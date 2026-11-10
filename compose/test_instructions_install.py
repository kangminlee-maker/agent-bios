"""Real temp-home checks for private installation and legacy migration."""
from __future__ import annotations

import ast
import base64
import contextlib
import hashlib
import json
import instructions_install
import os
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
import unittest.mock

from instructions_install import InstructionsInstaller, InstallError
from instructions_transaction import TransactionPendingError, confirmed_release, guard_pending


SOURCE = Path(__file__).resolve().parent.parent


class _InstallerFixture(unittest.TestCase):
    """A real temp home with a synthetic package tree.

    The installer that runs is this checkout's; the package it installs is `self.repo`. That is the
    `--repo` route, where the installer code and the installed package are deliberately not one tree.
    """

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
                         "compose/domains.json", "learn/learning.schema.json", "launch/agent-launch.py", "launch/agent-launch.toml",
                         "wrappers/jsonl_lines.py"):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / relative, target)
        shutil.copytree(SOURCE / "launch" / "i18n", self.repo / "launch" / "i18n")
        shutil.copytree(SOURCE / "compose" / "bootstrap", self.repo / "compose" / "bootstrap")
        (self.repo / "package.json").write_text(json.dumps({"files": [
            "claude/", "compose/assemble.py", "compose/instructions_catalog.py", "compose/instructions_store.py", "compose/instructions_transaction.py", "compose/pkgid.py",
            "compose/domains.json", "compose/bootstrap/", "learn/learning.schema.json",
            "launch/agent-launch.py", "launch/agent-launch.toml", "launch/i18n", "wrappers/jsonl_lines.py",
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


class InstructionsInstallTests(_InstallerFixture):
    def test_launcher_reachability_answers_whether_the_deployed_launcher_can_be_typed(self) -> None:
        # install() writes the launcher into a directory the caller's PATH may not
        # carry. Nothing in the installed tree records that, so the completion
        # summary can only report it from here.
        bin_root = self.home / ".local" / "bin"
        absent = self.installer().launcher_reachability()
        self.assertEqual(str(bin_root / "agent-launch"), absent["path"])
        self.assertEqual(str(bin_root), absent["directory"])
        self.assertFalse(absent["on_path"])
        self.assertIs(False, absent["shell_connected"])
        for path in (f"/usr/bin:{bin_root}", f"{bin_root}/", f"{bin_root}//"):
            reachable = InstructionsInstaller(self.repo, {**self.env, "PATH": path}).launcher_reachability()
            self.assertTrue(reachable["on_path"], path)
        for path in ("", "/usr/bin", "~/.local/bin", str(bin_root) + "x"):
            # A literal ~ is not expanded when a shell searches PATH, so it does
            # not reach the launcher and must not be reported as if it did.
            missed = InstructionsInstaller(self.repo, {**self.env, "PATH": path}).launcher_reachability()
            self.assertFalse(missed["on_path"], path)

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


# The installer side of probe 10 (`distill-probes-20261020/installer`, 11 scenarios run by its
# `run_all.sh`).  The probe varied the installer by building four whole trees and installing through
# subprocesses; here a second installer version is a fixture that moves BOTH hashes at once, because
# moving one alone is a different scenario — the refused claim.
#
# This file list is typed independently of `instructions_install.INSTALLER_CODE` on purpose: a digest
# the installer agrees with itself about is not evidence.  If the two declarations ever diverge, the
# recomputed digest differs and the route cases below fail.
INDEPENDENT_INSTALLER_FILES = ("compose/instructions_install.py", "compose/instructions_transaction.py",
                               "compose/host_platform.py", "launch/shell_integration.py")


def independent_installer_digest(root: Path) -> str:
    files = [{"path": relative, "sha256": hashlib.sha256((Path(root) / relative).read_bytes()).hexdigest()}
             for relative in INDEPENDENT_INSTALLER_FILES]
    canonical = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class InstallationReceiptTests(_InstallerFixture):
    """Probe scenarios c1 routes, c1b controls, c2 binding A, c3 failure, pristine recovery,
    c3b upgrade-pending, and receipt identity."""

    def receipts(self) -> list[Path]:
        directory = self.state / "runtime" / "receipts"
        return sorted(directory.glob("*.json")) if directory.is_dir() else []

    def receipt(self, transaction_id: str | None = None) -> tuple[dict, Path]:
        """One receipt, read the way a consumer must: the file name is the hash of the bytes.

        A recovery leaves two transactions — the recovered one and the install that followed it — so a
        case about recovery names the transaction it means instead of assuming a single receipt.
        """
        paths = self.receipts()
        if transaction_id is not None:
            paths = [path for path in paths
                     if json.loads(path.read_text(encoding="utf-8"))["transaction_id"] == transaction_id]
        self.assertEqual(1, len(paths), f"expected exactly one receipt, found {[p.name for p in paths]}")
        raw = paths[0].read_bytes()
        self.assertEqual(paths[0].stem, hashlib.sha256(raw).hexdigest())
        return json.loads(raw), paths[0]

    def pending_transaction_id(self) -> str:
        """The id of the one interrupted transaction, read from its journal directory."""
        journals = sorted((self.state / "runtime" / "installer-transactions").glob("*/journal.json"))
        self.assertEqual(1, len(journals))
        return journals[0].parent.name

    def journals(self) -> list[dict]:
        root = self.state / "runtime" / "installer-transactions"
        return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.glob("*/journal.json"))]

    @contextlib.contextmanager
    def other_installer(self, mark: str = "other"):
        """A second installer VERSION: the at-import hash and the at-receipt hash move together.

        That is what a different installer tree looks like from inside the process. Moving only one of
        the two is the mid-run replacement, which must refuse the receipt and is tested separately.
        """
        real = instructions_install._installer_code()
        files = [{"path": entry["path"], "sha256": hashlib.sha256((entry["sha256"] + mark).encode()).hexdigest()}
                 for entry in real["files"]]
        other = {"root": real["root"], "files": files,
                 "digest": hashlib.sha256(instructions_install._canonical(files)).hexdigest()}
        self.assertNotEqual(real["digest"], other["digest"])
        with unittest.mock.patch.object(instructions_install, "_CODE_AT_START", other), \
                unittest.mock.patch.object(instructions_install, "_installer_code", lambda: other):
            yield other

    def interrupt_first_projection(self, installer: InstructionsInstaller) -> None:
        original = installer._write_planned
        calls = 0

        def fail_once(path, version, mode):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("injected projection interruption")
            return original(path, version, mode)

        installer._write_planned = fail_once  # type: ignore[method-assign]

    # ---- c1: the receipt names the installer code that executed -------------------------------

    def test_receipt_names_the_executing_installer_not_the_installed_package(self) -> None:
        self.installer().install("builder-base")
        receipt, path = self.receipt()
        self.assertEqual("InstallationReceipt/v1", receipt["schema"])
        self.assertEqual("success", receipt["result"])
        self.assertEqual(independent_installer_digest(SOURCE), receipt["installer"]["digest"])
        self.assertEqual(receipt["installer"]["digest"], receipt["installer"]["digest_at_import"])
        self.assertEqual(str(SOURCE), receipt["installer"]["root"])
        self.assertNotEqual(str(self.repo), receipt["installer"]["root"])
        record = json.loads((self.state / "runtime" / "private-install.json").read_text(encoding="utf-8"))
        self.assertEqual(record["transaction_id"], receipt["transaction_id"])
        self.assertEqual(record["release_digest"], receipt["release_digest"])
        self.assertEqual(record["baseline_ref"], receipt["baseline_ref"])
        self.assertEqual(record["selection"], receipt["selection"])
        self.assertIsNone(receipt["begun_by_installer_digest"])
        # The journal is the pointer from the transaction to the receipt.
        committed = [data for data in self.journals() if data["state"] == "COMMITTED"]
        self.assertEqual([path.stem], [data["receipt_id"] for data in committed])

    def test_receipt_artifacts_are_one_flat_list_whose_rows_carry_their_role(self) -> None:
        self.installer().install("builder-base")
        receipt, _ = self.receipt()
        record = json.loads((self.state / "runtime" / "private-install.json").read_text(encoding="utf-8"))
        self.assertEqual({"release", "owned"}, {row["role"] for row in receipt["artifacts"]})
        self.assertEqual({"path", "sha256", "role"}, {key for row in receipt["artifacts"] for key in row})
        release = {row["path"]: row["sha256"] for row in receipt["artifacts"] if row["role"] == "release"}
        self.assertEqual({entry["path"]: entry["sha256"] for entry in record["installed_files"]}, release)
        owned = {row["path"] for row in receipt["artifacts"] if row["role"] == "owned"}
        self.assertIn(record["launcher"]["path"], owned)
        self.assertLessEqual({entry["path"] for entry in record["config_files"]}, owned)
        # The package's own store and catalog ran inside this installer process, so they are named here
        # rather than inferred from the installer digest.
        modules = {entry["path"] for entry in receipt["installer"]["package_modules_run"]}
        self.assertIn("compose/instructions_store.py", modules)

    def test_an_installer_reached_through_a_symlink_hashes_the_tree_the_link_resolves_to(self) -> None:
        # The npm route is a `.bin/agent-bios` symlink; `_installer_code` resolves `__file__` before
        # hashing, so the digest must be the real tree's and never the link's directory.
        link = Path(self.tmp.name) / "linked-checkout"
        link.symlink_to(SOURCE)
        probe = ("import json, sys; sys.path.insert(0, %r); import instructions_install as m; "
                 "print(json.dumps(m._CODE_AT_START))" % str(link / "compose"))
        proc = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                              env={**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"},
                              cwd=str(self.tmp.name), stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stderr)
        code = json.loads(proc.stdout)
        self.assertEqual(str(SOURCE), code["root"])
        self.assertEqual(independent_installer_digest(SOURCE), code["digest"])

    def cli(self, release: str, *args: str) -> dict:
        """The consumer surface a reader actually has: `instructions snapshot`, as the CLI runs it."""
        clean = {key: value for key, value in os.environ.items()
                 if not key.startswith("AGENT_BIOS_") and key not in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "ZDOTDIR")}
        proc = subprocess.run([sys.executable, str(SOURCE / "compose" / "instructions.py"), "--repo", release,
                               "--json", *args], capture_output=True, text=True, timeout=300,
                              env={**clean, **self.env, "PYTHONDONTWRITEBYTECODE": "1"},
                              cwd=str(self.home), stdin=subprocess.DEVNULL)
        self.assertEqual(0, proc.returncode, proc.stderr)
        return json.loads(proc.stdout)

    def test_the_cli_snapshot_surface_returns_the_installation_binding(self) -> None:
        result = self.installer().install("builder-base")
        receipt, path = self.receipt()
        release = result["record"]["package_root"]
        created = self.cli(release, "snapshot", "--host", "codex", "--cwd", str(self.home))
        binding = self.cli(release, "snapshot", "--content-ref", created["content_ref"])["installation_binding"]
        self.assertTrue(binding["bound"], binding)
        self.assertEqual(path.stem, binding["receipt_id"])
        self.assertEqual(receipt["installer"]["digest"], binding["installer_digest"])
        self.assertEqual(receipt["transaction_id"], binding["transaction_id"])

    # ---- c1b: the controls on that claim -------------------------------------------------------

    def test_one_changed_line_in_a_declared_file_moves_the_digest(self) -> None:
        # `launch/shell_integration.py` executes but never enters `sys.modules`, so a discovered file
        # set would miss it. Changing it must move the digest, or the declaration buys nothing.
        tree = Path(self.tmp.name) / "installer-copy"
        for relative in INDEPENDENT_INSTALLER_FILES:
            target = tree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / relative, target)
        before = independent_installer_digest(tree)
        self.assertEqual(independent_installer_digest(SOURCE), before)
        integration = tree / "launch" / "shell_integration.py"
        integration.write_bytes(integration.read_bytes() + b"# one added line\n")
        self.assertNotEqual(before, independent_installer_digest(tree))
        # And the installer itself, run from that copy, reports the moved digest.
        probe = ("import sys; sys.path.insert(0, %r); import instructions_install as m; "
                 "print(m._CODE_AT_START['digest'])" % str(tree / "compose"))
        proc = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                              env={**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"},
                              cwd=str(self.tmp.name), stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual(independent_installer_digest(tree), proc.stdout.strip())

    def test_installer_code_replaced_mid_run_refuses_the_receipt_and_not_the_install(self) -> None:
        real = instructions_install._installer_code()
        moved = {**real, "digest": "0" * 64}
        with unittest.mock.patch.object(instructions_install, "_installer_code", lambda: moved):
            result = self.installer().install("builder-base")
        self.assertTrue(result["stored"])
        self.assertEqual([], self.receipts())
        committed = [data for data in self.journals() if data["state"] == "COMMITTED"]
        self.assertEqual(1, len(committed))
        self.assertNotIn("receipt_id", committed[0])
        self.assertTrue(self.installer().verify()["stored"])

    def test_a_declared_file_missing_from_the_layout_refuses_the_receipt(self) -> None:
        real = instructions_install._installer_code()
        unreadable = {**real, "files": [{**real["files"][0], "sha256": None}, *real["files"][1:]]}
        with unittest.mock.patch.object(instructions_install, "_CODE_AT_START", unreadable), \
                unittest.mock.patch.object(instructions_install, "_installer_code", lambda: unreadable):
            result = self.installer().install("builder-base")
        self.assertTrue(result["stored"])
        self.assertEqual([], self.receipts())

    # ---- c2 A: an old installer installing a package that carries a new installer ---------------

    def test_an_old_installer_installing_a_newer_installer_names_its_own_digest(self) -> None:
        for relative in INDEPENDENT_INSTALLER_FILES:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / relative, target)
            target.write_bytes(target.read_bytes() + b"# the package's newer installer\n")
        manifest = json.loads((self.repo / "package.json").read_text(encoding="utf-8"))
        manifest["files"] = sorted({*manifest["files"], *INDEPENDENT_INSTALLER_FILES})
        (self.repo / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.installer().install("builder-base")
        receipt, _ = self.receipt()
        self.assertEqual(independent_installer_digest(SOURCE), receipt["installer"]["digest"])
        self.assertNotEqual(independent_installer_digest(self.repo), receipt["installer"]["digest"])
        # The installed release really does carry the newer installer; only the claim is the old one's.
        release = {row["path"] for row in receipt["artifacts"] if row["role"] == "release"}
        self.assertIn("compose/instructions_install.py", release)

    # ---- F18 ordering and recovery identity (done-when 2) --------------------------------------

    def test_the_receipt_exists_before_the_journal_reaches_committed(self) -> None:
        installer = self.installer()
        original = installer._journal_write

        def fail_at_commit(journal, value):
            if value.get("state") == "COMMITTED":
                raise OSError("injected fault between the receipt and the commit marker")
            return original(journal, value)

        installer._journal_write = fail_at_commit  # type: ignore[method-assign]
        with self.assertRaises(OSError):
            installer.install("builder-base")
        receipt, _ = self.receipt()               # the receipt is already on disk
        self.assertEqual("success", receipt["result"])
        self.assertEqual(["NEEDS_RECOVERY"], [data["state"] for data in self.journals()])

    def test_a_recovery_by_another_installer_names_both_digests(self) -> None:
        with self.other_installer("begun-by-x") as begun:
            installer = self.installer()
            self.interrupt_first_projection(installer)
            with self.assertRaises(OSError):
                installer.install("builder-base")
        self.assertEqual([], self.receipts())
        self.assertEqual([begun["digest"]], [data["installer_digest"] for data in self.journals()])
        recovered = self.pending_transaction_id()
        finished = self.installer().install("builder-base")       # recovered by this checkout
        self.assertTrue(finished["stored"])
        receipt, _ = self.receipt(recovered)
        self.assertEqual(independent_installer_digest(SOURCE), receipt["installer"]["digest"])
        self.assertEqual(begun["digest"], receipt["begun_by_installer_digest"])
        self.assertNotEqual(receipt["installer"]["digest"], receipt["begun_by_installer_digest"])
        # The install that followed the recovery was begun and finished by one installer.
        following, _ = self.receipt(finished["record"]["transaction_id"])
        self.assertIsNone(following["begun_by_installer_digest"])

    def test_a_transaction_begun_and_finished_by_one_installer_carries_no_second_digest(self) -> None:
        installer = self.installer()
        self.interrupt_first_projection(installer)
        with self.assertRaises(OSError):
            installer.install("builder-base")
        recovered = self.pending_transaction_id()
        self.installer().install("builder-base")
        receipt, _ = self.receipt(recovered)
        self.assertEqual(independent_installer_digest(SOURCE), receipt["installer"]["digest"])
        self.assertIsNone(receipt["begun_by_installer_digest"])

    # ---- c3: a failed transaction writes no success receipt -------------------------------------

    def test_a_real_permission_failure_leaves_no_receipt_and_no_record(self) -> None:
        bin_root = self.home / ".local" / "bin"
        bin_root.mkdir(parents=True)
        bin_root.chmod(0o500)
        self.addCleanup(lambda: bin_root.exists() and bin_root.chmod(0o700))
        with self.assertRaises((OSError, InstallError)):
            self.installer().install("builder-base")
        self.assertEqual([], self.receipts())
        self.assertFalse((self.state / "runtime" / "private-install.json").exists())
        self.assertEqual(["NEEDS_RECOVERY"], [data["state"] for data in self.journals()])

    def test_a_verify_failure_after_publication_leaves_no_receipt(self) -> None:
        installer = self.installer()
        installer._verify_transaction_install = lambda data: (_ for _ in ()).throw(  # type: ignore[method-assign]
            InstallError("injected post-publication verification failure"))
        with self.assertRaises(InstallError):
            installer.install("builder-base")
        self.assertEqual([], self.receipts())
        self.assertEqual(["NEEDS_RECOVERY"], [data["state"] for data in self.journals()])

    def test_a_transient_failure_recovers_into_a_receipt(self) -> None:
        installer = self.installer()
        self.interrupt_first_projection(installer)
        with self.assertRaises(OSError):
            installer.install("builder-base")
        self.assertEqual([], self.receipts())
        recovered = self.pending_transaction_id()
        self.installer().install("builder-base")
        receipt, path = self.receipt(recovered)
        self.assertEqual("success", receipt["result"])
        committed = [data for data in self.journals() if data["state"] == "COMMITTED"]
        self.assertIn(path.stem, [data["receipt_id"] for data in committed])

    def test_a_user_edit_of_an_owned_projection_refuses_the_retry_and_writes_no_receipt(self) -> None:
        installer = self.installer()
        self.interrupt_first_projection(installer)
        with self.assertRaises(OSError):
            installer.install("builder-base")
        launcher = self.home / ".local" / "bin" / "agent-launch"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text("# edited by the user between the attempts\n", encoding="utf-8")
        with self.assertRaises(InstallError):
            self.installer().install("builder-base")
        self.assertEqual([], self.receipts())

    # ---- c3b: a transaction begun before receipts existed (done-when 3) ------------------------

    def test_a_transaction_begun_before_receipts_existed_finishes_unbound(self) -> None:
        installer = self.installer()
        self.interrupt_first_projection(installer)
        with self.assertRaises(OSError):
            installer.install("builder-base")
        journal = next((self.state / "runtime" / "installer-transactions").glob("*/journal.json"))
        data = json.loads(journal.read_text(encoding="utf-8"))
        record_path = str(self.state / "runtime" / "private-install.json")
        entry = next(item for item in data["paths"] if item["path"] == record_path)
        record = json.loads(base64.b64decode(entry["after"]["bytes_b64"].encode("ascii"), validate=True))
        del record["transaction_id"]              # as a pre-receipt installer planned it
        entry["after"] = InstructionsInstaller._planned_version(
            instructions_install._canonical(record) + b"\n")
        del data["installer_digest"]
        journal.write_text(json.dumps(data), encoding="utf-8")
        recovered = journal.parent.name
        self.assertTrue(self.installer().install("builder-base")["stored"])
        # It can finish; it cannot be bound. Only the install that followed it has a receipt.
        bound = {json.loads(path.read_text(encoding="utf-8"))["transaction_id"] for path in self.receipts()}
        self.assertNotIn(recovered, bound)
        finished = next(item for item in self.journals()
                        if item["candidate"]["transaction_id"] == recovered)
        self.assertEqual("COMMITTED", finished["state"])
        self.assertNotIn("receipt_id", finished)

    # ---- receipt identity (done-when 6) --------------------------------------------------------

    def test_the_receipt_id_is_the_hash_of_the_body_and_lives_outside_it(self) -> None:
        self.installer().install("builder-base")
        receipt, path = self.receipt()
        self.assertNotIn("receipt_id", receipt)
        self.assertNotIn("receipt_id", receipt["installer"])
        canonical = instructions_install._canonical(receipt)
        self.assertEqual(canonical, path.read_bytes())
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), path.stem)
        # Re-serialized from a reordered mapping, the canonical form hashes the same.
        reordered = dict(reversed(list(receipt.items())))
        self.assertNotEqual(list(reordered), list(receipt))
        self.assertEqual(path.stem, hashlib.sha256(instructions_install._canonical(reordered)).hexdigest())
        self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_a_body_carrying_its_own_id_is_refused_at_write(self) -> None:
        installer = self.installer()
        original = installer._receipt_body

        def with_its_own_id(data, record, now):
            body = original(data, record, now)
            body["receipt_id"] = "0" * 64
            return body

        installer._receipt_body = with_its_own_id  # type: ignore[method-assign]
        with self.assertRaises(InstallError) as caught:
            installer.install("builder-base")
        self.assertIn("must not carry its own id", str(caught.exception))
        self.assertEqual([], self.receipts())


# Every scenario of the probe's `run_all.sh`, and where it landed here.  A scenario whose port is
# partial says so in its own comment; the two `sc_*_mutation` scenarios are not tests at all but
# pretrials — the probe planted the defect in the code and required the named case to fail, which is
# this repo's rule for a new control and is run before the commit, not by the suite.
PORTED_SCENARIOS: dict[str, tuple[str, ...]] = {
    "sc_c1_routes": (
        "test_instructions_install.py:InstallationReceiptTests.test_receipt_names_the_executing_installer_not_the_installed_package",
        "test_instructions_install.py:InstallationReceiptTests.test_receipt_artifacts_are_one_flat_list_whose_rows_carry_their_role",
        "test_instructions_install.py:InstallationReceiptTests.test_an_installer_reached_through_a_symlink_hashes_the_tree_the_link_resolves_to",
    ),
    "sc_c1b_controls": (
        "test_instructions_install.py:InstallationReceiptTests.test_one_changed_line_in_a_declared_file_moves_the_digest",
        "test_instructions_install.py:InstallationReceiptTests.test_installer_code_replaced_mid_run_refuses_the_receipt_and_not_the_install",
        "test_instructions_install.py:InstallationReceiptTests.test_a_declared_file_missing_from_the_layout_refuses_the_receipt",
    ),
    "sc_c2_binding": (
        "test_instructions_install.py:InstallationReceiptTests.test_an_old_installer_installing_a_newer_installer_names_its_own_digest",
        "test_instructions_store.py:InstallationBindingTest.test_two_installs_of_one_release_bind_their_sessions_to_their_own_receipts",
        "test_instructions_store.py:InstallationBindingTest.test_an_earlier_snapshot_keeps_binding_to_the_receipt_it_was_built_from",
    ),
    "sc_c3_failure": (
        "test_instructions_install.py:InstallationReceiptTests.test_a_real_permission_failure_leaves_no_receipt_and_no_record",
        "test_instructions_install.py:InstallationReceiptTests.test_a_verify_failure_after_publication_leaves_no_receipt",
        "test_instructions_install.py:InstallationReceiptTests.test_a_transient_failure_recovers_into_a_receipt",
    ),
    "probe_pristine_recovery": (
        "test_instructions_install.py:InstallationReceiptTests.test_a_user_edit_of_an_owned_projection_refuses_the_retry_and_writes_no_receipt",
    ),
    "sc_c3b_upgrade_pending": (
        "test_instructions_install.py:InstallationReceiptTests.test_a_transaction_begun_before_receipts_existed_finishes_unbound",
        "test_instructions_store.py:InstallationBindingTest.test_an_installation_without_a_receipt_leaves_the_snapshot_unbound",
    ),
    "sc_c3m_mutation": (
        "test_instructions_install.py:InstallationReceiptTests.test_a_verify_failure_after_publication_leaves_no_receipt",
    ),
    "sc_c4_unbound": (
        "test_instructions_store.py:InstallationBindingTest.test_a_snapshot_whose_artifacts_differ_from_the_receipt_is_unbound_by_field",
        "test_instructions_store.py:InstallationBindingTest.test_a_snapshot_from_another_baseline_is_unbound_by_name",
        "test_instructions_store.py:InstallationBindingTest.test_a_tampered_or_missing_receipt_is_unbound_with_its_reason",
        "test_instructions_store.py:InstallationBindingTest.test_a_receipt_the_store_cannot_verify_leaves_the_snapshot_unbound",
    ),
    "sc_c4m_mutation": (
        "test_instructions_store.py:InstallationBindingTest.test_a_snapshot_whose_artifacts_differ_from_the_receipt_is_unbound_by_field",
    ),
    "sc_c6_git_update": (
        "test_instructions_install.py:InstallationReceiptTests.test_one_changed_line_in_a_declared_file_moves_the_digest",
    ),
    "sc_c7_cli_snapshot": (
        "test_instructions_install.py:InstallationReceiptTests.test_the_cli_snapshot_surface_returns_the_installation_binding",
    ),
}

# A scenario whose port substitutes something for what the probe did says so here, and the coverage
# case prints it beside the scenario: a reader of the count must see what was NOT ported rather than
# read 11 as 11 identical ports.
PORT_NOTES: dict[str, str] = {
    "sc_c6_git_update": ("git remote fixture replaced by a copied tree run as a subprocess; the property held is "
                         "that the digest follows the tree that EXECUTES, not the script that started the update. "
                         "The `install.sh update` pull path itself is not exercised"),
    "sc_c3m_mutation": ("not a test but a pretrial: the receipt write is moved before "
                        "`_verify_transaction_install` and the named case must fail by name"),
    "sc_c4m_mutation": ("not a test but a pretrial: the artifact comparison is dropped from "
                        "`installation_binding` and the named case must fail by name"),
}


class ProbeScenarioCoverageTest(unittest.TestCase):
    """The ported suite must keep naming every probe scenario, and no named case may go assertion-free.

    A case that loses its assertions still passes, and a map pointing at a renamed method is a claim
    about coverage that nothing holds. Both are decidable from the test sources, so both are checked
    here instead of being remembered.
    """

    def assertion_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        trees = {name: ast.parse((SOURCE / "compose" / name).read_text(encoding="utf-8"))
                 for name in {entry.split(":")[0] for entries in PORTED_SCENARIOS.values() for entry in entries}}
        for entries in PORTED_SCENARIOS.values():
            for entry in entries:
                file_name, qualified = entry.split(":")
                class_name, method_name = qualified.split(".")
                classes = [node for node in trees[file_name].body
                           if isinstance(node, ast.ClassDef) and node.name == class_name]
                self.assertEqual(1, len(classes), f"{entry}: no such test class")
                methods = [node for node in classes[0].body
                           if isinstance(node, ast.FunctionDef) and node.name == method_name]
                self.assertEqual(1, len(methods), f"{entry}: no such test method")
                counts[entry] = sum(1 for node in ast.walk(methods[0])
                                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                                    and node.func.attr.startswith("assert"))
        return counts

    def test_every_probe_scenario_is_ported_and_carries_assertions(self) -> None:
        self.assertEqual(11, len(PORTED_SCENARIOS))      # the eleven scenarios of the probe's run_all.sh
        counts = self.assertion_counts()
        self.assertTrue(counts)
        empty = sorted(entry for entry, count in counts.items() if count == 0)
        self.assertEqual([], empty, f"ported cases with no assertion: {empty}")
        self.assertEqual([], sorted(set(PORT_NOTES) - set(PORTED_SCENARIOS)), "a note names no ported scenario")
        for scenario, entries in sorted(PORTED_SCENARIOS.items()):
            note = PORT_NOTES.get(scenario)
            print(f"  {scenario}: {sum(counts[entry] for entry in entries)} assertions in {len(entries)} case(s)"
                  + (f"\n      ported with a substitution: {note}" if note else ""))
        print(f"  ported total: {sum(counts.values())} assertions in {len(counts)} distinct cases")


if __name__ == "__main__":
    unittest.main()
