# C-1 / C-2 decision session — KICKOFF (HISTORICAL RECORD)

> **SESSION COMPLETE — 2026-07-26.** Both C-1 master levers and all four C-2 questions
> were decided. The outcomes live in `ECOSYSTEM-ARCHITECTURE.md` (the two levers, the five
> ecosystem questions resolved against them, and the foundational contract) and in
> `DESIGN.md` (the four adapter-split decisions). This file is kept only as the record of
> how the session was framed — it is no longer a "start here."

Purpose: settle the **two master levers** of the domain-package ecosystem (C-1), then
propagate them into the **four open adapter-split questions** (C-2). Both are user
decisions — the assistant's job is to frame them in outcome terms, not to pick.

Prepared 2026-07-26. Everything below was verified against real code or is a recorded
review finding; do not re-derive it from scratch.

## Read first, in this order

1. `design/adapter-split/ECOSYSTEM-ARCHITECTURE.md` — the unified architecture and the
   five open decisions, each framed as a *kind* of problem.
2. `design/adapter-split/DESIGN.md` — the adapter-split origin plus the dual-provider
   review that overturned its first draft.
3. `design/adapter-split/architecture-draft.html` — the diagram, if a visual helps the
   conversation.

## Settled — do not re-open

- **The three threads are one architecture.** adapter-split, finer domains, and
  multi-author versioned packages resolved into: a general core engine + composable
  `@author/domain@version` packages + the learn!/distill! feedback loop.
- **The git-fork mechanism is dead.** Two independent frontier reviewers (Claude and
  gpt-5.6-sol), both re-deriving from code, converged: `package.json` conflicts on every
  release (reproduced with `git merge-file`, exit 1), and the shared installer's `update`
  sends a fork user to core, silently disabling their upload. A multi-author ecosystem
  cannot be a fork anyway.
- **The day1 sink is a protocol, not two config values** — `X-Hook-Token` auth,
  `learning_id` dedup, a 400/413 permanent-drop policy, the JSON shape, and a single
  sink-agnostic watermark are all baked into the shared transport.
- **Deployment config must be user-owned and never deployed.** A shipped-and-verified
  config gets clobbered on update and then fails its own verification.
- **agent-bios is not company-deployed.** Only the author uses it; npm publishes reach
  ~1 user and there is no fleet to migrate. Structural change is cheap right now — and
  there is no demand pressure forcing openness yet.

## C-1 — the two master levers

Every remaining ecosystem question hangs off these. Ask them in outcome terms.

**Lever 1 — how open, how soon?** Single/org authorship ↔ third-party/public.

- *Single or org only:* distribution can stay a local convention, conflicts are solved by
  namespacing alone, trust is a non-issue, and granularity can stay coarse. Almost
  everything else becomes deferrable.
- *Open to third parties:* a registry, a trust model, a real precedence engine, and
  signing all become required, and several of them are retrofit-hard.

**Lever 2 — prose-only or code-carrying packages?**

- *Prose only:* a bad package is bad advice — recoverable, reviewable by reading. Trust,
  safety, and composition bars stay low.
- *Code-carrying (hooks, scripts):* a package can execute, so sandboxing, signing, and a
  security review become structural requirements rather than nice-to-haves.

**Recorded recommendation** (from ECOSYSTEM-ARCHITECTURE, for the user to accept or
reject): **prose-first, single/org for now**, fixing only the cheap-but-retrofit-hard
foundations — the package identity unit (`@author/domain@version`), the manifest shape,
and the composition contract — while leaving registry, signing, and a conflict engine to
proven demand. Rationale: the hard part is content and classification, not plumbing, and
sparse empty packages are the failure mode to avoid.

### What each lever unlocks

| Open decision | If single/org + prose | If open + code |
|---|---|---|
| Distribution | local convention now; npm later if sharing appears | registry or npm scoped, decided up front |
| Conflict / precedence | namespacing is sufficient | a real precedence engine is required |
| Trust / signing | defer entirely | foundational, retrofit-impossible |
| Domain granularity | stay coarse, split on evidence | pressure to pre-fragment |

## C-2 — the four adapter-split questions

Take them **after** C-1; two of them mostly inherit their answers.

1. **Fork vs npm-dependency wrapper.** The user chose fork on 2026-07-23, before the
   review. Re-decide with the evidence above — review strongly recommends the wrapper
   (day1 preset + a thin wrapper depending on core; bin stays `agent-bios`).
   *Largely settled by C-1: a multi-author ecosystem cannot be a fork.*
2. **Sink scope.** (a) Keep it day1-shaped, default-off with a configurable endpoint, or
   (b) define a real sink-adapter contract (`sink_id`, per-sink watermark, auth mode,
   idempotency, retry policy, backlog resend). (a) is recommended while day1 is the only
   org. *Directly downstream of Lever 1.*
3. **Third-party scope.** Is the promise one-way ingest only, or a full own-corpus
   curation loop? The curator pipeline is currently org-**data**-coupled — `build-promotions`
   emits this repo's manifest and the installer prunes using the package's
   `promotions.json` — so a third party's own loop needs overlay-owned ledger and
   promotions, or the promise has to be narrowed.
4. **Pre-existing packaging gaps** — fix now or defer? Both block the general-product
   goal regardless of the above: `learn!` capture may not run after an npm-only install
   (the guide invokes `scripts/collect-learning.py` from the cwd, and the installer never
   puts it on a PATH — an `agent-bios learn` subcommand would fix it), and npm `files[]`
   omits the curator scripts, so "the curator pipeline ships in core" is false on npm.

## How to run the session

- Frame both levers as consequences, not jargon — what changes for the user, what it
  costs, what risk it carries, and what becomes hard to undo later.
- Do not implement anything in this session. The deliverable is decisions recorded in
  `ECOSYSTEM-ARCHITECTURE.md` and `DESIGN.md`, plus the foundational contract written
  down if C-1 lands on foundations-now.
- If design drafting follows the decision and two frontier providers are reachable, the
  corpus rule calls for dual-provider drafts from one blind packet. codex/gpt-5.6-sol is
  OAuth-backed, so that costs nothing extra and needs no spend approval.
- A decided lever should be written into the doc **with its date and rationale**, so the
  next reader inherits the decision rather than the debate.

## Downstream items waiting on this

- `design/reviewer-registry/DESIGN.md` — pluggable reviewers inherit Q1–Q3 from these
  levers; sequence it after, not before.
- Role presets and the plain-register core rewrite.
- opencode and Cursor assembler targets.
