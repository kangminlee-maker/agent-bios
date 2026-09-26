"""The local profile and principal bindings, through the journal as the runtime runs them."""
from __future__ import annotations

import unittest

import bench
from bench import Bench, Person

from workenv import access, identity
from workenv.contracts import b01, c01, c03, canonical

READ, RENAME = "access.profile.read", "access.profile.rename"
ADD, REVOKE = "identity.binding.add", "identity.binding.revoke"
INSTANT = "2026-09-26T09:00:00Z"


def label(name: str) -> dict:
    return {"kind": "profile_label", "schema": 1, "display_name": name}


class Profile(unittest.TestCase):
    def setUp(self):
        self.bench, self.person = Bench(), Person()

    def tearDown(self):
        self.bench.close()

    def read(self, now=None) -> dict:
        return self.bench.run(access.access_profile_read,
                              bench.request(self.person, READ, self.person.profile), now=now)

    def test_first_use_writes_the_profile_and_an_active_state_at_generation_one(self):
        answer = self.read(now=INSTANT)
        self.assertEqual(answer["returned"], [
            {"kind": "local_profile", "schema": 1, "profile_id": self.person.profile,
             "principal_id": self.person.principal, "created_at": INSTANT},
            {"kind": "access_state", "schema": 1, "profile_id": self.person.profile,
             "state": {"is": "active", "because": "first_use"}, "access_generation": 1,
             "changed_at": INSTANT}])
        self.assertEqual((answer["result"]["outcome"]["stage"], answer["receipt"]),
                         ("previewed", None))

    def test_the_profile_is_written_by_the_first_request_whatever_it_is(self):
        key = self.bench.keys.make()
        payload = bench.binding(self.person.principal, key)
        self.bench.run(identity.identity_binding_add,
                       bench.request(self.person, ADD, self.person.principal, payload),
                       [payload], now=INSTANT)
        later = self.read(now="2026-09-26T10:00:00Z")
        self.assertEqual(later["returned"][0]["created_at"], INSTANT)

    def test_a_rename_changes_the_label_and_nothing_that_names_the_profile(self):
        before = self.read(now=INSTANT)["returned"][0]
        for name in ("Laptop", "Work laptop"):
            renamed = self.bench.run(access.access_profile_rename,
                                     bench.request(self.person, RENAME, self.person.profile,
                                                   label(name)), [label(name)])
            self.assertEqual(renamed["returned"], [{**before, "display_name": name}])
            self.assertEqual(renamed["result"]["outcome"]["stage"], "committed")
        self.assertEqual(self.read()["returned"][0], {**before, "display_name": "Work laptop"})

    def test_another_profile_than_the_actors_own_is_refused(self):
        other = Person()
        self.read()
        for operation, payload in ((READ, None), (RENAME, label("Theirs"))):
            answer = self.bench.run(
                access.access_profile_rename if payload else access.access_profile_read,
                bench.request(self.person, operation, other.profile, payload),
                [payload] if payload else [])
            self.assertEqual(answer["result"]["outcome"]["material_gaps"],
                             [{"code": c03.REQUEST_MISMATCH, "pointer": "/target/resource_id"}])
        self.assertEqual(self.bench.store().read("SELECT COUNT(*) FROM profiles")[0][0], 1)


class Bindings(unittest.TestCase):
    def setUp(self):
        self.bench, self.person = Bench(), Person()
        self.first_key = self.bench.keys.make()

    def tearDown(self):
        self.bench.close()

    def add(self, person, payload, proofs=(), **options) -> dict:
        sealed = bench.request(person, ADD, payload["principal_id"], payload, proofs)
        return self.bench.run(identity.identity_binding_add, sealed, [payload, *proofs],
                              **options)

    def first(self) -> dict:
        payload = bench.binding(self.person.principal, self.first_key)
        answer = self.add(self.person, payload, now=INSTANT)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed")
        return answer["returned"][0]

    def stage(self, answer) -> tuple:
        outcome = answer["result"]["outcome"]
        return outcome["stage"], outcome["material_gaps"]

    def test_the_first_binding_is_stored_as_submitted_with_what_the_runtime_owns(self):
        payload = bench.binding(self.person.principal, self.first_key)
        answer = self.add(self.person, payload, now=INSTANT)
        (stored,) = answer["returned"]
        self.assertEqual({k: v for k, v in stored.items() if k not in ("binding_id",
                                                                       "created_at")}, payload)
        self.assertRegex(stored["binding_id"], r"^bnd_[0-9a-f]{32}$")
        self.assertEqual(stored["created_at"], INSTANT)
        self.assertEqual(answer["result"]["outputs"],
                         [{"kind": "principal_binding", "digest": canonical.digest_of(stored)}])

    def test_a_key_bound_to_another_principal_is_a_conflict_and_stays_theirs(self):
        self.first()
        other = Person()
        answer = self.add(other, bench.binding(other.principal, self.first_key))
        self.assertEqual(self.stage(answer), ("conflict", [{"code": c01.BINDING_CONFLICT}]))
        self.assertEqual(answer["returned"], [])
        owners = self.bench.store().read("SELECT DISTINCT principal_id FROM bindings")
        self.assertEqual(owners, [(self.person.principal,)])

    def test_a_second_key_without_proof_is_unverified_and_nothing_is_bound(self):
        self.first()
        answer = self.add(self.person, bench.binding(self.person.principal,
                                                     self.bench.keys.make(), "enrollment"))
        self.assertEqual(self.stage(answer), ("refused", [{"code": c01.BINDING_UNVERIFIED}]))
        self.assertEqual(len(identity.bindings_of(self.bench.store(), self.person.principal)), 1)

    def test_a_second_key_signed_by_the_first_is_bound_to_the_same_principal(self):
        held = self.first()
        second = bench.binding(self.person.principal, self.bench.keys.make(), "enrollment")
        proof = self.bench.keys.envelope(self.first_key, held["binding_id"], second)
        answer = self.add(self.person, second, [proof])
        self.assertEqual(self.stage(answer), ("committed", []))
        self.assertEqual(answer["returned"][0]["principal_id"], self.person.principal)

    def test_a_proof_that_does_not_verify_under_the_named_binding_proves_nothing(self):
        held = self.first()
        second_key = self.bench.keys.make()
        second = bench.binding(self.person.principal, second_key, "enrollment")
        for proof in (
                # signed by the key it asks to bind, not by the principal's binding
                self.bench.keys.envelope(second_key, held["binding_id"], second),
                # over other bytes than the binding it names
                self.bench.keys.envelope(self.first_key, held["binding_id"], second,
                                         data=b"other bytes"),
                # in another record kind's namespace
                self.bench.keys.envelope(self.first_key, held["binding_id"], second,
                                         namespace="agent-bios/source_manifest"),
                # naming a binding that is not the principal's
                self.bench.keys.envelope(self.first_key, bench.ident("bnd"), second)):
            answer = self.add(self.person, second, [proof])
            self.assertEqual(self.stage(answer), ("refused", [{"code": c01.BINDING_UNVERIFIED}]))

    def test_a_proof_the_request_does_not_name_proves_nothing(self):
        held = self.first()
        second = bench.binding(self.person.principal, self.bench.keys.make(), "enrollment")
        proof = self.bench.keys.envelope(self.first_key, held["binding_id"], second)
        sealed = bench.request(self.person, ADD, self.person.principal, second)
        answer = self.bench.run(identity.identity_binding_add, sealed, [second, proof])
        self.assertEqual(self.stage(answer), ("refused", [{"code": c01.BINDING_UNVERIFIED}]))

    def test_the_same_key_for_the_same_principal_is_the_earlier_binding(self):
        payload = bench.binding(self.person.principal, self.first_key)
        first = self.add(self.person, payload)
        again = self.add(self.person, payload)
        self.assertEqual(again["returned"], first["returned"])
        self.assertEqual(again["receipt"], first["receipt"])
        self.assertEqual(again["result"]["outcome"]["receipt_digest"],
                         first["result"]["outcome"]["receipt_digest"])
        self.assertEqual(self.bench.store().read("SELECT COUNT(*) FROM receipts")[0][0], 1)

    def test_a_revoked_binding_proves_nothing_and_its_stored_results_stay(self):
        held = self.first()
        second_key = self.bench.keys.make()
        second = bench.binding(self.person.principal, second_key, "enrollment")
        bound = self.add(self.person, second,
                         [self.bench.keys.envelope(self.first_key, held["binding_id"], second)])
        revoke = bench.request(self.person, REVOKE, held["binding_id"])
        answer = self.bench.run(identity.identity_binding_revoke, revoke)
        self.assertEqual(self.stage(answer), ("committed", []))
        third = bench.binding(self.person.principal, self.bench.keys.make(), "enrollment")
        refused = self.add(self.person, third,
                           [self.bench.keys.envelope(self.first_key, held["binding_id"], third)])
        self.assertEqual(self.stage(refused), ("refused", [{"code": c01.BINDING_UNVERIFIED}]))
        signed = self.add(self.person, third, [self.bench.keys.envelope(
            second_key, bound["returned"][0]["binding_id"], third)])
        self.assertEqual(self.stage(signed), ("committed", []))

    def test_only_the_actors_own_binding_that_stands_can_be_revoked(self):
        held = self.first()
        other = Person()
        for person, target in ((other, held["binding_id"]), (self.person, bench.ident("bnd"))):
            answer = self.bench.run(identity.identity_binding_revoke,
                                    bench.request(person, REVOKE, target))
            self.assertEqual(self.stage(answer), ("refused", [
                {"code": c01.REF_UNAVAILABLE, "pointer": "/target/resource_id"}]))
        self.assertEqual(len(identity.bindings_of(self.bench.store(), self.person.principal)), 1)
        revoke = bench.request(self.person, REVOKE, held["binding_id"])
        self.assertEqual(self.stage(self.bench.run(identity.identity_binding_revoke, revoke)),
                         ("committed", []))
        again = bench.request(self.person, REVOKE, held["binding_id"])
        self.assertEqual(self.stage(self.bench.run(identity.identity_binding_revoke, again))[1],
                         [{"code": c01.REF_UNAVAILABLE, "pointer": "/target/resource_id"}])

    def test_a_principal_whose_every_binding_is_revoked_takes_no_key_without_proof(self):
        held = self.first()
        self.bench.run(identity.identity_binding_revoke,
                       bench.request(self.person, REVOKE, held["binding_id"]))
        new = bench.binding(self.person.principal, self.bench.keys.make(), "enrollment")
        for proofs in ((), (self.bench.keys.envelope(self.first_key, held["binding_id"], new),)):
            answer = self.add(self.person, new, proofs)
            self.assertEqual(self.stage(answer), ("refused", [{"code": c01.BINDING_UNVERIFIED}]))

    def test_a_proof_by_another_principals_binding_proves_nothing(self):
        held = self.first()
        other = Person()
        other_key = self.bench.keys.make()
        theirs = self.add(other, bench.binding(other.principal, other_key))["returned"][0]
        second = bench.binding(self.person.principal, self.bench.keys.make(), "enrollment")
        proof = self.bench.keys.envelope(other_key, theirs["binding_id"], second)
        answer = self.add(self.person, second, [proof])
        self.assertEqual(self.stage(answer), ("refused", [{"code": c01.BINDING_UNVERIFIED}]))
        self.assertEqual(len(identity.bindings_of(self.bench.store(), self.person.principal)), 1)
        self.assertTrue(held)

    def test_a_binding_for_another_principal_than_the_target_is_refused(self):
        other = Person()
        payload = bench.binding(other.principal, self.first_key)
        sealed = bench.request(self.person, ADD, self.person.principal, payload)
        answer = self.bench.run(identity.identity_binding_add, sealed, [payload])
        self.assertEqual(self.stage(answer)[1][0]["code"], c03.REQUEST_MISMATCH)


class Signatures(unittest.TestCase):
    def setUp(self):
        self.bench, self.person = Bench(), Person()

    def tearDown(self):
        self.bench.close()

    def test_verify_names_the_b01_code(self):
        key = self.bench.keys.make()
        payload = bench.binding(self.person.principal, key)
        held = self.bench.run(identity.identity_binding_add,
                              bench.request(self.person, ADD, self.person.principal, payload),
                              [payload])["returned"][0]
        record = label("signed")
        store = self.bench.store()
        good = self.bench.keys.envelope(key, held["binding_id"], record)
        self.assertIsNone(identity.verify(store, good, canonical.encode(record)))
        self.assertEqual(identity.verify(store, good, canonical.encode(label("altered"))),
                         b01.SIGNATURE_INVALID)
        stranger = {**good, "signer_binding_id": bench.ident("bnd")}
        self.assertEqual(identity.verify(store, stranger, canonical.encode(record)),
                         b01.SIGNER_NOT_PERMITTED)


if __name__ == "__main__":
    unittest.main()
