#!/usr/bin/env python3
"""Changed-path tests for InstructionsStore's private, immutable lifecycle."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from compose import instructions_store
from compose.instructions_store import InstructionsStore, InstructionsStoreError, StaleRevision, ValidationError, verify_snapshot

_COLLECT_PATH = Path(__file__).resolve().parents[1] / "learn" / "collect-learning.py"
_COLLECT_SPEC = importlib.util.spec_from_file_location("test_collect_learning", _COLLECT_PATH)
assert _COLLECT_SPEC and _COLLECT_SPEC.loader
_COLLECT = importlib.util.module_from_spec(_COLLECT_SPEC)
_COLLECT_SPEC.loader.exec_module(_COLLECT)


class _Catalog:
    from instructions_catalog import normalize_content, update_content
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


class _StoreFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "repo"
        (self.repo / "compose" / "bootstrap").mkdir(parents=True)
        (self.repo / "compose" / "bootstrap" / "SKILL.md").write_text("# instructions\n", encoding="utf-8")
        (self.repo / "compose" / "instructions_catalog.py").write_text("# fixture compiler\n", encoding="utf-8")
        self.store = InstructionsStore(self.repo, root / "state", root / "user")
        self.store._catalog_module = lambda: _Catalog  # type: ignore[method-assign]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _apply(self, payload: dict) -> dict:
        plan = self.store.plan(payload)
        return self.store.apply(plan["plan_id"], plan["expected_revision"])

    def _snapshot_refs(self, host: str, **kwargs) -> list[str]:
        snapshot = self.store.snapshot(host, **kwargs)
        return [item["ref"] for item in self.store.snapshot_inventory(snapshot["content_ref"])["items"]]


class InstructionsStoreTest(_StoreFixture):
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

    def test_learning_events_hold_line_separators_and_bare_cr_whitespace(self) -> None:
        # a learning event ends at "\n" only: the writer keeps U+2028 and U+2029 raw inside the
        # lesson, and a bare CR between tokens is JSON whitespace; neither ends the event
        self.store.install()
        lesson = "before\u2028between\u2029after"
        first = self.store.capture_learning("codex", self._learning(lesson, 1))
        second = self.store.capture_learning("codex", self._learning("second lesson", 2))
        source = self.store.user_root / "learnings" / "codex" / "events.jsonl"
        lines = source.read_bytes().split(b"\n")
        self.assertEqual(3, len(lines))
        source.write_bytes(lines[0] + b"\n" + b"{\r" + lines[1][1:] + b"\r\n")
        refs = {row["ref"] for row in self.store.list_items()}
        for captured in (first, second):
            self.assertIn(f"@local/learnings-codex:{captured['learning_id']}", refs)
        self.assertEqual(lesson, self.store.show(f"@local/learnings-codex:{first['learning_id']}")["item"]["body"])

    def test_a_release_store_reads_with_its_own_roots_splitter(self) -> None:
        # A private release's store is loaded by path while another root's host_platform is
        # already imported (the installer's); it must still read with its own root's splitter,
        # and fail naming that path when its own root lacks one.
        import re
        import shutil
        import sys
        import host_platform  # noqa: F401 - the checkout's module, cached as the installer leaves it
        self.assertIn("host_platform", sys.modules)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td).resolve()
            release = base / "release"
            (release / "compose").mkdir(parents=True)
            shutil.copy2(Path(__file__).resolve().parent / "instructions_store.py", release / "compose" / "instructions_store.py")
            spec = importlib.util.spec_from_file_location("test_release_instructions_store", release / "compose" / "instructions_store.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            store = module.InstructionsStore(release, base / "state", base / "user")
            events = base / "user" / "learnings" / "codex" / "events.jsonl"
            events.parent.mkdir(parents=True)
            events.write_text('{"a": 1}\n', encoding="utf-8")
            with self.assertRaisesRegex(FileNotFoundError, re.escape(str(release / "wrappers" / "jsonl_lines.py"))):
                store._learning_events("codex")
            (release / "wrappers").mkdir()
            shutil.copy2(Path(__file__).resolve().parents[1] / "wrappers" / "jsonl_lines.py", release / "wrappers" / "jsonl_lines.py")
            self.assertEqual([{"a": 1}], store._learning_events("codex"))

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
            store = InstructionsStore(Path(__file__).resolve().parents[1], root / "state", root / "user")
            store.install([])
            snapshot = store.snapshot("codex")
            verified = verify_snapshot(Path(snapshot["path"]), snapshot["content_ref"])
            self.assertGreater(len(verified["file_digests"]), 1)
            self.assertIn("output.json", verified["file_digests"])

    def test_real_catalog_can_remove_every_item_and_recover_through_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = InstructionsStore(Path(__file__).resolve().parents[1], root / "state", root / "user")
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
            self.assertIn("Instructions management: invoke $agent-bios", empty["instruction_text"])
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
        store = InstructionsStore(self.repo, linked, Path(self.tmp.name) / "user-two")
        store._catalog_module = lambda: _Catalog  # type: ignore[method-assign]
        with self.assertRaises(InstructionsStoreError):
            store.install()

    def test_refuses_a_symlinked_personal_root(self) -> None:
        target = Path(self.tmp.name) / "outside-user"
        target.mkdir()
        linked = Path(self.tmp.name) / "linked-user"
        linked.symlink_to(target, target_is_directory=True)
        store = InstructionsStore(self.repo, Path(self.tmp.name) / "state-two", linked)
        store._catalog_module = lambda: _Catalog  # type: ignore[method-assign]
        with self.assertRaises(InstructionsStoreError):
            store.install()


class InstallationBindingTest(_StoreFixture):
    """The consumer half of probe 10: scenarios c2 B and C, c4 unbound, and receipt identity.

    The installer's own writing is covered in `test_instructions_install.py`; what is planted here is
    exactly the state a snapshot reads — the install record, its COMMITTED journal, and the receipt.
    """

    def digests(self) -> dict[str, str]:
        """The three release files a snapshot hashes into its inputs, keyed by their release path."""
        return {"compose/instructions_catalog.py": (self.repo / "compose" / "instructions_catalog.py").read_bytes(),
                "compose/instructions_store.py": Path(instructions_store.__file__).read_bytes(),
                "compose/bootstrap/SKILL.md": (self.repo / "compose" / "bootstrap" / "SKILL.md").read_bytes()}

    def installer_fields(self, **overrides) -> dict:
        """The installer block as the writer writes it: every field present, and `digest` the canonical
        hash of `files`, which is what `_installer_code` derives it from and the reader re-derives."""
        files = [{"path": "compose/instructions_install.py", "sha256": "2b" * 32},
                 {"path": "compose/instructions_transaction.py", "sha256": "3c" * 32}]
        digest = hashlib.sha256(json.dumps(files, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode("utf-8")).hexdigest()
        return {"digest_at_import": digest, "digest": digest, "build": "0.0.0-fixture", "root": "/fixture",
                "files": files, "package_modules_run": [{"path": "compose/instructions_store.py",
                                                         "sha256": "4d" * 32}], **overrides}

    def receipt_body(self, transaction_id: str, baseline_ref: str, **overrides) -> dict:
        """The body the installer would write for this store, with any field replaced for a control."""
        body = {
            "schema": "InstallationReceipt/v1", "result": "success", "transaction_id": transaction_id,
            "installer": self.installer_fields(),
            "begun_by_installer_digest": None, "release_digest": "release-" + transaction_id,
            "baseline_ref": baseline_ref, "selection": [],
            "artifacts": [{"path": path, "sha256": hashlib.sha256(content).hexdigest(), "role": "release"}
                          for path, content in sorted(self.digests().items())],
            "at": 0,
        }
        body.update(overrides)
        return body

    def write_receipt(self, body: dict) -> str:
        raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        receipt_id = hashlib.sha256(raw).hexdigest()
        path = self.store.runtime / "receipts" / f"{receipt_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return receipt_id

    def plant(self, transaction_id: str = "tx-a", *, receipt: bool = True, committed: bool = True,
              record_transaction: bool = True, **overrides) -> str | None:
        """Install state pointing at one transaction, as the installer leaves it."""
        baseline_ref = self.store.status()["selected_baseline_ref"]
        receipt_id = self.write_receipt(self.receipt_body(transaction_id, baseline_ref, **overrides)) if receipt else None
        record = {"schema_version": 1, "package_root": str(self.repo), "release_digest": "release-" + transaction_id}
        if record_transaction:
            record["transaction_id"] = transaction_id
        (self.store.runtime / "private-install.json").write_text(json.dumps(record), encoding="utf-8")
        journal = self.store.runtime / "installer-transactions" / transaction_id / "journal.json"
        journal.parent.mkdir(parents=True, exist_ok=True)
        # A pending journal would stop every read (`guard_pending`), so "not committed" here is a
        # superseded transaction: readable, and no binding.
        data = {"state": "COMMITTED" if committed else "SUPERSEDED"}
        if receipt_id:
            data["receipt_id"] = receipt_id
        journal.write_text(json.dumps(data), encoding="utf-8")
        return receipt_id

    def inputs(self, host: str = "codex") -> dict:
        """`snapshot()` returns the compiled result; the recorded inputs are read back from the snapshot."""
        return self.store.snapshot_inventory(self.store.snapshot(host)["content_ref"])["inputs"]

    # ---- the binding a snapshot carries --------------------------------------------------------

    def test_a_snapshot_records_the_receipt_id_before_its_content_ref_is_derived(self) -> None:
        self.store.install()
        receipt_id = self.plant("tx-a")
        snapshot = self.store.snapshot("codex")
        inventory = self.store.snapshot_inventory(snapshot["content_ref"])
        self.assertEqual(receipt_id, inventory["inputs"]["installation_receipt_id"])
        # content_ref is the digest of exactly those inputs, so the binding is immutable with no pin change.
        self.assertEqual(snapshot["content_ref"],
                         hashlib.sha256(json.dumps(inventory["inputs"], ensure_ascii=False, sort_keys=True,
                                                   separators=(",", ":")).encode("utf-8")).hexdigest())
        binding = inventory["installation_binding"]
        self.assertTrue(binding["bound"])
        self.assertEqual({"bound", "receipt_id", "transaction_id", "installer_digest", "release_digest",
                          "begun_by_installer_digest"}, set(binding))
        self.assertEqual("tx-a", binding["transaction_id"])
        self.assertEqual(receipt_id, binding["receipt_id"])
        self.assertEqual("release-tx-a", binding["release_digest"])

    def test_two_installs_of_one_release_bind_their_sessions_to_their_own_receipts(self) -> None:
        # c2 B and C: the second install does not move the first snapshot, and the two differ only
        # in the receipt id, so `content_ref` separates them.
        self.store.install()
        first_receipt = self.plant("tx-a")
        first = self.store.snapshot("codex")
        first_bytes = (Path(first["path"]) / "inventory.json").read_bytes()
        second_receipt = self.plant("tx-b")
        second = self.store.snapshot("codex")
        self.assertNotEqual(first["content_ref"], second["content_ref"])
        first_inputs = self.store.snapshot_inventory(first["content_ref"])["inputs"]
        second_inputs = self.store.snapshot_inventory(second["content_ref"])["inputs"]
        differing = {key for key in second_inputs if second_inputs[key] != first_inputs[key]}
        self.assertEqual({"installation_receipt_id"}, differing)
        self.assertEqual(first_bytes, (Path(first["path"]) / "inventory.json").read_bytes())
        self.assertEqual(first_receipt, self.store.snapshot_inventory(first["content_ref"])["inputs"]["installation_receipt_id"])
        self.assertEqual(second_receipt, self.store.snapshot_inventory(second["content_ref"])["installation_binding"]["receipt_id"])
        # Control: the same receipt id again yields the same content_ref.
        self.plant("tx-a")
        self.assertEqual(first["content_ref"], self.store.snapshot("codex")["content_ref"])

    def test_an_earlier_snapshot_keeps_binding_to_the_receipt_it_was_built_from(self) -> None:
        self.store.install()
        first_receipt = self.plant("tx-a")
        first = self.store.snapshot("codex")
        self.plant("tx-b")
        binding = self.store.snapshot_inventory(first["content_ref"])["installation_binding"]
        self.assertTrue(binding["bound"])
        self.assertEqual(first_receipt, binding["receipt_id"])
        self.assertEqual("tx-a", binding["transaction_id"])

    # ---- c4: unbound is a verdict, never a refusal ---------------------------------------------

    def test_a_snapshot_whose_artifacts_differ_from_the_receipt_is_unbound_by_field(self) -> None:
        self.store.install()
        receipt_id = self.plant("tx-a")
        inputs = self.inputs()
        forged = {**inputs, "compiler_digest": "f" * 64, "store_schema_digest": "f" * 64}
        verdict = instructions_store.installation_binding(self.store.state_root, forged)
        self.assertFalse(verdict["bound"])
        self.assertEqual(receipt_id, verdict["receipt_id"])
        self.assertIn("compiler_digest", verdict["reason"])
        self.assertIn("store_schema_digest", verdict["reason"])
        self.assertNotIn("bootstrap_digest", verdict["reason"])

    def test_a_snapshot_from_another_baseline_is_unbound_by_name(self) -> None:
        self.store.install()
        self.plant("tx-a")
        inputs = self.inputs()
        verdict = instructions_store.installation_binding(self.store.state_root, {**inputs, "baseline_ref": "other"})
        self.assertFalse(verdict["bound"])
        self.assertIn("baseline_ref", verdict["reason"])

    def test_a_tampered_or_missing_receipt_is_unbound_with_its_reason(self) -> None:
        self.store.install()
        receipt_id = self.plant("tx-a")
        inputs = self.inputs()
        self.assertTrue(instructions_store.installation_binding(self.store.state_root, inputs)["bound"])
        path = self.store.runtime / "receipts" / f"{receipt_id}.json"
        path.write_bytes(path.read_bytes().replace(b'"result":"success"', b'"result":"SUCCESS"'))
        tampered = instructions_store.installation_binding(self.store.state_root, inputs)
        self.assertFalse(tampered["bound"])
        self.assertIn("does not hash to its id", tampered["reason"])
        path.unlink()
        missing = instructions_store.installation_binding(self.store.state_root, inputs)
        self.assertFalse(missing["bound"])
        self.assertIn("missing", missing["reason"])

    def test_an_installation_without_a_receipt_leaves_the_snapshot_unbound(self) -> None:
        # The pre-receipt installer: a record with no transaction id, and a committed journal with no
        # receipt id. Both must read as "no receipt", never as a bound snapshot.
        self.store.install()
        self.plant("tx-a", receipt=False, record_transaction=False)
        inputs = self.inputs()
        self.assertIsNone(inputs["installation_receipt_id"])
        verdict = instructions_store.installation_binding(self.store.state_root, inputs)
        self.assertFalse(verdict["bound"])
        self.assertEqual("snapshot records no installation receipt", verdict["reason"])
        self.assertFalse(self.store.snapshot_inventory(
            self.store.snapshot("codex")["content_ref"])["installation_binding"]["bound"])

    def test_a_transaction_that_has_not_committed_is_not_read_as_a_binding(self) -> None:
        self.store.install()
        self.plant("tx-a", committed=False)
        self.assertIsNone(self.inputs()["installation_receipt_id"])

    def test_a_receipt_the_store_cannot_verify_leaves_the_snapshot_unbound(self) -> None:
        # The journal names a receipt whose artifacts do not cover this store, so the snapshot refuses
        # to record it in the first place rather than recording a binding that will not verify.
        self.store.install()
        baseline_ref = self.store.status()["selected_baseline_ref"]
        body = self.receipt_body("tx-a", baseline_ref)
        body["artifacts"] = [{**row, "sha256": "0" * 64} for row in body["artifacts"]]
        receipt_id = self.write_receipt(body)
        (self.store.runtime / "private-install.json").write_text(
            json.dumps({"schema_version": 1, "transaction_id": "tx-a", "package_root": str(self.repo)}), encoding="utf-8")
        journal = self.store.runtime / "installer-transactions" / "tx-a" / "journal.json"
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text(json.dumps({"state": "COMMITTED", "receipt_id": receipt_id}), encoding="utf-8")
        self.assertIsNone(self.inputs()["installation_receipt_id"])

    # ---- receipt identity (done-when 6) --------------------------------------------------------

    def test_reading_a_receipt_is_the_check_that_its_bytes_were_not_edited(self) -> None:
        self.store.install()
        receipt_id = self.plant("tx-a")
        receipt = instructions_store.read_installation_receipt(self.store.state_root, receipt_id)
        self.assertEqual("tx-a", receipt["transaction_id"])
        path = self.store.runtime / "receipts" / f"{receipt_id}.json"
        # A re-serialization with reordered keys is the same canonical bytes, so it still reads.
        reordered = dict(reversed(list(json.loads(path.read_bytes()).items())))
        path.write_bytes(json.dumps(reordered, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        self.assertEqual(receipt, instructions_store.read_installation_receipt(self.store.state_root, receipt_id))
        # One changed byte is not.
        path.write_bytes(path.read_bytes().replace(b'"at":0', b'"at":1'))
        with self.assertRaises(ValidationError):
            instructions_store.read_installation_receipt(self.store.state_root, receipt_id)

    def test_a_receipt_that_is_not_a_success_receipt_is_not_evidence(self) -> None:
        self.store.install()
        baseline_ref = self.store.status()["selected_baseline_ref"]
        for overrides in ({"schema": "InstallationReceipt/v2"}, {"result": "failed"}):
            receipt_id = self.write_receipt(self.receipt_body("tx-a", baseline_ref, **overrides))
            with self.assertRaises(ValidationError):
                instructions_store.read_installation_receipt(self.store.state_root, receipt_id)

    def test_a_receipt_that_hashes_to_its_name_and_breaks_its_contract_is_unbound_by_reason(self) -> None:
        # Each of these recomputes its own file name, so the hash check passes: what is tested is the
        # contract, which was accepted as bound or raised where a verdict was promised (X r1 F4).
        self.store.install()
        baseline_ref = self.store.status()["selected_baseline_ref"]
        inputs = self.inputs()
        written = self.installer_fields()
        cases = {
            "carries its own id": {"receipt_id": "0" * 64},
            "names no installer": {"installer": None},
            # every field below is one the writer always writes, so its absence is not a receipt (X r2 F2)
            "is not the shape the installer writes: root": {"installer": {
                key: value for key, value in written.items() if key != "root"}},
            "is not the shape the installer writes: ran_at": {"installer": {**written, "ran_at": 1}},
            "two different installer digests": {"installer": self.installer_fields(digest_at_import="a" * 64)},
            "installer digests are not digests": {"installer": self.installer_fields(
                digest_at_import="nope", digest="nope")},
            "installer names no root": {"installer": self.installer_fields(root="")},
            "build is neither a version nor absent": {"installer": self.installer_fields(build=5)},
            "lists no installer files": {"installer": self.installer_fields(files=[])},
            "installer file row of another shape": {"installer": self.installer_fields(
                files=[{"path": "compose/instructions_install.py", "sha256": None}])},
            "is not the hash of its own file list": {"installer": self.installer_fields(
                digest_at_import="b" * 64, digest="b" * 64)},
            "lists no package modules": {"installer": self.installer_fields(package_modules_run=None)},
            "package module row of another shape": {"installer": self.installer_fields(
                package_modules_run=[{"path": "compose/instructions_store.py"}])},
            "transaction_id is not a str": {"transaction_id": None},   # overrides the body's own value
            "at is not a int": {"at": "2026-11-11"},
            "beginning installer digest is not a digest": {"begun_by_installer_digest": "earlier"},
            "equals the finishing one": {"begun_by_installer_digest": written["digest"]},
            "lists no artifacts": {"artifacts": None},
            "artifact row of another shape": {"artifacts": [{"path": "compose/instructions_store.py",
                                                             "sha256": "0" * 64}]},
            # an unhashable role reached set membership and raised where a verdict was promised (X r2 F1)
            "artifact row of another shape (role is a list)": {"artifacts": [
                {"path": "compose/instructions_store.py", "sha256": "0" * 64, "role": []}]},
            "artifact row of another shape (role is an object)": {"artifacts": [
                {"path": "compose/instructions_store.py", "sha256": "0" * 64, "role": {"release": True}}]},
        }
        missing = {"names no beginning installer digest, not even as absent": "begun_by_installer_digest"}
        for expected, overrides in {**cases, **{key: {} for key in missing}}.items():
            with self.subTest(case=expected):
                body = self.receipt_body("tx-a", baseline_ref)
                body.update(overrides)
                body.pop(missing.get(expected, ""), None)
                receipt_id = self.write_receipt(body)
                with self.assertRaises(ValidationError) as caught:
                    instructions_store.read_installation_receipt(self.store.state_root, receipt_id)
                self.assertIn(expected.split(" (")[0], str(caught.exception))
                verdict = instructions_store.installation_binding(
                    self.store.state_root, {**inputs, "installation_receipt_id": receipt_id})
                self.assertFalse(verdict["bound"])
                self.assertIn(expected.split(" (")[0], verdict["reason"])

    def test_a_receipt_id_may_not_leave_the_receipt_directory(self) -> None:
        self.store.install()
        for receipt_id in ("../private-install", "/etc/passwd", ""):
            with self.assertRaises(ValidationError):
                instructions_store.read_installation_receipt(self.store.state_root, receipt_id)
        symlinked = self.store.runtime / "receipts" / f"{'a' * 64}.json"
        symlinked.parent.mkdir(parents=True, exist_ok=True)
        symlinked.symlink_to(self.repo / "compose" / "instructions_catalog.py")
        with self.assertRaises(InstructionsStoreError):
            instructions_store.read_installation_receipt(self.store.state_root, "a" * 64)


if __name__ == "__main__":
    unittest.main()
