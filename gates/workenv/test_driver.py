"""The conformance driver: what it resolves for a profile, and that it runs nowhere but the tree."""
from __future__ import annotations

import contextlib
import io
import pathlib
import shutil
import subprocess
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


FAMILY_MODULE = '''\
"""A family module standing in for a real one, written by the test that uses it."""
import unittest

SET_UP = []


def setUpModule():
    SET_UP.append("up")


class Shows(unittest.TestCase):
    def test_the_thing_holds(self):
        self.assertEqual({verdict}, "holds")

    def test_nothing(self):
        pass

    @unittest.skip("planted: the test is not written yet")
    def test_skipped(self):
        self.assertEqual({verdict}, "holds")

    @unittest.expectedFailure
    def test_expected_to_fail(self):
        self.assertEqual({verdict}, "broken")

    async def test_never_awaited(self):
        self.assertEqual({verdict}, "holds")

    @unittest.expectedFailure
    def test_expected_to_fail_but_holds(self):
        self.assertEqual({verdict}, "holds")

    def test_lists(self):
        self.assertEqual([1, 2], [1, {verdict}])

    def test_the_module_was_set_up(self):
        self.assertTrue(SET_UP)

    def check_helper(self):
        self.assertEqual({verdict}, "holds")

    def test_generator(self):
        yield
        self.assertEqual({verdict}, "holds")


def a_bare_case():
    """A callable the loader turns into a TestCase instance with no method to run."""
    return unittest.TestCase()


class BrokenSetUp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise RuntimeError("the class could not be set up")

    def test_anything(self):
        pass


class Awaited(unittest.IsolatedAsyncioTestCase):
    """A coroutine test on a TestCase that awaits it, which runs its body as any test does."""

    async def test_the_thing_holds(self):
        self.assertEqual({verdict}, "holds")


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

    def test_a_skipped_test_fails_the_case_rather_than_passing_it(self):
        # unittest counts a skipped test as run, so `testsRun` alone would report it passed.
        outcome, detail = self.outcome_of("Shows.test_skipped")
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("was skipped", detail)

    def test_a_test_marked_as_an_expected_failure_fails_the_case(self):
        outcome, detail = self.outcome_of("Shows.test_expected_to_fail")
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("expected failure", detail)

    def test_an_unexpected_success_fails_the_case(self):
        outcome, detail = self.outcome_of("Shows.test_expected_to_fail_but_holds")
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("expected failure", detail)

    def test_a_method_that_is_not_a_test_fails_the_case(self):
        outcome, detail = self.outcome_of("Shows.check_helper")
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("not a test method", detail)

    def test_a_name_that_loads_to_a_case_with_no_method_fails_that_case_alone(self):
        outcome, detail = self.outcome_of("a_bare_case")
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("runTest", detail)

    def test_a_class_that_cannot_be_set_up_fails_with_its_cause(self):
        outcome, detail = self.outcome_of("BrokenSetUp.test_anything")
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("the class could not be set up", detail)

    def test_a_list_difference_is_stated_by_the_exception_line(self):
        outcome, detail = self.outcome_of("Shows.test_lists")
        self.assertEqual(outcome, driver.FAILED)
        self.assertTrue(detail.startswith("AssertionError: Lists differ"), detail)

    def test_the_modules_own_set_up_runs_before_its_tests(self):
        self.assertEqual(self.outcome_of("Shows.test_the_module_was_set_up")[0], driver.PASSED)

    def test_a_generator_test_fails_the_case_because_its_body_never_runs(self):
        outcome, detail = self.outcome_of("Shows.test_generator", verdict='"broken"')
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("is a generator", detail)

    def test_a_coroutine_nothing_awaits_fails_the_case_because_its_body_never_runs(self):
        outcome, detail = self.outcome_of("Shows.test_never_awaited", verdict='"broken"')
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("never awaits", detail)

    def test_a_coroutine_its_testcase_awaits_is_judged_by_its_body(self):
        # The positive control for the two above: an awaited coroutine runs, so what it asserts
        # decides the case either way.
        self.assertEqual(self.outcome_of("Awaited.test_the_thing_holds")[0], driver.PASSED)
        outcome, detail = self.outcome_of("Awaited.test_the_thing_holds", verdict='"broken"')
        self.assertEqual(outcome, driver.FAILED)
        self.assertIn("broken", detail)

    def test_the_driver_refuses_to_run_with_assertions_stripped(self):
        case, family = inherited_family()
        ran = subprocess.run([sys.executable, "-O", "-B", str(HERE / "conformance" / "driver.py"),
                              "--case-profile", PROFILE, "--family", family],
                             capture_output=True, text=True)
        self.assertEqual(ran.returncode, 2, ran.stdout + ran.stderr)
        self.assertIn('"outcome": "refused"', ran.stdout)
        self.assertIn("-O", ran.stdout)

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

    def test_a_case_the_module_names_no_test_for_is_blocked_and_still_reported(self):
        profile = self.profile_of()
        chosen = driver.bound(self.registry, profile, self.FAMILY, cases.bundle(cases.ROOT))
        self.assertGreater(len(chosen), 1)
        self.write({chosen[0]: "Shows.test_the_thing_holds"})
        report = driver.run(profile, self.FAMILY, root=self.root, catalog=self.catalog())
        self.assertEqual(sorted(report["cases"]), chosen)
        self.assertEqual(report["cases"][chosen[0]]["outcome"], driver.PASSED)
        for case in chosen[1:]:
            self.assertEqual(report["cases"][case]["outcome"], driver.BLOCKED, case)
            self.assertIn(f"names no test for {case}", report["cases"][case]["why"])

    def test_a_module_that_cannot_be_imported_fails_every_case_and_still_reports(self):
        profile = self.profile_of()
        chosen = driver.bound(self.registry, profile, self.FAMILY, cases.bundle(cases.ROOT))
        for text, cause in (('raise RuntimeError("import broke")\n', "import broke"),
                            ('import unittest\nraise unittest.SkipTest("not here")\n',
                             "skips itself on import")):
            with self.subTest(cause=cause):
                (self.root / self.declared).write_text(text, encoding="utf-8")
                report = driver.run(profile, self.FAMILY, root=self.root, catalog=self.catalog())
                self.assertEqual(sorted(report["cases"]), chosen)
                for case, outcome in report["cases"].items():
                    self.assertEqual(outcome["outcome"], driver.FAILED, case)
                    self.assertIn(cause, outcome["why"], case)

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
