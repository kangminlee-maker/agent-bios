"""A repository bound from more than one checkout (C01), as SRC-10's clone and worktree are, and
a fork of it, as SRC-10's fork is.

Each checkout keeps its own binding. A repository-authored home rests on one of them, and a
publication to its source reads the document root of the checkout that binding was made from,
whichever checkout was bound last. A fork bound to derive its own authority does not read the
original's sources; one bound to read the original does.
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
from test_memory import WAL, Memory, choice  # noqa: E402
from test_sources import BIND, INSTANT, RESOLVE, Checkout, gaps, home, sha  # noqa: E402

from workenv import sources, storage  # noqa: E402
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


class Forks(Bound):
    def setUp(self):
        super().setUp()
        self.clone_binding = self.bound(self.clone)
        self.source_id, registered = self.registered_on(self.clone_binding)
        published = self.publish(choice(self.scope, WAL), head=registered["receipt"]["head_digest"],
                                 source=self.source_id)
        self.revision, self.head = published["returned"][1], published["receipt"]["head_digest"]
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
