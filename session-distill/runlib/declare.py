#!/usr/bin/env python3
"""S0: the run declaration (`run.json`) and its amendments (design §4.1, §13.2, §8.4).

`create` validates a declaration and writes `run.json` at `declaration_seq` 0. Until a stage
has recorded that it read it, `set_fields` edits it in place; from then on a change is an
amendment (`amend`): one line in `amendments.jsonl`, `declaration_seq` advanced, and the
stages whose results it makes stale listed in `invalidates[]`. Changing `checks{}` after a
stage record exists invalidates S3 and everything downstream; changing `output_caps{}` after
one invalidates S2 and everything downstream, because S2 cut the windows against that cap.

A declaration is checked in three steps, each only when the one before it holds. Its structure
is `schemas/run.schema.json`, validated by jsonschema through `validate.py` (closed objects,
types, patterns, required fields). Then the semantic checks a schema cannot state: the window
runs forward in a real zone, source names are unique and name the zstd path, seat strings
parse and name stages, the four strata are each seated once, and every host allowance is
measured on the host version the declaration names. Then seat coverage.

Failures are named by their first word: ACCOUNT_UNDECLARED, SEAT_UNCOVERED, AMEND_REQUIRED,
ALLOWANCE_UNDECLARED, HOST_ALLOWANCE_STALE, RUN_EXISTS, DECLARATION_INVALID,
SEAT_COVERAGE_UNREADABLE, DENSITY_UNPROVENANCED.

Every seat of the declaration (stage seats and the four actor strata) must be named in the
`targets:` of the prompting guide that owns its host. That coverage is read by
`launch/check-prompting-targets.sh`'s own `OWNERS` and `targets()`, taken out of the script
at call time: nothing here restates which guide owns which host or how its targets are read.

`posture` (production, rehearsal or development) is the failure posture of design §4, added
to the declaration by `design/session-distill/2026-10-21T0318--2d4fbd4--plan-addendum-wp01.md`;
it is read by `records.StageRun.run_items`. `host_allowance` is the per-seat allowance of the
amendment to design §5.4 and `destinations` the root of each class every S11 and S12 writer
must resolve into. `output_caps` is the output-token cap of S3's calls: S2 cuts every window
reserving it and S3 declares it on every call, so both read this one number. `density`, the one
optional field, is an earlier run's measured table of what a token covers per seat and kind
(WP-08e): each entry names the run, the samples and the time it was measured, and a stage reads
it only where its own run has measured nothing of that seat and kind (`dispatch.measured_density`).
Nothing copies it forward; whoever declares the run writes it.

  declare.py --self-test
"""
import ast
import copy
import datetime
import json
import math
import pathlib
import re
import sys
import tempfile
import types
import zoneinfo

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import gate, records, stagelock, validate
from runlib.records import Refused

REPO = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = json.loads((pathlib.Path(__file__).resolve().parents[1] / "schemas" / "run.schema.json")
                    .read_text(encoding="utf-8"))
VALIDATOR = validate.compile_schema(SCHEMA)
STRATA = tuple(SCHEMA["properties"]["actor_seats"]["items"]["properties"]["stratum"]["enum"])  # design §8.4
DESTINATIONS = tuple(SCHEMA["properties"]["destinations"]["required"])
# A change to these top-level fields makes the results of the named stage, and every later
# stage that has a record, stale: criteria applied by S3 no longer describe what it read, and a
# window S2 cut while reserving one output cap is not the window a call reserving another may
# send - raising the cap is accepted as an amendment, and the views are cut again under it
# (`design/session-distill/2026-11-03T2155--6779ed7--the-output-cap-is-declared-and-a-reading-cites-its-own-quotes.md`).
INVALIDATED_FROM = {"checks": "S3", "output_caps": "S2"}
# The stage whose calls carry a window of a transcript view (S3 reading and its expansions): the
# seat of that stage needs a declared host allowance (amendment to design §5.4).
VIEW_WINDOW_STAGE = "S3"


def _is_text(value):
    return isinstance(value, str) and value.strip() != ""


def parse_seat(seat):
    """(provider, model, effort) of `provider:model/effort`, or None."""
    provider, colon, rest = seat.partition(":")
    model, slash, effort = rest.rpartition("/")
    return (provider, model, effort) if provider and colon and model and slash and effort else None


# --- structure: the schema ------------------------------------------------------------------

def structure_errors(run):
    """The schema's violations as `CODE path: message`. `account` has its own code: S0 cannot
    proceed without the owner's declared extra-usage setting and date (design §13.2)."""
    errors = []
    for err in validate.violations(VALIDATOR, run):
        where = [str(part) for part in err.absolute_path]
        if err.validator == "required":  # one line per missing name, wherever jsonschema repeats it
            problems = [(where + [name], "missing") for name in err.validator_value if name not in err.instance]
        else:
            problems = [(where, err.message)]
        for path, message in problems:
            code = "ACCOUNT_UNDECLARED" if path[:1] == ["account"] else "DECLARATION_INVALID"
            line = f"{code} {'.'.join(path) or '<root>'}: {message}"
            if line not in errors:
                errors.append(line)
    return errors


# --- semantics: what the schema cannot state ------------------------------------------------

def semantic_errors(run):
    """Cross-field and value checks over a declaration that has the schema's structure."""
    errors = []
    window = run["window"]
    try:
        zone = zoneinfo.ZoneInfo(window["tz"])
        start, end = (datetime.datetime.fromisoformat(window[key]) for key in ("start", "end"))
        start, end = (t if t.tzinfo else t.replace(tzinfo=zone) for t in (start, end))
        if not start < end:
            errors.append("DECLARATION_INVALID window: the half-open window [start, end) is empty or reversed")
    except (ValueError, KeyError) as exc:  # ZoneInfoNotFoundError is a KeyError
        errors.append(f"DECLARATION_INVALID window: start and end must be ISO-8601 and tz an IANA zone: {exc}")
    try:
        datetime.date.fromisoformat(run["account"]["declared_on"])
    except ValueError:
        errors.append("ACCOUNT_UNDECLARED account.declared_on: not a calendar date")
    names = [source["name"] for source in run["sources"]]
    errors.extend(f"DECLARATION_INVALID sources: source name {name!r} repeats"
                  for name in sorted({n for n in names if names.count(n) > 1}))
    if "zstd" not in names:
        errors.append("DECLARATION_INVALID sources: the absolute zstd path must be declared as a source named 'zstd'")
    errors.extend(f"DECLARATION_INVALID budget.per_stage.{key}: key is not a stage"
                  for key in run["budget"]["per_stage"] if key not in records.STAGES)
    errors.extend(f"DECLARATION_INVALID seats.{key}: key is not a stage"
                  for key in run["seats"] if key.split(".")[0] not in records.STAGES)
    strata = [actor["stratum"] for actor in run["actor_seats"]]
    if sorted(strata) != sorted(STRATA):
        errors.append(f"DECLARATION_INVALID actor_seats: exactly one seat per stratum {list(STRATA)} is required, got {strata}")
    seats = {f"seats.{key}": seat for key, seat in run["seats"].items()}
    seats.update({f"actor_seats.{actor['stratum']}": actor["seat"] for actor in run["actor_seats"]})
    seats.update({f"host_allowance.{seat}": seat for seat in run["host_allowance"]})
    errors.extend(f"DECLARATION_INVALID {where}: not a seat, expected provider:model/effort ({seat!r})"
                  for where, seat in seats.items() if parse_seat(seat) is None)
    if errors:
        return errors  # what follows reads seats as provider:model/effort
    for actor in run["actor_seats"]:
        if actor["stratum"].split("-")[0] != parse_seat(actor["seat"])[0]:
            errors.append(f"DECLARATION_INVALID actor_seats: the {actor['stratum']} stratum names a seat of another provider: {actor['seat']}")
    declared = {seat for where, seat in seats.items() if not where.startswith("host_allowance.")}
    for seat, entry in run["host_allowance"].items():
        if seat not in declared:
            errors.append(f"DECLARATION_INVALID host_allowance.{seat}: not a seat this declaration names")
        elif entry["host_version"] != run["hosts"].get(parse_seat(seat)[0]):
            errors.append(f"HOST_ALLOWANCE_STALE host_allowance.{seat}: measured on host {entry['host_version']}, "
                          f"the declaration names {run['hosts'].get(parse_seat(seat)[0])}")
    view_seat = run["seats"][VIEW_WINDOW_STAGE]
    if view_seat not in run["host_allowance"]:
        errors.append(f"ALLOWANCE_UNDECLARED seats.{VIEW_WINDOW_STAGE}: {view_seat} reads view windows and "
                      f"has no host_allowance entry")
    return errors + density_errors(run) + retry_errors(run)


def retry_errors(run):
    """The declared retry's violations (W review of WP-08e r1, F4): a `retry` names its count, its margin or both; an
    empty one re-declares nothing and so could lift a claim stop by changing nothing."""
    held = run.get("retry")
    if held is None:
        return []
    if not any(key in held for key in ("count", "margin")):
        return ["DECLARATION_INVALID retry: a declared retry names its count, its margin or both"]
    # an integer, not an integral float (W r2, F9): the schema's integer admits 2.0, and the claim's arithmetic then
    # ranges over it and raises
    return [f"DECLARATION_INVALID retry.{key}: an integer, not {held[key]!r}" for key in ("count", "margin")
            if key in held and (isinstance(held[key], bool) or not isinstance(held[key], int))]


DENSITY_KIND = re.compile(r"S[0-9]+[a-z]?:[a-z_]+")   # a declared density's kind, matched whole (fullmatch)


def density_errors(run):
    """The declared density table's violations (WP-08e, lead decision): each entry is an earlier run's measured table
    as that run wrote it, so it carries where it was measured (`measured_in`, a run id), on how many calls (`samples`,
    at least one) and when (`at`, ISO-8601); an entry without that is DENSITY_UNPROVENANCED, never a number taken on
    trust. It is keyed as a reservation class is (W review of WP-08e r1, F3): by a seat the declaration names, then by
    a stage's kind (`<stage>:<case type>`)."""
    errors = []
    named = set((run.get("seats") or {}).values()) | {a.get("seat") for a in run.get("actor_seats") or []}
    for seat, kinds in sorted((run.get("density") or {}).items()):
        if parse_seat(seat) is None:
            errors.append(f"DECLARATION_INVALID density.{seat}: not a seat, expected provider:model/effort")
        elif seat not in named:
            errors.append(f"DECLARATION_INVALID density.{seat}: not a seat this declaration names")
        for kind, entry in sorted(kinds.items()):
            where = f"density.{seat}.{kind!r}" if not DENSITY_KIND.fullmatch(kind) else f"density.{seat}.{kind}"
            if not DENSITY_KIND.fullmatch(kind):
                # the whole key, both ends (W r2, F9): the schema's `$` admits a trailing newline, and the reader's
                # exact key would never match it, so the entry would be read as nothing
                errors.append(f"DECLARATION_INVALID {where}: not a kind, expected <stage>:<case type> exactly")
            elif kind.split(":")[0] not in records.STAGES:
                errors.append(f"DECLARATION_INVALID {where}: {kind.split(':')[0]!r} is not a stage")
            value = entry["bytes_per_token"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f"DECLARATION_INVALID {where}.bytes_per_token: a finite number, not {value!r}")
            elif not value > 0:
                errors.append(f"DECLARATION_INVALID {where}.bytes_per_token: a token covers more than no bytes")
            missing = [k for k in ("measured_in", "samples", "at") if k not in entry]
            if not _is_text(entry.get("measured_in", "x")):
                missing.append("measured_in (a run id)")
            samples = entry.get("samples", 1)
            if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
                missing.append("samples (at least one)")
            try:
                datetime.datetime.fromisoformat(entry.get("at", "2026-01-01"))
            except (TypeError, ValueError):
                missing.append("at (ISO-8601)")
            if missing:
                errors.append(f"DENSITY_UNPROVENANCED {where}: a declared density carries the run that measured it, "
                              f"its samples and when; this one lacks {', '.join(missing)}")
    return errors


# --- seat coverage by the prompting-targets gate's own reader ------------------------------

class GateUnreadable(Exception):
    """The gate's reader could not be taken out of its script."""


def prompting_reader(repo=REPO):
    """(OWNERS, targets) exactly as `launch/check-prompting-targets.sh` defines them.

    The gate is a shell script around one Python body, so its reader is not importable. The
    two definitions are compiled out of that body, from the script's own text, and run with
    `pathlib.Path` resolving against `repo` (the script `cd`s there). When the gate changes
    how it reads targets, this follows; when it stops defining them, this fails by name."""
    script = pathlib.Path(repo) / "launch" / "check-prompting-targets.sh"
    try:
        body = re.search(r"<<'PY'\n(.*?)\nPY\n", script.read_text(encoding="utf-8"), re.S).group(1)
        tree = ast.parse(body)
    except (OSError, AttributeError, SyntaxError) as exc:
        raise GateUnreadable(f"{script} has no Python body to read: {exc!r}") from exc
    picked = [node for node in tree.body
              if (isinstance(node, ast.FunctionDef) and node.name == "targets")
              or (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "OWNERS"
                                                       for t in node.targets))]
    if len(picked) != 2:
        raise GateUnreadable(f"{script} does not define OWNERS and targets() at the top of its Python body")
    namespace = {"re": re, "sys": sys, "pathlib": types.SimpleNamespace(Path=lambda p: pathlib.Path(repo) / p)}
    exec(compile(ast.Module(body=picked, type_ignores=[]), str(script), "exec"), namespace)
    return namespace["OWNERS"], namespace["targets"]


def seat_coverage(run, repo=REPO):
    """SEAT_UNCOVERED for every seat (stage seats and actor strata) whose model the guide
    owning its provider does not name in `targets:`; SEAT_COVERAGE_UNREADABLE when the gate's
    reader or a guide cannot be read."""
    seats = sorted(set(run["seats"].values()) | {actor["seat"] for actor in run["actor_seats"]})
    try:
        owners, targets = prompting_reader(repo)
        covered, errors = {}, []
        for seat in seats:
            provider, model, _effort = parse_seat(seat)
            guide = owners.get(provider)
            if guide is None:
                errors.append(f"SEAT_UNCOVERED {seat}: no prompting guide owns provider {provider!r}")
                continue
            if guide not in covered:
                covered[guide] = targets(guide)
            if model not in covered[guide]:
                errors.append(f"SEAT_UNCOVERED {seat}: {guide} does not name {model} in its targets")
        return errors
    except GateUnreadable as exc:
        return [f"SEAT_COVERAGE_UNREADABLE {exc}"]
    except SystemExit as exc:  # the gate's reader exits on a missing guide or an absent targets:
        return [f"SEAT_COVERAGE_UNREADABLE {exc}"]


def check_declaration(run, repo=REPO):
    """Every violation of a declaration, each starting with its code; empty when it holds."""
    return structure_errors(run) or semantic_errors(run) or seat_coverage(run, repo)


# --- actions on a run directory -------------------------------------------------------------

def parse_value(text):
    """A `--set` value: JSON when it parses as JSON, else the text itself."""
    try:
        return json.loads(text)
    except ValueError:
        return text


def apply_assignments(run, assignments):
    """(new run, diff) for dotted-path assignments; the last key may be new, the path to it may not."""
    new, diff = copy.deepcopy(run), {}
    for path, value in assignments:
        keys = path.split(".")
        if keys[0] == "declaration_seq":
            raise Refused("DECLARATION_INVALID declaration_seq: set by declare, never assigned")
        parent = new
        for key in keys[:-1]:
            parent = parent.get(key) if isinstance(parent, dict) else None
        if not isinstance(parent, dict):
            raise Refused(f"DECLARATION_INVALID {path}: no such object to assign into")
        diff[path] = {"old": copy.deepcopy(parent.get(keys[-1])), "new": value}
        parent[keys[-1]] = value
    return new, diff


def _validated(run, repo):
    errors = check_declaration(run, repo)
    if errors:
        raise Refused("\n".join(errors))


def create(run_dir, run, repo=REPO):
    """Write `run.json` for a new run at declaration_seq 0 and bind its sha256 to seq 0 in the
    declaration log; a declaration is never replaced."""
    if run.get("declaration_seq", 0) != 0:
        raise Refused("DECLARATION_INVALID declaration_seq: a new declaration starts at 0")
    run = {**run, "declaration_seq": 0}
    _validated(run, repo)
    with stagelock.hold(run_dir, "declaration"):
        records.confine_declaration(run_dir)  # before anything is created or looked for
        if records.run_json_path(run_dir).exists() or records.amendments_path(run_dir).exists():
            raise Refused(f"RUN_EXISTS {run_dir}: amend it, never redeclare")
        records.append_amendment(run_dir, {"seq": 0, "at": records.now(), "reason": "declaration", "scope": [],
                                           "invalidates": [], "diff": {}, "run_json_sha256": records.bound_digest(run)})
        records.write_json(run_dir, records.run_json_path(run_dir), run)
    return run


def set_fields(run_dir, assignments, repo=REPO):
    """Edit the declaration in place while it is still a draft: declaration_seq 0, and no stage
    has recorded that it read it. The seq-0 binding follows the edit."""
    with stagelock.hold(run_dir, "declaration"):
        run, _digest, _amendments = records.declaration_state(run_dir)
        recorded = sorted(records.stage_records(run_dir))
        if recorded:
            raise Refused(f"AMEND_REQUIRED {', '.join(recorded)} already read run.json: "
                          f"change it with --amend, which says what it invalidates")
        if run["declaration_seq"] > 0:
            raise Refused(f"AMEND_REQUIRED declaration_seq {run['declaration_seq']}: an amended declaration "
                          f"changes only by a further amendment")
        new, _diff = apply_assignments(run, assignments)
        _validated(new, repo)
        records.write_json(run_dir, records.run_json_path(run_dir), new)
        records.rebind(run_dir, records.bound_digest(new))
    return new


def amend(run_dir, assignments, reason, scope=(), invalidates=(), repo=REPO):
    """Append an amendment and apply it: `scope[]` names the stages licensed to read it
    (default: every stage), `invalidates[]` the stages whose results it makes stale (the
    ones `INVALIDATED_FROM` derives, plus those named), and the line binds the sha256 of the
    run.json it produces to its seq. The line is written before run.json, so a crash between
    the two leaves a declaration_seq behind the log, which `records.declaration_state` reports
    as DECLARATION_DRIFT, never a silent edit. An amendment of a run.json that is not the
    one the log authorized is refused the same way."""
    if not _is_text(reason):
        raise Refused("DECLARATION_INVALID reason: an amendment states why")
    unknown = sorted((set(scope) | set(invalidates)) - set(records.STAGES))
    if unknown:
        raise Refused(f"DECLARATION_INVALID scope/invalidates: not stages: {unknown}")
    with stagelock.hold(run_dir, "declaration"):
        run, _digest, _amendments = records.declaration_state(run_dir)
        new, diff = apply_assignments(run, assignments)
        if not diff:
            raise Refused("DECLARATION_INVALID amendment: it changes nothing")
        new["declaration_seq"] = run["declaration_seq"] + 1
        _validated(new, repo)
        recorded = records.stage_records(run_dir)
        derived = {stage for path in diff if path.split(".")[0] in INVALIDATED_FROM
                   for stage in records.STAGES[records.STAGES.index(INVALIDATED_FROM[path.split(".")[0]]):]
                   if stage in recorded}
        amendment = {"seq": new["declaration_seq"], "at": records.now(), "reason": reason,
                     "scope": sorted(scope or records.STAGES, key=records.STAGES.index),
                     "invalidates": sorted(derived | set(invalidates), key=records.STAGES.index),
                     "diff": diff, "run_json_sha256": records.bound_digest(new)}
        records.append_amendment(run_dir, amendment)
        records.write_json(run_dir, records.run_json_path(run_dir), new)
    return amendment


# --- self-test ------------------------------------------------------------------------------

def fixture():
    """A valid declaration (golden): its seats are the ones the prompting guides cover today. Its S3 seat and
    its Claude host are the ones seats.json pins, read from it, so a re-pin moves every suite built on this
    declaration with it instead of leaving them on a host version the checkout no longer pins."""
    digest = lambda name: records.sha256_bytes(name.encode())  # noqa: E731
    pinned = gate.seats()
    claude = pinned["hosts"]["claude"]["version"]
    sonnet, opus = pinned["stage_seats"][VIEW_WINDOW_STAGE][0], "claude:claude-opus-5-5/high"
    astra = "codex:gpt-6-astra/xhigh"
    return {
        "question": "Which repeated work patterns deserve a place in the library?",
        "kind": "periodic",
        "posture": "production",
        "window": {"start": "2026-10-01T00:00:00", "end": "2026-10-08T00:00:00", "tz": "Asia/Seoul"},
        "sources": [{"name": "claude_projects", "path": "/srv/fixture/claude/projects"},
                    {"name": "codex_sessions", "path": "/srv/fixture/codex/sessions"},
                    {"name": "zstd", "path": "/opt/homebrew/bin/zstd"}],
        "checks": {"view_complete_share_min": 0.9},
        "budget": {"per_stage": {"S3": 4000000, "S4": 1000000},
                   "per_episode": {"tokens": 200000, "compactions": 2, "max_budget_usd": 5.0, "max_turns": 40},
                   "reserve": 0.15},
        "seats": {"S3": sonnet, "S4": opus, "S6.A": opus, "S6.B": astra, "S7b": astra},
        "actor_seats": [{"stratum": "claude-main", "seat": sonnet, "provenance": "observed"},
                        {"stratum": "claude-subagent", "seat": opus, "provenance": "observed"},
                        {"stratum": "codex-main", "seat": astra, "provenance": "observed"},
                        {"stratum": "codex-subagent", "seat": "codex:gpt-6-luna/medium", "provenance": "fallback"}],
        "config_manifest_B": {"global": digest("global")},
        "starting_hashes": {"ledger": digest("ledger"), "coverage": digest("coverage"),
                            "layers": {"global": digest("global")}},
        "account": {"extra_usage": "off", "declared_on": "2026-10-21"},
        "hosts": {"claude": claude, "codex": "0.163.0"},
        "declaration_seq": 0,
        "host_allowance": {sonnet: {"allowance_tokens": 3200, "host_version": claude,
                                    "flag_set_sha256": digest("flags")}},
        "output_caps": {VIEW_WINDOW_STAGE: 32000},
        "destinations": {name: f"/srv/fixture/destinations/{name}" for name in DESTINATIONS},
    }


def self_test():
    failures, ran = [], []

    def control(name, errors, *needles):
        """A named control: `errors` must carry every needle; with none it must be empty."""
        ran.append(name)
        if not needles and errors:
            failures.append(f"{name}: expected no violation, got {errors}")
        for needle in needles:
            if not any(needle in line for line in errors):
                failures.append(f"{name}: expected {needle!r} in {errors}")

    # A control whose subject raises something other than a named refusal fails by its own name,
    # with the exception in the message: a reverted check must not hide behind a traceback.
    def checked(run):
        try:
            return check_declaration(run)
        except Exception as exc:
            return [f"RAISED {exc!r}"]

    def mutated(edit):
        run = fixture()
        edit(run)
        return checked(run)

    def refusal(action, *args, **kwargs):
        try:
            action(*args, **kwargs)
        except Refused as exc:
            return str(exc).splitlines()
        except Exception as exc:
            return [f"RAISED {exc!r}"]
        return []

    # The declaration's fields, copied here once: design §4.1's contents plus what the plan adds
    # (WP-01: declaration_seq, host_allowance, destinations; P3 / design §13.2: account, hosts) and
    # `posture`, whose authority is design/session-distill/2026-10-21T0318--2d4fbd4--plan-addendum-wp01.md,
    # and `output_caps` (WP-08: the cap's declared home, named in the schema's $comment).
    # The schema is the authority for their shape; this pins which fields exist.
    # `density` and `retry` are the two optional fields (WP-08e: an earlier run's measured table; W r1 F4: the retries a
    # call's claim holds), each named in the schema's $comment.
    declared = {"question", "kind", "posture", "window", "sources", "checks", "budget", "seats",
                "actor_seats", "config_manifest_B", "starting_hashes", "account", "hosts",
                "declaration_seq", "host_allowance", "output_caps", "destinations"}
    control("schema-requires-exactly-the-declared-fields",
            [] if set(SCHEMA["required"]) == declared and set(SCHEMA["properties"]) == declared | {"density", "retry"}
            and "density (optional)" in SCHEMA["$comment"] and "retry (optional)" in SCHEMA["$comment"]
            else [f"schema requires {sorted(SCHEMA['required'])}, declares {sorted(SCHEMA['properties'])}"])
    measured = {"bytes_per_token": 1.852, "measured_in": "c2-20261110", "samples": 8, "at": "2026-11-10T23:22:00+09:00"}
    s3_seat = fixture()["seats"][VIEW_WINDOW_STAGE]  # a name of its own: `sonnet` is assigned later in this function
    control("WP-08e: a declared density with the run, the samples and the time that measured it is accepted",
            mutated(lambda run: run.update(density={s3_seat: {"S3:window": dict(measured)}})))
    control("WP-08e: a declared density without its provenance is refused at S0 by name (DENSITY_UNPROVENANCED)",
            mutated(lambda run: run.update(density={s3_seat: {"S3:window": {"bytes_per_token": 1.852}}})),
            f"DENSITY_UNPROVENANCED density.{s3_seat}.S3:window: a declared density carries the run that measured it")
    control("WP-08e: a declared density with no samples or an unreadable time is refused at S0 by name",
            mutated(lambda run: run.update(density={s3_seat: {"S3:window": {**measured, "samples": 0, "at": "yesterday"}}})),
            f"DENSITY_UNPROVENANCED density.{s3_seat}.S3:window", "samples (at least one), at (ISO-8601)")
    control("W r1 F4: a declared retry with its count and margin is accepted",
            mutated(lambda run: run.update(retry={"count": 2, "margin": 4000})))
    control("W r2 F9: a declared retry count that is an integral float is refused by name, before any arithmetic",
            mutated(lambda run: run.update(retry={"count": 2.0})), "DECLARATION_INVALID retry.count: an integer, not 2.0")
    control("W r2 F9: a declared density kind with a trailing newline is refused by name, so it is never read as nothing",
            mutated(lambda run: run.update(density={s3_seat: {"S3:window\n": dict(measured)}})),
            f"DECLARATION_INVALID density.{s3_seat}.'S3:window\\n': not a kind")
    control("W r2 F9: a declared density that is not finite is refused by name",
            mutated(lambda run: run.update(density={s3_seat: {"S3:window": {**measured, "bytes_per_token": math.inf}}})),
            f"DECLARATION_INVALID density.{s3_seat}.S3:window.bytes_per_token: a finite number, not inf")
    control("W r1 F4: a declared retry that names neither its count nor its margin is refused by name",
            mutated(lambda run: run.update(retry={})), "DECLARATION_INVALID retry: a declared retry names its count")
    control("WP-08e: a declared density is keyed by a seat the declaration names, as a reservation class is",
            mutated(lambda run: run.update(density={"claude:claude-fable-5-2/high": {"S3:window": dict(measured)},
                                                    "claude": {"S3:window": dict(measured)}})),
            "DECLARATION_INVALID density.claude:claude-fable-5-2/high: not a seat this declaration names",
            "DECLARATION_INVALID density.claude: not a seat, expected provider:model/effort")
    addendum = "design/session-distill/2026-10-21T0318--2d4fbd4--plan-addendum-wp01.md"
    control("posture-is-authorized-by-a-named-addendum-that-exists",
            [] if addendum in SCHEMA["$comment"] and (REPO / addendum).is_file()
            else [f"run.schema.json cites {SCHEMA['$comment']!r}; {addendum} must be named and present"])
    control("valid-declaration", checked(fixture()))  # the positive control, first
    # over the pinned set, not the schema's own list: a control that indexes a live list stops testing, silently, when
    # an entry leaves it, so a requirement dropped from the schema still has its drop control here, and that fails
    for name in sorted(declared):
        code = "ACCOUNT_UNDECLARED" if name == "account" else "DECLARATION_INVALID"
        control(f"drop-{name}", mutated(lambda run, name=name: run.pop(name)), f"{code} {name}: missing")
    control("unknown-field", mutated(lambda run: run.update(extra=1)),
            "DECLARATION_INVALID <root>: Additional properties", "'extra' was unexpected")
    control("declaration-not-an-object", checked([]), "DECLARATION_INVALID <root>: [] is not of type 'object'")
    control("account-not-an-object", mutated(lambda run: run.update(account="off")),
            "ACCOUNT_UNDECLARED account: 'off' is not of type 'object'")
    control("account-extra-usage-undecided", mutated(lambda run: run["account"].update(extra_usage="maybe")),
            "ACCOUNT_UNDECLARED account.extra_usage")
    control("account-without-date", mutated(lambda run: run["account"].pop("declared_on")),
            "ACCOUNT_UNDECLARED account.declared_on: missing")
    control("account-impossible-date", mutated(lambda run: run["account"].update(declared_on="2026-13-40")),
            "ACCOUNT_UNDECLARED account.declared_on: not a calendar date")
    control("kind-unknown", mutated(lambda run: run.update(kind="adhoc")), "DECLARATION_INVALID kind")
    control("output-cap-zero", mutated(lambda run: run["output_caps"].update(S3=0)), "DECLARATION_INVALID output_caps.S3")
    control("output-cap-not-an-integer", mutated(lambda run: run["output_caps"].update(S3=True)),
            "DECLARATION_INVALID output_caps.S3")
    control("output-cap-for-a-stage-nothing-reads", mutated(lambda run: run["output_caps"].update(S4=8000)),
            "DECLARATION_INVALID output_caps: Additional properties")
    control("posture-unknown", mutated(lambda run: run.update(posture="staging")), "DECLARATION_INVALID posture")
    control("window-reversed", mutated(lambda run: run["window"].update(start="2026-10-09T00:00:00")),
            "DECLARATION_INVALID window: the half-open window")
    control("window-empty", mutated(lambda run: run["window"].update(end=run["window"]["start"])),
            "DECLARATION_INVALID window: the half-open window")
    control("window-unknown-zone", mutated(lambda run: run["window"].update(tz="Mars/Olympus")),
            "DECLARATION_INVALID window: start and end")
    control("sources-empty", mutated(lambda run: run.update(sources=[])), "DECLARATION_INVALID sources: [] should be non-empty")
    control("sources-without-zstd", mutated(lambda run: run["sources"].pop()), "DECLARATION_INVALID sources: the absolute zstd")
    control("sources-relative-path", mutated(lambda run: run["sources"][0].update(path="claude/projects")),
            "DECLARATION_INVALID sources.0.path")
    control("sources-repeated-name", mutated(lambda run: run["sources"][1].update(name="zstd")),
            "DECLARATION_INVALID sources: source name 'zstd' repeats")
    control("budget-negative-tokens", mutated(lambda run: run["budget"]["per_episode"].update(tokens=-1)),
            "DECLARATION_INVALID budget.per_episode.tokens")
    control("budget-stage-unknown", mutated(lambda run: run["budget"]["per_stage"].update(S99=1)),
            "DECLARATION_INVALID budget.per_stage.S99: key is not a stage")
    control("budget-stage-name-malformed", mutated(lambda run: run["budget"]["per_stage"].update(census=1)),
            "DECLARATION_INVALID budget.per_stage: 'census' does not match any of the regexes")
    control("budget-no-turn-cap", mutated(lambda run: run["budget"]["per_episode"].pop("max_turns")),
            "DECLARATION_INVALID budget.per_episode.max_turns: missing")
    control("seat-malformed", mutated(lambda run: run["seats"].update(S4="claude-opus-5-5")),
            "DECLARATION_INVALID seats.S4: not a seat")
    control("seats-without-the-view-window-stage", mutated(lambda run: run["seats"].pop("S3")),
            "DECLARATION_INVALID seats.S3: missing")
    control("seat-for-unknown-stage", mutated(lambda run: run["seats"].update(S99="claude:claude-sonnet-5-5/xhigh")),
            "DECLARATION_INVALID seats.S99: key is not a stage")
    control("actor-stratum-missing", mutated(lambda run: run["actor_seats"].pop()), "DECLARATION_INVALID actor_seats")
    control("actor-stratum-repeated", mutated(lambda run: run["actor_seats"][3].update(stratum="codex-main")),
            "DECLARATION_INVALID actor_seats: exactly one seat per stratum")
    control("actor-seat-of-another-provider",
            mutated(lambda run: run["actor_seats"][0].update(seat="codex:gpt-6-astra/xhigh")),
            "the claude-main stratum names a seat of another provider")
    control("starting-hash-not-sha256", mutated(lambda run: run["starting_hashes"].update(ledger="abc")),
            "DECLARATION_INVALID starting_hashes.ledger")
    control("manifest-entry-not-sha256", mutated(lambda run: run["config_manifest_B"].update(extra_layer="abc")),
            "DECLARATION_INVALID config_manifest_B.extra_layer")
    control("destination-class-missing", mutated(lambda run: run["destinations"].pop("recovery")),
            "DECLARATION_INVALID destinations.recovery: missing")
    control("destination-root-relative", mutated(lambda run: run["destinations"].update(nudge="state/nudge")),
            "DECLARATION_INVALID destinations.nudge")
    # the amendment to design §5.4: a declared allowance for the view-window seat, measured on the declared host
    sonnet = fixture()["seats"]["S3"]
    control("host-allowance-missing-for-the-view-window-seat", mutated(lambda run: run["host_allowance"].clear()),
            f"ALLOWANCE_UNDECLARED seats.S3: {sonnet}")
    control("host-allowance-only-for-another-seat",
            mutated(lambda run: run.update(host_allowance={run["seats"]["S4"]: run["host_allowance"].popitem()[1]})),
            "ALLOWANCE_UNDECLARED seats.S3")
    control("host-allowance-measured-on-another-host-version",
            mutated(lambda run: run["hosts"].update(claude="2.1.305")),
            f"HOST_ALLOWANCE_STALE host_allowance.{sonnet}: measured on host {fixture()['hosts']['claude']}, "
            f"the declaration names 2.1.305")
    control("host-allowance-for-an-undeclared-seat",
            mutated(lambda run: run["host_allowance"].update({"claude:claude-haiku-5-5/low": run["host_allowance"][sonnet]})),
            "DECLARATION_INVALID host_allowance.claude:claude-haiku-5-5/low: not a seat this declaration names")
    control("host-allowance-key-not-a-seat", mutated(lambda run: run["host_allowance"].update({"sonnet": run["host_allowance"][sonnet]})),
            "DECLARATION_INVALID host_allowance.sonnet: not a seat")
    control("host-allowance-without-its-flag-set", mutated(lambda run: run["host_allowance"][sonnet].pop("flag_set_sha256")),
            f"DECLARATION_INVALID host_allowance.{sonnet}.flag_set_sha256: missing")
    # seat coverage by the prompting-targets gate's own reader
    control("stage-seat-uncovered",
            mutated(lambda run: run["seats"].update(S4="claude:claude-opus-9-9/high")),
            "SEAT_UNCOVERED claude:claude-opus-9-9/high")
    control("codex-subagent-stratum-uncovered",  # plan P6: the runtime half of the targets gate
            mutated(lambda run: run["actor_seats"][3].update(seat="codex:gpt-4o-mini/medium")),
            "SEAT_UNCOVERED codex:gpt-4o-mini/medium")
    control("provider-without-a-guide", mutated(lambda run: run["seats"].update(S4="gemini:gemini-3/high")),
            "SEAT_UNCOVERED gemini:gemini-3/high: no prompting guide owns provider 'gemini'")

    # the reader is the gate's own: compiled from its script, and it follows the script when that changes
    owners, targets = prompting_reader()
    targets_gate = str(REPO / "launch" / "check-prompting-targets.sh")
    ran.append("reader-is-compiled-from-the-gate-script")
    if targets.__code__.co_filename != targets_gate or owners.get("claude") is None:
        failures.append(f"reader-is-compiled-from-the-gate-script: {targets.__code__.co_filename}")
    with tempfile.TemporaryDirectory() as td:
        scratch = pathlib.Path(td)
        (scratch / "launch").mkdir()
        (scratch / "codex" / "guides").mkdir(parents=True)
        text = pathlib.Path(targets_gate).read_text(encoding="utf-8")
        for guide in ("claude-prompting", "gpt-prompting"):
            (scratch / "codex" / "guides" / f"{guide}.md").write_bytes(
                (REPO / "codex" / "guides" / f"{guide}.md").read_bytes())

        def with_gate(edit):
            (scratch / "launch" / "check-prompting-targets.sh").write_text(edit(text), encoding="utf-8")
            return seat_coverage(fixture(), scratch)

        control("scratch-copy-of-the-gate-agrees", with_gate(lambda t: t))
        control("gate-edit-moves-the-verdict",  # claude seats now read the gpt guide: the reader followed the script
                with_gate(lambda t: t.replace('"claude": "claude-prompting"', '"claude": "gpt-prompting"')),
                f"SEAT_UNCOVERED {sonnet}: gpt-prompting does not name {parse_seat(sonnet)[1]}")
        control("gate-without-a-targets-function",
                with_gate(lambda t: t.replace("def targets(", "def renamed(")), "SEAT_COVERAGE_UNREADABLE")
        control("gate-without-a-python-body", with_gate(lambda t: t.replace("<<'PY'", "<<'EOF'")),
                "SEAT_COVERAGE_UNREADABLE")
        (scratch / "codex" / "guides" / "gpt-prompting.md").unlink()
        control("guide-missing", with_gate(lambda t: t), "SEAT_COVERAGE_UNREADABLE FAIL: missing prompting guide")

    # actions on a run directory. A step that must succeed for the controls after it to mean anything
    # is run through `must`: if it is refused, the failure is named by the step and the rest is skipped.
    class Abort(Exception):
        pass

    def must(step, action, *args, **kwargs):
        try:
            return action(*args, **kwargs)
        except Exception as exc:
            failures.append(f"{step}: refused unexpectedly ({exc}); the controls after it were not run")
            raise Abort from exc

    def stage_once(directory, name, output=None):
        # S2 has parts (`records.STAGE_PARTS`), and a writer there names the part it produces; these
        # controls are about the declaration a stage binds, not about parts.
        part = "views" if name in records.STAGE_PARTS else None
        with records.run_stage(directory, name, part=part) as stage_run:
            if output:
                (directory / output).write_text("{}\n", encoding="utf-8")
                stage_run.output(output)

    with tempfile.TemporaryDirectory() as td:
        try:
            run_dir = pathlib.Path(td) / "r1"
            control("create", [] if must("create", create, run_dir, fixture())["declaration_seq"] == 0 else ["not at seq 0"])
            control("create-twice", refusal(create, run_dir, fixture()), "RUN_EXISTS")
            control("create-invalid", refusal(create, pathlib.Path(td) / "r2", {**fixture(), "kind": "x"}),
                    "DECLARATION_INVALID kind")
            if records.run_json_path(pathlib.Path(td) / "r2").exists():
                failures.append("create-invalid: an invalid declaration was written")
            control("create-at-a-later-seq", refusal(create, pathlib.Path(td) / "r3", {**fixture(), "declaration_seq": 2}),
                    "DECLARATION_INVALID declaration_seq")
            control("set-before-any-stage",
                    [] if must("set before any stage", set_fields, run_dir, [("checks.view_complete_share_min", 0.8)])
                    ["checks"]["view_complete_share_min"] == 0.8 else ["not applied"])
            control("set-rebinds-the-declaration-at-seq-0", refusal(records.declaration_state, run_dir))
            control("set-invalid-value", refusal(set_fields, run_dir, [("kind", "adhoc")]), "DECLARATION_INVALID kind")
            control("set-seq", refusal(set_fields, run_dir, [("declaration_seq", 7)]), "DECLARATION_INVALID declaration_seq")
            control("set-into-nothing", refusal(set_fields, run_dir, [("budget.nope.x", 1)]), "no such object")
            control("amend-without-reason", refusal(amend, run_dir, [("budget.reserve", 0.2)], " "), "an amendment states why")
            control("amend-unknown-stage", refusal(amend, run_dir, [("budget.reserve", 0.2)], "r", scope=["S99"]), "not stages")
            control("amend-changing-nothing", refusal(amend, run_dir, [], "r"), "it changes nothing")
            must("stage S1 starts under the bound declaration", stage_once, run_dir, "S1", "census.json")
            control("set-after-a-stage-recorded",
                    refusal(set_fields, run_dir, [("checks.view_complete_share_min", 0.7)]), "AMEND_REQUIRED S1")
            first = must("amend budget", amend, run_dir, [("budget.reserve", 0.2)], "raise the retry reserve", scope=["S2"])
            control("amend-budget", [] if (first["seq"], first["scope"], first["invalidates"]) == (1, ["S2"], [])
                    else [f"unexpected amendment {first}"])
            for stage in ("S2", "S3", "S4"):
                must(f"stage {stage} starts under the bound declaration", stage_once, run_dir, stage)
            second = must("amend checks", amend, run_dir, [("checks.view_complete_share_min", 0.95)],
                          "tighten the completeness criterion")
            control("amend-checks-invalidates-s3-and-downstream",
                    [] if (second["seq"], second["invalidates"]) == (2, ["S3", "S4"]) else [f"unexpected {second}"])
            third = must("amend hosts.codex", amend, run_dir, [("hosts.codex", "0.164.0")], "host upgrade", invalidates=["S1"])
            control("amend-explicit-invalidation", [] if third["invalidates"] == ["S1"] else [f"unexpected {third}"])
            logged = records.read_amendments(run_dir)
            control("amendments-are-logged-in-order",
                    [] if [a["seq"] for a in logged] == [1, 2, 3] and logged[1]["diff"] == {
                        "checks.view_complete_share_min": {"old": 0.8, "new": 0.95}} else [f"log is {logged}"])
            control("run-json-follows-the-log",
                    [] if records.read_json(records.run_json_path(run_dir))["declaration_seq"] == 3 else ["seq not advanced"])
            control("amend-to-an-invalid-declaration", refusal(amend, run_dir, [("kind", "adhoc")], "r"), "DECLARATION_INVALID kind")
            if len(records.read_amendments(run_dir)) != 3:
                failures.append("amend-to-an-invalid-declaration: the refused amendment was logged")
            # a host upgrade is re-measured in the same amendment: the version alone leaves the allowance stale
            control("amend-host-upgrade-without-remeasuring", refusal(amend, run_dir, [("hosts.claude", "2.1.305")], "upgrade"),
                    f"HOST_ALLOWANCE_STALE host_allowance.{sonnet}")
            remeasured = {sonnet: {**fixture()["host_allowance"][sonnet], "host_version": "2.1.305"}}
            upgrade = must("amend the host upgrade with its allowance", amend, run_dir,
                           [("hosts.claude", "2.1.305"), ("host_allowance", remeasured)], "upgrade, re-measured")
            control("amend-host-upgrade-with-the-new-allowance",
                    [] if upgrade["seq"] == 4 and records.read_json(records.run_json_path(run_dir))["host_allowance"] == remeasured
                    else [f"unexpected {upgrade}"])
            # raising the cap is ACCEPTED, and every recorded stage from S2 on is stale: S2 cut the windows reserving
            # the old cap, so a call reserving more may not send them
            raised = must("amend output_caps", amend, run_dir, [("output_caps.S3", 48000)], "a longer answer")
            control("amend-output-cap-invalidates-s2-and-downstream",
                    [] if (raised["seq"], raised["invalidates"]) == (5, ["S2", "S3", "S4"]) else [f"unexpected {raised}"])

            # each declaration seq is bound to the run.json authorized at it: a hand edit, before any stage
            # has read the new seq, is found by the next amendment, edit or stage
            bound = pathlib.Path(td) / "r5"
            must("create r5", create, bound, fixture())
            log = records.read_log(bound)
            control("create-binds-the-declaration-to-seq-0",
                    [] if len(log) == 1 and log[0]["seq"] == 0 and log[0]["run_json_sha256"] == records.sha256_file(records.run_json_path(bound))
                    else [f"unexpected log {log}"])
            must("amend r5", amend, bound, [("budget.reserve", 0.2)], "raise the retry reserve")
            control("an-amendment-binds-the-new-run-json-to-its-seq",
                    [] if records.read_log(bound)[-1]["run_json_sha256"] == records.sha256_file(records.run_json_path(bound))
                    and records.read_log(bound)[-1]["seq"] == 1 else [f"unexpected log {records.read_log(bound)}"])
            control("set-after-an-amendment-is-refused", refusal(set_fields, bound, [("budget.reserve", 0.3)]),
                    "AMEND_REQUIRED declaration_seq 1")
            authorized = records.run_json_path(bound).read_bytes()
            edited = records.read_json(records.run_json_path(bound))
            edited["checks"]["view_complete_share_min"] = 0.5
            records.run_json_path(bound).write_text(records.json_text(edited), encoding="utf-8")  # by hand: the seq stays 1
            log_before = records.amendments_path(bound).read_bytes()
            control("amend-after-a-hand-edit-of-checks-is-refused", refusal(amend, bound, [("budget.reserve", 0.4)], "r"),
                    "DECLARATION_DRIFT declare: run.json is not the declaration authorized at seq 1")
            control("set-after-a-hand-edit-is-refused", refusal(set_fields, bound, [("budget.reserve", 0.4)]), "DECLARATION_DRIFT")
            control("the-refused-amend-logged-nothing",
                    [] if records.amendments_path(bound).read_bytes() == log_before else ["the log changed"])
            records.run_json_path(bound).write_bytes(authorized)
            control("the-authorized-run-json-amends-again",
                    [] if must("amend the authorized run.json", amend, bound, [("budget.reserve", 0.4)], "r")["seq"] == 2
                    else ["not amended"])

            # a link inside a new run directory cannot make `create` write outside it: nothing is created
            # at the link's target, and nothing is logged inside before the refusal
            def escape(action, *args):
                try:
                    action(*args)
                    return []
                except stagelock.Escaped as exc:
                    return [str(exc)]
                except Exception as exc:
                    return [f"RAISED {exc!r}"]

            for name, linked_file in (("r6", "run.json"), ("r7", "amendments.jsonl")):
                linked, external = pathlib.Path(td) / name, pathlib.Path(td) / f"{name}-external"
                linked.mkdir()
                external.mkdir()
                (linked / linked_file).symlink_to(external / linked_file)  # dangling
                control(f"create-through-a-dangling-{linked_file}-link", escape(create, linked, fixture()), "RUN_PATH_ESCAPE")
                control(f"the-refused-create-touched-nothing-via-{linked_file}",
                        [] if not list(external.iterdir()) and sorted(p.name for p in linked.iterdir()) in (
                            [linked_file, "locks"], ["locks", linked_file]) else
                        [f"external {list(external.iterdir())}, run dir {sorted(p.name for p in linked.iterdir())}"])

            # a link made after the declaration cannot make a later mutation half-happen: both files are confined
            # before either is written, no byte changes, and the same call succeeds once the link is repaired
            mutators = {"amend": lambda directory: amend(directory, [("budget.reserve", 0.4)], "raise the reserve"),
                        "set": lambda directory: set_fields(directory, [("budget.reserve", 0.4)])}
            for mutator, mutate in mutators.items():
                for linked_file, other_file in (("run.json", "amendments.jsonl"), ("amendments.jsonl", "run.json")):
                    name = f"{mutator}-with-{linked_file}-linked-out"
                    directory, external = pathlib.Path(td) / f"l-{mutator}-{linked_file}", pathlib.Path(td) / f"l-{mutator}-{linked_file}-x"
                    external.mkdir()
                    must(f"create {directory.name}", create, directory, fixture())
                    linked, other = directory / linked_file, directory / other_file
                    body, other_body = linked.read_bytes(), other.read_bytes()
                    (external / linked_file).write_bytes(body)
                    linked.unlink()
                    linked.symlink_to(external / linked_file)
                    control(name, escape(mutate, directory), "RUN_PATH_ESCAPE")
                    control(f"the-refused-{name}-changed-no-file",
                            [] if (external / linked_file).read_bytes() == body and linked.read_bytes() == body
                            and other.read_bytes() == other_body and sorted(q.name for q in external.iterdir()) == [linked_file]
                            else [f"{linked_file} or {other_file} or the link target changed"])
                    linked.unlink()
                    linked.write_bytes(body)  # the link repaired
                    result = must(f"{name}, retried once the link is repaired", mutate, directory)
                    retried = records.read_json(records.run_json_path(directory))
                    control(f"{name}-succeeds-once-the-link-is-repaired",
                            [] if retried["budget"]["reserve"] == 0.4 and result
                            and retried["declaration_seq"] == (1 if mutator == "amend" else 0)
                            else [f"the retried {mutator} left {retried['budget']['reserve']} at seq {retried['declaration_seq']}"])

            # done-when 3 on a run whose only record is S3: --set is refused naming S3, the same change
            # through --amend is accepted, logged, and marks S3 invalidated
            s3_dir = pathlib.Path(td) / "r4"
            must("create r4", create, s3_dir, fixture())
            must("stage S3 starts under the bound declaration", stage_once, s3_dir, "S3")
            change = [("checks.view_complete_share_min", 0.99)]
            control("set-checks-after-s3-is-refused", refusal(set_fields, s3_dir, change), "AMEND_REQUIRED S3 already read run.json")
            control("the-refused-set-changed-nothing",
                    [] if records.read_json(records.run_json_path(s3_dir))["checks"]["view_complete_share_min"] == 0.9
                    else ["run.json was edited in place"])
            accepted = must("amend the checks change", amend, s3_dir, change, "tighten the criterion")
            control("the-same-checks-change-through-amend",
                    [] if (accepted["seq"], accepted["invalidates"]) == (1, ["S3"])
                    and records.read_amendments(s3_dir) == [accepted]
                    and records.read_json(records.run_json_path(s3_dir))["checks"]["view_complete_share_min"] == 0.99
                    else [f"unexpected {accepted}"])
        except Abort:
            pass

    for failure in failures:
        print(f"declare --self-test [FAIL] {failure}")
    if failures:
        return 1
    for name in ran:
        print(f"  control {name}")
    print(f"declare --self-test: OK ({len(ran)} controls)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: declare.py --self-test")
    sys.exit(self_test())
