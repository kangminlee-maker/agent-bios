#!/usr/bin/env python3
"""What a window's follow-up of one expected observation resolves to, derived by code (design §11).

S3 finds each occasion and judges it: its exposure (`eligible`, or `exposure_unknown` when the window cannot show the
exposure rule held before the decision or action) and its verdict (`observed` or `not_observed`), with evidence ids.
Code sets every instance's coverage basis over the window's scope (design §5.4) and derives the resolution here, in
§11's order:

- **not_observed**: at least one eligible occasion not observed, whatever else is incomplete;
- **observed**: at least one eligible occasion, every eligible occasion observed, no `exposure_unknown` occasion, and
  basis `source` or `view` (the basis is recorded with it: a view-based observed cannot rule out an unseen occasion
  that was not observed);
- **no_occasion**: basis `source` and no occasion found;
- **pending** otherwise (basis incomplete, basis view for an absence, or `exposure_unknown` occasions), carried to the
  next window.

The result is the ledger's resolution (`schemas/ledger.schema.json` `$defs.resolution`) without `run` and `window`,
which the stage that stores it adds (WP-21). An occasion shown not exposed (before the application, an old pin) is no
occasion of the applied item: the exposure predicate WP-21 builds excludes it before this derivation, so an instance
here is eligible or exposure_unknown and nothing else (plan amendment of 2026-11-03, row 6; WP-08 commit 4).

This module is pure: standard library only, no runlib import, no file read, no clock. Failures are named by their
first word: RESOLUTION_INPUT.

  measures.py --self-test
"""
import json
import pathlib
import sys

RESOLUTIONS = ("not_observed", "observed", "no_occasion", "pending")  # design §11, in its order
BASES = ("incomplete", "view", "source")                              # design §5.4
EXPOSURES = ("eligible", "exposure_unknown")                          # design §11
VERDICTS = ("observed", "not_observed")                               # design §11


class ResolutionInput(ValueError):
    pass


def counts_of(instances):
    """The ledger's counts: eligible occasions, their observed and not observed, and the exposure_unknown ones."""
    eligible = [i for i in instances if i["exposure"] == "eligible"]
    return {"eligible": len(eligible),
            "observed": sum(i["verdict"] == "observed" for i in eligible),
            "not_observed": sum(i["verdict"] == "not_observed" for i in eligible),
            "exposure_unknown": sum(i["exposure"] == "exposure_unknown" for i in instances)}


def input_problems(instances, basis):
    """Why `instances` and `basis` are not one expected observation's instances in one scope, as a list."""
    problems = []
    if basis not in BASES:
        problems.append(f"RESOLUTION_INPUT basis {basis!r} is none of {list(BASES)}")
    if len({i["expected_id"] for i in instances}) > 1:
        problems.append(f"RESOLUTION_INPUT instances of {sorted({i['expected_id'] for i in instances})}: a resolution "
                        "is derived for one expected observation")
    for n, i in enumerate(instances):
        if i["exposure"] not in EXPOSURES:
            problems.append(f"RESOLUTION_INPUT instance {n} exposure {i['exposure']!r} is none of {list(EXPOSURES)}")
        if i["verdict"] not in VERDICTS:
            problems.append(f"RESOLUTION_INPUT instance {n} verdict {i['verdict']!r} is none of {list(VERDICTS)}")
        if i["basis"] != basis:
            problems.append(f"RESOLUTION_INPUT instance {n} has basis {i['basis']!r}, and its scope's is {basis!r}: an "
                            "instance's basis is its scope's, set by code")
    locators = [i["occasion_locator"] for i in instances]
    if len(set(locators)) != len(locators):
        problems.append(f"RESOLUTION_INPUT occasions repeat: {sorted(o for o in set(locators) if locators.count(o) > 1)}")
    return problems


def derive_resolution(instances, basis):
    """`{resolution, basis, counts, occasions}` of one expected observation's `instances` in a scope of `basis`."""
    problems = input_problems(instances, basis)
    if problems:
        raise ResolutionInput("; ".join(problems))
    counts = counts_of(instances)
    if counts["not_observed"]:
        resolution = "not_observed"
    elif (counts["eligible"] and counts["observed"] == counts["eligible"] and not counts["exposure_unknown"]
          and basis in ("source", "view")):
        resolution = "observed"
    elif basis == "source" and not instances:
        resolution = "no_occasion"
    else:
        resolution = "pending"
    return {"resolution": resolution, "basis": basis, "counts": counts,
            "occasions": sorted(i["occasion_locator"] for i in instances)}


# ---------------------------------------------------------------- the O9 fixtures (design §15), as far as §11 derives

def fx_instance(n, exposure="eligible", verdict="observed", basis="source", expected="eo-1"):
    return {"expected_id": expected, "occasion_locator": f"view-a#{n}/message/content", "exposure": exposure,
            "verdict": verdict, "basis": basis, "evidence_ids": [f"ev-{n}"]}


def fx_scope(sessions=(), sources=None):
    """A scope for `views.coverage_basis`: one accounted source, and sessions given as (status, view, source, unprocessed)."""
    return {"sources": sources if sources is not None else [{"accounted": True, "directory_present": True}],
            "sessions": [{"status": s, "view_complete": v, "source_complete": c, "unprocessed": u} for s, v, c, u in sessions]}


DONE = ("read_complete", True, True, False)          # a session read to the end, every omission expanded
SKIPPED = ("read_complete", True, False, False)      # view complete with one skipped span


def o9_fixtures():
    """`[(name, scope, instances, expected resolution)]`: the O9 rows whose outcome §11's derivation decides. A row about
    exposure itself (an old installer on the receipt, a removed wrapper's carrier, a compiler digest, a loading record,
    a recovery begun by another installer, a pre-receipt transaction) is the predicate's, WP-21's; a row about reading
    (the search forcing an expansion, a skipped span's match) reaches this derivation as the instances and the basis
    reading left, and S3's self-test runs it through the reader."""
    def i(*args, **kwargs):
        return fx_instance(*args, **kwargs)
    source, view = fx_scope([DONE, DONE]), fx_scope([DONE, SKIPPED])
    return [
        ("O9 one observed, one not observed, one pre-application (excluded by exposure), one exposure_unknown: not "
         "observed wins", source, [i(1), i(2, verdict="not_observed"), i(4, exposure="exposure_unknown")], "not_observed"),
        ("O9 only observed and exposure_unknown occasions: pending", source,
         [i(1), i(2, exposure="exposure_unknown")], "pending"),
        ("O9 the only match lies in a skipped span: no occasion on basis view is pending", view, [], "pending"),
        ("O9 the paraphrased occasion the search misses behind an identical head and tail: no occasion refused, basis "
         "view, pending", view, [], "pending"),
        ("O9 observed occasions in a window with one skipped span: observed on basis view", view,
         [i(1, basis="view"), i(2, basis="view")], "observed"),
        ("O9 observed occasions in a window with a missing transcript: pending", fx_scope([DONE, ("known_absent", False,
         False, False)]), [i(1, basis="incomplete")], "pending"),
        ("O9 a request, then a guide read, then the correct action: exposed and observed", source, [i(1)], "observed"),
        ("O9 a source-complete window with no occasion: no occasion", source, [], "no_occasion"),
        ("O9 observed occasions in a window with a deferred session: pending", fx_scope([DONE, ("deferred", False, False,
         False)]), [i(1, basis="incomplete")], "pending"),
        ("O9 observed occasions in a window with a failed session: pending", fx_scope([DONE, ("failed", False, False,
         False)]), [i(1, basis="incomplete")], "pending"),
        ("O9 observed occasions in a window with a partially read session: pending", fx_scope([DONE, ("read_partial",
         True, False, False)]), [i(1, basis="incomplete")], "pending"),
        ("O9 an occasion whose exposure was not recorded: exposure_unknown leaves it pending", source,
         [i(1, exposure="exposure_unknown")], "pending"),
        ("F04 one source left unaccounted: an absence is pending", fx_scope([DONE], [{"accounted": True,
         "directory_present": True}, {"accounted": False, "directory_present": True}]), [], "pending"),
        ("F04 one source left unaccounted: an observed occasion is pending", fx_scope([DONE], [{"accounted": True,
         "directory_present": True}, {"accounted": False, "directory_present": True}]), [i(1, basis="incomplete")],
         "pending"),
        ("a not-observed occasion in an incomplete scope is still not observed", fx_scope([DONE, ("failed", False, False,
         False)]), [i(1, basis="incomplete"), i(2, verdict="not_observed", basis="incomplete")], "not_observed"),
        ("a not-observed occasion whose exposure is unknown is no eligible one: pending", source,
         [i(1, exposure="exposure_unknown", verdict="not_observed")], "pending"),
    ]


def fixture_problems(name, scope, instances, want, basis_of):
    """What is wrong with one fixture's derivation, naming the fixture."""
    basis = basis_of(scope)
    try:
        got = derive_resolution(instances, basis)
    except ResolutionInput as exc:
        return [f"{name}: {exc}"]
    return [] if got["resolution"] == want else [f"{name}: derived {got['resolution']!r} on basis {basis!r}, expected {want!r}"]


def self_test():
    failures = []
    here = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(here))
    from runlib import views  # the basis predicate the reader uses; the self-test reads it, the module does not

    fixtures = o9_fixtures()
    for name, scope, instances, want in fixtures:
        failures += fixture_problems(name, scope, instances, want, views.coverage_basis)
        for other in RESOLUTIONS:
            if other != want and not any(name in p for p in fixture_problems(name, scope, instances, other,
                                                                             views.coverage_basis)):
                failures.append(f"{name}: expecting {other!r} instead does not fail by the fixture's name")
    def derived(label, instances, basis):
        """The resolution, or None with the refusal named under `label`: a control that raises names itself."""
        try:
            return derive_resolution(instances, basis)
        except ResolutionInput as exc:
            failures.append(f"{label}: refused as {exc}")
            return None

    reached = {(derived(name, inst, views.coverage_basis(scope)) or {}).get("resolution")
               for name, scope, inst, _w in fixtures} - {None}  # a refused fixture is named above, not sorted here
    if reached != set(RESOLUTIONS):
        failures.append(f"the fixtures reach {sorted(reached)}, and §11 has {sorted(RESOLUTIONS)}: a branch is unexercised")

    # The rule over every vocabulary combination: each branch exactly where §11 puts it.
    for basis in BASES:
        for shape in ((), ("eligible", "observed"), ("eligible", "not_observed"), ("exposure_unknown", "observed")):
            inst = [fx_instance(1, *shape, basis=basis)] if shape else []
            got = (derived(f"one occasion {shape or 'none'} on basis {basis}", inst, basis) or {}).get("resolution")
            want = ("not_observed" if shape == ("eligible", "not_observed") else
                    "observed" if shape == ("eligible", "observed") and basis != "incomplete" else
                    "no_occasion" if not shape and basis == "source" else "pending")
            if got != want:
                failures.append(f"one occasion {shape or 'none'} on basis {basis}: derived {got!r}, expected {want!r}")

    # The result is the ledger's resolution without run and window, and the vocabularies are the schemas'.
    schemas = here / "schemas"
    ledger = json.loads((schemas / "ledger.schema.json").read_text(encoding="utf-8"))["$defs"]
    observation = json.loads((schemas / "observation.schema.json").read_text(encoding="utf-8"))["properties"]
    got = derived("the result's shape", [fx_instance(1)], "source") or {"counts": {}}
    if set(got) | {"run", "window"} != set(ledger["resolution"]["required"]):
        failures.append(f"the result's keys {sorted(got)} plus run and window are not the ledger resolution's "
                        f"{sorted(ledger['resolution']['required'])}")
    if set(got["counts"]) != set(ledger["counts"]["required"]):
        failures.append(f"the counts {sorted(got['counts'])} are not the ledger's {sorted(ledger['counts']['required'])}")
    for label, mine, theirs in (("resolution", RESOLUTIONS, ledger["resolution"]["properties"]["resolution"]["enum"]),
                                ("ledger basis", BASES, ledger["resolution"]["properties"]["basis"]["enum"]),
                                ("instance basis", BASES, observation["basis"]["enum"]),
                                ("exposure", EXPOSURES, observation["exposure"]["enum"]),
                                ("verdict", VERDICTS, observation["verdict"]["enum"])):
        if set(mine) != set(theirs):
            failures.append(f"the {label} vocabulary {sorted(mine)} is not the schema's {sorted(theirs)}")

    # Inputs that are not one expected observation's instances in one scope are refused by name.
    for label, instances, basis, needle in (
            ("a basis outside §5.4", [], "partial", "RESOLUTION_INPUT basis 'partial'"),
            ("two expected observations", [fx_instance(1), fx_instance(2, expected="eo-2")], "source", "a resolution is derived for one"),
            ("an instance of another scope's basis", [fx_instance(1, basis="view")], "source", "an instance's basis is its scope's"),
            ("a third exposure", [fx_instance(1, exposure="not_exposed")], "source", "exposure 'not_exposed'"),
            ("a third verdict", [fx_instance(1, verdict="unclear")], "source", "verdict 'unclear'"),
            ("one occasion twice", [fx_instance(1), fx_instance(1)], "source", "occasions repeat")):
        try:
            derive_resolution(instances, basis)
            failures.append(f"{label}: derived, and it should be refused")
        except ResolutionInput as exc:
            if needle not in str(exc):
                failures.append(f"{label}: refused as {exc}, expected {needle!r}")
    counted = derived("the counts", [fx_instance(1), fx_instance(2, verdict="not_observed"),
                                     fx_instance(3, exposure="exposure_unknown", verdict="not_observed")], "source") or {}
    if counted.get("counts") != {"eligible": 2, "observed": 1, "not_observed": 1, "exposure_unknown": 1} or \
            counted.get("occasions") != [f"view-a#{n}/message/content" for n in (1, 2, 3)]:
        failures.append(f"the counts and occasions keep every instance, the exposure_unknown one apart: {counted}")

    for failure in failures:
        print(f"measures --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"measures --self-test: OK ({len(fixtures)} O9 and F04 fixtures, each failing by name when its expected "
          "resolution is flipped; every branch of §11 reached; the result is the ledger's resolution; inputs that are "
          "not one observation in one scope refused)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: measures.py --self-test")
    sys.exit(self_test())
