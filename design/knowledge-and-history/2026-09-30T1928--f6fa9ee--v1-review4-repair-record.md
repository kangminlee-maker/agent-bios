---
created_at: 2026-09-30T19:28:31+09:00
head: f6fa9ee
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20260930-cc95f9, D-20260930-c06461
---

# V1's fourth bound review found a received unit attributed by its bytes and a leave-out the entry cannot do, and both are fixed

This follows the [18:08 repair record](2026-09-30T1808--6e73c2d--v1-refused-start-repair-record.md)
and the [18:19 direct-use record](2026-09-30T1819--fac8542--v1-acceptance-after-refused-start-repair-direct-use-record.md).

- **The record.** V1 was recorded into `run-13` at `f6fa9ee`, and all 21 cases passed. `run-13`
  is `run-12` without V1's third, unpublished attempt (`v1-accept/make_run13.py`).
- **The review.** One bound review ran on `gpt-6-astra` at max effort, hermetic and read-only,
  from 18:24:28 to 18:44:56 (`review-v1-20260930-r4/`).
- **The result.** `defects_found`: two medium findings, and 19 stated checks. The recomputed
  identities and the recorded outcomes agree. Publishing would unaccept neither P00 nor P01.

V1's attempt in `run-13` is not published. V1 is recorded again, in a new run, after this repair.

## What the review found, re-derived here

### 1. A unit no delivery carries was listed as received when its bytes were another's

This goes against done-when [6].

- **The reviewer's case.** It composed a personal Instructions document and a knowledge document
  with the same bytes, and activated the preparation. The activation projected the Instructions
  unit alone. `delivery.observe` listed both units in its inventory.
- **In the code.** `delivery.observations` listed every prepared unit whose body digest was among
  the bodies received. A body digest names bytes, not a unit. A knowledge unit, or a shadowed
  Instructions unit, whose bytes a delivered unit shares was listed as arrived.
- **Checked here.** A shadowed unit with its winner's bytes is listed too, by the same line.

### 2. A refusal named Space where Space changes nothing

This goes against done-when [10].

- **The reviewer's case.** An enabled collection selects the repository's Instructions, and the
  checkout's document changed since it was admitted. The start is refused `working_bytes_moved`,
  and the entry names Space. A collection's position is its recorded choice, which Space does not
  change (`Position.toggles`), so the next start is refused the same way.
- **In the code.** The refusal's wording did not depend on the position. The 18:19 real use left
  out a position no collection applies, which toggles.

## What the owner chose

Both are fixed within the frozen contract (`D-20260930-cc95f9`). Three alternatives are closed:

- deferring the first finding as a known limitation;
- letting Space leave out a collection's position for one start, which changes the composition
  request and reopens P01;
- deferring the second finding.

## What changed

- **`workenv/delivery.py`.**
  - `carried(unit)` is the one reading of "a delivery carries this unit's body": an Instructions
    unit of a delivered standing that names a body.
  - An observation's inventory lists a unit only where it is carried and its body was received.
  - The module's description says so.
- **`workenv/hosts/start.py`.** `delivered` asks `carried`, so the bodies a start hands over and the
  units an observation lists come from one rule.
- **`workenv/tui.py`.**
  - A start refused `working_bytes_moved` names Space only where every position showing a
    changed document toggles.
  - Otherwise it names admitting the document again alone: `시작하지 못함 · 레포 문서가 등록 뒤
    바뀜 · 다시 등록` (en `re-admit`, ja `再登録`). That covers a collection's position, and a
    start refused although no position showed the change, since the entry cannot say which to
    leave out.
  - The module's description says so.
- **Tests:**
  - `test_delivery`: an attempt handing over bytes an Instructions and a knowledge unit share
    lists the Instructions unit alone.
  - `test_roles`: the same after an activation, and a shadowed unit with its winner's bytes.
  - `test_tui`: the refusal with Space where the changed position toggles, and without it once a
    collection applies that position, which still shows the change and stays selected after
    Space.
  - `test_tui`, `test_commands`: a refusal where no position shows the change names admitting
    alone.
  - `test_start`: a start of an Instructions and a knowledge source hands over the Instructions
    body alone.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1zb.py`).
  - Its first run (`mutate_v1zb.txt`) caught 7 of 8. It missed `start.delivered` handing over
    every unit with a body: no start test composed a unit a delivery does not carry. The
    `test_start` test above was added for it.
  - Run again (`mutate_v1zb-2.txt`), it caught 8 of 8: the inventory matching bytes alone, a
    delivery carrying any role or any standing, a start handing over every body, Space named
    always, for a collection's position or where no position shows the change, and admitting
    alone never named.
- **The earlier sweeps, re-run on this tree** (`mutate_*-rerun-v1zb.txt`):
  - `mutate_v1r.py` caught 8 of 8, `mutate_v1v.py` 5 of 5, `mutate_v1z.py` 12 of 12,
    `mutate_v1za.py` 6 of 6, and `mutate_v1ux-reanchored.py` 6 of 6.
  - `mutate_v1u.py` caught the 22 it could apply, `mutate_v1u-reanchored.py` the 1, and
    `mutate_v1x.py` the 11. The anchors they found no match for are the ones the
    [17:34 record](2026-09-30T1734--4e78577--v1-moved-document-repair-record.md) names, which
    `mutate_v1ux-reanchored.py` undoes on the code as it is now. No new one.
- **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`, 837 outcomes) are identical before (an archive
  of `f6fa9ee`) and after: 61 passed, 764 blocked, 12 failed. V1's 21 pass.
- **Bindings.** `cases.py --bindings` equals the 13 frozen bindings `run-13` holds, so P01 is not
  reopened.

## Next

1. A short real use on both hosts with the committed code, and the drift clone's refusal.
2. `run-14`: `run-13` without V1's attempt.
3. V1 recorded again, and one bound review, whose result goes to the owner.
