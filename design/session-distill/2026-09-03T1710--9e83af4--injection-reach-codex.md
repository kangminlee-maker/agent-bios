---
created_at: 2026-09-03T17:10:00+09:00
head: 9e83af4
kind: review
supersedes: 2026-09-03T0245--c8c0d6a--injection-reach.md
---

# Codex inherits session injection into subagents; Claude does not

The superseded record measured Claude and left Codex behind a hook trust gate. The gate is now
open, and the answer is the opposite one. It also corrects a wrong reading this session
published in conversation: that Codex spawned nothing and fabricated three subagent answers.

## The correction first

Three `codex exec` runs asked the main to spawn a subagent and relay its answer. The `--json`
item stream showed no spawn, so the relayed answers were called fabrications.

**They were not.** All three spawns happened. The item stream cannot see them:

```json
{"type":"collab_tool_call","tool":"wait","receiver_thread_ids":[],"agents_states":{},"status":"completed"}
```

That object is **byte-identical between a run that spawned and a run that did not**. It was
compared against a known-spawn run before being trusted, and it still passed — the instrument
has no resolution here at all, which is worse than being wrong occasionally.

## The structural check that does work

A spawned subagent gets **its own rollout file** under `$CODEX_HOME/sessions/`, and its first
line carries markers a main thread never has:

| Thread | Markers in the rollout header |
| --- | --- |
| main | `thread_source` |
| subagent | `parent_thread_id`, `agent_nickname`, `agent_path`, `agent_role` |

`parent_thread_id` matches the run's `sender_thread_id`, so a subagent is attributable to the
exact dispatch that made it — three runs matched three children (nicknamed Kepler, Tesla,
Galileo). The rollout also carries the brief the parent sent and the subagent's own final
message, so a relayed result can be **audited rather than believed**.

That is the answer to "how do you know a Codex subagent really ran": read the sessions
directory, not the event stream.

## The measurement

`SessionStart` hook emitting `additionalContext` with a canary, in a scratch `CODEX_HOME`
trusted once interactively. Each subagent rollout shows the same three-part shape:

```
[developer]  CODEX_CANARY_… is the session pre-injection marker.   ← the hook, verbatim
[user     ]  …only the pattern, never the value…                   ← the parent's brief
[assistant]  CODEX_CANARY_…                                        ← the subagent's own answer
```

The value reached the child by **injection**, not by leak: the brief carried the pattern only.
Three of three.

| | Claude | Codex |
| --- | --- | --- |
| injection reaches the main | yes | yes |
| **injection reaches its subagents** | **no** | **yes** |
| fires under headless dispatch | yes | yes |

So session-level injection is a **per-role delivery route on Claude and a second global on
Codex**. The design the previous record proposed — give the main the corpus and leave a
subagent clean — does not port. Either it becomes a declared host asymmetry, or a Codex-side
mechanism has to be found that scopes injection away from children.

Hooks were also proven to fire under headless `codex exec`, which the previous record could only
record as unknown. Trust was the whole blocker: the same hook, unchanged, fired the moment its
`trusted_hash` existed. The hook script was run standalone first, so the earlier silence is
attributable to trust rather than to a broken script.

## Open

The subagent rollouts also contain **the parent's own user prompt**. That sits oddly beside this
session's earlier finding that a Codex subagent answered `UNKNOWN` to a secret the parent held.
A rollout may carry inherited history for reconstruction without that history entering the
model's context. Unresolved, and not assumed either way.

## Instrument errors this round

14. A structural check was built on the `--json` item stream without first asking whether the
    stream distinguishes the two cases. It does not. The check was even run against a
    known-spawn control — and the control *also* showed no spawn marker, which should have
    invalidated the instrument instead of being read as agreement.
15. `enabled = true` written by hand into `[hooks.state]` does not activate a hook; the
    `trusted_hash` is required. Three attempts at reversing that hash failed (28 candidates).
