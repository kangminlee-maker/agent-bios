# Learning placement framework

User-decided 2026-07-18 (this session). Governs how session-distill items —
and future learnings generally — are routed into execution. Referenced from
HANDOFF.md pending decision §2/§2b; placement work must follow this.

## Layers (cheapest-that-still-fires-on-time wins)

1. **Enforcement** — owned scripts/wrappers/settings make the mistake
   impossible or the right way the default. Reaches ALL consumers.
2. **Verification gates** (post-hoc) — lint/CI/parity checks catch the
   violation after the fact: shellcheck, check-parity.sh-style gates, tests.
   Reaches all consumers; zero context cost.
3. **Hook injection** — PreToolUse tool/command-pattern match injects 1–3
   relevant guideline bullets as read-only context. Claude-side only.
4. **Guides** — scoped instruction files behind a router line; fire when the
   agent recognizes the situation. Model-neutral via canonical→mirror.
5. **Global CLAUDE.md / AGENTS.md** — always-loaded; strict token budget;
   only cross-domain situation-recognition principles, compressed, preferring
   extension of an existing bullet.
6. **Session-start memory** — project/user-specific facts and state, not
   generalized principles. A principle that graduates to the corpus is
   removed from memory (no double residence).
7. **Incubator ledger** — committed cumulative ledger of not-yet-promoted
   candidates. Passive but retrievable; feeds the lifecycle below.

## Learning typology (content-side view; classify BEFORE walking the tree)

Ask in order — first match wins, but apply the leftward-reformulation rule
below before settling:

- **A. Own-tooling defect** — root cause is a flaw in a script/tool we own.
  Not knowledge; a repair. → enforcement (fix), gate. Reaches everyone.
- **B. Tool gotcha** — counterintuitive external-tool behavior with a
  machine-detectable trigger (command pattern). → gate if a lint rule exists,
  else hook (Claude accelerator) + tooling-gotchas guide (codex fallback).
- **C. Recognition principle** — cross-domain semantic signal → suspicion/
  action. → global, preferring extension of an existing bullet.
- **D. Domain procedure** — multi-step method within an already-routed kind
  of work. → that guide; hermetic dispatch needs packet injection.
- **E. Environment fact** — non-generalizable, decaying specific fact.
  → memory / env block.
- **F. Unproven** — evidence below the promotion bar. → incubator ledger.

- **G. Principle/direction learning** — a value ordering or stance that
  shapes many decisions diffusely (tension → preference ordering), e.g. the
  12-round-review meta-lesson (delivery over assurance for single-user
  tools). NOT extractable by incident mining; see the distillation section.

Two completing rules:
- **Leftward reformulation first**: type is not fixed. Prefer E→C
  (generalize a fact into a principle, e.g. "this machine is zsh" → "pin the
  interpreter") and B/C/D→A (mechanize knowledge into structure, e.g. "grep
  misjudges binaries" → "harness Grep/ripgrep is the default") whenever the
  target layer's admission bar passes. Cheaper and more reliable than prose.
- **Consumer escalation**: after picking the type's primary mechanism, check
  the coverage matrix against "who is the executor when this is needed"; if
  the executor includes hermetic dispatch or scripts, escalate B–D to
  enforcement/gate/packet injection — prose layers never reach them.

## Org overlay: user-side landing vs curator-side routing (collection loop)

The typology and layers above are the **curator-side** routing (the `distill!`
pipeline / this framework). The light **session learning** flow (`learn!`,
`design/collection-loop/DESIGN.md`) is deliberately thinner: at capture time
EVERY type lands as **prose** (in the user's personal learnings file) plus a
JSON record whose `classification {type, layer, meets_bar}` and
`proposed_domain` are **metadata only** — the user side never builds the
hook/gate/enforcement. Mechanization and canonical placement happen later, when
a curator promotes the collected learning through the routing tree. `domain`
(D6 key ∪ tier name ∪ `unclassified`) is the join key between the two sides.

| Type | User-side landing (`learn!`, prose + record; layer = intent) | Curator-side routing (`distill!` / curation → canonical home) |
|---|---|---|
| A. Own-tooling defect | prose + record, `layer: enforcement`/`gate` | fix the tool + add the gate; remove the prose once mechanized |
| B. Tool gotcha | prose + record, `layer: hook`/`gate` | hook injection + tooling-gotchas guide (codex fallback) |
| C. Recognition principle | prose + record, `layer: global` | one compressed global bullet (extend an existing one) |
| D. Domain procedure | prose + record, `layer: guide` | the owning guide; packet injection where the executor is hermetic |
| E. Environment fact | prose + record, `layer: memory` | memory / env block (or reformulate E→C first) |
| F. Unproven | usually dropped at the admission bar; borderline items recorded for triage | incubator ledger |
| G. Principle/direction | recorded as an ordinary learning — **not manufactured user-side** | principle machinery (curator-only; the distillation section above) |

Two invariants hold across the overlay: the light flow records **intent, not
mechanism** (per the placement-cardinality rule, the canonical home is written
once — curator-side); and a below-bar item is dropped at capture, so what
reaches curation already cleared `meets_bar` or was flagged `unclassified` for
triage rather than silently promoted.

## Principle distillation (type G — user-decided 2026-07-18)

The v1 screeners' extraction unit is the incident, which structurally yields
directives. Principle evidence is distributed, so G uses its own machinery:

- **Sources**: (1) user-correction mining — collect the turns where the user
  redirected the agent, cluster by the value/tension being corrected (the
  existing digests already carry rollback/correction signals; re-screen them
  with this question, no new collection); (2) initiative-arc retrospectives —
  multi-session cost-vs-outcome reviews (the 12-round lesson is the
  exemplar); (3) upward distillation — when ≥3 promoted directives share one
  underlying value, propose the parent principle and demote the directives
  to guide-level instances (the vertical counterpart of leftward
  reformulation).
- **Evidence bar** (higher than directives; a wrong principle biases every
  decision): ≥3 independent instances of the same tension resolved the same
  way by the user, OR one arc retrospective explicitly confirmed by the user.
- **Anti-abstraction guard**: a principle must name both sides of the
  tension, the preference ordering, and what it now forbids. A direction
  must make an applicable choice and its rationale clear.
- **Application by gap kind**: *missing* → add/extend in the global principle
  sections (direction content is what the always-loaded budget is FOR —
  counterpart of the strict bar on situational directives entering global);
  *under-applied* (recitation-behavior gap) → prose repetition is invalid;
  change the surface instead (workflow gates, checklists at the acting
  point, behavior tests); *mis-prioritized* → rewrite the existing text to
  make the ordering explicit — riskier than additive edits, so verification
  below is mandatory.
- **Verification**: assess both meaning and application. Check that the principle
  correctly explains its evidence, value ordering, conditions, and limits; also
  check relevant decisions and actions, including unwanted effects, through
  proportionate application cases, before/after A/B on the same scenarios, or the
  staged adversarial battery (S2-11 method). A correct explanation alone does not
  prove application, and one suitable action alone does not prove understanding.
  Preserving an already-correct choice may be the intended result. Keep untested
  effects explicit in the review rather than claiming both dimensions verified.
- **Lifecycle**: decays by value drift and model-generation change (newer
  tiers need less prescription — de-prescribe), not tool versions;
  re-validate at arc retrospectives.

## Routing decision tree

0. Project/user-specific fact (not a general principle)? → memory (6)
1. Passes the enforcement bar (below)? → enforcement (1)
2. Violation deterministically detectable post-hoc? → verification gate (2)
3. Syntactic trigger (command pattern) exists? → hook (3) + guide fallback
4. Procedure in an already-routed domain? → existing guide (4)
5. Cross-domain recognition principle? → global (5), one compressed line
6. None of the above → incubator (7), not dropped

## Enforcement bar (all four required)

- Near-universal superiority within our values (no normal situation where the
  enforced way is worse; counterexample kills it — e.g. global pipefail fails:
  `cmd | head -1` → SIGPIPE 141, so pipefail is hook/gate material).
- Deterministically decidable violation (no semantic judgment).
- Enforcement point is a capability surface we own.
- Loud failures; no silent behavior change.

## Hook charter

Only sanctioned pattern: PreToolUse pattern match → inject relevant bullets as
read-only context. No blocking, no rewriting, no semantic judging. Triggers
syntactically deterministic; injected text derives from the canonical corpus
(no second source of truth); managed registry with token caps. Other hook uses
need case-by-case approval.

## Model-neutrality principle

The canonical consumption path for any learning should live in a model-neutral
layer (corpus canonical→mirror, enforcement, gates). Model-specific layers
(Claude hooks, skills) are accelerators by default, not the sole carrier.
Last-resort exception (user-refined 2026-07-18): when no neutral layer can
deliver a learning on time, skills MAY carry it — but Codex and Claude skills
are incompatible and must be authored and maintained per model, so adoption
requires a prior judgment that the content is worth that duplicated cost, and
the per-model skill bodies must derive from one canonical source so the
variants cannot drift.

## Consumer-coverage rule

Before placing, ask: "who is the executor at the moment this learning is
needed?" Consumers differ by channel:

| Consumer | Channels it reads |
|---|---|
| Claude main/subagents | CLAUDE.md, guides, hooks, memory |
| Codex chat sessions | AGENTS.md mirror, guides |
| Hermetic dispatched reviewers (codex-run packet) | the packet ONLY |
| Scripts/gates | code only |

If the executor is a hermetic dispatch or a script, prose layers are all
ineffective — only enforcement, gates, or dispatcher-side packet injection
(the dispatcher pulls relevant bullets from the corpus into the packet) work.

## Lifecycle

States: candidate → placed(layer) | incubating → promoted | retired.

- **Incubator ledger**: committed file; each rolling pipeline re-run merges
  new candidates into it by cluster identity, accumulating independent-session
  recurrence. Entry: {cluster id, supporting sessions, strength, placed_at
  (file + stable anchor), status, dates}. Corpus text stays clean; provenance
  lives in the ledger.
- **Promotion criteria** (reuses the strength rubric): independent-session
  recurrence ≥2, OR single-event with high materiality (irreversible /
  verification-corrupting / security). Promotion is never automatic — the
  human-approved-bundle gate stays.
- **Retirement criteria**: (a) refuted or observed harmful → remove + dated
  correction; (b) tool/version-bound fact expired → update or remove;
  (c) mechanized — once a prose item is implemented as a gate/enforcement,
  remove the prose. Low firing frequency is NOT a retirement reason
  (rare-high-cost items fire rarely by design).
- **Re-validation cadence**: no new schedule; piggyback on the already-decided
  rolling-window re-runs (ledger merge + decay scan for version-bound facts).

## Per-layer admission tests (completing the uneven set)

Enforcement and hooks have their bars above. The rest:

- **Gate bar**: violation deterministically detectable from artifacts (files,
  diff, command output); a checker already exists (e.g. a shellcheck rule,
  a parity-style script) or is buildable small; false-positive rate low enough
  that the gate won't get disabled (a noisy gate is worse than none); has a
  natural run point (pre-commit, CI, dispatch wrapper). Anything requiring
  semantic judgment is disclosure-only, never blocking (consistent with the
  global hard-block rule).
- **Guide bar**: the situation falls under an existing guide's `use_when`; the
  router line already fires for that kind of work. Otherwise see the new-guide
  criterion below.
- **Global bar**: cross-domain situation-recognition; compressible to ≤~50
  tokens; extension of an existing bullet (≤~20 token delta) preferred over a
  new bullet; subject to the budget rule below.
- **Memory bar**: a fact about this user/these projects, not generalizable.
- **Incubator**: the default when nothing above admits the item.

## Placement cardinality

- Each learning has exactly ONE canonical home. Accelerators (hook injection,
  dispatcher packet injection) and mirrors (codex/, ko/) replicate from it.
- Split into two placements only when the item genuinely contains two
  separable concepts (e.g. S4-06: general comparison principle → global;
  cost-specific procedure → guide). Record a split as two ledger entries
  sharing the cluster id.
- When a gate/enforcement implements an item, no prose version is written
  (existing prose is removed); the ledger marks it `mechanized` with the
  implementation path.

## New-guide creation criterion

Create a new guide only when ≥5 promoted items share a routing situation no
existing guide's `use_when` covers AND a one-line router can name that
situation in terms the agent will recognize mid-task. (tooling-gotchas, with
~18 recommended items, qualifies.)

## Token budget (measured 2026-07-18)

- `claude/CLAUDE.md` ≈ 20.1 KB ≈ ~5.0K tokens — paid every session.
- `claude/guides/` total ≈ 97.8 KB ≈ ~24.5K tokens — paid only on routing.
- Rules: every prose placement in the classification output carries a token
  estimate; per promotion round, global net growth ≤ ~500 tokens (~+10%);
  flag any single guide crossing ~16 KB (current max) for split/compaction.

## Per-layer firing verification (part of §P8 apply)

- enforcement: script test — wrong path fails loudly, right path is default.
- gate: known-bad fixture triggers it, known-good passes; assert the checked
  set is non-empty (no vacuous green).
- hook: trigger-regex test set — positive commands from bundle evidence fire,
  common benign commands stay silent.
- guide: router firing is measurable from the session corpus (census can
  count guide reads); router phrasing reviewed against agent vocabulary.
- global: staged adversarial battery (S2-11 method) for high-value bullets.
- §P8 apply verification = these per-layer tests + parity gate, not just diff.

## Bundle classification procedure

Walk every bundle item (all 74; unselected ones default to incubator) through
the routing tree and emit per item: {id, layer, mechanism detail (script /
gate rule / hook pattern / guide § / global bullet extended), token cost for
prose layers, consumer check (does it need dispatcher packet injection?),
split entries if any, firing-verification method}. Ambiguous routings are
marked PROPOSED for the user instead of silently resolved. Output lands as an
annex/column in BUNDLE-ko-review.md and seeds the incubator ledger.
