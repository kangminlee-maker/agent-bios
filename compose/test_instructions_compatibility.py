"""Compatibility contracts independent of the canonical instruction compiler."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from instructions_install import InstructionsInstaller
from instructions_store import InstructionsStore, ValidationError, verify_snapshot
from instructions_transaction import TransactionError, environment_value, transaction_lock, try_transaction_lock


ROOT = Path(__file__).resolve().parents[1]


class InstructionsCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="instructions-compatibility-")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_old_module_import_is_the_same_writer_and_exception_identity(self):
        old = importlib.import_module("corpus_store")
        new = importlib.import_module("instructions_store")
        self.assertIs(old, new)
        self.assertIs(old.CorpusStore, InstructionsStore)
        self.assertIs(old.CorpusStoreError, new.InstructionsStoreError)

    def test_package_and_legacy_transaction_imports_share_reentrant_scope(self):
        names = ("instructions_transaction", "corpus_transaction",
                 "compose.instructions_transaction", "compose.corpus_transaction")
        modules = [importlib.import_module(name) for name in names]
        self.assertTrue(all(module is modules[0] for module in modules))
        old = self.root / "old-release/compose"
        old.mkdir(parents=True)
        (old / "corpus_store.py").write_text("from corpus_transaction import try_transaction_lock\n")
        installer = InstructionsInstaller(ROOT, {"HOME": str(self.root)})
        loaded = installer._private_module(old.parent, "instructions_store")
        with transaction_lock(self.root):
            with loaded.try_transaction_lock(self.root) as acquired:
                self.assertTrue(acquired, "historical store loaded an independent process-local lock")

    def test_original_launcher_ownership_is_verified_with_its_release_vocabulary(self):
        installer = InstructionsInstaller(ROOT, {"HOME": str(self.root)})
        old = self.root / "old-release"
        (old / "launch").mkdir(parents=True)
        (old / "launch/agent-launch.toml").write_text("# old release\n")
        legacy = ("#!/bin/sh\nexport AGENT_BIOS_PRIVATE_CORPUS=1\n"
                  f"export AGENT_BIOS_PACKAGE_ROOT={old}\n"
                  "exec python3 \"$AGENT_BIOS_PACKAGE_ROOT/launch/agent-launch.py\" \"$@\"\n").encode()
        record = {"launcher": {"path": str(installer.bin_root / "agent-launch"),
                                "sha256": hashlib.sha256(legacy).hexdigest()}}
        installer._validate_owned_record(record, old)
        record["launcher"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "ownership claim"):
            installer._validate_owned_record(record, old)

    def test_environment_alias_fallback_and_conflict_are_explicit(self):
        for canonical, legacy in (
            ("AGENT_BIOS_INSTRUCTIONS_DIR", "AGENT_BIOS_CORPUS_DIR"),
            ("AGENT_BIOS_INSTRUCTIONS_STATUS", "AGENT_BIOS_CORPUS_STATUS"),
            ("AGENT_BIOS_PRIVATE_INSTRUCTIONS", "AGENT_BIOS_PRIVATE_CORPUS"),
        ):
            with self.subTest(canonical=canonical):
                self.assertEqual("default", environment_value({}, canonical, legacy, "default"))
                self.assertEqual("same", environment_value({legacy: "same"}, canonical, legacy))
                self.assertEqual("same", environment_value({canonical: "same", legacy: "same"}, canonical, legacy))
                with self.assertRaisesRegex(TransactionError, canonical + ".*" + legacy):
                    environment_value({canonical: "a", legacy: "b"}, canonical, legacy)

    def test_legacy_root_override_selects_the_same_store_without_relocation(self):
        env = {"HOME": str(self.root), "AGENT_BIOS_CORPUS_DIR": str(self.root / "existing")}
        with mock.patch.dict(os.environ, env, clear=True):
            store = InstructionsStore(ROOT)
            installer = InstructionsInstaller(ROOT)
        self.assertEqual(store.user_root, installer.user_root)
        self.assertEqual(self.root / "existing", store.user_root)
        self.assertFalse((self.root / "existing").exists())

    def test_conflicting_root_overrides_fail_before_any_store_write(self):
        env = {"HOME": str(self.root), "AGENT_BIOS_CORPUS_DIR": str(self.root / "old"),
               "AGENT_BIOS_INSTRUCTIONS_DIR": str(self.root / "new")}
        with mock.patch.dict(os.environ, env, clear=True):
            for build in (lambda: InstructionsStore(ROOT), lambda: InstructionsInstaller(ROOT)):
                with self.assertRaisesRegex(TransactionError, "conflicting"):
                    build()
        self.assertEqual([], list(self.root.iterdir()))

    def test_default_physical_store_is_preserved(self):
        installer = InstructionsInstaller(ROOT, {"HOME": str(self.root)})
        self.assertEqual(self.root / ".config/agent-bios/corpus", installer.user_root)
        self.assertFalse((self.root / ".config/agent-bios/instructions").exists())

    def test_old_and_new_public_commands_observe_identical_state(self):
        env = dict(os.environ, AGENT_BIOS_STATE_DIR=str(self.root / "state"),
                   AGENT_BIOS_INSTRUCTIONS_DIR=str(self.root / "user"))
        env.pop("AGENT_BIOS_CORPUS_DIR", None)
        outputs = []
        for command in ("instructions", "corpus"):
            result = subprocess.run(["bash", str(ROOT / "install.sh"), command, "status", "--json"],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0], outputs[1])

    def test_old_script_entrypoint_uses_the_canonical_cli(self):
        result = subprocess.run([sys.executable, str(ROOT / "compose/corpus.py"), "--help"],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("agent-bios instructions", result.stdout)

    def test_new_writer_observes_a_legacy_process_lock(self):
        # The old published lock name is the interoperability contract, independent
        # of either Python module's current helper implementation.
        legacy = "import fcntl,pathlib,sys; p=pathlib.Path(sys.argv[1])/'.corpus-store.lock'; f=p.open('a'); fcntl.flock(f,fcntl.LOCK_EX); print('locked',flush=True); sys.stdin.read()"
        process = subprocess.Popen([sys.executable, "-c", legacy, str(self.root)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual("locked", process.stdout.readline().strip())
            with try_transaction_lock(self.root) as acquired:
                self.assertFalse(acquired)
            self.assertFalse((self.root / ".instructions-store.lock").exists())
        finally:
            process.communicate(input="", timeout=10)

    def _legacy_snapshot(self):
        # Independent schema-v1 fixture: legacy words are original evidence bytes,
        # not a request to update the archived instruction text during verification.
        inputs = {"schema_version": 1, "host": "codex", "compiler_digest": "old-corpus-compiler"}
        canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
        reference = hashlib.sha256(canonical).hexdigest()
        path = self.root / reference
        path.mkdir()
        body = b"Run agent-bios corpus list.\n"
        output = json.dumps({"files": ["bundle.md"], "instruction_text": body.decode()}).encode()
        (path / "bundle.md").write_bytes(body)
        (path / "output.json").write_bytes(output)
        inventory = {"inputs": inputs, "items": [{"ref": "@local/personal:legacy-item"}],
                     "file_digests": {"bundle.md": hashlib.sha256(body).hexdigest(),
                                      "output.json": hashlib.sha256(output).hexdigest()}}
        (path / "inventory.json").write_text(json.dumps(inventory))
        return path, reference

    def test_old_snapshot_identity_and_original_command_bytes_remain_exact(self):
        path, reference = self._legacy_snapshot()
        before = {p.name: p.read_bytes() for p in path.iterdir()}
        result = verify_snapshot(path, reference)
        self.assertEqual(reference, result["content_ref"])
        self.assertEqual("@local/personal:legacy-item", result["items"][0]["ref"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in path.iterdir()})

    def test_old_snapshot_corruption_does_not_resolve_to_current_content(self):
        path, reference = self._legacy_snapshot()
        (path / "bundle.md").write_text("Run agent-bios instructions list.\n")
        with self.assertRaisesRegex(ValidationError, "digest mismatch"):
            verify_snapshot(path, reference)


if __name__ == "__main__":
    unittest.main()
