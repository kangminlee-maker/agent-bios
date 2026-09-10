---
created_at: 2026-09-01T13:30:51+09:00
head: 41b88a4
kind: design
supersedes: 2026-09-01T1321--41b88a4--chatgpt-desktop-corpus-observation.md
---

# Desktop preflight boundary and an agent-bios configuration path

## Correction

The superseded record said that the desktop task "loads agent-bios." That collapsed
deployment, instruction discovery, and launch preflight into one event.

The observed facts support this narrower statement:

- Codex loaded the global `~/.codex/AGENTS.md`.
- The file's `agent-bios:central` region is an artifact previously assembled and deployed by
  agent-bios, so that deployed corpus content reached the task.
- The ChatGPT desktop app did **not** run the agent-bios program, `agent-launch`, its terminal
  UI, or a preset-derived `LaunchPlan` for this task.

## Three different mechanisms

| Mechanism | Authority | Lifetime | Desktop observation |
| --- | --- | --- | --- |
| Corpus selection and apply | `agent-bios onboard --domains ...` → assembler | persistent across later sessions | the previously applied result was present |
| Instruction discovery | Codex reads global and project `AGENTS.md` files | fixed when the task starts | global and repository files were loaded |
| Launch preflight | interactive shell function → `agent-launch` → real CLI | one CLI invocation | not reached |

For an interactive zero-argument terminal launch, `launch/agent-launch.zsh` replaces the shell
command `codex` with a function and runs `agent-launch` only when stdin and stdout are TTYs. The
desktop app instead starts its bundled Codex app-server directly, outside the shell function,
so strengthening `.zshrc`, PATH shims, or the existing wrapper cannot make the TUI appear.

The corpus panel and the launch preset panel also have different effects. Applying a corpus
selection delegates to the existing `agent-bios onboard --domains ...` path, which updates
`selection.json`, assembles the selected corpus, and atomically replaces only the managed region
of `~/.codex/AGENTS.md`. A launch preset instead projects model, effort, policy, agents, and
developer instructions into that one CLI process; it does not update the global instruction
file.

## What Codex currently exposes

OpenAI documents three relevant desktop surfaces:

1. `AGENTS.md` discovery reads the global file before project files, once when a task starts.
2. `SessionStart` hooks run after the session exists and may add context or show a system
   message. Command hooks receive protocol JSON on stdin and return protocol output on stdout;
   they are not a terminal preloader.
3. Project actions appear in the desktop top bar and run commands in the integrated terminal.

A hook can therefore report the applied selection or detect missing state. It cannot make a
late rewrite of `~/.codex/AGENTS.md` change the instruction chain already loaded for the current
task. A project action can run the existing terminal selector, but it is project-local and its
result applies to a new task.

## Options

| Option | User outcome | Cost / risk | Done when | Portability |
| --- | --- | --- | --- | --- |
| Run `agent-bios onboard` in the integrated terminal, then start a new task | works now; no product change | manual and easy to forget the restart | the next task observes the chosen managed region | uses the existing CLI wherever it runs |
| Add a project Action that runs the same command | one visible button inside the app | repeated per project; still applies only to a new task | click, select, apply, open a new task | official desktop surface, project-scoped |
| Bundle a Codex plugin with a status hook and explicit `$agent-bios-onboard` skill | one cross-project desktop entrypoint; current domains are visible | medium implementation; selection is conversational rather than the old TUI | the skill passes an explicit validated set to `agent-bios onboard`, and the next task reports that set | official plugin/hook surfaces; no app-bundle patch |
| Move selected Codex domains out of global `AGENTS.md` and inject them from `SessionStart` | a selection can affect the current task | high-risk host-specific redesign; splits Claude and Codex delivery and duplicates authority | hook context exactly equals the selected assembled bundle on startup and compaction | Codex-only |

Replacing the app's bundled Codex binary, intercepting its absolute path, or relying on a file
watcher is not a viable option. Those routes cross the app-signing/update boundary or duplicate
the installer/assembler's write authority, and an open task would still retain its old context.

## Recommended default

Use the third option, delivered in two increments:

1. **Immediate recovery path:** document and expose `agent-bios onboard` in the desktop
   integrated terminal. After a successful apply, state explicitly that the current task is
   unchanged and a new task is required.
2. **Desktop-native path:** package a personal Codex plugin whose read-only `SessionStart` hook
   displays the applied domains and whose explicit `$agent-bios-onboard` skill gathers the
   desired set. The skill must not write `selection.json` or `AGENTS.md`; it passes the exact set
   to the existing `agent-bios onboard --domains ...` command, which remains the sole writer,
   validator, installer, and rollback/canary owner.

The hook should be advisory, not a selector. It runs after instruction discovery, has no TTY,
and cannot repair the current task by rewriting the source file. Bundling it with the plugin also
avoids overwriting or merging into the user's existing `~/.codex/hooks.json`.

This restores corpus configuration inside the desktop workflow without claiming parity for the
other half of the TUI. Model, effort, permission, review, and developer-instruction `LaunchPlan`
settings remain CLI-only until the desktop exposes a supported pre-thread creation input for
them.

## Verification boundary

The existing activation canary exercises Claude, not Codex desktop. The existing Codex verify
path proves that the managed marker exists, not that a desktop task consumed it. Do not relabel
either as desktop proof.

The desktop path is complete when all of these are observed:

1. the configuration surface enumerates a non-empty domain set from the installer-owned status;
2. the chosen closed set reaches `agent-bios onboard --domains ...` unchanged;
3. the installer records the selection and replaces only the managed global region;
4. the current task is labelled as still using its start-time context; and
5. a newly created desktop Codex task observes the newly selected managed content.

The last item remains a live-surface observation until a supported desktop or app-server probe
can expose the effective instruction chain deterministically.
