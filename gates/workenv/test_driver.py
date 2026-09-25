"""The conformance driver: what it resolves for a profile, and that it runs nowhere but the tree."""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import unittest

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


def inherited_family() -> tuple[str, str]:
    """(a case PROFILE runs only because a stage before it selects it, that case's family)."""
    registry, (plan, catalog, _) = cases.load(), selected()
    own = next(row for row in registry["selects"] if row["profile"] == PROFILE)["cases"]
    bound = cases.case_map(registry, catalog, PROFILE, nodes_of(plan))
    # one whose family module is not written yet, so what the driver reports is its own work
    case = next(c for c in sorted(bound) if c not in own
                and c in {row["id"] for row in registry["cases"]}
                and not (cases.ROOT / driver.module_of(catalog, bound[c])).exists())
    return case, bound[case]


class Resolution(unittest.TestCase):
    def setUp(self):
        self.case, self.family = inherited_family()

    def test_it_runs_the_cases_an_earlier_stage_selected_again(self):
        report = driver.run(PROFILE, self.family)
        self.assertIn(self.case, report["cases"])
        self.assertEqual(report["driver"], cases.load()["driver"])

    def test_what_it_runs_is_the_familys_part_of_every_binding(self):
        # The one-reader property the registry rests on, asked of every profile and family:
        # the driver runs exactly the cases the binding files under the family, atomic ones
        # included, and no other set.
        registry, bundle = cases.load(), selected()
        plan, catalog, _ = bundle
        nodes, checked = nodes_of(plan), 0
        for name in sorted(row["profile"] for row in registry["selects"]):
            bound = cases.case_map(registry, catalog, name, nodes)
            for family in sorted(set(bound.values())):
                want = sorted(c for c, f in bound.items() if f == family
                              and c in driver.family_cases(registry, family, catalog))
                if not want:
                    continue
                self.assertEqual(driver.bound(registry, name, family, bundle), want, (name, family))
                checked += 1
        self.assertGreater(checked, 50, "the comparison judged almost nothing")

    def test_an_atomic_case_runs_through_its_family(self):
        registry, bundle = cases.load(), selected()
        plan, catalog, _ = bundle
        bound = cases.case_map(registry, catalog, "V1", nodes_of(plan))
        atomic = {row["id"] for row in registry["atomic"]}
        family, case = next((f, c) for c, f in sorted(bound.items()) if c in atomic
                            and f != "N01" and f in {r["id"] for r in catalog["cases"]})
        self.assertIn(case, driver.bound(registry, "V1", family, bundle))

    def test_nothing_is_passed_while_no_module_judges_the_family(self):
        # The driver resolves; the module the catalog names is what passes a case. A driver that
        # reported otherwise would report the rule satisfied by its own absence of work.
        #
        # The assertion names that module, because an earlier version of this test did not: it
        # required every outcome to be BLOCKED, which the driver satisfied by having no other
        # outcome at all.
        _, catalog, _ = selected()
        declared = driver.module_of(catalog, self.family)
        self.assertFalse((cases.ROOT / declared).exists(),
                         f"{declared} now exists, so this test no longer stands on its absence")
        report = driver.run(PROFILE, self.family)
        self.assertTrue(report["cases"])
        for case, outcome in report["cases"].items():
            self.assertEqual(outcome["outcome"], driver.BLOCKED, case)
            self.assertIn(declared, outcome["why"], case)

    def test_a_profile_the_registry_selects_nothing_for_is_refused(self):
        with self.assertRaises(driver.DriverError) as raised:
            driver.run("P99", self.family)
        self.assertIn("the registry selects no cases for it", str(raised.exception))

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


FAMILY_MODULE = '''\
"""A family module standing in for a real one, written by the test that uses it."""
import unittest


class Shows(unittest.TestCase):
    def test_the_thing_holds(self):
        self.assertEqual({verdict}, "holds")

    def test_nothing(self):
        pass


class Nothing(unittest.TestCase):
    """A TestCase the loader can load and that holds no test, so the suite runs nothing."""


class Empty:
    """A name that is not a test at all, so the loader cannot make a suite of it."""


CASES = {cases}
'''


class Judging(unittest.TestCase):
    """The route from a case to the module that judges it, and what each outcome means.

    The family module is written by the test into a temporary root, and the catalog handed to
    the driver points at it. Nothing is planted in the real tree, so a failure here cannot leave
    a stray `test_*.py` behind for the workenv gate to discover.
    """

    FAMILY = "N02"

    def setUp(self):
        self.registry = cases.load()
        self.declared = "family_under_test.py"
        self.real = sorted(driver.family_cases(self.registry, self.FAMILY, self.catalog()))
        self.assertTrue(self.real, f"{self.FAMILY} defines no case to stand this test on")
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)

    def catalog(self, path=None):
        """A catalog naming one family and where it is judged."""
        return {"cases": [{"id": self.FAMILY, "path": self.declared if path is None else path}]}

    def write(self, mapping, verdict='"holds"'):
        (self.root / self.declared).write_text(
            FAMILY_MODULE.format(cases=repr(mapping), verdict=verdict), encoding="utf-8")

    # ---- the module itself

    def test_a_module_the_catalog_names_but_nothing_wrote_blocks_and_says_which(self):
        found, why = driver.judge(self.registry, self.catalog(), self.FAMILY, self.root)
        self.assertIsNone(found)
        self.assertIn(self.declared, why)
        self.assertIn("does not exist yet", why)

    def test_a_module_naming_no_case_blocks_rather_than_passing_vacuously(self):
        self.write({})
        found, why = driver.judge(self.registry, self.catalog(), self.FAMILY, self.root)
        self.assertIsNone(found)
        self.assertIn("names no case it shows", why)

    def test_a_module_naming_a_case_the_registry_does_not_define_is_refused(self):
        # Asymmetric on purpose: a case with no test is work not done, but a test claiming a
        # case that does not exist is a mapping that is wrong, and per-case reporting hides it.
        self.write({f"{self.FAMILY}-INVENTED-POS": "Shows.test_the_thing_holds"})
        with self.assertRaises(driver.DriverError) as raised:
            driver.judge(self.registry, self.catalog(), self.FAMILY, self.root)
        self.assertIn(f"{self.FAMILY}-INVENTED-POS", str(raised.exception))
        self.assertIn("the registry does not define", str(raised.exception))

    def test_a_family_the_catalog_gives_no_module_is_refused(self):
        with self.assertRaises(driver.DriverError) as raised:
            driver.module_of(self.catalog(path=""), self.FAMILY)
        self.assertIn("names no module to judge it", str(raised.exception))

    def test_a_family_the_catalog_does_not_define_is_refused(self):
        with self.assertRaises(driver.DriverError) as raised:
            driver.module_of(self.catalog(), "N99")
        self.assertIn("the catalog defines no such family", str(raised.exception))

    # ---- what one named test yields

    def outcome_of(self, test, verdict='"holds"'):
        self.write({self.real[0]: test}, verdict=verdict)
        found, why = driver.judge(self.registry, self.catalog(), self.FAMILY, self.root)
        self.assertIsNotNone(found, why)
        module, named = found[self.real[0]]
        return driver.shown(module, named)

    def test_a_test_that_holds_passes_the_case(self):
        self.assertEqual(self.outcome_of("Shows.test_the_thing_holds")[0], driver.PASSED)

    def test_a_test_that_does_not_hold_fails_the_case_and_carries_its_text(self):
        outcome, detail = self.outcome_of("Shows.test_the_thing_holds", verdict='"broken"')
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("broken", detail)

    def test_a_loadable_name_holding_no_test_fails_rather_than_passing_on_an_empty_run(self):
        # This is what reaches the `testsRun == 0` branch: the loader builds a suite and the
        # suite runs nothing. Without it that branch would sit unreachable behind the loader.
        outcome, detail = self.outcome_of("Nothing")
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("ran no test", detail)

    def test_a_name_that_is_not_a_test_at_all_fails(self):
        outcome, detail = self.outcome_of("Empty")
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("cannot be loaded", detail)

    def test_a_name_the_module_does_not_hold_fails_and_says_what_is_missing(self):
        outcome, detail = self.outcome_of("Shows.test_absent")
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("test_absent", detail)

    # ---- end to end, which is the only place `passed` reaches a report

    def profile_of(self):
        """A profile the registry selects this family's cases for."""
        for row in self.registry["selects"]:
            if any(driver.family_of(case) == self.FAMILY for case in row["cases"]):
                return row["profile"]
        self.fail(f"no profile selects a case of {self.FAMILY}")

    def report(self, verdict='"holds"'):
        selected = [c for c in self.registry["selects"]
                    if c["profile"] == self.profile_of()][0]["cases"]
        mine = [c for c in selected if driver.family_of(c) == self.FAMILY]
        self.write({case: "Shows.test_the_thing_holds" for case in mine}, verdict=verdict)
        return driver.run(self.profile_of(), self.FAMILY, root=self.root, catalog=self.catalog())

    def test_a_judged_case_reaches_the_report_as_passed_with_the_test_that_showed_it(self):
        report = self.report()
        self.assertTrue(report["cases"])
        for case, outcome in report["cases"].items():
            self.assertEqual(outcome["outcome"], driver.PASSED, case)
            self.assertEqual(outcome["test"], "Shows.test_the_thing_holds")

    def test_a_wrong_implementation_fails_the_case_by_name(self):
        # The control the plan asks for: plant a wrong judgement and require the case to fall
        # with its own id, not a silent blocked or a green report.
        report = self.report(verdict='"wrong"')
        self.assertTrue(report["cases"])
        for case, outcome in report["cases"].items():
            self.assertEqual(outcome["outcome"], driver.FAILED, case)
            self.assertIn("wrong", outcome["why"], case)


if __name__ == "__main__":
    unittest.main()
