"""Source revisions (C01): committing or admitting one immutable revision of a source.

`source.revision.commit` takes the manifest its payload states for the source the request
targets and stores it with the `produced_at` the runtime owns; the stored manifest's digest is
the revision, and the source's head moves to it. In order:

  - A manifest naming another source than the target is `request_mismatch`; a source this
    installation holds no home for is `ref_unavailable`; a head other than the one the request
    expects is `stale_base`.
  - A source published by a package is the publisher's bytes: a revision of it here is
    `publisher_bytes_modified`, and an addition is a derived source with a home of its own.
  - Each signature envelope among the request's proofs must be over the payload's bytes: an
    envelope for another digest, or one that does not verify under the key of the binding it
    names, is refused by the B01 code at `/proof_digests/<i>`, and so is one from a key that is
    not one of the actor's own standing bindings. A commit with no signature needs none.
  - The members' bytes are what the person supplies with the request, and for a source authored
    in a repository, the files at the members' paths in the checkout bound to it. For a source
    whose role is `memory`, and only there, the bytes of a record the request carries are a
    member's too, because such a source's members are records (C05): a record written in another
    checkout arrives as the record it is, not as a file this installation already holds. Bytes of
    another size or digest than the member states are `object_digest_mismatch` at that member;
    a member whose bytes are not at hand is stored by its hash alone.

`source.revision.admit` admits a revision through the route its `source_request` payload names.
Only a revision authored here (`author_here`) is admitted yet; adding a published package or
importing an external one is not. The request carries the manifest the route names by
`manifest_digest`, and a route naming one it does not carry is `ref_unavailable` at
`/route/manifest_digest`. The first admission of a source expects no head and creates it in the
destination's scope, with the payload's role, kept the destination's way; a later one names the
head it expects and must name the same scope, role and way, or it is a second home:
`source_home_conflict`. A destination kept by a package is the publisher's:
`publisher_bytes_modified`. A repository-authored destination rests on a binding of its
repository held here, or it is `binding_unverified`, and its members' bytes come from that
checkout. From there an admission is a commit: the same signatures, bytes, bundle and head.

The manifest and the bytes at hand are published as the bundle `objects/<revision>/` before the
unit of work begins, in the storage binding's order (`workenv.storage.publish`), so a revision the
journal holds always has its bundle; a bundle the journal does not hold is an interrupted commit,
and committing the same bytes again finds it by its name.

Every check above but the bytes reads what the store holds, so each entry names them as its
`admits`, which the journal asks before the bundle is published and again in the unit of work,
where the answer stands (`workenv.journal`). The step that publishes reads the admission once
more for what it publishes from; where it no longer holds, the request runs again from the start.
"""
from __future__ import annotations

import hashlib
import pathlib

from workenv import identity, journal, storage
from workenv.contracts import b01, c01, c03, canonical
from workenv.sources import homes

NAMESPACE = identity.NAMESPACE + "source_manifest"
AUTHORED, PUBLISHED = "repository_authored", "package_published"
# The one role whose members are records, so a record carried with the request is a member's
# bytes (C05). For every other role the bytes at hand are the person's and the checkout's alone.
MEMORY = "memory"


def refused(call, code: str, pointer: str | None = None) -> dict:
    gap = {"code": code} if pointer is None else {"code": code, "pointer": pointer}
    return journal.answered(call, "refused", gaps=[gap], recovery=["new_governed_request"])


def unsigned(call, store: storage.Store, manifest: dict) -> dict | None:
    """The refusal of the first signature among the request's proofs that is not over these
    bytes by one of the actor's own keys, or None."""
    data = canonical.encode(manifest)
    digest = canonical.digest_of(manifest)
    own = identity.bindings_of(store, call.request["actor"]["principal_id"])
    carried = {journal.digest_of(value): value for value in call.carried}
    for index, named in enumerate(call.request["proof_digests"]):
        envelope = carried.get(named)
        if not isinstance(envelope, dict) or envelope.get("kind") != identity.ENVELOPE:
            continue
        pointer = f"/proof_digests/{index}"
        if envelope["namespace"] != NAMESPACE:
            return refused(call, b01.SIGNATURE_NAMESPACE_MISMATCH, pointer)
        if envelope["signed_digest"] != digest:
            return refused(call, b01.SIGNATURE_INVALID, pointer)
        if envelope["signer_binding_id"] not in own:
            return refused(call, b01.SIGNER_NOT_PERMITTED, pointer)
        code = identity.verify(store, envelope, data)
        if code is not None:
            return refused(call, code, pointer)
    return None


def checkout_of(store: storage.Store, repository_id: str) -> pathlib.Path | None:
    found = store.read("SELECT checkout FROM repositories WHERE repository_id = ?",
                       (repository_id,))
    return pathlib.Path(found[0][0]) if found and found[0][0] else None


def theirs(data: bytes, member: dict) -> bool:
    return len(data) == member["size"] and hashlib.sha256(data).hexdigest() == member["digest"]


def of_a_record(call, member: dict) -> bytes | None:
    """The bytes of a record the request carries that are the member's, or None. Only a memory
    source's revision reads this: its members are records (C05), so a record written in another
    checkout arrives as the record it is. For every other role the bytes at hand are what they
    were, and this is never asked."""
    for value in call.carried:
        if isinstance(value, dict) and journal.digest_of(value) == member["digest"]:
            data = canonical.encode(value)
            if theirs(data, member):
                return data
    return None


def gathered(call, manifest: dict, checkout: pathlib.Path | None,
             records: bool = False) -> tuple[dict | None, dict[str, bytes]]:
    """The refusal of the first member whose bytes at hand differ, or None; and the members'
    bytes at hand, by path. A member whose bytes are not at hand is stored by its hash alone.
    `records` adds the bytes of a record the request carries, for a memory source alone."""
    found: dict[str, bytes] = {}
    for index, member in enumerate(manifest["members"]):
        data = call.members.get(member["digest"])
        if data is None and records:
            data = of_a_record(call, member)
        if data is None and checkout is not None and (checkout / member["path"]).is_file():
            data = (checkout / member["path"]).read_bytes()
        if data is None:
            continue
        if not theirs(data, member):
            return refused(call, c03.OBJECT_DIGEST_MISMATCH, f"/members/{index}"), {}
        found[member["path"]] = data
    return None, found


def published(call, manifest: dict, source: dict, checkout: pathlib.Path | None) -> dict:
    """What the unit of work commits, once the bytes at hand are the manifest's and its bundle is
    published; or the answer refusing them."""
    refusal, members = gathered(call, manifest, checkout, source.get("role") == MEMORY)
    if refusal is not None:
        return {"answer": refusal}
    stored = {**manifest, "produced_at": journal.now(call)}
    digest = canonical.digest_of(stored)
    storage.publish(call, digest, canonical.encode(stored), members)
    return {"stored": stored, "digest": digest, "source": source}


def committing(call, store: storage.Store) -> tuple[dict | None, tuple | None]:
    """A commit's admission as the store holds it now: the refusal, or the manifest, the source
    it revises and the checkout its bytes come from."""
    manifest = journal.payload(call)
    source_id = call.request["target"]["resource_id"]
    if manifest["source_id"] != source_id:
        return refused(call, c03.REQUEST_MISMATCH, "/target/resource_id"), None
    held = homes.source_of(store, source_id)
    if held is None or held["home"] is None:
        return refused(call, c01.REF_UNAVAILABLE), None
    moved = journal.stale(call, store)
    if moved is not None:
        return moved, None
    where = held["home"]["home"]
    if where["mode"] == PUBLISHED:
        return refused(call, c01.PUBLISHER_BYTES_MODIFIED), None
    return None, (manifest, held, checkout_of(store, where["repository_id"])
                  if where["mode"] == AUTHORED else None)


def admitting(call, store: storage.Store) -> tuple[dict | None, tuple | None]:
    """An admission's admission as the store holds it now: the refusal, or the manifest, the
    source it creates or revises and the checkout its bytes come from."""
    asked = journal.payload(call)
    route = asked["route"]
    if route["route"] != "author_here":
        raise journal.JournalError(f"admitting through {route['route']} is not served yet")
    manifest = next((value for value in call.carried
                     if isinstance(value, dict) and value.get("kind") == "source_manifest"
                     and journal.digest_of(value) == route["manifest_digest"]), None)
    if manifest is None:
        return refused(call, c01.REF_UNAVAILABLE, "/route/manifest_digest"), None
    source_id = call.request["target"]["resource_id"]
    if manifest["source_id"] != source_id:
        return refused(call, c03.REQUEST_MISMATCH, "/target/resource_id"), None
    moved = journal.stale(call, store)
    if moved is not None:
        return moved, None
    destination = asked["destination"]
    source = {"source_id": source_id, "scope": destination["scope"], "role": asked["role"],
              "home_mode": destination["home_mode"]}
    held = homes.source_of(store, source_id)
    if held is not None and any(held[field] != source[field]
                                for field in ("scope", "role", "home_mode")):
        return homes.conflict(call), None
    if destination["home_mode"] == PUBLISHED:
        return refused(call, c01.PUBLISHER_BYTES_MODIFIED), None
    checkout = None
    if destination["home_mode"] == AUTHORED:
        checkout = checkout_of(store, destination["scope"].get("repository_id", ""))
        if checkout is None:
            return refused(call, c01.BINDING_UNVERIFIED), None
    return None, (manifest, source, checkout)


def admits(reading):
    """The admission checks the journal asks before the unit of work and again in it: the
    target as the store holds it, then the signatures, whose signers' bindings it holds too."""
    def checks(call, store: storage.Store) -> dict | None:
        refusal, admitted = reading(call, store)
        return refusal or unsigned(call, store, admitted[0])
    return checks


def preparing(reading):
    """The step before the unit of work: the bytes, published. The admission it reads was
    asked a moment before; where it no longer holds, the request runs again from the start."""
    def prepare(call) -> dict:
        refusal, admitted = reading(call, storage.of(call.state))
        if refusal is not None:
            raise journal.Again(call.request["request_id"])
        return published(call, *admitted)
    return prepare


def settled(call) -> dict:
    """The unit of work of a commit or an admission the journal admitted in it: the revision,
    and the head it moves to."""
    prepared = call.prepared
    if "answer" in prepared:
        return prepared["answer"]
    store = storage.of(call.state)
    stored, digest = prepared["stored"], prepared["digest"]
    source = homes.source_of(store, prepared["source"]["source_id"]) or prepared["source"]
    store.put(stored)
    position = store.read("SELECT COUNT(*) FROM revisions WHERE source_id = ?",
                          (source["source_id"],))[0][0] + 1
    store.write("INSERT OR IGNORE INTO revisions (revision_digest, source_id, position) "
                "VALUES (?, ?, ?)", (digest, source["source_id"], position))
    homes.keep_source(store, source["source_id"], source["scope"], source["role"],
                      source["home_mode"], revision_digest=digest)
    return journal.committed(call, [stored], head=digest)


def source_revision_commit(call) -> dict:
    return settled(call)


def source_revision_admit(call) -> dict:
    return settled(call)


source_revision_commit.admits, source_revision_commit.prepare = (admits(committing),
                                                                preparing(committing))
source_revision_admit.admits, source_revision_admit.prepare = (admits(admitting),
                                                              preparing(admitting))
