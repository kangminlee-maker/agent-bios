"""The conformance driver: what every family case's command runs through.

The catalog spells 27 of its families' commands as `<conformance-driver> --case-profile <P>
--family <Nxx>`, and the registry names this file as that driver, so a family case cannot run
until it exists. It resolves what a profile runs in one family, and it owns the joined-case
rule. What a profile runs is what its binding holds — its own selection, and every case an
earlier stage in its node's scope introduced, which a later stage runs again on the bytes that
exist then — and `cases.case_map` is the one reader of that, so the driver cannot run a set the
binding does not name.

A **joined case** is one an implementation profile runs against an accepted predecessor's real
files. The registry says which case joins to which node (`selects[].joined`); this module is
what makes the joining real, because a marker that nothing acts on would let a name satisfy the
rule. Three things follow from that, and each is a refusal rather than a convention:

  a substituted resolver   `--subject-root` points subject resolution at some other tree. It is
                           how a fixture double would reach a joined run, so a selection holding
                           a joined case refuses it outright. Nothing else in the run is allowed
                           to decide this: a flag that is merely ignored still reads as accepted.
  an unaccepted predecessor  without the accepted run evidence there is no manifest to hold the
                           files against, so every joined case is `blocked` and named. It is
                           never `passed`: at this point in the plan nothing is accepted, and a
                           driver that reported otherwise would report the rule satisfied by its
                           own absence of work.
  files that moved         the predecessor's subjects are re-measured from the real tree and
                           their fingerprints compared with the ones its record was accepted on.
                           A difference means the bytes are not the accepted ones, and the run
                           stops there rather than proving a hash against itself.

What it hands back for a joined case is the verified member map — every path the predecessor's
accepted subjects cover and the sha256 each was accepted with — so a case that later reads any
of them is reading something already held against the accepted manifest, and the driver's own
output states which files that was.

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
nothing would otherwise report the case satisfied by an empty run.

  python3 gates/workenv/conformance/driver.py --case-profile V3 --family N27
  python3 gates/workenv/conformance/driver.py --case-profile V3 --family N27 --accepted RUN
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import cases  # noqa: E402
import subjects  # noqa: E402

PASSED = "passed"
FAILED = "failed"
BLOCKED = "blocked"
REFUSED = "refused"


class DriverError(ValueError):
    """A run this module refuses, named."""


def family_of(case: str) -> str:
    return case.split("-")[0]


def selection(registry: dict, profile: str) -> dict:
    """The profile's `selects` row, or a DriverError naming what is missing."""
    rows = [row for row in registry["selects"] if row["profile"] == profile]
    if not rows:
        raise DriverError(f"{profile}: the registry selects no cases for it")
    return rows[0]


def bound(registry: dict, profile: str, family: str,
          selected: tuple[dict, dict, object]) -> tuple[list[str], dict[str, str]]:
    """(the profile's cases in the family, case -> the node each joined one runs against).

    `selected` is the bundle `CURRENT.md` selects, read where the registry is: the plan's nodes
    say which earlier stages a profile runs again, and the catalog holds the profile.
    """
    row = selection(registry, profile)
    plan, catalog, _ = selected
    nodes = {node["id"]: node for node in plan["nodes"]}
    defined = family_cases(registry, family)
    chosen = sorted(case for case in cases.case_map(registry, catalog, profile, nodes)
                    if case in defined)
    if not chosen:
        raise DriverError(f"{profile}: it runs no case of {family}")
    joined = {entry["case"]: entry["predecessor"] for entry in row.get("joined", [])
              if family_of(entry["case"]) == family}
    return chosen, joined


def accepted_subjects(record: dict, node: str) -> dict[str, str]:
    """The subject fingerprints the predecessor's record was accepted on."""
    stated = record.get("subjects")
    if not isinstance(stated, dict) or not stated:
        raise DriverError(f"{node}: its record states no subject it was accepted on")
    return stated


def predecessor_members(node: str, accepted: dict, root: pathlib.Path) -> dict[str, str]:
    """Every path the node's accepted subjects cover, by the sha256 it was accepted with.

    The fingerprints are re-measured from `root` and compared with the accepted ones, so a
    member map only comes back when the tree still holds the bytes the record was accepted on.
    """
    records = accepted.get("records") or {}
    if node not in records:
        raise DriverError(f"{node}: the run evidence holds no accepted record for it")
    declared = subjects.manifests()
    members: dict[str, str] = {}
    for name, stated in sorted(accepted_subjects(records[node], node).items()):
        if name not in declared:
            raise DriverError(f"{node}: it was accepted on subject {name}, which no manifest "
                              f"declares")
        identity, why = subjects.state(name, declared[name], root)
        if identity is None:
            raise DriverError(f"{node}: subject {name} measures nothing here: {why}")
        if subjects.fingerprint(identity) != stated:
            raise DriverError(f"{node}: subject {name} measures "
                              f"{subjects.fingerprint(identity)} and its record was accepted on "
                              f"{stated}")
        members.update(identity.get("members", {}))
    if not members:
        raise DriverError(f"{node}: its accepted subjects cover no file to run against")
    return members


def family_cases(registry: dict, family: str) -> set[str]:
    """Every case of the family the registry defines, across all profiles."""
    return {row["id"] for row in registry["cases"] if family_of(row["id"]) == family}


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
    spec.loader.exec_module(module)
    named = getattr(module, "CASES", None)
    if not isinstance(named, dict) or not named:
        return None, f"{declared} names no case it shows"
    unknown = sorted(set(named) - family_cases(registry, family))
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
    result = unittest.TestResult()
    suite.run(result)
    if result.testsRun == 0:
        return FAILED, f"{test} ran no test, so it shows nothing"
    problems = [text for _, text in result.failures + result.errors]
    if problems:
        return FAILED, stated_cause(problems[0])
    return PASSED, f"{result.testsRun} test(s) in {test}"


def stated_cause(traceback: str) -> str:
    """The line naming why it failed, not the last line of the text.

    unittest ends an `assertEqual` failure with the diff, so taking the last line reports `+ x`
    and loses the values that differed. The line wanted is the last one that is not part of that
    diff, which is where the exception states itself.
    """
    for line in reversed(traceback.strip().splitlines()):
        if line.strip() and line[:1] not in ("-", "+", "?", " ", "\t"):
            return line.strip()
    return "the test failed and stated no cause"


def run(profile: str, family: str, accepted: dict | None, subject_root: pathlib.Path | None,
        root: pathlib.Path = cases.ROOT, catalog: dict | None = None) -> dict:
    """What this profile runs of this family, what was held for it, and what each case shows.

    `catalog` is the bundle the families are read from; left out, it is the one `CURRENT.md`
    selects. A caller that already holds the bundle passes it rather than having it read again.
    """
    registry = cases.load()
    selected = cases.bundle(cases.ROOT)
    chosen, joined = bound(registry, profile, family, selected)
    if joined and subject_root is not None:
        raise DriverError(f"{profile}: {', '.join(sorted(joined))} run against an accepted "
                          f"predecessor's real files, and --subject-root would resolve them "
                          f"somewhere else")
    if catalog is None:
        catalog = selected[1] if root == cases.ROOT else cases.bundle(root)[1]
    tests, absent = judge(registry, catalog, family, root)
    outcomes, loaded = {}, {}
    for case in chosen:
        node = joined.get(case)
        held = {}
        if node is not None:
            # A joined case reaches its predecessor's files only after they are held against the
            # manifest its record was accepted on; nothing is judged before that succeeds.
            try:
                members = predecessor_members(node, accepted or {}, subject_root or root)
            except DriverError as error:
                outcomes[case] = {"outcome": BLOCKED, "joined_to": node, "why": str(error)}
                continue
            loaded[case] = members
            held = {"joined_to": node, "loaded": len(members)}
        if tests is None:
            outcomes[case] = {"outcome": BLOCKED, **held, "why": absent}
            continue
        if case not in tests:
            outcomes[case] = {"outcome": BLOCKED, **held,
                              "why": f"{module_of(catalog, family)} names no test for {case}"}
            continue
        module, test = tests[case]
        outcome, detail = shown(module, test)
        outcomes[case] = {"outcome": outcome, **held, "test": test, "why": detail}
    return {"profile": profile, "family": family, "driver": registry["driver"],
            "cases": outcomes, "joined": joined, "loaded_files": loaded}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case-profile", required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("--accepted", type=pathlib.Path,
                        help="run evidence holding the predecessors' accepted records")
    parser.add_argument("--subject-root", type=pathlib.Path,
                        help="resolve subjects from this tree; refused for a joined case")
    args = parser.parse_args(argv)
    evidence = json.loads(args.accepted.read_text()) if args.accepted else None
    try:
        report = run(args.case_profile, args.family, evidence, args.subject_root)
    except DriverError as error:
        print(json.dumps({"outcome": REFUSED, "why": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if all(c["outcome"] != REFUSED for c in report["cases"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
