---
created_at: 2026-09-30T16:42:27+09:00
head: 3e78f11
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20260930-38bbad
---

# V1 acceptance: the third review's repair in use, and a start refused because the repository's AGENTS.md changed (record)

This is a dated direct-use record for V1's done-when [0]. It records the real use run by the agent
on 2026-09-30 between 16:33 and 16:42 KST, on this machine, through the code at `3e78f11`. That
code is the repair described in the [16:30 record](2026-09-30T1630--22ff98a--v1-review3-repair-record.md),
and it is the last commit that changes `workenv/`.

The setup is that of the [12:52 record](2026-09-30T1252--6676966--v1-acceptance-both-hosts-direct-use-record.md):

- Claude Code 2.1.285 and Codex CLI 0.159.2 (`gpt-6.1-sol`);
- the main checkout;
- the state base `v1-accept/use/base`;
- tmux.

The base still holds the person's Instructions collection with one source that does not resolve.
Evidence is in the workbench's `v1-accept/use/`, files `50` … `70`, with `readmit.py`,
`run-start-bodiless.sh` and `check_last.py`.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## What was run and what was seen

1. **The effects on the entry** (`51`). The entry now draws each effect on its line:
   - `(제안) 도구 Claude Code · 새 세션 · 모델 호출`
   - `(제안) 권한 · 호스트 설정대로 확인 · 권한 요청`
   - `Claude Code 새 세션 시작 · 파일 변경 · 모델 호출`
2. **A start refused** (`52`).
   - Enter on the start did not launch the host. The entry's result line read
     `시작하지 못함 · activating the environment was refused with working_bytes_moved`. The entry
     was then closed with its tmux session, so no exit status was read.
   - The cause is the main checkout's `AGENTS.md`. Another session edits the shared checkout, and
     it had changed the file at 16:26, uncommitted. The main checkout's HEAD had also moved to
     `45c54a0` since the morning.
   - The repository's Instructions source is authored in the repository. Its admitted revision
     names body `242afd12…`, and the checkout's document now reads `d0c90c49…`. Activation refuses
     where "a repository-authored unit's document in the bound checkout is no longer the body the
     preparation names" (`roles.moved`). The refusal is correct. See the finding below.
3. **Admitting the document again** (`readmit.py`, `55`, `56`).
   - `source.revision.admit` ran on the source's head `00c98839…` with the checkout's `AGENTS.md`,
     through the journal, as `prep.py` admits. It was `committed`, with new head `90fda21c…`.
   - `sources` then listed the repository's Instructions at that revision.
   - No command admits a source yet. That is the workbench's, as for `prep.py`
     (`D-20260929-34e9ab`).
4. **A Claude Code session from the entry** (`57`, `58`).
   - Asked with no tool for every body sha256 in order, it gave `d0c90c49…` (`AGENTS.md`), then
     `74d227ef…` (`korean-writing.md`).
   - It named the unresolved `src_832de866…` at revision `666666666666`.
   - `/exit` ended it, and `start` exited 0.
5. **What reached it** (`59`, `60`).
   - The host session `00807cb58521` was activated at 07:38:04Z with two units and the gap.
   - The job's environment digest matches the handed text.
   - The recorded preparation renders the handed text byte for byte, and the text holds no `unt_`.
6. **A Codex session from the entry** (`61`, `62`).
   - The entry drew the same effects with the tool `Codex CLI`.
   - The session gave the same two digests in order, and named the unresolved source.
   - `/exit` ended it, and `start` exited 0.
7. **What reached it** (`63`, `64`).
   - The host session `8cd3a2350e23` was activated at 07:39:33Z with two units and the gap.
   - The digest and render checks hold, and the text holds no `unt_`.
8. **A body not held** (`65` … `70`), on `base-bodiless`, a copy of the base.
   - **The setup.** The bundle bytes of `korean-writing.md` (personal source `src_108d…`, revision
     `7561de27…`) were removed.
   - **`sources`** reads `personal instructions (collection …): nothing selected is usable here`.
     The source's line ends `; body not held here: korean-writing.md`.
   - **The entry** reads `[x] 개인 지침 · 쓸 수 없는 원본 src_832de866 · 본문 없음 korean-writing.md`.
   - **A Claude Code session started** from it, and quoted its missing section. The section names
     the unresolved source, then "The personal instructions member korean-writing.md, source
     src_108d… at revision 7561de27ed4d: its body is not held here, so this environment does not
     hold it."
     - It said it received one Instructions body, `AGENTS.md`.
     - It said it does not know the rules in `korean-writing.md`.
     - It said its Korean replies come from the person's own `~/.claude/CLAUDE.md`, which does not
       stand in for the missing member.
   - **What reached it.** The activation's projection holds two units: `korean-writing.md`'s
     names no body. It carries the unresolved gap, and the render checks hold.
   - **`received`** lists the one unit that reached the session.

## What this shows against V1's done-when

At `3e78f11`, on each host:

- **[0]:** a session in this repository with repository then personal Instructions, and a record
  of what it received.
- **[6]:** a `new` delivery whose recorded preparation renders the text the session holds.
- **[8] and [10]:** the effects are drawn where they apply. An unresolved selection is visible on
  the entry and to the session, and so is a member whose body is not held. Neither stops the
  start.

## What was found

This finding is not dispositioned by this record.

**A start whose repository document changed after it was admitted is refused, and the person is
given an internal code and no next step.**

- **Seen.** Step 2. The entry, before the start, showed `(제안) 레포 지침 · AGENTS.md` like any
  other time. After Enter it showed `activating the environment was refused with
  working_bytes_moved`:
  - an English contract code, inside Korean copy;
  - no statement of what moved;
  - no statement of what would let the next start run.
- **Why.** `roles.moved` compares each repository-authored unit's body with the checkout's
  document. The entry's result shows the owner's reason as it is. Nothing before the start compares
  the two.
- **Recovery.** Admitting the document again, which V1 has no command for.
- **How often.** Whenever a selected repository document is edited after it is admitted. In this
  repository that is the file other sessions edit.
- **Against.** Done-when [10], "same-request recovery stay visible", and the SSOT's plain-product
  copy.

## Seen, and not a finding

- `received` lists the units whose bodies reached the session. The body-less member stays in the
  activation's projection with no body, and the session's missing section names it.
