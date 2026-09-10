---
created_at: 2026-09-03T23:20:00+09:00
head: a477bcc
kind: review
---

# Tier-economics experiment design — review round 1

Target: `2026-09-03T2215--a477bcc--tier-economics-write-experiment.md` at sha256 `c41669f13cb1`
(the revision after the official-doc cross-check was folded in). Criterion: **AI workbench /
harness** — a defect is a signal that would look true and be false. Packet:
`…-review-packet.md` beside this file; it bundled the two prior measurement records, the two
spawn-target definitions, and the harness parser excerpt.

## Who reviewed, and what that bought

| Seat | Isolation | Receipt | Participation | Findings | Cost |
| --- | --- | --- | --- | --- | --- |
| `gpt-5.6-sol` / max | `codex-run.sh --profile hermetic` — fresh CODEX_HOME, no AGENTS.md, read-only, `--output-schema` | `…-codex-receipt.json`: packet sha `188de666…` = disk, result sha recorded, exit 0 | R1–R6 all checked | 22 | modelled only (OAuth) |
| `claude-fable-5` / max | `claude -p --setting-sources ''` — corpus stripped, plan mode | `modelUsage` keys `claude-fable-5` (+ host-internal haiku) | R1–R6 all checked | 16 | $5.93 measured |

Cross-family is the top rung of the independence ladder; the second seat is a different
model of the author's family with the shared corpus removed. Every anchor quote from both
reviewers was found verbatim in the target (38/38), so no finding rests on a fabricated
line. Both echoed the target hash.

## Disposition

Accepted 37, narrowed 3, rejected 0. Two reviewers reaching the same defect independently
is the strongest signal this round produced; those are listed first.

### Found by both (11)

| Defect | Claude | Codex | Severity |
| --- | --- | --- | --- |
| A delegated run's cost omits every child: Codex child usage lives in the child rollout, not the parent's `exec --json` stream. No control sums parent+child. | #1 | #3 | blocker ×2 |
| KEEP threshold has no sample-size qualifier while DELETE does; fires on Stage-1 screen data the design itself disavows. | #2 | #16 | blocker ×2 |
| "Any cell" over tens of cells — one crosses 25% under the null. | #6 | #17 | high / blocker |
| Excluding above-cliff runs removes inline's expensive runs only; inline looks cheaper; false DELETE. | #7 | #21 | high ×2 |
| `sweep` is read-only by definition; write cells cannot decide its fate. | #8 | #4 | high / blocker |
| Known-bad probe is one-sided: a checker that fails everything passes it. | #10 | #9 | high / blocker |
| The main's model+effort is unpinned; thinking is 57% of output and moves with effort. | #11 | #1 | high ×2 |
| "Zero items = instrument failure" erases a genuine 0-for-N quality result. | #14 | #11 | medium / high |
| Five-kind field mapping is never proven to exist per host before the null rule applies. | #13 | #12 | medium / blocker |
| "An effect absent on Codex is absent everywhere" — the fork arms' mechanism is host-specific. | #5 | #20 | high / blocker |
| Claude fork arm names no mechanism; the bundled record and the design disagree on whether one exists. | #15 | #15 | medium / high — **narrowed** |

### Codex only (11)

- **#2 blocker — attribution.** Cheap-vs-inline confounds the seat with the routing mechanism (shorter child context, no prior-turn thinking, fan-out reuse). A same-model isolated spawn is the control; the seat effect is cheap-vs-delegated-same.
- **#5 high** — "write-dominated" is asserted; make output dominance a measured cell-validity gate.
- **#6 medium** — sol/luna ratio is 20× on input and cache kinds, 16.7× on output; the staging rationale used the smaller one.
- **#7 blocker** — `N` names both items-per-run and repetitions; and `items_attempted` echoed ≠ identity-set equality.
- **#8 high** — no pre-registered estimator; ratio-of-means and mean-of-ratios give 50% vs 10.8% on the same runs.
- **#10 high** — an equivalent mutant blocks all cells; admit mutants only via an independent oracle.
- **#13 high** — sequential arms share a warm prefix; a fresh suffix is not a fresh cache.
- **#14 blocker** — the Codex cache-key control passes on the standing prefix; needs a parent-only run-unique canary.
- **#18 blocker** — DELETE on point estimates ≤20% is not evidence of absence; needs the upper bound.
- **#19 high** — the DELETE predicate quantifies over mid and fork arms, which carry no evidence about cheap seats.
- **#22 medium — narrowed.** Claims the 60-file sweep cell was N=5. The record says both: §2 "the pinned cells are N=5", Limits "the four load-bearing cells are N=5; every other cell … N=2". Raw runs do not survive. Held as ambiguous in the design rather than resolved either way.

### Claude only (5)

- **#3 high** — control 1 on Codex checks the rate table against itself.
- **#4 high** — Σ(kinds×rates) is never reconciled with a measured `total_cost_usd`; Claude, the only billed host, enters last.
- **#9 high** — topology (children per run, concurrency, copies per item) is a hidden axis as large as the seat axis.
- **#12 medium** — "Claude 5×" is opus→haiku; the table's top seat gives 10×.
- **#16 detected_miss** — Stage 0 (a) has no pass criterion for a pure measurement.

### Narrowed

- Both #15: the fork mechanism does exist on Claude Code (official sub-agents doc, fetched
  2026-09-03: a fork "inherits … model, and prompt cache"); Bundle 1's "there is no subagent
  fork" was measured against a nonexistent `subagent_type: "fork"`. The finding survives as:
  name the invocation per host and require an inheritance receipt. Exclusion of a cheap fork
  on Claude stands on "inherits model", not on unavailability.
- Codex #22 as above.

## What the round says about the design

Three of the design's own safeguards were the sources of false signals: the cliff
*exclusion* (biases inline), the zero-items *rule* (erases quality failures), and the
parent-stream *parser* (erases children). Two more were one-sided (known-bad without
known-good; DELETE on point estimates). The reviewers did not disagree with the question;
they disagreed with the instrument. Round 2 should re-review the rewritten design at its new
hash before Stage 0 is built.
