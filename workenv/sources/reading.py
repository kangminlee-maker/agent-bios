"""Reading a source back (C01): an exact reference resolved from what this installation holds.

`reference.resolve` answers the `source_ref` its payload states for the source the request
targets: the revision's manifest, the source's home at the head it read, and, when the reference
names a member, that member's bytes as the revision's bundle holds them. A reference naming
another source than the target is `request_mismatch`, and a head other than the one the request
expects is `stale_base`. A revision this installation does not hold for that source, a scope or
role other than the source's, a member the manifest does not list, or member bytes the bundle does
not hold as the manifest states them, is `ref_unavailable`: nothing is read in their place, and
no request can recover it, because asking again does not bring the bytes here.

Resolving reads only this installation's own store and bundles, so no provider is reached and
its provider effect is `not_applicable`.
"""
from __future__ import annotations

import hashlib

from workenv import journal, storage
from workenv.contracts import c01, c03
from workenv.sources import homes


def unavailable(call) -> dict:
    return journal.answered(call, "refused", gaps=[{"code": c01.REF_UNAVAILABLE}])


def member_bytes(call, revision: str, member: dict) -> bytes | None:
    """The member's bytes as the revision's bundle holds them, when they are the bytes it
    states."""
    path = storage.bundle(call.state, revision) / storage.MEMBERS / member["path"]
    if not path.is_file():
        return None
    data = path.read_bytes()
    if len(data) != member["size"] or hashlib.sha256(data).hexdigest() != member["digest"]:
        return None
    return data


def reference_resolve(call) -> dict:
    store = storage.of(call.state)
    ref = journal.payload(call)
    if ref["source_id"] != call.request["target"]["resource_id"]:
        return journal.answered(call, "refused", gaps=[{"code": c03.REQUEST_MISMATCH,
                                                        "pointer": "/target/resource_id"}],
                                recovery=["new_governed_request"])
    moved = journal.stale(call, store)
    if moved is not None:
        return moved
    held = homes.source_of(store, ref["source_id"])
    kept = store.read("SELECT 1 FROM revisions WHERE revision_digest = ? AND source_id = ?",
                      (ref["revision_digest"], ref["source_id"]))
    if held is None or not kept or held["scope"] != ref["scope"] or held["role"] != ref["role"]:
        return unavailable(call)
    manifest = store.get(ref["revision_digest"])
    values = [manifest] + ([held["home"]] if held["home"] is not None else [])
    if "member" in ref:
        if ref["member"] not in manifest["members"]:
            return unavailable(call)
        data = member_bytes(call, ref["revision_digest"], ref["member"])
        if data is None:
            return unavailable(call)
        values.append(data)
    return journal.answered(call, "previewed", values)
