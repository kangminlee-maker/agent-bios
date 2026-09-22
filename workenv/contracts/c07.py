"""C07 Preparation and composition: the gaps its operations answer with.

Record kinds: `preparation_request`, `preparation`, `action_assessment`, `delivery_observation`,
`environment_edition`, `environment_adoption`, `collection`.

Three questions are asked and answered apart. What this is composed from is the preparation;
whether this actor may act with it is the assessment; and what the task needs is assessed only
when a task was actually requested, so a session that starts without one reads `not_requested`
rather than satisfied. Composing an environment grants nothing, which is why no field of a
preparation carries a right.

Four facts about one body are also kept apart: selected, prepared, requested for delivery and
observed as delivered. A preparation proves assembly. A parent session's receipt proves nothing
about a child, and a replica holding the bytes is not a recipient that received them.

A preparation is stored whole and never changes, because later requests name it — an
activation, a delivery, an observation. Composing writes that private record and moves no head,
so its answer names no receipt and is not a pure preview. A preparation composed for a session
start — its `preparation_request` declares `session.routing.activate` and the sealed request
names the session's recipient link — also records that session as selected only: the answer
returns a `session_routing` (C04) in that state beside the preparation.

A `unit_id` names a unit of the one preparation that minted it; another preparation of the same
member mints its own, and a unit is followed across preparations by its source, member and
revision. A unit also names the `source_home` its source was composed under: a source's
conditions live on its home, so a home registered again with new conditions reaches the next
preparation by that digest while the revision stays the same, and unchanged bytes cancel no new
qualification. An assessment answers the `operation_request` its request carries, names it by
digest, and stores nothing. Observing a preparation writes what was observed and moves no head:
a preparation nothing delivered or activated has no observation, and one whose delivery was
requested and not seen is `not_observed` with `delivery_unobserved`.

Each repository, person and Team keeps one `collection` per role: nine positions, each with
its own head. A position is an original; a preparation is derived from the heads it read and
never writes one. An entry references a source at an exact revision, or a memory source at the
frontier each operation observes, and declares the units composition resolves: an overlap key,
applicable conditions, whether the unit must resolve at startup when it wins, and what its bytes
need. An empty position contributes nothing; a switch turned `off` excludes that selection until
it is turned on, and nothing else. Units of one layer that answer one concern are ordered by
explicit precedence, or the concern stays `same_layer_unordered` for the query that needs it.
A draft is staged by the change that names it: the change carries the draft's `source_manifest`
beside the collection, the owner stages those bytes without accepting them, and the source's
head moves only when its own owner commits the revision. Composition reads entries, not drafts.

A head is one value: a collection's is the digest of the collection its last committed change
stored, and an environment's the digest of its current edition. The base a request expects, the
head its receipt names and a preparation's `collection_head` all state that digest. An adoption
names the edition it adopts as its base, leaves the environment's head where it was, and its
receipt names the adoption it stored.

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
                "environment_adoption", "collection")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name. A request for an operation states
# its `effect` class and grant `action`, and targets a resource whose id carries one of its
# `targets` prefixes: a preparation and an assessment are the requester's own, an observation
# targets the preparation it observes, and a change to a collection or an environment targets
# its head.
OPERATIONS = {
    "preparation.compose": {"takes": ("preparation_request",),
                            "returns": ("preparation", "session_routing"),
                            "effect": "durable_candidate", "action": "use", "targets": ("prn",)},
    "preparation.assess": {"takes": ("operation_request",), "returns": ("action_assessment",),
                           "effect": "pure_preview", "action": "read", "targets": ("prn",)},
    "delivery.observe": {"takes": (), "returns": ("delivery_observation",),
                         "effect": "durable_candidate", "action": "read", "targets": ("prp",)},
    "environment.publish": {"takes": ("environment_edition",),
                            "returns": ("environment_edition",),
                            "effect": "owner_commit", "action": "publish", "targets": ("env",)},
    "environment.adopt": {"takes": (), "returns": ("environment_adoption",),
                          "effect": "owner_commit", "action": "adopt", "targets": ("env",)},
    "collection.change": {"takes": ("collection",), "returns": ("collection",),
                          "effect": "owner_commit", "action": "contribute", "targets": ("col",)},
    "collection.read": {"takes": (), "returns": ("collection",),
                        "effect": "pure_preview", "action": "read", "targets": ("col",)},
}

SELECTION_UNRESOLVED = "selection_unresolved"
WORKING_BYTES_MOVED = "working_bytes_moved"
ISOLATION_UNPROVEN = "isolation_unproven"
DELIVERY_UNOBSERVED = "delivery_unobserved"
RENDERING_NOT_RETAINED = "rendering_not_retained"
ADOPTION_EVIDENCE_MISSING = "adoption_evidence_missing"
SAME_LAYER_UNORDERED = "same_layer_unordered"

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
    SAME_LAYER_UNORDERED: "units of one layer that answer one concern with no explicit "
                          "precedence between them; the concern stays unresolved for the query "
                          "that needs it, and nothing else is held back",
}
