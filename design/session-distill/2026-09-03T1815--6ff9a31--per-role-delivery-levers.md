---
created_at: 2026-09-03T18:15:00+09:00
head: 6ff9a31
kind: review
supersedes: 2026-09-03T1710--9e83af4--injection-reach-codex.md
---

# Per-role delivery: both hosts can target a subagent, only Claude can exclude one

The asymmetry recorded last is one-directional, which is the shape that decides the design.

## Claude has both directions, and the second one already ships

An agent body reaches the subagent and **not** the main — the exact inverse of session injection.
Measured with a launch-defined agent (`--agents '{"probeagent":{...,"prompt":"AGENT_BODY_CANARY_… "}}'`),
asked for the value by pattern only:

```
MAIN: NONE
SUB:  AGENT_BODY_CANARY_3XQ7
```

Verified structurally, not from the answer: one `Agent` call, `subagent_type: probeagent`, canary
absent from the brief.

So Claude covers every combination already:

| Claude mechanism | main | subagent |
| --- | --- | --- |
| `SessionStart` `additionalContext` | yes | **no** |
| agent body (`--agents` at launch, or `agents/*.md`) | **no** | yes |
| global `CLAUDE.md` | yes | yes |

`--agents` is a launch flag, so the subagent-only route is session-scoped rather than fixed on
disk. Per-role delivery on Claude needs no new mechanism — only the decision about which rules
each role gets.

## Codex: the excluding direction was not found

Four candidate keys were probed under `[agents]` with the wrong-type instrument that established
`default_subagent_model`:

| Key | Error position | Reading |
| --- | --- | --- |
| `default_subagent_model` | `2:26` "expected a string" | known key |
| `subagent_developer_instructions` | `1:1` "expected struct AgentRoleToml" | not a key here |
| `subagent_history_start_ordinal` | `1:1` | not a key here |
| `history_mode`, `memory_mode` | `1:1` | not a key here |
| *(negative control)* `bogus_xyz` | `1:1` | — |

The positive control separating `2:26` from `1:1` is what makes this readable; the four strings
exist in the binary but are not user config at this path.

`[features.multi_agent_v2]` could not be probed at all — **its positive control fails
identically** to its negative one (`data did not match any variant of untagged enum FeatureToml`),
so that table has no resolution with this instrument and nothing about it is claimed.

Codex's agent TOML carries `developer_instructions`, so the *subagent-only* direction almost
certainly exists there in the same shape as Claude's agent body. It was not measured. What is
missing is **main-only**.

## The consequence

> Both hosts can target a subagent. Only Claude can exclude one.

That is a workable shape rather than a blocker. On Codex, session injection behaves like the
global, so moving a rule from the global to injection there **changes nothing about what a
subagent sees** — it does not make things worse, it just buys nothing. The Claude-only capability
is *making a subagent clean*, and that is what has to be declared rather than assumed portable.

## The one untried lever

`UserPromptSubmit` injection on Codex. A subagent's turn is not a user prompt, so it may not
cross where `SessionStart` does. Untested because hook trust is granted per event, and the
registration needs one interactive approval in the scratch home. If it does not cross, Codex gains
a main-only route and the design ports after all.
