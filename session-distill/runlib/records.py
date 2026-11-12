#!/usr/bin/env python3
"""What a run directory holds, and the rules stages keep over it.

`run.json` is the declaration (S0). It changes only through an amendment, which appends one
line to `amendments.jsonl` and advances `declaration_seq`. That log also binds every
`declaration_seq` to the sha256 of the run.json authorized at it (seq 0 is the declaration
itself), so a `run.json` edited by hand is found by comparing it with the log, whether or not
a stage has read it yet. Every stage S1-S12 leaves
`stages/<stage>/record.json` pinning the declaration it read (hash and sequence), the inputs
it consumed with the stage and sequence that produced each, and its outputs with their
hashes. A stage refuses to start when an input is partial, stale or invalid, or when the
declaration it would read is not the one its inputs were produced under, unless an amendment
licenses the difference (design §4, §4.1).

A stage's items fail under the run's posture (design §4): in production a failing item is
quarantined with the items sharing its unit, route or test configuration and the others
continue; in development and rehearsal the first failure stops the stage by name. An input
that is partial, stale or invalid is refused whatever the posture.

Failures are named by their first word: DECLARATION_DRIFT, INPUT_STALE, INPUT_PARTIAL,
INPUT_INVALID, OUTPUT_OUTSIDE_RUN, RUN_PATH_ESCAPE (`stagelock.confine`: no write leaves the run
directory, through a symlink or otherwise), ITEM_FAILED, ITEMS_JOBS_INVALID, SET_MISMATCH. Predicates return their
violations as a list; the ones that guard starting a stage or running its items raise `Refused`.

  records.py --self-test
"""
import concurrent.futures
import contextlib
import copy
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import threading

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import stagelock


JSONL_LINES = pathlib.Path(__file__).resolve().parents[2] / "wrappers" / "jsonl_lines.py"


def _load_jsonl_lines():
    """wrappers/jsonl_lines.py, loaded by path from this checkout: the one JSONL splitter, shipped
    (shipped readers use it too) and imported here, never copied; runlib's readers reach it as
    records.jsonl_lines (a text) and records.jsonl_read (a file, its bytes decoded here)."""
    if not JSONL_LINES.is_file():
        raise FileNotFoundError(f"JSONL_SPLITTER_MISSING {JSONL_LINES}: the one JSONL splitter is not there")
    spec = importlib.util.spec_from_file_location("agent_bios_jsonl_lines", JSONL_LINES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_jsonl = _load_jsonl_lines()
jsonl_lines, jsonl_read = _jsonl.split, _jsonl.read

# S0 is the declaration itself (run.json); these are the stages that read it and leave a record.
STAGES = ("S1", "S2", "S3", "S4", "S5", "S5b", "S6", "S7", "S7b", "S8", "S9", "S9b", "S10", "S10b", "S11",
          "S12")
# S5b (WP-11b) sits between S5 and S6 rather than at the end: `declare.py` derives an amendment's
# invalidation range from `STAGES.index` and sorts by it, so a stage appended after S12 would be
# invalidated last and ordered last whatever it actually runs before.
# The stages whose one record holds more than one producer, and the parts each has. A stage absent
# here keeps the single-producer record shape exactly as it was, and its readers do not change: S2
# produces the reading views and the inventory of the library, which neither calls the other nor
# may overwrite the other's record (design §6.1, §6.3). S10 parses the owner's decisions and, for a 판정, adjudicates
# them (design §10.1, §10.2; plan WP-20): two producers whose outputs neither may replace. S10b builds the final set
# the owner confirms and reads the owner's confirmation of it (design §10.3; plan WP-20 K6): the confirmation reads
# the build's manifest as its input, so the two are parts of one record rather than one producer replacing itself.
STAGE_PARTS = {"S2": ("views", "inventory"), "S10": ("parse", "adjudicate"), "S10b": ("build", "confirm"),
               "S11": ("plan", "effects")}
# A part a stage MAY have. It is written and read like any other part, and counts toward the stage's status only
# when it is there: S11's destination manifest (`destinations.write`) is not made by release 1's apply, which
# writes the declared checkout alone, so its absence must not leave a finished apply `partial`.
STAGE_OPTIONAL_PARTS = {"S11": ("destinations",)}


def parts_of(stage):
    return tuple(STAGE_PARTS.get(stage, ())) + tuple(STAGE_OPTIONAL_PARTS.get(stage, ()))
STATUSES = ("running", "complete", "partial", "failed")
OUTCOMES = ("retained", "merged", "rejected", "quarantined")  # design §3.2 item 5


class Refused(Exception):
    """A driver refusal; the message starts with the named code."""


class RunStopped(Refused):
    """A refusal that stops the run, not an item (W review of WP-08e r2, F2; lead decision): a call that stopped the run
    (INPUT_BOUND_EXCEEDED, CLAIM_EXCEEDED) or a dispatch refused while a stop stands (RUN_STOPPED). No posture quarantines
    it: `run_items` raises it as it is, under production too, and lets no item start after it, so the stage ends
    failed rather than complete with its units quarantined."""


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(pathlib.Path(path).read_bytes())


def json_text(obj):
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def bound_digest(obj):
    """The sha256 `write_json` gives a file holding `obj`: what the declaration log binds."""
    return sha256_bytes(json_text(obj).encode("utf-8"))


def write_text(run_dir, path, text):
    """Whole-file replace through a temporary in the same directory: a reader sees the old
    file or the complete new one. `path` is confined beneath `run_dir` first."""
    # Reached from the run directory's own descriptor (`stagelock.beneath`): confining the path and then opening
    # it by name let a directory swapped for a link in between take the temporary and the rename outside the run.
    with stagelock.beneath(run_dir, path) as (parent, name):
        temporary = f".{name}.{os.urandom(8).hex()}"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        except BaseException:
            try:
                os.unlink(temporary, dir_fd=parent)
            except OSError:
                pass
            raise


def write_json(run_dir, path, obj):
    write_text(run_dir, path, json_text(obj))


# The member names a stage record carries, which is what a refusal about one may name. A key outside
# this set is reported by its ordinal, so a name missing here costs a readable location and nothing
# more (`projection.document_location`).
RECORD_KEYS = frozenset((
    "stage", "parts", "status", "run_json_sha256", "declaration_seq", "started", "ended",
    "inputs", "outputs", "calls", "quarantined", "usage", "artifact", "sha256", "producer_stage",
    "producer_seq", "id", "reason", "because", "unit", "route", "test_config",
    "measured", "provisional", "unresolved", "complete",
))


def _floor():
    """`runlib.projection`, imported on use.

    `projection` imports this module for `jsonl_read`, so the two cannot both import at module
    level; the dependency that matters is this direction, because the floor is where a record is
    judged before it is published."""
    from runlib import projection
    return projection


def record_disclosures(document):
    """What a stage record would disclose, through the floor's one entry point.

    A stage record is a document this run writes, so it answers the question every written document
    answers — and it answers it BEFORE the bytes land, not after the stage completed. The earlier
    code checked only after `cmd_inventory` finished successfully, which left the `running` document
    and every failure record unchecked; an item's quarantine reason is an exception message, and an
    exception message is a path more often than not (GC#6)."""
    return _floor().document_disclosures(document, str(pathlib.Path.home()), schema=RECORD_KEYS)


def publish_record(run_dir, stage, document, failing=None):
    """THE publication of a stage record: judged by the floor, then written.

    Every write of `stages/<stage>/record.json` goes through here — the `running` document, the
    final one, the failure one, and the one carrying another part's preserved entry — so a control
    observes the real writer rather than a helper beside it.

    `failing` is the exception already on its way out, when there is one: the final publication runs
    in a `finally`, and a refusal there replaces what was in flight. The disclosure is the graver
    fact, so it is the one raised, but the failure it ran beside is carried in the message rather
    than swallowed."""
    problems = record_disclosures(document)
    if problems:
        floor = _floor()
        beside = ""
        if failing is not None:
            beside = (f" (raised while {type(failing).__name__}: "
                      f"{floor.diagnostic(failing, str(pathlib.Path.home()))} was in flight)")
        raise Refused(f"RECORD_DISCLOSES {stage}: {'; '.join(problems[:4])}"
                      + (f" (+{len(problems) - 4} more)" if len(problems) > 4 else "")
                      + f"; the stage record is not written{beside}")
    write_json(run_dir, record_path(run_dir, stage), document)


def read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused(f"RECORD_UNREADABLE {path}: {exc}") from exc


# The one place the fixture tree is located. A suite asks `fixture_root`, never recomputes the path, so a tree
# without the fixtures - a copy of the shipped files - ends every suite that needs them by name.
FIXTURE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "fixtures"


def fixture_root(*parts):
    """`session-distill/fixtures/`, or the directory `parts` names inside it, for a self-test - refused by name
    (`FIXTURES_ABSENT <path>`) when that directory is not there, rather than read until a file open fails."""
    path = FIXTURE_ROOT.joinpath(*parts)
    if not path.is_dir():
        raise Refused(f"FIXTURES_ABSENT {path}: this tree carries no {'/'.join(('fixtures',) + parts)} directory, which "
                      "this self-test's fixtures are read from")
    return path


def run_json_path(run_dir):
    return pathlib.Path(run_dir) / "run.json"


def amendments_path(run_dir):
    return pathlib.Path(run_dir) / "amendments.jsonl"


def record_path(run_dir, stage):
    return pathlib.Path(run_dir) / "stages" / stage / "record.json"


def append_amendment(run_dir, amendment):
    path = stagelock.confine(run_dir, amendments_path(run_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(amendment, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_log(run_dir):
    """Every line of `amendments.jsonl`: seq 0 is the declaration, seq 1.. the amendments."""
    path = amendments_path(run_dir)
    if not path.is_file():
        return []
    try:
        return [json.loads(line) for line in jsonl_read(path) if line.strip()]
    except ValueError as exc:
        raise Refused(f"RECORD_UNREADABLE {path}: {exc}") from exc


def read_amendments(run_dir):
    return [entry for entry in read_log(run_dir) if entry.get("seq", 0) >= 1]


def rebind(run_dir, digest):
    """Rebind the last log entry (the declaration at seq 0, before any stage has read it) to the
    run.json that `declare --set` has just written."""
    log = read_log(run_dir)
    log[-1] = {**log[-1], "run_json_sha256": digest}
    write_text(run_dir, amendments_path(run_dir), "".join(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n" for e in log))


def stage_records(run_dir):
    found = {}
    for stage in STAGES:
        path = record_path(run_dir, stage)
        if path.is_file():
            found[stage] = read_json(path)
    return found


def confine_declaration(run_dir):
    """Both files of a declaration, run.json and the log, confined to the run directory before
    either is read or written: a mutator that logs and then finds run.json linked away would
    otherwise leave the two disagreeing."""
    for destination in (run_json_path(run_dir), amendments_path(run_dir)):
        stagelock.confine(run_dir, destination)


def declaration_state(run_dir, who="declare"):
    """(run, run_json_sha256, amendments) of a run whose run.json is the declaration the log
    authorized: the log is numbered 0..n, `declaration_seq` is n, and the sha256 of run.json is
    the one bound to n. Anything else means run.json or the log was changed outside `declare`,
    and `who` (a stage, or declare) is told so by name. It confines both files first
    (RUN_PATH_ESCAPE), so every mutator that calls it under the declaration lock has done so
    before its first write."""
    confine_declaration(run_dir)
    path = run_json_path(run_dir)
    if not path.is_file():
        raise Refused(f"RUN_UNDECLARED {run_dir}: no run.json")
    run, log = read_json(path), read_log(run_dir)
    if not log:
        raise Refused(f"DECLARATION_DRIFT {who}: no declaration is bound to {path} (the log has no seq-0 entry)")
    if [entry.get("seq") for entry in log] != list(range(len(log))):
        raise Refused(f"DECLARATION_DRIFT {who}: the declaration log is not numbered 0..{len(log) - 1}")
    if run.get("declaration_seq") != len(log) - 1:
        raise Refused(f"DECLARATION_DRIFT {who}: run.json is at declaration_seq "
                      f"{run.get('declaration_seq')} but the declaration log ends at {len(log) - 1}")
    digest = sha256_file(path)
    if digest != log[-1].get("run_json_sha256"):
        raise Refused(f"DECLARATION_DRIFT {who}: run.json is not the declaration authorized at seq "
                      f"{len(log) - 1}: its sha256 is {digest[:12]}, the log bound {str(log[-1].get('run_json_sha256'))[:12]}")
    return run, digest, log[1:]


def check_declaration_order(consumer, consumer_seq, producer, producer_seq, amendments):
    """Whether `consumer`, which read declaration `consumer_seq`, may consume the results of
    `producer`, produced under `producer_seq` (design §4.1). Violations, empty when it may.

    Equal sequences pass. Otherwise some amendment in (producer_seq, consumer_seq] must list
    the consumer in `scope[]`, and none may list the producer in `invalidates[]`. No amendment
    between, none that lists the consumer, or a consumer that read an older declaration than
    its producer, is a silent advance."""
    if consumer_seq == producer_seq:
        return []
    between = [a for a in amendments if producer_seq < a["seq"] <= consumer_seq]
    errors = [f"INPUT_STALE {producer}: amendment {a['seq']} invalidates it" for a in between
              if producer in a["invalidates"]]
    if not between:
        errors.append(f"DECLARATION_DRIFT {consumer}: read declaration {consumer_seq} but consumed "
                      f"{producer}, produced under {producer_seq}, with no amendment between")
    elif not any(consumer in a["scope"] for a in between):
        errors.append(f"DECLARATION_DRIFT {consumer}: no amendment between {producer_seq} and "
                      f"{consumer_seq} lists it in scope")
    return errors


# The containment test of `stagelock.confine`, for paths that are read or merely named (artifacts, run ids).
contained = stagelock.contained


# What two items can share for one's failure to take the other with it (design §4).
SHARED_KEYS = ("unit", "route", "test_config")


def run_items(posture, items, work, jobs=1, stop=None):
    """Run `work(item)` over `items` under a failure posture (design §4).

    An item is `{id, unit, route, test_config}`; a key it does not have shares nothing. In
    `production` an item whose work raises is quarantined together with every other item that
    shares its unit, route or test configuration, those not yet run are skipped and those
    already done are moved to the quarantine, and the independent items continue. Under any
    other posture the first failure stops by name (ITEM_FAILED), and so does a missing posture.
    Returns `{done: [ids], quarantined: [{id, reason, because}]}`; `because` is the failing item
    that took the item with it, None for the failing item itself.

    With `jobs` above one, the items run that many at a time and the posture's rules hold as they do one at a time
    (WP-08 commit 5b): items joined by a shared unit, route or test configuration, directly or through others, run in
    one sequence in their order, so a failure skips and quarantines the others of its sequence exactly as above, and
    sequences that share nothing run side by side. Under any posture but production a failure sets `stop` (an event a
    caller may hold) and lets no item start after it; the items already running finish, and the earliest failure in
    `items` order is the one named. `done`
    and the quarantine are in `items` order. A `jobs` that is not a positive integer is refused (ITEMS_JOBS_INVALID).

    A `RunStopped` is not an item's failure: under every posture it is raised as it is, and no item starts after it."""
    expect_set(item["id"] for item in items)
    if isinstance(jobs, bool) or not isinstance(jobs, int) or jobs < 1:
        raise Refused(f"ITEMS_JOBS_INVALID {jobs!r}: items run one or more at a time")
    if jobs == 1:
        return _run_sequence(posture, items, work)
    order = {item["id"]: n for n, item in enumerate(items)}
    stop, failed = stop if stop is not None else threading.Event(), []

    def sequence(group):
        try:
            return _run_sequence(posture, group, work, stop)
        except RunStopped:
            raise                    # it has set `stop`; it passes through by its class, never by its words
        except Refused as exc:
            if not str(exc).startswith("ITEM_FAILED "):
                raise
            stop.set()
            failed.append((min(n for i, n in order.items() if str(exc).startswith(f"ITEM_FAILED {i} (")), exc))
            return {"done": [], "quarantined": []}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        outcomes = [future.result() for future in [pool.submit(sequence, group) for group in sharing_groups(items)]]
    if failed:
        raise min(failed, key=lambda pair: pair[0])[1]
    done = {i for outcome in outcomes for i in outcome["done"]}
    chunks = {}  # a failure and the items it took with it, in the order one at a time would list them
    for outcome in outcomes:
        for entry in outcome["quarantined"]:
            chunks.setdefault(entry["because"] or entry["id"], []).append(entry)
    return {"done": [item["id"] for item in items if item["id"] in done],
            "quarantined": [entry for key in sorted(chunks, key=order.get) for entry in chunks[key]]}


def sharing_groups(items):
    """`items` split into the sequences that share a unit, route or test configuration, directly or through others,
    each in `items` order, ordered by their first item."""
    parent = list(range(len(items)))

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    first = {}
    for n, item in enumerate(items):
        for key in SHARED_KEYS:
            if item.get(key) is not None:
                held = first.setdefault((key, item[key]), n)
                parent[find(n)] = find(held)
    groups = {}
    for n, item in enumerate(items):
        groups.setdefault(find(n), []).append(item)
    return list(groups.values())  # keyed in the order their first items come


def _run_sequence(posture, items, work, stop=None):
    """One sequence of `run_items`, one item at a time; with `stop`, no item starts once it is set."""
    done, quarantined = [], {}
    for item in items:
        if stop is not None and stop.is_set():
            break
        if item["id"] in quarantined:
            continue
        try:
            work(item)
        except RunStopped:
            if stop is not None:
                stop.set()
            raise
        except Exception as exc:
            # The reason is published in the stage record, and an exception's message is a path
            # often enough — an OSError's message IS one. It passes the floor here, where the text
            # is made, rather than at the seam that would then have to refuse the whole record.
            floor = _floor()
            reason = f"{type(exc).__name__}: {floor.project(str(exc), floor.CURRENT, str(pathlib.Path.home()))}"
            if posture != "production":
                raise Refused(f"ITEM_FAILED {item['id']} ({posture}): {reason}") from exc
            quarantined[item["id"]] = {"id": item["id"], "reason": reason, "because": None}
            for other in items:
                shared = [key for key in SHARED_KEYS
                          if item.get(key) is not None and item.get(key) == other.get(key)]
                if other["id"] != item["id"] and shared and other["id"] not in quarantined:
                    shared_value = floor.project(repr(item[shared[0]]), floor.CURRENT, str(pathlib.Path.home()))
                    quarantined[other["id"]] = {"id": other["id"], "because": item["id"],
                                                "reason": f"shares {shared[0]} {shared_value} with {item['id']}, which failed"}
            done = [i for i in done if i not in quarantined]
        else:
            done.append(item["id"])
    return {"done": done, "quarantined": list(quarantined.values())}


class StageRun:
    """The record of a running stage; the stage adds its outputs, runs its items under the
    run's posture, and may mark itself partial. `declaration` is the run.json the stage was
    admitted against, read under the declaration lock: a stage takes what it needs of the
    declaration from here, never from a read of its own made before admission, which an
    amendment could have overtaken (X review of WP-08 r1)."""

    def __init__(self, run_dir, record, posture, declaration=None):
        self.run_dir, self.record, self.posture = pathlib.Path(run_dir), record, posture
        self.declaration = declaration

    def admitted(self, early):
        """`early`, a declaration a stage read before admission so that it could refuse before writing a record, when it
        is the one this stage was admitted against; refused by name otherwise (DECLARATION_MOVED), because an amendment
        landed between the read and the admission (X review of WP-08 r2)."""
        if bound_digest(early) != self.record["run_json_sha256"]:
            raise Refused(f"DECLARATION_MOVED {self.record['stage']}: the declaration read before admission "
                          f"({bound_digest(early)[:12]}) is not the one the stage was admitted against "
                          f"({self.record['run_json_sha256'][:12]}, declaration_seq {self.record['declaration_seq']}); "
                          "run the stage again")
        return early

    def output(self, artifact):
        path = contained(self.run_dir, artifact)
        if path is None:
            raise Refused(f"OUTPUT_OUTSIDE_RUN {artifact}: leaves the run directory")
        self.record["outputs"].append({"artifact": artifact, "sha256": sha256_file(path)})

    def run_items(self, items, work, jobs=1):
        """`run_items` under this run's posture, `jobs` at a time; the quarantined items are listed in the record."""
        result = run_items(self.posture, items, work, jobs)
        self.record["quarantined"].extend(result["quarantined"])
        return result


def _legacy_part(stage, record):
    """Which declared part a pre-parts record belongs to, from the artifacts it recorded.

    A record written before a stage had parts names no producer, but its outputs do: `views.json`
    was written by the views part and by nothing else. A record whose outputs match no part's
    artifacts keeps no part name, and the caller decides what to do with it."""
    produced = {row.get("artifact") for row in record.get("outputs") or []}
    for label in parts_of(stage):
        if any(str(artifact).startswith(label) or str(artifact).startswith(f"{label}.")
               or str(artifact).startswith(f"{label}/") for artifact in produced):
            return label
    return None


def producing_part(record, artifact):
    """`(label, entry)` of the part of a stage record that produced `artifact`.

    A record with no `parts` is the single-producer shape and answers for itself, so every reader
    written before parts existed keeps working unchanged."""
    parts = record.get("parts")
    if not isinstance(parts, dict):
        return record.get("stage"), record
    for label in sorted(parts):
        entry = parts[label]
        if any(row.get("artifact") == artifact for row in entry.get("outputs", [])):
            return label, entry
    return None, None


def derived_status(record):
    """A stage's status, derived from its parts and never written on its own: complete only when
    every declared part is complete."""
    parts = record.get("parts")
    if not isinstance(parts, dict):
        return record.get("status")
    declared = tuple(STAGE_PARTS.get(record.get("stage"), ())) + tuple(
        label for label in STAGE_OPTIONAL_PARTS.get(record.get("stage"), ()) if label in parts)
    states = [parts.get(label, {}).get("status") for label in declared]
    if "failed" in states:
        return "failed"
    if "running" in states:
        return "running"
    if all(state == "complete" for state in states):
        return "complete"
    return "partial"


def _check_input(run_dir, stage, spec, seq, amendments, records):
    """(pinned input, violations) for one declared input `{artifact, producer_stage}`."""
    artifact, producer = spec["artifact"], spec["producer_stage"]
    produced = records.get(producer)
    if produced is None:
        return None, [f"INPUT_INVALID {producer}: no record for the stage that produces {artifact}"]
    # An input is judged against the PART that produced it: the inventory failing says nothing
    # about views.json, and views being partial says everything about it.
    label, produced = producing_part(produced, artifact)
    if produced is None:
        return None, [f"INPUT_INVALID {producer}: no part of its record produced {artifact}"]
    producer_label = f"{producer}.{label}" if label and label != producer else producer
    if produced.get("status") in ("running", "partial"):
        return None, [f"INPUT_PARTIAL {producer_label}: its record is {produced['status']}, so {artifact} is incomplete"]
    if produced.get("status") != "complete":
        return None, [f"INPUT_INVALID {producer_label}: its record is {produced.get('status')!r}"]
    path = contained(run_dir, artifact)
    if path is None:
        return None, [f"INPUT_INVALID {producer}: {artifact} leaves the run directory"]
    if not path.is_file():
        return None, [f"INPUT_INVALID {producer}: {artifact} is not a file"]
    digest = sha256_file(path)
    if {o["artifact"]: o["sha256"] for o in produced["outputs"]}.get(artifact) != digest:
        return None, [f"INPUT_INVALID {producer_label}: {artifact} is not the output {producer_label} recorded"]
    errors = check_declaration_order(stage, seq, producer, produced["declaration_seq"], amendments)
    return {"artifact": artifact, "sha256": digest, "producer_stage": producer,
            "producer_seq": produced["declaration_seq"]}, errors


def provenance_problems(stage, pinned, records):
    """INPUT_STALE for each producer of an admitted input that read another artifact this stage admits now, in bytes
    other than those it admits (W review of WP-09 r1, F2; lead decision). An output's own digest says the producer
    wrote it and nothing has changed it since; it does not say the producer read what is there now. A producer run
    again at the same declaration sequence leaves its consumers' inputs each valid alone and stale together: S1 run
    again under S3's results, which S4 would otherwise read beside the new census."""
    admitted = {entry["artifact"]: entry["sha256"] for entry in pinned}
    errors = {}
    for entry in pinned:
        label, produced = producing_part(records[entry["producer_stage"]], entry["artifact"])
        producer = entry["producer_stage"] + (f".{label}" if label and label != entry["producer_stage"] else "")
        for read in (produced or {}).get("inputs") or []:
            now_at = admitted.get(read["artifact"])
            if now_at is not None and read["sha256"] != now_at:
                errors[f"INPUT_STALE {producer}: it read {read['artifact']} at {read['sha256'][:12]}, and {stage} admits "
                       f"{read['artifact']} at {now_at[:12]}; {producer} is run again over what is there now"] = True
    return list(errors)


@contextlib.contextmanager
def run_stage(run_dir, stage, inputs=(), part=None):
    """Hold the stage's lock, refuse to start on a stale, partial or invalid input or a
    declaration edited outside `declare`, write the record as `running`, and finish it as
    `complete` (or as `partial` when the stage said so, or `failed` on an exception).

    `inputs` are `{artifact, producer_stage}`: the artifact's path under the run directory.

    `part` names one producer of a stage that has several (`STAGE_PARTS`). The record is still one
    file and one lock; this call reads it, replaces its own part's entry, and leaves every other
    part's entry exactly as it found it. The stage's own status is derived from the parts rather
    than written, so no producer can declare a stage complete on another's behalf."""
    if stage not in STAGES:
        raise Refused(f"STAGE_UNKNOWN {stage}: not one of {', '.join(STAGES)}")
    if part is not None and part not in parts_of(stage):
        raise Refused(f"STAGE_PART_UNKNOWN {stage}.{part}: the parts of {stage} are "
                      f"{list(parts_of(stage)) or 'none'}")
    if part is None and stage in STAGE_PARTS:
        # A part-less write to a stage that HAS parts replaces the whole record, whatever is there.
        # Refusing only when another part's entry already exists made the rule depend on the order
        # the producers happened to run in (GC#9).
        raise Refused(f"STAGE_PART_REQUIRED {stage}: it has the parts {list(STAGE_PARTS[stage])}, so a "
                      f"writer names the part it produces")
    with stagelock.hold(run_dir, f"stage-{stage}"):
        # the declaration lock makes "read the declaration, check, pin it" one step: `declare`
        # cannot edit or amend between the check and the record
        with stagelock.hold(run_dir, "declaration"):
            run, digest, amendments = declaration_state(run_dir, stage)
            seq, records, errors, pinned = run["declaration_seq"], stage_records(run_dir), [], []
            for spec in inputs:
                entry, problems = _check_input(run_dir, stage, spec, seq, amendments, records)
                errors.extend(problems)
                if entry:
                    pinned.append(entry)
            errors.extend(provenance_problems(stage, pinned, records))
            if errors:
                raise Refused("\n".join(errors))
            record = {"stage": stage, "run_json_sha256": digest, "declaration_seq": seq, "started": now(),
                      "ended": None, "status": "running", "inputs": pinned, "outputs": [], "calls": [],
                      "quarantined": [], "usage": {"measured": 0, "provisional": 0, "unresolved": 0, "complete": False}}
            document = record
            existing = read_json(record_path(run_dir, stage)) if record_path(run_dir, stage).is_file() else {}
            if part is not None:
                parts = dict(existing.get("parts") or {})
                if not parts and existing.get("outputs") is not None:
                    # A record written before this stage had parts is one producer's record. Which
                    # producer is decided by the artifacts it carries, and it is kept: adding a part
                    # beside it must not take `views.json` away from the stage that made it (GB#11).
                    kept = _legacy_part(stage, existing)
                    if kept is None:
                        # A running or failed record with no outputs names no producer, and its
                        # artifacts cannot name one either. Discarding it silently is what GB#11
                        # forbids, so the ambiguity is refused rather than resolved (GC#9).
                        raise Refused(f"STAGE_PART_AMBIGUOUS {stage}: the record already here names no part "
                                      f"and its outputs identify none (status "
                                      f"{existing.get('status')!r}, {len(existing.get('outputs') or [])} "
                                      f"output(s)); close or remove it before a part writes")
                    if kept != part:
                        parts[kept] = existing
                parts[part] = record
                document = {"stage": stage, "parts": parts}
                document["status"] = derived_status(document)
            elif existing.get("parts"):
                raise Refused(f"STAGE_PART_REQUIRED {stage}: its record already holds the parts "
                              f"{sorted(existing['parts'])}, and a writer that names no part would "
                              f"replace all of them")
            publish_record(run_dir, stage, document)
        try:
            yield StageRun(run_dir, record, run.get("posture"), copy.deepcopy(run))
        except BaseException:
            record["status"] = "failed"
            raise
        else:
            if record["status"] == "running":
                record["status"] = "complete"
        finally:
            record["ended"] = now()
            if part is not None:
                document["status"] = derived_status(document)
            publish_record(run_dir, stage, document, sys.exc_info()[1])


@contextlib.contextmanager
def fx_amended_at_admission(stage, assignments, when="before"):
    """Self-test fixture: while it is held, `run_stage` of `stage` has an amendment of `assignments` land just before its
    admission (`before`) or just after it (`after`) - the two places a stage that reads the declaration on its own can
    be overtaken (X review of WP-08 r1 and r2). Every stage's race control uses it, so the two cases are the same two
    cases everywhere. `run_stage` is restored on exit."""
    from runlib import declare  # declare imports this module, so the fixture imports it when it runs
    if when not in ("before", "after"):
        raise ValueError(f"when: {when!r}")
    module, admitted = sys.modules[__name__], run_stage

    @contextlib.contextmanager
    def racing(run_dir, name, inputs=(), part=None):
        if name == stage and when == "before":
            declare.amend(run_dir, assignments, f"an amendment just before {stage}'s admission")
        with admitted(run_dir, name, inputs, part=part) as held:
            if name == stage and when == "after":
                declare.amend(run_dir, assignments, f"an amendment just after {stage}'s admission")
            yield held
    module.run_stage = racing
    try:
        yield
    finally:
        module.run_stage = admitted


# The structural guard of the declaration a stage reads (X review of WP-08 r2; the shape three reviews found one stage at
# a time): a stage builds from the declaration it was admitted against, `StageRun.declaration`, so outside the sites
# listed here nothing reads run.json - takes its path, reads its state, or spells its name. Each site is a module and its
# top-level function, or a class's method, with the reason it may. A site not listed, a listed site that no longer reads
# the declaration, and a scan that found no module or no site fail by name: DECLARATION_READ_UNLISTED,
# DECLARATION_READ_STALE, DECLARATION_READ_UNSCANNED. Every Python module of session-distill is scanned, the pipeline
# beside distill.py included. The guard sees a read where it is spelled: a listed site that hands what it read to its
# caller hands on the declaration, so each reason says what the site does with it.
DECLARATION_FILE = "run.json"
DECLARATION_READS = frozenset(("run_json_path", "declaration_state"))
DECLARATION_MODULES = ("*.py", "runlib/*.py")
DECLARATION_READERS = {
    ("runlib/records.py", "<module>"): "this guard's own DECLARATION_FILE, the name it looks for",
    ("runlib/records.py", "run_json_path"): "the one place the declaration's path is spelled",
    ("runlib/records.py", "confine_declaration"): "confines the declaration's path beneath the run before anything reads it",
    ("runlib/records.py", "declaration_state"): "the declaration's reader, which takes no lock itself and checks that run.json "
                                                "is the one the log binds. Its callers hold different locks: run_stage's "
                                                "stage admission and dispatch's stop stamp (_stop_run) hold the declaration "
                                                "lock; dispatch's reservation (reserve) holds the supervisor's lock alone, "
                                                "and so does the standing-stop check (_blocked) where reserve and a call's "
                                                "launch make it; that check as a call first makes it and the seat admission "
                                                "(_admit_seat), both before the call takes the supervisor's lock, and the "
                                                "read-only budget query (remaining) hold neither. A read without the "
                                                "declaration lock that lands "
                                                "mid-amendment is refused by name (DECLARATION_DRIFT) rather than believed",
    ("runlib/records.py", "run_stage"): "admits a stage: what it reads under the lock is the StageRun.declaration the stage "
                                        "builds from",
    ("runlib/destinations.py", "_self_test_body"): "reads back the run.json its own fixture just wrote, to judge the "
                                             "manifest against the roots a real declaration carries rather than a "
                                             "shape invented in the suite. The module itself never reads the "
                                             "declaration from disk: `document` and `write` are handed it by their "
                                             "caller, which is what lets apply resolve destinations before it opens "
                                             "any stage record. The suite's own body carries the "
                                             "read because a dying-control wrapper owns the name "
                                             "`self_test`, and this allowlist is keyed by the "
                                             "FUNCTION that reads, not by the file",
    ("runlib/declare.py", "create"): "the declaration's writer (S0): writes run.json under the declaration lock",
    ("runlib/declare.py", "set_fields"): "the declaration's writer: an amendment's fields, read and written under the lock",
    ("runlib/declare.py", "amend"): "the declaration's writer: an amendment, read and written under the lock",
    ("runlib/census.py", "run"): "S1 reads the declaration before admission for the coverage base and originator table it "
                                 "pins; StageRun.admitted refuses that read unless it is byte for byte the declaration S1 was "
                                 "admitted against (DECLARATION_MOVED)",
    ("runlib/dispatch.py", "Supervisor.remaining"): "the budget a stage has left, read against the declaration current "
                                                    "when it is asked, as a reservation reads it",
    ("runlib/dispatch.py", "Supervisor.reserve"): "a call's reservation reads the budget current at the call, under the "
                                                  "dispatcher's lock: a call's admission, not a stage's build",
    ("runlib/dispatch.py", "Supervisor._admit_seat"): "a call's seat and host allowance are admitted against the "
                                                      "declaration current when it is made",
    ("runlib/dispatch.py", "Supervisor._blocked"): "whether an amendment lifts the run's standing stop is read from the "
                                                   "declaration's log as it stands",
    ("runlib/dispatch.py", "Supervisor._stop_run"): "a run's stop is stamped with the declaration and amendments current "
                                                    "when it stops",
    ("runlib/inventory.py", "<module>"): "RUN_MARKERS names the declaration's file to recognise a run directory, and reads "
                                         "nothing of it",
    ("distill.py", "self_test"): "the CLI's self-test reads the declarations its scratch runs made, to check what each "
                                 "command declared and recorded",
    ("runlib/records.py", "self_test"): "the records self-test reads the declarations it plants",
    ("runlib/declare.py", "self_test"): "the declaration's own self-test reads what its writer wrote",
    ("runlib/census.py", "controls"): "the census self-test's body reads its scratch runs' declarations, to check what S1 "
                                      "recorded against them",
    ("runlib/dispatch.py", "self_test"): "the dispatcher's self-test plants and reads its scratch runs' declarations",
    ("runlib/views.py", "self_test"): "the S2 self-test reads its scratch runs' declarations, to check what S2 recorded",
    ("runlib/stage_review_korean.py", "self_test"): "the S9b suite reads the seats its golden run declares, to amend them "
                                                    "with the stage's two seats (a dotted key is assigned as a whole map)",
    ("runlib/stage_adjudicate.py", "self_test"): "the S10 suite reads the seats its golden run declares, to amend "
                                                 "them with the second pass's two seats (a dotted key is assigned as "
                                                 "a whole map)",
    ("runlib/stage_apply.py", "_held_declaration"): "S11's effects part takes the declaration's lock around every "
                                                    "write and reads the declaration again under it, held to the one "
                                                    "it was admitted under: admission releases that lock, so an "
                                                    "amendment could otherwise land while files are being written",
    ("runlib/stage_close.py", "_self_test_body"): "the S12 suite reads the declaration of the run S3's own fixture made, "
                                                  "to fold its results as the stage does under its admission",
    ("runlib/stage_read.py", "fx_reader"): "the S3 fixture reads the seat its golden run declared, to seed the supervisor "
                                           "before S3 runs",
    ("runlib/stage_read.py", "self_test"): "the S3 self-test reads its scratch runs' declarations, to check what S3 "
                                           "recorded against them",
    ("runlib/stage_delivery.py", "standing_stop"): "S5b asks whether a stop still stands before it writes an evidence "
                                                   "document that would be read as whole, and only a later amendment of "
                                                   "a stop's own key lifts one: the read is of the log alone, outside "
                                                   "the stage's admission, and a declaration it cannot read holds every "
                                                   "recorded stop standing rather than reading the run open",
}


def declaration_texts(root=None):
    """The sources `declaration_reads` judges: every module of `DECLARATION_MODULES`, by path relative to session-distill."""
    root = pathlib.Path(root) if root is not None else pathlib.Path(__file__).resolve().parents[1]
    return {path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
            for pattern in DECLARATION_MODULES for path in sorted(root.glob(pattern))}


def declaration_reads(texts, allowed=None):
    """`(violations, sites)` of the declaration guard over `texts` (`{relative path: source}`). A site is where code
    names `run_json_path` or `declaration_state`, under any name it imported them as, or the literal "run.json"; it is
    keyed by its module and top-level function, a class's method as `Class.method`, or `<module>`."""
    import ast
    allowed = DECLARATION_READERS if allowed is None else allowed
    sites = {}
    for rel, text in sorted(texts.items()):
        tree = ast.parse(text)
        names = set(DECLARATION_READS) | {a.asname for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                                         for a in n.names if a.name in DECLARATION_READS and a.asname}
        units = []
        for top in tree.body:
            if isinstance(top, ast.ClassDef):
                units += [(f"{top.name}.{m.name}" if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) else top.name, m)
                          for m in top.body]
            else:
                units.append((top.name if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)) else "<module>", top))
        for name, unit in units:
            for node in ast.walk(unit):
                if (isinstance(node, ast.Constant) and node.value == DECLARATION_FILE) \
                        or (isinstance(node, ast.Name) and node.id in names) \
                        or (isinstance(node, ast.Attribute) and node.attr in DECLARATION_READS):
                    sites.setdefault((rel, name), node.lineno)
    violations = [f"DECLARATION_READ_UNLISTED {rel}:{line} ({name}): reads the declaration where no stage's admission "
                  "carries it; a stage builds from StageRun.declaration, and a site that must read run.json is listed in "
                  "records.DECLARATION_READERS with its reason" for (rel, name), line in sorted(sites.items())
                  if (rel, name) not in allowed]
    violations += [f"DECLARATION_READ_STALE {rel} ({name}): listed in records.DECLARATION_READERS, and it no longer reads "
                   "the declaration" for rel, name in sorted(set(allowed) - set(sites))]
    if not texts or not sites:
        violations.append(f"DECLARATION_READ_UNSCANNED: {len(texts)} modules scanned and {len(sites)} sites found; a "
                          "guard that judged nothing is not clean")
    return violations, set(sites)


def expect_set(ids):
    """The ids a transformation must account for, each once."""
    ids = list(ids)
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise Refused(f"SET_MISMATCH expected ids repeat: {repeated}")
    return frozenset(ids)


def observe_set(expected, outcomes):
    """Violations of the set accounting of design §3.2 item 5, empty when it holds.

    Every expected id must appear exactly once as `retained`, `rejected` (with a `reason`),
    `quarantined`, or inside the `members` of a `merged` output. An outcome is
    `{id, outcome[, reason][, members]}`; for `merged`, `id` names the merged output and
    `members` the input ids it absorbs. An outcome of any other kind, a merge without
    members and a rejection without a reason account for nothing."""
    accounted, invalid, output_ids = [], [], []
    for item in outcomes:
        kind, reason, members = item.get("outcome"), item.get("reason"), item.get("members")
        output_ids.append(item.get("id"))
        if kind == "merged" and members:
            accounted.extend(members)
        elif kind in ("retained", "quarantined") or (kind == "rejected" and reason):
            accounted.append(item.get("id"))
        else:
            invalid.append(item.get("id"))
    missing = sorted(expected - set(accounted))
    extra = sorted(set(accounted) - expected)
    repeated = sorted({i for i in accounted if accounted.count(i) > 1}
                      | {i for i in output_ids if output_ids.count(i) > 1})
    if missing or extra or repeated or invalid:
        return [f"SET_MISMATCH missing={missing} extra={extra} repeated={repeated} invalid={sorted(invalid)}"]
    return []


def broad_handlers(src, module):
    """Every handler of production code in `src` that a RunStopped can meet - one catching a class of its MRO, or bare -
    as `(key, reraises)` (the lead's verification of WP-08e commit 4, finding 3). `key` is `module:function:caught#n`,
    n counting the same catch in the same function, so a line moving never renames a site. `reraises` is structural: a
    handler of the same `try` before it catches RunStopped and ends in a bare `raise`, or the handler itself always
    ends in one (its last statement, with no return, break or continue anywhere in it). A `self_test`, a
    `_self_test…` body it delegates to, and what is nested in either is not production code."""
    import ast
    catches = {cls.__name__ for cls in RunStopped.__mro__} - {"object"}

    def caught(handler):
        if handler.type is None:
            return ["<bare>"]
        elts = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        return [ast.unparse(e).split(".")[-1] for e in elts]

    def always_raises(handler):
        nodes = [n for stmt in handler.body for n in ast.walk(stmt)]
        return (bool(handler.body) and isinstance(handler.body[-1], ast.Raise) and handler.body[-1].exc is None
                and not any(isinstance(n, (ast.Return, ast.Break, ast.Continue)) for n in nodes))

    out, seen = [], {}

    def walk(node, path):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # The suite, whatever it is called: a module whose `self_test` is a wrapper that
                # reports a dying control keeps its body in `_self_test_body`, and that body's
                # handlers are the suite's as much as the wrapper's are.
                if child.name == "self_test" or child.name.startswith("_self_test"):
                    continue
                walk(child, path + [child.name])
                continue
            if isinstance(child, ast.Try):
                passed = False                  # an earlier handler of this try re-raises a RunStopped
                for handler in child.handlers:
                    names = caught(handler)
                    if "RunStopped" in names and always_raises(handler):
                        passed = True
                        continue
                    if any(n in catches or n == "<bare>" for n in names):
                        where = f"{module}:{'.'.join(path) or '<module>'}:{'|'.join(names)}"
                        seen[where] = seen.get(where, 0) + 1
                        out.append((f"{where}#{seen[where]}", passed or always_raises(handler)))
            walk(child, path)
    walk(ast.parse(src), [])
    return out


def self_test():
    failures = []

    def expect(label, errors, *needles):
        """`errors` must name every needle; with no needle it must be empty."""
        if not needles and errors:
            failures.append(f"{label}: expected no violation, got {errors}")
        for needle in needles:
            if not any(needle in line for line in errors):
                failures.append(f"{label}: expected {needle!r} in {errors}")

    def amend(seq, scope=("S2", "S3"), invalidates=()):
        return {"seq": seq, "at": now(), "reason": "fixture", "scope": list(scope),
                "invalidates": list(invalidates), "diff": {}}

    # check_declaration_order (WP-01 done-when 2). Positive controls first.
    expect("equal sequences", check_declaration_order("S2", 0, "S1", 0, []))
    expect("amended, scope covers, producer not invalidated",
           check_declaration_order("S2", 1, "S1", 0, [amend(1, scope=("S2",))]))
    expect("two amendments, both license the consumer",
           check_declaration_order("S3", 2, "S1", 0, [amend(1), amend(2)]))
    expect("silently advanced", check_declaration_order("S2", 1, "S1", 0, []),
           "DECLARATION_DRIFT S2", "with no amendment between")
    expect("amendment outside the range does not count",
           check_declaration_order("S2", 1, "S1", 0, [amend(2)]), "DECLARATION_DRIFT S2")
    expect("the producer's own declaration is not between",
           check_declaration_order("S3", 2, "S2", 1, [amend(1, scope=("S3",))]), "DECLARATION_DRIFT S3")
    expect("producer invalidated", check_declaration_order("S2", 1, "S1", 0, [amend(1, invalidates=("S1",))]),
           "INPUT_STALE S1")
    expect("amendment does not list the consumer",
           check_declaration_order("S4", 1, "S1", 0, [amend(1, scope=("S2",))]), "DECLARATION_DRIFT S4")
    expect("one amendment licenses the consumer, a later one is about another stage",
           check_declaration_order("S3", 2, "S1", 0, [amend(1, scope=("S3",)), amend(2, scope=("S2",))]))
    expect("the licence comes after an amendment about another stage",
           check_declaration_order("S3", 2, "S1", 0, [amend(1, scope=("S2",)), amend(2, scope=("S3",))]))
    expect("amendments between, none lists the consumer",
           check_declaration_order("S3", 2, "S1", 0, [amend(1, scope=("S2",)), amend(2, scope=("S2",))]),
           "DECLARATION_DRIFT S3", "lists it in scope")
    expect("a licence does not outlive a later invalidation of the producer",
           check_declaration_order("S3", 2, "S1", 0, [amend(1, scope=("S3",)),
                                                      amend(2, scope=("S2",), invalidates=("S1",))]),
           "INPUT_STALE S1")
    expect("consumer read an older declaration than its producer",
           check_declaration_order("S2", 0, "S1", 1, [amend(1)]), "DECLARATION_DRIFT S2")

    # set accounting (done-when 4)
    expected = expect_set(["a", "b", "c"])
    expect("equal sets", observe_set(expected, [{"id": i, "outcome": "retained"} for i in "abc"]))
    expect("every outcome kind", observe_set(expected, [
        {"id": "a", "outcome": "retained"}, {"id": "m", "outcome": "merged", "members": ["b", "c"]}]))
    expect("rejected with a reason and quarantined", observe_set(expected, [
        {"id": "a", "outcome": "rejected", "reason": "duplicate"}, {"id": "b", "outcome": "quarantined"},
        {"id": "c", "outcome": "retained"}]))
    expect("one id missing", observe_set(expected, [{"id": i, "outcome": "retained"} for i in "ab"]),
           "SET_MISMATCH", "missing=['c']")
    expect("one extra id", observe_set(expected, [{"id": i, "outcome": "retained"} for i in "abcd"]),
           "SET_MISMATCH", "extra=['d']")
    expect("one missing and one extra, both named",
           observe_set(expected, [{"id": i, "outcome": "retained"} for i in "abd"]),
           "missing=['c']", "extra=['d']")
    expect("an id accounted twice",
           observe_set(expected, [{"id": i, "outcome": "retained"} for i in "abcc"]), "repeated=['c']")
    expect("a member also retained", observe_set(expected, [
        {"id": "a", "outcome": "retained"}, {"id": "b", "outcome": "retained"},
        {"id": "m", "outcome": "merged", "members": ["b", "c"]}]), "repeated=['b']")
    expect("merge without members", observe_set(expected, [
        {"id": "a", "outcome": "retained"}, {"id": "b", "outcome": "retained"},
        {"id": "c", "outcome": "merged", "members": []}]), "invalid=['c']")
    expect("rejection without a reason", observe_set(expected, [
        {"id": "a", "outcome": "retained"}, {"id": "b", "outcome": "retained"},
        {"id": "c", "outcome": "rejected"}]), "missing=['c']", "invalid=['c']")
    expect("an outcome outside the four", observe_set(expected, [
        {"id": i, "outcome": "dropped"} for i in "abc"]), "invalid=['a', 'b', 'c']")
    try:
        expect_set(["a", "a"])
        failures.append("an expected set with a repeated id was accepted")
    except Refused as exc:
        expect("repeated expected id", [str(exc)], "SET_MISMATCH")

    # the failure posture over items (design §4): production quarantines with dependants and goes on
    def item(name, **keys):
        return {"id": name, **keys}

    batch = [item("A", unit="U1"), item("B", unit="U1", route="R1", test_config="T1"), item("C", route="R1", unit="U5"),
             item("D", test_config="T1"), item("E", unit="U2"), item("F"), item("G", route="R3"), item("X", unit="U5")]

    def run_batch(posture, items, fails=("B",)):
        calls = []

        def work(it):
            calls.append(it["id"])
            if it["id"] in fails:
                raise ValueError(f"{it['id']} failed")
        try:
            return run_items(posture, items, work), calls
        except Refused as exc:  # production that stopped is reported under its own controls, not a crash
            return ({"done": [], "quarantined": [], "stopped": str(exc)} if posture == "production" else str(exc)), calls

    def run_batch_jobs(posture, items, jobs, fails=("B",)):
        calls, calls_lock = [], threading.Lock()

        def work(it):
            with calls_lock:
                calls.append(it["id"])
            if it["id"] in fails:
                raise ValueError(f"{it['id']} failed")
        try:
            return run_items(posture, items, work, jobs=jobs), calls
        except Refused as exc:
            return ({"done": [], "quarantined": [], "stopped": str(exc)} if posture == "production" else str(exc)), calls

    result, calls = run_batch("production", batch)
    expect("production: the failing item and its dependants are quarantined, the rest continue",
           [] if sorted(q["id"] for q in result["quarantined"]) == ["A", "B", "C", "D"]
           and result["done"] == ["E", "F", "G", "X"] else [f"{result}"])
    expect("production: a dependant that was not yet run is skipped, not run", [] if "C" not in calls and "D" not in calls
           else [f"calls {calls}"])
    expect("production: a dependant already done is moved to the quarantine",
           [] if "A" in calls and any(q["id"] == "A" and q["because"] == "B" and "unit 'U1'" in q["reason"]
                                      for q in result["quarantined"]) else [f"{result}, calls {calls}"])
    expect("production: the failing item says why and is not its own dependant",
           [] if {"id": "B", "reason": "ValueError: B failed", "because": None} in result["quarantined"]
           else [f"{result}"])
    expect("production: sharing is one hop, a dependant's other unit takes no one else",
           [] if "X" in result["done"] else [f"{result}"])
    result, calls = run_batch("production", [item("P"), item("Q"), item("R", unit="U1")], fails=("P",))
    expect("production: items with no shared key are independent",
           [] if result["done"] == ["Q", "R"] and [q["id"] for q in result["quarantined"]] == ["P"] else [f"{result}"])
    result, calls = run_batch("production", batch, fails=())
    expect("production: no failure, nothing quarantined", [] if result["quarantined"] == [] and len(result["done"]) == 8
           else [f"{result}"])
    for posture in ("development", "rehearsal", None):
        message, calls = run_batch(posture, batch)
        expect(f"{posture}: the first failure stops by name and nothing after it runs",
               [message] if isinstance(message, str) else [f"{message}"],
               f"ITEM_FAILED B ({posture}): ValueError: B failed")
        if calls != ["A", "B"]:
            failures.append(f"{posture}: work continued past the failure: {calls}")
    message, _calls = run_batch("production", [item("A"), item("A")])
    expect("items with a repeated id", [message] if isinstance(message, str) else [f"{message}"], "SET_MISMATCH")

    # W r2, F2: a refusal that stops the run is not an item's failure, under production too
    stopped_calls = []

    def run_stops(it):
        stopped_calls.append(it["id"])
        if it["id"] == "B":
            raise RunStopped("CLAIM_EXCEEDED r-S3-B-a1: 3 main requests, at most 2")
    for posture, jobs in (("production", 1), ("production", 4), ("development", 1)):
        stopped_calls.clear()
        try:
            run_items(posture, batch, run_stops, jobs=jobs)
            raised = None
        except RunStopped as exc:
            raised = str(exc)
        except Exception as exc:  # noqa: BLE001 - a quarantine or another refusal fails the control by name
            raised = f"{type(exc).__name__}: {exc}"
        expect(f"W r2 F2: a run stop raised by an item ends run_items as itself under {posture}, {jobs} at a time, "
               "and quarantines nothing",
               [] if raised == "CLAIM_EXCEEDED r-S3-B-a1: 3 main requests, at most 2"
               and (jobs > 1 or stopped_calls == ["A", "B"]) else [f"{raised} calls {stopped_calls}"])

    # the lead's verification of commit 4, finding 3: every handler a RunStopped can meet re-raises it or is named here
    # with its reason. A module is scanned when its code names RunStopped or a supervisor - the only places one is
    # raised or passes; census and views run stages through `run_stage` and `run_items` with no supervisor, so none
    # arises in them. A site re-raising by structure (`broad_handlers`) needs no entry; an unnamed one fails by name.
    cannot_see = "its try body calls no supervisor, item or stage, so no RunStopped is raised inside it"
    stop_sites = {
        "dispatch:Supervisor._stop_run:Exception#1": f"taking the declaration lock; {cannot_see}",
        "dispatch:Supervisor._stop_run:Exception#2": f"reading the declaration to stamp the stop; {cannot_see}",
        "dispatch:Supervisor._stop_run:Exception#3": f"stamping the stop, this code's arithmetic; {cannot_see}",
        "dispatch:Supervisor._now:Exception#1": f"the run's clock; {cannot_see}",
        "dispatch:Supervisor._now:Exception#2": f"the fallback clock; {cannot_see}",
        "dispatch:Supervisor._rows_snapshot:Exception#1": f"copying the monitor's rows; {cannot_see}",
        "dispatch:Supervisor._offer_stop:Exception#1": "deciding and recording one obligation's stop (_bound_entry, "
                                                       f"_claim_entry, _stop_run), which raise none; {cannot_see}",
        "dispatch:Supervisor._bound_entry:Exception#1": f"serializing the stop entry; {cannot_see}",
        "dispatch:Supervisor._record_stop:Exception#1": f"writing the call's own record of its stop; {cannot_see}",
        "dispatch:Supervisor.call:OSError|Refused#1": f"reading the server policy record; {cannot_see}",
        "dispatch:Supervisor.call:Exception#1": "offering the stop on the failure path; _offer_stop raises none and the "
                                                "enclosing handler re-raises the original failure",
        "dispatch:Supervisor.item:Refused#1": f"building the expected packet to size the reservation; {cannot_see}",
        "dispatch:Supervisor.reusable:Refused#1": f"the gate's refusal of an earlier attempt; {cannot_see}",
        "stage_form:origin_of:Refused#1": f"storing an origin block as evidence; {cannot_see}",
        "stage_read:keep:Refused#1": f"locating one quote in the view; {cannot_see}",
    }
    import ast as _ast
    here = pathlib.Path(__file__).resolve().parent
    suite_src = ("def _self_test_body(failures, ran):\n    try:\n        pass\n    except Refused:\n        pass\n"
                 "def run():\n    try:\n        pass\n    except Refused:\n        pass\n")
    expect("a handler in a suite's delegated body is the suite's, and the same handler in production code is not",
           [] if [key for key, _r in broad_handlers(suite_src, "m")] == ["m:run:Refused#1"]
           else [f"{broad_handlers(suite_src, 'm')}"])

    def stop_modules(read):
        """The runlib modules whose code names RunStopped or a supervisor: `{stem: source}`."""
        out = {}
        for path in sorted(here.glob("*.py")):
            src = read(path)
            tree = _ast.parse(src)
            ids = ({n.attr for n in _ast.walk(tree) if isinstance(n, _ast.Attribute)}
                   | {n.id for n in _ast.walk(tree) if isinstance(n, _ast.Name)})
            if ids & {"RunStopped", "Supervisor", "supervisor"}:
                out[path.stem] = src
        return out

    def stop_site_problems(modules, named):
        found = [site for stem, src in modules.items() for site in broad_handlers(src, stem)]
        unnamed = [key for key, reraises in found if not reraises and key not in named]
        stale = sorted(set(named) - {key for key, reraises in found if not reraises})
        return ([f"STOP_HANDLER_UNNAMED {key}: catches a RunStopped and neither re-raises it nor is named" for key in unnamed]
                + [f"STOP_HANDLER_STALE {key}: named, and no handler that keeps a RunStopped is there" for key in stale]
                + ([] if found else ["STOP_HANDLER_NONE: the scan found no handler at all"]))
    live_modules = stop_modules(lambda path: path.read_text(encoding="utf-8"))
    expect("lead v4 3: the modules a RunStopped passes through are scanned - dispatch, records, stage_form, stage_read",
           [] if {"dispatch", "records", "stage_form", "stage_read"} <= set(live_modules) else [sorted(live_modules)])
    expect("lead v4 3: every handler a RunStopped can meet re-raises it or is named with its reason",
           stop_site_problems(live_modules, stop_sites))
    reraising = [key for stem, src in live_modules.items() for key, rr in broad_handlers(src, stem) if rr]
    expect("lead v4 3: the re-raising sites are found as such - run_items' two sequences, run_stage, the call's own",
           [] if {"records:_run_sequence:Exception#1", "records:run_items.sequence:Refused#1",
                  "records:run_stage:BaseException#1", "dispatch:Supervisor.call:BaseException#1"} <= set(reraising)
           else [sorted(reraising)])
    planted = dict(live_modules)
    planted["dispatch"] = planted["dispatch"].replace(
        "            except breakers.Deferred as exc:\n                return {\"item\": item, \"outcome\": \"deferred\"",
        "            except Refused:\n                return None\n            except breakers.Deferred as exc:\n"
        "                return {\"item\": item, \"outcome\": \"deferred\"", 1)
    expect("control, lead v4 3: a handler planted around the supervisor's call that swallows a refusal fails by name",
           stop_site_problems(planted, stop_sites) if planted["dispatch"] != live_modules["dispatch"] else ["not planted"],
           "STOP_HANDLER_UNNAMED dispatch:Supervisor.item:Refused#2")
    unpassed = dict(live_modules)
    unpassed["records"] = unpassed["records"].replace(
        "        except RunStopped:\n            if stop is not None:\n                stop.set()\n            raise\n", "", 1)
    expect("control, lead v4 3: _run_sequence without its RunStopped pass fails by name - its Exception handler then "
           "keeps the stop",
           stop_site_problems(unpassed, stop_sites) if unpassed["records"] != live_modules["records"] else ["not planted"],
           "STOP_HANDLER_UNNAMED records:_run_sequence:Exception#1")
    expect("control, lead v4 3: a named site that no longer keeps a RunStopped is stale, by name",
           stop_site_problems(live_modules, {**stop_sites, "dispatch:Supervisor.gone:Refused#1": "x"}),
           "STOP_HANDLER_STALE dispatch:Supervisor.gone:Refused#1")
    expect("control, lead v4 3: a scan over nothing reports nothing found", stop_site_problems({}, {}),
           "STOP_HANDLER_NONE")

    # WP-08 commit 5b: items run `jobs` at a time under the same rules
    one_at_a_time, calls_one = run_batch("production", batch)
    side_by_side, calls_many = run_batch_jobs("production", batch, 4)
    expect("jobs: production over the batch four at a time quarantines and keeps what one at a time does, in its order",
           [] if side_by_side == one_at_a_time else [f"{side_by_side} != {one_at_a_time}"])
    expect("jobs: a dependant not yet run is skipped four at a time too, because items that share run in one sequence",
           [] if "C" not in calls_many and "D" not in calls_many and sorted(calls_many) == sorted(calls_one)
           else [f"calls {calls_many}"])
    expect("jobs: the sequences are the items joined by a shared key, directly or through others, in items order",
           [] if [[i["id"] for i in g] for g in sharing_groups(batch)] == [["A", "B", "C", "D", "X"], ["E"], ["F"], ["G"]]
           else [f"{[[i['id'] for i in g] for g in sharing_groups(batch)]}"])
    both_running = {"B": threading.Event(), "F": threading.Event()}
    many_fail_calls, many_fail_lock = [], threading.Lock()

    def two_fail(it):
        with many_fail_lock:
            many_fail_calls.append(it["id"])
        if it["id"] in both_running:  # B and F each fail only once the other runs: both failures are made
            both_running[it["id"]].set()
            both_running["F" if it["id"] == "B" else "B"].wait(timeout=30)
            raise ValueError(f"{it['id']} failed")
    try:
        run_items("development", batch, two_fail, jobs=4)
        many_fail = "ran through"
    except Refused as exc:
        many_fail = str(exc)
    expect("jobs: under development four at a time the earliest failure in items order is named",
           [many_fail] if isinstance(many_fail, str) else [f"{many_fail}"], "ITEM_FAILED B (development): ValueError: B failed")
    expect("jobs: and nothing of the failing sequence runs after its failure",
           [] if "C" not in many_fail_calls and "D" not in many_fail_calls and "X" not in many_fail_calls
           else [f"calls {many_fail_calls}"])
    widest, in_flight, flight_lock, thirteen = [0], [0], threading.Lock(), []
    gate_12, gate_13 = threading.Barrier(12), threading.Barrier(13)

    def flying(it):
        with flight_lock:
            in_flight[0] += 1
            widest[0] = max(widest[0], in_flight[0])
        try:
            if int(it["id"][1:]) < 13:  # thirteen at once would meet here; twelve workers wait it out and it breaks
                try:
                    gate_13.wait(timeout=2)
                    thirteen.append(it["id"])
                except threading.BrokenBarrierError:
                    pass
            if int(it["id"][1:]) < 12:  # the first twelve meet: only twelve running at once can pass
                gate_12.wait(timeout=30)
        finally:
            with flight_lock:
                in_flight[0] -= 1
    try:
        flown = run_items("production", [item(f"i{n}") for n in range(30)], flying, jobs=12)
    except Refused as exc:
        flown = {"done": [], "quarantined": [], "refused": str(exc)}
    expect("jobs: twelve at a time runs twelve independent items at once and never a thirteenth",
           [] if widest[0] == 12 and not thirteen and len(flown["done"]) == 30 and not flown["quarantined"]
           else [f"widest {widest[0]}, thirteen met {thirteen}, {flown}"])
    stopped, q1_running, ran_after = threading.Event(), threading.Event(), []

    def failing_first(it):
        if it["id"] == "P":
            q1_running.wait(timeout=30)  # P fails while Q1 runs
            raise ValueError("P failed")
        if it["id"] == "Q1":
            q1_running.set()
            stopped.wait(timeout=30)  # Q1 outlasts the failure: run_items sets the stop when P fails
        ran_after.append(it["id"])
    try:
        run_items("development", [item("P", unit="UP"), item("Q1", unit="UQ"), item("Q2", unit="UQ")], failing_first,
                  jobs=2, stop=stopped)
        stop_message = "ran through"
    except Refused as exc:
        stop_message = str(exc)
    expect("jobs: under development a failure lets no item start after it, in any sequence",
           [] if stop_message.startswith("ITEM_FAILED P ") and stopped.is_set() and ran_after == ["Q1"]
           else [f"{stop_message} stopped={stopped.is_set()} ran {ran_after}"])
    for bad_jobs in (0, True, "2"):
        try:
            run_items("production", [item("A")], lambda it: None, jobs=bad_jobs)
            got_jobs = "ran"
        except Refused as exc:
            got_jobs = str(exc)
        expect(f"jobs: {bad_jobs!r} is refused", [got_jobs], "ITEMS_JOBS_INVALID")

    def interrupted(it):
        raise KeyboardInterrupt
    try:
        run_items("production", [item("A")], interrupted)
        failures.append("an interrupt was quarantined as an item failure")
    except KeyboardInterrupt:
        pass

    # a record ends at "\n" only; JSON allows U+2028 and U+2029 raw inside a string, and
    # str.splitlines() would cut there
    with tempfile.TemporaryDirectory() as td:
        held = {"seq": 0, "reason": "before\u2028between\u2029after"}
        amendments_path(td).write_text(json.dumps(held, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            got = read_log(td)
        except Refused as exc:
            got = str(exc)
        if got != [held]:
            failures.append(f"jsonl-line-separators-inside-a-string-read-whole (read_log): {got!r}")
        # a bare CR is JSON whitespace, which text-mode reading would turn into a line break; CRLF still ends a record
        later = {"seq": 1, "reason": "after a bare CR"}
        amendments_path(td).write_bytes(("{\r" + json.dumps(held)[1:] + "\r\n" + json.dumps(later) + "\n").encode("utf-8"))
        try:
            got = read_log(td)
        except Refused as exc:
            got = str(exc)
        if got != [held, later]:
            failures.append(f"jsonl-bare-cr-whitespace-and-crlf-read-whole (read_log): {got!r}")

    # stage records on real files under a scratch run directory
    with tempfile.TemporaryDirectory() as td:
        run_dir = pathlib.Path(td) / "r1"
        def by_hand(path, obj):
            """An edit made outside the driver: no lock, no binding, no confinement."""
            pathlib.Path(path).write_text(json_text(obj), encoding="utf-8")

        def declare_fixture(directory, run):
            """A declaration as `declare` leaves it: the seq-0 binding in the log, then run.json."""
            append_amendment(directory, {"seq": 0, "at": now(), "reason": "declaration", "scope": [],
                                         "invalidates": [], "diff": {}, "run_json_sha256": bound_digest(run)})
            write_json(directory, run_json_path(directory), run)

        def amend_fixture(directory, run, entry):
            """An amendment as `declare` leaves it: the log line binding the new run.json, then run.json."""
            append_amendment(directory, {**entry, "run_json_sha256": bound_digest(run)})
            write_json(directory, run_json_path(directory), run)

        base = {"declaration_seq": 0, "question": "fixture", "posture": "production"}
        declare_fixture(run_dir, base)

        def start(stage, inputs=(), part=None):
            try:
                with run_stage(run_dir, stage, inputs, part=part) as st:
                    (run_dir / f"{stage}.out").write_text(f"{stage} output\n", encoding="utf-8")
                    st.output(f"{stage}.out")
                return []
            except Refused as exc:
                return str(exc).splitlines()
            except stagelock.Locked:
                raise
            except Exception as exc:  # a reverted check fails by its control's name, not by a traceback
                return [f"RAISED {exc!r}"]

        def part_run_elsewhere(directory):
            """A part named for a stage that declares none: refused by name."""
            try:
                with run_stage(directory, "S1", part="views"):
                    pass
                return []
            except Refused as exc:
                return str(exc).splitlines()

        def start_in(other_dir, stage="S1", inputs=()):
            try:
                with run_stage(other_dir, stage, inputs):
                    pass
                return []
            except Refused as exc:
                return str(exc).splitlines()
            except Exception as exc:
                return [f"RAISED {exc!r}"]

        def produce(stage, status="complete"):
            with run_stage(run_dir, stage) as st:
                (run_dir / f"{stage}.out").write_text(f"{stage} output\n", encoding="utf-8")
                st.output(f"{stage}.out")
                st.record["status"] = status
            return read_json(record_path(run_dir, stage))

        first = produce("S1")
        expect("stage record fields", [k for k in ("stage", "run_json_sha256", "declaration_seq", "started", "ended",
                                                    "status", "inputs", "outputs", "calls", "quarantined", "usage")
                                       if k not in first])
        if first["status"] != "complete" or first["run_json_sha256"] != sha256_file(run_json_path(run_dir)):
            failures.append(f"S1 record does not pin the declaration it read: {first}")
        expect("complete input accepted", start("S3", [{"artifact": "S1.out", "producer_stage": "S1"}]))
        # Guard the subject: when the run above was refused there is no record to read, and the
        # control that named the refusal has already fired.
        pinned = (read_json(record_path(run_dir, "S3")).get("inputs")
                  if record_path(run_dir, "S3").is_file() else "no S3 record was written")
        if pinned != [{"artifact": "S1.out", "sha256": sha256_file(run_dir / "S1.out"),
                       "producer_stage": "S1", "producer_seq": 0}]:
            failures.append(f"S3 record does not pin its input: {pinned}")
        produce("S4", status="partial")
        expect("partial input is refused under the production posture", start("S5", [{"artifact": "S4.out", "producer_stage": "S4"}]), "INPUT_PARTIAL S4")
        expect("no producer record", start("S7", [{"artifact": "S6.out", "producer_stage": "S6"}]), "INPUT_INVALID S6")
        (run_dir / "S1.out").write_text("tampered\n", encoding="utf-8")
        expect("input changed since its producer recorded it",
               start("S3", [{"artifact": "S1.out", "producer_stage": "S1"}]), "INPUT_INVALID S1")
        (run_dir / "S1.out").write_text("S1 output\n", encoding="utf-8")
        try:
            with run_stage(run_dir, "S6"):
                raise RuntimeError("stage failed")
        except RuntimeError:
            pass
        if read_json(record_path(run_dir, "S6"))["status"] != "failed":
            failures.append("a stage that raised was not recorded failed")
        expect("failed input", start("S8", [{"artifact": "S6.out", "producer_stage": "S6"}]), "INPUT_INVALID S6")
        expect("unknown stage", start("S0"), "STAGE_UNKNOWN S0")
        # W review of WP-09 r1, F2 (lead decision): a producer's own inputs are held to what the consumer admits
        prov = pathlib.Path(td) / "prov"
        declare_fixture(prov, base)

        def made(stage, inputs, text):
            with run_stage(prov, stage, inputs) as st:
                (prov / f"{stage}.out").write_text(text, encoding="utf-8")
                st.output(f"{stage}.out")
        both = [{"artifact": "S3.out", "producer_stage": "S3"}, {"artifact": "S1.out", "producer_stage": "S1"}]
        made("S1", [], "census as S3 read it\n")
        made("S3", [{"artifact": "S1.out", "producer_stage": "S1"}], "results over that census\n")
        expect("a consumer admitting what its producer read is admitted", start_in(prov, "S4", both))
        made("S1", [], "census made again at the same sequence\n")
        expect("a producer run again at the same sequence under its consumer's other input is INPUT_STALE",
               start_in(prov, "S4", both), "INPUT_STALE S3: it read S1.out")
        expect("an input whose producer read nothing the consumer admits is held to its own record alone",
               start_in(prov, "S4", [{"artifact": "S3.out", "producer_stage": "S3"}]))
        # a declaration edited outside `declare`: same sequence, different bytes
        by_hand(run_json_path(run_dir), {**base, "question": "edited by hand"})
        expect("run.json edited without an amendment", start("S9"), "DECLARATION_DRIFT S9")
        by_hand(run_json_path(run_dir), base)
        expect("restored declaration", start("S9"))
        # a sequence that outran the amendment log
        by_hand(run_json_path(run_dir), {**base, "declaration_seq": 1})
        expect("declaration_seq ahead of the declaration log", start("S9b"), "DECLARATION_DRIFT S9b",
               "but the declaration log ends at 0")
        amend_fixture(run_dir, {**base, "declaration_seq": 1}, amend(1, scope=("S10",)))
        expect("amendment licenses S10, producer S1 not invalidated",
               start("S10", [{"artifact": "S1.out", "producer_stage": "S1"}], part="parse"))
        # S10 has parts (STAGE_PARTS), so its pinned inputs are its part's
        held_s10 = read_json(record_path(run_dir, "S10")) if record_path(run_dir, "S10").is_file() else {}
        pinned_s10 = ((held_s10.get("parts") or {}).get("parse") or held_s10).get("inputs") or []
        if [row.get("producer_seq") for row in pinned_s10] != [0]:
            failures.append(f"S10 pinned its producer's sequence as its own: {pinned_s10}")
        # S10b has parts too (STAGE_PARTS), so the start names one; the declaration is judged before the part is
        expect("amendment does not list S10b",
               start("S10b", [{"artifact": "S1.out", "producer_stage": "S1"}], part="build"), "DECLARATION_DRIFT S10b")
        # a log that is not a numbered sequence, or not readable, is named
        good_log = amendments_path(run_dir).read_text(encoding="utf-8")
        amendments_path(run_dir).write_text(good_log.splitlines()[0] + "\n" + json.dumps(amend(2)) + "\n", encoding="utf-8")
        expect("declaration log skips a number", start("S12"), "DECLARATION_DRIFT S12", "not numbered 0..1")
        amendments_path(run_dir).write_text("", encoding="utf-8")
        expect("declaration log without a seq-0 entry", start("S12"), "DECLARATION_DRIFT S12", "no declaration is bound")
        amendments_path(run_dir).write_text("{not json\n", encoding="utf-8")
        try:
            read_amendments(run_dir)
            failures.append("an unreadable amendment log was read")
        except Refused as exc:
            expect("unreadable amendment log", [str(exc)], "RECORD_UNREADABLE")
        expect("no declaration at all", start_in(pathlib.Path(td) / "r2"), "RUN_UNDECLARED")
        amendments_path(run_dir).write_text(good_log, encoding="utf-8")
        # a held stage lock refuses a second runner by name
        with stagelock.hold(run_dir, "stage-S12"):
            try:
                start("S12")
                failures.append("a stage started while its lock was held")
            except stagelock.Locked as exc:
                expect("held stage lock", [str(exc)], "STAGE_LOCKED stage-S12")
        # a declaration being written holds a stage back: it neither reads nor pins half an amendment
        with stagelock.hold(run_dir, "declaration"):
            try:
                start("S12")
                failures.append("a stage started while the declaration lock was held")
            except stagelock.Locked as exc:
                expect("held declaration lock", [str(exc)], "STAGE_LOCKED declaration")
        # an unreadable record is named, not skipped
        record_path(run_dir, "S12").parent.mkdir(parents=True)
        record_path(run_dir, "S12").write_text("{not json", encoding="utf-8")
        try:
            stage_records(run_dir)
            failures.append("an unreadable stage record was skipped")
        except Refused as exc:
            expect("unreadable record", [str(exc)], "RECORD_UNREADABLE")

        # a rerun checks the stage's own previous pin before it replaces the record
        again = pathlib.Path(td) / "r5"
        declare_fixture(again, base)
        expect("first run of the only stage", start_in(again, "S1"))
        expect("rerun under the unchanged declaration", start_in(again, "S1"))
        by_hand(run_json_path(again), {**base, "question": "edited by hand"})
        pin = record_path(again, "S1").read_bytes()
        expect("the only recorded stage rerun after an unamended edit", start_in(again, "S1"), "DECLARATION_DRIFT S1")
        if record_path(again, "S1").read_bytes() != pin:
            failures.append("the refused rerun overwrote the pin it was checked against")

        # a declaration seq is bound to the run.json authorized at it, not to what a stage happened to read
        def amended_run(name):
            directory = pathlib.Path(td) / name
            declare_fixture(directory, {**base, "checks": {"view_complete_share_min": 0.9}})
            with run_stage(directory, "S3") as stage_run:
                (directory / "S3.out").write_text("S3 output\n", encoding="utf-8")
                stage_run.output("S3.out")
            amend_fixture(directory, {**base, "checks": {"view_complete_share_min": 0.9}, "declaration_seq": 1,
                                      "budget": {"reserve": 0.2}}, amend(1, scope=("S4",)))  # a budget amendment: nobody invalidated
            return directory

        consume_s3 = [{"artifact": "S3.out", "producer_stage": "S3"}]
        clean = amended_run("r7")
        expect("a clean amended run lets the next stage consume across the amendment",
               start_in(clean, "S4", consume_s3))
        edited = amended_run("r8")
        run_before, s3_before = run_json_path(edited).read_bytes(), record_path(edited, "S3").read_bytes()
        hand_edited = read_json(run_json_path(edited))
        hand_edited["checks"]["view_complete_share_min"] = 0.5  # the criteria, by hand; the seq stays 1
        by_hand(run_json_path(edited), hand_edited)
        expect("a hand edit of checks before any stage at the new seq", start_in(edited, "S4", consume_s3),
               "DECLARATION_DRIFT S4: run.json is not the declaration authorized at seq 1")
        if record_path(edited, "S4").exists() or record_path(edited, "S3").read_bytes() != s3_before:
            failures.append("the refused stage start wrote or overwrote a record")
        run_json_path(edited).write_bytes(run_before)
        expect("the authorized run.json lets the stage start again", start_in(edited, "S4", consume_s3))

        # the run directory is a boundary: an artifact outside it is refused for that reason alone,
        # every one of them existing and matching the hash its producer recorded
        bound = pathlib.Path(td) / "r6"
        declare_fixture(bound, base)
        outside = pathlib.Path(td) / "outside.out"
        outside.write_text("outside\n", encoding="utf-8")
        (bound / "sub").mkdir(parents=True)
        (bound / "sub" / "ok.out").write_text("inside\n", encoding="utf-8")
        (bound / "sub" / "link.out").symlink_to(outside)
        expect("first run of the producer", start_in(bound, "S1"))
        producer = read_json(record_path(bound, "S1"))
        listed = {"sub/ok.out": sha256_file(bound / "sub" / "ok.out"), "sub/gone.out": sha256_bytes(b"gone"),
                  "../outside.out": sha256_file(outside), str(outside): sha256_file(outside),
                  "sub/link.out": sha256_file(outside)}
        producer["outputs"] = [{"artifact": name, "sha256": digest} for name, digest in listed.items()]
        by_hand(record_path(bound, "S1"), producer)

        def consume(name):
            return start_in(bound, "S3", [{"artifact": name, "producer_stage": "S1"}])

        expect("a contained artifact is accepted", consume("sub/ok.out"))  # the positive case, before any escape
        expect("a contained artifact that is not a file", consume("sub/gone.out"), "INPUT_INVALID S1: sub/gone.out is not a file")
        for escape in ("../outside.out", str(outside), "sub/link.out"):
            lines = consume(escape)
            expect(f"artifact {escape} leaves the run directory", lines, f"INPUT_INVALID S1: {escape} leaves the run directory")
            if len(lines) != 1:
                failures.append(f"artifact {escape}: containment was not the only violation: {lines}")
        with run_stage(bound, "S3") as stage_run:
            stage_run.output("sub/ok.out")
        for escape in ("../outside.out", "sub/link.out"):
            try:
                with run_stage(bound, "S4") as stage_run:
                    stage_run.output(escape)
                failures.append(f"output {escape} outside the run directory was recorded")
            except Refused as exc:
                expect(f"output {escape} leaves the run directory", [str(exc)], f"OUTPUT_OUTSIDE_RUN {escape}")
            except Exception as exc:
                failures.append(f"output {escape} outside the run directory raised {exc!r} instead of being refused")

        # the failure posture inside a stage: production lists the quarantine and completes, development stops
        def fail_b(it):
            if it["id"] == "B":
                raise ValueError("B failed")

        for posture in ("production", "development"):
            posted = pathlib.Path(td) / f"items-{posture}"
            declare_fixture(posted, {**base, "posture": posture})
            try:
                with run_stage(posted, "S3") as stage_run:
                    stage_run.run_items(batch, fail_b)
                outcome = "completed"
            except Refused as exc:
                outcome = str(exc)
            recorded = read_json(record_path(posted, "S3"))
            if posture == "production":
                expect("stage in production: the quarantine is listed in the record and the stage completes",
                       [] if outcome == "completed" and recorded["status"] == "complete"
                       and sorted(q["id"] for q in recorded["quarantined"]) == ["A", "B", "C", "D"]
                       else [f"{outcome} {recorded['status']} {recorded['quarantined']}"])
            else:
                expect("stage in development: the first failing item stops the stage by name",
                       [outcome], "ITEM_FAILED B (development)")
                expect("stage in development: the record says failed and lists no quarantine",
                       [] if recorded["status"] == "failed" and recorded["quarantined"] == [] else [f"{recorded}"])

        # a symlink inside the run directory cannot redirect a metadata write out of it: a clean run
        # first, then each internal link, each pointing at a fixture-owned target that must stay as it was
        def escape(action, *args):
            try:
                action(*args)
                return []
            except stagelock.Escaped as exc:
                return [str(exc)]
            except Exception as exc:
                return [f"RAISED {exc!r}"]

        def under_run(directory, stage):
            with run_stage(directory, stage):
                pass

        def link_run(name):
            directory, target = pathlib.Path(td) / name, pathlib.Path(td) / f"{name}-external"
            target.mkdir()
            declare_fixture(directory, base)
            return directory, target

        clean_dir, clean_target = link_run("r9")
        expect("a clean run writes its log, locks and stage records", escape(under_run, clean_dir, "S1"))
        if record_path(clean_dir, "S1").is_file() is not True or list(clean_target.iterdir()):
            failures.append("the clean run did not write its record inside the run directory")

        dangling, target = link_run("r10")
        (dangling / "stages").mkdir(exist_ok=True)
        amendments_path(dangling).unlink()
        amendments_path(dangling).symlink_to(target / "log.jsonl")  # dangling: nothing is there yet
        expect("a dangling amendments.jsonl", escape(append_amendment, dangling, {"seq": 1}), "RUN_PATH_ESCAPE")
        if list(target.iterdir()):
            failures.append(f"a dangling amendments.jsonl was created through: {list(target.iterdir())}")

        kept, target = link_run("r11")
        external_log = json.dumps({"seq": 0, "run_json_sha256": "outside"}) + "\n"  # a log someone else owns
        (target / "log.jsonl").write_text(external_log, encoding="utf-8")
        amendments_path(kept).unlink()
        amendments_path(kept).symlink_to(target / "log.jsonl")
        expect("an amendments.jsonl linked to an existing external file", escape(append_amendment, kept, {"seq": 1}),
               "RUN_PATH_ESCAPE")
        expect("the declaration log rebound through a link", escape(rebind, kept, "0" * 64), "RUN_PATH_ESCAPE")
        if (target / "log.jsonl").read_text(encoding="utf-8") != external_log or [p.name for p in target.iterdir()] != ["log.jsonl"]:
            failures.append("an external file behind amendments.jsonl was changed")

        # The swap AFTER confinement: `confine` is made to answer as it would have before a directory on the
        # way became a link, and the write must still not leave the run (`stagelock.beneath`).
        swapped, target = link_run("r12b")
        (swapped / "apply").symlink_to(target)
        real_confine = stagelock.confine
        stagelock.confine = lambda run, destination: pathlib.Path(run).resolve() / pathlib.Path(
            destination).relative_to(run)
        try:
            expect("a directory swapped for a link after the path was confined",
                   escape(write_text, swapped, swapped / "apply" / "plan.json", "x"), "RUN_PATH_ESCAPE")
        finally:
            stagelock.confine = real_confine
        if list(target.iterdir()):
            failures.append(f"a record was written through a directory swapped for a link: {list(target.iterdir())}")

        locks, target = link_run("r12")
        (locks / "locks").symlink_to(target)
        expect("a symlinked locks directory", escape(under_run, locks, "S1"), "RUN_PATH_ESCAPE")
        if list(target.iterdir()):
            failures.append(f"a lock was created through a symlinked locks directory: {list(target.iterdir())}")

        parent, target = link_run("r13")
        (parent / "stages").mkdir()
        (parent / "stages" / "S1").symlink_to(target)
        expect("a symlinked stages/<stage> parent", escape(under_run, parent, "S1"), "RUN_PATH_ESCAPE")
        if list(target.iterdir()):
            failures.append(f"a stage record was written through a symlinked stage directory: {list(target.iterdir())}")

        stages, target = link_run("r14")
        (stages / "stages").symlink_to(target)
        expect("a symlinked stages directory", escape(under_run, stages, "S1"), "RUN_PATH_ESCAPE")
        if list(target.iterdir()):
            failures.append(f"a stage record was written through a symlinked stages directory: {list(target.iterdir())}")

        # ---- a stage with several producers: one record, one lock, one part each
        parts_dir = pathlib.Path(td) / "parts"
        declare_fixture(parts_dir, base)

        def part_run(label, artifact, status="complete", raising=False, body=None):
            try:
                with run_stage(parts_dir, "S2", part=label) as st:
                    (parts_dir / artifact).write_text(body or f"{label} output\n", encoding="utf-8")
                    st.output(artifact)
                    st.record["status"] = status
                    if raising:
                        raise RuntimeError(f"{label} failed")
            except RuntimeError:
                pass
            except Refused as exc:
                return str(exc).splitlines()
            return []

        expect("the first part of a stage runs", part_run("views", "views.json"))
        expect("the second part runs beside it", part_run("inventory", "inventory.json"))
        both = read_json(record_path(parts_dir, "S2"))
        if sorted(both.get("parts", {})) != ["inventory", "views"]:
            failures.append(f"the second part clobbered the first: {sorted(both.get('parts', {}))}")
        both.setdefault("parts", {}).setdefault("views", {"outputs": [], "started": None})
        both["parts"].setdefault("inventory", {"outputs": [], "started": None})
        if [o["artifact"] for o in both["parts"]["views"].get("outputs", [])] != ["views.json"]:
            failures.append(f"the views part lost its own outputs: {sorted(both['parts']['views'])}")
        if both.get("status") != "complete":
            failures.append(f"a stage whose every part is complete is not complete: {both.get('status')}")
        started = both["parts"]["views"].get("started")
        expect("a part reruns", part_run("inventory", "inventory.json", body="a second inventory\n"))
        again = read_json(record_path(parts_dir, "S2"))
        again_parts = again.get("parts", {})
        if again_parts.get("views") != both["parts"]["views"] or again_parts.get("views", {}).get("started") != started:
            failures.append("rerunning one part rewrote the other part's entry")
        if again_parts.get("inventory", {}).get("outputs") == both["parts"]["inventory"].get("outputs"):
            failures.append("rerunning a part did not replace its own entry")
        part_run("inventory", "inventory.json", raising=True)
        derived = read_json(record_path(parts_dir, "S2"))
        if derived.get("status") != "failed" or derived.get("parts", {}).get("views", {}).get("status") != "complete":
            failures.append(f"the stage status is not derived from its parts: {derived.get('status')} "
                            f"/ {derived.get('parts', {}).get('views', {}).get('status')}")
        expect("a downstream input is admitted by the part that produced it",
               start_in(parts_dir, "S3", [{"artifact": "views.json", "producer_stage": "S2"}]))
        expect("an artifact no part of the stage produced",
               start_in(parts_dir, "S4", [{"artifact": "nobody.json", "producer_stage": "S2"}]),
               "INPUT_INVALID S2", "no part of its record produced")
        expect("a downstream input whose producing part failed",
               start_in(parts_dir, "S5", [{"artifact": "inventory.json", "producer_stage": "S2"}]),
               "INPUT_INVALID S2.inventory")
        part_run("views", "views.json", status="partial")
        expect("a downstream input whose producing part is partial",
               start_in(parts_dir, "S6", [{"artifact": "views.json", "producer_stage": "S2"}]),
               "INPUT_PARTIAL S2.views")
        expect("a part the stage does not declare", part_run("census", "census.json"),
               "STAGE_PART_UNKNOWN S2.census")
        expect("a writer that names no part of a stage that has them",
               start_in(parts_dir, "S2", []), "STAGE_PART_REQUIRED S2")
        # the same refusal before any part has run: a fresh part-less write is the same violation
        fresh_dir = pathlib.Path(td) / "fresh-parts"
        declare_fixture(fresh_dir, base)
        expect("a part-less writer to a stage with parts, before any part has run",
               start_in(fresh_dir, "S2", []), "STAGE_PART_REQUIRED S2")
        if record_path(fresh_dir, "S2").is_file():
            failures.append("a refused part-less write still left an S2 record")
        # The second half of the same rule, and the one `STAGE_PARTS` does not reach: a stage this
        # version declares NO parts for, whose record on disk nevertheless holds some — an older
        # run's, or a later version's. A part-less write there would replace every part's entry at
        # once, so it is refused by what the record HOLDS rather than by the table. This was a
        # control-audit survivor: removing the refusal left every suite green.
        held_dir = pathlib.Path(td) / "parts-held-by-record"
        declare_fixture(held_dir, base)
        held_record = {"stage": "S3", "status": "complete", "declaration_seq": 1,
                       "parts": {"a-producer": {"stage": "S3", "status": "complete", "outputs": []}}}
        write_json(held_dir, record_path(held_dir, "S3"), held_record)
        expect("a part-less writer to a stage whose record already holds parts",
               start_in(held_dir, "S3", []), "STAGE_PART_REQUIRED S3", "already holds the parts")
        if read_json(record_path(held_dir, "S3")) != held_record:
            failures.append("the refused part-less write replaced the parts the record held")
        if "S3" in STAGE_PARTS:
            failures.append("S3 has declared parts, so this control is the table's refusal again")
        # An optional part counts toward the stage's status only when it is there.
        done = {"status": "complete"}
        got = [derived_status({"stage": "S11", "parts": {"plan": done, "effects": done}}),
               derived_status({"stage": "S11", "parts": {"plan": done}}),
               derived_status({"stage": "S11", "parts": {"plan": done, "effects": done,
                                                         "destinations": {"status": "failed"}}}),
               "destinations" in parts_of("S11"), "destinations" in STAGE_PARTS["S11"]]
        if got != ["complete", "partial", "failed", True, False]:
            failures.append(f"an optional part: absent it must not hold the stage partial, present it counts: {got}")
        # a legacy record whose outputs identify no part: refused, not silently replaced
        ambiguous_dir = pathlib.Path(td) / "ambiguous-legacy"
        declare_fixture(ambiguous_dir, base)
        write_json(ambiguous_dir, record_path(ambiguous_dir, "S2"),
                   {"stage": "S2", "status": "failed", "outputs": [], "declaration_seq": 1})
        def legacy_ambiguous():
            try:
                with run_stage(ambiguous_dir, "S2", part="inventory"):
                    pass
                return []
            except Refused as exc:
                return str(exc).splitlines()
            except Exception as exc:
                return [f"RAISED {exc!r}"]

        expect("a legacy record whose outputs identify no producer", legacy_ambiguous(),
               "STAGE_PART_AMBIGUOUS S2")
        if read_json(record_path(ambiguous_dir, "S2")).get("status") != "failed":
            failures.append("the ambiguous legacy record was overwritten after all")
        # a record written before the stage had parts keeps its producer when a part is added
        legacy_dir = pathlib.Path(td) / "legacy"
        declare_fixture(legacy_dir, base)
        # Built directly, not through the writer API: the writer now refuses a part-less write to a
        # stage with parts, so a fixture made with it would be a record this version can produce
        # rather than the one an older version left behind (GC#9).
        (legacy_dir / "views.json").write_text("the legacy views output\n", encoding="utf-8")
        write_json(legacy_dir, record_path(legacy_dir, "S2"), {
            "stage": "S2", "run_json_sha256": sha256_file(legacy_dir / "run.json"),
            "declaration_seq": read_json(legacy_dir / "run.json")["declaration_seq"],
            "started": now(), "ended": now(), "status": "complete", "inputs": [],
            "outputs": [{"artifact": "views.json", "sha256": sha256_file(legacy_dir / "views.json")}],
            "calls": [], "quarantined": [],
            "usage": {"measured": 0, "provisional": 0, "unresolved": 0, "complete": True}})
        with run_stage(legacy_dir, "S2", part="inventory") as st:
            (legacy_dir / "inventory.json").write_text("the inventory output\n", encoding="utf-8")
            st.output("inventory.json")
        moved = read_json(record_path(legacy_dir, "S2"))
        if sorted(moved.get("parts", {})) != ["inventory", "views"]:
            failures.append(f"adding a part discarded the legacy producer: {sorted(moved.get('parts', {}))}")
        kept_label, kept_entry = producing_part(moved, "views.json")
        if kept_label != "views" or not kept_entry:
            failures.append(f"the legacy producer's artifact lost its producing part: {kept_label}")
        expect("a downstream input on the artifact the legacy producer made",
               start_in(legacy_dir, "S3", [{"artifact": "views.json", "producer_stage": "S2"}]))
        expect("a stage that declares no parts refuses one",
               part_run_elsewhere(parts_dir), "STAGE_PART_UNKNOWN S1.views")
        # the record written before parts existed still reads, and is still its own producer
        legacy = read_json(record_path(run_dir, "S1"))
        if "parts" in legacy or derived_status(legacy) != legacy.get("status"):
            failures.append(f"a single-producer record did not keep its shape: {sorted(legacy)}")
        try:
            label, entry = producing_part(legacy, "S1.out")
        except Exception as exc:  # the control names the rule, not a traceback
            label, entry = f"RAISED {exc!r}", None
        if label != "S1" or entry is not legacy:
            failures.append(f"a record written before parts existed no longer answers for its own output: {label}")

        # ---- GC#6: every stage-record publication crosses the disclosure boundary FIRST, and the
        # controls observe the real writer — `run_stage`'s own two writes — rather than a helper.
        home = str(pathlib.Path.home())
        secret_path = f"{home}/Documents/not-a-real-file"

        def published(directory, stage, body, part=None):
            """What `run_stage` left on disk, and what it raised: the writer itself, not a filter."""
            try:
                with run_stage(directory, stage, part=part) as stage_run:
                    body(stage_run)
                raised = ""
            except Refused as exc:
                raised = str(exc)
            except Exception as exc:
                raised = f"RAISED {exc!r}"
            path = record_path(directory, stage)
            return raised, (path.read_text(encoding="utf-8") if path.is_file() else "")

        # (1) a failure record: an item's quarantine reason is an exception message, and an OSError's
        # message IS a path. The record is published, and what it publishes is the projection.
        failing_dir = pathlib.Path(td) / "disclose-items"
        declare_fixture(failing_dir, base)

        def fail_with_path(item):
            if item["id"] == "B":
                raise OSError(f"cannot read {secret_path}")
        raised, text = published(failing_dir, "S3", lambda st: st.run_items(batch, fail_with_path))
        if secret_path in text or home in text:
            failures.append(f"a quarantine reason published the owner's home path: {raised} {text[:200]}")
        if "<HOME>" not in text or '"quarantined"' not in text:
            failures.append(f"the failure record was not published with the reason projected: {raised} {text[:200]}")

        # (2) a preserved part: the record already on disk is carried into `parts` by the FIRST
        # (running) publication, so the boundary has to be crossed there and not after the stage.
        kept_dir = pathlib.Path(td) / "disclose-preserved"
        declare_fixture(kept_dir, base)
        (kept_dir / "views.json").write_text("the legacy views output\n", encoding="utf-8")
        planted = {"stage": "S2", "run_json_sha256": sha256_file(kept_dir / "run.json"),
                   "declaration_seq": read_json(kept_dir / "run.json")["declaration_seq"],
                   "started": now(), "ended": now(), "status": "complete", "inputs": [],
                   "outputs": [{"artifact": "views.json", "sha256": sha256_file(kept_dir / "views.json")}],
                   "calls": [{"api_key": "shortpass"}], "quarantined": [],
                   "usage": {"measured": 0, "provisional": 0, "unresolved": 0, "complete": True}}
        write_json(kept_dir, record_path(kept_dir, "S2"), planted)
        before = record_path(kept_dir, "S2").read_text(encoding="utf-8")
        raised, text = published(kept_dir, "S2", lambda st: None, part="inventory")
        expect("a preserved part carrying a credential is refused before the record is published",
               [raised], "RECORD_DISCLOSES S2", "a credential-named member")
        if text != before:
            failures.append("the refused publication replaced the record anyway")
        if "shortpass" in raised:
            failures.append(f"the refusal repeated the credential it objected to: {raised}")

        # (3) the final publication: a stage that puts a raw path in its own record is refused there,
        # and the refusal carries the stage's own failure when one was already in flight.
        late_dir = pathlib.Path(td) / "disclose-final"
        declare_fixture(late_dir, base)

        def leak_late(stage_run):
            stage_run.record["calls"].append({"note": secret_path})
        raised, text = published(late_dir, "S3", leak_late)
        expect("a stage record that would publish a raw path is refused at its final publication",
               [raised], "RECORD_DISCLOSES S3", "the string discloses a home path")
        if secret_path in text:
            failures.append(f"the refused final publication wrote the path anyway: {text[:200]}")

        def leak_and_fail(stage_run):
            stage_run.record["calls"].append({"note": secret_path})
            raise ValueError("the stage itself failed")
        both_dir = pathlib.Path(td) / "disclose-final-failing"
        declare_fixture(both_dir, base)
        raised, _text = published(both_dir, "S3", leak_and_fail)
        expect("a refusal in the finally names the failure that was already in flight",
               [raised], "RECORD_DISCLOSES S3", "ValueError", "was in flight")

    # The structural guard (X review of WP-08 r2): outside the listed sites nothing reads run.json. Positive control first,
    # on the real tree: every site is listed and every listed site still reads the declaration.
    texts = declaration_texts()
    found, sites = declaration_reads(texts)
    expect("the real tree reads the declaration only where DECLARATION_READERS says why", found)
    if sites != set(DECLARATION_READERS) or not {"distill.py", "census.py", "runlib/records.py"} <= set(texts):
        failures.append(f"the guard judged {len(texts)} modules and {sorted(sites)} sites, not every module of "
                        "session-distill and every listed site")

    def planted(rel, function, line):
        """`texts` with `line` as the first statement of `function` in `rel`: a read before the stage's admission."""
        import ast
        node = next(n for n in ast.parse(texts[rel]).body if isinstance(n, ast.FunctionDef) and n.name == function)
        lines = texts[rel].splitlines(keepends=True)
        at = node.body[0].lineno - 1
        return {**texts, rel: "".join(lines[:at] + [" " * node.body[0].col_offset + line + "\n"] + lines[at:])}

    for label, plant, code in (
            ("S2 reading the declaration before its admission",
             planted("runlib/views.py", "run", "early = records.read_json(records.run_json_path(run_dir))"),
             "DECLARATION_READ_UNLISTED runlib/views.py:"),
            ("S3 spelling the declaration's file itself",
             planted("runlib/stage_read.py", "run", 'early = json.loads((run_dir / "run.json").read_text())'),
             "DECLARATION_READ_UNLISTED runlib/stage_read.py:"),
            ("S2 reading the declaration's state under another name",
             {**planted("runlib/views.py", "run", "early = state_of(run_dir)"),
              "runlib/views.py": "from runlib.records import declaration_state as state_of\n"
              + planted("runlib/views.py", "run", "early = state_of(run_dir)")["runlib/views.py"]},
             "DECLARATION_READ_UNLISTED runlib/views.py:")):
        found_here = declaration_reads(plant)[0]
        expect(f"{label} is named", found_here, code, "(run)")
    unlisted = {key: why for key, why in DECLARATION_READERS.items() if key != ("runlib/census.py", "run")}
    expect("S1's pre-admission read with its entry removed is named", declaration_reads(texts, unlisted)[0],
           "DECLARATION_READ_UNLISTED runlib/census.py:", "(run)")
    expect("an entry whose site no longer reads the declaration is named",
           declaration_reads(texts, {**DECLARATION_READERS, ("runlib/views.py", "run"): "fixture"})[0],
           "DECLARATION_READ_STALE runlib/views.py (run)")
    with tempfile.TemporaryDirectory() as td:
        moved = declaration_texts(td)
        expect("a scan that found no module is not clean", declaration_reads(moved, {})[0], "DECLARATION_READ_UNSCANNED: 0 modules")
    expect("a scan that found no site is not clean", declaration_reads({"runlib/views.py": "def run():\n    pass\n"}, {})[0],
           "DECLARATION_READ_UNSCANNED: 1 modules scanned and 0 sites")

    # the fixture tree has one locator (lead, after lane L's measurement of the shipped tree): every suite that reads
    # fixtures asks `fixture_root`, and a tree without fixtures/ ends each of them by name
    # over a fixture tree of its own, so this suite needs none of the checkout's fixtures
    expect("the locator is this checkout's fixtures/", [] if FIXTURE_ROOT == pathlib.Path(__file__).resolve().parents[1]
           / "fixtures" else [str(FIXTURE_ROOT)])
    held_locator = FIXTURE_ROOT
    with tempfile.TemporaryDirectory(prefix="records-fixtures-") as own:
        globals()["FIXTURE_ROOT"] = pathlib.Path(own) / "fixtures"
        try:
            (pathlib.Path(own) / "fixtures" / "replay").mkdir(parents=True)
            expect("the fixture root, and a directory inside it named by its parts",
                   [] if (fixture_root(), fixture_root("replay")) == (pathlib.Path(own) / "fixtures",
                                                                     pathlib.Path(own) / "fixtures" / "replay")
                   else ["moved"])
            try:
                absent = fixture_root("absent")
            except Refused as exc:
                absent = str(exc)
            expect("control: a fixture directory that is not there is refused by name", [str(absent)],
                   f"FIXTURES_ABSENT {pathlib.Path(own) / 'fixtures' / 'absent'}: this tree carries no fixtures/absent "
                   "directory")
        finally:
            globals()["FIXTURE_ROOT"] = held_locator
    import ast as _fx_ast

    def fixture_spellings(texts):
        """`FIXTURE_PATH_RECOMPUTED <file>:<line>` for every path built from a `"fixtures"` literal outside this
        module: the literal as an operand of `/`, or as an argument of `joinpath`."""
        out = []
        for rel, src in sorted(texts.items()):
            for node in _fx_ast.walk(_fx_ast.parse(src)):
                operands = ([node.left, node.right] if isinstance(node, _fx_ast.BinOp) and isinstance(node.op, _fx_ast.Div)
                            else list(node.args) if isinstance(node, _fx_ast.Call) and isinstance(node.func, _fx_ast.Attribute)
                            and node.func.attr == "joinpath" else [])
                if any(isinstance(o, _fx_ast.Constant) and o.value == "fixtures" for o in operands):
                    out.append(f"FIXTURE_PATH_RECOMPUTED {rel}:{node.lineno}: the fixture tree is located by records.fixture_root")
        return out
    runlib_texts = {f"runlib/{path.name}": path.read_text(encoding="utf-8")
                    for path in sorted(pathlib.Path(__file__).resolve().parent.glob("*.py")) if path.name != "records.py"}
    expect("no runlib module but this one builds the fixture tree's path", fixture_spellings(runlib_texts))
    expect("control: a module that recomputes it is named",
           fixture_spellings({**runlib_texts, "runlib/breaker.py": runlib_texts["runlib/breaker.py"]
                              + "\nREPLAY = pathlib.Path(__file__).resolve().parents[1] / \"fixtures\" / \"replay\"\n"}),
           "FIXTURE_PATH_RECOMPUTED runlib/breaker.py:")
    expect("the spelling scan read the modules it judges", [] if len(runlib_texts) > 5 else [sorted(runlib_texts)])
    # each suite entered in THIS process (a suite is never handed to a child: dispatch's DISPATCH_SELF_TEST_ARGV)
    # with the locator pointed at a directory that holds no fixtures/: it returns 1 and says FIXTURES_ABSENT by name,
    # and raises nothing - which is what its `__main__` turns into an exit without a traceback
    import io
    from runlib import breaker as _fx_breaker, dispatch as _fx_dispatch, gate as _fx_gate
    from runlib import monitor as _fx_monitor, views as _fx_views
    # the suites read the locator of the module they import, `runlib.records` - which is not this one when this file
    # runs as `__main__` - so that module's root is the one pointed away
    from runlib import records as _fx_records
    held_root = _fx_records.FIXTURE_ROOT
    with tempfile.TemporaryDirectory(prefix="records-nofix-") as nofix:
        _fx_records.FIXTURE_ROOT = pathlib.Path(nofix) / "fixtures"
        try:
            for name, suite in (("gate", _fx_gate.self_test), ("dispatch", _fx_dispatch.self_test),
                                ("views", _fx_views.self_test), ("breaker", _fx_breaker.self_test),
                                ("monitor", _fx_monitor.self_test)):
                said = io.StringIO()
                try:
                    with contextlib.redirect_stdout(said):
                        code = suite()
                except BaseException as exc:  # noqa: BLE001 - a suite that raises fails this control by name
                    code = f"raised {type(exc).__name__}: {str(exc)[:200]}"
                expect(f"control: {name}'s suite over a tree without fixtures/ ends with FIXTURES_ABSENT by name and "
                       "raises nothing", [] if code == 1 and said.getvalue().startswith(
                           f"{name} --self-test: FIXTURES_ABSENT {pathlib.Path(nofix) / 'fixtures'}") else
                       [f"{code!r} {said.getvalue()[-300:]!r}"])
        finally:
            _fx_records.FIXTURE_ROOT = held_root

    for failure in failures:
        print(f"records --self-test [FAIL] {failure}")
    if failures:
        return 1
    print("records --self-test: OK (declaration order: equal, amended, silently advanced, invalidated, "
          "unlicensed, reversed; set accounting; the failure posture over items; stage records pin the "
          "declaration, inputs and outputs, refuse partial, invalid, stale and drifted declarations and "
          "paths that leave the run directory; run.json is read only where DECLARATION_READERS says why)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: records.py --self-test")
    sys.exit(self_test())
