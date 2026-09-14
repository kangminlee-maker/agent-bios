"""OS-independent entrypoint contract and real local lock checks."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import host_platform
from instructions_transaction import transaction_lock, try_transaction_lock

ROOT=Path(__file__).resolve().parents[1]
class HostPlatformTests(unittest.TestCase):
    def test_windows_entrypoint_is_an_argv_not_shell_text(self):
        with patch.object(host_platform,'WINDOWS',True):
            argv=host_platform.cli_argv(Path('folder with spaces'),'instructions','show','한글 & value')
        self.assertEqual(argv,[sys.executable,str(Path('folder with spaces/compose/native_cli.py')),'instructions','show','한글 & value'])
    def test_existing_lock_is_reentrant_without_creating_readonly_state(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'state'
            with try_transaction_lock(root) as held:self.assertFalse(held)
            self.assertFalse(root.exists())
            with transaction_lock(root):
                with try_transaction_lock(root) as held:self.assertTrue(held)
    def test_native_version_does_not_install_or_require_bash(self):
        p=subprocess.run([sys.executable,str(ROOT/'compose/native_cli.py'),'--version'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertRegex(p.stdout.strip(),r'^\d+\.\d+\.\d+$')

    def test_package_import_does_not_need_compose_on_pythonpath(self):
        p=subprocess.run([sys.executable, '-c', 'import compose.instructions_transaction; import compose.instructions_store'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
