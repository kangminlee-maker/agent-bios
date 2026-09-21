"""Scenario generator tests. Run by gates/workenv/check-workenv.py, one process per file.

Each rule the generator enforces is shown firing on a spec built here from a base that generates
cleanly, so a failure is attributable to the one change made to it."""
import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

import scenarios  # noqa: E402
from workenv.contracts import examples  # noqa: E402

REQUEST = {"name": "bind", "from": "c01/link_request.json",
           "set": [{"pointer": "/request_id", "value": "@bind_request"},
                   {"pointer": "/actor/principal_id", "value": "@alice"},
                   {"pointer": "/actor/device_id", "value": "@laptop"},
                   {"pointer": "/owner/principal_id", "value": "@alice"},
                   {"pointer": "/target/resource_id", "value": "@alice"},
                   {"pointer": "/payload_digest", "value": "#first_key"}]}
BASE = {
    "case": "N02-C01-POS",
    "says": "A local principal binds a device key, and the owner answers with the stored binding.",
    "ids": [{"name": "alice", "prefix": "prn"}, {"name": "laptop", "prefix": "dev"},
            {"name": "bind_request", "prefix": "req"}],
    "records": [
        {"name": "first_key", "from": "c01/binding_as_submitted.json",
         "set": [{"pointer": "/principal_id", "value": "@alice"},
                 {"pointer": "/credential/device_id", "value": "@laptop"}]},
        REQUEST,
        {"name": "stored_key", "from": "c01/device_key_binding.json",
         "set": [{"pointer": "/principal_id", "value": "@alice"},
                 {"pointer": "/binding_id", "value": "$bnd:first_binding"},
                 {"pointer": "/created_at", "value": "$instant:bound_at"}]}],
    "steps": [{"name": "bind_first_key", "request": "bind", "carries": ["first_key"],
               "answer": {"stage": "committed", "local_effect": "committed",
                          "provider_effect": "not_applicable", "gaps": [], "recovery": [],
                          "returns": ["stored_key"]}}],
}


def spec_bytes(spec):
    return json.dumps(spec).encode()


class Generator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = examples.load_schemas()

    def generate(self, spec):
        return scenarios.generate(spec_bytes(spec), self.schemas)

    def refused(self, fragment, change):
        spec = copy.deepcopy(BASE)
        change(spec)
        with self.assertRaises(scenarios.ScenarioError) as caught:
            self.generate(spec)
        self.assertIn(fragment, str(caught.exception))

    def record(self, spec, name):
        return next(r for r in spec["records"] if r["name"] == name)

    def test_the_base_joins_its_request_payload_and_result(self):
        # Positive control: every refusal below is a change to this spec.
        built = self.generate(BASE)
        by_name = {row["name"]: row for row in built["records"]}
        request = by_name["bind"]["record"]
        self.assertEqual(request["payload_digest"], by_name["first_key"]["digest"])
        result = by_name["bind_first_key_result"]["record"]
        self.assertEqual(result["request_digest"], by_name["bind"]["digest"])
        self.assertEqual(result["outputs"], [{"kind": "principal_binding",
                                              "digest": by_name["stored_key"]["digest"]}])
        receipt = by_name["bind_first_key_receipt"]
        self.assertEqual(result["outcome"]["receipt_digest"], receipt["digest"])
        self.assertEqual(receipt["record"]["request_digest"], by_name["bind"]["digest"])
        self.assertEqual({m["name"] for m in built["minted"]},
                         {"first_binding", "bound_at", "bind_first_key_head",
                          "bind_first_key_sequence", "bind_first_key_committed_at"})

    def test_a_payload_its_operation_does_not_take(self):
        def change(spec):
            self.record(spec, "first_key")["from"] = "c01/repository_binding_as_submitted.json"
            self.record(spec, "first_key")["set"] = []
        self.refused("identity.binding.add takes", change)

    def test_a_returned_record_its_operation_does_not_return(self):
        def change(spec):
            spec["records"].append({"name": "stray", "from": "c01/exact_member_of_a_revision.json"})
            spec["steps"][0]["answer"]["returns"] = ["stray"]
        self.refused("identity.binding.add returns", change)

    def test_a_digest_the_request_names_and_the_step_does_not_carry(self):
        def change(spec):
            spec["steps"][0]["carries"] = []
        self.refused("does not carry", change)

    def test_a_carried_record_the_request_does_not_name(self):
        def change(spec):
            spec["records"].append({"name": "extra", "from": "c01/binding_as_submitted.json"})
            spec["steps"][0]["carries"].append("extra")
        self.refused("which the request does not name", change)

    def test_a_minted_value_used_before_any_step_returns_it(self):
        def change(spec):
            self.record(spec, "bind")["set"].append(
                {"pointer": "/rationale", "value": "$bnd:first_binding"})
        self.refused("before any step returns them", change)

    def test_an_answer_the_result_schema_cannot_give(self):
        # A commit beside a gap that prevents one has no spelling in operation_result.
        def change(spec):
            spec["steps"][0]["answer"]["gaps"] = [{"code": "stale_base"}]
        self.refused("no result the contract permits", change)

    def test_a_committed_answer_states_a_committed_local_effect(self):
        def change(spec):
            spec["steps"][0]["answer"]["local_effect"] = "private_state_written"
        self.refused("a committed answer states local_effect 'committed'", change)

    def test_a_payload_its_schema_refuses_in_an_answered_step(self):
        def change(spec):
            self.record(spec, "first_key")["set"].append(
                {"pointer": "/binding_id", "value": "bnd_" + "0" * 32})
        self.refused("is refused in submit mode", change)

    def test_a_refused_step_states_exactly_its_refusals(self):
        spec = copy.deepcopy(BASE)
        self.record(spec, "first_key")["set"].append(
            {"pointer": "/binding_id", "value": "bnd_" + "0" * 32})
        spec["steps"][0] = {"name": "bind_first_key", "request": "bind", "carries": ["first_key"],
                            "refused": [{"record": "first_key", "code": "runtime_owned_field",
                                         "pointer": "/binding_id"}]}
        spec["records"] = [r for r in spec["records"] if r["name"] != "stored_key"]
        self.generate(spec)
        spec["steps"][0]["refused"][0]["pointer"] = "/principal_id"
        with self.assertRaises(scenarios.ScenarioError) as caught:
            self.generate(spec)
        self.assertIn("is refused with", str(caught.exception))

    def test_a_record_derived_from_another_carries_its_joins(self):
        spec = copy.deepcopy(BASE)
        spec["ids"].append({"name": "again_request", "prefix": "req"})
        spec["records"].append({"name": "bind_again", "from": "bind",
                                "set": [{"pointer": "/request_id", "value": "@again_request"}]})
        spec["steps"].append({**copy.deepcopy(spec["steps"][0]), "name": "bind_again",
                              "request": "bind_again", "answer": {**spec["steps"][0]["answer"],
                                                                  "returns": []}})
        built = self.generate(spec)
        by_name = {row["name"]: row["record"] for row in built["records"]}
        self.assertEqual(by_name["bind_again"]["payload_digest"],
                         by_name["bind"]["payload_digest"])
        self.assertIn({"record": "bind_again", "pointer": "/payload_digest",
                       "digest_of": "first_key"}, built["joins"])

    def test_a_derived_record_keeps_no_join_where_it_replaces_the_value(self):
        spec = copy.deepcopy(BASE)
        spec["ids"].append({"name": "again_request", "prefix": "req"})
        spec["records"].append({"name": "second_key", "from": "first_key",
                                "set": [{"pointer": "/credential/key_generation", "value": 2}]})
        spec["records"].append({"name": "bind_again", "from": "bind",
                                "set": [{"pointer": "/request_id", "value": "@again_request"},
                                        {"pointer": "/payload_digest", "value": "#second_key"}]})
        spec["steps"].append({"name": "bind_second_key", "request": "bind_again",
                              "carries": ["second_key"],
                              "answer": {**spec["steps"][0]["answer"], "returns": []}})
        joins = [j for j in self.generate(spec)["joins"] if j["record"] == "bind_again"]
        self.assertIn({"record": "bind_again", "pointer": "/payload_digest",
                       "digest_of": "second_key"}, joins)
        self.assertNotIn({"record": "bind_again", "pointer": "/payload_digest",
                          "digest_of": "first_key"}, joins)

    def test_a_record_derived_from_itself(self):
        def change(spec):
            self.record(spec, "bind")["from"] = "bind"
        self.refused("names its own digest", change)

    def test_a_record_from_an_example_that_does_not_exist(self):
        def change(spec):
            self.record(spec, "first_key")["from"] = "c01/no_such_example.json"
        self.refused("no example", change)

    def test_an_id_the_spec_never_names(self):
        def change(spec):
            spec["ids"] = [i for i in spec["ids"] if i["name"] != "laptop"]
        self.refused("no id named 'laptop'", change)

    def test_a_record_no_step_uses(self):
        def change(spec):
            spec["records"].append({"name": "unused", "from": "c01/binding_as_submitted.json"})
        self.refused("named by no step", change)

    def test_a_spec_its_own_schema_refuses(self):
        def change(spec):
            spec["unexpected"] = True
        self.refused("unknown_field", change)


    def test_a_catalog_case_id_names_a_scenario_too(self):
        self.generate({**copy.deepcopy(BASE), "case": "SRC-10"})

    def test_a_record_the_payload_names_may_ride_with_it(self):
        # A batch names its item requests inside its plan, not in the request.
        spec = {"case": "N21-C10-POS", "says": "A batch carries the request it names.", "ids": [],
                "records": [
                    {"name": "item", "from": "c03/batch_second_publication_request.json"},
                    {"name": "plan", "from": "c03/batch_across_three_carriers.json",
                     "drop": ["/items/4", "/items/3", "/items/2", "/items/1"],
                     "set": [{"pointer": "/items/0/request_digest", "value": "#item"}]},
                    {"name": "batch", "from": "c03/batch_request.json",
                     "set": [{"pointer": "/payload_digest", "value": "#plan"}]}],
                "steps": [{"name": "submit_batch", "request": "batch", "carries": ["plan", "item"],
                           "answer": {"stage": "committed", "local_effect": "committed",
                                      "provider_effect": "not_applicable", "gaps": [],
                                      "recovery": [], "returns": []}}]}
        self.generate(spec)
        spec["records"][1]["set"] = []
        with self.assertRaises(scenarios.ScenarioError) as caught:
            self.generate(spec)
        self.assertIn("which the request does not name", str(caught.exception))

    def test_a_later_request_can_expect_the_head_a_commit_moved_to(self):
        spec = copy.deepcopy(BASE)
        # An adoption takes no payload and targets an environment, which keeps a head.
        spec["ids"] += [{"name": "again_request", "prefix": "req"},
                        {"name": "environment", "prefix": "env"}]
        spec["records"].append({"name": "bind_again", "from": "bind", "drop": ["/payload_digest"],
                                "set": [
            {"pointer": "/request_id", "value": "@again_request"},
            {"pointer": "/operation", "value": "environment.adopt"},
            {"pointer": "/action", "value": "adopt"},
            {"pointer": "/target/resource_id", "value": "@environment"},
            {"pointer": "/target/base/expects", "value": "head"},
            {"pointer": "/target/base/head_digest", "value": "$digest:first_head"}]})
        spec["steps"].append({"name": "bind_again", "request": "bind_again", "carries": [],
                              "answer": {**spec["steps"][0]["answer"], "returns": []}})
        with self.assertRaises(scenarios.ScenarioError) as caught:
            self.generate(spec)
        self.assertIn("before any step returns them", str(caught.exception))
        spec["steps"][0]["answer"]["head"] = "first_head"
        built = self.generate(spec)
        self.assertEqual(built["steps"][0]["head"], "first_head")
        # The second receipt names the team the request names, and says where that id came from.
        self.assertIn({"record": "bind_again_receipt", "pointer": "/target/base/head_digest",
                       "minted": "first_head"}, built["joins"])
        spec["steps"][0]["answer"]["stage"] = "previewed"
        self.refused_spec("only a committed answer has one", spec)

    def test_a_head_that_names_a_returned_record_is_that_records_digest(self):
        spec = copy.deepcopy(BASE)
        spec["steps"][0]["answer"]["head"] = "stored_key"
        built = self.generate(spec)
        by_name = {row["name"]: row for row in built["records"]}
        self.assertEqual(by_name["bind_first_key_receipt"]["record"]["head_digest"],
                         by_name["stored_key"]["digest"])
        self.assertIn({"record": "bind_first_key_receipt", "pointer": "/head_digest",
                       "digest_of": "stored_key"}, built["joins"])
        spec["steps"][0]["answer"]["head"] = "first_key"
        self.refused_spec("the answer does not return it", spec)

    def test_an_index_one_past_the_end_appends_an_object(self):
        spec = {"case": "N21-C10-POS", "says": "A plan item is added in the spec.", "ids": [],
                "records": [{"name": "plan", "from": "c03/batch_across_three_carriers.json",
                             "set": [{"pointer": "/items/5/carrier", "value": "local"}]},
                            {"name": "batch", "from": "c03/batch_request.json",
                             "set": [{"pointer": "/payload_digest", "value": "#plan"}]}],
                "steps": [{"name": "submit", "request": "batch", "carries": ["plan"],
                           "answer": {"stage": "committed", "local_effect": "committed",
                                      "provider_effect": "not_applicable", "gaps": [],
                                      "recovery": [], "returns": []}}]}
        # The appended item holds only its carrier, so the plan is refused where it is missing.
        self.refused_spec("'pointer': '/items/5/request_digest'", spec)
        spec["records"][0]["set"][0]["pointer"] = "/items/6/carrier"
        self.refused_spec("no item 6", spec)

    def test_a_carried_record_the_step_submits_is_read_as_submitted(self):
        # A founding submits its new policy with the proposal; the store does not hold it yet.
        spec = {"case": "N10-C08-POS", "says": "A founding submits its policy.", "ids": [],
                "records": [{"name": "policy", "from": "c08/policy_as_submitted.json"},
                            {"name": "proposal", "from": "c08/proposal_as_submitted.json",
                             "set": [{"pointer": "/policy_digest", "value": "#policy"}]},
                            {"name": "found", "from": "c08/founding_request.json",
                             "set": [{"pointer": "/payload_digest", "value": "#proposal"}]}],
                "steps": [{"name": "found_team", "request": "found",
                           "carries": ["proposal", "policy"],
                           "answer": {"stage": "committed", "local_effect": "committed",
                                      "provider_effect": "not_applicable", "gaps": [],
                                      "recovery": [], "returns": []}}]}
        self.refused_spec("policy is refused in stored mode", spec)
        spec["steps"][0]["submits"] = ["policy"]
        self.assertEqual(self.generate(spec)["steps"][0]["submits"], ["policy"])
        spec["steps"][0]["submits"] = ["proposal"]
        self.refused_spec("not a record it carries besides its payload", spec)

    def test_a_missing_field_before_index_zero_is_a_new_array(self):
        def change(spec):
            self.record(spec, "first_key")["set"].append(
                {"pointer": "/missing_list/0/code", "value": "x"})
        # The array is created, so the only complaint is the schema's: no such field.
        self.refused("'pointer': '/missing_list'", change)

    def test_a_change_that_makes_a_key_of_an_index_is_refused_by_name(self):
        def change(spec):
            self.record(spec, "first_key")["set"].append(
                {"pointer": "/missing_list/1/code", "value": "x"})
        self.refused("is not a record canonical JSON can hold", change)

    def test_an_identical_resubmission_replays_the_first_answer(self):
        spec = copy.deepcopy(BASE)
        spec["steps"].append({"name": "bind_again", "request": "bind", "carries": ["first_key"],
                              "replays": "bind_first_key"})
        built = self.generate(spec)
        self.assertEqual(built["steps"][1]["result"], "bind_first_key_result")
        self.assertEqual(built["steps"][1]["returns"], ["stored_key"])
        spec["steps"][1]["replays"] = "never_ran"
        self.refused_spec("which is no earlier answered step", spec)
        spec["ids"].append({"name": "again_request", "prefix": "req"})
        spec["records"].append({"name": "bind_other", "from": "bind",
                                "set": [{"pointer": "/request_id", "value": "@again_request"}]})
        spec["steps"][1].update(request="bind_other", replays="bind_first_key")
        self.refused_spec("with other request bytes", spec)

    def test_a_returned_record_can_name_its_own_steps_receipt(self):
        spec = copy.deepcopy(BASE)
        self.record(spec, "stored_key")["set"].append(
            {"pointer": "/evidence_digests/-", "value": "#bind_first_key_receipt"})
        built = self.generate(spec)
        by_name = {row["name"]: row for row in built["records"]}
        self.assertEqual(by_name["stored_key"]["record"]["evidence_digests"],
                         [by_name["bind_first_key_receipt"]["digest"]])
        self.assertIn({"record": "stored_key", "pointer": "/evidence_digests/0",
                       "digest_of": "bind_first_key_receipt"}, built["joins"])

    def test_a_duplicate_under_a_new_id_states_the_earlier_receipt(self):
        spec = copy.deepcopy(BASE)
        spec["ids"].append({"name": "again_request", "prefix": "req"})
        spec["records"].append({"name": "bind_other", "from": "bind",
                                "set": [{"pointer": "/request_id", "value": "@again_request"}]})
        spec["steps"].append({"name": "bind_again", "request": "bind_other",
                              "carries": ["first_key"],
                              "answer": {"stage": "committed", "local_effect": "committed",
                                         "provider_effect": "not_applicable", "gaps": [],
                                         "recovery": [], "returns": [],
                                         "receipt_of": "bind_first_key"}})
        built = self.generate(spec)
        by_name = {row["name"]: row for row in built["records"]}
        self.assertNotIn("bind_again_receipt", by_name)
        self.assertEqual(by_name["bind_again_result"]["record"]["outcome"]["receipt_digest"],
                         by_name["bind_first_key_receipt"]["digest"])
        self.assertEqual(built["steps"][1]["receipt_of"], "bind_first_key")
        spec["steps"][1]["answer"]["receipt_of"] = "never_ran"
        self.refused_spec("which no earlier committed step wrote", spec)
        spec["steps"][1]["answer"].update(receipt_of="bind_first_key", head="again_head")
        self.refused_spec("names an earlier receipt", spec)

    def refused_spec(self, fragment, spec):
        with self.assertRaises(scenarios.ScenarioError) as caught:
            self.generate(spec)
        self.assertIn(fragment, str(caught.exception))


QUERY = [{"name": "ask", "from": "c03/query_by_request_id.json",
          "set": [{"pointer": "/request_id", "value": "@bind_request"}]},
         {"name": "query", "from": "bind",
          "set": [{"pointer": "/request_id", "value": "@query_request"},
                  {"pointer": "/operation", "value": "operation.query"},
                  {"pointer": "/action", "value": "read"},
                  {"pointer": "/effect_class", "value": "pure_preview"},
                  {"pointer": "/target/resource_id", "value": "@bind_request"},
                  {"pointer": "/payload_digest", "value": "#ask"}]}]
SECOND = [{"name": "second_key", "from": "c01/binding_as_submitted.json",
           "set": [{"pointer": "/principal_id", "value": "@alice"},
                   {"pointer": "/credential/device_id", "value": "@desktop"}]},
          {"name": "bind_second", "from": "bind",
           "set": [{"pointer": "/request_id", "value": "@second_request"},
                   {"pointer": "/payload_digest", "value": "#second_key"}]},
          {"name": "stored_second", "from": "stored_key",
           "set": [{"pointer": "/binding_id", "value": "$bnd:second_binding"},
                   {"pointer": "/evidence_digests/-", "value": "$digest:second_evidence"}]}]


class World(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = examples.load_schemas()

    def spec(self, world, **step):
        spec = copy.deepcopy(BASE)
        spec["world"] = world
        spec["steps"][0].update(step)
        return spec

    def generate(self, spec):
        return scenarios.generate(spec_bytes(spec), self.schemas)

    def refused(self, fragment, spec):
        with self.assertRaises(scenarios.ScenarioError) as caught:
            self.generate(spec)
        self.assertIn(fragment, str(caught.exception))

    def test_a_world_states_where_and_when_each_step_runs(self):
        # Positive control for this class.
        built = self.generate(self.spec(
            {"processes": ["laptop", "desktop"], "clock": {"start": "2026-09-21T09:00:00Z"},
             "partitions": [{"between": ["laptop", "desktop"], "from": "bind_first_key"}],
             "faults": [{"step": "bind_first_key", "point": "after_commit_before_return"}]},
            process="laptop", advance_seconds=60))
        self.assertEqual(built["steps"][0]["process"], "laptop")
        self.assertEqual(built["steps"][0]["at"], "2026-09-21T09:01:00Z")
        self.assertEqual(built["world"]["faults"][0]["point"], "after_commit_before_return")

    def test_every_step_names_one_of_the_processes(self):
        self.refused("runs on no process", self.spec({"processes": ["laptop", "desktop"]}))
        self.refused("names a process", self.spec({}, process="laptop"))

    def test_a_clock_moves_only_when_the_world_declares_one(self):
        self.refused("moves a clock", self.spec({}, advance_seconds=5))

    def test_a_partition_names_processes_and_steps_in_order(self):
        world = {"processes": ["laptop", "desktop"]}
        self.refused("which is no process", self.spec(
            {**world, "partitions": [{"between": ["laptop", "phone"], "from": "bind_first_key"}]},
            process="laptop"))
        self.refused("which is no step", self.spec(
            {**world, "partitions": [{"between": ["laptop", "desktop"], "from": "later"}]},
            process="laptop"))
        self.refused("before it starts", self.spec(
            {**world, "partitions": [{"between": ["laptop", "desktop"], "from": "bind_first_key",
                                      "until": "bind_first_key"}]}, process="laptop"))

    def test_a_fault_names_a_b03_point_on_an_answered_step(self):
        self.refused("no fault point B03 declares", self.spec(
            {"faults": [{"step": "bind_first_key", "point": "after_lunch"}]}))
        self.refused("no answered step", self.spec(
            {"faults": [{"step": "later", "point": "before_stage"}]}))

    def test_a_fault_can_leave_the_answer_to_a_later_query(self):
        spec = self.spec({"faults": [{"step": "bind_first_key", "observed_by": "ask_after",
                                      "point": "after_commit_before_return"}]})
        spec["ids"].append({"name": "query_request", "prefix": "req"})
        spec["records"].extend(copy.deepcopy(QUERY))
        spec["steps"].append({"name": "ask_after", "request": "query", "carries": ["ask"],
                              "answer": {"stage": "previewed", "local_effect": "none",
                                         "provider_effect": "not_applicable", "gaps": [],
                                         "recovery": [], "returns": ["bind_first_key_result",
                                                                     "bind_first_key_receipt"]}})
        self.assertEqual(self.generate(spec)["world"]["faults"][0]["observed_by"], "ask_after")
        spec["steps"][1]["answer"]["returns"] = ["bind_first_key_receipt"]
        self.refused("returning bind_first_key_result", spec)

    def test_a_step_can_run_while_another_is_in_flight(self):
        spec = self.spec({"during": [{"step": "bind_first_key", "runs": "bind_second_key"}]})
        spec["ids"] += [{"name": "desktop", "prefix": "dev"},
                        {"name": "second_request", "prefix": "req"}]
        spec["records"].extend(copy.deepcopy(SECOND))
        spec["steps"].insert(0, {"name": "bind_second_key", "request": "bind_second",
                                 "carries": ["second_key"],
                                 "answer": {**spec["steps"][0]["answer"],
                                            "returns": ["stored_second"]}})
        self.assertEqual(self.generate(spec)["world"]["during"][0]["runs"], "bind_second_key")
        mixed = copy.deepcopy(spec)
        mixed["steps"].reverse()
        self.refused("must be listed immediately before it", mixed)
        next(r for r in spec["records"] if r["name"] == "first_key")["set"].append(
            {"pointer": "/evidence_digests/-", "value": "$digest:second_evidence"})
        self.refused("which that step mints", spec)

    def test_a_runner_step_names_a_situation_of_its_own_case(self):
        spec = {"case": "RUN-MODE", "says": "A runner refused unattended dispatches nothing.",
                "ids": [], "records": [],
                "steps": [{"name": "refused", "runner": "no_qualification"}]}
        self.assertEqual(self.generate(spec)["steps"], [{"name": "refused",
                                                         "runner": "no_qualification"}])
        spec["steps"][0]["runner"] = "stale_base"
        self.refused("no runner situation", spec)


class Committed(unittest.TestCase):
    def test_every_generated_scenario_is_what_its_spec_generates(self):
        schemas = examples.load_schemas()
        for spec in scenarios.specs():
            with self.subTest(spec=str(spec.relative_to(HERE))):
                target = spec.with_name(scenarios.GENERATED)
                self.assertTrue(target.is_file(), f"{target} is not generated")
                self.assertEqual(target.read_bytes(),
                                 scenarios.render(scenarios.generate(spec.read_bytes(), schemas)))


if __name__ == "__main__":
    unittest.main()
