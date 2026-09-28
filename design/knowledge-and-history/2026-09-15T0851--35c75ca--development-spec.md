---
created_at: 2026-09-15T08:55:34+09:00
head: 35c75ca
kind: design
status: implementation-process-specification-no-product-implementation
design_ssot: 2026-09-15T0851--35c75ca--consolidated-design-ssot.md
task_graph: 2026-09-15T0851--35c75ca--development-plan.json
test_catalog: 2026-09-15T0851--35c75ca--test-catalog.json
baseline_evidence: 2026-09-15T0851--35c75ca--brownfield-evidence.json
---

# Team environment expansion — brownfield development specification

## Authority and execution scope

The [SSOT](2026-09-15T0851--35c75ca--consolidated-design-ssot.md) owns product
meaning, required scope and policy boundaries. This document owns implementation
boundaries and work acceptance against it. The [evidence graph](2026-09-15T0851--35c75ca--development-plan.json)
owns one node/dependency model for builds, verification and qualification; file ownership and required evidence. The
[test catalog](2026-09-15T0851--35c75ca--test-catalog.json) owns named test-family
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

Validate the active planning bundle and its executable regression suite:

```bash
python3 gates/check-development-plan.py
python3 gates/check-development-plan.py --self-test
```

The stable gate resolves the one CURRENT selector, verifies exact current bundle
members, runs the dated validator in normal mode and actually executes its bound
regression helper. It does not dispatch work or require unimplemented product tests
to pass. The initial brownfield snapshot comparison is a dispatch-time check, not
an eternal commit gate on future implementation changes.

To examine supplied run evidence without executing it, use the dated checker with
`--run <run-evidence.json>`. Exit 0 means the requested terminal/mode conditions
are satisfied; exit 2 means valid evaluated evidence has not satisfied terminal
acceptance; exit 1 means an invalid bundle/input. Nonterminal readiness is in the
JSON `ready` field for the explicitly requested mode. A runner uses the same
`evaluate` contract before dispatch, not a second task-only shortcut.

## 1. Brownfield input and transition constraints

HEAD `35c75ca` alone is insufficient: canonical Instructions modules/tests are
among the current untracked files, while the naming migration and other work
modify tracked sources. [Selected evidence](2026-09-15T0851--35c75ca--brownfield-evidence.json)
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
evidence graph lists narrower owner paths. Current `compose/` owners are reuse candidates. P01 may retire or simplify them
as part of the chosen target boundary; no compatibility wrapper is mandatory.
Avoid unrelated rewrites that do not improve the target or transition.

| New owner | Initial responsibility |
| --- | --- |
| contracts / storage / journal / trust | Versioned envelopes, immutable objects, scoped durable updates, request results and trust/control verification |
| identity / access / credential adapters | Local account-free identity, protected credential use, session generation, lock/signout/explicit reentry |
| authority / Team / lifecycle | Manual founding/enrollment, grants, exact reviews, finalization, controlled succession and all Team lifecycle effects |
| knowledge / memory / reading | Role-owned content and qualified bounded readers with separate reducers and revision domains |
| environments / preparation | Repository/personal/Team composition, per-role source collections, effective units and selection provenance, required winning bodies and gaps |
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
storage/scope/intake rules; S05-scope-composition owns default application.
Separate namespace scope (repository/person/Team), role collection and source
authoring authority. Each scope has Instructions, knowledge and memory collections;
source manifests still have one authoring home. No global business-content store
or mixed editable effective source is introduced.
Use package-published, repository-authored or managed source profiles. The repo
may hold docs/adr/ or docs/knowledge/ where explicitly bound; managed namespace
records can produce Markdown views. Never allow the repository document and an
editable managed twin both to own the same accepted state.

Required namespace data: stable source ID, owner/acceptance authority, role,
source home scope and applicability, authoring
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
verified source authority, even when one Team owns or references both. Reader composition applies repository > personal > Team to Instructions/knowledge
units under applicable conditions; decision conflicts use explicit user arbitration. Source-qualified IDs, history and qualifications
remain intact. Publisher origin/domain does not introduce a fourth priority layer.

### Scoped composition implementation

P03 provides independently addressable scope × role collection heads, bindings,
objects and drafts. P06 resolves Instructions/knowledge order and version-bound decision-use preferences;
P04/P05 own applicability and source-internal decision lifecycle semantics. P11
shows the nine original positions and a separate effective view. A prepared or
rendered snapshot may be retained for continuity but is not an editable original.

An entry retains layer, role, source/owner, exact revision/frontier, enabled state
and any explicit overlap key/ref. Use bounded role-specific units; title matching
or a generic LLM semantic merge is not an identity contract. Unkeyed prose is
delivered in distinct labeled layers: repository-first for Instructions/knowledge,
and user arbitration for recognized decision conflicts. Absence of keys does not
authorize an automatic decision winner. P01 freezes examples
and current-host bindings. Include native project/global instruction inputs in
that inventory: map repository inputs and personal inputs without duplicate
injection or a false precedence claim about an unsupported host. No mandatory
Team registration or write into a merely observed repository is introduced.

Resolve enabled/applicable unit metadata, source-internal state and local selection,
then apply Instructions/knowledge scope order or the decision-arbitration branch
per overlapping concern. Unrelated lower entries remain.
Derive body/dependency requirements from winners; a shadowed or disabled Team
entry's mandatory flag, denied body or absent network must not block independent
local use. Missing/denied winning required startup material remains a gap, not an
empty higher layer silently satisfied by a lower one. Task-specific issues can
wait for the actual request; no first-screen goal/target form is added.

Turning a source/position off excludes that selection until reenabled; other layers
may still contribute. Preserve on/off state across restart/recomposition. Same-layer
Instructions/knowledge conflicts use explicit selection/order or remain qualified
for the affected query; decision conflicts do not get a winner from that order.
An explicit user composition preference can vary the default and is captured with
the preparation; a source body cannot secretly replace the resolver policy.

Changing own repository/personal work content requires no Team approval, readoption,
waiver or P07 connection. Do not invoke Team governance merely because a lower Team
rule disagrees. Actual source reads/disclosure/exports and Team source/grant/shared
state changes retain their own narrow authorizations; priority never creates them.
Keep rights on protected bytes actually reused, not on independent replacements.
The selected default is for efficiency, not a Team content-compliance service.

P06 uses pure resolver plus local provider cases, and M1 remains a real local-only
path. Real Team source/rights integration is M2; full source editing/export is M3.
P10/P17 verify that a later override changes future preparation without changing an
existing session's exact pin/body. Subject fingerprints include the resolver/order,
collection bindings, role adapters and actual receiver projection. Do not mark
an old acceptance current after those inputs change.

### Decision-use arbitration

S05-decision-arbitration is a required exception to scope priority. P05 derives the
applicable current decision set and conflict, preserving lifecycle/conditions and
comparison coverage. P06 admits the actual logical use only after a valid user
answer or current keep-mode preference. P03 stores private preferences, questions,
answers, use receipts and invalidations atomically, including backup/restart. P11
and host adapters present the relevant question; an unattended/unsupported prompt
route returns pending_user instead of selecting the repository alternative.

No current task/use means no compulsory decision prompt. Compatible/empty memory
is valid. A conflicting use has no automatic winner. Obtain an explicit source selection or bounded user resolution
and keep-until-change or ask-each-use mode, with no prechecked consent. A later ask
under unchanged ask-mode requests the application only; mode can be changed by the
user. After an input change, any remaining conflict obtains a fresh application/mode;
compatible or empty current material needs no arbitration.

A stable concern identity is separate from its changing basis and each use ID.
Do not derive the lookup identity only from the chosen record or candidate hash,
which could leave obsolete consent available to reappear later. Trusted host/user
answer evidence is required; an agent-written success/consent flag is not an answer.

A preference binds principal, question/conditions, repository/Team/selected-decision-source
context and every relevant participant's source/record/revision/lifecycle identity,
plus relevant-set change continuity and coverage. Do not key it by session ID or
only by the chosen body. Relevant participant/set changes invalidate before the
next use; unknown rights/coverage cannot be bypassed by a preference. Revalidate
at answer admission and actual use. After a known change, old matching bytes do
not revive the invalidated record. Unrelated source updates can preserve it after
revalidating the relevant set; a raw whole-Team frontier equality check is too broad.

Use stable tool-owned logical-use and question identities. Retry/page/reconnect
of one unchanged use restores the same pending question or answered result;
ask-mode prompts again on the next distinct use. Changing the basis invalidates an
old answer even if its logical-use ID is unchanged. A changed basis creates a new
question version with its own sealed identity, not an edited request payload. P01 freezes concrete source
revision/change evidence and a bounded protocol; no global revision service or
universal semantic conflict engine is added. Offline reuse is qualified by the
verified local basis and actual source conditions, then invalidated on a received
relevant change. Preserve previous delivered snapshots and source decisions.

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

A locally owned candidate or override may support ordinary local work, preserving
its actual unadopted/candidate status. It does not become accepted Team memory;
local use is not restricted to research solely because Team adoption is absent. Publication and any widened Team applicability go through the
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
| C05 Decision memory | Explicit repo/Team/personal sources and current lifecycle → qualified state; conflicting actual use → user application/mode bound to its full relevant basis | Missing/cyclic/conflicting closure, restricted proof failure and false acceptance cannot revive an old choice |
| C06 Reader envelope | Scope/basis, required query set, role/view, question, processing/output budget and pinned continuation → body/qualifications/refs/omissions | Access before metadata; exact cursor binding; retained-body declaration is not a hash/parent receipt; no false completeness |
| C07 Preparation/composition | Separate repository/personal/Team role collections, explicit selection/order, observed project bytes and declared operation → immutable preparation and separate action assessment | No synthetic Team/host/history; dirty-byte changes invalidate affected claims; selected/adopted/prepared/delivered differ |
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

## 4. One graph for work and evidence

The previous graph made build work executable while treating milestone tests as
side notes. Schema 2 uses **one node and predecessor model** for baseline, contract
freeze, implementation, package production, verification and runner qualification.
A node produces artifacts and, where declared, a specific evidence claim. The
catalog declares mandatory acceptance obligations independently of the graph;
each needs exactly one compatible producer with the required profile, cases and
subjects. Merely preserving an ID or listing a family is insufficient.

| Node group | Function and dependency |
| --- | --- |
| P00 / P01 | Coordinator-controlled source baseline, contracts, case/fixture/adapter-contract binding registry and scoped subject-resolver specification |
| P02–P16 / P19 | Product implementation with existing owner/dependency limits; P19 follows local P06 and feeds later candidate UI |
| M1 | Real personal journey verification from its local predecessors, with DEL-PERSONAL; no Team/external product dependency |
| M2 | Real manual-Team journey and actual recipient verification, including DEL-TEAM, from its declared Team/local predecessors |
| M3 | Complete required operations verification after their implementations, including intake/promotion; does not wait for P17 or the final package |
| P18 | Build immutable candidate package/inventory and isolated cutover plan from accepted implementation; no source repair or real user cutover here |
| P17 | Product-read-only integrated validation; depends on passed current M1/M2/M3 and accepted P18 candidate; includes Team recipient cases |
| M4 | Product-read-only final installed-candidate and controlled cutover verification; consumes P17/P18, CAP-14 and every terminal obligation |
| R0 | Coordinator-controlled qualification of the selected runner/configuration after P01; required before unattended dispatch, not an unconditional product dependency |

Six terminal claims are required: personal work, Team work, complete operations,
local backup restore, integrated target and package readiness. The local-backup
claim is produced by P03's N05 evidence; the others have explicit verification
nodes. A seventh claim, runner-qualified, is conditional on unattended mode.
Coordinator-controlled completion may leave R0 unexecuted. This means active
coordinator dispatch/review, not a demand for repeated human permission clicks.
A runner cannot silently downgrade a requested unattended run to coordinator mode.

P18 now produces the package **before** final verification. Candidate construction
can test its own produced artifact; CAP-14 tests the already accepted P18 artifact
at M4. An own candidate is not an accepted-self prerequisite. Build→verification→
build and verification→later-package cycles are rejected by the same graph traversal.

Verification nodes write only isolated test/evidence outputs. On failure they
return failed/pending evidence and a repair request to an owning implementation
node in a successor plan/attempt. They never modify product code behind a passed
result. Packaging also cannot fix shipped source or manifest code incidentally;
return such edits to their owner before rebuilding and reverifying the candidate.

After P01, identity and storage can proceed independently; knowledge and memory
follow storage, while manual governance can proceed when identity is available.
Personal P10/P11 remains independent of Team/SSO/GitHub. Optional carriers and auth
adapters retain their later predecessors. All parallel work additionally respects
file owners, the integrator-only shared paths, actual current evidence and mode.
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
| Nine scope/role collections and repository-first effective composition | P03/P06/P11; M1 local, M2 actual Team, M3 source operations, P10/P17 pin continuity | N27, N16, N15 |
| TUI entry: options, selected basis, execution choice and next effect | P11; real personal M1, Team M2, shared operations M3; actual observations P17 | N16, N26 |
| Explicit simulated test harness | P01 and each integration | N01, N16, N25; real mode rejects fixture fallback |

### TUI entry implementation slice

S11's [TUI entry contract](2026-09-15T0851--35c75ca--consolidated-design-ssot.md#s11-tui-entry)
is part of P11, with U04/U10/U11 coverage. The current host mode picker,
Instructions authoring screen and installation wizard are separate brownfield
entrances; classify their routing before changing any one menu. Do not rename
SWE/Builder buttons and leave professional role, Instructions loading and execution
configuration conflated. A known host goes directly to W01 environment/startup preparation;
the generic Studio hub serves arrival without a specified job. Direct links and
existing recipients retain their exact authorized routes.

The first screen derives only permitted cwd/repository/revision and bounded recent
checkpoints. It cannot infer a current goal, business target, next requested action
or overall completion. Remove goal/location-as-task forms and prefilled intentions.
A proposed new session is a start choice, not a known new-task request. Preserve
exact execution resources/recipients where supplied or explicitly selected.

Without a task request, W01 validates environment access, declared essential
orientation and session-start conditions; task support is not assessed. Source
maps/checkpoints are allowed; task-specific K/M queries wait for the actual host
request. Instrument the entry/selection/startup checks to prove those queries were
not called. A missing goal does not block starting; missing essential startup
material or rights still can.

Keep design/review criteria out of ordinary product copy. Render real environment,
source, tool and permission values with concrete action labels. Normal startup
performs owner validation and dispatch under one named start action; block with
a specific reason/remedy when necessary. No dedicated effect panel or universal
preview-confirm-start wizard is required. Retain material rights, additional model
calls and shared effects where the user chooses them. N16 evaluates the actual
action/state transitions and N26 evaluates human comprehension, not the presence
of meta headings, a fixed panel count or a fixed number of clicks.

P01 freezes examples of choices, explicit selection, expected next effect and
observed result using C07/C11/C12 evidence. Distinguish focus from selection and
installed/configured material from prepared/delivered context. Include each route's
scope, supported action, material gap and stale/unknown recovery. This is a thin
client projection, not another authoritative state store or a generic UI engine.
Freeze the actual terminal/locale support and observation protocol before making
support claims; do not freeze a pixel layout, menu count or old mode spelling.

P11 implements the common shell and actual personal preparation/recipient path.
Two bounded packets may proceed in parallel: one owner builds TUI rendering and
interaction; an independent owner writes state/effect oracles under the P11 unit
home. Shared launcher/install/setup/locale/bridge paths integrate serially through
the integrator. Existing tests may be adapted for choice preservation, slow lookup,
80×24 and locale behavior; their old menu labels are not permanent requirements.
The personal slice does not wait for Team, SSO or an actual usability participant.

The shell displays capability-declared future views honestly. M1 verifies real
personal/empty-repository entry, M2 binds multiple Teams/offline evidence, and M3
binds lifecycle/shared unknown operations. Later UI changes return to the owning
build work; these verification nodes do not edit product source. P17 consumes
current evidence and N26 actual comprehension/Korean terminal observations of the
integrated P18 candidate. Missing observations remain pending, never replaced by
AI role-play or browser clicks. An earlier formative study is reusable only for
its unchanged measured subject and scope, not automatically for later Team paths.

Current and final tested-subject manifests must include relevant rendering,
key handling, locale text, option-to-operation mapping and shared provider state.
Copy changes can invalidate comprehension evidence even when business logic does
not change. Changing unrelated source material does not mandate a new UI study.
Observe the exact candidate; repeat only affected support/interaction claims.

## 5. Intermediate tests and failure design

The test catalog defines positive and material negative oracles before coding.
Its `planned` files/commands do not exist yet; P00 supplies the actual prepared
Python/tool bindings before a runner expands command templates. Do not treat a
missing planned test as a passing test. The original 17:20 planning baseline
executed only B01/B02/B03: 12 compatibility, 23 app and 3 transaction tests passed
using their temporary stores. Those dated results document starting behavior; they are not
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
Atomic definitions own case meaning and prerequisites; profile selection lives only
in `profiles.required_atomic_case_ids`, with no separately maintained reverse list.
The family IDs in the catalog are coverage groups, not a requirement to pass the
entire future family's file at each early task. For example, P04 runs knowledge
reader cases; P05 runs memory cases; P10/P11 prove personal delivery/client behavior;
Team delivery is exercised by required M2 and integrated P17; full UI/provider coverage belongs to M3/P17. N27/N28 cases bind to their earliest
role/local profile; Team promotion and live extraction/package cases remain in
their later profiles. Source-binding and extractor tests cannot make P19 depend
on a Team or a network-only provider.
P01 freezes the runner-interface/preflight case contract. R0 executes the selected
runner qualification after that freeze and before unattended dispatch; future
external-product provider qualification stays with its own later nodes.
A missing case binding is not ready, never an empty passing suite. The P01 freeze
task itself authors and verifies those bindings before implementation dispatch.
Shared conformance/fixture/index files have one integrator; each task owns its
unit tests under gates/workenv/units/<task-id>/. Concrete discovery is wired to
all these paths in P01/integration, with a nonempty subject requirement. Legitimate
empty memory and permitted empty selections remain valid product results.
M1/M2/M3/M4 are executable verification nodes with normal accepted predecessors.
Their required evidence is consumed by downstream nodes and terminal obligations,
not stored in an optional side table.

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

N16 entry tests compare different focused, selected, installed and delivered
references against actual request/receipt effects. Fixture strings and rendered
screens can check state/geometry; they do not establish actual Korean composition,
SSH/screen-reader support or comprehension. N26 requires first-exposure users to
state options, selection and predicted effect/target, then compare their action's
observed outcome; record help, confusion, exact UI subject and unresolved critical
misinterpretations. Actual Korean composition/commit/cancel, paste and resize are
observed in the claimed terminal environment. P01 fixes the bounded protocol and
participant/support scope; disclose the actual sample and limits. Do not infer
universal optimality or productivity from a small formative study.

Live Google/Slack registration and real external consent are distinct from fake
issuer tests. Use controlled explicitly authorized test identities when available;
never print secrets. Missing live setup is `pending_external_evidence`, not green.
The runner may continue independent work; it cannot claim that adapter supported
or publish a full-product completion claim from a simulated result. Likewise,
do not replace actual novice/IME/accessibility observations with screenshots or
invent time savings. Intermediate named experimental coverage can be reported
with those limits; full scope remains outstanding until its required proof exists.

## 6. Evidence validity, admission and replanning

### Work packets and current measurements

Each packet binds run/node/attempt, exact plan/node/catalog/profile identity,
accepted predecessor result digests, required input and candidate artifacts,
current subject fingerprints, scope/file ownership, observed mode/runner identity,
required cases and done criteria. R0 binds the selected runner executable/configuration
and the preflight adapter contract; its fingerprint is not a model's self-report.
The product source and user authorization boundaries remain unchanged.

P01 freezes a registry of concrete case IDs, canonical family mappings, fixtures
and **adapter-contract** fingerprints for every node profile. This declares test
inputs/interfaces; it does not assert that future product adapters or live credentials
already exist. Actual implementation/tool/provider identities are measured in the
appropriate tested subject and qualification evidence when those nodes run. Changing
a shared registry is a contract revision and invalidates its dependent proof.

The coordinator/qualified runner measures current subjects independently of past
receipts. A subject manifest identifies its real source/config/fixture/adapter or
artifact closure, including shared dispatch/schema paths that can affect it. Unknown
closure is not a current fingerprint. The evaluator compares those measurements;
it does not magically discover dependencies or establish that a dishonest operator
ran a test. P01/N25 must prove the actual resolver/recorder binding used for execution.
Unrelated changes outside a declared sound subject need not invalidate it; shared
contract changes invalidate the affected dependent graph. Preserve old evidence
and unique work rather than resetting the run or relabeling a past result.

### One acceptance predicate

A passed label alone never establishes acceptance. Every selected result must have:

- correct run/node/attempt and exact fixed plan/node fingerprints;
- the current frozen profile/case/fixture/adapter-contract binding;
- every required case present and passed, including mandatory atomic cases under
  their canonical family, with no skipped/pending/unsupported substitute;
- the required evidence class: a deterministic fixture result cannot qualify a
  real runner, provider or user/platform observation when the family requires it;
- current tested-subject fingerprints and the exact accepted predecessor receipts;
- a complete existing evidence-artifact inventory with matching bytes;
- an allowed recorded mode and product-change evidence consistent with the node's
  effect class; verification/qualification and candidate packaging cannot repair
  product source;
- for unattended work, a previously accepted matching R0 qualification reference
  at dispatch and the same current runner/configuration fingerprint.

P01's registry artifact must match the supplied current registry; per-node bindings
cannot be changed behind that freeze. The author-side evaluator validates these
relationships and file identities over supplied observations. Actual commands,
source measurements and observed results come from the selected trusted runner,
not LLM-written success strings. R0's real preflight proves that integration before
unattended work; synthetic checker fixtures do not qualify a real runner.

Failed, pending, running, canceled or unknown selected results are neither accepted
nor automatically redispatched. An in-flight attempt overrides an old selected pass.
Reconcile an unknown attempt or explicitly create a successor/retry disposition,
retain earlier attempt evidence, and then obtain fresh acceptance. A previously
passed result made stale by a relevant input change can be revalidated; it cannot
remain current merely because its node ID is unchanged.

### Scheduling and terminal conditions

```text
resolve current bundle, frozen case registry and measured subjects
validate one DAG containing build, verification, package and qualification nodes
recursively accept only current, complete results with accepted predecessor evidence
choose explicit requested mode; never silently fall back
for unattended mode, require current R0 before admitting a worker/command
ready := unstarted or stale-passed nodes with accepted predecessors and bound cases
         minus unresolved in-flight/failed/pending attempts and resource conflicts
dispatch a bounded packet; record admission, exact attempt and qualification reference
build candidate / run tests / collect real effects and evidence
integrate permitted owner delta; remeasure affected subjects and revalidate
accept the result only through the same predicate; unlock all kinds of dependent node
terminal := accepted M4 plus every mandatory terminal claim on current evidence
```

P00, P01 and R0 are coordinator-controlled bootstrap, preventing qualification from
requiring its own unattended execution. A coordinator-only product run can complete
without R0; it cannot claim unattended assurance. Later R0 qualification does not
rewrite historical record modes. Runner/configuration change invalidates its current
qualification and dependent unattended reliance; preserve artifacts and revalidate
rather than deleting work. The result separates product acceptance, requested-mode
readiness and their combined terminal condition.

A changed Team subject invalidates M2 and its consumers, while an unchanged M1 can
remain valid. A changed verification attempt changes its evidence digest, requiring
consumers to use the new result. A changed package invalidates package-dependent
verification. The final node observes the exact P18 candidate, not whichever source
checkout or previous package happened to pass earlier.

Use isolated workspaces from P00 and a single integrator for shared source/index
writes. Scope changes create a dated successor plan; map all remaining requirements
and invalidate affected contracts/evidence. P01 owns contract changes, implementation
owners own repairs, verification nodes own judgment. Do not weaken an obligation,
change mode, forge evidence, or drop a case merely to finish. External authorization
is sought only when actually required; routine authorized work continues.

### Recovery evidence classes

Process restart, local backup restore, peer reconstruction and controlled cutover
are different claims. P03/N05 owns restart and consistent local-state backup recovery;
P09/N14 owns peer reconstruction; M4/N24 owns final controlled test cutover. P18 only
produces its candidate. N05's BKP-RESTORE/INTEGRITY/COVERAGE/PASSIVE cases are required
by a terminal-consumed local-backup obligation, not interchangeable with N14.

The local test uses low-level C03 fixtures before Team/P19 exist: covered private
draft/candidate, undispatched outbox, unknown-operation identity/receipt mapping,
control/sequence state and exact object closure. Restore after actual loss of the
live DB, not merely process restart. Reject inconsistent or missing members and
state the backup's coverage/RPO under the configured policy; do not promise unknown
post-backup work recovered or absent. Restored authority/access remains passive.
Later P07/P09 integration proves actual current-policy/key/fencing behavior; a passive
label alone is not an active-writer safety proof. These are scheduled product tests,
not a claim this planning repair implemented or executed the backup subsystem.

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
an unfinished task into accepted work. P18 produces the candidate; M4 verifies its installed/cutover readiness. Publishing,
deployment or real user-data cutover is a separate actual action.
