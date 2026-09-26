"""Sources: homes, revisions, reading back, and the person's checkout, through the journal."""
from __future__ import annotations

import contextlib
import hashlib
import os
import pathlib
import subprocess
import unittest
from unittest import mock

import bench
from bench import Bench, Killed, Person

from workenv import identity, journal, sources, storage
from workenv.contracts import b01, c01, c03, canonical

REGISTER, COMMIT, RESOLVE = "source.home.register", "source.revision.commit", "reference.resolve"
ADMIT = "source.revision.admit"
BIND, OBSERVE = "repository.bind", "source.observe"
INSTANT = "2026-09-26T09:00:00Z"
ORIGIN = "git@github.com:example/work.git"
CONCEPTS, RATES = b"# Concepts\n\nA rate applies per period.\n", b"period,rate\n2026,0.1\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def home(person: Person, source_id: str, **changes) -> dict:
    value = {"kind": "source_home", "schema": 1, "source_id": source_id, "role": "knowledge",
             "scope": person.scope, "acceptance_authority": person.scope, "format_version": 1,
             "home": {"mode": "managed", "markdown_view": {"view": "none"}},
             "applicability": {"states": "unstated"}, "disclosure": "private",
             "retention": {"keep": "until_withdrawn"}, "publication_evidence_digests": []}
    value.update(changes)
    return value


def manifest(source_id: str, members: dict[str, bytes]) -> dict:
    return {"kind": "source_manifest", "schema": 1, "source_id": source_id, "format_version": 1,
            "members": [{"path": path, "digest": sha(data), "size": len(data)}
                        for path, data in members.items()]}


def gaps(answer: dict) -> list[dict]:
    return answer["result"]["outcome"]["material_gaps"]


class Checkout:
    """A git checkout of the test's own, made with no git variable of the caller's."""

    def __init__(self, directory: pathlib.Path, name: str = "work"):
        self.path = (directory / name).resolve()
        self.path.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("GIT_")}
        self.env.update(HOME=str(directory), GIT_CONFIG_NOSYSTEM="1",
                        GIT_AUTHOR_NAME="test", GIT_AUTHOR_EMAIL="test@localhost",
                        GIT_COMMITTER_NAME="test", GIT_COMMITTER_EMAIL="test@localhost")
        self.git("init", "-q", "-b", "main")

    def git(self, *arguments: str) -> str:
        return subprocess.run(["git", "-c", "commit.gpgsign=false", "-c",
                               "core.hooksPath=/dev/null", *arguments], cwd=self.path,
                              env=self.env, check=True, capture_output=True,
                              text=True).stdout.strip()

    def write(self, path: str, data: bytes) -> None:
        target = self.path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "state")


class Base(unittest.TestCase):
    def setUp(self):
        self.bench, self.person = Bench(), Person()
        self.scratch = pathlib.Path(self.bench.scratch.name)
        self.source = bench.ident("src")
        self.repository = bench.ident("rep")

    def tearDown(self):
        self.bench.close()

    def run_with(self, entry, sealed: dict, carried=(), members=None, **options) -> dict:
        call = self.bench.call(sealed, carried, **options)
        call.members = dict(members or {})
        return journal.layer_journal(call, entry)

    def register(self, payload: dict, base: dict | None = None, **options) -> dict:
        target = {"resource_id": payload["source_id"], "base": base or {"expects": "absent"}}
        return self.run_with(sources.source_home_register,
                             bench.request(self.person, REGISTER, target, payload), [payload],
                             now=INSTANT, **options)

    def commit(self, payload: dict, head: str, proofs=(), members=None, **options) -> dict:
        target = {"resource_id": payload["source_id"],
                  "base": {"expects": "head", "head_digest": head}}
        return self.run_with(sources.source_revision_commit,
                             bench.request(self.person, COMMIT, target, payload, proofs=proofs),
                             [payload, *proofs], members=members, now=INSTANT, **options)

    def resolve(self, ref: dict, head: str) -> dict:
        target = {"resource_id": ref["source_id"],
                  "base": {"expects": "head", "head_digest": head}}
        return self.run_with(sources.reference_resolve,
                             bench.request(self.person, RESOLVE, target, ref), [ref])

    def registered(self, **changes) -> tuple[dict, str]:
        """A managed source registered here: its stored home and the head it made."""
        answer = self.register(home(self.person, self.source, **changes))
        return answer["returned"][0], answer["receipt"]["head_digest"]

    def committed(self, members: dict[str, bytes], head: str) -> tuple[dict, str]:
        answer = self.commit(manifest(self.source, members), head,
                             members={sha(data): data for data in members.values()})
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        return answer["returned"][0], answer["receipt"]["head_digest"]

    def signed(self, signer: Person, record: dict, namespace: str = "agent-bios/source_manifest",
               data: bytes | None = None) -> dict:
        """An envelope over the record by the signer's key, bound here on first use."""
        signers = self.__dict__.setdefault("signers", {})
        if signer.principal not in signers:
            key = self.bench.keys.make()
            payload = bench.binding(signer.principal, key)
            added = self.run_with(identity.identity_binding_add,
                                  bench.request(signer, "identity.binding.add", signer.principal,
                                                payload), [payload])
            signers[signer.principal] = key, added["returned"][0]["binding_id"]
        key, binding_id = signers[signer.principal]
        return self.bench.keys.envelope(key, binding_id, record, namespace, data)

    def count(self, table: str) -> int:
        return self.bench.store().read(f"SELECT COUNT(*) FROM {table}")[0][0]

    def bundles(self) -> list[str]:
        objects = self.bench.state / storage.OBJECTS
        return sorted(path.name for path in objects.iterdir()
                      if path.name != storage.STAGING) if objects.is_dir() else []

    # The checkout.

    def selection(self, checkout: Checkout, *roots: tuple[str, str]) -> dict:
        return {"kind": "source_selection", "schema": 1, "roots": [
            {"need": need, "place": {"from": "working_tree", "repository_id": self.repository,
                                     "checkout": str(checkout.path), "path": path}}
            for path, need in roots]}

    def observe(self, selection: dict) -> dict:
        return self.run_with(sources.source_observe,
                             bench.request(self.person, OBSERVE, self.repository, selection),
                             [selection], now=INSTANT)

    def bind(self, checkout: Checkout, repository: str | None = None) -> dict:
        payload = {"kind": "repository_binding", "schema": 1,
                   "repository_id": repository or self.repository, "relation": {"how": "clone"}}
        with contextlib.chdir(checkout.path):
            return self.run_with(sources.repository_bind,
                                 bench.request(self.person, BIND, self.repository, payload),
                                 [payload], now=INSTANT)


class Homes(Base):
    def test_the_first_registration_creates_the_source_and_its_head_is_the_home_stored(self):
        submitted = home(self.person, self.source)
        answer = self.register(submitted)
        self.assertEqual(answer["returned"], [{**submitted, "registered_at": INSTANT}])
        self.assertEqual(answer["receipt"]["head_digest"],
                         canonical.digest_of(answer["returned"][0]))
        self.assertEqual(self.count("sources"), 1)

    def test_registering_again_changes_its_conditions_and_moves_the_head(self):
        _, head = self.registered()
        _, revision = self.committed({"concepts.md": CONCEPTS}, head)
        changed = home(self.person, self.source, disclosure="team",
                       home={"mode": "managed",
                             "markdown_view": {"view": "derived", "path": "views/notes.md"}})
        answer = self.register(changed, {"expects": "head", "head_digest": revision})
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        self.assertNotEqual(answer["receipt"]["head_digest"], revision)
        held = sources.homes.source_of(self.bench.store(), self.source)
        self.assertEqual((held["home"]["disclosure"], held["revision_digest"]),
                         ("team", canonical.digest_of(
                             self.bench.store().get(held["revision_digest"]))))

    def test_a_registration_changing_where_or_by_whom_the_source_is_owned_is_a_second_home(self):
        _, head = self.registered()
        other = Person()
        for changes in ({"acceptance_authority": other.scope},
                        {"scope": other.scope},
                        {"role": "memory"},
                        {"home": {"mode": "repository_authored", "repository_id": self.repository,
                                  "document_root": "docs",
                                  "binding_evidence_digest": sha(b"binding")}}):
            answer = self.register(home(self.person, self.source, **changes),
                                   {"expects": "head", "head_digest": head})
            self.assertEqual(gaps(answer), [{"code": c01.SOURCE_HOME_CONFLICT}], changes)
        self.assertEqual(journal.head_of(self.bench.store(), self.source), head)

    def test_another_package_in_the_same_mode_is_a_second_home(self):
        published = {"mode": "package_published", "package_id": bench.ident("pkg"),
                     "publisher_evidence_digest": sha(b"publisher"), "license_conditions": "MIT"}
        _, head = self.registered(home=published)
        other = self.register(home(self.person, self.source,
                                   home={**published, "package_id": bench.ident("pkg")}),
                              {"expects": "head", "head_digest": head})
        self.assertEqual(gaps(other), [{"code": c01.SOURCE_HOME_CONFLICT}])
        same = self.register(home(self.person, self.source,
                                  home={**published, "license_conditions": "CC-BY-4.0"}),
                             {"expects": "head", "head_digest": head})
        self.assertEqual(same["result"]["outcome"]["stage"], "committed", gaps(same))

    def test_a_first_registration_of_a_source_held_here_is_a_second_home(self):
        self.registered()
        answer = self.register(home(self.person, self.source, disclosure="team"))
        self.assertEqual(gaps(answer), [{"code": c01.SOURCE_HOME_CONFLICT}])

    def test_a_registration_on_a_head_the_source_is_not_at_is_stale(self):
        self.registered()
        answer = self.register(home(self.person, self.source, disclosure="team"),
                               {"expects": "head", "head_digest": sha(b"another head")})
        self.assertEqual((answer["result"]["outcome"]["stage"], gaps(answer)),
                         ("stale", [{"code": c03.STALE_BASE}]))

    def test_a_home_for_another_source_than_the_target_is_a_mismatch(self):
        submitted = home(self.person, self.source)
        target = {"resource_id": bench.ident("src"), "base": {"expects": "absent"}}
        answer = self.run_with(sources.source_home_register,
                               bench.request(self.person, REGISTER, target, submitted),
                               [submitted])
        self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH,
                                         "pointer": "/target/resource_id"}])
        self.assertEqual(self.count("sources"), 0)

    def test_a_repository_authored_home_rests_on_the_binding_held_for_its_repository(self):
        checkout = Checkout(self.scratch)
        checkout.commit()

        def authored(evidence: str) -> dict:
            where = {"layer": "repository", "repository_id": self.repository}
            return home(self.person, self.source, scope=where, acceptance_authority=where,
                        home={"mode": "repository_authored", "repository_id": self.repository,
                              "document_root": "docs", "binding_evidence_digest": evidence})
        unbound = self.register(authored(sha(b"a binding nobody holds")))
        self.assertEqual(gaps(unbound), [{"code": c01.BINDING_UNVERIFIED}])
        binding = self.bind(checkout)["returned"][0]
        other = self.register(authored(sha(b"another binding")))
        self.assertEqual(gaps(other), [{"code": c01.BINDING_UNVERIFIED}])
        held = self.register(authored(canonical.digest_of(binding)))
        self.assertEqual(held["result"]["outcome"]["stage"], "committed", gaps(held))
        checkout.write("docs/new.md", b"new\n")
        rebound = self.bind(checkout)["returned"][0]
        self.assertEqual(rebound, binding)   # nothing observed, so the same binding again
        checkout.commit()
        moved = self.bind(checkout)["returned"][0]
        again = self.register(authored(canonical.digest_of(moved)),
                              {"expects": "head", "head_digest": held["receipt"]["head_digest"]})
        self.assertEqual(again["result"]["outcome"]["stage"], "committed", gaps(again))


class Revisions(Base):
    def test_a_revision_is_stored_with_its_production_time_and_becomes_the_head(self):
        _, head = self.registered()
        submitted = manifest(self.source, {"concepts.md": CONCEPTS, "tables/rates.csv": RATES})
        answer = self.commit(submitted, head,
                             members={sha(CONCEPTS): CONCEPTS, sha(RATES): RATES})
        stored = {**submitted, "produced_at": INSTANT}
        digest = canonical.digest_of(stored)
        self.assertEqual((answer["returned"], answer["receipt"]["head_digest"]),
                         ([stored], digest))
        bundle = storage.bundle(self.bench.state, digest)
        self.assertEqual((bundle / storage.MANIFEST).read_bytes(), canonical.encode(stored))
        self.assertEqual((bundle / storage.MEMBERS / "tables/rates.csv").read_bytes(), RATES)
        self.assertEqual(sources.homes.source_of(self.bench.store(), self.source)
                         ["revision_digest"], digest)

    def test_a_member_whose_bytes_are_not_at_hand_is_stored_by_its_hash_alone(self):
        _, head = self.registered()
        answer = self.commit(manifest(self.source, {"concepts.md": CONCEPTS, "rates.csv": RATES}),
                             head, members={sha(CONCEPTS): CONCEPTS})
        bundle = storage.bundle(self.bench.state, answer["receipt"]["head_digest"])
        self.assertEqual(sorted(p.name for p in (bundle / storage.MEMBERS).iterdir()),
                         ["concepts.md"])

    def test_bytes_other_than_a_member_states_are_refused_at_it_and_nothing_is_published(self):
        _, head = self.registered()
        answer = self.commit(manifest(self.source, {"concepts.md": CONCEPTS, "rates.csv": RATES}),
                             head, members={sha(CONCEPTS): CONCEPTS, sha(RATES): RATES + b"x"})
        self.assertEqual(gaps(answer), [{"code": c03.OBJECT_DIGEST_MISMATCH,
                                         "pointer": "/members/1"}])
        self.assertEqual((self.count("revisions"), self.bundles()), (0, []))

    def test_a_source_this_installation_holds_no_home_for_is_unavailable(self):
        answer = self.commit(manifest(self.source, {"concepts.md": CONCEPTS}), sha(b"head"))
        self.assertEqual(gaps(answer), [{"code": c01.REF_UNAVAILABLE}])

    def test_a_manifest_of_another_source_than_the_target_is_a_mismatch(self):
        _, head = self.registered()
        submitted = manifest(bench.ident("src"), {"concepts.md": CONCEPTS})
        target = {"resource_id": self.source, "base": {"expects": "head", "head_digest": head}}
        answer = self.run_with(sources.source_revision_commit,
                               bench.request(self.person, COMMIT, target, submitted), [submitted])
        self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH,
                                         "pointer": "/target/resource_id"}])

    def test_a_revision_on_a_head_the_source_is_not_at_is_stale_and_publishes_nothing(self):
        self.registered()
        answer = self.commit(manifest(self.source, {"concepts.md": CONCEPTS}), sha(b"old head"),
                             members={sha(CONCEPTS): CONCEPTS})
        self.assertEqual((answer["result"]["outcome"]["stage"], answer["result"]
                          ["supported_recovery"]), ("stale", ["reseal_on_current_head"]))
        self.assertEqual(self.bundles(), [])

    def test_a_head_that_moves_after_the_bundle_is_published_is_stale_at_the_commit(self):
        _, head = self.registered()
        test = self

        class Racing:
            """The entry, with another commit landing between its bundle and its unit."""

            def __call__(self, call):
                return sources.source_revision_commit(call)

            def prepare(self, call):
                staged = sources.revisions.prepare(call)
                test.committed({"concepts.md": CONCEPTS}, head)
                return staged
        submitted = manifest(self.source, {"tables/rates.csv": RATES})
        target = {"resource_id": self.source, "base": {"expects": "head", "head_digest": head}}
        answer = self.run_with(Racing(), bench.request(self.person, COMMIT, target, submitted),
                               [submitted], members={sha(RATES): RATES}, now=INSTANT)
        self.assertEqual(answer["result"]["outcome"]["stage"], "stale")
        self.assertEqual(self.count("revisions"), 1)

    def test_a_package_published_source_takes_no_revision_here(self):
        _, head = self.registered(home={
            "mode": "package_published", "package_id": bench.ident("pkg"),
            "publisher_evidence_digest": sha(b"publisher"), "license_conditions": "CC-BY-4.0"})
        answer = self.commit(manifest(self.source, {"concepts.md": CONCEPTS}), head)
        self.assertEqual(gaps(answer), [{"code": c01.PUBLISHER_BYTES_MODIFIED}])

    def test_a_signature_by_the_actors_own_key_over_the_manifest_is_accepted(self):
        _, head = self.registered()
        submitted = manifest(self.source, {"concepts.md": CONCEPTS})
        answer = self.commit(submitted, head, proofs=[self.signed(self.person, submitted)])
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))

    def test_a_signature_that_is_not_over_these_bytes_by_the_actor_is_refused_at_it(self):
        _, head = self.registered()
        submitted = manifest(self.source, {"concepts.md": CONCEPTS})
        altered = manifest(self.source, {"concepts.md": CONCEPTS + b"!"})
        cases = [
            (self.signed(self.person, submitted, data=canonical.encode(altered)),
             b01.SIGNATURE_INVALID),
            ({**self.signed(self.person, submitted), "signed_digest": sha(b"other")},
             b01.SIGNATURE_INVALID),
            (self.signed(self.person, submitted, namespace="agent-bios/principal_binding"),
             b01.SIGNATURE_NAMESPACE_MISMATCH),
            (self.signed(Person(), submitted), b01.SIGNER_NOT_PERMITTED)]
        for envelope, code in cases:
            answer = self.commit(submitted, head, proofs=[envelope])
            self.assertEqual(gaps(answer), [{"code": code, "pointer": "/proof_digests/0"}])
        self.assertEqual(self.count("revisions"), 0)

    def test_a_process_killed_before_the_rename_leaves_no_revision_and_runs_again(self):
        _, head = self.registered()
        submitted = manifest(self.source, {"concepts.md": CONCEPTS})
        sealed = bench.request(self.person, COMMIT, {
            "resource_id": self.source, "base": {"expects": "head", "head_digest": head}},
            submitted)
        call = self.bench.call(sealed, [submitted], now=INSTANT,
                               arm="after_stage_before_rename")
        with self.assertRaises(Killed):
            journal.layer_journal(call, sources.source_revision_commit)
        bench.restart(self.bench.state)
        self.assertEqual((self.count("revisions"), self.bundles()), (0, []))
        again = journal.layer_journal(self.bench.call(sealed, [submitted], now=INSTANT),
                                      sources.source_revision_commit)
        self.assertEqual(again["result"]["outcome"]["stage"], "committed")

    def test_a_bundle_published_before_a_crash_is_found_by_its_name_when_run_again(self):
        _, head = self.registered()
        submitted = manifest(self.source, {"concepts.md": CONCEPTS})
        sealed = bench.request(self.person, COMMIT, {
            "resource_id": self.source, "base": {"expects": "head", "head_digest": head}},
            submitted)
        call = self.bench.call(sealed, [submitted], now=INSTANT,
                               arm="after_dirsync_before_begin")
        call.members = {sha(CONCEPTS): CONCEPTS}
        with self.assertRaises(Killed):
            journal.layer_journal(call, sources.source_revision_commit)
        bench.restart(self.bench.state)
        self.assertEqual((self.count("revisions"), len(self.bundles())), (0, 1))
        again = journal.layer_journal(self.bench.call(sealed, [submitted], now=INSTANT),
                                      sources.source_revision_commit)
        self.assertEqual(self.bundles(), [again["receipt"]["head_digest"]])
        self.assertEqual(list((self.bench.state / storage.OBJECTS / storage.STAGING).iterdir()),
                         [])

    def test_a_repository_authored_revision_reads_its_members_from_the_bound_checkout(self):
        checkout = Checkout(self.scratch)
        checkout.write("docs/rules.md", CONCEPTS)
        checkout.commit()
        binding = self.bind(checkout)["returned"][0]
        where = {"layer": "repository", "repository_id": self.repository}
        registered = self.register(home(
            self.person, self.source, scope=where, acceptance_authority=where,
            home={"mode": "repository_authored", "repository_id": self.repository,
                  "document_root": "docs",
                  "binding_evidence_digest": canonical.digest_of(binding)}))
        head = registered["receipt"]["head_digest"]
        answer = self.commit(manifest(self.source, {"docs/rules.md": CONCEPTS}), head)
        bundle = storage.bundle(self.bench.state, answer["receipt"]["head_digest"])
        self.assertEqual((bundle / storage.MEMBERS / "docs/rules.md").read_bytes(), CONCEPTS)
        checkout.write("docs/rules.md", CONCEPTS + b"edited\n")
        moved = self.commit(manifest(self.source, {"docs/rules.md": CONCEPTS}),
                            answer["receipt"]["head_digest"])
        self.assertEqual(gaps(moved), [{"code": c03.OBJECT_DIGEST_MISMATCH,
                                        "pointer": "/members/0"}])


class Admissions(Base):
    """A revision authored here, admitted with the manifest its route names."""

    def asked(self, manifest: dict | None, *, role: str = "instructions", scope: dict | None = None,
              mode: str = "managed", route: dict | None = None) -> dict:
        return {"kind": "source_request", "schema": 1, "role": role,
                "destination": {"scope": scope or self.person.scope, "home_mode": mode},
                "route": route or {"route": "author_here",
                                   "manifest_digest": canonical.digest_of(manifest)}}

    def admit(self, request: dict, manifest: dict | None, base: dict | None = None,
              members=None, proofs=()) -> dict:
        target = {"resource_id": self.source, "base": base or {"expects": "absent"}}
        carried = [request, *([manifest] if manifest else []), *proofs]
        return self.run_with(sources.source_revision_admit,
                             bench.request(self.person, ADMIT, target, request, proofs=proofs),
                             carried, members=members, now=INSTANT)

    def authored(self, members: dict[str, bytes], base: dict | None = None, **options) -> dict:
        submitted = manifest(self.source, members)
        return self.admit(self.asked(submitted, **options), submitted, base,
                          members={sha(data): data for data in members.values()})

    def test_an_authored_revision_creates_its_source_kept_as_its_destination_states(self):
        answer = self.authored({"rules/review.md": CONCEPTS})
        stored = {**manifest(self.source, {"rules/review.md": CONCEPTS}), "produced_at": INSTANT}
        self.assertEqual((answer["returned"], answer["receipt"]["head_digest"]),
                         ([stored], canonical.digest_of(stored)))
        held = sources.homes.source_of(self.bench.store(), self.source)
        self.assertEqual((held["scope"], held["role"], held["home"], held["home_mode"]),
                         (self.person.scope, "instructions", None, "managed"))
        bundle = storage.bundle(self.bench.state, canonical.digest_of(stored))
        self.assertEqual((bundle / storage.MEMBERS / "rules/review.md").read_bytes(), CONCEPTS)

    def test_a_later_admission_names_the_head_it_expects(self):
        head = self.authored({"rules/review.md": CONCEPTS})["receipt"]["head_digest"]
        second = self.authored({"rules/review.md": RATES}, {"expects": "head", "head_digest": head})
        self.assertEqual(second["result"]["outcome"]["stage"], "committed", gaps(second))
        stale = self.authored({"rules/review.md": CONCEPTS + RATES},
                              {"expects": "head", "head_digest": head})
        self.assertEqual(stale["result"]["outcome"]["stage"], "stale")
        again = self.authored({"rules/review.md": RATES})
        self.assertEqual(again["result"]["outcome"]["stage"], "stale")
        self.assertEqual((self.count("revisions"), len(self.bundles())), (2, 2))

    def test_a_route_naming_a_manifest_the_request_does_not_carry_is_unavailable(self):
        submitted = manifest(self.source, {"rules/review.md": CONCEPTS})
        answer = self.admit(self.asked(submitted), None)
        self.assertEqual(gaps(answer), [{"code": c01.REF_UNAVAILABLE,
                                         "pointer": "/route/manifest_digest"}])
        other = manifest(self.source, {"rules/review.md": RATES})
        carried = self.admit(self.asked(submitted), other)
        self.assertEqual(gaps(carried), [{"code": c01.REF_UNAVAILABLE,
                                          "pointer": "/route/manifest_digest"}])

    def test_a_manifest_of_another_source_than_the_target_is_a_mismatch(self):
        submitted = manifest(bench.ident("src"), {"rules/review.md": CONCEPTS})
        answer = self.admit(self.asked(submitted), submitted)
        self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH,
                                         "pointer": "/target/resource_id"}])
        self.assertEqual(self.count("sources"), 0)

    def test_an_admission_into_another_scope_role_or_way_of_keeping_is_a_second_home(self):
        head = self.authored({"rules/review.md": CONCEPTS})["receipt"]["head_digest"]
        base = {"expects": "head", "head_digest": head}
        repository = {"layer": "repository", "repository_id": self.repository}
        for options in ({"role": "knowledge"}, {"scope": Person().scope},
                        {"mode": "repository_authored"},
                        {"scope": repository, "mode": "repository_authored"}):
            answer = self.authored({"rules/review.md": RATES}, base, **options)
            self.assertEqual(gaps(answer), [{"code": c01.SOURCE_HOME_CONFLICT}], options)
        registered = self.register(home(self.person, self.source, role="instructions", home={
            "mode": "package_published", "package_id": bench.ident("pkg"),
            "publisher_evidence_digest": sha(b"publisher"), "license_conditions": "MIT"}), base)
        self.assertEqual(gaps(registered), [{"code": c01.SOURCE_HOME_CONFLICT}])
        same_way = self.register(home(self.person, self.source, role="instructions"), base)
        self.assertEqual(same_way["result"]["outcome"]["stage"], "committed", gaps(same_way))

    def test_a_source_held_before_its_way_of_keeping_was_is_read_from_its_home(self):
        _, head = self.registered(role="instructions")
        store = self.bench.store()
        with store.unit(self.bench.call(bench.request(self.person, "access.profile.read",
                                                      self.person.profile))):
            store.write("UPDATE sources SET home_mode = NULL")
        answer = self.authored({"rules/review.md": CONCEPTS},
                               {"expects": "head", "head_digest": head})
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))

    def test_a_destination_kept_by_a_package_is_the_publishers(self):
        answer = self.authored({"rules/review.md": CONCEPTS}, mode="package_published")
        self.assertEqual(gaps(answer), [{"code": c01.PUBLISHER_BYTES_MODIFIED}])

    def test_a_repository_destination_rests_on_its_binding_and_reads_its_checkout(self):
        checkout = Checkout(self.scratch)
        checkout.write("rules/review.md", CONCEPTS)
        checkout.commit()
        repository = {"layer": "repository", "repository_id": self.repository}
        submitted = manifest(self.source, {"rules/review.md": CONCEPTS})
        asked = self.asked(submitted, scope=repository, mode="repository_authored")
        self.assertEqual(gaps(self.admit(asked, submitted)), [{"code": c01.BINDING_UNVERIFIED}])
        self.bind(checkout)
        checkout.write("rules/review.md", RATES)
        moved = self.admit(asked, submitted)
        self.assertEqual(gaps(moved), [{"code": c03.OBJECT_DIGEST_MISMATCH,
                                        "pointer": "/members/0"}])
        checkout.write("rules/review.md", CONCEPTS)
        answer = self.admit(asked, submitted)
        bundle = storage.bundle(self.bench.state, answer["receipt"]["head_digest"])
        self.assertEqual((bundle / storage.MEMBERS / "rules/review.md").read_bytes(), CONCEPTS)

    def test_a_signature_among_its_proofs_is_held_to_what_a_commit_holds_it_to(self):
        submitted = manifest(self.source, {"rules/review.md": CONCEPTS})
        altered = manifest(self.source, {"rules/review.md": RATES})
        envelope = self.signed(self.person, submitted, data=canonical.encode(altered))
        answer = self.admit(self.asked(submitted), submitted, proofs=[envelope])
        self.assertEqual(gaps(answer), [{"code": b01.SIGNATURE_INVALID,
                                         "pointer": "/proof_digests/0"}])

    def test_adding_or_importing_a_package_is_not_served_yet(self):
        route = {"route": "import_external_package", "declared_origin": "a vendor",
                 "license_conditions": "MIT", "revision_digest": sha(b"revision")}
        with self.assertRaises(journal.JournalError):
            self.admit(self.asked(None, route=route), None)


class Reading(Base):
    def setUp(self):
        super().setUp()
        self.home, head = self.registered()
        self.revision, self.head = self.committed({"concepts.md": CONCEPTS,
                                                   "tables/rates.csv": RATES}, head)
        self.digest = canonical.digest_of(self.revision)

    def ref(self, **changes) -> dict:
        value = {"kind": "source_ref", "schema": 1, "source_id": self.source,
                 "role": "knowledge", "scope": self.person.scope,
                 "revision_digest": self.digest,
                 "member": {"path": "tables/rates.csv", "digest": sha(RATES), "size": len(RATES)}}
        value.update(changes)
        return value

    def test_an_exact_member_resolves_to_the_manifest_the_home_and_its_bytes(self):
        answer = self.resolve(self.ref(), self.head)
        self.assertEqual(answer["returned"], [self.revision, self.home, RATES])
        self.assertEqual([output["kind"] for output in answer["result"]["outputs"]],
                         ["source_manifest", "source_home", storage.MEMBER])
        self.assertEqual((answer["result"]["outcome"]["stage"],
                          answer["result"]["provider_effect"]), ("previewed", "not_applicable"))

    def test_a_reference_naming_no_member_resolves_to_the_manifest_and_the_home(self):
        ref = self.ref()
        del ref["member"]
        self.assertEqual(self.resolve(ref, self.head)["returned"], [self.revision, self.home])

    def test_what_this_installation_does_not_hold_as_referenced_is_unavailable(self):
        for ref in (self.ref(revision_digest=sha(b"no revision")),
                    self.ref(role="memory"),
                    self.ref(scope=Person().scope),
                    self.ref(member={"path": "unlisted.md", "digest": sha(b"x"), "size": 1})):
            answer = self.resolve(ref, self.head)
            self.assertEqual((gaps(answer), answer["result"]["supported_recovery"]),
                             ([{"code": c01.REF_UNAVAILABLE}], []), ref)

    def test_a_reference_to_another_source_than_the_target_is_a_mismatch(self):
        target = {"resource_id": bench.ident("src"),
                  "base": {"expects": "head", "head_digest": self.head}}
        ref = self.ref()
        answer = self.run_with(sources.reference_resolve,
                               bench.request(self.person, RESOLVE, target, ref), [ref])
        self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH,
                                         "pointer": "/target/resource_id"}])

    def test_bytes_the_bundle_holds_under_a_path_its_manifest_does_not_list_are_not_read(self):
        extra = b"slipped in\n"
        (storage.bundle(self.bench.state, self.digest) / storage.MEMBERS / "extra.md"
         ).write_bytes(extra)
        ref = self.ref(member={"path": "extra.md", "digest": sha(extra), "size": len(extra)})
        self.assertEqual(gaps(self.resolve(ref, self.head)), [{"code": c01.REF_UNAVAILABLE}])

    def test_member_bytes_changed_in_the_bundle_are_not_read_in_its_place(self):
        path = storage.bundle(self.bench.state, self.digest) / storage.MEMBERS / "tables/rates.csv"
        path.write_bytes(RATES.replace(b"0.1", b"0.2"))
        self.assertEqual(gaps(self.resolve(self.ref(), self.head)),
                         [{"code": c01.REF_UNAVAILABLE}])

    def test_a_reference_on_a_head_the_source_is_not_at_is_stale(self):
        answer = self.resolve(self.ref(), sha(b"old head"))
        self.assertEqual(answer["result"]["outcome"]["stage"], "stale")


class Observing(Base):
    def setUp(self):
        super().setUp()
        self.checkout = Checkout(self.scratch)
        self.checkout.write(".gitignore", b"*.tmp\n")
        self.checkout.write("docs/adr/0001.md", b"one\n")
        self.checkout.write("docs/adr/0002.md", b"two\n")
        self.checkout.write("README.md", b"readme\n")
        self.checkout.commit()
        self.checkout.write("docs/adr/0002.md", b"two, edited\n")
        self.checkout.write("docs/adr/0000-draft.md", b"draft\n")
        self.checkout.write("docs/adr/scratch.tmp", b"ignored\n")
        self.checkout.write("docs/adr-private/notes.md", b"not selected\n")

    def read(self, root: int, path: str, state: str, data: bytes) -> dict:
        return {"read": "tree", "root": root, "path": path, "state": state, "digest": sha(data),
                "size": len(data)}

    def test_an_observation_reads_the_working_tree_under_its_roots_as_git_lists_it(self):
        selection = self.selection(self.checkout, ("docs/adr", "required"),
                                   ("README.md", "optional"))
        answer = self.observe(selection)
        self.assertEqual(answer["returned"], [{
            "kind": "source_observation", "schema": 1,
            "selection_digest": canonical.digest_of(selection), "missing": [],
            "observed_at": INSTANT, "read": [
                self.read(0, "docs/adr/0001.md", "committed", b"one\n"),
                self.read(0, "docs/adr/0002.md", "modified", b"two, edited\n"),
                self.read(0, "docs/adr/0000-draft.md", "untracked", b"draft\n"),
                self.read(1, "README.md", "committed", b"readme\n")]}])
        self.assertEqual((answer["result"]["outcome"]["stage"], gaps(answer)), ("previewed", []))

    def test_a_tracked_file_deleted_from_the_working_tree_is_not_read(self):
        (self.checkout.path / "docs/adr/0001.md").unlink()
        answer = self.observe(self.selection(self.checkout, ("docs/adr", "required")))
        self.assertNotIn("docs/adr/0001.md",
                         [read["path"] for read in answer["returned"][0]["read"]])

    def test_a_symbolic_link_is_read_as_the_path_it_holds(self):
        os.symlink("/etc/hosts", self.checkout.path / "docs/adr/hosts.md")
        answer = self.observe(self.selection(self.checkout, ("docs/adr/hosts.md", "required")))
        self.assertEqual(answer["returned"][0]["read"],
                         [self.read(0, "docs/adr/hosts.md", "untracked", b"/etc/hosts")])

    def test_a_required_root_with_no_file_is_missing_and_an_optional_one_is_not_reported(self):
        answer = self.observe(self.selection(self.checkout, ("docs/none", "required"),
                                             ("docs/also-none", "optional")))
        self.assertEqual((answer["returned"][0]["missing"], answer["returned"][0]["read"]),
                         ([0], []))
        self.assertEqual(gaps(answer), [{"code": c01.REF_UNAVAILABLE, "pointer": "/roots/0"}])

    def test_observing_changes_nothing_and_keeps_the_selection_it_read(self):
        selection = self.selection(self.checkout, ("docs/adr", "required"))
        self.observe(selection)
        store = self.bench.store()
        self.assertEqual(store.get(canonical.digest_of(selection)), selection)
        self.assertEqual([self.count(t) for t in ("sources", "revisions", "repositories")],
                         [0, 0, 0])

    def test_git_reads_the_named_checkout_whatever_repository_the_caller_points_git_at(self):
        other = Checkout(self.scratch, "other")
        other.write("docs/adr/elsewhere.md", b"elsewhere\n")
        other.commit()
        with mock.patch.dict(os.environ, {"GIT_DIR": str(other.path / ".git"),
                                          "GIT_WORK_TREE": str(other.path)}):
            answer = self.observe(self.selection(self.checkout, ("docs/adr", "required")))
        self.assertEqual([read["path"] for read in answer["returned"][0]["read"]],
                         ["docs/adr/0001.md", "docs/adr/0002.md", "docs/adr/0000-draft.md"])

    def test_a_place_other_than_a_working_tree_is_not_read_yet(self):
        selection = {"kind": "source_selection", "schema": 1, "roots": [{"need": "required",
                     "place": {"from": "source_revision", "source_id": self.source,
                               "revision_digest": sha(b"revision")}}]}
        with self.assertRaises(journal.JournalError):
            self.observe(selection)


class Binding(Base):
    def setUp(self):
        super().setUp()
        self.checkout = Checkout(self.scratch)
        self.checkout.write("docs/adr/0001.md", b"one\n")
        self.checkout.commit()
        self.checkout.git("remote", "add", "origin", ORIGIN)

    def test_a_binding_states_the_remote_branch_and_head_it_observed(self):
        answer = self.bind(self.checkout)
        self.assertEqual(answer["returned"][0]["observed"], {
            "locator": ORIGIN, "branch": "main", "commit": self.checkout.git("rev-parse", "HEAD")})
        self.assertEqual(self.bench.store().read("SELECT checkout FROM repositories")[0][0],
                         str(self.checkout.path))

    def test_a_checkout_with_no_origin_is_located_by_its_directory_and_a_detached_head_by_none(
            self):
        self.checkout.git("remote", "remove", "origin")
        self.checkout.git("checkout", "-q", "--detach")
        observed = self.bind(self.checkout)["returned"][0]["observed"]
        self.assertEqual((observed["locator"], "branch" in observed),
                         (str(self.checkout.path), False))

    def test_a_binding_after_a_complete_observation_names_it(self):
        observed = self.observe(self.selection(self.checkout, ("docs/adr", "required")))
        answer = self.bind(self.checkout)
        self.assertEqual(answer["returned"][0]["observed"]["working_bytes_digest"],
                         canonical.digest_of(observed["returned"][0]))

    def test_bytes_that_moved_since_the_observation_are_not_claimed(self):
        self.observe(self.selection(self.checkout, ("docs/adr", "required")))
        self.checkout.write("docs/adr/0001.md", b"one, edited\n")
        self.assertNotIn("working_bytes_digest", self.bind(self.checkout)["returned"][0]
                         ["observed"])

    def test_an_observation_missing_a_required_root_is_passed_over(self):
        complete = self.observe(self.selection(self.checkout, ("docs/adr", "required")))
        self.observe(self.selection(self.checkout, ("docs/none", "required")))
        self.assertEqual(self.bind(self.checkout)["returned"][0]["observed"]
                         ["working_bytes_digest"], canonical.digest_of(complete["returned"][0]))

    def test_only_an_observation_of_this_repository_in_this_checkout_is_named(self):
        elsewhere = Checkout(self.scratch, "elsewhere")
        elsewhere.write("docs/adr/0001.md", b"one\n")
        elsewhere.commit()
        self.observe(self.selection(elsewhere, ("docs/adr", "required")))
        theirs = self.selection(self.checkout, ("docs/adr", "required"))
        other = bench.ident("rep")
        for root in theirs["roots"]:
            root["place"]["repository_id"] = other
        self.run_with(sources.source_observe,
                      bench.request(self.person, OBSERVE, other, theirs), [theirs], now=INSTANT)
        self.assertNotIn("working_bytes_digest", self.bind(self.checkout)["returned"][0]
                         ["observed"])

    def test_only_the_last_complete_observation_is_named_and_one_that_moved_names_none(self):
        self.checkout.write("README.md", b"readme\n")
        self.checkout.commit()
        self.observe(self.selection(self.checkout, ("docs/adr", "required")))
        self.observe(self.selection(self.checkout, ("README.md", "required")))
        self.checkout.write("README.md", b"readme, edited\n")
        self.assertNotIn("working_bytes_digest", self.bind(self.checkout)["returned"][0]
                         ["observed"])

    def test_a_directory_git_does_not_read_as_a_checkout_is_unavailable(self):
        outside = self.scratch / "not-a-checkout"
        outside.mkdir()
        payload = {"kind": "repository_binding", "schema": 1, "repository_id": self.repository,
                   "relation": {"how": "clone"}}
        with contextlib.chdir(outside), mock.patch.dict(os.environ,
                                                        {"GIT_CEILING_DIRECTORIES": str(
                                                            self.scratch)}):
            answer = self.run_with(sources.repository_bind,
                                   bench.request(self.person, BIND, self.repository, payload),
                                   [payload])
        self.assertEqual(gaps(answer), [{"code": c01.REF_UNAVAILABLE}])

    def test_a_binding_of_another_repository_than_the_target_is_a_mismatch(self):
        answer = self.bind(self.checkout, bench.ident("rep"))
        self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH,
                                         "pointer": "/target/resource_id"}])
        self.assertEqual(self.count("repositories"), 0)


if __name__ == "__main__":
    unittest.main()
