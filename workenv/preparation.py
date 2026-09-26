"""Preparation and composition (C07): the nine positions, and an environment composed from them.

Each repository, person and Team keeps one collection per role — Instructions, knowledge and
memory — and each collection is the original of its position. `collection.change` stores the
collection its payload states for the collection the request targets, with the `changed_at` the
runtime owns; its head is the digest of that stored collection. The first change of a collection
expects no head and every later one names the head it expects (`stale_base`). A collection keeps
the one position it was created for, and a position is kept by one collection: a change moving a
collection to another position, or creating a second collection for a position held by another,
is `request_mismatch` at `/position`, and one whose owner is not the position's scope is
`request_mismatch` at `/owner`, because the receipt goes to that owner. A draft the change lists
is staged as the change carries it: its `source_manifest` must be among the carried records
(`ref_unavailable` at that draft) and name the draft's source (`request_mismatch`); the manifest
and the member bytes carried with it are kept by digest, and nothing accepts them — no revision,
no source head. `collection.read` answers the collection at the head the position holds.

`preparation.compose` composes the preparation its `preparation_request` asks for, for the
requester alone (a target other than the actor's principal is `request_mismatch`). It reads and
writes no position: it names each one it read at its head, and is stored whole, apart from every
original, so its answer moves no head and names no receipt. Only a basis of scoped ad hoc sources
is composed yet; an adopted environment's basis and a requested task's support are not.

  - **Order.** The scopes are applied repository, then personal, then Team, unless the request
    states an explicit order, which must name the basis's scopes and no others
    (`request_mismatch` at `/order`).
  - **Positions.** Role by role — Instructions, knowledge, memory — each scope's position of that
    role in the applied order, where one is held: `switched_off` contributes nothing, a position
    with no entry is `empty` and contributes nothing, and every other one is `applied`.
  - **Units.** An Instructions or knowledge entry contributes the units it declares from its
    pinned revision, in the layer of its position's scope whoever owns the source, and an entry
    declaring none contributes each member of that revision as unkeyed prose. A source pinned by
    the basis alone contributes each member of its revision as unkeyed prose, in the layer of its
    own scope. An entry switched off contributes its units `disabled`. An entry naming a source,
    revision or member this installation does not hold is `selection_unresolved` at its
    position: it is not absence, and nothing lower is said to satisfy it. A source of another
    role than its position's is not composed there: knowledge or memory in an Instructions
    position is `role_promotion_refused`, and any other is `selection_unresolved`. Units are
    listed in the order they were read: role by role, then layer by layer in the applied
    order, then the positions' entries and the pinned sources as they are stated.
  - **Competition.** Units that declare one concern within one role compete: the unit of the
    first layer in the order wins, and the others are `shadowed` by it. Units of that one layer
    compete by their entries' explicit precedence, lowest first; where no precedence orders the
    lowest against every other, the concern is `unresolved` for the query that needs it, each unit
    of that first layer states `same_layer_unordered`, and nothing else is held back. A unit with no
    concern is unkeyed prose, `layered` in its labelled layer. A winning unit's declared needs
    name it in the needed unit's `needed_by`; a unit that does not win names nothing.
  - **Bodies.** A unit's body is its member's bytes in the pinned revision's bundle, the
    immutable snapshot every revision is read from, whoever authors it: a repository-authored
    source's working tree is what the checkout records, never a body. A unit states its body's
    digest only where the bundle holds the member's bytes. A winning or layered unit whose bytes
    the bundle does not hold is `role_body_unavailable`, and one whose bytes are other bytes is
    `object_digest_mismatch`, each at that unit; a shadowed or disabled unit gates nothing.
  - **Memory.** A memory entry, or a pinned memory source, contributes no unit: it fixes the
    frontier of its source as this operation observes it, the source's head.
  - **The checkout.** The preparation records the checkout it was composed in as it is now: the
    repository bound from the working tree the process runs in, with its remote, branch, HEAD and
    selected working bytes; or the directory alone where no repository is bound from it. Working
    bytes the binding claimed that the working tree no longer reads as are `working_bytes_moved`.
  - **The recipient.** The request's work scope, else the first scope its basis names, and the
    recipient link the request names, which must be held here (`recipient_link_unknown`). A
    recipient is `proven_fresh` unless its link says otherwise: a start composes the whole context
    it hands over, and inherits none.
  - **A session start.** A preparation declaring `session.routing.activate` for a named link also
    records that session as selected only: a `session_routing` with no projection and no usage
    contract, which leaves the always surface unchanged and native files preserved.
"""
from __future__ import annotations

import hashlib
import pathlib

from workenv import journal, storage
from workenv.contracts import c01, c03, c04, c07, c11, canonical
from workenv.sources import checkouts, homes

ROLES = ("instructions", "knowledge", "memory")
INSTRUCTIONS, MEMORY = "instructions", "memory"
DEFAULT_ORDER = ("repository", "personal", "team")
SESSION_START = "session.routing.activate"
# The one adapter this module composes for: the host session a preparation is handed to.
ADAPTER = {"name": "session_adapter", "version": "0.1.0"}
DELIVERED = ("winning", "layered")


def refused(call, code: str, pointer: str | None = None) -> dict:
    gap = {"code": code} if pointer is None else {"code": code, "pointer": pointer}
    return journal.answered(call, "refused", gaps=[gap], recovery=["new_governed_request"])


def held_collection(store: storage.Store, scope: dict, role: str) -> str | None:
    found = store.read("SELECT collection_id FROM collections WHERE scope = ? AND role = ?",
                       (journal.scope_key(scope), role))
    return found[0][0] if found else None


# Collections.

def collection_change(call) -> dict:
    store = storage.of(call.state)
    collection = journal.payload(call)
    collection_id = call.request["target"]["resource_id"]
    if collection["collection_id"] != collection_id:
        return refused(call, c03.REQUEST_MISMATCH, "/target/resource_id")
    moved = journal.stale(call, store)
    if moved is not None:
        return moved
    position = collection["position"]
    scope, role = journal.scope_key(position["scope"]), position["role"]
    kept = store.read("SELECT scope, role FROM collections WHERE collection_id = ?",
                      (collection_id,))
    other = held_collection(store, position["scope"], role)
    if (kept and kept[0] != (scope, role)) or (other is not None and other != collection_id):
        return refused(call, c03.REQUEST_MISMATCH, "/position")
    if call.request["owner"] != position["scope"]:
        return refused(call, c03.REQUEST_MISMATCH, "/owner")
    carried = {journal.digest_of(value): value for value in call.carried}
    drafts = []
    for index, draft in enumerate(collection["drafts"]):
        manifest = carried.get(draft["manifest_digest"])
        if not isinstance(manifest, dict) or manifest.get("kind") != "source_manifest":
            return refused(call, c01.REF_UNAVAILABLE, f"/drafts/{index}/manifest_digest")
        if manifest["source_id"] != draft["source_id"]:
            return refused(call, c03.REQUEST_MISMATCH, f"/drafts/{index}/source_id")
        drafts.append(manifest)
    for manifest in drafts:
        store.put(manifest)
        for member in manifest["members"]:
            data = call.members.get(member["digest"])
            if data is not None and len(data) == member["size"]:
                store.put(data)
    stored = {**collection, "changed_at": journal.now(call)}
    digest = store.put(stored)
    store.write("INSERT OR IGNORE INTO collections (collection_id, scope, role) VALUES (?, ?, ?)",
                (collection_id, scope, role))
    return journal.committed(call, [stored], head=digest)


def collection_read(call) -> dict:
    store = storage.of(call.state)
    moved = journal.stale(call, store)
    if moved is not None:
        return moved
    head = journal.head_of(store, call.request["target"]["resource_id"])
    if head is None:
        return journal.answered(call, "refused", gaps=[{"code": c01.REF_UNAVAILABLE}])
    return journal.answered(call, "previewed", [store.get(head)])


# Composition.

def layer_rank(order: list[dict], layer: str) -> int:
    """Where a layer applies: only units of a position compete, and its scope is in the order."""
    return [scope["layer"] for scope in order].index(layer)


def body_of(call, revision: str, member: dict) -> tuple[str | None, str | None]:
    """(the member's digest, None) where the revision's bundle holds its bytes, else (None, why)."""
    path = storage.bundle(call.state, revision) / storage.MEMBERS / member["path"]
    if not path.is_file():
        return None, c04.ROLE_BODY_UNAVAILABLE
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != member["digest"]:
        return None, c03.OBJECT_DIGEST_MISMATCH
    return member["digest"], None


class Composition:
    """One preparation being composed: what it read, in the order it read it."""

    def __init__(self, call, store: storage.Store, order: list[dict]):
        self.call, self.store, self.order = call, store, order
        self.collections: list[dict] = []
        self.units: list[dict] = []
        self.frontiers: list[dict] = []
        self.gaps: list[dict] = []

    def unresolved(self, where: str) -> None:
        self.gaps.append({"code": c07.SELECTION_UNRESOLVED, "pointer": where})

    def revision_of(self, source_id: str, revision: str | None) -> tuple[dict, dict] | None:
        source = homes.source_of(self.store, source_id)
        if source is None or revision is None or not self.store.read(
                "SELECT 1 FROM revisions WHERE revision_digest = ? AND source_id = ?",
                (revision, source_id)):
            return None
        return source, self.store.get(revision)

    def frontier(self, source_id: str, where: str) -> None:
        head = journal.head_of(self.store, source_id)
        if head is None:
            self.unresolved(where)
            return
        found = {"source_id": source_id, "checkpoint_digest": head}
        if found not in self.frontiers:
            self.frontiers.append(found)

    def unit(self, source: dict, revision: str, member: dict, declared: dict | None,
             switch: str, precedence: int | None, layer: str) -> None:
        unit = {"unit_id": journal.mint("unt"), "source_id": source["source_id"],
                "revision_digest": revision, "role": source["role"], "layer": layer,
                "member": member["path"]}
        if source["home_digest"] is not None:
            unit["home_digest"] = source["home_digest"]
        declared = declared or {}
        for field in ("concern", "startup"):
            if field in declared:
                unit[field] = declared[field]
        if switch == "off":
            unit["standing"] = "disabled"
        elif "concern" not in declared:
            unit["standing"] = "layered"
        self.units.append({"unit": unit, "member": member, "precedence": precedence,
                           "needs": declared.get("needs", [])})

    def entry(self, entry: dict, scope: dict, role: str, where: str) -> None:
        held = homes.source_of(self.store, entry["source_id"])
        if held is not None and held["role"] != role:
            code = c04.ROLE_PROMOTION_REFUSED if role == INSTRUCTIONS else \
                c07.SELECTION_UNRESOLVED
            self.gaps.append({"code": code, "pointer": where})
            return
        if role == MEMORY:
            if entry["switch"] == "on":
                self.frontier(entry["source_id"], where)
            return
        pin = entry["pin"]
        found = self.revision_of(entry["source_id"], pin.get("revision_digest"))
        if found is None:
            self.unresolved(where)
            return
        source, manifest = found
        members = {member["path"]: member for member in manifest["members"]}
        declared = entry.get("units") or [{"member": path} for path in members]
        for unit in declared:
            if unit["member"] not in members:
                self.unresolved(where)
                continue
            self.unit(source, pin["revision_digest"], members[unit["member"]],
                      unit if "units" in entry else None, entry["switch"],
                      entry.get("precedence"), scope["layer"])

    def position(self, scope: dict, role: str) -> None:
        collection_id = held_collection(self.store, scope, role)
        if collection_id is None:
            return
        head = journal.head_of(self.store, collection_id)
        collection = self.store.get(head)
        state = ("switched_off" if collection["switch"] == "off"
                 else "empty" if not collection["entries"] else "applied")
        where = f"/collections/{len(self.collections)}"
        self.collections.append({"collection_id": collection_id, "head_digest": head,
                                 "state": state})
        if state == "applied":
            for entry in collection["entries"]:
                self.entry(entry, scope, role, where)

    def pinned(self, pin: dict, source: dict, manifest: dict) -> None:
        if source["role"] == MEMORY:
            self.frontier(source["source_id"], "")
            return
        for member in manifest["members"]:
            self.unit(source, pin["revision_digest"], member, None, "on", None,
                      source["scope"]["layer"])

    def compose(self, pins: list[tuple[dict, dict, dict]]) -> None:
        keys = [journal.scope_key(scope) for scope in self.order]
        for role in ROLES:
            for scope in self.order:
                self.position(scope, role)
                for pin, source, manifest in pins:
                    if source["role"] == role and journal.scope_key(source["scope"]) == \
                            journal.scope_key(scope):
                        self.pinned(pin, source, manifest)
            for pin, source, manifest in pins:
                if source["role"] == role and journal.scope_key(source["scope"]) not in keys:
                    self.pinned(pin, source, manifest)
        self.compete()
        self.bodies()

    def compete(self) -> None:
        concerns: dict[tuple[str, str], list[dict]] = {}
        for held in self.units:
            if "standing" not in held["unit"]:
                unit = held["unit"]
                concerns.setdefault((unit["role"], unit["concern"]), []).append(held)
        for competing in concerns.values():
            first = min(layer_rank(self.order, held["unit"]["layer"]) for held in competing)
            top = [held for held in competing
                   if layer_rank(self.order, held["unit"]["layer"]) == first]
            winner = top[0] if len(top) == 1 else next(
                (held for held in top if held["precedence"] is not None and all(
                    other is held or (other["precedence"] is not None
                                      and other["precedence"] > held["precedence"])
                    for other in top)), None)
            for held in competing:
                unit = held["unit"]
                if winner is None:
                    unit["standing"] = "unresolved"
                    held["unordered"] = any(other is held for other in top)
                elif held is winner:
                    unit["standing"] = "winning"
                else:
                    unit["standing"] = "shadowed"
                    unit["shadowed_by"] = winner["unit"]["unit_id"]
        for held in self.units:
            if held["unit"]["standing"] != "winning":
                continue
            for need in held["needs"]:
                for other in self.units:
                    if (other["unit"]["source_id"], other["unit"]["member"]) == \
                            (need["source_id"], need["member"]):
                        other["unit"].setdefault("needed_by", []).append(
                            held["unit"]["unit_id"])

    def bodies(self) -> None:
        for index, held in enumerate(self.units):
            unit = held["unit"]
            if held.get("unordered"):
                self.gaps.append({"code": c07.SAME_LAYER_UNORDERED, "pointer": f"/units/{index}"})
            if unit["standing"] == "disabled":
                continue
            digest, why = body_of(self.call, unit["revision_digest"], held["member"])
            if digest is not None:
                unit["body_digest"] = digest
            elif unit["standing"] in DELIVERED:
                self.gaps.append({"code": why, "pointer": f"/units/{index}"})


def observed(store: storage.Store) -> tuple[dict, list[dict]]:
    """The checkout the process works in as it is now, and `working_bytes_moved` where the
    working bytes its binding claimed are not what it reads as now."""
    here = pathlib.Path.cwd().resolve()
    checkout = checkouts.top(here)
    bound = checkouts.bound_at(store, checkout) if checkout is not None else None
    if bound is None:
        return {"locator": str(checkout or here)}, []
    repository_id, binding = bound
    now = checkouts.observed_in(store, repository_id, checkout)
    claimed = binding["observed"].get("working_bytes_digest")
    moved = claimed is not None and now.get("working_bytes_digest") != claimed
    return now, [{"code": c07.WORKING_BYTES_MOVED}] if moved else []


def preparation_compose(call) -> dict:
    store = storage.of(call.state)
    request = call.request
    asked = journal.payload(call)
    if request["target"]["resource_id"] != request["actor"]["principal_id"]:
        return refused(call, c03.REQUEST_MISMATCH, "/target/resource_id")
    basis = asked["basis"]
    if basis["from"] != "ad_hoc":
        raise journal.JournalError("composing on an adopted environment is not served yet")
    if "work_request" in asked:
        raise journal.JournalError("assessing a requested task's support is not served yet")
    scopes = basis["scopes"]
    order = asked.get("order") or sorted(scopes, key=lambda scope: DEFAULT_ORDER.index(
        scope["layer"]))
    if sorted(map(journal.scope_key, order)) != sorted(map(journal.scope_key, scopes)):
        return refused(call, c03.REQUEST_MISMATCH, "/order")
    link = None
    if "recipient_digest" in request:
        link = store.get(request["recipient_digest"])
        if not isinstance(link, dict) or link.get("kind") != "recipient_link":
            return refused(call, c11.RECIPIENT_LINK_UNKNOWN, "/recipient_digest")
    composition = Composition(call, store, order)
    pins = []
    for index, pin in enumerate(basis["source_pins"]):
        found = composition.revision_of(pin["source_id"], pin["revision_digest"])
        if found is None:
            return refused(call, c01.REF_UNAVAILABLE, f"/basis/source_pins/{index}")
        pins.append((pin, *found))
    composition.compose(pins)
    checkout, moved = observed(store)
    recipient = {"work_scope": request.get("work_scope") or scopes[0],
                 "isolation": link["isolation"] if link else "proven_fresh"}
    if link is not None:
        recipient["recipient_digest"] = request["recipient_digest"]
    gaps = composition.gaps + moved
    preparation = {"kind": "preparation", "schema": 1, "preparation_id": journal.mint("prp"),
                   "request_digest": canonical.digest_of(asked), "order": order,
                   "collections": composition.collections,
                   "units": [held["unit"] for held in composition.units],
                   "frontiers": composition.frontiers, "observed": checkout, "adapter": ADAPTER,
                   "recipient": recipient, "work_support": {"assessed": "not_requested"},
                   "omissions": [], "material_gaps": gaps, "prepared_at": journal.now(call)}
    store.write("INSERT INTO preparations (preparation_id, digest) VALUES (?, ?)",
                (preparation["preparation_id"], store.put(preparation)))
    values = [preparation]
    if link is not None and asked["declared_operation"]["name"] == SESSION_START:
        values.append({"kind": "session_routing", "schema": 1,
                       "session": {"host": link["host"],
                                   "profile_id": request["actor"]["profile_id"]},
                       "delivery": {"state": "selected_only"}, "always_surface": "unchanged",
                       "native_files": "preserved", "routed_at": journal.now(call)})
    return journal.answered(call, "previewed", values, gaps=gaps,
                            local_effect="private_state_written")
