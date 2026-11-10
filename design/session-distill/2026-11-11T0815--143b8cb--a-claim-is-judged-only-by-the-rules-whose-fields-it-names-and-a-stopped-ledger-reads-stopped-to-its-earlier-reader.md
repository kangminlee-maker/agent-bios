---
created_at: 2026-11-11T08:15:00+09:00
head: 143b8cb
kind: design
supersedes: null
---

# A claim is judged only by the rules whose fields it names, and a stopped ledger reads stopped to its earlier reader

WP-08e, commit 5: the lead's four findings on commit 4 (143b8cb), from its verification and reproduction script
(`w8e-repro.py`, probes A1 and A1b). Lead decision D-20261111-48d163. This record amends the 0710 record of commit 4
where it describes how a claim is judged and what a ledger holds; the 0710 record is not edited.

## 1. Each rule judges with the fields it needs (`bound.claim_breaches`, `bound.claim_shape`)

- **The hole.** Commit 4 applied the first-request rule only when a claim named both `first` and `step`. A claim
  recorded by 78e1e92 names `first` and no `step`, so its first request fell back to the per-request `input_at_most`
  ceiling and a first request past its reserved estimate was accepted (A1: a record rewritten to that shape; A1b: an
  untouched 78e1e92 call directory, one main request of 90,352 input tokens against `first` 88,352 and
  `input_at_most` 93,566).
- **The rule now.** The request count is judged by `requests_at_most`, request 1 by `first`, the k-th retry by
  `first + k x step`. A rule whose field the claim does not name judges nothing; no request is ever judged by
  `input_at_most` alone. `bound.claim_shape` names each field a rule needs for rows that exist and the claim lacks: a
  retry row and no `step` (the 78e1e92 shape with two main requests), a request and no `first` or no
  `requests_at_most`. `bound.claim_problems` is the breaches followed by each shape line, prefixed `CLAIM_SHAPE:`.
- **Readers.** The gate refuses a shape problem as `CLAIM_SHAPE <call_id>: ...; a claim is never judged by a weaker
  rule`, beside the usage breach it already refused as `CLAIM_EXCEEDED`; both templates are in the gate's §3.2
  inventory. The dispatcher's claim entry (`_claim_entry`) and S4's `within_claim` and `observed` decide on
  `claim_problems`, so a shape problem stops the run under `CLAIM_EXCEEDED` with its line in the record's `breaches`.
  `CLAIM_SHAPE` is a refusal code and a breach line, not a stop code: the gate's `stops` schema still admits only
  `INPUT_BOUND_EXCEEDED` and `CLAIM_EXCEEDED` (unchanged, as the lead noted), and a third stop code would have to
  change it.
- **Controls.** bound: an old-shape claim (no `step`) whose one request is above `first` is a breach by name; the same
  claim with two main requests names the `step` its retry rule needs; within `first` with one request, neither; a
  claim naming only `input_at_most` judges nothing by it and names the `first` it lacks; an unreadable claim is a
  breach and an unreadable shape a refusal. dispatch, ported from A1: a dense call's record rewritten to the 78e1e92
  shape (claim without `step`, no stop record) is refused `CLAIM_EXCEEDED` by the gate, its failure line beginning
  `request 1 took`; a two-request call rewritten the same way is refused `CLAIM_SHAPE` alone, naming the step; a
  one-request call within `first`, rewritten the same way, is accepted. A1b's numbers are the bound control's.
- **Not controlled.** Every claim this tree writes (`dispatch.call_claim`, `stage_form.form_claim`) names all four
  fields, so the dispatcher's and S4's shape path has no producer today and no control of its own; the gate's has.

## 2. The ledger keeps `stopped` beside `stops` (`bound.projection`)

- **The hole.** Commit 4 read the earlier one-entry `stopped` but wrote only `stops`, so a ledger it wrote read open
  to the reader of commit 3 (78e1e92's `_blocked`, which reads `ledger["stopped"]`), probed both ways by the lead.
- **The rule now.** Every stop the dispatcher records (`_stop_run`, under the ledger lock) writes `stopped` too: the
  one-entry projection of the stops standing at that moment, with the amendments read for the stamp, or every record
  standing when they could not be read. No standing stop: `null`. One: that record itself, so the earlier reader lifts
  it by its own key, as this code does. Several: one unstamped record whose `stamp` names them all
  (`several-stops: ...`), which the earlier reader holds terminal. So the earlier reader never reads open a run this
  code reads stopped; it can read stopped one this code reads open, after both keys are amended, and the owner then
  continues with this code. `ledger()` returns the `stopped` it read, so every other ledger write carries it.
- **Controls** (dispatch, the earlier reader ported into the self-test as `old_blocked`: 78e1e92's `_blocked` with
  its `bound.blocked`/`bound.lifted`): a ledger this code wrote with a claim stop reads stopped to the earlier reader;
  that reader is not reopened by `host_allowance` and is by `retry`, as this code is; a bound stop and a claim stop
  standing read stopped to it after `host_allowance` alone, their projection one unstamped record. bound: the
  projection is `None`, the one standing record, or one record naming several, which is terminal.

## 3. Every handler a RunStopped can meet re-raises it or is named (`records.broad_handlers`)

- **The enumeration.** `records.broad_handlers` lists every handler of production code that catches a class of
  RunStopped's MRO (`RunStopped`, `Refused`, `Exception`, `BaseException`) or is bare, keyed by module, function and
  catch with an ordinal, never by line. A site re-raises by structure when a handler of the same `try` before it
  catches RunStopped and ends in a bare `raise`, or when it always ends in one (its last statement, with no return,
  break or continue in it). The scan covers the runlib modules whose code names RunStopped or a supervisor - dispatch,
  records, stage_form, stage_read, the only places one is raised or passes; census, declare and views run stages
  through `run_stage` and `run_items` with no supervisor, so none arises in them.
- **What it found.** Twenty-three handlers: eight re-raise by structure (the dispatcher's call, twice by `Refused`
  and once by `BaseException`; its main boundary; `write_text`; `_run_sequence`; `run_items`' parallel sequence;
  `run_stage`). Fifteen are named in the records self-test, each with its reason: thirteen in the dispatcher (taking
  the declaration lock, reading and stamping the declaration, the clock and its fallback, the monitor's rows, the
  offer and its entry, the call's own stop record, the server policy, the failure path's offer, the sizing packet,
  the gate's refusal of an earlier attempt), S4's origin evidence and S3's quote location. Each one's `try` body calls
  no supervisor, item or stage; the failure path's offer is followed by the enclosing handler's re-raise.
- **One change of code.** `run_items`' parallel sequence passed a RunStopped only because its message does not begin
  `ITEM_FAILED `; it now passes it by class (`except RunStopped: raise` before `except Refused`), so the structure
  says so.
- **Controls** (records): the four modules are scanned; every site re-raises or is named; the re-raising sites are
  found as such; a handler planted in `Supervisor.item` around the supervisor's call that swallows a refusal fails
  `STOP_HANDLER_UNNAMED dispatch:Supervisor.item:Refused#2`; `_run_sequence` without its RunStopped pass fails
  `STOP_HANDLER_UNNAMED records:_run_sequence:Exception#1`; a named site that keeps nothing fails
  `STOP_HANDLER_STALE`; a scan over nothing fails `STOP_HANDLER_NONE`.
- **Not established.** A module that reaches a supervisor through a name the scan does not read (a callable passed
  in under another name) is not scanned. `distill.py` is outside runlib and outside the scan; its command boundary
  catches `Refused`, prints the stop and exits 1, which is where a RunStopped ends.

## 4. S4's fallback stops from the rows it judged (`stage_form.usage_rows`)

- **The hole.** S4's fallback stop re-read `usage.json["requests"]` before persisting the stop, so a usage record
  unreadable by then raised `KeyError` and no stop was recorded.
- **The rule now.** S4 reads the accepted call's usage once, through `usage_rows`: no file, `None`; a file without
  request rows, `RECORD_UNREADABLE <path>: no request rows`, by name. `observed` judges those rows, and the fallback
  persists the stop from the same rows (`stop_on_claim`), never re-reading.
- **Controls** (stage_form): an S4 call over its claim whose usage record is replaced after it was judged stops the
  run `CLAIM_EXCEEDED` with the ledger's stop recorded, not a `KeyError`; a usage record without request rows is
  refused `RECORD_UNREADABLE`.

## The stopped call's density

The lead accepted commit 4's reading of F1: a call that stopped the run is excluded from calibration, which means the
p95 sample; its first request's density stays in the class's density sample, since the first request is what the
estimate is measured from.

## Measured on this tree

| What | Result |
| --- | --- |
| Revert rows (`rows-c5.py`) | 4 baselines PASS (bound, records, dispatch, stage_form); 6 revert rows CAUGHT, none missed, no traceback |
| Collateral | the projection row also fails the dispatcher's two delegation checks, which name `bound.projection` as owed |
| Self-tests | every session-distill module with a self-test: 34, 0 not rc=0 |

The `LEDGER_REL` references in `stage_read.py` are unchanged here; lane L takes them at integration. The reproduction
script's probes A2 to A5 are not changed by this commit.
