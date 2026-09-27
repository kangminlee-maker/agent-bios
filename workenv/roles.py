"""What reaches a session (C04): activating a session with one preparation.

`session.routing.activate` activates the requester's own session on its profile (a profile
other than the actor's is `request_mismatch`) with one preparation composed here
(`ref_unavailable` otherwise). A preparation composed for a link is prepared for the host
session that link names, so a session on another host is `recipient_mismatch`. Activation is
explicit: composing a start records the session as selected only, and only this operation
activates it. A refusal is recovered by a new request.

  - **The claims it rests on.** A preparation records the checkout it was composed in and the
    bodies it names. Where the working bytes it claimed no longer read the same, or a
    repository-authored unit's document in the bound checkout is no longer the body the
    preparation names, what the preparation said is no longer true there, and activation is
    refused `working_bytes_moved`. Composing again reads the checkout as it is now.
  - **What it delivers.** The preparation's Instructions units, projected through this owner as
    one `role_projection` for the executor view entered at session start: every unit named with
    its layer and standing, shadowed and disabled ones included. The bytes of each winning or
    layered unit's body are returned beside it, as `source_member`, so the session receives the
    text each `body_digest` names. A preparation with no Instructions unit projects nothing.
  - **The usage contract.** Every activated routing carries the short memory usage contract this
    runtime writes and a pointer to the guide behind it, by path and by the digest of the bytes
    this installation holds, whether or not anything else is delivered.
  - **What it leaves alone.** The always surface is unchanged and native instruction files are
    preserved: activation writes neither.

Activation is committed with a receipt. Where the preparation names a link, it is recorded as
what the preparation's recipient, the host session that link names, received. A preparation
composed for no link names no recipient, and the owner makes none up, so its activation is
observed for nobody.
"""
from __future__ import annotations

import hashlib
import pathlib

from workenv import delivery, journal, preparation, storage
from workenv.contracts import c01, c02, c03, c07, canonical
from workenv.sources import checkouts, homes

GUIDES = pathlib.Path(__file__).with_name("guides")
GUIDE = "guides/memory-use.md"
USAGE = ("Decision memory is read, never applied on your behalf. When an actual use would rely on "
         "incompatible current choices, ask the person. The procedure is in the guide this "
         "points at.")
ENTRANCE = {"name": "session_start", "root_origin": "owner"}
EXECUTOR = "executor"
INSTRUCTIONS = preparation.INSTRUCTIONS
AUTHORED = "repository_authored"


def refused(call, code: str, pointer: str | None = None) -> dict:
    gap = {"code": code} if pointer is None else {"code": code, "pointer": pointer}
    return journal.answered(call, "refused", gaps=[gap], recovery=["new_governed_request"])


def usage_contract() -> dict:
    data = (GUIDES / pathlib.Path(GUIDE).name).read_bytes()
    return {"text": USAGE, "guide": {"path": GUIDE, "digest": hashlib.sha256(data).hexdigest()}}


def moved(store: storage.Store, prepared: dict) -> bool:
    """Whether what the preparation said about the checkout is no longer true there."""
    claimed = prepared["observed"].get("working_bytes_digest")
    if claimed is not None:
        now, _ = preparation.observed(store)
        if now.get("working_bytes_digest") != claimed:
            return True
    for unit in prepared["units"]:
        # An authored source was admitted from its bound checkout, whose snapshot holds every
        # member: its units always name a body, and its repository always names a checkout.
        source = homes.source_of(store, unit["source_id"])
        if source["home_mode"] != AUTHORED:
            continue
        where = source["home"]["home"] if source["home"] else source["scope"]
        checkout = pathlib.Path(store.read("SELECT checkout FROM repositories WHERE "
                                           "repository_id = ?", (where["repository_id"],))[0][0])
        if not (checkout / unit["member"]).is_file() or hashlib.sha256(
                checkouts.read(checkout, unit["member"])).hexdigest() != unit["body_digest"]:
            return True
    return False


def projection(call, prepared: dict) -> tuple[dict | None, list[bytes]]:
    """The preparation's Instructions units as one projection, and the bytes it delivers."""
    units = [unit for unit in prepared["units"] if unit["role"] == INSTRUCTIONS]
    if not units:
        return None, []
    plan = {"kind": "projection_plan", "schema": 1,
            "source_pins": [{"source_id": unit["source_id"],
                             "revision_digest": unit["revision_digest"]} for unit in units],
            "role": INSTRUCTIONS, "recipient_view": EXECUTOR, "entrance": ENTRANCE,
            "order": prepared["order"]}
    projected, members = [], []
    for unit in units:
        value = {field: unit[field] for field in ("unit_id", "source_id", "revision_digest",
                                                   "layer", "standing", "body_digest",
                                                   "shadowed_by", "concern") if field in unit}
        projected.append({**value, "source_role": INSTRUCTIONS})
        if unit["standing"] in delivery.DELIVERED_STANDINGS and "body_digest" in unit:
            members.append((storage.bundle(call.state, unit["revision_digest"]) / storage.MEMBERS
                            / unit["member"]).read_bytes())
    gaps = [gap for gap in prepared["material_gaps"]
            if gap.get("pointer", "").startswith("/units/")
            and prepared["units"][int(gap["pointer"].split("/")[2])] in units]
    return {"kind": "role_projection", "schema": 1, "projection_id": journal.mint("prj"),
            "plan_digest": canonical.digest_of(plan), "role": INSTRUCTIONS,
            "recipient_view": EXECUTOR, "units": projected, "material_gaps": gaps,
            "prepared_at": journal.now(call)}, members


def session_routing_activate(call) -> dict:
    store = storage.of(call.state)
    activation = journal.payload(call)
    profile = call.request["target"]["resource_id"]
    if profile != call.request["actor"]["profile_id"] or \
            activation["session"]["profile_id"] != profile:
        return refused(call, c03.REQUEST_MISMATCH, "/target/resource_id")
    prepared = delivery.preparation_by_digest(store, activation["preparation_digest"])
    if prepared is None:
        return refused(call, c01.REF_UNAVAILABLE, "/preparation_digest")
    recipient = prepared["recipient"].get("recipient_digest")
    if recipient is not None and store.get(recipient)["host"] != activation["session"]["host"]:
        return refused(call, c02.RECIPIENT_MISMATCH, "/session/host")
    if moved(store, prepared):
        return refused(call, c07.WORKING_BYTES_MOVED)
    projected, members = projection(call, prepared)
    projections = [] if projected is None else [projected]
    routing = {"kind": "session_routing", "schema": 1, "session": activation["session"],
               "delivery": {"state": "activated",
                            "projections": [store.put(value) for value in projections],
                            "memory_usage": usage_contract()},
               "always_surface": "unchanged", "native_files": "preserved",
               "routed_at": journal.now(call)}
    if recipient is not None:
        delivery.record(call, {"preparation": prepared["preparation_id"], "recipient": recipient,
                               "recipient_kind": delivery.HOST_SESSION,
                               "saw": delivery.ACTIVATED, "record": store.put(routing)})
    return journal.committed(call, [routing, *projections, *members])
