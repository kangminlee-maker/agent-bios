---
created_at: 2026-11-10T10:40:00+09:00
head: 6114f54
kind: review
supersedes: null
---

# WP-08c live2 held its limits, and dw2's carried request closed on the agent's reply, not on the decisive line

WP-08c's live pair, run on the merged tree (`6114f54`, tree equal to `22c7a95`'s package plus WP-09) through the real
seat. Both legs are synthetic fixtures, so their text is quoted. Owner limit: D-20261105-82fdee, with D-20261106-281029
(9 calls, 85,000 input, 20,000 output).

## The calls

**live1, 2026-11-06 04:34 KST, tree `22c7a95`.** One call, refused by the provider before any model work: the
seven-day usage limit (`usage_limit_reached`), 0 input and 0 output tokens measured. dw2's unit stayed `deferred` and the
pair ended `PAIR-END rc=20`. Under D-20261106-281029 it does not count against the limit.

**live2, 2026-11-10 10:27-10:29 KST, tree `6114f54`.** Claude Code 2.1.317 before and after,
`claude-sonnet-5-5/high` observed on every call.

| Leg | Call | Input | Output |
| --- | --- | ---: | ---: |
| dw2 | window w1 | 7,569 | 1,692 |
| dw2 | expansion | 8,797 | 1,616 |
| dw2 | stitch | 7,120 | 625 |
| dw5 | window w1 | 11,425 | 2,508 |
| dw5 | window w2 | 9,145 | 3,388 |
| dw5 | expansion | 10,196 | 2,075 |
| dw5 | stitch | 6,872 | 560 |
| **total** | **7 of 9** | **61,124 of 85,000** | **12,464 of 20,000** |

Every role and cache are counted; no call was unmeasured. Every call was accepted at its first attempt: 0
`UNKNOWN_LABEL`, 0 `EXPOSURE_ORDER`, 0 `SCHEMA_INVALID`, 0 stage-check failures, 0 retries. Four calls passed their
provisional reservation of 6,432: dw2's window (9,261) and stitch (7,745), and dw5's window w1 (13,933) and stitch
(7,432). The pair guard held.

Each call's stream carried one `rate_limit_event`. The seven-day utilization it reports is an integer percent, and it
read 0 before and after all seven calls (status `allowed`, reset 2026-11-16 09:00 KST). About 73,600 tokens therefore
moved it by less than one unit; what a token costs against the owner's limit needs a measurement around a larger run.

## dw5: as its fixture intends

Read whole. All five judgements equal the intent (ask 2, ask 3, ask again, ask 4, test run); ask 1, before the guide was
read, is left out. Both resolutions are `not_observed` on a `source` basis, as intended. The search forced the expansion
once, and no occasion split across instances.

## dw2: the plan's done-when holds; the carried request closed on the reply

Plan WP-08 done-when 2 (`2026-10-20T2119--cc0498f--implementation-plan.md`) asks that the decisive outcome in the
omitted middle of a successful tool result be found after expansion and not found without, live through the real seat.

- **Read whole**, and no event is left pending after the fold. The omitted span is whole lines (line 3, characters
  1,176 to 7,377). The two earlier live runs left a cleanup event open on a line the expansion cut
  (`2026-11-05T2113--0546a25--...`); WP-08c's whole-line middle removed it, and this run confirms that live.
- **Not found without expansion.** The decisive line is in 0 of 1 window packets.
- **Found after expansion.** The expansion's packet shows it (1 of 1, accepted), and the expansion's claim quotes it:
  `restore verified: all 4812 rows match the backup, none missing`.

Done-when 2 is met by its words. The pair report's fifth condition, that the carried event `pe-1` resolve on a quote of
that line, is not met:

- The stitch resolved `pe-1` (the request on line 1) on two of the window's claims: the agent ran
  `restore-backup --into staging --verify`, and its only reply was that the command finished. The claim quoting the
  decisive line was joinable and was not chosen.
- That claim itself reads the line as printed before the copy work finished: "It may not cover the later batches, so it
  may not show that every row came back."
- The fixture invites that reading. `fx_decisive_log` inserts the decisive line between `copied batch 019` and
  `copied batch 020` of forty, so in the source the verification does precede half of the copying.
- The two earlier live runs (WP-08's dw2-live2, WP-08b's live1) resolved `pe-1` on the decisive line. This is the first
  of three that did not.

Nothing the run needs was lost: the decisive line is a quoted claim of the unit S4 reads, and the request's outcome as
the stitch recorded it, an agent that did not answer the question it was asked, is true of the fixture.

## What follows

Lead decision D-20261110-253d6a: the stitch contract does not change, and dw2 is not run again now.
The fixture places the decisive line after the last copy batch, still inside the omitted middle, when a dw2 live run is
next approved; that run then shows whether the stitch links a request to an outcome the reader has no reason to doubt.
If it still closes the request on the reply, the stitch contract is the question.
