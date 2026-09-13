---
created_at: 2026-09-13T14:25:57+09:00
head: 9501eff
kind: design
status: research
---

# Before design: instructions, domain knowledge, and decision history

This is a dated research assessment, not an adopted architecture or a new runtime contract. Its purpose is to identify the decisions and evidence needed before expanding corpus. Working names below are provisional; the operated lexicon has not changed.

The user wants three distinct functions: guidance for doing work, knowledge of the work's domain, and memory of how work and decisions developed across concurrent activities. The research recommendation is to separate their meaning, authority, and lifecycle first, then discover how much storage and delivery machinery they can share.

## Evidence boundary

Inspected agent-bios at HEAD `9501eff`, the local onto-mcp checkout at HEAD `caa20c6`, and selected files from the user-owned `accounting-kr` domain package. The onto MCP registry was queried with `onto_list(kind=lenses)` and `onto_list(kind=domains)` against this project. No ontology review or reconstruct run was performed. Local package contents were inspected as source material, not certified as correct domain knowledge. No current tax rate is asserted in this note.

Primary external sources were checked on 2026-09-13. Source-backed observations and this note's recommendations are distinguished below. This is a bounded preparatory review, not an exhaustive literature review or an empirical comparison of implementations.

## What the implementation already establishes

| Observation | Evidence | Consequence for research |
| --- | --- | --- |
| Corpus has instruction kinds (`rule`, `guide`, `skill`, `hook`, `agent`) and separate delivery surfaces. | [catalog](/Users/kangmin/Documents/agent-bios-personal/compose/corpus_catalog.py:33), [store](/Users/kangmin/Documents/agent-bios-personal/compose/corpus_store.py:28) | Adding content requires examining its interpretation as well as its placement. A historical quotation must not acquire instruction authority merely by retrieval. |
| Existing domain labels classify work and selections. | [domain manifest](/Users/kangmin/Documents/agent-bios-personal/compose/domains.json:4) | A work category and a domain knowledge model are different concepts even if they share a label. |
| Stable item identities, selected immutable snapshots, and session pins exist. | [identity](/Users/kangmin/Documents/agent-bios-personal/compose/corpus_catalog.py:8), [snapshot](/Users/kangmin/Documents/agent-bios-personal/compose/corpus_store.py:1466), [resume](/Users/kangmin/Documents/agent-bios-personal/compose/corpus_session.py:635) | Reuse candidates for version attribution; not proof that the same lifecycle fits changing knowledge. |
| Captured learning becomes a rule, defaulting to the always surface. | [learning projection](/Users/kangmin/Documents/agent-bios-personal/compose/corpus_store.py:453) | Appropriate to the current lesson flow, but unsafe as an automatic conversion for every historical event or domain claim. |
| Decision records include alternatives, reasons, reversal conditions, source session, and Git provenance. Their displayed lanes group by session. | [record construction](/Users/kangmin/Documents/agent-bios-personal/decisions/record-decision.py:98), [session grouping](/Users/kangmin/Documents/agent-bios-personal/decisions/record-decision.py:471), [graph](/Users/kangmin/Documents/agent-bios-personal/decisions/record-decision.py:557) | A useful starting point for decision capture; session lanes do not yet represent workstream identity or causal dependencies. |
| The repo ontology owns implementation dependencies and obligations, excluding payload meaning and dated records. | [scope](/Users/kangmin/Documents/agent-bios-personal/ontology/domain_scope.md:9) | Transfer methods for evidence and impact analysis, without treating its instance model as a general business ontology. |
| Prompting sources distinguish structural pins, online drift, and semantic re-derivation. | [source checker](/Users/kangmin/Documents/agent-bios-personal/gates/check-prompting-sources.py:6) | Source change detection and correct knowledge revision are already recognized as separate operations. |

One present-state disagreement affects reuse assumptions: the decision recorder and lexicon describe heavy session distill as shipped, while [package enforcement](/Users/kangmin/Documents/agent-bios-personal/gates/check-package.sh:281) declares `session-distill/` author-side and its [workflow guide](/Users/kangmin/Documents/agent-bios-personal/claude/guides/session-distill-workflow.md:72) requires a checkout. The expansion should not rely on the older shipping explanation. This note records the discrepancy without resolving it.

## Three roles, with independent classification axes

| Provisional role | Question it answers | Main acceptance question |
| --- | --- | --- |
| Work instructions | How should this agent perform this work? | Is this an authorized, applicable behavioral rule or procedure? |
| Domain knowledge | What concepts, relationships, constraints, values, and claims apply here? | What supports this content, under which scope, and with what status? |
| Decision history | What happened, what was considered, what was chosen, and what followed? | What is actually recorded, by whom, and how is it connected to evidence? |

These are semantic roles, not a conclusion that three databases or three copies of every document are required. One document may contain all three. A domain principle can justify a work instruction; a decision can adopt an organizational principle; an event can support a later claim. The links matter, and the original roles must remain distinguishable.

For this investigation, use **history** for the retained record and **memory** for the capability to select and use prior material in subsequent work. This is a proposed working distinction, not a universal definition. The broader memory literature also separates functions from representation and evolution; its terminology is not a ready-made product taxonomy. [Hu et al., Memory in the Age of AI Agents, v2](https://arxiv.org/abs/2512.13564v2)

Keep at least these axes independent during sampling: semantic role; scope and owner; source and authority; temporal interpretation; acceptance state; expected revision behavior; delivery method. For example, a rarely changed organizational aspiration is neither an observed fact nor a universal law.

## Domain knowledge: enduring structure and changing claims

The user's durable/variable distinction is useful, but stability should describe expected revision behavior rather than certify an assertion as eternally true. Even a structural model can change when the domain boundary changes. Goals can be deliberately replaced. The reason and authority for revision differ from those for correcting a measurement or updating an external rule.

Sample existing material into these categories before designing a schema:

- Goals and adopted principles: desired outcomes, priorities, and commitments.
- Definitions and structural models: what entities and relationships mean.
- Scoped rules and factual claims: externally grounded requirements, parameters, observations, and interpretations.
- Validation criteria: questions, constraints, cases, and evidence requirements used to judge the other content.

OMG's Business Motivation Model distinguishes desired ends from means and directives; SBVR distinguishes definitional rules from behavioral rules that may be violated. These support separating a desired or required state from a claim that it actually holds. They do not require adopting either complete standard. [BMM 1.3](https://www.omg.org/spec/BMM/1.3/PDF), [SBVR 1.5](https://www.omg.org/spec/SBVR/1.5/PDF)

### The time questions that a latest document cannot answer

For an externally changing rule, distinguish its applicability in the domain from its presence in the knowledge store. Temporal database research calls these valid time and transaction time. [Özsoyoğlu and Snodgrass, 1995](https://www2.cs.arizona.edu/~rts/pubs/TKDEAug95.pdf)

The pilot must answer both:

1. Given what is known now, which rule applied to the target period?
2. At the time of the earlier decision, which version was available in our system?

Publication, effective start, applicability to a business period, discovery, and acceptance are not interchangeable timestamps. Date intervals alone may be insufficient: jurisdiction, entity type, exceptions, and transition conditions can select different rules for the same calendar date. Goals, observations, and questions also need different temporal semantics rather than a mandatory generic validity interval.

A candidate evidence unit is a claim with a stable identity, revision, scope, source version and passage, temporal meaning, and acceptance status. Compare this against lighter document annotations. A confidence score cannot replace distinctions such as unsupported, disputed, scope unresolved, review overdue, or formerly applicable. Old does not necessarily mean false; newly retrieved does not necessarily mean authoritative.

### What onto can contribute

The MCP registry returned nine lenses: logic, structure, dependency, semantics, pragmatics, evolution, coverage, conciseness, and axiology. The first eight have explicit primary domain document mappings in both [the contract](/Users/kangmin/Documents/onto-mcp/.onto/processes/review/lens-prompt-contract.md:126) and [the implementation](/Users/kangmin/Documents/onto-mcp/src/core-runtime/cli/materialize-review-prompt-packets.ts:382).

| Lens | Primary document | Research use |
| --- | --- | --- |
| logic | `logic_rules.md` | Contradictions and incompatible constraints |
| structure | `structure_spec.md` | Missing entities, paths, and relationships |
| dependency | `dependency_rules.md` | Consequences of changing a premise or rule |
| semantics | `concepts.md` | Identity, terminology, and scope ambiguity |
| pragmatics | `competency_qs.md` | Whether useful questions can be answered |
| evolution | `extension_cases.md` | Revision, expansion, and correction cases |
| coverage | `domain_scope.md` | Missing relevant subdomains |
| conciseness | `conciseness_rules.md` | Unnecessary distinctions and duplication |
| axiology | No dedicated primary file; purpose/principles and selected context | Whether the knowledge serves the intended purpose and values |

The eight documents are an authoring and review organization; the nine lenses are evaluation perspectives. Their verified mapping is useful, but neither is a complete schema for every knowledge assertion. Current contracts also keep domain context and alignment context distinct. [context contract](/Users/kangmin/Documents/onto-mcp/.onto/processes/review/review-context-manifest-contract.md:155)

The inspected accounting package already combines fundamental structure and period-specific assertions. Its [scope](/Users/kangmin/.onto/domains/accounting-kr/domain_scope.md:37) includes dated tax parameters, while [extension cases](/Users/kangmin/.onto/domains/accounting-kr/extension_cases.md:89) explicitly discuss amendment impacts across documents. This is a useful test corpus. A file-level `last_updated` cannot alone establish that each assertion and dependent question is current. These observations do not certify or reject the package's tax claims.

Four different checks need separate evidence:

- Logical consistency: can the modeled assertions coexist?
- Required information: are the necessary scope, sources, and relationships actually present?
- External grounding: do authoritative sources support the interpretation for this case?
- Decision usefulness: can a relevant question be answered correctly, including when to withhold an answer?

OWL's open-world reasoning and SHACL's validation against declared shapes illustrate the first two distinctions. Neither establishes that an external fact is true. [OWL 2 Primer](https://www.w3.org/TR/owl2-primer/), [SHACL](https://www.w3.org/TR/shacl/)

Competency questions can define required capability even before a complete ontology exists. Each pilot question should name the decision it changes, scope, required evidence, expected answer form, and a counterexample. Research on CQ translation shows that natural-language questions do not map one-to-one onto formal queries. A question list alone therefore does not establish executable validation. [Wiśniewski et al., 2018](https://arxiv.org/abs/1811.09529)

Freshness and source authority should initially be concerns applied through the existing lenses and questions, not an assumed tenth lens. Onto explicitly separates domain concerns from authority to alter the lens registry. [lens governance](/Users/kangmin/Documents/onto-mcp/.onto/processes/review/lens-registry.md:74)

## History: preserve decisions and the relationships around them

ADR supplies a compact adopted-decision record: context, choice, status, and consequences. It preserves earlier decisions when replaced. IBIS supplies a complementary representation of unresolved issues, alternatives, and supporting or opposing arguments. Together they cover more of the user's need than a commit log alone. [Nygard, 2011](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions), [Conklin, 2008](https://www.cognexus.org/Papers/Growing_a_Global_Issue_Base.pdf)

Investigate these related records without prescribing a single linear workflow:

- Observed events and artifacts: requests, trials, errors, results, commits, releases.
- Questions and exploration: assumptions, alternatives, evidence, unresolved disagreement.
- Decisions and commitments: who selected what, under which scope, and why.
- Follow-through: implementation, verification, outcomes, reversal, or reopening.
- Reusable learning: a later generalization with links to the original experience.

Proposed, accepted, implemented, and verified describe different things. Expected consequences and observed outcomes are different evidence. A later summary of why a decision happened must distinguish explicit contemporaneous rationale from a later inference. If no reason is recorded, the system should be able to say so. The target is an auditable account of stated rationale and evidence, not a reconstruction of unrecorded internal reasoning.

### Concurrent work needs more than lanes

A workstream can cross sessions, branches, dates, and repositories. One session can contribute to several workstreams; one decision can constrain several workstreams. The pilot must include splitting, joining, shared premises, and reopening, not merely two parallel timeline columns.

Relations should distinguish chronology, evidence use, dependency, contradiction, replacement, and shared subject. Time order alone is not causal evidence. Lamport's partial-order treatment of distributed events is a useful analogy, not a directly applicable human workflow specification. [Lamport, 1978](https://www.microsoft.com/en-us/research/publication/time-clocks-ordering-events-distributed-system/)

Do not demand that every relation form a DAG. Event causality should not loop; an argument or issue may be revisited repeatedly. W3C PROV offers entity/activity/agent and usage/derivation/revision relations for the evidence layer, without deciding whether an argument is sound or a choice is authorized. [PROV-O](https://www.w3.org/TR/prov-o/)

Readable narratives and structured links can coexist. A current-state view should expose unresolved choices and its source records. It is only a deterministic projection when its interpretation rules are defined; a synthesized judgment may itself need provenance.

## Where the three roles meet

The most valuable cross-boundary question is: **which explicit premises and source versions supported a decision, and what needs reconsideration when one changes?**

A candidate chain is decision → cited claim revision → source revision, with scope and acceptance status retained. This must distinguish material merely delivered to an agent from material explicitly cited as a premise. A delivery receipt can establish supplied bytes; it cannot prove cognitive reliance, completeness of context, or identical future model output.

An event may support a lesson, a domain claim, or a new procedure. Promotion should preserve the source and make any widened scope or adopted authority visible. A one-off workaround does not become universal guidance merely because it was remembered. Likewise, a source update should flag affected current decisions or derived artifacts without rewriting what was recorded historically.

Three delivery hypotheses deserve comparison, rather than an early choice:

| Hypothesis | Benefit | Failure case to test |
| --- | --- | --- |
| Pin all selected context for a task | Coherent edition and easier content reconstruction | A material amendment appears during a long task |
| Fetch current knowledge at each read | Fresh source access | Different reads silently combine incompatible editions |
| Pin a working edition and refresh at explicit checkpoints | Makes changes visible while retaining an audit trail | Checkpoints miss a critical update or create excessive interruption |

Instruction snapshots, knowledge revisions, and historical capture may need different policies. Historical lookup also needs an explicit choice between present assessment and the knowledge available at the earlier time. Permission and applicability scope must survive retrieval: shared domain content, organization policy, project decisions, and private history should not silently override one another.

Retention is another separate decision. Corrections can preserve history while changing present interpretation, but a requirement to remove sensitive source material may also require removing derived excerpts and indexes. An append-only design is a candidate with limits, not an unconditional promise to retain everything.

## Research sequence and stop condition

Start with one narrow portion of `accounting-kr` and two intersecting development workstreams from this repo. Use synthetic rule editions for temporal tests, with no claim that their values describe actual law. Keep another small non-tax case to check whether the taxonomy merely fits the example.

1. **Select decision-changing questions.** Begin with roughly 6–10, including applicability now, applicability then, knowledge available then, rejected alternatives, open questions, and affected decisions after a premise changes. Record an expected answer and source evidence before comparing approaches.
2. **Annotate a small source sample.** Mark role, scope, authority, time meaning, and recorded versus inferred rationale. Record ambiguous classifications instead of forcing every sentence into one bucket.
3. **Compare progressively richer representations.** Start with annotated documents and existing decision records; add stable claim/decision links only where questions fail; add more formal ontology or derived graph indexes when they resolve a demonstrated failure. These approaches can coexist, so measure the extra structure rather than treating them as exclusive products.
4. **Inject bounded changes and contradictions.** Run the scenarios below against the same question set and evidence boundary. Keep extraction and retrieval errors separate.
5. **Evaluate usefulness and maintenance cost.** Compare answer correctness, scope and temporal correctness, source traceability, false rationale, missed impacts, justified abstention, capture effort, revision effort, and delivered context size. Repeat probabilistic comparisons before making performance claims.
6. **Decide only the boundaries the evidence supports.** Produce a classification with counterexamples, a question-and-evidence set, an onto mapping, a temporal scenario, and a concurrent history sample. Only then choose naming, schemas, storage, and runtime integration.

| Scenario | Required distinction |
| --- | --- |
| An amendment is published now but applies later | Newest publication versus applicable rule |
| A change is discovered late, or a source is retrospectively corrected | Domain time versus system knowledge at the decision time |
| Two apparently conflicting claims cover different entities or exceptions | Scope difference versus genuine contradiction |
| Two authoritative sources conflict for the same scope | Dispute versus automatic newest-value replacement |
| A source changes but a derived summary or question does not | Source refresh versus completed semantic update |
| Two workstreams independently choose incompatible approaches | Concurrent decisions versus fabricated causal order |
| One workstream consumes the other's result and later reopens a decision | Explicit dependency, supersession, and many-to-many membership |
| An old decision was justified then but unsuitable now | Historical rationale versus current recommendation |
| A one-off fix is proposed as a general instruction | Experience versus accepted generalization |
| No record explains why an option was rejected | Justified unknown versus invented rationale |
| Every schema check passes but the interpretation is wrong | Structural conformity versus grounded correctness |
| A query or lens reaches no relevant claim | Empty subject set versus successful validation |

LongMemEval contributes evaluation axes for extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention. Its conversational tasks do not certify performance on this product's decision histories. LoCoMo adds long-conversation event and temporal reasoning scenarios, with a similar transfer limitation. [LongMemEval](https://arxiv.org/abs/2410.10813), [LoCoMo](https://aclanthology.org/2024.acl-long.747/)

Zep's 2025 paper provides a concrete precedent for retaining episodes alongside derived semantic facts and using two temporal axes. Its described preference for newly ingested information when invalidating conflicting facts should not be imported as authority resolution for legal or organizational knowledge. Its benchmarks are evidence about that evaluated system and task, not grounds for choosing our storage. [Zep, §§2.1–2.2.3](https://arxiv.org/html/2501.13956v1)

The research can stop and design can begin when each selected question has a bounded evidence path, representative failure cases distinguish the candidates, and remaining uncertainty can be expressed as an explicit tradeoff. Success is useful decisions with correct scope, time, and provenance at tolerable maintenance cost—not the largest ontology, most memories, or a nominally complete lens score.

Still open: whether corpus remains the umbrella name; which actors may adopt norms and accept external claims; minimum workstream identity and relation structure; refresh policy; capture and retention scope; and which machinery belongs in agent-bios versus an external knowledge provider. This note closes none of those alternatives.
