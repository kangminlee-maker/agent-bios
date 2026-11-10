---
created_at: 2026-11-10T14:50:00+09:00
head: 368ab6c
kind: design
supersedes: null
---

# The baseline selected at an instant is read from the switch journals, and what they cannot place is named

Package relhist, commit 1 of 2 (brief `work/lead/relhist-brief.md`). D-20261102-ff52a2 left an unpinned Claude
session's and every Codex session's release catalog and adopted packages `release_history_deferred`. Its stage 0
(2026-11-10, code only) found the following. Only `compose/instructions_store.py` writes `runtime/state.json`'s
`selected_baseline_ref`: its recovery (installs) and `apply` (rollback, reset, and the other authoring operations).
Each write leaves a journal with the prior pointer, the next pointer and a time. The lead decided option C
(D-20261110-9c60bc). The history answers the baseline selected at the session's time, and the row says its basis is
the selection history, not the session's pin. This commit is the history alone, a function of the journals. Commit 2
connects it to the release rows. No product file changes.

This amends b2c8ef1 §9 (option 2's sketch) where the code reads the journals differently. Each difference is
listed under "Against the sketch".

## What lands

- `history_journals(state)`: every `<id>/journal.json` under `runtime/transactions` (the store),
  `runtime/installer-transactions`, `runtime/resets` and `runtime/migrations` of a frozen state. Reads go through
  the one source selection. A journal that is not a JSON object is None, never left out.
- `history_switches(journals)`: the switches and the journals that may hide one.
  - A switch is a finished store journal, `COMMITTED` (`committed_at`) or `RECOVERED_COMMITTED` (`recovered_at`).
    It names its prior and next pointer.
  - Its start is the plan's `created_at`. An install has none (the store's install journal has no instant before its
    recovery), so it takes the installer journal of the same id's `created_at`, or no start at all.
  - A journal whose pointer does not move (an install after a rollback, a selection change) is a link of the chain
    only.
  - `PLANNED` moves nothing and is not read.
  - These may hide a switch: a store journal not finished or not readable; an installer, reset or migration journal
    that is not `COMMITTED` or `SUPERSEDED`; a finished reset whose own store journal is not a finished switch. Each
    is placed at its own instant when it has one.
- `selection_history(journals, current)`: the time line as half-open pieces in seconds. Each piece answers a
  baseline or names why not:
  - before the first journal: `before_first_switch`;
  - a moving switch's `[start, end]`: `switch_in_flight`, or `switch_recovered` for a plan the store's recovery
    finished, whose `end` is the recovery's time. An install with no installer journal starts at the previous
    switch;
  - between two switches: the earlier `after`, or `history_gap` when the later `before` differs;
  - two moving switches finishing in one second: everything from the first one's start to the second one's end is
    `switch_tie`;
  - after the last switch: its `after` while the frozen state still selects it (when it was read), `history_gap`
    otherwise;
  - a journal that may hide a switch makes the answered piece it falls in `journal_unfinished`, or every answered
    piece when it cannot be placed;
  - no finished switch at all: `history_absent`.
- `history_answer(pieces, first, last)`: the piece holding both of a session's instants. Two instants in two pieces
  give the first unknown piece's reason among them, or `spans_switch`. No instant gives `session_undated`. An
  uncertain reason carries the `uncertain: ` prefix a row carries (S-21).

The keys are the history's own until commit 2 publishes them. The reason vocabulary admits only a key a run of the
suite publishes, so they enter `UNKNOWN_REASONS` with the rows that carry them.

## Against the sketch (b2c8ef1 §9)

- Before the first switch is `before_first_switch` whatever its prior pointer. The sketch read a null prior pointer
  as nothing installed. A state directory that was removed and installed again (a legacy uninstall purges it) also
  starts from null, so a null is not evidence that nothing was selected earlier.
- An install's window is narrowed by the installer journal's `created_at` when there is one. The sketch held every
  install to `[the previous switch, this switch)`.
- A recovered plan journal (`switch_recovered`), a finished reset whose store journal is missing, and installer or
  migration journals that did not finish are named. The sketch named only PREPARED, NEEDS_RECOVERY and malformed
  store journals.
- A journal that moves nothing opens no window, so a session across an install after a rollback keeps the
  rolled-back baseline.

## Controls

Section "relhist: the baseline-selection history, from the journals alone". It uses one fixture of four switches:
two installs with installer journals, a rollback, and a reset with its reset journal. Controls 1 to 16 each change
one condition: rollback then reset; before the first journal; the switch boundary; the installer's narrowing and
its absence; a recovered install and a recovered plan; a PLANNED journal; an unreadable one; a placed unfinished
one (PREPARED, an orphan reset, an installer left NEEDS_RECOVERY); a broken chain; the tail against the state; a
tie; a session across a switch; a session with no instant; an install that keeps the pointer; no finished journal;
the reader.

Work tool `pt-relhist.py` (not committed) runs 19 revert rows, each over a fresh copy with the inventory suite in
full, under a fake HOME and a short TMPDIR. Every row is caught by the control it names, no row cuts a block, and
none prints a traceback. The `none` row passes.
