---
created_at: 2026-09-30T21:43:02+09:00
head: 8bda008
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20260930-c92d68
---

# V1 acceptance: a changed AGENTS.md left out on one host and admitted again for the other (record)

This is a dated direct-use record for V1's done-when [0]. It records a short real use run by the
agent on 2026-09-30 between 21:38 and 21:43 KST, on this machine, through the code at `8bda008`.
That code is the repair described in the
[21:35 record](2026-09-30T2135--8c27731--v1-review6-repair-record.md), and it is the last commit
that changes `workenv/`.

The setup is that of the
[20:38 record](2026-09-30T2038--5ee9bd2--v1-acceptance-after-review5-direct-use-record.md):
Claude Code 2.1.285, Codex CLI 0.159.2 (`gpt-6.1-sol`), tmux, the main checkout and the state
base `v1-accept/use/base`. Evidence is in the workbench's `v1-accept/use/`, files `119` …
`131`, with `readmit.py` and `check_last.py`.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## What was run and what was seen

Another session had edited the main checkout's `AGENTS.md` since it was last admitted. It read
`fc4775b5…`, and the admitted body is `d0c90c49…`. That was used as it was.

1. **`sources`** (`119`) read `repository instructions: nothing selected is usable here`, its
   source's line ending `; changed in the checkout since admitted: AGENTS.md`.
2. **The Claude Code entry** (`120`) read `› [x] (제안) 레포 지침 · 등록 뒤 바뀜 AGENTS.md`.
3. **Enter on the start** (`121`) launched nothing, and drew `시작하지 못함 · 레포 문서가 등록 뒤
   바뀜 · Space로 빼거나 다시 등록`. No collection applies that position, so Space is named.
4. **Leaving it out** (`122`). Up, Up and Space made the line `[ ] 레포 지침 · 등록 뒤 바뀜
   AGENTS.md`. Tab moved through the note, the tool and the permissions to the start, and Enter
   started Claude Code.
5. **The session** (`123`) gave one Instructions body, `korean-writing.md`, `74d227ef…`, and
   named `src_832de866…` as not usable. `/exit` ended it, and `start` exited 0.
6. **What reached it** (`124`, `125`). The host session `a65773062a5f` was activated at
   12:39:55Z with one unit and the gap. The digest and render checks hold, and the text holds no
   `unt_`. `received` lists the one unit.
7. **Admitting it again** (`126`, `127`). `readmit.py` admitted the checkout's `AGENTS.md` as
   the source's new revision `58732599…`, through the journal, as the workbench's
   (`D-20260929-34e9ab`). `sources` then read `installed`.
8. **The Codex entry** (`128`) read `› [x] (제안) 레포 지침 · AGENTS.md`, and showed the Claude
   start's note as the previous note.
9. **The session** (`129`), on `GPT-6.1-Sol low`, gave `fc4775b5…` (`AGENTS.md`), then
   `74d227ef…` (`korean-writing.md`), and named the same source. `/exit` ended it, and
   `start` exited 0.
10. **What reached it** (`130`, `131`). The host session `5f2b7dfe9b31` was activated at
    12:41:48Z with two units and the gap. The digest and render checks hold, and the text holds
    no `unt_`. `received` lists the two units, repository then personal.

## What this shows against V1's done-when

At `8bda008`:

- **[0]:** on each host, a session in this repository with the Instructions selected, and a record
  of what it received.
- **[6]:** a `new` delivery whose recorded preparation renders the text the session holds, on
  each host. `received` lists exactly the units the session was handed.
- **[10]:** a document another session changed is shown before the start. Both next steps the
  refusal names were taken, one on each host, and each led to a start.

## What this run did not exercise

- **A change handed to a running session at a prompt.** No step of this run composed a newer
  preparation for a running session's link. The order the repair set (output first, then the
  record) is shown by the `test_start` tests it added, including one on a real closed pipe.
- **A switched-off repository-authored unit.** The base's repository Instructions are not in a
  collection. That case is shown by the `test_roles` test the repair added.
