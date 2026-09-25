"""Case registry and runtime-rule oracle tests. Run by gates/workenv/check-workenv.py, one process
per file."""
import copy
import json
import pathlib
import shutil
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
        self.assertEqual(len(report), 13)

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
            self.selection(r, "PK")["cases"].append("N24-GHOST-NEG")
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
            self.assertEqual(cases.derive(registry, pathlib.Path(folder),
                                          cases.load_serving())[1],
                             ["N24-C03-NEG: its scenario is written for N24-C03-POS"])

    def test_a_family_the_catalog_does_not_hold_is_refused(self):
        def edit(r):
            r["cases"].append(dict(copy.deepcopy(r["cases"][0]), id="N99-C01-POS"))
            self.selection(r, "V1")["cases"].append("N99-C01-POS")
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
        self.refused("selects PK: DEL-PERSONAL is outside its families",
                     lambda r: self.selection(r, "PK")["cases"].append("DEL-PERSONAL"))

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

    def test_a_rule_whose_contract_steps_no_binding_profile_serves_is_refused(self):
        # Every C05 operation served by a node no profile's scope holds: the case's C05 steps
        # are the driver's wherever it is bound. V2 still lists C05 and is in scope of every
        # profile binding the case, so a check that asked only whether a node in scope lists
        # the contract would count the rule checked.
        serving = copy.deepcopy(cases.load_serving())
        c05 = {op for op, contract in cases.owners()[0].items() if contract == "C05"}
        for operation in c05:
            if not serving["operations"][operation].get("addressed"):
                serving["operations"][operation]["node"] = "SYNTHETIC-UNREACHED"
        derived = cases.derive(self.registry, serving=serving)[0]
        self.assertIn("C05", {n["id"]: n for n in self.loaded[0]["nodes"]}["V2"]["contracts"])
        problems = cases.check(self.registry, loaded=self.loaded, paths=self.paths,
                               derived=derived)[0]
        self.assertIn("rule C05/gap_named_entry_not_current: N07-STATE-GAP-NEG is bound at no "
                      "profile whose scope serves one of its C05 steps", problems)

    def test_a_rule_checked_by_a_case_that_never_drives_its_contract_is_refused(self):
        # The storage case drives C01, C03, C08 and C09 and no C05 operation or record, and it
        # is bound where C05 is implemented: only the case's own contracts can tell.
        rule = "C05/gap_named_entry_not_current"

        def edit(registry):
            self.row(registry, "cases", "N07-STATE-GAP-NEG")["rules"].remove(rule)
            self.row(registry, "cases", "N01-STORE-POS").setdefault("rules", []).append(rule)
        self.refused(f"rule {rule}: N01-STORE-POS drives no operation or record of C05", edit)

    def test_a_rule_is_checked_where_a_node_in_scope_implements_it(self):
        # V4 lists no C06 of its own and runs V2's code, which does: the reading a stage chain
        # needs, since a later stage is never asked to restate an earlier one's contracts.
        nodes = {n["id"]: n for n in self.loaded[0]["nodes"]}
        self.assertNotIn("C06", nodes["V4"]["contracts"])
        self.assertIn("N08-READER-GAP-NEG", self.selection(self.registry, "V4")["cases"])
        self.assertIn("C06/gap_named_frontier_not_returned",
                      self.row(self.registry, "cases", "N08-READER-GAP-NEG")["rules"])
        self.assertFalse([p for p in self.check(self.registry) if "N08-READER-GAP-NEG" in p])

    def test_a_selection_outside_the_profiles_families_is_refused(self):
        self.refused("is outside its families",
                     lambda r: self.selection(r, "V1")["cases"].append("N10-C08-POS"))

    def test_a_case_nobody_selects_is_refused(self):
        def edit(r):
            self.selection(r, "PK")["cases"].remove("N24-C03-NEG")
        self.refused("N24-C03-NEG: defined and selected by no profile", edit)

    def test_a_selected_case_nobody_defines_is_refused(self):
        self.refused("is defined nowhere",
                     lambda r: self.selection(r, "V1")["cases"].append("N02-GHOST-POS"))

    def test_a_stage_runs_every_case_the_stages_before_it_selected(self):
        # The re-run rule: nothing is joined to one predecessor; every case an implementation or
        # package node in scope selects is bound again, and the driver runs it on the tree.
        nodes = {n["id"]: n for n in self.loaded[0]["nodes"]}
        bound = cases.case_map(self.registry, self.loaded[1], "V3", nodes)
        for earlier in ("V1", "V2"):
            for case in self.selection(self.registry, earlier)["cases"]:
                self.assertIn(case, bound, (earlier, case))

    def test_a_row_that_states_joined_cases_is_refused(self):
        def edit(registry):
            self.selection(registry, "V3")["joined"] = [{"case": "N07-C05-POS",
                                                         "predecessor": "V2"}]
        path = pathlib.Path(tempfile.mkdtemp()) / "case-index.json"
        self.addCleanup(shutil.rmtree, path.parent, True)
        registry = copy.deepcopy(self.registry)
        path.write_text(json.dumps(registry), encoding="utf-8")
        cases.load(path)  # positive control: the registry as it stands loads
        edit(registry)
        path.write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaises(cases.CaseError) as raised:
            cases.load(path)
        self.assertIn("joined", str(raised.exception))

    def test_a_case_bound_where_a_layer_it_needs_is_out_of_scope_is_refused(self):
        # DC-KEEP's last step is V2's own use, refused access_locked; only the admission layer
        # states that, and it arrives with V4. Bound at V2, the case cannot pass there.
        self.refused("V2: DC-KEEP cannot pass here: use_while_locked expects access_locked, which "
                     "only the admission layer states, and V4 is not in its scope",
                     lambda r: self.selection(r, "V2")["cases"].append("DC-KEEP"))

    def test_the_same_case_bound_where_the_layer_is_in_scope_passes_the_check(self):
        nodes = {n["id"]: n for n in self.loaded[0]["nodes"]}
        self.assertIn("DC-KEEP", cases.case_map(self.registry, self.loaded[1], "V4", nodes))
        self.assertFalse([p for p in self.check(self.registry) if "DC-KEEP" in p])

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
        self.selection(registry, "PK")["cases"].clear()
        self.assertIn("PK: the evaluator refuses its case map: "
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
        items = len(next(n for n in self.loaded[0]["nodes"] if n["id"] == "V1")["done_when"])
        self.refused("covers V1: no row maps its done_when items",
                     lambda r: r["covers"].remove(self.cover(r, "V1")))
        self.refused(f"covers V1: {items - 1} items for {items} done_when items",
                     lambda r: self.cover(r, "V1")["done_when"].pop())

    def test_a_done_when_item_realized_by_a_case_the_profile_does_not_run_is_refused(self):
        self.refused("covers V1 done_when[0]: N24-C03-NEG is bound to neither V1 nor R0",
                     lambda r: self.cover(r, "V1")["done_when"][0].append("N24-C03-NEG"))

    def test_a_node_contract_no_bound_case_drives_needs_a_reason_elsewhere(self):
        def drop(r):
            row = self.cover(r, "PK")
            row["elsewhere"] = [e for e in row["elsewhere"] if e["contract"] != "C12"]
        self.refused("covers PK: no bound case drives C12", drop)
        self.refused("covers PK: elsewhere names C01, which a bound case drives",
                     lambda r: self.cover(r, "PK")["elsewhere"].append(
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


class Serving(unittest.TestCase):
    """Which node answers each step, the layers every request passes through, and what the
    driver would answer itself (D-20260924-38ef51, -f80d5c, -3bb074, D-20260925-3768a8)."""

    @classmethod
    def setUpClass(cls):
        cls.loaded = cases.bundle()
        cls.registry = cases.load()
        cls.serving = cases.load_serving()
        cls.derived = cases.derive(cls.registry)[0]
        cls.nodes = {n["id"]: n for n in cls.loaded[0]["nodes"]}
        carried = {row["profile"] for row in cls.registry["carried"]}
        cls.open = sorted(set(cls.loaded[1]["profiles"]) - carried)

    def serving_refused(self, fragment, mutate):
        serving = copy.deepcopy(self.serving)
        mutate(serving)
        problems = cases.serving_problems(serving, self.loaded[0])
        self.assertTrue(any(fragment in p for p in problems), (fragment, problems))

    def unexercised(self, registry=None, serving=None):
        return cases.unexercised(registry or self.registry, self.loaded[1], self.nodes, self.open,
                                 self.derived, serving or self.serving)

    def test_the_table_serves_every_declared_operation_and_nothing_else(self):
        self.assertEqual(cases.serving_problems(self.serving, self.loaded[0]), [])

    def test_a_layer_stating_a_refusal_its_contract_does_not_declare_is_refused(self):
        def edit(serving):
            layer = next(row for row in serving["layers"] if row["name"] == "admission")
            layer["states"].append("request_id_conflict")
        self.serving_refused("serving layer admission: it states request_id_conflict, which C02 "
                             "does not declare", edit)
        self.assertEqual(set(self.serving["operations"]), set(cases.owners()[0]))
        self.assertEqual(len(self.serving["operations"]), 91)

    def test_an_operation_without_a_row_is_refused(self):
        self.serving_refused("serving team.found: the contracts declare it and no row serves it",
                             lambda s: s["operations"].pop("team.found"))

    def test_a_row_for_no_declared_operation_is_refused(self):
        self.serving_refused("serving team.dissolve: no contract declares it",
                             lambda s: s["operations"].__setitem__(
                                 "team.dissolve", {"node": "V5", "entry": "workenv.team:x"}))

    def test_a_node_that_does_not_implement_the_contract_is_refused(self):
        self.serving_refused("serving team.found: V1 does not implement C08",
                             lambda s: s["operations"].__setitem__(
                                 "team.found", {"node": "V1", "entry": "workenv.access:x"}))

    def test_an_entry_outside_the_nodes_owned_paths_is_refused(self):
        # V5 owns every earlier stage's paths too, so the entry is one a later stage adds.
        self.serving_refused("serving team.found: workenv.lifecycle:team_found is not under V5's",
                             lambda s: s["operations"]["team.found"].__setitem__(
                                 "entry", "workenv.lifecycle:team_found"))

    def test_a_node_that_builds_nothing_is_refused(self):
        self.serving_refused("serving team.found: V9 is not an implementation node",
                             lambda s: s["operations"]["team.found"].__setitem__("node", "V9"))

    def test_an_addressed_operation_must_target_a_request(self):
        self.serving_refused("serving team.state.read: marked addressed and it targets no request",
                             lambda s: s["operations"].__setitem__(
                                 "team.state.read", {"addressed": True}))

    def test_a_table_without_the_journal_layer_is_refused(self):
        def edit(s):
            s["layers"] = [layer for layer in s["layers"] if layer["name"] != cases.JOURNAL]
        self.serving_refused("no journal layer", edit)

    def test_a_refusal_two_layers_state_can_come_from_either(self):
        # A second layer stating access_locked, at V8: DC-KEEP at V4 still has the admission
        # layer in scope, whichever of the two is declared first.
        admission = next(row for row in self.serving["layers"] if row["name"] == "admission")
        later = dict(copy.deepcopy(admission), name="later-admission", node="V8")
        on_v2 = copy.deepcopy(self.registry)
        next(r for r in on_v2["selects"] if r["profile"] == "V2")["cases"].append("DC-KEEP")
        for first in (False, True):
            with self.subTest(later_declared_first=first):
                serving = copy.deepcopy(self.serving)
                serving["layers"].insert(0 if first else len(serving["layers"]), later)
                self.assertEqual(cases.serving_problems(serving, self.loaded[0]), [])
                self.assertEqual(cases.unpassable(self.registry, self.loaded[1], self.nodes,
                                                  self.open, self.derived, serving), [])
                names = ("later-admission and admission" if first
                         else "admission and later-admission")
                where = "V8, V4" if first else "V4, V8"
                self.assertIn(f"V2: DC-KEEP cannot pass here: use_while_locked expects "
                              f"access_locked, which only the {names} layers state, and none "
                              f"of {where} is in its scope",
                              cases.unpassable(on_v2, self.loaded[1], self.nodes, self.open,
                                               self.derived, serving))

    def test_a_layer_stated_twice_is_refused(self):
        self.serving_refused("serving layers: admission is stated twice",
                             lambda s: s["layers"].append(copy.deepcopy(s["layers"][0])))

    def test_scope_follows_dependencies_through_other_nodes(self):
        # V3 depends on V2, which depends on V1: the first stage is in V3's scope, R0 is not.
        self.assertNotIn("V1", self.nodes["V3"]["depends_on"])
        self.assertIn("V1", cases.scope("V3", self.nodes))
        self.assertNotIn("R0", cases.scope("V3", self.nodes))

    def test_a_query_is_routed_to_the_node_that_serves_the_request_it_addresses(self):
        query = next(s for s in self.derived["N02-C01-POS"]["steps"]
                     if s.get("operation") == "operation.query")
        self.assertEqual((query["node"], query["addresses"]), ("V1", "identity.binding.add"))

    def test_a_step_addressing_a_request_no_step_submits_cannot_be_routed(self):
        built = json.loads((cases.ROOT / cases.scenario_dir("N02-C01-POS")
                            / cases.scenarios.GENERATED).read_bytes())
        held = next(r for r in built["records"]
                    if r["record"].get("operation") == "operation.query")
        held["record"]["target"]["resource_id"] = "req_" + "0" * 32
        problems = cases.served_steps(built, self.serving)[1]
        self.assertTrue(any("no step of this scenario submits a request under that id" in p
                            for p in problems), problems)

    def test_nothing_is_left_answered_by_the_driver_everywhere_without_a_reason(self):
        # V9 runs every case with every stage in scope, so no step is the driver's everywhere,
        # and the given rows the component graph needed have no step left to excuse.
        problems, disclosures = self.unexercised()
        self.assertEqual((problems, disclosures), ([], []))
        self.assertEqual(self.registry["given"], [])

    def lock_steps(self):
        return [s["name"] for s in self.derived["N03-SECRET-NEG"]["steps"]
                if s.get("operation") == "access.transition"]

    def served_nowhere(self):
        # A serving node no binding profile's scope holds: its steps are the driver's everywhere.
        serving = copy.deepcopy(self.serving)
        serving["operations"]["access.transition"]["node"] = "SYNTHETIC-UNREACHED"
        derived = cases.derive(self.registry, serving=serving)[0]
        return serving, derived

    def test_a_step_no_binding_profile_serves_is_disclosed(self):
        serving, derived = self.served_nowhere()
        self.assertTrue(self.lock_steps())
        disclosures = cases.unexercised(self.registry, self.loaded[1], self.nodes, self.open,
                                        derived, serving)[1]
        for step in self.lock_steps():
            self.assertTrue(any(d.startswith(f"N03-SECRET-NEG {step} ") for d in disclosures),
                            (step, disclosures))

    def test_a_given_row_accepts_exactly_the_steps_it_names(self):
        serving, derived = self.served_nowhere()
        registry = copy.deepcopy(self.registry)
        registry["given"] = [{"case": "N03-SECRET-NEG", "steps": self.lock_steps(),
                              "reason": "planted"}]
        problems, disclosures = cases.unexercised(registry, self.loaded[1], self.nodes, self.open,
                                                  derived, serving)
        self.assertEqual(problems, [])
        self.assertFalse([d for d in disclosures if d.startswith("N03-SECRET-NEG ")], disclosures)
        registry["given"][0]["steps"] = self.lock_steps()[1:]
        disclosures = cases.unexercised(registry, self.loaded[1], self.nodes, self.open,
                                        derived, serving)[1]
        self.assertTrue(any(d.startswith(f"N03-SECRET-NEG {self.lock_steps()[0]} ")
                            for d in disclosures), disclosures)

    def test_a_given_row_that_excuses_an_exercised_step_is_refused(self):
        registry = copy.deepcopy(self.registry)
        registry["given"].append({"case": "N02-C01-POS", "steps": ["read_profile"],
                                  "reason": "planted"})
        problems = self.unexercised(registry)[0]
        self.assertTrue(any("given N02-C01-POS: read_profile is answered by code" in p
                            for p in problems), problems)

    def test_a_given_row_naming_no_step_or_no_case_is_refused(self):
        registry = copy.deepcopy(self.registry)
        registry["given"].append({"case": "N01-STORE-POS", "steps": ["no_such_step"],
                                  "reason": "planted"})
        registry["given"].append({"case": "N01-STORE-POS", "steps": ["another_missing_step"],
                                  "reason": "planted"})
        registry["given"].append({"case": "N99-NONE-POS", "steps": ["x"], "reason": "planted"})
        problems = self.unexercised(registry)[0]
        for fragment in ("given N01-STORE-POS: stated twice",
                         "given N01-STORE-POS: no_such_step is not a step of its scenario",
                         "given N99-NONE-POS: no profile binds a case by that id"):
            self.assertTrue(any(fragment in p for p in problems), (fragment, problems))

    def test_a_case_on_which_no_code_in_scope_runs_is_refused(self):
        # Every operation served outside V1's scope and no layer: the driver would answer every
        # step of V1's cases, and binding them there is evidence of nothing.
        serving = copy.deepcopy(self.serving)
        serving["layers"] = []
        for row in serving["operations"].values():
            if not row.get("addressed"):
                row["node"] = "V8"
        derived = cases.derive(self.registry, serving=serving)[0]
        problems = cases.unexercised(self.registry, self.loaded[1], self.nodes, self.open,
                                     derived, serving)[0]
        self.assertTrue(any(p.startswith("V1: N01-STORE-POS runs no code in its scope")
                            for p in problems), problems)


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
        self.assertEqual(len(self.before), 13)
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
        self.assertEqual(self.moved(after, "fixture_fingerprint"), {"PK", "V9"})
        self.assertEqual(self.moved(after, "adapter_fingerprint"), set())

    def reached(self, operation):
        return {p for p in self.profiles if p != "P00" and any(
            operation in (s.get("operation"), s.get("addresses"))
            for c in self.before[p]["cases"] for s in self.derived.get(c, {}).get("steps", []))}

    def test_a_serving_row_moves_exactly_the_profiles_whose_steps_reach_it(self):
        path = self.root / cases.SERVING
        original = path.read_bytes()
        serving = json.loads(original)
        serving["operations"]["workstream.open"]["entry"] = "workenv.memory:renamed"
        wanted = self.reached("workstream.open")
        self.assertTrue(wanted and wanted != set(self.profiles) - {"P00"})
        try:
            path.write_text(json.dumps(serving))
            after = self.bindings(self.registry)
        finally:
            path.write_bytes(original)
        self.assertEqual(self.moved(after, "adapter_fingerprint"), wanted)
        self.assertEqual(self.moved(after, "fixture_fingerprint"), set())

    def test_writing_a_feature_module_moves_exactly_the_profiles_whose_cases_use_it(self):
        feature = "during"
        module = f"{cases.FEATURES}/{feature}.py"
        wanted = self.readers_of(lambda drives: feature in drives["features"])
        self.assertTrue(wanted and wanted != set(self.profiles) - {"P00"})
        target = self.root / module
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text('"""planted"""\n')
            after = {p: cases.binding(self.registry, p, self.loaded, self.root,
                                      self.paths + [module]) for p in self.profiles}
        finally:
            target.unlink()
        self.assertEqual(self.moved(after, "adapter_fingerprint"), wanted)
        self.assertNotIn("P01", wanted)

    def test_the_drivers_core_moves_every_profile_it_runs_and_not_the_freeze_itself(self):
        path = self.root / cases.CORE[0]
        original = path.read_bytes()
        try:
            path.write_bytes(original + b"\n")
            after = self.bindings(self.registry)
        finally:
            path.write_bytes(original)
        self.assertEqual(self.moved(after, "adapter_fingerprint"),
                         set(self.profiles) - {"P00", "P01"})


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
