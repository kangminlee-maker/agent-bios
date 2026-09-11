#!/usr/bin/env python3
"""Real-store checks for the Corpus CLI and mounted Textual Studio."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
COMPOSE = REPO / "compose"
if str(COMPOSE) not in sys.path:
    sys.path.insert(0, str(COMPOSE))

from corpus_store import CorpusStore  # noqa: E402


class CorpusFixture:
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="agent-bios-corpus-ui-test-")
        root = Path(self.temp.name)
        self.state = root / "state"
        self.user = root / "user"
        self.store = CorpusStore(REPO, state_root=self.state, user_root=self.user)
        installed = self.store.install()
        self.assertGreater(installed["items"], 0)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def personal_item(title: str, body: str = "Use the real store.\n") -> dict[str, object]:
        return {
            "title": title,
            "body": body,
            "surface": "requested",
            "tier": "env-personal",
            "domains": ["personal"],
            "kind": "rule",
            "members": {"content.md": body},
        }

class CorpusStoreCase(CorpusFixture, unittest.TestCase):
    def test_machine_cli_real_store_roundtrip(self) -> None:
        request = Path(self.temp.name) / "request.json"
        request.write_text(
            json.dumps({"operation": "create", "item": self.personal_item("CLI item")}),
            encoding="utf-8",
        )
        base = [
            sys.executable, str(COMPOSE / "corpus.py"), "--repo", str(REPO),
            "--state-dir", str(self.state), "--user-dir", str(self.user), "--json",
        ]
        planned = subprocess.run(
            [*base, "plan", "--input", str(request)], text=True, capture_output=True, check=True,
        )
        plan = json.loads(planned.stdout)
        self.assertEqual(plan["details"]["operation"], "create")
        applied = subprocess.run(
            [*base, "apply", plan["plan_id"], "--expected-revision", plan["expected_revision"]],
            text=True, capture_output=True, check=True,
        )
        result = json.loads(applied.stdout)
        ref = result["details"]["ref"]
        listing = json.loads(subprocess.run(
            [*base, "search", "CLI item"], text=True, capture_output=True, check=True,
        ).stdout)
        self.assertEqual([row["ref"] for row in listing], [ref])
        shown = json.loads(subprocess.run(
            [*base, "show", ref], text=True, capture_output=True, check=True,
        ).stdout)
        self.assertEqual(shown["item"]["title"], "CLI item")
        snapshot = json.loads(subprocess.run(
            [*base, "snapshot", "--host", "codex"], text=True, capture_output=True, check=True,
        ).stdout)
        snapshot_root = Path(snapshot["path"])
        self.assertTrue((snapshot_root / "bootstrap" / "SKILL.md").is_file())
        self.assertIn(ref, snapshot["instruction_text"])
        pinned = json.loads(subprocess.run(
            [*base, "snapshot", "--content-ref", snapshot["content_ref"]],
            text=True, capture_output=True, check=True,
        ).stdout)
        self.assertEqual(pinned["content_ref"], snapshot["content_ref"])
        pinned_item = next(item for item in pinned["items"] if item["ref"] == ref)
        self.assertEqual(pinned_item["body"], "Use the real store.\n")

        # The machine plan/apply path uses the same non-destructive toggle as Studio.
        request.write_text(json.dumps({"operation": "enable", "items": {ref: False},
                                       "expected_revision": self.store.status()["revision"]}), encoding="utf-8")
        disabled = json.loads(subprocess.run(
            [*base, "plan", "--input", str(request)], text=True, capture_output=True, check=True,
        ).stdout)
        subprocess.run([*base, "apply", disabled["plan_id"], "--expected-revision", disabled["expected_revision"]],
                       text=True, capture_output=True, check=True)
        disabled_row = next(row for row in self.store.list_items() if row["ref"] == ref)
        self.assertFalse(disabled_row["enabled"])
        self.assertEqual("active", disabled_row["state"])
        disabled_snapshot = json.loads(subprocess.run(
            [*base, "snapshot", "--host", "codex"], text=True, capture_output=True, check=True,
        ).stdout)
        self.assertNotIn(ref, disabled_snapshot["instruction_text"])

        current = next(item for item in self.store.list_items() if item["ref"] == ref)
        request.write_text(json.dumps({
            "operation": "remove", "ref": ref, "item_digest": current["digest"],
        }), encoding="utf-8")
        removal = json.loads(subprocess.run(
            [*base, "plan", "--input", str(request)], text=True, capture_output=True, check=True,
        ).stdout)
        subprocess.run(
            [*base, "apply", removal["plan_id"], "--expected-revision", removal["expected_revision"]],
            text=True, capture_output=True, check=True,
        )
        self.assertEqual(
            next(item for item in self.store.list_items() if item["ref"] == ref)["state"],
            "removed",
        )
        pinned_after = json.loads(subprocess.run(
            [*base, "snapshot", "--content-ref", snapshot["content_ref"]],
            text=True, capture_output=True, check=True,
        ).stdout)
        self.assertEqual(pinned_after, pinned)
        self.assertEqual(
            next(item for item in pinned_after["items"] if item["ref"] == ref)["body"],
            "Use the real store.\n",
        )
        suffix_json = subprocess.run(
            [*base[:-1], "status", "--json"], text=True, capture_output=True, check=True,
        )
        self.assertTrue(json.loads(suffix_json.stdout)["installed"])
        default_listing = subprocess.run(
            base, text=True, stdin=subprocess.DEVNULL, capture_output=True, check=True,
        )
        self.assertGreater(len(json.loads(default_listing.stdout)), 0)

    def test_native_enablement_does_not_bypass_opt_in(self) -> None:
        hook = next(row for row in self.store.list_items() if row["kind"] == "hook")
        ref = hook["ref"]
        plan = self.store.plan({"operation": "enable", "items": {ref: True}})
        self.store.apply(plan["plan_id"], plan["expected_revision"])
        for host in ("claude", "codex"):
            ordinary = self.store.snapshot(host, selection=[])
            self.assertEqual({}, ordinary["assets"])
            self.assertTrue(any(row.get("ref") == ref and "disabled" in row.get("reason", "")
                                for row in ordinary["unavailable"]))
            opted_in = self.store.snapshot(host, selection=[], native=True)
            self.assertTrue(opted_in["assets"].get("claude_plugins") if host == "claude"
                            else opted_in["assets"].get("codex_hooks"))
        plan = self.store.plan({"operation": "enable", "items": {ref: False}})
        self.store.apply(plan["plan_id"], plan["expected_revision"])
        for host in ("claude", "codex"):
            off = self.store.snapshot(host, selection=["all"], native=True)
            self.assertNotIn(ref, [item["ref"] for item in self.store.snapshot_inventory(off["content_ref"])["items"]])


@unittest.skipUnless(importlib.util.find_spec("textual"), "Textual is required")
class CorpusBundleUiTests(CorpusFixture, unittest.TestCase):
    def test_arrow_preview_apply_and_discard_return_to_visible_controls(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import Tree

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                await pilot.pause()
                tree = app.query_one("#library", Tree)
                node = next(node for state in tree.root.children for package in state.children
                            for node in package.children if node.data.endswith(":rule-003"))
                ref = node.data
                tree.focus()
                tree.move_cursor(node)
                await pilot.pause()
                await pilot.press("space", "right")
                app.query_one("#wiki").scroll_end(animate=False)
                await pilot.pause()
                await pilot.press("down", "enter")
                self.assertEqual("preview", app.mode)
                self.assertEqual("plan-cancel", app.focused.id)
                await pilot.press("enter")
                self.assertEqual("view", app.mode)
                self.assertEqual("enablement-preview", app.focused.id)
                await pilot.press("enter", "right")
                self.assertEqual("apply", app.focused.id)
                await pilot.press("enter")
                self.assertEqual("library", app.focused.id)
                self.assertFalse(self.store.show(ref)["enabled"])
                await app.toggle_enabled(ref)
                app._focus_id("enablement-discard")
                await pilot.pause()
                await pilot.press("enter")
                self.assertEqual("library", app.focused.id)
                self.assertFalse(app.toggle_drafts)
                self.assertFalse(self.store.show(ref)["enabled"])

        asyncio.run(exercise())

    def test_arrows_navigate_controls_library_and_document_without_tab(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import Input, Tree

        before = self.store.status()["revision"]

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                await pilot.pause()
                tree = app.query_one("#library", Tree)
                node = next(node for state in tree.root.children for package in state.children
                            for node in package.children if node.data.endswith(":rule-003"))
                tree.move_cursor(node)
                await pilot.pause()
                search = app.query_one("#search", Input)
                search.focus()
                await pilot.press("down")
                self.assertEqual("create", app.focused.id)
                await pilot.press("right")
                self.assertEqual("edit", app.focused.id)
                await pilot.press("left", "down")
                self.assertIs(tree, app.focused)
                await pilot.press("right")
                self.assertIs(app.query_one("#wiki").document, app.focused)
                await pilot.press("left")
                self.assertIs(tree, app.focused)
                tree.move_cursor(tree.root)
                await pilot.pause()
                await pilot.press("up")
                self.assertEqual("create", app.focused.id)
                await pilot.press("up")
                self.assertIs(search, app.focused)
                await app.select_ref(node.data)
                app._focus_id("restore")
                await pilot.press("right")
                self.assertEqual("reset", app.focused.id)  # Recover is disabled.
                await pilot.press("left")
                self.assertEqual("restore", app.focused.id)

        asyncio.run(exercise())
        self.assertEqual(before, self.store.status()["revision"])

    def test_search_caret_and_select_arrows_keep_native_editing(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import Input, Select

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                search = app.query_one("#search", Input)
                search.value = "abc"
                search.cursor_position = 1
                await pilot.pause()
                await pilot.press("right")
                self.assertIs(search, app.focused)
                self.assertEqual(2, search.cursor_position)
                await pilot.press("left")
                self.assertEqual(1, search.cursor_position)
                search.selection = type(search.selection)(0, len(search.value))
                await pilot.press("right")
                self.assertIs(search, app.focused)
                self.assertEqual(3, search.cursor_position)
                await pilot.press("right")
                select = app.query_one("#view-select", Select)
                self.assertIs(select, app.focused)
                original = select.value
                await pilot.press("down", "down", "up")
                self.assertTrue(select.expanded)
                await pilot.press("escape")
                self.assertFalse(select.expanded)
                self.assertEqual(original, select.value)
                await pilot.press("left")
                self.assertIs(search, app.focused)
                self.assertEqual("abc", search.value)

        asyncio.run(exercise())

    def test_arrow_navigation_reaches_pending_controls_and_stays_in_modals(self) -> None:
        from corpus_ui import CorpusStudio, Confirmation
        from textual.widgets import Input, Tree

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                await pilot.pause()
                ref = next(row["ref"] for row in app.items if row["item_id"] == "rule-003")
                await app.select_ref(ref)
                await app.toggle_enabled(ref)
                search = app.query_one("#search", Input)
                search.focus()
                await pilot.press("down")
                self.assertIs(app.query_one("#library", Tree), app.focused)
                await pilot.press("right")
                viewer = app.query_one("#wiki")
                self.assertIs(viewer.document, app.focused)
                viewer.scroll_end(animate=False)
                await pilot.pause()
                await pilot.press("down")
                self.assertEqual("enablement-preview", app.focused.id)
                await pilot.press("right")
                self.assertEqual("enablement-discard", app.focused.id)
                await pilot.press("up")
                self.assertEqual("library", app.focused.id)
                await app.action_request_quit()
                await pilot.pause()
                self.assertIsInstance(app.screen, Confirmation)
                app._focus_id("confirm-no")
                await pilot.press("right")
                self.assertEqual("confirm-yes", app.focused.id)
                await pilot.press("left", "up")
                self.assertEqual("confirm-no", app.focused.id)
                self.assertIsInstance(app.screen, Confirmation)
                self.assertTrue(self.store.show(ref)["enabled"])

        asyncio.run(exercise())

    def test_editor_arrows_move_text_caret_and_button_focus_separately(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import TextArea

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                await pilot.pause()
                ref = next(row["ref"] for row in app.items if row["item_id"] == "rule-003")
                await app.select_ref(ref)
                app.action_edit()
                await pilot.pause()
                editor = app.query_one("#editor-body", TextArea)
                before = editor.text
                editor.focus()
                await pilot.press("right", "down", "left", "up")
                self.assertIs(editor, app.focused)
                self.assertEqual(before, editor.text)
                app._focus_id("editor-cancel")
                await pilot.press("right")
                self.assertEqual("preview", app.focused.id)
                await pilot.press("up")
                self.assertIs(editor, app.focused)
                self.assertIsNone(app.pending_plan)

        asyncio.run(exercise())

    def test_space_batches_changes_without_moving_cursor_or_touching_pins(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import Tree

        rows = self.store.list_items()
        refs = [next(row["ref"] for row in rows if row["item_id"] == ident) for ident in ("rule-003", "rule-004")]
        before = {host: self.store.snapshot(host) for host in ("claude", "codex")}
        pins = {host: self.store.snapshot_inventory(snap["content_ref"]) for host, snap in before.items()}
        revision = self.store.status()["revision"]

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                tree = app.query_one("#library", Tree)
                await pilot.pause()
                leaves = [leaf for state in tree.root.children for package in state.children for leaf in package.children]
                first = next(leaf for leaf in leaves if leaf.data == refs[0])
                tree.focus()
                tree.move_cursor(first)
                await pilot.pause()
                await pilot.press("space")
                self.assertIs(tree.cursor_node, first)
                self.assertTrue(first.label.plain.startswith("[ ]*"))
                self.assertIn("pending; not applied", app.query_one("#wiki").document.source)
                await pilot.press("down", "space")
                self.assertEqual(refs[1], tree.cursor_node.data)
                self.assertEqual(dict.fromkeys(refs, False), app.toggle_drafts)
                self.assertEqual(revision, self.store.status()["revision"])
                self.assertTrue(all(self.store.show(ref)["enabled"] for ref in refs))
                await pilot.click("#enablement-preview")
                self.assertEqual("preview", app.mode)
                self.assertEqual(dict.fromkeys(refs, False), app.pending_plan["details"]["items"])
                await pilot.click("#plan-cancel")
                self.assertEqual(2, len(app.toggle_drafts))
                await pilot.click("#enablement-preview")
                await pilot.click("#apply")
                await pilot.pause()
                self.assertEqual({}, app.toggle_drafts)
                self.assertTrue(all(not self.store.show(ref)["enabled"] for ref in refs))

        asyncio.run(exercise())
        for host, snapshot in before.items():
            after = self.store.snapshot(host)
            after_items = self.store.snapshot_inventory(after["content_ref"])["items"]
            self.assertEqual([item["ref"] for item in pins[host]["items"] if item["ref"] not in refs],
                             [item["ref"] for item in after_items])
            self.assertEqual(pins[host], self.store.snapshot_inventory(snapshot["content_ref"]))
        for ref in refs:
            self.assertEqual("active", self.store.show(ref)["state"])
            self.assertEqual(next(row["body"] for row in rows if row["ref"] == ref), self.store.show(ref)["item"]["body"])

    def test_space_is_text_in_inputs_and_keeps_group_expansion(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import Input, TextArea, Tree

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                search = app.query_one("#search", Input)
                search.focus()
                await pilot.press("space")
                self.assertEqual(" ", search.value)
                self.assertEqual({}, app.toggle_drafts)
                search.value = ""
                await pilot.pause()
                tree = app.query_one("#library", Tree)
                tree.focus()
                tree.move_cursor(tree.root)
                await pilot.pause()
                expanded = tree.root.is_expanded
                await pilot.press("space")
                self.assertNotEqual(expanded, tree.root.is_expanded)
                self.assertEqual({}, app.toggle_drafts)
                tree.root.expand_all()
                await pilot.pause()
                ref = next(row["ref"] for row in app.items if row["item_id"] == "rule-003")
                await app.select_ref(ref)
                app.action_edit()
                await pilot.pause()
                editor = app.query_one("#editor-body", TextArea)
                editor.focus()
                before = editor.text
                await pilot.press("space")
                self.assertEqual(len(before) + 1, len(editor.text))
                self.assertEqual({}, app.toggle_drafts)
                await app.toggle_enabled(ref)
                self.assertEqual({}, app.toggle_drafts)

        asyncio.run(exercise())

    def test_toggle_staleness_discard_deleted_items_and_quit_confirmation(self) -> None:
        from corpus_ui import CorpusStudio, Confirmation

        def change(ref, **patch):
            plan = self.store.plan({"operation": "update", "ref": ref, "patch": patch,
                                   "item_digest": self.store.show(ref)["digest"]})
            self.store.apply(plan["plan_id"], plan["expected_revision"])

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                await pilot.pause()
                ref = next(row["ref"] for row in app.items if row["item_id"] == "rule-003")
                await app.select_ref(ref)
                await app.toggle_enabled(ref)
                app.action_edit()
                self.assertEqual("view", app.mode)
                change(ref, title="Concurrent change")
                app._preview_toggles()
                self.assertIsNone(app.pending_plan)
                self.assertTrue(app.toggle_drafts)
                self.assertTrue(self.store.show(ref)["enabled"])
                await app._discard_toggles()
                await pilot.pause()
                self.assertEqual({}, app.toggle_drafts)
                await app.select_ref(ref)
                await app.toggle_enabled(ref)
                app._preview_toggles()
                self.assertEqual("preview", app.mode)
                change(ref, title="Changed after preview")
                await app._apply_pending()
                self.assertEqual("preview", app.mode)
                self.assertTrue(self.store.show(ref)["enabled"])
                await app.action_cancel()
                await app.action_request_quit()
                await pilot.pause()
                self.assertIsInstance(app.screen, Confirmation)
                await pilot.click("#confirm-no")
                self.assertTrue(app.toggle_drafts)
                await app._discard_toggles()
                plan = self.store.plan({"operation": "remove", "ref": ref})
                self.store.apply(plan["plan_id"], plan["expected_revision"])
                await app.refresh_library()
                await app.toggle_enabled(ref)
                self.assertEqual({}, app.toggle_drafts)
                self.assertEqual("removed", self.store.show(ref)["state"])

        asyncio.run(exercise())

    def test_disabled_guide_warning_does_not_toggle_its_trigger(self) -> None:
        from corpus_ui import CorpusStudio
        rows = self.store.list_items()
        trigger = next(row["ref"] for row in rows if row["item_id"] == "rule-039")
        guide = next(row["ref"] for row in rows if row["item_id"] == "guide-concept-economy")
        plan = self.store.plan({"operation": "enable", "items": {trigger: True, guide: True}})
        self.store.apply(plan["plan_id"], plan["expected_revision"])

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                await pilot.pause()
                await app.toggle_enabled(guide)
                await app.select_ref(trigger)
                self.assertIn("OFF — linked guide disabled", app.query_one("#wiki").document.source)
                self.assertEqual({guide: False}, app.toggle_drafts)
                self.assertTrue(self.store.show(trigger)["enabled"])
                await app.toggle_enabled(guide)
                self.assertEqual({}, app.toggle_drafts)

        asyncio.run(exercise())

    def test_arrow_keys_update_document_without_enter_and_groups_clear_actions(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import Button, Tree

        rows = self.store.list_items()
        revision = self.store.status()["revision"]

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                tree = app.query_one("#library", Tree)
                await pilot.pause()
                package = tree.root.children[0].children[0]
                first, second = package.children[:2]
                tree.focus()
                tree.move_cursor(first)
                await pilot.pause()
                self.assertEqual(first.data, app.current_ref)
                await pilot.press("down")
                self.assertEqual(second.data, tree.cursor_node.data)
                self.assertEqual(second.data, app.current_ref)
                self.assertIn(self.store.show(second.data)["item"]["body"], app.query_one("#wiki").document.source)
                await pilot.press("up")
                self.assertEqual(first.data, app.current_ref)
                # Parent groups must not retain a destructive action on the old item.
                await pilot.press("up")
                self.assertIs(tree.cursor_node, package)
                self.assertIsNone(app.current_ref)
                self.assertIn("# Corpus group", app.query_one("#wiki").document.source)
                for selector in ("#edit", "#remove", "#restore", "#recover"):
                    self.assertTrue(app.query_one(selector, Button).disabled)
                await pilot.press("down", "down", "down", "up")
                self.assertEqual(tree.cursor_node.data, app.current_ref)
                self.assertIn(self.store.show(app.current_ref)["item"]["body"], app.query_one("#wiki").document.source)

        asyncio.run(exercise())
        self.assertEqual(rows, self.store.list_items())
        self.assertEqual(revision, self.store.status()["revision"])

    def test_highlights_cannot_retarget_editor_or_prepared_plan(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import TextArea, Tree

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                tree = app.query_one("#library", Tree)
                await pilot.pause()
                package = tree.root.children[0].children[0]
                first, second = package.children[:2]
                tree.move_cursor(first)
                await pilot.pause()
                app.action_edit()
                await pilot.pause()
                editor = app.query_one("#editor-body", TextArea)
                draft = editor.text + "\nPreserve this draft.\n"
                editor.text = draft
                tree.move_cursor(second)
                await pilot.pause()
                self.assertEqual(first.data, app.current_ref)
                self.assertEqual(draft, editor.text)
                payload, summary = app._editor_payload()
                app._stage_plan(payload, summary)
                pending = app.pending_plan
                tree.move_cursor(package)
                await pilot.pause()
                self.assertEqual(first.data, app.current_ref)
                self.assertIs(pending, app.pending_plan)
                self.assertEqual("preview", app.mode)

        asyncio.run(exercise())

    def test_guide_pointers_use_literal_same_package_members_without_guessing(self) -> None:
        from corpus_ui import CorpusStudio, guide_pointers, library_label

        rule = {"kind": "rule", "package_id": "@test/one", "title": "[literal] rule",
                "surface": "always", "body": "Read `guides/a.md` and `guides/b.md`; guides/a.md."}
        guide = {"kind": "guide", "package_id": "@test/one", "ref": "@test/one:a",
                 "members": {"guides/a.md": "body"}, "surface": "relevant", "state": "removed"}
        other = dict(guide, package_id="@test/two", ref="@test/two:a")
        rows = [guide, other]
        before = json.dumps(rows, sort_keys=True)
        pointers = guide_pointers(rule, rows)
        self.assertEqual([p["path"] for p in pointers], ["guides/a.md", "guides/b.md"])
        self.assertEqual(pointers[0]["target"]["ref"], guide["ref"])
        self.assertEqual(pointers[0]["target"]["state"], "removed")
        self.assertIsNone(pointers[1]["target"])
        self.assertIsNone(guide_pointers(rule, [other])[0]["target"])
        duplicate = dict(guide, ref="@test/one:duplicate")
        ambiguous = guide_pointers(rule, [guide, duplicate])[0]
        self.assertIsNone(ambiguous["target"])
        self.assertIn("Ambiguous", ambiguous["problem"])
        self.assertEqual([], guide_pointers(dict(rule, body="Think about concept economy."), rows))
        self.assertEqual([], guide_pointers(dict(rule, body="guides/../a.md"), rows))
        self.assertEqual([], guide_pointers(dict(rule, kind="guide"), rows))
        label = library_label(rule, rows)
        self.assertTrue(label.plain.startswith("[x] → GUIDE a, b"))
        self.assertIn("[literal] rule", label.plain)
        self.assertEqual(before, json.dumps(rows, sort_keys=True))
        app = CorpusStudio(self.store)
        app.items = [other]
        rendered = app._render_item(rule, {"item": rule}, "effective")
        self.assertIn("Not found in this package", rendered)
        self.assertNotIn("corpus://", rendered)
        app.items = [guide, duplicate]
        rendered = app._render_item(rule, {"item": rule}, "effective")
        self.assertIn("Ambiguous guide reference", rendered)
        self.assertNotIn("corpus://", rendered)

    def test_guide_pointer_navigation_preserves_authoring_and_host_snapshots(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import Markdown, Tree

        rows = self.store.list_items()
        rule = next(row for row in rows if row["item_id"] == "rule-039")
        guide = next(row for row in rows if row["item_id"] == "guide-concept-economy")
        before = {host: self.store.snapshot(host) for host in ("claude", "codex")}
        revision = self.store.status()["revision"]

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(120, 42)) as pilot:
                await app.select_ref(rule["ref"])
                await pilot.pause()
                tree = app.query_one("#library", Tree)
                leaves = [leaf for state in tree.root.children for package in state.children
                          for leaf in package.children]
                label = next(leaf.label.plain for leaf in leaves if leaf.data == rule["ref"])
                self.assertIn("→ GUIDE concept-economy", label)
                document = app.query_one("#wiki").document
                self.assertIn("## Guide pointer", document.source)
                self.assertIn("## Rule\n\n", document.source)
                self.assertIn(f"[guides/concept-economy.md](corpus://{guide['ref']})", document.source)
                self.assertIn("**relevant** · available", document.source)
                self.assertIn("always · rule", document.source)
                self.assertIn(rule["body"], document.source)
                document.post_message(Markdown.LinkClicked(document, f"corpus://{guide['ref']}"))
                await pilot.pause()
                self.assertEqual(guide["ref"], app.current_ref)
                self.assertIn(guide["body"], document.source)
                # Normal rules remain normal, with no inferred guide classification.
                ordinary = next(row for row in rows if row["item_id"] == "rule-040")
                await app.select_ref(ordinary["ref"])
                self.assertNotIn("## Guide pointer", document.source)

        asyncio.run(exercise())
        self.assertEqual(rows, self.store.list_items())
        self.assertEqual(revision, self.store.status()["revision"])
        for host, snapshot in before.items():
            self.assertEqual(snapshot, self.store.snapshot(host))

    def test_guide_pointer_display_tracks_edits_removals_and_surface_changes(self) -> None:
        from corpus_ui import CorpusStudio, guide_pointers
        rows = self.store.list_items()
        rule = next(row for row in rows if row["item_id"] == "rule-039")
        guide = next(row for row in rows if row["item_id"] == "guide-concept-economy")
        app = CorpusStudio(self.store)
        for operation in (
            {"operation": "update", "ref": guide["ref"], "patch": {"surface": "requested"}},
            {"operation": "remove", "ref": guide["ref"]},
            {"operation": "update", "ref": rule["ref"], "patch": {"body": "A plain rule."}},
        ):
            current = next(row for row in self.store.list_items() if row["ref"] == operation["ref"])
            plan = self.store.plan(dict(operation, item_digest=current["digest"]))
            self.store.apply(plan["plan_id"], plan["expected_revision"])
            app.items = self.store.list_items()
            result = self.store.show(rule["ref"])
            rendered = app._render_item(rule, result, "effective")
            if operation["ref"] == rule["ref"]:
                self.assertNotIn("## Guide pointer", rendered)
                self.assertEqual([], guide_pointers(result["item"], app.items))
            elif operation["operation"] == "remove":
                self.assertIn("removed", rendered)
            else:
                self.assertIn("**requested** · available", rendered)
                self.assertNotIn("**relevant**", rendered)

    def test_primary_hook_renders_as_code_instead_of_comment_headings(self) -> None:
        from corpus_ui import CorpusStudio

        hook = next(row for row in self.store.list_items() if row["kind"] == "hook")
        original = self.store.show(hook["ref"])["item"]["body"]

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(100, 30)) as pilot:
                await app.select_ref(hook["ref"])
                await pilot.pause()
                document = app.query_one("#wiki").document
                self.assertEqual(1, len(document.query("MarkdownH1")))
                self.assertEqual(1, len(document.query("MarkdownFence")))
                self.assertIn(original, document.source)
                self.assertIn("```python\n#!/usr/bin/env python3\n", document.source)
                self.assertEqual(original, self.store.show(hook["ref"])["item"]["body"])

        asyncio.run(exercise())

    def test_code_fences_cannot_be_closed_by_source_and_markdown_stays_prose(self) -> None:
        from corpus_ui import CorpusStudio, render_member_body
        body = '# comment\ntext = """\n```\n# not a heading\n````\n"""\n'
        self.assertEqual(body, render_member_body(body, "guide.MD"))
        for member in ("hook.py", "config.toml", "data.json", "notes.txt"):
            rendered = render_member_body(body, member)
            self.assertTrue(rendered.startswith("`````"))
            self.assertTrue(rendered.endswith("`````"))
            self.assertIn(body, rendered)

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(100, 30)) as pilot:
                item = {"title": "source.py", "ref": "@local/personal:source", "kind": "hook",
                        "surface": "event", "primary_member": "source.py", "body": body}
                document = app.query_one("#wiki").document
                await document.update(app._render_item(item, {"item": item}, "effective"))
                await pilot.pause()
                self.assertEqual(1, len(document.query("MarkdownH1")))
                self.assertEqual(1, len(document.query("MarkdownFence")))

        asyncio.run(exercise())

    def test_read_navigation_cannot_retarget_an_open_companion_draft(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import Select, TextArea

        item = next(row for row in self.store.list_items() if row["item_id"] == "skill-slide-writing")
        sibling = next(row for row in self.store.list_items() if row["ref"] != item["ref"])
        companion = "guides/slide-writing/RUNBOOK.md"

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(100, 30)) as pilot:
                await app.select_ref(item["ref"])
                await pilot.click("#edit")
                self.assertTrue(app.query_one("#view-select", Select).disabled)
                self.assertTrue(app.query_one("#library").disabled)
                app.query_one("#member-select", Select).value = companion
                await pilot.pause()
                draft = app.query_one("#editor-body", TextArea).text + "\nKeep this companion draft.\n"
                app.query_one("#editor-body", TextArea).text = draft
                app.query_one("#view-select", Select).value = "installed"
                await pilot.pause()
                self.assertTrue(app.editor_dirty())
                app.query_one("#view-select", Select).value = "effective"
                await pilot.pause()
                await app.select_ref(sibling["ref"])
                self.assertEqual(app.current_ref, item["ref"])
                self.assertEqual(app.current_member, companion)
                self.assertEqual(app.query_one("#editor-body", TextArea).text, draft)
                payload, _summary = app._editor_payload()
                self.assertEqual(payload["patch"]["body"], item["body"])
                self.assertEqual(payload["patch"]["members"][companion], draft)
                await pilot.click("#preview")
                await pilot.pause()
                await pilot.click("#apply")
                await pilot.pause()
                saved = self.store.show(item["ref"])["item"]
                self.assertEqual(saved["body"], item["body"])
                self.assertEqual(saved["members"][companion], draft)

        asyncio.run(exercise())

    def test_criterion_primary_and_companion_drafts_apply_together(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import Select, TextArea

        item = next(row for row in self.store.list_items() if row["item_id"] == "skill-slide-writing")
        primary = item["primary_member"]
        companion = "guides/slide-writing/RUNBOOK.md"
        self.assertEqual(item["kind"], "guide")

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(80, 24)) as pilot:
                await app.select_ref(item["ref"])
                await pilot.pause()
                selector = app.query_one("#member-select", Select)
                self.assertEqual(selector.value, primary)
                self.assertGreater(selector.region.height, 0)
                await pilot.click("#edit")
                await pilot.pause()
                editor = app.query_one("#editor-body", TextArea)
                self.assertEqual(editor.text, item["body"])
                self.assertGreater(editor.region.height, 0)
                self.assertLessEqual(editor.region.bottom, app.screen.region.bottom)
                selector.value = companion
                await pilot.pause()
                self.assertEqual(editor.text, item["members"][companion])
                self.assertFalse(app.editor_dirty())
                revised_companion = editor.text + "\nA personal execution note.\n"
                editor.text = revised_companion
                selector.value = primary
                await pilot.pause()
                self.assertEqual(editor.text, item["body"])
                revised_primary = editor.text.replace("central judgment", "central decision", 1)
                self.assertNotEqual(revised_primary, item["body"])
                editor.text = revised_primary
                selector.value = companion
                await pilot.pause()
                self.assertEqual(editor.text, revised_companion)
                payload, summary = app._editor_payload()
                self.assertEqual(payload["patch"]["body"], revised_primary)
                self.assertEqual(payload["patch"]["members"][companion], revised_companion)
                self.assertIn(companion, summary)
                self.assertIn(primary, summary)
                await pilot.click("#preview")
                await pilot.pause()
                self.assertEqual(app.mode, "preview")
                self.assertTrue(selector.disabled)
                await pilot.click("#apply")
                await pilot.pause()
                saved = self.store.show(item["ref"])["item"]
                self.assertEqual(saved["body"], revised_primary)
                self.assertEqual(saved["members"][companion], revised_companion)
                self.assertEqual(saved["primary_member"], primary)
                self.assertEqual(selector.value, primary)
                await pilot.click("#restore")
                await pilot.pause()
                await pilot.click("#apply")
                await pilot.pause()
                restored = self.store.show(item["ref"])["item"]
                self.assertEqual(restored["body"], item["body"])
                self.assertEqual(restored["members"], item["members"])

        asyncio.run(exercise())

    def test_companion_cancel_preserves_saved_bundle(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import Select, TextArea

        item = next(row for row in self.store.list_items() if row["item_id"] == "skill-slide-writing")
        companion = "guides/slide-writing/RUNBOOK.md"

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(80, 24)) as pilot:
                await app.select_ref(item["ref"])
                selector = app.query_one("#member-select", Select)
                selector.value = companion
                await pilot.pause()
                self.assertEqual(app.current_member, companion)
                self.assertIn(item["members"][companion], app.query_one("#wiki").document.source)
                await pilot.click("#edit")
                await pilot.pause()
                self.assertEqual(app.query_one("#editor-body", TextArea).text, item["members"][companion])
                app.query_one("#editor-body", TextArea).text = "Discard this companion edit.\n"
                await pilot.click("#editor-cancel")
                await pilot.pause()
                await pilot.click("#confirm-no")
                await pilot.pause()
                self.assertEqual(app.mode, "editor")
                await pilot.click("#editor-cancel")
                await pilot.pause()
                await pilot.click("#confirm-yes")
                await pilot.pause()
                self.assertEqual(app.mode, "view")
                self.assertEqual(selector.value, item["primary_member"])
                self.assertEqual(self.store.show(item["ref"])["item"]["members"], item["members"])

        asyncio.run(exercise())


@unittest.skipUnless(importlib.util.find_spec("textual"), "Textual runtime is not installed")
class CorpusTextualCase(CorpusFixture, unittest.TestCase):
    def test_legacy_content_editor_requires_an_explicit_primary_member(self) -> None:
        from corpus_ui import CorpusStudio
        from textual.widgets import Select

        legacy = {
            "ref": "@local/personal:legacy", "digest": "0" * 64,
            "title": "Legacy", "body": "Stale body\n",
            "surface": "requested", "tier": "domain", "domains": ["personal"], "kind": "guide",
            "members": {"guides/one.md": "One\n", "guides/two.md": "Two\n"},
            "content_conflict": {"reason": "legacy body has no match",
                                 "members": ["guides/one.md", "guides/two.md"]},
        }

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(80, 24)) as pilot:
                app._open_editor(legacy)
                await pilot.pause()
                primary = app.query_one("#editor-primary-member", Select)
                self.assertGreater(primary.region.width, 0)
                self.assertEqual(primary.value, Select.NULL)
                with self.assertRaisesRegex(ValueError, "Choose the primary member"):
                    app._editor_payload()
                primary.value = "guides/two.md"
                payload, _summary = app._editor_payload()
                self.assertEqual("guides/two.md", payload["patch"]["primary_member"])
                self.assertEqual("Stale body\n", payload["patch"]["body"])

        asyncio.run(exercise())

    def test_action_regions_fit_80x24_and_100x30(self) -> None:
        from corpus_ui import Confirmation, CorpusStudio
        from textual.widgets import Select

        async def check(size: tuple[int, int]) -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=size) as pilot:
                screen = app.screen.region
                selectors = (
                    "#search", "#view-select", "#create", "#edit", "#remove",
                    "#restore", "#recover", "#reset", "#library", "#wiki",
                )
                for selector in selectors:
                    region = app.query_one(selector).region
                    self.assertGreater(region.width, 0, selector)
                    self.assertGreater(region.height, 0, selector)
                    self.assertGreaterEqual(region.x, screen.x, selector)
                    self.assertGreaterEqual(region.y, screen.y, selector)
                    self.assertLessEqual(region.right, screen.right, selector)
                    self.assertLessEqual(region.bottom, screen.bottom, selector)

                action_regions = [
                    app.query_one(selector).region for selector in
                    ("#create", "#edit", "#remove", "#restore", "#recover", "#reset")
                ]
                for left, right in zip(action_regions, action_regions[1:]):
                    self.assertLessEqual(left.right, right.x)

                # Mouse reaches Create; the compact editor retains a visible body,
                # surface selector, and Preview/Cancel controls at both sizes.
                await pilot.click("#create")
                await pilot.pause()
                for selector in ("#editor-title", "#editor-surface", "#editor-body", "#editor-cancel", "#preview"):
                    region = app.query_one(selector).region
                    self.assertGreater(region.width, 0, selector)
                    self.assertGreater(region.height, 0, selector)
                    self.assertLessEqual(region.right, screen.right, selector)
                    self.assertLessEqual(region.bottom, screen.bottom, selector)
                await pilot.press("f2")
                self.assertEqual(app.focused.id, "editor-surface")
                self.assertIsInstance(app.focused, Select)
                await pilot.click("#editor-cancel")
                await pilot.pause()
                self.assertEqual(app.mode, "view")

        for size in ((80, 24), (100, 30)):
            asyncio.run(check(size))

    def test_narrow_mounted_widgets_create_edit_remove_restore_recover_learning_and_reset(self) -> None:
        from corpus_ui import Confirmation, CorpusStudio
        from textual.widgets import Input, MarkdownViewer, Select, TextArea, Tree

        baseline_ref = next(
            row["ref"] for row in self.store.list_items()
            if row.get("kind") == "rule" and row.get("baseline_ref")
        )
        learning_id = "12345678-1234-1234-1234-123456789abc"
        self.store.capture_learning("codex", {
            "schema_version": 1,
            "learning_id": learning_id,
            "lesson": "Keep the observed learning source immutable.",
            "domain": "ui-learning",
            "created": "2026-09-07T00:00:00Z",
            "supporting_sessions": ["codex:ui-test"],
        })
        learning_ref = f"@local/learnings-codex:{learning_id}"

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(80, 24)) as pilot:
                self.assertIsInstance(app.query_one("#library"), Tree)
                viewer = app.query_one("#wiki")
                self.assertIsInstance(viewer, MarkdownViewer)
                self.assertFalse(viewer._open_links)
                self.assertIsInstance(app.query_one("#editor-body"), TextArea)
                self.assertIsInstance(app.query_one("#editor-surface"), Select)

                app.query_one("#library", Tree).focus()
                await pilot.press("v")
                await pilot.pause()
                self.assertEqual(app.query_one("#view-select", Select).value, "installed")
                app.query_one("#view-select", Select).value = "effective"
                await pilot.pause()

                await pilot.click("#create")
                app.query_one("#editor-title", Input).value = "Mounted item"
                app.query_one("#editor-body", TextArea).text = "First body.\n"
                app.query_one("#editor-surface", Select).value = "requested"
                await pilot.pause()

                # Dirty cancellation is explicit and preserves the editor on No.
                await pilot.click("#editor-cancel")
                await pilot.pause()
                self.assertIsInstance(app.screen, Confirmation)
                await pilot.click("#confirm-no")
                await pilot.pause()
                self.assertEqual(app.mode, "editor")

                await pilot.click("#preview")
                await pilot.pause()
                self.assertEqual(app.mode, "preview")
                self.assertFalse(any(row.get("title") == "Mounted item" for row in self.store.list_items()))
                await pilot.click("#apply")
                await pilot.pause()
                created = next(row for row in self.store.list_items() if row.get("title") == "Mounted item")

                await app.select_ref(created["ref"])
                app.query_one("#library", Tree).focus()
                await pilot.press("e")
                app.query_one("#editor-body", TextArea).text = "Edited body.\n"
                await pilot.press("f2")
                self.assertEqual(app.focused.id, "editor-surface")
                app.query_one("#editor-surface", Select).value = "relevant"
                await pilot.click("#preview")
                await pilot.pause()
                await pilot.click("#apply")
                await pilot.pause()
                changed = self.store.show(created["ref"])["item"]
                self.assertEqual(changed["body"], "Edited body.\n")
                self.assertEqual(changed["surface"], "relevant")
                self.assertEqual(changed["members"]["content.md"], "Edited body.\n")

                await app.select_ref(created["ref"])
                await pilot.click("#remove")
                await pilot.pause()
                await pilot.click("#apply")
                await pilot.pause()
                personal_removed = next(
                    row for row in self.store.list_items() if row["ref"] == created["ref"]
                )
                self.assertEqual(personal_removed["state"], "removed")
                await app.select_ref(created["ref"])
                await pilot.click("#recover")
                await pilot.pause()
                await pilot.click("#apply")
                await pilot.pause()
                personal_recovered = next(
                    row for row in self.store.list_items() if row["ref"] == created["ref"]
                )
                self.assertEqual(personal_recovered["state"], "active")

                # A host-qualified immutable learning is a recoverable personal
                # authority too; Recover must not be limited to @local/personal.
                await app.select_ref(learning_ref)
                self.assertFalse(app.query_one("#remove").disabled)
                await pilot.click("#remove")
                await pilot.pause()
                await pilot.click("#apply")
                await pilot.pause()
                learning_removed = next(
                    row for row in self.store.list_items() if row["ref"] == learning_ref
                )
                self.assertEqual(learning_removed["state"], "removed")
                self.assertTrue(learning_removed["learning_source"])
                await app.select_ref(learning_ref)
                self.assertFalse(app.query_one("#recover").disabled)
                app.query_one("#library", Tree).focus()
                await pilot.press("shift+r")
                await pilot.pause()
                self.assertEqual(app.mode, "preview")
                await pilot.click("#apply")
                await pilot.pause()
                learning_recovered = next(
                    row for row in self.store.list_items() if row["ref"] == learning_ref
                )
                self.assertEqual(learning_recovered["state"], "active")

                # Remove and restore traverse a selected installed item, not a fake row.
                await app.select_ref(baseline_ref)
                await pilot.click("#remove")
                await pilot.pause()
                await pilot.click("#apply")
                await pilot.pause()
                removed = next(row for row in self.store.list_items() if row["ref"] == baseline_ref)
                self.assertEqual(removed["state"], "removed")
                await app.select_ref(baseline_ref)
                app.query_one("#library", Tree).focus()
                await pilot.press("r")
                await pilot.pause()
                await pilot.click("#apply")
                await pilot.pause()
                restored = next(row for row in self.store.list_items() if row["ref"] == baseline_ref)
                self.assertEqual(restored["state"], "active")

                app.query_one("#search", Input).value = "Mounted item"
                await pilot.pause()
                def item_refs(node):
                    refs = [node.data] if isinstance(node.data, str) else []
                    for child in node.children:
                        refs.extend(item_refs(child))
                    return refs

                self.assertEqual(item_refs(app.query_one("#library", Tree).root), [created["ref"]])

                await pilot.click("#reset")
                await pilot.pause()
                await pilot.click("#apply")
                await pilot.pause()
                self.assertFalse(any(row.get("title") == "Mounted item" for row in self.store.list_items()))

        asyncio.run(exercise())

    def test_narrow_hook_binding_edit_preview_apply_and_restore(self) -> None:
        from corpus_catalog import HOOK_EVENTS
        from corpus_ui import Confirmation, CorpusStudio
        from textual.widgets import Input, Select

        hook = next(row for row in self.store.list_items() if row.get("kind") == "hook")
        original = self.store.show(hook["ref"])["item"]
        original_body = original["body"]
        original_binding = dict(original["hook"])
        replacement_event = "Interrupt"  # Codex-only events must survive the common editor.
        self.assertIn(replacement_event, HOOK_EVENTS)

        async def exercise() -> None:
            app = CorpusStudio(self.store)
            async with app.run_test(size=(80, 24)) as pilot:
                await app.select_ref(hook["ref"])
                await pilot.click("#edit")
                await pilot.pause()
                self.assertEqual("editor", app.mode)
                for selector in ("#hook-binding-row", "#editor-hook-event", "#editor-hook-matcher"):
                    region = app.query_one(selector).region
                    self.assertGreater(region.width, 0, selector)
                    self.assertGreater(region.height, 0, selector)
                    self.assertLessEqual(region.right, app.screen.region.right, selector)
                    self.assertLessEqual(region.bottom, app.screen.region.bottom, selector)
                app.query_one("#editor-hook-event", Select).value = replacement_event
                app.query_one("#editor-hook-matcher", Input).value = "Bash|Read"
                self.assertTrue(app.editor_dirty())
                await pilot.click("#editor-cancel")
                await pilot.pause()
                self.assertIsInstance(app.screen, Confirmation)
                await pilot.click("#confirm-no")
                await pilot.pause()
                self.assertEqual("editor", app.mode)
                await pilot.click("#preview")
                await pilot.pause()
                self.assertEqual(app.mode, "preview")
                await pilot.click("#apply")
                await pilot.pause()
                changed = self.store.show(hook["ref"])["item"]
                self.assertEqual(original_body, changed["body"])
                self.assertEqual({"event": replacement_event, "matcher": "Bash|Read"}, changed["hook"])
                await app.select_ref(hook["ref"])
                await pilot.click("#restore")
                await pilot.pause()
                await pilot.click("#apply")
                await pilot.pause()
                restored = self.store.show(hook["ref"])["item"]
                self.assertEqual(original_body, restored["body"])
                self.assertEqual(original_binding, restored["hook"])

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
