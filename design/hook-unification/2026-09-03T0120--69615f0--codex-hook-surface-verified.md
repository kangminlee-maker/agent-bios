---
created_at: 2026-09-03T01:20:00+09:00
head: 69615f0
kind: review
supersedes: 2026-08-19T0929--12914d0--backlog.md
---

# Codex's hook surface, verified — and the stale claim it leaves behind

The 2026-08-19 backlog already established that Codex hooks exist and are config-parsed, at
codex-cli 0.146.0. Nothing that record changed ever reached the live files, so four live sites
went on saying the opposite for two weeks. This record re-verifies the capability at 0.151.0,
names the sites, and records the correction.

The failure shape is the one `AGENTS.md` names under ontology rounds: **when a decision lands,
nothing re-reads the claims whose dependencies it changed.** The knowledge was in the repo. It
was not where a reader would meet it.

## What Codex actually has (codex-cli 0.151.0)

`[features] hooks = true` is **stable**, not experimental (`codex features list`). Registration
is `$CODEX_HOME/hooks.json`, same shape as Claude's `settings.json` block — event name, an
optional `matcher`, a list of `{type: "command", command: ...}`.

Twelve events, extracted from the binary's own enum:

```
PreToolUse  PermissionRequest  PostToolUse  PreCompact  PostCompact
SessionStart  SessionEnd  UserPromptSubmit  SubagentStart  SubagentStop
Stop  Interrupt
```

**PreToolUse blocks.** The binary carries the literal failure strings:

```
Command blocked by PreToolUse hook:
Tool call blocked by PreToolUse hook:
```

The payload carries `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `reason`,
`model`, `permission_mode`, `agent_transcript_path`, `stop_hook_active`, `tool_name`,
`tool_input`, `tool_response`, `last_assistant_message`, and — the one that matters for tier
enforcement — **`agent_id` and `agent_type`**.

So for the pinned-tier question Codex is the *easier* host, not the harder one: `agent_type` is
a first-class field and `SubagentStart` is a dedicated event, where Claude requires reaching
into `tool_input.subagent_type` on the Agent call.

**Not verified: whether a hook fires under headless `codex exec`.** Hooks are trust-gated —
`config.toml` carries `[hooks.state."<path>:<event>:<i>:<j>"]` with `trusted_hash` — and a
freshly written hook in a scratch `CODEX_HOME` produced no output for either PreToolUse or
PostToolUse. The hash input could not be reproduced (nine candidate hashings, no match), so no
positive control was established and the silence proves nothing. Any build gates on getting one
hook to fire first.

## The lever that may make the hook unnecessary

`[agents] default_subagent_model` and `default_subagent_reasoning_effort` are real config keys,
and they govern a spawn that names no tier.

Establishing this took three instruments, two of which could not discriminate:

| Probe | Verdict |
| --- | --- |
| Does the config load? | useless — an unknown table loads fine; the bogus-table control passed too |
| Wrong type at the key | discriminating — a known key errors at the *value* position (`2:26`), an unknown one blows up the whole table at `1:1` |
| Bogus model name, real spawn | decisive |

The third: with `default_subagent_model = "no-such-model-xyz"`, a spawn naming no agent type
returned `Unknown model 'no-such-model-xyz' for spawn_agent. Available models: gpt-5.6-sol,
gpt-5.6-terra, gpt-5.6-luna, gpt-5.5, gpt-5.4`. With `gpt-5.6-luna` the same prompt returned
`PONG`. The key is honored on exactly the path the pinning rule is about.

That is a one-line config change with no friction and no rule text — strictly better than a
blocking hook for this particular problem, on this host.

**No Claude equivalent was found.** `claude --help` (2.1.259) exposes `--agent`, `--agents`,
`--model`, `--effort`, `--fallback-model`, but no default for an untiered subagent. The
installed package could not be located to search its settings schema, so absence is *not*
proven — only unfound.

## The four live sites, corrected

| Site | Said | Now says |
| --- | --- | --- |
| `claude/hooks/tooling-gotchas-hook.py` header | "the hook is Claude-only" | agent-bios registers this hook on Claude only; Codex has hooks of its own, not wired here |
| same file, `self_test` docstring | "Codex gets nothing from a hook" | nothing registers this hook on Codex; wiring is open work, not a host limitation |
| `SURFACES.md` catalog row | Reaches: `Claude only` | `Claude only, by deployment` |
| `SURFACES.md` Hook injection admits | "Claude-only, so anything admitted here needs a guide fallback" | the guide fallback stands, but the boundary is named as deployment, with the Codex surface and this initiative cited |
| `benchmarks/dispatch.py` | "codex has no settings file" | the codex spec declares none, so nothing is registered there |
| `benchmarks/selftest.py` control | "a host with no settings surface carries no hooks" | "a host whose spec declares no settings file carries no hooks" |

The first two ship. That is why they were fixed first: a comment in `claude/hooks/` is installed
on every user's machine and read by the next model that opens the file.

Dated records under `design/` were left alone — their age is on the label, which is the point of
the naming rule.

## Instrument errors this round

Continuing the running list; all caught, three before they reached a conclusion:

11. `which codex` and `type -a claude` resolve to **shell functions** from the launcher, so
    `realpath` on the result landed inside the repo and reported the `codex/` payload directory
    as the binary. Worse, a bare `claude config list` launched a nested Claude session that
    answered in prose. Resolve past the wrapper (`/opt/homebrew/Caskroom/codex/<v>/bin/codex`)
    before probing either host.
12. `cmd 2>&1 >/dev/null | head` under zsh MULTIOS delivered stdout to the pipe anyway, so a
    config probe read JSON where it expected an error message. Separate the streams into files.
13. The first config probe asked "does it load?" A bogus table loaded clean, which is what the
    negative control was for. Acceptance is not knowledge when unknown keys are ignored.
