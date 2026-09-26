"""The request journal: read, held and answered once, and what it answers by itself."""
from __future__ import annotations

import unittest

import bench
from bench import Bench, Killed, Person

from workenv import journal, storage
from workenv.contracts import c03, canonical

RENAME = "access.profile.rename"


def label(name: str = "Laptop") -> dict:
    return {"kind": "profile_label", "schema": 1, "display_name": name}


class Entry:
    """An entry that answers with what it is told to, and counts its calls."""

    def __init__(self, answer):
        self.make, self.calls = answer, 0

    def __call__(self, call):
        self.calls += 1
        return self.make(call)


def commits(call):
    return journal.committed(call, [journal.payload(call)])


class Base(unittest.TestCase):
    def setUp(self):
        self.bench = Bench()
        self.person = Person()

    def tearDown(self):
        self.bench.close()

    def rename(self, payload=None, **changes):
        payload = label() if payload is None else payload
        return bench.request(self.person, RENAME, self.person.profile, payload, **changes), payload

    def query(self, request_id: str) -> dict:
        asked = {"kind": "operation_query", "schema": 1, "request_id": request_id}
        return self.bench.run(None, bench.request(self.person, "operation.query", request_id,
                                                  asked), [asked])

    def held_count(self) -> int:
        return self.bench.store().read("SELECT COUNT(*) FROM requests")[0][0]


class Reading(Base):
    def test_an_unknown_field_on_the_request_is_refused_and_nothing_is_held(self):
        sealed, payload = self.rename(access_token="tok")
        entry = Entry(commits)
        call = self.bench.call(sealed, [payload])
        answer = journal.layer_journal(call, entry)
        self.assertEqual(answer, {"refused": [{"record": "request", "code": "unknown_field",
                                               "pointer": "/access_token"}]})
        self.assertEqual((entry.calls, call.admissions, self.held_count()), (0, 0, 0))
        self.assertEqual(self.query(sealed["request_id"])["returned"][0]["kind"],
                         "request_not_held")

    def test_a_payload_is_read_in_submit_mode(self):
        payload = bench.binding(self.person.principal, bench.example_key("A"))
        payload["binding_id"] = bench.ident("bnd")
        sealed = bench.request(self.person, "identity.binding.add", self.person.principal,
                               payload)
        answer = self.bench.run(Entry(commits), sealed, [payload])
        self.assertIn({"record": "carried/0", "code": "runtime_owned_field",
                       "pointer": "/binding_id"}, answer["refused"])

    def test_a_version_this_reader_does_not_hold_is_refused_at_its_schema(self):
        payload = label()
        payload["schema"] = 2
        sealed, _ = self.rename(payload)
        answer = self.bench.run(Entry(commits), sealed, [payload])
        self.assertEqual(answer["refused"], [{"record": "carried/0",
                                              "code": "unsupported_schema_version",
                                              "pointer": "/schema"}])

    def test_another_carried_record_is_refused_only_when_it_is_no_record_either_way(self):
        sealed, payload = self.rename()
        submitted = bench.binding(self.person.principal, bench.example_key("B"))
        answer = self.bench.run(Entry(commits), sealed, [payload, submitted])
        self.assertNotIn("refused", answer)
        broken = {**label(), "email": "a@example.com"}
        sealed, payload = self.rename()
        answer = self.bench.run(Entry(commits), sealed, [payload, broken])
        self.assertEqual(answer["refused"], [{"record": "carried/1", "code": "unknown_field",
                                              "pointer": "/email"}])


class Held(Base):
    def test_the_same_request_again_gets_the_original_answer_and_runs_nothing(self):
        sealed, payload = self.rename()
        entry = Entry(commits)
        first = self.bench.run(entry, sealed, [payload])
        again = self.bench.run(entry, sealed, [payload])
        self.assertEqual((again, entry.calls), (first, 1))
        self.assertEqual(first["result"]["outcome"]["stage"], "committed")

    def test_the_same_id_with_other_bytes_is_a_conflict_and_the_original_stays(self):
        sealed, payload = self.rename()
        first = self.bench.run(Entry(commits), sealed, [payload])
        other = label("Desktop")
        clash = {**sealed, "payload_digest": canonical.digest_of(other)}
        answer = self.bench.run(Entry(commits), clash, [other])
        outcome = answer["result"]["outcome"]
        self.assertEqual((outcome["stage"], outcome["material_gaps"]),
                         ("refused", [{"code": c03.REQUEST_ID_CONFLICT}]))
        self.assertEqual(answer["result"]["supported_recovery"], ["query_same_request"])
        self.assertEqual(answer["result"]["provider_effect"], "not_applicable")
        self.assertEqual(answer["result"]["request_digest"], canonical.digest_of(clash))
        self.assertEqual(self.query(sealed["request_id"])["returned"],
                         [first["result"], first["receipt"]])

    def test_a_pending_request_asked_again_runs_again_and_its_new_answer_is_held(self):
        before, _ = self.rename()
        self.bench.run(Entry(commits), before, [label()])
        sealed, payload = self.rename(label("Desktop"))
        waiting = Entry(lambda call: journal.answered(call, "in_review"))
        self.bench.run(waiting, sealed, [payload])
        entry = Entry(commits)
        second = self.bench.run(entry, sealed, [payload])
        third = self.bench.run(entry, sealed, [payload])
        self.assertEqual(second["result"]["outcome"]["stage"], "committed")
        self.assertEqual((third, entry.calls, self.held_count()), (second, 1, 2))
        self.assertEqual(self.query(sealed["request_id"])["returned"][0], second["result"])
        # it keeps its place among the requests the journal holds
        self.assertEqual(self.bench.store().read(
            "SELECT position FROM requests WHERE request_id = ?", (sealed["request_id"],)),
            [(2,)])

    def test_an_unknown_request_asked_again_under_its_own_id_is_settled_by_its_owner(self):
        sealed, payload = self.rename()
        self.bench.run(Entry(lambda call: journal.answered(call, "unknown")), sealed, [payload])
        entry = Entry(commits)
        self.assertEqual(self.bench.run(entry, sealed, [payload])["result"]["outcome"]["stage"],
                         "committed")
        self.assertEqual(entry.calls, 1)

    def test_a_settled_refusal_is_not_run_again(self):
        sealed, payload = self.rename()
        refusing = Entry(lambda call: journal.answered(call, "refused", gaps=[
            {"code": c03.STALE_BASE}]))
        first = self.bench.run(refusing, sealed, [payload])
        self.assertEqual(self.bench.run(refusing, sealed, [payload]), first)
        self.assertEqual(refusing.calls, 1)


class Addressed(Base):
    def test_a_query_returns_the_original_result_and_its_receipt(self):
        sealed, payload = self.rename()
        first = self.bench.run(Entry(commits), sealed, [payload])
        answer = self.query(sealed["request_id"])
        self.assertEqual(answer["returned"], [first["result"], first["receipt"]])
        self.assertEqual(answer["result"]["outputs"],
                         [{"kind": "operation_result",
                           "digest": canonical.digest_of(first["result"])},
                          {"kind": "operation_receipt",
                           "digest": canonical.digest_of(first["receipt"])}])
        self.assertEqual(answer["result"]["outcome"]["stage"], "previewed")

    def test_a_query_for_an_id_never_received_names_only_the_id(self):
        asked = bench.ident("req")
        self.assertEqual(self.query(asked)["returned"],
                         [{"kind": "request_not_held", "schema": 1, "request_id": asked}])

    def test_a_cancel_of_an_answered_request_is_too_late(self):
        sealed, payload = self.rename()
        self.bench.run(Entry(commits), sealed, [payload])
        asked = {"kind": "operation_query", "schema": 1, "request_id": sealed["request_id"]}
        cancel = bench.request(self.person, "operation.cancel", sealed["request_id"], asked)
        answer = self.bench.run(None, cancel, [asked])
        self.assertEqual(answer["result"]["outcome"],
                         {"stage": "refused", "material_gaps": [{"code": c03.CANCEL_TOO_LATE}]})
        self.assertEqual(answer["result"]["provider_effect"], "not_applicable")

    def test_a_cancel_of_a_request_not_held_is_not_served(self):
        asked = {"kind": "operation_query", "schema": 1, "request_id": bench.ident("req")}
        cancel = bench.request(self.person, "operation.cancel", asked["request_id"], asked)
        with self.assertRaises(journal.JournalError):
            self.bench.run(None, cancel, [asked])


class Ruled(Base):
    def test_a_payload_the_operation_does_not_take_is_refused(self):
        entry = Entry(commits)
        asked = {"kind": "operation_query", "schema": 1, "request_id": bench.ident("req")}
        named_elsewhere = self.rename()[0] | {"payload_digest": canonical.digest_of(label("X"))}
        for sealed, carried in (
                (self.rename()[0] | {"payload_digest": canonical.digest_of(asked)}, [asked]),
                ({k: v for k, v in self.rename()[0].items() if k != "payload_digest"}, []),
                (named_elsewhere, [label()])):
            answer = self.bench.run(entry, sealed, carried)
            self.assertEqual(answer["result"]["outcome"]["material_gaps"],
                             [{"code": c03.PAYLOAD_NOT_TAKEN, "pointer": "/payload_digest"}])
        read = bench.request(self.person, "access.profile.read", self.person.profile, label())
        answer = self.bench.run(entry, read, [label()])
        self.assertEqual(answer["result"]["outcome"]["material_gaps"][0]["code"],
                         c03.PAYLOAD_NOT_TAKEN)
        self.assertEqual(entry.calls, 0)

    def test_a_request_stating_another_effect_class_is_refused(self):
        sealed, payload = self.rename(effect_class="pure_preview")
        answer = self.bench.run(Entry(commits), sealed, [payload])
        self.assertEqual(answer["result"]["outcome"]["material_gaps"],
                         [{"code": c03.EFFECT_CLASS_MISMATCH}])

    def test_the_same_operation_under_a_new_id_while_one_is_unknown_is_refused(self):
        sealed, payload = self.rename()
        unknown = Entry(lambda call: journal.answered(
            call, "unknown", recovery=["query_same_request"], provider_effect="unknown"))
        self.bench.run(unknown, sealed, [payload])
        again = {**sealed, "request_id": bench.ident("req")}
        answer = self.bench.run(unknown, again, [payload])
        self.assertEqual(answer["result"]["outcome"]["material_gaps"],
                         [{"code": c03.RESUBMITTED_WHILE_UNKNOWN, "pointer": "/request_id"}])
        self.assertEqual((answer["result"]["provider_effect"], unknown.calls), ("none", 1))
        other = label("Desktop")
        elsewhere = {**sealed, "request_id": bench.ident("req"),
                     "payload_digest": canonical.digest_of(other)}
        self.assertEqual(self.bench.run(unknown, elsewhere, [other])["result"]["outcome"]
                         ["stage"], "unknown")

    def test_a_preview_repeating_an_unknown_one_is_not_a_resubmission(self):
        read = bench.request(self.person, "access.profile.read", self.person.profile)
        unknown = Entry(lambda call: journal.answered(call, "unknown"))
        self.bench.run(unknown, read)
        again = {**read, "request_id": bench.ident("req")}
        self.assertEqual(self.bench.run(unknown, again)["result"]["outcome"]["stage"], "unknown")
        self.assertEqual(unknown.calls, 2)


class Committing(Base):
    def test_the_answer_committed_is_handed_to_the_point_after_the_commit(self):
        sealed, payload = self.rename()
        call = self.bench.call(sealed, [payload], arm=journal.COMMITTED)
        with self.assertRaises(Killed) as died:
            journal.layer_journal(call, Entry(commits))
        self.assertEqual(call.points, [storage.IN_TXN, journal.COMMITTED])
        bench.restart(self.bench.state)
        self.assertEqual(self.query(sealed["request_id"])["returned"],
                         [died.exception.answer["result"], died.exception.answer["receipt"]])
        entry = Entry(commits)
        self.assertEqual(self.bench.run(entry, sealed, [payload]), died.exception.answer)
        self.assertEqual(entry.calls, 0)

    def test_a_process_killed_before_the_commit_holds_nothing_and_runs_again(self):
        sealed, payload = self.rename()
        with self.assertRaises(Killed):
            self.bench.run(Entry(commits), sealed, [payload], arm=storage.IN_TXN)
        bench.restart(self.bench.state)
        self.assertEqual(self.held_count(), 0)
        entry = Entry(commits)
        self.assertEqual(self.bench.run(entry, sealed, [payload])["result"]["outcome"]["stage"],
                         "committed")
        self.assertEqual(entry.calls, 1)

    def test_a_refusal_from_what_it_wraps_writes_nothing_not_even_first_use(self):
        sealed, payload = self.rename()
        triples = {"refused": [{"record": "carried/0", "code": "value_not_allowed",
                                "pointer": "/display_name"}]}
        self.assertEqual(self.bench.run(Entry(lambda call: triples), sealed, [payload]),
                         triples)
        store = self.bench.store()
        self.assertEqual(store.read("SELECT COUNT(*) FROM profiles")[0][0], 0)
        self.assertEqual(self.held_count(), 0)

    def test_receipts_count_per_owner_and_move_the_target_head(self):
        sealed, payload = self.rename()
        first = self.bench.run(Entry(commits), sealed, [payload])
        second_sealed, second_payload = self.rename(label("Desktop"))
        second = self.bench.run(Entry(commits), second_sealed, [second_payload])
        someone = Person()
        theirs = bench.request(someone, RENAME, someone.profile, label())
        third = self.bench.run(Entry(commits), theirs, [label()])
        self.assertEqual([first["receipt"]["sequence"], second["receipt"]["sequence"],
                          third["receipt"]["sequence"]], [1, 2, 1])
        self.assertNotEqual(first["receipt"]["head_digest"], second["receipt"]["head_digest"])
        head = self.bench.store().read("SELECT head_digest FROM heads WHERE resource_id = ?",
                                       (self.person.profile,))[0][0]
        self.assertEqual(head, second["receipt"]["head_digest"])
        self.assertEqual(first["result"]["outcome"]["receipt_digest"],
                         canonical.digest_of(first["receipt"]))

    def test_an_answer_naming_another_request_is_a_defect(self):
        sealed, payload = self.rename()

        def wrong(call):
            answer = commits(call)
            answer["result"]["request_id"] = bench.ident("req")
            return answer
        with self.assertRaises(journal.JournalError):
            self.bench.run(Entry(wrong), sealed, [payload])
        self.assertEqual(self.held_count(), 0)

    def test_a_given_answer_is_held_and_its_records_placed(self):
        sealed, payload = self.rename()
        stated = commits(self.bench.call(sealed, [payload]))

        def given(call):
            storage.place_given(call)
            return call.given
        answer = self.bench.run(given, sealed, [payload], given=stated)
        self.assertEqual(answer, stated)
        self.assertEqual(self.query(sealed["request_id"])["returned"],
                         [stated["result"], stated["receipt"]])
        self.assertEqual(self.bench.store().get(canonical.digest_of(payload)), payload)


if __name__ == "__main__":
    unittest.main()
