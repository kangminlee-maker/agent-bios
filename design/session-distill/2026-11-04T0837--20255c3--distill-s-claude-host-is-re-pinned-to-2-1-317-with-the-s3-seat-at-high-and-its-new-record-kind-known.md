---
created_at: 2026-11-04T08:37:00+09:00
head: 20255c3
kind: design
supersedes: null
---

# Distill's Claude host is re-pinned to 2.1.317 with the S3 seat at /high, and its new record kind known

WP-08 commit 6, item A-1 of the stage-0 plan. The pinned versioned file 2.1.304 is gone from the machine, so every live
Claude dispatch was refused HOST_BINARY_UNPINNED. The re-pin follows `session-distill/REPIN.md`. It also moves the S3
seat to `/high`, as plan amendment row 13 asks (D-20261103-4b967e). The decision is D-20261104-71deb3.

## Steps and what each showed

1. **The binary.** `2.1.317 (Claude Code)` from the versioned file
   `~/.local/share/claude/versions/2.1.317`, which is a file and not a symlink. The `claude` symlink points at it.
   - Checked at 08:27:13 before the first call, and again at 08:30:34 and 08:36:07 after the last calls.
   - The version did not change.
2. **The flags.** `--help` on 2.1.317 lists every flag the hermetic profiles send. It was saved at 06:49 and
   re-checked byte for byte before the first call. The CLI reference page was not read (no network).
3. **One standalone hermetic call.** It ran through `claude-run.sh --profile hermetic`, at `/high` rather than REPIN's
   `/medium`, so every call measured the S3 seat. The cell root was under `/private/tmp`, mode 700.
   - Every record kind in its transcript was inside the measured sets.
   - The host reported `contextWindow` 1,000,000 and `maxOutputTokens` 128,000.
4. **Four judge calls through dispatch.** Stage S3, structured output, calibration tranche, `view_window` false,
   output cap 4,096.
   - The host finished each call.
   - `claude-run` then refused each one's evidence: `RECORD_KIND_UNKNOWN 'tools-used'`, exit 70. So the gate failed all
     four.
   - The supervisor still closed each reservation as `failed`, charged with what the capture measured (provisional 0,
     unresolved 0), and left none open.
   - This is the outcome REPIN step 3 exists to catch. The standalone call has no schema, so it did not show the kind.
5. **The new kind.** `tools-used` has the fields `type`, `tools` and `sessionId`. Its one tool name is the
   StructuredOutput tool, the same as the assistant's `tool_use` and among the tools the request offered.
   - It carries no instruction, skill, agent, hook or MCP context.
   - So it is added to `RECORD_KINDS["2.1.317"]` as known and unread, together with the `structured_output`
     attachment.
   - Every type in `READ_TYPES` appeared. The read attachments the sample did not show are `agent_listing_delta`,
     `deferred_tools_delta`, `instructions` and `skill_listing`. One empty hermetic call loads none of them, so they
     are unobserved, not gone.
6. **A fifth judge call through dispatch**, with the kind known. The lead approved this sixth call before it was made.
   - It passed the gate with no code.
   - Its usage record is complete: 3,847 measured.
   - The host reported `contextWindow` 1,000,000.

## What changed

- **`session-distill/seats.json`:**
  - `hosts.claude.version` 2.1.317 and its versioned path.
  - `stage_seats.S3` is `claude:claude-sonnet-5-5/high`, and its `$comment` says so.
  - `host_allowance.hermetic` is 3,795: the maximum observed main-request input (input + cache read + cache creation)
    over the five judge calls through dispatch (3,795, 3,784, 3,784, 3,784, 3,794).
  - `seat_capacity` holds one row, `claude:claude-sonnet-5-5/high`: 1,000,000 at 2.1.317.
  - The `/xhigh` and `/medium` rows are removed. They named the old version, and nothing reads them once S3 is
    `/high`, since only view-window calls ask for a capacity and only S3 makes them.
- **`wrappers/claude_hermetic_evidence.py`:** `RECORD_KINDS["2.1.317"]` holds the kinds the six calls showed.
- **`gates/check_parity.py`:** the pin line names 2.1.317.
- **`session-distill/runlib/dispatch.py`:** `design_4`, the self-test's copy of design §4's seats, has S3 at `/high`.
- **`DEPENDENCIES.md`** and **`docs/advanced-launch.md`:** the hermetic profile's verified version is 2.1.317. The
  isolation effect of the flag set stays the one measured on 2.1.304.

## What the measurement cost

| Call | Input tokens | Output tokens |
| --- | --- | --- |
| standalone hermetic | 1,782 | 4 |
| dispatch judge 1 (refused) | 3,795 | 53 |
| dispatch minimal 2-4 (refused) | 3,784 each | 237, 105, 189 |
| dispatch judge 5 | 3,794 | 53 |
| **six calls** | **20,723** | **641** |

These are host-reported per call. Input counts cache reads and cache creation.

## Evidence

The evidence is kept author-side, mode 700, under the workbench's `distill-redesign/work/impl/wp08/c6/`:
- `step3/`: the standalone call's capture.
- `run/`: the dispatch run directory, with each call's capture, usage record and the supervisor ledger.
- `run-call-*.out`: the measurement script's counts, never content.

Captures were read for record kinds and counts only.

The hook and a real umbrella in a clean clone of this commit follow it. The clean clone is where the pin first names
a file that exists on this machine.
