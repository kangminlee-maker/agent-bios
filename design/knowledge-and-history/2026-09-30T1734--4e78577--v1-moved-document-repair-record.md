---
created_at: 2026-09-30T17:34:51+09:00
head: 4e78577
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20260930-bea6c5
---

# A repository document changed since it was admitted is shown before the start, and its refusal says what to do

This repairs the finding in the [16:42 direct-use record](2026-09-30T1642--3e78f11--v1-acceptance-after-review3-direct-use-record.md).

That run's start was refused. The main checkout's `AGENTS.md` had been edited by another session
after it was admitted. The refusal was right, but the entry showed `activating the environment
was refused with working_bytes_moved`:

- an internal code;
- no statement of what moved;
- no next step.

Nothing before the start showed it either.

## What the owner chose

Option A (`D-20260930-bea6c5`):

- show the change on the entry and in `sources` before a start;
- word the refusal in the person's language with the next steps, which are leaving the
  repository's Instructions out or admitting the document again;
- add no command that admits it again, since admitting sources stays the workbench's in V1
  (`D-20260929-34e9ab`).

Two alternatives are closed:

- a command, or an automatic admission at start;
- deferring.

## What changed

- **`workenv/roles.py`.** `drifted(store, source_id, member, digest)` is the one reading of "a
  repository-authored source's document in its bound checkout no longer reads as the body
  admitted". It is `moved`'s per-unit check, lifted out, and `moved` asks it. Any other source is
  never drifted.
- **`workenv/tui.py`.**
  - `position_of` asks `drifted` for each Instructions member a pin selects, with a collection
    or without one.
    - A changed member is not listed among the held names.
    - The position is `partial`, or `missing` where nothing else is usable.
    - Its label names it: `등록 뒤 바뀜 AGENTS.md` (en `changed since admitted`, ja `登録後に変更`),
      and counts the rest.
  - `Entry.answered` takes the gap codes an `unavailable` answer stated, and refuses them with any
    other answer.
  - A start refused `working_bytes_moved` is drawn as `시작하지 못함 · 레포 문서가 등록 뒤 바뀜 ·
    Space로 빼거나 다시 등록` (en `Not started · repository document changed · leave it out
    (Space) or re-admit`, ja likewise). Each fits one 80-column line.
  - Any other refusal is drawn with the owner's reason, as before.
- **`workenv/hosts/start.py`.** `StartError` carries the codes the owner's answer stated.
- **`workenv/commands.py`.**
  - `start` hands those codes to the entry.
  - `sources` ends a changed source's line with `; changed in the checkout since admitted:
    <members>`.
- **Tests:**
  - `test_roles`: `drifted` on an authored document unchanged, edited and removed, and never on
    a managed source;
  - `test_tui`: the entry before and after the checkout's document changes;
  - `test_tui`: the refusal drawn with and without the code, and codes refused with an `unknown`
    answer;
  - `test_commands`: `sources`, and the command drawing the refusal;
  - `test_start`: the codes the refusal carries.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1z.py`, `mutate_v1z.txt`) caught 12 of 12:
  drift itself, `moved` asking it, the entry, `sources`, the codes carried and handed on, the
  wording drawn, and codes taken only with `unavailable`.
- **The earlier sweeps, re-run on this tree** (`mutate_*-rerun-v1z.txt`):
  - `mutate_v1r.py` caught 8 of 8, and `mutate_v1v.py` 5 of 5.
  - `mutate_v1u.py` caught the 22 it could apply, and `mutate_v1x.py` the 11.
  - Six mutations found no anchor, because this repair restructured `position_of` and `held_at`:
    one of `mutate_v1u.py` (also in `mutate_v1u-reanchored.py`) and five of `mutate_v1x.py`.
    Re-anchored on the code as it is now, undoing the same things
    (`mutate_v1ux-reanchored.py`), all six are caught.
- **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`, 837 outcomes) are identical before and after. V1's
  21 pass.
- **Bindings.** `cases.py --bindings` equals the 13 frozen bindings `run-12` holds, so P01 is not
  reopened.

## Next

1. **A short real use on both hosts** with the committed code.
   - The main checkout's `AGENTS.md` has changed again since `readmit.py`, so the entry should show
     it before the start, and the refusal should read in Korean.
   - Then admit it again, and start on both hosts.
2. **`run-13`:** `run-12` without V1's attempt.
3. **V1 recorded again,** and one bound review, whose result goes to the owner.
