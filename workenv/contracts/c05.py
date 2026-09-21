"""C05 Recorded choices and their current state: the gaps its operations answer with.

Record kinds: `workstream`, `choice_record`, `lifecycle_event`, `state_question`,
`qualified_state`, `application_preference`, `memory_candidate`, `state_proof`,
`comparison_basis`.

Records are immutable; what happens to them is a separate event, and current state is reduced
from both before anything is ranked or clipped. That order is what keeps a withdrawal from
being filtered away and leaving the earlier choice reading as current — so `qualified_state`
names every entry it reduced, including the ones it could not resolve.

Lanes are associations: a choice or an event may be recorded in several workstreams, a state
question may ask about one lane's records, and an event recorded in another lane still changes the
state of the record it targets. Each `qualified_state` entry names the source its record was read
from.

Where the records behind a correction are restricted, a `state_proof` issued by their authority for
one audience and one question can stand in for them: it states the reduced state, what it covers
and what it does not identify, and grants nothing. One that does not verify, is stale or is about
another subject or audience leaves state unresolved.

A `memory_candidate` is a proposed choice or event before any destination accepts it — a
lifecycle state, not a store. Every version keeps the origin it was created with, so editing never
changes the capture, the transcript or an original record; it is promoted only by a commit at its
destination, whose receipt it then names, and a rejected candidate is kept.

Nothing here selects a winner between incompatible applicable choices. That is
`choice_conflict_unresolved`, and it is answered by the person, through C06 and C11, whose
answer an `application_preference` then records against the whole relevant participant set. The
question and the answer are bound to a `comparison_basis`: that set with its revisions, coverage
and change generation.
A code this module does not own but its results state: C01's `id_bound_to_other_bytes`, for
two records that share an id and differ in bytes.

Four rules relate one element of a record to another, which a schema cannot state; the runtime
owner keeps them and P01's cases check them: the record an active preference's answer selects is
a participant its list marks applicable, a `qualified_state` entry named by a gap's pointer is
not `current`, every entry names the source that holds its record and the state's frontiers name
that source, and every version of a candidate keeps the origin of the version before it.
"""
CONTRACT = "C05"
RECORD_KINDS = ("workstream", "choice_record", "lifecycle_event", "state_question",
                "qualified_state", "application_preference", "memory_candidate", "state_proof",
                "comparison_basis")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name.
OPERATIONS = {
    "workstream.open": {"takes": ("workstream",), "returns": ("workstream",)},
    "memory.candidate.store": {"takes": ("memory_candidate",), "returns": ("memory_candidate",)},
    "memory.candidate.reject": {"takes": (), "returns": ("memory_candidate",)},
    "memory.record.publish": {"takes": ("choice_record",),
                              "returns": ("choice_record", "source_manifest", "memory_candidate")},
    "memory.lifecycle.apply": {"takes": ("lifecycle_event",),
                               "returns": ("lifecycle_event", "source_manifest",
                                           "memory_candidate")},
    "memory.state.resolve": {"takes": ("state_question",), "returns": ("qualified_state",)},
    "memory.state.prove": {"takes": ("state_question",), "returns": ("state_proof",)},
    "memory.preference.record": {"takes": (), "returns": ("application_preference",)},
}

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "selected_participant_applicable": "the record an active preference's answer selects "
                                       "is one its own participant list marks applicable",
    "gap_named_entry_not_current": "a qualified_state entry a gap's pointer names is not current",
    "entry_from_named_source": "every qualified_state entry names the source that holds its "
                               "record, and its frontiers name that source",
    "candidate_keeps_its_origin": "every version of a memory_candidate names the origin of the "
                                  "version before it",
}

BASIS_TARGET_MISSING = "basis_target_missing"
BASIS_CYCLE = "basis_cycle"
COMPETING_SUCCESSORS = "competing_successors"
LIFECYCLE_CONTRADICTION = "lifecycle_contradiction"
STATE_PROOF_INVALID = "state_proof_invalid"
STATE_PROOF_STALE = "state_proof_stale"
STATE_PROOF_OUT_OF_SCOPE = "state_proof_out_of_scope"
CHOICE_CONFLICT_UNRESOLVED = "choice_conflict_unresolved"
PREFERENCE_INVALIDATED = "preference_invalidated"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    BASIS_TARGET_MISSING: "a stated reliance on a record this reader cannot reach",
    BASIS_CYCLE: "records whose stated reliance closes on itself",
    COMPETING_SUCCESSORS: "more than one record declaring it replaces the same one whole",
    LIFECYCLE_CONTRADICTION: "events whose assertions about one record cannot both hold",
    STATE_PROOF_INVALID: "a qualified state artifact whose issuer or signature does not verify",
    STATE_PROOF_STALE: "a qualified state artifact behind the frontier this operation observed",
    STATE_PROOF_OUT_OF_SCOPE: "a qualified state artifact about other subjects or another "
                              "audience than the one asking",
    CHOICE_CONFLICT_UNRESOLVED: "incompatible applicable choices with no current application "
                                "from the person; no order and no timestamp picks one",
    PREFERENCE_INVALIDATED: "a stored application whose relevant participant set has moved",
}
