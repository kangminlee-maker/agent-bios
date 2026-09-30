---
created_at: 2026-09-30T15:13:54+09:00
head: 3851a9a
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20260930-5d1abb
---

# V1's second bound review found two recovery paths that fail silently, and both are repaired

This follows the [12:52 direct-use record](2026-09-30T1252--6676966--v1-acceptance-both-hosts-direct-use-record.md).
V1 was recorded into `run-11` at `3851a9a`, with all 21 cases passed. `run-11` is `run-10` without
V1's first, unpublished attempt. Its one bound review was dispatched to `gpt-6-astra` at max
effort, hermetic and read-only, from 12:58:20 to 13:22:24, with the recorded commit's source in the
packet.

The review returned `defects_found`: two findings, and 20 stated checks. It found that:

- every digest the record states recomputes, including 76 file hashes and the source tree identity;
- the 21 outcomes are what the logs show;
- publishing would unaccept neither P00 nor P01.

V1's pending attempt in `run-11` is therefore not published, and V1 is recorded again, in a new
run, after this repair.

## What the review found, re-derived here

1. **Medium: an identical request that overlaps another runs twice** (done-when [1] and [10]).
   - **The reviewer's case.** It scheduled a second submission of the same request to finish
     after the first had looked the request up and before the first opened its unit of work.
     Both ran, the journal held two receipts for one request id, and the later answer replaced
     the original.
   - **In the code.** `journal.layer_journal` read `held()` before `store.unit()`. The unit takes
     SQLite's write lock (`BEGIN IMMEDIATE`), which orders the two units but was never asked the
     question again.
   - **The contract.** C03 says a repeated request gets the original result and receipt.
2. **Medium: the entry's check is asked once only** (done-when [8] and [10]).
   - **The reviewer's case.** After a check answered `unknown`, Enter on "Check this request"
     dispatched nothing and showed nothing. The start stayed held back, so the person could not
     start until the entry was opened again.
   - **In the code.** `Entry.check` returned whenever `self.checking` was set, whether or not its
     query had been answered.

## What the owner chose

Both are fixed before V1 is recorded again (`D-20260930-5d1abb`). Two alternatives are closed:

- fixing the check only and deferring the overlap;
- accepting V1 with both as known defects.

## What changed

- **`workenv/journal.py`.**
  - `repeated(call, store, digest)` states step 2 once: a conflict where the held request's bytes
    differ, its original answer where it was answered, or nothing where it is not held or is
    pending.
  - `layer_journal` asks it first, as before. It asks again as the first thing inside the unit of
    work, under the write lock; an answer found there leaves the unit without writing.
  - `_Refused` is `_Unwritten`, since the held answer leaves the same way.
  - The module docstring's step 2 says so.
- **`workenv/tui.py`.** `Entry.check` dispatches nothing only while its query is unanswered or
  once it found the start settled. An `unknown` or `unavailable` answer lets Enter ask again, and
  the check shows `executing` / `pending` again. The docstring's dispatch paragraph says so.
- **Tests.**
  - `test_journal.py`: an identical request answered while this one waited is its answer. The test
    runs the reviewer's interleaving by having the first `held()` run the second submission to its
    end. It checks one entry call, one receipt, and the query returning that answer.
  - `test_tui.py`: a check answered without settling its start can be asked again (`unknown` and
    `unavailable`), and a settled one is not.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1v.py`, `mutate_v1v.txt`) caught all 5 mutations:
  - no second look under the lock;
  - the second look ignoring an answered request;
  - a check asked once only;
  - a settled check asked again;
  - a check in flight asked again.
- **The earlier sweeps, re-run on this tree:** `mutate_v1r.py` 8 of 8 and `mutate_v1u.py` 24 of 24
  caught (`mutate_v1r-rerun-v1v.txt`, `mutate_v1u-rerun-v1v.txt`).
- **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`: 837 outcomes, 61 passed, 764 blocked, 12 failed)
  are identical before and after. V1's 21 pass.
- **Bindings.** `cases.py --bindings` emits the same binding as `run-11` holds frozen for all 13
  profiles, so P01 is not reopened.

## Next

1. **A short real use on both hosts** with the committed code, so the direct-use evidence ran the
   recorded product code.
2. **`run-12`:** `run-11` without V1's attempt, kept as evidence.
3. **V1 recorded again,** and one bound review.
