"""C08 Team governance: the gaps its operations answer with.

Record kinds: `founding_proposal`, `governing_policy`, `membership_record`, `grant_record`,
`approval`, `lifecycle_action`, `membership_invitation`, `membership_consent`,
`invitation_cancellation`, `team_state`, `team_profile`, `stewardship_transfer`,
`device_retirement`, `source_rights`.

A Team's rules govern that Team's resources and shared operations. They reach no further: a
repository's or a person's own work is not a shared change, and no policy here can reclassify it
as one. Nothing in this contract can widen what a source's own owner permits either.

Independence is countable rather than asserted. A policy cannot be written that counts the
requester, a recorded author, or an agent acting under someone's sponsorship, because those
three exclusions are fixed in the schema; an agent's approval names its sponsor, so the count
can see two voices belonging to one person. Machine validation is recorded as evidence or as a
governed automation route, never as a vote, and elapsed time has no record at all.

Founding is bounded: a Team id that has committed its governance never re-enters founding mode,
and a revised proposal is a new version whose earlier acceptances no longer hold. A nominee's
acceptance is an `approval` of the exact founding request, so a revision leaves it behind. An
unused, incomplete founding can be cancelled; the Team id is then terminal, like a closed Team's.

Joining is three records and one governed change: the Team's `membership_invitation`, the
invitee's `membership_consent` bound to the device credential they proved and to the Team's
out-of-band verification, and the membership change that names both. A cancelled or expired
invitation admits nobody. A provider claim admits a member only through an `admission` rule in
the Team's policy, and a group's membership is either an approved member set with current
evidence or dynamic membership delegated to one named provider connection.

`team_state` is where a Team stands, and `team_profile` its labels; a rename keeps the Team id.
Duties change hands by `stewardship_transfer`, and a device leaves by `device_retirement`,
each after the unique work it would strand is disposed of. A source's own rights are
`source_rights`, which no Team grant exceeds; a derivative permits nothing its bases do not.
"""
CONTRACT = "C08"
RECORD_KINDS = ("founding_proposal", "governing_policy", "membership_record", "grant_record",
                "approval", "lifecycle_action", "membership_invitation", "membership_consent",
                "invitation_cancellation", "team_state", "team_profile", "stewardship_transfer",
                "device_retirement", "source_rights")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name.
OPERATIONS = {
    "team.found": {"takes": ("founding_proposal",),
                   "returns": ("governing_policy", "membership_record", "grant_record",
                               "team_state", "team_profile")},
    "team.policy.set": {"takes": ("governing_policy",), "returns": ("governing_policy",)},
    "team.membership.change": {"takes": ("membership_record",), "returns": ("membership_record",)},
    "team.grant.change": {"takes": ("grant_record",), "returns": ("grant_record",)},
    "team.approval.record": {"takes": ("approval",), "returns": ("approval",)},
    "team.lifecycle.apply": {"takes": ("lifecycle_action",), "returns": ("team_state",)},
    "team.invitation.issue": {"takes": ("membership_invitation",),
                              "returns": ("membership_invitation",)},
    "team.invitation.cancel": {"takes": ("invitation_cancellation",),
                               "returns": ("invitation_cancellation", "membership_record")},
    "team.consent.record": {"takes": ("membership_consent",), "returns": ("membership_consent",)},
    "team.state.read": {"takes": (),
                        "returns": ("team_state", "team_profile", "governing_policy",
                                    "membership_record", "grant_record")},
    "team.profile.set": {"takes": ("team_profile",), "returns": ("team_profile",)},
    "team.stewardship.transfer": {"takes": ("stewardship_transfer",),
                                  "returns": ("stewardship_transfer",)},
    "team.device.retire": {"takes": ("device_retirement",), "returns": ("device_retirement",)},
    "source.rights.set": {"takes": ("source_rights",), "returns": ("source_rights",)},
}

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "derivative_within_base_rights": "a source's rights carry only bases whose rights the store "
                                     "holds and allow derivation, and allow nothing a carried "
                                     "base's rights do not",
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
INVITATION_NOT_OPEN = "invitation_not_open"
TEAM_ARCHIVED = "team_archived"
TEAM_TERMINAL = "team_terminal"
GRANT_NOT_HELD = "grant_not_held"
CLAIM_NOT_ADMITTED = "claim_not_admitted"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    BOOTSTRAP_ALREADY_COMMITTED: "a Team id re-entering founding, or its founding cancelled, "
                                 "after its governance committed",
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
    INVITATION_NOT_OPEN: "a consent or admission naming an invitation that was cancelled, has "
                         "expired, has already admitted someone or was issued by another Team; "
                         "a late consent does not revive it",
    TEAM_ARCHIVED: "a new mutation, adoption or piece of work on an archived Team; the "
                   "continuation its policy names and a governed restore are what proceed",
    TEAM_TERMINAL: "an operation on a Team whose closure or cancelled founding is terminal; "
                   "nothing reopens it, evidence recovery does not revive it, and the same name "
                   "needs a new Team id",
    GRANT_NOT_HELD: "an action the actor holds no current grant for in that scope: never issued, "
                    "expired, revoked or suspended, or held through a group whose membership "
                    "evidence no longer covers them",
    CLAIM_NOT_ADMITTED: "a verified provider claim that no admission rule in the Team's policy "
                        "names; a login, an e-mail address or a workspace membership admits "
                        "nobody by itself",
}
