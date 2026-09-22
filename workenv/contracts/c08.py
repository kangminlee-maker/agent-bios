"""C08 Team governance: the gaps its operations answer with.

Record kinds: `founding_proposal`, `governing_policy`, `membership_record`, `grant_record`,
`approval`, `lifecycle_action`, `membership_invitation`, `membership_verification`,
`membership_consent`, `invitation_cancellation`, `team_state`, `team_profile`,
`stewardship_transfer`, `device_retirement`, `source_rights`.

A Team's rules govern that Team's resources and shared operations. They reach no further: a
repository's or a person's own work is not a shared change, and no policy here can reclassify it
as one. Nothing in this contract can widen what a source's own owner permits either.

Independence is countable rather than asserted. A policy cannot be written that counts the
requester, a recorded author, or an agent acting under someone's sponsorship, because those
three exclusions are fixed in the schema; an agent's approval names its sponsor, so the count
can see two voices belonging to one person. Machine validation is recorded as evidence or as a
governed automation route, never as a vote, and elapsed time has no record at all. A request or
approval is judged under the policy version it names, and one naming a version a later commit
replaced is `policy_superseded`.

Founding is bounded: a Team id that has committed its governance never re-enters founding mode,
and a revised proposal is a new version whose earlier acceptances no longer hold. A nominee's
acceptance is an `approval` of the exact founding request, so a revision leaves it behind. An
unused, incomplete founding can be cancelled; the Team id is then terminal, like a closed Team's.
A founding returns the proposal as sealed. Its commit admits the Team's first members — the founder
by that proposal, each nominee by the proposal and its own acceptance — and writes the authority's
founding epoch with the proposal's finalizer.

Joining is four records and one governed change: the Team's `membership_invitation`, its
`membership_verification` that the actual participant holds the device credential they proved,
the invitee's `membership_consent` bound to both, and the membership change that names the
invitation and the consent. A cancelled or expired invitation admits nobody. A provider claim
admits a member only through an `admission` rule in the Team's policy. A policy's `fresh_checks`
name the Team actions that also need sign-in evidence from a provider in the current access
session. A grant change names the exact revision it replaces; the grant keeps its id.

Every Team commit is sequenced by the Team's one finalizer and moves the Team head, the value its
receipt states; a request that changes the Team expects that head. An approval moves no head,
because it is counted against the exact request it approves, and a head it moved would make that
request stale. A committed finalizer handover writes the successor epoch that fences the old
finalizer.

`team_state` is where a Team stands, and `team_profile` its labels; a rename keeps the Team id.
A `lifecycle_action` travels in the operation whose authority its effect needs
(`LIFECYCLE_ACTIONS`). Duties change hands by `stewardship_transfer`, and a device leaves by
`device_retirement`, each after the unique work it would strand is disposed of. A source's own
rights are `source_rights`, which no Team grant exceeds; a derivative permits nothing its bases do
not, and setting them is a commit to the source that moves its head.
"""
CONTRACT = "C08"
RECORD_KINDS = ("founding_proposal", "governing_policy", "membership_record", "grant_record",
                "approval", "lifecycle_action", "membership_invitation", "membership_verification",
                "membership_consent", "invitation_cancellation", "team_state", "team_profile",
                "stewardship_transfer", "device_retirement", "source_rights")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name. `effect` is the effect class every
# request for it states, `action` the one grant action it needs, and `targets` the id prefixes
# its target may carry.
OPERATIONS = {
    "team.found": {"takes": ("founding_proposal",),
                   "returns": ("founding_proposal", "governing_policy", "membership_record",
                               "grant_record", "team_state", "team_profile",
                               "authority_continuity"),
                   "effect": "owner_commit", "action": "policy", "targets": ("tem",)},
    "team.policy.set": {"takes": ("governing_policy",), "returns": ("governing_policy",),
                        "effect": "owner_commit", "action": "policy", "targets": ("tem",)},
    "team.membership.change": {"takes": ("membership_record",), "returns": ("membership_record",),
                               "effect": "owner_commit", "action": "grant", "targets": ("tem",)},
    "team.membership.leave": {"takes": ("lifecycle_action",), "returns": ("membership_record",),
                              "effect": "owner_commit", "action": "local_profile",
                              "targets": ("tem",)},
    "team.grant.change": {"takes": ("grant_record",), "returns": ("grant_record",),
                          "effect": "owner_commit", "action": "grant", "targets": ("tem",)},
    "team.approval.record": {"takes": ("approval",), "returns": ("approval",),
                             "effect": "owner_commit", "action": "review", "targets": ("req",)},
    "team.lifecycle.apply": {"takes": ("lifecycle_action",), "returns": ("team_state",),
                             "effect": "owner_commit", "action": "policy", "targets": ("tem",)},
    "team.retention.apply": {"takes": ("lifecycle_action",),
                             "returns": ("team_state", "removal_outcome"),
                             "effect": "owner_commit", "action": "retain_delete",
                             "targets": ("tem",)},
    "team.continuation.record": {"takes": ("lifecycle_action",), "returns": ("team_state",),
                                 "effect": "owner_commit", "action": "contribute",
                                 "targets": ("tem",)},
    "team.device.forget": {"takes": ("lifecycle_action",), "returns": (),
                           "effect": "owner_commit", "action": "local_profile",
                           "targets": ("dev",)},
    "team.invitation.issue": {"takes": ("membership_invitation",),
                              "returns": ("membership_invitation",),
                              "effect": "owner_commit", "action": "grant", "targets": ("tem",)},
    "team.invitation.cancel": {"takes": ("invitation_cancellation",),
                               "returns": ("invitation_cancellation", "membership_record"),
                               "effect": "owner_commit", "action": "grant", "targets": ("tem",)},
    "team.verification.record": {"takes": ("membership_verification",),
                                 "returns": ("membership_verification",),
                                 "effect": "owner_commit", "action": "grant",
                                 "targets": ("tem",)},
    "team.consent.record": {"takes": ("membership_consent",), "returns": ("membership_consent",),
                            "effect": "owner_commit", "action": "local_profile",
                            "targets": ("tem",)},
    "team.state.read": {"takes": (),
                        "returns": ("team_state", "team_profile", "governing_policy",
                                    "membership_record", "grant_record"),
                        "effect": "pure_preview", "action": "read", "targets": ("tem",)},
    "team.profile.set": {"takes": ("team_profile",), "returns": ("team_profile",),
                         "effect": "owner_commit", "action": "policy", "targets": ("tem",)},
    "team.stewardship.transfer": {"takes": ("stewardship_transfer",),
                                  "returns": ("stewardship_transfer", "authority_continuity"),
                                  "effect": "owner_commit", "action": "transfer",
                                  "targets": ("tem",)},
    "team.device.retire": {"takes": ("device_retirement",), "returns": ("device_retirement",),
                           "effect": "owner_commit", "action": "transfer", "targets": ("tem",)},
    "source.rights.set": {"takes": ("source_rights",), "returns": ("source_rights",),
                          "effect": "owner_commit", "action": "policy", "targets": ("src",)},
}

# Which `lifecycle_action` effects each operation that takes one carries: the effect decides the
# authority a request needs, so one operation per authority.
LIFECYCLE_ACTIONS = {
    "team.lifecycle.apply": ("archive", "restore", "close", "cancel_founding"),
    "team.retention.apply": ("purge",),
    "team.continuation.record": ("continue_archived",),
    "team.membership.leave": ("leave",),
    "team.device.forget": ("forget_here",),
}

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "derivative_within_base_rights": "a source's rights carry only bases whose rights the store "
                                     "holds and allow derivation, and allow nothing a carried "
                                     "base's rights do not",
    "founding_standing_names_its_founding": "a membership admitted by founding names the "
                                            "proposal whose founder and Team it has; one "
                                            "admitted by nomination names a proposal that "
                                            "nominates its principal and that principal's "
                                            "approval of the founding",
    "grant_revision_keeps_its_grant": "a grant that revises another keeps its id, Team and "
                                      "holder and is its next revision; a grant that revises "
                                      "none is revision 1",
    "consent_matches_its_verification": "a consent's verification names the same invitation and "
                                        "binding as the consent",
    "continuity_follows_its_founding_or_handover": "a Team's founding epoch is epoch 1 of that "
                                                   "Team with the proposal's finalizer; a "
                                                   "successor carries the handover's finalizer, "
                                                   "names its predecessor, fences that epoch's "
                                                   "finalizer and is the next epoch of the same "
                                                   "authority",
    "lifecycle_action_fits_its_operation": "a lifecycle action travels only in an operation "
                                           "whose `LIFECYCLE_ACTIONS` row carries its effect",
}

BOOTSTRAP_ALREADY_COMMITTED = "bootstrap_already_committed"
PROPOSAL_SELF_AUTHORIZED = "proposal_self_authorized"
APPROVER_NOT_INDEPENDENT = "approver_not_independent"
APPROVAL_THRESHOLD_UNMET = "approval_threshold_unmet"
DELEGATION_CEILING_EXCEEDED = "delegation_ceiling_exceeded"
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
POLICY_SUPERSEDED = "policy_superseded"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    BOOTSTRAP_ALREADY_COMMITTED: "a Team id re-entering founding, or its founding cancelled, "
                                 "after its governance committed",
    PROPOSAL_SELF_AUTHORIZED: "a proposal offered as its own authority to commit",
    APPROVER_NOT_INDEPENDENT: "an approval from the requester, a recorded author, or an agent "
                              "acting under their sponsorship",
    APPROVAL_THRESHOLD_UNMET: "fewer distinct accountable people than the policy requires",
    DELEGATION_CEILING_EXCEEDED: "a grant beyond the scope, actions or depth its parent allows",
    SOURCE_RIGHT_NOT_OVERRIDABLE: "an action a source's own rights, or a carried base's, do not "
                                  "allow: a derivation, export or use, or a Team grant or policy "
                                  "applied past them; reading alone allows neither derivation nor "
                                  "export",
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
    TEAM_ARCHIVED: "a new mutation, adoption or piece of work on an archived Team; a "
                   "continuation naming the existing work it continues and a governed restore "
                   "are what proceed",
    TEAM_TERMINAL: "an operation on a Team whose closure or cancelled founding is terminal; "
                   "nothing reopens it, and the same name needs a new Team id",
    GRANT_NOT_HELD: "an action the actor holds no current grant for in that scope: never issued, "
                    "expired, revoked or suspended",
    CLAIM_NOT_ADMITTED: "a verified provider claim that no admission rule in the Team's policy "
                        "names; a login, an e-mail address or a workspace membership admits "
                        "nobody by itself",
    POLICY_SUPERSEDED: "a request or approval naming a Team policy version that a later committed "
                       "version has replaced; it is sealed again under the current policy",
}
