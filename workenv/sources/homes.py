"""Source homes (C01): where a source is authored, who accepts it, and on what conditions.

`source.home.register` registers the home its payload states for the source the request targets.
The first registration expects no head and creates the source. Registering it again names the
head it expects and changes only the home's conditions — applicability, disclosure, retention,
publication evidence, the evidence the home rests on and the Markdown view it derives — which
moves the head while every revision stays what it was. A registration that changes where the
source is authored (its mode, repository and document root, or package), the scope, the role or
the accepting authority, or a first registration of a source this installation already holds, is
a second home: `source_home_conflict`, and the source stays what it was. A repository-authored
home rests on one binding this installation holds for its repository — a repository bound from a
clone and a worktree holds two, one per checkout — and its bytes are read from the checkout that
binding was made from; a home naming a binding not held is `binding_unverified`.

A fork does not gain a second writer under the source ids it copied (SSOT S04): a request whose
owner is a repository bound here as a fork of another repository writes none of that original's
sources, and reads them only where the fork is bound to read the original through it
(`fork_original_read`) rather than only to derive its own authority (`fork_derived_authority`).
Each operation that reads or writes a source asks `as_fork`, after its own checks of the request,
and answers `repository_binding_required`; a registration that would be a second home stays
`source_home_conflict`, which it is whoever asks.

A source's head is the digest of the record its last commit stored: the home a registration
stored, or the manifest a revision commit or admission stored. How a source's home keeps it —
managed, repository-authored or package-published — is held for every source, whether its home
was registered or it was admitted with none, so a registration keeping it another way is a second
home too.
"""
from __future__ import annotations

import pathlib

from workenv import journal, storage
from workenv.contracts import c01, c03, canonical
from workenv.sources import checkouts

# Where a source is authored: registering its home again may change anything of it but these.
WHERE = ("mode", "repository_id", "document_root", "package_id")
FORK_READ, FORK_DERIVED = "fork_original_read", "fork_derived_authority"


def source_of(store: storage.Store, source_id: str) -> dict | None:
    """The source this installation holds: its scope, role, home, how the home keeps it, and its
    current revision."""
    found = store.read("SELECT scope, role, home_digest, revision_digest, home_mode FROM sources "
                       "WHERE source_id = ?", (source_id,))
    if not found:
        return None
    scope, role, home, revision, mode = found[0]
    record = store.get(home) if home else None
    return {"source_id": source_id, "scope": canonical.load(scope.encode("utf-8")),
            "role": role, "home": record, "home_digest": home, "revision_digest": revision,
            "home_mode": mode or (record["home"]["mode"] if record else None)}


def keep_source(store: storage.Store, source_id: str, scope: dict, role: str, home_mode: str,
                home_digest: str | None = None, revision_digest: str | None = None) -> None:
    """Write the source's row, keeping what the call leaves out as it was."""
    held = source_of(store, source_id)
    store.write("INSERT OR REPLACE INTO sources (source_id, scope, role, home_digest, "
                "revision_digest, home_mode) VALUES (?, ?, ?, ?, ?, ?)",
                (source_id, journal.scope_key(scope), role,
                 home_digest or (held or {}).get("home_digest"),
                 revision_digest or (held or {}).get("revision_digest"), home_mode))


def authored_at(home: dict) -> dict:
    return {field: home["home"].get(field) for field in WHERE}


def conflict(call) -> dict:
    return journal.answered(call, "refused", gaps=[{"code": c01.SOURCE_HOME_CONFLICT}],
                            recovery=["new_governed_request"])


def bound(store: storage.Store, home: dict) -> bool:
    """Whether a repository-authored home names a binding held for its repository."""
    return checkouts.holds(store, home["repository_id"], home["binding_evidence_digest"])


def as_fork(store: storage.Store, owner: dict, scope: dict, reads: bool = False) -> bool:
    """Whether a request the owner makes would use a fork as the original the scope is: the
    owner is a repository bound here as a fork of the scope's repository, and the request writes
    there, or reads there with no binding made to read the original through the fork."""
    if owner.get("layer") != "repository" or scope.get("layer") != "repository" or \
            owner.get("repository_id") == scope.get("repository_id"):
        return False
    relations = [store.get(binding)["relation"]
                 for binding, _ in checkouts.held(store, owner["repository_id"])]
    hows = {relation["how"] for relation in relations
            if relation.get("original_repository_id") == scope["repository_id"]}
    return bool(hows) and (not reads or FORK_READ not in hows)


def fork_refused(call) -> dict:
    return journal.answered(call, "refused", gaps=[{"code": c01.REPOSITORY_BINDING_REQUIRED}],
                            recovery=["new_governed_request"])


def checkout_of(store: storage.Store, source: dict) -> pathlib.Path | None:
    """The checkout a repository-authored source's bytes are read from, as `source_of` holds the
    source: the one its home's binding was made from, or, for a source admitted with no home,
    the one its repository was bound from most recently. None where the repository is bound
    from no checkout here."""
    if source["home"] is not None:
        where = source["home"]["home"]
        return checkouts.checkout_for(store, where["repository_id"],
                                      where["binding_evidence_digest"])
    return checkouts.checkout_for(store, source["scope"].get("repository_id", ""))


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
    if as_fork(store, call.request["owner"], home["scope"]):
        return fork_refused(call)
    moved = journal.stale(call, store)
    if moved is not None:
        return moved
    if held is not None and (held["scope"] != home["scope"] or held["role"] != home["role"]
                             or held["home_mode"] != home["home"]["mode"] or (
            held["home"] is not None and (
                authored_at(held["home"]) != authored_at(home)
                or held["home"]["acceptance_authority"] != home["acceptance_authority"]))):
        return conflict(call)
    if home["home"]["mode"] == "repository_authored" and not bound(store, home["home"]):
        return journal.answered(call, "refused", gaps=[{"code": c01.BINDING_UNVERIFIED}],
                                recovery=["new_governed_request"])
    stored = {**home, "registered_at": journal.now(call)}
    digest = store.put(stored)
    keep_source(store, source_id, home["scope"], home["role"], home["home"]["mode"],
                home_digest=digest)
    return journal.committed(call, [stored], head=digest)
