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

Commit 1 of this package lands the stage's frame: its place in `records.STAGES`, its admission through
`records.run_stage` with the two required inputs, its two refusals, and the document's shape. Every pair it enumerates
is `unknown` with the reason `delivery_assembly_pending` and the document says `complete: false`, which the evidence
readers of the following commits replace. A pending answer is written as one rather than left out, so a reader of this
file can tell "no evidence yet" from "evidence that found nothing".

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
          {"artifact": "inventory/current.json", "producer_stage": "S2"})
SOURCES_DIR = "sources"
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


def pairs_of(checks):
    """Every (session, unit, decision) this run owes an answer for, from S5's rows.

    One row per candidate, each naming the session its evidence came from, the units it concerns and the record ordinal
    of the decision. A candidate that names no unit is kept with `unit_id` None: the pair is still owed an answer, and
    dropping it would shrink the denominator silently."""
    owed = []
    for row in checks.get("candidates") or []:
        session = row.get("session_ref") or (row.get("evidence") or {}).get("session_ref")
        decision = row.get("decision_at")
        units = row.get("unit_ids") or ([row["unit_id"]] if row.get("unit_id") else [None])
        for unit in units:
            owed.append({"candidate_id": row.get("candidate_id") or row.get("id"),
                         "session_ref": session, "unit_id": unit, "decision_at": decision})
    return owed


def document(run_dir, checks, sources):
    """The stage's document: one row per owed pair, and the summary a reader counts from."""
    rows = [{**pair, "state": "unknown", "level": None, "reasons": [PENDING], "coverage": None}
            for pair in pairs_of(checks)]
    states = {}
    for row in rows:
        states[row["state"]] = states.get(row["state"], 0) + 1
    return {"stage": STAGE, "complete": False,
            "pending_reason": "the evidence readers land in the commits after this one; every pair is answered "
                              "`unknown` with its reason rather than left out, so a reader can tell a missing "
                              "assembly from an assembly that found nothing",
            "sources": {"count": len(sources), "dir": SOURCES_DIR},
            "rows": rows,
            "summary": {"pairs": len(rows), "states": states,
                        "sessions": len({row["session_ref"] for row in rows if row["session_ref"]}),
                        "units": len({row["unit_id"] for row in rows if row["unit_id"]})}}


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
        doc = document(run_dir, checks, sources)
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
        # The document's shape over rows of S5's own spelling, with no run directory involved: the readers of the
        # commits after this one replace the row bodies, and this control is what tells a reader of the file that a
        # pending answer is written as one.
        checks = {"candidates": [{"candidate_id": "c-1", "session_ref": "claude:s1", "unit_ids": ["u-1", "u-2"],
                                  "decision_at": 7},
                                 {"candidate_id": "c-2", "session_ref": "codex:s2", "decision_at": 3}]}
        doc = document(root, checks, ["aa.jsonl"])
        control("every pair S5 names is owed an answer", str(doc["summary"]["pairs"]), "3")
        control("and a candidate naming no unit keeps its pair", json.dumps(doc["rows"][-1]), '"unit_id": null')
        control("a pending answer is written as an unknown with its reason", json.dumps(doc["rows"][0]), PENDING)
        control("and the document says so of itself", json.dumps({"complete": doc["complete"]}), '"complete": false')
        clean("no row carries bytes or session text",
              [key for row in doc["rows"] for key in row if key in ("returned", "text", "bytes")])

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
    print(f"stage_delivery --self-test: OK ({len(ran)} controls: the stage's place in STAGES, the document's shape "
          f"over S5's rows with every pending pair answered by name, and the two refusals with nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv[1:] else
             print("usage: stage_delivery.py --self-test (the stage runs as `distill.py deliver`)") or 2)
