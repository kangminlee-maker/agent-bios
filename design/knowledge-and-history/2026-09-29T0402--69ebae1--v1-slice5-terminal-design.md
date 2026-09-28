---
created_at: 2026-09-29T04:02:42+09:00
head: 69ebae1
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260929-0d8aa3, D-20260929-e1d487, D-20260929-24bf2e, D-20260929-c2b4cc, D-20260926-8ee6bb
---

# V1, fifth slice, third increment: the terminal, its commands and the launcher

This is the third increment of the [14:58 design](2026-09-28T1458--dcdbebc--v1-slice5-design.md).
It adds one element to the [16:01 entry grammar](2026-09-28T1601--4e305e5--v1-slice5-entry-grammar-design.md),
and it designs the program a person runs: `agent-bios start <host>` and the other commands of
`D-20260926-8ee6bb`. The host launcher routes into the same program. Three read-only surveys
preceded it on 2026-09-29: `install.sh`'s dispatch, the launcher, and what the design documents
specify for these commands.

## The owner's decisions (2026-09-29)

1. **The launcher opens the entry.**
   - A bare interactive `agent-launch <host>` opens the entry at the `host_launcher` entrance. That
     is also where a bare `claude` or `codex` typed at a terminal goes, through the shell
     connection.
   - The entry has no `Launch? [Y/n/q]` question.
   - A named preset is still started with `--preset NAME`, and the Custom hub with `--custom`.
   - The launcher's old menu stays reachable with `--presets`, so its other jobs keep a way in:
     Instructions, understand, the shell connection and the language.
2. **The session's permissions are chosen in the entry.**
   - The person chooses between the host's own settings and skipping its confirmations.
   - Skipping passes the flags the launcher's bypass presets pass:
     - Claude Code: `--dangerously-skip-permissions`;
     - Codex: `--dangerously-bypass-approvals-and-sandbox`.
3. **The start checks the host itself.** A host whose installed version no probe qualified for
   delivery to a new session is probed by the start before the entry is drawn. The start first
   says so in one line. A probe launches the host once and costs one model call.

## The grammar gains one element

W01's order becomes:

- `field.note`, `execution.tool`, **`execution.permissions`**, the blockers, `action.start`.

**`execution.permissions`** (setting):

- It is present with a start action.
- Its value is `host_settings` or `skip_confirmations`.
- It is `suggested` with the suggestion mark until ← or → changes it. It is then `selected`,
  with no suggestion mark. Nothing remembers the choice between starts.
- Its effect is `permission_request` with `host_settings`, and none with `skip_confirmations`.
- It is always a Tab stop, because it always has an alternative. ← and → change it only while it
  is focused and no start has been dispatched.

**What does not change:**

- The composition request is unchanged. Permissions are an argument of the launch, not part of
  the environment, so the terminal hands the choice to the start.
- The keys line names ←→ as changing a setting. The catalog key `key.tool` becomes
  `key.change`. It is named on every W01 with a start, since the permissions always have an
  alternative.
- The English label of `key.arrows` becomes `↑↓ items`. With `←→ change`, the English keys line
  would be 79 cells, one more than an 80-column row holds after the focus gutter.

The seven case drafts are restated for the element: one more Tab before the start, and the
element in every W01 frame.

## The program

### Where state lives

- **The state root** is `${AGENT_BIOS_STATE_DIR:-~/.local/share/agent-bios}/workenv/state`. This
  is the existing local state base plus a subtree workenv owns, and it is configurable, as the
  SSOT asks (SSOT 1283–1284). `AGENT_BIOS_STATE_DIR` is a root the caller chooses, so each
  entrance row says `root_origin: caller`.
- **The actor's ids** (principal, device, profile) are minted at first use. They are kept in
  `actor.json` beside the state root, readable by its owner alone.
- **The profile** is written by the journal on the first request, as `workenv/access.py` states.
- **No device key is made at first use.** The SSOT gives a person a protected local credential
  only "when a sharing/recovery operation needs one" (SSOT 868–870), and the account-free path
  signs nothing. TUI-ENTRY-ACCOUNT-FREE's binding step exercises the owner operation, not the
  program.

### The commands

Each command runs as `python3 workenv/commands.py <verb>`. `install.sh` dispatches `start`,
`profile`, `sources`, `prepare` and `received` there before its flag parser, as `learn` and
`cost` are dispatched. Every request is submitted through the journal as the actor's.

**The scope** is the repository bound from the checkout the command runs in, when one is bound;
otherwise it is the person's. Binding a repository, and adding sources, have no command in this
increment. See "Open for the slice's real use" below.

- **`profile`** reads the profile (`access.profile.read`). It prints the profile id, the principal,
  when first use wrote it, and the access state and generation.
- **`sources`** prints each position of the scope's basis in composition order: the collection or
  the sources held there, with their accepted revisions and member paths.
- **`prepare <host>`** composes the start the entry would suggest (`preparation.compose`). It
  prints the preparation's units in order, with their standing and body digests, and its material
  gaps. It activates and launches nothing. It first probes the host, if needed.
- **`start <host> [--entrance setup|host_launcher]`**:
  1. first use;
  2. the host probe, if needed;
  3. `route.offer` of a start route per installed host in the scope, the named host's first;
  4. `operation.history.read` of the scope;
  5. the entry, drawn in the terminal.

  On a dispatched start, it passes the entry's sealed compose request, unchanged, to
  `workenv.hosts.start` with the permissions chosen. The start composes and activates. Then
  `route.select` records the route for that request, and the program replaces itself with the
  host. A start the owner refuses is drawn as its answer, and nothing is launched.
- **`received`** answers `delivery.observe` for the latest session this installation activated.
  It prints what reached each recipient.

### The terminal

- **Its layer.** The terminal draws `workenv/tui.py`'s frames and turns key bytes into the
  model's inputs. It adds no rule of its own.
- **Drawing.** Each element is one line: the two-cell focus gutter, then its marks and its label,
  clipped at `columns − 2` cells. A field's value follows on up to three lines. An element below
  the last row is not drawn.
- **Keys.**
  - The arrows, Tab and Shift-Tab, Enter, Esc, Space, Backspace, Home, Page Up and Page Down are
    read by their escape sequences.
  - Bracketed paste arrives as one paste input.
  - Any other printable text is a text input.
  - A resize (`SIGWINCH`) is a resize input.
- **Leaving.** Ctrl-C and Ctrl-D leave without sending anything. No letter is a shortcut.
- **Answers.** A dispatched request's answer, which a pure drive never has, is drawn in its
  result element:
  - an unknown outcome stays `unknown`;
  - a refusal or a failure is `unavailable`, with the owner's reason as its label.

## The launcher and the entrances

- **`launch/agent-launch.py`.** A bare interactive launch execs `workenv/commands.py start <host>
  --entrance host_launcher`, under the Python that runs the launcher. The launcher's host names
  map to the adapters' (`claude` to `claude-code`). No preset, custom, understand, dry-run,
  resume or `--presets` flag may be present.
- **The gate's picker scenarios** open the old menu with `--presets`.
- **The Codex hook's trust.** It is keyed on the hook command's exact bytes: the interpreter's path
  and `hook.py`'s path (`D-20260927-f6c55a`). So a start probes and launches under one
  interpreter. A launcher running under another interpreter than `agent-bios` would be asked
  again.
- **Entrance rows.** `gates/workenv/entrances.jsonl` gains:
  - the five `install.sh` commands;
  - `workenv/commands.py`, one row per verb.

## Increments within this one

1. **3a.** The permissions element: `tui.py`, its tests and the drafts. Each adapter's skip flags,
   and the start taking a sealed request and the permissions.
2. **3b.** `workenv/local.py`, `workenv/commands.py` and `workenv/terminal.py`, the `install.sh`
   arm, the entrance rows and `package.json`.
3. **3c.** The launcher's route and its gate scenarios.

Each ends with a mutation sweep and a commit through the hook.

## Open for the slice's real use

V1's check is "seeing the profile, the sources and their order, preparing, launching a real
session and reading what reached it", with repository, personal and supplied Instructions
composed in that order. **No command yet binds a repository or adds a source.** The slice-four
use did both through a script calling the owner operations. Whether V1 gets commands for them,
and which, is brought to the owner before the real use.
