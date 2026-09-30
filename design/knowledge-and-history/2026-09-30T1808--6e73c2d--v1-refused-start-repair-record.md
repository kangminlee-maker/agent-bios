---
created_at: 2026-09-30T18:08:53+09:00
head: 6e73c2d
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20260930-bea6c5
---

# A start the owner refused leaves the entry's choices open, so its next step works where it is named

This repairs what the real use of the
[17:34 repair](2026-09-30T1734--4e78577--v1-moved-document-repair-record.md) found, at `6e73c2d`.

## What was seen

The real use ran on a clone of the main checkout, `v1-accept/use/drift/checkout`, with its own
state base. Evidence is in `v1-accept/use/`, files `73` … `80`.

1. **Before the change** (`75`). The entry showed `› [x] (제안) 레포 지침 · AGENTS.md`.
2. **The change** (`76`). One line was appended to the clone's `AGENTS.md` only.
3. **`sources`** (`77`) read `nothing selected is usable here`. The source's line ended
   `; changed in the checkout since admitted: AGENTS.md`.
4. **The entry** (`78`) showed `› [x] (제안) 레포 지침 · 등록 뒤 바뀜 AGENTS.md`.
5. **Enter on the start** (`79`) launched nothing. It drew `시작하지 못함 · 레포 문서가 등록 뒤
   바뀜 · Space로 빼거나 다시 등록`.

So far the repair held. Then:

6. **Space did nothing** (`80`). Up, Up and Space on the repository's Instructions left the line
   `[x]`. The entry was left with Ctrl-C (exit 130).

The refusal named a next step that did not work in the entry that named it.

- **Why.** Space, the tool and permissions arrows and the start all asked whether a start had been
  dispatched (`Entry.started`). A refused start is still dispatched, so every choice stayed held.
  Leaving the entry and opening it again was the only way out, and nothing said so.
- **Against.** Done-when [10], "same-request recovery stay visible", and the owner's option A,
  whose wording names Space.

## What changed

- **`workenv/tui.py`.**
  - `Entry.choosing()` is the one reading of "the choices can still change and start".
    - It holds when no start was dispatched, or when the owner answered the last one
      `unavailable`.
    - A refused start started nothing: `start.start` raises its refusal only while activation
      is not `unknown`, and before any launch.
    - A start pending or `unknown` still holds the choices. TUI-ENTRY-UNKNOWN forbids a new
      request for the same unknown operation, and that is unchanged.
  - Space, the tool and permissions arrows and the start ask `choosing()`.
  - After a refusal, the start dispatches a new `preparation.compose` for the choices as they
    now are. The refused start's result stays drawn until then.
  - The module's description says so.
- **The refusal's wording is unchanged.** Its next step now works where it is read.
- **Nothing else changes.** `commands.begin` already went on reading the screen after a refusal
  and starting the next captured request. The owner's journal already refuses a request repeated
  while an identical one is unknown (`resubmitted_while_unknown`).
- **Tests:**
  - `test_tui`: after a refusal, Space leaves the person's Instructions out and the tool turns;
    the refusal stays drawn; Enter sends a second compose with a new request and no pin.
  - `test_tui`: a start pending, or answered `unknown`, holds every choice and sends nothing
    again.
  - `test_commands`: `start` refused once, then Enter in the same entry, launches the host with a
    second request.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1za.py`, `mutate_v1za.txt`) caught 6 of 6:
  `choosing()` ignoring the refusal, freeing an `unknown` start, freeing a pending start, and each
  of Space, the arrows and the start asking only whether a start was dispatched.
- **The earlier sweeps, re-run on this tree** (`mutate_*-rerun-v1za.txt`):
  - `mutate_v1r.py` caught 8 of 8, `mutate_v1v.py` 5 of 5, `mutate_v1z.py` 12 of 12, and
    `mutate_v1ux-reanchored.py` 6 of 6.
  - `mutate_v1u.py` caught the 22 it could apply, `mutate_v1u-reanchored.py` the 1, and
    `mutate_v1x.py` the 11. The anchors they found no match for are the ones the
    [17:34 record](2026-09-30T1734--4e78577--v1-moved-document-repair-record.md) names, which
    `mutate_v1ux-reanchored.py` undoes on the code as it is now. No new one.
- **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`, 837 outcomes) are identical before (an archive
  of `6e73c2d`) and after: 61 passed, 764 blocked, 12 failed. V1's 21 pass.
- **Bindings.** `cases.py --bindings` equals the 13 frozen bindings `run-12` holds, so P01 is not
  reopened.

## Next

1. The drift real use again: the entry shows the change, the start is refused, and Space then
   Enter starts without the repository's Instructions. Then one start on each host in the state
   base.
2. `run-13`: `run-12` without V1's attempt.
3. V1 recorded again, and one bound review, whose result goes to the owner.
