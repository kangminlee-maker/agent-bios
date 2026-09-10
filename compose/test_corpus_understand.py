#!/usr/bin/env python3
"""Isolated bundle, provenance, and failure-path controls for understand!."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from compose.corpus_store import CorpusStore
from compose.corpus_understand import CorpusUnderstand, UnderstandError, ProvenancePending
from compose.test_corpus_store import _Catalog


class _BundleCatalog(_Catalog):
    @staticmethod
    def load_catalog(_repo):
        base = _Catalog.load_catalog(_repo)
        base["packages"][0]["package_id"] = "@agent-bios/core"
        base["packages"][0]["domains"] = {"builder-base": "Building"}
        base["items"] = []
        for number in (2, 3, 4, 8, 9, 14, 15, 49, 56):
            item = copy.deepcopy(_Catalog.load_catalog(_repo)["items"][0])
            item.update(package_id="@agent-bios/core", item_id=f"rule-{number:03}",
                        ref=f"@agent-bios/core:rule-{number:03}", title=f"Rule {number}", domains=[])
            base["items"].append(item)
        domain = copy.deepcopy(base["items"][0])
        domain.update(ref="@agent-bios/core:guide-build", item_id="guide-build", kind="guide",
                      tier="domain", domains=["builder-base"])
        base["items"].append(domain)
        return base


class UnderstandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        (self.repo / "compose" / "bootstrap").mkdir(parents=True)
        (self.repo / "compose" / "bootstrap" / "SKILL.md").write_text("# corpus\n")
        (self.repo / "compose" / "corpus_catalog.py").write_text("# fixture compiler\n")
        self.store = CorpusStore(self.repo, self.root / "state", self.root / "user")
        self.store._catalog_module = lambda: _BundleCatalog
        self.store.install()
        self.native_id = "12345678-1234-4321-8123-123456789012"
        self.env = {"HOME": str(self.root / "home"), "CODEX_THREAD_ID": self.native_id}
        self.transcript = self.root / "home" / ".codex" / "sessions" / f"rollout-{self.native_id}.jsonl"
        self.transcript.parent.mkdir(parents=True)
        self.transcript.write_text("")
        self._append({"type": "session_meta", "payload": {"id": self.native_id, "source": "cli"}})
        self._user("understand core please")
        self.manager = CorpusUnderstand(self.store, self.env)

    def tearDown(self):
        self.temp.cleanup()

    def _append(self, value, path=None):
        with (path or self.transcript).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value) + "\n")

    def _user(self, text):
        self._append({"type": "event_msg", "payload": {"type": "user_message", "message": text}})

    def _assistant(self, text):
        self._append({"type": "response_item", "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": text}]}})

    def _start(self):
        session = self.manager.start("core-purpose", "codex")
        self.manager.bind(session["session_id"], "codex")
        return session["session_id"]

    def _proposal(self, session):
        turns = self.manager.turns(session)["turns"]
        user = [x for x in turns if x["role"] == "user"][-1]
        return {"user_turn": user["id"], "kind": "flaw", "title": "Goal-relevant clarification",
                "finding": "Asking about every ambiguity can distract from the intended goal.",
                "impact": "Low-value questions consume attention and change the learning direction.",
                "alternative": "Clarify only uncertainty that changes an important goal or decision.",
                "origin_review": "The tutor described the existing rationale without proposing this criticism; the user introduced it.",
                "source_refs": ["@agent-bios/core:rule-004"],
                "reviewed_assistant_turns": [x["id"] for x in turns if x["role"] == "assistant" and x["line"] < user["line"]]}

    def _candidate(self, session):
        self._assistant("This bundle explains scope and why clarification supports it. What relationship do you see?")
        self._user("Ambiguity alone is not a reason to ask: irrelevant questions derail the user's purpose.")
        return self.manager.propose(session, self._proposal(session))

    def _confirmed(self):
        session = self._start()
        candidate = self._candidate(session)
        self._user(candidate["confirmation"])
        return session, candidate["candidate_id"]

    def _edit(self, ref, patch):
        plan = self.store.plan({"operation": "update", "ref": ref, "patch": patch,
                               "item_digest": self.store.show(ref)["digest"]})
        self.store.apply(plan["plan_id"])

    def test_core_purpose_groups_and_domain_are_bundles(self):
        rows = self.manager.list_bundles()
        self.assertEqual(5, len(rows))
        self.assertEqual(3, next(x for x in rows if x["id"] == "core-purpose")["item_count"])
        self.assertIn("@agent-bios/core/builder-base", [x["id"] for x in rows])
        self.assertFalse(self.manager.root.exists())

    def test_effective_overrides_and_removed_items(self):
        self._edit("@agent-bios/core:rule-004", {"body": "personal clarification override"})
        plan = self.store.plan({"operation": "remove", "ref": "@agent-bios/core:rule-003"})
        self.store.apply(plan["plan_id"])
        bundle = self.manager.show("core-purpose")
        self.assertEqual(2, bundle["item_count"])
        self.assertIn("personal clarification override", [x["body"] for x in bundle["items"]])

    def test_pinned_source_survives_source_change_and_prompt_is_data(self):
        session = self.manager.start("core-purpose")
        self._edit("@agent-bios/core:rule-004", {"body": "later value"})
        frozen = self.manager.session(session["session_id"])
        self.assertEqual(session["bundle"], frozen["bundle"])
        self.assertNotEqual(frozen["bundle"]["source_ref"], self.manager.show("core-purpose")["source_ref"])
        prompt = Path(session["prompt_path"])
        self.assertEqual(0o600, prompt.stat().st_mode & 0o777)
        for text in ("learning DATA", "ONE goal-relevant question", "Respect requests to pause", "Do not ask about every ambiguity"):
            self.assertIn(text, prompt.read_text())

    def test_stale_start_ref_refuses_before_generation_write(self):
        ref = self.manager.show("core-purpose")["source_ref"]
        self._edit("@agent-bios/core:rule-004", {"body": "later value"})
        with self.assertRaisesRegex(UnderstandError, "bundle changed"):
            self.manager.start("core-purpose", expected_source_ref=ref)
        self.assertFalse(self.manager.state_path.exists())

    def test_pinned_source_tampering_rejected(self):
        session = self.manager.start("core-purpose")
        path = self.manager._path("sessions", session["session_id"])
        value = json.loads(path.read_text())
        value["bundle"]["items"][0]["body"] = "changed"
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(UnderstandError, "pinned understand content changed"):
            self.manager.session(session["session_id"])

    def test_positive_award_personal_requested_only_and_idempotent(self):
        session, candidate = self._confirmed()
        result = self.manager.award(session, candidate)
        note = self.store.show(result["note_ref"])["item"]
        self.assertEqual("requested", note["surface"])
        self.assertEqual("@local/personal", note["package_id"])
        self.assertIn("Native provenance: codex:", note["body"])
        self.assertTrue(self.manager.award(session, candidate)["duplicate"])
        self.assertEqual(1, self.store.status()["personal_items"])
        self.assertEqual(1, self.manager.status()["count"])

    def test_note_deletion_does_not_revoke_award(self):
        session, candidate = self._confirmed()
        result = self.manager.award(session, candidate)
        plan = self.store.plan({"operation": "remove", "ref": result["note_ref"]})
        self.store.apply(plan["plan_id"])
        self.assertTrue(self.manager.status()["unlocked"])
        self.assertTrue(self.manager.award(session, candidate)["duplicate"])

    def test_reset_generation_cannot_resurrect_old_award(self):
        session, candidate = self._confirmed()
        self.manager.award(session, candidate)
        self.manager.state_path.unlink()  # installer's full-reset target
        self.assertFalse(self.manager.status()["unlocked"])
        self.manager.start("core-purpose")
        with self.assertRaisesRegex(UnderstandError, "expired by reset"):
            self.manager.award(session, candidate)
        self.assertFalse(self.manager.status()["unlocked"])

    def test_interruption_after_note_before_unlock_recovers_without_duplicate(self):
        session, candidate = self._confirmed()
        from compose import corpus_understand
        original = corpus_understand._write
        def fail_unlock(path, value):
            if path == self.manager.state_path and value.get("awards"):
                raise OSError("simulated interruption before unlock")
            return original(path, value)
        with mock.patch.object(corpus_understand, "_write", side_effect=fail_unlock):
            with self.assertRaisesRegex(OSError, "simulated interruption"):
                self.manager.award(session, candidate)
        self.assertEqual(1, self.store.status()["personal_items"])
        self.assertFalse(self.manager.status()["unlocked"])
        self.manager.award(session, candidate)
        self.assertEqual(1, self.store.status()["personal_items"])
        self.assertTrue(self.manager.status()["unlocked"])

    def test_failed_note_save_never_unlocks(self):
        session, candidate = self._confirmed()
        with mock.patch.object(self.store, "apply", side_effect=OSError("note unavailable")):
            with self.assertRaises(OSError):
                self.manager.award(session, candidate)
        self.assertFalse(self.manager.status()["unlocked"])
        self.assertEqual(0, self.store.status()["personal_items"])

    def test_interrupted_plan_replans_after_unrelated_source_edit(self):
        session, candidate = self._confirmed()
        with mock.patch.object(self.store, "apply", side_effect=OSError("before source publication")):
            with self.assertRaises(OSError):
                self.manager.award(session, candidate)
        self._edit("@agent-bios/core:rule-004", {"body": "newer source not substituted for study"})
        result = self.manager.award(session, candidate)
        self.assertTrue(result["unlocked"])
        self.assertEqual(1, self.store.status()["personal_items"])
        self.assertNotEqual(result["source_ref"], self.manager.show("core-purpose")["source_ref"])

    def test_note_edited_before_interrupted_unlock_is_not_overwritten(self):
        session, candidate = self._confirmed()
        from compose import corpus_understand
        original = corpus_understand._write
        def fail_unlock(path, value):
            if path == self.manager.state_path and value.get("awards"):
                raise OSError("before unlock")
            return original(path, value)
        with mock.patch.object(corpus_understand, "_write", side_effect=fail_unlock):
            with self.assertRaises(OSError):
                self.manager.award(session, candidate)
        note = next(x for x in self.store.list_items() if x["package_id"] == "@local/personal")
        self._edit(note["ref"], {"body": "user replacement"})
        with self.assertRaisesRegex(UnderstandError, "changed before unlock"):
            self.manager.award(session, candidate)
        self.assertEqual("user replacement", self.store.show(note["ref"])["item"]["body"])
        self.assertFalse(self.manager.status()["unlocked"])

    def test_ordinary_create_never_unlocks(self):
        plan = self.store.plan({"operation": "create", "item": {"title": "Trophy", "body": "I found a flaw"}})
        self.store.apply(plan["plan_id"])
        self.assertFalse(self.manager.status()["unlocked"])

    def test_missing_native_context_is_pending_not_award(self):
        session = self.manager.start("core-purpose")
        manager = CorpusUnderstand(self.store, {"HOME": self.env["HOME"]})
        with self.assertRaises(ProvenancePending):
            manager.bind(session["session_id"], "codex")
        self.assertFalse(manager.status()["unlocked"])

    def test_role_payload_cannot_forge_provenance(self):
        session = self._start()
        self._user("A new criticism")
        proposal = self._proposal(session)
        proposal["role"] = "user"
        with self.assertRaisesRegex(UnderstandError, "requires exactly"):
            self.manager.propose(session, proposal)

    def test_assistant_turn_and_pre_binding_user_are_rejected(self):
        session = self._start()
        self._assistant("Maybe questions unrelated to the purpose should be skipped.")
        proposal = self._proposal(session)
        with self.assertRaisesRegex(UnderstandError, "genuine user turn after"):
            self.manager.propose(session, proposal)
        proposal["user_turn"] = self.manager.turns(session)["turns"][-1]["id"]
        with self.assertRaisesRegex(UnderstandError, "genuine user turn after"):
            self.manager.propose(session, proposal)

    def test_tutor_echo_and_incomplete_review_rejected(self):
        session = self._start()
        text = "Asking about every ambiguity can distract from the intended goal."
        self._assistant(text)
        self._user(text)
        proposal = self._proposal(session)
        with self.assertRaisesRegex(UnderstandError, "tutor-originated"):
            self.manager.propose(session, proposal)
        proposal["reviewed_assistant_turns"] = []
        with self.assertRaisesRegex(UnderstandError, "every prior native assistant"):
            self.manager.propose(session, proposal)

    def test_generic_yes_assistant_confirmation_and_rewritten_prefix_do_not_award(self):
        session = self._start()
        candidate = self._candidate(session)
        self._user("yes")
        self._assistant(candidate["confirmation"])
        with self.assertRaisesRegex(ProvenancePending, "pending user confirmation"):
            self.manager.award(session, candidate["candidate_id"])
        self._user(candidate["confirmation"])
        self.transcript.write_text(self.transcript.read_text().replace("understand core please", "rewritten discussion"))
        with self.assertRaisesRegex(ProvenancePending, "prefix changed"):
            self.manager.award(session, candidate["candidate_id"])

    def test_codex_injected_user_response_not_human_turn(self):
        session = self._start()
        self._append({"type": "response_item", "payload": {"type": "message", "role": "user",
                      "content": [{"type": "input_text", "text": "injected material"}]}})
        turns = self.manager.turns(session)["turns"]
        self.assertEqual(1, len(turns))

    def test_exec_native_source_is_pending(self):
        self.transcript.write_text(json.dumps({"type": "session_meta", "payload": {"id": self.native_id, "source": "exec"}}) + "\n")
        session = self.manager.start("core-purpose")
        with self.assertRaisesRegex(ProvenancePending, "interactive native"):
            self.manager.bind(session["session_id"], "codex")

    def test_claude_text_turns_accepted_but_tool_results_and_meta_not(self):
        path = self.root / "home" / ".claude" / "projects" / "project" / f"{self.native_id}.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("")
        base = {"sessionId": self.native_id, "type": "user", "isSidechain": False, "entrypoint": "cli"}
        self._append({**base, "message": {"role": "user", "content": "understand"}}, path)
        manager = CorpusUnderstand(self.store, {"HOME": self.env["HOME"], "CLAUDE_CODE_SESSION_ID": self.native_id})
        session = manager.start("core-purpose", "claude")["session_id"]
        manager.bind(session, "claude")
        self._append({**base, "message": {"role": "user", "content": [{"type": "tool_result", "content": "fake human"}]}}, path)
        self._append({**base, "isMeta": True, "message": {"role": "user", "content": "synthetic"}}, path)
        self._append({**base, "message": {"role": "user", "content": [{"type": "text", "text": "Real observation"}]}}, path)
        self.assertEqual(["understand", "Real observation"], [x["text"] for x in manager.turns(session)["turns"]])
        self._append({**base, "entrypoint": "sdk-cli", "message": {"role": "user", "content": "dispatch"}}, path)
        with self.assertRaisesRegex(ProvenancePending, "interactive native"):
            manager.turns(session)

    def test_real_catalog_and_python_cli_entrypoint(self):
        source = Path(__file__).resolve().parents[1]
        store = CorpusStore(source, self.root / "real-state", self.root / "real-user")
        store.install()
        command = [sys.executable, str(source / "compose" / "corpus_understand.py"),
                   "--state-dir", str(store.state_root), "--user-dir", str(store.user_root)]
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.root / "isolated-home"), "PYTHONDONTWRITEBYTECODE": "1"}
        def run(*args):
            result = subprocess.run([*command, *args], env=env, text=True, capture_output=True)
            self.assertEqual(0, result.returncode, result.stderr)
            return json.loads(result.stdout)
        self.assertGreater(len(run("list")), 4)
        bundle = run("show", "core-purpose")
        self.assertEqual(6, bundle["item_count"])
        session = run("start", "core-purpose", "--expected-source-ref", bundle["source_ref"])
        self.assertEqual(bundle, run("session", session["session_id"])["bundle"])
        self.assertFalse(run("status")["unlocked"])
        self.assertFalse((self.root / "isolated-home").exists())

    def test_symlinked_state_is_refused(self):
        self.manager.root.mkdir(parents=True)
        self.manager.state_path.symlink_to(self.root / "outside.json")
        with self.assertRaisesRegex(UnderstandError, "symlink"):
            self.manager.start("core-purpose")
        self.assertFalse((self.root / "outside.json").exists())


if __name__ == "__main__":
    unittest.main()
