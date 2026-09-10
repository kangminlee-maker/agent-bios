---
created_at: 2026-08-06T17:27:00+09:00
head: 4716f8f
kind: design
supersedes: none
---

# Half the always-loaded corpus is one domain's inline rules, and the layer that could carry them free is unused

The forcing case, from the author: the deployed global is builder-centric, so non-builder work
pays for rules it will not use — and for software engineering the repo's own `AGENTS.md`
governs anyway, so the global either duplicates it or argues with it.

Everything below is measured at `4716f8f`. Nothing here is decided; the per-rule disposition is
a human judgement and this exists to make it a cheap one.

## What is actually in the always-loaded layer

```bash
python3 -c "import json,collections; d=json.load(open('compose/domains.json'));
print(collections.Counter(e.get('tier') for e in d['bullets']))"
```

113 bullets assemble for the full selection. **`core` — the tier that means universal — is 25.
`builder-base` alone is 56.** The rest: `llm-pipeline-dev` 15, `multi-agent-orchestration` 9,
`visualization-docs` 7, `office-work` 1, plus one never-assembled `env-personal`.

Inside those 56:

| section | bullets | guide that already exists |
| --- | --- | --- |
| Concept Economy | 16 | **none** |
| Coding Guidelines | 14 | `coding-staged-workflow.md` |
| Verification Discipline | 13 | `review-request.md` |
| Tooling and Operational Safety | 7 | `tooling-gotchas.md` + the PreToolUse hook |
| Documentation Hygiene | 6 | `implementation-map.md` |

**Four of the 56 are guide pointers. Fifty-two are the rule itself, inline, up to 829 characters
each.** The router pattern this corpus is built around is used four times in its largest domain.

## The criterion is already written, and it is not being applied

> A rule earns global placement only if it must work **even when the agent fails to recognize
> the situation**. A rule whose failure mode is recognition failure belongs behind a pointer.

Applied to the five sections: Concept Economy fires when you name something, Coding when you
code, Verification after you change something, Documentation when you write docs. All four are
situations an agent can recognize — 49 bullets that the criterion sends behind a pointer.

The seven that survive it are the Tooling traps, because an unknown trap is exactly what you
cannot look up. And those seven already have the cheapest carrier in the stack.

## Correcting a wrong turn taken while drafting this

An earlier version of this analysis proposed moving the trap rules **into** the hook. That is
wrong twice over.

It is wrong because the hook is Claude-only, so "move" would delete the rule for Codex. And it
is wrong because it misreads what the hook is: `claude/hooks/tooling-gotchas-hook.py` says in
its own docstring that message text *derives from* `claude/guides/tooling-gotchas.md` — the
guide is the authority, the hook is a projection of it, and the guide mirrors to
`codex/guides/`. `SURFACES.md` states the rule directly: *"Claude-only, so anything admitted
here needs a guide fallback for Codex."* The fallback is not missing. The hook is an
accelerator, and nothing needs to move into it.

What survives the correction is the real gap, and it is not about the hook at all.

## The model-agnostic layer nobody is using

The placement framework ranks **Enforcement** first, above gates and hooks, for one stated
reason: *owned scripts/wrappers/settings make the mistake impossible or the right way the
default — reaches ALL consumers.* It is model-agnostic because both agents run the same shell
and the same `git`; it costs zero tokens; and it does not depend on recognition, which is the
property the guide layer cannot provide.

Three of the seven trap rules dissolve into a default:

| trap | default that removes it |
| --- | --- |
| `git pull` into a dirty worktree | `pull.ff = only` |
| `$?` after a pipeline | `set -o pipefail` |
| `grep` misreading text as binary | a `grep` that passes `-a`, or `rg` ahead of it on PATH |

The other four cannot be defaulted away, and should not be: `git diff A..B` and
`git checkout <path>` are valid commands whose damage comes from meaning the other one, and a
default that blocks them breaks correct work. Those stay guide-carried with the hook in front.

**None of the three defaults is deployed today.** `launch/agent-launch.zsh` is 38 lines and its
only behaviour is two `unalias` calls; there is no `pipefail`, and `pull.ff` is unset. So the
same trap is currently stated in three places — global bullet, guide, hook — while the layer
that could stop it being a trap at all sits empty.

## Is everything else consumed where it sits

Reachability is fine and is not the problem:

```bash
# every guide, and who points at it
```

All fourteen guides are pointed at — eleven from the global, `llm-capability-boundary`'s
`-examples` and `-patterns` from the parent guide (a legitimate depth chain), and
`session-distill-workflow` from the launch preset alone, which is right because it is
`audience: author` and withheld from installs. No orphans. The three tier agents are referenced.

So the sweep's question is not "does anything read this". It is the sharper one: **is this in
the cheapest layer that still fires on time?** Today the answer for 52 bullets is no by the
corpus's own rule, and for three traps it is no by two layers.

## Options

| | approach | what it costs |
| --- | --- | --- |
| **A** | inline rules move behind the pointers that already exist | fires only on recognition; one guide must be written |
| **B** | a project template written by `init` | reaches only repos that ran it, duplicates, drifts |
| **C** | split `builder-base` into a thin core and a guide-carried depth | same as A, expressed in domains |
| **D** | ~~move traps into the hook~~ | withdrawn above |
| **E** | push what can be defaulted into Enforcement | changes behaviour of existing scripts; needs care |

**A + E.** C restates A in domain vocabulary and adds a domain without adding a mechanism. B is
the wrong surface for universal discipline — it cannot reach a repo that never ran `init`, so it
cannot replace the global; it is the right surface for repo-specific tailoring, which is a
separate decision and should not be settled by this one.

The blocker on A is that **Concept Economy has no guide**, and it is the largest block at 16.
The other four sections are "delete the inline copy, keep the pointer"; this one is "write the
guide first".

## What has to be decided by a person

Which of the 52 must survive recognition failure. That is not derivable — it is a judgement
about how this corpus is actually used, and the sweep exists to put each bullet in front of that
judgement once.

## Risks to carry into execution

`set -o pipefail` changes the exit status of existing pipelines and can turn working scripts
red. It is a behaviour change to a shared environment and belongs behind a default-off opt-in
until proven over this repo's own scripts — the corpus says as much about risky changes, and
this is one.

`pull.ff = only` and a `grep` shim are narrower but still ambient: they change what a command
does without the caller asking. Each needs to be reversible and visibly declared, not quietly
installed.

## Entry conditions

Not blocked. The measurement above is the input the sweep needs; the first executable step is
writing the Concept Economy guide, because it is the one piece of A that cannot be done by
deletion.
