"""The conformance driver: what it resolves, and what it refuses for a joined case."""
from __future__ import annotations

import pathlib
import sys
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
PROFILE = "P04"


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

    def test_nothing_is_passed_while_no_node_implements_the_family(self):
        # The driver resolves; the node that implements the family is what passes it. A driver
        # that reported otherwise would report the rule satisfied by its own absence of work.
        report = driver.run(PROFILE, self.family, None, None)
        self.assertTrue(report["cases"])
        for case, outcome in report["cases"].items():
            self.assertEqual(outcome["outcome"], driver.BLOCKED, case)

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


if __name__ == "__main__":
    unittest.main()
