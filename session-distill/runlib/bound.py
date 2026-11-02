#!/usr/bin/env python3
"""The window bound, owned once (design §5.4 as amended, record
`design/session-distill/2026-10-21T0026--cc0498f--input-bound-amendment.md`).

A view-window call keeps one rule, and before this module the rule existed twice: `views.py` cut
windows against its own copy and `dispatch.py` admitted calls against another, with two constants
spelled `INPUT_LIMIT` and `INPUT_BOUND`, check (a) in both, check (d) in only one, the excess record
written by neither, and the recovery rule in the side that cannot dispatch. Two implementations of
one rule is the defect; keeping them in step is not the fix.

So the rule lives here and both sides import it: `views.py` to decide how large a window may be,
`dispatch.py` to admit a call, settle it, stop the run and lift the stop. This module is **pure** -
standard library only, no `runlib` import, no file read, no clock - so it cannot grow a second
opinion about where the run's state lives. Its callers supply the state and raise its refusals.

The rule, in the amendment's own terms:

* **(a)** what the driver sends in one call, plus the host's declared allowance, stays within
  `INPUT_BOUND` tokens, each token covering at least one byte;
* **(d)** that payload, the allowance and the reserved output together stay within the seat's
  context capacity;
* **settlement** - the input a view-window call really read (prompt input + cache creation + cache
  read) is compared with `INPUT_BOUND` after the call; above it, the host changed;
* an excess **stops the run**, recorded once with the declaration it ran under;
* the stop **lifts only** on a re-measured `host_allowance`, declared later than that record.

A call that carries no view window is bound by none of this: its own section's contract holds, and
an R-authoring call is a non-window call by definition (design §8.6).
"""

import hashlib
import json
import pathlib
import re
import sys

INPUT_BOUND = 120_000        # tokens; the driver's bytes plus the host allowance stay within this
PACKET_OVERHEAD = 12_288     # bytes of template, schema and instructions a packet adds to a window

# There is no constant for the seat's context capacity, and none for the output reservation. Both were
# invented numbers, and one of them was false: the capacity is host-reported evidence `seats.json`
# declares per seat (BA#1), and the reservation is THIS CALL's declared output cap - what the call
# reserved for its answer, not what the host would allow it (the lead's ruling of 2026-10-22). `limits`
# therefore requires both, so neither reader can fall back on a number nobody chose.

STOP_CODE = "INPUT_BOUND_EXCEEDED"
AMENDED_KEY = "host_allowance"   # the only declaration key whose amendment lifts this stop


# ---- the limits one call keeps ---------------------------------------------------------------

def limits(allowance, *, capacity, reservation, seat=None, overhead=PACKET_OVERHEAD):
    """The bound a view-window call keeps: a declared `allowance`, the seat's declared `capacity`, and
    the call's own declared output `reservation`.

    `capacity` and `reservation` are keyword-only and have no defaults on purpose - see above."""
    return {"seat": seat, "allowance": allowance, "capacity": capacity, "reservation": reservation,
            "overhead": overhead}


def driver_budget(limits):
    """Bytes the driver may supply in one view-window call: the tighter of (a) and (d)."""
    return min(INPUT_BOUND - limits["allowance"],
               limits["capacity"] - limits["reservation"] - limits["allowance"])


def check_bound(driver_bytes, limits):
    """Violations of the two pre-dispatch checks for a view-window call; empty when both hold."""
    errors = []
    if driver_bytes > INPUT_BOUND - limits["allowance"]:
        errors.append(f"WINDOW_BOUND_EXCEEDED (a): {driver_bytes} driver bytes exceed {INPUT_BOUND} - the declared "
                      f"allowance {limits['allowance']} = {INPUT_BOUND - limits['allowance']}")
    if driver_bytes + limits["allowance"] + limits["reservation"] > limits["capacity"]:
        errors.append(f"WINDOW_CAPACITY_EXCEEDED (d): {driver_bytes} driver bytes + allowance {limits['allowance']} + "
                      f"output reservation {limits['reservation']} exceed the seat's context capacity "
                      f"{limits['capacity']}")
    return errors


# ---- what the driver sends ------------------------------------------------------------------

BY_CONTENT = "appended_prompts"   # the one declared kind with no path form - see `part_body`

# What a declared part can be refused for. The dispatcher raises these under the call id, computing the
# code from the problem rather than writing it, so its refusal inventory reads this tuple instead of a
# literal; the self-test below plants a part of each shape and requires every member to fire.
PART_CODES = ("DRIVER_PART_UNCOUNTED", "DRIVER_PART_LENGTH_CONFLICT", "APPENDED_PROMPT_PATH_FORM")


def part_body(part, kind=None):
    """`(body, problem)` - the EXACT bytes of one declared driver part, read or encoded ONCE.

    Everything else about the part derives from these bytes and from nothing else: the length admission
    counts, the sha256 and the length the call record carries, and what the adapter delivers. Deriving
    them from separate reads is how a record came to hash a whole prompt while admitting the length of
    something else (BB#1), so there is one read here and no second one anywhere.

    A part is text, or bytes, or a record carrying `text`, an already-read `body`, or a `path` this
    process can read. A part that is none of those is **not counted as zero** - it is reported, because
    an uncountable part makes the driver's share unknown, and understating that share is the one failure
    the bound exists to prevent.

    `kind` is the manifest key the part was declared under, because one of them admits no path: an
    appended system prompt is declared by its content (BB#3) - the path form produced a record the call
    schema rejects and nothing ever read it back - while an instruction file IS a path on the host and
    keeps it."""
    if isinstance(part, bytes):
        return part, None
    if isinstance(part, str):
        return part.encode("utf-8"), None
    if not isinstance(part, dict):
        return None, f"DRIVER_PART_UNCOUNTED {type(part).__name__}: a declared part that is not text, bytes or a record"
    if kind == BY_CONTENT and "path" in part:
        # BEFORE any content is chosen (BC#3). A prompt carrying both content and a path used to pass
        # here on its content and be recorded with the path beside it, which CALL_SCHEMA then rejects -
        # after the call was launched. The field's presence is the refusal, not which branch wins.
        return None, (f"APPENDED_PROMPT_PATH_FORM {part.get('path')!r}: an appended system prompt is declared by its "
                      f"content, and this declaration carries a path; the path form is the instruction file's, and "
                      f"this kind has none")
    if isinstance(part.get("body"), bytes):          # a snapshot: these bytes were read once already
        return part["body"], None
    if isinstance(part.get("text"), str):
        return part["text"].encode("utf-8"), None
    if isinstance(part.get("path"), str):
        try:
            return pathlib.Path(part["path"]).read_bytes(), None
        except OSError as exc:
            return None, (f"DRIVER_PART_UNCOUNTED {part['path']}: {exc.strerror or exc}; a declared part this process "
                          f"cannot read leaves the driver's share unknown")
    return None, (f"DRIVER_PART_UNCOUNTED {sorted(part)}: a declared part carries neither content nor a readable "
                  f"path, so the driver's share cannot be counted")


def asserted_length_problem(part, body):
    """The problem when a caller's asserted length disagrees with the bytes ALREADY READ, else None.

    It takes the body rather than the part, so the check cannot be the reason a file is read a second
    time (BC#1): one read, and the assertion is judged against exactly those bytes. The only thing an
    assertion can do here is disagree - believing it instead let a part hash 130 KB of prompt and be
    admitted as one byte (BB#1)."""
    asserted = part.get("bytes") if isinstance(part, dict) else None
    if asserted is None or (isinstance(asserted, int) and not isinstance(asserted, bool)
                            and asserted == len(body)):
        return None
    return (f"DRIVER_PART_LENGTH_CONFLICT {part.get('name') or part.get('path') or sorted(part)}: the part "
            f"asserts {asserted!r} bytes and its content is {len(body)}; the length admission counts, the "
            f"length the record carries and the bytes the host receives are one snapshot, so a number that "
            f"disagrees with them is refused rather than believed")


def part_bytes(part, kind=None):
    """`(bytes, problem)` for one declared driver part: the length of its own bytes."""
    body, problem = part_body(part, kind)
    if problem:
        return 0, problem
    problem = asserted_length_problem(part, body)
    return (0, problem) if problem else (len(body), None)


def part_snapshot(part, kind=None):
    """`(snapshot, problem)` - one declared part read ONCE: its bytes, their sha256 and their length.

    One `part_body` call and nothing else reads: the length, the hash and the bytes the adapter is
    handed all come off this body, and an asserted length is judged against it rather than against a
    second read of the same path (BC#1). A snapshot is itself a part (its `body`), so the counter takes
    it without reading anything again and the record keeps `evidence_of` it."""
    body, problem = part_body(part, kind)
    if problem:
        return None, problem
    problem = asserted_length_problem(part, body)
    if problem:
        return None, problem
    snapshot = {"body": body, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
    for key in ("name", "path"):
        if isinstance(part, dict) and isinstance(part.get(key), str):
            snapshot[key] = part[key]
    return snapshot, None


def evidence_of(snapshot):
    """What a snapshot is RECORDED as: everything about it but the bytes themselves."""
    return {key: value for key, value in snapshot.items() if key != "body"}


DECLARED_PARTS = ("instructions", BY_CONTENT)


def driver_parts(packet, schema_bytes=None, manifest=None):
    """`(part, kind)` for every part of one call that the DRIVER supplies, in the order counted.

    The packet (its template, the principles block and the window payload are one object by the time
    it is built), the schema, and what the call's own manifest declares it carries: instruction files
    and appended system prompts. The packet and the schema are bytes of no declared kind, so their
    `kind` is None.

    What the **host** loads by itself under the profile is not here. That is the measured allowance,
    and counting it again on the driver's side would charge the same tokens twice - which is why this
    takes the call's own manifest and never the merged one that carries `seats.json`'s builtin
    context. Files merely readable in the working directory are not sent, so they are not counted
    either: a read shows up in the observed input, and settlement is what catches it."""
    parts = [(packet, None)]
    if schema_bytes is not None:
        parts.append((schema_bytes, None))
    declared = manifest or {}
    for key in DECLARED_PARTS:
        for item in declared.get(key) or []:
            parts.append((item, key))
    return parts


def part_evidence(part, kind=None):
    """`(record, problem)` - what a declared driver part is RECORDED as, from the bytes just read.

    One representation for both readers: the payload count needs the content, and the call record needs
    evidence of it that a schema can close over. So a caller declares a part by its content - `text`, or
    an instruction file's `path` to read - and what the record keeps is its name, its sha256 and its
    length. A part that only asserts a number is not evidence of anything, and a record of text nobody
    counted is not either (BA#2)."""
    snapshot, problem = part_snapshot(part, kind)
    return (None, problem) if problem else (evidence_of(snapshot), None)


def declared_snapshots(manifest):
    """`(snapshots, problems)` - the call's declared parts, each read once, by manifest key.

    This is the single read. `declared_evidence` records these snapshots, `driver_bytes` counts them,
    and the dispatcher delivers their bytes, so the three readers cannot disagree (BB#1)."""
    snapshots, problems = {}, []
    for key in DECLARED_PARTS:
        if not (manifest or {}).get(key):
            continue
        rows = []
        for part in manifest[key]:
            snapshot, problem = part_snapshot(part, key)
            if problem:
                problems.append(problem)
            else:
                rows.append(snapshot)
        snapshots[key] = rows
    return snapshots, problems


def declared_evidence(manifest):
    """`(manifest, problems)` - the call's manifest with every declared driver part recorded as evidence.

    The dispatcher writes this into the call record, so what the gate reads is the sha256 and length of
    the bytes the payload count actually counted."""
    snapshots, problems = declared_snapshots(manifest)
    out = dict(manifest or {})
    for key, rows in snapshots.items():
        out[key] = [evidence_of(row) for row in rows]
    return out, problems


def driver_bytes(packet, schema_bytes=None, manifest=None):
    """`(bytes, problems)` - the UTF-8 size of everything the driver sends for one call.

    Counting the window alone understates the driver's part by exactly the overhead the bound exists
    to include, which is why this is the only counter and both sides call it."""
    total, problems = 0, []
    for part, kind in driver_parts(packet, schema_bytes, manifest):
        size, problem = part_bytes(part, kind)
        total += size
        if problem:
            problems.append(problem)
    return total, problems


def admitted_parts(packet, schema_bytes=None, manifest=None):
    """`(driver_bytes, evidence, snapshots, problems)` for one call, from ONE read of each part.

    The dispatcher's entry point, and the reason the three answers agree by construction: the parts are
    read here, the count is taken over those snapshots, the evidence is those snapshots without their
    bytes, and the snapshots themselves are what the adapter is handed to deliver (BB#1, BB#2)."""
    snapshots, problems = declared_snapshots(manifest)
    evidence = dict(manifest or {})
    for key, rows in snapshots.items():
        evidence[key] = [evidence_of(row) for row in rows]
    total, counting = driver_bytes(packet, schema_bytes, {**(manifest or {}), **snapshots})
    return total, evidence, snapshots, problems + [p for p in counting if p not in problems]


# ---- what the call really read ---------------------------------------------------------------

# the three components of observed input, in the two spellings the artifacts use: a capture's
# what `observed_rows` reports for a row it could not read at all
ROW_UNREADABLE = "row-unreadable"

# Anthropic-shaped usage, and a usage record's own request rows
INPUT_PARTS = (("input_tokens", "input"),
               ("cache_creation_input_tokens", "cache_creation"),
               ("cache_read_input_tokens", "cache_read"))


def countable(value):
    """A host-reported token count: a whole number, not negative, and not a bool.

    `isinstance(x, int)` admits `True` and `-20000`, and both were counted (HC#4): a negative cache
    field cancelled an otherwise conclusive excess, and a bool was read as one token. Neither is a
    count, so both are reported as missing instead."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def render_count(value):
    """A count rendered for a diagnostic, never raising.

    Python refuses to format an integer past its digit limit, so a stop could fail on its own
    message with the excess already observed (HC#0). A number this reader cannot render is still a
    number the rule has decided about."""
    try:
        return f"{value}"
    except Exception:                          # noqa: BLE001 - a diagnostic never decides anything
        return "a count too large to render"


def observed_of(usage):
    """`(observed, missing)` for one usage mapping, in either spelling.

    The valid components are a LOWER BOUND on what that request put in front of the model, and they
    are returned as one: a request whose input alone is past the bound is past the bound whatever its
    cache fields failed to say (HC#1). A component that is missing or is not a count is reported
    instead, independently, and never read as a zero."""
    total, missing = 0, []
    for spellings in INPUT_PARTS:
        found = [usage.get(name) for name in spellings if countable(usage.get(name))]
        if not found:
            missing.append(spellings[0])
            continue
        total += found[0]
    return total, missing


def row_observation(row, state="measured"):
    """`(observed, missing)` for ONE request row, or `(None, missing)` when it is not in `state`.

    The one per-row policy both readers share, so the live rows and the written record cannot
    disagree about the same row (HC#1). It raises on nothing it is given."""
    try:
        if row.get("state", state) != state:
            return None, []
        total, missing = observed_of(row)
    except Exception:                          # noqa: BLE001 - this reading decides a stop: it cannot raise
        return None, [ROW_UNREADABLE]
    return total, missing


def observed_rows(rows, state="measured"):
    """`(observed, missing)` - the largest observation over the `state` rows, by a reading that
    cannot raise.

    The maximum, not the sum: the bound is what one request put in front of the model. A row that
    cannot be read at all, or a container that cannot be walked, is reported in `missing` and never
    hides another row's excess. `observed_input` is this same reading over a written usage record."""
    totals, missing = [], []
    try:
        candidates = list(rows or [])
    except Exception:                          # noqa: BLE001 - not even a sequence (HC#0)
        return 0, [ROW_UNREADABLE]
    for row in candidates:
        total, gaps = row_observation(row, state)
        if total is not None:
            totals.append(total)
        missing += [gap for gap in gaps if gap not in missing]
    return (max(totals) if totals else 0), missing


def observed_input(requests, state="measured"):
    """The same reading over a usage record's own request rows - one policy, two callers."""
    return observed_rows(requests, state)


def check_observed(observed, view_window):
    """After a call: a view-window call whose observed input is above the bound is a host change."""
    if view_window and observed > INPUT_BOUND:
        return [f"{STOP_CODE}: observed input {render_count(observed)} tokens exceeds {INPUT_BOUND} on a view-window "
                "call; the host added more than the declared allowance - re-measure it and amend the declaration"]
    return []


# ---- the one excess record, and the one way back ---------------------------------------------

def excess(call_id, observed, at):
    """The run's stop entry for a bound excess - the single record of it, before it is committed.

    One record, written where the stop is written, read where the stop is read; a second file beside it
    would be a second thing to keep true. The sequence it is compared against is NOT in it yet: see
    `committed`."""
    return {"code": STOP_CODE, "call_id": call_id, "observed": observed, "at": at,
            "detail": f"{STOP_CODE} {call_id}: a view-window call read {render_count(observed)} input tokens, past "
                      f"the {INPUT_BOUND} bound; the host changed, so the run stops"}


def committed(entry, declaration_seq):
    """The excess record as it is COMMITTED, stamped with the sequence recovery is measured from.

    That sequence is the latest the declaration had reached when the stop was written - not the one the
    call was reserved under. A call can be reserved at seq 2, an amendment of `host_allowance` can land at
    seq 3 while the call is still running, and the call can then overrun: stamping the call's own sequence
    would let that amendment - which was recorded BEFORE anybody knew the host had changed - lift the stop
    it could not have anticipated. Recovery means a measurement taken after the overrun, so the sequence
    must be read where the stop is committed, under the same lock."""
    return {**entry, "declaration_seq": declaration_seq}


def lifted(stopped, amendments):
    """Whether a run stopped by the bound may dispatch again.

    True only for a bound stop that a **later** amendment of `host_allowance` follows: the allowance
    is re-measured and declared through `declare --amend`, at a sequence after the record's. Any
    other stop code is not this rule's to lift, and neither an unrelated amendment nor one recorded
    earlier lifts it."""
    if not stopped or stopped.get("code") != STOP_CODE:
        return False
    seq = stopped.get("declaration_seq")
    if not isinstance(seq, int):
        return False
    for amendment in amendments or []:
        if not isinstance(amendment.get("seq"), int) or amendment["seq"] <= seq:
            continue
        if any(str(key).split(".")[0] == AMENDED_KEY for key in amendment.get("diff") or {}):
            return True
    return False


def terminal(stopped):
    """Whether a stop can never be lifted: nothing this rule knows will reopen the run.

    Two shapes are terminal. A stop code this rule does not own is not its to lift, and a bound stop with
    no `declaration_seq` has nothing for an amendment to be later than - which is what makes the unstamped
    stop of a lock timeout the end of the run."""
    if not stopped:
        return False
    return stopped.get("code") != STOP_CODE or not isinstance(stopped.get("declaration_seq"), int)


def strongest(kept, offered):
    """Which of two stop records a run keeps: **a stop never weakens** (BD#0).

    The ledger holds one `stopped` entry, and more than one call can settle an excess - one timing out on
    the declaration lock and recording an unstamped stop, another, already running, settling later with a
    stamped one. Writing the newer entry over the older made the run recoverable by amendment: the stamped
    sequence gave a later `host_allowance` amendment something to pass, while the reason the first stop was
    unstamped had not gone away. So the entry kept is the stronger of the two:

    * nothing kept yet - the offered stop;
    * a terminal stop already kept - that one, unchanged;
    * the offered stop terminal - the offered one;
    * otherwise both are stamped bound stops, and the higher `declaration_seq` is kept, so recovery must
      pass the LATEST excess rather than an earlier one; an equal sequence keeps what is already recorded.

    Each call still reports its own refusal in its own call record; this decides only what the run's one
    stop entry says."""
    if not kept:
        return offered
    if not offered or terminal(kept):
        return kept
    if terminal(offered):
        return offered
    return offered if offered["declaration_seq"] > kept["declaration_seq"] else kept


def blocked(stopped, amendments):
    """None when dispatch may go on; else the named stop, lifted or not by the rule above."""
    if not stopped:
        return None
    if lifted(stopped, amendments):
        return None
    if stopped.get("code") == STOP_CODE:
        # the dispatcher's own contract spells a stop `RUN_STOPPED <code> at <call_id>`; this adds the one
        # thing a bound stop has that the others do not - the way back
        return (f"RUN_STOPPED {STOP_CODE} at {stopped.get('call_id')}: observed {stopped.get('observed')} tokens; "
                "every dispatch stays refused until host_allowance is re-measured and declared through "
                "`declare --amend`")
    return f"RUN_STOPPED {stopped.get('code')} at {stopped.get('call_id')}: nothing more is dispatched in this run"


# ---- self-test ------------------------------------------------------------------------------

def source_text():
    """This module's own source, for the controls that hold it to its shape."""
    return pathlib.Path(__file__).read_text(encoding="utf-8")


def self_test():
    """The rule, over the shapes its two callers really hand it.

    The controls the view side used to run against its own copy live here now, by the same names, so
    moving the rule did not drop them: the (a) and (d) pair, the tighter-budget case, the complete
    payload count, the observed-input settlement and its non-window exemption, and the stop's
    lifting. What those names cannot cover - the real dispatch boundary - is controlled in
    `dispatch.py`'s own self-test against retained captures."""
    failures = []

    def named(label, got, want=None):
        if want is None:
            if got:
                failures.append(f"{label}: {got}")
        elif not any(want in line for line in got):
            failures.append(f"{label}: {want!r} is in none of {got}")

    def expect(label, got, want):
        if got != want:
            failures.append(f"{label}: got {got!r}, expected {want!r}")

    # the self-test's own numbers, and it says so: a capacity and a reservation are declared per seat and
    # per call in production, and nothing here stands in for either
    held = limits(4000, seat="claude:claude-sonnet-5-5/xhigh", capacity=200_000, reservation=32_000)

    # (a) and (d), the pair that was split across two modules
    named("bound (a) and (d): a window inside both checks passes", check_bound(1000, held))
    named("control, bound (a): driver bytes above 120k minus the declared allowance are named",
          check_bound(INPUT_BOUND - held["allowance"] + 1, held), "WINDOW_BOUND_EXCEEDED")
    named("control, bound (d): driver bytes that pass (a) but leave no room for the output reservation are named",
          check_bound(50_000, {**held, "capacity": 60_000}), "WINDOW_CAPACITY_EXCEEDED")
    expect("bound (a) at its exact value is inside the bound",
           check_bound(INPUT_BOUND - held["allowance"], held), [])
    tighter = limits(4000, capacity=100_000, reservation=32_000)
    expect("a run whose (d) check is the tighter bound has the smaller driver budget",
           (driver_budget(tighter) < driver_budget(held), driver_budget(held)),
           (True, INPUT_BOUND - held["allowance"]))

    # the complete driver payload: the parts a call really sends, and nothing the host adds
    window = "a window of blocks\n" * 40
    packet = ("CALL-ID: r1/S3/t1/0a\nSTAGE: S3\n\nthe principles block\n=== PAYLOAD ===\n" + window).encode("utf-8")
    schema = b'{"type":"object"}'
    own_bytes = len(pathlib.Path(__file__).read_bytes())
    instruction = {"path": str(pathlib.Path(__file__)), "kind": "project"}
    prompt = {"text": "an appended system prompt"}
    plain, plain_problems = driver_bytes(packet, schema)
    expect("done-when 3(a): the gate counts the packet and the schema",
           (plain, plain_problems), (len(packet) + len(schema), []))
    expect("done-when 3(a): ... which is more than the window on its own, so the overhead the bound exists to "
           "include is inside it", plain > len(window.encode("utf-8")), True)
    carried, carried_problems = driver_bytes(packet, schema,
                                             {"instructions": [instruction], "appended_prompts": [prompt]})
    expect("done-when 3(a): the COMPLETE driver payload counts the declared instructions and appended prompts",
           (carried - plain, carried_problems),
           (own_bytes + len(prompt["text"].encode("utf-8")), []))
    expect("done-when 3(a): ... and the planted parts are not zero, so the equality above is not a 0-byte one",
           own_bytes + len(prompt["text"].encode("utf-8")) > 0, True)
    # the host's own context is NOT the driver's part: the allowance already covers it
    expect("the builtin context a host loads by itself is not counted on the driver's side",
           driver_bytes(packet, schema, {"skills": [{"bytes": 9999}], "agents": [{"bytes": 9999}],
                                         "hooks": [{"bytes": 9999}], "workdir_files": [{"bytes": 9999}]})[0],
           plain)
    named("control, done-when 3(a): a declared part this process cannot count is reported, never read as zero",
          driver_bytes(packet, schema, {"instructions": [{"kind": "project"}]})[1], "DRIVER_PART_UNCOUNTED")
    named("control, done-when 3(a): a declared part whose path cannot be read is reported",
          driver_bytes(packet, schema, {"instructions": [{"path": "/nonexistent/instruction.md"}]})[1],
          "DRIVER_PART_UNCOUNTED")

    # BB#1: one read per part. The count, the record and the bytes the host receives come from one
    # snapshot, so an asserted length is only ever something that can disagree with them.
    conflicting = {"name": "stage.md", "text": "P" * 130_000, "bytes": 1}
    named("control, BB#1: a part asserting a length its content contradicts is refused by name",
          driver_bytes(packet, schema, {"appended_prompts": [conflicting]})[1], "DRIVER_PART_LENGTH_CONFLICT")
    named("control, BB#1: ... and it is refused on the recording side too, so neither reader believes it",
          declared_evidence({"appended_prompts": [conflicting]})[1], "DRIVER_PART_LENGTH_CONFLICT")
    expect("control, BB#1: ... and the hash of the full content is not recorded beside the asserted length",
           declared_evidence({"appended_prompts": [conflicting]})[0]["appended_prompts"], [])
    expect("BB#1: an asserted length equal to the content is the content's length",
           part_bytes({"text": "abc", "bytes": 3}), (3, None))
    named("control, BB#1: a length asserted as something other than a whole number is refused",
          [part_bytes({"text": "abc", "bytes": "3"})[1] or ""], "DRIVER_PART_LENGTH_CONFLICT")
    # The files the BB#1 and BC#1 controls write and rewrite live in a scratch directory of their own, never
    # beside this module: the source tree is what the umbrella's other legs read while this one runs.
    import shutil
    import tempfile
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="bound-selftest-"))
    moving, counted_path = scratch / "part.md", scratch / "counted.md"
    source_dir = pathlib.Path(__file__).resolve().parent
    expect("its scratch files live outside the source tree the other umbrella legs read",
           [str(p) for p in (moving, counted_path) if p.resolve().is_relative_to(source_dir)], [])
    try:
        moving.write_bytes(b"the bytes that were counted")
        snapshot, snapshot_problem = part_snapshot({"name": "moving.md", "path": str(moving)})
        moving.write_bytes(b"other bytes entirely, written after the snapshot")
        expect("BB#1: a file edited after its snapshot changes neither the count nor the record",
               (snapshot_problem, part_bytes(snapshot)[0], evidence_of(snapshot)["bytes"],
                evidence_of(snapshot)["sha256"]),
               (None, len(b"the bytes that were counted"), len(b"the bytes that were counted"),
                hashlib.sha256(b"the bytes that were counted").hexdigest()))
        expect("BB#1: ... and the snapshot still carries those exact bytes, which is what is delivered",
               snapshot["body"], b"the bytes that were counted")
    finally:
        moving.unlink(missing_ok=True)
    total, evidence_once, snapshots_once, once_problems = admitted_parts(
        packet, schema, {"instructions": [instruction], "appended_prompts": [prompt]})
    expect("BB#1: the dispatcher's one entry point gives the count, the evidence and the snapshots of one read",
           (once_problems, total, [evidence_of(s) for s in snapshots_once["appended_prompts"]],
            evidence_once["appended_prompts"], snapshots_once["appended_prompts"][0]["body"]),
           ([], carried, evidence_once["appended_prompts"],
            [{"sha256": hashlib.sha256(prompt["text"].encode("utf-8")).hexdigest(),
              "bytes": len(prompt["text"].encode("utf-8"))}], prompt["text"].encode("utf-8")))
    named("control, BB#1: a conflicting length refuses the whole entry point, not one of its three answers",
          admitted_parts(packet, schema, {"appended_prompts": [conflicting]})[3], "DRIVER_PART_LENGTH_CONFLICT")

    # BC#1: exactly one read per path-backed part. The count, the hash and the delivered bytes come off
    # one body, and the asserted length is judged against THAT body - not against a second read, which is
    # what `part_bytes` used to do inside `part_snapshot`.
    real_read_bytes = pathlib.Path.read_bytes
    try:
        counted_path.write_bytes(b"ten bytes!")
        reads = []

        def counting_read(self):
            reads.append(str(self))
            return real_read_bytes(self)

        pathlib.Path.read_bytes = counting_read
        snapshot, snapshot_problem = part_snapshot({"name": "i.md", "path": str(counted_path), "bytes": 10})
        pathlib.Path.read_bytes = real_read_bytes
        expect("BC#1: a path-backed part is read exactly once, asserted length and all",
               (snapshot_problem, reads.count(str(counted_path)),
                (snapshot or {}).get("bytes"), (snapshot or {}).get("body")),
               (None, 1, 10, b"ten bytes!"))
        # ... and a source whose answer CHANGES between reads shows the same thing from the other side:
        # a second read would be judged against the first body's assertion and refuse
        bodies = [b"ten bytes!", b"1"]

        def changing_read(self):
            return bodies.pop(0) if str(self) == str(counted_path) else real_read_bytes(self)

        pathlib.Path.read_bytes = changing_read
        changed, changed_problem = part_snapshot({"name": "i.md", "path": str(counted_path), "bytes": 10})
        pathlib.Path.read_bytes = real_read_bytes
        expect("BC#1: a changing read source is read once, so the snapshot is self-consistent",
               (changed_problem, (changed or {}).get("bytes"), (changed or {}).get("sha256"),
                (changed or {}).get("body"), len(bodies)),
               (None, 10, hashlib.sha256(b"ten bytes!").hexdigest(), b"ten bytes!", 1))
    finally:
        pathlib.Path.read_bytes = real_read_bytes
        shutil.rmtree(scratch, ignore_errors=True)

    # BB#3: an appended system prompt is declared by content; the path form is the instruction file's
    named("control, BB#3: an appended prompt declared by path is refused at declaration",
          declared_evidence({"appended_prompts": [{"name": "stage.md", "path": str(pathlib.Path(__file__))}]})[1],
          "APPENDED_PROMPT_PATH_FORM")
    named("control, BB#3: ... on the counting side as well",
          driver_bytes(packet, schema, {"appended_prompts": [{"path": str(pathlib.Path(__file__))}]})[1],
          "APPENDED_PROMPT_PATH_FORM")
    expect("BB#3: ... while an instruction file's path is read as before",
           declared_evidence({"instructions": [instruction]})[1], [])
    # BC#3: and a declaration carrying BOTH content and a path is refused for the path, before either
    # content branch is taken - that mixture used to pass on its content and be recorded with a `path`
    # the call schema rejects, which is a deterministic failure discovered after the launch
    for label, mixed in (("text and a path", {"name": "stage.md", "text": "hello", "path": "metadata.md"}),
                         ("body and a path", {"name": "stage.md", "body": b"hello", "path": "metadata.md"}),
                         ("a path of None", {"name": "stage.md", "text": "hello", "path": None})):
        named(f"control, BC#3: an appended prompt declared with {label} is refused",
              declared_snapshots({"appended_prompts": [mixed]})[1], "APPENDED_PROMPT_PATH_FORM")
        named(f"control, BC#3: ... and counted nowhere ({label})",
              driver_bytes(b"", None, {"appended_prompts": [mixed]})[1], "APPENDED_PROMPT_PATH_FORM")
    expect("BC#3: ... and no record is produced for it, so nothing reaches the call schema",
           declared_evidence({"appended_prompts": [{"name": "stage.md", "text": "hello",
                                                    "path": "metadata.md"}]})[0]["appended_prompts"], [])

    # every code the dispatcher's part refusal can carry, each fired by a part of that shape: the inventory
    # on the other side reads PART_CODES, so a code that no shape produces, or a shape whose code is not
    # named here, is caught on this side
    planted = {"DRIVER_PART_UNCOUNTED": {"instructions": [{"kind": "project"}]},
               "DRIVER_PART_LENGTH_CONFLICT": {"appended_prompts": [conflicting]},
               "APPENDED_PROMPT_PATH_FORM": {"appended_prompts": [{"path": str(pathlib.Path(__file__))}]}}
    expect("PART_CODES names exactly the refusals a declared part is planted for", sorted(planted), sorted(PART_CODES))
    for code, planted_manifest in planted.items():
        problems = declared_snapshots(planted_manifest)[1]
        named(f"control, PART_CODES: {code} is the leading word of the problem its shape produces",
              [p.split()[0] for p in problems], code)

    # BA#2: one representation - counted from the content, recorded as its hash and length
    evidence, evidence_problems = declared_evidence(
        {"instructions": [{"path": str(pathlib.Path(__file__)), "kind": "project"}],
         "appended_prompts": [{"name": "stage.md", "text": "an appended system prompt"}]})
    expect("BA#2: an appended prompt is counted from its text and recorded as its hash and length",
           (evidence_problems, evidence["appended_prompts"]),
           ([], [{"sha256": hashlib.sha256("an appended system prompt".encode("utf-8")).hexdigest(),
                  "bytes": len("an appended system prompt"), "name": "stage.md"}]))
    expect("BA#2: an instruction file is counted from its bytes and recorded with its path",
           (evidence["instructions"][0]["bytes"], evidence["instructions"][0]["path"]),
           (own_bytes, str(pathlib.Path(__file__))))
    expect("BA#2: the recorded length is the length the payload count counted",
           driver_bytes(b"", None, {"appended_prompts": [{"text": "an appended system prompt"}]})[0],
           evidence["appended_prompts"][0]["bytes"])
    named("control, BA#2: a part that asserts a number instead of content is not evidence",
          declared_evidence({"appended_prompts": [{"name": "x", "bytes": 10}]})[1], "DRIVER_PART_UNCOUNTED")
    named("control, BA#2: a part whose path cannot be read is reported here too",
          declared_evidence({"instructions": [{"path": "/nonexistent/i.md"}]})[1], "DRIVER_PART_UNCOUNTED")
    expect("a manifest with no declared parts is returned unchanged",
           declared_evidence({"skills": [{"bytes": 1}]}), ({"skills": [{"bytes": 1}]}, []))

    # settlement, in both artifact spellings, with the missing-field refusal
    capture = {"input_tokens": 100_000, "cache_creation_input_tokens": 10_000, "cache_read_input_tokens": 5_000}
    rows = [{"state": "measured", "input": 100_000, "cache_creation": 10_000, "cache_read": 5_000}]
    expect("done-when 3(b): observed input is input + cache creation + cache read", observed_of(capture), (115_000, []))
    expect("the two artifact spellings of observed input give one number",
           observed_of(capture)[0], observed_input(rows)[0])
    expect("observed input is the largest request, not their sum",
           observed_input(rows + [{"state": "measured", "input": 7, "cache_creation": 0, "cache_read": 0}])[0],
           115_000)
    expect("an unmeasured request is not observed input",
           observed_input([{"state": "unmeasured", "input": 999_999, "cache_creation": 0, "cache_read": 0}])[0], 0)
    named("control, done-when 3(b): a usage mapping missing a cache field is reported, never read as a smaller number",
          observed_of({"input_tokens": 1})[1], "cache_creation_input_tokens")
    # HB#0: the live reading the stop decision rests on, which runs before anything has been written and
    # must therefore survive every row shape the monitor can be left in
    over_row = {"state": "measured", "input": 135_796, "cache_creation": 0, "cache_read": 0}
    expect("HB#0: a complete row establishes its excess beside a row that cannot be read at all",
           observed_rows([None, over_row]), (135_796, [ROW_UNREADABLE]))
    expect("HB#0: ... and beside a row missing a component, which is listed rather than read as a zero",
           observed_rows([{"state": "measured", "input": 1}, over_row]),
           (135_796, ["cache_creation_input_tokens", "cache_read_input_tokens"]))
    # HC#1: the valid components of a row are a LOWER BOUND, and a lower bound past the bound is an
    # excess - the components that are missing are reported beside it, never instead of it
    expect("HC#1: a partial row's valid components are what that request is known to have put in",
           observed_rows([{"state": "measured", "input": 1, "cache_read": 2}]),
           (3, ["cache_creation_input_tokens"]))
    expect("HC#1: a row whose input alone is past the bound is an excess with a cache field missing",
           (observed_rows([{"state": "measured", "input": 135_796, "cache_read": 0}])[0] > INPUT_BOUND,
            observed_rows([{"state": "measured", "input": 135_796, "cache_read": 0}])[1]),
           (True, ["cache_creation_input_tokens"]))
    expect("HC#4: a negative component is not a count, so it cannot cancel an excess",
           observed_rows([{"state": "measured", "input": 135_796, "cache_creation": 0, "cache_read": -20_000}]),
           (135_796, ["cache_read_input_tokens"]))
    expect("HC#4: a bool component is not a count either",
           observed_rows([{"state": "measured", "input": 135_796, "cache_creation": True, "cache_read": 0}]),
           (135_796, ["cache_creation_input_tokens"]))
    def guarded(fn, *args):
        """What `fn` answered, or what it raised - a reading that must not raise is judged by a control
        that can SAY it raised, rather than dying with it (BD#4)."""
        try:
            return fn(*args)
        except Exception as exc:                   # noqa: BLE001 - the raise IS the finding
            return f"raised: {exc!r}"

    expect("HC#0: a container that cannot even be walked is reported, not raised",
           guarded(observed_rows, 7), (0, [ROW_UNREADABLE]))
    # HC#1: and the two readers cannot disagree, because they are one reading
    shapes = ([], [None], 7, [{"state": "measured", "input": 135_796, "cache_read": 0}],
              [{"state": "measured", "input": 1, "cache_creation": 0, "cache_read": 2}],
              [{"state": "measured", "input": -1, "cache_creation": 0, "cache_read": 0}],
              [{"state": "measured", "input": True, "cache_creation": 0, "cache_read": 0}],
              [{"state": "sent", "input": 999_999, "cache_creation": 0, "cache_read": 0}],
              [{"state": "measured", "input": 2, "cache_creation": 0, "cache_read": 0},
               {"state": "measured", "input": 135_796, "cache_creation": 0, "cache_read": 0}])
    expect("HC#1: the live rows and the written record are read by one policy",
           [guarded(observed_rows, shape) for shape in shapes],
           [guarded(observed_input, shape) for shape in shapes])
    expect("control, HC#1: and that table is not empty, nor all one answer",
           (len(shapes) >= 9, len({str(guarded(observed_rows, shape)) for shape in shapes}) > 1), (True, True))
    expect("HB#0: an unmeasured row is not a live observation either",
           observed_rows([{"state": "sent", "input": 999_999, "cache_creation": 0, "cache_read": 0}])[0], 0)
    expect("HB#0: the reading raises on no shape it can be given",
           [observed_rows(rows_in)[0] for rows_in in
            (None, [], [None], ["not a row"], [{"state": "measured", "input": "x"}], [over_row])],
           [0, 0, 0, 0, 0, 135_796])
    named("observed input: a view-window call within 120k is accepted", check_observed(INPUT_BOUND, True))
    named("control, observed input: a view-window call above 120k is a host change",
          check_observed(INPUT_BOUND + 1, True), STOP_CODE)
    named("observed input: the same observation on a call that carries no view window is accepted, so the R "
          "authoring of §8.6 keeps its own section's contract", check_observed(136_000, False))

    # the one record, and the one way back
    stop = committed(excess("r1/S3/t1/0a", 135_796, "2026-10-22T09:00:00+09:00"), 2)
    expect("the committed excess record carries the sequence recovery is measured from",
           (stop["code"], stop["declaration_seq"], stop["observed"]), (STOP_CODE, 2, 135_796))
    named("the excess record's detail names the call and the bound", [stop["detail"]], "r1/S3/t1/0a")
    expect("dispatch is open before any excess is recorded", blocked(None, []), None)
    named("an excess blocks dispatch", [blocked(stop, []) or ""], f"RUN_STOPPED {STOP_CODE}")
    later_unrelated = [{"seq": 3, "diff": {"caps.S3": 1}}]
    named("control, M4: an amendment of another key does not lift the stop",
          [blocked(stop, later_unrelated) or ""], STOP_CODE)
    earlier = [{"seq": 1, "diff": {"host_allowance.claude:claude-sonnet-5-5/xhigh": 4000}}]
    named("control, M4: a host_allowance amendment recorded EARLIER than the excess does not lift it",
          [blocked(stop, earlier) or ""], STOP_CODE)
    same_seq = [{"seq": 2, "diff": {"host_allowance.x": 1}}]
    named("control, M4: a host_allowance amendment at the same sequence does not lift it",
          [blocked(stop, same_seq) or ""], STOP_CODE)
    later = [{"seq": 3, "diff": {"host_allowance.claude:claude-sonnet-5-5/xhigh": 4200}}]
    expect("M4: a host_allowance amendment recorded after the excess lifts the stop", blocked(stop, later), None)
    expect("M4: ... and the excess record is still there, so recovery does not forget it",
           (stop["call_id"], stop["observed"]), ("r1/S3/t1/0a", 135_796))
    # BD#0: a stop never weakens. Two calls can settle an excess in one run, and the entry kept is the
    # stronger - which is what keeps an unstamped stop from being replaced by a stamped one an amendment
    # can then pass.
    unstamped = {**excess("r1/S3/t1/0a", 135_796, "now"), "stamp": "lock-timeout: declaration"}
    stamped_low = committed(excess("r1/S3/t1/0b", 130_001, "now"), 2)
    stamped_high = committed(excess("r1/S3/t1/0c", 130_002, "now"), 5)
    expect("BD#0: the first stop of a run is kept", strongest(None, unstamped), unstamped)
    expect("BD#0: an unstamped stop is terminal, so no later stamped stop replaces it",
           strongest(unstamped, stamped_high), unstamped)
    expect("control, BD#0: ... and the run is still blocked after an amendment later than that stamp",
           blocked(strongest(unstamped, stamped_high), [{"seq": 9, "diff": {"host_allowance.a": 1}}]) is not None,
           True)
    expect("BD#0: between two stamped stops the higher sequence is kept",
           (strongest(stamped_low, stamped_high), strongest(stamped_high, stamped_low)),
           (stamped_high, stamped_high))
    expect("control, BD#0: ... so an amendment between the two sequences does not lift the run",
           blocked(strongest(stamped_low, stamped_high), [{"seq": 3, "diff": {"host_allowance.a": 1}}]) is not None,
           True)
    expect("BD#0: an equal sequence keeps what is already recorded",
           strongest(stamped_low, committed(excess("x", 1, "now"), 2)), stamped_low)
    expect("BD#0: a stop this rule does not own is terminal and is not replaced",
           strongest({"code": "PROVIDER_DEFERRED", "call_id": "x"}, stamped_high)["code"], "PROVIDER_DEFERRED")
    expect("BD#0: an unstamped stop offered against a stamped one is the stronger",
           strongest(stamped_low, unstamped), unstamped)
    expect("BD#0: terminal is the shape nothing lifts, in both of its forms",
           (terminal(None), terminal(unstamped), terminal(stamped_low),
            terminal({"code": "PROVIDER_DEFERRED", "declaration_seq": 2})),
           (False, True, False, True))

    other = {"code": "PROVIDER_DEFERRED", "call_id": "r1/S3/t1/0b", "declaration_seq": 2}
    expect("a stop this rule does not own is not lifted by a host_allowance amendment",
           lifted(other, later), False)
    named("... and it still blocks dispatch under its own code", [blocked(other, later) or ""], "RUN_STOPPED")
    expect("a bound stop with no declaration sequence is not lifted by anything",
           lifted({"code": STOP_CODE, "call_id": "x"}, later), False)
    expect("control, BA#0: an uncommitted excess record carries no sequence, so nothing lifts it",
           ("declaration_seq" in excess("x", 1, "now"),
            lifted(excess("x", 1, "now"), later)), (False, False))
    expect("control, BA#0: the sequence a stop is stamped with is the one the COMMIT read, not the call's",
           (committed(excess("x", 1, "now"), 7)["declaration_seq"],
            lifted(committed(excess("x", 1, "now"), 7), [{"seq": 5, "diff": {"host_allowance.a": 1}}]),
            lifted(committed(excess("x", 1, "now"), 7), [{"seq": 8, "diff": {"host_allowance.a": 1}}])),
           (7, False, True))

    # ... and neither invented number may come back
    import inspect
    signature = inspect.signature(limits)
    for name in ("capacity", "reservation"):
        if signature.parameters[name].default is not inspect.Parameter.empty:
            failures.append(f"limits() has a default for {name}, so a caller can fall back on a number nobody chose")
    # a module-level constant is an assignment at column 0, which is what this looks for - the names
    # appear in this file's own prose, and a text search would match itself
    back = re.search(r"^(OUTPUT_RESERVATION|CONTEXT_CAPACITY)\s*=", source_text(), re.M)
    if back:
        failures.append(f"a module-level {back.group(1)} constant is back, so a caller can fall back on it")

    # the module is pure: a second opinion about where the run's state lives is what it exists to prevent
    source = source_text()
    for forbidden in ("from runlib", "import runlib", "open(", "subprocess"):
        if forbidden in source.split('"""The window bound', 1)[-1].split("def self_test", 1)[0]:
            failures.append(f"bound.py reaches for {forbidden!r} outside its self-test, so the rule has state of its own")

    for line in failures:
        print(f"bound --self-test [FAIL] {line}")
    if failures:
        return 1
    print("bound --self-test: OK (the bound's two pre-dispatch checks, the complete driver payload with its "
          "uncountable-part refusals, one read per declared part with its conflicting-length and path-form "
          "refusals, observed-input settlement in both artifact spellings, the single excess record, and the "
          "recovery rule's five cases)")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else
             (print(json.dumps({"INPUT_BOUND": INPUT_BOUND, "PACKET_OVERHEAD": PACKET_OVERHEAD,
                                "STOP_CODE": STOP_CODE, "AMENDED_KEY": AMENDED_KEY}, indent=2)) or 0))
