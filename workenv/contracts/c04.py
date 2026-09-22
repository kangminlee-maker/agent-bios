"""C04 Behavioural sources and domain knowledge: the gaps its operations answer with.

Record kinds: `projection_plan`, `role_projection`, `knowledge_question`, `knowledge_view`,
`session_routing`, `session_activation`, `knowledge_model`, `form_profile`.

Two operations share this contract because they share one rule: what reaches a role is decided
by the one admission owner, from exact source revisions, and nothing else is promoted into it.
A projection carries behavioural units only — `projected_unit.source_role` is fixed, so a
knowledge or memory source cannot enter a projection by being listed in one — and a knowledge
view carries a body with the evidence behind it and never the authority to act: the answer
returns the bytes of each member the view names (`source_member`) beside the view.

A request arrives through an entrance, and the plan carries that entrance: an entrance whose
root the caller chose reaches protected bytes only through the admission owner, and one that
would not is refused here rather than at whichever command happened to offer it.

A unit with an overlap key competes for its concern; a unit without one is unkeyed prose,
delivered `layered` in its labelled layer and the application order, with no winner declared.

A knowledge view prefers one layer's answer and keeps the others beside it with their own
evidence: the layer order chooses what to prefer, never what is true, and sources that disagree
under the same conditions are stated as `knowledge_evidence_conflicts`. A view names every
companion the revisions it cites declare, held or unavailable, and no other source, so a missing
companion stays a qualification rather than dropping out of the answer. A domain model or a form
profile is a structured member of a knowledge source revision; `knowledge.member.prepare` checks
one before it is committed and names a relation to a missing node or a field mapped nowhere.
Clean structure is not semantic validation.

A projection or a member check is a preview: it returns what would reach the role, or what would
be committed, and stores nothing. A question is answered with a view the owner keeps, so
`knowledge.view.open` reopens it by its id unchanged after later revisions; asking writes that
private record and moves no head.

A session is activated explicitly, by a `session_activation` naming the session and the
preparation it receives. A session never activated sends nothing: the composition prepared for
its start records it as selected only (C07), and only an activation returns an activated
`session_routing`, so selecting sources activates nothing. Activation is committed with a
receipt against the session's profile. It projects the preparation's Instructions through the
same admission owner and returns each projection it delivered beside the routing, so every
digest in the routing's `projections` names a record that answer returns.
"""
CONTRACT = "C04"
RECORD_KINDS = ("projection_plan", "role_projection", "knowledge_question",
                "knowledge_view", "session_routing", "session_activation", "knowledge_model",
                "form_profile")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name. A request for an operation states
# its `effect` class and grant `action`, and targets a resource whose id carries one of its
# `targets` prefixes: a projection, a question and its view are the requester's own, a view is
# reopened by its id, a member is checked against the source it will be committed to, and a
# session is activated on its profile.
OPERATIONS = {
    "role.project": {"takes": ("projection_plan",), "returns": ("role_projection",),
                     "effect": "pure_preview", "action": "use", "targets": ("prn",)},
    "knowledge.question.ask": {"takes": ("knowledge_question",),
                               "returns": ("knowledge_view", "source_member"),
                               "effect": "durable_candidate", "action": "read",
                               "targets": ("prn",)},
    "knowledge.view.open": {"takes": (), "returns": ("knowledge_view",),
                            "effect": "pure_preview", "action": "read", "targets": ("viw",)},
    "session.routing.activate": {"takes": ("session_activation",),
                                 "returns": ("session_routing", "role_projection"),
                                 "effect": "owner_commit", "action": "use",
                                 "targets": ("prf",)},
    "knowledge.member.prepare": {"takes": ("knowledge_model", "form_profile"),
                                 "returns": ("knowledge_model", "form_profile"),
                                 "effect": "pure_preview", "action": "contribute",
                                 "targets": ("src",)},
}

SOURCE_NOT_AUTHORIZED = "source_not_authorized"
PROTECTED_ROOT_BYPASS = "protected_root_bypass"
ROLE_PROMOTION_REFUSED = "role_promotion_refused"
ROLE_BODY_UNAVAILABLE = "role_body_unavailable"
APPLICABILITY_UNSTATED = "applicability_unstated"
COMPANION_UNAVAILABLE = "companion_unavailable"
CONDITION_NOT_COVERED = "condition_not_covered"
KNOWLEDGE_EVIDENCE_CONFLICTS = "knowledge_evidence_conflicts"
MODEL_REFERENCE_DANGLING = "model_reference_dangling"
FORM_MAPPING_INVALID = "form_mapping_invalid"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    SOURCE_NOT_AUTHORIZED: "a source this actor is not permitted to project or read",
    PROTECTED_ROOT_BYPASS: "an entrance that would reach protected bytes through a root the "
                           "caller chose, around the admission owner",
    ROLE_PROMOTION_REFUSED: "knowledge or memory offered as behavioural text",
    ROLE_BODY_UNAVAILABLE: "a winning unit whose body this installation does not hold",
    APPLICABILITY_UNSTATED: "a source that states no applicability, kept explicit rather than "
                            "read as applying everywhere",
    COMPANION_UNAVAILABLE: "a declared companion the answer needs and this installation lacks",
    CONDITION_NOT_COVERED: "a condition that can change the answer and no source covers",
    KNOWLEDGE_EVIDENCE_CONFLICTS: "sources that answer one question under the same conditions "
                                  "and disagree; each keeps its evidence, and preferring a "
                                  "layer settles nothing about which is true",
    MODEL_REFERENCE_DANGLING: "a model relation whose endpoint names no node of the model, "
                              "including a node the revision deleted",
    FORM_MAPPING_INVALID: "a form field mapped nowhere the canonical data holds, or data the "
                          "profile could hold only by dropping an exception",
}

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "relation_endpoints_are_nodes": "both ends of every knowledge_model relation name a node of "
                                    "that model",
}
