---
created_at: 2026-11-10T18:46:00+09:00
head: 9164820
kind: design
supersedes: null
---

# A misdated switch inside another's stretch carries it on, and a record type that is no kind is activity

Package relhist, commit 5. It amends the commit-4 record
(`2026-11-10T1805--f8ecc36--a-record-with-no-instant-opens-the-sessions-span-and-a-switch-dated-backwards-is-held-from-the-previous-one.md`)
by this record only. Codex review W round 2 on `9164820` (`work/lead/relhist-w-r2-review.json`, verdict
fix_then_accept, the last round) found that round 1's two fixes hold for their simple cases. It accepted the six
metadata kinds and counting `summary` as activity, and found two new major defects. No product file changes;
`inventory.py` does.

## A misdated switch inside another's stretch (R1)

Commit 4 held a misdated switch's stretch from the previous switch to its later instant. A switch finishing inside
that stretch was taken in by it and handed its pointer on. When that switch was misdated too, its own later instant
was dropped.

The review's probe: A selected at 10, A->B started 50 and finished 20, B->C started 80 and finished 30, the state
selecting C. The stretch ended at 50, and a session at 60 was answered C, although B could still have been selected
then.

Now (`selection_history`):

- A switch finishing inside the stretch, misdated itself, carries the stretch on to its own start when that is later.
  This applies when it moves the pointer, or moves nothing but breaks the chain.
- Three things move to that start: the stretch's last piece's `to`, the cursor, and how far the stretch reaches.
  Later switches are judged against the stretch as carried on.
- A link that moves nothing and keeps the chain still carries nothing.
- The stretch keeps the key it already has, whatever carries it on: `switch_misdated` when a misdated switch opened
  it, `history_gap` when a misdated broken link did.

## A record type that is no kind (R2)

`span_openings` asked whether an undated record's `type` was in `METADATA_KINDS` by set membership. A `type` that is a
list or an object raised `TypeError`. That check runs outside `transcript_events`' acquisition handler, and for
pinned sessions too, so one such line stopped the whole inventory.

Now `_metadata` holds a record to be metadata only when its `type` is a string in `METADATA_KINDS`. A `type` of any
other shape is no kind, so the record counts as activity and opens the span like any other.

## Controls

These extend section "relhist: the baseline-selection history":

- relhist 33, pure, over writer-shaped installs (ISO `recovered_at`, integer installer `created_at`): A at 10, A->B
  dated 50 and finished 20, and a third journal:
  - B->C dated 80 and finished 30: answers at 25, 45 and 60 are `switch_misdated`, at 85 C;
  - the same with C->D dated 55 and finished 60, inside the stretch as carried on: inside it, D answered after;
  - B->C finished at 90, after the stretch: B is answered at 60, and 85 is in flight;
  - a plan C->C created 80 and committed 30, a broken link: `switch_misdated` up to 80, C after;
  - every time line is one ordered run, each stretch starting where the one before it ends.
- relhist 34, through the production path: undated records whose `type` is a list and an object, after the last dated
  record across the switch, are `session_partly_dated`. The run goes on and answers its dated session.

Work tool `pt-relhist.py` (not committed) runs revert rows over fresh copies, under a fake HOME and a short TMPDIR:

- 6 new rows: the absorbed switch not carrying the stretch; carrying it only when it moves the pointer; carrying it only
  when it breaks the chain; the reach not carried; the cursor not carried; the `type` shape unchecked.
- 3 retargeted rows: rh29b, rh29c and rh29d, whose line now asks `_metadata`.

Each of the 9 rows is caught by the control it names. No block is cut and no row prints a traceback. The `none` row
passes.

`work/impl/relhist/w2-repro.py TREE` (not committed) runs the review's two probes and these variants in memory over a
checkout's inventory module:

- On `9164820`:
  - a session at 60 is answered C in the absorbed-moving and absorbed-link shapes;
  - the list and object types raise `TypeError`.
- On this commit:
  - 60 is `switch_misdated` in both shapes;
  - the finish-90 shape answers B at 60 on both trees;
  - every type shape opens the span above.
