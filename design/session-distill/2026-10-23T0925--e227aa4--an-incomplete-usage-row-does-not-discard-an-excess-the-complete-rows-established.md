---
created_at: 2026-10-23T09:25:40+09:00
head: e227aa4
kind: review
supersedes: 2026-10-22T1951--2c1235a--a-stop-is-written-before-anything-that-can-fail-and-every-call-records-its-own.md
---

# An incomplete usage row does not discard an excess the complete rows established

Hermetic review round 1 on `e227aa4` returned `fix_then_accept`: the F-19 and F-20 fixes hold, and two
things did not. This record supersedes the 1951 one, which states the persist-first property without
the qualification it needs and gives two of the round-5 labels the wrong way round.

## HA#0 — the one path on which an observed excess still escaped

`bound.observed_input` answers two questions independently: the largest observed input over the
measured rows, and which components some row failed to state. Settlement raised `USAGE_INCOMPLETE` for
the second before writing the stop for the first, so a call with one complete request at 135 796 input
tokens and one request whose input was not an integer ended with no `stopped` entry and the next
reservation admitted. The excess the complete rows establish is now persisted first; the
`USAGE_INCOMPLETE` refusal is unchanged and is still what the call fails with, and the call record is
written with the offered stop before that refusal is raised.

## HA#1 — the losing stop's diagnostic, through real settlement

The earlier-terminal-stop control called `_stop_run` directly and read its return value, so a change
that recorded only a stop the run keeps would have passed it. The control now plants the terminal stop
while the call is in flight — at the point settlement measures the call, with none of this supervisor's
locks held — breaks this call's own stamping, and asserts the saved `call.json`, the retained ledger
entry and the refusal the call raises.

## What persist-first actually claims

**It holds while the supervisor lock and the ledger are usable, and the state in which it does not hold
is not a state that admits a call.** Every reservation passes through the same three operations the
stop needs: `reserve` takes `Supervisor._lock()`, reads `ledger.json` through `records.read_json`
(which raises `RECORD_UNREADABLE`), and ends in `self._write(ledger)`. So a supervisor lock that cannot
be taken, a ledger that cannot be read, and a ledger that cannot be written each refuse the next
reservation by the same failure that prevented the stop from being written. Admission is not open in
that state.

**The residual is repair, not the failure.** Nothing remembers that a stop could not be written. If the
condition clears — a permission restored, a full disk freed — the ledger reads clean, carries no
`stopped` entry, and admission reopens. This is not protected, and closing it would mean a record of
the attempt outside the ledger the attempt could not reach.

Per-call persistence has the same shape: the stop reaches `call.json` when that final write succeeds.
A failure there leaves the initial record written at launch beside a ledger stop that stands, which
the gate refuses as unfinished.

## Round-5 labels

The 1951 record and the code comments swapped two of them. **BE#2 is the contention signal** —
`STOP_ACQUIRING` was set before the real lock attempt, so the interleaving control could pass on a
favourable schedule. **BE#3 is the per-call diagnostic** — a programming error after a successful
declaration read was labelled `declaration-unreadable`, and a stop that lost to an earlier terminal one
was persisted nowhere. Both were fixed in `e227aa4`; only their names were wrong. The code comments and
the control `BE#2-the-amendment-was-released-by-real-contention-on-the-declaration-lock` carry the
corrected labels here.

## One correction to the amender's wording

The 1951 record says the amender releases the declaration lock only after the contention signal
arrives. It also has a 30-second timeout, so it can release without one — and on that schedule the
named control fails rather than passing quietly, which is the property that matters.

## Closed alternatives

- **Treating an incomplete usage record as a reason to decide nothing.** Ruled out. The two answers
  `observed_input` returns do not depend on each other: a complete row above the bound is an observed
  host change whatever another row failed to state, and the incomplete row is still reported.
- **Recording only the stop the run keeps.** Ruled out, and now controlled: the case where a stop loses
  is exactly the case where a defect in this code would otherwise leave no trace.

## The known residual, unchanged

The instruction comparison is made in the observer's form, which collapses whitespace and strips HTML
comments, so a change between the count and the send that the normalization ignores alters the raw
length the bound counted without producing a refusal. It is recorded as a residual, not a property.
