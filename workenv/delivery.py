"""Recipients and delivery (C11, C07): links, what an attempt delivered, and what reached each of
a preparation's recipients.

This module knows no host. What a host can reach is its adapter's and its probes'
(`workenv.hosts`), and the owner reads nothing else about it: whether a route reaches the
recipient an attempt names on the host installed here.

`recipient.link.open` stores the link its payload states for the requester alone (a principal
other than the actor's is `request_mismatch`), with the id and the time the runtime owns. Its
destination is the digest of the session id a host adapter reported, never one the runtime
makes up.

`recipient.delivery.attempt` records one delivery of a preparation's bodies to one recipient on
one link. The bodies travel beside a projection or an activation, never in the attempt: an
adapter that handed them to its host records here which it handed over. The owner checks the
attempt against what it holds, in this order:

  - **The link.** A link this installation did not open is `recipient_link_unknown`, and the
    attempt is answered with the channel it did not have (`no_channel`). It names no recipient
    this installation knows, so no observation records it.
  - **The preparation.** One not composed here is `ref_unavailable`, and one composed for another
    recipient is `recipient_mismatch`: the preparation names its recipient, and bodies go to no
    other.
  - **The bodies.** An attempt names only bodies its preparation composed and this installation
    holds. A rehydrated recipient offered anything else, a bare hash in place of bytes, is
    `rehydration_needs_bodies` and the bodies are `lost`; any other recipient named a body the
    preparation did not compose is `request_mismatch` at `/requested/bodies`.
  - **The route.** Where the link's host has no route to the recipient that a probe on the host
    installed here qualified, the attempt is answered `supported: false` with no channel:
    `child_route_unsupported` for a child, and `route_unsupported` for any other. Nothing stands
    in for a missing route. A link this installation does not hold names no host, so `supported`
    there is the runtime's own, which reaches every recipient.

A refused attempt delivers nothing. One answered with the attempt it refused keeps that attempt
privately (`private_state_written`); where it named a link held here, it is also kept as a
delivery requested of that recipient and not seen. Otherwise it is committed as `received`, for
exactly the bodies it names. `received` states that the adapter reported, in a
request sealed by the person's device key, handing exactly those bodies to its host for that
recipient; it does not state that a model read or followed them, which is observed use, a third
fact. The evidence is that sealed request, and `evidence_digest` is its digest. A new, current or
rehydrated recipient is the host session the link names, named by the link's digest; a child is
its own recipient, named by its delivery on the link, since a parent's receipt says nothing about
a child.

`delivery.observe` answers, for one preparation, one observation per recipient a delivery of it
was requested of, in the order each was first requested. A recipient anything reached names
what it saw (`delivered`, or `activated` where the session was activated with it), the evidence,
and the inventory of the units whose bodies arrived, from those deliveries alone: an attempt
refused later changes none of it. A recipient nothing reached is `not_observed` with
`delivery_unobserved`, and a child is named only by what reached it. It reads what the attempts
and activations recorded and keeps each observation it answers, privately
(`private_state_written`); observing again gives the same observation and writes nothing, and a
preparation composed later changes none of it. A preparation no delivery was requested of
answers none.
"""
from __future__ import annotations

from workenv import hosts, journal, storage
from workenv.contracts import c01, c02, c03, c06, c07, c11, c12, canonical

HOST_SESSION, CHILD_SESSION = "host_session", "child_session"
# What a recorded delivery saw: its bodies arrived, the session was activated with them, or it
# was requested of the recipient and not seen.
DELIVERED, ACTIVATED, UNSEEN = "delivered", "activated", "unseen"
KEPT = "private_state_written"
# The standings whose bodies a projection delivers.
DELIVERED_STANDINGS = ("winning", "layered")


def refused(call, code: str, pointer: str | None = None) -> dict:
    gap = {"code": code} if pointer is None else {"code": code, "pointer": pointer}
    return journal.answered(call, "refused", gaps=[gap])


def link_of(store: storage.Store, link_id: str) -> tuple[str, dict] | None:
    found = store.read("SELECT digest FROM links WHERE link_id = ?", (link_id,))
    return (found[0][0], store.get(found[0][0])) if found else None


def preparation_by_digest(store: storage.Store, digest: str) -> dict | None:
    found = store.read("SELECT preparation_id FROM preparations WHERE digest = ?", (digest,))
    return store.get(digest) if found else None


def preparation_by_id(store: storage.Store, preparation_id: str) -> dict | None:
    found = store.read("SELECT digest FROM preparations WHERE preparation_id = ?",
                       (preparation_id,))
    return store.get(found[0][0]) if found else None


def record(call, row: dict) -> None:
    """Keep one delivery requested of a recipient, with what it saw."""
    storage.of(call.state).write(
        "INSERT INTO deliveries (preparation, recipient, recipient_kind, saw, record, evidence, "
        "at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (row["preparation"], row["recipient"], row["recipient_kind"], row["saw"], row["record"],
         canonical.digest_of(call.request), journal.now(call)))


# Links.

def recipient_link_open(call) -> dict:
    store = storage.of(call.state)
    link = journal.payload(call)
    principal = call.request["target"]["resource_id"]
    if principal != call.request["actor"]["principal_id"] or link["principal_id"] != principal:
        return refused(call, c03.REQUEST_MISMATCH, "/target/resource_id")
    stored = {**link, "link_id": journal.mint("lnk"), "created_at": journal.now(call)}
    store.write("INSERT INTO links (link_id, digest) VALUES (?, ?)",
                (stored["link_id"], store.put(stored)))
    return journal.committed(call, [stored])


# Attempts.

def answered_attempt(attempt: dict, supported: bool, observed: dict, gaps: list[dict],
                     at: str) -> dict:
    return {**attempt, "supported": supported, "observed": observed, "material_gaps": gaps,
            "at": at}


def recipient_of(link_digest: str, attempt: dict) -> tuple[str, str]:
    """The recipient an attempt on a held link names, and which recipient it is."""
    if attempt["requested"]["recipient"] == "child":
        return CHILD_SESSION, canonical.digest_of({"link": link_digest,
                                                   "use_id": attempt["use_id"]})
    return HOST_SESSION, link_digest


def unseen(call, preparation: dict, link_digest: str, answer: dict) -> dict:
    """Keep a refused attempt on a held link as a delivery requested and not seen."""
    attempt = answer["returned"][0]
    kind, recipient = recipient_of(link_digest, attempt)
    record(call, {"preparation": preparation["preparation_id"], "recipient": recipient,
                  "recipient_kind": kind, "saw": UNSEEN,
                  "record": storage.of(call.state).put(attempt)})
    return answer


def recipient_delivery_attempt(call) -> dict:
    store = storage.of(call.state)
    attempt = journal.payload(call)
    link_id = call.request["target"]["resource_id"]
    if attempt["link_id"] != link_id:
        return refused(call, c03.REQUEST_MISMATCH, "/target/resource_id")
    requested = attempt["requested"]
    if requested["what"] != "body":
        raise journal.JournalError("delivering a question or a resume is not served yet")
    at = journal.now(call)
    found = link_of(store, link_id)
    if found is None:
        gaps = [{"code": c11.RECIPIENT_LINK_UNKNOWN}]
        return journal.answered(call, "refused", [answered_attempt(
            attempt, True, {"saw": "no_channel"}, gaps, at)], gaps=gaps, local_effect=KEPT)
    link_digest, link = found
    preparation = preparation_by_digest(store, requested["preparation_digest"])
    if preparation is None:
        return refused(call, c01.REF_UNAVAILABLE, "/requested/preparation_digest")
    if preparation["recipient"].get("recipient_digest") != link_digest:
        return refused(call, c02.RECIPIENT_MISMATCH)
    composed = {unit["body_digest"] for unit in preparation["units"] if "body_digest" in unit}
    if not set(requested["bodies"]) <= composed:
        if requested["recipient"] == "rehydrated":
            gaps = [{"code": c11.REHYDRATION_NEEDS_BODIES}]
            return unseen(call, preparation, link_digest, journal.answered(
                call, "refused", [answered_attempt(attempt, True, {"saw": "lost"}, gaps, at)],
                gaps=gaps, local_effect=KEPT))
        return refused(call, c03.REQUEST_MISMATCH, "/requested/bodies")
    if not hosts.supports(store, link["host"], requested["recipient"]):
        code = (c06.CHILD_ROUTE_UNSUPPORTED if requested["recipient"] == "child"
                else c12.ROUTE_UNSUPPORTED)
        gaps = [{"code": code}]
        return unseen(call, preparation, link_digest, journal.answered(
            call, "refused", [answered_attempt(attempt, False, {"saw": "no_channel"}, gaps, at)],
            gaps=gaps, local_effect=KEPT))
    stored = answered_attempt(attempt, True, {
        "saw": "received", "received": requested["bodies"],
        "evidence_digest": canonical.digest_of(call.request)}, [], at)
    kind, recipient = recipient_of(link_digest, attempt)
    record(call, {"preparation": preparation["preparation_id"], "recipient": recipient,
                  "recipient_kind": kind, "saw": DELIVERED, "record": store.put(stored)})
    return journal.committed(call, [stored])


# Observation.

def observations(store: storage.Store, preparation: dict) -> list[dict]:
    """What reached each recipient a delivery of one preparation was requested of, from what
    the owner recorded."""
    recorded = store.read("SELECT recipient, recipient_kind, saw, record, evidence, at FROM "
                          "deliveries WHERE preparation = ? ORDER BY position",
                          (preparation["preparation_id"],))
    grouped: dict[tuple[str, str], list[tuple]] = {}
    for recipient, kind, saw, kept, evidence, at in recorded:
        grouped.setdefault((kind, recipient), []).append((saw, kept, evidence, at))
    found = []
    for (kind, recipient), rows in grouped.items():
        held = [row for row in rows if row[0] != UNSEEN]
        if not held:
            requested = {"recipient_kind": kind}
            if kind == HOST_SESSION:
                requested["recipient_digest"] = recipient
            found.append({"kind": "delivery_observation", "schema": 1,
                          "preparation_id": preparation["preparation_id"],
                          "requested": requested, "observed": {"saw": "not_observed"},
                          "material_gaps": [{"code": c07.DELIVERY_UNOBSERVED}],
                          "recorded_at": rows[-1][3]})
            continue
        received: set[str] = set()
        for saw, kept, _, _ in held:
            value = store.get(kept)
            received |= set(value["observed"]["received"]) if saw == DELIVERED else {
                body for projection in value["delivery"]["projections"]
                for body in delivered_bodies(store.get(projection))}
        inventory = [{"unit_id": unit["unit_id"], "source_id": unit["source_id"],
                      "revision_digest": unit["revision_digest"],
                      "body_digest": unit["body_digest"]}
                     for unit in preparation["units"] if unit.get("body_digest") in received]
        found.append({
            "kind": "delivery_observation", "schema": 1,
            "preparation_id": preparation["preparation_id"],
            "requested": {"recipient_kind": kind, "recipient_digest": recipient},
            "observed": {"saw": ACTIVATED if any(row[0] == ACTIVATED for row in held)
                         else DELIVERED,
                         "at": held[0][3],
                         "evidence_digest": canonical.digest_of([row[2] for row in held]),
                         "inventory": inventory},
            "material_gaps": [], "recorded_at": held[-1][3]})
    return found


def delivered_bodies(projection: dict) -> list[str]:
    return [unit["body_digest"] for unit in projection["units"]
            if unit["standing"] in DELIVERED_STANDINGS and "body_digest" in unit]


def delivery_observe(call) -> dict:
    store = storage.of(call.state)
    preparation = preparation_by_id(store, call.request["target"]["resource_id"])
    if preparation is None:
        return refused(call, c01.REF_UNAVAILABLE, "/target/resource_id")
    found = observations(store, preparation)
    # The journal keeps what an answer returns, so an observation not kept yet is written now.
    fresh = any(store.get(canonical.digest_of(value)) is None for value in found)
    return journal.answered(call, "previewed", found, local_effect=KEPT if fresh else "none")
