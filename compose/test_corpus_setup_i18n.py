"""Locale, message coverage, outcome fidelity, and display-data ownership checks."""
from __future__ import annotations

import ast
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from corpus_setup import catalog_choices, dependency_inventory, format_setup_result
from corpus_install import CorpusInstaller
from corpus_setup_i18n import (
    LANGUAGES, MESSAGES, choice_label, dependency_display, detect_language,
    template_fields, translate, validate_catalogs,
)


ROOT = Path(__file__).resolve().parents[1]


def literal_translation_keys(source: str) -> set[str]:
    keys = set()
    tree = ast.parse(source)
    def literals(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if isinstance(node, ast.IfExp):
            return literals(node.body) | literals(node.orelse)
        return set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in
                                               {"STAGES", "LANGUAGE_TITLE", "LANGUAGE_CONTINUE", "LANGUAGE_CANCEL"}
                                               for target in node.targets):
            if isinstance(node.value, (ast.Tuple, ast.List)):
                for value in node.value.elts:
                    keys.update(literals(value))
            else:
                keys.update(literals(node.value))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
        index = 1 if name == "translate" else 0
        if name not in {"translate", "t", "_t", "_set_status", "ValueError"} or len(node.args) <= index:
            continue
        argument = node.args[index]
        keys.update(literals(argument))
    return keys


class LocaleTests(unittest.TestCase):
    def test_language_choices_include_japanese_and_stable_ids(self):
        self.assertEqual((("English", "en"), ("한국어", "ko"), ("日本語", "ja")), LANGUAGES)

    def test_first_nonempty_locale_has_precedence_even_when_unsupported(self):
        cases = [({"LC_ALL": "ja_JP.UTF-8", "LC_MESSAGES": "ko_KR.UTF-8", "LANG": "en_US.UTF-8"}, "ja"),
                 ({"LC_ALL": "", "LC_MESSAGES": "ko-KR", "LANG": "ja_JP"}, "ko"),
                 ({"LC_ALL": " \t", "LC_MESSAGES": "", "LANG": "JA_jp.UTF-8@custom"}, "ja"),
                 ({"LC_ALL": "fr_FR.UTF-8", "LC_MESSAGES": "ja_JP", "LANG": "ko_KR"}, "en"),
                 ({"LC_ALL": "C.UTF-8", "LANG": "ko_KR"}, "en"), ({}, "en")]
        for environment, expected in cases:
            with self.subTest(environment=environment):
                before = dict(environment)
                self.assertEqual(expected, detect_language(environment))
                self.assertEqual(before, environment)

    def test_default_environment_and_unknown_language_fallback(self):
        with patch.dict(os.environ, {"LANG": "ja_JP.UTF-8"}, clear=True):
            self.assertEqual("ja", detect_language())
        self.assertEqual("Cancel", translate("unsupported", "Cancel"))


class CatalogTests(unittest.TestCase):
    def test_catalogs_are_nonempty_and_placeholders_match(self):
        self.assertGreater(len(MESSAGES), 100)
        self.assertEqual([], validate_catalogs())
        for source, versions in MESSAGES.items():
            values = {name: "__" + name + "__" for name in template_fields(source)}
            for language in ("en", "ko", "ja"):
                with self.subTest(source=source, language=language):
                    rendered = translate(language, source, **values)
                    for value in values.values():
                        self.assertIn(value, rendered)
            self.assertEqual(2, len(versions))

    def test_placeholder_control_detects_a_missing_field(self):
        source = "Setup could not finish. Details: {detail}"
        with patch.dict(MESSAGES, {source: ("상세 내용을 누락한 번역", "詳細：{detail}")}):
            self.assertTrue(any("placeholder mismatch (ko)" in issue for issue in validate_catalogs()))
        self.assertEqual({"value", "width"}, template_fields("Value: {value:{width}}"))

    def test_formatter_and_ui_literal_calls_have_both_translations(self):
        for relative in ("compose/corpus_setup.py", "compose/corpus_setup_ui.py"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            if relative.endswith("corpus_setup.py"):
                formatter = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "format_setup_result")
                source = ast.get_source_segment(source, formatter)
            keys = literal_translation_keys(source)
            self.assertGreater(len(keys), 10, f"no meaningful translation calls found in {relative}")
            missing = keys - MESSAGES.keys()
            self.assertEqual(set(), missing, f"untranslated literals in {relative}: {sorted(missing)}")

    def test_coverage_includes_conditional_statuses_and_stage_names(self):
        keys = literal_translation_keys('STAGES = ("First stage", "Second stage")\nself._set_status("Ready" if good else "Failed")\nself._t("Apply")')
        self.assertEqual({"First stage", "Second stage", "Ready", "Failed", "Apply"}, keys)

    def test_unknown_user_text_and_format_values_are_preserved(self):
        original = "My custom {instructions} — 日本語 / 한국어 / https://example.test/?q={raw}"
        for language in ("en", "ko", "ja"):
            self.assertEqual(original, translate(language, original))
            result = translate(language, "Setup could not finish. Details: {detail}", detail=original)
            self.assertIn(original, result)
        with self.assertRaises(KeyError):
            translate("ja", "Setup could not finish. Details: {detail}", wrong="value")
        with self.assertRaises(KeyError):
            translate("ko", "Setup could not finish. Details: {detail}")


class DisplayOwnershipTests(unittest.TestCase):
    def test_dynamic_source_scope_labels_have_explicit_translations(self):
        for scope in ("global", "project", "source"):
            self.assertIn(scope, MESSAGES)
            for language in ("ko", "ja"):
                self.assertNotEqual(scope, translate(language, scope))

    def test_dependency_display_translates_only_display_fields(self):
        row = {"id": "ui-rich", "title": "rich (included)", "version": "15.0.0", "status": "available",
               "role": "bundled UI dependency", "purpose": "Included in the Textual runtime; no separate installation is needed.",
               "path": "/tmp/原本 {file}/rich", "install_scope": "process-owned temporary directory",
               "install_argv": ["python", "--path", "/tmp/原本 {file}"], "manual_reason": ""}
        before = copy.deepcopy(row)
        for language in ("ko", "ja"):
            shown = dependency_display(language, row)
            self.assertNotEqual(row["title"], shown["title"])
            self.assertNotEqual(row["purpose"], shown["purpose"])
            for field in ("id", "version", "path", "install_argv"):
                self.assertEqual(row[field], shown[field])
            shown["install_argv"].append("changed only in display copy")
            self.assertEqual(before, row)

    def test_dependency_diagnostics_and_unknown_external_prose_stay_verbatim(self):
        prefix = "The shipped UI bundle is unavailable; verify or reinstall this agent-bios package."
        detail = " UI wheel SHA256 mismatch: /tmp/{raw}/textual.whl"
        row = {"id": "textual", "title": "Textual (included)", "manual_reason": prefix + detail}
        for language in ("ko", "ja"):
            shown = dependency_display(language, row)
            self.assertTrue(shown["manual_reason"].endswith(detail))
            self.assertFalse(shown["manual_reason"].startswith(prefix))
            custom = {"id": "external", "title": "My {external} helper", "purpose": "Project prose must stay as written."}
            self.assertEqual(custom, dependency_display(language, custom))

    def test_actual_first_party_dependency_fields_have_catalog_coverage(self):
        with tempfile.TemporaryDirectory() as home:
            rows = dependency_inventory(ROOT, {"HOME": home, "PATH": ""}, which=lambda *args, **kwargs: None)
        self.assertTrue(rows)
        untranslated = set()
        for row in rows:
            for field in ("title", "role", "status", "purpose", "manual_reason"):
                value = row.get(field, "")
                if not value or value in MESSAGES:
                    continue
                if field == "title" and row["id"].startswith("ui-") and value.endswith(" (included)"):
                    continue
                if field == "manual_reason" and re.fullmatch(r"Use the official installer, or install npm with Node\.js [0-9]+\+ and rerun setup\.", value):
                    for language in ("ko", "ja"):
                        self.assertNotEqual(value, dependency_display(language, row)[field])
                    continue
                untranslated.add(value)
        self.assertEqual(set(), untranslated)

    def test_supplied_domain_labels_translate_and_external_labels_remain_original(self):
        manifest = json.loads((ROOT / "compose/domains.json").read_text(encoding="utf-8"))
        for name, description in manifest["domains"].items():
            self.assertIn(description, MESSAGES)
            row = {"target": manifest["package_id"] + "/" + name}
            row["label"] = description + " (" + row["target"] + ")"
            before = dict(row)
            for language in ("ko", "ja"):
                shown = choice_label(language, row)
                self.assertNotIn(description, shown)
                self.assertIn(row["target"], shown)
                self.assertEqual(before, row)
        package = {"target": "@external/project", "label": "All content in @external/project"}
        self.assertIn("@external/project", choice_label("ja", package))
        external = {"target": "@external/project/custom", "label": "User {custom} prose (@external/project/custom)"}
        self.assertEqual(external["label"], choice_label("ko", external))

    def test_real_first_party_choice_labels_do_not_use_english_fallback(self):
        with tempfile.TemporaryDirectory() as home:
            rows = catalog_choices(CorpusInstaller(ROOT, {"HOME": home}))
            self.assertGreater(len(rows), 1)
            before = copy.deepcopy(rows)
            self.assertFalse(any(row["target"].startswith("@local/") for row in rows))
            for row in rows:
                for language in ("ko", "ja"):
                    with self.subTest(target=row["target"], language=language):
                        shown = choice_label(language, row)
                        self.assertNotEqual(row["label"], shown)
                        self.assertIn(row["target"], shown)
            self.assertEqual(before, rows)
            self.assertEqual([], list(Path(home).rglob("*")))

    def test_actual_old_node_guidance_has_no_english_fallback(self):
        from types import SimpleNamespace
        calls = []
        def which(name, **kwargs):
            return "/fixture/" + name if name in {"node", "npm"} else None
        def runner(argv, **kwargs):
            calls.append(argv)
            return SimpleNamespace(returncode=0, stdout="v20.1.0\n" if argv[0].endswith("node") else "11.0.0\n", stderr="")
        with tempfile.TemporaryDirectory() as home:
            rows = dependency_inventory(ROOT, {"HOME": home}, which=which, runner=runner, system="Linux")
        node = next(row for row in rows if row["id"] == "node")
        before = copy.deepcopy(node)
        self.assertEqual("missing", node["status"])
        self.assertIn(node["manual_reason"], MESSAGES)
        self.assertTrue(calls)
        self.assertTrue(all(call[1:] == ["--version"] for call in calls))
        for language in ("ko", "ja"):
            shown = dependency_display(language, node)
            self.assertNotEqual(node["manual_reason"], shown["manual_reason"])
            self.assertIn("Node.js 22", shown["manual_reason"])
            self.assertEqual(node["version"], shown["version"])
        self.assertEqual(before, node)

    def test_actual_unavailable_bundle_guidance_translates_around_exact_diagnostic(self):
        def no_process(*args, **kwargs):
            raise AssertionError("no discovered command may execute")
        with tempfile.TemporaryDirectory() as temporary:
            rows = dependency_inventory(Path(temporary) / "missing-package", {"HOME": temporary},
                                        which=lambda *args, **kwargs: None, runner=no_process, system="Linux")
        row = next(row for row in rows if row["id"] == "textual")
        before = copy.deepcopy(row)
        prefix = "The shipped UI bundle is unavailable; verify or reinstall this agent-bios package."
        reason = row["manual_reason"]
        self.assertEqual("missing", row["status"])
        self.assertTrue(reason.startswith(prefix))
        detail = reason[len(prefix):]
        self.assertIn("manifest is missing", detail)
        for language in ("ko", "ja"):
            shown = dependency_display(language, row)["manual_reason"]
            self.assertTrue(shown.startswith(translate(language, prefix)))
            self.assertTrue(shown.endswith(detail))
            self.assertNotEqual(reason, shown)
        self.assertEqual(before, row)


class LocalizedResultTests(unittest.TestCase):
    def test_conversation_results_keep_retry_and_management_out_of_the_tui(self):
        outcomes = [
            {"applied": False, "installation_error": "RAW DIAGNOSTIC"},
            {"applied": False, "dependency_failed": "jsonschema", "dependency_results": []},
            {"applied": False, "extras_error": "RAW DIAGNOSTIC", "installation_applied": True},
            {"applied": False, "cancelled": True, "cancelled_after_start": True, "dependency_results": []},
            {"applied": True, "plan": {"selection_mode": "none", "targets": []}},
        ]
        before = copy.deepcopy(outcomes)
        for result in outcomes:
            for language in ("en", "ko", "ja"):
                text = format_setup_result(result, language, interface="conversation")
                self.assertNotIn("agent-bios install", text)
                self.assertNotIn("agent-bios corpus (", text)
                if not result.get("applied"):
                    self.assertIn("agent-bios setup status", text)
                    self.assertIn("agent-bios setup resume", text)
                    self.assertIn("review_id", text)
                if "RAW DIAGNOSTIC" in result.values():
                    self.assertIn("RAW DIAGNOSTIC", text)
        self.assertEqual(before, outcomes)

    def test_localized_success_preserves_ids_commands_and_input_data(self):
        result = {"applied": True, "plan": {"selection_mode": "selected", "targets": ["@agent-bios/core/builder-base"]},
                  "dependency_results": [{"id": "jsonschema", "returncode": 0}],
                  "extras": {"app_bridge": {"registered": True}, "import": {"capture_id": "capture-{123}", "source_count": 2,
                             "next_command": "agent-bios import prompt 'capture-{123}'", "app_request": "Use $agent-bios to import capture capture-{123}"}}}
        before = copy.deepcopy(result)
        english = format_setup_result(result)
        for language in ("ko", "ja"):
            text = format_setup_result(result, language)
            self.assertNotEqual(english, text)
            for value in ("@agent-bios/core/builder-base", "jsonschema", "capture-{123}", "agent-bios import prompt 'capture-{123}'", "$agent-bios"):
                self.assertIn(value, text)
            self.assertNotIn("Model review is required", text)
            self.assertEqual(before, result)

    def test_cancellation_preview_and_partial_stop_report_real_outcomes(self):
        for language in ("ko", "ja"):
            cases = [({"cancelled": True}, "Setup cancelled. No installation changes were applied."),
                     ({"dry_run": True}, "Setup preview complete. No installation changes were applied."),
                     ({"cancelled": True, "cancelled_after_start": True, "installation_applied": True},
                      "The private runtime installation is retained; remaining setup was not applied."),
                     ({"cancelled": True, "cancelled_after_start": True}, "The private runtime installation was not applied."),
                     ({"applied": False}, "Setup did not complete.")]
            for result, message in cases:
                self.assertIn(translate(language, message), format_setup_result(result, language))

    def test_errors_keep_raw_diagnostics_and_do_not_become_success(self):
        detail = "E_LOCK_BUSY /tmp/{capture}/ユーザー — exact diagnostic"
        cases = [{"installation_error": detail, "dependency_results": [{"id": "codex", "returncode": 0}]},
                 {"extras_error": detail, "installation_applied": True, "extras": {"app_bridge": {"registered": True}}},
                 {"dependency_failed": "dependency-{id}", "dependency_results": [{"id": "jsonschema", "returncode": 0}]}]
        for language in ("ko", "ja"):
            for result in cases:
                before = copy.deepcopy(result)
                text = format_setup_result(result, language)
                self.assertNotIn(translate(language, "Setup complete. Private runtime installed."), text)
                self.assertIn("dependency-{id}" if "dependency_failed" in result else detail, text)
                self.assertEqual(before, result)

    def test_existing_registration_warning_and_external_request_are_preserved(self):
        warning = "Preserving changed /tmp/{raw}/SKILL.md"
        request = "External request {keep this verbatim}"
        result = {"applied": True, "plan": {"selection_mode": None},
                  "installation": {"app_bridge": {"registered": True, "needs_action": [warning]}},
                  "extras": {"import": {"capture_id": "C1", "app_request": request}}}
        for language in ("ko", "ja"):
            text = format_setup_result(result, language)
            self.assertIn(translate(language, "Setup complete. Private runtime installed."), text)
            self.assertIn(translate(language, "Codex app bridge needs attention; existing files were preserved:"), text)
            self.assertIn(warning, text)
            self.assertIn(request, text)

    def test_all_selection_modes_have_localized_outcomes(self):
        plans = [{"selection_mode": "none", "targets": []}, {"selection_mode": "selected", "targets": ["all"]},
                 {"selection_mode": "default", "targets": []}, {"selection_mode": "default", "targets": ["@core/example"]},
                 {"selection_mode": None, "targets": None}]
        for plan in plans:
            result = {"applied": True, "plan": plan}
            english = format_setup_result(result)
            for language in ("ko", "ja"):
                self.assertNotEqual(english, format_setup_result(result, language))


if __name__ == "__main__":
    unittest.main()
