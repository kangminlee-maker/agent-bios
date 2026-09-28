---
created_at: 2026-09-14T14:55:31+09:00
head: 35c75ca
kind: design
status: recommended-design-not-implemented
refines: 2026-09-14T1300--35c75ca--consistency-clarification-proposal.md
review: 2026-09-14T1300--35c75ca--whole-design-consistency-review.md
---

# Minimal integrated consistency repair

## Recommendation and purpose

Repair the existing preparation, reader, authorization and lifecycle contracts.
Preserve Team environment selection, sharing, continuity and source authority.
The Instructions / Domain knowledge / Decision memory distinction, exact
environment editions, local replicas and optional recommended GitHub transport
remain the design basis.

The [four proposed clarifications](2026-09-14T1300--35c75ca--consistency-clarification-proposal.md)
already contain sufficient detail for the identified boundaries. This record
integrates them into a small implementation and UI plan. It does not create a
new service, mandatory setup wizard or universal policy/workflow engine. It is
a recommendation, not evidence of deployed behavior or user adoption of a new
Team policy. The [audit findings](2026-09-14T1300--35c75ca--whole-design-consistency-review.md)
remain open until successor contracts and scenario evidence meet their closure conditions.

## 1. Separate three questions in the existing preparation

| Question | Meaning and evidence | What it does not establish |
| --- | --- | --- |
| What basis did we select? | Exact adopted environment, permitted candidate, or bounded ad hoc sources; adoption evidence where applicable | Adoption merely because sources are useful or present |
| What support is established for this work? | Required coherent bodies, qualified decision state, editions/frontiers, verification and material gaps | Globally latest knowledge, complete unstated semantics, or actual model comprehension |
| Which action can this actor perform now? | Requested action/scope, applicable grants, source and Team constraints, required approvals and permitted offline evidence | Blanket authority from a role title, a ready preparation or a previous approval |

These are independent dimensions of existing objects, not one new global
`ready` state. An adopted environment can lack a required local body. A complete
research packet can be unadopted. A qualified reviewer can lack contribution or
publication rights. Show the pertinent combination rather than inventing one
status for every combination.

Keep exact work/scope, selected basis, recipient, references and evidence bound
to the preparation. Add a supported existing-work reference for continuation
where applicable. Use the existing role-specific readers for actual bodies;
Instructions still direct consumption, knowledge supports the current judgment,
and memory returns qualified state before optional history expansion.

UI clients consume the same scoped evaluation meanings. This does not imply a
central always-online server: evaluation can run against locally verifiable
evidence where the governing offline policy permits it. Replication, authority,
adoption, local preparation and actual host delivery retain separate meanings.

At execution, evaluate the current applicable evidence again under the same
rules. A stored preview is not an execution grant. Relevant changes invalidate
affected preparation/approval conditions while preserving historical receipts.
Keep denied, missing, unknown, unsupported and conflicting outcomes distinct,
with a permitted remedy where one exists. Online reachability alone neither
permits nor forbids the operation.

## 2. Four narrow contract repairs

| Finding / existing owner | Recommended rule | Small default and extension boundary |
| --- | --- | --- |
| G01 / grants and membership | Effective privilege expansion is governed even if it occurs by adding a group member. | Default to approved members plus applicable membership evidence. Dynamic eligibility requires explicit bounded delegation to the named membership authority. Known removal overrides an old approved list. |
| G02 / preparation and knowledge reader | Accept an explicit unadopted research/drafting basis without inventing adoption. | No Team-standard claim or implied publication/adoption permission. Enforce required sources and Team/source conditions in every mode. |
| G03 / memory reader and offline transfer | Accept verified event closure or an authorized, verifiable qualified state artifact. | Reuse the existing provider result and transfer envelope. Bind authority, permitted scope/audience, frontier, supported interpretation, body/qualifications and validity/control conditions. An arbitrary summary or self-declared signing key is insufficient. |
| G04 / Team lifecycle and recipient preparation | Distinguish the logical work being continued from the host session receiving it. | Use existing work/operation evidence; require applicable continuation policy, rights and scope. Do not introduce mandatory task-tracker registration or permit broader work from a bare continuation label. |

For G03, a permitted result such as "this decision was withdrawn" can travel
without confidential reasons. That result grants no additional rights, does not
claim hidden event bodies were delivered and cannot certify global latestness.
Without sufficient supported evidence, state remains unresolved; do not revive
the older visible decision. Raw evidence remains unavailable where restricted.

For G04, an archived Team may permit a replacement device/recipient for the same
bounded work. Permanent closure still prohibits resumed Team work. Authorized
retained-evidence reading, recovery, preservation and cleanup remain separate
operations under surviving stewardship and source/retention rights; they do not
reactivate the Team. Retained membership alone grants none of these actions.

## 3. UI changes within the current navigation

| Surface | Required repair |
| --- | --- |
| W01 preparation | Show selected basis, action-specific readiness and the relevant gaps. Permit explicit unadopted discovery when authorized; do not manufacture prior project decisions. |
| Material management / review | Derive both button eligibility and submission checks from the actor's applicable capability set. Review-only users cannot save a source proposal unless a separate contribution grant is declared. |
| W08 recovery | Carry the incoming work/preparation and missing-object set. Receiving and verifying the required bodies can change the dependent readiness; merely navigating cannot. Label unrelated permitted investigation separately. |
| W09 delivery / continuation | Carry the same preparation and actual recipient evidence. Identify existing-work continuation separately from a new host session. Prepared, delivered and observed-use claims remain distinct. |
| Team lifecycle | Separate restoration of operation from retained-evidence recovery. Closed-Team evidence actions retain the closure marker and their own eligibility checks. |

A compact W01 example for an authorized first investigation:

```text
사용 기준       선택한 자료 · 팀 기준으로는 아직 미채택
현재 작업       조사·초안 작성 준비됨
팀 기준 변경    별도 채택 권한·절차 필요

[조사 시작]   [자료와 근거 보기]
```

This example is scoped to its declared operation, not a universal user role or
replacement for specific missing conditions. For a missing required body, the
same area says which dependency is unavailable and offers the permitted recovery
route. Technical proof details stay behind the evidence view unless necessary
for a user's decision. TUI, GUI and CLI can present the same meanings differently.

## 4. Closure sequence and evidence

1. Integrate these four repairs into a dated successor contract set with an
   explicit precedence/owner map. Reuse existing concepts; do not rely on latest
   timestamp alone to resolve contradictions or expand current runtime claims.
2. Define one small scenario data set for the affected preparation, grants,
   source evidence and Team states. All related prototype routes consume those
   identities and transitions, including direct entry and return navigation.
3. Repair the successor prototypes and exercise the original failing routes,
   plus the material rejected cases below. Record exact artifact identities and
   results before closing any audit finding.
4. Implement the same contracts in the actual non-UI operations and supported
   adapters. UI success is evidence about the prototype, not runtime enforcement.

| Case | Required outcome |
| --- | --- |
| Group manager self-adds into a privileged group | No new powers without approved expansion or existing explicit bounded delegation; removed/expired members cannot rely on old approval. |
| New Team investigates before adopting an environment | Permitted research works with an unadopted label; denied required sources and substantive action limits remain binding. |
| Confidential correction is needed offline | Valid permitted qualified state can be used without hidden text; forged, expired, wrong-scope or unsupported evidence cannot restore the old decision. |
| Archived work changes recipient | Authorized same-work continuation can succeed; unrelated work and scope expansion remain blocked. |
| Reviewer navigates to contribution | Both visible controls and submission reject absent contribution rights. |
| W01 missing body navigates to W08 and returns | The gap persists until actual sufficient verification, then the dependent assessment is recomputed. |
| Closed Team evidence is recovered or cleaned up | Only authorized evidence/retention effects occur; the Team stays closed. |
| Permission changes after an allowed preview | Execution rechecks and refuses stale authority; a retry preserves the exact request identity where reconciliation is needed. |

These cases establish the named repairs, not completeness of all semantics,
retrieval relevance or human usability. Existing valid paths must remain valid.

## 5. Deliberate exclusions and revisit conditions

| Deferred detail | Reason | Revisit when |
| --- | --- | --- |
| A new universal policy/workflow service | Existing scoped evaluators and operation journals already own the relevant decisions. | A concrete cross-provider operation cannot preserve authority/evidence using those contracts. |
| Mandatory task management or a global task graph | A scoped existing-work reference is sufficient for the continuation boundary. | Real host/workstream evidence cannot distinguish permitted continuation reliably. |
| Identity-provider-specific group administration screens | The authorization mode and delegation boundary can be defined independently of vendor UI. | A chosen provider integration needs concrete enrollment, removal and recovery behavior before shipment. |
| New status menus and a full studio redesign | The failures concern meaning and state propagation in existing routes. | Scenario/user evaluation shows those routes cannot communicate the repaired meanings. |
| Final proof serialization, cryptographic suite and universal validity duration | Semantic requirements can be fixed now; provider/source constraints determine concrete formats and offline validity. | Before implementing interoperable state-artifact import/export; these are implementation prerequisites, not optional validation. |

Source permissions, verified control changes, exact scoped references, clear
incomplete results and accountable approval are not excluded. They preserve the
product purpose while the lower-impact representation details remain deferred.
