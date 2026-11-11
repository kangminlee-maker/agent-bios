#!/usr/bin/env python3
"""S7 propose (WP-12 commit 4b): one proposal per candidate, held to the contract code can decide.

The disposition is the model's answer; the kind and the diagnosis are NOT. S6 derived those, and a
packet that invited them again would give the proposal two sources for the same field - so an answer
that carries either is refused (`ANSWER_REDERIVES_DERIVED`), and the flat proposal this module hands
to `runlib/placement.py` takes them from the derivation.

What this module owns: the packet, the shape of an answer (`schemas/propose.schema.json`), the flat
view the contract reads, the unknowns a proposal must carry forward by name, the review row, and the
document. What it does not own and does not restate: the allowed pairs, the structural rules and the
placement rules (`runlib/placement.py` over its three tables), the semantic bars
(`packets/placement_contract.md`, judged by S7b), and the order (`runlib/ranking.py`).

Release 1 reads S6's derivations with `unit_outcomes` in the named state `none` - a state with a
count, not an empty list. A proposal that rests on a unit outcome must carry that state by name; a
module that read it as "no unit is affected" would propose changes on evidence nobody has.

    stage_propose.py --self-test
"""
import collections
import json
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import packet, placement, ranking, records  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
STAGE = "S7"
SCHEMA_PATH = HERE / "schemas" / "propose.schema.json"
FIXTURES_PATH = HERE / "tables" / "propose_fixtures.json"
TEMPLATE = "propose"
# S7's inputs, by the stage that produces each: staleness is the shared mechanism's to judge.
INPUTS = ({"artifact": "judgments/derivations.json", "producer_stage": "S6"},
          {"artifact": "judgments/gate-verdicts.json", "producer_stage": "S6"},
          {"artifact": "checked-candidates.json", "producer_stage": "S5"})
# The derivation fields that can arrive as a named state rather than an answer, and the proposal
# field each one would otherwise decide. Data, because the list grows as producers land and a
# proposal must name what it could not know.
UNKNOWN_SOURCES = (
    {"field": "unit_outcomes", "answered_when": "derived",
     "effect_on": "which units this candidate's disposition acts on"},
    {"field": "delivery", "answered_when": "assembled",
     "effect_on": "whether the units were delivered before the decision"},
    {"field": "arc_confirmation", "answered_when": "confirmed",
     "effect_on": "whether a type G candidate's arc is confirmed"},
    {"field": "points.release", "answered_when": "judged",
     "effect_on": "what the release reference point says about this candidate"},
)
DERIVED_FIELDS = ("kind", "diagnosis")


# ---- the legacy intake, under the row the owner decided -------------------------------------------
# The owner's answer lives in `tables/allowed_pairs.json`'s legacy row as DATA (`owner_default`), and
# this module reads it. A default that lived only in a comment would be a default nobody applies.

def legacy_default():
    """The owner's decided default for a legacy incubating entry, from the table."""
    rows = [row for row in placement.table("pairs")["rows"] if row.get("legacy_incubating")]
    if len(rows) != 1:
        raise Refused(f"LEGACY_ROW_NOT_ONE {len(rows)}: §7.2 has exactly one legacy row, and the "
                      f"default is read from it")
    held = rows[0].get("owner_default")
    if not held or not held.get("disposition") or not held.get("call_spent"):
        raise Refused("LEGACY_DEFAULT_UNDECLARED: the legacy row carries no owner_default with a "
                      "disposition and a call_spent, so which entries reach a call is undecided")
    return held


def decision1_kind(entry):
    """The kind of a legacy entry's `decision1`, by its first word, or `none` when it has none.

    The owner's grouping key: the 118 entries without a classification block differ from one another
    only in this one line, so its first word is what the report groups them by."""
    for row in entry.get("decisions") or []:
        if isinstance(row, dict) and row.get("field") == "decision1":
            return (str(row.get("legacy_text") or "").split(" ") or ["none"])[0] or "none"
    return "none"


def call_spent_on(entry):
    """Whether this legacy entry reaches an S7 packet, by the owner's `call_spent` rule.

    `classified_only`: an entry carrying a classification block names the layer someone meant to
    write it into and is read one at a time; one without differs from its neighbours only in its
    legacy line, so code proposes the default and no call is made. The plan's done-when 5 - items at
    `none` stay in the intake - read as what it costs."""
    rule = legacy_default()["call_spent"]
    if rule == "classified_only":
        return bool(entry.get("classification"))
    if rule == "all":
        return True
    raise Refused(f"LEGACY_CALL_RULE_UNKNOWN {rule!r}: the legacy row declares classified_only or all")


def mapped_incubate(entry):
    """A schema-2 incubate decision this legacy entry already carries, or None.

    An entry migrated WITH a decision is not an entry awaiting a default: it enters the intake with
    what it has (the plan's F-O5-10). A legacy_migration row is not such a decision - it records the
    migration of the status, not a judgment - so it is excluded by its own kind."""
    for row in entry.get("decisions") or []:
        if not isinstance(row, dict) or row.get("kind") == "legacy_migration":
            continue
        if row.get("disposition") == "incubate":
            return row
    return None


def legacy_answer(entry):
    """The default proposal code makes for a legacy entry no call is spent on.

    It carries no operations and no observation, because the default is the ABSENCE of a new
    judgment: §7.2's `none_stays_in_intake` asks exactly that, and the reason says which group the
    entry was counted in rather than pretending to a reading nobody did."""
    held = legacy_default()
    group = decision1_kind(entry)
    mapped = mapped_incubate(entry)
    if mapped is not None:
        # It enters with the decision it has. The observation and the expiry come from that decision,
        # not from this code: a default that wrote an observation for an entry would be inventing the
        # thing §7.3 asks for.
        return {"disposition": "incubate", "consequence": "none", "operations": [],
                "destination": {"layer": "incubator", "carrier": None},
                "expected_observation": mapped.get("expected_observation"),
                "unknowns": [],
                "reasons": {"what_happened": f"레거시 항목 {entry.get('id')}은 이미 incubate 결정을 들고 있다",
                            "proposal": "그 결정 그대로 흡입에 들어온다",
                            "reason": f"스키마 2로 맵핑된 결정이 있어 기본값이 적용되지 않는다. 묶음 {group}.",
                            "cost": "없음",
                            "serves": "그 결정을 내린 사람과 그것을 확인할 다음 창",
                            "falsifier": "저장된 관측이 만료에 이르러 확인되지 않으면 그 결정이 틀렸다"},
                "legacy_group": group, "entered_with_decision": True}
    return {"disposition": held["disposition"], "consequence": "none", "operations": [],
            "destination": {"layer": "incubator", "carrier": None},
            "expected_observation": None, "unknowns": [],
            "reasons": {"what_happened": f"대장의 레거시 항목 {entry.get('id')}이 흡입에 남아 있다",
                        "proposal": "제안 없음: 소유자가 정한 기본값대로 흡입에 남긴다",
                        "reason": (f"이 항목에는 분류 블록이 없어 이번 창의 증거가 더 말해 주는 것이 없다. "
                                   f"묶음 {group}."),
                        "cost": "없음: 대장도 라이브러리도 바뀌지 않는다",
                        "serves": "이 항목을 다시 읽을 다음 창의 작업자",
                        "falsifier": "이 상황이 다시 일어나 새 증거가 생기면 보통 후보로 올라온다"},
            "legacy_group": group, "entered_with_decision": False}


def legacy_split(entries):
    """`{calls, defaults, groups}`: which legacy entries reach a packet and which code answers.

    The groups are counted over the entries this run holds, never over a remembered figure: the
    owner's 24-and-118 was a measurement of one day's ledger, and a module that hard-coded it would
    be wrong the first time an entry moved."""
    calls, defaults = [], []
    for entry in entries:
        (calls if call_spent_on(entry) else defaults).append(entry)
    groups = collections.Counter(decision1_kind(entry) for entry in defaults)
    return {"calls": [e.get("id") for e in calls],
            "defaults": [{"id": e.get("id"), "group": decision1_kind(e), "answer": legacy_answer(e)}
                         for e in defaults],
            "groups": dict(groups),
            "counts": {"entries": len(entries), "calls": len(calls), "defaults": len(defaults),
                       "groups": len(groups)}}


def schema_bytes():
    if not SCHEMA_PATH.is_file():
        raise Refused(f"PROPOSE_SCHEMA_ABSENT {SCHEMA_PATH}: an answer would be judged by nothing")
    return SCHEMA_PATH.read_bytes()


def named_states(derivation):
    """`[{field, state, effect}]`: every UNKNOWN_SOURCES field this derivation did not answer.

    Read from the document's own spelling of the state, never from its absence: a field that is not
    there at all is itself a state (`absent`), and silence is what this list exists to prevent."""
    held = []
    for source in UNKNOWN_SOURCES:
        node = derivation
        for part in source["field"].split("."):
            node = (node or {}).get(part) if isinstance(node, dict) else None
        state = node.get("state") if isinstance(node, dict) else node
        if state is None:
            state = "absent"
        if str(state) != source["answered_when"]:
            held.append({"field": source["field"], "state": str(state),
                         "effect": source["effect_on"]})
    return held


def candidate_facts(candidate, derivation_row):
    """The candidate's own fields S7 is given: its id, type, kind, diagnosis and admission."""
    outcome = (derivation_row or {}).get("outcome") or {}
    return {"candidate_id": candidate["candidate_id"],
            "type": candidate.get("type"),
            "kind": (outcome.get("kind") or {}).get("kind"),
            "diagnosis": ((outcome.get("candidate_diagnosis") or {}).get("current") or {}).get("diagnosis"),
            "admission": (outcome.get("admission") or {}).get("admission"),
            "lineages": (derivation_row or {}).get("lineages"),
            "promotion": (outcome.get("promotion") or {}).get("eligible")}


def packet_for(candidate, derivation, derivation_row, units=(), intake_entry=None, call_id="c1",
               seat="propose"):
    """The S7 packet's bytes for one candidate, with the placement contract and its digest inside.

    The contract text travels whole rather than summarised: S7b judges the proposal against that
    same text, and a packet that paraphrased it would be a second authority for the bars."""
    facts = candidate_facts(candidate, derivation_row)
    payload = packet.render(TEMPLATE, {
        "candidate": json.dumps({**candidate, **facts}, ensure_ascii=False, indent=1),
        "judgments": json.dumps((derivation_row or {}).get("requirements") or {}, ensure_ascii=False,
                                indent=1),
        "derivation": json.dumps({"facts": facts, "unknowns": named_states(derivation)},
                                 ensure_ascii=False, indent=1),
        "units": json.dumps(list(units), ensure_ascii=False, indent=1),
        "intake_entry": json.dumps(intake_entry, ensure_ascii=False, indent=1) if intake_entry
                        else "none: this candidate comes from this window's sessions",
        "placement_contract": f"sha256:{placement.contract_digest()}\n\n{placement.contract_text()}",
        "returns": "Return one JSON object in the schema of this call.",
    }, template_dir=HERE / "packets")
    return packet.build(call_id, STAGE, seat, payload, schema=schema_bytes(), repo=HERE.parent)


def proposal_of(answer, candidate, derivation_row, legacy_incubating=False):
    """The flat proposal `placement.py` and `ranking.py` read, assembled from the answer and S6.

    The kind and the diagnosis come from the derivation here, which is the single place the two
    sources could have diverged."""
    facts = candidate_facts(candidate, derivation_row)
    held = {k: v for k, v in answer.items()}
    held.update({"item_id": candidate["candidate_id"], "candidate_id": candidate["candidate_id"],
                 "kind": facts["kind"], "diagnosis": facts["diagnosis"],
                 "legacy_incubating": bool(legacy_incubating),
                 "lineages": facts["lineages"] if isinstance(facts["lineages"], int) else 0,
                 "requires_test": answer.get("disposition") not in placement.LEDGER_ONLY + ("none",),
                 # Both read by `placement.py`'s promotion rule and by the legacy `place` condition.
                 # They come from S6's derivation, never from the answer: a proposal that declared
                 # its own eligibility would be judging its own bar.
                 "admitted": facts["admission"] == "admitted",
                 "promotion_eligible": facts["promotion"],
                 # The contract's own field names, filled from the answer rather than asked for twice:
                 # `reason` is the Korean reason the person reads (§7.3's reason fields), and `harmful`
                 # is the one flag a `reduce` needs that no other field carries.
                 "reason": (answer.get("reasons") or {}).get("reason"),
                 "harmful": answer.get("harmful")})
    return held


def awaiting_r(answer, candidate, derivation_row):
    """`(bool, reason)`: whether this proposal waits for an R comparison before it can be applied.

    A CORE item admitted by adjudication enters no F this run (§10): it is `awaiting_R`, and the
    reason is carried beside the row rather than written into its status, because §7.2's status
    vocabulary has no such value and inventing one would put a row in no §9 group. Core is read from
    the destination layer the table names - anything but `personal` - so the distinction has one
    owner."""
    facts = candidate_facts(candidate, derivation_row)
    if answer["disposition"] in placement.LEDGER_ONLY + ("none",):
        return False, "a ledger-only disposition enters no F"
    layer = (answer.get("destination") or {}).get("layer")
    if layer == "personal":
        return False, "a personal item admitted by adjudication proceeds (§10)"
    if facts["admission"] == "adjudication":
        return True, ("a core item admitted by adjudication is awaiting_R: it enters no F this run "
                      "and is tested against its own R comparison first (§10)")
    return False, "admitted directly, so its F is this run's"


def answer_problems(answer, candidate, derivation, derivation_row, active_keep=None,
                    legacy_incubating=False):
    """Every problem of one answer, by name: its shape, the contract, and the unknowns it must carry.

    Order matters only in that the shape comes first: a contract check over a malformed answer
    reports the malformation twice in different words."""
    problems = _shape_problems(answer)
    for field in DERIVED_FIELDS:
        if field in answer:
            problems.append(f"ANSWER_REDERIVES_DERIVED {field}: S6 derived it, so a proposal that "
                            f"carries its own would give the field two sources")
    if problems:
        return problems
    proposal = proposal_of(answer, candidate, derivation_row, legacy_incubating)
    problems += placement.problems(proposal, active_keep)
    # §10.4: a ledger-only disposition changes no installed instruction, so it carries no operations
    # and needs no test. The structural table owns the rest of §7.3; this one is §10.4's own sentence.
    if answer["disposition"] in placement.LEDGER_ONLY + ("none",) and answer.get("operations"):
        problems.append(f"LEDGER_ONLY_WITH_OPERATIONS {candidate['candidate_id']}: a "
                        f"{answer['disposition']} changes the ledger alone, and carries "
                        f"{len(answer['operations'])} library operation(s)")
    # The unknowns. A state the derivation named must be carried by name; a proposal may carry more
    # than the run has (a field it could not use for its own reason), but never fewer.
    wanted = {row["field"] for row in named_states(derivation)}
    carried = {row["field"] for row in answer.get("unknowns") or []}
    for field in sorted(wanted - carried):
        state = next(r["state"] for r in named_states(derivation) if r["field"] == field)
        problems.append(f"UNKNOWN_NOT_CARRIED {candidate['candidate_id']}.{field}={state}: the "
                        f"derivation named this state, so the proposal carries it forward rather "
                        f"than resting on an answer nobody has")
    for row in answer.get("unknowns") or []:
        if row["field"] not in {s["field"] for s in UNKNOWN_SOURCES}:
            problems.append(f"UNKNOWN_FIELD_UNDECLARED {row['field']}: not one of "
                            f"{', '.join(s['field'] for s in UNKNOWN_SOURCES)}")
    # §10's R rule, stated by the answer rather than inferred later: a core item admitted by
    # adjudication must say it requires an R, and one that does not is returned rather than carried
    # into an F it cannot enter.
    waits, _reason = awaiting_r(answer, candidate, derivation_row)
    if waits and answer.get("requires_R") is not True:
        problems.append(f"REQUIRES_R_ABSENT {candidate['candidate_id']}: a core item admitted by "
                        f"adjudication is awaiting_R, so its proposal says requires_R")
    return problems


def _shape_problems(answer):
    """The answer against its schema, through whichever validator this tree has."""
    try:
        import jsonschema
    except ImportError:  # the sandbox may lack it; the shape is then judged by the required keys
        schema = json.loads(schema_bytes())
        return [f"ANSWER_FIELD_ABSENT {name}" for name in schema["required"] if name not in answer]
    validator = jsonschema.Draft202012Validator(json.loads(schema_bytes()))
    return [f"ANSWER_INVALID {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in sorted(validator.iter_errors(answer), key=lambda e: list(e.absolute_path))]


def review_row(answer, candidate, derivation_row, status="proposed"):
    """The row `ranking.py` orders: the four §7.2 fields, the consequence, the lineages and the id."""
    facts = candidate_facts(candidate, derivation_row)
    return {"candidate_id": candidate["candidate_id"], "status": status,
            "kind": facts["kind"], "diagnosis": facts["diagnosis"],
            "disposition": answer["disposition"], "consequence": answer["consequence"],
            "lineages": facts["lineages"] if isinstance(facts["lineages"], int) else 0,
            "changes_library": answer["disposition"] not in placement.LEDGER_ONLY + ("none",)}


def document(derivations, candidates, answers, active_keep=None, legacy=()):
    """`proposals.json`: every candidate answered, ranked, with each refusal named and counted.

    A candidate whose answer does not hold is NOT dropped and not silently re-asked: its row carries
    `status: returned` with the problems, because a proposal missing from the document is a candidate
    nobody decided."""
    rows = {r["candidate_id"]: r for r in (candidates or {}).get("candidates") or []}
    verdicts = (derivations or {}).get("verdicts") or {}
    legacy_ids = set(legacy or ())
    proposals, returned = [], []
    for cid in sorted(rows):
        answer = (answers or {}).get(cid)
        if answer is None:
            returned.append({"candidate_id": cid, "problems": [f"ANSWER_ABSENT {cid}: S7 made no "
                                                               f"proposal for a candidate it was given"]})
            continue
        problems = answer_problems(answer, rows[cid], derivations, verdicts.get(cid), active_keep,
                                   cid in legacy_ids)
        if problems:
            returned.append({"candidate_id": cid, "problems": problems})
            continue
        waits, why = awaiting_r(answer, rows[cid], verdicts.get(cid))
        proposals.append({**review_row(answer, rows[cid], verdicts.get(cid)), "proposal": answer,
                          "legacy_incubating": cid in legacy_ids,
                          "awaiting_R": waits, "awaiting_R_reason": why})
    not_derived = [r["candidate_id"] for r in (derivations or {}).get("not_derived") or []]
    tally = collections.Counter
    return {"stage": STAGE,
            "proposals": ranking.ranked(proposals),
            "returned": sorted(returned, key=lambda r: r["candidate_id"]),
            "unknowns_in_force": named_states(derivations or {}),
            "not_derived": sorted(not_derived),
            "contract": {"placement_contract_sha256": placement.contract_digest(),
                         "schema_sha256": packet.sha256_bytes(schema_bytes())},
            "counts": {"candidates": len(rows), "proposed": len(proposals), "returned": len(returned),
                       "not_derived": len(not_derived),
                       "awaiting_R": sum(1 for p in proposals if p["awaiting_R"]),
                       "disposition": dict(tally(p["disposition"] for p in proposals)),
                       "status_group": dict(tally(p["status_group"] for p in ranking.ranked(proposals)))}}


def run(run_dir, answers, active_keep=None, legacy=()):
    """The stage, through the shared mechanism: nothing is written on refusal."""
    run_dir = pathlib.Path(run_dir)
    with records.run_stage(run_dir, STAGE, INPUTS) as stage:
        derivations = records.read_json(run_dir / "judgments" / "derivations.json")
        candidates = records.read_json(run_dir / "checked-candidates.json")
        doc = document(derivations, candidates, answers, active_keep, legacy)
        records.write_json(run_dir, "proposals.json", doc)
        return stage, doc


# ---- the O5 fixture library ----------------------------------------------------------------------
# Each case runs the REAL functions on a real-shaped candidate, derivation and answer, and its answer
# is frozen in `tables/propose_fixtures.json`. A changed answer fails by name, a case the table does
# not hold fails as ROW_UNFIXTURED, and a frozen case no plant produces fails as FIXTURE_ORPHAN -
# the mechanism WP-10's and WP-11b's libraries use, for the same reason: a fixture that drifts with
# the code it judges proves the code agrees with itself.

def _candidate(cid="k1", kind="gap", diagnosis="gap", admission="admitted", eligible=True,
               lineages=3, ctype="D"):
    return ({"candidate_id": cid, "type": ctype, "admission": {"admission": admission}},
            {"outcome": {"kind": {"kind": kind},
                         "candidate_diagnosis": {"current": {"diagnosis": diagnosis}},
                         "admission": {"admission": admission},
                         "promotion": {"eligible": eligible}},
             "lineages": lineages, "requirements": {}})


def _answered(**over):
    """A complete answer in the schema's shape, which each case then varies by one field."""
    held = {"disposition": "place", "consequence": "quality",
            "operations": [{"type": "create", "target": "claude/guides/g.md",
                            "before_state_sha256": "absent", "content": "the text"}],
            "artifact_set": {"english": "the text", "korean": "한글 번역",
                             "registration": "router line", "gate_change": None},
            "behavior_contract": {"recognition": "r", "completed_action": "a", "meaning": "m",
                                  "boundary": "b", "competing_value": "c",
                                  "roles_and_routes": ["coding"], "failure_criteria": ["f"]},
            "expected_observation": None,
            "destination": {"layer": "guides", "carrier": "claude/guides/g.md", "situation": "s"},
            "reasons": {"what_happened": "무엇이 있었는가", "proposal": "제안", "reason": "이유",
                        "cost": "비용", "serves": "누구에게", "falsifier": "반증"},
            "unknowns": []}
    held.update(over)
    return held


ANSWERED = {"unit_outcomes": {"state": "derived"}, "delivery": {"state": "assembled"},
            "arc_confirmation": {"state": "confirmed"}, "points": {"release": {"state": "judged"}}}
# What release 1 actually hands S7 (lane E's J4a): three named states and an unjudged release point.
RELEASE_1 = {"unit_outcomes": {"state": "none", "candidates": 7},
             "delivery": {"state": "delivery_assembly_waiting", "pairs": 12},
             "arc_confirmation": {"state": "undetermined", "passed_as": False},
             "points": {"release": "absent (D-20261111-c4fa71)"}}
CARRIED = [{"field": r["field"], "state": r["state"], "effect": "proposed on the rest"}
           for r in ()]  # filled per case from named_states


def _carry(derivation):
    return [{"field": r["field"], "state": r["state"],
             "effect": "the proposal rests on the remaining evidence and says so"}
            for r in named_states(derivation)]


# The real S3-03 as the author-side ledger holds it (design/session-distill/ledger.json, read
# 2026-11-11): status incubating, no classification block, two legacy decision lines and the
# migration row, and NO mapped schema-2 decision. Carried as a constant rather than read from
# `design/`, because this module ships and that file does not.
S3_03 = {"id": "S3-03", "status": "incubating", "kind": "unclassified", "diagnosis": "unknown",
         "disposition": "none",
         "decisions": [{"run": "legacy-unknown", "disposition": "unknown", "approval_id": "legacy",
                        "at": "2026-07-19", "field": "decision1",
                        "legacy_text": "user-approved-default 2026-07-19"},
                       {"run": "legacy-unknown", "disposition": "unknown", "approval_id": "legacy",
                        "at": "2026-07-19", "field": "decision2",
                        "legacy_text": "recommendation-confirmed 2026-07-19"},
                       {"run": "legacy-unknown", "kind": "legacy_migration", "disposition": "unknown",
                        "field": "status", "legacy_text": "incubating"}]}
# Its counterpart: the same shape WITH a mapped schema-2 incubate decision (the plan's F-O5-10).
S3_03_MAPPED = {**S3_03, "id": "S2-99",
                "decisions": [*S3_03["decisions"],
                              {"run": "r-2026-11", "kind": "judgment", "disposition": "incubate",
                               "approval_id": "a1",
                               "expected_observation": {"occasion": "같은 상황이 다시 온다",
                                                        "exposure_rule": "선택되고 읽힌다",
                                                        "expected_behavior": "에이전트가 그대로 한다",
                                                        "retrieval_terms": ["그 말"],
                                                        "expiry": "2027-02-01", "counter": None}}]}


def fixture_cases():
    """The O5 plants this stage owns, each with the real inputs it runs on."""
    keep_cand, keep_row = _candidate("k-keep", "confirmed", "covered")
    red_cand, red_row = _candidate("k-reduce", "misfire", "covered")
    merge_cand, merge_row = _candidate("k-merge", "misfire", "redundant")
    nd_cand, nd_row = _candidate("k-nd", "not delivered", "unknown")
    adj_cand, adj_row = _candidate("k-adj", admission="adjudication")
    g_cand, g_row = _candidate("k-g", ctype="G", eligible=False, lineages=1)
    return (
        {"id": "F-O5-01", "plant": "evidence supporting keep", "candidate": keep_cand,
         "row": keep_row, "derivation": ANSWERED,
         "answer": _answered(disposition="keep", operations=[], expected_observation=None,
                             destination={"layer": "incubator", "carrier": None},
                             reasons={**_answered()["reasons"], "reason": "이 단위는 그대로 둔다"})},
        {"id": "F-O5-02", "plant": "evidence supporting re-deliver", "candidate": nd_cand,
         "row": nd_row, "derivation": ANSWERED,
         "answer": _answered(disposition="re-deliver",
                             operations=[{"type": "route", "target": "router/relevant.md",
                                          "names": "claude/guides/g.md",
                                          "before_state_sha256": "a" * 64}],
                             destination={"layer": "session_injection", "carrier": "router/relevant.md",
                                          "situation": "the same situation"})},
        {"id": "F-O5-03", "plant": "evidence supporting reduce", "candidate": red_cand,
         "row": red_row, "derivation": ANSWERED,
         "answer": _answered(disposition="reduce", harmful=True,
                             operations=[{"type": "delete", "target": "claude/guides/g.md",
                                          "anchor": "## a bullet", "before_state_sha256": "b" * 64}],
                             destination={"layer": "guides", "carrier": "claude/guides/g.md"})},
        {"id": "F-O5-04", "plant": "redundant pair of working units", "candidate": merge_cand,
         "row": merge_row, "derivation": ANSWERED,
         "answer": _answered(disposition="reduce",
                             operations=[{"type": "merge", "target": "claude/guides/g.md#one",
                                          "units": ["u1", "u2"], "before_state_sha256": "c" * 64,
                                          "content": "one bullet for both"}],
                             destination={"layer": "guides", "carrier": "claude/guides/g.md"})},
        {"id": "F-O5-08", "plant": "core item admitted by adjudication", "candidate": adj_cand,
         "row": adj_row, "derivation": ANSWERED, "answer": _answered(requires_R=True)},
        {"id": "F-O5-08b", "plant": "the same admission on a personal item", "candidate": adj_cand,
         "row": adj_row, "derivation": ANSWERED,
         "answer": _answered(destination={"layer": "personal", "carrier": "~/notes/own.md"})},
        {"id": "F-O5-15", "plant": "a type G candidate below the lineage bar", "candidate": g_cand,
         "row": g_row, "derivation": ANSWERED, "answer": _answered()},
        {"id": "F-O5-15b", "plant": "the same candidate proposed as incubate instead",
         "candidate": g_cand, "row": g_row, "derivation": ANSWERED,
         "answer": _answered(disposition="incubate", operations=[],
                             destination={"layer": "incubator", "carrier": None},
                             expected_observation={"occasion": "the same situation again",
                                                   "exposure_rule": "selected and read",
                                                   "expected_behavior": "the agent does it",
                                                   "retrieval_terms": ["the term"],
                                                   "expiry": "2027-02-01", "counter": None})},
        {"id": "F-O5-RELEASE1", "plant": "release 1's three named states, carried forward",
         "candidate": _candidate("k-r1")[0], "row": _candidate("k-r1")[1], "derivation": RELEASE_1,
         "answer": _answered(unknowns=_carry(RELEASE_1))},
        {"id": "F-O5-RELEASE1b", "plant": "the same, with one state not carried",
         "candidate": _candidate("k-r1b")[0], "row": _candidate("k-r1b")[1], "derivation": RELEASE_1,
         "answer": _answered(unknowns=_carry(RELEASE_1)[1:])},
    )


def legacy_fixture_cases():
    """The legacy plants (F-O5-09, -10, -13), answered by code under the owner's decided row."""
    classified = {**S3_03, "id": "S2-07",
                  "classification": {"type": "F", "layer": "guide", "meets_promotion_bar": False}}
    return (
        {"id": "F-O5-09", "plant": "legacy S3-03: no mapped decision, no classification block",
         "entry": S3_03},
        {"id": "F-O5-10", "plant": "a legacy entry with a mapped incubate decision",
         "entry": S3_03_MAPPED},
        # -13 is a different entry from -09 on purpose: its legacy line is a `below-bar-default`, the
        # largest of the owner's three groups, so the fixture shows the group naming and not only the
        # default. Under the owner's decision its disposition is the same as -09's, which is what
        # "stays in the intake" means here.
        {"id": "F-O5-13", "plant": "one left at none stays in the legacy intake, in another group",
         "entry": {**S3_03, "id": "S2-11",
                   "decisions": [{"field": "decision1", "legacy_text": "below-bar-default 2026-07-18",
                                  "disposition": "unknown", "approval_id": "legacy"},
                                 {"field": "status", "kind": "legacy_migration",
                                  "legacy_text": "incubating", "disposition": "unknown"}]}},
        {"id": "F-O5-09b", "plant": "the same entry with a classification block reaches a call",
         "entry": classified},
    )


def run_legacy_fixture(case):
    """What code answers for one legacy entry: whether a call is spent, and the default it makes."""
    entry = case["entry"]
    answer = legacy_answer(entry)
    return {"call_spent": call_spent_on(entry), "disposition": answer["disposition"],
            "entered_with_decision": answer["entered_with_decision"],
            "group": answer["legacy_group"], "entry_id": entry.get("id"),
            "observation": bool(answer.get("expected_observation"))}


def run_fixture(case):
    """The real answer for one case: its problems, and what the row says about it."""
    problems = answer_problems(case["answer"], case["candidate"], case["derivation"], case["row"])
    waits, why = awaiting_r(case["answer"], case["candidate"], case["row"])
    return {"problems": problems, "awaiting_R": waits, "awaiting_R_reason": why,
            "disposition": case["answer"]["disposition"]}


def generate_fixtures():
    return {"$comment": "Frozen answers of the O5 plants S7 owns (WP-12). Regenerate deliberately: a "
                        "changed answer here is a changed contract, and the suite names the case.",
            "cases": [{"id": case["id"], "plant": case["plant"], **run_fixture(case)}
                      for case in fixture_cases()],
            "legacy_cases": [{"id": case["id"], "plant": case["plant"], **run_legacy_fixture(case)}
                             for case in legacy_fixture_cases()]}


def fixture_problems():
    """The frozen table against the real answers, both ways."""
    if not FIXTURES_PATH.is_file():
        return [f"FIXTURES_ABSENT {FIXTURES_PATH}: every §7.2 state path would be judged by nothing"]
    held = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    frozen = {row["id"]: row for row in held["cases"] + held.get("legacy_cases", [])}
    made = generate_fixtures()
    live = {row["id"]: row for row in made["cases"] + made["legacy_cases"]}
    problems = [f"ROW_UNFIXTURED {cid}: this plant has no frozen answer" for cid in sorted(set(live) - set(frozen))]
    problems += [f"FIXTURE_ORPHAN {cid}: a frozen answer no plant produces" for cid in sorted(set(frozen) - set(live))]
    for cid in sorted(set(live) & set(frozen)):
        if live[cid] != frozen[cid]:
            problems.append(f"FIXTURE_CHANGED {cid}: the answer is no longer the frozen one "
                            f"({frozen[cid].get('problems')} -> {live[cid].get('problems')})")
    return problems


# ---- self-test -----------------------------------------------------------------------------------

def self_test():
    """The fixtures, then one planted violation per rule, each named.

    Golden only: no model call is made here and none is made by this module - S7's call is the
    driver's, and this suite judges the packet it would send and the answer it would receive."""
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

    def _said_without_default():
        """The loader's refusal with its case PLANTED: a legacy row stripped of its owner_default.

        The table is restored on the way out, and the control after this one judges the real one, so
        a plant that leaked would be visible rather than silent."""
        held = placement.table("pairs")
        row = [r for r in held["rows"] if r.get("legacy_incubating")][0]
        kept = row.pop("owner_default")
        try:
            try:
                legacy_default()
            except Refused as exc:
                return str(exc)
            return ""
        finally:
            row["owner_default"] = kept

    def said(answer, candidate=None, derivation=None, row=None, keep=None, legacy=False):
        cand, drow = _candidate()
        return "; ".join(answer_problems(answer, candidate or cand, derivation or ANSWERED,
                                         row if row is not None else drow, keep, legacy))

    # The library, both ways.
    clean("every O5 plant this stage owns answers what its frozen fixture says", fixture_problems())
    control("and the library holds the ten plants, not a subset",
            str(len(json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["cases"])), "10")
    for case in fixture_cases():
        clean(f"{case['id']} runs the real function on a real-shaped answer ({case['plant']})",
              [] if isinstance(run_fixture(case)["problems"], list) else ["not a list"])

    # F-O5-01..04: the four dispositions evidence supports, each clean on its own pair and refused on
    # a pair §7.2 does not allow, so neither reading is a coincidence of the fixture.
    ids = {case["id"]: case for case in fixture_cases()}
    for fid, disposition in (("F-O5-01", "keep"), ("F-O5-02", "re-deliver"), ("F-O5-03", "reduce"),
                             ("F-O5-04", "reduce")):
        case = ids[fid]
        clean(f"{fid}: the evidence's own disposition ({disposition}) passes the contract",
              run_fixture(case)["problems"])
        control(f"{fid}: the same answer under a pair that does not allow it is refused by name",
                said({**case["answer"], "disposition": "place"}, case["candidate"], case["derivation"],
                     case["row"]),
                "PAIR_DISALLOWED")
    control("F-O5-01: a keep with no reason is refused, which is what makes its reason load-bearing",
            said({**ids["F-O5-01"]["answer"],
                  "reasons": {**ids["F-O5-01"]["answer"]["reasons"], "reason": " "}},
                 ids["F-O5-01"]["candidate"], ANSWERED, ids["F-O5-01"]["row"]),
            "REASON_REQUIRED")
    control("F-O5-03: a reduce on a covered unit that is not claimed harmful is refused",
            said({**ids["F-O5-03"]["answer"], "harmful": False}, ids["F-O5-03"]["candidate"],
                 ANSWERED, ids["F-O5-03"]["row"]),
            "PAIR_DISALLOWED")
    control("F-O5-04: the merge operation IS the condition, so the same answer without it is refused",
            said({**ids["F-O5-04"]["answer"], "operations": []}, ids["F-O5-04"]["candidate"],
                 ANSWERED, ids["F-O5-04"]["row"]),
            "PAIR_DISALLOWED")

    # F-O5-08: awaiting_R, and the personal counterpart that proceeds.
    control("F-O5-08: a core item admitted by adjudication is awaiting_R",
            str(run_fixture(ids["F-O5-08"])["awaiting_R"]), "True")
    control("and the row says why, in §10's terms", run_fixture(ids["F-O5-08"])["awaiting_R_reason"],
            "enters no F this run")
    control("a core item admitted by adjudication whose proposal does not say requires_R is returned",
            said({k: v for k, v in ids["F-O5-08"]["answer"].items() if k != "requires_R"},
                 ids["F-O5-08"]["candidate"], ANSWERED, ids["F-O5-08"]["row"]),
            "REQUIRES_R_ABSENT")
    control("F-O5-08b: the same admission on a PERSONAL item proceeds",
            str(run_fixture(ids["F-O5-08b"])["awaiting_R"]), "False")
    control("and it says so rather than being silent", run_fixture(ids["F-O5-08b"])["awaiting_R_reason"],
            "personal item admitted by adjudication proceeds")
    control("an item admitted directly is not awaiting_R either, and says that",
            awaiting_r(_answered(), *_candidate())[1], "admitted directly")
    clean("a ledger-only disposition enters no F whatever its admission",
          [] if awaiting_r(_answered(disposition="keep", operations=[]),
                           *_candidate(admission="adjudication"))[0] is False
          else ["a keep read as awaiting_R"])

    # F-O5-15: the type G candidate below the lineage bar. G_ANTI_ABSTRACTION itself is S4's
    # (`stage_form.py` refuses a G candidate without its sides, ordering, prohibition and three
    # instances); what S7 owns is the bar - such a candidate may be proposed only as incubate, keep
    # or drop, never placed.
    control("F-O5-15: a type G candidate below the lineage bar cannot be placed",
            "; ".join(run_fixture(ids["F-O5-15"])["problems"]), "below the promotion bar")
    clean("F-O5-15b: the same candidate proposed as incubate with an observation and an expiry passes",
          run_fixture(ids["F-O5-15b"])["problems"])
    control("and an incubate with no expiry is refused, so the observation is load-bearing",
            said({**ids["F-O5-15b"]["answer"], "expected_observation": None},
                 ids["F-O5-15b"]["candidate"], ANSWERED, ids["F-O5-15b"]["row"]),
            "EXPIRY_REQUIRED")

    # Release 1's named states, which is the interface lane E's J4a actually hands S7.
    control("release 1's derivation carries four named states, not an empty unit outcome",
            str(len(named_states(RELEASE_1))), "4")
    control("and the state is read as the document spells it, not as a boolean",
            json.dumps(named_states(RELEASE_1)[0]), '"state": "none"')
    clean("a proposal that carries every named state forward passes",
          run_fixture(ids["F-O5-RELEASE1"])["problems"])
    control("one that drops a state is returned, naming the field and the state",
            "; ".join(run_fixture(ids["F-O5-RELEASE1b"])["problems"]),
            "UNKNOWN_NOT_CARRIED k-r1b.unit_outcomes=none")
    clean("a derivation that answered everything demands nothing be carried", named_states(ANSWERED))
    control("a field missing from the derivation altogether is a state, not a silence",
            json.dumps(named_states({})), '"state": "absent"')
    control("and an unknown this module does not declare is refused rather than accepted as extra",
            said(_answered(unknowns=[{"field": "mood", "state": "none", "effect": "none"}])),
            "UNKNOWN_FIELD_UNDECLARED")

    # The legacy intake, under the row the owner decided on 2026-11-11 (D-20261111-e53a01). The
    # default and the call rule are READ from the table, so this suite judges the decision as data
    # and not a copy of it.
    legacy = {case["id"]: case for case in legacy_fixture_cases()}
    clean("every legacy plant answers what its frozen fixture says",
          [p for p in fixture_problems() if "F-O5-09" in p or "F-O5-10" in p or "F-O5-13" in p])
    control("the owner's default is read from the legacy row, not held here",
            legacy_default()["disposition"], "none")
    control("and so is the rule for which entries reach a call",
            legacy_default()["call_spent"], "classified_only")
    control("F-O5-09: S3-03 carries no classification block, so no call is spent on it",
            str(run_legacy_fixture(legacy["F-O5-09"])["call_spent"]), "False")
    control("and its proposal is the owner's default",
            run_legacy_fixture(legacy["F-O5-09"])["disposition"], "none")
    control("F-O5-09b: the same entry WITH a classification block reaches a call, so the rule is the "
            "block and not the id", str(run_legacy_fixture(legacy["F-O5-09b"])["call_spent"]), "True")
    control("F-O5-10: an entry with a mapped incubate decision enters with it rather than with the "
            "default", run_legacy_fixture(legacy["F-O5-10"])["disposition"], "incubate")
    control("and its observation comes from that decision, not from this code",
            str(run_legacy_fixture(legacy["F-O5-10"])["observation"]), "True")
    control("and it says it entered with a decision, so the two cases are told apart by a field "
            "rather than by the absence of one",
            str(run_legacy_fixture(legacy["F-O5-10"])["entered_with_decision"]), "True")
    control("F-O5-13: an entry of the largest group stays in the intake, and its group is named",
            run_legacy_fixture(legacy["F-O5-13"])["group"], "below-bar-default")
    # The swapped control the plan asks for: each answer must name its own entry, and swapping the
    # two entries must change both answers. An answer that did not depend on its entry would pass
    # the first half and fail this one.
    nine, ten = legacy["F-O5-09"]["entry"], legacy["F-O5-10"]["entry"]
    control("the S3-03 answer names S3-03", run_legacy_fixture(legacy["F-O5-09"])["entry_id"], "S3-03")
    control("and the mapped entry's answer names the mapped entry",
            run_legacy_fixture(legacy["F-O5-10"])["entry_id"], "S2-99")
    control("swapped, the two fixtures fail by entry id: the id of each answer follows its entry",
            f'{run_legacy_fixture({"entry": ten})["entry_id"]}/'
            f'{run_legacy_fixture({"entry": nine})["entry_id"]}', "S2-99/S3-03")
    control("and swapping changes the disposition too, so neither answer is entry-independent",
            f'{run_legacy_fixture({"entry": ten})["disposition"]}/'
            f'{run_legacy_fixture({"entry": nine})["disposition"]}', "incubate/none")
    migrated_as_incubate = {**S3_03, "id": "S2-77",
                            "decisions": [{"field": "status", "kind": "legacy_migration",
                                           "disposition": "incubate",
                                           "legacy_text": "incubating"}]}
    control("a legacy_migration row that carries the word incubate is still not a mapped decision: it "
            "records the migration of a status, not a judgment",
            str(legacy_answer(migrated_as_incubate)["entered_with_decision"]), "False")
    control("so such an entry takes the owner's default",
            legacy_answer(migrated_as_incubate)["disposition"], "none")
    clean("a legacy default carries no library operation, which is what none_stays_in_intake asks",
          [case["id"] for case in legacy_fixture_cases()
           if legacy_answer(case["entry"])["operations"]])
    # The split, counted over the entries the run holds rather than remembered.
    split = legacy_split([case["entry"] for case in legacy_fixture_cases()])
    control("the split counts the calls and the defaults of THIS run",
            f"{split['counts']['entries']}={split['counts']['calls']}+{split['counts']['defaults']}",
            "4=1+3")
    control("and names the groups it found, rather than the owner's figure of the day",
            json.dumps(sorted(split["groups"])), "below-bar-default")
    control("a legacy row with no owner_default is refused, so an undecided default cannot be applied "
            "silently", _said_without_default(), "LEGACY_DEFAULT_UNDECLARED")
    # The owner's sentence reaches the model, not only the table: the packet is where a proposal is
    # actually shaped, and a decision that lived only in a table would be a decision the caller
    # never reads.
    packet_text = (HERE / "packets" / TEMPLATE).with_suffix(".md").read_text(encoding="utf-8")
    control("the packet carries the owner's decided sentence for a legacy entry", packet_text,
            str(legacy_default().get("text") or "<the legacy row states no sentence>").split(".")[0])
    control("and tells the reader that the entry's own history is not this window's evidence",
            packet_text, "it is the record of an earlier default")

    # The two sources rule, §10.4, and the shape.
    control("an answer that carries its own kind is refused: S6 derived it",
            said({**_answered(), "kind": "gap"}), "ANSWER_REDERIVES_DERIVED")
    control("its own diagnosis too", said({**_answered(), "diagnosis": "gap"}),
            "ANSWER_REDERIVES_DERIVED")
    control("a ledger-only disposition carrying a library operation is refused by §10.4",
            said(_answered(disposition="keep",
                           reasons={**_answered()["reasons"], "reason": "그대로"}),
                 *_candidate("k-keep", "confirmed", "covered")[:1],
                 row=_candidate("k-keep", "confirmed", "covered")[1]),
            "LEDGER_ONLY_WITH_OPERATIONS")
    control("an answer missing a required field is named by the field",
            said({k: v for k, v in _answered().items() if k != "reasons"}), "reasons")
    control("an operation with no before-state hash is named, because §7.3 asks every one for it",
            said(_answered(operations=[{"type": "create", "target": "claude/guides/g.md"}])),
            "before_state_sha256")
    control("a disposition outside §7.2's vocabulary is refused by the schema, not by a guess",
            said(_answered(disposition="rewrite")), "ANSWER_INVALID")

    # The packet: the contract travels whole, with its digest, and the derived fields are given.
    built = packet_for(_candidate()[0], ANSWERED, _candidate()[1])
    text = built.decode("utf-8")
    control("the packet carries the placement contract's own text", text, "## The bars")
    control("and its digest, so a reader can bind the bars the proposal was judged by", text,
            f"sha256:{placement.contract_digest()}")
    control("and the schema the answer is held to, by digest in the envelope", text,
            f"SCHEMA: sha256:{packet.sha256_bytes(schema_bytes())}")
    between = text.split("<candidate>", 1)[-1].split("</candidate>", 1)[0]
    control("the packet gives the derived kind inside the candidate block rather than asking for it",
            between, '"kind": "gap"')
    clean("and the block is the candidate's, not the whole packet, which the derivation block would "
          "have satisfied on its own",
          [] if "<judgments>" not in between else ["the span reaches past the candidate block"])
    control("and it names the states the derivation could not answer", 
            packet_for(_candidate()[0], RELEASE_1, _candidate()[1]).decode("utf-8"),
            "delivery_assembly_waiting")
    control("a packet for a lifecycle candidate carries its ledger entry",
            packet_for(_candidate()[0], ANSWERED, _candidate()[1],
                       intake_entry={"id": "S3-03", "status": "incubating"}).decode("utf-8"),
            '"S3-03"')
    control("and one for a session candidate says plainly that there is none",
            text, "none: this candidate comes from this window's sessions")

    # The document: nothing is dropped, and every refusal is counted.
    cands = {"candidates": [_candidate("k1")[0], _candidate("k2")[0], _candidate("k3")[0]]}
    derivations = {"verdicts": {"k1": _candidate("k1")[1], "k2": _candidate("k2")[1],
                                "k3": _candidate("k3")[1]},
                   "not_derived": [{"candidate_id": "k9", "why": "a judge's call did not finish"}],
                   **ANSWERED}
    doc = document(derivations, cands, {"k1": _answered(), "k2": _answered(disposition="rewrite")})
    control("a candidate whose answer does not hold is returned, not dropped",
            json.dumps(doc["returned"]), "k2")
    control("a candidate with no answer at all is returned too, by name",
            json.dumps(doc["returned"]), "ANSWER_ABSENT k3")
    control("and the counts reconcile with the candidates given",
            f"{doc['counts']['candidates']}={doc['counts']['proposed']}+{doc['counts']['returned']}",
            "3=1+2")
    control("S6's own not_derived candidates are carried, so they are visible rather than missing",
            json.dumps(doc["not_derived"]), "k9")
    control("every proposal carries its rank", str([p["rank"] for p in doc["proposals"]]), "[1]")
    control("the document binds the contract text it was judged by",
            doc["contract"]["placement_contract_sha256"], placement.contract_digest())
    clean("and carries no instruction text of the person's own: the answers' own fields only",
          [k for k in doc if k in ("instruction_text", "compiled_text", "units_text")])

    reporting.append(True)
    if failures:
        for name, detail in failures:
            print(f"stage_propose --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"stage_propose --self-test: FAILED ({len(failures)} of {len(ran)} controls)",
              file=sys.stderr)
        return 1
    print(f"stage_propose --self-test: OK ({len(ran)} controls: the ten O5 plants against their frozen "
          f"answers, each disposition clean on its own pair and refused on another, awaiting_R for a "
          f"core item admitted by adjudication and not for its personal counterpart, the type G "
          f"candidate held below the lineage bar, release 1's four named states carried forward or "
          f"returned by name, the two-sources rule, §10.4's ledger-only rule, and the packet carrying "
          f"the contract whole with its digest)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-test"]:
        sys.exit(self_test())
    if sys.argv[1:2] == ["--freeze-fixtures"]:
        FIXTURES_PATH.write_text(json.dumps(generate_fixtures(), ensure_ascii=False, indent=1) + "\n",
                                 encoding="utf-8")
        print(f"stage_propose: froze {len(generate_fixtures()['cases'])} fixtures into {FIXTURES_PATH}")
        sys.exit(0)
    sys.exit("usage: stage_propose.py --self-test | --freeze-fixtures")
