"""C10 Custody and retention: the gaps its operations answer with.

Record kinds: `custody_commitment`, `custody_acknowledgment`, `retention_plan`,
`removal_outcome`, `removal_request`, `derivation_query`, `derivation_map`.

Custody is what a named accountable device or peer undertook to keep, object by object, under a
storage generation. A copy count is not custody and no schema here holds one: more independent
failure domains improve recovery, they do not prove it, and a configurable target is not a quorum.

Promised bodies and evictable cache are two lists. When space runs out the answer is to decline
the promise, which somebody sees, and never to evict a promised body, which nobody sees.

Removal happens to copies. Confirmed, denied, unreachable and unknown stay apart, a confirmed
removal names its tombstone so returning offline data cannot put the object back, and nothing
here promises that a copy already delivered or outside this Team's control is gone. A copy the
retention plan in force still promises is `held` and names that plan: it is neither removed nor
refused, and a plan that no longer promises the object is what releases it.

What the store derives from an object — an index, an excerpt, a candidate, a prompt, an export —
is in its `derivation_map`, and removing the object removes each of them with it, copy by copy;
nothing names a replacement for removed evidence. That the removal's derived copies cover the
map relates two records, which a schema cannot state; the runtime owner keeps it and P01's cases
check it.
"""
CONTRACT = "C10"
RECORD_KINDS = ("custody_commitment", "custody_acknowledgment", "retention_plan",
                "removal_outcome", "removal_request", "derivation_query", "derivation_map")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name. A request for an operation states
# its `effect` class and grant `action`, and targets a resource whose id carries one of its
# `targets` prefixes: a custody commitment targets the holder that undertakes it and an
# acknowledgment the commitment it observes; retention and removal target the scope whose
# holders keep the copies.
OPERATIONS = {
    "custody.commit": {"takes": ("custody_commitment",), "returns": ("custody_commitment",),
                       "effect": "owner_commit", "action": "retain_delete",
                       "targets": ("dev", "per")},
    "custody.acknowledge": {"takes": ("custody_acknowledgment",),
                            "returns": ("custody_acknowledgment",),
                            "effect": "owner_commit", "action": "retain_delete",
                            "targets": ("cus",)},
    "retention.plan.set": {"takes": ("retention_plan",), "returns": ("retention_plan",),
                           "effect": "owner_commit", "action": "retain_delete",
                           "targets": ("tem", "prn", "rep")},
    "removal.execute": {"takes": ("removal_request",), "returns": ("removal_outcome",),
                        "effect": "owner_commit", "action": "retain_delete",
                        "targets": ("tem", "prn", "rep")},
    "retention.derivations.read": {"takes": ("derivation_query",),
                                   "returns": ("derivation_map",),
                                   "effect": "pure_preview", "action": "read",
                                   "targets": ("tem", "prn", "rep")},
}

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "removal_covers_derivatives": "a removal outcome names every object the store's derivation "
                                  "map records for the removed object among its derived copies",
}

CUSTODY_INCOMPLETE = "custody_incomplete"
RETENTION_DECLINED = "retention_declined"
STORAGE_GENERATION_RESET = "storage_generation_reset"
UNIQUE_OUTBOX_AT_RISK = "unique_outbox_at_risk"
REMOVAL_UNCONFIRMED = "removal_unconfirmed"
ERASURE_NOT_PROMISED = "erasure_not_promised"
RESURRECTION_REFUSED = "resurrection_refused"
REMOVAL_HELD = "removal_held"

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
    REMOVAL_HELD: "a copy the retention plan in force still promises; it is kept, neither "
                  "removed nor refused, until a plan that no longer promises it is set",
}
