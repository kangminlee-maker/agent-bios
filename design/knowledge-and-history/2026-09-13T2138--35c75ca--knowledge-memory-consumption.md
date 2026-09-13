---
created_at: 2026-09-13T21:38:50+09:00
head: 35c75ca
kind: design
status: proposed
extends: 2026-09-13T1857--35c75ca--environment-storage-design.md
scope_amendment: 2026-09-13T2027--35c75ca--team-as-environment-unit.md
---

# Efficient consumption of knowledge and decision memory

## Decision

Use **compact orientation, task-specific bodies, and expandable evidence**. These are reading depths over the same owned material, not new stores. Instructions keep their existing consumption surfaces. Domain knowledge and Decision memory gain distinct readers because domain applicability and decision-state reduction require different semantics.

The objective is enough applicable information for a worker to continue the team's task with bounded context cost. Minimizing returned text alone is not success. A locator without the needed body, or a short answer without its exceptions, can be cheaper and wrong.

This is a proposed contract, not a description of currently callable knowledge/memory APIs. `SURFACES.md` continues to catalog implemented routes. The parallel Instructions migration owns identifier and CLI changes.

## 1. Shared reading pattern, different content

| Moment | Instructions, existing model | Domain knowledge, proposed | Decision memory, proposed |
| --- | --- | --- | --- |
| Select/start an environment | Selected compact always rules and procedure locators | Domain scope/purpose, a compact topic/question map, and required readiness qualifications | Team/work scope and a route to discover relevant workstreams; no complete team history |
| Begin or resume a relevant task | Follow an applicable guide/procedure | A bounded support body: needed concepts, applicable rules, conditions, and source references | A bounded current-state body: recorded choices, unresolved issues/conflicts, and meaningful implementation/reassessment state |
| Check, explain, or reconsider | Read the owning procedure | Expand the exact rule/table, definitions, exceptions, or original evidence | Read recorded reasons/alternatives, replacements/corrections, outcomes, and exact premises |
| Delegate or restore lost context | Deliver the selected child/resume projection | Re-deliver the necessary support body and usable locators under the same edition | Re-deliver the necessary state body and usable locators under an identified frontier |

The bootstrap gives the worker a way to recognize and locate information. It does not certify that the worker knows the content. The first relevant task needs actual bodies. Environment authors may designate a small essential orientation excerpt where recognizing a domain situation requires knowing that excerpt in advance. That excerpt is still scoped reference material with a source, not a new global behavioral rule.

The procedure explaining **when to call the readers** belongs in selected Instructions or the explicitly activated environment's consumption procedure. The **facts and history they return** travel through reference/tool context. A past sentence such as “always use X” does not become a developer/system instruction because it was retrieved.

## 2. Domain knowledge: get the support for this judgment

The knowledge reader offers three views:

| View | Returned body | When to use it |
| --- | --- | --- |
| Map | Domain purpose/scope, topics or competency questions, notable known limits, exact expansion locators | Finding what the selected domain can help answer; changing subject |
| Support | The smallest coherent material needed for the declared question: relevant definitions, relationships, scoped rule/table, essential conditions/exceptions, and evidence references | Making the current domain judgment |
| Evidence | Exact versioned passages, containing sections/tables, source excerpts, or related definitions | A material assumption is uncertain, disputed, changed, insufficiently supported, or about to be revised |

Start with documents, sections, and tables. Split only when separate citation, applicability, or revision is needed. A useful support unit must preserve its declared context: a table row may require its headers, units, applicable period, and exception note. A bare matching number is not a usable answer.

Known required companions travel with the support body or are explicitly marked missing. If the source does not define a safe smaller unit, return the containing section/table before attempting arbitrary chunking. Authoring determines those declared companion relationships; code can enforce their inclusion, not discover every unstated semantic dependency.

The request names the task subject and, when relevant, the target period, jurisdiction/entity conditions, and intended use. The operation provides the approved environment and knowledge editions. Missing conditions that change the answer produce a scoped unknown or clarification need, not an assumed default. A goal, a definition, a fact claim, and a validation question retain their different meanings in the returned body.

Stable principles and changing facts use the same route. Their freshness obligations differ. Check a source when the domain/task requires current evidence, a known update is material, or validity cannot be established from the selected edition. A changed source is a candidate update; it does not silently replace an environment pin. Research may inspect authorized new evidence while marking it outside the adopted edition. Using it as a changed team premise follows the environment's adoption policy, including any already-authorized update process; no new blanket human-confirmation step is introduced.

Onto's domain scope and competency questions can seed maps and lookup routes. The existing eight documents remain canonical items or generated views with one owner each. Do not run nine lenses for every read. Onto review is appropriate when authoring/revising a package or investigating a material semantic concern; its findings are evidence, not automatic acceptance or freshness certification.

## 3. Decision memory: current state first, recorded why on demand

The memory reader offers three views:

| View | Returned body | When to use it |
| --- | --- | --- |
| State | Relevant recorded choices, unresolved questions/conflicts, current implementation/reassessment qualifications, and pointers to reasons | First use, resuming work, taking over from another worker, or changing work scope |
| Why/history | A selected decision's recorded context, alternatives, rationale, correction/replacement chain, exact premises, and meaningful outcomes | Explaining a choice, considering reversal, comparing alternatives, or investigating a failure |
| Evidence | Exact decision/event records or bounded cited source passages | Checking a disputed interpretation or substantiating a consequential change |

A successor must be able to discover state from the selected team's authorized work scope without knowing a predecessor's session or record IDs. When the workstream is not yet identified, provide a bounded permitted directory/map and identify the scope gap. Do not substitute an empty state result or the worker's personal history. Task matching may propose a scope; it never grants access.

At operation preparation, resolve a named required-subject set from the environment's declared obligations, explicit task/reference requests, and the selected work scope's state query. Keep its origin and coverage visible. Union these required identities with optional scoped search candidates before any ranking or candidate limit. A search shortlist must not define away a required old decision. If a required query cannot be resolved under the recipient's access, report that requirement as unresolved without exposing restricted identities.

The state body reports what has actually been recorded. Adoption does not prove implementation; implementation does not prove verification. Missing rationale remains missing, and later explanations are identified as later interpretations. An accepted decision is evidence of a scoped team choice; memory retrieval alone does not raise its instruction priority or grant execution permission.

Historical explanation expands the decision's exact premises and recorded context. Newer corrections may accompany them as a present assessment, but do not rewrite what was available then. Inspecting an older premise does not require adopting that old knowledge edition as the team's current environment.

### State must be established before ranking and clipping

1. Resolve the authorized sources, frontier(s), required subjects, and additional candidate decision subjects for the selected work scope.
2. Follow the state-relevant events targeting those decisions and their lifecycle assertions, including corrections recorded under other workstreams.
3. Reduce the qualified current state at that frontier.
4. Rank subjects/passages for the requested task/view.
5. Fit the result into the output budget and expose omissions/continuation.

Indexes and cached state projections can implement this without replaying every record on every request. However, a search result for a decision cannot be presented as currently accepted before its state-changing closure is considered. Workstream or access filtering must not hide a relevant withdrawal and produce a falsely current result. Restricted event text can remain private; the provider returns an authorized state result or states that current state cannot be established.

Recency helps find updates but is not authority or relevance. An old, still-applicable decision can matter more than many recent unrelated messages. Combining independent records does not merge conflicting choices. No retrieval score resolves a conflict.

## 4. A small read contract

Use one reader per role with the views above. The common envelope is deliberately small; these are conceptual fields, not finalized public command names:

```text
request
  selected operation/environment scope (service-resolved)
  required subjects/queries from environment and task (resolved before ranking)
  role + view
  task subject/question, or an exact reference
  output budget
  optional pinned continuation or explicitly retained packet

response
  usable body
  scope and edition/frontier identity
  material qualifications and required gaps
  exact source/expansion references
  bounded omissions and continuation/end indication
```

Detailed provenance and hashes can remain in the stored receipt/structured result. The model-facing body needs readable source aliases, the relevant scope/time, current-state qualifications, and a way to expand. Avoid repeating complete manifests or both a full JSON dump and an equivalent prose dump in the context window.

The service resolves access scope before searching or exposing candidate metadata. A caller-supplied team name cannot widen it. Cursors bind to the role/view, question/selector, edition/frontier, and access context. Continuing a page never follows a newer head silently; a refresh is another read. If authorization changes, retaining a cursor does not preserve access.

Reaching the end of a page sequence means the selected resource/result was delivered. Satisfying the declared required set means its named obligations were covered. Neither proves that retrieval found every semantically relevant fact or that a model read and relied on the text. Keep those claims separate.

Runtime can enforce access, fixed references/cursors, output bounds, declared closure, and refusal to report complete context. Task relevance, unstated semantic dependencies, and sufficient evidence for a judgment remain author/model review responsibilities. The selected reading procedure guides the worker; reference wrappers alone cannot compel model behavior or control arbitrary host tools.

## 5. Budget policy

The caller/host supplies a bounded output budget appropriate to the operation. No universal token count is adopted before measurement. The transport cap includes metadata and continuation fields; its deterministic byte bound may be separate from a host's token estimate.

An output cap is not a bound on retrieval work. Providers use indexed/cached projections and a finite processing budget. If the required state or companion closure cannot be established within that budget, report incomplete context rather than perform an unbounded traversal or certify an arbitrary partial result. The initial contract does not require replaying the entire team's history on each read.

Prioritize in this order:

1. Scope/edition identity and material limitations needed to interpret the answer.
2. Declared required support and state qualifications for the selected task subjects.
3. The most relevant additional bodies.
4. Optional rationale, examples, and deeper evidence through expansion locators.

Do not clip away a returned rule's necessary applicability/exception or a decision's unresolved/withdrawn/corrected status to make the body fit. If the required set cannot fit, return a bounded incomplete result and a usable continuation or narrower-scope path. The affected dependent judgment waits for sufficient context; unrelated work can continue.

Distinguish known output truncation from uncertain semantic coverage. “More results exist” and “the reader cannot establish completeness” are different qualifications. Empty, denied, unavailable, unsupported, unresolved, and truncated results must remain distinguishable even if the eventual wire format groups some under shared status categories.

Stop expansion when the declared question has adequate support and required unknowns are resolved or honestly carried into the answer. Do not traverse every linked document merely because a link exists. A relevance stopping judgment is recorded as such, not disguised as a completeness proof.

## 6. When to read again

| Trigger | Consumption behavior |
| --- | --- |
| First relevant operation | Read a knowledge map/support body and scoped memory state as needed; locators alone do not establish readiness |
| Task subject or workstream changes | Resolve the new authorized scope and its required bodies |
| A premise is challenged or a decision may change | Expand exact knowledge evidence or recorded why/history |
| A material update becomes known | Establish a new operation boundary before the affected decision/action; reconcile through the environment's update policy |
| Resume current work | Keep the old receipt for attribution; resolve a permitted current frontier and rebuild/re-deliver the needed state |
| Context compaction or uncertain retained context | Rehydrate actual support/state bodies; unchanged hashes do not mean text remains in the model's context |
| Delegate to a subagent | Deliver its bounded task body, scope, fixed edition/frontier, and usable evidence locators; verify the child's available reader route |
| Combine delegated results | Preserve each result's exact premises/frontier; reconcile material differences before combining assumptions |
| Team/context changes | Recheck authority and compatibility; use a suitable isolated/fresh context when required |

The routing procedure owns semantic triggers such as “this question depends on domain rules.” Deterministic host events can signal resume or context changes where supported, but broad keyword hooks do not establish domain applicability. On hosts without a reliable compaction/child signal, explicit preparation and body re-delivery remain available.

If a child cannot call the reader, provide its required bounded source body directly or declare that the subtask lacks necessary context. Parent delivery receives no credit as child delivery. A child can request expansion under its actual allowed scope; inheritance never grants new permissions.

## 7. Reuse without pretending the model remembers

Cache immutable source bytes by exact reference, subject to access and retention. Cache source-derived knowledge text by source editions, question/conditions, and renderer version. Cache memory state additionally by frontier, selector, and reducer version. Namespace/access distinctions must survive both storage and reuse.

Before returning cached support, re-evaluate current applicability, freshness, and readiness qualifications against the operation's target conditions, known updates/disputes, and source-check evidence. An unchanged K1 may acquire a material warning when a K2 correction becomes known but is not yet adopted. Reuse source-derived text where valid; do not reuse the earlier “current/adequate” judgment merely because source hashes match. A qualification change is not an unchanged result.

Caching can avoid repeated fetches, reduction, or generation. It cannot prove that a body is still in the consumer's context. A compact unchanged response is allowed only when the current caller explicitly identifies the matching body and qualifications as retained for its present context. A locator, cache entry, delivery receipt, or inherited packet ID alone does not establish this. First use, child preparation, and recovery after compaction or uncertainty return the required bodies even when source hashes match. This is a caller retention declaration, not a claim of host introspection or proven model attention.

Incremental delta delivery remains optional initially. If implemented later, it requires an identified retained baseline and includes withdrawals, corrections, removals, and changed qualifications. Without that baseline, rebuild the scoped body. A transport cursor alone is not a valid memory-state baseline.

A generated summary is a derived view with sources and generation metadata. It is not accepted domain knowledge or a decision record merely because it was cached. Publishing a reusable lesson or changing a team choice uses the existing explicit adoption/capture contracts.

## 8. Existing machinery to reuse carefully

- The existing Instructions compiler already separates compact selected rules from routed guides and requested procedure descriptions: [catalog router](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_catalog.py:684), [snapshot assembly](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_catalog.py:856).
- Current management search matches item text/metadata and can return whole item structures: [search](/Users/kangmin/Documents/agent-bios-personal/compose/instructions.py:109). It is not a semantic knowledge-support or current-memory contract.
- The working-tree Understand reader has bounded UTF-8 pages, exact resource checks, and explicit end markers: [paging helper](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_understand.py:127). Those transport principles are reusable; the tutor's records and workflow do not become the memory subsystem.
- Current surfaces distinguish storage, discovery, explicit app delivery, and native pinning. Keep those claims and role boundaries. Do not add planned K/M routes to the implemented catalog until their adapters exist.

These observations refer to the inspected working tree at this record's date. The canonical owner paths were verified after integrating the parallel Instructions rename; the proposed K/M consumption semantics remain separate from that implementation.

## 9. Acceptance and deliberate exclusions

The companion scenario review specifies negative cases. Compare the proposed approach with full-source delivery and locator-only delivery over the same task/evidence set. Measure answer/support correctness, false current-state claims, justified unknowns, source expansion count, delivered bytes/tokens, and latency/capture cost. Optimize cost only after preserving the required information and qualifications. No performance improvement is claimed by this design alone.

Initially omit a new vector/graph database, a learned relevance model, automatic causal extraction, per-item expiry schedules, full transcript ingestion, mandatory nine-lens review on reads, and incremental delta streams. Use existing authored scope/question metadata, simple scoped search, explicit links, and coherent sections/tables first. Revisit a mechanism when observed retrieval failures or costs show that it is needed.

The first vertical slice should let a replacement team member identify an existing decision, obtain the applicable domain support, inspect one recorded reason, and continue under a bounded packet. Repeat with a cross-workstream correction, small budget, unavailable evidence, and a child/context reset. That proves useful consumption rather than merely another storage/search interface.
