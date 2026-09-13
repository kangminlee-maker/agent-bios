---
guide_id: session-distill-workflow
language: en
status: active
audience: author
use_when:
  - a session was launched with the Session distill preset (mission-injected)
  - the launcher nudge says enough sessions accumulated for a mining window
  - learning from LLM work sessions to improve the instructions and its application
  - promoting, incubating, or retiring items in the session-distill ledger
core_rules:
  - read Goal and desired outcomes before state files or pipeline work; use it to judge the run and its delegated work
  - the ledger is the SSOT for state; read it before touching the pipeline
  - placement follows PLACEMENT-FRAMEWORK.md, never ad-hoc judgment
  - every promotion passes an explicit user-approval gate
  - the canonical always surface is frozen to reductions; route additions to guides, skills, or session-level injection
  - close the window by updating mirrors, parity, deployment, and the nudge baseline
---

# Session-Distill Workflow

## Goal and desired outcomes — read first

Learn from the user's directly handled LLM work sessions so that
the user and future agents can correctly understand and explain what was learned,
apply it in relevant situations, and improve work quality, reliability, time,
and cost in line with the user's goals and priorities.

This goal applies across LLM providers and tools, including future integrations.
The collection sources currently supported are described under Stage 1.

Useful learning includes successful approaches, mistakes and corrections,
recurring friction, consequential exceptions, and the reasoning behind choices.
Compare it with existing knowledge: add what is missing, clarify or correct what
is inaccurate, improve what is not being applied, and preserve what works.
The novelty-focused screeners provide inputs to this broader goal; use the
retained session evidence for questions their candidate lists do not answer.

A run should produce:

1. **Grounded learnings.** Explain what happened, what was learned, why the
   evidence supports it, and its limits. Keep observed facts, interpretation,
   and unresolved uncertainty distinguishable, with traceable session evidence.
2. **Understandable, reusable content.** State the lesson, its rationale,
   application conditions and boundaries. For a decision principle, explain the
   competing values and the user's priority between them. Preserve concrete
   facts or procedures where generalization would lose useful meaning.
3. **Assessment of both meaning and application.** Check whether the lesson is
   correctly explained and supported, and whether relevant decisions or actions
   apply it appropriately. Assess expected benefit and unwanted effects;
   preserving an already-correct decision can be a good result. Use checks
   proportionate to the evidence and consequence, and distinguish observed or
   tested effects from proposed ones. An untested candidate may remain for
   review; neither a fluent explanation nor one suitable action proves both.
4. **Reviewable recommendations.** Show the relationship to existing rules, the
   proposed disposition and canonical home, the intended consumer, the expected
   benefit and cost, and the verification still needed. Give the user enough
   context to adopt, revise, retain, incubate, or retire the learning.
5. **Durable, verified application of approved changes.** Route accepted work
   through the placement framework into the guide, principle, memory, tool fix,
   gate, or other existing mechanism that reaches its consumer. Keep evidence
   and decisions in the ledger; report what was applied and verified and what
   remains open. A review-ready proposal and an applied change are distinct
   outcomes, and promotion still requires explicit user approval.

Judge success by useful, justified learning and its appropriate application.
Candidate counts and added text measure output volume. A supported decision to
keep existing content, or a clearly bounded unresolved finding, is also useful.
Carry this goal and the relevant outcome criteria into delegated work, then
assess its results against them before presenting the run as complete.

**Requires an agent-bios checkout.** This runbook edits the instructions themselves, so it
names repo paths and runs repo scripts. On a packaged install those do not exist:
say so and stop rather than following steps you cannot execute.

Runbook for a session-distill run: mine recent main-context sessions,
verify candidates, place them through the framework, and apply with the user.
Everything durable lives in the agent-bios repo.

## Read next (SSOT)

1. `design/session-distill/ledger.json` — the initiative's state. Every item
   carries its status (placed / incubating / incubating-G / absorbed /
   adopted-no-text), strength, and provenance, so what is open, what was
   promoted, and what is still incubating are all queries against this file.
   Read state here and nowhere else: a count or a status written into prose is
   correct on the day it is written and silently wrong afterwards.
2. `design/session-distill/versions.json` — authoring provenance mapping each
   closed mining window to its commit. Private rollback selects an installed
   `baseline_ref` through the instructions plan; this registry is not that authority.
3. `design/session-distill/PLACEMENT-FRAMEWORK.md` — the placement framework
   (typology A–G, layers, admission bars, lifecycle). Apply the current
   `AGENTS.md` reductions-only rule and `SURFACES.md` delivery contract when
   choosing a destination; the framework does not authorize global growth.

## Stage 1 — Mine (pipeline in `session-distill/`)

The current collectors read Claude Code and Codex session histories.
Run in order; each stage reads the previous stage's `out/`:

1. `census.py --end YYYY-MM-DD` — enumerate from both providers'
   history.jsonl; keep only directly-handled main-context sessions by
   transcript-side provenance (dispatched = Codex source=exec /
   Claude sidechain/sdk-cli/agentId).
2. `digest.py` — one secret-redacted digest per session with deterministic
   6-criteria signals. Screen ALL digests; triage orders, never drops.
3. `batch.py` — the baseline blob (`claude/CLAUDE.md` + every guide, the
   repo's canonical instructions) and per-provider batches; writes
   `out/batch_index.json`, which the screeners take as their `args`.
4. Provider-affine screening against that baseline: `screen-claude.js`
   (Claude sessions; a Workflow script — pass the index as `args`, one
   WORKHORSE screener per batch) and `screen-codex.py` (Codex sessions;
   one hermetic read-only `codex exec` per batch, packet on stdin). Novelty
   is judged against real baseline text, not memory. Then `collect.py`
   unions the two outputs into `out/candidates-all.json` and fails when a
   provider's screened set is smaller than its batch.
5. `consolidate.js` (Workflow; `args` = baseline, candidates path, count,
   and the ledger's `{id, lesson}` list) — dedup + independent novelty
   verification, then a match pass naming which survivor recurs an
   existing ledger entry. Rank by strength (recurrence × materiality),
   never by self-reported confidence. Save its return value as
   `out/consolidated.json`.
6. `bundle_final.py` — tiered bundle. `merge-ledger.py --window-end <date>`
   (dry-run; `--apply` writes) merges survivors into `ledger.json`: a
   recurrence gains the window's sessions under `recurrence`, a new lesson
   becomes a `candidate` entry — so recurrence accumulates across windows
   and incubated items promote when they re-occur.

## Stage 2 — Review with the user

- Produce a Korean review edition as a local repo file (this user cannot
  access web artifact renders): per item, principle, why it was selected,
  verdict, and placement recommendation, with stable IDs.
- Decisions, in order: ① selection against the promotion bar (recurrence ≥2
  or single-event high materiality — irreversible / verification-corrupting /
  security); ② PROPOSED resolutions (never silently resolved); ③ G-candidate
  adoption. Record every decision in the ledger.

## Stage 3 — Classify and apply (§P8)

- Walk each accepted item through the framework pipeline: type (A–G) →
  leftward reformulation (fact→principle, knowledge→structure) → layer →
  consumer check (hermetic dispatch and scripts read no prose) → admission
  bar → token estimate. Ambiguity stays PROPOSED for the user.
- Apply canonical-first, on a branch, stepwise commits: canonical guide text
  → reductions to the canonical always surface (delete, merge, or move rules
  out; additions belong in guides, skills, or session-level injection) → other guides →
  hooks (derive injected text from the canonical guide; read-only, never
  blocking) → enforcement in owned wrappers (loud failures; keep
  stdout/stderr channel contracts) → codex/ + ko/ mirrors.
- Verify per layer, not just by diff: enforcement/gate fixture tests
  (non-vacuous — known-bad must fire), hook trigger positive/negative sets,
  `gates/check-parity.sh` exit 0 unpiped, prompting-target gate, then
  `bash install.sh install` from this checkout to store the changed private
  release and `bash install.sh verify` to verify it. Activate a new configured
  session through `agent-launch` and check its delivery evidence separately;
  installation does not activate content or change an existing session pin.

## Stage 4 — G-pass (principles, not directives)

- Mine user-correction turns (deterministic marker extraction over digests)
  and initiative-arc retrospectives; add upward distillation over newly
  placed directives (≥3 sharing one value → parent-principle candidate).
- G evidence bar is higher: ≥3 independent consistent resolutions, or one
  user-confirmed arc retrospective. A principle must name the tension, the
  ordering, and what it forbids. For an under-applied gap (rule exists but
  behavior does not follow), prose repetition is invalid — list it for the
  behavior battery and change the surface instead.

## Stage 5 — Close the window

1. Ledger: statuses to placed (with implementation paths) / incubating;
   dated corrections for anything refuted.
2. Write a new timestamped completion record under `design/session-distill/`
   following `AGENTS.md`; incidental finds become next-window candidates.
3. Register the instructions version: append {version = window end, commit = the
   instructions-close commit} to `design/session-distill/versions.json` for authoring provenance. Private rollback selects an installed `baseline_ref`
   through `agent-bios instructions plan`; the window registry does not authorize a
   global-file rollback. Then run
   `python3 session-distill/update-state.py --window-end <date>`
   (nudge baseline) and `instructions-state.py project` (launcher status panel).
4. Merge the branch, push, and confirm the private release from this checkout
   (`bash install.sh verify`); report stored-state and session-delivery evidence
   separately.
