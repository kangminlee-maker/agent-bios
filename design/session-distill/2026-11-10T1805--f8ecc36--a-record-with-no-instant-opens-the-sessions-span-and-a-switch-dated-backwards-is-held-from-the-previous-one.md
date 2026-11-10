---
created_at: 2026-11-10T18:05:00+09:00
head: f8ecc36
kind: design
supersedes: null
---

# A record with no instant opens the session's span, and a switch dated backwards is held from the previous one

Package relhist, commit 4. It amends the commit-3 record
(`2026-11-10T1705--39e0643--the-selection-historys-answer-stays-out-of-context-sets-and-an-unread-state-leaves-the-tail-unknown.md`)
by this record only. Codex review W round 1 on `f8ecc36` (`work/lead/relhist-w-r1c-review.json`, verdict
fix_then_accept) found the eight interim findings fixed and two new major findings. Both could give a baseline with
no reason from timing evidence that does not support it. No product file changes; `inventory.py` does.

## A record with no instant (W1, D-20261110-4a0d15)

Before this commit a session's span was the first and last instant its records carry. A complete line that did not
decode, or a record with no usable instant, was left out of it. When such a record lay after the last dated one, the
span could stop short of a switch the session reached. The review's probe gave a complete catalog row for the old
baseline in that case.

The rule now (`span_openings`, `history_of`):

- Three kinds of record can open the span:
  - a complete line that does not decode;
  - a record whose time field is there but is not an instant (a zone-less string, a value of another type);
  - a record with no time field at all, unless its kind is one the host writes as metadata (below).
- Line order places such a record, as `brackets` places an undated event (S-5, R1 #4):
  - it opens the span above unless a later dated record bounds it, with the instants rising from the first record up
    to that one (`brackets`' `(after, ok)`);
  - it opens the span below unless an earlier dated record bounds it, with the instants rising from that one to the
    last (the mirror).
  - So a record between two dated ones of a rising transcript opens nothing. A step back between its two bounds opens
    both sides, and a step back before them opens the side above.
- An open side reaches the start or the end of time. `history_of` answers a baseline only when the dated span and
  the opened span give the same answer. Otherwise the answer is `uncertain: session_partly_dated`.
- A dated span that already gives a reason keeps it.
- A Codex thread opens where any of its files does: the renames' base is taken over the union of its files' spans
  and openings. In the release index each file is answered over its own span and openings, as before.
- A partial trailing line is still no part of the transcript (D-20261103-8facee).

The metadata kinds (`METADATA_KINDS`) come from this repository only; the owner's corpus was not read.

- Claude: `mode`, `permission-mode`, `atis-latch`, `file-history-snapshot`, `ai-title`, `last-prompt`.
  - These are the head kinds `session-distill/runlib/census.py` `fx_claude` models with no time field.
  - `session-distill/runlib/lineage.py` `HEAD_INHERIT` and its self-test hold that `ai-title` and `last-prompt` are
    written only after a turn and can stand after the first user record.
  - Each is a kind `wrappers/claude_hermetic_evidence.py` `RECORD_KINDS` measured for 2.1.304.
- Codex: none. `fx_codex` writes a time on every record.
- Any other kind, an unknown one included, counts as activity. No source in this repository names Claude's `summary`
  record, so it is not excluded.

## A switch dated backwards (W2)

Before this commit a finished switch whose start was after its end was clamped to `[end, nextafter(end))`. A session
between the two instants was answered with the new baseline. The writers use the wall clock, so a clock stepped back
between a plan's creation and its commit gives this order.

Now (`selection_history`):

- A switch whose start is after its end is `misdated`. This covers a plan's `created_at`, and an install narrowed by
  an installer journal whose `created_at` is later than the install's end.
- Its uncertain window, `switch_misdated`, runs from the previous switch (as for an install with no start) to the
  later of its two instants.
- A link that moves nothing and breaks the chain holds its `history_gap` up to that later instant too.
- When the widened stretch reaches past later switches, this commit chose to keep the time line ordered:
  - a switch that finishes inside the stretch is inside it, with no window of its own;
  - the pointer it leaves is what the stretch hands on;
  - a switch finishing after the stretch starts its window no earlier than the stretch's end, as every window starts
    no earlier than the one before.
  - A broken chain inside the stretch is not named separately: the stretch stays `switch_misdated` (uncertain), not
    `history_gap` (unknown). Neither answers a baseline.
- Ties are as before: two moving switches finishing in one second are one `switch_tie` window. When the later one is
  misdated, that window reaches its later instant.

## The clock assumption

Journal and transcript instants are assumed to come from one clock that did not step back. A step back is seen only in
two places:

- where a journal's start follows its finish (`switch_misdated`);
- where a transcript's instants step back, which opens a record's sides as above.

A step back hidden between two consistent instants is not seen. The commit-3 record's continuity assumption is
unchanged.

## Notes

- Codex W r1 noted that `hash_tree`'s whole-root manifest can still list omission paths inside a migration's backup.
  That manifest was there before this package and does not depend on the journal acquisition, so it is unchanged.
- `freeze_inputs` still maps `NO_POINTER` to `UNREAD_POINTER`, although `selection_history` treats both alike. It is
  left as it is, so that `NO_POINTER` stays a value only a journal names.

## Controls

These extend section "relhist: the baseline-selection history":

- relhist 29, through the production path, over the tail fixture's state (ref-ha until the install of 10-03 10:00,
  ref-hb after):
  - the dated passing case answers ref-ha;
  - each of these after the last dated record, across the switch, is `session_partly_dated`: a line that does not
    decode, an undated turn, a zone-less one;
  - an undated turn before the first dated record is `session_partly_dated`;
  - each of these keeps the answer: a line between two dated records, an `ai-title` with no time field, an opening
    that stays inside the stretch after the last switch;
  - a step back between a line's bounds opens both sides, and a step back before them opens the side above.
- relhist 30: a Codex thread in two files. The first file alone answers ref-ha. The second file's undecodable last
  line makes that file `session_partly_dated`, and the renames' base over the thread too.
- relhist 31, pure:
  - a misdated plan, an install narrowed by a later installer journal, a misdated plan whose stretch reaches past the
    next switch, and a misdated broken link with a switch finishing inside its gap, each with sessions inside the
    widened stretch and after it;
  - the passing history answers as before;
  - every time line is one ordered run, each stretch starting where the one before it ends.
- relhist 32, through the production path: an installer journal dated after its install finished leaves a session
  before it `switch_misdated`, and a session after the later instant answered.
- The vocabulary's expected set gains `session_partly_dated` and `switch_misdated`. Each is carried by a document this
  suite's runs wrote.

Work tool `pt-relhist.py` (not committed) runs revert rows over fresh copies, under a fake HOME and a short TMPDIR:

- 19 new rows:
  - an undecodable line placed;
  - a bad time field read as none;
  - metadata opening;
  - an undated turn placed;
  - each side unbracketed;
  - the side before the first left closed;
  - the mirror ignored;
  - a step back before the line ignored above;
  - the opened span unchecked;
  - every opening made uncertain;
  - openings unrecorded;
  - the first file's openings only;
  - misdating unseen;
  - the stretch ending at the finish;
  - the stretch starting at the finish;
  - a switch inside the stretch not held by it;
  - each of the two places that record how far the stretch reaches, unset.
- 2 retargeted rows: rh3 and rh4b.

Each of the 21 rows is caught by the control it names. No block is cut and no row prints a traceback. The `none` row
passes.
