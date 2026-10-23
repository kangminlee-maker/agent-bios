---
created_at: 2026-10-23T10:30:38+09:00
head: 64c5962
kind: review
supersedes: 2026-10-23T0925--e227aa4--an-incomplete-usage-row-does-not-discard-an-excess-the-complete-rows-established.md
---

# The stop decision is the first thing settlement does

Hermetic review round 2 on `64c5962` returned `fix_then_accept` with one major finding, HB#0: more
statements between the process ending and the stop could fail and discard an observed excess — the
result write, the reconciliation in `_usage`, the seat projection, the usage write, the cell deletion,
the breaker work — and a malformed row could abort the reading itself before it returned another row's
excess. The reviewer reproduced each with a complete 135 796-token row: no ledger stop, no call stop,
the next reservation admitted, with the supervisor lock and ledger usable.

**This is the third round to find another pre-stop path, so what is closed here is the class, not the
instances.** This record supersedes the 0925 one, which called `USAGE_INCOMPLETE` "the one path" and
said closing the repair residual would necessarily need a record outside the ledger. Both were
overclaims; the second is corrected below with the alternative that would in fact close it.

## What settlement does now

`_follow` returns, and the next statement is the stop decision. Its input is the host's own
per-request input components, read straight off the monitor's rows by `bound.observed_rows`, an
extraction that cannot raise: a row that is not a mapping, or whose components are not whole numbers,
is reported in `missing` and contributes nothing to the maximum, so it is never read as a smaller
number and never hides another row's complete excess. If an excess is established, `_stop_run`
persists the strongest stop under the supervisor lock and the call record is written with the offered
stop at once. Every later failure propagates exactly as it did before.

**Between the end of `_follow` and the stop there is now nothing**, which is the only form of this
guarantee that survives the next statement somebody adds. The statements that used to be there are all
after it, each for its own reason:

| Statement | Why it is after the stop |
| --- | --- |
| `result.json` write | a file write; it can fail on the filesystem |
| `frames.jsonl` write, transcript copy | the same, and a copy of a tree the host wrote |
| `gate.Call(call_dir).result` | parses host-written JSON |
| `_usage` reconciliation | sums host-reported fields of every shape, and can raise on any of them |
| `gate.observed_seats` | projects the seat from the capture; the reviewer failed it |
| `usage.json` write, `_delete_cell` | a write, then a refusal (`USAGE_UNCAPTURED`) that depends on it |
| breaker observation and deferral | reads host events and writes the breaker's state |
| `call.json`, `_receipt`, `charge` | the three the earlier rounds already moved |
| `observed_input` over the written record | kept: reconciliation can make a row measured that was not measured when the live rows were read, and the earlier stop already stands if one was found |

`bound.py` stays the one owner of the rule: `observed_rows` is the live reading, `observed_input`
remains the reader of a written usage record, and both answer in the same `(observed, missing)` shape.

## What is still not covered, and why

**`_follow` itself.** The decision cannot precede the function that produces the rows it reads. Inside
`_follow` the only handled failure is an `OSError` while feeding the packet, which is ignored; a
failure in the reader threads, the sampler or the drain raises out of it with rows already in the
monitor and no stop written. This is a residual, named rather than closed: covering it would mean a
stop decision inside the follow loop, on rows the host is still adding to, which is a second decision
point and the thing this round exists to remove.

**Repair.** Nothing remembers that a stop could not be written. The 0925 record said closing that
would need a record outside the ledger; that is wrong, and the alternative below is how it would be
closed.

## Closed alternatives

- **A pending-settlement barrier in the ledger** — written before launch, cleared on settlement, so a
  run with an uncleared barrier refuses admission. The reviewer raised it, and it would close the
  repair residual as well, since a stop that could not be written leaves the barrier standing. Not
  taken: it either serialises concurrent view-window calls or needs liveness detection and a recovery
  protocol for a barrier left by a process that died, which is a lifecycle change beyond F-19.
  **Revisit when** repair-reopens-admission is observed in practice, or a recovery protocol is being
  designed for another reason.
- **Fixing the instances.** Ruled out by this round's own history: three rounds, three different
  statements, each closed on its own and each followed by another. The order is the property now, and
  one control holds every statement settlement makes after the process ends against it.
- **Treating an unreadable row as a reason to decide nothing.** Ruled out. It is exactly how one
  malformed row would hide another row's complete, host-reported excess.

## Controls

Six replayed calls, each breaking one statement that used to run before the stop — a malformed
aggregate, a failing seat projection, a monitor row whose output is not a number, a row that is not a
mapping, a sealed call directory after `_usage`, and a sealed call directory at the moment `_follow`
returns. Each asserts the ledger stop, a refused next dispatch and the call's own failure; the call
record is asserted wherever the directory is still writable, which is every case but the last, where
the seal precedes the stop block's own write on purpose. One more control holds the source order
against every post-process statement, and five in `bound.py` hold the extraction itself. Reverting the
order fails seventeen of them by name; reverting the extraction fails `bound.py`'s own control and
four dispatch controls.

## The known residual, unchanged

The instruction comparison is made in the observer's form, which collapses whitespace and strips HTML
comments, so a change between the count and the send that the normalization ignores alters the raw
length the bound counted without producing a refusal. It is recorded as a residual, not a property.
