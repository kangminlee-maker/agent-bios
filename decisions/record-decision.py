#!/usr/bin/env python3
"""Record one decision about developing this repo, in order, as it happens.

Scope: this repo and whoever works on it. The line against session distill is
shipping. Distill is a feature of the deployed package, run by its users against
their own sessions; this never leaves the checkout, and `gates/check-package.sh`
enforces that in both directions — nothing here may enter `package.json` files[].
Folding this into distill, or letting it replace part of distill, stays open;
until then the two are separate because one ships and one does not.

Authority split. The caller supplies semantics only: kind, summary, the
alternatives it closed, and why. Everything checkable is stamped here — id,
timestamp, branch, HEAD, dirty flag, session. No caller flag can set those; an
LLM cannot know them reliably and would be guessing, so they are not offered.

Identity is CONTENT, not position. `id` is `D-<date>-<6 hex>`, the hex derived
from every field of the record but the id itself. It was `D-<seq>`, a position in
the file, and a positional id cannot merge: two branches that each appended
"the 62nd record" produced two D-0062s and every merge needed a hand renumber,
which then moved every reference to the records it renumbered. A content id is
the same on every branch that carries the record, so ledgers written apart are
merged by concatenation — order in the file is append order per branch and
carries no meaning; every projection sorts by the instant.

This is provenance for a cooperating tool, NOT a security boundary. `session`
comes from the environment, which a caller can set, and the ledger is an
append-only text file anyone can edit. `--check` therefore validates the artifact
itself — shape, the recording bar, and that every id is the id its content
derives to — so a hand-edited or forged row fails a gate instead of being
rendered as fact. What the content id does not see is a row DELETED whole; the
positional sequence caught that in the middle of the file and never at its end,
and this trades that partial protection for mergeability. Stated here so it is a
choice and not an oversight.

Time is NOT recorded here, because it is already recorded elsewhere. Every
action in a session transcript carries its own timestamp, so elapsed time is a
projection over those instants, not a quantity anyone measures or stores. This
file keeps only the instant a decision was made; `--timeline` derives duration
by reading the action stream. Storing a precomputed interval would put a derived
value outside its source and freeze it at the moment of writing.

`--timeline` splits a span into active and idle. Consecutive actions closer than
IDLE_S apart are active: a main context waiting on a background task is working,
and its tool results keep landing. A silence longer than IDLE_S is reported as
idle rather than counted or dropped, because only a person can tell a long wait
from an absence. Nothing here silently reinterprets a number.

The recording bar is structural, not exhortative: a decision must name at least
one alternative it CLOSED (rejected, deferred, or blocked). That is what makes
the log answerable for "where did this first go wrong" — the paths not taken are
the ones with no other trace. A record with nothing closed is refused.

  --check       validate the ledger on disk: that the file exists and holds
                records at all, then their shape, bar, and content-bound ids
  --migrate     rewrite every id that is not its content id (a one-time move off
                positional ids, and idempotent after it); prints the old→new map
  --merge PATH  append every record of another ledger not already here, by id —
                a record carried by both branches is one record, not two
  --render      the log, chronologically, with intervals derived from timestamps
  --timeline    active/idle per decision, derived from session action timestamps
  --self-test   prove the bar refuses, the stamps are not caller-settable, and
                every projection is computed rather than stored. Exits 0 only if
                all controls hold.
"""
import argparse
import glob
import fcntl
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

REPO = pathlib.Path(__file__).resolve().parents[1]
LEDGER = REPO / "decisions" / "decisions.jsonl"

# Where each host writes a session transcript. The session id is the whole
# filename on one host and a suffix of it on the other, so the pattern belongs
# with its root rather than inside the resolver. Both hosts write one JSON object
# per line carrying a top-level "timestamp", so load_actions reads either
# unchanged — verified against codex-cli 0.145.0 and again on 0.146.0, which
# arrived mid-session and moved its own install path. The layout is what this
# depends on, so re-check it here rather than trusting the version.
CLAUDE_SESSIONS = pathlib.Path(os.environ.get(
    "CLAUDE_CONFIG_DIR", pathlib.Path.home() / ".claude")) / "projects"
CODEX_SESSIONS = pathlib.Path(os.environ.get(
    "CODEX_HOME", pathlib.Path.home() / ".codex")) / "sessions"

KINDS = ("design", "direction", "stop", "steering")

# A silence longer than this is not counted as active. It is reported, never
# dropped: only a person can tell a long background wait from an absence.
IDLE_S = 900

# Stamped by this tool. Listed so the self-test can prove none is reachable
# from the caller's payload.
STAMPED = ("id", "at", "branch", "head", "dirty", "session")

# Supplied by the caller: the meaning, which no tool can derive.
SEMANTIC = ("kind", "summary", "closed", "why")

# What `--check` requires of a row on disk. Derived from the two sets above
# rather than hand-listed, because a hand-listed subset is what let a row missing
# `branch` pass the gate and then crash `--render`, which indexes it directly.
# Every field `stamp()` writes must be present; `reverses_if` and `backfilled`
# are conditional and read with .get().
REQUIRED = STAMPED + SEMANTIC


class BarError(ValueError):
    """The payload does not meet the recording bar."""


def validate(payload):
    """Semantic bar. Raises BarError; never repairs the payload."""
    if payload.get("kind") not in KINDS:
        raise BarError(f"kind must be one of {KINDS}, got {payload.get('kind')!r}")
    for field in ("summary", "why"):
        if not (payload.get(field) or "").strip():
            raise BarError(f"{field} is required and must not be blank")
    closed = [c.strip() for c in payload.get("closed", []) if c.strip()]
    if not closed:
        raise BarError(
            "a decision must close at least one alternative (--closed); "
            "if nothing was closed, this is not a decision worth recording"
        )
    return closed


def decision_id(record):
    """The id a record's content derives to: `D-<local date of at>-<6 hex>`.

    The hex is over EVERY field of the record except the id — the semantic ones
    (kind, summary, closed, why, reverses_if) and the stamped provenance (at,
    branch, head, dirty, session, backfilled) alike — canonicalised as sorted JSON.
    It bound only the instant, session and summary at first, which let a row's
    `closed`, `why` or provenance be rewritten under an id that still checked
    out (review of PR #32); the ledger exists to keep exactly those, so the id
    binds them all. Editing any field by hand changes what the id should be, and
    `--check` compares. The date prefix is for the reader; uniqueness rests on
    the hex plus the check.
    """
    body = {k: v for k, v in record.items() if k != "id"}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:6]
    date = str(record.get("at", ""))[:10].replace("-", "")
    return f"D-{date}-{digest}"


def stamp(payload, now, git, session=None, backfill=False):
    """Build the record. Pure: all environment arrives as arguments.

    Deterministic fields are computed here and overwrite anything of the same
    name in the payload, so a caller cannot author its own provenance.
    """
    closed = validate(payload)
    record = {
        "kind": payload["kind"],
        "summary": payload["summary"].strip(),
        "closed": closed,
        "why": payload["why"].strip(),
    }
    if (payload.get("reverses_if") or "").strip():
        record["reverses_if"] = payload["reverses_if"].strip()
    record.update({
        "at": now.isoformat(timespec="seconds"),
        "branch": git["branch"],
        "head": git["head"],
        "dirty": git["dirty"],
        # The session that recorded this. Deterministic: the harness exports it,
        # and it is also the transcript's filename, so a decision points at the
        # exact action stream it belongs to. None when the harness did not set it.
        "session": session,
    })
    if backfill:
        # The instant is when this was typed, not when it was decided, so every
        # interval touching it is unreliable and says so downstream.
        record["backfilled"] = True
    record["id"] = decision_id(record)
    return record


def parse_ts(value):
    """An instant, not a string. Every ordering keys on this.

    `stamp()` writes the LOCAL offset, so two records made in different zones —
    or across a machine's own offset change — compare wrongly as text:
    `…T16:46+09:00` sorts after `…T07:46+00:00` while being the earlier moment,
    which inverts the sequence and prints negative intervals.

    A non-string is refused as a ValueError rather than reaching `.replace` and
    raising AttributeError. Every caller already treats ValueError as "not an
    instant" — one counts it as damage, the other reports it as a bad row — so
    stating the type here fixes both instead of guarding each call site.
    """
    if not isinstance(value, str):
        raise ValueError(f"an instant is written as text; got {type(value).__name__} "
                         f"{value!r}")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_ledger(path):
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def git_facts():
    def run(*args):
        return subprocess.run(args, cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.strip()
    try:
        return {
            "branch": run("git", "rev-parse", "--abbrev-ref", "HEAD"),
            "head": run("git", "rev-parse", "--short", "HEAD"),
            "dirty": bool(run("git", "status", "--porcelain")),
        }
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        sys.exit(f"record-decision: not a usable git repo ({exc}); refusing to "
                 f"stamp provenance this tool cannot derive")


def intervals(records):
    """Elapsed between consecutive decisions, derived from their instants.

    Returned, never stored. An interval is unreliable when either end was
    backfilled, because that end's instant is when it was typed.

    Pairs form WITHIN a session, never across one. The wall-clock between one
    session's last decision and the next session's first is time away, and
    `--timeline` already refuses to count it; rendering the same span as a
    derived `+…` made the log contradict the projection.
    """
    out = []
    for sid, recs in by_session(records).items():
        for prev, cur in zip(recs, recs[1:]):
            out.append({
                "id": cur["id"],
                "seconds": int((parse_ts(cur["at"]) - parse_ts(prev["at"])).total_seconds()),
                # `None` is not a session, it is the absence of one, so the rows
                # sharing that key are unrelated invocations rather than one
                # stretch of work. --timeline already refuses to trust them;
                # pairing them here and printing the gap plainly did not.
                "unreliable": bool(prev.get("backfilled") or cur.get("backfilled")
                                   or sid is None),
            })
    return out


def check_artifact(path, records):
    """The ledger AS A FILE, which `check_ledger` cannot see.

    An absent or empty artifact satisfies every claim made about its contents, so
    validating only the rows reports `OK (0 records)` after the repository's whole
    decision history is deleted. The file's existence is the one property the row
    walk is structurally unable to judge, so it is judged here.
    """
    if not path.is_file():
        return [f"{path} does not exist; this gate protects the decision record, "
                f"and a missing file passes a row walk over nothing"]
    if not records:
        return [f"{path} holds no records; an empty ledger satisfies every check "
                f"below, so it is refused rather than reported clean"]
    return []


def check_ledger(records):
    """Problems with the rows as they exist on disk. Empty list means clean.

    Pure over rows: the artifact's own existence is `check_artifact`'s, so an
    empty list here is legitimately clean and both are run by `--check`.
    """
    problems, seen = [], set()
    for i, r in enumerate(records, 1):
        where = r.get("id", f"line {i}")
        for field in REQUIRED:
            if field not in r:
                problems.append(f"{where}: missing {field!r}")
        if r.get("kind") not in KINDS:
            problems.append(f"{where}: kind {r.get('kind')!r} is not one of {KINDS}")
        # Shape before content: `render` joins this list, so a bare string passes
        # a truthiness test, then joins character by character into "o; o; p; s".
        closed = r.get("closed")
        if not isinstance(closed, list):
            problems.append(f"{where}: closed is {type(closed).__name__}, not a list; "
                            f"a string here renders as one alternative per character")
        elif not all(isinstance(c, str) for c in closed):
            problems.append(f"{where}: closed holds a non-string member; the "
                            f"projections join it as text")
        elif not [c for c in closed if c.strip()]:
            problems.append(f"{where}: closes no alternative — the recording bar")
        # Type before emptiness, and for the same reason `closed` needed shape:
        # `str(...)` here would validate a stringified copy of a value the
        # projections then index as text. `{"summary": 7}` passed this check and
        # raised TypeError inside render's join on the next line.
        for field in ("summary", "why", "branch", "head"):
            if field in r and not isinstance(r[field], str):
                problems.append(f"{where}: {field} is {type(r[field]).__name__}, not a "
                                f"string; the projections render it as text")
            elif not str(r.get(field) or "").strip():
                problems.append(f"{where}: {field} is blank")
        if "session" in r and not (r["session"] is None or isinstance(r["session"], str)):
            problems.append(f"{where}: session is {type(r['session']).__name__}; it is a "
                            f"transcript id or null, and the lanes slice it as text")
        for flag in ("dirty", "backfilled"):
            if flag in r and not isinstance(r[flag], bool):
                problems.append(f"{where}: {flag} is {type(r[flag]).__name__}, not a "
                                f"bool; a non-empty string here reads as true and the "
                                f"projections report it that way")
        # Optional, but rendered by concatenation the moment it is present.
        if "reverses_if" in r and not isinstance(r["reverses_if"], str):
            problems.append(f"{where}: reverses_if is {type(r['reverses_if']).__name__}, "
                            f"not a string; --render concatenates it")
        if r.get("id") != decision_id(r):
            problems.append(f"{where}: id is not the id its content derives to "
                            f"({decision_id(r)}); a field was edited by hand, or the row "
                            f"was written by hand — or the ledger predates this id scheme "
                            f"and needs --migrate")
        if r.get("id") in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(r.get("id"))
        if "seq" in r:
            problems.append(f"{where}: carries a positional seq; identity is the "
                            f"content id now — run --migrate")
        try:
            here = parse_ts(r["at"])
        except (KeyError, ValueError):
            problems.append(f"{where}: at {r.get('at')!r} is not an ISO instant")
            continue
        if here.tzinfo is None:
            problems.append(f"{where}: at {r['at']} carries no UTC offset; stamp() "
                            f"always writes one, so this was edited by hand and "
                            f"cannot be ordered against the rest")
    return problems


def merge(mine, theirs):
    """Union by content id. `theirs` is migrated first, so a branch that has not
    run --migrate merges as well as one that has. Returns (rows, appended)."""
    theirs, _ = migrate(theirs)
    have = {r.get("id") for r in mine}
    appended = [r for r in theirs if r.get("id") not in have]
    return list(mine) + appended, appended


def migrate(records):
    """Every row's id becomes its content id; positional `seq` is dropped.

    Idempotent: a row already carrying its content id is untouched. Returns
    (rows, {old_id: new_id}) and writes nothing — the caller decides where.
    """
    out, moved = [], {}
    for r in records:
        row = {k: v for k, v in r.items() if k != "seq"}
        new_id = decision_id(row)
        if row.get("id") != new_id:
            moved[row.get("id")] = new_id
            row["id"] = new_id
        # id last in the row for stable, readable diffs? No — keep the key order the
        # recorder writes (semantic first, stamps after), which is what json.dumps of
        # the original preserved; only the value changed.
        out.append(row)
    return out, moved


def session_id():
    """The session that recorded this, from whichever host is running.

    Both hosts export one; reading only Claude's gave every Codex-recorded row a
    null session, collapsing them into the shared `unattributed` lane where no
    transcript resolves and no span can be derived. Verified on codex-cli 0.145.0
    and 0.146.0:
    `CODEX_THREAD_ID` is exported to the commands Codex runs, and its value is the
    id in the rollout filename. Absent outside a session.

    Codex wins when BOTH are set, because that is the only nesting that occurs:
    a Claude session running `codex exec` passes its own variable straight through
    — measured, the inner Codex process still sees `CLAUDE_CODE_SESSION_ID` — so
    preferring Claude stamped the OUTER session onto work the inner one did and
    resolved the wrong transcript. The reverse nesting is not something this
    repo's launcher produces; if it ever does, the environment alone cannot tell
    the two apart and this needs a host signal rather than a longer list.
    """
    for var in ("CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID"):
        if os.environ.get(var):
            return os.environ[var]
    return None


def transcript_roots(claude=None, codex=None):
    """(root, filename pattern) per host, overridable for tests."""
    return ((pathlib.Path(claude or CLAUDE_SESSIONS), "*/{sid}.jsonl"),
            (pathlib.Path(codex or CODEX_SESSIONS), "*/*/*/rollout-*-{sid}.jsonl"))


def resolve_transcript(session, roots):
    """A session's transcript, found by name. The id IS part of the filename.

    The id is escaped before globbing: it arrives from the environment, and a
    caller that set it to `*` would otherwise match a stranger's transcript and
    report its actions as this session's work.
    """
    if not session:
        return None
    for root, pattern in roots:
        hits = sorted(glob.glob(os.path.join(
            str(root), pattern.format(sid=glob.escape(session)))))
        if hits:
            return hits[0]
    return None


def load_actions(paths):
    """(instants, damaged) from the given transcripts, sorted.

    Only the transcripts of sessions that recorded decisions are read. Globbing
    every project would fold unrelated work into these spans, which is how a
    duration stops meaning anything.

    A bad line is skipped and COUNTED, never swallowed: an earlier version let
    one malformed record end a file's scan and returned the prefix as if it were
    the whole stream, which silently shortens every span after it.
    """
    stamps, damaged = [], 0
    for path in paths:
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            damaged += 1
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            # Parse every line rather than pre-filtering on the marker: a line
            # truncated mid-write can lose `"timestamp"` entirely, and skipping it
            # before the try/except is how a damaged line goes uncounted.
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                damaged += 1
                continue
            if not isinstance(rec, dict) or "timestamp" not in rec:
                continue                      # metadata rows carry no instant
            # A row that HAS the key but not a usable instant is damage, not
            # metadata: `{"timestamp": 123}` used to reach parse_ts and abort the
            # whole projection with AttributeError instead of being counted, and
            # an explicit `null` is a lost instant rather than an absent one.
            ts = rec["timestamp"]
            try:
                when = parse_ts(ts)
            except (ValueError, TypeError):
                damaged += 1
                continue
            # A naive instant cannot be compared with the offset-aware ones, and
            # one of them anywhere in the stream raised TypeError out of the sort
            # below — the whole projection lost to one malformed line, which is
            # what counting damage exists to prevent.
            if when.tzinfo is None:
                damaged += 1
                continue
            stamps.append(when)
    return sorted(stamps), damaged


def by_session(records):
    """Session id -> its decisions, in order; lanes ordered by first decision."""
    lanes = {}
    for r in sorted(records, key=lambda x: parse_ts(x["at"])):
        lanes.setdefault(r.get("session"), []).append(r)
    return lanes


def split_span(actions, start, end, idle_s=IDLE_S):
    """Active vs idle between two instants, from the action stream.

    The span's own boundaries are gaps like any other. Walking only the gaps
    BETWEEN actions silently dropped the head and the tail — a decision's
    instant is stamped separately from the actions, so those two gaps are the
    normal case, not an edge one, and a 300s span with actions at 100s and 200s
    reported 100s. Active plus idle now accounts for the whole interval.

    An inverted span yields nothing rather than negative time. Counting the
    boundaries made that case reachable: with no action between them the single
    remaining gap is `end - start`, which a clock skew or a reused session id can
    make negative, and a negative "active" second is worse than a missing one.
    """
    if end < start:
        return {"active_s": 0, "idle_s": 0, "actions": 0}
    inside = [t for t in actions if start <= t <= end]
    # Accumulate exact microseconds and truncate ONCE, at the end. Truncating each
    # gap discarded the sub-second part of every one of them, and an action stream
    # is mostly sub-second gaps: replaying this ledger's spans over their real
    # transcripts lost 947 seconds in total, 216 in a single span. Summing floats
    # instead is not enough either — a thousand 0.9s gaps drift to 900.99…, which
    # int() then rounds down to 900 and loses the second all over again.
    micro, idle_us = timedelta(microseconds=1), idle_s * 1_000_000
    active = idle = 0
    for a, b in zip([start] + inside, inside + [end]):
        gap = (b - a) // micro
        if gap <= idle_us:
            active += gap
        else:
            idle += gap
    return {"active_s": active // 1_000_000, "idle_s": idle // 1_000_000,
            "actions": len(inside)}


def timeline_rows(records, actions_by_session, idle_s=IDLE_S, damage_by_session=None):
    """Active/idle per decision, within its own session. Pure.

    Intervals never cross a session boundary: the wall-clock between the last
    decision of one session and the first of the next is time away, not work.
    The first decision of a session is measured from that session's first
    action, which is where its work actually began.

    `damage_by_session` carries forward what `load_actions` counted. A damaged
    line is a missing instant, which can move a gap from one side of the idle
    threshold to the other, so every row derived from that session says so. The
    count was previously summed for a footnote and dropped before it reached
    here, leaving affected rows presented as reliable.
    """
    damage_by_session = damage_by_session or {}
    rows = []
    for sid, recs in by_session(records).items():
        actions = actions_by_session.get(sid) or []
        for i, cur in enumerate(recs):
            start = parse_ts(recs[i - 1]["at"]) if i else (actions[0] if actions else None)
            if start is None:
                rows.append({"id": cur["id"], "kind": cur["kind"], "session": sid,
                             "active_s": 0, "idle_s": 0, "actions": 0,
                             "unreliable": True, "from": "no actions"})
                continue
            span = split_span(actions, start, parse_ts(cur["at"]), idle_s)
            span.update({
                "id": cur["id"], "kind": cur["kind"], "session": sid,
                "from": "previous decision" if i else "session start",
                # Unreliable when the instant is not when the work happened, when
                # the session is unknown (records from different invocations share
                # the None lane), when no action backs the span at all, or when
                # the transcript this span was read from had an unreadable line.
                "unreliable": bool(cur.get("backfilled")
                                   or (i and recs[i - 1].get("backfilled"))
                                   or sid is None
                                   or span["actions"] == 0
                                   or damage_by_session.get(sid)),
            })
            rows.append(span)
    return rows


def graph(records, rows=None):
    """Sessions as lanes, decisions as nodes, in time order."""
    lanes = list(by_session(records).keys())
    spans = {sid: (parse_ts(recs[0]["at"]), parse_ts(recs[-1]["at"]))
             for sid, recs in by_session(records).items()}
    timings = {r["id"]: r for r in (rows or [])}
    out = ["# Decision graph", ""]
    for i, sid in enumerate(lanes):
        label = (sid or "unattributed")[:8]
        out.append(f"  lane {i + 1}: {label}  ({len(by_session(records)[sid])} decisions)")
    out.append("")
    for r in sorted(records, key=lambda x: parse_ts(x["at"])):
        cells = []
        for sid in lanes:
            if sid == r.get("session"):
                cells.append("●")
            elif spans[sid][0] <= parse_ts(r["at"]) <= spans[sid][1]:
                cells.append("│")
            else:
                cells.append(" ")
        t = timings.get(r["id"])
        timing = ""
        if t:
            timing = f"  [{fmt_span(t['active_s'])} active"
            timing += f", {fmt_span(t['idle_s'])} idle" if t["idle_s"] else ""
            timing += "]" + (" ~" if t["unreliable"] else "")
        out.append(f"  {' '.join(cells)}  {r['id']} {r['kind']:<9} "
                   f"{r['at'][:16]}{timing}")
        out.append(f"  {' '.join('│' if c in '●│' else ' ' for c in cells)}"
                   f"    {r['summary'][:72]}")
    return "\n".join(out)


def fmt_span(seconds):
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def render(records, path=None):
    """Chronological, human-readable. Derived from the ledger, never stored —
    a second persisted copy would be one more thing that can drift.

    The header names the file actually read. Hardcoding the canonical path meant
    `--render --ledger elsewhere.jsonl` printed someone else's rows under this
    repo's provenance.
    """
    gaps = {i["id"]: i for i in intervals(records)}
    filled = sum(1 for r in records if r.get("backfilled"))
    source = path if path is not None else LEDGER
    try:
        source = pathlib.Path(source).relative_to(REPO)
    except (TypeError, ValueError):
        pass
    lines = ["# Decision log", "",
             f"Generated from `{source}`. Do not edit by hand.", "",
             f"{len(records)} decisions"
             + (f", {filled} backfilled (instants unreliable)" if filled else ""), ""]
    for r in sorted(records, key=lambda x: parse_ts(x["at"])):
        gap = ""
        if r["id"] in gaps:
            g = gaps[r["id"]]
            gap = f" · +{fmt_span(g['seconds'])}" + (" ~" if g["unreliable"] else "")
        lines += [f"## {r['id']} · {r['kind']} · {r['at']}{gap}", "", r["summary"], "",
                  "- **Closed:** " + "; ".join(r["closed"]),
                  "- **Why:** " + r["why"]]
        if r.get("reverses_if"):
            lines.append("- **Reverses if:** " + r["reverses_if"])
        lines += [f"- `{r['branch']}` at `{r['head']}`"
                  + (" (dirty)" if r["dirty"] else ""), ""]
    return "\n".join(lines)


def self_test():
    now = datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)
    git = {"branch": "b", "head": "abc1234", "dirty": False}
    ok = {"kind": "design", "summary": "s", "closed": ["alt"], "why": "w"}
    checks = []

    def check(name, fn):
        try:
            checks.append((name, bool(fn())))
        except Exception as exc:  # a control that errors is a failed control
            checks.append((f"{name} [raised {exc!r}]", False))

    def refuses(payload):
        try:
            stamp(payload, now, git)
        except BarError:
            return True
        return False

    check("no closed alternative is refused", lambda: refuses({**ok, "closed": []}))
    check("whitespace-only closed is refused", lambda: refuses({**ok, "closed": ["  "]}))
    check("blank summary is refused", lambda: refuses({**ok, "summary": " "}))
    check("blank why is refused", lambda: refuses({**ok, "why": ""}))
    check("unknown kind is refused", lambda: refuses({**ok, "kind": "misc"}))
    check("a valid payload is accepted",
          lambda: stamp(ok, now, git)["id"] == decision_id(stamp(ok, now, git)))
    check("the id names the date and derives from content",
          lambda: stamp(ok, now, git)["id"].startswith("D-20260804-")
          and stamp({**ok, "summary": "other"}, now, git)["id"] != stamp(ok, now, git)["id"])
    check("no positional field is stamped", lambda: "seq" not in stamp(ok, now, git))

    forged = {**ok, **{f: "FORGED" for f in STAMPED}}
    rec = stamp(forged, now, git)
    check("no stamped field is caller-settable",
          lambda: not any(rec[f] == "FORGED" for f in STAMPED))
    check("provenance comes from the git argument",
          lambda: rec["branch"] == "b" and rec["head"] == "abc1234")

    # No duration is stored: it is a projection over instants.
    later = stamp(ok, now + timedelta(seconds=600), git)
    check("no interval is persisted on the record",
          lambda: "elapsed_s" not in rec and "elapsed_s" not in later)
    check("two instants of one decision have two ids", lambda: later["id"] != rec["id"])
    check("interval is derived from the two instants",
          lambda: intervals([rec, later])[0]["seconds"] == 600)
    check("a single record yields no interval", lambda: intervals([rec]) == [])
    check("derivation is order-independent",
          lambda: intervals([later, rec]) == intervals([rec, later]))

    back = stamp(ok, now + timedelta(seconds=600), git, backfill=True)
    check("a backfilled record says so", lambda: back["backfilled"] is True)
    check("an interval touching a backfill is marked unreliable",
          lambda: intervals([rec, back])[0]["unreliable"] is True)
    # Both ends live AND attributed. The earlier version of this control used the
    # sessionless pair above and asserted the interval was reliable, which is the
    # very thing that made a gap between two unrelated invocations read as work.
    live_a = stamp(ok, now, git, session="sess-live")
    live_b = stamp(ok, now + timedelta(seconds=600), git, session="sess-live")
    check("an interval between live records in one session is not",
          lambda: intervals([live_a, live_b])[0]["unreliable"] is False)
    check("an interval between records with no session is never reliable",
          lambda: intervals([rec, later])[0]["unreliable"] is True)
    check("a sessionless gap is still reported, not dropped",
          lambda: intervals([rec, later])[0]["seconds"] == 600)

    # Active/idle comes from the action stream, and a long silence is not active.
    base = now
    actions = [base, base + timedelta(seconds=60), base + timedelta(seconds=120),
               base + timedelta(seconds=120 + IDLE_S + 300)]
    span = split_span(actions, base, base + timedelta(seconds=120 + IDLE_S + 300))
    check("close actions count as active", lambda: span["active_s"] == 120)
    check("a long silence is idle, not active",
          lambda: span["idle_s"] == IDLE_S + 300)
    check("nothing is dropped from the span",
          lambda: span["active_s"] + span["idle_s"] == 120 + IDLE_S + 300)
    check("the action count is reported", lambda: span["actions"] == 4)
    check("an empty action stream yields no time",
          lambda: split_span([], base, base + timedelta(hours=1))["active_s"] == 0)
    check("waiting below the threshold stays active",
          lambda: split_span([base, base + timedelta(seconds=IDLE_S - 1)], base,
                             base + timedelta(seconds=IDLE_S))["idle_s"] == 0)
    # The span's own ends are gaps too. A decision's instant is stamped apart from
    # the action stream, so an action never lands exactly on a boundary and the
    # head and tail gaps are the normal case — walking only between actions
    # reported a 300s span as 100s.
    edged = split_span([base + timedelta(seconds=100), base + timedelta(seconds=200)],
                       base, base + timedelta(seconds=300))
    check("the whole span is accounted for, not just between actions",
          lambda: edged["active_s"] + edged["idle_s"] == 300)
    check("the head and tail gaps are counted as active when short",
          lambda: edged["active_s"] == 300)
    one = split_span([base + timedelta(seconds=150)], base, base + timedelta(seconds=300))
    check("a single action still accounts for its whole span",
          lambda: one["active_s"] + one["idle_s"] == 300 and one["actions"] == 1)
    check("an actionless span is still time, and it is idle",
          lambda: split_span([], base, base + timedelta(hours=1))["idle_s"] == 3600)
    # Counting the boundaries made the inverted case reachable: one gap of
    # end - start, with nothing between them to keep it positive.
    inverted = split_span([], base + timedelta(seconds=300), base)
    check("an inverted span yields nothing, never negative time",
          lambda: inverted["active_s"] == 0 and inverted["idle_s"] == 0)
    check("an inverted span is not silently reliable",
          lambda: inverted["actions"] == 0)
    # An action stream is mostly sub-second gaps, and truncating each one
    # independently threw all of it away: 1000 actions 0.9s apart reported 1
    # second of a 900-second span. Measured on the real ledger, the per-gap
    # int() lost 947 seconds across 32 spans.
    dense = [base + timedelta(milliseconds=900 * i) for i in range(1, 1001)]
    packed = split_span(dense, base, base + timedelta(seconds=901))
    check("sub-second gaps are not each truncated away",
          lambda: packed["active_s"] == 901)
    check("the dense span still counts every action",
          lambda: packed["actions"] == 1000)
    # Session attribution, and intervals that never cross a session boundary.
    s1 = stamp(ok, base, git, session="sess-a")
    s2 = stamp(ok, base + timedelta(seconds=120), git, session="sess-a")
    s3 = stamp(ok, base + timedelta(days=1), git, session="sess-b")
    check("the session is stamped from the argument", lambda: s1["session"] == "sess-a")
    check("session is not caller-settable",
          lambda: stamp({**ok, "session": "FORGED"}, base, git,
                        session="sess-a")["session"] == "sess-a")
    check("an absent session records None, not a guess",
          lambda: stamp(ok, base, git)["session"] is None)
    check("lanes group by session",
          lambda: list(by_session([s1, s2, s3])) == ["sess-a", "sess-b"])

    acts = {"sess-a": actions, "sess-b": [base + timedelta(days=1, seconds=-60),
                                          base + timedelta(days=1)]}
    rows = timeline_rows([s1, s2, s3], acts)
    check("one row per decision, not per pair", lambda: len(rows) == 3)
    check("the first decision measures from session start",
          lambda: rows[0]["from"] == "session start")
    check("later decisions measure from the previous one",
          lambda: rows[1]["from"] == "previous decision")
    by_id = {r["id"]: r for r in rows}
    check("a cross-session gap is never counted as work",
          lambda: by_id[s3["id"]]["active_s"] == 60)
    check("a session with no transcript reports zero, not a guess",
          lambda: timeline_rows([s1], {})[0]["active_s"] == 0
          and timeline_rows([s1], {})[0]["unreliable"] is True)

    g = graph([s1, s2, s3], rows)
    check("the graph opens one lane per session",
          lambda: "lane 1" in g and "lane 2" in g and "lane 3" not in g)
    check("each decision sits on its own lane",
          lambda: g.count("●") == 3)

    # The ledger gate: a hand-edited or forged row must fail, a clean one pass.
    good = [stamp(ok, base, git, session="s"),
            stamp(ok, base + timedelta(seconds=1), git, session="s")]
    check("a clean ledger has no problems", lambda: check_ledger(good) == [])
    check("a forged id fails", lambda: check_ledger(
        [{**good[0], "id": "D-9999"}]) != [])
    check("an edited summary fails the id it was stamped under", lambda: check_ledger(
        [good[0], {**good[1], "summary": "rewritten by hand"}]) != [])
    check("an edited instant fails the id it was stamped under", lambda: check_ledger(
        [good[0], {**good[1], "at": "2026-08-04T15:00:09+00:00"}]) != [])
    check("a leftover positional seq fails", lambda: check_ledger(
        [good[0], {**good[1], "seq": 2}]) != [])
    # EVERY field is bound, not only the three that name the decision: a rewritten
    # closed/why/kind/reverses_if or a rewritten provenance stamp fails the id.
    for field, value in (("closed", ["another alt"]), ("why", "rewritten"),
                         ("kind", "stop"), ("reverses_if", "planted"),
                         ("branch", "other"), ("head", "0000000"), ("dirty", True),
                         ("session", "elsewhere"), ("backfilled", True)):
        check(f"an edited {field} fails the id it was stamped under",
              lambda f=field, v=value: check_ledger([{**good[0], f: v}]) != [])
    check("a duplicate id fails", lambda: check_ledger([good[0], good[0]]) != [])
    # Merge: two ledgers appended apart concatenate clean in either order — the
    # property positional ids could not have, and the reason they are gone.
    branch_a = [stamp(ok, base, git, session="A"),
                stamp(ok, base + timedelta(hours=2), git, session="A")]
    branch_b = [stamp({**ok, "summary": "on b"}, base + timedelta(hours=1), git, session="B")]
    check("ledgers written apart concatenate clean",
          lambda: check_ledger(branch_a + branch_b) == [] and check_ledger(branch_b + branch_a) == [])
    check("an earlier instant appended later is a merge, not a hand edit",
          lambda: check_ledger([branch_a[1], branch_b[0]]) == [])
    # Migration: positional rows become content rows; already-content rows are untouched.
    legacy = [{**good[0], "id": "D-0001", "seq": 1}, {**good[1], "id": "D-0002", "seq": 2}]
    migrated, moved = migrate(legacy)
    check("--migrate rewrites positional ids to content ids and drops seq",
          lambda: check_ledger(migrated) == [] and set(moved) == {"D-0001", "D-0002"}
          and all("seq" not in r for r in migrated))
    check("--migrate is idempotent", lambda: migrate(migrated) == (migrated, {}))
    # --merge is a union by id: a record both branches carry appears once, a record
    # only the other branch carries is appended, and a positional other branch is
    # migrated on the way in.
    shared = branch_a[0]
    only_theirs = stamp({**ok, "summary": "only on the other branch"}, base + timedelta(hours=3),
                        git, session="B")
    merged_rows, appended = merge(branch_a, [shared, only_theirs])
    check("--merge appends only what is not already here by id",
          lambda: [r["id"] for r in appended] == [only_theirs["id"]]
          and merged_rows.count(shared) == 1 and check_ledger(merged_rows) == [])
    check("--merge migrates a positional other branch on the way in",
          lambda: merge(branch_a, [{**only_theirs, "id": "D-0007", "seq": 7}])[1][0]["id"]
          == only_theirs["id"])
    check("an interval never crosses a session boundary",
          lambda: [i["id"] for i in intervals([s1, s2, s3])] == [s2["id"]])
    check("the log and the projection agree on what is not work",
          lambda: f"## {s3['id']}" in render([s1, s2, s3])
          and " · +" not in render([s3]))
    check("a row closing nothing fails", lambda: check_ledger(
        [{**good[0], "closed": []}]) != [])
    check("an unknown kind fails", lambda: check_ledger(
        [{**good[0], "kind": "misc"}]) != [])
    check("a non-instant at fails", lambda: check_ledger(
        [{**good[0], "at": "yesterday"}]) != [])
    check("a non-string at is reported, not raised", lambda: check_ledger(
        [{**good[0], "at": 123}]) != [])
    check("check_ledger is pure over rows: no rows, no row problems",
          lambda: check_ledger([]) == [])

    # A row that passes --check must survive every projection that consumes it.
    # The required set was a hand-written subset, so a row missing `branch` was
    # declared valid and then crashed --render on the very next line.
    for field in STAMPED + SEMANTIC:
        check(f"a row missing {field!r} fails --check",
              lambda f=field: check_ledger([{k: v for k, v in good[0].items()
                                             if k != f}]) != [])
    check("every field --check requires, --render can index",
          lambda: render([good[0]]) and True)

    # `closed` is joined by --render, so its SHAPE is load-bearing: a bare string
    # is iterable and non-blank, passing a truthiness bar and rendering as one
    # alternative per character.
    check("closed as a bare string fails", lambda: check_ledger(
        [{**good[0], "closed": "oops"}]) != [])
    check("closed holding a non-string fails", lambda: check_ledger(
        [{**good[0], "closed": ["ok", 7]}]) != [])
    check("closed as a mapping fails", lambda: check_ledger(
        [{**good[0], "closed": {"a": 1}}]) != [])
    check("a proper list of alternatives passes", lambda: check_ledger(
        [stamp({**ok, "closed": ["a", "b"]}, base, git, session="s")]) == [])

    # Shape is not only `closed`'s problem. Validating `str(value)` checks a
    # stringified COPY, so a numeric summary was declared clean and then raised
    # TypeError inside render's join — the same defect one field over.
    for field, bad in (("summary", 7), ("why", ["a"]), ("branch", 3), ("head", 9)):
        check(f"a non-string {field} fails --check",
              lambda f=field, b=bad: check_ledger([{**good[0], f: b}]) != [])
    check("a non-string session fails --check", lambda: check_ledger(
        [{**good[0], "session": 5}]) != [])
    check("a null session is still valid — it means no harness",
          lambda: check_ledger([stamp(ok, base, git, session=None)]) == [])
    check("a non-bool dirty fails --check", lambda: check_ledger(
        [{**good[0], "dirty": "false"}]) != [])
    # Optional fields are still rendered the moment they are present, so their
    # types are load-bearing too — "false" reads as true, and an int concatenates
    # into a TypeError.
    check("a non-bool backfilled fails --check", lambda: check_ledger(
        [{**good[0], "backfilled": "false"}]) != [])
    check("a non-string reverses_if fails --check", lambda: check_ledger(
        [{**good[0], "reverses_if": 7}]) != [])
    # Stamped WITH the field, because a reverses_if planted after stamping is exactly
    # the hand edit the id now catches.
    with_reverse = stamp({**ok, "reverses_if": "x"}, base, git, session="s")
    check("a proper reverses_if still passes and renders", lambda: check_ledger(
        [with_reverse]) == [] and "Reverses if" in render([with_reverse]))
    check("every row --check accepts, --render renders",
          lambda: isinstance(render([{**good[0], "session": None}]), str))

    # The artifact itself. check_ledger walks rows and cannot see the file, so a
    # deleted ledger reported OK over zero records — the single most complete
    # failure this gate exists to catch.
    with tempfile.TemporaryDirectory() as td:
        gone = pathlib.Path(td) / "decisions.jsonl"
        check("a missing ledger file fails", lambda: check_artifact(gone, []) != [])
        gone.write_text("", encoding="utf-8")
        check("an empty ledger file fails", lambda: check_artifact(gone, []) != [])
        gone.write_text(json.dumps(good[0]) + "\n", encoding="utf-8")
        check("a ledger with records passes the artifact check",
              lambda: check_artifact(gone, read_ledger(gone)) == [])
        check("the artifact check reads the same rows --check validates",
              lambda: read_ledger(gone) == [good[0]])

    # The WIRING, not just the function. A control that calls check_artifact
    # directly proves the function works and says nothing about whether --check
    # calls it — which is how a fix ships inert. This runs the real dispatch over
    # a planted artifact and reads the exit status the parity gate reads.
    def check_exit(path):
        return subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--check", "--ledger", str(path)],
            capture_output=True, text=True).returncode

    with tempfile.TemporaryDirectory() as td:
        planted = pathlib.Path(td)
        (planted / "rows.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in good), encoding="utf-8")
        (planted / "empty.jsonl").write_text("", encoding="utf-8")
        (planted / "bad.jsonl").write_text(
            json.dumps({**good[0], "closed": "oops"}) + "\n", encoding="utf-8")
        check("--check accepts a clean planted ledger",
              lambda: check_exit(planted / "rows.jsonl") == 0)
        check("--check refuses an absent ledger",
              lambda: check_exit(planted / "absent.jsonl") != 0)
        check("--check refuses an empty ledger",
              lambda: check_exit(planted / "empty.jsonl") != 0)
        check("--check refuses a row the projections would corrupt",
              lambda: check_exit(planted / "bad.jsonl") != 0)

        # The seam is read-only, and says so rather than appending elsewhere.
        # Run a COPY laid out so its own LEDGER resolves inside the temp dir: a
        # control must not be able to write to the real log by failing, and this
        # one's failure mode is precisely an append that should not have happened.
        elsewhere = planted / "copy" / "decisions"
        elsewhere.mkdir(parents=True)
        (elsewhere / "record-decision.py").write_text(
            pathlib.Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
        refused = subprocess.run(
            [sys.executable, str(elsewhere / "record-decision.py"),
             "--ledger", str(planted / "rows.jsonl"), "--kind", "design",
             "--summary", "s", "--closed", "a", "--why", "w"],
            capture_output=True, text=True)
        check("recording into a redirected ledger is refused, not silently ignored",
              lambda: refused.returncode != 0
              and "--ledger selects the ledger to READ" in refused.stderr)
        check("the refusal happens before anything is written anywhere",
              lambda: not (elsewhere / "decisions.jsonl").exists()
              and read_ledger(planted / "rows.jsonl") == good)

        # The read projections get the artifact's own check too. --render over a
        # missing file printed a confident "0 decisions" under this repo's
        # provenance, which is a claim about a file nobody has.
        def read_exit(flag, path):
            return subprocess.run(
                [sys.executable, os.path.abspath(__file__), flag, "--ledger", str(path)],
                capture_output=True, text=True)
        for flag in ("--render", "--timeline", "--graph"):
            check(f"{flag} refuses an absent ledger",
                  lambda f=flag: read_exit(f, planted / "absent.jsonl").returncode != 0)
        check("--render names the file it actually read",
              lambda: f"`{planted / 'rows.jsonl'}`"
              in read_exit("--render", planted / "rows.jsonl").stdout)
        check("--render still names the canonical ledger by its repo-relative path",
              lambda: "`decisions/decisions.jsonl`" in render(good))

        # Damage reaching reliability is a WIRING claim too. Injecting damage into
        # timeline_rows proves the helper honours it and says nothing about
        # whether --timeline passes it in — dropping that one keyword argument
        # left every row reliable with the self-test still green.
        (planted / "one.jsonl").write_text(
            json.dumps(good[0]) + "\n", encoding="utf-8")
        proj = planted / "projects" / "p"
        proj.mkdir(parents=True)
        clean = ('{"timestamp":"2026-08-04T14:59:00Z"}\n'
                 '{"timestamp":"2026-08-04T14:59:30Z"}\n')

        def timeline_out(transcript):
            (proj / f"{good[0]['session']}.jsonl").write_text(transcript, encoding="utf-8")
            return subprocess.run(
                [sys.executable, os.path.abspath(__file__), "--timeline",
                 "--ledger", str(planted / "one.jsonl"),
                 "--transcripts", str(planted / "projects")],
                capture_output=True, text=True).stdout

        check("a clean transcript yields a reliable row through the real dispatch",
              lambda: "~unreliable" not in timeline_out(clean))
        check("--timeline carries transcript damage into the row it prints",
              lambda: "~unreliable" in timeline_out(clean + "{BROKEN\n"))

    # #8 — a hand-edited instant is caught by the id it was stamped under, not by
    # its position: an out-of-order instant that IS its own content is a merge.
    back_in_time = [good[0], {**good[1], "at": "2000-01-01T00:00:00+00:00"}]
    check("a hand-edited instant fails",
          lambda: check_ledger(back_in_time) != [])
    check("equal instants are allowed (a batch under one lock)",
          lambda: check_ledger([good[0], stamp({**ok, "summary": "same instant"}, base, git,
                                                session="s")]) == [])

    # #9 — ordering keys on the instant, not on how it is spelled. Same moment
    # written in two zones must not reorder.
    early = {**good[0], "at": "2026-08-04T16:46:13+09:00"}      # 07:46:13Z
    late = {**good[1], "at": "2026-08-04T07:46:33+00:00"}       # 07:46:33Z
    check("mixed offsets order by instant, not by text",
          lambda: intervals([early, late])[0]["id"] == late["id"])
    check("a mixed-offset interval is never negative",
          lambda: intervals([early, late])[0]["seconds"] == 20)
    # #8 — a naive instant must be reported, not crash the comparison.
    naive = [good[0], {**good[1], "at": "2026-08-04T00:00:01"}]
    check("a naive instant is reported, not raised",
          lambda: any("no UTC offset" in p for p in check_ledger(naive)))

    # #4 — lane containment is a plain comparison, not a sort key, so the previous
    # round's sort-key fix missed it. Row ORDER cannot detect that; only whether an
    # open lane is drawn through another session's row can. Session A spans
    # 07:00Z-09:00Z written as +09:00; B sits at 08:00Z inside it, but as text
    # "16:00+09:00" > "08:00+00:00", so a string compare declares A closed and
    # omits its continuation bar.
    a1 = {**good[0], "id": "D-0001", "seq": 1, "session": "A", "at": "2026-08-04T16:00:00+09:00"}
    b1 = {**good[0], "id": "D-0002", "seq": 2, "session": "B", "at": "2026-08-04T08:00:00+00:00"}
    a2 = {**good[0], "id": "D-0003", "seq": 3, "session": "A", "at": "2026-08-04T18:00:00+09:00"}
    lanes = graph([a1, b1, a2])
    b_row = [l for l in lanes.splitlines() if "D-0002" in l][0]
    check("an open lane continues through another session's row",
          lambda: "│" in b_row)
    check("graph places every record on a lane", lambda: lanes.count("●") == 3)

    check("render orders by instant across offsets",
          lambda: render([late, early]).index(early["id"]) <
                  render([late, early]).index(late["id"]))

    # Damaged transcript lines are counted, never silently truncating the stream.
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "t.jsonl"
        f.write_text('{"timestamp":"2026-08-04T00:00:00Z"}\n'
                     '{"timestamp": BROKEN}\n'
                     '{"timestamp":"2026-08-04T00:01:00Z"}\n', encoding="utf-8")
        got, dmg = load_actions([str(f)])
    check("a malformed line does not end the scan", lambda: len(got) == 2)
    check("the malformed line is counted", lambda: dmg == 1)

    # A line truncated badly enough to lose the marker must still be counted; the
    # earlier pre-filter skipped it before the counter could see it.
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "cut.jsonl"
        f.write_text('{"timestamp":"2026-08-04T00:00:00Z"}\n'
                     '{"type":"assistant","mes\n', encoding="utf-8")
        got2, dmg2 = load_actions([str(f)])
    check("a truncated line with no marker is still counted",
          lambda: dmg2 == 1 and len(got2) == 1)
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "meta.jsonl"
        f.write_text('{"type":"mode"}\n{"type":"ai-title"}\n', encoding="utf-8")
        got3, dmg3 = load_actions([str(f)])
    check("valid metadata rows are not miscounted as damage",
          lambda: dmg3 == 0 and got3 == [])

    # A row that HAS a timestamp but not a usable one is damage. This one used to
    # raise AttributeError out of parse_ts and abort --timeline entirely, so no
    # count was reached and no row was produced at all.
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "nonstring.jsonl"
        f.write_text('{"timestamp":"2026-08-04T00:00:00Z"}\n'
                     '{"timestamp": 123}\n', encoding="utf-8")
        got4, dmg4 = load_actions([str(f)])
    check("a non-string timestamp is damage, not a crash",
          lambda: dmg4 == 1 and len(got4) == 1)

    # A row carrying the key with a falsy value is damaged too. Skipping on
    # truthiness treated `0` and `""` as metadata, so those lines vanished from
    # both the stream and the damage count.
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "falsy.jsonl"
        f.write_text('{"timestamp":"2026-08-04T00:00:00Z"}\n'
                     '{"timestamp": 0}\n{"timestamp": ""}\n', encoding="utf-8")
        got5, dmg5 = load_actions([str(f)])
    check("a falsy timestamp is damage, not metadata",
          lambda: dmg5 == 2 and len(got5) == 1)

    # An explicit null is a LOST instant, not an absent one — `.get()` could not
    # tell it from a metadata row. And a naive instant parsed fine, then raised
    # TypeError out of the sort below, losing the whole projection to one line.
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "edge.jsonl"
        f.write_text('{"timestamp":"2026-08-04T00:00:00Z"}\n'
                     '{"timestamp": null}\n'
                     '{"timestamp":"2026-08-04T00:01:00"}\n'
                     '{"type":"mode"}\n', encoding="utf-8")
        got6, dmg6 = load_actions([str(f)])
    check("an explicit null timestamp is damage, not an absent key",
          lambda: dmg6 == 2 and len(got6) == 1)
    check("a naive transcript instant is counted, not raised",
          lambda: all(t.tzinfo is not None for t in got6))
    check("a row with no timestamp key is still metadata",
          lambda: dmg6 == 2)

    # Damage must reach the rows derived from it: a missing instant can move a gap
    # across the idle threshold, so the span is short by an unknown amount. The
    # count was summed for a footnote and dropped before reliability was computed.
    check("a session with a damaged transcript yields no reliable row",
          lambda: all(r["unreliable"] for r in
                      timeline_rows([s1, s2], acts, damage_by_session={"sess-a": 1})))
    check("the same rows without damage are reliable",
          lambda: not any(r["unreliable"] for r in
                          timeline_rows([s1, s2], acts)[1:]))

    # Session capture and transcript resolution, per host. Reading only Claude's
    # variable gave every Codex-recorded row a null session, which shares the
    # unattributed lane and resolves no transcript.
    def with_env(**wanted):
        saved = {k: os.environ.get(k) for k in wanted}

        def apply(values):
            for k, v in values.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        apply(wanted)
        try:
            return session_id()
        finally:
            apply(saved)

    check("the Claude session id is captured",
          lambda: with_env(CLAUDE_CODE_SESSION_ID="c-1", CODEX_THREAD_ID=None) == "c-1")
    check("the Codex thread id is captured",
          lambda: with_env(CLAUDE_CODE_SESSION_ID=None, CODEX_THREAD_ID="x-1") == "x-1")
    check("neither host running records None, not a guess",
          lambda: with_env(CLAUDE_CODE_SESSION_ID=None, CODEX_THREAD_ID=None) is None)
    # Measured: a Claude session running `codex exec` passes its own variable into
    # the inner process, so both are set and the inner Codex thread is the one
    # doing the work. Preferring Claude stamped the outer session onto it.
    check("the inner Codex thread wins when a Claude session spawned it",
          lambda: with_env(CLAUDE_CODE_SESSION_ID="outer", CODEX_THREAD_ID="inner")
          == "inner")

    with tempfile.TemporaryDirectory() as td:
        cl = pathlib.Path(td) / "projects" / "some-project"
        cx = pathlib.Path(td) / "sessions" / "2026" / "08" / "05"
        cl.mkdir(parents=True)
        cx.mkdir(parents=True)
        (cl / "sess-c.jsonl").write_text("", encoding="utf-8")
        (cx / "rollout-2026-08-05T11-08-25-thread-x.jsonl").write_text("", encoding="utf-8")
        roots = transcript_roots(cl.parent, cx.parents[2])
        check("a Claude transcript resolves by filename",
              lambda: resolve_transcript("sess-c", roots) == str(cl / "sess-c.jsonl"))
        check("a Codex transcript resolves by the id inside its rollout name",
              lambda: resolve_transcript("thread-x", roots) ==
              str(cx / "rollout-2026-08-05T11-08-25-thread-x.jsonl"))
        check("an unknown session resolves to nothing, not to someone else's",
              lambda: resolve_transcript("no-such-session", roots) is None)
        check("a wildcard session id matches nothing",
              lambda: resolve_transcript("*", roots) is None)
        check("no session resolves to nothing",
              lambda: resolve_transcript(None, roots) is None)

    # No evidence means unreliable, not a confident zero.
    none_rows = timeline_rows([stamp(ok, base, git),
                               stamp(ok, base + timedelta(seconds=60), git)], {})
    check("an unknown session is never reliable",
          lambda: all(r["unreliable"] for r in none_rows))
    check("a span with no actions is never reliable",
          lambda: timeline_rows([s1, s2], {"sess-a": []})[1]["unreliable"] is True)

    out = render([later, rec])
    check("render is chronological", lambda: out.index(rec["id"]) < out.index(later["id"]))
    check("render shows a derived interval", lambda: "+10m" in out)
    check("render marks an unreliable interval", lambda: "~" in render([rec, back]))

    failed = [n for n, good in checks if not good]
    for name in failed:
        print(f"record-decision --self-test: FAIL: {name}", file=sys.stderr)
    if failed:
        sys.exit(1)
    if not checks:
        sys.exit("record-decision --self-test: no controls ran")
    print(f"record-decision --self-test: OK ({len(checks)} controls)")


def main():
    ap = argparse.ArgumentParser(
        description="Record one decision about developing this repo.")
    ap.add_argument("--kind", choices=KINDS,
                    help="design: how it is built. direction: what to work on. "
                         "stop: abandon or block. steering: a redirect mid-work.")
    ap.add_argument("--summary", help="what was decided, one or two sentences")
    ap.add_argument("--closed", action="append", default=[],
                    help="an alternative this closed; repeatable, at least one")
    ap.add_argument("--why", help="the reason, and the evidence it rests on")
    ap.add_argument("--reverses-if", dest="reverses_if",
                    help="what would overturn this")
    ap.add_argument("--backfill", action="store_true",
                    help="record a past decision; its instant is when it was "
                         "typed, so intervals touching it are marked unreliable")
    ap.add_argument("--check", action="store_true",
                    help="validate the ledger on disk and exit")
    ap.add_argument("--merge", metavar="PATH", default=None,
                    help="append the records of another ledger that are not already "
                         "here, matched by content id, and exit")
    ap.add_argument("--migrate", action="store_true",
                    help="rewrite ids to content ids in place (idempotent) and print "
                         "the old→new map; a one-time move off positional ids")
    ap.add_argument("--ledger", default=None,
                    help=f"the ledger to read (default: {LEDGER}). A seam, so a "
                         f"control can run --check against a planted artifact "
                         f"through the real dispatch rather than around it")
    ap.add_argument("--render", action="store_true",
                    help="print the log chronologically and exit")
    ap.add_argument("--timeline", action="store_true",
                    help="active/idle per decision, from session action timestamps")
    ap.add_argument("--graph", action="store_true",
                    help="sessions as lanes, decisions as nodes, in time order")
    ap.add_argument("--transcripts", default=None,
                    help=f"Claude session transcript root (default: {CLAUDE_SESSIONS})")
    ap.add_argument("--codex-sessions", default=None,
                    help=f"Codex session transcript root (default: {CODEX_SESSIONS})")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    ledger = pathlib.Path(args.ledger) if args.ledger else LEDGER
    records = read_ledger(ledger)
    # Every projection reads the artifact, so every projection is entitled to the
    # artifact's own check. Running it only under --check let `--render` print a
    # confident "0 decisions" over a file that was not there.
    if args.check or args.render or args.timeline or args.graph:
        gone = check_artifact(ledger, records)
        if gone:
            for msg in gone:
                print(f"record-decision: {msg}", file=sys.stderr)
            sys.exit(1)
    if args.check:
        problems = check_ledger(records)
        for msg in problems:
            print(f"record-decision --check: {msg}", file=sys.stderr)
        if problems:
            sys.exit(1)
        print(f"record-decision --check: OK ({len(records)} records, "
              f"ids content-bound)")
        return
    if args.merge or args.migrate:
        # Read INSIDE the lock and rewrite from what was read there. Reading before
        # the lock, as the recorder's own append path never did, let a decision
        # recorded between the read and the lock be truncated away by the rewrite
        # (review of PR #32).
        other = pathlib.Path(args.merge) if args.merge else None
        if other is not None and not other.is_file():
            sys.exit(f"record-decision: --merge {other} is not a file")
        with ledger.open("r+", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            fh.seek(0)
            locked = [json.loads(l) for l in fh.read().splitlines() if l.strip()]
            if other is not None:
                rows, appended = merge(locked, read_ledger(other))
                problems = check_ledger(rows)
                if problems:
                    for msg in problems:
                        print(f"record-decision --merge: {msg}", file=sys.stderr)
                    sys.exit(1)
            else:
                rows, moved = migrate(locked)
            fh.seek(0)
            fh.truncate()
            fh.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        if other is not None:
            for r in appended:
                print(f"+ {r['id']}  {r['summary'][:70]}")
            print(f"record-decision --merge: {len(appended)} appended, "
                  f"{len(rows) - len(appended)} already here")
        else:
            for old, new in moved.items():
                print(f"{old} -> {new}")
            print(f"record-decision --migrate: {len(moved)} id(s) rewritten, "
                  f"{len(rows) - len(moved)} already content-bound")
        return
    if args.render:
        print(render(records, ledger))
        return
    if args.timeline or args.graph:
        roots = transcript_roots(args.transcripts, args.codex_sessions)
        scanned = {sid: load_actions([t]) if (t := resolve_transcript(sid, roots))
                   else ([], 0) for sid in by_session(records)}
        loaded = {sid: a for sid, (a, _) in scanned.items()}
        damage = {sid: d for sid, (_, d) in scanned.items()}
        damaged = sum(damage.values())
        missing = [sid for sid, a in loaded.items() if not a]
        rows = timeline_rows(records, loaded, damage_by_session=damage)
        if args.graph:
            print(graph(records, rows))
        else:
            total = sum(len(a) for a in loaded.values())
            print(f"{total} action instants from {len(loaded)} session(s)")
            for row in rows:
                mark = " ~unreliable" if row["unreliable"] else ""
                print(f"  {(row['session'] or 'unattributed')[:8]}  {row['id']:<8} "
                      f"{row['kind']:<9} active {fmt_span(row['active_s']):>6}  "
                      f"idle {fmt_span(row['idle_s']):>6}  "
                      f"({row['actions']} actions, from {row['from']}){mark}")
        if damaged:
            print(f"\n{damaged} unreadable transcript line(s) skipped — spans over "
                  f"the affected window are short by an unknown amount", file=sys.stderr)
        if missing:
            print(f"\nno transcript found for {len(missing)} session(s): "
                  f"{', '.join((m or 'unattributed')[:8] for m in missing)} — "
                  f"their spans report zero rather than a guess", file=sys.stderr)
        return

    # `--ledger` is a read seam. Honouring it here as well would let a recording
    # land somewhere other than the log, and ignoring it silently would be worse:
    # the caller would believe it had. So the combination is refused.
    if args.ledger:
        sys.exit("record-decision: --ledger selects the ledger to READ; a decision "
                 "is always appended to the canonical one. Drop --ledger to record.")

    payload = {"kind": args.kind, "summary": args.summary or "",
               "closed": args.closed, "why": args.why or "",
               "reverses_if": args.reverses_if}
    git = git_facts()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.seek(0)
        current = [json.loads(l) for l in fh.read().splitlines() if l.strip()]
        try:
            record = stamp(payload, datetime.now().astimezone(), git,
                           session=session_id(), backfill=args.backfill)
        except BarError as exc:
            sys.exit(f"record-decision: {exc}")
        if any(r.get("id") == record["id"] for r in current):
            # Field-for-field the same as a row already here: the same decision typed
            # twice within a second. Refused rather than written as a duplicate id the
            # check would then fail on.
            sys.exit(f"record-decision: {record['id']} is already recorded (an identical "
                     f"record exists)")
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"{record['id']} recorded")


if __name__ == "__main__":
    main()
