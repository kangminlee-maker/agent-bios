"""Temp-home checks for explicit empty and exact corpus installation choices."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import corpus_catalog
from corpus_install import CorpusInstaller, InstallError
from corpus_store import CorpusStore, ValidationError, verify_snapshot
from corpus_setup import run_setup


SOURCE = Path(__file__).resolve().parents[1]


class ChoiceCatalog:
    normalize_content = staticmethod(corpus_catalog.normalize_content)
    update_content = staticmethod(corpus_catalog.update_content)
    compile_items = staticmethod(corpus_catalog.compile_items)

    @staticmethod
    def load_catalog(_repo):
        def item(package, name, tier, domains):
            body = f"Instruction for {name}."
            return {"ref": f"{package}:{name}", "package_id": package, "item_id": name,
                    "title": name, "body": body, "surface": "always", "tier": tier,
                    "domains": domains, "kind": "rule", "members": {"rule.md": body},
                    "primary_member": "rule.md", "origin": {"kind": "installed"}}
        return {"schema_version": 1,
                "packages": [{"package_id": "@fixture/base", "domains": {"coding": "Coding", "office": "Office"}},
                             {"package_id": "@fixture/other", "domains": {"coding": "Other coding"}}],
                "items": [item("@fixture/base", "core", "core", []),
                          item("@fixture/base", "infra", "infra", []),
                          item("@fixture/base", "coding", "domain", ["coding"]),
                          item("@fixture/base", "office", "domain", ["office"]),
                          item("@fixture/other", "other-core", "core", []),
                          item("@fixture/other", "other-coding", "domain", ["coding"])]}


class StoreChoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        (self.repo / "compose/bootstrap").mkdir(parents=True)
        (self.repo / "compose/bootstrap/SKILL.md").write_text("# Corpus management\n", encoding="utf-8")
        (self.repo / "compose/corpus_catalog.py").write_text("# Fixture compiler identity\n", encoding="utf-8")
        self.store = CorpusStore(self.repo, self.root / "state", self.root / "user")
        self.store._catalog_module = lambda: ChoiceCatalog

    def tearDown(self):
        self.temp.cleanup()

    def apply(self, payload):
        plan = self.store.plan(payload)
        return self.store.apply(plan["plan_id"], plan["expected_revision"])

    def test_none_has_no_rules_no_personal_no_enabled_override_and_no_bootstrap(self):
        self.store.install(["all"])
        local = self.apply({"operation": "create", "item": {"title": "Personal", "body": "Personal rule", "surface": "always"}})["details"]["ref"]
        self.apply({"operation": "enable", "items": {"@fixture/base:coding": True, local: True}})
        before = self.store.snapshot("codex")
        before_inventory = copy.deepcopy(self.store.snapshot_inventory(before["content_ref"]))
        for host in ("claude", "codex"):
            with self.subTest(host=host):
                empty = self.store.snapshot(host, selection_mode="none")
                self.assertEqual([], empty["item_refs"])
                self.assertEqual("", empty["instruction_text"])
                self.assertEqual({}, empty["assets"])
                path = Path(empty["path"])
                self.assertFalse((path / "bootstrap").exists())
                self.assertEqual("", (path / "launch-content/instructions.md").read_text(encoding="utf-8"))
                checked = verify_snapshot(path, empty["content_ref"])
                self.assertEqual([], checked["items"])
                preview = self.store.snapshot(host, selection_mode="none", dry_run=True)
                self.assertEqual(empty["content_ref"], preview["content_ref"])
        self.assertEqual(before_inventory, self.store.snapshot_inventory(before["content_ref"]))
        self.assertIn(local, self.store.snapshot("codex")["item_refs"])

    def test_exact_domain_package_and_item_exclude_unrelated_core_and_true_overrides(self):
        self.store.install(["all"])
        self.apply({"operation": "enable", "items": {"@fixture/other:other-core": True, "@fixture/base:office": True}})
        cases = [(["@fixture/base/coding"], {"@fixture/base:coding"}),
                 (["@fixture/base:coding"], {"@fixture/base:coding"}),
                 (["@fixture/base"], {"@fixture/base:core", "@fixture/base:infra", "@fixture/base:coding", "@fixture/base:office"})]
        for selection, expected in cases:
            with self.subTest(selection=selection):
                for host in ("claude", "codex"):
                    result = self.store.snapshot(host, selection=selection, selection_mode="selected")
                    self.assertEqual(expected, set(result["item_refs"]))

    def test_default_keeps_implicit_core_infra_and_local_items(self):
        self.store.install([])
        local = self.apply({"operation": "create", "item": {"title": "Personal", "body": "Personal rule"}})["details"]["ref"]
        result = self.store.snapshot("codex")
        self.assertEqual({"@fixture/base:core", "@fixture/base:infra", "@fixture/other:other-core", local}, set(result["item_refs"]))
        self.assertTrue((Path(result["path"]) / "bootstrap/SKILL.md").is_file())

    def test_explicit_install_replaces_saved_mode_targets_and_enablement(self):
        self.store.install(["all"])
        self.apply({"operation": "select", "selection": ["@fixture/other"], "selection_mode": "selected"})
        self.apply({"operation": "enable", "items": {"@fixture/base:coding": False, "@fixture/other:other-core": True}})
        self.store.install(["@fixture/base/coding"], selection_mode="selected", replace_selection=True)
        self.assertEqual(["@fixture/base:coding"], self.store.snapshot("codex")["item_refs"])
        self.assertEqual({}, self.store.status()["enabled_overrides"])
        self.store.install([], selection_mode="none", replace_selection=True)
        self.assertEqual([], self.store.snapshot("codex")["item_refs"])

    def test_snapshot_mode_override_does_not_change_saved_user_selection(self):
        self.store.install(["@fixture/base/coding"], selection_mode="selected", replace_selection=True)
        before = self.store.status()
        self.store.snapshot("codex", selection_mode="none")
        self.assertEqual(before, self.store.status())
        self.assertEqual(["@fixture/base:coding"], self.store.snapshot("codex")["item_refs"])

    def test_explicit_snapshot_selection_can_opt_in_from_saved_none_without_persisting(self):
        self.store.install([], selection_mode="none", replace_selection=True)
        before = self.store.status()
        selected = self.store.snapshot("codex", selection=["@fixture/base/coding"])
        self.assertEqual("default", selected["selection_mode"])
        self.assertIn("@fixture/base:coding", selected["item_refs"])
        self.assertIn("@fixture/base:core", selected["item_refs"])
        self.assertNotIn("@fixture/base:office", selected["item_refs"])
        self.assertEqual(before, self.store.status())
        self.assertEqual("", self.store.snapshot("codex")["instruction_text"])
        explicit_off = self.store.snapshot("codex", selection=["@fixture/base/coding"], selection_mode="none")
        self.assertEqual("", explicit_off["instruction_text"])
        self.assertEqual([], explicit_off["item_refs"])

    def test_selected_respects_explicit_false_override(self):
        self.store.install(["@fixture/base/coding"], selection_mode="selected", replace_selection=True)
        self.apply({"operation": "enable", "items": {"@fixture/base:coding": False}})
        self.assertEqual([], self.store.snapshot("codex")["item_refs"])

    def test_invalid_modes_and_none_with_targets_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.store.install(["all"], selection_mode="none")
        with self.assertRaises(ValidationError):
            self.store.install([], selection_mode="guess")


class InstallerChoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "package"
        shutil.copytree(SOURCE / "claude", self.repo / "claude")
        files = ["compose/assemble.py", "compose/corpus_catalog.py", "compose/corpus_store.py", "compose/corpus_transaction.py", "compose/pkgid.py",
                 "compose/domains.json", "learn/learning.schema.json", "launch/agent-launch.py", "launch/agent-launch.toml"]
        for relative in files:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / relative, target)
        shutil.copytree(SOURCE / "launch/i18n", self.repo / "launch/i18n")
        shutil.copytree(SOURCE / "compose/bootstrap", self.repo / "compose/bootstrap")
        (self.repo / "package.json").write_text(json.dumps({"files": files + ["claude/", "launch/i18n", "compose/bootstrap/"]}), encoding="utf-8")
        self.home, self.state, self.user = self.root / "home", self.root / "state", self.root / "user"
        self.env = {"HOME": str(self.home), "AGENT_BIOS_STATE_DIR": str(self.state), "AGENT_BIOS_CORPUS_DIR": str(self.user),
                    "CLAUDE_CONFIG_DIR": str(self.home / ".claude"), "CODEX_HOME": str(self.home / ".codex")}
        self.installer = CorpusInstaller(self.repo, self.env)

    def tearDown(self):
        self.temp.cleanup()

    def store(self):
        return self.installer._store(Path(self.installer.status()["package_root"]))

    def test_store_binds_one_catalog_module_per_immutable_release_instance(self):
        from unittest import mock
        with mock.patch.object(self.installer, "_private_module", wraps=self.installer._private_module) as load:
            store = self.installer._store(self.repo)
            catalog = store._catalog_module()
            self.assertIs(catalog, store._catalog_module())
            self.assertIs(catalog, store._catalog_module())
        catalog_calls = [call for call in load.call_args_list if call.args[1] == "corpus_catalog"]
        self.assertEqual(1, len(catalog_calls))

    def apply(self, payload):
        store = self.store()
        plan = store.plan(payload)
        return store.apply(plan["plan_id"], plan["expected_revision"])

    def test_no_corpus_install_and_plain_update_preserve_native_sources(self):
        originals = {}
        for relative in (".claude/CLAUDE.md", ".codex/AGENTS.md", "project/AGENTS.md", "project/CLAUDE.md"):
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("native " + relative + "\n").encode())
            originals[path] = path.read_bytes()
        preview = self.installer.install(dry_run=True, selection_mode="none", targets=[])
        self.assertEqual("none", preview["selection_mode"])
        self.assertFalse(self.state.exists())
        self.installer.install(selection_mode="none", targets=[])
        self.assertTrue(self.installer.verify()["stored"])
        self.assertEqual([], self.store().snapshot("codex")["item_refs"])
        updated = self.installer.install()
        self.assertEqual("none", updated["record"]["selection_mode"])
        self.assertEqual([], self.store().snapshot("claude")["item_refs"])
        self.assertEqual(originals, {path: path.read_bytes() for path in originals})

    def test_explicit_targets_replace_prior_authoring_selection_then_update_preserves_choices(self):
        self.installer.install(selection_mode="selected", targets=["@agent-bios/core"])
        refs = {row["ref"] for row in self.store().list_items() if row.get("tier") == "core"}
        self.assertTrue(refs)
        unwanted = sorted(refs)[0]
        self.apply({"operation": "enable", "items": {unwanted: True}})
        self.installer.install(selection_mode="selected", targets=["@agent-bios/core/builder-base"])
        selected = self.store().snapshot("codex")["item_refs"]
        self.assertTrue(selected)
        self.assertNotIn(unwanted, selected)
        self.assertEqual({}, self.store().status()["enabled_overrides"])
        disabled = selected[0]
        self.apply({"operation": "enable", "items": {disabled: False}})
        before = self.store().snapshot("codex")["item_refs"]
        self.installer.install()
        self.assertEqual(before, self.store().snapshot("codex")["item_refs"])
        self.assertEqual({disabled: False}, self.store().status()["enabled_overrides"])

    def test_explicit_legacy_domains_replaces_saved_none_and_plain_update_preserves_it(self):
        self.installer.install(selection_mode="none", targets=[])
        installed = self.installer.install("builder-base")
        self.assertEqual("default", installed["record"]["selection_mode"])
        store = self.store()
        self.assertEqual("default", store.status()["selection_mode"])
        self.assertIn("@agent-bios/core/builder-base", store.status()["selection"])
        snapshot = store.snapshot("codex")
        self.assertTrue(snapshot["item_refs"])
        catalog = self.installer.setup_catalog()
        domain_refs = {item["ref"] for item in catalog["items"]
                       if item["tier"] == "domain" and "builder-base" in item["domains"]}
        self.assertTrue(domain_refs)
        self.assertTrue(domain_refs.intersection(snapshot["item_refs"]))
        self.installer.install()
        self.assertEqual("default", self.store().status()["selection_mode"])
        self.assertEqual(snapshot["item_refs"], self.store().snapshot("codex")["item_refs"])

    def test_launcher_explicit_domain_can_opt_in_from_saved_none_for_one_launch(self):
        from test_corpus_launch_consistency import launcher
        self.installer.install(selection_mode="none", targets=[])
        store = self.store()
        before = store.status()
        config = self.installer.launch_root / "profiles.toml"
        generation = launcher._corpus_generation(self.state, config)
        snapshot = launcher._snapshot_from_config(store, config, generation, "codex",
                                                  ["@agent-bios/core/builder-base"], dry_run=False, native=False)
        self.assertTrue(snapshot["item_refs"])
        self.assertTrue(snapshot["instruction_text"])
        self.assertEqual("default", snapshot["selection_mode"])
        self.assertEqual(before, store.status())
        self.assertEqual("", store.snapshot("codex")["instruction_text"])

    def test_none_resets_existing_local_selection_and_true_overrides(self):
        self.installer.install(selection_mode="selected", targets=["all"])
        local = self.apply({"operation": "create", "item": {"title": "Personal", "body": "Personal rule", "surface": "always"}})["details"]["ref"]
        self.apply({"operation": "enable", "items": {local: True}})
        self.assertIn(local, self.store().snapshot("codex")["item_refs"])
        self.installer.install(selection_mode="none", targets=[])
        self.assertEqual([], self.store().snapshot("codex")["item_refs"])
        self.assertEqual({}, self.store().status()["enabled_overrides"])
        self.assertEqual("Personal rule", self.store().show(local)["item"]["body"])

    def test_exact_item_target_and_invalid_selection_preview(self):
        catalog = self.installer.setup_catalog()
        ref = next(row["ref"] for row in catalog["items"] if row["tier"] == "domain")
        self.installer.install(selection_mode="selected", targets=[ref])
        self.assertEqual([ref], self.store().snapshot("claude")["item_refs"])
        for kwargs in ({"selection_mode": "none", "targets": [ref]}, {"selection_mode": "selected", "targets": []},
                       {"selection_mode": "selected", "targets": ["@missing/package"]}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(InstallError):
                    self.installer.install(dry_run=True, **kwargs)

    def test_existing_personal_item_can_be_an_exact_install_target(self):
        self.installer.install(selection_mode="none", targets=[])
        ref = self.apply({"operation": "create", "item": {"title": "Personal selection", "body": "Use this personal rule.",
                         "surface": "always"}})["details"]["ref"]
        self.assertTrue(self.installer.install(dry_run=True, selection_mode="selected", targets=[ref])["dry_run"])
        self.assertEqual("none", self.store().status()["selection_mode"])
        self.installer.install(selection_mode="selected", targets=[ref])
        for host in ("claude", "codex"):
            self.assertEqual([ref], self.store().snapshot(host)["item_refs"])
        self.installer.install()
        self.assertEqual([ref], self.store().snapshot("codex")["item_refs"])

    def test_wizard_catalog_can_select_personal_corpus_before_first_import(self):
        from corpus_setup import catalog_choices
        choices = catalog_choices(self.installer)
        self.assertIn("@local/personal", [choice["target"] for choice in choices])
        self.installer.install(selection_mode="selected", targets=["@local/personal"])
        ref = self.apply({"operation": "create", "item": {"title": "Personal-only", "body": "Personal-only corpus body", "surface": "always"}})["details"]["ref"]
        self.assertEqual([ref], self.store().snapshot("codex")["item_refs"])

    def test_exact_learning_target_is_valid_but_only_delivered_to_its_host(self):
        self.installer.install(selection_mode="none", targets=[])
        learning_id = "11111111-1111-4111-8111-111111111111"
        self.store().capture_learning("codex", {
            "schema_version": 1, "learning_id": learning_id,
            "lesson": "CODEX_ONLY_LEARNING_SCOPE", "domain": "unclassified",
            "created": "2026-09-12T00:00:00Z", "supporting_sessions": ["codex:abcd1234"],
        })
        ref = "@local/learnings-codex:" + learning_id
        self.installer.install(selection_mode="selected", targets=[ref])
        self.assertEqual([ref], self.store().snapshot("codex")["item_refs"])
        claude = self.store().snapshot("claude")
        self.assertEqual([], claude["item_refs"])
        self.assertNotIn("CODEX_ONLY_LEARNING_SCOPE", claude["instruction_text"])
        self.installer.install()
        self.assertEqual([ref], self.store().snapshot("codex")["item_refs"])

    def test_wizard_keep_choice_preserves_saved_mode_and_user_enablement(self):
        self.installer.install(selection_mode="selected", targets=["@agent-bios/core/builder-base"])
        selected = self.store().snapshot("codex")["item_refs"]
        self.assertTrue(selected)
        self.apply({"operation": "enable", "items": {selected[0]: False}})
        before = self.store().status()
        answers = iter(["none", "4", "n", "skip", "apply"])
        result = run_setup(self.installer, input_fn=lambda _: next(answers), output_stream=io.StringIO(), inventory=[])
        self.assertTrue(result["applied"])
        after = self.store().status()
        self.assertEqual(before["selection"], after["selection"])
        self.assertEqual(before["selection_mode"], after["selection_mode"])
        self.assertEqual(before["enabled_overrides"], after["enabled_overrides"])


if __name__ == "__main__":
    unittest.main()
