"""C12 Client and provider capabilities: the gaps its operations answer with.

Record kinds: `capability_profile`, `capability_probe`, `route_outcome`,
`route_offer`, `route_selection`.

Read, question, user event and resume are qualified one at a time, against the installed client
and the wire version it actually negotiated. A capability is qualified only by naming the probe
that qualified it, so a published specification, a registered tool name or a product's reputation
cannot stand in for one. A probe keeps what the client declared apart from what it did, because
a client that offers a capability and then refuses it is the case worth seeing.

A run is real or it names its fixture. A real run has nowhere to put a fixture digest, so a
fixture standing in for a real result cannot be written down; an unsupported route says so with
its reason instead of returning an empty success.
"""
CONTRACT = "C12"
RECORD_KINDS = ("capability_profile", "capability_probe", "route_outcome",
                "route_offer", "route_selection")
IN_RESULTS = True

CAPABILITY_NOT_QUALIFIED = "capability_not_qualified"
FIXTURE_RESULT_IN_REAL_MODE = "fixture_result_in_real_mode"
PROTOCOL_CLAIM_ONLY = "protocol_claim_only"
LOCAL_ORIGIN_IS_NOT_AUTHORITY = "local_origin_is_not_authority"
HIDDEN_CONFIRMATION_REFUSED = "hidden_confirmation_refused"
NAVIGATION_CHANGED_STATE = "navigation_changed_state"
ROUTE_UNSUPPORTED = "route_unsupported"
WIRE_VERSION_UNSUPPORTED = "wire_version_unsupported"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    CAPABILITY_NOT_QUALIFIED: "a capability no probe has qualified on this installed client",
    FIXTURE_RESULT_IN_REAL_MODE: "a fixture result offered as a real run",
    PROTOCOL_CLAIM_ONLY: "support claimed from a specification or a registered name rather than "
                         "from what this installation did",
    LOCAL_ORIGIN_IS_NOT_AUTHORITY: "a request trusted because it came from this machine",
    HIDDEN_CONFIRMATION_REFUSED: "a confirmation the person was never shown",
    NAVIGATION_CHANGED_STATE: "a navigation or metadata read that would have changed state",
    ROUTE_UNSUPPORTED: "an operation no qualified route on this client can carry",
    WIRE_VERSION_UNSUPPORTED: "a negotiated protocol version this client does not speak",
}
