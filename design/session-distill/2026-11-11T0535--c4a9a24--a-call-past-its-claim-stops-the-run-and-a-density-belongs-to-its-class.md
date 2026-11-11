---
created_at: 2026-11-11T05:35:00+09:00
head: c4a9a24
kind: design
supersedes: null
---

# A call past its claim stops the run, and a density belongs to its class

WP-08e, commit 3, the fixes of review W round 1 (on c4a9a24: fix_then_accept, four major findings and one minor),
folded into the commit that carries the three lead decisions of
`2026-11-11T0410--c4a9a24--a-run-may-declare-an-earlier-runs-measured-density-and-an-unmeasured-class-is-reserved-at-its-estimate.md`.
F3 and F4 are lead decisions (D-20261111-6e1079 and D-20261111-fe7671 in the lane's ledger). This record amends the
0252 and 0330 records where they say what a density is keyed by and what "at most" holds; neither is edited. The 0410
record, written in the same commit, states the seat keying and the claimed retries as this one does.

## F1: a gather is packed in the order the window lists its omissions

The dry measures a window's gather over its skipped omissions in the window's manifest order; the live path gathered
them in the order the accepted answer decided them, and the answer check accepts any order. The reviewer's probe:
middles of ten lengths packed in manifest order make six gather windows and 622,417 first-request tokens; decided in
the order [7, 9, 10, 5, 2, 6, 1, 4, 3, 8] they made eight and 667,800, above the dry's claimed maximum.
`Reader.file` now sorts the window's skipped omissions by their position in the window's rows before it gathers.

## F2: a gather's reason stays on the coverage record

A gather the provider deferred defers its unit, and a gather that failed beside a failed window leaves it read
partial. `observation_scope` read the files' reasons only for a unit read complete, and named a session in
`not_source` only when nothing blocked it, so both reasons fell out of `resolutions.json`, leaving a generic deferred
session in `incomplete`. The reasons are the files' whatever the unit's status: a session whose files name reasons is
in `not_source` with them and its status, beside the incomplete basis that still names it as blocking.

## F3: a density is keyed as a reservation class is

`class_key` keys a reservation by stage, the complete seat and case type; density was read per host and kind, so a
same-host seat change borrowed the other seat's density (the reviewer's probe: an S3 sample of the sonnet seat read
`measured: claude/S3:window/1 samples` for an opus seat). Lead decision: density is keyed exactly as the classes.

- `dispatch.density_samples` keys by `(seat, "<stage>:<case type>")`; `measured_density(run_dir, seat, stage,
  case_type, declared)` reads the seat's own; the basis reads `measured: <seat>/<stage>:<kind>/<n> samples`.
- The measured table, and so a declared `density` table, is `{seat: {kind: entry}}`. S0 refuses a key that is not a
  seat (`provider:model/effort`) or a seat the declaration does not name, `DECLARATION_INVALID density.<key>`.
- **The retry margin stays pooled per host** (`retry_share` reads every seat and kind of the host): what a refused
  structured output's error carries is the host's text, not a seat's, and C2 measured two retries in all.

## F4: a call past its claim stops the run

The "at most" claim counted one retry, and nothing limits the host to two main requests: a second retry past
`first + cap + margin` was recorded by S4 as `within_claim=false` and the stage went on. Lead decision, consistent
with bound.py's posture: an observed request above the claim is a named stop of the run before any further call. The
host's own retries are not capped; they are held to the claim.

- **The claim.** A call holds its first request and `count` retries, each carrying an answer at the output cap and the
  error share on top of the request before it: at most `retries + 1` main requests, none past `first + retries ×
  (cap + margin)` (`dispatch.input_at_most`; `spend_at_most` sums the requests and their answers). `count` is the
  declaration's `retry.count`, else `RETRIES_CLAIMED` (1); the margin is the declared `retry.margin`, else
  `RETRY_ERROR_TOKENS`, raised by a larger share the run measured. `retry` is the declaration's second optional field;
  S0 refuses one that names neither (`DECLARATION_INVALID retry`).
- **Which calls carry it.** Every call reserved with an estimate it can be held to: its packet's driver bytes and its
  output cap known, and its host's hermetic allowance measured (`Supervisor.claim_terms`). The reservation records the
  terms; `call.json` `bound.claim` holds the claim on the bytes the call really sent (`call_claim`), and is null for a
  call reserved without them (no output cap, no measured allowance), which is held only to the bound and its
  reservation. This covers calls reserved at the measured p95 as well as provisional ones.
- **The stop.** Settlement reads the usage record; more main requests than claimed, or one past the claimed input, is
  `CLAIM_EXCEEDED` (`bound.claim_excess`: the call, its main requests and the largest, beside the requests and input
  claimed). It is stamped with the declaration's sequence as a bound excess is, and lifts only on a later amendment of
  `retry` (`bound.LIFTED_BY`): a re-declared count or margin, never `host_allowance`, never one recorded earlier. A
  bound stop and a claim stop standing together are kept unstamped, so terminal: one entry kept for either would let
  the other's amendment lift a run the first still stops.
- **The call and the stage.** The call's answer, usage and spend stay as measured (charged measured); the call then
  fails by name, so the stage that made it does not complete. A stage resumed after the stop lifts makes a new
  attempt: the stopped attempt was never judged, so it is not reused.
- **S4.** `observed` reads the requests against the claim as well as the largest request (`requests_at_most`). An
  accepted formation call outside its claim - one reused under a declaration whose claim it now exceeds, or one no
  claim was recorded for - stops the run (`Supervisor.stop_on_claim`, unless a stop stands) and S4 refuses it by name;
  `within_claim=false` no longer coexists with a completed stage.
- **The dry** writes `retries_claimed` and its basis beside the margin.

## F5: the eleven c2 rows were ten

The 0330 record says "pretrial rows `c2-*`, 11 rows, all caught". `rows-c2.py` holds thirteen entries: three
baselines (`none-*`) and ten revert rows, and the logs `pt-c2-a`, `pt-c2-b` and `pt-c2-c` name exactly those ten as
caught. No eleventh row was written or run: the count was wrong, and the review packet repeated it. The 0330 record is
dated and stays as written; this is its correction.

## The collateral failures under the provisional revert

With the provisional reservation reverted (rows `c3-tranche-bound`, `c3-sizing-missing`), 34 stage_read controls fail
beside the named ones. They are the broad fixtures' real reservation refusal: every broad fixture whose reading skips
a middle makes a gather, and an unmeasured gather with no estimate is refused `CALIBRATION_PROVISIONAL` in a broad
tranche. They are not 34 independent gather controls. Under `c3-tranche-bound` six dispatch controls of F4 fail too:
their calls reserve broadly in an unmeasured class.

## Controls

Pretrial rows `rows-c3f.py`, 40 rows: six baselines passing as they are, the 19 revert rows of `rows-c3.py` (six
retargeted where these fixes moved their lines), and 15 new ones, all caught:

- `stage_read`: a window's gather with its omissions decided in reverse order packs into the windows of one decided in
  order, and sends what the dry claimed (F1); a provider-deferred gather keeps `gather_deferred: provider`, and gathers
  that failed beside a failed window keep `gather_failed`, on the coverage record beside the incomplete basis (F2, two
  rows); another seat of the same host borrows nothing of the seat a call measured (F3); a declared retry is what each
  window's claim holds and the dry names it (F4: the count, its application, the margin).
- `declare`: a declared density keyed by something other than a seat the declaration names is refused (F3); a declared
  retry that names neither field is refused (F4).
- `dispatch`: a call of three main requests stops the run by name with the counts and amounts, its measured spend kept,
  and the next reservation is refused; an amendment of another key does not lift it and a later retry amendment does;
  a call of two requests within its claim does not stop; a call whose retry takes more input than claimed does (F4).
- `bound`: a third request, or one past the claimed input, is an excess; a claim stop is named, not lifted by
  `host_allowance` nor by an earlier retry amendment, and lifted by a later one; a bound stop and a claim stop together
  are terminal (F4).
- `stage_form`: a formation call of three requests stops the run and S4 does not complete; after a margin amendment
  the next attempt is stopped again; an accepted call no claim was recorded for, past S4's own claim, stops the run and
  S4 refuses it; once the count is re-declared the same shape completes; two requests within the claim complete (F4).

## What this does not establish

- That a live host retries at most once: C2 measured two retried calls of thirteen, each once. A run whose host retries
  twice stops, and continues only on a re-declared count.
- That the fewest density of a class holds for its next call: a call denser than every earlier one of its class can
  pass its claim on a retry and stop the run. Floor and declared bases are as high as the class's measurements allow.
- Any claim of a call no estimate can be made for; such a call has none.
