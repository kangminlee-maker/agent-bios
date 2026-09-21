"""C03 Owned operations: the gaps its operations answer with.

Record kinds: `operation_request`, `operation_result`, `operation_receipt`, `operation_query`,
`request_not_held`, `entrance_disposition`, `cutover_plan`, `restore_report`, `backup_set`.

Every protected operation of every contract travels in one sealed request and is answered by
one result. The request names its payload by digest, so the payload's shape belongs to the
contract that owns it. The digest of the request's stored bytes is its identity: the runtime
adds no field to it, and the same `request_id` with other bytes is a conflict, never a second
operation. A receipt is what makes an object accepted; asking again with the same request
returns the original result and receipt. A result always answers a request its owner holds; an id
the owner never received is answered by `request_not_held`, which carries nothing else. A committed
result names its receipt and states only gaps that qualify a commit (`errors.disclosed`); a gap
that prevents a commit, such as `stale_base`, belongs to a result that did not commit.

What a request carries is its operation's to say. `OPERATIONS` in each contract module names
the record kinds an operation takes and the kinds its result may return, so a request states no
payload kind of its own: the payload's bytes name their kind, and a kind the operation does not
take — or a payload where it takes none, or none where it takes one — is `payload_not_taken`.

A request states its effect class. `pure_preview` writes nothing; a plan that is stored says
`durable_candidate`; only `owner_commit` moves a head, and it names the base it expects.

Which operation a request may name, and which entrance may raise it, are both closed lists
rather than patterns. An open pattern accepts a typo as readily as an operation, so nothing
downstream can tell a new name from a wrong one; `OPERATIONS` here is the union the contract
modules declare, and `ENTRANCES` is every way a caller starts work. Either list growing is a
contract change, which is a replan trigger — that is the cost, and it is the one being bought.

`entrance_disposition` answers one question per entrance: can it reach state the target keeps,
through a root the caller chose, without the one admission owner? An entrance that reaches has
two spellings, `choke_point` and `routed`, and both name a guard. Reaching state outside a
choke point has no spelling at all, so the construction sites and the guarded set are the same
set by construction rather than by a later count. `cutover_plan` is the single retirement: its
three stages are three named fields, because a stage list can be reordered or shortened and
three fields cannot, and `commits` is one because the cutover is abortable until it.

A backup is taken and restored through the same owner. `backup_set` is what it took — the
database snapshot and every other member by digest — and is submitted back whole to restore.
What a restore establishes is a `restore_report`: the receipt sequence the backup covers and the
instant it represents. Work
after that instant is neither recovered nor known to be absent, so the report has one value for
it, and restored authority is passive until access, clock and keys are established again.
"""
CONTRACT = "C03"
RECORD_KINDS = ("operation_request", "operation_result", "operation_receipt", "operation_query",
                "request_not_held", "entrance_disposition", "cutover_plan", "restore_report",
                "backup_set")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name.
OPERATIONS = {
    "operation.cancel": {"takes": ("operation_query",), "returns": ()},
    "operation.query": {"takes": ("operation_query",),
                        "returns": ("operation_result", "operation_receipt", "request_not_held")},
    "entrance.disposition.record": {"takes": ("entrance_disposition",),
                                    "returns": ("entrance_disposition",)},
    "entrance.cutover.commit": {"takes": ("cutover_plan",), "returns": ()},
    "store.backup.create": {"takes": (), "returns": ("backup_set",)},
    "store.backup.restore": {"takes": ("backup_set",), "returns": ("restore_report",)},
}

# Every way a caller starts work with the target. A disposition is recorded for each.
ENTRANCES = (
    "session_start", "host_launcher", "studio_hub", "supplied_request", "work_link",
    "setup", "locked_scope", "decision_cli", "decision_mcp", "studio_bridge",
    "capture_intake", "compatibility_route",
    # A support command — measurement, checks, a cache, cleanup. Added when the existing routes
    # were disposed of one by one: `cost`, `help` and the check scripts fit no other name.
    "maintenance",
)

# The three places a guard sits. Named by what each owns, because that is what decides
# which one an entrance routes through — not by the module that happens to hold it today.
CHOKE_POINTS = ("source_store", "projection_owner", "publication_lock")

# The id prefixes whose owner keeps a head. A request targeting one names the base it expects
# (`absent`, or the exact head); a request targeting anything else has no base to name, so a
# head-moving request cannot be written without its stale-head precondition. A source keeps its
# revision head, a collection its original head (SSOT S13), an environment its edition, and a
# Team the head its one finalizer sequences (SSOT S11).
HEAD_KEEPING = ("src", "col", "env", "tem")

# Targets no contract declares an id for, which operations nonetheless address: a stored
# memory candidate before it is a record, and the concern an application preference answers.
TARGET_ONLY = ("cnd", "cnc")

# Why an entrance reaches no state the target keeps. Each value was found by tracing the
# shipped tree; a reason no entrance has is not carried here. Only `holds_no_write` holds whoever
# chose the entrance's root; the others hold only under a root the entrance fixes itself. A root
# the caller chose is one a caller sets for this route alone — an argument, `--repo`,
# `AGENT_BIOS_STATE_DIR`. `$HOME` is not one: every owner resolves its own root from it, so
# moving it moves the kept state with it.
NO_REACH_REASONS = ("writes_only_under_temp", "writes_only_in_self_test",
                    "writes_outside_kept_state", "holds_no_write")

REQUEST_ID_CONFLICT = "request_id_conflict"
REQUEST_MISMATCH = "request_mismatch"
STALE_BASE = "stale_base"
EFFECT_CLASS_MISMATCH = "effect_class_mismatch"
OBJECT_DIGEST_MISMATCH = "object_digest_mismatch"
OUTCOME_UNKNOWN = "outcome_unknown"
OUTCOME_PARTIAL = "outcome_partial"
CANCEL_TOO_LATE = "cancel_too_late"
PAYLOAD_NOT_TAKEN = "payload_not_taken"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    REQUEST_ID_CONFLICT: "a request id already used for a request with other bytes",
    REQUEST_MISMATCH: "an approval, proof or payload bound to another request than this one",
    STALE_BASE: "an owner commit whose expected base is no longer the head",
    EFFECT_CLASS_MISMATCH: "an operation that would write more than its stated effect class",
    OBJECT_DIGEST_MISMATCH: "staged bytes whose digest differs from the one the request names",
    OUTCOME_UNKNOWN: "a dispatched effect whose outcome is not known; ask again by the same id",
    OUTCOME_PARTIAL: "an effect some owners committed and others did not",
    CANCEL_TOO_LATE: "a cancellation that reached its owner after the commit",
    PAYLOAD_NOT_TAKEN: "a payload of a kind the named operation does not take, a payload named "
                       "where it takes none, or none named where it takes one",
}
