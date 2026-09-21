"""C11 The recipient: the gaps its operations answer with.

Record kinds: `recipient_link`, `answer_evidence`, `delivery_attempt`,
`surface_observation`, `exposure_trial`.

`answer_evidence` is the record every other contract points at by digest when it says a person
answered. It carries the host's effective configuration as measured at the time of the question,
because the configuration that can answer for a person is the same one that would have to prove
it did not. Exactly one origin is an answer, and it must name the evidence that separated a
person from the host's own automation; cancel, decline, timeout, a hook's reply, a tool-permission
approval and a model's quotation are each a named non-answer.

On the installed hosts nothing has qualified that separation yet, so the honest records today are
the non-answers, and a conflicting use waits as C06's `pending_user`. The shape is what makes
that visible instead of letting an `accept` pass for a person.

A destination says where to ask and nothing more: no preference, use or choice is keyed by one.
A retry of a use keeps its use id and question version — a new id is a different question.

An `exposure_trial` is one participant attempting one task on a surface met for the first time
(N26): what they said before acting — options, selection, predicted effect and target — kept apart
from the outcome observed, with help, confusion, the exact UI subject and any critical
misinterpretation left unresolved. It names the `surface_observation` it happened in and
qualifies nothing about terminals or answers itself.
"""
CONTRACT = "C11"
RECORD_KINDS = ("recipient_link", "answer_evidence", "delivery_attempt",
                "surface_observation", "exposure_trial")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request.
# The union across the contract modules is the closed list a request may name.
OPERATIONS = (
    "recipient.link.open",
    "recipient.answer.record",
    "recipient.delivery.attempt",
    "surface.observe",
)

RECIPIENT_LINK_UNKNOWN = "recipient_link_unknown"
ANSWER_ORIGIN_UNVERIFIED = "answer_origin_unverified"
ANSWER_NOT_FROM_A_PERSON = "answer_not_from_a_person"
RESUME_STALE = "resume_stale"
DESTINATION_INVENTED = "destination_invented"
REHYDRATION_NEEDS_BODIES = "rehydration_needs_bodies"
RETRY_UNDER_A_NEW_ID_REFUSED = "retry_under_a_new_id_refused"
MANAGEMENT_DETOUR_REFUSED = "management_detour_refused"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    RECIPIENT_LINK_UNKNOWN: "a host, recipient or work link this runtime has no record of",
    ANSWER_ORIGIN_UNVERIFIED: "a route that cannot separate a person from the host's own "
                              "automation, so no answer from it can qualify a choice",
    ANSWER_NOT_FROM_A_PERSON: "a cancel, decline, timeout, hook reply, tool-permission approval "
                              "or model quotation offered as this person's answer",
    RESUME_STALE: "a resume for a question version whose basis has since moved",
    DESTINATION_INVENTED: "a destination nobody supplied for this use",
    REHYDRATION_NEEDS_BODIES: "a hash offered where the actual bodies are required",
    RETRY_UNDER_A_NEW_ID_REFUSED: "a retry that minted a new use or question id; that is a "
                                  "different question, not a second attempt",
    MANAGEMENT_DETOUR_REFUSED: "a decision question routed through a management screen instead "
                               "of the working host the use is in",
}
