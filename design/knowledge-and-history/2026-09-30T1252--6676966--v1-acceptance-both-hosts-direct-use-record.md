---
created_at: 2026-09-30T12:52:06+09:00
head: 6676966
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20260930-b36ceb, D-20260930-89edca, D-20260930-76d550, D-20260930-6c708c
---

# V1 acceptance: direct use of the repaired code on both hosts (record)

This is a dated direct-use record for V1's done-when [0]. It records the real use run by the agent
on 2026-09-30 between 11:59 and 12:51 KST, on this machine, through the code at `6676966`. That
code is the repair the [11:54 record](2026-09-30T1154--2a4a466--v1-use-findings-repair-record.md)
describes, of the three findings in the
[09:42 direct-use record](2026-09-30T0942--6265ff4--v1-acceptance-direct-use-record.md).

The owner chose that Codex is used again after they change their Codex setup
(`D-20260930-89edca`). They upgraded the Homebrew Codex CLI from 0.158.0 to 0.159.2 at 12:44 (the
reason is under "Why Codex refused the person's model"), and kept `model = "gpt-6.1-sol"`.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## Where and with what

- **Hosts:** Claude Code 2.1.285, and Codex CLI 0.159.2 (`/opt/homebrew/bin/codex`), with the
  person's own settings and accounts.
- **The repository:** the main checkout `~/Documents/agent-bios-personal`. Nothing was written
  there.
- **The state:** the same base as the 09:42 record, `…/team-env-20260920/v1-accept/use/base`. It
  still holds the person's Instructions collection with one source that does not resolve
  (`src_832d…7574` at revision `666…6`).
- **The program:** `workenv/commands.py` from the worktree at `6676966`, run by
  `/opt/homebrew/opt/python@3.14/bin/python3.14`.
- **The terminal:** each `start` ran inside tmux (a private socket, 120×40, `LANG=ko_KR.UTF-8`),
  driven by keys sent to it and read back from the rendered screen.
- **Evidence:** the workbench's `v1-accept/use/`, files `16` and `17` and `20` … `38`, and
  `tab-trace/`.

## What was run and what was seen

1. **The sources** (`21`).
   - The person's Instructions position reads `some selected sources do not resolve`.
   - The missing source's line reads `src_832d… revision 666666666666: does not resolve here
     (selection_unresolved)`.
2. **Preparing on Codex 0.158.0, before the upgrade** (`22`): `no_response`, now ending
   "Codex ended the turn with an error: The 'gpt-6.1-sol' model is not supported when using Codex
   with a ChatGPT account."
3. **The entry for Claude Code** (`23`, `24`).
   - The person's Instructions line reads `[x] 개인 지침 · korean-writing.md · 쓸 수 없는 원본
     src_832de866`.
   - Its detail reads `… · 원본 · 일부 원본을 쓸 수 없음`.
4. **A Claude Code session from the entry** (`25`).
   - Asked, with no tool, whether its environment says anything is missing, it quoted the
     section. The section's line now names `selected source src_832de86643aae111fd1c3d62cc657574
     at revision 666666666666`.
   - It named the two bodies it received.
   - It stated that `korean-writing.md` has another source id and does not stand in for the
     missing one.
   - `/exit` ended it, and `start` exited 0.
5. **What reached it** (`26`, `27`).
   - The host session `428658a73d65` was activated at 03:00:43Z with the two units.
   - The activation's projection carries `selection_unresolved` at `/collections/0`.
   - The job's environment digest is the sha256 of the handed text.
   - The delivery's recorded preparation renders the handed text byte for byte.
   - No `unt_` is in the text.
   - The text names the missing source and its revision.
6. **Preparing on Codex 0.159.2** (`30`, `31`).
   - The probe reported `worked`.
   - The preparation composed `repository, personal` with two units and
     `gap selection_unresolved at /collections/0`.
7. **The entry for Codex** (`32`, `33`).
   - It is the same as step 3, with the tool `Codex CLI`.
   - Tab from the note went to the tool row, then to the permissions. See "Seen, and not a
     finding".
8. **A Codex session from the entry** (`34`, `35`, `35b`).
   - Codex 0.159.2 started on `GPT-6.1-Sol low`. It showed two warnings:
     - the embedded-mode notice for `-c` overrides, also seen on 2026-09-29;
     - the person's weekly usage.
   - At the first prompt, asked with no tool, it listed its environment's headings. They run from
     `# agent-bios work environment` through `## Repository instructions: AGENTS.md` and
     `## Personal instructions: korean-writing.md` (with their bodies' headings) to
     `## Missing from this environment`.
   - It quoted the missing section with the source and revision, and stated no `unt_` id appears.
   - The whole answer is in `35b`, read from Codex's own rollout file for the session.
   - `/exit` ended it, and `start` exited 0.
9. **What reached it** (`36`, `37`).
   - The host session `aefe4adaa7ac` was activated at 03:47:55Z with two units and the same gap.
   - The job's environment digest is the sha256 of the handed text.
   - The recorded preparation renders the handed text byte for byte.
   - No `unt_` is in the text.
   - The link's host is `codex 0.159.2`, and its destination names the session id Codex printed on
     exit (`01a0f06c-…`).

## Why Codex refused the person's model

The account was not the reason (`17`). Asked by the same account:

- Codex 0.158.0 lists `gpt-6-astra` as default and no `gpt-6.1-sol`, and a turn on `gpt-6.1-sol`
  fails with the 400 above.
- Codex 0.159.0 (inside the ChatGPT app) lists `gpt-6.1-sol` as default, and the same turn
  succeeds.

The two share `~/.codex/config.toml`, which named `gpt-6.1-sol` from 06:19. Which program wrote it
is not recorded. Codex's own model cache (`~/.codex/models_cache.json`, fetched by client 0.159.0)
ranks `gpt-6.1-sol` first. The offered models depend on the Codex version. The refusal's words name
the account.

The raw wire of the refused turn is `16-codex-app-server-turn.jsonl`. It is the fixture the Codex
repair was built from.

## What this shows against V1's done-when

**Shown here, on this machine, at `6676966`:**

- **[0]:** a Claude Code session and a Codex session in this repository, each with the profile made
  at first use, repository then personal Instructions in that order, and a record of what it
  received.
- **[6]:** a `new` delivery on each host whose recorded preparation renders exactly the text the
  session holds.
- **[10]:** a selected source that does not resolve still starts, and it is visible where the
  person chooses (the entry, its detail, `sources`) and to the session (its missing section, with
  the source). The activation carries the gap.
- **The Codex probe** states Codex's own reason when a turn fails.

## Seen, and not a finding

- **Tab after the note, on the Codex entry** (step 7). Two Tabs from the note stopped on the
  permissions, not the start, and it was first read as a lost Tab. It was traced (`38`,
  `tab-trace/`) in five replays of the same keys on a copy of the state:
  - every Tab reached the entry and moved the focus: note → tool → permissions;
  - with Claude Code and Codex both qualified, the tool row has alternatives, so it is a Tab stop
    (the entry grammar: "the tool (when it has alternatives)"), and the screen marks it.
  The 09:42 record's first observation, on the Claude Code entry before Codex was qualified, is not
  explained by this and was not seen again. Its cause is not established.
- **The Codex session listed "the line under each heading" as blank.** The line under each heading
  is a blank line, then the source line.
