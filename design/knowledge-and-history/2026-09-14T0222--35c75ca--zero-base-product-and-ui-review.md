---
created_at: 2026-09-14T02:22:09+09:00
head: 35c75ca
kind: review
status: revised-interaction-hypothesis-human-validation-pending
amends:
  - 2026-09-13T2328--35c75ca--studio-ui-design.md
  - 2026-09-13T2338--35c75ca--studio-complete-screen-contracts.md
  - 2026-09-14T0132--35c75ca--team-crud-and-creation-design.md
---

# Zero-base review of the complete product and UI

## Verdict

The current designs are useful authority/data/operation contracts, but the
prototype interaction is not established as optimal. It repeatedly asks a
worker to operate the architecture: choose a content category, inspect each
store, step through protocol phases, then finally start work. More administrative
requirements produced more destinations rather than a reconsidered entry model.

Preserve the semantic and reliability contracts. Replace the assumption that
their structure must become the primary UI. The leading hypothesis is a
**work-context brief**: show the Team/environment, relevant working standards,
current decisions and material limitations for the work being started or resumed.
Retain a direct environment-notebook/catalog entry for people who want to explore
or maintain material without a task. Compare both against the module-first
baseline before choosing a final primary interaction.

This is a requirements synthesis and cognitive walkthrough. Neither agreement
between AI reviewers nor successful scripted clicks proves human usability.
There are no observed Studio participant results, measured productivity gains,
or numerical "optimality" scores in this review.

## 1. What is fixed, and what is open

The product purpose is workers selecting, sharing and inheriting **Team** work
environments, using Instructions, Domain knowledge and Decision memory to
continue appropriate work across people, models, sessions and devices.

User requirements include distinct source meanings, stable/changing domain
knowledge and ontology/question support, decision rationale and parallel
workstreams, efficient consumption, full Studio and Team CRUD scope, explicit
authority/approval, offline and closed-network operation, P2P as the complete
foundation, and GitHub connection as the recommended optional setup choice.

The following are changeable design choices, not additional user demands:

| Earlier choice | Disposition in this review |
| --- | --- |
| Seven permanent destinations copied from source and operational modules | Reopen. Entry/navigation follows user jobs and context; all functions remain reachable. |
| Separate visits to Instructions, knowledge and memory before starting | Replace for ordinary work with one scoped brief, preserving typed sources and qualifications. |
| Manual preview, readiness check, then use on every start | Replace with one intent action where authorized; keep distinct underlying operations/evidence. |
| A fixed four-page creation wizard | Reopen. All creation choices stay available; the page count follows dependencies and research. |
| All status axes and version/frontier counters in every header | Replace with context-relevant status plus expandable exact evidence. |
| One reviewer, three retained copies, named role bundles | Keep as explicitly proposed defaults where applicable; do not treat those numbers or labels as user requirements. |
| Finalizer, grant ceiling and checkpoint vocabulary during routine use | Expose when needed for administration, failure explanation or audit; ordinary wording names the effect. |
| A new task must always be created to use a changed environment | Use the supported actual recipient/context; require isolation only when needed. |

No requested capability is removed from scope. Moving a graph editor, retention
review or Team closure behind an appropriate entry is not postponing its design.
Source-specific forms and the previous complete lifecycle contracts remain
applicable unless this review explicitly changes presentation or orchestration.

The user selected decentralized storage, not arbitrary permissionless consensus.
Logical finalization, publication, Team adoption and replication retain their
distinct meanings. A transport convenience cannot override those obligations.

## 2. Start with the user's decisions

These are task hypotheses grounded in the stated product purpose, not personas
validated by interviews. A single person may occupy several roles.

| User situation | First useful outcome | What they should not have to learn first |
| --- | --- | --- |
| Joining a colleague's work | Understand the received Team/environment, current choices, open questions and permitted next action | Internal source taxonomy, repository setup, opaque history IDs |
| Returning to work | Recover the prior working context and see material changes affecting it | All Team settings or the entire history |
| Starting a different role/Team | Confirm the intended Team/environment and know the applicable scope before delivery | A new task-tracker schema or an assumed link between role and permission |
| Maintaining knowledge/instructions | Find the owned source or permitted derivative and propose the right kind of change | An artificial task registration before editing |
| Recording/reconsidering a decision | Capture choice/reason or inspect the actual correction/replacement path | Treating history as an editable generic document |
| Reviewing a change | Understand the exact effect, evidence, authority and who acts next | Every storage/transport phase as a separate manual action |
| Operating a Team | Create/manage/recover/retire the actual Team safely | A display-only dashboard that hides the needed administrative route |
| Working during disconnection | Know what can continue, what is local/unshared and what requires new evidence | Equating GitHub connectivity with permission or readiness |

The first screen must answer three questions: **Which Team/environment am I
using? What matters for this work? Can I proceed, or what concrete thing is
missing?** Exact provenance remains reachable without requiring memorization.

Task-first does not mean a new general-purpose task manager. Reuse host-provided
task/project context, workstream references and prior preparation/delivery
receipts. Do not require a new task name, due date, assignee or board card.
When task context is absent, allow environment exploration and ask only for
conditions that materially change the required knowledge/state.

## 3. Critique of the current design

The existing three finite prototypes demonstrate operation distinctions, not a
joined product journey. The observed source entry remains Instructions Studio
in `compose/instructions_ui.py`; this review does not claim implemented Team,
knowledge, memory or P2P providers.

| Finding | Evidence in the existing design/prototype | Consequence | Revision |
| --- | --- | --- | --- |
| The module model leaks into the entry experience | Four content areas expanded to seven destinations | Ordinary workers must classify their need before receiving useful context | Work-context entry plus direct source/environment exploration |
| Protocol phases became a manual ceremony | Context preview → readiness → use; publication → adoption demo clicks | Users perform machine-checkable transitions repeatedly | Orchestrate authorized phases; stop only for meaningful choice, missing input or failure |
| Setup precedes visible value too often | Team creation and storage/governance details dominate recent prototypes | An invited worker can appear to need to configure a new Team or repository | Invitation/known-context route bypasses creation, without bypassing consent or grants |
| Status precision has no hierarchy | Draft/adopted/task versions, frontiers and retention counts appear together | Important blockers compete with informational lag | Keep current context and relevant impact visible; details on demand |
| Routine offline operation looks like an exception | Earlier governance fixture has one blanket offline-blocking mode | Users can infer GitHub absence means work is impossible | Show qualified local usability and pending exchange separately |
| Advanced capability lists are not findability evidence | Graph/form/bulk/recovery contracts exist mainly as tables | Complete documentation can hide a difficult-to-find function | Map each capability to a user intent, entry and return path; test discovery |
| Maintenance and work can become disconnected | Each fixture has its own state and starting assumptions | Team creation does not naturally lead into first environment, use and handoff | Test a joined lifecycle with the same identities and real providers later |
| Professional and authorization roles are easy to confuse | Role-like vocabulary is repeated in setup and permissions | Selecting an accounting/development profile may look like access elevation | Separate "what work" from "what this account may do" |
| A unified source view may imply universal editing | Composition presents excerpts from separately owned sources | Editing an excerpt can appear to edit the shared source or overwrite memory | Offer source-aware actions with explicit target/effect before submission |
| No actual-user evidence chooses the entry model | QA records verify fixture transitions and widths | "All tests passed" cannot establish intuitive understanding | Compare believable tasks with likely users and record misconceptions |

The asynchronous storage amendment supersedes the older blanket offline fixture.
The advanced/Team CRUD contracts supersede their older deferrals. Preserve those
dated records as evidence, not simultaneous current alternatives.

## 4. Alternative interaction models

Evaluate organizing objects before arranging navigation. None is preferred
because it has a sidebar, fewer cards or a fashionable layout.

| Model | Primary object/action | Strength hypothesized | Risk to test |
| --- | --- | --- | --- |
| Existing module-first baseline | Choose a store/administrative area, then operate it | Predictable for trained administrators who know the model | High conceptual entry cost for ordinary or returning workers |
| A. Work-context brief | Open known work/handoff or select an environment for present work | Useful current context and recovery action appear together; fewer classification decisions | Can accidentally become a task tracker or hide maintenance with no active task |
| B. Shared environment notebook | Open the team's selected environment and explore its coherent standards | Clear ownership and orientation; suitable for browsing and maintaining a reusable environment | Large material may overwhelm a returning worker or obscure an urgent contextual change |

Take A as the leading test hypothesis and retain B as a direct entry and serious
comparison. B must receive meaningful resume/change shortcuts; A must receive
visible source-management and Team-management entries. Do not deliberately
make one candidate weaker to validate the preferred answer.

Known host context or an invitation may route directly to the appropriate
object. A new visitor without either gets an explicit choice to open an available
environment, accept an invitation or create a Team. The app must not infer
membership or import private history from a name match.

## 5. Functional orchestration versus visible steps

| Intent | Visible commitment | Required internal phases/evidence |
| --- | --- | --- |
| Start with the shown environment | `이 기준으로 작업 시작` naming Team/environment and actual recipient | Scope/access resolution, required bodies, qualifications, compatibility, exact delivery and receipt; stop on unmet conditions |
| Resume | `이 기준으로 이어가기`, with meaningful changes offered when relevant | Retained-context check or re-delivery, permitted current frontier and source qualifications; preserve old context identity |
| Approve | Exact proposed change and effect, then `변경 승인` | Current reviewer eligibility, fixed request/policy/content and approval evidence; execution remains pending if not authorized here |
| Publish and adopt where already authorized | One action explicitly naming both exact effects, such as `4판 발행 및 이 팀에서 채택` | Separate publication and adoption operations/receipts; recover partial/unknown results, no cross-provider atomicity claim |
| Recover missing local material | `다른 팀 사본에서 받아 준비`, with the permitted source identified | Scope-aware inventory, integrity/control checks, complete required body closure; receiving is not automatic use |
| Propose a source/decision change | Target-aware revision, derivative, new decision or correction action | Source ownership, exact base, typed semantics, current approval rules and durable request identity |

A preview remains accessible before use and compulsory where policy or a
material changed effect requires user review. It is not a universal extra click.
One intent may span several authorized operations, but no intent grants missing
permissions or treats approval as execution. A partial result says which phase
completed and what remains; it does not return to an unqualified start screen.

## 6. Information hierarchy

| Visible when | Information |
| --- | --- |
| Always relevant to current action | Team and selected environment; current work/recipient context if known; material blocking condition or allowed operating scope |
| When choosing or changing an effect | Difference between current task and adopted edition; source ownership; apply/adopt/use targets; relevant period/condition/exception; missing required evidence; requested privileges or deletion scope |
| Expandable audit/administration | Full manifests, opaque IDs/digests, full checkpoint lineage, grant ceilings, raw receipts, complete peer inventory, detailed validation reports |

Conditions and exceptions necessary to interpret a shown claim never disappear
behind progressive disclosure. "Details" can hold deeper evidence, not the
qualification that makes a visible answer true. Similarly, a revoked decision
must not appear current merely because the correction is collapsed.

Use text tied to the user's decision. Korean examples are
`이 작업에 필요한 근거가 없습니다`, `지난 교환 때 확인한
기준으로 작업 가능`, `승인 완료 · 담당자의 발행 대기`, and `이 작업은 3판,
팀의 새 기준은 4판`. Ordinary sync delay or an unmet optional copy target is
not styled like a permission failure. A mandatory custody/source requirement
still blocks the dependent operation.

The colloquial UI phrase `팀 기준` is a presentation of the selected work
environment, not a renamed storage object or a claim that one Team has one
environment. Display the environment name with it. Instructions, Domain
knowledge and Decision memory retain their canonical meanings and owners.

## 7. Joined journeys and retained management coverage

1. **Join or receive work:** open a verified invitation/handoff → inspect exact
   Team and offered scope → consent/enroll as required → read the useful brief
   and gaps → start when permitted. The invited worker does not create a Team
   or connect their own GitHub repository just to enter existing work.
2. **Return:** open the previous preparation/work reference → recover bodies
   and show relevant change → continue the permitted prior basis or prepare a
   changed basis. Merely receiving a new edition never switches the old task.
3. **Maintain:** enter directly through environment/source exploration or from
   a questionable passage → inspect the owner and exact source → propose the
   appropriate typed change → review effect → follow its authority workflow.
4. **Review:** open the authorized request at the affected material → compare
   exact changes and unresolved requirements → approve/reject → see who acts
   next. If the same actor can execute an already-authorized effect, offer that
   explicit action without forcing them to hunt another menu.
5. **Work offline:** use complete permitted local material → save unique local
   work → exchange when a route is available → verify control/closure → expose
   relevant differences or unresolved conflicts. GitHub status never replaces
   readiness or freshness evidence.
6. **Create/manage/retire a Team:** use a visible Team-management entry → create,
   inspect, change or retire the identified Team. GitHub remains recommended
   and P2P-only remains visible during creation. Initial governance, memberships,
   first environment and actual task readiness remain distinct outcomes.
7. **Handoff or change consumer:** prepare a bounded account of relevant work,
   current decisions, open questions and exact premises → verify the recipient's
   own access/reader route → deliver required bodies or a usable approved route.
   A parent receipt, file locator or old hash alone does not establish delivery.

Management destinations retain direct discoverable entries. Source editors,
ontology/questions/lens review, workstreams, derivatives, search, bulk transfer,
grants, policies, ownership, device custody, recovery, retention and full Team
CRUD map to those entries and preserve the previous detailed forms. The
consolidated requirement board supplies their traceability; reduced top-level
navigation must not remove their subjects, actions, failures or return paths.

Team creation uses a reviewable setup sheet or an adaptive sequence. Required
responsibility and connection choices stay available at creation. Ask for an
offline planning input when relevant; distinguish that plan from an actual
source authorization. GitHub selection alone does not connect/upload, and a
pending nominee is not an independent member. Founding cancellation and normal
governed closure remain different operations.

## 8. Validation that can choose between the alternatives

Use the same sanitized source material, permissions, tasks and failure facts
across candidates. Record first exposure separately for novices assigned to
different initial candidates; do not describe a person's second prototype as
an untrained first-use result. For subsequent within-person comparisons,
counterbalance presentation order and use equivalent tasks. Learning the Team/
environment/approval concepts still carries over and must be reported, even
when the task's surface details differ. Include likely
ordinary workers, nondeveloper domain workers, source maintainers and Team
operators, including those with intermittent/offline constraints. Role labels
are recruitment hypotheses, not observed participant demographics.

Give goals, not button instructions:

| Task | Observable result |
| --- | --- |
| Continue a colleague's work without its prior chat | Correct Team/environment; current choice and open issue identified; permitted next action found |
| Return after a relevant correction | Recognizes what changed and whether the current task switched; no false current-state answer |
| Propose a domain correction | Finds source owner and proper change action; does not mistake proposal for Team adoption |
| Review a change as an approver without publication rights | Understands approval result and who still acts; does not report rollout complete |
| Work without GitHub using valid local material | Can proceed within the shown limits and identify unshared work |
| Encounter missing required evidence | Finds the permitted recovery/clarification route; does not act as if the evidence exists |
| Change Team or retire only a local copy | Predicts affected scope; does not delete/close the wrong Team or move private content |
| Create/join a Team and reach useful first work, with GitHub skipped | Preserves the same Team ID, actual membership/authority state and source references through creation/joining → first environment composition/selection → required review/publication/adoption → qualified delivery to its consumer; no hidden pre-created environment or fixture switch fills the gap |

Record unaided completion, critical authority/scope misconceptions, wrong first
actions, recovery paths, assistance, explanation accuracy and time-to-first-useful
result. Click counts are a diagnostic, not the outcome. Measure delivered
context cost only after required meaning is preserved. Small qualitative rounds
identify problems; do not infer population effect sizes from them.

The first-work probe has two evidence levels: the continuous prototype must
preserve its identities and state through the whole route; the implemented
product must additionally prove the actual provider and recipient effects.
Success at the first level is not real host delivery. The comparison artifact
includes a fresh-Team fixture for this route, starting with zero environments
and an empty Team decision scope rather than borrowing a prepared Team's data.

A critical misconception such as wrong-Team use, confusing approval with rollout,
or treating a missing condition as satisfied blocks adoption of that interaction
until repaired. A cannot be selected merely because users like its appearance;
it must preserve expert findability and all required safeguards. If B supports
users' actual entry model better, make it primary. Retain both entry paths when
they serve different observed contexts without duplicating authority or state.

No participants are recruited or contacted by this review. Human validation is
pending. Scripted prototype checks establish only local fixture transitions,
accessibility basics and layout behavior, not intuitive understanding.

## 9. Explicit exclusions and implementation status

- Remove the assumption of seven fixed menus and a fixed number of setup pages;
  revisit physical layout after task/mental-model evidence.
- Do not create a general task tracker, autonomous chat-only interface, universal
  editor, or extra source store to realize the work-context entry.
- Do not remove any user-required source, governance, offline or Team CRUD
  capability. Less frequent controls are placed at their relevant task/subject.
- No mining, automatic quorum finalization, mandatory GitHub or whole-history
  prompt delivery is introduced by simplifying the human interface.
- Do not choose fonts, density, animation, navigation orientation or product
  branding as proxies for this review's success. Those are lower-impact choices
  after the interaction model is supported.

The current turn produces the consolidated board, this review, comparison
prototype and inspection evidence. Production adapters, actual approvals,
P2P/GitHub state and real host delivery are not implemented by those artifacts.

## Research basis

Starting from users' intended outcomes and keeping non-user suggestions as
research assumptions follows [GOV.UK user-needs guidance](https://www.gov.uk/service-manual/user-research/start-by-learning-user-needs).
The mapping above is this product's hypothesis, not a finding from that source.

Contextual status, recognizable actions, error prevention and reduced recall
burden are supported by [Nielsen's usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/).
Those heuristics do not prescribe seven destinations or prove that fewer
screens are always better. Familiar controls can be reused after the task is
understood; zero-base reasoning does not require unfamiliar interaction.

Secondary controls can be revealed where needed, as described in
[Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/).
This review explicitly keeps material conditions and action consequences visible.

Believable goal-based tasks without navigation hints and observation of actual
or likely users follow [GOV.UK moderated usability testing guidance](https://www.gov.uk/service-manual/user-research/using-moderated-usability-testing).
Existing unrelated FDE design-method research is useful method context, not
evidence about Studio users or a substitute for this validation.
