"""C12 Client and provider capabilities: the gaps its operations answer with.

Record kinds: `capability_profile`, `capability_probe`, `route_outcome`,
`route_offer`, `route_selection`, `surface_script`, `surface_trace`, `validation_request`,
`validation_run`.

Read, question, user event, resume, a provider callback and a validator are qualified one
at a time, against the installed client
and the wire version it actually negotiated. A capability is qualified only by naming the probe
that qualified it, so a published specification, a registered tool name or a product's reputation
cannot stand in for one. A probe keeps what the client declared apart from what it did, because
a client that offers a capability and then refuses it is the case worth seeing. A probe
against a fixture names it, so a mocked provider or key qualifies nothing; that a profile
rests only on probes that ran for real relates the profile to its probes, which a schema
cannot state, so the runtime owner keeps it and P01's cases check it.

A run is real or it names its fixture. A real run has nowhere to put a fixture digest, so a
fixture standing in for a real result cannot be written down; an unsupported route says so with
its reason instead of returning an empty success.

The client is driven the way a person drives it. A `surface_script` is keys, typed text,
paste, resize and locale changes from one entrance; a `surface_trace` is what each input
left on the screen — every element by role, label, marks, focus, selection and state,
where navigation stood, what it dispatched, and which owner operations it called and
what each read, so a task-specific query during entry is seen. Focus,
a suggested default and a selection are three facts, and colour has no field. A trace is
state and geometry: it establishes no comprehension and no input-method composition.

An offered route that acts on material names the collection position it targets and
whether that is the original or the effective view.

Validation is pinned: exact targets, lenses by digest, the package the questions belong
to. A run is clean or has findings only over checks that all ran; anything else is
unverified. That a run covers every pinned target and lens relates it to its request,
which the runtime owner keeps and P01's cases check.
"""
CONTRACT = "C12"
RECORD_KINDS = ("capability_profile", "capability_probe", "route_outcome",
                "route_offer", "route_selection", "surface_script", "surface_trace",
                "validation_request", "validation_run")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name.
OPERATIONS = {
    "capability.probe": {"takes": ("capability_probe",),
                         "returns": ("capability_probe", "capability_profile")},
    "route.offer": {"takes": ("route_offer",), "returns": ("route_offer",)},
    "route.select": {"takes": ("route_selection",), "returns": ("route_outcome",)},
    "surface.drive": {"takes": ("surface_script",), "returns": ("surface_trace",)},
    "validation.run": {"takes": ("validation_request",), "returns": ("validation_run",)},
}

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "qualified_only_by_a_real_probe": "every capability a profile marks qualified names a "
                                      "probe of that capability on that client and wire "
                                      "that ran for real",
    "validation_covers_its_request": "a clean run or a run with findings checks every "
                                     "target and lens its request pinned, and no check "
                                     "or finding names another",
}

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
