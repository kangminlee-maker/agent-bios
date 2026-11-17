---
created_at: 2026-11-13T06:52:00+09:00
head: 52c75f8
kind: review
supersedes: none (it follows 2026-11-13T0610--9022f09--s11-and-s12-after-the-second-review.md)
---

# The third review of the write path, and what is not claimed

The review of S12's second round (pinned at `9ff896d`; S11's code in scope as the write path S12 shares) returned
**rework**: five blocking, two major, two minor. Review file: the lead's `work/lead/s12-x-r2-review.json`. With
this, S11 has had its two capped rounds and S12 its two, and all three reviews returned rework.

## What each became

- **A refused retry authorized the plan it had refused** (blocking). The plan's commitment was read from the
  effects part's own record, which every attempt replaces. It is now `apply/plan-commitment.json`, written once,
  after the whole-set check passes and before the first effect, and replaced by no attempt.
- **A rival file put under the target's name during the final read was overwritten** (blocking). The target's
  identity is kept from the read, and the name must still hold that file before the rename.
- **The staged file could change while it was read back** (blocking). Its metadata is taken before and after
  the scan and must be the same.
- **A run directory replaced after admission took the stage's later records elsewhere** (blocking).
  `records.run_stage` pins the run directory's identity for the stage (`stagelock.pinned`), and
  `stagelock.beneath` refuses an anchor that is another directory.
- **S12 wrote the old checkout after an amendment** (blocking). S12 holds the declaration's lock around its two
  writes and checks the declaration under it, and once more before it says complete, as S11 does.
- **The journal's order was read against the plan's order, not in its own** (major). The record stream must be
  the plan's history exactly: a completed prefix and at most one planned record after it.
- **A file that is not a ledger passed as a finished close** (major). The base is validated as a ledger before
  anything is read out of it, and a ledger carrying this run's window without its decisions is
  `CLOSE_INCOMPLETE`.
- **A refused replacement left a directory** (minor). Directories are made only for a file that is not there.
- **The journal control still compared by substring** (minor). It compares lists and appends its own failure.

Also in this commit, not from the review: the window row's `accounted` and `fully_read` are S3's own answers
(`stage_close.window_flags`) where the run has read results, and null where it has none. This replaces the
sentence in 2026-11-13T0448 that the close does not compute them.

## What is not claimed

Each round found races one step narrower than the last: first a check before the staging, then a change during
the staging, then a change during the read-back. That sequence does not end by adding checks. POSIX gives no
compare-and-rename, so between any two of the calls that read the target and the staged file, and the rename, a
concurrent writer can still act. `stage_apply.py` now says this without the earlier claim that unapproved bytes
are never installed.

What the code is held to, by its own controls and revert rows: it refuses on accident, on a stale file, on a
second run of itself, on an edited or incomplete plan, on a moved declaration, and on a link anywhere in a path.
What it is not: a defence against a process that writes the checkout or the run directory concurrently and
adversarially. Whether that is enough for release 1 is the owner's decision, and it is asked rather than assumed:
the fixes in this commit have had no cross-family review, because the cap is two rounds per unit.
