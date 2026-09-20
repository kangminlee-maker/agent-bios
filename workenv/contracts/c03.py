"""C03 Owned operations: the gaps its operations answer with.

Record kinds: `operation_request`, `operation_result`, `operation_receipt`, `operation_query`.

Every protected operation of every contract travels in one sealed request and is answered by
one result. The request names its payload by digest, so the payload's shape belongs to the
contract that owns it. The digest of the request's stored bytes is its identity: the runtime
adds no field to it, and the same `request_id` with other bytes is a conflict, never a second
operation. A receipt is what makes an object accepted; asking again with the same request
returns the original result and receipt.

A request states its effect class. `pure_preview` writes nothing; a plan that is stored says
`durable_candidate`; only `owner_commit` moves a head, and it names the base it expects.
"""
CONTRACT = "C03"
RECORD_KINDS = ("operation_request", "operation_result", "operation_receipt", "operation_query")
IN_RESULTS = True

REQUEST_ID_CONFLICT = "request_id_conflict"
REQUEST_MISMATCH = "request_mismatch"
REQUEST_UNKNOWN = "request_unknown"
STALE_BASE = "stale_base"
EFFECT_CLASS_MISMATCH = "effect_class_mismatch"
OBJECT_DIGEST_MISMATCH = "object_digest_mismatch"
OUTCOME_UNKNOWN = "outcome_unknown"
OUTCOME_PARTIAL = "outcome_partial"
CANCEL_TOO_LATE = "cancel_too_late"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    REQUEST_ID_CONFLICT: "a request id already used for a request with other bytes",
    REQUEST_MISMATCH: "an approval, proof or payload bound to another request than this one",
    REQUEST_UNKNOWN: "a query for a request id this owner never received",
    STALE_BASE: "an owner commit whose expected base is no longer the head",
    EFFECT_CLASS_MISMATCH: "an operation that would write more than its stated effect class",
    OBJECT_DIGEST_MISMATCH: "staged bytes whose digest differs from the one the request names",
    OUTCOME_UNKNOWN: "a dispatched effect whose outcome is not known; ask again by the same id",
    OUTCOME_PARTIAL: "an effect some owners committed and others did not",
    CANCEL_TOO_LATE: "a cancellation that reached its owner after the commit",
}
