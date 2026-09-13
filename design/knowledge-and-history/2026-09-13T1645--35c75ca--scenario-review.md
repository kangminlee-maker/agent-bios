---
created_at: 2026-09-13T16:45:56+09:00
head: 35c75ca
kind: review
status: design-walkthrough
reviews: 2026-09-13T1642--35c75ca--minimal-architecture.md
---

# Scenario review of the minimal architecture

Companion to [the proposed design](/Users/kangmin/Documents/agent-bios-personal/design/knowledge-and-history/2026-09-13T1642--35c75ca--minimal-architecture.md). These are worked contract examples and adversarial design review, not executed runtime tests or empirical performance results. Symbolic IDs are illustrative; the existing runtime does not implement the proposed providers.

## A. Changing knowledge: synthetic rate schedule

All rates, dates, and jurisdiction below are fictional. One stable item, `example/rate-schedule`, covers one declared entity class and jurisdiction. Each revision retains its complete table and exact source evidence.

| Revision | Available in the local store | Accepted for this scope | Contents of that complete edition |
| --- | --- | --- | --- |
| K1 | January 10 | January 11 | 10% from January 1 |
| K2 | June 10 | June 11 | 10% in the current year; 12% from next January 1 |
| K3 | September 10 | September 12 | 10% January–June; corrected 11% July–December; 12% from next January 1 |

K3 captures a correction discovered in September with July applicability. An August 15 decision D1 cites K2 as its explicit premise. Its rationale records that it applied the selected schedule; no additional motive is inferred.

| Query or action | Required result | Contract exercised |
| --- | --- | --- |
| Inspect D1 in September | Return K2 and its source edition; D1 recorded 10% | Exact historical citation |
| Evaluate August using the accepted September 13 edition | K3's July–December row states 11% | Applicability within the selected edition |
| Evaluate December | 11%, not the later 12% entry | Publication/availability does not imply applicability |
| Inspect September 11 local state | K3 is available but not accepted; K2 is selected and the known material correction remains pending | Availability and acceptance are different |
| Require a confirmed current assessment on September 11 | Surface the pending correction; obtain its disposition before certifying the affected answer | A stale selection does not hide known uncertainty |
| Assess impact after accepting K3 | Find D1 through its explicit K2 premise; request review without changing D1 | Bounded impact, historical preservation |
| Import K2 into a second store in October | Preserve K2's identity and source metadata; add an October local availability receipt | Source revision versus local ingestion |

Result of the walkthrough: full schedule revisions and exact references distinguish the required questions without a generic temporal database. The domain-specific interpretation of the table still requires a valid rule/reader; this exercise does not establish automatic applicability reasoning.

## B. Concurrent work and changing decisions

Workstreams W1 and W2 have stable IDs and distinct purposes. Sessions S1 and S2 are provenance only. The bounded shared decision scope is `example/config-format`.

1. W1 records adopted decision D2 choosing format A, with premise K2. W2 independently records adopted D3 choosing format B, also with premise K2. No causal edge connects D2 and D3 merely because they cite the same source.
2. A later session S3 continues W1 under the same workstream ID. If W2 uses W1's output, the consuming record adds an exact `basis` reference. Workstream membership alone cannot create it.
3. A scoped view returns both D2 and D3. A conflict event can target both; semantic incompatibility is a recorded finding, not a guarantee derived from equal scope or time order.
4. D4 adopts C and names D2 and D3 in `replaces`. Its scope is exactly the declared shared scope. The current view can show C while retaining the replaced choices and reasons.
5. If concurrent D5 instead adopts E and names the same predecessors, both D4 and D5 remain in the current candidate set. Removing the predecessors cannot conceal the competition between successors. A later resolution must name the choices it displaces.
6. An implementation observation targets D4 and cites the resulting artifact. This proves an observation about implementation; acceptance by itself did not prove implementation or verification.

Result of the walkthrough: stable workstream identity, explicit premises, targeted events, and whole-decision replacement cover the example. No total ordering of independent work, option-node graph, or automatic conflict adjudicator is required.

## C. Cheap failure cases that change the design

| Failure case | Required behavior | Where it belongs |
| --- | --- | --- |
| A record incorrectly says a decision was accepted | Append a correction targeting that acceptance assertion; do not present a later withdrawal as the same event | History semantics |
| A real acceptance is later withdrawn | Preserve that it was once accepted and record the subsequent withdrawal | History semantics |
| Destination content exists, but promotion selection fails | Request remains pending; the content reference does not certify adoption | Destination provider receipt |
| Destination selection succeeds, but completion recording is interrupted | Reconcile from its successful selection receipt; do not replay selection blindly | Local recovery and history completion |
| Same immutable ID arrives with different bytes | Reject collision/corruption instead of overwriting | Provider integrity boundary |
| A referenced decision or event is missing | Show unresolved affected state; do not substitute a latest object or erase another candidate | Reference resolver/current-work reducer |
| Lifecycle assertions contradict or replacement links cycle | Report unresolved affected decisions; chronological sorting cannot choose a winner | Current-work reducer |
| Raw knowledge says “always do X” | Return it as domain/reference content; its phrasing does not grant instruction authority | Role-specific delivery |
| A lesson is captured from one successful workaround | Retain the scoped experience; publish/select a general rule only through explicit destination adoption | Promotion boundary |
| Source text is no longer available | Report unavailable evidence; retain provenance where permitted without claiming content reconstruction | Reference resolver/retention |
| A new memory event is appended while corpus editing is pending | Keep corpus's local expected revision independent of the new memory provider | Local concurrency boundary |

These cases become implementation acceptance tests with negative controls when the corresponding runtime owners are introduced. At design time, they are specification obligations, not green gates.

## Independent review and limits

Two delegated reviews examined the draft's temporal/knowledge boundary and decision/concurrency boundary. Both identified premature adoption evidence in the promotion sequence. The knowledge review also found the conflation of canonical revision metadata and local ingestion time. The history review required a distinction between correcting a false acceptance assertion and subsequently withdrawing an actual choice. The design now separates those cases and names unresolved reducer behavior.

The reviews agreed that compulsory claim atomization, universal source ranking, a generic scope algebra, and an argument graph would add complexity without resolving these examples. Their omission is recorded with revisit triggers in the design.

This was same-family agent review and a manual scenario walkthrough. It is neither independent cross-family validation nor implementation verification. External-domain interpretation accuracy, capture effort, retrieval quality, and practical refresh cost remain unmeasured. The first implementation slice should measure those in a narrow real workflow instead of expanding the schema in advance.
