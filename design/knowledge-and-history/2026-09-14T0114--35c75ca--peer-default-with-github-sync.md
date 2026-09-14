---
created_at: 2026-09-14T01:14:54+09:00
head: 35c75ca
kind: direction
status: user-selected-design-direction
amends:
  - 2026-09-14T0107--35c75ca--peer-replicated-team-checkpoints.md
  - 2026-09-14T0003--35c75ca--disconnected-storage-and-sync.md
---

# Default: peer storage with GitHub synchronization

## Selected direction

The user selects decentralized peer storage as the default for robustness.
P2P is the complete operating foundation; GitHub is an optional convenience
integration and the preferred managed shared-state/synchronization route when
configured. This replaces treating peer replication as merely an optional
extension, or treating absence of GitHub as a degraded read-only mode.

The product purpose is preserved through locally available team context,
recovery from another authorized worker, and continuity during loss of a device
or hosted service. Sharing and recovery still respect each source owner's
permissions and the Team's approval/adoption boundaries.

| Responsibility | Default |
| --- | --- |
| Working and retained copies | Authorized worker-local peer repositories, with explicit retention coverage |
| Optional convenient shared storage and exchange | A configured GitHub repository for permitted portable objects, checkpoints and shared records |
| Alternative exchange | Direct authorized peer transfer, internal Git or full/incremental file packages when required by connectivity or source policy |
| Establishing accepted Team state | Existing exact-change approval, logical finalization and Team adoption rules |
| Verifying received data | The same identity, trust, permission, lineage, control-state and required-closure checks for every route |

GitHub stores real shared state; it is not restricted to a transient relay. It
must not be the sole retained location for material needed by the promised
offline profile, nor the only source from which an accepted checkpoint can be
verified and recovered.

## GitHub-free completeness

Initial Team/trust setup, source authoring, exact review, authorized finalization,
Team adoption, local use, permitted peer/package exchange and recovery must all
have a GitHub-free route. A GitHub account, repository, API, PR review or hosted
job must not be a hidden prerequisite for those core capabilities.

The existing authority and connectivity conditions still apply: absence of
GitHub must not prevent a valid operation, but an unavailable required approver,
finalization role, permitted communication path or source body may. This is not
permissionless or partition-independent finalization.

Adding GitHub improves shared-state retention and asynchronous exchange without
changing source identities, accepted checkpoints or approval meanings. Removing
the integration leaves the verified P2P system operable. Before retiring any
storage route, confirm the required retained copies and unique outboxes are
available under the existing custody rules.

## Operating rules

1. Save local work durably first. Keep unique drafts/outboxes until their
   acceptance or deliberate retention outcome is established.
2. Use the configured GitHub route for normal permitted exchange. A successful
   upload or newly visible commit does not itself publish, approve, adopt or
   activate an environment.
3. Import the same portable records from GitHub, another peer or an allowed
   package. Deduplicate by exact identity/request; the route does not change
   their meaning or grant extra authority.
4. Preserve required local bodies and verifiable checkpoints when GitHub is
   unavailable. Continue permitted work under the chosen offline conditions.
   New shared commits require the legitimate finalization role and applicable
   approval/authority evidence, regardless of the selected transport.
5. On reconnection, reconcile exact checkpoint lineage, controls, missing
   objects, outboxes and receipts. Do not replace local state with the newest
   remote directory or select a competing head by timestamp/branch name.
6. Upload only content and metadata whose source/recipient/export rules permit
   GitHub storage. A scope forbidden from external transfer uses its allowed
   alternative route without losing the peer-storage design.

GitHub repository access and branch controls supplement the product's authority
contract. Repository administration, branch names and remote availability do
not become replacement approval evidence or automatic authority succession.
The logical finalization role and its governed transfer remain as specified in
the peer design; decentralized finalization is not implied by this selection.

## Setup and Studio consequences

Environment setup offers GitHub as the preferred shared synchronization
destination and records its configured repository, permitted scope and exchange
policy. Selecting a design default does not supply credentials, infer a target
repository or authorize export of every local source. This does not change the
current product's zero-egress default or create automatic outbound behavior in
an unconfigured installation.

Studio shows local availability, peer retention acknowledgments, GitHub exchange
state and Team adoption separately. It can therefore show a valid environment
as locally usable while GitHub synchronization is pending. Unsupported source
or authority requirements still prevent an unwarranted readiness claim.

Acceptance must include GitHub unavailable with usable local/peer copies,
recovery without GitHub, a prohibited-export scope using another route,
duplicate delivery over GitHub and a peer, and conflicting remote/local heads
preserved for authority reconciliation. A GitHub upload alone must not satisfy
the peer-retention target or create a Team approval.

Also test the complete setup-to-use and subsequent update/recovery lifecycle
with GitHub never configured, then with the optional integration added and
removed. Equal authorized source inputs must retain the same environment and
authority semantics across both routes; transport acknowledgments may differ.

## Scope and status

This records the user's architecture choice. No GitHub repository, credentials,
network listener, recurring sync job or runtime implementation was created or
changed. Concrete adapters and deployment configuration remain implementation
work under the already-defined storage, governance and complete screen contracts.

A delegated consistency check confirmed the distinction between default shared
storage, unique authority, permitted replication and alternate closed-network
routes. This is design review, not an operational reliability test.
