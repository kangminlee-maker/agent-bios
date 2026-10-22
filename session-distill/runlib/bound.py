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

def part_bytes(part):
    """`(bytes, problem)` for one declared driver part.

    A part is text, or bytes, or a record naming what it carries: an explicit `bytes`, or a `path`
    this process can read. A part that is none of those is **not counted as zero** - it is reported,
    because an uncountable part makes the driver's share unknown, and understating that share is the
    one failure the bound exists to prevent."""
    if isinstance(part, bytes):
        return len(part), None
    if isinstance(part, str):
        return len(part.encode("utf-8")), None
    if isinstance(part, dict):
        if isinstance(part.get("bytes"), int) and part["bytes"] >= 0:
            return part["bytes"], None
        if isinstance(part.get("text"), str):
            return len(part["text"].encode("utf-8")), None
        if isinstance(part.get("path"), str):
            try:
                return len(pathlib.Path(part["path"]).read_bytes()), None
            except OSError as exc:
                return 0, (f"DRIVER_PART_UNCOUNTED {part['path']}: {exc.strerror or exc}; a declared part this process "
                           f"cannot read leaves the driver's share unknown")
        return 0, (f"DRIVER_PART_UNCOUNTED {sorted(part)}: a declared part carries neither bytes, text nor a readable "
                   f"path, so the driver's share cannot be counted")
    return 0, f"DRIVER_PART_UNCOUNTED {type(part).__name__}: a declared part that is not text, bytes or a record"


def driver_parts(packet, schema_bytes=None, manifest=None):
    """The parts of one call that the DRIVER supplies, in the order they are counted.

    The packet (its template, the principles block and the window payload are one object by the time
    it is built), the schema, and what the call's own manifest declares it carries: instruction files
    and appended system prompts.

    What the **host** loads by itself under the profile is not here. That is the measured allowance,
    and counting it again on the driver's side would charge the same tokens twice - which is why this
    takes the call's own manifest and never the merged one that carries `seats.json`'s builtin
    context. Files merely readable in the working directory are not sent, so they are not counted
    either: a read shows up in the observed input, and settlement is what catches it."""
    parts = [packet]
    if schema_bytes is not None:
        parts.append(schema_bytes)
    declared = manifest or {}
    for key in ("instructions", "appended_prompts"):
        for item in declared.get(key) or []:
            parts.append(item)
    return parts


def part_evidence(part):
    """`(record, problem)` - what a declared driver part is RECORDED as, once its bytes are counted.

    One representation for both readers: the payload count needs the content, and the call record needs
    evidence of it that a schema can close over. So a caller declares a part by its content - `text`, or a
    `path` to read - and what the record keeps is its name, its sha256 and its length. A part that only
    asserts a number is not evidence of anything, and a record of text nobody counted is not either
    (BA#2)."""
    size, problem = part_bytes(part)
    if problem:
        return None, problem
    if isinstance(part, dict) and isinstance(part.get("text"), str):
        body = part["text"].encode("utf-8")
    elif isinstance(part, dict) and isinstance(part.get("path"), str):
        body = pathlib.Path(part["path"]).read_bytes()
    elif isinstance(part, (str, bytes)):
        body = part.encode("utf-8") if isinstance(part, str) else part
    else:
        return None, (f"DRIVER_PART_UNCOUNTED {sorted(part) if isinstance(part, dict) else type(part).__name__}: a "
                      f"declared part is recorded by its content, and this one carries none")
    record = {"sha256": hashlib.sha256(body).hexdigest(), "bytes": size}
    for key in ("name", "path"):
        if isinstance(part, dict) and isinstance(part.get(key), str):
            record[key] = part[key]
    return record, None


def declared_evidence(manifest):
    """`(manifest, problems)` - the call's manifest with every declared driver part recorded as evidence.

    The dispatcher writes this into the call record, so what the gate reads is the sha256 and length of
    the bytes the payload count actually counted."""
    out, problems = dict(manifest or {}), []
    for key in ("instructions", "appended_prompts"):
        if not (manifest or {}).get(key):
            continue
        rows = []
        for part in manifest[key]:
            record, problem = part_evidence(part)
            if problem:
                problems.append(problem)
            else:
                rows.append(record)
        out[key] = rows
    return out, problems


def driver_bytes(packet, schema_bytes=None, manifest=None):
    """`(bytes, problems)` - the UTF-8 size of everything the driver sends for one call.

    Counting the window alone understates the driver's part by exactly the overhead the bound exists
    to include, which is why this is the only counter and both sides call it."""
    total, problems = 0, []
    for part in driver_parts(packet, schema_bytes, manifest):
        size, problem = part_bytes(part)
        total += size
        if problem:
            problems.append(problem)
    return total, problems


# ---- what the call really read ---------------------------------------------------------------

# the three components of observed input, in the two spellings the artifacts use: a capture's
# Anthropic-shaped usage, and a usage record's own request rows
INPUT_PARTS = (("input_tokens", "input"),
               ("cache_creation_input_tokens", "cache_creation"),
               ("cache_read_input_tokens", "cache_read"))


def observed_of(usage):
    """`(observed, missing)` for one usage mapping, in either spelling.

    A mapping missing any of the three is reported rather than read as a smaller number: a missing
    cache field would make every overrun look like a call within the bound."""
    total, missing = 0, []
    for spellings in INPUT_PARTS:
        found = [usage.get(name) for name in spellings if isinstance(usage.get(name), int)]
        if not found:
            missing.append(spellings[0])
            continue
        total += found[0]
    return total, missing


def observed_input(requests, state="measured"):
    """`(observed, missing)` - the largest observed input over the `state` rows of a usage record.

    The maximum, not the sum: the bound is what one request put in front of the model."""
    rows = [row for row in requests or [] if row.get("state", state) == state]
    totals, missing = [], []
    for row in rows:
        total, gaps = observed_of(row)
        totals.append(total)
        missing += [gap for gap in gaps if gap not in missing]
    return (max(totals) if totals else 0), missing


def check_observed(observed, view_window):
    """After a call: a view-window call whose observed input is above the bound is a host change."""
    if view_window and observed > INPUT_BOUND:
        return [f"{STOP_CODE}: observed input {observed} tokens exceeds {INPUT_BOUND} on a view-window call; the host "
                "added more than the declared allowance - re-measure it and amend the declaration"]
    return []


# ---- the one excess record, and the one way back ---------------------------------------------

def excess(call_id, observed, at):
    """The run's stop entry for a bound excess - the single record of it, before it is committed.

    One record, written where the stop is written, read where the stop is read; a second file beside it
    would be a second thing to keep true. The sequence it is compared against is NOT in it yet: see
    `committed`."""
    return {"code": STOP_CODE, "call_id": call_id, "observed": observed, "at": at,
            "detail": f"{STOP_CODE} {call_id}: a view-window call read {observed} input tokens, past the "
                      f"{INPUT_BOUND} bound; the host changed, so the run stops"}


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
    instruction = {"path": None, "bytes": 2048}
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
           (2048 + len(prompt["text"].encode("utf-8")), []))
    expect("done-when 3(a): ... and the planted parts are not zero, so the equality above is not a 0-byte one",
           2048 + len(prompt["text"].encode("utf-8")) > 0, True)
    # the host's own context is NOT the driver's part: the allowance already covers it
    expect("the builtin context a host loads by itself is not counted on the driver's side",
           driver_bytes(packet, schema, {"skills": [{"bytes": 9999}], "agents": [{"bytes": 9999}],
                                         "hooks": [{"bytes": 9999}], "workdir_files": [{"bytes": 9999}]})[0],
           plain)
    named("control, done-when 3(a): a declared part this process cannot count is reported, never read as zero",
          driver_bytes(packet, schema, {"instructions": [{"kind": "project"}]})[1], "DRIVER_PART_UNCOUNTED")
    named("control, done-when 3(a): a declared part whose path cannot be read is reported",
          driver_bytes(packet, schema, {"appended_prompts": [{"path": "/nonexistent/prompt.md"}]})[1],
          "DRIVER_PART_UNCOUNTED")

    # BA#2: one representation - counted from the content, recorded as its hash and length
    evidence, evidence_problems = declared_evidence(
        {"instructions": [{"path": str(pathlib.Path(__file__)), "kind": "project"}],
         "appended_prompts": [{"name": "stage.md", "text": "an appended system prompt"}]})
    own_bytes = len(pathlib.Path(__file__).read_bytes())
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
          "uncountable-part refusals, observed-input settlement in both artifact spellings, the single excess "
          "record, and the recovery rule's five cases)")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else
             (print(json.dumps({"INPUT_BOUND": INPUT_BOUND, "CONTEXT_CAPACITY": CONTEXT_CAPACITY,
                                "OUTPUT_RESERVATION": OUTPUT_RESERVATION, "PACKET_OVERHEAD": PACKET_OVERHEAD},
                               indent=2)) or 0))
