# Spawn policy — integrated design

Dated 2026-07-19. Status: **v1 SHIPPED + live-verified 2026-07-19** (see the v1
verification record below; commits `f1d13ea` + `284f3b1` on `main`; durable tier
agents + Standing spawn-policy block live in the deployed globals). Header
corrected 2026-07-23 — it had stalely read "design approved-pending" long after
v1 shipped. Owner: this repo's launch/delegation surface (agent-launch, shell
wrapper, globals, cli-multi-model-workflow guide).

## Sources and provenance

- **Diagnosis** (this session, 2026-07-19): measured subagent usage since the
  feature landed (launcher 2026-07-13, guide gates 2026-07-05). Claude: 2,067
  sessions, 2.6% ever spawn; Codex: 6,364 sessions, 0.06% `spawn_agent`.
  Tier-named spawns concentrate in 18 sessions; SWEEP used zero times. Root
  causes: (a) the zsh wrapper injects tier agents/contract only on the
  zero-argument interactive TTY path — resume/flagged/IDE/non-TTY sessions get
  nothing; (b) the always-loaded contract states bindings and review dispatch
  but no rules for WHEN to spawn; the When To Spawn gates live in a guide whose
  router line only fires for explicitly multi-model work (self-referential
  trigger).
- **Vendor confirmation** (claude-prompting guide, Delegation): "Left
  unprompted this tier under-reaches for subagents … it will not spend an
  expensive capability unless it is reasonably sure the capability is needed"
  — the always-on trigger surface is the documented fix, not a workaround.
- **Framework A** (local main, Opus 4.8/xhigh, in-conversation): two opposed
  optimizations; gate-owned quality; mechanism taxonomy M1–M4; metric set with
  falsification pairing; proportionality staging.
- **Framework B** (`sol-ultra-report-2026-07-19.md`): gpt-5.6-sol, ultra,
  hermetic blind packet (`sol-dispatch-packet-2026-07-19.md`). Ran solo — one
  native collab spawn failed in the hermetic profile. Predicate-conjunction
  gates, E/H economics, blind-packet protocol, statistical calibration
  apparatus, three risk findings.

Convergent items below are marked **[both]** (independent cross-family
agreement — high confidence); single-source items are marked [A] or [B].

## Governing directive (user, 2026-07-19)

Two-phase trigger design:

- **v1 — principled triggers, reliable firing.** Gates are logical criteria
  derived from the integrated principles. Room for LLM judgment exists
  *inside* a gate (borderline classification), never *about* the gates: they
  are checked at every work-unit boundary, and when a gate's criteria match,
  it fires — that consistency is the v1 objective. No calibration constants
  appear in the v1 policy text; countable criteria that make a trigger
  checkable (≥2 independent items, two failed attempts) are allowed as
  determinacy aids, ratio constants are not.
- **P2 — numeric trigger guide from data.** Once decision records accumulate,
  derive data-backed constants (leverage ratio, displacement thresholds,
  per-gate capture targets) and publish them as a revised trigger guide.
  sol's statistical apparatus (randomized holdouts, CI-gated moves, blinded
  adjudication) applies only to boundary-*widening* decisions, per the
  proportionality rule for single-user tooling.

Corollary: the one-line decision record ships with v1 — it is what makes P2
possible.

## Concept economy

The canonical concept remains the existing **When To Spawn gates** in
`cli-multi-model-workflow.md` (gates 1–4: independence, parallelism, residual
context, specifiability). This design *extends* that concept — it does not
introduce a parallel vocabulary. New named sub-concepts, each mapped to its
parent: down-gate refinements (→ gate 4), E/H leverage (→ spawn economics),
frontier gate (→ the existing "escalate by spawning FRONTIER first" rule),
blind packet, disposition, decision record.

## Part 1 — Spawn-point definitions (integrated)

### Down-delegation (WORKHORSE / SWEEP): quality-neutral by construction

A down-spawn point exists exactly where **quality is enforced by verification,
not by generation** [both — "gate-owned quality" ≡ "the acceptance oracle, not
trust in the lower tier"]. All conditions must hold:

1. **Decision-complete / input-closed** [both]: no unresolved semantic choice
   remains; required evidence lies in a finite named scope; no user intent must
   be inferred.
2. **Machine-checkable done-when** [both]: a predeclared test, schema, checklist,
   or short diff review can reject a materially wrong result *without repeating
   the reasoning*. If verification repeats the work, the gate fails [B].
3. **Decision locality** [B]: no unresolved choice crosses scope, architecture,
   public interface, security/privacy/data, external-effect, or shard
   boundaries.
4. **Reversibility / staging** [B]: output is staged until the main accepts it;
   the subagent cannot independently commit external or irreversible actions.
5. **Positive leverage** [both]: H (brief + verify + correct + integrate)
   must be clearly subordinate to E (the work the main would do inline). v1
   states this qualitatively — an in-gate LLM judgment; P2 binds a measured
   ratio (sol's starting proposal: E ≥ 2H; equivalent framing: spawn overhead
   ratio < 1 [A]).
6. **Trigger benefit** — at least one of: ≥2 independent parallel items [A];
   working log ≫ conclusion (context displacement — main-context hygiene is an
   independent benefit beyond token cost) [A].

**SWEEP admission** [B]: every unit applies one explicit rule to independent
targets; output mechanically replayable or evidence-carrying; **ambiguity is
returned as an exception, never resolved**. **WORKHORSE admission** [B]: local
semantic judgment or implementation with frozen requirements, interfaces,
invariants, and acceptance criteria.

### Frontier up-delegation: quality-raising by mechanism

A frontier spawn point is a **bounded, packet-expressible judgment** where all
three fire [B, subsuming A's signals]:

1. **Material stakes**: error would change a user-facing verdict, fix an
   architecture/public interface, invalidate ≥2 downstream units, or create
   security/privacy/data-loss/irreversibility risk (≈ blast radius M3 [A]).
2. **Residual epistemic risk** — at least one concrete signal: two viable
   alternatives persist; evidence or requirements conflict; an unverified
   assumption can flip the decision; **two attempts or hypotheses failed**
   (≈ capability gap M1 [A]); a material claim lacks a mechanical oracle.
3. **Ex-ante decision leverage** [B]: before spawning, the main names the
   finding that would change the selected option, constraint, implementation,
   test plan, release decision, or confidence band.

Mechanism taxonomy retained for later calibration [A]: M1 capability gap, M2
independence, M3 blast radius, M4 effort budget — record which mechanism
motivated each spawn so calibration can learn which mechanisms actually
predict uplift.

**Exclusion (both directions)** [both]: work that needs the main's live context
or unresolved round-trips stays inline; packet context loss beats tier gain.

**Blind-packet protocol** [both; operationalized by B]: the main privately
records its current option + confidence + change conditions, then starts
frontier in fresh context with raw evidence, constraints, evaluation rubric,
and neutrally ordered alternatives — never its preference, rationale,
confidence, or draft verdict. Verdict lands before the main's draft is
revealed. For artifact review: provide the artifact, omit the diagnosis.
Known residual risk [B]: anchoring can leak through evidence *selection and
framing* even with conclusions stripped; over-stripping produces
context-starved reviews. Balance, do not maximize.

**Disposition** [both — "reversal rate" ≡ "disposition"]: after the verdict,
record whether it produced a material change or an evidence-backed uncertainty
reduction. Neither → the spawn was vacuous; persistent vacuity indicts the
gate definition or packet leakage.

## Part 2 — Inline SpawnPolicy contract (v1 draft, the centerpiece)

Model-neutral text carried in the always-loaded surface (see Part 4).
Behavioral rules only — logical criteria, no calibration constants. Judgment
latitude exists inside a gate, never about applying the gates. Draft:

```
SpawnPolicy (apply at each work-unit boundary; when a gate fires, note one
line: gate, tier, spawn|inline, why — this record is required, the format is
one line, no more):
1. Verifying or reviewing your own work: always spawn (frontier for verdicts).
   Send a blind packet — evidence, constraints, rubric, neutral alternatives —
   never your draft conclusion; pre-note what finding would change what.
2. Two or more independent items: spawn in parallel. Use sweep only when each
   item applies one explicit rule and ambiguity returns as an exception;
   otherwise workhorse.
3. Broad reads, searches, test runs, or implementation bursts whose working
   log will dwarf the conclusion: spawn workhorse/sweep with a bounded report
   contract.
4. Down-spawn only decision-complete work with a machine-checkable done-when,
   staged output (no external irreversible actions), and briefing+verifying
   it clearly cheaper than doing it yourself.
5. Before an irreversible or authority-changing action, or when two attempts
   failed or two design alternatives persist: spawn a bounded frontier
   judgment. Record its disposition: what changed, or why nothing did.
6. Keep work inline when it needs your live context or when verifying a
   delegated result would repeat the reasoning. Explicit no-fan-out from the
   user wins over all of the above.
```

Precedence: a launcher preset with `Delegation=off` disables gates 1–5's spawn
obligation (the record habit stays); explicit user no-fan-out always wins.

## Part 3 — Decision record (the log-generating mechanism)

One line per gate event, in-transcript (no new file surface in v1):
`SpawnGate: <gate#> <tier> <spawn|inline> — <short why>` plus, for frontier,
the pre-noted change condition and afterwards `Disposition: <changed X |
no-change because Y>`. Deliberately rejected [proportionality, A]: sol's full
task card (8 fields + E/H estimates) for every spawn — recording overhead
raises H and re-suppresses spawning, the failure being fixed. Full card only
for frontier spawns, where stakes justify it.

## Part 4 — Activation placement (capability surface, per PLACEMENT-FRAMEWORK)

The diagnosis showed prose alone cannot fix this: most sessions never receive
the policy. Placement by layer, cheapest-that-fires:

1. **Enforcement — durable tier agents** (closes the wrapper gap): ship
   frontier/workhorse/sweep as installed agent definitions that load in EVERY
   session regardless of entry path. Deliberately no helm agent: HELM is the
   main role, not a spawnable worker — the measured helm-as-subagent spawns
   (22×) were an anti-pattern this removes structurally — Claude: `~/.claude/agents/*.md` deployed
   by `agent-bios install`; Codex: `agents.*` tables + `features.multi_agent`
   in `~/.codex/config.toml`, pointing at the installer-deployed
   `~/.codex/agents/*.toml` templates. Correction 2026-07-19: the installer
   does not deploy or merge `codex/config.toml` (repo copy is an ignored
   personal reference snapshot; runtime config is live-owned), so the codex
   registration is a one-time additive edit of the live file (backed up as
   `config.toml.bak-spawn-policy-20260719`), not an installer artifact. The
   launcher remains the session-specific projection for model/effort/review
   overrides; precedence: launcher `-c`/`--agents` pins > durable defaults
   (verified: CLI agents flag beats user-level files in Claude Code docs).
2. **Enforcement — SpawnPolicy in the always-loaded corpus**: add the Part 2
   block to global CLAUDE.md / AGENTS.md (both hosts, model-neutral canonical
   path), NOT only the launcher contract — the launcher reaches ~none of real
   sessions today. The launcher contract keeps carrying it too (harmless
   duplication until the wrapper gap decision lands).
3. **Guides**: fold Part 1's refinements into `cli-multi-model-workflow.md`'s
   existing When To Spawn section (extend gates 1–4; add the frontier gate,
   blind packet, disposition). Router line unchanged — the guide remains the
   deep reference; the inline block is the always-on trigger.
4. **Wrapper (optional, deferred decision)**: widen `agent-launch.zsh` so
   flagged/resume invocations also receive projection. With placements 1–2 the
   urgency drops; revisit after v1 data.

## Part 5 — Metrics, staged

**P1 (with v1, computable from transcripts + decision records):**

| metric | detects | source |
|---|---|---|
| gate-event count & spawn/inline split per gate | policy not firing at all (the current 2.6% baseline) | records [both] |
| rework rate (main/user edits delegated output) | down-delegation quality loss — rises ⇒ "quality-neutral" claim rejected | file history [A] |
| context displacement (sidechain tokens ÷ report tokens) | spawns with no compression benefit | transcripts [A] |
| round-trips per spawn | specifiability gate misjudged | transcripts [A] |
| frontier disposition rate (changed / total) | vacuous spawns (≈0) or leakage (≈100% agreement); escalation latency proxy | records [both] |

**P2 — numeric trigger guide (after records accumulate).** Deliverable: a
revised SpawnPolicy/guide whose constants are data-derived — leverage ratio,
displacement thresholds, per-gate capture targets. The heavier apparatus is
required only to MOVE a boundary outward: non-inferiority margin δ for
down-tier quality retention (catastrophic escapes: zero tolerance), net
compute saving vs floor β, frontier causal net win on randomized eligible
cases with hidden baselines, ≥N valid calls per trigger cohort before judging
it, stratified by host/tier/gate [B]. Known limit [B]: observational
comparisons measure task selection, not tier value — hence randomization only
at this stage, and only for widening.

## Risks (carried from both sources)

1. Self-reported gates are gameable; metrics can improve while hard judgment
   drifts downward [B]. Mitigation: P1 rework rate + periodic manual audit of
   decision records.
2. Sparse causal evidence: frontier-worthy cases are rare by construction [B].
   Accept: v1 optimizes trigger consistency, not proof.
3. Record fatigue: if the one-line record erodes, calibration data dies
   silently. Watch gate-event counts in P1; if they collapse while spawns
   continue, the record habit — not the policy — failed.
4. Threshold non-portability across model upgrades [B]: recalibrate on model
   change; the constants are placeholders by design (governing directive).

## Decisions (user, 2026-07-19)

1. v1 scope = Part 4 placements 1–3 in one pass: durable tier agents + global
   SpawnPolicy block + guide fold-in. Placement 4 (wrapper widening) deferred.
2. Korean mirror (`ko/`) updates in the same pass.
3. `Delegation=off` = gates' spawn obligation off, record habit stays;
   explicit user no-fan-out always wins.
4. (Same day, follow-up) Launcher must stop projecting helm as a spawnable
   subagent — `SPAWNABLE_TIERS` now feeds both hosts' projections, and parity
   asserts helm's absence from the Claude `--agents` JSON as a negative
   control.
5. (Same day, follow-up) Codex registration is installer-owned after all, via
   an additive fragment: `codex/config-additions.toml` declares exactly the
   agent-bios-managed content (marked `[agents.*]` block + tagged
   `features.multi_agent` line); install merges/checks it idempotently,
   uninstall strips only that content, and parity gates the fragment against
   the canonical agent templates. This supersedes the "one-time live edit"
   correction in Part 4 — the stale personal `codex/config.toml` snapshot is
   deleted (it was gitignored and npm-excluded all along). Verified by a
   temp-HOME fresh-machine E2E: merge → idempotent unchanged → uninstall
   restores the user config byte-identical. Also fixed en route: an unchanged
   idempotent install exited 1 via a bare `&&` chain under `set -e`.

## Done-when (v1 implementation, once approved)

- Fresh sessions on BOTH hosts, entered via a flagged/resume path (not the
  launcher), can name the four tiers and the SpawnPolicy gates when asked, and
  spawn a tier-named subagent on a gate-matching task — verified live, not by
  config presence.
- `agent-bios verify` (check-parity) passes with the new deployed surfaces.
- Decision-record lines appear in real transcripts within the first sessions;
  P1 queries over them return non-empty results (cardinality > 0 asserted).

## v1 verification record (2026-07-19)

- Deploy: `agent-bios install` green — corpus `match`, agent TOMLs OK, repo
  mirror parity OK, prompting targets OK; `~/.claude/agents/{frontier,
  workhorse,sweep}.md` present. `check-parity.sh` PASS over all four
  global/guide mirrors including the ko translations.
- Claude live probe (bare `command claude --model claude-haiku-4-5 -p`, the
  previously broken flagged non-launcher path): agent list includes
  frontier/workhorse/sweep (no helm, as designed); quoted the "Standing spawn
  policy" first clause verbatim. Print-mode agent loading, UNCONFIRMED in
  vendor docs, is hereby empirically confirmed.
- Claude end-to-end spawn probe (fresh headless session): spawned
  `subagent_type: sweep`, which ran the scan and reported its command —
  durable tier spawn works on the bare path, not just listing.
- Codex live probes (bare `codex exec`): `spawn_agent` tool present →
  `features.multi_agent = true` reaches bare sessions. Schema probe:
  spawn_agent = {task_name, message, fork_turns(none|all)} — no agent-name
  parameter, so native spawn cannot select the named `[agents.*]` tiers;
  consistent with the guide's documented limitation. Tier-pinned codex
  dispatch remains via the deployed codex-run/codex-helm wrappers (install's
  codex-helm dry-run green); `[agents.*]` serves the surfaces that consume it
  (launcher sessions, interactive app).
- Unverified residue: IDE-extension entry path not probed (no headless IDE
  surface); resume path not separately probed — low residual risk given the
  user-agents dir is watched from session start and both flagged + print
  paths passed. SpawnGate record accumulation in organic sessions: pending
  (this implementation session emitted the first real records).
