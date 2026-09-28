---
created_at: 2026-09-29T08:49:24+09:00
head: 48020b4
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260929-703c89, D-20260929-b36a5b
---

# V1, fifth slice, fourth increment (b): a settled check is drawn on the same screen

This follows the [07:39 record](2026-09-29T0739--9f2cfc0--v1-slice5-unconfirmed-start-record.md) of
the unconfirmed start, whose first open item it closes. V1 is not complete, and no node is
accepted by this work.

## Why

At `48020b4`, the check that settled a start drew it badly. This was shown to the owner on
2026-09-29 with the workbench's `show5e.py`, on an 80-column screen:

1. **The label contradicted what happened.** It read `확인하지 못함 · <reason>`, "could not check",
   though the check had settled the start. The entry model drew a check's answer only as
   `unknown` or `unavailable`.
2. **The reason was English and was cut off.** The cut fell at column 80, before its instruction
   to open the entry again.
3. **The start stayed blocked on the same screen.** The model held back the next start whenever
   it held a draft, whatever the check had answered.

The owner chose to reflect the settled start on the same screen (`D-20260929-b36a5b`).

## What changed

- **`workenv/tui.py`.**
  - **A new answer.** A check can be answered `settled`, with the stage its start now stands at,
    which is no longer pending.
  - **How it is drawn.** The draft shows the settled start in the entry's own words, in all three
    languages:
    - `settled.committed`: the session reported that it began;
    - `settled.expired`: recorded as not reported by its session;
    - `settled.other`: any other stage, named as it is.
    - Each label ends by saying the next start can run.
  - **Its element state.** `delivered` where the session reported, `unavailable` otherwise. Both
    are values the contract's element states already hold.
  - **What it releases.**
    - A settled start no longer holds the next one back (`holds_back`), and the start's earlier
      `blocked` mark is cleared.
    - The hub signals only a start that still holds back, and focuses the signal only then.
  - **Refused answers.** `settled` is refused for the start's own request, or at a pending stage.
    An answer to no request is refused too; before this, it was accepted when nothing had been
    dispatched.
- **`workenv/commands.py`.**
  - **The order in the dispatcher.** It settles a start that nothing waits for any more before it
    answers the check's query. So the query itself returns the settled result.
  - **What `checked` answers.** `settled` with the stage, for any stage no longer pending. This
    also covers a start whose session reported while the screen was open. That start used to read
    `확인하지 못함 · the request was answered committed; open the entry again to see it`; it now
    reads `settled.committed`.
- **`docs/recovery.md`** says the next start can run at once.

## What did not change

- **The frozen cases.** `surface.drive` records what the model dispatches and hands it no answer,
  so no drafted trace can reach `settled`.
- **The element states,** which the contract fixes.

## How it was checked

- **Unit tests.**
  - `test_tui.py` (61):
    - the three settled labels and their states;
    - the start, blocked before the check, running after it;
    - the hub no longer signalling;
    - the refused answers;
    - the catalog width check, with the longest stage name filled in.
  - `test_commands.py` (33):
    - the check settles an unwaited start;
    - the next start runs from the same screen;
    - `checked` answers settled stages.
- **Mutation sweeps (workbench `v1-slice5/`).**
  - `mutate5f.py`, this change: 13 of 13 caught.
  - `mutate5e.py`, `mutate5d.py`, `mutate5c.py`, `mutate5b.py`: 40 of 40, 58 of 58, 22 of 22
    and 87 of 87 still caught. Five anchors in the changed lines moved and were updated.
- **The V1 cases (`runv1-inc4b.txt`):** 19 passed and 3 failed, the same case for case as
  `runv1-inc4.txt`.
- **The screens (`show5e.py`, `show5e-4b.txt`),** drawn by the real code with a fake host:
  - After Enter on the check, the draft reads `지난 시작 · 세션이 시작을 알리지 않음으로 기록됨 ·
    새로 시작 가능` (English `Last start: recorded as not reported by its session · you can start
    again`), whole on 80 columns, with state `unavailable`.
  - Tab three times and Enter then dispatches the start and launches the host on the same
    screen.
  - While a program still waits on the start, the check leaves it `unknown`, as before.

## Open

- **A stage outside `committed` and `expired` is named in its own English word.** For example, a
  confirmation refused on a moved checkout reads `refused(으)로 끝남`.
- **The earlier open items remain:** F-19, the orphaned host, and the two activations per start.
