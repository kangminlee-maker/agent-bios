"""The conformance driver: what it resolves, and what it refuses for a joined case."""
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
import subjects  # noqa: E402

# One profile whose node has an implementation predecessor, and the family its joined case is
# of. Read from the registry rather than written down, so a registry edit moves the test with it.
PROFILE = "V3"


def joined_case() -> tuple[str, str, str]:
    """(the profile's joined case, its family, the node it runs against)."""
    row = driver.selection(cases.load(), PROFILE)
    entry = row["joined"][0]
    return entry["case"], driver.family_of(entry["case"]), entry["predecessor"]


def accepted_on(node: str, subject: str, fingerprint: str) -> dict:
    """Run evidence in which `node` was accepted on one subject."""
    return {"records": {node: {"subjects": {subject: fingerprint}}}}


class Resolution(unittest.TestCase):
    def setUp(self):
        self.case, self.family, self.node = joined_case()

    def test_it_resolves_the_profiles_cases_of_one_family(self):
        report = driver.run(PROFILE, self.family, None, None)
        self.assertIn(self.case, report["cases"])
        self.assertEqual(report["joined"], {self.case: self.node})
        self.assertEqual(report["driver"], cases.load()["driver"])
        for case in report["cases"]:
            self.assertEqual(driver.family_of(case), self.family)

    def test_nothing_is_passed_while_no_module_judges_the_family(self):
        # The driver resolves; the module the catalog names is what passes a case. A driver that
        # reported otherwise would report the rule satisfied by its own absence of work.
        #
        # The assertion names that module, because the earlier version of this test did not: it
        # required every outcome to be BLOCKED, which the driver satisfied by having no other
        # outcome at all. It would have gone on passing after a `passed` branch was added and
        # left unreachable, which is the shape of green this repo keeps paying for.
        _, catalog, _ = cases.bundle(cases.ROOT)
        declared = driver.module_of(catalog, self.family)
        self.assertFalse((cases.ROOT / declared).exists(),
                         f"{declared} now exists, so this test no longer stands on its absence")
        report = driver.run(PROFILE, self.family, None, None)
        self.assertTrue(report["cases"])
        for case, outcome in report["cases"].items():
            self.assertEqual(outcome["outcome"], driver.BLOCKED, case)
        # A joined case is stopped earlier, by its predecessor, and reports that instead. The
        # rest reach the module check, and the count is asserted so this does not go quiet if
        # every case of the family becomes joined.
        reached = [c for c in report["cases"] if c not in report["joined"]]
        self.assertTrue(reached, "every case is joined, so none reached the module check")
        for case in reached:
            self.assertIn(declared, report["cases"][case]["why"], case)

    def test_a_profile_the_registry_selects_nothing_for_is_refused(self):
        with self.assertRaises(driver.DriverError) as raised:
            driver.run("P99", self.family, None, None)
        self.assertIn("the registry selects no cases for it", str(raised.exception))

    def test_a_family_the_profile_runs_no_case_of_is_refused(self):
        with self.assertRaises(driver.DriverError) as raised:
            driver.run(PROFILE, "N99", None, None)
        self.assertIn("it runs no case of N99", str(raised.exception))


class Joined(unittest.TestCase):
    """The rule: a joined case runs against the predecessor's real accepted files."""

    def setUp(self):
        self.case, self.family, self.node = joined_case()
        self.subject = "contracts"
        identity, why = subjects.state(self.subject, subjects.manifests()[self.subject])
        self.assertIsNotNone(identity, why)
        self.members = identity["members"]
        self.assertTrue(self.members, "the subject this test stands on covers no file")
        self.fingerprint = subjects.fingerprint(identity)

    def run_against(self, accepted, subject_root=None):
        return driver.run(PROFILE, self.family, accepted, subject_root)

    def test_it_loads_the_predecessors_real_files_and_says_which(self):
        report = self.run_against(accepted_on(self.node, self.subject, self.fingerprint))
        self.assertEqual(report["loaded_files"][self.case], self.members)
        self.assertEqual(report["cases"][self.case]["loaded"], len(self.members))
        self.assertEqual(report["cases"][self.case]["joined_to"], self.node)

    def test_a_substituted_resolver_is_refused_outright(self):
        # This is the "a fixture double is unavailable to that process" clause. It refuses the
        # run rather than ignoring the flag: a flag that is ignored still reads as accepted.
        with self.assertRaises(driver.DriverError) as raised:
            self.run_against(accepted_on(self.node, self.subject, self.fingerprint),
                             subject_root=pathlib.Path("/nonexistent"))
        self.assertIn("--subject-root would resolve them somewhere else", str(raised.exception))

    def test_a_predecessor_with_no_accepted_record_blocks_rather_than_passes(self):
        report = self.run_against({"records": {}})
        self.assertEqual(report["loaded_files"], {})
        self.assertIn(f"{self.node}: the run evidence holds no accepted record",
                      report["cases"][self.case]["why"])

    def test_files_that_moved_since_the_record_was_accepted_block_the_case(self):
        report = self.run_against(accepted_on(self.node, self.subject, "f" * 64))
        self.assertEqual(report["loaded_files"], {})
        self.assertIn("and its record was accepted on " + "f" * 64,
                      report["cases"][self.case]["why"])

    def test_a_subject_no_manifest_declares_blocks_the_case(self):
        report = self.run_against(accepted_on(self.node, "not-a-subject", self.fingerprint))
        self.assertIn("which no manifest declares", report["cases"][self.case]["why"])

    def test_a_record_stating_no_subject_blocks_the_case(self):
        report = self.run_against({"records": {self.node: {"subjects": {}}}})
        self.assertIn("states no subject it was accepted on", report["cases"][self.case]["why"])


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
        self.real = sorted(driver.family_cases(self.registry, self.FAMILY))
        self.assertTrue(self.real, f"{self.FAMILY} defines no case to stand this test on")
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.declared = "family_under_test.py"

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
        return driver.run(self.profile_of(), self.FAMILY, None, None,
                          root=self.root, catalog=self.catalog())

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
