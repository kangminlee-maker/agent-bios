---
created_at: 2026-09-02T11:30:00+09:00
head: ff09dd5
kind: review
supersedes: 2026-09-01T1612--ff09dd5--spawn-clause-does-not-fire.md
---

# Spawn economics, measured

Why an agent spawns is two questions, not one: **cost** (send decision-free work to a cheaper
tier) and **isolation** (get a context that does not carry the caller's frame). This record
measures both against the deployed corpus, with the third question the earlier record left
open — whether the always-spawn clause fires at all.

Every figure is from `claude -p --output-format json --permission-mode plan --model
claude-opus-5 --effort medium` against fixtures built for the run. Cost is the host's
`total_cost_usd`; the per-response `usage` object is NOT the session total and was not used
for any conclusion.

## The task

One explicit rule over N files: report every JS function declared with more than 3
parameters. Ground truth is generated with the fixture and kept outside it. This is the
decision-free shape the cost argument assumes — if delegation ever pays, it pays here.

## 1. Tier pricing is real

Whole session on one model, no delegation:

| Tier | Model / effort | Cost | Recall | FP |
| --- | --- | --- | --- | --- |
| SWEEP | `claude-haiku-4-5` / low | $0.097 | 100% | 0 |
| WORKHORSE | `claude-opus-5` / medium | $0.449 | 100% | 0 |
| HELM | `claude-opus-5` / xhigh | $0.648 | 100% | 0 |

Six runs, identical answers, **6.7× spread**. The 2026-07-26 attempt could not reach this
because it read organic traffic, where per-task cost across tiers is routing-confounded and
the tier ladder is injected at CLI process launch. Dispatching the same task at each seat
sidesteps both.

## 2. Delegation does not deliver that pricing on its own

Main on `claude-opus-5`, delegating the same task. Baselines and the pinned cells are N=5;
the judgment cells are N=2:

| Files | Inline (N=5) | Delegated, tier by judgment | Delegated, tier pinned |
| --- | --- | --- | --- |
| 60 | $0.627 | **$1.085 (+73%)** | $0.571 sweep (**−9%**) · $0.665 sonnet (+6%) |
| 150 | $0.919 | **$1.439 (+57%)** | $0.921 sonnet (**+0.3%**) |

The cause is in what the agent chose, not in the pricing:

| Files | `subagent_type` chosen | Model it ran on |
| --- | --- | --- |
| 15 | `sweep` | `claude-haiku-4-5` |
| 60 | `Explore` | `claude-opus-5` |
| 150 | `Explore` | `claude-opus-5` / `claude-sonnet-5` |

The task's nature never changed — one rule, no decisions. Only the file count grew, and the
agent escalated the subagent tier with it. Delegation then costs **more** than doing the work
inline. Pinning the tier removes that surcharge; the next section shows it does not turn into
a saving.

## 3. Delegation does not save money at any size tested

A first reading at N=2 showed pinned delegation at −19% (60 files) and −36% (150), and a cost
curve that stayed flat while inline grew. Re-running the four load-bearing cells to N=5
removed all three:

| 60 → 150 files | Growth |
| --- | --- |
| Inline | $0.627 → $0.919 (**+46%**) |
| Delegated (`sonnet` pinned) | $0.665 → $0.921 (**+39%**) |

The curves are the same shape. Within-cell spread is what made the smaller sample look
otherwise — inline at 150 files ranges $0.688 to $1.260 across five runs.

**Cost is therefore not a reason to delegate this workload.** The best measured case is
break-even with the tier pinned; the default, unpinned, is a 57–73% surcharge. Whatever
justifies a spawn here, it is context and isolation, not price.

## 4. Quality risk is in the strategy, not the tier

| Run | Subagent tools | Recall |
| --- | --- | --- |
| haiku, 60 files | `Read` × 60 | 99.0% |
| haiku, 60 files | `Bash` × 2, `Read` × 1 | 100% |
| sonnet, 60 files | `Bash` × 3, no `Read` | 96.9% |
| sonnet, 60 files | `Bash` × 3, no `Read` | 90.8% |
| sonnet, 150 files (N=5) | `Bash`, no `Read` | 100% |

Only the 60-file sonnet cell lost items; every 150-file run was exact. So this is a real but
narrow observation, not a rule about the tier or the strategy.

The runs that scripted the scan dropped items **scattered across the file range**, with
nothing under `EXCEPTIONS:`. A complete-looking list was up to 9% short, and no ground truth
means no way to know. Strategy varies within a model too — the two haiku runs differed — so
this is not a tier property.

A delegated result therefore needs a completeness check the caller can evaluate. The corpus
already asks for a `bounded report contract`; what it does not say is what to reconcile
against.

## 5. Subagent fork does not exist; session fork does

`subagent_type: "fork"` was requested four times. It never forked: the subagent ran
`claude-haiku-4-5` rather than the parent's model, received a ~550-character brief, was told
to read the files itself, and did. `fork` is absent from the session's own `agents` list.
The capability catalog at `cli-api-adaptor/.../runtime-capability-catalog.md` carries four
fork entries and all four are session/thread lifecycle — `codex exec fork`, `codex fork`,
`thread/fork`, and Claude's `--fork-session`. There is no subagent-fork command.

`--fork-session` is real (CLI 2.1.258), and its economics turn entirely on the model:

| Fork target | Total | Context cost | cache_read | cache_write | Reuse | Recall |
| --- | --- | --- | --- | --- | --- | --- |
| `claude-opus-5` (same) | $0.159 | $0.035 | 61,013 | 665 | **98.9%** | 100% |
| `claude-sonnet-5` | $0.276 | $0.207 | 18,666 | 53,777 | 25.8% | 98.0% |
| `claude-haiku-4-5` | $0.318 | $0.274 | 0 | 72,924 | **0.0%** | 84.7% |

Same model: the KV cache carries and context is effectively free. Change the model and the
cache is void — caches are per-model — so the inherited conversation is re-sent at creation
price.

The sonnet row's 25.8% is not a fork benefit. Independent sonnet subagents in the same
fixture measured 32.2% and 34.2%, and the first sonnet run of all measured 0%. What is being
reused is that model's own standing prefix (system prompt plus corpus, ~19k), which any spawn
of that model gets. Haiku, cold in this project, shows the uncontaminated number.

**Forking to a cheaper model costs more than not forking**: haiku's fork ran 2× the
same-model fork ($0.318 vs $0.159) and 7.9× on context alone, while recall fell to 84.7%.
Cheaper per token, dearer in total, and less accurate.

## 6. Every spawn inherits the whole instruction corpus

A subagent asked to report its own loaded context, having made **zero tool calls**, named:

```
~/.claude/CLAUDE.md
~/.claude/central/bundle.md
~/.claude/personal/learnings.md
~/.claude/rules/context7.md
<project>/CLAUDE.md
```

and returned the deployed `agent-bios-bundle-rev` and a planted project canary. Injection was
19,360 tokens with `cache_read: 0`.

So an in-process spawn isolates the conversation and shares everything else: the rules, the
learnings, the priorities, and the blind spots. That is the mechanism behind the earlier
record's result — a verifier subagent would carry the same learnings that let the main catch
those defects inline, and would miss whatever they miss. This repo's review ladder already
ranks different provider over different model over higher effort; "same-corpus subagent"
appears nowhere on it, and this is why.

`--setting-sources` strips it, verified in both directions:

| Setting | Global corpus | Project `CLAUDE.md` | Injection | Cost |
| --- | --- | --- | --- | --- |
| (control) | `481cbf6f` | present | 25,960 | $0.279 |
| `--setting-sources project` | absent | present | 4,992 | $0.063 |
| `--setting-sources ''` | absent | absent | 4,737 | $0.060 |

It propagates to subagents: under `--setting-sources ''` a `general-purpose` subagent
reported NONE to all three questions, at 11,185 tokens of injection against the control's
21,926 (−49%, cost −68%).

**The lever has a cost of its own.** Agent definitions live in the same user scope, so
stripping settings also removes `sweep`, `workhorse` and `frontier` — the available types
fell from 15 to 5. A corpus-free spawn and a pinned tier cannot come from one process.

## What this changes

- **Delegating to save money does not work here.** Pinned, it is break-even; unpinned it is a
  57–73% surcharge, because the agent escalates the subagent tier as the task grows. If a
  spawn is worth making, the reason has to be context or isolation.
- Cost savings do not come from forking either. Same-model fork is for reusing an expensive
  context across follow-ups; cross-model fork is priced like an independent spawn without
  being one.
- Independence bought by an in-process spawn is conversational, not epistemic. Where the
  point is a different perspective, the corpus has to come off, and then the tier ladder does
  too.

## Limits

The four load-bearing cells are N=5; every other cell, including both fork tables and all
judgment-delegation rows, is N=2 and should be read as directional. One task shape
(mechanical scan), one host, `medium` effort, headless `-p` throughout.

Within-cell spread is large enough to invert a conclusion: inline at 150 files ran $0.688 to
$1.260 across five repetitions. The first reading of this experiment, at N=2, reported
savings of 19% and 36% that the larger sample erased, and a flat-slope result that did not
survive either. Treat any figure here below roughly 20% as noise unless its cell says N=5.

## Instrument errors made here

Three, all caught, worth repeating because each produced a confident wrong reading:

1. A spawn counter keyed on `Task` returned zero for every run. The tool is named `Agent`.
   The conclusion survived only because the full counter dict was printed beside it.
2. Splitting a response on `"EXCEPTIONS:"` truncated at a preamble that *mentioned* the
   heading, scoring 98 correct items as 0 and manufacturing a quality failure that was
   reported before being checked. Anchor the split to line start.
3. A fork/isolation check that searched the first message for `"function "` or `"mod0"`
   matched the brief itself and called all four runs forks. Fixture-unique identifiers
   settled it the other way.
4. The `EXCEPTIONS:` truncation returned a second time, on a run whose subagent printed
   `EXCEPTIONS: none` **above** its data. That scored 269 correct items as 0 and put a
   fabricated 80% recall into a reported table. Splitting on a section heading is the wrong
   shape entirely; parse the whole response and detect data inside the exceptions block
   instead.

`--output-format json` also emits a bare object rather than an array often enough to break a
parser that assumes one shape; `benchmarks/dispatch.py` already documents this.
