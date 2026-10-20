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
its head. Counting follows §5.3: a lineage counts once, through its root, when its component has exactly
one root and a host-written index names that root.

Identity is `(host, session id)`: a transcript is keyed `<host>:<id>` (`lineage.identity`) in the coverage
state, in lineage components and in S3's results. The originator table is a declared source of the run
(`name: originators`, its `path` and `sha256`); S1 reads exactly those bytes.

An S3 result, which `reconcile` takes, is `{transcript, status, readings, pending_events, resolved_events}`,
`readings` a list of `{version, sha, read, processed}` over the versions it read (`processed` is keyed by
window id); `coverage.apply_results` says what each field must satisfy.

The legacy `session-distill/census.py` is untouched until the cutover (WP-22); this is `distill.py census`.
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


def blank(host, ident, source, path=None, **fields):
    entry = {"host": host, "id": ident, "source": source, "path": path, "sha256": None, "status": "eligible", "reason": None,
             "parent": None, "originator": None, "entrypoint": None, "source_class": None,
             "lineage": {"component": None, "root": None, "unique_root": False, "affirmed": [], "measurement_pending": False},
             "provenance": None, "counted": False, "window_overlap": None, "pin": {"content_ref": None},
             "versions": [], "owned": [], "work": {"version": None, "in_window": [], "backlog": []}, "alt_paths": []}
    entry.update(fields)
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


def read_full(file, zstd, scan, own, prev):
    """One pass over a whole transcript: `{sha, record_count, prefix_sha, prefix_ok, owned, before, after}`.

    `sha` hashes everything read, `prefix_sha` the complete lines only, so a record the host is still
    writing moves the first and not the second. `prefix_ok` answers §5.2's append-only test against `prev`,
    the version on record: did the first `prev.record_count` lines hash to its `prefix_sha`."""
    whole, count, boundary, tail = hashlib.sha256(), 0, None, b""
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
        count += 1
        if prev and count == prev["record_count"]:
            boundary = whole.hexdigest()
    prefix = whole.hexdigest()
    whole.update(tail)
    return {"sha": whole.hexdigest(), "record_count": count, "prefix_sha": prefix,
            "prefix_ok": None if prev is None else boundary == prev["prefix_sha"], **own.finish(count)}


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
        if meta is None:
            entry.update(status="unknown_provenance", reason="no_session_meta")
        elif kind == "subagent":
            entry.update(status="child_of", parent=parent) if parent else entry.update(status="unknown_provenance", reason="child_without_parent")
        else:
            status, reason, cls = lineage.classify_codex(source, entry["originator"], ("codex", ident) in pins, table)
            entry.update(status=status, reason=reason, source_class=cls)
    entry["pin"]["content_ref"] = pins.get((host, ident))
    return entry


def provenance_of(entry, host, threads, history, desktop):
    """`indexed`, `not_indexed` or `index_missing` from the index the host itself writes (design §5.3).

    Codex: a `threads` row of this id whose `rollout_path` is the file, or the file before in-place
    compression (the index keeps the pre-compression path). Claude CLI: a `history.jsonl` entry with the
    id. Claude Desktop: a session-index file whose `cliSessionId` is the id."""
    if host == "codex":
        if threads is None:
            return "index_missing"
        row = threads.get(entry["id"])
        if not row or not row["rollout_path"]:
            return "not_indexed"
        have = os.path.realpath(row["rollout_path"])
        want = os.path.realpath(entry["path"])
        return "indexed" if have in (want, want[:-len(".zst")] if want.endswith(".zst") else want) else "not_indexed"
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
    pins, bad = (sources.read_pins(src["agent_bios_state"]) if report["agent_bios_state"]["state"] == "present" else ({}, 0))
    report["agent_bios_state"]["detail"] = f"{bad} pin files ignored" if bad else None
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
        if ident in entries:  # one identity in two files: the first keeps the entry, the other is named beside it
            entries[ident]["alt_paths"].append(file["path"])
            continue
        entries[ident], extras[ident] = entry, {"file": file, "head": head}
    discovered = {}  # the identities each source named, counted before anything else is decided about them
    for entry in entries.values():
        discovered[entry["source"]] = discovered.get(entry["source"], 0) + 1
    for ident, entry in entries.items():
        if entry["status"] == "child_of" and lineage.identity(entry["host"], entry["parent"]) not in entries:
            entry.update(status="unknown_provenance", reason="orphan_child", parent=None)  # a link to nothing
        elif entry["status"] not in ("child_of", "unreadable"):
            entry["provenance"] = provenance_of(entry, entry["host"], threads, history, desktop)

    # every eligible transcript is read in full, whatever its age: its sha, its continuity against the version on
    # record, the records the window owns, and the lineage evidence wherever in the file it lies
    owed = {b["transcript"] for b in state["backlog"]} | {e["transcript"] for e in state["pending_events"]}

    def read(ident):
        file = extras[ident]["file"]
        scan, own = (lineage.ClaudeScan() if file["host"] == "claude" else lineage.CodexScan(file["stem"])), coverage.Ownership(start, end)
        try:
            return scan, own, read_full(file, zstd, scan, own, coverage.latest(state, ident)), None
        except sources.Unreadable as exc:
            return scan, own, None, str(exc)

    for ident, entry in entries.items():
        if entry["status"] != "eligible":
            continue
        scan, own, got, error = read(ident)  # one at a time: decompression runs beside it in zstd, and CPU-bound threads only fight for the GIL
        if error:
            entry.update(status="unreadable", reason=error)
        elif own.stamped == 0 and got["record_count"]:
            entry.update(status="unknown_provenance", reason="no_timestamps", source_class=None)
        else:
            extras[ident]["head"]["scan"] = scan
            coverage.observe(state, ident, got["sha"], got["record_count"], got["prefix_sha"], got["prefix_ok"])
            entry.update(sha256=got["sha"], owned=got["owned"], window_overlap=(
                "context_only" if not got["owned"] else "straddles_start" if got["before"] else "straddles_end" if got["after"] else "inside"))
    for ident, entry in entries.items():
        if entry["status"] != "eligible":
            continue
        entry["work"] = coverage.work_of(state, ident, entry["owned"], window_id)
        if not entry["work"]["in_window"] and not entry["work"]["backlog"]:
            entry["status"] = "nothing_new"
        known = state["transcripts"].get(ident, {"versions": []})["versions"]
        entry["versions"] = [{k: v[k] for k in ("sha", "record_count", "prefix_sha")} for v in known]
        entry["sha256"] = entry["sha256"] or (known[-1]["sha"] if known else None)

    # lineage over the owner's transcripts, then the counting rule (design §5.3)
    mine = {i: e for i, e in entries.items() if e["status"] in ("eligible", "nothing_new")}
    nodes = [extras[i]["head"]["scan"].lineage_node(e["id"]) for i, e in mine.items()]
    linked, pending, active = lineage.components(nodes), {n["id"]: n.get("pending", False) for n in nodes}, {}
    for ident, entry in mine.items():
        entry["lineage"] = {**linked[ident], "measurement_pending": pending[ident]}
        active[entry["lineage"]["component"]] = active.get(entry["lineage"]["component"], False) or bool(entry["owned"])
    for ident, entry in mine.items():
        lin = entry["lineage"]
        entry["counted"] = bool(lin["unique_root"] and lin["root"] == ident and entry["provenance"] == "indexed"
                                and active[lin["component"]] and entry["source_class"] in CLASSES)
    named = index_only(set(entries), threads, history, desktop, pins, table, start, end)
    # work the coverage state still owes on a transcript that is no longer here is a lost transcript, not a vanished obligation
    lost = [blank(*lineage.split_identity(ident), "coverage_state", status="known_absent", reason="owed_by_coverage")
            for ident in sorted(owed - set(entries) - {key_of(e) for e in named})]
    if lost:
        report["coverage_state"] = {"state": "present", "path": None, "discovered": None, "unrecognized": 0, "totals": None,
                                    "detail": "transcripts the coverage state owes work on that are no longer here"}
    for entry in named + lost:
        discovered[entry["source"]] = discovered.get(entry["source"], 0) + 1
    everything = list(entries.values()) + named + lost
    for name, rep in report.items():
        if rep["state"] == "present" and name != "agent_bios_state":
            rep["discovered"] = discovered.get(name, 0)
    census = summarize(everything, report, run["kind"], window_id, table, table_sha, state)
    return census, (state if run["kind"] == "periodic" else base)


def totals_of(entries, report):
    for name, rep in report.items():
        if rep["state"] == "present" and name != "agent_bios_state":
            rep["totals"] = {}
            for e in entries:
                if e["source"] == name:
                    rep["totals"][e["status"]] = rep["totals"].get(e["status"], 0) + 1


def summarize(entries, report, kind, window_id, table, table_sha, state):
    """Fold per-transcript entries into the census document and check that nothing was dropped."""
    totals_of(entries, report)
    entries.sort(key=lambda e: (e["source"], e["path"] or "", e["id"]))
    originators, provenance, pins, components = {}, {}, {}, {}
    for e in entries:
        if e["originator"] is not None and e["entrypoint"] == "vscode" and e["path"]:
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
              "pending_events": copy.deepcopy(state["pending_events"]), "transcripts": entries}
    errors = account(census)
    if errors:
        raise Refused("\n".join(errors))
    return census


def account(census):
    """Violations of the set accounting of §5.1, empty when it holds: no identity appears twice, a source with
    no total files nothing under it, and each source's statuses add up to the identities it discovered."""
    errors, seen = [], {}
    for e in census["transcripts"]:
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
    (SET_MISMATCH otherwise, listing the sessions). The inputs are not touched, and the reconciled census
    must still conform to its schema."""
    census, window_id = copy.deepcopy(census), census["window"]
    waiting = {key_of(e): e for e in census["transcripts"] if e["status"] == "eligible"}
    got = [r["transcript"] for r in results]
    missing, extra = sorted(set(waiting) - set(got)), sorted(set(got) - set(waiting))
    repeated = sorted({i for i in got if got.count(i) > 1})
    if missing or extra or repeated:
        raise Refused(f"SET_MISMATCH S3 results do not match the eligible sessions: missing={missing} extra={extra} repeated={repeated}")
    # a targeted run's results are held to the periodic rules against the state the census observed, and then discarded
    seen = state if kind == "periodic" else coverage.observed(state, waiting.values())
    after = coverage.apply_results(seen, window_id, kind, results, {i: e["owned"] for i, e in waiting.items()})
    for result in results:
        waiting[result["transcript"]]["status"] = result["status"]
    totals_of(census["transcripts"], census["sources"])
    census["pending_events"] = copy.deepcopy(after["pending_events"])
    errors = account(census) + [f"CENSUS_INVALID {p}" for p in validate.validate_instance(validator(), census)[:5]]
    if errors:
        raise Refused("\n".join(errors))
    flags = dict(zip(("accounted", "fully_read"), coverage.accounted(census["transcripts"], after, window_id)))
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
            f"  independence: {ind['unknown_components']}/{ind['components']} components and {ind['unknown_sessions']}/{ind['sessions']} sessions unknown"]


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

    def codex(self, tid, rows, where="sessions", zst=False, indexed=True, source=None, mtime=None, raw=None, day=3):
        directory = self.sessions / "2026" / "10" / f"{day:02d}" if where == "sessions" else self.archived
        path = directory / f"rollout-2026-10-{day:02d}T10-00-00-{tid}.jsonl"
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
        (self.state / "sessions" / "pins" / "codex").mkdir(parents=True, exist_ok=True)
        (self.state / "sessions" / "pins" / "codex" / f"{tid}.json").write_text(
            json.dumps({"host": "codex", "session_id": tid, "content_ref": "sha256:fixture"}))

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


def fx_check(census, expected):
    """Violations of a fixture table `{name: (identity, {attribute: value})}`, each naming its fixture."""
    by_id, errors = {key_of(e): e for e in census["transcripts"]}, []
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


def fx_results(census, status="read_complete", skip=(), extra_read=None, pending=None, resolved=None):
    """S3's results for every eligible session: it read and processed everything the window owns (and the backlog),
    each range credited to the version it belongs to. `skip`, `extra_read`, `pending` and `resolved` are keyed by identity."""
    out = []
    for e in census["transcripts"]:
        ident = key_of(e)
        if e["status"] != "eligible" or ident in skip:
            continue
        newest = e["work"]["version"]
        readings = {newest: {"version": newest, "sha": e["sha256"], "processed": {census["window"]: e["work"]["in_window"]},
                             "read": coverage.union(coverage.union(e["owned"], e["work"]["in_window"]), (extra_read or {}).get(ident, []))}}
        for b in e["work"]["backlog"]:
            got = readings.setdefault(b["version"], {"version": b["version"], "sha": e["versions"][b["version"]]["sha"], "processed": {}, "read": []})
            got["processed"][b["window"]] = coverage.union(got["processed"].get(b["window"], []), b["unread"])
            got["read"] = coverage.union(got["read"], b["unread"])
        out.append({"transcript": ident, "status": status, "readings": [readings[v] for v in sorted(readings)],
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
        return {e["id"]: e for e in census["transcripts"]}

    def by_key(census):
        return {key_of(e): e for e in census["transcripts"]}

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
               (sorted(e["host"] for e in census["transcripts"] if e["id"] == same), sorted(k for k in state["transcripts"] if k.endswith(same)), account(census)),
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
        unreadable = {e["id"]: e for e in census_unzstd["transcripts"] if e["status"] == "unreadable"}
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
               (t_b["status"], t_b["work"]["in_window"], coverage.latest(state_b, MK)["processed"] == coverage.latest(state1, MK)["processed"] != {}),
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
        coverage.apply_results = lambda st, w, kind, res, owned: original(st, w, "periodic", res, owned)  # a writer that ignores the run kind
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

        # the legacy census-to-digest handoff of the runbook still runs on a fixture home (the cutover is WP-22)
        legacy = Home(root / "legacy")
        sid = "c0000050-0000-4000-8000-000000000000"
        stamp = datetime.datetime(2026, 10, 5, 12).timestamp()
        legacy.put(legacy.projects / "-fx" / f"{sid}.jsonl", [
            {"type": "user", "entrypoint": "cli", "message": {"role": "user", "content": "make the weekly summary shorter"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "ok"}}])
        legacy.history_path.write_text(json.dumps({"sessionId": sid, "timestamp": int(stamp * 1000), "display": "make the weekly summary shorter"}) + "\n")
        (legacy.root / ".codex" / "history.jsonl").write_text("")
        scratch = root / "legacy-out"
        scratch.mkdir()
        env = {"HOME": str(legacy.root), "PATH": os.environ.get("PATH", "")}
        step1 = subprocess.run([sys.executable, "-I", str(HERE / "census.py"), "--end", "2026-10-08", "--window-days", "7", "--out", str(scratch)],
                               capture_output=True, text=True, env=env)
        step2 = subprocess.run([sys.executable, "-I", str(HERE / "digest.py"), "--census", str(scratch / "census.json"), "--out", str(scratch)],
                               capture_output=True, text=True, env=env)
        digests = json.loads((scratch / "digests.json").read_text()) if (scratch / "digests.json").exists() else []
        expect("census.py --end then digest.py: the documented handoff still runs on the fixture",
               (step1.returncode, step2.returncode, [(d["session_id"], d["goals"]) for d in digests]), (0, 0, [(sid, ["make the weekly summary shorter"])]))


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
