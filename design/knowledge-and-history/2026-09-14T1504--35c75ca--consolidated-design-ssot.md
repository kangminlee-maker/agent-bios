---
created_at: 2026-09-14T15:04:08+09:00
head: 35c75ca
kind: design
status: consolidated-target-design-not-runtime-certification
authority_scope: Team work-environment expansion design
entrypoint: CURRENT.md
sources: 2026-09-14T1504--35c75ca--ssot-sources.json
---

# agent-bios Team work environments — consolidated design SSOT

This is the current **target-design** reference for the Team environment
expansion. It consolidates the research, decisions, complete operational scope,
UI direction and consistency repairs recorded through this revision. A reader
does not need to reconcile the earlier design sequence to determine the rules
below. [CURRENT.md](CURRENT.md) is its navigation pointer, not a second design.

For this initiative's target design, this document supersedes the normative
role of the earlier design/recommendation documents listed in the
[source inventory](2026-09-14T1504--35c75ca--ssot-sources.json). Those artifacts
remain evidence of rationale, alternatives, reviews and historical prototypes.
They cannot override this consolidated text through an old diagram or example.
This does not supersede implemented APIs, repository working rules, or the
separate Instructions compatibility/migration contract.

**Status vocabulary:** user requirements are required outcomes; design rules
are the current means of satisfying them; defaults/hypotheses remain changeable
through design review and the affected Team's governance. Written design,
simulated behavior, runtime enforcement and observed human usability are separate
evidence levels. Nothing here certifies the whole future product as implemented.

## Contents

[S01 Purpose](#s01) · [S02 Concepts](#s02) · [S03 Knowledge](#s03) ·
[S04 Decisions](#s04) · [S05 Environment/preparation](#s05) ·
[S06 Consumption](#s06) · [S07 Governance](#s07) · [S08 Storage/sync](#s08) ·
[S09 Team lifecycle](#s09) · [S10 First work/data origins](#s10) ·
[S11 Studio](#s11) · [S12 Acceptance](#s12) · [S13 Exclusions](#s13) ·
[S14 Evidence and maintenance](#s14).

<a id="s01"></a>
## S01. Purpose and requirements

The canonical product purpose remains in [AGENTS.md](../../AGENTS.md).
Its wording is reproduced here as the design criterion:

> agent-bios exists to let workers compose, share, and inherit team work environments
> from Instructions, Domain knowledge, and Decision memory, so they can perform
> their roles within the standards and context of their team, industry, and organization.
>
> A team is the basic unit for selecting, adopting, and sharing a work environment.
>
> Workers should be able to select an environment appropriate to their role and
> team, collaborate from shared standards and decision context, and continue
> the work when a worker, model, session, or device changes. Shared context does
> not require identical outputs or erase personal, team, and organizational boundaries.

Selecting appropriate material should let a worker perform a role in a Team's
context: the same worker can act as a developer or accounting worker and can
work with different Teams' standards. Team, organization, industry, role and
project scope must remain distinguishable. Team is the basic sharing/adoption
unit; it does not force a company hierarchy or one environment per Team.

The stable requirement IDs below preserve the complete user scope. Detailed
historical origin traces remain in the source inventory's requirements board.

| ID | Required outcome | Owning sections |
| --- | --- | --- |
| U01 | Select, compose, share and inherit appropriate work environments; preserve purpose in the repository charter and decision ledger | S01–S02, S05–S06, S14 |
| U02 | Team is the basic selection/adoption/sharing unit | S02, S09 |
| U03 | Distinct Instructions, Domain knowledge and Decision memory; product-wide Instructions terminology | S02, S14 |
| U04 | Simple, robust, extensible structure; explicit exclusions; zero-base usability review and understandable visual design | S11–S14 |
| U05 | Durable principles plus changing applicable knowledge and required updates | S03 |
| U06 | Ontology or competency questions, onto 8+1 lenses/domain package, model/form/validation authoring | S03, S11 |
| U07 | Decision context, alternatives, reasons, premises and consequences beyond Git history | S04 |
| U08 | Parallel/intersecting workstreams and continuity across workers/sessions | S04–S06 |
| U09 | Efficient useful consumption with essential meaning preserved | S06 |
| U10 | Complete Studio, including advanced source editing, search, derivatives, bulk operations, administration and recovery | S11 |
| U11 | Current/new/child work and context recovery with truthful actual-delivery state | S05–S06, S10–S11 |
| U12 | Scoped rights, allocation, review, publication, adoption and execution | S07 |
| U13 | Complete Team creation/read/update/delete, enrollment, members/devices, connections and ownership continuity | S09 |
| U14 | Corrections, derivatives, retention/deletion, access changes and recovery | S03–S04, S07–S09, S11 |
| U15 | Complete local/P2P foundation without GitHub | S08–S09 |
| U16 | Eligible GitHub connection recommended and initially selected, optional and independently removable | S08–S09 |
| U17 | Closed networks and one or two weekly exchange opportunities with useful permitted local work | S06, S08–S09 |
| U18 | Authorized peer copies improve recovery; expose actual coverage and outstanding exchange | S08–S09 |

Research notes, handoffs and visualizations are design deliverables, not an
implicit requirement for research, diagram or handoff services in the product.

<a id="s02"></a>
## S02. Small conceptual model

**Separate what changes independently; connect what must be understood together.**

| Concept | Owns | Must remain distinct from |
| --- | --- | --- |
| Instructions | Behavioral rules, procedures, triggers and their appropriate host delivery | Retrieved facts or recorded past choices |
| Domain knowledge | Commitments, domain meaning, models, factual claims and criteria with applicability/evidence | Instructions, approval or universal truth |
| Decision memory | Actual scoped decisions, stated reasons and meaningful lifecycle/outcome events across workstreams | Commit/transcript logs or inferred intent |
| Team | Stable sharing/adoption identity, membership and governed environment choices | Display name, repository, all source ownership or all worker context |
| Environment edition | An immutable, owned composition of exact Instructions/knowledge references and authorized memory selection policy | One worker's installation, current memory contents or automatic permissions |
| Operation preparation and receipts | Scoped selection, resolved evidence, usable bodies, gaps and actual local/host outcomes | Source authority, global completeness or model comprehension |

References connect role-specific stores; they do not require a universal row,
database, editor or state reducer. A document may contain several roles: keep
its source bytes and distinguish the selected portions' meaning and delivery.
Adding knowledge/memory as instruction compiler kinds would give them the wrong
authority. Promote a lesson into Instructions or knowledge only through the
destination owner's explicit revision/adoption process.

Stable identity, immutable revision, owner namespace, domain scope, origin,
local acquisition and acceptance are distinct. Imports preserve exact source
identity and add local availability evidence. Exact references resolve to the
matching revision or an explicit unavailable result, never a moving substitute.
Hashes prove byte identity, not ownership, trust, permission or freshness.

Search, graphs, timelines, summaries, dashboards and prepared context are
derived views with named source owners. A generated interpretation is not an
accepted domain claim or Team decision. Existing instruction catalog identity,
authoring revisions, compiled snapshots and native session pins retain their
specific meanings; none becomes a universal version identifier.

<a id="s03"></a>
## S03. Domain knowledge and authoring

Use coherent documents, sections, tables or bounded assertions. Split only when
independent citation, applicability or revision requires it. Preserve a table's
headers, units, effective conditions and exceptions with its values. Add machine
fields where an actual query/editor/validator consumes them.

| Meaning | Example type | Required interpretation |
| --- | --- | --- |
| Commitment | Team direction or adopted principle | An intention/choice, not an observed fact |
| Definition/model | Domain concepts, relationships and structure | Scoped meanings and qualifications |
| Claim | A rule, parameter or factual assertion | Evidence, applicability and material uncertainty |
| Criterion | A competency or validation question | A check to perform, not a proven answer |

Durable versus changing is a **maintenance property**, not two ontologies or
stores. The user's tax example separates the general calculation structure
from changing rates/relief conditions; this is a modeling example, not tax advice.
Both use the same revision/evidence route. Complete schedule editions suffice
initially; no generic temporal-interval engine is required.

Keep domain applicability, local availability, scoped acceptance and source/review
evidence separate. Record relevant period, jurisdiction/entity conditions,
exceptions, source and required update obligations. Missing answer-changing
conditions yield a scoped unknown. A recent review does not prove current truth;
no universal rule makes the newest source authoritative.

Historical explanation uses the decision's exact cited edition. A present
assessment of an earlier period uses the selected applicable edition and that
period's conditions, disclosing current evidence limitations. Future-effective
rules and late corrections create new revisions; neither rewrites old premises.
Material new evidence is a candidate update. Dependent use rechecks adequacy and
follows environment update/adoption policy; source refresh does not silently
change a Team pin. Conflicting evidence remains qualified until a scoped
interpretation settles its use.

Onto integration retains its eight domain documents and **8+1 lenses**. Each
document is a canonical versioned source or a projection with one authoring
owner. Support competency questions before requiring a complete graph. A useful
question names the decision it can change, necessary scope/evidence, expected
answer form and counterexample. Authoring/review selects pinned targets, domain
package, questions and relevant lenses; results remain findings tied to those
versions. Onto does not refresh external facts, grant acceptance or certify
truth, and nine-lens review is not run on every read. Model/form editors remain
in scope; their minimum operations are in S11.

| Lens | Existing domain-package home / purpose |
| --- | --- |
| Logic | `logic_rules.md` — logical obligations |
| Structure | `structure_spec.md` — allowed structure |
| Dependency | `dependency_rules.md` — dependency obligations |
| Semantics | `concepts.md` — concepts and meanings |
| Pragmatics | `competency_qs.md` — questions the model must help answer |
| Evolution | `extension_cases.md` — extension/change cases |
| Coverage | `domain_scope.md` — required scope and boundaries |
| Conciseness | `conciseness_rules.md` — unnecessary complexity |
| Axiology (+1) | Purpose, principles and context across the package; no mandatory ninth document |

This is the retained integration mapping, not a new universal domain schema.

<a id="s04"></a>
## S04. Decision memory and concurrent work

| Record | Minimum useful meaning |
| --- | --- |
| Workstream | Stable ID, editable name, purpose/scope; can outlive a session, branch or repository |
| Decision | Question/context, scoped choice, recorded alternatives/reason, exact stated premises, optional expected consequences/revisit condition |
| Event | Attributable adoption, correction, withdrawal, replacement, observation or reassessment; exact target, evidence, recorded time and occurrence time when known |

Unresolved discussion remains a note. Missing historical reasons/alternatives
remain missing; later explanations are labeled later interpretations. A commit
can support what changed, not establish an unrecorded why. Initial decision and
its acceptance can be recorded in one atomic local write where authorized.
Acceptance, implementation and verification remain separate facts rather than
a compulsory linear status pipeline.

Store immutable decisions/events. Correct an erroneous assertion with another
targeted record. Correcting a false acceptance assertion differs from withdrawing
a choice actually accepted earlier. Expected outcomes remain in the decision;
observed outcomes belong in events. Historical explanations preserve what was
known/stated then while showing permitted later qualifications separately.

Only three causal relations need initial structured support: `basis` for exact
stated reliance, `target` for an event's subject, and `replaces` for an explicitly
displaced choice in bounded scope. Delivered context is not automatically a
premise. Membership in several workstreams is an association, not causality;
one record may be indexed in several lanes without duplication. Device time,
receipt order and explicit causal links retain different meanings.

Independent authorized records can be unioned. Identical IDs with different
bytes are corruption/conflict. Combining records does not resolve incompatible
choices. Whole-decision replacement with equal declared scope is the initial
automated case; partial changes require explicitly bounded decisions/resolution,
not inferred scope algebra. Missing targets, cycles, competing successors and
contradictory lifecycle assertions produce qualified unresolved state. Arrival
time or a clean textual merge cannot select the semantic winner.

Current state is established **before** ranking/clipping: resolve required
subjects and sources/frontiers; follow state-relevant events, including events
in other workstreams; reduce qualified state; then rank and bound the body.
Filtering cannot conceal a withdrawal and revive an earlier decision.

For restricted corrections, sufficient evidence is either verified required
event closure or a provider-authorized, verifiable **qualified state artifact**.
The latter binds trusted issuer/authority, permitted subject/query/scope/audience,
exact frontier and coverage, supported interpretation contract, actual state
body and material unknowns, control/retention evidence and offline conditions.
It may disclose a permitted effect without confidential reasons or protected
record identities/counts. It grants no new rights and does not claim hidden
bodies were delivered, independently reconstructed or globally latest. Invalid,
unsupported, stale or wrong-scope proof leaves state unresolved; an arbitrary
summary or self-declared signing key is insufficient. This serializes the
existing authorized reader result rather than creating another knowledge store.

<a id="s05"></a>
## S05. Environment selection, preparation and actual use

An environment edition identifies its stable ID/owner/purpose/applicability;
exact Instructions and knowledge revisions; authorized memory sources/selectors
and optional historical baseline; required/optional components and host needs;
exact parents and explicit additions/replacements. Team may adopt several
environments. Allowed professional material can be shared across Teams without
merging their private sources or decision scope.

Composition initially uses pinned inclusion and a flattened exact manifest.
No automatic hierarchy gives industry, organization, Team or project precedence.
Duplicate required material with different versions needs explicit resolution;
semantic disagreements need review. Parent updates are candidates, not floating
inheritance. Personal derivatives have distinct identity, owner, base and changes;
they cannot claim the unchanged Team edition's adoption or relax source rights.

Instructions/knowledge are pinned by edition. Memory evolves without a new
environment edition for every event: the edition pins source/selection policy,
each operation fixes its observed frontier and record selection. A frontier is
an exact checkpoint/set identity, not a wall-clock timestamp. An event citing a
newer premise does not change static pins; incompatible dependent work needs an
environment update or an explicit unmet condition.

Keep three independent preparation questions:

| Dimension | Evidence and result |
| --- | --- |
| Selection basis | Exact adopted environment, permitted candidate/derivative, or scoped ad hoc sources; adoption evidence only when applicable |
| Work support | Required coherent bodies, qualified memory state, editions/frontiers, applicability, known controls and gaps |
| Action eligibility | Actor, requested operation/scope, grants, source/Team constraints, approvals and permitted offline evidence |

Unadopted research/drafting may proceed when permitted. It does not fabricate
an environment ID, Team-standard badge, adoption or substantive execution
permission. Required source denial cannot be bypassed by relabeling an action
as research. Changes to basis, relevant premises or operation scope establish
a new preparation boundary. Do not compress every combination into one global
Team-ready flag.

The operation manifest retains exact composition/frontiers, selected subjects,
source/rendered digests, actual bodies or their permitted retention location,
adapter identity, recipient/work scope, observed authority/offline conditions,
material gaps and omissions. Store detailed provenance once; show readable source
aliases and meaningful qualifications to the worker. New recipients need their
own supported body/reader route. A replica holding data is not a host recipient.

Distinguish prepared, requested delivery, observed delivery/activation and
observed use. A manifest proves assembly; a hash cannot reconstruct lost bytes;
a parent's receipt proves no child delivery. Exact historical rendering requires
retained permitted rendered bytes. Native host globals/project context remain
additional context, not captured by the environment. Known incompatible context
or Team isolation requirements block affected activation until a compatible
fresh or evidenced isolated context exists. A new conversation alone does not
prove isolation. Preserve the previous pin's audit identity, but allow continued
use only while its actual permissions and conditions still permit it.

<a id="s06"></a>
## S06. Efficient consumption and continuity

| Moment | Instructions | Domain knowledge | Decision memory |
| --- | --- | --- | --- |
| Select/orient | Compact applicable rules and procedure triggers | Scope/purpose and topic/question map; essential orientation where declared | Authorized work scope and discoverable workstream directory |
| Start/resume relevant work | Applicable procedure | Small coherent support body with definitions, conditions, exceptions and sources | Qualified current choices, open questions/conflicts and outcome qualifications |
| Explain/reconsider | Owning procedure details | Exact evidence/table/model or containing section | Recorded why/alternatives, correction chain and exact historical premises |
| Delegate/rehydrate | Compatible recipient projection | Necessary bounded bodies and usable expansion route | Necessary state body under an identified frontier and recipient rights |

Instructions own when to consult readers. Knowledge/history are reference
context, not upgraded behavioral instructions. Each role has its own reader
semantics; the small shared envelope carries work/scope, required subjects,
role/view, question/exact selector, budget and optional pinned continuation.
Results carry usable body, scope/edition/frontier, material gaps/qualifications,
exact expansion references and bounded omissions/end indication.

Resolve access before exposing candidates or metadata. Derive the named required
set from environment obligations, explicit task/reference requests and authorized
work-scope queries; combine with optional search candidates before ranking.
Include knowledge companions and memory closure before fitting output. Declared
dependency inclusion can be enforced; all unstated semantic needs cannot.

Bound both retrieval processing and returned context. Prioritize scope/material
limitations, required support/state, useful optional content, then expandable
detail. If required work cannot fit or be established, return incomplete with
continuation/narrowing/remedy; affected judgment waits while unrelated permitted
work can continue. Do not strip an exception, withdrawal or uncertainty to fit.
No universal token count, confidence score or ranking policy is selected without
evidence. Empty, denied, unavailable, unsupported, unresolved and truncated remain
distinguishable. End-of-pagination is not proof of all semantic relevance.

Cursors bind role/view/selector, version/frontier and access context; another
page never silently follows a newer head. Refresh is another read; revocation
can invalidate a cursor. Cache immutable bytes subject to retention, and derived
text by exact sources, question/conditions and renderer/reducer version. Preserve
namespace/access boundaries. Recheck current applicability and material known
qualifications even when byte hashes match.

Resume, scope/Team changes, known material updates, challenged premises,
compaction/uncertain retention and child creation trigger appropriate bounded
re-reading/re-delivery. A matching cached body can be omitted only under an
explicit current-caller declaration that the body and qualifications are retained;
receipts/hashes alone do not prove this. First use, uncertain retention and a
new child require actual bodies. Unsupported child readers need permitted direct
body delivery or an explicit gap. Deltas remain optional and require a known
retained baseline including changed corrections/qualifications. Reconcile different
premises/frontiers before combining delegated results.

A worker can discover authorized relevant decisions without knowing a previous
worker's session IDs. Task matching can suggest scope, not grant access. Retrieval
quality, relevance and model comprehension remain empirical/review obligations.

<a id="s07"></a>
## S07. Authority, approvals and operations

Source ownership, Team adoption, membership and actual task execution have
different owners/effects. Selecting an environment/role, copying bytes, being a
Team maintainer or holding a review grant confers no unrelated powers. An
environment may require a host capability, but it does not install credentials
or grant that capability.

Grants bind authenticated principal/provider, resource scope, allowed actions,
issuer, revision, optional expiry and delegation ceiling. People, groups and
identified service/agent principals are supported. UI role templates are editable
grant bundles, not an implicit rank hierarchy. Preserve `read`, `use`, `contribute`,
`review`, source/environment `publish`, Team `adopt`, scoped `decide`, and bounded
`grant`, `policy`, `transfer`, `suspend`, `retain/delete`, `export` actions.
Read permission alone does not authorize export or feeding protected material
to an arbitrary host. Agent execution retains an accountable sponsor and bounded
delegation; no invented independent human approvals.

An issuer cannot exceed its explicit delegation ceiling. Child/service grants
cannot exceed the effective parent's scope, actions, recipient restrictions or
lifetime; upstream withdrawal constrains dependent future use under the applicable
offline policy. Editing a role template does not mutate existing grants, and
assignment-management rights alone do not grant source-body access.

Effective privilege expansion through group membership is governed even when
the grant row does not change. The recommended default requires an approved
member set plus applicable current/permitted-offline membership evidence. Dynamic
membership eligibility requires explicit bounded delegation to a named provider;
a group manager is not implicitly a grant authority. Known removals override old
approved lists. Expiry/revocation/source constraints apply to both modes. Approval
counts resolve distinct accountable eligible people, not keys, accounts, groups
or repeated agent runs.

For a policy requiring independent human review, exclude the requester,
recorded accountable authors and agents acting under their sponsorship from
the independent count. Machine validation is evidence or an explicitly governed
automation route, not a human vote.

The governing policy specifies operation scope, eligibility/independence, checks,
approval threshold, expiry and execution authority. Proposed starting policy is
one independent human review for shared high-impact changes where appropriate;
it is not a universal user requirement or permission to weaken an established
Team policy. Read/preview/permitted use need no extra content vote per read.
Contribution saves proposals; review does not publish, adoption does not edit a
source, and recording a decision does not make it authoritative. Grant expansion
and policy weakening are judged under the existing policy and delegation ceiling.
Pre-authorized containment may restrict access without creating a privilege
expansion route; preserve required recovery/ownership capacity.

A sealed request binds operation, owner, requester/actors/accountable author,
exact payload and target, expected head/base, policy and relevant evidence,
requested effect and rationale. Approval binds that exact request and eligible
reviewer. Changing defining inputs requires a new request/approval basis. At
execution, recheck authority, eligibility, source constraints, policy, expiry,
validation and expected head. A prior allowed preview or approval is not an
evergreen grant. Old receipts remain historical evidence after revocation.

The authority serializes a pending approval's retraction against commit. An
offline signature proves its attributable statement, not current execution
eligibility; a self-reported signing time cannot establish that an approval
preceded a relevant withdrawal. Apply the policy's supported evidence at execution.

Shared mutation states retain `draft → in review → approved → executing → committed`
and changes requested/rejected/withdrawn/expired/stale/blocked/conflict/unknown;
multi-provider groups can partially complete. Silence and elapsed time are not
approval. A single user intent may orchestrate already-authorized phases; it
does not require repeated confirmation clicks or merge their authority/effects.

Each shared head has an authority-owned conditional commit with an exact
request-bound operation ID and durable atomic result receipt. Retry/query an
unknown outcome using the same ID; reusing it for another payload fails. Current
head equality or uploaded blob presence is not proof of a request's success.
Conflict preserves candidates. Cancellation can be too late/unknown; reversal
is a new governed effect. No cross-provider all-or-nothing promise: publish
components, then the environment, then separately adopt, with per-owner receipts.

<a id="s08"></a>
## S08. Local/P2P storage, optional GitHub and disconnected work

The **complete operating foundation is local/P2P**. GitHub is a recommended,
initially selected setup option where policy permits, and a useful carrier/store
of permitted shared state. Core founding, authoring, review/changes, use,
exchange and recovery have non-GitHub routes. Selection is not connection,
account authorization, repository creation or upload. Removing GitHub does not
remove Team identity or the non-GitHub routes. A hosted-only service cannot be
the product's only operating path.

| Boundary | Retained material / behavior |
| --- | --- |
| Portable owned source | Exact source objects and manifests, permitted decision/events, policy/control/checkpoints and verified operation receipts |
| Worker-local state | Authorized verified cache, observed references, private drafts/outbox, availability evidence and host-specific compilation/recovery journals |
| Authorized peers | Retained permitted object sets and control continuity for declared Team/environment/work scope; independently verifiable copies |
| Optional carriers | GitHub, permitted direct/internal links, or explicitly transferred offline packages; same identity, verification and authorization semantics |

Do not synchronize whole personal installation directories, credentials, native
session IDs, local locks or incomplete local journals as portable authority.
Rebuild local host realizations from permitted canonical sources. Authorized audit
artifacts can retain exact rendered bytes without becoming executable sessions.

Replica custody, approval and shared-head ordering are distinct. The current
minimal ordering proposal is one logical finalizer per authority scope/head with
conditional sequencing, which can run on an authorized member device. It is not
a blockchain, universal consensus network or per-copy voting system. Signed
objects and copies do not confer finalization rights. Failure of a finalizer
can delay new shared writes while permitted reads, drafts and existing work
continue. Verified governed succession must preserve authority continuity and
prevent the old writer from independently finalizing; absent required evidence,
shared writes wait rather than inventing a failover. GitHub/copy count does not
remove this availability tradeoff.

Retain accepted authority epoch/checkpoint and predecessor continuity. Conflicting
authoritative successors are fork evidence and stop automatic adoption in the
affected scope; largest version, latest arrival, longest chain or majority of
cached files cannot resolve them. Rollback to old content is a new authorized
transition. Backups of authority state are passive, not extra active writers.
Planned succession needs successor consent/readiness, exact handoff and old-writer
fencing; copying a key is not authorized transfer. Protect signing/authority state
from ordinary worker-agent access even when hosted on a member's computer.

Track actual custody by exact required body/control inventory, accountable
peer/device, observation/acknowledgment and scope. A connected peer, nominal
copy count or checkpoint hash is not a complete retained copy. More authorized
independent failure domains improve recovery; they do not prove it. Three copies
is a configurable proposed target, not quorum or a universal minimum. One copy
cannot provide device-loss redundancy; missing targets should not automatically
block unrelated permitted work.

Custody commitments identify storage generation and retention limits as well as
the exact object set. Keep evictable caches separate: insufficient space means
declining retention, not silently evicting promised bodies. A reset/replacement
generation invalidates old custody assumptions. Protect unique outboxes with
independent backup; correlated peer loss remains possible. Reconstructing from
another peer is stronger recovery evidence than counting old acknowledgments.

Every relevant source/environment declares offline-use/authority conditions.
Composition can tighten but never relax source access, export, retention or
offline restrictions. No universal validity duration is imposed. Closed networks
and one/two weekly exchanges are supported use cases, not hard-coded intervals.
An authorized internal/offline finalizer and approvals can operate when their
evidence/policy permit: offline does not universally mean proposals only.
Unknown remote revocation cannot be detected instantaneously; report the last
verified frontier/control state and applicable validity. Known restrictive controls
must affect new dependent use even if unrelated body transfer fails.

A sole writer knows its own scope's state, not another owner's unseen changes.
Track the relevant owners' qualified checkpoint observations instead of inventing
a global clock. Clock rollback, old-disk restoration or lost trust/control state
cannot renew an offline allowance; unsupported validity requires refresh or
verified re-enrollment. No permitted information path means no convergence in
that direction. Offline readiness also requires locally/internal-network usable
host/model, readers, tools, schemas and validators where the task needs them;
downloaded source files alone do not make an external-only dependency available.

Transfer envelopes bind authority/namespace, permitted recipient/scope, exact
inventory/hash/size, prerequisites, supported semantics, checkpoints, requests
and receipts. Trust comes from authenticated enrollment or independently verified
authority continuity, not the package's own public key. Signing is not encryption;
protect confidentiality as required. Unsupported required policy/event semantics
remain unsupported, never silently discarded.

Support complete/bootstrap, incremental and return-contribution packages. Deltas
use acknowledged exact inventory/checkpoint, not "since Tuesday". A missing or
damaged baseline can use a permitted complete transfer; never require an endless
chain of unavailable deltas. Required working bodies and sufficient qualified
memory state must be locally reachable. Restricted citation evidence may stay
unavailable, but an answer needing it remains unverified.

Exchange sequence: persist the outbox; stage permitted bounded input without
executing imported scripts; verify trust/control continuity and restrictions;
verify object prerequisites and sufficient state evidence; atomically promote
verified local availability; resolve contributions under owning authority;
return exact acknowledgment/acceptance receipts; deliberately prepare/use.
Exported, received, verified, accepted and committed are different outcomes.
Preserve unique drafts/outboxes while outcomes are unknown. Resume interruption
with the same request and verified objects. Duplicate imports are idempotent;
conflicting bytes, advanced bases and incompatible decisions remain explicit.

Withdrawal, pointer removal, logical closure and physical purge differ. Durable
controls/tombstones prevent returning offline data from silently resurrecting
deleted content. Governed cleanup tracks permitted source/derived caches,
indexes, excerpts and exports; confirmed, denied, unreachable and unknown removal
remain separate. Previously delivered or uncontrolled copies cannot be promised
erased. History can truthfully become unavailable. Deletion does not authorize
rewriting old records or hiding unknown outcomes.

<a id="s09"></a>
## S09. Team creation, membership, update and retirement

Team identity is stable across renames and connection changes. A Team can have
several environments, and a worker can join several Teams. Company/industry/
project applicability adds context without mandatory hierarchy or automatic
inheritance of rights. Creation never silently produces adopted knowledge or
fictional past decisions.

| Operation family | Minimum inputs and outcome |
| --- | --- |
| Create | Name/purpose, relevant applicability, founding principal/responsibilities, governance and recovery proposal, initial sharing/connectivity/retention conditions; stable Team ID and explicit founding state |
| Join | Verified Team/issuer invitation and terms, recipient consent and permitted membership registration; consent, invitation receipt and active membership remain distinct |
| Read | Authorized Team/environment selection, membership/rights and relevant adoption/custody/operation state; no restricted detail leaked to unauthenticated invitees |
| Update | Exact affected identity/settings/grants/policy/connection changes, before/after effects and required governing approvals; stable Team ID and bound outcome receipt |
| Copy/derive | New Team identity/governance with only permitted selected sources/configuration; no copied members, credentials, approval authority or invented history |
| Devices/ownership | Enroll/retire keys/devices and transfer stewardship/finalization under continuity policy; protect unique drafts, required owners/reviewers and recovery capacity |

Creation can be one reviewable flow rather than a fixed page count. Keep required
choices visible or reachable: eligible GitHub recommendation, P2P-only/internal/
package alternatives, permitted network/export destinations, offline conditions,
custody target and designated responsibilities. A selected option performs no
remote mutation. Team founding, identity verification, source access, first
environment and first work are separate evidenced outcomes with continuous
identity. Pending setup should identify what can proceed and what remains unmet.

Founding has a bounded bootstrap to avoid needing an established Team's approval
before that Team exists. The shared founding path establishes the proposed policy
with independently verified participant acceptance/review; nomination or a UI
button cannot manufacture another person. The bootstrap only establishes this
new identity's initial authority. It cannot weaken source rights or become an
established Team's emergency bypass. Canceling an unused founding setup is a
bounded separate path that preserves actual external effects and pending outcomes.
Personal/local work does not claim independent shared-Team approval.

The authenticated founder seals the Team ID, exact initial policy/grants,
nominees, finalizer binding and recovery responsibilities. Independently identified
nominated humans verify/accept that exact proposal; the designated authority
checks identity, required acceptances and capabilities and commits the initial
governance checkpoint. Before that commit, only permitted setup, drafts and
invitation artifacts are available. Revising the proposal invalidates earlier
pending acceptances, and competing completions serialize for the same Team ID.
After initial governance commits, that Team ID never reenters founding mode.
An explicitly selected solo profile is self-founded/self-reviewed and carries
no independent approval claim; absence of a reviewer cannot select it silently.

Founder cancellation is limited to an unused incomplete setup on which no
committed protected governance, member/grant, environment or decision effect
depends. Invalidate its exact pending proposal/invitations and retain a terminal
identity marker so delayed acceptance cannot reactivate it. This does not need
a never-enrolled reviewer's approval and does not delete an external repository;
unique drafts and uncertain external effects keep their explicit disposition.

Joining/leaving, invitations, grant changes and ownership succession preserve
explicit delegation ceilings and applicable review. Do not remove the last
required owner, reviewer/recovery capacity or sole finalizer without a permitted
disposition. A small Team losing a participant may face pending protected actions;
never invent an approver. Show the policy's actual succession/recovery route and
what useful authorized work remains available.

GitHub setup binds account, repository identity, permitted namespace and effects
before provisioning. Existing work-project and Team-sync repositories are separate
concepts even if deliberately configured to the same physical repository. Handle
partial provisioning durably: reconcile an unknown result with the same operation,
retain the created repository association, and separately authorize cleanup.
Disconnecting one Team neither revokes another Team's shared credential nor deletes
its repository. Changes affecting materialization invalidate affected preparation.

| Lifecycle action | Meaning and constraints |
| --- | --- |
| Archive | Reversibly stop ordinary Team mutations, new adoptions and new Team work; retain permitted history and necessary governance/retention routes |
| Continue archived work | Only the existing logical work/scope named by applicable continuation policy; replacing/rehydrating a recipient requires its own allowed conditions and current source rights |
| Restore | Governed return to operation under the same ID; recheck grants, rights, custody and host requirements rather than reviving everything automatically |
| Leave | End this principal's membership/dependent delegations with continuity obligations satisfied; independently held grants need their own disposition |
| Forget on this device | Remove permitted local view/data; membership/other replicas remain; disposition unique drafts/outbox and preserve required anti-replay controls |
| Permanently close | Terminal identity-level closure for future Team work, with durable closure marker and surviving evidence stewardship; same name later requires a new Team ID |
| Evidence recovery/retention after closure | Only separately authorized retained-evidence reading, recovery, preservation/cleanup under source/retention conditions; never reactivate Team work |
| Purge | Separately governed removal of exact owned copies with actual per-owner outcomes; closure/local forgetting is not global physical deletion |

Identify logical continuation using existing host/workstream/operation evidence;
a `continuation_of` label alone grants no permission. New recipient creation is
neither automatically new work nor automatically permitted continuation. Changed
scope, broader decisions or new environment use need their own allowed operation.
No mandatory task-tracker service is required.

Permanent closure follows archive/no-new-work → inspect exact closure plan →
request/review → authoritative commit. The plan covers surviving ownership,
retention/purge, outboxes and unknown operations, required custody and repository
disposition. An unreachable peer is not evidence it has no unique work. Confirm
the exact Team identity/effects, but typed confirmation is not authorization.
GitHub retention is normally independent; archival/deletion is separately scoped.
Cleanup failure does not undo a committed Team closure.

Required ownership, authority and surviving evidence-stewardship disposition
must complete before terminal closure; merely listing an intended successor
is insufficient. Physical purge may remain separately pending under its own
receipts. If even minimal replay-control retention conflicts with governing
deletion policy, expose that incompatibility rather than promise both effects.

<a id="s10"></a>
## S10. W01/W09 data origins and first work

W01 is a **derived work preparation**, not a remote task database. W09 is the
planned/actual recipient and delivery evidence for that preparation. Neither
requires an existing remote repository, predecessor session or registered task.

| Input | Legitimate source | Limitation |
| --- | --- | --- |
| Work request/scope | Current user/host request or explicitly connected task source | Do not infer detailed intent or prior decisions from a repository name |
| Team/environment | Authorized selected provider/local replica and actual adoption evidence | Repository membership or a public package does not prove Team adoption |
| Working-project evidence | Explicitly selected local files or permitted connected project source; bounded inspection | Code/logs establish observed artifacts, not unrecorded rationale |
| Knowledge and decisions | Selected scoped readers, exact revisions/frontiers and qualified results | Search failure/denial is not an empty history |
| Previous preparation | Actual retained operation manifest/receipts when available | Receipt alone does not prove current body retention or model use |
| Recipient | Supported host adapter or explicit target selection followed by actual target evidence | Do not invent session IDs or treat storage peers as recipients |

Discover candidates from authorized host/project context, disclose the selected
scope and obtain missing user intent when it materially changes preparation.
Do not silently search all personal transcripts, remote repositories or Teams.
Observation, user-supplied context, imported decision records and generated
interpretation retain their different provenance and authority.

A work-project repository supplies bounded project evidence; the optional Team
sync repository carries permitted Team objects/checkpoints. Neither implies the
other or its rights. Selecting a folder/URL does not initialize agent-bios inside
the project, collect its complete history, upload it or enroll another Team.
A spreadsheet, policy document or brief can be the work object with no repository.
Reuse actual host-supplied scope where supported rather than requiring retyping.

Identify the actual inspected revision or selected bytes and observation time.
For local editing, preserve dirty/untracked selected files; HEAD alone does not
identify that working tree and a remote URL is only a locator until inspected.
Bounded per-file references suffice without snapshotting the whole project.
Recheck materially changed evidence before dependent action. Reading code,
configuration or test definitions is not observation of deployed behavior or
successful test execution; record those only with corresponding execution evidence.

**Brownfield:** inspect bounded existing project evidence and authorized Team
memory. If project decisions are absent, report that within the checked scope.
Offer to record a present decision/interpretation from now; do not manufacture
the project's earlier why or require exhaustive archaeology before useful work.

**Greenfield:** use applicable Team standards and the current request even with
no project/repository. Relevant Team decisions may exist; a new project does not
mean all Team memory is empty. If no adopted environment exists, choose a
permitted candidate or scoped sources and explicitly prepare unadopted research/
drafting. Later Team adoption is its own governed effect. Record actual new
choices as they occur.

| Observed state | Meaning |
| --- | --- |
| Not checked | Scope has not been inspected; no absence claim |
| Authorized lookup succeeded with none | Legitimate empty result within that scope |
| Required body not local | Missing material with permitted recovery route; not missing historical rationale |
| Denied/unreachable/unsupported source | Specific unmet dependent requirement, without restricted-detail leakage |
| Permitted complete local evidence while disconnected | Work under last verified basis and offline conditions; no global-latest claim |

W09 follows target planned → required material prepared → delivery requested →
observed result. Unsupported adapters expose permitted manual/export routes
without claiming native activation; user attestation and adapter observation
retain distinct evidence strength. Current/new/child/continuation targets all
retain actual rights, body requirements and isolation checks.

<a id="s11"></a>
## S11. Studio, navigation and complete operational UI

The shell is **agent-bios · Studio**, spanning all three content roles and Team
environments. It owns no competing private source store. Its operation meanings
are shared with TUI/CLI/host routes, while representation fits the user's job.

The work brief is the leading worker-consumption hypothesis; the shared-environment
notebook/catalog is a serious primary authoring/maintenance candidate. Neither
is proven universally optimal. A contextual hub offers five spoke groups; it
is navigation, not a central server or mandatory first step. Direct authorized
links remain valid. Do not require new task registration or a Studio visit to
use a host-provided work context.

| Arrival | Entry |
| --- | --- |
| No known Team/invitation | Create Team or open a received invitation |
| Invitation | Permitted invitation/enrollment detail; no pre-authorized private management view |
| Known Team with an environment | Contextual home or directly requested work/material |
| Known Team without environment | First environment W02; no hidden adopted fixture |
| Exact work/source/review link | Requested authorized target, with scoped unavailable outcome where necessary |
| Existing host work | W01 brief or W09 actual recipient/continuation |

| Spoke / family | User question and main path |
| --- | --- |
| Work · W01 | Which standards/context support this task? Open knowledge W03, why W04, missing-material W08 or recipient W09 |
| Work · W09 | Who receives which actual context? Deliver/rehydrate/hand off, preserving work identity and evidence |
| Environment/material · W02 | What does our Team share? Compose exact references; edit owned Instructions through its source route; review changes W05 |
| Environment/material · W03 | Where does this knowledge apply and what supports it? Body/conditions/evidence, model/form/questions, revision and validation |
| Environment/material · W04 | How did this choice arise? Qualified current state, parallel lanes, recorded why and targeted events |
| Environment/material · W10 | Find/move/edit the right material within scope; inspect per-item owner/version, plan and partial outcomes |
| Review · W05 | What exact effect is proposed and what does approval authorize? Preserve separate publish/adopt/use outcomes |
| Team · W06 | Found this Team with reviewable identity, governance and P2P/GitHub conditions |
| Team · W07 | Manage membership, rights, settings, devices and lifecycle with exact affected objects |
| Exchange/recovery · W08 | What is local, unshared, missing or uncertain? Verify/reconcile, then return to the same preparation |

Navigation preserves origin, Team/environment, work/recipient scope, exact
selected version, draft/request identity and return position. Back and home are
different. Browsing another Team does not switch an active task or grant access.
W01 → W08 preserves the original missing-body set until actual sufficient
verification. W05 returns to the same sealed candidate; it cannot silently rebase
approvals. Recheck changed rights/qualifications when returning. Protected metadata
remains protected even when explaining an unavailable route.

Show three relevant dimensions from S05: selected basis, work support and
action-specific eligibility. Material conditions/unknowns remain beside the claim;
raw hashes/manifests can expand. Review-only scenarios cannot contribute unless
an explicit separate grant exists. UI visibility and execution use the same rules,
with fresh execution evaluation rather than trusting an old displayed answer.

### Complete operation contracts

All rows remain **in design scope**; a backend not yet implemented must have a
truthful unsupported state and implementation acceptance, not an inert success
button. These are functional contracts rather than a requirement for separate
pages. Shared mutation behavior is input → validation/effect preview → authorized
submission → actual outcome/recovery, combining already-authorized phases where
appropriate. Drafts survive navigation; discard is explicit.

| Operation | Minimum input / owned effect | Required failure or recovery behavior |
| --- | --- | --- |
| Instructions editing | Owner/base, member/body, applicability, delivery surface/trigger and dependencies; exact diff → source candidate/revision | Field errors and changed-base conflict preserve draft; no implicit Team adoption/current-task switch |
| Knowledge editing | Meaning, scope/body/table, period/conditions/exceptions, evidence, companions and update obligation → owned revision | Missing qualifications stay unresolved; future schedules/late corrections preserve earlier citations |
| Model/graph editing | Stable node/type/definition/scope/evidence and qualified relation endpoints; equivalent table/text view → versioned model | Dangling/duplicate IDs, referenced deletions and unsupported semantics expose exact impact; clean structure is not semantic validation |
| Domain form profiles | Fields/types/constraints/applicability, canonical schema mapping, profile version and samples → versioned previewed editor profile | Invalid mapping/unsupported validators/incompatible data prevent use; no silent exception loss or arbitrary code execution |
| Questions/validation | Pinned targets/domain package/questions/lenses, expected evidence/counterexample → run/results/finding disposition | Empty subject, partial run, timeout, unsupported lens or missing grounding is not a clean review; corrections require revised targets/recheck |
| Search/ranking | Authorized namespace/role, query/exact ref, topic/workstream, current/history, period and supported sort; scoped saved query | Distinguish empty/denied/failed/incomplete; old required decisions and cross-lane corrections survive ranking limits |
| Derivatives | Exact base, permitted new owner/scope/modifications and carried conditions → distinct derivative | Disallowed derivation/export refused; upstream conflicts remain candidates; Team adoption not inherited |
| Decision/outcome capture | Scoped question/choice/workstreams, actual reason/alternatives/premises; observations target records with evidence/time | Missing rationale labeled; notes, acceptance, implementation and verification remain different facts |
| Correction/withdrawal/replacement | Typed exact target, reason/evidence/successor/scope and resulting-state preview → append event | Missing/restricted targets, cycles and competing resolutions remain unresolved; no timestamp winner |
| Permissions/policy | Principal/resource/action ceiling, constraints/expiry, before/after effective powers → governed grant/control receipt | Unknown rights, stale policy, group expansion and revoked authority cannot pass via a role label |
| Team/device/lifecycle | S09 exact identity/effect plan, continuity/custody and applicable governance → separate lifecycle receipts | No ambiguous generic delete; no revival through evidence recovery; unique work and unknown outcomes retained |
| Retention/deletion | Exact owned objects/derived copies, retention obligations/reason/consequences → per-owner removal/retention receipts | Holds, denied, unreachable, partial and unknown removal remain visible; no erasure claim for uncontrolled delivered context |
| Bulk/import/export | Source/destination owner, role/schema/identity mapping, duplicate/conflict policy and permitted closure; per-item plan | Provider-scoped atomicity and per-item results; retry completed/unknown groups with bound IDs, not duplicates or silent skipped successes |
| Offline/exchange | Local drafts/outbox, exact observed refs, permitted sources/recipient/carrier and verification → receipt/availability | P2P/GitHub/package routes have equal semantics; no false absence, adoption, authority or activation from transfer alone |
| Concurrent edits | Common base/current head/candidate/affected subjects → supported reconciliation and conditional commit | Preserve both candidates if base moves; semantic disagreement survives textual merge |
| Unknown operation/outage | Exact request/ID/target and last confirmed stage → query/reconcile/resume/cancel result | Unknown is not failed; cancellation may be too late; no retry under invented new ID |
| Recipient/context inspection | Actual recipient/parent/work, edition/frontiers, body/reader routes and retention/delivery evidence | Missing bodies, incompatible context, unsupported adapter or uncertain delivery limits the claim; parent receipt gives no child credit |
| Provider administration | Verified identity, configured connection/authorization, capability/schema and source conditions | Read-only differs from disconnected/denied/unsupported; conversions create derivatives rather than rewriting imported identities |
| Administrative signals | Authorized scoped reviews/gaps/drafts/transfers/retention/unknown operations → exact owning item | Partial coverage stays qualified; dashboard counts are not complete inventory or authority evidence |
| Scenario harness | Labeled fictional inputs, operation stages and injected races/outages with expected outcomes | Never grants production rights or substitutes fixture success into real operation views |

TUI/CLI retain compact known-item work, remote administration and machine-readable
plans/recovery. A local graphical Studio is the leading experiment for long-source
comparison, models, concurrent decisions and ordinary nondeveloper management.
Core setup/authoring/changes/use/exchange/recovery must remain possible without
GUI; ordinary graphical use must not force nondevelopers into JSON/CLI. Outcome
equivalence does not require identical pixels or every command as a button.

Use locally available assets and an authenticated, authorized local operation
bridge if a browser GUI is implemented. A loopback address or page origin alone
is not a Team grant. No frontend framework, native wrapper or hosting provider is
chosen here. Dedicated/native packaging remains conditional on measured input,
accessibility, distribution and isolation needs. Closing/reopening any surface
recovers durable drafts/outboxes/unknown requests with the same identity.

Keyboard actions, structured equivalents for graphs, focus/error association,
readable contrast, narrow layouts and preserved return position are required.
Actual Korean IME/paste, terminal cell width/resizing, SSH, screen readers, zoom
and host adapter behavior need real supported-surface testing. Mock terminal
screens do not emulate them. Judge correctness/comprehension before speed; use
first-exposure groups and realistic maintainer/nondeveloper jobs. Five spokes,
sidebar placement, wizard length and primary home remain testable presentations.

<a id="s12"></a>
## S12. Acceptance and implementation sequence

The full scope is designed now; implementation can proceed in vertical slices.
Prefer one complete useful path over many independent screens with substituted
fictional identities. Implement common scoped operations and their owning checks,
then appropriate clients. Do not create a universal engine for hypothetical reuse.

| Acceptance group | Required evidence |
| --- | --- |
| First real work | Create/join → first explicit environment or permitted unadopted preparation → actual recipient; same Team/rights/sources throughout, no fabricated history |
| Knowledge | Changing applicability, future schedule and late correction preserve exact old premises; essential conditions survive bounded consumption |
| Concurrent memory | Old required decision and cross-workstream withdrawal remain qualified; missing targets/cycles/conflicting successors do not produce a false winner |
| Required repair G01 | Unauthorized self-add cannot create group powers; explicit bounded delegation works; removal/expiry and same-human multiple identities are handled |
| Required repair G02 | Unadopted investigation works where permitted, retains status, cannot bypass required denial or silently become adopted |
| Required repair G03 | Valid permitted state proof works without private event text; forged/stale/wrong-scope/audience/unsupported proof fails without reviving an old decision |
| Required repair G04 | Archived same-work replacement can succeed under policy; new/broader work cannot; missing identity/authority is explicit |
| Prototype repairs P01–P03 | Review-only cannot save contribution; W01→W08 preserves missing evidence until verification; closed evidence recovery does not reactivate Team |
| Preview/execute race | Revocation, changed policy/base or target between preview/approval and execution invalidates affected permission/conditions |
| Disconnected exchange | No GitHub, closed/internal route, a week between contacts and missed window; useful permitted work, durable outbox, trust/control verification and conflict reconciliation |
| Loss and authority | Recover actual required objects after device/hosted-store loss; report incomplete custody; unavailable finalizer and small-Team participant loss follow governed continuity without invented authority |
| Unknown/partial outcomes | Lost commit response resolves the same request; mixed provider batch preserves real completed/denied/unknown results; no duplicate mutation |
| Recipient/context | New/child/compacted contexts receive actual required bodies; incompatible native context and revoked rights block affected use; matching hashes are insufficient |
| Lifecycle | Leave/forget/archive/restore/close/purge have distinct effects; returning stale copies cannot resurrect deleted material |
| Surface usability | Same task/rights/state across TUI and GUI; find an unfamiliar advanced action and recover from error; measure actual comprehension, input and accessibility |

Each complete-operation row in S11 needs a meaningful permitted case and a
material failure case under the appropriate owner. Mechanical tests establish
deterministic properties; relevance, domain adequacy, real human independence,
usability and operational availability need their corresponding evidence.

Sequence: (1) consolidated contracts and shared scenario identities;
(2) connected successor prototypes exercising the repairs and full journeys;
(3) actual provider/adapter vertical slice and offline/recovery failure tests;
(4) measured usability/scale probes to decide packaging and heavier mechanisms.
Preserve existing Instructions behavior and compatibility during implementation.

<a id="s13"></a>
## S13. Deliberate exclusions and revisit conditions

These exclusions narrow mechanisms, not the user-required operational scope.
Earlier blanket deferrals of sync, P2P, full Studio, advanced editing or Team
CRUD are superseded by the included contracts above.

| Deferred mechanism/detail | Reason | Revisit condition |
| --- | --- | --- |
| Universal content schema, graph database, global writer/workflow/policy service | Different role/owner semantics connect through exact refs and local operations | A concrete required operation cannot preserve those contracts economically |
| Compulsory atomic claims/formal ontology for all prose | Coherent sections/tables suffice | Independent citation/update or repeated ambiguity requires smaller units |
| Generic bitemporal engine and partial-scope algebra | Exact schedule editions and bounded decisions cover initial work | Repeated real interval/exception queries become unreliable or too costly |
| Full transcript ingestion and general argument graph | Significant decisions/outcomes and evidence preserve necessary flow | Missing detail or repeated argument reuse prevents a consequential answer |
| Automatic semantic/causal resolution, global ranking and exhaustive impact inference | Unsupported certainty would obscure explicit evidence and unresolved states | A bounded domain supplies a tested policy and measured benefit |
| Continuous universal refresh, fixed expiry and confidence score | Domain/source conditions differ; qualified checks can occur at operation boundaries | Actual freshness obligations or failures require a targeted mechanism |
| New onto lenses/package redesign | Existing documents/questions/lenses are sufficient integration points | A material evaluation gap cannot be expressed through them |
| Global consensus/blockchain, general CRDT editing, distributed transactions | Replicas, conditional owned heads and explicit conflict handling cover the baseline | Measured multiwriter/finalizer availability needs justify added coordination |
| Mandatory task tracker/global task graph | Existing work/operation evidence can identify continuation | Actual host evidence cannot distinguish authorized continuation reliably |
| Identity-provider-specific group administration | Declare membership authority independently of vendor UI | Before shipping a selected provider's enrollment/removal/recovery integration |
| Final proof wire format, cryptographic suite, universal lease duration | Fix semantics first; concrete provider/source interoperability determines bindings | Before implementing interoperable proof import/export; verification is mandatory, not deferred |
| Dedicated/native GUI, universal home and fixed menu/wizard count | User job, accessibility and operating environment decide representation | Supported-surface and first-exposure evidence favors a specific form |
| Global erase/instant unseen revocation/identical model outputs | Outside the guarantees established by owned sources and offline evidence | Reassess only a narrower enforceable claim with actual evidence |

Maintain exclusions and their revisit conditions in the decision ledger when a
choice closes an alternative. Do not defer permissions, actual control evidence,
source conditions, required bodies, explicit uncertainty or durable recovery.

<a id="s14"></a>
## S14. Evidence, open work and SSOT maintenance

This is a **consolidated design**, not a new implementation release. Existing
Instructions machinery has its current contracts in repository code/docs; this
consolidation does not reverify or change it. The Team/K/M provider system,
decentralized exchange and complete Studio still require implementation evidence.
The separate Instructions naming work retains its compatibility boundaries;
historical component names in earlier artifacts are not current terminology.

Its [handoff](../instructions-rename/2026-09-13T1846--35c75ca--handoff.md) and
[integration record](../instructions-rename/2026-09-13T2227--35c75ca--integrated-source.md)
are provenance for that work. The current
[Instructions compatibility contract](../../docs/instructions-compatibility.md)
owns supported legacy interfaces; this design consolidation neither removes
them nor claims a new published or installed release.

| Subject | Status at this revision |
| --- | --- |
| U01–U18 and full advanced scope | Included in this SSOT with owning sections and acceptance groups |
| G01–G04 audit boundaries | Clarifications integrated into S04–S07/S09; contract and runtime cases still require the S12 evidence |
| P01–P03 earlier prototype mismatches | Historical failing artifacts preserved; not silently fixed by writing this document or drawing a new map |
| Integrated visualization | A Korean projection of selected SSOT relationships/conditions, labeled as design; no source/authority/runtime store |
| Human usability and optimum GUI/TUI packaging | Unproven; concrete evaluation criteria in S11–S12 |
| Whole-design correctness | No formal completeness certification; review and tests close named claims, not all future cases |

The [source inventory](2026-09-14T1504--35c75ca--ssot-sources.json) records exact
pre-consolidation artifact identities and their provenance roles. Hashes identify
what was reviewed, not proof every assertion was correct. Source groups cover
initial research/model, purpose/Team, storage/consumption, full Studio/governance,
P2P/setup/CRUD, requirements/UX, wireframes/hub/cold start and consistency repairs.
The original review/QA evidence retains its stated scope and historical failures.

For future design changes, produce a dated successor of this complete SSOT,
update the single CURRENT.md pointer, and record material decisions/exclusions.
Do not maintain competing latest rules in supplements. Preserve older snapshots;
design projections must identify which SSOT they depict and be regenerated or
clearly labeled stale when it changes. Product purpose stays canonical in
AGENTS.md; implementation terminology stays canonical in the ontology lexicon.
Those are explicit authority boundaries, not competing Team design documents.

The accompanying visualization and consolidation QA are reachable from CURRENT.md.
Its graphics explain relationships and illustrative conditions; if a projection
disagrees with this source, correct the projection and retain evidence of the fix.
No setup selection in a design artifact authorizes a real connection, membership,
publication, data transfer or Team lifecycle operation.
