"""C06 The reader envelope: the gaps its operations answer with.

Record kinds: `reader_envelope`, `reader_result`, `pending_question`, `resume_request`.

One envelope serves all three roles, and one result comes back with a standing that says which
kind of answer it is. Seven standings stay apart because they lead different places: a source
with nothing to say is `empty` and is a valid answer, while `denied`, `unavailable`,
`unsupported`, `unresolved` and `truncated` each name something else that happened.

Access is resolved before any candidate or metadata is shown, so a reader that cannot establish
it returns `access_not_established` rather than a list of what it would have returned. A cursor
carries the basis it was taken at, so a later page cannot quietly follow a newer head. That a
frontier named by an `access_not_established` gap's pointer is not returned relates one element to
another, which a schema cannot state; the runtime owner keeps it and P01's cases check it.

Reading is not applying. An inspection returns history and alternatives and admits no use of
them; when an actual use needs a person's answer, the question is sealed and stored first and
the result carries it as `pending_user`, the question and use it waits on, which is never a
first option chosen on their behalf.
"""
CONTRACT = "C06"
RECORD_KINDS = ("reader_envelope", "reader_result", "pending_question", "resume_request")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request.
# The union across the contract modules is the closed list a request may name.
OPERATIONS = (
    "memory.use.prepare",
    "reader.body.read",
    "reader.question.answer",
    "reader.use.resume",
)

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "gap_named_frontier_not_returned": "a result returns no frontier an access_not_established "
                                       "gap's pointer names",
}

ACCESS_NOT_ESTABLISHED = "access_not_established"
CURSOR_BASIS_MOVED = "cursor_basis_moved"
CURSOR_REVOKED = "cursor_revoked"
BUDGET_EXHAUSTED = "budget_exhausted"
BASELINE_NOT_RETAINED = "baseline_not_retained"
CHILD_ROUTE_UNSUPPORTED = "child_route_unsupported"
USE_NOT_ADMITTED = "use_not_admitted"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    ACCESS_NOT_ESTABLISHED: "access that could not be resolved before candidates or metadata "
                            "would have been exposed",
    CURSOR_BASIS_MOVED: "a continuation whose basis is no longer the one it was taken at",
    CURSOR_REVOKED: "a continuation a revocation has invalidated",
    BUDGET_EXHAUSTED: "required material that did not fit the budget; the answer is incomplete "
                      "and carries its continuation",
    BASELINE_NOT_RETAINED: "a delta asked for against a baseline the caller has not declared it "
                           "still holds",
    CHILD_ROUTE_UNSUPPORTED: "a child reader this route cannot deliver to; the parent's delivery "
                             "does not cover it",
    USE_NOT_ADMITTED: "an inspection or a retained body offered as an admitted use",
}
