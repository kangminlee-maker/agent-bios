---
created_at: 2026-11-03T22:05:00+09:00
head: 6779ed7
kind: design
supersedes: null
---

# Plan amendment: WP-08 reads a unit file by file, stitches per unit, and derives the window resolution

This amends WP-08 of `2026-10-20T2119--cc0498f--implementation-plan.md`. That text was written on 2026-10-20. Since
then the run's unit became a root with every descendant at any depth (D-20261103-85f3e8), a Codex thread written in
several files became one session of ordered segments with coverage per file (D-20261103-a7128a), records appended
after their window ran became `appended` backlog with `unowned` disclosed (D-20261103-71a195), and a line became one
file's coordinate (D-20261103-536a52). WP-08's stage 0 (2026-11-03) compared the plan's
eight done-when items and its artifacts list with the code at 6779ed7. The lead approved items 2.1 to 2.12 on
2026-11-03, with four additions that are written into rows 1, 6, 7 and 9 below. The owner answered 2.13 (D-20261103-4b967e)
and the live-call budget (D-20261103-3e34be).

## What changes

| # | Plan text (10-20) | Amended |
|---|---|---|
| 1 | "one stitch call per session" | **One stitch per unit.** It runs after every window of every member file has a result. Pending events are ordered by (segment order, line) within a file and by record instant across the unit's members. When a unit's pending events and later claims do not fit one call's bound, the unit is stitched in shards, and one rule holds: an event is carried through the shards to the last one and is resolved there, or it ends `unresolved`. The rule gets its control in the stitch commit. |
| 2 | `claims/<transcript>.jsonl`, `events/<transcript>.jsonl` | Keyed by the **file's view name**, from its coverage key (`codex:<id>@<stem>` for a file of a Codex thread). Each unit also gets `read/<unit>.json`. |
| 3 | "reconciliation of each session's reading status back into the census" | S3 writes **`read-results.json`**, the input of `coverage.apply_results`: one result per unit, with readings per file and terminal statuses. S3 dry-folds it against the run's coverage state, so a result that does not fit is refused in S3 rather than in S12. S12 promotes it. The census is S1's record and is not rewritten. |
| 4 | (silent) | `appended` and earlier-window ranges reach S3 as `backlog(w)` records and are credited to `(file, version, w)`. An old-version backlog of a rewritten file is never viewed, so such a unit ends `read_partial` with those versions listed. No new rule. |
| 5 | basis `incomplete` for a scope with a partial, failed, deferred, unreadable, unknown-provenance or known-absent session | The scope is made of **units with every member**. A resolution about window w is also `incomplete` when the census reports records owned by w that no run will process (`unowned`). |
| 6 | done-when 5: the §11 resolution fixtures run through `measures.derive_resolution` (WP-21), and the live seeded path is "resolved by code (WP-21), rendered and closed into the ledger" | **`measures.derive_resolution`**, §11's four rules as pure code, is built in WP-08 together with its O9 fixtures. WP-21 stores and consumes it. "Rendered and closed into the ledger" moves to **WP-21** (render and ledger close) and to **WP-23** (the rehearsal's live seeded path through render and close). WP-08 asserts each instance and the resolution derived from it. It renders nothing and closes nothing. |
| 7 | (the cap had no declared home; `distill.py views --output-cap`) | **`run.json` `output_caps.S3`**, read by S2 when it cuts windows and by S3 when it calls. An amendment of it is accepted and makes S2 and every later recorded stage stale, because the windows were cut against that cap. |
| 8 | done-when 6: "concurrency 12 honoured" | A golden semaphore probe proves that at most 12 calls are in flight. The live three-window leg runs inside the calibration tranche, serial and provisional, and is reported as calibration. |
| 9 | (silent) | A unit can owe records to the window and still cut no window, because none of the owed records holds a content block. S3 credits those ranges as read and processed by code, without a call, and ends the unit `read_complete`. The run record counts such units with their reasons, and the C1 page shows the count. |
| 10 | done-when 5: "the search forcing expansions" | S3 computes `forced_by_search` per file, from the retrieval terms of the expected observations due, before it checks a window's decisions. |
| 11 | done-when 1: "a revision is a new claim referencing the old" | Claim files are append-only and record a digest per line: an in-place edit is `CLAIM_IMMUTABLE`. A later stage writes a revision to its own `claim-revisions.jsonl` `{claim_id, revises}`. §3.3 does not change. |
| 12 | C1 (checkpoint amendment of 2026-11-03) | No expected observation exists in the owner's ledger yet, so C1 has no observation judgments on real sessions. Done-when 5's live path runs on the seeded corpus, and the C1 page says so. |
| 13 | heading: `claude-sonnet-5-5/xhigh` | `claude-sonnet-5-5/high` (D-20261103-4b967e). The seat changes together with A-1's re-pin and re-measure, because the host allowance is measured for each seat. |

The package order, the other done-when items, the verification point and the review gate (X on the packets and
schemas, W on the code) do not change.

## Closed

- Row 6, WP-08 asserting instances only and moving the resolution fixtures to WP-21: done-when 5 then could not be
  checked inside WP-08. Revisit if WP-21's store needs a resolution shape that `derive_resolution` does not return.
- Row 3, rewriting the census with reading status: two stages would then write one record.
- Row 1, a stitch call per file: the outcome of an event in a parent often lies in a child, or in a later file of the
  same thread.

Revisit any row when a decision it rests on (listed in the first paragraph) is reopened.
