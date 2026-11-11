---
created_at: 2026-11-11T20:00:00+09:00
head: be48606
kind: design
supersedes: 2026-11-11T1900--18b483e--judge-b-reviews-each-absence-claim-over-every-flag-either-sweep-raised-and-fifty-negatives-the-run-id-draws.md
---

# WP-11 J3c: a flagged unit returns to both judges alone, and their disagreement makes the claim disputed

Plan WP-11 done-when 3, its last part (F-O4-03, F-O4-12c); design §6.2: "A unit flagged by either sweep or by Judge B
returns to both judges; disagreement makes the candidate disputed." No model call is made; every call goes to the
golden hosts.

## What returns, and in what shape (D-20261111-6573fb)

- **The returned units.** For every absence claim Judge B reviewed, the returned units are every flag either sweep
  raised and every unit B marked a match (`returned_of`). They are read from the kept cross-review.
- **Units only.** §6.2 returns units to the judges, not the candidate. A reconsideration therefore asks for the
  returned units' judgments and their matching units' following and contribution, and nothing about the candidate.
  - The first draft sent the full judgment packet and discarded its requirements and class answers. The lead
    rejected it: it pays for output nobody reads, and leaves a second, contradictory candidate answer in the run.
  - Admission stays the first judgment's.
- **The packet.** `packets/reconsider.md` shows the candidate, its claims and quotes, and the returned units with their
  context lines. It shows no ledger entry. Its rules for judging a unit are the judgment packet's words, and a control
  holds the two texts equal.
- **The schema.** `schemas/reconsider.schema.json` is `judge.schema.json`'s `units` and `matching_units` with the
  definitions they reach, closed (`reconsider_projection`). A control holds the file equal to the projection.
  - A candidate-level field is refused by the closed schema in a run (SCHEMA_INVALID).
  - `answer_problems(reconsider=True)` refuses one by FIELD_UNEXPECTED. In a run the schema refuses it first.
- **The calls.** Judge A and Judge B are sent one payload (N#1) as items `<item>-RA` and `<item>-RB`, in the dispatch
  class `reconsider`. The stage checks each answer as a first judgment's units and matching units. The accepted
  answer is kept under `reconsiderations/<item>/<A|B>.json` with the returned set and the payload hash.

## What the claim becomes

- **Diagnosis.** The claim is diagnosed again by `derive.candidate_diagnosis` at a complete reference point
  (`reconsidered_diagnosis`). It reads the units of the first judgments and the reconsidered ones.
  - A unit both judges now find matching makes the claim no gap.
  - A unit they disagree on that could reach a row before the gap makes it `unknown` by `disputed` (O4).
  - A claim nothing contradicts keeps its gap.
- **Nothing returned.** A claim whose cross-review returns nothing keeps its gap without a call.
- **A missing reconsideration.** A claim missing either judge's accepted reconsideration, or one judging other units
  than were returned, is RECONSIDERATION_MISSING. It is named and not diagnosed, and S6's record stays partial. A
  re-run calls only that judge again.

## The fixture

- **The cross-review.** The golden cross-review marks a match on the first unit both sweeps found unrelated
  (`flag_first_negative`). So every claim returns a unit only Judge B raised.
- **The three claims.**
  - In the first, both judges now match its first returned unit, which only one sweep flagged.
  - In the second, only Judge A matches it.
  - In the third, neither does.
- **The four golden runs.**
  1. A sweep is missing a pair.
  2. A cross-review is missing a unit.
  3. Judge B's reconsideration of the first claim also answers the candidate's requirements. It is refused by the
     schema on both attempts, and the claim is RECONSIDERATION_MISSING.
  4. The clean run calls only that reconsideration again.

## Controls

stage_judge's self-test goes from 133 to 156 controls; packet's from 51 to 53.

- **J3c pretrial.** 17 revert rows were run on the final shape, and all 17 were caught. On the first pass four were
  missed. Two expected control names had changed. Two controls raised on an empty result, and now fail by name: J2a's
  attempt-capacity control and J3c's fixture guard.
- **Equivalent mutant.** One more row turns off the stage check's reconsideration mode. It passes, as expected:
  the closed schema refuses a candidate-level field before the stage check reads it.
- **Partial-status row.** This row removes both the failed-call test and the missing-reconsideration test. A failed
  reconsideration call is also RECONSIDERATION_MISSING, so either test alone keeps the record partial.
- **No control covers N#1 here.** Removing the reconsideration receipts from `stage_receipts` is caught by no
  control. Both judges are sent one text by construction, so no run can make the receipts diverge.
- **Earlier rows.** The J3a (22) and J3b (15) rows were run again over the changed golden, and all were caught.
  Five of them needed new line text first.

## The 18:07 edit

J3a (18b483e) includes one edit made at 18:07 by this lane's earlier turn, between the lead's stop and resume. It
made `sweep_view` count the names it does not hold, and applied the prepared control patch. It was found in the
session transcript, checked and kept.

## For C3: the S6 sample (owner, D-20261111-4a455d)

The owner decided that C3 judges a stratified sample: formed `all`, g_cluster `all`, and legacy and redundancy_hint
at fixed sizes. The full population is judged at the release rehearsal through the reuse keys, and S6's budget is not
raised. The owner also decided that no further S2 runs on a C2 clone; a fresh inventory is measured at C3's own S2
run.

The budget taken is RR-1's S6 input of 3,500,000. C2's run.json declares no `budget.per_stage.S6`.

A call's input is `ceil((payload bytes + 9,000) / 2.27) + 3,795`: J0's density, its fixed bytes per call and Claude's
hermetic allowance. A candidate is two calls, one per judge. The payloads are C2's per-source medians.

| Source | Candidates | Median payload | One call | One candidate |
|---|---|---|---|---|
| formed | 7 | 180,635 B | 87,335 | 174,670 |
| g_cluster | 3 | 171,395 B | 83,265 | 166,530 |
| legacy | 142 | 167,961 B | 81,752 | 163,504 |
| redundancy_hint | 121 | 111,319 B | 56,799 | 113,598 |

- **The fixed part.** Formed and g_cluster in full come to 1,722,280, which leaves 1,777,720.
- **By input.** A legacy and redundancy_hint pair costs 277,102, so n = 6 of each fits.
  - The total is 3,384,892, leaving 115,108.
  - Seven of each would be 3,661,994, over the budget.
- **By spend.** Dispatch reserves a stage's budget as spend, and the next call's reservation has to fit what is left.
  This view adds output at J0's upper median of 10,933 tokens a call. It also keeps room for the last reservation:
  234,670, the largest call's spend at most at the 20,000 cap with one retry. Then n = 4 of each fits, totalling
  3,224,276.

The proposed C3 `judge.candidate_kinds` is `{"formed": "all", "g_cluster": "all", "legacy": 4, "redundancy_hint": 4}`
by spend, or 6 and 6 by input. The lead chooses. C3's `judge --dry` measures the drawn sample's packets before any
call. These figures count the judgment calls only. The sweeps, the cross-review and the reconsiderations add calls
only at a complete reference point.

## Next

J4: the derivations over the judgments and reconsiderations, the D5 gate controls, and done-when 2 through
`derive.admission`.
