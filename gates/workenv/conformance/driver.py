"""The conformance driver: what every family case's command runs through.

The catalog spells 27 of its families' commands as `<conformance-driver> --case-profile <P>
--family <Nxx>`, and the registry names this file as that driver, so a family case cannot run
until it exists. It resolves what a profile runs in one family.

What a profile runs is what its binding holds: its own selection, its catalog cases, and every
case an implementation or package node its node depends on selects, which it runs again on the
tree as it stands (the re-run rule P01 freezes). `cases.case_map` is the one reader of that, so
the driver runs exactly the family's part of the binding — atomic cases included, which the
catalog files under the family — and no other set. Every case runs on the real tree: the driver
takes no option that would point it at another one, so a fixture double has no way into a run.
A stage extends files an earlier stage wrote, so a case is never held against an earlier
stage's accepted bytes; whether that stage is still current is the evaluator's question, answered
by the later stage's record.

`passed` still belongs to the node that implements the family, never to this module. What the
driver owns is the route to it. Every family in the catalog names the module that judges it
(`cases[].path`), and this is what reads that field: it imports the module, asks which case each
of its tests shows, runs that test, and reports `passed` or `failed` with the failure text. A
family whose module does not exist yet, or that names no test for a case, is `blocked` and says
which module and which case — so the report names the work that is owed rather than going quiet.

The module declares `CASES`, mapping a case id to the test that shows it, the way a contract
declares `RUNTIME_RULES` and `rules.py` holds the oracle for each name. Two rules keep the
mapping honest, and they are deliberately asymmetric:

  a case the module does not name   `blocked`. The registry defines the case and nobody has
                                    written its test yet, which is a state the plan expects.
  a name the registry does not have refused outright. The module claims to show a case of its
                                    family that does not exist, so the mapping is wrong rather
                                    than incomplete, and reporting per case would hide it.

A named test that runs no test at all is `failed`, not `passed`: naming a class that holds
nothing would otherwise report the case satisfied by an empty run. So is one that is skipped or
marked as an expected failure: unittest counts either as run, and neither shows its assertion
holding. A generator test, or a coroutine on a TestCase that does not await it, is `failed` for the
same reason: unittest records it as a success without running its body. And the driver refuses to
run at all under `python -O`, which strips every bare `assert` from a judging module.

The command exits 0 only when every case it runs passed, 1 when any failed or is blocked, and
2 when the run itself is refused. A family module that cannot be imported, or skips itself on
import, fails every case it would have judged, with the cause; it does not end the report.

  python3 gates/workenv/conformance/driver.py --case-profile V3 --family N27
"""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import cases  # noqa: E402

PASSED = "passed"
FAILED = "failed"
BLOCKED = "blocked"
REFUSED = "refused"


class DriverError(ValueError):
    """A run this module refuses, named."""


class ModuleFailed(Exception):
    """A family module that cannot be imported, so every case it would judge fails."""


def family_of(case: str) -> str:
    return case.split("-")[0]


def runnable(registry: dict, catalog: dict, profile: str) -> None:
    """A DriverError unless the profile is one whose binding is run: a catalog profile that is
    not carried. A `selects` row is not asked for, because a profile can hold catalog cases
    alone, as the runner qualification does."""
    if profile not in catalog["profiles"]:
        raise DriverError(f"{profile}: the catalog defines no such profile")
    if profile in {row["profile"] for row in registry["carried"]}:
        raise DriverError(f"{profile}: its binding is carried from its accepted record, so "
                          f"nothing here runs it")


def bound(registry: dict, profile: str, family: str,
          selected: tuple[dict, dict, object]) -> list[str]:
    """The profile's cases in the family: the family's part of its binding.

    `selected` is the bundle `CURRENT.md` selects, read where the registry is: the plan's nodes
    say which earlier stages a profile runs again, and the catalog holds the profile and which
    atomic cases a family files.
    """
    plan, catalog, _ = selected
    runnable(registry, catalog, profile)
    nodes = {node["id"]: node for node in plan["nodes"]}
    members = family_cases(registry, family, catalog)
    binding = cases.case_map(registry, catalog, profile, nodes)
    chosen = sorted(case for case in binding if case in members)
    if not chosen:
        commanded = sorted(case for case, of in binding.items() if of == family
                           and case in {row["id"] for row in registry["bootstrap"]})
        if commanded:
            raise DriverError(f"{profile}: its cases of {family} are bootstrap cases "
                              f"({', '.join(commanded)}), which run their own commands")
        raise DriverError(f"{profile}: it runs no case of {family}")
    return chosen


def family_cases(registry: dict, family: str, catalog: dict) -> set[str]:
    """Every case of the family the registry defines, across all profiles: its new cases, and the
    atomic ones the catalog files under it, which run through the family's command too."""
    atomic = {a["id"] for f in catalog["cases"] if f["id"] == family
              for a in f.get("atomic_cases", [])}
    return ({row["id"] for row in registry["cases"] if family_of(row["id"]) == family}
            | {row["id"] for row in registry["atomic"] if row["id"] in atomic})


def module_of(catalog: dict, family: str) -> str:
    """The module the catalog says judges this family. One reader, so one answer."""
    entry = next((row for row in catalog["cases"] if row["id"] == family), None)
    if entry is None:
        raise DriverError(f"{family}: the catalog defines no such family")
    declared = entry.get("path")
    if not declared:
        raise DriverError(f"{family}: the catalog names no module to judge it")
    return declared


def judge(registry: dict, catalog: dict, family: str,
          root: pathlib.Path) -> tuple[dict | None, str]:
    """(case -> the test that shows it, "") for the family's module, or (None, why not yet).

    The module is located by the catalog's own `path` for the family, so the field the bundle
    already carries is what decides where a family is judged, rather than a second list here
    that could disagree with it.
    """
    declared = module_of(catalog, family)
    path = root / declared
    if not path.is_file():
        return None, f"{family} is judged by {declared}, which does not exist yet"
    spec = importlib.util.spec_from_file_location(f"_family_{family}", path)
    if spec is None or spec.loader is None:
        raise DriverError(f"{family}: {declared} cannot be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    # Registered, so unittest finds the module to run its setUpModule and tearDownModule.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except unittest.SkipTest as skip:
        sys.modules.pop(spec.name, None)
        raise ModuleFailed(f"{declared} skips itself on import, so it shows nothing: "
                           f"{skip}") from skip
    except (Exception, SystemExit) as error:
        sys.modules.pop(spec.name, None)
        raise ModuleFailed(f"{declared} cannot be imported: {type(error).__name__}: "
                           f"{error}") from error
    named = getattr(module, "CASES", None)
    if not isinstance(named, dict) or not named:
        return None, f"{declared} names no case it shows"
    unknown = sorted(set(named) - family_cases(registry, family, catalog))
    if unknown:
        raise DriverError(f"{declared}: it names {', '.join(unknown)}, which the registry does "
                          f"not define as a case of {family}")
    return {case: (module, test) for case, test in named.items()}, ""


def shown(module: object, test: str) -> tuple[str, str]:
    """(outcome, detail) from running the one test a case names."""
    loader = unittest.defaultTestLoader
    try:
        suite = loader.loadTestsFromName(test, module)
    except Exception as error:  # a name the module does not hold is the module's defect
        return FAILED, f"{test} cannot be loaded: {error}"
    for case in tests_in(suite):
        why = unrunnable(case)
        if why:
            return FAILED, f"{test} {why}"
    result = unittest.TestResult()
    try:
        suite.run(result)
    except Exception as error:
        return FAILED, f"{test} raised outside its test body: {type(error).__name__}: {error}"
    problems = [text for _, text in result.failures + result.errors]
    if problems:
        return FAILED, stated_cause(problems[0])
    if result.skipped:
        return FAILED, f"{test} was skipped, so it shows nothing: {result.skipped[0][1]}"
    if result.testsRun == 0:
        return FAILED, f"{test} ran no test, so it shows nothing"
    if result.expectedFailures or result.unexpectedSuccesses:
        return FAILED, f"{test} is marked as an expected failure, so its run shows nothing"
    return PASSED, f"{result.testsRun} test(s) in {test}"


def tests_in(suite: unittest.TestSuite):
    """Every test in a suite, through any nesting."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from tests_in(item)
        else:
            yield item


def unrunnable(case: unittest.TestCase) -> str:
    """Why unittest would record this test as a success without running its body, or ""."""
    name = getattr(case, "_testMethodName", "")
    method = getattr(case, name, None)
    if method is None:
        return f"has no method {name} to run"
    if not (name.startswith(unittest.defaultTestLoader.testMethodPrefix) or name == "runTest"):
        return f"names {name}, which is not a test method, so running it shows nothing"
    if inspect.isgeneratorfunction(method) or inspect.isasyncgenfunction(method):
        return "is a generator, so unittest never runs its body"
    if (inspect.iscoroutinefunction(method)
            and not isinstance(case, unittest.IsolatedAsyncioTestCase)):
        return "is a coroutine its TestCase never awaits, so its body never runs"
    return ""


def stated_cause(traceback: str) -> str:
    """The line naming why it failed, not the last line of the text.

    unittest ends an `assertEqual` failure with the diff, so taking the last line reports `+ x`
    and loses the values that differed, and a list diff's element lines look like causes. The
    line wanted is the exception's own, the first unindented line after the traceback's last
    frame; without frames, the last line that is not part of a diff.
    """
    lines = traceback.strip().splitlines()
    frames = [index for index, line in enumerate(lines) if line.startswith("  File ")]
    if frames:
        # After the last frame and its indented source lines comes the exception's own line.
        for line in lines[frames[-1] + 1:]:
            if line.strip() and line[:1] not in (" ", "\t"):
                return line.strip()
    for line in reversed(lines):
        if line.strip() and line[:1] not in ("-", "+", "?", " ", "\t"):
            return line.strip()
    return "the test failed and stated no cause"


def run(profile: str, family: str, root: pathlib.Path = cases.ROOT,
        catalog: dict | None = None) -> dict:
    """What this profile runs of this family, and what each case shows.

    `root` is where the family's judging module is found; `catalog` is the bundle the families
    are read from, the one `CURRENT.md` selects when left out. What the profile runs is read from
    the registry and bundle where they are, never from `root`.
    """
    if sys.flags.optimize:
        raise DriverError("python runs with -O, which strips every bare assert from a judging "
                          "module, so a case could pass on an assertion that never ran")
    registry = cases.load()
    selected = cases.bundle(cases.ROOT)
    chosen = bound(registry, profile, family, selected)
    if catalog is None:
        catalog = selected[1] if root == cases.ROOT else cases.bundle(root)[1]
    try:
        tests, absent = judge(registry, catalog, family, root)
    except ModuleFailed as failure:
        return {"profile": profile, "family": family, "driver": registry["driver"],
                "cases": {case: {"outcome": FAILED, "why": str(failure)} for case in chosen}}
    outcomes = {}
    for case in chosen:
        if tests is None:
            outcomes[case] = {"outcome": BLOCKED, "why": absent}
            continue
        if case not in tests:
            outcomes[case] = {"outcome": BLOCKED,
                              "why": f"{module_of(catalog, family)} names no test for {case}"}
            continue
        module, test = tests[case]
        outcome, detail = shown(module, test)
        outcomes[case] = {"outcome": outcome, "test": test, "why": detail}
    return {"profile": profile, "family": family, "driver": registry["driver"], "cases": outcomes}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case-profile", required=True)
    parser.add_argument("--family", required=True)
    args = parser.parse_args(argv)
    try:
        report = run(args.case_profile, args.family)
    except DriverError as error:
        print(json.dumps({"outcome": REFUSED, "why": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return status(report)


def status(report: dict) -> int:
    """0 when every case the report holds passed, else 1: a blocked case has shown nothing."""
    outcomes = [case["outcome"] for case in report["cases"].values()]
    return 0 if outcomes and all(outcome == PASSED for outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
