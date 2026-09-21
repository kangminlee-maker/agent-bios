"""C11 The recipient: the gaps its operations answer with.

Record kinds: `recipient_link`, `answer_evidence`, `delivery_attempt`,
`surface_observation`, `exposure_trial`, `host_reply`, `study_protocol`.

`answer_evidence` is the record every other contract points at by digest when it says a person
answered. It names the `host_configuration` (C12) the runtime measured on that host when it
classified the reply, because the configuration that can answer for a person is the same one that
would have to prove it did not. Exactly one origin is an answer, and it must name the evidence
that separated a person from the host's own automation: the C12 `capability_probe` of
`user_event` that ran for real and worked on that host. Cancel, decline, timeout, a hook's reply,
a tool-permission approval and a model's quotation are each a named non-answer. That the
configuration and the probe are the answering host's relates the evidence to them, which a schema
cannot state; the runtime owner keeps it and P01's cases check it.

On the installed hosts nothing has qualified that separation yet, so the honest records today are
the non-answers, and a conflicting use waits as C06's `pending_user`. The shape is what makes
that visible instead of letting an `accept` pass for a person.

A destination says where to ask and nothing more: no preference, use or choice is keyed by one.
Its digest is of the identifier the host adapter reported for it, which is the host's bytes and
not a record. A link's `rights_digest` names the Team `grant_record` (C08) its principal receives
the work scope's material under, when a Team's grant is what permits it.
A retry of a use keeps its use id and question version — a new id is a different question.
A question or resume attempt names the use the reader owner minted; a body attempt's use id is
the caller's own name for that one delivery, as a request id is.
An attempt names exactly what it delivers — a question version, one preparation's bodies to a
new, current, child or rehydrated recipient, or a resume — and a receipt names exactly the
bodies that arrived.

An `exposure_trial` is one participant attempting one task on a surface met for the first time
(N26): what they said before acting — options, selection, predicted effect and target — kept apart
from the outcome observed, with help, confusion, the exact UI subject and any critical
misinterpretation left unresolved. It names the `surface_observation` it happened in, and the
`study_protocol` and task it was run under, and qualifies nothing about terminals or answers
itself. The protocol is fixed first: each cell is a task, a participant class, a listed
terminal, a locale and input routes with the fewest trials it needs, so a missing observation
is found by counting. An observation states the input routes it used.

What a host delivered is a `host_reply`, which names no origin: the runtime decides that. A
verified answer carries what the person chose. That the choice is one of the alternatives its
question version offered relates the evidence to the question, which a schema cannot state; the
runtime owner keeps it and P01's cases check it. A reply choosing a record its question version
did not offer is refused, and no evidence is written for it.
"""
CONTRACT = "C11"
RECORD_KINDS = ("recipient_link", "answer_evidence", "delivery_attempt",
                "surface_observation", "exposure_trial", "host_reply", "study_protocol")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. `effect`, `action` and `targets`
# are what every request for it states: its effect class, the one grant action it needs and
# the id prefixes its target may carry. The union across the contract modules is the closed
# list a request may name.
OPERATIONS = {
    "recipient.link.open": {"takes": ("recipient_link",), "returns": ("recipient_link",),
                            "effect": "owner_commit", "action": "use", "targets": ("prn",)},
    "recipient.answer.record": {"takes": ("host_reply",),
                                "returns": ("answer_evidence", "host_configuration"),
                                "effect": "owner_commit", "action": "use", "targets": ("qst",)},
    "recipient.delivery.attempt": {"takes": ("delivery_attempt",),
                                   "returns": ("delivery_attempt",),
                                   "effect": "owner_commit", "action": "use",
                                   "targets": ("lnk",)},
    "surface.observe": {"takes": ("surface_observation", "exposure_trial"),
                        "returns": ("surface_observation", "exposure_trial"),
                        "effect": "owner_commit", "action": "contribute", "targets": ("prf",)},
    "surface.protocol.record": {"takes": ("study_protocol",),
                                "returns": ("study_protocol",),
                                "effect": "owner_commit", "action": "contribute",
                                "targets": ("prf",)},
}

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "answer_selects_an_offered_alternative": "a verified answer that selects a record selects "
                                             "one its question version offered",
    "attempt_outcome_fits_its_request": "an attempt sees an answer only to a question it "
                                        "delivered, and receives only bodies it asked to "
                                        "deliver",
    "answer_separated_on_its_own_host": "evidence names a configuration measured for real on "
                                        "the host it names, and a verified answer's separation "
                                        "evidence is a user_event probe that ran for real and "
                                        "worked on that host",
}

RECIPIENT_LINK_UNKNOWN = "recipient_link_unknown"
ANSWER_ORIGIN_UNVERIFIED = "answer_origin_unverified"
ANSWER_NOT_FROM_A_PERSON = "answer_not_from_a_person"
RESUME_STALE = "resume_stale"
DESTINATION_INVENTED = "destination_invented"
REHYDRATION_NEEDS_BODIES = "rehydration_needs_bodies"
RETRY_UNDER_A_NEW_ID_REFUSED = "retry_under_a_new_id_refused"
MANAGEMENT_DETOUR_REFUSED = "management_detour_refused"
ALTERNATIVE_NOT_OFFERED = "alternative_not_offered"

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
    ALTERNATIVE_NOT_OFFERED: "a reply choosing a record its question version did not offer",
}
