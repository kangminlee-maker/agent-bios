---
created_at: 2026-09-06T20:40:00+09:00
head: 5cc90fa
kind: design
role: independent frontier draft (codex seat) from the blind packet 2026-09-06T2021--5cc90fa--spawn-trigger-experiment-packet.md (read with its created_at stamped 12:10, sha256 b71ebdfcfbf8…; the committed packet differs only in that stamp, sha256 c1e1a471a769…); unedited; synthesized into 2026-09-06T2050--5cc90fa--spawn-trigger-experiment.md
seat: gpt-5.6-sol at ultra, read-only, packet on stdin
session: 01a07673-f159-79e1-9c21-f3f5d146ca65
body_sha256: c256314151b392fcef30d6eb86dcd25c3d4908b754ef3884bd301c48d11cf26d
---

# 1. The question

For the Claude host’s self-contained, dependent L2 edit family, estimate at small M the paired difference between inline and delegated-workhorse modelled ledger cost to parity, after charging each candidate rule for its own evaluation at every recorded boundary and for its global-text carriage on every parent and child request. Compare candidate rules by the actions they select, adherence on known-opposite cases, required inputs, tokens, and decision seconds. The result is the simplest rule that identifies a confirmed paying region while preserving held-out quality, or “none” if no rule survives.

# 2. Candidate trigger forms this design discriminates between

Inputs are counted beyond the common explicit no-fan-out override.

| Form | Inputs | Already known at the boundary? | Treatment |
|---|---:|---|---|
| T-A item count | M: 1 | Yes only for an itemized unit; unsafe without the existing eligibility envelope | Its count may be used by T-E; not deployed alone |
| T-B shape checklist | decision-complete, machine-checkable done-when, self-contained: 3 | Yes after normal planning | Selectable |
| T-C default with exceptions | live context, repeated-reasoning verification, other inline exception: 3 after bounded-work classification | Yes | Selectable |
| T-D leverage ratio | T-B eligibility plus E and H estimates: 5 | E and H require fresh judgment or a tool | Selectable only if that extra cost buys unique discrimination |
| T-E two-stage | T-B plus M: 4 | Yes when the unit is itemized | Selectable |
| T-F tier by difficulty | T-B plus L: 4 | L is a semantic judgment | Not selectable: L1/L3 are not run |

T-B and T-C are one behavioral class on ordinary eligible fixtures. Exception cards distinguish their adherence and evaluation cost, not their implementation outcomes.

The pre-registered mapping is:

- If delegation pays at M=1 and no larger sampled M reverses direction, select T-B or T-C. Choose the one with zero adherence errors and the smaller input count; then smaller operating-cost upper bound; then shorter text and decision latency.
- If a lower tested size is confirmed not to pay and a larger size is confirmed to pay, select T-E with the smallest confirmed conservative threshold. Untested smaller sizes remain inline.
- T-D wins only if its sealed pre-outcome decisions correctly distinguish every confirmed paying and non-paying cell that the simpler forms cannot, and its additional operating cost leaves a positive net contrast. Equal decisions select the simpler observable-input rule.
- T-A alone is rejected because the task experiment cannot justify discarding eligibility.
- The tier is WORKHORSE: the existing retention result is KEEP and found no confirmed rebind. Existing SWEEP, fan-out, FRONTIER, independence, and escalation rules remain separate.
- Reject all candidate cost-trigger forms if delegated quality misses parity, no form passes the controls, trigger cost removes every saving, or the observed cost pattern cannot be represented by any candidate’s own rule. “None” means no cost-driven spawn on this tested shape; quality-driven gates remain.
- “Spawn less than now” is established when current v1 delegates on a boundary card whose matched execution cell is confirmed non-paying, while the selected T-E rule keeps it inline.

# 3. Design

## Variables and estimands

Host is Claude; L=L2. Initial M values are 1, 5, and 10. At most one conditional discovery cell is added: M=3 if the boundary lies between 1 and 5, M=7 if it lies between 5 and 10, or M=40 if M=10 does not pay. This is a pre-registered decision tree, not a post-hoc grid.

Task arms are inline and delegated-workhorse. Each cell uses R matched blocks, one shared fixture per block, counterbalanced arms, the existing B₁/B₂ repair protocol, receipts, access scan, sealing, and exactly-R reader.

For candidate rule \(r\), the primary estimand at M is:

\[
S_r(M)=C_{\text{inline, parity}}(M)
-\left[C_{\text{workhorse, parity}}(M)+C_{\text{rule},r}\right].
\]

The rule’s operating cost is computed per completed work unit from:

- the actual number of SpawnGate decisions multiplied by the one-sided upper bound on marginal decision cost per boundary; and
- the actual parent/child request count multiplied by the exact ledger cost of carrying that candidate’s global text.

Thus repeated evaluation and retransmission are charged rather than treated as free. Tools calculate tokens, prices, bounds, and the M decision tree; the agent supplies only semantic boundary judgments.

A cell is:

- **PAY** when WORKHORSE reaches the same done-when and has no additional held-out defect versus its matched inline arm, and the one-sided lower bound of \(S_r(M)\) is above zero;
- **NONPAY** when quality fails or the one-sided upper bound of \(S_r(M)\) is at or below zero;
- **UNCLEAR** otherwise.

The reader also reports how many boundary evaluations one confirmed spawn saving funds. At the cited 2.6% firing rate, 39 evaluations per saving is the break-even sensitivity. This is not a trigger input or a claim about a future task mix.

## Build surface

No new generator rung, execution arm, repair rule, or implementation brief is required.

- Extend the existing M parameter downward and add controls for exact item count, visible-test failure, non-empty held-out checks, helper use, and the degenerate M=1 chain.
- Register inline versus delegated-workhorse as a primary reader contrast and add its sign-reversal self-test.
- Add one decision-only boundary brief. Before runs, freeze and hash the shortest semantics-preserving text for T-A through T-E, current v1, and a length-matched null. Reuse request receipts and SpawnGate records; do not add a second cost artifact.
- Add paired exception cards, but no executable context-dependence axis.

Estimated build cost is about one engineer-day: generator validation, one brief, reader projection, and controls.

## Staging

**Stage A — trigger-cost and adherence screen.** Run eight matched boundary-card blocks across T-A through T-E, v1, and the length-matched null, counterbalanced. Cards include ordinary M=1/5/10 fixtures and pairs differing in exactly one fact: self-contained versus parent-only information, machine-checkable versus reasoning-repeating verification, and no-fan-out absent versus present. Decisions are sealed before task outcomes are read.

For each rule, measure input, output, exposed reasoning usage, wall-clock, tool calls, and static global-text tokens. The paired rule-minus-null upper bound supplies marginal decision cost. Any known-opposite error rejects that wording. A tool call is fully charged; it survives only if the resulting rule still meets PAY.

**Stage B — downward-M discovery.** Run M=1, 5, and 10 with R=10 sound blocks and two arms. Then run at most one pre-declared conditional cell:

- M=3 when M=1 is not PAY and M=5 is PAY;
- M=7 when M=5 is not PAY and M=10 is PAY;
- M=40 when M=10 is not PAY.

A lower-M PAY followed by a higher-M NONPAY rejects an item-count threshold. An UNCLEAR cell stays inline and cannot establish a constant.

Discovery uses paired block bootstrap with 10,000 fixed-seed draws and one-sided 90% screening bounds. It writes a candidate manifest containing the exact rule, threshold interpretation, cells, contrasts, seats, and confirmation R before fresh data exist.

**Stage C — confirmation.** Confirm the nominated PAY cell and, when the result would tighten spawning, its nearest tested lower cell using R=5 fresh blocks each. Set \(k\) to the manifest’s exact number of claims, at most two, and use one-sided \(1-0.1/k\) bounds. Unlisted thresholds are NOT RUN. An unclear result produces no text change; R is never extended automatically.

## Controls and thresholds

- Every cell asserts exactly R sound matched blocks and a non-empty held-out subject before reading.
- A seeded arm-label/sign reversal must reverse the reader’s result.
- A planted held-out defect must fail parity; a planted oracle read must be caught by the access scan.
- Length-matched null cards must exercise both output labels; deliberately inverted decisions must be rejected by the scorer.
- Prompt hashes, requested and actual seats, effort, participant costs, request counts, and SpawnGate counts must match the stage declaration.
- Zero is the economic threshold: no unregistered “small enough” loss.
- Selection is lexicographic among rules with equivalent confirmed decisions: fewer inputs, inputs already known, lower operating-cost upper bound, then shorter text and lower decision latency.

# 4. Budget and stop rules

| Stage | Volume | Expected cost | Serial wall-clock | Hard ceiling |
|---|---:|---:|---:|---:|
| A: trigger screen | 56 short calls | $3–10 | 15–45 min | $10 |
| B: initial discovery | 60 full runs | $30–75 | 1.5–4.5 h | $75 |
| B: one conditional cell | 20 full runs | $10–25 | 0.5–1.5 h | $25 |
| C: confirmation | 10–20 full runs | $5–30 | 0.25–1.5 h | $30 |

Total ceiling: **$140**, excluding engineering time. A stage starts only if the remaining budget covers its ceiling.

Stop on two consecutive failed dispatches, identity or seat mismatch, failed negative control, prompt-hash drift, inability to complete exactly R sound blocks within the stage ceiling, or a non-monotone result that defeats the candidate form. Voided runs may be replaced with fresh blocks only inside the declared ceiling. Any extension beyond R or $140 requires owner approval.

# 5. What this cannot answer

This design cannot value independence or escalation; their benefit is error detection or authority control, not cheap implementation. It excludes independent fan-out and cannot revise the ≥2-items parallelism rule.

The exception cards test instruction adherence only. They do not measure the real cost of transferring parent-held context, so the live-context exception remains.

Only Claude, one dependent L2 family, and WORKHORSE versus inline are tested. It cannot select T-F, build L1/L3, or establish a small-M SWEEP rebind. Codex remains excluded until its held-out-oracle isolation failure is repaired.

Inline versus WORKHORSE intentionally combines routing, shorter child context, brief construction, reconciliation, and seat price. That is the deployed decision, but it prevents attributing savings to seat alone. All-zero held-out defects may again leave quality uninformative despite the planted-defect control.

The experiment produces net cost per tested work unit and evaluations-funded sensitivity, not corpus-wide savings: a representative future boundary distribution is unavailable. Wall-clock is reported but does not choose the trigger.

# 6. Decisions for the owner

- **Run the minimal L2 design with a $140 ceiling (default).** It can select a WORKHORSE cost trigger without building another generator axis. L1/L3, context, or fan-out would multiply build and cell cost.
- **Use a conservative tested threshold (default).** This may leave savings at untested intermediate M values, but avoids paying to locate an exact integer breakpoint.
- **Treat UNCLEAR as no text change (default).** More precision requires a separately approved completion draw; the threshold is not repaired after results.
- **Optimize ledger cost and disclose latency (default).** Making elapsed time co-equal requires a utility or veto threshold declared before runs.
- **Keep quality-driven and SWEEP/fan-out gates unchanged (default).** The experiment has no evidence to weaken or broaden them.
- **Treat the 2.6% firing-rate calculation as a sensitivity, not proof of corpus-wide return (default).** A deployment-wide savings claim would require a separately sampled boundary distribution.

# 7. Assumptions you made

- The L2 generator accepts positive M; only the dependency chain degenerates at M=1.
- M is already explicit for this task family and needs no counting tool.
- Seats, effort, ledger pricing, corpus pin, and repair protocol remain fixed across stages.
- Decision-only paired calls conservatively bound embedded trigger deliberation.
- Request receipts and SpawnGate records expose every request and work-unit boundary used by the operating ledger.
- Savings are monotone enough between sampled M values for a conservative threshold; a sampled reversal rejects that assumption.
- The cited 2.6% rate is suitable only for the stated sensitivity calculation.
- Engineering time is available but excluded from ledger cost.
