---
created_at: 2026-09-14T17:52:58+09:00
head: 35c75ca
kind: design
status: implementation-process-specification-no-product-implementation
design_ssot: 2026-09-14T1752--35c75ca--consolidated-design-ssot.md
task_graph: 2026-09-14T1752--35c75ca--development-plan.json
test_catalog: 2026-09-14T1752--35c75ca--test-catalog.json
baseline_evidence: 2026-09-14T1752--35c75ca--brownfield-evidence.json
---

# Team environment expansion — brownfield development specification

## Authority and execution scope

The [SSOT](2026-09-14T1752--35c75ca--consolidated-design-ssot.md) owns product
meaning, required scope and policy boundaries. This document owns implementation
boundaries and work acceptance against it. The [task graph](2026-09-14T1752--35c75ca--development-plan.json)
owns task IDs, prerequisites, file ownership and required evidence. The
[test catalog](2026-09-14T1752--35c75ca--test-catalog.json) owns named test-family
oracles. They are linked engineering projections, not competing product rules.

The user's request authorizes this design/specification work. Product development
will use the work packets below when started; no runtime job, deployment, OAuth
consent, shared mutation or publication is executed by creating the plan.
“AI dynamic workflow” means dependency- and evidence-driven development, not a
particular model, orchestrator, plugin or newly promised product feature.

Scope includes U01–U21, W01–W10 and the complete advanced-operation table in SSOT
S11. **The user explicitly waives backward compatibility.** Old command
spellings, schema readers, native resume support, mixed-version operation and
generic upgrade/downgrade machinery are not acceptance requirements. Replace or
remove them when that makes the target simpler. Preserving current source work,
explicitly selected data and correct new authority boundaries is a separate
transition obligation, not a promise to preserve old interfaces.
 Personal use must work before Team, SSO or GitHub completion. Implementation
can expose explicitly named completed slices; a partial slice is not the whole
Studio and fixtures are never a substitute for its real providers.

Validate this planning bundle before a later execution begins:

```bash
python3 design/knowledge-and-history/2026-09-14T1752--35c75ca--check-development-plan.py design/knowledge-and-history/2026-09-14T1752--35c75ca--development-plan.json --self-test --check-inputs
```

This checks a nonempty acyclic plan, coverage, task-scoped test profiles, personal
independence from Team/SSO prerequisites, owner conflicts and inspected-source
drift. Its negative controls exercise actual plan failures. It never starts a
worker, runs product tests, freezes unbound case IDs or marks implementation done.

## 1. Brownfield input and transition constraints

HEAD `35c75ca` alone is insufficient: canonical Instructions modules/tests are
among the current untracked files, while the naming migration and other work
modify tracked sources. [Selected evidence](2026-09-14T1752--35c75ca--brownfield-evidence.json)
binds the actual bytes inspected for this spec. It is not a complete runnable
implementation baseline. P00 must capture the necessary tracked modifications,
deletions, untracked runtime/tests/docs and file modes into an isolated baseline.

Do not reset/stash/clean the shared checkout, stage unrelated work or make a new
worker start from HEAD while ignoring that state. Capture a coherent source set,
verify it after copying, and retry only changed inputs if concurrent work moved.
Record symlink identities; do not follow links outside the declared source scope.
Do not copy personal installed state/credentials, ignored secrets or arbitrary
output directories as convenient baseline data. Required omitted inputs remain
explicit gaps. A private isolated repository/worktree may host the captured base;
the main checkout/index and others' changes remain owned by their existing work.

| Existing owner / source evidence | Transition risk | Target rule |
| --- | --- | --- |
| Instructions catalog/store kinds, refs and source state | Reusing a convenient old field mixes people, Team, facts and behavioral rules | New schemas/IDs may replace old ones; preserve three-role meaning and record explicit source/data conversion |
| Authoring revisions, snapshots and native pins | Reusing one revision for login, K/M and every task makes unrelated changes interfere | Separate target revision/authority domains; old session-resume compatibility is not required |
| Transaction aliases, locks and journal parsers | Old processes still write during conversion or two writers own the same state | Quiesce old writers and change ownership once; use new scoped journals instead of supporting mixed writers |
| InstructionsStore.plan versus setup preview | A call labeled plan unexpectedly writes or requires permission | Keep effect classification explicit; APIs can be renamed/replaced rather than inheriting ambiguous names |
| compile_items and instruction_text delivery | K/M/project evidence gains developer/system authority | Reuse/factor the safe Instructions projection where useful; role-specific reference delivery is required |
| AppSessions.off and setup machine/task identity | Old delivery switches/IDs impersonate authentication and logout | New access owner and principal identities; old APIs may retire, but their current effects are not mistaken for the target |
| Catalog/root overrides, installer/setup/import and direct APIs | Protected data is reachable through a retained unguarded surface | Inventory all target-supported entrances including --repo; guard, replace or remove them, with no silent old-route fallback |
| App bridge inventories and release loading | A convenient arbitrary-command bridge bypasses scoped operations | Target bridge contains an exact typed allowlist and verified package identity; no duty to retain old bridge generations as executable |
| Tutor, learning promotion and author decision ledger | Logs or lessons are automatically turned into Team decisions or always rules | Reuse bounded algorithms and evidence principles; keep role/authority owners distinct and author code unshipped |
| Reset/uninstall paths and native host homes | Transition/logout deletes unrelated data or modifies another host's credentials | Explicit object/effect plan; selected data export/import or deliberate fresh start, with no blanket cleanup |
| Installer/package/gates/ontology | New runtime/tests are missing from installed payload or test discovery | Verify the target inventory, contracts and new nonempty suites; adapt or retire obsolete tests by an explicit target decision |

Exact current anchors and file hashes are in the evidence manifest. Symbols
are preferable to durable line-number assertions because subsequent edits move
lines. New identifiers and formats may change at cutover. Preserve source work and
selected historical evidence as data where needed; this does not require keeping
old executable snapshots or readers supported indefinitely.

### Protected Instructions: guard the target, retire obsolete paths

A different folder alone is insufficient while retained commands accept --repo,
custom state/user roots, direct catalog calls or known snapshot refs. P01 inventories
all entrances and explicitly selects reuse, replacement or retirement. New protected
sources/packets live in target-owned schema/layout and are never silently published
as public/personal catalog items. Reuse compile_items only as an authenticated
projection if the spike proves its output and side effects fit; extracting a smaller
compiler or replacing the old entrypoint is allowed.

Every supported target CLI/owner/catalog/install/setup/import/bridge/host/resume route
checks the target namespace and current access at its owner. Obsolete commands and
compatibility shims can be removed. They need no continuing translation layer and
must not silently fall through to an unintended target action. Test --repo, root
and path aliases, direct calls, stale handles and explicit export. New authentication
must not be bypassable through a retained convenience route.

Do not claim a historical binary learned the new guard or require a permanent
old/new runtime matrix. Cutover stops old managed writers and replaces supported
entrypoints; it does not promise to control arbitrary separately copied old binaries
or an OS owner reading plaintext. Already-delivered host context remains outside
recall guarantees. Selected historical records can be exported or archived as data
without maintaining native resume or executable old-state compatibility.

## 2. Implementation profile and code ownership

Use an additive Python runtime beside the current Instructions machinery.
The selected proposed home is `workenv/`, with role modules rather than a service
per concept. Author tests live under `gates/workenv/`; they must not ship. The
task graph lists narrower owner paths. Current `compose/` owners are reuse candidates. P01 may retire or simplify them
as part of the chosen target boundary; no compatibility wrapper is mandatory.
Avoid unrelated rewrites that do not improve the target or transition.

| New owner | Initial responsibility |
| --- | --- |
| contracts / storage / journal / trust | Versioned envelopes, immutable objects, scoped durable updates, request results and trust/control verification |
| identity / access / credential adapters | Local account-free identity, protected credential use, session generation, lock/signout/explicit reentry |
| authority / Team / lifecycle | Manual founding/enrollment, grants, exact reviews, finalization, controlled succession and all Team lifecycle effects |
| knowledge / memory / reading | Role-owned content and qualified bounded readers with separate reducers and revision domains |
| environments / preparation | Exact composition/adoption, personal or Team basis, selected-byte project evidence, required bodies and gaps |
| Instructions adapter / admission / host delivery | Role separation and guarded actual-recipient evidence at the target boundary |
| exchange / custody / carriers | Full/delta/return transfer, control-first verification, durable outbox and exact retained-copy evidence |
| auth adapters | Optional Google/Slack/OIDC identity evidence and guarded linking; never general Team authorization |
| CLI / TUI / Studio | Clients of typed operations; local GUI assets and protected bridge, no competing content or permission store |

Portable objects are immutable exact byte records. Mutable head/receipt/control
updates need a real atomic owner transaction and restart proof. Immutable files
plus a scoped transactional journal are the initial implementation profile;
SQLite is selected for that local mutable journal and explicitly derived indexes.
Versioned JSON/Markdown/table bundles are the portable source format; a live
database file is not mirrored between peers. The state DB is not wholly
rebuildable: keep authoritative refs, operation receipts, outboxes and controls
separate from disposable index tables, with supported consistent backup/recovery.
Do not create one global revision/transaction for every source and Team.

P01 must select and prove the concrete encoding, signature/verifier library,
SQLite transaction/durability settings and file-publication barriers, OS credential protection and local bridge
binding. Prefer maintained implementations and installed offline dependencies;
do not write custom OAuth/JWT/cryptographic primitives. The frozen binding record
contains versions, supported platforms, exact positive/negative examples,
recovery assumptions and packaging inputs. Missing platform protection means
unsupported protected operation, not a mock or plaintext fallback. This is a
bounded discovery/freeze task: later workers cannot invent these choices locally.

The initial GUI is a locally served presentation over these operations. No
Internet-only frontend dependency, hosted-only backend, mandatory login or
particular frontend framework is introduced by this spec. Freeze an actual
bridge/client binding in P01 before P11; preserve the bundled Textual owner and
its version/inventory where it is reused. OAuth setup is optional and later;
pure personal/manual-Team routes must already function without its credentials.

### Source homes, repository identity and concrete stored records

SSOT S03-sources, S04-scopes, S06-intake and S08-source-storage own the new
storage/scope/intake rules. A source namespace is the existing owner boundary
configured with one authoring home, not a new global business-content store.
Use package-published, repository-authored or managed source profiles. The repo
may hold docs/adr/ or docs/knowledge/ where explicitly bound; managed namespace
records can produce Markdown views. Never allow the repository document and an
editable managed twin both to own the same accepted state.

Required namespace data: stable source ID, owner/acceptance authority, role,
default home scope (personal/Team/repository/domain), applicability, authoring
home/adapter, format version, disclosure/retention and exact publication evidence.
Repository bindings carry stable repo/source identity separately from locator,
branch/commit and selected working bytes. Clones/worktrees can share a verified
source; forks need an explicit original-read or derived-authority binding. No
registration or project write is required for ad hoc inspection.

Each immutable revision directory carries a JSON manifest and exact member set
(Markdown, CSV/JSON tables, attachments as declared). The manifest's member hashes
bind content; the external revision digest is derived without self-hashing fields.
Decision/event targets and exact premises remain structured; long explanations
may be Markdown members. Acceptance is evidenced by owning receipts/events, not
a mutable status word in two files. The local transaction associates committed
heads and exact receipts only after required immutable objects are durable.
Test crash before/after body staging and DB commit; orphan objects stay unaccepted.
Database loss cannot reconstruct authority by scanning arbitrary staged files.

Provided domain packages and additions use one format. Implement at least one
real reviewed starter package, add/import/create/extend routes, and source-aware
comparison without silently changing installed publisher bytes or Team adoption.
The current compose/domains.json is an Instructions routing catalog, not the K
store. Repo ADR and Team ADR remain distinct home scopes with independently
verified source authority, even when one Team owns or references both. Reader
union preserves source-qualified IDs, required closure and conflicts; no automatic
Team/repo/supplied/newest precedence is introduced.

### Learning/distillation brownfield correction

The current collector v1 appends into InstructionsStore's host learning log;
_learning_item projects records as personal rule/always in selected future
snapshots, ignoring classification.layer for delivery semantics. It lacks the
new typed destination, repository/Team scope and exact source-span/authority
contract. It also affects the Instructions authoring revision. K/M candidates
must not be sent through that path or treated as already-promoted lessons.

The heavy session-distill pipeline is different: it compares against repository
Instructions, filters for generalizable principles and emits author-side
candidates/review bundles. Its clipping/generalization can remove names, periods,
repo-specific choices and reasons needed by K/M. It does not already implement
this generic intake service and does not automatically apply every output.
session-distill/ and its ledger are currently author-side in the package boundary.
Choose a supported packaged extractor adapter/subset for the new runtime, with
bounded explicit input and run-owned output; do not import author-only code or
scan all personal histories by default. Backward compatibility remains waived.

P19 owns typed local intake/candidate operations using P06's existing local
identity/storage/role providers. Preserve exact source records/frontier, capture
nonce and recipient restrictions, role and home/applicability scope, candidate
version and destination request. A new domain label cannot alter the global
Instructions routing manifest or ontology automatically. Actual recorded decision,
missing rationale and later model generalization are separate results.

Personal candidate use is an explicit unadopted research basis, not default
accepted memory. Publication and any widened Team applicability go through the
destination owner's exact request/receipt; installation/upload/capture/semantic
matching alone never promotes. Team promotion depends on P07/P08/P15 and its
late integration profile; P19 itself does not wait for Team or external services.
Preserve candidate/evidence and exact unknown outcomes. Signout or a changed Team
selection cannot redirect a late extractor result or restart it under a new nonce.

## 3. Contract set to freeze with concrete examples

Names below define meaning; P01 supplies versioned schemas and executable fixture
instances without altering those meanings. Public spelling changes after freeze
invalidate affected downstream work packets. Detailed role bodies remain owned
by their provider, not coerced into a universal business schema.

| ID | Input → result / owned effect | Mandatory refusal or qualification |
| --- | --- | --- |
| C01 Identity/reference | Scoped principal/Team/device/repository and source-home bindings, exact versioned source refs and verified bindings → stable IDs / exact bytes or unavailable | Mutable email/name/key is not stable identity; duplicate ID/different bytes and unsupported version fail |
| C02 Access session | Exact profile/device/session generation, action/resource/recipient, proof/control refs → allowed or specific access gap; lock/signout/unlock persist named local effects | Signed-out/old handles, silent refresh/reopen, wrong recipient, revoked/expired evidence and unsatisfied fresh-auth requirement cannot pass |
| C03 Owned operations | Typed intake/candidate and destination promotion; pure preview or durable candidate; sealed request with exact target/base/policy → owner commit plus atomic receipt; same-ID query/retry | No write from pure preview; durable plan is labeled; stale base, mismatched request, unknown/partial/cancel-too-late remain distinct |
| C04 Instructions / knowledge | Exact authorized Instructions source → guarded role projection; K view/question/conditions → coherent body and evidence | No retained unguarded protected-root bypass; K never enters instruction_text; missing applicability/companions stays explicit |
| C05 Decision memory | Explicit repo/Team/personal home scope, required subjects + sources/frontiers/work scope → state before ranking, why/history or evidence | Missing/cyclic/conflicting closure, restricted proof failure and false acceptance cannot revive an old choice |
| C06 Reader envelope | Scope/basis, required query set, role/view, question, processing/output budget and pinned continuation → body/qualifications/refs/omissions | Access before metadata; exact cursor binding; retained-body declaration is not a hash/parent receipt; no false completeness |
| C07 Preparation/composition | Personal/adopted/candidate/scoped-source basis, actual project bytes and declared operation → immutable preparation and separate action assessment | No synthetic Team/host/history; dirty-byte changes invalidate affected claims; selected/adopted/prepared/delivered differ |
| C08 Team governance | Exact founding/join/grant/review/adoption/lifecycle request + current source/Team policy → qualified approval/conditional effect | No bootstrap reuse, group self-add escalation, same-person extra vote, proposal self-authorization or source-right override |
| C09 Exchange/trust | Permitted exact inventory, prerequisites, authority lineage, controls and payload → staged/verified/accepted/committed receipts | Forgery, wrong audience, old control/fork, missing baseline/body, executable import and partial restriction failures cannot become ready |
| C10 Custody/retention | Peer/device generation + exact retained set/limits and governed cleanup plan → dated acknowledgment or copy-specific result | No quorum from copy count, silent cache eviction of promised data, unique-outbox loss, resurrection or global-erasure claim |
| C11 Recipient | Prepared role bodies + actual host/recipient/work link + rights/isolation → supported delivery result or explicit gap | No K/M authority promotion, unsupported/stale resume bypass, invented session ID, hash-only rehydration or automatic retry under a new ID |
| C12 Client/provider capabilities | Exact operation/capabilities, origin/draft/request/return state → real result and action-specific UI | No fixture success in real mode, local-origin-as-auth, repeated hidden confirmation, unauthorized metadata or state change from navigation |

Example shape for a protected operation (field spellings are frozen by P01):

```text
request: schema, request_id, actor/device, local_access_generation,
         action, owner/resource, exact target/base, recipient/work_scope,
         policy/control/proof references, payload_digest
result:  local_effect, provider_effect, actual_stage,
         exact output/receipt refs, material_gaps, supported_recovery
```

Do not put secrets/tokens/private keys in ordinary request journals, source
packages, context manifests, logs or peer data. Reuse current returned-as-context
vocabulary only at its actual evidence strength. A stored receipt cannot prove
that a model read, retained or obeyed the returned body.

### Access barrier and in-flight boundary

The updated SSOT S07-local-access fixes profile/install scope, `active/locked/
signed_out`, durable invalidation, explicit reentry and no automatic reauthentication.
Every managed protected entry checks the access generation at admission, and
presentation checks it again for late results. Never queue a new send under a
signed-out session. Permission changes still re-evaluate at owner execution.

A shared write dispatched before local signout can commit. Recover the same
request result; local signout is not cancellation or withdrawal. A separately
authorized member-PC finalizer continues only under its own declared lifecycle.
Session-derived child handles expire with the local session; already delivered
native context and independently delegated tasks have their actual limitations.
Local persistence failure denies affected access and reports incomplete durability.

## 4. Sequence, parallelism and usable milestones

The task graph is the executable ordering reference. All product tasks are still
planned. The plan checker validates topology and coverage; it is not a scheduler
or evidence that any implementation task has completed.

| Milestone | Relevant tasks | Exit evidence |
| --- | --- | --- |
| M0: safe starting point | P00–P01 | Complete isolated brownfield baseline, regression classification and frozen platform/contracts |
| M1: useful personal work | P02–P06, P10–P11; no dependency on P07/P08/SSO/GitHub | Account-free real sources → preparation → actual recipient/client; no fake Team or session |
| M2: Team without Internet services | P07–P09 plus the shared P10/P11 interfaces; run the M2 integration profile | Manual Team governance, exact environment adoption, actual recipient and real peer/package recovery without Google/Slack/GitHub |
| M3: full operations and clients | P11–P16 and P19 | Complete Studio/CLI/TUI routes, optional carriers/SSO, full Team lifecycle and advanced authoring/search/bulk/retention |
| M4: integrated qualification | P17–P18 including intake/promotion coverage | Named fault scenarios, actual supported adapter evidence, controlled cutover/package and exact integrated-tree gates |

After P01, identity (P02) and storage (P03) can proceed independently. After P03,
knowledge (P04), memory (P05), and eligible governance work use disjoint owners.
Optional GitHub (P12) and OIDC (P13) are independent once their listed foundations
are accepted. They never gate initial personal or manual-Team feasibility.
P01 may permit early UI layout/fixture work under a separate bounded packet,
but a fixture-complete screen remains unaccepted as real functionality until its
provider task passes. Do not maintain independent fixture state per screen.

Cap workers by available host slots and ownership, not an arbitrary parallelism
target. One coordinator owns shared integrations: `install.sh`, `package.json`,
legacy adapter files, bridge inventories, root docs, ontology and gates. Workers
submit patches/proposals for those shared files; no concurrent index writes.
Nested/overlapping owned roots also serialize even if graph prerequisites permit
parallel execution. P19 follows P06 for personal/local capture and feeds P15 candidate review; it is
not an M1 prerequisite. P15's graph/form, memory-editor and validation subitems may
split after contracts freeze, while all original acceptance stays mapped.

### Complete screen/operation coverage

| Capability retained from S11 | Implementation task(s) | Main tests |
| --- | --- | --- |
| Instructions source/member/trigger editing | P06, P11, P15 | N04, N20, current behavior comparison where relevant |
| Knowledge text/table/applicability and supplied/additional sources | P03–P04, P15 | N06, N20, N27 |
| Repo/Team source binding and single authoring authority | P03–P06, P08, P16 | N27 |
| Learning/session-distill intake and candidate promotion | P19, P15; Team integration P07/P08/P17 | N28 |
| Ontology graph and structured equivalent | P15 | N20 |
| Domain form/profile editing | P15 | N20 |
| Questions, pinned lenses, validation/findings | P15 | N20, N23 |
| Scoped search/ranking/history | P04–P05, P16 | N07–N08, N21 |
| Source/environment derivatives | P08, P16 | N12, N21 |
| Decision/workstream/outcome capture | P05, P15 | N07, N20 |
| Corrections/withdrawals/replacement | P05, P15 | N07, N20 |
| Permissions, approvals and policy | P07, P11 | N11, N16 |
| Personal identity, lock/signout and auth connections | P02, P13 | N02–N03, N18, N23 |
| Full Team/device/ownership CRUD/lifecycle | P07, P14 | N10–N11, N19 |
| Retention/deletion/evidence recovery | P14, P16 | N19, N21 |
| Bulk/import/export | P09, P16 | N13, N21 |
| Offline exchange and carriers | P09, P12 | N13–N14, N17, N22 |
| Concurrent change/reconciliation | P03, P07, P16 | N05, N11, N21 |
| Unknown outcomes and outage recovery | P03, P09–P10, P12, P16 | N05, N13, N15, N17, N22 |
| Actual recipient and context inspection | P10–P11 | N04, N15–N16, N23 |
| Provider administration | P12–P13, P16 | N17–N18, N23 |
| Scoped administrative signals | P16 | N21 |
| Explicit simulated test harness | P01 and each integration | N01, N16, N25; real mode rejects fixture fallback |

## 5. Intermediate tests and failure design

The test catalog defines positive and material negative oracles before coding.
Its `planned` files/commands do not exist yet; P00 supplies the actual prepared
Python/tool bindings before a runner expands command templates. Do not treat a
missing planned test as a passing test. Only B01/B02/B03 were executed in this
planning turn: 12 compatibility, 23 app and 3 transaction tests passed using
their temporary stores. They document the starting behavior; they are not
permanent target requirements. P00 classifies all present tests and P01 explicitly
keeps, adapts or retires them against the target. The full baseline/gate is not
certified by those three results.

| Checkpoint | Run and inspect | What it can establish |
| --- | --- | --- |
| K0 before workers | Source/contract hashes, actual test discovery, prepared tools and P00 baseline suites | Starting input and preexisting failure classification |
| K1 per owner | Task-scoped target cases plus relevant retained/adapted existing tests; real durable-store fault tests where touched | Owning behavior, direct bypass refusal, unchanged protected state and exact effects |
| K2 at client seam | Same actor/data/request through visible UI and direct CLI/MCP/API; origin/return and stale result tests | UI and execution agree for the tested scenarios |
| K3 at useful vertical slice | Personal start; manual Team first environment; governed source change; peer recovery; recipient continuation | Actual joined identity/source/body/receipt flow, not independent demos |
| K4 at supported deployment | Real platform credentials/host/provider, disconnected processes and controlled test clock; actual user/IME/SSH tests | Claimed adapter/platform/operating evidence with explicit unsupported/skipped limits |
| K5 before integration commit/release readiness | Exact integrated-index package/parity/ontology/mirror/new-suite gates, tarball and isolated target installation/cutover | What the candidate actually contains and preserves; not automatic publishing authority |

Per-task profiles select atomic case IDs and concrete adapter scopes during P01.
The family IDs in the catalog are coverage groups, not a requirement to pass the
entire future family's file at each early task. For example, P04 runs knowledge
reader cases; P05 runs memory cases; P10/P11 prove personal delivery/client behavior;
Team delivery is exercised by M2; full UI/provider coverage belongs to M3/P17. N27/N28 cases bind to their earliest
role/local profile; Team promotion and live extraction/package cases remain in
their later profiles. Source-binding and extractor tests cannot make P19 depend
on a Team or a network-only provider.
P01's real platform spikes exclude future external-provider and runner qualification.
A missing case binding is not ready, never an empty passing suite. The P01 freeze
task itself authors and verifies those bindings before implementation dispatch.
Shared conformance/fixture/index files have one integrator; each task owns its
unit tests under gates/workenv/units/<task-id>/. Concrete discovery is wired to
all these paths in P01/integration, with a nonempty subject requirement. Legitimate
empty memory and permitted empty selections remain valid product results.
Milestone profiles run once their accepted artifacts exist, independent of later
optional-task readiness; acceptance records their actual evidence separately.

Fault injection surrounds **observed durable boundaries**, not only a happy-path
final return: before/after candidate/object persistence, control learning, head+
receipt commit, outbox dispatch, acknowledgment, local access invalidation and
presentation. Require positive control first, named mutation/fault actually hit,
restart of the relevant process and preserved unique work. Assert one attributable
result on retry rather than merely a final matching head.

Cross the important dimensions selectively: personal/Team/source owner; consumer/
contributor/reviewer/executor; active/locked/signed-out; local/peer/GitHub/provider
reachability; valid/expired/revoked/unknown proof; none/draft/adopted/actual context;
missing/partial/verified bodies; active/archived/closed Team; first/current/child/
compacted recipient. Pairwise cases help breadth, but must include named interactions
G01–G04/P01–P03 and logout+in-flight commit, fresh restriction+partial import,
protected namespace+retained custom-root entrance, and archived work+replacement recipient.

Use self-contained fixtures so shrinking a live set cannot mute a negative test.
Introduce structural gate assertions with a negative control when runtime owners
land. New `gates/workenv/test_*.py` discovery must be explicitly wired into the
umbrella with a nonempty-subject check; the current Instructions glob excludes it.
Author tests and execution-plan files remain outside npm payload. Read the actual
gate before changing its coverage; no fixture or archive allowlist may hide a
runtime violation.

Live Google/Slack registration and real external consent are distinct from fake
issuer tests. Use controlled explicitly authorized test identities when available;
never print secrets. Missing live setup is `pending_external_evidence`, not green.
The runner may continue independent work; it cannot claim that adapter supported
or publish a full-product completion claim from a simulated result. Likewise,
do not replace actual novice/IME/accessibility observations with screenshots or
invent time savings. Intermediate named experimental coverage can be reported
with those limits; full scope remains outstanding until its required proof exists.

## 6. Dynamic AI development protocol

### Work packet and result contracts

Each worker receives actual artifact paths and bounded content, not a transcript
dump: run/task/attempt identity; SSOT/spec/plan/contract/input hashes; accepted
predecessor result refs; chosen role and available verified tool/model capability;
owned paths and shared-file proposal rules; exact target and exclusions; required
test IDs/commands after binding; done criteria; constraints and stop/replan signals.
Do not infer access/permission from the packet or silently switch to a fallback
model/provider and report the requested one as used.

Return an attributable result containing baseline and output tree/delta, changed
paths, artifacts and their digests, commands and actual exits/subject identities,
skips/prerequisites, findings/decisions and unresolved work. A status notification,
empty report or natural-language “done” is not accepted output. Preserve meaningful
failed attempts and unique artifacts; do not overwrite an unknown outcome with a
new task identity after interruption.

Development run state lives separately from the frozen plan in an author-side
run directory. Track `planned/ready/running/needs_revision/pending_evidence/
accepted/invalidated/canceled` with exact attempt/result references. Persist state
before declaring a dispatch/result transition. The plan checker here is only
static validation; a later chosen runner must prove N25 before unattended use.

### Scheduling and integration

```text
read the fixed plan and current verified run state
invalidate results whose inputs or contract dependencies changed
ready := tasks with all predecessors accepted and freeze prerequisites satisfied
choose ready work with nonoverlapping owner resources within available slots
dispatch bounded packets; persist exact attempt handles
validate result artifacts, scope and actual tests
review material risks with a separate appropriate perspective
integrate one accepted delta at a time; rerun affected seams on the combined tree
accept only the verified integration result; unlock dependent tasks
```

Use separate isolated source workspaces based on P00, with `feat/` branches if
branches are created. Only the integrator stages shared commits. It verifies
incoming base fingerprints against current inputs and applies a delta, never
copies a worker's whole checkout over others' work. Stale disjoint changes may
be rebased and reverified; same-owner/contract changes return to the owner. The
index-snapshot hook must judge the final staged set, including new untracked
files; bypassing it or racing another staging operation is not integration.

Keep semantic review and deterministic gates separate. For security/authority,
use a reviewer that inspects the real code/evidence; record actual independence
and limits rather than claiming a new subagent guarantees provider diversity.
Fix within the authorized scope autonomously. Repeated fresh instances of the
same root cause, a broader authority/data-loss boundary, unfrozen public contract
or conflicting inputs trigger a bounded redesign task. Do not endlessly patch
instances or weaken tests to end a round.

Replanning writes a new plan/contract revision linked to prior attempts, maps all
unfulfilled requirements/tests to successor tasks and invalidates only dependent
evidence. A runner cannot drop coverage, relax source policy or change accepted
product scope on its own. External authorization or missing user intent is sought
only when actually required; ordinary reversible work stays within the existing
authorization. Do not turn local product governance approvals into automatic
permission to contact people, grant real access or publish a release.

## 7. Controlled transition, target package and completion

The user does not require backward compatibility. Choose one supported target
runtime/schema/entrypoint set. Remove obsolete command aliases, serialized readers,
bridge/resume routes and upgrade/downgrade machinery where they add no target value.
Existing tests can be retained, adapted or retired with a reason and replacement
oracle for any still-required behavior; do not preserve an API merely to keep a
legacy test green.

P00 captures the current source baseline. Before actual user cutover, inventory
which personal sources, decisions, drafts, pending operations and evidence the
operator elects to carry forward. Use one explicit export/transform/import for
that known data, or an explicit fresh start after disposition. There is no required
automatic migration for every historical release, stable old command spelling,
native session resume or mixed-version writer support. No choice here authorizes
silently deleting data, relabeling personal content as Team-approved or uploading it.

Cutover is prepare → validate target/import → quiesce old owned writers → switch
owned entrypoints/state ownership → verify target → retain/dispose source data as
explicitly planned. Unknown old operations must be reconciled or retained with
an exact recovery obligation before their writer disappears. Do not run old/new
writers against one mutable store. A failed pre-switch conversion keeps the source
usable; after new writes begin, use target-version recovery or a governed inverse,
not a blind copy of old state that loses new work or revives revoked controls.

After quiescing old writers, recheck that the selected source-data revision still
matches the export baseline. Capture and validate any remaining changes before
switching ownership, or quiesce before the final export. Do not switch while
selected data or unknown-operation disposition is unaccounted for. A conversion
validated while its source was still changing is not a final cutover proof.

Package the actual target runtime/assets and offline dependencies, with author
specs/tests excluded. Update target bridge inventories, surface/endpoint contracts,
ontology and mirrors through their owners. Teach only commands the new runtime
supports. Verify fresh installed lookup and the selected cutover in temporary
user/state roots; preserve unrelated native host accounts/configuration. New
endpoint activation, OAuth consent, source export and publication still have their
actual authorization boundaries. Small user count simplifies compatibility policy,
not the new system's access, durability or honest-result requirements.

Completion reports accepted task IDs, exact integrated tree, actual test/adapter
coverage and remaining scope. Missing external/user evidence is explicit. A mock,
empty discovery, skipped check, completed package or elapsed budget cannot turn
an unfinished task into accepted work. The output of P18 is a reviewable target
release/cutover result; publishing or deploying it is a separate actual action.
