---
created_at: 2026-09-06T20:29:00+09:00
head: 5cc90fa
kind: design
role: independent frontier draft (claude seat) from the blind packet 2026-09-06T2021--5cc90fa--spawn-trigger-experiment-packet.md (read with its created_at stamped 12:10, sha256 b71ebdfcfbf8…; the committed packet differs only in that stamp, sha256 c1e1a471a769…); unedited; synthesized into 2026-09-06T2050--5cc90fa--spawn-trigger-experiment.md
seat: claude-fable-5 at max
session: in-session `frontier` agent (claude-fable-5 at max), packet inline, delivered in three parts
body_sha256: c7aaf7ad79319fbf452f029a298f63c91eb257d6b3be5687c5517d016de1eb2b
---

# Experiment design: locating the spawn trigger's boundary, and pricing the trigger itself

## 1. The question

For the existing L2 task family on the Claude host, measure the paired per-block difference in modelled ledger cost to parity between **inline** and **delegated-workhorse** as a function of M over {1, 2, 3, 5}, joined to the known M ∈ {10, 40, 160} results, and **net of the measured per-boundary evaluation cost of each candidate trigger text**. Secondary estimand: each candidate rule text's decision cost (marginal parent-seat tokens and seconds at a work-unit boundary) and decision consistency (flip rate over repeats on a fixed scenario set). The first estimand locates the smallest work unit at which delegation pays; the second prices the rule that would exploit it. Together they select the simplest trigger form whose *net* saving is bounded above zero everywhere the rule says spawn — or reject all forms. The primary contrast is inline vs delegated-workhorse on purpose: the trigger decides routing and seat jointly, so the confound the cost experiment avoided is this design's object.

## 2. Candidate trigger forms discriminated, and the decision rule

This design discriminates **T-A, T-B, T-C, T-D, T-E**, and conditionally **T-F** (Stage 3 only). Two instruments do the work: the small-M sweep decides *where* delegation pays (separating count-bearing forms from count-free ones), and the trigger-cost harness decides *which surviving text* is cheap and stable enough to ship (separating forms with identical extensions but different evaluation costs).

Define S(M) = paired mean (inline − workhorse) cost to parity at M, minus c_trig, the selected rule's measured per-boundary decision cost in dollars. "Pays at M" means the one-sided 95% lower bound of S(M) exceeds zero. N* = the smallest tested M that pays, with every larger tested M also paying.

| Result | Selected form | Trigger consequence |
|---|---|---|
| Pays down to M=1 | **T-C** (or T-B; harness picks the cheaper text) | Default-delegate bounded implementation to WORKHORSE; named exceptions only; no number |
| N* ∈ {2, 3, 5} | **T-E** with N = N* | Shape checklist plus "at least N* items" |
| Pays only at M ≥ 10 | **T-E** with N = 10 | **Spawn less than now**: small bounded units stay inline, against v1's count-free gates |
| Pays nowhere new, controls pass | **None** | Keep v1 text; add "not below 10 items"; report |
| Known-answer control fails | **None** | Instrument audit before any trigger change |

T-D is expected to fail the harness (two unobservable inputs, E and H, estimated per boundary); if its measured cost or flip rate crosses the pre-registered thresholds it is rejected regardless of the sweep's result. If it survives cheaply, that is information and it re-enters. T-F is rejected by default on concept economy — its extra input (a difficulty read) buys nothing demonstrated at L2, where no REBIND held — unless the owner funds Stage 3 and L1 shows the sweep seat winning by the materiality threshold. Tier: WORKHORSE everywhere the rule says spawn, unless the small-M sweep arm shows a sweep advantage with lower bound ≥ 15% of inline cost, confirmed; the existing SWEEP fan-out clause (one-rule scans) is untouched and untested here.

Input counts, static: T-A 1–2; T-B 3; T-C 3; T-D 2 estimates (not observable); T-E 4; T-F +1 judgment. All but T-D's are readable from the plan the agent already holds. The harness converts these counts into measured cost.

## 3. Design

**Variables (reused terms).** Host: Claude only. L: L2 (L1 in conditional Stage 3). M: {1, 2, 3, 5} new, {10} as control. Arms: inline, delegated-workhorse, delegated-sweep; delegated-same at M=1 only, as a control. R: blocks per cell, matched, one fixture per block shared by its arms. Contrasts: inline − workhorse (primary), workhorse − sweep (tier, secondary). Reading: discovery → candidate manifest → confirmation at 1 − 0.1/k. Repair protocol, receipts, access scan, seals, breaker: unchanged.

**Task and new axes, with build cost.**

- *Small-M draw (Stage 1a):* assumed a generator parameter (it drew 10/40/160); validation only. At M=1 the dependent chain degenerates to a single edit — acceptable and disclosed, since one item is exactly the trigger's smallest case; M=2–5 keep the chain.
- *Trigger-cost harness (Stage 1b):* new, ~1 day. Seven rule texts (T-A..T-F plus a null rule "always inline") × 15 boundary scenarios × 3 repeats, run on the parent seat as decision-only calls. Scenarios: 8 drawn from fixture briefs across M = 1..160, 4 from mined SpawnGate-record shapes, 3 adversarial (ambiguous count; live-context flavor; verification-repeats-reasoning flavor). Each scenario carries an author-labeled intended decision per form, written before any run and held out of the prompt. Marginal cost = tokens under rule text minus tokens under the null text, paired per scenario. Flip rate = fraction of scenario × rule triples whose decision differs across repeats.
- *Split-spec context axis (Stage 2, conditional):* new generator variant, ~1–2 days: K of M item specs live only in parent-visible material, so the brief must carry them; the access scan is extended to catch a child reading the parent-only spec directly.
- *L1 rung (Stage 3, conditional):* defined but not built; ~1 day.

**Treatment matrix.**

| Stage | Cells | Arms | R |
|---|---|---|---|
| 1a discovery | M ∈ {1,2,3,5} × L2 × Claude | inline, workhorse, sweep | 10 |
| 1a controls | M=1: delegated-same; M=10: inline, workhorse | as named | 5 |
| 1b harness | 15 scenarios | 7 rule texts | 3 repeats |
| Confirmation | boundary cell(s) from manifest | inline, workhorse | 5 fresh |
| 2 (conditional) | M=10 × K ∈ {3, 7} | inline, workhorse | 10 |
| 3 (conditional) | L1 × M=10 | workhorse, sweep | 10 |

**Staging and what each stage decides alone.** Stage 1a and 1b run in parallel; they share nothing. 1a alone decides count-free vs count-bearing (rows 1–3 of the decision table). 1b alone can reject a form on cost or instability, and picks the phrasing among forms the sweep leaves standing — including between T-B and T-C, which have near-identical extensions but possibly different evaluation costs. Confirmation runs only the boundary cell N* and its nearest non-paying neighbor. Stage 2 runs only if a T-C/T-E form is selected: it decides whether "needs live context" stays a named exception (delegation stops paying, or parity fails, at low K) or is dropped because brief-writing absorbs the transfer cheaply — one fewer input if dropped. Stage 3 runs only on owner opt-in.

**Sample-size rule.** R=10 per discovery cell (the M=10 discovery separated arms cleanly at n=14–15; small-M deltas are smaller, so R=10 with paired blocks; if the bound straddles zero at R=10, stop and report rather than extend — extension past declared R needs approval). Controls R=5. Confirmation R=5 fresh blocks at 1 − 0.1/k, k = confirmed contrasts. Exactly-R completeness with surplus disclosure, as the reader already enforces.

**Controls, including known-opposite.**

1. *Known-answer:* M=10 inline vs workhorse, R=5, must reproduce the −19% direction with a lower bound above zero before any small-M cell is read. Agreement with expectation is exactly when the instrument gets tested.
2. *Known-opposite:* delegated-same at M=1 must **lose** to inline — the ~$0.3 fixed spawn overhead against ~$0.07 of work. If it wins, the cost model or runner is broken; nothing else is read.
3. *Harness null rule:* "always inline" must show ~zero marginal tokens and zero flips. *Harness positive-cost control:* T-D's arithmetic must show measurably higher cost than T-B — proving the harness can see a difference before its verdicts are trusted.
4. *Empty-subject guard:* every cell asserts its run count before any bound is computed (reader's completeness check); a bound over zero blocks is NOT RUN, not clean.
5. Existing: access scan per run, seals, 271-check self-test, revert proofs.

**Pre-registered thresholds.**

- Pays at M: one-sided 95% lower bound of S(M) > 0; confirmation at 1 − 0.1/k.
- c_trig conversion: the harness's own measured dollars per marginal token at the parent seat.
- Rule rejection: median marginal decision cost > 300 tokens per boundary, or flip rate > 10%. Derivation: at an assumed 20 boundaries per session, decision spend must stay well under one small spawn's saving (~$0.14–0.24), or the trigger eats its own benefit — the owner's premise made numeric.
- Tier materiality: sweep replaces workhorse in the trigger only if its advantage has a confirmed lower bound ≥ 15% of inline cost at the relevant M.
- Non-monotone S(M) across adjacent M: stop the read; owner reviews rather than the reader auto-picking N*.

## 4. Budget and stop rules

| Stage | Runs / calls | Est. cost | Wall-clock |
|---|---|---|---|
| 1a discovery + controls | ~135 runs | $50–60 | ~4–5 h |
| 1b harness | ~315 decision calls | $10–20 | ~1–2 h |
| Confirmation | 10–20 runs | ~$10 | ~1 h |
| 2 (conditional) | 40 runs | ~$30 + 1–2 d build | ~2 h |
| 3 (conditional) | 20 runs | ~$12 + 1 d build | ~1 h |

Per-M-cell cost (~$11 at 3 arms × R=10) sits inside the approved $18–25. **Ceiling: $150 total**; any stage projecting past its estimate × 1.5 stops for approval. Stops: two consecutive failed dispatches (existing breaker); known-answer or known-opposite control failing its direction stops the stage before any new cell is read; per-cell cost > $25 stops that cell; bounds straddling zero at declared R stop rather than extend.

## 5. What this cannot answer

- **Quality-driven gates.** Independence and escalation spawn to catch errors and break ties; a cost-to-parity experiment on a family where quality never separated (302/302 at level 0) cannot price a caught error. Those gates keep their v1 wording untouched.
- **Fan-out.** M independent items with parallel children (X-6) is excluded; the parallelism clause ships unvalidated.
- **Residual context.** Stage 2 measures the *briefing cost* of parent-held information, not the value of context displacement to the parent's remaining work.
- **One host.** Codex is excluded (sweep-seat oracle reads voided 37.5% of runs). The trigger text ships host-neutral on one host's evidence, disclosed.
- **One family, L2.** Generalization beyond bounded-edit chains is assumption; L3, where quality might finally separate seats, stays unbuilt unless Stage 3 expands.
- **Boundary detection.** The cost of noticing a work-unit boundary is identical across forms and unmeasured.
- **Accepted confound, named:** inline vs workhorse merges routing and seat; that is the deployed decision's shape, so it is embraced, not controlled away.

## 6. Decisions for the owner

1. **Ceiling $150 for Stages 1 + confirmation, conditional 2–3 inside it.** Default: approve. Alternative: cap at $90 (Stage 1 + confirmation only), deciding count-free vs count-bearing but leaving the live-context exception judged, not measured.
2. **Stage 2 (context axis) if T-C/T-E is selected.** Default: run — it can delete one input from the shipped rule, and exception-list length is the rule's cost forever. Skipping keeps the exception on judgment.
3. **Stage 3 (L1 tier read).** Default: skip; tier collapses to WORKHORSE, and T-F dies on concept economy. Running it (~$12 + 1 day) could hand mechanical rungs to the sweep seat for a further ~10% per delegated unit.
4. **Fan-out stage later.** Default: defer; the parallelism clause stays as-is with a dated "unvalidated" note.
5. **Ship on one host's evidence.** Default: yes, with the disclosure; the alternative — rebuilding Codex cells around the oracle-reading sweep seat — costs more than the wording decision warrants now.

## 7. Assumptions

- The fixture generator's M is a free parameter down to 1; only the inter-item chain degenerates at M=1.
- Small-M runs cost roughly proportionally less, with a per-run floor near $0.10.
- Modelled ledger prices and the git pin hold across all stages.
- Boundaries per session ≈ 20, taken from SpawnGate records and transcripts; used only to justify the 300-token threshold, disclosed as rough.
- The Claude OAuth seat stays available; the breaker covers revocation as before.
- Prior discovery M=10 figures are valid known-answer references at this pin.
- Decision-only harness calls on the parent seat are billable and measurable through the existing cost accounting.
