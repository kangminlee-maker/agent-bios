"""The commands a person runs (`workenv.commands`) and where they keep what they make
(`workenv.local`): the profile, the sources in the order they compose, a preparation shown and
not started, the start from the entry to the host it launches, and what reached that session.

The hosts are `fakehost.py` on a PATH of the test's own, as in `test_start`; the terminal is a
screen of the test's own fed bytes a person would type, read by the real decoder.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import stat
import unittest
from unittest import mock

import bench
from test_probes import VERSION, Hosts
from test_routes import Routing, unknown
from test_sources import INSTANT, ORIGIN, Checkout, gaps

from workenv import commands, hosts, local, sources, terminal, tui
from workenv.hosts import hook, probes, start

BODY = b"# Review\n\nOne approval.\n"
NOTES = b"# Notes\n"
DOWN, RIGHT, TAB, ENTER, QUIT = b"\x1b[B", b"\x1b[C", b"\t", b"\r", b"\x03"


class Screen:
    """A terminal of the test's own: its size, what it drew, and the bytes typed, one read each."""

    def __init__(self, *reads: bytes, size=(80, 24)):
        self.reads, self.columns, self.rows = list(reads), *size
        self.frames: list[dict] = []
        self.held = False

    def size(self) -> tuple[int, int]:
        return self.columns, self.rows

    def __enter__(self):
        self.held = True
        return self

    def __exit__(self, *_):
        self.held = False

    def draw(self, frame: dict) -> None:
        self.frames.append(frame)

    def inputs(self):
        decoder = terminal.Decoder()
        for data in self.reads:
            yield from decoder.feed(data)
        yield from decoder.flush()

    def element(self, element_id: str, at: int = -1) -> dict:
        return next(e for e in self.frames[at]["elements"] if e["element_id"] == element_id)


class Commanding(Hosts, Routing):
    def setUp(self):
        Routing.setUp(self)
        Hosts.setUp(self)
        self.base = pathlib.Path(self.bench.scratch.name) / "base"
        self.env = {**self.environ, local.BASE: str(self.base)}
        # The person the tests author as is the installation's actor.
        self.bench.state = local.state_root(self.env)
        local.home(self.env).mkdir(parents=True)
        (local.home(self.env) / local.ACTOR).write_text(json.dumps(self.person.actor))
        self.launched: list[tuple[start.Launch, dict]] = []

    def tearDown(self):
        Hosts.tearDown(self)
        Routing.tearDown(self)

    def run_command(self, *argv: str, screen: Screen | None = None,
                    workdir: pathlib.Path | None = None) -> tuple[int, str]:
        said, err = [], io.StringIO()
        with contextlib.redirect_stderr(err), mock.patch.dict(os.environ, self.env):
            code = commands.main(list(argv), dict(self.env), workdir or self.work,
                                 out=said.append, screen=screen, run=self.became)
        self.err = err.getvalue()
        return code, "\n".join(said)

    def became(self, launch: start.Launch, environ: dict) -> int:
        self.launched.append((launch, environ))
        return 0

    def qualified(self, *names: str) -> None:
        for name in names:
            self.probed(name, "new", version=VERSION)

    def bound(self) -> pathlib.Path:
        """A checkout of ORIGIN, bound as the repository."""
        checkout = Checkout(self.scratch, "repo")
        checkout.git("remote", "add", "origin", ORIGIN)
        checkout.commit()
        payload = {"kind": "repository_binding", "schema": 1,
                   "repository_id": self.repository["repository_id"],
                   "relation": {"how": "clone"}}
        with contextlib.chdir(checkout.path):
            answer = self.run_with(sources.repository_bind,
                                   bench.request(self.person, "repository.bind",
                                                 self.repository["repository_id"], payload),
                                   [payload], now=INSTANT)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        return checkout.path

    def held_requests(self, operation: str) -> list[tuple[str, str]]:
        return self.bench.store().read("SELECT request_id, stage FROM requests WHERE "
                                       "operation = ? ORDER BY position", (operation,))


class Local(unittest.TestCase):
    def test_the_state_root_is_under_the_base_the_caller_sets_or_the_home(self):
        self.assertEqual(local.state_root({"HOME": "/h"}),
                         pathlib.Path("/h/.local/share/agent-bios/workenv/state"))
        self.assertEqual(local.state_root({"HOME": "/h", local.BASE: "/b"}),
                         pathlib.Path("/b/workenv/state"))
        self.assertEqual(local.root_origin({"HOME": "/h"}), "owner")
        self.assertEqual(local.root_origin({"HOME": "/h", local.BASE: "/b"}), "caller")

    def test_the_actor_is_minted_once_and_readable_by_its_owner_alone(self):
        scratch = bench.Bench()
        self.addCleanup(scratch.close)
        environ = {"HOME": scratch.scratch.name}
        self.assertIsNone(local.held_actor(environ))
        actor = local.actor(environ)
        self.assertEqual(local.actor(environ), actor)
        self.assertEqual([actor[name][:4] for name, _ in local.IDS], ["prn_", "dev_", "prf_"])
        path = local.home(environ) / local.ACTOR
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        path.write_text(json.dumps({**actor, "device_id": "key_1"}))
        with self.assertRaisesRegex(local.LocalError, "principal, a device and a profile"):
            local.actor(environ)

    def test_the_locale_is_the_first_language_the_environment_sets(self):
        for environ, found in (({"LANG": "ko_KR.UTF-8"}, "ko"),
                               ({"LC_ALL": "ja_JP.UTF-8", "LANG": "ko_KR.UTF-8"}, "ja"),
                               ({"LC_MESSAGES": "en_US", "LANG": "ko_KR"}, "en"),
                               ({"LANG": "C.UTF-8"}, "en"), ({}, "en")):
            with self.subTest(environ=environ):
                self.assertEqual(local.locale(environ), found)


class Profile(Commanding):
    def test_the_first_request_writes_the_profile_that_names_the_actor(self):
        code, said = self.run_command("profile")
        self.assertEqual(code, 0, self.err)
        self.assertIn(f"Profile {self.person.profile}", said)
        self.assertIn(f"principal {self.person.principal}", said)
        self.assertIn("access active (first_use), generation 1", said)

    def test_first_use_mints_the_actor_it_then_keeps(self):
        (local.home(self.env) / local.ACTOR).unlink()
        _, said = self.run_command("profile")
        actor = local.held_actor(self.env)
        self.assertIn(f"Profile {actor['profile_id']}", said)
        self.assertEqual(self.run_command("profile")[1], said)


class Sources(Commanding):
    def test_nothing_is_held_before_first_use_and_nothing_is_written(self):
        (local.home(self.env) / local.ACTOR).unlink()
        self.assertEqual(self.run_command("sources"),
                         (0, "Nothing is held on this installation yet."))
        self.assertIsNone(local.held_actor(self.env))

    def test_each_position_shows_its_sources_in_the_order_they_compose(self):
        me = self.person.scope
        rules, revision = self.authored(me, {"rules/review.md": BODY})
        notes, noted = self.authored(me, {"notes.md": NOTES}, role="knowledge")
        code, said = self.run_command("sources")
        self.assertEqual(code, 0, self.err)
        self.assertEqual(said.splitlines(), [
            "Each position, in the order it composes:",
            "  personal instructions: installed",
            f"    {rules} revision {revision[:12]}: rules/review.md",
            "  personal knowledge: held; its bodies are read for a task",
            f"    {notes} revision {noted[:12]}: notes.md",
            "  personal memory: none"])

    def test_a_bound_checkout_composes_the_repository_before_the_person(self):
        checkout = self.bound()
        rules, revision = self.authored(self.repository, {"AGENTS.md": BODY})
        said = self.run_command("sources", workdir=checkout)[1].splitlines()
        self.assertEqual([line for line in said if not line.startswith("    ")], [
            "Each position, in the order it composes:",
            "  repository instructions: installed", "  repository knowledge: none",
            "  repository memory: none", "  personal instructions: none",
            "  personal knowledge: none", "  personal memory: none"])
        self.assertEqual(said[2], f"    {rules} revision {revision[:12]}: AGENTS.md")

    def test_a_collection_names_itself_and_the_sources_it_switches_on(self):
        me = self.person.scope
        rules, revision = self.authored(me, {"rules/review.md": BODY})
        collection = self.collection(me, "instructions", [self.entry(rules, revision)])
        self.placed(collection)
        said = self.run_command("sources")[1].splitlines()
        self.assertEqual(said[1:3], [
            f"  personal instructions (collection {collection['collection_id']}): installed",
            f"    {rules} revision {revision[:12]}: rules/review.md"])


class Prepare(Commanding):
    def test_the_suggested_start_is_composed_shown_and_nothing_is_activated(self):
        self.qualified("claude-code")
        rules, _ = self.authored(self.person.scope, {"rules/review.md": BODY})
        code, said = self.run_command("prepare", "claude-code")
        self.assertEqual(code, 0, self.err)
        lines = said.splitlines()
        self.assertRegex(lines[0], r"\APreparation prp_[0-9a-f]{32}, composed in the order "
                                   r"personal:\Z")
        self.assertRegex(lines[1], rf"\A  personal instructions layered: rules/review.md "
                                   rf"\(source {rules}, body [0-9a-f]{{12}}\)\Z")
        self.assertEqual(lines[-1], "Nothing was activated or launched.")
        self.assertEqual(self.held_requests("session.routing.activate"), [])
        [(request_id, stage)] = self.held_requests("preparation.compose")
        self.assertEqual(stage, "previewed")
        offer = tui.latest_offer(self.bench.store(), "setup")
        self.assertEqual(offer["entrance"], {"name": "setup", "root_origin": "caller"})

    def test_a_host_no_probe_qualified_is_probed_first_and_said_to_be(self):
        code, said = self.run_command("prepare", "codex")
        self.assertEqual(code, 0, self.err)
        self.assertTrue(said.startswith(
            f"Checking that Codex CLI {VERSION} hands a new session its work environment. "
            "This runs Codex CLI once and makes one model call.\n  worked: "), said)
        self.assertEqual([stage for _, stage in self.held_requests("capability.probe")],
                         ["committed"])
        self.assertTrue(hosts.supports(self.bench.store(), {"name": "codex", "version": VERSION},
                                       "new"))

    def test_a_host_the_probe_did_not_qualify_is_not_prepared_for(self):
        self.env["FAKE_HOST_MODE"] = "ignore"
        code, said = self.run_command("prepare", "codex")
        self.assertEqual(code, 1)
        self.assertIn("  refused: ", said)
        self.assertIn(f"Codex CLI {VERSION} was not shown to hand a new session", self.err)
        self.assertEqual(self.held_requests("preparation.compose"), [])
        self.assertEqual(self.held_requests("route.offer"), [])

    def test_a_start_whose_result_is_unknown_is_checked_before_another_is_prepared(self):
        self.qualified("claude-code")
        self.activate(self.prepared(self.ask([self.person.scope])), entry=unknown)
        self.assertEqual(self.run_command("prepare", "claude-code")[0], 1)
        self.assertIn("the last start's result is unknown (req_", self.err)
        self.assertEqual(len(self.held_requests("preparation.compose")), 1)

    def test_a_host_not_installed_is_named(self):
        self.env["PATH"] = "/nonexistent"
        self.assertEqual(self.run_command("prepare", "claude-code")[0], 1)
        self.assertIn("no Claude Code is installed on this machine's path", self.err)


class Start(Commanding):
    def test_the_entry_s_start_launches_the_host_with_what_it_sealed(self):
        self.qualified("claude-code")
        self.authored(self.person.scope, {"rules/review.md": BODY})
        screen = Screen(TAB, "다음 단계".encode(), TAB, TAB, ENTER)
        code, said = self.run_command("start", "claude-code", screen=screen)
        self.assertEqual((code, said), (0, ""), self.err)
        [(launch, environ)] = self.launched
        self.assertEqual(pathlib.Path(launch.executable).name, "claude")
        self.assertNotIn("--dangerously-skip-permissions", launch.arguments)
        self.assertEqual(environ[local.BASE], str(self.base))
        [(compose, _)] = self.held_requests("preparation.compose")
        self.assertEqual(self.element_of(screen, "result.start")["refers_to"]["request_id"],
                         compose)
        self.assertEqual(self.bench.store().read(
            "SELECT rationale FROM requests WHERE request_id = ?", (compose,)), [("다음 단계",)])
        [(select, stage)] = self.held_requests("route.select")
        self.assertEqual(stage, "committed")
        self.assertEqual([stage for _, stage in self.held_requests("session.routing.activate")],
                         ["committed"])
        self.assertEqual(screen.frames[0]["view"]["origin"],
                         {"name": "setup", "root_origin": "caller"})
        self.assertFalse(screen.held)

    def element_of(self, screen: Screen, element_id: str) -> dict:
        return next(e for frame in reversed(screen.frames) for e in frame["elements"]
                    if e["element_id"] == element_id)

    def test_skipping_the_confirmations_on_the_entry_skips_them_in_the_host(self):
        self.qualified("claude-code")
        screen = Screen(TAB, TAB, RIGHT, TAB, ENTER)
        self.assertEqual(self.run_command("start", "claude-code", "--entrance",
                                          "host_launcher", "--locale", "en",
                                          screen=screen)[0], 0, self.err)
        [(launch, _)] = self.launched
        self.assertEqual(launch.arguments[-1], "--dangerously-skip-permissions")
        self.assertEqual(screen.frames[0]["view"]["origin"]["name"], "host_launcher")
        self.assertEqual(screen.frames[0]["locale"], "en")

    def test_the_tool_the_person_turns_to_is_the_host_started(self):
        self.qualified("claude-code", "codex")
        screen = Screen(TAB, TAB, RIGHT, TAB, TAB, ENTER)
        self.assertEqual(self.run_command("start", "claude-code", screen=screen)[0], 0, self.err)
        [(launch, _)] = self.launched
        self.assertEqual(pathlib.Path(launch.executable).name, "codex")
        self.assertEqual(self.element_of(screen, "execution.tool")["value"], "Codex CLI")

    def test_the_named_host_is_offered_first(self):
        self.qualified("claude-code", "codex")
        for name, tool in (("codex", "Codex CLI"), ("claude-code", "Claude Code")):
            with self.subTest(host=name):
                screen = Screen(QUIT)
                self.run_command("start", name, screen=screen)
                self.assertEqual(screen.element("execution.tool", 0)["value"], tool)

    def test_an_installed_host_no_probe_qualified_is_not_offered_beside_the_named_one(self):
        self.qualified("claude-code")
        screen = Screen(QUIT)
        self.run_command("start", "claude-code", screen=screen)
        offer = tui.latest_offer(self.bench.store(), "setup")
        self.assertEqual(len(offer["offered"]), 1)
        self.assertEqual(screen.element("execution.tool", 0)["value"], "Claude Code")

    def test_leaving_the_entry_sends_nothing_and_launches_nothing(self):
        self.qualified("claude-code")
        for leave in (QUIT, b"\x04"):
            with self.subTest(leave=leave):
                screen = Screen(TAB, TAB, TAB, leave, ENTER)
                self.assertEqual(self.run_command("start", "claude-code", screen=screen)[0],
                                 commands.LEFT)
        self.assertEqual((self.launched, self.held_requests("preparation.compose"),
                          self.held_requests("route.select")), ([], [], []))

    def test_a_start_the_owner_refuses_is_drawn_and_launches_nothing(self):
        self.qualified("claude-code")
        screen = Screen(TAB, TAB, TAB, ENTER, QUIT)
        with mock.patch.object(start, "start", side_effect=start.StartError("activating failed")):
            code, _ = self.run_command("start", "claude-code", "--locale", "ko", screen=screen)
        self.assertEqual(code, commands.LEFT)
        result = self.element_of(screen, "result.start")
        self.assertEqual((result["state"], result["label"]),
                         ("unavailable", "시작하지 못함 · activating failed"))
        self.assertEqual((self.launched, self.held_requests("route.select")), ([], []))

    def test_the_check_of_an_unknown_start_is_answered_in_the_entry(self):
        self.qualified("claude-code")
        prepared = self.prepared(self.ask([self.person.scope]), rationale="이전 메모")
        activated = self.activate(prepared, entry=unknown)
        screen = Screen(ENTER, QUIT)
        self.assertEqual(self.run_command("start", "claude-code", screen=screen)[0],
                         commands.LEFT)
        first, checked = screen.frames[0], screen.frames[1]
        self.assertEqual(next(e for e in first["elements"] if e["focused"])["element_id"],
                         "action.check")
        draft = next(e for e in checked["elements"] if e["element_id"] == "result.draft")
        self.assertEqual((draft["state"], draft["refers_to"]["request_id"]),
                         ("unknown", activated["result"]["request_id"]))
        check = next(e for e in checked["elements"] if e["element_id"] == "action.check")
        self.assertEqual((check["executing"], checked["dispatched"] != []), (False, True))
        self.assertEqual(self.held_requests("preparation.compose")[1:], [])

    def test_the_entry_needs_a_terminal(self):
        self.qualified("claude-code")
        with mock.patch.object(os, "isatty", return_value=False):
            self.assertEqual(self.run_command("start", "claude-code")[0], 1)
        self.assertIn("the entry needs a terminal", self.err)

    def test_the_program_becomes_the_host_with_the_launch_s_environment(self):
        launch = start.Launch("/bin/host", ["--a"], {probes.JOB: "/j"}, ("NESTED",),
                              pathlib.Path("/d"), "text")
        with mock.patch.object(os, "execve") as execve:
            commands.execute(launch, {"NESTED": "1", "KEEP": "2", probes.JOB: "old"})
        execve.assert_called_once_with("/bin/host", ["/bin/host", "--a"],
                                       {"KEEP": "2", probes.JOB: "/j"})

    def test_a_check_is_drawn_unknown_only_while_the_request_is_held_pending(self):
        def query(*returned, stage="previewed", gaps=()):
            return {"result": {"outcome": {"stage": stage, "material_gaps": list(gaps)}},
                    "returned": list(returned)}

        def result(stage):
            return {"kind": "operation_result", "outcome": {"stage": stage}}
        self.assertEqual(commands.checked(query(result("unknown"))), ("unknown", None))
        self.assertEqual(commands.checked(query(result("partial"))), ("unknown", None))
        self.assertEqual(commands.checked(query(result("committed")))[0], "unavailable")
        self.assertEqual(commands.checked(query({"kind": "request_not_held"})),
                         ("unavailable", "this installation holds no such request"))
        self.assertEqual(commands.checked(query(stage="refused", gaps=[{"code": "x"}])),
                         ("unavailable", "refused with x"))
        self.assertEqual(commands.checked({"refused": [["request", "c", "/p"]]})[0],
                         "unavailable")


class Received(Commanding):
    def test_nothing_is_received_before_a_session_reports(self):
        self.assertEqual(self.run_command("received"),
                         (0, "No session started here has reported that it began."))

    def test_what_reached_the_session_the_start_launched_is_shown(self):
        self.qualified("claude-code")
        rules, _ = self.authored(self.person.scope, {"rules/review.md": BODY})
        self.run_command("start", "claude-code", screen=Screen(TAB, TAB, TAB, ENTER))
        [(launch, _)] = self.launched
        event = {"hook_event_name": "SessionStart", "source": "startup", "session_id": "s-1"}
        with contextlib.chdir(self.work), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            hook.main(["claude-code"], io.StringIO(json.dumps(event)),
                      {hook.JOB: launch.environ[probes.JOB]})
        self.assertEqual(err.getvalue(), "")
        code, said = self.run_command("received")
        self.assertEqual(code, 0, self.err)
        lines = said.splitlines()
        self.assertRegex(lines[0], r"\AWhat reached the session started with preparation "
                                   r"prp_[0-9a-f]{32}:\Z")
        self.assertRegex(lines[1], r"\A  host session [0-9a-f]{12}: activated at \S+Z\Z")
        self.assertRegex(lines[2], rf"\A    unt_[0-9a-f]{{32}} from {rules}, body "
                                   r"[0-9a-f]{12}\Z")


if __name__ == "__main__":
    unittest.main()
