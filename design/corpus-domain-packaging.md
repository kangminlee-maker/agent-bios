# Corpus domain packaging — active design note

Status: **active design** (user-activated 2026-07-19). Premise changed from the
single-user backlog framing to a ~500-person in-house deployment; see the
"Premise change + resolved decisions" section below for what that overturns.

## Premise change + resolved decisions (2026-07-19)

The single-user, own-machine framing (G-4: delivery over assurance) that biased
this doc toward "defer the mechanism" is **void**. Confirmed new premise (user,
2026-07-19):

- **Deployment**: ~500 people, in-house, **company-wide mixed roles** (not an
  engineering-only population) → core shrinks to universal judgment principles;
  most current corpus becomes narrow domains installed by a minority.
- **Operating model — two ownership areas + a collection loop**:
  1. Central-managed area — central owns a canonical corpus (core + installable
     domain packages) and pushes it.
  2. Personal area — each user distills their own sessions locally (the existing
     session-distill system, run per-user).
  3. Collection loop (user's stated long-term goal) — harvest per-user
     distillations centrally → curate (dedup, classify, promote/retire) → new
     canonical version → redistribute.
- **First deliverable = onboarding experience** (user's priority): where a new
  hire installs central core, selects role/domains, and gets their personal
  area set up. corpus-domain-packaging (distribution half) and session-distill
  (collection half) are now two halves of one org-scale system; central
  curation is the join.

### New load-bearing axis: ownership separation (not in the original forks)
Central-pushed (overwrite-managed) content and user-owned (harvested) content
must **never share an overwrite-managed file** — a push would clobber personal
work. This overturns the [[consumption-layer-governance]] placement framework's
single-owner assumption: personal distillations can no longer be *placed into*
central-managed files; they need a separate user-owned layer that is never
overwritten and that is the harvest unit.

### Resolved: file topology (two ownership zones; amended 2026-07-20)
Verified empirically (Claude Code loader, 2026-07-19): `@import <path>` in
CLAUDE.md re-reads imported files every session (central updates propagate next
session); load precedence high→low is managed-policy CLAUDE.md (user cannot
override) > `~/.claude/CLAUDE.md` (user) > project > local. First import shows
a one-time approval dialog; a permanent decline silently loads nothing.

- **Personal-owned** (installer writes ONCE at onboarding, never after):
  `~/.claude/CLAUDE.md` — entry file, seeded with the `@import` line at
  onboarding, then user-owned; `verify` may read-check the import line and
  report, never rewrite. Plus `~/.claude/personal/*` (session distillations).
- **Central-managed** (installer overwrites on push): the `~/.claude/central/`
  TREE, not a single file — `central/bundle.md` (core + selected domain
  bullets), `central/guides/*` (lazy-referenced by router bullets; assembly
  rewrites reference paths — inlining guides into the bundle would pre-pay
  ~30K guide tokens every session), `central/hooks/*`, `central/agents/*`,
  and a marker-merged fragment of `~/.claude/settings.json` for the keys
  central owns (hook registrations; merge-not-overwrite — that file also
  holds user-owned config). Hook installation is gated by the same domain
  manifest entry as the guide it projects (no domain → no hook).
- **Onboarding canary** (required, part of the first deliverable): a
  first-session check that fails visibly unless the central bundle actually
  loaded — an import-approval decline or broken import line is an onboarding
  failure, not a silent state (file comparison cannot detect approval state).
- **Codex realization**: AGENTS.md has no imports and no precedence ladder,
  so the ownership boundary is filesystem-enforced on Claude Code ONLY.
  Codex gets a marker-merged single `~/.codex/AGENTS.md` (the
  codex_config_additions pattern already in install.sh): push rewrites only
  its own marked region; the personal region survives by merge convention —
  a weaker guarantee, accepted deliberately.

### Resolved: collection posture = full automatic harvest (user, 2026-07-20)
The whole `~/.claude/personal/*` tree is the harvest unit, collected
automatically — no shared/private split, no per-item contributor consent
gate (chosen over a consent-gated subset with the privacy tradeoff stated).
Technical floor that remains: the digest pipeline's secret-redaction carries
over to harvest, and central curation keeps human approval before anything
enters the canonical corpus. The per-user approval gate in the existing
lifecycle governs a user's LOCAL placements, not collection.

### Resolved: core posture = B (default, user-space)
Core ships in the user-space central bundle, NOT the enforced managed-policy
path (`/Library/Application Support/ClaudeCode/CLAUDE.md`). Rationale: the
system's purpose is sharing/utilization, not enforcement; no named
must-enforce risk. The managed-policy path stays reserved as an escalation for
any single core rule that later must be unremovable. Caveat: the enforced
property is Claude-Code-only — Codex/AGENTS.md has no such precedence ladder,
so cross-tool enforcement parity would need a separate mechanism (D1 seam).

### Resolved: D4 = staged, split by half (assembly unit amended 2026-07-20)
- Distribution half — **build now, scoped**: classification + manifest +
  parity gate + **per-domain package assembly at install time** (assemble
  each user's selected domain combination from per-domain package files) —
  not a per-user per-bullet projection compiler, and not pre-assembled
  role-preset bundles (that earlier wording predated the D3 opt-in decision
  and contradicted it; presets return in Phase 2 as named selections over
  the same assembler).
- Collection half — **convention now, build later**: establish the user-owned
  layer and the curation concept; defer the aggregation/harvest pipeline (the
  user's own "long-term" sequencing).

### Resolved: D5 — core boundary (mixed-role thinning; amended 2026-07-20)
Company-wide mixed roles thin core hard. Universal core (all ~500, any role):
1. Problem Solving (goal/scope/ambiguity/method/done-when).
2. Decision Framing (outcome-terms options; translate jargon to consequences).
3. Verify-before-done — principle slice only ("no done-claim without evidence;
   report failures honestly"); the code/ontology/spreadsheet verification menus
   stay domain.
4. Basic safety slice — no secrets in transcript-logged channels; keep changes
   in requested scope. (git/rm/shell specifics stay domain.)

The plain-register core rewrite is DEFERRED to Phase 2 (user-confirmed
2026-07-20); Phase-1 technical users are fine with the current register.

Slice mechanics (2026-07-20): slices 3–4 do not exist as whole bullets, so the
Granularity rules gain a sub-bullet-split allowance for exactly these two.
Pre-drafted splits — core keeps "Never accept secrets through transcript- or
history-logged channels" (from claude/CLAUDE.md:113; the env-slot/rotation/
echo-suppression mechanics stay builder-base) and "Keep file changes within
the requested scope" (from Global Preferences, claude/CLAUDE.md:6).

Moved OUT of core: Concept Economy, Documentation Hygiene, the verification
menus, and tooling-safety mechanics → all into **builder-base** (below);
language preference (Korean) → env-personal (never packaged).

**builder-base is THE single technical-common domain** (naming unified
2026-07-20; the phrasings "coding domain", "coding/design domain", and
"tooling-gotchas → shell-ops" in older sections below are superseded):
it holds Coding Guidelines + coding-staged-workflow + mock-realization-
boundary, Concept Economy, Verification Discipline menus + review-request
guide (WITH its router bullet — same package, no dangling reference),
Documentation Hygiene, and Tooling and Operational Safety mechanics +
tooling-gotchas guide (+ its hook, domain-gated per the topology). Installed
by all technical roles; shell-ops and other fine splits are later-split
candidates justified only by usage data. Specialty domains: llm-pipeline-dev,
multi-agent-orchestration, visualization-docs, office-work (carves the
spreadsheet bullet out of Coding Guidelines at the bullet pass).

Open item for the bullet-level pass: test the standing spawn-policy bullets
(claude/CLAUDE.md:119-120) against the core criterion — they are delegation-
judgment principles, not orchestration tool knowledge; defaulting them to the
orchestration domain by omission is not a decision.

### Resolved: D3 = per-domain opt-in (A) + phased rollout
Selection = **A (per-domain opt-in)**, not presets. Rollout is **sequential,
technical roles first, then expanding** (user, 2026-07-19); technical users
self-select domains fine (builder-base as one coarse toggle), so presets add
nothing for the v1 cohort. Presets (B/C) defer to the non-technical waves —
where self-selection breaks down.

- Phase 1 (technical): core + per-domain opt-in. Onboarding = install core +
  domain checklist + personal-area setup.
- Phase 2+ (other roles): add role presets + plain-register core.

**Re-sequencing consequence:** the D5 plain-register core rewrite is a
non-technical concern; Phase-1 technical users are fine with the current
register → rewrite **DEFERRED to Phase 2** (user-confirmed 2026-07-20).

Selection front-end only — the manifest + assembler (D1/D2) are unchanged by
A-vs-presets; opt-in just removes the role→domain mapping layer. Open for
D1/D2: where per-user domain selection state lives under central management.

### Derived rules (amended 2026-07-20)
- **Promote → migrate, executed user-side**: the push only INFORMS — it ships
  a promotion manifest naming the absorbed personal items; the user-side
  session-distill tooling (owner of the personal zone) removes or rewrites
  the local copy, and only after verifying the item is present in that user's
  OWN assembled bundle (per-domain opt-in means promotion into a package the
  user did not install must NOT trigger local removal — that would silently
  lose the learning). Central never edits personal files; a ledger-global
  `placed` flip is not a removal trigger.
- **Retire → reconcile** (symmetric to promote→migrate): central retirements
  and revisions ship as a machine-readable correction feed in the push; the
  user-side workflow reconciles personal copies against it (flag for the
  user, never silently delete). Without this, equal-precedence flat context
  accumulates central↔personal contradictions push after push.
- **Novelty is judged against the full canon**: per-user distillation screens
  novelty against the complete canonical manifest, not the user's installed
  subset — a hit on a not-installed domain is tagged "exists-in-canon", not
  novel (else opt-in users mint permanent personal duplicates of canonical
  rules that no dedup path can ever clear).
- **Cross-tool seam**: CLAUDE.md combines via `@import`; AGENTS.md (Codex)
  combines via marker-merged concat (see topology). The assembler must emit
  the correct combination per tool. Tracked under D1.

### Resolved: D1/D2 mechanism (partial, 2026-07-20)
- **D2 = separate manifest (`domains.json`)**, keyed by the parity gate's
  stable-phrase anchors; each domain entry lists bullets (anchors), guides
  (files), hooks (files + the settings keys they register), agents (files) —
  non-markdown assets are first-class manifest citizens.
- **Manifest gates** (mechanize the review's finding classes): bidirectional
  completeness (every bullet assigned ≥1 tier/domain; every anchor resolves);
  router-bullet and its guide land in the SAME package; per-package token
  budget; hook gated with its source guide's domain.
- **Assembly location = LOCAL** (user-decided 2026-07-20): the package
  (npm/git) ships the full canon + manifest; the installer assembles the
  selected domain combination on the user's machine. Matches the pull-based
  distribution; makes novelty-vs-full-canon screening free; selection changes
  re-assemble without re-download.
- **Per-user selection state = installer state dir** (user-decided
  2026-07-20): `~/.local/share/agent-bios/` (e.g. `selection.json`) — central
  tree is overwritten by push, personal zone is harvested; install state is
  the correct ownership class.
- **Source layout (Fork 1) = tagged-monolith hybrid** (independent FRONTIER
  judgment 2026-07-20, neutral blind packet, all cited anchors re-verified):
  `claude/CLAUDE.md` stays the sole TEXT authority; `domains.json` is the
  sole CLASSIFICATION authority; guides/hooks/agents are assigned at file
  grain in the same manifest. Physical per-domain split loses on the decisive
  axis: under domain proliferation the recurring operation is the boundary
  event (birth/split/merge) — tagging prices it as a one-file manifest diff,
  physical split as 4-tree file surgery (claude/, codex/, ko/ ×2) with ledger
  `placed_at` rewrites and KO translation fallout, paid repeatedly while
  boundaries are declared unstable; and cross-domain items are native under
  tagging (one anchor, N domains), while under physical split the D2 manifest
  becomes a second membership authority that can disagree with file location.
  - **Load-bearing condition**: the bijection/coverage gate (every bullet
    claimed by ≥1 domain and exactly one tier; every anchor resolves
    uniquely; non-vacuity guards) lands IN THE SAME CHANGE as domains.json —
    the gap between them is the silent-drop window (a reworded bullet
    vanishing from every subsequent push). The assembler asserts
    extracted-count == manifest expectation for the selection and dedups
    multi-domain anchors.
  - **Curator ergonomics**: generated read-only per-domain projections
    (build/domains/<name>.md) — derived views of the source authority,
    never hand-edited.
  - **One-time text prep before the manifest**: promote the two D5 slices
    (claude/CLAUDE.md:6, :113) to standalone bullets across all 4 trees,
    parity-checked, so bullet-grain extraction suffices.
  - **Change conditions (flip globals to physical split when ANY holds)**:
    (a) curation ownership partitions across teams needing per-path review
    routing; (b) same-file conflict pain in ≥3 consecutive push cycles
    despite append discipline; (c) anchor reassignment <~2%/quarter for two
    consecutive quarters while curators review only via projections.
    Migration at flip time = scripted partition by manifest (cheaper than
    splitting now).
  - **Falsification probe — EXECUTED 2026-07-20, verdict confirmed**: the
    builder-base→shell-ops split dry-run under the tagged layout measured
    **1 file (config/domains.json), ±11 lines, 0 corpus text files touched**
    (7 bullet reassignments + guide + hook + registry entry), gate GREEN;
    the partial-split negative control (guide moved without its router
    bullet) was caught by the router co-package gate. No re-judge needed.
    Bonus datum: shell-ops would carry ~3K tokens — above the granularity
    floor, so it remains a viable later split.
  - Adjacent gap flagged (layout-independent): EN↔KO parity checks guide-SET
    equality only — content-level KO drift of the globals is unchecked and
    widens with curation churn. Owned by D1/D2 implementation.

### Resolved: D6 = A, unified classification (user-approved 2026-07-20)
One classification pass covers both origins — the 110-bullet corpus + 13
guides AND the ledger's placed learning items — using the same domain
registry; ledger entries gain a `domain` field.
> Correction 2026-07-20: the ledger's `placed_at` (file + stable anchor)
> described by PLACEMENT-FRAMEWORK.md is null in the live artifact for all
> 50 placed entries — placement location exists only as free-text
> `implementation` hints. The domain field is therefore NOT deterministically
> derivable; it is filled by a judgment pass (run 2026-07-20) instead, and
> the framework's entry-shape description should be treated as aspirational
> until placements are re-keyed. **Implementation approved 2026-07-20**; order: slice prep
→ domains.json + bijection gate in the same change (includes the
classification pass with its user-approval gate) → assembler + entry
seeding + Codex marker-merge → onboarding TUI + canary → CI wiring.

### Design re-review record (2026-07-20)
Three independent adversarial reviewers (ops-reality, ownership/collection-
loop, corpus-partition lenses) ran against the resolved decisions: 20
findings (3 blocker / 10 high / 7 medium), every anchor re-verified against
the repo, zero rejected. Direction upheld (two-zone ownership, thin core,
opt-in, phased rollout); all fixes are folded into the amended sections above
(topology tree + settings merge-fragment, entry-file seeding + onboarding
canary, Codex marker-merge, collection posture, builder-base naming
unification, infra tier, slice mechanics, migrate/reconcile/novelty rules,
D4 assembly unit). Org-posture calls resolved by the user 2026-07-20:
collection = full automatic harvest; builder-base = one coarse domain;
plain-register rewrite deferred to Phase 2.

### Revised discussion order
ownership-separation axis (done) → D5 (done) → D3 (done 2026-07-19) →
adversarial design re-review + amendments (done 2026-07-20) → D1/D2
(mechanism — done 2026-07-20; source layout via independent FRONTIER
judgment) → D6 (done 2026-07-20) → **implementation in progress
(approved 2026-07-20)**.

## Motivation

Make the whole corpus (AGENTS.md / CLAUDE.md / guides — not just the
session-distill items) transplantable to other users by work domain. Example:
the "LLM And Capability Boundary" section plus its three guides (~7K tokens)
is dead weight for anyone not developing LLM pipelines; they should simply not
install that domain package. Extends design/session-distill/
PLACEMENT-FRAMEWORK.md: packages become the canonical truth unit; a user's
CLAUDE.md / guides / hooks / scripts become per-environment projections.

## Classification criteria — four tiers (infra added 2026-07-20)

- **core** (installed by everyone): removing it degrades any user's sessions.
  Work-independent thinking/judgment principles: Problem Solving, Decision
  Framing, Verification Discipline (principle part), Documentation Hygiene,
  basic tool safety (git, secrets).
- **domain** (installed by predicate): a domain is VALID only if a natural
  yes/no question about the user's work exists ("do you develop LLM
  pipelines?", "do you orchestrate multiple models/CLIs?") such that "no"
  makes the entire package safely omittable. No predicate → it is core, not a
  domain.
- **env/personal** (never packaged): person/machine/project facts (type E),
  language preference, local paths. Stays in memory / personal settings.
- **infra** (always installed, independent of domain selection; added by the
  2026-07-20 review): the machinery of the system itself — the
  session-distill-workflow guide + its launcher preset (no CLAUDE.md router;
  reached via config/agent-launch.toml), the collect-session hook
  registrations, install/verify tooling. Not core (not judgment principles),
  not a domain (per-user distillation is universal by premise — no valid
  opt-out question exists), not env-personal (shared procedural content).

Unit of classification is the **bullet/rule, not the section** — current
sections mix tiers (Tooling and Operational Safety holds core git/secret
rules AND cloud-CLI domain rules). Sections/files are reassembled as package
projections; matches the ledger's per-item granularity.

## Granularity rules

1. **No predicate, no split** — if the installation question cannot be
   phrased naturally, do not split.
2. **Omission gain > management cost** — split only when the omittable chunk
   is material (~≥1–2K tokens). A 200-token sliver with a manifest costs more
   than it saves.
3. **Co-use cohesion, empirically checked** — rules that fire in the same
   sessions belong together. Measurable against the archived 249-session
   corpus: relevance ≈100% of sessions → core; ≈0% for a user class →
   validated split. Validate predicates with data, not intuition.
4. **Dependency direction** — domain→core only; two domains needing each
   other are one domain. Target count: core + 7±2 domains.

## Preliminary mapping (superseded 2026-07-20 — kept for provenance)

> Domain names below predate the resolved D5: "coding" as its own domain and
> the learning-born "shell-cli-gotchas" are ABSORBED into builder-base; see
> "Resolved: D5" above for current names.

core (thinking/judgment/doc-hygiene principles — smaller than it looks) ·
coding (a domain itself — non-coding users exist: Coding Guidelines most,
coding-staged-workflow, mock-realization-boundary) · llm-pipeline-dev (LLM
And Capability Boundary + 3 guides; biggest omission gain) ·
multi-agent-orchestration (Multi-Model Workflow + cli-multi-model-workflow +
both prompting guides + review-request) · visualization-docs (Visual
Explanations + svg guide + implementation-map) · office-work (spreadsheet
bullet etc.) · plus learning-born domains (shell-cli-gotchas, git-ops-safety,
cloud-infra-deploy, state-lifecycle-ownership, docs-handoff…).

## Design-direction decisions (discussion prep — 2026-07-20)

Measured corpus to ground the discussion: `claude/CLAUDE.md` = 12 sections,
110 bullets, ~5.9K tokens. 13 guides (2K–18K each). Sections mix tiers (e.g.
Tooling and Operational Safety holds core git/secret rules AND shell/cloud
domain rules), which is why the unit question below matters.

Six forks, primary three first. Each has a recommendation to react to, not
derive.

### D1 — Packaging mechanism (load-bearing)
- **A. Physical split**: separate the corpus into per-domain source files;
  install assembles the selected domains. Cleanest boundaries; biggest
  restructure; breaks the single-canonical-file model and the parity gate's
  current shape.
- **B. Tag-and-project**: one canonical corpus stays; a manifest assigns each
  bullet/guide to domain(s); install projects the selected domains into the
  deployed files. Minimal file churn; reuses the token-gate + anchor
  discipline already built.
- **C. Section/guide-as-package**: promote existing sections and guides to be
  the package unit; a package = a set of sections + guides.
- **Recommendation: hybrid keyed by layer** — B for globals (bullet-level,
  because sections mix tiers) + C for guides (a guide is already a natural
  domain unit: cli-multi-model, llm-capability-boundary, svg map ~1:1 to
  domains). One mechanism per layer, each matched to that layer's grain.

### D2 — Where the domain assignment lives
- **A. Inline** in the corpus (frontmatter/tags). **B. Separate manifest**
  (`domains.json`: stable-anchor → domain).
- **Recommendation: B** — keeps prose clean (documentation hygiene),
  machine-owned and grep-auditable, reuses the parity gate's anchor approach.
  Risk: anchor drift (S3-12) — use the stable-phrase anchors the parity gate
  already enforces, and gate the manifest against them.

### D3 — User selection model
> **RESOLVED 2026-07-19** — chose **A (per-domain opt-in)**, not the earlier
> "C, ship A first". Phased rollout (technical roles first) makes self-select
> work for v1; presets defer to the non-technical waves. See "Resolved: D3" up
> top.
- **A. Per-domain opt-in** (install flag / TUI checklist). **B. Role presets**
  (developer / ops / researcher / minimal → domain bundles). **C. Both.**
- **Recommendation: C, ship A first** — presets are a thin layer once domains
  exist.

### D4 — Build-now vs convention-now (the G-4 call)
> **RESOLVED 2026-07-19** — the G-4 single-user basis below is VOID (500-user
> deployment). Answer is now staged and split by half (distribution: build the
> per-domain assembler now — amended 2026-07-20; collection loop: convention
> now). See "Premise change + resolved decisions" at the top.
- **A. Build the full projection/assembly tooling now.**
- **B. Establish the manifest + core/domain boundary now as convention; keep
  deploying the full corpus (everyone gets everything) behind a default-on
  "all domains" flag until a second consumer or a real need to slim appears;
  the manifest makes slimming a later config flip.**
- **Recommendation: B** — single-user, own-machine (G-4: delivery over
  assurance). The value now is the STRUCTURE (knowing core vs domain, being
  transplantable), not the mechanism. Build classifier + manifest +
  validation; defer the assembly filter.

### D5 — Core boundary (needs the user's judgment)
> **RESOLVED 2026-07-19** — see "Resolved: D5 — core boundary" up top. Mixed
> roles thin core to a thin-4 (plain-register rewrite deferred to Phase 2);
> technical-common content → a single "builder base" domain. The Domain list
> below uses superseded names ("coding", "shell-ops") — builder-base absorbed
> them (2026-07-20).
What every future user carries unconditionally. Candidate split from the
measured sections:
- **Core**: Problem Solving, Decision Framing, Verification Discipline
  (principles), Documentation Hygiene, and the security/safety core of
  Tooling and Operational Safety.
- **Domain**: LLM And Capability Boundary → llm-pipeline-dev; Coding
  Guidelines + coding-staged/mock guides → coding; Multi-Model Workflow +
  cli-multi-model/prompting guides → orchestration; Visual Explanations +
  Implementation Map + svg guide → visualization; tooling-gotchas → shell-ops.
- **Undecided, needs discussion**: Concept Economy (16 bullets — universal
  design discipline, or a coding-domain concern?); Global Preferences
  (language/scope — arguably env-personal, not core).

### D6 — Reconciliation with the learning ledger
The 50 placed learning items have layers but no domain; the existing 110
bullets + 13 guides were never classified. **A.** one unified classification
pass over both; **B.** keep learning-domain and corpus-domain separate.
- **Recommendation: A** — a bullet is a bullet regardless of origin; the
  manifest covers the whole deployed corpus and the ledger references the
  same domain names.

Discussion order (original — superseded 2026-07-19 by the "Revised discussion
order" up top): D4 (scope of the effort) → D5 (core boundary, the judgment
call) → D1/D2 (mechanism) → D3/D6 (follow-ons).

## Deferred (activate with the backlog, or later)

- Bullet-level classification pass of the whole corpus; per-item `domain`
  field in design/session-distill/ledger.json.
- Projection tooling (package → CLAUDE.md/guides/hooks assembly with the
  global token cap enforced at assembly time) — manual projection + a
  parity-style anchor gate is enough while there is one consumer; build the
  compiler only when a second consumer actually appears (G-4: delivery over
  assurance for single-user tools).
- Cross-domain items: primary domain + cross-reference; referenced by most
  domains → promote to core.
- **New tool targets: opencode and Cursor** (user-requested 2026-07-20).
  Extends the D1 cross-tool seam beyond claude/codex: per-tool emission in
  the assembler (verify each tool's instruction-file conventions empirically
  at implementation time — import support, global/project file locations,
  rules format), install/verify/uninstall surfaces, parity coverage for the
  new emissions, and an ownership-boundary realization per tool
  (filesystem-enforced vs marker-merge vs not-realizable). First scoping
  call when activated: emission-only (the corpus reaches the tool) vs full
  claude/codex parity (tiers, wrappers, review routes, launcher backend).
