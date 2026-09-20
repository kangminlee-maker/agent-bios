"""Subject manifest and resolver tests. Run by gates/workenv/check-workenv.py, one process
per file."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import subjects  # noqa: E402

# P00 recorded this input and this fingerprint in run team-env-20260920b. They are literals
# because deriving the expectation from the rule under test would compare it to itself.
P00_BASELINE_INPUT = {"tree": "795b49b9cbd16078abfab9388e419ebe0d202203",
                      "manifest_sha256": "8dec8bf7d2f652afbedce9f55cdc3ca160f5a3ea68f24e5"
                                         "6e340a77ba94fa02a"}
P00_BASELINE_FINGERPRINT = "6f4029928e1170efa8ef19983ad2c323fc6d5e14adc2b6db7a87e3c4bcdb1104"

PLAN = {"subjects": {"one": {}, "two": {}},
        "nodes": [{"id": "N1", "depends_on": [], "owned_paths": ["src/one.py"]},
                  {"id": "N2", "depends_on": ["N1"], "owned_paths": ["src/two/"]},
                  {"id": "N3", "depends_on": ["N2"], "owned_paths": []}]}
NODES = {n["id"]: n for n in PLAN["nodes"]}
TRACKED = ["src/one.py", "src/two/a.py", "src/two/b.py", "other/three.py"]


class Rule(unittest.TestCase):
    def test_the_rule_reproduces_the_recorded_baseline_derivation(self):
        self.assertEqual(subjects.fingerprint(P00_BASELINE_INPUT), P00_BASELINE_FINGERPRINT)

    def test_the_manifest_that_carries_that_record_resolves_to_it(self):
        declared = subjects.manifests()
        self.assertEqual(declared["baseline"]["recorded"], P00_BASELINE_INPUT)
        self.assertEqual(subjects.resolve("baseline", declared=declared),
                         P00_BASELINE_FINGERPRINT)

    def test_key_order_in_the_identity_does_not_change_the_fingerprint(self):
        # Both orders, against each other: comparing one of them to the recorded value only
        # catches the order that happens to differ from sorted.
        reversed_keys = dict(reversed(list(P00_BASELINE_INPUT.items())))
        self.assertNotEqual(list(reversed_keys), list(P00_BASELINE_INPUT))
        self.assertEqual(subjects.fingerprint(reversed_keys),
                         subjects.fingerprint(P00_BASELINE_INPUT))


class Manifests(unittest.TestCase):
    def test_the_manifest_set_is_the_plans_subject_set(self):
        wanted = set(subjects.plan()["subjects"])
        self.assertTrue(wanted)
        self.assertEqual(set(subjects.manifests()), wanted)

    def test_every_manifest_states_an_identity_the_resolver_holds(self):
        held = {"path_closure", "recorded", "measured_elsewhere"}
        kinds = {name: manifest["identity"] for name, manifest in subjects.manifests().items()}
        self.assertTrue(kinds)
        self.assertEqual(set(kinds.values()) - held, set())

    def test_a_subject_nothing_here_measures_names_the_node_that_does(self):
        elsewhere = {name: manifest for name, manifest in subjects.manifests().items()
                     if manifest["identity"] == "measured_elsewhere"}
        self.assertTrue(elsewhere)
        for name, manifest in elsewhere.items():
            self.assertIn(manifest["measured_by"], {n["id"] for n in subjects.plan()["nodes"]},
                          name)
            self.assertIsNone(subjects.resolve(name))

    def test_the_real_check_passes_and_reports_every_subject(self):
        problems, report = subjects.check()
        self.assertEqual(problems, [])
        named = {line.split(": ", 1)[0] for line in report[1:]}
        self.assertEqual(named, set(subjects.manifests()))


class Closure(unittest.TestCase):
    """The closure rules, against a plan and a file list this test writes itself."""

    def prefixes(self, manifest, name="one", payload=None):
        return subjects.prefixes(name, manifest, NODES, payload)

    def test_a_node_the_manifest_includes_contributes_the_paths_the_plan_says_it_owns(self):
        found = self.prefixes({"declared": ["doc/x.md"], "include": {"owned_by": ["N1"]}})
        self.assertEqual(found, {"doc/x.md": "declared", "src/one.py": "N1"})

    def test_reaches_follows_depends_on_to_every_node_behind_it(self):
        self.assertEqual(subjects.reaches("N3", NODES), ["N1", "N2", "N3"])
        found = self.prefixes({"declared": [], "include": {"reaches": "N3"}})
        self.assertEqual(found, {"src/one.py": "N1", "src/two/": "N2"})

    def test_a_manifest_naming_a_node_the_plan_does_not_hold(self):
        for include in ({"owned_by": ["N9"]}, {"reaches": "N9"}):
            with self.assertRaises(subjects.SubjectError) as raised:
                self.prefixes({"declared": [], "include": include})
            self.assertIn("N9", str(raised.exception))

    def test_a_closure_that_names_nothing_at_all(self):
        with self.assertRaises(subjects.SubjectError) as raised:
            self.prefixes({"declared": [], "include": {"owned_by": ["N3"]}})
        self.assertIn("empty", str(raised.exception))

    def test_a_prefix_selects_the_tracked_paths_under_it(self):
        selected, unwritten = subjects.closure("one", {"src/two/": "N2"}, TRACKED)
        self.assertEqual(selected, ["src/two/a.py", "src/two/b.py"])
        self.assertEqual(unwritten, [])

    def test_a_prefix_the_manifest_declares_and_nothing_matches(self):
        with self.assertRaises(subjects.SubjectError) as raised:
            subjects.closure("one", {"src/gone.py": "declared"}, TRACKED)
        self.assertIn("src/gone.py", str(raised.exception))

    def test_a_prefix_a_node_owns_and_nobody_has_written_yet(self):
        selected, unwritten = subjects.closure("one", {"src/one.py": "N1", "src/later/": "N2"},
                                               TRACKED)
        self.assertEqual(selected, ["src/one.py"])
        self.assertEqual(unwritten, ["N2 has not written src/later/"])

    def test_a_subject_waiting_on_an_unwritten_path_resolves_to_unknown(self):
        manifest = {"identity": "path_closure", "declared": [],
                    "include": {"owned_by": ["N1", "N2"]}}
        built, why = subjects.state("one", manifest, pathlib.Path("/nowhere"), NODES,
                                    ["src/one.py"])
        self.assertIsNone(built)
        self.assertIn("N2 has not written src/two/", why)


class Fingerprints(unittest.TestCase):
    def identity(self, members):
        return {"subject": "one", "members": members}

    def test_two_runs_over_one_tree_give_one_fingerprint(self):
        first = subjects.resolve("contracts")
        self.assertIsNotNone(first)
        self.assertEqual(first, subjects.resolve("contracts"))

    def test_a_byte_inside_the_closure_moves_it(self):
        before = self.identity({"src/one.py": "a" * 64})
        after = self.identity({"src/one.py": "b" * 64})
        self.assertNotEqual(subjects.fingerprint(before), subjects.fingerprint(after))

    def test_a_byte_outside_the_closure_does_not_move_it(self):
        wanted = {"src/one.py": "N1"}
        first, _ = subjects.closure("one", wanted, TRACKED)
        wider, _ = subjects.closure("one", wanted, TRACKED + ["other/four.py"])
        self.assertEqual(first, wider)

    def test_an_absent_manifest_resolves_to_unknown_and_not_to_a_digest(self):
        self.assertIsNone(subjects.resolve("no-such-subject"))
        self.assertIsNone(subjects.resolve("contract"))

    def test_the_contracts_subject_holds_the_dispatch_and_every_schema(self):
        built, why = subjects.state("contracts", subjects.manifests()["contracts"])
        self.assertIsNotNone(built, why)
        held = set(built["members"])
        self.assertIn("workenv/contracts/records.py", held)
        self.assertIn("workenv/__init__.py", held)
        documents = {p for p in held if p.endswith(".schema.json")}
        on_disk = {f"workenv/contracts/schemas/{p.name}"
                   for p in (subjects.ROOT / "workenv/contracts/schemas").glob("*.schema.json")}
        self.assertEqual(documents, on_disk)


class Payload(unittest.TestCase):
    def test_the_payload_is_what_files_names_less_the_exceptions(self):
        manifest = subjects.manifests()["package"]
        excepted = manifest.get("except") or {}
        self.assertTrue(excepted)
        entries = subjects.payload_of(subjects.ROOT, "package.json", excepted)
        declared = json.loads((subjects.ROOT / "package.json").read_bytes())["files"]
        self.assertEqual(set(entries), {e.lstrip("./") for e in declared} - set(excepted))

    def test_an_exception_naming_a_path_the_payload_does_not(self):
        with self.assertRaises(subjects.SubjectError) as raised:
            subjects.payload_of(subjects.ROOT, "package.json", {"no-such-entry": "a reason"})
        self.assertIn("no-such-entry", str(raised.exception))

    def test_an_exception_for_a_path_that_is_in_the_tree_after_all(self):
        present = json.loads((subjects.ROOT / "package.json").read_bytes())["files"][0]
        with self.assertRaises(subjects.SubjectError) as raised:
            subjects.payload_of(subjects.ROOT, "package.json", {present.lstrip("./"): "stale"})
        self.assertIn("in the tree after all", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
