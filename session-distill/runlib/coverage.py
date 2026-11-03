#!/usr/bin/env python3
"""The coverage state of design §5.2, and the range algebra it rests on.

`session-distill/coverage.json` records, per transcript, a list of versions `{sha,
record_count, prefix_sha}` and, per version, two kinds of range over its records (0-based
record index, half-open): **read** (seen in a view, for any reason) and **processed for
window w** (owned by w and extracted for it). Only processed ranges discharge work: a record
read as context for another window stays unprocessed for its own, and the run that owns it
reads it again. Records are the lines of the decompressed transcript, so record `i` is line
`i + 1`. A *version* is a continuity chain: an append updates it in place (`sha`,
`record_count`, `prefix_sha` move, the ranges before it stay true), a rewrite starts the next
one. Pending events, the backlog of unread ranges and the window flags live beside it.

This module owns the state and its transitions; it does not decide when to promote a run's
state to the tracked file. `write_atomic` is that last step (lock, base-hash check, temporary
file, fsync, rename), for S12. Targeted runs read but never advance periodic coverage:
`check_targeted` is the guard that says so.

A transcript is keyed by its identity, `<host>:<session id>` (`lineage.identity`). Work has the identity
(transcript, version, window): a record range is owed to one version of one transcript for one window, so
an S3 result names the version it read and may credit a range only to the current window's own records of
the latest version, or to a backlog entry of that same version and window, and only for records the same
result read: a record read earlier as context is read again by the run that owns it. A targeted run's
results are held to the same rules against the state it observed, and then discarded. One result answers a
unit, a root with its members (D-20261103-85f3e8): a member is a transcript of its own here, and the result's
readings credit it by name.

Failures are named by their first word: COVERAGE_INVALID, COVERAGE_BASE_STALE,
TARGETED_ADVANCED_COVERAGE, PROCESSED_OUTSIDE_OWNED, PROCESSED_UNREAD, VERSION_MISMATCH,
RESULT_INCONSISTENT, RESULT_STATUS_INVALID.

  coverage.py --self-test
"""
import bisect
import copy
import datetime
import itertools
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import zoneinfo

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import lineage, records, stagelock, validate
from runlib.records import Refused

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[1] / "schemas" / "coverage.schema.json"
TERMINAL = ("read_complete", "read_partial", "failed", "deferred", "nothing_new")  # design §5.1
CARRIED = ("read_partial", "failed", "deferred")  # the ones whose unread ranges wait in the backlog
# the backlog status of records S1 found appended to a version after the run of the window that owns them (review c0fix
# r1 #1): no result left them unread, they had not been written when that window was read
APPENDED = "appended"
_VALIDATOR = []


def validator():
    if not _VALIDATOR:
        _VALIDATOR.append(validate.compile_schema(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))))
    return _VALIDATOR[0]


# ---- ranges: sorted, merged, non-empty [start, end) pairs over record indexes -----------------

def normalize(ranges):
    merged = []
    for start, end in sorted(map(tuple, ranges)):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def union(a, b):
    return normalize([*a, *b])


def subtract(a, b):
    out, cuts = [], normalize(b)
    for start, end in normalize(a):
        for cut_start, cut_end in cuts:
            if cut_end <= start or cut_start >= end:
                continue
            if cut_start > start:
                out.append([start, cut_start])
            start = max(start, cut_end)
            if start >= end:
                break
        if start < end:
            out.append([start, end])
    return out


def window_bounds(window):
    """(start, end, id) of a run's half-open window (design §4.1): aware instants and the key the
    state files it under. A window without an offset is read in its own `tz`."""
    zone = zoneinfo.ZoneInfo(window["tz"])
    start, end = (datetime.datetime.fromisoformat(window[k]) for k in ("start", "end"))
    start, end = (t if t.tzinfo else t.replace(tzinfo=zone) for t in (start, end))
    return start, end, f"{window['start']}/{window['end']}@{window['tz']}"


def bounds_of(window_id):
    """(start, end) of the window an id names, read back the way `window_bounds` wrote it (`<start>/<end>@<tz>`)."""
    span, _at, tz = window_id.rpartition("@")
    start, _slash, end = span.partition("/")
    try:
        return window_bounds({"start": start, "end": end, "tz": tz})[:2]
    except (ValueError, zoneinfo.ZoneInfoNotFoundError) as exc:
        raise Refused(f"COVERAGE_INVALID window {window_id!r}: {exc}") from exc


def instant(stamp):
    """A record's timestamp as an aware instant (one without an offset is UTC), or None when it has none that parses."""
    try:
        when = datetime.datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=datetime.timezone.utc)


class Ownership:
    """Which records a window owns (design §5.2): a record belongs to the window when its timestamp
    is in `[start, end)`. A record with no timestamp takes its predecessor's; leading ones take the
    first that has one."""

    def __init__(self, start, end):
        self.start, self.end, self.runs, self.stamped = start, end, [], 0

    def feed(self, index, stamp):
        when = instant(stamp)
        if when is None:
            return
        self.stamped += 1
        side = -1 if when < self.start else 1 if when >= self.end else 0
        if not self.runs:
            self.runs.append([side, 0])
        elif self.runs[-1][0] != side:
            self.runs.append([side, index])

    def finish(self, count):
        """`{owned, before, after}`: the owned ranges and whether records lie before or after the window."""
        bounds = [run[1] for run in self.runs[1:]] + [count]
        owned = normalize([[run[1], end] for run, end in zip(self.runs, bounds) if run[0] == 0])
        sides = {run[0] for run in self.runs}
        return {"owned": owned, "before": -1 in sides, "after": 1 in sides}


class Owners:
    """Which of several windows (`[(start, end, id)]`) own each record, by `Ownership`'s rule: a record belongs to every
    window whose `[start, end)` holds its timestamp, one without a timestamp to its predecessor's windows, leading ones
    to the first stamped record's. The windows are searched by their start, and the search goes back only while an
    earlier window still reaches past the record, so windows that do not overlap cost a comparison or two a record."""

    def __init__(self, windows):
        self.windows = sorted(windows, key=lambda w: (w[0], w[1]))
        self.starts = [w[0] for w in self.windows]
        self.reach = list(itertools.accumulate((w[1] for w in self.windows), max))
        self.runs = []

    def feed(self, index, stamp):
        when = instant(stamp)
        if when is None:
            return
        found, k = [], bisect.bisect_right(self.starts, when) - 1
        while k >= 0 and self.reach[k] > when:
            if self.windows[k][1] > when:
                found.append(self.windows[k][2])
            k -= 1
        owners = tuple(sorted(found))
        if not self.runs:
            self.runs.append([owners, 0])
        elif self.runs[-1][0] != owners:
            self.runs.append([owners, index])

    def finish(self, count):
        """`{window id: owned ranges}` for every window that owns a record."""
        bounds = [run[1] for run in self.runs[1:]] + [count]
        owned = {}
        for (owners, start), end in zip(self.runs, bounds):
            for window in owners:
                owned.setdefault(window, []).append([start, end])
        return {window: normalize(ranges) for window, ranges in owned.items()}


# ---- the state --------------------------------------------------------------------------------

def new_state():
    return {"transcripts": {}, "pending_events": [], "backlog": [], "windows": {}}


def digest(state):
    return records.bound_digest(state)


def check_state(state):
    """Violations of the state's own invariants, beyond its schema; empty when it holds."""
    errors = list(map(lambda e: f"COVERAGE_INVALID {e}", validate.validate_instance(validator(), state)))
    if errors:
        return errors
    for tid, entry in state["transcripts"].items():
        for number, version in enumerate(entry["versions"]):
            where = f"{tid} version {number}"
            sets = [("read", version["read"])] + [(f"processed[{w}]", r) for w, r in version["processed"].items()]
            for label, ranges in sets:
                if ranges != normalize(ranges):
                    errors.append(f"COVERAGE_INVALID {where} {label}: ranges are not sorted, merged and non-empty")
                elif ranges and ranges[-1][1] > version["record_count"]:
                    errors.append(f"COVERAGE_INVALID {where} {label}: a range ends past record_count {version['record_count']}")
            for w, ranges in version["processed"].items():
                if subtract(ranges, version["read"]):
                    errors.append(f"COVERAGE_INVALID {where} processed[{w}]: records processed that were never read")
    ids = [event["id"] for event in state["pending_events"]]
    errors += [f"COVERAGE_INVALID pending event id {i!r} repeats" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for item in state["pending_events"] + state["backlog"]:
        versions = state["transcripts"].get(item["transcript"], {}).get("versions", [])
        if item["version"] >= len(versions):
            errors.append(f"COVERAGE_INVALID {item.get('id') or 'backlog'} names version {item['version']} of {item['transcript']}, which is not in the state")
    return errors


def load(path):
    """(state, sha256 of the file's bytes). A file that is absent is the empty state, which hashes as
    the committed initial file does; one that does not conform is refused by name."""
    path = pathlib.Path(path)
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        data = records.json_text(new_state()).encode("utf-8")
    except OSError as exc:
        raise Refused(f"COVERAGE_INVALID {path}: {exc.strerror or exc}") from exc
    try:
        state = json.loads(data)
    except ValueError as exc:
        raise Refused(f"COVERAGE_INVALID {path}: not JSON: {exc}") from exc
    errors = check_state(state) if isinstance(state, dict) else ["COVERAGE_INVALID the state is not an object"]
    if errors:
        raise Refused("\n".join(errors))
    return state, records.sha256_bytes(data)


def latest(state, tid):
    versions = state["transcripts"].get(tid, {}).get("versions")
    return versions[-1] if versions else None


def observe(state, tid, sha, record_count, prefix_sha, prefix_ok):
    """Fold one reading of transcript `tid` into the state; returns `new`, `same`, `append` or `rewritten`.

    `prefix_ok` is the append-only test (§5.2): did the first `record_count` records of the previous
    latest version hash to its `prefix_sha` in what was just read. None when there was no previous."""
    versions = state["transcripts"].setdefault(tid, {"versions": []})["versions"]
    fresh = {"sha": sha, "record_count": record_count, "prefix_sha": prefix_sha, "read": [], "processed": {}}
    if not versions:
        versions.append(fresh)
        return "new"
    last = versions[-1]
    if last["sha"] == sha:
        return "same"
    if prefix_ok and record_count >= last["record_count"]:
        last.update(sha=sha, record_count=record_count, prefix_sha=prefix_sha)
        return "append"
    versions.append(fresh)
    return "rewritten"


def carry_appended(state, tid, late):
    """Hold in the backlog what S1 found appended to `tid`'s latest version and owned by a window already run: `late` maps
    such a window's id to the records of the append it owns (review c0fix r1 #1). D-20261103-8facee gives what the host
    appends after a census to the next run, and the next run reads another window: without this, a record stamped inside
    a window that has been read - a line the host was still writing then, or one written late - is owned by no run. Each
    is owed to its own window, under the status `appended`; what that window processed or the backlog already holds is
    not owed again. Returns the entries added."""
    versions = state["transcripts"][tid]["versions"]
    number, version, added = len(versions) - 1, versions[-1], []
    for window, ranges in sorted(late.items()):
        held = normalize([r for b in state["backlog"] if (b["transcript"], b["version"], b["window"]) == (tid, number, window)
                          for r in b["unread"]])
        unread = subtract(subtract(ranges, version["processed"].get(window, [])), held)
        if unread:
            added.append({"transcript": tid, "version": number, "window": window, "status": APPENDED, "unread": unread})
    state["backlog"] += added
    return added


def work_of(state, tid, owned, window_id):
    """What a run owes one transcript: `version` (the latest, which `in_window` is about), `in_window` (owned
    records not yet processed for the window) and `backlog` (unread ranges carried from earlier runs, each
    naming the version and window it is owed to, read first)."""
    version = latest(state, tid)
    done = version["processed"].get(window_id, []) if version else []
    carried = [{"window": b["window"], "version": b["version"], "unread": b["unread"]} for b in state["backlog"] if b["transcript"] == tid]
    return {"version": len(state["transcripts"][tid]["versions"]) - 1 if version else None,
            "in_window": subtract(owned, done), "backlog": carried}


def accounted(entries, state, window_id, units=None, owned=None):
    """(accounted, fully_read) of a window over the census `entries` that are eligible (design §5.2).

    Accounted: every eligible session has a terminal status, and a session whose reading did not finish has
    what it still owes in the backlog: the unread records of this window it owns, and whatever it carries
    from earlier windows, each under the window it belongs to. A session is its unit (D-20261103-85f3e8), and the
    state names its files (D-20261103-a7128a): `units` maps a root's identity to `(its own files' keys, its members'
    files' keys)`, `owned` a key to the records the window owns there, and every file's unread records are owed the
    same way. Without them a session is one file under its identity and owns what its entry says. Fully read: every
    one finished or had nothing to read."""
    eligible = [e for e in entries if e["status"] == "eligible" or e["status"] in TERMINAL]
    terminal = all(e["status"] in TERMINAL for e in eligible)
    if owned is None:
        owned = {lineage.identity(e["host"], e["id"]): e.get("owned", []) for e in entries}

    def owes_nothing_unheld(entry):
        root = lineage.identity(entry["host"], entry["id"])
        own, members = (units or {}).get(root, ([root], []))
        held_any = False
        for tid in list(own) + list(members):
            version = latest(state, tid)
            remaining = subtract(owned.get(tid, []), version["processed"].get(window_id, []) if version else [])
            held = [b for b in state["backlog"] if b["transcript"] == tid and b["unread"]]
            held_any = held_any or bool(held)
            if subtract(remaining, normalize([r for b in held if b["window"] == window_id for r in b["unread"]])):
                return False
        return held_any

    carried = all(owes_nothing_unheld(e) for e in eligible if e["status"] in CARRIED)
    return terminal and carried, all(e["status"] in ("read_complete", "nothing_new") for e in eligible)


def observed(state, files):
    """A copy of `state` as the census observed it: each of the census's `files` (`census.segments_of`: a `key`, the
    `versions` S1 recorded and its `work`) has those versions, an append moved in place and a rewrite added, with nothing
    read or processed in a new one; and the backlog S1 added for records appended after their window was run
    (`carry_appended`), which the work carries and the state does not."""
    after = copy.deepcopy(state)
    for file in files:
        have = after["transcripts"].setdefault(file["key"], {"versions": []})["versions"]
        for number, version in enumerate(file["versions"]):
            if number < len(have):
                have[number].update(version)
            else:
                have.append({**version, "read": [], "processed": {}})
        for b in (file.get("work") or {}).get("backlog", []):
            held = normalize([r for h in after["backlog"] if (h["transcript"], h["version"], h["window"]) == (file["key"], b["version"], b["window"])
                              for r in h["unread"]])
            unread = subtract(b["unread"], held)
            if unread:
                after["backlog"].append({"transcript": file["key"], "version": b["version"], "window": b["window"], "status": APPENDED, "unread": unread})
    return after


def apply_results(state, window_id, kind, results, owned, units=None):
    """The state after S3's `results` (a copy; `state` is not touched).

    A result is `{transcript, status, readings, pending_events, resolved_events}`, `readings` a list of
    `{version, sha, read, processed}` with `processed` keyed by window id. Its status is one of the terminal
    statuses whatever the run kind. A reading names the version it read and its sha; a range is credited to a
    window only when that reading read it, and the window owns it in the latest version (`owned` maps a transcript
    to the ranges the current window owns there) or a backlog entry of that same transcript, version and window
    still holds it. A targeted run reads but never advances coverage: its results are held to the same rules and
    the state it gets back is the one it gave.

    One result answers a unit (D-20261103-85f3e8), and the state names its files (D-20261103-a7128a): `units` maps the
    result's transcript to `(the keys of its own files, the keys of its members' files)`, by default its identity alone.
    A reading names the file it read by `transcript`, which a session of one file may leave out; a reading naming a
    file outside the unit is refused, and so is one that leaves it out of a session written across several files. A
    `read_complete` or `nothing_new` result leaves nothing of the unit unprocessed, and a carried one keeps every
    file's unread ranges in the backlog under that file. A pending event names its file the same way, by default the
    session's last."""
    folded = _fold(state, window_id, results, owned, units or {})
    return folded if kind == "periodic" else copy.deepcopy(state)


def _fold(state, window_id, results, owned, units):
    for result in results:
        if result["status"] not in TERMINAL:
            raise Refused(f"RESULT_STATUS_INVALID {result['transcript']}: {result['status']!r} is not a terminal status; S3 ends in one of {TERMINAL}")
    after = copy.deepcopy(state)
    for result in results:
        root = result["transcript"]
        own, members = units.get(root, ([root], []))
        unit = list(own) + list(members)
        newest, credited, seen = {}, {}, set()
        for tid in unit:
            versions = after["transcripts"].get(tid, {}).get("versions", [])
            if tid in own and not versions:
                raise Refused(f"VERSION_MISMATCH {tid}: the state has no version of it")
            newest[tid] = len(versions) - 1
        for reading in result["readings"]:
            tid, n = reading.get("transcript", own[0] if len(own) == 1 else None), reading["version"]
            if tid is None:
                raise Refused(f"RESULT_INCONSISTENT {root}: a reading names no file, and the session is written across "
                              f"{len(own)} files ({own}); a reading names the one it read")
            if tid not in newest:
                raise Refused(f"RESULT_INCONSISTENT {root}: a reading names {tid}, which is not a member of its unit")
            if (tid, n) in seen:
                raise Refused(f"RESULT_INCONSISTENT {root}: version {n} of {tid} is read twice in one result")
            seen.add((tid, n))
            versions = after["transcripts"].get(tid, {}).get("versions", [])
            if not 0 <= n < len(versions) or versions[n]["sha"] != reading["sha"]:
                have = versions[n]["sha"][:12] if 0 <= n < len(versions) else "absent"
                raise Refused(f"VERSION_MISMATCH {tid}: S3 read version {n} as {reading['sha'][:12]}, the state has {have}")
            version = versions[n]
            version["read"] = union(version["read"], reading["read"])
            for w, ranges in reading["processed"].items():
                if not ranges:
                    continue
                if subtract(ranges, reading["read"]):
                    raise Refused(f"PROCESSED_UNREAD {tid}: version {n} processed {subtract(ranges, reading['read'])} for window {w}, which this result "
                                  "did not read; a record read earlier as context is read again by the run that processes it")
                allowed = normalize([r for b in after["backlog"] if (b["transcript"], b["version"], b["window"]) == (tid, n, w) for r in b["unread"]]
                                    + (owned.get(tid, []) if w == window_id and n == newest[tid] else []))
                if subtract(ranges, allowed):
                    raise Refused(f"PROCESSED_OUTSIDE_OWNED {tid}: version {n} processed {subtract(ranges, allowed)} for window {w}, which is owed "
                                  f"{allowed}; a record is processed by the run whose window owns it or that reads its backlog, never in advance")
                version["processed"][w] = union(version["processed"].get(w, []), ranges)
                credited[(tid, n, w)] = union(credited.get((tid, n, w), []), ranges)
        # the backlog of the unit: each entry loses what was credited to its own transcript, version and window; this window's,
        # on each member's latest version, is recomputed
        kept, remaining, carried_over = [], {}, False
        for entry in after["backlog"]:
            if entry["transcript"] not in newest:
                kept.append(entry)
            elif not (entry["window"] == window_id and entry["version"] == newest[entry["transcript"]]):
                entry["unread"] = subtract(entry["unread"], credited.get((entry["transcript"], entry["version"], entry["window"]), []))
                if entry["unread"]:
                    kept.append(entry)
                    carried_over = True
        for tid in unit:
            if newest[tid] < 0:
                continue
            left = subtract(owned.get(tid, []), after["transcripts"][tid]["versions"][newest[tid]]["processed"].get(window_id, []))
            if left:
                remaining[tid] = left
        if result["status"] in ("read_complete", "nothing_new") and (remaining or carried_over):
            where = next(iter(remaining.items()), None)
            raise Refused(f"RESULT_INCONSISTENT {root}: {result['status']}, but "
                          f"{f'{where[1]} of {where[0]}' if where else 'earlier-window ranges'} are still unprocessed")
        if result["status"] in CARRIED:
            if not (remaining or carried_over):
                raise Refused(f"RESULT_INCONSISTENT {root}: {result['status']}, but nothing is left unread")
            kept += [{"transcript": tid, "version": newest[tid], "window": window_id, "status": result["status"], "unread": left}
                     for tid, left in remaining.items()]
        after["backlog"] = kept
        # a result resolves only the events of its own unit: one naming an event that is not pending, or that is pending
        # on a file outside the unit, is refused before anything is removed (review c0fix r1 #5)
        pending_on = {e["id"]: e["transcript"] for e in after["pending_events"]}
        gone = set(result.get("resolved_events", []))
        foreign = sorted(i for i in gone if pending_on.get(i) not in newest)
        if foreign:
            raise Refused(f"RESULT_INCONSISTENT {root}: it resolves {foreign}, which are not pending events of its unit "
                          f"({[pending_on.get(i) for i in foreign]})")
        after["pending_events"] = [e for e in after["pending_events"] if e["id"] not in gone]
        known = {e["id"] for e in after["pending_events"]}
        for e in result.get("pending_events", []):
            where = e.get("transcript", own[-1])
            if where not in newest:
                raise Refused(f"RESULT_INCONSISTENT {root}: a pending event names {where}, which is not a file of its unit")
            if e["id"] not in known:
                after["pending_events"].append({"version": newest[where], "window": window_id, **e, "transcript": where})
    errors = check_state(after)
    if errors:
        raise Refused("\n".join(errors))
    return after


def check_targeted(base, after):
    """Violations when a targeted run's coverage is not the base it started from, byte for byte."""
    if records.json_text(base) == records.json_text(after):
        return []
    return ["TARGETED_ADVANCED_COVERAGE: a targeted run reads but never advances periodic coverage; "
            f"its state hashes {digest(after)[:12]}, the periodic base {digest(base)[:12]}"]


def write_atomic(state_dir, state, base_sha):
    """Replace `<state_dir>/coverage.json` with `state`, only if the file on disk still hashes to
    `base_sha` (what the run started from): under the coverage lock, the new bytes go to a temporary in
    the same directory, are fsynced, and renamed over it. Returns the new sha256."""
    errors = check_state(state)
    if errors:
        raise Refused("\n".join(errors))
    state_dir = pathlib.Path(state_dir)
    target = state_dir / "coverage.json"
    with stagelock.hold(state_dir / "out", "coverage"):
        _, on_disk = load(target)
        if on_disk != base_sha:
            raise Refused(f"COVERAGE_BASE_STALE {target}: the file hashes {on_disk[:12]}, the run started from {base_sha[:12]}; "
                          "another run advanced it, so this one must be redone from the new base")
        text = records.json_text(state)
        fd, tmp = tempfile.mkstemp(dir=state_dir, prefix=".coverage.json.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        except BaseException:
            pathlib.Path(tmp).unlink(missing_ok=True)
            raise
        dir_fd = os.open(state_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    return records.sha256_bytes(text.encode("utf-8"))


def contract_mismatch(schema, contract):
    """Where the coverage schema departs from §5.2 (`contract` maps a place in the schema to
    `(the fields the design names, the fields the schema adds to place the object)`): the required set must
    be exactly their union, and every place must cite the section."""
    errors = []
    for place, (design, added) in contract.items():
        node = schema["$defs"][place.split("/", 1)[1]] if place else schema
        have, want = set(node.get("required", [])), set(design) | set(added)
        missing, extra = sorted(want - have), sorted(have - want)
        if missing or extra:
            errors.append(f"CONTRACT_MISMATCH coverage (design §5.2) {place or 'state'}: required lacks {missing} adds {extra}")
        if not str(node.get("$comment", "")).startswith("design §5.2"):
            errors.append(f"CONTRACT_MISMATCH coverage (design §5.2) {place or 'state'}: $comment does not cite the section")
    return errors


def self_test():
    failures = []

    def expect(label, got, want):
        if got != want:
            failures.append(f"{label}: expected {want!r}, got {got!r}")

    def refused(label, fn, code):
        try:
            fn()
            failures.append(f"{label}: nothing was refused")
        except Refused as exc:
            if code not in str(exc):
                failures.append(f"{label}: expected {code}, got {exc}")

    sha = lambda text: hashlib.sha256(text.encode()).hexdigest()  # noqa: E731
    W1, W2 = "w1", "w2"

    # ranges: positive controls, then the cases an off-by-one would break
    expect("normalize merges touching ranges and drops empty ones", normalize([[5, 8], [0, 2], [2, 4], [9, 9]]), [[0, 4], [5, 8]])
    expect("subtract cuts the middle", subtract([[0, 10]], [[3, 5]]), [[0, 3], [5, 10]])
    expect("subtract of a superset leaves nothing", subtract([[2, 4]], [[0, 10]]), [])
    expect("subtract of a disjoint range leaves it", subtract([[2, 4]], [[4, 9]]), [[2, 4]])
    expect("union", union([[0, 2]], [[2, 5], [7, 8]]), [[0, 5], [7, 8]])

    # ownership: records before, inside and after the window; a record with no stamp follows its predecessor
    zone = datetime.timezone.utc
    start, end = datetime.datetime(2026, 10, 1, tzinfo=zone), datetime.datetime(2026, 10, 8, tzinfo=zone)
    own = Ownership(start, end)
    for index, stamp in enumerate(["2026-09-30T23:00:00Z", None, "2026-10-01T00:00:00Z", "2026-10-07T23:59:59.999Z", None,
                                   "2026-10-08T00:00:00Z", "garbage"]):
        own.feed(index, stamp)
    expect("owned runs are [start, end) and stampless records follow", own.finish(7), {"owned": [[2, 5]], "before": True, "after": True})
    lead = Ownership(start, end)
    for index, stamp in enumerate([None, None, "2026-10-02T00:00:00Z"]):
        lead.feed(index, stamp)
    expect("leading records without a stamp take the first stamp", lead.finish(3), {"owned": [[0, 3]], "before": False, "after": False})
    expect("a window id carries its zone", window_bounds({"start": "2026-10-01T00:00:00", "end": "2026-10-08T00:00:00", "tz": "Asia/Seoul"})[2],
           "2026-10-01T00:00:00/2026-10-08T00:00:00@Asia/Seoul")
    expect("a window without an offset is read in its zone", window_bounds({"start": "2026-10-01T09:00:00", "end": "2026-10-08T00:00:00", "tz": "Asia/Seoul"})[0],
           datetime.datetime(2026, 10, 1, tzinfo=zone))

    # r1 #1: several windows at once, as S1 judges records against the windows already run; c reaches past a
    day = lambda d, m=10: datetime.datetime(2026, m, d, tzinfo=zone)  # noqa: E731
    owners = Owners([(day(1), day(8), "a"), (day(8), day(15), "b"), (day(1, 9), day(15), "c")])
    for index, stamp in enumerate(["2026-08-30T00:00:00Z", None, "2026-10-02T00:00:00Z", "2026-10-09T00:00:00Z", None, "garbage"]):
        owners.feed(index, stamp)
    expect("r1 #1: each record belongs to every window that holds its stamp, stampless ones to their predecessor's",
           owners.finish(6), {"a": [[2, 3]], "b": [[3, 6]], "c": [[2, 6]]})

    # versions: new, same, append (continuity), rewritten (it fails)
    state = new_state()
    expect("first reading", observe(state, "t", sha("a"), 10, sha("a"), None), "new")
    expect("the same bytes", observe(state, "t", sha("a"), 10, sha("a"), True), "same")
    expect("appended records keep the version", observe(state, "t", sha("b"), 14, sha("b"), True), "append")
    expect("the append moved the version in place", [(v["sha"], v["record_count"]) for v in state["transcripts"]["t"]["versions"]], [(sha("b"), 14)])
    expect("a failed continuity starts the next version", observe(state, "t", sha("c"), 20, sha("c"), False), "rewritten")
    expect("the prior version is still there for its evidence", [v["sha"] for v in state["transcripts"]["t"]["versions"]], [sha("b"), sha("c")])
    short = new_state()
    observe(short, "t", sha("a"), 10, sha("a"), None)
    expect("fewer records than before is a rewrite whatever the prefix says", observe(short, "t", sha("b"), 6, sha("b"), True), "rewritten")

    T = lineage.identity("claude", "t")

    def row(status, ident="t"):
        return {"host": "claude", "id": ident, "status": status}

    def reading(text, read, processed, version=0):
        return {"version": version, "sha": sha(text), "read": read, "processed": processed}

    def answer(status, readings, **kw):
        return {"transcript": T, "status": status, "readings": readings, "pending_events": [], "resolved_events": [], **kw}

    # F04, two runs: the records past window w's end are read as context in run 1 and processed by run 2
    state = new_state()
    observe(state, T, sha("x"), 12, sha("x"), None)
    run1 = answer("read_complete", [reading("x", [[0, 12]], {W1: [[0, 10]]})], pending_events=[{"id": "e1", "first_record": 9}])
    after1 = apply_results(state, W1, "periodic", [run1], {T: [[0, 10]]})
    v = latest(after1, T)
    expect("run 1: context records are read and not processed for their own window", (v["read"], v["processed"]), ([[0, 12]], {W1: [[0, 10]]}))
    expect("run 1: the pending event keeps its id", [e["id"] for e in after1["pending_events"]], ["e1"])
    expect("run 2 still owes the records run 1 read as context", work_of(after1, T, [[10, 12]], W2)["in_window"], [[10, 12]])
    run2 = answer("read_complete", [reading("x", [[0, 12]], {W2: [[10, 12]]})], resolved_events=["e1"])
    after2 = apply_results(after1, W2, "periodic", [run2], {T: [[10, 12]]})
    expect("run 2: the records are processed for the window that owns them", latest(after2, T)["processed"], {W1: [[0, 10]], W2: [[10, 12]]})
    expect("run 2: the stitched event is resolved", after2["pending_events"], [])
    expect("run 1's own record of the state is unchanged by run 2", [e["id"] for e in after1["pending_events"]], ["e1"])
    own = {T: [[0, 10]]}
    refused("processing a record the window does not own", lambda: apply_results(
        state, W1, "periodic", [{**run1, "readings": [reading("x", [[0, 12]], {W1: [[0, 11]]})]}], own), f"PROCESSED_OUTSIDE_OWNED {T}")
    refused("a result for another version of the transcript", lambda: apply_results(
        state, W1, "periodic", [{**run1, "readings": [reading("other", [[0, 12]], {W1: [[0, 10]]})]}], own), f"VERSION_MISMATCH {T}")
    refused("a result for a version the state does not have", lambda: apply_results(
        state, W1, "periodic", [{**run1, "readings": [reading("x", [[0, 12]], {W1: [[0, 10]]}, version=3)]}], own), f"VERSION_MISMATCH {T}")
    refused("a result for a transcript the state does not have", lambda: apply_results(
        state, W1, "periodic", [{**run1, "transcript": "claude:ghost"}], own), "VERSION_MISMATCH claude:ghost")
    refused("a deferred result for a transcript the state does not have", lambda: apply_results(
        state, W1, "periodic", [answer("deferred", [], transcript="claude:ghost")], own), "VERSION_MISMATCH claude:ghost: the state has no version")
    refused("one version read twice in a result", lambda: apply_results(
        state, W1, "periodic", [{**run1, "readings": [run1["readings"][0]] * 2}], own), "RESULT_INCONSISTENT")
    refused("read_complete with work left", lambda: apply_results(
        state, W1, "periodic", [answer("read_complete", [reading("x", [[0, 12]], {W1: [[0, 5]]})])], own), f"RESULT_INCONSISTENT {T}")
    refused("read_partial with nothing left", lambda: apply_results(
        state, W1, "periodic", [{**run1, "status": "read_partial"}], own), f"RESULT_INCONSISTENT {T}")
    refused("processing what was not read", lambda: apply_results(
        state, W1, "periodic", [answer("read_complete", [reading("x", [[0, 4]], {W1: [[0, 10]]})])], own), f"PROCESSED_UNREAD {T}")
    # F#1 (round 2): run 1 read [10, 12) as context; run 2 owns it and must read it again, however much earlier runs read
    refused("the owning run processes records it did not read again, because an earlier run read them as context", lambda: apply_results(
        after1, W2, "periodic", [answer("read_complete", [reading("x", [], {W2: [[10, 12]]})])], {T: [[10, 12]]}),
        f"PROCESSED_UNREAD {T}: version 0 processed [[10, 12]] for window {W2}")
    refused("the owning run reads only part of what it processes", lambda: apply_results(
        after1, W2, "periodic", [answer("read_complete", [reading("x", [[10, 11]], {W2: [[10, 12]]})])], {T: [[10, 12]]}), f"PROCESSED_UNREAD {T}")
    expect("the owning run that reads its records again is credited", latest(apply_results(
        after1, W2, "periodic", [answer("read_complete", [reading("x", [[10, 12]], {W2: [[10, 12]]})])], {T: [[10, 12]]}), T)["processed"][W2], [[10, 12]])

    # F#1: a window's records are never credited in advance. Run 1 read [10, 12) as context; it may not also process them for window 2
    refused("a result crediting a later window's records in advance", lambda: apply_results(
        state, W1, "periodic", [answer("read_complete", [reading("x", [[0, 12]], {W1: [[0, 10]], W2: [[10, 12]]})])], own),
        f"PROCESSED_OUTSIDE_OWNED {T}: version 0 processed [[10, 12]] for window {W2}")
    expect("the refused credit left run 2 its work", work_of(apply_results(state, W1, "periodic", [run1], own), T, [[10, 12]], W2)["in_window"], [[10, 12]])
    refused("an earlier window's range that no backlog entry holds", lambda: apply_results(
        after1, W2, "periodic", [answer("read_complete", [reading("x", [[0, 12]], {W1: [[10, 12]], W2: [[10, 12]]})])], {T: [[10, 12]]}),
        f"PROCESSED_OUTSIDE_OWNED {T}: version 0 processed [[10, 12]] for window {W1}")

    # F#2: every result ends in a terminal status, and nothing_new cannot make work vanish
    for bad in ("eligible", "in_progress", "excluded", "known_absent", ""):
        refused(f"a result with the status {bad!r}", lambda bad=bad: apply_results(state, W1, "periodic", [{**run1, "status": bad}], own), "RESULT_STATUS_INVALID")
    refused("a targeted run's results carry a terminal status too", lambda: apply_results(state, W1, "targeted", [{**run1, "status": "eligible"}], own), "RESULT_STATUS_INVALID")
    refused("nothing_new while the window still owns unprocessed records", lambda: apply_results(
        state, W1, "periodic", [answer("nothing_new", [reading("x", [], {})])], own), f"RESULT_INCONSISTENT {T}: nothing_new")
    refused("nothing_new while an earlier window's backlog remains", lambda: apply_results(
        apply_results(state, W1, "periodic", [answer("read_partial", [reading("x", [[0, 6]], {W1: [[0, 6]]})])], own), W2, "periodic",
        [answer("nothing_new", [reading("x", [], {})])], {T: []}), f"RESULT_INCONSISTENT {T}: nothing_new")
    expect("nothing_new once everything is processed is allowed", apply_results(
        state, W1, "periodic", [answer("nothing_new", [reading("x", [[0, 10]], {W1: [[0, 10]]})])], own)["backlog"], [])

    # the backlog: a partial session carries its unread ranges, and the next run reads them first and clears them
    part = answer("read_partial", [reading("x", [[0, 6]], {W1: [[0, 6]]})])
    carried = apply_results(state, W1, "periodic", [part], own)
    expect("a partial session's unread ranges are in the backlog", carried["backlog"], [
        {"transcript": T, "version": 0, "window": W1, "status": "read_partial", "unread": [[6, 10]]}])
    expect("the next run is told to read the backlog first, by version and window", work_of(carried, T, [], W2),
           {"version": 0, "in_window": [], "backlog": [{"window": W1, "version": 0, "unread": [[6, 10]]}]})
    cleared = apply_results(carried, W2, "periodic", [answer("read_complete", [reading("x", [[0, 10]], {W1: [[6, 10]]})])], {T: []})
    expect("reading the backlog clears it and credits its own window", (cleared["backlog"], latest(cleared, T)["processed"]), ([], {W1: [[0, 10]]}))
    failed = apply_results(state, W1, "periodic", [answer("failed", [])], own)
    expect("a failed session carries all of its work", failed["backlog"][0]["unread"], [[0, 10]])

    # F#3: work has a version. A rewrite starts version 1 with other bytes at the same offsets; the backlog still belongs to version 0
    rewrite = copy.deepcopy(carried)
    expect("a rewrite starts the next version", observe(rewrite, T, sha("y"), 12, sha("y"), False), "rewritten")
    refused("a backlog range credited from a reading of the rewritten version", lambda: apply_results(
        rewrite, W2, "periodic", [answer("read_complete", [reading("x", [], {}), reading("y", [[0, 12]], {W1: [[6, 10]], W2: [[10, 12]]}, version=1)])],
        {T: [[10, 12]]}), f"PROCESSED_OUTSIDE_OWNED {T}: version 1 processed [[6, 10]] for window {W1}")
    expect("the new version's work is its own, the old version's backlog is still owed", work_of(rewrite, T, [[0, 12]], W2),
           {"version": 1, "in_window": [[0, 12]], "backlog": [{"window": W1, "version": 0, "unread": [[6, 10]]}]})
    both = apply_results(rewrite, W2, "periodic", [answer("read_complete", [
        reading("x", [[0, 10]], {W1: [[6, 10]]}, version=0), reading("y", [[0, 12]], {W2: [[0, 12]]}, version=1)])], {T: [[0, 12]]})
    expect("each credit lands on the version it was read from", ([v["processed"] for v in both["transcripts"][T]["versions"]], both["backlog"]),
           ([{W1: [[0, 10]]}, {W2: [[0, 12]]}], []))
    expect("a backlog entry's version must exist", any("names version 4" in e for e in check_state(
        {**carried, "backlog": [{**carried["backlog"][0], "version": 4}]})), True)

    # F#2 (round 2): rerunning the window a backlog entry belongs to, after a rewrite, may read the old version for it
    rerun = apply_results(rewrite, W1, "periodic", [answer("read_complete", [
        reading("x", [[6, 10]], {W1: [[6, 10]]}, version=0), reading("y", [[0, 12]], {W1: [[0, 12]]}, version=1)])], {T: [[0, 12]]})
    expect("the window that owns the backlog reads the old version for it and its own records of the new one",
           ([v["processed"] for v in rerun["transcripts"][T]["versions"]], rerun["backlog"]), ([{W1: [[0, 10]]}, {W1: [[0, 12]]}], []))
    refused("the same window, a rewritten version, and offsets that only the old version's backlog held", lambda: apply_results(
        rewrite, W1, "periodic", [answer("read_complete", [reading("y", [[0, 12]], {W1: [[6, 10]]}, version=1)])], {T: [[10, 12]]}),
        f"PROCESSED_OUTSIDE_OWNED {T}: version 1 processed [[6, 10]] for window {W1}")

    # F#3 (round 2): a session still carrying an earlier window's backlog is accounted for the current one, which keeps the original windows
    deferred = apply_results(carried, W2, "periodic", [answer("deferred", [])], {T: []})
    expect("deferring earlier-window work again keeps its window", deferred["backlog"], carried["backlog"])
    expect("the current window owes nothing and the earlier backlog is held: accounted, not fully read",
           accounted([{**row("deferred"), "owned": []}], deferred, W2), (True, False))
    mixed = apply_results(carried, W2, "periodic", [answer("deferred", [reading("x", [], {})])], {T: [[10, 12]]})
    expect("both windows' obligations are held, each under its own window", sorted((b["window"], b["unread"]) for b in mixed["backlog"]),
           [(W1, [[6, 10]]), (W2, [[10, 12]])])
    expect("the current window's own unread records and the carried ones are held: accounted",
           accounted([{**row("deferred"), "owned": [[10, 12]]}], mixed, W2), (True, False))
    expect("the current window owns records that no backlog entry of its own holds: not accounted",
           accounted([{**row("deferred"), "owned": [[10, 12]]}], deferred, W2), (False, False))
    expect("the session carries nothing and is deferred without a backlog: not accounted",
           accounted([{**row("deferred"), "owned": []}], new_state(), W2), (False, False))

    # a window is accounted when every eligible session is terminal and its unread ranges are held; fully read is separate
    entries = [row("read_partial"), row("read_complete", "u"), row("excluded", "x")]
    expect("partial with its backlog: accounted, not fully read", accounted(entries, carried, W1), (True, False))
    expect("partial without its backlog: not accounted", accounted(entries, new_state(), W1), (False, False))
    expect("one session left non-terminal: not accounted", accounted([*entries[1:], row("eligible", "n")], new_state(), W1), (False, False))
    expect("all complete or nothing to read: both", accounted([entries[1], row("nothing_new", "n")], new_state(), W1), (True, True))
    expect("no eligible session at all", accounted([entries[2]], new_state(), W1), (True, True))
    expect("a backlog held for another host's session of the same id does not account for this one",
           accounted([{**row("read_partial"), "host": "codex"}], carried, W1), (False, False))

    # F#0 (round 2): a targeted run's results are held to the periodic rules, then discarded
    refused("a targeted run's false nothing_new", lambda: apply_results(
        state, W1, "targeted", [answer("nothing_new", [reading("x", [], {})])], own), f"RESULT_INCONSISTENT {T}: nothing_new")
    refused("a targeted run's reading of a version the state does not have", lambda: apply_results(
        state, W1, "targeted", [{**run1, "readings": [reading("other", [[0, 12]], {W1: [[0, 10]]})]}], own), f"VERSION_MISMATCH {T}")
    refused("a targeted run processing what it did not read", lambda: apply_results(
        state, W1, "targeted", [answer("read_complete", [reading("x", [[0, 4]], {W1: [[0, 10]]})])], own), f"PROCESSED_UNREAD {T}")
    refused("a targeted run crediting a later window", lambda: apply_results(
        state, W1, "targeted", [answer("read_complete", [reading("x", [[0, 12]], {W1: [[0, 10]], W2: [[10, 12]]})])], own), "PROCESSED_OUTSIDE_OWNED")

    # a targeted run reads but never advances periodic coverage
    expect("a targeted run returns the base", records.json_text(apply_results(state, W1, "targeted", [run1], own)), records.json_text(state))
    expect("the targeted guard passes the unchanged state", check_targeted(state, apply_results(state, W1, "targeted", [run1], own)), [])
    expect("the targeted guard names a processed range that advanced", [e.split(":")[0] for e in check_targeted(
        state, apply_results(state, W1, "periodic", [run1], own))], ["TARGETED_ADVANCED_COVERAGE"])

    # observed(): the versions a census saw laid over a state that has not seen them
    seen_at = [{"key": T, "versions": [{"sha": sha("x2"), "record_count": 14, "prefix_sha": sha("x2")}]},
               {"key": "codex:n", "versions": [{"sha": sha("n"), "record_count": 3, "prefix_sha": sha("n")}]}]
    watched = observed(after1, seen_at)
    expect("an append moves the version in place and keeps what was read", [(v["sha"], v["record_count"], v["read"]) for v in watched["transcripts"][T]["versions"]],
           [(sha("x2"), 14, [[0, 12]])])
    expect("a transcript the state never saw gets a version with nothing read", watched["transcripts"]["codex:n"]["versions"][0]["read"], [])
    expect("observing leaves the state it was given alone", records.json_text(after1) == records.json_text(apply_results(state, W1, "periodic", [run1], own)), True)

    # review c0fix r1 #1: records appended after the run of the window that owns them are owed to that window
    week = {"start": "2026-10-01T00:00:00", "end": "2026-10-08T00:00:00", "tz": "Asia/Seoul"}
    expect("r1 #1: a window id is read back to the bounds it was made from", bounds_of(window_bounds(week)[2]), window_bounds(week)[:2])
    refused("r1 #1: a window id that is not <start>/<end>@<tz> is refused by name", lambda: bounds_of("w1"), "COVERAGE_INVALID window 'w1'")
    late = copy.deepcopy(after1)  # version 0 of T: 12 records, window 1 processed [0, 10)
    expect("r1 #1: the append moves version 0 in place", observe(late, T, sha("x3"), 14, sha("x3"), True), "append")
    expect("r1 #1: the appended records a window already run owns are held for it, under the status appended",
           carry_appended(late, T, {W1: [[12, 14]]}), [{"transcript": T, "version": 0, "window": W1, "status": APPENDED, "unread": [[12, 14]]}])
    # each on a copy: a reverted check must fail its own label, not leave an entry that makes a later control raise
    expect("r1 #1: what the backlog already holds is not held again", carry_appended(copy.deepcopy(late), T, {W1: [[12, 14]]}), [])
    expect("r1 #1: what the window processed is not owed again", carry_appended(copy.deepcopy(late), T, {W1: [[8, 10]]}), [])
    expect("r1 #1: the next run is told to read them, under their window", work_of(late, T, [], W2)["backlog"],
           [{"window": W1, "version": 0, "unread": [[12, 14]]}])
    try:
        credited_late = apply_results(late, W2, "periodic", [answer("read_complete", [
            {"version": 0, "sha": sha("x3"), "read": [[0, 14]], "processed": {W1: [[12, 14]]}}])], {T: []})
        credited_late = (latest(credited_late, T)["processed"], credited_late["backlog"])
    except Refused as exc:  # a control reads the refusal, never a traceback
        credited_late = str(exc)
    expect("r1 #1: the next run that reads them is credited under their window, and they leave the backlog", credited_late,
           ({W1: [[0, 10], [12, 14]]}, []))
    seen_late = observed(after1, [{"key": T, "versions": [{"sha": sha("x3"), "record_count": 14, "prefix_sha": sha("x3")}],
                                   "work": {"version": 0, "in_window": [], "backlog": [{"window": W1, "version": 0, "unread": [[12, 14]]}]}}])
    expect("r1 #1: the state a targeted census observed holds the backlog it added for appended records", seen_late["backlog"],
           [{"transcript": T, "version": 0, "window": W1, "status": APPENDED, "unread": [[12, 14]]}])

    # review c0fix r1 #5: a result resolves only the pending events of its own unit
    pair = new_state()
    RA, RB = lineage.identity("claude", "ra"), lineage.identity("claude", "rb")
    for tid, text in ((RA, "ra"), (RB, "rb")):
        observe(pair, tid, sha(text), 4, sha(text), None)
    pair["pending_events"] = [{"id": "event-b", "transcript": RB, "version": 0, "window": W1, "first_record": 2}]

    def whole(tid, text, resolved=()):
        return {**answer("read_complete", [reading(text, [[0, 4]], {W1: [[0, 4]]})]), "transcript": tid, "resolved_events": list(resolved)}

    both_owned = {RA: [[0, 4]], RB: [[0, 4]]}
    refused("r1 #5: a result resolving another unit's pending event is refused, naming the event", lambda: apply_results(
        pair, W1, "periodic", [whole(RA, "ra", ["event-b"]), whole(RB, "rb")], both_owned), f"RESULT_INCONSISTENT {RA}: it resolves ['event-b']")
    refused("r1 #5: a result resolving an event that is not pending is refused", lambda: apply_results(
        pair, W1, "periodic", [whole(RA, "ra", ["ghost"]), whole(RB, "rb")], both_owned), f"RESULT_INCONSISTENT {RA}: it resolves ['ghost']")
    expect("r1 #5: the unit an event is pending on resolves it", apply_results(
        pair, W1, "periodic", [whole(RA, "ra"), whole(RB, "rb", ["event-b"])], both_owned)["pending_events"], [])

    # the state on disk: it validates, and writes are atomic against a base hash
    with tempfile.TemporaryDirectory() as td:
        directory = pathlib.Path(td)
        _, base = load(directory / "coverage.json")
        expect("an absent file hashes as the empty state", base, digest(new_state()))
        new = write_atomic(directory, after1, base)
        expect("the write lands with the hash it reports", load(directory / "coverage.json")[1], new)
        refused("a write from a stale base", lambda: write_atomic(directory, after2, base), "COVERAGE_BASE_STALE")
        expect("a refused write left the file as it was", load(directory / "coverage.json")[1], new)
        write_atomic(directory, after2, new)
        expect("a write from the current base lands", [e["id"] for e in load(directory / "coverage.json")[0]["pending_events"]], [])
        expect("no temporary file is left behind", sorted(p.name for p in directory.iterdir() if p.name != "out"), ["coverage.json"])
        with stagelock.hold(directory / "out", "coverage"):
            try:
                write_atomic(directory, after1, load(directory / "coverage.json")[1])
                failures.append("a write went ahead while another writer held the lock")
            except stagelock.Locked as exc:
                if "STAGE_LOCKED coverage" not in str(exc):
                    failures.append(f"a held lock was refused unnamed: {exc}")
        (directory / "bad.json").write_text('{"transcripts": {}}')
        refused("a state that does not conform", lambda: load(directory / "bad.json"), "COVERAGE_INVALID")
        (directory / "bad.json").write_text("{")
        refused("a state that is not JSON", lambda: load(directory / "bad.json"), "COVERAGE_INVALID")
    broken = copy.deepcopy(after2)
    broken["transcripts"][T]["versions"][0]["processed"]["w9"] = [[0, 99]]
    with tempfile.TemporaryDirectory() as refused_into:
        refused("a range past record_count", lambda: write_atomic(pathlib.Path(refused_into), broken, digest(new_state())),
                "COVERAGE_INVALID")
    for label, edit, fragment in (
            ("ranges out of order", lambda st: st["transcripts"][T]["versions"][0]["read"].__setitem__(slice(None), [[5, 8], [0, 2]]), "ranges are not sorted"),
            ("a read range past record_count", lambda st: st["transcripts"][T]["versions"][0]["read"].__setitem__(slice(None), [[0, 99]]), "ends past record_count 12"),
            ("processed records never read", lambda st: st["transcripts"][T]["versions"][0]["read"].__setitem__(slice(None), [[0, 4]]), "never read"),
            ("an event naming a version the state lacks", lambda st: st["pending_events"].append(
                {"id": "ghost", "transcript": T, "version": 5, "window": W1, "first_record": 0}), "names version 5")):
        mutated = copy.deepcopy(after2)
        edit(mutated)
        if not any(fragment in line for line in check_state(mutated)):
            failures.append(f"state invariant not named: {label} -> {check_state(mutated)}")
    refused("a state path that cannot be read", lambda: load(tempfile.gettempdir()), "COVERAGE_INVALID")
    again = copy.deepcopy(after2)
    again["pending_events"] = [{"id": "e", "transcript": T, "version": 0, "window": W1, "first_record": 1}] * 2
    expect("a pending event id that repeats is named", [e for e in check_state(again) if "repeats" in e] != [], True)

    # the tracked state conforms to its own schema and invariants
    expect("the tracked session-distill/coverage.json is a valid coverage state", check_state(load(SCHEMA_PATH.parent.parent / "coverage.json")[0]), [])

    # contract fidelity (done-when 7): the lists below are the field lists of design §5.2, copied once and cited. The first
    # list of each pair is what the design names; the second is what the schema adds to say whose an object is
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    contract = {"": (["transcripts", "pending_events", "backlog", "windows"], []),
                "$defs/version": (["sha", "record_count", "prefix_sha", "read", "processed"], []),
                "$defs/window_flags": (["accounted", "fully_read"], []),
                "$defs/pending_event": (["id"], ["transcript", "version", "window", "first_record"]),
                "$defs/backlog_entry": (["unread"], ["transcript", "version", "window", "status"])}
    expect("the schema matches design §5.2", contract_mismatch(schema, contract), [])
    for place in contract:
        node_of = lambda doc, place=place: doc["$defs"][place.split("/", 1)[1]] if place else doc  # noqa: E731
        for field in node_of(schema)["required"]:
            mutated = copy.deepcopy(schema)
            node_of(mutated)["required"].remove(field)
            found = contract_mismatch(mutated, contract)
            if not any(f"(design §5.2) {place or 'state'}: required lacks ['{field}']" in line for line in found):
                failures.append(f"contract control not named: {place or 'state'} lacking {field} -> {found}")
        mutated = copy.deepcopy(schema)
        node_of(mutated)["required"].append("extra")
        found = contract_mismatch(mutated, contract)
        if not any(f"(design §5.2) {place or 'state'}: required lacks [] adds ['extra']" in line for line in found):
            failures.append(f"contract control not named: {place or 'state'} adding a required field -> {found}")
        uncited = copy.deepcopy(schema)
        node_of(uncited)["$comment"] = "design §0.0"
        if not any(f"{place or 'state'}: $comment does not cite" in line for line in contract_mismatch(uncited, contract)):
            failures.append(f"a {place or 'state'} definition that cites another section was not named")
    for failure in failures:
        print(f"coverage --self-test [FAIL] {failure}")
    if failures:
        return 1
    print("coverage --self-test: OK (range algebra; window ownership; versions new/same/append/rewritten; two-run range ownership "
          "with a pending event stitched across the boundary and no credit in advance; terminal result statuses only and no false "
          "nothing_new; backlog carried and cleared by version and window; accounted vs fully read; a targeted run leaves the base "
          "byte-identical; atomic write refuses a stale base and a held lock; every required set of the schema equals design §5.2's)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: coverage.py --self-test")
    sys.exit(self_test())
