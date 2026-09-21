"""C06 The reader envelope: the gaps its operations answer with.

Record kinds: `reader_envelope`, `reader_result`, `pending_question`, `resume_request`.

One envelope serves all three roles, and one result comes back with a standing that says which
kind of answer it is. Seven standings stay apart because they lead different places: a source
with nothing to say is `empty` and is a valid answer, while `denied`, `unavailable`,
`unsupported`, `unresolved` and `truncated` each name something else that happened.

A budget bounds what may be examined as well as what may be returned, and a result states what it
consumed of both. Each returned unit says whether it answers a required subject or is optional
support, so required meaning is fitted first. A selected source the read did not check is named as
not checked, remote and unknown, or missing, apart from one it checked and found empty. An envelope
says whether it asks for history as well as what is current: with history included, a unit that
is no longer current comes back marked `superseded` or `withdrawn`, and with it excluded none
does.

Access is resolved before any candidate or metadata is shown, so a reader that cannot establish
it returns `access_not_established` rather than a list of what it would have returned. A cursor
carries the basis it was taken at, so a later page cannot quietly follow a newer head. That a
frontier named by an `access_not_established` gap's pointer is not returned relates one element to
another, which a schema cannot state; the runtime owner keeps it and P01's cases check it, and
likewise that a result whose envelope excludes history returns no unit marked `superseded` or
`withdrawn`.

An envelope may also select the person's own memory candidates, each at an exact version. They
come back beside the units as `candidates`, marked unadopted: support for this work that no
destination has accepted. A candidate is never a winning unit, and reading one publishes,
adopts and commits nothing; a candidate the reader may not see is refused like any other access.

Reading is not applying. An inspection returns history and alternatives and admits no use of
them; when an actual use needs a person's answer, the question is sealed and stored first and
the result carries a `pending_user` use, the question and use it waits on, which is never a
first option chosen on their behalf. A result that admits a use names that use and the state it
was admitted on; a later use or a child recipient is admitted on its own. A question is sealed
against a `comparison_basis`.

A use is what an answer applies to. `memory.use.prepare` targeting a concern starts a new use of
it, whose id the owner mints; targeting a use prepares that same use again — a retry under a new
request, a later page or a reconnect — and finds its one pending question or its admitted result,
sealing a new question version only when the basis has moved. A stored application that no longer
holds — a participant moved, or the basis cannot be verified, as after a restore — comes back as
it now stands, invalidated with the reason, beside `preference_invalidated`, and the use waits on a
new question. `reader.use.resume` targets the use it resumes and carries the answer as C11's
evidence; the answer itself has no field here. A resume whose evidence is not a verified answer
leaves the use waiting: the result is `blocked`, states `answer_not_from_a_person` or
`answer_origin_unverified`, and returns the same `pending_user` use. A prepare, or a resume's
recheck before admission, that cannot reach a required participant of the comparison is `blocked`
with C05's `comparison_incomplete` and returns the result naming that source as unread.
`reader.question.answer` returns the sealed question a use waits on and its basis, for the working
host to ask; it writes nothing and admits nothing.
"""
CONTRACT = "C06"
RECORD_KINDS = ("reader_envelope", "reader_result", "pending_question", "resume_request")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name. `effect`, `action` and `targets`
# are the effect class, the grant action and the target id prefixes every request for it states.
OPERATIONS = {
    "memory.use.prepare": {"takes": ("reader_envelope",),
                           "returns": ("reader_result", "pending_question", "qualified_state",
                                       "comparison_basis", "application_preference"),
                           "effect": "durable_candidate", "action": "use",
                           "targets": ("cnc", "use")},
    "reader.body.read": {"takes": ("reader_envelope",), "returns": ("reader_result",),
                         "effect": "pure_preview", "action": "read",
                         "targets": ("src", "rep", "prn")},
    "reader.question.answer": {"takes": ("reader_envelope",),
                               "returns": ("reader_result", "pending_question",
                                           "comparison_basis"),
                               "effect": "pure_preview", "action": "read", "targets": ("use",)},
    "reader.use.resume": {"takes": ("resume_request",), "returns": ("reader_result",),
                          "effect": "durable_candidate", "action": "use", "targets": ("use",)},
}

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "gap_named_frontier_not_returned": "a result returns no frontier an access_not_established "
                                       "gap's pointer names",
    "history_only_when_asked": "a result whose envelope excludes history returns no unit "
                               "marked superseded or withdrawn",
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
