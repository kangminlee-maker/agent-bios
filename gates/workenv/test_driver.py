"""The conformance driver: what it resolves for a profile, and that it runs nowhere but the tree."""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "conformance"))
import cases  # noqa: E402
import driver  # noqa: E402

# A stage that runs an earlier stage's cases again, and a family it holds only from that stage.
# Read from the registry rather than written down, so a registry edit moves the test with it.
PROFILE = "V3"


def selected() -> tuple[dict, dict, object]:
    return cases.bundle(cases.ROOT)


def nodes_of(plan: dict) -> dict[str, dict]:
    return {node["id"]: node for node in plan["nodes"]}


NOTHING = "refused: it runs no case of the family"
COMMANDED = "refused: its cases of the family are bootstrap cases"


def disagreements(bundle: tuple[dict, dict, object]) -> tuple[list, list[tuple[str, str, bool]]]:
    """(each profile and family where the driver's answer differs from the binding's, every pair
    compared with whether a refusal was expected). Every open profile is asked about every
    catalog family: the binding's cases in it, or a refusal naming why it runs none. The
    binding's set is read from `case_map` alone, never through the driver, so a driver that
    drops or adds cases cannot move what it is held to as well. A bootstrap case runs its own
    command, not the driver's."""
    registry = cases.load()
    plan, catalog, _ = bundle
    nodes = nodes_of(plan)
    carried = {row["profile"] for row in registry["carried"]}
    commanded = {row["id"] for row in registry["bootstrap"]}
    found, pairs = [], []
    for name in sorted(set(catalog["profiles"]) - carried):
        full = cases.case_map(registry, catalog, name, nodes)
        for family in sorted(row["id"] for row in catalog["cases"]):
            want = sorted(c for c, f in full.items() if f == family and c not in commanded)
            if not want:
                want = (COMMANDED if any(f == family for c, f in full.items() if c in commanded)
                        else NOTHING)
            try:
                got = driver.bound(registry, name, family, bundle)
            except driver.DriverError as error:
                text = str(error)
                got = (NOTHING if f"it runs no case of {family}" in text
                       else COMMANDED if f"its cases of {family} are bootstrap cases" in text
                       else text)
            if got != want:
                found.append((name, family, got, want))
            pairs.append((name, family, want in (NOTHING, COMMANDED)))
    return found, pairs


def inherited_family() -> tuple[str, str]:
    """(a case PROFILE runs only because a stage before it selects it, that case's family)."""
    registry, (plan, catalog, _) = cases.load(), selected()
    own = next(row for row in registry["selects"] if row["profile"] == PROFILE)["cases"]
    bound = cases.case_map(registry, catalog, PROFILE, nodes_of(plan))
    case = next(c for c in sorted(bound) if c not in own
                and c in {row["id"] for row in registry["cases"]})
    return case, bound[case]


class Resolution(unittest.TestCase):
    def setUp(self):
        self.case, self.family = inherited_family()

    def test_it_runs_the_cases_an_earlier_stage_selected_again(self):
        report = driver.run(PROFILE, self.family)
        self.assertIn(self.case, report["cases"])
        self.assertEqual(report["driver"], cases.load()["driver"])

    def test_what_it_runs_is_the_familys_part_of_every_binding(self):
        # The one-reader property the registry rests on, asked of every open profile and
        # family, the runner qualification included: the driver runs exactly the cases the
        # binding files under the family, atomic ones included, and no other set.
        found, pairs = disagreements(selected())
        self.assertEqual(found, [])
        self.assertGreater(len([p for p in pairs if not p[2]]), 50,
                           "the comparison judged almost no bound family")
        self.assertTrue([p for p in pairs if p[2]],
                        "no family a profile binds nothing of was asked")
        self.assertIn(("R0", "N25", False), pairs)

    def test_a_driver_that_answers_for_a_family_it_binds_nothing_of_disagrees(self):
        # The control for the refusal half: a driver that hands back the family's cases where
        # the profile binds none of them must be caught at every such pair.
        real = driver.bound

        def generous(registry, profile, family, selected):
            try:
                return real(registry, profile, family, selected)
            except driver.DriverError:
                return sorted(driver.family_cases(registry, family, selected[1]))
        with mock.patch.object(driver, "bound", generous):
            found, _ = disagreements(selected())
        self.assertTrue(found)
        self.assertTrue(all(want in (NOTHING, COMMANDED) for *_, want in found), found[:3])
        self.assertIn("P01", {name for name, *_ in found})

    def test_a_driver_that_drops_atomic_cases_disagrees_with_the_binding(self):
        # The control for the comparison above: keep one atomic case of all of them, and the
        # binding, read without the driver, must show every profile that lost one.
        real = driver.family_cases

        def fewer(registry, family, catalog):
            atomic = {row["id"] for row in registry["atomic"]}
            return {c for c in real(registry, family, catalog)
                    if c not in atomic or c == min(atomic)}
        with mock.patch.object(driver, "family_cases", fewer):
            found, _ = disagreements(selected())
        self.assertIn("R0", {name for name, *_ in found})
        # a partial drop, not only a family left with nothing: the driver still answers with
        # cases, and fewer than the binding holds
        self.assertTrue([f for f in found if isinstance(f[2], list) and f[2]], found[:3])

    def test_an_atomic_case_runs_through_its_family(self):
        registry, bundle = cases.load(), selected()
        plan, catalog, _ = bundle
        bound = cases.case_map(registry, catalog, "V1", nodes_of(plan))
        atomic = {row["id"] for row in registry["atomic"]}
        family, case = next((f, c) for c, f in sorted(bound.items()) if c in atomic
                            and f != "N01" and f in {r["id"] for r in catalog["cases"]})
        self.assertIn(case, driver.bound(registry, "V1", family, bundle))

    def test_nothing_is_passed_while_the_code_that_serves_it_is_unwritten(self):
        # The driver resolves and runs; the code the serving table names is what passes a case.
        # A driver that reported otherwise would report the rule satisfied by its own absence of
        # work. Every V1 case passes through the journal layer, so while that module is absent
        # each case names it, or the driver feature it waits for.
        journal = "workenv/journal.py"
        self.assertFalse((cases.ROOT / journal).exists(),
                         f"{journal} now exists, so this test no longer stands on its absence")
        report = driver.run(PROFILE, self.family)
        self.assertTrue(report["cases"])
        for case, outcome in report["cases"].items():
            self.assertEqual(outcome["outcome"], driver.BLOCKED, case)
            self.assertTrue("module workenv.journal is not written yet" in outcome["why"]
                            or "no feature module" in outcome["why"], outcome)
        self.assertTrue(any("workenv.journal" in o["why"] for o in report["cases"].values()))

    def test_a_profile_the_catalog_does_not_define_is_refused(self):
        with self.assertRaises(driver.DriverError) as raised:
            driver.run("P99", self.family)
        self.assertIn("P99: the catalog defines no such profile", str(raised.exception))

    def test_a_carried_profile_is_refused_because_nothing_here_runs_it(self):
        carried = cases.load()["carried"][0]["profile"]
        with self.assertRaises(driver.DriverError) as raised:
            driver.run(carried, self.family)
        self.assertIn(f"{carried}: its binding is carried", str(raised.exception))

    def test_a_profile_holding_catalog_cases_alone_runs_them(self):
        # The runner qualification has no `selects` row: every case it binds is the catalog's.
        registry, bundle = cases.load(), selected()
        profile = bundle[1]["profiles"]["R0"]
        self.assertNotIn("R0", {row["profile"] for row in registry["selects"]})
        self.assertTrue(profile["required_atomic_case_ids"])
        self.assertEqual(driver.bound(registry, "R0", profile["family_ids"][0], bundle),
                         sorted(profile["required_atomic_case_ids"]))

    def test_the_report_holds_every_case_the_profile_runs(self):
        registry, bundle = cases.load(), selected()
        # V1's N27 and R0's N25 hold atomic cases, which a filter by family prefix would drop.
        for profile, family in ((PROFILE, self.family), ("V1", "N27"), ("R0", "N25")):
            with self.subTest(profile=profile):
                self.assertEqual(sorted(driver.run(profile, family)["cases"]),
                                 driver.bound(registry, profile, family, bundle))

    def test_a_family_bound_only_by_bootstrap_cases_is_refused_with_that_reason(self):
        with self.assertRaises(driver.DriverError) as raised:
            driver.run("P01", "N01")
        self.assertIn("P01: its cases of N01 are bootstrap cases", str(raised.exception))

    def test_the_command_exits_zero_only_when_every_case_passed(self):
        def report(*outcomes):
            return {"cases": {f"c{i}": {"outcome": o} for i, o in enumerate(outcomes)}}
        self.assertEqual(driver.status(report(driver.PASSED, driver.PASSED)), 0)
        for outcomes in ((driver.PASSED, driver.FAILED), (driver.BLOCKED,), ()):
            with self.subTest(outcomes=outcomes):
                self.assertEqual(driver.status(report(*outcomes)), 1)
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(driver.main(["--case-profile", PROFILE, "--family", self.family]), 1)
        self.assertIn(driver.BLOCKED, printed.getvalue())

    def test_a_family_the_profile_runs_no_case_of_is_refused(self):
        with self.assertRaises(driver.DriverError) as raised:
            driver.run(PROFILE, "N99")
        self.assertIn("it runs no case of N99", str(raised.exception))


class Rerun(unittest.TestCase):
    """The re-run rule: a case runs on the real tree, and nothing can point it at another."""

    def test_the_command_takes_no_option_that_substitutes_the_tree(self):
        # The two options the joined-case route had: another subject tree, and accepted run
        # evidence to hold predecessor bytes against. Each is now an unknown argument.
        case, family = inherited_family()
        for option in (["--subject-root", "/nonexistent"], ["--accepted", "/nonexistent"]):
            with self.assertRaises(SystemExit) as raised:
                driver.main(["--case-profile", PROFILE, "--family", family, *option])
            self.assertEqual(raised.exception.code, 2, option)


# The package every planted entry lives in: the real one's contracts stay reachable beneath it.
PACKAGE = f"""\
import pathlib
__path__.append({str(cases.ROOT / "workenv")!r})
"""
OWNED = f"""\
import sys
sys.path.insert(0, {str(HERE)!r})
import scripted_owner
"""


class EndToEnd(unittest.TestCase):
    """The only place `passed` reaches a report: the driver runs a case against code planted in
    a root of its own, the scripted owner answering at every entry V1 serves."""

    PROFILE, FAMILY, CASE = "V1", "N09", "N09-C07-POS"

    def setUp(self):
        registry, bundle = cases.load(), selected()
        self.assertEqual(driver.bound(registry, self.PROFILE, self.FAMILY, bundle), [self.CASE])
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.scenario = cases.ROOT / cases.scenario_dir(self.CASE) / "scenario.json"

    def plant(self, entry_source: str = "") -> None:
        serving = cases.load_serving()
        rows = [row for row in serving["operations"].values() if row.get("node") == "V1"]
        modules: dict[str, list[str]] = {}
        for row in rows:
            module, _, name = row["entry"].partition(":")
            modules.setdefault(module, []).append(
                entry_source.format(name=name) or f"{name} = scripted_owner.answer\n")
        modules.setdefault("workenv.journal", []).append(
            "def layer_journal(call, inner):\n    return inner(call)\n")
        modules.setdefault("workenv.storage", []).append(
            "def place_given(call):\n    pass\n")
        (self.root / "workenv").mkdir()
        (self.root / "workenv" / "__init__.py").write_text(PACKAGE, encoding="utf-8")
        for module, bodies in modules.items():
            path = self.root / (module.replace(".", "/") + ".py")
            path.write_text(OWNED + "".join(bodies), encoding="utf-8")

    def report(self, plants=()) -> dict:
        with mock.patch.dict(os.environ, {"SCRIPTED_SCENARIO": str(self.scenario),
                                          "SCRIPTED_PLANTS": json.dumps(list(plants))}):
            return driver.run(self.PROFILE, self.FAMILY, root=self.root)

    def test_a_case_answered_as_stated_reaches_the_report_as_passed(self):
        self.plant()
        report = self.report()
        self.assertEqual(report["cases"][self.CASE]["outcome"], driver.PASSED, report)
        self.assertEqual(driver.status(report), 0)

    def test_a_wrong_implementation_fails_the_case_by_name(self):
        # The control the plan asks for: plant a wrong answer and require the case to fall
        # naming where, not a silent blocked or a green report.
        self.plant()
        report = self.report([{"step": "compose_nothing", "path": "result",
                               "pointer": "/local_effect", "value": "none"}])
        outcome = report["cases"][self.CASE]
        self.assertEqual((outcome["outcome"], outcome["step"], outcome["pointer"]),
                         (driver.FAILED, "compose_nothing", "/local_effect"), outcome)
        self.assertEqual(driver.status(report), 1)

    def test_code_that_raises_fails_the_case_with_its_cause(self):
        self.plant("def {name}(call):\n    raise RuntimeError('broken entry')\n")
        outcome = self.report()["cases"][self.CASE]
        self.assertEqual(outcome["outcome"], driver.FAILED, outcome)
        self.assertIn("RuntimeError: broken entry", outcome["why"])


if __name__ == "__main__":
    unittest.main()
