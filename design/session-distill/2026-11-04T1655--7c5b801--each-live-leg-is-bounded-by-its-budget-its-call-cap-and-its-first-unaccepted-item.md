---
created_at: 2026-11-04T16:55:00+09:00
head: 7c5b801
kind: design
supersedes: null
---

# Each live leg is bounded by its budget, its call cap and its first unaccepted item

WP-08 commit 7, second part: how the live legs run, fixed before their first call. The fixtures are commit 7c5b801's
`stage_read.fx_live_legs`. The runner is a work-directory script, not committed.

The owner's answer of 2026-11-04 is D-20261104-6439cc:
- a retry margin of four calls, one per leg;
- DW5 asked again after plan A's measurements.

The lead then set the caps: DW2 5, DW3 apart 7, DW3 twin 6, C1 7, so 25 calls for the legs. With the six calls of the
re-pin, WP-08 makes at most 31. Every token the legs spend comes out of what the owner left: input 350k and output 90k
for WP-08 in all, less what the re-pin spent.

## The declarations

Every leg's run declares the same S3 settings:
- seat `claude:claude-sonnet-5-5/high`, host 2.1.317;
- the measured hermetic allowance 3,795 with the pinned flag-set hash;
- output cap 32,000 and per-call token cap 200,000;
- kind `periodic`.

| Leg | Declared S3 budget | Call cap | Calls needed | High estimate, needed / with one retry |
| --- | --- | --- | --- | --- |
| dw2 | 56,000 | 5 | 3 | 31.0k / 43.3k |
| apart | 121,000 | 7 | 6 | 87.4k / 103.8k |
| twin | 102,000 | 6 | 5 | 69.8k / 85.4k |
| c1 | set after the three legs, from their measurements | 7 | 3-6 | about 97k without an expansion |

- **The token model.** The estimates use ⑦'s model: per call, the host's 2,000 tokens plus the driver bytes at 2.3
  bytes a token. Output is put at 3,000 tokens per fixture window or expansion and 2,000 per stitch.
- **Why the budget is larger than the estimate.** The dispatcher admits a call only when the stage's spend plus the
  call's reservation fits the budget. A reservation is twice the largest measured call of its class in the run, and
  6,432 before the first. So a budget equal to the high estimate would refuse the retry the owner granted. Each budget
  is the smallest that admits the leg's needed calls and one retry at the high estimate. The budget counts input,
  cache and output together.
- **C1's budget.** It is fixed after the three fixture legs, from what they measured per call. It is set so that
  everything spent in WP-08 stays inside the owner's limit. If its one clipped record were expanded at the largest part
  the driver admits (116,205 bytes), the high estimate would be about 155k.

## What stops a leg in code

- **Its budget.** A call that does not fit is `BUDGET_EXHAUSTED`, and its item is recorded `not_done`.
- **The call cap.** Every reservation is counted, and the one past the cap is refused before anything is dispatched
  (`LEG_CAP_REACHED`). A reservation refused before dispatch still counts, so the cap bounds host calls from above.
- **Its first item that ends other than accepted** (`LEG_ENDED`). An item can end failed after its retry, deferred,
  stopped or not done. The leg's unit can then no longer be read whole, so the done-when cannot be met in that run, and
  no further call is spent on it.
  - A dry run of the apart leg showed the difference. With a runner that answers nothing, it spent its whole cap of 7
    on failing windows. With `LEG_ENDED` it stopped after the first window's two attempts.
  - The lead approved the rule on 2026-11-04 (D-20261104-72bf04).

Every call is serial. No S3 class has a measured call in a new run, so S3 runs as a calibration tranche.

## The order, and when it stops for the lead

The order is DW2, apart, twin, then C1.
- The run pauses for the lead after DW2, whose measured calls re-check the remaining budgets.
- It pauses again before C1, whose budget the lead confirms.
- Apart or twin stops and is reported instead of going on to the next leg if any of these happens:
  - it goes past the high estimate;
  - it ends by `LEG_ENDED`, `LEG_CAP_REACHED` or `BUDGET_EXHAUSTED`;
  - the Claude version changes.

## Checked before the first call, and around every leg

1. **The tree.** It is at the commit holding the fixtures. No other hook or umbrella runs, and the worktree is not
   edited while a leg runs.
2. **The version.** The versioned file `~/.local/share/claude/versions/2.1.317` is a regular file, and its
   `--version` prints 2.1.317, before and after every leg. A change discards that leg's measurement, and the lead is
   told first.
3. **The token file.** It exists with mode 600 and reaches `claude-run` as `CLAUDE_RUN_TOKEN_FILE`, a path. Nothing
   opens it.
4. **The declaration.** The runner prints the declaration it amended, and it matches the table.
5. **The directories.** Each leg uses a new run directory and a new cell root under `/private/tmp`, both mode 700. A
   leg refuses to start over either.
6. **The real roots.** Their names are listed before and after each leg. The three agent-bios roots must be equal.
7. **C1's content.** C1 reads the owner's sessions, and their claims and quotes are stored in its run directory, which
   is mode 700. Logs and messages carry counts, bytes, tokens and codes, never a body.

A dry run of each fixture leg passed, with a runner that prints its argv and starts no host. It went through the
declaration's amendment, the reservation, the seat's admission and the runner's argv. The version was 2.1.317 before
and after, and the real roots were equal.

## Done-when 3's carried pending event, until S12 exists

Done-when 3 asks that `coverage.json` carry the twin's pending event forward for the next run's stitch.
- S3 folds its hand-back into the coverage state with `census.reconcile` under the run's kind, and writes nothing of
  it. S12, not yet built, is to write `coverage.json`.
- Until S12 exists, the carry is seen in the result of S3's fold. The twin runs `periodic` inside its own fixture run
  directory, and the runner repeats S3's fold from what S3 wrote. It prints the pending events before and after the
  fold, as ids, first records and windows.
- The real coverage state is not touched.
- On the golden twin the fold carries the cause's event, at first record 0 in the run's window.
