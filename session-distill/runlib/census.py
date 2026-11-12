#!/usr/bin/env python3
"""S1, the census (design §5.1, §5.2, §5.3): what transcripts exist, which are the owner's, and what each owes.

Enumeration starts from the transcript directories (`claude_projects`, `codex_sessions`,
`codex_archived_sessions`), plain and zstd-compressed alike, and takes the union with the identities the
host indexes name for the window. Every discovered identity ends in exactly one status of §5.1:
`excluded(reason)`, `child_of(parent)`, `unknown_provenance`, `unreadable`, `known_absent`, or eligible,
which S3's results later turn into `read_complete`, `read_partial`, `failed` or `deferred` (`reconcile`).
`nothing_new` is decided here, when the window owns nothing the coverage state still owes. A source whose
directory is missing is reported unknown with no total, never zero.

Every transcript is read at its head, which is enough for its class and for the children and the
automated rollouts that are known by their first record. Every eligible transcript is then read in full,
once, whatever its age: sha, record count, the append-only test against the version on record, the records
the window owns, and all the lineage evidence (pointers, host-minted record ids, (timestamp, human text)
turns) wherever in the file it lies, because an old transcript's only link to an active one may be past
its head. The version is the transcript's complete lines (D-20261103-8facee): a line the host is still
writing is not in it, and what the host appends after this read is the next run's. The next run reads another
window, so what it finds appended to a version and stamped inside a window already run - a line that was still being
written then, or one written late - it holds in the backlog under that window, for itself to read (`carry_appended`).

Every row's `window_overlap` says how it lies against the window: from its record timestamps for a row read in full
(inside, straddles_start, straddles_end, straddles_both, context_only); for a row left unread - unknown, unreadable, or
a member of such a root - from the best evidence its files give (`unread_overlap`): `before_window` when each was last
written before the window starts, its record timestamps otherwise, `undetermined` when neither decides. The observation
basis counts a row only when its unit may hold a record of the window (D-20261106-208882).

The unit S1 judges and S2 reads is a root with all its descendants at any depth (D-20261103-85f3e8): every
member of an eligible root is read in full like the root, and the root is `nothing_new` only when neither it
nor any member owes the window anything. A member whose read fails leaves the unit and its descendants stay in it:
the unit follows the parent links, not the statuses. One S3 result answers the unit, crediting each member's readings to
the member. Counting follows §5.3: a lineage counts once, through its root, when its component has exactly
one root and a host-written index names that root.

Identity is `(host, session id)`: a transcript is keyed `<host>:<id>` (`lineage.identity`) in the coverage
state, in lineage components and in S3's results. The originator table is a declared source of the run
(`name: originators`, its `path` and `sha256`); S1 reads exactly those bytes.

An S3 result, which `reconcile` takes, is `{transcript, status, readings, pending_events, resolved_events}`,
`readings` a list of `{version, sha, read, processed}` over the versions it read (`processed` is keyed by
window id); `coverage.apply_results` says what each field must satisfy.

The legacy `session-distill/census.py` survives the cutover as an author-side window tool (the v1 window
census), not as part of this pipeline; this module is `distill.py census`.
Failures are named by their first word: SET_MISMATCH, ORIGINATOR_TABLE_INVALID, ORIGINATOR_TABLE_UNDECLARED,
ORIGINATOR_TABLE_CHANGED, COVERAGE_BASE_STALE, CENSUS_INVALID, RUN_PATH_ESCAPE (the snapshot directory leaves the run).

  census.py --self-test
"""
import concurrent.futures
import contextlib
import copy
import datetime
import functools
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import coverage, lineage, records, sources, stagelock, validate
from runlib.records import Refused

HERE = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_PATH = HERE / "schemas" / "census.schema.json"
ORIGINATORS_PATH = HERE / "originators.json"
ORIGINATORS_SOURCE = "originators"  # the name under which a run declares its originator table
CLASSES = ("claude-cli", "claude-desktop", "codex-cli", "codex-desktop")
TABLE_CLASSES = ("codex-cli", "codex-desktop", "excluded", "unknown_provenance")
DIRECTORIES = ("claude_projects", "codex_sessions", "codex_archived_sessions", "claude_desktop_index", "agent_bios_state")
HEAD_RECORDS = 256        # records of a head: enough to classify a transcript before it is read in full
ENTRYPOINT_SCAN = 4096    # how far into a Claude file the first entrypoint is looked for
# Rows the census leaves unread whose place against the window the observation basis still needs (D-20261106-208882),
# and the window_overlap values that say a row holds no record of the window: by its record timestamps, or by the
# file-time bound (`unread_overlap`).
UNREAD_STATUSES = ("unknown_provenance", "unreadable")
OUTSIDE = ("context_only", "before_window")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_VALIDATOR = []


def validator():
    if not _VALIDATOR:
        _VALIDATOR.append(validate.compile_schema(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))))
    return _VALIDATOR[0]


def load_originators(path=ORIGINATORS_PATH):
    """(`{originator: class}`, sha256 of the file): the owner's table that assigns a source class to the
    Codex clients that all write `vscode` (design §5.1)."""
    data = pathlib.Path(path).read_bytes()
    try:
        table = json.loads(data)["codex"]
        bad = {k: v for k, v in table.items() if v not in TABLE_CLASSES}
    except (ValueError, KeyError, AttributeError, TypeError) as exc:
        raise Refused(f"ORIGINATOR_TABLE_INVALID {path}: expected {{\"codex\": {{originator: class}}}} ({exc})") from exc
    if bad:
        raise Refused(f"ORIGINATOR_TABLE_INVALID {path}: {bad} are not one of {TABLE_CLASSES}")
    return table, records.sha256_bytes(data)


def bound_table(declaration, override=None):
    """(`{originator: class}`, sha256) of the table the declaration binds to this run.

    The table is a declared source: `{name: originators, path, sha256}`. S1 refuses a declaration that names
    none, a `--originators` that is not the declared path, an entry without a pin and bytes that are not the
    pinned ones, so classification cannot change under one declaration without an amendment."""
    entry = next((s for s in declaration["sources"] if s["name"] == ORIGINATORS_SOURCE), None)
    if entry is None:
        raise Refused(f"ORIGINATOR_TABLE_UNDECLARED S1: the declaration names no '{ORIGINATORS_SOURCE}' source; declare the table with its path and sha256")
    if override and os.path.abspath(override) != entry["path"]:
        raise Refused(f"ORIGINATOR_TABLE_UNDECLARED S1: {override} is not the declared table {entry['path']}; amend the declaration to use another")
    if not entry.get("sha256"):
        raise Refused(f"ORIGINATOR_TABLE_UNDECLARED S1: the '{ORIGINATORS_SOURCE}' source {entry['path']} carries no sha256")
    table, sha = load_originators(entry["path"])
    if sha != entry["sha256"]:
        raise Refused(f"ORIGINATOR_TABLE_CHANGED S1: {entry['path']} hashes {sha[:12]}, the declaration pinned {entry['sha256'][:12]}; "
                      "amend the declaration with the new hash to accept the edit")
    return table, sha


def key_of(entry):
    return lineage.identity(entry["host"], entry["id"])


# What a census row holds of one transcript file. A Claude row holds its one file in these fields; a Codex row holds
# them per file in `segments`, never on the row (D-20261103-a7128a): Codex Desktop writes one thread across several
# rollout files under one id, and a row-level copy of one file's fields read as the session's would drop the others.
SEGMENT_FIELDS = ("path", "sha256", "versions", "owned", "work")


def stem_of(path):
    """A Codex rollout file's name without `.jsonl` or `.jsonl.zst`: the same for a file and its compressed copy."""
    return re.sub(r"\.jsonl$", "", re.sub(r"\.zst$", "", os.path.basename(path)))


def segment(stem, source, path=None):
    return {"stem": stem, "source": source, "path": path, "sha256": None, "versions": [], "owned": [],
            "work": {"version": None, "in_window": [], "backlog": []}}


def coverage_key(entry, seg):
    """The coverage state's name for one file of a row: the row's identity for a Claude transcript, and
    `codex:<id>@<stem>` for every Codex rollout file, one file or several (D-20261103-a7128a)."""
    return key_of(entry) if entry["host"] == "claude" else f"{key_of(entry)}@{seg['stem']}"


def identity_of_key(key):
    """The row identity a coverage key belongs to."""
    return key.split("@", 1)[0]


def segments_of(entry):
    """The transcript files of a census row in their order, each `{key, stem, source, path, sha256, versions, owned,
    work}` with `key` its coverage key: the one reader of a row's files outside the census (D-20261103-a7128a). A Codex
    row's are its `segments` (none for a row an index or the coverage state names without a file); a Claude row's is the
    row itself. What it returns is a copy: a reader changes nothing in the census through it."""
    if entry["host"] == "codex":
        return [{"key": coverage_key(entry, seg), **copy.deepcopy(seg)} for seg in entry["segments"]]
    return [{"key": key_of(entry), "stem": None, "source": entry["source"], **copy.deepcopy({k: entry[k] for k in SEGMENT_FIELDS})}]


CENSUS_FILE = "census.json"


def load_document(path):
    """The census document at `path`, parsed. What the read raises - absent, unreadable, not JSON - is the caller's to
    name; `rows` then takes the rows out of it."""
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def load(run_dir):
    """The census S1 left in `run_dir`, refused by name when there is none."""
    path = pathlib.Path(run_dir) / CENSUS_FILE
    if not path.is_file():
        raise Refused(f"INPUT_INVALID S1: {path} is absent; run the census first")
    return load_document(path)


def misplaced(e):
    """Why a row's files are not where its host keeps them, or None: a Codex row holds them in `segments` and never on
    the row, a Claude row never in `segments` (D-20261103-a7128a)."""
    if e.get("host") == "codex":
        on_row = [k for k in SEGMENT_FIELDS if k in e]
        return (f"a Codex row carries {on_row} on the row" if on_row
                else None if isinstance(e.get("segments"), list) else "a Codex row has no segments")
    return "a Claude row carries segments" if "segments" in e else None


def rows(document):
    """The rows of a census document: the one way into them outside the census (with `segments_of` for a row's files).
    ValueError, naming the first row, when they are not a list of rows each holding its files where its host keeps
    them, so a reader built for another shape fails here by name instead of reading a part of a session as the whole."""
    transcripts = document.get("transcripts") if isinstance(document, dict) else None
    if not isinstance(transcripts, list) or not all(isinstance(e, dict) for e in transcripts):
        raise ValueError("CENSUS_MALFORMED: its transcripts are not a list of rows")
    for e in transcripts:
        why = misplaced(e)
        if why:
            raise ValueError(f"CENSUS_MALFORMED {e.get('host')}:{e.get('id')}: {why}")
    return transcripts


# The structural guard of D-20261103-a7128a: outside this module a census document is read only through `load` or
# `load_document` and its rows only through `rows`, so every reader meets the row shapes above. A module that names the
# census file is listed here with the reason it may; a site not listed, or a listed site that no longer names it, fails.
READER_MODULES = ("distill.py", "runlib/*.py")
READER_EXCEPTIONS = {
    ("runlib/views.py", "run"): "declares census.json as S2's input artifact; the census itself is read through load",
    ("runlib/stage_read.py", "run"): "declares census.json as S3's input artifact; the census itself is read through load "
                                     "and rows, and folded back through reconcile",
    ("runlib/inventory.py", "<module>"): "CENSUS names the file the inventory part declares and opens",
    ("runlib/inventory.py", "census_entries"): "maps an absent, unreadable or malformed census to the transcript layers' "
                                               "named unknowns, reading it through load_document and rows",
    ("distill.py", "cmd_inventory"): "declares the census as the inventory part's S1 input artifact",
    ("runlib/stage_form.py", "<module>"): "INPUTS declares census.json as S4's S1 input artifact; the barrier reads the "
                                          "census itself through load and rows",
}
LOADERS = frozenset(("load", "load_document", "build", "reconcile", "run"))
TEST_CODE = ("self_test", "fx_", "golden")


def reader_bypasses(texts):
    """Violations of the guard over `texts` (`{relative path: source}`): `(violations, sites)`. A site is a
    `(module, top-level function)` of non-test code that names the census file (`"census.json"` or `CENSUS`); a
    violation is a site no exception lists, an exception no site matches, or a census document taken from this
    module's loaders and indexed for its `transcripts` instead of read through `rows`."""
    import ast
    sites, violations = set(), []
    for rel, text in sorted(texts.items()):
        tree = ast.parse(text)
        for top in [n for n in tree.body]:
            name = top.name if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else "<module>"
            if name.startswith(TEST_CODE):
                continue
            skipped = {id(n) for f in ast.walk(top) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name.startswith(TEST_CODE)
                       for n in ast.walk(f)}
            loaded = set()
            for node in ast.walk(top):
                if id(node) in skipped:
                    continue
                if (isinstance(node, ast.Constant) and node.value == CENSUS_FILE) or (isinstance(node, ast.Name) and node.id == "CENSUS") \
                        or (isinstance(node, ast.Attribute) and node.attr == "CENSUS"):
                    sites.add((rel, name))
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) \
                        and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "census" and node.value.func.attr in LOADERS:
                    for target in node.targets:
                        loaded |= {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}
            for node in ast.walk(top):
                if id(node) in skipped:
                    continue
                key = (node.slice if isinstance(node, ast.Subscript) else node.args[0] if isinstance(node, ast.Call) and node.args
                       and isinstance(node.func, ast.Attribute) and node.func.attr == "get" else None)
                holder = node.value if isinstance(node, ast.Subscript) else node.func.value if key is not None else None
                if isinstance(key, ast.Constant) and key.value == "transcripts" and isinstance(holder, ast.Name) and holder.id in loaded:
                    violations.append(f"CENSUS_READER_BYPASS {rel}:{node.lineno} ({name}): {holder.id}['transcripts'] is a census "
                                      "document's rows taken around census.rows")
    violations += [f"CENSUS_READER_BYPASS {rel} ({name}) names the census file outside the census, and no exception lists it"
                   for rel, name in sorted(sites - set(READER_EXCEPTIONS))]
    violations += [f"CENSUS_READER_BYPASS stale exception {rel} ({name}): it no longer names the census file"
                   for rel, name in sorted(set(READER_EXCEPTIONS) - sites) if rel in texts]
    return violations, sites


def reader_texts():
    """The sources `reader_bypasses` judges: every module of `READER_MODULES` but this one."""
    found = {}
    for pattern in READER_MODULES:
        for path in sorted(HERE.glob(pattern)):
            rel = path.relative_to(HERE).as_posix()
            if rel != "runlib/census.py":
                found[rel] = path.read_text(encoding="utf-8")
    return found


def blank(host, ident, source, path=None, **fields):
    """A row as the census builds it: its files in `segments` whatever the host, until `finish` gives it its shape."""
    entry = {"host": host, "id": ident, "source": source, "status": "eligible", "reason": None,
             "parent": None, "originator": None, "entrypoint": None, "source_class": None,
             "lineage": {"component": None, "root": None, "unique_root": False, "affirmed": [], "measurement_pending": False},
             "provenance": None, "counted": False, "window_overlap": None, "pin": {"content_ref": None},
             "segments": [segment(stem_of(path) if host == "codex" else None, source, path)] if path else [], "alt_paths": []}
    entry.update(fields)
    return entry


def finish(entry):
    """A built row in the shape the census document holds: a Claude row's one file moved onto the row, a Codex row's
    files left in `segments`."""
    if entry["host"] == "claude":
        files = entry.pop("segments")
        entry.update({k: (files[0] if files else segment(None, entry["source"]))[k] for k in SEGMENT_FIELDS})
    return entry


def name_id(path):
    """The session id a rollout's file name carries, for the one whose first record cannot be read."""
    stem = os.path.basename(path)
    found = UUID.findall(stem)
    return found[-1] if found else re.sub(r"\.(zst|jsonl)", "", stem)


def parse(text):
    try:
        when = datetime.datetime.fromisoformat(text)
        return when if when.tzinfo else when.replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def head_of(file, zstd):
    """A transcript's head: its scan, its first timestamp, and the error that stopped the read."""
    claude = file["host"] == "claude"
    scan, first_ts, error = (lineage.ClaudeScan() if claude else lineage.CodexScan(file["stem"])), None, None
    try:
        with contextlib.closing(sources.read_lines(file["path"], zstd)) as lines:
            for index, raw in enumerate(lines):
                try:
                    rec = json.loads(raw)
                except ValueError:
                    rec = None
                if isinstance(rec, dict):
                    scan.feed(rec, index)
                    first_ts = first_ts or (rec["timestamp"] if isinstance(rec.get("timestamp"), str) else None)
                if claude:
                    if (index + 1 >= HEAD_RECORDS and scan.entrypoint) or index + 1 >= ENTRYPOINT_SCAN:
                        break
                elif index + 1 >= HEAD_RECORDS or (index == 0 and (
                        scan.meta is None or scan.kind()[0] == "subagent" or scan.meta.get("source") not in ("cli", "vscode"))):
                    break  # a child or an automated rollout is known by its first record
    except sources.Unreadable as exc:
        error = str(exc)
    return {"scan": scan, "first_ts": first_ts, "error": error}


def read_full(file, zstd, scan, own, prev, earlier=()):
    """One pass over a whole transcript: `{sha, record_count, prefix_sha, prefix_ok, partial_tail, owned, before, after,
    late}`.

    The version this run reads is the transcript's complete lines (D-20261103-8facee): `sha` and `prefix_sha` both
    hash them, and a record the host is still writing is no record yet, so it moves neither (`partial_tail` says it was
    there). S2 copies exactly these `record_count` lines and accepts them when they hash to `sha`; what the host
    appends after this read belongs to the next run. `prefix_ok` answers §5.2's append-only test against `prev`, the
    version on record: did the first `prev.record_count` lines hash to its `prefix_sha`. Of the windows of `earlier`
    (`(start, end, id)`, the windows already run), `late` maps each to the records it owns past `prev.record_count` in
    an append - what was written after that window was read (review c0fix r1 #1) - and `unowned` to the records it owns
    in a version with no earlier one to be owed through: a file never read before, or one rewritten since. Those are
    owned by no run, and the census counts them."""
    whole, count, boundary, tail = hashlib.sha256(), 0, None, b""
    owners = coverage.Owners(earlier) if earlier else None
    if prev and prev["record_count"] == 0:
        boundary = whole.hexdigest()
    for raw in sources.read_lines(file["path"], zstd):
        if not raw.endswith(b"\n"):
            tail = raw
            break
        whole.update(raw)
        try:
            rec = json.loads(raw)
        except ValueError:
            rec = None
        if isinstance(rec, dict):
            scan.feed(rec, count)
            own.feed(count, rec.get("timestamp"))
            if owners:
                owners.feed(count, rec.get("timestamp"))
        count += 1
        if prev and count == prev["record_count"]:
            boundary = whole.hexdigest()
    prefix = whole.hexdigest()
    prefix_ok = None if prev is None else boundary == prev["prefix_sha"]
    earlier_owned = owners.finish(count) if owners else {}
    appended = {window: coverage.subtract(ranges, [[0, prev["record_count"]]]) for window, ranges in earlier_owned.items()} if prefix_ok else {}
    return {"sha": prefix, "record_count": count, "prefix_sha": prefix, "partial_tail": bool(tail), "prefix_ok": prefix_ok,
            "late": {w: r for w, r in appended.items() if r}, "unowned": {} if prefix_ok else earlier_owned, **own.finish(count)}


class _NoScan:
    """`read_full`'s scan for a unit member: its records are the root's evidence, not lineage of their own (§5.1)."""

    def feed(self, rec, index=0):
        pass


NO_SCAN = _NoScan()


def overlap_of(got):
    """How a read transcript lies against the window: inside it, across its start, its end or both, or only as context."""
    if not got["owned"]:
        return "context_only"
    return {(False, False): "inside", (True, False): "straddles_start", (False, True): "straddles_end",
            (True, True): "straddles_both"}[(bool(got["before"]), bool(got["after"]))]


def unread_overlap(entry, zstd, start, end):
    """How a row the census does not read in full lies against the window (lead decision D-20261106-208882), from the
    best evidence each of its files gives. A file last written before the window starts holds none of its records,
    since a record is written no earlier than its timestamp: the file-time bound, `before_window` when it decides every
    file. A file it cannot rule out has its record timestamps read to the end, as `read_full` reads them (complete
    lines only), and lies inside, across or outside the window by them (`overlap_of`). A file named with no path, one
    that cannot be read and one with no timestamped record leave the row `undetermined`, and so in the basis's scope.

    The bound fails only where a record's timestamp is later than its writing (a skewed clock) or a file's time was set
    back by hand; both are outside what the census can see, and a file the bound cannot decide is read."""
    sides, decided_by_time = {"owned": False, "before": False, "after": False}, True
    for seg in entry["segments"]:
        path = seg["path"]
        try:
            if path is None:
                return "undetermined"
            if os.stat(path).st_mtime < start.timestamp():
                sides["before"] = True  # every record of it lies before the window
                continue
            own, count = coverage.Ownership(start, end), 0
            for raw in sources.read_lines(path, zstd):
                if not raw.endswith(b"\n"):
                    break
                try:
                    rec = json.loads(raw)
                except ValueError:
                    rec = None
                if isinstance(rec, dict):
                    own.feed(count, rec.get("timestamp"))
                count += 1
        except (OSError, sources.Unreadable):
            return "undetermined"
        if not own.stamped:
            return "undetermined"
        decided_by_time = False
        got = own.finish(count)
        for side in sides:
            sides[side] = sides[side] or bool(got[side])
    return "before_window" if decided_by_time else overlap_of(sides)


def root_of(by_key, entry):
    """The root `entry`'s chain of parents reaches in `by_key` (`{<host>:<id>: entry}`): the first ancestor that names
    no parent, `entry` itself when it names none, or None when the chain breaks or loops. The chain is the parent links,
    not the statuses: a member whose own read failed keeps its parent and stays a link, so what lies below it is still
    in its root's unit (review c0fix r1 #2)."""
    seen = set()
    while entry is not None and entry.get("parent") is not None:
        if key_of(entry) in seen:
            return None
        seen.add(key_of(entry))
        entry = by_key.get(lineage.identity(entry["host"], entry["parent"]))
    return entry


def units_of(by_key):
    """`{root key: [member keys]}`: every `child_of` entry of `by_key` under the root its chain reaches, at any depth
    (D-20261103-85f3e8). A member that could not be read is no member, and its descendants still are. The members are
    sorted, so a unit reads the same in every run."""
    found = {}
    for key, entry in by_key.items():
        root = root_of(by_key, entry) if entry["status"] == "child_of" else None
        if root is not None:
            found.setdefault(key_of(root), []).append(key)
    return {root: sorted(members) for root, members in found.items()}


def units(transcripts):
    """`units_of` over a census document's transcripts: the one reader of the unit that reconcile and S2 share."""
    return units_of({key_of(e): e for e in transcripts})


def load_index(src, report, name, loader):
    """What `loader` reads from the index `name`, or None; the report says whether it was read, and why not."""
    rep = report[name]
    if rep["state"] != "present":
        return None
    try:
        return loader(src[name])
    except sources.Unreadable as exc:
        rep["state"], rep["detail"] = "unreadable", str(exc)
        return None


def discover(src, report):
    files = []
    if report["claude_projects"]["state"] == "present":
        top, children, report["claude_projects"]["unrecognized"] = sources.discover_claude(src["claude_projects"])
        files += [{"host": "claude", "source": "claude_projects", "path": p, "stem": i, "child_of": None} for i, p in top]
        files += [{"host": "claude", "source": "claude_projects", "path": p, "stem": os.path.basename(p)[:-len(".jsonl")],
                   "child_of": parent} for parent, p in children]
    for name in ("codex_sessions", "codex_archived_sessions"):
        if report[name]["state"] == "present":
            found, report[name]["unrecognized"] = sources.discover_codex(src[name])
            files += [{"host": "codex", "source": name, "path": p, "stem": os.path.basename(p), "child_of": None} for p in found]
    return files


def entry_of(file, head, pins, table):
    """The first classification of one transcript file, from its head alone (design §5.1)."""
    host = file["host"]
    if file["child_of"]:  # a Claude subagent file: linked to its session, read as part of it, never counted
        return blank(host, f"{file['child_of']}/{file['stem']}", file["source"], file["path"], status="child_of",
                     parent=file["child_of"], entrypoint="subagents")
    scan = head["scan"]
    ident = file["stem"] if host == "claude" else (scan.meta or {}).get("id") or name_id(file["path"])
    entry = blank(host, ident, file["source"], file["path"])
    if head["error"]:
        entry.update(status="unreadable", reason=head["error"])
    elif host == "claude":
        if scan.child():  # a sidechain thread wherever it lies on disk; its records carry the parent's session id
            parent = scan.session_id if scan.session_id and scan.session_id != ident else None
            entry.update(entrypoint="sidechain", **({"status": "child_of", "parent": parent} if parent else
                                                    {"status": "unknown_provenance", "reason": "child_without_parent"}))
        else:
            status, reason, cls = lineage.classify_claude(scan.entrypoint)
            entry.update(status=status, reason=reason, source_class=cls, entrypoint=scan.entrypoint)
    else:
        meta, (kind, parent) = scan.meta, scan.kind()
        source = meta.get("source") if meta else None
        entry.update(originator=meta.get("originator") if meta else None,
                     entrypoint=source if isinstance(source, str) else "subagent" if kind == "subagent" else None)
        sub = meta.get("source", {}).get("subagent") if meta and isinstance(meta.get("source"), dict) else None
        if meta is None:
            entry.update(status="unknown_provenance", reason="no_session_meta")
        elif isinstance(sub, dict) and sub.get("other") == "guardian":
            # Codex's own automatic risk review of a session's actions (D-20261103-b1989d): automated like `exec`, never a unit member
            entry.update(status="excluded", reason="guardian")
        elif kind == "subagent":
            entry.update(status="child_of", parent=parent) if parent else entry.update(status="unknown_provenance", reason="child_without_parent")
        else:
            status, reason, cls = lineage.classify_codex(source, entry["originator"], ("codex", ident) in pins, table)
            entry.update(status=status, reason=reason, source_class=cls)
    entry["pin"]["content_ref"] = pins.get((host, ident))
    return entry


def provenance_of(entry, host, threads, history, desktop):
    """`indexed`, `not_indexed` or `index_missing` from the index the host itself writes (design §5.3).

    Codex: a `threads` row of this id whose `rollout_path` is one of the row's files - any segment of a thread
    written across several, or a true copy of one (`alt_paths`) - or such a file before in-place compression (the index
    keeps the pre-compression path). Claude CLI: a `history.jsonl` entry with the id. Claude Desktop: a session-index file
    whose `cliSessionId` is the id."""
    if host == "codex":
        if threads is None:
            return "index_missing"
        row = threads.get(entry["id"])
        if not row or not row["rollout_path"]:
            return "not_indexed"
        have = os.path.realpath(row["rollout_path"])
        wanted = [os.path.realpath(p) for p in [s["path"] for s in entry["segments"] if s["path"]] + entry["alt_paths"]]
        return "indexed" if any(have in (want, want[:-len(".zst")] if want.endswith(".zst") else want) for want in wanted) else "not_indexed"
    index = desktop if entry["entrypoint"] == "claude-desktop" else history
    return "index_missing" if index is None else "indexed" if entry["id"] in index else "not_indexed"


def index_only(seen, threads, history, desktop, pins, table, start, end):
    """Identities an index names with a timestamp in the window and no transcript here (design §5.1);
    `seen` holds the identities (`<host>:<id>`) of the transcripts that are here."""
    lo, hi, found = start.timestamp(), end.timestamp(), []
    for sid, row in sorted((desktop or {}).items()):
        if lineage.identity("claude", sid) not in seen and row[0] is not None and row[0] / 1000 < hi and (row[1] or row[0]) / 1000 >= lo:
            found.append(blank("claude", sid, "claude_desktop_index", status="known_absent", source_class="claude-desktop", entrypoint="claude-desktop"))
            seen.add(lineage.identity("claude", sid))
    for sid, span in sorted((history or {}).items()):
        if lineage.identity("claude", sid) not in seen and span[0] is not None and span[0] / 1000 < hi and span[1] / 1000 >= lo:
            found.append(blank("claude", sid, "claude_history", status="known_absent", source_class="claude-cli", entrypoint="cli"))
            seen.add(lineage.identity("claude", sid))
    for sid, row in sorted((threads or {}).items()):
        if lineage.identity("codex", sid) in seen or row["created_at"] is None or not (row["created_at"] < hi and (row["updated_at"] or row["created_at"]) >= lo):
            continue
        raw = row["source"]
        source = "subagent" if isinstance(raw, str) and raw.startswith("{") else raw
        status, reason, cls = ("excluded", "subagent", None) if source == "subagent" else \
            lineage.classify_codex(source, row["originator"], ("codex", sid) in pins, table)
        found.append(blank("codex", sid, "codex_state", status="known_absent" if status == "eligible" else status, reason=reason, source_class=cls,
                           entrypoint=source, originator=row["originator"], pin={"content_ref": pins.get(("codex", sid))}))
        seen.add(lineage.identity("codex", sid))
    return found


def build(run, base, table, table_sha, jobs=8, scratch=None):
    """The census of one run: `(census, coverage state after the run)`; `base` is not touched.

    A targeted run reads but never advances periodic coverage, so what it returns is `base`. `scratch` is
    the confined parent under which the Codex index snapshot gets a directory of its own while it is read."""
    src = sources.declared(run)
    zstd = src.get("zstd")
    start, end, window_id = coverage.window_bounds(run["window"])
    state = copy.deepcopy(base)
    report = {name: {"state": sources.state_of(src.get(name), name in DIRECTORIES), "path": src.get(name), "discovered": None,
                     "unrecognized": 0, "totals": None, "detail": None} for name in sources.SOURCE_NAMES if name != "zstd"}
    files = discover(src, report)
    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:  # before the indexes are loaded: spawning is cheapest from a small heap
        heads = list(pool.map(lambda f: None if f["child_of"] else head_of(f, zstd), files))
    # The ROLLOUT lookup, in which a Codex key is a rollout id some pin names and never a thread id, so
    # a pin cannot answer for a rollout it does not name (X r2 F3).
    pins, bad, claimed, _threads = (sources.read_pins(src["agent_bios_state"])
                                    if report["agent_bios_state"]["state"] == "present" else ({}, 0, {}, {}))
    # A rollout two pins claim is keyed to neither (X r1 F5): the census makes no choice by file order,
    # and the ambiguity is reported here so a reader sees it rather than a missing pin.
    detail = [f"{bad} pin files ignored"] if bad else []
    detail += [f"{len(claimed)} rollout(s) claimed by more than one pin: "
               + "; ".join(f"{rollout}={','.join(ids)}" for rollout, ids in sorted(claimed.items()))] if claimed else []
    report["agent_bios_state"]["detail"] = "; ".join(detail) or None
    threads = load_index(src, report, "codex_state", functools.partial(sources.read_threads, scratch=scratch))
    history = load_index(src, report, "claude_history", sources.read_history)
    desktop = load_index(src, report, "claude_desktop_index", sources.read_desktop_index)
    if history is not None:
        history, bad = history
        report["claude_history"]["detail"] = f"{bad} lines ignored" if bad else None

    entries, extras = {}, {}
    for file, head in zip(files, heads):
        entry = entry_of(file, head, pins, table)
        ident = key_of(entry)
        if ident not in entries:
            entries[ident], extras[ident] = entry, {"file": file, "head": head, "files": [file]}
            continue
        have, stem = entries[ident], entry["segments"][0]["stem"]
        if entry["host"] == "claude" or any(s["stem"] == stem for s in have["segments"]):
            have["alt_paths"].append(file["path"])  # the same file found twice: the first keeps it, the copy is named beside it
            continue
        # one Codex thread written across several rollout files under one id (D-20261103-a7128a): one row, a segment per
        # file in name order, which is the order the host wrote them in; the row is classified from its first file
        files_now = sorted(extras[ident]["files"] + [file], key=lambda f: stem_of(f["path"]))
        if files_now[0] is file:
            entry["segments"], entry["alt_paths"] = have["segments"] + entry["segments"], have["alt_paths"]
            entries[ident], extras[ident]["file"], extras[ident]["head"] = entry, file, head
        else:
            have["segments"] = have["segments"] + entry["segments"]
        entries[ident]["segments"].sort(key=lambda s: s["stem"])
        extras[ident]["files"] = files_now
    discovered = {}  # the identities each source named, counted before anything else is decided about them
    for entry in entries.values():
        discovered[entry["source"]] = discovered.get(entry["source"], 0) + 1
    for ident, entry in entries.items():
        if entry["status"] == "child_of" and lineage.identity(entry["host"], entry["parent"]) not in entries:
            entry.update(status="unknown_provenance", reason="orphan_child", parent=None)  # a link to nothing
        elif entry["status"] not in ("child_of", "unreadable"):
            entry["provenance"] = provenance_of(entry, entry["host"], threads, history, desktop)

    for ident, entry in entries.items():
        if entry["status"] == "child_of" and root_of(entries, entry) is None:  # parents that loop reach no root: a link to nothing
            entry.update(status="unknown_provenance", reason="orphan_child", parent=None)

    # every eligible transcript is read in full, whatever its age: its sha, its continuity against the version on
    # record, the records the window owns, and the lineage evidence wherever in the file it lies
    owed = {b["transcript"] for b in state["backlog"]} | {e["transcript"] for e in state["pending_events"]}
    # a file of a row the coverage state owes work on and that is no longer here: the session cannot be read in full, so
    # its row says which file it lacks, and the work stays owed (the file is listed with no path)
    present = {coverage_key(e, s) for e in entries.values() for s in e["segments"]}
    for key in sorted(k for k in owed - present if identity_of_key(k) in entries and "@" in k):
        entry = entries[identity_of_key(key)]
        entry["segments"] = sorted(entry["segments"] + [segment(key.split("@", 1)[1], "coverage_state")], key=lambda s: s["stem"])
        entry.update(status="unreadable", reason=f"SEGMENT_ABSENT {key}: the coverage state owes work on this file of the "
                                                 "session and it is no longer here")

    # the windows already run, whose records appended since their run are owed to them (review c0fix r1 #1); what the
    # windows own in a file never read before or in a rewritten version is owed through no version, and is counted
    earlier = [(*coverage.bounds_of(w), w) for w in sorted(state["windows"]) if w != window_id]
    unowned = {"earlier_windows": len(earlier), "rewritten": {"files": 0, "records": 0}, "first_seen": {"files": 0, "records": 0}}

    def read(ident, scanned=True):
        """Every file of row `ident` read in full: `(scan, [(segment, got)], stamped records, error)`. The scan is the
        first file's - its kind and its pointer are the row's - with the lineage evidence of the later files added; a
        later file's own `history_base` is no edge (D-20261103-a7128a)."""
        entry, row_scan, out, stamped = entries[ident], None, [], 0
        for seg, file in zip(entry["segments"], extras[ident]["files"]):
            scan = (lineage.ClaudeScan() if file["host"] == "claude" else lineage.CodexScan(file["stem"])) if scanned else NO_SCAN
            own = coverage.Ownership(start, end)
            try:
                got = read_full(file, zstd, scan, own, coverage.latest(state, coverage_key(entry, seg)), earlier)
            except sources.Unreadable as exc:
                return None, [], 0, str(exc)
            if scanned:
                row_scan = scan if row_scan is None else row_scan.absorb(scan)
            out.append((seg, got))
            stamped += own.stamped
        return row_scan, out, stamped, None

    def taken(entry, out):
        for seg, got in out:
            if coverage.observe(state, coverage_key(entry, seg), got["sha"], got["record_count"], got["prefix_sha"], got["prefix_ok"]) == "append":
                coverage.carry_appended(state, coverage_key(entry, seg), got["late"])
            nobody = coverage.normalize([r for ranges in got["unowned"].values() for r in ranges])
            if nobody:
                cell = unowned["first_seen" if got["prefix_ok"] is None else "rewritten"]
                cell["files"], cell["records"] = cell["files"] + 1, cell["records"] + sum(end - start for start, end in nobody)
            seg.update(sha256=got["sha"], owned=got["owned"])
        entry["window_overlap"] = overlap_of({side: any(got[side] for _seg, got in out) for side in ("owned", "before", "after")})

    def unstamped(out, stamped):
        return stamped == 0 and any(got["record_count"] for _seg, got in out)

    for ident, entry in entries.items():
        if entry["status"] != "eligible":
            continue
        scan, out, stamped, error = read(ident)  # one at a time: decompression runs beside it in zstd, and CPU-bound threads only fight for the GIL
        if error:
            entry.update(status="unreadable", reason=error)
        elif unstamped(out, stamped):
            entry.update(status="unknown_provenance", reason="no_timestamps", source_class=None)
        else:
            extras[ident]["head"]["scan"] = scan
            taken(entry, out)

    # The unit S1 judges and S2 reads is a root with all its descendants, at any depth (D-20261103-85f3e8; design §5.1:
    # a child is "read as part of the parent's evidence"). Every member of a root still eligible after its own read is
    # read in full like the root, so what the window owns in it is known. A member that cannot be read, or carries no
    # timestamp, is named the way a root would be and leaves the unit; the rest of the unit is judged without it.
    unit_members = units_of(entries)
    for root, members in unit_members.items():
        if entries[root]["status"] != "eligible":
            continue
        for ident in members:
            entry = entries[ident]
            _scan, out, stamped, error = read(ident, scanned=False)
            if error:
                entry.update(status="unreadable", reason=error)
                continue
            if unstamped(out, stamped):
                entry.update(status="unknown_provenance", reason="no_timestamps")
                continue
            taken(entry, out)

    # A row left unread - unknown, unreadable, or a member of such a root - still lies somewhere against the window, and
    # the observation basis counts it only when it may hold a record of it (D-20261106-208882; stage_read.observation_scope).
    # A member of an excluded root is out of every scope with its root, so it is not looked at.
    for ident, entry in entries.items():
        if entry["window_overlap"] is not None:
            continue
        root = root_of(entries, entry) if entry["status"] == "child_of" else None
        if entry["status"] in UNREAD_STATUSES or (root is not None and root["status"] in UNREAD_STATUSES):
            entry["window_overlap"] = unread_overlap(entry, zstd, start, end)

    def owes(entry):
        return any(s["work"]["in_window"] or s["work"]["backlog"] for s in entry["segments"])

    def worked(entry):
        for seg in entry["segments"]:
            key = coverage_key(entry, seg)
            seg["work"] = coverage.work_of(state, key, seg["owned"], window_id)
            known = state["transcripts"].get(key, {"versions": []})["versions"]
            seg["versions"] = [{k: v[k] for k in ("sha", "record_count", "prefix_sha")} for v in known]
            seg["sha256"] = seg["sha256"] or (known[-1]["sha"] if known else None)

    for ident, entry in entries.items():
        if entry["status"] != "eligible":
            continue
        worked(entry)
        read_members = [m for m in unit_members.get(ident, []) if entries[m]["status"] == "child_of"]
        for member in read_members:
            worked(entries[member])
        # nothing is new for the unit only when neither the root nor any member owes the window anything
        if not owes(entry) and not any(owes(entries[m]) for m in read_members):
            entry["status"] = "nothing_new"

    # lineage over the owner's transcripts, then the counting rule (design §5.3); a component is active in the window
    # when any unit in it owns a record of the window, a member's as much as a root's
    def owns(entry):
        return any(s["owned"] for s in entry["segments"])

    mine = {i: e for i, e in entries.items() if e["status"] in ("eligible", "nothing_new")}
    nodes = [extras[i]["head"]["scan"].lineage_node(e["id"]) for i, e in mine.items()]
    linked, pending, active = lineage.components(nodes), {n["id"]: n.get("pending", False) for n in nodes}, {}
    for ident, entry in mine.items():
        entry["lineage"] = {**linked[ident], "measurement_pending": pending[ident]}
        unit_owned = owns(entry) or any(owns(entries[m]) for m in unit_members.get(ident, []) if entries[m]["status"] == "child_of")
        active[entry["lineage"]["component"]] = active.get(entry["lineage"]["component"], False) or unit_owned
    for ident, entry in mine.items():
        lin = entry["lineage"]
        entry["counted"] = bool(lin["unique_root"] and lin["root"] == ident and entry["provenance"] == "indexed"
                                and active[lin["component"]] and entry["source_class"] in CLASSES)
    named = index_only(set(entries), threads, history, desktop, pins, table, start, end)
    # work the coverage state still owes on a transcript that is no longer here is a lost transcript, not a vanished obligation
    present = {coverage_key(e, s) for e in entries.values() for s in e["segments"]}
    lost_keys = sorted(k for k in owed - present if identity_of_key(k) not in {key_of(e) for e in named})
    lost = []
    for ident in sorted({identity_of_key(k) for k in lost_keys}):
        row = blank(*lineage.split_identity(ident), "coverage_state", status="known_absent", reason="owed_by_coverage")
        if row["host"] == "codex":
            row["segments"] = [segment(k.split("@", 1)[1], "coverage_state") for k in lost_keys if identity_of_key(k) == ident and "@" in k]
        lost.append(row)
    if lost:
        report["coverage_state"] = {"state": "present", "path": None, "discovered": None, "unrecognized": 0, "totals": None,
                                    "detail": "transcripts the coverage state owes work on that are no longer here"}
    for entry in named + lost:
        discovered[entry["source"]] = discovered.get(entry["source"], 0) + 1
    everything = [finish(e) for e in list(entries.values()) + named + lost]
    for name, rep in report.items():
        if rep["state"] == "present" and name != "agent_bios_state":
            rep["discovered"] = discovered.get(name, 0)
    census = summarize(everything, report, run["kind"], window_id, table, table_sha, state, unowned)
    return census, (state if run["kind"] == "periodic" else base)


def totals_of(entries, report):
    for name, rep in report.items():
        if rep["state"] == "present" and name != "agent_bios_state":
            rep["totals"] = {}
            for e in entries:
                if e["source"] == name:
                    rep["totals"][e["status"]] = rep["totals"].get(e["status"], 0) + 1


def summarize(entries, report, kind, window_id, table, table_sha, state, unowned):
    """Fold per-transcript entries into the census document and check that nothing was dropped."""
    totals_of(entries, report)
    entries.sort(key=lambda e: (e["source"], first_path(e) or "", e["id"]))
    originators, provenance, pins, components = {}, {}, {}, {}
    for e in entries:
        if e["originator"] is not None and e["entrypoint"] == "vscode" and first_path(e):
            cell = originators.setdefault(e["originator"], {"count": 0, "class": table.get(e["originator"], "unmapped")})
            cell["count"] += 1
        if e["provenance"]:
            cell = provenance.setdefault(f"{e['host']}/{e['entrypoint'] or 'none'}",
                                         {"indexed": 0, "not_indexed": 0, "index_missing": 0})
            cell[e["provenance"]] += 1
        if e["status"] in ("eligible", "nothing_new"):
            cell = pins.setdefault(e["source"], {"eligible": 0, "pinned": 0})
            cell["eligible"] += 1
            cell["pinned"] += e["pin"]["content_ref"] is not None
        if e["lineage"]["component"]:
            components.setdefault(e["lineage"]["component"], []).append(e)
    unknown = [c for c, members in components.items() if not (members[0]["lineage"]["unique_root"] and any(
        key_of(m) == m["lineage"]["root"] and m["provenance"] == "indexed" for m in members))]
    census = {"kind": kind, "window": window_id, "originator_table_sha256": table_sha, "sources": report,
              "originators": originators, "provenance": provenance, "pins": pins,
              "independence": {"components": len(components), "unknown_components": len(unknown),
                               "sessions": sum(map(len, components.values())),
                               "unknown_sessions": sum(len(components[c]) for c in unknown)},
              "unowned": unowned, "pending_events": copy.deepcopy(state["pending_events"]), "transcripts": entries}
    errors = account(census)
    if errors:
        raise Refused("\n".join(errors))
    return census


def first_path(e):
    """The path of a finished row's first file, or None."""
    return e["path"] if e["host"] == "claude" else (e["segments"][0]["path"] if e["segments"] else None)


def shape_errors(e):
    """Where a row departs from its host's shape: a Claude row holds its file's fields on the row and has no `segments`;
    a Codex row holds them only in `segments` (D-20261103-a7128a). The schema cannot say this - its lint admits no
    conditional keyword (validate.SUPPORTED_KEYWORDS) - so the census's own accounting does."""
    if e["host"] == "codex":
        on_row = [k for k in SEGMENT_FIELDS if k in e]
        if on_row or not isinstance(e.get("segments"), list):
            return [f"SET_MISMATCH shape {key_of(e)}: a Codex row holds its files in segments, "
                    + (f"never {on_row} on the row" if on_row else "and this one has none")]
        return []
    missing = [k for k in SEGMENT_FIELDS if k not in e]
    if missing or "segments" in e:
        return [f"SET_MISMATCH shape {key_of(e)}: a Claude row holds its file on the row, "
                + (f"and this one lacks {missing}" if missing else "never in segments")]
    return []


def account(census):
    """Violations of the set accounting of §5.1, empty when it holds: no identity appears twice, a source with
    no total files nothing under it, each source's statuses add up to the identities it discovered, and every row has
    its host's shape."""
    errors, seen = [], {}
    for e in census["transcripts"]:
        errors += shape_errors(e)
        seen.setdefault(key_of(e), []).append(e["source"])
    errors += [f"SET_MISMATCH id {i} appears {len(s)} times ({sorted(s)})" for i, s in sorted(seen.items()) if len(s) > 1]
    for name, rep in census["sources"].items():
        mine = [e for e in census["transcripts"] if e["source"] == name]
        if rep["totals"] is None:
            errors += [f"SET_MISMATCH {e['id']}: filed under {name}, which has no total ({rep['state']})" for e in mine]
        elif sum(rep["totals"].values()) != rep["discovered"] or len(mine) != rep["discovered"]:
            errors.append(f"SET_MISMATCH {name}: discovered {rep['discovered']}, statuses sum to {sum(rep['totals'].values())}, {len(mine)} entries")
    stray = sorted({e["source"] for e in census["transcripts"]} - set(census["sources"]))
    errors += [f"SET_MISMATCH entries are filed under {s}, which is not a source" for s in stray]
    return errors


def dump(census):
    """The census as JSON, one transcript to a line: a corpus of 60,000 rollouts is read with `grep`."""
    head = json.dumps({k: v for k, v in census.items() if k != "transcripts"}, indent=1, sort_keys=True, ensure_ascii=False)
    lines = ",\n".join("  " + json.dumps(e, sort_keys=True, ensure_ascii=False, separators=(",", ":")) for e in census["transcripts"])
    return head[:-2] + ',\n "transcripts": [\n' + lines + "\n ]\n}\n"


def reconcile(census, state, results, kind):
    """S3's `results` folded back: `(census, state, flags)` with the eligible statuses terminal.

    Every session that was `eligible` at S1 needs exactly one result, and a result names an eligible session
    (SET_MISMATCH otherwise, listing the sessions). A result answers the session's whole unit: the readings of its
    read members are credited to them (`coverage.apply_results`). The inputs are not touched, and the reconciled census
    must still conform to its schema. A reading names the file it read by its coverage key (`segments_of`) unless the
    session is one file."""
    census, window_id = copy.deepcopy(census), census["window"]
    waiting = {key_of(e): e for e in census["transcripts"] if e["status"] == "eligible"}
    # one result answers a unit (D-20261103-85f3e8): its members' readings are credited to them, and what they own is owed
    # the coverage state names files, not rows: a Codex thread's files each by its own key (D-20261103-a7128a), so a unit is
    # the files of its root and the files of its read members
    by_key, found = {key_of(e): e for e in census["transcripts"]}, units(census["transcripts"])
    files = {i: segments_of(e) for i, e in by_key.items() if i in waiting or e["status"] == "child_of"}
    members = {root: [m for m in found.get(root, []) if by_key[m]["status"] == "child_of" and any(s["sha256"] for s in files[m])]
               for root in waiting}
    got = [r["transcript"] for r in results]
    missing, extra = sorted(set(waiting) - set(got)), sorted(set(got) - set(waiting))
    repeated = sorted({i for i in got if got.count(i) > 1})
    if missing or extra or repeated:
        raise Refused(f"SET_MISMATCH S3 results do not match the eligible sessions: missing={missing} extra={extra} repeated={repeated}")
    unit_keys = {root: ([s["key"] for s in files[root]], [s["key"] for m in members[root] for s in files[m]]) for root in waiting}
    read = [s for root in waiting for s in files[root]] + [s for ms in members.values() for m in ms for s in files[m]]
    # a targeted run's results are held to the periodic rules against the state the census observed, and then discarded
    seen = state if kind == "periodic" else coverage.observed(state, read)
    owned = {s["key"]: s["owned"] for s in read}
    after = coverage.apply_results(seen, window_id, kind, results, owned, unit_keys)
    for result in results:
        waiting[result["transcript"]]["status"] = result["status"]
    totals_of(census["transcripts"], census["sources"])
    census["pending_events"] = copy.deepcopy(after["pending_events"])
    errors = account(census) + [f"CENSUS_INVALID {p}" for p in validate.validate_instance(validator(), census)[:5]]
    if errors:
        raise Refused("\n".join(errors))
    flags = dict(zip(("accounted", "fully_read"), coverage.accounted(census["transcripts"], after, window_id, unit_keys, owned)))
    if kind == "periodic":
        after["windows"][window_id] = flags
    else:
        errors = coverage.check_targeted(seen, after)
        if errors:
            raise Refused("\n".join(errors))
        after = copy.deepcopy(state)  # nothing of it is kept: periodic coverage stays what it was, byte for byte
    return census, after, flags


def window_counts(entries):
    """The eligible sessions, how many have a terminal status (accounted) and how many were read to the end
    or had nothing to read (fully read): reported apart, since a deferred session is the first and not the second."""
    eligible = [e["status"] for e in entries if e["status"] == "eligible" or e["status"] in coverage.TERMINAL]
    return {"eligible": len(eligible), "accounted": sum(s in coverage.TERMINAL for s in eligible),
            "fully_read": sum(s in ("read_complete", "nothing_new") for s in eligible)}


def run(run_dir, coverage_path=None, originators_path=None, jobs=8):
    """`distill.py census`: write `census.json` and the run's `coverage.json` into the run directory.

    The coverage state read is the one the declaration pinned (`starting_hashes.coverage`) and the originator
    table the one it declared (`bound_table`); the tracked file is not written here, S12 promotes the run's
    copy with `coverage.write_atomic`. The Codex index is read through a snapshot in a directory of its own, made fresh
    under `<run>/private` (confined first) and removed by the reader that made it, and nothing else."""
    run_dir = pathlib.Path(run_dir)
    if not records.run_json_path(run_dir).is_file():
        raise Refused(f"RUN_UNDECLARED {run_dir}: no run.json")
    declaration = records.read_json(records.run_json_path(run_dir))
    base, base_sha = coverage.load(coverage_path or HERE / "coverage.json")
    pinned = declaration["starting_hashes"]["coverage"]
    if pinned != base_sha:
        raise Refused(f"COVERAGE_BASE_STALE S1: the declaration pinned coverage {pinned[:12]}, the file hashes {base_sha[:12]}; "
                      "amend starting_hashes.coverage or restore the file")
    table, table_sha = bound_table(declaration, originators_path)
    parent = stagelock.confine(run_dir, run_dir / "private")  # resolved beneath the run before anything is created or read into it
    with records.run_stage(run_dir, "S1") as stage:
        # the declaration was read first so that a stale pin or table is refused before any record is written; what
        # builds the census is that read only if it is the declaration S1 was admitted against (X review of WP-08 r2)
        declaration = stage.admitted(declaration)
        parent.mkdir(exist_ok=True)
        census, state = build(declaration, base, table, table_sha, jobs, parent)
        problems = validate.validate_instance(validator(), census)
        if problems:
            raise Refused("CENSUS_INVALID " + "; ".join(problems[:5]))
        records.write_text(run_dir, run_dir / "census.json", dump(census))
        records.write_json(run_dir, run_dir / "coverage.json", state)
        stage.output("census.json")
        stage.output("coverage.json")
    return census


def report_lines(census):
    """The census as the few lines a person reads: counts per source, never a transcript's content."""
    def totals(rep):
        return "unknown (no total)" if rep["totals"] is None else ", ".join(f"{k} {v}" for k, v in sorted(rep["totals"].items())) or "empty"
    ind, counts = census["independence"], window_counts(census["transcripts"])
    return [f"census {census['kind']} window {census['window']}: {counts['eligible']} eligible, {counts['accounted']} accounted, "
            f"{counts['fully_read']} fully read",
            *[f"  {name}: {rep['state']}{' - ' + rep['detail'] if rep['detail'] else ''}; {totals(rep)}" for name, rep in sorted(census["sources"].items())],
            *[f"  provenance {key}: indexed {c['indexed']}, not_indexed {c['not_indexed']}, index_missing {c['index_missing']}"
              for key, c in sorted(census["provenance"].items())],
            *[f"  originator {name}: {c['count']} ({c['class']})" for name, c in sorted(census["originators"].items())],
            f"  independence: {ind['unknown_components']}/{ind['components']} components and {ind['unknown_sessions']}/{ind['sessions']} sessions unknown",
            f"  owned by no run, against {census['unowned']['earlier_windows']} windows already run: "
            + "; ".join(f"{cause} {c['files']} files {c['records']} records" for cause, c in (
                ("rewritten", census["unowned"]["rewritten"]), ("first seen", census["unowned"]["first_seen"])))]


def contract_mismatch(schema, statuses):
    """Where the census schema's status vocabulary departs from §5.1's list (`statuses`)."""
    have = schema["$defs"]["transcript"]["properties"]["status"]["enum"]
    errors = [f"CONTRACT_MISMATCH census (design §5.1): status {verb} {sorted(fields)}"
              for verb, fields in (("lacks", set(statuses) - set(have)), ("adds", set(have) - set(statuses))) if fields]
    if not str(schema.get("$comment", "")).startswith("design §5.1"):
        errors.append("CONTRACT_MISMATCH census (design §5.1): $comment does not cite the section")
    return errors


# ---- the self-test: a synthetic corpus, one fixture for each O1 plant of design §18, every one golden -----------------

REALIZATION = "golden"  # every fixture is synthetic: `Home` builds the host layout, `fx_*` the records (mock/realization boundary)
ZSTD = "/opt/homebrew/bin/zstd"
WINDOW = {"start": "2026-10-01T00:00:00", "end": "2026-10-08T00:00:00", "tz": "UTC"}
NEXT = {"start": "2026-10-08T00:00:00", "end": "2026-10-15T00:00:00", "tz": "UTC"}
NEXT_ID = "2026-10-08T00:00:00/2026-10-15T00:00:00@UTC"  # the id the state files NEXT under
STATUSES_5_1 = ("excluded", "child_of", "unknown_provenance", "unreadable", "known_absent", "eligible",
                "read_complete", "read_partial", "failed", "deferred", "nothing_new")  # design §5.1, copied once and cited


def fx_when(day, month=10, hour=0):
    return datetime.datetime(2026, month, day, hour, tzinfo=datetime.timezone.utc).timestamp()


def fx_stamp(day, k, month=10):
    """The k-th second after 10:00 on a day: a transcript of any length gets distinct, ordered timestamps."""
    return f"2026-{month:02d}-{day:02d}T{10 + k // 3600:02d}:{k // 60 % 60:02d}:{k % 60:02d}.000Z"


def fx_claude(sid, entry="cli", head="fresh", day=3, turns=3, uuids=None, stamps=None, entries=None, texts=None, side=None, month=10):
    """The records of a Claude Code session: a head, then alternating user and assistant records.
    A user record carries a text of its own unless `texts` gives it one; `side` is `(isSidechain, agentId)`."""
    rows = [{"type": t} for t in {"fresh": ["mode", "permission-mode", "atis-latch", "file-history-snapshot"],
                                  "fork": ["ai-title", "last-prompt", "file-history-snapshot", "file-history-snapshot"]}[head]]
    for k, stamp in enumerate(stamps or [fx_stamp(day, k, month) for k in range(turns * 2)]):
        ep = entries[k] if entries else entry
        text = texts[k // 2] if texts and k // 2 < len(texts) else f"{sid} question {k // 2}"
        rows.append({"type": "user" if k % 2 == 0 else "assistant", "timestamp": stamp, "sessionId": sid,
                     "uuid": uuids[k] if uuids and k < len(uuids) else f"{sid}-{k}", **({"entrypoint": ep} if ep else {}),
                     **({"message": {"role": "user", "content": text}} if k % 2 == 0 else {}),
                     **({"isSidechain": side[0], "agentId": side[1]} if side else {})})
    return rows


def fx_codex(tid, source="cli", originator="codex-tui", day=3, turns=3, ns=None, meta=None, compacted=False, ordinal=0, texts=None, month=10):
    """The records of a Codex rollout: session_meta, then a turn start and a user message for each turn."""
    at = lambda k: fx_stamp(day, k, month)  # noqa: E731
    rows = [{"timestamp": at(0), "ordinal": ordinal, "type": "session_meta",
             "payload": {"id": tid, "timestamp": at(0), "originator": originator, "source": source, **(meta or {})}}]
    for k in range(turns):
        text = texts[k] if texts and k < len(texts) else f"{tid} prompt {k}"
        rows.append({"timestamp": at(k + 1), "type": "event_msg", "payload": {"type": "task_started", "turn_id": f"{ns or tid}-t{k}"}})
        rows.append({"timestamp": at(k + 1), "type": "response_item", "payload": {
            "type": "message", "role": "user", "id": f"msg_{ns or tid}_{k}", "content": [{"type": "input_text", "text": text}]}})
    if compacted:
        rows.append({"timestamp": at(turns + 1), "type": "compacted", "payload": {}})
    return rows


class Home:
    """A host layout under a scratch directory: the transcripts, the three indexes, the pins."""

    open_writers = []  # the homes whose Codex database is held open by a writer; the self-test closes them

    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.projects = self.root / ".claude" / "projects"
        self.history_path = self.root / ".claude" / "history.jsonl"
        self.desktop_dir = self.root / "Library" / "claude-code-sessions"
        self.sessions = self.root / ".codex" / "sessions"
        self.archived = self.root / ".codex" / "archived_sessions"
        self.db = self.root / ".codex" / "state_5.sqlite"
        self.state = self.root / "agent-bios-state"
        self.hist, self.rows, self.desktops, self.writer = {}, [], 0, None
        for directory in (self.projects, self.desktop_dir, self.sessions, self.archived, self.state):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def put(path, rows, mtime=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in rows))
        os.utime(path, (mtime or fx_when(5), mtime or fx_when(5)))
        return path

    def claude(self, sid, rows, mtime=None, history=True):
        if history:
            self.hist[sid] = int(fx_when(3) * 1000)
        return self.put(self.projects / "-fx" / f"{sid}.jsonl", rows, mtime)

    def child(self, parent, name, rows):
        return self.put(self.projects / "-fx" / parent / "subagents" / f"{name}.jsonl", rows)

    def desktop(self, sid, created, last, listed=True):
        self.desktops += 1
        (self.desktop_dir / "a" / "b").mkdir(parents=True, exist_ok=True)
        (self.desktop_dir / "a" / "b" / f"local_{self.desktops}.json").write_text(json.dumps(
            {"sessionId": f"local_{self.desktops}", "cliSessionId": sid, "createdAt": int(fx_when(created) * 1000),
             "lastActivityAt": int(fx_when(last) * 1000), "title": "fixture"}))

    def codex(self, tid, rows, where="sessions", zst=False, indexed=True, source=None, mtime=None, raw=None, day=3, name_at=None):
        directory = self.sessions / "2026" / "10" / f"{day:02d}" if where == "sessions" else self.archived
        path = directory / f"rollout-{name_at or f'2026-10-{day:02d}T10-00-00'}-{tid}.jsonl"
        if raw is None:
            self.put(path, rows, mtime)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        if zst:
            subprocess.run([ZSTD, "-q", "-f", "--rm", str(path)], check=True)
            path = path.with_name(path.name + ".zst")
            os.utime(path, (mtime or fx_when(5), mtime or fx_when(5)))
        if indexed:
            first = rows[0]["payload"]
            self.rows.append((tid, str(path)[:-len(".zst")] if zst else str(path), first["source"], first["originator"],
                              int(fx_when(3)), int(fx_when(4)), 1 if where == "archived" else 0))
        return path

    def finish(self, corrupt=False, wal=False):
        """Write the indexes. With `wal` the host has the Codex database open: every row is committed to its write-ahead
        log, never checkpointed, and the connection stays open (`close`) so the `-wal` and `-shm` are there to be read."""
        self.history_path.write_text("".join(json.dumps({"sessionId": s, "timestamp": ms, "display": "fixture"}) + "\n"
                                             for s, ms in sorted(self.hist.items())))
        if corrupt:
            self.db.write_bytes(b"not a database" * 200)
            return
        conn = sqlite3.connect(self.db)
        if wal:
            conn.execute("pragma journal_mode=wal")
        conn.execute("create table threads(id text, rollout_path text, source text, originator text, created_at integer, "
                     "updated_at integer, archived integer)")
        conn.commit()
        if wal:
            conn.execute("pragma wal_checkpoint(truncate)")
            conn.execute("pragma wal_autocheckpoint=0")
        conn.executemany("insert into threads values(?,?,?,?,?,?,?)", self.rows)
        conn.commit()
        if wal:
            self.writer = conn
            Home.open_writers.append(self)
        else:
            conn.close()

    def close(self):
        writer, self.writer = self.writer, None
        if writer:
            writer.close()

    def host_bytes(self):
        """The Codex database, its -wal and its -shm: name, size, mtime and the hash of the bytes (absent ones omitted)."""
        out = []
        for suffix in ("", "-wal", "-shm"):
            path = pathlib.Path(str(self.db) + suffix)
            if path.exists():
                out.append((path.name, path.stat().st_size, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()))
        return out

    def pin(self, tid):
        """An activation pin as the current activation writes one: named by the app-server's thread id and
        NAMING the rollout the host wrote, which is the id a census row carries (F-22). Without the rollout
        fields the pin answers for no transcript, which is what every pin written before the binding is."""
        (self.state / "sessions" / "pins" / "codex").mkdir(parents=True, exist_ok=True)
        (self.state / "sessions" / "pins" / "codex" / f"{tid}.json").write_text(
            json.dumps({"host": "codex", "session_id": tid, "content_ref": "sha256:fixture",
                        "rollout_id": tid, "rollout_path": str(self.sessions / f"rollout-{tid}.jsonl"),
                        "rollout_method": "thread.path"}))

    def run(self, kind="periodic", window=WINDOW, drop=(), table=None, **paths):
        """A declaration's `kind`, `window` and `sources`; `table` is the `(path, sha256)` of the originator table it binds."""
        declared = {"claude_projects": self.projects, "claude_history": self.history_path, "claude_desktop_index": self.desktop_dir,
                    "codex_sessions": self.sessions, "codex_archived_sessions": self.archived, "codex_state": self.db,
                    "agent_bios_state": self.state, "zstd": ZSTD}
        declared.update(paths)
        path, sha = table or (ORIGINATORS_PATH, load_originators()[1])
        return {"kind": kind, "window": window, "sources": [{"name": n, "path": str(p)} for n, p in declared.items() if n not in drop]
                + [{"name": ORIGINATORS_SOURCE, "path": str(path), "sha256": sha}]}


def fx_get(entry, key):
    for part in key.split("."):
        entry = entry[part]
    return entry


def fx_view(e):
    """A row as the fixtures read it: a Codex row of one file, or of none, with that file's fields beside its own, so one
    expectation reads a row of either host alike. A row of several files is left as it is: what it holds per file is
    read through `segments_of`."""
    if e["host"] != "codex" or len(e["segments"]) > 1:
        return e
    seg = e["segments"][0] if e["segments"] else segment(None, e["source"])
    return {**e, **{k: seg[k] for k in SEGMENT_FIELDS}}


def fx_check(census, expected):
    """Violations of a fixture table `{name: (identity, {attribute: value})}`, each naming its fixture."""
    by_id, errors = {key_of(e): fx_view(e) for e in census["transcripts"]}, []
    for name, (ident, want) in sorted(expected.items()):
        got = by_id.get(ident)
        if got is None:
            errors.append(f"FIXTURE {name}: {ident} is not in the census")
            continue
        errors += [f"FIXTURE {name}: {key} is {fx_get(got, key)!r}, expected {value!r}" for key, value in want.items() if fx_get(got, key) != value]
    return errors


def fx_corpus(h):
    """Plant every fixture of design §18 O1 in `h` and return `{name: (id, expected attributes)}`."""
    C = lambda n: f"c{n:07d}-0000-4000-8000-000000000000"  # noqa: E731
    X = lambda n: f"019e{n:04d}-0000-7000-8000-000000000000"  # noqa: E731
    CK = lambda n: lineage.identity("claude", C(n))  # noqa: E731
    XK = lambda n: lineage.identity("codex", X(n))  # noqa: E731
    exp = {}

    def claude(name, n, rows, want, **kw):
        h.claude(C(n), rows, **kw)
        exp[name] = (CK(n), want)

    def codex(name, n, rows, want, **kw):
        h.codex(X(n), rows, **kw)
        exp[name] = (XK(n), want)

    counted = {"status": "eligible", "provenance": "indexed", "counted": True, "lineage.unique_root": True}
    claude("claude_cli_root", 1, fx_claude(C(1)), {**counted, "source_class": "claude-cli", "window_overlap": "inside", "owned": [[0, 10]],
                                                    "lineage.root": CK(1)})
    claude("claude_desktop_named", 2, fx_claude(C(2), entry="claude-desktop"), {**counted, "source_class": "claude-desktop"}, history=False)
    h.desktop(C(2), 2, 3)
    claude("claude_desktop_unindexed", 3, fx_claude(C(3), entry="claude-desktop"),
           {"status": "eligible", "source_class": "claude-desktop", "provenance": "not_indexed", "counted": False}, history=False)
    claude("claude_sdk", 4, fx_claude(C(4), entry="sdk-cli"), {"status": "excluded", "reason": "sdk-cli", "source_class": None}, history=False)
    claude("claude_no_entrypoint", 5, fx_claude(C(5), entry=None), {"status": "unknown_provenance", "reason": "no_entrypoint"}, history=False)
    claude("claude_resumed_headless", 6, fx_claude(C(6), entries=["cli", "cli", "sdk-cli", "sdk-cli", "sdk-cli", "sdk-cli"]),
           {**counted, "source_class": "claude-cli", "entrypoint": "cli"})
    h.child(C(1), "agent-a", fx_claude(C(1)))
    exp["claude_child"] = (lineage.identity("claude", f"{C(1)}/agent-a"), {"status": "child_of", "parent": C(1), "counted": False, "provenance": None})
    h.child(C(9), "agent-b", fx_claude(C(9)))
    exp["claude_orphan_child"] = (lineage.identity("claude", f"{C(9)}/agent-b"), {"status": "unknown_provenance", "reason": "orphan_child", "parent": None})
    claude("claude_fork", 7, fx_claude(C(7), head="fork", uuids=[f"{C(1)}-0", f"{C(1)}-1"]),
           {"status": "eligible", "counted": False, "provenance": "not_indexed", "lineage.unique_root": True, "lineage.root": CK(1),
            "lineage.affirmed": [{"from": CK(7), "to": CK(1), "via": ["record_ids"]}]}, history=False)
    shared = [f"{C(10)}-{k}" for k in range(6)]
    claude("claude_copy_original", 10, fx_claude(C(10), uuids=shared), {"status": "eligible", "provenance": "indexed", "counted": False,
                                                                       "lineage.unique_root": False, "lineage.root": None})
    claude("claude_copy_beside_original", 11, fx_claude(C(11), uuids=shared), {"status": "eligible", "provenance": "not_indexed",
                                                                              "counted": False, "lineage.unique_root": False}, history=False)
    claude("claude_lone_copy", 12, fx_claude(C(12)), {"status": "eligible", "provenance": "not_indexed", "counted": False,
                                                       "lineage.unique_root": True}, history=False)
    straddle = ["2026-09-30T10:00:00.000Z", "2026-09-30T10:01:00.000Z"] + [f"2026-10-02T10:0{k}:00.000Z" for k in range(4)]
    claude("claude_straddles_window_start", 13, fx_claude(C(13), stamps=straddle),
           {**counted, "window_overlap": "straddles_start", "owned": [[6, 10]]})
    old = [f"2026-09-01T10:0{k}:00.000Z" for k in range(4)]
    claude("claude_before_the_window", 14, fx_claude(C(14), stamps=old), {"status": "nothing_new", "window_overlap": "context_only",
                                                                       "owned": [], "counted": False}, mtime=fx_when(1, 9))

    claude("claude_continued_in", 15, fx_claude(C(15)) + [{"type": "continued-in", "continuedInSessionId": C(16)}], {**counted, "lineage.root": CK(15)})
    claude("claude_continuation_by_pointer", 16, fx_claude(C(16)), {"status": "eligible", "counted": False, "lineage.root": CK(15), "lineage.unique_root": True,
                                                                  "provenance": "not_indexed"}, history=False)

    dated = {"status": "eligible", "provenance": "indexed", "counted": True, "lineage.unique_root": True}
    codex("codex_cli", 1, fx_codex(X(1)), {**dated, "source_class": "codex-cli", "window_overlap": "inside",
                                           "alt_paths": [str(h.archived / f"rollout-2026-10-03T10-00-00-{X(1)}.jsonl")]})
    h.codex(X(1), fx_codex(X(1)), where="archived", indexed=False)  # the same id in a second file
    codex("codex_desktop_named", 2, fx_codex(X(2), "vscode", "Codex Desktop"), {**dated, "source_class": "codex-desktop", "originator": "Codex Desktop"})
    codex("codex_work_desktop", 3, fx_codex(X(3), "vscode", "codex_work_desktop"), {**dated, "source_class": "codex-desktop"})
    codex("codex_exec", 4, fx_codex(X(4), "exec", "codex_exec"), {"status": "excluded", "reason": "exec", "counted": False}, indexed=False)
    codex("codex_claude_code_in_vscode", 5, fx_codex(X(5), "vscode", "Claude Code"),
          {"status": "excluded", "reason": "originator:Claude Code", "provenance": "not_indexed"}, indexed=False)
    codex("codex_unnamed_originator", 6, fx_codex(X(6), "vscode", "NewClient"),
          {"status": "unknown_provenance", "reason": "originator:NewClient"}, indexed=False)
    codex("codex_activated_with_pin", 7, fx_codex(X(7), "vscode", "agent-bios"),
          {**dated, "source_class": "codex-cli", "pin.content_ref": "sha256:fixture"})
    h.pin(X(7))
    codex("codex_activated_without_pin", 8, fx_codex(X(8), "vscode", "agent-bios"),
          {"status": "unknown_provenance", "reason": "agent-bios:unpinned", "pin.content_ref": None}, indexed=False)
    codex("codex_child", 9, fx_codex(X(9), "cli", meta={"parent_thread_id": X(1)}), {"status": "child_of", "parent": X(1), "counted": False},
          indexed=False)
    codex("codex_compressed_in_place", 10, fx_codex(X(10), "vscode", "Codex Desktop"),
          {**dated, "source_class": "codex-desktop"}, zst=True)
    codex("codex_moved_to_archive", 11, fx_codex(X(11), "vscode", "Codex Desktop"), {**dated, "source_class": "codex-desktop"},
          where="archived", zst=True)
    codex("codex_lone_copy", 12, fx_codex(X(12), "vscode", "Codex Desktop"),
          {"status": "eligible", "provenance": "not_indexed", "counted": False, "lineage.unique_root": True}, indexed=False)
    codex("codex_fork", 13, fx_codex(X(13), "cli", meta={"forked_from_id": X(1)}, ordinal=5),
          {"status": "eligible", "counted": False, "lineage.root": XK(1), "lineage.unique_root": True,
           "lineage.affirmed": [{"from": XK(13), "to": XK(1), "via": ["forked_from_id"]}]})
    codex("codex_compaction", 14, fx_codex(X(14), compacted=True),
          {"status": "eligible", "counted": False, "lineage.unique_root": False, "lineage.measurement_pending": True})
    shared_ids = "copyns"
    codex("codex_copy_original", 15, fx_codex(X(15), ns=shared_ids), {"status": "eligible", "counted": False, "lineage.unique_root": False})
    codex("codex_copy_beside_original", 16, fx_codex(X(16), ns=shared_ids),
          {"status": "eligible", "counted": False, "lineage.unique_root": False, "provenance": "not_indexed"}, indexed=False)
    codex("codex_index_names_another_file", 18, fx_codex(X(18)), {"status": "eligible", "provenance": "not_indexed", "counted": False,
                                                                 "lineage.unique_root": True}, indexed=False)
    h.rows.append((X(18), "/elsewhere/rollout.jsonl", "cli", "codex-tui", int(fx_when(3)), int(fx_when(4)), 0))
    codex("codex_unreadable_rollout", 17, [], {"status": "unreadable", "counted": False}, raw=b"not zstd at all", zst=False, indexed=False)
    junk = h.sessions / "2026" / "10" / "03" / f"rollout-2026-10-03T10-00-00-{X(17)}.jsonl"
    junk.rename(junk.with_name(junk.name + ".zst"))

    # design §5.3's third link, an identical (timestamp, human text) turn, with no pointer and no shared record id
    claude("claude_turn_root", 30, fx_claude(C(30), texts=["shared plan"]), {**counted, "lineage.root": CK(30)})
    claude("claude_turn_replay", 31, fx_claude(C(31), head="fork", texts=["shared plan"]),
           {"status": "eligible", "counted": False, "provenance": "not_indexed", "lineage.unique_root": True, "lineage.root": CK(30),
            "lineage.affirmed": [{"from": CK(31), "to": CK(30), "via": ["timestamp_text"]}]}, history=False)
    claude("claude_same_text_other_time_root", 32, fx_claude(C(32), texts=["same words"]), {**counted})
    claude("claude_same_text_other_time_replay", 33, fx_claude(C(33), head="fork", day=4, texts=["same words"]),
           {"status": "eligible", "counted": False, "lineage.unique_root": False}, history=False)
    claude("claude_same_time_other_text_root", 34, fx_claude(C(34)), {**counted})
    claude("claude_same_time_other_text_replay", 35, fx_claude(C(35), head="fork"),
           {"status": "eligible", "counted": False, "lineage.unique_root": False}, history=False)
    codex("codex_turn_root", 30, fx_codex(X(30), texts=["codex shared plan"]), {**dated, "lineage.root": XK(30)})
    codex("codex_turn_replay", 31, fx_codex(X(31), meta={"history_base": {"thread_id": "gone"}}, ordinal=5, texts=["codex shared plan"]),
          {"status": "eligible", "counted": False, "lineage.unique_root": True, "lineage.root": XK(30),
           "lineage.affirmed": [{"from": XK(31), "to": XK(30), "via": ["timestamp_text"]}]}, indexed=False)
    codex("codex_same_text_other_time_root", 32, fx_codex(X(32), texts=["codex same words"]), {**dated})
    codex("codex_same_text_other_time_replay", 33, fx_codex(X(33), meta={"history_base": {"thread_id": "gone"}}, ordinal=5, day=4, texts=["codex same words"]),
          {"status": "eligible", "counted": False, "lineage.unique_root": False}, indexed=False)

    # a Claude child by its records (a sidechain thread, or one that names an agent), wherever the file lies; an ordinary session is not one
    claude("claude_sidechain_parent", 36, fx_claude(C(36)), {**counted})
    claude("claude_sidechain_child", 37, fx_claude(C(36), side=(True, "a1")),
           {"status": "child_of", "parent": C(36), "counted": False, "entrypoint": "sidechain", "provenance": None}, history=False)
    claude("claude_agentid_child", 38, fx_claude(C(36), side=(False, "a2")), {"status": "child_of", "parent": C(36), "counted": False}, history=False)
    claude("claude_sidechain_without_parent", 39, fx_claude(C(39), side=(True, "a3")),
           {"status": "unknown_provenance", "reason": "child_without_parent", "counted": False}, history=False)
    inline = {"type": "user", "timestamp": fx_stamp(3, 90), "sessionId": C(41), "isSidechain": True, "message": {"role": "user", "content": "inline side"}}
    claude("claude_inline_sidechain_is_no_child", 41, fx_claude(C(41), side=(False, None)) + [inline], {**counted})

    # lineage evidence past the first 256 records of an old transcript, where the head-only test never looks
    old = {"month": 9, "day": 1, "turns": 140}
    before = {"status": "nothing_new", "window_overlap": "context_only", "counted": True, "lineage.unique_root": True}
    claude("claude_old_continued_in_past_the_head", 42, fx_claude(C(42), **old) + [{"type": "continued-in", "continuedInSessionId": C(43)}],
           {**before, "lineage.root": CK(42)}, mtime=fx_when(1, 9))
    claude("claude_continuation_of_the_old_one", 43, fx_claude(C(43)),
           {"status": "eligible", "provenance": "indexed", "counted": False, "lineage.unique_root": True, "lineage.root": CK(42)})
    claude("claude_old_shares_an_id_past_the_head", 44, fx_claude(C(44), uuids=[None] * 270 + ["late-shared-uuid"], **old),
           {**before, "lineage.root": CK(44)}, mtime=fx_when(1, 9))
    claude("claude_fork_of_the_old_one", 45, fx_claude(C(45), head="fork", uuids=["late-shared-uuid"]),
           {"status": "eligible", "provenance": "not_indexed", "counted": False, "lineage.unique_root": True, "lineage.root": CK(44)}, history=False)
    late_texts = [f"{C(46)} question {k}" for k in range(140)]
    late_texts[135] = "late shared words"
    claude("claude_old_shares_a_turn_past_the_head", 46, fx_claude(C(46), texts=late_texts, **old), {**before, "lineage.root": CK(46)}, mtime=fx_when(1, 9))
    claude("claude_replay_of_the_old_turn", 47, fx_claude(C(47), head="fork", stamps=[fx_stamp(1, 270, 9)] + [fx_stamp(3, k) for k in range(1, 6)],
                                                          texts=["late shared words"]),
           {"status": "eligible", "provenance": "not_indexed", "counted": False, "window_overlap": "straddles_start",
            "lineage.unique_root": True, "lineage.root": CK(46)}, history=False)
    codex("codex_old_shares_a_turn_id_past_the_head", 34, fx_codex(X(34), month=9, day=1, turns=200),
          {**before, "lineage.root": XK(34)}, mtime=fx_when(1, 9))
    tail = {"timestamp": fx_stamp(3, 50), "type": "event_msg", "payload": {"type": "task_started", "turn_id": f"{X(34)}-t190"}}
    codex("codex_continuation_of_the_old_one", 35, fx_codex(X(35), meta={"history_base": {"thread_id": "gone"}}, ordinal=5) + [tail],
          {"status": "eligible", "counted": False, "lineage.unique_root": True, "lineage.root": XK(34)}, indexed=False)

    # the remaining pointers of §5.3: a Codex history_base to a session that is here, and a thread_spawn child
    codex("codex_history_base_root", 36, fx_codex(X(36)), {**dated, "lineage.root": XK(36)})
    codex("codex_history_base_continuation", 37, fx_codex(X(37), meta={"history_base": {"thread_id": X(36)}}, ordinal=5),
          {"status": "eligible", "counted": False, "lineage.unique_root": True, "lineage.root": XK(36),
           "lineage.affirmed": [{"from": XK(37), "to": XK(36), "via": ["history_base"]}]}, indexed=False)
    codex("codex_thread_spawn_child", 38, fx_codex(X(38), source={"subagent": {"thread_spawn": {"parent_thread_id": X(36)}}}),
          {"status": "child_of", "parent": X(36), "counted": False}, indexed=False)

    # identity is (host, id): one string names a Claude session and a Codex thread, and both survive
    claude("same_id_claude", 60, fx_claude(C(60)), {**counted, "host": "claude"})
    h.codex(C(60), fx_codex(C(60)), day=3)
    exp["same_id_codex"] = (lineage.identity("codex", C(60)), {**dated, "host": "codex", "source_class": "codex-cli"})

    # identities an index names for the window with no transcript here, and one outside the window
    h.rows.append((X(20), "/gone/a.jsonl", "cli", "codex-tui", int(fx_when(3)), int(fx_when(4)), 0))
    exp["codex_index_only"] = (XK(20), {"status": "known_absent", "source_class": "codex-cli", "source": "codex_state", "path": None})
    h.rows.append((X(21), "/gone/b.jsonl", "exec", "codex_exec", int(fx_when(3)), int(fx_when(4)), 0))
    exp["codex_index_only_excluded"] = (XK(21), {"status": "excluded", "reason": "exec", "source": "codex_state"})
    h.rows.append((X(22), "/gone/c.jsonl", "cli", "codex-tui", int(fx_when(1, 1)), int(fx_when(2, 1)), 0))
    h.desktop(C(20), 3, 4)
    exp["desktop_index_only"] = (CK(20), {"status": "known_absent", "source_class": "claude-desktop", "source": "claude_desktop_index"})
    h.hist[C(21)] = int(fx_when(4) * 1000)
    exp["history_index_only"] = (CK(21), {"status": "known_absent", "source_class": "claude-cli", "source": "claude_history"})
    return exp


def fx_results(census, status="read_complete", skip=(), extra_read=None, pending=None, resolved=None, members=True):
    """S3's results for every eligible session: it read and processed everything the window owns (and the backlog),
    each range credited to the version it belongs to - of every file of the root, and of every file of each read member
    of its unit, a file named by its coverage key unless it is the root's only file under the root's own identity
    (D-20261103-85f3e8, D-20261103-a7128a). `skip` names sessions, `extra_read` files by key; `pending` and `resolved`
    are keyed by session. With `members` False the results answer the roots' own files alone."""
    by_key, found = {key_of(e): e for e in census["transcripts"]}, units(census["transcripts"])

    def readings_of(file, named):
        newest = file["work"]["version"]
        if newest is None:
            return []
        name = {"transcript": file["key"]} if named else {}
        readings = {newest: {**name, "version": newest, "sha": file["sha256"], "processed": {census["window"]: file["work"]["in_window"]},
                             "read": coverage.union(coverage.union(file["owned"], file["work"]["in_window"]), (extra_read or {}).get(file["key"], []))}}
        for b in file["work"]["backlog"]:
            got = readings.setdefault(b["version"], {**name, "version": b["version"], "sha": file["versions"][b["version"]]["sha"], "processed": {}, "read": []})
            got["processed"][b["window"]] = coverage.union(got["processed"].get(b["window"], []), b["unread"])
            got["read"] = coverage.union(got["read"], b["unread"])
        return [readings[v] for v in sorted(readings)]

    out = []
    for e in census["transcripts"]:
        ident = key_of(e)
        if e["status"] != "eligible" or ident in skip:
            continue
        readings = [r for f in segments_of(e) for r in readings_of(f, f["key"] != ident)]
        for m in found.get(ident, []) if members else []:
            if by_key[m]["status"] == "child_of" and any(f["sha256"] for f in segments_of(by_key[m])):
                readings += [r for f in segments_of(by_key[m]) for r in readings_of(f, True)]
        out.append({"transcript": ident, "status": status, "readings": readings,
                    "pending_events": (pending or {}).get(ident, []), "resolved_events": (resolved or {}).get(ident, [])})
    return out


class Checks:
    """The assertions of the self-test: each records its label and, when it does not hold, a failure that names it."""

    def __init__(self):
        self.failures, self.ran = [], []

    def expect(self, label, got, want):
        failures = self.failures
        self.ran.append(label)
        if got != want:
            failures.append(f"{label}: expected {want!r}, got {got!r}")

    def refused(self, label, fn, *codes):
        failures = self.failures
        self.ran.append(label)
        try:
            fn()
            failures.append(f"{label}: nothing was refused")
        except (Refused, stagelock.Escaped) as exc:
            for code in codes:
                if code not in str(exc):
                    failures.append(f"{label}: expected {code!r} in {exc}")


def controls(checks):
    expect, refused = checks.expect, checks.refused
    probe = Checks()
    probe.expect("wrong value", 1, 2)
    probe.refused("no refusal", lambda: None)
    probe.refused("wrong code", lambda: (_ for _ in ()).throw(Refused("CODE_A")), "CODE_B")
    probe.refused("right code", lambda: (_ for _ in ()).throw(Refused("CODE_A")), "CODE_A")
    # an assert, not `expect`: the assertions are what is under test, and a statement that vouches for itself vouches for nothing
    assert [f.split(":")[0] for f in probe.failures] == ["wrong value", "no refusal", "wrong code"], \
        f"the assertions do not record a wrong value, a missing refusal and a wrong code, each by its label: {probe.failures}"
    table, table_sha = load_originators()
    empty = coverage.new_state()

    def make(root, name="home", corrupt=False):
        home = Home(root / name)
        expected = fx_corpus(home)
        home.finish(corrupt=corrupt, wal=not corrupt)  # the host has the Codex database open, its rows only in the write-ahead log
        return home, expected

    def by_id(census):
        """The census by bare session id: the fixtures share none across hosts except the one `by_key` serves."""
        return {e["id"]: fx_view(e) for e in census["transcripts"]}

    def by_key(census):
        return {key_of(e): fx_view(e) for e in census["transcripts"]}

    X1, C1 = "019e0001-0000-7000-8000-000000000000", "c0000001-0000-4000-8000-000000000000"
    cid, xid = (lambda sid: lineage.identity("claude", sid)), (lambda sid: lineage.identity("codex", sid))  # noqa: E731
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td).resolve()
        scratch = root / "scratch"
        scratch.mkdir()
        home, expected = make(root)
        host_before = home.host_bytes()
        census, state = build(home.run(), empty, table, table_sha, jobs=4, scratch=scratch)
        found = by_id(census)
        expect("done-when 6, end to end: the host's db, -wal and -shm keep their bytes and mtimes through a whole census",
               (sorted(n for n, *_ in host_before), home.host_bytes() == host_before, list(scratch.iterdir())),
               (["state_5.sqlite", "state_5.sqlite-shm", "state_5.sqlite-wal"], True, []))
        expect("every thread row lives only in the write-ahead log and is still found: the census indexed them",
               (sqlite3.connect(f"file:{home.db}?immutable=1", uri=True).execute("select count(*) from threads").fetchone()[0], by_id(census)[X1]["provenance"]),
               (0, "indexed"))

        # the corpus is O1 of design §18; the positive control comes first, then each fixture's status flipped by name
        expect("the fixtures are declared golden", REALIZATION, "golden")
        expect("every fixture is declared and present", (len(expected) >= 60, [n for n, (i, _) in expected.items() if i not in by_key(census)]), (True, []))
        expect("every fixture classifies as expected", fx_check(census, expected), [])
        expect("the census can emit every link of design §5.3: pointers, shared record ids and identical (timestamp, human text) turns",
               {via for e in census["transcripts"] for edge in e["lineage"]["affirmed"] for via in edge["via"]},
               {"forked_from_id", "history_base", "continued_in", "record_ids", "timestamp_text"})
        expect("the other pointers of §5.3 name a child: parent_thread_id and source.subagent.thread_spawn",
               [(found[xi]["status"], found[xi]["parent"]) for xi in ("019e0009-0000-7000-8000-000000000000", "019e0038-0000-7000-8000-000000000000")],
               [("child_of", "019e0001-0000-7000-8000-000000000000"), ("child_of", "019e0036-0000-7000-8000-000000000000")])
        same = lineage.split_identity(lineage.identity("codex", "c0000060-0000-4000-8000-000000000000"))[1]
        expect("one id on two hosts is two transcripts, two entries of the coverage state, and the sets still add up",
               (sorted(e["host"] for e in census["transcripts"] if e["id"] == same),
                sorted(identity_of_key(k) for k in state["transcripts"] if identity_of_key(k).endswith(same)), account(census)),
               (["claude", "codex"], [f"claude:{same}", f"codex:{same}"], []))
        for name, (ident, want) in sorted(expected.items()):
            flipped = next(s for s in STATUSES_5_1 if s != want.get("status", "eligible"))
            named = [e for e in fx_check(census, {name: (ident, {**want, "status": flipped})}) if f"FIXTURE {name}:" in e and "status" in e]
            expect(f"fixture {name}: a flipped expected status fails by its name", len(named), 1)
        expect("an expected id that is not there is named", fx_check(census, {"ghost": ("nope", {"status": "eligible"})}),
               ["FIXTURE ghost: nope is not in the census"])
        expect("a windowed read leaves no non-vacuous gap: the census read the compressed rollout in the window",
               (found["019e0010-0000-7000-8000-000000000000"]["sha256"] is not None, found["019e0010-0000-7000-8000-000000000000"]["owned"] != []),
               (True, True))

        # the reports of §5.1 and §5.3: originators with counts, the unknown-independence share, pins per source
        expect("originators are listed with their counts", {k: v["count"] for k, v in census["originators"].items()},
               {"Codex Desktop": 4, "codex_work_desktop": 1, "Claude Code": 1, "NewClient": 1, "agent-bios": 2})
        expect("the share of components and sessions with unknown independence", census["independence"],
               {"components": 36, "unknown_components": 10, "sessions": 48, "unknown_sessions": 12})
        expect("pins are counted per source", census["pins"]["codex_sessions"], {"eligible": 20, "pinned": 1})
        expect("provenance is counted per host and first entrypoint", (census["provenance"]["claude/claude-desktop"], census["provenance"]["codex/vscode"]),
               ({"indexed": 1, "not_indexed": 1, "index_missing": 0}, {"indexed": 5, "not_indexed": 4, "index_missing": 0}))
        expect("index-only identities are filed under the index that named them", {n: r["totals"] for n, r in census["sources"].items()
               if n in ("codex_state", "claude_history", "claude_desktop_index")},
               {"codex_state": {"known_absent": 1, "excluded": 1}, "claude_history": {"known_absent": 1}, "claude_desktop_index": {"known_absent": 1}})
        expect("an index row outside the window names nothing", "019e0022-0000-7000-8000-000000000000" in found, False)
        expect("the census conforms to its schema and the dump is JSON of it", (validate.validate_instance(validator(), census),
                                                                              json.loads(dump(census)) == json.loads(json.dumps(census))), ([], True))
        expect("a census document holds one transcript to a line", sum(1 for line in dump(census).splitlines() if line.startswith('  {"alt_paths"')),
               len(census["transcripts"]))

        # done-when 2: statuses are disjoint and add up; a dropped, repeated or misfiled entry is SET_MISMATCH
        expect("the discovered set equals the statuses' union", account(census), [])
        dropped = copy.deepcopy(census)
        dropped["transcripts"] = [e for e in dropped["transcripts"] if e["id"] != X1]
        expect("an entry dropped from the census is named", [e.split(":")[0] for e in account(dropped)], ["SET_MISMATCH codex_sessions"])
        repeated = copy.deepcopy(census)
        repeated["transcripts"].append(copy.deepcopy(repeated["transcripts"][0]))
        expect("an identity that appears twice is named", any("appears 2 times" in e for e in account(repeated)), True)
        stray = copy.deepcopy(census)
        stray["transcripts"][0]["source"] = "no_such_source"
        expect("an entry filed under no source is named", any("not a source" in e for e in account(stray)), True)
        absent = copy.deepcopy(census)
        absent["sources"]["codex_archived_sessions"]["totals"] = None
        expect("an entry under a source with no total is named", any("has no total" in e for e in account(absent)), True)

        # done-when 2, reconcile: S3's results fold back, the counts add up, and a deleted result is named
        results = fx_results(census)
        reconciled, after, flags = reconcile(census, state, results, "periodic")
        expect("no session stays eligible once S3 has answered", {e["status"] for e in reconciled["transcripts"] if e["source"] in ("claude_projects", "codex_sessions")}
               <= {"read_complete", "nothing_new", "child_of", "excluded", "unknown_provenance", "unreadable"}, True)
        expect("the per-source counts add up again", account(reconciled), [])
        expect("a window fully answered is accounted and fully read", (flags, after["windows"][census["window"]]), ({"accounted": True, "fully_read": True},) * 2)
        victim = results[3]["transcript"]
        refused("an S3 record deleted fails the reconciliation naming the session",
                lambda: reconcile(census, state, results[:3] + results[4:], "periodic"), "SET_MISMATCH", victim)
        refused("a result for a session that was not eligible", lambda: reconcile(census, state, results + [{**results[0], "transcript": cid("c0000004-0000-4000-8000-000000000000")}], "periodic"),
                "SET_MISMATCH", "extra=['claude:c0000004")
        refused("a session answered twice", lambda: reconcile(census, state, results + [results[0]], "periodic"), "SET_MISMATCH", "repeated=")
        left = fx_results(census, skip=(victim,))
        partial = copy.deepcopy(reconciled)
        next(e for e in partial["transcripts"] if key_of(e) == victim)["status"] = "eligible"
        expect("one session left non-terminal: the window is not accounted", coverage.accounted(partial["transcripts"], after, census["window"])[0], False)

        # source states: a missing directory is unknown, never zero; an undeclared one is told apart; an empty one is zero
        census_missing, _ = build(home.run(codex_archived_sessions=root / "no-such-dir"), empty, table, table_sha, jobs=4)
        missing = census_missing["sources"]["codex_archived_sessions"]
        expect("a missing source directory is unknown with no total", (missing["state"], missing["totals"], missing["discovered"]), ("missing", None, None))
        expect("the other sources are unaffected and the sets still add up", (account(census_missing), census_missing["sources"]["codex_sessions"]["totals"]),
               ([], census["sources"]["codex_sessions"]["totals"]))
        lost = by_id(census_missing)["019e0011-0000-7000-8000-000000000000"]
        expect("what lived in the missing directory is not claimed as read: the index still names it, absent",
               (lost["status"], lost["source"], lost["path"]), ("known_absent", "codex_state", None))
        census_undeclared, _ = build(home.run(drop=("claude_history",)), empty, table, table_sha, jobs=4)
        expect("an undeclared index is told from a missing one and its sessions are index_missing",
               (census_undeclared["sources"]["claude_history"]["state"], by_id(census_undeclared)["c0000001-0000-4000-8000-000000000000"]["provenance"],
                by_id(census_undeclared)["c0000001-0000-4000-8000-000000000000"]["counted"]), ("undeclared", "index_missing", False))
        void = Home(root / "void")
        void.finish()
        census_void, state_void = build(void.run(), empty, table, table_sha, jobs=4)
        expect("all sources empty: the run succeeds with zero eligible and zero totals, not unknown",
               ([e for e in census_void["transcripts"] if e["status"] == "eligible"], census_void["sources"]["codex_sessions"]["totals"],
                census_void["sources"]["claude_projects"]["discovered"], census_void["independence"]),
               ([], {}, 0, {"components": 0, "unknown_components": 0, "sessions": 0, "unknown_sessions": 0}))
        census_unzstd, _ = build(home.run(zstd="/nonexistent/zstd"), empty, table, table_sha, jobs=4)
        unreadable = {e["id"]: fx_view(e) for e in census_unzstd["transcripts"] if e["status"] == "unreadable"}
        packed = sorted(p.name for p in list(home.sessions.rglob("*.zst")) + list(home.archived.rglob("*.zst")))
        expect("with zstd missing every .zst rollout is unreadable by name, not skipped",
               (len(unreadable), len(packed), all("ZSTD_UNAVAILABLE /nonexistent/zstd" in e["reason"] and e["path"] in e["reason"] for e in unreadable.values() if e["path"].endswith(".zst"))),
               (len(packed), len(packed), True))
        expect("the plain rollouts are still read", by_id(census_unzstd)["019e0001-0000-7000-8000-000000000000"]["status"], "eligible")
        home_bad, _ = make(root, "bad-index", corrupt=True)
        census_bad, _ = build(home_bad.run(), empty, table, table_sha, jobs=4)
        bad = by_id(census_bad)["019e0001-0000-7000-8000-000000000000"]
        expect("an unreadable index makes its sessions index_missing: read, not counted",
               (census_bad["sources"]["codex_state"]["state"], bad["status"], bad["provenance"], bad["counted"], bad["sha256"] is not None),
               ("unreadable", "eligible", "index_missing", False, True))

        # D-20261103-85f3e8: the unit S1 judges is a root with every member at any depth. A Codex root whose own records
        # are all before the window, with a member chain three deep: the first two write in the window, the third does not
        units_home = Home(root / "units")
        R, K1, K2, K3 = (f"019e00{n}-0000-7000-8000-000000000000" for n in (80, 81, 82, 83))
        spawn = lambda parent: {"subagent": {"thread_spawn": {"parent_thread_id": parent}}}  # noqa: E731
        units_home.codex(R, fx_codex(R, "vscode", "Codex Desktop", month=9, day=1), mtime=fx_when(1, 9))
        units_home.codex(K1, fx_codex(K1, spawn(R)), indexed=False)
        units_home.codex(K2, fx_codex(K2, spawn(K1)), indexed=False)
        units_home.codex(K3, fx_codex(K3, spawn(K2), month=9, day=1), indexed=False, mtime=fx_when(1, 9))
        # a Claude root before the window whose one subagent writes in it, and a second subagent that cannot be read
        CR = "c0000080-0000-4000-8000-000000000000"
        units_home.claude(CR, fx_claude(CR, month=9, day=1), mtime=fx_when(1, 9))
        units_home.child(CR, "agent-in", fx_claude(CR, side=(True, "in")))
        locked = units_home.child(CR, "agent-locked", fx_claude(CR, side=(True, "locked")))
        # a root with records before, inside and after the window, and one whose last line the host is still writing
        CB, CT = "c0000081-0000-4000-8000-000000000000", "c0000082-0000-4000-8000-000000000000"
        units_home.claude(CB, fx_claude(CB, stamps=["2026-09-30T10:00:00.000Z", "2026-10-03T10:00:00.000Z", "2026-10-09T10:00:00.000Z"]))
        writing = units_home.claude(CT, fx_claude(CT))
        with writing.open("ab") as handle:
            handle.write(b'{"type": "user", "timestamp": "2026-10-03T11:00:00.000Z", "message": {"role": "user", "content": "half')
        units_home.finish()
        locked.chmod(0)
        try:
            unit_census, unit_state = build(units_home.run(), empty, table, table_sha, jobs=2)
        finally:
            locked.chmod(0o644)
        u = by_key(unit_census)
        RK, K1K, K2K, K3K, CRK = xid(R), xid(K1), xid(K2), xid(K3), cid(CR)
        CIN, CLOCK = cid(f"{CR}/agent-in"), cid(f"{CR}/agent-locked")
        expect("85f3e8: a root whose own records are all before the window is eligible when a member writes in it",
               (u[RK]["status"], u[RK]["window_overlap"], u[RK]["owned"], u[CRK]["status"]), ("eligible", "context_only", [], "eligible"))
        expect("85f3e8: members are read at every depth - each carries the version S1 read and what the window owns of it",
               [(k, u[k]["status"], u[k]["sha256"] is not None, u[k]["owned"] != []) for k in (K1K, K2K, K3K, CIN)],
               [(K1K, "child_of", True, True), (K2K, "child_of", True, True), (K3K, "child_of", True, False), (CIN, "child_of", True, True)])
        expect("85f3e8: the unit is the root with every member under it, whatever the depth; a member left unreadable is no longer in it",
               (units(unit_census["transcripts"]).get(RK), units(unit_census["transcripts"]).get(CRK)), ([K1K, K2K, K3K], [CIN]))
        expect("85f3e8: a member that cannot be read is named unreadable under its parent, and the unit is judged on the rest",
               (u[CLOCK]["status"], u[CLOCK]["parent"], "READ_FAILED" in (u[CLOCK]["reason"] or ""), u[CRK]["status"]),
               ("unreadable", CR, True, "eligible"))
        expect("85f3e8: a unit active only through a member counts once, through its root",
               (u[RK]["counted"], u[RK]["provenance"], u[RK]["lineage"]["unique_root"]), (True, "indexed", True))
        expect("the window_overlap of a transcript with records before, inside and after the window says it straddles both",
               (u[cid(CB)]["window_overlap"], u[cid(CB)]["owned"]), ("straddles_both", [[5, 6]]))
        complete = writing.read_bytes().rsplit(b"\n", 1)[0] + b"\n"
        expect("8facee: the version S1 records is the complete lines - a line the host is still writing moves no hash",
               (u[cid(CT)]["sha256"], u[cid(CT)]["versions"][-1]["prefix_sha"], u[cid(CT)]["versions"][-1]["record_count"]),
               (hashlib.sha256(complete).hexdigest(), hashlib.sha256(complete).hexdigest(), 10))
        expect("the unit census conforms to its schema and its sets add up", (validate.validate_instance(validator(), unit_census), account(unit_census)), ([], []))
        # one S3 result answers the unit: its members' readings are credited to them, and a result that leaves a member's
        # window unprocessed, or reads outside its unit, is refused by name
        unit_results = fx_results(unit_census)
        _rc, unit_after, unit_flags = reconcile(unit_census, unit_state, unit_results, "periodic")
        expect("85f3e8: a member's readings are credited to the member, and the window is accounted",
               (coverage.latest(unit_after, segments_of(by_key(unit_census)[K2K])[0]["key"])["processed"].get(unit_census["window"]), unit_flags),
               (u[K2K]["owned"], {"accounted": True, "fully_read": True}))
        refused("85f3e8: a read_complete that leaves a member's window unprocessed is refused, naming the member",
                lambda: reconcile(unit_census, unit_state, fx_results(unit_census, members=False), "periodic"), "RESULT_INCONSISTENT", CIN)
        stranger = [{**r, "readings": r["readings"] + [{**r["readings"][0], "transcript": XK1}]} for r in unit_results
                    for XK1 in [xid(X1)]]
        refused("85f3e8: a reading that names a transcript outside the result's unit is refused",
                lambda: reconcile(unit_census, unit_state, stranger, "periodic"), "RESULT_INCONSISTENT", "not a member of its unit")
        partial = {r["transcript"]: r for r in fx_results(unit_census, status="deferred", members=False)}
        deferred = [partial[r["transcript"]] if r["transcript"] in (RK, CRK) else r for r in unit_results]
        _rd, deferred_after, deferred_flags = reconcile(unit_census, unit_state, deferred, "periodic")
        expect("85f3e8: a carried result keeps every member's unread window in the backlog, under the member",
               (sorted(identity_of_key(b["transcript"]) for b in deferred_after["backlog"] if identity_of_key(b["transcript"]) in (K1K, K2K, CIN)),
                deferred_flags["accounted"]),
               (sorted([K1K, K2K, CIN]), True))

        # review c0fix r1 #2: a member whose full read fails, under a root and above a member of its own, is named and
        # leaves the unit; what lies below it stays in the root's unit and is read, processed and carried with it
        mid_home = Home(root / "mid")
        MR, MM, MD = (f"019e00{n}-0000-7000-8000-000000000000" for n in (84, 85, 86))
        mid_home.codex(MR, fx_codex(MR, "vscode", "Codex Desktop"))
        mid_file = mid_home.codex(MM, fx_codex(MM, spawn(MR)), indexed=False)
        mid_home.codex(MD, fx_codex(MD, spawn(MM)), indexed=False)
        mid_home.finish()
        whole_read = globals()["read_full"]

        def mid_fails(file, *args, **kwargs):
            """The head of the middle member reads, so it names its parent; its full read fails, as a tail the host
            corrupted or a file replaced between the two reads would make it."""
            if file["path"] == str(mid_file):
                raise sources.Unreadable(f"READ_FAILED {mid_file}: planted")
            return whole_read(file, *args, **kwargs)

        globals()["read_full"] = mid_fails
        try:
            mid_census, mid_state = build(mid_home.run(), empty, table, table_sha, jobs=2)
        finally:
            globals()["read_full"] = whole_read
        mv, MDK = by_key(mid_census), segments_of(by_key(mid_census)[xid(MD)])[0]["key"]
        expect("r1 #2: a member whose read failed keeps its parent, and the member below it stays in the root's unit",
               (mv[xid(MM)]["status"], mv[xid(MM)]["parent"], units(mid_census["transcripts"]).get(xid(MR))), ("unreadable", MR, [xid(MD)]))
        _rm, mid_after, mid_flags = reconcile(mid_census, mid_state, fx_results(mid_census), "periodic")
        expect("r1 #2: the member below a failed one is processed with its root, and the window is accounted",
               ((coverage.latest(mid_after, MDK) or {}).get("processed", {}).get(mid_census["window"]), mid_flags),
               (mv[xid(MD)]["owned"], {"accounted": True, "fully_read": True}))
        refused("r1 #2: a read_complete that leaves the member below a failed one unprocessed is refused, naming it",
                lambda: reconcile(mid_census, mid_state, fx_results(mid_census, members=False), "periodic"), "RESULT_INCONSISTENT", MDK)

        # review c0fix r1 #1: a record appended after the run of the window its stamp is in is owed to that window by the
        # next run (D-20261103-8facee): a line the host was still writing at window 1's census and completed since, and a
        # complete line written late; a line stamped in the window being run is that window's, as before
        late_home = Home(root / "late")
        LP, LA = "c0000090-0000-4000-8000-000000000000", "c0000091-0000-4000-8000-000000000000"
        partial_path, append_path = late_home.claude(LP, fx_claude(LP, day=7)), late_home.claude(LA, fx_claude(LA, day=7))
        with partial_path.open("ab") as handle:
            handle.write(b'{"type": "user", "timestamp": "2026-10-07T12:00:00.000Z", "message": {"role": "user", "content": "half')
        LR, LF = "c0000092-0000-4000-8000-000000000000", "c0000093-0000-4000-8000-000000000000"
        rewritten_path = late_home.claude(LR, fx_claude(LR, day=7))
        late_home.finish()
        late1, late_state1 = build(late_home.run(), empty, table, table_sha, jobs=2)
        _rl, late_after1, _fl = reconcile(late1, late_state1, fx_results(late1), "periodic")
        with partial_path.open("ab") as handle:
            handle.write(b'"}}\n')
        with append_path.open("ab") as handle:
            for stamp in ("2026-10-07T13:00:00.000Z", "2026-10-09T09:00:00.000Z"):
                handle.write(json.dumps({"type": "user", "timestamp": stamp, "message": {"role": "user", "content": "late"}}).encode() + b"\n")
        # outside the fix, and counted: a session rewritten since window 1 was run, and one never read before, both stamped in it
        late_home.put(rewritten_path, fx_claude(LR, day=7, texts=["the first question, rewritten"]))
        late_home.claude(LF, fx_claude(LF, day=7, turns=2))
        late2, late_state2 = build(late_home.run(window=NEXT), late_after1, table, table_sha, jobs=2)
        lv, W1ID = by_key(late2), late1["window"]
        expect("r1 #1: with no window run before, nothing can be owned by no run, and the census says it judged no window",
               late1["unowned"], {"earlier_windows": 0, "rewritten": {"files": 0, "records": 0}, "first_seen": {"files": 0, "records": 0}})
        expect("r1 #1: what a window already run owns in a rewritten version or a file never read before is counted, by cause",
               late2["unowned"], {"earlier_windows": 1, "rewritten": {"files": 1, "records": 10}, "first_seen": {"files": 1, "records": 8}})
        expect("r1 #1: a line completed after its window was run is owed to that window by the next run",
               (lv[cid(LP)]["status"], lv[cid(LP)]["work"]["backlog"], lv[cid(LP)]["work"]["in_window"]),
               ("eligible", [{"window": W1ID, "version": 0, "unread": [[10, 11]]}], []))
        expect("r1 #1: a complete line written late is owed to the window its stamp is in, a line of the window being run to it",
               (lv[cid(LA)]["work"]["backlog"], lv[cid(LA)]["work"]["in_window"]),
               ([{"window": W1ID, "version": 0, "unread": [[10, 11]]}], [[11, 12]]))
        expect("r1 #1: S1 holds them in the run's backlog under the status appended",
               sorted((b["transcript"], b["window"], b["status"], b["unread"]) for b in late_state2["backlog"]),
               [(cid(LP), W1ID, "appended", [[10, 11]]), (cid(LA), W1ID, "appended", [[10, 11]])])
        _rl2, late_after2, late_flags2 = reconcile(late2, late_state2, fx_results(late2), "periodic")
        expect("r1 #1: the next run processes each under its own window, and nothing is left owed",
               ([coverage.latest(late_after2, k)["processed"] for k in (cid(LP), cid(LA))], late_after2["backlog"], late_flags2),
               ([{W1ID: [[0, 11]]}, {W1ID: [[0, 11]], NEXT_ID: [[11, 12]]}], [], {"accounted": True, "fully_read": True}))
        late_t, late_t_state = build(late_home.run(kind="targeted", window=NEXT), late_after1, table, table_sha, jobs=2)
        try:
            _rt, late_t_after, late_t_flags = reconcile(late_t, late_t_state, fx_results(late_t), "targeted")
            targeted_late = (late_t_flags, records.json_text(late_t_after) == records.json_text(late_after1))
        except Refused as exc:  # a control reads the refusal, never a traceback
            targeted_late = str(exc)[:300]
        expect("r1 #1: a targeted run reads the appended records under their window, and leaves periodic coverage as it was",
               targeted_late, ({"accounted": True, "fully_read": True}, True))
        # WP-08 commit 4b, Q4: unowned records are counted only against the windows already run other than the one being
        # run (`earlier` in `build`), so the share of the window S3 reads is zero by construction, and S3's observation
        # basis takes no unowned input (`stage_read.observation_scope`). A re-run of window 1 over the state its first run
        # left, with a file rewritten and one first seen since, counts none of their records as unowned.
        try:
            rerun_unowned = build(late_home.run(), late_after1, table, table_sha, jobs=2)[0]["unowned"]
        except Refused as exc:  # a control reads the refusal, never a traceback
            rerun_unowned = str(exc)[:300]
        expect("4b Q4: a census never counts the window it is run for among the windows unowned records are owed to",
               rerun_unowned, {"earlier_windows": 0, "rewritten": {"files": 0, "records": 0}, "first_seen": {"files": 0, "records": 0}})
        # what read_full says a window already run owns is the appended records only, never the ones before them
        lines = append_path.read_bytes().splitlines(keepends=True)
        before = {"record_count": 10, "prefix_sha": hashlib.sha256(b"".join(lines[:10])).hexdigest()}
        w1_start, w1_end, _w1 = coverage.window_bounds(WINDOW)
        got_late = read_full({"host": "claude", "path": str(append_path)}, ZSTD, NO_SCAN, coverage.Ownership(*coverage.window_bounds(NEXT)[:2]),
                             before, [(w1_start, w1_end, W1ID)])
        expect("r1 #1: the records a window already run owns are taken from the append alone", (got_late["prefix_ok"], got_late["late"]),
               (True, {W1ID: [[10, 11]]}))

        # D-20261103-a7128a: a Codex thread written across several rollout files under one id is one row, a file per
        # segment in name order, each under its own coverage key; a copy of one file under the same name is no segment
        seg_home = Home(root / "segments")
        SL, SF, SS, ST, SC, G = (f"019e01{n}-0000-7000-8000-000000000000" for n in (10, 11, 12, 13, 14, 15))
        later = {"history_base": {"thread_id": "019e0199-0000-7000-8000-000000000000", "end_ordinal_exclusive": 7}}
        # SL: in the window only in its last file, the first before it; the index names the last; only the last compacted
        seg_home.codex(SL, fx_codex(SL, "vscode", "Codex Desktop", month=9, day=20), indexed=False, name_at="2026-09-20T10-00-00")
        seg_home.codex(SL, fx_codex(SL, "vscode", "Codex Desktop", meta=later, compacted=True), name_at="2026-10-03T10-00-00")
        # SF: in the window only in its first file, the last after it, and the later file's history_base points elsewhere;
        # its first file was archived, so the census finds the later one first, and the later one says it was run by exec
        seg_home.codex(SF, fx_codex(SF, "vscode", "Codex Desktop"), where="archived", name_at="2026-10-03T10-00-00")
        seg_home.codex(SF, fx_codex(SF, "exec", "codex_exec", day=10, meta=later), indexed=False, name_at="2026-10-10T10-00-00")
        # SS: both files in the window; the second has a compressed copy in archived_sessions, which the index names
        seg_home.codex(SS, fx_codex(SS, "vscode", "Codex Desktop", day=2), indexed=False, name_at="2026-10-02T10-00-00")
        seg_home.codex(SS, fx_codex(SS, "vscode", "Codex Desktop", day=4, meta=later), indexed=False, name_at="2026-10-04T10-00-00", day=4)
        copy_of = seg_home.codex(SS, fx_codex(SS, "vscode", "Codex Desktop", day=4, meta=later), where="archived", zst=True,
                                 name_at="2026-10-04T10-00-00", day=4)
        # ST: its last file is being written: a line without its end
        seg_home.codex(ST, fx_codex(ST, "vscode", "Codex Desktop", day=2), name_at="2026-10-02T10-00-00")
        writing_file = seg_home.codex(ST, fx_codex(ST, "vscode", "Codex Desktop", day=4, meta=later), indexed=False, name_at="2026-10-04T10-00-00", day=4)
        with writing_file.open("ab") as handle:
            handle.write(b'{"timestamp": "2026-10-04T11:00:00.000Z", "type": "event_msg", "payload": {"type": "task_sta')
        # SC: a child of SF in two files; G: a Guardian review of SS
        spawn_of = lambda parent: {"subagent": {"thread_spawn": {"parent_thread_id": parent}}}  # noqa: E731
        seg_home.codex(SC, fx_codex(SC, spawn_of(SF)), indexed=False, name_at="2026-10-03T11-00-00")
        seg_home.codex(SC, fx_codex(SC, spawn_of(SF), day=5, meta=later), indexed=False, name_at="2026-10-05T11-00-00", day=5)
        seg_home.codex(G, fx_codex(G, {"subagent": {"other": "guardian"}}, meta={"parent_thread_id": SS}), indexed=False)
        # a Claude session with a workflow's journal beside its subagents
        CW = "c0000090-0000-4000-8000-000000000000"
        seg_home.claude(CW, fx_claude(CW))
        seg_home.put(seg_home.projects / "-fx" / CW / "subagents" / "workflows" / "w" / "journal.jsonl", [{"type": "step"}])
        seg_home.finish()
        seg_census, seg_state = build(seg_home.run(), empty, table, table_sha, jobs=2)
        sg = {key_of(e): e for e in seg_census["transcripts"]}
        files = {k: segments_of(e) for k, e in sg.items()}
        SLK, SFK, SSK, STK, SCK, GK = (xid(s) for s in (SL, SF, SS, ST, SC, G))
        expect("a7128a: a thread in several files is one row, its files in name order, each under its own coverage key",
               [(f["key"], f["source"]) for f in files[SSK]],
               [(f"{SSK}@rollout-2026-10-02T10-00-00-{SS}", "codex_sessions"), (f"{SSK}@rollout-2026-10-04T10-00-00-{SS}", "codex_sessions")])
        expect("a7128a: a file found again under its own name is a copy beside its row, not a file of the session",
               (sg[SSK]["alt_paths"], len(files[SSK])), ([str(copy_of)], 2))
        expect("a7128a: a thread in the window only in its last file is eligible, and the window owns that file's records",
               (sg[SLK]["status"], [f["owned"] != [] for f in files[SLK]], [f["sha256"] is not None for f in files[SLK]], sg[SLK]["window_overlap"]),
               ("eligible", [False, True], [True, True], "straddles_start"))
        expect("a7128a: a thread in the window only in its first file is eligible, and the window owns that file's records",
               (sg[SFK]["status"], [f["owned"] != [] for f in files[SFK]], sg[SFK]["window_overlap"]), ("eligible", [True, False], "straddles_end"))
        expect("a7128a: a thread spanning two files owes the window both",
               [f["work"]["in_window"] != [] for f in files[SSK]], [True, True])
        complete_lines = writing_file.read_bytes().rsplit(b"\n", 1)[0] + b"\n"
        expect("a7128a: a file still being written is its complete lines, like any transcript",
               (files[STK][1]["sha256"], files[STK][1]["versions"][-1]["record_count"]), (hashlib.sha256(complete_lines).hexdigest(), 7))
        expect("a7128a: a thread is indexed when the index names any of its files, or a copy of one",
               (sg[SLK]["provenance"], sg[SFK]["provenance"], sg[SSK]["provenance"]), ("indexed", "indexed", "indexed"))
        expect("a7128a: the kind and pointer are the first file's, though the census found a later one first: its source "
               "classifies the thread, and a later file's history_base is no edge, so the thread is its own root",
               (sg[SFK]["status"], sg[SFK]["entrypoint"], sg[SFK]["lineage"]["root"], sg[SFK]["lineage"]["unique_root"],
                sg[SFK]["lineage"]["affirmed"], sg[SFK]["counted"]),
               ("eligible", "vscode", SFK, True, [], True))
        expect("a7128a: a compaction in any file of a thread keeps its lineage pending",
               (sg[SLK]["lineage"]["measurement_pending"], sg[SFK]["lineage"]["measurement_pending"]), (True, False))
        expect("85f3e8 with a7128a: a member in two files is read in both, as part of its root's unit",
               (sg[SCK]["status"], [f["sha256"] is not None and f["owned"] != [] for f in files[SCK]], units(seg_census["transcripts"]).get(SFK)),
               ("child_of", [True, True], [SCK]))
        expect("b1989d: a Guardian review session is excluded by name, and is no member of the session it reviews",
               (sg[GK]["status"], sg[GK]["reason"], units(seg_census["transcripts"]).get(SSK)), ("excluded", "guardian", None))
        expect("a workflow's journal under subagents/ is no child: no row, and counted with the files that are not read",
               (sorted(k for k in sg if k.startswith(cid(CW))), seg_census["sources"]["claude_projects"]["unrecognized"]), ([cid(CW)], 1))
        expect("the census of split threads conforms to its schema and its sets add up",
               (validate.validate_instance(validator(), seg_census), account(seg_census)), ([], []))

        # one S3 result answers a thread in several files: each reading names the file it read, and is credited to it
        seg_results = fx_results(seg_census)
        _seg_done, seg_after, seg_flags = reconcile(seg_census, seg_state, seg_results, "periodic")
        expect("a7128a: each file's readings are credited to that file, the first and the last alike",
               ([coverage.latest(seg_after, f["key"])["processed"].get(seg_census["window"]) for f in files[SSK]], seg_flags),
               ([f["owned"] for f in files[SSK]], {"accounted": True, "fully_read": True}))
        pending_results = [{**r, "pending_events": [{"id": "pe-seg", "first_record": 2}]} if r["transcript"] == SSK else r for r in seg_results]
        _pending_done, pending_after, _pending_flags = reconcile(seg_census, seg_state, pending_results, "periodic")
        expect("a7128a: a pending event of a thread in several files is held under its last file unless it names one",
               [(e["transcript"], e["version"]) for e in pending_after["pending_events"] if e["id"] == "pe-seg"], [(files[SSK][-1]["key"], 0)])
        stray_event = [{**r, "pending_events": [{"id": "pe-stray", "first_record": 2, "transcript": f"{SSK}@nowhere"}]} if r["transcript"] == SSK
                       else r for r in seg_results]
        refused("a7128a: a pending event naming a file outside its unit is refused",
                lambda: reconcile(seg_census, seg_state, stray_event, "periodic"), "RESULT_INCONSISTENT", "not a file of its unit")
        unnamed = [{**r, "readings": [{k: v for k, v in g.items() if k != "transcript"} for g in r["readings"]]} if r["transcript"] == SSK else r
                   for r in seg_results]
        refused("a7128a: a reading that names no file of a thread written in several is refused",
                lambda: reconcile(seg_census, seg_state, unnamed, "periodic"), "RESULT_INCONSISTENT", "names no file")
        first_only = [{**r, "readings": [g for g in r["readings"] if g.get("transcript") != files[SSK][0]["key"]]} if r["transcript"] == SSK else r
                      for r in seg_results]
        refused("a7128a: a read_complete that leaves the first file's window unprocessed is refused, naming that file",
                lambda: reconcile(seg_census, seg_state, first_only, "periodic"), "RESULT_INCONSISTENT", files[SSK][0]["key"])

        # the shape of a row is its host's: the census's own accounting names a row that departs from it, and so does
        # the one reader of rows outside the census
        def bent(change):
            doc = copy.deepcopy(seg_census)
            change({key_of(e): e for e in doc["transcripts"]})
            return doc
        for label, change, why in (
                ("a Codex row carrying a file's path on the row", lambda rows_: rows_[SSK].update(path="/x"), "never ['path'] on the row"),
                ("a Codex row without segments", lambda rows_: rows_[SSK].pop("segments"), "and this one has none"),
                ("a Claude row carrying segments", lambda rows_: rows_[cid(CW)].update(segments=[]), "never in segments")):
            doc = bent(change)
            expect(f"a7128a: {label} is named by the census's accounting",
                   [e for e in account(doc) if "SET_MISMATCH shape" in e and why in e] != [], True)
            try:
                rows(doc)
                said = None
            except ValueError as exc:
                said = str(exc)
            expect(f"a7128a: {label} is refused by the reader of rows", "CENSUS_MALFORMED" in (said or ""), True)

        # a file of a thread the coverage state owes work on that is gone: the row says which, and the work stays owed;
        # a thread with no file left is a lost transcript under the file's own key
        gone_key, lost_key = f"{SSK}@rollout-2026-10-01T09-00-00-{SS}", f"{xid('019e0198-0000-7000-8000-000000000000')}@rollout-2026-10-01T09-00-00-x"
        owing = coverage.new_state()
        for key in (gone_key, lost_key):
            coverage.observe(owing, key, "ab" * 32, 3, "ab" * 32, None)
            owing["backlog"].append({"transcript": key, "version": 0, "window": NEXT_ID, "status": "deferred", "unread": [[0, 3]]})
        owed_census, _owed_state = build(seg_home.run(), owing, table, table_sha, jobs=2)
        og = {key_of(e): e for e in owed_census["transcripts"]}
        expect("a7128a: a session whose owed file is gone is unreadable, naming the file, and lists it with no path",
               (og[SSK]["status"], (og[SSK]["reason"] or "").startswith(f"SEGMENT_ABSENT {gone_key}:"),
                [(f["key"], f["path"] is None) for f in segments_of(og[SSK])][0]),
               ("unreadable", True, (gone_key, True)))
        expect("a7128a: a thread whose every owed file is gone is a lost transcript, listing the file it owes",
               ((og[identity_of_key(lost_key)]["status"], [f["key"] for f in segments_of(og[identity_of_key(lost_key)])]),
                account(owed_census), validate.validate_instance(validator(), owed_census)),
               (("known_absent", [lost_key]), [], []))

        # the structural guard: outside the census a census document is read only through its readers
        texts = reader_texts()
        bypasses, reader_sites = reader_bypasses(texts)
        expect("a7128a: outside the census, the census file is named only where an exception says why, and its rows are read through rows",
               (bypasses, len(texts) >= 20, sorted(reader_sites)), ([], True, sorted(READER_EXCEPTIONS)))
        for label, planted_text, code in (
                ("a module that parses the census file itself", texts["runlib/views.py"]
                 + '\n\ndef sneak(run_dir):\n    return json.loads((run_dir / "census.json").read_text())\n', "runlib/views.py (sneak)"),
                ("a census document's rows taken around rows", texts["runlib/views.py"]
                 + '\n\ndef sneak(run_dir):\n    doc = census.load(run_dir)\n    return doc["transcripts"]\n', "(sneak): doc['transcripts']"),
                ("an exception whose site no longer names the file", texts["runlib/views.py"].replace('"census.json"', '"elsewhere.json"'),
                 "stale exception runlib/views.py (run)")):
            found_here = reader_bypasses({**texts, "runlib/views.py": planted_text})[0]
            expect(f"a7128a: {label} is named", [v for v in found_here if code in v] != [], True)

        # done-when 1 and 3, the runs that follow one another: a resume, an event across the window's end, a rewrite
        two = Home(root / "two")
        T = "c0000070-0000-4000-8000-000000000000"
        TK = cid(T)
        stamps = ["2026-10-02T10:00:00.000Z", "2026-10-03T10:00:00.000Z", "2026-10-07T23:50:00.000Z", "2026-10-08T00:10:00.000Z", "2026-10-08T01:00:00.000Z"]
        path = two.claude(T, fx_claude(T, stamps=stamps), mtime=fx_when(9))
        original = path.read_bytes()
        M = "019e0070-0000-7000-8000-000000000000"
        MK = xid(M)
        moved = two.codex(M, fx_codex(M, "vscode", "Codex Desktop"), zst=True)
        two.finish()
        run1, built1 = build(two.run(), empty, table, table_sha, jobs=2)
        t1 = by_id(run1)[T]
        expect("run 1: the event's outcome lies past the window, so the session straddles its end and owns the records before it",
               (t1["window_overlap"], t1["owned"], t1["work"]["in_window"]), ("straddles_end", [[0, 7]], [[0, 7]]))
        event = {"id": "event-1", "first_record": 6}
        r1 = fx_results(run1, extra_read={TK: [[7, 9]]}, pending={TK: [event]})
        state1 = reconcile(run1, built1, r1, "periodic")[1]
        v1 = coverage.latest(state1, TK)
        expect("run 1: the outcome was read as context and is not processed for the window that did not own it",
               (v1["read"], v1["processed"]), ([[0, 9]], {run1["window"]: [[0, 7]]}))
        run2, built2 = build(two.run(window=NEXT), state1, table, table_sha, jobs=2)
        t2 = by_id(run2)[T]
        expect("run 2: the window that owns the outcome processes it again though run 1 read it", (t2["owned"], t2["work"]["in_window"]), ([[7, 9]], [[7, 9]]))
        expect("run 2: the pending event survives the run boundary with its id", [e["id"] for e in run2["pending_events"]], ["event-1"])
        state2 = reconcile(run2, built2, fx_results(run2, resolved={TK: ["event-1"]}), "periodic")[1]
        expect("run 2: the event is stitched and resolved; each record is processed once, by its own window",
               (coverage.latest(state2, TK)["processed"], state2["pending_events"]),
               ({run1["window"]: [[0, 7]], run2["window"]: [[7, 9]]}, []))
        no_reread = fx_results(run2, resolved={TK: ["event-1"]})
        for answer in no_reread:
            for got in answer["readings"]:
                got["read"] = []  # the owning run keeps its processed credit but does not read the records again
        refused("the run that owns a context-read record may not process it without reading it again", lambda: reconcile(run2, built2, no_reread, "periodic"),
                "PROCESSED_UNREAD", "which this result did not read")
        again, _ = build(two.run(window=NEXT), state2, table, table_sha, jobs=2)
        expect("a transcript with nothing new since the last window is nothing_new", (by_id(again)[T]["status"], by_id(again)[T]["work"]["in_window"]),
               ("nothing_new", []))
        before = fx_when(10)
        two.put(path, fx_claude(T, stamps=stamps + ["2026-10-09T09:00:00.000Z", "2026-10-09T09:01:00.000Z"]), mtime=before)
        appended, state3 = build(two.run(window=NEXT), state2, table, table_sha, jobs=2)
        t3 = by_id(appended)[T]
        expect("a resumed session with appended records is one transcript whose continuity holds and whose new records are a new range",
               (len(t3["versions"]), t3["versions"][0]["record_count"], t3["owned"], t3["work"]["in_window"], t3["status"], T in {e["id"] for e in appended["transcripts"]}),
               (1, 11, [[7, 11]], [[9, 11]], "eligible", True))

        # a rewrite: a new version read in full; the evidence ids of the prior version still resolve to the copy of the bytes they came from
        store = root / "immutable-copies"
        store.mkdir()

        def keep(data):
            """The immutable copy S2 will make of each version, named by its sha (WP-06 owns it; this stands in for its store)."""
            (store / hashlib.sha256(data).hexdigest()).write_bytes(data)
            return hashlib.sha256(data).hexdigest()

        def resolve(locator, state, defective=False):
            """The bytes of one record an evidence id names: the version it came from, found by the sha the id carries."""
            versions = state["transcripts"][locator["transcript"]]["versions"]
            version = versions[-1] if defective else next(v for v in versions if v["sha"] == locator["sha"])
            return (store / version["sha"]).read_bytes().splitlines()[locator["record"]]

        prior = {"transcript": TK, "sha": keep(original), "record": 4}
        two.put(path, fx_claude(T, stamps=["2026-10-02T11:00:00.000Z"] + stamps[1:]), mtime=before)
        rewritten, state4 = build(two.run(window=NEXT), state2, table, table_sha, jobs=2)
        t4 = by_id(rewritten)[T]
        expect("a rewritten transcript fails continuity: a new version, read in full, the prior version kept for its evidence",
               (len(t4["versions"]), t4["versions"][0]["sha"] == coverage.latest(state2, TK)["sha"], t4["versions"][1]["sha"] == t4["sha256"], t4["work"]["in_window"],
                coverage.latest(state4, TK)["read"]), (2, True, True, [[7, 9]], []))
        current = {"transcript": TK, "sha": keep(path.read_bytes()), "record": 4}
        live_record = path.read_bytes().splitlines()[4]
        expect("a prior version's evidence id still resolves to the bytes it was cut from, a new one to the new version's",
               (resolve(prior, state4) == original.splitlines()[4], resolve(prior, state4) != live_record, resolve(current, state4) == live_record),
               (True, True, True))
        expect("instrument control: a resolver that follows the latest version returns the rewritten record for the old id",
               resolve(prior, state4, defective=True) == live_record, True)

        # a rollout moved to archived_sessions is the same transcript: the coverage captured before the move is the base of the run after it
        parked = by_id(run1)[M]
        archived_at = two.archived / moved.name
        archived_at.parent.mkdir(parents=True, exist_ok=True)
        moved.rename(archived_at)
        two.rows = [(M, str(archived_at)[:-len(".zst")], "vscode", "Codex Desktop", int(fx_when(3)), int(fx_when(4)), 1)]
        two.close()
        two.db.unlink()
        two.finish()
        run_b, state_b = build(two.run(), state1, table, table_sha, jobs=2)
        t_b = by_id(run_b)[M]
        expect("a rollout moved to archived_sessions is the same transcript: one version, a new path, still indexed",
               (t_b["id"], len(t_b["versions"]), t_b["sha256"] == parked["sha256"], t_b["source"], t_b["provenance"]),
               (M, 1, True, "codex_archived_sessions", "indexed"))
        expect("the move keeps its continuity: the ranges processed before it are still processed, so the window owes it nothing",
               (t_b["status"], t_b["work"]["in_window"],
                coverage.latest(state_b, f"{MK}@{stem_of(moved)}")["processed"] == coverage.latest(state1, f"{MK}@{stem_of(moved)}")["processed"] != {}),
               ("nothing_new", [], True))
        run_c, _ = build(two.run(), empty, table, table_sha, jobs=2)
        expect("instrument control: a census that forgot the pre-move coverage would treat the moved file as new work",
               (by_id(run_c)[M]["status"], by_id(run_c)[M]["work"]["in_window"] != []), ("eligible", True))

        # F#3 at the census: a backlog belongs to a version, and a rewrite that keeps the offsets cannot discharge it
        rw = Home(root / "rewrite")
        R = "c0000071-0000-4000-8000-000000000000"
        RK = cid(R)
        rpath = rw.claude(R, fx_claude(R))
        rw.finish()
        first_rw, built_rw = build(rw.run(), empty, table, table_sha, jobs=2)
        answers = fx_results(first_rw)
        answers[0].update(status="read_partial")
        answers[0]["readings"][0].update(read=[[0, 6]], processed={first_rw["window"]: [[0, 6]]})
        _, partial_rw, _ = reconcile(first_rw, built_rw, answers, "periodic")
        rw.put(rpath, fx_claude(R, texts=["rewritten a", "rewritten b", "rewritten c"], stamps=[fx_stamp(3, k) for k in range(5)] + [fx_stamp(3, 99)]))
        after_rw, built_after = build(rw.run(window=NEXT), partial_rw, table, table_sha, jobs=2)
        r_entry = by_id(after_rw)[R]
        expect("after a rewrite the backlog still names the version it was owed on, and the new version has work of its own",
               (len(r_entry["versions"]), r_entry["work"]["version"], r_entry["work"]["backlog"], r_entry["status"]),
               (2, 1, [{"window": first_rw["window"], "version": 0, "unread": [[6, 10]]}], "eligible"))
        good = fx_results(after_rw)
        done_rw, state_rw, _ = reconcile(after_rw, built_after, good, "periodic")
        expect("the backlog is discharged from a reading of the version it belongs to",
               (state_rw["backlog"], coverage.latest(state_rw, RK)["processed"], state_rw["transcripts"][RK]["versions"][0]["processed"]),
               ([], {}, {first_rw["window"]: [[0, 10]]}))
        forged = copy.deepcopy(good)
        forged[0]["readings"] = [{"version": 1, "sha": forged[0]["readings"][-1]["sha"], "read": [[0, 10]], "processed": {first_rw["window"]: [[6, 10]]}}]
        refused("the same offsets read from the rewritten version do not discharge the old version's backlog",
                lambda: reconcile(after_rw, built_after, forged, "periodic"), "PROCESSED_OUTSIDE_OWNED", f"version 1 processed [[6, 10]] for window {first_rw['window']}")

        # done-when 1 and 3: deferred and partial sessions are carried, and read first by the next run
        carry = Home(root / "carry")
        ids = [f"c00000{n}-0000-4000-8000-000000000000" for n in (40, 41, 42)]
        keys = [cid(i) for i in ids]
        for sid in ids:
            carry.claude(sid, fx_claude(sid))
        carry.finish()
        first, built_first = build(carry.run(), empty, table, table_sha, jobs=2)
        answers = fx_results(first)
        answers[0].update(status="read_partial")
        answers[0]["readings"][0].update(read=[[0, 6]], processed={first["window"]: [[0, 6]]})
        answers[1].update(status="deferred", readings=[])
        answers[2].update(status="failed", readings=[])
        done, carried, flags = reconcile(first, built_first, answers, "periodic")
        expect("partial, deferred and failed sessions are terminal, with their unread ranges in the backlog",
               ({key_of(e): e["status"] for e in done["transcripts"]}, [(b["transcript"], b["status"], b["unread"]) for b in carried["backlog"]], flags),
               (dict(zip(keys, ("read_partial", "deferred", "failed"))), [(keys[0], "read_partial", [[6, 10]]), (keys[1], "deferred", [[0, 10]]),
                                                                        (keys[2], "failed", [[0, 10]])], {"accounted": True, "fully_read": False}))
        expect("accounted and fully read are counted apart", (window_counts(first["transcripts"]), window_counts(done["transcripts"])),
               ({"eligible": 3, "accounted": 0, "fully_read": 0}, {"eligible": 3, "accounted": 3, "fully_read": 0}))
        wait = copy.deepcopy(answers)
        refused("a backlog lost is not accepted: a session unanswered", lambda: reconcile(first, built_first, wait[:2], "periodic"), "SET_MISMATCH", ids[2])
        ahead = copy.deepcopy(answers)
        ahead[0]["readings"][0]["processed"][NEXT_ID] = [[6, 10]]
        ahead[0]["readings"][0]["read"] = [[0, 10]]
        refused("S3 may not credit the records of a later window in advance", lambda: reconcile(first, built_first, ahead, "periodic"),
                "PROCESSED_OUTSIDE_OWNED", f"for window {NEXT_ID}")
        for label, status, code in (("a session answered nothing_new while it still owes work", "nothing_new", "RESULT_INCONSISTENT"),
                                    ("a session answered with a status that is not terminal", "eligible", "RESULT_STATUS_INVALID"),
                                    ("a session answered with a status of the census's own", "known_absent", "RESULT_STATUS_INVALID")):
            bad = copy.deepcopy(fx_results(first))
            bad[0]["status"] = status
            if status == "nothing_new":
                bad[0]["readings"][0]["processed"] = {}  # it processed nothing, so the window's records are still owed
            refused(label, lambda bad=bad: reconcile(first, built_first, bad, "periodic"), code)
        nxt, built_nxt = build(carry.run(window=NEXT), carried, table, table_sha, jobs=2)
        expect("the next run reads the backlog first, tagged with the window it belongs to, though the window owns nothing",
               ([e["status"] for e in nxt["transcripts"]], by_id(nxt)[ids[0]]["work"]["backlog"], by_id(nxt)[ids[0]]["work"]["in_window"]),
               (["eligible"] * 3, [{"window": first["window"], "version": 0, "unread": [[6, 10]]}], []))
        deferral = fx_results(nxt, status="deferred")
        for answer in deferral:
            answer["readings"] = []
        _, kept_state, kept_flags = reconcile(nxt, built_nxt, deferral, "periodic")
        expect("a session that defers the earlier window's backlog again keeps it under that window, and the current window is accounted, not fully read",
               (kept_flags, sorted({b["window"] for b in kept_state["backlog"]}), sorted((b["transcript"], b["unread"]) for b in kept_state["backlog"])),
               ({"accounted": True, "fully_read": False}, [first["window"]], sorted((b["transcript"], b["unread"]) for b in carried["backlog"])))
        cleared = reconcile(nxt, built_nxt, fx_results(nxt), "periodic")
        expect("reading the backlog clears it and credits the window it belongs to",
               (cleared[1]["backlog"], coverage.latest(cleared[1], keys[1])["processed"], cleared[2]), ([], {first["window"]: [[0, 10]]}, {"accounted": True, "fully_read": True}))

        nowhere = root / "nowhere"
        nowhere.mkdir()
        gone, _ = build(carry.run(window=NEXT, claude_projects=nowhere), carried, table, table_sha, jobs=2)
        expect("a transcript the coverage state still owes that is gone is a lost transcript, filed and counted, not a vanished obligation",
               ([(e["id"], e["status"], e["reason"], e["source"]) for e in gone["transcripts"]], gone["sources"]["coverage_state"]["totals"], account(gone)),
               ([(i, "known_absent", "owed_by_coverage", "coverage_state") for i in ids], {"known_absent": 3}, []))

        # done-when 3: a targeted run reads but never advances periodic coverage
        tgt, tstate = build(carry.run(kind="targeted"), carried, table, table_sha, jobs=2)
        expect("a targeted run starts from the base and returns it", records.json_text(tstate), records.json_text(carried))
        t_done, t_state, t_flags = reconcile(tgt, carried, fx_results(tgt), "targeted")
        expect("a targeted run's results reconcile its statuses and leave periodic coverage byte-identical",
               (records.json_text(t_state) == records.json_text(carried), {e["status"] for e in t_done["transcripts"]}), (True, {"read_complete"}))
        fresh_t, fresh_base = build(carry.run(kind="targeted"), empty, table, table_sha, jobs=2)
        fresh_answers = fx_results(fresh_t)
        _, fresh_after, _ = reconcile(fresh_t, fresh_base, fresh_answers, "targeted")
        expect("a targeted run over transcripts the base never saw reconciles against the state it observed, and leaves the base as it was",
               (records.json_text(fresh_after) == records.json_text(empty), len(fresh_answers)), (True, 3))
        false_new = copy.deepcopy(fresh_answers)
        false_new[0].update(status="nothing_new")
        false_new[0]["readings"][0]["processed"] = {}
        refused("a targeted run's unread work reported nothing_new is refused by name", lambda: reconcile(fresh_t, fresh_base, false_new, "targeted"),
                "RESULT_INCONSISTENT", "nothing_new")
        wrong_sha = copy.deepcopy(fresh_answers)
        wrong_sha[0]["readings"][0]["sha"] = "0" * 64
        refused("a targeted run's reading of bytes the census did not see is refused by name", lambda: reconcile(fresh_t, fresh_base, wrong_sha, "targeted"),
                "VERSION_MISMATCH")
        original = coverage.apply_results
        coverage.apply_results = lambda st, w, kind, res, owned, members=None: original(st, w, "periodic", res, owned, members)  # a writer that ignores the run kind
        try:
            refused("a targeted run that advanced a processed range fails TARGETED_ADVANCED_COVERAGE",
                    lambda: reconcile(tgt, carried, fx_results(tgt), "targeted"), "TARGETED_ADVANCED_COVERAGE")
        finally:
            coverage.apply_results = original

        # Codex compaction is classified only once design §14 check 5 has measured it (WP-23 records that)
        lineage.CODEX_COMPACTION_MEASURED = True
        try:
            measured, _ = build(home.run(), empty, table, table_sha, jobs=4)
        finally:
            lineage.CODEX_COMPACTION_MEASURED = False
        later = by_id(measured)["019e0014-0000-7000-8000-000000000000"]
        expect("once the compaction is measured the same fixture is an ordinary counted root",
               (later["lineage"]["measurement_pending"], later["lineage"]["unique_root"], later["counted"]), (False, True, True))

        # the originator table: the shipped defaults are design §5.1's, and an owner's bad edit is named
        expect("the shipped originator table is the design's default", table,
               {"Codex Desktop": "codex-desktop", "codex_work_desktop": "codex-desktop", "Claude Code": "excluded",
                "codex_vscode": "unknown_provenance", "codex-chrome-extension-sidepanel": "unknown_provenance"})
        (root / "table.json").write_text('{"codex": {"Codex Desktop": "everything"}}')
        refused("an originator mapped to a class that does not exist", lambda: load_originators(root / "table.json"), "ORIGINATOR_TABLE_INVALID", "everything")
        (root / "table.json").write_text("[1]")
        refused("an originator table that is not the expected object", lambda: load_originators(root / "table.json"), "ORIGINATOR_TABLE_INVALID")
        owner_map = by_id(build(home.run(), empty, {**table, "NewClient": "codex-desktop"}, table_sha, jobs=4)[0])["019e0006-0000-7000-8000-000000000000"]
        expect("the owner maps an originator at S0 and its sessions follow", (owner_map["status"], owner_map["source_class"]), ("eligible", "codex-desktop"))

        # S1 as a stage: it reads the coverage the declaration pinned, writes into the run directory, and the tracked file stays
        from runlib import declare
        out, tracked = root / "out", root / "state"
        out.mkdir()
        tracked.mkdir()
        (tracked / "coverage.json").write_text(records.json_text(empty))
        _, base_sha = coverage.load(tracked / "coverage.json")
        fixture = declare.fixture()
        declaration = {**fixture, "window": WINDOW, "sources": home.run()["sources"], "starting_hashes": {**fixture["starting_hashes"], "coverage": base_sha}}
        declare.create(out / "r1", declaration)
        done = run(out / "r1", tracked / "coverage.json", jobs=2)
        record = records.read_json(records.record_path(out / "r1", "S1"))
        expect("the stage records census.json and the run's coverage.json, complete", (record["status"], [o["artifact"] for o in record["outputs"]]),
               ("complete", ["census.json", "coverage.json"]))
        expect("the file is the census", json.loads((out / "r1" / "census.json").read_text()) == json.loads(json.dumps(done)), True)
        expect("the run's coverage is the base plus what was observed, and the tracked file is untouched",
               (len(coverage.load(out / "r1" / "coverage.json")[0]["transcripts"]) > 0, coverage.load(tracked / "coverage.json")[1] == base_sha), (True, True))
        refused("a census of a run that was never declared", lambda: run(out / "nobody", tracked / "coverage.json", jobs=2), "RUN_UNDECLARED")
        declare.create(out / "r2", {**declaration, "starting_hashes": {**fixture["starting_hashes"], "coverage": "0" * 64}})
        refused("a declaration that pinned another coverage state stops the stage", lambda: run(out / "r2", tracked / "coverage.json", jobs=2), "COVERAGE_BASE_STALE")
        expect("the refused stage left no record", records.record_path(out / "r2", "S1").exists(), False)
        # X review of WP-08 r2: an amendment landing just before S1's admission, after census.run read the declaration, is
        # refused by name; one landing just after it changes nothing the census was built from
        later = [("window.end", "2026-10-09T00:00:00")]
        for when in ("before", "after"):
            raced = out / f"race-{when}"
            declare.create(raced, declaration)
            with records.fx_amended_at_admission("S1", later, when):
                try:
                    got = run(raced, tracked / "coverage.json", jobs=2)["window"]
                except Refused as exc:
                    got = str(exc).split()[0]
                except Exception as exc:  # noqa: BLE001 - reported by the control below, by name
                    got = repr(exc)
            s1 = records.record_path(raced, "S1")
            seq = records.read_json(s1)["declaration_seq"] if s1.is_file() else None
            if when == "before":
                expect("X r2: an amendment between census.run's read and S1's admission is refused, and no census is written",
                       (got, (raced / "census.json").exists()), ("DECLARATION_MOVED", False))
            else:
                expect("X r2: an amendment just after S1's admission changes nothing the census was built from",
                       (got, seq, records.read_json(records.run_json_path(raced))["declaration_seq"]),
                       (coverage.window_bounds(WINDOW)[2], 0, 1))
        declare.create(out / "r3", declaration)
        real_build = build
        globals()["build"] = lambda *a, **k: ({**real_build(*a, **k)[0], "kind": "bogus"}, empty)
        try:
            refused("a census that breaks its own schema is not written", lambda: run(out / "r3", tracked / "coverage.json", jobs=2), "CENSUS_INVALID")
        finally:
            globals()["build"] = real_build
        expect("nothing was written for it", (out / "r3" / "census.json").exists(), False)

        # the snapshot directory: confined beneath the run, made fresh for each read, and the only thing ever removed
        expect("a finished run leaves no snapshot directory behind", sorted(p.name for p in (out / "r1" / "private").glob("*")), [])
        external = root / "external-source"
        external.mkdir()
        declare.create(out / "r7", declaration)
        os.symlink(external, out / "r7" / "private")
        with sources.open_threads(home.db, scratch=out / "r7" / "private"):
            expect("instrument control: an unconfined snapshot parent that is a link writes the clone outside the run", len(list(external.iterdir())), 1)
        refused("a snapshot parent that is a link out of the run is refused before any snapshot byte is written",
                lambda: run(out / "r7", tracked / "coverage.json", jobs=2), "RUN_PATH_ESCAPE")
        expect("nothing was written through the link and the refused stage left no record",
               (list(external.iterdir()), records.record_path(out / "r7", "S1").exists()), ([], False))
        declare.create(out / "r8", declaration)
        keep = out / "r8" / "keep"
        keep.mkdir()
        (keep / "artifact.txt").write_text("another stage's output")
        os.symlink(keep, out / "r8" / "scratch")  # the name an earlier shape used for its scratch directory
        os.symlink(keep, out / "r8" / "private")  # and the parent itself, a link to another directory of the run
        run(out / "r8", tracked / "coverage.json", jobs=2)
        expect("links planted where a scratch directory might be, to a directory of the run that holds an artifact: the artifact survives "
               "and only the run's own snapshot directory was removed",
               (sorted(p.name for p in keep.glob("*")), (out / "r8" / "census.json").is_file()), (["artifact.txt"], True))
        declare.create(out / "r9", declaration)
        (out / "r9" / "private").mkdir()
        (out / "r9" / "private" / "artifact.txt").write_text("already there")
        run(out / "r9", tracked / "coverage.json", jobs=2)
        expect("a private directory that already held an artifact is not taken over or emptied", sorted(p.name for p in (out / "r9" / "private").glob("*")), ["artifact.txt"])

        # F#8: the originator table is bound to the declaration; classification cannot change under it without an amendment
        shutil.copyfile(ORIGINATORS_PATH, root / "bound.json")
        bound_sha = records.sha256_bytes((root / "bound.json").read_bytes())
        with_table = {**declaration, "sources": [x for x in declaration["sources"] if x["name"] != ORIGINATORS_SOURCE]
                      + [{"name": ORIGINATORS_SOURCE, "path": str(root / "bound.json"), "sha256": bound_sha}]}
        expect("a declared table whose bytes are the pinned ones is the run's table", bound_table(with_table), (table, bound_sha))
        expect("naming the declared path again is no override", bound_table(with_table, str(root / "bound.json"))[1], bound_sha)
        refused("a --originators that is not the declared table", lambda: bound_table(with_table, str(ORIGINATORS_PATH)), "ORIGINATOR_TABLE_UNDECLARED", "is not the declared table")
        refused("a declaration that names no table", lambda: bound_table({**declaration, "sources": [x for x in declaration["sources"] if x["name"] != ORIGINATORS_SOURCE]}),
                "ORIGINATOR_TABLE_UNDECLARED", "names no 'originators' source")
        refused("a declared table with no pin", lambda: bound_table({**declaration, "sources": [x for x in with_table["sources"] if x["name"] != ORIGINATORS_SOURCE]
                                                                    + [{"name": ORIGINATORS_SOURCE, "path": str(root / "bound.json")}]}),
                "ORIGINATOR_TABLE_UNDECLARED", "carries no sha256")
        declare.create(out / "r4", with_table)
        (root / "bound.json").write_text('{"codex": {"Codex Desktop": "codex-cli"}}')  # the owner edits the table after declaring
        refused("a table edited after the declaration pinned it stops the stage", lambda: run(out / "r4", tracked / "coverage.json", jobs=2),
                "ORIGINATOR_TABLE_CHANGED", "amend the declaration")
        expect("the refused stage left no record", records.record_path(out / "r4", "S1").exists(), False)
        declare.create(out / "r5", {**declaration, "sources": [x for x in declaration["sources"] if x["name"] != ORIGINATORS_SOURCE]})
        refused("a stage over a declaration without a table", lambda: run(out / "r5", tracked / "coverage.json", jobs=2), "ORIGINATOR_TABLE_UNDECLARED")
        declare.create(out / "r6", declaration)
        refused("a stage given another table than the declared one", lambda: run(out / "r6", tracked / "coverage.json", str(root / "bound.json"), jobs=2),
                "ORIGINATOR_TABLE_UNDECLARED")

        # done-when 7: the status vocabulary is design §5.1's
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        expect("the census schema's statuses are design §5.1's", contract_mismatch(schema, STATUSES_5_1), [])
        expect("the endings of an eligible session are the terminal statuses of the coverage state", STATUSES_5_1[6:], coverage.TERMINAL)
        uncited = {**schema, "$comment": "design §0.0"}
        expect("a census schema that cites another section is named", contract_mismatch(uncited, STATUSES_5_1),
               ["CONTRACT_MISMATCH census (design §5.1): $comment does not cite the section"])
        for how, mutate in (("lacking one", lambda e: e.remove("nothing_new")), ("adding one", lambda e: e.append("quarantined"))):
            mutated = copy.deepcopy(schema)
            mutate(mutated["$defs"]["transcript"]["properties"]["status"]["enum"])
            expect(f"a schema {how} status is named", [e.split(":")[0] for e in contract_mismatch(mutated, STATUSES_5_1)], ["CONTRACT_MISMATCH census (design §5.1)"])

        # D-20261106-208882: a row the census leaves unread lies against the window by the best evidence its files give -
        # the file-time bound first, its record timestamps where the bound cannot rule it out, undetermined otherwise
        lay = Home(root / "overlap")
        U = lambda n: f"c00000{n:02d}-0000-4000-8000-0000000000aa"  # noqa: E731
        UX = lambda n: f"019e00{n:02d}-0000-7000-8000-0000000000aa"  # noqa: E731
        sept = [f"2026-09-01T10:0{k}:00.000Z" for k in range(6)]
        unstamped = [{k: v for k, v in r.items() if k != "timestamp"} for r in fx_claude(U(4), entry=None)]
        lay.claude(U(1), fx_claude(U(1), entry=None), history=False)  # unknown: records in the window, written in it
        lay.claude(U(2), fx_claude(U(2), entry=None, stamps=sept), mtime=fx_when(1, 9), history=False)  # last written before it
        lay.claude(U(3), fx_claude(U(3), entry=None, stamps=sept), history=False)  # records before it, written in it
        lay.claude(U(4), unstamped, history=False)  # no timestamp at all, written in the window
        lay.claude(U(6), [{**r, "sessionId": U(6)} for r in unstamped], mtime=fx_when(1, 9), history=False)  # the same, written before it
        lay.claude(U(5), fx_claude(U(5), entry=None, stamps=sept), mtime=fx_when(1, 9), history=False)  # an unknown root out of the window
        lay.child(U(5), "agent-in", fx_claude(U(5)))  # ... whose member has records in it
        lay.claude(U(7), fx_claude(U(7), entry="sdk-cli"), history=False)  # an excluded root
        lay.child(U(7), "agent-ex", fx_claude(U(7)))  # ... whose member is never looked at
        lay.claude(U(8), fx_claude(U(8)))  # an eligible session, read in full
        lay.codex(UX(1), fx_codex(UX(1), "vscode", "NewClient"), indexed=False)  # unknown Codex, in the window
        lay.codex(UX(2), fx_codex(UX(2), "vscode", "NewClient", month=9, day=1), mtime=fx_when(1, 9), indexed=False)  # out by the bound
        for n, when in ((3, fx_when(5)), (4, fx_when(1, 9))):  # unreadable rollouts, written in the window and before it
            bad = lay.codex(UX(n), [], raw=b"not zstd at all", zst=False, indexed=False)
            bad = bad.rename(bad.with_name(bad.name + ".zst"))
            os.utime(bad, (when, when))
        # unknown Codex threads in two files, the window in one of them: every file's evidence decides the row, whichever
        # comes first (W review of WP-08d r1, F1). UX5's first file was last written before the window and its second
        # holds records in it; UX6's first holds records in the window and its second only records after it
        lay.codex(UX(5), fx_codex(UX(5), "vscode", "NewClient", month=9, day=20), mtime=fx_when(20, 9), indexed=False,
                  name_at="2026-09-20T10-00-00")
        lay.codex(UX(5), fx_codex(UX(5), "vscode", "NewClient"), indexed=False, name_at="2026-10-03T10-00-00")
        lay.codex(UX(6), fx_codex(UX(6), "vscode", "NewClient"), indexed=False, name_at="2026-10-03T10-00-00")
        lay.codex(UX(6), fx_codex(UX(6), "vscode", "NewClient", day=10), mtime=fx_when(10), indexed=False,
                  name_at="2026-10-10T10-00-00", day=10)
        lay.finish()
        laid, _laid_state = build(lay.run(), empty, table, table_sha, jobs=2, scratch=scratch)
        laid_by = {key_of(e): (e["status"], e["window_overlap"]) for e in laid["transcripts"]}
        want_laid = {cid(U(1)): ("unknown_provenance", "inside"), cid(U(2)): ("unknown_provenance", "before_window"),
                     cid(U(3)): ("unknown_provenance", "context_only"), cid(U(4)): ("unknown_provenance", "undetermined"),
                     cid(U(6)): ("unknown_provenance", "before_window"), cid(U(5)): ("unknown_provenance", "before_window"),
                     cid(f"{U(5)}/agent-in"): ("child_of", "inside"), cid(U(7)): ("excluded", None),
                     cid(f"{U(7)}/agent-ex"): ("child_of", None), cid(U(8)): ("eligible", "inside"),
                     xid(UX(1)): ("unknown_provenance", "inside"), xid(UX(2)): ("unknown_provenance", "before_window"),
                     xid(UX(3)): ("unreadable", "undetermined"), xid(UX(4)): ("unreadable", "before_window")}
        expect("D-208882: an unread row lies against the window by its evidence - the file-time bound, its record timestamps "
               "where the bound cannot decide, undetermined where neither can - and a member of an unknown root is looked at "
               "while one of an excluded root is not", {k: laid_by.get(k) for k in want_laid}, want_laid)
        expect("D-208882: the census document with the new window_overlap values meets its schema and its sets add up",
               (validate.validate_instance(validator(), laid), account(laid)), ([], []))
        laid_rows = {key_of(e): e for e in laid["transcripts"]}
        split = {xid(UX(n)): (laid_by.get(xid(UX(n))), len(segments_of(laid_rows[xid(UX(n))])) if xid(UX(n)) in laid_rows else 0)
                 for n in (5, 6)}
        expect("D-208882: an unread thread in two files lies by the evidence of both - an old first file and a second in the "
               "window straddle its start, a first in the window and a second after it straddle its end",
               split, {xid(UX(5)): (("unknown_provenance", "straddles_start"), 2), xid(UX(6)): (("unknown_provenance", "straddles_end"), 2)})
        # ... and the observation basis S3 settles over them (stage_read.observation_scope, imported here so that the
        # census's own evidence is what the scope is judged on): each, beside a unit read whole, keeps it incomplete, named
        from runlib import stage_read, views
        alone = []
        for n in (5, 6):
            doc = copy.deepcopy(laid)
            doc["transcripts"] = [e for e in doc["transcripts"] if key_of(e) in (cid(U(8)), xid(UX(n)))]
            scope, causes = stage_read.observation_scope(doc, [{"transcript": cid(U(8)), "status": "read_complete"}],
                                                         {cid(U(8)): (True, True)})
            alone.append((views.coverage_basis(scope), [c["session"] for c in causes["sessions"]], causes["sources"]))
        expect("D-208882: the observation scope over an unread thread in two files, one of them in the window, is incomplete "
               "and names it, whichever file comes first", alone,
               [("incomplete", [xid(UX(5))], []), ("incomplete", [xid(UX(6))], [])])


def self_test():
    if not os.access(ZSTD, os.X_OK):
        print(f"census --self-test [FAIL] ZSTD_UNAVAILABLE {ZSTD}: the compressed fixtures need the declared zstd")
        return 1
    checks = Checks()
    try:
        controls(checks)
    except Exception as exc:  # a reverted check fails the control it served, by name, not as a traceback
        checks.failures.append(f"RAISED {exc!r} after control {checks.ran[-1] if checks.ran else '(none)'!r}")
    finally:
        for home in Home.open_writers:
            home.close()
    for failure in checks.failures:
        print(f"census --self-test [FAIL] {failure}")
    if checks.failures:
        return 1
    print(f"census --self-test: OK ({len(checks.ran)} controls)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: census.py --self-test")
    sys.exit(self_test())
