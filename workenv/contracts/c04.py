"""C04 Behavioural sources and domain knowledge: the gaps its operations answer with.

Record kinds: `projection_plan`, `role_projection`, `knowledge_question`, `knowledge_view`,
`session_routing`, `session_activation`.

Two operations share this contract because they share one rule: what reaches a role is decided
by the one admission owner, from exact source revisions, and nothing else is promoted into it.
A projection carries behavioural units only — `projected_unit.source_role` is fixed, so a
knowledge or memory source cannot enter a projection by being listed in one — and a knowledge
view carries a body with the evidence behind it and never the authority to act.

A request arrives through an entrance, and the plan carries that entrance: an entrance whose
root the caller chose reaches protected bytes only through the admission owner, and one that
would not is refused here rather than at whichever command happened to offer it.

A session is activated explicitly, by a `session_activation` naming the session and the
preparation it receives; a session never activated sends nothing and is recorded as selected only.
"""
CONTRACT = "C04"
RECORD_KINDS = ("projection_plan", "role_projection", "knowledge_question",
                "knowledge_view", "session_routing", "session_activation")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name.
OPERATIONS = {
    "role.project": {"takes": ("projection_plan",), "returns": ("role_projection",)},
    "knowledge.question.ask": {"takes": ("knowledge_question",), "returns": ("knowledge_view",)},
    "knowledge.view.open": {"takes": (), "returns": ("knowledge_view",)},
    "session.routing.activate": {"takes": ("session_activation",), "returns": ("session_routing",)},
}

SOURCE_NOT_AUTHORIZED = "source_not_authorized"
PROTECTED_ROOT_BYPASS = "protected_root_bypass"
ROLE_PROMOTION_REFUSED = "role_promotion_refused"
ROLE_BODY_UNAVAILABLE = "role_body_unavailable"
APPLICABILITY_UNSTATED = "applicability_unstated"
COMPANION_UNAVAILABLE = "companion_unavailable"
CONDITION_NOT_COVERED = "condition_not_covered"

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
}
