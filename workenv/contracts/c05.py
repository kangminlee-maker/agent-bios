"""C05 Recorded choices and their current state: the gaps its operations answer with.

Record kinds: `workstream`, `choice_record`, `lifecycle_event`, `state_question`,
`qualified_state`, `application_preference`.

Records are immutable; what happens to them is a separate event, and current state is reduced
from both before anything is ranked or clipped. That order is what keeps a withdrawal from
being filtered away and leaving the earlier choice reading as current — so `qualified_state`
names every entry it reduced, including the ones it could not resolve.

Nothing here selects a winner between incompatible applicable choices. That is
`choice_conflict_unresolved`, and it is answered by the person, through C06 and C11, whose
answer an `application_preference` then records against the whole relevant participant set.
A code this module does not own but its results state: C01's `id_bound_to_other_bytes`, for
two records that share an id and differ in bytes.
"""
CONTRACT = "C05"
RECORD_KINDS = ("workstream", "choice_record", "lifecycle_event", "state_question",
                "qualified_state", "application_preference")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request.
# The union across the contract modules is the closed list a request may name.
OPERATIONS = (
    "workstream.open",
    "memory.candidate.store",
    "memory.record.publish",
    "memory.lifecycle.apply",
    "memory.state.resolve",
    "memory.preference.record",
)

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
