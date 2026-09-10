---
created_at: 2026-09-02T18:15:00+09:00
head: ff09dd5
kind: design
supersedes: 2026-09-02T1740--ff09dd5--spawn-across-hosts.md
---

# Spawn rule wording — the candidate diff

Two records measured the spawn policy; this one turns the measurements into text. Nothing
here is applied. Whether a rule earns its place in the deployed global is the one thing
`AGENTS.md` §3 names as unguarded on purpose — a person decides.

Four measured facts drive every change below:

1. The always-spawn Independence clause produced **0 spawns in 3 gate-triggering situations**,
   with a positive control proving the mechanism works in that dispatch mode.
2. An in-process spawn **inherits the whole instruction corpus** — verified on both hosts, one
   with zero tool calls. Isolation is conversational, not epistemic.
3. Delegation is **not a cost lever**: pinned, it is break-even (+0.3% at 150 files, −9% at 60,
   both inside a spread that ran $0.688–$1.260 across five repetitions); unpinned it costs
   **57–73% more** than inline, because the agent escalates the subagent tier as the task grows.
4. Fork cache reuse is **host-asymmetric**: Claude 98.9% same-model / 0% cross-model, Codex
   14–18% regardless.

## Global — `claude/CLAUDE.md`, Multi-Model Workflow

### Change 1 — Independence

Before:

> Independence: verifying or reviewing your own work always spawns, and you raise it yourself —
> before presenting a load-bearing conclusion or taking an irreversible step, propose the
> cross-check unprompted; the user should never have to ask for it.

After:

> Independence: before a load-bearing conclusion or an irreversible step, propose the
> cross-check unprompted; the user should never have to ask. An in-process spawn inherits your
> corpus — a fresh conversation, not a fresh perspective — so when perspective is the point go
> outside the process, different provider first, with a blind packet and never your draft
> conclusion.

What it displaces: `always spawns`, which measured as never firing, and the Escalation clause's
blind-packet parenthetical, which becomes a restatement once Independence carries the
requirement. Escalation then reads `… spawns a bounded FRONTIER judgment with a blind packet and
a pre-noted change condition`. Net change is roughly two words.

Why the sentence moved rather than being deleted: fact 2 is the reason the rule existed. This
repo's recorded failure is agreeing-and-wrong self-verification, and a same-corpus subagent is
exactly the mechanism that reproduces it. The rule was not wrong about the danger; it named a
remedy that does not reach it.

### Change 2 — the down-spawn criterion

Before:

> Down-spawns carry a machine-checkable done-when on decision-complete work with staged output
> (no external irreversible actions) and briefing-plus-verifying clearly cheaper than doing.

After:

> Down-spawns carry a machine-checkable done-when on decision-complete work with staged output
> (no external irreversible actions) and a named tier — delegation buys context, not price, and
> an unpinned tier escalates with task size.

What it displaces: `briefing-plus-verifying clearly cheaper than doing`, a criterion fact 3
shows is unavailable — the best measured case is break-even and the default is a surcharge.
`a named tier` is the intervention that actually removes the surcharge. Net +13 words, in
exchange for deleting a false test.

Cost is deliberately phrased without a ratio. Claude's 1:50 cache-to-output price ratio is not
a Codex fact, and Codex runs on a subscription where the scarce resource is rate limit.

## Guide — `claude/guides/cli-multi-model-workflow.md`

The global carries the rule; the numbers and the host split belong here (§8).

**§When To Spawn, gate 1.** `Independence: verification or review always spawns; isolation is
the purpose.` → verification and review go **outside the process**; an in-process spawn isolates
the conversation and injects the full corpus, so it is a different conversation with the same
rules, learnings and blind spots. Rank by what it buys: different provider, then different
model, then a fresh process at the same model.

**§Delegation Mechanics**, new bullet: delegation is not a cost lever. On a mechanical scan at
60 and 150 files, a pinned down-spawn was break-even with inline and an unpinned one ran 57–73%
dearer, because the agent escalates the subagent tier as the task grows. Pin the tier; delegate
to keep a large working log out of the main.

**§Model Switching And The Prompt Cache**, new bullet: forking preserves conversation content on
both hosts and the cache on only one. Claude `--fork-session` at the same model reuses ~99% of
the inherited context and ~0% across models; Codex `exec fork` re-sends regardless (14–18%). So
"fork without changing the model" is a Claude rule; on Codex a fork is priced like a fresh
dispatch.

**§Review Independence**, extending the isolation bullet: a same-process subagent has a fresh
*conversation* and the same corpus. That clears conversation-level contamination and nothing
above it, so it lands on `perspective_floor` and can never earn a rung.

**Corpus exclusion**, one bullet wherever host levers live: there is no per-spawn corpus
suppression on either host — the agent definitions carry model and effort, not scope. Excluding
the corpus is a process-level act (`claude --setting-sources ''`, or `CODEX_HOME` pointed at a
directory holding only `auth.json`) and it removes the tier agent definitions with it, so a
corpus-free reader and a pinned tier cannot come from one process. An emptied `CODEX_HOME`
without `auth.json` fails 401.

**§Evidence Base**, three rows:

| Evidence | Result / rule supported |
|---|---|
| 4 dispatches over 3 gate-triggering situations + positive control (2026-09-01) | the always-spawn Independence clause produced 0 spawns; de-minimis absorbed all three |
| 60/150-file mechanical scan, N=5 on load-bearing cells (2026-09-02) | inline $0.627→$0.919; pinned delegation $0.665→$0.921; unpinned +57–73%; tier escalates with size |
| fork cache reuse, both hosts (2026-09-02) | Claude same-model 98.9% / cross-model 0–26%; Codex 14–18% at any model — fork guidance is host-qualified |

## What is deliberately not changed

- The review ladder's ordering. Fact 2 explains *why* different-provider outranks
  different-model; it does not reorder anything.
- The Escalation, Parallelism and Residual-context gates. Nothing measured touches them.
- `Delegation=off` and the `SpawnGate` record line. The measurement makes the records more
  useful, not less.

## Open

Applying this closes F-16 by its fifth alternative — state the behaviour the gates produce.
Choosing instead to make the clause fire is still live and this draft does not foreclose it; it
would mean weakening the de-minimis escape, which is the clause that absorbed all three probes
and did so correctly each time.

Cross-provider review of this wording before it lands has not been run.
