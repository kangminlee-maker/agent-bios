Criterion: AI workbench / harness

Role: independent reviewer of an EXPERIMENT DESIGN. You have no prior contact with this
repository or its authors. Judge only what is in this packet.

Goal: find every place where this design, implemented as written, would emit a signal that
LOOKS TRUE AND IS FALSE — a cost figure attributed to the wrong cause, a control that cannot
fire, a denominator that is not pinned, a comparison made without a common basis, a
threshold that decides the wrong way on the evidence it would have. Being wrong is not the
defect; being wrong while looking right is.

Success criteria: every finding states (1) the exact input or condition, (2) the signal the
design would emit, (3) what the truth would be instead, (4) an anchor — the section heading
and a verbatim quote of the line. A finding without a failure path is not a finding; say
"unverified" as a boundary note instead. An empty result must list what you checked.

Defect classes — exactly one per finding:
  false_signal   (stop-relevant) a signal that would look true and be false
  detected_miss  a false positive the design itself would catch — this is the harness working

Severity floor: medium. Do not write a finding you would rate low; it will be discarded
unread. Do not write anything phrased as "watch", "consider later", "document" — carry-forward
findings are discarded too. Ask only for what must change in THIS design before it runs.

Stage: this is a PRE-IMPLEMENTATION design. Missing implementation is not a defect. The
harness it extends exists (an excerpt is bundled); the design's claims about that harness
ARE reviewable against the excerpt.

Target revision: design file sha256 c41669f13cb1. Findings anchor to its section headings and
verbatim quoted lines, not to line numbers.

Goldens for this criterion (verbatim from the criterion's owner; use them to classify at
the boundary):
  + a shell test runner received one nonexistent path, so every run exited 1 and every
    mutation reported KILLED — a green instrument that never ran its subject. (measured)
  + a test-inventory grep matched only one naming shape and missed every parameterized
    name; three reviewers judged a populated file empty — nothing tied the denominator
    to the source's own count. (measured)
  + a negative control kept passing after a faithful revert of the fix it was written
    against — a guard satisfied by an absence. (measured)
  + a review round returned "clean" with no receipt that the declared packet was
    dispatched on the exact seat — false_signal although nothing observed was wrong:
    what is refused is absence of proof, not proof of falsity. (constructed)
  − one reviewer over-classed an item; another lens plus measurement filtered it — the
    harness caught it, so it worked: detected_miss, not a defect. (measured)
  − five review rounds returned 8 → 9 → 10 → 5 → 12 findings and every count was true.
    A truthful unpleasant signal is not a false signal. (measured)
  ± a surviving mutation proved equivalent — the platform already normalized what the
    mutated guard checked. A harness that auto-reads "survived = gap" has a defect in
    that rule. (measured)

Rubric — check each, and report what you checked even when you find nothing:
  R1 Attribution: could any cell show a cost difference whose cause is not the seat?
  R2 Common basis: is every compared pair on the same units, denominators, population?
  R3 Controls: can each named control actually fire on the failure it names? Would any
     pass vacuously?
  R4 Thresholds: given the noise the design itself reports, can the pre-registered
     thresholds decide wrongly?
  R5 Claims about the bundled harness and prior records: is any claim the design makes
     about them false on the bundled text?
  R6 Vendor facts the design cites: are any internally inconsistent or misapplied in the
     cell design? (You cannot fetch; judge consistency and application only.)

Output: JSON conforming to the schema you were given. Nothing else.

================================================================================
TARGET — the design under review (sha256 c41669f13cb1)
================================================================================
---
created_at: 2026-09-03T22:15:00+09:00
head: a477bcc
kind: design
---

# Tier economics for write-dominated work: experiment design

## Why this exists

`2026-09-02T1130--ff09dd5--spawn-economics-measured.md` is being quoted as "delegation
has no cost advantage, so the cheap tiers have no basis." Its own Limits clause is
narrower than that in three ways at once, and every one of them cuts against the
quotation:

> One task shape (**mechanical scan**), one host, `medium` effort, headless `-p`
> throughout.

- **Shape.** The task was read-only: report every JS function with more than three
  parameters. The subagents used `Read` and `Bash` and nothing else. A scan is
  input-dominated, and the price gap between tiers is widest on **output** tokens — so
  the one shape measured is the shape least able to show a cheap seat's advantage.
- **Seat.** The 150-file pinned cell used **sonnet**. There is no cheap-seat cell above
  60 files, and the single cheap-seat cell (60 files, N=2) is the only saving anywhere
  in the table: −9%. The headline is a statement about mid-tier children.
- **Purpose.** `claude/agents/workhorse.md` is the only spawn target with no
  `disallowedTools` — the write-capable seat. Its stated purpose is bulk bounded
  implementation. The experiment never asked it to write anything.

So the supported claim is: *no cost advantage for delegating a read-dominated mechanical
scan of ≤150 files to a mid-tier child on Claude.* That is not a basis for deleting the
write-capable seats.

One finding of that record does survive untouched, because it is about routing behaviour
rather than price: **unpinned delegation escalated the child's tier as the task grew**
(60 files → `Explore`/opus, 150 → `Explore`/opus·sonnet), producing +57–73%. A gate that
names a seat cannot know the work's size or its output share.

## The decision this feeds

Whether agent-bios ships cheap seats (`workhorse`, `sweep`) as spawn targets at all, and
if so, what a routing rule may say about them. Deletion is the expensive direction: it
takes `agent-launch.toml` bindings, `TIER_ORDER`/`SPAWNABLE_TIERS`, the agent
definitions, the deployed global, `cli-multi-model-workflow.md`, and a full recapture of
`gates/goldens/review-matrix.json`, whose projected argv carries the tier names byte for
byte.

## The question

> For **write-dominated bounded work**, does pinning a spawn to a cheaper seat cost less
> than doing the same work inline — **at equal or better verified quality** — and at what
> size does the sign change?

Falsifiable, decision-linked, and it names the quality condition, because a cheaper wrong
answer is not cheaper.

Wall-clock is collected alongside cost. Parallelism and context isolation are the two
benefits the corpus claims for these seats and **neither has ever been measured here**;
wall-clock is free to collect in the same runs and settles one of them.

## What already exists, and the one thing that does not

`benchmarks/` is an instruction-behaviour harness, not a cost harness, but most of what
this experiment needs is already built there:

| Need | State |
| --- | --- |
| Two-host dispatch, model + effort pinned per call | `dispatch.py` `command_for`, `dispatch` |
| **Proof the child ran on the pinned seat** | `seat_problem()`, `codex_seat_from_rollout()` — reads the child's own rollout header |
| Writable fixtures, snapshot-restored per response | `run.py` postcondition path — "the agent's answer is the file it did or did not change" |
| A known-bad probe per check | `naive_edit`: planted into a pristine copy, the check must report MISS "or it is not checking" |
| Claude cost | `_parse_claude` reads `total_cost_usd`, and already handles both JSON shapes the binary emits |
| **Codex cost** | **absent.** `_parse_codex` returns `cost_usd: None` and extracts no token counts at all |

The Codex gap is the blocking one, because the objection that prompted this experiment is
specifically about GPT pricing — sol against luna is where the ratio is largest. Stage 0
below exists only to close it.

## Design

### Task

**N bounded edits to an existing codebase**, each with a failing test that must pass and
an out-of-scope regression check that must keep passing. This exercises the workhorse
contract as written ("Preserve out-of-scope behavior", "Stage output for the main's
acceptance") rather than a greenfield proxy, and it is output-dominated: the billed work
is code the agent writes.

A **difficulty ladder** rather than one difficulty, because the answer a routing rule
needs is a frontier, not a scalar:

- **L1** — mechanical edit, one call site, no judgement (rename, guard, boundary fix).
- **L2** — small algorithm inside a frozen interface.
- **L3** — edit requiring a read of an adjacent module to avoid breaking it.

Fixtures are generated per repetition with run-unique identifiers, and the tests live
outside the working directory. Both rules come from the prior record's instrument
errors: cells that re-scanned the files measured re-derivation rather than inheritance,
and canaries that named the string they asked about proved nothing.

### Cells

| Axis | Values |
| --- | --- |
| Arm | inline · delegated-cheap (effort low) · delegated-cheap (effort high) · delegated-mid · fork-same · fork-cheap (Codex only) |
| Size | N = 10 · 40 · 160 items |
| Difficulty | L1 · L2 · L3 |
| Host | Codex (GPT) first, Claude second |

**Why six arms.** The first three arms are all *isolated spawns with a packet*: the main
writes a brief at its own price, the child pays a cache write for the corpus, and the
main reads the report. The two fork arms hold the other side of that trade — no brief to
compose, the parent's context inherited, and a cache **read** instead of a write when
the model is the parent's. The effort-split pair separates the two variables a tier
bundles. Each of these was raised as a distinct question and they share one fixture and
one baseline, so running them apart would build both twice.

**fork-cheap exists on Codex only.** Official Claude Code docs: a fork "inherits the full
conversation history, system prompt, tools, **model**, and prompt cache" — a fork onto a
cheaper model is not a thing Claude Code offers. The prior record's haiku `--fork-session`
cell was a *session* fork, a different mechanism. On Codex, `spawn_agent` with
`fork_turns: "all"` (the default) and a different model is the cheap-fork cell, and it
is a cache-write cell by construction since the cache is keyed per model.

**Fan-out is cheaper than N writes on Claude.** The official doc states that in a
fan-out "Claude Code briefly delays secondary agents so their initial requests can reuse
the prefix cached by the first agent" — so N parallel spawns cost one write and N−1
reads, not N writes. The parallel arms record `cache_creation` per child to confirm it.

Staged, because the full cross is unaffordable and the discriminating case is known in
advance:

- **Stage 0** — teach `dispatch.py` to read all five Codex token kinds (it reads none
  today); split Claude's `cache_creation` by TTL; build the price table; run the
  instrument controls below. Two more controls come from the official-doc cross-check:
  (a) **Codex child cache key.** `client.rs` derives a subagent's `prompt_cache_key` as
  `"{source}:{parent_thread_id}"` — the child inherits the parent's key — yet the prior
  record measured only 14–18% cache reuse on `codex exec fork`. Either `exec fork` and
  `spawn_agent` are different paths, or the key is shared and the prefix is not. Read
  `cached_input_tokens` on a `spawn_agent` child's **first** request before any Codex
  fork cell is trusted. (b) **Claude subagent TTL.** Confirm a child's writes land in
  `ephemeral_5m`, not `ephemeral_1h`, from a real child transcript. No cell counts until
  these pass.
- **Stage 1** — Codex only, 6 arms × 3 sizes × L2, **N=3**. Codex first because the
  price ratio is largest there (16.7× on output), so an effect absent here is absent
  everywhere. 54 runs.
- **Stage 2** — only if Stage 1 shows an effect: confirm at **N=5**, add L1 and L3, add
  Claude.

N=3 is deliberately not enough to conclude from. The prior record read N=2 as a 19% and
36% saving that N=5 erased, and set the rule this follows: **treat any figure under
roughly 20% as noise unless its cell is N=5.** Stage 1 is a screen, not a verdict.

### Common basis

The two hosts are not billed alike, and comparing them without fixing that is the trap
the corpus names before any comparison.

- **Claude** — `total_cost_usd`, measured, per run — AND the token breakdown, because
  the dollar alone cannot say which of the five kinds below moved.
- **Codex** — an OAuth subscription pays no per-run dollar. Tokens by kind are measured;
  dollars are then **modelled** from the published rates below. Every Codex figure is
  labelled modelled and is never mixed into a mean with a measured Claude figure.

**Five token kinds, never three.** Cross-checked against the official usage objects and
pricing pages on 2026-09-03 (this session's own transcript, a live Codex rollout,
`platform.claude.com/docs/en/about-claude/pricing`, `developers.openai.com/api/docs/pricing`):

| Kind | Claude field | Codex field | Price vs base input |
| --- | --- | --- | --- |
| uncached input | `input_tokens` | `input_tokens − cached_input_tokens` | 1× |
| cache read | `cache_read_input_tokens` | `cached_input_tokens` | 0.1× (0.025× on Fable 5.1) |
| cache write | `cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` | `cache_write_input_tokens` | **1.25× (5m) / 2× (1h)** Claude; 1.25× GPT |
| visible output | `output_tokens − thinking` | `output_tokens − reasoning_output_tokens` | output rate |
| thinking | `output_tokens_details.thinking_tokens` | `reasoning_output_tokens` | **billed as output** (both vendors, verbatim) |

Cache read and cache write are opposite-signed costs and were previously folded into one
"cached" column. That fold hides the largest fixed cost of a spawn: the prior record
measured subagent injection at `cache_read: 0`, and the official Claude Code doc confirms
a non-fork subagent "warm[s] its own cache … rather than reading the parent's cache" —
**a spawn is, by construction, a cache-write event.**

Thinking is separated because it moves with `effort`, not with the model — a live Codex
rollout today showed 28,817 reasoning of 50,617 output tokens (57%). A tier is a
model+effort pair, so an undifferentiated output column cannot say whether a cheap seat
was cheap because of its model or its effort. The design adds an effort-split arm for
that reason.

**Host asymmetries the same cell design must not be projected across:**

- **GPT long-context cliff.** Above 272K input tokens the *whole request* is billed at
  2× input / 1.5× output (`gpt-5.6-luna` model page, verbatim). Claude 4.6+ bills the full
  1M window at standard rates. A live Codex rollout today sat at 266,137 input — 6K under
  the cliff. Every Codex run records its peak input; a run that crosses 272K is flagged,
  and a saving that appears only in flagged runs is a cliff effect, not a seat effect.
- **Prior-turn thinking is re-billed as input** (both vendors). This taxes long inline
  runs and not short delegated ones, structurally — cache hits absorb most of it, but
  the first write of each turn's thinking is at full rate.
- **Cache TTL.** Claude Code subagents use a **5-minute TTL**; the main session's usage
  here shows `ephemeral_1h`. A subagent's writes are cheaper (1.25× vs 2×) but expire
  sooner, so a long-running child that pauses >5m between requests re-writes.

**Rate table (official, 2026-09-03, $/MTok — input / cache write / cache read / output):**

| Seat | Rates | Cache write note |
| --- | --- | --- |
| claude-fable-5 | 10 / 12.5 (5m) · 20 (1h) / 1 / 50 | |
| claude-opus-5 | 5 / 6.25 · 10 / 0.5 / 25 | |
| claude-sonnet-5 | 2 / 2.5 · 4 / 0.2 / 10 | |
| claude-haiku-4-5 | 1 / 1.25 · 2 / 0.1 / 5 | |
| gpt-5.6-sol | 4 / 5 / 0.4 / 20 | ×2 input, ×1.5 output above 272K |
| gpt-5.6-terra | 2 / 2.5 / 0.2 / 12 | same cliff |
| gpt-5.6-luna | 0.2 / 0.25 / 0.02 / 1.2 | same cliff |

Output-rate ratio, top seat to cheapest: **GPT 16.7×, Claude 5×.** That ratio is why the
GPT host runs first.

Report cost per **verified item** (cost ÷ items passing), never per run: an arm that
attempts fewer items must not look cheaper for it.

### Controls

The result is worth nothing without these, and they run before the cells.

1. **Known-opposite control.** The 6.7× spread between seats for whole-session work is
   already established. Run it first: if the harness does not reproduce a large gap
   where one is known to exist, the harness is broken and no cell means anything.
2. **Denominator assertion.** Every run reports `items_attempted`; the harness FAILS the
   run when it is not N, rather than printing it. Agreement with expectation is exactly
   when a printed number goes unread.
3. **Seat receipt.** `seat_problem()` on every run. A run whose child answered on a seat
   other than the pinned one is **discarded and reported**, never averaged in — that
   escalation is the confound that produced the +57–73% row.
4. **Zero detection.** A run reporting $0, zero output tokens, or zero items is an
   instrument failure, not a cheap run — and so is a null `thinking_tokens` /
   `reasoning_output_tokens` or a null cache-write field: that is the parser not
   reading the kind, not the kind being absent.
4b. **Cliff guard (Codex).** Peak input per run is recorded; a run above 272K input is
   flagged and excluded from the seat comparison, because its whole request was billed
   at the long-context multiplier.
5. **Known-bad probe per check.** Following `naive_edit`: plant the wrong edit into a
   pristine fixture and require the checker to fail it. A checker that has never failed
   is not checking.
6. **Fresh fixture per repetition**, so cross-run caching cannot flatter a later cell.

### Pre-registered thresholds

Declared before running, because the prior record's largest error was reading a small
sample and reporting the direction it happened to show.

- **Keep the cheap seats** if delegated-to-cheap beats inline by **≥25%** cost per
  verified item at equal-or-better pass rate, at any tested size, on either host.
- **Delete them** if no delegated arm beats inline by **>20%** at any size on either
  host, at Stage 2 sample sizes.
- **Anything between is inconclusive, and the seats stay.** The default follows
  reversibility, not preference: keeping is a no-op, deleting costs a golden recapture
  across every setup/host/family combination.

## What this cannot answer

Context isolation — a large log staying out of the main's window — is not a cost or a
wall-clock quantity and no cell here measures it. It stays an argued benefit.

Nor does this measure quality on work with no machine-checkable done-when, which is most
of what a main context actually does. The result generalises to bounded, verifiable
implementation and no further.

## Note on how this design was produced

The corpus asks for dual-provider frontier drafts on a design question of this size.
Subagents are disabled in this session, so this is a single perspective and has had no
independent review. Treat the threshold values in particular as proposals.


================================================================================
BUNDLE 1 — the prior measurement record the design narrows (cited as evidence)
================================================================================
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


================================================================================
BUNDLE 2 — the cross-host record (fork cells, corpus-exclusion levers)
================================================================================
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


================================================================================
BUNDLE 3 — the two spawn-target definitions the design says it exercises
================================================================================
--- claude/agents/workhorse.md ---
---
name: workhorse
description: WORKHORSE tier — bounded implementation, fixes, tests, and per-item judgment. Spawn decision-complete work with frozen scope/interfaces and a machine-checkable done-when; two or more independent items spawn in parallel.
model: claude-opus-5
effort: medium
---

Complete one bounded implementation, fix, or per-item judgment from a packet naming objective, frozen scope and inputs, allowed actions, output, done-when, and verification. Preserve out-of-scope behavior; batch independent reads; escalate missing decisions or authority instead of resolving them. Stage output for the main's acceptance — no external irreversible actions (push, install, credential, or remote mutation). Run the narrowest reliable changed-path check. Report: status, files_or_items_touched, evidence, verification or gap, risks_or_escalations.

--- claude/agents/sweep.md ---
---
name: sweep
description: SWEEP tier — cheap wide scans, candidate finding, mechanical checks, and closed-form summaries. Spawn when each item applies one explicit rule; ambiguity returns as an exception, never resolved.
model: claude-haiku-4-5
effort: low
disallowedTools: [Edit, Write, NotebookEdit]
---

Run one clear repeatable scan, candidate pass, mechanical check, or closed summary over exact inputs, rules, stop condition, and output shape. Read-only: do not edit, broaden scope, choose architecture, or seek authority. Parallelize independent reads. Surface ambiguity as an exception instead of inferring intent. Report: status, the non-empty items_checked, findings with proving evidence or command, risks_or_escalations.


================================================================================
BUNDLE 4 — the harness parsers the design says it must extend (benchmarks/dispatch.py, excerpt)
================================================================================
def _parse_claude(stdout: str) -> dict:
    """claude --output-format json emits EITHER a bare result object or an array of
    events ending in one — measured both shapes from the same binary on 2026-08-26
    (the array appeared when a rate_limit_event accompanied the result). A parser
    that knew only one shape would have turned an ordinary run into a defect."""
    payload = json.loads(stdout)
    events = payload if isinstance(payload, list) else [payload]
    if not events:
        raise ValueError("claude JSON output is empty")
    final = events[-1]
    models = sorted((final.get("modelUsage") or {}).keys())
    return {
        "session_id": final.get("session_id") or events[0].get("session_id"),
        "models_reported": models,
        "result_text": final.get("result") or "",
        "cost_usd": final.get("total_cost_usd"),
        "host_error": bool(final.get("is_error")),
    }


