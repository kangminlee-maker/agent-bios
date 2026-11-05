---
created_at: 2026-11-03T22:45:00+09:00
head: 637a6a1
kind: design
supersedes: null
---

# S3 reads each window and keeps only what code can hold to the transcript

WP-08's second commit: the reader, over dispatch's golden host. Every window S2 cut is read by one call through the
supervisor, and what the call answers is kept only as far as code can check it against the window and the
projection. No model is called; `distill read` stays `STAGE_NOT_IMPLEMENTED` until the live legs. The contract it
fills is the first commit's (`…T2155--6779ed7--the-output-cap-is-declared-and-a-reading-cites-its-own-quotes.md`)
under the plan amendment of the same time.

## What lands

- `session-distill/runlib/stage_read.py`: `run(run_dir, supervisor)` reads every unit's views, one read record per unit
  in `read/<unit>.json`, the claim, event and evidence stores per file, `read-results.json` and `read.json`.
- `dispatch.Supervisor.item(..., stage_check=)`: a stage's own judgement of an attempt the gate accepted.
- dispatch's golden host answers from a plan (`answers`: rows of `match` texts and an `answer`, `<CALL-ID>` replaced
  by the call's id), so a stage's golden run answers each window with an answer made for that window.
- `declare`'s drop controls run over the pinned field set rather than the schema's `required` list.
- `views.golden(allowance_entry=)` declares the allowance seats.json measured, which dispatch admits a view-window
  call against; `views.fx_census` totals each source as S1 does, so the census S3 hands back is accountable.
- `packets/read.md`: an event starts on an owned record that is not `context`.
- `census.READER_EXCEPTIONS` lists `stage_read.run`, which declares census.json as S3's input artifact and reads the
  census only through `load`, `rows` and `reconcile`.
- `gates/check-parity.sh`: the stage's self-test is a leg.

## Steps 4 and 5 are the stage's, through the supervisor

The gate's steps 4 (references) and 5 (accounting) read `contract.json`, which is static: it cannot say "the entry a
quote names is a record this window owns" or "one decision per omission of the window's own records", because both
depend on the window the call was sent. `stage_check` takes a function of the attempt's call directory and returns
failure lines; the supervisor asks it only of an attempt the gate accepted, and a failing attempt is retried once
with exactly those lines, as a gate failure is (`gate.correction({"failures": lines})`). Its codes join the item's.

Closed: widening `contract.json` with per-window data (a contract written per call is not a contract); checking the
answer only after the item returns (the one corrective retry the design allows would be lost, and a stage would
re-implement the retry).

`answer_problems` (RECORD_INTEGRITY): every quote names an owned entry; every claim's and observation's evidence ids
name quotes of the same answer; every event's claim ids name its claims; every claim echoes the packet's CALL-ID; an
event starts on an owned record that is not context (design §5.2: an event belongs to the window of its first
record, and a context record lies outside the run's time window); ids do not repeat; an observation is one due in
this window. Then `views.check_decisions` over the window's own omissions (SET_MISMATCH, EXPANSION_SKIPPED,
EXPANSION_DECISION_INVALID).

## What an accepted answer leaves

Quote fidelity is code's, after the call: each quote becomes an evidence record through `evidence.from_view`, which
locates the text in what the window showed and reads the span from the projection. A quote that does not locate drops
every claim citing it, and an event left with no claim, and the window's read record lists each drop with its code
(QUOTE_MISMATCH, QUOTE_AMBIGUOUS, …). A claim is never repaired. A stored claim keeps the answered fact,
interpretation and uncertainty, with the located evidence ids and an id derived from its window
(`c-<sha256(window, local id)[:16]>`); its stored record is validated against `claim.schema.json` (CLAIM_INVALID),
and an event against `event.schema.json` (EVENT_INVALID).

Claim files are append-only. The read record holds each stored line's sha256, and `stored_claims` refuses a store
whose lines are not exactly the recorded ones: an edited line, a line no record holds, a recorded line gone
(CLAIM_IMMUTABLE). A revision is a new claim (§3.3).

## Expansions and the overlap rows

An `expand` decision is executed by `views.expand` and its windows are read under the same template, answered and
kept like any window; `skip` is logged by `views.record_decision`. A file is view complete through
`views.completeness`: every window accepted, every own omission decided, every expansion read.

The overlap rows follow D-20261103-8bfd69 and the lead's three conditions:

1. A row is credited only through the window of the same view whose `records` hold its record, and only when that
   window was accepted; otherwise it is uncredited and named among the unit's reasons, and the unit stays
   `read_partial`. That window must show the interval or list it as its own omission (OVERLAP_INTERVAL_UNSHOWN).
2. A row whose record no window holds and which the view's sequence lists `owned: false` is counted (`not_owed`),
   never a gap; the run's total is `read.json` `overlap_not_owed`. This is the population the C0c probe counted
   (3,476 on the owner's two days).
3. A row whose record no window holds and which the sequence does not list `owned: false` is OVERLAP_OWNER_MISSING.

An uncredited row implies an owner that was not accepted, so the view is already incomplete; the row is not a second
condition on `view_complete`.

## A unit's status and what it hands back

A unit is `read_complete` when every file is view complete, no overlap row is uncredited, no other version is
unresolved, and no pending event waits: a pending event answered in a window, or carried in the coverage state for
one of its files, needs the stitch call, which is the next commit, so until then such a unit is `read_partial`
(done-when 3). `deferred` when the provider deferred a window, `failed` when no window was accepted. A file whose owed
records hold no content block has no window and is credited by code, with its reason (plan amendment row 9); one with
viewed blocks and no window is WINDOWLESS_VIEW. A window whose bytes are not the ones views.json recorded is never
read (VIEW_DRIFT).

Each file's reading reports `read` as the records its accepted windows showed, and `processed`, only when its unit is
`read_complete`, as what the file owes: its own records on the latest version and that version's backlog. The results,
one per eligible unit and one per viewed unit (a unit S1 did not make eligible is refused by name rather than
dropped), are folded through `census.reconcile` against the state S1 left, so a result that does not fit
(PROCESSED_OUTSIDE_OWNED, SET_MISMATCH, …) is refused in S3, before `read-results.json` is written. S12 promotes it.

## Not in this commit

- The stitch, and the carry-forward of a pending event into `pending_events` (commit 3). A result names no pending or
  resolved event yet; a carried event stays in the state untouched.
- Expected observations (commit 4): the packet says `none`, and an observation answered is refused as not due.
- Resumability (commit 5). A rerun appends to the claim stores, and a unit quarantined after its windows stored claims
  leaves lines no read record holds; both are refused by CLAIM_IMMUTABLE on the next read, which is the loud failure
  this commit keeps until resumability defines what a rerun keeps.
- The live legs and `distill read` (commit 7).

## Controls

`stage_read.py --self-test` makes golden runs S0 to S2 with `views.golden` and reads them through a supervisor whose
host answers from a plan made of the windows themselves (each row matched by the window's whole rendered text, a
retry's row also by the correction its packet carries). Run A reads every window: one forced omission skipped on the
first attempt (refused, retried with its lines, expanded on the second), a retyped quote, a quote of the omitted
middle, a pending and a resolved event. Run B skips the forced omission twice, so its window fails and the overlap
rows it owns stay uncredited. Run C credits a range its file does not owe and is refused by the hand-back. Then
each step-4 departure on one answer, the overlap refusals, windowless and drifted views, the unit statuses and the
hand-back, without a call.
