#!/usr/bin/env python3
"""Understand! picker, responsive award display, and inert native launch coverage.

All homes, instructions state and provider executables belong to temporary fixtures.
The fake app-server rejects every unlisted method, especially model generation.
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compose"))
from instructions_store import InstructionsStore
from instructions_understand import InstructionsUnderstand, TROPHY_ART


def load_launcher():
    spec = importlib.util.spec_from_file_location("understand_test_launcher", ROOT / "launch/agent-launch.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Fixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-bios-understand-ui-")
        self.root = Path(self.temp.name).resolve()
        self.home, self.state, self.user = [self.root / name for name in ("home", "state", "user")]
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("AGENT_BIOS_", "AGENT_LAUNCH_", "GIT_"))}
        env.update(HOME=str(self.home), CODEX_HOME=str(self.home / ".codex"),
                   CLAUDE_CONFIG_DIR=str(self.home / ".claude"),
                   AGENT_BIOS_PRIVATE_INSTRUCTIONS="1", AGENT_BIOS_STATE_DIR=str(self.state),
                   AGENT_BIOS_INSTRUCTIONS_DIR=str(self.user), AGENT_BIOS_PACKAGE_ROOT=str(ROOT),
                   AGENT_BIOS_UPDATE_CHECK="0", AGENT_LAUNCH_LANG="en", TERM="xterm-256color",
                   PYTHONDONTWRITEBYTECODE="1", XDG_CACHE_HOME=str(self.root / "cache"),
                   PATH=str(self.bin) + os.pathsep + env.get("PATH", ""),
                   UNDERSTAND_PROBE_LOG=str(self.root / "native.jsonl"))
        self.env = env
        self.env_patch = patch.dict(os.environ, env, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.addCleanup(self.temp.cleanup)
        for path in (self.home / ".codex/AGENTS.md", self.home / ".claude/CLAUDE.md"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("USER GLOBAL; never change\n")
        self.store = InstructionsStore(ROOT, self.state, self.user)
        self.store.install([])
        self.manager = InstructionsUnderstand(self.store, env)
        self.launch = load_launcher()
        self.config_path = ROOT / "launch/agent-launch.toml"
        self.launch.load_catalogs(self.config_path)
        self.config = self.launch.load_config(self.config_path)
        for name in ("claude", "codex"):
            executable = self.bin / name
            executable.write_text(f"#!{sys.executable}\n" + r'''
import json, os, pathlib, sys
with open(os.environ['UNDERSTAND_PROBE_LOG'], 'a') as stream:
    stream.write(json.dumps({'host': pathlib.Path(sys.argv[0]).name, 'argv': sys.argv[1:],
                            'session': os.environ.get('AGENT_BIOS_UNDERSTAND_SESSION')}) + '\n')
if 'app-server' in sys.argv:
    for line in sys.stdin:
        request = json.loads(line)
        method = request['method']
        if method == 'initialized':
            continue
        if method == 'initialize':
            result = {}
        elif method == 'config/read':
            result = {'config': {'developer_instructions': 'NATIVE DEVELOPER MARKER'}}
        elif method in ('thread/start', 'thread/read'):
            result = {'thread': {'id': '12345678-1234-1234-1234-123456789abc'}}
        elif method == 'thread/inject_items':
            result = {}
        else:
            raise SystemExit('Forbidden fake-provider method: ' + method)
        print(json.dumps({'id': request['id'], 'result': result}), flush=True)
''')
            executable.chmod(0o755)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "launch/agent-launch.py"),
                               "--config", str(self.config_path), *args], env=self.env,
                              cwd=self.root, text=True, capture_output=True, timeout=40)

    def assert_globals_unchanged(self):
        for path in (self.home / ".codex/AGENTS.md", self.home / ".claude/CLAUDE.md"):
            self.assertEqual("USER GLOBAL; never change\n", path.read_text())


class UnderstandLaunchTests(Fixture, unittest.TestCase):
    def test_learning_plan_has_no_coding_workflow_or_permission_escalation(self):
        for host in ("claude", "codex"):
            plan = self.launch.build_understand_plan(self.config, host, "core-purpose")
            argv = self.launch.project_args(plan, materialize_agents=False)
            self.assertEqual("helm", plan["main_tier"])
            self.assertFalse(plan["delegation"])
            self.assertEqual("none", plan["review_setup"])
            self.assertIsNone(plan["trigger"])
            self.assertNotIn("--agents", argv)
            self.assertNotIn("--dangerously-skip-permissions", argv)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
            self.assertIn("understand", plan["mission"].lower())
            for text in (plan["mission"], self.launch.understand_initial_prompt("<prompt>")):
                self.assertIn("10", text)
                self.assertIn("followups", text)
                self.assertIn("without a compulsory question", text)
                self.assertNotIn("End each active learning turn", text)

    def test_dry_run_does_not_create_a_learning_session(self):
        for host in ("claude", "codex"):
            result = self.run_cli("--dry-run", "--understand", "core-purpose", host)
            self.assertEqual(0, result.returncode, result.stderr)
            projected = json.loads(result.stdout.splitlines()[-1])
            self.assertEqual(1, sum("<pinned-understand-session-prompt>" in arg for arg in projected))
        self.assertFalse((self.user / "understand").exists())
        self.assert_globals_unchanged()

    def test_real_dispatch_uses_one_pinned_prompt_and_scoped_native_loading(self):
        for host in ("claude", "codex"):
            with self.subTest(host=host):
                result = self.run_cli("--yes", "--understand", "core-purpose", host)
                self.assertEqual(0, result.returncode, result.stderr)
                calls = [json.loads(line) for line in (self.root / "native.jsonl").read_text().splitlines()]
                call = [row for row in calls if row["host"] == host and "app-server" not in row["argv"]][-1]
                self.assertTrue(call["session"])
                record = self.manager.session(call["session"])
                self.assertEqual("core-purpose", record["bundle"]["id"])
                self.assertEqual(1, call["argv"].count(self.launch.understand_initial_prompt(record["prompt_path"])))
                self.assertNotIn("--", call["argv"])
                self.assertEqual(record["prompt"], Path(record["prompt_path"]).read_text())
                self.assertFalse(self.manager.status()["unlocked"])
                self.assertNotIn("--plugin-dir", call["argv"])
                if host == "codex":
                    self.assertIn("resume", call["argv"])
                    self.assertTrue(any("NATIVE DEVELOPER MARKER" in value for value in call["argv"]))
        self.assert_globals_unchanged()

    def test_conflicting_launch_modes_are_rejected(self):
        for conflicting in (["--preset", "balanced"], ["--custom"], ["--instructions-native"],
                            ["--resume-session", "existing"], ["--instructions"]):
            with self.subTest(conflicting=conflicting), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.launch.parse_args(["--understand", "core-purpose", *conflicting, "claude"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.launch.parse_args(["--understand", "core-purpose", "claude", "--", "other prompt"])

    def test_picker_returns_bundle_identity_and_back_does_not_start(self):
        with patch.object(self.launch, "choose", return_value="core-purpose") as choose:
            self.assertEqual("core-purpose", self.launch.understand_menu(None))
        options = choose.call_args.args[1]
        self.assertGreater(len(options), 1)
        self.assertTrue(all(not option.value.endswith(".md") for option in options))
        with patch.object(self.launch, "choose", side_effect=self.launch.BackRequested):
            self.assertIsNone(self.launch.understand_menu(None))
        self.assertFalse((self.user / "understand").exists())


class UnderstandTUITests(Fixture, unittest.IsolatedAsyncioTestCase):
    async def choose_value(self, app, pilot, value):
        from textual.widgets import OptionList
        for _ in range(150):
            matches = [i for i, item in enumerate(getattr(app.screen, "_options", [])) if item.value == value]
            if matches and app.screen.is_mounted and isinstance(app.focused, OptionList):
                await pilot.pause()
                app.screen.query_one(OptionList).highlighted = matches[0]
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                return
            await asyncio.sleep(0.02)
        self.fail(f"mounted screen never exposed {value}")

    async def test_root_to_bundle_picker_never_treats_a_file_as_unit(self):
        app = self.launch._build_app_class()(self.config, "claude", None, False, self.config_path)
        async with app.run_test(size=(120, 42)) as pilot:
            await self.choose_value(app, pilot, self.launch.UNDERSTAND_OPTION)
            self.assertGreater(len(app.screen._options), 1)
            self.assertFalse(app.screen._plan["delegation"])
            self.assertEqual("standard", app.screen._plan["claude_permission_mode"])
            await self.choose_value(app, pilot, "core-purpose")
        self.assertEqual("error", app.outcome[0])
        self.assertIsInstance(app.outcome[1], self.launch.UnderstandRequested)
        self.assertEqual("core-purpose", app.outcome[1].bundle_id)
        self.assertFalse((self.user / "understand").exists())

    async def test_trophy_uses_durable_status_and_yields_space_on_resize(self):
        from textual.widgets import Static
        with patch.object(self.launch, "understand_manager") as factory:
            factory.return_value.status.return_value = {"unlocked": True, "trophy_art": TROPHY_ART}
            app = self.launch._build_app_class()(self.config, "claude", None, False, self.config_path)
            async with app.run_test(size=(120, 42)) as pilot:
                for _ in range(100):
                    if app.screen.query(f"#{self.launch.TROPHY_PANEL_ID}"):
                        break
                    await asyncio.sleep(0.02)
                await pilot.pause()
                trophy = app.screen.query_one(f"#{self.launch.TROPHY_PANEL_ID}", Static)
                self.assertTrue(trophy.display)
                self.assertEqual(TROPHY_ART, str(trophy.content))
                await pilot.resize_terminal(80, 24)
                await pilot.pause()
                self.assertFalse(trophy.display)
                self.assertGreaterEqual(app.screen.query_one("#al-title").region.y, 0)
                await pilot.resize_terminal(120, 42)
                await pilot.pause()
                self.assertTrue(trophy.display)
                await pilot.press("q")
        factory.return_value.status.assert_called()

    async def test_locked_trophy_never_appears_on_large_terminal(self):
        app = self.launch._build_app_class()(self.config, "claude", None, False, self.config_path)
        async with app.run_test(size=(160, 50)) as pilot:
            for _ in range(100):
                found = app.screen.query(f"#{self.launch.TROPHY_PANEL_ID}")
                if found:
                    break
                await asyncio.sleep(0.02)
            await pilot.pause()
            self.assertFalse(found.first().display)
            await pilot.press("q")


if __name__ == "__main__":
    unittest.main()
