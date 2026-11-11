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
        if not (row.get("applies_to") or {}).get("operation") and not (row.get("applies_to") or {}).get("role"):
            problems.append(f"RULE_APPLIES_TO_NOTHING {name}: a row answering for no operation and "
                            f"no role is never picked")
    return problems


def rule_for(occasion):
    """The one row that answers for this occasion, or None.

    A role is more specific than an operation: a DELETED executable is answered by
    `executable_deleted`, not by `delete_or_merge`, because §11 writes that branch separately. The
    table states it with both keys, and the longest `applies_to` wins — so the rule is the table's,
    not a precedence written here.
    """
    operation, role = occasion.get("operation"), occasion.get("role")
    best, best_keys = None, -1
    for row in rules():
        applies = row.get("applies_to") or {}
        wants_operation = applies.get("operation")
        wants_role = applies.get("role")
        if wants_operation and operation not in wants_operation:
            continue
        if wants_role and role not in wants_role:
            continue
        if not wants_operation and not wants_role:
            continue
        keys = bool(wants_operation) + bool(wants_role)
        if keys > best_keys:
            best, best_keys = row, keys
    return best


def ordering_problems(occasion):
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
            continue
        if held["at_record"] >= at:
            problems.append(f"FACT_AFTER_DECISION {occasion.get('locator')} {name}: observed at "
                            f"record {held['at_record']} and the decision is at {at}, so it is not "
                            f"exposure to it")
    return problems


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
    held = ordering_problems(occasion)
    if held:
        return {"verdict": UNKNOWN, "rule": row["id"], "why": "; ".join(held)}
    missing = [name for name in row["requires"] if _value(occasion, name) is None]
    if missing:
        return {"verdict": UNKNOWN, "rule": row["id"],
                "why": f"EXPOSURE_FACT_ABSENT {', '.join(missing)}: the branch cannot be shown "
                       f"either way, so the occasion is carried rather than answered"}
    # A row's `unknown_when` is read BEFORE its `shown_when`: §11 writes the unknown case into two
    # of its branches itself ("a transaction begun or finished by another installer version, or an
    # unbound one, is exposure_unknown"), and a condition like that answered as `not_exposed` would
    # say the item could not have fired where the design says nobody knows. The field had no reader
    # for one commit, which is the label-nobody-reads trap in its own right.
    if row.get("unknown_when"):
        unknown, why = _unknown(row, occasion)
        if unknown:
            return {"verdict": UNKNOWN, "rule": row["id"], "why": why}
    shown, why = _shown(row, occasion)
    return {"verdict": ELIGIBLE if shown else NOT_EXPOSED, "rule": row["id"], "why": why}


def _unknown(row, occasion):
    """Whether this row's own unknown condition holds, and why. One branch per rule that declares one."""
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
    """Whether this row's condition holds, and the sentence a reader needs. One branch per rule id."""
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
        for label, facts, want in (("shown", shown, ELIGIBLE), ("absent", absent, NOT_EXPOSED),
                                   ("unanswerable", unknown, UNKNOWN)):
            cases.append({"id": f"F-EXP-{name}-{label}", "rule": name, "expect": want,
                          "occasion": {"locator": f"{name}/{label}", "operation": operation,
                                       "role": role, "at_record": 10, "facts": facts}})
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
    failures, ran = [], []

    def control(name, got, want):
        ran.append(name)
        if want not in str(got):
            failures.append((name, f"expected {want!r} in {str(got)[:400]!r}"))

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

    # ---- the three verdicts ----------------------------------------------------------------------
    def occasion(**over):
        held = {"locator": "o-1", "operation": "create", "at_record": 10,
                "facts": {"delivered_version": APPLIED, "applied_version": APPLIED}}
        held.update(over)
        return held

    control("a merge whose merged unit the pin does NOT hold is not exposure, even though the "
            "removal succeeded: the branch has two halves and one generated negative covers only one",
            verdict({"locator": "m-1", "operation": "merge", "at_record": 5,
                     "facts": {"pin_units": ["u-kept"], "removed_unit": "u-gone",
                               "merged_unit": "u-merged"}})["verdict"], NOT_EXPOSED)
    control("and the why says which half failed",
            verdict({"locator": "m-1", "operation": "merge", "at_record": 5,
                     "facts": {"pin_units": ["u-kept"], "removed_unit": "u-gone",
                               "merged_unit": "u-merged"}})["why"],
            "does not hold the merged one")
    control("an invocation at the applied PATH but the old HASH is not exposure, for the same "
            "reason: §6.3's levels exist to catch exactly that",
            verdict({"locator": "i-1", "role": "tool", "at_record": 5,
                     "facts": {"invocation_path": "bin/w", "invocation_sha256": OTHER,
                               "applied_path": "bin/w", "applied_sha256": APPLIED}})["verdict"],
            NOT_EXPOSED)
    control("exposure shown makes the occasion eligible", verdict(occasion())["verdict"], ELIGIBLE)
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

    control("O9: an installer change with the OLD installer on the receipt is shown not exposed",
            said({"locator": "o9-a", "role": "installer", "at_record": 5,
                     "facts": {"installer_digest": OTHER, "applied_sha256": APPLIED,
                               "begun_by_installer_digest": None}}), NOT_EXPOSED)
    control("O9: a recovery BEGUN by the old installer is exposure_unknown, not not_exposed — §11 "
            "writes that case into the branch itself",
            said({"locator": "o9-b", "role": "installer", "at_record": 5,
                     "facts": {"installer_digest": APPLIED, "applied_sha256": APPLIED,
                               "begun_by_installer_digest": OTHER}}), UNKNOWN)
    control("and the why says why nobody knows",
            said({"locator": "o9-b", "role": "installer", "at_record": 5,
                     "facts": {"installer_digest": APPLIED, "applied_sha256": APPLIED,
                               "begun_by_installer_digest": OTHER}}, "why"),
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
                     "facts": {"applied_sha256": APPLIED}}), UNKNOWN)
    control("O9: a removed wrapper resolving to an OLDER carrier is shown not exposed",
            said({"locator": "o9-d", "operation": "delete", "role": "wrapper", "at_record": 5,
                     "facts": {"resolved_path": "bin/old", "resolved_sha256": "fa" + "l" * 62,
                               "removed_sha256": OTHER, "fallback_sha256": "fa" + "l" * 62,
                               "required_replacement": APPLIED}}), NOT_EXPOSED)
    control("O9: one with no resolution recorded is exposure_unknown",
            said({"locator": "o9-e", "operation": "delete", "role": "wrapper", "at_record": 5,
                     "facts": {"removed_sha256": OTHER}}), UNKNOWN)
    control("O9: a compiler change with the OLD compiler digest is shown not exposed",
            said({"locator": "o9-f", "role": "catalog_compiler", "at_record": 5,
                     "facts": {"compiler_digest": OTHER, "applied_sha256": APPLIED}}),
            NOT_EXPOSED)
    control("O9: a personal change with no loading record is exposure_unknown",
            said({"locator": "o9-g", "operation": "personal", "at_record": 5,
                     "facts": {"layer_sha256": APPLIED, "applied_sha256": APPLIED}}),
            UNKNOWN)

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
