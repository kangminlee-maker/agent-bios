---
created_at: 2026-11-11T19:00:00+09:00
head: 18b483e
kind: design
supersedes: 2026-11-11T1830--1e51859--an-absence-claim-is-swept-over-every-unit-it-was-not-judged-against-in-shards-bound-to-the-inventory.md
---

# WP-11 J3b: Judge B reviews each absence claim over every flag either sweep raised and fifty negatives the run id draws

Plan WP-11 done-when 3 (F10); design §6.2's cross-review. No model call is made; every call goes to the golden hosts.

## What is reviewed

- **When.** The cross-review runs inside S6's one run, after the sweeps (`cross_stage`). Judge B reviews an absence
  claim only when every sweep of its group was accepted (D-20261111-c3cac9). The other choice was a review over the
  shards that finished. It was closed because a failed shard's flags are unknown, and done-when 3 requires every flag.
  Such a claim is named `not_reviewed`, and S6's record stays partial. The re-run reviews it once those sweeps are
  accepted. A claim with no remaining unit is named and not reviewed.
- **Flags.** A unit is a flag when either sweep marked its situation or its action as a match (`flags_of`).
- **Negatives.** The fifty negatives are drawn from the units both sweeps marked as no match (`negatives_of`). They are
  the first fifty by sha256 of the run id, the candidate and the unit. A claim with fewer than fifty such units is
  shown all of them.
- **The packet.** `packets/cross_review.md` shows the candidate as the sweeps saw it (`sweep_view`). It shows each
  flagged and sampled unit with its layer, path, heading, text and both sweeps' marks and reasons. Labels are k1 and
  n1, ...; no stored id is shown.
- **The call.** The seat is `seats.S6.B`, the class `cross_review`, and the output cap the judge's 20,000. The answer
  is `schemas/cross_review.schema.json`: one verdict per unit, giving situation, action and a reason.

## Checks

- **The answer.** `cross_problems` requires every unit shown judged exactly once (CROSS_UNIT_MISSING,
  CROSS_UNIT_TWICE), and only by labels the packet shows (UNKNOWN_LABEL). It is the stage check on each attempt.
- **The kept record.** It is kept under `cross_review/<item>.json` with the seat, call id, seed, inventory hash,
  payload hash, flags, negatives and the verdicts in stored ids. Before it is written, `cross_review_problems` holds it
  to what the kept sweep results build now.
  - A flag the record lacks, or another sample of negatives, is CROSS_REVIEW_INCOMPLETE.
  - A payload hash other than the one the sweep results build is CROSS_REVIEW_STALE. This catches a mark or reason
    changed after the review was sent.
- **Reuse.** A re-run reuses an accepted review when its payload is unchanged. The payload carries both sweeps'
  marks and reasons, so a changed sweep result is a new call.

## The fixture

The golden library gains seventy catalog units (`fx_library(wide=70)`), so a claim has more than fifty negatives.
The sweeps are cut at 40 units and 3 candidates. Each fixture sweep flags a different unit, so a flag one sweep alone
raised is held. The three golden runs on one run directory are:

1. A sweep answer missing a pair. Its group's claims are not reviewed.
2. A cross-review answer missing a unit. That review fails both attempts by name, and the record stays partial.
3. The clean run. Only the failed review is called anew, and every other review is reused.

## Controls

stage_judge's self-test goes from 116 to 133 controls; packet's from 49 to 51. Pretrial ran 15 J3b revert rows. The
first pass missed two, and both were fixed in the control, not the row.

- **Flags.** The fixture's two sweeps flagged the same units, so "any sweep" and "both sweeps" could not be told
  apart. The sweeps now flag different units.
- **Seat.** A review sent to the wrong seat left no record. The control block then raised a KeyError, and no control
  was reported. The block now reads an empty record and fails by name.

The 23 J3a rows were run again over the wider golden, and all were caught. One J3a row needed a stronger edit:
removing the sweeps from the partial test is now masked. A failed sweep leaves its group's claims unreviewed, and
that alone makes the record partial. The row removes both paths.

## Next

J3c: the reconsiderations (design §6.2, the rest of plan done-when 3). A unit either sweep flagged, or Judge B's
cross-review marked as a match, returns to both judges (`reconsiderations/<candidate>/{A,B}.json`). A reconsideration
missing from one judge is RECONSIDERATION_MISSING, and a disagreement makes the candidate disputed. The golden
cross-review already plants one match no sweep raised (`Note step 7 of`).
