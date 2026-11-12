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
    payload = packet.render(TEMPLATE, {
        "candidate": json.dumps(candidate, ensure_ascii=False, indent=1),
        "judgments": json.dumps((proposal_row.get("judgments") or {}), ensure_ascii=False, indent=1),
        "proposal": json.dumps({k: v for k, v in proposal_row.items() if k != "judgments"},
                               ensure_ascii=False, indent=1),
        "units": json.dumps(list(units), ensure_ascii=False, indent=1),
        "placement_contract": f"sha256:{placement.contract_digest()}\n\n{placement.contract_text()}",
        "returns": "Return one JSON object in the schema of this call.",
    }, template_dir=HERE / "packets")
    return packet.build(call_id, STAGE, seat, payload, schema=schema_bytes(), repo=HERE.parent)


def merge_targets(proposal):
    return [op.get("target") for op in proposal.get("operations") or []
            if op.get("type") in MERGE_TYPES]


def review_problems(review, proposal_row, kind=None, diagnosis=None, legacy_incubating=False):
    """Every problem of one review, by name: its shape, the merge question, the bars, the alternative."""
    # BEFORE the shape check, and that order is the whole point: the schema's additionalProperties
    # already refuses an unknown field, so this rule was unreachable behind it and said nothing. A
    # review that wrote itself a decision deserves to be told why, not that a property was
    # unexpected.
    problems = [f"REVIEW_DECIDES {field}: a review shows disagreement and the owner resolves it; it "
                f"does not carry a decision of its own"
                for field in ("approved", "decision", "applied", "confirmed") if field in review]
    if problems:
        return problems
    problems = _shape_problems(review)
    if problems:
        return problems
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


def document(proposals, reviews, candidates=None, only=None):
    """`review-s7b.json`: one row per proposal, with every unreviewed and returned case named.

    A proposal with no review is NOT carried as agreed. Silence is not a second reader, and a stage
    that filled it in would make the whole call decorative."""
    rows, returned, unreviewed = [], [], []
    by_id = {p["candidate_id"]: p for p in (proposals or {}).get("proposals") or []}
    problems = stage_propose.subset_problems(only, by_id)
    if problems:
        raise Refused("; ".join(problems))
    if only is not None:
        by_id = {cid: row for cid, row in by_id.items() if cid in set(only)}
    for cid in sorted(by_id):
        review = (reviews or {}).get(cid)
        if review is None:
            unreviewed.append({"item_id": cid, "why": "S7b returned no review for this proposal"})
            continue
        problems = review_problems(review, by_id[cid])
        if problems:
            returned.append({"item_id": cid, "problems": problems})
            continue
        rows.append(row_of(review, by_id[cid]))
    tally = collections.Counter
    return {"stage": STAGE, "reviews": rows,
            "subset": sorted(only) if only is not None else None,
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


# ---- self-test -----------------------------------------------------------------------------------

def self_test():
    """Positive control first, then one planted violation per rule, each named.

    Golden: no model call is made here or by this module. What is judged is the packet S7b would be
    sent and the review it would return."""
    failures, ran, reporting = [], [], []

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
        held = {"verdict": "agree",
                "disposition_review": {"holds": True, "reason": "증거가 그 처분을 지지한다",
                                       "evidence": ["c1"]},
                "destination_review": {"holds": True, "reason": "가장 싼 자리다"},
                "faithful_merge": "n/a", "alternative": None,
                "bars": [{"bar": bar, "holds": True, "reason": "충족"} 
                         for bar in placement.contract_bars()],
                "notes": "동의한다"}
        held.update(over)
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
    # S7b takes the same subset S7 does, and asks S7's question about it rather than its own.
    two = {"proposals": [row(candidate_id="k1"), row(candidate_id="k2")]}
    reviews_two = {cid: review() for cid in ("k1", "k2")}
    one = document(two, reviews_two, only=["k2"])
    control("a subset review answers that subset and says which",
            f'{one["counts"]["proposals"]}:{json.dumps(one["subset"])}', '1:["k2"]')
    control("and a full review says it is not a subset",
            json.dumps(document(two, reviews_two)["subset"]), "null")
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

    control("`run` refuses a subset by name: the stage's output is one file, so a subset run would "
            "replace the whole review with those rows",
            refused(lambda: run("/nonexistent-run", reviews_two, only=["k2"])), "SUBSET_IN_RUN S7b")
    control("and the refusal is S7's sentence, so one rule has one wording",
            next(line.strip() for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                 if "SUBSET_IN_RUN" in line and "raise" in line),
            "stage_propose.SUBSET_IN_RUN")
    control("the refusal comes before the run directory is touched, so a bad call cannot half-open "
            "a stage", refused(lambda: run("/nonexistent-run", reviews_two, only=["k2"])),
            "SUBSET_IN_RUN")

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
