---
created_at: 2026-09-30T18:19:39+09:00
head: fac8542
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20260930-bea6c5
---

# V1 acceptance: a refused start left out in the same entry, and one start on each host (record)

This is a dated direct-use record for V1's done-when [0]. It records the real use run by the agent
on 2026-09-30 between 18:12 and 18:19 KST, on this machine, through the code at `fac8542`. That
code is the repair described in the
[18:08 record](2026-09-30T1808--6e73c2d--v1-refused-start-repair-record.md), and it is the last
commit that changes `workenv/`.

The setup is that of the
[16:42 record](2026-09-30T1642--3e78f11--v1-acceptance-after-review3-direct-use-record.md):
Claude Code 2.1.285, Codex CLI 0.159.2 (`gpt-6.1-sol`), and tmux. Evidence is in the workbench's
`v1-accept/use/`, files `81` … `95`, with `check_last.py`.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## A changed repository document, left out in the same entry

This ran on `v1-accept/use/drift/`:

- `checkout` is a clone of the main checkout at `226576d`, whose `AGENTS.md` had one line
  appended after it was admitted;
- `base` is its own state, where only Claude Code is qualified.

1. **The entry** (`81`) read `› [x] (제안) 레포 지침 · 등록 뒤 바뀜 AGENTS.md`.
2. **Enter on the start** (`82`) launched nothing. It drew `시작하지 못함 · 레포 문서가 등록 뒤
   바뀜 · Space로 빼거나 다시 등록`.
3. **Up, Up, Space** (`83`) left the repository's Instructions out: `› [ ] 레포 지침 · 등록 뒤
   바뀜 AGENTS.md`. The refusal stayed drawn.
4. **Tab to the start, and Enter** (`84`). Claude Code asked whether to trust the clone's folder,
   which it had not seen. It was trusted, and the session started.
5. **The session** (`85`), asked with no tool for every Instructions body its environment
   handed it, gave one: `korean-writing.md`, `74d227ef…`.
   - It said the repository's `AGENTS.md` was not among them.
   - It said it read that file only through the root `CLAUDE.md`'s own import, which is Claude
     Code's, not the environment's.
   - `/exit` ended it, and `start` exited 0.
6. **What reached it** (`86`, `87`).
   - The host session `9cf88427ba65` was activated at 09:14:09Z with one unit, from the personal
     source, and no gap.
   - The job's environment digest matches the handed text.
   - The recorded preparation renders the handed text byte for byte, and the text holds no `unt_`.

## One start on each host

This ran in the main checkout, on the state base `v1-accept/use/base`. The base still holds the
person's Instructions collection with one source that does not resolve.

`sources` (`88`) listed the repository's Instructions `installed` at revision `90fda21c`. The
main checkout's `AGENTS.md` still reads `d0c90c49…`, as it did when `readmit.py` admitted it.

1. **The Claude Code entry** (`89`) showed both Instructions, the person's naming the unresolved
   `src_832de866`. A note was typed, and Tab moved through the tool and the permissions to the
   start.
2. **The session** (`90`) gave `d0c90c49…` (`AGENTS.md`), then `74d227ef…`
   (`korean-writing.md`). It named `src_832de866…` at revision `666666666666` as
   `selection_unresolved`. `/exit` ended it, and `start` exited 0.
3. **What reached it** (`91`). The host session `4ca8ff69c3b9` was activated at 09:15:53Z with
   two units and the gap. The digest and render checks hold, and the text holds no `unt_`.
4. **The Codex entry** (`92`) showed the Claude start's note as the previous note, and the same
   positions with the tool `Codex CLI`.
5. **The session** (`93`), on `GPT-6.1-Sol low`, gave the same two digests in the same order,
   and named the unresolved source. `/exit` ended it, and `start` exited 0.
6. **What reached it** (`95`). The host session `4b5daa2f964f` was activated at 09:17:59Z with
   two units and the gap. The digest and render checks hold, and the text holds no `unt_`.

## What this shows against V1's done-when

At `fac8542`:

- **[0]:** on each host, a session in this repository with repository then personal Instructions,
  and a record of what it received.
- **[6]:** a `new` delivery whose recorded preparation renders the text the session holds, in all
  three starts.
- **[10]:** a changed repository document is shown before the start. The refusal names a next
  step, and that step works in the same entry. An unresolved selection is visible on the entry and
  to the session.

## Seen, and not a finding

- **Codex's startup warning** (`94`), "Running without the shared background server:
  command-line configuration overrides … requires embedded mode". The launch passes `-c`
  overrides, and Codex runs embedded when it does. The
  [12:52 record](2026-09-30T1252--6676966--v1-acceptance-both-hosts-direct-use-record.md) saw it
  first.
- **Claude Code's folder trust.** It is the host's own question for a folder it has not seen. It
  was asked once, for the clone.
- **`AGENTS.md` in the drift session.** Claude Code reads it through the checkout's `CLAUDE.md`,
  whatever the environment holds. The environment's own delivery left it out, as selected.
