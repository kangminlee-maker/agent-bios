---
created_at: 2026-09-14T01:35:17+09:00
head: 35c75ca
kind: design
status: proposed-team-lifecycle-contracts
depends_on:
  - 2026-09-13T2336--35c75ca--studio-governance-design.md
  - 2026-09-13T2338--35c75ca--studio-complete-screen-contracts.md
  - 2026-09-14T0107--35c75ca--peer-replicated-team-checkpoints.md
  - 2026-09-14T0114--35c75ca--peer-default-with-github-sync.md
  - 2026-09-14T0127--35c75ca--github-recommended-setup-option.md
---

# Team lifecycle: complete operations and UX acceptance

Team creation, reading, updates, and retirement are in scope. The complete
GitHub-free route uses the local/P2P provider, its trust bootstrap, governed
operations, and permitted peer/package exchange. A GitHub account or repository
is an optional connection, never the Team's identity or root of authority.

This record specifies behavior for the lifecycle design and simulated UI. It
does not establish that a Team/P2P/GitHub runtime provider is implemented.

## Creation checklist

Use four steps. The user can return to earlier steps without losing the draft.
A draft is not yet a created Team. Existing valid authentication can be reused;
the UI must not ask the user to re-authorize an already-authorized step.

| Step | Minimum fields and display | Required boundary |
| --- | --- | --- |
| 1. Team basics | Display name; short purpose/scope; identified founding principal; local storage location as an advanced setting. Separate Create new Team from Join existing Team. | Stable Team ID is allocated by the supported creation operation, not derived from the name, GitHub account, organization label, or repository URL. Naming a Team does not join an existing one. |
| 2. Storage and connection | P2P/local storage foundation; inherited network/source restrictions; `GitHub 연결 (추천)` initially selected for eligible scopes; visible `P2P만 사용`. GitHub flow names authenticated account, exact repository, requested capability and permitted exchange scope. | Selecting the recommendation alone causes no connection, repository creation, scan of local private sources, or upload. Explicitly forbidden scopes select the permitted P2P route. Authentication, repository binding and content transfer are distinct operations. |
| 3. Initial responsibility and policy | Founding owner; operating profile; initial finalization holder; reviewer/recovery assignments or clearly pending enrollment; resulting action checklist. | Shared Team is not silently converted to self-review when a second eligible person is absent. Initial authority is recorded as founding/bootstrap authority, not independent approval. Devices and service accounts do not become additional independent people. |
| 4. Review and create | Name/ID candidate, owner/profile, exact bootstrap grants/policy, local destination, connection state and planned external effects, pending conditions; explicit Create action. | A sealed request binds the creation effect. Lost results resume that request. Optional connection failure does not repeat Team creation or delete an externally created repository. |

Source policy is evaluated before presenting an actionable external connection.
An unknown policy is not an automatic export grant. A closed-network choice can
create and operate the Team through P2P even with GitHub never configured.
If a user deliberately selects P2P only, retain that preference and do not
repeatedly reopen GitHub setup.

After successful creation, show separate facts:

- **Team:** created under its stable identity and initial control checkpoint.
- **Governance:** ready or pending the named enrollment/recovery conditions.
- **Storage:** local control data retained; actual peer custody coverage.
- **GitHub:** not selected, configured, pending, unavailable, or verified for the
  named principal and repository. One worker's authorization is not every
  member's repository access.
- **Environment:** none until an explicit environment-creation operation.

With one device and no environment, say that the **Team control checkpoint** has
one retained copy. Do not display three copies or imply an environment is
recoverable before it exists. Primary next actions are Create first environment
and Enroll/invite members. Creating an environment draft may be permitted while
protected publication/adoption remains blocked by incomplete shared governance.

## Lifecycle operation matrix

Every receipt below binds the actual actor, Team/resource ID, exact request,
base/control version, policy evidence, committed result and operation ID. An
unknown outcome is reconciled before retrying. Invitation delivery, approval,
execution and peer-retention acknowledgment are separate evidence.

| Operation | Actor and object | Preconditions / minimum input | State effect and receipt | Failure or pending result | UX acceptance |
| --- | --- | --- | --- | --- | --- |
| Create | Identified founder; new Team genesis | New-Team route; supported local/provider identity; name/purpose; explicit bootstrap policy and storage choice | One stable Team identity, founding authority and control checkpoint; creation receipt | Invalid identity/storage, stale request, or unknown result preserves the draft; optional connection may remain pending | Double-click or response loss creates one Team; P2P-only needs no GitHub account |
| Read/list/inspect | Authorized principal; Team and permitted related state | Read permission or appropriately limited local association metadata; selected view | No mutation; display exact observed control/adoption state and qualifications | Denied, unavailable, archived, closed and unknown-current-state remain distinct; no restricted counts/names leak | Inspecting another Team changes neither active task nor membership |
| Update name/purpose/default preferences | Scoped Team operator; Team metadata | Existing Team ID; current base; changed fields and meaning/effect preview | New metadata/control revision; identity unchanged; update receipt | Concurrent update preserves both input and current state for review | Rename is reflected in the selector without duplicating the Team, rewriting historical labels, or changing task pins |
| Copy as a new Team | Authorized creator; permitted template material | Source Team/template ID and revision; allowed copy/export scope; new name/owner | New Team ID and fresh authority; provenance links to the permitted template | Prohibited source copying or unavailable required material blocks that part; no copied authority | Copy does not carry memberships, private keys, credentials, accepted grants, or the original Team's authority |
| Invite and join | Eligible membership issuer, then invited principal; membership proposal | Exact Team ID/trust origin, recipient, offered grant ceiling, expiry/conditions; recipient acceptance and identity verification | Pending invitation → verified enrollment and permitted initial grants; invite/enrollment receipts | Expired/revoked invitation, mismatched Team, unverified recipient, or changed policy prevents membership; sending alone adds no eligible reviewer | Offline invitation/package enrollment works; typing an email or matching a Team name does not join |
| Enroll a device/peer | Existing eligible member/custodian; identified device and permitted storage subscription | Existing person identity; new device/storage generation; Team trust verification; authorized scope and custody choice | Enrolled device; subsequently verified local content and retention receipt | No provider route, insufficient space, failed verification or missing bodies leaves custody incomplete | A second device is another storage peer, not another independent human approval |
| Retire or replace a device | Eligible device/custody operator; specific device generation | Known custody/outboxes, credential scope and replacement/recovery plan | Device association retired; affected custody acknowledgments qualified; replacement has a new storage generation | Unique unreconciled work or last required retained material produces a recovery condition; offline removal remains pending | An old acknowledgment is not counted as proof that the replacement device has the bytes |
| Add/remove members or change grants | Scoped issuer/executor; membership and named grants | Current authorization ceiling; exact recipient/actions/resource/expiry; policy-required review | Governed membership/grant change with effective-rights result | Insufficient authority, self-expansion, stale eligibility, or broken governance continuity blocks the protected change | Removing membership revokes Team-derived permissions; independent direct grants remain visible and need their own treatment |
| Update governance policy | Eligible governance actors; versioned policy | Current old policy; proposed reviewer/independence/action rules; affected pending requests; valid resulting continuity | New policy/control revision and receipt; pending requests re-evaluated | Proposed weaker policy cannot approve itself; absent eligible reviewer keeps request pending | Shared→solo is a governed policy change, not an ordinary creation-profile toggle |
| Transfer ownership/finalization | Current authorized custodian and accepted eligible successor; exact governance/head responsibility | Named successor, accepted scope, policy approval, recovery capability, current finalizer/control state and transition plan | Governed handover/control epoch; exact roles and active issuer transition recorded | Missing successor acceptance, unresolved in-flight finalization, or loss of required recovery/reviewer path blocks completion | Removing the outgoing owner cannot create two independent finalizers or erase outstanding authoritative operations |
| Leave Team | Current member, with required governance/custody handling; own membership | Identify remaining ownership/reviewer/custody responsibilities and unique work; confirm intended membership effect | Leave/revocation receipt; future Team-derived rights removed; historical records preserved | Last required owner/reviewer/recovery path or unique custody requires transfer, recovery or closure path | Leave is not local deletion, Team closure, deletion of personal derivatives, or proof that every separate grant disappeared |
| Forget on this device | Local operator; this device's Team association, cache and allowed retained copies | Local retention/custody obligations and unique drafts/outboxes assessed; explicit objects to remove | Local association/data removed as allowed; local removal receipt; shared Team unchanged | Retained-only copy, unresolved local work or mandatory retention exposes a concrete handoff/retention remedy | Another peer's Team remains active; forgetting cannot revoke remote membership or delete the GitHub repository |
| Archive | Authorized Team operator; Team lifecycle state | Exact Team/base; preview of inhibited actions and allowed read/admin activity; current policy | Archived under same Team ID; archival receipt; data/control lineage retained | Stale head or unavailable authority leaves Team unchanged | Archived Team remains findable in an archive filter; new shared work is unavailable as declared, while history remains qualified and readable where permitted |
| Restore archived Team | Eligible Team governance actors; archived Team | Same ID; current control/policy; access and required custody rechecked | New control revision restores supported active operations; restoration receipt | Closed Team, missing authority or unresolved controls cannot be treated as an ordinary restore | Restore does not create a duplicate Team, re-enable revoked grants, or reactivate old task contexts |
| Permanently close Team | Authorized governance/retention actors; Team identity and owned resources | Exact closure request, applicable approvals, external adopters/source dependencies, custody/outboxes, retention/deletion outcomes | Terminal Team tombstone/control record; protected future Team mutations disabled; per-owner retention/removal receipts | Unknown/partial physical deletion is reported separately; other owners' sources and repositories are not implicitly removed | A closed Team cannot be restored by importing an old checkpoint; a later Team with the same display name has a new ID |
| Attach GitHub | Authorized connection operator; Team connection profile and exact repository | Explicit account/repository selection, supported capability, allowed source/export scope; distinguish existing binding from create-new-repository request | Connection profile receipt; future permitted exchange route available; upload only within an explicitly authorized exchange | Canceled/failed/unknown connection leaves the Team and P2P usable; unrelated repository contents are not adopted as Team state | Recommended selection alone uploads nothing; repository access does not grant Team governance |
| Replace GitHub repository | Authorized connection operator; old and new bindings | Exact old/new repository IDs; authorization/export compatibility; accepted checkpoints and unique outbox/recovery coverage; pending old operations reconciled | New binding after reviewed transition; existing Team/content IDs preserved; both transition outcomes retained | Missing unique data, unknown old write or incompatible destination keeps replacement pending | The old repository is neither overwritten nor deleted; a changed repository does not create or rename the Team |
| Disconnect GitHub | Authorized Team connection operator; selected binding | Identify pending transfers, unique remote/outbox material and retained P2P recovery coverage; reviewed scope | Future Team exchange through that binding stops; local/P2P state and receipts remain | Pending/unknown remote writes remain recoverable; insufficient retained coverage is disclosed and handled before route retirement | Disconnect works without closing the Team, deleting the repository, or revoking a shared account connection used by another Team |

“Archive” must name its operational effect in the preview. The recommended
baseline prevents new shared releases/adoptions and new Team task preparation,
while permitting authorized historical reading and necessary governance,
access-restriction, restore, or closure operations. Existing delivered context
is not erased; its continued use remains governed by source/Team policy. Local
drafts and observations can remain preserved as unaccepted work.

## Bootstrap and last-owner invariants

Shared governance needs a bounded founding route. Otherwise the initial
independent reviewer cannot be enrolled because the policy already demands the
reviewer who does not yet exist.

The creation request therefore contains an explicit initial grant/policy plan.
The founding operation establishes that plan as genesis authority; it is marked
self-founded, not independently approved. Offered initial assignments remain
pending until the named principals accept and qualify. Completing that exact
bootstrap plan is a distinct supported transition. It cannot become a reusable
exception for subsequent privilege expansion or a way to add arbitrary future
reviewers without the governing policy.

The founding plan also needs a bounded abandonment operation. Before shared
bootstrap completes, the founder may close an otherwise unused Team when no
other accepted member/grant, adopted environment, or authoritative shared
decision relies on it. Pending invitations are withdrawn, unique drafts receive
an explicit retention/discard outcome, and the Team ID is retired with a control
record. This is recorded as founding cancellation, not independently approved
ordinary Team deletion. It does not delete a repository or undo an unknown
external operation. Once those preconditions no longer hold, use normal governed
closure. A failed setup must not trap its founder behind the missing reviewer.

The UI identifies which actions are usable now and which await completion.
Reviewer, recovery custodian and finalization holder are separate duties, even
when a policy allows one eligible person to hold several. A pending invitation
is not an accepted assignment. Two accounts or devices under one accountable
person do not satisfy an independence requirement.

Before ownership, member, or device removal, evaluate the **resulting** authority
and recovery paths. A count of owners is insufficient if the remaining person
cannot perform recovery or no eligible independent reviewer remains. Offer the
actual permitted routes: complete a transfer/enrollment, invoke an established
recovery process, archive, or close. Do not invent a client-side emergency owner
or silently weaken policy to make the button work.

Authority backup is not another active finalizer. Peer packages must not clone
private signing keys or mutable finalization/voting state into competing active
instances. The transfer receipt records the governed authority transition;
copying a storage checkpoint alone cannot enact it.

## Team connection versus environment composition

A Team connection profile supplies an allowed default transport/destination.
An environment records whether it uses that profile or another explicitly
permitted connection. Inheriting a connection does not inherit credentials or
broader export rights. Each recipient still needs its own effective access.

Changing the Team default affects future exchange/preparation according to that
binding; it does not rewrite published environment editions, source ownership,
accepted decisions, or active task pins. An explicitly pinned alternative
connection is not silently replaced. Source-specific external-transfer limits
remain effective even when the Team owns the destination repository.

Do not infer Team membership from GitHub organization membership, repository
write access, matching account names, or a repository containing familiar files.
Attaching an existing repository requires verifying the intended Team/namespace
binding. An unrelated repository can be selected as an import source only through
the separate permitted import/review route; it is not automatically relabeled.

## Weekly/offline operation and retirement

Local drafting, reading and P2P-only Team operations follow their declared
offline/authority conditions. A weekly connection is a chance to reconcile, not
a promise that every peer has current control state. Display the last verified
control/checkpoint and actual pending work. No automatic sync schedule or public
listener is created merely by selecting the recommended option.

Creation and each lifecycle mutation use a durable request identity. Reopening
the wizard or management panel resumes the request and queries its outcome.
Changing the sealed request's effect requires a new request; it must not reuse
an earlier approval or completion receipt. Cross-provider effects remain
separate: Team creation can succeed with GitHub pending, and a repository
operation can succeed while its acknowledgment is lost.

Known closure/tombstone/control records are evaluated before exposing imported
older checkpoints as current. An old offline peer cannot resurrect a known
closed Team by advertising an earlier head, resetting its local storage, or
renaming the Team. Restoring an archived Team uses a new authorized control
revision; restoring local bytes is not that operation.

A device that has not received a later closure cannot be promised instant
knowledge of it. Joining/recovering a device must establish the required trusted
control continuity and offline-use qualifications. If those cannot be
established, protected current operations remain unverified or blocked. Do not
accept an old package as a fresh trust bootstrap simply because its signature
is valid. Physical deletion at unreachable peers stays pending/unconfirmed;
logical Team closure is not proof that every copy has been erased.

## Required integrated journeys

1. Create with GitHub recommended but never connect: no upload occurs. Choose
   P2P only and finish with one real local control copy, governance pending when
   appropriate, and no environment yet.
2. Create using an explicit closed-network restriction: GitHub is unavailable
   for that scope; local creation, offline enrollment and the permitted peer
   route remain complete.
3. Lose the Create response and reopen: recover the same Team ID and receipt.
   A pending connection is resumed independently, without a duplicate Team.
4. Complete the bounded shared bootstrap with a verified second person. Create
   an environment draft, review/publish/adopt through the resulting policy, and
   retain real copies on additional enrolled devices.
5. Rename the Team and replace its GitHub repository: Team/source identities,
   historical records and task pins remain intact; unrelated remote contents
   and the old repository are preserved.
6. Attempt to remove the final usable owner/recovery path: no silent removal;
   complete a supported handover or closure route. A second device cannot stand
   in for the missing independent reviewer.
7. Compare local forget, leave, archive, restore and permanent close in the UI.
   Each review names different objects and effects. Only archive has the
   ordinary same-Team restore path.
8. Close a Team while one peer is offline, then import its old package: a peer
   with the tombstone rejects resurrection, while remote physical deletion
   remains an honestly pending outcome.
9. Disconnect GitHub after proving permitted local/peer recovery coverage:
   ordinary P2P operation continues, the repository remains present, and another
   Team's use of the same authenticated account is unaffected.
10. Copy a permitted Team template: the copy receives a new identity and fresh
    founding authority, with no inherited members, credentials or private keys.

The prototype should demonstrate these state distinctions with labeled fixtures.
Mock identities, authorization results, copy counts and receipts are simulation
evidence only. Runtime acceptance also needs provider-enforced permissions,
conditional updates, exact request replay, real persistence/custody checks and
the supported offline trust/recovery route. No CRUD operation is deferred to an
unspecified future requirement.
