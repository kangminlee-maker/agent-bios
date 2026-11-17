---
created_at: 2026-11-06T09:03:00+09:00
head: ed6e3d3
kind: design
supersedes: null
---

# S4's admitted capacity is in each call's record, and each attempt is measured under the id it is sent with

WP-09, commit 8: the fixes for review W round 2 (rework; one major, one minor). This was W's last round, as round 2
was X's. X's two majors from its round 2 were reproduced by W with fixtures of its own and found fixed, and X's two
minors passed. The lead checks this commit by re-running the reviewers' reproductions on a pinned clone.

This record covers:
- `Supervisor.call`'s `context_capacity`, `Supervisor.item`'s `packet_check`, and the golden host's
  `context_window`, in `session-distill/runlib/dispatch.py`;
- `judge`, `recorded_capacity`, `observed`, `packet_bytes` and `run` in `session-distill/runlib/stage_form.py`.

The record of commit 7 (`2026-11-06T0826`) stays as written. Where this record differs from it, this one describes the
code from this commit on.

## F1: the capacity S4 was admitted against is in each call's record

Commit 7 bounded S4 by its seat's capacity (1,000,000, from the host's model catalogue) but kept that number to
itself. A call without a view window returns from `dispatch._admit_seat` before the seat's capacity is read, so
`call.json` recorded `bound.context_capacity: null`. `gate.window_bound` compares the host's reported context window
with that field only when it is an integer, so a result reporting 200,000 passed.

Now:
- `Supervisor.call` takes `context_capacity`, the capacity a call without a view window was admitted against by its
  own stage. It is recorded in `call.json`'s bound block as a view-window call's is. One that is not a positive
  integer is `CAPACITY_INVALID`, the reservation released and nothing sent; the code joins the refusals dispatch's
  module docstring and its self-test's cited set list. A view-window call's capacity is still the one dispatch reads
  from seats.json.
- S4 passes the capacity `form_budget` admitted it against, through `Supervisor.item`, to every attempt.
- The gate then compares it with every model's reported `contextWindow` (`CAPACITY_DRIFT`, unchanged). A drifting
  attempt is not accepted, and nothing is formed.
- S4 requires the field. Its judge (`judge` → `recorded_capacity`) first checks that the attempt's record carries the
  admitted capacity; one that does not stops S4 by name (`CAPACITY_UNRECORDED`) before its answer is judged, retried
  or reused. An attempt recorded before this commit therefore stops a run that would reuse it.

The first live S4 call is where the catalogue's capacity and the 1.94 bytes a token are first checked. Its
`form.json` now keeps, under `call.observed`:
- `admitted_capacity` and `context_window` (per model, as the host reported it);
- `driver_bytes`, `input_tokens` (the main request's input as the host reported it, `bound.observed_input`) and their
  ratio `bytes_per_token`. The input tokens include the host's own context, so the ratio reads low.

A host reporting another window fails the call's gate, so that run forms nothing, and the declaration (seats.json) is
corrected before the next.

The golden host reports a `contextWindow` when its spec names one (`context_window`), so S4's controls can make a host
agree or disagree with the record. Without it, it reports none, as before, and no other suite changes.

## F2: each attempt is measured under the id it is sent with

`packet_bytes` measures under an `a2` call id. A resumed run's attempts are given longer ids (`Supervisor.reserve`
counts past the closed ones: `a10`, `a11`), and the call id is part of the packet, so the packet sent was a byte longer
than the one measured. With a bound narrowed to the admitted estimate plus a 4,096-byte correction, the a11 retry was
measured at the bound and sent one byte over it.

Now `Supervisor.item` asks `packet_check` after the attempt is reserved, with the packet built under the id the
reservation gave. S4 measures that packet (`bound.driver_bytes`). A packet over the bound releases its reservation
unspent and stops the item by name (`FORM_OVER_BOUND S4: this attempt's packet ...`) before anything is sent.

Admission still uses `packet_bytes` (an `a2` id) plus the correction room: an estimate made before any id is given.
The measure that decides whether an attempt is sent is now the exact one.

## Controls added

In `stage_form.py --self-test` (129 controls):
- F1: with a host reporting the admitted capacity, the record carries it and the call is accepted, and `form.json`
  keeps what was observed; with a host reporting 200,000, the gate fails the call (`CAPACITY_DRIFT`), the record is
  partial and nothing is formed; with the capacity dropped on its way to the call, S4 stops after one attempt
  (`CAPACITY_UNRECORDED`); a capacity that is no number is `CAPACITY_INVALID`, its reservation released.
- F2: after nine closed attempts the attempts are a10 and a11; a bound one byte short of the a11 packet as sent refuses
  that retry at exactly its bytes, before sending, and leaves no reservation open.

## Not covered

- The live call: the capacity and the ratio are compared for the first time on 2026-11-09 at the earliest.
- `bytes_per_token` divides by the main request's input, the host's own context included; separating the two needs
  the host's share of that request, which the usage record does not give.
