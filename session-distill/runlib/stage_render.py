#!/usr/bin/env python3
"""S9 render (plan WP-20 K2; design §9, §7.5, O6; release-1 amendment 2026-11-11T0040): the review's rows.

This part is the ROW MODEL (K2a): what the review shows, as data, before a byte of Markdown. The population is S4's
`population.json`, never `proposals.json`, so an item that vanished before S7 is still a row:

- every population candidate is exactly one row, or one member of a group row;
- every rejected finding of S4 is one row; every item a stage record holds as quarantined is one row;
- every non-finding is one appendix row, counted by reason;
- a candidate S5's checks failed, S6 did not derive, or S7 returned is a row of the failed group, its stage and
  codes named;
- the planted controls S5 mixed in are no rows: `proposals.json` may hold an id outside the population only when
  `controls.json` planted it (PROPOSAL_UNACCOUNTED otherwise).

The legacy intake follows the owner's decision for release 1 (relayed by the lead, 2026-11-11): an incubating legacy
entry defaults to the disposition `none`; one that carries a classification block, or that S7 proposed for, is its
own row; the others are grouped by the first word of their legacy `decision1` (`LEGACY_GROUPS` first, any other word
after, by name), one group row each with its count, its member ids listed. A candidate of another source left out by
the declared sample (`judge.candidate_kinds`) is grouped the same way by source (lead Q2 default). One decision on a
group row applies to every member.

Each row carries every O6 field (`O6_FIELDS`, owned by `schemas/propose.schema.json`'s `reasons`), its §7.5 rank
(`runlib/ranking.py`, which owns the order), the test state S6 named (`untested: s8_deferred`), its `item_sha` (the
whole row, the Korean included, so a regenerated Korean field makes an earlier decision stale) and `payload_sha256`
(its English source: the row without the Korean). A core item admitted by adjudication is `awaiting_R` as S7 says,
never eligible this run (D-20261111-c48e9a).

    stage_render.py --self-test
"""
import collections
import hashlib
import json
import pathlib
import re
import unicodedata
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from grammar import owner_lines  # noqa: E402
from runlib import controls as planted_controls  # noqa: E402
from runlib import derive, ranking, records, stage_adjudicate, stage_propose, stage_review_proposals  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
STAGE = "S9"
PROPOSE_SCHEMA = HERE / "schemas" / "propose.schema.json"
# S9's inputs, by the stage that produces each.
INPUTS = ({"artifact": "census.json", "producer_stage": "S1"},
          {"artifact": "population.json", "producer_stage": "S4"},
          {"artifact": "intake.json", "producer_stage": "S4"},
          {"artifact": "candidates.json", "producer_stage": "S4"},
          {"artifact": "checked-candidates.json", "producer_stage": "S5"},
          {"artifact": "controls.json", "producer_stage": "S5"},
          {"artifact": "checks.json", "producer_stage": "S5"},
          {"artifact": "judgments/judge.json", "producer_stage": "S6"},
          {"artifact": "judgments/derivations.json", "producer_stage": "S6"},
          {"artifact": "judgments/gate-verdicts.json", "producer_stage": "S6"},
          {"artifact": "proposals.json", "producer_stage": "S7"},
          {"artifact": stage_review_proposals.OUTPUT, "producer_stage": "S7b"})
# The ranking keys of a row nothing judged: values inside ranking.py's vocabularies that say "not determined", so a
# rejected finding, a failed item or a group row orders without a key invented for it (lead Q4 default).
UNDETERMINED = {"kind": "unclassified", "diagnosis": "unknown", "consequence": "none", "lineages": 0}
# The statuses of rows that ended before a proposal (lead Q3 default: ranking.json places them in
# quarantined_or_failed; until it does, ranking refuses them by name rather than this module placing them).
FAILED, RETURNED, QUARANTINED = "failed", "returned", "quarantined"
# The owner's three legacy groups. A first word outside them is still its own group (every entry accounted), and the
# header names it, since the owner decided for these three.
LEGACY_GROUPS = ("below-bar-default", "user-approved-default", "incubating")
# A row with no proposal has nothing for S7b to review; a proposal's row carries what S7b recorded for it.
S7B_NONE = {"state": "none", "why": "S7b reviews proposals, and this row carries none"}
# S7b offers at most one alternative per proposal and gives it no id, so the review shows it under this one; the
# owner takes it with `결정: 수정 대안 s7b`, and S10b resolves it from review-s7b.json (lead decision, K2c).
ALTERNATIVE_ID = "s7b"
# S9b's visible mark on a row whose Korean still fails after its one regeneration (design §9): shown, never withheld.
MARK = "번역 검토 실패"
S9B_OUTPUTS = (r"review-s9b\.v(\d+)\.json", r"regenerated-reasons\.v(\d+)\.json")
S7B_ROW_FIELDS = ("verdict", "disposition_holds", "destination_holds", "bars_failing", "faithful_merge",
                  "alternative", "disagreement", "owner_resolves", "notes")
CLASS_ORDER = ("irreversible", "security", "verification-corrupting", "cost", "quality", "none")
JUDGES = ("A", "B")
ROW_KINDS = ("candidate", "legacy", "legacy_group", "left_out_group", "rejected_finding", "stage_item")


def o6_fields():
    """The O6 fields every row carries: `schemas/propose.schema.json`'s `reasons`, which owns them."""
    schema = json.loads(PROPOSE_SCHEMA.read_text(encoding="utf-8"))
    return tuple(schema["$defs"]["reasons"]["required"])


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_of(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def item_of(candidate_id):
    """S6's item name for a candidate (`stage_judge.item_of`), restated in one line to keep S9 off S6's module."""
    return "j" + hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:12]


# ---- the run's documents ------------------------------------------------------------------------------------------

def s9b_reviewed_an_earlier_document(run_dir, rec):
    """Whether S9b read, from a stage before S9, an output that stage has since written again.

    S9's own outputs are not asked: S9 renders again over S9b's review by design, so they differ after every
    overlay and say nothing about what S9b reviewed."""
    held = records.stage_records(run_dir)
    for read in rec.get("inputs") or []:
        producer = read.get("producer_stage")
        if producer in (None, STAGE):
            continue
        now = {o["artifact"]: o["sha256"] for o in (held.get(producer) or {}).get("outputs") or []}
        if read["artifact"] in now and now[read["artifact"]] != read["sha256"]:
            return True
    return False


def s9b_inputs(run_dir):
    """S9b's outputs as S9's inputs when S9b has run (overlay decision (a), K4b): its review and its regenerated
    proposals, each through the shared record checks. A record that is not complete is refused (S9B_UNSETTLED), since
    the review it would overlay is not there to read; a run S9b never reviewed renders as before."""
    rec = records.stage_records(pathlib.Path(run_dir)).get("S9b")
    if rec is None:
        return ()
    if s9b_reviewed_an_earlier_document(pathlib.Path(run_dir), rec):
        # S9b's review is of documents that have since been made again (S7 or S7b was run again). Its overlay is
        # not carried: this render is of what is there now, and S9b then reviews this render. Refusing instead
        # left the run with no next step - S9 refused the stale S9b and S9b refused the stale S9, each asking
        # for the other to be run again (the first live run, after S7 was fixed and run again).
        return ()
    if rec.get("status") != "complete":
        raise Refused(f"S9B_UNSETTLED: S9b's record is {rec.get('status')!r}, so the review it would overlay is not "
                      "there; run S9b to completion before rendering again")
    names = [o["artifact"] for o in rec.get("outputs") or []]
    held = [next((n for n in names if re.fullmatch(pattern, n)), None) for pattern in S9B_OUTPUTS]
    if None in held:
        raise Refused(f"S9B_UNSETTLED: S9b's record names {names}, not one review and one regenerated proposals")
    return tuple({"artifact": n, "producer_stage": "S9b"} for n in held)


def load(run_dir, ledger=None, overlays=()):
    """Every document the rows are made from, read once: `{population, intake, census, controls, checks, judge,
    derivations, proposals, judgments, quarantined, ledger}`. `ledger` is the pinned schema 2 document S4 read
    (`lifecycle_intake.ledger_of`), passed by the caller that names its reference."""
    run_dir = pathlib.Path(run_dir)
    read = lambda rel: records.read_json(run_dir / rel)  # noqa: E731
    docs = {"population": read("population.json"), "intake": read("intake.json"), "census": read("census.json"),
            "controls": read("controls.json"), "checks": read("checks.json"), "judge": read("judgments/judge.json"),
            "derivations": read("judgments/derivations.json"), "proposals": read("proposals.json"),
            "s7b": read(stage_review_proposals.OUTPUT), "ledger": ledger, "judgments": {}, "quarantined": {},
            # what each candidate says, for `subject_of`: the candidates S6 was sent, and S4's rejected findings
            "said": {c["candidate_id"]: c for c in read("checked-candidates.json").get("candidates") or []},
            "findings": {f["finding_id"]: f for f in read("candidates.json").get("rejected_findings") or []}}
    for spec in overlays:
        if spec["producer_stage"] == "S9b":
            key = "s9b_review" if spec["artifact"].startswith("review-s9b.") else "s9b_regenerated"
            docs[key] = read(spec["artifact"])
    # S10's adjudication (K5), laid over S6's derivations, S7's proposals and S7b's review in version order, before
    # anything reads them: every reader below sees one population, recomputed where the owner adjudicated
    adjudicated = stage_adjudicate.read_inputs(run_dir, [s for s in overlays if s["producer_stage"] == "S10"])
    if adjudicated:
        docs["derivations"], docs["proposals"], docs["s7b"], docs["overlay_problems"] = stage_adjudicate.overlay(
            docs["derivations"], docs["proposals"], docs["s7b"], adjudicated)
    for row in docs["judge"].get("calls") or []:
        held = {}
        for who in JUDGES:
            path = run_dir / "judgments" / item_of(row["candidate_id"]) / f"{who}.json"
            held[who] = records.read_json(path) if path.is_file() else None
        docs["judgments"][row["candidate_id"]] = held
    for stage in records.STAGES:
        path = run_dir / "stages" / stage / "record.json"
        if path.is_file():
            entries = records.read_json(path).get("quarantined") or []
            if entries:
                docs["quarantined"][stage] = entries
    return docs


# ---- the parts of a row -------------------------------------------------------------------------------------------

def judges_of(judgments, verdict):
    """Both judges as the row shows them: the requirement marks the derivation used, the consequence class, and the
    unit matches with their reasons; None for a judge with no accepted judgment."""
    out = {}
    marks = (verdict or {}).get("requirements") or {}
    for who in JUDGES:
        doc = (judgments or {}).get(who)
        if doc is None:
            out[who] = None
            continue
        j = doc.get("judgment") or {}
        out[who] = {"seat": doc.get("seat"), "call_id": doc.get("call_id"),
                    "requirements": dict(sorted((marks.get(who) or j.get("requirements") or {}).items())),
                    "consequence_class": j.get("consequence_class"),
                    "reasons": {n: v.get("reason") for n, v in sorted((j.get("requirements") or {}).items())
                                if isinstance(v, dict) and v.get("reason")},
                    # S6 stores each comparison under `unit_id` (`stage_judge.JudgeLabels.resolve`)
                    "units": [{"unit": u.get("unit_id"), "situation": u.get("situation"), "action": u.get("action"),
                               "reason": u.get("reason"), "quote": u.get("quote")} for u in j.get("units") or []],
                    # the rest of what the judge wrote, carried whole so the page's appendix can print it
                    "no_longer_arises": j.get("no_longer_arises"),
                    "matching_units": list(j.get("matching_units") or []),
                    "ledger_relations": list(j.get("ledger_relations") or [])}
    return out


def consequence_of(judges):
    """The row's consequence class when no proposal states one: the judges' class when they agree, else the graver of
    the two, so a disagreement never orders a row below what either judge claimed."""
    held = [CLASS_ORDER.index(derive.DESIGN_CLASS_RENAMES.get(c, c)) for c in
            ((j or {}).get("consequence_class") for j in judges.values()) if c is not None]
    return CLASS_ORDER[min(held)] if held else UNDETERMINED["consequence"]


def disputed_of(verdict):
    """The disputed judgments of a disputed admission, each a numbered label the review's `판정` lines answer: every
    requirement the two judges did not both mark met. The owner's own value is met or unmet."""
    names = derive.table()["requirements"]
    a, b = ((verdict or {}).get("requirements") or {}).get("A") or {}, ((verdict or {}).get("requirements") or {}).get("B") or {}
    rows = [n for n in names if not (a.get(n) == b.get(n) == "met")]
    return [{"label": str(i), "ref": f"requirement/{n}", "A": a.get(n), "B": b.get(n), "values": ["met", "unmet"]}
            for i, n in enumerate(rows, 1)]


def units_of(check_row, delivery):
    """The row's related units, each with the delivery evidence S6 had: release 1 assembles none, and says so."""
    state = (delivery or {}).get("state") or "absent"
    return [{"unit_id": u.get("unit_id") if isinstance(u, dict) else u, "delivery": state}
            for u in (check_row or {}).get("retrieved_units") or []]


SUBJECT_FIELDS = ("lesson", "situation", "action", "exception")


def subject_of(said=None, entry=None, finding=None):
    """What the row is about, in its source's own words: `[{"part", "text"}]`. A formed candidate's lesson, situation,
    action and exception; a cluster's member lessons; a legacy entry's lesson as the pinned ledger holds it; a
    redundancy hint's two units and their similarity; a rejected finding's text and S4's reason. A row with no such
    source (a group, a stage item) has none, and the page then says so by printing no subject line."""
    out = []

    def add(part, text):
        if isinstance(text, str) and text.strip():
            out.append({"part": part, "text": text})
    if finding is not None:
        add("finding", finding.get("finding"))
        add("rejection_reason", finding.get("reason"))
        return out
    said = said or {}
    for name in SUBJECT_FIELDS:
        add(name, said.get(name))
    lifecycle = said.get("lifecycle") or {}
    for lesson in lifecycle.get("lessons") or []:
        add("member_lesson", lesson)
    if entry is not None:
        add("ledger_lesson", entry.get("lesson"))
    if lifecycle.get("target_unit"):
        add("hinted_unit", str(lifecycle["target_unit"]))
    if lifecycle.get("target_units"):
        add("similar_units", f"{', '.join(str(u) for u in lifecycle['target_units'])} "
                             f"(match {lifecycle.get('match')}, similarity {lifecycle.get('similarity')})")
    return out


# ---- the Korean O6 text of rows no proposal speaks for --------------------------------------------------------------

def o6_failed(stage, codes):
    shown = ", ".join(codes) or "(코드 없음)"
    return {"what_happened": f"{stage} 단계가 이 항목을 끝내지 못했습니다: {shown}.",
            "proposal": "제안 없음: 처리가 끝나지 않은 항목입니다.",
            "reason": f"{stage}의 기록이 이 항목을 실패 또는 격리로 남겼습니다.",
            "cost": "없음", "serves": "해당 없음",
            "falsifier": f"{stage}를 다시 실행했을 때 같은 코드 없이 끝나면 이 기록은 틀린 것입니다."}


def o6_rejected_finding(failed):
    shown = ", ".join(failed) or "(이름 없음)"
    return {"what_happened": "S4가 이 발견을 형성 단계에서 거부했습니다.",
            "proposal": "제안 없음: 형성 단계에서 거부된 발견입니다.",
            "reason": f"충족하지 못한 요구 사항: {shown}.",
            "cost": "없음", "serves": "해당 없음",
            "falsifier": f"이 발견이 {shown}을(를) 충족한다는 근거가 있으면 이 거부는 틀린 것입니다."}


def o6_admission(admission, disputed, verdict):
    if admission == "disputed":
        shown = ", ".join(d["ref"].split("/", 1)[1] for d in disputed) or "(요구 사항 아닌 검사)"
        return {"what_happened": f"두 판정자의 판단이 요구 사항 {shown}에서 갈렸습니다.",
                "proposal": "제안 없음: 판정이 필요합니다.",
                "reason": "두 판정자가 함께 충족이라고 한 요구 사항만 승인됩니다.",
                "cost": "없음", "serves": "해당 없음",
                "falsifier": "갈린 요구 사항마다 한쪽 판정이 맞다는 근거가 있으면 판정으로 정리됩니다."}
    marks = (verdict or {}).get("requirements") or {}
    both = [n for n in derive.table()["requirements"]
            if (marks.get("A") or {}).get(n) == (marks.get("B") or {}).get(n) == "unmet"]
    shown = ", ".join(both)
    return {"what_happened": f"두 판정자 모두 요구 사항 {shown}을(를) 충족하지 않는다고 판정했습니다.",
            "proposal": "제안 없음: 승인 요건에서 거부되었습니다.",
            "reason": f"두 판정자가 함께 충족하지 않는다고 한 요구 사항: {shown}.",
            "cost": "없음", "serves": "해당 없음",
            "falsifier": f"{shown}이(가) 충족된다는 근거가 있으면 이 거부는 틀린 것입니다."}


def o6_legacy(members, word):
    what = (f"이전 기록에서 이어진 legacy 항목 {members}개입니다. decision1의 첫 단어는 '{word}'입니다." if word
            else "이전 기록에서 이어진 legacy 항목이고, 분류 블록이 있습니다.")
    return {"what_happened": what,
            "proposal": "제안 없음: 기본 처분은 none(바꾸지 않음)입니다.",
            "reason": "이번 실행에서 판정하지 않은 legacy 항목이며, 소유자 결정으로 기본값을 none으로 둡니다.",
            "cost": "없음", "serves": "해당 없음",
            "falsifier": "구성원 가운데 지금 바꿔야 할 항목이 있으면 그 항목을 따로 결정합니다."}


def o6_left_out(members, source, why):
    return {"what_happened": f"선언된 판정 표본 밖에 남은 {source} 후보 {members}개입니다: {why}.",
            "proposal": "제안 없음: 기본 처분은 none(바꾸지 않음)입니다.",
            "reason": "이번 실행의 표본(judge.candidate_kinds)에 들지 않아 판정하지 않았습니다.",
            "cost": "없음", "serves": "해당 없음",
            "falsifier": "구성원 가운데 지금 바꿔야 할 항목이 있으면 그 항목을 따로 결정합니다."}


# ---- the rows -----------------------------------------------------------------------------------------------------

def _row(item_id, row_kind, status, test_state, o6, **fields):
    held = {"item_id": item_id, "candidate_id": item_id, "row_kind": row_kind, "status": status, **UNDETERMINED,
            "disposition": "none", "changes_library": False, "events": [], "members": [], "test": test_state,
            "s7b": S7B_NONE, "failure": None, "awaiting_R": False, "awaiting_R_reason": None, "proposal": None,
            "guarded_keeps": [], "disputed": [], "judges": None, "units": [], "subject": [], "o6": o6}
    held.update(fields)
    return held


def s7b_states(doc):
    """`({item_id: state}, problems)` from review-s7b.json: reviewed (S7b's row fields), returned (its codes) or
    unreviewed (S7b's reason). An id S7b lists twice is named (S7B_DUPLICATED)."""
    states, problems = {}, []
    entries = ([(r["item_id"], {"state": "reviewed", **{k: r.get(k) for k in S7B_ROW_FIELDS}})
                for r in (doc or {}).get("reviews") or []]
               + [(r["item_id"], {"state": "returned", "codes": [x.split(" ", 1)[0] for x in r.get("problems") or []]})
                  for r in (doc or {}).get("returned") or []]
               + [(r["item_id"], {"state": "unreviewed", "why": r.get("why")})
                  for r in (doc or {}).get("unreviewed") or []])
    for ident, state in entries:
        if ident in states:
            problems.append(f"S7B_DUPLICATED {ident}: S7b lists it as {states[ident]['state']} and as {state['state']}")
            continue
        states[ident] = state
    return states, problems


def s9b_states(doc, proposed, problems):
    """`{item_id: state}` from S9b's review: passed, regenerated and passed, marked, unreviewed or returned. An entry
    for an item S7 did not propose is named (OVERLAY_UNACCOUNTED)."""
    states = {}
    for r in doc.get("rows") or []:
        states[r["item_id"]] = {"state": "marked" if r["mark"] else "regenerated" if r["regenerated"] else "passed",
                                "mark": bool(r["mark"]), "notes": r.get("notes"),
                                "carried_from": r.get("carried_from"),
                                "payload_sha256": r.get("payload_sha256"), "korean_sha256": r.get("korean_sha256")}
    for r in doc.get("unreviewed") or []:
        states[r["item_id"]] = {"state": "unreviewed", "mark": False, "why": r.get("why")}
    for r in doc.get("returned") or []:
        states[r["item_id"]] = {"state": "returned", "mark": False, "codes": list(r.get("codes") or [])}
    problems += [f"OVERLAY_UNACCOUNTED {i}: S9b's review names an item S7 did not propose"
                 for i in sorted(set(states) - set(proposed))]
    return states


def s9b_of_row(states, cid):
    """The row's S9b state when S9b has run (None otherwise, so a run S9b never reviewed renders as before); a proposal
    S9b's version did not hold yet is named as such."""
    if states is None:
        return None
    return states.get(cid) or {"state": "not_yet", "mark": False,
                               "why": "S9b reviewed an earlier version, before this proposal was in it"}


def proposal_row(cid, p, test_state, base, s7b, row_kind="candidate", s9b=None):
    """A row S7 proposed for: its status, its proposal, S7's Korean reasons as the row's O6, and what S7b recorded
    for it. A legacy entry keeps its row kind, since S6 did not judge it and the left-out count holds it as
    unjudged."""
    answer = p["proposal"]
    keep = answer.get("keep_record_named")
    return _row(cid, row_kind, p["status"], test_state, dict(answer["reasons"]),
                **{**base, "s7b": s7b, **({"s9b": s9b} if s9b is not None else {}), "consequence": p["consequence"],
                   "disposition": p["disposition"],
                   "changes_library": p["changes_library"], "proposal": answer,
                   "awaiting_R": p["awaiting_R"], "awaiting_R_reason": p["awaiting_R_reason"],
                   "legacy_incubating": p.get("legacy_incubating", False),
                   "guarded_keeps": [keep] if keep and p["disposition"] == "reduce" else []})


def returned_row(cid, held, test_state, base, row_kind="candidate"):
    """A row S7 returned: a failed row naming S7 and its codes."""
    codes = [x.split(" ", 1)[0] for x in held.get("problems") or []]
    return _row(cid, row_kind, RETURNED, test_state, o6_failed("S7", codes),
                **{**base, "failure": {"stage": "S7", "codes": codes}})


def rows_of(docs):
    """`(rows, appendix, problems)`: every row of the review before ordering, the appendix (non-findings, group
    members), and every accounting problem by name. The rows are not ranked here (`document` ranks them)."""
    pop, deriv, judge, props = docs["population"], docs["derivations"], docs["judge"], docs["proposals"]
    test_state = deriv.get("test")
    verdicts = deriv.get("verdicts") or {}
    not_derived = {r["candidate_id"]: r.get("why") for r in deriv.get("not_derived") or []}
    check_failed = (judge.get("population") or {}).get("check_failed") or {}
    left_out = (judge.get("population") or {}).get("left_out") or {}
    judged = {c["candidate_id"] for c in judge.get("calls") or []}
    proposed = {p["candidate_id"]: p for p in props.get("proposals") or []}
    returned = {r["candidate_id"]: r for r in props.get("returned") or []}
    s7b_of, _counted_in_population_problems = s7b_states(docs.get("s7b"))
    checks = {c["candidate_id"]: c for c in (docs["checks"] or {}).get("candidates") or []}
    intake = {c["candidate_id"]: c for c in (docs["intake"] or {}).get("candidates") or []}
    entries = {e["id"]: e for e in ((docs.get("ledger") or {}).get("entries") or [])}
    said, findings = docs.get("said") or {}, docs.get("findings") or {}
    rows, problems, groups = [], list(docs.get("overlay_problems") or []), collections.OrderedDict()
    # the overlays, in stage order (decision (a)): S9b's regenerated proposals over S7's, each held to S7's own rule
    for ident, answer in sorted(((docs.get("s9b_regenerated") or {}).get("proposals") or {}).items()):
        if ident not in proposed:
            problems.append(f"OVERLAY_UNACCOUNTED {ident}: S9b regenerated a proposal S7 did not make")
            continue
        moved = stage_propose.regenerated_problems(proposed[ident]["proposal"], answer)
        if moved:
            problems.append(f"OVERLAY_INVALID {ident}: {'; '.join(moved)}")
            continue
        proposed[ident] = {**proposed[ident], "proposal": answer}
    s9b_of = s9b_states(docs.get("s9b_review"), proposed, problems) if docs.get("s9b_review") is not None else None
    for cand in pop["candidates"]:
        cid, source = cand["candidate_id"], cand["source"]
        events = list(cand.get("event_ids") or [])
        # the entry a candidate is about, whatever its source: a legacy entry's own, a due decision's target
        target = ((intake.get(cid) or {}).get("target_entry")
                  or ((said.get(cid) or {}).get("lifecycle") or {}).get("target_entry"))
        subject = subject_of(said.get(cid), entries.get(target)) or [
            {"part": "no_source", "text": f"a {source} candidate with no text of its own in checked-candidates.json, "
                                          f"intake.json or the pinned ledger"}]
        if cid in check_failed:
            rows.append(_row(cid, "candidate", FAILED, test_state, o6_failed("S5", check_failed[cid]),
                             source=source, events=events, subject=subject, failure={"stage": "S5", "codes": list(check_failed[cid])}))
            continue
        if cid in not_derived:
            rows.append(_row(cid, "candidate", FAILED, test_state, o6_failed("S6", [str(not_derived[cid])]),
                             source=source, events=events, subject=subject,
                             failure={"stage": "S6", "codes": [str(not_derived[cid])]}))
            continue
        if cid not in judged:
            if source not in left_out:
                problems.append(f"RENDER_INCOMPLETE {cid}: S6 neither judged it, nor failed its checks, nor left its "
                                f"source {source} out")
                continue
            if source == "legacy":
                entry = entries.get((intake.get(cid) or {}).get("target_entry"))
                if entry is None:
                    problems.append(f"RENDER_INCOMPLETE {cid}: a legacy candidate whose entry the pinned ledger does "
                                    "not hold, so it cannot be grouped")
                    continue
                # the grouping key is WP-12's, which S7's legacy split groups by: one owner for the owner's rule
                held = {"source": source, "events": events, "subject": subject,
                        "legacy_word": stage_propose.decision1_kind(entry)}
                if cid in returned:
                    rows.append(returned_row(cid, returned[cid], test_state, held, "legacy"))
                    continue
                # the owner's rule: an entry with a classification block is its own row, and so is one S7 proposed
                # something other than the default for; the rest, S7's `none` default included (WP-12 answers them
                # in code, no call), are one group per first word of decision1
                p = proposed.get(cid)
                if entry.get("classification") is not None or (p and p["disposition"] != "none"):
                    rows.append(proposal_row(cid, p, test_state, held, s7b_of.get(cid), "legacy",
                                             s9b_of_row(s9b_of, cid)) if p else
                                _row(cid, "legacy", None, test_state, o6_legacy(1, None), **held))
                    continue
                groups.setdefault(("legacy", stage_propose.decision1_kind(entry)), []).append(cid)
            else:
                groups.setdefault(("left_out", source), []).append(cid)
            continue
        verdict = verdicts.get(cid)
        if verdict is None:
            problems.append(f"RENDER_INCOMPLETE {cid}: S6 judged it and neither derived it nor named it not derived")
            continue
        outcome = verdict.get("outcome") or {}
        admission = (outcome.get("admission") or {}).get("admission")
        judges = judges_of(docs["judgments"].get(cid), verdict)
        base = {"source": source, "events": events, "subject": subject, "admission": admission, "judges": judges,
                "kind": (outcome.get("kind") or {}).get("kind") or UNDETERMINED["kind"],
                "diagnosis": ((outcome.get("candidate_diagnosis") or {}).get("current") or {}).get("diagnosis")
                             or UNDETERMINED["diagnosis"],
                "lineages": verdict.get("lineages") if isinstance(verdict.get("lineages"), int) else 0,
                "eligible": (outcome.get("eligible") or {}).get("eligible"),
                "units": units_of(checks.get(cid), deriv.get("delivery")),
                "consequence": consequence_of(judges),
                **({"adjudication": verdict["adjudication"]} if verdict.get("adjudication") else {})}
        if admission in ("disputed", "rejected"):
            disputed = disputed_of(verdict) if admission == "disputed" else []
            rows.append(_row(cid, "candidate", admission, test_state, o6_admission(admission, disputed, verdict),
                             disputed=disputed, **base))
            continue
        if cid in proposed:
            rows.append(proposal_row(cid, proposed[cid], test_state, base, s7b_of.get(cid), s9b=s9b_of_row(s9b_of, cid)))
            continue
        if cid in returned:
            rows.append(returned_row(cid, returned[cid], test_state, base))
            continue
        problems.append(f"RENDER_INCOMPLETE {cid}: admitted by S6, and S7 neither proposed for it nor returned it")
    for (family, word), members in groups.items():
        rows.append(_row(f"group:{family}:{word}", f"{family}_group", None, test_state,
                         o6_legacy(len(members), word) if family == "legacy"
                         else o6_left_out(len(members), word, (left_out.get(word) or {}).get("why")),
                         source="legacy" if family == "legacy" else word, members=sorted(members),
                         legacy_word=word if family == "legacy" else None))
    for finding in pop.get("rejected_findings") or []:
        rows.append(_row(finding["finding_id"], "rejected_finding", "rejected", test_state,
                         o6_rejected_finding(finding.get("failed") or []), events=list(finding.get("event_ids") or []),
                         subject=subject_of(finding=findings.get(finding["finding_id"]) or {}),
                         failed_requirements=list(finding.get("failed") or [])))
    for stage, entries_ in sorted(docs.get("quarantined", {}).items(), key=lambda kv: records.STAGES.index(kv[0])):
        for entry in entries_:
            rows.append(_row(f"{stage}:{entry['id']}", "stage_item", QUARANTINED, test_state,
                             o6_failed(stage, [str(entry.get("reason"))]),
                             failure={"stage": stage, "codes": [str(entry.get("reason"))], "because": entry.get("because")}))
    appendix = {"non_findings": [{"event_id": n["event_id"], "reason": n["reason"], "duplicate_of": n.get("duplicate_of")}
                                 for n in pop.get("non_findings") or []],
                "group_members": {r["item_id"]: r["members"] for r in rows if r["members"]}}
    return rows, appendix, problems


# What ranking.py adds to a row (its place, its group, the group's display label): no hash covers them, since other
# rows move them, and a rendered row's hashes are reproduced from the row without them (`keyed`).
RANK_FIELDS = ("rank", "status_group", "status_label")


def english_of(row):
    """The row's English source: the row without its Korean, which is the O6 text; inside S7's answer, its `reasons`
    (the person reads them, so they are Korean: `schemas/propose.schema.json`) and `artifact_set.korean`; and S7b's
    `notes` and its alternative's `reason`, which S7b writes in Korean for the owner (`packets/s7b.md`). S9b's record
    of the row is no part of it either: it judges the Korean against this payload."""
    held = {k: v for k, v in row.items() if k not in ("o6", "s9b", "item_sha", "payload_sha256") + RANK_FIELDS}
    if isinstance(held.get("proposal"), dict):
        answer = {k: v for k, v in held["proposal"].items() if k != "reasons"}
        if isinstance(answer.get("artifact_set"), dict):
            answer["artifact_set"] = {k: v for k, v in answer["artifact_set"].items() if k != "korean"}
        held["proposal"] = answer
    if isinstance(held.get("s7b"), dict):
        s7b = {k: v for k, v in held["s7b"].items() if k != "notes"}
        if isinstance(s7b.get("alternative"), dict):
            s7b["alternative"] = {k: v for k, v in s7b["alternative"].items() if k != "reason"}
        held["s7b"] = s7b
    return held


def korean_sha256_of(proposal):
    """The sha256 of a proposal's Korean reason fields, the text S9b judges (`stage_propose.REASON_FIELDS`). S9b
    binds a verdict to it and S9 holds a verdict to it before showing one (Codex WP-20 r1 F3, r2 F1)."""
    reasons = (proposal or {}).get("reasons") if isinstance(proposal, dict) else None
    return sha256_of({name: (reasons or {}).get(name) for name in stage_propose.REASON_FIELDS})


S9B_UNBOUND = "S9b judged another text of this row: its English or its Korean has changed since"


def s9b_bound(rows):
    """The rows whose S9b verdict was given on another text than the row shows, each such verdict replaced by the
    row's not-yet state (Codex WP-20 r2 F1: a fresh pass on regenerated Korean was shown beside S7's original after
    the next render). A verdict carries the English payload and the Korean it judged; one that carries neither is
    bound to nothing and shown as not yet reviewed."""
    stale = []
    for r in rows:
        held = r.get("s9b")
        if not isinstance(held, dict) or held.get("state") not in ("passed", "regenerated", "marked"):
            continue
        if (held.get("payload_sha256") != sha256_of(english_of(r))
                or held.get("korean_sha256") != korean_sha256_of(r.get("proposal"))):
            r["s9b"] = {"state": "not_yet", "mark": False, "why": S9B_UNBOUND}
            stale.append(r["item_id"])
    return stale


def keyed(row):
    """`(row with its hashes)`: `payload_sha256` over its English source (`english_of`), `item_sha` over all of it, the
    Korean included. Neither covers the rank, which other rows move."""
    english = english_of(row)
    whole = {k: v for k, v in row.items() if k not in ("item_sha", "payload_sha256") + RANK_FIELDS}
    return {**row, "payload_sha256": sha256_of(english), "item_sha": sha256_of(whole)}


# ---- what makes the rows no review --------------------------------------------------------------------------------

def population_problems(rows, appendix, docs):
    """Design §9's one population, each break by name: every candidate, rejected finding, quarantined item and
    non-finding exactly once (RENDER_INCOMPLETE when absent, RENDER_DUPLICATED when twice), and every proposal outside
    the population a planted control (PROPOSAL_UNACCOUNTED)."""
    pop, problems = docs["population"], []
    shown = collections.Counter()
    for r in rows:
        if r["row_kind"] in ("legacy_group", "left_out_group"):
            shown.update(r["members"])
        else:
            shown[r["item_id"]] += 1
    want = [("candidate", c["candidate_id"]) for c in pop["candidates"]]
    want += [("rejected finding", f["finding_id"]) for f in pop.get("rejected_findings") or []]
    want += [(f"{stage} quarantined item", f"{stage}:{e['id']}") for stage, es in (docs.get("quarantined") or {}).items()
             for e in es]
    for what, ident in want:
        if shown[ident] == 0:
            problems.append(f"RENDER_INCOMPLETE {ident}: a {what} of the population with no row")
        elif shown[ident] > 1:
            problems.append(f"RENDER_DUPLICATED {ident}: a {what} shown {shown[ident]} times")
    wanted = {ident for _w, ident in want}
    for ident in sorted(set(shown) - wanted):
        problems.append(f"RENDER_UNACCOUNTED {ident}: a row the population does not hold")
    listed = collections.Counter(n["event_id"] for n in appendix.get("non_findings") or [])
    for n in pop.get("non_findings") or []:
        if listed[n["event_id"]] != 1:
            problems.append(f"RENDER_INCOMPLETE {n['event_id']}: a non-finding listed {listed[n['event_id']]} times in "
                            "the appendix, not once")
    for ident in sorted(set(listed) - {n["event_id"] for n in pop.get("non_findings") or []}):
        problems.append(f"RENDER_UNACCOUNTED {ident}: an appendix row the population's non-findings do not hold")
    planted = {p["candidate_id"] for p in (docs.get("controls") or {}).get("planted") or []}
    population = {c["candidate_id"] for c in pop["candidates"]}
    for ident in sorted({p["candidate_id"] for p in (docs["proposals"].get("proposals") or [])}
                        | {r["candidate_id"] for r in (docs["proposals"].get("returned") or [])}):
        if ident not in population and ident not in planted:
            problems.append(f"PROPOSAL_UNACCOUNTED {ident}: S7 answered for a candidate that is neither in the "
                            "population nor a planted control")
    # S7b answers for exactly S7's proposals: each reviewed, returned or listed unreviewed, once
    s7b_of, s7b_problems = s7b_states(docs.get("s7b"))
    problems += s7b_problems
    proposed_ids = {p["candidate_id"] for p in docs["proposals"].get("proposals") or []}
    for ident in sorted(proposed_ids - set(s7b_of)):
        problems.append(f"RENDER_INCOMPLETE {ident}: S7 proposed for it, and S7b neither reviewed it, returned it nor "
                        "listed it unreviewed")
    for ident in sorted(set(s7b_of) - proposed_ids):
        problems.append(f"S7B_UNACCOUNTED {ident}: S7b answered for an item S7 did not propose")
    return problems


def counts_of(rows, appendix):
    """The review's counts line, from its own rows: what it shows, never what a producer said."""
    candidates = collections.Counter()
    members = 0
    for r in rows:
        if r["row_kind"] in ("legacy_group", "left_out_group"):
            candidates[r["source"]] += len(r["members"])
        elif r["row_kind"] in ("candidate", "legacy"):
            candidates[r["source"]] += 1
            if r["source"] == "formed":
                members += len(r["events"])
    return {"candidates": dict(sorted(candidates.items())),
            "candidate_members": members,
            "rejected_findings": sum(1 for r in rows if r["row_kind"] == "rejected_finding"),
            "rejected_finding_members": sum(len(r["events"]) for r in rows if r["row_kind"] == "rejected_finding"),
            "non_findings": dict(sorted(collections.Counter(n["reason"] for n in appendix["non_findings"]).items())),
            "status": dict(sorted(collections.Counter(str(r["status"]) for r in rows).items())),
            "disposition": dict(sorted(collections.Counter(r["disposition"] for r in rows).items()))}


def counts_problems(counts, docs):
    """The counts line held to S4's and S6's own counts (COUNTS_DIVERGE, by the count): the population's candidates per
    source, its members, its rejected-finding members and its non-findings per reason; and each source S6 left out,
    whose count must be the members the review groups for it."""
    s4 = docs["population"].get("counts") or {}
    problems = []
    for name, have in (("candidates", counts["candidates"]), ("candidate_members", counts["candidate_members"]),
                       ("rejected_finding_members", counts["rejected_finding_members"]),
                       ("non_findings", counts["non_findings"])):
        want = s4.get(name)
        if name == "candidates":
            want = {k: v for k, v in (want or {}).items() if v}
        if have != want:
            problems.append(f"COUNTS_DIVERGE {name}: the review shows {have}, S4 counted {want}")
    return problems


def left_out_problems(rows, docs):
    """Each source S6's sample left out against the members the review shows unjudged for it (COUNTS_DIVERGE)."""
    left = (docs["judge"].get("population") or {}).get("left_out") or {}
    shown = collections.Counter()
    for r in rows:
        if r["row_kind"] in ("legacy_group", "left_out_group"):
            shown[r["source"]] += len(r["members"])
        elif r["row_kind"] == "legacy":
            shown["legacy"] += 1
    return [f"COUNTS_DIVERGE left_out.{source}: S6 left out {left.get(source, {}).get('count', 0)}, the review shows "
            f"{shown[source]} unjudged" for source in sorted(set(left) | set(shown))
            if left.get(source, {}).get("count", 0) != shown[source]]


def row_problems(rows):
    """What makes a row no review row, structurally: an O6 field absent or empty (ROW_FIELD_ABSENT), a row kind this
    module does not make (ROW_KIND_UNKNOWN), no test state (TEST_STATE_ABSENT)."""
    fields, problems = o6_fields(), []
    for r in rows:
        for name in fields:
            value = (r.get("o6") or {}).get(name)
            if not (isinstance(value, str) and value.strip()):
                problems.append(f"ROW_FIELD_ABSENT {r['item_id']}.{name}: every review row carries every O6 field")
        if r.get("row_kind") not in ROW_KINDS:
            problems.append(f"ROW_KIND_UNKNOWN {r['item_id']}: {r.get('row_kind')!r}")
        if not r.get("test"):
            problems.append(f"TEST_STATE_ABSENT {r['item_id']}: the test column is a named state, never a blank")
    return problems


def document(docs):
    """`{rows, appendix, counts, problems, marked}`: the rows in §7.5's order with their hashes, or the problems that
    make them no review. A row ranking cannot place is reported by ranking's own code, never placed by a guess."""
    rows, appendix, problems = rows_of(docs)
    problems += population_problems(rows, appendix, docs)
    counts = counts_of(rows, appendix)
    problems += counts_problems(counts, docs) + left_out_problems(rows, docs) + row_problems(rows)
    if problems:
        return {"rows": [], "appendix": appendix, "counts": counts, "problems": problems}
    unbound = set(s9b_bound(rows))
    keyed_rows = [ordering_view(keyed(r)) for r in rows]
    # ranking's own problems first, as a list: a row it cannot place is reported by its code, and `ranked` is called
    # only over rows it can place, so no refusal of it is caught here
    unplaced = ranking.value_problems(keyed_rows)
    if unplaced:
        return {"rows": [], "appendix": appendix, "counts": counts, "problems": [f"RANK_REFUSED {p}" for p in unplaced]}
    # the items S9b's own review marked, read from its document rather than the rows, so render_text can hold the
    # rendered headings to S9b and not to a state rows_of may have worked out wrong (MARK_MISSING)
    # (a verdict given on another text than the row shows marks nothing it shows: `s9b_bound`)
    marked = sorted(r["item_id"] for r in (docs.get("s9b_review") or {}).get("rows") or []
                    if r.get("mark") and r["item_id"] not in unbound)
    return {"rows": [{k: v for k, v in r.items() if k != ORDER_ONLY} for r in ranking.ranked(keyed_rows)],
            "appendix": appendix, "counts": counts, "problems": [], "marked": marked}


# S7b's part of the order: ranking reads `owner_resolves` off the row it orders (lane L's 5851e09), so S9 hands it
# the S7b record's own value for the ordering and takes it off again. It is no field of the row: the row already
# carries S7b's record, and item_sha leaves rank out, so a reorder alone changes no item's sha.
ORDER_ONLY = "owner_resolves"


def ordering_view(row):
    """The row as ranking orders it: with S7b's `owner_resolves` when S7b reviewed the row, without it (ranking's
    neutral position) when S7b returned it, did not review it, or has no record of it."""
    s7b = row.get("s7b") or {}
    if s7b.get("state") == "reviewed" and isinstance(s7b.get("owner_resolves"), bool):
        return {**row, ORDER_ONLY: s7b["owner_resolves"]}
    return row


# ---- the Markdown (K2b) -------------------------------------------------------------------------------------------
# The review is Korean; identifiers, codes, quotes and the judges' own words stay as written. Every group §9 names has
# its title here, held to ranking.py's table by the self-test, so a group added there cannot render untitled.
GROUP_TITLES = {"proposed_and_tested": "제안 (release 1: 시험 전)", "disputed": "판정이 필요한 항목",
                "confirmed_and_keep": "확인됨과 유지", "already_resolved_and_unclassified": "이미 해결됨과 미분류",
                "rejected": "거부된 항목", "quarantined_or_failed": "격리되거나 실패한 항목"}
STATUS_LABELS = {"proposed": "제안됨 (시험 전)", "tested": "시험됨", "disputed": "판정 필요", "rejected": "거부됨",
                 "returned": "S7이 돌려보냄", "failed": "실패", "quarantined": "격리됨",
                 None: "판정하지 않음 (기본 처분 none)"}
# Each of ranking.py's keys in the owner's words, in the table's order and held to it by the self-test, so the header
# names the order the rows are in. `lineages` is the judges' part of the fallback and `owner_resolves` S7b's (the
# release-1 amendment's WP-20 row: "the §7.5 order falls back to the judges and S7b, and the header names the
# fallback"; ranking key from lane L's 5851e09).
KEY_TITLES = {"status_group": "상태 그룹", "consequence": "결과 등급", "lineages": "판정자들이 인정한 독립 계보 수",
              "owner_resolves": "S7b가 이견을 내고 소유자에게 맡긴 항목 먼저", "kind": "종류", "diagnosis": "진단",
              "change": "변경 여부", "candidate_id": "항목 id"}
FALLBACK = ("순서는 §7.5를 따릅니다. 이번 release에는 시험 결과가 없으므로(S8은 release 2), 시험 결과 대신 판정자와 "
            "S7b에 기댑니다. 판정자 쪽은 두 판정자가 인정한 독립 계보 수이고, S7b 쪽은 S7b가 이견을 내고 소유자에게 "
            "맡긴 항목을 먼저 두는 것입니다. 키 순서: " + ", ".join(KEY_TITLES.values()) + ".")
AWAITING_R = "R 대기: 판정으로 들어온 core 항목이라 이번 실행의 F에 들지 않고, 적용 대상이 아닙니다 (S8은 release 2)."


# What a CommonMark preview reads as markup that hides or replaces the characters written: a raw HTML tag, comment or
# autolink (`<`), a character reference (`&`), and a link, image or footnote (`[`, whose destination and title a
# preview does not show). A backslash before each makes a preview show it as typed; emphasis, strikethrough and code
# spans restyle but hide nothing, and are left as written (lead decisions, 2026-11-12).
MARKUP = "<&["


def inline(text):
    """A field's text on one line, shown by a Markdown preview as typed: every run of whitespace, newlines included,
    one space, so a field never starts a line and nothing a model wrote can stand where an owner-block marker would;
    every backslash doubled first, so a backslash a model wrote cannot undo an escape; then a backslash before every
    character of MARKUP. The only place this is done; deterministic, so an unedited copy's fixed lines still equal the
    render byte for byte. The owner approves the text they read."""
    one = " ".join(str(text).split()).replace("\\", "\\\\")
    for ch in MARKUP:
        one = one.replace(ch, "\\" + ch)
    # last, so a notation's one backslash is never doubled: a backslash and a `u` a model wrote shows as `\\u`
    return visible(one)


# Which characters are written as themselves: an allowlist (lead decisions, 2026-11-12). A letter, number,
# punctuation mark or symbol (categories L*, N*, P*, S*), the plain space, and a combining mark (Mn, Mc) that follows a
# character written as itself. Everything else is written in visible notation: format characters and controls (Cf,
# Cc), a lone surrogate (Cs, which UTF-8 cannot write), unassigned and private-use code points (Cn, Co), every other
# space (Zs but U+0020, Zl, Zp), an enclosing mark (Me), and a mark with no base. BLANK_LOOKALIKES are characters of an
# allowed category that show nothing, or a blank. They are derived, not listed: every Default_Ignorable_Code_Point of an
# allowed category (the Hangul fillers U+115F, U+1160, U+3164, U+FFA0, which ordinary Korean prose written in
# precomposed syllables never holds and which fake a blank name; the combining grapheme joiner; the two invisible Khmer
# inherent vowels; every variation selector), plus the one blank that is not default-ignorable: the braille blank
# U+2800, a symbol that renders as an empty cell.
#
# DEFAULT_IGNORABLE is Unicode's Default_Ignorable_Code_Point as DerivedCoreProperties.txt lists it. Python's
# unicodedata does not carry the property, so its ranges are copied here. Perl's Unicode::UCD (Unicode 13.0.0) lists the
# same ranges but U+180F, which Unicode 14.0.0 added as a variation selector, and every variation selector is
# default-ignorable. The suite holds the copy to the property's own derivation (DI_FORMAT_EXCLUDED): every format
# character but the ones the derivation excludes, and every character the database names a variation selector.
DEFAULT_IGNORABLE = ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
                     (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164),
                     (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
                     (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF))
# The derivation's exclusions from "Cf": Prepended_Concatenation_Mark, the interlinear annotation characters
# FFF9..FFFB and the Egyptian hieroglyph format controls (DerivedCoreProperties.txt, the Default_Ignorable_Code_Point
# header).
DI_FORMAT_EXCLUDED = ((0x0600, 0x0605), (0x06DD, 0x06DD), (0x070F, 0x070F), (0x0890, 0x0891), (0x08E2, 0x08E2),
                      (0xFFF9, 0xFFFB), (0x110BD, 0x110BD), (0x110CD, 0x110CD), (0x13430, 0x1345F))
BRAILLE_BLANK = 0x2800


def _written_category(cp):
    """Whether a code point's category is one the allowlist writes as itself (a mark only after a base)."""
    category = unicodedata.category(chr(cp))
    return category[0] in "LNPS" or category in ("Mn", "Mc")


BLANK_LOOKALIKES = frozenset({cp for lo, hi in DEFAULT_IGNORABLE for cp in range(lo, hi + 1) if _written_category(cp)}
                             | {BRAILLE_BLANK})


def notation(ch):
    """A character's code point in visible notation: `\\uXXXX`, or `\\UXXXXXXXX` beyond the first plane."""
    return f"\\u{ord(ch):04X}" if ord(ch) <= 0xFFFF else f"\\U{ord(ch):08X}"


def unshown(text, keep=""):
    """For each character of `text`, whether it is written in notation rather than as itself (the allowlist above;
    a character in `keep` is written as itself and is no base for a mark)."""
    flags, based = [], False
    for ch in text:
        category = unicodedata.category(ch)
        if ch in keep or ch == " ":
            flags.append(False)
            based = False
        elif ord(ch) not in BLANK_LOOKALIKES and (category[0] in "LNPS" or (category in ("Mn", "Mc") and based)):
            flags.append(False)
            based = True
        else:
            flags.append(True)
            based = False
    return flags


def visible(text, keep=""):
    """`text` with every character the allowlist does not write as itself in its visible notation."""
    return "".join(notation(ch) if hide else ch for ch, hide in zip(text, unshown(text, keep)))


def invisible_in(text, keep=""):
    """The characters of `text` the allowlist does not write as themselves, in order."""
    return [ch for ch, hide in zip(text, unshown(text, keep)) if hide]


def fence_line(line):
    """`(shown, replaced, doubled)` for one line inside a fence: every backslash the line holds is shown doubled, and
    every character the allowlist does not write as itself but a tab is replaced by its notation, whose one backslash is
    the renderer's own; `doubled` counts the line's backslashes. So a notation is always the last of an odd run of
    backslashes and the content's own `\\u....` the end of an even one, whatever the line holds around it: the rule
    `inline` follows outside fences (lead decision 2026-11-12, which replaced doubling only a run before a notation or
    its imitation)."""
    hide = unshown(line, keep="\t")
    out, replaced = [], []
    for i, ch in enumerate(line):
        if hide[i]:
            replaced.append(f"U+{ord(ch):04X}")
            out.append(notation(ch))
        else:
            out.append("\\\\" if ch == "\\" else ch)
    return "".join(out), replaced, line.count("\\")


def live_markup(line):
    """The positions in `line` of a MARKUP character a CommonMark reading takes as markup: one preceded by an even
    number of backslashes, none included."""
    out, run = [], 0
    for i, ch in enumerate(line):
        if ch == "\\":
            run += 1
            continue
        if ch in MARKUP and run % 2 == 0:
            out.append(i)
        run = 0
    return out


LINE_SEPARATORS = ("\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")


def fenced(text):
    """Multi-line text inside a code fence longer than any backtick run it holds, its carriage returns and other line
    separators normalized, every character the allowlist does not write as itself but a tab in visible notation
    (`fence_line`; each named on a line after the fence), and every line shaped like an owner line or an owner-block
    marker (`owner_lines.owner_shaped`) escaped with a leading backslash."""
    body = str(text).replace("\r\n", "\n")
    for separator in LINE_SEPARATORS:   # each a line break to some editor: a real line, so it is escaped as one
        body = body.replace(separator, "\n")
    lines = [fence_line(line) for line in body.split("\n")]
    body = ["\\" + shown if owner_lines.owner_shaped(shown) else shown for shown, _r, _d in lines]
    longest = max((len(run) for line in body for run in re.findall(r"`+", line)), default=0)
    fence = "`" * max(3, longest + 1)
    replaced = [(n, ", ".join(sorted(set(points)))) for n, (_s, points, _d) in enumerate(lines, 1) if points]
    doubled = sum(d for _s, _r, d in lines)
    note = []
    if replaced or doubled:   # every line named, never cut short: the note is the owner's list of what was changed
        said = []
        if replaced:
            listed = "; ".join(f"{n}번째 줄 {points}" for n, points in replaced)
            said.append(f"보이지 않거나 빈칸처럼 보이는 문자를 \\uXXXX 표기로 바꿨습니다: {listed}.")
        if doubled:
            said.append(f"원문의 백슬래시 {doubled}개는 모두 두 개씩 보였습니다. 그래서 홀수 개의 백슬래시 뒤에 오는 "
                        "표기는 바꾼 문자이고, 짝수 개 뒤에 오는 것은 원문의 글자입니다.")
        note = ["- 위 펜스 안에서 " + " ".join(said)]
    return [fence, *body, fence, *note]


def judge_line(who, judge):
    if judge is None:
        return f"- 판정자 {who}: 수락된 판정 없음"
    marks = ", ".join(f"{inline(k)}={inline(v)}" for k, v in judge["requirements"].items())
    units = f"단위 비교 {len(judge['units'])}개는 부록에 있습니다" if judge["units"] else "단위 판정 없음"
    return (f"- 판정자 {who} ({inline(judge['seat'])}): 요구 사항 {marks}; 결과 등급 {inline(judge['consequence_class'])}; "
            f"{units}")


def judge_units_line(who, judge):
    """One judge's comparison of the candidate with every retrieved unit: the appendix's line, so a row stays short
    and nothing a judge wrote is left off the page."""
    return (f"  - 판정자 {who} · 단위 비교: " + "; ".join(
        f"{inline(u['unit'])} 상황 {inline(u['situation'])} 행동 {inline(u['action'])}: {inline(u['reason'])}"
        + (f" (인용: {inline(u['quote'])})" if u.get("quote") else "") for u in judge["units"]))


def judge_record_lines(who, judge):
    """Everything else one judge wrote, for the appendix: the reason for every requirement (the row prints only the
    disputed and the jointly unmet ones), whether the situation no longer arises, the units it matched and its
    relations to ledger entries. With `judge_units_line`, no field of an accepted judgment is on no line of the page."""
    out = []
    reasons = judge.get("reasons") or {}
    if reasons:
        out.append(f"  - 판정자 {who} · 요구 사항별 이유: " + "; ".join(
            f"{inline(n)}={inline((judge.get('requirements') or {}).get(n))}: {inline(r)}" for n, r in reasons.items()))
    gone = judge.get("no_longer_arises")
    if isinstance(gone, dict):
        out.append(f"  - 판정자 {who} · 더는 생기지 않는 상황인가: {inline(gone.get('value'))}"
                   + (f": {inline(gone.get('reason'))}" if gone.get("reason") else "")
                   + (f" (근거 {', '.join(inline(e) for e in gone.get('evidence_ids') or [])})"
                      if gone.get("evidence_ids") else ""))
    if judge.get("matching_units"):
        out.append(f"  - 판정자 {who} · 일치한 단위: " + "; ".join(
            f"{inline(m.get('unit_id'))} 기여 {inline(m.get('contribution'))}"
            f" (근거 {', '.join(inline(e) for e in m.get('contribution_evidence_ids') or []) or '없음'})"
            f" 따름 {inline(m.get('following'))}"
            f" (근거 {', '.join(inline(e) for e in m.get('following_evidence_ids') or []) or '없음'})"
            for m in judge["matching_units"]))
    if judge.get("ledger_relations"):
        out.append(f"  - 판정자 {who} · 대장 항목과의 관계: " + "; ".join(
            f"{inline(r.get('entry_id'))} {inline(r.get('relation'))}: {inline(r.get('reason'))}"
            for r in judge["ledger_relations"]))
    return out


SUBJECT_LABELS = {"lesson": "교훈", "situation": "상황", "action": "행동", "exception": "예외",
                  "member_lesson": "묶인 교훈", "ledger_lesson": "대장에 적힌 교훈", "similar_units": "비슷한 두 단위",
                  "finding": "발견", "rejection_reason": "형성 단계의 거부 이유", "hinted_unit": "가리키는 단위",
                  "no_source": "원문 없음"}


def reason_lines(row, name):
    """Each judge's own reason for one requirement, indented under the line that names it."""
    return [f"  - 판정자 {who}의 이유: {inline(((row['judges'] or {}).get(who) or {}).get('reasons', {}).get(name))}"
            for who in JUDGES if ((row.get("judges") or {}).get(who) or {}).get("reasons", {}).get(name)]


def proposal_lines(answer):
    """The proposal's own parts, beyond its O6 reasons: destination, operations, contract, observation, artifacts and
    the unknowns it carries."""
    out = []
    dest = stage_propose.carried_destination(answer)
    out.append(f"- 대상: layer {inline(dest.get('layer'))}, carrier {inline(dest.get('carrier'))}" if dest
               else "- 대상: 없음 (바꾸지 않는 제안은 대상을 갖지 않습니다)")
    for n, op in enumerate(answer.get("operations") or [], 1):
        out.append(f"- 연산 {n}: {inline(op['type'])} {inline(op['target'])} "
                   f"(before {inline(str(op['before_state_sha256'])[:12])})")
        for field in ("content", "diff"):
            if op.get(field):
                out += fenced(op[field])
    contract = answer.get("behavior_contract")
    if contract:
        out.append("- 행동 계약: " + "; ".join(
            f"{inline(k)} {inline(v if isinstance(v, str) else ' / '.join(v))}" for k, v in contract.items()))
    observation = answer.get("expected_observation")
    if observation:
        out.append("- 기대 관찰: " + "; ".join(f"{inline(k)} {inline(v)}"
                                         for k, v in observation.items() if v is not None))
    artifacts = answer.get("artifact_set")
    if artifacts:
        out.append(f"- 산출물 등록: {inline(artifacts['registration'])}")
        for field in ("english", "korean"):
            if artifacts.get(field):
                out.append(f"- 산출물 ({field}):")
                out += fenced(artifacts[field])
    for u in answer.get("unknowns") or []:
        out.append(f"- 알 수 없음: {inline(u['field'])}={inline(u['state'])} — {inline(u['effect'])}")
    return out


def s7b_lines(state):
    """What S7b recorded for the row, in the owner's words; its notes and the alternative's reason are model text, kept
    on their field's line. The alternative is offered under its one id."""
    kind = (state or {}).get("state")
    if kind == "reviewed":
        holds = lambda v: "맞음" if v else "맞지 않음"  # noqa: E731
        out = [f"- S7b: 검토함 · 판정 {'이견' if state['verdict'] == 'disagree' else '동의'} · 처분 "
               f"{holds(state['disposition_holds'])} · 위치 {holds(state['destination_holds'])} · 병합 충실 "
               f"{inline(state['faithful_merge'])} · 통과하지 못한 기준 "
               f"{', '.join(inline(b) for b in state['bars_failing'] or []) or '없음'}"
               + (" · 소유자가 정합니다" if state.get("owner_resolves") else "")]
        out.append(f"- S7b 메모: {inline(state.get('notes'))}")
        alt = state.get("alternative")
        if alt:
            where = stage_propose.carried_destination(alt) or {}
            out.append(f"- S7b 대안 {ALTERNATIVE_ID}: 처분 {inline(alt.get('disposition'))} · 위치 "
                       f"{inline(where.get('layer') or '-')}/{inline(where.get('carrier') or '-')} · 이유 "
                       f"{inline(alt.get('reason'))} "
                       f"(고르려면 `결정: 수정 대안 {ALTERNATIVE_ID}`)")
        return out
    if kind == "returned":
        return [f"- S7b: 돌려보냄 ({', '.join(inline(c) for c in state.get('codes') or []) or '코드 없음'})"]
    if kind == "unreviewed":
        return [f"- S7b: 검토 없음 ({inline(state.get('why'))})"]
    return [f"- S7b: 해당 없음 ({S7B_NONE['why']})"]


def s9b_lines(state):
    """What S9b found of the row's Korean. A marked row says so in its heading too (`row_lines`)."""
    kind = state.get("state")
    if kind == "marked":
        return [f"- S9b: {MARK} — 한 번 다시 만든 뒤에도 영어 원문과 맞지 않거나 쉽지 않습니다. 영어 원문을 함께 보고 "
                "결정하세요.", f"- S9b 메모: {inline(state.get('notes'))}"]
    if kind == "regenerated":
        return ["- S9b: 한국어를 한 번 다시 만든 뒤 통과"]
    if kind == "passed":
        return ["- S9b: 통과"]
    if kind == "returned":
        return [f"- S9b: 돌려보냄 ({', '.join(inline(c) for c in state.get('codes') or []) or '코드 없음'})"]
    return [f"- S9b: 검토 없음 ({inline(state.get('why'))})"]


def mark_problems(doc, text):
    """An item S9b's own review marked whose heading in `text` does not carry the mark (MARK_MISSING). It reads the
    marked ids `document` took from S9b's review, not the rows' states, so a state worked out wrong is caught too: the
    mark is the one thing S9b's result must change in the review, and a render that dropped it would show a failing
    row as clean."""
    headings = {line.split("`")[1]: line for line in text.split("\n") if line.startswith("### ") and "`" in line}
    return [f"MARK_MISSING {ident}: S9b marked it and its heading does not say {MARK}"
            for ident in doc.get("marked") or [] if MARK not in headings.get(ident, "")]


SIDES = {"A": "판정자 A 쪽", "B": "판정자 B 쪽", "own": "소유자 값"}


def row_lines(row, fields):
    """One row as the review prints it, its owner block last."""
    o6 = row["o6"]
    marked = (row.get("s9b") or {}).get("mark")
    out = [f"### {row['rank']}. `{row['item_id']}`" + (f" · {MARK}" if marked else ""),
           f"- 상태: {inline(STATUS_LABELS.get(row['status'], row['status']))} · 종류 {inline(row['kind'])} · 진단 "
           f"{inline(row['diagnosis'])} · 처분 {inline(row['disposition'])} · 결과 등급 {inline(row['consequence'])} · "
           f"독립 계보 {inline(row['lineages'])}"]
    labels = {"what_happened": "무엇이 있었나", "proposal": "제안", "reason": "이유", "cost": "비용",
              "serves": "누구에게", "falsifier": "반증"}
    # what the row is about, before anything said of it: the source's own words, which are English
    out += [f"- 후보 원문 · {SUBJECT_LABELS.get(part['part'], inline(part['part']))}: {inline(part['text'])}"
            for part in row.get("subject") or []]
    out += [f"- {labels.get(name, name)}: {inline(o6[name])}" for name in fields]
    if row.get("judges"):
        out += [judge_line(who, row["judges"].get(who)) for who in JUDGES]
    if row["status"] == "rejected" and row.get("judges"):
        held = [row["judges"].get(who) or {} for who in JUDGES]
        for name in sorted(set.intersection(*[{n for n, v in (j.get("requirements") or {}).items() if v == "unmet"}
                                              for j in held])):
            out.append(f"- 함께 미충족으로 본 요구 사항: {inline(name)}")
            out += reason_lines(row, name)
    adjudication = row.get("adjudication")
    if adjudication:
        said = "; ".join(f"{inline(r.get('judgment_ref'))} {inline(r.get('value'))} "
                         f"({SIDES.get(r.get('side'), inline(r.get('side')))})" for r in adjudication.get("resolved") or [])
        out.append(f"- 소유자 판정: v{inline(adjudication.get('version'))}의 결정 {inline(adjudication.get('adjudication_id'))}"
                   f"에서 {said} · 판정 전 {inline(adjudication.get('before'))}, 다시 계산한 결과 "
                   f"{inline(adjudication.get('derived'))}")
    for d in row.get("disputed") or []:
        out.append(f"- 판정할 것 {d['label']}: {inline(d['ref'])} — A {inline(d['A'])}, B {inline(d['B'])} (자기 값은 "
                   f"{' 또는 '.join(inline(v) for v in d['values'])})")
        out += reason_lines(row, d["ref"].split("/", 1)[1] if "/" in d["ref"] else d["ref"])
    if row.get("proposal"):
        out += proposal_lines(row["proposal"])
    out += s7b_lines(row["s7b"])
    if row.get("s9b") is not None:
        out += s9b_lines(row["s9b"])
    out.append(f"- 시험: {row['test']}")
    if row.get("awaiting_R"):
        out.append(f"- {AWAITING_R}")
    if row.get("failure"):
        out.append(f"- 실패: {inline(row['failure']['stage'])} {', '.join(inline(c) for c in row['failure']['codes'])}")
    if row.get("units"):
        out.append(f"- 관련 단위: {len(row['units'])}개 (부록의 `{row['item_id']}`)")
    if row.get("events"):
        out.append(f"- 사건: {', '.join(inline(e) for e in row['events'])}")
    if row.get("members"):
        out.append(f"- 구성원: {len(row['members'])}개 (부록의 `{row['item_id']}`). 이 행의 결정 한 줄은 구성원 모두에 "
                   "적용됩니다.")
    out.append(f"- 해시: item_sha {row['item_sha']} · payload_sha256 {row['payload_sha256']}")
    out += owner_lines.review_block(row["item_id"], row["item_sha"], [d["label"] for d in row.get("disputed") or []])
    return out


def header_lines(meta, counts):
    """§9's header: the declaration, per-source coverage, the controls, the natural rejection share, the counts per
    disposition and status, the previous window's observation resolutions, §13's measures and the budget spent. A part
    whose producer has not run is named, never left out."""
    d = meta["declaration"]
    out = [f"# 세션 정리 검토 v{meta['version']}", "",
           "이 파일은 코드가 만든 렌더이고 고치지 않습니다. 결정은 같은 버전의 decisions 파일에서 각 항목의 "
           "소유자 블록 안에만 씁니다.", "",
           owner_lines.APPROVAL_EFFECT, "",
           "## 머리말", "",
           f"- 실행: {inline(meta['run_id'])} · 종류 {inline(d.get('kind'))} · 자세 {inline(d.get('posture'))} · 선언 순번 "
           f"{inline(d.get('declaration_seq'))}",
           f"- 창: {inline((d.get('window') or {}).get('start'))} – {inline((d.get('window') or {}).get('end'))} "
           f"({inline((d.get('window') or {}).get('tz'))})",
           f"- 질문: {inline(d.get('question'))}"]
    for source, s in sorted((meta.get("census") or {}).items()):
        totals = ", ".join(f"{inline(k)} {inline(v)}" for k, v in sorted((s.get("totals") or {}).items())) or "없음"
        out.append(f"- 출처 {inline(source)}: 상태 {inline(s.get('state'))}, 발견 {inline(s.get('discovered'))}, {totals}")
    flags = meta.get("window_flags")
    out.append(f"- 창 범위: accounted {inline(flags['accounted'])}, fully_read {inline(flags['fully_read'])}" if flags
               else "- 창 범위: 기록 없음 (coverage.json에 이 창의 표시가 없음)")
    out.append(f"- 대조군 결과: {inline(meta['controls'])}")
    if meta.get("legacy_unexpected"):
        out.append("- 예상 밖의 legacy 묶음 (소유자가 정한 세 묶음 밖): " + ", ".join(inline(w) for w in meta["legacy_unexpected"]))
    out.append(f"- 자연 거부 비율: {inline(meta['rejection_share'])}")
    out.append("- 처분별: " + ", ".join(f"{inline(k)} {inline(v)}" for k, v in counts["disposition"].items()))
    out.append("- 상태별: " + ", ".join(f"{inline(STATUS_LABELS.get(None if k == 'None' else k, k))} {inline(v)}"
                                      for k, v in counts["status"].items()))
    out.append("- 출처별 후보: " + ", ".join(f"{inline(k)} {inline(v)}" for k, v in counts["candidates"].items()))
    out.append(f"- 사건: 후보 구성원 {counts['candidate_members']}, 거부된 발견 {counts['rejected_findings']}개 "
               f"(구성원 {counts['rejected_finding_members']}), 비발견 "
               + (", ".join(f"{inline(k)} {inline(v)}" for k, v in counts["non_findings"].items()) or "없음"))
    out.append(f"- 이전 창의 관찰 결과: {inline(meta['resolutions'])}")
    out.append("- §13 측정: 아직 없음: S12가 돌지 않았습니다.")
    out.append("- 쓴 예산: " + (", ".join(f"{inline(s)} {inline(v)}" for s, v in meta["spent"].items()) or "기록 없음"))
    out.append(f"- {FALLBACK}")
    return out


def appendix_lines(doc, locators):
    out = ["## 부록", "", "### 비발견 (사유별)", ""]
    for n in sorted(doc["appendix"]["non_findings"], key=lambda n: (n["reason"], n["event_id"])):
        dup = f", {inline(n['duplicate_of'])}의 중복" if n.get("duplicate_of") else ""
        out.append(f"- `{n['event_id']}` {inline(n['reason'])}{dup} · 위치 {inline(locators.get(n['event_id'], 'unavailable'))}")
    if not doc["appendix"]["non_findings"]:
        out.append("- 없음")
    out += ["", "### 그룹 행의 구성원", ""]
    for ident, members in sorted(doc["appendix"]["group_members"].items()):
        out.append(f"- `{ident}` ({len(members)}개): " + ", ".join(f"`{m}`" for m in members))
    if not doc["appendix"]["group_members"]:
        out.append("- 없음")
    out += ["", "### 행별 판정 기록과 관련 단위", "",
            "- 각 행에는 갈린 요구 사항과 함께 미충족으로 본 요구 사항의 이유만 있고, 판정자가 쓴 나머지는 모두 여기에 "
            "있습니다. S7b가 항목마다 쓴 세부 사유(처분과 위치 검토의 이유, 기준별 이유, 병합 소견)는 S7b의 문서에 "
            "실리지 않아 이 화면에도 없으며, 실행 폴더의 review-proposals 호출 기록에 있습니다.", ""]
    held = [r for r in doc["rows"] if r.get("units") or any(j for j in (r.get("judges") or {}).values())]
    for row in held:
        out.append(f"- `{row['item_id']}`")
        for who in JUDGES:
            judge = (row.get("judges") or {}).get(who)
            if not judge:
                continue
            out += judge_record_lines(who, judge)
            if judge.get("units"):
                out.append(judge_units_line(who, judge))
        if row.get("units"):
            out.append("  - 관련 단위: " + ", ".join(f"{inline(u['unit_id'])} (전달 증거: {inline(u['delivery'])})"
                                                 for u in row["units"]))
    if not held:
        out.append("- 없음")
    return out


def render_text(doc, meta, locators):
    """The review's bytes: the header, each §9 group in ranking.py's order with its rows, and the appendix."""
    fields = o6_fields()
    out = header_lines(meta, doc["counts"])
    for group in ranking.table()["groups"]:
        rows = [r for r in doc["rows"] if r["status_group"] == group["id"]]
        out += ["", f"## {GROUP_TITLES[group['id']]} ({len(rows)})", ""]
        for row in rows:
            out += row_lines(row, fields) + [""]
        if not rows:
            out.append("- 없음")
    out += [""] + appendix_lines(doc, locators)
    text = "\n".join(out) + "\n"
    missing = page_problems(doc, text) + mark_problems(doc, text)
    if missing:
        raise Refused("RENDER_REFUSED " + "\n".join(missing))
    return text


def page_problems(doc, text):
    """What makes `text` a page whose owner lines are not all the renderer's: a line outside every owner block shaped
    like an owner line or a marker (OWNER_LINE_OUTSIDE_BLOCK; the parser would not read it, but the owner would), a
    MARKUP character a preview would read, on a line outside every fence and marker (MARKUP_LIVE), a character the
    allowlist does not write as itself anywhere but a tab inside a fence (INVISIBLE_CHARACTER), and blocks other than one per row in the rows'
    order (OWNER_BLOCK_FORGED). Every model-made value is written through
    `inline` or `fenced`, so neither can happen from a row's text; this refuses the page if a field ever is not."""
    fixed, blocks, problems = owner_lines.segments(text.split("\n"))
    problems = list(problems)
    fence = None
    for n, line in fixed:
        if owner_lines.owner_shaped(line) and not (owner_lines.OPEN.match(line) or line == owner_lines.CLOSE):
            problems.append(f"OWNER_LINE_OUTSIDE_BLOCK line {n}: shaped like an owner line, and no owner block holds it")
        hidden = invisible_in(line, keep="\t" if fence is not None and line != fence else "")
        if hidden:
            problems.append(f"INVISIBLE_CHARACTER line {n}: U+{ord(hidden[0]):04X} changes what is seen without being "
                            "seen")
        if fence is None and re.fullmatch(r"`{3,}", line):
            fence = line
        elif fence is not None:
            fence = None if line == fence else fence
        elif not (owner_lines.OPEN.match(line) or line == owner_lines.CLOSE) and live_markup(line):
            problems.append(f"MARKUP_LIVE line {n}: column {live_markup(line)[0] + 1} is markup a Markdown preview "
                            "would read, outside every fence")
    held = [b["fields"].get("item") for b in blocks]
    rows = [r["item_id"] for r in doc["rows"]]
    if held != rows:
        at = next((i for i, (h, r) in enumerate(zip(held, rows)) if h != r), min(len(held), len(rows)))
        problems.append(f"OWNER_BLOCK_FORGED: the page holds {len(held)} owner blocks for {len(rows)} rows; block "
                        f"{at + 1} is {held[at] if at < len(held) else 'missing'}, row {at + 1} is "
                        f"{rows[at] if at < len(rows) else 'none'}")
    return problems


def spec_of(doc):
    """The current rows as `owner_lines.parse` holds the owner's lines to them: each item's sha, its disputed labels
    with their own values, S7b's alternative under its one id when S7b offered one, and the keep records its proposal
    overrides."""
    return {r["item_id"]: {"item_sha": r["item_sha"],
                           "judgments": {d["label"]: list(d["values"]) for d in r.get("disputed") or []},
                           "refs": {d["label"]: d["ref"] for d in r.get("disputed") or []},
                           "alternatives": [ALTERNATIVE_ID] if ((r.get("s7b") or {}).get("state") == "reviewed"
                                                                and r["s7b"].get("alternative")) else [],
                           "guarded_keeps": list(r.get("guarded_keeps") or []),
                           "members": list(r.get("members") or [])}
            for r in doc["rows"]}


def locators_of(run_dir):
    """Each event's locator, `<session file>#<record>`, from S3's stored events."""
    out = {}
    for path in sorted((pathlib.Path(run_dir) / "events").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                out.setdefault(row["event_id"], f"{path.stem}#{row.get('at_record')}")
    return out


def meta_of(run_dir, declaration, docs, version):
    """The header's facts, each from its producer or named absent."""
    run_dir = pathlib.Path(run_dir)
    window = declaration.get("window") or {}
    wid = coverage_window_id(window)
    cov = records.read_json(run_dir / "coverage.json") if (run_dir / "coverage.json").is_file() else {}
    flags = (cov.get("windows") or {}).get(wid)
    ledger = run_dir / "supervisor" / "ledger.json"
    spent = {}
    if ledger.is_file():
        for stage, entry in (records.read_json(ledger).get("stages") or {}).items():
            s = entry.get("spent") or {}
            spent[stage] = (s.get("measured") or 0) + (s.get("provisional") or 0)
    res_path = run_dir / "observations" / "resolutions.json"
    resolutions = "기록 없음 (S3의 observations/resolutions.json이 없음)"
    if res_path.is_file():
        held = records.read_json(res_path).get("resolutions") or {}
        tally = collections.Counter(str((v or {}).get("resolution") if isinstance(v, dict) else v) for v in held.values())
        resolutions = ", ".join(f"{k} {n}" for k, n in sorted(tally.items())) or "없음"
    natural = [r for r in docs_rows_natural(docs)]
    rejected = sum(1 for r in natural if r == "rejected")
    share = f"{rejected} / {len(natural)}" if natural else "해당 없음 (판정된 자연 후보 없음)"
    # the planted controls evaluated after S6, never a stop (D-20261115-18d56b), over S6's own derivations
    evaluation = planted_controls.evaluation_in(run_dir)
    controls = planted_controls.korean_line(evaluation)
    unexpected = sorted({r["legacy_word"] for r in document_rows(docs) if r["row_kind"] == "legacy_group"}
                        - set(LEGACY_GROUPS))
    return {"version": version, "run_id": run_dir.resolve().name, "declaration": declaration,
            "legacy_unexpected": unexpected,
            "census": (docs.get("census") or {}).get("sources") or {}, "window_flags": flags, "spent": dict(sorted(spent.items())),
            "resolutions": resolutions, "rejection_share": share, "controls": controls,
            "controls_evaluation": evaluation}


def document_rows(docs):
    return rows_of(docs)[0]


def coverage_window_id(window):
    from runlib import coverage
    return coverage.window_bounds(window)[2] if window else None


def docs_rows_natural(docs):
    """The admission of every natural (not planted) candidate S6 derived: the rejection share's population."""
    planted = {p["candidate_id"] for p in (docs.get("controls") or {}).get("planted") or []}
    return [((v.get("outcome") or {}).get("admission") or {}).get("admission")
            for cid, v in ((docs.get("derivations") or {}).get("verdicts") or {}).items() if cid not in planted]


def frozen_name(version):
    return f"frozen-proposals.v{version}.json"


def material_of(answer):
    """What §13.4 calls a material change of a proposal, as data: its disposition, destination, operation targets and
    behavior contract. Anything else that differs (its reasons, its artifacts' wording) is wording."""
    return {"disposition": answer.get("disposition"), "destination": stage_propose.carried_destination(answer),
            "targets": sorted([op.get("type"), op.get("target")] for op in answer.get("operations") or []),
            "behavior_contract": answer.get("behavior_contract")}


def same_material(now, frozen):
    """Whether a proposal's material is what was frozen. Both sides are read with the destination a proposal
    carries: a `none` frozen before `carried_destination` holds the layer its answer wrote, and that is no change."""
    def carried(m):
        return {**m, "destination": stage_propose.carried_destination(m)} if isinstance(m, dict) else m
    return carried(now) == carried(frozen)


def frozen_after(held, rows, version, rendered_at):
    """§13.4's frozen proposals after this render: each item's proposal as it was the first time it was rendered as
    proposed (release 1 has no "tested", lead decision E7), never replaced by a later version."""
    items = dict((held or {}).get("items") or {})
    for r in rows:
        if r["status"] in ("proposed", "tested") and r.get("proposal") and r["item_id"] not in items:
            items[r["item_id"]] = {"version": version, "rendered_at": rendered_at,
                                   "material": material_of(r["proposal"]),
                                   "wording_sha256": sha256_of({"reasons": r["proposal"].get("reasons"),
                                                                "artifact_set": r["proposal"].get("artifact_set")})}
    return {"stage": STAGE, "items": dict(sorted(items.items()))}


def previous_of(run_dir, version):
    """`(previous, frozen)` for a render of `version`: the highest earlier version with a rows file (written last, so a
    render cut short before it is skipped), bound by that file's sha256, and that version's frozen proposals, held to
    the sha256 its rows file recorded (FROZEN_CHANGED). A rows file whose render or frozen proposals are gone was
    complete and lost a file since (RENDER_FILE_MISSING). `(None, None)` before the first render."""
    run_dir = pathlib.Path(run_dir)
    done = sorted(int(p.name[len("review.v"):-len(".json")]) for p in run_dir.glob("review.v*.json")
                  if p.name[len("review.v"):-len(".json")].isdigit() and int(p.name[len("review.v"):-len(".json")]) < version)
    if not done:
        return None, None
    k = done[-1]
    rows_path, frozen_path = run_dir / f"review.v{k}.json", run_dir / frozen_name(k)
    for gone in (run_dir / f"review.ko.v{k}.md", frozen_path):
        if not gone.is_file():
            raise Refused(f"RENDER_FILE_MISSING {gone.name}: review.v{k}.json is written after it, so it was there and "
                          "is gone; a render's files are kept")
    held = records.read_json(rows_path)
    if records.sha256_file(frozen_path) != held.get("frozen_sha256"):
        raise Refused(f"FROZEN_CHANGED {frozen_name(k)}: its bytes are not the ones review.v{k}.json recorded; the "
                      "first-render proposals §13.4 measures against are written once")
    return {"version": k, "rows_sha256": records.sha256_file(rows_path)}, records.read_json(frozen_path)


def next_version(run_dir):
    held = [int(p.name[len("review.ko.v"):-len(".md")]) for p in pathlib.Path(run_dir).glob("review.ko.v*.md")
            if p.name[len("review.ko.v"):-len(".md")].isdigit()]
    return max(held, default=0) + 1


def run(run_dir, ledger=None):
    """S9 through the shared mechanism: the review, its owner copy and its rows, as version n+1. Nothing is written on
    refusal, and an existing version is never written again."""
    run_dir = pathlib.Path(run_dir)
    overlays = s9b_inputs(run_dir) + stage_adjudicate.adjudicated_inputs(run_dir)
    with records.run_stage(run_dir, STAGE, INPUTS + overlays) as stage:
        if ledger is None:
            from runlib import lifecycle_intake
            ledger = lifecycle_intake.ledger_of(stage.declaration)[0]
        docs = load(run_dir, ledger, overlays)
        doc = document(docs)
        if doc["problems"]:
            raise Refused("RENDER_REFUSED " + "\n".join(doc["problems"]))
        version = next_version(run_dir)
        meta = meta_of(run_dir, stage.declaration, docs, version)
        text = render_text(doc, meta, locators_of(run_dir))
        name, copy_name, rows_name = f"review.ko.v{version}.md", f"decisions.ko.v{version}.md", f"review.v{version}.json"
        frozen_rel = frozen_name(version)
        for rel in (name, copy_name, rows_name, frozen_rel):
            if (run_dir / rel).exists():
                raise Refused(f"RENDER_VERSION_EXISTS {rel}: a render is written once")
        copy = owner_lines.copy_of(text, name)
        rendered_at = records.now()
        previous, held_frozen = previous_of(run_dir, version)
        frozen = frozen_after(held_frozen, doc["rows"], version, rendered_at)
        records.write_text(run_dir, run_dir / name, text)
        records.write_text(run_dir, run_dir / copy_name, copy)
        records.write_json(run_dir, run_dir / frozen_rel, frozen)
        # the rows file last: a version is complete when it is there, and it binds the frozen proposals and the version
        # before it, so S10 can hold an older version's copy to the current rows through the chain
        records.write_json(run_dir, run_dir / rows_name, {
            "stage": STAGE, "version": version, "render": name, "render_sha256": owner_lines.sha256_text(text),
            "copy": copy_name, "rendered_at": rendered_at, "frozen": frozen_rel,
            "frozen_sha256": records.sha256_file(run_dir / frozen_rel), "previous": previous, "rows": doc["rows"],
            "appendix": doc["appendix"], "counts": doc["counts"], "spec": spec_of(doc),
            "controls": meta["controls_evaluation"]})
        for rel in (name, copy_name, frozen_rel, rows_name):
            stage.output(rel)
        return {"version": version, "render": name, "copy": copy_name, "rows": len(doc["rows"])}


# ---- self-test ----------------------------------------------------------------------------------------------------

def fixture_docs():
    """A run's documents, real-shaped: the S7 document is the real `stage_propose.document` over these derivations."""
    req = derive.table()["requirements"]
    met = {n: "met" for n in req}

    def verdict(adm, a=None, b=None, kind="gap", diagnosis="gap", lineages=2):
        return {"lineages": lineages, "requirements": {"A": a or dict(met), "B": b or dict(met)},
                "outcome": {"admission": {"admission": adm, "row": adm}, "kind": {"kind": kind, "row": "k"},
                            "candidate_diagnosis": {"current": {"diagnosis": diagnosis}, "release": "absent"},
                            "eligible": {"eligible": True, "row": "lineages", "allowed_dispositions": None},
                            "candidate_id": "x", "test": "untested: s8_deferred", "unit_diagnosis": {}, "unit_outcomes": []}}

    disputed_b = {**met, "bounded": "unmet", "positioned": "uncertain"}
    rejected = {**met, "actionable": "unmet"}
    population = {"candidates": [
        {"candidate_id": "k-a", "source": "formed", "event_ids": ["e1", "e2"]},
        {"candidate_id": "k-b", "source": "formed", "event_ids": ["e3"]},
        {"candidate_id": "k-c", "source": "formed", "event_ids": ["e4"]},
        {"candidate_id": "k-d", "source": "formed", "event_ids": ["e5"]},
        {"candidate_id": "k-e", "source": "formed", "event_ids": ["e6"]},
        {"candidate_id": "k-f", "source": "formed", "event_ids": ["e7"]},
        {"candidate_id": "k-g", "source": "formed", "event_ids": ["e11"]},
        {"candidate_id": "due_decision:P-1@r1", "source": "due_decision", "event_ids": []},
        {"candidate_id": "legacy:L-1", "source": "legacy", "event_ids": []},
        {"candidate_id": "legacy:L-2", "source": "legacy", "event_ids": []},
        {"candidate_id": "legacy:L-3", "source": "legacy", "event_ids": []},
        {"candidate_id": "legacy:L-4", "source": "legacy", "event_ids": []},
        {"candidate_id": "legacy:L-5", "source": "legacy", "event_ids": []},
        {"candidate_id": "redundancy_hint:u1|u2", "source": "redundancy_hint", "event_ids": []},
        {"candidate_id": "redundancy_hint:u3|u4", "source": "redundancy_hint", "event_ids": []}],
        "rejected_findings": [{"finding_id": "r-1", "event_ids": ["e8"], "failed": ["bounded"]}],
        "non_findings": [{"event_id": "e9", "reason": "routine_step", "duplicate_of": None},
                         {"event_id": "e10", "reason": "duplicate_of_another_event", "duplicate_of": "e1"}],
        "counts": {"candidates": {"formed": 7, "due_decision": 1, "legacy": 5, "redundancy_hint": 2},
                   "candidate_members": 8, "rejected_finding_members": 1,
                   "non_findings": {"duplicate_of_another_event": 1, "routine_step": 1}}}
    intake = {"candidates": [{"candidate_id": f"legacy:L-{i}", "source": "legacy", "target_entry": f"L-{i}"}
                             for i in range(1, 6)]
              + [{"candidate_id": "due_decision:P-1@r1", "source": "due_decision", "pending_intervention": True,
                  "target_entry": "L-5"}]}

    def entry(ident, word, classification=None):
        return {"id": ident, "status": "incubating", "classification": classification, "lesson": f"lesson of {ident}",
                "decisions": [{"field": "decision1", "legacy_text": f"{word} 2026-07-19 imported", "run": "legacy-1"}]}

    ledger = {"schema": 2, "entries": [entry("L-1", "incubating", {"type": "D"}), entry("L-2", "below-bar-default"),
                                       entry("L-3", "below-bar-default"), entry("L-4", "user-approved-default"),
                                       entry("L-5", "incubating")]}
    derivations = {"stage": "S6", "test": "untested: s8_deferred",
                   "verdicts": {"k-a": verdict("admitted", kind="confirmed", diagnosis="covered", lineages=3),
                                "k-b": verdict("disputed", b=disputed_b),
                                "k-c": verdict("rejected", a=rejected, b=rejected),
                                "k-d": verdict("admitted"),
                                "due_decision:P-1@r1": verdict("admitted", kind="not delivered", diagnosis="unknown"),
                                "k-g": verdict("adjudication", kind="not delivered", diagnosis="unknown"),
                                "k-p": verdict("admitted")},
                   "not_derived": [{"candidate_id": "k-f", "why": "UNIT_OUTCOME_UNDERIVED"}],
                   "delivery": {"state": "delivery_assembly_waiting", "pairs": 3},
                   "unit_outcomes": {"state": "none", "candidates": 5},
                   "arc_confirmation": {"state": "undetermined", "passed_as": False},
                   "points": {"release": "absent"}}
    judged = ["k-a", "k-b", "k-c", "k-d", "k-f", "k-g", "due_decision:P-1@r1", "k-p"]
    judge = {"stage": "S6", "calls": [{"candidate_id": c, "item": item_of(c), "source": "formed"} for c in judged],
             "population": {"candidates": 15, "judged": len(judged), "check_failed": {"k-e": ["QUOTE_MISMATCH"]},
                            "left_out": {"legacy": {"count": 5, "of": 5, "why": "left out"},
                                         "redundancy_hint": {"count": 2, "of": 2, "why": "a sample of 0"}}}}
    judgments = {c: {who: {"seat": f"seat-{who}", "call_id": f"{c}-{who}",
                           "judgment": {"consequence_class": "quality" if who == "A" else "security-relevant",
                                        "requirements": dict(met),
                                        # every field a judge writes, each with text only this candidate and
                                        # this judge carry, so a line that lost one is seen
                                        "units": [{"unit_id": "u-9", "situation": "yes", "action": "no", "reason": "r"},
                                                  {"unit_id": "u-8", "situation": "no", "action": "no",
                                                   "reason": f"unit {c}/{who}", "quote": f"quote {c}/{who}"}],
                                        "no_longer_arises": {"value": False, "reason": f"arises {c}/{who}",
                                                             "evidence_ids": [f"ev-n {c}/{who}"]},
                                        "matching_units": [{"unit_id": "u-9", "contribution": "partial",
                                                            "contribution_evidence_ids": [f"ev-c {c}/{who}"],
                                                            "following": "unknown", "following_evidence_ids": []}],
                                        "ledger_relations": [{"entry_id": "L-1", "relation": "same",
                                                              "reason": f"relation {c}/{who}"}]}}
                     for who in JUDGES} for c in judged}
    # the two judges' own reasons on the disputed and the rejected candidate, as S6's judgment files hold them
    for cid, name in (("k-b", "bounded"), ("k-c", "actionable")):
        for who in JUDGES:
            judgments[cid][who]["judgment"]["requirements"] = {
                **{n: {"mark": "met", "reason": f"{who} agrees {cid} is {n}"} for n in req},
                name: {"mark": "unmet", "reason": f"{who} says {cid} is not {name}"}}
    # what each candidate says: a formed candidate's four parts, a cluster's lessons, a hint's two units
    said = {"k-b": {"candidate_id": "k-b", "source": "formed", "lesson": "Quote the glob", "situation": "An unquoted star",
                    "action": "Quote it", "exception": "Not in bash"},
            "redundancy_hint:u1|u2": {"candidate_id": "redundancy_hint:u1|u2", "source": "redundancy_hint",
                                      "lifecycle": {"target_units": ["u1", "u2"], "match": "near", "similarity": 0.8}}}
    findings = {"r-1": {"finding_id": "r-1", "finding": "The timeout command is absent", "reason": "One retry each time"}}
    candidates = {"candidates": [{"candidate_id": c, "type": "D"} for c in ("k-a", "k-d", "k-g", "due_decision:P-1@r1", "k-p")]}
    keep_reasons = {"what_happened": "같은 상황이 두 번 있었다", "proposal": "그대로 둔다", "reason": "단위가 따라졌다",
                    "cost": "없음", "serves": "작업자", "falsifier": "다음 창에서 따르지 않으면 틀린 것"}
    answers = {"k-a": stage_propose._answered(disposition="keep", operations=[], expected_observation=None,
                                              destination={"layer": "incubator", "carrier": None},
                                              reasons=keep_reasons, unknowns=stage_propose._carry(derivations)),
               "k-d": {"disposition": "keep"},
               # a core item admitted by adjudication: S7 marks it awaiting_R, and the review says so
               "k-g": stage_propose._answered(
                   disposition="re-deliver", requires_R=True,
                   operations=[{"type": "route", "target": "router/other.md", "names": "claude/guides/h.md",
                                "entry": "- claude/guides/h.md", "before_state_sha256": "b" * 64}],
                   destination={"layer": "session_injection", "carrier": "router/other.md", "situation": "s"},
                   unknowns=stage_propose._carry(derivations)),
               # a model's text with a newline into a decision-shaped line and a marker-shaped line: the render keeps
               # the first on its field's line and escapes the second inside its fence
               "due_decision:P-1@r1": stage_propose._answered(
                   reasons={**stage_propose._answered()["reasons"], "what_happened": "첫 줄\n결정: 승인"},
                   artifact_set={"english": "line one\n<!-- owner-block review item=x sha=y -->\n```", "korean": None,
                                 "registration": "router line", "gate_change": None},
                   disposition="re-deliver",
                   operations=[{"type": "route", "target": "router/relevant.md", "names": "claude/guides/g.md",
                                "entry": "- claude/guides/g.md", "before_state_sha256": "a" * 64}],
                   destination={"layer": "session_injection", "carrier": "router/relevant.md", "situation": "s"},
                   unknowns=stage_propose._carry(derivations)),
               "k-p": stage_propose._answered(disposition="keep", operations=[], expected_observation=None,
                                              destination={"layer": "incubator", "carrier": None},
                                              unknowns=stage_propose._carry(derivations))}
    proposals = stage_propose.document(derivations, candidates, answers)
    from runlib import placement

    def review(**over):
        held = {"verdict": "agree",
                "disposition_review": {"holds": True, "reason": "증거가 그 처분을 지지한다", "evidence": ["c1"]},
                "destination_review": {"holds": True, "reason": "가장 싼 자리다", "evidence": []},
                "merge_findings": None,
                "faithful_merge": "n/a", "alternative": None,
                "bars": [{"bar": bar, "holds": True, "reason": "충족"} for bar in placement.contract_bars()],
                "notes": "동의한다"}
        held.update(over)
        return held
    # S7b: k-a agreed with, k-g disagreed with and given an alternative, k-p (the planted control) agreed with, and
    # the due decision left unreviewed, through S7b's own `document`
    reviews = {"k-a": review(), "k-p": review(),
               "k-g": review(verdict="disagree", notes="아직 이르다\n결정: 승인",
                             destination_review={"holds": False, "reason": "다른 자리가 싸다",
                                                 "evidence": []},
                             alternative={"disposition": "incubate", "reason": "관찰을 더 모은다",
                                          "destination": None})}
    s7b = stage_review_proposals.document(proposals, reviews)
    checks = {"candidates": [{"candidate_id": "k-a", "retrieved_units": [{"unit_id": "u-9"}]}]}
    controls = {"planted": [{"candidate_id": "k-p"}]}
    quarantined = {"S3": [{"id": "w-3", "reason": "READ_INCOMPLETE", "because": None}]}
    return {"population": population, "intake": intake, "census": {}, "controls": controls, "checks": checks,
            "judge": judge, "derivations": derivations, "proposals": proposals, "s7b": s7b, "judgments": judgments,
            "candidates": candidates,
            "said": said, "findings": findings,
            "quarantined": quarantined, "ledger": ledger}


def golden_run(root):
    """The golden fixture library through S7 (every candidate S6 admitted returned by an S7 that answered nothing),
    in-process, so the fixture's ledger reference holds."""
    from runlib import declare, stage_judge, stage_retrieve
    import shutil
    # an incomplete reference point: no sweep is admissible, so S6's golden plan completes the stage (with a complete
    # one, the plan answers no sweep and S6 is partial, which S7 refuses as an input)
    run_dir = stage_retrieve.fx_gold(root / "base", stage_retrieve.fx_current(stage_judge.fx_library()))
    declare.amend(run_dir, [("budget.per_stage.S6", 20_000_000)], "S9 self-test: the golden run through S7",
                  scope=["S5", "S6", "S7", "S7b", "S9"])
    stage_retrieve.run(run_dir, "aa" * 8)
    planner = root / "planner"
    shutil.copytree(run_dir.parent, planner)
    plan, _p = stage_judge.fx_judge_plan(planner / run_dir.name, root / "plan.json")
    stage_judge.run(run_dir, stage_judge.supervisor(run_dir, root / "cells", plan))
    # S7's own run, answering nothing: every candidate S6 admitted is returned, and the render reads the proposals
    # document S7's record names as its output
    stage_propose.run(run_dir, {})
    stage_review_proposals.run(run_dir, {})
    return run_dir


def self_test():
    """Positive controls on the fixture run's documents first; then one planted break per rule, each named."""
    import copy
    failures, ran, reporting = [], [], []

    def record(name):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        ran.append(name)

    def control(name, got, want):
        record(name)
        if not isinstance(got, str):
            raise TypeError(f"CONTROL_GOT_NOT_STR {name}: {type(got).__name__}")
        if want not in got:
            failures.append((name, f"expected {want!r} in {got[:600]!r}"))

    def equal(name, got, want):
        record(name)
        if got != want:
            failures.append((name, f"expected {want!r}, got {got!r}"))

    def clean(name, problems):
        record(name)
        if not isinstance(problems, list):
            raise TypeError(f"CLEAN_PROBLEMS_NOT_LIST {name}: {type(problems).__name__}")
        if problems:
            failures.append((name, f"expected nothing, got {problems}"))

    base = fixture_docs()

    def doc_of(edit=None):
        docs = copy.deepcopy(base)
        if edit:
            edit(docs)
        return document(docs)

    def said(edit):
        return "\n".join(doc_of(edit)["problems"]) or "(none)"

    def row_of(doc, ident):
        return next((r for r in doc["rows"] if r["item_id"] == ident), {})

    good = doc_of()
    clean("the fixture run's documents make a review with nothing refused", good["problems"])
    ids = [r["item_id"] for r in good["rows"]]
    equal("every population member, rejected finding and quarantined item is one row or one group member",
          sorted(ids), sorted(["k-a", "k-b", "k-c", "k-d", "k-e", "k-f", "k-g", "due_decision:P-1@r1", "legacy:L-1",
                               "group:legacy:below-bar-default", "group:legacy:user-approved-default",
                               "group:legacy:incubating", "group:left_out:redundancy_hint", "r-1", "S3:w-3"]))
    equal("the planted control S7 answered for is no row", "k-p" in ids, False)
    equal("statuses: proposed, disputed, rejected, returned, failed (S5 and S6), quarantined, and the unjudged",
          {r["item_id"]: r["status"] for r in good["rows"]},
          {"k-a": "proposed", "k-b": "disputed", "k-c": "rejected", "k-d": "returned", "k-e": "failed", "k-f": "failed",
           "k-g": "proposed",
           "due_decision:P-1@r1": "proposed", "legacy:L-1": None, "group:legacy:below-bar-default": None,
           "group:legacy:user-approved-default": None, "group:legacy:incubating": None,
           "group:left_out:redundancy_hint": None, "r-1": "rejected", "S3:w-3": "quarantined"})
    equal("every failed, returned and quarantined row is in §9's quarantined-or-failed group, never placed by its kind",
          {r["item_id"]: r["status_group"] for r in good["rows"] if r["status"] in (FAILED, RETURNED, QUARANTINED)},
          {i: "quarantined_or_failed" for i in ("k-d", "k-e", "k-f", "S3:w-3")})
    equal("the owner's legacy rule: a classified entry is its own row, the rest grouped by decision1's first word",
          {r["item_id"]: r["members"] for r in good["rows"] if r["row_kind"] == "legacy_group"},
          {"group:legacy:below-bar-default": ["legacy:L-2", "legacy:L-3"],
           "group:legacy:user-approved-default": ["legacy:L-4"], "group:legacy:incubating": ["legacy:L-5"]})
    equal("and every group row defaults to none", {r["disposition"] for r in good["rows"] if r["members"]}, {"none"})
    # WP-12 answers an unclassified legacy entry with the default `none` in code (no call): it stays in its group; a
    # classified entry, or one S7 proposed something else for, is its own row carrying the proposal
    legacy_docs = copy.deepcopy(fixture_docs())
    base_p = next(p for p in legacy_docs["proposals"]["proposals"] if p["candidate_id"] == "k-a")
    for cid, disposition in (("legacy:L-1", "keep"), ("legacy:L-2", "none"), ("legacy:L-5", "keep")):
        legacy_docs["proposals"]["proposals"].append(dict(copy.deepcopy(base_p), candidate_id=cid,
                                                          disposition=disposition))
    legacy_docs["proposals"]["returned"].append({"candidate_id": "legacy:L-4", "problems": ["ANSWER_INVALID x"]})
    legacy_docs["s7b"] = stage_review_proposals.document(legacy_docs["proposals"], {})
    unworded = copy.deepcopy(fixture_docs())
    for entry in unworded["ledger"]["entries"]:
        if entry["id"] == "L-3":
            entry["decisions"] = []
    equal("a legacy entry with no decision1 is grouped under S7's own key for it",
          {r["item_id"]: r["members"] for r in rows_of(unworded)[0] if r["row_kind"] == "legacy_group"}
          .get("group:legacy:none"), ["legacy:L-3"])
    legacy_doc = document(legacy_docs)
    legacy_rows, legacy_problems = legacy_doc["rows"], legacy_doc["problems"]
    clean("legacy entries S7 answered make rows with nothing refused", legacy_problems)
    by_id = {r["item_id"]: r for r in legacy_rows}
    equal("a legacy entry S7 proposed for is its own row carrying the proposal when it is classified or the proposal is "
          "not the default; S7's none default stays in its group; one S7 returned is a failed row",
          ((by_id.get("legacy:L-1") or {}).get("status"), bool((by_id.get("legacy:L-1") or {}).get("proposal")),
           "legacy:L-2" in by_id, (by_id.get("group:legacy:below-bar-default") or {}).get("members"),
           (by_id.get("legacy:L-5") or {}).get("disposition"), "group:legacy:incubating" in by_id,
           (by_id.get("legacy:L-4") or {}).get("status"), "group:legacy:user-approved-default" in by_id),
          ("proposed", True, False, ["legacy:L-2", "legacy:L-3"], "keep", False, RETURNED, False))
    equal("the disputed row's 판정 labels are the requirements the judges did not both mark met",
          [(d["label"], d["ref"], d["A"], d["B"]) for d in row_of(good, "k-b").get("disputed", [])],
          [("1", "requirement/bounded", "met", "unmet"), ("2", "requirement/positioned", "met", "uncertain")])
    equal("a disagreeing consequence class orders the row by the graver one", row_of(good, "k-b").get("consequence"),
          "security")
    equal("the proposal's O6 text is S7's Korean reasons", row_of(good, "k-a").get("o6", {}).get("falsifier"),
          "다음 창에서 따르지 않으면 틀린 것")
    equal("every row carries S6's named test state", {r["test"] for r in good["rows"]}, {"untested: s8_deferred"})
    equal("the S7-returned row names S7's codes", row_of(good, "k-d").get("failure", {}).get("stage"), "S7")
    equal("the rows are ranked: a rank per row, 1..n", [r["rank"] for r in good["rows"]], list(range(1, len(ids) + 1)))
    equal("and grouped by §9: the proposed group first", (good["rows"] or [{}])[0].get("status_group"),
          "proposed_and_tested")
    equal("ranking twice gives the same bytes", canonical(doc_of()["rows"]), canonical(good["rows"]))
    equal("the input order does not move the order",
          [r["item_id"] for r in doc_of(lambda d: d["population"]["candidates"].reverse())["rows"]], ids)
    a = row_of(good, "k-a")
    def recost(d):
        next(p for p in d["proposals"]["proposals"] if p["candidate_id"] == "k-a")["proposal"]["reasons"]["cost"] = \
            "다른 비용"
    moved = doc_of(recost)
    b = row_of(moved, "k-a")
    equal("a changed Korean field moves the item's sha and not its English payload's",
          (a.get("item_sha") != b.get("item_sha"), a.get("payload_sha256") == b.get("payload_sha256")), (True, True))
    equal("the counts line is the rows' own", good["counts"]["candidates"],
          {"due_decision": 1, "formed": 7, "legacy": 5, "redundancy_hint": 2})

    # ---- the population, each member exactly once -----------------------------------------------------------------
    control("a rejected finding the rows lose is named (the population is S4's, the counts S4's)",
            "\n".join(population_problems([r for r in rows_of(base)[0] if r["item_id"] != "r-1"], rows_of(base)[1],
                                          base)), "RENDER_INCOMPLETE r-1")
    control("a failed item the rows lose is named",
            "\n".join(population_problems([r for r in rows_of(base)[0] if r["item_id"] != "k-e"], rows_of(base)[1],
                                          base)), "RENDER_INCOMPLETE k-e")
    control("a quarantined item the rows lose is named",
            "\n".join(population_problems([r for r in rows_of(base)[0] if r["item_id"] != "S3:w-3"], rows_of(base)[1],
                                          base)), "RENDER_INCOMPLETE S3:w-3")
    rows, appendix, _p = rows_of(base)
    control("a non-finding the appendix loses is named",
            "\n".join(population_problems(rows, {**appendix, "non_findings": appendix["non_findings"][1:]}, base)),
            "RENDER_INCOMPLETE e9")
    control("an eventless legacy candidate the rows lose is named",
            "\n".join(population_problems([dict(r, members=[m for m in r["members"] if m != "legacy:L-4"])
                                           for r in rows], appendix, base)), "RENDER_INCOMPLETE legacy:L-4")
    control("a pending intervention on a placed entry the rows lose is named",
            "\n".join(population_problems([r for r in rows if r["item_id"] != "due_decision:P-1@r1"], appendix, base)),
            "RENDER_INCOMPLETE due_decision:P-1@r1")
    control("a member shown twice is named", "\n".join(population_problems(rows + [rows[0]], appendix, base)),
            "RENDER_DUPLICATED")
    control("a proposal S7 made that the rows lose is caught: S7 neither proposed for it nor returned it",
            said(lambda d: d["proposals"].update(proposals=[p for p in d["proposals"]["proposals"]
                                                            if p["candidate_id"] != "k-a"])),
            "RENDER_INCOMPLETE k-a: admitted by S6, and S7 neither proposed")
    control("an item gone before S7 is still a row: the population, not proposals.json, makes the rows",
            ",".join(r["item_id"] for r in doc_of(lambda d: (d["proposals"].update(
                proposals=[p for p in d["proposals"]["proposals"] if p["candidate_id"] != "k-a"],
                returned=d["proposals"]["returned"] + [{"candidate_id": "k-a", "problems": ["ANSWER_ABSENT k-a"]}]),
                d["s7b"].update(reviews=[r for r in d["s7b"]["reviews"] if r["item_id"] != "k-a"])))
                     ["rows"]), "k-a")
    control("a proposal for a candidate neither in the population nor planted is named",
            said(lambda d: d["controls"].update(planted=[])), "PROPOSAL_UNACCOUNTED k-p")
    control("a candidate S6 judged and neither derived nor named not derived is named",
            said(lambda d: d["derivations"]["verdicts"].pop("k-c")), "RENDER_INCOMPLETE k-c: S6 judged it")
    control("a candidate S6 never judged, from a source it did not leave out, is named",
            said(lambda d: d["judge"]["population"]["left_out"].pop("redundancy_hint")),
            "RENDER_INCOMPLETE redundancy_hint:u1|u2")
    control("a legacy candidate whose entry the pinned ledger lacks is named",
            said(lambda d: d["ledger"]["entries"].pop()), "RENDER_INCOMPLETE legacy:L-5")

    # ---- the counts line ----------------------------------------------------------------------------------------
    control("a count of S4's edited by one diverges by name",
            said(lambda d: d["population"]["counts"].update(candidate_members=9)), "COUNTS_DIVERGE candidate_members")
    control("a non-finding reason count edited diverges", said(lambda d: d["population"]["counts"]["non_findings"]
                                                              .update(routine_step=2)), "COUNTS_DIVERGE non_findings")
    control("a source count edited diverges", said(lambda d: d["population"]["counts"]["candidates"].update(formed=8)),
            "COUNTS_DIVERGE candidates")
    control("a rejected-finding member count edited diverges",
            said(lambda d: d["population"]["counts"].update(rejected_finding_members=2)),
            "COUNTS_DIVERGE rejected_finding_members")
    control("S6's left-out count against the members the review shows unjudged",
            said(lambda d: d["judge"]["population"]["left_out"]["legacy"].update(count=4)),
            "COUNTS_DIVERGE left_out.legacy")

    # ---- every row a review row -----------------------------------------------------------------------------------
    control("a proposal without a falsifier is refused structurally",
            "\n".join(row_problems([dict(r, o6={k: v for k, v in r["o6"].items() if k != "falsifier"})
                                    for r in rows[:1]])), "ROW_FIELD_ABSENT")
    control("an empty O6 field is refused", "\n".join(row_problems([dict(r, o6={**r["o6"], "cost": " "}) for r in rows[:1]])),
            "ROW_FIELD_ABSENT")
    control("a blank test state is refused", "\n".join(row_problems([dict(r, test="") for r in rows[:1]])),
            "TEST_STATE_ABSENT")
    control("a row kind this module does not make is refused",
            "\n".join(row_problems([dict(r, row_kind="other") for r in rows[:1]])), "ROW_KIND_UNKNOWN")
    equal("the O6 fields are the propose schema's reasons, in its order", o6_fields(),
          ("what_happened", "proposal", "reason", "cost", "serves", "falsifier"))
    control("a row ranking cannot place is reported by ranking's own code, not placed by a guess",
            said(lambda d: d["derivations"]["verdicts"]["k-a"]["outcome"]["kind"].update(kind="sideways")),
            "RANK_REFUSED")

    # ---- the Markdown (K2b) --------------------------------------------------------------------------------------
    meta = {"version": 1, "run_id": "fx", "declaration": {"kind": "periodic", "posture": "production",
            "declaration_seq": 2, "window": {"start": "2026-10-01", "end": "2026-10-08", "tz": "UTC"},
            "question": "Which patterns?"}, "census": {}, "window_flags": None, "spent": {"S6": 1000},
            "resolutions": "없음", "rejection_share": "1 / 5", "controls": "기록 없음", "legacy_unexpected": []}
    def rendered(held, held_meta=None, locators=None):
        """render_text's page, or its refusal as text: a refused page fails the controls that read it by name instead
        of ending the suite."""
        try:
            return render_text(held, meta if held_meta is None else held_meta, {} if locators is None else locators)
        except Refused as exc:
            return f"REFUSED {exc}"
    text = rendered(good, meta, {"e9": "s1#3"}) if good["rows"] else ""
    clean("the render is a render owner_lines can copy", owner_lines.render_problems(text) if text else ["NO_ROWS"])

    def section(item_id, page=None):
        """The lines of one row's section of the page: from its heading to the next heading."""
        lines = (text if page is None else page).split("\n")
        start = next((n for n, line in enumerate(lines) if line.startswith("### ") and f"`{item_id}`" in line), None)
        if start is None:
            return []
        end = next((n for n in range(start + 1, len(lines)) if lines[n].startswith("#")), len(lines))
        return lines[start:end]
    equal("a disputed row states what its candidate says, in the candidate's own words, before anything said of it",
          [line for line in section("k-b") if line.startswith("- 후보 원문")],
          ["- 후보 원문 · 교훈: Quote the glob", "- 후보 원문 · 상황: An unquoted star", "- 후보 원문 · 행동: Quote it",
           "- 후보 원문 · 예외: Not in bash"])
    equal("a legacy entry's own row states the lesson the pinned ledger holds for it, and a rejected finding its text "
          "and S4's reason",
          ([line for line in section("r-1") if line.startswith("- 후보 원문")],
           [line for line in section("legacy:L-1") if line.startswith("- 후보 원문")]),
          (["- 후보 원문 · 발견: The timeout command is absent", "- 후보 원문 · 형성 단계의 거부 이유: One retry each time"],
           ["- 후보 원문 · 대장에 적힌 교훈: lesson of L-1"]))
    equal("each disputed requirement is followed by both judges' own reasons for it",
          [line for line in section("k-b") if "의 이유:" in line],
          ["  - 판정자 A의 이유: A says k-b is not bounded", "  - 판정자 B의 이유: B says k-b is not bounded",
           "  - 판정자 A의 이유: A agrees k-b is positioned", "  - 판정자 B의 이유: B agrees k-b is positioned"])
    equal("a rejected row names each requirement both judges marked unmet, with their reasons",
          [line for line in section("k-c") if "미충족으로 본" in line or "의 이유:" in line],
          ["- 함께 미충족으로 본 요구 사항: actionable", "  - 판정자 A의 이유: A says k-c is not actionable",
           "  - 판정자 B의 이유: B says k-c is not actionable"])
    appendix_at = text.find("### 행별 판정 기록과 관련 단위")

    def appendix_of(item_id):
        """The appendix lines under one row's id: from the line that names it to the next row's."""
        lines = text[appendix_at:].split("\n")
        start = next((n for n, line in enumerate(lines) if line == f"- `{item_id}`"), None)
        if start is None:
            return []
        end = next((n for n in range(start + 1, len(lines)) if lines[n].startswith("- `")), len(lines))
        return lines[start + 1:end]
    judged_rows = [r["item_id"] for r in good["rows"] if r.get("judges")]
    lost = [f"{cid}/{who}: {field}" for cid in judged_rows for who in JUDGES
            for field in ("unit", "quote", "arises", "ev-n", "ev-c", "relation")
            if sum(f"{field} {cid}/{who}" in line for line in appendix_of(cid)) != 1]
    equal("everything a judge wrote for a row is on exactly one line of the appendix under that row's id: each "
          "unit comparison with its quote, whether the situation still arises, the matched units and the ledger "
          "relations, for every judged row and both judges",
          (len(judged_rows) >= 5, lost), (True, []))
    equal("each comparison names the unit it is of, as S6 stores it: the whole comparison line of every judged row "
          "and judge, both units with their own marks, reason and quote",
          ({(cid, who): [line for line in appendix_of(cid) if line.startswith(f"  - 판정자 {who} · 단위 비교: ")]
            for cid in judged_rows for who in JUDGES},
           len(judged_rows) >= 5, "None 상황" in text),
          ({(cid, who): [f"  - 판정자 {who} · 단위 비교: u-9 상황 yes 행동 no: r; "
                         f"u-8 상황 no 행동 no: unit {cid}/{who} (인용: quote {cid}/{who})"]
            for cid in ("k-a", "k-b", "k-c", "k-d", "k-g", "due_decision:P-1@r1", "k-p")
            for who in ("A", "B") if cid in judged_rows}, True, False))
    equal("an S7b alternative that changes nothing prints no destination, whatever its answer wrote beside it",
          [line.split(" · ")[1] for line in s7b_lines({
              "state": "reviewed", "verdict": "disagree", "disposition_holds": False, "destination_holds": True,
              "faithful_merge": "n/a", "bars_failing": [], "owner_resolves": True, "notes": "n",
              "alternative": {"disposition": "none", "reason": "r",
                              "destination": {"layer": "guides", "carrier": "claude/guides/a.md"}}})
           if line.startswith("- S7b 대안")], ["위치 -/-"])
    old_frozen = {"disposition": "none", "destination": {"layer": "ledger", "carrier": None}, "x": 1}
    equal("a `none` frozen with the layer its answer wrote is the same material as that proposal read now, and a "
          "changed disposition or a changed destination of any other proposal is not",
          [same_material({**old_frozen, "destination": None}, old_frozen),
           same_material({**old_frozen, "disposition": "keep"}, old_frozen),
           same_material({"disposition": "keep", "destination": {"layer": "guides", "carrier": "a"}},
                         {"disposition": "keep", "destination": {"layer": "guides", "carrier": "b"}})],
          [True, False, False])
    equal("and the row itself holds the counts, not the comparisons: two per judge, and one related unit",
          ([line.rsplit("; ", 1)[-1] for line in section("k-a") if line.startswith("- 판정자")],
           [line for line in section("k-a") if line.startswith("- 관련 단위")],
           [cid for cid in judged_rows if any("unit " + cid in line for line in section(cid))],
           "u-9 (전달 증거: delivery_assembly_waiting)" in "\n".join(appendix_of("k-a"))),
          (["단위 비교 2개는 부록에 있습니다", "단위 비교 2개는 부록에 있습니다"], ["- 관련 단위: 1개 (부록의 `k-a`)"], [], True))
    equal("a reason for a requirement both judges marked met is in the appendix and not in the row",
          ([who for who in JUDGES if sum(f"actionable=met: {who} agrees k-b is actionable" in line
                                         for line in appendix_of("k-b")) == 1],
           any("agrees k-b is actionable" in line for line in section("k-b"))), (["A", "B"], False))
    equal("a `none` prints no destination, whatever layer its answer wrote beside it, and any other disposition its own",
          [proposal_lines({"disposition": "none", "destination": {"layer": "ledger", "carrier": None}})[0],
           proposal_lines({"disposition": "keep", "destination": {"layer": "incubator", "carrier": None}})[0]],
          ["- 대상: 없음 (바꾸지 않는 제안은 대상을 갖지 않습니다)", "- 대상: layer incubator, carrier None"])
    equal("a candidate with no text of its own says so on its row instead of printing no subject",
          sorted({(r["source"], r["subject"][0]["part"]) for r in good["rows"]
                  if r["row_kind"] == "candidate" and r["subject"] and r["subject"][0]["part"] == "no_source"})[:1]
          + [[r["item_id"] for r in good["rows"] if r["row_kind"] in ("candidate", "legacy") and not r["subject"]]],
          [("formed", "no_source"), []])
    equal("a due decision's row states the lesson of the entry it is about",
          [line for line in section("due_decision:P-1@r1") if line.startswith("- 후보 원문")],
          ["- 후보 원문 · 대장에 적힌 교훈: lesson of L-5"])
    try:   # a render copy_of refuses is this section's controls failing by name, not the suite dying
        owner_copy = owner_lines.copy_of(text, "review.ko.v1.md") if text else ""
    except Refused as exc:
        owner_copy, text = "", f"COPY_REFUSED {exc}\n{text}"
    parsed, probs = owner_lines.parse(text, owner_copy, spec=spec_of(good), render_name="review.ko.v1.md") if text \
        else (None, ["NO_ROWS"])
    clean("its unedited copy parses against the rows' spec with nothing refused", probs)
    items = (parsed or {"items": []})["items"]
    equal("and every row is undecided", sorted({i["state"] for i in items}), ["undecided"])
    equal("one owner block per row, in the rows' order", [i["item_id"] for i in items],
          [r["item_id"] for r in good["rows"]])
    equal("the same documents render the same bytes", rendered(doc_of(), meta, {"e9": "s1#3"}) if text else None,
          text or "(no rows)")
    equal("every §9 group in ranking's table has a title here", sorted(GROUP_TITLES),
          sorted(g["id"] for g in ranking.table()["groups"]))
    control("the header names the §7.5 fallback", text, FALLBACK)
    equal("the header names ranking's keys in the table's order, the judges' and S7b's parts among them",
          list(KEY_TITLES), [k["id"] for k in ranking.table()["keys"]])

    # S7b's key (lane L's 5851e09): k-g, which S7b disagreed with and left to the owner, moves ahead of
    # due_decision:P-1@r1, which ties it on group, consequence and lineages and has no S7b review; neither order is the
    # id order (due_decision < k-a < k-g)
    def proposed_order(page):
        return [line.split("`")[1] for line in page.split("\n")
                if line.startswith("### ") and "`" in line and line.split("`")[1] in ("k-a", "k-g", "due_decision:P-1@r1")]
    agreed = doc_of(lambda d: next(r for r in d["s7b"]["reviews"] if r["item_id"] == "k-g").update(
        owner_resolves=False))
    equal("a row S7b leaves to the owner is rendered ahead of a tie with no S7b review; without that the old order",
          (proposed_order(text), proposed_order(rendered(agreed))),
          (["k-a", "k-g", "due_decision:P-1@r1"], ["k-a", "due_decision:P-1@r1", "k-g"]))
    held_keys = ranking.table()["keys"]
    kept_keys = list(held_keys)
    held_keys[:] = [k for k in held_keys if k["id"] != "owner_resolves"]
    try:
        unkeyed = doc_of()
    finally:
        held_keys[:] = kept_keys
    equal("a reorder alone changes no item's sha: the same rows ranked without S7b's key differ only in rank",
          ([r["item_id"] for r in unkeyed["rows"]] != [r["item_id"] for r in good["rows"]],
           {r["item_id"]: (r["item_sha"], r["payload_sha256"]) for r in unkeyed["rows"]}
           == {r["item_id"]: (r["item_sha"], r["payload_sha256"]) for r in good["rows"]},
           any(ORDER_ONLY in r for r in good["rows"])), (True, True, False))
    control("§13's measures are named as not yet produced", text, "§13 측정: 아직 없음")
    equal("every row shows the test state", text.count("- 시험: untested: s8_deferred"), len(good["rows"]) or -1)
    equal("every row shows S7b's state", sum(1 for line in text.split("\n") if line.startswith("- S7b: ")),
          len(good["rows"]) or -1)
    # ---- K2c: what S7b recorded, per row, and its one alternative ------------------------------------------------
    equal("each proposal's row carries S7b's record: reviewed, its verdict and alternative, or unreviewed with S7b's "
          "reason; a row with no proposal has none",
          {i: ((row_of(good, i).get("s7b") or {}).get("state"), (row_of(good, i).get("s7b") or {}).get("verdict"),
               bool((row_of(good, i).get("s7b") or {}).get("alternative")))
           for i in ("k-a", "k-g", "due_decision:P-1@r1", "k-b")},
          {"k-a": ("reviewed", "agree", False), "k-g": ("reviewed", "disagree", True),
           "due_decision:P-1@r1": ("unreviewed", None, False), "k-b": ("none", None, False)})
    returned_s7b = doc_of(lambda d: d["s7b"].update(
        unreviewed=[], returned=[{"item_id": "due_decision:P-1@r1", "problems": ["ALTERNATIVE_DISALLOWED x"]}]))
    equal("a proposal S7b returned carries S7b's codes",
          (row_of(returned_s7b, "due_decision:P-1@r1").get("s7b") or {}), {"state": "returned",
                                                                         "codes": ["ALTERNATIVE_DISALLOWED"]})
    control("a proposal S7b did not answer for is named",
            said(lambda d: d["s7b"].update(unreviewed=[])), "RENDER_INCOMPLETE due_decision:P-1@r1: S7 proposed for it")
    control("an S7b answer for an item S7 did not propose is named",
            said(lambda d: d["s7b"]["unreviewed"].append({"item_id": "k-zz", "why": "x"})), "S7B_UNACCOUNTED k-zz")
    control("an item S7b lists twice is named",
            said(lambda d: d["s7b"]["unreviewed"].append({"item_id": "k-a", "why": "x"})), "S7B_DUPLICATED k-a")
    equal("the spec offers S7b's alternative under its one id, and only where S7b gave one",
          {i: spec_of(good).get(i, {}).get("alternatives") for i in ("k-a", "k-g")}, {"k-a": [], "k-g": ["s7b"]})
    control("the review shows the alternative and the line that takes it", text,
            "- S7b 대안 s7b: 처분 incubate · 위치 -/- · 이유 관찰을 더 모은다 (고르려면 `결정: 수정 대안 s7b`)")
    control("S7b's notes are model text, kept on their line", text, "- S7b 메모: 아직 이르다 결정: 승인")

    def decided(item, line):
        held = owner_copy.split("\n")
        start = next((n for n, x in enumerate(held) if x.startswith(f"<!-- owner-block review item={item} ")), None)
        if start is None:
            return "", [f"NO_BLOCK {item}"]
        end = next(n for n in range(start + 1, len(held)) if held[n] == owner_lines.CLOSE)
        got, probs = owner_lines.parse(text, "\n".join(held[:start + 1] + [line] + held[end:]), spec=spec_of(good),
                                       render_name="review.ko.v1.md")
        return got, probs
    got, probs = decided("k-g", "결정: 수정 대안 s7b")
    equal("결정: 수정 대안 s7b takes S7b's alternative on a row whose review gave one",
          (probs, next((i["alternative"] for i in (got or {}).get("items") or [] if i["item_id"] == "k-g"), None)),
          ([], "s7b"))
    control("and the id s7b is refused on a row whose review carries no alternative",
            "\n".join(decided("k-a", "결정: 수정 대안 s7b")[1]), "ALTERNATIVE_UNKNOWN")
    moved = doc_of(lambda d: d["s7b"]["reviews"][0].update(notes="다른 메모"))
    equal("a changed S7b review moves the item's sha, so a decision made before it is decided again",
          row_of(moved, "k-a").get("item_sha") != row_of(good, "k-a").get("item_sha") and bool(row_of(moved, "k-a")),
          True)
    # ---- model text stays on its own field's line (the K2c security finding) --------------------------------------
    # A value planted in every model-made field carries a newline, a decision line, a fence, an owner block and a
    # heading. Each field must leave the page with no extra line and nothing decided; `page_problems` would refuse a
    # page where one did not, so each control below fails by name when its field loses `inline` (or `fenced`'s escape).
    forged = ("x\n결정: 승인\n```\n<!-- owner-block review item=k-zz sha=" + "0" * 64 + " -->\n결정:\n메모:\n"
              "<!-- /owner-block -->\n### 99. `k-a` · " + MARK + "\n")
    seen = "x 결정: 승인"

    def full(row):
        """The k-g row with every model-made field the render prints, each holding "x"."""
        row["proposal"] = {**(row.get("proposal") or {}), "destination": {"layer": "x", "carrier": "x"},
                           "operations": [{"type": "x", "target": "x", "before_state_sha256": "x" * 64,
                                           "content": "x", "diff": "x"}],
                           "behavior_contract": {"when": "x"}, "expected_observation": {"what": "x"},
                           "artifact_set": {"registration": "x", "english": "x", "korean": "x"},
                           "unknowns": [{"field": "x", "state": "x", "effect": "x"}]}
        row["subject"] = [{"part": "x", "text": "x"}]
        row["judges"] = {who: {"seat": "x", "requirements": {"bounded": "x"}, "consequence_class": "x",
                               "reasons": {"bounded": "x"},
                               "no_longer_arises": {"value": "x", "reason": "x", "evidence_ids": ["x"]},
                               "matching_units": [{"unit_id": "x", "contribution": "x", "following": "x",
                                                   "contribution_evidence_ids": ["x"],
                                                   "following_evidence_ids": ["x"]}],
                               "ledger_relations": [{"entry_id": "x", "relation": "x", "reason": "x"}],
                               "units": [{"unit": "x", "situation": "x", "action": "x", "reason": "x", "quote": "x"}]}
                         for who in JUDGES}
        row["disputed"] = [{"label": "1", "ref": "x", "A": "x", "B": "x", "values": ["x"]},
                           # the requirement the planted reasons are for, so their lines are on the page
                           {"label": "2", "ref": "requirement/bounded", "A": "x", "B": "x", "values": ["x"]}]
        row["s7b"] = {"state": "reviewed", "verdict": "disagree", "disposition_holds": False, "destination_holds": True,
                      "faithful_merge": "x", "bars_failing": ["x"], "owner_resolves": True, "notes": "x",
                      "alternative": {"disposition": "x", "destination": {"layer": "x", "carrier": "x"}, "reason": "x"}}
        row["failure"] = {"stage": "x", "codes": ["x"]}
        row["units"] = [{"unit_id": "x", "delivery": "x"}]
        row["events"] = ["x"]
        for name in ("kind", "diagnosis", "disposition", "consequence", "lineages"):
            row[name] = "x"

    def at(*path):
        def plant(row, value):
            held = row
            for key in path[:-1]:
                held = held[key]
            held[path[-1]] = value
        return plant

    def key_of(*path):
        def plant(row, value):
            held = row
            for key in path:
                held = held[key]
            held[value] = held.pop(next(iter(held)))
        return plant

    def state(name, **fields):
        def plant(row, value):
            row[name] = {k: (value if v is None else [value] if v == [None] else v) for k, v in fields.items()}
        return plant
    inline_plants = [("the status line's kind", at("kind")), ("the status line's diagnosis", at("diagnosis")),
                     ("the status line's disposition", at("disposition")),
                     ("the status line's consequence", at("consequence")),
                     ("the status line's lineages", at("lineages")),
                     *[(f"O6 field {name}", at("o6", name)) for name in o6_fields()],
                     ("a subject's text", at("subject", 0, "text")),
                     ("a subject's part", at("subject", 0, "part")),
                     ("a judge's reason for a disputed requirement", at("judges", "A", "reasons", "bounded")),
                     ("a judge's seat", at("judges", "A", "seat")),
                     ("a judge's requirement name", key_of("judges", "A", "requirements")),
                     ("a judge's requirement mark", at("judges", "A", "requirements", "bounded")),
                     ("a judge's consequence class", at("judges", "A", "consequence_class")),
                     ("a judged unit's id", at("judges", "A", "units", 0, "unit")),
                     ("a judged unit's situation", at("judges", "A", "units", 0, "situation")),
                     ("a judged unit's action", at("judges", "A", "units", 0, "action")),
                     ("a judged unit's reason", at("judges", "A", "units", 0, "reason")),
                     ("a judged unit's quote", at("judges", "A", "units", 0, "quote")),
                     ("a judge's reason on whether it still arises", at("judges", "A", "no_longer_arises", "reason")),
                     ("a judge's evidence on whether it still arises", at("judges", "A", "no_longer_arises", "evidence_ids", 0)),
                     ("a matched unit's id", at("judges", "A", "matching_units", 0, "unit_id")),
                     ("a matched unit's contribution", at("judges", "A", "matching_units", 0, "contribution")),
                     ("a matched unit's evidence", at("judges", "A", "matching_units", 0, "contribution_evidence_ids", 0)),
                     ("a ledger relation's entry", at("judges", "A", "ledger_relations", 0, "entry_id")),
                     ("a ledger relation's reason", at("judges", "A", "ledger_relations", 0, "reason")),
                     ("a disputed judgment's reference", at("disputed", 0, "ref")),
                     ("a disputed judgment's side A", at("disputed", 0, "A")),
                     ("a disputed judgment's side B", at("disputed", 0, "B")),
                     ("a disputed judgment's own value", at("disputed", 0, "values", 0)),
                     ("the proposal's destination layer", at("proposal", "destination", "layer")),
                     ("the proposal's destination carrier", at("proposal", "destination", "carrier")),
                     ("an operation's type", at("proposal", "operations", 0, "type")),
                     ("an operation's target", at("proposal", "operations", 0, "target")),
                     ("an operation's before-state hash", at("proposal", "operations", 0, "before_state_sha256")),
                     ("a behavior contract's key", key_of("proposal", "behavior_contract")),
                     ("a behavior contract's value", at("proposal", "behavior_contract", "when")),
                     ("an expected observation's key", key_of("proposal", "expected_observation")),
                     ("an expected observation's value", at("proposal", "expected_observation", "what")),
                     ("the artifact registration", at("proposal", "artifact_set", "registration")),
                     ("an unknown's field", at("proposal", "unknowns", 0, "field")),
                     ("an unknown's state", at("proposal", "unknowns", 0, "state")),
                     ("an unknown's effect", at("proposal", "unknowns", 0, "effect")),
                     ("S7b's merge answer", at("s7b", "faithful_merge")),
                     ("S7b's failing bar", at("s7b", "bars_failing", 0)),
                     ("S7b's notes", at("s7b", "notes")),
                     ("S7b's alternative disposition", at("s7b", "alternative", "disposition")),
                     ("S7b's alternative layer", at("s7b", "alternative", "destination", "layer")),
                     ("S7b's alternative carrier", at("s7b", "alternative", "destination", "carrier")),
                     ("S7b's alternative reason", at("s7b", "alternative", "reason")),
                     ("S7b's returned code", state("s7b", state="returned", codes=[None])),
                     ("S7b's unreviewed reason", state("s7b", state="unreviewed", why=None)),
                     ("S9b's notes on a marked row", state("s9b", state="marked", mark=True, notes=None)),
                     ("S9b's returned code", state("s9b", state="returned", mark=False, codes=[None])),
                     ("S9b's unreviewed reason", state("s9b", state="unreviewed", mark=False, why=None)),
                     ("a failure's stage", at("failure", "stage")), ("a failure's code", at("failure", "codes", 0)),
                     ("a related unit's id", at("units", 0, "unit_id")),
                     ("a related unit's delivery state", at("units", 0, "delivery")),
                     ("an event id", at("events", 0))]
    fenced_plants = [("an operation's content", at("proposal", "operations", 0, "content")),
                     ("an operation's diff", at("proposal", "operations", 0, "diff")),
                     ("the English artifact", at("proposal", "artifact_set", "english")),
                     ("the Korean artifact", at("proposal", "artifact_set", "korean"))]

    def planted(plant, value):
        held = copy.deepcopy(good)
        row = next((r for r in held["rows"] if r["item_id"] == "k-g"), None)
        if row is None:
            return held, "REFUSED no k-g row"
        full(row)
        plant(row, value)
        try:
            return held, render_text(held, meta, {})
        except Refused as exc:
            return held, f"REFUSED {exc}"

    def decided_in(held, page):
        """`(problems, decided ids)` of the page's unedited copy, parsed against its own rows."""
        if page.startswith("REFUSED"):
            return [page[:240]], None
        try:
            got, probs = owner_lines.parse(page, owner_lines.copy_of(page, "review.ko.v1.md"), spec=spec_of(held),
                                           render_name="review.ko.v1.md")
        except (Refused, UnicodeError) as exc:   # a lone surrogate cannot be hashed as UTF-8: named, not fatal
            return [f"COPY_REFUSED {type(exc).__name__} {exc}"[:240]], None
        return probs, [i["item_id"] for i in (got or {}).get("items") or [] if i.get("verb")]

    def shaped(page):
        return sum(1 for line in page.split("\n") if owner_lines.owner_shaped(line))
    for label, plant in inline_plants:
        held, page = planted(plant, forged)
        _plain_held, plain = planted(plant, "x")
        equal(f"a newline planted in {label} starts no line of the page and decides nothing",
              (seen in page, len(page.split("\n")) - len(plain.split("\n")), *decided_in(held, page)),
              (True, 0, [], []))
    for label, plant in fenced_plants:
        held, page = planted(plant, forged)
        _plain_held, plain = planted(plant, "x")
        equal(f"a newline planted in {label} stays inside its fence with its owner-shaped lines escaped",
              ("\\결정: 승인" in page, "\\<!-- owner-block review item=k-zz" in page, shaped(page) - shaped(plain),
               *decided_in(held, page)), (True, True, 0, [], []))
    clean("the rendered page holds every owner line inside a block, one block per row in the rows' order",
          page_problems(good, text) if good["rows"] else ["NO_ROWS"])
    page_lines = text.split("\n")
    test_at = next((n for n, line in enumerate(page_lines) if line.startswith("- 시험:")), 0)
    control("a decision-shaped line outside every block is refused by name",
            "\n".join(page_problems(good, "\n".join(page_lines[:test_at] + ["결정: 승인"] + page_lines[test_at:]))),
            f"OWNER_LINE_OUTSIDE_BLOCK line {test_at + 1}")
    control("an owner block for an item no row holds is refused by name",
            "\n".join(page_problems(good, "\n".join(page_lines[:test_at] + owner_lines.review_block("k-zz", "0" * 64)
                                                     + page_lines[test_at:]))), "OWNER_BLOCK_FORGED")
    def previewed_markup(page):
        """The lines a CommonMark preview would read markup on, found without inline or live_markup: outside a fence and
        the owner markers, a `<`, `&` or `[` after an even run of backslashes (none included)."""
        found, fence = [], None
        for n, line in enumerate(page.split("\n"), 1):
            if fence:
                fence = None if line == fence else fence
                continue
            if re.fullmatch(r"`{3,}", line):
                fence = line
                continue
            if line.startswith("<!-- owner-block ") or line == "<!-- /owner-block -->":
                continue
            if re.search(r"(?<!\\)(?:\\\\)*[<&\[]", line):
                found.append(n)
        return found
    clean("the rendered page has no markup a preview would read outside its fences",
          previewed_markup(text) if good["rows"] else ["NO_ROWS"])
    markup_plants = ["\\<!-- x -->", "\\\\<!-- x -->", "<details><summary>s</summary>x</details>",
                     "<span hidden>x</span>", '<div style="display:none">', "&lt;b&gt; &#x202E;",
                     '[ok](x "hidden title")', "![i](x)"]
    for label, plant in inline_plants:
        live = []
        for value in markup_plants:
            _held, page = planted(plant, value)
            if page.startswith("REFUSED") or previewed_markup(page):
                live.append(value if not page.startswith("REFUSED") else f"{value}: {page[:160]}")
        equal(f"markup planted in {label} is shown as typed", live, [])
    # blank-looking characters of an allowed category, named rather than listed: no code point is copied from
    # BLANK_LOOKALIKES, so the derived set is held to the database's own names
    def looks_blank(c):
        name = unicodedata.name(c, "")
        return (("HANGUL" in name and "FILLER" in name) or "VARIATION SELECTOR" in name
                or name in ("BRAILLE PATTERN BLANK", "COMBINING GRAPHEME JOINER", "KHMER VOWEL INHERENT AQ",
                            "KHMER VOWEL INHERENT AA"))

    def unseen(page, tabs_in_fences=False):
        """Every character of `page` a reader would not see as itself, found without unshown, visible or
        invisible_in: anything but a letter, number, punctuation mark, symbol or plain space, a mark with no seen
        base, and a blank-looking character; a line break is the page's own, and so (when asked) is a tab on a line
        inside a fence."""
        found, fence = [], None
        for line in page.split("\n"):
            inside = fence is not None and line != fence
            if fence is None and re.fullmatch(r"`{3,}", line):
                fence = line
            elif fence is not None and line == fence:
                fence = None
            seen_base = False
            for c in line:
                kind = unicodedata.category(c)
                ok = c == " " or (c == "\t" and tabs_in_fences and inside) or (not looks_blank(c) and (
                    kind[0] in ("L", "N", "P", "S") or (kind in ("Mn", "Mc") and seen_base)))
                seen_base = ok and c not in " \t"
                if not ok:
                    found.append(f"U+{ord(c):04X}")
        return found
    equal("the derived blank-lookalike set is every character the database names a Hangul filler, a variation "
          "selector, the braille blank, the grapheme joiner or an invisible Khmer inherent vowel",
          sorted(BLANK_LOOKALIKES), [c for c in range(0x110000) if looks_blank(chr(c))])

    def within(cp, ranges):
        return any(lo <= cp <= hi for lo, hi in ranges)
    equal("the copied Default_Ignorable_Code_Point holds what its derivation puts there: every format character but "
          "the excluded ones, and every character the database names a variation selector",
          ([f"U+{c:04X}" for c in range(0x110000) if unicodedata.category(chr(c)) == "Cf"
            and not within(c, DI_FORMAT_EXCLUDED) and not within(c, DEFAULT_IGNORABLE)],
           [f"U+{c:04X}" for c in range(0x110000) if "VARIATION SELECTOR" in unicodedata.name(chr(c), "")
            and not within(c, DEFAULT_IGNORABLE)],
           [f"U+{c:04X}" for c in range(0x110000) if within(c, DI_FORMAT_EXCLUDED) and within(c, DEFAULT_IGNORABLE)]),
          ([], [], []))
    equal("every default-ignorable code point is written in notation, after a letter as alone",
          [f"U+{c:04X}" for lo, hi in DEFAULT_IGNORABLE for c in range(lo, hi + 1)
           if not (invisible_in(chr(c)) == [chr(c)] and invisible_in("a" + chr(c)) == [chr(c)])], [])
    unseen_plant = ("x\u202ey\u202a\u2066\u2069\u200b\u200c\u200d\u2060\ufeff\u061c\u200e\u200f\x00\x07\x1b\x7f\x9b"
                    "\u00ad\U000e0001\ud800\u115f\u1160\u3164\uffa0\u2800\u034f\ufe0f\U000e0100\u180b\u17b4"
                    "\u0378\ue000\U000f0000\u00a0\u3000\u2028\u0301\u20dd \\u202E z")
    clean("the rendered page holds no character a reader would not see as itself", unseen(text) if good["rows"]
          else ["NO_ROWS"])
    for label, plant in inline_plants:
        _held, page = planted(plant, unseen_plant)
        equal(f"an invisible character planted in {label} is shown in visible notation",
              (page.startswith("REFUSED") and page[:160], unseen(page), "\\u202E" in page), (False, [], True))
    _held, page = planted(at("s7b", "alternative", "destination", "carrier"), "x\u202ey \\u202E z \u3164 e\u0301")
    control("a backslash and u a model wrote shows doubled, so it cannot pass for the notation; a filler is shown, "
            "a mark on its letter kept", page, "x\\u202Ey \\\\u202E z \\u3164 e\u0301")
    for label, plant in fenced_plants:
        held, page = planted(plant, "a\tb\n" + unseen_plant)
        lines_ = page.split("\n")
        equal(f"an invisible character planted in {label} is shown in visible notation, a tab kept, each one named",
              (unseen(page, tabs_in_fences=True), "a\tb" in lines_,
               any(line.startswith("- 위 펜스 안에서 보이지 않거나") and "2번째 줄" in line and "U+202E" in line
                   for line in lines_), *decided_in(held, page)), ([], True, True, [], []))
    # more than twenty lines, each with a real replaced character, and the notation imitated on line 23: the page
    # tells them apart by the backslash run before each, and its note names every line
    long_content = "\n".join(f"line {n} \u202e" + (" \\u202E" if n == 23 else " \\\u202e" if n == 24 else "")
                             for n in range(1, 26))
    held, page = planted(at("proposal", "operations", 0, "content"), long_content)
    lines_ = page.split("\n")
    runs = [[len(m.group(1)) % 2 for m in re.finditer(r"(\\+)u202E", line)] for line in lines_
            if re.match(r"line \d+ \\", line)]
    note = next((line for line in lines_ if line.startswith("- 위 펜스 안에서 보이지 않거나")), "")
    equal("past line twenty a replaced character and an imitation of its notation still look different, and the note "
          "names every line",
          (len(runs), runs[22:24], all(r == [1] for i, r in enumerate(runs) if i not in (22, 23)),
           all(f"{n}번째 줄 U+202E" in note for n in range(1, 26)), "원문의 백슬래시 2개는 모두 두 개씩" in note),
          (25, [[1, 0], [1, 1]], True, True, True))
    # a file's own backslashes, with no replaced character and no notation-shaped text near them, are doubled too, so
    # the reading of a run never depends on what follows it
    held, page = planted(at("proposal", "operations", 0, "content"), "re a\\d+ \\\\ b")
    lines_ = page.split("\n")
    note = next((line for line in lines_ if line.startswith("- 위 펜스 안에서")), "")
    equal("inside a fence every backslash of the file is shown doubled, and the note says so",
          ("re a\\\\d+ \\\\\\\\ b" in lines_, "원문의 백슬래시 3개는 모두 두 개씩" in note, "\\uXXXX 표기로" in note),
          (True, True, False))
    tricky = 'a\n``````\n~~~~~~~\n<div style="display:none">\n&lt;x&gt; [l](u "t")'
    for label, plant in fenced_plants:
        held, page = planted(plant, tricky)
        lines_ = page.split("\n")
        _held, separated = planted(plant, "y\u2028메모: 숨김\u0085결정: 승인")
        equal(f"a line separator planted in {label} makes a line of its own, escaped like any other",
              ("\\메모: 숨김" in separated.split("\n"), "\\결정: 승인" in separated.split("\n")), (True, True))
        equal(f"raw markup planted in {label} is inert inside a fence no backtick or tilde run in it can close",
              (previewed_markup(page), "`" * 7 in lines_, '<div style="display:none">' in lines_,
               *decided_in(held, page)), ([], True, True, [], []))
    kept_inline = globals()["inline"]
    globals()["inline"] = str   # every field as if it had lost `inline`: the page must be refused, not written
    try:
        _held, unguarded = planted(at("s7b", "alternative", "destination", "carrier"), forged)
    finally:
        globals()["inline"] = kept_inline
    control("a page whose fields lost inline is refused by render_text itself, not written", unguarded,
            "OWNER_LINE_OUTSIDE_BLOCK line")
    globals()["inline"] = str
    try:
        _held, unescaped = planted(at("s7b", "alternative", "destination", "carrier"), "<span hidden>x</span>")
    finally:
        globals()["inline"] = kept_inline
    control("and so is one whose field lost inline's markup escape, by name", unescaped, "MARKUP_LIVE line")
    globals()["inline"] = str
    try:
        _held, unshown = planted(at("s7b", "alternative", "destination", "carrier"), "x\u202Ey")
    finally:
        globals()["inline"] = kept_inline
    control("and so is one whose field lost inline's visible notation, by name", unshown, "INVISIBLE_CHARACTER line")
    control("an invisible character on a line of the page is refused by name",
            "\n".join(page_problems(good, "\n".join(page_lines[:test_at] + ["- x \u202ey"] + page_lines[test_at:]))),
            f"INVISIBLE_CHARACTER line {test_at + 1}: U+202E")
    equal("a tab is a file's own character inside a fence, and refused outside one",
          (page_problems(good, "\n".join(page_lines[:test_at] + ["```", "\tx", "```"] + page_lines[test_at:])),
           bool(page_problems(good, "\n".join(page_lines[:test_at] + ["- \tx"] + page_lines[test_at:])))), ([], True))
    control("a line outside every fence holding markup a preview would read is refused by name",
            "\n".join(page_problems(good, "\n".join(page_lines[:test_at] + ["- x <span hidden>y</span>"]
                                                     + page_lines[test_at:]))), f"MARKUP_LIVE line {test_at + 1}")
    equal("a markup character after an even run of backslashes is live, after an odd run escaped",
          [bool(page_problems(good, "\n".join(page_lines[:test_at] + [f"- x {'\\' * n}<span hidden>y"]
                                               + page_lines[test_at:]))) for n in (0, 1, 2, 3, 4)],
          [True, False, True, False, True])
    clean("and inside a fence the same line is inert, so it is not",
          page_problems(good, "\n".join(page_lines[:test_at] + ["```", "<span hidden>y</span>", "```"]
                                        + page_lines[test_at:])))
    control("owner_shaped reads a line as the parser does: NFC and stripped",
            str([owner_lines.owner_shaped(s) for s in (" 결정: 승인", unicodedata.normalize("NFD", "메모: x"),
                                                         "  <!-- /owner-block -->", "- 결정: 승인", "\\결정: 승인")]),
            "[True, True, True, False, False]")

    # ---- K4b: S9b's regenerated Korean and its marks, overlaid in stage order (decision (a)) ---------------------
    from runlib import stage_review_korean as s9b_stage

    def s9b_verdict(failing=()):
        return {"verdict": "fail" if failing else "pass", "notes": "예외를 빠뜨렸다" if failing else "그대로다",
                "fields": [{"field": f, "faithful": f not in failing, "plain": True, "finding": "f"}
                           for f in s9b_stage.FIELDS]}
    base_docs = fixture_docs()
    unlaid = document(base_docs)
    answer_kg = next(p["proposal"] for p in base_docs["proposals"]["proposals"] if p["candidate_id"] == "k-g")
    better = {**copy.deepcopy(answer_kg), "reasons": {**answer_kg["reasons"], "what_happened": "다시 쓴 무엇이 있었나"}}
    s9b_review, s9b_regen, s9b_probs = s9b_stage.document(
        {"version": 1, "render_sha256": "r" * 64, "rows": unlaid["rows"]}, base_docs["proposals"],
        base_docs["candidates"], base_docs["derivations"],
        {"k-a": s9b_verdict(["cost"]), "k-g": s9b_verdict(["what_happened"]), "due_decision:P-1@r1": s9b_verdict()},
        {"k-g": better}, {"k-g": s9b_verdict()})

    def overlaid(edit=None):
        held = {**copy.deepcopy(base_docs), "s9b_review": copy.deepcopy(s9b_review),
                "s9b_regenerated": copy.deepcopy(s9b_regen)}
        if edit:
            edit(held)
        return document(held)
    over = overlaid()
    clean("S9b's review and regenerated proposals overlay S7's with nothing refused", s9b_probs + over["problems"])
    # Codex WP-20 r2 F1: a verdict is shown only beside the text it judged. The regenerated row's verdict binds the
    # regenerated Korean; without the regenerated proposals laid over S7's, the row shows S7's original Korean, so its
    # verdict is not shown as a pass
    bare = overlaid(lambda d: d.update(s9b_regenerated={"stage": "S9b", "version": 1, "proposals": {}}))
    equal("a verdict on regenerated Korean shown beside S7's original is not shown as passed, and marks nothing",
          ((row_of(bare, "k-g").get("s9b") or {}).get("state"), (row_of(bare, "k-g").get("s9b") or {}).get("why"),
           (row_of(over, "k-g").get("s9b") or {}).get("state")), ("not_yet", S9B_UNBOUND, "regenerated"))
    english_moved_s9b = overlaid(lambda d: next(r for r in d["s9b_review"]["rows"] if r["item_id"] == "k-a")
                                 .update(payload_sha256="e" * 64))
    equal("nor one given on another English payload, whose mark then marks nothing it shows",
          ((row_of(english_moved_s9b, "k-a").get("s9b") or {}).get("state"), english_moved_s9b.get("marked"),
           over.get("marked")), ("not_yet", [], ["k-a"]))
    equal("a regenerated row shows its new Korean over the same English payload, and its sha moves",
          ((row_of(over, "k-g").get("o6") or {}).get("what_happened"),
           row_of(over, "k-g").get("payload_sha256") == row_of(unlaid, "k-g").get("payload_sha256"),
           row_of(over, "k-g").get("item_sha") != row_of(unlaid, "k-g").get("item_sha")),
          ("다시 쓴 무엇이 있었나", True, True))
    equal("each proposal's row carries S9b's state, and no other row does",
          {r["item_id"]: (r.get("s9b") or {}).get("state") for r in over["rows"] if "s9b" in r},
          {"k-a": "marked", "k-g": "regenerated", "due_decision:P-1@r1": "passed"})
    try:
        over_text = render_text(over, meta, {})
    except Refused as exc:  # a heading that lost its mark is refused by render_text itself; the controls below name it
        over_text = str(exc)
    control("a marked row says so in its heading", over_text, f"`k-a` · {MARK}")
    control("and a regenerated row says it was rewritten once", over_text, "- S9b: 한국어를 한 번 다시 만든 뒤 통과")
    clean("the rendered marks are all there", mark_problems(over, over_text))
    equal("the marked ids are S9b's own", over.get("marked"), ["k-a"])
    lost = copy.deepcopy(over)
    # found, not assumed: a reverted rule upstream can leave the overlay without the marked row, and that must fail this
    # control by name rather than end the suite
    marked = next((r for r in lost.get("rows") or [] if r.get("item_id") == "k-a"), None)
    if marked is None or not isinstance(marked.get("s9b"), dict):
        dropped = "NO_MARKED_ROW: the overlay holds no row k-a with an S9b state to drop the mark from"
    else:
        marked["s9b"]["mark"] = False
        try:
            dropped = f"rendered {len(render_text(lost, meta, {}))} bytes"
        except Refused as exc:
            dropped = str(exc)
    control("a row S9b marked, rendered without its mark, is refused by name", dropped, "MARK_MISSING k-a")
    control("an overlay for an item S7 did not propose is refused by name",
            "\n".join(overlaid(lambda d: d["s9b_regenerated"]["proposals"].update({"k-zz": better}))["problems"]),
            "OVERLAY_UNACCOUNTED k-zz")
    control("an S9b review entry for an item S7 did not propose is refused by name",
            "\n".join(overlaid(lambda d: d["s9b_review"]["unreviewed"].append({"item_id": "k-zz", "why": "x"}))
                      ["problems"]), "OVERLAY_UNACCOUNTED k-zz")
    control("an overlay that moves a non-Korean field is refused through S7's own regenerated_problems",
            "\n".join(overlaid(lambda d: (d["s9b_regenerated"]["proposals"].get("k-g") or {}).update(disposition="drop"))
                      ["problems"]), "OVERLAY_INVALID k-g: REGENERATION_CHANGED disposition")
    first_frozen = frozen_after(None, unlaid["rows"], 1, "t1")
    equal("the frozen first proposal is unaffected by an overlay",
          frozen_after(first_frozen, over["rows"], 2, "t2")["items"].get("k-g"), first_frozen["items"].get("k-g"))
    plain = document({**copy.deepcopy(base_docs), "s9b_review": None, "s9b_regenerated": None})
    equal("a run S9b never reviewed renders exactly as before: the same rows, and no S9b line",
          (plain["rows"] == unlaid["rows"], any("s9b" in r for r in unlaid["rows"]),
           any(line.startswith("- S9b") for line in rendered(unlaid).split("\n"))), (True, False, False))
    equal("a proposal S9b's version did not hold yet is named as not yet reviewed",
          (row_of(overlaid(lambda d: d["s9b_review"].update(
              rows=[r for r in d["s9b_review"]["rows"] if r["item_id"] != "k-a"])), "k-a").get("s9b") or {}).get("state"),
          "not_yet")
    reworded = doc_of(lambda d: next(r for r in d["s7b"]["reviews"] if r["item_id"] == "k-g")["alternative"].update(
        reason="다른 이유"))
    equal("a rendered row's two hashes are reproduced from the row itself, whatever ranking added",
          sorted({(keyed(r)["item_sha"] == r["item_sha"], keyed(r)["payload_sha256"] == r["payload_sha256"])
                  for r in good["rows"]}), [(True, True)])
    equal("S7b's Korean (its notes, its alternative's reason) is no part of the English payload",
          [row_of(x, i).get("payload_sha256") for x, i in ((moved, "k-a"), (reworded, "k-g"))],
          [row_of(good, "k-a").get("payload_sha256"), row_of(good, "k-g").get("payload_sha256")])
    control("a core item admitted by adjudication is shown awaiting R", text, AWAITING_R)
    control("a model's newline cannot start a line: the decision-shaped text stays on its field's line", text,
            "- 무엇이 있었나: 첫 줄 결정: 승인")
    control("a marker-shaped line inside a model's text is escaped in its fence", text,
            "\\<!-- owner-block review item=x sha=y -->")
    control("a fence is longer than any backtick run inside it", text, "````\nline one")
    control("the disputed row's block carries one 판정 line per disputed judgment", text,
            "결정:\n메모:\n판정 1:\n판정 2:\n<!-- /owner-block -->")
    control("a group row's members are listed in the appendix", text,
            "- `group:legacy:below-bar-default` (2개): `legacy:L-2`, `legacy:L-3`")
    control("a non-finding is listed with its locator", text, "- `e9` routine_step · 위치 s1#3")
    equal("the spec carries each disputed label with its own values and its reference",
          ((spec_of(good).get("k-b") or {}).get("judgments"), (spec_of(good).get("k-b") or {}).get("refs")),
          ({"1": ["met", "unmet"], "2": ["met", "unmet"]}, {"1": "requirement/bounded", "2": "requirement/positioned"}))
    a = row_of(good, "k-a")
    control("each row prints its item_sha and its payload_sha256", text,
            f"item_sha {a.get('item_sha')} · payload_sha256 {a.get('payload_sha256')}")
    control("a legacy first word outside the owner's three is named in the header",
            rendered(good, {**meta, "legacy_unexpected": ["odd"]}) if text else "", "예상 밖의 legacy 묶음")

    # ---- §13.4's frozen proposals (lead decision E7: frozen at the first render as proposed) ---------------------
    first = frozen_after(None, good["rows"], 1, "t1")
    equal("the first render freezes every proposed row's proposal, by item, at its version",
          {k: v["version"] for k, v in first["items"].items()}, {"k-a": 1, "k-g": 1, "due_decision:P-1@r1": 1})

    def redisposed(rows):
        out = copy.deepcopy(rows)
        for r in out:
            if r["item_id"] == "k-a":
                r["proposal"]["disposition"] = "drop"
            if r["item_id"] == "k-b":
                r.update(status="proposed", proposal=copy.deepcopy(row_of(good, "k-a").get("proposal") or {"x": 1}))
        return out
    later = frozen_after(first, redisposed(good["rows"]), 2, "t2")
    equal("a later version never replaces a frozen proposal, and freezes only what is new",
          ({k: v["version"] for k, v in later["items"].items()},
           ((later["items"].get("k-a") or {}).get("material") or {}).get("disposition")),
          ({"k-a": 1, "k-b": 2, "k-g": 1, "due_decision:P-1@r1": 1}, "keep"))
    equal("the material part is §13.4's four fields", sorted((first["items"].get("k-a") or {}).get("material") or {}),
          ["behavior_contract", "destination", "disposition", "targets"])

    # previous_of on files of its own: the golden run's S7 proposes nothing, so its frozen proposals are empty
    import shutil as _shutil
    import tempfile as _tempfile
    chain = pathlib.Path(_tempfile.mkdtemp(prefix="s9-chain-"))
    try:
        records.write_json(chain, chain / "frozen-proposals.v1.json", first)
        (chain / "review.ko.v1.md").write_text("v1\n", encoding="utf-8")
        records.write_json(chain, chain / "review.v1.json",
                           {"version": 1, "frozen_sha256": records.sha256_file(chain / "frozen-proposals.v1.json")})
        (chain / "review.ko.v2.md").write_text("v2, cut short\n", encoding="utf-8")
        records.write_json(chain, chain / "frozen-proposals.v2.json", {"stage": STAGE, "items": {}})
        try:
            prev, carried = previous_of(chain, 3)
        except Refused as exc:
            prev, carried = str(exc), None
        equal("a render carries the frozen proposals of the last complete version, skipping one cut short before its "
              "rows file", ((prev or {}).get("version") if isinstance(prev, dict) else prev,
                            sorted((carried or {}).get("items") or {})), (1, sorted(first["items"])))
        equal("and binds that version's rows file by its sha256", (prev or {}).get("rows_sha256") if isinstance(prev, dict)
              else prev, records.sha256_file(chain / "review.v1.json"))
        records.write_json(chain, chain / "review.v3.json", {"version": 3, "frozen_sha256": "0" * 64})
        (chain / "review.ko.v3.md").write_text("v3\n", encoding="utf-8")
        try:
            lost = f"returned {previous_of(chain, 4)[0]}"
        except (Refused, OSError) as exc:  # a reverted check fails this control by name, not by a traceback
            lost = f"{type(exc).__name__}: {exc}"
        control("a complete version that has lost a file since is refused by name, not skipped", lost,
                "RENDER_FILE_MISSING frozen-proposals.v3.json")
    finally:
        _shutil.rmtree(chain, ignore_errors=True)

    # ---- the stage, end to end on the golden run ------------------------------------------------------------------
    import shutil
    import tempfile
    root = pathlib.Path(tempfile.mkdtemp(prefix="s9-"))
    class SectionStopped(Exception):
        pass
    try:
        try:
            run_dir, said_run = golden_run(root), None
        except Exception as exc:  # an upstream stage that breaks fails this section's first control by name
            equal("S9 renders the golden run (S1 to S7) as version 1",
                  (None, f"GOLDEN_RUN_FAILED {type(exc).__name__}: {exc}"[:300]), (1, None))
            raise SectionStopped from exc
        cli_out = root / "cli"
        shutil.copytree(run_dir.parent, cli_out)
        try:
            first = run(run_dir)
        except Refused as exc:
            first, said_run = {}, str(exc)
        equal("S9 renders the golden run (S1 to S7) as version 1", (first.get("version"), said_run), (1, None))
        names = sorted(p.name for p in run_dir.glob("*.v1.*"))
        equal("it writes the render, the owner's copy, the frozen proposals and the rows", names,
              ["decisions.ko.v1.md", "frozen-proposals.v1.json", "review.ko.v1.md", "review.v1.json"])
        if names:
            text1 = (run_dir / "review.ko.v1.md").read_text(encoding="utf-8")
            # the whole sentence, as one line of the page (Codex WP-20 r2 F6: two substrings passed beside an added
            # unconditional promise): approval is provisional, only a changing proposal changes files, a new
            # candidate's `none` is kept in the run's record alone, commands follow only a change
            equal("the review says, in one line, what approving does in release 1",
                  [line for line in text1.split("\n") if line.startswith("승인은 아직 적용이 아닙니다.")],
                  ['승인은 아직 적용이 아닙니다. 승인한 항목으로 만든 최종 집합을 확정(S10b)하고 적용(S11)하면, 파일을 바꾸는 제안만 선언된 체크아웃의 파일을 바꿉니다. `none`(바꾸지 않음)과 대장에만 남는 처리(keep·incubate·drop)는 파일을 바꾸지 않고, 대장에 항목이 없는 새 후보의 `none`은 대장에 줄을 만들지 않고 이번 실행의 마무리 기록(close.json)에만 남습니다. 커밋과 설치는 소유자가 직접 합니다 — 적용으로 파일이 바뀌면 실행할 명령을 그대로 보여 드립니다.'])
            held = records.read_json(run_dir / "review.v1.json")
            got, probs = owner_lines.parse(text1, (run_dir / "decisions.ko.v1.md").read_text(encoding="utf-8"),
                                           spec=held["spec"], render_name="review.ko.v1.md")
            clean("the written copy parses against the written spec", probs)
            equal("every row the golden run's S7 returned is in the quarantined-or-failed group",
                  sorted({r["status_group"] for r in held["rows"] if r["status"] == RETURNED}) or ["(none returned)"],
                  ["quarantined_or_failed"])
            equal("the rows file binds the render by its sha256", held["render_sha256"], owner_lines.sha256_text(text1))
            # D-20261115-18d56b: the planted controls evaluated after S6 over the run's own artifacts, recorded in the
            # rows file and stated in one header line; the run went on whatever the evaluation says
            recorded = held.get("controls") or {}
            equal("the rows file records the planted controls' evaluation over the run's own S5 and S6 artifacts",
                  recorded, planted_controls.evaluation_in(run_dir))
            equal("and the header states it in one line, the evaluation's own",
                  [line for line in text1.split("\n") if line.startswith("- 대조군 결과: ")],
                  [f"- 대조군 결과: {inline(planted_controls.korean_line(recorded))}"] if recorded else ["(none recorded)"])
            equal("the golden run's evaluation counts every planted control once per stage it is checked at",
                  sum(recorded.get("counts", {}).get(k, 0) for k in ("expected", "failed", "not_applicable")),
                  sum(len(e["checked_at"]) for e in records.read_json(run_dir / "controls.json")["planted"])
                  + len(records.read_json(run_dir / "controls.json")["gate"]))
            stage_record = records.read_json(run_dir / "stages" / "S9" / "record.json")
            equal("the stage record lists the three outputs and the frozen proposals",
                  sorted(o.get("artifact") if isinstance(o, dict) else o for o in stage_record.get("outputs") or []),
                  ["decisions.ko.v1.md", "frozen-proposals.v1.json", "review.ko.v1.md", "review.v1.json"])
            equal("version 1 binds no earlier version, and binds its frozen proposals by sha256",
                  (held.get("previous"), held.get("frozen_sha256")),
                  (None, records.sha256_file(run_dir / "frozen-proposals.v1.json")))
            equal("the rows file carries its render time (§13.4's review time starts there)",
                  isinstance(held.get("rendered_at"), str) and held["rendered_at"][:2] == "20", True)
        if names:
            # the golden run's S7 proposes nothing: plant one frozen proposal in version 1, bound as its rows file binds
            planted = {"stage": STAGE, "items": {"planted-item": {"version": 1, "rendered_at": "t1", "material": {},
                                                                  "wording_sha256": "0" * 64}}}
            records.write_json(run_dir, run_dir / "frozen-proposals.v1.json", planted)
            rows1 = records.read_json(run_dir / "review.v1.json")
            rows1["frozen_sha256"] = records.sha256_file(run_dir / "frozen-proposals.v1.json")
            records.write_json(run_dir, run_dir / "review.v1.json", rows1)
            before = (run_dir / "review.ko.v1.md").read_bytes()
            try:
                second = run(run_dir).get("version")
            except Refused as exc:
                second = f"refused: {str(exc)[:160]}"
            equal("a second render of the same run is version 2, and version 1's bytes stay as they were",
                  (second, (run_dir / "review.ko.v1.md").read_bytes() == before), (2, True))
            held2 = records.read_json(run_dir / "review.v2.json") if (run_dir / "review.v2.json").is_file() else {}
            equal("version 2's rows bind version 1's rows file by its sha256",
                  held2.get("previous"), {"version": 1, "rows_sha256": records.sha256_file(run_dir / "review.v1.json")})
            frozen2 = (records.read_json(run_dir / "frozen-proposals.v2.json")
                       if (run_dir / "frozen-proposals.v2.json").is_file() else {})
            equal("the render of version 2 carries version 1's frozen proposals as they were frozen",
                  (frozen2.get("items") or {}).get("planted-item"), planted["items"]["planted-item"])
            frozen_path = run_dir / "frozen-proposals.v2.json"
            kept = frozen_path.read_bytes() if frozen_path.is_file() else b""
            frozen_path.write_bytes(kept + b"\n")
            try:
                changed = f"written {run(run_dir).get('version')}"
            except Refused as exc:
                changed = str(exc)
            frozen_path.write_bytes(kept)
            control("frozen proposals edited after their render are refused by name", changed,
                    "FROZEN_CHANGED frozen-proposals.v2.json")
            (run_dir / "decisions.ko.v3.md").write_text("planted", encoding="utf-8")
            try:
                third = f"written {run(run_dir).get('version')}"
            except Refused as exc:
                third = str(exc)
            control("a version any of whose three files exists is never written again", third,
                    "RENDER_VERSION_EXISTS decisions.ko.v3.md")
        # the driver's command, as a process, on a copy of the same run: the path a person takes
        import subprocess
        from runlib import stage_read
        done = subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "render", "--run-id", run_dir.name,
                               "--out", str(cli_out), "--checkout-ledger", str(stage_read.CHECKOUT_LEDGER)],
                              capture_output=True, text=True, timeout=600)
        control("the driver's `render` runs S9 as a process and prints the version and the row count",
                f"rc={done.returncode} {done.stdout}{done.stderr[-400:]}", "rc=0 S9 render: version 1, ")
        # S9b over the current version, and the next render reading it through the shared checks
        (run_dir / "decisions.ko.v3.md").unlink(missing_ok=True)
        from runlib import stage_review_korean as s9b_stage
        def s9b_taken():
            return sorted(i["artifact"] for i in records.read_json(run_dir / "stages" / "S9" / "record.json")["inputs"]
                          if i["producer_stage"] == "S9b")
        try:
            v3 = run(run_dir)["version"]
            untaken = s9b_taken()
            s9b_stage.run(run_dir, {})
            v4 = run(run_dir)["version"]
            took = s9b_taken()
        except Refused as exc:
            v3, untaken, v4, took = None, None, None, str(exc)
        equal("a render before S9b declares exactly S9's own inputs; one after takes S9b's two outputs as inputs",
              (v3, untaken, v4, took), (3, [], 4, ["regenerated-reasons.v3.json", "review-s9b.v3.json"]))
        held = records.read_json(run_dir / "stages" / "S9b" / "record.json")
        records.write_json(run_dir, run_dir / "stages" / "S9b" / "record.json", {**held, "status": "failed"})
        try:
            unsettled = f"written {run(run_dir)['version']}"
        except Refused as exc:
            unsettled = str(exc)
        control("a render over an S9b record that is not complete is refused by name", unsettled, "S9B_UNSETTLED")
        records.write_json(run_dir, run_dir / "stages" / "S9b" / "record.json", held)
        # S9b's review of documents a stage before S9 has since written again (the first live run: S7 was fixed
        # and run again after S9b, and S9 and S9b each refused the other as stale, with no next step)
        upstream = [i for i in held["inputs"] if i.get("producer_stage") not in (None, STAGE)]
        records.write_json(run_dir, run_dir / "stages" / "S9b" / "record.json",
                           {**held, "inputs": [{**i, "sha256": "0" * 64} if i in upstream else i for i in held["inputs"]]})
        equal("an S9b review of documents made again since is not overlaid, and the render is not refused for it",
              (bool(upstream), s9b_inputs(run_dir)), (True, ()))
        records.write_json(run_dir, run_dir / "stages" / "S9b" / "record.json", held)
        equal("while a review of what is there now is taken as before", len(s9b_inputs(run_dir)), 2)
        # S7b alone run again after S9b reviewed the current version: S9b is not owed a second review of that
        # version and S9 is owed a new render. Neither may leave the other with no next step, in either order.
        try:
            s9b_stage.run(run_dir, {})                                   # S9b reviews version 4
            stage_review_proposals.run(run_dir, {})                      # S7b alone, again
            try:
                first = f"reviewed {s9b_stage.run(run_dir, {})}"         # the operator tries S9b first
            except Refused as exc:
                first = str(exc).split(" ", 1)[0]
            kept = (records.stage_records(run_dir).get("S9b") or {}).get("status")
            v5 = run(run_dir)["version"]                                 # then S9
            again = s9b_stage.run(run_dir, {}).get("version")            # and S9b has a version to review
        except Refused as exc:
            first, kept, v5, again = str(exc), None, None, None
        equal("after S7b alone is run again, S9b refuses the version it reviewed and keeps its record, S9 renders "
              "the next version, and S9b reviews that one", (first, kept, v5, again),
              ("S9B_VERSION_REVIEWED", "complete", 5, 5))
        (run_dir / "stages" / "S7b" / "record.json").unlink(missing_ok=True)
        try:
            without = f"written {run(run_dir).get('version')}"
        except Refused as exc:
            without = str(exc)
        control("a run S7b has not reviewed does not render", without, "INPUT_INVALID S7b")
    except SectionStopped:
        pass
    except Exception as exc:  # a later break fails this section by name, never the whole suite
        failures.append(("the golden run's section ran to its end", f"{type(exc).__name__}: {exc}"[:600]))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    reporting.append(True)
    if failures:
        for label, detail in failures:
            print(f"stage_render --self-test [FAIL] {label}: {detail}", file=sys.stderr)
        print(f"stage_render --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"stage_render --self-test: OK ({len(ran)} controls: the rows are S4's population exactly once each, the "
          f"planted control none; the owner's legacy groups; the S5/S6/S7 failures and the quarantined; the counts line "
          f"held to S4 and S6; O6 per row; §7.5's order through ranking.py)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit("usage: stage_render.py --self-test")
