#!/usr/bin/env python3
"""Isolated bundle, provenance, and failure-path controls for understand!."""
from __future__ import annotations

import copy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from compose.corpus_store import CorpusStore
from compose.corpus_understand import (CorpusUnderstand, UnderstandError, ProvenancePending,
                                      LEARNING_POLICY, MAX_OUTPUT_BYTES, MAX_PROMPT_BYTES,
                                      MAX_PAGE_BYTES, _json_text, _page)
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

    def test_enablement_does_not_remove_or_repin_learning_bundles(self):
        before = self.manager.list_bundles()
        self.assertGreater(len(before), 0)
        ref = "@agent-bios/core:rule-003"
        plan = self.store.plan({"operation": "enable", "items": {ref: False}})
        self.store.apply(plan["plan_id"], plan["expected_revision"])
        self.assertFalse(self.store.show(ref)["enabled"])
        self.assertEqual(before, self.manager.list_bundles())
        self.assertTrue(any(ref == item["ref"] for bundle in self.manager._bundles() for item in bundle["items"]))

    def _append(self, value, path=None):
        with (path or self.transcript).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value) + "\n")

    def _user(self, text):
        self._append({"type": "event_msg", "payload": {"type": "user_message", "message": text}})

    def _assistant(self, text):
        self._append({"type": "response_item", "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": text}]}})

    def _cli(self, *args):
        from compose import corpus_understand
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(corpus_understand, "CorpusUnderstand", return_value=self.manager), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = corpus_understand.main(list(args))
        self.assertLessEqual(len(output.getvalue().encode("utf-8")), MAX_OUTPUT_BYTES)
        return code, output.getvalue(), errors.getvalue()

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
        for text in ("learning DATA", "10 questions per source bullet INCLUDING all followups",
                     "Respect requests to pause", "Do not ask about every ambiguity"):
            self.assertIn(text, prompt.read_text())

    def _read_all(self, session, *, ref=None, member=None, limit=1024):
        pages, offset, digest = [], 0, None
        while True:
            page = self.manager.read(session, ref, member, offset=offset, limit_bytes=limit,
                                     expected_sha256=digest)
            self.assertLessEqual(len(_json_text(page).encode("utf-8")), MAX_OUTPUT_BYTES)
            self.assertEqual(offset, page["offset"])
            self.assertEqual(len(page["text"].encode("utf-8")), page["end_offset"] - offset)
            pages.append(page["text"])
            if page["eof"]:
                self.assertIsNone(page["next_offset"])
                self.assertEqual(page["total_bytes"], page["end_offset"])
                return "".join(pages)
            self.assertGreater(page["next_offset"], offset)
            offset, digest = page["next_offset"], page["resource_sha256"]

    def test_large_single_line_unicode_members_are_exact_pinned_pages(self):
        ref = "@agent-bios/core:rule-004"
        text = "한글😀\"\\" * 40000 + "PINNED-END"
        self.assertGreater(len(text.encode("utf-8")), 353 * 1024)
        self.assertNotIn("\n", text)
        self._edit(ref, {"body": text})
        session = self.manager.start("core-purpose")
        before = self.manager._path("sessions", session["session_id"]).read_bytes()
        self.assertLessEqual(len(session["prompt"].encode("utf-8")), MAX_PROMPT_BYTES)
        self.assertNotIn("PINNED-END", session["prompt"])
        manifest = json.loads(self._read_all(session["session_id"], limit=256))
        self.assertNotIn("PINNED-END", json.dumps(manifest))
        self.assertEqual(session["bundle"]["source_ref"], manifest["bundle"]["source_ref"])
        row = next(x for x in manifest["items"] if x["ref"] == ref)
        self.assertTrue(row["members"])
        self._edit(ref, {"body": "NEW-AUTHORING"})
        item = next(x for x in session["bundle"]["items"] if x["ref"] == ref)
        self.assertEqual(item["body"], self._read_all(session["session_id"], ref=ref, limit=MAX_PAGE_BYTES))
        for member in row["members"]:
            self.assertEqual(item["members"][member["name"]],
                             self._read_all(session["session_id"], ref=ref, member=member["name"], limit=MAX_PAGE_BYTES))
        self.assertEqual(before, self.manager._path("sessions", session["session_id"]).read_bytes())

    def test_json_overhead_and_utf8_cursors_are_bounded_without_data_loss(self):
        text = ("\0\t\n\"\\😀한글" * 5000) + "END"
        offset, chunks, digest = 0, [], None
        while True:
            page = _page(text, {"format": "text"}, offset=offset, limit_bytes=MAX_PAGE_BYTES,
                         expected_sha256=digest)
            serialized = _json_text(page).encode("utf-8")
            self.assertLessEqual(len(serialized), MAX_OUTPUT_BYTES)
            self.assertTrue(all(len(line) <= MAX_OUTPUT_BYTES for line in serialized.splitlines()))
            chunks.append(page["text"])
            if page["eof"]:
                break
            self.assertGreater(page["next_offset"], offset)
            offset, digest = page["next_offset"], page["resource_sha256"]
        self.assertEqual(text, "".join(chunks))
        with self.assertRaisesRegex(UnderstandError, "UTF-8 boundary"):
            _page("😀body", {}, offset=1)
        with self.assertRaisesRegex(UnderstandError, "resource changed"):
            _page(text, {}, expected_sha256="wrong")
        for limit in (0, 255, MAX_PAGE_BYTES + 1):
            with self.assertRaises(UnderstandError):
                _page(text, {}, limit_bytes=limit)
        with self.assertRaisesRegex(UnderstandError, "metadata"):
            _page("x", {"title": "q" * MAX_OUTPUT_BYTES})

    def test_old_full_prompt_sessions_get_compact_entry_without_rewrite(self):
        session = self.manager.start("core-purpose")
        record_path = self.manager._path("sessions", session["session_id"])
        old = json.loads(record_path.read_text())
        old.pop("learning_policy")
        old["prompt"] = "OLD FULL PROMPT " + "x" * (353 * 1024)
        Path(old["prompt_path"]).write_text(old["prompt"])
        record_path.write_text(json.dumps(old, ensure_ascii=False))
        retained = {path: path.read_bytes() for path in (record_path, Path(old["prompt_path"]))}
        view = self.manager.session_view(self.manager.session(session["session_id"]))
        self.assertTrue(view["legacy_prompt"])
        self.assertNotIn("items", view["bundle"])
        self.assertLess(len(_json_text(view).encode("utf-8")), MAX_OUTPUT_BYTES)
        self.assertNotIn("OLD FULL PROMPT", view["entry_prompt"])
        self.assertEqual(old["bundle"]["source_ref"], view["bundle"]["source_ref"])
        self.assertTrue(json.loads(self._read_all(session["session_id"]))["items"])
        self.assertEqual(retained, {path: path.read_bytes() for path in retained})

    def test_finite_contract_has_a_ceiling_and_a_natural_end_in_all_tutor_entries(self):
        session = self.manager.start("core-purpose")
        self.assertEqual(10, session["learning_policy"]["max_questions_per_bullet"])
        self.assertTrue(LEARNING_POLICY["followups_count_toward_limit"])
        self.assertFalse(LEARNING_POLICY["question_after_every_reply"])
        source = Path(__file__).resolve().parents[1]
        texts = [session["prompt"], (source / "claude/skills/understand/SKILL.md").read_text(),
                 (source / "docs/understand.md").read_text()]
        for text in texts:
            flat = " ".join(text.split()).lower()
            self.assertIn("10", flat)
            self.assertIn("followup", flat)
            self.assertIn("clarification", flat)
            self.assertIn("ceiling, not a target", flat)
            self.assertIn("without a compulsory followup", flat)
            self.assertNotIn("end every active learning turn", flat)
            self.assertNotIn("after every learning reply", flat)

    def test_cli_transcript_pages_require_one_snapshot_and_preserve_every_turn(self):
        from compose import corpus_understand
        session = self._start()
        self._assistant("Earlier explanation " + "한😀\"" * 12000)
        self._user("My independent observation " + "x" * 40000)
        expected = self.manager.turns(session)
        offset, digest, chunks = 0, None, []

        def invoke(*args):
            output, errors = io.StringIO(), io.StringIO()
            with mock.patch.object(corpus_understand, "CorpusUnderstand", return_value=self.manager), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                result = corpus_understand.main([*args])
            self.assertLessEqual(len(output.getvalue().encode("utf-8")), MAX_OUTPUT_BYTES)
            return result, output.getvalue(), errors.getvalue()

        while True:
            args = ["turns", session, "--offset", str(offset)]
            if digest:
                args += ["--expected-sha256", digest]
            result, output, errors = invoke(*args)
            self.assertEqual(0, result, errors)
            page = json.loads(output)
            chunks.append(page["text"])
            if page["eof"]:
                break
            offset, digest = page["next_offset"], page["resource_sha256"]
        self.assertEqual(expected, json.loads("".join(chunks)))
        result, output, errors = invoke("turns", session, "--offset", "256")
        self.assertEqual(1, result)
        self.assertEqual("", output)
        self.assertIn("require --expected-sha256", errors)
        self._assistant("A later turn changes the transcript snapshot.")
        result, output, errors = invoke("turns", session, "--offset", str(offset), "--expected-sha256", digest)
        self.assertEqual(1, result)
        self.assertEqual("", output)
        self.assertIn("resource changed", errors)

    def test_cli_refuses_oversized_metadata_without_partial_json(self):
        from compose import corpus_understand
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(corpus_understand, "CorpusUnderstand", return_value=self.manager), \
                mock.patch.object(self.manager, "list_bundles", return_value=[{"title": "😀" * MAX_OUTPUT_BYTES}]), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = corpus_understand.main(["list"])
        self.assertEqual(1, code)
        self.assertEqual("", output.getvalue())
        self.assertIn("bounded output limit", errors.getvalue())

    def test_oversized_proposal_is_refused_before_persistence_and_can_be_shortened(self):
        session = self._start()
        self._assistant("This bundle connects clarification to the user's goal.")
        self._user("Questions that cannot change an important decision only add distraction.")
        proposal = self._proposal(session)
        proposal["impact"] = "한글 impact " * 6000
        path = self.root / "proposal.json"
        path.write_text(json.dumps(proposal))
        before = {p: p.read_bytes() for p in self.manager.root.rglob("*") if p.is_file()}
        for _ in range(2):
            code, output, errors = self._cli("propose", session, "--file", str(path))
            self.assertEqual(1, code)
            self.assertEqual("", output)
            self.assertIn("bounded review limit", errors)
            self.assertFalse((self.manager.root / "discoveries").exists())
            self.assertEqual(before, {p: p.read_bytes() for p in self.manager.root.rglob("*") if p.is_file()})
        proposal["impact"] = "Unnecessary questions consume attention."
        path.write_text(json.dumps(proposal))
        code, output, errors = self._cli("propose", session, "--file", str(path))
        self.assertEqual(0, code, errors)
        result = json.loads(output)
        self.assertTrue(self.manager._path("discoveries", result["candidate_id"]).is_file())
        self.assertEqual("save understand " + result["candidate_id"], result["confirmation"])

    def test_legacy_oversized_proposal_review_is_read_only_and_award_returns_compact_success(self):
        session = self._start()
        candidate = self._candidate(session)
        record_path = self.manager._path("discoveries", candidate["candidate_id"])
        legacy = json.loads(record_path.read_text())
        legacy["proposal"]["impact"] = "legacy impact " * 5000 + "LEGACY-NOTE-END"
        record_path.write_text(json.dumps(legacy))
        before = record_path.read_bytes()
        proposal_path = self.root / "legacy-proposal.json"
        proposal_path.write_text(json.dumps(legacy["proposal"]))
        code, output, errors = self._cli("propose", session, "--file", str(proposal_path))
        self.assertEqual(1, code)
        self.assertEqual("", output)
        self.assertIn("bounded output limit", errors)
        self.assertEqual(before, record_path.read_bytes())
        self.assertEqual(0, self.store.status()["personal_items"])
        self._user(legacy["confirmation"])
        code, output, errors = self._cli("award", session, candidate["candidate_id"])
        self.assertEqual(0, code, errors)
        result = json.loads(output)
        self.assertTrue(result["unlocked"])
        self.assertNotIn("LEGACY-NOTE-END", output)
        self.assertIn("LEGACY-NOTE-END", self.store.show(result["note_ref"])["item"]["body"])
        code, output, errors = self._cli("award", session, candidate["candidate_id"])
        self.assertEqual(0, code, errors)
        self.assertTrue(json.loads(output)["duplicate"])
        self.assertEqual(1, self.store.status()["personal_items"])

    def test_oversized_start_and_bind_metadata_refuse_before_state_changes(self):
        bundle = self.manager.show("core-purpose")
        bundle["title"] = "😀" * MAX_OUTPUT_BYTES
        with mock.patch.object(self.manager, "show", return_value=bundle):
            code, output, errors = self._cli("start", "core-purpose")
        self.assertEqual(1, code)
        self.assertEqual("", output)
        self.assertIn("no session was created", errors)
        self.assertFalse(self.manager.root.exists())
        session = self.manager.start("core-purpose", "codex")
        record_path = self.manager._path("sessions", session["session_id"])
        before = record_path.read_bytes()
        cursor, turns = self.manager._transcript("codex")
        cursor["extra_metadata"] = "x" * MAX_OUTPUT_BYTES
        with mock.patch.object(self.manager, "_transcript", return_value=(cursor, turns)):
            code, output, errors = self._cli("bind", session["session_id"], "--host", "codex")
        self.assertEqual(1, code)
        self.assertEqual("", output)
        self.assertIn("binding was not saved", errors)
        self.assertEqual(before, record_path.read_bytes())

    def test_invalid_legacy_award_source_metadata_fails_before_note_or_award(self):
        session = self._start()
        candidate = self._candidate(session)
        record_path = self.manager._path("discoveries", candidate["candidate_id"])
        record = json.loads(record_path.read_text())
        record["source_ref"] = "bad-source" * 6000
        record_path.write_text(json.dumps(record))
        self._user(record["confirmation"])
        before = record_path.read_bytes()
        code, output, errors = self._cli("award", session, candidate["candidate_id"])
        self.assertEqual(1, code)
        self.assertEqual("", output)
        self.assertIn("does not match the pinned", errors)
        self.assertEqual(before, record_path.read_bytes())
        self.assertEqual(0, self.store.status()["personal_items"])
        self.assertFalse(self.manager.status()["unlocked"])

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
            self.assertLessEqual(len(result.stdout.encode("utf-8")), MAX_OUTPUT_BYTES)
            return json.loads(result.stdout)
        self.assertGreater(len(run("list")), 4)
        bundle = run("show", "core-purpose")
        self.assertEqual(6, bundle["item_count"])
        session = run("start", "core-purpose", "--expected-source-ref", bundle["source_ref"])
        self.assertNotIn("items", session["bundle"])
        self.assertEqual(bundle, run("session", session["session_id"])["bundle"])
        self.assertFalse(run("status")["unlocked"])
        huge = "한글😀single-line" * 25000
        plan = store.plan({"operation": "create", "item": {"title": "Large learning guide", "body": huge,
                           "kind": "guide", "surface": "requested", "domains": ["large-learning"]}})
        created = store.apply(plan["plan_id"], plan["expected_revision"])
        pinned = run("start", "@local/personal/large-learning", "--host", "claude")
        self.assertGreater(len(huge.encode("utf-8")), 353 * 1024)
        self.assertNotIn(huge[:100], pinned["entry_prompt"])
        page = run("read", pinned["session_id"], "--ref", created["details"]["ref"], "--limit-bytes", "1024")
        self.assertFalse(page["eof"])
        self.assertGreater(page["next_offset"], 0)
        self.assertEqual(huge.encode("utf-8")[:page["end_offset"]].decode("utf-8"), page["text"])
        second = run("read", pinned["session_id"], "--ref", created["details"]["ref"],
                     "--offset", str(page["next_offset"]), "--expected-sha256", page["resource_sha256"])
        self.assertEqual(page["end_offset"], second["offset"])
        self.assertFalse((self.root / "isolated-home").exists())

    def test_symlinked_state_is_refused(self):
        self.manager.root.mkdir(parents=True)
        self.manager.state_path.symlink_to(self.root / "outside.json")
        with self.assertRaisesRegex(UnderstandError, "symlink"):
            self.manager.start("core-purpose")
        self.assertFalse((self.root / "outside.json").exists())


if __name__ == "__main__":
    unittest.main()
