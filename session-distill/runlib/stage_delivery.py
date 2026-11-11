#!/usr/bin/env python3
"""S5b, the delivery evidence (WP-11b): the producer of what `delivery_evidence.delivery()` judges.

WP-10's `runlib/delivery_evidence.py` answers, for one unit in one session before one decision, whether the unit was
`delivered`, `exposed_not_read`, `selected_unavailable`, `not_delivered` or `unknown`, by design §6.3. It was built and
judged on frozen fixtures. This stage is the half that was missing: the evidence itself, assembled from the records the
run already holds, written as `delivery-evidence.json` under the run so S6 can read one answer per (session, unit,
decision) instead of recomputing it.

The stage runs between S5 and S6 as `distill.py deliver --run-id ID`. It is `S5b` in `records.STAGES`, inserted
between `S5` and `S6` rather than appended, because `declare.py` derives an amendment's invalidation range from
`STAGES.index` and sorts by it: a stage appended after `S12` would be invalidated and ordered as though it ran last.

**What it reads, and nothing else.** `checks.json` (S5) for the candidates and the decision events they cite, the
inventory (S2) for pins, selection, injection and native events, the in-force windows and each unit's operative
context, and the run's own immutable copy of the session records (`sources/<version_sha>.jsonl`, written by S2, mode
0444) for the tool calls that read a guide file back. The immutable copy is the only acquisition: this stage never
reads the owner's `~/.claude` or `~/.codex`.

**What it writes.** Names, ids, hashes, line counts, states and reasons, with a per-requirement coverage summary. Never
the bytes a session read, and never session text. The raw copy is read because the clipped views cannot carry a
read's returned bytes, and nothing read from it leaves this process except as a count or a hash.

**`read_unparsed` means the HOST elided the result.** A tool result this run clipped for a view is not a reason: the
clip is ours, and this stage does not read views at all. A call whose returned bytes the host truncated or replaced is
`unknown` with that reason, never `exposed_not_read`, because a miss is not claimed from evidence nobody read.

**The pairs it owes an answer for** come from the artifacts' own shapes: a check row's `retrieved_units` and
`named_units_absent` (`checks.schema.json`), the sessions and decision events of S4's `candidates.json`, and the
record ordinal in an event record's `at_record`. That ordinal is the scale `delivery()` takes `decision_at` on. The
inventory's own native and injection events carry an instant and a line instead, and are read where they are used.

**The unit's operative context is the judge's one-step set** — `edges.direct` plus `edges.reached`, published on every
current unit (plan WP-11 D1 (a1)) — never the transitive `operative_context` closure beside it and never a
recomputation of mentions. An inventory that publishes no edges is refused by name.

Commit 1 of this package landed the stage's frame: its place in `records.STAGES`, its admission through
`records.run_stage`, its two refusals, and the document's shape. Commit 2 anchored the enumeration on the artifacts
above, and the session evidence follows. Until it does, every pair is `unknown` with the reason
`delivery_assembly_pending` and the document says `complete: false`. That is this stage's per-pair state inside a file
that EXISTS; S6's `delivery_assembly_waiting` is its state when no such file exists at all. A pending answer is
written as one rather than left out, so a reader can tell "no evidence assembled yet" from "evidence that found
nothing".

  stage_delivery.py --self-test
"""
import json
import pathlib
import re
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import bound, delivery_evidence, derive, dispatch, projection, records  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
STAGE = "S5b"
OUTPUT = "delivery-evidence.json"
SOURCES_DIR = "sources"
EVENTS_DIR = "events"
VIEWS_FILE = "views.json"
# Admitted against every producer whose records this stage reads, so the shared staleness judgement applies: a
# `checks.json` or an inventory written again after this stage ran makes the next reader refuse rather than trust it.
INPUTS = ({"artifact": "checks.json", "producer_stage": "S5"},
          {"artifact": VIEWS_FILE, "producer_stage": "S2"},
          {"artifact": "candidates.json", "producer_stage": "S4"},
          {"artifact": "inventory/current.json", "producer_stage": "S2"},
          {"artifact": "inventory/sessions.json", "producer_stage": "S2"},
          {"artifact": "inventory/release.json", "producer_stage": "S2"})
# This stage's own per-pair state inside a file that EXISTS, and not to be read as lane E's
# `delivery_assembly_waiting`, which is S6's state when no such file exists at all. One says "the
# evidence readers have not answered this pair yet", the other says "there is nothing to read".
PENDING = "delivery_assembly_pending"


def sources_present(run_dir):
    """The immutable copies S2 left, by file name. Empty is not an error here; `run` decides."""
    root = pathlib.Path(run_dir) / SOURCES_DIR
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_file())


def standing_stop(run_dir):
    """The run's standing stop as the dispatcher's own rule reads it, or None.

    Read rather than assumed absent: this stage writes a document S6 will judge candidates by, and a run that stopped
    at a cap has evidence only up to the stop. The source is the supervisor's ledger, through `bound`, so there is one
    reading of "stopped" in the driver and not a second one here."""
    run_dir = pathlib.Path(run_dir)
    ledger_path = dispatch.run_ledger_path(run_dir)
    if not ledger_path.is_file():
        return None
    held = records.read_json(ledger_path)
    stops = bound.as_stops(held.get("stops", held.get("stopped")))
    if not stops:
        return None
    # Only a later amendment of a stop's own key lifts it, so the amendments decide which stops still stand. A
    # declaration this stage cannot read is read as "unread" rather than as "no amendment": `bound` holds every
    # recorded stop standing in that case, which is the direction that cannot read a stopped run as open. The run is
    # refused either way — here by name, or by `run_stage` as undeclared — and never written to.
    try:
        _run, _digest, amendments = records.declaration_state(run_dir, who=STAGE)
    except Refused:
        amendments = None
    return bound.blocked(stops, amendments)


def decisions_of(run_dir):
    """`{event_id: (transcript file stem, record ordinal)}` over the event records S3 wrote.

    The decision a candidate concerns is an EVENT, and an event record names its place as
    `at_record`, whose first component is the record's ordinal in that transcript ("76837/message/
    content"). That ordinal is the scale `delivery_evidence.delivery()` takes `decision_at` on and
    the scale a read's `at` is on, so the mapping is made once, here, rather than in each reader.

    The inventory's own events carry an ISO instant in `at` and the line in `line`; they are a
    different record set (the native and injection events of a session) and are read where they are
    used, never mixed with these ids."""
    found = {}
    root = pathlib.Path(run_dir) / EVENTS_DIR
    if not root.is_dir():
        return found
    for path in sorted(root.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            at_record = row.get("at_record")
            head = str(at_record or "").split("/")[0]
            found[row.get("event_id")] = (path.stem, int(head) if head.isdigit() else None)
    return found


def sessions_index(sessions):
    """`{"host:id": session row}` and `{transcript id: session row}` over the inventory's sessions.

    A candidate names its sessions as `host:id` (S4's spelling) and an event record is named by its
    transcript file; the inventory's rows carry both, so both ways in are built from the one
    document rather than guessed at either end."""
    by_name, by_transcript = {}, {}
    for row in sessions.get("sessions") or []:
        if row.get("session"):
            by_name[row["session"]] = row
        transcript = (row.get("transcript") or {}).get("id")
        if transcript:
            by_transcript[transcript] = row
    return by_name, by_transcript


def pairs_of(checks, candidates, decisions, by_name, by_transcript):
    """Every (session, unit, decision) this run owes an answer for.

    Re-anchored on the artifacts' own shapes (WP-11b commit 2). Commit 1 read `session_ref`,
    `unit_ids` and `decision_at` off a check row; `checks.schema.json` has none of those. A check
    row carries `candidate_id`, `retrieved_units` and `named_units_absent`; the sessions and the
    decision events are S4's, in `candidates.json`. The controls then tested a shape chosen here
    rather than one anybody writes, which is why this is anchored to the schema and exercised on a
    real run's artifacts.

    A pair is owed per (decision event, unit): the event fixes both the session — the transcript its
    record belongs to — and the ordinal. A candidate with no readable event keeps one pair per unit
    with `decision_at` None, and a candidate naming no unit keeps a pair with `unit_id` None:
    either way the pair is answered with a reason rather than dropped, because a denominator that
    shrinks silently is the one number nobody can check."""
    units_by_candidate = {}
    for row in checks.get("candidates") or []:
        named = [u["unit_id"] for u in row.get("retrieved_units") or [] if u.get("unit_id")]
        units_by_candidate[row.get("candidate_id")] = named + list(row.get("named_units_absent") or [])
    owed = []
    for row in candidates.get("candidates") or []:
        cid = row.get("candidate_id")
        units = units_by_candidate.get(cid) or [None]
        events = []
        for event_id in row.get("event_ids") or []:
            stem, ordinal = decisions.get(event_id, (None, None))
            transcript = (stem or "").split("_", 1)[-1] if stem else None
            session = by_transcript.get(transcript)
            events.append({"event_id": event_id, "decision_at": ordinal,
                           "session_ref": (session or {}).get("session_ref"),
                           "session": (session or {}).get("session"),
                           "reason": None if ordinal is not None and session else
                                     ("event_record_absent" if ordinal is None else "session_unmatched")})
        if not events:
            # The candidate's own sessions, so the pair still names where it would be judged.
            for name in row.get("sessions") or [None]:
                session = by_name.get(name) if name else None
                events.append({"event_id": None, "decision_at": None,
                               "session_ref": (session or {}).get("session_ref"), "session": name,
                               "reason": "no_decision_event"})
        for event in events:
            for unit in units:
                owed.append({"candidate_id": cid, "unit_id": unit, **event})
    return owed


def selected_items(shared, store):
    """`{item_ref: surface}` of a shared selection inventory, as far as the INVENTORY states it.

    The items a session received, and the surface each was selected at, are the SNAPSHOT's
    (`inventory.snapshot_shape`: `items`, `output.unavailable`, `output.instruction_text`), and a
    snapshot lives in the owner's state root — not in this run. S2 is what reads it; S5b reads what
    S2 published, because moving that acquisition here would make the stage read the owner's state
    directly and would make S2's recorded failure unverifiable.

    S2 publishes the snapshot's `items` with their surfaces (the fact-only half of the lead's
    boundary decision), so a published surface is the snapshot's own answer. An item the carriers
    name and the items block does not is held with a surface of None, and the judge then answers the
    levels that need a surface as unknown rather than guessing one — which is what EVERY item read
    as before that block existed."""
    stated = {item.get("ref"): item.get("surface") for item in shared.get("items") or []
              if isinstance(item, dict) and item.get("ref")}
    held = {}
    for carrier in shared.get("carriers") or []:
        version = ((store.get("versions") or {}).get(carrier.get("carrier_id")) or {}).get(
            carrier.get("version_sha256")) or {}
        if version.get("item_ref"):
            held[version["item_ref"]] = stated.get(version["item_ref"])
    return held


# A published coverage row whose `r-` reference names no unit of this run. It is NOT a dropped row:
# a drop is a resolution failure, and a block that lost every row to one would read like a block that
# was never published — which is a different answer about the same session.
UNRESOLVED = "coverage_ref_unresolved"
# A pair one of the judge's inputs is missing for. The reasons already name WHICH input, so this is
# the statement that the state beside them is this stage's and not §6.3's.
UNJUDGED = "delivery_unjudged"


def pointer_facts(shared):
    """`{item_ref: pointer}` from the selection inventory's published predicate over the compiled text.

    A row whose `pointer` is None says the surface has no pointer to find at all; it is carried as
    None rather than dropped, because the judge's reader distinguishes "nothing to find" from "not
    found" and a dropped row would send it back to a text this run does not hold."""
    return {row["ref"]: row.get("pointer") for row in shared.get("item_pointer_in_compiled_text") or []
            if isinstance(row, dict) and isinstance(row.get("ref"), str)}


def surface_facts(shared):
    """`{unit_ref: surface}` of every unit this selection holds, as S2 published it.

    Keyed by the inventory's reference, like the coverage counts, and translated per pair. A unit
    with a null surface is held as None: the judge then answers `surface_unclassified`, which is the
    honest answer for a unit whose item neither the snapshot nor the baseline named."""
    return {row["unit_ref"]: row.get("surface") for row in shared.get("unit_surfaces") or []
            if isinstance(row, dict) and isinstance(row.get("unit_ref"), str)}


def coverage_facts(shared, units):
    """`({unit_id: {covered, total}}, [reference nothing here resolves])` from the published counts.

    The counts S2 publishes are keyed by the inventory's `r-` reference, and the judge asks about a
    `unit_id`, so this translates between them over the units of the run. A reference that resolves
    to no unit is RETURNED rather than dropped, because the two outcomes are not the same claim: a
    fact that could not be attached is a resolution failure this run should say out loud, while
    silence would make a block whose every row failed indistinguishable from a session whose
    inventory published no block at all.

    The compiled instruction text itself is never in the run (lead decision, WP-11b), so these
    counts are the only way `delivery_evidence.in_compiled_text` can answer at all. A session whose
    inventory publishes none reads unknown by `compiled_text_unavailable`; one whose rows did not
    resolve reads unknown by `coverage_ref_unresolved`; neither is ever `not_delivered`."""
    ids = {}
    for unit in units:
        ids.setdefault(unit.get("unit_ref"), []).append(unit.get("unit_id"))
    facts, unresolved = {}, []
    for row in shared.get("instruction_coverage") or []:
        held = ids.get(row.get("unit_ref")) or []
        if not held:
            unresolved.append(row.get("unit_ref"))
            continue
        for unit_id in held:
            facts[unit_id] = {"covered": row.get("covered"), "total": row.get("total")}
    return facts, sorted(ref for ref in unresolved if isinstance(ref, str))


# The tools whose input NAMES the file it returned. A reader of this kind is unambiguous: the path is
# the call's own argument, not a guess about a command line.
NAMED_READERS = {"Read", "NotebookRead", "view", "read_file"}
# The tools that run a command, where the path has to be read out of the command text.
SHELL_READERS = {"Bash", "shell", "local_shell", "container.exec"}
# A command that returns a file's bytes. `grep` is one: it returns the lines it matched, which can
# cover a requirement.
READING_VERBS = ("cat", "sed", "head", "tail", "less", "more", "bat", "grep", "rg", "awk")
PATH_TOKEN = re.compile(r"[\w./@~+-]*\.(?:md|markdown|json|toml|txt|ya?ml)")


def _text_of(content):
    """A tool result's returned text, or None when this run cannot read it back as text.

    None is `read_unparsed` material: a result the host elided, a structured payload, an image. A
    miss is never claimed from a call whose bytes were not read, so the difference between "no text
    here" and "text that did not cover the requirement" is kept."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [block.get("text") for block in content
                 if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)]
        return "\n".join(parts) if parts else None
    return None


def _paths_in(command):
    """The file paths a shell command names, in order, as far as a conservative reading goes."""
    return [match.group(0) for match in PATH_TOKEN.finditer(command or "")
            if "/" in match.group(0) or match.group(0).startswith(".")]


def _claude_reads(lines):
    """(reads, unparsed, counts) over a Claude transcript version's records.

    A read is attributed to the line of its RESULT, because that is when the bytes reached the
    session: the call records the intent, the result records what came back, and the judge asks what
    the session had read BEFORE the decision."""
    calls, reads, unparsed = {}, [], []
    counts = {"results": 0, "errors": 0, "no_text": 0, "unnamed_command": 0}
    for at, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        content = ((row.get("message") or {}).get("content"))
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                calls[block.get("id")] = (block.get("name"), block.get("input") or {})
                continue
            if block.get("type") != "tool_result":
                continue
            counts["results"] += 1
            name, arguments = calls.get(block.get("tool_use_id"), (None, {}))
            if name is None:
                continue
            if block.get("is_error"):
                counts["errors"] += 1
                continue
            returned = _text_of(block.get("content"))
            if name in NAMED_READERS:
                path = arguments.get("file_path") or arguments.get("path") or arguments.get("notebook_path")
                if not path:
                    continue
                if returned is None:
                    counts["no_text"] += 1
                    unparsed.append({"at": at, "path": path, "reason": "result_not_text"})
                else:
                    reads.append({"at": at, "path": path, "returned": returned})
            elif name in SHELL_READERS:
                command = arguments.get("command") or arguments.get("script") or ""
                if not any(verb in command for verb in READING_VERBS):
                    continue
                named = _paths_in(command)
                if not named:
                    counts["unnamed_command"] += 1
                    unparsed.append({"at": at, "path": None, "reason": "command_names_no_path"})
                elif returned is None:
                    counts["no_text"] += 1
                    unparsed += [{"at": at, "path": path, "reason": "result_not_text"} for path in named]
                else:
                    reads += [{"at": at, "path": path, "returned": returned} for path in named]
    return reads, unparsed, counts


def _codex_reads(lines):
    """The same over a Codex rollout: `function_call` / `custom_tool_call` and their outputs."""
    calls, reads, unparsed = {}, [], []
    counts = {"results": 0, "errors": 0, "no_text": 0, "unnamed_command": 0}
    for at, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        payload = row.get("payload") or {}
        kind = payload.get("type")
        if kind in ("function_call", "custom_tool_call"):
            arguments = payload.get("arguments") or payload.get("input") or ""
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {"command": arguments}
            calls[payload.get("call_id")] = (payload.get("name"), arguments if isinstance(arguments, dict) else {})
            continue
        if kind not in ("function_call_output", "custom_tool_call_output"):
            continue
        counts["results"] += 1
        name, arguments = calls.get(payload.get("call_id"), (None, {}))
        if name is None:
            continue
        output = payload.get("output")
        returned = output if isinstance(output, str) else _text_of(output)
        command = arguments.get("command")
        if isinstance(command, list):
            command = " ".join(str(part) for part in command)
        if name in NAMED_READERS:
            path = arguments.get("path") or arguments.get("file_path")
            if not path:
                continue
            if returned is None:
                counts["no_text"] += 1
                unparsed.append({"at": at, "path": path, "reason": "result_not_text"})
            else:
                reads.append({"at": at, "path": path, "returned": returned})
        elif name in SHELL_READERS or command:
            if not any(verb in (command or "") for verb in READING_VERBS):
                continue
            named = _paths_in(command)
            if not named:
                counts["unnamed_command"] += 1
                unparsed.append({"at": at, "path": None, "reason": "command_names_no_path"})
            elif returned is None:
                counts["no_text"] += 1
                unparsed += [{"at": at, "path": path, "reason": "result_not_text"} for path in named]
            else:
                reads += [{"at": at, "path": path, "returned": returned} for path in named]
    return reads, unparsed, counts


def reads_of(copy_path, host):
    """(reads, unparsed, counts) read from ONE immutable copy of a transcript version.

    The copy S2 wrote is the only place these bytes are read from: the views are clipped, so they
    cannot carry what a result returned, and the owner's own files are not this stage's to open. The
    bytes stay in this process — the document carries counts, paths and states, never text."""
    path = pathlib.Path(copy_path)
    if not path.is_file():
        return [], [], {"copy_missing": True}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    reads, unparsed, counts = (_codex_reads(lines) if host == "codex" else _claude_reads(lines))
    return reads, unparsed, {**counts, "records": len(lines)}


def copies_of(views):
    """`{session or transcript ref: (the copy's path under the run, host)}` from S2's manifest."""
    found = {}
    for row in views.get("transcripts") or []:
        copy = row.get("source_copy")
        if not copy:
            continue
        for key in (row.get("session"), row.get("transcript"), row.get("name")):
            if key:
                found[key] = (copy, row.get("host"))
    return found


def basis_of(session_row, shared_of, store):
    """`(basis, pin_reason, selected, history_selected)` for one session, from the inventory's row.

    `basis` is what the judge's `_selection` reads: `pin` when the pin was read and a selection
    inventory answers for it, `selection_history` when the owner's library history is what answers,
    and None otherwise — with the reason the inventory recorded, carried through as `pin_reason` so
    the judge's unknown names it rather than reading "unpinned" over an input failure.

    A pin whose selection inventory is missing is NOT a pin basis. The items a session received are
    the selection's to say, and reading a pin alone as "selected nothing" would turn an input
    failure into an absence — the difference between `unknown` and `not_delivered` for every unit of
    that session. Measured on the lead's C2 run: 39 sessions with a read pin, none with a selection
    inventory, every one `input_failed`."""
    pin = session_row.get("pin") or {}
    selection = session_row.get("selection") or {}
    shared = shared_of(selection.get("inventory_ref")) if selection.get("inventory_ref") else None
    selected = selected_items(shared, store) if shared else {}
    if pin.get("status") == "read" and selection.get("status") == "read" and selected:
        return "pin", None, selected, {}
    reason = selection.get("reason") or pin.get("reason") or "unpinned"
    if selection.get("inventory_ref") and not selected:
        reason = "selection_inventory_names_no_item"
    elif selection.get("status") == "read" and not selection.get("inventory_ref"):
        reason = "selection_read_without_an_inventory"
    elif selection.get("reason"):
        reason = f"selection_{selection['reason']}"
    return None, reason, selected, {}


def units_by_version(units):
    """`{(carrier_id, version_sha256): [unit_id]}` — what an event's member names, as unit ids.

    A native or injection event records the carrier versions it loaded (`members`), not units; the
    judge asks whether the unit was among them, so the mapping is made here from the inventory's own
    unit records."""
    out = {}
    for unit in units.values():
        key = (unit.get("carrier_id"), unit.get("version_sha256"))
        out.setdefault(key, []).append(unit["unit_id"])
    return out


def native_events_of(session_row, events_by_ref, by_version):
    """The session's native and injection events as the judge takes them: `[{at, unit_ids, kind}]`.

    `at` is the event's RECORD ORDINAL — the inventory's `line` — because that is the scale
    `decision_at` is on; the event's own `at` is an ISO instant and is not comparable with it. An
    event whose line is unknown is dropped from the comparable set and counted, never placed at an
    ordinal nobody recorded."""
    rows, undated = [], 0
    for event in events_by_ref.get(session_row.get("session_ref")) or []:
        line = event.get("line")
        if not isinstance(line, int):
            undated += 1
            continue
        unit_ids = []
        for member in event.get("members") or []:
            unit_ids += by_version.get((member.get("carrier_id"), member.get("version_sha256"))) or []
        rows.append({"at": line, "kind": event.get("kind"), "unit_ids": sorted(set(unit_ids))})
    return sorted(rows, key=lambda row: row["at"]), undated


def release_of(release_doc, session_ref):
    """The reference point `derive.absence` reads for this session: `{complete, layers, items}`.

    The release document states a session's completeness per layer through the reasons it could not
    resolve; a layer it does not name is complete. `items` is what the release holds, and an empty
    one is why `_absence` answers `unknown` rather than `not_delivered` — an absence is only read
    where the release is known to hold the item."""
    for row in release_doc.get("sessions") or []:
        if row.get("session_ref") != session_ref:
            continue
        point = row.get("unsegmented") or {}
        layers = {entry.get("layer"): entry.get("status")
                  for entry in point.get("incomplete_reasons") or []}
        return {"complete": point.get("complete") is True, "layers": layers,
                "items": sorted(point.get("items") or [])}
    return {"complete": False, "layers": {}, "items": [], "absent_from_release_document": True}


def session_evidence(session_row, events_by_ref, by_version, release_doc, shared_of, store,
                     run_dir=None, copies=None, unit_records=()):
    """The judge's `session` input: selection and the snapshot's facts, the events, the release, and
    the bytes the session read back.

    Three sources, each with its own absence rule. The inventory answers selection, events and the
    release. S2 answers what the session was GIVEN — the items with their surfaces and the per-unit
    coverage of the compiled instruction text, as counts, because that text is the owner's and never
    enters a run. The run's immutable copy answers what the session READ. A key one of them cannot
    fill is absent rather than empty, so no reader can mistake "not assembled" for "nothing there"."""
    basis, pin_reason, selected, history = basis_of(session_row, shared_of, store)
    native, undated = native_events_of(session_row, events_by_ref, by_version)
    evidence = {"session_ref": session_row.get("session_ref"), "basis": basis,
                "selected": selected, "history_selected": history,
                "native_events": native,
                "release": release_of(release_doc, session_row.get("session_ref"))}
    # The instant the selected instructions were put in front of the session, on the record-ordinal
    # scale: the FIRST recorded injection, because the ladder asks whether the session had been given
    # the selection before the decision, and the earliest recorded one is the earliest this run can
    # say. Absent when no injection is recorded, which leaves the judge to answer
    # `injection_unrecorded_before_decision` rather than read an unrecorded injection as none. The
    # fixture library is what found this missing: without it every always-surface unit stopped at
    # `selected`, whatever the coverage facts said.
    injections = [row["at"] for row in native if row.get("kind") == "session_injection"]
    if injections:
        evidence["injection_at"] = min(injections)
    if pin_reason:
        evidence["pin_reason"] = pin_reason
    counts = {"native_events": len(native), "events_without_a_line": undated}
    # The snapshot's facts, as S2 published them on this session's selection inventory: the rows a
    # surface could not be routed on, and the per-unit coverage of the compiled instruction text.
    # Looked up here as well as in `basis_of` because the two read the document for different
    # answers, and a basis of None does not mean the facts are absent.
    selection_ref = (session_row.get("selection") or {}).get("inventory_ref")
    shared = shared_of(selection_ref) if selection_ref else None
    if shared is not None:
        facts, unresolved_refs = coverage_facts(shared, unit_records)
        unavailable = [row for row in shared.get("unavailable") or [] if isinstance(row, dict)]
        # Absent rather than empty, by the same rule as `reads`: an empty block is "the text covered
        # nothing", which is a claim, and a missing one is "this run cannot say", which is the truth.
        if facts:
            evidence["instruction_coverage"] = facts
        if unavailable:
            evidence["unavailable"] = unavailable
        # The pointer predicate and the per-unit catalogue surface, both facts S2 publishes because
        # both are read off the compiled text or the owner's baseline. The pointer map goes to the
        # judge as it is; the surfaces are translated per pair, where the unit id is known.
        pointers = pointer_facts(shared)
        if pointers:
            evidence["item_pointer_in_compiled_text"] = pointers
        if shared.get("router_path") is not None:
            evidence["router_path"] = shared["router_path"]
        surfaces = surface_facts(shared)
        counts.update({"coverage_facts": len(facts), "unavailable_rows": len(unavailable),
                       "coverage_refs_unresolved": unresolved_refs,
                       "pointer_facts": len(pointers), "unit_surfaces": len(surfaces),
                       "compiled_text_digest": "present" if shared.get("instruction_text_sha256") else "absent"})
    # The session's own records, from the run's immutable copy. Absent rather than empty when the run
    # holds no copy for this session: an empty `reads` is "it read nothing", which is a claim, and a
    # missing key is "this run cannot say", which is the truth.
    key = session_row.get("session") or session_row.get("session_ref")
    found = (copies or {}).get(key) or (copies or {}).get((session_row.get("transcript") or {}).get("id"))
    if found and run_dir is not None:
        copy, host = found
        reads, unparsed, read_counts = reads_of(pathlib.Path(run_dir) / copy, host)
        evidence["reads"] = reads
        evidence["unparsed"] = [row for row in unparsed if row.get("path")]
        counts.update({"reads": len(reads), "unparsed": len(unparsed),
                       "unparsed_without_a_path": sum(1 for row in unparsed if not row.get("path")),
                       **{f"records_{k}": v for k, v in read_counts.items()}})
    else:
        counts["copy"] = "absent"
    return evidence, counts


def unit_index(current):
    """`{unit_id: the unit in the judge's input shape}`, built from the inventory's own records.

    The operative context is the ONE-STEP set the §6.2 judge packet holds — `edges.direct` plus
    `edges.reached`, which the inventory publishes on every current unit since lane E's export
    (plan WP-11 D1 (a1)) — and never the transitive `operative_context` closure beside it, and never
    a recomputation of mentions here. The export is carried by every unit of a document or by none,
    so a document without it is refused by name rather than read with the closure as a stand-in."""
    units, without = {}, []
    for row in current.get("units") or []:
        edges = row.get("edges")
        if not isinstance(edges, dict):
            without.append(row.get("unit_id"))
            continue
        context = sorted({row["unit_id"], *(edges.get("direct") or []), *(edges.get("reached") or [])})
        units[row["unit_id"]] = {
            "unit_id": row["unit_id"], "path": row.get("path"), "text": row.get("text"),
            "version_sha256": row.get("version_sha256"), "layer": row.get("layer"),
            "item_ref": row.get("item_ref"), "carrier_id": row.get("carrier_id"),
            "n": row.get("n"), "start": (row.get("block") or {}).get("start"),
            "operative_context": context, "context_source": "inventory.edges",
        }
    if without:
        raise Refused(f"DELIVERY_EDGES_ABSENT {len(without)} current unit(s) carry no `edges` "
                      f"(first: {without[:3]}): the one-step context set is the inventory's to "
                      f"publish, and reading the transitive closure instead would answer a "
                      f"different question than the judge's")
    return units


REDACTED = projection.FLOOR.PLACEHOLDER


def document(run_dir, checks, candidates, current, sessions, release_doc, store, shared_of, sources,
             views=None):
    """The stage's document: one row per owed pair, and the summary a reader counts from."""
    units = unit_index(current)
    # The inventory's own `r-` reference per unit id: S2 keys its per-unit facts by it, and the judge
    # asks by unit id.
    refs_by_unit = {row.get("unit_id"): row.get("unit_ref") for row in current.get("units") or []}
    by_name, by_transcript = sessions_index(sessions)
    decisions = decisions_of(run_dir)
    by_version = units_by_version(units)
    events_by_ref = {}
    for event in sessions.get("events") or []:
        events_by_ref.setdefault(event.get("session_ref"), []).append(event)
    rows_by_ref, counts_by_ref = {}, {}
    for row in sessions.get("sessions") or []:
        ref = row.get("session_ref")
        rows_by_ref[ref] = row
    rows = []
    for pair in pairs_of(checks, candidates, decisions, by_name, by_transcript):
        unit = units.get(pair["unit_id"]) if pair["unit_id"] else None
        session_row = rows_by_ref.get(pair["session_ref"])
        evidence, session_counts, session_surfaces = None, {}, {}
        if session_row is not None:
            if pair["session_ref"] not in counts_by_ref:
                built, counts = session_evidence(session_row, events_by_ref, by_version, release_doc,
                                                 shared_of, store, run_dir,
                                                 copies_of(views or {}), current.get("units") or ())
                # The per-unit catalogue surfaces are kept beside the evidence rather than inside it:
                # they are keyed by the inventory's `r-` reference and belong to the pair, where the
                # unit id is known, and the judge's input shape is not widened to carry them.
                selection_ref = (session_row.get("selection") or {}).get("inventory_ref")
                shared = shared_of(selection_ref) if selection_ref else None
                counts_by_ref[pair["session_ref"]] = (built, counts,
                                                      surface_facts(shared) if shared else {})
            evidence, session_counts, session_surfaces = counts_by_ref[pair["session_ref"]]
        # Every reason that holds, in the order a reader would ask them, and never one in place of
        # another: a pair can lack a decision AND name a unit the inventory does not carry, and a
        # row that reported only the last of those would send someone to the wrong artifact.
        reasons = []
        if pair.get("reason"):
            reasons.append(pair["reason"])
        if pair["unit_id"] and unit is None:
            reasons.append("unit_absent_from_inventory")
        elif unit is not None and (unit.get("text") == REDACTED or not unit.get("text")):
            # A unit whose own text this run cannot see cannot be judged on its lines, and handing the
            # judge the redaction placeholder would make every comparison fail — a MISS claimed from
            # evidence nobody read, which is the one thing §6.3 forbids. The pair is answered unknown
            # by name instead. 14,116 of 26,855 current units are redacted on the lead's C2 run.
            reasons.append("unit_text_redacted")
        if evidence is None:
            reasons.append("session_absent_from_inventory")
        elif evidence.get("basis") is None:
            reasons.append(evidence.get("pin_reason") or "unpinned")
        # A coverage row S2 published that resolved to no unit of this run. Named on every pair of
        # that session whose unit the block could not answer for, so a block that lost its rows is
        # visible as a resolution failure rather than as a session nobody published facts for. It
        # never changes the state away from unknown: a fact that failed to resolve is not evidence
        # that the text lacked the unit's lines.
        if (session_counts.get("coverage_refs_unresolved")
                and (evidence or {}).get("instruction_coverage", {}).get(pair["unit_id"]) is None):
            reasons.append(UNRESOLVED)
        # The judge answers the pair when the four things it reads are all there: the unit with its
        # own text, the session's evidence, and the decision's ordinal. Any one missing is a pair
        # this stage can only name, never judge, so the reasons above stand on their own and the
        # state is the unknown they explain. The judge is never handed a stand-in for a missing
        # input — that is how a miss gets claimed from evidence nobody read.
        answer = None
        if not reasons and unit is not None and evidence is not None and pair.get("decision_at") is not None:
            # The ladder §6.3 judges a unit on is the surface the SESSION's snapshot selected its item
            # at, which is a fact about that session and not a property of the unit — two sessions can
            # hold the same unit at different surfaces, and the native layers are judged by their layer
            # with no surface at all. So the surface is attached per pair, from the session's own
            # selection, and a session that states none leaves the judge to answer
            # `surface_unclassified` rather than be handed a guess.
            # The surface the session was given the item at, else the item's CATALOGUE surface as S2
            # published it. The second is what classifies the ladder of a unit the session was not
            # given, which is where §6.3's absence lives: without it the judge answered
            # `surface_unclassified` for every such unit and no absence could ever be found.
            surface = ((evidence.get("selected") or {}).get(unit.get("item_ref"))
                       or (evidence.get("history_selected") or {}).get(unit.get("item_ref"))
                       or session_surfaces.get(refs_by_unit.get(unit["unit_id"])))
            # Only where the judge's own classifier cannot place the unit already: the native layers
            # are matched BY LAYER, and attaching a surface to one of them moved it onto the
            # always-rule ladder, where its recorded-injection absence read as `not_in_release`
            # instead of `not_in_recorded_injection` (found by the frozen native fixture).
            classified = delivery_evidence.surface_row(unit) is not None
            subject = unit if classified or not surface else {**unit, "surface": surface}
            answer = delivery_evidence.delivery(subject, units, evidence, pair["decision_at"])
        else:
            reasons.append(UNJUDGED)
        held = (answer or {}).get("requirements") or []
        rows.append({**{k: v for k, v in pair.items() if k != "reason"},
                     "state": (answer or {}).get("state", "unknown"),
                     "level": (answer or {}).get("level"),
                     "reasons": (answer or {}).get("reasons") or reasons,
                     "surface": (answer or {}).get("surface"),
                     "selection": (answer or {}).get("selection"),
                     "decision_ordinal": "event.at_record" if pair.get("decision_at") is not None else None,
                     "requirements": len(unit["operative_context"]) if unit else None,
                     "native_events": len((evidence or {}).get("native_events") or []),
                     "reads": None if evidence is None or "reads" not in evidence
                              else len(evidence["reads"]),
                     "release_complete": ((evidence or {}).get("release") or {}).get("complete"),
                     # The per-requirement coverage, as counts of what each requirement's own status
                     # was. Never the lines themselves and never the bytes: a count is what a reader
                     # of this file is owed, and the judge's own rows hold the rest.
                     "coverage": None if answer is None else {
                         "requirements": len(held),
                         "met": sum(1 for row in held if row.get("status") == "met"),
                         "unmet": sum(1 for row in held if row.get("status") == "unmet"),
                         "unknown": sum(1 for row in held if row.get("status") == "unknown")},
                     "coverage_refs_unresolved": len(session_counts.get("coverage_refs_unresolved") or ())})
    states = {}
    for row in rows:
        states[row["state"]] = states.get(row["state"], 0) + 1
    # The resolution failures, per session and in total: a count a reader can see, and the refs
    # themselves, which are inventory ids rather than anything a session wrote.
    unresolved_by_session = {ref: counts.get("coverage_refs_unresolved") or []
                             for ref, (_built, counts, _surfaces) in counts_by_ref.items()
                             if counts.get("coverage_refs_unresolved")}
    unjudged = sum(1 for row in rows if UNJUDGED in row["reasons"])
    # The installer surface is not a unit's: §6.3 answers it from the installation binding and its
    # receipt, through `installer_exposure` rather than through a ladder. This run holds neither —
    # the binding is a verdict over the owner's state root and the receipt lives beside it, and S2
    # publishes no part of either today — so the judge is called with the inputs as they are and
    # answers `unknown: unbound`. The inputs are NOT invented here, and the absent producer is named
    # in the document, because an installer row that read `delivered` from nothing would be the one
    # claim §6.3 forbids. Raised with the lead as the same boundary question the compiled text had.
    installer = {**delivery_evidence.installer_exposure(None, None, None),
                 "inputs": {"binding": "no_producer_in_the_run", "receipt": "no_producer_in_the_run",
                            "snapshot_artifacts": "no_producer_in_the_run"},
                 "producer_absent": "the installation binding is a verdict over the owner's state root "
                                    "and S2 publishes no part of it; acquiring it here would move the "
                                    "boundary this package was told to keep at S2"}
    return {"stage": STAGE, "complete": not unjudged,
            # A pair this stage could not hand to the judge is `unknown` with the input it lacked
            # named, and is counted here. It is a state INSIDE a file that exists, never S6's
            # `delivery_assembly_waiting`, which is S6's state when no such file exists at all —
            # the two must stay distinguishable, because one says the evidence was assembled and
            # answered nothing for this pair and the other says nobody assembled any.
            "pending_reason": None if not unjudged else
                              f"{unjudged} of {len(rows)} pairs lack one of the judge's inputs and are "
                              f"`unknown` naming it ({PENDING}); this is the per-pair state inside a file "
                              f"that exists, not S6's `delivery_assembly_waiting`",
            "sources": {"count": len(sources), "dir": SOURCES_DIR},
            "context_source": "inventory.edges",
            "ordinal_source": {"decision": "the first component of an event record's at_record",
                               "events": "the inventory event's line; its `at` is an ISO instant and "
                                         "is not on this scale"},
            "rows": rows,
            "installer": installer,
            "summary": {"pairs": len(rows), "states": states,
                        "sessions": len({row["session_ref"] for row in rows if row["session_ref"]}),
                        "units": len({row["unit_id"] for row in rows if row["unit_id"]}),
                        "decisions": len({row["decision_at"] for row in rows if row["decision_at"] is not None}),
                        "pairs_without_a_decision": sum(1 for row in rows if row["decision_at"] is None),
                        "coverage_refs_unresolved": sum(len(refs) for refs in unresolved_by_session.values()),
                        "sessions_with_an_unresolved_coverage_ref": len(unresolved_by_session),
                        "pairs_named_" + UNRESOLVED: sum(1 for row in rows if UNRESOLVED in row["reasons"]),
                        "pairs_judged": len(rows) - unjudged,
                        "pairs_" + UNJUDGED: unjudged},
            "coverage_refs_unresolved": {ref: refs for ref, refs in sorted(unresolved_by_session.items())}}


def run(run_dir):
    """S5b over S5's checks and S2's inventory. Refuses before any write; writes one document."""
    run_dir = pathlib.Path(run_dir)
    stopped = standing_stop(run_dir)
    if stopped:
        raise Refused(f"DELIVERY_RUN_STOPPED {stopped}: the evidence after a stop is the evidence of a run that did "
                      f"not finish, and this document is read as though it were whole")
    sources = sources_present(run_dir)
    if not sources:
        raise Refused(f"DELIVERY_SOURCES_MISSING {run_dir / SOURCES_DIR}: the bytes a session read back are read from "
                      f"the run's immutable copy, which S2 writes; nothing else is an acquisition this stage may make")
    with records.run_stage(run_dir, STAGE, INPUTS) as stage:
        checks = records.read_json(run_dir / "checks.json")
        candidates = records.read_json(run_dir / "candidates.json")
        current = records.read_json(run_dir / "inventory" / "current.json")
        sessions = records.read_json(run_dir / "inventory" / "sessions.json")
        release_doc = records.read_json(run_dir / "inventory" / "release.json")
        store_path = run_dir / "inventory" / "shared" / "store.json"
        store = records.read_json(store_path) if store_path.is_file() else {}

        def shared_of(inventory_ref):
            """The shared selection inventory a session names, or None when the run does not hold it."""
            path = run_dir / "inventory" / "shared" / f"selection-{inventory_ref}.json"
            return records.read_json(path) if path.is_file() else None

        views = records.read_json(run_dir / VIEWS_FILE)
        doc = document(run_dir, checks, candidates, current, sessions, release_doc, store, shared_of,
                       sources, views)
        records.write_json(run_dir, run_dir / OUTPUT, doc)
        stage.output(OUTPUT)
        declaration_seq = stage.record["declaration_seq"]
    return {**doc["summary"], "complete": doc["complete"], "declaration_seq": declaration_seq}


def report_lines(summary):
    return [f"S5b delivery evidence: {summary['pairs']} pair(s) over {summary['sessions']} session(s) and "
            f"{summary['units']} unit(s); states {summary['states']}",
            f"S5b: complete={summary['complete']} (the evidence readers land in the following commits)"]


# ---- the §6.3 fixture library, at the RECORDS level ---------------------------------------------

FIXTURES_PATH = HERE / "tables" / "stage_delivery_fixtures.json"
# One fixture per state path this stage can write. W2 froze the judge's own fixtures per TABLE ROW
# (`tables/delivery_evidence_fixtures.json`); these are the same states reached the long way, from
# run-shaped artifacts through `document`, which is the only way to tell a judge that answers from a
# producer that assembles the right evidence. The two stage-level paths are this stage's own states,
# not §6.3's, and are named as such.
STATE_PATHS = ("delivered", "exposed_not_read", "not_delivered",
               "not_delivered/selection_lacks_item", "selected_unavailable",
               "unknown/absent_from_compiled_text", f"unknown/{UNRESOLVED}", f"unknown/{UNJUDGED}")


def _records_fixture(path_id):
    """The run-shaped artifacts that drive `document` to one state path, and what it must answer.

    Every fixture is a whole set of artifacts in the spellings their producers write, because that is
    what this stage reads: a fixture written in the judge's input shape would test the judge again
    and say nothing about the assembly. The session, the unit and the decision are the same in all of
    them; what differs is the evidence, which is the point.
    """
    unit = {"unit_id": "u-1", "path": "claude/guides/g.md", "text": "- the rule", "version_sha256": "a" * 64,
            "layer": "catalog", "item_ref": "claude:guides/g", "carrier_id": "c-" + "0" * 24, "n": 1,
            "unit_ref": "r-" + "1" * 24, "block": {"start": 100},
            "operative_context": ["u-1"], "edges": {"direct": ["u-1"], "reached": []}}
    session_ref = "p-" + "1" * 24
    base = {
        "events": [{"event_id": "v-1", "at_record": "500/message/content", "kind": "request"}],
        "checks": {"candidates": [{"candidate_id": "k-1", "named_units_absent": [],
                                   "retrieved_units": [{"unit_id": "u-1", "layer": "catalog", "rank": 1,
                                                        "score": 1.0, "named": True, "copies": 1}]}]},
        "candidates": {"candidates": [{"candidate_id": "k-1", "sessions": ["claude:t-1"],
                                       "event_ids": ["v-1"]}]},
        "current": {"units": [unit]},
        "sessions": {"sessions": [{"session_ref": session_ref, "session": "claude:t-1",
                                   "transcript": {"host": "claude", "id": "t-1", "source": "claude_projects"},
                                   "pin": {"status": "read", "content_ref": "b" * 64, "baseline_ref": None,
                                           "include_global_instructions": True, "reason": None},
                                   "selection": {"status": "read", "reason": None,
                                                 "inventory_ref": "i-" + "a" * 24},
                                   "delivery": {"status": "unknown", "reason": None, "event_refs": []}}],
                     "events": [{"event_id": "e-1", "kind": "session_injection", "session_ref": session_ref,
                                 "line": 10, "at": "2026-09-16T07:44:40+00:00", "members": []}]},
        "release": {"sessions": [{"session_ref": session_ref, "segments": [],
                                  "unsegmented": {"complete": True, "items": ["claude:guides/g"],
                                                  "incomplete_reasons": []}}]},
        "store": {"versions": {"c-" + "0" * 24: {"a" * 64: {"item_ref": "claude:guides/g"}}}, "units": {}},
        "shared": {"carriers": [{"carrier_id": "c-" + "0" * 24, "version_sha256": "a" * 64}],
                   "items": [{"ref": "claude:guides/g", "surface": "always"}],
                   "instruction_text_sha256": "d" * 64,
                   "instruction_coverage": [{"unit_ref": "r-" + "1" * 24, "covered": 1, "total": 1}],
                   "item_pointer_in_compiled_text": [{"ref": "claude:guides/g", "pointer": None,
                                                      "basis": "surface_has_no_pointer"}],
                   "router_path": None,
                   "unit_surfaces": [{"unit_ref": "r-" + "1" * 24, "surface": "always",
                                      "source": "snapshot"}],
                   "unavailable": []},
        "copy": [],
    }
    if path_id == "delivered":
        # The always surface, whose top level is the compiled text holding the unit's lines: the
        # injection is recorded before the decision and the counts say every line was there.
        return base, {"state": "delivered", "level": "exposed"}
    if path_id == "unknown/absent_from_compiled_text":
        return ({**base, "shared": {**base["shared"],
                                    "instruction_coverage": [{"unit_ref": "r-" + "1" * 24, "covered": 0,
                                                              "total": 1}]}},
                {"state": "unknown", "reason": "absent_from_compiled_text"})
    if path_id == "selected_unavailable":
        return ({**base, "shared": {**base["shared"],
                                    "unavailable": [{"ref": "claude:guides/g", "surface": "always",
                                                     "reason": "route_absent"}]}},
                {"state": "selected_unavailable", "level": "selected"})
    if path_id == "not_delivered/selection_lacks_item":
        # The catalogue route, reachable since S2 publishes the catalogue surface of a unit whose
        # item the session was NOT given: the selection was read and holds another item, the release
        # holds this one at a complete reference point, and the ladder is classified from the
        # baseline. Before those facts the judge answered `surface_unclassified` and §6.3's absence
        # could not be found at all.
        return ({**base,
                 "store": {"versions": {"c-" + "0" * 24: {"a" * 64: {"item_ref": "claude:other"}}},
                           "units": {}},
                 "shared": {**base["shared"],
                            "items": [{"ref": "claude:other", "surface": "always"}],
                            "instruction_coverage": [],
                            "item_pointer_in_compiled_text": [{"ref": "claude:other", "pointer": None,
                                                               "basis": "surface_has_no_pointer"}],
                            "unit_surfaces": [{"unit_ref": "r-" + "1" * 24, "surface": "always",
                                               "source": "baseline"}]}},
                {"state": "not_delivered", "reason": "selection_lacks_item"})
    if path_id == "not_delivered":
        # Reached through the NATIVE layer, which is the only place an absence is a finding from what
        # a run holds: a native unit's ladder is classified by its layer and needs no surface, and a
        # recorded injection before the decision that does not carry the unit, over a complete
        # release, is `not_in_recorded_injection`.
        #
        # The catalogue route cannot reach this state from records, and the reason is worth keeping:
        # `_absence` is for an item the selection does not hold, while a unit's SURFACE — the ladder
        # it is judged on — is published only for the items the snapshot DID select. An item the
        # session was not given therefore has no classified ladder here, and the judge answers
        # `surface_unclassified` rather than an absence. Raised with the lead beside the pointer
        # question: S2 publishing each unit's catalogue surface, not only the selected ones, would
        # open it.
        native_unit = {**unit, "layer": "native_global", "path": "CLAUDE.md", "item_ref": "native:global"}
        return ({**base,
                 "current": {"units": [native_unit]},
                 "sessions": {**base["sessions"],
                              "events": [{"event_id": "e-1", "kind": "native", "session_ref": session_ref,
                                          "line": 10, "at": "2026-09-16T07:44:40+00:00",
                                          "members": [{"carrier_id": "c-" + "9" * 24,
                                                       "version_sha256": "f" * 64, "ordinal": 0}]}]},
                 # A native unit's item is not a catalogue item, so no surface is published for it;
                 # the ladder comes from its layer, which is the point of this fixture.
                 "shared": {**base["shared"],
                            "unit_surfaces": [{"unit_ref": "r-" + "1" * 24, "surface": None,
                                               "source": "unpublished"}]}},
                {"state": "not_delivered", "reason": "not_in_recorded_injection"})
    if path_id == f"unknown/{UNRESOLVED}":
        return ({**base, "shared": {**base["shared"],
                                    "instruction_coverage": [{"unit_ref": "r-" + "9" * 24, "covered": 1,
                                                              "total": 1}]}},
                {"state": "unknown", "reason": UNRESOLVED})
    if path_id == f"unknown/{UNJUDGED}":
        # No decision event at all: one of the judge's four inputs is missing, so this stage answers
        # and says that it did.
        return ({**base, "candidates": {"candidates": [{"candidate_id": "k-1", "sessions": ["claude:t-1"],
                                                        "event_ids": []}]}},
                {"state": "unknown", "reason": UNJUDGED})
    if path_id == "exposed_not_read":
        # A requested guide: its ladder delivers only at a read of the unit's own bytes, and S2's
        # pointer fact says the compiled text held its emitted path. Nothing read the file, so the
        # unit is exposed and not delivered. Reachable since S2 publishes the pointer predicate;
        # before that the state could not be produced from records at all, and the fixture said so.
        return ({**base,
                 "shared": {**base["shared"],
                            "items": [{"ref": "claude:guides/g", "surface": "requested"}],
                            "item_pointer_in_compiled_text": [{"ref": "claude:guides/g", "pointer": True,
                                                               "basis": "emitted_path"}],
                            "unit_surfaces": [{"unit_ref": "r-" + "1" * 24, "surface": "requested",
                                               "source": "snapshot"}]}},
                {"state": "exposed_not_read", "level": "pointer exposed"})
    raise Refused(f"FIXTURE_UNKNOWN {path_id}: no records fixture is written for this state path")


def generate_fixtures(path=FIXTURES_PATH):
    """Write the records fixtures once; a second call refuses, as W2's generator does."""
    path = pathlib.Path(path)
    if path.exists():
        raise Refused(f"FIXTURES_FROZEN {path}: generated once and committed; delete it by hand to regenerate")
    fixtures = []
    for path_id in STATE_PATHS:
        artifacts, expected = _records_fixture(path_id)
        fixtures.append({"id": path_id, "artifacts": artifacts, "expected": expected})
    doc = {"$comment": "design §6.3 at the records level: one frozen fixture per state path "
                       "`runlib/stage_delivery.py` can write, each a whole set of run-shaped artifacts "
                       "driven through `document`. Written once by `stage_delivery.py "
                       "--generate-fixtures`; the self-test never regenerates them.",
           "fixtures": fixtures}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(fixtures)


def run_fixture(root, fixture):
    """`document` over one frozen fixture's artifacts, against what it must answer.

    A fixture declared unreachable carries its reason and no artifacts; it is executed as that
    declaration, so the library still accounts for every state path and the reason is in the file
    rather than in somebody's memory."""
    if fixture.get("artifacts") is None:
        why = (fixture.get("expected") or {}).get("unreachable")
        return [] if why else [f"FIXTURE_UNREACHABLE_UNEXPLAINED {fixture['id']}: a state path with no "
                               f"artifacts and no reason"]
    artifacts = fixture["artifacts"]
    run_dir = pathlib.Path(root) / f"fx-{fixture['id'].replace('/', '-')}"
    (run_dir / EVENTS_DIR).mkdir(parents=True)
    (run_dir / EVENTS_DIR / "claude_t-1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in artifacts["events"]), encoding="utf-8")
    session = dict(artifacts["sessions"])
    doc = document(run_dir, artifacts["checks"], artifacts["candidates"], artifacts["current"], session,
                   artifacts["release"], artifacts["store"], lambda ref: artifacts["shared"],
                   artifacts["copy"] or ["aa.jsonl"])
    rows = [row for row in doc["rows"] if row["unit_id"] == "u-1"]
    if not rows:
        return [f"FIXTURE_NO_ROW {fixture['id']}: the artifacts owe no pair for the unit"]
    row = rows[0]
    got = {"state": row["state"]}
    want = dict(fixture["expected"])
    if "level" in want:
        got["level"] = row["level"]
    if "reason" in want:
        got["reason"] = want["reason"] if want["reason"] in (row["reasons"] or []) else (row["reasons"] or [None])[0]
    return [] if got == want else [f"FIXTURE_FAILED {fixture['id']}: expected {want}, got {got} "
                                   f"(reasons {row['reasons']})"]


# ---- self-test ----------------------------------------------------------------------------------

def self_test():
    """Positive control first, then one planted violation per rule, each refused BY NAME."""
    failures, ran = [], []

    def control(label, got, want):
        ran.append(label)
        if want not in got:
            failures.append(f"{label}: expected {want!r} in {got!r}")

    def clean(label, got):
        """An absence asserted as an absence: `want=""` cannot fail, since every string holds it."""
        ran.append(label)
        if got:
            failures.append(f"{label}: expected nothing, got {got!r}")

    def refusal(call):
        try:
            call()
        except Refused as exc:
            return str(exc)
        except Exception as exc:  # a non-refusal comes back to its control instead of ending the suite
            return f"{type(exc).__name__}: {exc}"
        return ""

    if STAGE not in records.STAGES:
        failures.append(f"{STAGE} is not in records.STAGES, so run_stage would refuse it as unknown")
    else:
        order = list(records.STAGES)
        if not order.index("S5") < order.index(STAGE) < order.index("S6"):
            failures.append(f"records.STAGES orders {STAGE} outside (S5, S6): {order}; declare.py derives an "
                            f"amendment's invalidation range and its ordering from this index")
    ran.append("the stage is registered between S5 and S6")

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        # The document's shape over the artifacts' OWN spellings, taken from `checks.schema.json`, S4's
        # `candidates.json` and an event record's `at_record`, as a real run writes them (measured on the
        # lead's C2 run, 2026-11-11). The first commit of this package read fields no producer writes —
        # `session_ref`, `unit_ids`, `decision_at` on a check row — and its controls passed because they
        # judged that invented shape and no real file.
        fixture = root / "fx"
        (fixture / EVENTS_DIR).mkdir(parents=True)
        (fixture / EVENTS_DIR / "claude_t-1.jsonl").write_text(
            json.dumps({"event_id": "v-1", "at_record": "76837/message/content", "kind": "request"}) + "\n"
            + json.dumps({"event_id": "v-2", "at_record": "9/message/content/0", "kind": "request"}) + "\n",
            encoding="utf-8")
        checks = {"candidates": [
            {"candidate_id": "k-1",
             "retrieved_units": [{"unit_id": "u-1", "layer": "catalog", "rank": 1, "score": 1.0,
                                  "named": True, "copies": 1}],
             "named_units_absent": ["u-gone"]},
            {"candidate_id": "k-2", "retrieved_units": [], "named_units_absent": []}]}
        candidates = {"candidates": [
            {"candidate_id": "k-1", "sessions": ["claude:t-1"], "event_ids": ["v-1", "v-2"]},
            {"candidate_id": "k-2", "sessions": ["claude:t-1"], "event_ids": []}]}
        current = {"units": [
            {"unit_id": "u-1", "path": "claude/guides/g.md", "text": "- x", "version_sha256": "a" * 64,
             "layer": "catalog", "item_ref": "claude:guides/g", "carrier_id": "c-" + "0" * 24, "n": 1,
             "block": {"start": 100}, "operative_context": ["u-1", "u-2", "u-3"],
             "edges": {"direct": ["u-1", "u-2"], "reached": []}},
            {"unit_id": "u-2", "path": "claude/guides/g.md", "text": "- y", "version_sha256": "a" * 64,
             "layer": "catalog", "item_ref": "claude:guides/g", "carrier_id": "c-" + "0" * 24, "n": 2,
             "block": {"start": 200}, "operative_context": ["u-2"],
             "edges": {"direct": ["u-2"], "reached": []}}]}
        sessions = {"sessions": [{"session_ref": "p-" + "1" * 24, "session": "claude:t-1",
                                  "transcript": {"host": "claude", "id": "t-1", "source": "claude_projects"},
                                  "pin": {"status": "read", "content_ref": "b" * 64, "baseline_ref": None,
                                          "include_global_instructions": True, "reason": None},
                                  "selection": {"status": "unknown", "reason": "input_failed",
                                                "inventory_ref": None},
                                  "delivery": {"status": "unknown", "reason": "input_failed", "event_refs": []}}]}
        release_doc = {"sessions": [{"session_ref": "p-" + "1" * 24, "segments": [],
                                     "unsegmented": {"complete": False, "items": [],
                                                     "incomplete_reasons": [
                                                         {"layer": "catalog", "status": "unknown",
                                                          "reasons": ["release_history_deferred"],
                                                          "inventory_ref": None}]}}]}
        store = {"versions": {}, "units": {}}
        doc = document(fixture, checks, candidates, current, sessions, release_doc, store,
                       lambda ref: None, ["aa.jsonl"])
        # k-1: two events x two units (one retrieved, one named-absent) = 4; k-2: one session, no event, no unit = 1.
        control("a pair is owed per decision event and unit", str(doc["summary"]["pairs"]), "5")
        control("an event's ordinal is read from its at_record", json.dumps((doc.get("rows") or [{}])[0]),
                '"decision_at": 76837')
        control("and the session comes from the transcript the event record belongs to",
                json.dumps((doc.get("rows") or [{}])[0]), '"session_ref": "p-111111111111111111111111"')
        control("a candidate with no decision event keeps its pair and says why",
                json.dumps((doc.get("rows") or [{}])[-1]), "no_decision_event")
        control("and a candidate naming no unit keeps it too", json.dumps((doc.get("rows") or [{}])[-1]),
                '"unit_id": null')
        control("a unit the inventory does not carry is named, not dropped",
                json.dumps([r for r in doc["rows"] if r["unit_id"] == "u-gone"]), "unit_absent_from_inventory")
        control("a pair one of the judge's inputs is missing for is an unknown naming that input",
                json.dumps((doc.get("rows") or [{}])[0]), "selection_input_failed")
        control("and saying the state beside it is this stage's, not the judge's",
                json.dumps((doc.get("rows") or [{}])[0]), UNJUDGED)
        clean("such a pair carries no judge fields it never got",
              [key for key in ("surface", "selection", "coverage")
               if ((doc.get("rows") or [{}])[0] or {}).get(key) is not None])
        control("and the document says so of itself", json.dumps({"complete": doc["complete"]}), '"complete": false')
        control("the pending state is not S6's waiting state", str(doc["pending_reason"]),
                "not S6's `delivery_assembly_waiting`")
        control("and it counts the pairs it could not hand over", json.dumps(doc["summary"]),
                '"pairs_delivery_unjudged": 5')
        clean("no row carries bytes or session text",
              [key for row in doc["rows"] for key in row if key in ("returned", "text", "bytes")])

        # The context set is the judge's one-step set, and the closure beside it is never read.
        units = unit_index(current)
        control("the operative context is direct plus one-step reached",
                json.dumps(units["u-1"]["operative_context"]), '["u-1", "u-2"]')
        clean("and the transitive closure is not what was read",
              [u for u in units.values() if "u-3" in u["operative_context"]])
        control("the source of that set is named in the row", units["u-1"]["context_source"], "inventory.edges")
        no_edges = {"units": [{**current["units"][0], "edges": None}]}
        control("an inventory that publishes no edges is refused by name",
                refusal(lambda: unit_index(no_edges)), "DELIVERY_EDGES_ABSENT")

        # ---- the inventory's half of the session evidence (commit 3) ----
        session_row = sessions["sessions"][0]
        events_by_ref = {"p-" + "1" * 24: [
            {"event_id": "e-1", "kind": "native", "session_ref": "p-" + "1" * 24, "line": 12,
             "at": "2026-09-16T07:44:40.323000+00:00",
             "members": [{"carrier_id": "c-" + "0" * 24, "version_sha256": "a" * 64, "ordinal": 0}]},
            {"event_id": "e-2", "kind": "native", "session_ref": "p-" + "1" * 24, "line": None,
             "at": "2026-09-16T07:45:00.000000+00:00", "members": []}]}
        evidence, counts = session_evidence(session_row, events_by_ref,
                                            units_by_version(unit_index(current)), release_doc,
                                            lambda ref: None, store)
        control("a native event is placed at its record line, not its instant",
                json.dumps((evidence.get("native_events") or [{}])[0]), '"at": 12')
        control("and its carrier version is resolved to the units it loaded",
                json.dumps((evidence.get("native_events") or [{}])[0]), '"unit_ids": ["u-1", "u-2"]')
        control("an event with no line is counted, not placed at an ordinal nobody recorded",
                str(counts.get("events_without_a_line", "no such count")), "1")
        clean("and it is not in the comparable set",
              [row for row in evidence.get("native_events") or [] if row.get("at") is None])
        control("a read pin with no selection inventory is not a pin basis",
                json.dumps({"basis": evidence.get("basis")}), '"basis": null')
        # `.get` with an absence VALUE, not `[...]`: a revert that makes this a pin basis removes the
        # key, and indexing it ended the run with a KeyError before either control could speak —
        # the same shape as the unguarded `[0]` this repo fixed in the ledger migrator's suite.
        control("and the reason the inventory recorded is what the unknown will name",
                evidence.get("pin_reason") or "no pin_reason was recorded", "selection_input_failed")
        # ---- the snapshot's facts, as S2 publishes them (commit 5b, the lead's fact-only decision).
        # A selection inventory with items, surfaces and per-unit coverage counts: the compiled text is
        # never in the run, so these counts are the only thing that can answer whether the session was
        # given a unit's lines. Keyed by the inventory's `r-` reference, translated here to the unit ids
        # the judge asks about.
        facts_shared = {
            "carriers": [{"carrier_id": "c-" + "0" * 24, "version_sha256": "a" * 64}],
            "items": [{"ref": "claude:guides/g", "surface": "always"}],
            "instruction_text_sha256": "d" * 64,
            "instruction_coverage": [{"unit_ref": "r-" + "1" * 24, "covered": 1, "total": 2},
                                     {"unit_ref": "r-" + "9" * 24, "covered": 5, "total": 5}],
            "unavailable": [{"ref": "claude:guides/g", "surface": "always", "reason": "route_absent"}]}
        facts_units = [{**current["units"][0], "unit_ref": "r-" + "1" * 24},
                       {**current["units"][1], "unit_ref": "r-" + "2" * 24}]
        facts_store = {"versions": {"c-" + "0" * 24: {"a" * 64: {"item_ref": "claude:guides/g"}}}, "units": {}}
        facts_row = {**session_row, "selection": {"status": "read", "reason": None,
                                                  "inventory_ref": "i-" + "a" * 24}}
        facts_evidence, facts_counts = session_evidence(
            facts_row, events_by_ref, units_by_version(unit_index(current)), release_doc,
            lambda ref: facts_shared, facts_store, None, None, facts_units)
        control("the per-unit coverage counts reach the judge under the unit ids it asks about",
                json.dumps(facts_evidence.get("instruction_coverage")), '"u-1": {"covered": 1, "total": 2}')
        # A published row whose reference resolves to no unit here: named and counted, never dropped.
        # The lead's correction (2026-11-11): a drop is a resolution failure, and a block that lost
        # every row to one would read like a session nobody published facts for.
        control("a coverage row naming a unit this run does not carry is named, not dropped",
                json.dumps(facts_counts.get("coverage_refs_unresolved")), "r-" + "9" * 24)
        clean("and no unit id is invented for it",
              [ref for ref in facts_evidence.get("instruction_coverage") or () if ref not in ("u-1", "u-2")])
        facts_sessions = {"sessions": [{**facts_row}]}
        facts_current = {"units": [{**row, "unit_ref": ref} for row, ref in
                                   zip(current["units"], ("r-" + "1" * 24, "r-" + "2" * 24))]}

        def facts_document(shared, current=None):
            """The rows and summary this stage writes when the session's inventory publishes `shared`."""
            doc_f = document(fixture, checks, candidates, current or facts_current, facts_sessions,
                             release_doc, facts_store, lambda ref: shared, ["aa.jsonl"])
            return {row["unit_id"]: row for row in doc_f["rows"]}, doc_f

        # The pair this fixture owes is u-1's, so the block that cannot answer for it is the one
        # naming another unit's reference.
        missed = {**facts_shared, "instruction_coverage": [{"unit_ref": "r-" + "9" * 24, "covered": 1, "total": 1}]}
        missed_rows, missed_doc = facts_document(missed)
        control("the pair whose coverage the block could not answer for names the failure",
                json.dumps(missed_rows.get("u-1") or {}), UNRESOLVED)
        # Both kinds of row at once, which is what makes the next assertion about the PAIR rather
        # than about the session: the block answers for u-1 and also carries a reference nothing here
        # resolves, so only the per-pair clause can keep the failure off u-1's row.
        answered = {**facts_shared,
                    "instruction_coverage": [{"unit_ref": "r-" + "1" * 24, "covered": 1, "total": 2},
                                             {"unit_ref": "r-" + "9" * 24, "covered": 1, "total": 1}]}
        answered_rows, answered_doc = facts_document(answered)
        clean("and the pair the block did answer for does not, though its session has an unresolved one",
              ([UNRESOLVED] if UNRESOLVED in ((answered_rows.get("u-1") or {}).get("reasons") or []) else [])
              + ([] if answered_doc["summary"]["coverage_refs_unresolved"] == 1
                 else ["the fixture's session has no unresolved reference, so the clause is untested"]))

        # ---- the judge's own answer (commit 7). The session here has a read pin, a selection
        # inventory and the facts, so every input §6.3 reads is present and the row is ITS answer
        # rather than this stage's unknown.
        judged_row = answered_rows.get("u-1") or {}
        clean("a pair with every input present is handed to the judge",
              [UNJUDGED] if UNJUDGED in (judged_row.get("reasons") or []) else [])
        control("and the row carries the surface the judge answered on", json.dumps(judged_row),
                '"surface": "always_rule"')
        control("with the selection basis it read", json.dumps(judged_row), '"selection": "pin"')
        control("and the per-requirement coverage as counts", json.dumps(judged_row.get("coverage")),
                '"requirements"')
        clean("the judged row carries no line of any unit and no byte any session read",
              [key for key in judged_row if key in ("text", "returned", "bytes", "instruction_text")])
        # The installer surface, which no ladder answers.
        # ---- the §6.3 fixture library at the records level (done-when 1). The ids are the state
        # paths, the frozen file is the authority, and the three sets must be one bijection:
        # a path with no fixture, a fixture for no path, and a fixture the run never executed are
        # each named by `derive.coverage_problems`, so the library cannot drift from the code.
        frozen = records.read_json(FIXTURES_PATH)
        # `frozen_case`, not `fixture`: this suite's `fixture` is its run directory, and a loop
        # variable of that name rebinds it for every line after this block (the shadowing trap this
        # file's suite has paid for once already).
        frozen_ids = [case["id"] for case in frozen.get("fixtures") or []]
        executed, fixture_problems = [], []
        for frozen_case in frozen.get("fixtures") or []:
            fixture_problems += run_fixture(root, frozen_case)
            executed.append(frozen_case["id"])
        clean("every frozen §6.3 fixture answers from the records what it was frozen with",
              fixture_problems)
        clean("and the state paths, the frozen fixtures and the executed cases are one set",
              derive.coverage_problems(STATE_PATHS, frozen_ids, executed))
        control("a state path with no frozen fixture is named",
                "; ".join(derive.coverage_problems(
                    tuple(STATE_PATHS) + ("delivered/by_another_route",), frozen_ids, executed)),
                "ROW_UNFIXTURED")
        control("and the generator refuses to overwrite the frozen file",
                refusal(lambda: generate_fixtures(FIXTURES_PATH)), "FIXTURES_FROZEN")
        control("a fixture declared unreachable with no reason is named",
                "; ".join(run_fixture(root, {"id": "x", "artifacts": None, "expected": {}})),
                "FIXTURE_UNREACHABLE_UNEXPLAINED")
        control("and a fixture whose artifacts owe no pair for its unit is named",
                "; ".join(run_fixture(root, {"id": "y", "artifacts": {
                    **(frozen["fixtures"][0]["artifacts"]),
                    "candidates": {"candidates": [{"candidate_id": "k-1", "sessions": ["claude:t-1"],
                                                   "event_ids": ["v-1"]}]},
                    "checks": {"candidates": [{"candidate_id": "k-1", "retrieved_units": [],
                                               "named_units_absent": []}]}},
                    "expected": {"state": "delivered"}})),
                "FIXTURE_NO_ROW")
        control("the installer surface is answered by the judge's own reader, not by a ladder",
                json.dumps(doc["installer"]), "receipt_live_waiting_wp15")
        control("and it is unknown by name while the run holds no binding",
                json.dumps(doc["installer"]), '"reasons": ["unbound"]')
        control("with the absent producer named rather than an input invented for it",
                json.dumps(doc["installer"]), "no_producer_in_the_run")
        clean("no installer answer claims a delivery from inputs this run does not hold",
              [doc["installer"]["state"]] if doc["installer"]["state"] != "unknown" else [])
        control("the summary says how many pairs the judge answered", json.dumps(answered_doc["summary"]),
                '"pairs_judged": 2')
        # End to end: the unroutable row S2 published is why this pair's state is what it is, which no
        # part of this stage decides on its own.
        control("and the unroutable row S2 published is what the state rests on", json.dumps(judged_row),
                '"state": "selected_unavailable"')
        control("with the reason the judge gives for it", json.dumps(judged_row), "route_unavailable")
        control("the document counts the unresolved references for a reader to see",
                json.dumps(missed_doc["summary"]), '"coverage_refs_unresolved": 1')
        control("and says which session they belong to", json.dumps(missed_doc["coverage_refs_unresolved"]),
                facts_row["session_ref"])
        # All of them unresolved: every unit of that session is unknown by name, and NOT ONE is
        # not_delivered — the state a block read as empty would have produced for all of them.
        gone_shared = {**facts_shared, "unavailable": [],
                       "instruction_coverage": [{"unit_ref": "r-" + "8" * 24, "covered": 1, "total": 1},
                                                {"unit_ref": "r-" + "9" * 24, "covered": 1, "total": 1}]}
        gone_evidence, gone_counts = session_evidence(
            facts_row, events_by_ref, units_by_version(unit_index(current)), release_doc,
            lambda ref: gone_shared, facts_store, None, None, facts_units)
        # The always surface, whose top level is the compiled text holding the unit's lines: the one
        # the coverage facts answer. Defined here because this block runs before the §6.3 pair below.
        gone_unit = {"unit_id": "u-1", "path": "claude/guides/g.md", "text": "- x", "surface": "always",
                     "version_sha256": "a" * 64, "layer": "catalog", "item_ref": "claude:guides/g",
                     "carrier_id": "c-" + "0" * 24, "n": 1, "start": 1, "operative_context": ["u-1"]}
        gone_session = {**gone_evidence, "basis": "pin", "selected": {"claude:guides/g": "always"},
                        "injection_at": 1, "release": {"complete": True, "layers": {}, "items": []}}
        gone_states = [delivery_evidence.delivery(
            {**gone_unit, "unit_id": unit_id}, {unit_id: {**gone_unit, "unit_id": unit_id}},
            gone_session, 10) for unit_id in ("u-1", "u-2")]
        control("a block whose every row failed to resolve is counted in full",
                str(len(gone_counts.get("coverage_refs_unresolved") or ())), "2")
        clean("and not one unit of that session reads not_delivered because of it",
              [answer for answer in gone_states if answer["state"] == "not_delivered"])
        clean("while every one of them is unknown with a reason",
              [answer for answer in gone_states if answer["state"] != "unknown" or not answer["reasons"]])
        # The one case that IS not_delivered, so the row above is not simply the absence of that
        # state: a readable snapshot that selected the item's carrier for nothing.
        empty_answer = delivery_evidence.delivery(
            gone_unit, {"u-1": gone_unit},
            {**gone_session, "selected": {}, "instruction_coverage": {},
             "release": {"complete": True, "layers": {}, "items": ["claude:guides/g"]}}, 10)
        control("a readable snapshot that selected no unit is not_delivered, not unknown",
                json.dumps(empty_answer), '"state": "not_delivered"')
        control("the surface the snapshot selected an item at is published, so the judge need not guess one",
                json.dumps(facts_evidence.get("selected")), '"claude:guides/g": "always"')
        control("the rows the selection could not route are carried as the judge reads them",
                json.dumps(facts_evidence.get("unavailable")), "route_absent")
        control("and the counts say the digest was published", json.dumps(facts_counts), '"compiled_text_digest": "present"')
        # The two facts the ladders needed, carried to the judge as facts rather than as text.
        pointer_shared = {**facts_shared, "unavailable": [],
                          "items": [{"ref": "claude:guides/g", "surface": "requested"}],
                          "item_pointer_in_compiled_text": [{"ref": "claude:guides/g", "pointer": True,
                                                             "basis": "emitted_path"}],
                          "router_path": "/x/router/relevant.md",
                          "unit_surfaces": [{"unit_ref": "r-" + "1" * 24, "surface": "requested",
                                             "source": "snapshot"}]}
        pointer_evidence, pointer_counts = session_evidence(
            facts_row, events_by_ref, units_by_version(unit_index(current)), release_doc,
            lambda ref: pointer_shared, facts_store, None, None, facts_units)
        control("the pointer predicate reaches the judge as a fact about the item",
                json.dumps(pointer_evidence.get("item_pointer_in_compiled_text")), '"claude:guides/g": true')
        control("and the router the compiled text named comes with it",
                json.dumps(pointer_evidence.get("router_path")), "router/relevant.md")
        clean("no part of the compiled text reaches the judge with them",
              [key for key in pointer_evidence if key == "instruction_text"])
        control("the counts say how many pointer facts and unit surfaces were published",
                json.dumps(pointer_counts), '"pointer_facts": 1')
        control("and how many surfaces", json.dumps(pointer_counts), '"unit_surfaces": 1')
        surface_rows, _surface_doc = facts_document(pointer_shared)
        control("a unit the session was not given is judged on the catalogue surface S2 published",
                json.dumps((surface_rows.get("u-1") or {}).get("surface")), "guide")
        # A native unit is matched by its LAYER, and attaching a published surface to one moved it
        # onto another ladder entirely; the classifier is asked first, and this row is why.
        native_rows, _native_doc = facts_document(
            {**pointer_shared,
             "unit_surfaces": [{"unit_ref": "r-" + "1" * 24, "surface": "requested", "source": "snapshot"}]},
            current={"units": [{**current["units"][0], "unit_ref": "r-" + "1" * 24,
                                "layer": "native_global", "item_ref": "native:global"}]})
        control("a native unit keeps its layer's ladder, whatever surface is published for it",
                json.dumps((native_rows.get("u-1") or {}).get("surface")), "native_layer")
        # Absence rather than emptiness: a session whose inventory publishes no facts carries NO
        # coverage key, and `delivery_evidence` then answers unknown by name. An empty block would be
        # the claim that the text covered nothing, which is `not_delivered` for every unit of it.
        bare_evidence, _bare_counts = session_evidence(
            facts_row, events_by_ref, units_by_version(unit_index(current)), release_doc,
            lambda ref: {"carriers": facts_shared["carriers"]}, facts_store, None, None, facts_units)
        clean("a selection inventory that publishes no facts leaves the evidence with no coverage key",
              [key for key in bare_evidence if key in ("instruction_coverage", "unavailable")])
        # The equivalence the lead named: the same k-of-n snapshot answers the same through the facts
        # path as through the text path. Judged by calling the judge itself, because "the same state"
        # is its answer and not this stage's.
        # The always surface, whose ladder ends at `exposed`: its top level is the compiled text
        # holding the unit's lines, which is exactly what the two paths answer differently.
        eq_unit = {"unit_id": "u-1", "path": "claude/guides/g.md", "text": "- x\n- y",
                   "version_sha256": "a" * 64, "layer": "catalog", "surface": "always",
                   "item_ref": "claude:guides/g", "carrier_id": "c-" + "0" * 24, "n": 1, "start": 1,
                   "operative_context": ["u-1"]}
        eq_session = {"session_ref": "claude:s", "basis": "pin", "selected": {"claude:guides/g": "always"},
                      "native_events": [], "injection_at": 1,
                      "release": {"complete": True, "layers": {}, "items": []}}

        def eq_state(text=None, facts=None):
            """The judge's state for this unit under one of the two paths."""
            answer = delivery_evidence.delivery(
                eq_unit, {"u-1": eq_unit},
                {**eq_session, **({"instruction_text": text} if text is not None else {})},
                10, instruction_coverage=facts)
            return answer.get("state"), tuple(answer.get("reasons") or ())

        eq_whole = (eq_state(text="- x\n- y"), eq_state(facts={"u-1": {"covered": 2, "total": 2}}))
        eq_partial = (eq_state(text="- x"), eq_state(facts={"u-1": {"covered": 1, "total": 2}}))
        clean("a snapshot covering all of a unit's lines answers the same through the facts path as "
              "through the text path",
              [f"text={eq_whole[0]} facts={eq_whole[1]}"] if eq_whole[0] != eq_whole[1] else [])
        clean("and a snapshot covering k of n answers the same through both, with the same reason",
              [f"text={eq_partial[0]} facts={eq_partial[1]}"] if eq_partial[0] != eq_partial[1] else [])
        clean("and the two paths are not the same answer for every input, so the comparison can fail",
              [] if eq_whole[0] != eq_partial[0] else [f"both paths answered {eq_whole[0]} for k of n and n of n"])
        control("a session with neither the text nor the facts is unknown by name, never a miss",
                json.dumps(delivery_evidence.delivery(eq_unit, {"u-1": eq_unit}, eq_session, 10)),
                "compiled_text_unavailable")
        clean("and that answer is not not_delivered",
              [delivery_evidence.delivery(eq_unit, {"u-1": eq_unit}, eq_session, 10).get("state")]
              if delivery_evidence.delivery(eq_unit, {"u-1": eq_unit}, eq_session,
                                            10).get("state") == "not_delivered" else [])

        control("the release is read as the point derive.absence judges",
                json.dumps(evidence.get("release") or {}), '"complete": false')
        control("a layer the release leaves unresolved is carried with its status",
                json.dumps((evidence.get("release") or {}).get("layers")), '"catalog": "unknown"')
        incomplete = derive.absence(evidence.get("release") or {})
        clean("and the absence policy reads it as incomplete", [] if not incomplete[0] else ["complete"])
        absent = release_of({"sessions": []}, "p-nobody")
        control("a session the release document does not carry is named, not read as complete",
                json.dumps(absent), "absent_from_release_document")

        # A unit whose text this run cannot see is answered unknown by name rather than judged on a
        # placeholder: the comparison would fail for every line and claim a miss from nothing read.
        redacted = {"units": [{**current["units"][0], "text": REDACTED},
                              current["units"][1]]}
        doc_red = document(fixture, checks, candidates, redacted, sessions, release_doc, store,
                           lambda ref: None, ["aa.jsonl"])
        control("a redacted unit is not judged on its placeholder",
                json.dumps([r["reasons"] for r in doc_red["rows"] if r["unit_id"] == "u-1"][0]),
                "unit_text_redacted")
        control("each row names the ordinal it used", json.dumps((doc.get("rows") or [{}])[0]),
                '"decision_ordinal": "event.at_record"')

        # ---- the bytes a session read back, from the run's immutable copy (commit 4) ----
        # Records in both hosts' own shapes. The returned text of a read is what covers a
        # requirement, so a result that cannot be read back as text is `unparsed`, never a miss.
        claude_copy = fixture / SOURCES_DIR / "cc.jsonl"
        claude_copy.parent.mkdir(parents=True, exist_ok=True)
        claude_copy.write_text("\n".join(json.dumps(row) for row in [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Read",
                 "input": {"file_path": "/x/guides/g.md"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1",
                 "content": [{"type": "text", "text": "     1\t- Read the log before you retry."}]}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t2", "name": "Bash",
                 "input": {"command": "sed -n '1,40p' /x/guides/h.md"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t2", "content": "- h"}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t3", "name": "Read", "input": {"file_path": "/x/guides/i.md"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t3", "is_error": True, "content": "No such file"}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t4", "name": "Read", "input": {"file_path": "/x/guides/j.md"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t4",
                 "content": [{"type": "image", "source": {}}]}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t5", "name": "Bash", "input": {"command": "cat $KNOWN_FILE"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t5", "content": "- opaque"}]}},
        ]) + "\n", encoding="utf-8")
        reads, unparsed, counts = reads_of(claude_copy, "claude")
        control("a named reader's path is its own argument", json.dumps((reads or [{}])[0]),
                '"path": "/x/guides/g.md"')
        control("and the read is attributed to the line its RESULT arrived on",
                json.dumps((reads or [{}])[0]), '"at": 2')
        control("the returned text is kept as returned, prefixes and all",
                json.dumps((reads or [{}])[0].get("returned")), "1\\t- Read the log")
        control("a reading command's path is read out of the command",
                json.dumps(reads[1:2]), '"path": "/x/guides/h.md"')
        clean("a failed call is not a read",
              [r for r in reads if (r.get("path") or "").endswith("i.md")])
        control("a result that is not text is unparsed, not a miss",
                json.dumps([r for r in unparsed if r["path"] and r["path"].endswith("j.md")]),
                "result_not_text")
        control("and a reading command naming no path is unparsed too",
                json.dumps(unparsed), "command_names_no_path")
        control("the counts say how many results were seen",
                str((counts or {}).get("results", "no such count")), "5")

        codex_copy = fixture / SOURCES_DIR / "cx.jsonl"
        codex_copy.write_text("\n".join(json.dumps(row) for row in [
            {"type": "response_item", "payload": {"type": "function_call", "call_id": "c1", "name": "shell",
                                                  "arguments": json.dumps({"command": ["cat", "/x/guides/g.md"]})}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1",
                                                  "output": "- Read the log before you retry."}},
        ]) + "\n", encoding="utf-8")
        codex_reads, _codex_unparsed, _codex_counts = reads_of(codex_copy, "codex")
        # Dumped whole rather than indexed: a revert that returns no read would end the suite with an
        # IndexError here and print nothing, which is the control-that-cannot-speak shape this branch
        # has now paid for twice (the ledger migrator's `[0]`, and `evidence["pin_reason"]`).
        control("a Codex shell call is read the same way", json.dumps(codex_reads),
                '"path": "/x/guides/g.md"')
        control("and at the line of its output", json.dumps((codex_reads or [{}])[0]), '"at": 2')

        missing = reads_of(fixture / SOURCES_DIR / "nope.jsonl", "claude")
        control("a copy the run does not hold is named, not read as an empty session",
                json.dumps(missing[2]), "copy_missing")

        # The manifest is what says which copy belongs to which session.
        # The manifest row's SESSION is what the session row names; its transcript string is deliberately
        # a different value here, so a lookup that only ever reads the transcript key fails this control
        # instead of passing on a fixture where the two happen to be equal.
        views = {"transcripts": [{"session": "claude:t-1", "transcript": "claude:other-1",
                                 "name": "claude_other-1", "host": "claude",
                                 "source_copy": f"{SOURCES_DIR}/cc.jsonl", "version_sha": "c" * 64}]}
        with_reads, read_counts = session_evidence(session_row, events_by_ref,
                                                   units_by_version(unit_index(current)), release_doc,
                                                   lambda ref: None, store, fixture, copies_of(views))
        control("the session's reads come from the copy its manifest row names",
                str(len(with_reads.get("reads") or [])), "2")
        control("and an unparsed call with no path is counted rather than dropped",
                str(read_counts.get("unparsed_without_a_path", "no such count")), "1")
        clean("no unparsed row without a path reaches the judge",
              [row for row in with_reads.get("unparsed") or [] if not row.get("path")])
        without, no_copy = session_evidence(session_row, events_by_ref,
                                            units_by_version(unit_index(current)), release_doc,
                                            lambda ref: None, store, fixture, {})
        clean("a session with no copy carries no `reads` key at all", [k for k in without if k == "reads"])
        control("and the counts say the copy is absent", json.dumps(no_copy), '"copy": "absent"')

        # The two refusals, each before any write.
        empty = root / "r-empty"
        (empty / SOURCES_DIR).mkdir(parents=True)
        control("a run whose immutable copy holds nothing is refused by name",
                refusal(lambda: run(empty)), "DELIVERY_SOURCES_MISSING")
        clean("and nothing is written for it", sorted(p.name for p in empty.iterdir() if p.is_file()))
        gone = root / "r-nosources"
        gone.mkdir()
        control("so is a run with no copy at all", refusal(lambda: run(gone)), "DELIVERY_SOURCES_MISSING")

        stopped = root / "r-stopped"
        (stopped / SOURCES_DIR).mkdir(parents=True)
        (stopped / SOURCES_DIR / "aa.jsonl").write_text("{}\n", encoding="utf-8")
        (stopped / "supervisor").mkdir()
        records.write_json(stopped, dispatch.run_ledger_path(stopped),
                           {"stages": {}, "stops": {"INPUT_BOUND_EXCEEDED": {
                               "code": "INPUT_BOUND_EXCEEDED", "call_id": "r1/S3/read/a0", "observed": 1,
                               "declaration_seq": 0}}})
        said = refusal(lambda: run(stopped))
        control("a run with a standing stop is refused by name", said, "DELIVERY_RUN_STOPPED")
        control("and the refusal carries the stop's own code", said, "INPUT_BOUND_EXCEEDED")
        clean("and nothing is written for it either",
              sorted(p.name for p in stopped.iterdir() if p.is_file()))
        # A declaration this stage cannot read holds the stop standing, rather than reading the run open: the
        # fixture above has no run.json at all, and the stop was still named. Asserted here as its own control,
        # because the direction is the whole point — the other reading would let an unreadable run.json turn a
        # stopped run into a complete-looking document.
        control("an unreadable declaration holds a recorded stop standing",
                standing_stop(stopped) or "", "INPUT_BOUND_EXCEEDED")

        # The stop reading is the dispatcher's, not a second one: an empty ledger is not a stop.
        open_run = root / "r-open"
        (open_run / SOURCES_DIR).mkdir(parents=True)
        (open_run / "supervisor").mkdir()
        records.write_json(open_run, dispatch.run_ledger_path(open_run), {"stages": {}, "stops": {}})
        clean("a ledger with no stop is not read as stopped", standing_stop(open_run))

    for failure in failures:
        print(f"stage_delivery --self-test [FAIL] {failure}", file=sys.stderr)
    if failures:
        return 1
    print(f"stage_delivery --self-test: OK ({len(ran)} controls: the stage's place in STAGES, the pairs owed over "
          f"the artifacts' own shapes with every pending one answered by name, the judge's one-step context set "
          f"and the refusal when the inventory publishes none, the inventory's half of the session "
          f"evidence — native events at their record line, the release as the absence policy reads it, a read "
          f"pin with no selection inventory kept out of the pin basis, and a redacted unit not judged on its "
          f"placeholder, the bytes a session read back from the run's immutable copy on both hosts "
          f"with a failed call no read, a non-text result unparsed and a missing copy named, and the two run "
          f"refusals with nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv[1:] else
             print("usage: stage_delivery.py --self-test (the stage runs as `distill.py deliver`)") or 2)
