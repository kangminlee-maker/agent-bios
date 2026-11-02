"""OS-independent entrypoint contract and real local lock checks."""
import contextlib
import errno
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import host_platform
from instructions_transaction import TransactionError, transaction_lock, try_transaction_lock

# A child that holds an exclusive flock on argv[1] until it is killed.
# a child holding a lock that lets go after 8 s: a wait without a bound returns late and fails, never hangs
HOLD = "import fcntl,sys,time; f=open(sys.argv[1],'a'); fcntl.flock(f,fcntl.LOCK_EX); print('held',flush=True); time.sleep(8)"

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
    def test_a_held_transaction_lock_is_refused_naming_its_setup_holder(self):
        # D-20261102-49b466: a writer waits at most the bound, says after the notice what it waits for,
        # and refuses naming the lock and the setup apply whose running receipt holds it. A receipt
        # whose recorded process identity no longer matches names nobody.
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'state'
            root.mkdir(mode=0o700)
            lock=root/'.corpus-store.lock'
            child=subprocess.Popen([sys.executable,'-c',HOLD,str(lock)],stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'held')
                receipts=root/'setup/receipts'
                receipts.mkdir(parents=True)
                owner={'pid':child.pid,'process_identity':host_platform.process_identity(child.pid)}
                (receipts/'gone.json').write_text(json.dumps({'state':'running','review_id':'review-gone','created_at':0,
                                                              'owner':{**owner,'process_identity':'another process'}}))
                (receipts/'live.json').write_text(json.dumps({'state':'running','review_id':'review-live','created_at':0,'owner':owner}))
                said=io.StringIO()
                with patch.object(host_platform,'LOCK_WAIT_S',.6),patch.object(host_platform,'LOCK_NOTICE_S',.2),\
                        contextlib.redirect_stderr(said),self.assertRaises(TransactionError) as refused:
                    with transaction_lock(root):
                        self.fail('took a lock another process holds')
                self.assertIn(f'the instructions transaction lock ({lock}) is still held after 0.6 s, held by setup apply '
                              f'review-live, pid {child.pid}, started ',str(refused.exception))
                self.assertNotIn('review-gone',str(refused.exception))
                self.assertIn(f'waiting for the instructions transaction lock ({lock}), held by setup apply review-live',
                              said.getvalue())
            finally:
                child.kill()
                child.wait()
                child.stdout.close()

    def test_the_windows_lock_emulation_waits_no_longer_than_the_bound(self):
        # The emulation retried a blocking request forever; driven here through a primitive that
        # always reports the byte held, it raises LockWaitExpired at the bound, and BlockingIOError
        # at once for LOCK_NB.
        calls=[0]
        def held(fd,mode,size):
            # a retry without a bound is stopped after 5 s of tries rather than spinning forever
            calls[0]+=1
            if calls[0]>100:
                raise AssertionError('the emulation kept retrying past the bound')
            raise OSError(errno.EACCES,'held')
        with tempfile.TemporaryFile() as f,patch.object(host_platform,'LOCK_WAIT_S',.3):
            with self.assertRaises(host_platform.LockWaitExpired):
                host_platform.emulated_flock(f.fileno(),2,held,0,1)
            with self.assertRaises(BlockingIOError):
                host_platform.emulated_flock(f.fileno(),2|4,held,0,1)
            host_platform.emulated_flock(f.fileno(),2,lambda fd,mode,size:None,0,1)

    def test_native_version_does_not_install_or_require_bash(self):
        p=subprocess.run([sys.executable,str(ROOT/'compose/native_cli.py'),'--version'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertRegex(p.stdout.strip(),r'^\d+\.\d+\.\d+$')

    def test_package_import_does_not_need_compose_on_pythonpath(self):
        p=subprocess.run([sys.executable, '-c', 'import compose.instructions_transaction; import compose.instructions_store'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
