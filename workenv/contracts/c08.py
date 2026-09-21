"""C08 Team governance: the gaps its operations answer with.

Record kinds: `founding_proposal`, `governing_policy`, `membership_record`, `grant_record`,
`approval`, `lifecycle_action`.

A Team's rules govern that Team's resources and shared operations. They reach no further: a
repository's or a person's own work is not a shared change, and no policy here can reclassify it
as one. Nothing in this contract can widen what a source's own owner permits either.

Independence is countable rather than asserted. A policy cannot be written that counts the
requester, a recorded author, or an agent acting under someone's sponsorship, because those
three exclusions are fixed in the schema; an agent's approval names its sponsor, so the count
can see two voices belonging to one person. Machine validation is recorded as evidence or as a
governed automation route, never as a vote, and elapsed time has no record at all.

Founding is bounded: a Team id that has committed its governance never re-enters founding mode,
and a revised proposal is a new version whose earlier acceptances no longer hold.
"""
CONTRACT = "C08"
RECORD_KINDS = ("founding_proposal", "governing_policy", "membership_record", "grant_record",
                "approval", "lifecycle_action")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name.
OPERATIONS = {
    "team.found": {"takes": ("founding_proposal",),
                   "returns": ("governing_policy", "membership_record", "grant_record")},
    "team.policy.set": {"takes": ("governing_policy",), "returns": ("governing_policy",)},
    "team.membership.change": {"takes": ("membership_record",), "returns": ("membership_record",)},
    "team.grant.change": {"takes": ("grant_record",), "returns": ("grant_record",)},
    "team.approval.record": {"takes": ("approval",), "returns": ("approval",)},
    "team.lifecycle.apply": {"takes": ("lifecycle_action",), "returns": ()},
}

BOOTSTRAP_ALREADY_COMMITTED = "bootstrap_already_committed"
PROPOSAL_SELF_AUTHORIZED = "proposal_self_authorized"
APPROVER_NOT_INDEPENDENT = "approver_not_independent"
APPROVAL_THRESHOLD_UNMET = "approval_threshold_unmet"
DELEGATION_CEILING_EXCEEDED = "delegation_ceiling_exceeded"
GROUP_MEMBERSHIP_ESCALATION = "group_membership_escalation"
SOURCE_RIGHT_NOT_OVERRIDABLE = "source_right_not_overridable"
LAST_OWNER_REMOVAL_REFUSED = "last_owner_removal_refused"
ACCEPTANCES_VOID_AFTER_REVISION = "acceptances_void_after_revision"
SUCCESSION_INCOMPLETE = "succession_incomplete"
CONFIRMATION_IS_NOT_AUTHORIZATION = "confirmation_is_not_authorization"
FINALIZER_UNAVAILABLE = "finalizer_unavailable"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    BOOTSTRAP_ALREADY_COMMITTED: "a Team id re-entering founding after its governance committed",
    PROPOSAL_SELF_AUTHORIZED: "a proposal offered as its own authority to commit",
    APPROVER_NOT_INDEPENDENT: "an approval from the requester, a recorded author, or an agent "
                              "acting under their sponsorship",
    APPROVAL_THRESHOLD_UNMET: "fewer distinct accountable people than the policy requires",
    DELEGATION_CEILING_EXCEEDED: "a grant beyond the scope, actions or depth its parent allows",
    GROUP_MEMBERSHIP_ESCALATION: "privilege widened by adding to a group nobody delegated",
    SOURCE_RIGHT_NOT_OVERRIDABLE: "Team policy applied over a source owner's own rights",
    LAST_OWNER_REMOVAL_REFUSED: "the last required owner, reviewer, recovery capacity or sole "
                                "finalizer removed with no permitted disposition",
    ACCEPTANCES_VOID_AFTER_REVISION: "acceptances of a proposal version that has since changed",
    SUCCESSION_INCOMPLETE: "terminal closure whose ownership, authority or evidence stewardship "
                           "is not settled; naming an intended successor is not settling it",
    CONFIRMATION_IS_NOT_AUTHORIZATION: "a typed confirmation offered in place of the authority "
                                       "the operation requires",
    FINALIZER_UNAVAILABLE: "a shared commit whose Team finalizer cannot be reached; it is "
                           "blocked, never finalized anywhere else, and the same request is "
                           "retried once the finalizer is reachable",
}
