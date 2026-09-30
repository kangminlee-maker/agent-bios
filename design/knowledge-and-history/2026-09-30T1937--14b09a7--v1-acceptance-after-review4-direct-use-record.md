---
created_at: 2026-09-30T19:37:54+09:00
head: 14b09a7
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20260930-cc95f9
---

# V1 acceptance: the fourth review's repair in use, on the drift clone and on each host (record)

This is a dated direct-use record for V1's done-when [0]. It records a short real use run by the
agent on 2026-09-30 between 19:31 and 19:37 KST, on this machine, through the code at `14b09a7`.
That code is the repair described in the
[19:28 record](2026-09-30T1928--f6fa9ee--v1-review4-repair-record.md), and it is the last commit
that changes `workenv/`.

It repeats, on that code, what the
[18:19 record](2026-09-30T1819--fac8542--v1-acceptance-after-refused-start-repair-direct-use-record.md)
showed. The setup is the same. Evidence is in the workbench's `v1-accept/use/`, files `96` …
`109`, with `check_last.py`.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## The drift clone

The clone's `AGENTS.md` still differs from the body admitted. No collection applies the
repository's Instructions there, so the position toggles.

1. **The entry** (`96`) read `› [x] (제안) 레포 지침 · 등록 뒤 바뀜 AGENTS.md`.
2. **Enter on the start** was refused. The screen of that refusal was not kept, so the entry was
   opened once more, refused the same way, and left with Ctrl-C (exit 130) (`97`). Its result
   read `시작하지 못함 · 레포 문서가 등록 뒤 바뀜 · Space로 빼거나 다시 등록`: Space is named,
   since the changed position toggles.
3. **Up, Up, Space, then Tab to the start** (`98`) left it out: `[ ] 레포 지침 · 등록 뒤 바뀜
   AGENTS.md`. Enter started Claude Code.
4. **The session** (`99`) gave one Instructions body, `korean-writing.md`, `74d227ef…`. It
   listed `memory-use.md` by path and digest and said no body came with it. `/exit` ended it,
   and `start` exited 0.
5. **What reached it** (`100`, `101`).
   - The digest and render checks hold, and the text holds no `unt_`.
   - `received` lists one unit, from the personal source, body `74d227ef9051`.

## One start on each host

In the main checkout, on the state base `v1-accept/use/base`. The main checkout's `AGENTS.md`
still reads `d0c90c49…`, the body admitted.

1. **Claude Code** (`102` … `105`).
   - The entry showed both Instructions, the person's naming the unresolved `src_832de866`.
   - The session gave `d0c90c49…` (`AGENTS.md`), then `74d227ef…` (`korean-writing.md`),
     and named `src_832de866…` as not usable. `/exit` ended it, and `start` exited 0.
   - The host session `a58df85a8207` was activated at 10:34:53Z with two units and the gap.
     The digest and render checks hold, and the text holds no `unt_`.
   - `received` lists the two units, repository then personal.
2. **Codex** (`106` … `109`).
   - The entry showed the Claude start's note as the previous note.
   - The session, on `GPT-6.1-Sol low`, gave the same two digests in the same order and named
     the same source. `/exit` ended it, and `start` exited 0.
   - The host session `6151f61bb695` was activated at 10:36:37Z with two units and the gap.
     The digest and render checks hold, and the text holds no `unt_`.
   - `received` lists the two units, repository then personal.

## What this shows against V1's done-when

At `14b09a7`:

- **[0]:** on each host, a session in this repository with repository then personal Instructions,
  and a record of what it received.
- **[6]:** in all three starts, a `new` delivery whose recorded preparation renders the text the
  session holds. `received` lists exactly the units the session was handed.
- **[10]:** the changed document is shown before the start. The refusal names Space where the
  position can be left out, and leaving it out in the same entry starts.

## What this run did not exercise

- **A collection's position with a changed document.** The drift clone's repository Instructions
  are not in a collection. That case is shown by the `test_tui` test the repair added.
- **Two units with the same bytes.** Neither base holds such a pair. That case is shown by the
  `test_delivery` and `test_roles` tests the repair added.
