"""The conformance driver: what every family case's command runs through.

The catalog spells 27 of its families' commands as `<conformance-driver> --case-profile <P>
--family <Nxx>`, and the registry names this file as that driver, so a family case cannot run
until it exists. It resolves what a profile runs in one family and runs each case.

What a profile runs is what its binding holds: its own selection, its catalog cases, and every
case an implementation or package node its node depends on selects, which it runs again on the
tree as it stands (the re-run rule P01 freezes). `cases.case_map` is the one reader of that, so
the driver runs exactly the family's part of the binding — atomic cases included, which the
catalog files under the family — and no other set. Every case runs on the real tree: the driver
takes no option that would point it at another one, so a fixture double has no way into a run.
A stage extends files an earlier stage wrote, so a case is never held against an earlier
stage's accepted bytes; whether that stage is still current is the evaluator's question, answered
by the later stage's record.

A case is its frozen scenario, and `executor.py` runs it: each step is submitted to the entry
`conformance/serving.json` names for its operation when that node is in the profile's scope (the
profile's node and every node it depends on), through the layers in scope, and every other step
is given its stated answer. `passed` means every step was answered as stated; the first
difference is `failed` and names the step, the record and the pointer; a case whose code, or the
feature of the driver it needs, is not written yet is `blocked` and says which. So `passed`
belongs to the code that serves the case, and the report names the work that is owed rather than
going quiet.

The command exits 0 only when every case it runs passed, 1 when any failed or is blocked, and
2 when the run itself is refused.

  python3 gates/workenv/conformance/driver.py --case-profile V1 --family N27
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cases  # noqa: E402
import executor  # noqa: E402
import scenarios  # noqa: E402

PASSED = executor.PASSED
FAILED = executor.FAILED
BLOCKED = executor.BLOCKED
REFUSED = "refused"


class DriverError(ValueError):
    """A run this module refuses, named."""


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


def run(profile: str, family: str, root: pathlib.Path = cases.ROOT) -> dict:
    """What this profile runs of this family, and what each case shows.

    What the profile runs, and the scenarios and serving table it runs them by, are read from the
    registry and bundle where they are; `root` is where the code under test is imported from.
    """
    registry = cases.load()
    selected = cases.bundle(cases.ROOT)
    chosen = bound(registry, profile, family, selected)
    nodes = {node["id"]: node for node in selected[0]["nodes"]}
    node = next(node["id"] for node in selected[0]["nodes"] if node.get("test_profile") == profile)
    routing = executor.routing(cases.load_serving(), cases.scope(node, nodes))
    rows = {row["id"]: row for key in ("atomic", "cases") for row in registry[key]}
    outcomes = {}
    for case in chosen:
        path = cases.ROOT / cases.scenario_dir(case) / scenarios.GENERATED
        if not path.is_file():
            outcomes[case] = {"outcome": BLOCKED,
                              "why": f"{case} has no scenario at {cases.scenario_dir(case)}"}
            continue
        outcomes[case] = executor.run_case(json.loads(path.read_bytes()), routing,
                                           rules=tuple(rows[case].get("rules", ())), root=root)
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
