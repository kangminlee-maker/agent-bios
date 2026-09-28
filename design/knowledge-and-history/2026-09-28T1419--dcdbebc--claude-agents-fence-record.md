---
created_at: 2026-09-28T14:19:03+09:00
head: dcdbebc
kind: design
supersedes: null
---

# Claude Code applies an `--agents` definition's tool fence to its subagent

The [14:04 record](2026-09-28T1404--b04af19--v1-slice4-launch-delivery-record.md) left one thing
unmeasured. The start gives each tier a session-scoped definition that keeps the installed one's
fields (`D-20260928-5b8737`). It was not shown whether Claude Code applies a tool fence written in
such a definition. It does, on Claude Code 2.1.283, measured on this machine on 2026-09-28.

## How it was measured

There were three runs of `claude -p`, one subagent each. Each run had a scratch directory of its
own, no setting sources, and edits accepted (`--permission-mode acceptEdits`), so only the
definition decided whether the subagent could write. The subagent was told to create a file
with the Write tool, not a shell, and to reply `NO_WRITE_TOOL` if it had no Write tool.

| The `--agents` definition | File written | Subagent's reply | Tools its transcript shows it calling |
| --- | --- | --- | --- |
| no fence (control) | yes | `WROTE` | `Write` |
| `disallowedTools: [Edit, Write, NotebookEdit]`, as the shipped frontier and sweep | no | `NO_WRITE_TOOL` | none |
| `tools: [Read]` | no | `NO_WRITE_TOOL` | none |

So a tier defined for the session keeps the read-only fence its installed definition states. The
control shows that the other two runs were refused by the fence, not by permissions.

## What this does not show

- It does not show whether a fenced subagent can still write through a tool the fence leaves
  open, such as `Bash`. The shipped fence names only `Edit`, `Write` and `NotebookEdit`; that is
  the installed definition's own boundary, which the start does not change.
- It does not measure Codex's `sandbox_mode` in a session-defined role. The start carries it as
  it carries the installed role's other fields.

## Evidence

The workbench's `team-env-20260920/v1-slice4-use/start/`: `fence.py`, `fence.out`,
`fence/result.json`, and the three session ids named there.
