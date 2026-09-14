"""Installation UI tests use temp state and an injected subprocess runner."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import venv
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from instructions_setup import SetupController, SetupError, catalog_choices, dependency_inventory, format_setup_result, run_setup


class Installer:
    def __init__(self, root: Path):
        self.repo = root
        self.env = {"HOME": str(root / "home"), "PATH": "/fixture/bin"}
        self.calls = []
        self.extras = []
        self.discoveries = []
        (root / "AGENTS.md").write_text("Demo instruction.\n")
        self.sources = [{"path": str(root / "AGENTS.md"), "root": str(root),
                         "scope": {"kind": "project", "root": str(root)}, "hosts": ["codex"]}]

    def setup_catalog(self):
        return {"packages": [{"package_id": "@fixture/library", "domains": {"coding": "Coding"}}]}

    def install(self, **kwargs):
        self.calls.append(kwargs)
        return {"dry_run": kwargs["dry_run"], "selection_mode": kwargs.get("selection_mode"), "targets": kwargs.get("targets")}

    def setup_discover(self, project_roots):
        self.discoveries.append(project_roots)
        return {"sources": self.sources, "omitted": []}

    def setup_extras(self, plan, *, dry_run=False):
        self.extras.append({"dry_run": dry_run, "plan": dict(plan)})
        return {"dry_run": dry_run, "app_bridge": plan["app_bridge"], "import_paths": plan["import_paths"]}


def dependency(identifier="textual", action=None):
    return {"id": identifier, "title": identifier, "role": "optional", "status": "missing",
            "purpose": "Fixture dependency", "version": "", "install_scope": "private fixture",
            "install_argv": action or ["/fixture/bin/bash", "/fixture/provision.sh"], "manual_reason": ""}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.installer = Installer(self.root)
        self.output = io.StringIO()
        self.processes = []

    def tearDown(self):
        self.temp.cleanup()

    def runner(self, argv, **kwargs):
        self.processes.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def run_setup(self, answers, **kwargs):
        iterator = iter(answers)
        return run_setup(self.installer, input_fn=lambda _: next(iterator), output_stream=self.output,
                         inventory=kwargs.pop("inventory", []), runner=kwargs.pop("runner", self.runner), **kwargs)

    def test_cancel_and_eof_never_apply_or_install_dependencies(self):
        for answers in ([], ["cancel"], ["1", "1", "n", "skip", "cancel"]):
            with self.subTest(answers=answers):
                self.installer.calls.clear()
                result = self.run_setup(answers, inventory=[dependency()])
                self.assertTrue(result["cancelled"])
                self.assertEqual([], [call for call in self.installer.calls if not call["dry_run"]])
                self.assertEqual([], self.processes)
                self.assertFalse((self.root / "home").exists())

    def test_stream_eof_cancels(self):
        result = run_setup(self.installer, input_stream=io.StringIO(""), output_stream=self.output,
                           runner=self.runner, inventory=[])
        self.assertTrue(result["cancelled"])
        self.assertEqual([], self.installer.calls)

    def test_no_instructions_is_explicit_none_mode(self):
        result = self.run_setup(["none", "1", "n", "skip", "apply"])
        self.assertTrue(result["applied"])
        self.assertEqual({"dry_run": False, "selection_mode": "none", "targets": []}, self.installer.calls[-1])
        self.assertEqual([], self.processes)

    def test_all_and_selected_have_no_implicit_default(self):
        result = self.run_setup(["none", "2", "n", "skip", "apply"])
        self.assertEqual(["all"], result["plan"]["targets"])
        result = self.run_setup(["none", "3", "2", "n", "skip", "apply"])
        self.assertEqual("selected", result["plan"]["selection_mode"])
        self.assertEqual(["@fixture/library/coding"], result["plan"]["targets"])

    def test_package_choice_and_saved_selection(self):
        result = self.run_setup(["none", "3", "1", "n", "skip", "apply"])
        self.assertEqual(["@fixture/library"], result["plan"]["targets"])
        result = self.run_setup(["none", "4", "n", "skip", "apply"])
        self.assertIsNone(result["plan"]["selection_mode"])
        self.assertIsNone(result["plan"]["targets"])
        self.assertEqual({"dry_run": True}, self.installer.calls[-2])
        self.assertEqual({"dry_run": False}, self.installer.calls[-1])

    def test_back_and_invalid_choices_preserve_no_write_boundary(self):
        result = self.run_setup(["none", "3", "99", "back", "1", "n", "skip", "apply"])
        self.assertTrue(result["applied"])
        self.assertEqual("none", result["plan"]["selection_mode"])
        self.assertIn("outside the displayed list", self.output.getvalue())

    def test_only_reviewed_selected_recipe_runs_without_shell(self):
        second = dependency("git", ["/fixture/bin/brew", "install", "git"])
        result = self.run_setup(["2", "1", "n", "skip", "apply"], inventory=[dependency(), second])
        self.assertTrue(result["applied"])
        self.assertEqual(1, len(self.processes))
        argv, options = self.processes[0]
        self.assertEqual(second["install_argv"], argv)
        self.assertIs(False, options["shell"])
        self.assertEqual(subprocess.DEVNULL, options["stdin"])
        self.assertIn('"argv": [', self.output.getvalue())

    def test_dependency_failure_reports_partial_results_without_base_install(self):
        def fail(argv, **kwargs):
            self.processes.append((argv, kwargs))
            return SimpleNamespace(returncode=8)
        result = self.run_setup(["1", "1", "n", "skip", "apply"], inventory=[dependency()], runner=fail)
        self.assertFalse(result["applied"])
        self.assertEqual("textual", result["dependency_failed"])
        self.assertEqual([], [call for call in self.installer.calls if not call["dry_run"]])

    def test_dependency_launch_error_does_not_return_to_apply_loop(self):
        def fail(argv, **kwargs):
            raise OSError("unavailable")
        result = self.run_setup(["1", "1", "n", "skip", "apply"], inventory=[dependency()], runner=fail)
        self.assertEqual("textual", result["dependency_failed"])
        self.assertIsNone(result["dependency_results"][0]["returncode"])
        self.assertIn("unavailable", result["dependency_results"][0]["stderr"])
        self.assertEqual([], [call for call in self.installer.calls if not call["dry_run"]])

    def test_dry_run_previews_extras_but_never_installs(self):
        result = self.run_setup(["1", "1", "yes", "globals", "1"], inventory=[dependency()], dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual([], self.processes)
        self.assertTrue(all(call["dry_run"] for call in self.installer.calls))
        self.assertTrue(all(call["dry_run"] for call in self.installer.extras))
        self.assertEqual([str(self.root / "AGENTS.md")], result["plan"]["import_paths"])

    def test_import_only_uses_exact_discovery_paths_and_explicit_project_roots(self):
        project = self.root / "project"
        project.mkdir()
        (project / "CLAUDE.md").write_text("Project instruction.\n")
        self.installer.sources.append({"path": str(project / "CLAUDE.md"), "root": str(project),
                                       "scope": {"kind": "project", "root": str(project)}, "hosts": ["claude"]})
        result = self.run_setup(["none", "1", "yes", json.dumps([str(project)]), "2", "apply"])
        self.assertTrue(self.installer.discoveries)
        self.assertTrue(all(roots == [str(project)] for roots in self.installer.discoveries))
        self.assertEqual([str(project / "CLAUDE.md")], result["plan"]["import_paths"])
        self.assertEqual([str(project)], result["plan"]["project_roots"])
        self.assertTrue(all(row["dry_run"] for row in self.installer.extras[:-1]))
        self.assertFalse(self.installer.extras[-1]["dry_run"])
        self.assertIn("require model review", self.output.getvalue())

    def test_empty_import_discovery_can_continue(self):
        self.installer.sources = []
        result = self.run_setup(["none", "1", "n", "globals", "apply"])
        self.assertTrue(result["applied"])
        self.assertEqual([], result["plan"]["import_paths"])

    def test_extras_failure_reports_completed_installation(self):
        def handler(plan, *, dry_run=False):
            if dry_run:
                return {"dry_run": True}
            raise RuntimeError("registration conflict")
        result = self.run_setup(["none", "1", "yes", "skip", "apply"], extras_handler=handler)
        self.assertFalse(result["applied"])
        self.assertTrue(result["installation_applied"])
        self.assertEqual("registration conflict", result["extras_error"])
        self.assertEqual(1, len([call for call in self.installer.calls if not call["dry_run"]]))

    def test_catalog_rejects_empty_inventory(self):
        self.installer.setup_catalog = lambda: {"packages": []}
        with self.assertRaisesRegex(SetupError, "No instructions packages"):
            catalog_choices(self.installer)


class SetupResultTests(unittest.TestCase):
    def test_existing_bridge_attention_is_not_hidden_by_successful_update(self):
        text = format_setup_result({"applied": True, "plan": {"selection_mode": None},
                                    "installation": {"app_bridge": {"registered": False,
                                        "needs_action": ["preserving changed app skill generation"]}}})
        self.assertIn("Private runtime installed", text)
        self.assertIn("bridge needs attention", text)
        self.assertIn("preserving changed app skill generation", text)

    def test_cancel_and_preview_are_clear_about_no_applied_changes(self):
        self.assertIn("No installation changes were applied", format_setup_result({"cancelled": True}))
        self.assertIn("preview complete", format_setup_result({"dry_run": True}))

    def test_dependency_failure_reports_prior_completed_actions(self):
        text = format_setup_result({"applied": False, "dependency_failed": "textual",
                                    "dependency_results": [{"id": "codex", "returncode": 0}, {"id": "textual", "returncode": 1}]})
        self.assertIn("failed: textual", text)
        self.assertIn("already installed: codex", text)
        self.assertIn("private runtime was not installed by this setup", text)
        self.assertNotIn("Setup complete", text)

    def test_extras_failure_keeps_completed_runtime_visible(self):
        text = format_setup_result({"applied": False, "installation_applied": True, "extras_error": "skill path conflict"})
        self.assertIn("Private runtime installed", text)
        self.assertIn("skill path conflict", text)
        self.assertIn("agent-bios instructions", text)
        self.assertNotIn("Setup complete", text)

    def test_success_reports_exact_choices_app_actions_and_capture_followup(self):
        result = {"applied": True, "plan": {"selection_mode": "selected", "targets": ["@fixture/base/coding"]},
                  "installation": {"record": {"installed_files": [{"path": "private/file-not-for-summary", "sha256": "digest"}]}},
                  "extras": {"app_bridge": {"registered": True}, "import": {"capture_id": "capture-123", "source_count": 2,
                             "classification": "requires model review", "next_command": "agent-bios import prompt capture-123",
                             "app_request": "Use $agent-bios to import capture capture-123"}}}
        text = format_setup_result(result)
        self.assertIn("@fixture/base/coding", text)
        self.assertIn("per-task preview/use/off", text)
        self.assertIn("instructions management", text)
        self.assertIn("capture-123 (2 source files)", text)
        self.assertIn("Model review is required before activation", text)
        self.assertIn("agent-bios import prompt capture-123", text)
        self.assertIn("Use $agent-bios to import capture capture-123", text)
        self.assertNotIn("private/file-not-for-summary", text)
        self.assertNotIn("installed_files", text)
        self.assertLess(len(text.splitlines()), 10)

    def test_none_and_preserve_choices_are_distinct(self):
        empty = format_setup_result({"applied": True, "plan": {"selection_mode": "none", "targets": []}})
        preserved = format_setup_result({"applied": True, "plan": {"selection_mode": None, "targets": None}})
        self.assertIn("future activated sessions: none", empty)
        self.assertIn("Saved instructions policy and item choices preserved", preserved)


class SetupControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.installer = Installer(self.root)
        self.commands = []

    def tearDown(self):
        self.temp.cleanup()

    def runner(self, argv, **kwargs):
        self.commands.append(argv)
        return SimpleNamespace(returncode=0, stdout="prepared", stderr="")

    def controller(self, **kwargs):
        return SetupController(self.installer, inventory=kwargs.pop("inventory", []),
                               runner=kwargs.pop("runner", self.runner), **kwargs)

    def assert_no_install(self):
        self.assertFalse(any(not call["dry_run"] for call in self.installer.calls))

    def test_fresh_default_and_saved_default_are_distinct(self):
        controller = self.controller()
        self.assertEqual("none", controller.default_plan()["selection_mode"])
        self.installer.status = lambda: {"installed": True}
        self.assertIsNone(controller.default_plan()["selection_mode"])
        self.assertIsNone(controller.default_plan()["targets"])

    def test_source_change_invalidates_review_before_any_dependency(self):
        controller = self.controller(inventory=[dependency("schema")])
        plan = controller.default_plan()
        plan.update(import_paths=[self.installer.sources[0]["path"]], dependencies=["schema"])
        preview = controller.preview(plan)
        (self.root / "AGENTS.md").write_text("Changed source.\n")
        with self.assertRaisesRegex(SetupError, "changed after review"):
            controller.apply(plan, preview)
        self.assertEqual([], self.commands)
        self.assert_no_install()

    def test_changed_recipe_invalidates_review(self):
        controller = self.controller(inventory=[dependency("schema")])
        plan = controller.default_plan()
        plan["dependencies"] = ["schema"]
        preview = controller.preview(plan)
        controller.dependencies[0]["install_argv"] = ["/different/installer", "schema"]
        with self.assertRaisesRegex(SetupError, "changed after review"):
            controller.apply(plan, preview)
        self.assertEqual([], self.commands)
        self.assert_no_install()

    def test_unoffered_action_or_source_cannot_be_submitted(self):
        controller = self.controller()
        for patch in ({"dependencies": ["unknown"]}, {"import_paths": [str(self.root / "outside.md")]},
                      {"app_bridge": "yes"}, {"selection_mode": []}, {"shell_command": "unexpected"}):
            with self.subTest(patch=patch):
                plan = {**controller.default_plan(), **patch}
                with self.assertRaises(SetupError):
                    controller.preview(plan)
        self.assert_no_install()

    def test_cancellation_retains_completed_dependency_and_stops_next_step(self):
        cancelled = False
        def runner(argv, **kwargs):
            nonlocal cancelled
            self.commands.append(argv)
            cancelled = True
            return SimpleNamespace(returncode=0, stdout="done", stderr="")
        controller = self.controller(inventory=[dependency("first"), dependency("second")], runner=runner)
        plan = controller.default_plan()
        plan["dependencies"] = ["first", "second"]
        result = controller.apply(plan, controller.preview(plan), should_cancel=lambda: cancelled)
        self.assertTrue(result["cancelled_after_start"])
        self.assertEqual(["first"], [row["id"] for row in result["dependency_results"]])
        self.assertEqual(1, len(self.commands))
        self.assert_no_install()
        self.assertIn("Dependencies retained: first", format_setup_result(result))
        self.assertNotIn("No installation changes", format_setup_result(result))

    def test_later_dependency_spawn_error_retains_previous_success(self):
        def runner(argv, **kwargs):
            self.commands.append(argv)
            if len(self.commands) == 2:
                raise OSError("second executable disappeared")
            return SimpleNamespace(returncode=0, stdout="first completed", stderr="")
        controller = self.controller(inventory=[dependency("first"), dependency("second")], runner=runner)
        plan = controller.default_plan()
        plan["dependencies"] = ["first", "second"]
        result = controller.apply(plan, controller.preview(plan))
        self.assertEqual("second", result["dependency_failed"])
        self.assertEqual([0, None], [row["returncode"] for row in result["dependency_results"]])
        self.assertIn("second executable disappeared", result["dependency_results"][1]["stderr"])
        self.assertIn("Dependencies already installed: first", format_setup_result(result))
        self.assert_no_install()

    def test_cancellation_after_runtime_preserves_it_and_skips_extras(self):
        cancelled = False
        original = self.installer.install
        def install(**kwargs):
            nonlocal cancelled
            result = original(**kwargs)
            if not kwargs["dry_run"]:
                cancelled = True
            return result
        self.installer.install = install
        controller = self.controller()
        plan = controller.default_plan()
        plan["app_bridge"] = True
        result = controller.apply(plan, controller.preview(plan), should_cancel=lambda: cancelled)
        self.assertTrue(result["installation_applied"])
        self.assertTrue(result["cancelled_after_start"])
        self.assertTrue(all(row["dry_run"] for row in self.installer.extras))
        self.assertIn("installation is retained", format_setup_result(result))

    def test_source_change_during_dependency_execution_preserves_partial_outcome(self):
        def runner(argv, **kwargs):
            (self.root / "AGENTS.md").write_text("Another process changed this file.\n")
            return SimpleNamespace(returncode=0, stdout="done", stderr="")
        controller = self.controller(inventory=[dependency("schema")], runner=runner)
        plan = controller.default_plan()
        plan.update(import_paths=[self.installer.sources[0]["path"]], dependencies=["schema"])
        result = controller.apply(plan, controller.preview(plan))
        self.assertIn("sources changed", result["installation_error"])
        self.assertEqual(0, result["dependency_results"][0]["returncode"])
        self.assert_no_install()
        self.assertIn("Dependencies retained: schema", format_setup_result(result))


class DependencyInventoryTests(unittest.TestCase):
    def test_ui_inventory_comes_from_bundle_without_a_managed_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = dependency_inventory(Path(__file__).resolve().parents[1],
                                        {"HOME": tmp, "AGENT_LAUNCH_VENV": str(Path(tmp) / "absent")},
                                        which=lambda *args, **kwargs: None)
            bundled = [row for row in rows if row["role"].startswith("bundled UI")]
            self.assertGreater(len(bundled), 1)
            self.assertTrue(all(row["status"] == "available" and row["install_argv"] is None for row in bundled))
            self.assertTrue(all(row["version"] for row in bundled))
            self.assertFalse((Path(tmp) / "absent").exists())

    def test_empty_managed_runtime_override_uses_default_home(self):
        def which(_name, **_kwargs):
            return None
        def runner(*_args, **_kwargs):
            raise AssertionError("no executable was discovered")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(__file__).resolve().parents[1]
            base = dependency_inventory(repo, {"HOME": tmp}, runner=runner, which=which)
            cleared = dependency_inventory(repo, {"HOME": tmp, "AGENT_LAUNCH_VENV": ""}, runner=runner, which=which)
            self.assertEqual(base, cleared)
            validator = next(row for row in cleared if row["id"] == "jsonschema")
            self.assertEqual(str(Path(tmp) / ".local/share/agent-launch/venv"), validator["install_scope"])

    def test_probes_are_read_only_and_builtin_recipes_use_argv(self):
        calls = []
        def which(name, **kwargs):
            return "/fixture/" + name if name not in {"codex", "claude", "zsh"} else None
        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            text = "v24.0.0\n" if argv[0].endswith("node") else "1.2.3\n"
            return SimpleNamespace(returncode=0, stdout=text, stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "launch").mkdir()
            (repo / "launch/provision-venv.sh").write_text('TEXTUAL_PIN="textual==8.2.8"\nJSONSCHEMA_PIN="jsonschema==4.26.0"\n', encoding="utf-8")
            rows = dependency_inventory(repo, {"HOME": tmp, "PATH": "/fixture"}, runner=runner, which=which, system="Darwin")
            inventory = {row["id"]: row for row in rows}
            self.assertEqual(["/fixture/brew", "install", "--cask", "codex"], inventory["codex"]["install_argv"])
            self.assertIsNone(inventory["textual"]["install_argv"])
            self.assertEqual("bundled UI runtime", inventory["textual"]["role"])
            self.assertEqual("learning capture", inventory["jsonschema"]["role"])
            self.assertFalse((repo / ".local").exists())
        self.assertTrue(calls)
        self.assertTrue(all(options["shell"] is False and options["stdin"] == subprocess.DEVNULL for _, options in calls))
        self.assertTrue(all(options["env"]["PYTHONDONTWRITEBYTECODE"] == "1" for _, options in calls))
        self.assertTrue(all("install" not in argv for argv, _ in calls))

    def test_npm_claude_requires_node_22_and_codex_can_use_node_18(self):
        def which(name, **kwargs):
            return "/fixture/" + name if name in {"node", "npm", "python3", "bash"} else None
        def runner(argv, **kwargs):
            return SimpleNamespace(returncode=0, stdout="v20.0.0\n" if argv[0].endswith("node") else "3.12.0\n", stderr="")
        rows = {row["id"]: row for row in dependency_inventory(Path("/fixture/repo"), {"HOME": "/fixture"}, runner=runner, which=which, system="Linux")}
        self.assertIsNone(rows["claude"]["install_argv"])
        self.assertIn("22+", rows["claude"]["manual_reason"])
        self.assertEqual(["/fixture/npm", "install", "-g", "@openai/codex"], rows["codex"]["install_argv"])

    def test_unsupported_platform_offers_no_execution_recipe(self):
        rows = dependency_inventory(Path("/fixture"), {}, runner=lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr=""),
                                    which=lambda name, **kwargs: "/fixture/" + name, system="Windows")
        self.assertTrue(rows)
        self.assertTrue(all(row["install_argv"] is None for row in rows))

    def test_failed_node_probe_does_not_authorize_npm_host_recipe(self):
        def which(name, **kwargs):
            return "/fixture/" + name if name in {"node", "npm"} else None
        def runner(argv, **kwargs):
            return SimpleNamespace(returncode=1, stdout="v24.0.0\n", stderr="failure")
        rows = {row["id"]: row for row in dependency_inventory(Path("/fixture"), {}, runner=runner, which=which, system="Linux")}
        self.assertIsNone(rows["codex"]["install_argv"])
        self.assertIsNone(rows["claude"]["install_argv"])

    def test_learning_validator_checks_managed_fallback_and_offers_exact_recipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            provisioner = repo / "launch/provision-venv.sh"
            provisioner.parent.mkdir()
            provisioner.write_text('TEXTUAL_PIN="textual==8.2.8"\nJSONSCHEMA_PIN="jsonschema==4.26.0"\n', encoding="utf-8")
            managed = repo / "managed/bin/python"
            managed.parent.mkdir(parents=True)
            managed.touch()
            env = {"HOME": tmp, "AGENT_LAUNCH_VENV": str(managed.parents[1])}
            calls = []
            def which(name, **kwargs):
                return "/fixture/" + name if name in {"python3", "bash"} else None
            def runner(argv, **kwargs):
                calls.append(argv)
                if "jsonschema" in " ".join(argv):
                    return SimpleNamespace(returncode=0 if argv[0] == str(managed) else 1,
                                           stdout="4.26.0\n" if argv[0] == str(managed) else "", stderr="missing")
                return SimpleNamespace(returncode=0, stdout="1.0\n", stderr="")
            rows = {row["id"]: row for row in dependency_inventory(repo, env, runner=runner, which=which, system="Linux")}
            self.assertEqual("available", rows["jsonschema"]["status"])
            self.assertEqual(str(managed), rows["jsonschema"]["path"])
            self.assertIsNone(rows["jsonschema"]["install_argv"])
            json_calls = [call for call in calls if "jsonschema" in " ".join(call)]
            self.assertEqual(["/fixture/python3", str(managed)], [call[0] for call in json_calls])
            self.assertIn("actual != '4.26.0'", json_calls[-1][-1])
            self.assertIn("sys.version_info < (3, 11)", json_calls[-1][-1])
            def missing(argv, **kwargs):
                return SimpleNamespace(returncode=1 if "jsonschema" in " ".join(argv) else 0, stdout="", stderr="missing")
            rows = {row["id"]: row for row in dependency_inventory(repo, env, runner=missing, which=which, system="Linux")}
            self.assertEqual(["/fixture/bash", str(provisioner), "--learning-only"], rows["jsonschema"]["install_argv"])
            self.assertEqual(str(managed.parents[1]), rows["jsonschema"]["install_scope"])

    def test_learning_validator_prefers_usable_system_python(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append(argv)
            return SimpleNamespace(returncode=0, stdout="4.25.1\n", stderr="")
        rows = {row["id"]: row for row in dependency_inventory(Path("/fixture"), {}, runner=runner,
                which=lambda name, **kwargs: "/fixture/" + name if name == "python3" else None, system="Linux")}
        self.assertEqual("available", rows["jsonschema"]["status"])
        self.assertEqual("/fixture/python3", rows["jsonschema"]["path"])
        self.assertEqual("4.25.1", rows["jsonschema"]["version"])
        self.assertIsNone(rows["jsonschema"]["install_argv"])

    def test_configured_bootstrap_python_controls_managed_install_recipes(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            configured = str(Path(tmp) / "selected-python")
            calls = []
            def which(name, **kwargs):
                return name if name == configured else ("/fixture/" + name if name in {"bash", "python3"} else None)
            def runner(argv, **kwargs):
                calls.append(argv)
                good = argv[0] != configured and "jsonschema" not in " ".join(argv)
                return SimpleNamespace(returncode=0 if good else 1, stdout="3.14.5\n" if good else "", stderr="missing venv")
            rows = {row["id"]: row for row in dependency_inventory(repo, {"HOME": tmp, "AGENT_LAUNCH_PYTHON": configured}, runner=runner, which=which)}
            self.assertEqual(configured, rows["python-venv"]["path"])
            self.assertEqual("missing", rows["python-venv"]["status"])
            self.assertTrue(any(argv[0] == configured and "ensurepip" in argv[-1] for argv in calls))
            self.assertIsNone(rows["textual"]["install_argv"])
            self.assertIsNone(rows["jsonschema"]["install_argv"])
            missing = {row["id"]: row for row in dependency_inventory(repo, {"HOME": tmp, "AGENT_LAUNCH_PYTHON": "/missing-python"}, runner=runner, which=which)}
            self.assertIsNone(missing["python-venv"]["path"])
            self.assertIsNone(missing["textual"]["install_argv"])

    def test_broken_package_managers_never_offer_install_recipes(self):
        def which(name, **kwargs):
            return "/fixture/" + name if name in {"node", "npm", "brew"} else None
        def runner(argv, **kwargs):
            okay = argv[0].endswith("node")
            return SimpleNamespace(returncode=0 if okay else 1, stdout="v24.0.0\n" if okay else "", stderr="broken")
        rows = {row["id"]: row for row in dependency_inventory(Path("/fixture"), {}, runner=runner, which=which, system="Linux")}
        self.assertEqual("missing", rows["homebrew"]["status"])
        self.assertEqual("missing", rows["npm"]["status"])
        self.assertTrue(all(row["install_argv"] is None for row in rows.values()))

    def test_old_node_does_not_restore_unsupported_platform_recipe(self):
        rows = dependency_inventory(Path("/fixture"), {},
            runner=lambda *a, **k: SimpleNamespace(returncode=0, stdout="v20.0.0\n", stderr=""),
            which=lambda name, **kwargs: "/fixture/" + name, system="Windows")
        self.assertTrue(rows)
        self.assertTrue(all(row["install_argv"] is None for row in rows))

    def test_incomplete_pin_source_refuses_to_offer_unpinned_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "launch").mkdir()
            (repo / "launch/provision-venv.sh").write_text('TEXTUAL_PIN="textual==8.2.8"\n', encoding="utf-8")
            with self.assertRaisesRegex(SetupError, "dependency pins are incomplete"):
                dependency_inventory(repo, {"HOME": tmp}, which=lambda *a, **k: None)


PIP_STUB = '''import json, os, pathlib, shutil, sys
root = pathlib.Path(__file__).parent
specs = [value for value in sys.argv[1:] if "==" in value]
with open(os.environ["SETUP_TEST_PIP_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(specs) + "\\n")
if not os.environ.get("SETUP_TEST_PIP_NOOP"):
    for spec in specs:
        name, version = spec.split("==", 1)
        for old in root.glob(name + "-*.dist-info"):
            shutil.rmtree(old)
        package = root / name
        package.mkdir(exist_ok=True)
        body = "__version__ = " + repr(version) + "\\n"
        if name == "jsonschema":
            body += "class Draft202012Validator: pass\\n"
        (package / "__init__.py").write_text(body, encoding="utf-8")
        metadata = root / (name + "-" + version + ".dist-info")
        metadata.mkdir()
        (metadata / "METADATA").write_text("Metadata-Version: 2.1\\nName: " + name + "\\nVersion: " + version + "\\n", encoding="utf-8")
'''


class ProvisionerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.managed = self.root / "managed environment"
        self.log = self.root / "pip.jsonl"
        self.script = Path(__file__).resolve().parents[1] / "launch/provision-venv.sh"
        self.env = dict(os.environ, HOME=str(self.root), AGENT_LAUNCH_VENV=str(self.managed),
                        AGENT_LAUNCH_PYTHON=sys.executable, SETUP_TEST_PIP_LOG=str(self.log))
        self.env.pop("PYTHONPATH", None)
        self.env.pop("PYTHONHOME", None)
        self.create_environment()

    def tearDown(self):
        self.temp.cleanup()

    def create_environment(self):
        venv.EnvBuilder(with_pip=False).create(self.managed)
        self.site = next((self.managed / "lib").glob("python*/site-packages"))
        (self.site / "pip.py").write_text(PIP_STUB, encoding="utf-8")

    def package(self, name, version, *, broken=False):
        package = self.site / name
        package.mkdir(exist_ok=True)
        body = f"__version__ = {version!r}\n"
        if name == "jsonschema":
            body += "class Draft202012Validator: pass\n"
        (package / "__init__.py").write_text("raise ImportError('broken fixture')\n" if broken else body, encoding="utf-8")
        metadata = self.site / (name + "-" + version + ".dist-info")
        metadata.mkdir(exist_ok=True)
        (metadata / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n", encoding="utf-8")

    def run_provisioner(self, *args):
        return subprocess.run(["bash", str(self.script), *args], shell=False, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, env=self.env, timeout=15)

    def installed_specs(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    def test_learning_only_installs_only_pinned_validator_and_preserves_textual(self):
        self.package("textual", "8.2.8")
        before = (self.site / "textual/__init__.py").read_bytes()
        result = self.run_provisioner("--learning-only")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([["jsonschema==4.26.0"]], self.installed_specs())
        self.assertEqual(before, (self.site / "textual/__init__.py").read_bytes())
        self.assertIn("jsonschema 4.26.0", result.stdout)

    def test_default_installs_only_pinned_textual(self):
        result = self.run_provisioner()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([["textual==8.2.8"]], self.installed_specs())
        self.assertFalse((self.site / "jsonschema").exists())

    def test_matching_pin_skips_pip(self):
        self.package("jsonschema", "4.26.0")
        result = self.run_provisioner("--learning-only")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], self.installed_specs())

    def test_wrong_installed_version_does_not_satisfy_pin(self):
        self.package("jsonschema", "4.25.1")
        result = self.run_provisioner("--learning-only")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([["jsonschema==4.26.0"]], self.installed_specs())

    def test_matching_metadata_with_broken_import_is_repaired(self):
        self.package("textual", "8.2.8", broken=True)
        result = self.run_provisioner()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([["textual==8.2.8"]], self.installed_specs())

    def test_matching_validator_pin_without_required_api_is_repaired(self):
        self.package("jsonschema", "4.26.0")
        (self.site / "jsonschema/__init__.py").write_text("__version__ = '4.26.0'\n", encoding="utf-8")
        result = self.run_provisioner("--learning-only")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([["jsonschema==4.26.0"]], self.installed_specs())
        self.assertIn("Draft202012Validator", (self.site / "jsonschema/__init__.py").read_text())

    def test_pip_success_without_pinned_result_fails_final_verification(self):
        self.package("jsonschema", "4.25.1")
        self.env["SETUP_TEST_PIP_NOOP"] = "1"
        result = self.run_provisioner("--learning-only")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("expected 4.26.0, found 4.25.1", result.stderr)

    def test_unknown_argument_rejected_before_install(self):
        result = self.run_provisioner("--unknown")
        self.assertEqual(2, result.returncode)
        self.assertEqual([], self.installed_specs())

    def old_python(self, path):
        if path.exists() or path.is_symlink():
            path.unlink()
        path.write_text(f"#!{sys.executable}\nimport pathlib, sys\nif sys.argv[1:2] == ['-c']:\n    sys.version_info = (3, 10, 99)\n    exec(sys.argv[2])\nelse:\n    pathlib.Path({str(self.log)!r}).write_text('unexpected interpreter mutation')\n    raise SystemExit(91)\n", encoding="utf-8")
        path.chmod(0o755)

    def test_unsupported_creation_python_preserves_missing_environment(self):
        shutil.rmtree(self.managed)
        old = self.root / "old-python"
        self.old_python(old)
        self.env["AGENT_LAUNCH_PYTHON"] = str(old)
        result = self.run_provisioner()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("requires Python 3.11+", result.stderr)
        self.assertFalse(self.managed.exists())
        self.assertFalse(self.log.exists())

    def test_unsupported_managed_python_is_preserved_without_pip(self):
        self.package("textual", "8.2.8")
        self.old_python(self.managed / "bin/python")
        before = (self.managed / "bin/python").read_bytes()
        result = self.run_provisioner()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("requires Python 3.11+", result.stderr)
        self.assertEqual(before, (self.managed / "bin/python").read_bytes())
        self.assertFalse(self.log.exists())

    def test_missing_environment_is_created_by_selected_interpreter(self):
        shutil.rmtree(self.managed)
        seed = self.root / "seed-python"
        seed.write_text(f"#!{sys.executable}\nimport pathlib, sys, venv\nif sys.argv[1:2] == ['-c']:\n    exec(sys.argv[2])\n    raise SystemExit(0)\nroot = pathlib.Path(sys.argv[-1])\nvenv.EnvBuilder(with_pip=False).create(root)\nsite = next((root / 'lib').glob('python*/site-packages'))\n(site / 'pip.py').write_text({PIP_STUB!r}, encoding='utf-8')\n", encoding="utf-8")
        seed.chmod(0o755)
        self.env["AGENT_LAUNCH_PYTHON"] = str(seed)
        result = self.run_provisioner("--learning-only")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([["jsonschema==4.26.0"]], self.installed_specs())


class SetupCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.state, self.user = self.root / "state", self.root / "user"
        self.script = Path(__file__).resolve().parents[1] / "install.sh"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.actions = self.root / "unexpected-actions.log"
        self.probes = self.root / "version-probes.log"
        (self.bin / "python3").symlink_to(sys.executable)
        for name, version in (("node", "v24.0.0"), ("npm", "11.0.0"), ("brew", "Homebrew 4.0.0"),
                              ("codex", "codex-cli 0.153.4"), ("claude", "2.1.263"),
                              ("git", "git version 2.50.1"), ("zsh", "zsh 5.9")):
            path = self.bin / name
            path.write_text(f'#!/bin/sh\nif [ "$#" -eq 1 ] && [ "$1" = --version ]; then\n  printf "%s\\n" "{name}" >> "$SETUP_CLI_PROBE_LOG"\n  printf "%s\\n" "{version}"\n  exit 0\nfi\nprintf "%s\\n" "{name} $*" >> "$SETUP_CLI_ACTION_LOG"\nexit 77\n', encoding="utf-8")
            path.chmod(0o755)
        blocked_python = self.bin / "blocked-bootstrap-python"
        blocked_python.write_text('#!/bin/sh\nif [ "$#" -eq 2 ] && [ "$1" = -c ]; then exit 77; fi\nprintf "%s\\n" "managed-python $*" >> "$SETUP_CLI_ACTION_LOG"\nexit 77\n', encoding="utf-8")
        blocked_python.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin) + ":/usr/bin:/bin",
                        AGENT_BIOS_STATE_DIR=str(self.state), AGENT_BIOS_INSTRUCTIONS_DIR=str(self.user),
                        CLAUDE_CONFIG_DIR=str(self.home / ".claude"), CODEX_HOME=str(self.home / ".codex"),
                        ZDOTDIR=str(self.home), AGENT_LAUNCH_VENV=str(self.root / "managed"),
                        AGENT_LAUNCH_PYTHON=str(blocked_python), SETUP_CLI_ACTION_LOG=str(self.actions),
                        SETUP_CLI_PROBE_LOG=str(self.probes), LC_ALL="C",
                        AGENT_BIOS_LEGACY_INSTALL="0", TERM="xterm-256color")
        for name in ("PYTHONPATH", "PYTHONHOME", "AGENT_BIOS_PRIVATE_INSTRUCTIONS", "AGENT_BIOS_PACKAGE_ROOT", "AGENT_BIOS_REPO"):
            self.env.pop(name, None)
        self.children = []

    def tearDown(self):
        for process, master, _ in self.children:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            os.close(master)
        self.temp.cleanup()

    def no_install_writes(self):
        self.assertFalse(self.state.exists())
        self.assertFalse(self.user.exists())
        self.assertFalse((self.home / ".local").exists())
        self.assertFalse((self.home / ".config").exists())
        self.assertFalse((self.root / "managed").exists())
        self.assertFalse(self.actions.exists())

    def spawn_tty(self, *arguments):
        master, slave = pty.openpty()
        import fcntl
        import struct
        import termios
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 100, 0, 0))
        try:
            process = subprocess.Popen(["/bin/bash", str(self.script), "install", *arguments],
                                       stdin=slave, stdout=slave, stderr=slave, env=self.env, cwd=self.root)
        finally:
            os.close(slave)
        child = (process, master, bytearray())
        self.children.append(child)
        return child

    def read_tty(self, child, until=None, timeout=25):
        process, master, output = child
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if until is not None and until.encode() in output:
                return output.decode(errors="replace")
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    chunk = b""
                if chunk:
                    output.extend(chunk)
                    continue
            if process.poll() is not None:
                text = output.decode(errors="replace")
                if until is not None:
                    self.fail(f"Installer exited before {until!r}; recent output: {text[-6000:]}")
                return text
        self.fail("Installer timed out; recent output: " + output.decode(errors="replace")[-6000:])

    def without_site_packages(self):
        python = self.bin / "python3"
        python.unlink()
        python.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -S \"$@\"\n")
        python.chmod(0o755)

    def reach_review(self, child):
        self.accept_language(child)
        self.press_next(child, 4)
        self.read_tty(child, "Capture is independent of instructions selection")
        self.press_next(child, 6)
        self.read_tty(child, "Choose dependencies")
        self.press_next(child, 4)
        self.read_tty(child, "Review the effects")

    def press_next(self, child, tabs):
        time.sleep(0.35)
        os.write(child[1], b"\t" * tabs + b"\r")

    def accept_language(self, child):
        self.read_tty(child, "Continue /")
        self.press_next(child, 2)
        return self.read_tty(child, "No installation changes yet.")

    def test_bare_tty_uses_bundled_textual_with_no_site_packages(self):
        self.without_site_packages()
        child = self.spawn_tty()
        output = self.read_tty(child, "Continue /")
        self.assertIn("Language /", output)
        self.assertIn("English", output)
        self.assertNotIn("Choose instructions", output)
        self.assertNotIn("Install numbers, or none", output)
        self.assertFalse(self.probes.exists())
        self.no_install_writes()
        os.write(child[1], b"\x1b")
        output = self.read_tty(child)
        self.assertEqual(0, child[0].returncode, output)
        self.assertIn("Setup cancelled.", output)
        self.no_install_writes()
        self.assertFalse(self.probes.exists())

    def test_selection_and_preview_flags_keep_the_interactive_route(self):
        for arguments in (("--instructions", "all"), ("--dry-run", "--instructions", "none"), ("--interactive",)):
            with self.subTest(arguments=arguments):
                child = self.spawn_tty(*arguments)
                self.accept_language(child)
                self.no_install_writes()
                os.write(child[1], b"\x03")
                output = self.read_tty(child)
                self.assertEqual(0, child[0].returncode, output)
                self.assertIn("Setup cancelled.", output)
                self.no_install_writes()

    def test_only_explicit_noninteractive_flags_use_machine_output(self):
        for arguments in (("--non-interactive",), ("--non-interactive", "--instructions", "none"),
                          ("--non-interactive", "--domains", "none", "--dry-run")):
            with self.subTest(arguments=arguments):
                child = self.spawn_tty(*arguments)
                output = self.read_tty(child)
                self.assertEqual(0, child[0].returncode, output)
                self.assertNotIn("Choose instructions", output)
                result = json.loads(output)
                self.assertNotIn("ui_language", result)
                self.assertTrue(result.get("stored") or result.get("dry_run"))
                self.assertFalse(self.actions.exists())

    def test_tty_interactive_dry_run_keeps_no_writes_and_compact_final_summary(self):
        child = self.spawn_tty("--dry-run")
        self.accept_language(child)
        self.press_next(child, 4)
        self.read_tty(child, "Capture is independent of instructions selection")
        self.press_next(child, 6)
        self.read_tty(child, "Choose dependencies")
        self.press_next(child, 4)
        self.read_tty(child, "Read-only preview.")
        self.no_install_writes()
        os.write(child[1], b"\r")
        output = self.read_tty(child)
        self.assertEqual(0, child[0].returncode, output)
        self.assertIn("Review setup", output)
        self.assertTrue(output.rstrip().endswith("Setup preview complete. No installation changes were applied."))
        self.assertNotIn("installed_files", output)
        self.no_install_writes()

    def test_tty_apply_installs_chosen_policy_and_prints_compact_completion(self):
        child = self.spawn_tty()
        self.reach_review(child)
        self.no_install_writes()
        os.write(child[1], b"\t\t\r")
        self.read_tty(child, "Setup complete. Private runtime installed.")
        os.write(child[1], b"\r")
        output = self.read_tty(child)
        self.assertEqual(0, child[0].returncode, output)
        self.assertIn("Setup complete. Private runtime installed.", output)
        self.assertIn("Instructions for future activated sessions: none.", output)
        self.assertNotIn("installed_files", output)
        record = json.loads((self.state / "runtime/private-install.json").read_text(encoding="utf-8"))
        self.assertEqual("none", record["selection_mode"])
        self.assertEqual([], record["selection"])
        self.assertFalse(self.actions.exists())

    def test_non_tty_install_requires_explicit_noninteractive_choice(self):
        for command in ("install", "onboard"):
            result = subprocess.run(["/bin/bash", str(self.script), command], stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, env=self.env, cwd=self.root, timeout=25)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("--non-interactive", result.stderr)
            self.assertEqual("", result.stdout)
            self.no_install_writes()

    def test_interactive_legacy_domain_flag_does_not_implicitly_apply(self):
        child = self.spawn_tty("--domains", "none")
        output = self.read_tty(child)
        self.assertNotEqual(0, child[0].returncode)
        self.assertIn("--non-interactive", output)
        self.no_install_writes()

    def test_japanese_selection_reaches_the_wizard_and_terminal_summary(self):
        self.without_site_packages()
        child = self.spawn_tty()
        self.read_tty(child, "Continue /")
        os.write(child[1], b"\r")
        self.read_tty(child, "日本語")
        os.write(child[1], b"\x1b[B\x1b[B\r")
        self.press_next(child, 2)
        self.read_tty(child, "指示")
        self.no_install_writes()
        os.write(child[1], b"\x03")
        output = self.read_tty(child)
        self.assertEqual(0, child[0].returncode, output[-3000:])
        self.assertIn("キャンセル", output.splitlines()[-1])
        self.assertNotIn("Setup cancelled.", output.splitlines()[-1])
        self.no_install_writes()

    def test_selected_language_survives_cli_output_boundaries(self):
        import instructions_install

        class Terminal(io.StringIO):
            def isatty(self):
                return True

        for language, script_pattern in (("ko", r"[가-힣]"), ("ja", r"[ぁ-ゖァ-ヺ]")):
            with self.subTest(language=language):
                error = RuntimeError("EXACT BACKEND DIAGNOSTIC")
                error.ui_language = language
                outcome = {"failed": False}

                def failed_ui(*args, **kwargs):
                    if outcome["failed"]:
                        raise error
                    return {"cancelled": True, "applied": False, "ui_language": language}

                ui = ModuleType("instructions_setup_ui")
                ui.run_setup_ui = failed_ui
                runtime = ModuleType("instructions_ui_runtime")
                runtime.activate_ui_runtime = lambda repo: None
                output, diagnostic = Terminal(), io.StringIO()
                with patch.dict(sys.modules, instructions_setup_ui=ui, instructions_ui_runtime=runtime), \
                        patch.dict(os.environ, self.env, clear=True), \
                        patch.object(sys, "stdin", Terminal()), patch.object(sys, "stdout", output), \
                        patch.object(sys, "stderr", diagnostic):
                    self.assertEqual(0, instructions_install.main(["--repo", str(self.script.parent), "install"]))
                    self.assertRegex(output.getvalue(), script_pattern)
                    self.assertEqual("", diagnostic.getvalue())
                    output.seek(0)
                    output.truncate()
                    outcome["failed"] = True
                    code = instructions_install.main(["--repo", str(self.script.parent), "install"])
                self.assertEqual(1, code)
                self.assertRegex(diagnostic.getvalue(), script_pattern)
                self.assertIn("EXACT BACKEND DIAGNOSTIC", diagnostic.getvalue())
                self.assertEqual("", output.getvalue())
                self.no_install_writes()


if __name__ == "__main__":
    unittest.main()
