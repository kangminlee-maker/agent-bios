"""The executor: every scenario it can run passes against a scripted owner, and each rule it
applies fails a planted difference by name (adapter design, section 7)."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "conformance"))
import cases  # noqa: E402
import executor  # noqa: E402
import host as hosts  # noqa: E402
from workenv.contracts import canonical  # noqa: E402

SCENARIOS = HERE / "fixtures" / "scenarios"
OWNER = "scripted_owner:answer"
JOURNAL = "scripted_owner:journal"
PLACE = "scripted_owner:place"
# A feature whose semantics a test does not need, installed as nothing.
INERT = types.SimpleNamespace(install=lambda run: None)


def scenario(case: str) -> tuple[pathlib.Path, dict]:
    path = SCENARIOS / case / "scenario.json"
    return path, json.loads(path.read_bytes())


def operations(built: dict) -> set[str]:
    return {row["record"]["operation"] for row in built["records"]
            if row["record"].get("kind") == "operation_request"}


def everything(built: dict, entry: str = OWNER) -> executor.Routing:
    """Every operation the scenario sends, served by one entry, with no layer in scope."""
    return executor.Routing({op: entry for op in operations(built)}, set(), [], [], False)


def run(case: str, plants=(), routing=None, features=None, shared=False, env=None,
        root: pathlib.Path = HERE, built=None) -> dict:
    """The case run against the scripted owner, or whatever `root` and `routing` name.

    `shared` gives every world process one host, so one owner sees the whole script."""
    path, stated = scenario(case)
    built = stated if built is None else built
    environment = {"SCRIPTED_SCENARIO": str(path), "SCRIPTED_PLANTS": json.dumps(list(plants)),
                   **(env or {})}
    made: list = []

    def spawn(base):
        if shared and made:
            return made[0]
        made.append(hosts.Host(root, base, env=environment))
        return made[-1]
    return executor.run_case(built, routing or everything(built), spawn=spawn,
                             features=features)


def module_root(test: unittest.TestCase, source: str) -> pathlib.Path:
    """A root holding one module, `planted`, which may delegate to the scripted owner."""
    root = pathlib.Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, root, True)
    (root / "planted.py").write_text(
        f"import sys\nsys.path.insert(0, {str(HERE)!r})\nimport scripted_owner\n{source}",
        encoding="utf-8")
    return root


class Positive(unittest.TestCase):
    def test_every_scenario_the_core_and_its_features_run_passes_against_a_scripted_owner(self):
        # The owner mints values of its own and computes digests over what it received, so a
        # pass means the executor learned each value, carried it where the scenario joins it and
        # recomputed what rests on it. A scenario needing a feature not written yet is blocked
        # by name, never passed.
        outcomes = {}
        for path in sorted(SCENARIOS.glob("*/scenario.json")):
            outcomes[path.parent.name] = run(path.parent.name)
        failed = {case: got for case, got in outcomes.items() if got["outcome"] != "passed"
                  and not got["why"].endswith("which no feature module under features/ runs yet")}
        self.assertEqual(failed, {})
        passed = [case for case, got in outcomes.items() if got["outcome"] == executor.PASSED]
        self.assertGreaterEqual(len(passed), 80, "the control ran almost nothing")
        signed = [case for case in passed
                  if "signature_envelope" in (SCENARIOS / case / "scenario.json").read_text()]
        self.assertTrue(signed, "no scenario that signs was run")

    def test_an_answer_stated_receipt_of_an_earlier_step_passes_with_that_receipt(self):
        got = run("n13-c09-pos", features=self.inert_clock(), shared=True)
        self.assertEqual(got["outcome"], executor.PASSED, got)

    @staticmethod
    def inert_clock() -> dict:
        signing, _ = executor.feature_modules({"signing"})
        return {"clock": INERT, "processes": INERT, **signing}


class Core(unittest.TestCase):
    """One planted difference each, which must fail naming the step, record and pointer."""

    def failed(self, case: str, plants, **where) -> dict:
        got = run(case, plants, **where.pop("run", {}))
        self.assertEqual(got["outcome"], executor.FAILED, got)
        for key, value in where.items():
            self.assertEqual(got.get(key), value, got)
        return got

    def test_a_value_stated_otherwise_fails_at_its_pointer(self):
        self.failed("n09-c07-pos", [{"step": "compose_personal", "path": "result",
                                     "pointer": "/local_effect", "value": "none"}],
                    step="compose_personal", record="compose_personal_result",
                    pointer="/local_effect")

    def test_a_principal_id_that_moves_after_rotation_fails_where_it_moved(self):
        self.failed("n02-c01-pos", [{"step": "bind_second_key", "path": "returned/0",
                                     "pointer": "/principal_id", "value": "prn_" + "1" * 32}],
                    step="bind_second_key", record="rotated_binding", pointer="/principal_id")

    def test_a_learned_value_answered_otherwise_later_fails_at_the_later_place(self):
        self.failed("n01-store-pos", [{"step": "query_the_binding", "path": "returned/1",
                                       "pointer": "/sequence", "value": 424242}],
                    step="query_the_binding", record="bind_device_key_receipt",
                    pointer="/sequence")

    def test_a_digest_over_other_bytes_fails_at_the_digest(self):
        self.failed("n09-c07-pos", [{"step": "bind_alice", "path": "result",
                                     "pointer": "/outputs/0/digest", "value": "0" * 64}],
                    step="bind_alice", record="bind_alice_result", pointer="/outputs/0/digest")

    def test_a_minted_value_not_of_its_shape_fails_where_it_is_minted(self):
        got = self.failed("n09-c07-pos", [{"step": "bind_alice", "path": "returned/0",
                                           "pointer": "/binding_id", "value": "bnd_nothex"}],
                          step="bind_alice", record="alice_binding", pointer="/binding_id")
        self.assertIn("as a bnd", got["why"])

    def test_a_minted_value_absent_from_its_first_place_fails(self):
        got = self.failed("n09-c07-pos", [{"step": "bind_alice", "path": "returned/0",
                                           "pointer": "/binding_id"}],
                          step="bind_alice", record="alice_binding", pointer="/binding_id")
        self.assertIn("no value there", got["why"])

    def test_a_value_its_owner_could_not_store_fails_in_stored_mode(self):
        got = self.failed("n09-c07-pos", [{"step": "author_my_rules", "path": "receipt",
                                           "pointer": "/sequence", "value": 0}],
                          step="author_my_rules", record="author_my_rules_receipt",
                          pointer="/sequence")
        self.assertIn("stored mode", got["why"])

    def test_a_refusal_with_another_code_fails(self):
        got = self.failed("n02-c01-neg", [{"step": "name_as_principal", "path": "refused/0",
                                           "pointer": "/code", "value": "schema_violation"}],
                          step="name_as_principal")
        self.assertIn("schema_violation", got["why"])

    def test_a_refused_request_that_was_admitted_fails(self):
        got = self.failed("n02-c01-neg", [{"step": "name_as_principal", "admit": True}],
                          step="name_as_principal")
        self.assertIn("admitted", got["why"])

    def test_a_stated_refusal_that_is_answered_fails(self):
        got = self.failed("n02-c01-neg", [{"step": "name_as_principal", "answer": True}],
                          step="name_as_principal")
        self.assertIn("states a refusal", got["why"])

    def test_a_replay_that_writes_a_new_receipt_fails(self):
        self.failed("n01-store-pos", [{"step": "read_carrier_back", "path": "receipt",
                                       "pointer": "/sequence", "value": 424242}],
                    step="read_carrier_back", record="bind_carrier_receipt", pointer="/sequence")

    def test_a_settled_duplicate_that_writes_a_new_receipt_fails(self):
        self.failed("n13-c09-pos", [{"step": "accept_full_transfer_again", "path": "receipt",
                                     "pointer": "/sequence", "value": 424242}],
                    run={"features": Positive.inert_clock(), "shared": True},
                    step="accept_full_transfer_again", record="accept_full_transfer_receipt",
                    pointer="/sequence")

    def test_an_answer_refusing_what_the_scenario_answers_fails(self):
        root = module_root(self, 'def answer(call):\n    return {"refused": [{"record": '
                                 '"request", "code": "schema_violation", "pointer": "/"}]}\n')
        _, built = scenario("n09-c07-pos")
        got = run("n09-c07-pos", routing=everything(built, "planted:answer"), root=root)
        self.assertEqual((got["outcome"], got["step"]), (executor.FAILED, "bind_alice"), got)
        self.assertIn("refused it", got["why"])


class Routing(unittest.TestCase):
    def setUp(self):
        self.log = pathlib.Path(tempfile.mkdtemp()) / "log.jsonl"
        self.addCleanup(shutil.rmtree, self.log.parent, True)

    def seen(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def request_ids(self, built: dict, steps: list[str]) -> set[str]:
        held = {row["name"]: row["record"] for row in built["records"]}
        return {held[s["request"]]["request_id"] for s in built["steps"] if s["name"] in steps}

    def test_a_step_no_code_in_scope_serves_is_given_placed_and_layered(self):
        _, built = scenario("n09-c07-pos")
        served = {"identity.binding.add": OWNER, "preparation.compose": OWNER}
        routing = executor.Routing(served, set(), [JOURNAL], [PLACE], True)
        got = run("n09-c07-pos", routing=routing, env={"SCRIPTED_LOG": str(self.log)})
        self.assertEqual(got["outcome"], executor.PASSED, got)
        given = [s["name"] for s in built["steps"]
                 if s["name"] in ("author_my_rules", "bind_repository", "author_repo_rules")]
        self.assertEqual(len(given), 3)
        placed = {line["place"] for line in self.seen() if "place" in line}
        self.assertEqual(placed, self.request_ids(built, given))
        layered = {line["request_id"] for line in self.seen() if line.get("layer") == "journal"}
        self.assertEqual(layered, self.request_ids(built, [s["name"] for s in built["steps"]]))

    def test_an_addressed_operation_is_answered_by_the_journal_in_scope(self):
        _, built = scenario("n01-store-pos")
        served = {op: OWNER for op in operations(built) - {"operation.query"}}
        routing = executor.Routing(served, {"operation.query"}, [JOURNAL], [], True)
        got = run("n01-store-pos", routing=routing, env={"SCRIPTED_LOG": str(self.log)})
        self.assertEqual(got["outcome"], executor.PASSED, got)
        queried = {line["request_id"] for line in self.seen()
                   if line.get("operation") == "operation.query" and not line["given"]}
        self.assertEqual(queried, self.request_ids(built, ["query_the_binding",
                                                            "query_the_binding_again"]))

    def test_an_addressed_operation_is_given_without_the_journal(self):
        _, built = scenario("n01-store-pos")
        served = {op: OWNER for op in operations(built) - {"operation.query"}}
        routing = executor.Routing(served, {"operation.query"}, [], [], False)
        self.assertEqual(run("n01-store-pos", routing=routing)["outcome"], executor.PASSED)

    def test_an_addressed_operation_no_layer_answers_fails(self):
        root = module_root(self, "answer = scripted_owner.answer\n"
                                 "def layer(call, inner):\n    return inner(call)\n")
        _, built = scenario("n01-store-pos")
        served = {op: "planted:answer" for op in operations(built) - {"operation.query"}}
        routing = executor.Routing(served, {"operation.query"}, ["planted:layer"], [], True)
        got = run("n01-store-pos", routing=routing, root=root)
        self.assertEqual((got["outcome"], got["step"]), (executor.FAILED, "query_the_binding"))
        self.assertIn("reached past every layer", got["why"])

    def test_the_profile_routing_serves_in_scope_operations_and_gives_the_rest(self):
        serving = cases.load_serving()
        routing = executor.routing(serving, {"V1", "P01"})
        self.assertEqual(routing.route("identity.binding.add"),
                         ("entry", "workenv.identity:identity_binding_add"))
        self.assertEqual(routing.route("team.found"), ("given", None))
        self.assertEqual(routing.route("operation.query"), ("addressed", None))
        self.assertEqual(routing.layers, ["workenv.journal:layer_journal"])
        self.assertEqual(routing.places, ["workenv.storage:place_given"])
        below = executor.routing(serving, {"P01"})
        self.assertEqual((below.route("operation.query"), below.layers, below.places),
                         (("given", None), [], []))


class Blocking(unittest.TestCase):
    def test_an_entry_not_written_blocks_and_names_it(self):
        _, built = scenario("n09-c07-pos")
        for entry, said in (("absent_module:answer", "module absent_module is not written"),
                            ("scripted_owner:absent", "scripted_owner defines no absent")):
            with self.subTest(entry=entry):
                got = run("n09-c07-pos", routing=everything(built, entry))
                self.assertEqual((got["outcome"], got["step"]), (executor.BLOCKED, "bind_alice"))
                self.assertIn(said, got["why"])

    def test_a_layer_not_written_blocks_and_names_it(self):
        _, built = scenario("n09-c07-pos")
        routing = executor.Routing(everything(built).entries, set(),
                                   ["absent_module:layer"], [], True)
        got = run("n09-c07-pos", routing=routing)
        self.assertEqual(got["outcome"], executor.BLOCKED, got)
        self.assertIn("absent_module:layer", got["why"])

    def test_a_feature_not_written_blocks_before_any_step(self):
        _, built = scenario("n09-c07-pos")
        planted = {**copy.deepcopy(built), "world": {"clock": {"start": "2026-01-01T00:00:00Z"}}}
        got = run("n09-c07-pos", built=planted)
        self.assertEqual(got["outcome"], executor.BLOCKED, got)
        self.assertNotIn("step", got)
        self.assertIn("uses clock", got["why"])

    def test_a_case_naming_runtime_rules_is_blocked_rather_than_judged_without_them(self):
        _, built = scenario("n09-c07-pos")
        got = executor.run_case(built, everything(built), rules=("C01/read_within_selection",))
        self.assertEqual(got["outcome"], executor.BLOCKED, got)
        self.assertIn("C01/read_within_selection", got["why"])


class Hosting(unittest.TestCase):
    def outcome(self, source: str, env=None) -> dict:
        root = module_root(self, source)
        _, built = scenario("n09-c07-pos")
        return run("n09-c07-pos", routing=everything(built, "planted:answer"), root=root,
                   env=env)

    def test_code_that_prints_does_not_corrupt_the_answer(self):
        got = self.outcome("def answer(call):\n    print('noise', flush=True)\n"
                           "    return scripted_owner.answer(call)\n")
        self.assertEqual(got["outcome"], executor.PASSED, got)

    def test_code_under_test_cannot_import_the_judge(self):
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        (root / "bare.py").write_text(
            "import importlib.util\ndef answer(call):\n    raise RuntimeError('judge importable: '"
            " + str(importlib.util.find_spec('host') is not None))\n", encoding="utf-8")
        _, built = scenario("n09-c07-pos")
        got = run("n09-c07-pos", routing=everything(built, "bare:answer"), root=root)
        self.assertIn("judge importable: False", got["why"])

    def test_code_that_raises_fails_with_its_own_line(self):
        got = self.outcome("def answer(call):\n    raise RuntimeError('boom')\n")
        self.assertEqual((got["outcome"], got["step"]), (executor.FAILED, "bind_alice"))
        self.assertIn("RuntimeError: boom", got["why"])

    def test_a_process_that_dies_fails_the_step(self):
        got = self.outcome("import os\ndef answer(call):\n    os._exit(3)\n")
        self.assertEqual((got["outcome"], got["step"]), (executor.FAILED, "bind_alice"))
        self.assertIn("died with status 3", got["why"])

    def test_code_under_test_runs_its_assertions_in_a_home_of_its_own(self):
        source = ("import os, pathlib\ndef answer(call):\n"
                  "    assert pathlib.Path.home() != pathlib.Path(os.environ['REAL_HOME'])\n"
                  "    home = pathlib.Path.home().resolve()\n"
                  "    assert (call.state / '..' / 'home').resolve() == home\n"
                  "    return scripted_owner.answer(call)\n")
        got = self.outcome(source, env={"REAL_HOME": str(pathlib.Path.home())})
        self.assertEqual(got["outcome"], executor.PASSED, got)
        with mock.patch.dict(os.environ, {"PYTHONOPTIMIZE": "1"}):
            got = self.outcome("def answer(call):\n    assert False, 'asserts run'\n")
        self.assertIn("AssertionError: asserts run", got["why"])


class Materializing(unittest.TestCase):
    """What the executor builds, apart from any owner that shares its code."""

    BUILT = {"records": [{"name": "a", "record": {"v": "stand-in"}},
                         {"name": "b", "record": {"ref": {"digest": "0" * 64, "size": 1}}}],
             "joins": [{"record": "a", "pointer": "/v", "minted": "m"},
                       {"record": "b", "pointer": "/ref/digest", "digest_of": "a"}],
             "minted": [{"name": "m", "shape": "digest", "step": "s"}], "steps": []}

    def fresh_run(self) -> executor.Run:
        workdir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, workdir, True)
        return executor.Run(copy.deepcopy(self.BUILT), None, workdir, None)

    def test_a_learned_value_fills_its_place_and_what_rests_on_it_is_recomputed(self):
        run = self.fresh_run()
        run.learned["m"] = "f" * 64
        a = run.materialize("a")
        self.assertEqual(a, {"v": "f" * 64})
        self.assertEqual(run.materialize("b")["ref"],
                         {"digest": hashlib.sha256(canonical.encode(a)).hexdigest(),
                          "size": len(canonical.encode(a))})

    def test_an_unlearned_value_keeps_its_stand_in(self):
        self.assertEqual(self.fresh_run().materialize("a"), {"v": "stand-in"})

    def test_the_first_difference_is_named_by_pointer(self):
        self.assertEqual(executor.difference({"a": [1, {"b~/": 2}]}, {"a": [1, {"b~/": 3}]}),
                         ("/a/1/b~0~1", "states 2, answered 3"))
        self.assertEqual(executor.difference({"a": 1}, {"a": True})[0], "/a")
        self.assertEqual(executor.difference([1], [1, 2]), ("/", "states 1 item(s), answered 2"))
        self.assertIsNone(executor.difference({"a": [1]}, {"a": [1]}))


class Signing(unittest.TestCase):
    """The signing feature, held to ssh-keygen's own verification."""

    CASE = "n01-store-neg"

    def setUp(self):
        _, self.built = scenario(self.CASE)
        workdir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, workdir, True)
        self.run_ = executor.Run(copy.deepcopy(self.built), None, workdir, None)
        executor.feature_modules({"signing"})[0]["signing"].install(self.run_)
        for hook in self.run_.prepare_hooks:
            hook(self.run_)

    def test_every_stated_public_key_is_replaced_by_a_generated_one(self):
        stated = {row["record"]["credential"]["public_key"] for row in self.built["records"]
                  if row["record"].get("kind") == "principal_binding"}
        self.assertTrue(stated)
        text = json.dumps(self.run_.templates)
        for key in stated:
            self.assertNotIn(key, text)

    def verified(self, data: bytes, envelope: dict) -> bool:
        public = self.run_.templates["stored_key"]["credential"]["public_key"]
        workdir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, workdir, True)
        (workdir / "allowed").write_text(
            f'person namespaces="{envelope["namespace"]}" {public}\n')
        body = envelope["sshsig"]
        lines = [body[i:i + 70] for i in range(0, len(body), 70)]
        (workdir / "sig").write_text("-----BEGIN SSH SIGNATURE-----\n" + "\n".join(lines)
                                     + "\n-----END SSH SIGNATURE-----\n")
        done = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(workdir / "allowed"),
                               "-I", "person", "-n", envelope["namespace"],
                               "-s", str(workdir / "sig")], input=data, capture_output=True)
        return done.returncode == 0

    def test_an_envelope_verifies_over_the_bytes_it_names_and_over_no_others(self):
        envelope = self.run_.materialize("signature")
        base64.b64decode(envelope["sshsig"], validate=True)
        named = self.run_.bytes_of("revision")
        self.assertEqual(hashlib.sha256(named).hexdigest(), envelope["signed_digest"])
        self.assertTrue(self.verified(named, envelope))
        self.assertFalse(self.verified(named + b" ", envelope))

    def test_an_envelope_whose_signer_the_scenario_does_not_state_fails(self):
        self.run_.learned["alice_binding"] = "bnd_" + "2" * 32
        self.run_.templates["stored_key"]["binding_id"] = "bnd_" + "3" * 32
        self.run_.joins["stored_key"] = []
        self.run_.forget()
        with self.assertRaises(executor.Stop) as raised:
            self.run_.materialize("signature")
        self.assertEqual(raised.exception.outcome, executor.FAILED)
        self.assertIn("no principal binding", raised.exception.why)


if __name__ == "__main__":
    unittest.main()
