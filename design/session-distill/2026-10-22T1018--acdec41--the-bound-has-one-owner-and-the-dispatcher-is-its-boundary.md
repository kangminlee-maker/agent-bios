---
created_at: 2026-10-22T10:18:00+09:00
head: acdec41
kind: design
supersedes: 2026-10-22T0853--d1ca7bb--a-fixture-that-passes-either-way-tests-nothing.md
---

# The bound has one owner, and the dispatcher is its boundary

The seam WP-06 and WP-02 were always going to meet at. The survey of 2026-10-22 found five deferred
obligations and six gaps; this is the wiring, as the lead ruled it.

## What was wrong

One rule existed twice. `views.py` cut windows against its own copy — `INPUT_LIMIT`, check (a), check
(d), the observed-input rule, an excess record in `input_bound.jsonl` and the recovery rule — while
`dispatch.py` admitted calls against another: `INPUT_BOUND`, check (a) alone, its own observed-input
arithmetic, and a run stop with no way back. Neither side called the other. The consequences were not
hypothetical:

* a window that passed (a) and left no room for the answer was **dispatched**, because (d) lived only
  on the side that cannot dispatch;
* the file the recovery rule reads was **never written**, so the rule could not have fired;
* **amendment recovery existed nowhere** — WP-06 had the rule without the stop, WP-02 the stop
  without the rule;
* the driver's payload was counted twice, by two expressions that agreed only by coincidence;
* the gate recorded `input_observed` and judged nothing with it.

## The shape now

`session-distill/runlib/bound.py` owns the rule and nothing else does. It is **pure** — standard
library only, no `runlib` import, no file read, no clock — so it cannot grow an opinion about where
the run's state lives; its callers supply the state and raise its refusals. A self-test control reads
its own source and fails if `from runlib`, `import runlib`, `open(` or `subprocess` appears outside
the self-test.

* `views.py` imports it to cut windows: `limits_of` still reads the declaration (where the allowance
  comes from is the view side's business), then asks `bound.limits` for the shape.
* `dispatch.py` imports it for all four of admission, settlement, the stop and the recovery.
* `gate.py` imports it to judge an accepted call against the same numbers.

Deleted, not kept in sync: `views.gate_dispatch`, `views.settle_dispatch`, `views.dispatch_blocked`,
`views.record_input_bound_exceeded`, `views.check_bound`, `views.check_observed_input`,
`views.driver_payload_bytes`, `views.driver_budget`, `views.USAGE_KEYS`, its four constants, and
`dispatch.INPUT_BOUND` with its inline (a) check and its own observed-input arithmetic. The
`input_bound.jsonl` path is gone with them.

## Four decisions worth stating

**One excess record.** The run ledger's `stopped` entry is it, and it now carries `declaration_seq`
and `observed` — `bound.excess(...)` builds it. The stop is written under the ledger lock where every
dispatch already reads it, so the record a run recovers from is the record it stopped on. A control
asserts no second file appears anywhere under the run.

**What the driver's part is.** `bound.driver_bytes` counts what the call **sends**: the packet (its
template, principles block and window payload are one object by then), the schema, and what the
call's own manifest declares it carries — instruction files and appended system prompts. The host's
builtin context from `seats.json` is **not** counted: that is the measured allowance, and charging it
to both sides would count the same tokens twice. Files merely readable in the working directory are
not sent, so they are not counted either — a read shows up in the observed input, and settlement is
what catches it. A declared part that can be neither read nor sized is **refused**
(`DRIVER_PART_UNCOUNTED`), never counted as zero: an uncountable part makes the driver's share
unknown, which is the one failure the bound exists to prevent.

**One code at the boundary, quoting which check failed.** The dispatcher still refuses with
`WINDOW_OVER_BOUND`, and its message now carries the rule's own line — `WINDOW_BOUND_EXCEEDED (a)` or
`WINDOW_CAPACITY_EXCEEDED (d)`. The contract list keeps one code for one stop; the reader still learns
which half of the rule was broken. (d) needs the seat's context size, which is `seats.json`'s to
declare beside the measured allowance (`context_capacity`), defaulting to the S3 seat's until every
slot carries one.

**The gate judges from the call directory alone.** Its premise is that a call directory holds what the
driver sent and declared, and it reads no run-level file. So the boundary's decision travels with the
call: `call.json` gains `bound{limit, driver_bytes, stop_standing}`, and the gate fails a view-window
call whose `input_observed` passes the bound, a call whose record says a stop stood when it was
admitted, and a call recording a limit that is not the rule's. `stop_standing` is false by
construction — the dispatcher refuses such a call — which is exactly why a gate should say so if one
ever appears. The field is **optional** in `CALL_SCHEMA`: call directories captured before this change
have none, and a gate that rejected them would be re-judging frozen evidence. That it is always
written now is held where it is produced, by dispatch's own controls.

## The controls that moved, by name

From `views.py`'s self-test into `bound.py`'s, with their names intact:

* `bound (a) and (d): a window inside both checks passes`
* `control, bound (a): driver bytes above 120k minus the declared allowance are named`
* `control, bound (d): driver bytes that pass (a) but leave no room for the output reservation are named`
* `observed input: a view-window call within 120k is accepted`
* `control, observed input: a view-window call above 120k is a host change`
* `observed input: the same observation on a call that carries no view window is accepted, so the R authoring of §8.6 keeps its own section's contract`
* `dispatch is open before any excess is recorded`
* `done-when 3(a): the gate counts the COMPLETE driver payload …` and `… which is more than the window on its own`

The tighter-budget control stayed in `views.py` in its window-cutting form (it is about how a corpus
is cut) and is mirrored in `bound.py` as a budget comparison. `views.py` reports 526 controls where it
reported 532: six moved out, none were dropped, and the capture-based controls stayed — the retained
pinned captures are WP-06's evidence and still settle there, now through the rule's own functions.

## What is proven, and where

| Gap (survey §3) | Control | Where |
| --- | --- | --- |
| M1 the helpers have a caller | `the-bound-helpers-have-a-caller`, `the-bound-is-not-spelled-twice-here`, `the-boundary-and-the-rule-agree-at-the-exact-bound` | `dispatch.py` self-test |
| M2 check (d) at the boundary | `a-window-leaving-room-for-the-answer-is-admitted` (clean first), `a-window-passing-(a)-but-leaving-no-room-for-the-answer-is-refused` | `dispatch.py` self-test, through a planted `context_capacity` in a `seats.json` copy |
| M3 the excess is recorded where the rule reads it | `the-excess-record-is-the-run-s-stop-entry`, `the-excess-record-carries-the-observation-and-the-declaration-it-ran-under`, `there-is-no-second-excess-file-beside-the-stop-entry` | `dispatch.py` self-test, over a real replayed overrun |
| M4 recovery, five steps | `M4-i-…`, `M4-ii-…`, `M4-iii-…`, `M4-v-…`, `M4-iv-…`, `M4-recovery-does-not-forget-the-excess` | `dispatch.py` self-test |
| M5 the count is what is sent | `the-driver-payload-counts-the-instructions-and-prompts-the-call-carries`, `the-planted-driver-parts-are-not-zero-bytes`, `the-host-s-own-context-is-not-charged-to-the-driver`, `a-window-inside-the-bound-whose-declared-instructions-pass-it-is-refused`, `a-declared-driver-part-that-cannot-be-counted-is-refused-not-read-as-zero` | `dispatch.py` self-test |
| M6 the gate judges it | `a-view-window-call-within-the-bound-is-accepted` (clean first), `a-view-window-call-past-the-bound-fails-the-gate`, `the-same-observation-on-a-non-window-call-is-accepted`, `a-call-admitted-while-the-run-was-stopped-fails-the-gate`, `a-call-recording-a-bound-that-is-not-the-rule-s-fails-the-gate` | `gate.py` self-test |

M4's five steps run against a **real** overrun: probe 7's R-authoring capture (~136k observed input)
replayed as a view-window call, which is the same evidence the four controls kept green from before
use. The earlier-sequence case (v) is not a fabricated row — the amendment really is recorded before
the excess, and the rule refuses it because it compares sequences.

Two scans needed teaching, and both were self-matching before they were fixed: the refusal inventory
could not see a code raised through the rule's own record (`raised_codes` adds it, and loses it the
moment that raise goes), and two controls looked for a literal their own source contained, so the
token is now assembled at run time rather than written.

## Still open

The same three residuals, unchanged: X#6, the 63-case unreadable-structure class, and cross-script
lookalikes (out of scope by the owner's decision of 2026-10-22).
