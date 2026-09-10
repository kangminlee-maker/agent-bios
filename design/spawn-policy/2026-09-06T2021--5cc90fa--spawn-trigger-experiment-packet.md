---
created_at: 2026-09-06T20:21:00+09:00
head: 5cc90fa
kind: design
role: blind design packet — the same bytes go to two frontier seats (one per provider); each returns an independent draft, and the working design is synthesized from both. It carries evidence, constraints, a rubric, and neutral alternatives; it carries no draft conclusion.
---

# Design packet: an experiment that yields a simple, cheap-to-evaluate spawn trigger

You are drafting an **experiment design**, not the trigger itself. Read everything below, then return one document in the deliverable shape at the end. Do not assume access to the repository, the run trees, or the network — everything you need is here. Where you must assume, say so in one line and continue.

## 1. Purpose clause, and the decision this feeds

An agent corpus (deployed instruction text for Claude Code and Codex) ships a **tier structure** — a parent seat (opus-5 at xhigh on Claude; gpt-5.6-sol on Codex) that can spawn child agents on cheaper seats: **WORKHORSE** (sonnet-5 at xhigh on Claude) for bounded implementation with frozen requirements, and **SWEEP** (haiku 4.5 on Claude, no effort lever; a "luna" seat on Codex) for one-rule mechanical scans that return ambiguity as an exception. A spawn policy, deployed in the always-loaded global text, tells the parent when to spawn. Its current text (v1, 2026-07-19) is quoted in §3.

A cost experiment (Sept 2026, §4) has now **confirmed** that spawning to the cheaper WORKHORSE seat reaches the same result for 45.5% less than spawning to the parent's own seat, and that the cheaper seats never fell short on quality on that task family. The owner's reading: the tier structure and the spawn mechanism are valuable and valid. **What the corpus still cannot say is *when* to spawn** — the v1 gates are qualitative, and the planned "P2" route (derive constants from accumulated one-line decision records) has not produced a constant.

The decision this experiment feeds: **the wording of the spawn trigger in the deployed global** — what an agent evaluates at each work-unit boundary to decide spawn-vs-inline, and to which tier. That text is re-sent every session and to every subagent; its evaluation cost is paid at every boundary.

**The owner's premise, binding on every draft:** *the spawn trigger must be as simple as possible. A heavy trigger accumulates judgment cost at every boundary and can make the whole scheme less efficient than never spawning.* A rule that asks the agent to estimate costs, run a tool, or reason at length before deciding is itself a cost the experiment must count. A trigger's simplicity — how many inputs it needs and whether each is already known at the boundary — is a first-class outcome, not a tie-breaker.

## 2. Corpus design principles (inject into your reasoning; the corpus enforces them)

- **Concept economy.** A new concept, field, term, or artifact is admitted only when a supported question demands it; reuse existing terms (below) and name any new one explicitly with what it displaces. A trigger with fewer inputs is preferred to one with more, at equal discriminating power.
- **LLM / capability boundary.** The LLM does semantic work (judging a task's shape); tools/code do deterministic work (counting, measuring, pricing). A trigger that needs a tool call per boundary pays that call every time; a trigger that needs only what the agent already sees pays nothing extra. Enforce constraints through the capability surface where possible rather than by repeated prohibition.
- **Staged workflow.** Design → implementation-process design → implementation. Success criteria are written before the work and verified against; a criterion written afterwards cannot fail. Minimum viable surface; real behaviour on the real path.
- **Verification discipline.** Pre-register estimands, thresholds, sample-size rules, and stop rules; every check has a negative control; a green result over an empty subject set is not a result; a measurement that agrees with expectation is the moment to test the instrument against a known-opposite input.
- **Documentation hygiene.** Active text states the present; dated records carry history; rules are phrased so others can follow them.
- **Decision framing.** Options are presented in outcome terms with a default; controls are sized to named risks; a target is a direction, not an absolute.

Existing terms to reuse: **M** (items per run), **L** (difficulty rung: L1 mechanical edit / L2 small algorithm inside a frozen interface / L3 edit needing a read of an adjacent module), **R** (repetitions per cell, matched blocks), **arm** (inline / delegated-same / delegated-workhorse / delegated-sweep), **cell** (host × M × L), **block** (one fixture shared by the arms), **contrast** (a paired difference between two arms over blocks), **retention** (workhorse vs same-seat child), **rebind** (sweep vs same, sweep vs workhorse), **KEEP / REBIND / no-seat-effect** (labels), **discovery → candidate manifest → confirmation** (two-phase reading at 1 − 0.1/k), **SpawnGate record** (one line per gate decision), **done-when** (the machine-checkable acceptance a down-spawn carries), **cost to parity** (the modelled ledger cost at which an arm reaches the same level of result as the parent's own seat, after a fixed repair protocol).

## 3. What the corpus says today (verbatim)

The deployed spawn block (Claude global, re-sent every session):

> Standing spawn policy: check the spawn gates at every work-unit boundary — judgment latitude applies inside a gate, never to whether the gates are checked. Independence: before presenting a load-bearing conclusion or taking an irreversible step, propose the cross-check unprompted; the user should never have to ask for it. Independence comes from the seat you dispatch to, so name it. Parallelism: two or more independent items spawn in parallel — SWEEP when each item applies one explicit rule and returns ambiguity as an exception, else WORKHORSE. Residual context: work whose log dwarfs the conclusion the main needs spawns with a bounded report contract. Escalation: an irreversible or authority-changing action ahead, two failed attempts, or two persisting design alternatives spawns a bounded FRONTIER judgment with a blind packet (evidence, constraints, rubric, neutral alternatives — never your draft conclusion) and a pre-noted change condition. Specifiability/de-minimis: work needing your live context, or whose verification would repeat the reasoning, or whose packet outweighs the work, stays inline.
>
> Down-spawns carry a machine-checkable done-when on decision-complete work with staged output (no external irreversible actions) and a tier pinned before dispatch. Record one line per gate decision — `SpawnGate: <gate> <tier> spawn|inline — <why>` — and for FRONTIER record the disposition afterward (what changed, or why nothing did). A launch contract's `Delegation=off` lifts the spawn obligation, not the records; explicit user no-fan-out always wins.

The spawn-policy design's governing directive (owner, 2026-07-19): *v1 — principled triggers, reliable firing: gates are logical criteria; judgment inside a gate, never about the gates; no calibration constants in v1 text; countable criteria that make a trigger checkable (≥2 independent items, two failed attempts) are allowed, ratio constants are not. P2 — numeric trigger guide from data: once decision records accumulate, derive data-backed constants (leverage ratio, displacement thresholds, per-gate capture targets).* Its down-delegation conditions: decision-complete / input-closed; machine-checkable done-when that rejects a wrong result *without repeating the reasoning*; decision locality; staged, reversible output; **positive leverage** — H (brief + verify + correct + integrate) clearly subordinate to E (the work the main would do inline), stated qualitatively in v1, with a measured ratio (a proposal: E ≥ 2H) deferred to P2; and a trigger benefit — ≥2 independent parallel items, or a working log ≫ the conclusion (context displacement). Its P1 metrics (gate-event count and spawn/inline split, rework rate, context displacement ratio, round-trips per spawn, frontier disposition rate) were to be computed from transcripts and decision records; the baseline firing rate cited then was 2.6%. **As of 2026-09-06 no constant has been derived from records** — the records route has not delivered P2.

## 4. What the cost experiment measured (Sept 2026; all figures are modelled ledger cost to parity, one host — Claude — one difficulty L2, one task family)

**Task family.** M bounded edits to an existing package: each item a stubbed function with a stated spec, a visible failing test that must pass, and a regression check that must keep passing; the M items are **one dependent work unit** (item k calls item k−1 through a shared helper), not M independent tasks — the contract's single-dispatch case. Every arm brings the work to the same done-when by one fixed repair protocol (B₁ = 2 self-verify passes by the child, B₂ = 1 repair pass by the parent), and a held-out defect count on checks no arm sees measures the level of result. The fixture generator draws **L2 only**; L1 and L3 are defined but not built. The parent seat in every arm is opus-5 at xhigh; **inline** = the parent does the work itself; **delegated-same** = the parent spawns one child on its own seat; **delegated-workhorse** = one child on sonnet-5 at xhigh; **delegated-sweep** = one child on haiku 4.5. Every spawn is a real `claude -p` child with the corpus's real workhorse/sweep agent definitions and a brief the parent writes; the spawn's cost includes the brief, the child's priming, and the parent's reconciliation.

**Registered result (confirmed).** Retention at M=40: the workhorse child reaches parity for **45.5% less** than the same-seat child, one-sided 96.7% lower bound 40.4% (five fresh blocks; discovery had 45.0% [43.1, 47.0]). Discovery also closed M=10 (+44.7% [41.9, 47.2]) and M=160 (+35.0% [27.9, 41.0]) as KEEP candidates, unconfirmed. No REBIND: the sweep child saves against the same seat but costs more than the workhorse at M=40 and M=160 (upper bound −2.4% at M=40 confirmation) and only 10.3% less at M=10. **Quality separated nothing**: every one of 302 sound runs reached parity at level 0 — the cheap seats never fell short on this family, so the same-level predicate held vacuously.

**Unregistered but measured — the numbers a spawn trigger actually needs** (mean $ per run over sound discovery runs, both roots; per-item cost in parentheses; n = runs):

| M | inline | delegated-same | delegated-workhorse | delegated-sweep |
|---|---|---|---|---|
| 10 | 0.733 (0.0733; n=15) | 1.069 (0.1069; n=14) | 0.591 (0.0591; n=15) | 0.538 (0.0538; n=15) |
| 40 | 0.913 (0.0228; n=5) | 1.225 (0.0306; n=5) | 0.674 (0.0169; n=5) | 0.803 (0.0201; n=5) |
| 160 | 1.230 (0.0077; n=9) | 1.465 (0.0092; n=8) | 0.953 (0.0060; n=9) | 1.081 (0.0068; n=7) |

Confirmation (M=40, five fresh blocks): inline 0.983, same 1.245, workhorse 0.679, sweep 0.791.

Read as differences from inline: same-seat delegation costs **+0.336 / +0.312 / +0.234 per run** at M=10/40/160 (+46% / +34% / +19%) — a roughly fixed overhead per spawn (brief, priming, reconciliation) that shrinks as a share when the work grows; the workhorse child is **−0.143 / −0.239 / −0.277** (−19% / −26% / −23%); the sweep child **−0.196 / −0.110 / −0.150** (−27% / −12% / −12%). Median dispatch wall-clock (seconds): inline 92 / 128 / 174; same 148 / 163 / 203; workhorse 107 / 133 / 208; sweep 150 / 260 / 266. So on this family a spawn to a cheaper seat paid at every tested M and the break-even was never observed; a linear extrapolation of the fixed overhead against the per-item saving puts it near M ≈ 5–7 for L2, which is a hypothesis, not a measurement. **Inline vs delegated was a consistency check in that design, not a registered contrast** — the design's comparator was delegated-same on purpose, because a child has a shorter context, no prior-turn thinking, and may reuse a fan-out prefix, which confounds seat with routing. For the trigger question that confound is the object of study.

**What the design of that experiment could not answer, by its own account:** the independent fan-out case (parallel children), tasks needing the parent's live context, quality-driven spawns (independence, escalation), the other host beyond a thinned Codex screen, any L but L2, and anything about wall-clock beyond reporting it.

**Instrument facts.** Runner: declares a stage (host × sizes × R × arms) at one git pin, one fixture per block shared by its arms, runs counterbalanced, records every run with a receipt (seats, effort, cost per participant and request, access scan of every tool call for reads of the held-out oracle, ledger of repair passes), seals finished runs, stops after two consecutive failed dispatches, resumes idempotently; a completion draw extends a stage's cells with fresh blocks for the same seats; a confirmation stage takes cells and R from a candidate manifest written by the discovery read. Reader: paired block bootstrap (10,000 draws, seed), one-sided bounds, exactly-R completeness with surplus disclosure, the 1 − 0.1/k confirmation threshold, NOT RUN vs not confirmed. Costs seen: $0.5–1.5 per run, 1.5–4.5 minutes per run, ≈$18 per 20-run cell at M=40; the Claude line has spent $121.58. Host facts: the Claude seat is an OAuth login whose token was revoked once mid-stage (the breaker caught it, no cost); haiku 4.5 has no effort lever; on Codex the sweep seat read the held-out oracle in 37.5% of runs (voided), so Codex cells never completed. The self-test holds 271 checks with negative controls; every reader fix has a revert proof.

## 5. Constraints

1. **Deliverable is a design**, in the shape given in §8, ≤ 2,500 words. Not the trigger text itself — but the design must say how its results map to trigger text (which result selects which candidate rule, and what result rejects all of them).
2. **Reuse the instrument.** New fixture axes cost build time; say which the design needs and what they cost to build (in the instrument's terms: generator rungs, arms, briefs, controls). Prefer the smallest set of new axes that can find a boundary.
3. **Count the trigger's own cost.** A candidate rule's evaluation cost at a boundary (tokens or seconds the agent spends to decide, plus any tool call) must be measured or bounded by the design, not assumed zero.
4. **Budget and stop rules.** State cost and wall-clock per stage; propose a budget ceiling and the pre-registered stop rules; the owner has approved ≈$18–25 per cell-stage before and stopped a step whose cost outgrew that; extension past a declared R needs approval.
5. **Pre-register** estimands, contrasts, thresholds, sample-size rule, and the decision rule from results to trigger text. Name what result would say "spawn less than now".
6. **Scope honesty.** State what the design cannot answer, including the quality-driven gates (independence, escalation) that a cost experiment cannot reach, and the fan-out case if not covered.
7. **The trigger must be evaluable by the agent at the boundary from what it already knows** — or the design must show that the extra information is worth its cost. Count a rule's inputs.
8. Single-user tooling; proportionality applies — the heavy apparatus (randomized holdouts, blinded adjudication) is warranted only for a boundary-widening move.

## 6. Rubric (how the two drafts will be judged and synthesized)

1. Does the design's result select a spawn-vs-inline **decision rule** an agent can apply at a boundary, and to which tier?
2. **Simplicity, counted**: number of inputs each candidate rule needs; whether each is observable without extra work; the rule's own evaluation cost, measured or bounded.
3. **Discrimination**: can the experiment reject at least two of the candidate rule forms, and can it reject all of them?
4. **Falsifiability**: names the result that would say "spawn less" or "never spawn on this shape".
5. **Instrument reuse and build cost**: new axes named with their cost; nothing rebuilt that exists.
6. **Pre-registration**: estimands, thresholds, R rule, stop rules, budget — all before data.
7. **Scope honesty**: what it cannot answer, stated; the confounds it accepts, named (routing vs seat; task family; one host).
8. Concept economy: no new term without a demanding question; existing terms reused.

## 7. Neutral alternatives (enumerate; none is preferred here)

Candidate **trigger forms** the experiment could discriminate between:

- **T-A Item-count threshold**: spawn to the cheaper seat when the work unit has at least N items (or the agent expects at least T minutes of bounded work); otherwise inline.
- **T-B Shape checklist, no numbers**: spawn when the work is decision-complete, has a machine-checkable done-when, and is self-contained (needs none of the parent's live context); otherwise inline. No count.
- **T-C Default-delegate with exceptions**: bounded implementation goes to the cheaper seat by default; the only inline cases are named exceptions (needs live context; verification would repeat the reasoning; explicit no-fan-out).
- **T-D Leverage ratio**: spawn when E ≥ 2H (or another constant), with E and H estimated at the boundary.
- **T-E Two-stage**: a shape checklist decides eligibility; a count decides worthwhileness.
- **T-F Tier by difficulty**: the same eligibility rule, but the tier is chosen by a difficulty read (L1 → sweep, L2 → workhorse, L3 → inline or workhorse-with-review).

Candidate **experiment shapes**:

- **X-1** Extend the existing instrument downward in M (e.g., 1, 2, 3, 5) at L2 to locate the break-even, with inline vs delegated-workhorse as the registered primary contrast.
- **X-2** Build L1 and L3 in the generator and run the M × L grid with inline as comparator, so the rule can be a function of both size and difficulty, and so quality can finally separate seats (L3).
- **X-3** Add a **context-dependence axis** to the generator: a variant of the task where the parent holds information the child needs (a spec only the parent has seen; a decision made earlier in the session), so "needs live context" becomes measurable rather than judged.
- **X-4** Measure the trigger's cost directly: instrument boundaries in real sessions (SpawnGate records) or in the harness, timing and token-counting the decision under each candidate rule text.
- **X-5** Observational: mine existing session transcripts for spawn/inline decisions and outcomes (known limit: measures task selection, not the trigger's value).
- **X-6** A fan-out variant: M independent items, parallel children vs inline — the case the last design excluded.

Combinations and orderings are open; so is a staged plan that runs the cheapest discriminating stage first.

## 8. Deliverable shape

Return one markdown document with these sections, in this order, ≤ 2,500 words:

1. **The question** — one paragraph, as an estimand: what is measured, on what, compared to what.
2. **Candidate trigger forms this design discriminates between** — and the decision rule mapping results to a form (or to "none").
3. **Design** — variables (reuse §2 terms), task and any new generator axis (with build cost), treatment matrix (arms, comparator), staging (which stage first and why; what each stage can decide alone), sample-size rule, controls (including the trigger-cost measurement and at least one known-opposite control), pre-registered thresholds.
4. **Budget and stop rules** — per stage cost and wall-clock; ceiling; what stops it.
5. **What this cannot answer** — including the quality-driven gates and any excluded case.
6. **Decisions for the owner** — each in outcome terms with a default.
7. **Assumptions you made** — one line each.

Write plainly. No preamble. Do not restate this packet.
