"""Headless guided-installer interactions over an isolated controller."""
from __future__ import annotations

import asyncio
import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

try:
    import textual
except ModuleNotFoundError:
    from corpus_ui_runtime import activate_ui_runtime
    activate_ui_runtime(Path(__file__).resolve().parents[1])

from textual.widgets import Button, Checkbox, Collapsible, Input, Select, SelectionList, Static
from corpus_setup_ui import SetupApp

from corpus_setup import SetupError


class Controller:
    def __init__(self, root: Path, *, saved=False):
        self.root = root
        self.saved = saved
        self.dependencies = [
            {"id": "python", "title": "Python", "status": "available", "version": "3.14.5",
             "role": "runtime", "purpose": "Runs private corpus storage.", "install_argv": None,
             "install_scope": "", "manual_reason": ""},
            {"id": "schema", "title": "Learning validator", "status": "missing", "version": "",
             "role": "learning capture", "purpose": "Validates selected learning submissions.",
             "install_argv": ["fixture-package-manager", "install", "schema"],
             "install_scope": str(root / "managed"), "manual_reason": ""},
            {"id": "personal", "title": "Personal integration", "status": "not assessed", "version": "",
             "role": "optional", "purpose": "Configured separately when needed.", "install_argv": None,
             "install_scope": "", "manual_reason": "No automatic installation recipe."},
        ]
        self.choices = [
            {"target": "@fixture/core/coding", "label": "Coding and verification"},
            {"target": "@fixture/core/office", "label": "Office documents"},
        ]
        self.effects = []
        self.previews = []
        self.discoveries = []
        self.apply_calls = []
        self.preview_error = None
        self.apply_error = None
        self.block_apply = False
        self.started = threading.Event()
        self.finish_step = threading.Event()
        self.default_gate = None
        self.default_calls = 0
        self.default_error = None

    def default_plan(self):
        self.default_calls += 1
        if self.default_error is not None:
            raise self.default_error
        if self.default_gate is not None:
            self.default_gate.wait(5)
        return {"selection_mode": None if self.saved else "none", "targets": None if self.saved else [],
                "dependencies": [], "app_bridge": False, "import_paths": [], "project_roots": []}

    def discover(self, roots):
        self.discoveries.append(list(roots))
        sources = [{"path": str(self.root / "global/AGENTS.md"), "scope": {"kind": "global"}}]
        sources.extend({"path": str(Path(root) / "AGENTS.md"), "scope": {"kind": "project", "root": root}}
                       for root in roots)
        return {"sources": sources, "omitted": []}

    def preview(self, plan):
        self.previews.append(copy.deepcopy(plan))
        if self.preview_error is not None:
            raise self.preview_error
        return {"plan": copy.deepcopy(plan), "installation": {"dry_run": True}, "extras": None,
                "review_id": "review-fixture", "source_versions": []}

    def apply(self, plan, preview=None, *, progress=None, should_cancel=None):
        self.apply_calls.append((copy.deepcopy(plan), copy.deepcopy(preview)))
        if self.apply_error is not None:
            raise self.apply_error
        progress({"stage": "dependency" if self.block_apply else "install", "message": "Running the selected operation", "dependency": "schema"})
        self.effects.append("dependency" if self.block_apply else "install")
        self.started.set()
        if self.block_apply:
            self.finish_step.wait(5)
            if should_cancel():
                return {"applied": False, "cancelled": True, "cancelled_after_start": True,
                        "dependency_results": [{"id": "schema", "returncode": 0}], "plan": plan}
        progress({"stage": "complete", "message": "Setup complete", "stdout": "Operation complete\n", "stderr": ""})
        return {"applied": True, "plan": plan, "dependency_results": [], "installation": {"stored": True}, "extras": None}


class SetupUiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="setup-ui-test-")
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        global_file = self.root / "global/AGENTS.md"
        global_file.parent.mkdir()
        global_file.write_text("User global instructions\n")
        (self.project / "AGENTS.md").write_text("User project instructions\n")
        self.originals = {path: path.read_bytes() for path in (global_file, self.project / "AGENTS.md")}
        self.installer = SimpleNamespace(repo=self.root, env={})

    def tearDown(self):
        self.temp.cleanup()

    async def wait_for(self, app, pilot, predicate):
        for _ in range(180):
            await pilot.pause(0.01)
            if predicate():
                return
        self.fail("UI did not reach the expected state")

    async def ready(self, app, pilot):
        if app.step == -1 and not app.busy:
            await self.click_ready(app, pilot, "#language-continue")
        await self.wait_for(app, pilot, lambda: app.ready and not app.busy)

    async def click_ready(self, app, pilot, selector):
        button = app.query_one(selector, Button)
        await self.wait_for(app, pilot, lambda: not app.busy and not button.disabled and button.display
                            and not button.has_class("-active"))
        self.assertTrue(await pilot.click(selector))

    async def next(self, app, pilot, step):
        await self.click_ready(app, pilot, "#next")
        await self.wait_for(app, pilot, lambda: app.step == step and not app.busy)

    async def review(self, app, pilot):
        await self.ready(app, pilot)
        for stage in (1, 2, 3):
            await self.next(app, pilot, stage)

    def assert_originals(self):
        self.assertEqual(self.originals, {path: path.read_bytes() for path in self.originals})

    async def test_no_corpus_capture_and_dependency_choices_share_one_apply(self):
        controller = Controller(self.root)
        app = SetupApp(self.installer, controller=controller)
        async with app.run_test(size=(80, 24)) as pilot:
            await self.ready(app, pilot)
            self.assertEqual("none", app.query_one("#corpus-mode", Select).value)
            app.query_one("#app-bridge", Checkbox).value = True
            await self.next(app, pilot, 1)
            app.query_one("#project-path", Input).value = str(self.project)
            await self.click_ready(app, pilot, "#add-project")
            await self.wait_for(app, pilot, lambda: not app.busy and len(app.sources) == 2)
            sources = app.query_one("#source-choices", SelectionList)
            sources.highlighted = 1
            sources.focus()
            await pilot.press("space")
            await self.next(app, pilot, 2)
            dependencies = app.query_one("#dependency-choices", SelectionList)
            self.assertTrue(dependencies.get_option_at_index(0).disabled)
            self.assertTrue(dependencies.get_option_at_index(2).disabled)
            dependencies.highlighted = 1
            dependencies.focus()
            await pilot.press("space")
            await self.next(app, pilot, 3)
            self.assertEqual([], controller.effects)
            self.assertEqual("none", controller.previews[-1]["selection_mode"])
            self.assertEqual([str(self.project / "AGENTS.md")], controller.previews[-1]["import_paths"])
            self.assertEqual(["schema"], controller.previews[-1]["dependencies"])
            self.assertTrue(controller.previews[-1]["app_bridge"])
            self.assertNotEqual("apply", app.focused.id)
            self.assertTrue(app.query_one("#details", Collapsible).collapsed)
            app.query_one("#details", Collapsible).collapsed = False
            await self.click_ready(app, pilot, "#apply")
            await self.wait_for(app, pilot, lambda: app.result is not None)
            self.assertTrue(app.result["applied"])
            self.assertEqual(1, len(controller.apply_calls))
            self.assertEqual(app.preview_result, controller.apply_calls[0][1])
            self.assert_originals()
            await self.click_ready(app, pilot, "#done")
            self.assertTrue(app.return_value["applied"])

    async def test_selected_corpus_and_back_preserve_choices(self):
        controller = Controller(self.root)
        app = SetupApp(self.installer, controller=controller)
        async with app.run_test(size=(80, 24)) as pilot:
            await self.ready(app, pilot)
            app.query_one("#corpus-mode", Select).value = "selected"
            await pilot.pause()
            await self.click_ready(app, pilot, "#next")
            await pilot.pause()
            self.assertEqual(0, app.step)
            choices = app.query_one("#corpus-choices", SelectionList)
            choices.highlighted = 0
            choices.focus()
            await pilot.press("space")
            await self.next(app, pilot, 1)
            await self.click_ready(app, pilot, "#back")
            await pilot.pause()
            self.assertEqual(0, app.step)
            self.assertEqual(["@fixture/core/coding"], choices.selected)
            self.assertEqual("selected", app.query_one("#corpus-mode", Select).value)
            await pilot.press("ctrl+c")
            self.assertEqual({"cancelled": True, "applied": False}, app.return_value)
            self.assertEqual([], controller.effects)

    async def test_source_selection_survives_back_and_pending_folder_input_is_not_ignored(self):
        controller = Controller(self.root)
        app = SetupApp(self.installer, controller=controller)
        async with app.run_test(size=(80, 24)) as pilot:
            await self.ready(app, pilot)
            await self.next(app, pilot, 1)
            app.query_one("#project-path", Input).value = str(self.project)
            await self.click_ready(app, pilot, "#next")
            await self.wait_for(app, pilot, lambda: not app.busy and len(app.sources) == 2)
            self.assertEqual(1, app.step)
            sources = app.query_one("#source-choices", SelectionList)
            sources.select(str(self.project / "AGENTS.md"))
            await self.click_ready(app, pilot, "#back")
            await pilot.pause()
            await self.next(app, pilot, 1)
            self.assertEqual([str(self.project / "AGENTS.md")], sources.selected)
            self.assertEqual([str(self.project)], controller.discoveries[-1])
            await pilot.press("ctrl+c")
        self.assertEqual([], controller.effects)

    async def test_saved_default_and_explicit_seed_are_distinct(self):
        for seed, expected in ((None, "keep"), ({"selection_mode": "selected", "targets": ["@fixture/core/office"]}, "selected")):
            controller = Controller(self.root, saved=True)
            app = SetupApp(self.installer, controller=controller, initial_plan=seed)
            async with app.run_test(size=(80, 24)) as pilot:
                await self.ready(app, pilot)
                self.assertEqual(expected, app.query_one("#corpus-mode", Select).value)
                if seed:
                    self.assertEqual(seed["targets"], app.query_one("#corpus-choices", SelectionList).selected)
                await pilot.press("ctrl+c")
            self.assertEqual([], controller.effects)

    async def test_mixed_all_and_item_seeds_are_not_silently_narrowed(self):
        controller = Controller(self.root)
        targets = ["all", "@local/personal:existing-item"]
        app = SetupApp(self.installer, controller=controller,
                       initial_plan={"selection_mode": "selected", "targets": targets})
        async with app.run_test(size=(80, 24)) as pilot:
            await self.ready(app, pilot)
            self.assertEqual("selected", app.query_one("#corpus-mode", Select).value)
            self.assertEqual(targets, app.query_one("#corpus-choices", SelectionList).selected)
            await self.next(app, pilot, 1)
            self.assertEqual(targets, app.plan["targets"])
            await pilot.press("ctrl+c")
        self.assertEqual([], controller.effects)

    async def test_cancel_at_each_stage_leaves_no_effects(self):
        for stop in range(4):
            controller = Controller(self.root)
            app = SetupApp(self.installer, controller=controller)
            async with app.run_test(size=(80, 24)) as pilot:
                await self.ready(app, pilot)
                for stage in range(1, stop + 1):
                    await self.next(app, pilot, stage)
                await pilot.press("escape" if stop % 2 == 0 else "ctrl+c")
                self.assertEqual({"cancelled": True, "applied": False}, app.return_value)
            self.assertEqual([], controller.effects)
            self.assert_originals()

    async def test_dry_run_cannot_apply_and_returns_controller_preview(self):
        controller = Controller(self.root)
        app = SetupApp(self.installer, controller=controller, dry_run=True)
        async with app.run_test(size=(80, 24)) as pilot:
            await self.review(app, pilot)
            self.assertFalse(app.query_one("#apply", Button).display)
            await self.click_ready(app, pilot, "#done")
            self.assertTrue(app.return_value["dry_run"])
            self.assertFalse(app.return_value["applied"])
            self.assertTrue(app.return_value["installation"]["dry_run"])
        self.assertEqual([], controller.apply_calls)

    async def test_preview_refusal_and_stale_apply_return_to_editable_review(self):
        controller = Controller(self.root)
        controller.preview_error = SetupError("Source changed")
        app = SetupApp(self.installer, controller=controller)
        async with app.run_test(size=(80, 24)) as pilot:
            await self.ready(app, pilot)
            await self.next(app, pilot, 1)
            await self.next(app, pilot, 2)
            await self.click_ready(app, pilot, "#next")
            await self.wait_for(app, pilot, lambda: not app.busy)
            self.assertEqual(2, app.step)
            self.assertIsNone(app.preview_result)
            controller.preview_error = None
            await self.next(app, pilot, 3)
            controller.apply_error = SetupError("Inputs changed after review")
            await self.click_ready(app, pilot, "#apply")
            await self.wait_for(app, pilot, lambda: not app.busy)
            self.assertEqual(2, app.step)
            self.assertIsNone(app.result)
            self.assertIsNone(app.preview_result)
            self.assertEqual([], controller.effects)
            await pilot.press("ctrl+c")

    async def test_cancel_during_apply_waits_for_safe_boundary_and_retains_outcome(self):
        controller = Controller(self.root)
        controller.block_apply = True
        app = SetupApp(self.installer, controller=controller)
        try:
            async with app.run_test(size=(80, 24)) as pilot:
                await self.review(app, pilot)
                await self.click_ready(app, pilot, "#apply")
                await self.wait_for(app, pilot, lambda: controller.started.is_set())
                await pilot.press("ctrl+c")
                self.assertTrue(app.cancel_requested.is_set())
                self.assertTrue(app.applying)
                self.assertIsNone(app.return_value)
                controller.finish_step.set()
                await self.wait_for(app, pilot, lambda: app.result is not None)
                self.assertTrue(app.result["cancelled_after_start"])
                self.assertEqual([{"id": "schema", "returncode": 0}], app.result["dependency_results"])
                self.assertNotIn("No installation changes were applied", str(app.query_one("#summary", Static).render()))
                await self.click_ready(app, pilot, "#done")
                self.assertTrue(app.return_value["cancelled"])
        finally:
            controller.finish_step.set()
        self.assertEqual(["dependency"], controller.effects)

    async def test_slow_read_only_initialization_does_not_block_cancel(self):
        controller = Controller(self.root)
        controller.default_gate = threading.Event()
        app = SetupApp(self.installer, controller=controller)
        try:
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                self.assertFalse(app.ready)
                await self.click_ready(app, pilot, "#language-continue")
                await self.wait_for(app, pilot, lambda: controller.default_calls == 1)
                await pilot.press("ctrl+c")
                self.assertEqual({"cancelled": True, "applied": False}, app.return_value)
                controller.default_gate.set()
        finally:
            controller.default_gate.set()
        self.assertEqual([], controller.effects)

    async def test_startup_language_choice_precedes_controller_construction_and_uses_two_tabs(self):
        from unittest import mock
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with mock.patch("corpus_setup.SetupController") as factory:
            app = SetupApp(SimpleNamespace(repo=self.root, env={"LANG": "ja_JP.UTF-8"}))
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                self.assertEqual(-1, app.step)
                self.assertEqual("ja", app.query_one("#language-select", Select).value)
                self.assertEqual("language-select", app.focused.id)
                self.assertFalse(app.busy)
                self.assertFalse(app.ready)
                factory.assert_not_called()
                app.query_one("#language-select", Select).value = "ko"
                await pilot.pause()
                self.assertEqual("ko", app.language)
                factory.assert_not_called()
                await pilot.press("tab")
                self.assertEqual("cancel", app.focused.id)
                await pilot.press("tab")
                self.assertEqual("language-continue", app.focused.id)
                await pilot.press("ctrl+c")
                self.assertEqual({"cancelled": True, "applied": False}, app.return_value)
            factory.assert_not_called()
        self.assertEqual(before, {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    async def test_language_switch_after_back_preserves_draft_without_reprobing(self):
        controller = Controller(self.root)
        raw_dependencies = copy.deepcopy(controller.dependencies)
        raw_choices = copy.deepcopy(controller.choices)
        app = SetupApp(self.installer, controller=controller)
        async with app.run_test(size=(80, 24)) as pilot:
            await self.ready(app, pilot)
            app.query_one("#corpus-mode", Select).value = "selected"
            app.query_one("#corpus-choices", SelectionList).select("@fixture/core/coding")
            app.query_one("#app-bridge", Checkbox).value = True
            await self.next(app, pilot, 1)
            app.query_one("#source-choices", SelectionList).select(str(self.root / "global/AGENTS.md"))
            app.query_one("#project-path", Input).value = str(self.project)
            await self.click_ready(app, pilot, "#back")
            await pilot.pause(0.3)
            await self.click_ready(app, pilot, "#back")
            await pilot.pause()
            self.assertEqual(-1, app.step)
            before = copy.deepcopy(app.plan)
            discovery_count = len(controller.discoveries)
            app.query_one("#language-select", Select).value = "ja"
            await pilot.pause()
            self.assertEqual(before, app.plan)
            await pilot.press("tab", "tab", "enter")
            await self.wait_for(app, pilot, lambda: app.step == 0 and not app.busy)
            self.assertEqual(1, controller.default_calls)
            self.assertEqual(discovery_count, len(controller.discoveries))
            self.assertEqual(before, app.plan)
            self.assertEqual(["@fixture/core/coding"], app.query_one("#corpus-choices", SelectionList).selected)
            self.assertTrue(app.query_one("#app-bridge", Checkbox).value)
            self.assertEqual(str(self.project), app.query_one("#project-path", Input).value)
            self.assertIn("キャンセル", str(app.query_one("#key-help", Static).content))
            await pilot.press("ctrl+c")
        self.assertEqual(raw_dependencies, controller.dependencies)
        self.assertEqual(raw_choices, controller.choices)
        self.assertEqual([], controller.effects)

    async def test_unchanged_corpus_value_rerenders_its_visible_caption_on_language_switch(self):
        controller = Controller(self.root)
        app = SetupApp(self.installer, controller=controller)
        async with app.run_test(size=(80, 24)) as pilot:
            for language, caption in (("ja", "コーパス"), ("ko", "코퍼스"), ("en", "No active corpus")):
                app.query_one("#language-select", Select).value = language
                await pilot.pause()
                await self.click_ready(app, pilot, "#language-continue")
                await self.wait_for(app, pilot, lambda: app.step == 0 and app.ready and not app.busy)
                self.assertEqual("none", app.query_one("#corpus-mode", Select).value)
                rendered = str(app.query_one("#corpus-mode SelectCurrent #label", Static).content)
                self.assertIn(caption, rendered)
                if language != "en":
                    self.assertNotIn("No active corpus", rendered)
                await self.click_ready(app, pilot, "#back")
                await self.wait_for(app, pilot, lambda: app.step == -1)
                await pilot.pause(0.3)
            self.assertEqual(1, controller.default_calls)
            await pilot.press("ctrl+c")

    async def test_english_korean_and_japanese_flows_localize_controls_and_keep_payloads(self):
        for language, locale, word, done_word in (("en", "en_US.UTF-8", "Choose corpus", "installed"),
                                                  ("ko", "ko_KR.UTF-8", "코퍼스", "설치"),
                                                  ("ja", "ja_JP.UTF-8", "コーパス", "インストール")):
            controller = Controller(self.root)
            app = SetupApp(SimpleNamespace(repo=self.root, env={"LANG": locale}), controller=controller)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                self.assertEqual(language, app.language)
                await self.ready(app, pilot)
                self.assertIn(word, str(app.query_one("#step-title", Static).content))
                await self.next(app, pilot, 1)
                for identifier in ("add-project", "clear-projects"):
                    widget = app.query_one("#" + identifier, Button)
                    self.assertLessEqual(widget.region.right, app.screen.region.right)
                app.query_one("#source-choices", SelectionList).select(str(self.root / "global/AGENTS.md"))
                await self.next(app, pilot, 2)
                app.query_one("#dependency-choices", SelectionList).select("schema")
                await self.next(app, pilot, 3)
                self.assertIn(str(self.root / "global/AGENTS.md"), str(app.query_one("#summary", Static).content))
                await self.click_ready(app, pilot, "#apply")
                await self.wait_for(app, pilot, lambda: app.result is not None)
                self.assertIn(done_word, str(app.query_one("#summary", Static).content))
                self.assertEqual(["schema"], controller.apply_calls[0][0]["dependencies"])
                self.assertEqual([str(self.root / "global/AGENTS.md")], controller.apply_calls[0][0]["import_paths"])
                self.assertNotIn("ui_language", controller.apply_calls[0][0])
                self.assertEqual(["Operation complete\n"], app.operation_output)
                await self.click_ready(app, pilot, "#done")

    async def test_korean_and_japanese_progress_validation_dryrun_and_startup_error(self):
        for language, cancel_word in (("ko", "취소"), ("ja", "キャンセル")):
            controller = Controller(self.root)
            app = SetupApp(self.installer, controller=controller, dry_run=True)
            async with app.run_test(size=(80, 24)) as pilot:
                app.query_one("#language-select", Select).value = language
                await pilot.pause()
                await self.ready(app, pilot)
                self.assertIn(cancel_word, str(app.query_one("#key-help", Static).content))
                app._progressed({"stage": "dependency", "dependency": "schema", "message": "Installing schema"})
                status = str(app.query_one("#status", Static).content)
                self.assertNotIn("Installing", status)
                self.assertTrue(any("가" <= character <= "힣" for character in status) if language == "ko" else "インストール" in status)
                await self.next(app, pilot, 1)
                app.query_one("#project-path", Input).value = "relative-invalid"
                await self.click_ready(app, pilot, "#add-project")
                self.assertNotIn("Choose an existing", str(app.query_one("#status", Static).content))
                app.query_one("#project-path", Input).value = ""
                await self.next(app, pilot, 2)
                await self.next(app, pilot, 3)
                self.assertFalse(app.query_one("#apply", Button).display)
                self.assertNotEqual("Close preview", str(app.query_one("#done", Button).label))
                await self.click_ready(app, pilot, "#done")
                self.assertTrue(app.return_value["dry_run"])
            failed = Controller(self.root)
            failed.default_error = SetupError("fixture startup detail")
            app = SetupApp(SimpleNamespace(repo=self.root, env={"LANG": language}), controller=failed)
            async with app.run_test(size=(80, 24)) as pilot:
                await self.click_ready(app, pilot, "#language-continue")
                await self.wait_for(app, pilot, lambda: app.result is not None)
                summary = str(app.query_one("#summary", Static).content)
                self.assertIn("fixture startup detail", summary)
                self.assertNotIn("Setup could not be prepared", summary)
                await self.click_ready(app, pilot, "#done")

    async def test_real_controller_preserves_originals_and_writes_only_after_apply(self):
        from corpus_setup import SetupController
        from test_corpus_install_choices import InstallerChoiceTests
        fixture = InstallerChoiceTests()
        fixture.setUp()
        try:
            originals = {}
            for relative in (".codex/AGENTS.md", ".claude/CLAUDE.md", "project/AGENTS.md"):
                path = fixture.home / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("User-owned instruction file\n")
                originals[path] = path.read_bytes()
            controller = SetupController(fixture.installer, inventory=[])
            app = SetupApp(fixture.installer, controller=controller)
            async with app.run_test(size=(80, 24)) as pilot:
                await self.review(app, pilot)
                self.assertFalse(fixture.state.exists())
                self.assertFalse(fixture.user.exists())
                self.assertEqual(originals, {path: path.read_bytes() for path in originals})
                await self.click_ready(app, pilot, "#apply")
                await self.wait_for(app, pilot, lambda: app.result is not None)
                self.assertTrue(app.result["applied"], app.result)
                self.assertTrue(fixture.installer.verify()["stored"])
                self.assertEqual("", fixture.store().snapshot("codex")["instruction_text"])
                self.assertEqual(originals, {path: path.read_bytes() for path in originals})
                await self.click_ready(app, pilot, "#done")
        finally:
            fixture.tearDown()


class SetupEntryPurityTests(unittest.TestCase):
    def test_wrapper_adds_language_only_to_result_or_exception(self):
        from unittest import mock
        from corpus_setup_ui import run_setup_ui
        raw = {"cancelled": True, "applied": False, "plan": {"targets": []}}
        app = SimpleNamespace(run=lambda: raw, backend_error=None, language="ja")
        with mock.patch("corpus_setup_ui.SetupApp", return_value=app):
            result = run_setup_ui(object())
        self.assertEqual("ja", result["ui_language"])
        self.assertNotIn("ui_language", raw)
        self.assertNotIn("ui_language", raw["plan"])
        error = SetupError("raw detail stays unchanged")
        app = SimpleNamespace(run=lambda: None, backend_error=error, language="ko")
        with mock.patch("corpus_setup_ui.SetupApp", return_value=app), self.assertRaises(SetupError) as caught:
            run_setup_ui(object())
        self.assertIs(error, caught.exception)
        self.assertEqual("ko", error.ui_language)
        self.assertEqual("raw detail stays unchanged", str(error))

    def test_no_tty_and_invalid_arguments_do_not_write_into_the_package(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="setup-entry-purity-") as tmp:
            root = Path(tmp)
            repo = root / "package"
            (repo / "compose").mkdir(parents=True)
            for relative in ("install.sh", "compose/corpus_install.py", "compose/corpus_transaction.py"):
                shutil.copy2(source / relative, repo / relative)
            (repo / "package.json").write_text("{}")
            executable = root / "bin/python3"
            executable.parent.mkdir()
            executable.symlink_to(sys.executable)
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("AGENT_BIOS_", "CODEX_", "CLAUDE_"))
                   and key not in {"PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"}}
            env.update(HOME=str(root / "home"), PATH=str(executable.parent) + os.pathsep + os.environ.get("PATH", ""))
            before = {path.relative_to(repo): path.read_bytes() for path in repo.rglob("*") if path.is_file()}
            for arguments in (["install"], ["install", "--not-an-install-option"]):
                with self.subTest(arguments=arguments):
                    result = subprocess.run(["/bin/bash", str(repo / "install.sh"), *arguments],
                                            env=env, stdin=subprocess.DEVNULL, text=True,
                                            capture_output=True, timeout=15)
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual(before, {path.relative_to(repo): path.read_bytes() for path in repo.rglob("*") if path.is_file()})
                    self.assertFalse((root / "home").exists())

    def test_source_change_during_real_registration_refuses_capture_and_retains_the_link(self):
        from unittest import mock
        from corpus_setup import SetupController
        from test_corpus_app import AppCorpusTests
        fixture = AppCorpusTests()
        fixture.setUp()
        try:
            source = (fixture.home / ".codex/AGENTS.md").resolve()
            bridge = fixture.installer._app_manager()
            register = bridge.register

            def change_source_after_register(*args, **kwargs):
                result = register(*args, **kwargs)
                source.write_text("User edit made while registration was running.\n")
                return result

            with mock.patch.object(fixture.installer, "_app_manager", return_value=bridge), \
                    mock.patch.object(bridge, "register", side_effect=change_source_after_register):
                controller = SetupController(fixture.installer, inventory=[])
                plan = controller.default_plan()
                plan.update(app_bridge=True, import_paths=[str(source)])
                preview = controller.preview(plan)
                result = controller.apply(plan, preview)
            self.assertFalse(result["applied"])
            self.assertTrue(result["installation_applied"])
            self.assertIn("extras_error", result)
            self.assertTrue(result["extras"]["app_bridge"]["registered"])
            self.assertTrue(bridge.status()["registered"])
            self.assertEqual([], list((fixture.user / "imports/captures").glob("*.json")))
            self.assertEqual("User edit made while registration was running.\n", source.read_text())
            for path, before in fixture.protected.items():
                if path.resolve() != source:
                    self.assertEqual(before, path.read_bytes())
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
