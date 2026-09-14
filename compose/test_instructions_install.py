"""Real temp-home checks for private installation and legacy migration."""
from __future__ import annotations

import json
import instructions_install
import shutil
from pathlib import Path
import tempfile
import unittest

from instructions_install import InstructionsInstaller, InstallError
from instructions_transaction import TransactionPendingError, confirmed_release, guard_pending


SOURCE = Path(__file__).resolve().parent.parent


class InstructionsInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "package"
        self.home = root / "home"
        self.state = root / "state"
        self.user = root / "user"
        for name in ("claude",):
            shutil.copytree(SOURCE / name, self.repo / name)
        for relative in ("compose/assemble.py", "compose/instructions_catalog.py", "compose/instructions_store.py", "compose/instructions_transaction.py", "compose/pkgid.py",
                         "compose/domains.json", "learn/learning.schema.json", "launch/agent-launch.py", "launch/agent-launch.toml"):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / relative, target)
        shutil.copytree(SOURCE / "launch" / "i18n", self.repo / "launch" / "i18n")
        shutil.copytree(SOURCE / "compose" / "bootstrap", self.repo / "compose" / "bootstrap")
        (self.repo / "package.json").write_text(json.dumps({"files": [
            "claude/", "compose/assemble.py", "compose/instructions_catalog.py", "compose/instructions_store.py", "compose/instructions_transaction.py", "compose/pkgid.py",
            "compose/domains.json", "compose/bootstrap/", "learn/learning.schema.json",
            "launch/agent-launch.py", "launch/agent-launch.toml", "launch/i18n",
        ]}), encoding="utf-8")
        self.claude = self.home / ".claude"
        self.codex = self.home / ".codex"
        self.env = {"HOME": str(self.home), "AGENT_BIOS_STATE_DIR": str(self.state),
                    "AGENT_BIOS_INSTRUCTIONS_DIR": str(self.user), "CLAUDE_CONFIG_DIR": str(self.claude),
                    "CODEX_HOME": str(self.codex), "ZDOTDIR": str(self.home)}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def installer(self) -> InstructionsInstaller:
        return InstructionsInstaller(self.repo, self.env)

    def test_private_install_verify_and_uninstall_do_not_touch_native_homes(self) -> None:
        self.claude.mkdir(parents=True)
        self.codex.mkdir(parents=True)
        (self.claude / "CLAUDE.md").write_text("my native Claude instructions\n", encoding="utf-8")
        (self.codex / "AGENTS.md").write_text("my native Codex instructions\n", encoding="utf-8")
        local = self.home / ".config" / "agent-launch" / "presets.local.toml"
        local.parent.mkdir(parents=True)
        local.write_text("[mine]\n", encoding="utf-8")
        before = {(self.claude / "CLAUDE.md"): (self.claude / "CLAUDE.md").read_bytes(),
                  (self.codex / "AGENTS.md"): (self.codex / "AGENTS.md").read_bytes(), local: local.read_bytes()}
        result = self.installer().install("builder-base")
        self.assertTrue(result["stored"])
        self.assertEqual("unverified", result["activation"])
        for path, content in before.items():
            self.assertEqual(content, path.read_bytes())
        launcher = self.home / ".local" / "bin" / "agent-launch"
        self.assertIn("AGENT_BIOS_PRIVATE_INSTRUCTIONS=1", launcher.read_text(encoding="utf-8"))
        self.assertIn("AGENT_BIOS_PACKAGE_ROOT", launcher.read_text(encoding="utf-8"))
        verified = self.installer().verify()
        self.assertTrue(verified["stored"])
        self.assertEqual("unverified", verified["activation"])
        (self.user / "packages" / "local").mkdir(parents=True)
        (self.user / "packages" / "local" / "kept.md").write_text("personal", encoding="utf-8")
        pin = self.state / "sessions" / "pins" / "codex" / "session.json"
        pin.parent.mkdir(parents=True)
        pin.write_text("{}", encoding="utf-8")
        removed = self.installer().uninstall()
        self.assertIn(str(launcher), removed["removed"])
        self.assertTrue((self.user / "packages" / "local" / "kept.md").is_file())
        self.assertTrue(pin.is_file())
        self.assertFalse(launcher.exists())
        self.assertEqual(b"[mine]\n", local.read_bytes())

    def test_dry_run_writes_nothing(self) -> None:
        result = self.installer().install("builder-base", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(self.state.exists())
        self.assertFalse(self.user.exists())
        self.assertFalse((self.home / ".local" / "bin" / "agent-launch").exists())

    def test_none_selects_core_only_and_noop_install_keeps_saved_selection(self) -> None:
        installed = self.installer().install("none")
        self.assertEqual([], installed["record"]["selection"])
        projection = json.loads((self.state / "corpus-status.json").read_text(encoding="utf-8"))
        self.assertEqual([], projection["domains"]["applied"])
        updated = self.installer().install()
        self.assertEqual([], updated["record"]["selection"])
        with self.assertRaises(InstallError):
            self.installer().install("none,builder-base")

    def test_install_refuses_owned_path_conflict_before_source_publication(self) -> None:
        conflict = self.home / ".local" / "bin" / "agent-launch"
        conflict.parent.mkdir(parents=True)
        conflict.write_text("user launcher\n", encoding="utf-8")
        with self.assertRaises(InstallError):
            self.installer().install("builder-base")
        self.assertFalse((self.state / "runtime" / "private-install.json").exists())
        runtime = self.state / "runtime" / "state.json"
        self.assertFalse(runtime.exists())
        self.assertEqual("user launcher\n", conflict.read_text(encoding="utf-8"))

    def test_interrupted_install_blocks_readers_then_replays_exact_candidate(self) -> None:
        installer = self.installer()
        original = installer._write_planned
        calls = 0

        def fail_once(path, version, mode):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("injected projection interruption")
            return original(path, version, mode)

        installer._write_planned = fail_once  # type: ignore[method-assign]
        with self.assertRaises(OSError):
            installer.install("builder-base")
        with self.assertRaises(TransactionPendingError):
            guard_pending(self.state)
        with self.assertRaises(TransactionPendingError):
            confirmed_release(self.state)
        result = self.installer().install("builder-base")
        self.assertTrue(result["stored"])
        journals = list((self.state / "runtime" / "installer-transactions").glob("*/journal.json"))
        self.assertTrue(journals)
        self.assertIn("COMMITTED", {json.loads(path.read_text(encoding="utf-8"))["state"] for path in journals})
        self.assertTrue(all(json.loads(path.read_text(encoding="utf-8"))["state"] in {"COMMITTED", "SUPERSEDED"}
                            for path in journals))
        self.installer().verify()
        self.assertTrue(confirmed_release(self.state).is_dir())

    def test_interrupted_reset_replays_and_never_archives_token_bytes(self) -> None:
        self.installer().install("builder-base")
        local = self.home / ".config" / "agent-launch" / "presets.local.toml"
        local.write_text("[personal]\n", encoding="utf-8")
        token = self.home / ".config" / "agent-bios" / "token"
        token.parent.mkdir(parents=True)
        secret = "reset-interruption-token"
        token.write_text(secret, encoding="utf-8")
        installer = self.installer()
        original = instructions_install._atomic_json
        tripped = False
        def fail_after_source(path, value):
            nonlocal tripped
            if (not tripped and "resets" in str(path) and isinstance(value, dict)
                    and value.get("phase") == "projections"):
                tripped = True
                raise OSError("injected post-source boundary")
            return original(path, value)
        instructions_install._atomic_json = fail_after_source  # type: ignore[assignment]
        preview = installer.reset()
        try:
            with self.assertRaises(OSError):
                installer.reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        finally:
            instructions_install._atomic_json = original  # type: ignore[assignment]
        with self.assertRaises(TransactionPendingError):
            guard_pending(self.state)
        token.write_text("replacement-token", encoding="utf-8")
        with self.assertRaises(InstallError):
            self.installer().reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        self.assertEqual("replacement-token", token.read_text(encoding="utf-8"))
        # Explicitly accepting a fresh preview may supersede the stale reset.
        fresh = self.installer().reset()
        # Retrying the accepted generation resumes it and returns that result;
        # it does not silently begin a second reset.
        self.installer().reset(apply=True, yes=True, expected_revision=fresh["expected_revision"])
        journals = list((self.state / "runtime" / "resets").glob("*/journal.json"))
        self.assertTrue(journals)
        self.assertIn("COMMITTED", {json.loads(path.read_text(encoding="utf-8"))["state"] for path in journals})
        self.assertTrue(all(json.loads(path.read_text(encoding="utf-8"))["state"] in {"COMMITTED", "SUPERSEDED"}
                            for path in journals))
        self.assertFalse(token.exists())
        self.assertNotIn(secret, "\n".join(path.read_text(encoding="utf-8") for path in journals))
        self.installer().verify()

    def test_reset_preview_detects_formerly_absent_local_file_before_writes(self) -> None:
        self.installer().install("builder-base")
        preview = self.installer().reset()
        added = self.home / ".config" / "agent-launch" / "review-methods.local.toml"
        added.write_text("[personal]\n", encoding="utf-8")
        with self.assertRaises(InstallError):
            self.installer().reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        self.assertEqual("[personal]\n", added.read_text(encoding="utf-8"))

    def test_reset_preview_generation_is_stable_across_clock_change(self) -> None:
        self.installer().install("builder-base")
        preview = self.installer().reset()
        original = instructions_install.time.time
        instructions_install.time.time = lambda: original() + 10  # type: ignore[assignment]
        try:
            result = self.installer().reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        finally:
            instructions_install.time.time = original  # type: ignore[assignment]
        self.assertFalse(result["preview"])

    def test_reset_replay_completes_after_token_delete_before_commit_receipt(self) -> None:
        self.installer().install("builder-base")
        token = self.home / ".config" / "agent-bios" / "token"; token.parent.mkdir(parents=True)
        token.write_text("original-token", encoding="utf-8")
        installer = self.installer(); preview = installer.reset(); original = instructions_install._atomic_json; tripped = False
        def fail_commit(path, value):
            nonlocal tripped
            if not tripped and "resets" in str(path) and isinstance(value, dict) and value.get("state") == "COMMITTED":
                tripped = True; raise OSError("injected commit receipt loss")
            return original(path, value)
        instructions_install._atomic_json = fail_commit  # type: ignore[assignment]
        try:
            with self.assertRaises(OSError):
                installer.reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        finally:
            instructions_install._atomic_json = original  # type: ignore[assignment]
        self.assertFalse(token.exists())
        recovered = self.installer().reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        self.assertTrue(recovered["recovered"])

    def test_reset_preview_detects_new_learning_event(self) -> None:
        self.installer().install("builder-base")
        preview = self.installer().reset()
        events = self.user / "learnings" / "codex" / "events.jsonl"; events.parent.mkdir(parents=True)
        events.write_text('{"learning_id":"new-event"}\n', encoding="utf-8")
        with self.assertRaises(InstallError):
            self.installer().reset(apply=True, yes=True, expected_revision=preview["expected_revision"])

    def test_forged_record_cannot_claim_foreign_file_with_matching_bytes(self) -> None:
        self.installer().install("builder-base")
        record_path = self.state / "runtime" / "private-install.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        launcher = self.home / ".local" / "bin" / "agent-launch"
        foreign = self.home / "foreign" / "agent-launch"
        foreign.parent.mkdir(parents=True)
        foreign.write_bytes(launcher.read_bytes())
        record["launcher"] = {"path": str(foreign), "sha256": record["launcher"]["sha256"]}
        record_path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(InstallError):
            self.installer().verify()
        with self.assertRaises(InstallError):
            self.installer().uninstall()
        self.assertTrue(foreign.is_file())

    def test_reset_rewinds_private_authoring_without_removing_sessions(self) -> None:
        self.installer().install("builder-base")
        sessions = self.state / "sessions" / "snapshots" / "retained"
        sessions.mkdir(parents=True)
        (sessions / "note").write_text("keep", encoding="utf-8")
        local = self.home / ".config" / "agent-launch" / "presets.local.toml"
        local.write_text("[personal]\n", encoding="utf-8")
        connections = self.home / ".config" / "agent-bios"
        connections.mkdir(parents=True)
        (connections / "ingest-url").write_text("https://example.test\n", encoding="utf-8")
        secret = "do-not-archive-this-token"
        (connections / "token").write_text(secret, encoding="utf-8")
        event = self.user / "learnings" / "codex" / "events.jsonl"
        event.parent.mkdir(parents=True)
        event.write_text('{"schema_version":1,"learning_id":"44444444-4444-4444-8444-444444444444","lesson":"retained lesson","domain":"builder-base","created":"2026-09-07T12:00:00+00:00","supporting_sessions":["codex:abcde"]}\n', encoding="utf-8")
        # The installer owns only the active unlock generation, not the
        # immutable learning-session history beside it. Award validity itself
        # is covered by the native-provenance tests, not by this reset fixture.
        understand = self.user / "understand"
        (understand / "sessions").mkdir(parents=True)
        generation = understand / "state.json"
        generation.write_text(json.dumps({"schema_version": 1, "generation": "a" * 32,
                                          "awards": {"fixture": {"note_ref": "@local/personal:fixture"}}}))
        (understand / "sessions" / "retained.json").write_text('{"fixture":"retained provenance"}')
        original_generation = generation.read_bytes()
        preview = self.installer().reset()
        self.assertTrue(preview["preview"])
        self.assertTrue(local.is_file())
        self.assertIn(str(generation), preview["archive"])
        self.assertEqual(original_generation, generation.read_bytes())
        reset = self.installer().reset(apply=True, yes=True, expected_revision=preview["expected_revision"])
        self.assertFalse(reset["preview"])
        self.assertTrue((sessions / "note").is_file())
        self.assertTrue(event.is_file())
        self.assertFalse(local.exists())
        self.assertTrue((self.home / ".config" / "agent-launch" / "profiles.toml").is_file())
        self.assertFalse((connections / "ingest-url").exists())
        self.assertFalse((connections / "token").exists())
        archive = Path(reset["archive"])
        self.assertFalse(generation.exists())
        self.assertEqual(original_generation, (archive / "state.json").read_bytes())
        self.assertTrue((understand / "sessions" / "retained.json").is_file())
        self.assertTrue((archive / "presets.local.toml").is_file())
        self.assertTrue((archive / "ingest-url").is_file())
        retained_text = "\n".join(path.read_text(encoding="utf-8") for path in archive.rglob("*") if path.is_file())
        journals = "\n".join(path.read_text(encoding="utf-8") for path in (self.state / "runtime" / "resets").rglob("*.json"))
        self.assertNotIn(secret, retained_text)
        self.assertNotIn(secret, journals)
        self.assertNotIn(secret, json.dumps(reset))
        self.installer().verify()

    def test_migration_previews_then_moves_events_before_removing_owned_projections(self) -> None:
        self.claude.mkdir(parents=True)
        self.codex.mkdir(parents=True)
        (self.claude / "CLAUDE.md").write_text(
            "# User\n@central/bundle.md\n@personal/learnings.md\nKeep this.\n", encoding="utf-8")
        (self.claude / "personal").mkdir()
        record = {"schema_version": 1, "learning_id": "11111111-1111-4111-8111-111111111111",
                  "lesson": "keep this learning", "domain": "builder-base",
                  "created": "2026-09-07T12:00:00+00:00", "supporting_sessions": ["claude:abcde"]}
        raw_record = json.dumps(record, ensure_ascii=False, separators=(",", ": "))
        (self.claude / "personal" / "learnings.jsonl").write_text(raw_record + "\n", encoding="utf-8")
        (self.claude / "personal" / "learnings.md").write_text("- old projection\n", encoding="utf-8")
        (self.codex / "AGENTS.md").write_text(
            "before\n" + "<!-- agent-bios:central:start -->\nold central\n<!-- agent-bios:central:end -->\n" +
            "outside\n" + "<!-- agent-bios:personal-learnings:start -->\nold learning\n<!-- agent-bios:personal-learnings:end -->\n" +
            "after\n", encoding="utf-8")
        (self.codex / "personal").mkdir()
        (self.codex / "personal" / "learnings.jsonl").write_text(
            json.dumps({"schema_version": 1, "learning_id": "22222222-2222-4222-8222-222222222222",
                        "lesson": "codex learning", "domain": "builder-base", "created": "2026-09-07T12:00:00+00:00",
                        "supporting_sessions": ["codex:abcde"]}, separators=(",", ": ")) + "\n",
            encoding="utf-8")
        (self.claude / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [
            {"command": str(self.claude / "central" / "hooks" / "tooling-gotchas-hook.py")}
        ]}]}}, indent=2), encoding="utf-8")
        (self.codex / "config.toml").write_text(
            "[features]\nmulti_agent = true  # agent-bios\n# >>> agent-bios additions >>>\n"
            "[agents.frontier]\ndescription = \"old\"\n# <<< agent-bios additions <<<\n", encoding="utf-8")
        legacy = self.claude / "central" / "bundle.md"
        legacy.parent.mkdir()
        legacy.write_text("old", encoding="utf-8")
        self.state.mkdir(parents=True)
        (self.state / "manifest.txt").write_text(str(legacy) + "\n", encoding="utf-8")
        preview = self.installer().migrate()
        self.assertTrue(preview["preview"])
        self.assertTrue(legacy.exists())
        self.assertIn("@central/bundle.md", (self.claude / "CLAUDE.md").read_text(encoding="utf-8"))
        # Keep this fixture focused on migration's event contract. The public
        # installer selection is already covered above with --domains none.
        self.installer().install("builder-base")
        applied = self.installer().migrate(apply=True, yes=True)
        self.assertFalse(applied["preview"])
        self.assertFalse(legacy.exists())
        self.assertNotIn("@central/bundle.md", (self.claude / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertIn("Keep this.", (self.claude / "CLAUDE.md").read_text(encoding="utf-8"))
        agents = (self.codex / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("before", agents)
        self.assertIn("outside", agents)
        self.assertIn("after", agents)
        self.assertNotIn("agent-bios:central", agents)
        self.assertNotIn("tooling-gotchas-hook.py", (self.claude / "settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("agent-bios additions", (self.codex / "config.toml").read_text(encoding="utf-8"))
        events = (self.user / "learnings" / "claude" / "events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(raw_record + "\n", events)
        store = self.installer()._store(Path(applied["package_root"]) if "package_root" in applied else
                                        Path(self.installer().status()["package_root"]))
        snapshot = store.snapshot("claude")
        inventory = json.loads((Path(snapshot["path"]) / "inventory.json").read_text(encoding="utf-8"))
        learning = next(item for item in inventory["items"] if item["ref"].endswith(":11111111-1111-4111-8111-111111111111"))
        self.assertEqual("keep this learning", learning["body"])
        self.assertTrue(Path(applied["backup_root"]).is_dir())

    def test_migration_refuses_same_learning_id_with_different_private_bytes(self) -> None:
        self.claude.mkdir(parents=True)
        (self.claude / "personal").mkdir()
        source = {"schema_version": 1, "learning_id": "33333333-3333-4333-8333-333333333333",
                  "lesson": "source learning", "domain": "builder-base", "created": "2026-09-07T12:00:00+00:00",
                  "supporting_sessions": ["claude:abcde"]}
        private = {**source, "lesson": "different private bytes"}
        (self.claude / "personal" / "learnings.jsonl").write_text(json.dumps(source) + "\n", encoding="utf-8")
        target = self.user / "learnings" / "claude" / "events.jsonl"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(private) + "\n", encoding="utf-8")
        preview = self.installer().migrate()
        self.assertTrue(any("same learning_id has different source/private bytes" in item
                            for item in preview["needs_action"]))
        with self.assertRaises(InstallError):
            self.installer().migrate(apply=True, yes=True)


if __name__ == "__main__":
    unittest.main()
