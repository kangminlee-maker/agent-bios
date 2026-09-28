---
created_at: 2026-09-14T07:58:28+09:00
head: 35c75ca
kind: design
status: proposed-interaction-direction-human-validation-pending
amends: 2026-09-14T0222--35c75ca--zero-base-product-and-ui-review.md
requirements: 2026-09-14T0217--35c75ca--requirements-coverage-review.md
---

# Zero-base review: disposition and complete scope

## Outcome

Retain the product's semantic, authority and continuity contracts; revise the
UI around users' decisions rather than mirroring storage and administration
modules. The previous seven-destination structure and repeated protocol-step
buttons are not established as optimal. They explain the implementation's
distinctions but can make useful work depend on learning those distinctions.

The review does not establish a universal replacement home. **A work-context
brief is the leading worker-facing hypothesis. A shared-environment notebook
is a serious primary Studio candidate for authoring and maintenance.** Both
must remain directly accessible, with the same sources, authority and state
qualifications. Physical layout follows those jobs, not the reverse.

This completes the requested desk review and prepares inspectable alternatives.
It is not a completed human usability study or proof that either candidate is
optimal. The earlier detailed analysis remains useful; this disposition narrows
its "leading hypothesis" to the relevant user/channel rather than every Studio
visit.

## One board for the requirements

The [consolidated board](2026-09-14T0217--35c75ca--requirements-coverage-review.md)
retains eighteen requirement groups with source traces, ten derived safeguards,
and a separate list of reversible design choices. Its U IDs remain stable for
this review. This small index puts the full scope in one view without treating
every exceptional field as another product feature.

| Requirement groups | Outcome to preserve | Where users encounter it |
| --- | --- | --- |
| U01–U04: purpose, Team, three content roles, design quality | Select, compose, share and inherit Team work environments; retain the accepted Instructions name and explicit project purpose | Team/environment selection, useful first work, coherent source-aware presentation; purpose remains in the repository charter and ledger |
| U05–U06: domain knowledge | Stable principles plus changing applicable knowledge; ontology or competency questions, 8+1 lenses and domain-package authoring/validation | Current task support, then source evidence and specialized knowledge authoring |
| U07–U09: decisions and consumption | Current choices, reasons, alternatives, concurrent workstreams and bounded context without loss of required meaning | Work brief, recorded why, scoped history, exact expansion and recipient re-delivery |
| U10–U14: complete Studio, working contexts, authority, Team/data lifecycle | Complete management and advanced operations with correct source, approval, execution, retention and lifecycle effects | Direct source/environment management, contextual review/recovery, and Team management; all detailed contracts stay in scope |
| U15–U18: P2P, optional recommended GitHub, disconnected use, recovery | A complete P2P foundation; convenient optional GitHub; work across closed/weekly networks and device loss | Local usability, meaningful pending exchange, peer recovery, explicit connection and custody administration |

The requirement to provide easy Korean explanations, an issue tree, reviewable
mockups and naming handoff belongs to the design deliverables. It does not
silently add a research service or diagram editor to the shipped product.

The board's 02:17 coverage assessment describes evidence then available. The
new comparison adds a continuous simulated Team-creation-to-first-work path;
it does not turn the previously unverified provider-backed path into an
implemented feature. Advanced written contracts remain distinct from interactive
and runtime coverage.

## The missing audience/channel decision

A worker may receive selected instructions and reference context within an
existing host application, CLI or MCP flow. A human opening Studio may instead
be creating, inspecting or maintaining shared environments. The conversation
does not establish the frequency of these visits. Assuming every worker must
open a task dashboard in Studio would be another conventional arrangement
chosen before observing the work.

Do not force nondevelopers to use a CLI or exclude ordinary workers from Studio.
Provide graphical direct routes to accept a received invitation/context, choose
a Team/environment, start/continue, inspect why, hand off, and recover missing
material. Hosts can expose the same contract through their appropriate surfaces.
Their authorization, adopted/actual-use state, source evidence and limitations
must agree with Studio; sharing data alone is not enough.

The work brief is therefore a consumption/launch/inspection surface that can
fit an existing workflow. The environment notebook/catalog is a compositional
authoring surface that can serve Studio's main use. A person can move between
them without changing their rights or being required to register a new task.
If research shows another entry model, adapt the entry while preserving those
complete routes.

## Concrete changes to retain

| Earlier interaction | Revised design rule |
| --- | --- |
| Pick a source category before getting useful context | Assemble one task-specific brief with visibly different source meanings; keep direct browsing/editing for specialists |
| Click Preview, Check and Use for every start | One clear intent may prepare, validate and deliver under existing authorization. Preview remains available; stop for a real choice, missing requirement or failure |
| Every internal state appears at equal weight | Keep Team/environment and material limitations visible. Expand raw IDs, manifests, grants and detailed receipts when they help a decision or audit |
| Everyone starts with Team creation/configuration | Existing members, invitations and known host context have their own direct routes. Only founders/operators configure a new Team |
| A fixed number of wizard pages | All required choices remain available during creation; sequence or one reviewable sheet follows dependencies and tested comprehension |
| GitHub or copy-count warnings imply the work is blocked | State local usability separately from optional exchange or durability targets; actual source/permission requirements still block dependent work |
| Fewer menus could hide advanced features | Keep visible source/environment and Team-management entry points; test findability for infrequent authoring, recovery and lifecycle operations |

Progressive disclosure cannot hide a material condition, exception, correction,
unknown, requested privilege or destructive scope. A shortened explanation
must not become a less qualified claim. Combining UI actions cannot combine
source ownership, approval, publication, Team adoption and delivery into one
ambiguous authority event.

One-reviewer policies, three-copy targets and named role bundles remain proposed
operating defaults, not immutable user requirements. Reconsider them against
the actual Team's needs without silently weakening an already-established
policy. The selected P2P foundation, GitHub recommendation and full CRUD scope
are user choices and remain.

## Function design still needs operational evidence

The preserved architecture is not declared optimal merely because its concepts
are coherent. Three common operations can reduce duplication across surfaces:
prepare/read the scoped context, propose/review an exact change, and execute/
recover the authorized effect. Their role-specific payloads and authorities stay
distinct; this is shared orchestration, not a universal editor or reducer.

The following are the highest-impact functional probes before implementation
can claim the purpose is met:

| Probe | What it decides |
| --- | --- |
| Joined setup through first real work | Whether the Team, source-selection, approval and actual consumer adapters form a usable whole rather than several unrelated demos |
| Two-person Team loses a required participant/device | Whether the selected policy and recovery route are operable at the Team's real scale; never synthesize a third human or silently weaken independence |
| A week without authority contact, followed by conflicting changes | Whether local work, outboxes, control evidence and reconciliation are reliable; a storage copy does not confer finalization rights |
| A local finalizer is unavailable | Whether the explicitly accepted delay in new shared writes is tolerable; this limitation is not removed by P2P replication or GitHub |
| New/compacted/child consumer needs knowledge and decisions | Whether required bodies and qualifications reach that actual consumer at acceptable cost; a parent's manifest or unchanged hash is insufficient |
| An expert maintains a large domain or decision set | Whether search, source-aware editing, validation and lifecycle operations remain findable without forcing ordinary workers to navigate their machinery |

Design scope remains complete for each probe. Actual timing, reliability,
retrieval quality and workflow frequency need evidence before selecting a
heavier service, a new finalization mechanism or a different default. Changing
the visual arrangement cannot substitute for those implementation obligations.

## What the comparison does and does not demonstrate

The [comparison source](2026-09-14T0222--35c75ca--zero-base-comparison-prototype.html)
has two entry models with the same fictional data and shared preparation reader.
A begins with current work context; B begins with the reusable Team environment.
Both can start known work directly and recover missing source bodies. B is not
penalized with a mandatory extra preparation click just to make A look better.

Cases cover return to work, GitHub-unavailable permitted work, a changed Team
edition, missing required support, approval without execution rights, and a
new-Team path. That last case preserves one Team ID through governance setup,
the first explicit environment draft, publication, adoption and simulated
delivery. New-Team memory is truthfully empty; a prepared Team's past decisions
are not silently copied in.

The controls for receiving a colleague's reply are explicitly simulated test
inputs. They are not an implemented invitation, authenticated approval or
permission check. The comparison's advanced-management directory demonstrates
the entry/grouping hypothesis; it does not reimplement the full editors and
Team CRUD already specified elsewhere.

The original module-first prototypes remain a historical baseline. This is
not a controlled three-way human experiment: they use earlier fixtures and
some superseded assumptions. A fair experiment must normalize data, permissions,
conditions and tasks before comparing results or claiming improvements.

## Choosing a primary interaction requires human evidence

Before each test, establish the participant's job, normal work surface and
reason for opening Studio. Give a believable goal without the navigation path.
Observe the selected Team/environment, interpretations of current versus pending
state, needed assistance, wrong-object actions and recovery. Measure time only
as observed; never invent a productivity score from screenshots or button counts.

Use separate first-exposure groups for novice comprehension. Later within-person
comparisons can counterbalance order and use equivalent tasks, but concept
learning still carries over and is not a second naive first use. Include ordinary
and nondeveloper workers as well as maintainers and Team operators.

Required probes include: join/create through first useful work using the same
identity/state; resume after a relevant change; propose a domain correction;
approve without claiming rollout; continue permitted offline work; recover a
missing required body; and distinguish Team closure from local removal.
The [detailed review](2026-09-14T0222--35c75ca--zero-base-product-and-ui-review.md)
provides the task scripts and decision criteria.

Critical scope/authority misconceptions must be corrected before choosing an
interaction. The simpler-looking candidate cannot win by dropping difficult
states, hiding maintenance, giving extra rights or forcing work into a new
task tracker. If maintainers dominate real Studio use, B may be primary there
and A may primarily appear in consumer/host flows. This remains a hypothesis,
not a statement that those user frequencies have been measured.

## Review and validation disposition

Independent delegated reviews covered requirements traceability, governance
boundaries and a UX analysis performed before seeing the existing prototypes.
They required two material improvements: validate the joined first-work journey,
and separate first-exposure research from learned comparisons. Those are now
in the prototype/test plan. A final channel/audience review found no critical
contradiction, provided worker graphical paths and the same authority semantics
remain accessible across surfaces.

The [QA record](2026-09-14T0758--35c75ca--zero-base-comparison-qa.md) reports ten
grouped fictional interaction checks and their limits. No participant study,
new runtime adapter, actual Team/source mutation, GitHub/P2P connection, or
real host activation was performed. The review is complete; empirical selection
of an optimal interface is still open.

Research-method support and its precise limits are linked in the detailed
review. In particular, a functional click-through is not the goal-based
observation of actual or likely users described by
[GOV.UK usability testing guidance](https://www.gov.uk/service-manual/user-research/using-moderated-usability-testing).
