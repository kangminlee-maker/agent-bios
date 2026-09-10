---
created_at: 2026-09-02T17:40:00+09:00
head: ff09dd5
kind: review
supersedes: 2026-09-02T1130--ff09dd5--spawn-economics-measured.md
---

# Spawn across hosts: what transfers and what does not

The economics record measured Claude only. The spawn policy is projected verbatim into
`codex/AGENTS.md`, so a rule changed on that evidence would land on a host it never
observed. This record measures the Codex side of the same questions.

Method: `codex exec --json`, which reports per-turn `usage` on `turn.completed` — including
`cached_input_tokens`, the analogue of Claude's `cache_read_input_tokens`. Unlike Claude's
result object, Codex separates `total_token_usage` from `last_token_usage` in its rollout,
so the per-turn figure needs no reconstruction.

## What is the same

**The tier ladder.** Both hosts bind four tiers, and both deploy agent definitions for them.
An earlier claim in this session that Codex lacked `workhorse` was wrong — it came from an
`ls` truncated by `head -3`. Codex has `frontier`, `reviewer`, `sweep`, `workhorse`; Claude
has `frontier`, `sweep`, `workhorse`. `reviewer` is an extra on the Codex side, not a gap.

**In-turn delegation exists on both.** Codex exposes `collaboration.spawn_agent` alongside
`followup_task`, `interrupt_agent`, `list_agents`, `send_message`, `wait_agent`. Its agent
types are the four deployed tiers plus built-in `default`, `explorer`, `worker`. An earlier
suspicion here — that Codex's multi-agent surface sits with the client rather than the model
— was wrong.

**A spawned subagent is isolated on both.** A parent told to hold a secret that exists
nowhere on disk, then to spawn a `sweep` subagent and ask it for that secret, relayed
`UNKNOWN`. The parent narrated the mechanism itself: *"I'll run the subagent with no
inherited conversation context."*

**A spawned subagent receives the whole instruction corpus on both.** Asked to name the
instruction files in its context, a Codex subagent listed `AGENTS.md` and the full deployed
guide set under `${CODEX_HOME}/guides/` — paths absent from the question, so it could only
have them from its own context.

That last pair is the one host-independent fact this session produced:

> **An in-process spawn isolates the conversation and injects the entire instruction corpus.
> It is therefore a different conversation, not a different perspective.**

## What differs, and it is the one that matters

Forking preserves conversation content on both hosts, and the KV cache on only one.

| Fork target | Claude `--fork-session` | Codex `exec fork` |
| --- | --- | --- |
| same model | **98.9%** cached | **18.0%** cached |
| one tier down | — | 14.0% (terra) |
| cheapest tier | 0.0% (haiku) | 16.4% (luna) |

Measured with the fixture absent from the working directory, so re-derivation was impossible
and the model had to use inherited context; all cells ran zero commands and returned 269/269.

On Claude the model binding is decisive: keep it and context is nearly free, change it and
the whole conversation is re-sent at creation price. On Codex the binding is irrelevant —
every fork re-sends. **"Do not change the model when you fork" is a real rule on Claude and
an empty one on Codex**, which makes it a licensed asymmetry the corpus has to name rather
than a rule to project.

Codex's inheritance is also more robust for correctness: forking down to the cheapest tier
still returned 269/269, where Claude's haiku fork fell to 84.7%.

## Excluding the corpus from a spawn

Neither host's agent definition can do it. Claude's frontmatter carries `name`,
`description`, `model`, `effort`; Codex's TOML carries those plus `sandbox_mode` and
`developer_instructions`. No field suppresses the inherited corpus, so **there is no
per-spawn exclusion.**

Process-level exclusion works on both, and was verified in both directions:

| Host | Lever | Effect |
| --- | --- | --- |
| Claude | `--setting-sources ''` | subagent answers NONE to every canary; injection 21,926 → 11,185 |
| Claude | `--setting-sources project` | global gone, project `CLAUDE.md` kept |
| Codex | `CODEX_HOME` → auth-only directory | `AGENTS.md` and guides absent; input ~69k → 15.4k |

Three costs come with it. Agent definitions live in the same scope, so the tier ladder goes
too — Claude's available types fell from 15 to 5, and an auth-only `CODEX_HOME` contains no
`agents/*.toml` by construction. Emptying `CODEX_HOME` completely also removes the OAuth
credential and every request fails 401; `auth.json` has to be copied in, which the capability
catalog's L5 entry for this lever does not mention. And exclusion is not total: skills still
loaded under the stripped Codex home.

So a corpus-free reader is reachable only as a **separate process**, without the tier ladder,
with the model named explicitly.

## Consequence for the rule

Of the four changes the economics record proposed, the cross-host evidence sorts them:

| Change | Transfers? |
| --- | --- |
| Add the blind-packet requirement to Independence | yes — it constrains brief content, not mechanism |
| Re-aim Independence at perspective the caller cannot supply | yes — corpus injection is confirmed on both |
| Require the tier to be named when delegating | yes — both ladders exist and both are reachable from the model |
| Drop cost as a criterion | phrase it without depending on a price ratio; Claude's 1:50 cache-to-output ratio is not a Codex fact, and Codex runs on an OAuth subscription where the scarce resource is rate limit, not dollars |

Fork guidance is the exception and must be host-qualified or left out.

## Limits

One repetition per Codex cell. The three fork cells agreeing within 14–18% is itself evidence
of a structural rather than noisy result, and the gap to Claude's 98.9% is far outside any
plausible noise, but no Codex figure here should be quoted as a measured mean.

Codex cost was not measured in money and cannot be: the session runs on an OAuth
subscription, so the comparable scarce quantity is tokens and rate-limit budget.

## Instrument errors added here

Continuing the list from the previous record, all caught, all the same shape — a probe that
could not discriminate:

5. A context-size proxy read the session transcript's last usage record. Under `--resume`
   every turn shares one file, so all four turns reported the end state. Per-turn figures
   must come from each dispatch's own result.
6. `result` is the final assistant message, not the session's output. A run whose last
   message was a correction delta scored 3 items instead of 269.
7. `ls … | head -3` truncated a four-entry directory, and an asymmetry was claimed from the
   three that survived.
8. Flags were assumed to carry across subcommands; `codex exec fork` rejects `-s` and takes
   `-m`. Captured stderr found it, discarded stderr had hidden it twice before.
9. The first Codex fork cells re-scanned the files instead of using inherited context, so
   they measured re-derivation, not inheritance. Removing the files from the working
   directory forced the intended path.
10. Three canary questions named the string they were asking about, so a YES proved nothing.
    Only the question that asked for a *list* — which the prompt did not contain — carried
    evidence. This one recurred three times before it was noticed.
