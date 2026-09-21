"""C03 Owned operations: the gaps its operations answer with.

Record kinds: `operation_request`, `operation_result`, `operation_receipt`, `operation_query`,
`request_not_held`, `request_not_covered`, `entrance_disposition`, `cutover_plan`,
`restore_report`, `backup_set`, `package_candidate`, `history_query`, `recent_history`,
`batch_plan`, `batch_result`.

Every protected operation of every contract travels in one sealed request and is answered by
one result. The request names its payload by digest, so the payload's shape belongs to the
contract that owns it. The digest of the request's stored bytes is its identity: the runtime
adds no field to it, and the same `request_id` with other bytes is a conflict, never a second
operation. A receipt is what makes an object accepted; asking again with the same request
returns the original result and receipt. An outcome that is unknown is settled by asking again
under the same id: a request repeating the operation, target and payload of one the owner holds
with an unknown outcome, under a new id, is `resubmitted_while_unknown`. A result always answers a
request its owner holds; an id the owner never received is answered by `request_not_held`, which
carries nothing else. A committed result names its receipt and states only gaps that qualify a
commit (`errors.disclosed`); a gap that prevents a commit, such as `stale_base`, belongs to a
result that did not commit.

What a request carries is its operation's to say. `OPERATIONS` in each contract module names
the record kinds an operation takes and the kinds its result may return, so a request states no
payload kind of its own: the payload's bytes name their kind, and a kind the operation does not
take — or a payload where it takes none, or none where it takes one — is `payload_not_taken`.

A request binds its requester, the actor, and — when others are accountable for what it
carries — those `accountable_authors` too, so a policy that excludes recorded authors from an
independent review can count them at the owner.

Many requests can travel as one `batch_plan`. Each item is its own sealed request, named by
digest, with the carrier that commits it; one carrier's items commit together or not at all, and
items on different carriers do not. The `batch_result` states each item's own outcome —
committed, refused, unknown, or withheld because its carrier's other items did not commit — and
has no summary to hide one in. A retry submits the same plan, so no item runs twice.

What happened recently is read when asked, not remembered as intent: `recent_history` gives one
scope's recent requests with the last stage confirmed for each, when, and what that observation
covered, and dated checkpoints with any note recorded then. It has no field for a goal, a current
request or a next action.

An operation's row also fixes what every request for it states, so two callers cannot spell one
operation two ways: its effect class (`effect`), the one grant action it needs (`action`), and the
id prefixes its target may carry (`targets`). `pure_preview` writes nothing; `durable_candidate`
stores a plan or candidate and moves no head; `owner_commit` commits what the owner keeps under a
receipt — only it moves a head, and on a target whose owner keeps one it names the base it
expects. An operation that needs no Team grant — one on the actor's own profile, installation or
request — states `local_profile`.

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
three fields cannot, and `commits` is one because the cutover is abortable until it. A route
is retired by a `retired_at_cutover` disposition recorded before the cutover commits, and an
entrance by having every route recorded for it retired; both stay retired through any later
restore. A request says which entrance it came through only by the access handle it names in
`proof_digests`: one whose handle was issued through a retired entrance, or a disposition that
would have a retired route reach kept state again, is `route_retired`.

The cutover also moves state ownership, once. Its `data` is a fresh start or one selected
transfer: the transfer names the export baseline its first conversion read, and the source
revision and outbox captured again after the old writers were quiesced, with the validated import
of exactly those. A source or outbox that moves after that capture is `cutover_source_moved`,
and the cutover waits for the next capture. Every operation the old runtime left unknown is
settled or carried with the recovery that settles it, and the old source is kept or archived:
the plan has no value that deletes it. `candidate_digest` names the `package_candidate` it
installs, whose members each say where their bytes came from. It must be one this owner
registered: bytes on disk without a registration receipt are not a candidate, and a digest naming
none is `candidate_not_registered`. Registering a candidate holds its closure: a path a member
`reaches` at run time that no member provides is `runtime_path_missing`, and a member copied
from a path the integrated source declares author-side is `author_side_member`, each at the place
in the candidate that names the path.

A backup is taken and restored through the same owner. `backup_set` is what it took — the
database snapshot and every other member by digest — and is submitted back whole to restore.
What a restore establishes is a `restore_report`: the receipt sequence the backup covers and the
instant it represents. Work after that instant is neither recovered nor known to be absent, so
the report has one value for it, and restored authority is passive until access, clock and keys
are established again. For the same reason a restored owner cannot tell an id it never received
from one received after the backup: a query for an id it does not hold is answered by
`request_not_covered`, which names that report, never by `request_not_held`.
"""
CONTRACT = "C03"
RECORD_KINDS = ("operation_request", "operation_result", "operation_receipt", "operation_query",
                "request_not_held", "request_not_covered", "entrance_disposition", "cutover_plan",
                "restore_report", "backup_set", "package_candidate", "history_query",
                "recent_history", "batch_plan", "batch_result")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name. `effect`, `action` and `targets` are
# what every request for it states: its effect class, the grant action it needs, and the id
# prefixes its target may carry.
#
# Cancelling, batching and the installation's own operations need no Team grant: a cancel
# withdraws the actor's own request and grants nothing, and each item of a batch is its own
# sealed request admitted under its own action, so the carrier states `local_profile`. A history
# read names the scope it reads in its payload, so its target is the profile that gathers it.
OPERATIONS = {
    "operation.cancel": {"takes": ("operation_query",), "returns": (),
                         "effect": "owner_commit", "action": "local_profile",
                         "targets": ("req",)},
    "operation.query": {"takes": ("operation_query",),
                        "returns": ("operation_result", "operation_receipt", "request_not_held",
                                    "request_not_covered"),
                        "effect": "pure_preview", "action": "read", "targets": ("req",)},
    "entrance.disposition.record": {"takes": ("entrance_disposition",),
                                    "returns": ("entrance_disposition",),
                                    "effect": "owner_commit", "action": "local_profile",
                                    "targets": ("prf",)},
    "entrance.cutover.commit": {"takes": ("cutover_plan",), "returns": (),
                                "effect": "owner_commit", "action": "local_profile",
                                "targets": ("prf",)},
    "store.backup.create": {"takes": (), "returns": ("backup_set",),
                            "effect": "owner_commit", "action": "local_profile",
                            "targets": ("prf",)},
    "store.backup.restore": {"takes": ("backup_set",), "returns": ("restore_report",),
                             "effect": "owner_commit", "action": "local_profile",
                             "targets": ("prf",)},
    "package.candidate.register": {"takes": ("package_candidate",),
                                   "returns": ("package_candidate",),
                                   "effect": "owner_commit", "action": "local_profile",
                                   "targets": ("prf",)},
    "operation.history.read": {"takes": ("history_query",), "returns": ("recent_history",),
                               "effect": "pure_preview", "action": "read", "targets": ("prf",)},
    "operation.batch.submit": {"takes": ("batch_plan",), "returns": ("batch_result",),
                               "effect": "owner_commit", "action": "local_profile",
                               "targets": ("prf",)},
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
CUTOVER_SOURCE_MOVED = "cutover_source_moved"
CANDIDATE_NOT_REGISTERED = "candidate_not_registered"
RUNTIME_PATH_MISSING = "runtime_path_missing"
AUTHOR_SIDE_MEMBER = "author_side_member"
ROUTE_RETIRED = "route_retired"
RESUBMITTED_WHILE_UNKNOWN = "resubmitted_while_unknown"

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "reached_paths_are_members": "every path a package_candidate member reaches is the path of "
                                 "a member of that candidate",
}

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
    CUTOVER_SOURCE_MOVED: "a cutover whose selected source data or outbox moved after the capture "
                          "its import was validated against; it switches only after the quiesced "
                          "state is captured and validated again",
    CANDIDATE_NOT_REGISTERED: "a cutover whose candidate_digest names no package candidate this "
                              "owner registered; bytes present without a registration receipt "
                              "are not one",
    RUNTIME_PATH_MISSING: "a package candidate with no member at a path one of its members "
                          "reaches at run time, such as an installer's or assembler's reference",
    AUTHOR_SIDE_MEMBER: "a package candidate member copied from a path the integrated source "
                        "declares author-side; author-side files never ship",
    ROUTE_RETIRED: "a request under a handle issued through an entrance the cutover retired, or "
                   "a disposition giving a retired route reach to kept state again; the route "
                   "names its successor and serves nothing itself",
    RESUBMITTED_WHILE_UNKNOWN: "a request repeating the operation, target and payload of one this "
                               "owner holds with an unknown outcome, under a new request id; the "
                               "first is settled by asking again under its own id",
}
