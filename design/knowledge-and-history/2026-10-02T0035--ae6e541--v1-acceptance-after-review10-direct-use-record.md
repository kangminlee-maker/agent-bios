---
created_at: 2026-10-02T00:35:01+09:00
head: ae6e541
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20261001-97ff18
---

# V1 acceptance: Codex's routes probed again, and one Codex session started, after review 10's repair (record)

This is a dated direct-use record for V1's done-when [0] and [6]. It records real use run by the
agent on 2026-10-02 between 00:32 and 00:35 KST, on this machine, through the code at `ae6e541`.
That commit is the repair in the
[00:26 repair record](2026-10-02T0026--8ef2bad--v1-review10-repair-record.md): Codex's probe
reads only its own conversation and turn.

The setup is that of the
[23:25 record](2026-10-01T2325--e8b281b--v1-acceptance-after-restructure-direct-use-record.md):
Codex CLI 0.159.2 (`gpt-6.1-sol`), tmux, the main checkout and the state base
`v1-accept/use/base`. `AGENTS.md` still read `d16c076c…`, the body admitted then. Evidence is in
the workbench's `v1-accept/use/`, files `176` … `183`, with the scripts `probe.py` and
`check_last.py`.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## What was run and what was seen

1. **Codex's three routes, probed again** (`176` … `178`, each headed by the commit it ran).
   `rehydrated`, `new` and `current` each `worked`. The `rehydrated` probe now counts a
   compaction only where Codex reported it in the turn it completed for this conversation.
2. **One Codex session, in the main checkout** (`179` … `183`).
   - **The entry.** It showed the Codex start of 23:23 as the previous note, and both
     Instructions. No probe was made at it: the latest `new` probe after the start is still
     `177`, which qualified the host.
   - **The offer.** The route offer made at this entry cites `177` (`e45f96a5…`) for Codex
     (`182`). No other start came after `177`.
   - **The new session.** On `GPT-6.1-Sol low`, it gave `AGENTS.md` `d16c076c…`, then
     `korean-writing.md` `231ac7c5…`, the personal body `midsession.py` committed during the
     23:23 Codex session, and named `src_832de866…` as not usable.
   - **The owner's record.** The activation and the `new` delivery were recorded at 15:33:37Z.
     The digest and render checks hold, and the text holds no `unt_` (`181`).
   - `/exit` ended the session, and `start` exited 0 (`183`).

## What this shows against V1's done-when

At `ae6e541`:

- **[0]:** a Codex session in this repository with repository then personal Instructions, and a
  record of what it received.
- **[6]:** each of Codex's routes probed by code that counts only what Codex confirmed for the
  probe's own conversation and turn, and a `new` delivery started on the probe that qualified
  it.

## What this run did not exercise

- **Claude Code.** The repair changed only `workenv/hosts/codex.py`. Claude Code's routes and
  session stand as the 23:25 record shows them.
- **A compaction or a change during this session.** The hook and the delivery records did not
  change. The 23:25 record holds a `rehydrated` delivery and a `current` notice on Codex.
- **Another conversation on the probe's server.** The probes met none that this record can show.
  `test_probes` holds that case.
