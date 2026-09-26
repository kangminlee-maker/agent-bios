"""Source homes (C01): where a source is authored, who accepts it, and on what conditions.

`source.home.register` registers the home its payload states for the source the request targets.
The first registration expects no head and creates the source. Registering it again names the
head it expects and changes only the home's conditions — applicability, disclosure, retention,
publication evidence, the evidence the home rests on and the Markdown view it derives — which
moves the head while every revision stays what it was. A registration that changes where the
source is authored (its mode, repository and document root, or package), the scope, the role or
the accepting authority, or a first registration of a source this installation already holds, is
a second home: `source_home_conflict`, and the source stays what it was. A repository-authored
home rests on the binding this installation holds for its repository; a home naming any other
binding is `binding_unverified`.

A source's head is the digest of the record its last commit stored: the home a registration
stored, or the manifest a revision commit stored.
"""
from __future__ import annotations

from workenv import journal, storage
from workenv.contracts import c01, c03, canonical

# Where a source is authored: registering its home again may change anything of it but these.
WHERE = ("mode", "repository_id", "document_root", "package_id")


def source_of(store: storage.Store, source_id: str) -> dict | None:
    """The source this installation holds: its scope, role, home and current revision."""
    found = store.read("SELECT scope, role, home_digest, revision_digest FROM sources "
                       "WHERE source_id = ?", (source_id,))
    if not found:
        return None
    scope, role, home, revision = found[0]
    return {"source_id": source_id, "scope": canonical.load(scope.encode("utf-8")),
            "role": role, "home": store.get(home) if home else None,
            "home_digest": home, "revision_digest": revision}


def keep_source(store: storage.Store, source_id: str, scope: dict, role: str,
                home_digest: str | None = None, revision_digest: str | None = None) -> None:
    """Write the source's row, keeping what the call leaves out as it was."""
    held = source_of(store, source_id)
    store.write("INSERT OR REPLACE INTO sources (source_id, scope, role, home_digest, "
                "revision_digest) VALUES (?, ?, ?, ?, ?)",
                (source_id, journal.scope_key(scope), role,
                 home_digest or (held or {}).get("home_digest"),
                 revision_digest or (held or {}).get("revision_digest")))


def authored_at(home: dict) -> dict:
    return {field: home["home"].get(field) for field in WHERE}


def conflict(call) -> dict:
    return journal.answered(call, "refused", gaps=[{"code": c01.SOURCE_HOME_CONFLICT}],
                            recovery=["new_governed_request"])


def bound(store: storage.Store, home: dict) -> bool:
    """Whether a repository-authored home names the binding held for its repository."""
    found = store.read("SELECT binding_digest FROM repositories WHERE repository_id = ?",
                       (home["repository_id"],))
    return bool(found) and found[0][0] == home["binding_evidence_digest"]


def source_home_register(call) -> dict:
    store = storage.of(call.state)
    home = journal.payload(call)
    source_id = call.request["target"]["resource_id"]
    if home["source_id"] != source_id:
        return journal.answered(call, "refused", gaps=[{"code": c03.REQUEST_MISMATCH,
                                                        "pointer": "/target/resource_id"}],
                                recovery=["new_governed_request"])
    held = source_of(store, source_id)
    if held is not None and call.request["target"]["base"]["expects"] == "absent":
        return conflict(call)
    moved = journal.stale(call, store)
    if moved is not None:
        return moved
    if held is not None and (held["scope"] != home["scope"] or held["role"] != home["role"] or (
            held["home"] is not None and (
                authored_at(held["home"]) != authored_at(home)
                or held["home"]["acceptance_authority"] != home["acceptance_authority"]))):
        return conflict(call)
    if home["home"]["mode"] == "repository_authored" and not bound(store, home["home"]):
        return journal.answered(call, "refused", gaps=[{"code": c01.BINDING_UNVERIFIED}],
                                recovery=["new_governed_request"])
    stored = {**home, "registered_at": journal.now(call)}
    digest = store.put(stored)
    keep_source(store, source_id, home["scope"], home["role"], home_digest=digest)
    return journal.committed(call, [stored], head=digest)
