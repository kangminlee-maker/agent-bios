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
directory, through a symlink or otherwise), ITEM_FAILED, SET_MISMATCH. Predicates return their
violations as a list; the ones that guard starting a stage or running its items raise `Refused`.

  records.py --self-test
"""
import contextlib
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

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
STAGES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S7b", "S8", "S9", "S9b", "S10", "S10b", "S11", "S12")
# The stages whose one record holds more than one producer, and the parts each has. A stage absent
# here keeps the single-producer record shape exactly as it was, and its readers do not change: S2
# produces the reading views and the inventory of the library, which neither calls the other nor
# may overwrite the other's record (design §6.1, §6.3).
STAGE_PARTS = {"S2": ("views", "inventory")}
STATUSES = ("running", "complete", "partial", "failed")
OUTCOMES = ("retained", "merged", "rejected", "quarantined")  # design §3.2 item 5


class Refused(Exception):
    """A driver refusal; the message starts with the named code."""


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
    path = stagelock.confine(run_dir, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise


def write_json(run_dir, path, obj):
    write_text(run_dir, path, json_text(obj))


def read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused(f"RECORD_UNREADABLE {path}: {exc}") from exc


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


def run_items(posture, items, work):
    """Run `work(item)` over `items` under a failure posture (design §4).

    An item is `{id, unit, route, test_config}`; a key it does not have shares nothing. In
    `production` an item whose work raises is quarantined together with every other item that
    shares its unit, route or test configuration, those not yet run are skipped and those
    already done are moved to the quarantine, and the independent items continue. Under any
    other posture the first failure stops by name (ITEM_FAILED), and so does a missing posture.
    Returns `{done: [ids], quarantined: [{id, reason, because}]}`; `because` is the failing item
    that took the item with it, None for the failing item itself."""
    expect_set(item["id"] for item in items)
    done, quarantined = [], {}
    for item in items:
        if item["id"] in quarantined:
            continue
        try:
            work(item)
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            if posture != "production":
                raise Refused(f"ITEM_FAILED {item['id']} ({posture}): {reason}") from exc
            quarantined[item["id"]] = {"id": item["id"], "reason": reason, "because": None}
            for other in items:
                shared = [key for key in SHARED_KEYS
                          if item.get(key) is not None and item.get(key) == other.get(key)]
                if other["id"] != item["id"] and shared and other["id"] not in quarantined:
                    quarantined[other["id"]] = {"id": other["id"], "because": item["id"],
                                                "reason": f"shares {shared[0]} {item[shared[0]]!r} with {item['id']}, which failed"}
            done = [i for i in done if i not in quarantined]
        else:
            done.append(item["id"])
    return {"done": done, "quarantined": list(quarantined.values())}


class StageRun:
    """The record of a running stage; the stage adds its outputs, runs its items under the
    run's posture, and may mark itself partial."""

    def __init__(self, run_dir, record, posture):
        self.run_dir, self.record, self.posture = pathlib.Path(run_dir), record, posture

    def output(self, artifact):
        path = contained(self.run_dir, artifact)
        if path is None:
            raise Refused(f"OUTPUT_OUTSIDE_RUN {artifact}: leaves the run directory")
        self.record["outputs"].append({"artifact": artifact, "sha256": sha256_file(path)})

    def run_items(self, items, work):
        """`run_items` under this run's posture; the quarantined items are listed in the record."""
        result = run_items(self.posture, items, work)
        self.record["quarantined"].extend(result["quarantined"])
        return result


def _legacy_part(stage, record):
    """Which declared part a pre-parts record belongs to, from the artifacts it recorded.

    A record written before a stage had parts names no producer, but its outputs do: `views.json`
    was written by the views part and by nothing else. A record whose outputs match no part's
    artifacts keeps no part name, and the caller decides what to do with it."""
    produced = {row.get("artifact") for row in record.get("outputs") or []}
    for label in STAGE_PARTS.get(stage, ()):
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
    declared = STAGE_PARTS.get(record.get("stage"), ())
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
    if part is not None and part not in STAGE_PARTS.get(stage, ()):
        raise Refused(f"STAGE_PART_UNKNOWN {stage}.{part}: the parts of {stage} are "
                      f"{list(STAGE_PARTS.get(stage, ())) or 'none'}")
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
            write_json(run_dir, record_path(run_dir, stage), document)
        try:
            yield StageRun(run_dir, record, run.get("posture"))
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
            write_json(run_dir, record_path(run_dir, stage), document)


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

        def start(stage, inputs=()):
            try:
                with run_stage(run_dir, stage, inputs) as st:
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
               start("S10", [{"artifact": "S1.out", "producer_stage": "S1"}]))
        pinned_s10 = (read_json(record_path(run_dir, "S10")).get("inputs")
                      if record_path(run_dir, "S10").is_file() else [])
        if [row.get("producer_seq") for row in pinned_s10] != [0]:
            failures.append(f"S10 pinned its producer's sequence as its own: {pinned_s10}")
        expect("amendment does not list S10b",
               start("S10b", [{"artifact": "S1.out", "producer_stage": "S1"}]), "DECLARATION_DRIFT S10b")
        # a log that is not a numbered sequence, or not readable, is named
        good_log = amendments_path(run_dir).read_text(encoding="utf-8")
        amendments_path(run_dir).write_text(good_log.splitlines()[0] + "\n" + json.dumps(amend(2)) + "\n", encoding="utf-8")
        expect("declaration log skips a number", start("S11"), "DECLARATION_DRIFT S11", "not numbered 0..1")
        amendments_path(run_dir).write_text("", encoding="utf-8")
        expect("declaration log without a seq-0 entry", start("S11"), "DECLARATION_DRIFT S11", "no declaration is bound")
        amendments_path(run_dir).write_text("{not json\n", encoding="utf-8")
        try:
            read_amendments(run_dir)
            failures.append("an unreadable amendment log was read")
        except Refused as exc:
            expect("unreadable amendment log", [str(exc)], "RECORD_UNREADABLE")
        expect("no declaration at all", start_in(pathlib.Path(td) / "r2"), "RUN_UNDECLARED")
        amendments_path(run_dir).write_text(good_log, encoding="utf-8")
        # a held stage lock refuses a second runner by name
        with stagelock.hold(run_dir, "stage-S11"):
            try:
                start("S11")
                failures.append("a stage started while its lock was held")
            except stagelock.Locked as exc:
                expect("held stage lock", [str(exc)], "STAGE_LOCKED stage-S11")
        # a declaration being written holds a stage back: it neither reads nor pins half an amendment
        with stagelock.hold(run_dir, "declaration"):
            try:
                start("S11")
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

    for failure in failures:
        print(f"records --self-test [FAIL] {failure}")
    if failures:
        return 1
    print("records --self-test: OK (declaration order: equal, amended, silently advanced, invalidated, "
          "unlicensed, reversed; set accounting; the failure posture over items; stage records pin the "
          "declaration, inputs and outputs, refuse partial, invalid, stale and drifted declarations and "
          "paths that leave the run directory)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: records.py --self-test")
    sys.exit(self_test())
