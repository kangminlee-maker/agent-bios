"""A repository bound from more than one checkout (C01), as SRC-10's clone and worktree are, and
a fork of it, as SRC-10's fork is.

Each checkout keeps its own binding. A repository-authored home rests on one of them, and a
publication, a commit or an admission to its source reads the checkout that binding was made
from, whichever checkout was bound last; two checkouts making the same binding leave it with the
first while that one still holds it. The entry names the branch of the checkout it is opened in.
A fork writes none of the original's sources however it is bound, and reads them only where it
is bound to read the original.
"""
from __future__ import annotations

import contextlib
import pathlib
import sqlite3
import sys

V1 = pathlib.Path(__file__).resolve().parents[1] / "v1"
if str(V1) not in sys.path:
    sys.path.insert(0, str(V1))

import bench  # noqa: E402
from test_memory import WAL, Memory, asked, choice, event  # noqa: E402
from test_sources import (BIND, INSTANT, ORIGIN, RESOLVE, Checkout, gaps, home,  # noqa: E402
                          manifest, sha)

from workenv import journal, memory, sources, storage, tui  # noqa: E402
from workenv.contracts import c01, canonical  # noqa: E402
from workenv.sources import checkouts  # noqa: E402

CLONE_ADR, WORKTREE_ADR = b"# ADR 0001\n\nWAL.\n", b"# ADR 0001\n\nA rollback journal.\n"


class Bound(Memory):
    """A clone and a worktree of one repository, each holding its own ADR 0001."""

    def setUp(self):
        super().setUp()
        self.clone = self.made("work", CLONE_ADR)
        self.worktree = self.made("work-feature", WORKTREE_ADR)
        self.scope = {"layer": "repository", "repository_id": self.repository}

    def made(self, name: str, adr: bytes) -> Checkout:
        checkout = Checkout(self.scratch, name)
        checkout.write("docs/adr/0001-journal-mode.md", adr)
        checkout.commit()
        return checkout

    def bound(self, checkout: Checkout) -> str:
        """The digest of the binding made from that checkout."""
        return canonical.digest_of(self.bind(checkout)["returned"][0])

    def registered_on(self, binding: str) -> tuple[str, dict]:
        source_id = bench.ident("src")
        return source_id, self.register(home(
            self.person, source_id, role="memory", scope=self.scope,
            acceptance_authority=self.scope,
            home={"mode": "repository_authored", "repository_id": self.repository,
                  "document_root": "docs/adr", "binding_evidence_digest": binding}))

    def cloned(self, name: str) -> Checkout:
        """A git clone of the clone, on its commit and with its remote."""
        made = Checkout.__new__(Checkout)
        made.path, made.env = self.scratch / name, dict(self.clone.env)
        self.clone.git("clone", "-q", "--no-hardlinks", str(self.clone.path), str(made.path))
        made.git("remote", "set-url", "origin", ORIGIN)
        return made

    def admitted(self, source_id: str, data: bytes) -> dict:
        """The ADR as `data`, admitted again through `author_here` to a source held here."""
        stated = manifest(source_id, {"docs/adr/0001-journal-mode.md": data})
        payload = {"kind": "source_request", "schema": 1, "role": "memory",
                   "destination": {"scope": self.scope, "home_mode": "repository_authored"},
                   "route": {"route": "author_here",
                             "manifest_digest": canonical.digest_of(stated)}}
        target = {"resource_id": source_id,
                  "base": {"expects": "head",
                           "head_digest": journal.head_of(self.bench.store(), source_id)}}
        return self.run_with(sources.source_revision_admit,
                             bench.request(self.person, "source.revision.admit", target, payload),
                             [payload, stated], now=INSTANT)

    def adr_published(self, source_id: str, head: str) -> dict:
        answer = self.publish(choice(self.scope, WAL), head=head, source=source_id)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", answer["result"])
        return answer["returned"][1]["members"][0]


class Checkouts(Bound):
    def test_a_clone_and_a_worktree_of_one_repository_are_both_held(self):
        clone, worktree = self.bound(self.clone), self.bound(self.worktree)
        store = self.bench.store()
        self.assertEqual(checkouts.held(store, self.repository),
                         [(worktree, self.worktree.path), (clone, self.clone.path)])

    def test_a_home_on_the_clone_reads_the_clone_after_the_worktree_was_bound(self):
        clone = self.bound(self.clone)
        self.bound(self.worktree)
        source_id, registered = self.registered_on(clone)
        self.assertEqual(registered["result"]["outcome"]["stage"], "committed")
        member = self.adr_published(source_id, registered["receipt"]["head_digest"])
        self.assertEqual((member["digest"], member["size"]), (sha(CLONE_ADR), len(CLONE_ADR)))

    def test_binding_the_same_checkout_again_keeps_the_homes_checkout(self):
        # The clone is bound again on a new commit, so the home's binding is no longer held,
        # and the worktree is bound last: the home still reads the checkout its binding was
        # made from.
        clone = self.bound(self.clone)
        source_id, registered = self.registered_on(clone)
        self.clone.write("README.md", b"moved on\n")
        self.clone.commit()
        self.assertNotEqual(self.bound(self.clone), clone)
        self.bound(self.worktree)
        member = self.adr_published(source_id, registered["receipt"]["head_digest"])
        self.assertEqual(member["digest"], sha(CLONE_ADR))

    def test_a_home_naming_a_binding_since_replaced_is_unverified(self):
        clone = self.bound(self.clone)
        self.clone.write("README.md", b"moved on\n")
        self.clone.commit()
        self.assertNotEqual(self.bound(self.clone), clone)
        _, registered = self.registered_on(clone)
        self.assertEqual([gap["code"] for gap in registered["result"]["outcome"]["material_gaps"]],
                         [c01.BINDING_UNVERIFIED])

    def test_a_binding_this_store_kept_no_checkout_for_reads_the_newest_checkout(self):
        # A store laid out before bindings were kept by checkout knows only the bindings it
        # still holds; a home on one replaced since reads where every home read then.
        clone = self.bound(self.clone)
        source_id, registered = self.registered_on(clone)
        self.bound(self.worktree)
        bench.restart(self.bench.state)
        connection = sqlite3.connect(self.bench.state / storage.DATABASE, isolation_level=None)
        try:
            connection.execute("DELETE FROM binding_checkouts WHERE binding_digest = ?", (clone,))
            connection.execute("DELETE FROM repositories WHERE binding_digest = ?", (clone,))
        finally:
            connection.close()
        member = self.adr_published(source_id, registered["receipt"]["head_digest"])
        self.assertEqual(member["digest"], sha(WORKTREE_ADR))


class Places(Bound):
    def setUp(self):
        super().setUp()
        self.clone.git("remote", "add", "origin", ORIGIN)

    def test_a_checkout_making_the_same_binding_as_another_leaves_the_home_on_the_first(self):
        # A clone of the clone on the same commit and remote, bound before an observation reads
        # either, makes the very binding the clone made.
        copy = self.cloned("work-copy")
        clone = self.bound(self.clone)
        source_id, registered = self.registered_on(clone)
        copy.write("docs/adr/0001-journal-mode.md", WORKTREE_ADR)
        self.assertEqual(self.bound(copy), clone)
        member = self.adr_published(source_id, registered["receipt"]["head_digest"])
        self.assertEqual(member["digest"], sha(CLONE_ADR))
        self.assertFalse((copy.path / "docs/adr/records.jsonl").exists())

    def test_a_binding_its_first_checkout_moved_on_from_is_read_where_it_is_still_held(self):
        copy = self.cloned("work-copy")
        clone = self.bound(self.clone)
        self.assertEqual(self.bound(copy), clone)
        source_id, registered = self.registered_on(clone)
        self.clone.write("docs/adr/0001-journal-mode.md", WORKTREE_ADR)
        self.clone.commit()
        self.assertNotEqual(self.bound(self.clone), clone)
        member = self.adr_published(source_id, registered["receipt"]["head_digest"])
        self.assertEqual(member["digest"], sha(CLONE_ADR))
        self.assertTrue((copy.path / "docs/adr/records.jsonl").exists())

    def test_an_admission_to_a_source_held_here_reads_its_homes_checkout(self):
        source_id, _ = self.registered_on(self.bound(self.clone))
        self.bound(self.worktree)
        theirs = self.admitted(source_id, WORKTREE_ADR)
        self.assertEqual(gaps(theirs),
                         [{"code": "object_digest_mismatch", "pointer": "/members/0"}])
        ours = self.admitted(source_id, CLONE_ADR)
        self.assertEqual(ours["result"]["outcome"]["stage"], "committed", ours["result"])

    def test_the_entry_names_the_branch_of_the_checkout_it_is_opened_in(self):
        self.worktree.git("checkout", "-q", "-b", "feature-backups")
        self.bound(self.clone)
        self.bound(self.worktree)
        store = self.bench.store()
        self.assertEqual(tui.location_of(store, self.scope, self.clone.path)["branch"], "main")
        self.assertEqual(tui.location_of(store, self.scope, self.worktree.path)["branch"],
                         "feature-backups")
        self.assertEqual(tui.location_of(store, self.scope, self.scratch)["branch"],
                         "feature-backups")


class Forks(Bound):
    def setUp(self):
        super().setUp()
        self.clone_binding = self.bound(self.clone)
        self.source_id, registered = self.registered_on(self.clone_binding)
        published = self.publish(choice(self.scope, WAL), head=registered["receipt"]["head_digest"],
                                 source=self.source_id)
        self.revision, self.head = published["returned"][1], published["receipt"]["head_digest"]
        self.record_id = published["returned"][0]["record_id"]
        self.fork_repository = bench.ident("rep")
        self.fork = self.made("work-fork", CLONE_ADR)

    def fork_bound(self, how: str) -> None:
        payload = {"kind": "repository_binding", "schema": 1,
                   "repository_id": self.fork_repository,
                   "relation": {"how": how, "original_repository_id": self.repository,
                                "authority_evidence_digest": self.clone_binding}}
        with contextlib.chdir(self.fork.path):
            answer = self.run_with(sources.repository_bind,
                                   bench.request(self.person, BIND, self.fork_repository,
                                                 payload), [payload], now=INSTANT)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", answer["result"])

    def read_from(self, repository: str) -> dict:
        """The source's revision resolved for a request the repository makes."""
        ref = {"kind": "source_ref", "schema": 1, "source_id": self.source_id, "role": "memory",
               "scope": self.scope, "revision_digest": canonical.digest_of(self.revision)}
        target = {"resource_id": self.source_id,
                  "base": {"expects": "head", "head_digest": self.head}}
        owner = {"layer": "repository", "repository_id": repository}
        return self.run_with(sources.reference_resolve,
                             bench.request(self.person, RESOLVE, target, ref, owner=owner), [ref])

    def test_a_fork_bound_to_derive_its_own_authority_does_not_read_its_original(self):
        self.fork_bound("fork_derived_authority")
        answer = self.read_from(self.fork_repository)
        self.assertEqual((gaps(answer), answer["result"]["supported_recovery"],
                          answer["returned"]),
                         ([{"code": c01.REPOSITORY_BINDING_REQUIRED}], ["new_governed_request"],
                          []))
        self.assertEqual(self.read_from(self.repository)["returned"][0], self.revision)

    def test_a_fork_bound_to_read_its_original_reads_it(self):
        self.fork_bound("fork_original_read")
        self.assertEqual(self.read_from(self.fork_repository)["returned"][0], self.revision)

    def test_a_repository_bound_as_no_fork_of_the_original_is_not_refused_as_one(self):
        self.assertEqual(self.read_from(bench.ident("rep"))["returned"][0], self.revision)

    def as_the_fork(self, entry, operation: str, target: dict, payload: dict,
                    carried=None) -> dict:
        owner = {"layer": "repository", "repository_id": self.fork_repository}
        return self.run_with(entry, bench.request(self.person, operation, target, payload,
                                                  owner=owner),
                             [payload] if carried is None else carried, now=INSTANT)

    def writes(self) -> dict[str, dict]:
        """Each way a request could write the original's source, made by the fork."""
        at_head = {"resource_id": self.source_id,
                   "base": {"expects": "head", "head_digest": self.head}}
        stated = manifest(self.source_id, {"docs/adr/0001-journal-mode.md": CLONE_ADR})
        admission = {"kind": "source_request", "schema": 1, "role": "memory",
                     "destination": {"scope": self.scope, "home_mode": "repository_authored"},
                     "route": {"route": "author_here",
                               "manifest_digest": canonical.digest_of(stated)}}
        conditions = home(self.person, self.source_id, role="memory", scope=self.scope,
                          acceptance_authority=self.scope, disclosure="published",
                          home={"mode": "repository_authored", "repository_id": self.repository,
                                "document_root": "docs/adr",
                                "binding_evidence_digest": self.clone_binding})
        return {
            "publish": self.as_the_fork(memory.memory_record_publish, "memory.record.publish",
                                        at_head, choice(self.scope, WAL)),
            "lifecycle": self.as_the_fork(memory.memory_lifecycle_apply,
                                          "memory.lifecycle.apply", at_head,
                                          event(self.person.principal, self.record_id,
                                                "adopted")),
            "register": self.as_the_fork(sources.source_home_register, "source.home.register",
                                         at_head, conditions),
            "commit": self.as_the_fork(sources.source_revision_commit, "source.revision.commit",
                                       at_head, stated),
            "admit": self.as_the_fork(sources.source_revision_admit, "source.revision.admit",
                                      at_head, admission, [admission, stated]),
        }

    def test_a_fork_writes_none_of_its_originals_sources_however_it_is_bound(self):
        for how in ("fork_derived_authority", "fork_original_read"):
            with self.subTest(how=how):
                self.fork_bound(how)
                records = (self.clone.path / "docs/adr/records.jsonl").read_bytes()
                for name, answer in self.writes().items():
                    self.assertEqual(gaps(answer),
                                     [{"code": c01.REPOSITORY_BINDING_REQUIRED}], name)
                self.assertEqual((self.clone.path / "docs/adr/records.jsonl").read_bytes(),
                                 records)
                self.assertEqual(journal.head_of(self.bench.store(), self.source_id), self.head)

    def test_a_fork_resolves_its_originals_state_only_where_it_is_bound_to_read_it(self):
        question = asked([self.scope])
        for how, stage in (("fork_derived_authority", "refused"),
                           ("fork_original_read", "previewed")):
            with self.subTest(how=how):
                self.fork_bound(how)
                answer = self.as_the_fork(memory.memory_state_resolve, "memory.state.resolve",
                                          {"resource_id": bench.ident("cnc")}, question)
                self.assertEqual(answer["result"]["outcome"]["stage"], stage, answer["result"])
