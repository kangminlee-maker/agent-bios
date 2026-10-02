"""Decision records, their lifecycle events, and the state the owner reduces from both (C05).

The calls go through the journal, as V1's tests make them: `bench` and the source helpers of
`units/v1` build the state root, the keys and the checkouts, so a memory source is registered and
revised here exactly as V1 registers and revises any source.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
from unittest import mock

V1 = pathlib.Path(__file__).resolve().parents[1] / "v1"
if str(V1) not in sys.path:
    sys.path.insert(0, str(V1))

import bench  # noqa: E402
from bench import Killed  # noqa: E402
from test_sources import INSTANT, Base, Checkout, home, manifest, sha  # noqa: E402

from workenv import journal, memory, sources  # noqa: E402
from workenv.contracts import c01, c03, c04, c05, c07, canonical  # noqa: E402

OPEN, PUBLISH, APPLY, RESOLVE = ("workstream.open", "memory.record.publish",
                                 "memory.lifecycle.apply", "memory.state.resolve")
QUESTION = "Which journal mode does the local state database use?"
OTHER_QUESTION = "What does one commit cost on the local volume?"
WAL, ROLLBACK = "WAL, with synchronous FULL.", "A rollback journal with synchronous EXTRA."
HERE = {"dimension": "repository", "value": "this one"}
ELSEWHERE = {"dimension": "repository", "value": "another one"}
OCCURRED = "2026-09-21T10:00:00Z"
LATER = "2026-09-22T10:00:00Z"


def choice(scope: dict, text: str, question: str = QUESTION, **changes) -> dict:
    value = {"kind": "choice_record", "schema": 1, "home": scope, "workstream_ids": [],
             "question": question, "choice": text, "reason": "Measured here.",
             "applicability": {"states": "stated", "conditions": [HERE]}}
    value.update(changes)
    return value


def event(principal: str, record_id: str, did: str, **changes) -> dict:
    value = {"kind": "lifecycle_event", "schema": 1, "attributed_to": principal,
             "target": {"targets": "record", "record_id": record_id},
             "effect": {"did": did}, "evidence_digests": []}
    value.update(changes)
    return value


def asked(scopes: list[dict], question: str = QUESTION, **changes) -> dict:
    value = {"kind": "state_question", "schema": 1, "scopes": scopes,
             "concern": {"question": question, "conditions": [HERE]},
             "include_superseded": False}
    value.update(changes)
    return value


def standings(answer: dict) -> list[tuple[str, str]]:
    """(record_id, standing) of each entry of the state an answer returned."""
    return [(entry["record_id"], entry["standing"]) for entry in answer["returned"][0]["entries"]]


def codes(answer: dict) -> list[tuple[str, str]]:
    return [(gap["code"], gap["pointer"]) for gap in answer["returned"][0]["material_gaps"]]


class Memory(Base):
    """A managed memory source of the person's, registered and ready to publish to."""

    def setUp(self):
        super().setUp()
        self.memory_home, self.head = self.registered(role="memory")

    def registered(self, **changes):
        answer = self.register(home(self.person, self.source, **changes))
        return answer["returned"][0], answer["receipt"]["head_digest"]

    def publish(self, payload: dict, head: str | None = None, source: str | None = None,
                **options) -> dict:
        """One record or event published to the memory source the request targets."""
        target = {"resource_id": source or self.source,
                  "base": {"expects": "head", "head_digest": head or self.head}}
        event_kind = payload["kind"] == "lifecycle_event"
        operation = APPLY if event_kind else PUBLISH
        entry = memory.memory_lifecycle_apply if event_kind else memory.memory_record_publish
        return self.run_with(entry,
                             bench.request(self.person, operation, target, payload), [payload],
                             now=INSTANT, **options)

    def record(self, payload: dict, head: str | None = None) -> dict:
        """The record a publication stored; the source's head moves to its revision."""
        answer = self.publish(payload, head)
        self.head = answer["receipt"]["head_digest"]
        return answer["returned"][0]

    def state(self, question: dict) -> dict:
        return self.run_with(memory.memory_state_resolve,
                             bench.request(self.person, RESOLVE,
                                           {"resource_id": bench.ident("cnc")}, question),
                             [question], now=INSTANT)

    def member(self, revision: dict, path: str = memory.RECORDS_MEMBER) -> bytes:
        """The bytes a revision's bundle holds for one of its members."""
        return (self.bench.state / "objects" / canonical.digest_of(revision) / "members"
                / path).read_bytes()

    def lines(self, data: bytes) -> list[dict]:
        return [canonical.load(line) for line in data.splitlines() if line.strip()]

    def second_source(self, scope: dict | None = None) -> tuple[str, dict]:
        """Another managed memory source, in the scope it names, with its own head."""
        source_id = bench.ident("src")
        payload = home(self.person, source_id, role="memory")
        if scope is not None:
            payload.update(scope=scope, acceptance_authority=scope)
        answer = self.register(payload)
        return source_id, answer["receipt"]["head_digest"]


class Lanes(Memory):
    def test_a_lane_is_opened_with_the_id_and_the_instant_this_installation_owns(self):
        lane = {"kind": "workstream", "schema": 1, "name": "Storage", "purpose": "Where state is.",
                "home": self.person.scope}
        answer = self.run_with(memory.workstream_open,
                               bench.request(self.person, OPEN, self.person.principal, lane),
                               [lane], now=INSTANT)
        stored = answer["returned"][0]
        self.assertEqual({**stored, "workstream_id": None, "created_at": None},
                         {**lane, "workstream_id": None, "created_at": None})
        self.assertTrue(stored["workstream_id"].startswith("wst_"))
        self.assertEqual(stored["created_at"], INSTANT)
        self.assertEqual(self.bench.store().read("SELECT workstream_id FROM workstreams"),
                         [(stored["workstream_id"],)])

    def test_a_lane_opened_against_another_target_than_its_home_is_a_mismatch(self):
        lane = {"kind": "workstream", "schema": 1, "name": "Storage", "purpose": "Where state is.",
                "home": self.person.scope}
        answer = self.run_with(memory.workstream_open,
                               bench.request(self.person, OPEN, bench.ident("rep"), lane),
                               [lane], now=INSTANT)
        self.assertEqual([gap["code"] for gap in answer["result"]["outcome"]["material_gaps"]],
                         [c03.REQUEST_MISMATCH])

    def test_a_question_naming_a_lane_reduces_only_the_records_recorded_in_it(self):
        lane, other = bench.ident("wst"), bench.ident("wst")
        here = self.record(choice(self.person.scope, WAL, workstream_ids=[lane]))
        self.record(choice(self.person.scope, ROLLBACK, workstream_ids=[other]))
        answer = self.state(asked([self.person.scope], workstream_ids=[lane]))
        self.assertEqual(standings(answer), [(here["record_id"], "current")])
        self.assertEqual(codes(answer), [])


class Publishing(Memory):
    def test_a_published_record_keeps_what_was_submitted_and_gets_its_id_and_instant(self):
        submitted = choice(self.person.scope, WAL)
        stored = self.record(submitted)
        self.assertEqual({key: stored[key] for key in submitted}, submitted)
        self.assertTrue(stored["record_id"].startswith("rec_"))
        self.assertEqual(stored["recorded_at"], INSTANT)

    def test_the_same_choice_published_twice_is_two_records_and_neither_is_edited(self):
        first = self.record(choice(self.person.scope, WAL))
        second = self.record(choice(self.person.scope, WAL))
        self.assertNotEqual(first["record_id"], second["record_id"])
        held = self.bench.store().read("SELECT entry_id FROM memory_entries ORDER BY position")
        self.assertEqual(held, [(first["record_id"],), (second["record_id"],)])

    def test_a_publication_makes_a_new_revision_whose_manifest_it_returns(self):
        answer = self.publish(choice(self.person.scope, WAL))
        stored, revision = answer["returned"]
        self.assertEqual(revision["kind"], "source_manifest")
        self.assertEqual(revision["source_id"], self.source)
        self.assertEqual([member["path"] for member in revision["members"]],
                         [memory.RECORDS_MEMBER])
        self.assertEqual(answer["receipt"]["head_digest"], canonical.digest_of(revision))
        self.assertEqual([output["kind"] for output in answer["result"]["outputs"]],
                         ["choice_record", "source_manifest"])
        self.assertEqual(self.bench.store().read(
            "SELECT revision_digest FROM revisions WHERE source_id = ?", (self.source,)),
            [(canonical.digest_of(revision),)])

    def test_the_records_member_is_the_member_before_it_and_one_line_per_new_record(self):
        first = self.publish(choice(self.person.scope, WAL))
        self.head = first["receipt"]["head_digest"]
        before = self.member(first["returned"][1])
        second = self.publish(choice(self.person.scope, ROLLBACK))
        data = self.member(second["returned"][1])
        # the rule: the bytes before it, then one line, and the lines are the records published
        self.assertTrue(data.startswith(before))
        self.assertEqual(data[len(before):].count(b"\n"), 1)
        self.assertEqual(self.lines(data), [first["returned"][0], second["returned"][0]])
        member = second["returned"][1]["members"][0]
        self.assertEqual((member["size"], member["digest"]),
                         (len(data), hashlib.sha256(data).hexdigest()))

    def test_an_event_is_a_line_of_the_member_after_the_record_it_targets(self):
        record = self.record(choice(self.person.scope, WAL))
        answer = self.publish(event(self.person.principal, record["record_id"], "adopted"))
        self.assertEqual(self.lines(self.member(answer["returned"][1])),
                         [record, answer["returned"][0]])

    def test_a_record_another_checkout_wrote_into_the_member_stays_in_the_next_revision(self):
        theirs = {**choice(self.person.scope, "WAL, as they measured it."),
                  "record_id": bench.ident("rec"), "recorded_at": "2026-09-18T10:00:00Z"}
        data = canonical.encode(theirs) + b"\n"
        payload = manifest(self.source, {memory.RECORDS_MEMBER: data})
        target = {"resource_id": self.source,
                  "base": {"expects": "head", "head_digest": self.head}}
        pulled = self.run_with(sources.source_revision_commit,
                               bench.request(self.person, "source.revision.commit", target,
                                             payload), [payload],
                               members={sha(data): data}, now=INSTANT)
        self.head = pulled["receipt"]["head_digest"]
        mine = self.publish(choice(self.person.scope, WAL))
        self.assertEqual(self.lines(self.member(mine["returned"][1])),
                         [theirs, mine["returned"][0]])

    def test_a_previous_member_whose_bytes_are_not_held_cannot_be_extended(self):
        data = canonical.encode(choice(self.person.scope, WAL)) + b"\n"
        payload = manifest(self.source, {memory.RECORDS_MEMBER: data})
        target = {"resource_id": self.source,
                  "base": {"expects": "head", "head_digest": self.head}}
        pulled = self.run_with(sources.source_revision_commit,
                               bench.request(self.person, "source.revision.commit", target,
                                             payload), [payload], now=INSTANT)
        answer = self.publish(choice(self.person.scope, ROLLBACK),
                              head=pulled["receipt"]["head_digest"])
        self.assertEqual([gap["code"] for gap in answer["result"]["outcome"]["material_gaps"]],
                         [c01.REF_UNAVAILABLE])

    def test_an_event_is_its_own_record_and_its_own_revision(self):
        record = self.record(choice(self.person.scope, WAL))
        answer = self.publish(event(self.person.principal, record["record_id"], "adopted"))
        stored, revision = answer["returned"]
        self.assertTrue(stored["event_id"].startswith("evt_"))
        self.assertEqual(stored["recorded_at"], INSTANT)
        self.assertEqual([output["kind"] for output in answer["result"]["outputs"]],
                         ["lifecycle_event", "source_manifest"])
        self.assertEqual(revision["members"][0]["path"], memory.RECORDS_MEMBER)

    def test_a_source_this_installation_does_not_hold_is_unavailable(self):
        answer = self.publish(choice(self.person.scope, WAL), head=sha(b"nothing"),
                              source=bench.ident("src"))
        self.assertEqual([gap["code"] for gap in answer["result"]["outcome"]["material_gaps"]],
                         [c01.REF_UNAVAILABLE])

    def test_a_source_of_another_role_is_not_a_memory_source(self):
        source_id = bench.ident("src")
        answer = self.register(home(self.person, source_id, role="knowledge"))
        refused = self.publish(choice(self.person.scope, WAL), source=source_id,
                               head=answer["receipt"]["head_digest"])
        self.assertEqual([gap["code"] for gap in refused["result"]["outcome"]["material_gaps"]],
                         [c01.REF_UNAVAILABLE])

    def test_a_head_other_than_the_one_the_request_expects_is_stale(self):
        answer = self.publish(choice(self.person.scope, WAL), head=sha(b"another head"))
        self.assertEqual(answer["result"]["outcome"]["stage"], "stale")

    def test_a_source_a_package_published_is_the_publishers_bytes(self):
        source_id = bench.ident("src")
        answer = self.register(home(self.person, source_id, role="memory",
                                    home={"mode": "package_published",
                                          "package_id": bench.ident("pkg"),
                                          "publisher_evidence_digest": sha(b"publisher"),
                                          "license_conditions": "As the publisher states."}))
        refused = self.publish(choice(self.person.scope, WAL), source=source_id,
                               head=answer["receipt"]["head_digest"])
        self.assertEqual([gap["code"] for gap in refused["result"]["outcome"]["material_gaps"]],
                         [c01.PUBLISHER_BYTES_MODIFIED])


class Admitted(Memory):
    """A memory source authored here through `author_here`: it has no home record, so no
    document root, and the files it was admitted with are the person's."""

    # A file a person wrote, ending mid-line: a line appended to it would join that line.
    HAND = b'{"note": "kept by hand"}\n{"half'

    def admitted(self, members: dict[str, bytes], scope: dict | None = None,
                 mode: str = "managed") -> tuple[str, str]:
        source_id = bench.ident("src")
        submitted = manifest(source_id, members)
        request = {"kind": "source_request", "schema": 1, "role": "memory",
                   "destination": {"scope": scope or self.person.scope, "home_mode": mode},
                   "route": {"route": "author_here",
                             "manifest_digest": canonical.digest_of(submitted)}}
        target = {"resource_id": source_id, "base": {"expects": "absent"}}
        answer = self.run_with(
            sources.source_revision_admit,
            bench.request(self.person, "source.revision.admit", target, request),
            [request, submitted], now=INSTANT,
            members=None if mode == "repository_authored" else {
                sha(data): data for data in members.values()})
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", answer["result"])
        return source_id, answer["receipt"]["head_digest"]

    def test_records_go_beside_the_files_it_was_admitted_with_which_stay_as_they_are(self):
        source_id, head = self.admitted({"decisions.jsonl": self.HAND})
        answer = self.publish(choice(self.person.scope, WAL), head=head, source=source_id)
        revision = answer["returned"][1]
        line = canonical.encode(answer["returned"][0]) + b"\n"
        self.assertEqual(revision["members"], [
            {"path": "decisions.jsonl", "digest": sha(self.HAND), "size": len(self.HAND)},
            {"path": memory.RECORDS_MEMBER, "digest": sha(line), "size": len(line)}])
        self.assertEqual((self.member(revision, "decisions.jsonl"), self.member(revision)),
                         (self.HAND, line))

    def test_a_repository_source_admitted_here_gains_its_records_member_in_the_checkout(self):
        checkout = Checkout(self.scratch)
        checkout.write("decisions.jsonl", self.HAND)
        checkout.commit()
        self.bind(checkout)
        scope = {"layer": "repository", "repository_id": self.repository}
        source_id, head = self.admitted({"decisions.jsonl": self.HAND}, scope=scope,
                                        mode="repository_authored")
        first = self.publish(choice(scope, WAL), head=head, source=source_id)
        second = self.publish(choice(scope, WAL), head=first["receipt"]["head_digest"],
                              source=source_id)
        lines = b"".join(canonical.encode(answer["returned"][0]) + b"\n"
                         for answer in (first, second))
        self.assertEqual([member["path"] for member in second["returned"][1]["members"]],
                         ["decisions.jsonl", memory.RECORDS_MEMBER])
        self.assertEqual(((checkout.path / "decisions.jsonl").read_bytes(),
                          (checkout.path / memory.RECORDS_MEMBER).read_bytes()),
                         (self.HAND, lines))
        self.assertEqual(standings(self.state(asked([scope]))),
                         [(first["returned"][0]["record_id"], "current"),
                          (second["returned"][0]["record_id"], "current")])


class Authored(Memory):
    """A memory source authored in the person's checkout."""

    def setUp(self):
        super().setUp()
        self.checkout = Checkout(self.scratch)
        self.checkout.write("docs/adr/0007-journal-mode.md", b"# ADR 0007\n\nWAL.\n")
        self.checkout.commit()
        self.scope = {"layer": "repository", "repository_id": self.repository}

    def authored(self, root: str = "docs/decisions") -> tuple[str, str]:
        """A repository-authored memory source whose repository is bound here."""
        binding = self.bind(self.checkout)["returned"][0]
        source_id = bench.ident("src")
        answer = self.register(home(
            self.person, source_id, role="memory", scope=self.scope,
            acceptance_authority=self.scope,
            home={"mode": "repository_authored", "repository_id": self.repository,
                  "document_root": root,
                  "binding_evidence_digest": canonical.digest_of(binding)}))
        return source_id, answer["receipt"]["head_digest"]

    def test_a_repository_authored_source_whose_repository_is_not_bound_is_unverified(self):
        source_id = bench.ident("src")
        answer = self.register(home(
            self.person, source_id, role="memory", scope=self.scope,
            acceptance_authority=self.scope,
            home={"mode": "repository_authored", "repository_id": self.repository,
                  "document_root": "docs/decisions",
                  "binding_evidence_digest": sha(b"no binding")}))
        self.assertEqual(answer["result"]["outcome"]["stage"], "refused")

    def test_the_records_of_an_authored_source_are_written_inside_the_folder_its_home_names(self):
        source_id, head = self.authored()
        answer = self.publish(choice(self.scope, WAL), head=head, source=source_id)
        member = answer["returned"][1]["members"][0]
        data = (self.checkout.path / "docs/decisions/records.jsonl").read_bytes()
        self.assertEqual((member["path"], member["digest"], member["size"]),
                         ("docs/decisions/records.jsonl", hashlib.sha256(data).hexdigest(),
                          len(data)))
        self.assertEqual(data, canonical.encode(answer["returned"][0]) + b"\n")
        self.assertFalse((self.checkout.path / memory.RECORDS_MEMBER).exists())

    def test_the_revision_is_the_files_under_the_document_root_and_that_member(self):
        source_id, head = self.authored(root="docs/adr")
        answer = self.publish(choice(self.scope, WAL), head=head, source=source_id)
        adr = (self.checkout.path / "docs/adr/0007-journal-mode.md").read_bytes()
        records = (self.checkout.path / "docs/adr/records.jsonl").read_bytes()
        self.assertEqual(answer["returned"][1]["members"], [
            {"path": "docs/adr/0007-journal-mode.md",
             "digest": hashlib.sha256(adr).hexdigest(), "size": len(adr)},
            {"path": "docs/adr/records.jsonl",
             "digest": hashlib.sha256(records).hexdigest(), "size": len(records)}])
        self.assertEqual(self.member(answer["returned"][1],
                                     "docs/adr/0007-journal-mode.md"), adr)

    def test_existing_markdown_beside_the_member_is_carried_and_never_parsed(self):
        source_id, head = self.authored(root="docs/adr")
        answer = self.publish(choice(self.scope, WAL), head=head, source=source_id)
        state = self.state(asked([self.scope]))
        self.assertEqual(standings(state),
                         [(answer["returned"][0]["record_id"], "current")])
        self.assertIn(source_id, [frontier["source_id"]
                                  for frontier in state["returned"][0]["frontiers"]])

    def test_a_file_outside_the_document_root_is_no_member_of_the_source(self):
        source_id, head = self.authored(root="docs/adr")
        data = b"period,rate\n2026,0.1\n"
        self.checkout.write("tables/rates.csv", data)
        payload = manifest(source_id, {"tables/rates.csv": data})
        target = {"resource_id": source_id, "base": {"expects": "head", "head_digest": head}}
        pulled = self.run_with(sources.source_revision_commit,
                               bench.request(self.person, "source.revision.commit", target,
                                             payload), [payload], now=INSTANT)
        answer = self.publish(choice(self.scope, WAL), source=source_id,
                              head=pulled["receipt"]["head_digest"])
        self.assertEqual([member["path"] for member in answer["returned"][1]["members"]],
                         ["docs/adr/0007-journal-mode.md", "docs/adr/records.jsonl"])

    def test_a_file_the_person_adds_under_the_root_is_a_member_of_the_next_revision(self):
        source_id, head = self.authored(root="docs/adr")
        first = self.publish(choice(self.scope, WAL), head=head, source=source_id)
        self.checkout.write("docs/adr/0008-backups.md", b"# ADR 0008\n\nNightly.\n")
        second = self.publish(choice(self.scope, ROLLBACK), source=source_id,
                              head=first["receipt"]["head_digest"])
        self.assertEqual([member["path"] for member in second["returned"][1]["members"]],
                         ["docs/adr/0007-journal-mode.md", "docs/adr/0008-backups.md",
                          "docs/adr/records.jsonl"])

    def test_the_members_are_ordered_by_their_path_wherever_the_member_falls(self):
        source_id, head = self.authored(root="docs/adr")
        self.checkout.write("docs/adr/z-notes.md", b"# Notes\n")
        answer = self.publish(choice(self.scope, WAL), head=head, source=source_id)
        self.assertEqual([member["path"] for member in answer["returned"][1]["members"]],
                         ["docs/adr/0007-journal-mode.md", "docs/adr/records.jsonl",
                          "docs/adr/z-notes.md"])

    def test_records_another_checkout_wrote_are_read_from_the_revision_committed_here(self):
        source_id, head = self.authored()
        theirs = {**choice(self.scope, WAL), "record_id": bench.ident("rec"),
                  "recorded_at": "2026-09-18T10:00:00Z"}
        data = canonical.encode(theirs)
        self.checkout.write("docs/decisions/journal-mode.json", data)
        self.checkout.commit()
        payload = manifest(source_id, {"docs/decisions/journal-mode.json": data})
        answer = self.commit_to(payload, head, [theirs])
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed")
        state = self.state(asked([self.scope]))
        self.assertEqual(standings(state), [(theirs["record_id"], "current")])

    def commit_to(self, payload: dict, head: str, carried: list) -> dict:
        from workenv import sources
        target = {"resource_id": payload["source_id"],
                  "base": {"expects": "head", "head_digest": head}}
        return self.run_with(sources.source_revision_commit,
                             bench.request(self.person, "source.revision.commit", target,
                                           payload), [payload, *carried], now=INSTANT)


class Working(Authored):
    """The member of a repository-authored source, which is also the person's own file."""

    def setUp(self):
        super().setUp()
        self.memory_source, self.memory_head = self.authored()

    def to_source(self, payload: dict, head: str | None = None, **options) -> dict:
        return self.publish(payload, head=head or self.memory_head,
                            source=self.memory_source, **options)

    def at(self) -> pathlib.Path:
        return self.checkout.path / "docs/decisions/records.jsonl"

    def gaps(self, answer: dict) -> list[str]:
        return [gap["code"] for gap in answer["result"]["outcome"]["material_gaps"]]

    def test_the_member_is_written_once_the_unit_of_work_decided_and_leaves_nothing_staged(self):
        answer = self.to_source(choice(self.scope, WAL))
        self.assertEqual(self.at().read_bytes(),
                         canonical.encode(answer["returned"][0]) + b"\n")
        self.assertEqual([path.name for path in self.at().parent.iterdir()
                          if path.name != "records.jsonl"], [])

    def test_a_refused_publication_writes_nothing_into_the_checkout(self):
        first = self.to_source(choice(self.scope, WAL))
        before = self.at().read_bytes()
        stale = self.to_source(choice(self.scope, ROLLBACK), head=sha(b"another head"))
        self.assertEqual(stale["result"]["outcome"]["stage"], "stale")
        self.assertEqual(self.at().read_bytes(), before)
        self.assertEqual(first["receipt"]["head_digest"],
                         journal.head_of(self.bench.store(), self.memory_source))

    def test_nothing_is_written_when_the_unit_of_work_refuses_what_was_admitted_before_it(self):
        # The admission holds when it is forecast and when `prepare` reads it, and no longer
        # holds in the unit of work, where its answer stands. The member is the person's file,
        # so it must not have been written on the way.
        first = self.to_source(choice(self.scope, WAL))
        before = self.at().read_bytes()
        passes, held = [], memory.publishing

        def moved(call, store):
            passes.append(call)
            if len(passes) >= 3:
                return memory.refused(call, c01.REF_UNAVAILABLE), None
            return held(call, store)

        with mock.patch.object(memory, "publishing", moved):
            answer = self.to_source(choice(self.scope, ROLLBACK),
                                    head=first["receipt"]["head_digest"])
        self.assertEqual(self.gaps(answer), [c01.REF_UNAVAILABLE])
        self.assertEqual(self.at().read_bytes(), before)
        self.assertEqual(journal.head_of(self.bench.store(), self.memory_source),
                         first["receipt"]["head_digest"])

    def test_a_working_file_the_person_changed_is_not_written_over(self):
        answer = self.to_source(choice(self.scope, WAL))
        self.at().write_bytes(b"mine\n")
        refused = self.to_source(choice(self.scope, ROLLBACK),
                                 head=answer["receipt"]["head_digest"])
        self.assertEqual(self.gaps(refused), [c07.WORKING_BYTES_MOVED])
        self.assertEqual(self.at().read_bytes(), b"mine\n")

    def test_a_working_file_the_person_removed_is_not_written_afresh(self):
        answer = self.to_source(choice(self.scope, WAL))
        self.at().unlink()
        refused = self.to_source(choice(self.scope, ROLLBACK),
                                 head=answer["receipt"]["head_digest"])
        self.assertEqual(self.gaps(refused), [c07.WORKING_BYTES_MOVED])
        self.assertFalse(self.at().exists())

    def test_a_working_file_where_no_member_was_published_is_not_written_over(self):
        self.checkout.write("docs/decisions/records.jsonl",
                            b"the person's own notes\n")
        refused = self.to_source(choice(self.scope, WAL))
        self.assertEqual(self.gaps(refused), [c07.WORKING_BYTES_MOVED])
        self.assertEqual(self.at().read_bytes(), b"the person's own notes\n")

    def test_a_symbolic_link_on_the_members_path_is_never_written_through(self):
        outside = self.scratch / "outside"
        outside.mkdir()
        (outside / "records.jsonl").write_bytes(b"not in the checkout\n")
        for part in ("docs/decisions", "docs/decisions/records.jsonl"):
            with self.subTest(part=part):
                link = self.checkout.path / part
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(outside if part.endswith("decisions")
                                else outside / "records.jsonl")
                refused = self.to_source(choice(self.scope, WAL))
                self.assertEqual(self.gaps(refused), [c04.PROTECTED_ROOT_BYPASS])
                self.assertEqual((outside / "records.jsonl").read_bytes(),
                                 b"not in the checkout\n")
                link.unlink()

    def test_a_crash_between_the_rename_and_the_commit_holds_no_record_and_loses_none(self):
        first = self.to_source(choice(self.scope, WAL))
        head = first["receipt"]["head_digest"]
        before = self.at().read_bytes()
        with self.assertRaises(Killed):
            self.to_source(choice(self.scope, "WAL, with synchronous NORMAL."), head=head,
                           arm="in_txn_before_commit")
        # the person's file holds one line more than the revision this installation holds
        orphan = self.at().read_bytes()
        self.assertTrue(orphan.startswith(before))
        self.assertEqual(orphan[len(before):].count(b"\n"), 1)
        bench.restart(self.bench.state)
        self.assertEqual(journal.head_of(self.bench.store(), self.memory_source), head)
        # nothing reads that line as a record
        state = self.state(asked([self.scope]))
        self.assertEqual(standings(state), [(first["returned"][0]["record_id"], "current")])
        # and the next publication extends the member it published, over the line nobody held
        again = self.to_source(choice(self.scope, ROLLBACK), head=head)
        self.assertEqual(again["result"]["outcome"]["stage"], "committed")
        data = self.at().read_bytes()
        self.assertEqual(data, before + canonical.encode(again["returned"][0]) + b"\n")
        self.assertEqual(self.member(again["returned"][1], "docs/decisions/records.jsonl"),
                         data)


class Reducing(Memory):
    def test_a_state_over_sources_holding_nothing_has_no_entry_and_names_them_all(self):
        other, _ = self.second_source()
        answer = self.state(asked([self.person.scope]))
        found = answer["returned"][0]
        self.assertEqual((found["entries"], found["material_gaps"]), ([], []))
        self.assertEqual({frontier["source_id"] for frontier in found["frontiers"]},
                         {self.source, other})
        self.assertEqual(found["comparison"], {"compared": 0, "unreachable": 0})

    def test_every_entry_names_the_source_its_record_was_committed_to(self):
        mine = self.record(choice(self.person.scope, WAL))
        answer = self.state(asked([self.person.scope]))
        entry = answer["returned"][0]["entries"][0]
        self.assertEqual((entry["record_id"], entry["source_id"]), (mine["record_id"], self.source))
        self.assertIn(entry["source_id"],
                      {frontier["source_id"] for frontier in answer["returned"][0]["frontiers"]})

    def test_an_entry_names_the_source_holding_its_record_and_not_another_asked_one(self):
        scope = {"layer": "repository", "repository_id": self.repository}
        other, head = self.second_source(scope)
        mine = self.record(choice(self.person.scope, WAL))
        theirs = self.publish(choice(scope, WAL, reason="Measured there."), head=head,
                              source=other)["returned"][0]
        found = self.state(asked([self.person.scope, scope]))["returned"][0]
        self.assertEqual([(entry["record_id"], entry["source_id"]) for entry in found["entries"]],
                         [(mine["record_id"], self.source), (theirs["record_id"], other)])

    def test_a_record_answering_another_question_is_not_reduced_for_this_concern(self):
        self.record(choice(self.person.scope, "4.11 ms.", question=OTHER_QUESTION))
        mine = self.record(choice(self.person.scope, WAL))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(mine["record_id"], "current")])

    def test_a_record_whose_applicability_contradicts_the_concern_is_not_reduced(self):
        self.record(choice(self.person.scope, ROLLBACK,
                           applicability={"states": "stated", "conditions": [ELSEWHERE]}))
        mine = self.record(choice(self.person.scope, WAL))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(mine["record_id"], "current")])

    def test_a_record_stating_no_applicability_is_reduced_for_the_concern(self):
        mine = self.record(choice(self.person.scope, WAL,
                                  applicability={"states": "unstated"}))
        self.assertEqual(standings(self.state(asked([self.person.scope]))),
                         [(mine["record_id"], "current")])

    def test_the_same_choice_recorded_twice_is_compatible_and_both_stay_current(self):
        first = self.record(choice(self.person.scope, WAL))
        second = self.record(choice(self.person.scope, WAL, reason="Measured again."))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(first["record_id"], "current"),
                                             (second["record_id"], "current")])
        self.assertEqual(codes(answer), [])

    def test_incompatible_applicable_choices_leave_every_one_of_them_unresolved(self):
        first = self.record(choice(self.person.scope, WAL))
        second = self.record(choice(self.person.scope, ROLLBACK))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(first["record_id"], "unresolved"),
                                             (second["record_id"], "unresolved")])
        self.assertEqual(codes(answer), [(c05.CHOICE_CONFLICT_UNRESOLVED, "/entries/0"),
                                         (c05.CHOICE_CONFLICT_UNRESOLVED, "/entries/1")])

    def test_neither_the_scope_order_nor_the_later_record_selects_a_winner(self):
        scope = {"layer": "repository", "repository_id": self.repository}
        other, head = self.second_source(scope)
        mine = self.record(choice(self.person.scope, WAL))
        theirs = self.publish(choice(scope, ROLLBACK), head=head,
                              source=other)["returned"][0]
        for scopes in ([self.person.scope, scope], [scope, self.person.scope]):
            answer = self.state(asked(scopes))
            self.assertEqual({standing for _, standing in standings(answer)}, {"unresolved"})
            self.assertEqual([record for record, _ in standings(answer)],
                             [mine["record_id"], theirs["record_id"]]
                             if scopes[0] == self.person.scope
                             else [theirs["record_id"], mine["record_id"]])

    def test_a_withdrawn_record_never_becomes_current_again(self):
        mine = self.record(choice(self.person.scope, WAL))
        self.record(event(self.person.principal, mine["record_id"], "withdrawn"))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(mine["record_id"], "withdrawn")])
        self.assertEqual(answer["returned"][0]["entries"][0]["qualification"],
                         memory.WITHDRAWN_QUALIFICATION)
        self.assertEqual(codes(answer), [])

    def test_a_withdrawal_states_the_note_the_person_wrote_with_it(self):
        mine = self.record(choice(self.person.scope, WAL))
        self.record(event(self.person.principal, mine["record_id"], "withdrawn",
                          note="Withdrawn when a second process began reading."))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(answer["returned"][0]["entries"][0]["qualification"],
                         "Withdrawn when a second process began reading.")

    def test_a_withdrawal_is_never_filtered_away_and_the_earlier_choice_is_not_left_current(self):
        first = self.record(choice(self.person.scope, WAL))
        second = self.record(choice(self.person.scope, WAL, reason="Again."))
        self.record(event(self.person.principal, second["record_id"], "withdrawn"))
        answer = self.state(asked([self.person.scope], include_superseded=False))
        self.assertEqual(standings(answer), [(first["record_id"], "current"),
                                            (second["record_id"], "withdrawn")])

    def test_a_withdrawal_ends_a_conflict_without_anything_ranking_the_rest(self):
        first = self.record(choice(self.person.scope, WAL))
        second = self.record(choice(self.person.scope, ROLLBACK))
        self.record(event(self.person.principal, second["record_id"], "withdrawn"))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(first["record_id"], "current"),
                                            (second["record_id"], "withdrawn")])
        self.assertEqual(codes(answer), [])

    def test_a_record_replaced_whole_is_superseded_by_the_successor_it_names(self):
        first = self.record(choice(self.person.scope, WAL))
        second = self.record(choice(self.person.scope, ROLLBACK,
                                    replaces={"record_id": first["record_id"],
                                              "extent": "whole"}))
        answer = self.state(asked([self.person.scope], include_superseded=True))
        self.assertEqual(standings(answer), [(first["record_id"], "superseded"),
                                            (second["record_id"], "current")])
        self.assertEqual(answer["returned"][0]["entries"][0]["superseded_by"],
                         second["record_id"])
        self.assertEqual(codes(answer), [])

    def test_a_superseded_entry_is_clipped_only_when_its_successor_is_among_the_entries(self):
        lane, other = bench.ident("wst"), bench.ident("wst")
        first = self.record(choice(self.person.scope, WAL, workstream_ids=[lane, other]))
        second = self.record(choice(self.person.scope, ROLLBACK, workstream_ids=[lane],
                                    replaces={"record_id": first["record_id"],
                                              "extent": "whole"}))
        asked_both = self.state(asked([self.person.scope], workstream_ids=[lane]))
        self.assertEqual(standings(asked_both), [(second["record_id"], "current")])
        self.assertEqual(asked_both["returned"][0]["comparison"],
                         {"compared": 2, "unreachable": 0})
        asked_other = self.state(asked([self.person.scope], workstream_ids=[other]))
        self.assertEqual(standings(asked_other), [(first["record_id"], "superseded")])

    def test_an_event_in_another_source_changes_the_state_of_the_record_it_targets(self):
        other, head = self.second_source()
        mine = self.record(choice(self.person.scope, WAL))
        self.publish(event(self.person.principal, mine["record_id"], "withdrawn"),
                     head=head, source=other)
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(mine["record_id"], "withdrawn")])

    def test_more_than_one_successor_leaves_the_record_and_both_successors_unresolved(self):
        first = self.record(choice(self.person.scope, WAL))
        larger = self.record(choice(self.person.scope, "WAL with NORMAL.",
                                    replaces={"record_id": first["record_id"],
                                              "extent": "whole"}))
        off = self.record(choice(self.person.scope, ROLLBACK,
                                 replaces={"record_id": first["record_id"],
                                           "extent": "whole"}))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(first["record_id"], "unresolved"),
                                            (larger["record_id"], "unresolved"),
                                            (off["record_id"], "unresolved")])
        self.assertEqual(codes(answer), [(c05.COMPETING_SUCCESSORS, f"/entries/{index}")
                                         for index in range(3)])
        self.assertEqual(answer["returned"][0]["entries"][0]["qualification"],
                         "Two records declare they replace it whole.")

    def test_competing_successors_are_not_compared_for_a_conflict_at_all(self):
        first = self.record(choice(self.person.scope, WAL))
        for text in ("WAL with NORMAL.", ROLLBACK):
            self.record(choice(self.person.scope, text,
                               replaces={"record_id": first["record_id"], "extent": "whole"}))
        answer = self.state(asked([self.person.scope]))
        self.assertNotIn(c05.CHOICE_CONFLICT_UNRESOLVED, [code for code, _ in codes(answer)])

    def test_an_adoption_and_a_withdrawal_stating_one_instant_cannot_both_hold(self):
        mine = self.record(choice(self.person.scope, WAL))
        for did in ("adopted", "withdrawn"):
            self.record(event(self.person.principal, mine["record_id"], did,
                              occurred_at=OCCURRED))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(mine["record_id"], "unresolved")])
        self.assertEqual(codes(answer), [(c05.LIFECYCLE_CONTRADICTION, "/entries/0")])

    def test_a_withdrawal_stating_a_later_instant_than_the_adoption_is_no_contradiction(self):
        mine = self.record(choice(self.person.scope, WAL))
        self.record(event(self.person.principal, mine["record_id"], "adopted",
                          occurred_at=OCCURRED))
        self.record(event(self.person.principal, mine["record_id"], "withdrawn",
                          occurred_at=LATER))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(mine["record_id"], "withdrawn")])
        self.assertEqual(codes(answer), [])

    def test_a_contradicted_record_is_still_compared_for_a_conflict(self):
        first = self.record(choice(self.person.scope, WAL))
        second = self.record(choice(self.person.scope, ROLLBACK))
        for did in ("adopted", "withdrawn"):
            self.record(event(self.person.principal, second["record_id"], did,
                              occurred_at=OCCURRED))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(first["record_id"], "unresolved"),
                                            (second["record_id"], "unresolved")])
        self.assertEqual(codes(answer), [(c05.CHOICE_CONFLICT_UNRESOLVED, "/entries/0"),
                                         (c05.CHOICE_CONFLICT_UNRESOLVED, "/entries/1"),
                                         (c05.LIFECYCLE_CONTRADICTION, "/entries/1")])

    def test_a_stated_reliance_on_a_record_this_reader_cannot_reach_is_counted(self):
        missing = bench.ident("rec")
        mine = self.record(choice(self.person.scope, WAL, basis=[
            {"relies_on": "record", "record_id": missing, "as_stated": "The old benchmark."}]))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(mine["record_id"], "unresolved")])
        self.assertEqual(codes(answer), [(c05.BASIS_TARGET_MISSING, "/entries/0")])
        self.assertEqual(answer["returned"][0]["comparison"],
                         {"compared": 2, "unreachable": 1})

    def test_a_reliance_on_a_record_this_reader_holds_is_no_gap(self):
        held = self.record(choice(self.person.scope, "4.11 ms.", question=OTHER_QUESTION))
        mine = self.record(choice(self.person.scope, WAL, basis=[
            {"relies_on": "record", "record_id": held["record_id"],
             "as_stated": "4.11 ms per commit."}]))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(mine["record_id"], "current")])
        self.assertEqual((codes(answer), answer["returned"][0]["comparison"]),
                         ([], {"compared": 1, "unreachable": 0}))

    def test_records_whose_stated_reliance_closes_on_itself_are_unresolved(self):
        source_id, head = self.second_source()
        first, second = bench.ident("rec"), bench.ident("rec")
        pulled = [{**choice(self.person.scope, "Every 1000 pages.", question="When?"),
                   "record_id": first, "recorded_at": "2026-09-18T10:00:00Z",
                   "basis": [{"relies_on": "record", "record_id": second,
                              "as_stated": "The trigger."}]},
                  {**choice(self.person.scope, "On page count.", question="When?"),
                   "record_id": second, "recorded_at": "2026-09-18T10:00:00Z",
                   "basis": [{"relies_on": "record", "record_id": first,
                              "as_stated": "The interval."}]}]
        self.carry(source_id, head, pulled)
        answer = self.state(asked([self.person.scope], question="When?"))
        self.assertEqual(standings(answer), [(first, "unresolved"), (second, "unresolved")])
        self.assertEqual(codes(answer), [(c05.BASIS_CYCLE, "/entries/0"),
                                         (c05.BASIS_CYCLE, "/entries/1")])

    def test_a_chain_of_reliance_that_does_not_close_is_no_cycle(self):
        held = self.record(choice(self.person.scope, "4.11 ms.", question=OTHER_QUESTION))
        mine = self.record(choice(self.person.scope, WAL, basis=[
            {"relies_on": "record", "record_id": held["record_id"], "as_stated": "Measured."}]))
        self.record(choice(self.person.scope, WAL, reason="Carried on.", basis=[
            {"relies_on": "record", "record_id": mine["record_id"], "as_stated": "The choice."}]))
        self.assertEqual({standing for _, standing in standings(self.state(
            asked([self.person.scope])))}, {"current"})

    def carry(self, source_id: str, head: str, records: list[dict]) -> dict:
        """One revision of a managed source whose members are the records themselves, as a
        person's own files hold them."""
        from workenv import sources
        members = {f"records/{index}.json": canonical.encode(record)
                   for index, record in enumerate(records)}
        payload = manifest(source_id, members)
        target = {"resource_id": source_id, "base": {"expects": "head", "head_digest": head}}
        return self.run_with(sources.source_revision_commit,
                             bench.request(self.person, "source.revision.commit", target,
                                           payload), [payload], members={
                                 sha(data): data for data in members.values()}, now=INSTANT)

    def test_a_member_the_contract_refuses_holds_no_record_and_the_resolve_answers(self):
        source_id, head = self.second_source()
        broken = {"kind": "choice_record", "schema": 1, "home": self.person.scope,
                  "workstream_ids": [], "record_id": bench.ident("rec"),
                  "recorded_at": "2026-09-18T10:00:00Z"}
        self.carry(source_id, head, [broken])
        mine = self.record(choice(self.person.scope, WAL))
        answer = self.state(asked([self.person.scope]))
        self.assertEqual(standings(answer), [(mine["record_id"], "current")])
        self.assertEqual(codes(answer), [])
        self.assertEqual(answer["returned"][0]["comparison"],
                         {"compared": 1, "unreachable": 0})

    def test_a_member_that_is_no_json_at_all_holds_no_record(self):
        source_id, head = self.second_source()
        payload = manifest(source_id, {"records/notes.md": b"# Notes\n\nNothing typed.\n"})
        target = {"resource_id": source_id, "base": {"expects": "head", "head_digest": head}}
        self.run_with(sources.source_revision_commit,
                      bench.request(self.person, "source.revision.commit", target, payload),
                      [payload], members={sha(b"# Notes\n\nNothing typed.\n"):
                                          b"# Notes\n\nNothing typed.\n"}, now=INSTANT)
        mine = self.record(choice(self.person.scope, WAL))
        self.assertEqual(standings(self.state(asked([self.person.scope]))),
                         [(mine["record_id"], "current")])

    def test_no_entry_a_gap_names_is_current(self):
        self.record(choice(self.person.scope, WAL))
        self.record(choice(self.person.scope, ROLLBACK))
        answer = self.state(asked([self.person.scope]))
        found = answer["returned"][0]
        named = {int(gap["pointer"].rsplit("/", 1)[1]) for gap in found["material_gaps"]}
        self.assertTrue(named)
        self.assertEqual([found["entries"][index]["standing"] for index in named],
                         ["unresolved"] * len(named))

    def test_the_state_names_the_question_it_answers_and_when_it_was_prepared(self):
        question = asked([self.person.scope])
        found = self.state(question)["returned"][0]
        self.assertEqual(found["question_digest"], canonical.digest_of(question))
        self.assertEqual(found["prepared_at"], INSTANT)

    def test_a_frontier_names_each_source_at_the_head_the_journal_holds_for_it(self):
        self.record(choice(self.person.scope, WAL))
        found = self.state(asked([self.person.scope]))["returned"][0]
        self.assertEqual(found["frontiers"], [
            {"source_id": self.source,
             "checkpoint_digest": journal.head_of(self.bench.store(), self.source)}])

    def test_resolving_commits_nothing_and_reaches_no_provider(self):
        answer = self.state(asked([self.person.scope]))
        self.assertEqual((answer["result"]["local_effect"], answer["result"]["provider_effect"]),
                         ("none", "not_applicable"))
        self.assertIsNone(answer["receipt"])
