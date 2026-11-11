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
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import bound, dispatch, records  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
STAGE = "S5b"
OUTPUT = "delivery-evidence.json"
# Admitted against the two producers whose records this stage reads, so the shared staleness judgement applies: a
# `checks.json` or an inventory written again after this stage ran makes the next reader refuse rather than trust it.
INPUTS = ({"artifact": "checks.json", "producer_stage": "S5"},
          {"artifact": "candidates.json", "producer_stage": "S4"},
          {"artifact": "inventory/current.json", "producer_stage": "S2"},
          {"artifact": "inventory/sessions.json", "producer_stage": "S2"},
          {"artifact": "inventory/release.json", "producer_stage": "S2"})
SOURCES_DIR = "sources"
EVENTS_DIR = "events"
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


def document(run_dir, checks, candidates, current, sessions, sources):
    """The stage's document: one row per owed pair, and the summary a reader counts from."""
    units = unit_index(current)
    by_name, by_transcript = sessions_index(sessions)
    decisions = decisions_of(run_dir)
    rows = []
    for pair in pairs_of(checks, candidates, decisions, by_name, by_transcript):
        unit = units.get(pair["unit_id"]) if pair["unit_id"] else None
        reasons = [PENDING]
        if pair.get("reason"):
            reasons = [pair["reason"], PENDING]
        if pair["unit_id"] and unit is None:
            reasons = ["unit_absent_from_inventory", PENDING]
        rows.append({**{k: v for k, v in pair.items() if k != "reason"},
                     "state": "unknown", "level": None, "reasons": reasons,
                     "requirements": len(unit["operative_context"]) if unit else None,
                     "coverage": None})
    states = {}
    for row in rows:
        states[row["state"]] = states.get(row["state"], 0) + 1
    return {"stage": STAGE, "complete": False,
            "pending_reason": "the session evidence readers land in the commit after this one; every pair is "
                              "answered `unknown` with its reason rather than left out, so a reader can tell a "
                              "missing assembly from an assembly that found nothing. This is the per-pair state "
                              "inside a file that exists, not S6's `delivery_assembly_waiting`, which is its "
                              "state when no such file exists at all",
            "sources": {"count": len(sources), "dir": SOURCES_DIR},
            "context_source": "inventory.edges",
            "rows": rows,
            "summary": {"pairs": len(rows), "states": states,
                        "sessions": len({row["session_ref"] for row in rows if row["session_ref"]}),
                        "units": len({row["unit_id"] for row in rows if row["unit_id"]}),
                        "decisions": len({row["decision_at"] for row in rows if row["decision_at"] is not None}),
                        "pairs_without_a_decision": sum(1 for row in rows if row["decision_at"] is None)}}


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
        doc = document(run_dir, checks, candidates, current, sessions, sources)
        records.write_json(run_dir, run_dir / OUTPUT, doc)
        stage.output(OUTPUT)
        declaration_seq = stage.record["declaration_seq"]
    return {**doc["summary"], "complete": doc["complete"], "declaration_seq": declaration_seq}


def report_lines(summary):
    return [f"S5b delivery evidence: {summary['pairs']} pair(s) over {summary['sessions']} session(s) and "
            f"{summary['units']} unit(s); states {summary['states']}",
            f"S5b: complete={summary['complete']} (the evidence readers land in the following commits)"]


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
        doc = document(fixture, checks, candidates, current, sessions, ["aa.jsonl"])
        # k-1: two events x two units (one retrieved, one named-absent) = 4; k-2: one session, no event, no unit = 1.
        control("a pair is owed per decision event and unit", str(doc["summary"]["pairs"]), "5")
        control("an event's ordinal is read from its at_record", json.dumps(doc["rows"][0]), '"decision_at": 76837')
        control("and the session comes from the transcript the event record belongs to",
                json.dumps(doc["rows"][0]), '"session_ref": "p-111111111111111111111111"')
        control("a candidate with no decision event keeps its pair and says why",
                json.dumps(doc["rows"][-1]), "no_decision_event")
        control("and a candidate naming no unit keeps it too", json.dumps(doc["rows"][-1]), '"unit_id": null')
        control("a unit the inventory does not carry is named, not dropped",
                json.dumps([r for r in doc["rows"] if r["unit_id"] == "u-gone"]), "unit_absent_from_inventory")
        control("a pending answer is written as an unknown with its reason", json.dumps(doc["rows"][0]), PENDING)
        control("and the document says so of itself", json.dumps({"complete": doc["complete"]}), '"complete": false')
        control("the pending state is not S6's waiting state", doc["pending_reason"],
                "not S6's `delivery_assembly_waiting`")
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
          f"and the refusal when the inventory publishes none, and the two run refusals with nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv[1:] else
             print("usage: stage_delivery.py --self-test (the stage runs as `distill.py deliver`)") or 2)
