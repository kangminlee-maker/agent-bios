---
created_at: 2026-11-05T21:05:00+09:00
head: a933acb
kind: design
supersedes: null
---

# Under the short labels no copy was refused, and DW5 judged as its fixture intends

WP-08b's live results: the dw2 leg and then the dw5 leg, run as one pair (`live1`, 2026-11-05 21:00:14 to 21:02:58)
on `a933acb`.
- **Host.** Claude Code 2.1.317, checked before and after each leg.
- **Seat.** S3 `claude:claude-sonnet-5-5/high`.
- **Inputs.** Both legs are fixtures; nothing of the owner's sessions was sent.
- **Numbers.** Counts, bytes, tokens and codes. The judgements are the fixture's, so they are given.

## Bounds

The owner's limits for the pair are 9 Claude calls, 80,000 input tokens and 20,000 output tokens (D-20261105-7dbc98).
Input counts cache reads and cache creation. They were held in code by a development tool outside the repository
(`work/impl/wp08b/live-pair.sh` with `live-leg.py --pair`):
- **Calls.** Each leg's cap is its planned calls plus one retry: dw2 4, dw5 4.
- **The pair guard.** Before each reservation, the guard adds what the pair has measured to one more call's share
  (15,000 input, 7,000 output). The reservation is refused (PAIR_LIMIT) unless the total fits the limits.
  - A call with no measured usage counts as one share.
  - **Limit.** The guard bounds which calls start, not what one call spends. A call larger than one share overshoots
    by its excess. The declared output cap of one call is 32,000.
- **Between the legs.** dw5 starts only if dw2 read its unit whole and leaves room for dw5's plan: 34,760 input (the
  high estimates of its three golden packets) and 9,000 output.
- **S3 budget.** It is 100,000 for each leg and only admits calls. The dispatcher reserves twice the largest call so
  far, so at 45,000 dw5 would have stopped before its second window.

The guard never refused. dw5 started with dw2's measured 23,160 input and 3,809 output carried in.

## The calls

Every call was accepted at its first attempt with one request.

| Leg | Call | Driver bytes | Input | Output |
| --- | --- | --- | --- | --- |
| dw2 | window w1 | 14,273 | 7,467 | 1,773 |
| dw2 | expansion | 17,962 | 8,419 | 1,312 |
| dw2 | stitch | 14,147 | 7,274 | 724 |
| dw5 | window w1 | 27,845 | 11,305 | 3,383 |
| dw5 | window w2 | 18,772 | 9,027 | 2,867 |
| dw5 | expansion | 19,700 | 9,477 | 1,095 |
| dw5 | stitch | 11,204 | 6,134 | 714 |
| **pair** | **7 calls** | **123,903** | **59,103** | **11,868** |

**Golden match.** The five window and expansion packets have the driver bytes of their golden runs, which the dry runs
had confirmed for each first window. The stitch packets depend on the events the reader writes, so no golden run fixes
them.

**The input estimate.** Six of the seven inputs are within 400 tokens of the base line, 1,437 + 0.411 × driver bytes.
The seventh, dw5's first window, came in 1,576 below it.

## Copying under the short labels

- No label the packet did not show was written (UNKNOWN_LABEL 0).
- No answer was refused by the schema (SCHEMA_INVALID 0).
- No stage check failed, and there were no retries.

For comparison, WP-08's legs (`2026-11-04T1922`):
- Under the bracketed heading (dw2-live2 and apart-live1, 11 calls), three answers were refused for ids copied wrong.
- Under the `entry:` line (10 calls), none was.

Here, under the labels, none of 7 was.

## dw2: done-when 2

- The unit is read_complete.
- The carried event `pe-1` is resolved by two claims of the expansion. Their two quotes are on line 3 (the clipped
  result's record) and line 4.
- The reader also wrote two events of its own. The stitch resolved one; the other (`…9835b10b83a2`) stays unresolved
  and is pending after the coverage fold.
- This is the shape of WP-08's dw2-live2, which met done-when 2. It holds here too.

**A correction to the pair report.** The report's dw2 line says "not met". The report required that no pending event
be left after the fold, which is stricter than done-when 2. The log is left as written.

## dw5: the follow-up half of WP-08's done-when 5

- The unit is read_complete.
- Both due observations were offered as `x1` and `x2`.
- The search forced the expansion (search_forced 1).
- Six instances were recorded on a source basis.

| Occasion | Intended | Live | Cited lines |
| --- | --- | --- | --- |
| ask 1 (line 3) | exposure_unknown, observed | exposure_unknown, observed | 3, 4, 5 |
| ask 2 (line 9) | eligible, observed | eligible, observed | 5, 9, 10 |
| ask 3 (line 13) | eligible, not observed | eligible, not observed | 5, 13, 14, 15 |
| asked again (line 15) | none | eligible, observed | 5, 15, 16 |
| ask 4 (line 20) | exposure_unknown, observed | exposure_unknown, observed | 20, 21 |
| test run (line 26), T-1 | exposure_unknown, not observed | exposure_unknown, not observed | 26 |

**Judgements.**
- All five intended judgements came out as intended.
- **Ask 1.** The reader kept it as exposure_unknown rather than leaving it out. Its evidence includes the guide's read
  on line 5, after the ask. read.md and D-20261104-6df529 give different rules for such an occasion; the lead holds
  that in the backlog.
- **One more occasion.** Line 15 is the person asking again for a simpler telling. It meets P-1's occasion criteria,
  and the reader judged it eligible and observed: line 16 answers in plain words. The fixture's intent missed this
  occasion. Since it is eligible and observed, it changes no resolution.

**Citations.** The reader cited the records the golden readings cite (`2026-11-05T2047`): each ask and the answer
after it, the guide's read for an eligible ask, and the asking again for ask 3.

**Resolutions.** Code derived both as intended:
- P-1 is not observed: eligible 3, observed 2, not observed 1, exposure_unknown 2.
- T-1 is pending: exposure_unknown 1.

**Events.** The reader wrote two events in dw5's windows, so the leg made a stitch call its golden run does not. Both
events were resolved, and the fold leaves none pending. That used dw5's fourth call, so no retry was left.

## The expansion gap, live

The design-defect candidate of `2026-11-05T2017` (scope narrowed in `2026-11-05T2047`) came out live as expected.
- T-1's occasion was judged only in the expansion: exposure_unknown and not observed. So T-1 is pending.
- The window did not judge T-1. No exposure differed, and no reading conflicted.
- T-1 is the first kind of the narrowed gap: its exposure, the guide's read, lies outside the expansion.

## The pair's surroundings

- **The real roots.** The names under the real `~/.claude` and `~/.codex` changed during the run. The changed paths
  belonged to other sessions and other projects.
  - The one new `sessions/` entry belongs to a process that was still running after the pair. It leads its own group,
    which is none of the seven host groups the pair started.
  - All seven host groups had exited.
- **The cells.** Each cell root was left empty.
- **The checkout.** The run left `__pycache__` in it, and that was removed.

## The DW5 pretrial's search-term row

In `e54cfe8`'s pretrial, the row that broke T-1's retrieval term failed only the placement control, not the instance
control. That is right:
- DW5's golden plan expands every omission of its own, so the expansion runs without the search.
- The fixture's readings judge T-1 only in an expansion.
- So T-1's instance still comes from the expansion, and the instance control (which checks that) holds.
- Whether the search forced the expansion is held by the placement control's `searched.forced`, which failed.
