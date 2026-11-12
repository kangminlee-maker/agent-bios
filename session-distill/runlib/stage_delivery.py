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
import inspect
import collections
import json
import pathlib
import re
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import bound, delivery_evidence, derive, dispatch, projection, records  # noqa: E402
from runlib import stagelock  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
STAGE = "S5b"
OUTPUT = "delivery-evidence.json"
SOURCES_DIR = "sources"
EVENTS_DIR = "events"
VIEWS_FILE = "views.json"
# Admitted against every producer whose records this stage reads, so the shared staleness judgement applies: a
# `checks.json` or an inventory written again after this stage ran makes the next reader refuse rather than trust it.
# Every artifact this stage READS, with the stage that produced it. `checked-candidates.json` is
# S5's own population — S4's candidates plus the planted controls of design §6.5, which is what S6
# judges — and it was not declared or read, so a planted control and its retrieved units were
# excluded from the pairs this stage owes an answer for, silently (the WP-11b review).
INPUTS = ({"artifact": "checks.json", "producer_stage": "S5"},
          {"artifact": "checked-candidates.json", "producer_stage": "S5"},
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


def view_index(views):
    """`{event-file stem: the views transcript row}` — the EXPLICIT mapping S2 published.

    The join used to be string surgery on the file stem: `stem.split("_", 1)[-1]`. S2 names a
    transcript's files with `views.safe_name(coverage_key)`, and a Codex coverage key is
    `codex:<id>@<segment>`, which becomes `codex_<id>_<segment>` — so removing the first underscore
    prefix leaves `<id>_<segment>`, which is no transcript id at all and matched nothing. Every
    Codex event therefore joined to no session and was reported `session_unmatched` (the WP-11b
    review). The row carries `name`, `transcript` and `session` itself; this reads them.

    Keyed on `name` AND on `segment`, because the event files S3 writes are per segment: a
    transcript split across several rollout files has one row per segment, and keying on the
    transcript alone would make the last one win.
    """
    held = {}
    for row in (views or {}).get("transcripts") or []:
        for key in (row.get("name"), row.get("segment")):
            if key:
                held.setdefault(str(key), row)
    return held


def pairs_of(checks, candidates, decisions, by_name, by_transcript, by_view=None,
             population=None):
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
            # The views row S2 published for that file, then the session it names. No string
            # surgery: a Codex stem carries the segment as well as the id, and splitting it left
            # neither (the WP-11b review).
            view = (by_view or {}).get(str(stem)) if stem else None
            transcript = view.get("transcript") if view else None
            session = by_transcript.get(transcript) or (
                by_name.get(view.get("session")) if view and view.get("session") else None)
            events.append({"event_id": event_id, "decision_at": ordinal,
                           "session_ref": (session or {}).get("session_ref"),
                           "session": (session or {}).get("session"),
                           # Which half of the join failed, so an unmatched pair says what to fix.
                           "reason": None if ordinal is not None and session else
                                     ("event_record_absent" if ordinal is None else
                                      "view_unmatched" if view is None else "session_unmatched")})
        if not events:
            # The candidate's own sessions, so the pair still names where it would be judged.
            for name in row.get("sessions") or [None]:
                session = by_name.get(name) if name else None
                events.append({"event_id": None, "decision_at": None,
                               "session_ref": (session or {}).get("session_ref"), "session": name,
                               "reason": "no_decision_event"})
        for event in events:
            for unit in units:
                owed.append({"candidate_id": cid, "unit_id": unit, "producer": "S4", **event})
    # S5's own population: S4's candidates PLUS the planted controls of design §6.5, which is the
    # population S6 judges. Enumerating only S4's excluded every planted control and its retrieved
    # units from the pairs this stage owes — silently, so the denominator shrank with no row saying
    # so (the WP-11b review). A planted control carries a fabricated session id, so its pair is
    # answered with a reason; that is the point, and it is not the same as not being asked.
    seen = {row.get("candidate_id") for row in candidates.get("candidates") or []}
    for row in (population or {}).get("candidates") or []:
        cid = row.get("candidate_id")
        if cid in seen or not cid:
            continue
        units = units_by_candidate.get(cid) or [None]
        for name in row.get("sessions") or [None]:
            session = by_name.get(name) if name else None
            for unit in units:
                owed.append({"candidate_id": cid, "unit_id": unit, "producer": "S5",
                             "event_id": None, "decision_at": None,
                             "session_ref": (session or {}).get("session_ref"),
                             "session": name,
                             "reason": "no_decision_event" if session
                                       else "session_absent_from_inventory"})
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


def version_universe(current, store):
    """`{path: {version_sha256: [lines]}}` over every carrier version THIS RUN names.

    `delivery_evidence.delivery` defaults its `versions` to the CURRENT units alone, and this stage
    passed none — so the shared store's historical versions were invisible to the byte binding, and
    a fragment shared by two versions could not be told apart (the WP-11b review). The run does hold
    them: `shared/store.json` keys every carrier version it names, each version lists its
    `unit_refs` in order, and each store unit carries its own projected `text`. The universe is
    assembled from those records, unioned with the current document's units, so a read of an older
    version is matched against the version it actually belongs to instead of against the current one.

    The lines of one version are its units' lines in the version's own order, which is the same rule
    `delivery_evidence.versions_of` uses for the current document — reached rather than restated
    where the shape allows it.
    """
    held = delivery_evidence.versions_of((current or {}).get("units") or [])
    units = (store or {}).get("units") or {}
    for carrier_id, by_version in ((store or {}).get("versions") or {}).items():
        for version_sha, version in (by_version or {}).items():
            path = (version or {}).get("path")
            if not path:
                continue
            lines = []
            for ref in (version or {}).get("unit_refs") or []:
                unit = units.get(ref) or {}
                if unit.get("text"):
                    lines += delivery_evidence.text_lines(unit["text"])
            if not lines:
                continue
            # The current document wins where both hold the same (path, version): it is the same
            # bytes, and its units are the ones the judge's requirements are keyed to.
            held.setdefault(path, {}).setdefault(version_sha, lines)
    return held


def released_items(shared, store):
    """The item refs ONE shared inventory holds, for the release's reference point.

    Not `selected_items`, which answers a different question: that one is what a SESSION received,
    so it walks the carriers the snapshot gave that session and resolves each through the store —
    an inventory naming no carrier yields nothing there, correctly. The release asks what the
    owner's library HELD at the reference point, which is the inventory's stated items as well as
    whatever its carriers resolve to. Reading the session question's answer for the release question
    is what made `items` empty for every session.
    """
    held = {item.get("ref") for item in shared.get("items") or []
            if isinstance(item, dict) and item.get("ref")}
    held |= set(selected_items(shared, store))
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
SHELL_READERS = {"Bash", "shell", "local_shell", "container.exec", "exec_command"}
# The argument names a shell tool carries its command under. `exec_command` uses `cmd`, and reading
# only `command` discarded every one of its calls as non-reading — silently, since a call with no
# command simply fell through (the WP-11b review). Named as data so a new shape is one entry.
COMMAND_ARGUMENTS = ("command", "cmd", "commands")
# What a host writes into a result when the call FAILED or when it elided the bytes. Either way the
# returned text is not what the file holds, so it is uncertainty rather than a read: a result saying
# "Process exited with code 1" was being counted as delivered bytes, and a truncation warning as
# the whole file (the WP-11b review).
EXIT_MARKER = re.compile(r"Process exited with code (\d+)")
ELISION_MARKERS = ("Warning: truncated", "[truncated]", "<response clipped>",
                   "… +", "... +", "[output elided]", "(output truncated)")


def result_defect(returned):
    """`("result_failed", detail)` / `("result_elided", detail)` / None for one returned text.

    Read before any read is admitted from it, in both adapters: the bytes a failed or elided result
    carries are not the file's, and admitting them makes a delivery claim out of an error message.
    """
    if not isinstance(returned, str):
        return None
    held = EXIT_MARKER.search(returned)
    if held and held.group(1) != "0":
        return "result_failed", f"exit code {held.group(1)}"
    for marker in ELISION_MARKERS:
        if marker in returned:
            return "result_elided", marker
    return None
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
            # The same judgment as the Codex adapter's: a result whose text says the call failed or
            # that the host elided the bytes is uncertainty, not a read. `is_error` above catches
            # the structured case; a host that writes the failure into the TEXT does not set it.
            defect = result_defect(returned)
            if name in NAMED_READERS:
                path = arguments.get("file_path") or arguments.get("path") or arguments.get("notebook_path")
                if not path:
                    continue
                if returned is None:
                    counts["no_text"] += 1
                    unparsed.append({"at": at, "path": path, "reason": "result_not_text"})
                elif defect:
                    counts[defect[0]] = counts.get(defect[0], 0) + 1
                    unparsed.append({"at": at, "path": path, "reason": defect[0],
                                     "detail": defect[1]})
                else:
                    reads.append({"at": at, "path": path, "returned": returned})
            elif name in SHELL_READERS:
                command = next((arguments.get(key) for key in COMMAND_ARGUMENTS
                                if arguments.get(key) is not None), None) \
                    or arguments.get("script") or ""
                if isinstance(command, list):
                    command = " ".join(str(part) for part in command)
                if not any(verb in command for verb in READING_VERBS):
                    continue
                named = _paths_in(command)
                if not named:
                    counts["unnamed_command"] += 1
                    unparsed.append({"at": at, "path": None, "reason": "command_names_no_path"})
                elif returned is None:
                    counts["no_text"] += 1
                    unparsed += [{"at": at, "path": path, "reason": "result_not_text"} for path in named]
                elif defect:
                    counts[defect[0]] = counts.get(defect[0], 0) + 1
                    unparsed += [{"at": at, "path": path, "reason": defect[0], "detail": defect[1]}
                                 for path in named]
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
        command = next((arguments.get(key) for key in COMMAND_ARGUMENTS
                        if arguments.get(key) is not None), None)
        if isinstance(command, list):
            command = " ".join(str(part) for part in command)
        elif command is not None and not isinstance(command, str):
            command = str(command)
        defect = result_defect(returned)
        if name in NAMED_READERS:
            path = arguments.get("path") or arguments.get("file_path")
            if not path:
                continue
            if returned is None:
                counts["no_text"] += 1
                unparsed.append({"at": at, "path": path, "reason": "result_not_text"})
            elif defect:
                counts[defect[0]] = counts.get(defect[0], 0) + 1
                unparsed.append({"at": at, "path": path, "reason": defect[0],
                                 "detail": defect[1]})
            else:
                reads.append({"at": at, "path": path, "returned": returned})
        elif name in SHELL_READERS or command:
            if not any(verb in (command or "") for verb in READING_VERBS):
                if command is None:
                    # A shell tool whose argument shape this adapter does not know. Kept as named
                    # uncertainty rather than dropped: a discarded call is indistinguishable from a
                    # call nobody made, which is how `exec_command` disappeared.
                    counts["call_shape_unsupported"] = counts.get("call_shape_unsupported", 0) + 1
                    unparsed.append({"at": at, "path": None, "reason": "call_shape_unsupported",
                                     "detail": f"{name}: {sorted(arguments)}"})
                continue
            named = _paths_in(command)
            if not named:
                counts["unnamed_command"] += 1
                unparsed.append({"at": at, "path": None, "reason": "command_names_no_path"})
            elif returned is None:
                counts["no_text"] += 1
                unparsed += [{"at": at, "path": path, "reason": "result_not_text"} for path in named]
            elif defect:
                counts[defect[0]] = counts.get(defect[0], 0) + 1
                unparsed += [{"at": at, "path": path, "reason": defect[0], "detail": defect[1]}
                             for path in named]
            else:
                reads += [{"at": at, "path": path, "returned": returned} for path in named]
    return reads, unparsed, counts


def reads_of(run_dir, copy, host):
    """(reads, unparsed, counts) read from ONE immutable copy of a transcript version.

    The copy S2 wrote is the only place these bytes are read from: the views are clipped, so they
    cannot carry what a result returned, and the owner's own files are not this stage's to open. The
    bytes stay in this process — the document carries counts, paths and states, never text.

    `copy` is a LABEL from S2's manifest and is confined before the filesystem is touched. It used
    to be joined with `/`, which discards `run_dir` entirely for an absolute label, follows `..`,
    and follows a symlink out — so a manifest row could point this stage at any file the owner can
    read, and `reads_of` would open it (the WP-11b review). A run artifact is data, and containment
    cannot rest on its producer being honest. The confinement lives HERE rather than at the call
    site because a caller can forget it; `run_dir` is therefore a parameter, not a convenience.
    """
    try:
        path = stagelock.confine(run_dir, pathlib.Path(run_dir) / str(copy))
    except stagelock.Escaped as exc:
        raise Refused(f"EVIDENCE_OUTSIDE_RUN {copy!r}: {exc}. S2's manifest names a copy beneath "
                      f"the run; a label that leaves it is refused rather than read") from exc
    if not path.is_file():
        return [], [], {"copy_missing": True}
    # The repository's JSONL splitter, not `str.splitlines()`. `splitlines()` also splits U+2028,
    # U+2029 and U+0085, so one JSONL record carrying a separator inside a JSON string became two
    # lines: the record ordinals this stage reports were on a different scale from S2's, and a
    # record could be discarded as unparsable (the WP-11b review, the same defect as the journal's).
    # `errors="replace"` was the old behaviour and is kept: a transcript byte this stage cannot
    # decode is not a reason to refuse an entire session's evidence.
    lines = records.jsonl_read(path, errors="replace")
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


def release_of(release_doc, session_ref, segment_ref=None, shared_of=None, store=None):
    """The reference point `derive.absence` reads for this session: `{complete, layers, items}`.

    Three things were wrong here, and together they made the catalogue absence unreachable (the
    WP-11b review):

    * `items` was read from `unsegmented.items`, and `release_rows` HAS NO SUCH FIELD — its members
      are `inventory_refs`, `layers`, `complete` and `incomplete_reasons`. So `items` was always
      empty, `_absence` always answered `unknown` rather than `not_delivered`, and no catalogue
      absence could ever be found. Item membership belongs to the shared inventories the row set
      REFERENCES, which is where it is read from now.
    * `segments` was ignored. A session a segment covers has `unsegmented: null`, so the row set
      came out `{}` and every such session was reported incomplete. The applicable row set is the
      segment the decision belongs to — the transcript file the event record was read from, which
      the views row names — and `unsegmented` only for a session no segment covers.
    * `layers` was derived from `incomplete_reasons`, which names only the layers that are NOT
      complete. The per-layer status lives in `layers` (one `release_row` each); a complete layer
      had no entry at all, so a reader could not tell "complete" from "not mentioned".

    `shared_of` and `store` are how item membership is resolved; without them the items are reported
    as unresolved rather than as empty, because an empty set is the claim that made this reachable.
    """
    held = next((row for row in release_doc.get("sessions") or []
                 if row.get("session_ref") == session_ref), None)
    if held is None:
        return {"complete": False, "layers": {}, "items": [],
                "absent_from_release_document": True}
    segments = [row for row in held.get("segments") or [] if isinstance(row, dict)]
    point = None
    if segment_ref is not None:
        point = next((row for row in segments if row.get("segment_ref") == segment_ref), None)
    if point is None and not segments:
        point = held.get("unsegmented")
    if point is None:
        # Segments exist and none of them is the one this decision belongs to. Not an absence and
        # not a completeness: the reference point for this decision was not resolved.
        return {"complete": False, "layers": {}, "items": [],
                "segment_unresolved": segment_ref, "segments": len(segments)}
    layers = {row.get("layer"): row.get("status") for row in point.get("layers") or []
              if isinstance(row, dict) and row.get("layer")}
    refs = [ref for ref in point.get("inventory_refs") or [] if ref]
    for row in point.get("layers") or []:
        source = (row or {}).get("source") or {}
        if source.get("inventory_ref"):
            refs.append(source["inventory_ref"])
    items, unresolved = set(), []
    for ref in sorted(set(refs)):
        shared = shared_of(ref) if shared_of else None
        if shared is None:
            unresolved.append(ref)
            continue
        items.update(released_items(shared, store or {}))
    return {"complete": point.get("complete") is True, "layers": layers,
            "items": sorted(items),
            # The references this run could not open. Reported rather than folded into an empty
            # `items`: an empty set says the release holds nothing, which is an absence claim.
            "items_unresolved": unresolved,
            "items_from": sorted(set(refs)),
            "point": "segment" if point is not held.get("unsegmented") else "unsegmented"}


def session_evidence(session_row, events_by_ref, by_version, release_doc, shared_of, store,
                     run_dir=None, copies=None, unit_records=(), segment_ref=None):
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
                # The reference point for THIS session's segment, with the items resolved through
                # the inventories the row set references.
                "release": release_of(release_doc, session_row.get("session_ref"),
                                      segment_ref, shared_of, store)}
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
        # WHY a pointer could not be established, which S2 now publishes
        # (`compiled_text_absent` | `catalog_rule_unread`) instead of leaving the list absent. An
        # absent list and an established absence read the same to the judge, and the judge then
        # asserted "no pointer" from an input nobody had read; with the reason it answers
        # `pointer_unavailable:<reason>` instead.
        if shared.get("item_pointer_unavailable"):
            evidence["item_pointer_unavailable"] = shared["item_pointer_unavailable"]
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
        reads, unparsed, read_counts = reads_of(run_dir, copy, host)
        if read_counts.get("copy_missing"):
            # The manifest NAMES a copy and the file is not there. Installing `reads = []` here made
            # that "the session read nothing", which is a claim — and the judge then reported an
            # exposed guide as not read, from evidence nobody acquired (the WP-11b review). The
            # acquisition state is carried instead, and the pair is answered unknown by name.
            counts["copy"] = "missing"
            evidence["read_evidence"] = {"status": "unavailable", "reason": "copy_missing",
                                         "copy": str(copy)}
        else:
            evidence["reads"] = reads
            evidence["unparsed"] = [row for row in unparsed if row.get("path")]
            evidence["read_evidence"] = {"status": "available", "reason": None,
                                        "copy": str(copy)}
            counts.update({"reads": len(reads), "unparsed": len(unparsed),
                           "unparsed_without_a_path": sum(1 for row in unparsed
                                                          if not row.get("path")),
                           **{f"records_{k}": v for k, v in read_counts.items()}})
    else:
        # No manifest entry at all: this run holds no copy for the session, which is a different
        # thing from a copy it holds and cannot open. Both are unknown, and the reason says which.
        # No manifest entry at all: `reads` stays ABSENT, which the judge already reads as "this
        # run cannot say" — that half was right. Only a copy the manifest NAMES and this run cannot
        # open was installing an empty `reads` as a claim, so only that half gains a reason.
        counts["copy"] = "absent"
        evidence["read_evidence"] = {"status": "absent", "reason": "copy_absent", "copy": None}
    return evidence, counts


def unit_index(current):
    """`{unit_id: the unit in the judge's input shape}`, built from the inventory's own records.

    The operative context is the ONE-STEP set the §6.2 judge packet holds — `edges.direct` plus
    `edges.reached`, which the inventory publishes on every current unit since lane E's export
    (plan WP-11 D1 (a1)) — and never the transitive `operative_context` closure beside it, and never
    a recomputation of mentions here. The export is carried by every unit of a document or by none,
    so a document without it is refused by name rather than read with the closure as a stand-in."""
    units, without, misshapen = {}, [], []
    for row in current.get("units") or []:
        edges = row.get("edges")
        if not isinstance(edges, dict):
            without.append(row.get("unit_id"))
            continue
        # `block` is the KIND of block the unit is, a string from the inventory's own enum
        # (`inventory.BLOCK_KINDS`), and `start` is not published in the emitted document at all.
        # This index read `block` as an object and took `start` out of it, so every real S2 unit
        # raised AttributeError here while the frozen fixtures — which carried `block: {"start": …}`,
        # a shape no producer writes — passed. Refusing by name is what makes the next shape change
        # a message instead of a traceback.
        if row.get("block") is not None and not isinstance(row["block"], str):
            misshapen.append(f"{row.get('unit_id')}: block is {type(row['block']).__name__}, not the "
                             f"string kind the inventory publishes")
            continue
        context = sorted({row["unit_id"], *(edges.get("direct") or []), *(edges.get("reached") or [])})
        units[row["unit_id"]] = {
            "unit_id": row["unit_id"], "path": row.get("path"), "text": row.get("text"),
            "version_sha256": row.get("version_sha256"), "layer": row.get("layer"),
            "item_ref": row.get("item_ref"), "carrier_id": row.get("carrier_id"),
            "n": row.get("n"),
            # Published if the inventory ever publishes it; today it does not, and the ordering in
            # `delivery_evidence.units_of` falls back to `n`, the occurrence number, which it does
            # publish. Carried as None rather than dropped so a reader can tell "not published"
            # from "zero".
            "start": row.get("start"), "block": row.get("block"),
            "operative_context": context, "context_source": "inventory.edges",
        }
    if misshapen:
        raise Refused(f"DELIVERY_UNIT_SHAPE {len(misshapen)} current unit(s) are not in the shape "
                      f"`inventory.emitted_document` writes (first: {misshapen[:2]})")
    if without:
        raise Refused(f"DELIVERY_EDGES_ABSENT {len(without)} current unit(s) carry no `edges` "
                      f"(first: {without[:3]}): the one-step context set is the inventory's to "
                      f"publish, and reading the transitive closure instead would answer a "
                      f"different question than the judge's")
    return units


REDACTED = projection.FLOOR.PLACEHOLDER


def consumed_binding(run_dir, paths):
    """`[{path, sha256}]` for every file this stage READ that its declaration cannot pin.

    `records.run_stage` pins each DECLARED input against its producer's recorded output digest.
    Three kinds of file this stage reads are not declarable that way: the event records under
    `events/`, `inventory/shared/store.json`, and the per-session
    `inventory/shared/selection-<ref>.json` — the last two because which ones exist depends on the
    run, and a static declaration of a file a run does not hold would refuse the run
    (`INPUT_INVALID`). They determine the verdict all the same, so their bytes are published HERE,
    with the document that rests on them: a reader can then tell whether the evidence moved under a
    later stage, which was not knowable at all before (the WP-11b review).

    This is a BINDING, not a check. Nothing in this run holds an earlier digest to compare it with,
    and saying so is the honest half; `records.provenance_problems` is what compares, and it can
    only compare what a producer recorded.
    """
    root = pathlib.Path(run_dir)
    held = []
    for path in sorted(set(str(one) for one in paths)):
        path = pathlib.Path(path)
        if not path.is_file():
            continue
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            relative = str(path)
        held.append({"path": relative, "sha256": records.sha256_file(path)})
    return held


def document(run_dir, checks, candidates, current, sessions, release_doc, store, shared_of, sources,
             views=None, population=None):
    """The stage's document: one row per owed pair, and the summary a reader counts from."""
    # Every file read below whose bytes the declaration cannot pin, collected as they are opened.
    consumed = sorted((pathlib.Path(run_dir) / EVENTS_DIR).glob("*.jsonl")) \
        if (pathlib.Path(run_dir) / EVENTS_DIR).is_dir() else []
    consumed.append(pathlib.Path(run_dir) / "inventory" / "shared" / "store.json")
    for held_row in (sessions or {}).get("sessions") or []:
        held_ref = (held_row.get("selection") or {}).get("inventory_ref")
        if held_ref:
            consumed.append(pathlib.Path(run_dir) / "inventory" / "shared"
                            / f"selection-{held_ref}.json")
    units = unit_index(current)
    # Every carrier version this run names, with its lines: the binding a read's bytes are matched
    # against. One assembly per document, because it is the same for every pair.
    universe = version_universe(current, store)
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
    for pair in pairs_of(checks, candidates, decisions, by_name, by_transcript,
                         view_index(views), population):
        unit = units.get(pair["unit_id"]) if pair["unit_id"] else None
        session_row = rows_by_ref.get(pair["session_ref"])
        evidence, session_counts, session_surfaces = None, {}, {}
        if session_row is not None:
            if pair["session_ref"] not in counts_by_ref:
                # The SEGMENT this session's records were read from, as S2's views row names it:
                # the reference point for a decision belongs to the segment the record is in, and a
                # session several rollout files cover has one row set per segment.
                held_view = next((row for row in (views or {}).get("transcripts") or []
                                  if row.get("session") == session_row.get("session")
                                  or row.get("transcript")
                                  == (session_row.get("transcript") or {}).get("id")), None)
                built, counts = session_evidence(session_row, events_by_ref, by_version, release_doc,
                                                 shared_of, store, run_dir,
                                                 copies_of(views or {}), current.get("units") or (),
                                                 (held_view or {}).get("segment"))
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
        # Reasons that are RECORDED but do not stop the judge: an input the ladder this pair is
        # judged on does not need. They reach the row like any other reason, so nothing is hidden;
        # what they do not do is turn a judgeable pair into an unknown (the WP-11b review).
        carried = []
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
            # The missing pin is RECORDED either way, because a reader counts it. Whether it also
            # stops the judge depends on the LADDER: §6.3's native rung is answered by the session's
            # own events — an event that loaded this unit's carrier version is evidence of delivery
            # on its own, and the selection pin says nothing about it. Treating every absent basis
            # as a missing input made an unpinned session with a native event answer
            # `unknown: unpinned`, over evidence that was already sufficient (the WP-11b review).
            held_native = [row for row in evidence.get("native_events") or []
                           if pair["unit_id"] and pair["unit_id"] in (row.get("unit_ids") or ())]
            if held_native:
                carried.append(evidence.get("pin_reason") or "unpinned")
            else:
                reasons.append(evidence.get("pin_reason") or "unpinned")
        # Whether the session's RECORDS could be read at all. An empty `reads` from a copy this run
        # cannot open is not "it read nothing": the pair is named unknown with the acquisition's own
        # reason, so a missing copy cannot become a claim that an exposed guide went unread.
        if evidence is not None:
            held_acquisition = evidence.get("read_evidence") or {}
            if held_acquisition.get("status") == "unavailable":
                reasons.append(held_acquisition.get("reason") or "read_evidence_unavailable")
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
            # ONE owner for that rule: `delivery_evidence.attach_surface`. This stage carried its
            # own copy — the snapshot's selection, then the selection history, then S2's published
            # catalogue surface, and only where the judge's own classifier cannot place the unit
            # already — and a rule in two places is what this review keeps finding. The copy is
            # gone; the stage translates the unit id to its item ref, which is the one thing only
            # the stage knows, and the rule itself answers.
            subject = delivery_evidence.attach_surface(
                unit, evidence, session_surfaces.get(refs_by_unit.get(unit["unit_id"])))
            # The version universe this run names, not the current units alone: see
            # `version_universe`. Computed once per document, above the pair loop.
            answer = delivery_evidence.delivery(subject, units, evidence, pair["decision_at"],
                                                versions=universe)
        else:
            reasons.append(UNJUDGED)
        held = (answer or {}).get("requirements") or []
        rows.append({**{k: v for k, v in pair.items() if k != "reason"},
                     "state": (answer or {}).get("state", "unknown"),
                     "level": (answer or {}).get("level"),
                     # The judge's own reasons, then the pair's, then the ones carried past the
                     # judge: a reader sees the missing pin even when it did not block the answer.
                     "reasons": list(dict.fromkeys(
                         ((answer or {}).get("reasons") or reasons) + carried)),
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
            # The bytes this stage read that its declaration cannot pin. See `consumed_binding`:
            # published rather than checked, because nothing here holds an earlier digest.
            "consumed": consumed_binding(run_dir, consumed),
            "consumed_unpinnable": ("the event records, the shared store and the per-session "
                                    "selection inventories are read by this stage and are not "
                                    "declarable inputs; their digests are published here so a "
                                    "later reader can tell whether they moved"),
            "context_source": "inventory.edges",
            "ordinal_source": {"decision": "the first component of an event record's at_record",
                               "events": "the inventory event's line; its `at` is an ISO instant and "
                                         "is not on this scale"},
            "rows": rows,
            "installer": installer,
            "summary": {"pairs": len(rows), "states": states,
                        # Which producer's population each pair came from, so a reader can see the
                        # planted controls were asked about rather than left out of the denominator.
                        "pairs_by_producer": dict(sorted(collections.Counter(
                            row.get("producer") or "unknown" for row in rows).items())),
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
    # BEFORE the stage record is published. `run_stage` writes `status: running` on entry and
    # `status: failed` on the way out of a refusal, so a prerequisite checked inside it leaves a
    # failed attempt behind for a condition that was knowable first — and a stage record that says
    # an attempt failed is read as an attempt (the WP-11b review). The edges export is S2's, so
    # whether it is there is decidable from S2's own document with nothing of this stage's written.
    held_current = records.read_json(run_dir / "inventory" / "current.json")
    unit_index(held_current)
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


def _producer_current(text="# Guide\n\n- the rule\n", path="claude/guides/g.md",
                      layer="catalog", item_ref="claude:guides/g"):
    """A real `current` document, from S2's own producer over a carrier written here.

    The fixtures used to carry a hand-written unit whose `block` was an object with a `start` in it.
    No producer writes that: `block` is a string kind and `start` is not published at all, so
    `unit_index` worked on every fixture and raised AttributeError on every real document. The shape
    must come from the producer, and it does not need the owner's data to do so — a carrier built
    from this text, under a fixture home, goes through `inventory.emitted_document`, which is THE
    production path (`reference_of` calls the same function).
    """
    from runlib import inventory

    # Removed before returning: the umbrella fails a leg that leaves an entry in TMPDIR, and it is
    # right to — a suite that litters cannot tell its own leftovers from a run's.
    with tempfile.TemporaryDirectory(prefix="s5b-fx-home-") as home:
        ctx = {"home": home, "state_root": None, "notes": {}, "commit": None,
               "release_ref": None, "snapshot": {}, "events": []}
        held = inventory.carrier(layer, path, text, item_ref=item_ref)
        document, _units = inventory.emitted_document(
            "current", [{"layer": layer, "producer": "the S5b fixture producer",
                         "status": "complete", "reasons": [], "carriers": [held]}], ctx)
    operative = [unit for unit in document["units"] if unit.get("class") == "operative"]
    if not operative:
        raise Refused("FIXTURE_PRODUCER_EMPTY: the producer published no operative unit, so a "
                      "fixture built from it would assert nothing")
    return document, operative[0]


def _records_fixture(path_id):
    """The run-shaped artifacts that drive `document` to one state path, and what it must answer.

    Every fixture is a whole set of artifacts in the spellings their producers write, because that is
    what this stage reads: a fixture written in the judge's input shape would test the judge again
    and say nothing about the assembly. The session, the unit and the decision are the same in all of
    them; what differs is the evidence, which is the point.
    """
    # The unit and the document around it come from S2's producer, not from this file. Every id the
    # other artifacts have to agree with is then read OFF the produced unit, because a fixture whose
    # carrier id is a row of zeros agrees only with itself.
    current_doc, unit = _producer_current()
    carrier_id = unit["carrier_id"]
    version = unit["version_sha256"]
    item_ref = unit["item_ref"]
    unit_ref = unit["unit_ref"]
    unit_id = unit["unit_id"]
    session_ref = "p-" + "1" * 24
    base = {
        "events": [{"event_id": "v-1", "at_record": "500/message/content", "kind": "request"}],
        "checks": {"candidates": [{"candidate_id": "k-1", "named_units_absent": [],
                                   "retrieved_units": [{"unit_id": unit_id, "layer": "catalog", "rank": 1,
                                                        "score": 1.0, "named": True, "copies": 1}]}]},
        "candidates": {"candidates": [{"candidate_id": "k-1", "sessions": ["claude:t-1"],
                                       "event_ids": ["v-1"]}]},
        "current": current_doc,
        "sessions": {"sessions": [{"session_ref": session_ref, "session": "claude:t-1",
                                   "transcript": {"host": "claude", "id": "t-1", "source": "claude_projects"},
                                   "pin": {"status": "read", "content_ref": "b" * 64, "baseline_ref": None,
                                           "include_global_instructions": True, "reason": None},
                                   "selection": {"status": "read", "reason": None,
                                                 "inventory_ref": "i-" + "a" * 24},
                                   "delivery": {"status": "unknown", "reason": None, "event_refs": []}}],
                     "events": [{"event_id": "e-1", "kind": "session_injection", "session_ref": session_ref,
                                 "line": 10, "at": "2026-09-16T07:44:40+00:00", "members": []}]},
        # The row set in the shape `inventory.schema.json` `release_rows` REQUIRES: the item
        # membership is the referenced inventory's, not a field of this row set (it has none), and
        # `layers` carries the per-layer status with `minItems: 1`. The fixture carried `items` and
        # no `layers`, which no producer writes — and `release_of` read exactly that invented shape
        # (the WP-11b review).
        "release": {"sessions": [{"session_ref": session_ref, "segments": [],
                                  "unsegmented": {"inventory_refs": ["i-" + "b" * 24],
                                                  "layers": [{"layer": "catalog",
                                                              "status": "complete", "reasons": [],
                                                              "source": {"inventory_ref":
                                                                         "i-" + "b" * 24,
                                                                         "layer": "catalog",
                                                                         "basis":
                                                                         "selection_history"}}],
                                                  "complete": True,
                                                  "incomplete_reasons": []}}]},
        # The release's own inventory, keyed by its ref: what the owner's library HELD at the
        # session's reference point, which is not what the session received.
        # ITEMS only, no carriers: `selected_items` resolves a carrier's version through the store,
        # and this fixture's store deliberately maps that version to another item — so carrying the
        # carrier here would overwrite the release's own membership with the selection's.
        "shared_by_ref": {"i-" + "b" * 24: {"items": [{"ref": item_ref, "surface": "always"}]}},
        "store": {"versions": {carrier_id: {version: {"item_ref": item_ref}}}, "units": {}},
        "shared": {"carriers": [{"carrier_id": carrier_id, "version_sha256": version}],
                   "items": [{"ref": item_ref, "surface": "always"}],
                   "instruction_text_sha256": "d" * 64,
                   "instruction_coverage": [{"unit_ref": unit_ref, "covered": 1, "total": 1}],
                   "item_pointer_in_compiled_text": [{"ref": item_ref, "pointer": None,
                                                      "basis": "surface_has_no_pointer"}],
                   "router_path": None,
                   "unit_surfaces": [{"unit_ref": unit_ref, "surface": "always",
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
                                    "instruction_coverage": [{"unit_ref": unit_ref, "covered": 0,
                                                              "total": 1}]}},
                {"state": "unknown", "reason": "absent_from_compiled_text"})
    if path_id == "selected_unavailable":
        return ({**base, "shared": {**base["shared"],
                                    "unavailable": [{"ref": item_ref, "surface": "always",
                                                     "reason": "route_absent"}]}},
                {"state": "selected_unavailable", "level": "selected"})
    if path_id == "not_delivered/selection_lacks_item":
        # The catalogue route, reachable since S2 publishes the catalogue surface of a unit whose
        # item the session was NOT given: the selection was read and holds another item, the release
        # holds this one at a complete reference point, and the ladder is classified from the
        # baseline. Before those facts the judge answered `surface_unclassified` and §6.3's absence
        # could not be found at all.
        return ({**base,
                 "store": {"versions": {carrier_id: {version: {"item_ref": "claude:other"}}},
                           "units": {}},
                 "shared": {**base["shared"],
                            "items": [{"ref": "claude:other", "surface": "always"}],
                            "instruction_coverage": [],
                            "item_pointer_in_compiled_text": [{"ref": "claude:other", "pointer": None,
                                                               "basis": "surface_has_no_pointer"}],
                            "unit_surfaces": [{"unit_ref": unit_ref, "surface": "always",
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
        # The native route gets its own PRODUCED document, from a carrier in the native layer: a
        # unit copied from the catalogue one and relabelled would carry a carrier id derived from
        # the catalogue layer, which no producer would ever emit for a native unit.
        native_doc, _native_unit = _producer_current(text="- the rule\n", path="CLAUDE.md",
                                                     layer="native_global", item_ref="native:global")
        native_operative = [u for u in native_doc["units"] if u.get("class") == "operative"]
        native_id = native_operative[0]["unit_id"]
        return ({**base,
                 "current": native_doc,
                 # The pair is owed for the NATIVE document's unit: leaving the catalogue id here
                 # left the fixture owing no pair at all, and `run_fixture` then reported
                 # FIXTURE_NO_ROW rather than the state this fixture exists to pin.
                 "checks": {"candidates": [{"candidate_id": "k-1", "named_units_absent": [],
                                            "retrieved_units": [{"unit_id": native_id,
                                                                 "layer": "native_global", "rank": 1,
                                                                 "score": 1.0, "named": True,
                                                                 "copies": 1}]}]},
                 "sessions": {**base["sessions"],
                              "events": [{"event_id": "e-1", "kind": "native", "session_ref": session_ref,
                                          "line": 10, "at": "2026-09-16T07:44:40+00:00",
                                          "members": [{"carrier_id": "c-" + "9" * 24,
                                                       "version_sha256": "f" * 64, "ordinal": 0}]}]},
                 # A native unit's item is not a catalogue item, so no surface is published for it;
                 # the ladder comes from its layer, which is the point of this fixture.
                 "shared": {**base["shared"],
                            # No coverage rows: coverage is published per catalogue unit, and the
                            # base block's row names the catalogue reference, which resolves to
                            # nothing in this document. Carrying it made the fixture answer
                            # `coverage_ref_unresolved` instead of the absence it exists to pin.
                            "instruction_coverage": [],
                            "unit_surfaces": [{"unit_ref": native_operative[0]["unit_ref"],
                                               "surface": None,
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
                            "unit_surfaces": [{"unit_ref": unit_ref, "surface": "requested",
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
        subject = None
        if artifacts is not None:
            operative = [u for u in (artifacts["current"].get("units") or [])
                         if u.get("class") == "operative"]
            subject = operative[0]["unit_id"] if operative else None
        fixtures.append({"id": path_id, "artifacts": artifacts, "expected": expected,
                         "subject_unit": subject})
    doc = {"$comment": "design §6.3 at the records level: one frozen fixture per state path "
                       "`runlib/stage_delivery.py` can write, each a whole set of run-shaped artifacts "
                       "driven through `document`. Written once by `stage_delivery.py "
                       "--generate-fixtures`; the self-test never regenerates them.",
           "fixtures": fixtures}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(fixtures)


# Which schema judges each frozen artifact, and for the ones no schema judges, why. The review of
# this package found the fixtures built from shapes no producer emits; a schema check is what makes
# that decidable rather than remembered. `current` is the one artifact with a published schema for
# the whole document, and it is the one the finding was about.
FIXTURE_SCHEMAS = {"current": ("inventory.schema.json", "current_document")}
FIXTURE_UNSCHEMAED = {
    "checks": "the fixture carries only the `candidates` block this stage reads; checks.schema.json "
              "describes the WHOLE S5 document, so validating a deliberate subset against it would "
              "fail on the blocks this stage never touches",
    "candidates": "S4's document is described by form.schema.json at the whole-document level, and "
                  "the fixture carries the two rows this stage reads",
    "sessions": "S2's session document has no published schema in session-distill/schemas",
    "release": "the release document has no published schema",
    "store": "the instruction store is state, not a stage document",
    "shared": "the selection inventory's shared block has no published schema of its own",
    "events": "an event record is validated by event.schema.json per LINE, not as a list; the "
              "fixture's rows are written into a .jsonl by `run_fixture` and read back by the stage",
    "copy": "a list of file names",
    "shared_by_ref": "one selection-inventory block per inventory ref, and that block has no "
                     "published schema of its own (the same reason as `shared`); the REFS are "
                     "judged by `release_of` reading them, and the fixture would fail its own "
                     "state path if a ref it names were not the one the release points at",
}


def fixture_schema_problems(frozen=None):
    """Every frozen artifact judged by its producer's schema, or named with why none judges it.

    An artifact nobody validates is how a fixture drifts from its producer: this library's `current`
    documents carried `block` as an object with a `start` in it, which `inventory.schema.json` would
    have refused the day it was written.
    """
    from runlib import validate

    frozen = frozen or json.loads(pathlib.Path(FIXTURES_PATH).read_text(encoding="utf-8"))
    problems, validators = [], {}
    for artifact, (schema_file, definition) in FIXTURE_SCHEMAS.items():
        schema = json.loads((HERE / "schemas" / schema_file).read_text(encoding="utf-8"))
        held = dict(schema["$defs"][definition])
        held["$defs"] = schema["$defs"]
        held["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        validators[artifact] = validate.compile_schema(held)
    judged = 0
    for fixture in frozen.get("fixtures") or []:
        artifacts = fixture.get("artifacts")
        if artifacts is None:
            continue
        for artifact, value in artifacts.items():
            if artifact in validators:
                judged += 1
                for problem in validate.validate_instance(validators[artifact], value):
                    problems.append(f"FIXTURE_SHAPE {fixture['id']} {artifact}: {problem}")
            elif artifact not in FIXTURE_UNSCHEMAED:
                problems.append(f"FIXTURE_UNJUDGED {fixture['id']} {artifact}: no schema judges this "
                                f"artifact and no reason is declared for it, so it can drift from "
                                f"its producer unnoticed")
    if not judged:
        problems.append("FIXTURE_SCHEMA_SCOPE_EMPTY: no artifact was judged by a schema, so a "
                        "green answer here would be about nothing")
    return problems


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
    # The event file is named the way the PRODUCER names it, and the views row the fixture hands
    # `document` carries that same name. Both come from `views.safe_name`, imported rather than
    # imitated: the join these fixtures exercise is the name mapping S2 publishes, and a fixture
    # that spelled the name itself would be testing a spelling nobody writes (the WP-11b review,
    # whose finding was exactly that the spelling and the reader disagreed).
    from runlib import views as _views
    session = dict(artifacts["sessions"])
    transcript_id = ((session.get("sessions") or [{}])[0].get("transcript") or {}).get("id") \
        or "claude:t-1"
    stem = _views.safe_name(transcript_id)
    (run_dir / EVENTS_DIR / f"{stem}.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in artifacts["events"]), encoding="utf-8")
    fixture_views = {"transcripts": [
        {"name": stem, "segment": stem, "transcript": transcript_id,
         "session": (session.get("sessions") or [{}])[0].get("session"),
         "host": (session.get("sessions") or [{}])[0].get("host") or "claude"}]}
    # One answer per REF, not one answer for every ref: the release's reference point and the
    # session's selection are different inventories, and a `shared_of` that answered alike could not
    # express a release holding an item the session was not given — which is §6.3's catalogue
    # absence (the WP-11b review).
    by_ref = artifacts.get("shared_by_ref") or {}

    def fixture_shared_of(ref):
        return by_ref.get(ref, artifacts["shared"])

    doc = document(run_dir, artifacts["checks"], artifacts["candidates"], artifacts["current"], session,
                   artifacts["release"], artifacts["store"], fixture_shared_of,
                   artifacts["copy"] or ["aa.jsonl"], fixture_views)
    # The subject is named by the fixture, because the unit id now comes from the producer and is a
    # digest, not "u-1". A hardcoded id here would silently select nothing and the fixture would
    # report FIXTURE_NO_ROW for every path.
    subject = fixture.get("subject_unit")
    if not subject:
        return [f"FIXTURE_SUBJECT_UNNAMED {fixture['id']}: the fixture does not say which unit its "
                f"expectation is about, so no row can be selected"]
    rows = [row for row in doc["rows"] if row["unit_id"] == subject]
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

    def _body():
        return _self_test_body(failures, ran)

    # A crash must not swallow what the suite already knows. The defect this package was fixed for
    # raised AttributeError inside `unit_index`, so a revert trial over it reported an exit code and
    # nothing else: the controls that would have NAMED the defect had already run, and their
    # failures were printed only at the end. Printing them before re-raising is what turns a
    # traceback into evidence.
    try:
        return _body()
    except BaseException as exc:
        # Printed even when nothing had failed yet, because the crash itself is the finding: the
        # defect this package was fixed for raised inside `unit_index` on the FIRST document call,
        # so a revert trial saw an exit code with no text and reported the control as silent.
        print(f"stage_delivery --self-test: INCOMPLETE ({len(ran)} controls ran, "
              f"{len(failures)} already failing when the suite died)", file=sys.stderr)
        print(f"stage_delivery --self-test [FAIL] the suite died: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        for held in failures:
            print(f"stage_delivery --self-test [FAIL] {held}", file=sys.stderr)
        raise


def _self_test_body(failures, ran):
    """The suite itself. Split out only so a crash can report the failures already collected."""

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
             "retrieved_units": [{"unit_id": None, "layer": "catalog", "rank": 1, "score": 1.0,
                                  "named": True, "copies": 1}],      # filled with u1 below
             "named_units_absent": ["u-gone"]},
            {"candidate_id": "k-2", "retrieved_units": [], "named_units_absent": []}]}
        candidates = {"candidates": [
            {"candidate_id": "k-1", "sessions": ["claude:t-1"], "event_ids": ["v-1", "v-2"]},
            {"candidate_id": "k-2", "sessions": ["claude:t-1"], "event_ids": []}]}
        # The document comes from S2's producer over a guide written here, not from a unit shape
        # typed into this suite. The one it replaced carried `block` as an object with a `start` in
        # it, which no producer emits: every control below passed over that shape while
        # `unit_index` raised AttributeError on every real document. Ids are digests now, so the
        # suite binds names to them instead of spelling them.
        current, _subject = _producer_current(
            text="# Guide\n\n- the first rule\n- the second rule\n")
        operative_units = [u for u in current["units"] if u.get("class") == "operative"]
        u1, u2 = operative_units[0]["unit_id"], operative_units[1]["unit_id"]
        heading_unit = next(u["unit_id"] for u in current["units"] if u.get("class") != "operative")
        # An id the producer did not emit, for the control that the closure is not substituted for
        # the one-step set.
        u_absent = "u-" + "0" * 16
        carrier_fx = operative_units[0]["carrier_id"]
        version_fx = operative_units[0]["version_sha256"]
        item_fx = operative_units[0]["item_ref"]
        ref_u1 = operative_units[0]["unit_ref"]
        ref_u2 = operative_units[1]["unit_ref"]
        checks["candidates"][0]["retrieved_units"][0]["unit_id"] = u1
        sessions = {"sessions": [{"session_ref": "p-" + "1" * 24, "session": "claude:t-1",
                                  "transcript": {"host": "claude", "id": "t-1", "source": "claude_projects"},
                                  "pin": {"status": "read", "content_ref": "b" * 64, "baseline_ref": None,
                                          "include_global_instructions": True, "reason": None},
                                  "selection": {"status": "unknown", "reason": "input_failed",
                                                "inventory_ref": None},
                                  "delivery": {"status": "unknown", "reason": "input_failed", "event_refs": []}}]}
        release_doc = {"sessions": [{"session_ref": "p-" + "1" * 24, "segments": [],
                                     "unsegmented": {"inventory_refs": [],
                                                     "layers": [{"layer": "catalog",
                                                                 "status": "unknown",
                                                                 "reasons": [
                                                                     "release_history_deferred"],
                                                                 "source": None}],
                                                     "complete": False,
                                                     "incomplete_reasons": [
                                                         {"layer": "catalog", "status": "unknown",
                                                          "reasons": ["release_history_deferred"],
                                                          "inventory_ref": None}]}}]}
        store = {"versions": {}, "units": {}}
        # The views document S2 publishes, named with the producer's own namer so the suite cannot
        # spell the join differently from the stage. `claude:t-1` -> `claude_t-1`, which is also
        # what the event file above is called.
        from runlib import views as _views_mod
        suite_views = {"transcripts": [
            {"name": _views_mod.safe_name("claude:t-1"), "segment": _views_mod.safe_name("claude:t-1"),
             "transcript": "t-1", "session": "claude:t-1", "host": "claude"}]}
        doc = document(fixture, checks, candidates, current, sessions, release_doc, store,
                       lambda ref: None, ["aa.jsonl"], suite_views)
        # k-1: two events x two units (one retrieved, one named-absent) = 4; k-2: one session, no event, no unit = 1.
        control("a pair is owed per decision event and unit", str(doc["summary"]["pairs"]), "5")
        control("an event's ordinal is read from its at_record", json.dumps((doc.get("rows") or [{}])[0]),
                '"decision_at": 76837')
        control("and the session comes from the transcript the event record belongs to",
                json.dumps((doc.get("rows") or [{}])[0]), '"session_ref": "p-111111111111111111111111"')
        # ---- the version universe this run names --------------------------------------------------
        #
        # `delivery` defaults `versions` to the CURRENT units alone and this stage passed none, so
        # the shared store's historical versions were invisible to the byte binding: a read of an
        # older version of a carrier was matched against the current text only (the WP-11b review).
        # The run holds those versions — the store keys each one, lists its `unit_refs` in order,
        # and each store unit carries its own projected text.
        older = "a" * 64
        store_with_history = {
            "versions": {"c-" + "1" * 24: {older: {"layer": "catalog", "path": "claude/guides/g.md",
                                                   "item_ref": "claude:guides/g",
                                                   "package_id": None, "form": "guide",
                                                   "length": 20, "split": True,
                                                   "unit_refs": ["r-" + "1" * 24]}}},
            "units": {"r-" + "1" * 24: {"carrier_id": "c-" + "1" * 24, "version_sha256": older,
                                        "n": 0, "start": 0, "end": 20, "sha": "b" * 64,
                                        "heading": None, "text": "- the older line\n",
                                        "class": "operative", "block": "list-item",
                                        "redaction_version": "r22"}}}
        held_universe = version_universe(current, store_with_history)
        control("the store's historical version is in the universe, keyed by its own path",
                json.dumps(sorted(held_universe.get("claude/guides/g.md") or {})), older)
        control("and its lines are the version's own units, in the version's order",
                json.dumps((held_universe.get("claude/guides/g.md") or {}).get(older)),
                "- the older line")
        clean("the current document's versions are still there, so the universe is a union and not "
              "a replacement",
              [] if len(held_universe.get(
                  [unit["path"] for unit in current["units"]][0]) or {}) >= 1
              else ["the current version was lost from the universe"])
        control("a store version whose units this run holds no text for is left out rather than "
                "entered with an empty line set, since empty lines match everything",
                json.dumps(sorted(version_universe(current, {
                    "versions": {"c-" + "2" * 24: {"c" * 64: {"path": "claude/guides/h.md",
                                                              "unit_refs": ["r-gone"]}}},
                    "units": {}}).get("claude/guides/h.md") or {})),
                "[]")
        control("the line rule is the judge's own, reached rather than restated",
                next((line.strip() for line in inspect.getsource(version_universe).splitlines()
                      if "versions_of(" in line), "<no such line>"),
                "delivery_evidence.versions_of(")
        control("and the document hands the judge that universe rather than letting it default to "
                "the current units",
                next((line.strip() for line in inspect.getsource(document).splitlines()
                      if "versions=" in line), "<no such line>"),
                "versions=universe")

        # ---- the bytes that decided the verdict, published ---------------------------------------
        #
        # `run_stage` pins every DECLARED input against its producer's recorded output digest. The
        # event records, the shared store and the per-session selection inventories are read by
        # this stage and are not declarable that way — which ones exist depends on the run — so a
        # change to them between S2 and a later reader was not knowable at all (the WP-11b review).
        # Their digests are published with the document that rests on them.
        bound_doc = document(fixture, checks, candidates, current, sessions, release_doc, store,
                             lambda ref: None, ["aa.jsonl"], suite_views)
        control("the event records this stage read are bound by digest in its own document",
                json.dumps([row["path"] for row in bound_doc["consumed"]]),
                f"{EVENTS_DIR}/claude_t-1.jsonl")
        clean("every bound row carries a full sha256, so the binding is a value and not a label",
              [row for row in bound_doc["consumed"]
               if len(row.get("sha256") or "") != 64])
        control("the digest is the file's own, not a recomputation of something else",
                [row["sha256"] for row in bound_doc["consumed"]
                 if row["path"].endswith("claude_t-1.jsonl")][0],
                records.sha256_file(fixture / EVENTS_DIR / "claude_t-1.jsonl"))
        clean("a file the run does not hold is not bound, since a digest of nothing is a claim",
              [row for row in bound_doc["consumed"] if "store.json" in row["path"]])
        control("and the document says why these are published rather than declared",
                bound_doc["consumed_unpinnable"], "not declarable inputs")
        # The binding MOVES when the bytes move: this is what makes it worth publishing.
        (fixture / EVENTS_DIR / "claude_t-1.jsonl").write_text(
            json.dumps({"event_id": "v-1", "at_record": "76837/message/content",
                        "kind": "request"}) + "\n"
            + json.dumps({"event_id": "v-2", "at_record": "9/message/content/0",
                          "kind": "request"}) + "\n"
            + json.dumps({"event_id": "v-3", "at_record": "11/message", "kind": "request"}) + "\n",
            encoding="utf-8")
        moved_doc = document(fixture, checks, candidates, current, sessions, release_doc, store,
                             lambda ref: None, ["aa.jsonl"], suite_views)
        control("a change to an event record changes the binding, which is the whole point of "
                "publishing it",
                json.dumps(bound_doc["consumed"] != moved_doc["consumed"]), "true")

        # ---- S5's checked population, planted controls included ----------------------------------
        #
        # S5 publishes `checked-candidates.json`: S4's candidates PLUS the planted controls of
        # design §6.5, which is the population S6 judges. This stage enumerated only S4's, so a
        # planted control and its retrieved units were never pairs it owed an answer for — silently,
        # so the denominator shrank with no row saying so (the WP-11b review). A planted control
        # carries a fabricated session id, so its pair is answered with a reason; that is the point,
        # and it is not the same as never being asked.
        planted_population = {"candidates": [
            {"candidate_id": "k-1", "source": "g_cluster", "sessions": ["claude:t-1"]},
            {"candidate_id": "k-planted", "source": "control_absence",
             "sessions": ["claude:fabricated-0001"]}]}
        planted_checks = {"candidates": checks["candidates"] + [
            {"candidate_id": "k-planted", "source": "control_absence",
             "retrieved_units": [{"unit_id": u1, "layer": "catalog", "rank": 1, "score": 1.0,
                                  "named": True, "copies": 1}],
             "named_units_absent": []}]}
        doc_pl = document(fixture, planted_checks, candidates, current, sessions, release_doc,
                          store, lambda ref: None, ["aa.jsonl"], suite_views, planted_population)
        pl_rows = [row for row in doc_pl["rows"] if row["candidate_id"] == "k-planted"]
        control("a planted control S5 checked is a pair this stage owes an answer for",
                json.dumps([row["unit_id"] for row in pl_rows]), u1)
        control("and the row says which producer's population it came from",
                json.dumps([row["producer"] for row in pl_rows]), "S5")
        control("its fabricated session is answered with a reason, which is not the same as the "
                "pair never being asked",
                json.dumps([row["reasons"] for row in pl_rows]), "session_absent_from_inventory")
        control("the summary counts the pairs by producer, so a shrinking denominator is visible",
                json.dumps(doc_pl["summary"]["pairs_by_producer"]), '"S5": 1')
        clean("a candidate S4 already names is not enumerated twice",
              [cid for cid in {row["candidate_id"] for row in doc_pl["rows"]}
               if len([row for row in doc_pl["rows"]
                       if row["candidate_id"] == cid and row["unit_id"] == u1
                       and row["event_id"] is None]) > 1])
        control("and without the population nothing is lost for S4's own pairs, so the enumeration "
                "only adds",
                str(len([row for row in document(
                    fixture, planted_checks, candidates, current, sessions, release_doc, store,
                    lambda ref: None, ["aa.jsonl"], suite_views)["rows"]
                    if row["candidate_id"] == "k-planted"])),
                "0")
        control("the stage declares that artifact with its producer, so a change to it invalidates "
                "this stage",
                json.dumps([row for row in INPUTS if "checked" in row["artifact"]]),
                '"producer_stage": "S5"')

        # ---- the required inputs depend on the LADDER, not on the pin ----------------------------
        #
        # Any `basis is None` added a reason, and the judge was called only when NO reason held: an
        # unpinned session with a native event that explicitly loaded the unit answered
        # `unknown: unpinned` over evidence that was already sufficient (the WP-11b review). §6.3's
        # native rung is answered by the session's own events; the selection pin says nothing about
        # it. The reason is still CARRIED onto the row, because a reader counts it.
        native_doc, native_unit = _producer_current(text="- the native rule\n", path="CLAUDE.md",
                                                    layer="native_global", item_ref="native:global")
        native_id = native_unit["unit_id"]
        native_carrier = native_unit["carrier_id"]
        native_version = native_unit["version_sha256"]
        unpinned_ref = "p-" + "7" * 24
        unpinned_sessions = {"sessions": [
            {"session_ref": unpinned_ref, "session": "claude:t-np", "host": "claude",
             "transcript": {"host": "claude", "id": "t-np", "source": "claude_projects"},
             # NOT pinned: the inventory could not read the pin at all.
             "pin": {"status": "unknown", "content_ref": None, "baseline_ref": None,
                     "include_global_instructions": True, "reason": "pin_unreadable"},
             "selection": {"status": "unknown", "reason": "input_failed", "inventory_ref": None},
             "delivery": {"status": "unknown", "reason": "input_failed", "event_refs": []}}],
            "events": [{"event_id": "e-np", "kind": "native", "session_ref": unpinned_ref,
                        "line": 3, "at": "2026-11-01T00:00:00+00:00",
                        "members": [{"carrier_id": native_carrier,
                                     "version_sha256": native_version, "ordinal": 0}]}]}
        (fixture / EVENTS_DIR / "claude_t-np.jsonl").write_text(
            json.dumps({"event_id": "v-np", "at_record": "9/message/content",
                        "kind": "request"}) + "\n", encoding="utf-8")
        unpinned_views = {"transcripts": [
            {"name": "claude_t-np", "segment": "claude_t-np", "transcript": "t-np",
             "session": "claude:t-np", "host": "claude"}]}
        unpinned_doc = document(
            fixture,
            {"candidates": [{"candidate_id": "k-np", "named_units_absent": [],
                             "retrieved_units": [{"unit_id": native_id, "layer": "native_global",
                                                  "rank": 1, "score": 1.0, "named": True,
                                                  "copies": 1}]}]},
            {"candidates": [{"candidate_id": "k-np", "sessions": ["claude:t-np"],
                             "event_ids": ["v-np"]}]},
            native_doc, unpinned_sessions,
            {"sessions": [{"session_ref": unpinned_ref, "segments": [],
                           "unsegmented": {"inventory_refs": [], "complete": True,
                                           "layers": [{"layer": "catalog", "status": "complete",
                                                       "reasons": [], "source": None}],
                                           "incomplete_reasons": []}}]},
            {"versions": {}, "units": {}}, lambda ref: None, ["aa.jsonl"], unpinned_views)
        np_rows = [row for row in unpinned_doc["rows"] if row["unit_id"] == native_id]
        clean("an unpinned session whose own event loaded the unit is JUDGED rather than answered "
              "unknown for want of a pin",
              [row["state"] for row in np_rows if row["state"] == "unknown"])
        # `basis_of` reports the SELECTION's reason first, which is the one that actually failed
        # here; the control names what the code says rather than what the fixture's pin field says.
        control("and the missing basis is still on the row, because a reader counts it",
                json.dumps([row["reasons"] for row in np_rows]), "selection_input_failed")
        control("the judge answered on the native rung, which needs no selection",
                json.dumps([row["state"] for row in np_rows]), "delivered")
        # And the other direction: a unit the session's events do NOT load still needs the pin,
        # because nothing else in this run can say whether the session was given it.
        other_doc, other_unit = _producer_current(text="- another rule\n", path="CLAUDE.md",
                                                  layer="native_global", item_ref="native:other")
        unloaded_doc = document(
            fixture,
            {"candidates": [{"candidate_id": "k-nq", "named_units_absent": [],
                             "retrieved_units": [{"unit_id": other_unit["unit_id"],
                                                  "layer": "native_global", "rank": 1,
                                                  "score": 1.0, "named": True, "copies": 1}]}]},
            {"candidates": [{"candidate_id": "k-nq", "sessions": ["claude:t-np"],
                             "event_ids": ["v-np"]}]},
            other_doc, unpinned_sessions,
            {"sessions": [{"session_ref": unpinned_ref, "segments": [],
                           "unsegmented": {"inventory_refs": [], "complete": True,
                                           "layers": [{"layer": "catalog", "status": "complete",
                                                       "reasons": [], "source": None}],
                                           "incomplete_reasons": []}}]},
            {"versions": {}, "units": {}}, lambda ref: None, ["aa.jsonl"], unpinned_views)
        nq_rows = [row for row in unloaded_doc["rows"]
                   if row["unit_id"] == other_unit["unit_id"]]
        control("a unit no event of that session loaded still needs the basis, and says so",
                json.dumps([row["reasons"] for row in nq_rows]), "selection_input_failed")
        control("and that unjudged pair says the judge was not called",
                json.dumps([row["reasons"] for row in nq_rows]), "delivery_unjudged")
        control("and that pair is unknown, since nothing in this run can say it was given",
                json.dumps([row["state"] for row in nq_rows]), "unknown")

        # ---- the session join reads S2's mapping, not the file stem's spelling -------------------
        #
        # `views.safe_name` turns a Codex coverage key `codex:<id>@<segment>` into
        # `codex_<id>_<segment>`. The join removed the first underscore prefix and used the rest as
        # a transcript id, which for Codex left `<id>_<segment>` — no transcript at all — so every
        # Codex event joined to nothing and was reported `session_unmatched` (the WP-11b review).
        # The key below is built with `census.coverage_key`'s own shape through `safe_name`, so the
        # control cannot spell it differently from the producer.
        codex_key = "codex:0199c3f7-aaaa-bbbb-cccc-00000000@rollout-2026-11-01"
        codex_stem = _views_mod.safe_name(codex_key)
        control("a Codex event file's name carries the segment as well as the id, which is why "
                "splitting it left neither",
                f"{codex_stem} -> {codex_stem.split('_', 1)[-1]}",
                "codex_0199c3f7-aaaa-bbbb-cccc-00000000_rollout-2026-11-01 -> "
                "0199c3f7-aaaa-bbbb-cccc-00000000_rollout-2026-11-01")
        (fixture / EVENTS_DIR / f"{codex_stem}.jsonl").write_text(
            json.dumps({"event_id": "v-cx", "at_record": "41/message/content",
                        "kind": "request"}) + "\n", encoding="utf-8")
        codex_views = {"transcripts": suite_views["transcripts"] + [
            {"name": codex_stem, "segment": codex_stem, "transcript": "cx-1",
             "session": codex_key, "host": "codex"}]}
        codex_sessions = {"sessions": sessions["sessions"] + [
            {**sessions["sessions"][0], "session_ref": "p-" + "2" * 24, "session": codex_key,
             "transcript": {"host": "codex", "id": "cx-1", "source": "codex_sessions"}}],
            "events": sessions.get("events") or []}
        codex_candidates = {"candidates": candidates["candidates"] + [
            {"candidate_id": "k-cx", "sessions": [codex_key], "event_ids": ["v-cx"]}]}
        codex_checks = {"candidates": checks["candidates"] + [
            {"candidate_id": "k-cx", "retrieved_units": [], "named_units_absent": []}]}
        doc_cx = document(fixture, codex_checks, codex_candidates, current, codex_sessions,
                          release_doc, store, lambda ref: None, ["aa.jsonl"], codex_views)
        cx_rows = [row for row in doc_cx["rows"] if row["event_id"] == "v-cx"]
        control("a Codex event joins to its session through that mapping",
                json.dumps(cx_rows), '"session_ref": "p-222222222222222222222222"')
        clean("and is not reported unmatched, which is what every Codex pair was",
              [row for row in cx_rows if row.get("reason") in ("session_unmatched",
                                                               "view_unmatched")])
        control("and its ordinal comes from its own event record", json.dumps(cx_rows),
                '"decision_at": 41')
        # A stem no views row names is `view_unmatched`, which says WHICH half of the join failed.
        (fixture / EVENTS_DIR / "codex_unlisted.jsonl").write_text(
            json.dumps({"event_id": "v-un", "at_record": "7/message", "kind": "request"}) + "\n",
            encoding="utf-8")
        doc_un = document(fixture, {"candidates": checks["candidates"] + [
            {"candidate_id": "k-un", "retrieved_units": [], "named_units_absent": []}]},
            {"candidates": candidates["candidates"] + [
                {"candidate_id": "k-un", "sessions": [], "event_ids": ["v-un"]}]},
            current, codex_sessions, release_doc, store, lambda ref: None, ["aa.jsonl"],
            codex_views)
        # The reason reaches the row's `reasons` list, which is where a reader counts them.
        un_reasons = [row["reasons"] for row in doc_un["rows"] if row["event_id"] == "v-un"]
        control("an event file no views row names is reported as the view half failing, not as an "
                "unmatched session",
                json.dumps(un_reasons), "view_unmatched")
        clean("and it is NOT reported as an unmatched session, which would point at the wrong half",
              [reasons for reasons in un_reasons if "session_unmatched" in reasons])
        control("a Codex pair whose view IS named reports neither half failing",
                json.dumps(sorted({reason for row in cx_rows for reason in row["reasons"]
                                   if reason in ("view_unmatched", "session_unmatched")})),
                "[]")

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
        held_said = None
        try:
            units = unit_index(current)
        except BaseException as exc:
            held_said = f"{type(exc).__name__}: {exc}"
            failures.append("the index reads a produced document without raising: " + held_said)
            units = {}
        # The expectation is the producer's own edges for that unit, read off the document that was
        # handed in — an input, not something this function computed.
        want_context = sorted({u1, *(operative_units[0]["edges"]["direct"] or []),
                               *(operative_units[0]["edges"]["reached"] or [])})
        control("the operative context is direct plus one-step reached",
                json.dumps(units[u1]["operative_context"]), json.dumps(want_context))
        clean("and the transitive closure is not what was read",
              [u for u in units.values() if u_absent in u["operative_context"]])
        control("the source of that set is named in the row", units[u1]["context_source"], "inventory.edges")
        # `block` is the KIND, a string, and `start` is not published at all. This index read
        # `block` as an object and took `start` out of it, so it worked on every frozen fixture --
        # which carried that invented shape -- and raised AttributeError on every real document.
        # Asked BEFORE anything that could crash on the same shape, and asked through a guard, so
        # a revert of the fix produces a named failure here rather than only an exit code.
        def said(call):
            try:
                call()
            except BaseException as exc:          # the exception IS this control's answer
                return f"{type(exc).__name__}: {exc}"
            return "no exception"

        control("the index reads a produced document without raising: `block` is a string and "
                "digging `start` out of it is what crashed on every real document",
                said(lambda: unit_index(current)), "no exception")
        held_index = units[u1]
        control("the unit carries the producer's block KIND, a string",
                json.dumps({"block": held_index["block"]}),
                json.dumps({"block": operative_units[0]["block"]}))
        control("and `start` is None because the emitted document does not publish it, rather than "
                "being dug out of `block`",
                json.dumps({"start": held_index["start"]}), '{"start": null}')
        control("a unit whose `block` is an object -- the shape the old fixtures carried -- is "
                "refused by name instead of raising AttributeError",
                refusal(lambda: unit_index(
                    {"units": [{**operative_units[0], "block": {"start": 100}}]})),
                "DELIVERY_UNIT_SHAPE")
        no_edges = {"units": [{**operative_units[0], "edges": None}]}
        control("an inventory that publishes no edges is refused by name",
                refusal(lambda: unit_index(no_edges)), "DELIVERY_EDGES_ABSENT")

        # ---- the inventory's half of the session evidence (commit 3) ----
        session_row = sessions["sessions"][0]
        events_by_ref = {"p-" + "1" * 24: [
            {"event_id": "e-1", "kind": "native", "session_ref": "p-" + "1" * 24, "line": 12,
             "at": "2026-09-16T07:44:40.323000+00:00",
             "members": [{"carrier_id": carrier_fx, "version_sha256": version_fx, "ordinal": 0}]},
            {"event_id": "e-2", "kind": "native", "session_ref": "p-" + "1" * 24, "line": None,
             "at": "2026-09-16T07:45:00.000000+00:00", "members": []}]}
        evidence, counts = session_evidence(session_row, events_by_ref,
                                            units_by_version(unit_index(current)), release_doc,
                                            lambda ref: None, store)
        control("a native event is placed at its record line, not its instant",
                json.dumps((evidence.get("native_events") or [{}])[0]), '"at": 12')
        control("and its carrier version is resolved to the units it loaded",
                json.dumps((evidence.get("native_events") or [{}])[0]),
                f'"unit_ids": {json.dumps(sorted([u1, u2, heading_unit]))}')
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
            "carriers": [{"carrier_id": carrier_fx, "version_sha256": version_fx}],
            "items": [{"ref": item_fx, "surface": "always"}],
            "instruction_text_sha256": "d" * 64,
            "instruction_coverage": [{"unit_ref": ref_u1, "covered": 1, "total": 2},
                                     {"unit_ref": "r-" + "9" * 24, "covered": 5, "total": 5}],
            "unavailable": [{"ref": item_fx, "surface": "always", "reason": "route_absent"}]}
        # The OPERATIVE units, with the refs the producer gave them: `current["units"][0]` is the
        # heading unit now, and attaching u1's reference to it put the coverage counts on the wrong
        # id while every control still passed.
        facts_units = [operative_units[0], operative_units[1]]
        facts_store = {"versions": {carrier_fx: {version_fx: {"item_ref": item_fx}}}, "units": {}}
        facts_row = {**session_row, "selection": {"status": "read", "reason": None,
                                                  "inventory_ref": "i-" + "a" * 24}}
        facts_evidence, facts_counts = session_evidence(
            facts_row, events_by_ref, units_by_version(unit_index(current)), release_doc,
            lambda ref: facts_shared, facts_store, None, None, facts_units)
        control("the per-unit coverage counts reach the judge under the unit ids it asks about",
                json.dumps(facts_evidence.get("instruction_coverage")),
                f'"{u1}": ' + '{"covered": 1, "total": 2}')
        # A published row whose reference resolves to no unit here: named and counted, never dropped.
        # The lead's correction (2026-11-11): a drop is a resolution failure, and a block that lost
        # every row to one would read like a session nobody published facts for.
        control("a coverage row naming a unit this run does not carry is named, not dropped",
                json.dumps(facts_counts.get("coverage_refs_unresolved")), "r-" + "9" * 24)
        clean("and no unit id is invented for it",
              [ref for ref in facts_evidence.get("instruction_coverage") or ()
               if ref not in (u1, u2, heading_unit)])
        facts_sessions = {"sessions": [{**facts_row}]}
        # The producer already gave every unit its `unit_ref`; zipping fresh constants onto the
        # document's units overwrote them, and the heading unit took u1's reference.
        facts_current = {"units": list(current["units"])}

        def facts_document(shared, current=None):
            """The rows and summary this stage writes when the session's inventory publishes `shared`."""
            doc_f = document(fixture, checks, candidates, current or facts_current, facts_sessions,
                             release_doc, facts_store, lambda ref: shared, ["aa.jsonl"],
                             suite_views)
            return {row["unit_id"]: row for row in doc_f["rows"]}, doc_f

        # The pair this fixture owes is u-1's, so the block that cannot answer for it is the one
        # naming another unit's reference.
        missed = {**facts_shared, "instruction_coverage": [{"unit_ref": "r-" + "9" * 24, "covered": 1, "total": 1}]}
        missed_rows, missed_doc = facts_document(missed)
        control("the pair whose coverage the block could not answer for names the failure",
                json.dumps(missed_rows.get(u1) or {}), UNRESOLVED)
        # Both kinds of row at once, which is what makes the next assertion about the PAIR rather
        # than about the session: the block answers for u-1 and also carries a reference nothing here
        # resolves, so only the per-pair clause can keep the failure off u-1's row.
        answered = {**facts_shared,
                    "instruction_coverage": [{"unit_ref": ref_u1, "covered": 1, "total": 2},
                                             {"unit_ref": "r-" + "9" * 24, "covered": 1, "total": 1}]}
        answered_rows, answered_doc = facts_document(answered)
        clean("and the pair the block did answer for does not, though its session has an unresolved one",
              ([UNRESOLVED] if UNRESOLVED in ((answered_rows.get(u1) or {}).get("reasons") or []) else [])
              + ([] if answered_doc["summary"]["coverage_refs_unresolved"] == 1
                 else ["the fixture's session has no unresolved reference, so the clause is untested"]))

        # ---- the judge's own answer (commit 7). The session here has a read pin, a selection
        # inventory and the facts, so every input §6.3 reads is present and the row is ITS answer
        # rather than this stage's unknown.
        judged_row = answered_rows.get(u1) or {}
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
        # Every frozen artifact held against its producer's schema, and each artifact no schema
        # judges named with its reason. This is what makes "the fixture is in the producer's shape"
        # decidable: `inventory.schema.json` would have refused the old `block: {"start": …}` unit
        # the day it was written.
        clean("every frozen artifact is judged by its producer's schema or says why not",
              fixture_schema_problems())
        planted_shape = {"fixtures": [{"id": "planted", "subject_unit": "u-x",
                                       "artifacts": {**frozen["fixtures"][0]["artifacts"],
                                                     "current": {"units": [
                                                         {**operative_units[0],
                                                          "block": {"start": 100}}]}},
                                       "expected": {"state": "delivered"}}]}
        control("a frozen unit in a shape the producer does not emit is refused by name — the "
                "defect this library was built with",
                "; ".join(fixture_schema_problems(planted_shape)), "FIXTURE_SHAPE planted current")
        control("and an artifact nobody judges and nobody excuses is named too",
                "; ".join(fixture_schema_problems(
                    {"fixtures": [{"id": "planted", "subject_unit": "u-x",
                                   "artifacts": {**frozen["fixtures"][0]["artifacts"],
                                                 "invented": {"what": "nothing produces this"}},
                                   "expected": {}}]})),
                "FIXTURE_UNJUDGED planted invented")
        control("a run that judged no artifact at all is refused, so a green answer cannot be "
                "about nothing",
                "; ".join(fixture_schema_problems({"fixtures": []})),
                "FIXTURE_SCHEMA_SCOPE_EMPTY")
        control("a fixture that does not name its subject unit is refused by name, since the ids "
                "are the producer's digests and no literal can stand in for them",
                "; ".join(run_fixture(root, {"id": "no-subject",
                                             "artifacts": frozen["fixtures"][0]["artifacts"],
                                             "expected": {"state": "delivered"}})),
                "FIXTURE_SUBJECT_UNNAMED")
        control("and a fixture whose artifacts owe no pair for its unit is named",
                "; ".join(run_fixture(root, {"id": "y", "artifacts": {
                    **(frozen["fixtures"][0]["artifacts"]),
                    "candidates": {"candidates": [{"candidate_id": "k-1", "sessions": ["claude:t-1"],
                                                   "event_ids": ["v-1"]}]},
                    "checks": {"candidates": [{"candidate_id": "k-1", "retrieved_units": [],
                                               "named_units_absent": []}]}},
                    "expected": {"state": "delivered"},
                    # Named, so the refusal is about the missing ROW and not about the missing name:
                    # with the subject unnamed the control met FIXTURE_SUBJECT_UNNAMED instead and
                    # stopped testing what it was written for.
                    "subject_unit": frozen["fixtures"][0]["subject_unit"]})),
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
                          "unit_surfaces": [{"unit_ref": ref_u1, "surface": "requested",
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
        # The REASON a pointer could not be established, which S2 publishes and this stage used to
        # drop. An absent list and an established absence read the same to the judge, and the judge
        # asserted "no pointer" from an input nobody had read (lane E's probe, P1).
        unavailable_shared = {**pointer_shared, "item_pointer_in_compiled_text": [],
                              "item_pointer_unavailable": "compiled_text_absent"}
        unavailable_evidence, _unavailable_counts = session_evidence(
            facts_row, events_by_ref, units_by_version(unit_index(current)), release_doc,
            lambda ref: unavailable_shared, facts_store, None, None, facts_units)
        control("the reason S2 publishes for a pointer it could not establish reaches the judge",
                json.dumps(unavailable_evidence.get("item_pointer_unavailable")),
                '"compiled_text_absent"')
        control("and the other reason it can publish reaches it the same way, since the two are "
                "different situations for a reader",
                json.dumps(session_evidence(
                    facts_row, events_by_ref, units_by_version(unit_index(current)), release_doc,
                    lambda ref: {**unavailable_shared,
                                 "item_pointer_unavailable": "catalog_rule_unread"},
                    facts_store, None, None, facts_units)[0].get("item_pointer_unavailable")),
                '"catalog_rule_unread"')
        clean("while a session whose pointers WERE established carries no reason, so the key is the "
              "unavailability and not a field that is always there",
              [key for key in pointer_evidence if key == "item_pointer_unavailable"])

        unplaced_unit = {"unit_id": "u-u", "path": "claude/guides/z.md", "text": "- z",
                         "version_sha256": "b" * 64, "layer": "catalog",
                         "item_ref": "claude:guides/z", "carrier_id": "c-" + "1" * 24, "n": 1,
                         "operative_context": ["u-u"]}

        # ONE owner for the surface rule, held by source: the stage translates the unit id to its
        # item ref and the rule answers. The copy this stage carried is the class of defect the
        # review found, so the control is that the stage no longer makes that decision itself.
        held_source = pathlib.Path(__file__).read_text(encoding="utf-8")
        control("the stage attaches a pair's surface through the one rule, not a copy of it",
                "yes" if "delivery_evidence.attach_surface(" in held_source else "no", "yes")
        # The stage still PUBLISHES `history_selected` as evidence, which is its job; what it may
        # no longer do is read it to decide a surface. That is the exact text of the copy that was
        # here, so the control names it rather than any mention of the field.
        # Assembled from pieces so that the pattern itself never appears as a literal in this
        # file: spelled whole, the control's own line matched it and the control failed on itself.
        held_copy = 'get("history_selected") or {}).' + 'get(unit'
        clean("and keeps no surface decision of its own: the copy read the session's selection, "
              "then its history, then the catalogue",
              [line.strip() for line in held_source.splitlines() if held_copy in line])
        # The native layers are the ones the TABLE names, read from it rather than spelled here:
        # a unit the table already places is returned untouched, because attaching a surface to one
        # moves it onto an item ladder (the frozen native fixture found that).
        held_native = next(row["layers"][0] for row in delivery_evidence.table()["surfaces"]
                           if row.get("layers"))
        control("the rule places a native unit by its layer, leaving it untouched rather than "
                "moving it onto an item ladder",
                json.dumps("surface" in delivery_evidence.attach_surface(
                    {"unit_id": "u-n", "layer": held_native, "item_ref": "claude:x"},
                    {"selected": {"claude:x": "requested"}}, None)),
                "false")
        control("and a unit no layer places takes the session's own surface",
                json.dumps(delivery_evidence.attach_surface(
                    {"unit_id": "u-s", "layer": "guides", "item_ref": "claude:guides/g"},
                    {"selected": {"claude:guides/g": "requested"}}, None).get("surface")),
                '"requested"')
        control("a unit with no surface from the session, the history or the catalogue stays "
                "unplaced, and the judge NAMES that rather than answering unknown silently",
                # Its own row, built here with every field a unit carries: a unit whose layer
                # places nothing and whose session names no surface. `attach_surface` returns it
                # unchanged, and what the judge then says is the point — a named state, not a
                # silent unknown.
                json.dumps((delivery_evidence.delivery(
                    delivery_evidence.attach_surface(unplaced_unit,
                                                     {"basis": "pin", "selected": {}}, None),
                    {"u-u": unplaced_unit},
                    {"basis": "pin", "selected": {}, "injection_at": 1,
                     "release": {"complete": True, "layers": {}, "items": []}}, 10)
                    or {}).get("reasons") or []),
                "surface_unclassified")
        control("the counts say how many pointer facts and unit surfaces were published",
                json.dumps(pointer_counts), '"pointer_facts": 1')
        control("and how many surfaces", json.dumps(pointer_counts), '"unit_surfaces": 1')
        surface_rows, _surface_doc = facts_document(pointer_shared)
        control("a unit the session was not given is judged on the catalogue surface S2 published",
                json.dumps((surface_rows.get(u1) or {}).get("surface")), "guide")
        # A native unit is matched by its LAYER, and attaching a published surface to one moved it
        # onto another ladder entirely; the classifier is asked first, and this row is why.
        native_rows, _native_doc = facts_document(
            {**pointer_shared,
             "unit_surfaces": [{"unit_ref": ref_u1, "surface": "requested", "source": "snapshot"}]},
            current={"units": [{**operative_units[0],
                                "layer": "native_global", "item_ref": "native:global"}]})
        control("a native unit keeps its layer's ladder, whatever surface is published for it",
                json.dumps((native_rows.get(u1) or {}).get("surface")), "native_layer")
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

        # ---- the reference point, against `release_rows` as it is PUBLISHED -----------------------
        #
        # Three defects met here and together made the catalogue absence unreachable (the WP-11b
        # review): `items` was read from a field `release_rows` does not have, `segments` was
        # ignored so every segmented session came out incomplete, and `layers` was derived from
        # `incomplete_reasons`, which names only the layers that are NOT complete.
        held_ref_a, held_ref_b = "i-" + "e" * 24, "i-" + "f" * 24
        rel_doc = {"sessions": [{"session_ref": "p-seg", "segments": [
            {"segment_ref": "rollout-one", "inventory_refs": [held_ref_a],
             "layers": [{"layer": "catalog", "status": "complete", "reasons": [],
                         "source": {"inventory_ref": held_ref_a, "layer": "catalog",
                                    "basis": "pin"}}],
             "complete": True, "incomplete_reasons": []},
            {"segment_ref": "rollout-two", "inventory_refs": [held_ref_b],
             "layers": [{"layer": "catalog", "status": "unknown",
                         "reasons": ["release_history_deferred"], "source": None}],
             "complete": False,
             "incomplete_reasons": [{"layer": "catalog", "status": "unknown",
                                     "reasons": ["release_history_deferred"],
                                     "inventory_ref": None}]}], "unsegmented": None}]}
        inventories = {held_ref_a: {"items": [{"ref": "claude:one", "surface": "always"}]},
                       held_ref_b: {"items": [{"ref": "claude:two", "surface": "always"}]}}
        first = release_of(rel_doc, "p-seg", "rollout-one", lambda ref: inventories.get(ref), {})
        second = release_of(rel_doc, "p-seg", "rollout-two", lambda ref: inventories.get(ref), {})
        control("the reference point is the SEGMENT the decision belongs to",
                json.dumps(first["items"]), "claude:one")
        control("and another segment of the same session answers differently, which is why one "
                "answer per session was wrong",
                json.dumps(second["items"]), "claude:two")
        control("each segment's own completeness is read, not the session's",
                json.dumps({"one": first["complete"], "two": second["complete"]}),
                '{"one": true, "two": false}')
        control("the point it answered on is named, so a reader knows which row set was used",
                first["point"], "segment")
        control("a COMPLETE layer carries its status, which deriving from incomplete_reasons could "
                "not say at all",
                json.dumps(first["layers"]), '"catalog": "complete"')
        control("and an incomplete one carries its own", json.dumps(second["layers"]),
                '"catalog": "unknown"')
        control("a segmented session whose segment this decision names none of is reported "
                "unresolved, not complete and not absent",
                json.dumps(release_of(rel_doc, "p-seg", "rollout-gone",
                                      lambda ref: inventories.get(ref), {})),
                '"segment_unresolved": "rollout-gone"')
        control("an inventory this run cannot open is named rather than folded into an empty item "
                "set, because an empty set is the absence claim",
                json.dumps(release_of(rel_doc, "p-seg", "rollout-one", lambda ref: None, {})),
                f'"items_unresolved": ["{held_ref_a}"]')
        clean("and `items` is not claimed for it",
              release_of(rel_doc, "p-seg", "rollout-one", lambda ref: None, {})["items"])
        # `unsegmented` is for a session NO segment covers, and only then.
        unseg_doc = {"sessions": [{"session_ref": "p-un", "segments": [],
                                   "unsegmented": {"inventory_refs": [held_ref_a],
                                                   "layers": [{"layer": "catalog",
                                                               "status": "complete",
                                                               "reasons": [], "source": None}],
                                                   "complete": True,
                                                   "incomplete_reasons": []}}]}
        control("a session no segment covers is answered from `unsegmented`",
                release_of(unseg_doc, "p-un", None, lambda ref: inventories.get(ref), {})["point"],
                "unsegmented")
        control("and its items come from the inventory that row set references",
                json.dumps(release_of(unseg_doc, "p-un", None,
                                      lambda ref: inventories.get(ref), {})["items"]),
                "claude:one")
        control("the release's item reader is not the SESSION's: one asks what the library held, "
                "the other what the session received",
                json.dumps(sorted(released_items(
                    {"items": [{"ref": "claude:stated"}]}, {}))),
                '["claude:stated"]')
        clean("and the session reader answers nothing for the same inventory, which is correct for "
              "its own question and was the bug for this one",
              sorted(selected_items({"items": [{"ref": "claude:stated"}]}, {})))

        # A unit whose text this run cannot see is answered unknown by name rather than judged on a
        # placeholder: the comparison would fail for every line and claim a miss from nothing read.
        redacted = {"units": [{**unit, "text": REDACTED} if unit["unit_id"] == u1 else unit
                              for unit in current["units"]]}
        doc_red = document(fixture, checks, candidates, redacted, sessions, release_doc, store,
                           lambda ref: None, ["aa.jsonl"], suite_views)
        control("a redacted unit is not judged on its placeholder",
                json.dumps(([r["reasons"] for r in doc_red["rows"] if r["unit_id"] == u1]
                            or [["NO_ROW_FOR_THE_SUBJECT_UNIT"]])[0]),
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
        reads, unparsed, counts = reads_of(fixture, claude_copy.relative_to(fixture), "claude")
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
        codex_reads, _codex_unparsed, _codex_counts = reads_of(fixture, codex_copy.relative_to(fixture), "codex")
        # Dumped whole rather than indexed: a revert that returns no read would end the suite with an
        # IndexError here and print nothing, which is the control-that-cannot-speak shape this branch
        # has now paid for twice (the ledger migrator's `[0]`, and `evidence["pin_reason"]`).
        control("a Codex shell call is read the same way", json.dumps(codex_reads),
                '"path": "/x/guides/g.md"')
        control("and at the line of its output", json.dumps((codex_reads or [{}])[0]), '"at": 2')

        # ---- Codex's exec_command, and a result that failed or was elided ------------------------
        #
        # `exec_command` carries its command under `cmd` and was absent from SHELL_READERS, so
        # every one of its calls fell through as non-reading — silently, since a call with no
        # `command` simply continued (the WP-11b review). And neither adapter read the result's own
        # text for a failure or an elision: "Process exited with code 1" was counted as the file's
        # delivered bytes, and a truncation warning as the whole file.
        shapes_copy = fixture / SOURCES_DIR / "shapes.jsonl"
        shapes_copy.write_text("\n".join(json.dumps(row) for row in [
            {"type": "response_item", "payload": {
                "type": "function_call", "call_id": "e1", "name": "exec_command",
                "arguments": json.dumps({"cmd": "cat /x/guides/exec.md"})}},
            {"type": "response_item", "payload": {
                "type": "function_call_output", "call_id": "e1",
                "output": "- the text of exec.md"}},
            {"type": "response_item", "payload": {
                "type": "function_call", "call_id": "e2", "name": "shell",
                "arguments": json.dumps({"command": ["cat", "/x/guides/failed.md"]})}},
            {"type": "response_item", "payload": {
                "type": "function_call_output", "call_id": "e2",
                "output": "cat: no such file\nProcess exited with code 1"}},
            {"type": "response_item", "payload": {
                "type": "function_call", "call_id": "e3", "name": "shell",
                "arguments": json.dumps({"command": ["cat", "/x/guides/elided.md"]})}},
            {"type": "response_item", "payload": {
                "type": "function_call_output", "call_id": "e3",
                "output": "- the first line\nWarning: truncated output"}},
            {"type": "response_item", "payload": {
                "type": "function_call", "call_id": "e4", "name": "shell",
                "arguments": json.dumps({"command": ["cat", "/x/guides/ok.md"]})}},
            {"type": "response_item", "payload": {
                "type": "function_call_output", "call_id": "e4",
                "output": "- all of it\nProcess exited with code 0"}},
            {"type": "response_item", "payload": {
                "type": "function_call", "call_id": "e5", "name": "local_shell",
                "arguments": json.dumps({"invocation": {"argv": ["cat", "/x/guides/odd.md"]}})}},
            {"type": "response_item", "payload": {
                "type": "function_call_output", "call_id": "e5", "output": "- something"}},
        ]) + "\n", encoding="utf-8")
        shape_reads, shape_unparsed, shape_counts = reads_of(
            fixture, shapes_copy.relative_to(fixture), "codex")

        def read_paths(held):
            return sorted(row["path"] for row in held if row.get("path"))

        control("an exec_command call carrying its command under `cmd` is a read",
                json.dumps(read_paths(shape_reads)), "/x/guides/exec.md")
        control("a result whose text says the call FAILED is uncertainty, not delivered bytes",
                json.dumps([row for row in shape_unparsed
                            if row.get("path") == "/x/guides/failed.md"]),
                '"reason": "result_failed"')
        control("and the refusal says which exit code it read",
                json.dumps([row for row in shape_unparsed
                            if row.get("path") == "/x/guides/failed.md"]),
                "exit code 1")
        clean("so the failed call contributes no read",
              [row for row in shape_reads if row["path"] == "/x/guides/failed.md"])
        control("a result the host ELIDED is uncertainty too, since the bytes are not the file's",
                json.dumps([row for row in shape_unparsed
                            if row.get("path") == "/x/guides/elided.md"]),
                '"reason": "result_elided"')
        clean("and it contributes no read either",
              [row for row in shape_reads if row["path"] == "/x/guides/elided.md"])
        control("an exit code of ZERO is not a failure, which is what makes the marker a status "
                "rather than a word to look for",
                json.dumps(read_paths(shape_reads)), "/x/guides/ok.md")
        control("a shell call whose argument shape this adapter does not know is kept as named "
                "uncertainty, not discarded as a call nobody made",
                json.dumps([row for row in shape_unparsed
                            if row.get("reason") == "call_shape_unsupported"]),
                "local_shell")
        control("and the counts say how many of each there were",
                json.dumps({key: shape_counts.get(key) for key in
                            ("result_failed", "result_elided", "call_shape_unsupported")}),
                '{"result_failed": 1, "result_elided": 1, "call_shape_unsupported": 1}')
        control("the command argument names are data, so a new shape is one entry",
                json.dumps(list(COMMAND_ARGUMENTS)), '["command", "cmd", "commands"]')
        # What the SHELL_READERS entry itself buys: a call of that tool whose argument shape this
        # adapter does not know is VISIBLE rather than dropped. Without the entry it matches neither
        # branch and falls through, which is how every `exec_command` call disappeared.
        odd_exec = fixture / SOURCES_DIR / "odd-exec.jsonl"
        odd_exec.write_text("\n".join(json.dumps(row) for row in [
            {"type": "response_item", "payload": {
                "type": "function_call", "call_id": "x1", "name": "exec_command",
                "arguments": json.dumps({"shell": {"argv": ["cat", "/x/guides/odd2.md"]}})}},
            {"type": "response_item", "payload": {
                "type": "function_call_output", "call_id": "x1", "output": "- bytes"}},
        ]) + "\n", encoding="utf-8")
        _odd_reads, odd_unparsed, odd_counts = reads_of(fixture, odd_exec.relative_to(fixture),
                                                        "codex")
        control("an exec_command call whose argument shape is unknown is named, which is what "
                "listing the tool buys: without it the call matches no branch and is dropped",
                json.dumps(odd_unparsed), '"reason": "call_shape_unsupported"')
        control("and it says which tool and which arguments, so the next shape is one entry",
                json.dumps(odd_unparsed), "exec_command: ['shell']")
        control("the tools whose calls are read as shell commands are named in one place",
                json.dumps(sorted(SHELL_READERS)),
                json.dumps(sorted(["Bash", "shell", "local_shell", "container.exec",
                                   "exec_command"])))

        # The SAME judgment on the Claude side: a host that writes the failure into the text does
        # not set `is_error`, so the structured check above it does not catch this one.
        cl_defect = fixture / SOURCES_DIR / "cl-defect.jsonl"
        cl_defect.write_text("\n".join(json.dumps(row) for row in [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "d1", "name": "Bash",
                 "input": {"command": "cat /x/guides/cl-failed.md"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "d1",
                 "content": "cat: missing\nProcess exited with code 2"}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "d2", "name": "Read",
                 "input": {"file_path": "/x/guides/cl-elided.md"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "d2",
                 "content": "- the head\n<response clipped>"}]}},
        ]) + "\n", encoding="utf-8")
        cl_reads, cl_unparsed, cl_counts = reads_of(fixture, cl_defect.relative_to(fixture),
                                                    "claude")
        clean("a Claude result that failed in its TEXT rather than in `is_error` admits no read",
              [row for row in cl_reads if "cl-failed" in row["path"]])
        control("and is named as the failure it is",
                json.dumps([row for row in cl_unparsed if "cl-failed" in (row.get("path") or "")]),
                '"reason": "result_failed"')
        clean("an elided Read result admits no read either",
              [row for row in cl_reads if "cl-elided" in row["path"]])
        control("and the one judgment serves both adapters, named in one place",
                next((line.strip() for line in inspect.getsource(_claude_reads).splitlines()
                      if "result_defect(" in line), "<no such line>"),
                "result_defect(returned)")
        control("with the Codex adapter reaching the same function",
                next((line.strip() for line in inspect.getsource(_codex_reads).splitlines()
                      if "result_defect(" in line), "<no such line>"),
                "result_defect(returned)")

        missing = reads_of(fixture, pathlib.PurePosixPath(SOURCES_DIR) / "nope.jsonl", "claude")
        control("a copy the run does not hold is named, not read as an empty session",
                json.dumps(missing[2]), "copy_missing")

        # ---- the label is CONFINED before the filesystem is touched -----------------------------
        #
        # The path was `pathlib.Path(run_dir) / copy`, which discards `run_dir` entirely for an
        # absolute label, follows `..`, and follows a symlink out. S2's manifest is a run artifact
        # and therefore DATA: a row in it could point this stage at any file the owner can read,
        # and it would open it and report its reads (the WP-11b review). The confinement lives in
        # `reads_of` rather than at the call site, because a caller can forget it.
        outside = pathlib.Path(fixture).parent / "outside-the-run.jsonl"
        outside.write_text(json.dumps(
            {"type": "assistant",
             "message": {"content": [{"type": "tool_use", "id": "x1", "name": "Read",
                                      "input": {"file_path": "/x/guides/secret.md"}}]}}) + "\n",
            encoding="utf-8")

        def _linked_label(root, target):
            """A label INSIDE the run whose own path is a symlink pointing at `target`.

            No string test catches this one: the label is relative, holds no `..` and starts with
            no slash. Only resolving it does.
            """
            link = pathlib.Path(root) / SOURCES_DIR / "linked.jsonl"
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(target)
            return str(link.relative_to(root))

        def document_probe_reads(root):
            """Every read of every copy this fixture's manifest names, as the stage would gather it.

            Used to assert that the file outside the run contributed nothing — an assertion about
            the OUTPUT, not only about the refusal, since a refusal that is caught somewhere above
            would still leave the read in the document.
            """
            held = []
            for label in (claude_copy.relative_to(root), codex_copy.relative_to(root)):
                try:
                    held.extend(reads_of(root, label, "claude")[0])
                except Exception:  # noqa: BLE001 - a refusal contributes nothing, which is the point
                    continue
            return held

        def escaped(label):
            try:
                reads_of(fixture, label, "claude")
            except Exception as exc:  # noqa: BLE001 - the refusal IS the answer
                return f"{type(exc).__name__}: {exc}"
            return "<no refusal>"

        control("an ABSOLUTE label is refused rather than read, which is the case `/` silently "
                "allowed by discarding the run",
                escaped(str(outside)), "EVIDENCE_OUTSIDE_RUN")
        control("a traversing label is refused", escaped("../outside-the-run.jsonl"),
                "EVIDENCE_OUTSIDE_RUN")
        control("and a label inside the run that SYMLINKS out, which no string test catches",
                escaped(_linked_label(fixture, outside)), "EVIDENCE_OUTSIDE_RUN")
        clean("the file outside the run was never opened: it still holds exactly what the control "
              "wrote, and no read of it reached any document",
              [] if "secret.md" not in json.dumps(document_probe_reads(fixture))
              else ["a read of the file outside the run reached the document"])
        control("and an ordinary label still works, so the confinement is not refusing everything",
                json.dumps(reads_of(fixture, claude_copy.relative_to(fixture), "claude")[0]),
                '"path": "/x/guides/g.md"')

        # ---- the JSONL splitter, not `str.splitlines()` ------------------------------------------
        #
        # `splitlines()` also splits U+2028, U+2029 and U+0085, so ONE record carrying a separator
        # inside a JSON string became two lines: the record ordinals this stage reports were on a
        # different scale from S2's, and the second half was discarded as unparsable. The same
        # defect as the journal's, in a different file (the WP-11b review).
        sep_copy = fixture / SOURCES_DIR / "sep.jsonl"
        sep_copy.write_text("\n".join([
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "s1", "name": "Read",
                 "input": {"file_path": "/x/guides/sep\u2028ated.md"}}]}}),
            json.dumps({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "s1", "content": "- the text"}]}}),
        ]) + "\n", encoding="utf-8")
        sep_reads, sep_unparsed, sep_counts = reads_of(fixture,
                                                       sep_copy.relative_to(fixture), "claude")
        control("a record carrying a Unicode line separator inside a JSON string is ONE record",
                str(sep_counts.get("records")), "2")
        control("and its read is attributed to the physical line its result arrived on, which is "
                "the ordinal S2 counts in",
                json.dumps((sep_reads or [{}])[0]), '"at": 2')
        clean("and nothing was discarded as unparsable", [row for row in sep_unparsed])
        control("the splitter is the repository's one, reached rather than re-implemented",
                next((line.strip() for line in inspect.getsource(reads_of).splitlines()
                      if "lines = " in line), "<no such line>"),
                "records.jsonl_read(path")

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

        # ---- a copy the manifest NAMES and this run cannot open ----------------------------------
        #
        # `reads_of` returns empty reads plus `copy_missing`, and this installed `reads = []` —
        # "the session read nothing", which is a claim. The judge then reported an exposed guide as
        # NOT READ from evidence nobody acquired (the WP-11b review). The no-entry case was already
        # right, and the two are different answers: one says this run holds no copy, the other that
        # it holds a copy it cannot open.
        gone_views = {"transcripts": [{**views["transcripts"][0],
                                       "source_copy": f"{SOURCES_DIR}/not-written.jsonl"}]}
        gone, gone_counts = session_evidence(session_row, events_by_ref,
                                             units_by_version(unit_index(current)), release_doc,
                                             lambda ref: None, store, fixture,
                                             copies_of(gone_views))
        clean("a copy the manifest names and the run cannot open installs NO reads, so nothing "
              "claims the session read nothing",
              [key for key in gone if key == "reads"])
        control("and the acquisition is carried as unavailable, with its own reason",
                json.dumps(gone.get("read_evidence")),
                '"status": "unavailable"')
        control("named `copy_missing`, which is not the same answer as holding no copy",
                json.dumps(gone.get("read_evidence")), '"reason": "copy_missing"')
        control("the counts distinguish the two", json.dumps(gone_counts), '"copy": "missing"')
        control("while holding no copy at all is `absent`, and says so in the evidence too",
                json.dumps(without.get("read_evidence")), '"reason": "copy_absent"')
        control("and an available copy records that it was read", json.dumps(
            with_reads.get("read_evidence")), '"status": "available"')
        # And the judge's side: the pair is answered unknown with that reason rather than judged.
        gone_doc = document(fixture, checks, candidates, current, sessions, release_doc, store,
                            lambda ref: None, ["aa.jsonl"],
                            {"transcripts": suite_views["transcripts"] + gone_views["transcripts"]})
        control("a pair whose session's records could not be acquired is answered unknown naming "
                "the acquisition, not judged against an empty read set",
                json.dumps([row["reasons"] for row in gone_doc["rows"]
                            if row.get("session") == "claude:t-1"]),
                "copy_missing")
        clean("and no such pair comes out delivered or missed",
              [row["state"] for row in gone_doc["rows"]
               if row.get("session") == "claude:t-1" and row["state"] != "unknown"])

        # The two refusals, each before any write.
        empty = root / "r-empty"
        (empty / SOURCES_DIR).mkdir(parents=True)
        control("a run whose immutable copy holds nothing is refused by name",
                refusal(lambda: run(empty)), "DELIVERY_SOURCES_MISSING")
        clean("and nothing is written for it", sorted(p.name for p in empty.iterdir() if p.is_file()))
        gone = root / "r-nosources"
        gone.mkdir()
        control("so is a run with no copy at all", refusal(lambda: run(gone)), "DELIVERY_SOURCES_MISSING")

        # The EDGES prerequisite, through `run`, before any stage record is published. It used to
        # be checked inside `document`, after `run_stage` had written `status: running` — so a
        # condition knowable from S2's own document left a FAILED attempt behind, and a stage record
        # that says an attempt failed is read as an attempt (the WP-11b review).
        no_edge_run = root / "r-noedges"
        (no_edge_run / SOURCES_DIR).mkdir(parents=True)
        (no_edge_run / SOURCES_DIR / "aa.jsonl").write_text("{}\n", encoding="utf-8")
        (no_edge_run / "inventory").mkdir(parents=True)
        stripped = {"units": [{key: value for key, value in unit.items() if key != "edges"}
                              for unit in current["units"]]}
        records.write_json(no_edge_run, no_edge_run / "inventory" / "current.json", stripped)
        control("a run whose current units carry no `edges` is refused by name",
                refusal(lambda: run(no_edge_run)), "DELIVERY_EDGES_ABSENT")
        clean("and NO stage record was published for it, so the refusal is not read as an attempt",
              sorted(str(held.relative_to(no_edge_run))
                     for held in (no_edge_run / "stages").rglob("*")
                     if held.is_file()) if (no_edge_run / "stages").is_dir() else [])
        clean("and this stage's output is not there either",
              [OUTPUT] if (no_edge_run / OUTPUT).is_file() else [])
        control("the prerequisite is read before the stage is entered, from S2's own document",
                next((line.strip() for line in inspect.getsource(run).splitlines()
                      if "unit_index(" in line), "<no such line>"),
                "unit_index(held_current)")
        clean("and the line that reads it comes BEFORE the one that enters the stage",
              [] if [n for n, line in enumerate(inspect.getsource(run).splitlines())
                     if "unit_index(held_current)" in line][0]
              < [n for n, line in enumerate(inspect.getsource(run).splitlines())
                 if "records.run_stage(" in line][0]
              else ["the prerequisite is read after the stage is entered"])

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
