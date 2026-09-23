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
from workenv.contracts.schema import load_schema  # noqa: E402


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

    def test_what_a_case_drives_is_read_from_its_scenario(self):
        derived, _ = cases.derive(self.registry)
        generator = ["gates/workenv/scenarios.py", "gates/workenv/scenario.schema.json"]
        cutover = derived["N24-C03-NEG"]
        self.assertIn("entrance.cutover.commit", cutover["operations"])
        self.assertEqual(cutover["contracts"], {"C01", "C03"})
        self.assertEqual(cutover["fixtures"],
                         ["gates/workenv/fixtures/scenarios/n24-c03-neg/", *generator])
        self.assertEqual(derived["RUN-MODE"]["contracts"], {"runner"})
        self.assertIn("gates/workenv/fixtures/runner/preflight.json",
                      derived["RUN-MODE"]["fixtures"])
        self.assertIn("B03", derived["N05-RESTART-POS"]["contracts"])
        self.assertIn("gates/workenv/fixtures/rules/derivative_within_base_rights.json",
                      derived["N27-RIGHTS-NEG"]["fixtures"])
        self.assertIn("gates/workenv/fixtures/text/korean.json",
                      derived["TUI-ENTRY-KO-STATE"]["fixtures"])

    def test_a_case_without_a_scenario_is_refused(self):
        def edit(r):
            r["cases"].append(dict(copy.deepcopy(self.row(r, "cases", "N24-C03-NEG")),
                                   id="N24-GHOST-NEG"))
            self.selection(r, "P18")["cases"].append("N24-GHOST-NEG")
        self.refused("N24-GHOST-NEG: no scenario at "
                     "gates/workenv/fixtures/scenarios/n24-ghost-neg/", edit)

    def test_a_scenario_no_case_defines_is_refused(self):
        def edit(r):
            r["cases"].remove(self.row(r, "cases", "N24-C03-NEG"))
            for row in r["selects"]:
                if "N24-C03-NEG" in row["cases"]:
                    row["cases"].remove("N24-C03-NEG")
        self.refused("scenario n24-c03-neg: no case is defined for it", edit)

    def test_a_scenario_written_for_another_case_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            place = cases.scenario_dir("N24-C03-NEG") + "scenario.json"
            built = json.loads((cases.ROOT / place).read_bytes())
            built["case"] = "N24-C03-POS"
            (pathlib.Path(folder) / place).parent.mkdir(parents=True)
            (pathlib.Path(folder) / place).write_text(json.dumps(built))
            registry = {"atomic": [], "cases": [self.row(self.registry, "cases", "N24-C03-NEG")]}
            self.assertEqual(cases.derive(registry, pathlib.Path(folder))[1],
                             ["N24-C03-NEG: its scenario is written for N24-C03-POS"])

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

    def test_an_atomic_case_selected_outside_the_profiles_families_is_refused(self):
        self.refused("selects P03: DEL-PERSONAL is outside its families",
                     lambda r: self.selection(r, "P03")["cases"].append("DEL-PERSONAL"))

    def test_a_fixture_nobody_tracks_is_refused(self):
        def edit(r):
            r["cases"][0]["reads"] = ["gates/workenv/fixtures/absent.json"]
        self.refused("matches no tracked file", edit)

    def test_an_oracle_the_family_does_not_hold_is_refused(self):
        def edit(r):
            r["cases"][0]["oracle"] = 9
        self.refused("has no oracle 9", edit)

    def test_a_rule_no_contract_declares_is_refused(self):
        def edit(r):
            self.row(r, "cases", "N07-C05-NEG")["rules"] = ["C05/nothing_declares_this"]
        self.refused("declared by no contract module", edit)

    def test_a_declared_rule_no_case_checks_is_refused(self):
        def edit(r):
            del self.row(r, "cases", "N08-READER-GAP-NEG")["rules"]
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

    def test_an_implementation_profile_that_states_no_joined_cases_is_refused(self):
        # Silence and "I have none" read alike in a document, and only one of them is correct.
        self.refused("P04 implements something and the row states no joined cases",
                     lambda r: self.selection(r, "P04").pop("joined"))

    def test_an_implementation_profile_joining_nothing_to_its_predecessor_is_refused(self):
        self.refused("P04 depends on P03, which implement, and no case is joined to any of them",
                     lambda r: self.selection(r, "P04").__setitem__("joined", []))

    def test_a_profile_with_no_implementation_predecessor_that_joins_one_is_refused(self):
        def edit(registry):
            self.selection(registry, "P02")["joined"] = [{"case": "N02-C01-POS",
                                                          "predecessor": "P03"}]
        self.refused("P02 depends on no node that implements", edit)

    def test_a_joined_case_the_profile_does_not_select_is_refused(self):
        def edit(registry):
            self.selection(registry, "P04")["joined"][0]["case"] = "N27-ADR-POS"
        self.refused("selects P04: N27-ADR-POS is joined and not selected", edit)

    def test_a_case_joined_to_a_node_the_profile_does_not_depend_on_is_refused(self):
        def edit(registry):
            self.selection(registry, "P04")["joined"][0]["predecessor"] = "P02"
        self.refused("is joined to P02, which P04 does not depend on as an implementation", edit)

    def test_the_bindings_artifact_covers_every_profile_the_plan_names(self):
        artifact = cases.bindings(self.registry, loaded=self.loaded, paths=self.paths)
        self.assertEqual(set(artifact), {"bindings"})
        self.assertEqual(set(artifact["bindings"]),
                         {node["test_profile"] for node in self.loaded[0]["nodes"]})

    def test_every_binding_in_the_artifact_satisfies_the_dated_evaluator(self):
        # The evaluator reads this artifact as the frozen registry, so a binding it would
        # refuse must not reach it as one this module emitted.
        plan, catalog, evaluator = self.loaded
        atomic = {a["id"]: f["id"] for f in catalog["cases"] for a in f.get("atomic_cases", [])}
        artifact = cases.bindings(self.registry, loaded=self.loaded, paths=self.paths)
        for name, binding in sorted(artifact["bindings"].items()):
            self.assertEqual(evaluator.binding_errors(catalog["profiles"][name], binding, atomic),
                             [], name)

    def test_the_artifact_carries_an_accepted_binding_verbatim(self):
        artifact = cases.bindings(self.registry, loaded=self.loaded, paths=self.paths)
        carried = next(r for r in self.registry["carried"] if r["profile"] == "P00")
        self.assertEqual(artifact["bindings"]["P00"],
                         cases.carried_binding(carried))

    def test_a_profile_selected_twice_is_refused(self):
        self.refused("stated twice", lambda r: r["selects"].append(copy.deepcopy(r["selects"][0])))

    def test_a_family_with_no_case_is_refused_by_the_dated_evaluator_too(self):
        registry = copy.deepcopy(self.registry)
        self.selection(registry, "P18")["cases"].clear()
        self.assertIn("P18: the evaluator refuses its case map: "
                      "empty/incomplete bound case families", self.check(registry))

    def test_an_operation_no_case_drives_is_refused(self):
        derived, _ = cases.derive(self.registry)
        for drives in derived.values():
            drives["operations"].discard("store.backup.create")
        problems = cases.check(self.registry, loaded=self.loaded, paths=self.paths,
                               derived=derived)[0]
        self.assertIn("operation store.backup.create: no case drives it", problems)

    def cover(self, registry, profile):
        return next(r for r in registry["covers"] if r["profile"] == profile)

    def test_a_profile_whose_done_when_nobody_maps_is_refused(self):
        self.refused("covers P03: no row maps its done_when items",
                     lambda r: r["covers"].remove(self.cover(r, "P03")))
        self.refused("covers P03: 6 items for 7 done_when items",
                     lambda r: self.cover(r, "P03")["done_when"].pop())

    def test_a_done_when_item_realized_by_a_case_the_profile_does_not_run_is_refused(self):
        self.refused("covers P03 done_when[0]: N24-C03-NEG is bound to neither P03 nor R0",
                     lambda r: self.cover(r, "P03")["done_when"][0].append("N24-C03-NEG"))

    def test_a_node_contract_no_bound_case_drives_needs_a_reason_elsewhere(self):
        def drop(r):
            row = self.cover(r, "P18")
            row["elsewhere"] = [e for e in row["elsewhere"] if e["contract"] != "C12"]
        self.refused("covers P18: no bound case drives C12", drop)
        self.refused("covers P18: elsewhere names C01, which a bound case drives",
                     lambda r: self.cover(r, "P18")["elsewhere"].append(
                         {"contract": "C01", "reason": "said without looking"}))

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
        cls.derived = cases.derive(cls.registry, cls.root)[0]
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
        return {p for p in self.profiles if p != "P00" and any(
            predicate(self.derived[c]) for c in self.before[p]["cases"] if c in self.derived)}

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
        fixture = "gates/workenv/fixtures/scenarios/n13-c09-pos/scenario.json"
        wanted = self.readers_of(lambda drives: fixture in drives["fixtures"]
                                 or any(f.endswith("/") and fixture.startswith(f)
                                        for f in drives["fixtures"]))
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
        wanted = self.readers_of(lambda drives: "C10" in drives["contracts"])
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


class RunnerInterface(unittest.TestCase):
    """The runner's preflight cases and the interface they drive are closed documents."""

    def test_the_preflight_cases_load_under_their_schema_and_each_interface_schema_loads(self):
        folder = cases.ROOT / cases.RUNNER_FIXTURES
        schemas = {path.name: load_schema(json.loads(path.read_text()))
                   for path in sorted(folder.glob("*.schema.json"))}
        self.assertEqual(sorted(schemas), ["invocation.schema.json", "packet.schema.json",
                                           "preflight.schema.json", "report.schema.json",
                                           "worker-result.schema.json"])
        preflight = json.loads((folder / "preflight.json").read_text())
        self.assertEqual(schemas["preflight.schema.json"].validate(preflight), [])
        self.assertTrue(preflight["cases"])

    def test_the_runner_contract_is_its_evaluator_suite_and_interface_schemas(self):
        plan = cases.bundle()[0]
        files = cases.contract_files(cases.RUNNER, plan)
        self.assertEqual(len([f for f in files if f.startswith(cases.RUNNER_FIXTURES)]), 5)


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
