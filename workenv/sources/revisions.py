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
    in a repository, the files at the members' paths in the checkout bound to it. Bytes of
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


def checkout_of(store: storage.Store, repository_id: str) -> pathlib.Path | None:
    found = store.read("SELECT checkout FROM repositories WHERE repository_id = ?",
                       (repository_id,))
    return pathlib.Path(found[0][0]) if found and found[0][0] else None


def gathered(call, store: storage.Store, manifest: dict,
             checkout: pathlib.Path | None) -> tuple[dict | None, dict[str, bytes]]:
    """The refusal of the first member whose bytes at hand differ, or None; and the members'
    bytes at hand, by path."""
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


def published(call, store: storage.Store, manifest: dict, source: dict,
              checkout: pathlib.Path | None) -> dict:
    """What the unit of work commits, once the signatures and the bytes at hand are the manifest's
    and its bundle is published; or the answer refusing them."""
    refusal = unsigned(call, store, manifest)
    if refusal is not None:
        return {"answer": refusal}
    refusal, members = gathered(call, store, manifest, checkout)
    if refusal is not None:
        return {"answer": refusal}
    stored = {**manifest, "produced_at": journal.now(call)}
    digest = canonical.digest_of(stored)
    storage.publish(call, digest, canonical.encode(stored), members)
    return {"stored": stored, "digest": digest, "source": source}


def prepare(call) -> dict:
    """A commit: refuse what can be refused before anything is written, then publish."""
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
    where = held["home"]["home"]
    if where["mode"] == PUBLISHED:
        return {"answer": refused(call, c01.PUBLISHER_BYTES_MODIFIED)}
    return published(call, store, manifest, held, checkout_of(
        store, where["repository_id"]) if where["mode"] == AUTHORED else None)


def prepare_admission(call) -> dict:
    """An admission: refuse what can be refused before anything is written, then publish."""
    store = storage.of(call.state)
    asked = journal.payload(call)
    route = asked["route"]
    if route["route"] != "author_here":
        raise journal.JournalError(f"admitting through {route['route']} is not served yet")
    manifest = next((value for value in call.carried
                     if isinstance(value, dict) and value.get("kind") == "source_manifest"
                     and journal.digest_of(value) == route["manifest_digest"]), None)
    if manifest is None:
        return {"answer": refused(call, c01.REF_UNAVAILABLE, "/route/manifest_digest")}
    source_id = call.request["target"]["resource_id"]
    if manifest["source_id"] != source_id:
        return {"answer": refused(call, c03.REQUEST_MISMATCH, "/target/resource_id")}
    moved = journal.stale(call, store)
    if moved is not None:
        return {"answer": moved}
    destination = asked["destination"]
    source = {"source_id": source_id, "scope": destination["scope"], "role": asked["role"],
              "home_mode": destination["home_mode"]}
    held = homes.source_of(store, source_id)
    if held is not None and any(held[field] != source[field]
                                for field in ("scope", "role", "home_mode")):
        return {"answer": homes.conflict(call)}
    if destination["home_mode"] == PUBLISHED:
        return {"answer": refused(call, c01.PUBLISHER_BYTES_MODIFIED)}
    checkout = None
    if destination["home_mode"] == AUTHORED:
        checkout = checkout_of(store, destination["scope"].get("repository_id", ""))
        if checkout is None:
            return {"answer": refused(call, c01.BINDING_UNVERIFIED)}
    return published(call, store, manifest, source, checkout)


def settled(call, prepared: dict) -> dict:
    """The unit of work of a commit or an admission: the revision, and the head it moves to."""
    if "answer" in prepared:
        return prepared["answer"]
    store = storage.of(call.state)
    moved = journal.stale(call, store)
    if moved is not None:
        return moved
    stored, digest, source = prepared["stored"], prepared["digest"], prepared["source"]
    store.put(stored)
    position = store.read("SELECT COUNT(*) FROM revisions WHERE source_id = ?",
                          (source["source_id"],))[0][0] + 1
    store.write("INSERT OR IGNORE INTO revisions (revision_digest, source_id, position) "
                "VALUES (?, ?, ?)", (digest, source["source_id"], position))
    homes.keep_source(store, source["source_id"], source["scope"], source["role"],
                      source["home_mode"], revision_digest=digest)
    return journal.committed(call, [stored], head=digest)


def source_revision_commit(call) -> dict:
    return settled(call, getattr(call, "prepared", None) or prepare(call))


def source_revision_admit(call) -> dict:
    return settled(call, getattr(call, "prepared", None) or prepare_admission(call))


source_revision_commit.prepare = prepare
source_revision_admit.prepare = prepare_admission
