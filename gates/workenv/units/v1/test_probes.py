"""Probing delivery routes: `capability.probe` runs the installed host through its adapter, and
the hook the host runs hands the recipient the probe's code.

The host here is `fakehost.py`, installed as `claude` and `codex` on a PATH of the test's own;
the probe, each adapter's drive and `hook.py` are the real code. The real hosts are probed on
the machine itself, and the record of that run says what they did.
"""
from __future__ import annotations

import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import unittest

import bench
from test_sources import INSTANT, Base, gaps

from workenv import hosts, journal
from workenv.contracts import c03, c12
from workenv.contracts.schema import STORED
from workenv.hosts import hook, probes

PROBE = "capability.probe"
FAKE = pathlib.Path(__file__).with_name("fakehost.py")
VERSION = "9.9.9"
EVERY = {host: sorted(adapter.routes) for host, adapter in hosts.adapters().items()}


class Hosts(unittest.TestCase):
    """A PATH holding the fake hosts, and the environment a probe runs in."""

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="workenv-probe-")
        root = pathlib.Path(self.scratch.name)
        (root / "bin").mkdir()
        for name in ("claude", "codex"):
            (root / "bin" / name).write_text(f"#!{sys.executable}\n" + FAKE.read_text())
            (root / "bin" / name).chmod(0o755)
        self.log = root / "log.jsonl"
        self.environ = {"PATH": f"{root / 'bin'}{os.pathsep}{os.environ['PATH']}",
                        "HOME": str(root), "FAKE_HOST_LOG": str(self.log),
                        "FAKE_HOST_VERSION": VERSION, "FAKE_HOST_MODE": "obey",
                        "FAKE_HOST_TRUST": "trusted", "CLAUDECODE": "1",
                        "CLAUDE_CODE_SESSION_ID": "outer", "CODEX_THREAD_ID": "outer"}
        self.work = root / "work"
        self.work.mkdir()

    def tearDown(self):
        self.scratch.cleanup()

    def probe(self, host: str, recipient: str, version: str = VERSION, **environ) -> tuple:
        asked = {"kind": "capability_probe", "schema": 1,
                 "client": {"name": host, "version": version}, "wire": probes.WIRE,
                 "capability": hosts.CAPABILITY[recipient]}
        with tempfile.TemporaryDirectory(dir=self.work) as workdir:
            return probes.probed(asked, {**self.environ, **environ},
                                 pathlib.Path(workdir).resolve())

    def drive(self, host: str, drive):
        """The adapter of the host with another drive, for the length of one probe."""
        adapter = hosts.adapter_for(host)
        original = adapter.drive
        object.__setattr__(adapter, "drive", drive)
        self.addCleanup(object.__setattr__, adapter, "drive", original)

    def runs(self) -> list[dict]:
        if not self.log.is_file():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()
                if json.loads(line)["argv"] != ["--version"]]


class Probing(Hosts):
    def test_a_route_that_hands_the_recipient_the_code_worked_on_every_declared_route(self):
        for host, recipients in EVERY.items():
            for recipient in recipients:
                if (host, recipient) == ("codex", "rehydrated"):
                    continue
                with self.subTest(host=host, recipient=recipient):
                    found, ran_under = self.probe(host, recipient)
                    self.assertEqual((found["offered"], found["outcome"]), (True, "worked"),
                                     found["observed"])
                    route = hosts.adapter_for(host).routes[recipient]
                    event = route.event if host == "claude-code" else \
                        route.event[0].lower() + route.event[1:]
                    self.assertIn(probes.hook(event, probes.command(host), True), ran_under)

    def test_a_host_that_does_not_run_the_hook_refused_the_route(self):
        for host in EVERY:
            with self.subTest(host=host):
                found, _ = self.probe(host, "new", FAKE_HOST_MODE="ignore")
                self.assertEqual((found["offered"], found["outcome"]), (True, "refused"))

    def test_a_code_the_hook_did_not_hand_over_does_not_count(self):
        for host in EVERY:
            with self.subTest(host=host):
                found, _ = self.probe(host, "current", FAKE_HOST_MODE="stale")
                self.assertEqual(found["outcome"], "refused")

    def test_a_host_that_gives_no_reply_did_not_respond(self):
        for host, recipients in EVERY.items():
            for recipient in recipients:
                for mode in ("silent", "error"):
                    if (host, recipient) == ("codex", "rehydrated"):
                        continue
                    with self.subTest(host=host, recipient=recipient, mode=mode):
                        found, _ = self.probe(host, recipient, FAKE_HOST_MODE=mode)
                        self.assertEqual((found["offered"], found["outcome"]),
                                         (True, "no_response"))

    def test_a_claude_session_that_could_not_be_compacted_did_not_respond(self):
        found, _ = self.probe("claude-code", "rehydrated", FAKE_HOST_MODE="nocompact")
        self.assertEqual(found["outcome"], "no_response")
        self.assertEqual(len(self.runs()), 2)

    def test_codex_listing_no_hooks_did_not_respond_and_asked_nothing(self):
        found, ran_under = self.probe("codex", "new", FAKE_HOST_MODE="nolist")
        self.assertEqual((found["offered"], found["outcome"], ran_under),
                         (True, "no_response", []))
        self.assertEqual([run for run in self.runs() if "exec" in run["argv"]], [])

    def test_the_probe_configures_only_the_route_it_probes_as_declared(self):
        for host, recipients in EVERY.items():
            for recipient in recipients:
                if (host, recipient) == ("codex", "rehydrated"):
                    continue
                with self.subTest(host=host, recipient=recipient):
                    self.log.unlink(missing_ok=True)
                    self.probe(host, recipient)
                    route = hosts.adapter_for(host).routes[recipient]
                    group = {"hooks": [{"type": "command", "command": probes.command(host)}]}
                    if route.source is not None:
                        group["matcher"] = route.source
                    runs = self.runs()
                    self.assertTrue(runs)
                    for run in runs:
                        self.assertEqual(run["groups"], {route.event: [group]})

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

    def test_codex_runs_keep_no_session_and_change_nothing(self):
        self.probe("codex", "current")
        [run] = [run for run in self.runs() if "exec" in run["argv"]]
        self.assertIn("--ephemeral", run["argv"])
        self.assertEqual(run["argv"][run["argv"].index("-s") + 1], "read-only")

    def test_an_adapter_that_cannot_drive_its_host_is_unsupported(self):
        self.drive("claude-code", None)
        found, _ = self.probe("claude-code", "new")
        self.assertEqual((found["offered"], found["outcome"]), (False, "unsupported"))
        self.assertFalse(self.log.exists())

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
        for host, recipient in (("codex", "child"), ("a-host-nobody-wrote", "new")):
            with self.subTest(host=host):
                found, ran_under = self.probe(host, recipient)
                self.assertEqual((found["offered"], found["outcome"], ran_under),
                                 (False, "unsupported", []))
        self.assertFalse(self.log.exists())

    def test_a_rehydrated_codex_session_is_unsupported_without_a_run(self):
        found, _ = self.probe("codex", "rehydrated")
        self.assertEqual((found["offered"], found["outcome"]), (False, "unsupported"))
        self.assertIn("compact", found["observed"])
        self.assertEqual(self.runs(), [])

    def test_a_rehydrated_claude_session_sees_only_what_was_handed_over_at_compaction(self):
        found, _ = self.probe("claude-code", "rehydrated")
        self.assertEqual(found["outcome"], "worked")
        argvs = [run["argv"] for run in self.runs()]
        session = argvs[0][argvs[0].index("--session-id") + 1]
        self.assertEqual([argv[-2:] for argv in argvs],
                         [[session, "Reply OK."], [session, "/compact"], [session, probes.ASK]])
        self.probe("claude-code", "rehydrated")
        self.assertNotIn(session, self.runs()[3]["argv"])

    def test_codex_records_every_hook_it_would_run_and_an_untrusted_probe_hook_as_not(self):
        found, ran_under = self.probe("codex", "new", FAKE_HOST_TRUST="untrusted")
        self.assertEqual(found["outcome"], "refused")
        self.assertIn("/hooks", found["observed"])
        self.assertEqual(ran_under, [probes.hook("stop", "the person's own hook", True),
                                     probes.hook("stop", "a managed hook", True),
                                     probes.hook("sessionStart", probes.command("codex"),
                                                 False)])

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
        long = probes.Run(None, [], "x" * 5000, outcome="no_response")
        self.drive("claude-code", lambda *arguments: long)
        found, _ = self.probe("claude-code", "new")
        self.assertEqual(len(found["observed"]), probes.OBSERVED)

    def test_a_host_that_cannot_start_or_does_not_finish_ran_nothing(self):
        slow = [sys.executable, "-c", "import time; time.sleep(5)"]
        self.assertIsNone(probes.ran(slow, self.work, dict(os.environ), timeout=0.2))
        self.assertIsNone(probes.ran([str(self.work / "missing")], self.work, dict(os.environ)))


class Hook(unittest.TestCase):
    def test_it_hands_the_text_only_to_the_recipient_its_job_names_on_every_host(self):
        for host, adapter in hosts.adapters().items():
            for recipient, route in adapter.routes.items():
                with self.subTest(host=host, recipient=recipient):
                    event = {"hook_event_name": route.event, "session_id": "s"}
                    if route.source is not None:
                        event["source"] = route.source
                    printed = hook.answer(host, event, {"recipient": recipient, "text": "T"})
                    self.assertEqual(printed, adapter.output(event, "T"))
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
                 "client": {"name": host, "version": VERSION}, "wire": wire or probes.WIRE,
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
        self.assertEqual((probe["outcome"], probe["mode"], probe["at"]),
                         ("worked", {"runs": "real"}, INSTANT))
        self.assertEqual((configuration["kind"], configuration["client"], configuration["hooks"],
                          configuration["measured_at"]),
                         ("host_configuration", probe["client"],
                          [probes.hook("SessionStart", probes.command("claude-code"), True)],
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
                            (self.submit(wire={"protocol": "command_hook", "version": "2"}),
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
