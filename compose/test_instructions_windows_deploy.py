"""Ownership, state-preservation and binding tests without mutating host PATH."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import windows_deploy as deploy


class Integration:
    def __init__(self):
        self.applied = []
        self.removed = []
        self.fail = False

    def apply(self, root, prior):
        if self.fail:
            raise OSError("simulated platform failure")
        self.applied.append(root)
        return {"owner": deploy.OWNER, "schema_version": 1, "root": str(root), "path_entry": str(root / "bin"), "shortcuts": {}}

    def remove(self, root, receipt):
        self.removed.append(root)
        return []


class Installer:
    def __init__(self, root):
        self.record_path = root / "runtime/private-install.json"
        self.installs, self.verifies, self.uninstalls = 0, 0, 0
        self.fail = False
        self.active = False
        self.env = None

    def install(self):
        self.installs += 1
        if self.fail:
            raise RuntimeError("native update failure")

    def verify(self):
        self.verifies += 1

    def uninstall(self):
        self.uninstalls += 1
        self.record_path.unlink(missing_ok=True)

    def _active_intents(self):
        return ["active"] if self.active else []


class MemoryWindowsIntegration(deploy.WindowsIntegration):
    """Use production PATH/shortcut ownership logic with isolated OS adapters."""
    def __init__(self, value="other;entry"):
        self.value = value
        self.kind = 2
        self.writes = []
        self.revision = 0

    def _path(self):
        return self.value, self.kind

    def _set_path(self, value, kind):
        self.value, self.kind = value, kind
        self.writes.append(value)

    def _shortcut(self, target, destination, command):
        self.revision += 1
        destination.write_text(str(target) + " " + command + " " + str(self.revision), encoding="utf-8")


class WindowsDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.source = self.base / "approved 한글 bundle"
        self.root = self.base / "Programs/app with spaces"
        self.state = self.base / "private state"
        self.python = self.base / "external python/python.exe"
        self.python.parent.mkdir()
        self.python.write_bytes(b"approved Python fixture")
        self.env = {"HOME": str(self.base / "home"), "AGENT_BIOS_STATE_DIR": str(self.state)}
        self.integration = Integration()
        self.installer = Installer(self.state)
        self.probes = []
        self.bundle()
        self.subject = self.deployment()

    def tearDown(self):
        self.temp.cleanup()

    def bundle(self, version="0.19.3"):
        for relative in ("package/compose", "dependencies", "commands"):
            (self.source / relative).mkdir(parents=True, exist_ok=True)
        (self.source / "package/package.json").write_text(json.dumps({"name": "agent-bios", "version": version}), encoding="utf-8")
        (self.source / "package/compose/runtime_entry.py").write_text("# entry fixture\n", encoding="utf-8")
        (self.source / "package/compose/native_cli.py").write_text("# native fixture\n", encoding="utf-8")
        (self.source / "dependencies/package.py").write_text("# dependencies fixture\n", encoding="utf-8")
        for name in deploy.COMMANDS:
            (self.source / "commands" / name).write_bytes(b"# signed static wrapper fixture\r\n")

    def factory(self, package, env):
        self.installer.env = env
        return self.installer

    def probe(self, binding):
        self.probes.append(binding)
        self.assertTrue(Path(binding["python"]["path"]).is_file())
        self.assertEqual(deploy._hash(Path(binding["python"]["path"])), binding["python"]["sha256"])

    def deployment(self, **kwargs):
        return deploy.Deployment(self.root, environ=self.env, integration=self.integration,
                                 installer_factory=self.factory, probe=kwargs.pop("probe", self.probe), **kwargs)

    def install(self, managed=None):
        return self.subject.install(self.source, self.python, managed)

    def configured(self):
        self.installer.record_path.parent.mkdir(parents=True, exist_ok=True)
        self.installer.record_path.write_text('{"selection":["@local/personal"]}', encoding="utf-8")

    def binding(self):
        return deploy._json(self.root / "deployment.json")

    def test_first_install_is_software_only_and_wrappers_are_exact_source_bytes(self):
        result = self.install()
        self.assertTrue(result["configuration_pending"])
        self.assertFalse(result["private_environment_updated"])
        self.assertEqual(self.installer.installs, 0)
        self.assertEqual(self.binding()["python"]["managed_root"], None)
        for name in deploy.COMMANDS:
            self.assertEqual((self.root / "bin" / name).read_bytes(), (self.source / "commands" / name).read_bytes())
        self.assertEqual(self.subject.verify()["version"], "0.19.3")

    def test_configured_update_calls_native_preserving_selection_and_runtime_identity(self):
        self.install()
        self.configured()
        before = self.installer.record_path.read_bytes()
        self.bundle("0.19.4")
        previous = dict(os.environ)
        result = self.install()
        self.assertTrue(result["private_environment_updated"])
        self.assertFalse(result["configuration_pending"])
        self.assertEqual(self.installer.installs, 1)
        self.assertEqual(self.installer.record_path.read_bytes(), before)
        self.assertEqual(self.installer.env["AGENT_BIOS_PYTHON_EXECUTABLE"], str(self.python))
        self.assertEqual(self.installer.env["AGENT_BIOS_PYTHON_DEPS"], self.binding()["dependencies_root"])
        for name in ("AGENT_BIOS_PYTHON_EXECUTABLE", "AGENT_BIOS_PYTHON_DEPS", "AGENT_BIOS_PYTHON_ENTRY"):
            self.assertEqual(os.environ.get(name), previous.get(name))

    def test_downgrade_refused_before_native_update_or_binding_switch(self):
        self.install()
        self.configured()
        before = (self.root / "deployment.json").read_bytes()
        self.bundle("0.19.2")
        with self.assertRaisesRegex(deploy.DeploymentError, "downgrade refused"):
            self.install()
        self.assertEqual((self.root / "deployment.json").read_bytes(), before)
        self.assertEqual(self.installer.installs, 0)

    def test_prerelease_ordering_does_not_use_lexical_numeric_identifiers(self):
        self.assertLess(deploy._version("1.2.3-rc.2"), deploy._version("1.2.3-rc.10"))
        self.assertLess(deploy._version("1.2.3-rc.10"), deploy._version("1.2.3"))

    def test_unowned_nonempty_root_is_unchanged(self):
        self.root.mkdir(parents=True)
        foreign = self.root / "unrelated.txt"
        foreign.write_text("mine")
        with self.assertRaisesRegex(deploy.DeploymentError, "unowned nonempty"):
            self.install()
        self.assertEqual(list(self.root.iterdir()), [foreign])

    def test_inno_root_is_named_refusal(self):
        self.root.mkdir(parents=True)
        (self.root / "unins000.exe").write_bytes(b"inno")
        with self.assertRaisesRegex(deploy.DeploymentError, "Inno-managed"):
            self.install()
        self.assertFalse((self.root / "owner.json").exists())

    def test_redirected_destination_is_rejected(self):
        target = self.base / "foreign"
        target.mkdir()
        self.root.parent.mkdir()
        try:
            self.root.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink privilege unavailable: {exc}")
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.install()
        self.assertEqual(list(target.iterdir()), [])

    def test_redirected_bundle_entry_is_rejected_before_claiming_root(self):
        try:
            (self.source / "package/foreign").symlink_to(self.python)
        except OSError as exc:
            self.skipTest(f"symlink privilege unavailable: {exc}")
        with self.assertRaisesRegex(deploy.DeploymentError, "redirected bundle"):
            self.install()
        self.assertFalse(self.root.exists())

    def test_missing_wrapper_does_not_create_installation(self):
        (self.source / "commands/agent-launch.ps1").unlink()
        with self.assertRaisesRegex(deploy.DeploymentError, "incomplete application bundle"):
            self.install()
        self.assertFalse(self.root.exists())

    def test_same_version_repairs_missing_owned_release_file(self):
        self.install()
        binding = self.binding()
        missing = Path(binding["application_root"]) / "compose/native_cli.py"
        missing.unlink()
        self.install()
        self.assertTrue(missing.is_file())
        self.assertEqual(self.binding()["release_root"], binding["release_root"])

    def test_same_version_does_not_delete_unknown_release_file(self):
        self.install()
        unknown = Path(self.binding()["release_root"]) / "user-file.txt"
        unknown.write_text("keep")
        with self.assertRaisesRegex(deploy.DeploymentError, "unexpected files"):
            self.install()
        self.assertEqual(unknown.read_text(), "keep")

    def test_modified_stable_command_refused_before_private_update(self):
        self.install()
        self.configured()
        command = self.root / "bin/agent-bios.ps1"
        command.write_text("user's script")
        self.bundle("0.19.4")
        with self.assertRaisesRegex(deploy.DeploymentError, "modified or unowned command"):
            self.install()
        self.assertEqual(command.read_text(), "user's script")
        self.assertEqual(self.installer.installs, 0)

    def test_bad_probe_does_not_publish_binding_or_update_private_state(self):
        self.install()
        self.configured()
        before = (self.root / "deployment.json").read_bytes()
        def fail(binding):
            raise deploy.DeploymentError("probe failed")
        self.subject = self.deployment(probe=fail)
        with self.assertRaisesRegex(deploy.DeploymentError, "probe failed"):
            self.install()
        self.assertEqual((self.root / "deployment.json").read_bytes(), before)
        self.assertEqual(self.installer.installs, 0)

    def test_fresh_script_root_cannot_adopt_preexisting_private_installation(self):
        self.configured()
        before = self.installer.record_path.read_bytes()
        with self.assertRaisesRegex(deploy.DeploymentError, "explicit deployment handoff"):
            self.install()
        self.assertFalse(self.root.exists())
        self.assertFalse((self.state / ".corpus-store.lock").exists())
        self.assertEqual(self.installer.record_path.read_bytes(), before)
        self.assertEqual(self.installer.installs, 0)
        self.assertEqual(self.integration.applied, [])

    def test_personal_source_only_state_does_not_block_new_script_installation(self):
        self.state.mkdir()
        personal = self.state / "personal.md"
        personal.write_text("personal source without installed runtime")
        self.assertTrue(self.install()["configuration_pending"])
        self.assertEqual(personal.read_text(), "personal source without installed runtime")

    def test_detached_root_reinstall_retains_custom_private_roots_without_reactivating_instructions(self):
        custom = self.base / "custom private authoring"
        self.env["AGENT_BIOS_INSTRUCTIONS_DIR"] = str(custom)
        self.subject = self.deployment()
        self.install()
        expected = self.binding()["private_environment"]
        self.configured()
        self.subject.uninstall()
        self.assertFalse(self.installer.record_path.exists())
        self.env.pop("AGENT_BIOS_INSTRUCTIONS_DIR")
        self.subject = self.deployment()
        result = self.install()
        self.assertTrue(result["configuration_pending"])
        self.assertEqual(self.binding()["private_environment"], expected)
        self.assertEqual(self.installer.installs, 0)

    def test_detached_root_cannot_adopt_private_state_installed_elsewhere(self):
        self.install()
        self.subject.uninstall()
        self.configured()  # Another deployment has since installed this shared state.
        before = (self.root / "owner.json").read_bytes()
        self.subject = self.deployment()
        with self.assertRaisesRegex(deploy.DeploymentError, "explicit deployment handoff"):
            self.install()
        self.assertEqual((self.root / "owner.json").read_bytes(), before)
        self.assertFalse((self.root / "deployment.json").exists())
        self.assertFalse((self.root / "bin/agent-bios.ps1").exists())
        self.assertEqual(self.installer.installs, 0)

    def test_detached_root_keeps_version_floor(self):
        self.install()
        self.subject.uninstall()
        self.bundle("0.19.2")
        self.subject = self.deployment()
        with self.assertRaisesRegex(deploy.DeploymentError, "downgrade refused"):
            self.install()
        self.assertFalse((self.root / "deployment.json").exists())

    def test_detached_root_rejects_explicit_authoring_relocation(self):
        self.install()
        self.subject.uninstall()
        self.env["AGENT_BIOS_INSTRUCTIONS_DIR"] = str(self.base / "different authoring root")
        with self.assertRaisesRegex(deploy.DeploymentError, "AGENT_BIOS_INSTRUCTIONS_DIR differs"):
            self.deployment()

    def test_private_update_failure_keeps_old_binding_and_pending_receipt(self):
        self.install()
        self.configured()
        before = (self.root / "deployment.json").read_bytes()
        self.bundle("0.19.4")
        self.installer.fail = True
        with self.assertRaisesRegex(deploy.DeploymentError, "native recovery is required"):
            self.install()
        self.assertEqual((self.root / "deployment.json").read_bytes(), before)
        self.assertEqual(deploy._json(self.root / "operation.json")["phase"], "private_update_needs_recovery")
        with self.assertRaisesRegex(deploy.DeploymentError, "operation is incomplete"):
            self.subject.verify()

    def test_platform_failure_keeps_native_updates_and_reports_pending_then_retry_recovers(self):
        self.install()
        self.configured()
        before = self.binding()
        self.bundle("0.19.4")
        self.integration.fail = True
        with self.assertRaisesRegex(OSError, "platform failure"):
            self.install()
        self.assertEqual(self.installer.installs, 1)
        self.assertEqual(self.binding(), before)
        self.assertEqual(deploy._json(self.root / "operation.json")["phase"], "private_environment_updated")
        self.integration.fail = False
        self.assertEqual(self.install()["version"], "0.19.4")

    def test_managed_runtime_is_copied_and_staging_may_be_removed(self):
        managed = self.python.parent
        result = self.install(managed)
        bound = Path(self.binding()["python"]["path"])
        self.assertNotEqual(bound, self.python)
        self.assertTrue(str(bound).startswith(str(self.root / "runtimes")))
        self.python.unlink()
        self.assertTrue(bound.is_file())
        self.assertTrue(self.subject.verify()["application_deployed"])

    def test_uninstall_detaches_owned_commands_but_preserves_personal_data_and_historical_code(self):
        self.install(self.python.parent)
        self.configured()
        personal = self.state / "personal.md"
        personal.write_text("personal instructions")
        command = self.root / "bin/agent-launch.ps1"
        command.write_text("user customized")
        binding = self.binding()
        result = self.subject.uninstall()
        self.assertEqual(self.installer.uninstalls, 1)
        self.assertEqual(personal.read_text(), "personal instructions")
        self.assertEqual(command.read_text(), "user customized")
        self.assertEqual(result["retained_release_paths"], [binding["release_root"]])
        self.assertEqual(result["retained_runtime_paths"], [binding["python"]["managed_root"]])
        self.assertFalse((self.root / "deployment.json").exists())
        self.assertFalse((self.root / "bin/agent-bios.ps1").exists())
        self.assertTrue(Path(binding["python"]["path"]).exists())

    def test_external_python_survives_uninstall(self):
        self.install()
        result = self.subject.uninstall()
        self.assertTrue(result["external_python_preserved"])
        self.assertTrue(self.python.exists())
        self.assertEqual(result["retained_runtime_paths"], [])

    def test_active_activation_refuses_removal_before_any_detach(self):
        self.install()
        self.installer.active = True
        with self.assertRaisesRegex(deploy.DeploymentError, "active instructions activation"):
            self.subject.uninstall()
        self.assertEqual(self.installer.uninstalls, 0)
        self.assertEqual(self.integration.removed, [])
        self.assertTrue((self.root / "bin/agent-bios.ps1").exists())

    def test_forged_tree_ownership_is_rejected_before_private_removal(self):
        self.install()
        owner = deploy._json(self.root / "owner.json")
        owner["trees"]["../../external python"] = {"python.exe": deploy._hash(self.python)}
        (self.root / "owner.json").write_bytes(deploy._canonical(owner))
        with self.assertRaisesRegex(deploy.DeploymentError, "invalid owned tree claim"):
            self.subject.uninstall()
        self.assertEqual(self.installer.uninstalls, 0)
        self.assertTrue(self.python.exists())

    def test_changed_private_state_root_is_refused(self):
        self.install()
        self.env["AGENT_BIOS_STATE_DIR"] = str(self.base / "different state")
        with self.assertRaisesRegex(deploy.DeploymentError, "differs from the saved"):
            self.deployment()

    def test_saved_custom_authoring_root_survives_absent_later_environment(self):
        custom = self.base / "custom personal instructions"
        self.env["AGENT_BIOS_INSTRUCTIONS_DIR"] = str(custom)
        self.subject = self.deployment()
        self.install()
        self.configured()
        self.env.pop("AGENT_BIOS_INSTRUCTIONS_DIR")
        self.subject = self.deployment()
        self.bundle("0.19.4")
        self.install()
        self.assertEqual(self.installer.env["AGENT_BIOS_INSTRUCTIONS_DIR"], str(custom))
        self.assertEqual(self.binding()["private_environment"]["AGENT_BIOS_INSTRUCTIONS_DIR"], str(custom))

    def test_explicit_authoring_root_relocation_is_rejected(self):
        self.install()
        self.env["AGENT_BIOS_INSTRUCTIONS_DIR"] = str(self.base / "new personal root")
        with self.assertRaisesRegex(deploy.DeploymentError, "AGENT_BIOS_INSTRUCTIONS_DIR differs"):
            self.deployment()

    def test_legacy_authoring_alias_is_saved_as_canonical_environment(self):
        self.env["AGENT_BIOS_CORPUS_DIR"] = str(self.base / "legacy root")
        self.subject = self.deployment()
        self.install()
        self.assertEqual(self.binding()["private_environment"]["AGENT_BIOS_INSTRUCTIONS_DIR"], str(self.base / "legacy root"))
        self.assertNotIn("AGENT_BIOS_CORPUS_DIR", self.binding()["private_environment"])

    def test_overlapping_source_and_deployment_root_is_rejected(self):
        self.root = self.source / "nested install"
        self.subject = self.deployment()
        with self.assertRaisesRegex(deploy.DeploymentError, "source bundle and deployment root must be separate"):
            self.install()
        self.assertFalse(self.root.exists())

    def test_overlapping_private_state_and_program_root_is_refused(self):
        self.env["AGENT_BIOS_STATE_DIR"] = str(self.root / "personal")
        with self.assertRaisesRegex(deploy.DeploymentError, "must be separate"):
            self.deployment()

    def test_persistent_path_preserves_preexisting_entry_and_registry_type(self):
        self.root.mkdir(parents=True)
        self.integration = MemoryWindowsIntegration("first;" + str(self.root / "bin") + ";last")
        self.integration.kind = 1
        with patch.dict(os.environ, {"APPDATA": str(self.base / "roaming")}):
            receipt = self.integration.apply(self.root, {})
            self.assertIsNone(receipt["path_entry"])
            original = self.integration.value
            self.integration.remove(self.root, receipt)
        self.assertEqual(self.integration.value, original)
        self.assertEqual(self.integration.kind, 1)

    def test_persistent_path_add_and_remove_preserve_empty_and_unrelated_entries(self):
        self.root.mkdir(parents=True)
        self.integration = MemoryWindowsIntegration("first;;last;")
        with patch.dict(os.environ, {"APPDATA": str(self.base / "roaming")}):
            receipt = self.integration.apply(self.root, {})
            self.assertEqual(self.integration.value, "first;;last;" + str(self.root / "bin"))
            self.integration.value += ";later"
            self.integration.remove(self.root, receipt)
        self.assertEqual(self.integration.value, "first;;last;later")

    def test_preexisting_foreign_start_menu_group_fails_before_path_mutation(self):
        self.root.mkdir(parents=True)
        self.integration = MemoryWindowsIntegration()
        with patch.dict(os.environ, {"APPDATA": str(self.base / "roaming")}):
            group = self.integration._group(self.root)
            group.mkdir(parents=True)
            (group / "foreign.txt").write_text("foreign")
            with self.assertRaisesRegex(deploy.DeploymentError, "unowned Start menu"):
                self.integration.apply(self.root, {})
        self.assertEqual(self.integration.writes, [])

    def test_modified_start_menu_shortcut_is_preserved(self):
        self.root.mkdir(parents=True)
        self.integration = MemoryWindowsIntegration()
        with patch.dict(os.environ, {"APPDATA": str(self.base / "roaming")}):
            receipt = self.integration.apply(self.root, {})
            shortcut = self.integration._group(self.root) / "agent-bios.lnk"
            shortcut.write_text("user changed target")
            retained = self.integration.remove(self.root, receipt)
        self.assertEqual(retained, [str(shortcut)])
        self.assertEqual(shortcut.read_text(), "user changed target")

    def test_start_menu_replace_failure_is_recoverable_from_pending_ownership(self):
        self.root.mkdir(parents=True)
        self.integration = MemoryWindowsIntegration()
        with patch.dict(os.environ, {"APPDATA": str(self.base / "roaming")}):
            prior = self.integration.apply(self.root, {})
            real_replace = os.replace
            def fail_link(source, destination):
                if str(destination).endswith("agent-bios.lnk"):
                    raise OSError("interrupted shortcut publication")
                return real_replace(source, destination)
            with patch.object(deploy.os, "replace", side_effect=fail_link):
                with self.assertRaisesRegex(OSError, "interrupted shortcut"):
                    self.integration.apply(self.root, prior)
            pending = deploy._json(self.root / "platform.json")
            self.assertTrue(pending["pending_shortcuts"])
            complete = self.integration.apply(self.root, pending)
        self.assertEqual(complete["pending_shortcuts"], {})
        self.assertEqual(len(complete["shortcuts"]), 2)

    def test_invalid_shortcut_receipt_cannot_remove_outside_owned_group(self):
        self.root.mkdir(parents=True)
        self.integration = MemoryWindowsIntegration()
        with patch.dict(os.environ, {"APPDATA": str(self.base / "roaming")}):
            receipt = self.integration.apply(self.root, {})
            original_path = self.integration.value
            receipt["shortcuts"][str(self.python)] = deploy._hash(self.python)
            with self.assertRaisesRegex(deploy.DeploymentError, "invalid Start menu ownership"):
                self.integration.remove(self.root, receipt)
        self.assertEqual(self.integration.value, original_path)
        self.assertTrue(self.python.is_file())


if __name__ == "__main__":
    unittest.main()
