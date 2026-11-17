---
created_at: 2026-11-11T07:10:00+09:00
head: 78e1e92
kind: design
supersedes: null
---

# A stop is a record per obligation, and a call that stopped the run is a failure

WP-08e, commit 4: the fixes of review W round 2 on 78e1e92 (rework, eight major findings and one minor), all of
them about the claim stop of round 1's F4, which existed but was not enforced end to end. Lead decision
D-20261111-b91759 (closed: a claim stop parallel to the bound stop; a terminal dual stop). This record amends the
0535 record of commit 3 where it describes how the claim stop is recorded, lifted and judged, and where it calls a
bound stop and a claim stop standing together terminal. The 0535 record is not edited.

## One stop mechanism

- **A stop is a record per obligation.** The supervisor ledger's `stops` holds `{code: record}`: the bound's
  `INPUT_BOUND_EXCEEDED`, lifted by `host_allowance`, and the claim's `CLAIM_EXCEEDED`, lifted by `retry`
  (`bound.LIFTED_BY`). Each record carries the declaration ordinal it was stamped with, and it stands until its own
  key is amended later than that ordinal. The run is open when no record stands (`bound.standing`, `bound.blocked`,
  which names every standing stop in the order they were recorded). A ledger written before this held one `stopped`
  entry; it reads as the mapping of that entry (`bound.as_stops`).
- **No dual terminal.** Records of different obligations never combine (`bound.kept`). Each lifts by its own
  amendment, in either order, and a lifted stop never combines with a later one (F3, F6).
- **Within one obligation, `bound.strongest` decides, and that is the standing rule.** A stamped record that a later
  amendment lifted is older than any stamped offer, because the lifting amendment precedes the offer's stamp, so a new
  breach after an amendment is kept and stands. An unstamped offer is terminal and kept either way. A terminal record
  never lifts.
- A call record carries its own offered stops as `stops`, one per obligation. The gate schema keeps `stop` for
  records written before this.

## Both obligations, at every settlement site

`Supervisor._offer_stop` decides both obligations independently over the monitor rows in hand at its three sites:
after following the host, after reconciliation, and on the way out of a failure.

- The bound applies to a view-window call; the claim applies to a call that carries one.
- Each obligation's stop is offered once per call. A bound stop no longer hides a claim breach (F3).
- The claim is no longer decided only after the usage record is written. A failure in projecting usage still leaves
  the stop persisted, and the caller gets the original exception (F4).
- A preparation failure fails closed for its own obligation.

## A call that stopped the run is a failure

- The call is charged `failed`. Its measured spend is kept and it is not a calibration sample. Its first-request
  density stays a density sample: it measures the class, and it is why the claim was false.
- The gate refuses it on two readings (F1): the stop the call recorded, and its usage against `bound.claim`, so a
  call whose stop record was lost is refused all the same.
- `gate.accepted` never yields its answer, and `Supervisor.reusable` names it `REUSE_NOT_ACCEPTED`.

## A run stop aborts the stage under every posture

`records.RunStopped` is a `Refused` that `run_items` raises as it is, under production too, and after it no item
starts. The dispatcher raises it in three places:

- for the stops a call offered;
- for a reservation refused while a stop stands;
- for a call reserved before the stop.

S4 raises it from its fallback. A production S3 whose call breaches its claim therefore ends by that call's name, its
stage `failed`, no unit quarantined and no hand-back written. A production S3 over a run whose stop stands ends at its
first reservation (F2).

## The claim holds the first request too

A call's claim (`dispatch.call_claim`, S4's `form_claim`) is `{requests_at_most, first, step, input_at_most}`:

- at most the first request and the declared retries;
- the first request within `first`, its reserved estimate: the bytes it sent at its class's density (the floor where
  unmeasured) plus the allowance;
- the k-th retry within `first + k × step`, where `step` is one answer at the cap plus the error share
  (`bound.claim_breaches`, each breach named by count or by request).

The reservation (`spend_at_most`) therefore bounds every request sequence the claim admits, provided each answer stays
within the output cap the host enforces. Round 2's example, a first request of 95,000 against an estimate of 53,795,
is a breach by name (F7). A claim recorded before `first` and `step` were named still holds each request within
`input_at_most`.

This is the cost of a true bound, already named in the 0535 record: a call denser than its class's estimate stops the
run on its first request. Lifting the stop takes an amendment of `retry`, the claim's key. The call's own density is
then a sample of its class, so the next call's estimate reads it.

S4's fallback offers the stop whatever the ledger already holds, so standing decides and presence does not (F5). After
a margin amendment lifts it, a reused attempt that still breaches stops the run again, stamped later.

## The dry sums every declared retry

Each window's `input_estimate.retries_at_most` is the sum over the declared retries of `first + k × (cap + margin)`.
`tokens_if_every_window_retried` and `tokens_at_rate` are built on that sum (F8). With one retry, as before, the sum
equals `at_most`.

## S0 refuses what no consumer could read whole (F9)

- A `retry.count` or `retry.margin` that is not an integer is refused, including an integral float such as `2.0` and
  a bool (`DECLARATION_INVALID retry.<key>: an integer`).
- A density kind must match `<stage>:<case type>` whole (`declare.DENSITY_KIND`, fullmatch). A trailing newline is
  refused instead of being read as nothing.
- A density that is not a finite number is refused.
- Each of these is refused through `declare --amend` too, which is the path that lifts a claim stop. The claim terms
  its consumer computes stay those of the declaration as it stood.

## Controls

Pretrial rows: `rows-c4.py`, 28 rows, one fix one row. Eight are baselines (bound, records, gate, declare, dispatch,
stage_read, stage_form, views); all eight pass, `none-views` included. The 20 revert rows are all caught, and none
printed a traceback. Logs: `pt-c4-a` (baselines), `pt-c4-b` (F1 to F4), `pt-c4-c` (F5 to F9) and `pt-c4-d`.

The first run of the two first-request rows missed. The dispatcher's control planted a first request above the last
retry's ceiling as well, so a claim without the first-request rule also caught it. The control now plants the first
request 1,000 tokens above its estimate and below that ceiling, and asserts the placement; `pt-c4-d` re-ran both rows
and the dispatch baseline.

- **F1:** the gate refuses a call that stopped the run, and the call is charged failed with no calibration sample; it
  is not reused; a call whose stop record was lost is refused from its usage; the gate accepts a call within its claim
  (baseline).
- **F2:** run_items raises a run stop as itself under production (one and four at a time) and under development;
  production S3 ends failed on a claim breach; production S3 over a standing stop ends at its first reservation; a call
  reserved before the stop is refused as a run stop.
- **F3:** a view-window call past both the bound and its claim leaves two records; host_allowance alone does not
  reopen the run, and the retry, its own key, does; at the rule, the two records are both standing and neither is
  terminal.
- **F4:** a call past its claim whose usage projection fails stops the run, and the caller gets the original failure.
- **F5:** S4's fallback after a margin amendment stops the run again, stamped later than the lifted stop.
- **F6:** in both orders (claim lifted then bound, bound lifted then claim), at the rule and in the dispatcher, the
  later stop stands with its own ordinal and its own key alone reopens the run.
- **F7:** a first request past its estimate but within the last retry's ceiling is a breach (at the rule, in the
  dispatcher with the stage budget equal to its reservation, and in S4's own claim).
- **F8:** with two declared retries, the dry's total is both retry requests of every window, computed in the control
  from the bytes at the floor; at a measured rate, `tokens_at_rate` is the rate times that total.
- **F9:** S0 refuses each of the three by name, and so does the amendment path.

Every session-distill self-test passes (34 modules: runlib's and the four top-level scripts with a self-test,
`plain-asks.py` and `update-state.py` now included; `allst-c4.log`).

## What this does not establish

- Behaviour on a live host. No model call has run under the claim.
- That a class's fewest density holds for its next call. A denser call stops the run, by design.
- That an orchestrator above the stages stops on a `RunStopped`. The stages end failed; what runs them is not in this
  package.
