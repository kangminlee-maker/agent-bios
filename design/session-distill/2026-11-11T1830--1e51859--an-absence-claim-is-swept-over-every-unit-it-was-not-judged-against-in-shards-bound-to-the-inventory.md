---
created_at: 2026-11-11T18:30:00+09:00
head: 1e51859
kind: design
supersedes: 2026-11-11T1745--d1fa430--no-judgment-is-reused-across-runs-or-judges-and-the-later-reference-point-call-waits-for-a-release-retrieval.md
---

# WP-11 J3a: an absence claim is swept over every unit it was not judged against, in shards bound to the inventory

Plan WP-11 done-when 6 and the sweep half of done-when 3; design §6.2's absence sweeps. The lead's decisions E1, E2
and E3 (2026-11-11), all defaults. No model call is made; every call goes to the golden hosts.

## Where the sweeps run (D-20261111-f2bc92)

The sweeps run inside S6's one run, after the judgments and before the record closes. A separate stage or S6 part
was closed: design §4 puts the sweeps in S6, a sweep needs the same run's judgments, and `records.STAGE_PARTS` is a
shared module lane L is editing. The dry measure is part of `distill.py judge --dry` (`judgments/dry.json`,
`sweep_upper_bound`).

## What is swept

- **Absence claims.** A judged candidate is an absence claim when no unit matches it by both judges, read as derive
  reads them (`agreed`, `unit_diagnosis`, `candidate_diagnosis` gives `gap`; `absent_candidates`). A unit the judges
  disagree on could cover the candidate, so it is not an absence claim. A candidate either judge did not judge is
  not swept, and is named.
- **Incomplete reference point.** At a reference point the absence policy reads as incomplete, every absence is
  `unknown`, no claim stands and nothing is swept. Under the `literal` policy that is C2's case.
- **Remaining units.** A claim's remaining units are the units S5 indexes (one per text in each layer) less the ones
  S5 retrieved for it. Every indexed layer counts under `literal`; a `scoped` policy limits them to its layers.
- **Groups and shards.** The claims are taken `candidates_per_shard` at a time in id order (E2: 5). Each group's
  remaining units, the union of its candidates', are cut `shard_units` at a time in unit id order (E2: 100). A shard
  names, for each candidate, only the units of it that are that candidate's remaining ones (E3).
  `shard_problems` refuses a plan where a candidate is in no group or two, or a remaining unit is in no shard of its
  group or two (SET_MISMATCH).
- **Calls.** Each shard goes to `seats.S6.sweep_a` (claude-sonnet-5-5/medium) and `seats.S6.sweep_b`
  (gpt-6-luna/medium) with one payload (N#1). The payload carries the inventory's hash, so a moved inventory is a new
  payload and no earlier attempt answers it. The output cap is 20,000 by default, declared on every sweep call.
- **Checks.** `sweep_problems` requires every listed pair judged exactly once (SWEEP_PAIR_MISSING, SWEEP_PAIR_TWICE),
  no other pair (SWEEP_PAIR_UNLISTED) and labels the packet shows (UNKNOWN_LABEL). An accepted answer is kept in the
  stores' ids under `sweeps/<group>/<shard>/<a|b>.json` with the inventory hash. `kept_sweep` refuses a result cut
  from another inventory (SWEEP_INVENTORY_MOVED).
- **Declaration.** run.json's `sweeps.{shard_units, candidates_per_shard, output_cap}` are optional integers
  (declare refuses an integral float). The summary says whether each value was declared or defaulted. The declare
  fixture seats both sweeps as seats.json pins them for S6.

## What a sweep is shown

A formed candidate is shown by its lesson, type, situation, action and exception. A lifecycle candidate is shown by
its record without its ids, with the texts of the ledger entries and units it names. A name the stores do not hold is
counted (`names_not_held`), as S5 counts a named unit it does not hold. The first version refused such a name as
RECORD_INTEGRITY; the C2 measurement below met one.

## The dry upper bound

Gap candidates exist only after judging, so `--dry` reports the bound the lead asked for. It takes every judged
candidate as a gap, its remaining units being the catalog layer's indexed units less its retrieved ones. It reports
groups, shards, calls, pairs, payload and driver bytes, input tokens at J0's density of 2.27 bytes a token, and output
at the cap, labelled as the bound. It was not measured on C2, and will not be.

## C2: four inventory re-runs outside the owner's approval

The C2 measurements of J0, J1b2 (twice) and this commit each ran S2's inventory part on an APFS clone, at 14:17,
15:56, 16:05 and 17:56. The clones lived under the mode-700 work directory and were removed. The fake environment
moved every configured root, but the inventory opens each bound census row's absolute path. So each run read up to
6,633 of the owner's live session files. Under D-20261103-c2f013 each such read is the owner's to approve; C2's
acquisition was approved, these re-runs were not. The lead has disclosed it to the owner, and the approved re-run is
the lead's.

The 17:56 run stopped before the bound, on the RECORD_INTEGRITY a re-made inventory met.

## Controls

stage_judge's self-test goes from 91 to 116 controls, declare's from 130 to 133, packet's from 47 to 49. Pretrial: 23
revert rows. The first pass caught 22. The miss was the template's registration in `packet.TEMPLATES`: `packet.render`
does not read that list, so S6 ran without it. A control now holds the sweep template registered with its three
placeholders, and its row was caught on re-run.

Before the pretrial, two expectations were computed through the functions under test (`remaining_of`). Reverting one
would have moved both sides. They are now computed from S5's index directly.

## Next

J3b: Judge B's cross-review per absence claim, with every partial flag either sweep raised and fifty negatives drawn by
the run id. J3c: the reconsiderations by both judges.
