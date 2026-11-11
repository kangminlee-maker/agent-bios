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
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from grammar import owner_lines  # noqa: E402
from runlib import derive, ranking, records, stage_propose  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
STAGE = "S9"
PROPOSE_SCHEMA = HERE / "schemas" / "propose.schema.json"
# S9's inputs, by the stage that produces each.
INPUTS = ({"artifact": "census.json", "producer_stage": "S1"},
          {"artifact": "population.json", "producer_stage": "S4"},
          {"artifact": "intake.json", "producer_stage": "S4"},
          {"artifact": "controls.json", "producer_stage": "S5"},
          {"artifact": "checks.json", "producer_stage": "S5"},
          {"artifact": "judgments/judge.json", "producer_stage": "S6"},
          {"artifact": "judgments/derivations.json", "producer_stage": "S6"},
          {"artifact": "proposals.json", "producer_stage": "S7"})
# The ranking keys of a row nothing judged: values inside ranking.py's vocabularies that say "not determined", so a
# rejected finding, a failed item or a group row orders without a key invented for it (lead Q4 default).
UNDETERMINED = {"kind": "unclassified", "diagnosis": "unknown", "consequence": "none", "lineages": 0}
# The statuses of rows that ended before a proposal (lead Q3 default: ranking.json places them in
# quarantined_or_failed; until it does, ranking refuses them by name rather than this module placing them).
FAILED, RETURNED, QUARANTINED = "failed", "returned", "quarantined"
# The owner's three legacy groups. A first word outside them is still its own group (every entry accounted), and the
# header names it, since the owner decided for these three.
LEGACY_GROUPS = ("below-bar-default", "user-approved-default", "incubating")
S7B_ABSENT = {"state": "absent", "why": "S7b has not run on this tree (WP-12 commit 5 brings it)"}
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

def load(run_dir, ledger=None):
    """Every document the rows are made from, read once: `{population, intake, census, controls, checks, judge,
    derivations, proposals, judgments, quarantined, ledger}`. `ledger` is the pinned schema 2 document S4 read
    (`lifecycle_intake.ledger_of`), passed by the caller that names its reference."""
    run_dir = pathlib.Path(run_dir)
    read = lambda rel: records.read_json(run_dir / rel)  # noqa: E731
    docs = {"population": read("population.json"), "intake": read("intake.json"), "census": read("census.json"),
            "controls": read("controls.json"), "checks": read("checks.json"), "judge": read("judgments/judge.json"),
            "derivations": read("judgments/derivations.json"), "proposals": read("proposals.json"),
            "ledger": ledger, "judgments": {}, "quarantined": {}}
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
                    "units": [{"unit": u.get("unit"), "situation": u.get("situation"), "action": u.get("action"),
                               "reason": u.get("reason")} for u in j.get("units") or []]}
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
            "s7b": S7B_ABSENT, "failure": None, "awaiting_R": False, "awaiting_R_reason": None, "proposal": None,
            "guarded_keeps": [], "disputed": [], "judges": None, "units": [], "o6": o6}
    held.update(fields)
    return held


def proposal_row(cid, p, test_state, base, row_kind="candidate"):
    """A row S7 proposed for: its status, its proposal and S7's Korean reasons as the row's O6. A legacy entry keeps its
    row kind, since S6 did not judge it and the left-out count holds it as unjudged."""
    answer = p["proposal"]
    keep = answer.get("keep_record_named")
    return _row(cid, row_kind, p["status"], test_state, dict(answer["reasons"]),
                **{**base, "consequence": p["consequence"], "disposition": p["disposition"],
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
    checks = {c["candidate_id"]: c for c in (docs["checks"] or {}).get("candidates") or []}
    intake = {c["candidate_id"]: c for c in (docs["intake"] or {}).get("candidates") or []}
    entries = {e["id"]: e for e in ((docs.get("ledger") or {}).get("entries") or [])}
    rows, problems, groups = [], [], collections.OrderedDict()
    for cand in pop["candidates"]:
        cid, source = cand["candidate_id"], cand["source"]
        events = list(cand.get("event_ids") or [])
        if cid in check_failed:
            rows.append(_row(cid, "candidate", FAILED, test_state, o6_failed("S5", check_failed[cid]),
                             source=source, events=events, failure={"stage": "S5", "codes": list(check_failed[cid])}))
            continue
        if cid in not_derived:
            rows.append(_row(cid, "candidate", FAILED, test_state, o6_failed("S6", [str(not_derived[cid])]),
                             source=source, events=events, failure={"stage": "S6", "codes": [str(not_derived[cid])]}))
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
                held = {"source": source, "events": events, "legacy_word": stage_propose.decision1_kind(entry)}
                if cid in returned:
                    rows.append(returned_row(cid, returned[cid], test_state, held, "legacy"))
                    continue
                # the owner's rule: an entry with a classification block is its own row, and so is one S7 proposed
                # something other than the default for; the rest, S7's `none` default included (WP-12 answers them
                # in code, no call), are one group per first word of decision1
                p = proposed.get(cid)
                if entry.get("classification") is not None or (p and p["disposition"] != "none"):
                    rows.append(proposal_row(cid, p, test_state, held, "legacy") if p else
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
        base = {"source": source, "events": events, "admission": admission, "judges": judges,
                "kind": (outcome.get("kind") or {}).get("kind") or UNDETERMINED["kind"],
                "diagnosis": ((outcome.get("candidate_diagnosis") or {}).get("current") or {}).get("diagnosis")
                             or UNDETERMINED["diagnosis"],
                "lineages": verdict.get("lineages") if isinstance(verdict.get("lineages"), int) else 0,
                "eligible": (outcome.get("eligible") or {}).get("eligible"),
                "units": units_of(checks.get(cid), deriv.get("delivery")),
                "consequence": consequence_of(judges)}
        if admission in ("disputed", "rejected"):
            disputed = disputed_of(verdict) if admission == "disputed" else []
            rows.append(_row(cid, "candidate", admission, test_state, o6_admission(admission, disputed, verdict),
                             disputed=disputed, **base))
            continue
        if cid in proposed:
            rows.append(proposal_row(cid, proposed[cid], test_state, base))
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


def english_of(row):
    """The row's English source: the row without its Korean, which is the O6 text and, inside S7's answer, its
    `reasons` (the person reads them, so they are Korean: `schemas/propose.schema.json`) and `artifact_set.korean`."""
    held = {k: v for k, v in row.items() if k not in ("o6", "rank", "status_group", "item_sha", "payload_sha256")}
    if isinstance(held.get("proposal"), dict):
        answer = {k: v for k, v in held["proposal"].items() if k != "reasons"}
        if isinstance(answer.get("artifact_set"), dict):
            answer["artifact_set"] = {k: v for k, v in answer["artifact_set"].items() if k != "korean"}
        held["proposal"] = answer
    return held


def keyed(row):
    """`(row with its hashes)`: `payload_sha256` over its English source (`english_of`), `item_sha` over all of it, the
    Korean included. Neither covers the rank, which other rows move."""
    english = english_of(row)
    whole = {k: v for k, v in row.items() if k not in ("rank", "status_group", "item_sha", "payload_sha256")}
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
    """`{rows, appendix, counts, problems}`: the rows in §7.5's order with their hashes, or the problems that make them
    no review. A row ranking cannot place is reported by ranking's own code, never placed by a guess."""
    rows, appendix, problems = rows_of(docs)
    problems += population_problems(rows, appendix, docs)
    counts = counts_of(rows, appendix)
    problems += counts_problems(counts, docs) + left_out_problems(rows, docs) + row_problems(rows)
    if problems:
        return {"rows": [], "appendix": appendix, "counts": counts, "problems": problems}
    keyed_rows = [keyed(r) for r in rows]
    # ranking's own problems first, as a list: a row it cannot place is reported by its code, and `ranked` is called
    # only over rows it can place, so no refusal of it is caught here
    unplaced = ranking.value_problems(keyed_rows)
    if unplaced:
        return {"rows": [], "appendix": appendix, "counts": counts, "problems": [f"RANK_REFUSED {p}" for p in unplaced]}
    return {"rows": ranking.ranked(keyed_rows), "appendix": appendix, "counts": counts, "problems": []}


# ---- the Markdown (K2b) -------------------------------------------------------------------------------------------
# The review is Korean; identifiers, codes, quotes and the judges' own words stay as written. Every group §9 names has
# its title here, held to ranking.py's table by the self-test, so a group added there cannot render untitled.
GROUP_TITLES = {"proposed_and_tested": "제안 (release 1: 시험 전)", "disputed": "판정이 필요한 항목",
                "confirmed_and_keep": "확인됨과 유지", "already_resolved_and_unclassified": "이미 해결됨과 미분류",
                "rejected": "거부된 항목", "quarantined_or_failed": "격리되거나 실패한 항목"}
STATUS_LABELS = {"proposed": "제안됨 (시험 전)", "tested": "시험됨", "disputed": "판정 필요", "rejected": "거부됨",
                 "returned": "S7이 돌려보냄", "failed": "실패", "quarantined": "격리됨",
                 None: "판정하지 않음 (기본 처분 none)"}
FALLBACK = ("순서는 §7.5를 따릅니다. 이번 release에는 시험 결과가 없으므로(S8은 release 2), 판정자와 S7b가 정한 "
            "키로만 정렬합니다: 상태 그룹, 결과 등급, 독립 계보 수, 종류, 진단, 변경 여부, 항목 id.")
AWAITING_R = "R 대기: 판정으로 들어온 core 항목이라 이번 실행의 F에 들지 않고, 적용 대상이 아닙니다 (S8은 release 2)."


def inline(text):
    """A field's text on one line: every run of whitespace, newlines included, one space. A field therefore never
    starts a line, so nothing a model wrote can stand where an owner-block marker would."""
    return " ".join(str(text).split())


def fenced(text):
    """Multi-line text inside a code fence longer than any backtick run it holds, its carriage returns normalized, and
    every line shaped like an owner-block marker escaped with a leading backslash (the one change made to it)."""
    body = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body = ["\\" + line if owner_lines.LOOKS_LIKE_MARKER.match(line) else line for line in body]
    longest = max((len(run) for line in body for run in re.findall(r"`+", line)), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence, *body, fence]


def judge_line(who, judge):
    if judge is None:
        return f"- 판정자 {who}: 수락된 판정 없음"
    marks = ", ".join(f"{k}={v}" for k, v in judge["requirements"].items())
    units = "; ".join(f"{u['unit']} 상황 {u['situation']} 행동 {u['action']}: {inline(u['reason'])}"
                      for u in judge["units"]) or "단위 판정 없음"
    return (f"- 판정자 {who} ({judge['seat']}): 요구 사항 {marks}; 결과 등급 {judge['consequence_class']}; "
            f"단위 {units}")


def proposal_lines(answer):
    """The proposal's own parts, beyond its O6 reasons: destination, operations, contract, observation, artifacts and
    the unknowns it carries."""
    out = []
    dest = answer.get("destination") or {}
    out.append(f"- 대상: layer {dest.get('layer')}, carrier {dest.get('carrier')}")
    for n, op in enumerate(answer.get("operations") or [], 1):
        out.append(f"- 연산 {n}: {op['type']} {inline(op['target'])} (before {op['before_state_sha256'][:12]})")
        for field in ("content", "diff"):
            if op.get(field):
                out += fenced(op[field])
    contract = answer.get("behavior_contract")
    if contract:
        out.append("- 행동 계약: " + "; ".join(
            f"{k} {inline(v if isinstance(v, str) else ' / '.join(v))}" for k, v in contract.items()))
    observation = answer.get("expected_observation")
    if observation:
        out.append("- 기대 관찰: " + "; ".join(f"{k} {inline(v if isinstance(v, str) else v)}"
                                         for k, v in observation.items() if v is not None))
    artifacts = answer.get("artifact_set")
    if artifacts:
        out.append(f"- 산출물 등록: {inline(artifacts['registration'])}")
        for field in ("english", "korean"):
            if artifacts.get(field):
                out.append(f"- 산출물 ({field}):")
                out += fenced(artifacts[field])
    for u in answer.get("unknowns") or []:
        out.append(f"- 알 수 없음: {u['field']}={u['state']} — {inline(u['effect'])}")
    return out


def row_lines(row, fields):
    """One row as the review prints it, its owner block last."""
    o6 = row["o6"]
    out = [f"### {row['rank']}. `{row['item_id']}`",
           f"- 상태: {STATUS_LABELS.get(row['status'], row['status'])} · 종류 {row['kind']} · 진단 {row['diagnosis']} · "
           f"처분 {row['disposition']} · 결과 등급 {row['consequence']} · 독립 계보 {row['lineages']}"]
    labels = {"what_happened": "무엇이 있었나", "proposal": "제안", "reason": "이유", "cost": "비용",
              "serves": "누구에게", "falsifier": "반증"}
    out += [f"- {labels.get(name, name)}: {inline(o6[name])}" for name in fields]
    if row.get("judges"):
        out += [judge_line(who, row["judges"].get(who)) for who in JUDGES]
    for d in row.get("disputed") or []:
        out.append(f"- 판정할 것 {d['label']}: {d['ref']} — A {d['A']}, B {d['B']} (자기 값은 {' 또는 '.join(d['values'])})")
    if row.get("proposal"):
        out += proposal_lines(row["proposal"])
    out.append(f"- S7b: 기록 없음 ({row['s7b']['why']})" if row["s7b"].get("state") == "absent" else f"- S7b: {row['s7b']}")
    out.append(f"- 시험: {row['test']}")
    if row.get("awaiting_R"):
        out.append(f"- {AWAITING_R}")
    if row.get("failure"):
        out.append(f"- 실패: {row['failure']['stage']} {', '.join(row['failure']['codes'])}")
    if row.get("units"):
        out.append("- 관련 단위: " + ", ".join(f"{u['unit_id']} (전달 증거: {u['delivery']})" for u in row["units"]))
    if row.get("events"):
        out.append(f"- 사건: {', '.join(row['events'])}")
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
           "## 머리말", "",
           f"- 실행: {meta['run_id']} · 종류 {d.get('kind')} · 자세 {d.get('posture')} · 선언 순번 {d.get('declaration_seq')}",
           f"- 창: {(d.get('window') or {}).get('start')} – {(d.get('window') or {}).get('end')} "
           f"({(d.get('window') or {}).get('tz')})",
           f"- 질문: {inline(d.get('question'))}"]
    for source, s in sorted((meta.get("census") or {}).items()):
        totals = ", ".join(f"{k} {v}" for k, v in sorted((s.get("totals") or {}).items())) or "없음"
        out.append(f"- 출처 {source}: 상태 {s.get('state')}, 발견 {s.get('discovered')}, {totals}")
    flags = meta.get("window_flags")
    out.append(f"- 창 범위: accounted {flags['accounted']}, fully_read {flags['fully_read']}" if flags
               else "- 창 범위: 기록 없음 (coverage.json에 이 창의 표시가 없음)")
    out.append(f"- 대조군 결과: {meta['controls']}")
    if meta.get("legacy_unexpected"):
        out.append("- 예상 밖의 legacy 묶음 (소유자가 정한 세 묶음 밖): " + ", ".join(meta["legacy_unexpected"]))
    out.append(f"- 자연 거부 비율: {meta['rejection_share']}")
    out.append("- 처분별: " + ", ".join(f"{k} {v}" for k, v in counts["disposition"].items()))
    out.append("- 상태별: " + ", ".join(f"{STATUS_LABELS.get(None if k == 'None' else k, k)} {v}"
                                      for k, v in counts["status"].items()))
    out.append("- 출처별 후보: " + ", ".join(f"{k} {v}" for k, v in counts["candidates"].items()))
    out.append(f"- 사건: 후보 구성원 {counts['candidate_members']}, 거부된 발견 {counts['rejected_findings']}개 "
               f"(구성원 {counts['rejected_finding_members']}), 비발견 "
               + (", ".join(f"{k} {v}" for k, v in counts["non_findings"].items()) or "없음"))
    out.append(f"- 이전 창의 관찰 결과: {meta['resolutions']}")
    out.append("- §13 측정: 아직 없음: S12가 돌지 않았습니다.")
    out.append("- 쓴 예산: " + (", ".join(f"{s} {v}" for s, v in meta["spent"].items()) or "기록 없음"))
    out.append(f"- {FALLBACK}")
    return out


def appendix_lines(doc, locators):
    out = ["## 부록", "", "### 비발견 (사유별)", ""]
    for n in sorted(doc["appendix"]["non_findings"], key=lambda n: (n["reason"], n["event_id"])):
        dup = f", {n['duplicate_of']}의 중복" if n.get("duplicate_of") else ""
        out.append(f"- `{n['event_id']}` {n['reason']}{dup} · 위치 {locators.get(n['event_id'], 'unavailable')}")
    if not doc["appendix"]["non_findings"]:
        out.append("- 없음")
    out += ["", "### 그룹 행의 구성원", ""]
    for ident, members in sorted(doc["appendix"]["group_members"].items()):
        out.append(f"- `{ident}` ({len(members)}개): " + ", ".join(f"`{m}`" for m in members))
    if not doc["appendix"]["group_members"]:
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
    return "\n".join(out) + "\n"


def spec_of(doc):
    """The current rows as `owner_lines.parse` holds the owner's lines to them: each item's sha, its disputed labels
    with their own values, S7b's alternatives (none until S7b runs) and the keep records its proposal overrides."""
    return {r["item_id"]: {"item_sha": r["item_sha"],
                           "judgments": {d["label"]: list(d["values"]) for d in r.get("disputed") or []},
                           "refs": {d["label"]: d["ref"] for d in r.get("disputed") or []},
                           "alternatives": [], "guarded_keeps": list(r.get("guarded_keeps") or []),
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
    controls = "기록 없음: S7의 대조군 평가가 아직 이 트리에 없음 (controls.evaluate는 S7이 부름)"
    unexpected = sorted({r["legacy_word"] for r in document_rows(docs) if r["row_kind"] == "legacy_group"}
                        - set(LEGACY_GROUPS))
    return {"version": version, "run_id": run_dir.resolve().name, "declaration": declaration,
            "legacy_unexpected": unexpected,
            "census": (docs.get("census") or {}).get("sources") or {}, "window_flags": flags, "spent": dict(sorted(spent.items())),
            "resolutions": resolutions, "rejection_share": share, "controls": controls}


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
    return {"disposition": answer.get("disposition"), "destination": answer.get("destination"),
            "targets": sorted([op.get("type"), op.get("target")] for op in answer.get("operations") or []),
            "behavior_contract": answer.get("behavior_contract")}


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
    with records.run_stage(run_dir, STAGE, INPUTS) as stage:
        if ledger is None:
            from runlib import lifecycle_intake
            ledger = lifecycle_intake.ledger_of(stage.declaration)[0]
        docs = load(run_dir, ledger)
        doc = document(docs)
        if doc["problems"]:
            raise Refused("RENDER_REFUSED " + "\n".join(doc["problems"]))
        version = next_version(run_dir)
        text = render_text(doc, meta_of(run_dir, stage.declaration, docs, version), locators_of(run_dir))
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
            "appendix": doc["appendix"], "counts": doc["counts"], "spec": spec_of(doc)})
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
              + [{"candidate_id": "due_decision:P-1@r1", "source": "due_decision", "pending_intervention": True}]}

    def entry(ident, word, classification=None):
        return {"id": ident, "status": "incubating", "classification": classification,
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
                                        "units": [{"unit": "u-9", "situation": "yes", "action": "no", "reason": "r"}]}}
                     for who in JUDGES} for c in judged}
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
                                "before_state_sha256": "b" * 64}],
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
                                "before_state_sha256": "a" * 64}],
                   destination={"layer": "session_injection", "carrier": "router/relevant.md", "situation": "s"},
                   unknowns=stage_propose._carry(derivations)),
               "k-p": stage_propose._answered(disposition="keep", operations=[], expected_observation=None,
                                              destination={"layer": "incubator", "carrier": None},
                                              unknowns=stage_propose._carry(derivations))}
    proposals = stage_propose.document(derivations, candidates, answers)
    checks = {"candidates": [{"candidate_id": "k-a", "retrieved_units": [{"unit_id": "u-9"}]}]}
    controls = {"planted": [{"candidate_id": "k-p"}]}
    quarantined = {"S3": [{"id": "w-3", "reason": "READ_INCOMPLETE", "because": None}]}
    return {"population": population, "intake": intake, "census": {}, "controls": controls, "checks": checks,
            "judge": judge, "derivations": derivations, "proposals": proposals, "judgments": judgments,
            "quarantined": quarantined, "ledger": ledger}


def golden_run(root):
    """The golden fixture library through S7 (every candidate S6 admitted returned by an S7 that answered nothing),
    in-process, so the fixture's ledger reference holds."""
    from runlib import declare, stage_judge, stage_propose, stage_retrieve
    import shutil
    # an incomplete reference point: no sweep is admissible, so S6's golden plan completes the stage (with a complete
    # one, the plan answers no sweep and S6 is partial, which S7 refuses as an input)
    run_dir = stage_retrieve.fx_gold(root / "base", stage_retrieve.fx_current(stage_judge.fx_library()))
    declare.amend(run_dir, [("budget.per_stage.S6", 20_000_000)], "S9 self-test: the golden run through S7",
                  scope=["S5", "S6", "S7", "S9"])
    stage_retrieve.run(run_dir, "aa" * 8)
    planner = root / "planner"
    shutil.copytree(run_dir.parent, planner)
    plan, _p = stage_judge.fx_judge_plan(planner / run_dir.name, root / "plan.json")
    stage_judge.run(run_dir, stage_judge.supervisor(run_dir, root / "cells", plan))
    # S7 through its own INPUTS and `document`, as `stage_propose.run` means to: that function, at 49fce8c, writes
    # `proposals.json` relative to the working directory (RUN_PATH_ESCAPE) and registers no output, reported to the
    # lead; this stand-in goes when lane L's fix lands
    with records.run_stage(run_dir, stage_propose.STAGE, stage_propose.INPUTS) as stage:
        doc = stage_propose.document(records.read_json(run_dir / "judgments" / "derivations.json"),
                                     records.read_json(run_dir / "checked-candidates.json"), {})
        records.write_json(run_dir, run_dir / "proposals.json", doc)
        stage.output("proposals.json")
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
            ",".join(r["item_id"] for r in doc_of(lambda d: d["proposals"].update(
                proposals=[p for p in d["proposals"]["proposals"] if p["candidate_id"] != "k-a"],
                returned=d["proposals"]["returned"] + [{"candidate_id": "k-a", "problems": ["ANSWER_ABSENT k-a"]}]))
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
    text = render_text(good, meta, {"e9": "s1#3"}) if good["rows"] else ""
    clean("the render is a render owner_lines can copy", owner_lines.render_problems(text) if text else ["NO_ROWS"])
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
    equal("the same documents render the same bytes", render_text(doc_of(), meta, {"e9": "s1#3"}) if text else None,
          text or "(no rows)")
    equal("every §9 group in ranking's table has a title here", sorted(GROUP_TITLES),
          sorted(g["id"] for g in ranking.table()["groups"]))
    control("the header names the §7.5 fallback", text, FALLBACK)
    control("§13's measures are named as not yet produced", text, "§13 측정: 아직 없음")
    equal("every row shows the test state", text.count("- 시험: untested: s8_deferred"), len(good["rows"]) or -1)
    equal("every row shows S7b's state", text.count("- S7b: 기록 없음"), len(good["rows"]) or -1)
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
            render_text(good, {**meta, "legacy_unexpected": ["odd"]}, {}) if text else "", "예상 밖의 legacy 묶음")

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
    try:
        run_dir, said_run = golden_run(root), None
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
            held = records.read_json(run_dir / "review.v1.json")
            got, probs = owner_lines.parse(text1, (run_dir / "decisions.ko.v1.md").read_text(encoding="utf-8"),
                                           spec=held["spec"], render_name="review.ko.v1.md")
            clean("the written copy parses against the written spec", probs)
            equal("every row the golden run's S7 returned is in the quarantined-or-failed group",
                  sorted({r["status_group"] for r in held["rows"] if r["status"] == RETURNED}) or ["(none returned)"],
                  ["quarantined_or_failed"])
            equal("the rows file binds the render by its sha256", held["render_sha256"], owner_lines.sha256_text(text1))
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
