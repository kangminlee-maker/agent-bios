---
created_at: 2026-10-02T00:26:45+09:00
head: 8ef2bad
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20261001-97ff18, D-20261001-fa937f, D-20260930-c06461
---

# V1's tenth bound review found Codex's probe counting another conversation's compaction, and the probe now reads only its own conversation and turn

This follows the [23:09 restructure record](2026-10-01T2309--3551ccb--v1-restructure-record.md)
and the [23:25 direct-use record](2026-10-01T2325--e8b281b--v1-acceptance-after-restructure-direct-use-record.md).

- **The record.** V1 was recorded into `run-19` at `8ef2bad`, and all 21 cases passed. `run-19`
  is `run-18` without V1's ninth, unpublished attempt (`v1-accept/make_run19.py`).
- **The review.** One bound review ran on `gpt-6-astra` at max effort, hermetic and read-only,
  from 23:31:37 to 23:51:35 (`review-v1-20261001-r10/`).
- **The result.** `defects_found`: one medium finding, and 19 stated checks. The recomputable
  fingerprints and case totals match. P00 and P01 would remain accepted.

V1's attempt in `run-19` is not published. V1 is recorded again, in a new run, after this repair.

## What the review found, re-derived here

### Medium: a compaction of another conversation qualified this one's

This goes against done-when [6]: a `rehydrated` route is qualified only where the host compacted
the session the probe asks.

- **The reviewer's case.** The probe asks Codex to compact conversation A. The server reports a
  `contextCompaction` item and a completed turn of conversation B, then A's compaction failing.
  A then answers with the code it already held. The probe kept `worked`; the right outcome is
  `no_response`, because A was never compacted.
- **Reproduced here** with the same notifications against the reader at `8ef2bad`:
  `compacted("A")` returned true.
- **The protocol.** In the app-server schema Codex CLI 0.159.2 generates (v2), every turn, item,
  compaction and error notification names its `threadId`, and each item, compaction and error
  its `turnId`. `turn/start` answers with the turn's `id`. The same schema has a
  `thread/started` notification, and a `spawnAgent` tool call naming a sender thread and receiver
  threads: one server may report more than one conversation, such as a subagent's.
- **In the code.** `Server` read every notification as the probe's. `compacted` counted any
  compaction report and the first completed turn. The same reading held for a turn: `ended`
  waited for any `turn/completed`, and the reply was every agent message, of any turn. So a
  `new` or `current` probe could also have been answered by another conversation's or an earlier
  turn's message.

## What the owner chose

The finding is fixed now, across every notification the probe reads, and V1 is recorded again
and reviewed an eleventh time (`D-20261001-97ff18`). The closed alternatives are deferring it
with the finding recorded, and judging it not a defect because a probe's server holds one
conversation: Codex subagents run on conversations of their own.

## What changed

- **`workenv/hosts/codex.py`.**
  - `Server` keeps the conversation it acts on and the turn it waits for. While it acts on one,
    a notification that does not name it is skipped. A request Codex makes of the client is
    still refused before that, as it was.
  - `ended` waits for the `turn/completed` of the turn `turn/start` returned.
  - A reply is the agent messages of that turn only.
  - `compacted` waits for this conversation's first `turn/completed`, and counts the compaction
    only where that turn completed and Codex reported the compaction in it.
  - The module's description says so.
- **`gates/workenv/units/v1/fakehost.py`.** Codex's `turn/start` answers with a turn id, and every
  notification carries its conversation and turn. Four modes are added:
  - `crosscompact`: another conversation's compaction and completed turn, then this one's
    compaction failing (the reviewer's case);
  - `stalecompact`: a compaction reported in an earlier turn, and the compaction's own turn
    completing without one;
  - `crossturn` and `staleturn`: another conversation's turn, or an earlier turn of this one,
    says the code and completes; then the probe's own turn completes saying `NONE`.
- **`gates/workenv/units/v1/test_probes.py`.**
  - A compaction reported and then failed (`compactitemfails`), `crosscompact` and
    `stalecompact` each leave the `rehydrated` probe `no_response`, and the session is not asked.
  - `crossturn` and `staleturn` leave a `new` and a `current` probe `refused`: the probe's turn
    said `NONE`, whatever another turn said.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1zh.py`, `mutate_v1zh-rerun-r10fix.txt`) caught 7
  of 7:
  - another conversation's notifications read as the probe's;
  - any turn's completion ending the wait;
  - any turn's agent message taken as the reply;
  - a compaction reported in any turn counting;
  - a compaction waiting for any conversation's turn;
  - the two compaction mutations of `mutate_v1zg.py` whose anchor this repair rewrote, anchored
    again: a failed compaction counting, and an unreported one counting.
- **A control that first survived.** The third mutation survived while `crossturn` and
  `staleturn` failed the probe's own turn: no reply was kept, whichever turn's message was read.
  The modes now complete the probe's turn with `NONE`, and the mutation turns `refused` into
  `worked`.
- **The earlier sweeps, re-run on this tree** (`mutate_*-rerun-r10fix.txt`), missed nothing they
  could apply.
  - `moved_anchors.py rerun-restructure rerun-r10fix` names the two compaction anchors above as
    the only ones this repair moved.
  - Every other anchor an earlier sweep cannot apply had already moved in the restructure.
    `mutate_v1zg-reanchored.py` caught all 45 of them again.
- **The V1 tests:** 590 pass. **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`, 837 outcomes) are identical to
  `outcomes-after-v1zf.json`, as they were after the restructure: 61 passed, 764 blocked,
  12 failed. V1's 21 pass.
- **Bindings.** `cases.py --bindings` equals the 13 frozen bindings `run-19` holds, so P01 is not
  reopened.

## What this does not show

- Whether the earlier real probes met another conversation's notifications. The reviewer states
  its case does not establish that, and the probes' evidence holds only what the probe kept.
  Every route is probed again on Codex with this code before V1 is recorded again.

## Next

1. Codex's three routes probed again with the committed code, and a short real use.
2. V1 recorded into `run-20`, which is `run-19` without V1's attempt (`v1-accept/make_run20.py`).
3. One bound review, whose result goes to the owner.
