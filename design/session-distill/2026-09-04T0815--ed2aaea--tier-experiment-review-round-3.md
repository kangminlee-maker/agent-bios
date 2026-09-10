---
created_at: 2026-09-04T08:15:00+09:00
head: ed2aaea
kind: review
---

# Tier-economics experiment design — review round 3

Target: `2026-09-03T2215--a477bcc--tier-economics-write-experiment.md` at sha256
`1d40701ca97d` (revision 3, the revision after round 2). Criterion: **AI workbench /
harness** — a defect is a signal that would look true and be false. Packet:
`…-review-packet.md` beside this file (sha256 `60218af2…`); it bundled revision 3, the two
prior measurement records, the two spawn-target definitions **and the launch config's tier
bindings on both hosts** (round 2 could not see the Codex binding), the harness parser
excerpt, and both prior round records, and asked each finding to carry a provenance —
*caused* by revision 3's changes, *surfaced* by them, or *pre-existing*. The packet told
both seats that round 2 had run on one seat and that its dispositions were claims.

## Who reviewed, and what that bought

| Seat | Isolation | Receipt | Participation | Findings | Cost |
| --- | --- | --- | --- | --- | --- |
| `gpt-5.6-sol` / max | `codex-run.sh --profile hermetic` — fresh CODEX_HOME, no AGENTS.md, read-only, `--output-schema` | `…-codex-receipt.json`: packet sha `60218af2…` = disk, result sha recorded, exit 0, 83,767 tokens | R1–R6 all checked | 17 | modelled only (OAuth) |
| `claude-fable-5` / max | `claude -p --setting-sources ''` — corpus stripped, plan mode | `…-claude-wrapper.json`: `modelUsage` keys `claude-fable-5` (+ host-internal haiku), 130,141 output tokens of which 120,336 thinking | R1–R6 all checked (R5 nothing found) | 9 | $9.73 measured |

The Claude seat ran after the operator re-logged in; the machine's stored credential had
been unusable to new processes since 00:33 KST (round-2 record). Its verdict came back
in two text blocks and the CLI's `result` field carried only the second, so the JSON was
recovered from the session transcript and parsed leniently (one raw control character
inside a string); the recovered document echoes the target hash and satisfies the schema.
`…-claude-fable5.json` is that recovered document; the wrapper is kept beside it as the
seat and cost receipt.

Cross-family is the top rung of the independence ladder; the second seat is a different
model of the author's family with the shared corpus removed. Every anchor quote from both
reviewers was found verbatim in the target (26/26). Both echoed the target hash.

## Disposition

Accepted 26, narrowed 3, rejected 0.

Provenance, as classified by the reviewers: **caused 13 · surfaced 7 · pre-existing 6.**
Thirteen of twenty-six were caused by revision 3's repairs — the highest share of any
round. Four defects were reached by both seats independently; those are listed first.

### Found by both (4)

| Codex | Claude | Finding | Revision 4 |
| --- | --- | --- | --- |
| #1 blocker | #5 medium | `delegated-shipped` resolved "at the run's HEAD" — a cell can pool two bindings, and confirmation can confirm a different seat than discovery searched | One experiment pin: HEAD, launch-config hash, agent-definition hashes frozen at Stage 0; a run whose resolved binding differs is a control failure |
| #3 high | #4 high | The matrix pins seat, mechanism, packet — not the child's agent body; the workhorse body changes behaviour ("escalate … instead of resolving") so part of the contrast is the body's | Every isolated delegated arm runs the identical workhorse body; body hash in the pin and in every participant's receipt; delegated-same is that body pinned to the parent's seat |
| #6, #7 high | #1 high | The eligibility label: a median of per-run shares lets cheap runs outvote expensive ones (Codex); measured per arm, the arm that saves thinking disqualifies itself by succeeding (Claude) | Eligibility is a property of the cell, from the comparator alone, as a ratio of sums priced per participant; arm shares reported beside the verdict; claims scoped to observed blocks |
| #12, #13, #14 blocker | #2 high, #8 medium | DELETE could fire from attribution alone, globally over a partially empty host family, without confirmation, on a dependent-only topology, and a Stage-1 screen could prune a host out of the family | Every verdict per host; DELETE renamed NO SEAT EFFECT with a scoped consequence, a minimum eligible family, and confirmation like every other verdict; the screen gates nothing; inline published beside every verdict |

### Codex only (10)

| # | Sev | Prov | Finding | Revision 4 |
| --- | --- | --- | --- | --- |
| 2 | blocker | caused | Claude retention differs by effort alone and the parser receipts only the model — both arms at one effort would report a contrast that never ran | Control 4 receipts model, effort, and body from the child's own artifact; Stage 0 plants an effort-only swap that must fail by name |
| 4 | high | surfaced | The cache receipt accepts anything from zero to the full prefix, so one arm cold and the other warm passes | Common-warm regime: uncounted priming per seat per block, then an equality band (±10% of the seat's Stage-0 prefix) on every run's first request |
| 5 | high | caused | The output-priced share used a single output rate over mixed-seat runs, against the estimator's own rule | Share priced per participant and per request, same formula as cost; mixed-seat golden crossing 40% under aggregate-before-pricing |
| 8 | blocker | caused | `input = uncached + read` omits both cache-write buckets, so omitting or double-pricing cache write passes conservation | Per-vendor partition written out; `cache_creation = 5m + 1h`, `context = uncached + read + write`; rates declared full prices not surcharges; goldens carry exact dollar totals; Codex subset relations established from Stage-0 receipts |
| 9 | high | pre-existing | ±3% reconciliation on each arm spans the 20/25 band, so the modelled estimator can cross where the bill does not | Claude's decisive run cost is measured `total_cost_usd`; a crossing within 3% is reported "at the tolerance" |
| 10 | blocker | pre-existing | Control 7 plants only a mutation of the item's own assertion; a fix that breaks out-of-scope behaviour scores as a pass | Second planted mutation per item that preserves the item and breaks the protected behaviour; the named regression assertion must fire |
| 11 | high | surfaced | `saving` has a registered sign; the pass-rate difference has none | `quality_difference(arm, ref) = pass_rate_arm − pass_rate_ref` registered with its ratio-of-sums pass rate |
| 15 | high | pre-existing | Three sizes, no interpolation rule, a verdict phrased for bounded work generally | Every verdict scoped to M ∈ {10, 40, 160}; "between which tested sizes" is the only frontier claim |
| 16 | high | surfaced | Two unadjusted 90% crossings leave ~16% family-wide false KEEP over 18 cells | *Narrowed*: confirmation at 1 − 0.1/k over the k candidates carried, plus a pre-designated primary cell per host, rather than a full family-wise sequential procedure |
| 17 | blocker | caused | An R=5 percentile bootstrap cannot see an undrawn tail; a 5×-cost-one-in-ten arm confirms a false 40% saving a third of the time | *Narrowed*: R=5 is a floor; per-cell R set before Stage 2 by a pre-registered rule from Stage-1 spread (5–15); a tail rule extends a cell by 5 blocks; not a coverage analysis |

### Claude only (5)

| # | Sev | Prov | Finding | Revision 4 |
| --- | --- | --- | --- | --- |
| 3 | high | caused | REBIND compared the candidate to the parent's seat only; a candidate strictly dominated by the shipped binding on cost and quality could still be named | REBIND requires clearing the incumbent too: `saving(candidate, shipped)` ≥25% and `quality_difference(candidate, shipped)` ≥ −Δ, confirmed |
| 6 | medium | surfaced | On Codex, control 0 conserved participant *count* only; a truncated child rollout publishes with a green receipt | Every child artifact must be complete — terminal record present, per-turn sum equal to its cumulative — and a cut-before-terminal probe is a planted case |
| 7 | medium | surfaced | The under-cliff secondary estimand cannot exist at M=160 under a whole-block reading and had no replenishment cap | Per compared pair, cap of 2R attempts, published as unavailable when the cap is reached |
| 8 | medium | pre-existing | Stage-1 "spread" was no statistic, and the screen's consequence was unstated while "Claude runs regardless" implied it could prune Codex | Statistic registered (SD of delegated-same over R=3); the bit gates nothing; Stage 2 runs every cell on fresh blocks |
| 9 | medium | pre-existing | "A scan's bill is dominated by reading the same files at any seat" contradicts the rate table two sentences later; the prior null came from delegation's fixed costs | Mechanism sentence rewritten to attribute the null to corpus injection, brief, warm-up, and unpinned escalation at the measured sizes |

### Narrowed

- **Codex #7** (eligibility as an unbounded R=5 classifier) — the endpoint is not bounded;
  the verdict's scope sentence names the observed share and claims nothing about a
  population. Bounding a gate on a gate would double the confirmation cost for a label
  whose threshold is itself a proposal.
- **Codex #16** (family-wise procedure) — a Bonferroni-style adjustment at confirmation
  plus one primary cell per host, rather than a sequential family-wise design. It is
  executable from the text; a fuller procedure is the statistician's to choose when the
  numbers are reviewed as numbers.
- **Codex #17** (tail-aware power analysis before running) — R is set by a rule from
  Stage-1 spread and extended on tail events. A coverage analysis needs a distribution
  the experiment has not observed; the rule is written before the data and can be wrong
  in a way the record will show.

## What the round says about the design

- **The repairs are the subjects again, at a higher share.** 13 of 26 caused by revision
  3, after 6 of 15 caused by revision 2. Each round's fixes are the next round's
  findings, and the findings have moved from the instrument (round 1) to the safeguards
  (round 2) to the statistics and the verdict semantics (round 3). The count is not
  converging: 38 → 15 → 26.
- **Both seats found the verdict semantics broken in the same places** — the binding
  pin, the agent body, the eligibility label, DELETE's reach. Two families agreeing on a
  design-level defect is the strongest signal a round can produce, and it landed on the
  part of the design that decides, not the part that measures.
- **The Claude seat's eligibility finding is the round's sharpest**: an effort reduction
  cuts thinking, thinking is output-priced, so the arm that saves is relabelled
  "not output-dominated" and barred from the predicate that would have found the saving.
  A safeguard that disqualifies the effect it guards is the criterion's definition of a
  false signal, and it was introduced by round 2's own repair.
- **Recommendation to the operator: stop reviewing the text and build Stage 0.** The
  remaining defect classes — statistics, verdict semantics — are the ones a fourth
  reading will keep finding at a constant rate, and the ones a running harness with
  planted failures shows for the price of a run. Two numbers are the operator's before
  Stage 0 starts: Δ (5 or 0) and whether the R rule's 5–15 range is affordable.
