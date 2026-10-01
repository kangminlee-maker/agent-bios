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
    name it in the needed unit's `needed_by`; a unit that does not win names nothing. A need no
    composed unit answers, by source and member, is `companion_unavailable` at the winning unit:
    its bytes rely on bytes this composition does not hold, and leaving the companion out of
    every selection does not make it any less needed (C07 `unit_binding`). Needs bind while the
    unit wins, so a needed unit that does not win names no needs of its own.
  - **Bodies.** A unit's body is its member's bytes in the pinned revision's bundle, the
    immutable snapshot every revision is read from, whoever authors it: a repository-authored
    source's working tree is what the checkout records, never a body. A unit states its body's
    digest only where the bundle holds the member's bytes. A winning unit, or a unit a winning
    unit needs, whose bytes the bundle does not hold is `role_body_unavailable`, and one whose
    bytes are other bytes is `object_digest_mismatch`, each at that unit; any other unit whose
    body is not held states none and gates nothing, as nothing depends on its bytes. A unit
    switched off is not read, unless a winning unit needs it: a need keeps it required even
    switched off (C07 `unit_binding`).
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

What each composed unit means for a start is read in one place, `Reading`, and every consumer
asks it: the activation, the projection, the start's environment, the hook, the observation, the
entry and `sources`. The entry and `sources` read a composition they run in memory
(`composed`), through the same `Composition` a preparation is composed with, so they show what a
start would compose rather than rebuilding it (design record
`2026-10-01T2134--3551ccb--v1-restructure-design.md`).
"""
from __future__ import annotations

import dataclasses
import functools
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
# The standings whose bodies a session is handed at its start.
DELIVERED_STANDINGS = ("winning", "layered")


def refused(call, code: str, pointer: str | None = None) -> dict:
    gap = {"code": code} if pointer is None else {"code": code, "pointer": pointer}
    return journal.answered(call, "refused", gaps=[gap], recovery=["new_governed_request"])


def held_collection(store: storage.Store, scope: dict, role: str) -> str | None:
    found = store.read("SELECT collection_id FROM collections WHERE scope = ? AND role = ?",
                       (journal.scope_key(scope), role))
    return found[0][0] if found else None


def revision_of(store: storage.Store, source_id: str,
                revision: str | None) -> tuple[dict, dict] | None:
    """A source this installation holds and the manifest of its revision, or None."""
    source = homes.source_of(store, source_id)
    if source is None or revision is None or not store.read(
            "SELECT 1 FROM revisions WHERE revision_digest = ? AND source_id = ?",
            (revision, source_id)):
        return None
    return source, store.get(revision)


def resolved(store: storage.Store, entry: dict,
             role: str) -> tuple[list[str], tuple[dict, dict] | None]:
    """What one collection entry resolves to here, the one reading of it: the gap codes it states
    at its position, and the source and manifest of the revision it pins where one is held.
    Composition composes from it, and the entry, `sources` and a session's environment show from
    it which selected source does not resolve."""
    held = homes.source_of(store, entry["source_id"])
    if held is not None and held["role"] != role:
        return [c04.ROLE_PROMOTION_REFUSED if role == INSTRUCTIONS
                else c07.SELECTION_UNRESOLVED], None
    if role == MEMORY:
        if entry["switch"] == "on" and journal.head_of(store, entry["source_id"]) is None:
            return [c07.SELECTION_UNRESOLVED], None
        return [], None
    found = revision_of(store, entry["source_id"], entry["pin"].get("revision_digest"))
    if found is None:
        return [c07.SELECTION_UNRESOLVED], None
    members = {member["path"] for member in found[1]["members"]}
    declared = entry.get("units") or [{"member": path} for path in members]
    return [c07.SELECTION_UNRESOLVED for unit in declared if unit["member"] not in members], found


def selected(manifest: dict, declared: list[dict] | None = None) -> list[str]:
    """The members a pin selects that its revision holds: each unit it declares, or else every
    member of the revision, as composition reads an entry."""
    members = [member["path"] for member in manifest["members"]]
    return [unit["member"] for unit in declared if unit["member"] in members] if declared \
        else members


def carries(unit: dict) -> bool:
    """Whether a session is handed this unit's body at its start: an Instructions unit of a
    delivered standing that names a body. It reads a prepared unit and a projected one alike, so
    the bodies a start hands over, those an activation returns and those an observation lists as
    arrived are one set."""
    return unit.get("role", unit.get("source_role")) == INSTRUCTIONS and \
        unit["standing"] in DELIVERED_STANDINGS and "body_digest" in unit


@dataclasses.dataclass(frozen=True)
class Reading:
    """What each unit of one composition means for a start: the one reading the activation, the
    projection, the start's environment, the hook, the observation, the entry and `sources` ask.

    `missing` names, by unit index, the needs no composed unit answers; a composition in memory
    knows them, and a stored preparation states only their gap (`companion_unavailable`)."""
    units: list[dict]
    gaps: list[dict]
    missing: dict = dataclasses.field(default_factory=dict)

    def at(self, index: int) -> list[dict]:
        """The gaps stated at one unit."""
        return [gap for gap in self.gaps if gap.get("pointer") == f"/units/{index}"]

    def delivered(self, unit: dict) -> bool:
        """An Instructions unit whose standing hands its body to a session, held or not."""
        return unit["role"] == INSTRUCTIONS and unit["standing"] in DELIVERED_STANDINGS

    @functools.cached_property
    def winners(self) -> set[str]:
        """The Instructions units that win with `startup: required`."""
        return {unit["unit_id"] for unit in self.units
                if unit["role"] == INSTRUCTIONS and unit["standing"] == "winning"
                and unit.get("startup") == "required"}

    def required(self, unit: dict) -> bool:
        """Whether the unit must resolve before a session starts: an Instructions unit winning
        with `startup: required`, or a unit such a unit needs, whatever its own standing (C07
        `unit_binding`)."""
        return unit["unit_id"] in self.winners or bool(self.winners &
                                                       set(unit.get("needed_by", [])))

    def claims(self, unit: dict) -> bool:
        """Whether the unit names a body the start rests on: one it delivers, or one a winning
        unit needs. Only such a unit is held to its document in the checkout."""
        return "body_digest" in unit and (self.delivered(unit) or "needed_by" in unit)

    def carried(self) -> list[dict]:
        """The units whose bodies a session is handed at its start, in order (`carries`)."""
        return [unit for unit in self.units if carries(unit)]

    def unheld(self) -> list[dict]:
        """The units a session would be handed whose bodies are not held and that state no gap:
        a layered unit, which gates nothing, named so its absence does not read as nothing
        selected (`D-20260930-38bbad`)."""
        return [unit for index, unit in enumerate(self.units)
                if self.delivered(unit) and "body_digest" not in unit and not self.at(index)]

    def unmet(self) -> dict | None:
        """The first gap stated at a unit that must resolve before a session starts, or None."""
        for gap in self.gaps:
            parts = gap.get("pointer", "").split("/")
            if len(parts) == 3 and parts[1] == "units" and \
                    self.required(self.units[int(parts[2])]):
                return gap
        return None


def reading(prepared: dict) -> Reading:
    """The reading of a stored preparation."""
    return Reading(prepared["units"], prepared["material_gaps"])


def declared_needs(store: storage.Store, prepared: dict, unit: dict) -> list[dict]:
    """The needs the collection that contributed a unit declares for it, read from the
    collections the preparation names at their heads; none for a unit no collection declares."""
    found = []
    for held in prepared["collections"]:
        collection = store.get(held["head_digest"])
        for entry in collection["entries"] if isinstance(collection, dict) else []:
            for binding in entry.get("units") or []:
                if entry["source_id"] == unit["source_id"] and \
                        binding["member"] == unit["member"]:
                    found += [need for need in binding.get("needs", []) if need not in found]
    return found


def unanswered(prepared: dict, needs: list[dict]) -> list[dict]:
    """Of a unit's needs, those no unit of the preparation answers."""
    held = {(unit["source_id"], unit.get("member")) for unit in prepared["units"]}
    return [need for need in needs if (need["source_id"], need["member"]) not in held]


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


def held(state, revision: str, path: str, digest: str) -> tuple[bytes | None, str | None]:
    """(the bytes, None) where the revision's bundle holds the member at `path` as the bytes
    `digest` names, else (None, why). Composing a unit and activating it read a body through
    this, so what a preparation names and what an activation returns are the same bytes."""
    found = storage.bundle(state, revision) / storage.MEMBERS / path
    if not found.is_file():
        return None, c04.ROLE_BODY_UNAVAILABLE
    data = found.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        return None, c03.OBJECT_DIGEST_MISMATCH
    return data, None


def body_of(state, revision: str, member: dict) -> tuple[str | None, str | None]:
    """(the member's digest, None) where the revision's bundle holds its bytes, else (None, why)."""
    data, why = held(state, revision, member["path"], member["digest"])
    return (None, why) if data is None else (member["digest"], None)


class Composition:
    """One preparation being composed: what it read, in the order it read it. It reads and
    writes no position; `preparation_compose` stores what it composed, and the entry and
    `sources` read one composed in memory (`composed`)."""

    def __init__(self, state, store: storage.Store, order: list[dict]):
        self.state, self.store, self.order = pathlib.Path(state), store, order
        self.collections: list[dict] = []
        self.units: list[dict] = []
        self.frontiers: list[dict] = []
        self.gaps: list[dict] = []
        # Each entry that states a gap at its collection: (the collection's pointer, its source,
        # the codes), so what does not resolve is named where it was selected.
        self.unresolved: list[tuple[str, str, list[str]]] = []

    @property
    def reading(self) -> Reading:
        return Reading([held["unit"] for held in self.units], self.gaps,
                       {index: held["missing"] for index, held in enumerate(self.units)
                        if held.get("missing")})

    def unresolved(self, where: str) -> None:
        self.gaps.append({"code": c07.SELECTION_UNRESOLVED, "pointer": where})

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
        codes, found = resolved(self.store, entry, role)
        self.gaps += [{"code": code, "pointer": where} for code in codes]
        if codes:
            self.unresolved.append((where, entry["source_id"], codes))
        if role == MEMORY and not codes and entry["switch"] == "on":
            self.frontier(entry["source_id"], where)
        if found is None:
            return
        source, manifest = found
        members = {member["path"]: member for member in manifest["members"]}
        for unit in entry.get("units") or [{"member": path} for path in members]:
            if unit["member"] in members:
                self.unit(source, entry["pin"]["revision_digest"], members[unit["member"]],
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
                answering = [other for other in self.units
                             if (other["unit"]["source_id"], other["unit"]["member"]) ==
                             (need["source_id"], need["member"])]
                for other in answering:
                    other["unit"].setdefault("needed_by", []).append(held["unit"]["unit_id"])
                if not answering:
                    held.setdefault("missing", []).append(need)

    def bodies(self) -> None:
        for index, held in enumerate(self.units):
            unit = held["unit"]
            if held.get("unordered"):
                self.gaps.append({"code": c07.SAME_LAYER_UNORDERED, "pointer": f"/units/{index}"})
            if unit["standing"] != "disabled" or "needed_by" in unit:
                digest, why = body_of(self.state, unit["revision_digest"], held["member"])
                if digest is not None:
                    unit["body_digest"] = digest
                elif unit["standing"] == "winning" or "needed_by" in unit:
                    self.gaps.append({"code": why, "pointer": f"/units/{index}"})
            if held.get("missing"):
                self.gaps.append({"code": c04.COMPANION_UNAVAILABLE,
                                  "pointer": f"/units/{index}"})


def composed(state, store: storage.Store, scopes: list[dict],
             pins: list[dict] = ()) -> Composition:
    """A composition of these scopes in the default order with these pins, run in memory and
    written nowhere: what a start of that basis would compose. A pin of a revision not held here
    is left out, as the request that names it would be refused."""
    order = sorted(scopes, key=lambda scope: DEFAULT_ORDER.index(scope["layer"]))
    composition = Composition(state, store, order)
    found = [(pin, *held) for pin in pins
             if (held := revision_of(store, pin["source_id"], pin["revision_digest"]))]
    composition.compose(found)
    return composition


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
    composition = Composition(call.state, store, order)
    pins = []
    for index, pin in enumerate(basis["source_pins"]):
        found = revision_of(store, pin["source_id"], pin["revision_digest"])
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
