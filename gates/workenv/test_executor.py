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
import rules as oracles  # noqa: E402
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
        root: pathlib.Path = HERE, built=None, rules=()) -> dict:
    """The case run against the scripted owner, or whatever `root` and `routing` name.

    `shared` gives every world process one host, so one owner sees the whole script."""
    path, stated = scenario(case)
    built = stated if built is None else built
    environment = {"SCRIPTED_SCENARIO": str(path), "SCRIPTED_PLANTS": json.dumps(list(plants)),
                   **(env or {})}
    made: list = []

    def spawn(base, cwd=None):
        if shared and made:
            return made[0]
        made.append(hosts.Host(root, base, env=environment, cwd=cwd))
        return made[-1]
    return executor.run_case(built, routing or everything(built), spawn=spawn,
                             features=features, rules=rules)


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
        # Each case applies the runtime rules its registry row names.
        registry = cases.load()
        rules = {row["id"].lower(): tuple(row.get("rules", ()))
                 for key in ("atomic", "cases") for row in registry[key]}
        outcomes = {}
        for path in sorted(SCENARIOS.glob("*/scenario.json")):
            outcomes[path.parent.name] = run(path.parent.name,
                                             rules=rules.get(path.parent.name, ()))
        failed = {case: got for case, got in outcomes.items() if got["outcome"] != "passed"
                  and not (got["outcome"] == executor.BLOCKED
                           and got["why"].endswith(("runs yet", "is not built yet",
                                                    "in a run yet", "cannot be judged")))}
        self.assertEqual(failed, {})
        passed = [case for case, got in outcomes.items() if got["outcome"] == executor.PASSED]
        self.assertGreaterEqual(len(passed), 85, "the control ran almost nothing")
        worlds = {"faults": "n05-restart-pos", "checkout": "src-01", "clock": "src-01",
                  "event_file_edit": "n27-selection-neg"}
        for feature, case in worlds.items():
            self.assertIn(feature, cases.features_of(scenario(case)[1]), case)
            self.assertIn(case, passed, f"no scenario using {feature} passed")
        signed = [case for case in passed
                  if "signature_envelope" in (SCENARIOS / case / "scenario.json").read_text()]
        self.assertTrue(signed, "no scenario that signs was run")

    def test_an_answer_stated_receipt_of_an_earlier_step_passes_with_that_receipt(self):
        got = run("n13-c09-pos", features=self.one_process("n13-c09-pos"), shared=True)
        self.assertEqual(got["outcome"], executor.PASSED, got)

    def test_every_v1_case_but_the_lost_reply_passes(self):
        registry, (plan, catalog, _) = cases.load(), cases.bundle(cases.ROOT)
        rows = {row["id"]: row for key in ("atomic", "cases") for row in registry[key]}
        bound = cases.case_map(registry, catalog, "V1", {n["id"]: n for n in plan["nodes"]})
        self.assertEqual(len(bound), 22)
        for case in sorted(bound):
            with self.subTest(case=case):
                got = run(case.lower(), rules=tuple(rows[case].get("rules", ())))
                if case == "TUI-ENTRY-UNKNOWN":
                    self.assertIn("event_reply_lost", got["why"])
                else:
                    self.assertEqual(got["outcome"], executor.PASSED, got)

    @staticmethod
    def one_process(case: str) -> dict:
        """Every feature the case uses, its processes run as one."""
        used = cases.features_of(scenario(case)[1]) - {"processes"}
        return {**executor.feature_modules(used)[0], "processes": INERT}


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

    def test_a_record_no_answer_shows_is_not_judged_and_the_case_does_not_pass(self):
        # N17-DISCONNECT-NEG's settled query names the partial carrier state by digest only.
        got = run("n17-disconnect-neg")
        self.assertEqual(got["outcome"], executor.BLOCKED, got)
        self.assertIn("no answer of the scenario shows a_partial", got["why"])

    def test_a_digest_learned_before_its_record_is_held_to_it_when_the_run_ends(self):
        run_ = built_run(self, "n09-c07-pos")
        record = next(iter(run_.templates))
        run_.later[(record, "digest")] = "0" * 64
        with self.assertRaises(executor.Stop) as raised:
            run_.settle()
        self.assertEqual((raised.exception.outcome, raised.exception.record),
                         (executor.FAILED, record))
        self.assertIn("not the record an earlier answer named", raised.exception.why)

    def test_a_layer_that_rewrites_a_given_answer_fails(self):
        # What the observation mints, its instant, is the value a layer could slip past.
        root = module_root(self, "import hashlib\nfrom workenv.contracts import canonical\n"
                                 "def layer(call, inner):\n    got = inner(call)\n"
                                 "    if call.given is not None and got.get('returned'):\n"
                                 "        record = got['returned'][0]\n"
                                 "        record['observed_at'] = '2099-01-01T00:00:00Z'\n"
                                 "        got['result']['outputs'][0]['digest'] = hashlib.sha256(\n"
                                 "            canonical.encode(record)).hexdigest()\n"
                                 "    return got\n")
        _, built = scenario("n27-selection-neg")
        entries = {op: "planted:answer" for op in operations(built) if op != "source.observe"}
        (root / "planted.py").write_text((root / "planted.py").read_text()
                                         + "answer = scripted_owner.answer\n", encoding="utf-8")
        routing = executor.Routing(entries, set(), ["planted:layer"], [], False)
        got = run("n27-selection-neg", routing=routing, root=root)
        self.assertEqual((got["outcome"], got["step"], got.get("pointer")),
                         (executor.FAILED, "observe_the_selection", "/observed_at"), got)

    def test_a_refusal_that_also_answers_fails(self):
        root = module_root(self, "def answer(call):\n    got = scripted_owner.answer(call)\n"
                                 "    if 'refused' in got:\n"
                                 "        got.update(result={'kind': 'operation_result'},\n"
                                 "                   returned=[], receipt=None)\n"
                                 "    return got\n")
        _, built = scenario("n02-c01-neg")
        got = run("n02-c01-neg", routing=everything(built, "planted:answer"), root=root)
        self.assertEqual((got["outcome"], got["step"]), (executor.FAILED, "name_as_principal"),
                         got)
        self.assertIn("neither a result nor a refusal alone", got["why"])

    def test_a_replay_resubmits_the_bytes_its_step_sent(self):
        # Built again, a replayed request has the same bytes in every scenario, so what is held
        # is that the replay sends the very request and carried records its step sent.
        runs: list = []
        close = executor.Run.close

        def kept(run_):
            runs.append(run_)
            close(run_)
        with mock.patch.object(executor.Run, "close", kept):
            got = run("n01-store-pos")
        self.assertEqual(got["outcome"], executor.PASSED, got)
        sent = runs[0].sent
        for replay in ("read_carrier_back", "read_carrier_back_again"):
            self.assertIs(sent[replay][0], sent["bind_carrier"][0])
            self.assertIs(sent[replay][1], sent["bind_carrier"][1])

    def test_a_replay_that_writes_a_new_receipt_fails(self):
        self.failed("n01-store-pos", [{"step": "read_carrier_back", "path": "receipt",
                                       "pointer": "/sequence", "value": 424242}],
                    step="read_carrier_back", record="bind_carrier_receipt", pointer="/sequence")

    def test_a_settled_duplicate_that_writes_a_new_receipt_fails(self):
        self.failed("n13-c09-pos", [{"step": "accept_full_transfer_again", "path": "receipt",
                                     "pointer": "/sequence", "value": 424242}],
                    run={"features": Positive.one_process("n13-c09-pos"), "shared": True},
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
        steps = [step["name"] for step in built["steps"]]
        planted = {**copy.deepcopy(built),
                   "world": {"during": [{"step": steps[1], "runs": steps[0]}]}}
        got = run("n09-c07-pos", built=planted)
        self.assertEqual(got["outcome"], executor.BLOCKED, got)
        self.assertNotIn("step", got)
        self.assertIn("uses during", got["why"])

    def test_a_rule_whose_context_no_run_finds_is_blocked_rather_than_judged_without_it(self):
        _, built = scenario("n09-c07-pos")
        rule = "C08/grant_revision_keeps_its_grant"
        # Run where the owner is found, so without the guard the case would pass unjudged.
        got = run("n09-c07-pos", rules=(rule,))
        self.assertEqual(got["outcome"], executor.BLOCKED, got)
        self.assertNotIn("step", got)
        self.assertIn(f"applies {rule}", got["why"])


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
        # The root holds the judge's package, as the repository root does.
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        judge = root / "gates" / "workenv" / "conformance"
        judge.mkdir(parents=True)
        (judge / "executor.py").write_text("JUDGE = True\n", encoding="utf-8")
        (root / "bare.py").write_text(
            "import importlib.util\ndef answer(call):\n    try:\n"
            "        import gates.workenv.conformance.executor\n        found = True\n"
            "    except ModuleNotFoundError:\n        found = False\n"
            "    raise RuntimeError(f'judge importable: {found}, host: '\n"
            "                       f'{importlib.util.find_spec(\"host\") is not None}')\n",
            encoding="utf-8")
        _, built = scenario("n09-c07-pos")
        got = run("n09-c07-pos", routing=everything(built, "bare:answer"), root=root)
        self.assertIn("judge importable: False, host: False", got["why"])

    def test_a_git_the_caller_exported_does_not_reach_the_code_under_test(self):
        source = ("import os\ndef answer(call):\n"
                  "    assert not [k for k in os.environ if k.startswith('GIT_')], 'GIT_ leaked'\n"
                  "    return scripted_owner.answer(call)\n")
        with mock.patch.dict(os.environ, {"GIT_DIR": "/nonexistent/.git"}):
            got = self.outcome(source)
        self.assertEqual(got["outcome"], executor.PASSED, got)

    def test_an_entry_that_says_not_written_while_it_runs_fails(self):
        # Only a callable missing before anything runs blocks a case.
        got = self.outcome("import __main__\ndef answer(call):\n"
                           "    raise __main__.NotWritten('implemented, and failing')\n")
        self.assertEqual((got["outcome"], got["step"]), (executor.FAILED, "bind_alice"), got)
        self.assertIn("NotWritten: implemented, and failing", got["why"])

    def test_code_that_changes_the_drivers_signing_key_fails(self):
        root = module_root(self, "def answer(call):\n    got = scripted_owner.answer(call)\n"
                                 "    for key in (call.state.parents[2] / 'keys').glob('key*'):\n"
                                 "        if key.suffix != '.pub':\n"
                                 "            key.write_bytes(b'not a key')\n    return got\n")
        # N09-C07-POS signs nothing after its first step, so only watching the keys sees it.
        for case in ("n02-c01-pos", "n09-c07-pos"):
            with self.subTest(case=case):
                _, built = scenario(case)
                got = run(case, routing=everything(built, "planted:answer"), root=root)
                self.assertEqual((got["outcome"], got["step"]),
                                 (executor.FAILED, built["steps"][0]["name"]), got)
                self.assertIn("was changed while the code under test ran", got["why"])

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

    def test_a_request_resting_on_a_value_no_answer_returned_fails_by_name(self):
        run = self.fresh_run()
        run.pending.append("m")
        with self.assertRaises(executor.Stop) as raised:
            run.step({"name": "send", "request": "a", "carries": []})
        self.assertEqual(raised.exception.outcome, executor.FAILED)
        self.assertIn("rests on a value no answer has returned yet", raised.exception.why)

    def test_a_digest_resting_on_a_pending_value_is_learned_and_then_held(self):
        run = self.fresh_run()
        run.pending.append("m")
        self.assertIsInstance(run.materialize("b")["ref"]["digest"], executor.Unknown)
        answered = {"ref": {"digest": "c" * 64, "size": 9}}
        self.assertEqual(run.resolve(run.materialize("b"), answered, "s", "b", ""), answered)
        self.assertEqual((run.later[("a", "digest")], run.later[("a", "size")]), ("c" * 64, 9))
        run.pending.clear()
        run.learned["m"] = "f" * 64
        run.forget()
        with self.assertRaises(executor.Stop) as raised:
            run.hold("t", "a", run.materialize("a"))
        self.assertIn("not the record an earlier answer named", raised.exception.why)

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



def built_run(test: unittest.TestCase, case: str, *features: str) -> executor.Run:
    """A run of the case with these features installed and prepared, and no step taken."""
    _, built = scenario(case)
    workdir = pathlib.Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, workdir, True)
    run_ = executor.Run(copy.deepcopy(built), None, workdir, None)
    modules = executor.feature_modules(set(features))[0]
    for name in features:
        modules[name].install(run_)
    for hook in run_.prepare_hooks:
        hook(run_)
    return run_


def facts(*steps: tuple[str, str, list[str]], **records: dict) -> dict:
    """A built scenario of the records named and the steps (name, operation, carried names)."""
    requests = {f"{name}_request": {"kind": "operation_request", "operation": operation}
                for name, operation, _ in steps}
    return {"records": [{"name": name, "record": record}
                        for name, record in {**records, **requests}.items()],
            "steps": [{"name": name, "request": f"{name}_request", "carries": carried}
                      for name, _, carried in steps], "joins": []}


def git_status(checkout: pathlib.Path) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "status", "--porcelain"], cwd=checkout, env=env,
                          capture_output=True, text=True).stdout


class Clock(unittest.TestCase):
    def test_the_call_is_given_the_instant_its_step_states(self):
        root = module_root(self, "def answer(call):\n    raise RuntimeError(f'now={call.now}')\n")
        _, built = scenario("src-01")
        got = run("src-01", routing=everything(built, "planted:answer"), root=root)
        self.assertIn(f"now={built['steps'][0]['at']}", got["why"])
        _, built = scenario("n09-c07-pos")
        got = run("n09-c07-pos", routing=everything(built, "planted:answer"), root=root)
        self.assertIn("now=None", got["why"])


class Faults(unittest.TestCase):
    def planted(self, source: str, case: str = "n05-restart-pos") -> dict:
        root = module_root(self, source)
        _, built = scenario(case)
        return run(case, routing=everything(built, "planted:answer"), root=root)

    def test_a_fault_the_code_never_reaches_fails_naming_the_point_and_the_step(self):
        got = self.planted("def answer(call):\n    call.point = lambda name, answer=None: None\n"
                           "    return scripted_owner.answer(call)\n")
        self.assertEqual((got["outcome"], got["step"]), (executor.FAILED, "commit_first_revision"))
        self.assertIn("after_commit_before_return was armed on this step, and the process "
                      "answered anyway", got["why"])

    def test_an_exit_as_if_killed_without_reaching_the_point_fails(self):
        got = self.planted(
            "import os\ndef answer(call):\n    call.point = lambda name, answer=None: None\n"
            "    got = scripted_owner.answer(call)\n"
            "    if call.request['operation'] == 'source.revision.commit':\n"
            "        os._exit(70)\n    return got\n")
        self.assertEqual((got["outcome"], got["step"]), (executor.FAILED, "commit_first_revision"))
        self.assertIn("exited with status 70 without reaching its armed fault point", got["why"])

    def test_the_point_past_the_commit_must_be_handed_the_committed_answer(self):
        got = self.planted("def answer(call):\n    point = call.point\n"
                           "    call.point = lambda name, answer=None: point(name)\n"
                           "    return scripted_owner.answer(call)\n")
        self.assertEqual((got["outcome"], got["step"]), (executor.FAILED, "commit_first_revision"))
        self.assertIn("without the answer it committed", got["why"])

    def test_a_restart_that_loses_what_was_committed_fails(self):
        # Observed by a later query, which must show what was committed.
        # The failure is a difference where the committed value is shown, not a dead process.
        got = run("n05-restart-pos", [{"step": "commit_first_revision", "forget": True}])
        self.assertEqual((got["outcome"], got["step"], got.get("pointer")),
                         (executor.FAILED, "query_after_restart", "/outputs/0/digest"), got)
        # Resubmitted automatically: the resubmission must be answered with it.
        got = run("cmp-select", [{"step": "switch_repository_source_off", "forget": True}])
        self.assertEqual((got["outcome"], got["step"]),
                         (executor.FAILED, "switch_repository_source_off"), got)
        self.assertIn("states", got["why"])
        self.assertIn("pointer", got)

    def test_a_resubmission_after_a_restart_is_answered_with_what_was_committed(self):
        self.assertEqual(run("cmp-select")["outcome"], executor.PASSED)

    def test_a_step_a_later_step_observes_is_not_sent_again(self):
        log = pathlib.Path(tempfile.mkdtemp()) / "log.jsonl"
        self.addCleanup(shutil.rmtree, log.parent, True)
        _, built = scenario("n05-restart-pos")
        held = {row["name"]: row["record"] for row in built["records"]}
        ids = {s["name"]: held[s["request"]]["request_id"] for s in built["steps"]}
        got = run("n05-restart-pos", env={"SCRIPTED_LOG": str(log)})
        self.assertEqual(got["outcome"], executor.PASSED, got)
        answered = [json.loads(line).get("answer") for line in log.read_text().splitlines()]
        answered = [line for line in answered if line]
        killed = answered.index(ids["commit_first_revision"])
        self.assertEqual(answered[killed + 1], ids["query_after_restart"])

    def test_a_fault_on_a_step_the_driver_gives_is_blocked(self):
        _, built = scenario("n05-restart-pos")
        routing = everything(built)
        del routing.entries["source.revision.commit"]
        got = run("n05-restart-pos", routing=routing)
        self.assertEqual((got["outcome"], got["step"]), (executor.BLOCKED, "commit_first_revision"))

    def test_what_a_later_step_shows_is_held_to_the_answer_the_caller_never_received(self):
        # The query after the restart names the revision the killed commit wrote; the driver
        # holds the answer that commit withheld, so a query naming another revision fails there.
        got = run("n05-restart-pos", [{"step": "query_after_restart", "path": "returned/0",
                                       "pointer": "/outputs/0/digest", "value": "e" * 64}])
        self.assertEqual((got["outcome"], got["step"], got.get("pointer")),
                         (executor.FAILED, "query_after_restart", "/outputs/0/digest"), got)


class Checkout(unittest.TestCase):
    def test_the_checkout_holds_what_the_records_state_and_replaces_its_stand_ins(self):
        _, built = scenario("n27-selection-neg")
        run_ = built_run(self, "n27-selection-neg", "checkout")
        checkout = run_.checkout
        self.assertEqual(run_.cwd, checkout)
        observation = next(r["record"] for r in built["records"]
                           if r["name"] == "observe_the_selection_observation")
        for read in observation["read"]:
            data = (checkout / read["path"]).read_bytes()
            self.assertEqual(len(data), read["size"], read["path"])
        status = git_status(checkout)
        self.assertIn(" M docs/adr/0002-backups.md", status)
        self.assertIn("?? docs/adr/0003-draft.md", status)
        self.assertNotIn("0001-journal-mode.md", status)
        text = json.dumps(run_.templates)
        stated = [read["digest"] for read in observation["read"]] + ["/home/ana/work",
                                                                     "0123456789abcdef" * 2]
        for value in stated:
            self.assertNotIn(value, text)
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=checkout, env=env,
                              capture_output=True, text=True).stdout.strip()
        self.assertIn(head, text)
        self.assertIn(str(checkout), text)

    def test_a_git_the_caller_exported_does_not_reach_the_checkout(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": "/nonexistent/.git",
                                          "GIT_WORK_TREE": "/nonexistent"}):
            run_ = built_run(self, "n09-c07-pos", "checkout")
        self.assertTrue((run_.checkout / ".git").is_dir())

    def test_what_a_checkout_cannot_hold_is_blocked_by_name(self):
        for case, said in (("src-10", "selections name 3 checkouts"),
                           ("n27-c01-neg", "two contents for rules/review.md")):
            with self.subTest(case=case):
                with self.assertRaises(executor.Stop) as raised:
                    built_run(self, case, "checkout")
                self.assertEqual(raised.exception.outcome, executor.BLOCKED)
                self.assertIn(said, raised.exception.why)

    def test_a_stand_in_is_replaced_only_where_a_field_of_its_kind_holds_it(self):
        feature = executor.feature_modules({"checkout"})[0]["checkout"]
        replaced = {("path", "X"): "/built", ("commit", "C"): "HEAD", ("digest", "D"): "real"}
        stated = {"operation": "X", "checkout": "X", "branch": "C", "commit": "C",
                  "digest": "D", "label": "D", "body_digests": ["D"]}
        self.assertEqual(feature.swapped(stated, replaced),
                         {"operation": "X", "checkout": "/built", "branch": "C", "commit": "HEAD",
                          "digest": "real", "label": "D", "body_digests": ["real"]})

    def test_a_path_no_selection_names_is_left_as_stated(self):
        # SRC-02's capture claims input from a neighbouring repository, which is refused; that
        # path is not a second checkout.
        run_ = built_run(self, "src-02", "checkout")
        self.assertIn("/home/ana/neighbouring-repository", json.dumps(run_.templates))
        self.assertNotIn("/home/ana/work\"", json.dumps(run_.templates))
        self.assertEqual(run("src-02")["outcome"], executor.PASSED)

    def test_the_first_state_is_what_records_state_before_an_edit(self):
        # N09-C07-NEG edits rules/review.md and adds rules/draft.md after its first steps; an
        # observation after the edits describes them, not the checkout the person started in.
        run_ = built_run(self, "n09-c07-neg", "checkout")
        self.assertFalse((run_.checkout / "rules" / "draft.md").exists())
        self.assertEqual(git_status(run_.checkout), "")
        self.assertEqual(len((run_.checkout / "rules" / "review.md").read_bytes()), 2048)

    def test_a_file_digest_the_owner_reads_is_the_digest_of_the_file(self):
        got = run("src-01", [{"step": "observe_working_tree", "path": "returned/0",
                              "pointer": "/read/0/digest", "value": "e" * 64}])
        self.assertEqual((got["outcome"], got["step"], got.get("pointer")),
                         (executor.FAILED, "observe_working_tree", "/read/0/digest"), got)

    def test_a_file_the_code_writes_is_not_in_the_first_state(self):
        run_ = built_run(self, "cmp-order", "checkout")
        self.assertFalse((run_.checkout / "decisions" / "records.jsonl").exists())
        self.assertTrue((run_.checkout / "rules" / "review.md").is_file())

    def test_a_given_read_of_a_file_states_the_digest_of_the_file(self):
        _, built = scenario("src-01")
        routing = everything(built)
        del routing.entries["source.observe"]
        given, seen = executor.Run.given, []

        def watched(run_, step):
            answer = given(run_, step)
            for record in answer.get("returned", []):
                for read in record.get("read", []) if isinstance(record, dict) else []:
                    target = run_.checkout / read["path"]
                    if read.get("read") == "tree" and target.is_file():
                        seen.append(read["digest"] == hashlib.sha256(
                            target.read_bytes()).hexdigest())
            return answer
        # The scripted owner does not learn what a given step answered, so later steps it
        # serves may differ; what is held here is the given answer itself.
        with mock.patch.object(executor.Run, "given", watched):
            run("src-01", routing=routing)
        self.assertTrue(seen)
        self.assertTrue(all(seen), seen)

    def test_a_file_the_code_says_it_wrote_is_the_file_at_its_path(self):
        _, built = scenario("cmp-order")
        step = next(s for s in built["steps"] if s["name"] == "publish_repo_dec")
        index = step["returns"].index("repo_dec_manifest_2")
        got = run("cmp-order", [{"step": "publish_repo_dec", "path": f"returned/{index}",
                                 "pointer": "/members/0/digest", "value": "e" * 64}])
        self.assertEqual((got["outcome"], got["step"], got.get("pointer")),
                         (executor.FAILED, "publish_repo_dec", "/members/0"), got)
        self.assertIn("says the code wrote decisions/records.jsonl", got["why"])

    def test_a_reader_outside_the_selection_meets_the_file_it_must_not_read(self):
        # N27-SELECTION-NEG's checkout holds docs/adr-private/notes.md beside docs/adr; a
        # reader matching paths by prefix reads it, and the observation it returns fails.
        root = module_root(self, (
            "import hashlib, pathlib\nfrom workenv.contracts import canonical\n"
            "def answer(call):\n    got = scripted_owner.answer(call)\n"
            "    if call.request['operation'] != 'source.observe':\n        return got\n"
            "    observation = got['returned'][0]\n"
            "    for path in sorted(pathlib.Path.cwd().rglob('*')):\n"
            "        name = path.relative_to(pathlib.Path.cwd()).as_posix()\n"
            "        if path.is_file() and name.startswith('docs/adr') and '/adr/' not in name:\n"
            "            data = path.read_bytes()\n"
            "            observation['read'].append({'read': 'tree', 'path': name, 'root': 0,\n"
            "                'digest': hashlib.sha256(data).hexdigest(), 'size': len(data),\n"
            "                'state': 'untracked'})\n"
            "    got['result']['outputs'][0]['digest'] = hashlib.sha256(\n"
            "        canonical.encode(observation)).hexdigest()\n    return got\n"))
        _, built = scenario("n27-selection-neg")
        got = run("n27-selection-neg", routing=everything(built, "planted:answer"), root=root,
                  rules=("C01/read_within_selection",))
        self.assertEqual((got["outcome"], got["step"]), (executor.FAILED, "observe_the_selection"),
                         got)


    def test_a_preparation_records_the_checkout_it_was_composed_in_where_none_is_bound(self):
        # N09-C07-POS composes twice before it binds a repository: the directory it works in
        # stands for the checkout the driver builds, and a scenario with a preparation builds one.
        _, built = scenario("n09-c07-pos")
        self.assertIn("checkout", cases.features_of(built))
        run_ = built_run(self, "n09-c07-pos", "checkout")
        text = json.dumps(run_.templates)
        self.assertNotIn('"/workspace"', text)
        self.assertEqual(run_.templates["empty_preparation"]["observed"],
                         {"locator": str(run_.checkout)})
        got = run("n09-c07-pos", [{"step": "compose_nothing", "path": "returned/0",
                                   "pointer": "/observed/locator", "value": "/workspace"}])
        self.assertEqual((got["outcome"], got["step"], got.get("pointer")),
                         (executor.FAILED, "compose_nothing", "/observed/locator"), got)

    def test_a_preparation_or_an_admission_into_a_repository_alone_needs_a_checkout(self):
        preparation = {"kind": "preparation", "observed": {"locator": "/workspace"}}
        admission = {"kind": "source_request",
                     "destination": {"home_mode": "repository_authored"}}
        managed = {"kind": "source_request", "destination": {"home_mode": "managed"}}
        for records, wanted in (({"p": preparation}, True), ({"a": admission}, True),
                                ({"m": managed}, False)):
            with self.subTest(records=records):
                self.assertEqual(cases.reads_a_checkout(facts(**records)), wanted)

    def test_a_remote_a_preparation_observed_is_not_a_directory_the_driver_builds(self):
        feature = executor.feature_modules({"checkout"})[0]["checkout"]
        templates = {"here": {"kind": "preparation", "observed": {"locator": "/workspace"}},
                     "there": {"kind": "preparation",
                               "observed": {"locator": "https://example.org/team/rules.git"}}}
        self.assertEqual(feature.worked_in(templates), {"/workspace"})

    def test_a_revision_admitted_into_a_repository_is_read_from_its_files(self):
        # N09-C07-POS admits the repository's rules revision into the repository itself, so its
        # member is a file of the checkout; N09-C07-NEG's later publication of its memory file is
        # written by the code, and only the admitted content is the first state.
        run_ = built_run(self, "n09-c07-pos", "checkout")
        stated = run_.templates["repo_rules_rev_submitted"]["members"][0]
        data = (run_.checkout / stated["path"]).read_bytes()
        self.assertEqual((len(data), hashlib.sha256(data).hexdigest()),
                         (stated["size"], stated["digest"]))
        built_run(self, "n09-c07-neg", "checkout")


class RevisionBytes(unittest.TestCase):
    def test_a_member_stated_by_digest_alone_stands_for_bytes_its_commit_carries(self):
        # CMP-SELECT commits the Team's managed revision stating each member by digest alone.
        _, built = scenario("cmp-select")
        stated = cases.stated_revision_members(built)
        self.assertTrue(stated)
        self.assertIn("revision_bytes", cases.features_of(built))
        run_ = built_run(self, "cmp-select", "revision_bytes")
        literals = {executor.at(next(r["record"] for r in built["records"] if r["name"] == name),
                                pointer)[1]["digest"] for name, pointer in stated}
        text = json.dumps(run_.templates)
        for literal in literals:
            self.assertNotIn(literal, text)
        for name, pointer in stated:
            member = executor.at(run_.templates[name], pointer)[1]
            data = run_.revision_bytes[member["digest"]]
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest()),
                             (member["size"], member["digest"]))
        feature = executor.feature_modules({"revision_bytes"})[0]["revision_bytes"]
        commit = next(step for step in built["steps"] if step["name"] == "commit_team_rules_r1")
        other = next(step for step in built["steps"] if step["name"] == "first_start")
        manifests = [run_.templates[name] for name in commit["carries"]]
        sent = {"carried": manifests, "members": {}}
        feature.attach(run_, commit, sent)
        self.assertEqual(set(sent["members"]),
                         {m["digest"] for record in manifests for m in record["members"]})
        self.assertEqual({hashlib.sha256(data).hexdigest() for data in sent["members"].values()},
                         set(sent["members"]))
        elsewhere = {"carried": manifests, "members": {}}
        feature.attach(run_, other, elsewhere)
        self.assertEqual(elsewhere["members"], {})

    def test_a_member_whose_text_digest_or_file_is_stated_otherwise_is_left_alone(self):
        # SRC-01 authors its revision in the repository, and DEL-PERSONAL gives its member's text.
        for case in ("src-01", "del-personal"):
            with self.subTest(case=case):
                self.assertEqual(cases.stated_revision_members(scenario(case)[1]), [])

    def test_only_a_revision_its_author_commits_or_admits_is_stated_and_not_a_file_it_reads(self):
        def members(*paths):
            return {"kind": "source_manifest", "source_id": "src_a",
                    "members": [{"path": path, "digest": path, "size": 1} for path in paths]}
        built = facts(("commit", "source.revision.commit", ["committed"]),
                      ("stage", "collection.change", ["drafted"]),
                      committed=members("rules/a.md", "docs/read.md"),
                      drafted=members("rules/b.md"),
                      observed={"kind": "source_observation", "read": [
                          {"read": "tree", "path": "docs/read.md"}]})
        self.assertEqual(cases.stated_revision_members(built), [("committed", "/members/0")])


class FileEdit(unittest.TestCase):
    def test_an_edit_lands_before_its_step_and_nowhere_else(self):
        run_ = built_run(self, "n27-selection-neg", "checkout", "event_file_edit")
        target = run_.checkout / "docs" / "adr"
        steps = {s["name"]: s for s in run_.built["steps"]}
        for hook in run_.before_hooks:
            hook(run_, steps["observe_the_selection"])
        self.assertTrue(target.is_dir())
        for hook in run_.before_hooks:
            hook(run_, steps["observe_after_the_directory_is_gone"])
        self.assertFalse(target.exists())
        run_ = built_run(self, "src-01", "checkout", "event_file_edit")
        event = run_.built["world"]["events"][0]
        for hook in run_.before_hooks:
            hook(run_, {"name": event["before"]})
        self.assertEqual((run_.checkout / event["path"]).read_text(), event["bytes"])

    def test_an_edit_reaching_outside_the_checkout_fails(self):
        run_ = built_run(self, "src-01", "checkout", "event_file_edit")
        run_.built["world"]["events"][0]["path"] = "../outside.md"
        run_.before_hooks.clear()
        executor.feature_modules({"event_file_edit"})[0]["event_file_edit"].install(run_)
        with self.assertRaises(executor.Stop) as raised:
            run_.before_hooks[0](run_, {"name": run_.built["world"]["events"][0]["before"]})
        self.assertEqual(raised.exception.outcome, executor.FAILED)
        self.assertIn("outside the checkout", raised.exception.why)

    def test_an_absent_edit_removes_a_single_file(self):
        run_ = built_run(self, "cmp-qualified", "checkout", "event_file_edit")
        target = run_.checkout / "rules" / "review.md"
        self.assertTrue(target.is_file())
        for hook in run_.before_hooks:
            hook(run_, {"name": "start_with_an_unavailable_winner"})
        self.assertFalse(target.exists())
        self.assertTrue((run_.checkout / "rules").is_dir())


class Rules(unittest.TestCase):
    RULE = "C01/read_within_selection"

    def test_a_rule_is_applied_to_what_code_in_scope_wrote(self):
        got = run("n27-selection-neg", rules=(self.RULE,))
        self.assertEqual(got["outcome"], executor.PASSED, got)
        self.assertIn(f"{self.RULE} held on 2 record(s)", got["why"])

    def test_a_record_breaking_the_rule_fails_naming_it(self):
        kind, store, _ = oracles.RULES[self.RULE]
        with mock.patch.dict(oracles.RULES, {self.RULE: (kind, store,
                                                         lambda record, context: ["/read/0"])}):
            got = run("n27-selection-neg", rules=(self.RULE,))
        self.assertEqual((got["outcome"], got["pointer"]), (executor.FAILED, "/read/0"), got)
        self.assertIn(f"breaks {self.RULE}", got["why"])

    def test_the_rule_reads_the_selection_the_record_names(self):
        seen = []
        kind, store, oracle = oracles.RULES[self.RULE]

        def watched(record, context):
            named = hashlib.sha256(canonical.encode(context["selection"])).hexdigest()
            seen.append(named == record["selection_digest"])
            return oracle(record, context)
        with mock.patch.dict(oracles.RULES, {self.RULE: (kind, store, watched)}):
            got = run("n27-selection-neg", rules=(self.RULE,))
        self.assertEqual(got["outcome"], executor.PASSED, got)
        self.assertEqual(seen, [True, True])

    def test_a_given_answer_is_not_judged_by_a_rule(self):
        _, built = scenario("n27-selection-neg")
        routing = everything(built)
        del routing.entries["source.observe"]
        got = run("n27-selection-neg", routing=routing, rules=(self.RULE,))
        self.assertIn(f"{self.RULE} held on 0 record(s)", got["why"])


if __name__ == "__main__":
    unittest.main()
