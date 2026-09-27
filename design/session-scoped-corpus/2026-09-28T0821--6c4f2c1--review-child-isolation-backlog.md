---
created_at: 2026-09-28T08:21:17+09:00
head: 6c4f2c1
kind: backlog
supersedes: null
---

# Backlog — a review child in an agent-launch Codex session receives the private instructions

## The owner's rule

The owner ruled on 2026-09-28 (`D-20260928-4a1cc3`) that a review session dispatched as a child
receives no agent-bios content, only its review instructions, because a review needs an isolated
perspective. Children dispatched by the tier rule (frontier, helm, workhorse, sweep) receive what
the main session received.

## What breaks it today

`compose/instructions_session.py` activates the private instructions in a Codex session as
session-wide `developer_instructions`.

It was measured on 2026-09-28 on Codex 0.157.1 through the app server. The tool is
`review_child_isolation.py`, and its outputs sit beside it in the workbench's
`team-env-20260920/v1-slice4-use/manual/`. A marker given that way reached the child's base
developer message in both cases:

- a child spawned with `fork_turns: none`;
- a child spawned with `fork_turns: all`.

The spawn arguments are confirmed in the parent's rollout.

So every Codex subagent of a session agent-launch started carries the private instructions,
review children included, however it was forked.

For comparison, a marker a `SessionStart` hook gave the parent reached only the `all` child, as a
copied developer message. That is the route V1 delivers by.

## Not measured

- **A role's own instructions.** The measured child had no role: no Codex agent roles are
  installed natively on this machine, so the child's `agent_role` was null. Whether a role's own
  `developer_instructions`, such as the shipped `codex/agents/reviewer.toml`, replace the
  session's for its child is the first thing to measure. If they do, a review dispatched with that
  role may already be clear.
- **Claude Code.** It is not affected in the same way as far as this record knows: the launcher
  appends the private instructions per call, and a Claude child starts from its own definition.
  This is not measured here.

## Directions, none chosen

- Deliver the private instructions through a `SessionStart` hook instead of
  `developer_instructions`. This is the route V1 builds (`D-20260928-30d875`: V1 joins agent-launch
  after its own start). A review child spawned with `fork_turns: none` then receives none of them.
- Give the review role instructions that replace the session's, if the measurement above shows a
  role can.

## When

This waits until V1 joins agent-launch (`D-20260928-30d875`), by the owner's choice on
2026-09-28. Until then, the shipped guide states that a review child is spawned with
`fork_turns: none`, and that session-wide `developer_instructions` reach every child
(`claude/guides/cli-multi-model-workflow.md`).
