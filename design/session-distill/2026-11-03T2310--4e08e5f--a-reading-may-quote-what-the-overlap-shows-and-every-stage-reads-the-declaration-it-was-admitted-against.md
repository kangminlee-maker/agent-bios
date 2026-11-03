---
created_at: 2026-11-03T23:10:00+09:00
head: 4e08e5f
kind: review
supersedes: null
---

# A reading may quote what the overlap shows, and every stage reads the declaration it was admitted against

The X review of WP-08's first commit (round 1, on 637a6a1) returned rework with two major findings and one minor. Both
majors were reproduced on 4e08e5f before the change, with the actual functions. This commit fixes all three, together
with the reader that the second commit landed on top of the first.

## 1. Quoting is not owning

**Finding.** The read template allowed quotes only of the window's own records, and the reader refused any other entry.
But every owned occasion of an expected observation must cite its exposure (design §11). When a request, a guide read
and the action are split at a window boundary, the exposure is shown only in the overlap before the window, so there
was no faithful answer. The stitch resolves events only, so it could not repair this later.

**Reproduced.** An answer quoting the last entry of a window's overlap was refused with RECORD_INTEGRITY (no record this
window owns). The overlap entry carried no `segments` and no `json_pointer`, so `evidence.from_view` could not locate it
(KeyError). Log: `work/impl/wp08/logs/x1fix-repro-2.log` (author-side).

**Change.**
- `views.overlap_of` now records the overlap entry's `json_pointer` and the segments of what it shows. The cut is a
  prefix, so these are the entry's own segments ended at the cut (`shown_segments`).
- The reader separates the two questions:
  - `quotable_entries` holds everything the window shows: its own records and the overlap on both sides. A quote may
    name any of them.
  - `shown_entries` holds the window's own records. An event must start on one of them, and an observation's
    occasion must lie on one of them.
- A quote is located only in what that entry showed, and the evidence record keeps the entry's own role. Text the
  overlap cut off does not locate (QUOTE_MISMATCH).
- `packets/read.md` says so: the owned records are the model's to report; the overlap belongs to the neighbouring
  windows and may be quoted as shown, as evidence. The read packet's fixed part now leaves 1,731 of the 12,288
  overhead bytes.

**Against D-20261103-8bfd69.** This does not conflict with that decision, under which a window decides only its own
omissions. Quoting the overlap creates no decision and credits nothing. An overlap row's omitted interval stays with
the window that owns its record, and a quote can never cite omitted or cut text, because it must locate in what was
shown.

## 2. The declaration a stage reads is the one it was admitted against

**Finding.** `views.run` read run.json and derived its limits before it entered `records.run_stage`. An amendment of
the cap that landed between the two let run_stage pin the newer declaration while the windows were cut with the
older cap.

**Reproduced.** Amending `output_caps.S3` to 48,000 just before S2's admission gave windows cut with a reservation of
32,000 under a run.json at 48,000. S2's record and run.json were both at `declaration_seq` 1, so the declaration-order
check could not see the gap.

**Change.**
- `records.run_stage` hands the stage the declaration it read under the declaration lock, as
  `StageRun.declaration`.
- `views.run` derives its limits, window and context from that declaration, inside the stage.
- S3's reader is built from that declaration too, and `read.json` names its `declaration_seq`.
- The reader compares the cap the view's windows were cut for (`sequence.json` `limits.reservation`) with the cap its
  calls declare, and refuses a difference by name (WINDOW_CAP_MISMATCH) before any call.

## 3. Each answer-contract comparison has a departure only it names

**Finding.** Two comparisons in `claims.answer_mismatch` could be removed without failing the claims self-test: the
window event's field set, and the observation verdict on its own.

**Reproduced.** Both removals left the self-test passing (`x1fix-repro-2.log`).

**Change.** Two mutations were added: a window event answering `stitched_from`, and a verdict the stored instance
cannot hold. Each fails by its own comparison's name.

## Controls

- **views:**
  - An amendment of the cap landing just before S2's admission is the cap the views record and their windows are cut
    with, under the declaration S2 recorded.
  - A quote of a cut overlap entry, and one of an overlap entry of a split span, is located and walks back to the copy
    with its role.
  - A cut overlap entry's segments end where its shown text ends.
  - A quote of what the overlap cut off is QUOTE_MISMATCH.
- **stage_read:**
  - A claim resting on a quote of the overlap before the window is kept, its evidence located in the overlap's shown
    stretch under that record's role.
  - The boundary case is answerable: an owned occasion whose exposure only the overlap shows, citing both.
  - An occasion, or an event, placed in the overlap is refused as another window's.
  - A quote of an entry the window does not show is refused.
  - WINDOW_CAP_MISMATCH is refused by name.
  - An amendment landing just before S3's admission is the declaration the reading runs under.
- **claims:** the two departures above.
