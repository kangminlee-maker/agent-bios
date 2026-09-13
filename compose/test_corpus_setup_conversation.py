"""Exercise conversation setup through the packaged shell and registered helper."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

from corpus_install import CorpusInstaller
from corpus_setup import SetupController


SOURCE = Path(__file__).resolve().parents[1]


class ConversationSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="conversation-setup-")
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "home"
        self.project = self.root / "project with spaces"
        self.state, self.user = self.root / "state", self.root / "user"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        python = self.bin / "python3"
        python.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -B -S \"$@\"\n")
        python.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin) + ":/usr/bin:/bin",
                        AGENT_BIOS_STATE_DIR=str(self.state), AGENT_BIOS_CORPUS_DIR=str(self.user),
                        CODEX_HOME=str(self.home / ".codex"), CLAUDE_CONFIG_DIR=str(self.home / ".claude"),
                        AGENT_LAUNCH_VENV=str(self.root / "managed"), AGENT_LAUNCH_PYTHON=str(python),
                        ZDOTDIR=str(self.home), LC_ALL="C", PYTHONDONTWRITEBYTECODE="1")
        for name in ("PYTHONPATH", "PYTHONHOME", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID",
                     "AGENT_BIOS_PACKAGE_ROOT", "AGENT_BIOS_REPO", "AGENT_BIOS_PRIVATE_CORPUS",
                     "BASH_ENV", "ENV"):
            self.env.pop(name, None)
        self.marker = "CONVERSATION_SETUP_SOURCE_BODY"
        self.originals = {}
        for path in (self.home / ".codex/AGENTS.md", self.home / ".claude/CLAUDE.md",
                     self.project / "AGENTS.md", self.project / "CLAUDE.md"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# User instructions\n{self.marker} {path.name}\n", encoding="utf-8")
            self.originals[path] = path.read_bytes()

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, *args, payload=None, prefix=None, env=None, expected=0):
        argv = prefix or ["/bin/bash", str(SOURCE / "install.sh"), "setup"]
        raw = subprocess.run([*argv, *args], input=payload, capture_output=True, text=True,
                             env=env or self.env, cwd=self.project, timeout=60)
        self.assertEqual(expected, raw.returncode, raw.stderr + raw.stdout[-5000:])
        self.assertNotIn(self.marker, raw.stdout)
        value = json.loads(raw.stdout)
        return value, raw.stdout

    def no_setup_writes(self):
        self.assertFalse(self.state.exists())
        self.assertFalse(self.user.exists())
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse((self.root / "managed").exists())
        self.assertEqual(self.originals, {path: path.read_bytes() for path in self.originals})

    def owned_snapshot(self):
        snapshot = {}
        for root in (self.home, self.state, self.user):
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_symlink():
                    snapshot[str(path)] = ("symlink", str(path.readlink()))
                elif path.is_file():
                    snapshot[str(path)] = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mode)
        return snapshot

    def request(self, *, extras=False):
        return {"selection_mode": "none", "targets": [], "dependencies": [],
                "app_bridge": extras, "project_roots": [str(self.project)] if extras else [],
                "import_paths": [str(self.project / "AGENTS.md")] if extras else []}

    def review(self, request, language="ja"):
        review, raw = self.call("plan", "--language", language, "--input", "-", payload=json.dumps(request))
        self.assertEqual("agent-bios-setup-review", review["kind"])
        self.assertEqual(language, review["language"])
        self.assertRegex(review["review_id"], r"^[0-9a-f]{64}$")
        artifact = self.root / "accepted review.json"
        artifact.write_text(raw, encoding="utf-8")
        return review, artifact

    def test_cold_start_inspection_discovery_and_plan_need_no_skill_host_cli_or_tty(self):
        start, _ = self.call("start", "--json")
        self.assertEqual("agent-bios-setup-start", start["kind"])
        self.assertEqual(["en", "ko", "ja"], [row["id"] for row in start["languages"]])
        self.assertEqual(SOURCE / "compose/setup/START.md", Path(start["guide_path"]))
        self.assertEqual(["/bin/bash", str(SOURCE / "install.sh"), "setup"], start["setup_argv"])
        self.no_setup_writes()
        inspection, _ = self.call("inspect", "--language", "ja")
        self.assertEqual("agent-bios-setup-inspection", inspection["kind"])
        self.assertEqual("none", inspection["default_plan"]["selection_mode"])
        dependencies = {row["id"]: row for row in inspection["dependencies"]}
        self.assertEqual("missing", dependencies["codex"]["status"])
        self.assertEqual("missing", dependencies["claude"]["status"])
        discovery, _ = self.call("discover", "--project-root", str(self.project))
        self.assertIn(str(self.project / "AGENTS.md"), [row["path"] for row in discovery["sources"]])
        review, _ = self.review(self.request(extras=True))
        self.assertIn("コーパス", review["summary"])
        self.assertEqual([], review["preview"]["plan"]["dependency_actions"])
        self.no_setup_writes()

    def test_machine_preview_is_the_shared_controller_preview(self):
        request = self.request()
        request.update(selection_mode="selected", targets=["@agent-bios/core/builder-base"])
        review, _ = self.review(request, language="ko")
        controller = SetupController(CorpusInstaller(SOURCE, self.env))
        self.assertEqual(controller.preview(request), review["preview"])
        self.no_setup_writes()

    def test_review_apply_and_registered_helper_keep_roots_and_task_context_separate(self):
        review, artifact = self.review(self.request(extras=True))
        self.no_setup_writes()
        next_call_env = dict(self.env, SHLVL="7", TERM="dumb", CODEX_THREAD_ID="fixture-later-tool-call")
        applied, _ = self.call("apply", "--input", str(artifact), "--review-id", review["review_id"], "--yes",
                               env=next_call_env)
        self.assertEqual("complete", applied["state"])
        self.assertTrue(applied["result"]["applied"])
        self.assertFalse(applied["replayed"])
        handoff = applied["handoff"]
        self.assertTrue(handoff["runtime_verified"])
        self.assertTrue(handoff["helper_registered"])
        self.assertTrue(handoff["helper_verified"])
        self.assertEqual("unverified", handoff["native_discovery"])
        self.assertFalse(handoff["task_activation"]["performed"])
        self.assertEqual("unchanged", handoff["task_activation"]["existing_tasks"])
        self.assertFalse((self.state / "sessions/app-context").exists())
        self.assertEqual(self.originals, {path: path.read_bytes() for path in self.originals})
        captured = applied["result"]["extras"]["import"]
        self.assertEqual("requires model review", captured["classification"])
        self.assertTrue((self.user / "imports/captures" / (captured["capture_id"] + ".json")).is_file())
        snapshot = self.owned_snapshot()
        repeated, _ = self.call("apply", "--input", str(artifact), "--review-id", review["review_id"], "--yes")
        self.assertTrue(repeated["replayed"])
        self.assertEqual(applied["result"], repeated["result"])
        self.assertEqual(snapshot, self.owned_snapshot())
        decoy = dict(self.env, HOME=str(self.root / "decoy-home"),
                     AGENT_BIOS_STATE_DIR=str(self.root / "decoy-state"),
                     AGENT_BIOS_CORPUS_DIR=str(self.root / "decoy-user"), SHLVL="9")
        prefix = [*handoff["helper_argv"], "setup"]
        resumed_start, _ = self.call("start", prefix=prefix, env=decoy)
        self.assertEqual(Path(handoff["package_root"]) / "compose/setup/START.md", Path(resumed_start["guide_path"]))
        status, _ = self.call("status", "--review-id", review["review_id"], prefix=prefix, env=decoy)
        self.assertEqual("complete", status["state"])
        self.assertEqual(applied["result"], status["result"])
        resumed, _ = self.call("resume", "--review-id", review["review_id"], prefix=prefix, env=decoy)
        self.assertIsNone(resumed["review"])
        self.assertEqual(snapshot, self.owned_snapshot())
        self.assertFalse((self.root / "decoy-home").exists())
        self.assertFalse((self.root / "decoy-state").exists())
        self.assertFalse((self.root / "decoy-user").exists())

    def test_completed_receipt_does_not_claim_current_runtime_is_verified_after_drift(self):
        review, artifact = self.review(self.request())
        self.call("apply", "--input", str(artifact), "--review-id", review["review_id"], "--yes")
        record = json.loads((self.state / "runtime/private-install.json").read_text())
        launcher = Path(record["launcher"]["path"])
        launcher.relative_to(self.home)
        launcher.write_bytes(launcher.read_bytes() + b"\n# fixture user change\n")
        snapshot = self.owned_snapshot()
        status, _ = self.call("status", "--review-id", review["review_id"])
        self.assertEqual("complete", status["state"])
        self.assertFalse(status["handoff"]["runtime_verified"])
        self.assertTrue(status["handoff"]["needs_action"])
        self.assertEqual(snapshot, self.owned_snapshot())


if __name__ == "__main__":
    unittest.main()
