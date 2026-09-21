"""Case registry and runtime-rule oracle tests. Run by gates/workenv/check-workenv.py, one process
per file."""
import copy
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "conformance"))
sys.path.insert(0, str(HERE.parents[1]))

import cases  # noqa: E402
import rules  # noqa: E402
from workenv.contracts import canonical, examples, records  # noqa: E402


class Registry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loaded = cases.bundle()
        cls.paths = cases.subjects.tracked()
        cls.registry = cases.load()

    def check(self, registry):
        return cases.check(registry, loaded=self.loaded, paths=self.paths)[0]

    def refused(self, fragment, mutate):
        registry = copy.deepcopy(self.registry)
        mutate(registry)
        problems = self.check(registry)
        self.assertTrue(any(fragment in p for p in problems), (fragment, problems))

    def row(self, registry, key, case):
        return next(r for r in registry[key] if r["id"] == case)

    def selection(self, registry, profile):
        return next(r for r in registry["selects"] if r["profile"] == profile)

    def test_the_registry_holds_and_reports_every_profile(self):
        problems, report = cases.check(self.registry, loaded=self.loaded, paths=self.paths)
        self.assertEqual(problems, [])
        self.assertEqual(set(report), set(self.loaded[1]["profiles"]))
        self.assertEqual(len(report), 25)

    def test_the_carried_binding_is_the_accepted_one_byte_for_byte(self):
        def edit(r):
            r["carried"][0]["cases"][0]["family"] = "B04"
        self.refused("no longer digests to the binding_digest", edit)

    def test_a_carried_profile_the_catalog_does_not_hold_is_refused(self):
        def edit(r):
            r["carried"].append(dict(copy.deepcopy(r["carried"][0]), profile="P99"))
        self.refused("carried P99: no such profile in the catalog", edit)

    def test_a_carried_binding_the_evaluator_refuses_is_refused(self):
        # A binding whose digest is restated to match still has to satisfy the evaluator.
        def edit(r):
            row = r["carried"][0]
            row["cases"] = [c for c in row["cases"] if c["family"] != "B01"]
            row["binding_digest"] = self.loaded[2].digest(cases.carried_binding(row))
        self.refused("carried P00: the evaluator refuses it: empty/incomplete bound case families",
                     edit)

    def test_a_catalog_bootstrap_case_nothing_runs_is_refused(self):
        self.refused("nothing runs it", lambda r: r["bootstrap"].pop())

    def test_a_bootstrap_case_no_open_profile_names_is_refused(self):
        def edit(r):
            r["bootstrap"].append({"id": "P02-contract-positive", "command": ["true"]})
        self.refused("bootstrap P02-contract-positive: no open profile's catalog entry", edit)

    def test_a_bootstrap_case_of_a_profile_with_many_families_is_refused(self):
        catalog = copy.deepcopy(self.loaded[1])
        catalog["profiles"]["P01"]["family_ids"] = ["N01", "N05"]
        problems = cases.check(self.registry, loaded=(self.loaded[0], catalog, self.loaded[2]),
                               paths=self.paths)[0]
        self.assertIn("bootstrap P01-contract-positive: P01 has more than one family to bind it to",
                      problems)

    def test_an_atomic_id_the_catalog_does_not_define_is_refused(self):
        def edit(r):
            r["atomic"].append(dict(copy.deepcopy(r["atomic"][0]), id="SRC-99"))
        self.refused("atomic SRC-99: the catalog defines no such case", edit)

    def test_a_contract_no_module_declares_is_refused(self):
        def edit(r):
            r["atomic"][0]["contracts"].append("C13")
        self.refused("contract C13 is no contract module's", edit)

    def test_a_family_the_catalog_does_not_hold_is_refused(self):
        def edit(r):
            r["cases"].append(dict(copy.deepcopy(r["cases"][0]), id="N99-C01-POS"))
            self.selection(r, "P03")["cases"].append("N99-C01-POS")
        self.refused("N99-C01-POS: family N99 is not in the catalog", edit)

    def test_a_selection_for_a_carried_or_unknown_profile_is_refused(self):
        for profile in ("P00", "P99"):
            with self.subTest(profile=profile):
                self.refused(f"selects {profile}: not a profile the registry binds",
                             lambda r, p=profile: r["selects"].append(
                                 {"profile": p, "cases": ["N02-C01-POS"]}))

    def test_an_atomic_case_the_registry_does_not_bind_is_refused(self):
        self.refused("the registry binds nothing", lambda r: r["atomic"].pop(0))

    def test_an_operation_outside_the_named_contracts_is_refused(self):
        def edit(r):
            r["atomic"][0]["operations"].append("team.found")
        self.refused("belongs to none of", edit)

    def test_a_fixture_nobody_tracks_is_refused(self):
        def edit(r):
            r["cases"][0]["fixtures"].append("gates/workenv/fixtures/absent.json")
        self.refused("matches no tracked file", edit)

    def test_an_oracle_the_family_does_not_hold_is_refused(self):
        def edit(r):
            r["cases"][0]["oracle"] = 9
        self.refused("has no oracle 9", edit)

    def test_a_rule_no_contract_declares_is_refused(self):
        def edit(r):
            self.row(r, "cases", "N07-PREFERENCE-NEG")["rule"] = "C05/nothing_declares_this"
        self.refused("declared by no contract module", edit)

    def test_a_declared_rule_no_case_checks_is_refused(self):
        def edit(r):
            del self.row(r, "cases", "N08-READER-GAP-NEG")["rule"]
        self.refused("rule C06/gap_named_frontier_not_returned: no case checks it", edit)

    def test_a_rule_checked_only_where_nobody_implements_it_is_refused(self):
        def edit(r):
            for row in r["selects"]:
                if row["profile"] in ("P05", "P17"):
                    row["cases"].remove("N07-STATE-GAP-NEG")
            self.selection(r, "M1")["cases"].append("N07-STATE-GAP-NEG")
        self.refused("is selected by no profile whose node implements C05", edit)

    def test_a_selection_outside_the_profiles_families_is_refused(self):
        self.refused("is outside its families",
                     lambda r: self.selection(r, "P02")["cases"].append("N05-CONTROL-POS"))

    def test_a_case_nobody_selects_is_refused(self):
        def edit(r):
            self.selection(r, "P18")["cases"].remove("N24-C03-NEG")
            self.selection(r, "M4")["cases"].remove("N24-C03-NEG")
        self.refused("N24-C03-NEG: defined and selected by no profile", edit)

    def test_a_selected_case_nobody_defines_is_refused(self):
        self.refused("is defined nowhere",
                     lambda r: self.selection(r, "P02")["cases"].append("N02-GHOST-POS"))

    def test_a_profile_selected_twice_is_refused(self):
        self.refused("stated twice", lambda r: r["selects"].append(copy.deepcopy(r["selects"][0])))

    def test_a_pair_without_a_negative_is_refused(self):
        self.refused("P18 N24: no negative case",
                     lambda r: self.selection(r, "P18")["cases"].remove("N24-C03-NEG"))

    def test_a_family_with_no_case_is_refused_by_the_dated_evaluator_too(self):
        registry = copy.deepcopy(self.registry)
        self.selection(registry, "P18")["cases"].clear()
        self.assertIn("P18: the evaluator refuses its case map: "
                      "empty/incomplete bound case families", self.check(registry))

    def test_an_operation_no_case_drives_is_refused(self):
        def edit(r):
            for row in r["atomic"] + r["cases"]:
                if "store.backup.create" in row["operations"]:
                    row["operations"].remove("store.backup.create")
        self.refused("operation store.backup.create: no case drives it", edit)

    def test_a_field_the_schema_does_not_define_is_refused_on_load(self):
        registry = copy.deepcopy(self.registry)
        registry["cases"][0]["evidence_class"] = "deterministic"
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "case-index.json"
            path.write_text(json.dumps(registry))
            with self.assertRaisesRegex(cases.CaseError,
                                        "unknown_field at /cases/0/evidence_class"):
                cases.load(path)

    def test_one_id_is_one_case_across_the_three_sets(self):
        registry = copy.deepcopy(self.registry)
        registry["cases"][0]["id"] = registry["cases"][1]["id"]
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "case-index.json"
            path.write_text(json.dumps(registry))
            with self.assertRaisesRegex(cases.CaseError, "duplicate_item"):
                cases.load(path)

    def test_polarity_is_read_from_the_id_and_an_atomic_case_holds_both(self):
        atomic = {"DC-SET"}
        self.assertEqual(cases.polarities("DC-SET", atomic), {cases.POSITIVE, cases.NEGATIVE})
        self.assertEqual(cases.polarities("N07-C05-POS", atomic), {cases.POSITIVE})
        self.assertEqual(cases.polarities("P01-contract-negative", atomic), {cases.NEGATIVE})
        self.assertEqual(cases.polarities("N07-C05", atomic), set())


class Bindings(unittest.TestCase):
    """The fingerprints move with what they name and nothing else. Measured on a copy of the
    tracked tree, so a mutation never touches the checkout."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.root = pathlib.Path(cls.folder.name)
        cls.paths = cases.subjects.tracked()
        for path in cls.paths:
            source = cases.ROOT / path
            if source.is_file():
                target = cls.root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
        cls.loaded = cases.bundle(cls.root)
        cls.registry = cases.load()
        cls.profiles = sorted(cls.loaded[1]["profiles"])
        cls.before = cls.bindings(cls.registry)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    @classmethod
    def bindings(cls, registry):
        return {p: cases.binding(registry, p, cls.loaded, cls.root, cls.paths)
                for p in cls.profiles}

    def moved(self, after, field):
        return {p for p in self.profiles if after[p][field] != self.before[p][field]}

    def readers_of(self, predicate):
        rows = {r["id"]: r for key in ("atomic", "cases") for r in self.registry[key]}
        return {p for p in self.profiles if p != "P00" and any(
            predicate(rows[c]) for c in self.before[p]["cases"] if c in rows)}

    def test_every_binding_is_one_the_dated_evaluator_accepts(self):
        atomic = {a["id"]: f["id"] for f in self.loaded[1]["cases"]
                  for a in f.get("atomic_cases", [])}
        self.assertEqual(len(self.before), 25)
        for profile, binding in self.before.items():
            with self.subTest(profile=profile):
                self.assertEqual(self.loaded[2].binding_errors(
                    self.loaded[1]["profiles"][profile], binding, atomic), [])

    def test_the_carried_binding_digests_to_what_its_record_states(self):
        row = self.registry["carried"][0]
        self.assertEqual(self.loaded[2].digest(self.before[row["profile"]]), row["binding_digest"])

    def test_a_fixtures_bytes_move_exactly_the_profiles_that_read_it(self):
        fixture = "workenv/contracts/examples/c09/verified.json"
        wanted = self.readers_of(lambda row: fixture in row["fixtures"]
                                 or any(f.endswith("/") and fixture.startswith(f)
                                        for f in row["fixtures"]))
        self.assertTrue(wanted and wanted != set(self.profiles) - {"P00"})
        original = (self.root / fixture).read_bytes()
        try:
            (self.root / fixture).write_bytes(original + b" ")
            after = self.bindings(self.registry)
        finally:
            (self.root / fixture).write_bytes(original)
        self.assertEqual(self.moved(after, "fixture_fingerprint"), wanted)
        self.assertEqual(self.moved(after, "adapter_fingerprint"), set())

    def test_a_contracts_bytes_move_exactly_the_profiles_that_drive_it(self):
        module = "workenv/contracts/c10.py"
        wanted = self.readers_of(lambda row: "C10" in row["contracts"])
        self.assertTrue(wanted and wanted != set(self.profiles) - {"P00"})
        original = (self.root / module).read_bytes()
        try:
            (self.root / module).write_bytes(original + b"\n")
            after = self.bindings(self.registry)
        finally:
            (self.root / module).write_bytes(original)
        self.assertEqual(self.moved(after, "adapter_fingerprint"), wanted)
        self.assertEqual(self.moved(after, "fixture_fingerprint"), set())

    def test_a_case_definition_moves_exactly_the_profiles_that_select_it(self):
        registry = copy.deepcopy(self.registry)
        row = next(r for r in registry["cases"] if r["id"] == "N24-C03-NEG")
        row["asserts"] += " Changed."
        after = self.bindings(registry)
        self.assertEqual(self.moved(after, "fixture_fingerprint"), {"P18", "M4"})
        self.assertEqual(self.moved(after, "adapter_fingerprint"), set())


class RuntimeRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = examples.load_schemas()
        cls.kinds = records.registry(cls.schemas)
        cls.fixtures = {}
        for path in sorted((HERE / "fixtures/rules").glob("*.json")):
            fixture = json.loads(path.read_text())
            cls.fixtures[fixture["rule"]] = fixture

    def record(self, value):
        if isinstance(value, str):
            value = canonical.load((HERE.parents[1] / value).read_bytes())
        identifier = records.resolve(value, self.kinds)
        self.assertEqual(self.schemas[identifier].validate(value, "stored"), [],
                         "a rule fixture must load; a record the schema refuses tests the schema")
        return value

    def context(self, row):
        """A context names the store's records by path, or states a mapping outright."""
        return {key: self.record(value) if isinstance(value, str) else value
                for key, value in row.get("context", {}).items()}

    def test_every_declared_rule_has_an_oracle_and_a_fixture(self):
        declared = set(cases.runtime_rules())
        self.assertTrue(declared)
        self.assertEqual(set(rules.RULES), declared)
        self.assertEqual(set(self.fixtures), declared)

    def test_each_oracle_passes_what_holds_and_catches_what_breaks_where_it_breaks(self):
        for rule, fixture in self.fixtures.items():
            kind, _, oracle = rules.RULES[rule]
            self.assertTrue(fixture["holds"] and fixture["breaks"], rule)
            for row in fixture["holds"]:
                with self.subTest(rule=rule, holds=row.get("what", row["record"])):
                    value = self.record(row["record"])
                    self.assertEqual(value["kind"], kind)
                    self.assertEqual(oracle(value, self.context(row)), [])
            for row in fixture["breaks"]:
                with self.subTest(rule=rule, breaks=row["what"]):
                    value = self.record(row["record"])
                    self.assertEqual(oracle(value, self.context(row)), row["at"])

    def test_every_accepted_example_of_a_rules_kind_holds_it(self):
        # The examples are contract fixtures other cases read; one that broke a rule would teach
        # an implementation the wrong thing without any test saying so.
        checked = 0
        for path in sorted(examples.EXAMPLES.rglob("*.json")):
            if path.name.endswith(examples.EXPECT_SUFFIX) or path == examples.INDEX:
                continue
            expectation = canonical.load(examples.expectation_path(path).read_bytes())
            if expectation.get("refusals") or expectation.get("subject") != "dispatched" \
                    or expectation.get("mode") != "stored":
                continue
            value = canonical.load(path.read_bytes())
            for rule, (kind, needs_store, oracle) in rules.RULES.items():
                if value.get("kind") == kind and not needs_store:
                    checked += 1
                    self.assertEqual(oracle(value, {}), [], f"{path.name} breaks {rule}")
        self.assertGreater(checked, 10)


if __name__ == "__main__":
    unittest.main()
