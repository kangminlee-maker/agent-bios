"""C12 Client and provider capabilities: the gaps its operations answer with.

Record kinds: `capability_profile`, `capability_probe`, `route_outcome`,
`route_offer`, `route_selection`, `surface_script`, `surface_trace`, `validation_request`,
`validation_run`, `host_configuration`.

Read, question, user event, resume, a provider callback and a validator are qualified one
at a time, against the installed client
and the wire version it actually negotiated. A capability is qualified only by naming the probe
that qualified it, so a published specification, a registered tool name or a product's reputation
cannot stand in for one. A probe keeps what the client declared apart from what it did, because
a client that offers a capability and then refuses it is the case worth seeing. A probe
against a fixture names it, so a mocked provider or key qualifies nothing; that a profile
rests only on probes that ran for real relates the profile to its probes, which a schema
cannot state, so the runtime owner keeps it.

A host is qualified under the configuration it runs, so what of that configuration can act for a
person is measured and kept: `host_configuration` lists every hook the host would run, on which
event, by the digest of its handler, and whether it is enabled, and an empty list is a host with
no hook. A probe returns the configuration it ran under, and C11 names the one a reply was
classified against.

A run is real or it names its fixture. A real run has nowhere to put a fixture digest, so a
fixture standing in for a real result cannot be written down; an unsupported route says so with
its reason instead of returning an empty success.

The client is driven the way a person drives it. A `surface_script` is keys, typed text,
paste, resize and locale changes from one entrance; a `surface_trace` is what each input
left on the screen — every element by role, label, marks, focus, selection and state,
where navigation stood, what it dispatched, and which owner operations it called and
what each read, so a task-specific query during entry is seen. Focus,
a suggested default and a selection are three facts, and colour has no field. A trace is
state and geometry: it establishes no comprehension and no input-method composition. An element
refers to a whole record by digest, to one part of a record by the id the record gives it — a
node or relation of a knowledge model — or to a source by its id; something shown against a
basis that has moved is `stale`, and a Team whose lifecycle ended is `closed`.

An offered route that acts on material names the collection position it targets and
whether that is the original or the effective view. A selection that opens a read-only view
expects `view_opened`, which writes nothing.

Validation is pinned: exact targets, lenses by digest, and the package the questions belong
to by the `source_manifest` of its source revision. A run is clean or has findings only over
checks that all ran; anything else is unverified. That a run covers every pinned target and
lens relates it to its request, which the runtime owner keeps.
"""
CONTRACT = "C12"
RECORD_KINDS = ("capability_profile", "capability_probe", "route_outcome",
                "route_offer", "route_selection", "surface_script", "surface_trace",
                "validation_request", "validation_run", "host_configuration")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. `effect`, `action` and `targets`
# are what every request for it states: its effect class, the one grant action it needs and
# the id prefixes its target may carry. The union across the contract modules is the closed
# list a request may name.
OPERATIONS = {
    "capability.probe": {"takes": ("capability_probe",),
                         "returns": ("capability_probe", "capability_profile",
                                     "host_configuration"),
                         "effect": "owner_commit", "action": "local_profile", "targets": ("prf",)},
    "route.offer": {"takes": ("route_offer",), "returns": ("route_offer",),
                    "effect": "owner_commit", "action": "read", "targets": ("prf",)},
    "route.select": {"takes": ("route_selection",), "returns": ("route_outcome",),
                     "effect": "owner_commit", "action": "read", "targets": ("prf",)},
    "surface.drive": {"takes": ("surface_script",), "returns": ("surface_trace",),
                      "effect": "pure_preview", "action": "read", "targets": ("prf",)},
    "validation.run": {"takes": ("validation_request",), "returns": ("validation_run",),
                       "effect": "owner_commit", "action": "review", "targets": ("rep", "prn")},
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
