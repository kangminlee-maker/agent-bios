---
created_at: 2026-11-04T07:00:00+09:00
head: 3da448e
kind: design
supersedes: null
---

# S3 reads units side by side and leaves the bytes one at a time leaves

WP-08 commit 5b is the concurrency half of commit 5. The lead answered its question (Q6) on 2026-11-04:

- S3 reads its units in a pool of twelve.
- A calibration tranche reads one at a time.
- jobs=1 and jobs=12 must leave byte-identical stores, time fields aside.
- Every file several units write is either merged in a fixed order or written under a lock, and this record says
  which.

The resumability half, commit 5a, is recorded in
`2026-11-04T0505--ac74916--a-run-resumed-over-its-own-directory-answers-each-window-with-the-attempt-it-accepted.md`.

## run_items runs items `jobs` at a time under the same posture

`records.run_items(posture, items, work, jobs=1, stop=None)` keeps one-at-a-time behaviour for `jobs=1`. With `jobs`
above one it works as follows.

- **Sequences.** Items are split into sequences (`sharing_groups`). A sequence holds the items joined by a shared
  unit, route or test configuration, directly or through other items, in `items` order. Each sequence runs one item
  at a time, so production's quarantine of a failing item's sharers, and the skip of those not yet run, are exactly
  what they are one at a time. Sequences that share nothing run side by side on a ThreadPoolExecutor of `jobs`
  workers.
- **Stopping.** Under any posture but production, a failure sets `stop`, an event the caller may hold, and no item
  starts after it. Items already running finish. The failure named is the earliest one in `items` order.
- **Ordering and refusal.** `done` and the quarantine come back in `items` order. A `jobs` that is not a positive
  integer is refused (ITEMS_JOBS_INVALID).

The `concurrent.futures` import is declared in dispatch's `PROCESS_IMPORTS_DECLARED`. The pool runs threads, not
processes.

Controls in `records --self-test`, all `jobs:` controls:

- Production over the mixed batch four at a time equals one at a time.
- A sharer not yet run is skipped.
- The sequences are the joined items.
- The earliest failure is named. B and F each fail only once the other is running, so both failures are made.
- Nothing of the failing sequence runs after it.
- A failure lets no item start after it, in any sequence. Q1 waits on the caller's stop, so this is decided by the
  event, not by time.
- Twelve at a time runs twelve independent items at once and never a thirteenth.
  - The first twelve meet at a barrier that only twelve concurrent workers can pass.
  - The first thirteen try a thirteen-party barrier first. Twelve workers can only wait it out (2 s) until it breaks,
    and a thirteenth worker would let it pass.
- Bad `jobs` values are refused.

## S3

`stage_read.run(..., jobs=S3_JOBS)`, with S3_JOBS = 12.

- **Calibration tranche.** It reads one unit at a time, whatever `jobs` it is given, because the dispatcher admits a
  calibration tranche's calls only at concurrency one (CALIBRATION_SERIAL).
- **Out-of-range jobs.** A `jobs` outside 1 to 12 is refused before the stage begins (READ_JOBS_EXCEEDED).
- **Record.** The stage summary records the `jobs` it read with.

Where each kind of output is written, and how:

| What | Written by | How it stays the same bytes |
| --- | --- | --- |
| `read/<unit>.json`, and each view's `claims/`, `events/`, `evidence/` and `views/<view>/expansion-*.json` | one unit | A view belongs to one unit, so no other unit writes these files |
| results, observations, completeness, search forcing, the summary's counts and lists | each unit gathers its own (`per_unit`) | folded after the units, in unit order, as one at a time adds them |
| `expansions.jsonl`, the one file every unit appends to | `views.record_decision` | **written under a lock** (`stagelock.hold(run_dir, "expansions")`), then **put in unit order** at the stage's end (`views.order_decisions`, a stable sort by the rank of each decision's view, replaced whole) |
| `read-results.json`, `observations/*`, `read.json` | the main thread | written after every unit, as before |
| the supervisor's ledger, calibration and breaker state, `calls/<id>` | dispatch | under dispatch's own file locks, or one directory per call; time fields throughout |

The decision log uses both strategies the lead named. The lock keeps each read-and-append whole: the
once-per-call check of commit 5a reads the log before it appends. The final ordering makes the bytes independent of
how the units interleaved. Within a view, decisions keep the order they were made in. For `jobs=1` the reordering
changes nothing.

The S3 fixture driver of commit 5a's kill test reads one unit at a time (`jobs=1`), so the kill leaves exactly the
held call open. The in-process resume and the one-go reference run with the default of twelve.

The golden host's plan is also written side by side now: `fx_stitcher` plants each stitch's answer into it. It does
so under a fixture lock and replaces the file whole, so a host never reads a plan half written.

Controls in `stage_read --self-test`:

- `5b Q6: S3 reading twelve units at a time leaves every store, read record, the results and the summary the bytes one
  at a time leaves, the reading's own jobs aside`.
  - It compares a run with jobs=1 against a run with jobs=12, in two roots under one name.
  - It covers the stores of commit 5a, every `read/<unit>.json`, `read-results.json` and `read.json` without `jobs`.
- `5b Q6: the units were read side by side: the first unit's first call waited until the second unit was read whole`.
  - In the jobs=12 run, the first unit's first call waits until the second unit's read record exists.
  - Only units read side by side can pass this, so it is decided by that file, not by time.
  - It also makes the second unit's appends come first, the order one at a time never takes.
- `5b Q6: the stage leaves the decision log in unit order, each view's decisions in the order made`.
  - In the golden run, every decision belongs to one unit, so no interleaving can happen.
  - This control therefore plants a decision of another unit's view against the unit order.
  - It runs the stage again (every call reused) and requires the log in unit order.
- `5b Q6: a calibration tranche reads its units one at a time, whatever jobs it is asked for`.
  - At most one call is in flight, and the summary's `jobs` is 1.
- `5b Q6: S3 refuses to read more than twelve units at a time, before the stage begins`.

## Not gated

- **The fold order.** The per-unit fold is in unit order, but only one list it builds can show the order: the
  summary's `windowless`. The golden run has no windowless view, so no control can tell an unsorted fold from a sorted
  one. Its order is the code's, unchecked.
- **The decision log's lock.** Its purpose is integrity under a concurrent read-and-append. No control forces two
  units to decide at the same instant, so the lock is unchecked.
- **Budget order.** When a stage budget cannot fit every reservation, which items are recorded `not_done` depends on
  the order the reservations arrive. Side by side, that order is not fixed. The golden budgets fit everything, and
  under a tight budget the not-done set of a jobs=12 run may differ from a jobs=1 run's.

## Commit 5a's Q4 path, checked by its own control

The lead asked, on 2026-11-04, for two cases to take two different paths.

- **Pid reused.** A recorded pid that is alive with another start time is our runner dead and its pid reused. It is
  named `identity_mismatch` and not signalled. Its reservation closes as interrupted, and the resume goes on.
- **Cannot verify.** These refuse the resume (RESUME_HOST_UNVERIFIED):
  - an identity recorded in part;
  - a failed listing;
  - a kill that left survivors.

Commit 5a's code already took these two paths. 5b adds the control
`a-pid-since-reused-by-another-process-closes-interrupted-and-the-resume-goes-on`, which uses a fixture process.
Before it, only `interrupted-refuses-the-resume-while-a-runner-it-cannot-verify-may-still-run` held the second path.
The Q4 decision D-20261104-efa3ec already names RESUME_HOST_UNVERIFIED and its three cases.
