---
created_at: 2026-11-13T06:10:00+09:00
head: 9022f09
kind: review
supersedes: none (it follows 2026-11-13T0525--e82d91a--s11-after-its-first-review.md)
---

# S11 and S12 after the second review

The second cross-family review (pinned at `8a8e310`: S11's rework, S12, the adjudication's second pass) returned
**rework** again: nine blocking, seven major, one minor. It was S11's second and last capped round and S12's
first. This record says what each became; the review file is the lead's (`work/lead/s11-x-r2-review.json`).

## S11

- **A plan whose rows each pass could still be empty, a subset or foreign** (blocking). The effects part now
  holds the plan whole. Its bytes are read once and must be the bytes admission pinned. Before any effect, the
  confirmed operations are planned again over the files and must give this plan byte for byte
  (`PLAN_NOT_THE_CONFIRMED_SET`); after one, the plan must be the one the journal's effects were taken from, read
  from the earlier effects record before this call replaces it (`PLAN_CHANGED`).
- **The run directory itself could be swapped for a link** (blocking). `stagelock.beneath` opens its anchor
  without following a link.
- **The staged file could be changed in place before the rename** (blocking). The descriptor that wrote it is
  kept, and its bytes, type, link count and name are read back through it immediately before the rename
  (`APPLY_STAGING_MOVED`). A consequence: bytes that are not the plan's after-state are never installed, where
  before they were installed and then reported.
- **A done record with no plan before it skipped an effect** (blocking). The journal's history per operation is
  planned then done, once each, in the plan's order; anything else is `APPLY_JOURNAL_CORRUPT`.
- **A lone CR was not a line ending** (blocking). `operations.lines_of` ends a line at LF, CRLF or CR and keeps
  each line's own offset.
- **An amendment after the last check went unseen** (major). The declaration's lock is held around each effect
  with the check under it, so an amendment cannot land during a write, and the check is made once more before
  the stage says it is complete.
- **A delayed plan call could poison a finished apply** (major). One S11 call runs at a time (`APPLY_LOCK`), so
  "no journal yet" is still true when the plan part's record is replaced.
- **Spelling checks disagreed with the target contract** (major). The write uses the contract's own comparison
  (`targets._spelling_on_disk`), so a canonically equivalent entry is the name; planned prefixes ask the
  filesystem whether it folds case (`targets.folds_case`) and refuse an undecided one rather than guess.
- **S7 refused what S11 would apply** (major). Whether a file is there depends on the ordered set, so S7's
  check of one proposal no longer reports the five codes that depend on it (`stage_propose.SET_DEPENDENT`).

## S12

- **The ledger and coverage writers resolved a path and then opened it by name; checked the base before
  staging; and coverage kept its lock inside the checkout** (three blocking). S12 no longer uses either module's
  writer. Both files go through `stage_apply.Checkout`: reached from the checkout's descriptor, staged first, held
  to the state the run pinned, read back. The validation of each module is kept. Nothing else is left in the
  checkout.
- **A drop always wrote retirement fields** (blocking). Retirement is the transition's to say (§12.3): a drop on
  a placed entry, or on a candidate about an existing unit, leaves a placed entry whose intervention was dropped.
- **A re-run's close.json listed no items** (major). What each item became is frozen with the allocation.
- **The control over what the close does not do compared the constant with itself** (major). It names the six.
- **Two branches allocate one id** (major). Not fixed: it is caught at merge and not prevented. Queued as F-35
  with three alternatives; the owner's use in release 1 is one checkout and one close at a time.

## Minor

- The journal's order control now compares lists and hands `control` the verdict.

## What this does not claim

No third review round was run on S11: the cap is two. The fixes above rest on this repository's own controls and
revert rows, which is weaker than a reviewer of another family, and says so here. The trust boundary is stated in
`stage_apply.py`: the run directory is trusted against accident and a second caller, not against a writer who can
rewrite the run's records, approvals and confirmation together.
