#!/usr/bin/env python3
"""S2, the reading views (design §5.4, §13.4; the amendment of its input bound, 2026-10-21).

For every eligible transcript, and the child transcripts linked to it, `run` leaves in the run directory:

* `sources/<version_sha>.jsonl` - the immutable copy of the version (decompressed if the host compressed it,
  mode 0444, named by its own sha256). It is raw, and no model reads it: the owner's openable locator points here.
* `redacted/<version_sha>.<redaction_version>.jsonl` - the projection of every content block of the version
  (`projection.project`); the only text a window, a search hit or a quote is built from.
* `views/<transcript>/<n>.json` - the windows, `views/<transcript>/sequence.json` - the order they were cut from,
  `index/bm25/<transcript>.json` - the full-source search index, and `views.json` - the manifest of all of it.
  The manifest also carries, per transcript, the shape counts `digest.py` kept (`hints_of`): they rank what to
  read, and no claim rests on one, because evidence is a locator into a copy (design §5.5), never a count.

**What is viewed.** The content blocks of a record are the human, assistant and delegated text, the tool calls with
their arguments and the tool results (Claude: `user`/`assistant` records and the `queued_command` attachment a human
typed while the assistant worked; Codex: `response_item` messages of the `user` and `assistant` roles, calls and
outputs). Thinking, developer text, system and bookkeeping records are not blocks. A tool result longer than
`CLIP_OVER` characters is **clipped**: its head, its tail, and every line of the middle that reads as an error, kept
whole; the rest is a gap named in the omission manifest with its size, its span and the sha256 of the omitted
characters (so two results that look alike from outside, and differ inside, are told apart). A record is viewed when
the census says this run owes it: the records the window owns and has not processed, and the backlog on the latest
version. Anything else is shown only as the overlap (five entries each side of a window, each cut to
`OVERLAP_ITEM_BYTES`) and is `context`.

**Windows.** Entries are cut greedily into windows in record order. Every viewed entry is owned by exactly one window;
an entry too large for a window is split into **spans**, each a slice of the entry's view text with the mapping of
every shown stretch to the block's characters (`segments`), so the spans' union is the entry. A window never joins
two viewed runs that have unviewed records between them.

**The bound** (design §5.4 as amended, view-window calls only). The driver's part of a call - the window as
`render_window` writes it, plus the packet template, schema and instructions (`overhead`) - is at most
`bound.INPUT_BOUND` minus the seat's declared host allowance, in bytes (a token covers at least one byte), and, with the
allowance and the output reservation (`run.json`'s `output_caps.S3`, the cap every S3 call declares), within the seat's
context capacity. A window failing either is cut smaller.
`bound.check_observed` compares what a call really consumed with `bound.INPUT_BOUND`; above it is a host change
(`INPUT_BOUND_EXCEEDED`) and the dispatcher refuses every dispatch until an amendment of `host_allowance` follows.
No guarantee about the complete request is claimed.

**Expansion** (`expand`, `record_decision`): a clipped record is expanded into windows under the same bound and the
same span mapping, or skipped with a reason; `forced_records` names the records that may not be skipped (those
between a pending event and the next human turn) and `forced_by_search` those a claim's retrieval terms match in
the full redacted text, clipped spans included. A session is *view complete* when
every window passed the gate and every clipped record has an executed expansion or a recorded skip, *source
complete* when no span was skipped (`completeness`); `coverage_basis` is the order of design §5.4's coverage basis.

Failures are named by their first word: ALLOWANCE_UNDECLARED, WINDOW_UNBOUNDED, WINDOW_BOUND_EXCEEDED,
WINDOW_CAPACITY_EXCEEDED, INPUT_BOUND_EXCEEDED, SOURCE_CHANGED, SOURCE_TAMPERED, SOURCE_UNREADABLE,
VIEW_NAME_COLLISION, SET_MISMATCH, OVERLAP_MISSING, SPAN_UNION_MISMATCH, ERROR_LINE_DROPPED, EXPANSION_SKIPPED,
EXPANSION_DECISION_INVALID, EXPANSION_DECISION_CONFLICT, EXPANSION_SOURCE_DRIFT, EXPANSION_UNKNOWN. Under the production posture a transcript
whose work raises is quarantined under that name and the run goes on (design §4, `records.run_items`).

  views.py --self-test
"""
import bisect
import collections
import contextlib
import copy
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import bound, census, claims, coverage, declare, gate, ledger, lineage, projection, records, search, sources, stagelock, validate
from runlib.records import Refused

OVERLAP_TURNS = 5
OVERLAP_ITEM_BYTES = 700
OVERLAP_SLACK = 260          # header and cut marker of an overlap entry, beyond its text
# What one side's overlap may cost a window. The same reservation as before, but now it is filled from a
# slice counted in TURNS rather than in entries, and whatever does not fit is accounted rather than dropped.
OVERLAP_SIDE_BYTES = OVERLAP_TURNS * (OVERLAP_ITEM_BYTES + OVERLAP_SLACK)
HEADER_SLACK = 700           # the window's own heading lines
MIN_ENTRY_BYTES = 2048       # a window that cannot hold an entry this large is unbounded
CLIP_OVER, HEAD_CHARS, TAIL_CHARS = 4_000, 1_200, 800
ERROR_LINE = re.compile(r"(?i)\b(error|exception|traceback|fatal|failed|failure|denied|not found|no such file|cannot|"
                        r"can't|unable to|timed out|timeout|panic|segmentation fault)\b")
FORCED_BY = ("pending_event", "search_match", "none")
DECISIONS = ("expand", "skip")
ROLE_BACKLOG = re.compile(r"^backlog\(.+\)$")


# ---- the bound -------------------------------------------------------------------------------

def limits_of(run, overhead=bound.PACKET_OVERHEAD, seats_path=None):
    """The bound a view-window call keeps, from the declaration: the S3 seat's declared allowance, and the output cap
    the declaration gives S3's calls.

    Where the allowance comes from is this module's business; what the bound then IS belongs to
    `runlib/bound.py`, which both this side and the dispatcher import (the seam record of 2026-10-22).

    There is no capacity argument. It was one, and a caller could then cut a window against a number no
    declaration carried; the capacity now comes from the shared reader on every path, and a test that needs
    another one declares it in a `seats.json` fixture and names it with `seats_path` - the reader is the
    same, and so is what it requires of a declaration (BB#5). There is no reservation argument either, for the same
    reason: the cap is `run.json`'s `output_caps`, the number S3's calls declare (WP-08)."""
    seat = (run.get("seats") or {}).get("S3")
    entry = (run.get("host_allowance") or {}).get(seat)
    if not seat or not entry:
        raise Refused(f"ALLOWANCE_UNDECLARED seats.S3: {seat!r} has no host_allowance entry, so no view window can be cut "
                      "against a bound (measure it in preflight and declare it)")
    # BA#1: the seat's context size is host-reported evidence seats.json declares, and cutting a window
    # reads the SAME declaration the dispatcher admits against. There is no default: a window cut against
    # an invented capacity is a window cut against nothing.
    capacity, basis = gate.seat_capacity(seat, (run.get("host_versions") or {}).get(seat.partition(":")[0])
                                         or (entry.get("host_version")),
                                         **({"path": seats_path} if seats_path else {}))
    if capacity is None:
        raise Refused(f"CAPACITY_UNDECLARED seats.S3: {basis}; no window is cut against a capacity nobody "
                      "measured (the seat's context window is host-reported)")
    # The output reservation is the cap the S3 call will declare for its answer - the same number the
    # dispatcher admits that call against. There is no constant: a window cut against a reservation nobody
    # chose reserves nothing (the ruling of 2026-10-22), and the declaration is where it is chosen (WP-08).
    reservation = (run.get("output_caps") or {}).get(declare.VIEW_WINDOW_STAGE)
    if not (isinstance(reservation, int) and not isinstance(reservation, bool) and reservation > 0):
        raise Refused(f"CAP_UNDECLARED output_caps.S3: output-token cap {reservation!r}; a window is cut against the cap "
                      "the call will declare for its answer, and run.json declares it as a positive integer")
    return bound.limits(entry["allowance_tokens"], seat=seat, capacity=capacity, reservation=reservation,
                        overhead=overhead)


def observed_input_of(capture):
    """A retained capture's observed input, as `bound` defines it.

    A capture missing any of the three components is refused rather than read as a smaller number: a
    missing cache field would make every overrun look like a call within the bound."""
    observed, missing = bound.observed_of((capture or {}).get("usage") or {})
    if missing:
        raise Refused(f"CAPTURE_USAGE_MISSING {capture.get('call_id')}: {', '.join(missing)}; the observed input of a "
                      "call is input + cache creation + cache read, and a missing field is not a zero")
    return observed


CAPTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "captures"


def retained_capture(name, root=None):
    """One retained capture, read from `session-distill/fixtures/captures/` and refused by name when its bytes
    moved from the sha256 pinned in `captures.json`.

    A dictionary written at the point of use is not a capture: its counts are whatever the test needed, so a
    control built on one proves that the arithmetic runs, not that the boundary holds for anything a host
    produced. These files are pinned, so a count cannot be adjusted to make a control pass without the pin
    failing first.

    Two of the three are RETAINED captures of the frozen probe evidence of 2026-10-20, copied with their
    usage block alone and naming their source file, its sha256 and the extraction rule: `within-bound`
    (24,806 observed input) and `r-authoring` (333,706, above the view-window bound - which the bound does
    not govern, because an R-authoring call is a non-window call by the contract of design 8.6). The third,
    `window-overrun`, is SYNTHETIC and says so in its own `origin`: no retained capture of a view-window
    call above the bound exists, so its counts are fake and labelled as fake."""
    # `root` is the directory holding `captures.json` and `captures/`. It is a parameter so a control can
    # plant a mismatch in a COPY: the mismatch control used to write altered bytes into the tracked fixture
    # in the checkout and restore them in `finally`, which needs write access to the checkout and shows
    # other readers - a parallel self-test, an interrupted run - a fixture that is not the fixture.
    root = pathlib.Path(root) if root is not None else CAPTURES.parent
    pins = json.loads((root / "captures.json").read_text(encoding="utf-8"))["captures"]
    path, name = root / "captures" / f"{name}.json", f"{name}.json"
    if name not in pins or not path.is_file():
        raise Refused(f"CAPTURE_UNPINNED {name}: no capture fixture of that name is pinned in captures.json")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != pins[name]:
        raise Refused(f"CAPTURE_HASH_MISMATCH {path}: the file is sha256:{digest[:12]} and the pin says "
                      f"{pins[name][:12]}; a capture whose bytes moved is not the capture a control was written against")
    return json.loads(raw.decode("utf-8"))


# ---- blocks, clipping, entries ---------------------------------------------------------------

def record_items(host, rec, child):
    """The content blocks of one parsed record that the view shows: `(json_pointer, kind, tool, is_error, value)`.
    `kind` is human, delegated (a parent's instruction to a child), summary, assistant, tool_call or tool_result."""
    if not isinstance(rec, dict):
        return
    if host == "claude":
        message = rec.get("message") if isinstance(rec.get("message"), dict) else None
        if rec.get("type") == "user" and message and not rec.get("isMeta"):
            who = "delegated" if child or rec.get("isSidechain") is True else "summary" if rec.get("isCompactSummary") else "human"
            content = message.get("content")
            if isinstance(content, str):
                yield "/message/content", who, None, False, content
            for i, block in enumerate(content if isinstance(content, list) else []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    yield f"/message/content/{i}/text", who, None, False, block["text"]
                elif block.get("type") == "tool_result":
                    failed, inner = block.get("is_error") is True, block.get("content")
                    if isinstance(inner, str):
                        yield f"/message/content/{i}/content", "tool_result", None, failed, inner
                    for j, part in enumerate(inner if isinstance(inner, list) else []):
                        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                            yield f"/message/content/{i}/content/{j}/text", "tool_result", None, failed, part["text"]
        elif rec.get("type") == "assistant" and message and isinstance(message.get("content"), list):
            for i, block in enumerate(message["content"]):
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                    yield f"/message/content/{i}/text", "assistant", None, False, block["text"]
                elif isinstance(block, dict) and block.get("type") == "tool_use":
                    yield f"/message/content/{i}/input", "tool_call", block.get("name"), False, block.get("input")
        elif rec.get("type") == "attachment" and isinstance(rec.get("attachment"), dict):
            attachment = rec["attachment"]  # what a person typed while the assistant was working
            if attachment.get("type") == "queued_command" and isinstance(attachment.get("prompt"), str):
                yield "/attachment/prompt", "delegated" if child else "human", None, False, attachment["prompt"]
        return
    payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else None
    if rec.get("type") != "response_item" or not payload:
        return
    kind = payload.get("type")
    if kind == "message" and payload.get("role") in ("user", "assistant"):
        who = "assistant" if payload["role"] == "assistant" else "delegated" if child else "human"
        for i, block in enumerate(payload.get("content") if isinstance(payload.get("content"), list) else []):
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                yield f"/payload/content/{i}/text", who, None, False, block["text"]
    elif kind == "function_call":
        yield "/payload/arguments", "tool_call", payload.get("name"), False, payload.get("arguments")
    elif kind == "custom_tool_call":
        yield "/payload/input", "tool_call", payload.get("name"), False, payload.get("input")
    elif kind in ("function_call_output", "custom_tool_call_output"):
        out = payload.get("output")
        if isinstance(out, str):
            yield "/payload/output", "tool_result", None, False, out
        for j, part in enumerate(out if isinstance(out, list) else []):
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                yield f"/payload/output/{j}/text", "tool_result", None, False, part["text"]


def clip_parts(text, kind):
    """`([(type, a, b)], meta)`: `text` parts are shown, `gap` parts omitted, together tiling [0, len(text)).
    `meta` is None for a block shown whole; else the head, the tail, the error lines kept whole, the omitted span of
    the middle with the sha256 of its characters, and the gaps."""
    n = len(text)
    if kind != "tool_result" or n <= CLIP_OVER:
        return [("text", 0, n)], None
    head, tail = HEAD_CHARS, n - TAIL_CHARS
    shown, errors, offset = [(0, head), (tail, n)], [], 0
    for line in text.splitlines(keepends=True):
        a, b = offset, offset + len(line)
        offset = b
        if b > head and a < tail and ERROR_LINE.search(line):
            errors.append([a, b])
            shown.append((a, b))
    parts, pos = [], 0
    for a, b in coverage.normalize(shown):
        if a > pos:
            parts.append(("gap", pos, a))
        parts.append(("text", a, b))
        pos = b
    if pos < n:
        parts.append(("gap", pos, n))
    if not any(p[0] == "gap" for p in parts):
        return [("text", 0, n)], None
    return parts, {"head": [0, head], "tail": [tail, n], "error_lines": errors,
                   "gaps": [[a, b] for t, a, b in parts if t == "gap"],
                   "omitted_span": {"start": head, "end": tail, "sha256": records.sha256_bytes(text[head:tail].encode("utf-8"))}}


def compose(text, parts):
    """The view text of a block and its `segments`: where each shown stretch sits in the view and in the block."""
    view, segments, pos = [], [], 0
    for kind, a, b in parts:
        piece = text[a:b] if kind == "text" else f"\n[... {b - a} chars omitted ({a}-{b}) ...]\n"
        if kind == "text":
            segments.append({"view": [pos, pos + len(piece)], "block": [a, b]})
        view.append(piece)
        pos += len(piece)
    return "".join(view), segments


def make_entry(item, line, role, offset):
    text = item["text"]
    parts, meta = clip_parts(text, item["kind"])
    view, segments = compose(text, parts)
    entry = {"record_id": f"{line}{item['pointer']}", "line": line, "json_pointer": item["pointer"], "kind": item["kind"],
             "tool": item.get("tool"), "ts": item.get("ts"), "error": bool(item.get("error")), "window_role": role,
             # The locator rides on EVERY entry. It used to live inside `clipped`, which an ordinary human or
             # assistant message does not have, so an overlap omission of such a message wrote `offset: None`
             # into the manifest and expansion died on `seek(None)` - a defect no control could see, because
             # the one control that expanded an overlap row supplied an offset of its own.
             "size": len(text), "text": view, "segments": segments, "owned": True, "offset": offset}
    if meta:
        entry["clipped"] = {**meta, "forced_by": "none", "offset": offset}
    return entry


def omission_id(record_id, start, end):
    """The identity of ONE omitted interval: the record, the interval in the projected block's own
    coordinates, and a digest of both.

    A record id is not an identity. A record can lose several intervals - a clip in the middle, a context cut
    at 700 characters, the rest of it when a side's budget ran out - and keying the accounting by record
    meant one expansion discharged all of them. The digest is what makes the identity safe in a FILE NAME:
    the path sanitiser folds characters, so two different records could otherwise write to one path."""
    digest = hashlib.sha256(f"{record_id}\x00{start}\x00{end}".encode("utf-8")).hexdigest()[:12]
    return f"{record_id}@{start}-{end}#{digest}"


def interval_of(entry, lo, hi, view_start, view_end):
    """One segment's share of the view range [view_start, view_end), as a block interval with its hash, or
    None when the segment lies outside the range."""
    start, end = max(lo, view_start), min(hi, view_end)
    return None if start >= end else (start, end)


def omitted_intervals(entry, view_start, view_end):
    """Every interval of the PROJECTED BLOCK that the view range [view_start, view_end) of `entry` covers,
    each with the hash of its own characters.

    The coordinates matter more than they look. An overlap cut used to be recorded as `[700, len]` over the
    entry's own view text, while expansion reads those numbers as offsets into the block - so for a split
    span, or for a clipped record whose view elides a gap, the interval named characters that were never
    omitted, and the hash could only disagree. `segments` is the mapping the entry already carries, and it
    is the only thing that can turn a view range into block coordinates."""
    out = []
    for seg in entry["segments"]:
        span = interval_of(entry, seg["view"][0], seg["view"][1], view_start, view_end)
        if span is None:
            continue
        lo, hi = span
        shift = seg["block"][0] - seg["view"][0]
        out.append({"start": lo + shift, "end": hi + shift,
                    "sha256": records.sha256_bytes(entry["text"][lo:hi].encode("utf-8"))})
    return out


def cap_text(text, max_bytes):
    """`(text cut to at most max_bytes, whether it was cut)`."""
    if len(text.encode("utf-8")) <= max_bytes:
        return text, False
    return text[:fit_end(text, 0, max_bytes)], True


def context_entry(item, line, role, offset=None):
    """A record no window owns, kept as overlap context. Its cut is accounted like any other: the span it
    leaves out and that span's hash, so an overlap entry never reports a cut nothing names."""
    text, cut = cap_text(item["text"], OVERLAP_ITEM_BYTES)
    entry = {"record_id": f"{line}{item['pointer']}", "line": line, "json_pointer": item["pointer"], "kind": item["kind"],
             "tool": item.get("tool"), "ts": item.get("ts"), "error": bool(item.get("error")), "window_role": role,
             "size": len(item["text"]), "text": text, "segments": [{"view": [0, len(text)], "block": [0, len(text)]}],
             "cut": cut, "owned": False, "offset": offset}
    if cut:
        # the item text IS the block here, so the cut's view coordinates are already the block's; it is kept
        # as a LIST because a context entry can lose this tail and then lose its shown part too, when the
        # side's budget runs out, and both intervals have to survive into the manifest
        entry["cut_spans"] = [{"start": len(text), "end": len(item["text"]),
                               "sha256": records.sha256_bytes(item["text"][len(text):].encode("utf-8"))}]
    return entry


TURN_KINDS = ("human", "assistant")   # design §5.4: a turn is a human or an assistant message


def is_turn(entry):
    """Whether this entry is part of a transcript TURN. A tool call and its result belong to the assistant's
    turn rather than being turns of their own, which is what §5.4 counts when it says five."""
    return entry.get("kind") in TURN_KINDS


def turn_key(entry):
    """The TURN an entry belongs to: the transcript record it came from, and that record's kind.

    One message is one turn however many entries it becomes. Counting entries instead counted every content
    block of a message, and then every span a split made of a block, as a turn of its own - so a five-turn
    overlap could be five fragments of a single assistant message and carry no human turn at all. A record
    line survives both block division and splitting (`slice_entry` copies it into every span), which is what
    makes it the identity to count."""
    return (entry["line"], entry["kind"])


def before_turns(seq, stop, turns):
    """The start of the longest contiguous slice of `seq[:stop]` holding at most `turns` TURNS.

    The slice is contiguous because context that skips the tool traffic between two turns is not the
    conversation that happened; the tool traffic rides along with the turn it belongs to and is not counted
    as one."""
    seen, index = [], stop
    while index > 0:
        entry = seq[index - 1]
        if is_turn(entry):
            key = turn_key(entry)
            if key not in seen:
                if len(seen) == turns:
                    break
                seen.append(key)
        index -= 1
    return index


def after_turns(seq, start, turns):
    """The end of the shortest contiguous slice of `seq[start:]` holding at most `turns` TURNS."""
    seen, index = [], start
    while index < len(seq):
        entry = seq[index]
        if is_turn(entry):
            key = turn_key(entry)
            if key not in seen:
                if len(seen) == turns:
                    break
                seen.append(key)
        index += 1
    return index


def turns_in(entries):
    """How many distinct transcript turns a slice of entries holds."""
    return len({turn_key(e) for e in entries if is_turn(e)})


def eid(entry):
    """The identity of an entry within its transcript: the record, and the span when it was split."""
    span = entry.get("span")
    return entry["record_id"] + (f"#{span['index']}/{span['of']}" if span else "")


def fit_end(text, start, max_bytes):
    """The largest end such that text[start:end] is at most max_bytes in UTF-8, at least start + 1."""
    end = min(len(text), start + max_bytes)
    while end > start + 1:
        size = len(text[start:end].encode("utf-8"))
        if size <= max_bytes:
            break
        end = max(start + 1, start + int((end - start) * max_bytes / size))
        while end > start + 1 and len(text[start:end].encode("utf-8")) > max_bytes:
            end -= 1
    return max(end, start + 1)


def slice_entry(entry, a, b, index, of):
    """The span [a, b) of an entry's view text: its text, the segments inside it re-based, and its place."""
    piece = copy.deepcopy({k: v for k, v in entry.items() if k not in ("text", "segments", "clipped")})
    piece["text"] = entry["text"][a:b]
    piece["segments"] = []
    for seg in entry["segments"]:
        lo, hi = max(seg["view"][0], a), min(seg["view"][1], b)
        if lo < hi:
            shift = seg["block"][0] - seg["view"][0]
            piece["segments"].append({"view": [lo - a, hi - a], "block": [lo + shift, hi + shift]})
    if "clipped" in entry and index == 1:
        piece["clipped"] = copy.deepcopy(entry["clipped"])
    piece["span"] = {"index": index, "of": of}
    return piece


def split_entry(entry, max_bytes):
    """The entry itself when its rendering fits `max_bytes`, else its spans, each of which does."""
    if len(render_entry(entry).encode("utf-8")) <= max_bytes:
        return [entry]
    limit = max_bytes - len(render_entry({**entry, "text": "", "span": {"index": 9999, "of": 9999}}).encode("utf-8"))
    cuts, pos, text = [], 0, entry["text"]
    while pos < len(text):
        end = fit_end(text, pos, limit)
        if end < len(text):
            newline = text.rfind("\n", pos + (end - pos) * 3 // 4, end)
            end = newline + 1 if newline >= 0 else end
        cuts.append((pos, end))
        pos = end
    return [slice_entry(entry, a, b, k, len(cuts)) for k, (a, b) in enumerate(cuts, 1)]


# ---- rendering: what the driver supplies ------------------------------------------------------

def role_label(role):
    return "backlog" if ROLE_BACKLOG.match(role) else role


def normal_stamp(value):
    """A record's timestamp as the view may carry it: parsed, then written back in one normal form - or None.

    A transcript's `timestamp` is a string the host wrote, and this code treated it as a number and copied
    it through to `header_of`, which renders it into the model's window. A string that carries a secret or
    a home path is therefore model-visible metadata, and a field nobody projects is the one place such a
    string can stand. Re-emitting only what `fromisoformat` parsed makes the field a timestamp by
    construction: anything else it held is gone, with no pattern to keep up to date."""
    if not isinstance(value, str):
        return None
    try:
        when = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    when = when if when.tzinfo else when.replace(tzinfo=datetime.timezone.utc)
    return when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def header_of(entry):
    bits = [f"[{eid(entry)}]", entry["kind"] + (f":{entry['tool']}" if entry.get("tool") else ""), entry.get("ts") or "-",
            role_label(entry["window_role"])]
    if entry.get("error"):
        bits.append("ERROR")
    return " ".join(bits)


def render_entry(entry):
    return header_of(entry) + "\n" + entry["text"] + "\n"


def shown_segments(entry, end):
    """The segments of `entry` that the first `end` characters of its view text show, each in the same coordinates."""
    out = []
    for seg in entry["segments"]:
        a, b = seg["view"]
        if a >= end:
            break
        stop = min(b, end)
        out.append({"view": [a, stop], "block": [seg["block"][0], seg["block"][0] + (stop - a)]})
    return out


def overlap_of(entry):
    """An entry as the overlap of its neighbour shows it: cut to OVERLAP_ITEM_BYTES, with its place in the
    sequence and every interval it has lost, in the PROJECTED BLOCK's coordinates, each with its own hash.

    Three things were wrong here at once, and each hid the next. The cut was once a bare `overlap_cut: true`,
    which is not an accounting - a window could drop most of a human turn with nothing naming what went. Then
    it became a single `omitted_span` in the ENTRY's own coordinates, which expansion reads as offsets into
    the block, so for a split span or a clipped record it named characters that were never omitted. And a
    singular field cannot hold what an entry has lost twice: a context entry cut to 700 characters and then
    shown is still missing its tail, and that tail reached no manifest at all, so a session could report
    itself source complete with content nobody had looked at.

    `omitted_intervals` is the one shape, in block coordinates, and it carries BOTH what this cut loses and
    what the entry had already lost."""
    text, cut = cap_text(entry["text"], OVERLAP_ITEM_BYTES)
    # `line` rides along because turn identity is the record's, and a consumer counting turns in a window
    # cannot recover it from a record_id
    # `size` is the record's own length - the full projected block - and it rides along unchanged. A row
    # that substituted a span's end, or the length of a text already capped to 700, reported the head of a
    # clipped result as the size of the record; §5.4 and done-when 4 read this number as the record's size.
    # `json_pointer` and the `segments` of what is shown let a quote of the overlap be located exactly as one of an owned
    # record: the overlap is evidence a reading may cite (an exposure seen before the action, X review of WP-08 r1), while
    # owning it stays with its own window. The cut is a prefix, so the shown segments are the entry's, ended at the cut.
    shown = {"entry": eid(entry), "record_id": entry["record_id"], "line": entry["line"], "json_pointer": entry["json_pointer"],
             "size": entry["size"], "kind": entry["kind"], "tool": entry.get("tool"),
             "ts": entry.get("ts"), "window_role": entry["window_role"], "error": entry.get("error", False),
             "text": text, "segments": shown_segments(entry, len(text)), "overlap_cut": cut or bool(entry.get("cut"))}
    lost = (omitted_intervals(entry, len(text), len(entry["text"])) if cut else []) \
        + list(entry.get("cut_spans", []))
    if lost:
        shown["omitted_intervals"] = lost
    return shown


def overlap_side(entries, budget=OVERLAP_SIDE_BYTES, from_end=False):
    """`(shown, omitted)` for one side's overlap: the turns nearest the window, filled to `budget`.

    A window stays bounded, so a side's overlap has a size. What changes is that the slice is counted in
    turns and that the entries the budget cannot hold are returned rather than silently absent: the caller
    lists them in the window, so every turn of the overlap is either shown or named."""
    ordered = list(reversed(entries)) if from_end else list(entries)
    shown, omitted, spent = [], [], 0
    for entry in ordered:
        rendered = overlap_of(entry)
        cost = len(render_overlap(rendered).encode("utf-8"))
        if spent + cost > budget and shown:
            # A turn the budget cannot hold is OMITTED, and an omission with no span and no hash is not an
            # accounting - it names a record and says nothing about what was in it. The whole text goes, so
            # the span is the whole text and the hash is the whole text's.
            omitted.append({"entry": eid(entry), "record_id": entry["record_id"], "line": entry["line"],
                            "kind": entry["kind"], "size": entry["size"], "reason": "overlap_budget",
                            # the whole of what this entry shows goes, in block coordinates, and so does
                            # anything it had already lost
                            "omitted_intervals": (omitted_intervals(entry, 0, len(entry["text"]))
                                                  + list(entry.get("cut_spans", [])))})
            continue
        spent += cost
        shown.append(rendered)
    if from_end:
        shown.reverse()
        omitted.reverse()
    return shown, omitted


def render_overlap(entry):
    return (header_of({**entry, "record_id": entry["entry"]}) + " (overlap)\n" + entry["text"]
            + ("\n[... cut ...]" if entry["overlap_cut"] else "") + "\n")


def render_window(window):
    """The window as the driver puts it into a packet: this text's UTF-8 bytes are the window's part of
    `driver_bytes`.

    The version is checked HERE as well, because this is the last boundary before a model sees the text and
    it takes a window object from any caller - a stale one rendered straight into a packet is exactly the
    text a newer masking exists to withhold, and the checked readers above cannot help a caller that did
    not use them."""
    current_version(window, f"window {window.get('window_n')} of {window.get('transcript')}")
    out = [f"WINDOW {window['window_n']} of {window['transcript']} version {window['version']} "
           f"sha256:{window['version_sha'][:12]} redaction {window['redaction_version']}"]
    if window["overlap"]["prev"]:
        out.append("--- overlap before: context, not owned by this window ---")
        out.extend(render_overlap(e) for e in window["overlap"]["prev"])
    out.append("--- records owned by this window ---")
    out.extend(render_entry(e) for e in window["records"])
    if window["overlap"]["next"]:
        out.append("--- overlap after: context, not owned by this window ---")
        out.extend(render_overlap(e) for e in window["overlap"]["next"])
    return "\n".join(out) + "\n"


def manifest_of(entries):
    return [{"record_id": e["record_id"], "line": e["line"], "size": e["size"],
             "omitted_span": e["clipped"]["omitted_span"], "error_lines": len(e["clipped"]["error_lines"]),
             "forced_by": e["clipped"]["forced_by"], "locator": {"offset": e["clipped"]["offset"]},
             "origin": "owned", "window_role": e["window_role"],
             "omission_id": omission_id(e["record_id"], e["clipped"]["omitted_span"]["start"],
                                        e["clipped"]["omitted_span"]["end"])}
            for e in entries if "clipped" in e]


def span_map_of(entries):
    return [{"record_id": e["record_id"], **e["span"], "segments": e["segments"]} for e in entries if "span" in e]


def overlap_manifest(window, seq):
    """The overlap's omissions as manifest rows - ONE ROW PER INTERVAL, so the one list a consumer reads
    covers them too.

    An overlap omission was accounted nowhere. A turn the budget could not hold was named in
    `overlap.omitted` and a turn cut to `OVERLAP_ITEM_BYTES` carried its cut, but neither entered
    `omission_manifest`, so §5.4's expansion could not reach them (`EXPANSION_UNKNOWN`) and completeness
    counted a view whole while part of its context was gone. One row per interval, because a row per RECORD
    kept the first interval and dropped the rest, and because a decision about one interval is not a
    decision about another. Rows carry `origin: "overlap"` - the record is context here rather than owned -
    and the locator is the entry's own, which every entry now has."""
    located = {e["record_id"]: e.get("offset") for e in seq}
    rows, seen = [], set()
    for side in ("prev", "next"):
        for shown in list(window["overlap"][side]) + list(window["overlap"]["omitted"][side]):
            for span in shown.get("omitted_intervals") or []:
                ident = omission_id(shown["record_id"], span["start"], span["end"])
                if ident in seen:
                    continue   # the same interval named twice in one window is one omission
                seen.add(ident)
                rows.append({"record_id": shown["record_id"], "line": shown["line"],
                             "size": shown["size"], "omitted_span": span,
                             "omission_id": ident, "error_lines": 0, "forced_by": "none",
                             "locator": {"offset": located.get(shown["record_id"])},
                             "origin": "overlap", "window_role": shown.get("window_role", "context")})
    return rows


def make_window(base, number, seq, i, j, limits, overlap=True):
    owned = [{k: v for k, v in e.items() if k != "owned"} for e in seq[i:j]]
    prev, prev_out, following, next_out = [], [], [], []
    if overlap:
        prev, prev_out = overlap_side(seq[before_turns(seq, i, OVERLAP_TURNS):i], from_end=True)
        following, next_out = overlap_side(seq[j:after_turns(seq, j, OVERLAP_TURNS)])
    window = {**base, "window_n": number, "records": owned,
              "overlap": {"prev": prev, "next": following, "omitted": {"prev": prev_out, "next": next_out}},
              "span_map": span_map_of(owned), "omission_manifest": manifest_of(owned), "host_allowance": limits["allowance"]}
    window["omission_manifest"] = window["omission_manifest"] + overlap_manifest(window, seq)
    window["driver_bytes"] = limits["overhead"] + len(render_window(window).encode("utf-8"))
    window["bound_ok"] = not bound.check_bound(window["driver_bytes"], limits)
    return window


def cut_windows(base, seq, limits, overlap=True):
    """Windows over `seq` (entries in record order; `owned` marks the ones to cut, the others are overlap context).

    Each owned entry lands in exactly one window; one too large to fit is split into spans first. A window ends
    where the next entry would push its driver bytes past the bound, and never spans a context entry."""
    budget = bound.driver_budget(limits) - limits["overhead"]
    ceiling = budget - HEADER_SLACK - (2 * OVERLAP_TURNS * (OVERLAP_ITEM_BYTES + OVERLAP_SLACK) if overlap else 0)
    if ceiling < MIN_ENTRY_BYTES:
        raise Refused(f"WINDOW_UNBOUNDED: {budget} bytes remain for a window after the packet's {limits['overhead']} and the "
                      f"allowance, and the heading and overlap need {budget - ceiling}; no entry of {MIN_ENTRY_BYTES} bytes fits")
    cutting = []
    for entry in seq:
        cutting.extend(split_entry(entry, ceiling) if entry["owned"] else [entry])
    own = [len(render_entry(e).encode("utf-8")) if e["owned"] else 0 for e in cutting]
    ctx = [len(render_overlap(overlap_of(e)).encode("utf-8")) for e in cutting]
    windows, i, n = [], 0, len(cutting)
    while i < n:
        if not cutting[i]["owned"]:
            i += 1
            continue
        before = sum(ctx[max(0, i - OVERLAP_TURNS):i]) if overlap else 0
        j, total = i, HEADER_SLACK + before
        while j < n and cutting[j]["owned"]:
            after = sum(ctx[j + 1:j + 1 + OVERLAP_TURNS]) if overlap else 0
            if j > i and total + own[j] + after > budget:
                break
            total += own[j]
            j += 1
        window = make_window(base, len(windows) + 1, cutting, i, j, limits, overlap)
        while not window["bound_ok"] and j > i + 1:  # the estimate was loose: shrink by the real bytes
            j -= 1
            window = make_window(base, len(windows) + 1, cutting, i, j, limits, overlap)
        if not window["bound_ok"]:
            raise Refused(f"WINDOW_UNBOUNDED: one entry ({eid(cutting[i])}) cannot be placed in a window within the bound: "
                          + "; ".join(bound.check_bound(window["driver_bytes"], limits)))
        windows.append(window)
        i = j
    return windows, [{"id": eid(e), "owned": e["owned"], "line": e["line"], "kind": e["kind"]} for e in cutting]


# ---- checks over a cut view -------------------------------------------------------------------

def error_lines_of(text, head=HEAD_CHARS, tail=TAIL_CHARS):
    """The error lines of a tool result's middle, as the clipper reads them (ranges in the block)."""
    out, offset, n = [], 0, len(text)
    for line in text.splitlines(keepends=True):
        a, b = offset, offset + len(line)
        offset = b
        if b > head and a < n - tail and ERROR_LINE.search(line):
            out.append([a, b])
    return out


def check_windows(sequence, windows):
    """Violations of the window invariants: every owned entry in exactly one window (SET_MISMATCH), and each window's
    overlap the entries the sequence puts around it (OVERLAP_MISSING)."""
    errors = []
    seen = [eid(r) for w in windows for r in w["records"]]
    errors += records.observe_set(records.expect_set(s["id"] for s in sequence if s["owned"]),
                                  [{"id": i, "outcome": "retained"} for i in seen])
    rows = list(sequence)
    order = [s["id"] for s in rows]
    place = {i: k for k, i in enumerate(order)}
    for w in windows:
        ids = [eid(r) for r in w["records"]]
        if not ids or any(i not in place for i in ids):
            errors.append(f"SET_MISMATCH window {w['window_n']}: it holds no record, or one the sequence does not have")
            continue
        first, last = min(place[i] for i in ids), max(place[i] for i in ids)
        # the overlap is counted in TURNS, and every turn of the slice is either shown or named as omitted
        for side, want in (("prev", order[before_turns(rows, first, OVERLAP_TURNS):first]),
                           ("next", order[last + 1:after_turns(rows, last + 1, OVERLAP_TURNS)])):
            have = [e["entry"] for e in w["overlap"][side]]
            named = [e["entry"] for e in w["overlap"].get("omitted", {}).get(side, [])]
            # a list is not a set: an entry listed twice in one side's shown or omitted list was counted as
            # one by every check here, so a window could show the same turn twice, or name one omitted twice,
            # and the accounting still balanced
            for which, listed in (("shown", have), ("omitted", named)):
                twice = sorted({i for i in listed if listed.count(i) > 1})
                if twice:
                    errors.append(f"OVERLAP_MISSING window {w['window_n']} ({side}): {twice} appears more than "
                                  f"once in the {which} list, so one turn is accounted as several")
            # membership next: every entry of the turn slice is either shown or named omitted
            if set(have) | set(named) != set(want):
                errors.append(f"OVERLAP_MISSING window {w['window_n']} ({side}): it holds {have} and names {named} "
                              f"omitted, the sequence puts {want} there")
            # ... and then the two must not overlap: an entry counted on both sides is accounted by neither
            if set(have) & set(named):
                errors.append(f"OVERLAP_MISSING window {w['window_n']} ({side}): {sorted(set(have) & set(named))} "
                              f"is both shown and named omitted, so it is accounted twice and verified once")
    return errors


def check_tiling(windows, texts=None):
    """Violations of the span mapping: for each record, the shown stretches and the gaps tile the block exactly (a message
    split into spans has the message as their union), and, given the projected text of each record (`texts`), every
    error line of a clipped result is within the shown stretches."""
    errors, by_record = [], collections.defaultdict(list)
    for w in windows:
        for r in w["records"]:
            by_record[r["record_id"]].append(r)
    for record_id, parts in sorted(by_record.items()):
        pieces = [list(s["block"]) for p in parts for s in p["segments"]]
        gaps = [g for p in parts if "clipped" in p for g in p["clipped"]["gaps"]]
        if coverage.normalize(pieces + gaps) != [[0, parts[0]["size"]]] or sum(b - a for a, b in pieces + gaps) != parts[0]["size"]:
            errors.append(f"SPAN_UNION_MISMATCH {record_id}: its shown stretches and gaps do not tile its {parts[0]['size']} characters exactly")
        if texts and record_id in texts:
            shown = coverage.normalize(pieces)
            for a, b in error_lines_of(texts[record_id]):
                if coverage.subtract([[a, b]], shown):
                    errors.append(f"ERROR_LINE_DROPPED {record_id}: the error line at {a}-{b} is not kept whole")
    return errors


# ---- the forcing, the decisions, the completeness ---------------------------------------------

def forced_records(clipped, human_lines, pending_first_records=(), search_hits=()):
    """`{record_id: forced_by}` of the clipped records that may not be skipped (design §5.4): every one between a
    pending event and the next human turn, and every one the full-source search matched. `clipped` is
    `[{record_id, line}]`; `human_lines` the 0-based record indexes of the human turns; a pending event is its first
    record's index; `search_hits` the record ids the search matched."""
    humans, forced, matched = sorted(human_lines), {}, set(search_hits)
    for item in clipped:
        index = item["line"] - 1
        for first in pending_first_records:
            k = bisect.bisect_right(humans, first)
            if index >= first and (k == len(humans) or index < humans[k]):
                forced[item["record_id"]] = "pending_event"
        if item["record_id"] not in forced and item["record_id"] in matched:
            forced[item["record_id"]] = "search_match"
    return forced


def forced_omissions(rows, forced):
    """`forced` carried over to the OMISSION ids of `rows`: a forced record forces every interval it lost.

    Forcing is a fact about a record - the search matched it, a pending event covers it - while a decision
    is about one interval. Without this carry, a skip of a forced record's interval matched nothing in
    `forced` and the refusal that exists to stop exactly that never fired."""
    return {row["omission_id"]: forced[row["record_id"]] for row in rows if row["record_id"] in forced}


def check_decisions(manifest_ids, forced, decisions):
    """Violations of S3's expand/skip answers over a window's omission manifest: one decision for each omitted
    INTERVAL (SET_MISMATCH otherwise), a reason for each, and a forced record never skipped (EXPANSION_SKIPPED).

    `manifest_ids` may be the manifest's rows or their ids; `forced` may be keyed by record or by omission, and
    rows let the two be reconciled."""
    errors = []
    rows = [m for m in manifest_ids if isinstance(m, dict)]
    manifest_ids = [m["omission_id"] if isinstance(m, dict) else m for m in manifest_ids]
    forced = {**forced, **forced_omissions(rows, forced)}
    ids = [decision_key(d) for d in decisions]
    missing, extra = sorted(set(manifest_ids) - set(ids)), sorted(set(ids) - set(manifest_ids))
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if missing or extra or repeated:
        errors.append(f"SET_MISMATCH omission manifest: missing={missing} extra={extra} repeated={repeated}")
    for d in decisions:
        if d.get("decision") not in DECISIONS or not str(d.get("reason") or "").strip():
            errors.append(f"EXPANSION_DECISION_INVALID {d.get('record_id')}: a decision is expand or skip, with a reason")
        # one refusal, one branch. `forced` carries both keys - the record's and, through the carry above,
        # each of its omissions - so a decision that names either is caught here; two branches for one
        # refusal is how one of them stops being exercised.
        elif d["decision"] == "skip" and decision_key(d) in forced:
            errors.append(f"EXPANSION_SKIPPED {decision_key(d)}: forced by {forced[decision_key(d)]}, so it "
                          "must be expanded")
    return errors


def unresolved_versions(backlog, version):
    """The work this stage did NOT resolve: the backlog of versions other than the one it viewed.

    S2 views one version of a transcript, and a session whose earlier versions still hold unread ranges has
    content nobody has looked at. This was a count (`backlog_other_versions`) that no consumer read, which
    is an inert field: it recorded the shortfall and bound nothing. It is a state now, and
    `completeness` enforces it - a session with unresolved versions is not source complete, so no claim of
    absence can rest on it until the work is done or the ranges are deliberately closed."""
    return [{"version": b["version"], "window": b["window"], "unread": b["unread"]}
            for b in sorted(backlog, key=lambda b: b["version"]) if b["version"] != version]


def decision_key(decision):
    """The omission a decision is about: its `omission_id`, or - for a caller that still speaks in records -
    its record id. Accounting is by INTERVAL, and a record id answers for every interval of its record."""
    return decision.get("omission_id") or decision.get("record_id")


def completeness(windows_ok, omission_ids, decisions, expanded_ok, unresolved=()):
    """`{view_complete, source_complete, skipped, unresolved}` of one session: view complete when every window passed
    the gate and every OMITTED INTERVAL has an executed expansion (`expanded_ok`: the ids whose expansion windows
    passed) or a recorded skip; source complete when, in addition, nothing was skipped and no other version is
    unresolved. The skipped omissions are listed, and so are the unresolved versions.

    The identity is the interval, not the record. Keyed by record, one expansion of a record that had lost
    three intervals discharged all three, and a session with content nobody had looked at reported itself
    source complete - the strongest basis a claim of absence can rest on."""
    chosen = {decision_key(d): d["decision"] for d in decisions}
    clipped_ids = omission_ids
    skipped = sorted(i for i in clipped_ids if chosen.get(i) == "skip")
    held = [u["version"] for u in unresolved]
    view = bool(windows_ok) and all(windows_ok) and all(
        chosen.get(i) == "skip" or (chosen.get(i) == "expand" and i in expanded_ok) for i in clipped_ids)
    return {"view_complete": view, "source_complete": view and not skipped and not held,
            "skipped": skipped, "unresolved_versions": held}


INCOMPLETE_STATUSES = ("unreadable", "known_absent", "unknown_provenance", "read_partial", "failed", "deferred")


def coverage_basis(scope):
    """`incomplete`, `view` or `source` for a claim's scope (design §5.4), checked in that order. `scope` is
    `{sources: [{accounted, directory_present}], sessions: [{status, unprocessed, view_complete, source_complete}]}`."""
    if any(not s["accounted"] or not s["directory_present"] for s in scope["sources"]):
        return "incomplete"
    for session in scope["sessions"]:
        if session["status"] in INCOMPLETE_STATUSES or session.get("unprocessed"):
            return "incomplete"
    # A session that is not even view complete is a hole, and the predicate used to FALL THROUGH it to
    # `source` - the strongest basis - because only the `view and not source` case was named. The mutation
    # M#10 asks for (losing the recorded skip) lands exactly here: it made the session incomplete and the
    # basis answered "source", so absence would have been claimable on work nobody finished.
    if any(not s["view_complete"] for s in scope["sessions"]):
        return "incomplete"
    if any(s["view_complete"] and not s["source_complete"] for s in scope["sessions"]):
        return "view"
    return "source"


def absence_claim_allowed(basis):
    """A claim of absence needs basis `source`; anything less leaves it `pending` (design §5.4)."""
    return basis == "source"


# ---- the immutable copy and the projection ---------------------------------------------------

class RangeSet:
    def __init__(self, ranges):
        self.ranges = coverage.normalize(ranges)
        self.starts = [r[0] for r in self.ranges]

    def __contains__(self, index):
        k = bisect.bisect_right(self.starts, index) - 1
        return k >= 0 and index < self.ranges[k][1]


def safe_name(identity):
    return re.sub(r"[^A-Za-z0-9._-]", "_", identity)


def copy_version(run_dir, path, zstd, version=None):
    """The immutable, hash-named copy of one transcript version: `(run-relative path, sha256)`.

    The version is the census's (D-20261103-8facee): `{sha, record_count}`, the transcript's first `record_count`
    complete lines as S1 read them. Exactly those lines are copied, decompressed, and they must hash to `sha`; what
    the host appended after the census - more lines, or a line it is still writing - is the next run's, and is not
    copied. Fewer complete lines than the census read, or other bytes in them, means the transcript was rewritten or
    truncated: SOURCE_CHANGED. Without a version every complete line is copied."""
    directory = stagelock.confine(run_dir, pathlib.Path(run_dir) / "sources")
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".copy.")
    digest, lines = hashlib.sha256(), 0
    count = version["record_count"] if version else None
    try:
        with os.fdopen(fd, "wb") as out, contextlib.closing(sources.read_lines(path, zstd, limit=count)) as read:
            for raw in read:
                if not raw.endswith(b"\n"):
                    break  # a record the host is still writing is no record yet
                out.write(raw)
                digest.update(raw)
                lines += 1
        sha = digest.hexdigest()
        if version and (lines < count or sha != version["sha"]):
            raise Refused(f"SOURCE_CHANGED {path}: its first {lines} complete lines hash {sha[:12]}, the census read {count} "
                          f"hashing {version['sha'][:12]}; the transcript was rewritten or truncated after the census, so S1 "
                          "must be run again")
        target = directory / f"{sha}.jsonl"
        if target.exists():
            if records.sha256_file(target) != sha:
                raise Refused(f"SOURCE_TAMPERED {target}: an existing copy does not hash to its name")
            os.unlink(tmp)
        else:
            os.chmod(tmp, 0o444)
            os.replace(tmp, target)
    except sources.Unreadable as exc:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise Refused(f"SOURCE_UNREADABLE {path}: {exc}") from exc
    except BaseException:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise
    return f"sources/{sha}.jsonl", sha


def project_version(run_dir, copy_rel, host, child, version, dest_rel):
    """Write the projection of every content block of the complete lines of a copy; returns the counts."""
    dest = stagelock.confine(run_dir, pathlib.Path(run_dir) / dest_rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".projection.")
    count = items = 0
    # M#8: how many blocks the backstop replaced, by detector, for THIS projection. A blanked block is a
    # block the mapping could not cover, so the count is the one number that says how often that happened -
    # and a figure nobody records is a figure nobody can act on. Taken as a difference, because the counter
    # is process-wide and a run is not the process.
    blanked_before = collections.Counter(projection.BLANKED)
    blocks_before = collections.Counter(projection.BLOCKS)
    try:
        with open(pathlib.Path(run_dir) / copy_rel, "rb") as src, os.fdopen(fd, "wb") as out:
            for raw in src:
                if not raw.endswith(b"\n"):
                    break  # a record the host was still writing is not a record yet
                count += 1
                try:
                    rec = json.loads(raw)
                except ValueError:
                    continue
                # Every transcript-derived string that reaches a window goes through the projection, and the
                # tool name is one: `header_of` renders it into the model's window, so a tool whose name
                # carried a secret pattern stood unmasked there however well its arguments were masked.
                # `kind` and the window role are this code's own words, and the timestamp is a number.
                blocks = [{"pointer": p, "kind": k, "tool": projection.project(t, version) if t else t,
                           "error": e, "text": projection.project(v, version)}
                          for p, k, t, e, v in record_items(host, rec, child) if v is not None]
                blocks = [b for b in blocks if b["text"].strip() or b["kind"] == "tool_call"]  # a call with no arguments still names its tool
                if blocks:
                    items += len(blocks)
                    out.write(json.dumps({"line": count, "ts": normal_stamp(rec.get("timestamp")),
                                          "items": blocks}, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
        os.replace(tmp, dest)
    except BaseException:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise
    # Two figures, because they answer two questions: how many CONTENT BLOCKS the backstop replaced, which
    # is what a reader of the run wants, and how many blanking operations ran - a structured block's leaves
    # each pass the exit, so one block with four masked leaves is four operations and one block.
    blanked = {reason: projection.BLOCKS[reason] - blocks_before[reason]
               for reason in projection.BLOCKS if projection.BLOCKS[reason] > blocks_before[reason]}
    operations = {reason: projection.BLANKED[reason] - blanked_before[reason]
                  for reason in projection.BLANKED if projection.BLANKED[reason] > blanked_before[reason]}
    return {"records": count, "items": items, "blanked": blanked, "blank_operations": operations}


def read_projection(path):
    """`(offset, record)` for each line of a projection file, in order."""
    with open(path, "rb") as handle:
        while True:
            offset = handle.tell()
            raw = handle.readline()
            if not raw:
                return
            yield offset, json.loads(raw)


def build_sequence(proj_path, viewed, role_of, index):
    """The sequence of one version: `(entries, human_lines, counts, tools, texts)`. The entries are the viewed blocks
    (owned), each with its view form, and up to OVERLAP_TURNS blocks of context each side of every run of them. `index`
    takes the full projected text of each viewed block, and `texts` keeps it for the checks that need the block and not
    the view. `counts` and `tools` are the shape counts `digest.py` kept, over every block of the version rather than
    the viewed ones: they are hints for ranking what to read, never evidence (design §5.5: evidence is a locator)."""
    # Context is retained by TURNS, not by blocks. A deque of five BLOCKS was five of whatever came last, so
    # six tool results standing between the window and the previous human turn pushed every turn out of it and
    # the window opened on tool traffic alone - the very case §5.4's five turns is for. `recent` is trimmed by
    # `before_turns`, which is the same counting the overlap itself uses, and `after_keys` closes the trailing
    # side once five distinct turns have gone by.
    seq, recent, humans, counts = [], [], [], collections.Counter()
    after_open, after_keys = False, []
    texts, tools = {}, collections.Counter()
    for offset, rec in read_projection(proj_path):
        line = rec["line"]
        for block in rec["items"]:
            item = {**block, "ts": rec.get("ts")}
            counts["items"] += 1
            counts[item["kind"]] += 1
            if item["kind"] == "tool_call" and item.get("tool"):
                tools[item["tool"]] += 1
            if item["kind"] == "tool_result" and item.get("error"):
                counts["error_results"] += 1
            if item["kind"] == "human":
                humans.append(line - 1)
            # Indexed whatever window owns it, or none. The search is over the full redacted text of the
            # version (§5.4's "full-source search"), and it decides which clipped records must be expanded:
            # an index built only from the work ranges cannot match anything outside them, so a search
            # that found nothing there was reporting its own blind spot as an answer.
            index.add([line, item["pointer"]], item["text"])
            texts[f"{line}{item['pointer']}"] = item["text"]
            if (line - 1) in viewed:
                counts["viewed"] += 1
                seq.extend(recent)
                recent = []
                seq.append(make_entry(item, line, role_of(line - 1), offset))
                after_open, after_keys = True, []
                continue
            entry = context_entry(item, line, "context", offset)
            if after_open:
                if is_turn(entry):
                    key = turn_key(entry)
                    if key not in after_keys:
                        if len(after_keys) == OVERLAP_TURNS:
                            after_open = False
                        else:
                            after_keys.append(key)
                if after_open:
                    seq.append(entry)
                    continue
            recent.append(entry)
            recent = recent[before_turns(recent, len(recent), OVERLAP_TURNS):]
    return seq, humans, counts, tools, texts


def hints_of(counts, tools):
    """The shape of a transcript, as `digest.py` counted it: what to read first, never what was said. A hint is not
    evidence and no claim rests on one."""
    return {"human_turns": counts["human"], "assistant_turns": counts["assistant"], "delegated_turns": counts["delegated"],
            "tool_calls": counts["tool_call"], "tool_results": counts["tool_result"],
            "error_results": counts["error_results"], "tools": dict(tools.most_common(15))}


def projection_texts(run_dir, redacted_rel):
    """`{record_id: the block's full projected text}` of one version - the text the full-source search decides on,
    clipped spans included, read back from the projection rather than from any window."""
    texts = {}
    for _offset, rec in read_projection(pathlib.Path(run_dir) / redacted_rel):
        for block in rec["items"]:
            texts[f"{rec['line']}{block['pointer']}"] = block["text"]
    return texts


def forced_by_search(run_dir, name, terms):
    """`{record_id: "search_match"}` for the clipped records of one view that the full-source search matches
    (design §5.4). The index narrows and the projection decides; a term that matches nothing forces nothing,
    and closes nothing either - the caller keeps it as such."""
    run_dir = pathlib.Path(run_dir)
    doc = sequence_doc(run_dir, name)
    texts = projection_texts(run_dir, doc["redacted"])
    clipped = {m["record_id"] for path in sorted((run_dir / "views" / name).glob("[0-9]*.json"))
               for m in window_doc(run_dir, name, path)["omission_manifest"]}
    index = search.load(run_dir / "index" / "bm25" / f"{name}.json")
    hits = search.search(index, terms, lambda ref: texts.get(f"{ref[0]}{ref[1]}", ""))
    return {rid: "search_match" for rid in (f"{h['ref'][0]}{h['ref'][1]}" for h in hits) if rid in clipped}


def role_fn(owned, backlog, version):
    """The window role of a record index (design §5.2): `in_window`, `backlog(<window>)` or `context`."""
    mine, held = RangeSet(owned), [(RangeSet(b["unread"]), b["window"]) for b in backlog if b["version"] == version]

    def role(index):
        if index in mine:
            return "in_window"
        for ranges, window in held:
            if index in ranges:
                return f"backlog({window})"
        return "context"
    return role


# ---- the stage -------------------------------------------------------------------------------

def index_destination(run_dir, rel):
    """The confined path to write an index to, with its parent made.

    The order is the whole of it: `mkdir(parents=True)` on an unconfined path follows a symlinked `index/`
    and creates `bm25/` inside whatever it points at, so a refusal that arrives afterwards arrives with a
    directory already made outside the run. Confinement first means nothing is created on the way to it."""
    destination = stagelock.confine(run_dir, pathlib.Path(run_dir) / rel)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def limits_refusal(golden_run):
    """The refusal `limits_of` gives for a declaration with no allowance, as a list of lines - so a control
    can read both stages' words for one stop side by side."""
    try:
        limits_of({"seats": {"S3": golden_run["seat"]}, "host_allowance": {}, "output_caps": {"S3": 32_000}})
    except Refused as exc:
        return str(exc).splitlines()
    return []


def census_version(file):
    """`{sha, record_count}` of the version S1 read of one transcript file (`census.segments_of`): the census's sha and
    the record count of the version its work names, both from the census. Not from the run's coverage state: a targeted
    run's state is the periodic base, which never holds what the census observed (review c0fix r1 #3). A file the census
    did not read has no version to copy, and is refused by name."""
    number, versions = file["work"]["version"], file.get("versions") or []
    if not file.get("sha256") or number is None or not 0 <= number < len(versions):
        raise Refused(f"VERSION_MISMATCH {file['key']}: the census holds no version of it to copy")
    return {"sha": file["sha256"], "record_count": versions[number]["record_count"]}


def view_transcript(run_dir, entry, file, state, ctx, unit=None):
    """Everything S2 leaves for one transcript file of a unit - `entry` its census row, `file` one of the row's files
    (`census.segments_of`), `unit` its root's identity; returns its line of `views.json`. A member's work is the census's,
    like a root's: S1 read every member of an eligible unit (D-20261103-85f3e8). Each file of a Codex thread written
    across several is a transcript of its own here, named by its coverage key (D-20261103-a7128a)."""
    run_dir = pathlib.Path(run_dir)
    ident = file["key"]
    child = entry["status"] == "child_of"
    rv, limits, zstd = ctx["redaction_version"], ctx["limits"], ctx["zstd"]
    copy_rel, sha = copy_version(run_dir, file["path"], zstd, census_version(file))
    name = safe_name(ident)
    proj_rel = f"redacted/{sha}.{rv}.jsonl"
    stats = project_version(run_dir, copy_rel, entry["host"], child, rv, proj_rel)
    work = file["work"]
    version, owned, backlog = work["version"], file["owned"], work["backlog"]
    viewed_ranges = coverage.union(work["in_window"], [r for b in backlog if b["version"] == version for r in b["unread"]])
    viewed, role_of = RangeSet(viewed_ranges), role_fn(owned, backlog, version)
    index = search.Index(sha, rv)
    seq, humans, counts, tools, texts = build_sequence(run_dir / proj_rel, viewed, role_of, index)
    pending = sorted(e["first_record"] for e in state["pending_events"] if e["transcript"] == ident and e["version"] == version)
    clipped = [e for e in seq if "clipped" in e]
    forced = forced_records([{"record_id": e["record_id"], "line": e["line"]} for e in clipped], humans, pending)
    for e in clipped:
        e["clipped"]["forced_by"] = forced.get(e["record_id"], "none")
    base = {"transcript": ident, "version": version, "version_sha": sha, "redaction_version": rv}
    windows, sequence = cut_windows(base, seq, limits)
    errors = check_windows(sequence, windows) + check_tiling(windows, texts)
    if errors:
        raise Refused("\n".join(errors[:5]))
    files = []
    for w in windows:
        rel = f"views/{name}/{w['window_n']}.json"
        records.write_json(run_dir, run_dir / rel, w)
        files.append({"path": rel, "sha256": records.sha256_file(run_dir / rel), "driver_bytes": w["driver_bytes"],
                      "records": len(w["records"]),
                      # the two kinds of omission are counted apart: a clipped OWNED record is work S3 must
                      # decide about this window's own records, an overlap omission is context the budget
                      # could not hold. One number over both says neither thing.
                      "clipped": sum(1 for m in w["omission_manifest"] if m["origin"] == "owned"),
                      "overlap_omissions": sum(1 for m in w["omission_manifest"] if m["origin"] == "overlap")})
    sequence_rel = f"views/{name}/sequence.json"
    records.write_json(run_dir, run_dir / sequence_rel, {
        **base, "source_copy": copy_rel, "redacted": proj_rel, "limits": limits, "sequence": sequence, "human_lines": humans,
        "pending_first_records": pending, "windows": len(windows)})
    index_rel = f"index/bm25/{name}.json"
    search.dump(index, index_destination(run_dir, index_rel))
    return {"transcript": ident, "session": census.key_of(entry), "segment": file["stem"], "name": name, "host": entry["host"],
            "kind": "child" if child else "session", "parent": entry.get("parent"), "unit": unit or census.key_of(entry),
            "version": version, "version_sha": sha, "source_copy": copy_rel, "redacted": proj_rel, "sequence": sequence_rel,
            "index": index_rel, "records": stats["records"], "items": counts["items"], "viewed_items": counts["viewed"],
            "windows": files, "clipped": len(clipped), "forced": sum(1 for v in forced.values() if v != "none"),
            "hints": hints_of(counts, tools), "unresolved_versions": unresolved_versions(backlog, version),
            "blanked": stats["blanked"], "blank_operations": stats["blank_operations"],
            "source_bytes": (run_dir / copy_rel).stat().st_size}


def run(run_dir, overhead=bound.PACKET_OVERHEAD, seats_path=None):
    """`distill.py views`: S2 over the census and the coverage state S1 left in the run directory."""
    run_dir = pathlib.Path(run_dir)
    try:
        transcripts = census.rows(census.load(run_dir))
    except ValueError as exc:
        raise Refused(f"INPUT_INVALID S1: {run_dir}/census.json: {exc}") from exc
    state = coverage.load(run_dir / "coverage.json")[0]
    # The unit is a root with every member at any depth (D-20261103-85f3e8). Of an eligible unit S2 reads each transcript
    # that owes the window something - the root or a member, its records in the window or its backlog - and no other: a
    # member with nothing to read would cut no window. An eligible root whose unit owes nothing contradicts S1.
    by_id = {census.key_of(e): e for e in transcripts}
    units = census.units(transcripts)
    owes = lambda f: bool(f["path"] and (f["work"]["in_window"] or f["work"]["backlog"]))  # noqa: E731
    todo, idle = [], []
    for root in (e for e in transcripts if e["status"] == "eligible"):
        unit = census.key_of(root)
        read = [(e, f, unit) for e in [root] + [by_id[m] for m in units.get(unit, [])] if e is root or e["status"] == "child_of"
                for f in census.segments_of(e) if owes(f)]
        todo += read
        if not read:
            idle.append(unit)
    if idle:
        raise Refused(f"SET_MISMATCH S2: eligible sessions whose unit owes the window nothing: {sorted(idle)}")
    names = collections.Counter(safe_name(f["key"]) for _e, f, _unit in todo)
    clash = sorted(n for n, c in names.items() if c > 1)
    if clash:
        raise Refused(f"VIEW_NAME_COLLISION: {clash} name more than one transcript")
    done = {}
    with records.run_stage(run_dir, "S2", [{"artifact": "census.json", "producer_stage": "S1"},
                                           {"artifact": "coverage.json", "producer_stage": "S1"}],
                           part="views") as stage:
        # the limits are the declaration this stage was admitted against: a read made before admission could be
        # overtaken by an amendment of the cap, and the windows would be cut at a cap the record does not name (X r1)
        declaration = stage.declaration
        limits = limits_of(declaration, overhead, seats_path)
        _, _, window_id = coverage.window_bounds(declaration["window"])
        ctx = {"limits": limits, "redaction_version": projection.CURRENT, "zstd": sources.declared(declaration).get("zstd"),
               "window_bounds": coverage.window_bounds(declaration["window"])[:2]}

        def work(item):
            done[item["id"]] = view_transcript(run_dir, item["entry"], item["file"], state, ctx, item["unit"])

        # a unit fails together: under the production posture a failing file quarantines its root and every other
        # file of the unit with it, because they share the unit (records.run_items)
        items = [{"id": f["key"], "unit": unit, "entry": e, "file": f} for e, f, unit in todo]
        outcome = stage.run_items(items, work)
        # the views published are the ones the stage still holds done: a file whose view was made before another file of
        # its unit failed went to the quarantine with the unit, and its view goes with it (review c0fix r1 #4)
        owed, published = {f["key"] for _e, f, _unit in todo}, set(outcome["done"])
        missing = sorted(owed - published - {q["id"] for q in outcome["quarantined"]})
        if missing:
            raise Refused(f"SET_MISMATCH S2: transcripts that owe the window something without a view: {missing}")
        manifest = {"window": window_id, "redaction_version": projection.CURRENT, "limits": limits,
                    "quarantined": outcome["quarantined"], "transcripts": [done[i] for i in sorted(published)]}
        manifest["totals"] = totals_of(manifest["transcripts"])
        records.write_json(run_dir, run_dir / "views.json", manifest)
        stage.output("views.json")
    return manifest


def totals_of(transcripts):
    """The manifest's totals. A line of the manifest is one file's view, and a Codex thread written in several files has a
    line for each (D-20261103-a7128a), so `files` counts the lines and `sessions` and `children` the distinct sessions
    they belong to (review c0fix r2)."""
    drivers = [w["driver_bytes"] for t in transcripts for w in t["windows"]]
    return {"files": len(transcripts), "sessions": len({t["session"] for t in transcripts if t["kind"] == "session"}),
            "children": len({t["session"] for t in transcripts if t["kind"] == "child"}), "windows": len(drivers),
            "driver_bytes": sum(drivers), "max_driver_bytes": max(drivers, default=0),
            "records": sum(t["records"] for t in transcripts), "items": sum(t["items"] for t in transcripts),
            "viewed_items": sum(t["viewed_items"] for t in transcripts), "clipped": sum(t["clipped"] for t in transcripts),
            "forced": sum(t["forced"] for t in transcripts), "source_bytes": sum(t["source_bytes"] for t in transcripts),
            # the work S2 did not resolve, where a reader of the artifact meets it. `completeness` is what
            # ENFORCES it - a session with any of these is not source complete - and the stage that holds the
            # S3 decisions is its caller, so this number is the state's visible form, never its authority.
            "unresolved_versions": sum(len(t["unresolved_versions"]) for t in transcripts),
            "overlap_omissions": sum(w["overlap_omissions"] for t in transcripts for w in t["windows"]),
            "hints": {key: sum(t["hints"][key] for t in transcripts)
                      for key in ("human_turns", "assistant_turns", "delegated_turns", "tool_calls", "tool_results",
                                  "error_results")}}


def report_lines(manifest):
    """Counts, window numbers and byte totals - never a transcript's content."""
    t, limits = manifest["totals"], manifest["limits"]
    per = sorted(len(x["windows"]) for x in manifest["transcripts"])
    mean = t["driver_bytes"] / t["windows"] if t["windows"] else 0
    return [f"views window {manifest['window']}: {t['sessions']} sessions and {t['children']} children in {t['files']} files, "
            f"{t['windows']} windows (per file: min {per[0] if per else 0}, median {per[len(per) // 2] if per else 0}, max {per[-1] if per else 0})",
            f"  driver bytes: total {t['driver_bytes']}, mean {mean:.0f}, max {t['max_driver_bytes']} of {bound.driver_budget(limits)} "
            f"(allowance {limits['allowance']}, overhead {limits['overhead']})",
            f"  estimated tokens at 3.5 bytes each (a packing diagnostic, not a bound): {t['driver_bytes'] / 3.5:.0f}",
            f"  source bytes {t['source_bytes']}, {t['records']} records, {t['items']} blocks, {t['viewed_items']} viewed, "
            f"{t['clipped']} clipped, {t['forced']} forced by a pending event",
            f"  hints (shape only, never evidence): {t['hints']['human_turns']} human turns, "
            f"{t['hints']['assistant_turns']} assistant turns, {t['hints']['tool_calls']} tool calls, "
            f"{t['hints']['error_results']} failed tool results",
            f"  quarantined {len(manifest['quarantined'])}"]


# ---- expansion -------------------------------------------------------------------------------

def current_version(document, where):
    """`document`, refused by name when it was built under another projection.

    The check belongs at every boundary where a stored artifact is CONSUMED, not only where a quote is
    verified: a window built under a projection that masked less is a window of text the current one would
    have masked, and reading it hands a model exactly what the newer masking exists to withhold."""
    stored = document.get("redaction_version")
    if stored != projection.CURRENT:
        raise Refused(f"REDACTION_VERSION_MISMATCH {where}: made under {stored!r}, the projection is "
                      f"{projection.CURRENT!r}; build the view again from the source")
    return document


def window_doc(run_dir, name, path):
    """One window of a view, refused if it was built under another projection."""
    return current_version(records.read_json(path), f"{name}/{pathlib.Path(path).name}")


def sequence_doc(run_dir, name):
    path = pathlib.Path(run_dir) / "views" / name / "sequence.json"
    return current_version(records.read_json(path), f"{name}/sequence.json")


def expand(run_dir, call_id, name, record_id, reason, forced_by="none", omission=None):
    """The omitted middle of a clipped record as additional windows under the same bound and span mapping; the
    decision is logged. Returns the windows (also written beside the view). The omitted characters are re-read from
    the projection and must hash to the manifest's `omitted_span.sha256`."""
    run_dir = pathlib.Path(run_dir)
    doc = sequence_doc(run_dir, name)
    first, window = None, None
    for path in sorted((run_dir / "views" / name).glob("[0-9]*.json")):
        doc_here = window_doc(run_dir, name, path)
        rows = [m for m in doc_here["omission_manifest"]
                if (m["omission_id"] == omission if omission else m["record_id"] == record_id)]
        # the record's OWN window decides: the same record is also context in its neighbours, and an
        # overlap row describes the cut the context made, not the record's own clip
        owned_row = next((m for m in rows if m.get("origin") != "overlap"), None)
        if owned_row:
            first, window = owned_row, doc_here
            break
        if rows and first is None:
            first, window = rows[0], doc_here
    if first is None:
        raise Refused(f"EXPANSION_UNKNOWN {omission or record_id}: no window of {name} lists it as clipped")
    if omission is None:
        every = sorted({m["omission_id"] for path in sorted((run_dir / "views" / name).glob("[0-9]*.json"))
                        for m in window_doc(run_dir, name, path)["omission_manifest"]
                        if m["record_id"] == record_id})
        if len(every) > 1:
            raise Refused(f"EXPANSION_AMBIGUOUS {record_id}: it lost {len(every)} intervals ({every}); name the "
                          "omission to expand, because expanding one of them discharges only that one")
    with open(run_dir / doc["redacted"], "rb") as handle:
        handle.seek(first["locator"]["offset"])
        line = json.loads(handle.readline())
    block = next(b for b in line["items"] if f"{line['line']}{b['pointer']}" == record_id)
    span = first["omitted_span"]
    middle = block["text"][span["start"]:span["end"]]
    if records.sha256_bytes(middle.encode("utf-8")) != span["sha256"]:
        raise Refused(f"EXPANSION_SOURCE_DRIFT {record_id}: the omitted characters no longer hash to the manifest's span")
    # an overlap omission belongs to no window's own records, so the row carries the role
    role = next((r["window_role"] for r in window["records"] if r["record_id"] == record_id),
                first.get("window_role", "context"))
    entry = {"record_id": record_id, "line": line["line"], "json_pointer": block["pointer"], "kind": block["kind"],
             "tool": block.get("tool"), "ts": line.get("ts"), "error": bool(block.get("error")), "window_role": role,
             "size": len(middle), "text": middle, "segments": [{"view": [0, len(middle)], "block": [span["start"], span["end"]]}], "owned": True}
    base = {"transcript": doc["transcript"], "version": doc["version"], "version_sha": doc["version_sha"],
            "redaction_version": doc["redaction_version"], "expansion_of": record_id}
    windows, _ = cut_windows(base, [entry], doc["limits"], overlap=False)
    # The path carries the OMISSION, not only the call. Two records expanded under one call id wrote
    # `expansion-<call>-1.json` each, and `records.write_text` replaces, so the first expansion's windows were
    # gone and `expansions.jsonl` still held both decisions - an artifact set that reads as complete and is
    # not. The omission id's digest is what makes the name safe through the path sanitiser.
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", call_id)
    tag = re.sub(r"[^A-Za-z0-9._-]", "_", first["omission_id"])[-24:]
    for w in windows:
        records.write_json(run_dir, run_dir / "views" / name / f"expansion-{safe}-{tag}-{w['window_n']}.json", w)
    record_decision(run_dir, call_id, name, record_id, "expand", reason, forced_by,
                    omission=first["omission_id"])
    return windows


def record_decision(run_dir, call_id, name, record_id, decision, reason, forced_by="none", omission=None):
    """Append one decision to `expansions.jsonl`. A skip of a forced record is refused (EXPANSION_SKIPPED); a call's
    decision of an omission is written once, and another decision of it by the same call is refused where it would be
    written (EXPANSION_DECISION_CONFLICT)."""
    if decision not in DECISIONS or forced_by not in FORCED_BY or not str(reason or "").strip():
        raise Refused(f"EXPANSION_DECISION_INVALID {record_id}: decision {decision!r} (expand or skip), forced_by {forced_by!r}, "
                      "and a reason are required")
    if decision == "skip" and forced_by != "none":
        raise Refused(f"EXPANSION_SKIPPED {record_id}: forced by {forced_by}, so it must be expanded")
    path = stagelock.confine(run_dir, pathlib.Path(run_dir) / "expansions.jsonl")
    # the locator names the OMISSION as well as the record: accounting is by interval, and a decision
    # that names only the record answers for intervals nobody looked at
    locator = {"transcript": name, "record_id": record_id, "omission_id": omission}
    line = json.dumps({"call_id": call_id, "locator": locator, "reason": reason, "decision": decision, "forced_by": forced_by},
                      sort_keys=True, ensure_ascii=False)
    # the same decision of the same call again, as a resumed run makes it when its call is reused, is not written
    # twice, and the same call deciding the same omission otherwise is refused (WP-08 commit 5a); a decision by another
    # call is another line
    held = [h for h in path.read_text(encoding="utf-8").splitlines() if h.strip()] if path.is_file() else []
    if line in held:
        return
    if any((d["call_id"], d["locator"]) == (call_id, locator) for d in map(json.loads, held)):
        raise Refused(f"EXPANSION_DECISION_CONFLICT {record_id}: call {call_id} decided {omission or 'the record'} of "
                      f"{name} already, otherwise; a call's decision of an omission is written once")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


# ---- fixtures ---------------------------------------------------------------------------------

REALIZATION = "golden"  # every fixture is synthetic: `golden` writes the transcripts and the run directory it reads
FX_WINDOW = {"start": "2026-10-01T00:00:00", "end": "2026-10-08T00:00:00", "tz": "UTC"}
FX_PREV_WINDOW = "2026-09-24T00:00:00/2026-10-01T00:00:00@UTC"
FX_SECRET = "sk-ant-oat01-" + "Ab1_" * 12          # the shape P4 sweeps the run directory for
FX_HOME = "/Users/fixtureowner"
FX_RAW_PATH = f"{FX_HOME}/Documents/repo/notes.md"
FX_TERM = "plain version"                          # a retrieval term of an expected observation (§7.3)
# M#3: metadata reaches the model too. The one tool call of the fixture is named after the swept shape, so
# the end-to-end sweep proves the projection covers every transcript-derived string a window renders and not
# only a block's text - `header_of` writes this name into the window.
FX_TOOL_SECRET = f"mcp__{FX_SECRET[:24]}__call"
FX_QUOTE = f"show me the {FX_TERM}"
FX_HIDDEN_PLAIN = "the person asked again for a simpler telling of it"          # carries no retrieval term
FX_HIDDEN_TERM = f"the person asked again for the {FX_TERM} of it"              # carries one
FX_HIDDEN_WIDTH = max(len(FX_HIDDEN_PLAIN), len(FX_HIDDEN_TERM))
# R#0: the shapes whose masking depends on the ORDER of decoding and masking, planted inside a record the
# window owns so the sweep reaches them through every artifact. The first is a floor match that crosses the
# structure's own syntax with an encoded key behind it; the second is a header whose scheme crosses a
# newline; the third is a home path encoded as a dictionary KEY.
FX_PLANTED_JSON = "r0planted-" + "Zz9" * 6
FX_PLANTED_HEADER = "r0opaque-" + "Yy8" * 6
FX_ENCODED_HOME = FX_HOME.replace("/", "\\u002f")
FX_MIXED = ('{"note":"api_key=abc", "\\u0070assword":"' + FX_PLANTED_JSON + '", '
            '"' + FX_ENCODED_HOME + '\\u002fx":1}')
FX_MULTILINE = "Authorization: Bearer\n" + FX_PLANTED_HEADER
# Q#0 and Q#2: the shapes whose masking depends on the FALLBACK and on the original text's obligations
# rather than on what the decoded form can reach. Each is planted in a transcript of its own so the whole
# stage runs over it - projection, windows, index, evidence - instead of the projection alone.
FX_FALLBACK_SCALAR = "q2encoded-secret-7Xy"       # reachable only by decoding, in a block that falls back
FX_FALLBACK_LEFTOVER = "q2leftover-credential"    # the cross-member floor claim that causes the fallback
FX_OBLIGATION_JSON = "q2leakme-structure-9"       # a secret-named key in prose whose value is a structure
FX_OBLIGATION_QUOTED = "q2quoted-credential-4"    # a quoted scalar that itself holds a structure
FX_FALLBACK_TOKEN = "sk-" + "A1b2" * 6
# A#3: the shapes of the last two rounds, downstream as well: an escaped array under a readable keyed name
# (Z#0), a quoted scalar whose keyed value holds a structure (A#0), and a literal mask standing beside a
# credential (rule 2) - each in a record of its own so a control can name its locator.
FX_ESCAPED_ARRAY = "a3escaped-array-credential"
FX_QUOTED_SCALAR = "a3quoted-scalar-credential"
FX_MASK_NEIGHBOUR = "a3beside-the-mask-credential"
# A#1 downstream: a plain structure, then an ESCAPED member. Nothing reads the escaped part unless escaped
# regions are read in their own coordinates, and the plain part used to excuse it.
FX_ESCAPED_TAIL = "a1tail-credential-after-a-plain-structure"
# M#7: the three shapes of the fifth round, each as its own located block, so a control can name a locator
# and a quote can be refused at it.
FX_SIBLING_KEY = "e0siblingnamecredential"      # the key's name stands in an unrelated value
FX_MIXED_DEPTH = "e1mixeddepthcredential"       # a twice-encoded token beside an already plain path
FX_NO_QUOTE_BODY = "e2noquotebodycredential"    # a decodable body with no escaped quote in it
# M#8: a credential behind six layers of escaped escapes, in prose a plain structure begins. No raw rule
# matches it and no mapping locates it; the verifier reads it through its lenient decoding and blanks the
# block. It is here so the recorded blank count has something to count.
FX_LAYERED = "m8layeredcredentialabcdefgh"
# R#4: the cross-member claim arriving as a STRUCTURE rather than as text. Each member is clean on its own;
# the floor match exists only in the serialisation between them, which is the text a reader sees.
FX_STRUCTURED_CROSS = "r4structuredcrosscredential"
# S#3: the rows the case table still lacked. A secret-named member whose colon carries a newline, which no
# textual key scanner with a space-only separator reads; an unreadable escape run; and S#0's keyed fragment
# in mixed text, which is a member of no object.
FX_MEMBER_NEWLINE = "s3membernewlinecredential"
FX_MIXED_TEXT = "s3mixedtextcredential"
# S#5: one content block with TWO leaves the backstop takes. It goes through the transcript, so the figures
# the run records are read from views.json rather than from the counters a control just moved itself.
FX_TWO_LEAF = "s5twoleafabcdefghijklmn"
# U#2: the shapes of the last two rounds, downstream as well. A long name a cap would have split; a value
# that merely starts with the mask and carries a comma; an escape run before a real newline; and a duplicate
# secret-named member whose masked copy stands last.
FX_LONG_NAME = "u2longnamecredential"
FX_MASK_COMMA = "u2maskcommacredential"
FX_ESCAPE_RUN = "u2escaperuncredential"
FX_DUPLICATE_LAST = "u2duplicatelastcredential"
# X#3: the reviewer's round-14 shapes as TRANSCRIPT ROWS rather than as strings handed to the detector. A
# detector string says what the rule answers; a row says what the stage does with it - the window it writes,
# the postings it makes, the quote it stores and the quote it refuses.
FX_READABLE_ARRAY = "x3readablearraycredential"
FX_READABLE_OBJECT = "x3readableobjectcredential"
FX_SCALAR_SUFFIX = "x3scalarsuffixcredential"
FX_NEWLINE_SEPARATOR = "x3newlineseparatorcredential"


def fx_stamp(day, hour=1, minute=0, month=10):
    return f"2026-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00.000Z"


def fx_human(stamp, text):
    return {"type": "user", "timestamp": stamp, "message": {"role": "user", "content": text}}


def fx_assistant(stamp, text):
    return {"type": "assistant", "timestamp": stamp, "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def fx_call(stamp, tool, arguments):
    return {"type": "assistant", "timestamp": stamp,
            "message": {"role": "assistant", "content": [{"type": "tool_use", "name": tool, "input": arguments}]}}


def fx_result(stamp, text, failed=False):
    return {"type": "user", "timestamp": stamp,
            "message": {"role": "user", "content": [{"type": "tool_result", "is_error": failed, "content": text}]}}


def fx_clipped(hidden, filler=6):
    """A tool result long enough to be clipped (design §5.4): a head and a tail that two of these share byte for
    byte, two lines of the middle that read as errors, and one sentence hidden in the gap between them. `filler`
    sets how much of the middle is omitted, so an expansion of it can be made to need more than one window."""
    head = "\n".join(f"  file {i:03d}  ok  {'.' * 30}" for i in range(70))
    tail = "\n".join(f"  summary {i:03d}  done  {'-' * 24}" for i in range(45))
    ordinary = [f"  middle line {i:03d} {'=' * 30}" for i in range(filler)]
    middle = ordinary[:filler // 2] + ["  error: the write was denied", "  Traceback (most recent call last):",
                                       "  " + hidden.ljust(FX_HIDDEN_WIDTH, ".")] + ordinary[filler // 2:]
    return head + "\n" + "\n".join(middle) + "\n" + tail


def fx_main_records():
    """T1, the eligible Claude session: one record before the window, the viewed turns, two after it."""
    return [
        fx_assistant(fx_stamp(30, month=9, hour=10), "an answer from the week before this window"),
        fx_human(fx_stamp(3, hour=1), f"{FX_QUOTE} of that, and see {FX_RAW_PATH} please"),
        fx_assistant(fx_stamp(3, hour=2), f"here it is; the slot still holds {FX_SECRET} for the runner"),
        fx_call(fx_stamp(3, hour=3), FX_TOOL_SECRET, {"command": f"ls {FX_HOME}/Documents/repo"}),
        fx_result(fx_stamp(3, hour=4), fx_clipped("the outcome of this read lands after the window", filler=500), failed=True),
        fx_human(fx_stamp(3, hour=5), f"and the other thing? {FX_MIXED} {FX_MULTILINE}"),
        # P#2: a host wrote this field, so it is a string like any other - and nothing projected it. The
        # fixture plants the swept shape and a home path in it, end to end.
        fx_result(f"{FX_SECRET} at {FX_RAW_PATH}", fx_clipped("nothing worth keeping is hidden here")),
        fx_assistant(fx_stamp(3, hour=7), "".join(f"paragraph {i:03d} of the long answer, which no window holds whole. "
                                                  for i in range(300))),
        fx_result(fx_stamp(3, hour=8), fx_clipped(FX_HIDDEN_PLAIN)),
        fx_result(fx_stamp(3, hour=9), fx_clipped(FX_HIDDEN_TERM)),
        fx_assistant(fx_stamp(9, hour=10), "an answer from the week after this window"),
        fx_assistant(fx_stamp(9, hour=11), "and one more after it"),
    ]


def fx_child_records():
    """T2, the child transcript linked to T1: a parent's instruction and the child's answer."""
    return [{"type": "user", "timestamp": fx_stamp(3, hour=3), "isSidechain": True,
             "message": {"role": "user", "content": "find every place the plain version is asked for"}},
            fx_assistant(fx_stamp(3, hour=4), "two places, both in the guides"),
            {"type": "attachment", "timestamp": fx_stamp(3, hour=4),
             "attachment": {"type": "queued_command", "prompt": "while you are there, check the Korean reference"}}]


def fx_codex_records():
    """T3, the Codex session deferred by the previous window: its records are the backlog this run reads first."""
    return [{"type": "response_item", "timestamp": fx_stamp(26, month=9, hour=1),
             "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "summarize the week"}]}},
            {"type": "response_item", "timestamp": fx_stamp(26, month=9, hour=2),
             "payload": {"type": "function_call", "name": "shell", "arguments": '{"command":"git log"}'}},
            {"type": "response_item", "timestamp": fx_stamp(26, month=9, hour=3),
             "payload": {"type": "function_call_output", "output": "two commits, both on the lane branch"}}]


def fx_write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return records.sha256_file(path)


def fx_entry(host, ident, source, path, sha, status="eligible", **fields):
    """A census row of one transcript file, in its host's shape (`census.finish`)."""
    fields.setdefault("counted", status == "eligible")
    file = {k: fields.pop(k) for k in ("owned", "work", "versions") if k in fields}
    entry = census.blank(host, ident, source, str(path), status=status, provenance="indexed", window_overlap="inside", **fields)
    entry["segments"][0].update(sha256=sha, **file)
    return census.finish(entry)


def fx_versions(state, tid):
    """The versions of `tid` a census row carries, as S1 writes them from the state it observed (`census.build`)."""
    return [{k: v[k] for k in ("sha", "record_count", "prefix_sha")} for v in state["transcripts"][tid]["versions"]]


def fx_owned(rows, window=None):
    """The records of `rows` the window owns, decided the way S1 decides them (`coverage.Ownership`)."""
    start, end, _id = coverage.window_bounds(window or FX_WINDOW)
    own = coverage.Ownership(start, end)
    for index, row in enumerate(rows):
        own.feed(index, row.get("timestamp"))
    return own.finish(len(rows))["owned"]


def fx_census(window_id, entries):
    """The census document a golden run reads: the fields S1 writes, over the fixture's transcripts. Each source has
    discovered what is filed under it and totals it by status, as S1 does, so the census S3 hands back is accountable
    (`census.account`)."""
    sources = {name: {"state": "present", "path": f"/srv/golden/{name}",
                      "discovered": sum(1 for e in entries if e["source"] == name),
                      "unrecognized": 0, "totals": {}, "detail": None} for name in census.DIRECTORIES}
    census.totals_of(entries, sources)
    return {"kind": "periodic", "window": window_id, "originator_table_sha256": records.sha256_bytes(b"golden"),
            "sources": sources,
            "originators": {}, "provenance": {}, "pins": {},
            "independence": {"components": 1, "unknown_components": 0, "sessions": len(entries), "unknown_sessions": 0},
            "unowned": {"earlier_windows": 0, "rewritten": {"files": 0, "records": 0}, "first_seen": {"files": 0, "records": 0}},
            "pending_events": [], "transcripts": entries}


def fx_seats(root, capacity, seat=None, host_version="2.1.304", name=None):
    """A `seats.json` fixture that differs from the checkout's in one declared context capacity.

    The capacity is read through `gate.seat_capacity` like every other, so a control that needs a narrower
    seat declares one instead of handing the window builder a number (BB#5)."""
    seat = seat or declare.fixture()["seats"][declare.VIEW_WINDOW_STAGE]
    held = json.loads(gate.SEATS.read_text(encoding="utf-8"))
    held["seat_capacity"] = {**(held.get("seat_capacity") or {}),
                             seat: {"context_capacity": capacity, "host_version": host_version,
                                    "basis": "a fixture's own declaration, not a measurement"}}
    path = pathlib.Path(root) / (name or f"seats-capacity-{capacity}.json")
    path.write_text(json.dumps(held), encoding="utf-8")
    return path


def golden(root, name="g", overhead=bound.PACKET_OVERHEAD, capacity=None, reservation=32_000,
           allowance=3200, census_sha=None, compressed=False, main_records=None, owned=None, allowance_entry=None,
           window=None, state=None, prefix_ok=None, ledger_doc=None):
    """A run directory S2 can be run over, and the result of running it (realization: golden).

    The transcripts are `fx_main_records` (eligible, with a pending event and four clipped tool results), its child,
    and a Codex session the previous window deferred. `overhead` is what makes the bound bite: the packet's bytes are
    the one part of the driver's budget a fixture can set, so a small corpus produces several windows, split spans and
    overlaps instead of a 100 KB one. `census_sha` plants a census that read other bytes than the copy now hashes to.
    `window` and `state` make the run of a later window over the coverage state an earlier run left (WP-08 done-when 4):
    the transcripts are observed into that state as S1 observes them, `prefix_ok` saying whether a changed file kept the
    earlier version as its prefix (`coverage.observe`), and nothing is planted in it. The declaration's checkout holds
    `ledger_doc` (an empty schema 2 ledger by default) and pins its hash, as S0 pins the ledger S3 reads the expected
    observations due from."""
    root = pathlib.Path(root)
    run_dir, host = root / name, root / f"{name}-host"
    main_path, child_path = host / "t1.jsonl", host / "t1-child.jsonl"
    codex_path = host / ("rollout-t3.jsonl.zst" if compressed else "rollout-t3.jsonl")
    # `main_records` lets a control run the WHOLE stage over a different transcript - the overlap cases need
    # long turns, and a case that cannot be built as a real run can only be tested against hand-made rows
    main_sha = fx_write(main_path, main_records() if main_records else fx_main_records())
    child_sha = fx_write(child_path, fx_child_records())
    if compressed:
        plain = host / "rollout-t3.jsonl"
        codex_sha = fx_write(plain, fx_codex_records())
        zstd = sources.declared(declare.fixture()).get("zstd")
        if not os.access(zstd or "", os.X_OK):
            raise Refused(f"ZSTD_UNAVAILABLE {zstd}: the compressed fixture is made with the declared zstd")
        try:
            subprocess.run([sources.checked_zstd(zstd), "-q", "-f", str(plain), "-o", str(codex_path)], check=True)
        except ValueError as exc:
            raise Refused(f"ZSTD_UNAVAILABLE {zstd}: {exc}") from exc
        plain.unlink()
    else:
        codex_sha = fx_write(codex_path, fx_codex_records())

    main_id, child_id, codex_id = "a1000000-0000-4000-8000-000000000001", "a1000000-0000-4000-8000-000000000002", \
        "019e0001-0000-7000-8000-000000000003"
    # a Codex file's coverage key names the file (D-20261103-a7128a)
    main_tid, child_tid, codex_tid = (lineage.identity("claude", main_id), lineage.identity("claude", child_id),
                                      f"{lineage.identity('codex', codex_id)}@{census.stem_of(codex_path)}")
    window = window or FX_WINDOW
    _start, _end, window_id = coverage.window_bounds(window)

    planted, state = state is None, copy.deepcopy(state) if state is not None else coverage.new_state()
    for tid, sha, count in ((main_tid, main_sha, len(main_records() if main_records else fx_main_records())),
                            (codex_tid, codex_sha, len(fx_codex_records())), (child_tid, child_sha, len(fx_child_records()))):
        coverage.observe(state, tid, sha, count, records.sha256_bytes(f"prefix-{tid}".encode()), prefix_ok)
    if planted:
        state["pending_events"] = [{"id": "pe-1", "transcript": main_tid, "version": 0, "window": window_id, "first_record": 4}]
        state["backlog"] = [{"transcript": codex_tid, "version": 0, "window": FX_PREV_WINDOW, "status": "deferred",
                             "unread": [[0, len(fx_codex_records())]]}]
    # the records whose timestamps fall in the window; for the default transcript the first and the last two
    # do not. A caller whose transcript puts a case on the first record says so, or the control it writes
    # would be about a record no window owns.
    main_owned = owned or [[1, 10]]
    codex_work = coverage.work_of(state, codex_tid, [], window_id)
    entries = [
        fx_entry("claude", main_id, "claude_projects", main_path, census_sha or main_sha, owned=main_owned,
                 work=coverage.work_of(state, main_tid, main_owned, window_id), versions=fx_versions(state, main_tid)),
        # S1 reads a member of an eligible unit like its root (D-20261103-85f3e8): the child carries its own work
        fx_entry("claude", child_id, "claude_projects", child_path, child_sha, status="child_of", parent=main_id,
                 owned=fx_owned(fx_child_records(), window),
                 work=coverage.work_of(state, child_tid, fx_owned(fx_child_records(), window), window_id),
                 versions=fx_versions(state, child_tid)),
        # a later window's run may find the Codex session owing it nothing, which S1 records as nothing new
        fx_entry("codex", codex_id, "codex_sessions", codex_path, codex_sha, owned=[], work=codex_work,
                 status="eligible" if codex_work["in_window"] or codex_work["backlog"] else "nothing_new",
                 versions=fx_versions(state, codex_tid)),
    ]
    document = fx_census(window_id, entries)
    problems = validate.validate_instance(census.validator(), document)
    if problems:
        raise Refused("CENSUS_INVALID the golden census does not conform: " + "; ".join(problems[:3]))

    declaration = {**declare.fixture(), "window": window, "output_caps": {declare.VIEW_WINDOW_STAGE: reservation}}
    seat = declaration["seats"][declare.VIEW_WINDOW_STAGE]
    declaration["host_allowance"] = {seat: {**declaration["host_allowance"][seat], "allowance_tokens": allowance}}
    if allowance_entry is not None:
        # a stage that DISPATCHES over these windows declares the allowance seats.json measured, which the
        # dispatcher admits a view-window call against; S2's own controls keep the small one that bites
        declaration["host_allowance"] = {seat: allowance_entry}
    checkout = root / f"{name}-checkout"
    ledger_path = checkout / ledger.LEDGER_REL
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(ledger.render(ledger_doc if ledger_doc is not None else ledger.sample_ledger()), encoding="utf-8")
    declaration["destinations"] = {**declaration["destinations"], "checkout": str(checkout.resolve())}
    declaration["starting_hashes"] = {**declaration["starting_hashes"], "ledger": records.sha256_file(ledger_path)}
    run_dir.mkdir(parents=True, exist_ok=True)
    declare.create(run_dir, declaration)
    with records.run_stage(run_dir, "S1") as stage:
        records.write_text(run_dir, run_dir / "census.json", census.dump(document))
        records.write_json(run_dir, run_dir / "coverage.json", state)
        stage.output("census.json")
        stage.output("coverage.json")

    # a narrower capacity than the checkout declares is a seats fixture, read by the shared reader (BB#5)
    manifest = run(run_dir, overhead,
                   fx_seats(root, capacity) if capacity is not None else None)
    by_name = {t["name"]: t for t in manifest["transcripts"]}
    main = by_name.get(safe_name(main_tid))  # absent when the run quarantined it, which `census_sha` plants
    # through the checked reader like every other window read, so the fixture cannot be the one place a
    # stale artifact would be accepted
    windows = [window_doc(run_dir, main["name"], run_dir / w["path"]) for w in main["windows"]] if main else []
    return {"run_dir": run_dir, "run": declaration, "seat": seat, "manifest": manifest, "limits": manifest["limits"],
            "main": main, "child": by_name.get(safe_name(child_tid)), "codex": by_name.get(safe_name(codex_tid)),
            "by_name": by_name, "windows": windows, "state": state, "census": document, "window": window_id,
            "paths": {"main": main_path, "child": child_path, "codex": codex_path, "ledger": ledger_path},
            "tids": {"main": main_tid, "child": child_tid, "codex": codex_tid},
            "lines": {"before": 1, "human": 2, "secret": 3, "call": 4, "pending_clip": 5, "second_human": 6,
                      "late_clip": 7, "long": 8, "pair_plain": 9, "pair_term": 10, "after": 11},
            "raw_path": FX_RAW_PATH, "secret": FX_SECRET, "home": FX_HOME, "term": FX_TERM, "realization": REALIZATION}


def golden_unit(root, name, plant=None):
    """A run whose census holds one unit (D-20261103-85f3e8): a Claude root, a member under it, a member under that
    member, and a third level whose records all lie before the window. `plant` is `changed` (the second level's
    census read other bytes), `idle` (the root's unit owes the window nothing) or `mid_unreadable` (S1 could not read the
    first level, which keeps its parent: review c0fix r1 #2). Returns `(run_dir, ids, manifest or the refusal)`."""
    root = pathlib.Path(root)
    run_dir, host = root / name, root / f"{name}-host"
    ids = {"root": "a2000000-0000-4000-8000-000000000001", "d1": "a2000000-0000-4000-8000-000000000002",
           "d2": "a2000000-0000-4000-8000-000000000003", "d3": "a2000000-0000-4000-8000-000000000004"}
    before = [{**row, "timestamp": fx_stamp(26, month=9, hour=row_n)} for row_n, row in enumerate(fx_child_records())]
    rows = {"root": fx_main_records(), "d1": fx_child_records(), "d2": fx_child_records(), "d3": before}
    parents = {"d1": "root", "d2": "d1", "d3": "d2"}
    _start, _end, window_id = coverage.window_bounds(FX_WINDOW)
    state, entries = coverage.new_state(), []
    for key in ("root", "d1", "d2", "d3"):
        path = host / f"{key}.jsonl"
        sha = fx_write(path, rows[key])
        tid = lineage.identity("claude", ids[key])
        coverage.observe(state, tid, sha, len(rows[key]), sha, None)
        owned = [] if plant == "idle" else fx_owned(rows[key])
        census_sha = "00" * 32 if (plant == "changed" and key == "d2") else sha
        fields = {"status": "child_of", "parent": ids[parents[key]]} if key in parents else {}
        if plant == "mid_unreadable" and key == "d1":
            fields.update(status="unreadable", reason=f"READ_FAILED {path}: planted")
        entries.append(fx_entry("claude", ids[key], "claude_projects", path, census_sha, owned=owned,
                                work=coverage.work_of(state, tid, owned, window_id), versions=fx_versions(state, tid), **fields))
    document = fx_census(window_id, entries)
    declaration = {**declare.fixture(), "window": FX_WINDOW}
    run_dir.mkdir(parents=True, exist_ok=True)
    declare.create(run_dir, declaration)
    with records.run_stage(run_dir, "S1") as stage:
        records.write_text(run_dir, run_dir / "census.json", census.dump(document))
        records.write_json(run_dir, run_dir / "coverage.json", state)
        stage.output("census.json")
        stage.output("coverage.json")
    try:
        outcome = run(run_dir, 32_000)
    except Exception as exc:  # the refusal, or what a reverted check raises: a control reads it, never a traceback
        outcome = exc
    return run_dir, {key: lineage.identity("claude", value) for key, value in ids.items()}, outcome


def golden_split(root, name, owns, base=None):
    """A run whose census holds one Codex thread written in two files (D-20261103-a7128a), the window owning `owns[0]` of
    the first and `owns[1]` of the second. `base` writes the run's coverage state as a targeted run leaves it, the
    periodic base instead of what S1 observed (review c0fix r1 #3): `empty`, or `older` (it saw two records fewer of each
    file). Returns `(the two files' coverage keys, manifest or the refusal)`."""
    root = pathlib.Path(root)
    run_dir, host = root / name, root / f"{name}-host"
    thread = "019e0002-0000-7000-8000-000000000004"
    _start, _end, window_id = coverage.window_bounds(FX_WINDOW)
    state, files = coverage.new_state(), []
    for n, owned in enumerate(owns):
        path = host / f"rollout-2026-10-0{n + 2}T10-00-00-{thread}.jsonl"
        sha = fx_write(path, fx_codex_records())
        key = f"{lineage.identity('codex', thread)}@{census.stem_of(path)}"
        coverage.observe(state, key, sha, len(fx_codex_records()), sha, None)
        files.append({**census.segment(census.stem_of(path), "codex_sessions", str(path)), "sha256": sha, "owned": owned,
                      "work": coverage.work_of(state, key, owned, window_id), "versions": fx_versions(state, key)})
    entry = census.blank("codex", thread, "codex_sessions", status="eligible", counted=True, provenance="indexed", window_overlap="inside")
    entry["segments"] = files
    document = fx_census(window_id, [census.finish(entry)])
    run_dir.mkdir(parents=True, exist_ok=True)
    declare.create(run_dir, {**declare.fixture(), "window": FX_WINDOW})
    with records.run_stage(run_dir, "S1") as stage:
        records.write_text(run_dir, run_dir / "census.json", census.dump(document))
        written = state
        if base == "empty":
            written = coverage.new_state()
        elif base == "older":
            written = copy.deepcopy(state)
            for entry in written["transcripts"].values():
                entry["versions"][-1]["record_count"] -= 2
        records.write_json(run_dir, run_dir / "coverage.json", written)
        stage.output("census.json")
        stage.output("coverage.json")
    try:
        outcome = run(run_dir, 32_000)
    except Exception as exc:  # the refusal, or what a reverted check raises: a control reads it, never a traceback
        outcome = exc
    return [f"{lineage.identity('codex', thread)}@{census.stem_of(f['path'])}" for f in files], outcome


# ---- self-test --------------------------------------------------------------------------------

# The window invariants of plan WP-06 done-when 3 and 4: this is the self-test's branch list, and the
# run below asserts that every one of them was exercised by a label of its own.
INVARIANTS = ("owned once", "overlap", "span union", "error line", "bound (a)", "bound (d)", "unbounded",
              "observed input", "omission manifest", "completeness", "forced", "basis")


class Checks:
    """The self-test's assertions, each under a label that is reported when it fails."""

    def __init__(self):
        self.failures, self.ran = [], []

    def expect(self, label, got, want):
        self.ran.append(label)
        if got != want:
            self.failures.append(f"{label}: got {got!r}, expected {want!r}")

    def named(self, label, errors, *codes):
        """`errors` is a list of violation lines: it must carry every code, and with none it must be empty."""
        self.ran.append(label)
        if not codes and errors:
            self.failures.append(f"{label}: expected no violation, got {errors}")
        for code in codes:
            if not any(code in line for line in errors):
                self.failures.append(f"{label}: expected {code!r} in {errors}")

    def refused(self, label, call, *codes):
        self.ran.append(label)
        try:
            call()
        except Refused as exc:
            self.named(label, [str(exc)], *codes)
            self.ran.pop()
            return
        except BaseException as exc:  # a reverted check must not hide behind a traceback
            self.failures.append(f"{label}: raised {type(exc).__name__}: {exc}")
            return
        self.failures.append(f"{label}: nothing was refused")


def fx_instrument():
    """The assertions are what everything below rests on, so they are tested first, by assert: a statement that
    vouches for itself vouches for nothing."""
    probe = Checks()
    probe.expect("wrong value", 1, 2)
    probe.named("missing code", ["CODE_A x"], "CODE_B")
    probe.named("unexpected violation", ["CODE_A x"])
    probe.refused("nothing refused", lambda: None, "CODE_A")
    probe.refused("wrong code", lambda: (_ for _ in ()).throw(Refused("CODE_A x")), "CODE_B")
    probe.refused("other exception", lambda: (_ for _ in ()).throw(ValueError("boom")), "CODE_A")
    probe.expect("right value", 1, 1)
    probe.refused("right code", lambda: (_ for _ in ()).throw(Refused("CODE_A x")), "CODE_A")
    labels = [f.split(":")[0] for f in probe.failures]
    assert labels == ["wrong value", "missing code", "unexpected violation", "nothing refused", "wrong code",
                      "other exception"], f"the assertions do not fail by label: {probe.failures}"


def fx_sweep(root, needles):
    """`{needle: [paths]}` for every file under `root` that holds one of `needles` as a fixed string - the sweep
    P4 and WP-06 done-when 2 run over a run directory, which is why no artifact of it is compressed."""
    found = {needle: [] for needle in needles}
    for path in sorted(pathlib.Path(root).rglob("*")):
        if not path.is_file():
            continue
        text = path.read_bytes()
        for needle in needles:
            if needle.encode("utf-8") in text:
                found[needle].append(str(path.relative_to(root)))
    return found


def fx_texts(run_dir, line):
    """The projected text of every viewed block of one transcript's version."""
    return projection_texts(run_dir, line["redacted"])


def fx_entries(windows):
    """The owned entries of a cut view, by their entry identity (a split message has one per span)."""
    return {eid(r): r for w in windows for r in w["records"]}


def self_test():
    fx_instrument()
    checks = Checks()
    expect, named, refused = checks.expect, checks.named, checks.refused
    # the evidence store is a consumer of these windows, imported here so the production side of this
    # module does not depend on it
    from runlib import evidence as evidence_store
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        golden_run = golden(root, "tight", overhead=100_000)
        run_dir, manifest, main = golden_run["run_dir"], golden_run["manifest"], golden_run["main"]
        # The fixture's own precondition, named. `main` is None when the run quarantined the transcript the
        # rest of this self-test reads, and every assertion after it then died on a NoneType rather than
        # reporting which invariant refused the view - a regression that crashes names nothing.
        if main is None:
            print("views --self-test [FAIL] the fixture's main transcript was quarantined, so no control below ran: "
                  + "; ".join(q.get("reason", "?") for q in manifest["quarantined"]))
            return 1
        windows, lines = golden_run["windows"], golden_run["lines"]
        texts = fx_texts(run_dir, main)
        name = main["name"]
        rid = lambda key, pointer="/message/content/0/content": f"{lines[key]}{pointer}"  # noqa: E731

        # ---- positive controls, before any planted violation ------------------------------------
        expect("the fixtures are declared golden", golden_run["realization"], "golden")
        expect("done-when 1: the immutable copy is named by its own sha256 and is read-only",
               (records.sha256_file(run_dir / main["source_copy"]) == main["version_sha"],
                oct((run_dir / main["source_copy"]).stat().st_mode & 0o777)), (True, "0o444"))
        expect("done-when 1: the copy is the transcript's bytes exactly, decompression aside",
               (run_dir / main["source_copy"]).read_bytes() == golden_run["paths"]["main"].read_bytes(), True)
        before = sorted(p.name for p in (run_dir / "sources").iterdir())
        expect("copying the same version twice leaves the one copy, and no temporary beside it",
               (copy_version(run_dir, golden_run["paths"]["main"], None, {"sha": main["version_sha"], "record_count": main["records"]})[1],
                sorted(p.name for p in (run_dir / "sources").iterdir())), (main["version_sha"], before))
        named("done-when 3, owned once and overlap: every owned entry is in exactly one window and each window's "
              "overlap is what the sequence puts around it",
              check_windows(records.read_json(run_dir / main["sequence"])["sequence"], windows))
        named("done-when 3, span union and error line: the shown stretches and the gaps tile every block, and every "
              "error line of a clipped result is kept whole", check_tiling(windows, texts))
        expect("done-when 3, bound (a) and (d): every window the stage cut is within the bound",
               [w["bound_ok"] for w in windows], [True] * len(windows))
        expect("a message larger than a window is split into mapped spans whose union is the message",
               (len([e for e in fx_entries(windows) if e.startswith(f"{lines['long']}/")]) > 1,
                coverage.normalize([s["block"] for e in fx_entries(windows).values() if e["line"] == lines["long"]
                                    for s in e["segments"]])),
               (True, [[0, len(texts[f"{lines['long']}/message/content/0/text"])]]))
        expect("design §5.2: every entry carries a window role, and the three the design names are all reached",
               sorted({role_label(r["window_role"]) for t in manifest["transcripts"]
                       for w in [records.read_json(run_dir / f["path"]) for f in t["windows"]]
                       for r in w["records"] + [{"window_role": e["window_role"]} for e in w["overlap"]["prev"] + w["overlap"]["next"]]}),
               ["backlog", "context", "in_window"])
        expect("the child transcript is viewed as the parent's, with the parent's instruction shown as delegated",
               (golden_run["child"]["kind"], sorted({r["kind"] for w in [records.read_json(run_dir / f["path"])
                                                                         for f in golden_run["child"]["windows"]] for r in w["records"]})),
               ("child", ["assistant", "delegated"]))
        expect("the Codex session's blocks are read through its own record shape",
               sorted({r["kind"] for w in [records.read_json(run_dir / f["path"]) for f in golden_run["codex"]["windows"]]
                       for r in w["records"]}), ["human", "tool_call", "tool_result"])
        # S2 holds two producers (records.STAGE_PARTS): this stage run is the views part, and the
        # stage itself is complete only once the inventory part has run too.
        expect("the views part of S2 is complete with views.json as its output",
               [(r["parts"]["views"]["status"], [o["artifact"] for o in r["parts"]["views"]["outputs"]])
                for s, r in records.stage_records(run_dir).items() if s == "S2"],
               [("complete", ["views.json"])])
        expect("the stage is partial while the other part of S2 has not run",
               [r["status"] for s, r in records.stage_records(run_dir).items() if s == "S2"], ["partial"])
        expect("the totals of views.json add up over the transcripts it lists",
               (manifest["totals"]["windows"], manifest["totals"]["clipped"]),
               (sum(len(t["windows"]) for t in manifest["transcripts"]), sum(t["clipped"] for t in manifest["transcripts"])))
        expect("the shape counts digest.py kept are carried as hints over every block of the version, viewed or not, "
               "and no claim rests on one",
               (main["hints"]["human_turns"], main["hints"]["assistant_turns"], main["hints"]["tool_calls"],
                main["hints"]["error_results"], main["hints"]["tools"]),
               # the tool's name is counted as the projection wrote it: the hint is a shape, and a hint that
               # carried the unmasked name would be one more place the name reached
               (2, 5, 1, 1, {projection.project(FX_TOOL_SECRET): 1}))
        expect("the report is counts, window numbers and byte totals, and holds no transcript text",
               [line for line in report_lines(manifest) if FX_TERM in line or FX_HOME in line], [])

        # ---- done-when 2: the projection is the only text, and the planted secret and path stay in the raw copy
        # M#3: the planted shape stands in a tool NAME as well as in a block's text, and the sweep looks for
        # it in both - a name `header_of` renders into the window is as model-visible as the text under it.
        expect("done-when 2: the tool name a window renders is the projection's, not the transcript's",
               [line for w in windows for r in w["records"] for line in [header_of(r)] if FX_SECRET[:10] in line], [])
        # P#2: the timestamp a window renders is a timestamp by construction - parsed and written back in one
        # normal form - so a host string carrying a secret or a path cannot stand in it
        expect("done-when 2: a record whose timestamp carried the planted shape renders no timestamp at all, "
               "and neither the shape nor the path reaches a header",
               [line for w in windows for r in w["records"] for line in [header_of(r)]
                if FX_SECRET[:10] in line or FX_HOME in line], [])
        expect("done-when 2: every timestamp a window carries is one `fromisoformat` parses and this code "
               "re-emitted, never the host's own string",
               sorted({r["ts"] for w in windows for r in w["records"] if r["ts"]}
                      - {normal_stamp(r["ts"]) for w in windows for r in w["records"] if r["ts"]}), [])
        expect("done-when 2: ... and the projection file carries no unparsable timestamp either",
               [line["ts"] for line in (json.loads(l) for l in
                                        (run_dir / main["redacted"]).read_text(encoding="utf-8").splitlines() if l.strip())
                if line["ts"] is not None and normal_stamp(line["ts"]) != line["ts"]], [])
        expect("done-when 2: the projection file carries no unmasked tool name either",
               [b for line in (json.loads(l) for l in
                               (run_dir / main["redacted"]).read_text(encoding="utf-8").splitlines() if l.strip())
                for b in line["items"] if FX_SECRET[:10] in (b.get("tool") or "")], [])
        # V#2: the sweep claims the EVIDENCE store too, and the golden run creates none - so the claim was
        # over an empty directory. Quotes are made here, from the very blocks that carry the planted shapes,
        # verified and stored, before the sweep runs. A masked quote must verify; a quote of the raw secret
        # must not exist in the projection at all, which is the same statement from the other side.
        quoted = []
        for record_key, needle in (("second_human", "and the other thing?"),
                                   ("second_human", projection.FLOOR.PLACEHOLDER)):
            entry = fx_entries(windows).get(f"{lines[record_key]}/message/content")
            if entry is None or needle not in entry["text"]:
                continue
            made = evidence_store.from_view(run_dir, main["version_sha"], entry, needle,
                                            occurrence=0 if entry["text"].count(needle) > 1 else None)
            expect(f"V#2: a quote of the projected text ({needle[:24]!r}) verifies against the immutable copy",
                   evidence_store.verify(run_dir, made), [])
            evidence_store.append(run_dir, "wp06-r4", made)
            quoted.append(made["evidence_id"])
        expect("V#2: the evidence store is not empty, so the sweep below judges something",
               (len(quoted) > 0, len(evidence_store.load(run_dir, "wp06-r4"))), (True, len(quoted)))
        for planted in (FX_PLANTED_JSON, FX_PLANTED_HEADER, FX_SECRET):
            refused(f"V#2: a quote of the raw secret {planted[:14]!r} cannot be made from the projection at all",
                    lambda needle=planted: evidence_store.from_quote(
                        run_dir, main["version_sha"], lines["second_human"], "/message/content", needle,
                        "in_window"),
                    "QUOTE_MISMATCH")
        sweep = fx_sweep(run_dir, [FX_SECRET[:10], FX_RAW_PATH, FX_PLANTED_JSON, FX_PLANTED_HEADER])
        expect("done-when 2 / R#0: the planted token, home path, the value behind a floor match that crosses "
               "JSON syntax, the credential after a multiline scheme, and an encoded home path used as a "
               "dictionary key are in no projection, window, index, evidence or report, and the raw copy "
               "keeps them (the instrument control: a sweep that found nothing anywhere proves nothing)",
               ({needle: sorted({p.split("/")[0] for p in paths}) for needle, paths in sweep.items()}),
               {FX_SECRET[:10]: ["sources"], FX_RAW_PATH: ["sources"], FX_PLANTED_JSON: ["sources"],
                FX_PLANTED_HEADER: ["sources"]})
        # An encoded home path is a question about the DECODED text, not about bytes: the artifacts are JSON,
        # so a backslash in the text is `\\` in the file and a byte sweep for the encoded form finds it
        # nowhere - in the raw copy either, which is how such a sweep reports clean over nothing.
        decoded_texts = [b["text"] for line in (json.loads(l) for l in
                                                (run_dir / main["redacted"]).read_text(encoding="utf-8").splitlines()
                                                if l.strip()) for b in line["items"]]
        raw_copy = (run_dir / main["source_copy"]).read_text(encoding="utf-8")
        expect("R#0: the raw copy really holds the encoded home path, so the next control judges something",
               FX_ENCODED_HOME.replace("\\", "\\\\") in raw_copy, True)
        expect("R#0: ... and no projected block's decoded text holds it, however it was encoded",
               [t[:40] for t in decoded_texts if FX_ENCODED_HOME in t or FX_HOME in t], [])
        expect("done-when 2: the home path is masked in the view, the rest of the path kept",
               f"see {projection.HOME_MASK}/Documents/repo/notes.md" in fx_entries(windows)[f"{lines['human']}/message/content"]["text"], True)

        # ---- Q#0, Q#2 and A#3: the decoded shapes, through the whole stage -----------------------
        #
        # The projection's own controls judge `project_text`. These judge the ARTIFACTS: a transcript of the
        # blocks whose secrets only decoding reaches, and of the blocks whose obligations only the original
        # text can see, run through the stage so the sweep covers the projection, the windows, the index and
        # a stored evidence record. Positive controls first - the run really reaches those sources, and the
        # store really holds a record - because a sweep over nothing reports clean.
        # The projection has ONE path now, so there is no fallback to count. What these controls judge
        # instead is that the transcript really exercised the masking sources the cases are about: an
        # encoded literal, an encoded secret-named key, and an escaped region.
        sources_before = {key: projection.STATS[key] for key in
                          ("encoded_secret_key", "unmappable_escape", "undecodable_claim")}
        fb = golden(root, "fb", main_records=fx_fallback_records, owned=[[0, 27]])
        fb_dir, fb_main = fb["run_dir"], fb["main"]
        expect("Q#2 / A#3: projecting this transcript really exercised the decoded sources these controls "
               "are about, so they judge the path they name",
               projection.STATS["encoded_secret_key"] > sources_before["encoded_secret_key"], True)
        fb_entries = fx_entries([window_doc(fb_dir, fb_main["name"], fb_dir / f["path"])
                                 for f in fb_main["windows"]])
        fb_texts = projection_texts(fb_dir, fb_main["redacted"])
        planted_by_name = {"FX_FALLBACK_SCALAR": FX_FALLBACK_SCALAR, "FX_HOME": FX_HOME,
                           "FX_OBLIGATION_JSON": FX_OBLIGATION_JSON,
                           "FX_OBLIGATION_QUOTED": FX_OBLIGATION_QUOTED,
                           "FX_ESCAPED_ARRAY": FX_ESCAPED_ARRAY, "FX_QUOTED_SCALAR": FX_QUOTED_SCALAR,
                           "FX_MASK_NEIGHBOUR": FX_MASK_NEIGHBOUR, "FX_ESCAPED_TAIL": FX_ESCAPED_TAIL,
                           "FX_SIBLING_KEY": FX_SIBLING_KEY, "FX_MIXED_DEPTH": FX_MIXED_DEPTH,
                           "FX_NO_QUOTE_BODY": FX_NO_QUOTE_BODY,
                           "FX_STRUCTURED_CROSS": FX_STRUCTURED_CROSS,
                           "FX_MEMBER_NEWLINE": FX_MEMBER_NEWLINE, "FX_MIXED_TEXT": FX_MIXED_TEXT,
                           "FX_LONG_NAME": FX_LONG_NAME, "FX_MASK_COMMA": FX_MASK_COMMA,
                           "FX_ESCAPE_RUN": FX_ESCAPE_RUN, "FX_DUPLICATE_LAST": FX_DUPLICATE_LAST,
                           "FX_READABLE_ARRAY": FX_READABLE_ARRAY,
                           "FX_READABLE_OBJECT": FX_READABLE_OBJECT,
                           "FX_SCALAR_SUFFIX": FX_SCALAR_SUFFIX,
                           "FX_NEWLINE_SEPARATOR": FX_NEWLINE_SEPARATOR}
        fb_quoted = []
        def every_spelling_of(value):
            """Every spelling of a planted value that this transcript or the projection can write."""
            return list(projection.spellings(value)) + [
                value, value.replace("/", "\\u002f"), value.replace("/", "\\\\/"),
                "".join(f"\\u{ord(character):04x}" for character in value)]

        # The vocabulary is built from the records' OWN strings rather than from a JSON dump of them: a dump
        # re-escapes every backslash, so the encoded spelling of a planted value no longer matched the text
        # being cleaned and stayed in the vocabulary - which then subtracted it from the very subjects it
        # should have been.
        cleaned = []
        for record in fx_fallback_records():
            for form in projection.spellings_of(record):
                for value in planted_by_name.values():
                    for spelling in every_spelling_of(value):
                        form = form.replace(spelling, " ")
                cleaned.append(form)
        ordinary = " ".join(cleaned)
        vocabulary = search.keys_of(ordinary)[0]

        # V#3: every row of the table states which detector must find it, and a CLEAN counterpart of the
        # same shape must be found by none - a row whose shape is blanked whatever it holds proves nothing
        # about the detector it names.
        def one_span_difference(clean, dirty):
            """`(whether the two differ in exactly one span, what stands there in the dirty text)`.

            A common prefix and a common suffix leave one span in each text; the pair is a pair only when
            the dirty span is the target value and the clean span is what the row masks it to."""
            start = 0
            while start < min(len(clean), len(dirty)) and clean[start] == dirty[start]:
                start += 1
            end = 0
            while (end < min(len(clean), len(dirty)) - start
                   and clean[len(clean) - 1 - end] == dirty[len(dirty) - 1 - end]):
                end += 1
            return True, dirty[start:len(dirty) - end]

        # Y#2: the dirty text of each pair is a LITERAL copy of the persisted row's own text, with exactly
        # the target value changed - not the row with its first mask substituted, which produced a different
        # shape and so read a rule the fixture does not run. The mask-plus-comma row keeps its comma; the
        # newline-separated member is the one that changes, not the nested member before it.
        row_detectors = {
            "FX_LONG_NAME": ("keyed fragment",
                             '{"note":"plain"} "' + "x" * 38 + '\\u0070assword":"'
                             + projection.FLOOR.PLACEHOLDER + '"',
                             '{"note":"plain"} "' + "x" * 38 + '\\u0070assword":"' + FX_LONG_NAME + '"'),
            "FX_MASK_COMMA": ("keyed fragment",
                              '{"note":"plain"} "\\u0070assword":"'
                              + projection.FLOOR.PLACEHOLDER + '"',
                              '{"note":"plain"} "\\u0070assword":"'
                              + projection.FLOOR.PLACEHOLDER + ',' + FX_MASK_COMMA + '"'),
            "FX_ESCAPE_RUN": ("verifier-limit", '{"note":"plain"} \\n ordinary words',
                              '{"note":"plain"} \\\n' + FX_ESCAPE_RUN),
            "FX_DUPLICATE_LAST": ("secret-named key",
                                  '{"password":"' + projection.FLOOR.PLACEHOLDER + '","password":"'
                                  + projection.FLOOR.PLACEHOLDER + '"}',
                                  '{"password":"' + FX_DUPLICATE_LAST + '","password":"'
                                  + projection.FLOOR.PLACEHOLDER + '"}'),
            "FX_MEMBER_NEWLINE": ("secret-named key",
                                  '{"safe":{"password":"' + projection.FLOOR.PLACEHOLDER
                                  + '"},"password"\n:"' + projection.FLOOR.PLACEHOLDER + '"}',
                                  '{"safe":{"password":"' + projection.FLOOR.PLACEHOLDER
                                  + '"},"password"\n:"' + FX_MEMBER_NEWLINE + '"}'),
            "FX_MIXED_TEXT": ("keyed fragment",
                              '{"note":"plain"} "\\u0070assword":"'
                              + projection.FLOOR.PLACEHOLDER + '"',
                              '{"note":"plain"} "\\u0070assword":"' + FX_MIXED_TEXT + '"'),
        }

        # W#3: separator gaps at and beyond the span the old rule capped at eight characters - the pair
        # differs only in the number of spaces, so what the control reads is the rule and not the shape.
        for spaces in (0, 1, 7, 8, 9, 40):
            gap = " " * spaces
            dirty = '{"note":"plain"} "\\u0070assword"' + gap + ':"w3gap_canary"'
            clean = '{"note":"plain"} "\\u0070assword"' + gap + ':"' + projection.FLOOR.PLACEHOLDER + '"'
            # AB#1: the clean case first for each gap, so a detector that fires on everything is read as
            # a failure here rather than confirmed by the dirty assertion that follows it
            expect(f"W#3: the clean counterpart at {spaces} space(s) is found by nothing",
                   projection.discloses(clean, FX_HOME), None)
            expect(f"W#3: ... and a separator {spaces} space(s) after the key is read",
                   projection.discloses(dirty, FX_HOME), "keyed fragment")

        # X#4: the pairs are the PERSISTED rows, with the planted value swapped for the mask and nothing
        # else changed - the previous pair substituted a shape of its own, so it read a rule the fixture
        # does not run. The clean case is asserted first in each pair.
        persisted_pairs = [
            ("X#3 / V#0: a readable array under an encoded key",
             '{"note":"plain"} "\\u0070assword":["%s"]', FX_READABLE_ARRAY, "keyed fragment"),
            ("X#3 / V#0: a readable object under an encoded key",
             '{"note":"plain"} "\\u0070assword":{"inner":"%s"}', FX_READABLE_OBJECT, "keyed fragment"),
            ("X#3 / V#1: a suffix after a masked scalar",
             '{"note":"plain"} "\\u0070assword":"' + projection.FLOOR.PLACEHOLDER + '"%s',
             FX_SCALAR_SUFFIX, "keyed fragment"),
            ("X#3 / V#2: a quoted key whose separator is on the next line",
             '{"note":"plain"} "password"\n: "%s"', FX_NEWLINE_SEPARATOR, "keyed fragment"),
        ]
        for label, shape, planted, detector in persisted_pairs:
            clean = shape % projection.FLOOR.PLACEHOLDER if "%s" in shape else shape
            if label.endswith("a suffix after a masked scalar"):
                clean = shape % ""        # the suffix removed, which is this row's only difference
            expect(f"X#4: {label}: the masked form of the persisted row is found by nothing",
                   projection.discloses(clean, FX_HOME), None)
            expect(f"X#4: {label}: the row as the transcript writes it is found by {detector!r}",
                   projection.discloses(shape % planted, FX_HOME), detector)

        for planted_name, (detector, clean, dirty) in sorted(row_detectors.items()):
            planted = planted_by_name[planted_name]
            # Y#2: clean and dirty differ in exactly ONE span, and that span is the target value
            # Y#2: the two texts differ in exactly ONE span, and that span carries the target value. For
            # the mask-plus-comma row the span is the comma and the value, which is what that row is about;
            # for the escape-run row it is the run, which is what THAT row is about.
            single, span = one_span_difference(clean, dirty)
            subject = planted if planted_name != "FX_ESCAPE_RUN" else FX_ESCAPE_RUN
            # the span is the target value, and what else it holds is only the punctuation the row is
            # about - stated per row rather than compared with itself
            extra = {"FX_MASK_COMMA": ",", "FX_ESCAPE_RUN": "\n"}.get(planted_name, "")
            expect(f"Y#2: {planted_name}: clean and dirty differ in exactly one span, and that span is the "
                   f"target value{' with the punctuation this row is about' if extra else ''}",
                   (single, span), (True, extra + subject))
            # the clean case first, then the exact detector the row is about
            expect(f"V#3: {planted_name}: its clean counterpart is found by nothing",
                   projection.discloses(clean, FX_HOME), None)
            expect(f"V#3: {planted_name}: the shape is found by {detector!r}",
                   projection.discloses(dirty, FX_HOME), detector)

        fb_index = search.load(fb_dir / fb_main["index"])
        for label, line, pointer, planted_name in FX_FALLBACK_CASES:
            planted, record = planted_by_name[planted_name], f"{line}{pointer}"
            # the case is at the locator it names, and the window owns it
            entry = fb_entries.get(record) or next(
                (e for key, e in fb_entries.items() if key.startswith(record)), None)
            if entry is None:
                checks.failures.append(f"Z#1: {label}: no window owns {record}, so nothing below judges it")
                continue
            expect(f"Z#1: {label}: the projected block at {record} holds no part of the planted value",
                   [form for form in projection.spellings(planted)
                    if len(form) >= projection.PARTIAL_SURVIVAL and form in fb_texts.get(record, "")], [])
            expect(f"Z#1: ... and the projection of that block discharges every obligation of the original",
                   projection.readable_survivors(
                       projection.serialise(
                           evidence_store.read_block(fb_dir / fb_main["source_copy"], line, pointer) or ""),
                       fb_texts.get(record, "")), [])
            # S#3: the row's own window, read by decoding rather than by bytes. The sweep below covers the
            # whole run; this says the block's own window is clean, which is what the row is about.
            projected = fb_texts.get(record, "")
            expect(f"S#3: {label}: no decoding of this block's window text reads the planted value",
                   [form for form in projection.spellings_of(projected)
                    if planted.lower() in form.lower()], [])
            # T#4: the PERSISTED window files, read from disk and decoded - not the projection file the
            # row's text came from. A window is what a reader opens, and it is written separately.
            window_hits = []
            for window in fb_main["windows"]:
                body = (fb_dir / window["path"]).read_text(encoding="utf-8", errors="replace")
                if any(planted.lower() in form.lower() for form in projection.spellings_of(body)):
                    window_hits.append(window["path"])
            expect(f"T#4: {label}: no persisted window file reads the planted value, decoded or raw",
                   window_hits, [])
            expect(f"S#3: {label}: the index holds no distinctive posting key of this row",
                   sorted(key for key in {k for form in every_spelling_of(planted)
                                          for k in search.keys_of(form)[0]} - vocabulary
                          if key in fb_index.postings), [])
            expect(f"R#4: {label}: projecting the projected block again changes nothing",
                   projection.project(projected, home=FX_HOME), projected)
            made = evidence_store.from_view(fb_dir, fb_main["version_sha"], entry,
                                            projection.FLOOR.PLACEHOLDER, occurrence=0)
            expect(f"Z#1: ... and a masked quote AT THAT LOCATOR verifies against the immutable copy",
                   (evidence_store.verify(fb_dir, made), made["line"], made["json_pointer"]),
                   ([], line, pointer))
            evidence_store.append(fb_dir, "wp06-r6", made)
            fb_quoted.append(made["evidence_id"])
            # T#4: and the record as the STORE holds it, read back rather than trusted from memory
            stored = [record for record in evidence_store.load(fb_dir, "wp06-r6")
                      if record["evidence_id"] == made["evidence_id"]]
            expect(f"T#4: {label}: the stored evidence record holds the mask and verifies from the copy",
                   [(record["redacted_text"], evidence_store.verify(fb_dir, record)) for record in stored],
                   [(projection.FLOOR.PLACEHOLDER, [])])
            refused(f"Z#1: ... while a quote of the raw value at that same locator is refused",
                    lambda needle=planted, at=line, ptr=pointer: evidence_store.from_quote(
                        fb_dir, fb_main["version_sha"], at, ptr, needle, "in_window"),
                    "QUOTE_MISMATCH")
        expect("Z#1: every planted case was judged at its own locator, and each left a stored record",
               (len(fb_quoted), len(evidence_store.load(fb_dir, "wp06-r6"))),
               (len(FX_FALLBACK_CASES), len(FX_FALLBACK_CASES)))
        # A#3: the index is inspected by its POSTINGS, not by asking it a question. `search` re-checks every
        # candidate against the projected text, so an index full of secret postings answers "no hits" while
        # carrying the secret in a file a reader can open. The postings are the artifact; they are what must
        # be clean.
        fb_index = search.load(fb_dir / fb_main["index"])
        # The vocabulary of this transcript with the planted values taken OUT: a key in it is ordinary
        # English the fixture's prose contains anyway, and asking the index to lack `secret` or `users` would
        # fail on the prose rather than on a leak. What remains - the keys only a planted value produces -
        # is this control's subject, and each case must contribute at least one or it judges nothing.
        for label, _line, _pointer, planted_name in FX_FALLBACK_CASES:
            planted = planted_by_name[planted_name]
            # M#4: every spelling the value is ACTUALLY emitted in - the plain one, each of the projection's
            # own spellings, and the encoded and slash-escaped forms the transcript writes - tokenised by
            # the index's own tokeniser rather than by a guess about what a key looks like.
            spelled = every_spelling_of(planted)
            distinctive = sorted({key for form in spelled for key in search.keys_of(form)[0]} - vocabulary)
            expect(f"A#3: {label} has a posting key of its own, so the index control below is about it",
                   len(distinctive) > 0, True)
            present = sorted(key for key in distinctive if key in fb_index.postings)
            expect(f"A#3: the index holds no posting key of {label} - in any spelling of the value",
                   present, [])
            hits = search.search(fb_index, [planted], lambda ref: fb_texts.get(f"{ref[0]}{ref[1]}", ""))
            expect(f"A#3: ... and the search over it matches nothing for that value either", hits, [])
        # ... and every artifact of this run is swept in its DECODED strings as well as its bytes, for both
        # spellings of the owner's path: the encoded one is what the source locator carries
        # E#5: every artifact is read by its OWN shape - a `.json` file parsed whole, a `.jsonl` file
        # parsed per record - and then every string in it is decoded by the verifier's decoder. Reading the
        # bytes alone misses a credential split across a record's escaping, and reading only one run's
        # projection misses contamination that lives in an index or a window and nowhere else.
        encoded_home = FX_HOME.replace("/", "\\u002f")
        slash_home = FX_HOME.replace("/", "\\\\/")
        decoded_strings, parsed_artifacts = [], 0
        for path in sorted(fb_dir.rglob("*")):
            if not path.is_file() or "sources" in path.parts:
                continue
            where = str(path.relative_to(fb_dir))
            raw = path.read_text(encoding="utf-8", errors="replace")
            decoded_strings.append((where, raw))
            documents = []
            if path.suffix == ".json":
                try:
                    documents.append(json.loads(raw))
                    parsed_artifacts += 1
                except ValueError:
                    expect(f"E#5: {where} is a .json artifact that parses, so its strings can be read",
                           False, True)
            elif path.suffix == ".jsonl":
                for line in raw.splitlines():
                    if not line.strip():
                        continue
                    try:
                        documents.append(json.loads(line))
                    except ValueError:
                        expect(f"E#5: every record of {where} parses, so its strings can be read",
                               False, True)
                parsed_artifacts += 1 if documents else 0
            for document in documents:
                decoded_strings += [(where, form) for form in projection.spellings_of(document)]
        expect("E#5: the run's .json and .jsonl artifacts were parsed by their own shape, so the sweep "
               "below reads their strings and not only their bytes", parsed_artifacts > 3, True)
        expect("A#3: the artifacts of the fallback run really were read, so the sweep below judges them",
               len(decoded_strings) > 10, True)
        # ---- M#2: an artifact made under the PREDECESSOR's projection is refused at every boundary -----
        #
        # The projection changed, so its version changed with it: r9 masked less than r10 does, and a window,
        # an index or an evidence record built under r9 is text the current masking exists to withhold. Each
        # boundary is asked separately, because each one is a different reader.
        stale_cases = []
        stale_window = dict(json.loads((fb_dir / fb_main["windows"][0]["path"]).read_text(encoding="utf-8")))
        stale_window["redaction_version"] = "r21"
        try:
            current_version(stale_window, "a window made under r21")
            stale_cases.append("a window made under r21 was accepted")
        except Refused as exc:
            if "REDACTION_VERSION_MISMATCH" not in str(exc):
                stale_cases.append(f"a stale window was refused unnamed: {exc}")
        stale_index_root = fb_dir.parent / "stale-index"
        shutil.copytree(fb_dir, stale_index_root)
        stale_index_path = stale_index_root / fb_main["index"]
        stale_index = json.loads(stale_index_path.read_text(encoding="utf-8"))
        stale_index["redaction_version"] = "r21"
        stale_index_path.write_text(json.dumps(stale_index, ensure_ascii=False), encoding="utf-8")
        try:
            search.load(stale_index_path, projection.CURRENT)
            stale_cases.append("an index made under r21 was accepted")
        except Exception as exc:
            if "REDACTION_VERSION_MISMATCH" not in str(exc):
                stale_cases.append(f"a stale index was refused unnamed: {exc}")
        shutil.rmtree(stale_index_root)
        try:
            projection.project("x", "r21")
            stale_cases.append("the r21 projection is still callable, so a stale artifact can be remade")
        except KeyError as exc:
            if "REDACTION_VERSION_MISMATCH" not in str(exc):
                stale_cases.append(f"the r21 projection was refused unnamed: {exc}")
        expect("M#2: a window, an index and the projection itself all refuse r21 by name", stale_cases, [])

        # M#8: the blanking is recorded where a reader of the run can see it. A figure nobody keeps is a
        # figure nobody can act on - and these transcripts really do blank blocks, so the field is not an
        # always-empty map.
        expect("M#8: the run's view stats carry a blanked-block count by detector",
               isinstance(fb_main.get("blanked"), dict), True)
        expect("M#8: a transcript whose blocks the mapping cannot cover records at least one blanked block",
               sum(fb_main.get("blanked", {}).values()) > 0, True)
        # S#5: read from the run's own views.json. The two-leaf block above is in the transcript, so one
        # blanked content block and two blanking operations is a statement about what the stage recorded -
        # not about counters a control moved itself, which would pass even if both fields held the same
        # figure.
        # T#6: the two-leaf block in a transcript of ITS OWN, so the figures are not an aggregate over
        # other blanking blocks, and views.json is reopened from disk rather than read from the return value.
        def fx_two_leaf_only():
            layered_leaf = "sk" + "\\\\u005c" * 6 + "u002d" + FX_TWO_LEAF
            return [fx_human(fx_stamp(1), "one block, two leaves"),
                    fx_call(fx_stamp(2), "Write", {"a": layered_leaf, "b": layered_leaf + "two",
                                                   "c": "plain words"})]

        isolated = golden(root, "two-leaf", main_records=fx_two_leaf_only, owned=[[0, 3]])
        reopened = json.loads((isolated["run_dir"] / "views.json").read_text(encoding="utf-8"))
        transcripts = reopened["transcripts"] if "transcripts" in reopened else [reopened]
        mine = [entry for entry in transcripts if entry.get("blanked")]
        expect("T#6: the isolated transcript's views.json records exactly one blanked content block and two "
               "blanking operations",
               [(entry.get("blanked"), entry.get("blank_operations")) for entry in mine],
               [({"floor": 1}, {"floor": 2})])

        # V#3 / T#2: the unfinished-escape row, counted from a persisted run of its OWN. The fixture is
        # chosen so the mapping cannot be what blanked it: no floor match, no locatable keyed value, only a
        # run this verifier cannot finish - so a verifier-limit count of exactly one block and one operation
        # is a statement about the verifier and about nothing else.
        def fx_escape_run_only():
            return [fx_human(fx_stamp(1), "one block with an unfinished escape run"),
                    fx_assistant(fx_stamp(2), '{"note":"plain"} \\\n' + FX_ESCAPE_RUN)]

        run_only = golden(root, "escape-run", main_records=fx_escape_run_only, owned=[[0, 3]])
        run_main = json.loads((run_only["run_dir"] / "views.json").read_text(encoding="utf-8"))
        entries = run_main["transcripts"] if "transcripts" in run_main else [run_main]
        counted = [(entry.get("blanked"), entry.get("blank_operations"))
                   for entry in entries if entry.get("blanked")]
        expect("V#3 / T#2: an isolated run of the unfinished-escape block records exactly one blanked "
               "content block and one blanking operation, both for verifier-limit",
               counted, [({"verifier-limit": 1}, {"verifier-limit": 1})])
        expect("V#3 / T#2: and the credential is in none of that run's artifacts, decoded or raw",
               [str(path.relative_to(run_only["run_dir"]))
                for path in sorted(run_only["run_dir"].rglob("*"))
                if path.is_file() and "sources" not in path.parts
                and any(FX_ESCAPE_RUN in form for form in projection.spellings_of(
                    path.read_text(encoding="utf-8", errors="replace")))], [])

        floor_blocks = fb_main.get("blanked", {}).get("floor", 0)
        floor_operations = fb_main.get("blank_operations", {}).get("floor", 0)
        expect("S#5: the run recorded blanked content blocks and blanking operations, and the two-leaf "
               "block is the one block that contributes a SECOND operation - so the operations exceed the "
               "blocks by exactly one",
               (floor_blocks > 0, floor_operations - floor_blocks), (True, 1))
        layered = "sk" + "\\\\u005c" * 6 + "u002dr6leafabcdefghijkl"
        ops_before = sum(projection.BLANKED.values())
        blocks_before = sum(projection.BLOCKS.values())
        projection.project({"a": layered, "b": layered + "two", "c": "plain words"}, home=FX_HOME)
        expect("R#6: a structured block with two blanking leaves counts two operations",
               sum(projection.BLANKED.values()) - ops_before, 2)
        expect("R#6: ... and exactly one blanked content block",
               sum(projection.BLOCKS.values()) - blocks_before, 1)
        expect("R#6: the run records blanked content blocks and blanking operations separately",
               sorted(fb_main.get("blank_operations", {}).values(), reverse=True)[:1]
               >= sorted(fb_main.get("blanked", {}).values(), reverse=True)[:1], True)
        expect("M#8: the recorded reasons are the verifier's own detector names",
               sorted(set(fb_main.get("blanked", {})) - {"floor", "home path", "secret-named key",
                                                         "keyed fragment", "verifier-limit",
                                                         "broken syntax"}), [])

        # ... and the two checks are proven on deliberate contamination, because a sweep that has never
        # rejected anything is a sweep whose reach is unknown. One copy of the run gets an encoded home path
        # in the INDEX alone, another in a WINDOW alone: each is a file the earlier controls did not read.
        for what, relative, mutate in (
                ("an encoded home path in the index and nowhere else", fb_main["index"],
                 lambda data: {**data, "postings": {**data["postings"],
                                                    **{key: [0] for key
                                                       in search.keys_of(encoded_home)[0]}}}),
                ("an encoded home path in a window, readable only after decoding",
                 fb_main["windows"][0]["path"], None)):
            planted_root = fb_dir.parent / f"planted-{abs(hash(what)) % 10000}"
            shutil.copytree(fb_dir, planted_root)
            target = planted_root / relative
            if mutate is None:
                # R#3: the contamination is written so that NO raw search for any spelling of the path
                # finds it - every character of the home is a \u escape - and only a decoding exposes it.
                # The window stays valid JSON, so the planted file is a window a reader could open.
                # TWICE encoded: inside the window's JSON string this reads as `\u002f\u0055...`, which
                # one decoding turns into the escape sequence and a second into the path itself. None of the
                # spellings the sweep searches for appears in the file's bytes.
                deep_home = "".join(f"\\\\u{ord(character):04x}" for character in FX_HOME)
                body = target.read_text(encoding="utf-8")
                planted_body = body.replace(projection.FLOOR.PLACEHOLDER, deep_home, 1)
                target.write_text(planted_body, encoding="utf-8")
                def reads_as_json(text):
                    """Whether a window file parses - as one document, or as one per line."""
                    try:
                        json.loads(text)
                        return True
                    except ValueError:
                        pass
                    lines = [line for line in text.splitlines() if line.strip()]
                    try:
                        for line in lines:
                            json.loads(line)
                    except ValueError:
                        return False
                    return bool(lines)

                expect("R#3: the planted window is still a window - it parses as it did before",
                       reads_as_json(planted_body), reads_as_json(body))
                expect("R#3: no raw search for any spelling of the owner's path finds the plant",
                       [spelling for spelling in every_spelling_of(FX_HOME)
                        if spelling in planted_body], [])
            else:
                target.write_text(json.dumps(mutate(json.loads(target.read_text(encoding="utf-8"))),
                                             ensure_ascii=False), encoding="utf-8")
            # The subjects are the index's OWN keys for the owner's path: a posting drops the backslashes,
            # so comparing the path's characters to a posting file's bytes can never match. This is what
            # M#4 means by deriving subjects from the emitted spellings through the real tokeniser.
            path_subjects = sorted({key for form in every_spelling_of(FX_HOME)
                                    for key in search.keys_of(form)[0]} - vocabulary)
            expect(f"M#4: the owner's path has index keys of its own, so the check below has subjects",
                   len(path_subjects) > 0, True)
            caught = []
            for path in sorted(planted_root.rglob("*")):
                if not path.is_file() or "sources" in path.parts:
                    continue
                raw = path.read_text(encoding="utf-8", errors="replace")
                forms = [raw]
                if path.suffix == ".json":
                    try:
                        forms += projection.spellings_of(json.loads(raw))
                    except ValueError:
                        pass
                elif path.suffix == ".jsonl":
                    for line in raw.splitlines():
                        try:
                            forms += projection.spellings_of(json.loads(line))
                        except ValueError:
                            pass
                # case-insensitively: the index lowercases its posting keys, so a contaminated posting is
                # the owner's path in a spelling the earlier byte comparison could not see
                lowered = [form.lower() for form in forms]
                if any(needle.lower() in form
                       for needle in (FX_HOME, encoded_home, slash_home) for form in lowered):
                    caught.append(str(path.relative_to(planted_root)))
                    continue
                # ... and an index is judged by its postings, which is where a tokenised path hides
                if '"postings"' in raw:
                    try:
                        postings = json.loads(raw).get("postings", {})
                    except ValueError:
                        postings = {}
                    if any(key in postings for key in path_subjects):
                        caught.append(str(path.relative_to(planted_root)))
            expect(f"E#5: the sweep rejects {what}", sorted(caught), [relative])
            if mutate is not None:
                planted_index = search.load(planted_root / relative)
                expect("M#4: the posting check rejects the planted index",
                       sorted(key for key in path_subjects if key in planted_index.postings) != [], True)
            shutil.rmtree(planted_root)

        for needle, what in ((FX_SIBLING_KEY, "the credential under an encoded key with a sibling name"),
                             (FX_MIXED_DEPTH, "the twice-encoded token beside a plain path"),
                             (FX_NO_QUOTE_BODY, "the credential in a body with no escaped quote"),
                             (FX_ESCAPED_TAIL, "the credential in an escaped member after a plain structure"),
                             (FX_ESCAPED_ARRAY, "the credential inside an escaped array"),
                             (FX_QUOTED_SCALAR, "the credential inside a quoted scalar's structure"),
                             (FX_MASK_NEIGHBOUR, "the credential standing beside a literal mask"),
                             (FX_HOME, "the owner's home in plain form"),
                             (encoded_home, "the owner's home in its encoded spelling"),
                             (slash_home, "the owner's home in its slash-escaped spelling"),
                             (FX_FALLBACK_SCALAR, "the encoded scalar credential"),
                             (FX_OBLIGATION_JSON, "the credential inside a readable structure"),
                             (FX_OBLIGATION_QUOTED, "the credential inside a quoted structure")):
            expect(f"A#3: no artifact of the run holds {what}, in its bytes or in any decoded string of it",
                   sorted({where for where, text in decoded_strings
                           if needle.lower() in text.lower()}), [])
        fb_sweep = fx_sweep(fb_dir, [FX_FALLBACK_SCALAR, FX_FALLBACK_LEFTOVER, FX_OBLIGATION_JSON,
                                     FX_OBLIGATION_QUOTED, FX_HOME])
        expect("Q#0 and Q#2: the credential only decoding could reach, the cross-member floor claim, the value "
               "of a secret-named key whose value is a readable structure, the credential inside a quoted "
               "structure, and the owner's home are in no projection, window, index, evidence or report of "
               "the fallback run - and the immutable copy keeps every one of them",
               {needle: sorted({path.split("/")[0] for path in paths}) for needle, paths in fb_sweep.items()},
               {needle: ["sources"] for needle in (FX_FALLBACK_SCALAR, FX_FALLBACK_LEFTOVER,
                                                   FX_OBLIGATION_JSON, FX_OBLIGATION_QUOTED, FX_HOME)})
        expect("Q#2: ... and the run it swept really has the artifacts the claim covers",
               sorted({part.split("/")[0] for part in
                       [str(x.relative_to(fb_dir)) for x in fb_dir.rglob("*") if x.is_file()]}
                      & {"sources", "redacted", "views", "index", "evidence"}),
               ["evidence", "index", "redacted", "sources", "views"])

        # ---- done-when 3 and 4 controls: each invariant fails by its name when it is broken -------
        duplicated = copy.deepcopy(windows)
        duplicated[1]["records"].append(copy.deepcopy(duplicated[0]["records"][0]))
        named("control, owned once: a record owned by two windows is named",
              check_windows(records.read_json(run_dir / main["sequence"])["sequence"], duplicated), "SET_MISMATCH")
        merged = copy.deepcopy(windows)
        merged[0]["records"] += merged[1]["records"]   # every owned id is still placed once, so only the empty window is wrong
        merged[1]["records"] = []
        named("control, owned once: a window that holds no record of its own is named",
              check_windows(records.read_json(run_dir / main["sequence"])["sequence"], merged), "SET_MISMATCH")
        thinned = copy.deepcopy(windows)
        thinned[0]["overlap"]["next"].pop()
        named("control, overlap: an overlap entry removed is named",
              check_windows(records.read_json(run_dir / main["sequence"])["sequence"], thinned), "OVERLAP_MISSING")
        both = copy.deepcopy(windows)
        for w in both:
            if w["overlap"]["prev"]:
                turn = next((e for e in w["overlap"]["prev"] if e["kind"] in TURN_KINDS), None)
                if turn:
                    w["overlap"]["omitted"]["prev"].append({"entry": turn["entry"], "record_id": turn["record_id"],
                                                            "kind": turn["kind"], "size": 1, "reason": "overlap_budget"})
                    break
        named("control, overlap: an entry both shown and named omitted is named, because a turn counted twice is "
              "neither accounted nor shown",
              check_windows(records.read_json(run_dir / main["sequence"])["sequence"], both), "OVERLAP_MISSING")
        # M#7: the overlap is five TURNS of design §5.4, not five sequence entries, and its text is the
        # sequence's text up to an omission that is named. Entry ids alone said nothing about either.
        sequence_rows = records.read_json(run_dir / main["sequence"])["sequence"]
        kinds = {r["id"]: r["kind"] for r in sequence_rows}
        for w in windows:
            for side in ("prev", "next"):
                shown = w["overlap"][side]
                # distinct TURNS, not entries of a turn kind: this control read entries and also called a
                # name that does not exist in this function, so it could neither fire nor be noticed
                turns = {(e["line"], e["kind"]) for e in shown if e["kind"] in TURN_KINDS}
                if len(turns) > OVERLAP_TURNS:
                    checks.failures.append(f"overlap {side} of window {w['window_n']} holds {len(turns)} turns, not at most "
                                    f"{OVERLAP_TURNS}")
        expect("done-when 3: every overlap entry's kind is the sequence's own, so a turn is counted as a turn",
               sorted({e["kind"] for w in windows for side in ("prev", "next") for e in w["overlap"][side]}
                      - set(kinds.values())), [])
        # the case that tells the two definitions apart: six tool results stand between the window and the
        # last human turn, so counting five ENTRIES reaches no turn at all while counting five TURNS does
        def synthetic(n, kind, text="x" * 40):
            return {"record_id": f"{n}/message/content", "line": n, "json_pointer": "/message/content", "kind": kind,
                    "tool": None, "ts": fx_stamp(1, hour=n), "error": False, "window_role": "in_window",
                    "size": len(text), "text": text, "segments": [{"view": [0, len(text)], "block": [0, len(text)]}],
                    "owned": True}
        straight = ([synthetic(1, "human"), synthetic(2, "assistant")]
                    + [synthetic(n, "tool_result") for n in range(3, 9)]
                    + [synthetic(9, "human")])
        probe = make_window({"transcript": "t", "version": 1, "version_sha": "ab" * 32,
                             "redaction_version": projection.CURRENT}, 1, straight, 8, 9, golden_run["limits"])
        expect("done-when 3: with six tool results between, the overlap still reaches the human and assistant "
               "turns before them - which five entries could never do",
               [e["kind"] for e in probe["overlap"]["prev"]][:2], ["human", "assistant"])

        # ---- P#3: the four cases of the five-turn overlap, each specified on its own -------------------
        base_probe = {"transcript": "t", "version": 1, "version_sha": "ab" * 32,
                      "redaction_version": projection.CURRENT}
        # (1) a SPLIT MESSAGE is one turn. Five spans of one assistant message used to count as five turns,
        # so the overlap was five fragments of one message and reached no other turn at all.
        long_one = synthetic(2, "assistant", "y" * 4_000)
        split = split_entry(long_one, 600)
        if len(split) < 5:
            checks.failures.append(f"the split-message case needs a message of several spans, got {len(split)}")
        split_seq = [synthetic(1, "human")] + split + [synthetic(3, "human")]
        expect("P#3(1): the spans of one message are one turn, however many spans there are",
               (turns_in(split), before_turns(split_seq, len(split_seq) - 1, OVERLAP_TURNS)), (1, 0))
        split_window = make_window(base_probe, 1, split_seq, len(split_seq) - 1, len(split_seq), golden_run["limits"])
        expect("P#3(1): ... so the window's overlap reaches the human turn BEFORE that message, which counting "
               "spans never did",
               sorted({e["kind"] for e in split_window["overlap"]["prev"]}), ["assistant", "human"])
        # (2) UNOWNED TOOL TRAFFIC does not push turns out of the retained context. The sequence builder kept
        # five BLOCKS, so six tool results between the window and the previous turn lost every turn.
        traffic = ([synthetic(1, "human"), synthetic(2, "assistant")]
                   + [synthetic(n, "tool_result") for n in range(3, 13)] + [synthetic(13, "human")])
        for entry in traffic[:12]:
            entry["owned"] = False
        expect("P#3(2): ten unowned tool results do not displace the turns before them, because the slice is "
               "counted in turns", traffic[before_turns(traffic, 12, OVERLAP_TURNS)]["kind"], "human")
        # ... and the same case through the SEQUENCE BUILDER, which is where the context is retained: it kept
        # five blocks, so ten tool results between the window and the turns before it lost every one of them
        probe_proj = run_dir / "p3-traffic.jsonl"
        with open(probe_proj, "w", encoding="utf-8") as handle:
            for n in range(1, 14):
                kind = "human" if n in (1, 13) else "assistant" if n == 2 else "tool_result"
                handle.write(json.dumps({"line": n, "ts": fx_stamp(1, hour=(n % 24)),
                                         "items": [{"pointer": "/message/content", "kind": kind,
                                                    "tool": None, "text": "t" * 60}]}) + "\n")
        built, _humans, _counts, _tools, _texts = build_sequence(
            probe_proj, {12}, lambda _line: "in_window", search.Index())
        expect("P#3(2): the sequence builder retains context by TURNS, so the human and assistant turns before "
               "ten tool results are still there when the window is cut",
               [e["kind"] for e in built][:2], ["human", "assistant"])
        expect("P#3(2): ... and the retained context is contiguous with the owned record, tool traffic included",
               len(built), 13)
        # (3) BUDGET EXHAUSTION: a turn the side's budget cannot hold is named omitted, with a span and a hash,
        # and the manifest a consumer reads carries it
        # five turns with tool traffic between them: the turns alone fit the side's budget, and the traffic
        # that belongs to them is what exhausts it
        fat = []
        for n in range(1, 11):
            fat.append(synthetic(n, "assistant" if n % 2 else "tool_result", "z" * 600))
        fat.append(synthetic(11, "human"))
        shown_side, gone_side = overlap_side(fat[:7], budget=1_200)
        expect("P#3(3): the entries the overlap budget cannot hold are NAMED omitted, never silently absent",
               (bool(shown_side), bool(gone_side), len(shown_side) + len(gone_side)), (True, True, 7))
        expect("P#3(3): ... and every one of them carries the intervals and hashes of what went, so the "
               "omission is verifiable rather than a label",
               [g["record_id"] for g in gone_side
                if [i["sha256"] for i in g.get("omitted_intervals") or []]
                != [records.sha256_bytes(("z" * 600).encode("utf-8"))]], [])
        fat_window = make_window(base_probe, 1, fat, 10, 11, golden_run["limits"])
        expect("P#3(3): the side's budget is exhausted in this case, which is what the next control reads",
               bool(fat_window["overlap"]["omitted"]["prev"]), True)
        expect("P#3(3): ... and an overlap omission is in the omission manifest, which is the one list a "
               "consumer reads",
               sorted({m["origin"] for m in fat_window["omission_manifest"]}) or ["(none)"], ["overlap"])
        # (4) DUPLICATE MEMBERSHIP: one turn listed twice in a side's list is one turn accounted as several
        doubled = copy.deepcopy(probe)
        doubled["overlap"]["prev"] = doubled["overlap"]["prev"] + doubled["overlap"]["prev"][-1:]
        def as_sequence(entries, owned_from):
            """The sequence rows `check_windows` reads: only the window's own entries are owned."""
            return [{"id": eid(e), "owned": k >= owned_from} for k, e in enumerate(entries)]
        named("control, P#3(4): a turn shown twice in one side's overlap is named, because the sets every other "
              "check used counted it once",
              check_windows(as_sequence(straight, 8), [doubled]), "OVERLAP_MISSING")
        twice_omitted = copy.deepcopy(fat_window)
        twice_omitted["overlap"]["omitted"]["prev"] = twice_omitted["overlap"]["omitted"]["prev"] * 2
        named("control, P#3(4): ... and so is a turn named omitted twice",
              check_windows(as_sequence(fat, 10), [twice_omitted]), "OVERLAP_MISSING")
        # M#8: the index is over the FULL redacted text of the version, not over the work ranges. The
        # fixture's first and last records are outside the window on purpose, so a term that occurs only
        # there is the test: with an index built from the viewed ranges it could not be found at all.
        full_index = search.load(run_dir / main["index"])
        full_texts = projection_texts(run_dir, main["redacted"])
        outside = search.search(full_index, ["week before this window"],
                                lambda ref: full_texts.get(f"{ref[0]}{ref[1]}", ""))
        expect("done-when 5: a term that occurs only outside the work ranges is found, because every projected "
               "block is indexed whatever window owns it",
               [f"{h['ref'][0]}{h['ref'][1]}" for h in outside], [f"{lines['before']}/message/content/0/text"])
        expect("done-when 5: the index holds a document for every projected block of the version, not only the "
               "viewed ones",
               len(full_index.docs), sum(len(line["items"]) for line in
                                         (json.loads(l) for l in (run_dir / main["redacted"]).read_text(
                                             encoding="utf-8").splitlines() if l.strip())))
        first_prev = next((w["overlap"]["prev"] for w in windows if w["overlap"]["prev"]), [])
        expect("done-when 3: a window's overlap reaches back over the tool traffic to a real turn, which five "
               "entries of a split message never did",
               any(e["kind"] in TURN_KINDS for e in first_prev), True)
        # the overlap shows the owning window's own entry text; a split span's overlap starts at the span,
        # so the comparison is against that entry, not against the whole block
        # an overlap entry is either a window's own entry seen from the side, or a record no window owns at
        # all (a turn outside the work ranges, kept as context); the base text differs for the two
        own_text = {eid(r): r["text"] for w in windows for r in w["records"]}
        base_text = lambda e: own_text.get(e["entry"], texts.get(e["record_id"], ""))  # noqa: E731
        expect("done-when 3 / V#1: the text an overlap entry shows is the start of the entry the sequence owns, "
               "and a cut is accounted by hashed intervals of the projected BLOCK rather than by a boolean",
               [e["entry"] for w in windows for side in ("prev", "next") for e in w["overlap"][side]
                if not base_text(e).startswith(e["text"])
                or (e["overlap_cut"] and not e.get("omitted_intervals"))
                or any(records.sha256_bytes(
                    texts.get(e["record_id"], "")[i["start"]:i["end"]].encode("utf-8")) != i["sha256"]
                    for i in e.get("omitted_intervals") or [])], [])
        wrong_text = copy.deepcopy(windows)
        for w in wrong_text:
            if w["overlap"]["prev"]:
                w["overlap"]["prev"][0]["text"] = w["overlap"]["prev"][0]["text"][5:]
                break
        expect("control, overlap: an overlap entry whose text is not the owned entry's own is found",
               [e["entry"] for w in wrong_text for e in w["overlap"]["prev"]
                if not base_text(e).startswith(e["text"])] != [], True)
        short = [copy.deepcopy(w) for w in windows]
        for w in short:
            w["records"] = [r for r in w["records"] if not (r["line"] == lines["long"] and r.get("span", {}).get("index") == 2)]
        named("control, span union: a span dropped from a split message is named", check_tiling(short, texts), "SPAN_UNION_MISMATCH")
        hidden_error = copy.deepcopy(windows)
        for w in hidden_error:
            for r in w["records"]:
                if r["record_id"] != rid("pending_clip"):
                    continue
                a, b = r["clipped"]["error_lines"][0]   # cut the error line out of the stretch that shows it
                segments = []
                for seg in r["segments"]:
                    lo, hi = seg["block"]
                    if lo <= a and b <= hi:
                        segments += [{"view": seg["view"], "block": [lo, a]}] if lo < a else []
                        segments += [{"view": seg["view"], "block": [b, hi]}] if b < hi else []
                    else:
                        segments.append(seg)
                r["segments"] = segments
                r["clipped"]["gaps"] = coverage.normalize(r["clipped"]["gaps"] + [[a, b]])
        named("control, error line: an error line of a clipped result moved into the gap is named",
              check_tiling(hidden_error, texts), "ERROR_LINE_DROPPED")

        # ---- done-when 3: the bound as the owner's amendment of §5.4 states it --------------------
        limits = golden_run["limits"]
        named("bound (a) and (d): a window inside both checks passes", bound.check_bound(1000, limits))
        named("control, bound (a): driver bytes above 120k minus the declared allowance are named",
              bound.check_bound(bound.INPUT_BOUND - limits["allowance"] + 1, limits), "WINDOW_BOUND_EXCEEDED")
        named("control, bound (d): driver bytes that pass (a) but leave no room for the output reservation are named",
              bound.check_bound(50_000, {**limits, "capacity": 60_000}), "WINDOW_CAPACITY_EXCEEDED")
        tighter = golden(root, "capped", overhead=100_000, capacity=150_000)
        expect("a run whose (d) check is the tighter bound cuts the same corpus into more windows: a window failing "
               "(d) is split", (bound.driver_budget(tighter["limits"]) < bound.driver_budget(limits),
                                tighter["manifest"]["totals"]["windows"] > manifest["totals"]["windows"]), (True, True))
        expect("WP-08: S2 cuts every window reserving the output cap run.json declares for S3",
               golden(root, "cap48", reservation=48_000)["manifest"]["limits"]["reservation"], 48_000)
        one = make_entry({"pointer": "/message/content", "kind": "human", "text": "x" * 100}, 1, "in_window", 0)
        refused("control, unbounded: a packet that leaves no room for an entry is refused, never cut away",
                lambda: cut_windows({"transcript": "t", "version": 0, "version_sha": "ab" * 32, "redaction_version": projection.CURRENT},
                                    [one], {**limits, "overhead": bound.INPUT_BOUND - 10_000}), "WINDOW_UNBOUNDED")
        named("control, unbounded: under the production posture the transcript whose windows cannot be bounded is "
              "quarantined by name", [q["reason"] for q in golden(root, "nobound", overhead=bound.INPUT_BOUND - 10_000)["manifest"]["quarantined"]],
              "WINDOW_UNBOUNDED")
        # BA#1: cutting a window reads the SAME declaration the dispatcher admits against, and there is no
        # default - a window cut against an invented capacity is cut against nothing.
        refused("control, BA#1: a seat seats.json declares no context capacity for cuts no window",
                lambda: limits_of({"seats": {"S3": "claude:no-such-model/high"},
                                   "host_allowance": {"claude:no-such-model/high": {
                                       "allowance_tokens": 4000, "host_version": "2.1.304"}}, "output_caps": {"S3": 32_000}}),
                "CAPACITY_UNDECLARED")
        # ... and the cap itself: a window is cut against the cap the call will declare, never a constant
        refused("control, the ruling of 2026-10-22: a window cut with no declared output cap is refused",
                lambda: limits_of({"seats": {"S3": "claude:claude-sonnet-5-5/xhigh"},
                                   "host_allowance": {"claude:claude-sonnet-5-5/xhigh": {
                                       "allowance_tokens": 3886, "host_version": "2.1.304"}}}),
                "CAP_UNDECLARED")
        expect("the ruling of 2026-10-22: the reservation in the window's limits IS the declared cap",
               limits_of({"seats": {"S3": "claude:claude-sonnet-5-5/xhigh"},
                          "host_allowance": {"claude:claude-sonnet-5-5/xhigh": {
                              "allowance_tokens": 3886, "host_version": "2.1.304"}}, "output_caps": {"S3": 48_000}})["reservation"], 48_000)
        expect("BA#1: the S3 seat's capacity is the host-reported one seats.json declares, not a constant",
               limits_of({"seats": {"S3": "claude:claude-sonnet-5-5/xhigh"},
                          "host_allowance": {"claude:claude-sonnet-5-5/xhigh": {
                              "allowance_tokens": 3886, "host_version": "2.1.304"}}, "output_caps": {"S3": 32_000}})["capacity"],
               gate.seat_capacity("claude:claude-sonnet-5-5/xhigh", "2.1.304")[0])
        # BB#5: there is no way to hand the window builder a capacity. Both entry points resolve it through
        # the shared declaration reader, and a control that needs another one declares it in a seats fixture -
        # so no production path, and no test, can cut a window against a number no declaration carries.
        import inspect
        for entry in (limits_of, run):
            expect(f"BB#5: {entry.__name__} takes no capacity of its own",
                   "capacity" in inspect.signature(entry).parameters, False)
            # WP-08: nor a reservation - the cap is the declaration's, so no caller can cut against another one
            expect(f"WP-08: {entry.__name__} takes no output reservation of its own",
                   "reservation" in inspect.signature(entry).parameters, False)
        narrower = fx_seats(root, 150_000)
        expect("BB#5: a capacity a seats fixture declares is read by the same reader production reads",
               limits_of({"seats": {"S3": "claude:claude-sonnet-5-5/xhigh"},
                          "host_allowance": {"claude:claude-sonnet-5-5/xhigh": {
                              "allowance_tokens": 3886, "host_version": "2.1.304"}}, "output_caps": {"S3": 32_000}},
                         seats_path=narrower)["capacity"],
               gate.seat_capacity("claude:claude-sonnet-5-5/xhigh", "2.1.304", path=narrower)[0])
        refused("control, BB#5: a fixture that declares no capacity for the seat cuts no window either",
                lambda: limits_of({"seats": {"S3": "claude:claude-sonnet-5-5/xhigh"},
                                   "host_allowance": {"claude:claude-sonnet-5-5/xhigh": {
                                       "allowance_tokens": 3886, "host_version": "9.9.9"}}, "output_caps": {"S3": 32_000}},
                                  seats_path=narrower),
                "CAPACITY_UNDECLARED")
        refused("control, allowance: a declaration with no measured host allowance for the S3 seat cuts no window",
                lambda: limits_of({"seats": {"S3": "claude:x/high"}, "host_allowance": {}}), "ALLOWANCE_UNDECLARED")
        no_allowance = {**golden_run["run"], "host_allowance": {}}
        # P#7: one code for one refusal. S0 named it HOST_ALLOWANCE_MISSING and WP-06's contract names it
        # ALLOWANCE_UNDECLARED; two names for the same stop is a contract that cannot be read from either
        # side, so S0's name was changed to the plan's and the old one must be gone everywhere.
        named("control, allowance at S0: the declaration itself is refused before any window is cut, under the "
              "one code WP-06's contract names",
              declare.check_declaration(no_allowance), "ALLOWANCE_UNDECLARED")
        expect("control, allowance: the superseded S0 spelling is in no refusal of either stage",
               [line for line in declare.check_declaration(no_allowance) + limits_refusal(golden_run)
                if "HOST_ALLOWANCE_MISSING" in line], [])
        named("observed input: a view-window call within 120k is accepted", bound.check_observed(bound.INPUT_BOUND, True))
        named("control, observed input: a view-window call above 120k is a host change",
              bound.check_observed(bound.INPUT_BOUND + 1, True), "INPUT_BOUND_EXCEEDED")
        named("observed input: the same observation on a call that carries no view window is accepted, so the R "
              "authoring of §8.6 keeps its own section's contract", bound.check_observed(136_000, False))
        # The boundary itself is the DISPATCHER's: `runlib/bound.py` owns the rule and `dispatch.py`
        # admits, settles, stops and recovers against it (the seam record of 2026-10-22). What stays here
        # is what this module owns - the retained captures and what the rule says about them.
        #
        # P#4: the captures these controls settle are FILES, each pinned by sha256 in
        # `fixtures/captures.json`, and `retained_capture` refuses one whose bytes moved. A dictionary
        # written at the point of use carries whatever counts the control wanted, so it can be adjusted until
        # the control passes; a pinned file cannot. Two of the three are retained probe captures of
        # 2026-10-20, copied with their usage block alone and naming their source file and its sha256:
        # `within-bound` and the R-authoring call, whose observed input really is above the bound. An
        # R-authoring call is a non-window call by the contract of design 8.6, so the bound does not govern
        # it and no evidence about a view window is needed. `window-overrun` stays constructed and says so:
        # no retained capture of a VIEW-WINDOW call above the bound exists.
        within = retained_capture("within-bound")
        overrun = retained_capture("window-overrun")
        authoring = retained_capture("r-authoring")
        usage = within["usage"]
        expect("done-when 3(b): the retained view-window capture within 120k settles, and its observed input is "
               "input + cache creation + cache read as the capture itself records them",
               (observed_input_of(within), bound.check_observed(observed_input_of(within), True)),
               (usage["input_tokens"] + usage["cache_creation_input_tokens"] + usage["cache_read_input_tokens"], []))
        refused("control, P#4: a capture name no pin covers is refused rather than read",
                lambda: retained_capture("not-pinned"), "CAPTURE_UNPINNED")
        # R#6: the mismatch is planted in a COPY of the fixture tree, under this run's own directory, so the
        # control never writes to the checkout
        copied = run_dir / "captures-copy"
        shutil.copytree(CAPTURES.parent, copied, dirs_exist_ok=True)
        expect("control, R#6: the copied fixture tree is the same fixture - it reads clean before the plant",
               retained_capture("within-bound", root=copied)["call_id"], within["call_id"])
        moved = copied / "captures" / "within-bound.json"
        moved.write_bytes(moved.read_bytes().replace(b'"input_tokens"', b'"input_tokens" '))
        refused("control, P#4: a capture whose bytes moved from its pin is not the capture a control was "
                "written against", lambda: retained_capture("within-bound", root=copied), "CAPTURE_HASH_MISMATCH")
        expect("control, R#6: ... and the fixture in the checkout is untouched by that plant",
               retained_capture("within-bound")["call_id"], within["call_id"])
        refused("control, done-when 3(b): a capture missing a cache field is refused, never read as a smaller number",
                lambda: observed_input_of({"call_id": "r1/S3/t1/0b", "usage": {"input_tokens": 1}}),
                "CAPTURE_USAGE_MISSING")
        expect("done-when 3: a retained R-authoring capture above 120k read as a NON-window call is accepted, and "
               "the window rule is untouched",
               bound.check_observed(observed_input_of(authoring), authoring["view_window"]), [])
        expect("control, P#4: the two retained captures name the source file they were copied from, its "
               "sha256 and the extraction rule, so a reader can go back to the evidence",
               [cap["call_id"] for cap in (within, authoring)
                if not all(mark in cap["origin"] for mark in ("sanitised", "sha256", "Extraction rule"))], [])
        expect("control, P#4: the R-authoring capture's observed input really is above the view-window bound, "
               "which is what makes it the case the non-window contract is for",
               observed_input_of(authoring) > bound.INPUT_BOUND, True)
        expect("control, P#4: every capture fixture carries usage counts and nothing else - no prompt, no "
               "completion, no identifier",
               sorted({key for cap in (within, overrun, authoring) for key in cap
                       if key not in ("call_id", "view_window", "origin", "note", "usage")}), [])
        expect("control, P#4: ... and the fixture bytes themselves are swept for the shape and for an owner "
               "path, the pins with them",
               [path.name for path in sorted(pathlib.Path(CAPTURES).glob("*.json")) + [CAPTURES.parent / "captures.json"]
                for text in [path.read_text(encoding="utf-8")]
                if "sk-ant-" + "oat" in text or FX_HOME in text
                or any(owner in text for owner in ("/Users/kangmin", "/home/", "/Users/Shared"))], [])
        named("control, done-when 3(c): a view-window capture above 120k is INPUT_BOUND_EXCEEDED (this one is "
              "the synthetic fixture: no retained capture of that case exists)",
              bound.check_observed(observed_input_of(overrun), True), "INPUT_BOUND_EXCEEDED")
        expect("control, done-when 3(c): the excess record the dispatcher writes carries that observation and the "
               "declaration it ran under, which is what the recovery rule reads",
               {key: bound.committed(bound.excess(overrun["call_id"], observed_input_of(overrun),
                                                   records.now()), 2)[key]
                for key in ("code", "call_id", "observed", "declaration_seq")},
               {"code": "INPUT_BOUND_EXCEEDED", "call_id": overrun["call_id"],
                "observed": observed_input_of(overrun), "declaration_seq": 2})

        def owned_omission(record):
            """The omission id of a record's own clip - the row whose origin is `owned`. A record can also
            have overlap rows now, so an expansion of "the clipped middle" has to say which interval it
            means."""
            return next(m["omission_id"] for w in windows for m in w["omission_manifest"]
                        if m["record_id"] == record and m["origin"] == "owned")

        # ---- done-when 4: the omission manifest and the two completeness levels -------------------
        clip = next(m for w in windows for m in w["omission_manifest"] if m["record_id"] == rid("pending_clip"))
        expect("done-when 4, omission manifest: a clipped record is named with its size and its omitted span",
               (clip["record_id"], clip["size"], clip["omitted_span"]["start"] < clip["omitted_span"]["end"],
                clip["omitted_span"]["sha256"] == records.sha256_bytes(
                    texts[rid("pending_clip")][clip["omitted_span"]["start"]:clip["omitted_span"]["end"]].encode("utf-8"))),
               (rid("pending_clip"), len(texts[rid("pending_clip")]), True, True))
        # the accounting unit is the omitted INTERVAL, which is what the manifest's rows now are
        clipped_ids = sorted({m["omission_id"] for w in windows for m in w["omission_manifest"]})
        expanded = {i: "expand" for i in clipped_ids}
        # R#2: a record that lost SEVERAL intervals is not discharged by one expansion. The case the finding
        # names is a context entry truncated at OVERLAP_ITEM_BYTES and THEN omitted for a side's budget: the
        # first cut lost its tail, the omission lost what was left, and the two intervals together are the
        # record. Nonrepetitive text, so a hash cannot match the wrong interval by accident.
        def wordy(n, length):
            return "".join(f"{n}-{k} " for k in range(length))[:length]
        wide = []
        for n in range(1, 11):
            item = {"pointer": "/message/content", "kind": "assistant" if n % 2 else "tool_result",
                    "text": wordy(n, 2_000), "tool": None, "ts": fx_stamp(1, hour=n % 24)}
            wide.append(context_entry(item, n, "context", offset=n * 7))
        wide.append(synthetic(11, "human"))
        wide_window = make_window(base_probe, 1, wide, 10, 11, golden_run["limits"])
        wide_rows = wide_window["omission_manifest"]
        by_record = collections.defaultdict(list)
        for m in wide_rows:
            by_record[m["record_id"]].append(m["omission_id"])
        several = {r: ids for r, ids in by_record.items() if len(ids) > 1}
        expect("R#2: a context entry truncated at 700 characters and then omitted for the side's budget has "
               "lost TWO intervals, and both are in the manifest", bool(several), True)
        worst = sorted(several)[0] if several else None
        expect("R#2: ... whose intervals tile the record's 2000 characters exactly, in the block's own "
               "coordinates",
               coverage.normalize([[m["omitted_span"]["start"], m["omitted_span"]["end"]]
                                   for m in wide_rows if m["record_id"] == worst]) if worst else None,
               [[0, 2_000]])
        expect("R#2: ... and each interval's hash is the hash of its own characters, so one cannot discharge "
               "another",
               len({m["omitted_span"]["sha256"] for m in wide_rows if m["record_id"] == worst}) if worst else None, 2)
        expect("R#2: ... and every row carries a usable locator, which is what expansion seeks with",
               [m["omission_id"] for m in wide_rows if m["locator"]["offset"] is None], [])
        if several:
            record, ids = sorted(several.items())[0]
            wide_ids = sorted(m["omission_id"] for m in wide_rows)
            partial = [{"omission_id": i, "decision": "expand", "reason": "the first interval only"}
                       for i in ids[:1]]
            expect(f"R#2: one interval expanded does not discharge the {len(ids)} that record lost - the "
                   "decision set is short, so the session is not view complete",
                   completeness([True], wide_ids, partial, set(ids[:1]))["view_complete"], False)
            expect("R#2: ... and the decision set is named incomplete rather than accepted",
                   bool([e for e in check_decisions(wide_rows, {}, partial) if "SET_MISMATCH" in e]), True)
            every = [{"omission_id": i, "decision": "expand", "reason": "all of them"} for i in wide_ids]
            expect("R#2: ... while a decision for every interval is complete",
                   (completeness([True], wide_ids, every, set(wide_ids))["view_complete"],
                    check_decisions(wide_rows, {}, every)), (True, []))
        oid_of = {}
        for w in windows:
            for m in w["omission_manifest"]:
                oid_of.setdefault(m["record_id"], m["omission_id"])
        with_skip = [{"omission_id": i, "decision": "skip" if i == oid_of[rid("pair_plain")] else "expand"}
                     for i in clipped_ids]
        expect("done-when 4, completeness: a recorded skip leaves the session view complete and not source complete, "
               "and the skipped span is listed",
               completeness([True] * len(windows), clipped_ids, with_skip,
                            set(clipped_ids) - {oid_of[rid("pair_plain")]}),
               {"view_complete": True, "source_complete": False, "skipped": [oid_of[rid("pair_plain")]],
                "unresolved_versions": []})
        # M#8: the backlog of an older version was a count no consumer read. It is a state, and completeness
        # enforces it: unread ranges of a version this stage did not view are content nobody has looked at,
        # so the session is not source complete and no claim of absence may rest on it.
        held = unresolved_versions([{"version": 1, "window": "w-1", "unread": [[0, 4]]},
                                    {"version": 2, "window": "w-2", "unread": [[7, 9]]}], 2)
        expect("done-when 4: the backlog of another version is carried as the work it is, not as a count",
               held, [{"version": 1, "window": "w-1", "unread": [[0, 4]]}])
        expect("done-when 4, completeness: a session with an unresolved earlier version is view complete and NOT "
               "source complete, and the version is named",
               completeness([True] * len(windows), clipped_ids,
                            [{"omission_id": i, "decision": d} for i, d in expanded.items()], set(clipped_ids),
                            unresolved=held),
               {"view_complete": True, "source_complete": True and False, "skipped": [], "unresolved_versions": [1]})
        expect("done-when 6: and no claim of absence may rest on it, because its basis is not source",
               absence_claim_allowed(coverage_basis(
                   {"sources": [{"accounted": True, "directory_present": True}],
                    "sessions": [{"status": "read_complete", "unprocessed": False, "view_complete": True,
                                  "source_complete": False}]})), False)
        expect("done-when 4: views.json carries the unresolved state per transcript and in its totals, and the "
               "fixture's own transcripts have none",
               ({t["name"]: t["unresolved_versions"] for t in manifest["transcripts"] if t["unresolved_versions"]},
                manifest["totals"]["unresolved_versions"]), ({}, 0))
        expect("done-when 4, completeness: a clipped record with neither an executed expansion nor a skip is not view "
               "complete", completeness([True] * len(windows), clipped_ids,
                                         [{"record_id": i, "decision": "expand"} for i in clipped_ids], set())["view_complete"], False)
        expect("done-when 4, completeness: a window that did not pass the gate is not view complete",
               completeness([True, False], clipped_ids, with_skip, set(clipped_ids))["view_complete"], False)
        # P#6: every branch of the forcing predicate, each as a case of its own with its own expected answer.
        # The golden run exercises one shape - a pending event before every clipped record with a later human
        # turn - and no call of it anywhere passed a search hit, so the search branch and the boundary cases
        # were covered by a label and nothing else.
        # `line` is 1-based and the predicate works in 0-based indexes, so each case names the INDEX it means
        def forcing(clipped_at, humans_at, events=(), hits=()):
            clipped = [{"record_id": f"r{index}", "line": index + 1} for index in clipped_at]
            return forced_records(clipped, humans_at, events, hits)
        for label, args, want in (
                ("a clipped record before the pending event is not forced",
                 ([3], [9], [5]), {}),
                ("the clipped record at the event is forced by the event",
                 ([5], [9], [5]), {"r5": "pending_event"}),
                ("one between the event and the next human turn is forced",
                 ([7], [9], [5]), {"r7": "pending_event"}),
                ("one at the next human turn itself is not forced, because the stretch ends there",
                 ([9], [9], [5]), {}),
                ("one after the next human turn is not forced",
                 ([11], [9], [5]), {}),
                ("with no later human turn at all, everything from the event on is forced",
                 ([7, 11], [2], [5]), {"r7": "pending_event", "r11": "pending_event"}),
                ("a search match forces a record no event covers",
                 ([11], [9], [5], ["r11"]), {"r11": "search_match"}),
                ("a search match alone forces, with no pending event declared",
                 ([4], [9], (), ["r4"]), {"r4": "search_match"}),
                ("when both reasons apply the event is the one recorded, because it is the stronger claim",
                 ([7], [9], [5], ["r7"]), {"r7": "pending_event"}),
                ("two events each force their own stretch",
                 ([3, 7], [5, 9], [2, 6]), {"r3": "pending_event", "r7": "pending_event"}),
                # the event index IS a human turn: the stretch runs from it to the NEXT human turn, not to
                # itself, which is the difference between the two sides of the search for that turn
                ("an event that falls on a human turn forces up to the following one",
                 ([5, 7, 11], [5, 9], [5]), {"r5": "pending_event", "r7": "pending_event"}),
                ("nothing is forced when neither reason applies",
                 ([3], [9], (), ()), {})):
            expect(f"done-when 5, forcing branch: {label}", forcing(*args), want)
        forced = forced_records([{"record_id": m["record_id"], "line": m["line"]} for w in windows for m in w["omission_manifest"]],
                                records.read_json(run_dir / main["sequence"])["human_lines"],
                                [e["first_record"] for e in golden_run["state"]["pending_events"]])
        manifest_rows = [m for w in windows for m in w["omission_manifest"]]
        named("done-when 5, forced: a decision for each omitted interval, with a reason, and no forced record skipped",
              check_decisions(manifest_rows, forced, [{"record_id": i, "decision": "expand", "reason": "the gap may hold the outcome"}
                                                    for i in clipped_ids]))
        named("control, forced: a clipped record with no decision is named",
              check_decisions(clipped_ids, forced, [{"record_id": clipped_ids[0], "decision": "skip", "reason": "small"}]),
              "SET_MISMATCH")
        named("control, forced: a decision without a reason is named",
              check_decisions(clipped_ids, forced, [{"record_id": i, "decision": "expand", "reason": " " if i == clipped_ids[0] else "r"}
                                                    for i in clipped_ids]), "EXPANSION_DECISION_INVALID")
        named("control, forced: a forced record answered with skip is named, whichever interval of it the "
              "decision was about",
              check_decisions(manifest_rows, forced,
                              [{"omission_id": i, "decision": "skip", "reason": "r"} for i in clipped_ids]),
              "EXPANSION_SKIPPED")

        # ---- done-when 5: the mandatory expansion predicate, by code ------------------------------
        expect("done-when 5, forced: a clipped record between a pending event and the next human turn is forced, and "
               "one after that human turn is not",
               (forced.get(rid("pending_clip")), rid("late_clip") in forced), ("pending_event", False))
        hits = forced_by_search(run_dir, name, [FX_TERM])
        expect("done-when 5, forced: the full-source search forces every clipped record it matches, clipped spans "
               "included", hits, {rid("pair_term"): "search_match"})
        expansion = expand(run_dir, "r1/S3/t1/2", name, rid("pending_clip"), "the outcome may be in the gap", "pending_event",
                             omission=owned_omission(rid("pending_clip")))
        expect("done-when 5: an expansion is additional windows under the same bound and span mapping, and one larger "
               "than a window is itself split",
               (len(expansion) > 1, [w["bound_ok"] for w in expansion],
                coverage.normalize([s["block"] for w in expansion for r in w["records"] for s in r["segments"]])),
               (True, [True] * len(expansion), [[clip["omitted_span"]["start"], clip["omitted_span"]["end"]]]))
        expect("the expansion's text is the omitted characters, and the decision is logged with its reason",
               ("".join(r["text"] for w in expansion for r in w["records"])
                == texts[rid("pending_clip")][clip["omitted_span"]["start"]:clip["omitted_span"]["end"]],
                [(d["locator"]["record_id"], d["decision"], d["forced_by"]) for d in
                 (json.loads(l) for l in (run_dir / "expansions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())]),
               (True, [(rid("pending_clip"), "expand", "pending_event")]))
        refused("control: an expansion of a record no window lists as clipped is refused",
                lambda: expand(run_dir, "r1/S3/t1/3", name, "99/message/content", "why not"), "EXPANSION_UNKNOWN")
        refused("control: a skip recorded against a forced record is refused",
                lambda: record_decision(run_dir, "r1/S3/t1/4", name, rid("pending_clip"), "skip", "too long", "pending_event"),
                "EXPANSION_SKIPPED")
        refused("control: a decision that is neither expand nor skip, or carries no reason, is refused",
                lambda: record_decision(run_dir, "r1/S3/t1/5", name, rid("late_clip"), "expand", ""),
                "EXPANSION_DECISION_INVALID")
        projected = run_dir / main["redacted"]
        kept = projected.read_bytes()
        projected.write_bytes(kept.replace(b"middle line 004", b"middle line 014"))
        refused("control: an expansion whose omitted characters no longer hash to the manifest's span is refused",
                lambda: expand(run_dir, "r1/S3/t1/6", name, rid("pending_clip"), "again",
                                       omission=owned_omission(rid("pending_clip"))), "EXPANSION_SOURCE_DRIFT")
        projected.write_bytes(kept)

        # M#5: the projection's version is enforced where a stored artifact is CONSUMED, not only where a
        # quote is verified. Positive control first - every expansion above read these same files.
        seq_path = run_dir / "views" / name / "sequence.json"
        seq_kept = seq_path.read_bytes()
        seq_path.write_bytes(seq_kept.replace(f'"redaction_version": "{projection.CURRENT}"'.encode(),
                                              b'"redaction_version": "r1"'))
        refused("control: a sequence document built under another projection version is refused",
                lambda: sequence_doc(run_dir, name), "REDACTION_VERSION_MISMATCH")
        seq_path.write_bytes(seq_kept)
        win_path = sorted((run_dir / "views" / name).glob("[0-9]*.json"))[0]
        win_kept = win_path.read_bytes()
        win_path.write_bytes(win_kept.replace(f'"redaction_version": "{projection.CURRENT}"'.encode(),
                                              b'"redaction_version": "r1"'))
        refused("control: a window built under another projection version is refused where it is read",
                lambda: window_doc(run_dir, name, win_path), "REDACTION_VERSION_MISMATCH")
        refused("control: an expansion that must read such a window is refused by the same name",
                lambda: expand(run_dir, "r1/S3/t1/8", name, rid("late_clip"), "under a stale window",
                                       omission=owned_omission(rid("late_clip"))),
                "REDACTION_VERSION_MISMATCH")
        # P#5: the rendering a model sees is its own boundary. It takes a window from any caller, so a
        # caller that skipped the checked readers must still not be able to put a stale window in a packet.
        stale_window = {**records.read_json(win_path), "redaction_version": "r1"}
        refused("control, P#5: a stale window rendered for a model is refused at the rendering itself",
                lambda: render_window(stale_window), "REDACTION_VERSION_MISMATCH")
        refused("control, P#5: and the search that reads every window of a view reads them through the checked "
                "reader", lambda: forced_by_search(run_dir, name, [FX_TERM]), "REDACTION_VERSION_MISMATCH")
        win_path.write_bytes(win_kept)
        index_path = run_dir / main["index"]
        index_kept = index_path.read_bytes()
        index_path.write_bytes(index_kept.replace(f'"redaction_version":"{projection.CURRENT}"'.encode(),
                                                 b'"redaction_version":"r1"'))
        def load_stale_index():
            try:
                search.load(index_path)
            except search.SearchError as exc:
                return f"refused: {exc}"
            return "loaded"
        expect("control: an index built under another projection version is refused where it is read",
               load_stale_index().startswith("refused: REDACTION_VERSION_MISMATCH"), True)
        index_path.write_bytes(index_kept)

        # ---- done-when 6: the F-O9-04 pair ------------------------------------------------------
        pair = fx_entries(windows)
        expect("done-when 6: the pair's visible head and tail are the same bytes, and the manifest tells them apart by "
               "the hash of what each hides",
               (pair[rid("pair_plain")]["text"] == pair[rid("pair_term")]["text"],
                pair[rid("pair_plain")]["clipped"]["omitted_span"]["sha256"]
                != pair[rid("pair_term")]["clipped"]["omitted_span"]["sha256"]), (True, True))
        expect("done-when 6: the search misses the paraphrased occasion, so nothing forces its expansion",
               (rid("pair_plain") in forced_by_search(run_dir, name, [FX_TERM]), rid("pair_plain") in forced), (False, False))
        # M#10: the scope is DERIVED from the skip that was actually recorded, not asserted. The control used
        # to construct `source_complete: False` by hand, so it would have passed with the skip lost before
        # completeness was ever computed - it assumed the result it claimed to prove.
        rows_by_oid = {m["omission_id"]: m for w in windows for m in w["omission_manifest"]}
        record_decision(run_dir, "r1/S3/t1/9", name, rid("pair_plain"), "skip",
                        "the paraphrased occasion is not worth the window",
                        omission=oid_of[rid("pair_plain")])
        for other in clipped_ids:
            if other != oid_of[rid("pair_plain")]:
                row = rows_by_oid[other]
                record_decision(run_dir, f"r1/S3/t1/9-{other}", name, row["record_id"], "expand", "read whole",
                                "pending_event" if row["record_id"] == rid("pending_clip") else "none",
                                omission=other)
        recorded = [json.loads(l) for l in (run_dir / "expansions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        mine = [d for d in recorded if d["locator"]["transcript"] == name and d["call_id"].startswith("r1/S3/t1/9")]
        derived = completeness([True] * len(windows), clipped_ids,
                               [{"omission_id": d["locator"]["omission_id"], "decision": d["decision"]} for d in mine],
                               {d["locator"]["omission_id"] for d in mine if d["decision"] == "expand"},
                               unresolved=unresolved_versions(golden_run["main"].get("unresolved_versions", []), 1))
        expect("done-when 6: the skip recorded for the paraphrased member is what makes the session view complete "
               "and not source complete, and it is the one span listed",
               (derived["view_complete"], derived["source_complete"], derived["skipped"]),
               (True, False, [oid_of[rid("pair_plain")]]))
        scope = {"sources": [{"accounted": True, "directory_present": True}],
                 "sessions": [{"status": "read_complete", "unprocessed": False,
                               "view_complete": derived["view_complete"], "source_complete": derived["source_complete"]}]}
        expect("done-when 6, basis: S3's skip leaves the session at basis view, and a claim of absence over it is "
               "refused - it stays pending",
               (coverage_basis(scope), absence_claim_allowed(coverage_basis(scope))), ("view", False))
        # the mutation M#10 asks for: the skip is lost before completeness is computed, and the chain must break
        without = [d for d in mine if d["locator"]["omission_id"] != oid_of[rid("pair_plain")]]
        lost = completeness([True] * len(windows), clipped_ids,
                            [{"omission_id": d["locator"]["omission_id"], "decision": d["decision"]} for d in without],
                            {d["locator"]["omission_id"] for d in without if d["decision"] == "expand"})
        lost_scope = {**scope, "sessions": [{"status": "read_complete", "unprocessed": False,
                                             "view_complete": lost["view_complete"],
                                             "source_complete": lost["source_complete"]}]}
        expect("control, done-when 6: with the skip lost, the session is not even view complete and the basis is "
               "incomplete - so absence stays pending for a different reason, and the link is what carried it",
               (lost["view_complete"], lost["source_complete"], lost["skipped"],
                coverage_basis(lost_scope), absence_claim_allowed(coverage_basis(lost_scope))),
               (False, False, [], "incomplete", False))
        # R#1/R#2/R#5: expansion against REAL generated overlap manifests. The whole stage is run over a
        # transcript of long human and assistant turns with tool traffic between them, which is the shape
        # whose overlap is really cut and whose side budget really runs out. The rows below are the stage's
        # own; nothing here writes a manifest by hand, which is how the previous control passed while
        # production wrote `locator.offset: None` and expansion died on it.
        long_run = golden(root, "long", main_records=fx_long_records)
        long_name, long_dir = long_run["main"]["name"], long_run["run_dir"]
        long_rows = [m for f in long_run["main"]["windows"]
                     for m in window_doc(long_dir, long_name, long_dir / f["path"])["omission_manifest"]]
        expect("R#1: the long-turn run really does omit overlap content, so these controls judge something",
               bool(long_rows), True)
        expect("R#1: every generated omission row carries a usable locator, which expansion seeks with",
               [m["omission_id"] for m in long_rows if m["locator"]["offset"] is None], [])
        # R#1 at the unit: the locator is on EVERY entry, owned or context, and a split span keeps it. The
        # rows above are all context today - an owned entry shown in a neighbour's overlap is not cut at the
        # moment, so the generated rows cannot see this - and the defect was exactly an owned message's
        # missing locator.
        long_seq = records.read_json(long_dir / long_run["main"]["sequence"])["sequence"]
        own_entries = [e for e in build_sequence(long_dir / long_run["main"]["redacted"],
                                                 {r["line"] - 1 for r in long_seq if r["owned"]},
                                                 lambda _l: "in_window", search.Index())[0]]
        expect("R#1: every sequence entry carries its projection offset, owned and context alike",
               [e["record_id"] for e in own_entries if e.get("offset") is None], [])
        wide_owned = next(e for e in own_entries if e["owned"] and len(e["text"]) > 1_000)
        expect("R#1: ... and a split span keeps the locator of the record it came from",
               [piece.get("offset") for piece in split_entry(wide_owned, 900)],
               [wide_owned.get("offset")] * len(split_entry(wide_owned, 900)))
        # R#2 at the unit: a view range of a SPLIT span maps to the block's own coordinates, not the span's.
        # Expansion reads these numbers as offsets into the block, so a span-local interval names characters
        # that were never omitted - and its hash can only disagree.
        piece = split_entry(wide_owned, 900)[1]
        mapped = omitted_intervals(piece, 100, len(piece["text"]))
        expect("R#2: the omitted interval of a split span is in the BLOCK's coordinates, so it starts past "
               "the span's own beginning",
               (bool(mapped), mapped[0]["start"] > 100 if mapped else None), (True, True))
        expect("R#2: ... and its hash is the hash of the characters it names, read from the block itself",
               [i["sha256"] for i in mapped],
               [records.sha256_bytes(wide_owned["text"][i["start"]:i["end"]].encode("utf-8")) for i in mapped])
        clip_entry = next((e for e in own_entries if "clipped" in e), None)
        if clip_entry is None:
            checks.failures.append("the long run holds no clipped record, so the clipped-coordinate control "
                                   "would pass over nothing")
        else:
            across = omitted_intervals(clip_entry, 0, len(clip_entry["text"]))
            expect("R#2: a clipped record's view elides its middle, so a view range across the elision maps "
                   "to SEVERAL block intervals rather than one",
                   len(across) == len(clip_entry["segments"]) and len(across) > 1, True)
        # ... and the invariant over EVERY generated row: the characters the block really holds at the row's
        # interval are the characters the row's hash names
        long_texts = projection_texts(long_dir, long_run["main"]["redacted"])
        wrong = [m["omission_id"] for m in long_rows
                 if records.sha256_bytes(long_texts.get(m["record_id"], "")
                                         [m["omitted_span"]["start"]:m["omitted_span"]["end"]].encode("utf-8"))
                 != m["omitted_span"]["sha256"]]
        expect("R#2: every generated omission row's interval, read against the projected block itself, holds "
               "the characters its hash names", wrong, [])
        for row in long_rows[:3]:
            back = expand(long_dir, "r1/S3/long/1", long_name, row["record_id"],
                          "the overlap omitted it and a claim needs it", omission=row["omission_id"])
            text = "".join(r["text"] for w in back for r in w["records"])
            expect(f"R#1: the omitted interval {row['omitted_span']['start']}-{row['omitted_span']['end']} of "
                   f"{row['record_id']} is expanded from the generated manifest, and its characters hash to "
                   "the interval the manifest named",
                   records.sha256_bytes(text.encode("utf-8")), row["omitted_span"]["sha256"])
        # ... a record that lost several intervals may not be expanded without saying which
        multi = sorted({m["record_id"] for m in long_rows
                        if sum(1 for x in long_rows if x["record_id"] == m["record_id"]) > 1})
        expect("R#2: the long-turn run has records that lost several intervals, so the next control judges "
               "something", bool(multi), True)
        if multi:
            refused("R#2: expanding such a record without naming the interval is refused, because expanding "
                    "one of them discharges only that one",
                    lambda: expand(long_dir, "r1/S3/long/2", long_name, multi[0], "all of it"),
                    "EXPANSION_AMBIGUOUS")
        # V#1: every DISPLAYED cut of a generated window is in the manifest, hashed against the projected
        # block, expandable, and required for completeness. A displayed cut is the easy one to lose - the
        # entry is still shown, so nothing looks missing - and a 2000-character context entry shown as 700
        # used to contribute no row at all.
        displayed = [(w_n, e) for w_n, w in [(f["path"], window_doc(long_dir, long_name, long_dir / f["path"]))
                                             for f in long_run["main"]["windows"]]
                     for side in ("prev", "next") for e in w["overlap"][side] if e.get("omitted_intervals")]
        expect("V#1: the long-turn run really shows entries whose text was cut, so these controls judge "
               "something", bool(displayed), True)
        if displayed:
            long_texts_v1 = projection_texts(long_dir, long_run["main"]["redacted"])
            manifested = {m["omission_id"] for m in long_rows}
            expect("V#1: every interval a DISPLAYED overlap entry has lost is in the omission manifest",
                   sorted({omission_id(e["record_id"], i["start"], i["end"])
                           for _w, e in displayed for i in e["omitted_intervals"]} - manifested), [])
            expect("V#1: ... and each of those intervals hashes to the characters the projected block holds there",
                   [e["record_id"] for _w, e in displayed for i in e["omitted_intervals"]
                    if records.sha256_bytes(long_texts_v1.get(e["record_id"], "")[i["start"]:i["end"]].encode("utf-8"))
                    != i["sha256"]], [])
            shown_row = next(m for m in long_rows
                             if m["omission_id"] in {omission_id(e["record_id"], i["start"], i["end"])
                                                     for _w, e in displayed for i in e["omitted_intervals"]})
            back = expand(long_dir, "r1/S3/long/displayed", long_name, shown_row["record_id"],
                          "the overlap showed only the head of it", omission=shown_row["omission_id"])
            expect("V#1: ... and a displayed entry's lost tail is expandable, its characters hashing to the row",
                   records.sha256_bytes("".join(r["text"] for w in back for r in w["records"]).encode("utf-8")),
                   shown_row["omitted_span"]["sha256"])
            expect("V#1: ... and completeness requires a decision about it, so a view that ignores it is not "
                   "complete",
                   completeness([True], sorted(manifested),
                                [{"omission_id": i, "decision": "expand", "reason": "r"}
                                 for i in sorted(manifested) if i != shown_row["omission_id"]],
                                manifested - {shown_row["omission_id"]})["view_complete"], False)
        # Q#1: `size` means the record's own length in every row, whatever the row is about. The projected
        # block is the authority, so each row is read against it - and the three shapes that got it wrong
        # are each present: a context entry capped before it got here, a clipped result whose view elides a
        # middle, and a split message whose entry is one span of it.
        block_len = {rid: len(text) for rid, text in long_texts_v1.items()} if displayed else {}
        if not displayed:
            block_len = {rid: len(text) for rid, text
                         in projection_texts(long_dir, long_run["main"]["redacted"]).items()}
        wrong_size = [(m["record_id"], m["size"], block_len.get(m["record_id"]))
                      for m in long_rows if m["size"] != block_len.get(m["record_id"])]
        expect("Q#1: every generated omission row's size is the full projected block's length, not a span's "
               "end and not the length of a text already capped", wrong_size, [])
        # Z#2: a record whose unsplit text is long is not a split record. The split ones are generated
        # here - a run whose packet overhead leaves a small window, so `cut_windows` really divides the long
        # messages into spans - and their span metadata is asserted before any size claim rests on them.
        split_records = [r for w in windows for r in w["records"] if "span" in r]
        expect("Z#2: the fixture really splits a message into spans, so the claims below judge split entries",
               bool(split_records), True)
        expect("Z#2: every split entry carries its place in the message - index, count and its own segments",
               [eid(r) for r in split_records
                if not (r["span"]["index"] >= 1 and r["span"]["of"] > 1 and r["segments"])], [])
        by_split = {rid: [r for r in split_records if r["record_id"] == rid]
                    for rid in {r["record_id"] for r in split_records}}
        expect("Z#2: ... and the spans of one message tile it, so no row derived from one rests on a guess",
               [rid for rid, parts in sorted(by_split.items())
                if coverage.normalize([list(seg["block"]) for part in parts for seg in part["segments"]]
                                      + [list(gap) for part in parts
                                         for gap in (part.get("clipped") or {}).get("gaps", [])])
                != [[0, parts[0]["size"]]]], [])
        split_rows = [m for w in windows for m in w["omission_manifest"] if m["record_id"] in by_split]
        expect("Z#2: the manifest really holds rows about those split messages", bool(split_rows), True)
        expect("Z#2: every displayed and omitted row derived from a split message reports the FULL projected "
               "block's length as its size, never a span's",
               [(m["record_id"], m["size"], len(texts.get(m["record_id"], "")))
                for m in split_rows if m["size"] != len(texts.get(m["record_id"], ""))], [])
        expect("Q#1: and so does every other row of this run, whatever it is about",
               [(m["record_id"], m["size"]) for w in windows for m in w["omission_manifest"]
                if m["size"] != len(texts.get(m["record_id"], ""))], [])
        # ... and the same for a SPLIT OWNED message shown in a neighbour's overlap, whose intervals are the
        # block's and not the span's
        split_owned = next((e for e in own_entries if e["owned"] and len(e["text"]) > OVERLAP_ITEM_BYTES * 2), None)
        if split_owned is None:
            checks.failures.append("the long run holds no owned entry long enough to be cut by the overlap, so "
                                   "the split-message control would pass over nothing")
        else:
            # the LAST span whose own text is longer than the overlap's item cap: that is the one the
            # overlap really cuts, and the one whose coordinates are not the block's unless they are mapped
            spans = split_entry(split_owned, 1_200)
            piece = next(x for x in reversed(spans) if len(x["text"]) > OVERLAP_ITEM_BYTES)
            shown_piece = overlap_of(piece)
            expect("V#1: a split owned message shown in an overlap reports its cut in the BLOCK's coordinates, "
                   "past the span's own beginning",
                   (bool(shown_piece.get("omitted_intervals")),
                    shown_piece["omitted_intervals"][0]["start"] > OVERLAP_ITEM_BYTES
                    if shown_piece.get("omitted_intervals") else None), (True, True))
            expect("V#1: ... and that interval hashes to the characters the block holds there",
                   [i["sha256"] for i in shown_piece.get("omitted_intervals") or []],
                   [records.sha256_bytes(split_owned["text"][i["start"]:i["end"]].encode("utf-8"))
                    for i in shown_piece.get("omitted_intervals") or []])
        # R#5: two expansions under ONE call id, both complete and both readable
        pair_rows = [m for m in long_rows if m["record_id"] != long_rows[0]["record_id"]][:1] + long_rows[:1]
        sets = []
        for row in pair_rows:
            got = expand(long_dir, "r1/S3/long/same-call", long_name, row["record_id"],
                         "both under one call", omission=row["omission_id"])
            sets.append((row, got))
        written = sorted((long_dir / "views" / long_name).glob("expansion-r1_S3_long_same-call-*.json"))
        expect("R#5: two expansions under one call id leave two independent artifact sets, not one overwriting "
               "the other", len(written), sum(len(got) for _row, got in sets))
        for row, got in sets:
            tag = re.sub(r"[^A-Za-z0-9._-]", "_", row["omission_id"])[-24:]
            mine = sorted((long_dir / "views" / long_name).glob(f"expansion-r1_S3_long_same-call-{tag}-*.json"))
            expect(f"R#5: ... and each set is readable on its own and carries its own record",
                   ([window_doc(long_dir, long_name, path)["expansion_of"] for path in mine],
                    len(mine)), ([row["record_id"]] * len(got), len(got)))
        decided = [json.loads(l) for l in (long_dir / "expansions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        expect("R#5: ... and each decision names the omission it was about, not only the record",
               [d for d in decided if not d["locator"].get("omission_id")], [])
        found = expand(run_dir, "r1/S3/t1/7", name, rid("pair_term"), "the search matched inside the gap", "search_match",
                       omission=owned_omission(rid("pair_term")))
        expect("done-when 6, control: the same occasion written with a retrieval term is matched, forced, expanded, and "
               "found", FX_HIDDEN_TERM in "".join(r["text"] for w in found for r in w["records"]), True)

        # ---- the coverage basis of §5.4, in the order the design checks it ------------------------
        expect("basis: every session source complete is basis source, and absence may rest on it",
               (coverage_basis({**scope, "sessions": [{"status": "read_complete", "unprocessed": False,
                                                       "view_complete": True, "source_complete": True}]}),
                absence_claim_allowed("source")), ("source", True))
        for label, change in (("a source that is not accounted", {"sources": [{"accounted": False, "directory_present": True}]}),
                              ("a source directory that is missing", {"sources": [{"accounted": True, "directory_present": False}]}),
                              ("a deferred session", {"sessions": [{"status": "deferred", "unprocessed": False,
                                                                    "view_complete": True, "source_complete": True}]}),
                              ("a session with records this window owns and has not processed",
                               {"sessions": [{"status": "read_complete", "unprocessed": True,
                                              "view_complete": True, "source_complete": True}]})):
            expect(f"basis: {label} makes the basis incomplete", coverage_basis({**scope, **change}), "incomplete")

        # ---- done-when 1: the copy is where tampering is caught ----------------------------------
        refused("control: a copy whose bytes the census did not read is refused",
                lambda: copy_version(root / "changed", golden_run["paths"]["main"], None, {"sha": "00" * 32, "record_count": main["records"]}),
                "SOURCE_CHANGED")
        quarantined = golden(root, "changed-run", overhead=100_000, census_sha="00" * 32)
        named("control: under the production posture the session whose source changed is quarantined by name and the "
              "run goes on", [q["reason"] for q in quarantined["manifest"]["quarantined"]], "SOURCE_CHANGED")
        planted = root / "tampered" / "sources"
        planted.mkdir(parents=True)
        (planted / f"{main['version_sha']}.jsonl").write_text("not the bytes this name claims\n", encoding="utf-8")
        refused("control: an existing copy that does not hash to its own name is refused",
                lambda: copy_version(root / "tampered", golden_run["paths"]["main"], None, {"sha": main["version_sha"], "record_count": main["records"]}),
                "SOURCE_TAMPERED")
        refused("control: a source that cannot be read is named, never silently skipped",
                lambda: copy_version(run_dir, root / "nothing-here.jsonl", None), "SOURCE_UNREADABLE")
        # D-20261103-8facee: the version S2 copies is the census's complete-line prefix. The host may append after the census
        # - lines, or the end of a line it was still writing - and that is the next run's; changed lines are not.
        version = {"sha": main["version_sha"], "record_count": main["records"]}
        original = golden_run["paths"]["main"].read_bytes()

        def copied(where, source):
            """The copy's `(run-relative path, sha256)`, or the refusal: a control reads either, never a traceback."""
            try:
                return copy_version(root / where, source, None, version)
            except Refused as exc:
                return exc
        appended = root / "appended" / "t1.jsonl"
        appended.parent.mkdir()
        appended.write_bytes(original + b'{"type": "user", "timestamp": "2026-10-03T23:00:00.000Z", "message": {"role": "user", "content": "later"}}\n')
        grown = copied("appended-run", appended)
        expect("8facee: a transcript the host appended to after the census is copied as the census read it",
               (grown[1], (root / "appended-run" / grown[0]).read_bytes() == original) if isinstance(grown, tuple) else grown,
               (main["version_sha"], True))
        writing = root / "appended" / "writing.jsonl"
        writing.write_bytes(original + b'{"type": "user", "timestamp": "2026-10-03T23:00:00.000Z", "message": {"role": "user", "content": "lat')
        writing_copy = copied("writing-run", writing)
        expect("8facee: a line the host is still writing is no record: the copy is the census's lines",
               writing_copy[1] if isinstance(writing_copy, tuple) else writing_copy, main["version_sha"])
        with writing.open("ab") as handle:
            handle.write(b'er"}}\n')
        completed_copy = copied("completed-run", writing)
        expect("8facee: a line still being written at the census and completed since is not copied either",
               completed_copy[1] if isinstance(completed_copy, tuple) else completed_copy, main["version_sha"])
        rewritten = root / "appended" / "rewritten.jsonl"
        rewritten.write_bytes(original.replace(b"2026-10-0", b"2026-11-0", 1))
        refused("8facee: a transcript whose census lines changed is SOURCE_CHANGED",
                lambda: copy_version(root / "rewritten-run", rewritten, None, version), "SOURCE_CHANGED", "rewritten or truncated")
        truncated = root / "appended" / "truncated.jsonl"
        truncated.write_bytes(b"".join(original.splitlines(keepends=True)[:-1]))
        refused("8facee: a transcript shorter than the census read is SOURCE_CHANGED",
                lambda: copy_version(root / "truncated-run", truncated, None, version), "SOURCE_CHANGED", "rewritten or truncated")
        # D-20261103-85f3e8: S2 reads a unit - the root and every member at any depth that owes the window something
        _unit_dir, unit_ids, unit_manifest = golden_unit(root, "unit")
        expect("85f3e8: S2 reads each member of the unit that owes the window something, at any depth, as part of the root's unit",
               sorted((t["transcript"], t["unit"], t["kind"]) for t in unit_manifest["transcripts"])
               if isinstance(unit_manifest, dict) else repr(unit_manifest),
               sorted([(unit_ids["root"], unit_ids["root"], "session"), (unit_ids["d1"], unit_ids["root"], "child"),
                       (unit_ids["d2"], unit_ids["root"], "child")]))
        _changed_dir, _ids, changed_manifest = golden_unit(root, "unit-changed", plant="changed")
        expect("85f3e8: under the production posture a member whose source changed quarantines its whole unit",
               sorted((q["id"], "SOURCE_CHANGED" in q["reason"], q["because"]) for q in changed_manifest["quarantined"])
               if isinstance(changed_manifest, dict) else repr(changed_manifest),
               sorted([(unit_ids["d2"], True, None), (unit_ids["root"], False, unit_ids["d2"]), (unit_ids["d1"], False, unit_ids["d2"])]))
        expect("r1 #4: the views made for a unit before one of its members failed are quarantined with it, not published",
               ([t["transcript"] for t in changed_manifest["transcripts"]], changed_manifest["totals"]["files"])
               if isinstance(changed_manifest, dict) else repr(changed_manifest), ([], 0))
        _mid_dir, _ids, mid_manifest = golden_unit(root, "unit-mid", plant="mid_unreadable")
        expect("r1 #2: a member S1 could not read leaves the unit, and the member below it is still read as part of the root's unit",
               sorted((t["transcript"], t["unit"], t["kind"]) for t in mid_manifest["transcripts"])
               if isinstance(mid_manifest, dict) else repr(mid_manifest),
               sorted([(unit_ids["root"], unit_ids["root"], "session"), (unit_ids["d2"], unit_ids["root"], "child")]))
        _idle_dir, _ids, idle = golden_unit(root, "unit-idle", plant="idle")
        named("85f3e8: an eligible root whose unit owes the window nothing contradicts S1 and is refused by name",
              [str(idle)] if isinstance(idle, Exception) else [], "SET_MISMATCH S2", unit_ids["root"])
        # D-20261103-a7128a: S2 reads each file of a thread written in several that owes the window something, as a
        # transcript of its own under its coverage key, and no other
        for label, owns, read in (("only its first file", ([[0, 3]], []), [0]), ("only its last file", ([], [[0, 3]]), [1]),
                                  ("both its files", ([[0, 3]], [[0, 3]]), [0, 1])):
            split_keys, split = golden_split(root, f"split-{read}", owns)
            expect(f"a7128a: a thread whose window lies in {label} has that file copied and viewed, under its own key",
                   sorted((t["transcript"], t["session"], t["segment"]) for t in split["transcripts"])
                   if isinstance(split, dict) else repr(split),
                   sorted((split_keys[n], split_keys[n].split("@")[0], split_keys[n].split("@")[1]) for n in read))
            if read == [0, 1]:
                expect("r2: a thread viewed in both its files is one session in two files, in the totals and in the report",
                       ((split["totals"]["sessions"], split["totals"]["children"], split["totals"]["files"]), report_lines(split)[0].split(": ", 1)[1].split(",")[0])
                       if isinstance(split, dict) else repr(split), ((1, 0, 2), "1 sessions and 0 children in 2 files"))
        for base, why in (("empty", "an empty base"), ("older", "a base that saw fewer records")):
            split_keys, targeted = golden_split(root, f"targeted-{base}", ([[0, 3]], [[0, 3]]), base=base)
            expect(f"r1 #3: a targeted run's views copy the version its census read, over {why}",
                   (sorted(t["transcript"] for t in targeted["transcripts"]), targeted["quarantined"])
                   if isinstance(targeted, dict) else repr(targeted), (sorted(split_keys), []))
        # M#12: the index destination is confined before anything is created. `index/` is replaced by a
        # symlink to a directory outside the run; the write must be refused AND the outside directory must
        # be exactly as it was - a refusal that arrives after `mkdir` has run is not a confinement.
        outside = root / "outside-the-run"
        outside.mkdir()
        escape_run = golden(root, "escape", overhead=100_000)["run_dir"]
        index_dir = escape_run / "index"
        shutil.rmtree(index_dir)
        index_dir.symlink_to(outside, target_is_directory=True)
        before = sorted(q.name for q in outside.iterdir())
        # the production path's own function, not a copy of its two lines in the test
        def confine_index():
            try:
                index_destination(escape_run, "index/bm25/x.json")
            except stagelock.Escaped as exc:
                return str(exc).split(" ", 1)[0]
            return "nothing was refused"
        expect("control: the index destination behind a symlink out of the run is refused by name",
               confine_index(), "RUN_PATH_ESCAPE")
        expect("control: ... and the directory outside the run is untouched, because nothing was created before "
               "the destination was confined",
               sorted(q.name for q in outside.iterdir()), before)
        compressed = golden(root, "zst", overhead=100_000, compressed=True)
        from runlib import sources as source_reader  # the name `sources` is a loop variable further down
        kept_declared = source_reader.declared
        source_reader.declared = lambda run: {**kept_declared(run), "zstd": "/bin/cat"}  # executable, and not zstd
        try:
            refused("control: the compressed fixture refuses a declared zstd that is another program",
                    lambda: golden(root, "zst-cat", overhead=100_000, compressed=True), "ZSTD_UNAVAILABLE /bin/cat")
        finally:
            source_reader.declared = kept_declared
        expect("done-when 1: a compressed rollout is copied decompressed, and the copy is named by the hash of those bytes",
               (records.sha256_file(compressed["run_dir"] / compressed["codex"]["source_copy"]) == compressed["codex"]["version_sha"],
                compressed["codex"]["windows"][0]["records"]), (True, 3))

        # ---- done-when 7: the contract the schema carries ----------------------------------------
        schema = claims.read_schema("evidence")
        expect("done-when 7: every evidence record carries window_role, and the schema cites the section each field "
               "comes from (the field list itself is copied once, in claims.py's self-test, cited to §5.5)",
               ("window_role" in schema["required"], schema["$comment"]),
               (True, "design §5.5, plus window_role from design §5.2"))
        refused("control: two transcripts that would be written to one view directory are refused",
                lambda: run(fx_prepared_run(root, "collide")), "VIEW_NAME_COLLISION")
        bare = root / "bare"
        bare.mkdir()
        declare.create(bare, {**golden_run["run"], "declaration_seq": 0})
        refused("control: S2 over a run whose census S1 never wrote is refused by name, never over an empty set",
                lambda: run(bare), "INPUT_INVALID S1")
        reporting = records.run_items
        records.run_items = lambda posture, items, work: {"done": [], "quarantined": []}
        try:  # a stage runner that reports neither a view nor a quarantine for an eligible session
            refused("control: an eligible session that ends with neither a view nor a quarantine is named",
                    lambda: run(fx_prepared_run(root, "silent", COLLIDING[:1])), "SET_MISMATCH S2")
        finally:
            records.run_items = reporting

    missing = [part for part in INVARIANTS if not any(part in label for label in checks.ran)]
    if missing:
        checks.failures.append(f"the self-test's branch list is not covered: no label exercises {missing}")

    # M#11: a label check is not a contract check. Covering INVARIANTS by phrase was satisfied while
    # OVERLAP_TURNS changed from five to four, because the construction and the checking moved together and
    # both labels still read "overlap". These pin the design's own constants and the complete branch set of
    # each predicate here, independently of any label - and each branch is exercised with its own row.
    checks.expect("design §5.4: the constants this stage is built on are the design's own",
                  {"overlap turns": OVERLAP_TURNS, "input bound": bound.INPUT_BOUND, "turn kinds": TURN_KINDS},
                  {"overlap turns": 5, "input bound": 120_000, "turn kinds": ("human", "assistant")})
    # every status §5.4 forbids a basis to rest on, each in a scope of its own
    prohibited = ("unreadable", "known_absent", "unknown_provenance", "read_partial", "failed", "deferred")
    checks.expect("design §5.4: the statuses that make a basis incomplete are exactly the six the design lists",
                  [status for status in prohibited
                   if coverage_basis({"sources": [{"accounted": True, "directory_present": True}],
                                      "sessions": [{"status": status, "unprocessed": False, "view_complete": True,
                                                    "source_complete": True}]}) != "incomplete"], [])
    # ... and the complete branch set of coverage_basis, each with its own row and its own expected answer
    def basis_of(sources, session):
        return coverage_basis({"sources": [sources], "sessions": [session]})
    good_source = {"accounted": True, "directory_present": True}
    complete = {"status": "read_complete", "unprocessed": False, "view_complete": True, "source_complete": True}
    for label, sources, session, want in (
            ("a source not accounted", {"accounted": False, "directory_present": True}, complete, "incomplete"),
            ("a source directory missing", {"accounted": True, "directory_present": False}, complete, "incomplete"),
            ("a session with unprocessed records", good_source, {**complete, "unprocessed": True}, "incomplete"),
            ("a session that is not view complete", good_source,
             {**complete, "view_complete": False, "source_complete": False}, "incomplete"),
            ("a session view complete but not source complete", good_source,
             {**complete, "source_complete": False}, "view"),
            ("everything complete", good_source, complete, "source")):
        checks.expect(f"design §5.4, basis branch: {label} gives {want}", basis_of(sources, session), want)
    checks.expect("design §5.4: a claim of absence rests on basis source and on nothing else",
                  {basis: absence_claim_allowed(basis) for basis in ("incomplete", "view", "source")},
                  {"incomplete": False, "view": False, "source": True})
    with tempfile.TemporaryDirectory(prefix="views-x1-") as td:
        x1 = pathlib.Path(td)
        # X review of WP-08 r1 #2 and r2: an amendment of the cap landing just before S2's admission is the cap the windows
        # are cut with; one landing just after it changes nothing they were cut with
        cap = [(f"output_caps.{declare.VIEW_WINDOW_STAGE}", 48_000)]
        for when, want in (("before", 48_000), ("after", 32_000)):
            with records.fx_amended_at_admission("S2", cap, when):
                try:
                    raced = golden(x1, f"raced-{when}", overhead=100_000)
                except Exception as exc:  # noqa: BLE001 - reported by the control below, by name
                    raced = {"error": repr(exc)}
            label = (f"X r1: an amendment just before S2's admission is the cap the views record and their windows are cut "
                     f"with, under the declaration S2 recorded" if when == "before" else
                     "X r2: an amendment just after S2's admission changes nothing the windows were cut with")
            if "error" in raced:
                checks.expect(label, raced["error"], None)
                continue
            raced_dir = pathlib.Path(raced["run_dir"])
            part = records.read_json(records.record_path(raced_dir, "S2")).get("parts", {}).get("views", {})
            # the amendment landed in both cases: run.json is at sequence 1 either way
            checks.expect(label, ({raced["manifest"]["limits"]["reservation"]},
                                  {sequence_doc(raced_dir, t["name"])["limits"]["reservation"] for t in raced["manifest"]["transcripts"]},
                                  part.get("declaration_seq"), records.read_json(records.run_json_path(raced_dir))["declaration_seq"]),
                          ({want}, {want}, 1 if when == "before" else 0, 1))
        # X review of WP-08 r1 #1: what the overlap shows is located like an owned record's text, and nothing past its cut
        shown_run = golden(x1, "shown", overhead=100_000)
        shown_dir, shown_main = pathlib.Path(shown_run["run_dir"]), shown_run["main"]
        cut_entry = next((e for w in shown_run["windows"] for e in w["overlap"]["prev"] if e["overlap_cut"]), None)
        split_part = next((e for w in shown_run["windows"] for e in w["overlap"]["prev"] + w["overlap"]["next"]
                            if "#" in e["entry"]), None)
        for label, entry in (("a cut overlap entry", cut_entry), ("an overlap entry of a split span", split_part)):
            if entry is None:
                checks.expect(f"X r1: the golden windows hold {label}", None, "an entry")
                continue
            try:
                made = evidence_store.from_view(shown_dir, shown_main["version_sha"], entry, entry["text"][:30])
                got = (evidence_store.verify(shown_dir, made), made["window_role"])
            except Exception as exc:  # noqa: BLE001 - an entry that cannot be located fails this control by name
                got = repr(exc)
            checks.expect(f"X r1: a quote of {label} as shown is located and walks back to the copy, keeping its role",
                          got, ([], entry["window_role"]))
        if cut_entry is not None:
            checks.expect("X r1: a cut overlap entry's segments end where its shown text ends, so they claim no more than "
                          "it shows", max((s["view"][1] for s in cut_entry.get("segments", [])), default=None),
                          len(cut_entry["text"]))
            owner_text = next(r["text"] for w in shown_run["windows"] for r in w["records"]
                              if eid(r) == cut_entry["entry"])
            past = owner_text[len(cut_entry["text"]):len(cut_entry["text"]) + 30]
            checks.refused("X r1: a quote of what the overlap cut off is not located in the overlap",
                           lambda: evidence_store.from_view(shown_dir, shown_main["version_sha"], cut_entry, past),
                           "QUOTE_MISMATCH")
    # WP-08 commit 5a: a call's decision of an omission is written once - again as it was, nothing more; otherwise, refused
    with tempfile.TemporaryDirectory() as decided:
        decided_dir = pathlib.Path(decided)
        omitted = {"name": "v", "record_id": "1/message/content", "omission": "1/message/content@0-9#ab"}

        def decide(call_id, decision, reason):
            """`written`, or the refusal's code: a reverted rule fails its control by name, not by a traceback."""
            try:
                record_decision(decided_dir, call_id, omitted["name"], omitted["record_id"], decision, reason,
                                omission=omitted["omission"])
            except Refused as exc:
                return str(exc).split()[0]
            return "written"

        def logged():
            path = decided_dir / "expansions.jsonl"
            return path.read_bytes() if path.is_file() else b""
        first_decision = decide("r1/S3/w1", "expand", "read it whole")
        log_once = logged()
        checks.expect("5a: a call's decision of an omission made again as it was is not written twice",
                      (first_decision, decide("r1/S3/w1", "expand", "read it whole"), logged() == log_once,
                       len(log_once.splitlines())), ("written", "written", True, 1))
        checks.expect("5a: the same call deciding the same omission otherwise is refused where it would be written",
                      (decide("r1/S3/w1", "skip", "not worth it"), logged() == log_once),
                      ("EXPANSION_DECISION_CONFLICT", True))
        checks.expect("5a: another call's decision of the same omission is another line",
                      (decide("r1/S3/w2", "skip", "not worth it"), len(logged().splitlines())), ("written", 2))
    if not checks.ran:
        checks.failures.append("the self-test asserted nothing")
    for failure in checks.failures:
        print(f"views --self-test [FAIL] {failure}")
    if checks.failures:
        return 1
    print(f"views --self-test: OK ({len(checks.ran)} controls over golden transcripts: the immutable copy and its "
          f"projection, the planted token and home path in no artifact but the copy, windows owned once with their "
          f"overlaps, split spans tiling their message, every error line kept, the five-turn overlap in each of its "
          f"four cases (a split message, unowned tool traffic, an exhausted side budget, duplicate membership) with "
          f"every omission hashed, manifested and expandable, the bound's (a), (d), observed-input and allowance "
          f"branches driven by hash-pinned retained captures, the omission manifest, both completeness levels, every "
          f"branch of the forced-expansion predicate, expansion against the generated manifests of a long-turn "
          f"run with two expansions under one call id, the stale-artifact refusals at the reading and rendering "
          f"boundaries, the F-O9-04 pair, and every coverage basis of §5.4)")
    return 0


COLLIDING = ("019e0001:0000-7000-8000-00000000000a", "019e0001_0000-7000-8000-00000000000a")


def fx_long_records():
    """A transcript of long human and assistant turns with tool traffic between them: the shape whose
    overlap really is cut and really does exhaust a side's budget, so `expand` can be exercised against
    generated manifest rows instead of rows a control wrote itself. The text is nonrepetitive, so no
    interval's hash can match another's by accident."""
    def wordy(tag, length):
        return "".join(f"{tag}-{k} " for k in range(length))[:length]
    out = []
    for n in range(1, 13):
        day, hour = 2 + n // 6, (n * 3) % 24
        out.append(fx_human(fx_stamp(day, hour=hour), wordy(f"h{n}", 2_400)))
        out.append(fx_assistant(fx_stamp(day, hour=hour), wordy(f"a{n}", 2_600)))
        out.append(fx_call(fx_stamp(day, hour=hour), "Bash", {"command": f"ls -la dir{n}"}))
        # the first result is over CLIP_OVER, so the run really holds a clipped record within the range the
        # window views: its view elides a middle, which is the case whose coordinates a view-local interval
        # gets wrong
        out.append(fx_result(fx_stamp(day, hour=hour), wordy(f"r{n}", 6_000 if n == 1 else 1_500)))
    return out


# Z#1: each planted case by the line it stands on and the pointer of its block, so a control can name the
# locator it is making a claim about instead of searching for one. The lines are 1-based record numbers of
# `fx_fallback_records`, and every one of them is inside the range the window views.
FX_FALLBACK_CASES = (
    ("an encoded scalar credential behind a cross-member floor claim", 1, "/message/content", "FX_FALLBACK_SCALAR"),
    ("an encoded home path behind a cross-member floor claim", 2, "/message/content/0/text", "FX_HOME"),
    ("a secret-named key in prose whose value is a readable structure", 3, "/message/content", "FX_OBLIGATION_JSON"),
    ("a quoted scalar that itself holds a structure", 4, "/message/content/0/text", "FX_OBLIGATION_QUOTED"),
    ("an escaped array under a readable keyed name", 6, "/message/content/0/text", "FX_ESCAPED_ARRAY"),
    ("a quoted scalar whose keyed value holds a structure", 7, "/message/content", "FX_QUOTED_SCALAR"),
    ("a credential beside a literal mask inside the value", 8, "/message/content/0/text", "FX_MASK_NEIGHBOUR"),
    ("an escaped member after a plain structure", 9, "/message/content", "FX_ESCAPED_TAIL"),
    ("R#4: a cross-member claim arriving as a structure", 14, "/message/content/0/input",
     "FX_STRUCTURED_CROSS"),
    ("E#0 downstream: an encoded key whose name stands in a sibling value", 10,
     "/message/content/0/text", "FX_SIBLING_KEY"),
    ("E#1 downstream: a twice-encoded token beside a plain path", 11, "/message/content", "FX_MIXED_DEPTH"),
    ("E#2 downstream: a decodable body with no escaped quote", 12, "/message/content/0/text",
     "FX_NO_QUOTE_BODY"),
    ("S#3: a secret-named member with a newline before its colon", 15, "/message/content/0/text",
     "FX_MEMBER_NEWLINE"),
    ("S#0 downstream: a keyed fragment in mixed text", 16, "/message/content", "FX_MIXED_TEXT"),
    ("U#2 / T#0: a secret-named key behind 38 characters of name", 18, "/message/content/0/text",
     "FX_LONG_NAME"),
    ("U#0: a value that starts with the mask and goes on past a comma", 19, "/message/content",
     "FX_MASK_COMMA"),
    ("U#2 / T#2: an escape run before an actual newline", 20, "/message/content/0/text", "FX_ESCAPE_RUN"),
    ("U#2 / T#4: a duplicate member whose masked copy comes last", 21, "/message/content",
     "FX_DUPLICATE_LAST"),
    ("X#3 / V#0: a readable array under an encoded key", 22, "/message/content/0/text",
     "FX_READABLE_ARRAY"),
    ("X#3 / V#0: a readable object under an encoded key", 23, "/message/content", "FX_READABLE_OBJECT"),
    ("X#3 / V#1: a suffix after a masked scalar", 24, "/message/content/0/text", "FX_SCALAR_SUFFIX"),
    ("X#3 / V#2: a quoted key whose separator is on the next line", 25, "/message/content",
     "FX_NEWLINE_SEPARATOR"),
)


def fx_fallback_records():
    """A transcript of the blocks whose secrets only decoding reaches, or whose obligations the decoded form
    cannot see. All of them sit in the range the window views, so the stage really processes them.

    The name is the history: these were the blocks that took the superseded fallback path. They are kept
    because each is a shape some round leaked on, and the single pass has to answer for all of them."""
    encoded_home = FX_HOME.replace("/", "\\u002f")
    return [
        fx_human(fx_stamp(3, hour=1),
                 'a fallback case: {"a":"' + FX_FALLBACK_TOKEN + ' api_key=","b":"' + FX_FALLBACK_LEFTOVER
                 + '", "\\u0070assword":"' + FX_FALLBACK_SCALAR + '"}'),
        fx_assistant(fx_stamp(3, hour=2),
                     'and one with a path: {"a":"' + FX_FALLBACK_TOKEN + ' api_key=","b":"'
                     + FX_FALLBACK_LEFTOVER + '", "' + encoded_home + '\\u002fx":1}'),
        fx_human(fx_stamp(3, hour=3),
                 'prefix "password": {"value":"' + FX_OBLIGATION_JSON + '","token":"x"}'),
        fx_assistant(fx_stamp(3, hour=4),
                     'authorization: "{\\"value\\":\\"' + FX_OBLIGATION_QUOTED + '\\"}"'),
        # the home path in plain form as well, so the sweep's instrument control has raw bytes to find
        fx_human(fx_stamp(3, hour=5), f"and what did that leave under {FX_HOME}/Documents?"),
        # Z#0: a readable keyed name whose value is an escaped array
        fx_assistant(fx_stamp(3, hour=6), 'prefix "password": [ "'
                     + "".join(f"\\u{ord(ch):04x}" for ch in FX_ESCAPED_ARRAY) + '" ]'),
        # A#0: a quoted scalar that holds a structure
        fx_human(fx_stamp(3, hour=7), 'note "api_key": "x{}' + FX_QUOTED_SCALAR + '"'),
        # rule 2: a literal mask beside a credential inside the value
        fx_assistant(fx_stamp(3, hour=8), '"secret": {"seen":"' + projection.FLOOR.PLACEHOLDER
                     + '","v":"' + FX_MASK_NEIGHBOUR + '"}'),
        # A#1: a plain structure followed by an escaped member
        fx_human(fx_stamp(3, hour=9), '{"a":"' + FX_FALLBACK_TOKEN + ' api_key=","b":"left"} '
                 + '\\"' + "".join(f"\\u{ord(ch):04x}" for ch in "password") + '\\": \\"'
                 + FX_ESCAPED_TAIL + '\\"'),
        # M#7 / E#0: the secret-named key is encoded and its name also stands in a sibling's value
        fx_assistant(fx_stamp(3, hour=10), '{"note":"password","'
                     + "".join(f"\\u{ord(ch):04x}" for ch in "password") + '":"' + FX_SIBLING_KEY + '"}'),
        # M#7 / E#1: a twice-encoded token beside an already plain encoded path, in one region
        fx_human(fx_stamp(3, hour=11), '\\"note\\":\\"sk\\\\u002d' + FX_MIXED_DEPTH
                 + '\\", \\"path\\":\\"' + FX_HOME.replace("/", "\\u002f") + '/x\\"'),
        # M#7 / E#2: a decodable body carrying no escaped quote at all
        fx_assistant(fx_stamp(3, hour=12), 'see sk\\u002d' + FX_NO_QUOTE_BODY + ' here'),
        # M#8: the shape the mapping cannot locate, which the verifier blanks
        fx_assistant(fx_stamp(3, hour=13), '{"note":"plain"} sk' + "\\\\u005c" * 6 + "u002d"
                     + FX_LAYERED),
        # R#4: a structured content block whose members form a claim only once serialised
        fx_call(fx_stamp(3, hour=14), "Write", {"a": FX_FALLBACK_TOKEN + " api_key=",
                                                "b": FX_STRUCTURED_CROSS}),
        # S#3: a secret-named member with a newline before its colon
        fx_assistant(fx_stamp(3, hour=15), '{"safe":{"password":"' + projection.FLOOR.PLACEHOLDER
                     + '"},"password"\n:"' + FX_MEMBER_NEWLINE + '"}'),
        # S#3 / S#0: a keyed fragment in mixed text, read by no member rule
        fx_human(fx_stamp(3, hour=16), '{"note":"plain"} "\\u0070assword":"' + FX_MIXED_TEXT + '"'),
        # S#5: one structured block whose two leaves each take the backstop
        fx_call(fx_stamp(3, hour=17), "Write",
                {"a": "sk" + "\\\\u005c" * 6 + "u002d" + FX_TWO_LEAF,
                 "b": "sk" + "\\\\u005c" * 6 + "u002d" + FX_TWO_LEAF + "two",
                 "c": "plain words"}),
        # U#2 / T#0: a secret-named key behind 38 characters of name
        fx_assistant(fx_stamp(3, hour=18), '{"note":"plain"} "' + "x" * 38
                     + '\\u0070assword":"' + FX_LONG_NAME + '"'),
        # U#2 / T#1 and U#0: a value that starts with the mask and goes on past a comma
        fx_human(fx_stamp(3, hour=19), '{"note":"plain"} "\\u0070assword":"'
                 + projection.FLOOR.PLACEHOLDER + ',' + FX_MASK_COMMA + '"'),
        # U#2 / T#2: an escape run before an actual newline, with the credential after it
        fx_assistant(fx_stamp(3, hour=20), '{"note":"plain"} \\\n' + FX_ESCAPE_RUN),
        # U#2 / T#4: a duplicate secret-named member whose MASKED copy comes last
        fx_human(fx_stamp(3, hour=21), '{"password":"' + FX_DUPLICATE_LAST + '","password":"'
                 + projection.FLOOR.PLACEHOLDER + '"}'),
        # X#3 / V#0: a readable array and a readable object under an encoded key
        fx_assistant(fx_stamp(3, hour=22), '{"note":"plain"} "\\u0070assword":["' + FX_READABLE_ARRAY + '"]'),
        fx_human(fx_stamp(3, hour=23), '{"note":"plain"} "\\u0070assword":{"inner":"'
                 + FX_READABLE_OBJECT + '"}'),
        # X#3 / V#1: a suffix standing after a masked scalar
        fx_assistant(fx_stamp(3, hour=24), '{"note":"plain"} "\\u0070assword":"'
                     + projection.FLOOR.PLACEHOLDER + '"' + FX_SCALAR_SUFFIX),
        # X#3 / V#2: a quoted key whose separator stands on the next line
        fx_human(fx_stamp(3, hour=25), '{"note":"plain"} "password"\n: "' + FX_NEWLINE_SEPARATOR + '"'),
        fx_assistant(fx_stamp(3, hour=6), "nothing a window may show"),
        fx_call(fx_stamp(3, hour=7), "Bash", {"command": "ls -la"}),
        fx_result(fx_stamp(3, hour=8), "two files and a directory"),
        fx_human(fx_stamp(3, hour=9), "good"),
    ]


def fx_prepared_run(root, name, idents=COLLIDING):
    """A declared run with a census of `idents` and no view cut yet. The default pair differs only in a character
    `safe_name` folds, so both would be written to one view directory."""
    run_dir = root / name
    run_dir.mkdir(parents=True, exist_ok=True)
    host = root / f"{name}-host"
    sha = fx_write(host / "one.jsonl", fx_codex_records())
    _s, _e, window_id = coverage.window_bounds(FX_WINDOW)
    entries = [fx_entry("codex", ident, "codex_sessions", host / "one.jsonl", sha, owned=[[0, 3]],
                        work={"version": 0, "in_window": [[0, 3]], "backlog": []})
               for ident in idents]
    document = fx_census(window_id, entries)
    declaration = {**declare.fixture(), "window": FX_WINDOW}
    declare.create(run_dir, declaration)
    with records.run_stage(run_dir, "S1") as stage:
        records.write_text(run_dir, run_dir / "census.json", census.dump(document))
        records.write_json(run_dir, run_dir / "coverage.json", coverage.new_state())
        stage.output("census.json")
        stage.output("coverage.json")
    return run_dir


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: views.py --self-test")
    sys.exit(self_test())
