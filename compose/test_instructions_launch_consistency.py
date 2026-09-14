"""Real launcher readers reject uncommitted and changing private generations."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import test_instructions_install as fixtures
from instructions_transaction import TransactionPendingError

spec = importlib.util.spec_from_file_location("instructions_launch_consistency", fixtures.SOURCE / "launch/agent-launch.py")
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)


class LauncherUiCapabilityTests(unittest.TestCase):
    def fixture_probe(self, *, missing_theme=False, unrelated_failure=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = {"rich/__init__.py": "", "rich/text.py": "Text = object\n",
                       "textual/__init__.py": "__version__ = '999.0'\nwork = object\n",
                       "textual/app.py": "App = object\n", "textual/binding.py": "Binding = object\n",
                       "textual/containers.py": "Horizontal = Vertical = VerticalScroll = object\n",
                       "textual/screen.py": "ModalScreen = object\n",
                       "textual/widgets/__init__.py": "Input = OptionList = Static = object\n",
                       "textual/widgets/option_list.py": "Option = object\n"}
            if not missing_theme:
                sources["textual/theme.py"] = "Theme = object\n"
            if unrelated_failure:
                sources["textual/theme.py"] = "import unrelated_ui_runtime\n"
            for relative, body in sources.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
            script = f"""import importlib.util, sys
sys.path.insert(0, {str(root)!r})
spec = importlib.util.spec_from_file_location('launcher_ui_probe', {str(fixtures.SOURCE / 'launch/agent-launch.py')!r})
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
print(module.textual_importable())
"""
            env = dict(os.environ, HOME=str(root))
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
            return subprocess.run([sys.executable, "-S", "-c", script], capture_output=True,
                                  text=True, env=env, timeout=15)

    def test_required_imports_define_compatibility_without_version_pin(self):
        result = self.fixture_probe()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("True", result.stdout.strip())

    def test_importable_textual_missing_theme_is_not_supported(self):
        result = self.fixture_probe(missing_theme=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("False", result.stdout.strip())

    def test_unrelated_import_errors_are_not_hidden_by_ui_probe(self):
        result = self.fixture_probe(unrelated_failure=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unrelated_ui_runtime", result.stderr)


class LaunchConsistencyTests(unittest.TestCase):
    setUp = fixtures.InstructionsInstallTests.setUp
    tearDown = fixtures.InstructionsInstallTests.tearDown
    installer = fixtures.InstructionsInstallTests.installer

    def test_config_change_between_setup_and_snapshot_is_rejected(self):
        installer = self.installer()
        installed = installer.install("none")
        release = Path(installed["record"]["package_root"])
        config = installer.launch_root / "profiles.toml"
        env = dict(self.env, AGENT_BIOS_PRIVATE_INSTRUCTIONS="1", AGENT_BIOS_PACKAGE_ROOT=str(release))
        with mock.patch.dict(os.environ, env):
            parsed, generation = launcher._load_private_config(config)
            self.assertTrue(parsed["presets"])
            config.write_text(config.read_text() + "\n# changed while setup open\n")
            with self.assertRaisesRegex(launcher.LaunchError, "changed during setup"):
                launcher._snapshot_from_config(installer._store(release), config, generation,
                                               "claude", None, dry_run=False, native=False)
            self.assertFalse((self.state / "sessions/snapshots").exists())

    def test_pending_update_blocks_configured_load_but_allows_prior_replay_config(self):
        installer = self.installer()
        installed = installer.install("none")
        release = Path(installed["record"]["package_root"])
        config = installer.launch_root / "profiles.toml"
        source = self.repo / "claude/guides/tooling-gotchas.md"
        source.write_text(source.read_text() + "\nCandidate update.\n")
        with mock.patch.object(installer, "_write_planned", side_effect=OSError("injected update interruption")):
            with self.assertRaises(OSError):
                installer.install("none")
        env = dict(self.env, AGENT_BIOS_PRIVATE_INSTRUCTIONS="1", AGENT_BIOS_PACKAGE_ROOT=str(release))
        with mock.patch.dict(os.environ, env):
            with self.assertRaises(TransactionPendingError):
                launcher._load_private_config(config)
            parsed, _generation = launcher._load_private_config(config, replay_only=True)
            self.assertTrue(parsed["hosts"])


class ReviewWrapperResolutionTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="private-review-adapters-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.package = self.root / "selected package"
        (self.package / "wrappers").mkdir(parents=True)
        self.native = {}
        self.wrappers = {}
        for host, name in (("codex", "codex-run"), ("codex", "codex-helm"),
                           ("claude", "claude-run")):
            source = fixtures.SOURCE / "wrappers" / f"{name}.sh"
            target = self.package / "wrappers" / source.name
            shutil.copy2(source, target)
            self.wrappers[name] = target
            decoy = self.root / host / "bin" / name
            decoy.parent.mkdir(parents=True, exist_ok=True)
            decoy.write_text("#!/bin/sh\nexit 99\n")
            decoy.chmod(0o755)
            self.native[name] = decoy
        self.env = {
            "HOME": str(self.root / "home"), "PATH": os.environ["PATH"],
            "CODEX_HOME": str(self.root / "codex"),
            "CLAUDE_CONFIG_DIR": str(self.root / "claude"),
            "AGENT_BIOS_PRIVATE_INSTRUCTIONS": "1",
            "AGENT_BIOS_PACKAGE_ROOT": str(self.package),
        }
        self.config = {"backends": {"claude": {"command": "/usr/bin/false"}}}

    def resolved(self):
        return {
            "codex-run": launcher.host_dispatch_command("codex", self.config),
            "claude-run": launcher.host_dispatch_command("claude", self.config),
            "cross-native": launcher.cross_native_command({"review_host": "codex"}),
            "codex-helm": launcher.cross_helm_command({"review_host": "codex"}),
        }

    def test_private_review_adapters_win_over_native_decoys(self):
        with mock.patch.dict(os.environ, self.env, clear=True):
            actual = self.resolved()
        expected = {name: str(path) for name, path in self.wrappers.items()}
        expected["cross-native"] = expected["codex-run"]
        self.assertEqual(expected, actual)
        for command in set(actual.values()):
            result = subprocess.run([command, "--help"], env=self.env, text=True,
                                    capture_output=True, timeout=10)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Usage:", result.stdout)

    def test_missing_private_adapters_do_not_borrow_native_copies(self):
        for path in self.wrappers.values():
            path.unlink()
        with mock.patch.dict(os.environ, self.env, clear=True):
            self.assertEqual({"codex-run": None, "cross-native": None,
                              "codex-helm": None, "claude-run": "/usr/bin/false"}, self.resolved())
            self.assertEqual("/usr/bin/false", launcher.cross_native_command(
                {"review_host": "claude", "review_backend": "/usr/bin/false"}))
            self.assertIsNone(launcher.cross_helm_command({"review_host": "claude"}))

    def test_nonexecutable_private_adapters_remain_unavailable(self):
        for path in self.wrappers.values():
            path.chmod(0o644)
        with mock.patch.dict(os.environ, self.env, clear=True):
            self.assertEqual({"codex-run": None, "cross-native": None,
                              "codex-helm": None, "claude-run": "/usr/bin/false"}, self.resolved())

    def test_nonprivate_installation_keeps_native_adapter_resolution(self):
        env = dict(self.env, AGENT_BIOS_PRIVATE_INSTRUCTIONS="0")
        with mock.patch.dict(os.environ, env, clear=True):
            actual = self.resolved()
        expected = {name: str(path) for name, path in self.native.items()}
        expected["cross-native"] = expected["codex-run"]
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
