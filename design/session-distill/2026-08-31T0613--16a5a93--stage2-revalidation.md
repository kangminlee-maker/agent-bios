---
created_at: 2026-08-31T06:13:18+09:00
head: 16a5a93
branch: main
kind: review
supersedes: —
---

# Before spending Stage 2: the pre-registered falsifier is satisfied on the data, and the approved budget is 2.6× the figure that was quoted

This re-derives the initiative's purpose and plan from the code and the stored receipts,
because Stage 1 is finished and Stage 2 is the first expensive step. It decides nothing —
every number below is re-derivable, and the decision at the end is the owner's.

Re-derive (the Bash tool is zsh, so `$var` does not word-split — spell the ids out):

```bash
python3 benchmarks/compare.py --control benchmarks/out/c1-control \
    --ablated benchmarks/out/c1-ablated --category security
python3 benchmarks/compare.py --control benchmarks/out/c1-control \
    --ablated benchmarks/out/c6-ablated --category security
python3 benchmarks/compare.py --control benchmarks/out/c1-control \
    --control benchmarks/out/c6rw-control-strengthen --ablated benchmarks/out/c6stub-arm \
    --scenarios sec-session sec-admin-auth sec-ratelimit sec-pwlen sec-lockout sec-control-strengthen
```

## 1. What still holds

The populations are real and derivable. The 13 "absent" items are exactly the 13 ledger rows
carrying `D-20260826-b2a39a`. The class assignment in the Claude draft is a clean partition of
the 107 placed rows — 40 D / 30 T / 17 F / 8 absorbed / 8 P / 3 M / 1 uncovered, no duplicate,
no stray, no gap. `claude/CLAUDE.md` is 20,235 characters (~5.1K tokens), matching the design's
baseline, and **no commit has touched it since `cfbfd55`**. The instrument is in better shape
than when the design was written: twelve review findings closed, C2 passing.

## 2. The pre-registered falsifier is satisfied on the data

§5 registers the condition in advance:

> C1 regresses and C6 does not → the trigger/action asymmetry is falsified for that bullet and
> R2 fires.

Re-derived from the stored receipts:

| arm | what it removes | result |
| --- | --- | --- |
| `c1-security-posture` | the whole rule | 4 of 5 security scenarios 4/4 → 0/4, **both hosts** |
| `c6-security-trigger` | the trigger, action kept | claude 0 regressions, codex 1 (`sec-session`); the two scenarios the pre-registration named, `sec-pwlen` and `sec-lockout`, are 4/4 → 4/4 |
| `c6-action-stub` | the action, trigger kept verbatim | `sec-session` and `sec-ratelimit` **regress on both hosts** |
| `c6-rewrite` | trigger rewritten neutrally | every ablated scenario **held**; the hardening control `sec-control-strengthen` collapsed 4/4 → 0/4 on both hosts |
| `c6-drop-consequence` | `state the consequence and` | nothing moved, either host |

So the registered condition is met: C1 regresses, C6 does not. The arm was instead declared
VOID (`D-20260826-b339c7`) on the ground that the deletion did not isolate the trigger — the
surviving action still says "do not apply THE WEAKENING", naming it, and the remainder grafts
onto the parent bullet's trigger. That reasoning is documented in `ablations.py` and it is
substantive. It is also the single shape that most deserves an outside reading: **a
pre-registered falsifying control ruled invalid after it returned the falsifying pattern.**

The two replacement arms do not rescue the thesis's cheap form; they point the same way as the
voided one. Stubbing the ACTION regressed two scenarios on both hosts. Neutralising the
TRIGGER regressed none of them. On the only bullet ever measured, the action was load-bearing
and the trigger's *presence* was not — the inverse of "the action derives, the trigger does
not". What survives is narrower: the trigger's *direction* is not derivable, which rests
entirely on the over-trigger of the hardening control.

That bullet is also the one §4's last line calls **untouchable regardless of test outcome**.
About 200 dispatches have therefore yielded zero compressible tokens and one four-word clause
shown droppable.

## 3. The approved budget is 2.6× the figure decision 3 quotes

§5 and owner decision 7 both state Population 1 as **≈1,760 responses** (55 arm-variants × 4
scenarios × 2 hosts × N=4) and 84 scenarios to author. Decision 3 — the budget the owner chose
from — still reads "~670 runs ≈ 8–9 h wall + ~42 scenarios to author", which is the earlier
2-arm, 2-scenario framing (21 × 2 × 2 × 4 × 2 = 672). The two defaults the owner actually
selected (N=4 both hosts, and 4 scenarios per item) multiply to 1,760, not 670.

Wall clock scales with it: not 8–9 hours but the better part of a day, before Population 2 (the
40 audited bullets) is measured at all on the same design.

## 4. What the protocol cannot report

`compare.py` computes `fell = before - after >= drop`; its verdict vocabulary is REGRESSED or
"-". §5's rules are one-directional throughout. **No arm can report an improvement.** The
protocol prices removing text only as damage.

The rule the initiative serves prices it the other way: `AGENTS.md` §8 justifies the global
budget by **dilution** — "each added bullet dilutes every other rule" — a cross-rule effect no
scenario touches. The money case is separately thin: the design's payoff is "5.1K → ~4.4K
tokens (−12–15%) … (inference; measure with `session-cost.py`)", self-labelled as inference and
never measured, while that tool's own docstring measures cache read+write at 92–94% of session
cost. So the best available outcome of the compression half is "this text may be deleted",
never "deleting it helped".

## 5. The two halves have different value

§5 splits Stage 2 into two questions, and they no longer carry the same weight.

- **2a — reach.** 13 absent items, arms *current* vs *restored*: does a rule still fire when it
  lives only in a router-gated guide? This is a defect question about text already shipped. It
  survives the compression thesis being abandoned outright, and the August audit's 21
  TRIGGER_GAP findings of 40 bullets is the reason to ask it. Marginal cost is the *restored*
  arm for 13 items — 13 of the 55 arm-variants.
- **2b — derivability.** All 21 items, *current* vs *ablated*. Its payoff is the unmeasured
  token figure; the evidence above points at the design's own R3 stop rule rather than away
  from it.

§1 already records that the guide split is settled on size alone, independent of derivability.
The largest structural win is therefore not gated by this experiment at all.

## The open decision

Not taken here. The options, in the design's own terms:

- **A** — run Stage 2 as designed (55 arm-variants, ≈1,760 responses).
- **B** — run 2a only; defer 2b.
- **C** — run 2b only; defer reach.
- **D** — stop the experiment; keep the guide split and the ledger correction, which are
  already decoupled.

Whichever is chosen, two repairs stand on their own: decision 3's budget line contradicts §5
and should carry the 1,760 figure, and if the initiative's justification is dilution then the
protocol needs an arm that can observe it.

An independent cross-family reading of this question was dispatched twice. The first seat
failed on usage credits without producing a report; the second re-derived the same arm
verdicts, the same budget discrepancy, and the same absence of an improvement arm, and its
verdict line did not survive transport. **Treat the corroboration as partial** — the numbers
above are re-derivable, the reading of them is one session's.
