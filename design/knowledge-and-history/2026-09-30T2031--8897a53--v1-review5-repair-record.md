---
created_at: 2026-09-30T20:31:06+09:00
head: 8897a53
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20260930-154b14, D-20260930-c06461
---

# V1's fifth bound review found the entry naming members a collection leaves out, and it names only those selected now

This follows the [19:28 repair record](2026-09-30T1928--f6fa9ee--v1-review4-repair-record.md)
and the [19:37 direct-use record](2026-09-30T1937--14b09a7--v1-acceptance-after-review4-direct-use-record.md).

- **The record.** V1 was recorded into `run-14` at `8897a53`, and all 21 cases passed. `run-14`
  is `run-13` without V1's fourth, unpublished attempt (`v1-accept/make_run14.py`).
- **The review.** One bound review ran on `gpt-6-astra` at max effort, hermetic and read-only,
  from 19:42:24 to 20:02:02 (`review-v1-20260930-r5/`).
- **The result.** `defects_found`: one medium finding, and 24 stated checks. The bound digests and
  the recorded case outcomes agree. Publishing would preserve P00 and P01.

V1's attempt in `run-14` is not published. V1 is recorded again, in a new run, after this repair.

## What the review found, re-derived here

**An entry position named members its collection does not select.** This goes against done-when
[7], [8] and [10].

- **The reviewer's case.** A revision holds `not-selected.md` and `selected.md`, and a collection
  entry declares only `selected.md`.
  - The entry read `installed` with the label `Personal Instructions · not-selected.md and 1 more`.
  - Composition, and the bodies a start hands over, held `selected.md` alone.
  - Selecting both members drew the same label.
  - With `selected.md`'s bytes absent, the position read `partial`, although nothing selected is
    usable.
- **In the code.** `position_of` checked missing bodies and changed documents within the declared
  units, but built its names from every member of the revision. `sources` listed every member the
  same way.

## What the owner chose

Fix it now, within the frozen contract (`D-20260930-154b14`). The closed alternative is deferring
it as a known limitation.

## What changed

- **`workenv/preparation.py`.**
  - `selected(manifest, declared)` is the one reading of "the members a pin selects": each unit it
    declares that its revision holds, or else every member, as composition reads an entry.
  - `unheld` asks it.
- **`workenv/tui.py`.**
  - `position_of` names only the selected members, for Instructions and for knowledge. It checks
    bodies and changes on the same members.
  - A collection whose selected bodies are all unusable reads `missing`.
  - `revision_names` had no other reader and is removed.
  - The module's description says a position names the members its pins select.
- **`workenv/commands.py`.** `sources` lists each source's selected members.
- **Tests:**
  - `test_preparation`: `selected` with no declared units, with an empty list of them, and with a
    declared member the revision does not hold.
  - `test_tui`: a collection selecting one of two members names it alone and reads `installed`;
    with its bytes absent it reads `missing`, naming it as not held; a knowledge collection names
    its selected member alone.
  - `test_commands`: `sources` lists the selected member alone.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1zc.py`, `mutate_v1zc.txt`) caught 6 of 6:
  `selected` ignoring what a pin declares or keeping a member the revision does not hold,
  `unheld` reading every member, and the entry's Instructions and knowledge names and `sources`
  naming every member.
- **The earlier sweeps, re-run on this tree** (`mutate_*-rerun-v1zc.txt`):
  - `mutate_v1r.py` caught 8 of 8, `mutate_v1v.py` 5 of 5, `mutate_v1za.py` 6 of 6,
    `mutate_v1zb.py` 8 of 8, and `mutate_v1ux-reanchored.py` 6 of 6.
  - `mutate_v1u.py` caught the 22 it could apply and `mutate_v1u-reanchored.py` the 1, with the
    anchors the
    [17:34 record](2026-09-30T1734--4e78577--v1-moved-document-repair-record.md) names.
  - `mutate_v1x.py` caught the 9 it could apply and `mutate_v1z.py` the 10. Four more anchors
    moved, because this repair introduced `selected` and restructured `position_of` and
    `held_at`: `unheld` finding nothing and ignoring the declared units, a changed member staying
    among the names, and `sources` checking no drift. Re-anchored on the code as it is now,
    undoing the same things (`mutate_v1xz-reanchored.py`), all four are caught. The other five of
    `mutate_v1x.py` are the ones `mutate_v1ux-reanchored.py` undoes.
- **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`, 837 outcomes) are identical before (an archive
  of `8897a53`) and after: 61 passed, 764 blocked, 12 failed. V1's 21 pass.
- **Bindings.** `cases.py --bindings` equals the 13 frozen bindings `run-15` holds, so P01 is not
  reopened.

## Next

1. A short real use on both hosts with the committed code.
2. V1 recorded into `run-15`, which is `run-14` without V1's attempt (`v1-accept/make_run15.py`).
3. One bound review, whose result goes to the owner.
