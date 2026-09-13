---
created_at: 2026-09-14T00:03:19+09:00
head: 35c75ca
kind: design
status: proposed-connectivity-independent-architecture
amends:
  - 2026-09-13T1857--35c75ca--environment-storage-design.md
  - 2026-09-13T2336--35c75ca--studio-governance-design.md
  - 2026-09-13T2338--35c75ca--studio-complete-screen-contracts.md
---

# Team environments across disconnected networks

## Decision and correction

Every worker has a durable, verified local working replica. Each shared mutable
head has a designated authority. GitHub, an internal Git service, an object
store, a shared file drop, and an offline exchange bundle are transport/storage
options over the same portable records and verification contract.

Neither public Internet nor an always-running service is a prerequisite for
ordinary permitted work. A shared authority is required to confirm shared-state
changes, but that authority can be an internal service or a designated isolated
computer that processes exchanges periodically. A file arriving most recently
does not become authoritative merely by arrival order.

The earlier governance requirement for a current authority check is amended:
**use the authority evidence required by the chosen connectivity policy; do not
equate that with Internet access or an always-reachable remote service.** An
offline reviewer may create a real signed approval statement. A designated
authority can commit against its own authoritative local policy while isolated.
An ordinary replica cannot turn gathered approvals into a shared-head commit.

The older governance prototype's single offline-blocking fixture demonstrates
one restrictive policy, not the full product rule. Its dated source is retained
as history; this record defines the broader contract.

## 1. Where the data and authority live

| Layer | Durable contents | Responsibility |
| --- | --- | --- |
| Worker replica | Authorized source editions and required bodies; known policies and grants; accepted authority and memory checkpoints; local drafts/events; outbox and transfer receipts | Work without continuous remote access; preserve local contributions and report exactly what is known |
| Shared authority per scope/head | Canonical policy/grants; accepted source/environment heads or Team adoption; accepted events; conditional-write state and operation receipts | Decide which shared changes committed; serialize conflicting updates within its own boundary |
| Distribution store or carrier | Immutable objects, authorized checkpoint packages, proposals/approvals and receipts | Deliver bytes through an allowed route; no implicit right to approve or change Team state |

Source owners, environment owners and Team adopters retain separate authority
boundaries. They may use one physical internal service without becoming one
undifferentiated owner. A consumer stores a vector of their relevant checkpoints;
there is no invented global transaction or global clock across providers.

The worker replica is not an expendable download cache: drafts, the outbox and
unshared observations may exist only there. The source cache and search index
are regenerable; those unique records and their delivery acknowledgments are not.
Do not synchronize a live database, lock files or a native session directory by
file mirroring. Synchronize the portable objects and records through the importer.

An illustrative logical layout, not a committed path or universal payload schema:

```text
Portable material
  immutable source objects and environment editions
  individually identified decisions, requests, approvals and receipts
  versioned authority policy, grants, revocations and deletion markers
  signed checkpoints over exact accepted references and event frontiers

Worker-only state
  local drafts and durable outbox
  last accepted checkpoints and transfer acknowledgments
  verified object cache and rebuildable indexes
  host compilation, activation pins, local delivery/recovery journals
  credentials and private keys in their protected host stores
```

Individual portable records avoid competing appends to one shared text file.
A JSONL export or a search database can be derived from those records. A record
set can merge by identity while the choices described by those records remain
in conflict; importing both does not choose a winner.

## 2. Deployment choices

These are interchangeable deployment profiles, not separate products.

| Situation | Recommended arrangement | Tradeoff |
| --- | --- | --- |
| Internet available and external storage permitted | Local replicas plus existing GitHub repository/review workflow and a trusted checkpoint publisher | Convenient collaboration; portability and offline evidence still need the application contract |
| No public Internet, internal network available | Local replicas plus an existing internal Git service or small internal authority service | Full shared approval/publication/adoption within the network; operate and back up the internal authority |
| Workers connect only once or twice a week | Local replicas plus a designated authority, durable outboxes and complete/incremental exchange packages | Work continues within offline policy; shared convergence and conflict discovery are delayed |
| No network path between machines | The same packages through approved removable media or a controlled transfer station; authority may be an isolated machine | No always-on server needed; media custody, acknowledgment and recovery become operating procedures |

If an internal Git service already exists, reuse it. If no service exists, begin
with the designated authority and package exchange rather than requiring a new
web platform. Add a server when concurrent access, centralized administration,
search or unattended exchanges justify its operating cost. Do not begin with
multi-region consensus, automatic peer election or simultaneous writable replicas
of the same Team head.

### Git and GitHub fit different parts of the system

Git can transport versioned objects without a live server: full bundles can
bootstrap a replica; incremental bundles require the recipient's prerequisite
objects, which can be verified before import. A bundle is read by clone/fetch,
not a writable remote to which clients push.
[Git bundle documentation](https://git-scm.com/docs/git-bundle)

GitHub branch protection can require reviews and dismiss approvals made stale
by changed content. Signed-commit requirements and review requirements are
separate controls. These are useful integration points; they do not by
themselves establish the product's source scope, Team adoption, memory frontier
or actual task delivery.
[GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)

A GitHub integration must bind approved content to an exact application request
and export authenticated approval evidence and a committed checkpoint. PR
comments and web badges alone are not portable offline authorization. Evidence
can be individually signed or attested by an explicitly trusted provider bridge;
copying unsigned review JSON does not authenticate a reviewer.

Only the configured authority publishes accepted checkpoints. Other repository
branches/commits remain candidates even if a Git administrator can write them.
Configure repository rules as an additional control, and keep checkpoint trust
independent of a branch name, administrator bypass or force-updated remote.

Do not bundle the full authoring repository merely for convenience. Select only
recipient-authorized portable content and its allowed history. Separate sources
with different confidentiality/retention boundaries. Git LFS stores file
references in Git while the large bodies live separately, so dependency closure
must account for the actual bodies, not just a successful clone.
[Git LFS documentation](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)

Retention-sensitive bodies need a storage boundary that can enforce their
declared retention rules; Git may carry allowed metadata/references instead.
Git history deletion requires coordinating other copies, and existing clones
can retain material. No Git or file-transfer profile promises erasure of
uncontrolled copies.
[GitHub history-removal guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)

## 3. The portable exchange contract

One exchange envelope is independent of its carrier. It identifies its format,
source authority/namespace, permitted recipients/scope, exact inventory with
hashes and sizes, required prerequisites, supported semantics, and the included
checkpoint/request/receipt references. Integrity and trusted origin cover the
envelope and its exact object set. Confidentiality protection is selected from
source and recipient policy; signing does not encrypt the content.

Three uses share this envelope:

- **Bootstrap/full transfer:** enough permitted source bodies, trust continuity,
  policy and event closure for the named environment and work scope.
- **Incremental transfer:** exact additions and control updates against declared
  prerequisites. A missing baseline is an incomplete import, not permission to
  guess or call a half-updated environment ready.
- **Return transfer:** contributed records, exact proposed changes, signed
  approvals and acknowledgment/receipt requests for the sender's work.

Provide a permitted complete transfer when a recipient's baseline is unknown,
damaged or too old. Delta efficiency must not make recovery depend on a chain
of unavailable files. A complete transfer still observes deletion and retention
policy; unavailable historical content is reported rather than resurrected.

Build deltas against the recipient's acknowledged checkpoint and object
inventory, not a wall-clock phrase such as "since last Tuesday." Preserve the
sender's outbox while receipt/acceptance is unknown. Transport retries and a
missed synchronization window must not discard unique local work.

The package contains required working content, not only an orientation index.
Instructions triggers and procedures needed offline, coherent knowledge units
with conditions/exceptions, and the permitted memory frontier and state-relevant
closure must be reachable locally. Citation evidence that cannot travel remains
explicitly unavailable; a task depending on it is not fully prepared.

A checkpoint binds stable authority identity and epoch, ordered revision and
predecessor, exact accepted heads, policy/control revision and memory frontier,
and applicable validity conditions. Scope-specific checkpoints avoid forcing
unrelated owners into one chain. A high number or recent timestamp is not a
substitute for verified trust and predecessor continuity.

Bootstrapping trust is an explicit authenticated enrollment or independently
verified transfer of the authority identity and root. A package cannot establish
trust in itself by containing its own public key. Preserve accountable human
identity across keys so key rotation does not manufacture a second reviewer.

Trusted roots, delegated keys, consistent signed snapshots and rollback/expiry
checks have established update-system precedent in
[the TUF specification](https://theupdateframework.github.io/specification/latest/).
That informs this design; adopting a complete TUF implementation is not decided
here, and the Team approval/decision protocol is not supplied by TUF. If used,
its verification requirements must be honored, not bypassed for convenience.

## 4. Synchronization without silent loss

1. **Prepare outbox:** seal immutable local records and requests with their bases,
   premises and known authority state. Persist before reporting saved. Preserve
   originals until the authority confirms acceptance or a deliberate retention
   decision removes them.
2. **Transfer into staging:** accept only allowed carrier/recipient/scope. Enforce
   inventory size and supported format, reject traversal/unexpected executable
   actions, and never run imported hooks/scripts as an import side effect.
3. **Verify control evidence first:** establish trusted identity/continuity, then
   process verified policy, revocations, suspensions and tombstones according
   to their authority. Reject older control state and conflicting successors.
4. **Verify objects and closure:** require exact bodies, prerequisites and all
   known state-relevant events necessary for a claimed result. Receiving unrelated
   new objects does not authorize them for this environment.
5. **Commit local availability:** promote a fully verified immutable set and its
   receipt atomically through the owning local journal. An interrupted import
   leaves the prior usable set intact; new denied/deleted controls still restrict
   future use even if some unrelated content transfer is incomplete.
6. **Resolve contributions at the authority:** check current authoritative policy,
   grants, reviewer eligibility, request binding and expected predecessor; issue
   a durable signed acceptance/rejection/commit receipt. Preserve rejected and
   conflicting proposals for the authorized contributor to revise.
7. **Return acknowledgment:** the sender distinguishes `exported`, `received`,
   `verified`, `accepted` and `committed`. A copied USB file or transport upload
   is not proof that its contents were accepted or applied.
8. **Prepare/use deliberately:** new adopted references remain separate from
   local readiness and actual task delivery. Existing tasks retain their exact
   prior context identity; future use also checks newly learned restrictions.

The object identity and canonical request, not the carrier filename, determine
idempotency. Re-importing a package creates no duplicate records or decisions.
Reusing an operation ID with different payload fails. If a response is lost,
query or return the existing operation receipt rather than issue a new mutation.

On interrupted transfer, resume verified chunks/objects when supported or
restart the immutable package transfer; never require editing an accepted
object in place. Failed validation is recorded with an actionable cause. A
sync job cannot report all-success while one required namespace is incomplete.

## 5. What work can proceed while disconnected

Public-Internet reachability and authoritative-Team reachability are different
capabilities. Studio must show which is missing.

| Operation | Internal authority reachable, no Internet | Ordinary replica has no authority connection |
| --- | --- | --- |
| Read, retrieve and work from prepared content | Allowed under applicable policies | Allowed within explicit offline-use conditions |
| Save drafts, observations, candidate decisions | Local save and normal submission | Durable local save and outbox; no invented Team acceptance |
| Make a decision within a delegated local mandate | Record its actual subject authority and premises | Record the bounded local decision and known authority checkpoint; do not assert that other workers know or share it |
| Review/sign an exact proposal | Normal review and commit-time eligibility checks | Signed review statement can be created/exchanged; shared commit remains pending |
| Publish/adopt/change shared grants | Responsible internal authority can commit | Ordinary replica queues requests; only the designated authority may commit |
| Commit on a designated isolated authority machine | Its local authority state governs | It can commit for its owned scope without a network service, and distribute signed receipts afterward |

A locally recorded choice does not become a Team-wide current choice solely
because its author was permitted to work offline. Its scope and decision mandate
determine its authority. At convergence, competing authorized choices may
remain unresolved; the record of what each person actually decided is preserved.

Approvals signed offline retain their historical meaning. Eligibility to use
them for a shared commit is checked by the committing authority; a signer being
authorized when they claim to have signed is not enough if the current policy
requires live eligibility at commit. Self-declared signing time does not prove
that a revoked key was used before revocation.

## 6. Offline operation profile and honest freshness

Provision a versioned connectivity profile for the environment and applicable
sources. It names:

- the maximum intended separation and ordinary exchange route/schedule;
- permitted offline actions, scope, recipients and any delegated local decisions;
- the authority evidence/lease or other bounded mandate required for each action;
- validity limits for control evidence, knowledge and required capabilities;
- expiry/uncertain-clock behavior and an authorized emergency update route;
- the configured authority location, custodians and recovery procedure.

The profile must fit once- or twice-weekly exchange if that is the operating
requirement. Do not hardcode a daily refresh requirement and then advertise
offline operation. Select the allowance with the Team and source owners: the
scheduled interval plus a contingency margin is a planning input, while stricter
source conditions remain the effective limit. This document assigns no universal
number of days or automatic grace period.

Longer disconnected use means slower awareness of remote changes. A worker
cannot immediately learn a revocation, correction or new decision that has not
reached them. Once received and verified, applicable restrictions govern future
operations; until then the client can only report its accepted checkpoint and
the guarantees of its chosen offline policy. Immediate centralized revocation
and unrestricted disconnected use cannot both be promised for the same material.

An authority's own local committed state is current for its scope because that
authority is its sole writer. An isolated local authority consuming another
owner's policies still has only the last permitted observation of that owner's
state. Its delegated rights must fit that owner's offline conditions. Independently
operating sites should own separate delegated scopes/heads rather than both
claiming to be the sole writer of the same head during a partition.

Keep these five facts separate in task preparation:

1. **Integrity/origin:** exact bytes and verified source identity.
2. **Permission:** use is authorized under the available control evidence.
3. **Applicability:** the knowledge's scope, period and exceptions fit this task.
4. **Freshness evidence:** when/against what source the claim was checked.
5. **Observed memory:** the known frontier plus explicitly local additions.

A known future-effective change can become applicable without another download.
An unknown amendment issued after the last exchange cannot. A valid signature
or offline allowance is not proof that external facts are current. Requirements
for newer evidence block the dependent claim/action, not unrelated local drafting.

Time-based expiry needs sufficiently trustworthy local time and retained state.
Record the last accepted control checkpoint and time observation durably. Clock
rollback, loss of those records or restoration of an old disk image does not
reset the allowance. Where the trust profile cannot establish time/state, obtain
an authorized refresh/re-enrollment rather than silently extend access. This is
not a claim to resist arbitrary compromise of the worker's operating system.

## 7. Conflict, failover, deletion and confidentiality

Each shared mutable head has one serialization boundary. It can run on a server
or a designated machine, but two isolated copies of its signing state cannot
both be treated as independent active authorities. Reviews remain independent
even when final commitment is serialized by one authority process.

Maintain the last accepted epoch/checkpoint. Reject replay as a new current
head. An intentional reversion to an older content edition is a new authorized
head transition with a new receipt; it does not roll the authority history back.
If incompatible signed successors appear, retain the evidence and stop automatic
adoption for the affected scope. Highest version or latest timestamp is not a
conflict-resolution policy.

Backups are passive. Authority failover requires a governed transfer/recovery,
updated epoch/trust evidence and a deployment-appropriate way to fence the old
writer. If the old writer cannot be fenced or reached, do not claim instant
global exclusion: replicas still isolated from the recovery have bounded stale
trust until they receive it or their allowance expires. Keep ambiguous shared
changes pending; do not elect a replacement merely because a server is silent.

Back up immutable bodies and history, authority heads/control state and receipts,
and governed recovery material. Also back up unique worker outboxes. Keep recovery
keys separate from ordinary signing/transport credentials. Restoring old content
must not silently restore old mutable authority state or active credentials.
Carry required intermediate key-rotation continuity to late-returning replicas;
root compromise needs the separately established recovery route.

Deletion/suspension controls travel as durable scoped records. Returning old
bundles cannot resurrect deleted revisions. Before distributing a fresh package,
apply current export/retention conditions and include the permitted control
closure. Known affected owned caches, excerpts and indexes are removed or denied
as required; already delivered prompts and uncontrolled copies cannot be
promised erased. If controlled access/deletion is essential, limit what leaves
the protected namespace rather than relying on a later global deletion promise.

A closed-network boundary may allow only inbound transfer or prohibit exporting
local decisions. Obey that topology: configure permitted direction and fields,
and keep prohibited content inside. No sync procedure bypasses an air gap. If
there is no permitted information path in a direction, convergence in that
direction is unavailable, not a transport feature waiting to be enabled.

## 8. Prepare the whole execution environment

Offline data alone is insufficient. Preparation checks local/inside-network
availability of the chosen host/model, required tools and readers, schemas,
validators, package dependencies and permitted source evidence. An environment
whose necessary model or tool only exists behind an unreachable external API
is not runnable merely because its instruction files were copied locally.

Ship/provision the required runtime through a separately verified deployment
package or approved internal repository. Do not embed credentials in the source
bundle. Compile host-specific context locally, and validate that the resulting
required paths operate with external network access disabled. Search/retrieval
must have a local implementation for the advertised offline profile; optional
remote enrichment cannot be required for its basic reader to work.

## 9. Studio implications

| Screen | Required addition |
| --- | --- |
| Environment setup | Authority/store location; permitted carriers/directions; connectivity profile and required local capabilities |
| Environment header | Exact locally observed adopted edition/checkpoint; last confirmed exchange; source-specific limits; local/unshared work indicator |
| Review queue | Signed review recorded versus authority-accepted versus committed; deferred eligibility checks named |
| Team/access | Offline mandates/expiry, delegated scopes, recipient restrictions, key/custodian continuity and pending revocations |
| Operations | Durable outbox/inbox; full/delta package preparation; prerequisites; receive/verify/accept/commit acknowledgments; partial/fork/uncertain outcomes |
| Task preview/use | Local content closure; permission/applicability/freshness/memory qualifications; actual recipient readiness, including model/tools |
| Recovery | Restore last accepted trust state and unique work; approved authority transfer; re-enrollment when continuity cannot be established |

Use labels such as `9월 14일 확인한 팀 기준`, `오프라인 사용 허용 범위 내`,
`새 작업 3건은 아직 공유 전`, or `권한 근거 갱신 필요`. Do not use an
unqualified `최신`, green online badge, or a single sync time to summarize all
five knowledge/authority facts.

## 10. Reference pilot and acceptance obligations

Start with two worker replicas and one authority role, using the same records
over (a) a Git-backed route and (b) full/incremental file exchange. The authority
may be an existing internal service or an isolated batch machine. This pilot is
recommended implementation work, not executed by this document.

Use one prepared environment for a simulated week without the authority. Workers
read local instructions/knowledge/memory, record independent work and exchange
a signed exact review. The authority then processes a publication and separate
adoption. On the next exchange, both workers converge on accepted controls and
records, with conflicts preserved and earlier task identities unchanged.

An illustrative weekly round is:

| Point | Worker and authority state |
| --- | --- |
| Monday departure | Workers verify checkpoint P40, environment E3, knowledge K7, memory F100 and the source-compatible offline allowance. Local runtime readiness is checked. |
| During the disconnected week | Each works from P40/F100, records local contributions and known changes, and keeps an outbox/backup. Neither claims to know the other's unseen decisions. |
| Next exchange: incoming work | The authority receives candidates and signed reviews if already available, returns per-item results, and requests any missing review or reconciliation. |
| Next exchange: outgoing state | Workers receive P41 and permitted updates/control records, verify closure and apply learned restrictions. Existing task context identities remain historical facts. |
| Unfinished approval | A proposal needing another person's response remains pending and may require another exchange window; a transfer is not an automatic approval. |

One- or two-times-weekly transfer is a connectivity schedule, not a guaranteed
approval completion time. When decisions must close faster, provide reviewers
at the internal site, pre-arrange review rounds within an available window, or
delegate a bounded local decision scope under the governing policy. Never hide
the latency by marking unseen work approved or dropping reviewer independence.

| Injected condition | Required observation |
| --- | --- |
| No Internet, internal authority reachable | Normal in-network review/commit/use; no public service dependency |
| No authority contact for the permitted week | Prepared work and local saving continue; exact known checkpoint stays visible |
| Offline signing, signer revoked before authority commit | Review remains evidence; commit fails current required eligibility |
| Lost/repeated/out-of-order package | Idempotent records; missing prerequisites or old control state disclosed; no false activation |
| One required body or correction omitted | Incomplete materialization; no false current-state answer |
| Modified inventory/object or wrong signer/namespace | Rejected before promotion |
| Conflicting edits or decision successors | Both candidates preserved; exact-base conflict or unresolved semantic state |
| Commit succeeded but return receipt lost | Same operation resolves; no duplicated publication/adoption |
| New restriction arrives with an incomplete body transfer | Restriction takes effect; old bytes do not stay usable solely because import is partial |
| Deleted object returns in an old full package | Tombstone prevents revival |
| Changed domain fact remains outside the air gap | No claim to know it; task qualifies or blocks according to freshness requirements |
| Offline permission expires or clock/state is unreliable | Dependent operation unavailable; allowed drafting continues; no silent grace period |
| Authority restored from backup while old writer survives | No automatic promotion; governed fencing/recovery or visible authority fork |
| Local disk loss before outbox acknowledgment | Recovery from the worker backup; remote sync cannot recover never-exported bytes |
| Runtime/tool/model needs external access | Offline-readiness check fails before work is advertised ready |
| Export is forbidden by network/source policy | Local records remain local; no claimed bidirectional convergence |

Pass these against real adapters and durable storage before claiming reliable
offline operation. Document observed recovery-point/recovery-time bounds from
the actual exchange and backup policy; this design promises no unmeasured
uptime, zero data loss, real-time revocation or global latestness.

## Review and implementation status

Two independent delegated analyses compared the deployment options and reviewed
offline authority semantics. A final read of this proposed contract found no
critical contradiction in the designated-authority, cross-owner policy, replay,
partial-import, weekly-use or recovery boundaries. This is design review, not
verification of a working storage or identity implementation.

No server was deployed, repository created, recurring synchronization scheduled,
or runtime source changed. Git/GitHub capabilities were checked through Context7
and the linked primary documentation. New design text is checked directly by the
repository's terminology scanner rather than relying on a tracked-file scan
that would omit an untracked record.
