---
created_at: 2026-11-10T15:30:00+09:00
head: d489c76
kind: design
supersedes: null
---

# An unpinned or Codex session's release is the baseline the library selected at its time, marked as the selection history

Package relhist, commit 2 of 2 (brief `work/lead/relhist-brief.md`; lead decision D-20261110-9c60bc). Commit 1
(`2026-11-10T1450--368ab6c--...`) built the baseline-selection history from the switch journals. This commit puts
it in the release index and in the renames' base. No product file changes; `inventory.py` and its schema do.

It amends b2c8ef1 in two places, by this record only:

- §3.12. An unpinned session's release catalog and adopted packages are no longer
  `unknown: release_history_deferred`. They are the history's answer.
- §3.3. A Codex session's catalog and adopted packages follow the same rule. Its selection, overlays and injection
  stay `id_space`.

## What lands

- Acquisition (`freeze_inputs`, done-when 5).
  - The four journal directories (`runtime/transactions`, `runtime/installer-transactions`, `runtime/resets`,
    `runtime/migrations`) are frozen like every other input, under the new optional input `selection_history`.
    The history is read from the copy, against the frozen runtime state's pointer.
  - Every baseline the history answers is frozen once under its own key. So the release inventory a session is
    answered with is published as a pinned session's own is.
  - When a journal directory cannot be copied (for instance, a link), the history is not read. Every answer is then
    `input_failed`, because a missing journal may hide a switch. A run given no state answers `input_unread`.
- A session's time (`transcript_events`): the first and last instants its transcript records, from every record's
  timestamp.
- The answer (`history_of`, called from `bind_transcripts`). It covers every Codex session and every Claude session
  whose selection is `unpinned`. The answer is the baseline of the history piece holding the session's first and
  last instants (commit 1's `history_answer`), or the reason none is:
  - `history_absent` is answered for every session, whatever its instants, when the state holds no finished store
    journal;
  - a session with no instant gets its transcript's read failure when the transcript was not read,
    `session_undated` otherwise;
  - the answered baseline is registered for publication.
- The rows (`static_rows`).
  - A release row that names an inventory now carries `basis`. It is `pin` for a pinned session's own snapshot's
    release and selection. It is `selection_history` for the history's answer: what the owner's library held at the
    session's time, not what the session received.
  - A reason the history gives is the row's, with no source. An uncertain one carries the `uncertain: ` prefix
    (S-21).
  - Overlays keep the selection's reason (`unpinned`, `id_space`).
  - The schema's `release_source` declares `basis` (`pin`, `selection_history`). Its `dependentRequired` makes
    `inventory_ref` require `layer` and `basis`, and `basis` require `inventory_ref`.
- The renames' base (`renames_base`).
  - A Codex `--pin`, and a Claude one whose session is unpinned, take the release the history answers over every
    file of that session, or its reason.
  - A run with no `--pin` is `no_pin_given`. It was `release_history_deferred`, whose text said a follow-up package
    would build the history.
- Vocabulary.
  - `release_history_deferred` is gone. In its place: `history_absent`, `before_first_switch`, `history_gap`,
    `session_undated`, `switch_in_flight`, `switch_recovered`, `switch_tie`, `spans_switch`, `journal_unfinished`,
    `no_pin_given`.
  - The vocabulary control reads a release row's uncertain reason behind its prefix, as a row carries it.

WP-10 decides whether a `selection_history` row counts as delivery evidence (§6.3). Under private installation only
an activated session receives agent-bios content.

## Controls

These extend section "relhist: the baseline-selection history":

- relhist 17 to 21 run one fixture state through the production path (`published_shared`: `freeze_inputs`,
  `bind_transcripts`, the shared inventories and the release index, crossed and written). Its journals give every
  answer: two installs with installer journals, a recovered rollback, two plans in one second, a plan after a gap,
  and a PREPARED one.
  - 17, the basis mark: an unpinned Claude session, a Codex session and a pinned session, and the release
    inventories published.
  - 18: each reason in a session's rows.
  - 19: a state with no finished journal, no state, and a linked journal directory.
  - 20: the renames' base for no `--pin`, a Codex one, an unpinned one, a pinned one, and one across a switch.
  - 21: every journal read through `read_source` lies under the run's frozen directory.
- Retargeted controls:
  - M4 now requires each run to take the journals through `freeze` (the seam) instead of not at all.
  - The unpinned run, X1, X7 and M4's rows expect `history_absent`, because the fixture's state holds no finished
    journal.
  - X12 has a case per `dependentRequired` entry, `basis` included. A source missing its inventory drops the other
    trigger, so each refusal is one trigger's.

Work tool `pt-relhist.py` (not committed) runs 32 revert rows over fresh copies, under a fake HOME and a short TMPDIR.
Thirteen rows are this commit's: an unmarked basis, an answer left unpublished, journals not frozen, journals read
live, instants not recorded, a read failure unnamed, stateless answered as failed, a failed copy read anyway, the
absent history not answered first, a Codex `--pin` by its selection, no `--pin` unnamed, the vocabulary's prefix
unread, and the schema not requiring `basis`. The other 19 are commit 1's rows, rerun on this tree.

Every row is caught by the control it names, no block is cut, and none prints a traceback. The `none` row passes.
