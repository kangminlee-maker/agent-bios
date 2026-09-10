---
created_at: 2026-09-03T02:45:00+09:00
head: c8c0d6a
kind: review
supersedes: 2026-09-03T0120--69615f0--codex-hook-surface-verified.md
---

# Session-level injection reaches the main and not its subagents

The question that decides whether the corpus can move off the always-loaded global:
**does a session-level pre-injection follow a spawn?** It does not, on Claude. That makes
delivery a per-role choice for the first time, which the global file has never been able to be.

## Result

Two `claude -p` runs, same prompt, same seat (`claude-opus-5` / medium), differing only in how
the marker was delivered. Each run asked the main to report a token matching
`SESSION_CANARY_<alnum>` in its own context, then to spawn one `general-purpose` subagent and
ask it the same about *its* context — with the value withheld from the brief.

| Delivery | main | subagent |
| --- | --- | --- |
| `SessionStart` hook, `additionalContext` | reported the value | **NONE** |
| project `CLAUDE.md` in cwd | reported the value | reported the value |

The second row is the control, and it is what makes the first readable: the same question, asked
the same way, gets the value out of a subagent when the subagent actually has it. Without it,
`NONE` could only have meant "subagents answer NONE to this question."

Both runs were verified from the transcript rather than the answer: exactly one `Agent` tool
call each, and the canary absent from both briefs. A relayed `NONE` from a spawn that never
happened would have read identically.

The first run also settles a second unknown by being `-p`: **`SessionStart` fires in headless
dispatch.** A delivery route that worked only in the interactive TUI would have been unusable
for batches.

## Why it matters

Every rule in `claude/CLAUDE.md` is re-sent to every subagent — measured at 19,360 tokens with
`cache_read: 0`. That is the mechanism behind this round's other finding: a spawned reviewer
carries the same rules, learnings and blind spots as its caller, so it is a fresh conversation
and not a fresh prior.

Session-level injection separates those two audiences. It can give the main everything while
leaving a subagent clean. Nothing else in the delivery catalog does that — `SURFACES.md` lists
the global bundle as reaching "every session, every subagent" with no way to split them.

That cuts both ways and the split is the design question, not a free win:

- A **verifier** should probably not inherit the caller's priors. Today it always does.
- A **worker** should probably inherit the coding and verification rules. Today that is the only
  thing it can do.

So the useful shape is not "move the corpus off the global" but **make delivery selectable per
role**, which requires knowing which rules each role needs — a question nobody has asked yet
because the answer was fixed.

## What is still unknown

- **Codex.** `SessionStart` exists in the binary's event enum, but hooks there are trust-gated by
  a per-hook `trusted_hash` and no hook has been made to fire in a scratch `CODEX_HOME`. Whether
  Codex behaves the same way is unmeasured — not negative.
- **Reliability.** The global file is the only delivery mechanism proven to always load. A hook
  can be untrusted, disabled, or silently fail, which is exactly what happened on Codex today.
  Anything that must work when the agent fails to recognize the situation cannot move to a
  mechanism with those failure modes until they are characterised.
- **Other clients.** Measured on the CLI only. The SDK, the desktop app and the web app were not
  tested.
- **Cache behaviour.** Whether injected context caches like a static file was not measured, and
  it decides the cost side of any move.

## Interim policy

`AGENTS.md` §8 now freezes the global to reductions. That is deliberately narrower than the
design question: it stops growth, which is the part that is irreversible in practice, without
committing to where the corpus ends up. Moving anything is an architecture commitment that
invalidates downstream units, so by this repo's own Escalation gate it belongs in a blind-packet
design pass, not in a conversation.
