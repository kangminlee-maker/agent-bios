---
created_at: 2026-09-14T01:32:25+09:00
head: 35c75ca
kind: design
status: proposed-complete-team-lifecycle
amends:
  - 2026-09-13T2336--35c75ca--studio-governance-design.md
  - 2026-09-13T2338--35c75ca--studio-complete-screen-contracts.md
  - 2026-09-14T0127--35c75ca--github-recommended-setup-option.md
---

# Team CRUD and creation workflow

## Coverage correction and purpose

Prior documents specified founding authority, independent review, connection
preferences and a Team/access destination. They did not provide a complete
Team CRUD flow or detailed connected screens. This record completes that design
scope: creation, discovery/read, updates, membership/ownership changes, archive,
restore, leaving, local removal, logical termination and governed data removal.
These are design contracts, not implemented production capabilities.

A Team is the basic unit through which workers select, share and continue work
environments. Its identity, membership, governance and lifecycle must survive a
display-name change, device loss, repository replacement or network partition.
Every operation preserves the source owners' rights and the distinction between
the Team, its environments, and actual worker contexts.

## Minimal state model

The stable Team ID is allocated once. Name, purpose, verified identity bindings,
governance/configuration revisions and lifecycle state are separately identifiable.
A same-name recreation has a new ID. A GitHub account, repository URL, path or
branch is not the Team identity.

Keep these axes separate:

| Axis | States or evidence |
| --- | --- |
| Team lifecycle | Initial setup, active, archived, permanently closed |
| Governance | Founding proposal pending, qualified/confirmed, required capacity unavailable |
| Membership | Invited, acceptance pending confirmation, member, left/revoked |
| Local presence | Not enrolled, verified local copy, forgotten locally; retention/control state may have separate required homes |
| Connection | P2P available/preparing; GitHub not selected, pending, connected, failed/unavailable |
| Working environment | None yet, draft, published, adopted; each actual task retains its own state |

Transport and cleanup have their own in-progress/unknown/partial operation
states. Do not make a Team lifecycle field writable through a generic form.
The authority executes named transitions with their preconditions and receipts.

## Team management UI

The app-level Team list precedes entry into one Team's Studio. It lists only
authorized Team metadata, allows name/ID search and lifecycle filtering, and
offers `팀 만들기` and `기존 팀 참여`. Opening a Team changes browsing context,
not a running task or membership. A pending invitation can expose its own
permitted invitation summary without exposing the Team's private sources.

Team detail uses five sections: `개요`, `구성원·기기`, `설정`, `변경 요청`,
and `종료·로컬 관리`. Its header shows stable context, lifecycle and the
observed configuration revision. Overview separates governance readiness,
environment adoption, local retention and GitHub connection. Work-environment
navigation continues into the previously designed Studio content areas.

Editors preserve drafts when switching sections. Each input names its scope;
error messages attach to the affected field. Review screens show exact before/
after values, policy, actor, eligible approvals, target acceptance if needed,
base revision and expected consequences. Status, authorization and unknown
results are never communicated by color alone.

## Create: four-step wizard

| Step | Inputs and presentation | Validation and result |
| --- | --- | --- |
| 1. Team identity | Name, optional purpose; authenticated founder shown separately from professional role; stable ID allocated for the setup operation | Name is a label, not a uniqueness/authorization claim. Repeated submission resumes the same setup; unauthenticated identity cannot found a trusted Team. |
| 2. Storage and connectivity | P2P foundation fixed; `GitHub 연결 (추천)` initially selected where permitted; `P2P만 사용`; chosen repository/scope; Internet/internal/periodic-transfer profile; offline operating ceiling where needed | No automatic connection/upload. GitHub cancellation/failure permits explicit connect-later or P2P-only completion. A forbidden external route is disabled by named policy. Verify actual local prerequisites separately. |
| 3. Initial responsibilities | Shared review profile by default or explicit solo profile; founder's exact grants; initial reviewer and recovery-custodian nominations; logical finalizer and device/store location | A nominee is not yet a member. A second device/agent of the founder is not an independent human. Named roles may share a person only when the policy allows it. Missing reviewer does not silently select solo. |
| 4. Review and create | Exact Team configuration, founding grants, source/export boundaries, external actions requested, pending connections/acceptances, local custody coverage | Commit the local/authenticated Team setup identity and signed founding proposal with a request-bound receipt. Show remaining steps rather than a single false completion badge. |

Team creation does not automatically publish or adopt a work environment, activate
a task, send messages, create a remote repository, or make other devices retained
copies. The next action after Team creation is governance completion where needed,
then creating/selecting the first environment through its own flow. Zero
environments and one confirmed retained copy are legitimate initial facts.

### Founding without a circular approval requirement

Founding is a narrow initial-governance protocol, not ordinary privilege expansion:

1. The authenticated founder seals an initial proposal containing Team ID,
   policy, their exact founding grants, nominees' proposed grants, finalizer
   binding and recovery responsibilities. It creates a Team in initial setup.
2. An independently identified nominated human verifies the Team/root and accepts
   that exact proposal. Acceptance is an attributable statement, not yet proof
   that all membership changes committed or a device downloaded the content.
3. The designated authority checks the current founding-proposal revision,
   identity/independence, required acceptances and capabilities, then commits
   the initial governance checkpoint. Protected Team operations become available
   subject to their normal permissions.

Before step 3, the founder can maintain setup, local drafts and named invitation
artifacts. The founder may replace nominees or revise the initial proposal only
by creating a new revision and invalidating old pending acceptances. Stale
offline acceptance cannot complete a different proposal. The authority serializes
competing attempts for the same Team ID.

Once initial governance is committed, that Team ID can never return to founding
mode. Reviewer replacement and profile downgrade use the established policy.
Solo creation is explicitly self-founded/self-reviewed; it does not fabricate
an independent approval. The bootstrap exception cannot be used to escape a
governance problem in an already established Team.

### Invitation, joining and another device

Creating an invitation artifact is separate from sending a message. An existing
Team invitation binds stable Team/authority identity, exact proposed recipient
and grants, expiry and a single request. Its recipient verifies identity/trust
and accepts; the authority then applies the governed membership change. Until
that receipt is known, show acceptance pending confirmation. Offline signed
invitation/acceptance packages follow the same protocol.

An existing member enrolling another device proves their existing membership
and the new device identity, imports permitted sources/control evidence, and
records that device's actual retained set. This does not create another human
member, reviewer vote or active finalizer. Joining never creates a second Team
because its name matches an invitation.

## Read: discover and inspect

List filters distinguish active, initial setup, archived and closed metadata
where authorized. Empty list, offline partial knowledge, access denial and a
failed query are separate states. No unauthorized titles/counts are disclosed.
Pagination/search retain the Team visibility scope and result qualification.

Detail shows observed version/checkpoint, members and grants the viewer may
inspect, adopted environments, peer custody evidence, connection status and
pending requests. Reading does not adopt, approve, join, copy private material
or activate a task. Historical/closed records expose only retained permitted
metadata and evidence; closing a Team does not grant everyone audit access.

## Update: typed changes rather than one unrestricted PATCH

| Change | Permission and review | Preserved facts |
| --- | --- | --- |
| Display name/purpose | Metadata-management grant; exact conditional update; no extra review required by the proposed default unless Team policy adds it | Team ID, source ownership, grants, environment identities and task pins |
| GitHub connect/replace/disconnect | Integration-management grant and review where storage/export scope changes; verified target identity; staged effect review | P2P remains operable; old repository is not deleted; integration access does not grant source rights |
| Offline/exchange/custody policy | Governance grant and existing-policy review; compare affected capabilities and source ceilings | Cannot relax underlying source requirements or turn a planned copy into a verified copy |
| Members/grants/review rules | Governed exact request, relevant independent review and recipient acceptance where required | No self-grant amplification; memberships, direct source grants and delegated agent rights remain distinct |
| Owner/recovery custodian | Current-policy authorization, successor consent and capability checks | At least the required governance/recovery path survives |
| Logical finalizer/device | Governed authority transfer with successor readiness, exact handoff evidence and old-writer fencing | Copying the journal/key to a second device does not authorize two active issuers |

Ownership and finalizer transfer are separately selected effects even if one
review combines them. A person leaving can require both transfers. Reviewer
eligibility follows the current policy, including exclusion of requester/authors
and beneficiaries where the grant policy requires it. If the remaining actors
cannot satisfy review or custody requirements, resolve that through normal
governance/recovery before executing; do not waive it during transfer.

Team connection settings are defaults for its environments, not rights over
their sources. Source-specific restrictions and explicitly different routes
remain visible. Changing a transport endpoint does not rewrite immutable
environment contents. Changes affecting materialization requirements invalidate
the corresponding preparation evidence.

External provisioning follows a separate durable operation journal. Bind setup
and repository identity before remote mutation. Unknown creation results are
reconciled under the same request, never retried with a new guessed name. An
already-created repository remains associated with the pending setup; cleanup
is explicit and separately authorized. Disconnecting one Team never revokes a
shared account credential or deletes another Team's repository implicitly.

## Delete and related lifecycle actions

| Action | Exact meaning | Important preconditions/effects |
| --- | --- | --- |
| Archive Team | Reversibly stop ordinary Team mutations, new adoptions and new Team task starts; retain permitted historical reads | Current governance review/commit. Existing tasks may finish only under the explicitly applicable continuation policy; delivered text is not recalled. |
| Restore Team | Resume permitted Team operation with the same ID | Current authorization and governed review. Re-evaluate source access, custody, host readiness and expired grants; nothing is automatically revived merely by restoration. |
| Leave Team | End this principal's membership and dependent delegations | Do not remove the last required owner, reviewer/recovery capacity or sole finalizer. Independent grants require their own disposition. Other members and Team identity remain. |
| Forget on this device | Remove this installation's permitted retained Team view/data | Preserve/transfer or explicitly dispose of unique drafts/outboxes and active authority state. Membership and other replicas remain unchanged. Keep required anti-replay controls outside ordinary cache removal. |
| Permanently close Team | Terminal logical deletion of this stable Team identity for future Team operations | Review exact closure plan against current state. Commit a durable identity-level closure marker. Reusing the name requires a new Team ID and enrollment. |
| Purge retained material | Separately governed removal of identified owned data/copies | Source ownership, retention and actual replica outcomes govern it. Report confirmed, denied, unreachable and unknown removals separately. |

Archived Teams still permit authorized restore, permanent closure, membership/
authority repair and necessary retention operations. The archive policy must not
disable the very governance route required to restore it. A closed Team permits
only retained evidence access and narrowly authorized cleanup/recovery of that
evidence; it cannot resume as an active Team.

The proposed destructive flow is **archive → inspect closure plan → request
permanent closure → current-policy approval → authority commit**. Active-Team
closure first establishes the governed no-new-work state. A closure plan lists
Team-owned material needing a surviving steward, separate purge or allowed
retention, outstanding operations, relevant custody obligations and the remote
repository disposition. Required ownership/authority disposition must complete
before final closure. Preserve unresolved local work under its governing policy;
an unreachable peer is not proof that it has no unshared work.

The UI asks for the exact Team name/identity on the final destructive review,
but typed confirmation is not authorization. Show GitHub repository retention as
the normal independent outcome. Optional repository archival/deletion is a
separate explicitly scoped external operation, with separate permission and
receipt. Team closure is not rolled back because a subsequent cleanup failed.

## P2P, concurrency and recovery invariants

All accepted metadata, configuration and lifecycle changes are portable records
under the existing authority/checkpoint contract. Peers apply verified closure,
revocation and deletion controls before admitting old content as usable. An old
disk, old package, same repository name or same Team name cannot resurrect a
closed Team. A still-disconnected peer cannot know the closure until it receives
it or its offline allowance ceases; do not promise immediate global shutdown.

Every mutation binds the actor, exact operation/payload, Team ID, relevant prior
revision, policy and request ID. Re-evaluate permissions and lifecycle at commit.
Concurrent update/leave/transfer/archive conflicts preserve candidates and require
fresh review of any changed effect. Do not silently carry an approval to a
different payload or automatically restore a stale Team state.

Unknown results are recovered with the same operation receipt. Cancel reports
whether pending work stopped, already committed, or remains uncertain. Physical
cleanup across peers/GitHub is not a cross-provider atomic transaction. Track
its individual results; retain the minimum permitted closure/control evidence
needed to reject replay. If even that evidence cannot be retained, disclose the
policy conflict instead of promising both total erasure and replay prevention.

## Validation scope

The accompanying mockup exercises Team CRUD through fictional identities and
local state transitions. It must not send invitations, authenticate to GitHub,
create real repositories, enroll devices, delete files or claim real authority
checks. Production acceptance requires the owning provider to enforce these
rules across UI, CLI and MCP calls, including bypass and crash/retry tests.

The lifecycle scenario companion enumerates successful and material failure
cases. UI coverage does not prove runtime availability, identity independence,
durable atomicity, deletion propagation or model compliance. Existing shipped
Instructions Studio remains separate until actual integration is implemented.
