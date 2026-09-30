---
created_at: 2026-09-30T21:35:00+09:00
head: 8c27731
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20260930-c92d68, D-20260930-c06461
---

# V1's sixth bound review found a delivery recorded before it was handed over and a switched-off unit refusing a start, and both are fixed

This follows the [20:31 repair record](2026-09-30T2031--8897a53--v1-review5-repair-record.md)
and the [20:38 direct-use record](2026-09-30T2038--5ee9bd2--v1-acceptance-after-review5-direct-use-record.md).

- **The record.** V1 was recorded into `run-15` at `8c27731`, and all 21 cases passed. `run-15`
  is `run-14` without V1's fifth, unpublished attempt (`v1-accept/make_run15.py`).
- **The review.** One bound review ran on `gpt-6-astra` at max effort, hermetic and read-only,
  from 20:44:14 to 21:02:09 (`review-v1-20260930-r6/`).
- **The result.** `defects_found`: one high and one medium finding, and 21 stated checks.
  Publishing V1 would unaccept neither P00 nor P01.

V1's attempt in `run-15` is not published. V1 is recorded again, in a new run, after this repair.

## What the review found, re-derived here

### 1. High: a prompt's changed bodies were recorded as received before they were handed over

This goes against done-when [6].

- **The reviewer's case.** A linked Claude Code session, and a new personal Instructions body.
  The hook ran with its standard output on a pipe whose reader was closed, and raised
  `BrokenPipeError`: nothing reached the session. `delivery.observe` still said `delivered`,
  with the new body. The next prompt printed nothing, since the preparation read as reached.
- **In the code.** `Session.prompted` recorded the `current` delivery, then returned the text,
  which `main` printed afterwards.
- **Checked here.** The notice that a change is too large for the hook was kept as given the same
  way, before it was printed. It is fixed with the delivery.

### 2. Medium: a switched-off repository-authored unit refused the start

This goes against done-when [5].

- **The reviewer's case.** A collection switches off a repository-authored source whose checkout
  document is unchanged. Composition gives the unit `disabled`, with no body. Activation was
  refused `working_bytes_moved`.
- **In the code.** `roles.moved` asked `drifted` about every unit, passing a disabled unit's
  absent body digest. `drifted` compared the checkout document's digest with `None`.

## What the owner chose

Both are fixed within the frozen contract (`D-20260930-c92d68`). The closed alternatives are
deferring either as a known limitation.

## What changed

- **`workenv/hosts/hook.py`.**
  - `Session.prompted` and `noticed` leave what they record in `Session.handed`, and record
    nothing themselves.
  - `main` prints and flushes first. Only when that succeeded does it record the delivery, or
    keep the notice as given.
  - Output the host did not take records nothing, and a later prompt hands it again. Standard
    output then goes to the null device, so the buffer left behind does not fail the hook at
    exit. Without that, a real closed pipe ended the hook with status 120.
  - A record that fails after the output is said on standard error.
  - The module's description says so.
- **`workenv/roles.py`.**
  - `moved` asks `drifted` only about units that name a body. A unit that names none claims
    nothing about its document.
  - A comment that said an authored source's units always name a body is corrected.
  - The module's description says so.
- **Tests:**
  - `test_start`: output the host did not take, on a stream that refuses it and on a real
    closed pipe in a separate process, records nothing, exits 0 and is handed again.
  - `test_start`: output handed over whose record fails says so.
  - `test_start`: a notice the host did not take is given again.
  - `test_roles`: a switched-off repository-authored unit activates.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1zd.py`, `mutate_v1zd.txt`) caught 8 of 8: the
  change recorded, or the notice kept, before the output; output not taken recorded; the output
  not flushed; the buffer left behind failing the hook at exit; nothing recorded once handed
  over; a failed record not said; `moved` reading a unit that names no body.
- **The earlier sweeps, re-run on this tree** (`mutate_*-rerun-v1zd.txt`):
  - `mutate_v1r.py` caught 8 of 8, `mutate_v1v.py` 5 of 5, `mutate_v1za.py` 6 of 6,
    `mutate_v1zb.py` 8 of 8, `mutate_v1zc.py` 6 of 6, `mutate_v1ux-reanchored.py` 6 of 6 and
    `mutate_v1xz-reanchored.py` 4 of 4.
  - `mutate_v1u.py`, `mutate_v1u-reanchored.py` and `mutate_v1x.py` caught all they could apply.
    The anchors they found no match for are the ones the
    [20:31 record](2026-09-30T2031--8897a53--v1-review5-repair-record.md) names.
  - `mutate_v1z.py` caught the 9 it could apply. Two of its anchors are the ones the 20:31 record
    names. A third moved because this repair changed `moved`: `moved` not asking `drifted`.
    Re-anchored on the code as it is now, undoing the same thing (`mutate_v1z-reanchored.py`), it
    is caught.
- **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`, 837 outcomes) are identical before (an archive
  of `8c27731`) and after: 61 passed, 764 blocked, 12 failed. V1's 21 pass.
- **Bindings.** `cases.py --bindings` equals the 13 frozen bindings `run-16` holds, so P01 is not
  reopened.

## Next

1. A short real use on both hosts with the committed code.
2. V1 recorded into `run-16`, which is `run-15` without V1's attempt (`v1-accept/make_run16.py`).
3. One bound review, whose result goes to the owner.
