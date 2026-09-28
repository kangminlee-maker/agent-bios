"""The owner's side of an entrance: the routes it offers, and the one a person selects (C12).

An entrance knows no rule of its own. It shows what the owner holds and hands on what the person
chose, and these two operations are where the owner keeps both:

  - `route.offer` keeps what one entrance offered, route by route, with the instant it did. A
    route whose support says it is qualified names the probe that qualified it, and the owner
    holds the entrance to that: the probe must be held here, of the capability the route's action
    needs, among the latest probes of it on its client, and those ran for real through the wire
    the route to that recipient takes now and worked (`workenv.hosts.qualified`). Anything else is
    refused `capability_not_qualified`, at the route's support. A route that says it is not
    qualified is kept as stated: it widens nothing.
  - `route.select` records one selection against an offer the owner holds (`ref_unavailable`
    otherwise), of a route that offer made (`request_mismatch` otherwise). The selection names
    the request the start produced, and the owner answers for that request: it must be held
    here (`ref_unavailable`), of an operation of the route's action (`request_mismatch`), and
    answered with a record, whose digest the outcome names; one still pending is
    `outcome_unknown`, settled by querying it. A route that is not qualified now, whatever its
    offer said, is refused `capability_not_qualified` and never run: the outcome says it is
    unsupported because the capability is absent, on the client the offer's qualified routes
    were probed on. An offer whose qualified routes name no one client names no client that
    could have carried it, so its refusal returns no outcome.

What an action needs is the table `NEEDS`. Starting work in an environment (`use`) needs a new
session to be handed it, which V1 does at launch (`new_delivery`); deciding (`decide`) needs a
question, which no V1 route carries. An action the table does not name needs a capability
nothing here qualifies, so no route of it is qualified. A later stage adds the capabilities it
qualifies.
"""
from __future__ import annotations

from workenv import hosts, journal, storage
from workenv.contracts import c01, c03, c12

# The C12 capability each action a route supports needs qualified.
NEEDS = {"use": "new_delivery", "decide": "question"}
OFFER, OUTCOME, PROBE = "route_offer", "route_outcome", "capability_probe"
# The recipient each delivery capability hands its context to.
RECIPIENT = {capability: recipient for recipient, capability in hosts.CAPABILITY.items()}


def refused(call, code: str, pointer: str | None = None, values=(), recovery=()) -> dict:
    gap = {"code": code} if pointer is None else {"code": code, "pointer": pointer}
    return journal.answered(call, "refused", values, gaps=[gap], recovery=recovery)


def held(store: storage.Store, digest: str | None, kind: str) -> dict | None:
    """The record of this kind held here under the digest, or None."""
    found = store.get(digest) if isinstance(digest, str) else None
    return found if isinstance(found, dict) and found.get("kind") == kind else None


def qualifies(store: storage.Store, probe: dict | None, capability: str | None) -> bool:
    """Whether a probe held here qualifies the capability on its client now."""
    recipient = RECIPIENT.get(capability)
    return probe is not None and recipient is not None and \
        probe in hosts.latest_probes(store, probe["client"], capability) and \
        hosts.qualified(store, probe["client"], recipient)


def route_offer(call) -> dict:
    """C12 `route.offer`, as the module docstring states."""
    store = storage.of(call.state)
    offer = journal.payload(call)
    for index, route in enumerate(offer["offered"]):
        support = route["support"]
        if support["qualified"] == "yes" and not qualifies(
                store, held(store, support["probe_digest"], PROBE),
                NEEDS.get(route["supported_action"])):
            return refused(call, c12.CAPABILITY_NOT_QUALIFIED, f"/offered/{index}/support",
                           recovery=["new_governed_request"])
    return journal.committed(call, [{**offer, "offered_at": journal.now(call)}])


def offered_client(store: storage.Store, offer: dict) -> dict | None:
    """The one client the offer's qualified routes were probed on, or None."""
    clients = []
    for route in offer["offered"]:
        probe = held(store, route["support"].get("probe_digest"), PROBE)
        if probe is not None and probe["client"] not in clients:
            clients.append(probe["client"])
    return clients[0] if len(clients) == 1 else None


def outcome(selection: dict, client: dict, capability: str, result: dict, at: str,
            gaps=()) -> dict:
    return {"kind": OUTCOME, "schema": 1, "for_request_id": selection["request_id"],
            "client": client, "capability": capability, "mode": {"runs": "real"},
            "result": result, "material_gaps": list(gaps), "at": at}


def route_select(call) -> dict:
    """C12 `route.select`, as the module docstring states."""
    store = storage.of(call.state)
    selection = journal.payload(call)
    offer = held(store, selection["offer_digest"], OFFER)
    if offer is None:
        return refused(call, c01.REF_UNAVAILABLE, "/offer_digest")
    route = next((route for route in offer["offered"]
                  if route["route_id"] == selection["selected"]), None)
    if route is None:
        return refused(call, c03.REQUEST_MISMATCH, "/selected")
    at = journal.now(call)
    capability = NEEDS.get(route["supported_action"])
    probe = held(store, route["support"].get("probe_digest"), PROBE)
    if not qualifies(store, probe, capability):
        client = probe["client"] if probe is not None else offered_client(store, offer)
        if client is None or capability is None:
            return refused(call, c12.CAPABILITY_NOT_QUALIFIED)
        gap = {"code": c12.CAPABILITY_NOT_QUALIFIED}
        unsupported = outcome(selection, client, capability,
                              {"got": "unsupported", "because": "capability_absent"}, at, [gap])
        return journal.answered(call, "refused", [unsupported], gaps=[gap])
    started = journal.held(store, selection["request_id"])
    if started is None:
        return refused(call, c01.REF_UNAVAILABLE, "/request_id")
    if journal.OPERATIONS[started["operation"]]["action"] != route["supported_action"]:
        return refused(call, c03.REQUEST_MISMATCH, "/request_id")
    if started["stage"] in journal.PENDING:
        return refused(call, c03.OUTCOME_UNKNOWN, "/request_id",
                       recovery=["query_same_request"])
    outputs = started["answer"]["result"]["outputs"]
    if not outputs:
        return refused(call, c01.REF_UNAVAILABLE, "/request_id")
    store.put({**selection, "selected_at": at})
    return journal.committed(call, [outcome(selection, probe["client"], capability,
                                            {"got": "result",
                                             "output_digest": outputs[0]["digest"]}, at)])
