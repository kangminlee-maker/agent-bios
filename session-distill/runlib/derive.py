#!/usr/bin/env python3
"""The derivations of design §6.4 (WP-10): two judges' judgments and the delivery states in; each unit's diagnosis,
the candidate's diagnosis per reference point, the unit outcomes, the kind, the admission and the promotion
eligibility out.

Every rule is read from `tables/unit_outcome.json`, the one source this code and its fixture generator both read:
the table's rows decide, and this module only says how a row is matched. A row the code never reaches is visible by
name, because the generator wrote one frozen fixture per row (`--generate-fixtures`, once) and the self-test runs
every fixture through these functions and compares three sets - the table's rows, the frozen fixtures and the cases
the run executed (WP-10 done-when 1, the pattern of `ledger.py`'s transition fixtures).

Two judges answer every judged field (§6.2). Where they agree, the field takes their value; where they differ it is
`disputed`, shown with both values, and the owner's adjudication (§10.1 `판정`, §10.2) supplies the value the
derivation is computed again with. A disputed following or contribution is matched as the table's `unknown`; a
disputed situation or action leaves the unit's diagnosis `disputed`, which only a row accepting every diagnosis
matches, and the outcome is `unknown` otherwise; a disputed unit that could outrank the candidate's best agreed
diagnosis leaves the candidate's diagnosis `unknown`.

A candidate's units are judged at two reference points: `release` (the session's time) and `current`. Unit outcomes
are read at `release`, one per unit and session, because delivery is a fact about a session; `current` answers
only whether a gap has since been covered (`already resolved`). An absence - the diagnosis `gap` - holds only at a
complete reference point (§6.4); which completeness is read is the table's `absence_completeness` policy, and every
absence answer names the layers it read.

Release 1 runs no S8 (D-20261111-818391): every derivation takes a named test state, `untested: s8_deferred`, never a
blank; no row of §6.4 needs a test result, and each row says so in its own `test` column.

  derive.py --self-test
  derive.py --generate-fixtures [PATH]
"""
import copy
import itertools
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
TABLE_PATH = HERE / "tables" / "unit_outcome.json"
FIXTURES_PATH = HERE / "tables" / "unit_outcome_fixtures.json"
SECTIONS = ("unit_diagnosis", "unit_outcome", "candidate_diagnosis", "kind", "admission", "promotion")
DISPUTED = "disputed"
WILD = ("any", "—")
JUDGED = ("situation", "action", "following", "contribution")
POINTS = ("release", "current")

_TABLES = {}


def table():
    """The §6.4 table, read once per process; a control may hold a scratch copy in `_TABLES["t"]`."""
    if "t" not in _TABLES:
        _TABLES["t"] = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    return _TABLES["t"]


def row_ids(held=None):
    held = held or table()
    return [f"{section}/{row['id']}" for section in SECTIONS for row in held[section]]


def accepted(column, domain):
    """The values a column of the unit-outcome table accepts: its domain for `any` or `—`, else its list."""
    return list(domain) if column in WILD else list(column)


# ---- the judged fields --------------------------------------------------------------------------

def agreed(a, b):
    """One judged field from the two judges: their value when they agree, `disputed` when they differ."""
    return a if a == b else DISPUTED


def unit_diagnosis(situation, action):
    """§6.4's unit diagnosis from a situation and an action match, each `yes` or `no` - or `disputed`."""
    if DISPUTED in (situation, action):
        return DISPUTED
    for row in table()["unit_diagnosis"]:
        if (row["situation"], row["action"]) == (situation, action):
            return row["diagnosis"]
    raise Refused(f"JUDGMENT_INVALID situation {situation!r}, action {action!r}: a match is one of "
                  f"{table()['domains']['judged']}")


def outcome_row(diagnosis, delivery, following, contribution):
    """`(row id, outcome)` of the unit-outcome row these values select. A disputed following or contribution is
    matched as `unknown`; a disputed diagnosis only by a row accepting every diagnosis, and `("disputed", "unknown")`
    when none does. Exactly one row matches any other combination (`table_problems` holds the table total)."""
    domains = table()["domains"]
    following = "unknown" if following == DISPUTED else following
    contribution = "unknown" if contribution == DISPUTED else contribution
    for name, value in (("delivery", delivery), ("following", following), ("contribution", contribution)):
        if value not in domains[name]:
            raise Refused(f"JUDGMENT_INVALID {name} {value!r}: one of {domains[name]}")
    hits = [row for row in table()["unit_outcome"]
            if (row["diagnosis"] in WILD or diagnosis in row["diagnosis"])
            and delivery in accepted(row["delivery"], domains["delivery"])
            and following in accepted(row["following"], domains["following"])
            and contribution in accepted(row["contribution"], domains["contribution"])]
    if len(hits) > 1:
        raise Refused(f"TABLE_AMBIGUOUS {[row['id'] for row in hits]}: rows overlap at ({diagnosis}, {delivery}, "
                      f"{following}, {contribution})")
    if not hits:
        if diagnosis == DISPUTED:
            return DISPUTED, "unknown"
        raise Refused(f"TABLE_NOT_TOTAL ({diagnosis}, {delivery}, {following}, {contribution}): no row selects it")
    return hits[0]["id"], hits[0]["outcome"]


def candidate_diagnosis(units, complete, lifecycle=None):
    """`(diagnosis, row id)` over a reference point's unit diagnoses: `units` maps a unit id to its diagnosis, or to
    `(disputed, [A's, B's])`. A redundancy candidate with enough covering units is `redundant`; otherwise the first
    precedence row an agreed unit reaches; `gap` only at a complete reference point; `unknown` when a disputed unit
    could reach a row before the agreed one."""
    rows = table()["candidate_diagnosis"]
    agreed_diagnoses = [d for d in units.values() if not isinstance(d, tuple)]
    possible = [p for d in units.values() if isinstance(d, tuple) for p in d[1]]
    for row in rows:
        if row.get("lifecycle") and lifecycle == row["lifecycle"] \
                and agreed_diagnoses.count("covers") >= row["covering_units_at_least"]:
            return row["diagnosis"], row["id"]
    ladder = [row for row in rows if not row.get("lifecycle")]
    for rank, row in enumerate(ladder):
        if row["if_any_unit"] is None or row["if_any_unit"] in agreed_diagnoses:
            if any(earlier["if_any_unit"] in possible for earlier in ladder[:rank]):
                return "unknown", DISPUTED
            if row["if_any_unit"] is None and not complete:
                return row["incomplete"], row["id"]
            return row["diagnosis"], row["id"]
    raise Refused("TABLE_NOT_TOTAL candidate diagnosis: no precedence row is reached")


def absence(point):
    """`(complete, read)` for an absence at one reference point under the table's policy: `literal` reads the point's
    own flag (§6.1), `scoped` the statuses of the layers it lists. `read` names what was read."""
    policy = table()["absence_completeness"]
    layers = point.get("layers") or {}
    if policy["policy"] == "literal":
        return point.get("complete") is True, {"policy": "literal", "flag": point.get("complete"),
                                               "unknown_layers": sorted(k for k, v in layers.items() if v != "complete")}
    if policy["policy"] == "scoped":
        wanted = policy["layers"]
        unknown = sorted(name for name in wanted if layers.get(name) != "complete")
        return not unknown, {"policy": "scoped", "layers_read": list(wanted), "unknown_layers": unknown}
    raise Refused(f"TABLE_INVALID absence_completeness {policy['policy']!r}: literal or scoped")


def kind_of(outcomes, release, current, no_longer_arises=False):
    """`(kind, row id)`: the first kind row, in the table's order, that holds. Outcome rows hold when a unit outcome is
    among theirs; the no-matching-unit rows only when no unit matched, by the pair of candidate diagnoses at
    `release` and `current`; the lifecycle row when both judges find the situation no longer arises."""
    for row in table()["kind"]:
        if row.get("lifecycle_no_longer_arises"):
            if no_longer_arises:
                return row["kind"], row["id"]
        elif "if_any_outcome" in row:
            if outcomes and set(outcomes) & set(row["if_any_outcome"]):
                return row["kind"], row["id"]
        elif not outcomes:
            if row["no_matching_unit"] == "otherwise" or row["no_matching_unit"] == {"release": release,
                                                                                    "current": current}:
                return row["kind"], row["id"]
    raise Refused(f"TABLE_NOT_TOTAL kind over {sorted(set(outcomes))}: no row holds")


def admission(a, b, checks_pass):
    """`(admission, row id)` from both judges' marks on every requirement and the deterministic checks."""
    names = table()["requirements"]
    for who, marks in (("A", a), ("B", b)):
        bad = [n for n in names if marks.get(n) not in table()["domains"]["requirement"]]
        if bad:
            raise Refused(f"JUDGMENT_INVALID judge {who}: requirement {bad[0]} is {marks.get(bad[0])!r}, one of "
                          f"{table()['domains']['requirement']}")
    rows = {row["id"]: row for row in table()["admission"]}
    if checks_pass is True and all(a[n] == b[n] == "met" for n in names):
        return rows["admitted"]["admission"], "admitted"
    if any(a[n] == b[n] == "unmet" for n in names):
        return rows["rejected"]["admission"], "rejected"
    return rows["disputed"]["admission"], "disputed"


def eligible(kind, lineages, class_a, class_b, arc_confirmed=False):
    """`(eligible, row id, allowed dispositions)` for a candidate of type `kind` with `lineages` affirmed independent
    lineages and each judge's consequence class."""
    rows = {row["id"]: row for row in table()["promotion"]}
    if isinstance(lineages, bool) or not isinstance(lineages, int) or lineages < 0:
        raise Refused(f"JUDGMENT_INVALID lineages {lineages!r}: a count")
    if kind in rows["type_g"]["types"]:
        g = rows["type_g"]
        if lineages >= g["independent_lineages_at_least"] or (g["or_arc_confirmed"] and arc_confirmed is True):
            return True, "type_g", None
    else:
        if lineages >= rows["lineages"]["independent_lineages_at_least"]:
            return True, "lineages", None
        classes = rows["consequence"]["both_judges_class_one_of"]
        if class_a in classes and class_b in classes:
            return True, "consequence", None
    return False, "below_bar", list(rows["below_bar"]["allowed_dispositions"])


# ---- the whole derivation -----------------------------------------------------------------------

def unit_outcome(judgment, delivery, test_state):
    """The derivations of §6.4 for one candidate (the interface of WP-10):
    `{unit_diagnosis, candidate_diagnosis, unit_outcomes[], kind, admission, eligible, test}`.

    `judgment`: `candidate {candidate_id, type, lifecycle}`; `judges {A, B}`, each `{requirements {name: mark},
    consequence_class, no_longer_arises}`; `points {release, current}`, each `{complete, layers {layer: status},
    units {unit_id: {A: {situation, action, following, contribution}, B: {...}}}}`; optional `adjudicated
    {point: {unit_id: {field: value}}}`; `checks_pass`; `lineages`; optional `arc_confirmed`.
    `delivery`: `{unit_id: [{session, state}]}` at `release`; a unit with no entry is `unknown` in no session."""
    if test_state not in table()["domains"]["test"]:
        raise Refused(f"TEST_STATE_UNNAMED {test_state!r}: a derivation names its test state, one of "
                      f"{table()['domains']['test']}, never a blank")
    candidate, judges = judgment["candidate"], judgment["judges"]
    adjudicated = judgment.get("adjudicated") or {}
    diagnoses, per_point, fields = {}, {}, {}
    for point in POINTS:
        held = judgment["points"].get(point)
        if held is None:
            per_point[point] = {"diagnosis": "unknown", "row": "absent", "absence": None}
            continue
        units = {}
        for unit_id, pair in held["units"].items():
            settled = adjudicated.get(point, {}).get(unit_id, {})
            values = {f: settled.get(f, agreed(pair["A"].get(f), pair["B"].get(f))) for f in JUDGED}
            diagnosis = unit_diagnosis(values["situation"], values["action"])
            if diagnosis == DISPUTED:
                both = [unit_diagnosis(pair[who]["situation"], pair[who]["action"]) for who in ("A", "B")]
                units[unit_id] = (DISPUTED, both)
            else:
                units[unit_id] = diagnosis
            fields[(point, unit_id)] = values
        complete, read = absence(held)
        diagnosis, row = candidate_diagnosis(units, complete, candidate.get("lifecycle"))
        per_point[point] = {"diagnosis": diagnosis, "row": row, "absence": read}
        diagnoses[point] = {u: (d[0] if isinstance(d, tuple) else d) for u, d in units.items()}
    outcomes = []
    for unit_id, diagnosis in sorted((diagnoses.get("release") or {}).items()):
        if diagnosis == "no match":
            continue
        values = fields[("release", unit_id)]
        disputed = [f for f in JUDGED if values[f] == DISPUTED]
        for held in delivery.get(unit_id) or [{"session": None, "state": "unknown"}]:
            row, outcome = outcome_row(diagnosis, held["state"], values["following"], values["contribution"])
            outcomes.append({"unit_id": unit_id, "session": held["session"], "diagnosis": diagnosis,
                             "delivery": held["state"], "following": values["following"],
                             "contribution": values["contribution"], "outcome": outcome, "row": row,
                             "disputed": disputed})
    no_longer = all(judges[who].get("no_longer_arises") is True for who in ("A", "B")) \
        and bool(candidate.get("lifecycle"))
    kind, kind_row = kind_of([o["outcome"] for o in outcomes], per_point["release"]["diagnosis"],
                             per_point["current"]["diagnosis"], no_longer)
    admitted, admission_row = admission(judges["A"]["requirements"], judges["B"]["requirements"],
                                        judgment.get("checks_pass"))
    ok, eligible_row, allowed = eligible(candidate["type"], judgment.get("lineages", 0),
                                         judges["A"].get("consequence_class"), judges["B"].get("consequence_class"),
                                         judgment.get("arc_confirmed", False))
    return {"candidate_id": candidate["candidate_id"], "unit_diagnosis": diagnoses, "candidate_diagnosis": per_point,
            "unit_outcomes": outcomes, "kind": {"kind": kind, "row": kind_row},
            "admission": {"admission": admitted, "row": admission_row},
            "eligible": {"eligible": ok, "row": eligible_row, "allowed_dispositions": allowed}, "test": test_state}


# ---- the table's own checks ---------------------------------------------------------------------

def table_problems(held=None):
    """What makes the table unusable as a total function: an unknown value, a combination no row or two rows select,
    an outcome no kind row reads, a row id twice, a test column that is neither `—` nor a named state."""
    held = held or table()
    domains, problems = held["domains"], []
    for section in SECTIONS:
        seen = [row["id"] for row in held[section]]
        problems += [f"TABLE_INVALID {section}/{i}: the id appears twice" for i in sorted({i for i in seen if seen.count(i) > 1})]
    for row in held["unit_outcome"]:
        for name in ("delivery", "following", "contribution"):
            if row[name] not in WILD and not set(row[name]) <= set(domains[name]):
                problems.append(f"TABLE_INVALID unit_outcome/{row['id']}: {name} {row[name]} outside {domains[name]}")
        if row["diagnosis"] not in WILD and not set(row["diagnosis"]) <= set(domains["diagnosis"]):
            problems.append(f"TABLE_INVALID unit_outcome/{row['id']}: diagnosis {row['diagnosis']}")
        if row["test"] != "—" and row["test"] not in domains["test"]:
            problems.append(f"TABLE_INVALID unit_outcome/{row['id']}: test {row['test']!r} names no test state")
    matching = [d for d in domains["diagnosis"] if d != "no match"]
    for combo in itertools.product(matching, domains["delivery"], domains["following"], domains["contribution"]):
        hits = [row["id"] for row in held["unit_outcome"]
                if (row["diagnosis"] in WILD or combo[0] in row["diagnosis"])
                and combo[1] in accepted(row["delivery"], domains["delivery"])
                and combo[2] in accepted(row["following"], domains["following"])
                and combo[3] in accepted(row["contribution"], domains["contribution"])]
        if len(hits) != 1:
            problems.append(f"{'TABLE_NOT_TOTAL' if not hits else 'TABLE_AMBIGUOUS'} {combo}: rows {hits}")
    read = {o for row in held["kind"] for o in row.get("if_any_outcome", [])}
    problems += [f"TABLE_INVALID kind: outcome {o!r} reaches no kind row"
                 for o in sorted({row["outcome"] for row in held["unit_outcome"]} - read)]
    # a class no judge can return would make its row unreachable without a word (D-20261111-f3d39c)
    declared = consequence_classes()
    problems += [f"CLASS_UNDECLARED promotion/{row['id']}: {c!r} is not a consequence class the judgment schema "
                 f"declares ({list(declared)})"
                 for row in held["promotion"] for c in row.get("both_judges_class_one_of") or [] if c not in declared]
    return problems


# ---- the frozen fixtures ------------------------------------------------------------------------

def _cases(section, row, held):
    """The cases one row's fixture holds, built from the row's own fields; the expectation is the row's, never this
    code's answer."""
    domains = held["domains"]
    if section == "unit_diagnosis":
        return [{"situation": row["situation"], "action": row["action"], "expected": row["diagnosis"]}]
    if section == "unit_outcome":
        diagnoses = [d for d in domains["diagnosis"] if d != "no match"] if row["diagnosis"] in WILD else row["diagnosis"]
        return [{"diagnosis": d, "delivery": v, "following": f, "contribution": c,
                 "expected": {"row": row["id"], "outcome": row["outcome"]}}
                for d, v, f, c in itertools.product(diagnoses, accepted(row["delivery"], domains["delivery"]),
                                                    accepted(row["following"], domains["following"]),
                                                    accepted(row["contribution"], domains["contribution"]))]
    if section == "candidate_diagnosis":
        ladder = [r for r in held[section] if not r.get("lifecycle")]
        if row.get("lifecycle"):
            units = {f"u{n}": "covers" for n in range(row["covering_units_at_least"])}
            return [{"units": units, "complete": True, "lifecycle": row["lifecycle"],
                     "expected": {"diagnosis": row["diagnosis"], "row": row["id"]}}]
        below = [r["if_any_unit"] for r in ladder[ladder.index(row) + 1:] if r["if_any_unit"]]
        units = {f"u{n}": d for n, d in enumerate(([row["if_any_unit"]] if row["if_any_unit"] else []) + below + ["no match"])}
        cases = [{"units": units, "complete": True, "lifecycle": None,
                  "expected": {"diagnosis": row["diagnosis"], "row": row["id"]}}]
        if "incomplete" in row:
            cases.append({"units": units, "complete": False, "lifecycle": None,
                          "expected": {"diagnosis": row["incomplete"], "row": row["id"]}})
        return cases
    if section == "kind":
        rows = held[section]
        if row.get("lifecycle_no_longer_arises"):
            return [{"outcomes": ["misfire"], "release": "covered", "current": "covered", "no_longer_arises": True,
                     "expected": {"kind": row["kind"], "row": row["id"]}}]
        if "if_any_outcome" in row:
            later = [o for r in rows[rows.index(row) + 1:] for o in r.get("if_any_outcome", [])]
            return [{"outcomes": [o] + later, "release": "covered", "current": "covered", "no_longer_arises": False,
                     "expected": {"kind": row["kind"], "row": row["id"]}} for o in row["if_any_outcome"]]
        pair = row["no_matching_unit"] if row["no_matching_unit"] != "otherwise" else {"release": "unknown",
                                                                                         "current": "gap"}
        return [{"outcomes": [], **pair, "no_longer_arises": False, "expected": {"kind": row["kind"], "row": row["id"]}}]
    if section == "admission":
        met = {n: "met" for n in held["requirements"]}
        first = held["requirements"][0]
        inputs = {"admitted": (met, met, True), "rejected": ({**met, first: "unmet"}, {**met, first: "unmet"}, True),
                  "disputed": ({**met, first: "uncertain"}, met, True)}[row["id"]]
        cases = [{"a": inputs[0], "b": inputs[1], "checks_pass": inputs[2], "expected": {"admission": row["admission"],
                                                                                         "row": row["id"]}}]
        if row["id"] == "disputed":
            cases.append({"a": met, "b": met, "checks_pass": False, "expected": {"admission": row["admission"],
                                                                                 "row": row["id"]}})
        return cases
    if section == "promotion":
        inputs = {"lineages": ("A", row.get("independent_lineages_at_least"), None, None, False),
                  "consequence": ("B", 0) + (tuple(row.get("both_judges_class_one_of", [None])[:1]) * 2) + (False,),
                  "type_g": ("G", row.get("independent_lineages_at_least"), None, None, False),
                  "below_bar": ("A", 1, "irreversible", "reversible", False)}[row["id"]]
        cases = [{"type": inputs[0], "lineages": inputs[1], "class_a": inputs[2], "class_b": inputs[3],
                  "arc_confirmed": inputs[4], "expected": {"eligible": row["eligible"], "row": row["id"]}}]
        if row["id"] == "type_g":
            cases.append({"type": "G", "lineages": 0, "class_a": None, "class_b": None, "arc_confirmed": True,
                          "expected": {"eligible": row["eligible"], "row": row["id"]}})
        return cases
    raise Refused(f"TABLE_INVALID section {section!r}")


def generate_fixtures(path=FIXTURES_PATH):
    """Write one fixture per row of the table, once. The fixtures are committed and a second call refuses: a fixture
    regenerated from the table it is meant to hold would hold nothing."""
    path = pathlib.Path(path)
    if path.exists():
        raise Refused(f"FIXTURES_FROZEN {path}: generated once and committed; delete it by hand to regenerate")
    held = table()
    fixtures = [{"id": f"{section}/{row['id']}", "cases": _cases(section, row, held)}
                for section in SECTIONS for row in held[section]]
    doc = {"$comment": "design §6.4: one frozen fixture per row of tables/unit_outcome.json, written once by "
                       "`runlib/derive.py --generate-fixtures`; the self-test never regenerates them.",
           "fixtures": fixtures}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(fixtures)


def run_fixture(fixture):
    """Every case of one frozen fixture through the production functions: the problems, `[]` when all hold."""
    section = fixture["id"].split("/", 1)[0]
    problems = []
    for n, case in enumerate(fixture["cases"]):
        try:
            if section == "unit_diagnosis":
                got = unit_diagnosis(case["situation"], case["action"])
            elif section == "unit_outcome":
                row, outcome = outcome_row(case["diagnosis"], case["delivery"], case["following"], case["contribution"])
                got = {"row": row, "outcome": outcome}
            elif section == "candidate_diagnosis":
                diagnosis, row = candidate_diagnosis(case["units"], case["complete"], case["lifecycle"])
                got = {"diagnosis": diagnosis, "row": row}
            elif section == "kind":
                kind, row = kind_of(case["outcomes"], case["release"], case["current"], case["no_longer_arises"])
                got = {"kind": kind, "row": row}
            elif section == "admission":
                result, row = admission(case["a"], case["b"], case["checks_pass"])
                got = {"admission": result, "row": row}
            else:
                ok, row, _allowed = eligible(case["type"], case["lineages"], case["class_a"], case["class_b"],
                                             case["arc_confirmed"])
                got = {"eligible": ok, "row": row}
        except Refused as exc:
            got = f"refused {str(exc).split()[0]}"
        if got != case["expected"]:
            problems.append(f"FIXTURE_FAILED {fixture['id']} case {n}: expected {case['expected']}, got {got}")
    return problems


def coverage_problems(rows, frozen, executed):
    """The three sets of done-when 1 by id: the table's rows, the frozen fixtures, the cases the run executed."""
    rows, frozen, executed = set(rows), set(frozen), set(executed)
    return ([f"ROW_UNFIXTURED {i}: a row of the table with no frozen fixture" for i in sorted(rows - frozen)]
            + [f"FIXTURE_ORPHAN {i}: a frozen fixture for no row of the table" for i in sorted(frozen - rows)]
            + [f"CASE_NOT_EXECUTED {i}: a frozen fixture the run never executed" for i in sorted(frozen - executed)]
            + [f"CASE_UNFROZEN {i}: a case the run executed with no frozen fixture" for i in sorted(executed - frozen)]
            + (["ROWS_NONE: the table has no rows, so a bijection over it says nothing"] if not rows else []))


# ---- the self-test ------------------------------------------------------------------------------

# The design's §6.4, copied here once (WP-10 done-when 5); the review compares it with the design text. Each
# outcome row is (unit diagnosis, delivery, following, contribution, unit outcome) in the design's words.
DESIGN_6_4_OUTCOME = (
    ("any", "unknown", "—", "—", "unknown"),
    ("any", "selected_unavailable or not_delivered", "—", "—", "not delivered"),
    ("covers", "exposed_not_read", "—", "—", "misfire (trigger)"),
    ("covers", "delivered", "not_followed", "—", "misfire"),
    ("covers", "delivered", "followed", "harmed", "misfire"),
    ("covers", "delivered", "followed", "helped", "confirmed"),
    ("covers", "delivered", "followed", "neutral", "neutral (followed, no effect)"),
    ("covers", "delivered", "followed", "unknown", "unknown"),
    ("covers", "delivered", "unknown", "—", "unknown"),
    ("trigger problem, wrong or insufficient", "delivered or exposed_not_read", "—", "—", "misfire"),
)
# "situation yes / action yes → covers; situation yes / action no → wrong or insufficient; situation no / action
# yes → trigger problem; neither → no match"
DESIGN_6_4_DIAGNOSIS = (("yes", "yes", "covers"), ("yes", "no", "wrong or insufficient"),
                        ("no", "yes", "trigger problem"), ("no", "no", "no match"))
# "covered (list every covering unit) > wrong or insufficient > trigger problem > gap"
DESIGN_6_4_CANDIDATE = ("covered", "wrong or insufficient", "trigger problem", "gap")
# "any misfire → misfire; else any not delivered → not delivered; else any unknown → unclassified; else any
# confirmed → confirmed; else (all neutral) → unclassified"
DESIGN_6_4_KIND = (("misfire", "misfire"), ("not delivered", "not delivered"), ("unknown", "unclassified"),
                   ("confirmed", "confirmed"), ("neutral (followed, no effect)", "unclassified"))
# "gap at release and current → gap; gap at release, covered at current → already resolved (no proposal)"
DESIGN_6_4_ABSENT = ((("gap", "gap"), "gap"), (("gap", "covered"), "already resolved"))
# "affirmed independent lineages ≥ 2, or a consequence both judges classed irreversible, security-relevant, or
# verification-corrupting"; §7.4, type G: "at least three independent lineages ... or an arc retrospective the owner
# confirms"; "Below the bar, the allowed dispositions are incubate, keep, and drop."
DESIGN_6_4_PROMOTION = (2, ("irreversible", "security-relevant", "verification-corrupting"), 3,
                        ("incubate", "keep", "drop"))
# D-20261111-f3d39c (WP-11 D11): §6.4 says "security-relevant" and §7.5 "security" for one class. The judgment
# schema's enum is the classes' one owner and spells them as §7.5 does; the copy above keeps §6.4's word, and the
# fidelity check reads it through this rename, so the difference is declared here rather than written over.
DESIGN_CLASS_RENAMES = {"security-relevant": "security"}
CLASSES_SCHEMA = HERE / "schemas" / "judge.schema.json"


def consequence_classes(path=CLASSES_SCHEMA):
    """The consequence classes a judge can return: the judgment schema's enum, their one owner (D-20261111-f3d39c)."""
    return tuple(json.loads(pathlib.Path(path).read_text(encoding="utf-8"))["$defs"]["consequence_class"]["enum"])


def render_outcome(row):
    def column(value, joiner):
        return value if value in WILD else joiner.join(value)
    return (column(row["diagnosis"], ", "), column(row["delivery"], " or "), column(row["following"], " or "),
            column(row["contribution"], " or "), row["outcome"])


def fidelity_problems(held=None):
    """The table against the design's own rows (WP-10 done-when 5)."""
    held = held or table()
    problems = []
    rendered = tuple(render_outcome(row) for row in held["unit_outcome"])
    if rendered != DESIGN_6_4_OUTCOME:
        problems += [f"CONTRACT_DRIFT unit_outcome row {n + 1}: the table says {have}, §6.4 says {want}"
                     for n, (have, want) in enumerate(itertools.zip_longest(rendered, DESIGN_6_4_OUTCOME)) if have != want]
    diagnosis = tuple((r["situation"], r["action"], r["diagnosis"]) for r in held["unit_diagnosis"])
    if diagnosis != DESIGN_6_4_DIAGNOSIS:
        problems.append(f"CONTRACT_DRIFT unit_diagnosis: {diagnosis}")
    ladder = tuple(r["diagnosis"] for r in held["candidate_diagnosis"] if not r.get("lifecycle"))
    if ladder != DESIGN_6_4_CANDIDATE:
        problems.append(f"CONTRACT_DRIFT candidate_diagnosis precedence: {ladder}")
    kinds = tuple((o, r["kind"]) for r in held["kind"] for o in r.get("if_any_outcome", [])[:1])
    if kinds != DESIGN_6_4_KIND:
        problems.append(f"CONTRACT_DRIFT kind precedence: {kinds}")
    absent = tuple(((r["no_matching_unit"]["release"], r["no_matching_unit"]["current"]), r["kind"])
                   for r in held["kind"] if isinstance(r.get("no_matching_unit"), dict))
    if absent != DESIGN_6_4_ABSENT:
        problems.append(f"CONTRACT_DRIFT kind with no matching unit: {absent}")
    rows = {r["id"]: r for r in held["promotion"]}
    promotion = (rows["lineages"]["independent_lineages_at_least"], tuple(rows["consequence"]["both_judges_class_one_of"]),
                 rows["type_g"]["independent_lineages_at_least"], tuple(rows["below_bar"]["allowed_dispositions"]))
    design = (DESIGN_6_4_PROMOTION[0], tuple(DESIGN_CLASS_RENAMES.get(c, c) for c in DESIGN_6_4_PROMOTION[1]),
              *DESIGN_6_4_PROMOTION[2:])
    if promotion != design:
        problems.append(f"CONTRACT_DRIFT promotion: {promotion}")
    if len(held["requirements"]) != 8:
        problems.append(f"CONTRACT_DRIFT admission: {len(held['requirements'])} requirements, §6.4 names eight")
    return problems


def self_test():
    failures, ran = [], []

    def expect(label, got, want):
        ran.append(label)
        if got != want:
            failures.append(f"{label}: expected {want!r}, got {got!r}")

    def named(label, lines, needle):
        ran.append(label)
        if not any(needle in line for line in lines):
            failures.append(f"{label}: expected {needle!r} in {lines}")

    def refused(label, action, code):
        ran.append(label)
        try:
            action()
        except Refused as exc:
            if not str(exc).startswith(code):
                failures.append(f"{label}: refused {str(exc)[:160]!r}, expected {code}")
            return
        except Exception as exc:  # noqa: BLE001 - anything else fails this control by name, never the suite
            failures.append(f"{label}: raised {type(exc).__name__}: {exc}, expected {code}")
            return
        failures.append(f"{label}: not refused, expected {code}")

    held = table()
    expect("the table is total, unambiguous and closed over its domains", table_problems(), [])
    expect("the table holds §6.4's rows, words and orders", fidelity_problems(), [])

    # done-when 5's controls: a changed row is named against the design's
    drifted = copy.deepcopy(held)
    drifted["unit_outcome"][5]["outcome"] = "neutral (followed, no effect)"
    named("control: a unit-outcome row that no longer says what §6.4 says", fidelity_problems(drifted),
          "CONTRACT_DRIFT unit_outcome row 6")
    swapped = copy.deepcopy(held)
    swapped["kind"][1], swapped["kind"][2] = swapped["kind"][2], swapped["kind"][1]
    named("control: the kind precedence reordered", fidelity_problems(swapped), "CONTRACT_DRIFT kind precedence")
    # the table's own totality, with its controls
    gone = copy.deepcopy(held)
    gone["unit_outcome"] = [row for row in gone["unit_outcome"] if row["id"] != "o9"]
    named("control: a row removed leaves its combinations unselected", table_problems(gone), "TABLE_NOT_TOTAL")
    overlap = copy.deepcopy(held)
    overlap["unit_outcome"][3]["following"] = "—"
    named("control: a row widened over another is ambiguous", table_problems(overlap), "TABLE_AMBIGUOUS")
    blank = copy.deepcopy(held)
    blank["unit_outcome"][0]["test"] = ""
    named("control: a test column that names nothing", table_problems(blank), "names no test state")
    respelled = copy.deepcopy(held)
    next(r for r in respelled["promotion"] if r["id"] == "consequence")["both_judges_class_one_of"][1] = "security-relevant"
    named("control: a promotion row naming a class outside the judgment schema's enum (D-20261111-f3d39c)",
          table_problems(respelled), "CLASS_UNDECLARED promotion/consequence")

    # done-when 1: the frozen fixtures, the table's rows, and the cases this run executed
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["fixtures"]
    executed = set()
    for fixture in fixtures:
        failures.extend(run_fixture(fixture))
        executed.add(fixture["id"])  # recorded after its cases ran through the production functions
    frozen = {f["id"] for f in fixtures}
    expect("table rows, frozen fixtures and executed cases are one set", coverage_problems(row_ids(), frozen, executed), [])
    added = copy.deepcopy(held)
    added["unit_outcome"].append({**added["unit_outcome"][0], "id": "o11"})
    named("control: a row added to a scratch copy, the frozen fixtures unchanged",
          coverage_problems(row_ids(added), frozen, executed), "ROW_UNFIXTURED unit_outcome/o11")
    named("control: a frozen fixture deleted", coverage_problems(row_ids(), frozen - {"kind/gap"}, executed - {"kind/gap"}),
          "ROW_UNFIXTURED kind/gap")
    named("control: an executed case removed from the run's record",
          coverage_problems(row_ids(), frozen, executed - {"unit_outcome/o4"}), "CASE_NOT_EXECUTED unit_outcome/o4")
    named("control: a case executed with no frozen fixture",
          coverage_problems(row_ids(), frozen, executed | {"unit_outcome/o0"}), "CASE_UNFROZEN unit_outcome/o0")
    named("control: a bijection over no rows", coverage_problems([], set(), set()), "ROWS_NONE")
    by_id = {f["id"]: f for f in fixtures}
    _TABLES["t"] = drifted
    try:
        named("control: a frozen fixture against a table whose row changed", run_fixture(by_id["unit_outcome/o6"]),
              "FIXTURE_FAILED unit_outcome/o6")
    finally:
        _TABLES["t"] = held
    with tempfile.TemporaryDirectory() as td:
        target = pathlib.Path(td) / "fixtures.json"
        expect("the generator writes one fixture per row", generate_fixtures(target), len(row_ids()))
        expect("the generator's fixtures are the frozen ones",
               json.loads(target.read_text(encoding="utf-8"))["fixtures"], fixtures)
        refused("a second generation", lambda: generate_fixtures(target), "FIXTURES_FROZEN")

    # done-when 2 (the derivation side): O3 verdicts, each with the control that flips its expectation
    met = {n: "met" for n in held["requirements"]}

    def unit(situation="yes", action="yes", following="followed", contribution="helped", b=None):
        one = {"situation": situation, "action": action, "following": following, "contribution": contribution}
        return {"A": one, "B": {**one, **(b or {})}}

    def judged(units, delivery, release=None, current=None, lifecycle=None, kind_type="A", test="untested: s8_deferred",
               **extra):
        point = {"complete": True, "layers": {}, "units": units}
        return unit_outcome({"candidate": {"candidate_id": "k1", "type": kind_type, "lifecycle": lifecycle},
                             "judges": {"A": {"requirements": met, "consequence_class": None},
                                        "B": {"requirements": met, "consequence_class": None}},
                             "points": {"release": release or point, "current": current or point},
                             "checks_pass": True, "lineages": 2, **extra},
                            delivery, test)

    def kind(result):
        return result["kind"]["kind"]
    pinned = {"session": "claude:s1", "state": "delivered"}
    expect("O3: a pinned session violating a delivered rule is a misfire",
           kind(judged({"u1": unit(following="not_followed", contribution="harmed")}, {"u1": [pinned]})), "misfire")
    expect("O3 control: the same rule followed, helping, is confirmed",
           kind(judged({"u1": unit()}, {"u1": [pinned]})), "confirmed")
    exposed = {"session": "claude:s1", "state": "exposed_not_read"}
    expect("O3: a guide pointer exposed and never read is a misfire (trigger)",
           judged({"u1": unit(following="not_followed")}, {"u1": [exposed]})["unit_outcomes"][0]["outcome"],
           "misfire (trigger)")
    expect("O3 control: the same guide read is a misfire, not a trigger misfire",
           judged({"u1": unit(following="not_followed")}, {"u1": [pinned]})["unit_outcomes"][0]["outcome"], "misfire")
    unavailable = {"session": "claude:s1", "state": "selected_unavailable"}
    expect("O3: selected_unavailable is not delivered", kind(judged({"u1": unit()}, {"u1": [unavailable]})),
           "not delivered")
    expect("O3 control: the same unit delivered is confirmed", kind(judged({"u1": unit()}, {"u1": [pinned]})), "confirmed")
    unpinned = {"session": "claude:s2", "state": "unknown"}
    expect("O3: an unpinned session is unclassified", kind(judged({"u1": unit()}, {"u1": [unpinned]})), "unclassified")
    expect("O3 control: with no delivery entry at all the unit is unknown in no session, unclassified",
           (kind(judged({"u1": unit()}, {})), judged({"u1": unit()}, {})["unit_outcomes"][0]["session"]),
           ("unclassified", None))
    mixed = judged({"u1": unit(), "u2": unit(following="not_followed")}, {"u1": [pinned], "u2": [pinned]})
    expect("O3: one helpful and one violated covering unit is a misfire, both shown",
           (kind(mixed), sorted(o["outcome"] for o in mixed["unit_outcomes"])), ("misfire", ["confirmed", "misfire"]))
    expect("O3 control: the violated unit removed, confirmed",
           kind(judged({"u1": unit()}, {"u1": [pinned]})), "confirmed")
    unknown_c = judged({"u1": unit(), "u2": unit(contribution="unknown")}, {"u1": [pinned], "u2": [pinned]})
    expect("O3: helpful and unknown-contribution is unclassified, both shown",
           (kind(unknown_c), sorted(o["outcome"] for o in unknown_c["unit_outcomes"])), ("unclassified", ["confirmed", "unknown"]))
    unknown_f = judged({"u1": unit(), "u2": unit(following="unknown")}, {"u1": [pinned], "u2": [pinned]})
    expect("O3: helpful and unknown-following is unclassified", kind(unknown_f), "unclassified")
    expect("O3 control: both helpful is confirmed",
           kind(judged({"u1": unit(), "u2": unit()}, {"u1": [pinned], "u2": [pinned]})), "confirmed")
    # the kind precedence on one mixed candidate (misfire > not delivered > unclassified > confirmed > all neutral)
    ladder = {"u1": (unit(), [pinned]), "u2": (unit(contribution="unknown"), [pinned]), "u3": (unit(), [unavailable]),
              "u4": (unit(following="not_followed"), [pinned]), "u5": (unit(contribution="neutral"), [pinned])}
    seen = []
    for drop in (None, "u4", "u3", "u2", "u1"):
        ladder.pop(drop, None)
        seen.append(kind(judged({u: v[0] for u, v in ladder.items()}, {u: v[1] for u, v in ladder.items()})))
    expect("the kind precedence over a mixed fixture, removing the strongest outcome each time", seen,
           ["misfire", "not delivered", "unclassified", "confirmed", "unclassified"])

    # two judges: agreement, dispute, adjudication
    split = judged({"u1": unit(b={"following": "not_followed"})}, {"u1": [pinned]})
    expect("a following the judges disagree on is disputed and read as unknown",
           (split["unit_outcomes"][0]["outcome"], split["unit_outcomes"][0]["disputed"], kind(split)),
           ("unknown", ["following"], "unclassified"))
    settled = judged({"u1": unit(b={"following": "not_followed"})}, {"u1": [pinned]},
                     adjudicated={"release": {"u1": {"following": "not_followed"}}})
    expect("control: the owner's adjudication of that following recomputes a misfire", kind(settled), "misfire")
    torn = judged({"u1": unit(b={"action": "no"})}, {"u1": [pinned]})
    expect("a situation or action the judges disagree on leaves the unit disputed and its outcome unknown",
           (torn["unit_diagnosis"]["release"]["u1"], torn["unit_outcomes"][0]["row"], kind(torn)),
           ("disputed", "disputed", "unclassified"))
    expect("a disputed unit that could cover leaves the candidate's diagnosis unknown",
           judged({"u1": unit(b={"action": "no"}), "u2": unit(situation="no")}, {})["candidate_diagnosis"]["release"]["row"],
           "disputed")
    expect("control: a disputed unit below an agreed cover leaves the cover",
           judged({"u1": unit(), "u2": unit(situation="no", b={"action": "no"})}, {"u1": [pinned]})
           ["candidate_diagnosis"]["release"]["diagnosis"], "covered")

    # absences: the completeness policy, by the layers it read
    nothing = {"u1": unit(situation="no", action="no")}
    gap_point = {"complete": True, "layers": {"catalog": "complete"}, "units": nothing}
    open_point = {"complete": False, "layers": {"catalog": "complete", "native_settings": "unknown"}, "units": nothing}
    expect("no matching unit at a complete release and current is a gap",
           kind(judged(nothing, {}, release=gap_point, current=gap_point)), "gap")
    covered_now = {"complete": True, "layers": {}, "units": {"u9": unit()}}
    expect("a gap at release, covered at current, is already resolved",
           kind(judged(nothing, {}, release=gap_point, current=covered_now)), "already resolved")
    literal = judged(nothing, {}, release=open_point, current=gap_point)
    expect("under the literal policy an incomplete release turns the gap unknown and the kind unclassified, naming the "
           "unknown layer", (literal["candidate_diagnosis"]["release"]["diagnosis"], kind(literal),
                             literal["candidate_diagnosis"]["release"]["absence"]["unknown_layers"]),
           ("unknown", "unclassified", ["native_settings"]))
    _TABLES["t"] = {**held, "absence_completeness": {"policy": "scoped", "layers": ["catalog"]}}
    try:
        scoped = judged(nothing, {}, release=open_point, current=gap_point)
        expect("control: the scoped policy over the catalog alone reads the same point as a gap, naming what it read",
               (kind(scoped), scoped["candidate_diagnosis"]["release"]["absence"]),
               ("gap", {"policy": "scoped", "layers_read": ["catalog"], "unknown_layers": []}))
    finally:
        _TABLES["t"] = held
    _TABLES["t"] = {**held, "absence_completeness": {"policy": "guessed"}}
    try:
        refused("an absence policy the table does not define", lambda: judged(nothing, {}), "TABLE_INVALID")
    finally:
        _TABLES["t"] = held

    # lifecycle: redundant and obsolete
    pair = {"u1": unit(), "u2": unit()}
    redundant = judged(pair, {"u1": [pinned], "u2": [pinned]}, lifecycle="redundancy_hint")
    expect("a redundancy candidate with two covering units is redundant and keeps the kind its units yield",
           (redundant["candidate_diagnosis"]["release"]["diagnosis"], kind(redundant)), ("redundant", "confirmed"))
    expect("control: the same units on a formed candidate are covered",
           judged(pair, {"u1": [pinned], "u2": [pinned]})["candidate_diagnosis"]["release"]["diagnosis"], "covered")
    gone_now = {"u1": unit(following="not_followed")}
    no_longer = unit_outcome({"candidate": {"candidate_id": "obsolete_hint:x", "type": "A", "lifecycle": "obsolete_hint"},
                              "judges": {"A": {"requirements": met, "no_longer_arises": True},
                                         "B": {"requirements": met, "no_longer_arises": True}},
                              "points": {"release": {"complete": True, "layers": {}, "units": gone_now},
                                         "current": {"complete": True, "layers": {}, "units": gone_now}},
                              "checks_pass": True, "lineages": 0}, {"u1": [pinned]}, "untested: s8_deferred")
    expect("a lifecycle candidate both judges find no longer arising is obsolete", kind(no_longer), "obsolete")
    expect("control: one judge alone does not make it obsolete",
           unit_outcome({**{"candidate": {"candidate_id": "obsolete_hint:x", "type": "A", "lifecycle": "obsolete_hint"},
                            "judges": {"A": {"requirements": met, "no_longer_arises": True},
                                       "B": {"requirements": met, "no_longer_arises": False}},
                            "points": {"release": {"complete": True, "layers": {}, "units": gone_now},
                                       "current": {"complete": True, "layers": {}, "units": gone_now}},
                            "checks_pass": True, "lineages": 0}}, {"u1": [pinned]}, "untested: s8_deferred")["kind"]["kind"],
           "misfire")

    # admission, eligibility, the test state
    result = judged({"u1": unit()}, {"u1": [pinned]})
    expect("both judges met on all eight with the checks passing is admitted, and two lineages are eligible",
           (result["admission"]["admission"], result["eligible"]["eligible"], result["test"]),
           ("admitted", True, "untested: s8_deferred"))
    expect("control: a failing deterministic check leaves it disputed",
           judged({"u1": unit()}, {"u1": [pinned]}, checks_pass=False)["admission"]["admission"], "disputed")
    expect("one lineage, no grave consequence: below the bar, with the dispositions it allows",
           judged({"u1": unit()}, {"u1": [pinned]}, lineages=1)["eligible"],
           {"eligible": False, "row": "below_bar", "allowed_dispositions": ["incubate", "keep", "drop"]})
    expect("a type G candidate needs three lineages", judged({"u1": unit()}, {"u1": [pinned]}, kind_type="G")["eligible"]["row"],
           "below_bar")
    refused("a derivation with no test state", lambda: judged({"u1": unit()}, {"u1": [pinned]}, test=""),
            "TEST_STATE_UNNAMED")
    refused("a derivation with a test state the table does not name",
            lambda: judged({"u1": unit()}, {"u1": [pinned]}, test="tested: maybe"), "TEST_STATE_UNNAMED")
    refused("a judged match outside the domain", lambda: unit_diagnosis("maybe", "yes"), "JUDGMENT_INVALID")
    refused("a requirement mark outside the domain", lambda: admission({**met, "bounded": "probably"}, met, True),
            "JUDGMENT_INVALID judge A")

    for failure in failures:
        print(f"derive --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"derive --self-test: OK ({len(ran)} controls, {len(fixtures)} frozen fixtures over the table's "
          f"{len(row_ids())} rows: the §6.4 table total and as the design states it, the three-set bijection with its "
          "four failures, the O3 verdicts each with its flipped control, the kind precedence over a mixed fixture, two "
          "judges' disputes and the adjudication that settles one, both absence policies, lifecycle redundant and "
          "obsolete, admission and promotion, the named test state)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--generate-fixtures"]:
        target = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else FIXTURES_PATH
        print(f"wrote {generate_fixtures(target)} fixtures to {target}")
        sys.exit(0)
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: derive.py --self-test | --generate-fixtures [PATH]")
    sys.exit(self_test())
