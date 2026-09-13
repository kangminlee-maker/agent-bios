---
created_at: 2026-09-13T23:28:00+09:00
head: 35c75ca
kind: design
status: proposed-ui-with-interactive-prototype
amends: 2026-09-13T2245--35c75ca--unified-studio-scope.md
depends_on:
  - 2026-09-13T1857--35c75ca--environment-storage-design.md
  - 2026-09-13T2138--35c75ca--knowledge-memory-consumption.md
---

# Studio: detailed interaction design

## Purpose and scope

Studio helps a worker start and continue work within a team's standards and
decision context. The main object is the selected team work environment; its
Instructions, Domain knowledge, and Decision memory are independently owned
sources reached through that environment.

This design specifies the integrated shell, reading screens, composition editor,
publication/adoption flow, and task preparation flow. An interactive Korean
prototype exercises two complete, simulated journeys. It does not add team,
knowledge, or memory providers to the shipped Instructions Studio.

Studio remains a working product label. A desktop application shell is the
interaction proposal, not a decision to replace the existing terminal UI with a
specific web framework or hosting service.

## Primary composition

Use one workspace with a left navigation rail and a shared context header. The
rail has four areas: `업무환경`, `작업 지침`, `업무 지식`, and `결정 기억`.
English semantic names appear as secondary labels where useful. The initial
screen is the environment overview, not a dashboard of document counts.

The header identifies Team and environment. Below them, separate labels show
the team's adopted edition, an owned draft when present, and this worker's
actual task edition. A selected draft or published edition is also named in
the page title. Never infer any of these from an unqualified `latest` badge.

Team and environment selectors change browsing scope, not an active task. A
task from another scope stays visibly identified with its Team. Unpublished
drafts remain attached to their own environment when navigating elsewhere.
Environment and source access are derived from the corresponding authorities;
selecting a Team does not grant editing rights.

Reading uses a list and detail panel. Conditions, exceptions, current choice,
and unresolved state are inline; long evidence and earlier records expand
within that detail panel. Task preparation and composition changes use the
main content area, rather than stacking modal dialogs. Returning to the
environment does not discard a draft; `초안 버리기` is an explicit operation.

At narrow widths the rail becomes wrapping top navigation and the list/detail
layout stacks. Do not hide essential conditions or actions to save width. The
optional owner column in the overview may collapse because each source's
detail retains its owner and permissions.

## Screen contract

| Screen | Content and primary action | State that must remain visible |
| --- | --- | --- |
| Environment overview | Exact static source versions; memory selectors; required/optional material; links to each reader; `작업 준비` | Team adoption; draft; actual task edition; newly published edition awaiting adoption |
| Instructions | Included status, owner, exact version, starting instructions, on-demand procedures and pointers | Source reading does not change environment inclusion; source version differs from environment edition |
| Domain knowledge | Topic/question map, stable principle, applicable current claims, effective interval, scope, conditions, exceptions, evidence and review state | Selected revision remains pinned; a newer available revision is a separate signal; checked date is not a guarantee of current truth |
| Decision memory | Current choice and unresolved issues, then recorded rationale, alternatives, evidence and multi-workstream chronology | Corrections apply to current state; replacement/withdrawal affects choice; missing rationale stays missing; expected and observed outcomes are distinct |
| Task selection | Task/question, role, applicable time, environment edition, permitted memory scope and target context | No delivery yet; changing task/scope invalidates prior preparation |
| Context preview | Actual proposed bodies and references, coherent knowledge support, qualified current memory, required gaps, omitted optional material and continuation | Preview is neither activation nor proof of reading; exact edition and memory frontier accompany the request |
| Readiness | Source access, required bodies, host support, context compatibility and any actionable missing condition | Ready refers to a named request and target; it is not a global property of an environment |
| Use result | Result for the exact reviewed request and actual delivery evidence | A failed or uncertain delivery is not success; model understanding/obedience is not established by a receipt |
| Composition edit | Source references and scope, required/optional declaration, local draft; `변경 내용 검토` | Source content and Team adoption remain unchanged |
| Change review | Before/after exact references and required meaning; owner/permission impact; named publication action | Publication creates an edition, not adoption or task activation |
| Publication/adoption | Newly published edition, currently adopted edition, composition difference; explicit Team adoption target | Existing tasks keep their own editions; subsequent use needs its own readiness and delivery result |

## Detailed authoring interactions

These forms are specified here but deliberately not represented by inert
buttons in the two-path prototype. Connect them when their owning providers
support the operation. Preserve the current Instructions authoring/recovery
capability while integrating it into the shell.

| Operation | Minimum fields and review | Commit effect |
| --- | --- | --- |
| Edit an instruction source | Source owner and base version; title/body; consumption surface and trigger; before/after preview | Create a source revision under its owner's authority. Offer an explicit environment-reference update separately. |
| Create a knowledge revision | Base revision; principle/claim; application scope; effective period where relevant; conditions and exceptions; evidence; review/update requirement | Create a revision; validate required companion meaning and relevant domain questions. Do not automatically move environments using an earlier revision. |
| Create a permitted derivative | Original source/version; new owner; proposed changes; carried provenance | Create a separately owned source if allowed. No implication of editing the original or obtaining its rights. |
| Record a decision | Question/subject; workstream; scope; choice; alternatives closed; recorded reason and evidence; replaces/withdraws reference when applicable | Append a decision event. Required gaps remain explicit, never filled with invented explanations. |
| Correct a record | Target assertion; corrected content; reason and evidence | Append a targeted correction. Preserve original content and provenance; recompute qualified current views. |
| Record an observed outcome | Target decision; observation and when it occurred; evidence | Append an observation; do not silently reinterpret it as a new choice. |

Environment editing and source editing have different titles, actions and
version checks. For example, removing the optional launch checklist from an
environment does not delete that checklist. Removing a memory workstream from a
view is not withdrawal of the decisions recorded there.

The memory default is qualified current state. Workstream filtering is a
reading aid; required correction closure is resolved before reduction. If an
authorized current answer depends on unavailable correction content, disclose
the limitation rather than showing the old assertion as current. Do not reveal
restricted source details merely to explain a gap.

## Request and transition rules

The production client holds view state and request references; provider data is
authoritative. Do not create a second Studio summary engine or state reducer.
The same consumers serve Studio preview and runtime delivery with the same
task, scope, edition, frontier, access qualifications and budget.

| Action | Changes | Must not change implicitly |
| --- | --- | --- |
| Browse Team/environment/source | View selection | Task pin, source ownership, Team adoption, environment composition |
| Edit composition | Owned draft based on a specific revision | Source bodies, published editions, active tasks |
| Publish | Immutable edition and publication receipt | Team adoption, delivery or activation |
| Adopt for Team | Adoption reference after version/authority check | Existing task contexts |
| Preview | Request-bound proposed context | Task activation |
| Check readiness | Qualified result for that request and target | Actual delivery |
| Use in task | Delivery operation and resulting task reference | Other task references, source ownership |

Readiness has no unconditional lifetime. A changed task, time, scope, edition,
frontier/access qualification or incompatible target invalidates the prior
result. Before use, revalidate the request binding and provider conditions.
If adoption changed since preview, disclose it and preserve the reviewed target
only when current policy permits; otherwise request a refreshed preview. Never
silently deliver the new edition under the earlier preview.

Production writes use the previously designed conditional head updates,
request-bound operation identifiers, and durable receipts. On an uncertain
result, show `결과 확인 중` and recover that operation. Avoid an unbound retry
that creates a second publication, adoption, or memory event.

The prototype shows each phase as a button press to make the effects inspectable.
This does not mandate repeated human confirmation for operations already
authorized by policy. A client may execute authorized phases together while
retaining their distinct targets, evidence, and failure states.

For a fresh worker, default to a new task context. Existing-context use is a
separate, capability-dependent route: require isolation only when context is
incompatible or policy requires it. Retaining a prior reference is not a right
to continue using withdrawn access, and Studio cannot erase content already
delivered to an uncontrolled context.

## Consumption presentation

Keep orientation compact and retrieve task-specific support. Admission of
required subjects precedes optional relevance ranking. Present a support unit
with its applicable conditions, exceptions and necessary companions; truncation
cannot convert a conditional claim into an unconditional one.

Current memory includes unresolved state and relevant correction/withdrawal
closure. The preview offers evidence expansion under the same request identity.
Opening evidence should return to the same preview and preserve its source
edition/frontier. A real source-view navigation requires a return reference;
the prototype uses in-place expansion to avoid losing reading position.

The production view discloses omitted optional material and required gaps. If
a response budget cannot include required meaning, show incomplete preparation
and a continuation action, not `ready`. Fetching all pages does not establish
semantic completeness. Cache availability is shown separately from current
access and applicability. New workers, child workers and compacted contexts
receive required bodies again unless retained body and qualifications are
explicitly known in that consuming context.

## Two prototype journeys

All teams, work, source text, dates and records are fictional fixtures. No
authentication, filesystem persistence, provider call, publication, adoption,
permission check, session creation or agent execution occurs. Status changes
exist only in the open prototype and reset with a new scenario or reload.

### A. A worker joins existing work

1. Open Product Development Team's adopted environment, edition 3.
2. Read the payment principle and current retry condition with its exception.
3. Read the current decision; expand why it was chosen, observe a correction
   recorded under the other workstream, and see the unresolved wait interval.
4. Choose the task, preview the instruction body, coherent knowledge and
   decision context at M-42. No task is active yet.
5. Check simulated readiness; no task is active yet.
6. Use in a new virtual task. The result records edition 3 and M-42.

The prototype also permits Customer Support Team and a second environment per
Team. A selection changes the browsing/task-preparation scope without changing
an existing virtual task. Both task examples per Team concern the same subject;
their required support intentionally overlaps. This is not a general-purpose
task parser or retrieval demonstration.

### B. A maintainer changes the shared starting point

1. Start with a virtual task on edition 3 and an owned edition-4 draft.
2. Remove the optional checklist. Required items remain included.
3. Review the one composition difference and publish edition 4.
4. Observe that Team adoption and the existing task are still edition 3. Leave
   the published edition unadopted, or return later to its adoption review.
5. Adopt edition 4 for the Team. The existing task stays on edition 3.
6. Prepare and start a new virtual task on edition 4. Its context omits the
   checklist pointer; the prior task remains identified as edition 3.

The scenario selector belongs to the prototype harness. It is not a production
permission or role-switching control. Rights are fixed fictional assumptions in
this demonstration, not conferred by a dropdown.

## States to implement beyond the happy path

| Condition | Product response |
| --- | --- |
| No environment/source available | Explain the actual scope and provide an authorized creation/import route if supported. |
| Provider unsupported | Show `아직 지원하지 않는 기능`; do not render a falsely empty library or instruct users to repair configuration. |
| Required source unavailable or access expired | Identify the permitted missing condition and supported remedy; withhold a ready claim. |
| Knowledge stale, outside its period, or incompletely qualified | Explain which qualification is missing; require needed refresh/evidence. |
| Required content exceeds budget | Preserve essential meaning, mark incomplete, expose continuation. |
| Concurrent edit or adoption | Preserve the user's draft, reload the authority's current reference, and review the actual conflict. |
| Offline | Evaluate the declared source/environment offline policy; cached content alone does not authorize use. |
| Delivery result unknown | Resolve the existing operation and show uncertainty until evidence establishes its outcome. |
| Incompatible current context | Offer an isolated/new task or other supported remedy; do not claim content was removed from an existing conversation. |

## Deliberate limits and next implementation boundary

- No search ranking UI, administrative dashboard, bulk editor, domain-specific
  form builder, or arbitrary ontology graph editor. They add surface area without
  proving the shared-environment start/continuation contract. Revisit when a real
  reader or authoring workflow needs them.
- No simulated network races, provider outage controls or complete recovery
  dialogs in this prototype. Their responses are specified above; validate them
  against real provider operations when those exist.
- No automatic knowledge freshness claim or live legal/accounting example.
  The fixtures exercise period/condition/evidence placement, not factual advice.
- Source authoring forms, deletion/retention, permissions administration,
  personal overlays, full-text search, child-session inspection and in-place
  session switching are not interactive here. Their existing architecture
  boundaries remain binding, with source-specific forms specified above.
- Final brand, typography tokens, persistence technology and implementation
  framework remain open. Optional prototype design controls compare left/top
  navigation, comfortable/compact spacing, and green/blue accents without
  changing workflow semantics.

Implement the read/preview/readiness path against real providers first, reusing
the existing instruction manager. Add publication/adoption and source authoring
as their authorities become available. A mock result must never be substituted
for a runtime capability check.

## Review and validation

An independent subagent reviewed the screen contracts and the main risks:
browsing versus inclusion, publication versus adoption versus use, source rights,
version/frontier distinction, and corrections versus ordinary document editing.
Its recommendations are reflected in the state table and fixtures.

Validation is performed against the sandboxed rendered prototype, not against
the shipped Studio runtime. The accompanying prototype QA record identifies
completed interactions, viewport checks and the limits of that evidence.

- [Prototype source](2026-09-13T2328--35c75ca--studio-ui-prototype.html)
- [Prototype QA record](2026-09-13T2328--35c75ca--studio-ui-qa.md)

The prototype is an HTML fragment. Use the visualize skill's `scripts/render.py`
to wrap it for standalone inspection; its bare fragment is the conversation
renderer input. The repository copy is the dated design snapshot. The displayed
conversation copy has identical bytes at this record's QA point.
