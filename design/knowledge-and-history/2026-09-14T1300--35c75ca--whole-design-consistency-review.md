---
created_at: 2026-09-14T13:00:57+09:00
head: 35c75ca
kind: review
status: findings-open-not-a-clean-certification
inventory: 2026-09-14T1300--35c75ca--consistency-audit-inventory.json
---

# Whole-design consistency review

## Verdict and scope

Do not mark the complete design and its prototypes contradiction-free. After
applying explicit amendments, this review found no demonstrated hard
contradiction between the main currently intended architectural principles.
It found **four consequential underspecified boundaries** and **three reproduced
prototype/wireframe mismatches**. A coherent architecture does not establish
complete operational rules or correct UI.

The [frozen inventory](2026-09-14T1300--35c75ca--consistency-audit-inventory.json)
records 38 pre-audit artifacts: 32 Markdown documents and 6 HTML artifacts.
Hashes establish review-subject identity, not proof of every assertion. The
semantic review used the current owning contracts, their explicit amendments,
the requirement board and relevant predecessor/QA records. Three delegated
reviews covered governance/storage/lifecycle, sources/consumption/cold start,
and UI/prototype behavior. These are separate analysis contexts, not human or
cross-provider validation.

This is a design review plus selected browser counterexamples, not formal
verification, production security testing or a usability study. Findings remain
open until their closure conditions are met. Proposed wording is not a tested
implementation or a policy already accepted by the user.

## Classification and effective sources

- **Hard contradiction:** two simultaneously applicable rules require mutually
  incompatible outcomes for the same state/action.
- **Underspecified boundary:** a required case permits materially different
  implementations because an input, owner or transition is undefined.
- **Prototype mismatch:** a fixture disagrees with its scenario or intended contract.
- **Superseded history:** an explicit amendment changes an earlier claim.
- **Accepted tradeoff / unverified property:** a stated limitation or an outcome
  needing implementation evidence is not automatically a contradiction.

Priorities below express consequences if carried into implementation, not an
exploit discovered in shipped code. A later timestamp alone does not repeal an
earlier source authority; scope and explicit amendments determine precedence.

| Boundary | Effective design source | Disposition |
| --- | --- | --- |
| Purpose, three roles, Team identity | AGENTS purpose; 18:04 purpose; 20:27 Team amendment | Coherent in the reviewed scope |
| Editions and evolving memory | 18:57 storage + 21:38 consumption | Static selection and per-operation frontier remain distinct |
| Permissions and approval | 23:36 governance + 00:03 offline amendment | G01 group authority is underspecified |
| State closure and privacy | 21:38 consumption + 00:03 offline packages | G03 portable qualified state is underspecified |
| P2P/GitHub | 01:07 peers + 01:14 direction + 01:27 setup | Optional recommended GitHub and complete P2P remain compatible |
| Team lifecycle | 01:32 CRUD + 01:35 scenarios | G04 recipient replacement during archive is underspecified |
| Cold-start preparation | 11:08 source contract over earlier W01/W09 | G02 selection/acceptance basis is underspecified |
| UI and channels | 07:58 disposition + 09:14/09:15 surfaces + 10:47 hub | No mandatory hub/GUI; three fixture mismatches below |
| History and deletion | Storage/offline + Team lifecycle | Unavailable history and limited purge are admitted; P03 overblocks evidence recovery |

Times identify the dated files in the inventory. Exact sites follow.

## G01 — Effective rights through group membership

**P1 · Authorization underspecification.**

[Governance:65](2026-09-13T2336--35c75ca--studio-governance-design.md:65) permits
groups as grant principals. [Governance:156](2026-09-13T2336--35c75ca--studio-governance-design.md:156)
limits delegated powers and requires review for privilege expansion.
[Team CRUD:155](2026-09-14T0132--35c75ca--team-crud-and-creation-design.md:155)
governs Team membership, but does not resolve an externally managed group's membership.

**Counterexample:** Group G holds publication/review rights. A person who can
manage G, but cannot grant those powers, adds themselves or a collaborator.
Effective powers expand without editing the protected grant. The current text
does not say whether G's manager was deliberately delegated that authority.

**Minimum proposal:** govern effective expansion, not only grant-row edits.
Use an approved member set or explicitly delegate bounded membership authority
to a named provider. Do not silently trust externally added members as new
privileged principals. Resolve distinct accountable humans and current/offline
membership evidence when evaluating approvals.

**Closure:** test unauthorized self-addition, explicitly delegated addition,
membership revocation, and multiple identities belonging to one reviewer. The
selected group mode and delegation ceiling must be explicit data.

## G02 — Unadopted preparation lacks an explicit consumer mode

**P1 · Reader-contract underspecification.**

[Consumption:47](2026-09-13T2138--35c75ca--knowledge-memory-consumption.md:47)
requires approved environment/knowledge editions. [Cold start:177](2026-09-14T1108--35c75ca--work-context-sources-and-cold-start.md:177)
allows permitted research/drafting with a candidate or explicitly unadopted scope.

**Counterexample:** a new Team with no adopted environment selects permitted
public sources for research. The UI allows it, but the reader appears to need
an approved edition. An implementation could refuse useful work or fabricate
an adoption/default identifier.

**Minimum proposal:** identify the preparation basis: adopted environment,
exact permitted candidate/derivative, or scoped ad hoc preparation. Preserve
source references, rights and required meaning in every mode. Only a matching
adoption receipt supports the Team-adopted claim. Discovery-ready and
Team-standard-ready are different outcomes.

**Closure:** nonadopted research can proceed without an adopted badge; it cannot
mutate adoption. Denied required sources remain denied. Transition to adopted
use requires matching preparation and actual adoption evidence.

## G03 — Restricted correction versus offline local closure

**P1 · State-evidence underspecification.**

[Consumption:79](2026-09-13T2138--35c75ca--knowledge-memory-consumption.md:79)
permits restricted event text to remain private while returning an authorized
state result. [Offline:166](2026-09-14T0003--35c75ca--disconnected-storage-and-sync.md:166)
and [Offline:202](2026-09-14T0003--35c75ca--disconnected-storage-and-sync.md:202)
require locally reachable state closure and necessary event verification.

**Counterexample:** visible decision D is corrected by C, which contains a
confidential investigation. The authority permits disclosure and offline use
of D's corrected status, but not C's body. The text does not define whether a
portable authoritative state result can satisfy closure. Implementers could
either demand private text or refuse an otherwise permitted disclosed result.

**Minimum proposal:** define two supported evidence paths: verified local event
closure, or a provider-authorized qualified state artifact. The latter binds
authority, permitted subject/query, exact frontier, interpretation version,
control evidence and offline conditions; it does not claim hidden bodies were
delivered. An arbitrary cached/LLM summary is not a substitute. Unsupported or
insufficient proof returns unresolved state, not the old decision.

**Closure:** accept the permitted qualified result without exposing C, and
reject forged, stale, wrong-scope or unsupported projections. Keep raw-history
availability separate from authorized-state availability and recheck known controls.

## G04 — Archived work with a replacement recipient

**P2 · Lifecycle/consumer underspecification.**

[Team CRUD:183](2026-09-14T0132--35c75ca--team-crud-and-creation-design.md:183)
forbids new Team task starts while permitting existing work to finish under its
continuation policy. [Storage:88](2026-09-13T1857--35c75ca--environment-storage-design.md:88)
may require a new compatible activation. [Lifecycle:89](2026-09-14T0135--35c75ca--team-lifecycle-scenarios.md:89)
also refers to preventing new task preparation.

**Counterexample:** an archived Team permits an existing task to finish, but
the worker loses a device. Does a replacement host context count as prohibited
new work or permitted continuation? Either interpretation fits the current words.

**Minimum proposal:** evaluate existing work identity/scope separately from the
host recipient. The continuation policy must govern replacement/rehydration
explicitly, with current rights and compatible context. A new recipient is
neither automatically new work nor automatically permitted continuation.

**Closure:** permitted replacement continues the identified work while unrelated
work remains blocked. Changed scope, expired rights or unknown identity cannot
inherit permission. Missing policy evidence remains an explicit unmet condition.

## Reproduced prototype/wireframe mismatches

These are design-artifact defects, not shipping enforcement vulnerabilities.
The [browser results](2026-09-14T1300--35c75ca--prototype-semantic-checks.json)
bind the exact existing hashes. Visible controls were used without internal
state injection. Earlier green QA results cover their paths, not every invariant.

### P01 — Review-only scenario allows a source proposal

**P2 · Internal scenario mismatch.** [Review view:41](2026-09-14T0222--35c75ca--zero-base-comparison-prototype.html:41)
labels review-only rights, but [the directory:42](2026-09-14T0222--35c75ca--zero-base-comparison-prototype.html:42)
offers contribution and [submission:61](2026-09-14T0222--35c75ca--zero-base-comparison-prototype.html:61)
saves without a scenario/grant check.

Reproduce: select the review-only case → material management → knowledge → new
version proposal → save. The case remains review-only while the proposal saves.
Correct by using one explicit capability set across routes, or visibly declaring
a separate contribution grant. Test handlers as well as control visibility.

### P02 — Missing-body recovery changes the apparent readiness

**P2 · Connected wireframe mismatch.** [W01:38](2026-09-14T0914--35c75ca--studio-wireframe-atlas.html:38)
can hold work for missing required body. [W08:45](2026-09-14T0914--35c75ca--studio-wireframe-atlas.html:45)
unconditionally says local work is possible, lists the body as to receive, and
lists the local P40 copy as holding required bodies.

Reproduce: W01 → required evidence missing → recovery explanation → W08.
No receive/verify action occurred. The atlas is not a state machine, as its QA
admits, but the apparently connected example changes its assumed scope silently.
Carry the same preparation/gap into W08, or explicitly separate unrelated
permitted investigation. Only actual fixture receipt/verification should satisfy
the missing-body condition in a connected example.

### P03 — Closed-Team evidence recovery is treated as revival

**P2 · Lifecycle fixture mismatch.** [Team design:190](2026-09-14T0132--35c75ca--team-crud-and-creation-design.md:190)
allows narrowly authorized recovery of retained evidence after closure. The
[local recovery view:65](2026-09-14T0132--35c75ca--team-crud-prototype.html:65)
and [handler:96](2026-09-14T0132--35c75ca--team-crud-prototype.html:96) block all
closed Teams with no separate evidence-only recovery action.

Reproduce: close the archived experimental Team through its authorized fixture
flow → switch to custodian Haemin → forget locally → reopen the forgotten Team.
Membership remains, but all reacquisition is blocked as reactivation. Separate
forbidden restoration from permitted read-only evidence recovery; preserve the
closure marker and require actual source/retention authorization. Membership
alone is not a sufficient recovery grant.

## Apparent conflicts not counted as current defects

| Apparent conflict | Applicable resolution or admitted limitation |
| --- | --- |
| Online-only approval versus offline operation | 00:03 explicitly amends 23:36: authority evidence is not Internet reachability; cross-owner unseen revocation remains bounded. |
| P2P versus one unavailable logical finalizer | Retention and finalization are separate; delayed new shared writes are an explicit tradeoff. |
| Recommended GitHub versus complete P2P | Setup recommendation is not connection/upload; P2P-only and forbidden-export alternatives remain. |
| Immutable history versus deletion | Historical bodies may become unavailable; control/tombstone retention and actual purge limits remain explicit. |
| Team identity versus several environments | 20:27 permits multiple environments and shared editions without inheriting source rights. |
| Missing history versus useful first work | 11:08 distinguishes not-checked/absent/denied and forbids invented historical rationale; G02 concerns its reader representation. |
| W01/W09 always show prior work | 11:08 explicitly supersedes the fixed predecessor assumption; old pictures are not the cold-start contract. |
| One intent button versus separate operations | Authorized phases can be orchestrated while preserving exact effects and receipts. |
| Two-person founding versus later loss | Founding is bounded and cannot be reused; later recovery may remain pending. The operational recovery policy is not proven by the fixture. |
| TUI/GUI differences | Representation differs; authority/outcomes must agree. Usability/IME/host behavior remains an empirical obligation. |

## Disposition

The [clarification proposal](2026-09-14T1300--35c75ca--consistency-clarification-proposal.md)
supplies concrete minimal rules for G01–G04. They are proposals, not silently
accepted new Team policies. The existing user-selected scope is preserved.

P01–P03 should be corrected in successor artifacts and the failing routes
rechecked before those fixtures are used to judge human understanding. A note
saying the backend will enforce the rule is not a substitute for consistent
fixture behavior. Old snapshots are intentionally preserved by this audit.

No existing design/prototype or runtime source was rewritten, and no actual
Team/source/membership change was performed. Findings are not closed by this
report or by lexical/link checks. The audit supports targeted repair, not an
unqualified statement that the entire design is proved correct.
