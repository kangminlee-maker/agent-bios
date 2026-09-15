---
created_at: 2026-09-14T02:17:26+09:00
head: 35c75ca
kind: review
status: consolidated-requirements-and-zero-based-ui-review
scope: user requirements, derived safeguards, current design/prototype coverage
---

# Requirements board and independent coverage review

The product must help people work with and continue a Team's shared standards
and decision context. The next UI should be assessed against that outcome,
without treating the current screen layout as a requirement.

This is one consolidated board for the requirements currently established in
the conversation. It distinguishes user requirements from the mechanisms and
layouts proposed to satisfy them. It is a dated review, not a new implementation
claim or an instruction to rewrite previous dated records.

## How to read the board

**U** identifies a user-required outcome or a preference explicitly recorded as
user-selected. The initial user request and latest consolidation/usability
request are directly available in this task; intervening preferences are traced
through the named records below. A document marked `proposed` is not, by itself,
evidence that every detail in it was required by the user.

Coverage labels are deliberately separate:

- **D:** an interaction/architecture contract is written.
- **M:** a finite simulated interaction has QA evidence.
- **R:** current repository documentation describes a corresponding implemented
  capability. This review did not repeat its runtime verification.

These labels do not add up to a completion percentage. A mocked form cannot
establish a real permission check, data synchronization, semantic validation,
durable receipt, or model delivery.

## Consolidated user requirements

| ID / group | Required outcome | User-origin trace | Present coverage and next proof |
| --- | --- | --- | --- |
| U01 · Purpose | Workers can select, compose, share and inherit an appropriate work environment for their role and work context; changing workers should preserve accumulated standards and decision context. | Purpose clarification [S2]; initial request [S1] | D; M covers separate onboarding/use fragments. The joined new-Team → first-environment → first-work path is not demonstrated. |
| U02 · Purpose | **Team** is the basic selection/adoption/sharing unit. Company, industry, organization and project remain relevant context rather than a mandatory hierarchy. | Explicit Team choice [S3] | D; M Team management. Team identity, memberships and environment choices still lack an integrated provider-backed workflow. |
| U03 · Content roles | Preserve Instructions, Domain knowledge and decision/history memory as distinct roles. **Instructions** replaces the old component name across the product, not only in a naming paragraph. | Initial request [S1]; accepted name [S2]; full migration handoff [S13] | R for Instructions management/naming with declared compatibility; D/M for the broader three-role environment. No implication that Team/K/M providers are implemented. |
| U04 · Design quality | Keep the structure simple, robust and conceptually extensible; record deliberate low-impact exclusions. Consolidate all requirements and review UI/function design from zero, prioritizing intuitive usability. | Initial design instruction; latest user request | The board supplies consolidation. Simplicity must now come from fewer concepts/steps and better defaults, not silently dropping the subsequently included workflows. No user-comprehension study has established intuitive usability. |
| U05 · Domain knowledge | Represent durable principles, direction and structure alongside changing domain rules/parameters; maintain applicability and necessary updates. | Initial request and tax-structure example [S1] | D; M illustrates conditions and a source revision. Real temporal selection, late corrections and external-grounding behavior remain unverified. |
| U06 · Domain knowledge | Support ontology-based knowledge or a meaningful validation/question set, informed by onto's existing **8+1 lenses** and domain package. Include the later-expanded model/graph, domain-form and validation authoring scope. | Initial onto reference [S1]; expanded complete Studio scope [S5] | D; M validates some input presence only. Graph/form editing, question maintenance, actual lens runs and finding-to-revision workflows are not interactively demonstrated. |
| U07 · Decision memory | Preserve the flow of decisions: context, alternatives, stated reasons, evidence and consequences, beyond what Git commits alone retain. | Initial history/ADR request [S1] | D; M limited why/current-state examples and proposed-versus-accepted events. Full capture/correction/outcome workflows and source evidence remain provider work. |
| U08 · Decision memory | Represent concurrent/intersecting workstreams and continuity across sessions and workers; one chronological lane is insufficient. | Initial multiple-flow request [S1] | D; M one cross-workstream correction example. General state closure, intersections, reopening and successor discovery are not verified by that fixture. |
| U09 · Consumption | Supply relevant knowledge and decision context efficiently enough for actual work, including expansion when needed, without losing essential meaning to context limits. | Consumption design request as recorded in [S4] | D; M fixed-topic previews. Required-set selection, retrieval cost/quality, clipping, continuation and rehydration need comparative task evidence. |
| U10 · Complete Studio | Design the previously deferred operational/advanced scope: source editing, graph/form tools, search/ranking controls, personal derivatives, bulk/import/export, administration, dashboards and recovery. Do not defer the design merely because a backend is absent. | Explicit scope expansion recorded in [S5] | D has minimum screen contracts. M and R cover only subsets; the full advanced scope is not an executable integrated Studio. |
| U11 · Working contexts | Make selected material usable in actual work and continuation, including current/new tasks, child workers and context recovery, with clear actual-use state. | Shared-work continuation purpose [S2]; consumption and expanded Studio scope [S4/S5] | R for existing Instructions host routes; M for virtual tasks. K/M readers and recipient-specific delivery/recovery remain unimplemented. |
| U12 · Authority | Define who can read, contribute, review, publish, adopt, grant rights and perform sensitive operations, and how approval relates to execution. | Governance requirement and complete-scope correction [S5] | D; M finite persona/policy fixtures. Those client controls are not authentication, independent-person proof or authority-side enforcement. |
| U13 · Team lifecycle | Design complete Team creation/read/update/delete behavior, joining, members/devices, governance and ownership changes, connection management, and retirement/recovery paths. | Explicit Team CRUD expansion [S10] | D; M substantial subset. Team copying, device retirement, repository provisioning, full purge outcomes and the first environment remain outside the tested fragment. |
| U14 · Data lifecycle | Handle correction, permitted derivation, retention/deletion, access changes and recovery without confusing them with ordinary editing or removal from a view. | Expanded operational scope [S5/S10] | D; M selected correction/suspension/cleanup states. Real multi-owner retention and deletion outcomes remain unverified. |
| U15 · P2P foundation | P2P/local peer storage is the complete default operating foundation. GitHub absence must not secretly remove Team setup, authoring, governed changes, use, exchange or recovery. | Explicit P2P choice [S8] | D; M connection choices and fictional recovery indicators. No real peer exchange, trust bootstrap or recovery proof is supplied by those screens. |
| U16 · GitHub option | Where permitted, GitHub connection is recommended and initially selected in setup; it remains optional, can store real permitted shared state, and can be added/removed without breaking the P2P foundation. | Explicit architecture/default choices [S8/S9] | D; M initial selection, failure, later connection and restricted-scope cases. No real account/repository binding or transfer is performed. |
| U17 · Disconnected work | Support closed networks and approximately one or two synchronization opportunities per week, with permitted internal/direct/package routes and useful local operation between contacts. | Network/frequency requirement recorded in [S6] | D; M planning inputs and selected offline fixtures. End-to-end offline setup, exchange, missed-window recovery and current-state reconciliation are not tested. |
| U18 · Recovery through peers | More authorized retained copies should improve recoverability after loss of a worker/device or hosted service; expose actual retained coverage and pending exchange/recovery. | Peer robustness request [S7/S8] | D; M fictional copy counts. Actual complete-object custody, device-loss reconstruction and unique-outbox recovery need operational evidence. |

### Advanced scope, without another requirements explosion

U06, U10, U11, U12, U13 and U14 together retain all the earlier operational
deferrals. Their detailed fields/actions remain in [S5] and [S10]. The board
does not turn every table cell or exceptional error message into another
top-level requirement. An owner can drill down from one U ID to those contracts
and their acceptance cases.

Research memos, issue-tree visualization, prototypes and migration handoffs are
requested **design deliverables**. Their existence should be recorded, but it
does not automatically make a diagram editor, research service or handoff
generator a new product feature.

The user also requires the purpose to remain explicit in the repository's
agent-facing charter and decision ledger. The current canonical purpose block
and its README/CLAUDE projection contract belong to U01's repository obligations;
their presence is not proof that every model paid attention to them. Easy Korean
explanation and reviewable visualizations belong to U04's design deliverables.

## Derived safeguards: preserve their effect, reconsider their presentation

These are design obligations supporting the U outcomes. Their exact fields and
mechanisms are assistant proposals; they are not additional user quotations.

| ID | Necessary distinction or safeguard | UI consequence |
| --- | --- | --- |
| D01 | Source ownership, Team adoption, environment composition and actual task use are different facts. | A worker should understand the effective choice and any relevant difference; every internal fact need not become a separate page or badge. |
| D02 | Stable identity differs from version, name, location and GitHub account. Earlier decisions retain exact premises and original rationale. | Names can be friendly; exact identity/history remains available when needed. Repository changes must not create another Team implicitly. |
| D03 | Domain applicability, local availability, scoped acceptance and review evidence differ. | Show the qualification that affects the current judgment; a recent check cannot manufacture current truth. |
| D04 | Required knowledge companions and memory state-changing closure precede ranking/clipping. | Search summaries cannot hide exceptions or revive a corrected/withdrawn choice. Missing requirements remain actionable. |
| D05 | Rights are scoped and constrained by source owners; selecting a role/Team/connection or copying a derivative grants no extra power. | Explain actual unavailable actions without exposing restricted details. Reuse valid authorization rather than repeatedly requesting it. |
| D06 | Approval binds an exact change; execution rechecks it and commits through its owner. Unknown outcomes and conflicts are not ordinary retry success. | Combine already-authorized steps where possible; preserve one meaningful review and outcome/recovery path. |
| D07 | Replication, content approval and ordering shared-head changes are separate. Offline evidence has limits. | A useful local environment can have GitHub pending or fewer retained copies than desired. Avoid a universal red/green “Team ready” state. |
| D08 | Local forgetting, membership departure, reversible archive, logical closure and physical removal affect different objects. | Use explicit object/effect labels and a concise consequence review; do not present ambiguous generic Delete. |
| D09 | P2P enrollment/retention cannot fabricate independent people, authority, complete copies or instantly observed revocation. | Nomination/connection/upload are not membership, custody or approval. Label simulated states as simulation. |
| D10 | Founding and authority succession must not create circular approval dependencies or unauthorized bypasses. | New-Team bootstrap and unused-setup cancellation need bounded paths; established policy cannot silently fall back to solo. |

No safeguard requires copying a universal cryptographic network, a global
database, or every private record to every peer. The contract is the required
effect; a smaller implementation can satisfy it if the relevant failures remain
detectable and recoverable.

## Current proposals that are not user-mandated UI requirements

| Proposal in earlier designs | Classification in this review |
| --- | --- |
| Four content destinations plus Review, Team/access and Operations | Reversible navigation hypothesis. Preserve role/authority distinctions; compare a module-first shell with task/context and environment-notebook alternatives. |
| Four-step Team wizard | Reversible workflow arrangement. Keep the user-selected eligible GitHub recommendation, P2P alternative and explicit effects; the number/order of pages can change. |
| Separate Preview, Readiness and Use buttons | Demonstration arrangement. Required distinctions can remain in request/receipt handling without three routine manual clicks. |
| One independent human reviewer as the shared-Team default; named role templates | Proposed governance defaults. Independence must be real when claimed, and existing Team policy must be obeyed; the user did not require this exact universal count/template. |
| Three retained copies | Proposed configurable durability target, not a universal user minimum, quorum or proof of independent failure domains. |
| One logical finalizer on a member's device | Proposed minimal finalization mechanism with an explicit write-availability tradeoff; not equivalent to the user's choice of distributed storage. |
| Exact manifests, file layouts, SQL/index choices, graph/vector infrastructure, signing formats | Architecture/implementation proposals subject to the required identity, authority, continuity and offline contracts. GitHub recommendation does not mandate GitHub-only semantics. |
| Studio label, sidebar orientation, palette, spacing and typography | Reversible presentation choices. The explicit Instructions name/meaning remains; intuitive interaction is the criterion for the larger shell. |
| Fixture actors, copy counts, repository list and numeric offline range | Test data only. They must never become silent product limits or claims about real rights/storage. |

Changing a proposal requires updating its design rationale and affected tests.
It does not mean weakening an established Team's live policy through a visual
toggle or dropping a user-required capability from scope.

## Conflicts and gaps found

### F01 — There is no demonstrated joined first-use journey

The Team prototype ends with zero environments. The Studio prototype starts
with an already populated/adopted environment. Governance examples assume
qualified fictional people. Each fragment has useful tests, but they do not
prove that one new worker can progress from Create/join Team through source
selection and the first environment to useful work without an unexplained
handoff. This is the highest-impact coverage gap for U01/U02/U09/U13.

The next comparison should use one continuous fixture and preserve its actual
Team ID, draft, permissions, environment and task state across the whole route.
Do not fill the gap by precreating a hidden environment or switching to an
unrelated prepared scenario.

### F02 — The current structure risks making the user navigate the data model

The designs expose Team, environment, edition, source revision, frontier,
approval, publication, adoption, delivery, custody and connection state. Those
are often necessary internal distinctions. Their simultaneous prominence is
not evidence of intuitive UI. The current QA measures finite transitions and
layout, not whether a newcomer understands what to do or why an action is
blocked.

Treat this as a usability risk to test, not a proven preference for another
layout. A primary view should answer: what work/environment is selected, what
can I do now, and what meaningful condition needs attention? Drill down to
source/policy/history details. Preserve qualifications without requiring users
to learn every storage term first.

### F03 — Earlier defaults remain visible in historical prototypes

The following are amended history, not active requirements:

- The 18:04 naming record retained old commands; the later full migration and
  current Instructions documentation supersede that implementation description.
- Earlier generic Company wording is amended by the explicit Team choice.
- The old governance mock blocks shared execution whenever offline. [S6]
  explicitly permits valid offline authority/approval under the chosen policy.
- Earlier UI/advanced-workflow deferrals are superseded by [S5].
- Earlier server/GitHub arrangements are refined by the user-selected complete
  P2P foundation and eligible GitHub recommendation [S8/S9].

Keep the old snapshots unchanged, but link them as historical evidence. A new
consolidated UI must not reproduce these superseded defaults merely because
their old mockup already has code.

### F04 — Written advanced coverage is not interactive or runtime coverage

The complete screen matrix establishes scope and minimum contracts. The QA
records explicitly exclude most graph/form editing, full search, derivatives,
bulk transfer, provider setup, real retention outcomes and recipient-specific
context recovery. Team QA additionally excludes copying, device retirement,
repository provisioning and the first environment. U10 is therefore designed
in outline, not demonstrated as an integrated usable product.

The answer is not another expanding list of inert buttons. Group related
actions around their object/task and demonstrate representative normal and
failure paths, retaining explicit coverage for every required capability.

### F05 — Small-Team administration needs a realistic usability case

The governance contract preserves independent review and last-owner/recovery
continuity. Bootstrap and founding cancellation address real deadlocks. However,
prototype handovers assume several eligible fictional people. A two-person
established Team that loses one person/device or has a role beneficiary who
cannot review still needs a comprehensible path under its actual policy.

This review does not declare the safeguards contradictory or require an
approval bypass. It identifies an unproven operating/UX case: show exactly what
can continue, what is pending, and the supported succession/recovery action.
The user did not require every Team to grow to a particular population just
to satisfy a fixture's role assignments.

### F06 — “Ready” and “done” need task-specific meaning

Creation, governance completion, source availability, allowed offline use,
replica coverage and GitHub connection can legitimately differ. A single global
completion badge either blocks useful work unnecessarily or hides a missing
requirement. Likewise, all results fitting in a preview or a transport returning
success is not proof of semantic sufficiency or actual child delivery.

Retain the separate facts, but summarize them according to the user's current
goal: ready to draft, usable for this task, awaiting shared review, or needing
another retained copy. This is a presentation redesign over the same contracts.

## Zero-based comparison without changing scope

Compare the module-first baseline, a task/context brief, and an environment
notebook using the same tasks, source rights, approval policy, data and failures.
Navigation categories, default panels and grouping may vary. Do not make one
alternative look simpler by removing difficult required states or silently
granting extra privileges.

Use these six end-to-end probes as the common denominator:

1. New person creates/joins a Team, chooses the connection route, establishes
   needed responsibility, creates/selects an environment, and starts useful work.
2. Returning person identifies the relevant decision and domain support, sees
   the material changes/unknowns, and continues without reading the full history.
3. Maintainer edits a source or environment, obtains required review, adopts
   the result, and understands why an existing task has not silently switched.
4. An eligible reader finds needed material through search and inspects its
   conditions/history; an advanced author uses the related model/form/bulk path.
5. A closed-network worker exchanges a package, resolves missing/conflicting
   data or a lost outcome, and recovers from an authorized peer without GitHub.
6. A member performs a Team lifecycle/access operation and can explain whether
   it affected membership, local storage, Team activity, sources or a repository.

Evaluate completion, wrong-object actions, misunderstanding of current versus
pending state, avoidable repeated input/confirmation, recovery from a mistake,
and the ability to find less-frequent capabilities. Mechanical click-through,
no-overflow checks and attractive screenshots are useful but insufficient.
Choose measurable targets after observing the baseline; do not invent a
universal click count or claim a performance gain before comparison.

## Trace index

- **S1 — Initial knowledge/history problem:** direct initial user request;
  [pre-design research](2026-09-13T1425--9501eff--pre-design-research.md).
- **S2 — User purpose and Instructions choice:**
  [accepted purpose/name](2026-09-13T1804--35c75ca--purpose-and-instructions-name.md).
- **S3 — Team as the basic unit:**
  [accepted Team amendment](2026-09-13T2027--35c75ca--team-as-environment-unit.md).
- **S4 — Efficient consumption:**
  [knowledge/memory consumers](2026-09-13T2138--35c75ca--knowledge-memory-consumption.md)
  and [scenario review](2026-09-13T2150--35c75ca--consumption-scenario-review.md).
- **S5 — Complete Studio/governance scope:**
  [governance design](2026-09-13T2336--35c75ca--studio-governance-design.md)
  and [complete screen contracts](2026-09-13T2338--35c75ca--studio-complete-screen-contracts.md).
- **S6 — Disconnected/weekly operation:**
  [storage and exchange design](2026-09-14T0003--35c75ca--disconnected-storage-and-sync.md).
- **S7 — Peer replication request and proposed mechanism:**
  [peer checkpoints](2026-09-14T0107--35c75ca--peer-replicated-team-checkpoints.md).
- **S8 — User-selected complete P2P foundation and optional GitHub storage:**
  [selected architecture direction](2026-09-14T0114--35c75ca--peer-default-with-github-sync.md).
- **S9 — User-selected GitHub recommendation:**
  [setup default](2026-09-14T0127--35c75ca--github-recommended-setup-option.md).
- **S10 — Complete Team CRUD:**
  [lifecycle design](2026-09-14T0132--35c75ca--team-crud-and-creation-design.md)
  and [operation scenarios](2026-09-14T0135--35c75ca--team-lifecycle-scenarios.md).
- **S11 — Actual prototype evidence and explicit limitations:**
  [Studio QA](2026-09-13T2328--35c75ca--studio-ui-qa.md),
  [governance QA](2026-09-13T2355--35c75ca--studio-governance-qa.md),
  [Team QA](2026-09-14T0202--35c75ca--team-crud-qa.md).
- **S12 — Current implemented Instructions boundary:**
  [README](../../README.md) and [Instructions documentation](../../docs/instructions.md).
- **S13 — Full naming migration scope:**
  [migration handoff](../instructions-rename/2026-09-13T1846--35c75ca--handoff.md)
  and [current compatibility contract](../../docs/instructions-compatibility.md).

For the next active requirements home, retain the U IDs and their provenance,
link detailed designs rather than duplicating them, and record explicit user
changes. Keep D safeguards and reversible UI hypotheses visibly separate. The
user should not have to reconstruct current scope by rereading every dated
amendment, and this review must not be presented as permanent current state
after its requirements or evidence change.
