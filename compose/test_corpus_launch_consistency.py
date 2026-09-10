"""Real launcher readers reject uncommitted and changing private generations."""
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

import test_corpus_install as fixtures
from corpus_transaction import TransactionPendingError

spec = importlib.util.spec_from_file_location("corpus_launch_consistency", fixtures.SOURCE / "launch/agent-launch.py")
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)


class LaunchConsistencyTests(unittest.TestCase):
    setUp = fixtures.CorpusInstallTests.setUp
    tearDown = fixtures.CorpusInstallTests.tearDown
    installer = fixtures.CorpusInstallTests.installer

    def test_config_change_between_setup_and_snapshot_is_rejected(self):
        installer = self.installer()
        installed = installer.install("none")
        release = Path(installed["record"]["package_root"])
        config = installer.launch_root / "profiles.toml"
        env = dict(self.env, AGENT_BIOS_PRIVATE_CORPUS="1", AGENT_BIOS_PACKAGE_ROOT=str(release))
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
        env = dict(self.env, AGENT_BIOS_PRIVATE_CORPUS="1", AGENT_BIOS_PACKAGE_ROOT=str(release))
        with mock.patch.dict(os.environ, env):
            with self.assertRaises(TransactionPendingError):
                launcher._load_private_config(config)
            parsed, _generation = launcher._load_private_config(config, replay_only=True)
            self.assertTrue(parsed["hosts"])


if __name__ == "__main__":
    unittest.main()
