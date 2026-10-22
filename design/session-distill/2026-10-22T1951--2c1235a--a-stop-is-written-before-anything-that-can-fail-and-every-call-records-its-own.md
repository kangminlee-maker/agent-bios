---
created_at: 2026-10-22T19:51:53+09:00
head: 2c1235a
kind: review
supersedes: 2026-10-22T1840--05e409a--a-stop-never-weakens-and-a-stop-that-cannot-be-stamped-is-still-written.md
---

# A stop is written before anything that can fail, and every call records its own

Round 5 of the dispatcher-seam review (`wp/06-dispatch-seam`, subject `0292cdf`) was the last round by
the owner's decision, and its findings went to the open-defect queue as F-19 (BE#0, BE#1) and F-20
(BE#2, BE#3), to be closed before WP-08 — the first stage that dispatches a view-window call. They are
closed on `wp/06-stop-persist`, and this record supersedes the 1840 one because two of its sentences
were claims the code did not keep.

**The 1840 record said each call reports its own stop in its own call record, and that the BD#2 control
makes the stop find the declaration mid-commit. Neither held.** `_stop_run` returned the entry it had
offered, but nothing wrote it anywhere: a call whose stop lost to an earlier terminal one left its
reason in a return value and nowhere else. And `STOP_ACQUIRING` was signalled where the stop *asked*
for the declaration lock, which is before any contention is known, so a schedule existed in which the
amender released the lock before the stop ever reached it and the control passed without the
interleaving it is named for.

## What is true now

**BE#0 — every failure to take the declaration lock is an unstamped stop.** The handler took
`stagelock.Locked` alone, so a `declaration.lock` at mode 000 (`PermissionError`) or linked out of the
run (`Escaped`) escaped with the excess already observed and nothing written. It now catches every
exception from the hold, records the stop under the supervisor lock with
`stamp: lock-unavailable: <the error>`, and keeps the original diagnostic. Strongest-stop selection is
unchanged: such a stop is unstamped, therefore terminal, and no amendment lifts it.

**BE#1 — the stop is persisted first.** The excess used to be established in settlement and written at
the end of it, after the call record, the receipt the launcher writes and the charge's calibration read
— so any of those failing ended the call with admission still open. The stop is now written as soon as
settlement establishes the excess, before all three. The call's remaining settlement still runs; if it
fails, that failure propagates as it did before and the stop stands. The order is checked over the
settlement slice of this module's own source, by `find` rather than `index`, so a mutation that moves
the stop out of that slice fails the control by name instead of aborting the suite.

**BE#2 — a stop says which half of itself failed, in the call's own record.** Reading the declaration
and stamping the entry are caught separately: a read failure (an unreadable file, a confinement
violation, a decode error, the reader's named `Refused`) is `declaration-unreadable`, while anything
thrown while stamping is this code's own arithmetic and is `stop-internal-error: <repr>`. The call
record carries this call's own offered stop — its code, observation, reason and `kept`, which says
whether the run adopted it or retained a stronger existing stop — so a programming error stays visible
even when an earlier terminal stop is the one the ledger keeps. `CALL_SCHEMA` admits the block
optionally, so records written before it existed stay valid.

**BE#3 — the interleaving control is released by real contention.** `stagelock.CONTENDED` is called
once, inside the real `flock` attempt, the first time the lock is found held; the self-test sets it and
production leaves it `None`. The amender now releases the declaration lock only after that signal
arrives from the stop's own acquisition, so the stop cannot avoid finding the declaration mid-commit.
Under that schedule the out-of-lock-read mutant fails every repetition.

## Closed alternatives

- **A finalisation path (F-19 alternative 2).** Ruled out. Keeping the old order and guaranteeing the
  stop write in a `finally` leaves two code paths that must agree on which stop is offered, and makes
  the guarantee depend on the finaliser itself not failing. Writing the stop at the moment the excess is
  established removes the window instead of covering it.
- **Report only (F-20 alternative 2).** Ruled out. Carrying the diagnostic in the refusal detail alone
  means a stamping defect leaves no trace once a terminal stop already stands — which is exactly the
  case where a defect in this code is hardest to see. The call record is the one place a later reader
  can find it.
- **Taking only the named refusal, and letting the last stop win.** Still ruled out, for the reasons the
  1840 record gives.

## A known residual

Unchanged from the 1840 record, and still not protected: the instruction comparison is made in the
observer's form, which collapses whitespace and strips HTML comments, so a change between the count and
the send that the normalization ignores alters the raw length the bound counted without producing a
refusal. Closing it would mean either a second comparison on the raw form, which the host's own
evidence cannot support, or counting the normalized form, which would make the bound's arithmetic
depend on one host's rendering rule.
