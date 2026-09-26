"""Source revisions (C01): committing one immutable revision of a source this installation holds.

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
    in a repository, the files at the members' paths in the checkout bound to it. Bytes of
    another size or digest than the member states are `object_digest_mismatch` at that member;
    a member whose bytes are not at hand is stored by its hash alone.

The manifest and the bytes at hand are published as the bundle `objects/<revision>/` before the
unit of work begins, in the storage binding's order (`workenv.storage.publish`), so a revision the
journal holds always has its bundle; a bundle the journal does not hold is an interrupted commit,
and committing the same bytes again finds it by its name.
"""
from __future__ import annotations

import hashlib
import pathlib

from workenv import identity, journal, storage
from workenv.contracts import b01, c01, c03, canonical
from workenv.sources import homes

NAMESPACE = identity.NAMESPACE + "source_manifest"
AUTHORED, PUBLISHED = "repository_authored", "package_published"


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


def checkout_of(store: storage.Store, home: dict) -> pathlib.Path | None:
    found = store.read("SELECT checkout FROM repositories WHERE repository_id = ?",
                       (home["repository_id"],))
    return pathlib.Path(found[0][0]) if found and found[0][0] else None


def gathered(call, store: storage.Store, manifest: dict,
             home: dict) -> tuple[dict | None, dict[str, bytes]]:
    """The refusal of the first member whose bytes at hand differ, or None; and the members'
    bytes at hand, by path."""
    checkout = checkout_of(store, home) if home["mode"] == AUTHORED else None
    found: dict[str, bytes] = {}
    for index, member in enumerate(manifest["members"]):
        data = call.members.get(member["digest"])
        if data is None and checkout is not None and (checkout / member["path"]).is_file():
            data = (checkout / member["path"]).read_bytes()
        if data is None:
            continue
        if len(data) != member["size"] or hashlib.sha256(data).hexdigest() != member["digest"]:
            return refused(call, c03.OBJECT_DIGEST_MISMATCH, f"/members/{index}"), {}
        found[member["path"]] = data
    return None, found


def prepare(call) -> dict:
    """Refuse what can be refused before anything is written, then publish the bundle."""
    store = storage.of(call.state)
    manifest = journal.payload(call)
    source_id = call.request["target"]["resource_id"]
    if manifest["source_id"] != source_id:
        return {"answer": refused(call, c03.REQUEST_MISMATCH, "/target/resource_id")}
    held = homes.source_of(store, source_id)
    if held is None or held["home"] is None:
        return {"answer": refused(call, c01.REF_UNAVAILABLE)}
    moved = journal.stale(call, store)
    if moved is not None:
        return {"answer": moved}
    if held["home"]["home"]["mode"] == PUBLISHED:
        return {"answer": refused(call, c01.PUBLISHER_BYTES_MODIFIED)}
    refusal = unsigned(call, store, manifest)
    if refusal is not None:
        return {"answer": refusal}
    refusal, members = gathered(call, store, manifest, held["home"]["home"])
    if refusal is not None:
        return {"answer": refusal}
    stored = {**manifest, "produced_at": journal.now(call)}
    digest = canonical.digest_of(stored)
    storage.publish(call, digest, canonical.encode(stored), members)
    return {"stored": stored, "digest": digest, "held": held}


def source_revision_commit(call) -> dict:
    prepared = getattr(call, "prepared", None) or prepare(call)
    if "answer" in prepared:
        return prepared["answer"]
    store = storage.of(call.state)
    moved = journal.stale(call, store)
    if moved is not None:
        return moved
    stored, digest, held = prepared["stored"], prepared["digest"], prepared["held"]
    store.put(stored)
    position = store.read("SELECT COUNT(*) FROM revisions WHERE source_id = ?",
                          (held["source_id"],))[0][0] + 1
    store.write("INSERT OR IGNORE INTO revisions (revision_digest, source_id, position) "
                "VALUES (?, ?, ?)", (digest, held["source_id"], position))
    homes.keep_source(store, held["source_id"], held["scope"], held["role"],
                      revision_digest=digest)
    return journal.committed(call, [stored], head=digest)


source_revision_commit.prepare = prepare
