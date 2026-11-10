---
created_at: 2026-11-10T17:05:00+09:00
head: 39e0643
kind: design
supersedes: null
---

# The selection history's answer stays out of context sets, and an unread state leaves the tail unknown

Package relhist, commit 3. It amends the commit-2 record
(`2026-11-10T1530--d489c76--an-unpinned-or-codex-sessions-release-is-the-baseline-the-library-selected-at-its-time-marked-as-the-selection-history.md`)
by this record only. The changes answer the interim review of `39e0643` (`work/lead/relhist-c-r1-review.json`,
verdict fix_then_accept). Codex review W waits for its usage limit. No product file changes; `inventory.py` and its
schema do.

## What changes

- Context sets (D-20261110-195c15).
  - `universe_of` takes an inventory only from a row whose basis is `pin`.
  - A release inventory the selection history answers is what the owner's library held, not what the session
    received. It is no part of a segment's context set until WP-10 rules on delivery evidence (§6.3).
  - So an unpinned or Codex segment's context set is the one it had before package relhist. The history's inventory
    is seen only on the index rows that carry basis `selection_history`.
  - The schema's `context_set` comment says so.
- The stretch after the last switch (`selection_history`, `freeze_inputs`).
  - The pointer `current` is now required. `freeze_inputs` gives:
    - None when the state holds no `runtime/state.json` (the store reads an absent file as no pointer);
    - `UNREAD_POINTER` when the file is there and could not be read, or names neither a baseline ref nor null;
    - the file's pointer otherwise.
  - A baseline ref equal to the last switch's result answers that baseline. A different ref, or None, is
    `history_gap`. Any other value is `input_failed`, because what the state selects now is not known.
  - Before this, an absent or unreadable state still answered the tail.
- The renames' base (`renames_base`).
  - It returns `(inventory_ref, reason, basis)`: `pin` for the `--pin` session's own snapshot, `selection_history` for
    the history's answer, None with no inventory.
  - `current.json`'s `notes.renames_base` carries the basis.
  - The manifest's done-when-1 copy of that inventory carries `baseline_basis` (`MANIFEST_TABLE`, optional).
- What is copied (`freeze_inputs`).
  - Only each `<directory>/<id>/journal.json` of the four journal directories is copied, which is all that
    `history_journals` reads.
  - A store transaction's other files and a migration's backup tree are no longer copied. A link inside a backup no
    longer disables the history, and the backed-up files' paths no longer reach `notes.frozen_missing`.
  - A journal directory that is a link, or lies under one, is a failed omission by its own path, even when it holds no
    journal. A journal directory that cannot be listed is a failed omission (`unreadable`). An id directory that is a
    link fails through `freeze`'s own check.
  - Each journal file is still copied whole: an installer journal's planned file bytes and a store plan's state
    documents are inside it. The copy lies in the temporary directory `run` removes. Only pointers, states and
    instants are read from it, and no journal content reaches a written document.
- The release index's cross-check (`release_cross_problems`).
  - It refuses a mislabelled basis as `RELEASE_BASIS_DIFFERS`. A row that names an inventory must have basis
    `selection_history` when it is a catalog or adopted-packages row of a Codex or unpinned session, and `pin` in every
    other case.
  - So the history's answer is never presented as a pinned session's own, nor a pin as the history's.
- Two texts.
  - `history_absent` says "no usable finished store journal".
  - `journal_unfinished` also covers a journal that has no instant to place it at, which makes every answered stretch
    uncertain.

## Assumption the answer rests on

The history assumes two things:

- the state directory existed continuously;
- every pointer change since the first journal went through the store.

The chain and tail checks catch an unjournaled change only when it leaves the pointer different. Two cases pass
unseen, and a session inside them is answered with a baseline:

- an unjournaled round trip, such as a hand edit A to X and back to A;
- a whole state directory restored from an older copy, such as the legacy uninstall archive.

The interim review's simulation found 0 wrong answers among 37,162 answered sessions when every switch was journaled.
All 5 wrong answers came from such a round trip after the last journal. WP-10 weighs `selection_history` rows with
this.

## Notes and residuals

- A Claude subagent's file row has no census pin of its own, even under a pinned parent. Its release rows are
  answered from the history, beside its parent's pin rows. The basis keeps the two apart.
- The tail's pointer is read from the live `runtime/state.json` before the copy is made. This read was there before
  this package. A switch landing between that read and the copy goes toward `history_gap`.
- Precision, not a defect: an unfinished store install journal has no instant of its own. It makes every answered
  stretch uncertain, although its installer journal's `created_at` could place it.
- No control covers these cases, each read in review against the writers:
  - an unfinished plan placed at `prepared_at` when it has no `created_at`;
  - a finished journal lacking `committed_at` or a usable pointer;
  - records whose timestamps are out of line order;
  - sidechain records widening a session's span.

## Controls

These extend section "relhist: the baseline-selection history":

- relhist 10, retargeted: a state that was not read leaves the tail `input_failed`; earlier stretches are answered
  as before.
- relhist 20, extended: the renames' base carries its basis. Two full `run`s (a Codex `--pin` and a pinned one) write
  it to `current.json`'s notes and the manifest. The unpinned run, D6 (b) and R8 now also require the basis.
- relhist 22, through the production path: one state with two installs. `runtime/state.json` is present, absent, not
  JSON, an array, or names a number. The answers are the baseline, `history_gap`, and `input_failed` three times.
- relhist 23, pure: journal ids whose name order is the reverse of their time give every answer as the time-ordered
  fixture.
- relhist 24: a Codex thread in two files on two sides of a switch. Each file is answered with its own baseline. The
  renames' base over the whole thread is `spans_switch`. `published_shared` now takes a thread in several files, as
  `published_run` does.
- relhist 25: a finished migration whose backup holds a file and a link. The history is read, the backup is not
  copied, and no `selection_history` omission is recorded.
- relhist 26: the published index crosses clean. An unpinned or Codex row relabelled `pin`, or a pinned row relabelled
  `selection_history`, is `RELEASE_BASIS_DIFFERS`.
- relhist 27: an unpinned session's context set equals the one it has with no history at all. A Codex session's
  names no history inventory. A pinned session's still holds its pin's release inventory.
- relhist 28: a journal directory linked to an empty one, and a file standing where a journal directory should be,
  each leave the history unread by name.
- M4, retargeted: each run's state carries a PLANNED store journal beside its transaction's own file. The seam must
  see exactly that `journal.json` taken, three runs over.

Work tool `pt-relhist.py` (not committed) runs revert rows over fresh copies, under a fake HOME and a short TMPDIR:

- 11 new rows: the basis left out of the notes; the manifest's basis dropped; an absent state read as unread; an
  unread tail answered; the switches left unordered; the first file only; whole directories frozen; the basis left
  unchecked; the history's inventory put in context sets; a linked directory listed; an unlistable directory skipped.
- 5 retargeted rows: rh10, rh17c, rh17d, rh19b, rh20b.
- 7 rows of commit 2 whose fixture or control changed: rh17a, rh17b, rh18a, rh18b, rh19a, rh19c, rh20a.

Each of the 23 rows is caught by the control it names. No block is cut and no row prints a traceback. The `none` row
passes.
