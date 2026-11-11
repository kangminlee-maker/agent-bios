#!/usr/bin/env python3
"""The proposal contract as code over its tables (WP-12 commit 1): §7.2's allowed pairs and §7.3's
structural rules.

Two tables and no judgement. `tables/allowed_pairs.json` holds the four closed vocabularies and the
dispositions each (kind, diagnosis) pair allows; `tables/structural_rules.json` holds §7.3's rules in
the order they are applied, each with the code it refuses by and the design sentence it comes from.
This module reads them and returns problems; it decides nothing a table does not state, because the
alternative is two authorities for one contract and the plan's own main risk for this package.

What it does NOT do: the §7.4 placement rules (`tables/placement_rules.json`, the next commit), the
semantic bars (`packets/placement_contract.md`, judged by S7b), and the ranking (§7.5). Those are
separate authorities on purpose.

    placement.py --self-test
"""
import itertools
import json
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
PAIRS_PATH = HERE / "tables" / "allowed_pairs.json"
RULES_PATH = HERE / "tables" / "structural_rules.json"
_TABLES = {}

# A disposition that writes nothing into the library: §10.4's ledger-only set, named once.
LEDGER_ONLY = ("keep", "incubate", "drop")
# What a candidate below the promotion bar may still be proposed as (the §6.4 table's `below_bar`
# row, whose `allowed_dispositions` this list must equal — asserted in the suite rather than copied
# by hand).
BELOW_BAR = ("incubate", "keep", "drop")


def table(which):
    """One of the two tables, read once per process. A control may seed `_TABLES` with a scratch copy."""
    if which not in _TABLES:
        path = {"pairs": PAIRS_PATH, "rules": RULES_PATH}[which]
        try:
            _TABLES[which] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise Refused(f"TABLE_UNREADABLE {path.name}: {exc}") from exc
    return _TABLES[which]


def vocabularies():
    return table("pairs")["vocabularies"]


def matches(row, kind, diagnosis, legacy_incubating=False):
    """Whether one row of the pairs table answers for this (kind, diagnosis).

    `any` is a wildcard in either column, and the legacy row answers ONLY for a legacy incubating
    entry — it holds for every kind including unclassified, so without that flag it would swallow
    every other row's pair and make the table unreadable."""
    if bool(row.get("legacy_incubating")) != bool(legacy_incubating):
        return False
    return ((row["kind"] == "any" or row["kind"] == kind)
            and (row["diagnosis"] == "any" or row["diagnosis"] == diagnosis))


def rows_for(kind, diagnosis, legacy_incubating=False):
    return [row for row in table("pairs")["rows"] if matches(row, kind, diagnosis, legacy_incubating)]


def allowed_for(kind, diagnosis, legacy_incubating=False):
    """`{disposition: the condition it requires, or None}` over every row that answers.

    Several rows can answer one pair — `redundant` holds for any kind — and the union is what §7.2
    means by "allowed": a disposition any answering row allows is allowed. Where two rows allow the
    same disposition, the one with no condition wins, because a row that allows it outright is the
    weaker bar and the table would otherwise read as forbidding what it allows."""
    out = {}
    for row in rows_for(kind, diagnosis, legacy_incubating):
        for entry in row["allowed"]:
            name, condition = entry["disposition"], entry.get("requires")
            if name not in out or out[name] is not None:
                out[name] = condition
    return out


def unknown_values(proposal):
    """The proposal's fields that are outside §7.2's closed vocabularies, by field name."""
    held = vocabularies()
    problems = []
    for field, vocabulary in (("kind", "kind"), ("diagnosis", "diagnosis"), ("disposition", "disposition")):
        value = proposal.get(field)
        if value not in held[vocabulary]:
            problems.append(f"VALUE_UNKNOWN {field} {value!r}: §7.2's vocabulary is "
                            f"{', '.join(held[vocabulary])}")
    return problems


# ---- the conditions §7.2's rows name -------------------------------------------------------------
#
# One reader per condition, each asking the proposal and nothing else. A condition whose reader is
# missing is a refusal rather than a pass: a row that names a condition nobody checks allows the
# disposition unconditionally, which is the quiet failure this table exists to prevent.

def _reason(proposal):
    reason = proposal.get("reason")
    return isinstance(reason, str) and reason.strip() != ""


def _operations(proposal, types=None):
    rows = [op for op in proposal.get("operations") or [] if isinstance(op, dict)]
    return [op for op in rows if types is None or op.get("type") in types]


CONDITIONS = {
    "drop_reason_acceptable_miss": _reason,
    "reduce_when_harmful": lambda p: p.get("harmful") is True,
    "reduce_by_merge": lambda p: bool(_operations(p, {"merge"})),
    "keep_with_reason": _reason,
    "incubate_owner_approved": lambda p: bool((p.get("expected_observation") or {}).get("expiry"))
                                         and bool(p.get("expected_observation")),
    "drop_retire_with_reason": _reason,
    "none_stays_in_intake": lambda p: not _operations(p),
    "place_admitted_and_eligible": lambda p: p.get("admitted") is True and p.get("promotion_eligible") is True,
}


def condition_problems():
    """A condition the pairs table names and this module cannot check, or the reverse."""
    named = set(table("pairs")["conditions"]) - {"$comment"}
    held = set(CONDITIONS)
    return ([f"CONDITION_UNCHECKED {name}: the pairs table names it and no reader asks it"
             for name in sorted(named - held)]
            + [f"CONDITION_UNNAMED {name}: a reader for a condition no row names"
               for name in sorted(held - named)])


def pair_problems(proposal):
    """§7.2 for one proposal: the pair, and the condition the allowing row names."""
    problems = unknown_values(proposal)
    if problems:
        return problems
    kind, diagnosis = proposal["kind"], proposal["diagnosis"]
    legacy = bool(proposal.get("legacy_incubating"))
    allowed = allowed_for(kind, diagnosis, legacy)
    disposition = proposal["disposition"]
    if disposition not in allowed:
        return [f"PAIR_DISALLOWED {kind} / {diagnosis} / {disposition}: §7.2 allows "
                f"{', '.join(sorted(allowed)) or 'nothing'}"
                + (" under the legacy-maintenance row" if legacy else "")]
    condition = allowed[disposition]
    if condition is not None and not CONDITIONS[condition](proposal):
        return [f"PAIR_DISALLOWED {kind} / {diagnosis} / {disposition}: §7.2 allows it only where "
                f"{table('pairs')['conditions'][condition]}"]
    return []


# ---- §7.3's structural rules ---------------------------------------------------------------------

def global_files():
    return tuple(table("rules")["operations"].get("global_files") or ())


def _global_ops(proposal):
    held = global_files()
    return [op for op in _operations(proposal) if str(op.get("target") or "") in held]


def _library_ops(proposal):
    return _operations(proposal, set(table("rules")["operations"]["library"]))


def structural_problems(proposal, active_keep=None):
    """§7.3's rules in the table's order, each refused by the table's own code.

    `active_keep` maps a unit id to the id of the keep record standing over it (§10.1). It is the
    caller's to supply from the ledger, because this module reads no ledger: a module that read one
    would answer about whatever file it found.
    """
    active_keep = dict(active_keep or {})
    problems = []
    for rule in table("rules")["rules"]:
        code, rid = rule["code"], rule["id"]
        if rid == "global_op":
            allowed = set(table("rules")["operations"]["global_allowed"])
            for op in _global_ops(proposal):
                if op.get("type") not in allowed:
                    problems.append(f"{code} {op.get('type')} on {op.get('target')}: §7.3 allows only "
                                    f"{', '.join(sorted(allowed))} on the always-loaded global file")
        elif rid == "incubate_expiry":
            if proposal.get("disposition") == "incubate" and not CONDITIONS["incubate_owner_approved"](proposal):
                problems.append(f"{code} {proposal.get('item_id')}: an incubate carries an expected "
                                f"observation and an expiry")
        elif rid == "keep_reason":
            if proposal.get("disposition") in ("keep", "drop") and not _reason(proposal):
                problems.append(f"{code} {proposal.get('disposition')} {proposal.get('item_id')}: "
                                f"§7.3 refuses a keep or a drop with no reason")
        elif rid == "pair":
            problems += pair_problems(proposal)
        elif rid == "promotion":
            if proposal.get("promotion_eligible") is False and proposal.get("disposition") not in BELOW_BAR:
                problems.append(f"{code} {proposal.get('disposition')} {proposal.get('item_id')}: a candidate "
                                f"below the promotion bar may be proposed only as "
                                f"{', '.join(BELOW_BAR)}")
        elif rid == "keep_record":
            touching = (["reduce"] if proposal.get("disposition") == "reduce" else []) + \
                       [op.get("type") for op in _operations(proposal, {"merge"})]
            if touching:
                named = set(proposal.get("keep_records_named") or ())
                guarded = sorted({unit: record for unit, record in active_keep.items()
                                  if record not in named}.items())
                problems += [f"{code} {unit}: an active keep record ({record}) stands over it, and the "
                             f"proposal does not name it; the owner's `keep 해제` comes first"
                             for unit, record in guarded]
        elif rid == "ledger_only":
            if proposal.get("disposition") in LEDGER_ONLY:
                if _library_ops(proposal):
                    problems.append(f"{code} {proposal.get('disposition')} {proposal.get('item_id')}: a "
                                    f"ledger-only disposition carries no library operation, and this one "
                                    f"carries {len(_library_ops(proposal))}")
                if proposal.get("requires_test") is not False:
                    problems.append(f"{code} {proposal.get('disposition')} {proposal.get('item_id')}: a "
                                    f"ledger-only disposition sets requires_test false, not "
                                    f"{proposal.get('requires_test')!r}")
        else:
            problems.append(f"RULE_UNIMPLEMENTED {rid}: the table names a rule this module does not apply")
    return problems


def problems(proposal, active_keep=None):
    """Every problem of one proposal, §7.2's and §7.3's, in the tables' own order."""
    return structural_problems(proposal, active_keep)


# ---- the tables against the design ---------------------------------------------------------------
#
# §7.2's table, copied from `design/session-distill/2026-10-20T1942--9684f05--mechanism-design.md`
# (### 7.2 Fields) and cited here, as (kind, diagnosis, the allowed dispositions in the design's
# order). The design writes the conditions in prose inside the cells; they are rendered here as the
# table's own condition ids so one comparison covers both.
DESIGN_7_2 = (
    ("gap", "any", "place, incubate, drop"),
    ("misfire", "trigger problem", "re-deliver, correct, incubate, drop (drop_reason_acceptable_miss)"),
    ("misfire", "wrong or insufficient", "correct, incubate, drop (drop_reason_acceptable_miss)"),
    ("misfire", "covered", "correct, re-deliver, reduce (reduce_when_harmful), incubate, "
                           "drop (drop_reason_acceptable_miss)"),
    ("not delivered", "any", "re-deliver, incubate, drop"),
    ("confirmed", "any", "keep, none"),
    ("any", "redundant", "reduce (reduce_by_merge), keep (keep_with_reason), none"),
    ("obsolete", "any", "reduce, keep (keep_with_reason), none"),
    ("any", "any", "incubate (incubate_owner_approved), drop (drop_retire_with_reason), "
                   "none (none_stays_in_intake), place (place_admitted_and_eligible)"),
    ("already resolved", "any", "none"),
    ("unclassified", "any", "none"),
)
# §7.3's structural sentences, copied from the same file (### 7.3 Proposal content (S7), the
# "Structural rules (code)" paragraph) and §10.4's ledger-only sentence from the plan's done-when 6.
DESIGN_7_3 = (
    "Global-file operations other than delete and merge are rejected",
    "an incubate without observation and expiry",
    "keep or drop without reason",
    "a disposition the promotion eligibility or §7.2 does not allow",
    "a disposition the promotion eligibility or §7.2 does not allow",
    "a `reduce` or `merge` touching a unit with an active `keep` record unless the proposal names the record",
    "Keep/incubate/drop proposals carry no library operations and `requires_test == false`",
)


def render_pair_row(row):
    def one(entry):
        return entry["disposition"] + (f" ({entry['requires']})" if entry.get("requires") else "")
    return (row["kind"], row["diagnosis"], ", ".join(one(entry) for entry in row["allowed"]))


def fidelity_problems():
    """The two tables against the design's own rows and sentences, and the conditions against their readers."""
    problems = list(condition_problems())
    rendered = tuple(render_pair_row(row) for row in table("pairs")["rows"])
    if rendered != DESIGN_7_2:
        problems += [f"CONTRACT_DRIFT allowed_pairs row {n + 1}: the table says {have}, §7.2 says {want}"
                     for n, (have, want) in enumerate(itertools.zip_longest(rendered, DESIGN_7_2))
                     if have != want]
    sentences = tuple(rule["design"] for rule in table("rules")["rules"])
    if sentences != DESIGN_7_3:
        problems += [f"CONTRACT_DRIFT structural_rules row {n + 1}: the table says {have!r}, §7.3 says {want!r}"
                     for n, (have, want) in enumerate(itertools.zip_longest(sentences, DESIGN_7_3))
                     if have != want]
    # The vocabularies are the design's four, and nothing reads a fifth.
    held = vocabularies()
    if set(held) != {"kind", "diagnosis", "disposition", "status"}:
        problems.append(f"CONTRACT_DRIFT vocabularies: {sorted(held)}")
    if not table("pairs")["rows"]:
        problems.append("TABLE_EMPTY allowed_pairs: a table with no rows allows nothing and refuses nothing")
    if not table("rules")["rules"]:
        problems.append("TABLE_EMPTY structural_rules: a table with no rules judges nothing")
    return problems


# ---- self-test -----------------------------------------------------------------------------------

def self_test():
    """Positive control first, then one planted violation per rule, each refused BY NAME."""
    failures, ran = [], []
    reporting = []

    def control(name, got, want):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}: this suite has begun publishing its report")
        if not isinstance(got, str):
            raise TypeError(f"CONTROL_GOT_NOT_STR {name}: this helper judges a string, not "
                            f"{type(got).__name__}; a list is truthy whatever it holds")
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

    def said(proposal, active_keep=None):
        return "; ".join(problems(proposal, active_keep))

    # The tables are the design's, and every condition they name has a reader.
    clean("the two tables carry §7.2's rows and §7.3's sentences, and every condition has a reader",
          fidelity_problems())
    # The below-bar dispositions are the §6.4 table's, not a second list: one owner for one value.
    from runlib import derive
    below = next((row.get("allowed_dispositions") for row in derive.table()["promotion"]
                  if row["id"] == "below_bar"), None)
    clean("the below-bar dispositions are the ones the §6.4 table allows, not a copy",
          [] if below is not None and tuple(below) == BELOW_BAR
          else [f"§6.4 says {below}, this module says {list(BELOW_BAR)}"])

    # ---- a proposal that passes, per disposition kind. Every control below plants ONE violation
    # into one of these, so a refusal is attributable to the mutation and not to the fixture.
    place = {"item_id": "i-1", "candidate_id": "k-1", "kind": "gap", "diagnosis": "gap",
             "disposition": "place", "admitted": True, "promotion_eligible": True,
             "requires_test": True, "reason": "the window shows the gap three times",
             "operations": [{"type": "create", "target": "claude/guides/g.md", "before_sha256": None}],
             "expected_observation": {"occasion": "a run of the gate", "expiry": "2027-01-01"}}
    keep = {"item_id": "i-2", "candidate_id": "k-2", "kind": "confirmed", "diagnosis": "covered",
            "disposition": "keep", "promotion_eligible": True, "requires_test": False,
            "reason": "the unit is followed and helps", "operations": []}
    incubate = {"item_id": "i-3", "candidate_id": "k-3", "kind": "misfire", "diagnosis": "trigger problem",
                "disposition": "incubate", "promotion_eligible": False, "requires_test": False,
                "operations": [], "reason": "below the bar, watched instead",
                "expected_observation": {"occasion": "the same situation recurs", "expiry": "2027-02-01"}}
    merge = {"item_id": "i-4", "candidate_id": "k-4", "kind": "misfire", "diagnosis": "redundant",
             "disposition": "reduce", "promotion_eligible": True, "requires_test": True,
             "reason": "two units say the same thing",
             "keep_records_named": ["kr-1"],
             "operations": [{"type": "merge", "target": "claude/guides/g.md", "before_sha256": "a" * 64}]}
    legacy = {"item_id": "i-5", "candidate_id": "S3-03", "kind": "unclassified", "diagnosis": "unknown",
              "disposition": "incubate", "legacy_incubating": True, "promotion_eligible": False,
              "requires_test": False, "operations": [], "reason": "the entry's history is unavailable",
              "expected_observation": {"occasion": "the situation recurs in a later window",
                                       "expiry": "2027-03-01"}}
    for label, proposal in (("a place", place), ("a keep", keep), ("an incubate", incubate),
                            ("a reduce by merge", merge), ("a legacy incubate", legacy)):
        clean(f"{label} proposal that satisfies §7.2 and §7.3 has no problem", problems(proposal))
    clean("and the reduce passes while its keep record is named",
          problems(merge, {"u-1": "kr-1"}))
    # The union's precedence rule, over a PLANTED table: no pair in the real table has an
    # unconditional row after a conditioned one for the same disposition, so the rule has no live
    # case and would otherwise sit here untested. A table that grows will have one.
    held_for_union = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
    try:
        _TABLES["pairs"] = {**held_for_union,
                            "rows": [{"id": "conditioned", "kind": "gap", "diagnosis": "any",
                                      "allowed": [{"disposition": "place", "requires": "keep_with_reason"}]},
                                     {"id": "outright", "kind": "any", "diagnosis": "any",
                                      "allowed": [{"disposition": "place"}]}]}
        clean("where two rows allow one disposition and only one of them conditions it, the "
              "unconditional row is the bar",
              [] if allowed_for("gap", "gap") == {"place": None}
              else [f"the union says {allowed_for('gap', 'gap')}"])
        _TABLES["pairs"] = {**held_for_union,
                            "rows": [{"id": "outright", "kind": "any", "diagnosis": "any",
                                      "allowed": [{"disposition": "place"}]},
                                     {"id": "conditioned", "kind": "gap", "diagnosis": "any",
                                      "allowed": [{"disposition": "place", "requires": "keep_with_reason"}]}]}
        clean("and the order of the two rows does not change that",
              [] if allowed_for("gap", "gap") == {"place": None}
              else [f"the union says {allowed_for('gap', 'gap')}"])
    finally:
        _TABLES["pairs"] = held_for_union

    # ---- one planted violation per rule (O5's fixtures F-O5-05, -06, -07, -14, and §7.3's rest)
    control("F-O5-07: a disposition §7.2 does not allow for the pair is refused by name",
            said({**place, "disposition": "keep"}), "PAIR_DISALLOWED")
    # The whole sorted list, not one word of it: "place" alone appears in half this suite's messages.
    control("and the refusal names what §7.2 does allow there",
            said({**place, "disposition": "keep"}), "§7.2 allows drop, incubate, place")
    control("a disposition §7.2 allows only under a condition is refused when the condition fails",
            said({**merge, "operations": [{"type": "edit", "target": "claude/guides/g.md",
                                           "before_sha256": "a" * 64}]}),
            "only where the reduce is a merge")
    control("F-O5-06: an incubate with no expiry is refused by name",
            said({**incubate, "expected_observation": {"occasion": "x"}}), "EXPIRY_REQUIRED")
    control("and one with no expected observation at all, the same",
            said({**incubate, "expected_observation": None}), "EXPIRY_REQUIRED")
    control("a keep with no reason is refused by name", said({**keep, "reason": ""}), "REASON_REQUIRED")
    control("a drop with no reason, the same",
            said({**place, "disposition": "drop", "reason": None, "operations": [],
                  "requires_test": False}), "REASON_REQUIRED")
    control("F-O5-05: a reduce over a unit with an active keep record the proposal does not name is "
            "refused by name",
            said({**merge, "keep_records_named": []}, {"u-1": "kr-1"}), "KEEP_GUARDED")
    control("and the refusal names the record, so the owner knows what to release",
            said({**merge, "keep_records_named": []}, {"u-1": "kr-1"}), "kr-1")
    control("a merge operation under another disposition is guarded the same way",
            said({**place, "operations": [{"type": "merge", "target": "claude/guides/g.md",
                                           "before_sha256": "a" * 64}]}, {"u-2": "kr-9"}),
            "KEEP_GUARDED")
    control("a global-file operation that is not a delete or a merge is refused by name",
            said({**place, "operations": [{"type": "edit", "target": "claude/CLAUDE.md",
                                           "before_sha256": "a" * 64}]}),
            "GLOBAL_OP_DISALLOWED")
    control("the Korean global file is the same surface",
            said({**place, "operations": [{"type": "create", "target": "ko/claude/CLAUDE.md",
                                           "before_sha256": None}]}),
            "GLOBAL_OP_DISALLOWED")
    clean("while a delete on the global file is allowed",
          problems({**place, "disposition": "reduce", "kind": "obsolete", "diagnosis": "unknown",
                    "operations": [{"type": "delete", "target": "claude/CLAUDE.md",
                                    "before_sha256": "a" * 64}]}))
    control("a candidate below the promotion bar proposed as a place is refused by name",
            said({**place, "promotion_eligible": False}), "PAIR_DISALLOWED")
    control("and the refusal says it was the promotion bar, not the pair",
            said({**place, "promotion_eligible": False}), "below the promotion bar")
    control("F-O5-14: a ledger-only disposition carrying a library operation is refused by name",
            said({**keep, "operations": [{"type": "edit", "target": "claude/guides/g.md",
                                          "before_sha256": "a" * 64}]}),
            "LEDGER_ONLY_VIOLATED")
    control("and one whose requires_test is not false, the same",
            said({**keep, "requires_test": True}), "LEDGER_ONLY_VIOLATED")
    control("a value outside §7.2's vocabulary is named as that, not read as a pair",
            said({**place, "kind": "regression"}), "VALUE_UNKNOWN kind")
    control("and the refusal prints the vocabulary it is outside of",
            said({**place, "diagnosis": "hunch"}), "§7.2's vocabulary is")

    # ---- the legacy row answers for a legacy entry only, which is what keeps it from swallowing
    # every other row: it holds for any kind, unclassified included.
    control("a legacy entry proposed as a correct, which its row does not allow, is refused by name",
            said({**legacy, "disposition": "correct"}), "under the legacy-maintenance row")
    control("an unclassified candidate that is NOT a legacy entry can only be none",
            said({**legacy, "legacy_incubating": False}), "PAIR_DISALLOWED")
    clean("and the same candidate as a legacy entry may be incubated", problems(legacy))
    control("a legacy place without admission and eligibility is refused by name",
            said({**legacy, "disposition": "place", "admitted": False}),
            "only where the entry is admitted")

    # ---- the tables themselves: a planted drift and an emptied table are named
    held_pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
    held_rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    try:
        _TABLES["pairs"] = {**held_pairs, "rows": [{**held_pairs["rows"][0],
                                                    "allowed": [{"disposition": "correct"}]}]
                                                  + held_pairs["rows"][1:]}
        control("a pairs table that drifts from §7.2 is named by row",
                "; ".join(fidelity_problems()), "CONTRACT_DRIFT allowed_pairs row 1")
        _TABLES["pairs"] = {**held_pairs, "rows": []}
        control("and an emptied pairs table is named rather than passing over nothing",
                "; ".join(fidelity_problems()), "TABLE_EMPTY allowed_pairs")
        _TABLES["pairs"] = held_pairs
        _TABLES["rules"] = {**held_rules, "rules": [{**held_rules["rules"][0], "design": "anything"}]
                                                   + held_rules["rules"][1:]}
        control("a structural table that drifts from §7.3 is named by row",
                "; ".join(fidelity_problems()), "CONTRACT_DRIFT structural_rules row 1")
        _TABLES["rules"] = {**held_rules,
                            "rules": held_rules["rules"] + [{"id": "invented", "code": "X", "design": "y",
                                                             "applies_to": "", "requires": ""}]}
        control("a rule the table names and this module does not apply is named",
                said(place), "RULE_UNIMPLEMENTED invented")
        _TABLES["pairs"] = {**held_pairs,
                            "conditions": {**held_pairs["conditions"], "never_checked": "a condition nobody asks"}}
        _TABLES["rules"] = held_rules
        control("a condition the table names with no reader is named",
                "; ".join(fidelity_problems()), "CONDITION_UNCHECKED never_checked")
    finally:
        _TABLES["pairs"], _TABLES["rules"] = held_pairs, held_rules
    clean("and the tables are back as they are on disk", fidelity_problems())

    reporting.append(True)
    if failures:
        for name, detail in failures:
            print(f"placement --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"placement --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"placement --self-test: OK ({len(ran)} controls: §7.2's pairs and their conditions, §7.3's "
          f"structural rules and §10.4's ledger-only rule, each from its table and each planted "
          f"violation refused by name, with the tables held against the design's own rows)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit("usage: placement.py --self-test")
