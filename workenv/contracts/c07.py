"""C07 Preparation and composition: the gaps its operations answer with.

Record kinds: `preparation_request`, `preparation`, `action_assessment`, `delivery_observation`,
`environment_edition`, `environment_adoption`.

Three questions are asked and answered apart. What this is composed from is the preparation;
whether this actor may act with it is the assessment; and what the task needs is assessed only
when a task was actually requested, so a session that starts without one reads `not_requested`
rather than satisfied. Composing an environment grants nothing, which is why no field of a
preparation carries a right.

Four facts about one body are also kept apart: selected, prepared, requested for delivery and
observed as delivered. A preparation proves assembly. A parent session's receipt proves nothing
about a child, and a replica holding the bytes is not a recipient that received them.

The checkout's bytes are recorded as they were, because the claims rest on them: bytes that
move afterwards invalidate those claims rather than being assumed unchanged.

An environment edition is what `environment.publish` publishes and `environment.adopt` adopts:
exact Instructions and knowledge revisions, a memory policy rather than memory records, the
components and host capabilities it needs, and exact parents with the explicit changes made to
them. A parent's newer edition is a candidate, never inherited by following its name. What an
adoption establishes is an `environment_adoption`: one exact edition in one scope.
"""
CONTRACT = "C07"
RECORD_KINDS = ("preparation_request", "preparation", "action_assessment",
                "delivery_observation", "environment_edition",
                "environment_adoption")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name.
OPERATIONS = {
    "preparation.compose": {"takes": ("preparation_request",), "returns": ("preparation",)},
    "preparation.assess": {"takes": ("operation_request",), "returns": ("action_assessment",)},
    "delivery.observe": {"takes": (), "returns": ("delivery_observation",)},
    "environment.publish": {"takes": ("environment_edition",), "returns": ("environment_edition",)},
    "environment.adopt": {"takes": (), "returns": ("environment_adoption",)},
}

SELECTION_UNRESOLVED = "selection_unresolved"
WORKING_BYTES_MOVED = "working_bytes_moved"
ISOLATION_UNPROVEN = "isolation_unproven"
DELIVERY_UNOBSERVED = "delivery_unobserved"
RENDERING_NOT_RETAINED = "rendering_not_retained"
ADOPTION_EVIDENCE_MISSING = "adoption_evidence_missing"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    SELECTION_UNRESOLVED: "a selected source that is unknown, denied or damaged; this is not "
                          "absence, and no lower layer silently satisfies it",
    WORKING_BYTES_MOVED: "observed bytes that changed after the claims resting on them were made",
    ISOLATION_UNPROVEN: "a context whose isolation is required and not evidenced; a new "
                        "conversation alone does not prove it",
    DELIVERY_UNOBSERVED: "a delivery that was requested and not observed",
    RENDERING_NOT_RETAINED: "an exact past rendering whose bytes were not retained; a digest "
                            "does not reconstruct them",
    ADOPTION_EVIDENCE_MISSING: "an adopted environment used without the adoption evidence that "
                               "would make it one",
}
