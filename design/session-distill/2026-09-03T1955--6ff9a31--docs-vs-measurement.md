---
created_at: 2026-09-03T19:55:00+09:00
head: 6ff9a31
kind: review
supersedes: 2026-09-03T1900--6ff9a31--codex-subagent-not-isolated.md
---

# What the vendors document, and the two conclusions it overturns

Reading the official sources after measuring turned two of this round's conclusions inside out.
Both were negative claims — "there is no way to X" — and a negative claim from probing is only
ever "not found."

## Codex: the exclusion lever exists, and it is a tool parameter

`spawn_agent` takes **`fork_turns`** (`codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs`):

| Value | Effect |
| --- | --- |
| `"all"` (**default**) | `FullHistory` — the parent's whole rollout becomes the child's inherited context |
| `"none"` | no parent context passed |
| `"3"` | the last N fork-turn boundaries |

That default is the entire explanation for this round's measurements: a Codex spawn **is a fork
unless told otherwise**. Verified rather than assumed — with `fork_turns: "none"` the child's
rollout contained neither the parent's secret nor the `SessionStart` canary, where the same probe
at the default contained both.

So the earlier conclusion is retracted: **Codex can produce a clean subagent, per spawn.** That is
finer-grained than anything on the Claude side, which decides corpus reach at process level. The
reason config probing failed is that this is not config — it is a parameter the model passes, so
it lands on the rule surface, not the capability surface.

Two more mechanisms the docs name and this session had not found:

- **`SubagentStart` hooks** receive `agent_id`, `agent_type`, `model`, `permission_mode` and may
  return `additionalContext` **and `continue: false` to block**. That is a real enforcement point
  for "pin the tier before dispatch" — the check is a set membership test on `agent_type`, and the
  host will refuse the spawn.
- A subagent inherits the parent's **prompt cache key** as `source:parent_thread_id`, which is why
  Codex fork reuse measured the way it did.

## Claude: the docs match the measurement, and name a role that already ships clean

`code.claude.com/docs/en/sub-agents` states a non-fork subagent starts fresh: it receives its own
system prompt, the Agent-tool prompt, the CLAUDE.md hierarchy, git status, preloaded skills, and a
sibling roster — **not** the parent's conversation, tool results, system prompt, output style, or
auto-memory. That is exactly what the child transcript showed.

Two facts worth having:

- **Built-in `Explore` and `Plan` intentionally omit CLAUDE.md files and git status.** A
  corpus-free subagent role already ships; the per-role delivery design does not start from zero.
- A **fork subagent does exist** — `/subtask`, documented as inheriting the full conversation and
  prompt cache. The 2026-09-02 record's "there is no subagent-fork command" is too strong and is
  corrected here. What that record measured is still true of this environment: in headless `-p`,
  `subagent_type: "fork"` returns `Agent type 'fork' not found`, and the available types are
  claude, Explore, frontier, general-purpose, Plan, sweep, workhorse and the plugin agents.

## The corrected picture

| | Claude | Codex |
| --- | --- | --- |
| default: child sees parent's conversation | no | **yes** (`fork_turns` defaults to `all`) |
| default: child sees the standing corpus | yes (except `Explore`/`Plan`) | yes |
| child sees session-level injection | no | yes, at the default |
| make a child clean | process-level (`--setting-sources ''`), or use `Explore`/`Plan` | **per spawn** (`fork_turns: "none"`) |
| refuse a spawn by agent type | not found | `SubagentStart` + `continue: false` |

**Both hosts can produce a clean subagent.** The mechanisms and the defaults differ, and Codex's
default is the permissive one — a spawned Codex reviewer inherits the caller's framing unless the
caller says otherwise, which is precisely the case where independence was the point.

## Method note

Every negative in this round came from probing a config surface, and both were wrong because the
mechanism lived somewhere else — a tool parameter, a hook event. Probing establishes presence, not
absence. The docs were the cheaper instrument and were consulted last; on a capability question
they belong first, with measurement confirming rather than substituting.
