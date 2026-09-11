#!/usr/bin/env python3
"""Changed-path tests for CorpusStore's private, immutable lifecycle."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from compose.corpus_store import CorpusStore, CorpusStoreError, StaleRevision, ValidationError, verify_snapshot

_COLLECT_PATH = Path(__file__).resolve().parents[1] / "learn" / "collect-learning.py"
_COLLECT_SPEC = importlib.util.spec_from_file_location("test_collect_learning", _COLLECT_PATH)
assert _COLLECT_SPEC and _COLLECT_SPEC.loader
_COLLECT = importlib.util.module_from_spec(_COLLECT_SPEC)
_COLLECT_SPEC.loader.exec_module(_COLLECT)


class _Catalog:
    from corpus_catalog import normalize_content, update_content
    normalize_content = staticmethod(normalize_content)
    update_content = staticmethod(update_content)

    @staticmethod
    def load_catalog(_repo: Path) -> dict:
        return {
            "schema_version": 1,
            "packages": [{"package_id": "@core/base", "domains": {"core": "Core"}}],
            "items": [{
                "ref": "@core/base:hello", "package_id": "@core/base", "item_id": "hello",
                "title": "Hello", "body": "installed body", "surface": "always", "tier": "core",
                "domains": ["core"], "kind": "rule", "members": {"content.md": "installed body"}, "origin": {"kind": "installed"},
            }],
        }

    @staticmethod
    def compile_items(items: list[dict], destination: Path, host: str) -> dict:
        destination.mkdir(parents=True, exist_ok=True)
        text = "\n".join(item["body"] for item in items) + "\n"
        (destination / f"{host}.md").write_text(text, encoding="utf-8")
        return {"instruction_text": text, "files": [f"{host}.md"],
                "item_refs": [item["ref"] for item in items], "unavailable": []}


class _PathCatalog(_Catalog):
    @staticmethod
    def compile_items(items: list[dict], destination: Path, host: str) -> dict:
        destination.mkdir(parents=True, exist_ok=True)
        text = f"Read {destination / 'items' / 'linked.md'}\n"
        emitted = destination / f"{host}.md"
        emitted.write_text(text, encoding="utf-8")
        return {"instruction_text": text, "files": [f"{host}.md"],
                "item_refs": [item["ref"] for item in items], "unavailable": []}


class _NestedInventoryCatalog(_Catalog):
    @staticmethod
    def compile_items(items: list[dict], destination: Path, host: str) -> dict:
        target = destination / "nested" / "inventory.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("member bytes\n", encoding="utf-8")
        return {"instruction_text": "nested member\n", "files": ["nested/inventory.json"],
                "item_refs": [item["ref"] for item in items], "unavailable": []}


class _DomainTargetCatalog(_Catalog):
    @staticmethod
    def load_catalog(_repo: Path) -> dict:
        catalog = copy.deepcopy(_Catalog.load_catalog(_repo))
        catalog["items"].append({
            "ref": "@core/base:domain-target", "package_id": "@core/base", "item_id": "domain-target",
            "title": "Domain target", "body": "domain target", "surface": "always", "tier": "domain",
            "domains": ["extra"], "kind": "guide", "members": {"guide.md": "domain target"}, "origin": {},
        })
        return catalog


class _SharedTargetCatalog(_Catalog):
    @staticmethod
    def load_catalog(_repo: Path) -> dict:
        catalog = copy.deepcopy(_Catalog.load_catalog(_repo))
        catalog["items"][0]["members"] = {"shared.md": "shared", "sibling.md": "sibling"}
        catalog["items"][0]["body"] = "shared"
        return catalog


class _UpdatingCatalog(_Catalog):
    body = "T1"

    @staticmethod
    def load_catalog(_repo: Path) -> dict:
        catalog = copy.deepcopy(_Catalog.load_catalog(_repo))
        catalog["items"][0]["body"] = _UpdatingCatalog.body
        catalog["items"][0]["members"] = {"content.md": _UpdatingCatalog.body}
        return catalog


class CorpusStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "repo"
        (self.repo / "compose" / "bootstrap").mkdir(parents=True)
        (self.repo / "compose" / "bootstrap" / "SKILL.md").write_text("# corpus\n", encoding="utf-8")
        (self.repo / "compose" / "corpus_catalog.py").write_text("# fixture compiler\n", encoding="utf-8")
        self.store = CorpusStore(self.repo, root / "state", root / "user")
        self.store._catalog_module = lambda: _Catalog  # type: ignore[method-assign]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _apply(self, payload: dict) -> dict:
        plan = self.store.plan(payload)
        return self.store.apply(plan["plan_id"], plan["expected_revision"])

    def _snapshot_refs(self, host: str, **kwargs) -> list[str]:
        snapshot = self.store.snapshot(host, **kwargs)
        return [item["ref"] for item in self.store.snapshot_inventory(snapshot["content_ref"])["items"]]

    def test_enablement_is_not_deletion_and_preserves_edits_pins_and_updates(self) -> None:
        self.store.install()
        ref = "@core/base:hello"
        self._apply({"operation": "update", "ref": ref, "item_digest": self.store.show(ref)["digest"],
                     "patch": {"body": "my edited instruction"}})
        original = self.store.show(ref)["item"]
        pins = {host: self.store.snapshot(host) for host in ("claude", "codex")}
        inventories = {host: self.store.snapshot_inventory(pin["content_ref"]) for host, pin in pins.items()}
        self._apply({"operation": "enable", "items": {ref: False}})
        self.assertFalse(self.store.show(ref)["enabled"])
        self.assertEqual("active", self.store.show(ref)["state"])
        self.assertEqual(original, self.store.show(ref)["item"])
        self.assertEqual(0, self.store.status()["tombstones"])
        for host in pins:
            off = self.store.snapshot(host, selection=["all"])
            self.assertNotIn(ref, [item["ref"] for item in self.store.snapshot_inventory(off["content_ref"])["items"]])
            self.assertNotIn("my edited instruction", off["instruction_text"])
            self.assertEqual(off["content_ref"], self.store.snapshot(host, selection=["all"], dry_run=True)["content_ref"])
            self.assertEqual(inventories[host], self.store.snapshot_inventory(pins[host]["content_ref"]))
        self.store.install()
        self.assertFalse(self.store.show(ref)["enabled"])
        self.assertEqual(original, self.store.show(ref)["item"])
        self._apply({"operation": "enable", "items": {ref: True}})
        self.assertEqual(original, self.store.show(ref)["item"])
        self.assertIn(ref, self._snapshot_refs("codex"))
        self._apply({"operation": "enable", "items": {ref: False}})
        self._apply({"operation": "restore", "ref": ref})
        self.assertFalse(self.store.show(ref)["enabled"])
        self._apply({"operation": "reset"})
        self.assertTrue(self.store.show(ref)["enabled"])
        self.assertEqual({}, self.store.status()["enabled_overrides"])

    def test_enablement_overrides_default_selection_and_null_returns_to_defaults(self) -> None:
        self.store._catalog_module = lambda: _DomainTargetCatalog
        self.store.install()
        self._apply({"operation": "select", "selection": []})
        core, domain = "@core/base:hello", "@core/base:domain-target"
        before = {row["ref"]: row for row in self.store.list_items()}
        self.assertTrue(before[core]["enabled"])
        self.assertFalse(before[domain]["enabled"])
        result = self._apply({"operation": "enable", "items": {core: False, domain: True}})
        for host in ("claude", "codex"):
            self.assertEqual([domain], self._snapshot_refs(host, selection=[]))
            self.assertEqual([domain], self._snapshot_refs(host, selection=["all"]))
        self.assertTrue(self.store.history(core))
        self._apply({"operation": "rollback", "history_id": result["history_id"]})
        self.assertEqual({}, self.store.status()["enabled_overrides"])
        self._apply({"operation": "enable", "items": {core: False, domain: True}})
        self._apply({"operation": "enable", "items": {core: None, domain: None}})
        self.assertEqual([core], self._snapshot_refs("claude"))
        self.assertNotIn("enabled_overrides", json.loads(self.store._user_state_path.read_text()))

    def test_enablement_personal_removal_recovery_and_learning(self) -> None:
        self.store.install()
        ref = self._apply({"operation": "create", "item": {"title": "personal", "body": "personal body"}})["details"]["ref"]
        self._apply({"operation": "enable", "items": {ref: False}})
        self._apply({"operation": "update", "ref": ref, "item_digest": self.store.show(ref)["digest"],
                     "patch": {"body": "edited while off"}})
        self._apply({"operation": "remove", "ref": ref})
        with self.assertRaises(ValidationError):
            self.store.plan({"operation": "enable", "items": {ref: True}})
        self._apply({"operation": "recover", "ref": ref})
        self.assertFalse(self.store.show(ref)["enabled"])
        self.assertEqual("edited while off", self.store.show(ref)["item"]["body"])
        self._apply({"operation": "enable", "items": {ref: True}})
        self.assertIn(ref, self._snapshot_refs("codex"))
        learned = self.store.capture_learning("codex", self._learning("a kept lesson", 1))
        learned_ref = f"@local/learnings-codex:{learned['learning_id']}"
        self._apply({"operation": "enable", "items": {learned_ref: False}})
        self.assertFalse(self.store.show(learned_ref)["enabled"])
        self.assertNotIn(learned_ref, self._snapshot_refs("codex"))
        self.assertEqual(1, len(self.store._learning_events("codex")))
        self._apply({"operation": "enable", "items": {learned_ref: True}})
        self.assertIn(learned_ref, self._snapshot_refs("codex"))

    def test_enablement_batch_is_atomic_stale_checked_and_backward_compatible(self) -> None:
        self.store.install()
        ref = "@core/base:hello"
        before = self.store._user_state_path.read_bytes()
        self.assertNotIn("enabled_overrides", json.loads(before))
        rows = self.store.list_items()
        self.assertEqual(before, self.store._user_state_path.read_bytes())
        revision = self.store.status()["revision"]
        self.assertEqual(revision, rows[0]["revision"])
        for items in ({}, [], {ref: 0}, {ref: "false"}, {ref: False, "@core/base:missing": True}):
            with self.subTest(items=items), self.assertRaises(ValidationError):
                self.store.plan({"operation": "enable", "items": items})
            self.assertEqual(before, self.store._user_state_path.read_bytes())
        preview = self.store.plan({"operation": "enable", "items": {ref: False}, "expected_revision": revision})
        self._apply({"operation": "update", "ref": ref, "item_digest": self.store.show(ref)["digest"],
                     "patch": {"title": "Changed elsewhere"}})
        with self.assertRaises(StaleRevision):
            self.store.apply(preview["plan_id"], preview["expected_revision"])
        with self.assertRaises(StaleRevision):
            self.store.plan({"operation": "enable", "items": {ref: False}, "expected_revision": revision})
        self.assertTrue(self.store.show(ref)["enabled"])

    def test_enablement_prepared_transaction_recovers_from_legacy_state(self) -> None:
        self.store.install()
        ref = "@core/base:hello"
        preview = self.store.plan({"operation": "enable", "items": {ref: False}})
        journal = self.store.runtime / "transactions" / preview["plan_id"] / "journal.json"
        record = json.loads(journal.read_text())
        self.assertNotIn("enabled_overrides", record["plan"]["before"]["user"])
        record["state"] = "PREPARED"
        journal.write_text(json.dumps(record))
        self.assertEqual(preview["result_revision"], self.store.status()["revision"])
        self.assertFalse(self.store.show(ref)["enabled"])
        self.assertTrue(self.store.history(ref))
        self.assertNotIn(ref, self._snapshot_refs("codex"))

    @staticmethod
    def _learning(lesson: str, _number: int) -> dict:
        return _COLLECT.build_record({"lesson": lesson, "domain": "core", "supporting_sessions": ["codex:abcd"]})

    def _promotion(self, captured: dict, target_ref: str, *, member: str | None = None, exclusive: bool = True) -> dict:
        target = self.store.show(target_ref)
        row = {"learning_id": captured["learning_id"], "host": "codex", "source_digest": captured["digest"],
               "target_ref": target_ref, "target_digest": target["digest"], "exclusive": exclusive}
        if member is not None:
            row["target_member"] = member
            row.pop("exclusive")
        return row

    def test_install_create_edit_remove_restore_reset_and_snapshot(self) -> None:
        installed = self.store.install()
        self.assertEqual(1, installed["items"])
        before = self.store.snapshot("codex")
        created = self._apply({"operation": "create", "item": {"title": "Personal", "body": "personal body"}})
        ref = created["details"]["ref"]
        shown = self.store.show(ref)
        edited = self._apply({"operation": "update", "ref": ref, "item_digest": shown["digest"], "patch": {"body": "edited body"}})
        self.assertNotEqual(created["revision"], edited["revision"])
        after = self.store.snapshot("codex")
        self.assertNotEqual(before["content_ref"], after["content_ref"])
        self.assertIn("installed body", before["instruction_text"])  # pinned projection remains readable
        self._apply({"operation": "remove", "ref": "@core/base:hello"})
        self.assertEqual("removed", self.store.show("@core/base:hello")["state"])
        self._apply({"operation": "restore", "ref": "@core/base:hello"})
        self.assertEqual("active", self.store.show("@core/base:hello")["state"])
        reset = self._apply({"operation": "reset"})
        self.assertEqual(installed["baseline_ref"], self.store.status()["selected_baseline_ref"])
        self.assertTrue((self.store.user_root / "trash" / reset["history_id"] / "state.json").is_file())
        self.assertIn("installed body", self.store.snapshot("codex")["instruction_text"])

    def test_installed_override_keeps_baseline_and_restore_clears_it(self) -> None:
        self.store.install()
        original = self.store.show("@core/base:hello")
        self._apply({"operation": "update", "ref": "@core/base:hello", "item_digest": original["digest"], "patch": {"body": "my version"}})
        self.assertEqual("installed body", self.store.show("@core/base:hello", "installed")["item"]["body"])
        self.assertEqual("my version", self.store.show("@core/base:hello")["item"]["body"])
        self._apply({"operation": "restore", "ref": "@core/base:hello"})
        self.assertEqual("installed body", self.store.show("@core/base:hello")["item"]["body"])

    def test_stale_plan_and_item_digest_do_not_change_sources(self) -> None:
        self.store.install()
        status = self.store.status()
        first = self.store.plan({"operation": "create", "item": {"title": "A", "body": "a"}})
        self._apply({"operation": "create", "item": {"title": "B", "body": "b"}})
        with self.assertRaises(StaleRevision):
            self.store.apply(first["plan_id"], first["expected_revision"])
        self.assertEqual(1, len(self.store.list_items(include_removed=False)) - 1)
        base = self.store.show("@core/base:hello")
        with self.assertRaises(StaleRevision):
            self.store.plan({"operation": "update", "ref": base["ref"], "item_digest": "0" * 64, "patch": {"body": "bad"}})
        self.assertNotEqual(status["revision"], self.store.status()["revision"])
        self.assertEqual("installed body", self.store.show("@core/base:hello")["item"]["body"])

    def test_history_rollback_and_immutable_snapshot(self) -> None:
        self.store.install()
        snap_one = self.store.snapshot("claude")
        self._apply({"operation": "create", "item": {"title": "A", "body": "a"}})
        history = self.store.history()
        self.assertTrue(history)
        self._apply({"operation": "rollback", "history_id": history[0]["history_id"]})
        snap_two = self.store.snapshot("claude")
        self.assertEqual(snap_one["content_ref"], snap_two["content_ref"])
        self.assertIn("installed body", Path(snap_one["path"]).joinpath("claude.md").read_text(encoding="utf-8"))

    def test_rejects_unknown_fields_and_unowned_member_paths(self) -> None:
        self.store.install()
        with self.assertRaises(ValidationError):
            self.store.plan({"operation": "create", "item": {"title": "A", "body": "a", "digest": "forbidden"}})
        with self.assertRaises(ValidationError):
            self.store.plan({"operation": "create", "item": {"title": "A", "body": "a", "members": {"../escape.md": "x"}}})

    def test_capture_learning_is_immutable_and_changes_snapshot(self) -> None:
        self.store.install()
        before = self.store.snapshot("codex")
        record = self._learning("learned", 1)
        captured = self.store.capture_learning("codex", record)
        after = self.store.snapshot("codex")
        self.assertNotEqual(before["content_ref"], after["content_ref"])
        self.assertEqual(record["learning_id"], captured["learning_id"])
        source = self.store.user_root / "learnings" / "codex" / "events.jsonl"
        self.assertEqual(1, len(source.read_text(encoding="utf-8").splitlines()))
        with self.assertRaises(ValidationError):
            duplicate = dict(record)
            duplicate["lesson"] = "different"
            self.store.capture_learning("codex", duplicate)

    def test_reset_suppresses_prior_learning_without_deleting_its_source(self) -> None:
        self.store.install()
        self.store.capture_learning("codex", self._learning("old learning", 1))
        self.assertIn("old learning", self.store.snapshot("codex")["instruction_text"])
        self._apply({"operation": "reset"})
        self.assertNotIn("old learning", self.store.snapshot("codex")["instruction_text"])
        source = self.store.user_root / "learnings" / "codex" / "events.jsonl"
        self.assertIn("old learning", source.read_text(encoding="utf-8"))
        self.store.capture_learning("codex", self._learning("new learning", 2))
        emitted = self.store.snapshot("codex")["instruction_text"]
        self.assertIn("new learning", emitted)
        self.assertNotIn("old learning", emitted)

    def test_learning_sources_are_listed_and_support_show_edit_remove_recover(self) -> None:
        self.store.install()
        captured = self.store.capture_learning("codex", self._learning("first lesson", 1))
        ref = f"@local/learnings-codex:{captured['learning_id']}"
        self.assertIn(ref, {row["ref"] for row in self.store.list_items()})
        shown = self.store.show(ref)
        self._apply({"operation": "update", "ref": ref, "item_digest": shown["digest"],
                     "patch": {"body": "edited lesson", "members": {"learning.md": "edited lesson"}}})
        edited = self.store.show(ref)
        self.assertEqual("edited lesson", edited["item"]["body"])
        self._apply({"operation": "remove", "ref": ref, "item_digest": edited["digest"]})
        self.assertEqual("removed", self.store.show(ref)["state"])
        self.assertNotIn(ref, {row["ref"] for row in self.store.list_items(include_removed=False)})
        self._apply({"operation": "recover", "ref": ref})
        self.assertEqual("active", self.store.show(ref)["state"])

    def test_exact_promotion_suppresses_only_the_matching_learning_source(self) -> None:
        self.store.install()
        captured = self.store.capture_learning("codex", self._learning("installed body", 1))
        baseline = self.store.status()["selected_baseline_ref"]
        promotions = {"version": 3, "promotions": [self._promotion(captured, "@core/base:hello")]}
        (self.store.runtime / "baselines" / baseline / "promotions.json").write_text(json.dumps(promotions), encoding="utf-8")
        snapshot = self.store.snapshot("codex")
        self.assertEqual(1, snapshot["instruction_text"].count("installed body"))
        self.assertNotIn("promotion_mapping_incomplete", str(snapshot["unavailable"]))

    def test_legacy_promotion_keeps_learning_and_discloses_uncertainty(self) -> None:
        self.store.install()
        captured = self.store.capture_learning("codex", self._learning("legacy lesson", 1))
        baseline = self.store.status()["selected_baseline_ref"]
        (self.store.runtime / "baselines" / baseline / "promotions.json").write_text(json.dumps({
            "version": 2, "promotions": [{"learning_id": captured["learning_id"], "anchor": "guide.md"}],
        }), encoding="utf-8")
        snapshot = self.store.snapshot("codex")
        self.assertIn("legacy lesson", snapshot["instruction_text"])
        self.assertIn("promotion_mapping_incomplete", str(snapshot["unavailable"]))

    def test_edited_target_requires_exclusive_or_member_promotion_mapping(self) -> None:
        self.store.install()
        captured = self.store.capture_learning("codex", self._learning("installed body", 1))
        target = self.store.show("@core/base:hello")
        self._apply({"operation": "update", "ref": target["ref"], "item_digest": target["digest"],
                     "patch": {"body": "locally edited target"}})
        baseline = self.store.status()["selected_baseline_ref"]
        row = self._promotion(captured, "@core/base:hello")
        (self.store.runtime / "baselines" / baseline / "promotions.json").write_text(json.dumps({"version": 3, "promotions": [row]}), encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "learning_rebase_conflict"):
            self.store.snapshot("codex")

    def test_edited_learning_requires_a_proven_replacement(self) -> None:
        self.store.install()
        captured = self.store.capture_learning("codex", self._learning("captured lesson", 1))
        learning = self.store.show(f"@local/learnings-codex:{captured['learning_id']}")
        self._apply({"operation": "update", "ref": learning["ref"], "item_digest": learning["digest"],
                     "patch": {"body": "edited lesson", "members": {"learning.md": "edited lesson"}}})
        baseline = self.store.status()["selected_baseline_ref"]
        (self.store.runtime / "baselines" / baseline / "promotions.json").write_text(json.dumps({"version": 3, "promotions": [self._promotion(captured, "@core/base:hello")]}), encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "learning_rebase_conflict"):
            self.store.snapshot("codex")

    def test_promotion_keeps_source_when_its_target_domain_is_deselected(self) -> None:
        self.store._catalog_module = lambda: _DomainTargetCatalog  # type: ignore[method-assign]
        self.store.install([])
        captured = self.store.capture_learning("codex", self._learning("domain learning", 1))
        baseline = self.store.status()["selected_baseline_ref"]
        (self.store.runtime / "baselines" / baseline / "promotions.json").write_text(json.dumps({
            "version": 3, "promotions": [self._promotion(captured, "@core/base:domain-target")],
        }), encoding="utf-8")
        self.assertIn("domain learning", self.store.snapshot("codex")["instruction_text"])

    def test_member_promotion_rejects_sibling_loss_and_accepts_preservation(self) -> None:
        self.store._catalog_module = lambda: _SharedTargetCatalog  # type: ignore[method-assign]
        self.store.install()
        captured = self.store.capture_learning("codex", self._learning("edited", 1))
        target = self.store.show("@core/base:hello")
        self._apply({"operation": "update", "ref": target["ref"], "item_digest": target["digest"],
                     "patch": {"members": {"shared.md": "edited"}}})
        baseline = self.store.status()["selected_baseline_ref"]
        promotion = {"version": 3, "promotions": [self._promotion(captured, "@core/base:hello", member="shared.md")]}
        (self.store.runtime / "baselines" / baseline / "promotions.json").write_text(json.dumps(promotion), encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "learning_rebase_conflict"):
            self.store.snapshot("codex")
        repaired = self.store.show("@core/base:hello")
        self._apply({"operation": "update", "ref": repaired["ref"], "item_digest": repaired["digest"],
                     "patch": {"members": {"shared.md": "edited", "sibling.md": "sibling"}}})
        promotion["promotions"][0]["target_digest"] = self.store.show("@core/base:hello")["digest"]
        (self.store.runtime / "baselines" / baseline / "promotions.json").write_text(json.dumps(promotion), encoding="utf-8")
        self.assertEqual([], self.store.snapshot("codex")["unavailable"])
        self.assertIn("sibling.md", self.store.show("@core/base:hello")["item"]["members"])

    def test_prepared_journal_recovers_a_split_source_publication(self) -> None:
        self.store.install()
        preview = self.store.plan({"operation": "create", "item": {"title": "Interrupted", "body": "body"}})
        journal_path = self.store.runtime / "transactions" / preview["plan_id"] / "journal.json"
        plan = json.loads(journal_path.read_text(encoding="utf-8"))["plan"]
        # Model the only unsafe interval: user source published, runtime pointer
        # not yet published, and the process dies before COMMITTED.
        journal_path.write_text(json.dumps({"state": "PREPARED", "plan": plan}), encoding="utf-8")
        self.store._user_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.store._user_state_path.write_text(json.dumps(plan["after"]["user"]), encoding="utf-8")
        recovered = self.store.status()
        self.assertEqual(preview["result_revision"], recovered["revision"])
        self.assertEqual("RECOVERED_COMMITTED", json.loads(journal_path.read_text(encoding="utf-8"))["state"])

    def test_learning_overlay_survives_forward_and_reverse_baseline_switch(self) -> None:
        self.store._catalog_module = lambda: _UpdatingCatalog
        _UpdatingCatalog.body = "T1"
        first = self.store.install()["baseline_ref"]
        captured = self.store.capture_learning("codex", self._learning("Captured learning", 1))
        ref = f"@local/learnings-codex:{captured['learning_id']}"
        shown = self.store.show(ref)
        self._apply({"operation": "update", "ref": ref, "item_digest": shown["digest"],
                     "patch": {"body": "Edited learning"}})
        _UpdatingCatalog.body = "T2"
        self.store.install()
        self._apply({"operation": "rollback", "baseline_ref": first})
        self.assertIn("Edited learning", self.store.snapshot("codex")["instruction_text"])

    def test_dry_run_snapshot_has_no_persistent_snapshot(self) -> None:
        self.store.install()
        preview = self.store.snapshot("codex", dry_run=True)
        self.assertFalse(Path(preview["path"]).exists())
        self.assertTrue(preview["instruction_text"])
        committed = self.store.snapshot("codex")
        self.assertEqual(preview["content_ref"], committed["content_ref"])

    def test_snapshot_validates_selection_and_exposes_pinned_inventory(self) -> None:
        self.store.install([])
        with self.assertRaises(ValidationError):
            self.store.snapshot("codex", selection=["core"])
        with self.assertRaises(ValidationError):
            self.store.snapshot("codex", selection=["@core/base:missing"])
        snapshot = self.store.snapshot("codex", selection=[])
        self.assertIn(str(Path(snapshot["path"]) / "bootstrap" / "SKILL.md"), snapshot["instruction_text"])
        inventory = self.store.snapshot_inventory(snapshot["content_ref"])
        self.assertIn("bootstrap/SKILL.md", inventory["files"])
        self.assertEqual(snapshot["content_ref"], inventory["content_ref"])

    def test_pinned_snapshot_rejects_altered_missing_and_output_metadata_files(self) -> None:
        self.store.install()
        snapshot = self.store.snapshot("codex")
        root = Path(snapshot["path"])
        for relative, mutation in (("codex.md", b"altered\n"), ("output.json", b"{}\n")):
            path = root / relative
            original = path.read_bytes()
            path.write_bytes(mutation)
            with self.assertRaises(ValidationError):
                verify_snapshot(root, snapshot["content_ref"])
            with self.assertRaises(ValidationError):
                self.store.snapshot("codex")
            path.write_bytes(original)
            self.assertEqual(snapshot["content_ref"], verify_snapshot(root, snapshot["content_ref"])["content_ref"])
        path = root / "codex.md"
        original = path.read_bytes()
        path.unlink()
        with self.assertRaises(ValidationError):
            self.store.snapshot_inventory(snapshot["content_ref"])
        path.write_bytes(original)
        self.assertEqual(snapshot["content_ref"], self.store.snapshot_inventory(snapshot["content_ref"])["content_ref"])

    def test_nested_member_named_inventory_json_is_hashed(self) -> None:
        self.store._catalog_module = lambda: _NestedInventoryCatalog  # type: ignore[method-assign]
        self.store.install()
        snapshot = self.store.snapshot("codex")
        member = Path(snapshot["path"]) / "nested" / "inventory.json"
        self.assertIn("nested/inventory.json", verify_snapshot(Path(snapshot["path"]), snapshot["content_ref"])["file_digests"])
        member.write_text("altered\n", encoding="utf-8")
        with self.assertRaises(ValidationError):
            verify_snapshot(Path(snapshot["path"]), snapshot["content_ref"])

    def test_real_catalog_snapshot_file_digest_inventory_is_self_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = CorpusStore(Path(__file__).resolve().parents[1], root / "state", root / "user")
            store.install([])
            snapshot = store.snapshot("codex")
            verified = verify_snapshot(Path(snapshot["path"]), snapshot["content_ref"])
            self.assertGreater(len(verified["file_digests"]), 1)
            self.assertIn("output.json", verified["file_digests"])

    def test_real_catalog_can_remove_every_item_and_recover_through_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = CorpusStore(Path(__file__).resolve().parents[1], root / "state", root / "user")
            store.install([])
            original_rows = store.list_items(include_removed=False)
            original_refs = [row["ref"] for row in original_rows]
            self.assertTrue(original_refs)
            for ref in original_refs:
                plan = store.plan({"operation": "remove", "ref": ref})
                store.apply(plan["plan_id"], plan["expected_revision"])
            empty = store.snapshot("codex")
            empty_inventory = store.snapshot_inventory(empty["content_ref"])
            self.assertEqual([], empty_inventory["item_refs"])
            self.assertIn("Corpus management: invoke $corpus", empty["instruction_text"])
            self.assertTrue((Path(empty["path"]) / "bootstrap" / "SKILL.md").is_file())
            self.assertGreaterEqual(len(empty_inventory["files"]), 2)
            restored = next(row["ref"] for row in original_rows if row["tier"] in {"core", "infra"})
            plan = store.plan({"operation": "restore", "ref": restored})
            store.apply(plan["plan_id"], plan["expected_revision"])
            self.assertIn(restored, store.snapshot_inventory(store.snapshot("codex")["content_ref"])["item_refs"])

    def test_install_preserves_all_selection_literal(self) -> None:
        self.store.install(["all"])
        self.assertIn("all", self.store._read_baseline(self.store.status()["selected_baseline_ref"])[1]["selection"])
        self.assertTrue(self.store.snapshot("codex")["instruction_text"])

    def test_no_change_update_adopts_t2_and_same_field_overlay_conflicts(self) -> None:
        self.store._catalog_module = lambda: _UpdatingCatalog  # type: ignore[method-assign]
        _UpdatingCatalog.body = "T1"
        t1 = self.store.install()
        _UpdatingCatalog.body = "T2"
        t2 = self.store.install()
        self.assertNotEqual(t1["baseline_ref"], t2["baseline_ref"])
        self.assertEqual(t2["baseline_ref"], self.store.status()["selected_baseline_ref"])
        self.assertEqual("T2", self.store.show("@core/base:hello")["item"]["body"])
        original = self.store.show("@core/base:hello")
        self._apply({"operation": "update", "ref": original["ref"], "item_digest": original["digest"],
                     "patch": {"surface": "requested"}})
        _UpdatingCatalog.body = "T3"
        rebased = self.store.install()
        self.assertEqual(rebased["baseline_ref"], self.store.status()["selected_baseline_ref"])
        self.assertEqual("T3", self.store.show("@core/base:hello")["item"]["body"])
        self.assertEqual("requested", self.store.show("@core/base:hello")["item"]["surface"])
        current = self.store.show("@core/base:hello")
        self._apply({"operation": "update", "ref": current["ref"], "item_digest": current["digest"],
                     "patch": {"body": "mine"}})
        _UpdatingCatalog.body = "T4"
        before = self.store.status()
        with self.assertRaisesRegex(ValidationError, "baseline_update_conflict"):
            self.store.install()
        after = self.store.status()
        self.assertEqual(before["last_successful_install_ref"], after["last_successful_install_ref"])
        self.assertEqual(before["selected_baseline_ref"], after["selected_baseline_ref"])

    def test_published_snapshot_rewrites_compiler_staging_paths_on_disk(self) -> None:
        self.store._catalog_module = lambda: _PathCatalog  # type: ignore[method-assign]
        self.store.install()
        snapshot = self.store.snapshot("claude")
        root = Path(snapshot["path"])
        emitted = (root / "claude.md").read_text(encoding="utf-8")
        self.assertIn(str(root / "items" / "linked.md"), emitted)
        self.assertNotIn("agent-bios-snapshot", emitted)
        self.assertNotIn(".staging-", emitted)

    def test_refuses_a_symlinked_runtime_root(self) -> None:
        target = Path(self.tmp.name) / "outside"
        target.mkdir()
        linked = Path(self.tmp.name) / "linked-state"
        linked.symlink_to(target, target_is_directory=True)
        store = CorpusStore(self.repo, linked, Path(self.tmp.name) / "user-two")
        store._catalog_module = lambda: _Catalog  # type: ignore[method-assign]
        with self.assertRaises(CorpusStoreError):
            store.install()

    def test_refuses_a_symlinked_personal_root(self) -> None:
        target = Path(self.tmp.name) / "outside-user"
        target.mkdir()
        linked = Path(self.tmp.name) / "linked-user"
        linked.symlink_to(target, target_is_directory=True)
        store = CorpusStore(self.repo, Path(self.tmp.name) / "state-two", linked)
        store._catalog_module = lambda: _Catalog  # type: ignore[method-assign]
        with self.assertRaises(CorpusStoreError):
            store.install()


if __name__ == "__main__":
    unittest.main()
