---
created_at: 2026-11-04T09:34:00+09:00
head: 1d2ef28
kind: design
supersedes: null
---

# The live legs' fixtures view the main session alone and are held golden to their calls

WP-08 commit 7, first part: the fixtures its live legs read. No model call and no network were made for this commit.
The legs themselves, the live runner and C1's S3 come after the lead confirms them.

The lead chose plan A on 2026-11-04 (D-20261104-32c139):
- the fixtures run main-only;
- done-when 2 gets a minimal session;
- done-when 3's apart session and its twin each get their own run;
- then C1 over 2026-11-03 07:00-08:00 KST.

Each leg has a call cap: DW2 4, DW3 apart 6, DW3 twin 5, C1 6. A leg that reaches its cap stops and is reported to the
lead. The retry margin and the live DW5 leg wait for the owner's answer.

## What changed

- **`views.golden(main_only=, pending_at=)`.**
  - `main_only` leaves the child and the Codex session out of the census, so S2 views the main session alone.
  - `pending_at` is the first record of the pending event the planted coverage state carries on the main session;
    None plants none.
  - The defaults keep every existing golden run byte for byte as it was. The views, evidence, dispatch and stage_read
    self-tests pass unchanged.
- **`stage_read.fx_apart_records(outcome=, trailing=, turns=, steps=)`.** The defaults are the existing session.
- **New in `stage_read`:**
  - `fx_decisive_records` and `fx_decisive_log`: done-when 2's session.
  - `fx_decisive_answers`: its golden readings.
  - `fx_live_legs()`: the three fixtures as `views.golden` keyword arguments, which the live runner is to read.

## The legs, measured golden

These numbers come from S3 over each fixture with the golden fake host. The bytes are the driver's `bound.driver_bytes`
per call.

| Leg | Fixture | Calls | Driver bytes |
| --- | --- | --- | --- |
| dw2 | request, call, successful clipped result (middle holds the outcome), closing turn; pending event on the request | 1 window + 1 expansion + 1 stitch = 3 | 13,378 + 16,981 + 8,646 = 39,005 |
| apart | request, five turns of 170 steps, outcome turn | 5 windows + 1 stitch = 6 | 124,464 (max 26,203) + 9,943 = 134,407 |
| twin | the apart session without its fifth window's records | 4 windows + 1 stitch = 5 | 96,115 (max 24,461) + 9,110 = 105,225 |

At ⑦'s token model (input ≈ calls × 2,000 + bytes / 3.0, high at bytes / 2.3) these are about:
- dw2: 19k input (23k high);
- apart: 57k (70k);
- twin: 45k (56k).

The legs total about 121k (149k high). The DW2 leg is one call under its cap; apart and twin are at theirs. So a gate
retry in either DW3 leg is the owner's margin to grant, not the cap's.

## Why the shapes are what they are

- **Done-when 3 (D-20261104-f3f0e9).**
  - S2's cut depends on the turns' lengths and the overlaps around them, not on their count. Dropping only the trailing
    turn from the golden apart session cuts three windows, and the outcome lands in the third.
  - Over turns of 150-450 steps, two to four turns never gave five windows with the outcome last. Five turns of 160-180
    steps do, and 170 is the middle of that range.
  - The twin is the apart session without the records of its outcome's window. So its transcript holds no outcome
    turn; a live reader reads every record it is shown. Its four windows equal the apart leg's first four.
- **Done-when 2 (D-20261104-2e7c9c).**
  - S2 forces a clipped record only between a pending event of the coverage state and the next human turn
    (`views.forced_records`). An event the window records itself would force nothing.
  - So the fixture plants the event on the request, and the clipped result after it is forced.
  - The result is a successful one, and no line of it reads as an error. The clipper therefore keeps none of the
    middle, and the decisive line is shown only by the expansion.
  - The middle fits one expansion part.

## The controls

Four new stage_read controls, one per leg's shape and outcome:
- dw2 shape: the main session alone, no failed tool result, one window whose clipped result is forced by the carried
  pending event, and one window, one expansion and one stitch call (three call directories).
- dw2 outcome: the decisive line is in the expansion's packet and in no window's. The stitch resolves the carried event
  with the expansion's claim, its evidence on the clipped result's record, and the unit's result lists it resolved.
- apart: five windows; the cause in the first and the outcome in the fifth and last; five window calls and one stitch;
  the cause resolved by the outcome's claim.
- twin: the apart leg's first four windows and no record of the outcome; four window calls and one stitch; the cause
  unresolved and handed on as a pending event of the unit's result.

Each control was seen to fail by name, with a positive run first. Each mutation below was applied alone, to a copy of a
clone carrying this change:

| Mutation | Failed by name |
| --- | --- |
| `views.golden` ignores `main_only` | dw2 shape, apart, twin |
| the apart leg keeps its trailing turn | apart, twin |
| the twin keeps its outcome turn | twin |
| dw2's result is a failed one | dw2 shape |
| dw2 plants no pending event | dw2 shape, dw2 outcome |
| the decisive line also in the result's head | dw2 outcome |
| `pending_at` ignored (always record 4) | dw2 shape, dw2 outcome |

## What the live legs will need, not built here

- **The live runner.** It is a work-directory script. Each leg is its own run; its `budget.per_stage.S3` bounds the
  spend in code. The leg's call cap is checked before each call.
- **Done-when 3's coverage carry.** "`coverage.json` carries the carry-forward pending-events entry" comes from two
  steps:
  - S3 folds its hand-back into the state with `census.reconcile` under the run's kind, and writes nothing of it.
  - S12, not yet built, is to write it.
  - A targeted run's fold returns the state it was given (`coverage.apply_results`).

  So the twin leg's run kind decides whether S3's own fold shows the carried entry. The alternative is to fold the
  live hand-back as periodic afterwards, as the golden cross-run controls do. That is a question for the lead before
  the twin leg runs.
- **C1's declaration.** `account.extra_usage` is `off`, the owner's answer in the 2026-11-03 WP-08 decision set.
  `run.schema.json`'s `account` admits no basis field. So the basis is kept with the declaration tool and the C1 run's
  logs in the work directory.
