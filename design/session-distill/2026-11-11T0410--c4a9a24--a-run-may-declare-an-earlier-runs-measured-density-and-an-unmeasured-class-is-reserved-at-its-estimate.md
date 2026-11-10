---
created_at: 2026-11-11T04:10:00+09:00
head: c4a9a24
kind: design
supersedes: null
---

# A run may declare an earlier run's measured density, and an unmeasured class is reserved at its estimate

WP-08e, commit 3. Lead decisions D-20261111-2a7e3d (declared density), D-20261111-638515 (calibration is the class's)
and D-20261111-7d6d62 (the gather marking's control). This record amends the two earlier WP-08e records
(`2026-11-11T0252--75ac7fe--a-calls-density-is-read-from-its-first-request-and-the-hosts-retry-is-a-margin-of-its-own.md`,
`2026-11-11T0330--180e352--the-middles-a-windows-reading-skipped-are-read-by-one-gather-or-named-where-they-are-not.md`)
where they say what follows from reading only the run's own calls; neither is edited.

## Declared density

- `run.json` may carry `density`, an optional field of the declaration: `{seat: {"<stage>:<case type>":
  {bytes_per_token, measured_in, samples, at}}}`, an earlier run's measured table, keyed as a reservation class is (the
  complete seat; review W round 1, F3, in the 0535 record of this commit). Whoever declares the run writes it,
  as `host_allowance` is written: a declared, re-measurable number, never a constant in code and never copied forward
  by the code. S0 refuses an entry without its provenance - the run that measured it, at least one sample, an
  ISO-8601 time - as `DENSITY_UNPROVENANCED`, a key that is not a seat the declaration names or a kind that is not a
  stage's as `DECLARATION_INVALID` (`declare.density_errors`).
- **Basis order** (`dispatch.measured_density`): the run's own sample, `measured: <seat>/<stage>:<kind>/<n> samples`;
  else the declared entry, `declared: <run id>/<n>`; else the floor, `floor: 1.0`. S4's claim says which it rests on
  (`form.json` `packet.density_basis`), and the dry names the basis of each window's estimate and of each gather's.
- **The measured table** (`dispatch.measured_table`) is written at the end of `read.json`, `read-dry.json` and
  `form.json` as `density_table`, in the shape a later declaration takes, and S4's report ends with one line per seat
  and kind. The self-tests that compare two runs' records leave it out with the reuse fields: its times are its
  calls' and a resumed run's extra attempt changes its counts.

With C2's table declared, a fresh run's dry reads its windows at 1.852 rather than at the floor, and its S4 at 2.27
(the one formation call it measured); a gather has no measured entry until a run makes one.

## Calibration is the class's

A class with fewer than five measured calls admits its call under a provisional reservation at that call's own
estimate (`Supervisor.provisional_amount`), in any tranche, as long as the budget left holds it; the sixth call on
is reserved from the measured p95, as before. The estimate is the call's spend at most (`spend_at_most`): its first
request (its packet's driver bytes at the density above, with the host's measured hermetic allowance) and an answer
at the output cap, then each retry its claim holds - one unless the declaration's `retry` says otherwise (the 0535
record) - its request at most (`input_at_most`) and its answer. `Supervisor.item`
sizes each attempt's packet under the id its reservation will most likely take and hands it to `reserve`; the
reservation records the estimate it rests on. A reservation the budget cannot hold records the item not done, so a
gather is then named `gather_deferred: budget`.

`CALIBRATION_PROVISIONAL` and `gather_deferred: calibration` now name only a call no estimate can be made for: one
that declares no output cap, or whose host has no measured hermetic allowance (`Supervisor.estimable`). S3 declares
its cap and its view-window seat needs a measured allowance to read at all, so a reading S3 does not meet the case;
the name is kept for the call that would. A class's calibration tranche still runs it at concurrency one.

What the estimate costs at C2's numbers: with S3's output cap of 32,000, three answers at the cap are 96,000 of any
call's provisional reservation. A gather of window 8's skipped middles, about 29k driver bytes, reserves about 160k
at the floor; after C2's hour of S3 had spent about 308k of its 400,000, that does not fit, and the gather would be
named `gather_deferred: budget`. A broad tranche reading twelve units at once holds up to twelve such reservations
open together. The budget a run declares for S3 has to hold its provisional calls, or they are named, not run.

## The gather marking

An occasion a gather reads is of the expansion side when readings of one record are settled (`keep`: a gather's
`where` carries `/g/`). Its control plants a window's reading and its gather's reading of one record judged
otherwise: the gather's verdict is kept and the window's superseded; without the marking both fall on the window
side and the occasion is dropped as conflicting.

## Controls

Each fails by name when its fix alone is reverted (pretrial rows `rows-c3.py`, 24 rows: 19 revert rows - 15 of this
commit and four of commits 1 and 2 retargeted where this commit moved their lines - all caught, and five suites
passing as they are; the commit's full set, with the review fixes, is `rows-c3f.py` in the 0535 record):

- `declare`: a declared density with its provenance is accepted; one without it, or with no samples or an unreadable
  time, is `DENSITY_UNPROVENANCED`; one keyed by a host, or by a seat the declaration does not name, is refused.
- `stage_read`: with no window call of its own the dry reads the declared density, each window naming it, and the
  measured table is empty; a window call of the run's own is preferred over the declared density, and the table holds
  it in the declared shape; an unmeasured gather in a broad tranche is reserved at its own estimate (its spend at most
  at the floor, written out in the control) and reads its middles; with three gathers seeded, the run's first two are
  provisional and the third - the class's sixth call - is reserved from the p95 of the five measured; a provisional
  gather whose estimate the budget cannot hold (a declared density of a thousandth of a byte a token) is not done and
  named `gather_deferred: budget`; a gather no estimate can be made for is named `gather_deferred: calibration`; the
  gather marking keeps the gather's verdict.
- `stage_form`: with no formation call of its own S4's claim rests on the declared density and names it, and its report
  ends with the run's measured table.
- `dispatch`: an unmeasured class's call with its packet and cap known is reserved broadly at its own estimate; one
  without a cap is still left to a calibration tranche.

Two of the controls first tested themselves: one computed the expected reservation with the function under test, so
a reverted `spend_at_most` changed both sides alike, and one read a key directly, so its revert raised instead of
failing by name. Both now write the expectation out and read with a default.

## What this does not establish

- That a declared density holds for a later run: it is the earlier run's fewest, and the run's own first call of the
  kind replaces it.
- That provisional reservations leave room for the run: at a 32,000 cap each holds about 96k for its answers.
- Any gather's measured density or cost: none has run live.
