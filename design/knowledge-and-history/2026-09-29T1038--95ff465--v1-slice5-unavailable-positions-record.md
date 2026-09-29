---
created_at: 2026-09-29T10:38:28+09:00
head: 95ff465
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260929-70b432
---

# V1, fifth slice, fourth increment (c): nothing to choose is marked and skipped, and Enter on a detail starts

This follows the [09:36 direct-use record](2026-09-29T0936--9f7b58c--v1-slice5-direct-use-record.md).
The owner began the run by hand that record leaves ahead, and reported two things on the entry.
It changes one rule of the [entry grammar](2026-09-28T1601--4e305e5--v1-slice5-entry-grammar-design.md)
and adds one. V1 is not complete, and no node is accepted by this work.

## Why

On 2026-09-29, about 09:56, the owner ran `start` from the main checkout in English and sent two
screenshots:

1. **A position with nothing held looked selectable.**
   - The entry drew `[ ] Repository knowledge · none yet`, a box like the ones Space toggles.
   - ↓ put the cursor on it.
   - The owner asked that a position which cannot be chosen because nothing is there say so, and
     that the cursor skip it.
2. **Enter on a detail did nothing.**
   - Enter on `Repository Instructions` opened its detail:
     `Repository Instructions · AGENTS.md · original · installed`, with the keys
     `Enter open·start · Esc back`.
   - Enter there changed nothing. The owner asked that it start.

The owner's ask is recorded as `D-20260929-70b432`.

## What changed

- **`workenv/tui.py`.**
  - **Which positions have something to choose.** A position has nothing to choose when its state
    is `checked_empty` or `configured`:
    - `checked_empty`: no source there, or a collection that includes nothing;
    - `configured`: a source with no accepted revision.
  - **How they are drawn.** Such a position is drawn with `[-]` and the catalog's new
    `unavailable` word in place of a box: `(선택 불가)`, `(unavailable)`, `(選択不可)`.
  - **Its element state is unchanged** (`checked_empty` or `configured`): the contract fixes the
    element states. The trace records the new marks.
  - **Focus.** Focus starts on the check of an unknown start, else a link's target, else the
    first position there is something to choose at, else the first Tab stop.
    - With nothing to choose anywhere, that stop is the note.
    - The arrows move only through positions there is something to choose at.
    - The keys name ↑↓ only when there is one.
  - **Enter on a detail, when a start is offered.** It returns to the W01 under it, focuses the
    start, and starts as Enter on the start does:
    - held back the same way by an unknown start, with focus handed to the check;
    - blocked the same way by a note longer than a rationale holds.
  - **The detail's keys.** They read `Enter 시작 · Esc 뒤로` (new catalog key `key.start`).
  - **With no start offered,** Enter on a detail does nothing, and its keys name Esc alone.
- **Tests.**
  - **`test_tui.py`, 65 tests (4 new):**
    - Enter on a detail starts from the W01 under it;
    - a detail with nothing to start names no Enter;
    - Enter on a detail while an unknown start holds back returns to its check;
    - with nothing to choose, the arrows move nothing and are not named.
  - **Rewritten to the new focus:** the drives of tests whose entry has nothing to choose, which
    now begin on the note.
  - **The detail test** now presses Tab and Down on the detail, and neither moves anything.
  - **`test_commands.py`:** four key sequences.
  - **Two tests would have passed vacuously.** Under the new focus, both would have passed without
    sending a start: `test_an_answer_is_one_the_entry_draws_to_a_request_it_dispatched` and
    `test_leaving_the_entry_sends_nothing_and_launches_nothing`. Their drives were corrected, and
    the first now asserts the start was sent.

## What did not change

- **The frozen cases.** The restatements stay drafts until the P01 re-freeze
  (D-20260928-d6ff3a).
- **The element states,** which the contract fixes.
- **The trace's client** stays version 1, as through the earlier increments of this slice. The
  re-freeze fixes the grammar the drafts state.

## How it was checked

- **The workenv gate** (`gates/workenv/check-workenv.py`, every unit leg and ruff): OK.
- **The drafts (workbench `v1-slice5/`).** The reference model `entry.py` was changed to the same
  two rules, and `restate.py` names the edit as increment 4c:
  - ACCOUNT-FREE's and REPO-NO-ENV's entries have nothing to choose, so they start on the note and
    reach the start with Tab, Tab and Enter;
  - N16's drives start on the knowledge position and press no Down.
- **The V1 cases (`runv1-inc4c.txt`):** 19 passed and 3 failed, the same three as before
  (DEL-PERSONAL, N15-C11-POS, CMP-QUALIFIED).
- **The control (`runv1-inc4c-control.txt`).** The new drafts were run against the previous
  `tui.py`, in a copy of the tree. All seven drafted entry cases failed by name:
  - a `[-]` mark answered `[ ]`;
  - focus in a place the drafts do not state;
  - a start never sent.
- **Mutation sweeps.**
  - `mutate5g.py`, this change: 13 of 13 caught.
  - `mutate5c.py` to `mutate5f.py`: 22, 58, 40 and 13, all caught.
  - `mutate5b.py`: 87 of 87, after one fix. One anchor had moved with the arrows' code. Once
    updated, its mutation (the arrows moving focus in any view) was missed: the only test that
    covered it no longer had anything to choose. A Down on the detail was added to the detail
    test, and the mutation is now caught.
- **The screens (`show5g.py`, `show5g.txt`),** drawn by the real code from a copy of the real-use
  state in the main checkout. The state holds the repository's `AGENTS.md` and the person's
  `korean-writing.md`.
  - The four empty positions read `[-] (선택 불가) … · 아직 없음`.
  - Down from the repository's Instructions lands on the person's Instructions.
  - Enter opens its detail, whose keys read `Enter 시작 · Esc 뒤로`.
  - Enter there returns to W01 with the start focused and sends one start.
  - The English screens match, with `(unavailable)` and `Enter start · Esc back`.

## Open

- **The owner's run by hand** resumes from here. It is the run the 09:36 record leaves ahead.
- **Enter on a W01 position still opens its detail,** as the grammar says. The detail now starts
  on Enter, so a person who meant to start reaches it with one more Enter.
- **The earlier open items remain:**
  - F-19;
  - the orphaned host;
  - the two activations per start;
  - a stage outside `committed` and `expired`, which is named in its own English word;
  - the observations of the 09:36 record.
