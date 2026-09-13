---
created_at: 2026-09-13T21:50:08+09:00
head: 35c75ca
kind: review
status: design-walkthrough
reviews: 2026-09-13T2138--35c75ca--knowledge-memory-consumption.md
---

# Consumption: scenario review and measurement plan

This reviews the proposed consumption contract. No Domain knowledge or Decision memory reader has been implemented or benchmarked by this work. Examples below are synthetic and are not tax, legal, or operational advice.

## Small fixture

Team T adopts environment E1. E1 pins knowledge edition K1 and declares an authorized memory source. The operation identifies workstream W1.

- K1 contains a rule table, its target-period header, and an exception note. These companions are declared necessary for its support unit.
- D1 is an older decision explicitly required by E1 or the task's selected scope. Its recorded choice cites K1. Adoption event A1 targets D1.
- D2 is recent but unrelated material that a relevance/recency search can rank above D1.
- At memory frontier F2, a correction C1 recorded in W2 targets A1 and states that the acceptance was recorded in error. D1's choice remains a record; its earlier acceptance is no longer established by A1.
- Source-check evidence later reveals a material K2 correction while E1 still pins K1 pending adoption.
- A child or compacted parent may retain a packet ID without retaining its body.

The fixture deliberately separates identity, source edition, current qualification, memory frontier, and actual body delivery.

## Required outcomes

| Case | Expected behavior | Failure to prevent |
| --- | --- | --- |
| A replacement begins without old decision IDs | Resolve permitted work scope and return a bounded state body, with D1 or its qualified current state | An empty personal history presented as team state |
| The domain situation needs an initial principle to be recognized | Include the declared essential orientation excerpt and its source | Hiding all useful meaning behind an unknown lookup path |
| Required D1 falls below search top-k | Include it or name the required coverage gap before limiting optional candidates | Treating relevance ranking as authority to discard required context |
| C1 belongs to W2 while the task selects W1 | Resolve D1/A1/C1 state closure before ranking/excerpt selection | Showing D1 as accepted because a workstream filter removed its correction |
| C1's contents are restricted | Return permitted qualified state or explicit inability to establish it | Leaking restricted evidence or certifying a falsely clean state |
| A support table row fits but its period/exception does not | Preserve companions or return incomplete support with expansion | Supplying a correct-looking number under the wrong conditions |
| A small budget cuts memory rationale | Keep current-state qualifications and source locators | Turning an unresolved or corrected choice into an unqualified one |
| Required closure exceeds processing budget | Report incomplete context and a bounded next step | Unbounded replay/traversal or arbitrary partial-result certification |
| K1 is cached and K2 becomes known | Re-evaluate qualification; disclose the material pending update | Reusing an old current/adequate judgment because K1's hash did not change |
| K2 is inspected during research | Mark its relation to the adopted edition and follow update policy for changed team use | Silent replacement of E1's pinned knowledge |
| Only the packet ID survives compaction | Return required bodies again | An unchanged-only response to a consumer missing the actual text |
| A child receives only a parent's receipt | Supply the scoped body and a usable reader/expansion route, or report insufficiency | Claiming inherited consumption from parent delivery |
| The frontier advances between pages | Continue on the original frontier; refresh is a new read | Combining one page of F1 with another of F2 |
| Two child results use different frontiers | Retain their references and reconcile material differences | Combining incompatible current-state assumptions as one snapshot |
| No recorded reason exists | Say it is not recorded; identify any later interpretation separately | Generating a plausible but invented rationale |
| The team/source access changes | Recheck permission and do not satisfy the lookup from another team's cache | Cross-team data substitution or stale access reuse |
| The selected source has no records | Distinguish a permitted empty result from denied/unavailable/unsupported/truncated | Making all zero-body responses look equivalent |
| A summary is cached or reused repeatedly | Keep it a derived view with sources | Promotion into accepted knowledge or Instructions through repetition |

These are future acceptance tests and review examples. Event closure and declared companion checks can receive deterministic assertions and negative controls. Relevance and external-source interpretation need evaluated examples and review; they are not proven by the presence of metadata.

## Compare consumption approaches

Use the same environment, questions, source editions, and memory frontiers for three baselines:

| Approach | What it measures |
| --- | --- |
| Full selected sources in context | Upper context cost and whether necessary material is available |
| Locators/search results only | Low initial cost, but risk that the worker never obtains necessary meaning |
| Proposed orientation + task bodies + evidence expansion | Whether bounded relevant meaning preserves correctness with less unnecessary context |

Before comparing efficiency, check correct required support/state, qualifications, source traceability, and justified unknowns. Then measure delivered bytes/tokens, retrieval/expansion count, time to a supported decision, and generation/capture cost. Include first use, takeover, retry, compaction, and delegation; a single-session happy path does not cover the intended product.

Use repeated runs where model judgments affect results, and report model/input conditions rather than treating a sample as a universal budget. A shorter response is not an improvement if it removes a necessary exception or old decision.

## Review dispositions

The memory-focused review found two ambiguities: required subjects could be pruned before reduction, and a retained packet ID could be mistaken for a retained body. The design now resolves required identities before ranking and requires an explicit present-context body declaration for an unchanged-only response.

The knowledge-focused review found that cached support could keep stale freshness/applicability qualifications while its source hash stayed fixed. The design now distinguishes reusable source-derived text from qualifications re-evaluated for the operation.

The design also separates finite retrieval work from output size, and runtime-enforced boundaries from semantic review. Those additions use the existing reader/response contract rather than introduce more stores or views.

These were same-family delegated design reviews. They do not establish independent cross-family validation or runtime performance.

## Exclusions and revisit triggers

| Excluded initially | Reason | Revisit when |
| --- | --- | --- |
| Universal token constants | Hosts and tasks have different usable budgets | A representative evaluation supports role/view-specific defaults |
| Incremental delta delivery | Correctness depends on a retained consumer baseline, including removals and corrections | Re-delivery cost is material and baseline retention is demonstrable |
| New vector/graph retrieval infrastructure | It cannot replace applicability, state, or authority contracts | Scoped metadata/search and explicit links miss material questions or exceed measured cost |
| Every-read full ontology review | It repeats expensive authoring/revision work | A specific live-read defect requires an additional targeted check |
| Automatic semantic completeness claims | Neither top-k nor graph closure proves all relevant meaning was found | A bounded domain provides a testable completeness criterion |

## Parallel implementation boundary

The corpus-to-Instructions migration is delegated in an isolated checkout. It must not silently implement these proposed K/M readers or describe them as shipped. The current main-side SURFACES introduction now ties consumption efficiency to the canonical team-work-environment purpose; the implemented surface catalog remains unchanged.
