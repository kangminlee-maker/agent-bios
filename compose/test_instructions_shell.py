"""Opt-in shell routing through the real CLI, zsh and mounted launcher TUI."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from instructions_install import InstructionsInstaller
from instructions_transaction import pending_status

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "launch"))
from shell_integration import ShellIntegration, ShellIntegrationError, START


class ShellFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-bios-shell-test-")
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.state = self.root / "state"
        self.user = self.root / "instructions"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_BIOS_", "AGENT_LAUNCH_", "GIT_"))}
        self.env.update(HOME=str(self.home), ZDOTDIR=str(self.home),
                        CLAUDE_CONFIG_DIR=str(self.home / ".claude"), CODEX_HOME=str(self.home / ".codex"),
                        AGENT_BIOS_STATE_DIR=str(self.state), AGENT_BIOS_INSTRUCTIONS_DIR=str(self.user),
                        AGENT_BIOS_PRIVATE_INSTRUCTIONS="1", AGENT_BIOS_UPDATE_CHECK="0",
                        AGENT_LAUNCH_LANG="en", PYTHONDONTWRITEBYTECODE="1", TERM="xterm-256color")
        for relative in (".claude/CLAUDE.md", ".codex/AGENTS.md"):
            target = self.home / relative
            target.parent.mkdir()
            target.write_bytes(b"user-owned instructions; never replace\n")
        self.original = b"# user's shell settings, without a final newline"
        (self.home / ".zshrc").write_bytes(self.original)
        self.installer = InstructionsInstaller(SOURCE, self.env)
        self.installer.install("none")
        self.manager = ShellIntegration(self.env, SOURCE)

    def tearDown(self):
        self.temp.cleanup()

    def assert_globals(self):
        for relative in (".claude/CLAUDE.md", ".codex/AGENTS.md"):
            self.assertEqual(b"user-owned instructions; never replace\n", (self.home / relative).read_bytes())

    def cli(self, *args, check=True):
        return subprocess.run(["/bin/bash", str(SOURCE / "install.sh"), *args],
                              env=self.env, text=True, capture_output=True, check=check)


class ShellTests(ShellFixture, unittest.TestCase):
    def test_default_off_and_help_names_real_entrypoints(self):
        self.assertFalse(self.manager.status()["enabled"])
        self.assertFalse(self.manager.script.exists())
        self.assertEqual(self.original, self.manager.startup.read_bytes())
        help_text = self.cli("help").stdout
        for command in ("agent-launch claude", "agent-launch codex", "agent-launch --instructions",
                        "agent-bios shell restore", "agent-bios shell remove"):
            self.assertIn(command, help_text)
        self.assert_globals()

    def test_cli_restore_idempotent_remove_preserves_user_bytes(self):
        restored = json.loads(self.cli("shell", "restore").stdout)
        self.assertTrue(restored["enabled"])
        backup = Path(restored["backup_root"])
        self.assertTrue((backup / "paths.json").is_file())
        self.assertEqual([], json.loads(self.cli("shell", "restore").stdout)["changed_paths"])
        self.assertEqual(1, self.manager.startup.read_bytes().count(START))
        self.assertTrue(json.loads(self.cli("shell").stdout)["enabled"])
        removed = json.loads(self.cli("shell", "remove").stdout)
        self.assertFalse(removed["enabled"])
        self.assertFalse(self.manager.script.exists())
        self.assertFalse(self.manager.receipt.exists())
        self.assertEqual(self.original, self.manager.startup.read_bytes())
        self.assertEqual([], json.loads(self.cli("shell", "remove").stdout)["changed_paths"])
        self.assert_globals()

    def test_missing_and_empty_startup_have_distinct_roundtrips(self):
        for existed in (False, True):
            with self.subTest(existed=existed):
                self.manager.startup.unlink(missing_ok=True)
                if existed:
                    self.manager.startup.touch()
                self.manager.apply("restore")
                self.manager.apply("remove")
                self.assertEqual(existed, self.manager.startup.exists())
                if existed:
                    self.assertEqual(b"", self.manager.startup.read_bytes())

    def test_dry_run_does_not_create_or_modify_shell_state(self):
        preview = json.loads(self.cli("shell", "restore", "--dry-run").stdout)
        self.assertTrue(preview["preview"])
        self.assertFalse(self.manager.script.exists())
        self.assertFalse(self.manager.receipt.exists())
        self.assertFalse((self.state / "runtime/shell-backups").exists())
        self.assertEqual(self.original, self.manager.startup.read_bytes())

    def test_incomplete_connection_is_disclosed_and_can_be_restored(self):
        self.manager.apply("restore")
        self.manager.receipt.unlink()
        incomplete = self.manager.status()
        self.assertFalse(incomplete["enabled"])
        self.assertTrue(incomplete["needs_action"])
        self.manager.apply("restore")
        self.assertTrue(self.manager.status()["enabled"])
        self.assertEqual([], self.manager.status()["needs_action"])
        self.manager.apply("remove")
        self.assertEqual(self.original, self.manager.startup.read_bytes())

    def crash_restore_after(self, target):
        code = '''
import os, signal, sys
sys.path.insert(0, sys.argv[1])
from shell_integration import ShellIntegration
manager = ShellIntegration()
original = manager._write
def crash(path, body, mode):
    original(path, body, mode)
    if str(path) == sys.argv[2]:
        os.kill(os.getpid(), signal.SIGKILL)
manager._write = crash
manager.apply("restore")
'''
        result = subprocess.run([sys.executable, "-c", code, str(SOURCE / "launch"), str(target)],
                                env=self.env, capture_output=True, timeout=20)
        self.assertEqual(-signal.SIGKILL, result.returncode, result.stderr.decode())

    def test_first_restore_persists_intent_before_publishing_script(self):
        for target in (self.manager.receipt, self.manager.script, self.manager.startup):
            with self.subTest(kill_after=target):
                self.crash_restore_after(target)
                self.assertTrue(self.manager.receipt.is_file())
                self.manager.apply("remove")
                self.assertFalse(self.manager.script.exists())
                self.assertEqual(self.original, self.manager.startup.read_bytes())
        self.assert_globals()

    def test_uninstall_cleans_orphan_script_without_receipt(self):
        self.manager.apply("restore")
        self.manager.receipt.unlink()  # old script-first restore crash state
        self.cli("uninstall")
        self.assertFalse(self.manager.script.exists())
        self.assertEqual(self.original, self.manager.startup.read_bytes())
        self.assert_globals()

    def test_reset_cleans_orphan_script_without_receipt(self):
        self.manager.apply("restore")
        self.manager.receipt.unlink()
        preview = self.installer.reset()
        self.assertIn(str(self.manager.script), preview["restore_defaults"])
        self.installer.reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        self.assertFalse(self.manager.script.exists())
        self.assertEqual(self.original, self.manager.startup.read_bytes())
        self.assert_globals()

    def test_install_recovers_orphan_script_without_receipt(self):
        self.manager.apply("restore")
        self.manager.receipt.unlink()
        self.installer.install()
        self.assertTrue(self.manager.status()["enabled"])

    def test_install_repairs_missing_and_nonexecutable_launcher_with_opt_in(self):
        self.manager.apply("restore")
        launcher = self.home / ".local/bin/agent-launch"
        for fault in ("missing", "nonexecutable"):
            with self.subTest(fault=fault):
                if fault == "missing":
                    launcher.unlink()
                else:
                    launcher.chmod(0o644)
                self.assertFalse(self.manager.status()["enabled"])
                self.installer.install()
                self.assertTrue(os.access(launcher, os.X_OK))
                self.assertTrue(self.manager.status()["enabled"])

    def test_default_off_does_not_claim_foreign_shell_symlink(self):
        foreign = self.root / "foreign-shell.zsh"
        foreign.write_bytes(b"# user's own shell adapter\n")
        self.manager.script.symlink_to(foreign)
        self.installer.install()
        preview = self.installer.reset()
        self.installer.reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        self.installer.uninstall()
        self.assertTrue(self.manager.script.is_symlink())
        self.assertEqual(b"# user's own shell adapter\n", foreign.read_bytes())
        self.assertEqual(self.original, self.manager.startup.read_bytes())

    def test_nonexecutable_launcher_is_not_reported_as_enabled(self):
        self.manager.apply("restore")
        (self.home / ".local/bin/agent-launch").chmod(0o644)
        result = self.cli("shell", "status", check=False)
        self.assertEqual(1, result.returncode)
        status = json.loads(result.stdout)
        self.assertFalse(status["enabled"])
        self.assertTrue(status["needs_action"])

    def test_shell_remove_does_not_require_ownership_of_launcher(self):
        self.manager.apply("restore")
        launcher = self.home / ".local/bin/agent-launch"
        launcher.unlink()
        foreign = self.root / "foreign-launcher"
        foreign.write_bytes(b"#!/bin/sh\nexit 0\n")
        foreign.chmod(0o755)
        launcher.symlink_to(foreign)
        self.assertFalse(self.manager.status()["enabled"])
        self.cli("shell", "remove")
        self.assertFalse(self.manager.script.exists())
        self.assertEqual(self.original, self.manager.startup.read_bytes())
        self.assertTrue(launcher.is_symlink())
        self.assertEqual(b"#!/bin/sh\nexit 0\n", foreign.read_bytes())

    def test_invalid_install_record_prevents_any_uninstall_mutation(self):
        self.manager.apply("restore")
        paths = (self.manager.startup, self.manager.script, self.manager.receipt,
                 self.home / ".local/bin/agent-launch")
        before = {path: path.read_bytes() for path in paths}
        original = self.installer.record_path.read_bytes()
        for fault in ("invalid-json", "unsafe-release", "invalid-ownership"):
            with self.subTest(fault=fault):
                record = json.loads(original)
                if fault == "unsafe-release":
                    record["package_root"] = str(self.root / "foreign-release")
                elif fault == "invalid-ownership":
                    record["launcher"]["path"] = str(self.root / "foreign-launcher")
                self.installer.record_path.write_bytes(
                    b"not-json" if fault == "invalid-json" else json.dumps(record).encode())
                result = self.cli("uninstall", check=False)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before, {path: path.read_bytes() if path.exists() else None for path in paths})
        self.assert_globals()

    def test_install_replay_refuses_changed_parent_before_any_projection(self):
        custom = self.home / "zsh-config"
        custom.mkdir()
        env = {**self.env, "ZDOTDIR": str(custom)}
        manager = ShellIntegration(env, SOURCE)
        manager.startup.write_bytes(self.original)
        manager.apply("restore")
        manager.startup.write_bytes(self.original)
        installer = InstructionsInstaller(SOURCE, env)
        original_write = installer._write_planned

        def interrupted(path, version, mode):
            if path == manager.startup:
                raise OSError("fixture pre-shell crash")
            original_write(path, version, mode)

        with patch.object(installer, "_write_planned", interrupted):
            with self.assertRaisesRegex(OSError, "pre-shell crash"):
                installer.install()
        custom.rename(self.root / "original-zsh-config")
        foreign = self.root / "foreign-zsh-config"
        foreign.mkdir()
        (foreign / ".zshrc").write_bytes(self.original)
        custom.symlink_to(foreign, target_is_directory=True)
        with self.assertRaises(RuntimeError) as failure:
            InstructionsInstaller(SOURCE, env).install()
        self.assertEqual(self.original, (foreign / ".zshrc").read_bytes())
        self.assertIn("symlink", f"{failure.exception} {failure.exception.__cause__}")
        self.assertTrue(pending_status(self.state)["pending"])

    def test_planned_write_and_delete_recheck_parent_symlinks(self):
        parent = self.root / "projection"
        parent.mkdir()
        target = parent / "file"
        target.write_bytes(b"before")
        before = self.installer._file_version(target)
        parent.rename(self.root / "original-projection")
        foreign = self.root / "foreign-projection"
        foreign.mkdir()
        (foreign / "file").write_bytes(b"before")
        parent.symlink_to(foreign, target_is_directory=True)
        self.assertFalse(self.installer._matches_version(target, before))
        for after in (self.installer._planned_version(b"after"), {"exists": False}):
            with self.subTest(after=after):
                with self.assertRaisesRegex(RuntimeError, "symlink"):
                    self.installer._write_planned(target, after, 0o600)
                self.assertEqual(b"before", (foreign / "file").read_bytes())

    @unittest.skipUnless(sys.platform == "darwin", "macOS system path aliases")
    def test_system_temp_alias_is_not_a_user_symlink_redirect(self):
        try:
            relative = self.root.relative_to("/private/var")
        except ValueError:
            self.skipTest("temporary root does not use the macOS /var alias")
        root = Path("/var") / relative / "system-alias-case"
        home, state, user = root / "home", root / "state", root / "user"
        home.mkdir(parents=True)
        env = {**self.env, "HOME": str(home), "ZDOTDIR": str(home),
               "CODEX_HOME": str(home / ".codex"), "CLAUDE_CONFIG_DIR": str(home / ".claude"),
               "AGENT_BIOS_STATE_DIR": str(state), "AGENT_BIOS_INSTRUCTIONS_DIR": str(user)}
        installer = InstructionsInstaller(SOURCE, env)
        installer.install("none")
        manager = ShellIntegration(env, SOURCE)
        self.assertTrue(manager.apply("restore")["enabled"])
        installer.install()
        preview = installer.reset()
        installer.reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        self.assertFalse(manager.script.exists())
        installer.uninstall()

    def test_restore_requires_a_real_private_installation(self):
        (self.state / "runtime/private-install.json").write_text("{}")
        with self.assertRaisesRegex(ShellIntegrationError, "private installation"):
            self.manager.apply("restore")
        self.assertFalse(self.manager.script.exists())
        self.assertEqual(self.original, self.manager.startup.read_bytes())

    def test_record_is_read_once_per_plan(self):
        self.manager.apply("restore")
        original = self.manager._read
        reads = 0

        def count(path):
            nonlocal reads
            if path == self.manager.receipt:
                reads += 1
            return original(path)

        self.manager._read = count
        self.manager.plan("remove")
        self.assertEqual(1, reads)

    def test_custom_zdotdir_is_respected(self):
        custom = self.home / "shell settings"
        custom.mkdir()
        other = ShellIntegration({**self.env, "ZDOTDIR": str(custom)}, SOURCE)
        other.apply("restore")
        self.assertIn(START, (custom / ".zshrc").read_bytes())
        self.assertEqual(self.original, self.manager.startup.read_bytes())
        with self.assertRaisesRegex(ShellIntegrationError, "HOME/ZDOTDIR"):
            self.manager.apply("remove")
        other.apply("remove")
        self.assertFalse((custom / ".zshrc").exists())

    def test_unknown_or_edited_script_is_preserved(self):
        self.manager.script.parent.mkdir(parents=True, exist_ok=True)
        self.manager.script.write_bytes(b"user script\n")
        for action in ("restore", "remove"):
            with self.assertRaisesRegex(ShellIntegrationError, "unowned or edited"):
                self.manager.apply(action)
        self.assertEqual(b"user script\n", self.manager.script.read_bytes())
        self.assertEqual(self.original, self.manager.startup.read_bytes())
        self.manager.script.unlink()
        self.manager.apply("restore")
        self.manager.script.write_bytes(b"my edited script\n")
        with self.assertRaisesRegex(ShellIntegrationError, "unowned or edited"):
            self.manager.apply("remove")
        self.assertIn(START, self.manager.startup.read_bytes())

    def test_edited_block_and_symlink_are_refused(self):
        self.manager.apply("restore")
        edited = self.manager.startup.read_bytes().replace(b"&& source", b"&& .")
        self.manager.startup.write_bytes(edited)
        with self.assertRaisesRegex(ShellIntegrationError, "block was edited"):
            self.manager.apply("remove")
        self.assertEqual(edited, self.manager.startup.read_bytes())
        self.manager.startup.unlink()
        target = self.root / "foreign"
        target.write_bytes(b"foreign data")
        self.manager.startup.symlink_to(target)
        with self.assertRaisesRegex(ShellIntegrationError, "symlink"):
            self.manager.apply("restore")
        self.assertEqual(b"foreign data", target.read_bytes())

    def test_mid_write_failure_rolls_back_and_keeps_verified_backup(self):
        real_write = self.manager._write
        failed = False

        def interrupted(path, body, mode):
            nonlocal failed
            real_write(path, body, mode)
            if path == self.manager.startup and not failed:
                failed = True
                raise OSError("fixture write interruption")

        self.manager._write = interrupted
        with self.assertRaisesRegex(ShellIntegrationError, "originals saved"):
            self.manager.apply("restore")
        self.assertEqual(self.original, self.manager.startup.read_bytes())
        self.assertFalse(self.manager.script.exists())
        backups = list((self.state / "runtime/shell-backups").glob("*/paths.json"))
        self.assertEqual(1, len(backups))
        rows = json.loads(backups[0].read_text())
        startup = next(row for row in rows if row["path"] == str(self.manager.startup))
        self.assertEqual(self.original, (backups[0].parent / startup["file"]).read_bytes())
        self.assert_globals()

    def test_new_user_shell_text_survives_removal(self):
        self.manager.apply("restore")
        self.manager.startup.write_bytes(b"# added before connection\n" + self.manager.startup.read_bytes()
                                        + b"\n# added after connection\n")
        self.assertEqual([], self.manager.apply("restore")["changed_paths"])
        self.manager.apply("remove")
        self.assertEqual(b"# added before connection\n" + self.original + b"\n# added after connection\n",
                         self.manager.startup.read_bytes())

    def test_install_keeps_opt_in_and_reset_removes_it(self):
        self.manager.apply("restore")
        self.installer.install()
        self.assertTrue(self.manager.status()["enabled"])
        self.assertTrue(self.installer.verify()["stored"])
        preview = self.installer.reset()
        self.assertIn(str(self.manager.startup), preview["restore_defaults"])
        self.installer.reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        self.assertFalse(self.manager.status()["enabled"])
        self.assertEqual(self.original, self.manager.startup.read_bytes())
        self.assertFalse(self.manager.receipt.exists())
        self.assert_globals()

    def test_uninstall_removes_only_owned_shell_connection(self):
        self.manager.apply("restore")
        self.installer.uninstall()
        self.assertFalse(self.manager.script.exists())
        self.assertEqual(self.original, self.manager.startup.read_bytes())
        self.assert_globals()

    def test_noninteractive_and_argument_calls_add_no_permission_flags(self):
        self.manager.apply("restore")
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        log = self.root / "argv.jsonl"
        for command in ("claude", "codex", "launcher"):
            path = fakebin / command
            path.write_text(f"#!{sys.executable}\nimport json,sys\nwith open({str(log)!r},'a') as f: f.write(json.dumps([{command!r},*sys.argv[1:]])+'\\n')\n")
            path.chmod(0o755)
        env = {**self.env, "PATH": str(fakebin) + os.pathsep + self.env["PATH"],
               "AGENT_LAUNCH_BIN": str(fakebin / "launcher")}
        command = f"source {shlex.quote(str(self.manager.script))}\nclaude\nclaude --no-tui --version\ncodex exec probe\n"
        subprocess.run(["/bin/zsh", "-dfc", command], env=env, check=True, capture_output=True)
        self.assertEqual([["claude"], ["claude", "--version"], ["codex", "exec", "probe"]],
                         [json.loads(row) for row in log.read_text().splitlines()])

    def test_unavailable_private_launcher_preserves_native_bypass_arguments(self):
        self.manager.apply("restore")
        (self.home / ".local/bin/agent-launch").chmod(0o644)
        fakebin = self.root / "fallback-bin"
        fakebin.mkdir()
        log = self.root / "fallback-args.jsonl"
        for host in ("claude", "codex"):
            target = fakebin / host
            target.write_text(f"#!{sys.executable}\nimport json,sys\nwith open({str(log)!r},'a') as f: f.write(json.dumps([{host!r},*sys.argv[1:]])+'\\n')\n")
            target.chmod(0o755)
        env = {**self.env, "PATH": str(fakebin) + os.pathsep + self.env["PATH"]}
        command = f"source {shlex.quote(str(self.manager.script))}; claude --no-tui --version; codex --no-tui --version"
        subprocess.run(["/bin/zsh", "-dfc", command], env=env, check=True, capture_output=True)
        self.assertEqual([["claude", "--version"], ["codex", "--version"]],
                         [json.loads(row) for row in log.read_text().splitlines()])
        launcher = self.home / ".local/bin/agent-launch"
        for fault in ("nonexecutable", "directory"):
            with self.subTest(fault=fault):
                if fault == "directory":
                    launcher.unlink()
                    launcher.mkdir()
                log.write_text("")
                master, slave = pty.openpty()
                try:
                    result = subprocess.run([
                        "/bin/zsh", "-dfi", "-c",
                        f"source {shlex.quote(str(self.manager.script))}; claude; codex",
                    ], env=env, stdin=slave, stdout=slave, stderr=slave, timeout=10)
                finally:
                    os.close(slave)
                    os.close(master)
                self.assertEqual(0, result.returncode)
                self.assertEqual([["claude"], ["codex"]],
                                 [json.loads(row) for row in log.read_text().splitlines()])

    def test_interactive_bare_calls_reach_launcher_then_withdraw_on_remove(self):
        self.manager.apply("restore")
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        log = self.root / "calls.jsonl"
        for name in ("claude", "codex", "launcher"):
            target = fakebin / name
            target.write_text(f"#!{sys.executable}\nimport json,sys\nwith open({str(log)!r},'a') as f: f.write(json.dumps([{name!r},*sys.argv[1:]])+'\\n')\n")
            target.chmod(0o755)
        env = {**self.env, "PATH": str(fakebin) + os.pathsep + self.env["PATH"],
               "AGENT_LAUNCH_BIN": str(fakebin / "launcher"), "PS1": "SHELL_TEST> "}
        master, slave = pty.openpty()
        process = subprocess.Popen(["/bin/zsh", "-dfi"], stdin=slave, stdout=slave, stderr=slave, env=env)
        os.close(slave)

        def wait_calls(count):
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if log.exists() and len(log.read_text().splitlines()) >= count:
                    return
                ready, _, _ = select.select([master], [], [], 0.05)
                if ready:
                    os.read(master, 65536)
            self.fail(f"zsh did not dispatch {count} calls")

        try:
            os.write(master, f"source {shlex.quote(str(self.manager.script))}\nclaude\ncodex\nclaude --version\n".encode())
            wait_calls(3)
            self.manager.apply("remove")
            os.write(master, b"claude\ncodex\n")
            wait_calls(5)
            self.assertEqual([["launcher", "claude"], ["launcher", "codex"], ["claude", "--version"],
                              ["claude"], ["codex"]], [json.loads(row) for row in log.read_text().splitlines()])
            os.write(master, b"exit\n")
            # Drain terminal output while zsh exits; a PTY writer can otherwise
            # wait for this very reader to consume its final prompt bytes.
            deadline = time.monotonic() + 1
            while process.poll() is None and time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.05)
                if ready:
                    try:
                        os.read(master, 65536)
                    except OSError:
                        break
        finally:
            if process.poll() is None:
                # Interactive zsh may ignore SIGTERM. This PID belongs only to
                # the fixture; always reap it even when an assertion failed.
                process.kill()
                process.wait(timeout=5)
            os.close(master)


class ShellTUITests(ShellFixture, unittest.IsolatedAsyncioTestCase):
    async def test_real_mode_menu_restores_and_removes_connection(self):
        await self.drive_menu(False)

    async def test_dry_run_menu_does_not_restore(self):
        await self.drive_menu(True)

    async def drive_menu(self, preview):
        from textual.widgets import OptionList
        spec = importlib.util.spec_from_file_location("shell_test_launcher", SOURCE / "launch/agent-launch.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        with patch.dict(os.environ, self.env, clear=True):
            spec.loader.exec_module(module)
            config_path = self.home / ".config/agent-launch/profiles.toml"
            module.load_catalogs(config_path)
            config = module.load_config(config_path)
            app = module._build_app_class()(config, "claude", None, False, config_path, preview)
            async with app.run_test(size=(120, 42)) as pilot:
                async def choose_value(value):
                    for _ in range(150):
                        options = getattr(app.screen, "_options", [])
                        found = [i for i, option in enumerate(options) if option.value == value]
                        if found:
                            screen = app.screen
                            # A pushed Screen exposes _options before on_mount
                            # installs its default highlight. Wait for that real
                            # UI lifecycle before simulating the user's choice.
                            await pilot.pause()
                            if app.screen is not screen or not screen.is_mounted:
                                continue
                            choices = screen.query_one(OptionList)
                            choices.focus()
                            await pilot.pause()
                            choices.highlighted = found[0]
                            await pilot.press("enter")
                            await pilot.pause()
                            return
                        await asyncio.sleep(0.02)
                    self.fail(f"real launcher screen did not expose {value}")

                await choose_value(module.SHELL_CONNECTION_OPTION)
                await choose_value("restore")
                await choose_value("apply")
                await choose_value("back")
                self.assertEqual(not preview, self.manager.status()["enabled"])
                if not preview:
                    await choose_value("remove")
                    await choose_value("apply")
                    await choose_value("back")
                    self.assertFalse(self.manager.status()["enabled"])
                await choose_value("back")
                await pilot.press("q")
                await pilot.pause()
            self.assertEqual(self.original, self.manager.startup.read_bytes())
            self.assert_globals()


if __name__ == "__main__":
    unittest.main()
