"""Probing delivery routes: `capability.probe` runs the installed host through its adapter, and
the route's carrier hands the recipient the probe's code: the host's launch instructions, a
kind of child defined at launch, or the hook the host runs.

The host here is `fakehost.py`, installed as `claude` and `codex` on a PATH of the test's own;
the probe, each adapter's drive and `hook.py` are the real code. The real hosts are probed on
the machine itself, and the record of that run says what they did.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest

import bench
from test_sources import INSTANT, Base, gaps

from workenv import hosts, journal
from workenv.contracts import c03, c12
from workenv.contracts.schema import STORED
from workenv.hosts import codex, hook, probes

PROBE = "capability.probe"
FAKE = pathlib.Path(__file__).with_name("fakehost.py")
VERSION = "9.9.9"
EVERY = {host: sorted(adapter.routes) for host, adapter in hosts.adapters().items()}


def wire_of(host: str, recipient: str | None) -> dict:
    """The wire a probe of the host's route to the recipient states, or the hook's where the
    host declares none."""
    adapter = hosts.adapter_for(host)
    route = adapter.routes.get(recipient) if adapter is not None else None
    return route.wire if route is not None else hosts.WIRES["hook"]


class Hosts(unittest.TestCase):
    """A PATH holding the fake hosts, and the environment a probe runs in."""

    def setUp(self):
        # A fake host answers at once, so a probe that waits out its time has hung.
        self.addCleanup(setattr, probes, "TIMEOUT", probes.TIMEOUT)
        probes.TIMEOUT = 20
        self.fakes = tempfile.TemporaryDirectory(prefix="workenv-probe-")
        root = pathlib.Path(self.fakes.name)
        (root / "bin").mkdir()
        for name in ("claude", "codex"):
            (root / "bin" / name).write_text(f"#!{sys.executable}\n" + FAKE.read_text())
            (root / "bin" / name).chmod(0o755)
        self.log = root / "log.jsonl"
        self.environ = {"PATH": f"{root / 'bin'}{os.pathsep}{os.environ['PATH']}",
                        "HOME": str(root), "FAKE_HOST_LOG": str(self.log),
                        "FAKE_HOST_VERSION": VERSION, "FAKE_HOST_MODE": "obey",
                        "FAKE_HOST_TRUST": "all", "CLAUDECODE": "1",
                        "CLAUDE_CODE_SESSION_ID": "outer", "CODEX_THREAD_ID": "outer"}
        self.work = root / "work"
        self.work.mkdir()

    def tearDown(self):
        self.fakes.cleanup()

    def probe(self, host: str, recipient: str, version: str = VERSION, **environ) -> tuple:
        asked = {"kind": "capability_probe", "schema": 1,
                 "client": {"name": host, "version": version}, "wire": wire_of(host, recipient),
                 "capability": hosts.CAPABILITY[recipient]}
        pathlib.Path(f"{self.log}.calls").unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(dir=self.work) as workdir:
            return probes.probed(asked, {**self.environ, **environ},
                                 pathlib.Path(workdir).resolve())

    def drive(self, host: str, drive):
        """The adapter of the host with another drive, for the length of one probe."""
        adapter = hosts.adapter_for(host)
        original = adapter.drive
        object.__setattr__(adapter, "drive", drive)
        self.addCleanup(object.__setattr__, adapter, "drive", original)

    def calls(self) -> list[dict]:
        """The prompts the fake Claude Code was given and the requests the fake Codex answered,
        in order."""
        calls = pathlib.Path(f"{self.log}.calls")
        if not calls.is_file():
            return []
        return [json.loads(line) for line in calls.read_text().splitlines()]

    def asked(self) -> list[str]:
        """What the probe asked the host: Claude Code's prompts and Codex's turns."""
        return [call["params"]["text"] if call["method"] == "prompt" else
                call["params"]["input"][0]["text"] for call in self.calls()
                if call["method"] in ("prompt", "turn/start")]

    def runs(self) -> list[dict]:
        if not self.log.is_file():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()
                if json.loads(line)["argv"] != ["--version"]]


class Probing(Hosts):
    def test_a_route_that_hands_the_recipient_the_code_worked_on_every_declared_route(self):
        for host, recipients in EVERY.items():
            for recipient in recipients:
                with self.subTest(host=host, recipient=recipient):
                    found, ran_under = self.probe(host, recipient)
                    self.assertEqual((found["offered"], found["outcome"]), (True, "worked"),
                                     found["observed"])
                    route = hosts.adapter_for(host).routes[recipient]
                    event = route.event if host == "claude-code" else \
                        route.event[0].lower() + route.event[1:]
                    self.assertIn(probes.hook(event, probes.command(host), True), ran_under)

    def test_a_host_that_takes_nothing_it_was_handed_refused_every_route(self):
        for host, recipients in EVERY.items():
            for recipient in recipients:
                with self.subTest(host=host, recipient=recipient):
                    found, _ = self.probe(host, recipient, FAKE_HOST_MODE="ignore")
                    self.assertEqual((found["offered"], found["outcome"]), (True, "refused"))

    def test_a_launch_or_definition_route_is_carried_at_launch_and_never_by_the_hook(self):
        # The host runs every hook but reads neither its launch instructions nor definitions.
        for host, adapter in hosts.adapters().items():
            for recipient, route in adapter.routes.items():
                with self.subTest(host=host, recipient=recipient):
                    found, _ = self.probe(host, recipient, FAKE_HOST_MODE="nolaunch")
                    self.assertEqual(found["outcome"],
                                     "worked" if route.carrier == "hook" else "refused",
                                     found["observed"])
        self.assertEqual({route.carrier for adapter in hosts.adapters().values()
                          for route in adapter.routes.values()}, set(hosts.WIRES))

    def test_a_host_that_drops_its_launch_instructions_on_compaction_refused_rehydration(self):
        for host in EVERY:
            with self.subTest(host=host):
                found, _ = self.probe(host, "rehydrated", FAKE_HOST_MODE="forget")
                self.assertEqual(found["outcome"], "refused")
                found, _ = self.probe(host, "new", FAKE_HOST_MODE="forget")
                self.assertEqual(found["outcome"], "worked")

    def test_a_child_takes_its_code_from_its_kinds_definition_alone(self):
        handing = probes.handed("").removesuffix(" .")
        for host in EVERY:
            with self.subTest(host=host):
                self.log.unlink(missing_ok=True)
                found, _ = self.probe(host, "child")
                self.assertEqual(found["outcome"], "worked")
                self.assertIn("definition of the kind", found["observed"])
                [run] = self.runs()
                self.assertEqual([part for part in run["argv"] if handing in part], [],
                                 "the code is in no argument, only in a definition's file")
        # The same reading finds the code where Codex takes it inline, at launch.
        self.log.unlink(missing_ok=True)
        self.probe("codex", "new")
        [run] = self.runs()
        self.assertEqual(len([part for part in run["argv"] if handing in part]), 1)

    def test_a_code_the_hook_did_not_hand_over_does_not_count(self):
        for host in EVERY:
            with self.subTest(host=host):
                found, _ = self.probe(host, "current", FAKE_HOST_MODE="stale")
                self.assertEqual(found["outcome"], "refused")

    def test_a_host_that_gives_no_reply_did_not_respond(self):
        for host, recipients in EVERY.items():
            for recipient in recipients:
                for mode in ("silent", "error"):
                    with self.subTest(host=host, recipient=recipient, mode=mode):
                        found, _ = self.probe(host, recipient, FAKE_HOST_MODE=mode)
                        self.assertEqual((found["offered"], found["outcome"]),
                                         (True, "no_response"))

    def test_a_session_that_could_not_be_compacted_did_not_respond_and_was_not_asked(self):
        # Refused at once, not after the probe's time has run out.
        for host in EVERY:
            with self.subTest(host=host):
                self.log.unlink(missing_ok=True)
                began = time.monotonic()
                found, _ = self.probe(host, "rehydrated", FAKE_HOST_MODE="nocompact")
                self.assertLess(time.monotonic() - began, 10)
                self.assertEqual(found["outcome"], "no_response")
                asked = self.asked()
                self.assertNotIn(probes.ASK, asked)

    def test_a_compaction_accepted_and_then_failed_or_not_done_qualifies_nothing(self):
        # Asked after a compaction that did not happen, the session still holds its launch
        # instructions and would give the code: only a compaction the host confirmed counts.
        for host in EVERY:
            for mode in ("compactfails", "compactquiet"):
                with self.subTest(host=host, mode=mode):
                    self.log.unlink(missing_ok=True)
                    found, _ = self.probe(host, "rehydrated", FAKE_HOST_MODE=mode)
                    self.assertEqual((found["offered"], found["outcome"]),
                                     (True, "no_response"))
                    self.assertIn("Before the question:", found["observed"])
                    self.assertNotIn(probes.ASK, self.asked())
        found, _ = self.probe("codex", "rehydrated", FAKE_HOST_MODE="compactfails")
        self.assertIn("did not compact the conversation", found["observed"])
        self.assertIn("compaction failed", found["observed"], "Codex's own reason is kept")
        found, _ = self.probe("claude-code", "rehydrated", FAKE_HOST_MODE="compactquiet")
        self.assertIn("did not compact the conversation", found["observed"])
        # A compaction reported and then failed is no compaction either, nor one Codex reported
        # of another conversation before failing this one's (r10-0).
        for mode in ("compactitemfails", "crosscompact", "stalecompact"):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                found, _ = self.probe("codex", "rehydrated", FAKE_HOST_MODE=mode)
                self.assertEqual(found["outcome"], "no_response")
                self.assertIn("did not compact the conversation", found["observed"])
                self.assertNotIn(probes.ASK, self.asked())

    def test_a_turn_codex_ends_other_than_completed_gives_no_reply(self):
        for mode in ("refusequiet", "saidinterrupted"):
            with self.subTest(mode=mode):
                found, _ = self.probe("codex", "new", FAKE_HOST_MODE=mode)
                self.assertEqual(found["outcome"], "no_response")

    def test_a_reply_in_another_conversation_or_turn_is_not_the_probe_s(self):
        # Codex reports the code in a completed turn that is not the one the probe started, then
        # the probe's own turn replies NONE: that reply is the probe's answer (r10-0).
        for mode in ("crossturn", "staleturn"):
            for recipient in ("new", "current"):
                with self.subTest(mode=mode, recipient=recipient):
                    found, _ = self.probe("codex", recipient, FAKE_HOST_MODE=mode)
                    self.assertEqual(found["outcome"], "refused", found["observed"])
        for host in EVERY:
            with self.subTest(host=host):
                found, _ = self.probe(host, "rehydrated")
                self.assertEqual(found["outcome"], "worked", found["observed"])

    def test_a_codex_turn_that_did_not_end_gave_no_reply(self):
        found, _ = self.probe("codex", "new", FAKE_HOST_MODE="noend")
        self.assertEqual(found["outcome"], "no_response")

    def test_a_codex_turn_given_up_keeps_codex_s_own_reason(self):
        # As Codex 0.158.0 did on 2026-09-30 for a configured model the account is not offered:
        # the provider's message, unwrapped from the JSON Codex passes on.
        said = ("Codex ended the turn with an error: The 'gpt-6.1-sol' model is not supported "
                "when using Codex with a ChatGPT account.")
        for mode in ("refuse", "refusenoend", "refusequiet"):
            for recipient in ("new", "rehydrated"):
                with self.subTest(mode=mode, recipient=recipient):
                    found, _ = self.probe("codex", recipient, FAKE_HOST_MODE=mode)
                    self.assertEqual(found["outcome"], "no_response")
                    self.assertIn(said, found["observed"])

    def test_an_error_codex_retries_or_a_turn_it_answered_after_is_not_its_reason(self):
        found, _ = self.probe("codex", "new", FAKE_HOST_MODE="retrysilent")
        self.assertEqual(found["outcome"], "no_response")
        self.assertNotIn("error", found["observed"])
        # A rehydrated session's first turn given up, and the question after it answered.
        found, _ = self.probe("codex", "rehydrated", FAKE_HOST_MODE="refusefirst")
        self.assertEqual(found["outcome"], "worked")
        self.assertNotIn("error", found["observed"])

    def test_codex_s_reason_is_its_own_words_where_it_passes_on_no_provider_error(self):
        self.assertEqual(codex.reason({"message": "stream disconnected"}), "stream disconnected")
        self.assertEqual(codex.reason({"message": '{"detail": "x"}'}), '{"detail": "x"}')
        self.assertEqual(codex.reason(None), "no reason given")

    def test_codex_starting_no_conversation_did_not_respond_and_asked_nothing(self):
        found, _ = self.probe("codex", "new", FAKE_HOST_MODE="nothread")
        self.assertEqual(found["outcome"], "no_response")
        self.assertIn("did not start a conversation", found["observed"])
        self.assertEqual(self.asked(), [])

    def test_codex_listing_no_hooks_did_not_respond_and_asked_nothing(self):
        found, ran_under = self.probe("codex", "new", FAKE_HOST_MODE="nolist")
        self.assertEqual((found["offered"], found["outcome"], ran_under),
                         (True, "no_response", []))
        self.assertEqual([call["method"] for call in self.calls()],
                         ["initialize", "initialized", "hooks/list"])

    def test_every_run_gives_the_host_every_declared_route_in_its_own_place(self):
        for host, recipients in EVERY.items():
            groups = hosts.adapter_for(host).groups(probes.command(host))
            for recipient in recipients:
                with self.subTest(host=host, recipient=recipient):
                    self.log.unlink(missing_ok=True)
                    self.probe(host, recipient)
                    runs = self.runs()
                    self.assertTrue(runs)
                    for run in runs:
                        self.assertEqual(run["groups"], groups)

    def test_claude_runs_on_no_setting_sources_and_keeps_a_session_only_to_compact_it(self):
        for recipient in EVERY["claude-code"]:
            with self.subTest(recipient=recipient):
                self.log.unlink(missing_ok=True)
                self.probe("claude-code", recipient)
                for run in self.runs():
                    argv = run["argv"]
                    self.assertEqual(argv[argv.index("--setting-sources") + 1], "")
                    self.assertEqual("--no-session-persistence" in argv,
                                     recipient != "rehydrated")

    def test_codex_conversations_keep_no_session_and_change_nothing(self):
        for recipient in EVERY["codex"]:
            with self.subTest(recipient=recipient):
                self.log.unlink(missing_ok=True)
                self.probe("codex", recipient)
                [opened] = [call["params"] for call in self.calls()
                            if call["method"] == "thread/start"]
                self.assertEqual((opened["ephemeral"], opened["sandbox"],
                                  opened["approvalPolicy"]), (True, "read-only", "never"))

    def test_a_rehydrated_codex_session_is_compacted_before_it_is_asked(self):
        found, _ = self.probe("codex", "rehydrated")
        self.assertEqual(found["outcome"], "worked")
        calls = self.calls()
        self.assertEqual([call["method"] for call in calls],
                         ["initialize", "initialized", "hooks/list", "thread/start", "turn/start",
                          "thread/compact/start", "turn/start"])
        self.assertEqual(calls[-1]["params"]["input"][0]["text"], probes.ASK)

    def test_a_child_is_asked_for_through_the_session(self):
        for host in EVERY:
            with self.subTest(host=host):
                self.log.unlink(missing_ok=True)
                self.probe(host, "child")
                asked = self.asked()
                self.assertEqual(asked, [probes.ASK_CHILD])

    def test_an_adapter_that_cannot_drive_its_host_is_unsupported(self):
        self.drive("claude-code", None)
        found, _ = self.probe("claude-code", "new")
        self.assertEqual((found["offered"], found["outcome"]), (False, "unsupported"))
        self.assertFalse(self.log.exists())

    def test_an_adapter_that_cannot_launch_its_host_is_unsupported_on_what_launch_carries(self):
        adapter = hosts.adapter_for("codex")
        original = adapter.launch
        object.__setattr__(adapter, "launch", None)
        self.addCleanup(object.__setattr__, adapter, "launch", original)
        for recipient, route in adapter.routes.items():
            with self.subTest(recipient=recipient):
                self.log.unlink(missing_ok=True)
                found, _ = self.probe("codex", recipient)
                self.assertEqual(found["outcome"],
                                 "worked" if route.carrier == "hook" else "unsupported")
                self.assertEqual(self.runs() != [], route.carrier == "hook")

    def test_another_version_or_no_installed_host_is_unreachable_and_nothing_runs(self):
        for host in EVERY:
            with self.subTest(host=host):
                found, ran_under = self.probe(host, "new", version="1.0.0")
                self.assertEqual((found["offered"], found["outcome"], ran_under),
                                 (False, "unreachable", []))
                self.assertIn(VERSION, found["observed"])
                found, _ = self.probe(host, "new", PATH="/nonexistent")
                self.assertEqual((found["offered"], found["outcome"]), (False, "unreachable"))
        self.assertEqual(self.runs(), [])

    def test_a_route_no_adapter_declares_is_unsupported_and_nothing_runs(self):
        adapter = hosts.adapter_for("codex")
        original = adapter.routes
        object.__setattr__(adapter, "routes", {r: v for r, v in original.items() if r != "child"})
        self.addCleanup(object.__setattr__, adapter, "routes", original)
        for host, recipient in (("codex", "child"), ("a-host-nobody-wrote", "new")):
            with self.subTest(host=host):
                found, ran_under = self.probe(host, recipient)
                self.assertEqual((found["offered"], found["outcome"], ran_under),
                                 (False, "unsupported", []))
        self.assertFalse(self.log.exists())

    def test_a_rehydrated_claude_session_is_one_run_given_each_prompt_in_turn(self):
        # Launch instructions are given to a process, so a second run would be handed them anew.
        found, _ = self.probe("claude-code", "rehydrated")
        self.assertEqual(found["outcome"], "worked")
        [run] = self.runs()
        self.assertEqual(self.asked(), ["Reply OK.", "/compact", probes.ASK])
        argv = run["argv"]
        self.assertEqual(argv[argv.index("--input-format") + 1], "stream-json")
        self.assertNotIn("--resume", argv)
        session = argv[argv.index("--session-id") + 1]
        self.probe("claude-code", "rehydrated")
        self.assertNotIn(session, self.runs()[1]["argv"])

    def test_codex_records_every_hook_it_would_run_and_an_untrusted_hook_as_not(self):
        found, ran_under = self.probe("codex", "current", FAKE_HOST_TRUST="")
        self.assertEqual(found["outcome"], "refused")
        self.assertIn("/hooks", found["observed"])
        command = probes.command("codex")
        self.assertEqual([(hook["event"], hook["enabled"]) for hook in ran_under],
                         [("stop", True), ("stop", True), ("sessionStart", False),
                          ("userPromptSubmit", False), ("subagentStart", False)])
        self.assertEqual([hook["handler_digest"] for hook in ran_under[2:]],
                         [hashlib.sha256(command.encode("utf-8")).hexdigest()] * 3)

    def test_a_hook_route_is_refused_when_its_own_place_is_untrusted_and_no_other_route_is(self):
        found, ran_under = self.probe("codex", "current",
                                      FAKE_HOST_TRUST="sessionStart:startup,sessionStart:compact")
        self.assertEqual(found["outcome"], "refused")
        self.assertIn("/hooks", found["observed"])
        self.assertIn(probes.hook("sessionStart", probes.command("codex"), True), ran_under)
        found, _ = self.probe("codex", "current", FAKE_HOST_TRUST="userPromptSubmit:")
        self.assertEqual((found["outcome"], "/hooks" in found["observed"]), ("worked", False))
        for recipient in ("new", "rehydrated", "child"):
            with self.subTest(recipient=recipient):
                found, _ = self.probe("codex", recipient, FAKE_HOST_TRUST="")
                self.assertEqual((found["outcome"], "/hooks" in found["observed"]),
                                 ("worked", False))

    def test_the_host_runs_as_a_session_of_its_own_with_the_job_it_serves(self):
        for host in EVERY:
            self.probe(host, "new")
        runs = self.runs()
        self.assertEqual(sorted({run["host"] for run in runs}), ["claude", "codex"])
        for run in runs:
            adapter = hosts.adapter_for({"claude": "claude-code"}.get(run["host"], run["host"]))
            self.assertEqual((set(run["nested"]) & set(adapter.nested), run["job"]),
                             (set(), True))

    def test_what_was_observed_is_kept_within_its_bound(self):
        long = probes.Run(None, [], "x" * 5000)
        self.drive("claude-code", lambda *arguments: long)
        found, _ = self.probe("claude-code", "new")
        self.assertEqual(len(found["observed"]), probes.OBSERVED)

    def test_a_host_that_cannot_start_or_does_not_finish_ran_nothing(self):
        slow = [sys.executable, "-c", "import time; time.sleep(5)"]
        self.assertIsNone(probes.ran(slow, self.work, dict(os.environ), timeout=0.2))
        self.assertIsNone(probes.ran([str(self.work / "missing")], self.work, dict(os.environ)))
        missing = codex.drive("new", str(self.work / "missing"), "c", [], self.work, {})
        self.assertEqual((missing.reply, missing.hooks), (None, []))


class Hook(unittest.TestCase):
    def test_it_hands_the_text_only_to_the_recipient_its_job_names_on_a_route_it_carries(self):
        for host, adapter in hosts.adapters().items():
            for recipient, route in adapter.routes.items():
                with self.subTest(host=host, recipient=recipient):
                    event = {"hook_event_name": route.event, "session_id": "s"}
                    if route.source is not None:
                        event["source"] = route.source
                    printed = hook.answer(host, event, {"recipient": recipient, "text": "T"})
                    self.assertEqual(printed, adapter.output(event, "T")
                                     if route.carrier == "hook" else None)
                    for other in set(adapter.routes) - {recipient}:
                        self.assertIsNone(hook.answer(host, event,
                                                      {"recipient": other, "text": "T"}))
        self.assertIsNone(hook.answer("a-host-nobody-wrote", {"hook_event_name": "SessionStart"},
                                      {"recipient": "new", "text": "T"}))

    def run_hook(self, event: str, environ: dict) -> subprocess.CompletedProcess:
        host = [] if environ.pop("NO_HOST", None) else ["claude-code"]
        with tempfile.TemporaryDirectory() as cwd:
            done = subprocess.run([sys.executable, str(probes.HOOK), *host], cwd=cwd,
                                  input=event, capture_output=True, text=True,
                                  env={"PATH": os.environ["PATH"], **environ})
            self.assertEqual(os.listdir(cwd), [])
        return done

    def test_run_by_its_host_it_prints_the_output_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            job = pathlib.Path(directory) / "job.json"
            job.write_text(json.dumps({"recipient": "current", "text": "T"}))
            event = {"hook_event_name": "UserPromptSubmit", "session_id": "s"}
            done = self.run_hook(json.dumps(event), {hook.JOB: str(job)})
            other = self.run_hook(json.dumps({"hook_event_name": "SubagentStart"}),
                                  {hook.JOB: str(job)})
            self.assertEqual(os.listdir(directory), ["job.json"])
        self.assertEqual((done.returncode, done.stdout.strip()),
                         (0, hosts.adapter_for("claude-code").output(event, "T")))
        self.assertEqual((other.returncode, other.stdout), (0, ""))

    def test_it_never_fails_its_host(self):
        event = json.dumps({"hook_event_name": "UserPromptSubmit"})
        job = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory())) / "job.json"
        job.write_text(json.dumps({"recipient": "current", "text": "T"}))
        for stdin, environ, error in ((event, {}, "KeyError"),
                                      (event, {hook.JOB: str(job), "NO_HOST": "1"},
                                       "IndexError"),
                                      ("not json", {hook.JOB: "/nonexistent"}, "JSONDecodeError"),
                                      (event, {hook.JOB: "/nonexistent"}, "FileNotFoundError")):
            with self.subTest(error=error):
                done = self.run_hook(stdin, environ)
                self.assertEqual((done.returncode, done.stdout), (0, ""))
                self.assertIn(error, done.stderr)

    def test_its_command_is_the_same_bytes_on_every_run_wherever_it_is_installed(self):
        self.assertEqual(probes.command("codex"), probes.command("codex"))
        self.assertEqual(probes.JOB, hook.JOB)
        self.assertTrue(probes.HOOK.is_file())
        original = probes.HOOK
        probes.HOOK = pathlib.Path("/a directory/with 'quotes'/hook.py")
        try:
            self.assertEqual(shlex.split(probes.command("codex")),
                             [sys.executable, str(probes.HOOK), "codex"])
        finally:
            probes.HOOK = original


class Configuration(unittest.TestCase):
    def test_codex_takes_any_text_as_the_very_string_it_is(self):
        # Launch instructions go to Codex as a TOML string, whatever characters they hold.
        for text in ("plain", 'a "quote" and \\ a backslash', "tab\tnewline\n\x7f\x00 end",
                     "규칙 😀 \u2028"):
            with self.subTest(text=text):
                self.assertEqual(tomllib.loads(f"v = {codex.toml(text)}")["v"], text)


class Serving(Hosts, Base):
    def setUp(self):
        Base.setUp(self)
        Hosts.setUp(self)
        self.saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(self.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        Hosts.tearDown(self)
        Base.tearDown(self)

    def submit(self, capability: str = "new_delivery", target: str | None = None,
               wire: dict | None = None, host: str = "claude-code", request_id=None) -> dict:
        asked = {"kind": "capability_probe", "schema": 1,
                 "client": {"name": host, "version": VERSION},
                 "wire": wire or wire_of(host, probes.RECIPIENT.get(capability)),
                 "capability": capability}
        sealed = bench.request(self.person, PROBE, target or self.person.profile, asked,
                               request_id=request_id)
        return self.run_with(hosts.capability_probe, sealed, [asked], now=INSTANT)

    def kept(self) -> int:
        return len(self.bench.store().read("SELECT digest FROM objects WHERE kind = ?",
                                           (hosts.PROBE,)))

    def test_a_probe_that_worked_is_kept_real_and_qualifies_the_route(self):
        answer = self.submit()
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        probe, configuration = answer["returned"]
        self.assertTrue(probe["probe_id"].startswith("prb_"))
        self.assertEqual((probe["outcome"], probe["mode"], probe["at"], probe["wire"]),
                         ("worked", {"runs": "real"}, INSTANT, hosts.WIRES["launch"]))
        self.assertEqual((configuration["kind"], configuration["client"], configuration["hooks"],
                          configuration["measured_at"]),
                         ("host_configuration", probe["client"],
                          [probes.hook(event, probes.command("claude-code"), True)
                           for event in ("SessionStart", "SubagentStart", "UserPromptSubmit")],
                          INSTANT))
        for value in answer["returned"]:
            self.assertEqual(journal.refusals(value, STORED, "/"), [])
        host = {"name": "claude-code", "version": VERSION}
        self.assertTrue(hosts.supports(self.bench.store(), host, "new"))
        self.assertFalse(hosts.supports(self.bench.store(), host, "current"))

    def test_every_probe_has_an_id_of_its_own(self):
        self.assertNotEqual(self.submit()["returned"][0]["probe_id"],
                            self.submit()["returned"][0]["probe_id"])

    def test_the_host_runs_before_the_unit_of_work_holds_the_store(self):
        held, original = [], probes.probed

        def watching(*arguments):
            held.append(self.bench.store().writing)
            return original(*arguments)
        probes.probed = watching
        try:
            answer = self.submit()
        finally:
            probes.probed = original
        self.assertEqual((held, answer["returned"][0]["outcome"]), ([False], "worked"))

    def test_a_probe_that_did_not_work_is_kept_and_qualifies_nothing(self):
        os.environ["FAKE_HOST_MODE"] = "ignore"
        answer = self.submit()
        self.assertEqual(answer["returned"][0]["outcome"], "refused")
        self.assertFalse(hosts.supports(self.bench.store(),
                                        {"name": "claude-code", "version": VERSION}, "new"))

    def test_a_replayed_probe_answers_as_before_without_running_the_host_again(self):
        request_id = bench.ident("req")
        first = self.submit(request_id=request_id)
        again = self.submit(request_id=request_id)
        self.assertEqual(again, first)
        self.assertEqual(len(self.runs()), 1)

    def test_a_probe_for_another_profile_or_wire_is_refused_before_the_host_runs(self):
        for answer, gap in ((self.submit(target=bench.ident("prf")),
                             {"code": c03.REQUEST_MISMATCH, "pointer": "/target/resource_id"}),
                            (self.submit(wire={"protocol": "launch_instructions", "version": "2"}),
                             {"code": c12.WIRE_VERSION_UNSUPPORTED, "pointer": "/wire"}),
                            (self.submit(wire=hosts.WIRES["hook"]),
                             {"code": c12.WIRE_VERSION_UNSUPPORTED, "pointer": "/wire"})):
            self.assertEqual(gaps(answer), [gap])
            self.assertEqual(answer["result"]["supported_recovery"], ["new_governed_request"])
        self.assertEqual((self.kept(), self.runs()), (0, []))

    def test_probing_anything_but_a_delivery_is_not_served(self):
        with self.assertRaisesRegex(journal.JournalError, "probing read is not served yet"):
            self.submit("read")
        self.assertEqual(self.runs(), [])


if __name__ == "__main__":
    unittest.main()
