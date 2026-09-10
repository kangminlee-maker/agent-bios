---
created_at: 2026-09-03T19:00:00+09:00
head: 6ff9a31
kind: review
supersedes: 2026-09-03T1815--6ff9a31--per-role-delivery-levers.md
---

# A Codex subagent is not a fresh conversation — retracting a claim this session shipped

`2026-09-02T1740--ff09dd5--spawn-across-hosts.md` recorded, as one of two host-independent
facts, that a spawned subagent is isolated from the parent's conversation on both hosts. That is
**false on Codex**, and the reason it was believed is the reason this session has now been wrong
twice: the evidence was what the parent said, not what the child had.

## What was measured

A parent was given a secret existing nowhere on disk, told to spawn one subagent and ask for it
without putting the value in the brief. The child's **own** transcript was then read.

| Host | Child's transcript contains the parent's turn input | Child's answer |
| --- | --- | --- |
| Claude | **no** — two messages: the brief and its reply | `UNKNOWN` |
| Codex | **yes** — the parent's full prompt, secret included | the secret |

Claude's child is written to `agent-<id>.jsonl` next to the session transcript. Codex's is a
rollout whose header carries `parent_thread_id`, `agent_nickname`, `agent_path`, `agent_role`.
In both runs the brief was checked and did not carry the value, so what the Codex child had came
with the turn, not from the parent.

The original result was a relayed `UNKNOWN` from a Codex parent that also narrated its own
mechanism — *"I'll run the subagent with no inherited conversation context."* The narration was
wrong and the relay agreed with it. Reading the artifact reverses both.

## What this changes

The corpus said an in-process spawn is *a fresh conversation carrying your standing
instructions*. Half of that is now host-specific:

| | Claude | Codex |
| --- | --- | --- |
| inherits the standing corpus | yes | yes |
| inherits session-level injection (`SessionStart`, `UserPromptSubmit`) | no | **yes, both** |
| inherits the parent's turn input | no | **yes** |

A Codex subagent is therefore not a weaker perspective than its parent — it is nearly the same
one, with the caller's framing included. On that host, "go outside the process" is not a
preference between two grades of independence; in-process review buys almost nothing.

`claude/guides/cli-multi-model-workflow.md` gate 1 is corrected accordingly, in both languages,
and now names the artifact to read on each host.

## The other half of the round

`UserPromptSubmit` was the last untried lever for a Codex main-only route. It crosses too — both
canaries appeared as `developer` messages in the child's context and the child reported both. So
**Codex has no main-only injection route among the events tested**, and the per-role delivery
design stands as a declared Claude-only capability.

The same run produced the control that had been missing all along: two hooks in one file, one
trusted and one not, in a single dispatch — the trusted one fired and the untrusted one was
silent. That proves the gate is trust rather than "hooks do not run headless" without needing a
second run. Trust also survived a version bump (0.151.0 → 0.153.0), so the hash is over the hook
definition, not the binary.

## Instrument errors this round

16. A binary was pinned by a **version-bearing path**, which the corpus names as ambient state
    that drifts. Codex auto-updated mid-session and every probe died `rc=127`. Resolve the
    symlink at call time and print what it resolved to.
17. Twice now a subagent claim rested on the parent's relay. Claude's `-p` session transcript has
    no sidechain entries, which makes the relay look like the only evidence available; the child's
    transcript is a **separate file** and it is the evidence. Never grade a subagent on what the
    caller said about it.
