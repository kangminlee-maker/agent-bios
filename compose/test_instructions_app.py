"""Isolated native discovery ownership and explicit Codex app context delivery."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from instructions_app import AppBridge, AppError, AppSessions
from instructions_install import InstructionsInstaller
from instructions_store import InstructionsStore
from instructions_transaction import TransactionError, confirmed_release


SOURCE = Path(__file__).resolve().parents[1]


class AppInstructionsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="agent-bios-app-")
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.repo = self.root / "package"
        self.state = self.root / "custom-state"
        self.user = self.root / "custom-user"
        self.project = self.root / "project"
        self.env = {**os.environ, "HOME": str(self.home), "AGENT_BIOS_STATE_DIR": str(self.state),
                    "AGENT_BIOS_INSTRUCTIONS_DIR": str(self.user), "CODEX_THREAD_ID": "app-task-one",
                    "CLAUDE_CONFIG_DIR": str(self.home / ".claude"), "CODEX_HOME": str(self.home / ".codex"),
                    "ZDOTDIR": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"}
        package = json.loads((SOURCE / "package.json").read_text(encoding="utf-8"))
        files = set(package["files"]) | {"compose/instructions_app.py", "compose/app_bridge/"}
        files.discard("provenance.json")
        for relative in sorted(files):
            source, target = SOURCE / relative, self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(source, target)
        package["files"] = sorted(files)
        (self.repo / "package.json").write_text(json.dumps(package), encoding="utf-8")
        self.protected = {}
        for path in (self.home / ".codex/AGENTS.md", self.home / ".claude/CLAUDE.md",
                     self.project / "AGENTS.md", self.project / "CLAUDE.md",
                     self.home / ".codex/config.toml", self.home / ".claude/settings.json"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("User-owned " + path.name + "\n", encoding="utf-8")
            self.protected[path] = path.read_bytes()
        self.installer = InstructionsInstaller(self.repo, self.env)
        self.installer.install("builder-base")
        self.bridge = AppBridge(self.repo, self.env)
        self.sessions = AppSessions(self.repo, self.env)

    def tearDown(self):
        self.temporary.cleanup()

    def assert_protected(self):
        for path, value in self.protected.items():
            self.assertEqual(value, path.read_bytes(), str(path))

    def helper(self, *args, env=None, payload=None):
        return subprocess.run([sys.executable, str(self.bridge.target / "scripts/bridge.py"), *args],
                              env=env or self.env, cwd=self.project, text=True,
                              input=payload, capture_output=True, timeout=45)

    def store(self):
        return InstructionsStore(confirmed_release(self.state), self.state, self.user)

    def add_personal(self, text="UNIQUE-APP-PERSONAL-CONTENT"):
        store = self.store()
        plan = store.plan({"operation": "create", "item": {"title": "App context fixture",
                           "body": text, "surface": "always", "tier": "env-personal",
                           "domains": ["personal"], "kind": "rule"}})
        store.apply(plan["plan_id"], expected_revision=plan["expected_revision"])

    def test_registration_is_explicit_only_and_preserves_native_state(self):
        self.assertFalse(self.bridge.status()["registered"])
        self.assertFalse(os.path.lexists(self.bridge.target))
        self.add_personal()
        dry = self.bridge.register(dry_run=True)
        self.assertTrue(dry["changed"])
        self.assertFalse(os.path.lexists(self.bridge.target))
        result = self.bridge.register()
        self.assertTrue(result["registered"])
        self.assertTrue(self.bridge.target.is_symlink())
        self.assertEqual(self.home / ".agents/skills/agent-bios", self.bridge.target)
        self.assertEqual("unverified", result["native_discovery"])
        self.assertIn("allow_implicit_invocation: false", (self.bridge.target / "agents/openai.yaml").read_text())
        all_registered = b"".join(path.read_bytes() for path in Path(result["generation"]).rglob("*") if path.is_file())
        self.assertNotIn(b"UNIQUE-APP-PERSONAL-CONTENT", all_registered)
        self.assertFalse(self.bridge.register()["changed"])
        self.assertFalse(self.sessions.status()["enabled"])
        self.assertFalse((self.state / "sessions/app-context").exists())
        self.assert_protected()
        self.assertTrue(self.bridge.unregister()["changed"])
        self.assertFalse(os.path.lexists(self.bridge.target))
        self.assertTrue(Path(result["generation"]).is_dir())
        self.assertFalse(self.bridge.unregister()["changed"])
        self.assert_protected()

    def test_legacy_member_inventory_remains_owned_and_refresh_keeps_original_bytes(self):
        current = Path(self.bridge.register()["generation"])
        files = {path.relative_to(current).as_posix(): path.read_bytes()
                 for path in current.rglob("*") if path.is_file()}
        files["scripts/corpus_transaction.py"] = files.pop("scripts/instructions_transaction.py")
        digest = hashlib.sha256()
        for name, body in sorted(files.items()):
            digest.update(name.encode() + b"\0" + body + b"\0")
        legacy = self.bridge.generations / digest.hexdigest()
        for name, body in files.items():
            path = legacy / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        self.bridge.target.unlink()
        self.bridge.target.symlink_to(legacy)
        self.assertTrue(self.bridge.status()["registered"])
        refreshed = self.bridge.refresh_registration()
        self.assertTrue(refreshed["registered"])
        self.assertTrue(refreshed["changed"])
        self.assertEqual(current, Path(refreshed["generation"]))
        self.assertEqual(files, {path.relative_to(legacy).as_posix(): path.read_bytes()
                                 for path in legacy.rglob("*") if path.is_file()})
        self.bridge.target.unlink()
        self.bridge.target.symlink_to(legacy)
        (legacy / "SKILL.md").write_text("corrupted historical bridge")
        self.assertFalse(self.bridge.status()["registered"])
        with self.assertRaisesRegex(AppError, "changed app skill generation"):
            self.bridge.unregister()
        self.assertTrue(self.bridge.target.is_symlink())

    def test_helper_normalizes_owned_outgoing_aliases_after_legacy_only_input(self):
        self.bridge.register()
        env = dict(self.env)
        env.pop("AGENT_BIOS_INSTRUCTIONS_DIR", None)
        env.pop("AGENT_BIOS_PRIVATE_INSTRUCTIONS", None)
        env["AGENT_BIOS_CORPUS_DIR"] = str(self.user) + "/."
        env["AGENT_BIOS_PRIVATE_CORPUS"] = "0"
        result = self.helper("session", "status", "--json", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(json.loads(result.stdout)["enabled"])

    def test_directory_foreign_link_and_ancestor_redirect_are_preserved(self):
        self.bridge.target.mkdir(parents=True)
        user_skill = self.bridge.target / "SKILL.md"
        user_skill.write_text("User skill", encoding="utf-8")
        for operation in (self.bridge.register, self.bridge.unregister):
            with self.assertRaisesRegex(AppError, "unowned"):
                operation()
        self.assertFalse(self.bridge.has_owned_registration())
        self.assertFalse(self.bridge.refresh_registration()["managed"])
        self.assertNotIn("needs_action", self.bridge.managed_status())
        self.assertEqual("User skill", user_skill.read_text())
        shutil.rmtree(self.bridge.target)
        foreign = self.root / "foreign"
        foreign.mkdir()
        self.bridge.target.symlink_to(foreign)
        with self.assertRaisesRegex(AppError, "unowned"):
            self.bridge.register()
        self.assertEqual(str(foreign), os.readlink(self.bridge.target))
        self.bridge.target.unlink()
        self.bridge.target.parent.rmdir()
        self.bridge.target.parent.symlink_to(foreign)
        with self.assertRaises(TransactionError):
            self.bridge.register()
        self.assertEqual([], list(foreign.iterdir()))
        self.assert_protected()

    def test_changed_registration_is_not_overwritten_or_removed(self):
        self.bridge.register()
        skill = self.bridge.target / "SKILL.md"
        skill.write_text(skill.read_text() + "\nUser addition\n")
        self.assertTrue(self.bridge.status()["needs_action"])
        for operation in (self.bridge.register, self.bridge.unregister):
            with self.assertRaisesRegex(AppError, "changed"):
                operation()
        self.assertTrue(self.bridge.has_owned_registration())
        self.assertTrue(self.bridge.refresh_registration()["needs_action"])
        response = self.helper("session", "status", "--json")
        self.assertEqual(2, response.returncode)
        self.assertIn("content changed", response.stderr)
        self.assertIn("User addition", skill.read_text())
        self.assert_protected()

    def test_bridge_resolves_latest_release_and_captured_roots_without_path_cli(self):
        first = self.bridge.register()
        bootstrap = self.repo / "compose/bootstrap/SKILL.md"
        bootstrap.write_text(bootstrap.read_text() + "\nCURRENT-PRIVATE-BOOTSTRAP\n")
        self.installer.install()
        decoy = self.root / "decoy-bin"
        decoy.mkdir()
        cli = decoy / "agent-bios"
        cli.write_text("#!/bin/sh\necho PATH-DECOY\nexit 90\n")
        cli.chmod(0o755)
        env = {**self.env, "PATH": str(decoy) + os.pathsep + os.environ.get("PATH", ""),
               "HOME": str(self.root / "wrong-home"),
               "AGENT_BIOS_STATE_DIR": str(self.root / "wrong-state"),
               "AGENT_BIOS_INSTRUCTIONS_DIR": str(self.root / "wrong-user")}
        response = self.helper("bootstrap", env=env)
        self.assertEqual(0, response.returncode, response.stderr)
        self.assertIn("CURRENT-PRIVATE-BOOTSTRAP", response.stdout)
        response = self.helper("session", "off", "--json", env=env)
        self.assertEqual(0, response.returncode, response.stderr)
        self.assertEqual("app-task-one", json.loads(response.stdout)["session_id"])
        self.assertTrue((self.state / "sessions/app-context/app-task-one.json").is_file())
        self.assertFalse((self.root / "wrong-state").exists())
        self.assertFalse((self.root / "wrong-user").exists())
        self.assertTrue(Path(first["generation"]).exists())
        self.assert_protected()

    def test_bridge_preserves_only_the_configured_managed_runtime_override(self):
        selected = self.root / "custom managed runtime"
        selected_env = {**self.env, "AGENT_LAUNCH_VENV": str(selected),
                        "UNRELATED_APP_SECRET": "DO-NOT-STORE-THIS-ENVIRONMENT-VALUE"}
        bridge = AppBridge(self.repo, selected_env)
        registered = bridge.register()
        config = json.loads((bridge.target / "bridge.json").read_text())
        self.assertEqual(str(selected), config["launch_venv"])
        self.assertNotIn("DO-NOT-STORE-THIS-ENVIRONMENT-VALUE", json.dumps(config))
        env = {**self.env, "AGENT_LAUNCH_VENV": str(self.root / "wrong-runtime")}
        response = self.helper("session", "use", "--json", env=env)
        self.assertEqual(0, response.returncode, response.stderr)
        self.assertEqual(str(selected), json.loads(response.stdout)["runtime"]["environment"]["AGENT_LAUNCH_VENV"])
        without_override = {key: value for key, value in self.env.items() if key != "AGENT_LAUNCH_VENV"}
        refreshed = AppBridge(self.repo, without_override).refresh_registration()
        self.assertTrue(refreshed["registered"])
        self.assertEqual(registered["generation"], refreshed["generation"])
        direct = AppSessions(self.repo, without_override).use(cwd=self.project)
        self.assertEqual(str(selected), direct["runtime"]["environment"]["AGENT_LAUNCH_VENV"])
        cleared = AppBridge(self.repo, {**self.env, "AGENT_LAUNCH_VENV": ""}).register()
        self.assertNotEqual(registered["generation"], cleared["generation"])
        self.assertEqual("", json.loads((bridge.target / "bridge.json").read_text())["launch_venv"])
        self.assert_protected()

    def test_setup_forwarding_uses_confirmed_release_and_saved_roots_without_context(self):
        self.add_personal("SETUP-MUST-NOT-DELIVER-THIS-CONTENT")
        selected = self.root / "chosen runtime"
        selected_env = {**self.env, "AGENT_LAUNCH_VENV": str(selected)}
        bridge = AppBridge(self.repo, selected_env)
        bridge.register()
        probe = ("import json, os, sys; print(json.dumps({'argv': sys.argv[1:], 'roots': "
                 "{key: os.environ.get(key) for key in ('HOME', 'AGENT_BIOS_STATE_DIR', "
                 "'AGENT_BIOS_INSTRUCTIONS_DIR', 'AGENT_BIOS_PACKAGE_ROOT', 'AGENT_LAUNCH_VENV', "
                 "'AGENT_BIOS_LEGACY_INSTALL')}}))")
        (self.repo / "install.sh").write_text("#!/bin/bash\nexec " + shlex.quote(sys.executable)
                                               + " -c " + shlex.quote(probe) + " \"$@\"\n")
        InstructionsInstaller(self.repo, selected_env).install()
        decoy = self.root / "decoy-bin"
        decoy.mkdir()
        (decoy / "agent-bios").write_text("#!/bin/sh\nexit 93\n")
        (decoy / "agent-bios").chmod(0o755)
        env = {**self.env, "PATH": str(decoy) + os.pathsep + os.environ.get("PATH", ""),
               "HOME": str(self.root / "wrong-home"),
               "AGENT_BIOS_STATE_DIR": str(self.root / "wrong-state"),
               "AGENT_BIOS_INSTRUCTIONS_DIR": str(self.root / "wrong-user"),
               "AGENT_LAUNCH_VENV": str(self.root / "wrong-runtime"),
               "AGENT_BIOS_LEGACY_INSTALL": "1"}
        env.pop("CODEX_THREAD_ID", None)
        response = self.helper("setup", "plan", "--language", "ja", "--input", "review choice.json", env=env)
        self.assertEqual(0, response.returncode, response.stderr)
        result = json.loads(response.stdout)
        self.assertEqual(["setup", "plan", "--language", "ja", "--input", "review choice.json"], result["argv"])
        self.assertEqual(str(self.home), result["roots"]["HOME"])
        self.assertEqual(str(self.state), result["roots"]["AGENT_BIOS_STATE_DIR"])
        self.assertEqual(str(self.user), result["roots"]["AGENT_BIOS_INSTRUCTIONS_DIR"])
        self.assertEqual(str(selected), result["roots"]["AGENT_LAUNCH_VENV"])
        self.assertEqual(str(confirmed_release(self.state)), result["roots"]["AGENT_BIOS_PACKAGE_ROOT"])
        self.assertEqual("0", result["roots"]["AGENT_BIOS_LEGACY_INSTALL"])
        self.assertNotIn("SETUP-MUST-NOT-DELIVER-THIS-CONTENT", response.stdout)
        self.assertFalse((self.state / "sessions/app-context").exists())
        self.assertFalse((self.root / "wrong-state").exists())
        self.assertFalse((self.root / "wrong-user").exists())
        self.assertFalse((self.root / "wrong-home").exists())
        self.assert_protected()

    def test_setup_bridge_does_not_add_an_arbitrary_command_escape(self):
        self.bridge.register()
        for command in ("install", "exec", "bash", "setup-guide"):
            with self.subTest(command=command):
                response = self.helper(command, "session", "use")
                self.assertEqual(2, response.returncode)
                self.assertIn("bridge supports", response.stderr)
                self.assertEqual("", response.stdout)
        self.assertFalse((self.state / "sessions/app-context").exists())
        self.assert_protected()

    def test_real_setup_start_and_inspect_through_bridge_are_read_only(self):
        self.add_personal("SETUP-INSPECTION-IS-NOT-INSTRUCTIONS-USE")
        self.bridge.register()
        before = {str(path): path.read_bytes() for root in (self.state, self.user)
                  for path in root.rglob("*") if path.is_file()}
        env = {**self.env, "HOME": str(self.root / "wrong-home"),
               "AGENT_BIOS_STATE_DIR": str(self.root / "wrong-state"),
               "AGENT_BIOS_INSTRUCTIONS_DIR": str(self.root / "wrong-user")}
        env.pop("CODEX_THREAD_ID", None)
        start = self.helper("setup", "start", env=env)
        self.assertEqual(0, start.returncode, start.stderr)
        started = json.loads(start.stdout)
        release = confirmed_release(self.state).resolve()
        self.assertEqual("agent-bios-setup-start", started["kind"])
        self.assertEqual(str(release / "compose/setup/START.md"), started["guide_path"])
        self.assertTrue(Path(started["guide_path"]).is_file())
        self.assertEqual(["/bin/bash", str(release / "install.sh"), "setup"], started["setup_argv"])
        self.assertEqual(str(self.home.resolve()), started["context"]["home"])
        self.assertNotIn("dependencies", started)
        inspected = self.helper("setup", "inspect", "--language", "ja", env=env)
        self.assertEqual(0, inspected.returncode, inspected.stderr)
        result = json.loads(inspected.stdout)
        self.assertEqual("agent-bios-setup-inspection", result["kind"])
        self.assertEqual("ja", result["language"])
        self.assertTrue(result["dependencies"])
        self.assertTrue(result["choices"])
        self.assertFalse(result["default_plan"]["app_bridge"])
        self.assertEqual([], result["default_plan"]["dependencies"])
        self.assertEqual(str(self.state.resolve()), result["context"]["state_dir"])
        self.assertEqual(str(self.user.resolve()), result["context"]["user_dir"])
        self.assertNotIn("SETUP-INSPECTION-IS-NOT-INSTRUCTIONS-USE", start.stdout + inspected.stdout)
        self.assertEqual(before, {str(path): path.read_bytes() for root in (self.state, self.user)
                                 for path in root.rglob("*") if path.is_file()})
        self.assertFalse((self.state / "sessions/app-context").exists())
        self.assertFalse((self.root / "wrong-home").exists())
        self.assert_protected()

    def test_refresh_does_not_opt_in_and_keeps_changed_native_file(self):
        self.assertFalse(self.bridge.refresh_registration()["registered"])
        self.bridge.register()
        old = self.bridge.target.resolve()
        skill = self.repo / "compose/app_bridge/SKILL.md"
        skill.write_text(skill.read_text() + "\nUpdated bridge fixture\n")
        self.installer.install()
        refreshed = self.bridge.refresh_registration()
        self.assertTrue(refreshed["registered"])
        self.assertNotEqual(old, self.bridge.target.resolve())
        self.assertTrue(old.exists())
        self.bridge.target.unlink()
        self.bridge.target.mkdir()
        (self.bridge.target / "notes.md").write_text("keep")
        with self.assertRaisesRegex(AppError, "unowned"):
            self.bridge.unregister()
        self.assertEqual("keep", (self.bridge.target / "notes.md").read_text())
        self.assert_protected()

    def test_corrupt_private_release_blocks_helper_without_falling_back(self):
        self.bridge.register()
        release = confirmed_release(self.state)
        target = release / "compose/bootstrap/SKILL.md"
        target.write_text(target.read_text() + "\ncorruption\n")
        response = self.helper("session", "use", "--json")
        self.assertEqual(2, response.returncode)
        self.assertIn("digest", response.stderr)
        self.assertFalse((self.state / "sessions/app-context").exists())

    def test_session_status_and_off_before_use_return_no_instructions(self):
        self.add_personal()
        before = self.sessions.status()
        self.assertFalse(before["enabled"])
        self.assertFalse(before["ever_delivered"])
        self.assertNotIn("instruction_text", before)
        self.assertFalse((self.state / "sessions/app-context").exists())
        off = self.sessions.off()
        self.assertFalse(off["clean_exclusion_requires_new_session"])
        self.assertNotIn("UNIQUE-APP-PERSONAL-CONTENT", json.dumps(off))
        preview = self.sessions.preview(selection_mode="none")
        self.assertEqual(0, preview["instruction_characters"])
        self.assertFalse(self.sessions.use(selection_mode="none")["ever_delivered"])
        self.assertFalse((self.state / "sessions/pins").exists())
        self.assert_protected()

    def test_empty_installed_selection_does_not_claim_delivered_context(self):
        self.installer.install(selection_mode="none")
        preview = self.sessions.preview(cwd=self.project)
        self.assertEqual(0, preview["instruction_characters"])
        result = self.sessions.use(cwd=self.project, expected_content_ref=preview["content_ref"])
        self.assertFalse(result["enabled"])
        self.assertFalse(result["ever_delivered"])
        self.assertFalse(result["clean_exclusion_requires_new_session"])
        self.assertNotIn("instruction_text", result)
        self.assert_protected()

    def test_use_returns_exact_snapshot_with_honest_receipt_and_off_cannot_retract(self):
        self.add_personal()
        preview = self.sessions.preview(cwd=self.project)
        self.assertNotIn("instruction_text", preview)
        self.assertNotIn("UNIQUE-APP-PERSONAL-CONTENT", json.dumps(preview))
        self.assertFalse((self.state / "sessions/app-context").exists())
        used = self.sessions.use(cwd=self.project, expected_content_ref=preview["content_ref"])
        self.assertTrue(used["enabled"])
        self.assertIn("UNIQUE-APP-PERSONAL-CONTENT", used["instruction_text"])
        inventory = self.store().snapshot_inventory(used["content_ref"])
        self.assertEqual(inventory["instruction_text"], used["instruction_text"])
        self.assertEqual("returned-as-context", used["delivery"])
        self.assertFalse(used["native_activation"])
        self.assertEqual("unverified", used["host_loading"])
        self.assertFalse(inventory.get("assets"))
        digest = hashlib.sha256(used["instruction_text"].encode()).hexdigest()
        self.assertEqual(digest, used["deliveries"][-1]["instruction_sha256"])
        self.assertNotIn("instruction_text", self.sessions.status())
        off = self.sessions.off()
        self.assertFalse(off["enabled"])
        self.assertFalse(off["context_retracted"])
        self.assertTrue(off["clean_exclusion_requires_new_session"])
        self.assertEqual(used["deliveries"], off["deliveries"])
        self.assertFalse(self.sessions.status("different-task")["enabled"])
        self.assertFalse((self.state / "sessions/pins").exists())
        self.assert_protected()

    def test_stale_preview_does_not_deliver_and_old_context_remains_immutable(self):
        first = self.sessions.use(cwd=self.project)
        old_snapshot = Path(first["deliveries"][-1]["snapshot_path"])
        before = {path.relative_to(old_snapshot): path.read_bytes() for path in old_snapshot.rglob("*") if path.is_file()}
        preview = self.sessions.preview(cwd=self.project)
        self.add_personal("SECOND-APP-CONTEXT")
        with self.assertRaisesRegex(AppError, "preview changed"):
            self.sessions.use(cwd=self.project, expected_content_ref=preview["content_ref"])
        self.assertEqual(1, len(self.sessions.status()["deliveries"]))
        second = self.sessions.use(cwd=self.project)
        self.assertIn("SECOND-APP-CONTEXT", second["instruction_text"])
        self.assertEqual(2, len(second["deliveries"]))
        self.assertNotEqual(first["content_ref"], second["content_ref"])
        self.assertEqual(before, {path.relative_to(old_snapshot): path.read_bytes() for path in old_snapshot.rglob("*") if path.is_file()})
        self.assert_protected()

    def test_explicit_selected_domain_and_no_instructions_are_session_local(self):
        revision = self.store().status()["revision"]
        chosen = self.sessions.use(selection=["@agent-bios/core/builder-base"], selection_mode="selected", cwd=self.project)
        snapshot = self.store().snapshot_inventory(chosen["content_ref"])
        self.assertEqual(["@agent-bios/core/builder-base"], snapshot["inputs"]["selection"])
        self.assertEqual(revision, self.store().status()["revision"])
        self.assertFalse(self.sessions.use(selection_mode="none")["enabled"])
        self.assertFalse(self.sessions.status("another-task")["ever_delivered"])

    def test_direct_app_selection_is_strict_even_when_the_list_is_empty(self):
        self.add_personal("EXCLUDE-UNSELECTED-PERSONAL-RULE")
        before = self.store().status()
        preview = self.sessions.preview(selection=[], cwd=self.project)
        self.assertEqual("selected", preview["selection_mode"])
        empty = self.sessions.use(selection=[], cwd=self.project)
        inventory = self.store().snapshot_inventory(empty["content_ref"])
        self.assertEqual([], inventory["item_refs"])
        self.assertEqual("selected", inventory["inputs"]["selection_mode"])
        self.assertNotIn("EXCLUDE-UNSELECTED-PERSONAL-RULE", empty["instruction_text"])
        selected = self.sessions.use(selection=["@agent-bios/core/builder-base"], cwd=self.project)
        inventory = self.store().snapshot_inventory(selected["content_ref"])
        self.assertTrue(inventory["items"])
        self.assertTrue(all("builder-base" in item["domains"] for item in inventory["items"]))
        self.assertEqual(before, self.store().status())

    def test_cli_empty_domains_never_falls_back_and_nonempty_domains_are_trimmed(self):
        self.bridge.register()
        for value in ("", "   ", " , , "):
            for operation in ("preview", "use"):
                with self.subTest(value=value, operation=operation):
                    response = self.helper("session", operation, "--domains", value, "--json")
                    self.assertEqual(2, response.returncode)
                    self.assertIn("--no-instructions", response.stderr)
                    self.assertEqual("", response.stdout)
        self.assertFalse(self.sessions.status()["ever_delivered"])
        response = self.helper("session", "use", "--domains", " @agent-bios/core/builder-base , , ", "--json")
        self.assertEqual(0, response.returncode, response.stderr)
        inventory = self.store().snapshot_inventory(json.loads(response.stdout)["content_ref"])
        self.assertEqual(["@agent-bios/core/builder-base"], inventory["inputs"]["selection"])
        self.assertEqual("selected", inventory["inputs"]["selection_mode"])

    def test_invalid_task_ids_and_redirected_receipts_are_refused(self):
        for value in ("../outside", "a/b", "", "x" * 129):
            with self.assertRaisesRegex(AppError, "valid task id"):
                self.sessions.off(value)
        self.assertFalse((self.state / "sessions/app-context").exists())
        missing = AppSessions(self.repo, {key: value for key, value in self.env.items() if key != "CODEX_THREAD_ID"})
        with self.assertRaisesRegex(AppError, "CODEX_THREAD_ID"):
            missing.status()
        directory = self.state / "sessions/app-context"
        directory.mkdir(parents=True)
        victim = self.root / "victim.json"
        victim.write_text("keep")
        (directory / "app-task-one.json").symlink_to(victim)
        with self.assertRaises(TransactionError):
            self.sessions.off()
        self.assertEqual("keep", victim.read_text())

    def test_registered_helper_delivers_real_context_only_on_explicit_use(self):
        self.add_personal("HELPER-EXPLICIT-CONTEXT")
        self.bridge.register()
        status = self.helper("session", "status", "--json")
        self.assertEqual(0, status.returncode, status.stderr)
        self.assertNotIn("HELPER-EXPLICIT-CONTEXT", status.stdout)
        preview = self.helper("session", "preview", "--json")
        self.assertEqual(0, preview.returncode, preview.stderr)
        reference = json.loads(preview.stdout)["content_ref"]
        use = self.helper("session", "use", "--expected-content-ref", reference, "--json")
        self.assertEqual(0, use.returncode, use.stderr)
        delivered = json.loads(use.stdout)
        self.assertIn("HELPER-EXPLICIT-CONTEXT", delivered["instruction_text"])
        self.assertEqual(str(self.state), delivered["runtime"]["environment"]["AGENT_BIOS_STATE_DIR"])
        self.assertEqual(str(self.user), delivered["runtime"]["environment"]["AGENT_BIOS_INSTRUCTIONS_DIR"])
        self.assertEqual("0", delivered["runtime"]["environment"]["AGENT_BIOS_LEGACY_INSTALL"])
        self.assertEqual("learn", delivered["runtime"]["bridge_learn_argv"][-1])
        self.assertEqual(str(confirmed_release(self.state)), delivered["runtime"]["package_root"])
        learning_help = self.helper("learn", "--help")
        self.assertEqual(0, learning_help.returncode, learning_help.stderr)
        self.assertIn("--host", learning_help.stdout)
        self.assertTrue(self.sessions.status()["enabled"])
        self.assertTrue(self.bridge.status()["registered"])
        self.assert_protected()

    def test_bridge_learning_ignores_inherited_legacy_mode_and_preserves_globals(self):
        self.bridge.register()
        response = self.helper("learn", "--host", "codex", "--no-upload",
                               env={**self.env, "AGENT_BIOS_LEGACY_INSTALL": "1"},
                               payload=json.dumps({"lesson": "Use the active private runtime for task capture.",
                                                   "domain": "unclassified", "supporting_sessions": ["codex:abcd1234"]}))
        self.assertEqual(0, response.returncode, response.stderr)
        events = self.user / "learnings/codex/events.jsonl"
        self.assertTrue(events.is_file())
        self.assertEqual(1, len(events.read_text().splitlines()))
        self.assertFalse((self.home / ".codex/personal").exists())
        self.assertFalse((self.home / ".claude/personal").exists())
        self.assert_protected()

    @unittest.skipUnless(shutil.which("codex"), "Codex CLI required for isolated native discovery probe")
    def test_real_codex_discovers_and_removes_only_the_opted_in_skill(self):
        from instructions_session import CodexServer
        native_home = self.root / "isolated-codex"
        native_home.mkdir()
        env = {**self.env, "CODEX_HOME": str(native_home)}

        def discovered():
            with CodexServer(shutil.which("codex"), cwd=str(self.project), env=env) as server:
                response = server.call("skills/list", {"cwds": [str(self.project)], "forceReload": True}, timeout=20)
            groups = response.get("data", [])
            self.assertTrue(groups)
            self.assertFalse([error for group in groups for error in group.get("errors", [])])
            return [skill for group in groups for skill in group.get("skills", []) if skill.get("name") == "agent-bios"]

        self.assertEqual([], discovered())
        registered = self.bridge.register()
        skills = discovered()
        self.assertEqual(1, len(skills))
        self.assertEqual(Path(registered["generation"]).resolve() / "SKILL.md", Path(skills[0]["path"]))
        self.assertEqual("user", skills[0]["scope"])
        self.assertFalse(self.sessions.status()["ever_delivered"])
        self.bridge.unregister()
        self.assertEqual([], discovered())
        self.assert_protected()


if __name__ == "__main__":
    unittest.main()
