---
created_at: 2026-10-01T16:39:44+09:00
head: 19c383e
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20261001-fa937f
---

# V1 acceptance: one start on each host after the eighth review's repair (record)

This is a dated direct-use record for V1's done-when [0]. It records a short real use run by the
agent on 2026-10-01 between 16:35 and 16:39 KST, on this machine, through the code at `19c383e`.
That code is the repair described in the
[16:31 record](2026-10-01T1631--7de34b9--v1-review8-repair-record.md), and it is the last commit
that changes `workenv/`.

The setup is that of the
[11:06 record](2026-10-01T1106--3c2ee2b--v1-acceptance-after-review7-direct-use-record.md):
Claude Code 2.1.286, Codex CLI 0.159.2 (`gpt-6.1-sol`), tmux, the main checkout and the state
base `v1-accept/use/base`. The checkout's `AGENTS.md` still read `fc4775b5…`, the body
admitted, so nothing was admitted again. Evidence is in the workbench's `v1-accept/use/`, files
`142` … `149`, with `check_last.py`.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## What was run and what was seen

1. **Claude Code, in the main checkout** (`142` … `145`).
   - The entry read `agent-bios · 로컬 레포 · main`, showed the Codex start of 11:06 as the
     previous note, and both Instructions, the person's naming the unresolved `src_832de866`.
   - The session gave `fc4775b5…` (`AGENTS.md`), then `74d227ef…` (`korean-writing.md`),
     and named `src_832de866…` as not usable. `/exit` ended it, and `start` exited 0.
   - The host session `6de60a3e6461` was activated at 07:36:43Z with two units and the gap. The
     digest and render checks hold, and the text holds no `unt_`. `received` lists the two
     units, repository then personal.
2. **Codex, in the main checkout** (`146` … `149`).
   - The entry showed the Claude start's note as the previous note.
   - The session, on `GPT-6.1-Sol low`, gave the same two digests in the same order and named
     the same source. `/exit` ended it, and `start` exited 0.
   - The host session `5209b6a5acad` was activated at 07:38:33Z with two units and the gap. The
     digest and render checks hold, and the text holds no `unt_`. `received` lists the two
     units.

## What this shows against V1's done-when

At `19c383e`:

- **[0]:** on each host, a session in this repository with repository then personal Instructions,
  and a record of what it received.
- **[6]:** a `new` delivery whose recorded preparation renders the text the session holds, on
  each host.

## What this run did not exercise

- **A switched-off unit a required winner needs.** Neither base selects a unit with `startup:
  required` or one that needs another. That case is shown by the `test_roles` tests the repair
  added.
- **A start still pending after more starts than the history lists.** Every start here settled.
  That case is shown by the `test_routes` and `test_tui` tests the repair added.
