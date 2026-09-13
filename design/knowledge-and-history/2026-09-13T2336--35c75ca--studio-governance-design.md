---
created_at: 2026-09-13T23:35:56+09:00
head: 35c75ca
kind: design
status: proposed-complete-governance-contract
amends:
  - 2026-09-13T1857--35c75ca--environment-storage-design.md
  - 2026-09-13T2245--35c75ca--unified-studio-scope.md
  - 2026-09-13T2328--35c75ca--studio-ui-design.md
---

# Studio governance: who may change the shared environment

## Correction to the earlier scope

The earlier prototype assumed a fictional user with publication and adoption
rights. It did not mean that all workers may publish. However, the earlier
design did not define how those rights are allocated, who approves a particular
change, or how authority is maintained. These are necessary parts of the shared
team environment, not optional administration polish.

The user's instruction brings all previously deferred Studio workflows into
design scope. The [complete screen-contracts companion](2026-09-13T2338--35c75ca--studio-complete-screen-contracts.md) specifies their minimum
forms, transitions, failure behavior and acceptance cases. Implementation may
be incremental; missing implementation must not be mistaken for unspecified
authority or a supported empty feature.

The product goal remains selection, sharing and continuation of team work
environments. **A worker's professional role is not an authorization role.**
Selecting a developer or accounting environment changes applicable working
context; it does not create permission to read, publish, grant access or adopt.

## Minimal model

Use three related contracts, served by their existing authoritative providers:

1. **Scoped grants:** who may perform which actions on which resources, under
   which conditions, and who granted those rights.
2. **Change requests and approvals:** the exact proposed effect, applicable
   policy, and recorded approval or rejection of that effect.
3. **Execution receipts:** whether the responsible provider actually committed
   that exact authorized effect.

These are cross-cutting contracts, not a fourth kind of working knowledge or a
single storage format for Instructions, knowledge and memory. An approval is
neither a source revision nor a delivery receipt. Source truth and semantic
validity are not established merely because someone approved publication.

### Resource boundaries

| Resource boundary | Authority it owns | Authority it does not gain |
| --- | --- | --- |
| Source namespace/package | Source revisions, release references, source access, export/retention conditions | Another owner's source; a consuming Team's adoption |
| Environment | Composition drafts, immutable editions and release selection | Rights to distribute referenced sources or change a consuming Team |
| Team | Membership, Team-scoped grants, Team policy and adopted environment reference | Every member's personal sources or another Team's namespace |
| Workstream/decision subject | Accepted decision effects and recording policy within its source | Blanket authority over every decision in an environment |
| Task/worker context | Local preparation, permitted delivery and its receipts | Upstream publishing, Team authority or implicit delegation to children |

A Team may own several of these resources, but co-ownership never collapses
the action boundaries. An environment can be published by one owner and adopted
by several Teams. A grant names stable resource IDs; display names are not keys.

### Grant shape and evaluation

An authoritative grant identifies the principal, resource scope, allowed action
set, issuer, grant ID/revision, optional expiry, and any delegation constraints.
Principals are authenticated people, groups or identified service/agent
principals. Issuer/provider identity is part of the binding. An unverified email,
local role string or editable document cannot establish identity or membership.

For a requested action, evaluate authenticated identity, applicable live grants,
resource/source constraints, delegated limits, policy and current operation
state. A role label alone is insufficient. Missing authorization denies the
action. Withdrawal, expiry or a stricter source constraint cannot be canceled
by a broader Team grant. Reading and search are checked as well as writes.

A private local provider may rely on its operating-system account boundary for
personal work. An editable local file or a client-assigned identity cannot prove
independent shared-Team approval. Imported shared decisions must retain verified
provider identity and request/receipt bindings; matching hashes alone establish
neither identity nor authority. Shared-state writes are judged by the configured
authority even when invoked from a desktop client or a manually transferred
candidate.

Keep the action vocabulary small but distinct:

- `read`, `use`, `contribute`, `review`;
- `publish` on a named source/environment and `adopt` on a Team environment;
- `decide` for an authoritative decision effect, separate from recording a
  proposed choice or observation;
- `grant`, `policy`, `transfer`, `suspend`, `retain/delete`, `export` as explicitly
  scoped administrative actions.

Approval eligibility is `review` for a specific operation class and scope;
execution still requires that operation's action grant. A reviewer cannot
publish merely because they may approve. Read access alone grants neither
export nor permission to feed protected material into an arbitrary host.

User-facing templates simplify assignment. They are editable grant bundles,
not a hierarchy in which a higher title silently inherits every power:

| Template | Starting bundle |
| --- | --- |
| Consumer (`사용`) | Read and use authorized adopted environments/material |
| Contributor (`기여`) | Consumer plus drafts, suggestions, proposed decisions and observations |
| Operator (`운영`) | Explicitly selected review, publication, adoption or decision actions on named resources |
| Access manager (`권한 관리`) | Request/manage assignments and governance policy within an explicit grant ceiling |

Show the resulting action checklist, scope, delegation ceiling and expiry before
assigning a bundle. Templates do not change existing grants when edited; that
requires an explicit reviewed grant change. An access manager does not obtain
source-body access solely by managing assignments.

## Who assigns authority

### Bootstrap and ownership continuity

Creating a new namespace/Team uses an authenticated provider operation that
records its founding owner, initial policy and governance capabilities. This is
the explicitly recorded root of authority; it does not claim independent
approval by a second person. Joining someone else's Team requires its invitation
and verified membership process, not typing its name into Studio.

The creation screen makes the operating profile explicit:

- **Personal/solo:** a named owner may perform the allowed actions and approve
  their own work. Receipts say self-reviewed, not independently approved. This
  never changes the rules of a Team that later adopts that personal source.
- **Shared Team:** independent human review is the starting policy for shared
  source/environment releases, adoption changes and privilege expansion. Setup
  needs an eligible second reviewer/recovery custodian before protected changes
  become available. It can remain read-only/setup-incomplete; it must not silently
  fall back to solo approval because a reviewer is unavailable.

Existing Teams cannot downgrade to solo by toggling a setting. Changing the
governance profile is approved and executed under the existing authority and
policy. Optional organization-level restrictions may tighten a Team's policy
through an explicitly configured authority relationship; no company hierarchy
is required and no parent relationship is inferred from names.

Ownership transfer names an eligible new custodian who accepts the transfer,
has the required authenticated recovery capability, and receives the exact
governance scope. Validate the resulting custodian/reviewer availability before
removing the previous one. An ordinary grant change cannot remove the last
required governance/recovery path. A documented provider recovery process uses
separately established custodians and leaves an audit record; it cannot be a
self-appointed emergency administrator in the client.

### Grant lifecycle

`requested → approved/rejected → applied → expired/revoked` identifies distinct
events. The assignment form includes recipient, action bundle, exact scope,
expiration/delegation bound and reason; its review shows added/removed powers,
affected policies and any pending operations that will lose eligibility.

An issuer can grant only within the scope and action ceiling explicitly
delegated to that issuer. Effective delegation is bounded by both the issuer's
current authority and the narrower issued grant. Revoking an upstream delegation
invalidates its dependent future use. Membership changes affect grants derived
through that membership; independent direct grants remain visible and require
their own review/revocation. Leaving a Team is not proof that all other grants
were removed.

Shared-profile privilege expansion, granting review power, or changing one's
own effective powers requires another eligible governance reviewer. An issuer
cannot count their own approval or split identities to satisfy this check.
Restricting access can be executed immediately by a pre-authorized custodian
when the resulting governance continuity constraints hold. Re-enabling,
expanding access or weakening policy follows the normal approved-change path.
The UI distinguishes emergency suspension from deletion and from policy waiver.

### Agents and delegated execution

An agent action records both the actual service/run identity and the accountable
person/service sponsor, along with its bounded delegation. Choosing an
environment is not a delegation. A child cannot exceed its parent's effective
scope, action set, recipient/export limits or lifetime.

The default shared profile counts independent human principals for approvals.
It excludes both the requester and all recorded accountable authors, including
agents acting under either's sponsorship. A different person who submits an
author's candidate cannot count their own approval of that request. An author's
agent, another run of that agent, or an agent acting for the same accountable
author cannot satisfy the independent-review requirement. Automated
validation may attach evidence; it does not fabricate human approval. Other
explicit automation policies may be designed as named machine checks and narrow
execution grants, but must not be labeled independent human review.

## Approval policy and exact-change binding

A versioned policy is attached to the owning scope and operation class. It names
eligible reviewer pools, required counts, independence constraints, mandatory
checks and any validity/expiry conditions. A default of one independent reviewer
is a proposed shared-Team starting profile, not a universal requirement for all
Teams or a claim that one review proves semantic correctness.

The simple policy form supports required reviewer pools with counts and
independence constraints. The only ordered stages are real resource dependencies
(source revision, environment edition, Team adoption). Arbitrary workflow code
is unnecessary for the designed workflows. Multiple required pools can be
satisfied in one review screen when the reviewer is separately eligible for
each; each approval still names its operation and effect.

| Operation | Proposed starting policy |
| --- | --- |
| Read, preview, permitted use | Current access and target requirements; no additional content approval on each read |
| Draft, proposed decision, observation | Contribution grant; record origin and unaccepted/proposed status |
| Source release | Source-qualified reviewer and structural/domain checks; execute with source publication authority |
| Environment release | Composition reviewer, exact dependencies and source distribution conditions; execute with environment publication authority |
| Team adoption/reversion | Team reviewer of the exact edition and applicability; execute with Team adoption authority |
| Accepted decision or state-changing correction/withdrawal | Subject's decision policy and authority; contributor recording alone cannot make a choice authoritative |
| Grant expansion, policy change, ownership transfer | Governance reviewer under current policy; execute within current governance scope |
| Suspension/access restriction | Pre-authorized containment action; reason and impact recorded, continuity checked |
| Deletion/retention/export change | Relevant owner and retention/source restrictions, named impact set and current approval policy |

A decision-authorized person can record their own in-scope decision directly
when the subject policy permits it. Otherwise a contribution remains proposed
until accepted. Attesting to an earlier decision requires evidence of the actual
decision maker and scope; the recording agent does not become that maker. Pending
proposals remain discoverable as unresolved context but never silently replace
accepted current state. A suspected harmful error may suspend reliance while
its correction awaits review.

### Request identity

Submitting seals an immutable request containing:

- operation, owning scope, requester/actors and accountable author;
- exact candidate payload/digest or revision references, expected base/head
  tokens, and affected source/Team/task targets;
- policy revision and required checks/evidence references;
- requested effect, rationale and operation-specific fields.

An approval identifies that request/digest, approving principal, eligibility
evidence, outcome, reason and time. Changing content, references, scope, target,
policy or relevant validation basis requires a new request and approvals. Keep
the earlier request and its review history; do not move approvals to a revised
draft. Display `수정되어 다시 검토 필요` or the actual qualification failure.

At execution, re-evaluate current requester and executor authority, approver
eligibility, delegation, policy revision, request expiry, required checks and
resource conditions. By default, an approver's revoked/expired authority no
longer authorizes a pending operation. Past committed operations retain their
historical receipts; later revocation is not a retroactive erasure of history.

Conditional head checks and request-bound operation IDs remain required. A
successful approval is not permission to overwrite a concurrently advanced
head. A policy change is approved under the current old policy and applied with
a conditional update; the proposed weaker policy cannot approve itself.

## State and recovery contract

The shared operation shell provides these states, with source-specific payloads:

`draft → in review → approved → executing → committed`

Additional explicit outcomes are `changes requested`, `rejected`, `withdrawn`,
`expired/stale`, `blocked`, `conflict`, `result unknown`, and `partially completed`
for a multi-provider batch. Approval and execution qualifications are re-derived,
so a previously approved request can become blocked before execution.

No vote is approval by elapsed time, silence or a notification delivery receipt.
Rejection records a reason. Revision after rejection creates a new request linked
to the earlier one. An eligible reviewer may retract a pending approval; the
provider serializes that against commit. After commit, rollback/withdrawal is a
new governed operation, not deletion of the approval history.

Execution commits the exact mutation with its durable receipt, or reports its
actual failure. If the response is lost, query/retry the same request-bound
operation ID. An unknown result is not a failed mutation to repeat under a new
ID. A receipt also cannot be used for different content or another resource.

Offline drafting and observations are allowed under cached source conditions.
Shared publication, adoption, grant/policy changes and authoritative approvals
need a current authority check; the baseline offline behavior is to queue a
proposal rather than pretend the shared action succeeded. Offline use follows
source policy and the recorded authorization lease; known revocation denies
future protected operations, while unseen revocation cannot be promised detected
instantaneously on an offline machine.

## Integrated screens

Retain four content areas, adding three cross-cutting destinations:

- **Review queue (`검토·승인`):** authorized requests, exact differences, owner,
  base, author, scope, required reviewers/checks and current eligibility. Separate
  approve/reject from execute; show why an action is unavailable and who can
  resolve it without exposing restricted identities or content.
- **Team and access (`팀·권한`):** creation/joining, membership, effective grant
  matrix, delegation/expiry, policies, custodians and grant/transfer reviews.
  Select a resource to inspect rights; a Team-wide role summary is not sufficient.
- **Operations (`동기화·기록`):** sync progress, pending work, conflicts, uncertain
  operations, receipt recovery, affected task contexts, retirement/deletion and
  audit. Audit events are operational evidence, separate from Decision memory;
  an explicit reference can connect a substantive adoption rationale to memory.

Do not require a second editor for each operation. Reuse the list, detail, diff,
review and outcome layouts with role-specific forms. Browser/CLI/MCP callers
must use the same policy evaluation and mutation authority. Disabled buttons
explain an outcome but do not enforce authorization.

## Required acceptance cases

1. A contributor can prepare a draft but cannot publish it by direct endpoint,
   alternate CLI/MCP route, hidden control or changed request body.
2. A reviewer can approve an exact candidate but cannot execute without the
   corresponding grant. A publisher without Team adoption rights cannot adopt.
3. A requester, an accountable author, their other sessions, and their delegated
   agents cannot constitute independent approval of that proposal. The executor
   may execute an independently approved request if separately authorized;
   execution is not an additional approval.
4. Editing an approved candidate, changing its target or policy, or losing a
   required source invalidates execution of the earlier reviewed request.
5. Revoking a reviewer's grant before execution blocks their pending approval;
   revoking a parent delegation blocks dependent agent actions.
6. A Team access manager cannot grant rights over another owner's sources or
   expand their own delegation ceiling. Source restrictions survive composition.
7. A grant/policy expansion is evaluated under the current governance policy;
   a proposed weaker policy cannot authorize its own installation.
8. An unapproved memory proposal is not returned as an accepted current choice.
   Correction, withdrawal and actual outcome preserve their separate meanings.
9. An accepted edition can be published without adoption; adoption can succeed
   without local readiness; an existing task does not silently change its pin.
10. A lost response resolves to the original receipt. Concurrent writes retain
    both candidates; blocked deletion/retention does not erase evidence anyway.
11. Solo mode is labeled self-reviewed; a shared Team's reviewer shortage never
    silently changes it to solo. Ownership changes preserve a valid recovery path.
12. Search, exports, logs and explanations reveal only authorized metadata/body;
    counts and existence of private records are not leaked through denied views.

These are design acceptance obligations for real provider implementation. The
interactive mock tests a finite subset of UI transitions and never establishes
that these security boundaries are implemented by the existing product.

## Design references

The distinction between role assignments and permissions, with additional
separation-of-duty constraints, is grounded in the
[NIST RBAC overview and FAQ](https://csrc.nist.gov/projects/role-based-access-control/faqs).
The scoped grants and exact-change approval contract above are this project's
design choices, not a claim of compliance with that standard.

Default denial, request-level checks, resource/relationship conditions,
server-side enforcement, logging and negative authorization tests follow
[OWASP's authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
Provider and identity-product selection remain implementation choices; the
required authority behavior is specified here rather than delegated to a library.

## Companion artifacts

- [Complete screen contracts](2026-09-13T2338--35c75ca--studio-complete-screen-contracts.md)
- [Governance prototype source](2026-09-13T2336--35c75ca--studio-governance-prototype.html)
- [Prototype QA and coverage limits](2026-09-13T2355--35c75ca--studio-governance-qa.md)

An independent design review checked the governance model and complete screen
coverage. Its required clarification—exclude both requester and accountable
authors from independent approval—is incorporated above. The review did not
verify a real identity or policy implementation.
