---
created_at: 2026-11-04T19:22:00+09:00
head: bb9d199
kind: design
supersedes: null
---

# The live legs met done-when 2 and 3, and C1 read both of its units

WP-08 commit 7's results. Every leg ran under the bounds fixed before its first call
(`2026-11-04T1655--7c5b801--each-live-leg-is-bounded-…`): its budget, its call cap, and its first unaccepted item.
- **Host.** Claude Code 2.1.317, checked before and after every leg.
- **Seat.** S3 `claude:claude-sonnet-5-5/high`.
- **Numbers.** Counts, bytes, tokens and codes only. The owner's sessions appear by structure alone.

## The legs

The owner's cap for WP-08 is 350,000 input and 90,000 output tokens, and 31 calls (D-20261104-e9019d). Input counts
cache reads and cache creation.

| Leg | Run | Calls | Input | Output | Result |
| --- | --- | --- | --- | --- | --- |
| ⑥ re-pin | — | 6 | 20,723 | 641 | the pin (commit ⑥); the rest of the WP-08 total before ⑦'s legs |
| dw2-live1 | fixture | 0 | 0 | 0 | both attempts exited 1 before any request: Claude Code refused the 2020-12 meta-schema (1cb256d, 4432262); not counted |
| dw2-live2 | fixture | 4 | 30,348 | 5,426 | done-when 2 met: the decisive line was in the expansion's packet only, and the carried event resolved on it |
| apart-live1 | fixture | 7 | 90,872 | 11,742 | stopped at its cap with the stitch not done; the fixture showed the outcome in every earlier window's overlap (45b421e) |
| apart-live2 | fixture | 6 | 68,500 | 5,335 | done-when 3 met (below) |
| c1-live1 | `runs/c1-cand-20261103-0708b` | 1 | 17,300 (counted) | 0 | stopped 0.09 s into its first call (below) |
| c1-live2 | `runs/c1-cand-20261103-0708c` | 4 | 68,183 | 14,862 | both units read_complete (below) |
| **WP-08** | | **28** | **295,926** | **38,006** | 54,074 input, 51,994 output and 3 calls left under the cap |

## apart-live2: done-when 3

The live apart session is the request, 460 short turns and the outcome, cut into five windows (45b421e). Every call was
accepted at its first attempt, with one request each.

| Call | Driver bytes | Input | Output |
| --- | --- | --- | --- |
| w1 | 26,581 | 12,969 | 1,125 |
| w2, w3, w4 | 26,668 each | 12,965 / 12,966 / 12,967 | 1,042 / 765 / 783 |
| w5 | 13,255 | 7,306 | 1,007 |
| stitch | 18,908 | 9,327 | 613 |

- **The request.** w1 recorded it as a pending event at entry 1. The stitch resolved it with the outcome's claim, whose
  one quote is on line 462. Window 5 alone owns that line, and only window 5's claim quotes it.
- **Further events.** The reader also left a pending "long-running task" event in each of w2 to w4 (entries 118, 229,
  340). The stitch resolved all three on the same claim, and w5 resolved an event of its own.
- **Unit.** The unit is read_complete, and the coverage fold leaves no pending event.

## c1-live1: the per-episode caps were zero

- **Cause.** `work/impl/wp08/c7/make-c1-declaration.py` gives S0-S2 zero per-episode caps, so that no model call is
  possible. The leg raised `per_stage.S3` alone, so each S3 call was held to a token cap of 0.
- **What happened.** The CLI wrote `system/status: requesting`, and the monitor tripped at once (`token cap: measured
  and provisional 0 >= 0`). The supervisor froze and killed the runner and the host together, 0.089 s after the hint.
  - That is inside the 0.25 s flush window, so whether the request left is unknown. The boundary is
    `STOP_BOUNDARY_UNVERIFIED`, from that one uncertain request; no problem was recorded and no process survived.
  - No provider signal, assistant event or usage was recorded.
- **How it is counted.** The lead counts it as one call at the window's high estimate, 17,300 input (D-20261104-93c5e1).
- **The gate's codes.** PROFILE_INHERITED, CWD_OUTSIDE_MANIFEST and CONTEXT_UNDECLARED all read absent values:
  - the kill left no `capture/host.json`, and the receipt's evidence empty;
  - for example, "the runner ran profile None" and "cwd None".

  The stream's `system/init` was compared with apart-live2 w1's in canonical form:
  - cwd and original_cwd are in the cell;
  - mcp_servers, skills, slash_commands and additional_directories are 0;
  - the 4 plugins, 4 agents, 1 tool and 14 capabilities are the same sets in both;
  - every other key and scalar is equal.

  c1-live2's host.json then showed the part init cannot: profile `hermetic`, every effective-context count 0 (agents,
  appended prompts, hooks, instructions, MCP servers, skills), no listed instruction. The gate's profile, context and
  working-directory checks passed.
- **Why no earlier check caught it.** C1 ran no dry leg, since a dry leg writes into the run folder. A dry leg would not
  have caught it either: its runner prints argv and emits no stream event, so the monitor never checks a cap.
  `live-leg.py` now stops before any call when a per-episode cap is zero (EPISODE_CAPS_ZERO), and `run-leg.sh` prints the
  caps as its third line.

## c1-live2: the owner's window, 2026-11-03 07:00-08:00 KST

- **The run folder.** `0708c` was made again by S0-S2 with the fixture legs' per-episode caps (200,000 tokens,
  2 compactions, 40 turns, 5.0 USD). Its views match 0708b's: 3 windows, S2 driver bytes 127,854, the largest 50,787 of
  116,205.
- **The calls.** Each was accepted at its first attempt, with one request each.

| Call | Driver bytes | Input | Output |
| --- | --- | --- | --- |
| unit 0 (Claude) session w1 | 35,535 | 17,448 | 4,251 |
| unit 0 child w1 | 49,464 | 22,663 | 3,297 |
| unit 0 stitch | 16,285 | 8,406 | 846 |
| unit 1 (Codex) session w1 | 38,710 | 19,666 | 6,468 |

- **What was read** (structure only):

| File | Windows | Claims | Quotes (all in_window) | Events, final | Overlap rows |
| --- | --- | --- | --- | --- | --- |
| unit 0 session | 1 | 5 | 16 | 2: resolved 1, unresolved 1 | 56 |
| unit 0 child | 1 | 3 | 8 | 2: unresolved 2 | 175 |
| unit 1 session | 1 | 6 | 18 | 4: resolved 3, unresolved 1 | 287 |

  - Every overlap row lies on a record the run does not owe (D-20261103-8bfd69).
  - No expected observation was due, and no claim was dropped.
  - The child window's one omission of its own was not forced, and its reading decided `skip`. So no expansion call
    was made.
- **Stitch and coverage.**
  - Unit 0's stitch call judged its three pending events unresolved.
  - Unit 1's one pending event had no claim after it with a quote the run processes, so code left it unresolved with no
    call (`by: code: no claim after it has a quote the run processes`).
  - Both units are read_complete. The coverage fold hands the four events on as pending at their first records.

## Rates

- **Host re-asks.** The host asked again within one call in 1 of the 27 calls with a measured request: apart-live1
  w2 a2. Its first request ended `end_turn` with text and no `StructuredOutput` call, and a host-inserted user text
  preceded the second. It cost 24,272 input against about 11,300 for a single request.
- **Ids copied wrong.** Under the bracketed heading (dw2-live2, apart-live1; 11 calls), three answers were refused: two
  entries written without `/text` and one call id with its label. Under the `entry:` line (apart-live2, c1-live2;
  10 calls), none was refused, and all 10 were accepted at their first attempt.
- **The input estimate.** Over the 16 single-request fixture calls, input = 1,437 + 0.411 × driver bytes, with the
  largest residual 595.
  - apart-live2's short turns came out denser, at 0.432 per byte.
  - C1's windows came in 900 to 2,300 above the base line and within 900 of the high one (0.432 per byte, plus 600).
  - The Codex window's 6,468 output passed the 5,000 the high estimate allowed per window.

## The no-call rule for an event with nothing to join

The rule that kept unit 1's stitch at zero calls is in `stage_read`: an event whose joinable claims are empty is decided
by code before the shards are planned. It is held by the existing control "done-when 4, run N: an event whose outcome
only the overlap after its window shows has no claim to join, is left unresolved by code with no call, and is handed on
at its first record".

The pretrial reverted the rule in a clean copy: no code decision, every event planned, every event sent to its group's
shards. That control then failed by name, beside two shard controls. The row's first form deleted the rule's block and
left the file unable to compile; the harness reported it as missed, and the row was corrected before it was counted.

## Backlog

- **Zero per-episode caps.** `dispatch` admits a call whose per-episode token cap is 0, and such a call is stopped as it
  starts, perhaps after its request has left. A refusal by name before the launch would let code prevent that. Until
  then, `live-leg.py`'s EPISODE_CAPS_ZERO check holds C1-shaped runs. This is in the lead's backlog (2026-11-04).
- **done-when 3's golden apart session.** It is apart in ownership only (`2026-11-04T1852--45b421e--…`), and is in the
  lead's backlog with its revisit condition.
- **Model-written values in failure messages.** A stage-check failure message quotes what the model wrote: an entry, a
  call id. C1's logs kept only each message's code, and a report of a real run needs the same rule.
- **Noticed, not examined: the role of an overlap row.** `views.overlap_manifest` gives an overlap row the role of its
  shown entry, but an entry the overlap budget omitted carries none and falls back to `context`. So the row of an omitted
  in-window record reads `context`. Overlap accounting goes by ownership, not by role; whether any reader of the role is
  affected was not examined.
