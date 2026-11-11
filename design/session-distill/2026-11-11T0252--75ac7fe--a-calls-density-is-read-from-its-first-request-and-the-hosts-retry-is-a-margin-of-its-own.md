---
created_at: 2026-11-11T02:52:00+09:00
head: 75ac7fe
kind: design
supersedes: null
---

# A call's density is read from its first request, and the host's retry is a margin of its own

WP-08e, commit 1 of 2. Lead decisions D-20261111-c79b78 (density) and D-20261111-8a4ddf (the retry), WP-08e's
stage 0 answers Q1, Q2 and Q4. This record corrects the C2 record
(`2026-11-11T0015--9d9482f--c2-read-nine-sessions-within-its-limits-and-its-recall-misses-gather-in-one-dense-codex-child-window.md`)
and amends S4's capacity records (`2026-11-06T0826--e44d63e--s4-is-bounded-by-its-own-seat-and-holds-what-it-reads-to-the-records-that-wrote-it.md`,
`2026-11-06T0903--ed6e3d3--s4s-admitted-capacity-is-in-each-calls-record-and-each-attempt-is-measured-under-its-own-id.md`,
D-20261106-224fa3); none of them is edited.

## What C2 measured, corrected

The C2 record says the Codex child's first window (window 8) ran at 1.01 bytes per token, dense enough to make a byte
almost a token. It did not. That call made two main requests: the host refused the first structured output and asked
again, so its usage record holds two requests (`attempts: 2`), and 114,576 is their sum. Read by request, from the
run's usage and call records (counts only):

| Call | Driver bytes | First request | Bytes a token, first | Second request | Bytes a token, largest | Sum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S3 window 8 | 115,742 | 53,546 | 2.16 | 61,030 | 1.90 | 1.01 |
| S4 form | 46,530 | 20,491 | 2.27 | 26,794 | 1.74 | 0.98 |

Every other C2 call made one request: the windows ran 1.85 to 2.09 bytes a token and the stitches 1.78 to 2.01, so
the fewest a window measured, 1.852, was itself below the 1.94 both estimates assumed. The first requests of the eight
windows total 216,952 input
tokens, inside the S3 dry's 214-244k; the 61,030 of window 8's retry is what the hour's S3 input (308,055 with the
stitches) holds beyond that. What window 8 shows is a retry, not dense text: 2 of C2's 13 calls retried, which is
F-32.

## The rule

- **Density** is read per host and kind of call - S3 window (its expansions are window calls), S3 stitch, S4 form -
  from the run's own calls (`dispatch.measured_density`): each call's driver bytes (`call.json` `bound.driver_bytes`)
  over the input of its FIRST main request (input, cache creation and cache read; `usage.first_input`), the fewest
  over the sample, rounded down to a thousandth so the tokens it gives are high. Where the run has no measured call of
  that host and kind the density is `DENSITY_FLOOR`, 1.0 byte a token, the assumption bound (a) already makes. Its
  basis is named wherever it is used: `measured: <host>/<stage>:<kind>/<n> samples` or `floor: 1.0`.
- **The retry** is counted once and additively. What one request of a call takes at most
  (`dispatch.input_at_most`) is the first request - the bytes at the density plus the host's allowance - plus one
  answer at the call's output cap plus an error-share margin: what a later request added beyond the request before it
  and that request's answer (`usage.retry_shares`). The margin is `RETRY_ERROR_TOKENS`, 1,118, the larger of C2's two
  shares (window 8: 1,118; S4: 584), raised by a larger share a run measures (`dispatch.retry_share`).
- **S4's claim** (`stage_form.form_budget`, `input_at_most`): `form.json`'s packet carries the first request
  (`first_request_tokens`) and the at-most (`input_tokens_at_most`) with their bases; the capacity check adds that
  request's output reservation, so it holds the retry's request whole. The accepted call's observation keeps its first
  request (`input_tokens`, `bytes_per_token`), its main requests and the largest of them apart, and says whether the
  largest stayed within the claim (`within_claim`). `tables/form_capacity.json` (1.94, from C1's S3 calls of another
  seat) is deleted.
- **S3's dry** (`read-dry.json`) estimates each window: the first request and the at-most. Its `estimate` holds the
  windows' first requests with their basis, the retry as a line of its own - the rate the run measured over the host's
  calls, what that rate of windows adds at most, and what every window retried once would add - and names expansions
  and stitches as `not_estimated`, since what they send follows from the answers. `not_measured` is gone.
- **Bound (a) is unchanged.** A view window is still cut so its driver bytes and the allowance stay within
  `INPUT_BOUND` at a byte a token, and the observed check still stops a view-window call whose request read more. The
  retry is why an observed request can exceed the first-request estimate: window 8's second request read 61,030
  against its first 53,546, both far below the bound.

## What follows from "the run's own calls"

The density and the retry rate come from calls the same run made, as the calibration samples do. Two cases read at the
floor because of it:

- A dry S3 before any call of a fresh run. C2's eight windows were 436,268 driver bytes; at the floor their first
  requests estimate 466,628 against the 216,952 measured, about twice. The estimate is high, never low, and as high
  as bound (a) already admits.
- S4, which makes one formation call a run: its claim reads at the floor unless the run holds an earlier formation
  attempt. On C2's packet that is 46,530 + 3,795 + 32,000 + 1,118 = 83,443 at most in one request, within the
  1,000,000 capacity with room.

Carrying samples from an earlier run (the way `Supervisor.seed_from` seeds calibration in the self-tests) would make
both measured; it is not built, and nothing here forecloses it.

## Controls

Each fails by name when its fix alone is reverted (pretrial rows `c1-*`, 13 rows, all caught):

- `usage`: a call's density reads its first main request, never the sum or the largest (C2's window 8 as counts);
  a retry's share is what its request added beyond the request before it and that request's answer; a first request
  not measured gives no density.
- `stage_form`: a run with no formation call reads S4's packet at the floor, named, the margin added once; of two
  formation calls measured at 1.5 and 2.0, the fewest - below the old 1.94 - makes the claim; C2's two-request
  formation call reads 2.270 by its first request, its retry counted apart, and its observation keeps the first and
  the largest request apart; a larger measured error share raises the margin; a retry that used the whole margin stays
  within the claim and one token less does not.
- `stage_read`: a dry S3 in a run with no window call estimates at the floor, named; C2's window-8 shape planted as an
  earlier call is read at 2.161, the dry names it as measured and carries the retry line; a host with no measured call
  of the kind reads at the floor whatever another host measured.

## What this does not establish

- That 1,118 covers every refusal's error text: it rests on two retries of one run.
- Any Codex density: no C2 call ran on a Codex seat, so a Codex seat reads at the floor.
- Why the two calls were refused, or how to refuse fewer: F-32.
