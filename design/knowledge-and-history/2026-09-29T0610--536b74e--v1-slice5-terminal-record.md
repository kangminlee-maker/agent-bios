---
created_at: 2026-09-29T06:10:27+09:00
head: 536b74e
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260929-138f97, D-20260929-087624, D-20260929-e1f04c
---

# V1, fifth slice, third increment: the terminal, its commands and the launcher (record)

This records the third increment of the [14:58 design](2026-09-28T1458--dcdbebc--v1-slice5-design.md),
built to the [04:02 terminal design](2026-09-29T0402--69ebae1--v1-slice5-terminal-design.md). It
landed in three commits: `0442768` (3a), `536b74e` (3b) and the commit that carries this record
(3c). V1 is not complete, and no node is accepted by this work. No person has used the entry on
a real host yet; that is the slice's real use, still ahead.

## What landed

### 3a, `0442768`: the permissions element

- `execution.permissions` in W01, as the design states: `host_settings` suggested with its
  `permission_request` effect, or `skip_confirmations`; always a Tab stop; ← → change it until a
  start is dispatched. The keys line names ←→ as changing a setting (`key.change`).
- The English `key.arrows` label became `↑↓ items`, so the English keys line fits 78 cells.
- `Adapter.skip`: Claude Code `--dangerously-skip-permissions`, Codex
  `--dangerously-bypass-approvals-and-sandbox`.
- `start.start(..., sealed=, skip=)`: the entry's sealed composition request is submitted
  unchanged, and one that is not this actor's composition of this request is refused. The skip
  arguments come last, only where the person chose them.

### 3b, `536b74e`: the program

- **`workenv/local.py`.**
  - The state root is `workenv/state` under `AGENT_BIOS_STATE_DIR` or `~/.local/share/agent-bios`.
  - `actor.json` is minted at first use, owner-only, by an exclusive create.
  - The locale is read from `LC_ALL`, then `LC_MESSAGES`, then `LANG`.
- **`workenv/terminal.py`.**
  - Raw mode, with the alternate screen and bracketed paste.
  - Keys are read by their escape sequences, including sequences split across reads.
  - Esc alone is Esc once nothing follows it within 50 ms.
  - Sequences nothing names are dropped whole.
  - Ctrl-C and Ctrl-D leave.
  - Frames are drawn as the model measures them, with controls in caret notation.
- **`workenv/commands.py`: `start`, `profile`, `sources`, `prepare`, `received`.** `install.sh`
  dispatches them before its flag parser, with fd 3 back on stdin.
- **`workenv/hosts/start.py`.**
  - `ENTRIES` now holds every operation this installation's processes ask the owner for.
  - A query needs no entry, and any other operation is refused by name.
- **`workenv/tui.py`.**
  - An answer handed to the entry is drawn in its result element:
    - the start's result, or the unknown start a check was for;
    - `unknown` stays unknown;
    - a refusal is `unavailable`, labelled `시작하지 못함 · <reason>` or `확인하지 못함 · <reason>`.
  - Space in a focused field is a space.
- **Entrances and payload.**
  - Ten entrance dispositions: the five `install.sh` commands at `setup`, and `commands.py` per
    verb (`start` at `host_launcher`), all routed through `projection_owner` with
    `root_origin: caller`.
  - Three payload files, so the ontology counts 127, and 23 install commands.

### 3c: the launcher

- **When the launcher opens the entry.**
  - A bare `agent-launch HOST` on a terminal execs `workenv/commands.py start <adapter>
    --entrance host_launcher --locale <launcher language>` under the launcher's own interpreter.
  - `--presets`, `--preset`, `--custom`, `--understand`, `--dry-run`, `--resume-session` and
    the instructions options keep the preset menu.
  - `--no-tui`, forwarded arguments and `AGENT_LAUNCH_TUI=0` keep the direct launch.
- **When the entry cannot start.** If the launcher routed here, the entry names
  `agent-launch --presets HOST`.
- **The gate's picker scenarios** pass `--presets`.
- **A new launcher check (`bare_launch_opens_the_entry`).**
  - It runs a bare launch on a pseudo-terminal with no host on PATH and a state root of its own.
  - It requires the entry's own refusal, the `--presets` hint and exit 1.
  - It fails by name when the route is switched off.
- **The UI entrypoint tests** (`compose/test_instructions_ui_entrypoints.py`) pass `--presets`.
  - The first commit attempt of 3c ran them without it.
  - A bare launch there reached the entry, which probed the `claude` on this machine's PATH once.
  - The test's own temporary HOME, `CLAUDE_CONFIG_DIR` and state root held it: the host exited
    with an error, and no model call was made.
  - The real state base holds no `workenv/`.
  - A test that launches bare on a terminal now reaches a real host unless it asks for the menu.
- **Documentation.** `docs/recovery.md`, `docs/session-model.md`, `docs/advanced-launch.md`,
  `ko/docs/advanced-launch.md` and `install.sh help` now say what a bare launch opens.

## Where it departs from the 04:02 design

Each departure is recorded as a decision.

1. **Only qualified hosts are offered beside the named one** (`D-20260929-138f97`).
   - The design said a start route per installed host. A route no probe qualified names no
     probe, so the entry could not name its host: its blocker would have named the start's tool.
   - The named host is probed when needed, and not started if the probe does not qualify it.
   - Other installed hosts are offered only where a probe already qualified them.
2. **Space in a focused field is a space** (`D-20260929-087624`). This is an addition to the
   grammar. The terminal reads the space byte as the Space key, and the model decides by focus.
3. **The instructions options keep the preset menu** (`D-20260929-e1f04c`). The design listed
   the flags that keep the menu and did not name these three.
4. **`sources` and `received` mint no actor.** Before first use they say nothing is held.
   `received` observes the preparation of the latest `activated` delivery, which is the
   session's own link.

## How it was checked

### Unit tests

| File | Tests | What they cover |
| --- | --- | --- |
| `test_tui.py` | 58 | |
| `test_terminal.py` | 17 | a real pseudo-terminal for raw mode, resize and restore; a pipe for end of input |
| `test_commands.py` | 28 | fake hosts; a screen fed the bytes a person types |
| `test_start.py` | 25 | |

`test_commands.py` covers:

- every verb;
- the auto-probe and its failure;
- two hosts and the tool turned;
- skipped confirmations;
- a refused start drawn;
- the check of an unknown start answered in the entry;
- the launcher's hint;
- the whole start → hook `SessionStart` → `received` flow.

### Mutation sweeps (workbench `v1-slice5/`)

- **`mutate5c.py`** (3a): 22 of 22 caught.
- **`mutate5d.py`** (3b): 58 of 58 caught on the full run over the tree this record lands with
  (`mutate5d-3c.txt`).
  - The first run missed five of 59.
  - One was equivalent: without the actor's early return, the exclusive create finds the file
    and returns the same actor. It is listed as equivalent.
  - Four were test gaps, now closed:
    - a split `ESC O` key;
    - two pseudo-terminal tests that waited instead of failing;
    - a state outside the answers with no reason.
- **`mutate5b.py`** (increment 2): 87 of 87 still caught, after four anchors moved.

### Cases and controls

- **The V1 cases with drafts** (`runv1-3b.txt`): 18 passed, 3 failed, 1 blocked, as before.
  - The six entrance drafts that can run pass.
  - The drafts are restated for the permissions element in the 3a restatement (`entry.py`).
- **`control5c.py`.** Removing the element, its Tab stop or its effect fails all six drafts.
  Changing its label fails none.
- **A pseudo-terminal smoke run.** It used the fake Claude Code, a temporary state root and
  Korean.
  - The probe line printed, then the first frame.
  - Tab, Tab, → changed the permissions to `확인 없이 실행`.
  - Ctrl-C left with 130.

## Open

- **Binding and sources.** No command binds a repository or adds a source. This was brought to
  the owner before the real use, as the 04:02 design says.
- **The probe line and command output are English.** Only the entry is localized.
- **The permission flags are not probed.** No probe has run with the skip arguments. The probe
  that qualified delivery ran with the host's own settings. The real use shows whether skipping
  changes what reaches a session.
- **Increment 4.** The unconfirmed start (`event_reply_lost`) blocks TUI-ENTRY-UNKNOWN's draft.
