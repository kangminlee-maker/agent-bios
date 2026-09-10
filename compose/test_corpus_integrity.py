"""Integrity scenarios through the real catalog, store and snapshot compiler."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

import compose.corpus_store as store_module

from compose.corpus_store import CorpusStore, CorpusStoreError, ValidationError


class CorpusIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = Path(__file__).resolve().parents[1]
        self.store = CorpusStore(self.repo, self.root / "state", self.root / "user")
        self.store.install(["all"])

    def tearDown(self):
        self.temp.cleanup()

    def apply(self, payload):
        plan = self.store.plan(payload)
        return self.store.apply(plan["plan_id"])

    def create(self, title="Repeated title", body="Original\nOLD_BODY"):
        return self.apply({"operation": "create", "item": {"title": title, "body": body}})["details"]["ref"]

    def test_reset_and_history_rollback_never_reissue_personal_id(self):
        first = self.create()
        snapshot = self.store.snapshot("claude")
        reset = self.apply({"operation": "reset"})
        second = self.create()
        self.assertNotEqual(first, second)
        self.apply({"operation": "rollback", "history_id": reset["history_id"]})
        third = self.create()
        self.assertNotIn(third, {first, second})
        self.assertTrue(Path(snapshot["path"]).is_dir())

    def test_creation_id_is_frozen_in_plan_and_retry_is_idempotent(self):
        plan = self.store.plan({"operation": "create", "item": {"title": "Frozen", "body": "body"}})
        result = self.store.apply(plan["plan_id"])
        self.assertEqual(plan["details"]["ref"], result["details"]["ref"])
        self.assertEqual(result, self.store.apply(plan["plan_id"]))
        self.assertEqual(1, self.store.status()["personal_items"])

    def test_forced_random_collision_checks_retired_id(self):
        first = self.create()
        self.apply({"operation": "reset"})
        retired = first.rsplit("personal-", 1)[1]
        generated = [SimpleNamespace(hex=retired), SimpleNamespace(hex="a" * 32),
                     SimpleNamespace(hex="b" * 32)]
        with mock.patch.object(store_module.uuid, "uuid4", side_effect=generated):
            plan = self.store.plan({"operation": "create", "item": {"title": "Repeated title", "body": "Body"}})
        self.assertEqual("@local/personal:personal-" + "a" * 32, plan["details"]["ref"])
        self.assertEqual(plan["details"]["ref"], self.store.apply(plan["plan_id"])["details"]["ref"])

    def test_caller_cannot_supply_an_identity(self):
        for field, value in (("item_id", "old-id"), ("ref", "@local/personal:old-id")):
            with self.subTest(field=field), self.assertRaisesRegex(ValidationError, "runtime-owned"):
                self.store.plan({"operation": "create", "item": {"title": "A", "body": "b", field: value}})

    def test_members_only_creation_and_conflicting_dual_input(self):
        created = self.apply({"operation": "create", "item": {"title": "Files", "primary_member": "a.md",
                              "members": {"a.md": "Text", "z.md": "Auxiliary"}}})
        shown = self.store.show(created["details"]["ref"])
        self.assertEqual("Text", shown["item"]["body"])
        with self.assertRaisesRegex(ValidationError, "conflict"):
            self.store.plan({"operation": "create", "item": {"title": "Files", "body": "Different",
                            "primary_member": "a.md", "members": {"a.md": "Text"}}})

    def test_source_interruption_dry_run_is_read_only_and_refuses_mixed_state(self):
        self.create()
        plan = self.store.plan({"operation": "reset"})
        original = store_module._atomic_write

        def stop_before_runtime(path, value):
            if path == self.store._runtime_state_path:
                raise OSError("injected source interruption")
            return original(path, value)

        with mock.patch.object(store_module, "_atomic_write", side_effect=stop_before_runtime):
            with self.assertRaises(OSError):
                self.store.apply(plan["plan_id"])
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(CorpusStoreError, "needs recovery"):
            self.store.snapshot("claude", dry_run=True)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.store.apply(plan["plan_id"])
        self.assertEqual(0, self.store.status()["personal_items"])

    def test_reverting_edit_removes_override(self):
        ref = "@agent-bios/core:guide-tooling-gotchas"
        original = self.store.show(ref)
        self.apply({"operation": "update", "ref": ref, "item_digest": original["digest"],
                    "patch": {"title": "Changed"}})
        changed = self.store.show(ref)
        self.apply({"operation": "update", "ref": ref, "item_digest": changed["digest"],
                    "patch": {"title": original["item"]["title"]}})
        self.assertEqual(0, self.store.status()["overrides"])

    def test_body_only_edit_reaches_requested_file_and_keeps_old_snapshot(self):
        ref = self.create()
        old = self.store.snapshot("claude")
        shown = self.store.show(ref)
        self.apply({"operation": "update", "ref": ref, "item_digest": shown["digest"],
                    "patch": {"body": "Edited\nNEW_BODY"}})
        new = self.store.snapshot("claude")
        inventory = json.loads((Path(new["path"]) / "inventory.json").read_text())
        item = next(item for item in inventory["items"] if item["ref"] == ref)
        self.assertEqual("Edited\nNEW_BODY", item["members"][item["primary_member"]])
        new_files = list((Path(new["path"]) / "items").rglob("content.md"))
        self.assertTrue(any(path.read_text() == "Edited\nNEW_BODY" for path in new_files))
        old_files = list((Path(old["path"]) / "items").rglob("content.md"))
        self.assertTrue(any("OLD_BODY" in path.read_text() for path in old_files))

    def _mutable_package(self):
        destination = self.root / "package"
        for directory in ("compose", "claude", "learn"):
            shutil.copytree(self.repo / directory, destination / directory,
                            ignore=shutil.ignore_patterns("__pycache__"))
        self.store.repo = destination
        return destination

    def test_disjoint_overlay_survives_update_and_reverse_rollback(self):
        package = self._mutable_package()
        t1 = self.store.status()["selected_baseline_ref"]
        ref = "@agent-bios/core:guide-tooling-gotchas"
        shown = self.store.show(ref)
        self.apply({"operation": "update", "ref": ref, "item_digest": shown["digest"],
                    "patch": {"title": "Personal title"}})
        path = package / "claude/guides/tooling-gotchas.md"
        path.write_text(path.read_text() + "\nUpstream body update.\n")
        t2 = self.store.install(["all"])["baseline_ref"]
        self.apply({"operation": "rollback", "baseline_ref": t1})
        item = self.store.show(ref)["item"]
        self.assertEqual("Personal title", item["title"])
        self.assertNotIn("Upstream body update.", item["body"])
        snap = self.store.snapshot("claude")
        inventory = json.loads((Path(snap["path"]) / "inventory.json").read_text())
        self.assertIn(ref, {item["ref"] for item in inventory["items"]})
        self.assertEqual(t2, self.store.status()["last_successful_install_ref"])

    def test_overlapping_rollback_preserves_current_state(self):
        package = self._mutable_package()
        t1 = self.store.status()["selected_baseline_ref"]
        ref = "@agent-bios/core:guide-tooling-gotchas"
        path = package / "claude/guides/tooling-gotchas.md"
        path.write_text(path.read_text() + "\nUpstream body update.\n")
        self.store.install(["all"])
        shown = self.store.show(ref)
        self.apply({"operation": "update", "ref": ref, "item_digest": shown["digest"],
                    "patch": {"body": "My independent body"}})
        before = self.store.status()["revision"]
        with self.assertRaisesRegex(ValidationError, "baseline_update_conflict"):
            self.store.plan({"operation": "rollback", "baseline_ref": t1})
        self.assertEqual(before, self.store.status()["revision"])

    def test_install_preparation_does_not_publish(self):
        package = self._mutable_package()
        path = package / "claude/guides/tooling-gotchas.md"
        path.write_text(path.read_text() + "\nCandidate update.\n")
        before = self.store.status()["revision"]
        candidate = self.store.prepare_install(["all"])
        self.assertEqual(before, self.store.status()["revision"])
        result = self.store.commit_install(candidate)
        self.assertEqual(result, self.store.commit_install(candidate))
        self.assertNotEqual(before, self.store.status()["revision"])


if __name__ == "__main__":
    unittest.main()
