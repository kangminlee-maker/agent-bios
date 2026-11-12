#!/usr/bin/env python3
"""§11's exposure predicate, one branch per table row (WP-21 commit 7).

Design §11: an occasion's exposure to the applied item "must be shown BEFORE the decision or action
the occasion concerns, not before the session began", and what counts as shown depends on what was
applied — a created unit's delivered version, a deleted unit's absence from the pin, a route's entry,
an executable's invocation path and hash, the installer's receipt digests, a deleted executable's
effective resolution, a personal layer's identity and loading record.

`tables/exposure_rules.json` holds those branches as data with the design clause each comes from;
this module picks the one row that applies and answers. It decides nothing a row does not state,
which is why the predicate's branch set can be held against §11's (done-when 12) instead of trusted.

**Three verdicts, and the reason is in the table's own `$comment_verdicts`.** §11's sentence names
two — `eligible`, `exposure_unknown` — while the plan's O9 fixtures distinguish an occasion shown NOT
exposed (an installer change with the old installer on the receipt) from one that cannot be shown (no
resolution recorded). `not_exposed` is the third, and `runlib/measures.py`, which admits only two,
receives those occasions as a COUNT rather than as instances: calling them eligible would count an
occasion the item could not reach, and calling them unknown would hold the window pending forever on
a question that has been answered.

**The ordering rule is the occasion's, not this module's.** §11 says exposure must be shown before
the decision the occasion concerns. An occasion record carries `at_record`, and every fact offered
as exposure carries the record it was observed at; a fact observed AFTER the decision is not
exposure, and this module refuses it by name rather than reading it.

    exposure.py --self-test
"""
import ast
import json
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import measures  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
TABLE_PATH = HERE / "tables" / "exposure_rules.json"
# §11's own two, which `measures` admits, and the third the O9 fixtures distinguish.
ELIGIBLE, NOT_EXPOSED, UNKNOWN = "eligible", "not_exposed", "exposure_unknown"
VERDICTS = (ELIGIBLE, NOT_EXPOSED, UNKNOWN)
_TABLE = {}


def table():
    if not _TABLE:
        _TABLE.update(json.loads(TABLE_PATH.read_text(encoding="utf-8")))
    return _TABLE


def rules():
    return tuple(table()["rules"])


def branches():
    return tuple(row["id"] for row in rules())


def table_problems():
    """What is wrong with the rule table itself, by name."""
    problems, rows = [], rules()
    if not rows:
        problems.append("RULE_SET_EMPTY: a predicate over no rule answers nothing")
        return problems
    seen, verdicts = set(), table().get("verdicts") or {}
    if sorted(verdicts) != sorted(VERDICTS):
        problems.append(f"VERDICT_SET: the table names {', '.join(sorted(verdicts))}, the code "
                        f"{', '.join(sorted(VERDICTS))}")
    for row in rows:
        name = row.get("id")
        if not name:
            problems.append("RULE_UNNAMED: a row with no id")
            continue
        if name in seen:
            problems.append(f"RULE_REPEATED {name}: two rows claiming one branch")
        seen.add(name)
        for field in ("applies_to", "requires", "shown_when", "design", "$comment"):
            if not row.get(field):
                problems.append(f"RULE_INCOMPLETE {name}: no {field}")
        if row.get("unknown_when"):
            try:
                _unknown(row, {"facts": {}})
            except Refused as exc:
                problems.append(f"RULE_UNKNOWN_UNREAD {name}: {exc}")
        # Every fact a predicate READS must be declared, as required or as optional. Undeclared, an
        # absent fact compares equal to None and the branch answers from nothing: `pin_units: []`
        # alone was certified eligible because `removed_unit` and `merged_unit` were neither
        # required nor declared optional.
        declared = set(row.get("requires") or ())
        for held_names in (row.get("requires_by_operation") or {}).values():
            declared |= set(held_names)
        declared |= set(row.get("optional_facts") or ())
        for field in ("shown_when", "unknown_when"):
            if not row.get(field):
                continue
            try:
                _eval(row[field], {}, f"{name}.{field}")
            except Refused as exc:
                problems.append(f"RULE_PREDICATE_UNREADABLE {name}: {exc}")
                continue
            undeclared = sorted(predicate_names(row[field]) - declared)
            if undeclared:
                problems.append(f"RULE_FACT_UNDECLARED {name}.{field}: reads "
                                f"{', '.join(undeclared)}, which the row declares neither in "
                                f"requires/requires_by_operation nor in optional_facts — an "
                                f"undeclared fact answers from its own absence")
        for operation in (row.get("requires_by_operation") or {}):
            if operation not in ((row.get("applies_to") or {}).get("operation") or ()):
                problems.append(f"RULE_OPERATION_UNCLAIMED {name}: requires_by_operation names "
                                f"{operation}, which this row does not apply to")
        if not (row.get("applies_to") or {}).get("operation") and not (row.get("applies_to") or {}).get("role"):
            problems.append(f"RULE_APPLIES_TO_NOTHING {name}: a row answering for no operation and "
                            f"no role is never picked")
        for key in (row.get("applies_to") or {}):
            if key not in precedence():
                problems.append(f"RULE_KEY_UNRANKED {name}: applies_to names {key}, which the "
                                f"table's precedence does not rank, so two rows matching on it "
                                f"could not be separated")
    if not precedence():
        problems.append("PRECEDENCE_UNSTATED: with no key order, a row matching one key and a row "
                        "matching another are separated by their position in the file")
    return problems


def precedence():
    """The applies_to keys, most specific first, as the table declares them."""
    return tuple(table().get("precedence") or ())


def rule_for(occasion):
    """The one row that answers for this occasion, or None. Refuses an ambiguous match.

    A role is more specific than an operation: a DELETED executable is answered by
    `executable_deleted`, not by `delete_or_merge`, because §11 writes that branch separately.

    Counting MATCHED KEYS was not enough, and round 2 found what that let through: an occasion of
    operation `edit` and role `installer` matches `create_or_edit` on its one key and
    `executable_installer` on its one key, and the loop kept whichever came FIRST in the file —
    `create_or_edit`, so an installer's exposure was judged by a library unit's rule. The weights
    come from the table's `precedence` now, and a genuine tie is REFUSED rather than broken by
    position: two rows claiming one occasion is a table defect, not something to answer by guessing.
    """
    operation, role = occasion.get("operation"), occasion.get("role")
    order = precedence()
    asked = {"operation": operation, "role": role}
    matched = []
    for row in rules():
        applies = row.get("applies_to") or {}
        wants = {key: applies.get(key) for key in order}
        if not any(wants.values()):
            continue
        if any(value and asked.get(key) not in value for key, value in wants.items()):
            continue
        # Most specific first: more matched keys outranks fewer, and among equal counts a row
        # matched on an EARLIER key in the declared precedence outranks one matched on a later key.
        weight = tuple(1 if wants.get(key) else 0 for key in order)
        matched.append((weight, row))
    if not matched:
        return None
    rank = lambda held: (sum(held), held)                                       # noqa: E731
    best = max(matched, key=lambda held: rank(held[0]))
    tied = sorted(row["id"] for weight, row in matched if rank(weight) == rank(best[0]))
    if len(tied) > 1:
        raise Refused(f"EXPOSURE_RULE_AMBIGUOUS {occasion.get('locator')}: {', '.join(tied)} claim "
                      f"one occasion (operation={operation!r} role={role!r}) at the same "
                      f"specificity, and the table's precedence {list(order)} does not separate "
                      f"them")
    return best[1]


def ordering_problems(occasion, required=()):
    """Facts offered as exposure that were observed at or after the decision, by name.

    §11: exposure must be shown BEFORE the decision or action the occasion concerns. A fact observed
    after it is not exposure, and reading it would answer the question with evidence from the wrong
    side of the decision.
    """
    at = occasion.get("at_record")
    if at is None:
        return [f"OCCASION_UNPOSITIONED {occasion.get('locator')}: the occasion records no position, "
                f"so 'before the decision' has nothing to be before"]
    problems = []
    for name, held in sorted((occasion.get("facts") or {}).items()):
        if not isinstance(held, dict) or "at_record" not in held:
            # A fact the ANSWER rests on must say where it was observed. An unpositioned one used to
            # be skipped, so an occasion could be certified eligible with no evidence at all that
            # its facts precede the decision — the ordering rule simply had nothing to read (the
            # round-3 review). A fact the rule does not require is not part of the answer, and is
            # not held to it.
            if name in (required or ()):
                problems.append(f"FACT_UNPOSITIONED {occasion.get('locator')} {name}: the answer "
                                f"rests on this fact and it records no position, so whether it was "
                                f"observed before the decision cannot be shown")
            continue
        if held["at_record"] >= at:
            problems.append(f"FACT_AFTER_DECISION {occasion.get('locator')} {name}: observed at "
                            f"record {held['at_record']} and the decision is at {at}, so it is not "
                            f"exposure to it")
    return problems


# ─── The predicate itself ────────────────────────────────────────────────────────────────────────
# `shown_when` and `unknown_when` are EXECUTED, over a grammar small enough to read in one sitting.
# They used to be prose beside a branch that dispatched on the row's id, and round 2 showed what
# that costs: replacing `create_or_edit.shown_when` with `False` left every answer unchanged, so
# the table described the predicate without being it. The only way a declaration cannot drift from
# the code is for the code to have no second copy to drift from.
#
# What the grammar admits: names (facts), the constants None/True/False and literal strings and
# numbers, `and`/`or`/`not`, the comparisons `== != is is not in not in`, and tuple and list
# literals. No calls, no attributes, no subscripts, no arithmetic — a predicate that needed one
# would be a branch in code again, and the table would have stopped being the authority.
_EVAL_COMPARISONS = {ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
                     ast.Is: lambda a, b: a is b, ast.IsNot: lambda a, b: a is not b,
                     ast.In: lambda a, b: a in (b if b is not None else ()),
                     ast.NotIn: lambda a, b: a not in (b if b is not None else ())}


def _eval(expression, facts, where):
    """The expression's truth over `facts`, or Refused if it is outside the grammar."""
    def refuse(node):
        return Refused(f"EXPOSURE_PREDICATE_UNREADABLE {where}: {expression!r} uses "
                       f"{type(node).__name__}, which this module does not execute; a predicate "
                       f"outside the grammar would have to be a branch in code, and then the table "
                       f"would no longer be the authority")

    def value(node):
        if isinstance(node, ast.BoolOp):
            held = [value(part) for part in node.values]
            return all(held) if isinstance(node.op, ast.And) else any(held)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not value(node.operand)
        if isinstance(node, ast.Compare):
            left = value(node.left)
            for operator, right in zip(node.ops, node.comparators):
                held = _EVAL_COMPARISONS.get(type(operator))
                if held is None:
                    raise refuse(operator)
                right_value = value(right)
                if not held(left, right_value):
                    return False
                left = right_value
            return True
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.Tuple, ast.List)):
            return tuple(value(part) for part in node.elts)
        if isinstance(node, ast.Name):
            return facts.get(node.id)
        raise refuse(node)

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise Refused(f"EXPOSURE_PREDICATE_UNPARSED {where}: {expression!r} ({exc})") from exc
    return bool(value(tree.body))


def predicate_names(expression):
    """Every fact name an expression reads. Derived, so a declaration cannot omit one silently."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return set()
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def predicate_reads(row):
    """Every fact name the row's own predicates READ, taken from their source.

    Derived rather than listed: `requires` is the floor the answer cannot be given without, and the
    predicate reads more than that. An OPTIONAL fact the predicate reads decides the answer when it
    is supplied — `required_replacement` turned `exposure_unknown` into `eligible` — so giving it
    without a position was a way past the before-the-decision rule (the round-4 review).
    """
    held = set()
    for expression in (row.get("shown_when"), row.get("unknown_when")):
        if expression:
            # The names come from the one reader that already parses these expressions, so this
            # cannot disagree with what the predicate actually reads.
            held |= set(predicate_names(str(expression)))
    return held


def positioned_facts(row, occasion):
    """The facts this answer must have a position for: what the predicate reads and the occasion gave.

    Optionality says whether a fact must EXIST. It says nothing about the timing of one that was
    supplied and is read, which is what the ordering rule is for.
    """
    held = set(required_facts(row, occasion))
    supplied = set((occasion.get("facts") or {}))
    return sorted(held | (predicate_reads(row) & supplied))


def required_facts(row, occasion):
    """The facts this row's predicate cannot be shown without, for THIS occasion's operation.

    `requires` is the row's floor; `requires_by_operation` adds what a particular operation needs.
    A merge needs the unit it merged into, a plain delete does not — and with neither required, an
    occasion carrying only `pin_units: []` was certified eligible because every absent fact
    compared equal to None. An absent fact is 'cannot be shown', which is `exposure_unknown`.
    """
    held = list(row.get("requires") or ())
    by_operation = row.get("requires_by_operation") or {}
    for name in by_operation.get(occasion.get("operation"), ()):
        if name not in held:
            held.append(name)
    return held


def _facts_of(occasion):
    """Every fact the occasion carries, by name, with positioned facts unwrapped."""
    return {name: _value(occasion, name) for name in (occasion.get("facts") or {})}


def _value(occasion, name):
    """One fact's value, whether it is a bare value or a positioned `{value, at_record}`."""
    held = (occasion.get("facts") or {}).get(name)
    if isinstance(held, dict) and "value" in held:
        return held["value"]
    return held


def verdict(occasion):
    """`{verdict, rule, why}` for one occasion. Refuses an occasion no rule answers for.

    The rule's `requires` decides answerability: a required fact absent means the question cannot be
    shown either way, which is `exposure_unknown` — never `not_exposed`. That is the distinction the
    O9 fixtures turn on, and reading an absent fact as a negative answer is the mistake §11's
    'cannot be shown' clause exists to prevent.
    """
    row = rule_for(occasion)
    if row is None:
        raise Refused(f"EXPOSURE_RULE_ABSENT {occasion.get('locator')}: no §11 branch answers for "
                      f"operation={occasion.get('operation')!r} role={occasion.get('role')!r}")
    held = ordering_problems(occasion, positioned_facts(row, occasion))
    if held:
        return {"verdict": UNKNOWN, "rule": row["id"], "why": "; ".join(held)}
    facts = _facts_of(occasion)
    missing = [name for name in required_facts(row, occasion) if facts.get(name) is None]
    if missing:
        return {"verdict": UNKNOWN, "rule": row["id"],
                "why": f"EXPOSURE_FACT_ABSENT {', '.join(missing)}: the branch cannot be shown "
                       f"either way, so the occasion is carried rather than answered"}
    # A row's `unknown_when` is read BEFORE its `shown_when`: §11 writes the unknown case into two
    # of its branches itself ("a transaction begun or finished by another installer version, or an
    # unbound one, is exposure_unknown"), and a condition like that answered as `not_exposed` would
    # say the item could not have fired where the design says nobody knows. The field had no reader
    # for one commit, which is the label-nobody-reads trap in its own right.
    #
    # Both conditions are the TABLE's expressions, executed. `_unknown` and `_shown` are consulted
    # for the sentence a reader needs and for nothing else: they no longer decide, so a row whose
    # condition is edited changes the answer.
    if row.get("unknown_when"):
        if _eval(row["unknown_when"], facts, f"{row['id']}.unknown_when"):
            return {"verdict": UNKNOWN, "rule": row["id"], "why": _unknown(row, occasion)[1]}
    shown = _eval(row["shown_when"], facts, f"{row['id']}.shown_when")
    return {"verdict": ELIGIBLE if shown else NOT_EXPOSED, "rule": row["id"],
            "why": _shown(row, occasion)[1]}


def _unknown(row, occasion):
    """The sentence for this row's unknown condition, when it holds.

    The table's `unknown_when` decides; this says it in words. The boolean it returns is the
    SENTENCE's subject, read by `table_problems` to show the two agree — never by `verdict`, which
    executes the expression. One decider, one explainer.
    """
    get = lambda name: _value(occasion, name)                                   # noqa: E731
    name = row["id"]
    if name == "executable_installer":
        begun = get("begun_by_installer_digest")
        if begun is not None and begun != get("applied_sha256"):
            return True, (f"the receipt says the transaction was begun by {str(begun)[:12]}… and "
                          f"finished by another version, so §11 shows nobody which version the "
                          f"session was exposed to")
        return False, ""
    if name == "executable_deleted":
        if get("resolved_path") is None and get("resolved_sha256") is None:
            return True, "the occasion recorded no resolution, so §11's exposure cannot be shown"
        return False, ""
    if name == "personal":
        if get("loading_record") is None:
            return True, "the host recorded no loading, so whether the layer was loaded is unknown"
        return False, ""
    raise Refused(f"EXPOSURE_UNKNOWN_UNIMPLEMENTED {name}: the table declares an unknown condition "
                  f"this module does not read, so the field would have no reader")


def _shown(row, occasion):
    """The sentence a reader needs for this row, and the subject of that sentence.

    As with `_unknown`: the table's `shown_when` is what `verdict` executes. This function explains
    the answer in the words of the facts, and `table_problems` holds its boolean against the
    executed expression for every generated fixture, so an explanation that says the opposite of
    the answer is a named failure rather than a surprise in a report.
    """
    get = lambda name: _value(occasion, name)                                   # noqa: E731
    name = row["id"]
    if name == "create_or_edit":
        held = get("delivered_version") == get("applied_version")
        return held, (f"the delivered version {str(get('delivered_version'))[:12]}… "
                      f"{'is' if held else 'is not'} the applied one")
    if name == "delete_or_merge":
        units = get("pin_units") or []
        removed_absent = get("removed_unit") not in units
        merged = get("merged_unit")
        merged_present = merged is None or merged in units
        held = removed_absent and merged_present
        return held, (f"the pin {'does not hold' if removed_absent else 'still holds'} the removed "
                      f"unit and {'holds' if merged_present else 'does not hold'} the merged one")
    if name == "route":
        held = get("route_entry") in (get("pin_routes") or []) and \
            get("routed_unit") in (get("pin_units") or [])
        return held, ("the pin shows the route entry and the unit it reaches" if held
                      else "the pin shows no route entry reaching the unit")
    if name == "executable_invoked":
        held = (get("invocation_path") == get("applied_path")
                and get("invocation_sha256") == get("applied_sha256"))
        return held, (f"the invocation names {str(get('invocation_path'))} at "
                      f"{str(get('invocation_sha256'))[:12]}…, "
                      f"{'the applied artifact' if held else 'not the applied artifact'}")
    if name == "executable_compiler":
        held = get("compiler_digest") == get("applied_sha256")
        return held, (f"the snapshot records compiler digest {str(get('compiler_digest'))[:12]}…, "
                      f"{'the applied version' if held else 'another version'}")
    if name == "executable_installer":
        begun = get("begun_by_installer_digest")
        held = (get("installer_digest") == get("applied_sha256")
                and begun in (None, get("applied_sha256")))
        return held, (f"the receipt names installer {str(get('installer_digest'))[:12]}… and "
                      f"{'no other beginner' if begun is None else 'beginner ' + str(begun)[:12] + '…'}")
    if name == "executable_deleted":
        resolved = get("resolved_sha256")
        replacement = get("required_replacement")
        held = (resolved != get("removed_sha256") and resolved != get("fallback_sha256")
                and (replacement is None or resolved == replacement))
        return held, (f"the effective resolution is {str(resolved)[:12]}…, "
                      f"{'neither the removed artifact nor an older carrier' if held else 'the removed artifact or an older carrier'}")
    if name == "personal":
        held = get("layer_sha256") == get("applied_sha256") and get("loading_record") is True
        return held, (f"the layer's identity {'matches' if get('layer_sha256') == get('applied_sha256') else 'does not match'} "
                      f"and the host's record says {'loaded' if get('loading_record') is True else 'not loaded'}")
    raise Refused(f"EXPOSURE_BRANCH_UNIMPLEMENTED {name}: the table names a branch this module does "
                  f"not answer, so the predicate is narrower than its own table")


def instances_for(expected_id, occasions, basis):
    """`{instances, not_exposed, verdicts}` — what `measures.derive_resolution` may be handed.

    The `not_exposed` occasions are COUNTED and listed, never passed on as instances: `measures`
    admits two exposure values, and either choice for a not-exposed occasion is wrong in a different
    direction. The count is what makes the exclusion visible in the run record.
    """
    instances, excluded, held = [], [], {}
    for occasion in occasions or ():
        answer = verdict(occasion)
        held[occasion.get("locator")] = answer
        if answer["verdict"] == NOT_EXPOSED:
            excluded.append({"locator": occasion.get("locator"), "rule": answer["rule"],
                             "why": answer["why"]})
            continue
        instances.append({"expected_id": expected_id,
                          "occasion_locator": occasion.get("locator"),
                          "exposure": answer["verdict"],
                          "verdict": occasion.get("judged") or "not_observed",
                          "basis": basis,
                          "evidence_ids": occasion.get("evidence_ids") or []})
    return {"instances": instances, "not_exposed": excluded, "verdicts": held}


def resolution_for(expected_id, occasions, basis):
    """The window resolution, through `measures.derive_resolution`, with the exclusions beside it.

    The resolution half is WP-08's and stays there: this module decides exposure and hands it over.
    """
    built = instances_for(expected_id, occasions, basis)
    held = measures.derive_resolution(built["instances"], basis)
    return {**held, "not_exposed": built["not_exposed"],
            "counts": {**held["counts"], "not_exposed": len(built["not_exposed"])}}


def fixture_cases():
    """Three cases per rule, generated FROM the rule: shown, shown absent, unanswerable.

    Done-when 7 asks for a generated fixture per rule. Generated rather than written out, so a branch
    added to the table without its cases cannot go untested — `fixture_problems` fails on a rule
    whose generated cases do not come back with the verdicts their construction implies.
    """
    cases = []
    for row in rules():
        name = row["id"]
        shown, absent, unknown = _fixture_facts(name)
        applies = row.get("applies_to") or {}
        operation = (applies.get("operation") or [None])[0]
        role = (applies.get("role") or [None])[0]
        # The 'absent' case is NOT_EXPOSED only where the rule HAS such an answer. The installer
        # branch does not: §11 says a transaction whose receipt names another version is unknown, so
        # for that rule every state is eligible or unknown, and a generator that assumed three
        # verdicts was asserting an answer the design does not have (the round-3 review). Read from
        # the row's own unknown condition over the case's own facts.
        held_absent = (UNKNOWN if row.get("unknown_when")
                       and _eval(row["unknown_when"], absent, f"{name}.unknown_when")
                       else NOT_EXPOSED)
        for label, facts, want in (("shown", shown, ELIGIBLE), ("absent", absent, held_absent),
                                   ("unanswerable", unknown, UNKNOWN)):
            # Every fact is POSITIONED before the decision, because that is what the answer now
            # requires: a fact the rule rests on says where it was observed, and a generated
            # fixture that left it bare would be asking for an answer §11 does not allow.
            cases.append({"id": f"F-EXP-{name}-{label}", "rule": name, "expect": want,
                          "occasion": {"locator": f"{name}/{label}", "operation": operation,
                                       "role": role, "at_record": 10,
                                       "facts": {held: {"value": value, "at_record": 5}
                                                 for held, value in facts.items()}}})
    return cases


APPLIED, OTHER = "ap" + "p" * 62, "ot" + "h" * 62


def _fixture_facts(name):
    """The three fact sets for one rule: shown, shown absent, and one a required fact is missing from."""
    if name == "create_or_edit":
        return ({"delivered_version": APPLIED, "applied_version": APPLIED},
                {"delivered_version": OTHER, "applied_version": APPLIED},
                {"applied_version": APPLIED})
    if name == "delete_or_merge":
        return ({"pin_units": ["u-kept", "u-merged"], "removed_unit": "u-gone",
                 "merged_unit": "u-merged"},
                {"pin_units": ["u-gone", "u-merged"], "removed_unit": "u-gone",
                 "merged_unit": "u-merged"},
                {"removed_unit": "u-gone", "merged_unit": "u-merged"})
    if name == "route":
        return ({"pin_routes": ["r-1"], "pin_units": ["u-1"], "route_entry": "r-1",
                 "routed_unit": "u-1"},
                {"pin_routes": ["r-1"], "pin_units": [], "route_entry": "r-1",
                 "routed_unit": "u-1"},
                {"route_entry": "r-1", "routed_unit": "u-1"})
    if name == "executable_invoked":
        return ({"invocation_path": "bin/w", "invocation_sha256": APPLIED, "applied_path": "bin/w",
                 "applied_sha256": APPLIED},
                {"invocation_path": "bin/w", "invocation_sha256": OTHER, "applied_path": "bin/w",
                 "applied_sha256": APPLIED},
                {"applied_path": "bin/w", "applied_sha256": APPLIED})
    if name == "executable_compiler":
        return ({"compiler_digest": APPLIED, "applied_sha256": APPLIED},
                {"compiler_digest": OTHER, "applied_sha256": APPLIED},
                {"applied_sha256": APPLIED})
    if name == "executable_installer":
        return ({"installer_digest": APPLIED, "applied_sha256": APPLIED,
                 "begun_by_installer_digest": None},
                {"installer_digest": OTHER, "applied_sha256": APPLIED,
                 "begun_by_installer_digest": None},
                {"applied_sha256": APPLIED})
    if name == "executable_deleted":
        return ({"resolved_path": "bin/new", "resolved_sha256": APPLIED, "removed_sha256": OTHER,
                 "fallback_sha256": "fa" + "l" * 62, "required_replacement": APPLIED},
                {"resolved_path": "bin/old", "resolved_sha256": "fa" + "l" * 62,
                 "removed_sha256": OTHER, "fallback_sha256": "fa" + "l" * 62,
                 "required_replacement": APPLIED},
                {"removed_sha256": OTHER, "fallback_sha256": "fa" + "l" * 62})
    if name == "personal":
        return ({"layer_sha256": APPLIED, "applied_sha256": APPLIED, "loading_record": True},
                {"layer_sha256": OTHER, "applied_sha256": APPLIED, "loading_record": True},
                {"layer_sha256": APPLIED, "applied_sha256": APPLIED})
    raise Refused(f"FIXTURE_UNGENERATED {name}: the table names a branch this generator has no cases "
                  f"for, so adding a rule without its fixtures would leave it untested")


def fixture_problems():
    """Every generated case whose verdict is not the one its construction implies, by name."""
    problems = []
    for case in fixture_cases():
        try:
            answer = verdict(case["occasion"])
        except Refused as exc:
            problems.append(f"FIXTURE_REFUSED {case['id']}: {exc}")
            continue
        if answer["verdict"] != case["expect"]:
            problems.append(f"FIXTURE_CHANGED {case['id']}: {answer['verdict']} where the case is "
                            f"built to be {case['expect']} ({answer['why']})")
        if answer["rule"] != case["rule"]:
            problems.append(f"FIXTURE_RULE {case['id']}: answered by {answer['rule']}")
    return problems


def document():
    """The predicate, for a reader checking it against §11."""
    return {"branches": list(branches()), "verdicts": list(VERDICTS),
            "design": {row["id"]: row["design"] for row in rules()},
            "cases": len(fixture_cases())}


# ---- self-test ---------------------------------------------------------------------------------


def self_test():
    """Every §11 branch, each table defect planted, and the three verdicts.

    The body is wrapped so a control that DIES still speaks: a traceback is not a control firing,
    and a revert trial that reads any output counts one as if it were. Found here by a revert trial
    of this unit's own round-2 fixes — the precedence row made `rule_for` refuse, a control read its
    answer without guarding, and the suite ended in a traceback with no [FAIL] line at all.
    """
    failures, ran = [], []
    try:
        return _self_test_body(failures, ran)
    except BaseException as exc:  # noqa: BLE001 - the suite must speak before it dies
        held = ran[-1] if ran else "<no control ran>"
        print(f"exposure --self-test [FAIL] the suite died after {held!r}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        for name, detail in failures:
            print(f"exposure --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"exposure --self-test: INCOMPLETE ({len(ran)} controls ran, {len(failures)} failed "
              f"before the suite died)", file=sys.stderr)
        raise


def _self_test_body(failures, ran):
    def control(name, got, want):
        ran.append(name)
        if want not in str(got):
            failures.append((name, f"expected {want!r} in {str(got)[:400]!r}"))

    def equals(name, got, want):
        """A control whose expectation is the WHOLE answer, not a fragment of it."""
        ran.append(name)
        if str(got) != str(want):
            failures.append((name, f"expected exactly {want!r}, got {str(got)[:400]!r}"))

    def clean(name, held):
        ran.append(name)
        if held:
            failures.append((name, f"expected nothing, got {held}"))

    def refusal(call):
        try:
            call()
        except Refused as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - a control that dies is not a control
            return f"RAISED {type(exc).__name__}: {exc}"
        return ""

    def answered_by(**occasion):
        """`rule=<id>` for this occasion, or the exception as text.

        The prefix is the point: `EXPOSURE_RULE_AMBIGUOUS create_or_edit, executable_installer ...`
        CONTAINS the id a control is looking for, so a bare substring check read a refusal as the
        right answer — this unit's own revert trial found the precedence control passing under a
        mutation that made every match a tie.
        """
        try:
            return f"rule={rule_for(occasion)['id']}"
        except BaseException as exc:  # noqa: BLE001 - the exception is the answer here
            return f"RAISED {type(exc).__name__}: {exc}"

    def guarded(call):
        """The call's answer, or the exception as text.

        A control that reads an answer a revert can make raise must not die on it: the exception IS
        the finding, and it has to reach a [FAIL] line to be one.
        """
        try:
            return call()
        except BaseException as exc:  # noqa: BLE001 - the exception is the answer here
            return f"RAISED {type(exc).__name__}: {exc}"

    def row_of(held, name):
        """The mutable row with this id, inside a `with_table` copy.

        By id rather than by position: a control that indexes `rules[4]` mutates whatever sits
        there, and a table reordered later would leave the control green while testing another
        branch.
        """
        for row in held["rules"]:
            if row["id"] == name:
                return row
        raise AssertionError(f"the suite's own fixture is stale: no rule {name!r} to mutate")

    def with_table(mutate, call):
        held = json.loads(json.dumps(table()))
        try:
            mutate(_TABLE)
            return call()
        finally:
            _TABLE.clear()
            _TABLE.update(held)

    # ---- the table -------------------------------------------------------------------------------
    clean("the rule table is well formed", table_problems())
    control("an empty rule set is refused, because a predicate over no rule answers nothing",
            "; ".join(with_table(lambda t: t.__setitem__("rules", []), table_problems)),
            "RULE_SET_EMPTY")
    control("two rows claiming one branch are refused",
            "; ".join(with_table(lambda t: t["rules"].append(dict(t["rules"][0])), table_problems)),
            "RULE_REPEATED create_or_edit")
    control("a row answering for no operation and no role is refused: it is never picked",
            "; ".join(with_table(lambda t: t["rules"][0].__setitem__("applies_to", {"note": "x"}),
                                 table_problems)),
            "RULE_APPLIES_TO_NOTHING")
    control("a row missing its design clause is refused, since the clause is what the branch rests on",
            "; ".join(with_table(lambda t: t["rules"][0].pop("design"), table_problems)),
            "RULE_INCOMPLETE create_or_edit: no design")
    control("the table's verdicts and the code's are held against each other",
            "; ".join(with_table(lambda t: t["verdicts"].pop("not_exposed"), table_problems)),
            "VERDICT_SET")

    # ---- which rule answers ----------------------------------------------------------------------
    control("a created unit is answered by the create-or-edit branch",
            str(rule_for({"operation": "create"})["id"]), "create_or_edit")
    control("a deleted UNIT by the delete-or-merge branch",
            str(rule_for({"operation": "delete"})["id"]), "delete_or_merge")
    control("while a deleted EXECUTABLE is answered by its own branch, which §11 writes separately",
            str(rule_for({"operation": "delete", "role": "wrapper"})["id"]), "executable_deleted")
    control("an invoked wrapper by the invoked branch",
            str(rule_for({"role": "wrapper"})["id"]), "executable_invoked")
    control("the installer by the single installer predicate",
            str(rule_for({"role": "installer"})["id"]), "executable_installer")
    control("an occasion no branch answers for is refused by name, with what it carried",
            refusal(lambda: verdict({"locator": "x", "operation": "rename"})),
            "EXPOSURE_RULE_ABSENT x")
    # Round 2: an EDITED installer. Both rows match at one key each, and the generic row used to
    # win by sitting earlier in the file, so an installer's exposure was judged by the rule for a
    # library unit's delivered version.
    control("an edited INSTALLER is answered by the installer's own branch, not by the generic "
            "create-or-edit row both rows match at one key",
            answered_by(operation="edit", role="installer"), "rule=executable_installer")
    control("and so is a created hook",
            answered_by(operation="create", role="hook"), "rule=executable_invoked")
    control("the role precedence is the TABLE's: with the key order reversed, the generic row wins "
            "and the answer changes, so the declaration is what decides",
            str(guarded(lambda: with_table(
                lambda held: held.__setitem__("precedence", ["operation", "role"]),
                lambda: answered_by(operation="edit", role="installer")))),
            "rule=create_or_edit")
    control("a genuine tie is REFUSED rather than broken by position",
            refusal(lambda: with_table(
                lambda held: row_of(held, "executable_compiler").__setitem__("applies_to", {"role": ["installer"]}),
                lambda: verdict({"locator": "tie", "role": "installer", "at_record": 2,
                                 "facts": {}}))),
            "EXPOSURE_RULE_AMBIGUOUS tie")
    control("and an unranked applies_to key is a table defect, since nothing could separate two "
            "rows matching on it",
            str(with_table(lambda held: row_of(held, "create_or_edit")["applies_to"].__setitem__("host", ["claude"]),
                           table_problems)),
            "RULE_KEY_UNRANKED")
    control("a table with no precedence at all is refused",
            str(with_table(lambda held: held.__setitem__("precedence", []), table_problems)),
            "PRECEDENCE_UNSTATED")

    # ---- the three verdicts ----------------------------------------------------------------------
    def occasion(**over):
        held = {"locator": "o-1", "operation": "create", "at_record": 10,
                "facts": {"delivered_version": {"value": APPLIED, "at_record": 9}, "applied_version": {"value": APPLIED, "at_record": 9}}}
        held.update(over)
        # POSITIONED before the decision unless the caller said otherwise: a fact the answer rests
        # on records where it was observed, and a fixture that leaves it bare is asking for an
        # answer §11 does not allow. A caller that positions a fact itself — which is how the
        # after-the-decision cases are built — keeps its own value.
        held_at = held.get("at_record")
        held["facts"] = {name: (value if isinstance(value, dict) and "at_record" in value
                                or held_at is None
                                else {"value": value, "at_record": held_at - 5})
                         for name, value in (held.get("facts") or {}).items()}
        return held

    control("a merge whose merged unit the pin does NOT hold is not exposure, even though the "
            "removal succeeded: the branch has two halves and one generated negative covers only one",
            verdict({"locator": "m-1", "operation": "merge", "at_record": 5,
                     "facts": {"pin_units": {"value": ["u-kept"], "at_record": 4}, "removed_unit": {"value": "u-gone", "at_record": 4}, "merged_unit": {"value": "u-merged", "at_record": 4}}})["verdict"], NOT_EXPOSED)
    control("and the why says which half failed",
            verdict({"locator": "m-1", "operation": "merge", "at_record": 5,
                     "facts": {"pin_units": {"value": ["u-kept"], "at_record": 4}, "removed_unit": {"value": "u-gone", "at_record": 4}, "merged_unit": {"value": "u-merged", "at_record": 4}}})["why"],
            "does not hold the merged one")
    control("an invocation at the applied PATH but the old HASH is not exposure, for the same "
            "reason: §6.3's levels exist to catch exactly that",
            verdict({"locator": "i-1", "role": "tool", "at_record": 5,
                     "facts": {"invocation_path": {"value": "bin/w", "at_record": 4}, "invocation_sha256": {"value": OTHER, "at_record": 4}, "applied_path": {"value": "bin/w", "at_record": 4}, "applied_sha256": {"value": APPLIED, "at_record": 4}}})["verdict"],
            NOT_EXPOSED)
    control("exposure shown makes the occasion eligible", verdict(occasion())["verdict"], ELIGIBLE)
    # Round 2: the table's predicate is EXECUTED. With `shown_when` set to a constant, the answer
    # has to follow the table — and before this it did not move at all, because the branch keyed on
    # the row's id decided and the field was prose beside it.
    control("a row's shown_when set to False makes a shown occasion not_exposed: the table decides",
            with_table(lambda held: row_of(held, "create_or_edit").__setitem__("shown_when", "False"),
                       lambda: verdict(occasion())["verdict"]),
            NOT_EXPOSED)
    control("and set to True it makes an unshown one eligible, so neither direction is the code's",
            with_table(lambda held: row_of(held, "create_or_edit").__setitem__("shown_when", "True"),
                       lambda: verdict(occasion(facts={"delivered_version": OTHER,
                                                       "applied_version": APPLIED}))["verdict"]),
            ELIGIBLE)
    control("a predicate outside the grammar is refused by name rather than evaluated",
            refusal(lambda: with_table(
                lambda held: row_of(held, "create_or_edit").__setitem__(
                    "shown_when", "__import__('os').system('x')"),
                lambda: verdict(occasion()))),
            "EXPOSURE_PREDICATE_UNREADABLE create_or_edit.shown_when")
    control("and an unparseable one too",
            str(with_table(lambda held: row_of(held, "create_or_edit").__setitem__("shown_when", "a =="),
                           table_problems)),
            "RULE_PREDICATE_UNREADABLE create_or_edit")
    # Round 2: incomplete evidence was CERTIFIED. Both shapes are the review's own.
    control("a merge carrying only an empty pin is unanswerable, not exposed: without the unit that "
            "was removed, 'the pin does not hold it' is true of every pin",
            verdict({"locator": "m-2", "operation": "merge", "at_record": 5,
                     "facts": {"pin_units": {"value": [], "at_record": 4}}})["verdict"], UNKNOWN)
    control("and it names both identities it lacks",
            verdict({"locator": "m-2", "operation": "merge", "at_record": 5,
                     "facts": {"pin_units": {"value": [], "at_record": 4}}})["why"], "removed_unit, merged_unit")
    control("while a plain DELETE needs only the removed unit, since no merge was asked for",
            verdict({"locator": "d-2", "operation": "delete", "at_record": 5,
                     "facts": {"pin_units": {"value": [], "at_record": 4}, "removed_unit": {"value": "u-gone", "at_record": 4}}})["verdict"], ELIGIBLE)
    control("a deleted wrapper carrying only its own resolution is unanswerable: 'neither the "
            "removed artifact nor an older carrier' needs both of those digests",
            verdict({"locator": "x-2", "operation": "delete", "role": "wrapper", "at_record": 5,
                     "facts": {"resolved_path": {"value": "bin/w", "at_record": 4}, "resolved_sha256": {"value": APPLIED, "at_record": 4}}})["verdict"],
            UNKNOWN)
    control("and names them",
            verdict({"locator": "x-2", "operation": "delete", "role": "wrapper", "at_record": 5,
                     "facts": {"resolved_path": {"value": "bin/w", "at_record": 4}, "resolved_sha256": {"value": APPLIED, "at_record": 4}}})["why"],
            "removed_sha256, fallback_sha256")
    control("an operation-conditional requirement must belong to a row that claims the operation",
            str(with_table(
                lambda held: row_of(held, "delete_or_merge").__setitem__(
                    "requires_by_operation", {"route": ["removed_unit"]}),
                table_problems)),
            "RULE_OPERATION_UNCLAIMED delete_or_merge")
    control("a fact a predicate reads and the row declares nowhere is a table defect",
            str(with_table(lambda held: row_of(held, "create_or_edit").__setitem__(
                "shown_when", "delivered_version == applied_version and vouched is True"),
                table_problems)),
            "RULE_FACT_UNDECLARED create_or_edit.shown_when")
    control("exposure shown ABSENT makes it not_exposed, which is an answer",
            verdict(occasion(facts={"delivered_version": OTHER,
                                    "applied_version": APPLIED}))["verdict"], NOT_EXPOSED)
    control("a required fact absent makes it exposure_unknown, never not_exposed: an absent fact is "
            "not a negative answer",
            verdict(occasion(facts={"applied_version": APPLIED}))["verdict"], UNKNOWN)
    control("and the why names the fact that was missing",
            verdict(occasion(facts={"applied_version": APPLIED}))["why"],
            "EXPOSURE_FACT_ABSENT delivered_version")

    # ---- §11's ordering rule ---------------------------------------------------------------------
    control("a fact observed AFTER the decision is not exposure to it",
            verdict(occasion(facts={"delivered_version": {"value": APPLIED, "at_record": 20},
                                    "applied_version": APPLIED}))["verdict"], UNKNOWN)
    control("and the refusal names the two positions",
            verdict(occasion(facts={"delivered_version": {"value": APPLIED, "at_record": 20},
                                    "applied_version": APPLIED}))["why"],
            "observed at record 20 and the decision is at 10")
    control("a fact observed AT the decision is not before it either",
            verdict(occasion(facts={"delivered_version": {"value": APPLIED, "at_record": 10},
                                    "applied_version": APPLIED}))["verdict"], UNKNOWN)
    control("one observed before it is read",
            verdict(occasion(facts={"delivered_version": {"value": APPLIED, "at_record": 9},
                                    "applied_version": APPLIED}))["verdict"], ELIGIBLE)
    control("an occasion with no position at all is unknown: 'before the decision' has nothing to "
            "be before", verdict(occasion(at_record=None))["verdict"], UNKNOWN)

    # ---- the O9 cases the plan names -------------------------------------------------------------
    def said(occasion, field="verdict"):
        """One occasion's answer, or the exception as text: a rule that vanished from the table made
        `verdict` raise straight through the control that needed to report it."""
        try:
            return verdict(occasion)[field]
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return f"RAISED {type(exc).__name__}: {exc}"

    control("O9: an installer change whose receipt names ANOTHER installer version is "
            "exposure_unknown, not not_exposed — §11 calls a transaction finished by another "
            "version unknown, and the condition said so only for the recovery field",
            said({"locator": "o9-a", "role": "installer", "at_record": 5,
                     "facts": {"installer_digest": {"value": OTHER, "at_record": 4}, "applied_sha256": {"value": APPLIED, "at_record": 4}, "begun_by_installer_digest": {"value": None, "at_record": 4}}}), UNKNOWN)
    control("O9: a recovery BEGUN by the old installer is exposure_unknown, not not_exposed — §11 "
            "writes that case into the branch itself",
            said({"locator": "o9-b", "role": "installer", "at_record": 5,
                     "facts": {"installer_digest": {"value": APPLIED, "at_record": 4}, "applied_sha256": {"value": APPLIED, "at_record": 4}, "begun_by_installer_digest": {"value": OTHER, "at_record": 4}}}), UNKNOWN)
    control("and the why says why nobody knows",
            said({"locator": "o9-b", "role": "installer", "at_record": 5,
                     "facts": {"installer_digest": {"value": APPLIED, "at_record": 4}, "applied_sha256": {"value": APPLIED, "at_record": 4}, "begun_by_installer_digest": {"value": OTHER, "at_record": 4}}}, "why"),
            "finished by another version")
    control("a table whose unknown condition this module does not read is refused, so the field "
            "cannot sit there with no reader",
            "; ".join(with_table(
                lambda t: t["rules"].append({"id": "unread", "applies_to": {"operation": ["x"]},
                                             "requires": ["a"], "shown_when": "a",
                                             "unknown_when": "never", "design": "d",
                                             "$comment": "planted"}),
                table_problems)),
            "RULE_UNKNOWN_UNREAD unread")
    control("O9: a pre-receipt transaction, with no installer digest at all, is exposure_unknown",
            said({"locator": "o9-c", "role": "installer", "at_record": 5,
                     "facts": {"applied_sha256": {"value": APPLIED, "at_record": 4}}}), UNKNOWN)
    control("O9: a removed wrapper resolving to an OLDER carrier is shown not exposed",
            said({"locator": "o9-d", "operation": "delete", "role": "wrapper", "at_record": 5,
                     "facts": {"resolved_path": {"value": "bin/old", "at_record": 4}, "resolved_sha256": {"value": "fa" + "l" * 62, "at_record": 4}, "removed_sha256": {"value": OTHER, "at_record": 4}, "fallback_sha256": {"value": "fa" + "l" * 62, "at_record": 4}, "required_replacement": {"value": APPLIED, "at_record": 4}}}), NOT_EXPOSED)
    control("O9: one with no resolution recorded is exposure_unknown",
            said({"locator": "o9-e", "operation": "delete", "role": "wrapper", "at_record": 5,
                     "facts": {"removed_sha256": {"value": OTHER, "at_record": 4}}}), UNKNOWN)
    control("O9: a compiler change with the OLD compiler digest is shown not exposed",
            said({"locator": "o9-f", "role": "catalog_compiler", "at_record": 5,
                     "facts": {"compiler_digest": {"value": OTHER, "at_record": 4}, "applied_sha256": {"value": APPLIED, "at_record": 4}}}),
            NOT_EXPOSED)
    control("O9: a personal change with no loading record is exposure_unknown",
            said({"locator": "o9-g", "operation": "personal", "at_record": 5,
                     "facts": {"layer_sha256": {"value": APPLIED, "at_record": 4}, "applied_sha256": {"value": APPLIED, "at_record": 4}}}),
            UNKNOWN)

    # ---- a fact the answer rests on says where it was observed --------------------------------
    #
    # `ordering_problems` skipped any fact without an `at_record`, so an occasion could be certified
    # ELIGIBLE with no evidence at all that its facts precede the decision: the rule had nothing to
    # read (the round-3 review). A fact the answering rule does not require is not part of the
    # answer and is not held to it.
    control("an occasion whose required fact records no position is exposure_unknown, not eligible",
            said({"locator": "p-1", "operation": "create", "at_record": 10,
                  "facts": {"delivered_version": APPLIED,
                            "applied_version": {"value": APPLIED, "at_record": 5}}}), UNKNOWN)
    control("and the why names the fact and says what cannot be shown",
            said({"locator": "p-1", "operation": "create", "at_record": 10,
                  "facts": {"delivered_version": APPLIED,
                            "applied_version": {"value": APPLIED, "at_record": 5}}}, "why"),
            "FACT_UNPOSITIONED p-1 delivered_version")
    control("the same occasion with both facts positioned before the decision is eligible, so the "
            "refusal is the missing position and not the fact",
            said(occasion(locator="p-2")), ELIGIBLE)
    # Round 4: optionality is about EXISTENCE, not timing. An optional fact the predicate READS
    # decides the answer when it is supplied — giving `required_replacement` with no position turned
    # exposure_unknown into eligible, so leaving it out of the position rule was a way past it.
    held_optional = {"locator": "p-4", "operation": "delete", "role": "hook", "at_record": 10,
                     "facts": {"resolved_path": {"value": "/a", "at_record": 5},
                               "resolved_sha256": {"value": "s", "at_record": 5},
                               "required_replacement": "new"}}
    # The WHY, not the verdict: this occasion is exposure_unknown either way — without the fix
    # because its required facts are absent — so a control reading only the verdict passed for the
    # wrong reason, which the revert trial reported as silent.
    control("an OPTIONAL fact the predicate reads must carry a position too, and the refusal is "
            "THAT fact's missing position rather than anything else about the occasion",
            said(held_optional, "why"), "FACT_UNPOSITIONED p-4 required_replacement")
    control("and the verdict it produces is exposure_unknown, never eligible",
            said(held_optional), UNKNOWN)
    clean("the same fact positioned before the decision is no longer an unpositioned-fact "
          "refusal, so what the rule caught was the missing position and not the fact",
          [held for held in [said({**held_optional, "locator": "p-5",
                                   "facts": {**held_optional["facts"],
                                             "required_replacement": {"value": "new",
                                                                      "at_record": 5}}}, "why")]
           if "FACT_UNPOSITIONED" in str(held)])
    control("and positioned AFTER it is refused by the ordering rule, which is the half that was "
            "already working",
            said({**held_optional, "locator": "p-6",
                  "facts": {**held_optional["facts"],
                            "required_replacement": {"value": "new", "at_record": 11}}}, "why"),
            "FACT_AFTER_DECISION")
    equals("the names held to the rule are the required ones plus the supplied ones the predicate "
            "reads, derived from the predicate's own source rather than listed twice",
            json.dumps(positioned_facts(
                next(row for row in table()["rules"] if row["id"] == "executable_deleted"),
                held_optional)),
            json.dumps(sorted(set(required_facts(
                next(row for row in table()["rules"] if row["id"] == "executable_deleted"),
                held_optional)) | {"required_replacement"})))
    clean("while a fact the predicate does not read at all is still not held to it, however it is "
          "supplied",
          [name for name in positioned_facts(
              next(row for row in table()["rules"] if row["id"] == "executable_deleted"),
              {**held_optional, "facts": {**held_optional["facts"], "a_note": "x"}})
           if name == "a_note"])
    clean("a fact the rule does NOT require may be unpositioned: it is not part of the answer",
          [said({"locator": "p-3", "operation": "create", "at_record": 10,
                 "facts": {"delivered_version": {"value": APPLIED, "at_record": 5},
                           "applied_version": {"value": APPLIED, "at_record": 5},
                           "a_note_nobody_requires": "x"}})] and
          [] if said({"locator": "p-3", "operation": "create", "at_record": 10,
                      "facts": {"delivered_version": {"value": APPLIED, "at_record": 5},
                                "applied_version": {"value": APPLIED, "at_record": 5},
                                "a_note_nobody_requires": "x"}}) == ELIGIBLE
          else ["an unrequired unpositioned fact changed the answer"])

    # ---- the installer branch answers eligible or unknown, never not_exposed -------------------
    control("a receipt whose digest is the applied one and whose recovery agrees is eligible",
            said({"locator": "i-1", "role": "installer", "at_record": 5,
                  "facts": {"installer_digest": {"value": APPLIED, "at_record": 4},
                            "applied_sha256": {"value": APPLIED, "at_record": 4},
                            "begun_by_installer_digest": {"value": None, "at_record": 4}}}),
            ELIGIBLE)
    control("an absent applied_sha256 is exposure_unknown: it was OPTIONAL while both conditions "
            "compare against it, so an absent one produced a negative answer from a fact nobody "
            "recorded",
            said({"locator": "i-2", "role": "installer", "at_record": 5,
                  "facts": {"installer_digest": {"value": APPLIED, "at_record": 4}}}), UNKNOWN)
    control("and the refusal names the absent fact rather than answering not_exposed",
            said({"locator": "i-2", "role": "installer", "at_record": 5,
                  "facts": {"installer_digest": {"value": APPLIED, "at_record": 4}}}, "why"),
            "EXPOSURE_FACT_ABSENT applied_sha256")
    control("the branch has no not_exposed state at all, which is what §11's sentence says: for an "
            "installer transaction nobody can know the installation was NOT exposed",
            json.dumps(sorted({said({"locator": f"i-{held}", "role": "installer", "at_record": 5,
                                     "facts": {"installer_digest": {"value": digest,
                                                                    "at_record": 4},
                                               "applied_sha256": {"value": APPLIED,
                                                                  "at_record": 4},
                                               "begun_by_installer_digest": {"value": begun,
                                                                             "at_record": 4}}})
                              for held, (digest, begun) in enumerate(
                                  [(APPLIED, None), (OTHER, None), (APPLIED, OTHER),
                                   (OTHER, OTHER)])})),
            '["eligible", "exposure_unknown"]')

    # ---- the generated fixtures ------------------------------------------------------------------
    clean("every generated case answers with the verdict its construction implies", fixture_problems())
    control("three cases per branch, generated from the table",
            f'{len(fixture_cases())}', f'{len(branches()) * 3}')
    control("a branch added to the table with no cases is refused rather than left untested",
            refusal(lambda: with_table(
                lambda t: t["rules"].append({"id": "newly_added", "applies_to": {"operation": ["x"]},
                                             "requires": ["a"], "shown_when": "a", "design": "d",
                                             "$comment": "planted"}),
                fixture_cases)),
            "FIXTURE_UNGENERATED newly_added")
    control("a branch the table names and this module does not answer is refused, so the predicate "
            "cannot be narrower than its table",
            refusal(lambda: _shown({"id": "newly_added"}, {})),
            "EXPOSURE_BRANCH_UNIMPLEMENTED")

    # ---- what measures receives ------------------------------------------------------------------
    built = instances_for("eo-1", [occasion(locator="a"),
                                   occasion(locator="b", facts={"delivered_version": OTHER,
                                                                "applied_version": APPLIED}),
                                   occasion(locator="c", facts={"applied_version": APPLIED})],
                          "source")
    control("a not_exposed occasion is excluded from the instances and counted",
            f'{len(built["instances"])}:{len(built["not_exposed"])}', "2:1")
    clean("and every instance carries one of the two exposure values measures admits",
          [row["exposure"] for row in built["instances"] if row["exposure"] not in measures.EXPOSURES])
    control("the excluded occasion is listed by locator and rule, so the exclusion is visible",
            json.dumps(built["not_exposed"]), '"locator": "b"')
    def resolved(*args):
        """`resolution_for` with any exception as a row: measures refuses an exposure value it does
        not admit, and a disabled exclusion raised straight through the suite."""
        try:
            return resolution_for(*args)
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return {"resolution": f"RAISED {type(exc).__name__}: {exc}", "counts": {"not_exposed": -1},
                    "not_exposed": []}

    held = resolved("eo-1", [occasion(locator="a", judged="observed"),
                                   occasion(locator="b", facts={"delivered_version": OTHER,
                                                                "applied_version": APPLIED})],
                          "source")
    control("the resolution comes from measures, not from a second implementation here",
            held["resolution"], "observed")
    control("with the not_exposed count beside it", str(held["counts"]["not_exposed"]), "1")
    clean("a window whose only occasion is not_exposed resolves as measures resolves an empty "
          "instance list, rather than as pending on an answered question",
          [] if resolved("eo-1", [occasion(locator="b",
                                            facts={"delivered_version": OTHER,
                                                   "applied_version": APPLIED})],
                         "source")["resolution"] == "no_occasion"
          else [resolved("eo-1", [occasion(locator="b",
                                           facts={"delivered_version": OTHER,
                                                  "applied_version": APPLIED})],
                         "source")["resolution"]])
    control("the resolution question goes to the module that owns it",
            next(line.strip() for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                 if "derive_resolution" in line and "held = " in line),
            "measures.derive_resolution")

    # ---- the branch set against §11 ---------------------------------------------------------------
    control("the predicate's branches are the table's, named for a reader checking them against §11",
            ", ".join(document()["branches"]), "create_or_edit, delete_or_merge, route")
    clean("and every branch carries the design clause it rests on",
          [name for name, clause in document()["design"].items() if not clause])

    import ast
    own = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    spawners = sorted({ast.unparse(node.func) for node in ast.walk(own) if isinstance(node, ast.Call)
                       and ast.unparse(node.func).split(".")[0] in ("subprocess", "os")})
    clean("exposure spawns nothing and reads no environment: the occasion's facts are handed to it",
          spawners)

    print(f"exposure --self-test: {'FAILED' if failures else 'OK'} ({len(ran)} controls: §11's eight "
          f"branches with three generated cases each, an absent fact read as unknown rather than as "
          f"a negative answer, the ordering rule at and after the decision, the seven O9 cases the "
          f"plan names, and the not_exposed occasions counted rather than handed to measures)")
    for name, detail in failures:
        print(f"exposure --self-test [FAIL] {name}: {detail}")
    return 1 if failures else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    print(json.dumps(document(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
