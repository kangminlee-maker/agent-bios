---
created_at: 2026-09-27T20:02:02+09:00
head: 28d1102
kind: backlog
supersedes: null
---

# Backlog — bringing a session that agent-launch did not start to the same state, mid-session

Owner's request, 2026-09-27: a skill that, inside a session started without `agent-launch`,
injects what `agent-launch` would have delivered, so the session then works as if it had been
started that way. Nothing here is designed or decided; this records the request and what the
current code says about it.

## What happens today

`docs/session-model.md` states the boundary: an Instructions selection seeds future **activated**
sessions, and plain CLI or Vanilla use receives nothing. Activation happens only at launch
(`compose/instructions_session.py`):

- **Codex:** the effective native developer instructions are preserved; the private instructions
  and the dynamic launch contract are injected as developer instructions. A durable host thread
  is created and read back, and its pin is recorded.
- **Claude Code:** a per-call append and a requested session id. The pin is recorded only after
  that id is observed in the native session log.
- **Both:** session-scoped hooks (a generated Claude plugin, per-run Codex `-c hooks.*`) and the
  private management bootstrap's path in the startup text, so `$agent-bios` is reachable.

A session started as plain `claude` or `codex` has none of these, and nothing can add them to it
afterwards the same way.

## What "the same as agent-launch" can and cannot mean inside a running session

- **Text can arrive; its standing differs.** A command the session runs can print the selected
  snapshot, and the model reads it as conversation content. That content is not system- or
  developer-level instruction, and the always-surface budget applies to it as to any other text.
- **Later events are not covered.** Compaction (`SessionStart` compact) and children
  (`SubagentStart`) are reached only by hooks the host registered at start. Codex takes per-run
  hooks only at launch. Claude Code loads plugins at startup. Registering hooks for a running
  session means writing the person's native settings, which the private install preserves; that
  needs the person's consent.
- **Nothing to resume.** No pin exists, so a later resume cannot restore the environment.
- **Delivery is not use.** C07 keeps "delivered" and "used" as separate facts, so the skill can
  show what was handed over, not that the model followed it.

## How it relates to the Team work-environment work

V1's fourth slice built this case's owner side (see the Team work-environment
[handoff of 2026-09-27 19:44](../knowledge-and-history/2026-09-27T1944--d80365f--handoff.md)). Each host adapter names the environment variable
through which a command the session runs finds its own session id (`CLAUDE_CODE_SESSION_ID`,
`CODEX_THREAD_ID`). That command is the *current* recipient C11 names, and its route is qualified
on both hosts on this machine. Once the third increment lands, a skill could run such a command:
open a link for the current session, compose, activate, and print the bodies. The same owner
operations would serve a mid-session activation and a hook-driven delivery. The rehydrated and
child recipients would still be unreached without registered hooks.

## Questions to settle before building

- Which parts of launch activation the skill must match, and how to tell the person which parts
  a mid-session activation cannot give.
- Whether the skill offers to register hooks for later sessions, with the person's consent, or
  only ever delivers to the current one.
- How to re-deliver after compaction without a hook (for example, telling the person to run it
  again), and how the session knows it has to.
- Host neutrality: Claude Code, Codex and a host added later, through the adapters rather than
  per-host scripts.

**Start condition:** after V1's fourth slice, third increment (real delivery through the hook),
because the mid-session command shares its owner operations.
