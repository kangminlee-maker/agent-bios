---
created_at: 2026-10-01T11:06:17+09:00
head: 3c2ee2b
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20261001-0fd591
---

# V1 acceptance: the branch the checkout is on, and one start on each host after the seventh review's repair (record)

This is a dated direct-use record for V1's done-when [0]. It records a short real use run by the
agent on 2026-10-01 between 10:58 and 11:06 KST, on this machine, through the code at `3c2ee2b`.
That code is the repair described in the
[10:58 record](2026-10-01T1058--b7e35f7--v1-review7-repair-record.md), and it is the last commit
that changes `workenv/`.

The setup is that of the
[21:43 record](2026-09-30T2143--8bda008--v1-acceptance-after-review6-direct-use-record.md), with
one change: Claude Code had updated itself to 2.1.286. Codex CLI is 0.159.2 (`gpt-6.1-sol`).
Evidence is in the workbench's `v1-accept/use/`, files `132` … `141`, with `check_last.py`.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## What was run and what was seen

1. **The branch, on the drift clone** (`132`, `133`).
   - The clone `v1-accept/use/drift/checkout` was bound on `main`. A branch
     `v1-branch-check` was made there and checked out; the main checkout was not touched.
   - `start claude-code` first asked whether Claude Code 2.1.286 qualifies, since no probe had
     qualified that version. The first opening was left with Ctrl-C during that probe. The
     second ran it to its end and opened the entry, which offered the Claude Code start.
   - The entry's first line read `agent-bios-personal · 로컬 레포 · v1-branch-check`: the branch
     the checkout is on as the entry opens, not the one it was bound on.
   - The entry was left with Ctrl-C (exit 130), and the clone was put back on `main`.
2. **Claude Code, in the main checkout** (`134` … `137`), on the state base
   `v1-accept/use/base`.
   - The probe of 2.1.286 ran first and `worked`.
   - The entry showed both Instructions, the person's naming the unresolved `src_832de866`.
   - The session gave `fc4775b5…` (`AGENTS.md`), then `74d227ef…` (`korean-writing.md`),
     and named `src_832de866…` as not usable. `/exit` ended it, and `start` exited 0.
   - The host session `fc1cf7db14a3` was activated at 02:03:07Z with two units and the gap. The
     digest and render checks hold, and the text holds no `unt_`. `received` lists the two
     units, repository then personal.
3. **Codex, in the main checkout** (`138` … `141`).
   - The entry showed the Claude start's note as the previous note.
   - The session, on `GPT-6.1-Sol low`, gave the same two digests in the same order and named
     the same source. `/exit` ended it, and `start` exited 0.
   - The host session `ab1171fd001d` was activated at 02:05:04Z with two units and the gap. The
     digest and render checks hold, and the text holds no `unt_`. `received` lists the two
     units.

## What this shows against V1's done-when

At `3c2ee2b`:

- **[0]:** on each host, a session in this repository with repository then personal Instructions,
  and a record of what it received.
- **[6]:** a `new` delivery whose recorded preparation renders the text the session holds, on
  each host, with Claude Code at a version a probe qualified on the way.
- **[9]:** the entry names the branch the checkout is on.

## What this run did not exercise

- **A required winning unit with no body.** Neither base selects a unit with `startup:
  required`. That case is shown by the `test_roles`, `test_start` and `test_tui` tests the
  repair added.
- **A shadowed document, and two identical requests overlapping.** Shown by the `test_roles` and
  `test_journal` tests the repair added.
