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

Target revision: design file sha256 (REVISION 3 — round 3 of review) 1d40701ca97d. Findings anchor to its section headings and
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

Provenance — this is round 3. Round 1's record (38 findings, answered by revision 2) is
BUNDLE 5 and round 2's record (15 findings, answered by revision 3) is BUNDLE 6. For every
finding, say which it is:
  caused        the defect exists BECAUSE of a change revision 3 made (name the change)
  surfaced      revision 3 made you look here, but the defect reproduces in revision 2 too
  pre_existing  present in revision 2, not addressed by revision 3
Do not re-file a round-1 or round-2 finding that a later revision addressed unless you can
show the fix did not close it — say what still fails. Round 2 ran on one seat; nothing in
BUNDLE 6 has been independently confirmed, so treat its dispositions as claims.

Output: JSON conforming to the schema you were given. Nothing else.


================================================================================
TARGET — the design under review, REVISION 3 (sha256 1d40701ca97d)
================================================================================
---
created_at: 2026-09-03T22:15:00+09:00
revised_at: 2026-09-04T07:40:00+09:00
head: 46959fd
kind: design
reviewed_by:
  - 2026-09-03T2320--a477bcc--tier-experiment-review-round-1.md
  - 2026-09-04T0725--46959fd--tier-experiment-review-round-2.md
---

# Tier economics for write-dominated work: experiment design

Revision 3. Revision 2 (sha256 `02e1ab995be7`) went through round 2 on one seat —
`gpt-5.6-sol`/max, hermetic; the second seat did not run, because every new `claude`
process on the machine lost its stored credential mid-session (the round record beside
this file says what was established and what was not). Fifteen findings, fifteen
accepted, two narrowed, none rejected. Six were caused by revision 2's own repairs — the
topology fix, the cliff repricing, the three-set denominator, the 40% relabel, the
one-sided bounds — which is round 1's lesson at one remove: a repair to a safeguard is a
safeguard. The largest finding is older than either revision and survived two seats in
round 1: **no arm ran the seat whose retention is being decided.** Round 3 must re-review
this revision at its own hash, on two seats, before Stage 0 is built.

## Why this exists

`2026-09-02T1130--ff09dd5--spawn-economics-measured.md` is being quoted as "delegation
has no cost advantage, so the cheap tiers have no basis." Its own Limits clause is
narrower than that in three ways at once, and every one of them cuts against the
quotation:

> One task shape (**mechanical scan**), one host, `medium` effort, headless `-p`
> throughout.

- **Shape.** The task was read-only: report every JS function with more than three
  parameters. The subagents used `Read` and `Bash` and nothing else. A scan is
  input-dominated, and the price gap between tiers on GPT is 20× on input and cache kinds
  and 16.7× on output — so a scan is not the least favourable shape for a cheap seat by
  rate alone; it is the least favourable because a scan's bill is dominated by *reading
  the same files at any seat*, which is work the seat's price barely moves.
- **Seat.** The 150-file pinned cell used **sonnet**. There is no cheap-seat cell above 60
  files. The 60-file cheap-seat cell is the only saving anywhere in the table (−9%), and
  the record is self-inconsistent about its sample size — §2 says "the pinned cells are
  N=5", Limits says "the four load-bearing cells are N=5; every other cell … N=2", and
  four load-bearing cells are inline 60/150 and sonnet 60/150. Raw runs do not survive.
  This design treats that cell's N as **unknown**, and nothing below rests on it.
- **Purpose.** `claude/agents/workhorse.md` is the only spawn target with no
  `disallowedTools` — the write-capable seat. Its stated purpose is bulk bounded
  implementation. The experiment never asked it to write anything.

So the supported claim is: *no cost advantage for delegating a read-dominated mechanical
scan of ≤150 files to a mid-tier child on Claude.* That is not a basis for deleting the
write-capable seat.

One finding of that record survives untouched, because it is about routing behaviour
rather than price: **unpinned delegation escalated the child's tier as the task grew**
(60 files → `Explore`/opus, 150 → `Explore`/opus·sonnet), producing +57–73%. A gate that
names a seat cannot know the work's size or its output share.

## The decision this feeds

Whether agent-bios ships **`workhorse`** — the write-capable seat — as a spawn target,
and what a routing rule may say about it.

**The shipped binding is not a cheap seat.** `launch/agent-launch.toml` at this HEAD binds
`workhorse` to `claude-opus-5 / medium` on Claude and `gpt-5.6-terra / high` on Codex —
the parent's own model at lower effort on one host, a mid seat on the other. Revisions 1
and 2 tested haiku and luna and called the result a verdict on `workhorse`; that verdict
would have been about a binding nobody ships. This revision splits the verdict in two
(*Pre-registered thresholds*): **retention** quantifies over the shipped binding, and the
cheap arms answer a different question — whether a *rebinding* would be justified.

**`sweep` is out of this experiment's scope.** It is read-only by definition
(`disallowedTools: [Edit, Write, NotebookEdit]`; "Read-only: do not edit"), so no
write-dominated cell can exercise its contract, and a verdict here that named it would be
grounded in cells it cannot run. Its fate needs a scan-shape experiment: the missing
cheap-seat cells above 60 files in the prior record, at Stage-2 sample sizes.

Deletion is the expensive direction: it takes `agent-launch.toml` bindings,
`TIER_ORDER`/`SPAWNABLE_TIERS`, the agent definitions, the deployed global,
`cli-multi-model-workflow.md`, and a full recapture of `gates/goldens/review-matrix.json`,
whose projected argv carries the tier names byte for byte.

## The question

> For **write-dominated bounded work**, does an isolated spawn pinned to the **shipped
> `workhorse` binding** cost less **than the same isolated spawn pinned to the parent's
> own seat** — at verified quality no worse than the margin **Δ** — and at what size does
> the sign change? Secondary: would a binding cheaper than the shipped one clear the same
> bar?

The comparator is **delegated-same**, not inline. Cheap-vs-inline confounds the seat with
the routing mechanism: a child has a shorter context, carries no prior-turn thinking, and
may reuse a fan-out prefix, and every one of those makes a delegated arm cheaper for
reasons a same-model spawn would deliver just as well. The seat effect is
arm-vs-delegated-same; inline is reported alongside as the reference the operator
actually faces.

**Δ is one named number.** Revisions 1 and 2 asked for "equal or better" quality while
KEEP accepted a pass rate up to 5 points worse — a rule that fires below the question it
answers is a false signal. The margin is now a single parameter, **Δ = 5 points**, written
into the question and the predicates alike. Δ = 0 is the strict reading and the operator
may tighten to it; that is a decision, flagged in the round-2 record rather than made
here.

Wall-clock is collected alongside cost. It answers nothing here — topology is held fixed
at one child per run, so parallelism is deferred to its own experiment (see *What this
cannot answer*) — but it is free, and a later design will want the baseline.

## What already exists, and what does not

`benchmarks/` is an instruction-behaviour harness, not a cost harness, but most of what
this experiment needs is already built there:

| Need | State |
| --- | --- |
| Two-host dispatch, model + effort pinned per call | `dispatch.py` `command_for`, `dispatch` |
| Proof the child ran on the pinned seat | `seat_problem()`, `codex_seat_from_rollout()` — reads the child's own rollout header |
| Writable fixtures, snapshot-restored per response | `run.py` postcondition path |
| A known-bad probe per check | `naive_edit`: planted into a pristine copy, the check must report MISS |
| Claude cost | `_parse_claude` reads `total_cost_usd` and handles both JSON shapes the binary emits |
| **Codex cost** | **absent.** `_parse_codex` returns `cost_usd: None` and extracts no token counts |
| **Child accounting** | **absent on both hosts.** `_parse_codex` reads the parent's `exec --json` stream; a `spawn_agent` child's usage lives in the child's own rollout. `_parse_claude` reads a session-level total — whether it includes children is corroborated only in use (the prior record's +57–73% surcharges came through it), never by a schema |

The last row is the blocking one. A harness that reads only the parent reports a delegated
run at roughly the cost of its brief, and a cheap child's entire bill becomes a "saving".

## Design

### Variables, named once

- **M** — items per run (the fixture's size). Values 10 · 40 · 160.
- **R** — repetitions per cell. Stage 1: 3. Stage 2: 5.
- **Δ** — the quality margin, in pass-rate points. 5.
- M and R are never both called N. A run's denominator is M; a cell's is R.

### Task

**M bounded edits to an existing codebase**, each with a failing test that must pass and
an out-of-scope regression check that must keep passing. This exercises the workhorse
contract as written ("Preserve out-of-scope behavior", "Stage output for the main's
acceptance") rather than a greenfield proxy.

**The M items are one bounded work unit, not M independent tasks.** They live in one
module family behind a shared interface, and later items depend on earlier ones. The
contract routes *two or more independent items* to parallel children, so an independent
batch measured on one sequential child would be measured on the wrong topology; a
dependent batch is the contract's single-dispatch case. Every verdict below is scoped to
that case, and the independent fan-out case is named under *What this cannot answer*.

**Output dominance is measured, not assumed.** "Write-dominated" is a claim about where
the bill lands, and an L3 edit that reads an adjacent module can be input-dominated in
fact. Every run records its cost share by token kind. The bill location is the
**output-priced share**: (visible output + thinking) × output rate ÷ modelled cost —
thinking is billed as output on both vendors, so a classifier that counts visible output
alone reports the opposite of where the bill lands. A cell whose median run has an
output-priced share below **40%** is labelled *not output-dominated*; its visible-output
share is reported beside it, and it is never pooled with the cells that are. The label is
an **eligibility condition**: only cells in which *both* compared arms are output-dominated
enter the KEEP/DELETE predicates, and a Stage 2 with no eligible contrast returns
INCONCLUSIVE, not DELETE. The 40% figure is pre-registered and can be wrong; what cannot
be wrong is that the label comes from the measurement.

A **difficulty ladder**, because the answer a routing rule needs is a frontier:

- **L1** — mechanical edit, one call site, no judgement.
- **L2** — small algorithm inside a frozen interface.
- **L3** — edit requiring a read of an adjacent module to avoid breaking it.

Fixtures are generated per repetition with run-unique identifiers, and the tests live
outside the working directory. A fresh fixture makes the *suffix* fresh; it does not make
the *cache* fresh — see *Cache order* below.

### Treatment matrix

Arms are not labels; each is a row that fixes everything an implementation would
otherwise choose. One row per host; the Codex rows are given, the Claude rows are filled
identically before Stage 2 and pinned in the record.

| Arm | Parent seat | Mechanism | Child seat | Children / run | Packet |
| --- | --- | --- | --- | --- | --- |
| inline | P | none | — | 0 | — |
| delegated-same | P | isolated spawn (`fork_turns: "none"` on Codex; non-fork subagent on Claude) | **= P** | 1 | workhorse 6-field |
| **delegated-shipped** | P | isolated spawn | **the host's shipped `workhorse` binding**, read from `launch/agent-launch.toml` at the run's HEAD and pinned in the record — at this HEAD `terra / high` (Codex), `opus-5 / medium` (Claude) | 1 | same |
| delegated-cheap-lowE | P | isolated spawn | luna / low (haiku / low) | 1 | same |
| delegated-cheap-highE | P | isolated spawn | luna / high (haiku / high) | 1 | same |
| delegated-mid | P | isolated spawn | sonnet / high — **Claude only**; on Codex the shipped binding *is* the mid seat and the row would duplicate delegated-shipped | 1 | same |
| fork-same | P | fork (`fork_turns: "all"`; Claude fork subagent) | = P | 1 | none |
| fork-cheap | P | fork | luna / low | 1 | none — **Codex only** |

**P** (the parent seat) is `gpt-5.6-sol / xhigh` on Codex and `claude-opus-5 / xhigh` on
Claude — the shipped HELM bindings — and is identical across every arm of a host. It is
registered here because thinking is 57% of output on a live rollout and moves with effort:
an unpinned parent makes the inline baseline a moving number.

On Claude, delegated-shipped against delegated-same is the **same model at two efforts**;
the contrast isolates effort, which the earlier WORKHORSE cost record already suspected
is the lever that matters. On Codex it is a model contrast (terra against sol). The two
hosts therefore answer the retention question through different mechanisms, and that is
one more reason a null on one host says nothing about the other.

**Topology is fixed**: one child per run, doing all M items, sequential, one pristine
fixture copy per run — the contract's own case for a dependent batch (*Task*). Fan-out
changes the fixed cost (one corpus injection per child) and the interference between
items; it is a second axis, and it is not this experiment's.

**delegated-same is the attribution control.** There are two verdicts, and they quantify
over different contrasts, never merged:

- **Retention** — `delegated-shipped − delegated-same`. The only contrast KEEP/DELETE for
  `workhorse` quantifies over.
- **Rebinding** — `delegated-cheap-lowE − delegated-same` and
  `delegated-cheap-highE − delegated-same`. These can name a REBIND candidate, scoped to
  the seat that produced it; they cannot keep or delete the tier.

Everything else — inline, mid, both forks — is reported and is not a decision input.

**fork-cheap exists on Codex only.** Official Claude Code docs (fetched 2026-09-03): a fork
"inherits the full conversation history, system prompt, tools, **model**, and prompt
cache". The prior record's "there is no subagent fork" on Claude was measured against a
nonexistent `subagent_type: "fork"` and is superseded by that doc. The Claude fork arm
uses the documented fork subagent, and it does not count until the *inheritance receipt*
below has passed.

### Staging

- **Stage 0** — instrument only; no cell counts until every control below passes.
- **Stage 1** — Codex, every Codex arm × 3 sizes × L2, R=3. A **screen**: its
  pre-registered outcome is one bit per contrast — *the point estimate of the contrast
  exceeds the run-to-run spread of delegated-same at that size* — and it decides nothing
  about seats.
- **Stage 2** — R=5, L1 and L3 added, and **Claude runs regardless of the Codex screen**.
  The fork arms' mechanism is host-specific (98.9% reuse on Claude, 14–18% on Codex in the
  prior record) and the TTL and fan-out behaviour differ, so a Codex null does not predict
  a Claude null. Any null conclusion is scoped to the host it was observed on.

### Common basis

The two hosts are not billed alike, and comparing them without fixing that is the trap
the corpus names before any comparison.

- **Claude** — `total_cost_usd`, measured, per run — AND the token breakdown.
- **Codex** — an OAuth subscription pays no per-run dollar. Tokens by kind are measured;
  dollars are **modelled** from the rate table, labelled modelled, and never pooled with a
  measured Claude figure. **A modelled Codex dollar is not an operational cost under
  OAuth**: the scarce quantity there is rate-limit budget, and how a request debits it is
  neither published nor measured here. Codex verdicts are labelled *API-rate-equivalent*
  and bear on an API-billed profile; they claim nothing about what a subscription run
  spends.

**Five token kinds** (cross-checked against the official usage objects and pricing pages,
2026-09-03):

| Kind | Claude field | Codex field | Price vs base input |
| --- | --- | --- | --- |
| uncached input | `input_tokens` | `input_tokens − cached_input_tokens` | 1× |
| cache read | `cache_read_input_tokens` | `cached_input_tokens` | 0.1× (0.025× Fable 5.1) |
| cache write | `cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` | `cache_write_input_tokens` | 1.25× (5m) / 2× (1h) Claude; 1.25× GPT |
| visible output | `output_tokens − thinking` | `output_tokens − reasoning_output_tokens` | output rate |
| thinking | `output_tokens_details.thinking_tokens` | `reasoning_output_tokens` | billed as output (both vendors) |

A non-fork spawn is a cache-write event by construction — the official Claude Code doc:
a subagent "warm[s] its own cache … rather than reading the parent's cache" — which is
why read and write are never folded into one "cached" column.

**Rate table** (official, 2026-09-03, $/MTok — input / cache write / cache read / output):

| Seat | Rates |
| --- | --- |
| claude-fable-5 | 10 / 12.5 (5m) · 20 (1h) / 1 / 50 |
| claude-opus-5 | 5 / 6.25 · 10 / 0.5 / 25 |
| claude-sonnet-5 | 2 / 2.5 · 4 / 0.2 / 10 |
| claude-haiku-4-5 | 1 / 1.25 · 2 / 0.1 / 5 |
| gpt-5.6-sol | 4 / 5 / 0.4 / 20 — ×2 input, ×1.5 output above 272K |
| gpt-5.6-terra | 2 / 2.5 / 0.2 / 12 — same cliff |
| gpt-5.6-luna | 0.2 / 0.25 / 0.02 / 1.2 — same cliff |

Top seat to cheapest: **GPT 20× on input and both cache kinds, 16.7× on output; Claude
10× on every kind (fable→haiku), 5× on every kind (opus→haiku).** Codex runs first because
every kind's ratio is larger there, not because of the output rate alone.

**The estimator, pre-registered.** A run's cost is **participant-indexed**:
Σ over participants, Σ over kinds, usage × rate[the participant's *receipted* seat][kind]
— never usage summed across participants and then priced, because a sol parent and a luna
child differ by 20× on the same kind. For a cell, cost per verified item is
**Σ cost over R runs ÷ Σ items passing over R runs** (ratio of sums). Repetitions are
paired across arms by fixture instance. A run with zero passing items contributes its full
cost and zero to the denominator — intention-to-treat. **Saving** for a contrast is

    saving = 1 − C_arm ÷ C_same

where C is the cell estimator: positive means the arm is cheaper, and 25% means the arm
costs three quarters of delegated-same. The raw difference `C_arm − C_same` is reported
beside it and is not a decision input. The 20% and 25% thresholds below apply to this
statistic and no other.

**Long-context cliff (Codex).** Every billed request records its context size and its
five token kinds. The multipliers apply **per request** that exceeds 272K, and a run's
cost is the sum over its requests; a run-level peak flag would price the run's
below-cliff requests at cliff rates. A run containing any cliff request is **flagged and
never excluded** — the cliff is real billing that inline structurally incurs at large M
and delegation structurally avoids, so it is part of the question. The primary estimand
is cliff-inclusive. A secondary under-cliff estimand is computed only over complete
matched blocks in which no arm crossed, and blocks are replenished until every compared
arm has R such blocks.

**Cache order.** Arms run in counterbalanced order within each matched block. On Codex
each run sets a fresh `prompt_cache_key`. On Claude the key is not controllable from the
CLI, and a 1-hour cache write (`ephemeral_1h_input_tokens`) outlives any practical gap
between arms, so waiting past the 5-minute subagent TTL does not make a sibling arm's
prefix cold. Instead the block's shared fixture packet is prefixed with a **run-unique
nonce placed before the fixture content**: the standing corpus prefix stays equally warm
for every arm, and nothing after the nonce can be read from a sibling arm's cache. The
state is **verified from the receipt**, not assumed: the first request of every run must
report `cache_read_input_tokens` no larger than the standing-prefix length measured in
Stage 0 (+5%), or the run is a control failure. Counterbalancing alone does not satisfy
this control.

### Controls

Every control has a way to fail and a way to pass vacuously that is named and closed.

0. **Run ledger (conservation).** Every run enumerates its participants — the parent and
   each expected child or fork — and every participant's usage is read from its own
   artifact (the Claude child transcript; the Codex child rollout, located by
   `parent_thread_id`), priced by the participant-indexed formula above. Publication of a
   run's cost **fails** unless the participant count matches the arm's row in the
   treatment matrix and the summed usage reconciles with the parent-reported total where
   one exists. A delegated probe run whose child usage is missing is the planted case,
   and it must fail by name.
1. **Known-opposite, on the billed host.** On Claude, run the seat-spread control twice —
   from measured `total_cost_usd` and from Σ(kinds×rates) — and require both to show the
   large spread *and* to agree within the reconciliation tolerance below. On Codex, where
   the "known" value would be computed from the same rate table under test, run a
   differential probe instead: per-turn versus cumulative summation of the same rollout
   must agree. On both hosts, **hand-calculated mixed-seat goldens** — a sol parent with a
   luna child, an opus parent with a haiku child — must fail under aggregation before
   pricing, under a swapped participant-to-seat mapping, and under a wrong-seat rate;
   agreement between two aggregations of the same usage validates none of those.
2. **Reconciliation.** Every Claude run must satisfy |Σ(kinds×rates) − `total_cost_usd`|
   ≤ 3% before any modelled figure on either host counts. This is the only place the
   model meets a bill.
3. **Denominator.** The generated manifest's identity set is the fixed intention-to-treat
   set. The verifier must receipt **every** assigned identity — pass or fail — and the
   child's touched set is recorded separately. An assigned identity the child never
   touched scores as a failed item, not as a missing one; the control failure is a
   verifier that leaves an assigned identity unreceipted. A run echoing
   `items_attempted: 40` proves nothing.
4. **Seat receipt.** `seat_problem()` on every participant. A child on a seat other than
   its row is discarded and reported, never averaged in.
5. **Field-existence proof.** Before the null rule below applies, each host has a captured
   payload showing every one of the five fields — cache read, cache write in both Claude
   lifetime buckets, uncached input, visible output, thinking — with **distinct nonzero
   sentinel values**, under conditions that force them (a fresh child; a warm second
   request; a high-effort turn). A zero field proves neither extraction nor identity.
   Frozen as parser goldens with exact values, conservation identities
   (`input = uncached + read`, `output = visible + thinking`), both Claude JSON shapes, and
   a cliff-boundary case. Every single-field omission or swap mutation — read for write,
   5m for 1h — must fail here.
6. **Failure classes.** *Infrastructure failure* — a null field after control 5, a missing
   dispatch or participant receipt, a runner error, a first request that reads more cache
   than the cold bound — is excluded and reported. *Counted outcome* — a receipted child,
   whatever it did — stays in the arm with its cost. A receipted child that attempted
   nothing, refused, or made no edit is **0 of M** under intention-to-treat, not a
   malfunction. A cheap seat that fails every L3 item is a result.
7. **Checker, both directions.** For every fixture: the faithful fix must **pass** first;
   that known-good copy is then mutated and the item's **own assertion** must fail — a
   runner error, a missing path, or a collection failure is a control failure, not a pass.
   A mutant the correct checker accepts is replaced (an independent oracle must show it
   fails the named behaviour while the faithful fix passes) before the gate runs; a
   surviving equivalent mutant is a defect in the *rule* that reads survival as a gap.
8. **Inheritance receipt (fork arms).** The parent holds a run-unique canary that exists
   nowhere on disk and in no packet. A fork child must return it; an isolated child must
   not. On Codex this replaces the cache-key control of revision 1, which passed on any
   nonzero `cached_input_tokens` — the standing corpus prefix produces those without any
   parent inheritance. The measured first-request reuse fraction is **recorded**, and
   fork-cell pricing is derived from the measured kind split whichever way it comes out;
   the gate's pass criterion is that the canary discriminates, not any particular fraction.
9. **Fresh fixture per repetition**, and the cache-order rule above.

### Pre-registered thresholds

Both verdicts quantify over **pre-named cells** (arm × M × L × host) that are *eligible* —
both compared arms labelled output-dominated (*Task*). Mid and fork arms carry no
evidence about either verdict and appear in no predicate. **No threshold can fire on
Stage-1 data.** Family size is recorded with the result: at this design, 2 hosts × 3 M ×
3 L gives 18 retention cells and 36 rebinding cells.

**One bound algorithm, pre-registered.** Resample the R matched blocks with replacement
(10,000 draws, seed recorded), recompute the ratio-of-sums estimator per arm and the
saving per draw, and take the one-sided 90% percentile bound. A block with zero passing
items in an arm stays in the sums — its cost counts and its passes are zero; a draw in
which an arm's summed passes is zero has an undefined saving and counts as failing to
clear the bound. The same algorithm, on the same draws, gives the bound on the pass-rate
difference. R=5 makes this bound coarse, which is one reason the thresholds are proposals;
what it is not is unspecified.

**Search, then confirm.** A cell whose bound crosses in Stage 2 is a *candidate*, not a
result: 36 pointwise bounds at 90% cross by chance. A candidate is re-run as a fresh
confirmatory block set — R=5 new repetitions, fixtures not reused — and must cross again
on the confirmatory data alone. KEEP and REBIND fire only on confirmation.

- **KEEP** if, in any eligible **retention** cell, the confirmed lower 90% bound of the
  saving is ≥25% *and* the confirmed lower bound of the pass-rate difference is ≥ −Δ.
- **DELETE** only if, for **every** eligible retention cell at R=5, the **upper** 90%
  bound of the saving is ≤20%. A point estimate under 20% is not evidence of absence.
- **REBIND candidate — `<seat>`** if an eligible **rebinding** cell meets the KEEP
  conditions after confirmation. It names the seat and the cells; it changes no binding
  by itself.
- **Otherwise inconclusive, and the seat stays** — including when no cell is eligible.
  The default follows reversibility: keeping is a no-op, deleting is a golden recapture
  across every setup/host/family combination.

The 25 / 20 / Δ=5 / 90 / 40 figures are proposals and were not independently reviewed
as numbers.

## What this cannot answer

- **Parallelism.** Topology is fixed at one child, and the fixture is a dependent batch;
  the contract's *independent items in parallel* case is unmeasured. Fan-out is the next
  experiment, and the official Claude Code note that a fan-out reuses the first child's
  prefix is a hypothesis for it, not a fact this design confirms.
- **What a subscription run spends.** Codex under OAuth debits a rate-limit budget by a
  rule that is not published; nothing here measures it, and the Codex verdicts are
  API-rate-equivalent only.
- **Context isolation** — a large log staying out of the main's window — is not a cost or
  wall-clock quantity and no cell measures it.
- **`sweep`.** Out of scope by contract; see *The decision this feeds*.
- Work with no machine-checkable done-when, which is most of what a main context does.

## Provenance

Revision 1 was produced in a single perspective with subagents disabled. Revision 2
incorporated round 1 of a two-seat review — `gpt-5.6-sol`/max hermetic and
`claude-fable-5`/max with the corpus stripped — 38 findings, 37 accepted, 3 narrowed, 0
rejected. Revision 3 incorporates round 2 on one seat — `gpt-5.6-sol`/max hermetic — 15
findings, 15 accepted, 2 narrowed (the topology finding is met by scoping the fixture to
a dependent batch rather than by adding fan-out; the quality finding by naming Δ rather
than by tightening it to zero), 0 rejected; the second seat did not run. Both round
records and every raw verdict are beside this file. Round 3 should re-review this
revision at its own hash, on two seats, before Stage 0 is built.


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
BUNDLE 3 — the two spawn-target definitions and the shipped tier bindings the design says it exercises
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

--- launch/agent-launch.toml, lines 150–200 at HEAD 46959fd (the shipped tier bindings on both hosts) ---
[hosts.codex.tiers.helm]
model = "gpt-5.6-sol"
effort = "xhigh"

[hosts.codex.tiers.workhorse]
model = "gpt-5.6-terra"
effort = "high"

[hosts.codex.tiers.sweep]
model = "gpt-5.6-luna"
effort = "low"

[hosts.codex.agent_templates]
frontier = "${CODEX_HOME}/agents/frontier.toml"
workhorse = "${CODEX_HOME}/agents/workhorse.toml"
sweep = "${CODEX_HOME}/agents/sweep.toml"

# Model id -> the name the human-readable guides write. The guides' Environment Binding tables
# restate these bindings in prose that also carries policy the profile does not hold ("main Ultra
# requires explicit selection"), so those tables are not generatable — but the MODEL IDENTITY in
# them is this file's, and until this map existed the parity gate compared each table to display
# names written inside the gate. That made the gate a third author of the binding. With the map
# here, the gate compares two real surfaces and holds no copy of its own.
[model_display]
"claude-fable-5" = "Claude Fable 5"
"claude-opus-5" = "Claude Opus 5"
"claude-haiku-4-5" = "Claude Haiku 4.5"
"gpt-5.6-sol" = "GPT-5.6 Sol"
"gpt-5.6-terra" = "GPT-5.6 Terra"
"gpt-5.6-luna" = "GPT-5.6 Luna"

[hosts.claude]
provider = "anthropic"
models = ["claude-fable-5", "claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]

[hosts.claude.tiers.frontier]
model = "claude-fable-5"
effort = "max"

[hosts.claude.tiers.helm]
model = "claude-opus-5"
effort = "xhigh"

[hosts.claude.tiers.workhorse]
model = "claude-opus-5"
effort = "medium"

[hosts.claude.tiers.sweep]
model = "claude-haiku-4-5"
effort = "low"


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

================================================================================
BUNDLE 5 — round 1 review record (the 38 findings revision 2 responded to)
================================================================================
---
created_at: 2026-09-03T23:20:00+09:00
head: a477bcc
kind: review
---

# Tier-economics experiment design — review round 1

Target: `2026-09-03T2215--a477bcc--tier-economics-write-experiment.md` at sha256 `c41669f13cb1`
(the revision after the official-doc cross-check was folded in). Criterion: **AI workbench /
harness** — a defect is a signal that would look true and be false. Packet:
`…-review-packet.md` beside this file; it bundled the two prior measurement records, the two
spawn-target definitions, and the harness parser excerpt.

## Who reviewed, and what that bought

| Seat | Isolation | Receipt | Participation | Findings | Cost |
| --- | --- | --- | --- | --- | --- |
| `gpt-5.6-sol` / max | `codex-run.sh --profile hermetic` — fresh CODEX_HOME, no AGENTS.md, read-only, `--output-schema` | `…-codex-receipt.json`: packet sha `188de666…` = disk, result sha recorded, exit 0 | R1–R6 all checked | 22 | modelled only (OAuth) |
| `claude-fable-5` / max | `claude -p --setting-sources ''` — corpus stripped, plan mode | `modelUsage` keys `claude-fable-5` (+ host-internal haiku) | R1–R6 all checked | 16 | $5.93 measured |

Cross-family is the top rung of the independence ladder; the second seat is a different
model of the author's family with the shared corpus removed. Every anchor quote from both
reviewers was found verbatim in the target (38/38), so no finding rests on a fabricated
line. Both echoed the target hash.

## Disposition

Accepted 37, narrowed 3, rejected 0. Two reviewers reaching the same defect independently
is the strongest signal this round produced; those are listed first.

### Found by both (11)

| Defect | Claude | Codex | Severity |
| --- | --- | --- | --- |
| A delegated run's cost omits every child: Codex child usage lives in the child rollout, not the parent's `exec --json` stream. No control sums parent+child. | #1 | #3 | blocker ×2 |
| KEEP threshold has no sample-size qualifier while DELETE does; fires on Stage-1 screen data the design itself disavows. | #2 | #16 | blocker ×2 |
| "Any cell" over tens of cells — one crosses 25% under the null. | #6 | #17 | high / blocker |
| Excluding above-cliff runs removes inline's expensive runs only; inline looks cheaper; false DELETE. | #7 | #21 | high ×2 |
| `sweep` is read-only by definition; write cells cannot decide its fate. | #8 | #4 | high / blocker |
| Known-bad probe is one-sided: a checker that fails everything passes it. | #10 | #9 | high / blocker |
| The main's model+effort is unpinned; thinking is 57% of output and moves with effort. | #11 | #1 | high ×2 |
| "Zero items = instrument failure" erases a genuine 0-for-N quality result. | #14 | #11 | medium / high |
| Five-kind field mapping is never proven to exist per host before the null rule applies. | #13 | #12 | medium / blocker |
| "An effect absent on Codex is absent everywhere" — the fork arms' mechanism is host-specific. | #5 | #20 | high / blocker |
| Claude fork arm names no mechanism; the bundled record and the design disagree on whether one exists. | #15 | #15 | medium / high — **narrowed** |

### Codex only (11)

- **#2 blocker — attribution.** Cheap-vs-inline confounds the seat with the routing mechanism (shorter child context, no prior-turn thinking, fan-out reuse). A same-model isolated spawn is the control; the seat effect is cheap-vs-delegated-same.
- **#5 high** — "write-dominated" is asserted; make output dominance a measured cell-validity gate.
- **#6 medium** — sol/luna ratio is 20× on input and cache kinds, 16.7× on output; the staging rationale used the smaller one.
- **#7 blocker** — `N` names both items-per-run and repetitions; and `items_attempted` echoed ≠ identity-set equality.
- **#8 high** — no pre-registered estimator; ratio-of-means and mean-of-ratios give 50% vs 10.8% on the same runs.
- **#10 high** — an equivalent mutant blocks all cells; admit mutants only via an independent oracle.
- **#13 high** — sequential arms share a warm prefix; a fresh suffix is not a fresh cache.
- **#14 blocker** — the Codex cache-key control passes on the standing prefix; needs a parent-only run-unique canary.
- **#18 blocker** — DELETE on point estimates ≤20% is not evidence of absence; needs the upper bound.
- **#19 high** — the DELETE predicate quantifies over mid and fork arms, which carry no evidence about cheap seats.
- **#22 medium — narrowed.** Claims the 60-file sweep cell was N=5. The record says both: §2 "the pinned cells are N=5", Limits "the four load-bearing cells are N=5; every other cell … N=2". Raw runs do not survive. Held as ambiguous in the design rather than resolved either way.

### Claude only (5)

- **#3 high** — control 1 on Codex checks the rate table against itself.
- **#4 high** — Σ(kinds×rates) is never reconciled with a measured `total_cost_usd`; Claude, the only billed host, enters last.
- **#9 high** — topology (children per run, concurrency, copies per item) is a hidden axis as large as the seat axis.
- **#12 medium** — "Claude 5×" is opus→haiku; the table's top seat gives 10×.
- **#16 detected_miss** — Stage 0 (a) has no pass criterion for a pure measurement.

### Narrowed

- Both #15: the fork mechanism does exist on Claude Code (official sub-agents doc, fetched
  2026-09-03: a fork "inherits … model, and prompt cache"); Bundle 1's "there is no subagent
  fork" was measured against a nonexistent `subagent_type: "fork"`. The finding survives as:
  name the invocation per host and require an inheritance receipt. Exclusion of a cheap fork
  on Claude stands on "inherits model", not on unavailability.
- Codex #22 as above.

## What the round says about the design

Three of the design's own safeguards were the sources of false signals: the cliff
*exclusion* (biases inline), the zero-items *rule* (erases quality failures), and the
parent-stream *parser* (erases children). Two more were one-sided (known-bad without
known-good; DELETE on point estimates). The reviewers did not disagree with the question;
they disagreed with the instrument. Round 2 should re-review the rewritten design at its new
hash before Stage 0 is built.


================================================================================
BUNDLE 6 — round 2 review record (the 15 findings revision 3 responded to; ONE seat only)
================================================================================
---
created_at: 2026-09-04T07:25:00+09:00
head: 46959fd
kind: review
---

# Tier-economics experiment design — review round 2

Target: `2026-09-03T2215--a477bcc--tier-economics-write-experiment.md` at sha256
`02e1ab995be7` (revision 2, the revision after round 1). Criterion: **AI workbench /
harness** — a defect is a signal that would look true and be false. Packet:
`…-review-packet.md` beside this file (sha256 `e84c33e2…`); it bundled revision 2, the two
prior measurement records, the two spawn-target definitions, the harness parser excerpt,
and round 1's finding summaries, and asked each finding to carry a provenance —
*caused* by revision 2's changes, *surfaced* by them, or *pre-existing*.

## Who reviewed, and what that bought

| Seat | Isolation | Receipt | Participation | Findings | Cost |
| --- | --- | --- | --- | --- | --- |
| `gpt-5.6-sol` / max | `codex-run.sh --profile hermetic` — fresh CODEX_HOME, no AGENTS.md, read-only, `--output-schema` | `…-codex-receipt.json`: packet sha `e84c33e2…` = disk, result sha recorded, exit 0, 77,135 tokens | R1–R6 all checked | 15 | modelled only (OAuth) |
| `claude-fable-5` / max | **did not run** | — | — | — | — |

**Why the second seat did not run.** Every new `claude` process on the author's machine
reported `Not logged in` from 00:33 KST on 2026-09-04 — nested under this session or from
a plain shell, the same binary the interactive session runs (2.1.259), with the nested
session's environment stripped one variable at a time and all at once; `claude auth
status` agreed. Round 1's Claude seat ran at 22:50 KST the evening before, on a keychain
item created at 22:45; the item was rewritten at 00:33 and unusable after. Sessions
started earlier kept working on the token they held in memory. What rewrote it was not
established. The coincidence on record is a burst of about twenty headless session starts
at 00:33–00:39 KST from another session's dispatch fleet, which is consistent with a
refresh-token rotation race across concurrent processes and proves nothing. Re-login is
the operator's action, so the round is recorded as it ran: one seat. A single seat buys
no independence beyond itself, and the first thing round 3 owes is the second seat.

Every anchor quote was found verbatim in the target (15/15). The target hash was echoed.

## Disposition

Accepted 15, narrowed 2, rejected 0.

Provenance, as classified by the reviewer and checked against revision 2's own change
list: **caused 6 · surfaced 4 · pre-existing 5.** The pre-existing five survived two seats
in round 1. One of them — #1 — is the largest finding of either round.

| # | Sev | Prov | Finding | Revision 3 |
| --- | --- | --- | --- | --- |
| 1 | blocker | pre-existing | No arm runs the shipped `workhorse` binding (`opus-5/medium` Claude, `terra/high` Codex); KEEP/DELETE on haiku/luna evidence would decide a binding nobody ships | New `delegated-shipped` arm bound from `agent-launch.toml` at the run's HEAD; **retention** verdict quantifies over it alone; cheap arms feed a separate **rebinding** verdict |
| 2 | high | caused | Topology fixed to one sequential child, but the contract routes independent items to parallel children | *Narrowed*: the fixture is declared a dependent batch (one module family, ordered items) — the contract's single-dispatch case — and the independent fan-out case is named as unanswered, rather than adding a fan-out axis |
| 3 | high | pre-existing | Codex modelled dollars feed the operational ship gate; under OAuth no dollar is paid and the rate-limit debit is unmeasured | Codex verdicts labelled *API-rate-equivalent*; subscription spend listed under *cannot answer* |
| 4 | high | surfaced | Per-turn-vs-cumulative probe validates aggregation, not participant→rate mapping; a sol parent + luna child priced as one aggregate passes it | Participant-indexed cost formula written into the estimator; hand-calculated mixed-seat goldens in control 1 that fail aggregation-before-pricing, swapped mapping, wrong-seat rate |
| 5 | high | surfaced | 1-hour cache writes outlive the 5-minute gap between Claude arms; counterbalancing cannot balance six arms at R=5 | Run-unique nonce before the fixture content; cold state verified from the first request's `cache_read_input_tokens` against a Stage-0 prefix bound |
| 6 | high | caused | Run-level peak flag prices below-cliff requests at cliff rates | Per-request context size and kinds retained; multipliers applied per request, then summed |
| 7 | high | surfaced | Goldens force only cache write and thinking nonzero; a hard-coded-zero cache-read extractor passes | Distinct nonzero sentinels for every field including both Claude lifetime buckets; every single-field omission/swap mutation must fail |
| 8 | blocker | pre-existing | Zero attempts by a receipted child is excluded as infrastructure failure; a refusal is a 0/M outcome | Infrastructure failure redefined by receipts and runner state; a receipted child with no attempts is 0 of M under intention-to-treat |
| 9 | high | caused | Three-set equality (manifest = attempted = receipted) contradicts control 6 for every partial attempt | Manifest is the fixed ITT set; verifier receipts every assigned identity; unattempted = failed; touched set recorded separately |
| 10 | medium | caused | 40% classifier counts visible output only, while thinking is billed as output | Output-priced share = (visible + thinking) × output rate ÷ cost; visible share reported beside |
| 11 | blocker | caused | KEEP/DELETE quantify over every cell regardless of the output-dominance label; all-ineligible Stage 2 emits DELETE | Eligibility (both arms output-dominated) precedes the predicates; no eligible contrast → INCONCLUSIVE |
| 12 | blocker | surfaced | "saving" has no registered sign or denominator; `(same/cheap)−1` and `(same−cheap)/same` disagree at the threshold | `saving = 1 − C_arm ÷ C_same`, registered; raw difference reported, not decisive |
| 13 | high | caused | One-sided bounds named, no bound algorithm; zero-pass repetitions can be dropped by a conforming implementation | Paired block bootstrap (10,000 draws, seed recorded, percentile bound) on the ratio-of-sums; zero-pass blocks stay; zero-total-pass draws fail the bound |
| 14 | blocker | pre-existing | Any-cell KEEP over 36 pointwise 90% bounds is a family-search false positive | Search-then-confirm: a crossing cell is re-run on fresh confirmatory blocks and must cross again; KEEP/REBIND fire only on confirmation; family size recorded |
| 15 | high | pre-existing | Question says "equal or better"; KEEP accepts −5 points | *Narrowed*: the margin is one named parameter Δ=5 in question and predicates alike; Δ=0 is the operator's to choose — **flagged, not decided** |

### Narrowed

- **#2** offered two repairs — scope to a dependent batch, or add the contract-required
  fan-out with every participant ledgered. Fan-out is a second axis with its own fixed
  costs and interference; adding it here would make the retention verdict depend on a
  mechanism the design has not instrumented. Scoping is the honest repair, and the
  independent case is now named as unmeasured rather than implied answered.
- **#15** offered two repairs — tighten the quality bound to ≥0, or rewrite the question
  to authorize the loss. Neither is the reviewer's to make or the author's. Revision 3
  makes the two surfaces agree on one named parameter, and the choice of its value is
  the operator's.

## What the round says about the design

- **Repairs to safeguards are safeguards.** Six of fifteen were caused by revision 2's
  fixes to round 1's findings — the same failure class round 1 named, one level up. A
  revision that answers a review should expect its answers to be the next review's
  subjects, which is why round 3 targets revision 3 at its own hash and not the diff.
- **Two seats shared one blind spot.** #1 was in the packet of both rounds — the
  workhorse definition bundled in both said `claude-opus-5 / medium` — and round 1's two
  seats each accepted the design's framing that the cheap arm was the tier under decision.
  Cross-family independence catches what one family cannot see; it does not catch a
  premise both were handed.
- **Open for the operator:** Δ. The design now asks for quality "no worse than Δ = 5
  points"; the strict reading is Δ = 0. This is a value judgement about the tier's
  purpose, and the design carries it as a parameter until it is made.

