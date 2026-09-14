"""Real clean-process terminal entrypoints use the shipped UI without a venv."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

from instructions_store import InstructionsStore
from instructions_install import InstructionsInstaller


ROOT = Path(__file__).resolve().parents[1]


class BundledUiEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="agent-bios-ui-entry-")
        self.root = Path(self.scratch.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.temporary = self.root / "temporary"
        self.temporary.mkdir()
        self.state, self.user = self.root / "state", self.root / "user"
        self.env = dict(os.environ, HOME=str(self.home), TMPDIR=str(self.temporary),
                        AGENT_BIOS_STATE_DIR=str(self.state), AGENT_BIOS_INSTRUCTIONS_DIR=str(self.user),
                        CODEX_HOME=str(self.home / ".codex"), CLAUDE_CONFIG_DIR=str(self.home / ".claude"),
                        AGENT_LAUNCH_VENV=str(self.root / "missing-venv"), AGENT_BIOS_LEGACY_INSTALL="0",
                        AGENT_BIOS_PRIVATE_INSTRUCTIONS="0", TERM="xterm-256color", PYTHONDONTWRITEBYTECODE="1")
        for name in ("PYTHONPATH", "PYTHONHOME", "AGENT_BIOS_PACKAGE_ROOT", "AGENT_BIOS_REPO", "AGENT_LAUNCH_TUI",
                     "AGENT_BIOS_INSTRUCTIONS_TUI_REEXEC", "AGENT_LAUNCH_REEXEC"):
            self.env.pop(name, None)
        self.config = self.root / "profiles.toml"
        config = (ROOT / "launch/agent-launch.toml").read_text(encoding="utf-8")
        config = config.replace('command = "codex"', 'command = "/usr/bin/true"').replace('command = "claude"', 'command = "/usr/bin/true"')
        self.config.write_text(config, encoding="utf-8")

    def tearDown(self):
        self.scratch.cleanup()

    def run_pty(self, script, args, *, ready=None, keys=b"\x1b", timeout=25):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 110, 0, 0))
        process = subprocess.Popen([sys.executable, "-S", str(script), *args], stdin=slave, stdout=slave,
                                   stderr=slave, env=self.env, cwd=self.root)
        os.close(slave)
        output = bytearray()
        sent = ready is None
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                readable, _, _ = select.select([master], [], [], 0.1)
                if readable:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        chunk = b""
                    output.extend(chunk)
                plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output.decode(errors="replace"))
                if not sent and ready in plain:
                    self.assertTrue(list(self.temporary.glob("agent-bios-ui-*")), "UI opened without the bundled runtime")
                    os.write(master, keys)
                    sent = True
                if process.poll() is not None:
                    self.assertTrue(sent, "UI did not reach its expected screen: " + plain)
                    return process.returncode, output.decode(errors="replace")
            self.fail("UI entrypoint timed out: " + output.decode(errors="replace"))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            os.close(master)

    def no_runtime_leak(self):
        self.assertEqual([], list(self.temporary.glob("agent-bios-ui-*")))
        self.assertFalse((self.root / "missing-venv").exists())

    def test_instructions_cli_without_site_packages_opens_real_textual_screen(self):
        InstructionsStore(ROOT, self.state, self.user).install([], selection_mode="none", replace_selection=True)
        code, output = self.run_pty(ROOT / "compose/instructions.py", ["--repo", str(ROOT)], ready="Instructions Studio")
        self.assertEqual(0, code, output)
        self.assertIn("\x1b[?1049h", output)
        self.assertNotIn("numbered fallback", output)
        self.no_runtime_leak()

    def test_checkout_launcher_without_site_packages_opens_real_textual_screen(self):
        code, output = self.run_pty(ROOT / "launch/agent-launch.py", ["--config", str(self.config), "claude"], ready="Esc cancel", keys=b"q")
        self.assertEqual(130, code, output)
        self.assertIn("\x1b[?1049h", output)
        self.assertNotIn("using numbered prompts", output)
        self.no_runtime_leak()

    def test_installed_private_launcher_uses_its_release_bundle(self):
        installer = InstructionsInstaller(ROOT, self.env)
        installed = installer.install(selection_mode="none", targets=[])
        release = Path(installed["record"]["package_root"])
        binaries = self.root / "host-stubs"
        binaries.mkdir()
        for name in ("claude", "codex"):
            (binaries / name).symlink_to("/usr/bin/true")
        self.env.update(AGENT_BIOS_PRIVATE_INSTRUCTIONS="1", AGENT_BIOS_PACKAGE_ROOT=str(release),
                        PATH=str(binaries) + os.pathsep + self.env["PATH"])
        code, output = self.run_pty(release / "launch/agent-launch.py",
                                    ["--config", str(installer.launch_root / "profiles.toml"), "claude"],
                                    ready="Esc cancel", keys=b"q")
        self.assertEqual(130, code, output)
        self.assertIn("\x1b[?1049h", output)
        self.assertNotIn("using numbered prompts", output)
        self.no_runtime_leak()

    def package_copy(self, name):
        package = self.root / name
        (package / "compose").mkdir(parents=True)
        (package / "launch").mkdir()
        for filename in ("instructions.py", "instructions_store.py", "instructions_transaction.py", "instructions_catalog.py",
                         "instructions_ui_runtime.py", "instructions_ui.py", "assemble.py", "pkgid.py", "host_platform.py"):
            shutil.copy2(ROOT / "compose" / filename, package / "compose" / filename)
        shutil.copy2(ROOT / "launch/agent-launch.py", package / "launch/agent-launch.py")
        shutil.copytree(ROOT / "compose/ui_runtime", package / "compose/ui_runtime")
        return package

    def test_corrupt_instructions_bundle_is_actionable_and_does_not_fall_back(self):
        package = self.package_copy("bad-instructions")
        wheel = next((package / "compose/ui_runtime").glob("*.whl"))
        data = bytearray(wheel.read_bytes()); data[len(data) // 2] ^= 1; wheel.write_bytes(data)
        code, output = self.run_pty(package / "compose/instructions.py", ["--repo", str(ROOT)])
        self.assertEqual(2, code, output)
        self.assertIn("SHA256 mismatch", output)
        self.assertNotIn("numbered fallback", output)
        self.no_runtime_leak()

    def test_corrupt_launcher_bundle_is_actionable_and_does_not_fall_back(self):
        package = self.package_copy("bad-launcher")
        next((package / "compose/ui_runtime").glob("*.whl")).unlink()
        code, output = self.run_pty(package / "launch/agent-launch.py", ["--config", str(self.config), "claude"])
        self.assertEqual(2, code, output)
        self.assertIn("bundled UI wheel missing", output)
        self.assertNotIn("using numbered prompts", output)
        self.no_runtime_leak()

    def test_backend_exec_releases_owned_ui_runtime(self):
        code = f"""import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('entry_launcher', {str(ROOT / 'launch/agent-launch.py')!r})
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert module._activate_cli_ui_runtime()
import textual
path = Path(textual.__file__).parents[1]
assert module.textual_importable()
assert module._build_app_class().__name__ == 'PreflightApp'
module.exec_backend(sys.executable, ['-S', '-c', 'from pathlib import Path; import sys; assert not Path(sys.argv[1]).exists(); print("backend received clean handoff")', str(path)])
"""
        result = subprocess.run([sys.executable, "-S", "-c", code], env=self.env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("backend received clean handoff", result.stdout)
        self.no_runtime_leak()

    def test_standalone_legacy_launcher_has_no_bundle_requirement(self):
        legacy = self.root / "legacy/launch"
        legacy.mkdir(parents=True)
        script = legacy / "agent-launch.py"
        shutil.copy2(ROOT / "launch/agent-launch.py", script)
        code = f"""import importlib.util, sys
spec=importlib.util.spec_from_file_location('legacy_launcher', {str(script)!r})
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
assert module._activate_cli_ui_runtime() is False
assert module._UI_RUNTIME_RELEASE is None
print('legacy compatibility retained')
"""
        result = subprocess.run([sys.executable, "-S", "-c", code], env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.no_runtime_leak()

    def test_standalone_launcher_uses_explicit_private_package_bundle(self):
        legacy = self.root / "standalone/launch"
        legacy.mkdir(parents=True)
        script = legacy / "agent-launch.py"
        shutil.copy2(ROOT / "launch/agent-launch.py", script)
        env = dict(self.env, AGENT_BIOS_PACKAGE_ROOT=str(ROOT), AGENT_BIOS_PRIVATE_INSTRUCTIONS="1")
        code = f"""import importlib.util, sys
spec=importlib.util.spec_from_file_location('private_launcher', {str(script)!r})
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
assert module._activate_cli_ui_runtime() is True
assert module.textual_importable()
assert module._UI_RUNTIME_RELEASE is not None
print('private package bundle selected')
"""
        result = subprocess.run([sys.executable, "-S", "-c", code], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("private package bundle selected", result.stdout)
        self.no_runtime_leak()


if __name__ == "__main__":
    unittest.main()
