#!/usr/bin/env python3
"""S7b review of proposals (WP-12 commit 5): a second reader on each disposition and destination.

The review SHOWS disagreement; it does not resolve it. The owner does, by approving, by naming the
alternative with `수정`, or by rejecting - so this module records the disagreement, holds the
alternative to the same table the proposal was held to, and refuses to let a review stand in for a
decision (`REVIEW_DECIDES`, a verdict written as an approval).

Two things it checks that only code can. A `faithful_merge` of `n/a` is checked against the
proposal's own operations, because a reviewer who did not look at a merge would otherwise pass it by
answering `n/a`. And the `bars` set is checked against the bars the contract text states, because a
bar left out of a review is not a bar that holds.

    stage_review_proposals.py --self-test
"""
import collections
import json
import pathlib
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import packet, placement, records, stage_propose, validate  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
STAGE = "S7b"
SCHEMA_PATH = HERE / "schemas" / "s7b.schema.json"
TEMPLATE = "s7b"
INPUTS = ({"artifact": stage_propose.OUTPUT, "producer_stage": "S7"},
          {"artifact": "checked-candidates.json", "producer_stage": "S5"})
MERGE_TYPES = ("merge",)


def schema_bytes():
    if not SCHEMA_PATH.is_file():
        raise Refused(f"S7B_SCHEMA_ABSENT {SCHEMA_PATH}: a review would be judged by nothing")
    return SCHEMA_PATH.read_bytes()


def packet_for(candidate, proposal_row, units=(), call_id="c1", seat="review"):
    """The S7b packet for one proposal, with the contract text and digest the proposal was judged by."""
    payload = payload_for(candidate, proposal_row, units)
    return packet.build(call_id, STAGE, seat, payload, schema=schema_bytes(), repo=HERE.parent)


def payload_for(candidate, proposal_row, units=()):
    """The packet's payload alone: what a supervised call is handed (`packet_for` builds around it)."""
    return packet.render(TEMPLATE, {
        "candidate": json.dumps(candidate, ensure_ascii=False, indent=1),
        "judgments": json.dumps((proposal_row.get("judgments") or {}), ensure_ascii=False, indent=1),
        "proposal": json.dumps({k: v for k, v in proposal_row.items() if k != "judgments"},
                               ensure_ascii=False, indent=1),
        "units": json.dumps(list(units), ensure_ascii=False, indent=1),
        "placement_contract": f"sha256:{placement.contract_digest()}\n\n{placement.contract_text()}",
        "returns": returns_text(),
    }, template_dir=HERE / "packets")


def returns_text():
    """What the packet asks back, with the bars by name.

    `review_problems` holds a review's `bars` to the contract text's own list in both directions, and
    the list is a parse of that text (`placement.contract_bars`): the bolded lead-ins of two
    sections. A reviewer reading the text cannot know which of its headings and paragraphs that parse
    takes - the first live S7b got five first answers refused for bars named after other paragraphs,
    and lost one review to it. So the packet spells the names it will be held to."""
    names = "; ".join(f"`{bar}`" for bar in placement.contract_bars())
    return ("Return one JSON object in the schema of this call. `bars` holds exactly one entry for each of these, "
            f"its `bar` spelled exactly as here and no other: {names}.")


def merge_targets(proposal):
    return [op.get("target") for op in proposal.get("operations") or []
            if op.get("type") in MERGE_TYPES]


def _schema_review_blocks():
    """The schema's `*_review` object fields — the blocks a review can call not-holding.

    Derived from the schema so the contradiction rule cannot fall behind it; the schema is the
    authority on which blocks exist, and a second list here would be a second authority.
    """
    schema = json.loads(schema_bytes().decode("utf-8"))
    held = schema.get("properties") or {}
    defs = schema.get("$defs") or {}

    def names_holds(shape):
        """Whether this property is an object carrying `holds` — following one `$ref` hop.

        The blocks are `$ref`s to `#/$defs/judgment`, so reading `properties` off the property
        itself found nothing and the rule judged an EMPTY set: every verdict passed and the control
        was green about nothing. That is the shape this repo calls a check that cannot fire.
        """
        shape = shape or {}
        ref = shape.get("$ref") or ""
        if ref.startswith("#/$defs/"):
            shape = defs.get(ref.split("/")[-1]) or {}
        return "holds" in (shape.get("properties") or {})

    return {name for name, shape in held.items()
            if name.endswith("_review") and names_holds(shape)}


def review_problems(review, proposal_row, kind=None, diagnosis=None, legacy_incubating=False):
    """Every problem of one review, by name: its shape, the merge question, the bars, the alternative."""
    # BEFORE the shape check, and that order is the whole point: the schema's additionalProperties
    # already refuses an unknown field, so this rule was unreachable behind it and said nothing. A
    # review that wrote itself a decision deserves to be told why, not that a property was
    # unexpected.
    # The root type first. REVIEW_DECIDES keeps its precedence over the SHAPE, which is the whole
    # reason it comes before the schema — but only for an object: on a scalar the membership test
    # raised TypeError and the stage ended with a traceback instead of one named invalid row (the
    # WP-12 review).
    if not isinstance(review, dict):
        return (_shape_problems(review)
                or [f"REVIEW_NOT_AN_OBJECT {type(review).__name__}: a review is an object"])
    problems = [f"REVIEW_DECIDES {field}: a review shows disagreement and the owner resolves it; it "
                f"does not carry a decision of its own"
                for field in ("approved", "decision", "applied", "confirmed") if field in review]
    if problems:
        return problems
    problems = _shape_problems(review)
    if problems:
        return problems
    # A verdict of `agree` that carries a NEGATIVE finding is a contradiction, and it reached the
    # owner as agreement with nothing to resolve: `disposition_review.holds=false` with
    # `verdict=agree` and no alternative passed, and the document then counted it as agreement
    # (the WP-12 review). The reviewer's own claims are preserved; what is refused is calling the
    # set of them agreement.
    # The schema's own review blocks, derived from it rather than listed here: a block added to the
    # schema would otherwise be a finding this rule cannot see.
    negative = [name for name in sorted(_schema_review_blocks())
                if isinstance(review.get(name), dict) and review[name].get("holds") is False]
    if review.get("verdict") == "agree" and negative:
        problems.append(f"REVIEW_VERDICT_CONTRADICTS {', '.join(sorted(negative))}: a verdict of "
                        f"agree with a finding that does not hold would reach the owner as "
                        f"agreement with nothing to resolve")
    if review.get("verdict") == "agree" and review.get("faithful_merge") == "no":
        problems.append("REVIEW_VERDICT_CONTRADICTS faithful_merge: a verdict of agree with an "
                        "unfaithful merge would reach the owner as agreement")
    proposal = proposal_row.get("proposal") or {}
    merges = merge_targets(proposal)
    # The merge question, against the operations rather than against the answer's own word for them.
    if merges and review["faithful_merge"] == "n/a":
        problems.append(f"MERGE_UNJUDGED {proposal_row.get('candidate_id')}: the proposal holds "
                        f"{len(merges)} merge operation(s) ({', '.join(str(t) for t in merges)}), so "
                        f"the review answers the merge question rather than n/a")
    if not merges and review["faithful_merge"] != "n/a":
        problems.append(f"MERGE_JUDGED_WITHOUT_ONE {proposal_row.get('candidate_id')}: the proposal "
                        f"holds no merge operation, and the review answers "
                        f"{review['faithful_merge']!r}")
    judged = [row["operation_target"] for row in review.get("merge_findings") or []]
    for target in merges:
        if target not in judged:
            problems.append(f"MERGE_FINDING_ABSENT {target}: every merge is judged for meaning and "
                            f"for an obligation neither unit carried")
    for target in judged:
        if target not in merges:
            problems.append(f"MERGE_FINDING_ORPHAN {target}: the proposal holds no such merge")
    # A `yes` that its own findings contradict: the summary may not be kinder than the detail.
    contradicting = [row["operation_target"] for row in review.get("merge_findings") or []
                     if not row["meaning_preserved"] or row["unrelated_obligation"]]
    if review["faithful_merge"] == "yes" and contradicting:
        problems.append(f"MERGE_SUMMARY_CONTRADICTED {', '.join(contradicting)}: the review answers "
                        f"yes while its own findings report a loss of meaning or an obligation "
                        f"introduced")
    # The bars, both ways, against the text's own list.
    stated = set(placement.contract_bars())
    answered = {row["bar"] for row in review["bars"]}
    for bar in sorted(stated - answered):
        problems.append(f"BAR_UNJUDGED {bar!r}: a bar left out of a review is not a bar that holds")
    for bar in sorted(answered - stated):
        problems.append(f"BAR_UNKNOWN {bar!r}: the contract text states no such bar")
    # The alternative, held to the same table as the proposal.
    alternative = review.get("alternative")
    if review["verdict"] == "agree" and alternative is not None:
        problems.append(f"ALTERNATIVE_WITH_AGREEMENT {proposal_row.get('candidate_id')}: an agreeing "
                        f"review carries no alternative, and this one names "
                        f"{alternative.get('disposition')!r}")
    if alternative is not None:
        allowed = placement.allowed_for(kind or proposal_row.get("kind"),
                                        diagnosis or proposal_row.get("diagnosis"),
                                        bool(legacy_incubating or proposal_row.get("legacy_incubating")))
        if alternative["disposition"] not in allowed:
            problems.append(f"ALTERNATIVE_DISALLOWED {alternative['disposition']}: §7.2 allows "
                            f"{', '.join(sorted(allowed)) or 'nothing'} for this pair, so this is not "
                            f"an alternative the owner could take")
        # The alternative IS a proposal - it is what the owner may take instead - so its destination
        # is held to §7.4's layers and to the carrier rules, through the same function S7's own
        # destination goes through. Both are model output that reaches the owner's review page, where
        # a carrier carrying a newline and a decision-shaped line could forge an owner's line; the
        # render escapes, and the producer refuses at the source.
        problems.extend(placement.destination_problems(
            alternative.get("destination"), where="alternative.destination",
            item=f"{proposal_row.get('candidate_id')}: "))
    return problems


_VALIDATOR = []


def validator():
    """The review's validator, through `runlib/validate.py`: the pinned dependency and the lint.

    No fallback, for the reason `stage_propose.validator` states: a validation that falls back to
    the schema's required keys accepts a wrong type, a wrong enum and an extra field, and every
    control over it passes."""
    if not _VALIDATOR:
        _VALIDATOR.append(validate.compile_schema(json.loads(schema_bytes())))
    return _VALIDATOR[0]


def _shape_problems(review):
    """The review against its schema: every violation, by json path."""
    return [f"REVIEW_INVALID {problem}" for problem in
            validate.validate_instance(validator(), review)]


def row_of(review, proposal_row):
    """The `review-s7b.json` row: the plan's shape, plus what the owner needs to resolve it."""
    return {"item_id": proposal_row.get("candidate_id"),
            "verdict": review["verdict"],
            "faithful_merge": review["faithful_merge"],
            "alternative": review.get("alternative"),
            "notes": review["notes"],
            "disposition_holds": review["disposition_review"]["holds"],
            "destination_holds": review["destination_review"]["holds"],
            "bars_failing": sorted(row["bar"] for row in review["bars"] if not row["holds"]),
            "disagreement": review["verdict"] == "disagree",
            "owner_resolves": review["verdict"] == "disagree"}


def document(proposals, reviews, candidates=None, only=None, unasked=None):
    """`review-s7b.json`: one row per proposal, with every unreviewed and returned case named.

    A proposal with no review is NOT carried as agreed. Silence is not a second reader, and a stage
    that filled it in would make the whole call decorative."""
    rows, returned, unreviewed = [], [], []
    by_id = {p["candidate_id"]: p for p in (proposals or {}).get("proposals") or []}
    problems = stage_propose.subset_problems(only, by_id)
    if problems:
        raise Refused("; ".join(problems))
    # The UPSTREAM population, inherited when this call asks for no narrower one. An S7 document
    # that was itself a subset reached here and came out `subset: null` while reviewing only those
    # rows, so the review read as the whole population; and the CLI has no `only` of its own, which
    # is exactly the path a reader would take (the WP-12 review, D-20261112-f46263: a subset names
    # its population and never narrows silently). `inherited` says where the marker came from, so
    # the provenance is not lost in the inheriting.
    upstream = (proposals or {}).get("subset")
    inherited = only is None and upstream is not None
    if inherited:
        # A narrower request would have to be a subset of what S7 recorded: narrowing past the
        # upstream population is how a review of three rows could claim to be a review of thirty.
        only = sorted(upstream)
    elif only is not None and upstream is not None:
        outside = sorted(set(only) - set(upstream))
        if outside:
            raise Refused(f"SUBSET_OUTSIDE_UPSTREAM {', '.join(outside)}: S7's document is itself a "
                          f"subset of {len(upstream)} row(s), so a review cannot ask for a row it "
                          f"does not carry")
    if only is not None:
        by_id = {cid: row for cid, row in by_id.items() if cid in set(only)}
    for cid in sorted(by_id):
        review = (reviews or {}).get(cid)
        if review is None:
            # `unasked` is the live stage's: a proposal no review was asked for is unreviewed for
            # that reason, which is not the same sentence as a call that returned nothing.
            unreviewed.append({"item_id": cid, "why": (unasked or {}).get(
                cid, "S7b returned no review for this proposal")})
            continue
        problems = review_problems(review, by_id[cid])
        if problems:
            returned.append({"item_id": cid, "problems": problems})
            continue
        rows.append(row_of(review, by_id[cid]))
    tally = collections.Counter
    return {"stage": STAGE, "reviews": rows,
            "subset": sorted(only) if only is not None else None,
            "subset_inherited": inherited,
            "upstream_subset": sorted(upstream) if upstream is not None else None,
            "returned": sorted(returned, key=lambda r: r["item_id"]),
            "unreviewed": sorted(unreviewed, key=lambda r: r["item_id"]),
            "contract": {"placement_contract_sha256": placement.contract_digest(),
                         "bars": list(placement.contract_bars()),
                         "schema_sha256": packet.sha256_bytes(schema_bytes())},
            "counts": {"proposals": len(by_id), "reviewed": len(rows), "returned": len(returned),
                       "unreviewed": len(unreviewed),
                       "verdict": dict(tally(r["verdict"] for r in rows)),
                       "disagreements": sum(1 for r in rows if r["disagreement"]),
                       "faithful_merge": dict(tally(r["faithful_merge"] for r in rows))}}


OUTPUT = "review-s7b.json"


def run(run_dir, reviews, only=None):
    """The stage, through the shared mechanism: nothing is written on refusal.

    The path is absolute beneath the run and the file is registered with `stage.output`, for the
    reason `stage_propose.run` states: a bare name is refused by the confinement, and an
    unregistered output leaves the next stage's staleness check nothing to read."""
    run_dir = pathlib.Path(run_dir)
    if only is not None:
        # The same refusal as S7's, named by S7 so there is one sentence for one rule.
        raise Refused(stage_propose.SUBSET_IN_RUN.format(stage=STAGE, n=len(list(only))))
    with records.run_stage(run_dir, STAGE, INPUTS) as stage:
        proposals = records.read_json(run_dir / stage_propose.OUTPUT)
        doc = document(proposals, reviews)
        records.write_json(run_dir, run_dir / OUTPUT, doc)
        stage.output(OUTPUT)
        return stage, doc


# ---- the supervised call (release 1) --------------------------------------------------------------
# One call per proposal a MODEL wrote. A legacy entry the owner's default answered in code
# (D-20261111-e53a01) is not a proposal anybody argued for, so there is nothing for a second reader
# to disagree with: it is named unreviewed with that reason, which S9 accounts for, and no call is
# spent on it. Everything else is the dispatcher's, as in S7.
SEAT_KEY = "S7b"
CASE = "review"
OUTPUT_CAP = 20_000
LIVE_INPUTS = INPUTS + ({"artifact": "checks.json", "producer_stage": "S5"},
                        {"artifact": "inventory/current.json", "producer_stage": "S2"})
CALLS = "review-proposals/calls.json"
DRY_RECORD = "review-proposals/dry.json"
UNASKED_DEFAULT = "the owner's legacy default answered it in code, so there is no proposal of a model's to review"


def item_of(candidate_id):
    """A proposal's item name in its call: opaque, since a call directory's name must not be the id."""
    import hashlib
    return "b" + hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:12]


def asked_of(proposals):
    """`(asked ids, {unasked id: why})` over S7's proposals: a model's proposal is reviewed, a
    defaulted one is not."""
    asked, unasked = [], {}
    for row in (proposals or {}).get("proposals") or []:
        if row.get("answered_by") == "default":
            unasked[row["candidate_id"]] = UNASKED_DEFAULT
        else:
            asked.append(row["candidate_id"])
    return sorted(asked), unasked


def live_check(proposal_row, capacity):
    """The stage's check of a review call's attempts (`Supervisor.item(stage_check=)`): the review
    contract's own refusals, so the one retry is told what `document` would return the row for."""
    from runlib import stage_read

    def judged(call_dir):
        held = ((records.read_json(pathlib.Path(call_dir) / "call.json").get("bound")) or {}).get("context_capacity")
        if held != capacity:
            raise Refused(f"CAPACITY_UNRECORDED {pathlib.Path(call_dir).name}: its call record "
                          f"carries the capacity {held!r}, and S7b was admitted against {capacity!r}")
        return review_problems(stage_read.answer_of(call_dir), proposal_row)
    return judged


def supervisor(run_dir, cells, plan=None, seats_path=None):
    """The supervisor S7b's calls go through, their cells under `cells` (made mode 700). Live, the
    pinned runner of the seat run.json names. With `plan`, a golden host's plan (`[{match, answer}]`,
    dispatch.FAKE_HOST's): the host answers from the plan and starts no model."""
    from runlib import dispatch
    cells = pathlib.Path(cells)
    cells.mkdir(mode=0o700, parents=True, exist_ok=True)
    if plan is None:
        return dispatch.Supervisor(run_dir, cell_root=cells, realization="live", seats_path=seats_path)
    # The golden host is S6's: its seat here is a Codex one, and that host is the one that answers
    # a Codex call from a plan (dispatch's own golden host replays a Codex stream and reads no plan).
    from runlib import stage_judge
    return stage_judge.supervisor(run_dir, cells, plan, seats_path)


def live(run_dir, supervisor=None, *, dry=False, seats_path=None, tranche="calibration"):
    """S7b with its supervised calls: `review-s7b.json` over the reviews the calls returned.

    Dry, it writes `review-proposals/dry.json` (who would be asked, each packet's measure) and
    leaves the record `partial`. Otherwise each asked proposal is one item through `supervisor`; an
    accepted review enters `document`, a call that ends other than accepted leaves its proposal
    unreviewed by name and the record `partial`, and a re-run reuses every accepted attempt.
    `review-proposals/calls.json` says what each call did: counts and codes, never a review's text."""
    from runlib import bound, dispatch, gate, stage_judge
    if not dry and supervisor is None:
        raise Refused("REVIEW_UNSUPERVISED S7b: a review call goes through a supervisor; without one, "
                      "run it dry (--dry) or over reviews in hand (--reviews)")
    run_dir = pathlib.Path(run_dir)
    run_id = run_dir.resolve().name
    with records.run_stage(run_dir, STAGE, LIVE_INPUTS) as stage:
        declaration = stage.declaration
        seat = ((declaration or {}).get("seats") or {}).get(SEAT_KEY)
        if not seat:
            raise Refused(f"SEAT_UNDECLARED {SEAT_KEY}: S7b's seat is named by run.json's seats")
        interrupted = [] if dry else supervisor.interrupted(STAGE)
        proposals = records.read_json(run_dir / stage_propose.OUTPUT)
        population = {r["candidate_id"]: r for r in
                      records.read_json(run_dir / "checked-candidates.json")["candidates"]}
        checks = {r["candidate_id"]: r for r in records.read_json(run_dir / "checks.json")["candidates"]}
        current = {u["unit_id"]: u for u in records.read_json(run_dir / "inventory" / "current.json")["units"]}
        by_id = {p["candidate_id"]: p for p in proposals.get("proposals") or []}
        asked, unasked = asked_of(proposals)
        held_schema = json.loads(schema_bytes().decode("utf-8"))
        limits = stage_judge.limits_of(seat, run_dir, declaration,
                                       seats_path if dry else supervisor.seats_path,
                                       case=CASE, output_cap=OUTPUT_CAP, stage=STAGE)
        packets, measured = {}, []
        for cid in asked:
            text = payload_for(population.get(cid) or {"candidate_id": cid}, by_id[cid],
                               stage_propose.unit_rows(checks.get(cid), current, None))
            item = item_of(cid)
            built = packet.build(f"{run_id}-{STAGE}-{item}-a1", STAGE, seat, text, schema_bytes())
            size = bound.driver_bytes(built, schema_bytes())[0]
            packets[cid] = (item, text)
            measured.append({"candidate_id": cid, "item": item,
                             "payload_bytes": len(text.encode("utf-8")),
                             "payload_sha256": packet.sha256_bytes(text.encode("utf-8")),
                             "driver_bytes": size,
                             "input_at_most": stage_judge.at_most_of(size, limits),
                             "over_capacity": bool(stage_judge.beyond_capacity(size, limits))})
        summary = {"stage": STAGE, "declaration_seq": declaration["declaration_seq"], "dry": dry,
                   "seat": seat, "limits": limits, "output_cap": OUTPUT_CAP,
                   "population": {"proposals": len(by_id), "asked": len(asked), "unasked": len(unasked),
                                  "unasked_by_reason": dict(sorted(collections.Counter(unasked.values()).items()))},
                   "packets": measured,
                   "budget": {"per_stage": ((declaration.get("budget") or {}).get("per_stage") or {}).get(STAGE)}}
        if dry:
            records.write_json(run_dir, run_dir / DRY_RECORD, summary)
            stage.output(DRY_RECORD)
            stage.record["status"] = "partial"
            return summary, None
        over = [m["candidate_id"] for m in measured if m["over_capacity"]]
        if over:
            raise Refused(f"REVIEW_OVER_CAPACITY S7b: {len(over)} packets exceed the seat's capacity "
                          f"{limits['capacity']} with the output cap and a retry's correction ({over[:3]})")
        episode = declaration["budget"]["per_episode"]
        caps = {"tokens": episode["tokens"], "compactions": episode["compactions"]}
        reviews, calls = {}, []
        for row in measured:
            cid = row["candidate_id"]
            item, text = packets[cid]
            out = supervisor.item(
                STAGE, item, seat, text, held_schema, case_type=CASE, caps=caps, view_window=False,
                tranche=tranche, max_output_tokens=OUTPUT_CAP, resume=True,
                context_capacity=limits["capacity"],
                stage_check=live_check(by_id[cid], limits["capacity"]),
                packet_check=lambda built: stage_judge.attempt_problems(
                    built, limits, schema_bytes(), SEAT_KEY, code="REVIEW_OVER_CAPACITY"))
            held = {"candidate_id": cid, "item": item, **stage_judge.call_row(out)}
            if out["outcome"] == "accepted":
                call_dir = pathlib.Path(out["accepted"])
                held["call_id"] = records.read_json(call_dir / "call.json")["call_id"]
                reviews[cid] = gate.accepted(call_dir, judged=True)
            else:
                unasked[cid] = (f"S7b's call ended {out['outcome']}"
                                + (f" ({', '.join(held['codes'])})" if held["codes"] else ""))
            calls.append(held)
        doc = document(proposals, reviews, unasked=unasked)
        records.write_json(run_dir, run_dir / OUTPUT, doc)
        stage.output(OUTPUT)
        outcomes = [c["outcome"] for c in calls]
        summary.update(calls=calls, interrupted=interrupted, tranche=tranche,
                       counts={**{o: outcomes.count(o) for o in sorted(set(outcomes))},
                               "reused": sum(1 for c in calls if c.get("reused"))},
                       document=doc["counts"], density_table=dispatch.measured_table(run_dir))
        records.write_json(run_dir, run_dir / CALLS, summary)
        stage.output(CALLS)
        if any(o != "accepted" for o in outcomes):
            stage.record["status"] = "partial"
        return summary, doc


def live_report_lines(summary):
    """What the driver prints of a live or dry S7b: counts, sizes and codes, never a review's text."""
    pop = summary["population"]
    lines = [f"S7b review-proposals{' (dry)' if summary['dry'] else ''}: declaration_seq "
             f"{summary['declaration_seq']}; {pop['asked']} of {pop['proposals']} proposals asked; not asked: "
             f"{'; '.join(f'{n} ({why})' for why, n in pop['unasked_by_reason'].items()) or 'none'}",
             f"packets: {sum(m['payload_bytes'] for m in summary['packets'])} payload bytes over "
             f"{len(summary['packets'])} calls on {summary['seat']}; output at most "
             f"{len(summary['packets']) * summary['output_cap']} tokens at the cap {summary['output_cap']}; "
             f"budget per_stage S7b {summary['budget']['per_stage']}"]
    if not summary["dry"]:
        counts, held = summary["counts"], summary["document"]
        lines.append("calls: " + (", ".join(f"{k} {v}" for k, v in counts.items() if k != "reused") or "none")
                     + f"; {counts['reused']} answered by an earlier accepted attempt")
        failed = sorted({c for row in summary["calls"] if row["outcome"] != "accepted" for c in row["codes"]})
        if failed:
            lines.append(f"codes of the calls not accepted: {', '.join(failed)}")
        lines.append(f"review-s7b.json: {held['reviewed']} reviewed, {held['disagreements']} disagreements, "
                     f"{held['returned']} returned, {held['unreviewed']} unreviewed")
    return lines


# ---- self-test -----------------------------------------------------------------------------------

def self_test():
    """Positive control first, then one planted violation per rule, each named.

    Golden: no model call is made here or by this module. What is judged is the packet S7b would be
    sent and the review it would return.
    The body is wrapped so a control that DIES still speaks: a traceback is not a control firing,
    and a revert trial that reads any output counts one as if it were (the WP-12 review). The
    wrapper prints a [FAIL] line naming the control that was in flight, so the evidence says which
    rule stopped being enforced.
    """
    failures, ran = [], []
    try:
        return _self_test_body(failures, ran)
    except BaseException as exc:  # noqa: BLE001 - the suite must speak before it dies
        held = ran[-1] if ran else "<no control ran>"
        print(f"stage_review_proposals --self-test [FAIL] the suite died after {held!r}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        for name, detail in failures:
            print(f"stage_review_proposals --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"stage_review_proposals --self-test: INCOMPLETE ({len(ran)} controls ran, {len(failures)} failed "
              f"before the suite died)", file=sys.stderr)
        raise


def _self_test_body(failures, ran):
    reporting = []

    def control(name, got, want):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        if not isinstance(got, str):
            raise TypeError(f"CONTROL_GOT_NOT_STR {name}: {type(got).__name__}")
        ran.append(name)
        if want not in got:
            failures.append((name, f"expected {want!r} in {got!r}"))

    def clean(name, problems):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        if not isinstance(problems, list):
            raise TypeError(f"CLEAN_PROBLEMS_NOT_LIST {name}: {type(problems).__name__}")
        ran.append(name)
        if problems:
            failures.append((name, f"expected nothing, got {problems}"))

    def review(**over):
        # Every property the strict provider dialect requires is present, which is now every
        # property: `merge_findings: None` is "this candidate has no merge to review" (what absence
        # used to mean) and each judgment carries its `evidence` list, empty where the review rests
        # on nothing.
        held = {"verdict": "agree",
                "disposition_review": {"holds": True, "reason": "증거가 그 처분을 지지한다",
                                       "evidence": ["c1"]},
                "destination_review": {"holds": True, "reason": "가장 싼 자리다",
                                       "evidence": []},
                "merge_findings": None,
                "faithful_merge": "n/a", "alternative": None,
                "bars": [{"bar": bar, "holds": True, "reason": "충족"} 
                         for bar in placement.contract_bars()],
                "notes": "동의한다"}
        held.update(over)
        # An override that names a judgment without its `evidence` gets the empty list, because the
        # overrides here are about the judgment's VERDICT and every one of them would otherwise have
        # to restate a field it does not care about. The rule itself is not softened: a review that
        # really omits `evidence` is refused by name, which the control below plants.
        for name in ("disposition_review", "destination_review"):
            if isinstance(held.get(name), dict):
                held[name] = {"evidence": [], **held[name]}
        # The same for an alternative an override names: `destination: None` is "this alternative
        # names no destination", which is what its absence meant, and an override about the
        # DISPOSITION should not have to say so.
        if isinstance(held.get("alternative"), dict):
            held["alternative"] = {"destination": None, **held["alternative"]}
        return held

    def row(**over):
        held = {"candidate_id": "k1", "kind": "gap", "diagnosis": "gap", "status": "proposed",
                "legacy_incubating": False,
                "proposal": {"disposition": "place",
                             "operations": [{"type": "create", "target": "claude/guides/g.md"}]}}
        held.update(over)
        return held

    def merging(**over):
        held = row(kind="misfire", diagnosis="redundant")
        held["proposal"] = {"disposition": "reduce",
                            "operations": [{"type": "merge", "target": "claude/guides/g.md#one",
                                            "units": ["u1", "u2"]}]}
        held.update(over)
        return held

    def said(rev, held=None):
        return "; ".join(review_problems(rev, held or row()))

    clean("an agreeing review of a proposal with no merge passes", review_problems(review(), row()))
    control("and its row carries the plan's own fields", json.dumps(sorted(row_of(review(), row()))),
            '"faithful_merge"')

    # The merge question, which only code can hold to the operations.
    merge_ok = review(faithful_merge="yes",
                      merge_findings=[{"operation_target": "claude/guides/g.md#one",
                                       "meaning_preserved": True, "unrelated_obligation": False,
                                       "reason": "두 단위의 뜻이 그대로다"}])
    clean("a merge judged for meaning and for an unrelated obligation passes",
          review_problems(merge_ok, merging()))
    control("a proposal holding a merge whose review answers n/a is returned, naming the operation",
            said(review(), merging()), "MERGE_UNJUDGED")
    only_unjudged = review(merge_findings=[{"operation_target": "claude/guides/g.md#one",
                                            "meaning_preserved": True, "unrelated_obligation": False,
                                            "reason": "뜻이 그대로다"}])
    control("and the refusal names the merge target, so the reviewer knows what was not judged",
            said(only_unjudged, merging()), "claude/guides/g.md#one")
    clean("read from the n/a rule alone: the review carries the finding, so no other rule names that "
          "target here",
          [p for p in review_problems(only_unjudged, merging()) if "MERGE_UNJUDGED" not in p])
    control("a review that answers the merge question where there is no merge is returned too",
            said(review(faithful_merge="yes"), row()), "MERGE_JUDGED_WITHOUT_ONE")
    control("a merge with no finding of its own is named",
            said(review(faithful_merge="yes"), merging()), "MERGE_FINDING_ABSENT")
    control("a finding for a merge the proposal does not hold is named",
            said(review(faithful_merge="yes",
                        merge_findings=[{"operation_target": "claude/guides/other.md#x",
                                         "meaning_preserved": True, "unrelated_obligation": False,
                                         "reason": "r"}]), merging()),
            "MERGE_FINDING_ORPHAN")
    control("a summary of yes over a finding that meaning was lost is refused: the summary may not "
            "be kinder than the detail",
            said(review(faithful_merge="yes",
                        merge_findings=[{"operation_target": "claude/guides/g.md#one",
                                         "meaning_preserved": False, "unrelated_obligation": False,
                                         "reason": "한 단위의 조건이 사라졌다"}]), merging()),
            "MERGE_SUMMARY_CONTRADICTED")
    control("and over a finding that an obligation was introduced, which is that field's failing "
            "direction",
            said(review(faithful_merge="yes",
                        merge_findings=[{"operation_target": "claude/guides/g.md#one",
                                         "meaning_preserved": True, "unrelated_obligation": True,
                                         "reason": "둘 다 없던 의무가 생겼다"}]), merging()),
            "MERGE_SUMMARY_CONTRADICTED")
    clean("while a no that its findings support is a complete review",
          review_problems(review(faithful_merge="no", verdict="disagree",
                                 alternative={"disposition": "none", "reason": "아무 것도 하지 않는다"},
                                 merge_findings=[{"operation_target": "claude/guides/g.md#one",
                                                  "meaning_preserved": False,
                                                  "unrelated_obligation": False, "reason": "뜻이 바뀐다"}]),
                          merging()))

    # The bars, against the contract text's own list.
    control("a bar left out of the review is returned, not read as a pass",
            said(review(bars=[{"bar": bar, "holds": True, "reason": "충족"}
                              for bar in placement.contract_bars()[1:]])),
            "BAR_UNJUDGED")
    control("and the refusal names the bar", 
            said(review(bars=[{"bar": bar, "holds": True, "reason": "충족"}
                              for bar in placement.contract_bars()[1:]])),
            repr(placement.contract_bars()[0]))
    control("a bar the contract text does not state is named",
            said(review(bars=[*({"bar": b, "holds": True, "reason": "r"} for b in placement.contract_bars()),
                              {"bar": "The brevity bar", "holds": True, "reason": "r"}])),
            "BAR_UNKNOWN")
    control("the packet names every bar a review is held to, spelled as the contract check reads it, so a "
            "reviewer need not guess which paragraphs of the text are bars",
            "missing: " + "; ".join(bar for bar in placement.contract_bars() if f"`{bar}`" not in returns_text())
            + " | named: " + str(len(placement.contract_bars())),
            f"missing:  | named: {len(placement.contract_bars())}")
    control("and the payload a call is handed carries that sentence",
            payload_for({"candidate_id": "k"}, {"judgments": {}}), returns_text())
    control("the bars come from the text, so the review's set is the text's set",
            ", ".join(placement.contract_bars()), "Leftward reformulation")
    clean("a failing bar is a complete review, and the row carries which ones failed",
          [] if row_of(review(verdict="disagree",
                              alternative={"disposition": "none", "reason": "r"},
                              bars=[{"bar": bar, "holds": bar != "The gate bar", "reason": "r"}
                                    for bar in placement.contract_bars()]),
                       row())["bars_failing"] == ["The gate bar"] else ["the failing bar is not carried"])

    # The alternative, held to the same table as the proposal.
    clean("a disagreement with an allowed alternative passes",
          review_problems(review(verdict="disagree",
                                 alternative={"disposition": "incubate", "reason": "아직 이르다"}),
                          row()))
    control("an alternative §7.2 does not allow for this pair is not an alternative",
            said(review(verdict="disagree",
                        alternative={"disposition": "correct", "reason": "r"}), row()),
            "ALTERNATIVE_DISALLOWED")
    control("and the refusal says what the pair does allow",
            said(review(verdict="disagree",
                        alternative={"disposition": "correct", "reason": "r"}), row()),
            "§7.2 allows")
    control("an agreeing review that nonetheless names an alternative is returned",
            said(review(alternative={"disposition": "none", "reason": "r"})),
            "ALTERNATIVE_WITH_AGREEMENT")
    clean("a disagreement with NO alternative is allowed: holding that nothing should be done is a "
          "position, written as the disposition none",
          review_problems(review(verdict="disagree", alternative=None), row()))
    clean("the legacy row's own allowances are used for a legacy item's alternative",
          review_problems(review(verdict="disagree",
                                 alternative={"disposition": "drop", "reason": "은퇴시킨다"}),
                          row(kind="unclassified", diagnosis="unknown", legacy_incubating=True)))
    control("while the same alternative on a non-legacy unclassified candidate is refused, so the "
            "legacy row is not quietly applied to everything",
            said(review(verdict="disagree", alternative={"disposition": "drop", "reason": "r"}),
                 row(kind="unclassified", diagnosis="unknown")),
            "ALTERNATIVE_DISALLOWED")

    # A review may not decide.
    for field in ("approved", "decision", "applied", "confirmed"):
        control(f"a review carrying {field!r} is returned: the owner resolves a disagreement",
                said({**review(), field: True}), "REVIEW_DECIDES")
    control("and the schema refuses such a field on its own too, so neither check rests on the other",
            "; ".join(_shape_problems({**review(), "approved": True})), "REVIEW_INVALID")
    control("the verdict vocabulary has two values, so an uncertainty cannot reach the owner as a "
            "shrug", said(review(verdict="unsure")), "REVIEW_INVALID")
    control("a review with no notes is returned: the owner reads them beside the proposal's reasons",
            said({k: v for k, v in review().items() if k != "notes"}), "notes")

    # The packet.
    built = packet_for(row(), row()).decode("utf-8")
    control("the packet carries the contract text S7b judges against", built, "## The bars")
    control("with the same digest the proposal was judged by", built,
            f"sha256:{placement.contract_digest()}")
    control("and the schema the review is held to", built,
            f"SCHEMA: sha256:{packet.sha256_bytes(schema_bytes())}")
    under_review = built.split("<proposal>", 1)[-1].split("</proposal>", 1)[0]
    control("the packet carries the proposal under review", under_review, '"disposition": "place"')
    clean("and that span is the proposal block, not the candidate block that also holds it",
          [] if "<units>" not in under_review else ["the span reaches past the proposal block"])
    control("and says plainly what code has already refused, so the review is asked only about "
            "judgment", built, "they never reached you")

    # The document: a proposal with no review is not carried as agreed.
    proposals = {"proposals": [row(candidate_id="k1"), row(candidate_id="k2"), row(candidate_id="k3")]}
    doc = document(proposals, {"k1": review(), "k2": review(verdict="unsure")})
    control("a proposal with no review is named as unreviewed rather than passed",
            json.dumps(doc["unreviewed"]), "k3")
    control("and the reason says the review is missing, not that it agreed",
            json.dumps(doc["unreviewed"]), "returned no review")
    control("a review that does not hold is returned by name", json.dumps(doc["returned"]), "k2")
    control("and the counts reconcile with the proposals given",
            f"{doc['counts']['proposals']}={doc['counts']['reviewed']}+{doc['counts']['returned']}"
            f"+{doc['counts']['unreviewed']}", "3=1+1+1")
    control("the document binds the contract and lists the bars it judged by",
            json.dumps(doc["contract"]["bars"]), "Leftward reformulation")
    control("disagreements are counted, because that number is what the owner must work through",
            str(document(proposals, {"k1": review(verdict="disagree", alternative=None)})
                ["counts"]["disagreements"]), "1")
    clean("and no row carries a decision of the owner's", 
          [k for r in doc["reviews"] for k in r if k in ("approved", "decision", "applied")])

    # `run` writes inside the run and registers the file. The end-to-end control lives in
    # stage_propose's suite, where the golden run through S6 is built; these two assert the same
    # properties on THIS file's source, so a regression here fails in the file that caused it.
    import ast
    own = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    run_fn = next(node for node in own.body if isinstance(node, ast.FunctionDef) and node.name == "run")
    writes = [ast.unparse(node) for node in ast.walk(run_fn) if isinstance(node, ast.Call)
              and ast.unparse(node.func) == "records.write_json"]
    control("every write of this stage passes a path beneath the run, never a bare name: a bare name "
            "is confined and refused as RUN_PATH_ESCAPE",
            "; ".join(writes), "run_dir / OUTPUT")
    registers = [ast.unparse(node) for node in ast.walk(run_fn) if isinstance(node, ast.Call)
                 and ast.unparse(node.func) == "stage.output"]
    control("and the file is registered with the stage, or its staleness is unreadable by the next "
            "stage", "; ".join(registers) or "<nothing registered>", "stage.output(OUTPUT)")
    clean("one write and one registration, so neither can be left behind by the other",
          [] if len(writes) == len(registers) == 1 else [f"{len(writes)} writes, {len(registers)} registrations"])
    def refused_text(call):
        """The refusal as text, or any other exception as text — the same rule as `refused` below.

        Defined here because the controls above use it: catching `Refused` alone made a control die
        rather than speak when the refusal under test was reverted.
        """
        try:
            call()
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return f"{type(exc).__name__}: {exc}"
        return ""

    # S7b takes the same subset S7 does, and asks S7's question about it rather than its own.
    two = {"proposals": [row(candidate_id="k1"), row(candidate_id="k2")]}
    reviews_two = {cid: review() for cid in ("k1", "k2")}
    one = document(two, reviews_two, only=["k2"])
    control("a subset review answers that subset and says which",
            f'{one["counts"]["proposals"]}:{json.dumps(one["subset"])}', '1:["k2"]')
    control("and a full review says it is not a subset",
            json.dumps(document(two, reviews_two)["subset"]), "null")

    # ---- the upstream population is inherited, not dropped ---------------------------------------
    #
    # S7's document may itself be a subset. Handed one with no `only` of its own, this stage reviewed
    # only the rows it held and reported `subset: null` — a review of one row that read as a review
    # of the population (the WP-12 review). The CLI has no `only` option, so that was the ONLY path
    # a reader would take.
    upstream_doc = {"proposals": [row(candidate_id="k2")], "subset": ["k2"]}
    held_inherited = document(upstream_doc, reviews_two)
    control("an S7 document that is itself a subset is reviewed as that subset, by name",
            json.dumps(held_inherited["subset"]), '["k2"]')
    control("and the document says the marker was inherited rather than asked for, so the "
            "provenance survives",
            json.dumps({"inherited": held_inherited["subset_inherited"],
                        "upstream": held_inherited["upstream_subset"]}),
            '{"inherited": true, "upstream": ["k2"]}')
    control("a review of the whole population still says so, and names no upstream subset",
            json.dumps({"subset": document(two, reviews_two)["subset"],
                        "inherited": document(two, reviews_two)["subset_inherited"],
                        "upstream": document(two, reviews_two)["upstream_subset"]}),
            '{"subset": null, "inherited": false, "upstream": null}')
    control("and a narrower request of its own is NOT recorded as inherited",
            json.dumps({"subset": one["subset"], "inherited": one["subset_inherited"]}),
            '{"subset": ["k2"], "inherited": false}')
    control("asking for a row the upstream subset does not carry is refused by name, since "
            "narrowing past it is how a review of one row could claim thirty",
            refused_text(lambda: document({"proposals": [row(candidate_id="k1"),
                                                         row(candidate_id="k2")],
                                           "subset": ["k2"]},
                                          reviews_two, only=["k1"])),
            "SUBSET_OUTSIDE_UPSTREAM k1")
    clean("while a request inside it is answered",
          [] if document({"proposals": [row(candidate_id="k1"), row(candidate_id="k2")],
                          "subset": ["k1", "k2"]},
                         reviews_two, only=["k2"])["subset"] == ["k2"]
          else ["a request inside the upstream subset was not answered"])

    # ---- a verdict that contradicts its own findings ---------------------------------------------
    #
    # `verdict=agree` with `disposition_review.holds=false` and no alternative passed, and the
    # document then counted it as agreement with `owner_resolves=false`: a negative finding reached
    # the owner marked as agreement with nothing to resolve (the WP-12 review).
    clean("the derived block set is NOT empty, since an empty one would pass every verdict while "
          "the control above stayed green",
          [] if _schema_review_blocks() else ["the schema named no review block"])
    control("the blocks the rule judges come from the schema, not from a list written here",
            json.dumps(sorted(_schema_review_blocks())),
            json.dumps(["destination_review", "disposition_review"]))
    for field in sorted(_schema_review_blocks()):
        held_review = review(verdict="agree", **{field: {"holds": False, "reason": "r"}})
        control(f"a verdict of agree with a {field} that does not hold is refused by name",
                "; ".join(review_problems(held_review, row())),
                f"REVIEW_VERDICT_CONTRADICTS {field}")
    control("and an agree verdict over an unfaithful merge too",
            "; ".join(review_problems(review(verdict="agree", faithful_merge="no"), row())),
            "REVIEW_VERDICT_CONTRADICTS faithful_merge")
    clean("a verdict of agree whose findings all hold is clean, so the rule judges the "
          "contradiction and not the verdict",
          review_problems(review(verdict="agree"), row()))
    clean("and a DISAGREE verdict carrying the same negative finding is clean, which is the shape "
          "the contradiction was hiding behind",
          [problem for problem in review_problems(
              review(verdict="disagree", disposition_review={"holds": False, "reason": "r"},
                     alternative={"disposition": "drop", "reason": "r"}), row())
           if "VERDICT_CONTRADICTS" in problem])

    # ---- the provider's strict dialect: every property required, absence given a name ------------
    #
    # The first live Codex S7b call was refused by the provider with `invalid_json_schema`. The
    # strict subset a provider-hosted structured answer must fit requires EVERY property to be in
    # `required`, so a field whose absence carried a meaning cannot exist: five of this contract's
    # properties were optional, and lane E's projection refused the call before sending rather than
    # letting a nullable stand-in admit a null this schema would then reject.
    #
    # Each of the five was decided on what its absence MEANT, so no reader gains a third case:
    # `merge_findings` is nullable (null = no merge to review, [] = a merge reviewed with nothing
    # found — two different answers), `alternative.destination` is nullable (null = the alternative
    # names no destination), its `carrier` was already nullable and is now required, and both
    # judgments' `evidence` is required outright because [] was already what absence said and is
    # the finding the field exists to make visible.
    held_schema = json.loads(packet.schema_bytes(json.loads(schema_bytes())))
    held_projected, held_strict = packet.provider_schema(held_schema, "codex")
    clean("the contract projects into the provider's strict subset with nothing left over, which "
          "is what lets a Codex seat be sent this call at all", held_strict)
    control("and the projection is produced rather than refused",
            "produced" if held_projected is not None else "refused", "produced")
    control("every property is required, which is the subset's rule and now this contract's shape",
            json.dumps(sorted(set(held_schema["properties"]) - set(held_schema["required"]))), "[]")
    control("a null `merge_findings` reads exactly as its absence did: no merge to review",
            json.dumps(review_problems(review(merge_findings=None), row())), "[]")
    control("while [] is a merge reviewed with nothing found, which is a different answer and is "
            "held to the proposal's own operations",
            "; ".join(review_problems(
                review(faithful_merge="yes", merge_findings=[]),
                row(proposal={"disposition": "reduce",
                              "operations": [{"type": "merge",
                                              "target": "claude/guides/g.md#one"}]}))),
            "MERGE_FINDING_ABSENT claude/guides/g.md#one")
    control("a review that really omits `evidence` is still refused by name, so requiring it is a "
            "rule and not a default the fixture hands out",
            "; ".join(review_problems({**review(),
                                       "disposition_review": {"holds": True, "reason": "r"}},
                                      row())),
            "REVIEW_INVALID disposition_review")
    control("and one that omits the whole `merge_findings` property is refused too, since absence "
            "is no longer a value this contract has",
            "; ".join(review_problems({k: v for k, v in review().items()
                                       if k != "merge_findings"}, row())),
            "REVIEW_INVALID <root>: 'merge_findings' is a required property")
    control("a null alternative destination is the alternative naming none",
            "; ".join(review_problems(
                review(verdict="disagree",
                       disposition_review={"holds": False, "reason": "r"},
                       alternative={"disposition": "none", "reason": "r", "destination": None}),
                row())),
            "")
    control("and an omitted one is refused, so the host must say which it means",
            # Built past the fixture helper on purpose: the helper fills `destination: None` for
            # every override, which is right for a fixture about a disposition and would hide the
            # omission this control is about.
            "; ".join(review_problems(
                {**review(verdict="disagree",
                          disposition_review={"holds": False, "reason": "r"}),
                 "alternative": {"disposition": "drop", "reason": "r"}},
                row())),
            "REVIEW_INVALID alternative: 'destination' is a required property")
    control("the duplicate `alternative` definition is gone: `alternative_or_null` is what the "
            "contract refers to, and two copies of one contract is the defect this unit keeps "
            "finding", json.dumps(sorted(json.loads(schema_bytes())["$defs"])),
            '["alternative_or_null", "bar_judgment", "judgment", "merge_finding", "text"]')

    # ---- a scalar review is a named row, not a traceback -----------------------------------------
    def guarded(call):
        """The call's answer, or the exception as the answer.

        A control that DIES is not a control: with the root-type guard reverted the membership test
        raises TypeError, the suite ended on a traceback, and the revert trial counted it as silent
        rather than as the guard firing. The exception is what the control reads now.
        """
        try:
            return "; ".join(call())
        except BaseException as exc:  # noqa: BLE001 - the exception IS the answer here
            return f"the control died: {type(exc).__name__}: {exc}"

    for held_scalar in (7, "a string", [1, 2], None):
        control(f"a {type(held_scalar).__name__} review is refused by name rather than raising",
                guarded(lambda: review_problems(held_scalar, row()))[:40], "REVIEW_INVALID")
    control("and REVIEW_DECIDES keeps its precedence over the shape for an OBJECT, which is why it "
            "comes first",
            "; ".join(review_problems({"approved": True}, row())), "REVIEW_DECIDES approved")
    def refused(call):
        """The refusal as text, or any other exception as text.

        Catching `Refused` alone made a control die rather than speak: with the refusal reverted the
        call reached `run_stage` over a path that does not exist and raised an OSError straight
        through the suite.
        """
        try:
            call()
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return f"{type(exc).__name__}: {exc}"
        return ""

    control("a proposal this run does not hold is refused by name rather than dropped",
            refused(lambda: document(two, reviews_two, only=["k9"])), "SUBSET_UNKNOWN k9")
    control("and an empty subset is refused", refused(lambda: document(two, reviews_two, only=[])),
            "SUBSET_EMPTY")
    # The alternative is a proposal - what the owner may take instead - so its destination goes
    # through the same function S7's own does. An automated review of lane E's render found this: the
    # alternative's layer and carrier are model output reaching the owner's page, and the render
    # escaping them is not the producer refusing them.
    def alt(**over):
        held = {"disposition": "correct", "reason": "더 싼 자리다",
                "destination": {"layer": "guides", "carrier": "claude/guides/g.md"}}
        held.update(over)
        return held

    disagreeing = review(verdict="disagree", alternative=alt(),
                         disposition_review={"holds": False, "reason": "그 처분이 아니다"})
    misfire = row(kind="misfire", diagnosis="wrong or insufficient")
    clean("an alternative with a §7.4 layer and a relative carrier passes",
          review_problems(disagreeing, misfire))
    control("an alternative whose layer is outside §7.4's order is refused by name",
            said(review(verdict="disagree", alternative=alt(destination={"layer": "everywhere",
                                                                        "carrier": "x"}),
                        disposition_review={"holds": False, "reason": "r"}), misfire),
            "LAYER_UNKNOWN k1: alternative.destination.layer")
    # Two gates, and which one speaks is worth being exact about. The SCHEMA refuses a multi-line
    # carrier first, because the shape check runs before the contract checks - so through
    # `review_problems` that is the message. The CODE rule is what holds where no schema runs: a
    # proposal row read from a `proposals.json` this version did not write, which `review_problems`
    # judges without re-validating. Both are asserted, each where it is the one that answers.
    control("an alternative carrier carrying a newline is refused by the schema first, which is what "
            "a forged owner line would need",
            said(review(verdict="disagree",
                        alternative=alt(destination={"layer": "guides",
                                                     "carrier": "g.md\nowner approved: yes"}),
                        disposition_review={"holds": False, "reason": "r"}), misfire),
            "REVIEW_INVALID alternative/destination/carrier")
    control("and the code rule refuses the same carrier where no schema runs, naming the field",
            "; ".join(placement.destination_problems(
                {"layer": "guides", "carrier": "g.md\nowner approved: yes"},
                where="alternative.destination", item="k1: ")),
            "DESTINATION_CARRIER_CONTROL k1: alternative.destination.carrier")
    control("an alternative carrier climbing out of the tree is refused",
            said(review(verdict="disagree",
                        alternative=alt(destination={"layer": "guides", "carrier": "../../etc/x"}),
                        disposition_review={"holds": False, "reason": "r"}), misfire),
            "DESTINATION_CARRIER_TRAVERSAL k1: alternative.destination")
    control("and an absolute one too",
            said(review(verdict="disagree",
                        alternative=alt(destination={"layer": "guides", "carrier": "/etc/passwd"}),
                        disposition_review={"holds": False, "reason": "r"}), misfire),
            "DESTINATION_CARRIER_ABSOLUTE k1: alternative.destination")

    control("the rules are S7's own function, not a second copy here",
            next(line.strip() for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                 if "destination_problems" in line and "problems.extend" in line),
            "placement.destination_problems")
    clean("an alternative with no destination at all is not a destination problem: whether one is "
          "required is the pair's question",
          [p for p in review_problems(
              review(verdict="disagree", alternative={"disposition": "correct", "reason": "r"},
                     disposition_review={"holds": False, "reason": "r"}), misfire)
           if "DESTINATION" in p or "LAYER_UNKNOWN" in p])

    # The absent run lives UNDER a temporary directory this control owns, and is removed whichever
    # way the call goes. `/nonexistent-run` was the path: with the subset guard reverted,
    # `records.run_stage` reaches `stagelock.hold`, which creates the locks directory before reading
    # the declaration — so a revert trial of this very control tried to write `/nonexistent-run/locks`
    # at the filesystem root. The WP-21 review found it, and this repo has paid for a control writing
    # outside its fixture before.
    with tempfile.TemporaryDirectory(prefix="s7b-absent-") as absent_root:
        absent_run = str(pathlib.Path(absent_root) / "no-such-run")
        control("`run` refuses a subset by name: the stage's output is one file, so a subset run "
                "would replace the whole review with those rows",
                refused(lambda: run(absent_run, reviews_two, only=["k2"])), "SUBSET_IN_RUN S7b")
        clean("and nothing was created for it, not even a lock directory",
              [] if not pathlib.Path(absent_run).exists()
              else [f"{absent_run} exists after a refused call"])
        control("and the refusal is S7's sentence, so one rule has one wording",
                next(line.strip() for line in
                     pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                     if "SUBSET_IN_RUN" in line and "raise" in line),
                "stage_propose.SUBSET_IN_RUN")
        control("the refusal comes before the run directory is touched, so a bad call cannot "
                "half-open a stage",
                refused(lambda: run(absent_run, reviews_two, only=["k2"])), "SUBSET_IN_RUN")

    control("the question is S7's, asked once: this file calls S7's own check",
            next(line.strip() for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                 if "subset_problems" in line and "problems = " in line),
            "problems = stage_propose.subset_problems(only, by_id)")

    control("and S7b's input is S7's output under the name S7 owns, not a second spelling",
            # The SOURCE line, not the value: a literal that happens to equal S7's output today
            # satisfies a value check and drifts the day S7 renames its file.
            next(line for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                 if line.startswith("INPUTS = ")), "stage_propose.OUTPUT")
    clean("and that name resolves to the file S7 really writes",
          [] if INPUTS[0]["artifact"] == stage_propose.OUTPUT else
          [f'{INPUTS[0]["artifact"]!r} is not {stage_propose.OUTPUT!r}'])

    # The wrapper that makes a dying control speak. Asserted from the source, because a suite that
    # ends in a traceback prints no control name at all and a revert trial then reads the traceback
    # as the control firing (the WP-12 review).
    # The WRAPPER's own source, not the file's. A scan of the whole file is satisfied by this
    # control's own text — the phrase it looks for appears in the line that looks for it — which is
    # how a planted mutation passed here before. The wrapper lives in `self_test` and this control
    # lives in `_self_test_body`, so asking `self_test` for its source excludes the control.
    import inspect
    wrapper_text = inspect.getsource(self_test)
    control("a control that dies names itself, since a traceback is not a control firing",
            next((line.strip() for line in wrapper_text.splitlines()
                  if "died after" in line and "print(" in line), "<no such line>"),
            "self-test [FAIL] the suite died after")
    control("and the wrapper is what the entry point runs, so the body cannot be called around it",
            next((line.strip() for line in wrapper_text.splitlines()
                  if "_self_test_body(" in line), "<no such line>"),
            "return _self_test_body(failures, ran)")

    # ---- the supervised call (release 1) ---------------------------------------------------------
    held_asked, held_unasked = asked_of({"proposals": [
        {"candidate_id": "k-model", "answered_by": "model"},
        {"candidate_id": "legacy:defaulted", "answered_by": "default"},
        {"candidate_id": "k-older", "disposition": "place"}]})
    control("a review is asked for a proposal a model wrote, and for one that does not say who wrote it",
            json.dumps(held_asked), json.dumps(["k-model", "k-older"]))
    control("and a legacy entry the owner's default answered is not asked, by name",
            json.dumps(held_unasked), json.dumps({"legacy:defaulted": UNASKED_DEFAULT}))
    import shutil
    live_root = pathlib.Path(tempfile.mkdtemp(prefix="s7b-live-", dir="/tmp"))
    try:
        from runlib import declare
        live_run = None
        try:
            live_run = stage_propose.fx_through_s6(live_root)
            live_cands = records.read_json(live_run / "checked-candidates.json")["candidates"]
            stage_propose.run(live_run, {r["candidate_id"]: stage_propose._answered(
                disposition="none", operations=[], destination={"layer": "incubator", "carrier": None})
                for r in live_cands})
        except Exception as exc:  # the fixture's own failure is reported, never swallowed
            live_run = None
            failures.append(("the golden run through S7 could not be made", repr(exc)))
            ran.append("the golden run through S7 could not be made")
        if live_run is not None:
            proposed = sorted(p["candidate_id"] for p in
                              records.read_json(live_run / stage_propose.OUTPUT)["proposals"])
            clean("the golden run holds more than one proposal to review",
                  [] if len(proposed) > 1 else [f"{proposed}"])
            control("a live run with no supervisor is refused by name",
                    refused_text(lambda: live(live_run)), "REVIEW_UNSUPERVISED S7b")
            declare.amend(live_run, [("budget.per_stage.S7b", 5_000_000)], "S7b's golden budget")
            dry_summary, _none = live(live_run, dry=True)
            control("dry: every proposal is measured, no document is written, and the stage is partial",
                    json.dumps([sorted(m["candidate_id"] for m in dry_summary["packets"]),
                                (live_run / OUTPUT).exists(),
                                records.read_json(records.record_path(live_run, STAGE)).get("status")]),
                    json.dumps([proposed, False, "partial"]))
            # One review decides, which the contract refuses; the others agree.
            deciding = proposed[0]
            plan_path = live_root / "plan.json"
            plan_path.write_text(json.dumps(
                [{"match": [json.dumps(cid)],
                  "answer": {**review(), "decision": "approve"} if cid == deciding else review()}
                 for cid in proposed], ensure_ascii=False), encoding="utf-8")
            live_summary, live_doc = live(live_run, supervisor(live_run, live_root / "cells", plan_path))
            control("each proposal is one supervised call, accepted where the review holds and failed "
                    "where it is refused twice",
                    json.dumps({c["candidate_id"]: c["outcome"] for c in live_summary["calls"]}, sort_keys=True),
                    json.dumps({cid: ("failed" if cid == deciding else "accepted") for cid in proposed},
                               sort_keys=True))
            control("the document reviews the accepted ones and names the failed one unreviewed BY ITS CALL",
                    json.dumps([sorted(r["item_id"] for r in live_doc["reviews"]),
                                [(u["item_id"], u["why"].split(" (")[0]) for u in live_doc["unreviewed"]]]),
                    json.dumps([proposed[1:], [[deciding, "S7b's call ended failed"]]]))
            control("the stage is partial while a call is not accepted, and both files are its outputs",
                    json.dumps([records.read_json(records.record_path(live_run, STAGE)).get("status"),
                                (live_run / CALLS).is_file(), (live_run / OUTPUT).is_file()]),
                    json.dumps(["partial", True, True]))
            again_summary, _doc = live(live_run, supervisor(live_run, live_root / "cells", plan_path))
            control("a re-run reuses every accepted attempt",
                    json.dumps(again_summary["counts"]["reused"]), json.dumps(len(proposed) - 1))
            clean("the report prints counts and codes and no review's text",
                  [line for line in live_report_lines(live_summary) if "동의한다" in line])
    finally:
        shutil.rmtree(live_root, ignore_errors=True)

    reporting.append(True)
    if failures:
        for name, detail in failures:
            print(f"stage_review_proposals --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"stage_review_proposals --self-test: FAILED ({len(failures)} of {len(ran)} controls)",
              file=sys.stderr)
        return 1
    print(f"stage_review_proposals --self-test: OK ({len(ran)} controls: the merge question held to the "
          f"proposal's own operations and to the review's own findings, the bars against the contract "
          f"text's list both ways, the alternative held to §7.2's table including the legacy row, a "
          f"review refused for carrying a decision, and a proposal with no review named rather than "
          f"passed)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit("usage: stage_review_proposals.py --self-test")
