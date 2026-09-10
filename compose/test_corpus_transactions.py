"""Fault boundaries discovered from real installer journal writes, then replayed."""
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import corpus_install
from corpus_transaction import guard_pending, TransactionPendingError
import test_corpus_install as fixtures


class TransactionBoundaryTests(unittest.TestCase):
    setUp = fixtures.CorpusInstallTests.setUp
    tearDown = fixtures.CorpusInstallTests.tearDown

    def _instance(self, name):
        root = Path(self.tmp.name) / name
        env = dict(self.env, HOME=str(root / "home"), AGENT_BIOS_STATE_DIR=str(root / "state"),
                   AGENT_BIOS_CORPUS_DIR=str(root / "user"))
        return corpus_install.CorpusInstaller(self.repo, env)

    def _journals(self, instance, kind):
        folder = "resets" if kind == "reset" else "installer-transactions"
        return list((instance.runtime / folder).glob("*/journal.json"))

    def test_every_observed_reset_phase_can_be_replayed_without_new_reset(self):
        phases = []
        original = corpus_install._atomic_json
        control = self._instance("reset-control")
        control.install("none")

        def observe(path, value):
            if "resets" in path.parts and value.get("phase") not in phases:
                phases.append(value["phase"])
            return original(path, value)

        with mock.patch.object(corpus_install, "_atomic_json", side_effect=observe):
            preview = control.reset()
            control.reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        self.assertGreaterEqual(len(phases), 4)
        for phase in phases:
            with self.subTest(phase=phase):
                instance = self._instance("reset-" + phase)
                instance.install("none")
                token = instance.launch_root.parent / "agent-bios/token"
                token.parent.mkdir(parents=True, exist_ok=True)
                token.write_text("boundary-test-token")
                (instance.launch_root / "presets.local.toml").write_text("# personal")
                preview = instance.reset()
                tripped = False

                def stop(path, value):
                    nonlocal tripped
                    result = original(path, value)
                    if "resets" in path.parts and value.get("phase") == phase and not tripped:
                        tripped = True
                        raise OSError("injected reset boundary")
                    return result

                with mock.patch.object(corpus_install, "_atomic_json", side_effect=stop):
                    with self.assertRaises(OSError):
                        instance.reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
                self.assertTrue(tripped)
                self.assertEqual(1, len(self._journals(instance, "reset")))
                instance.reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
                self.assertEqual(1, len(self._journals(instance, "reset")))
                self.assertFalse(token.exists())
                self.assertTrue(instance.verify()["stored"])
                guard_pending(instance.state_root)

    def test_every_observed_install_phase_guards_readers_and_recovers(self):
        phases = []
        original = corpus_install._atomic_json
        control = self._instance("install-control")

        def observe(path, value):
            if "installer-transactions" in path.parts and value.get("phase") not in phases:
                phases.append(value["phase"])
            return original(path, value)

        with mock.patch.object(corpus_install, "_atomic_json", side_effect=observe):
            control.install("none")
        self.assertGreaterEqual(len(phases), 4)
        for phase in phases:
            with self.subTest(phase=phase):
                instance = self._instance("install-" + phase)
                tripped = False

                def stop(path, value):
                    nonlocal tripped
                    result = original(path, value)
                    if "installer-transactions" in path.parts and value.get("phase") == phase and not tripped:
                        tripped = True
                        raise OSError("injected install boundary")
                    return result

                with mock.patch.object(corpus_install, "_atomic_json", side_effect=stop):
                    with self.assertRaises(OSError):
                        instance.install("none")
                self.assertTrue(tripped)
                with self.assertRaises(TransactionPendingError):
                    guard_pending(instance.state_root)
                instance.install("none")
                self.assertTrue(instance.verify()["stored"])
                guard_pending(instance.state_root)

    def test_reset_recovers_a_split_store_publication(self):
        instance = self._instance("source-split")
        installed = instance.install("none")
        store = instance._store(Path(installed["record"]["package_root"]))
        created = store.plan({"operation": "create", "item": {"title": "Keep in history", "body": "Body"}})
        store.apply(created["plan_id"])
        preview = instance.reset()
        module = sys.modules[store.__class__.__module__]
        original = module._atomic_write
        tripped = False

        def stop(path, value):
            nonlocal tripped
            if path == store._runtime_state_path and not tripped:
                tripped = True
                raise OSError("split source write")
            return original(path, value)

        with mock.patch.object(instance, "_store", return_value=store):
            with mock.patch.object(module, "_atomic_write", side_effect=stop):
                with self.assertRaises(OSError):
                    instance.reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
            self.assertTrue(tripped)
            instance.reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        self.assertEqual(0, store.status()["personal_items"])
        self.assertEqual(1, len(self._journals(instance, "reset")))
        self.assertTrue(instance.verify()["stored"])


if __name__ == "__main__":
    unittest.main()
