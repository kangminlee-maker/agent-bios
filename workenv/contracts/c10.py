"""C10 Custody and retention: the gaps its operations answer with.

Record kinds: `custody_commitment`, `custody_acknowledgment`, `retention_plan`,
`removal_outcome`.

Custody is what a named accountable device or peer undertook to keep, object by object, under a
storage generation. A copy count is not custody and no schema here holds one: more independent
failure domains improve recovery, they do not prove it, and a configurable target is not a quorum.

Promised bodies and evictable cache are two lists. When space runs out the answer is to decline
the promise, which somebody sees, and never to evict a promised body, which nobody sees.

Removal happens to copies. Confirmed, denied, unreachable and unknown stay apart, a confirmed
removal names its tombstone so returning offline data cannot put the object back, and nothing
here promises that a copy already delivered or outside this Team's control is gone.
"""
CONTRACT = "C10"
RECORD_KINDS = ("custody_commitment", "custody_acknowledgment", "retention_plan",
                "removal_outcome")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request.
# The union across the contract modules is the closed list a request may name.
OPERATIONS = (
    "custody.commit",
    "custody.acknowledge",
    "retention.plan.set",
    "removal.execute",
)

CUSTODY_INCOMPLETE = "custody_incomplete"
RETENTION_DECLINED = "retention_declined"
STORAGE_GENERATION_RESET = "storage_generation_reset"
UNIQUE_OUTBOX_AT_RISK = "unique_outbox_at_risk"
REMOVAL_UNCONFIRMED = "removal_unconfirmed"
ERASURE_NOT_PROMISED = "erasure_not_promised"
RESURRECTION_REFUSED = "resurrection_refused"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    CUSTODY_INCOMPLETE: "a promised object a holder no longer has, or has damaged",
    RETENTION_DECLINED: "a promise declined for want of space, rather than a promised body "
                        "evicted quietly",
    STORAGE_GENERATION_RESET: "a holder whose storage generation moved, so the old commitment's "
                              "assumptions no longer hold",
    UNIQUE_OUTBOX_AT_RISK: "an outbox or draft held in one place only",
    REMOVAL_UNCONFIRMED: "a copy whose removal was denied, unreachable or unknown",
    ERASURE_NOT_PROMISED: "copies outside this authority's control, which no removal can promise "
                          "are gone",
    RESURRECTION_REFUSED: "returning offline data that would restore a removed object; its "
                          "tombstone stops it",
}
