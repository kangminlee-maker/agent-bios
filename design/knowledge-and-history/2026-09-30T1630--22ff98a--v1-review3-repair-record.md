---
created_at: 2026-09-30T16:30:07+09:00
head: 22ff98a
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20260930-38bbad, D-20260930-c06461
---

# V1's third bound review found two things the person is not shown, and both are shown now

This follows the [15:13 repair record](2026-09-30T1513--3851a9a--v1-review2-repair-record.md)
and the [15:21 direct-use record](2026-09-30T1521--3715395--v1-acceptance-after-review2-direct-use-record.md).

- **The record.** V1 was recorded into `run-12` at `22ff98a`, and all 21 cases passed. `run-12`
  is `run-11` without V1's second, unpublished attempt.
- **The review.** One bound review ran on `gpt-6-astra` at max effort, hermetic and read-only,
  from 15:25:39 to 15:44:37. The packet held the recorded commit's source.
- **The result.** `defects_found`: two findings, one high and one medium, and 19 stated checks.
  The recomputed identities and the recorded outcomes agree. Publishing would unaccept neither P00
  nor P01.

V1's attempt in `run-12` is not published. V1 is recorded again, in a new run, after this repair.

## What the review found, re-derived here

### 1. High: an Instructions member whose body is not held drops out silently

This goes against done-when [10].

- **The reviewer's case.** It used N09-C07-POS's personal selection with one member's bytes
  missing from the bundle.
  - The position read `installed`.
  - Composition answered `previewed` with no material gap.
  - Activation committed.
  - The environment held no trace of the member.
- **In the code.** `Composition.bodies` gives a body-less unit a gap only where it wins or a
  winner needs it. Any other unit states no `body_digest` and gates nothing.
- **Why the code does this.** That is the frozen contract as read on 2026-09-27
  ([cmp-qualified record](2026-09-27T0100--d090ad2--cmp-qualified-placement-record.md)):
  - C07's `prepared_unit` gates a start only on a winning or needed unit;
  - `role_body_unavailable` is defined for a winning unit;
  - four frozen scenarios state such a unit with no gap.
- **Why it is still a finding.** Nothing else named the missing member either. The SSOT says
  "Unknown, denied, corrupt or missing selected material is not absence".

### 2. Medium: the entry's effects were never drawn

This goes against done-when [8] and [10].

- **What the model holds.** The tool (`model_calls`), the permissions (`permission_request`) and
  the start (`file_changes`, `model_calls`) state their effects in the frame. TUI-ENTRY-OPTIONS
  asserts them.
- **What the terminal drew.** `terminal.lines` drew marks and label only. The direct-use screens
  show no effect.

## What the owner chose

- **Both are fixed within the frozen contract** (`D-20260930-38bbad`).
  - A missing body is named, and it still gates nothing.
  - Two alternatives are closed:
    - making a layered unit's missing body a material gap, which changes C07 and its scenarios and
      re-freezes P01;
    - deferring both.
- **Every later bound review result for V1 is brought to the owner** (`D-20260930-c06461`). The
  closed alternative was a stopping rule: fix high findings and defer the rest.

## What changed

- **`workenv/preparation.py`.**
  - `unheld(state, revision, manifest, declared)` finds the members a pin selects whose bundle
    bytes are not held as the manifest states them. It uses `body_of`, the same reading
    composition uses.
  - `body_of` takes the state root instead of the call.
- **`workenv/tui.py`.**
  - `position_of` asks `unheld` for Instructions positions, with a collection or without one.
    - A position lacking some bodies is `partial`.
    - One lacking every body is `missing`.
    - Its label names the first member, `본문 없음 notes/bare.md` (en `body not held`, ja
      `本文なし`), and counts the rest.
    - The member is not listed as held.
  - `drawn(element, locale)` is the line the terminal draws: marks, label, then each effect in the
    locale's words (`모델 호출`, `파일 변경`, `권한 요청`; en and ja alike). `Entry.fit` measures
    that line, so `shown` stays what is drawn.
- **`workenv/terminal.py`.** `lines` draws `tui.drawn`.
- **`workenv/commands.py`.**
  - `sources` ends such a source's line with `; body not held here: <members>`.
  - Its `partial` and `missing` words now cover both causes: `some of what is selected is not
    usable here` and `nothing selected is usable here`.
- **`workenv/hosts/start.py`.**
  - `unheld(prepared)` finds the Instructions units whose standing would deliver them but that
    name no body and state no gap.
  - `gaps_text` names each one after the material gaps, as `- The personal instructions member
    rules/plain.md, source src_… at revision …: its body is not held here, so this environment
    does not hold it.`
  - A winning unit's missing body keeps its `role_body_unavailable` line and is not named twice.
  - Nothing particular to one preparation is added, so the hook's environment digest still
    holds.
- **Tests.** New or changed tests in five files:
  - `test_preparation`: `unheld`.
  - `test_tui`: a partial and a missing position.
  - `test_tui`: each effect on its line.
  - `test_terminal`: effects drawn in the frame's words.
  - `test_terminal`: the measure-versus-draw test, now with effects.
  - `test_commands`: the `sources` line.
  - `test_start`: named once beside a winning unit's gap.
  - `test_start`: a start that tells the session.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1x.py`, `mutate_v1x.txt`) caught 16 of 16. Each
  mutation undoes one part: the finding, the entry, `sources`, the environment, the single naming
  and the drawing.
- **The earlier sweeps, re-run on this tree** (`mutate_v1*-rerun-v1x.txt`):
  - `mutate_v1r.py` caught 8 of 8, and `mutate_v1v.py` 5 of 5.
  - `mutate_v1u.py` caught the 22 of 24 it could apply. The other two found no anchor, because
    this repair restructured the code they mutate. Re-anchored on the code as it is now,
    undoing the same things (`mutate_v1u-reanchored.py`), both are caught.
- **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`, 837 outcomes) are identical before and after. V1's
  21 pass.
- **Bindings.** `cases.py --bindings` equals the 13 frozen bindings `run-12` holds, so P01 is not
  reopened.

## Next

1. A short real use on both hosts with the committed code.
2. `run-13`: `run-12` without V1's attempt.
3. V1 recorded again, and one bound review. Its result goes to the owner.
