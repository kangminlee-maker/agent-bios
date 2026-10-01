---
created_at: 2026-10-02T07:34:11+09:00
head: bc51953
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20261002-fceb6a
---

# V1 acceptance: one new session on each host after review 11's repair, and Claude Code's new version probed (record)

This is a dated direct-use record for V1's done-when [0] and [6]. It records real use run by the
agent on 2026-10-02 between 07:30 and 07:34 KST, on this machine, through the code at `bc51953`.
That commit is the repair in the
[07:26 repair record](2026-10-02T0726--b9a3a45--v1-review11-repair-record.md): an activation
reads each body it returns as composition read it. Activation serves both hosts, so each host
started one new session.

The setup is that of the
[00:35 record](2026-10-02T0035--ae6e541--v1-acceptance-after-review10-direct-use-record.md):
Codex CLI 0.159.2 (`gpt-6.1-sol`), tmux, the main checkout and the state base
`v1-accept/use/base`, where `AGENTS.md` still read `d16c076c…`, the body admitted. Claude Code
had moved from 2.1.286 to 2.1.287. Evidence is in the workbench's `v1-accept/use/`, files `184`
… `195`, with the scripts `probe.py` and `check_last.py`.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## What was run and what was seen

1. **Claude Code 2.1.287, in the main checkout** (`184` … `188`).
   - **The entry.** It showed the Codex start of 00:33 as the previous note, and both
     Instructions.
   - **Its new version qualified.** No probe qualified 2.1.287, so the start probed it: a `new`
     probe of 2.1.287 `worked` at 22:30:41Z, fourteen seconds before the activation (`188`).
   - **The new session.** It gave `AGENTS.md` `d16c076c…`, then `korean-writing.md` `231ac7c5…`,
     and named `src_832de866…` as not usable.
   - **The owner's record.** The activation and the `new` delivery were recorded at 22:30:55Z.
     The digest and render checks hold, and the text holds no `unt_` (`186`).
   - `/exit` ended the session, and `start` exited 0 (`187`).
2. **Claude Code 2.1.287's other routes, probed** (`189`, `190`, each headed by the commit it
   ran). `current` and `rehydrated` each `worked`.
3. **Codex, in the main checkout** (`191` … `194`).
   - **The entry.** It showed the Claude start's note as the previous note.
   - **The new session.** On `GPT-6.1-Sol low`, it gave the same two bodies in the same order,
     and named the same unusable source.
   - **The owner's record.** The activation and the `new` delivery were recorded at 22:33:16Z,
     and the checks hold (`193`).
   - `/exit` ended it, and `start` exited 0 (`194`).
4. **The deliveries recorded** (`195`): an `activated` and a `delivered` row for each start, and
   nothing else since the 00:33 start.

## What this shows against V1's done-when

At `bc51953`:

- **[0]:** on each host, a session in this repository with repository then personal
  Instructions, and a record of what it received.
- **[6]:** a `new` delivery on each host, activated by code that refuses a body not held as its
  unit names, and so committed only on the bodies the preparation names. Claude Code's new version was qualified by a probe before anything started on it, and
  each of its routes worked.

## What this run did not exercise

- **A body changed after composition.** Nothing in the base was changed between composing and
  activating. `test_roles` holds that case.
- **A compaction or a change during these sessions.** The hook and the delivery records did not
  change. The 23:25 record holds a `rehydrated` delivery and a `current` notice on each host.
