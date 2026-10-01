---
created_at: 2026-10-01T16:31:47+09:00
head: 7de34b9
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20261001-fa937f, D-20260930-c06461
---

# V1's eighth bound review found a needed unit escaping its gate when switched off and an unknown start pushed out of the history, and both are fixed

This follows the [10:58 repair record](2026-10-01T1058--b7e35f7--v1-review7-repair-record.md)
and the [11:06 direct-use record](2026-10-01T1106--3c2ee2b--v1-acceptance-after-review7-direct-use-record.md).

- **The record.** V1 was recorded into `run-17` at `7de34b9`, and all 21 cases passed. `run-17`
  is `run-16` without V1's seventh, unpublished attempt (`v1-accept/make_run17.py`).
- **The review.** One bound review ran on `gpt-6-astra` at max effort, hermetic and read-only,
  from 11:10:31 to 11:31:52 (`review-v1-20261001-r8/`).
- **The result.** `defects_found`: one high and one medium finding, and 18 stated checks. The
  recomputable fingerprints and case totals match. P00 and P01 would remain accepted.

V1's attempt in `run-17` is not published. V1 is recorded again, in a new run, after this repair.

## What the review found, re-derived here

### 1. High: a needed unit escaped the start's gate once switched off

This goes against done-when [10].

- **The reviewer's case.** A required winning `AGENTS.md` unit needs a companion whose body is not
  held. Switched on, the companion's `role_body_unavailable` refused the activation. Switched
  off, it kept `needed_by` but stated no gap, and the activation committed.
- **The contract.** C07's `unit_binding`: a needed unit "stays required with its own conditions,
  even when it is itself shadowed or switched off".
- **In the code.** `Composition.bodies` skipped every `disabled` unit before reading its body.

### 2. Medium: an unknown start pushed out of the history was started again

This goes against done-when [10] and TUI-ENTRY-UNKNOWN.

- **The reviewer's case.** An activation left unknown, then ten preparations in the same scope.
  The history listed the latest ten, the unknown start was not among them, and the entry
  dispatched a new composition instead of returning to its check.
- **In the code.** `operation_history_read` kept the latest `limit` starts whatever their stage.
  The entry finds its unknown start in that history only.

## What the owner chose

Both are fixed within the frozen contract, and every later V1 review result keeps going to the
owner (`D-20261001-fa937f`). The closed alternatives are deferring either finding, and fixing
only high findings from the next review on.

## What changed

- **`workenv/preparation.py`.** `Composition.bodies` reads a switched-off unit a winning unit
  needs: it states its body's digest, or its gap. Any other switched-off unit is still not read.
  The module's description says so.
- **`workenv/journal.py`.** `operation_history_read` lists at most `limit` starts, oldest first:
  first the latest pending ones, then the latest others in the places left. A start still pending
  stays listed however many came after it. The history's contract is unchanged: both lists stay
  bounded. The module's description says so.
- **Tests:**
  - `test_roles`: a switched-off unit a required winner needs gates the start when its body is
    not held, and is read, not delivered, when it is.
  - `test_routes`: a pending start stays listed after more than `limit` later starts; the latest
    pending ones take their places first, at most `limit`; the list stays oldest first.
  - `test_tui`: an unknown start stays the entry's draft after eleven later starts, and Enter
    dispatches no composition.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1zf.py`, `mutate_v1zf.txt`) caught 6 of 6 on its
  first run: a needed unit switched off not read; every unit switched off read; a pending start
  not kept; pending starts past the limit kept; the oldest others filling the rest; the list
  not oldest first.
- **The earlier sweeps, re-run on this tree** (`mutate_*-rerun-v1zf.txt`):
  - `mutate_v1r.py` caught 8 of 8, `mutate_v1v.py` 5 of 5, `mutate_v1za.py` 6 of 6,
    `mutate_v1zc.py` 6 of 6, `mutate_v1ze.py` 11 of 11, `mutate_v1ux-reanchored.py` 6 of 6,
    `mutate_v1xz-reanchored.py` 4 of 4, `mutate_v1z-reanchored.py` 1 of 1 and
    `mutate_v1zbd-reanchored.py` 3 of 3.
  - `mutate_v1u.py`, `mutate_v1u-reanchored.py`, `mutate_v1x.py`, `mutate_v1z.py`,
    `mutate_v1zb.py` and `mutate_v1zd.py` caught all they could apply. Each missed only the
    anchors the [10:58 record](2026-10-01T1058--b7e35f7--v1-review7-repair-record.md) and the
    records before it name, which the re-anchored sweeps above cover. No anchor moved in this
    repair.
- **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`, 837 outcomes) are identical before (an archive
  of `7de34b9`) and after: 61 passed, 764 blocked, 12 failed. V1's 21 pass.
- **Bindings.** `cases.py --bindings` equals the 13 frozen bindings `run-18` holds, so P01 is not
  reopened.

## Next

1. A short real use on both hosts with the committed code.
2. V1 recorded into `run-18`, which is `run-17` without V1's attempt (`v1-accept/make_run18.py`).
3. One bound review, whose result goes to the owner.
