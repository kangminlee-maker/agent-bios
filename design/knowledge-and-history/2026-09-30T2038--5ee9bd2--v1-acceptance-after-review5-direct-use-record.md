---
created_at: 2026-09-30T20:38:57+09:00
head: 5ee9bd2
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20260930-154b14
---

# V1 acceptance: one start on each host after the fifth review's repair (record)

This is a dated direct-use record for V1's done-when [0]. It records a short real use run by the
agent on 2026-09-30 between 20:34 and 20:39 KST, on this machine, through the code at `5ee9bd2`.
That code is the repair described in the
[20:31 record](2026-09-30T2031--8897a53--v1-review5-repair-record.md), and it is the last commit
that changes `workenv/`.

It repeats, on that code, the starts of the
[19:37 record](2026-09-30T1937--14b09a7--v1-acceptance-after-review4-direct-use-record.md). The
setup is the same: Claude Code 2.1.285, Codex CLI 0.159.2 (`gpt-6.1-sol`), tmux, the main
checkout and the state base `v1-accept/use/base`. Evidence is in the workbench's
`v1-accept/use/`, files `110` … `118`, with `check_last.py`.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## What was run and what was seen

1. **`sources`** (`110`).
   - The repository's Instructions are `installed`: `AGENTS.md` at revision `90fda21c`. The
     main checkout's `AGENTS.md` still reads `d0c90c49…`, the body admitted.
   - The person's collection is `some of what is selected is not usable here`. It lists
     `korean-writing.md` and the unresolved `src_832de866…`.
2. **Claude Code** (`111` … `114`).
   - The entry showed `[x] (제안) 레포 지침 · AGENTS.md` and `[x] 개인 지침 · korean-writing.md
     · 쓸 수 없는 원본 src_832de866`.
   - The session gave `d0c90c49…` (`AGENTS.md`), then `74d227ef…` (`korean-writing.md`),
     and named `src_832de866…` as not usable. `/exit` ended it, and `start` exited 0.
   - The host session `5464f46b8bb7` was activated at 11:36:03Z with two units and the gap. The
     digest and render checks hold, and the text holds no `unt_`.
   - `received` lists the two units, repository then personal.
3. **Codex** (`115` … `118`).
   - The entry showed the Claude start's note as the previous note.
   - The session, on `GPT-6.1-Sol low`, gave the same two digests in the same order and named
     the same source. `/exit` ended it, and `start` exited 0.
   - The host session `91b3977998aa` was activated at 11:37:49Z with two units and the gap. The
     digest and render checks hold, and the text holds no `unt_`.
   - `received` lists the two units, repository then personal.

## What this shows against V1's done-when

At `5ee9bd2`, on each host:

- **[0]:** a session in this repository with repository then personal Instructions, and a record
  of what it received.
- **[6]:** a `new` delivery whose recorded preparation renders the text the session holds.
  `received` lists exactly the units it was handed.
- **[7], [8], [10]:** the entry and `sources` name the members selected, and the unresolved
  selection is visible on the entry and to the session.

## What this run did not exercise

- **A collection that selects some of a revision's members.** The person's collection selects
  whole revisions. That case is shown by the `test_tui` and `test_commands` tests the repair
  added.
