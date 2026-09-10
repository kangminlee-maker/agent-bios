# Session-Distill initiative — SSOT handoff

> **Added 2026-08-05, and the only text below this line that is not July's.**
> This is a July record, kept as written. Its figures and paths are claims about
> the tree on their dates — the pipeline has since moved out of `scripts/`, and
> the ledger has grown past every count named here. For current state read
> `design/session-distill/2026-08-05T1139--fcea430--re-derivation.md`, or
> re-derive from the artifact:
> ```bash
> python3 -c "import json,collections;e=json.load(open('design/session-distill/ledger.json'))['entries'];print(len(e),collections.Counter(x['status'] for x in e))"
> ```

Last updated 2026-07-18. This is the single source of truth for the whole
initiative. Read this first in any new session before touching the pipeline.

## The goal (verbatim intent, from the Codex kickoff 2026-07-16 09:14)

Mine the user's last ~3 weeks of local Claude Code / Codex sessions — only
**directly-handled main-context** sessions, not dispatched subagents/exec —
for learnings **not already in AGENTS.md / CLAUDE.md / guides**, convert them
to **general principles**, and produce a **human-reviewable candidate bundle**
the user selects from before anything is written to the corpus. Value criteria:
① high token spend to reach a decision ② rollback / wrong-then-corrected
③ repeated re-exploration a guide could shortcut ④ recurrent errors ⑤ rare but
high-cost events ⑥ decisions that clearly raised speed/cost/design quality.

Extraction is the goal; the pipeline is the means. Repository edits (§P8 apply)
are a separate, explicitly-approved step.

## Current state (DONE)

A working **v1 pipeline** was built and run end-to-end. It produced the first
real deliverable: a verified, tiered candidate bundle.

Numbers: **249** eligible main sessions (232 Claude + 17 Codex, 21-day window
ending 2026-07-18) → 85 raw candidates (provider-affine screening) → 76
consolidated clusters → **74 survive** independent novelty verification
(45 novel + 29 extend-existing), tiered by strength (7 at strength-4, 41 at
strength-3, 26 at strength-2).

The deliverable: `scripts/session-distill/out/BUNDLE.md`. A Korean review
edition for item-by-item selection (IDs S4-01…S2-26, per-item rule-applied
placement recommendation) is at `design/session-distill/BUNDLE-ko-review.md`
(2026-07-18); the user reviews it before the promotion-scope and placement
decisions below. The full framework classification pass ran 2026-07-18
(3 sonnet agents + main review, 11 corrections): results in the review doc's
annex and seeded into `design/session-distill/ledger.json` (74 entries,
status=candidate). Distribution: enforcement 3 / hook 6 / guide 33 / global 32
(bar-passing global ≈735 tokens > 500 cap — resolve via selection + G-2
absorption), promotion bar passed 43/74, PROPOSED 13, G-candidates 4 (annex).

## Pipeline (all durable in `scripts/session-distill/`)

Run order (each reads the previous stage's `out/`):
1. `census.py` — enumerate from each provider's history.jsonl, confirm
   transcripts, classify main-vs-dispatched by transcript-side provenance
   (Claude: entrypoint=cli + non-sidechain + human turn; Codex: source=cli|vscode,
   exclude source=exec/originator=codex_exec). → `out/census.json`
2. `digest.py` — one compact, secret-redacted digest per session + deterministic
   6-criteria signals. Digests total ~600K tokens, so **screen all — triage
   only orders, never drops** (a 1-turn session held a top learning). → `out/digests.json`
3. baseline blob — `claude/CLAUDE.md` + 12 guides concatenated (~29.6K tokens),
   handed to screeners so novelty is judged against real baseline text.
4. `screen-claude.js` (Workflow, sonnet, 20 batches) + `screen-codex.js`
   (ultracode-for-codex, gpt-5.6-sol, 2 batches) — provider-affine screening.
   → `out/candidates-claude.json`, `out/candidates-codex.json`
5. `consolidate.js` (Workflow: 1 opus clusterer + per-cluster sonnet verifiers) —
   dedup + independent novelty verification; self-reported confidence is
   provider-relative, so rank by strength (recurrence × materiality), not confidence.
   → `out/consolidated.json`
6. `bundle_final.py` — tiered Markdown. → `out/BUNDLE.md` (+ `bundle.py` legacy).

`out/` heavy intermediates are gitignored; BUNDLE.md/BUNDLE.json are kept.
To re-run for a fresh window: `census.py --end YYYY-MM-DD` then re-run 2→6.

## Corpus archive (the R1 preservation step)

`~/.local/share/session-distill-archive/census-2026-07-16/` — 29,293 in-window
files (8.66 GB source) + both history.jsonl, per-file SHA-256 `manifest.jsonl`.
Built to stop attrition (4/265 ids were already irrecoverable). The current v1
census reads live provider stores, not the archive; wire it to the archive if
re-runs must be reproducible against a frozen corpus.

## Selection decisions — RESOLVED 2026-07-19

Decisions 1–3 were made with the user (recorded per-entry in `ledger.json`):
①  bar-passing default approved → 43 selected; ② PROPOSED 13 resolved
(S3-12, S3-17, S2-14 user-promoted; rest per recommendation) → 46 selected /
28 incubating; ③ all four G principles adopted (G-1 no-text mechanization
direction; G-2/G-3 global principle lines absorbing S4-03·S3-06·S4-07·S3-16
as guide instances; G-4 as ~20-token extension of the Verification
Discipline proportionality bullet) → final: 49 selected, 78 ledger entries.
## §P8 apply — COMPLETED 2026-07-19 (branch session-distill-p8)

All 49 selected items placed and live-deployed via `agent-bios install`:
tooling-gotchas guide created (20 bullets incl. budget-displaced items);
global CLAUDE.md +500 tokens exactly (hard gate PASS; G-2/G-3/G-4 principle
lines, five compact extensions, router); five guides extended (17
placements); PreToolUse hook with six read-only injections (trigger test set
6+7, fired live in-session); two wrapper enforcements (codex-run dispatch
audit log + unpinned-model warning, log-file only to preserve the channel
contract; codex-helm review scope manifest) with shim/dry-run fixture tests;
codex/ + ko/ mirrors regenerated, two new parity anchors, check-parity.sh
PASS exit 0; prompting-target gate PASS. Ledger: 49 placed / 28 incubating /
1 adopted-no-text, implementation paths recorded. Deployed wrapper backups:
~/.codex/bin/*.bak-p8; settings backup ~/.claude/settings.json.bak-p8.
Incidental finds during verification (grep resolves to ugrep on this
machine; codex-helm dry-run blocks on inherited idle stdin — pre-existing,
documented in install.sh) are candidates for the next pipeline window.

## G-pass v1.5 — ran 2026-07-19, candidates PENDING user decision

Deterministic correction-turn extraction over the digests' timelines (48
excerpts / 29 sessions; note the timelines sample only ~60 turns/session, so
full-transcript correction mining needs a digest.py v2 pass next window).
Clustered into four G candidates, recorded in ledger.json as PROPOSED:
- **G-5** share/use-over-restrict (4 independent sessions; would absorb
  S2-17) — meets the evidence bar; recommend adopting into Decision Framing.
- **G-6** delegation sizing under-applied gap (5 sessions correcting a rule
  the guide already states) — text repetition is invalid per framework;
  recommend behavior-battery listing + next-window observation.
- **G-7** design done-when = decision-free implementation (2 sessions, below
  bar) and **G-8** agent under-proposes cross-verification (weak evidence) —
  both incubating.
Branch merged to main and pushed (session-distill-p8 also pushed).

## Launcher integration — shipped 2026-07-19/20

The initiative is productized in the launcher: a Session Distill area on
the root screen (split panel + hub) shows the applied corpus version and
mechanism counts (from `corpus-state.py project` →
`~/.local/share/agent-bios/corpus-status.json`), a packages screen (v1:
single core corpus; the list shape awaits the domain-packaging backlog), and
Versions & rollback backed by `design/session-distill/versions.json`
(learning CONTENT versions = corpus commits, distinct from system
deployment; rollback re-deploys globals/guides/hooks only). The
`session-distill` preset injects the workflow mission into the launch
contract on both hosts, and the launcher nudges when provider history grows
past `[session_distill].nudge_after` since the last window
(`update-state.py` baseline). Window close now also appends to
versions.json (workflow guide stage 5).

## Pending decisions (historical — superseded by the section above)

1. **Promotion scope** — promote strength-4 (7) only, or through strength-3 (48)?
   All 74 would blow the corpus token budget.
2. **Placement reality-check** — screeners proposed 49/74 for "global CLAUDE.md",
   but the repo rule is *only situation-recognition failures belong global;
   procedures/thresholds/examples belong in scoped guides.* Most (pipefail,
   grep -a, zsh idioms) must move to guides (or a new tooling-gotchas guide).
   The token budget cannot absorb 49 global bullets.
2b. **Consumption-layer governance (user-decided 2026-07-18)** — finalized in
   `design/session-distill/PLACEMENT-FRAMEWORK.md`: 7 layers (enforcement,
   post-hoc verification gates incl. shellcheck/parity-style checks, hook
   injection, guides, global, memory, incubator ledger), routing tree,
   enforcement bar (pipefail fails it; S4-05 dispatch-scope fix and S4-04
   backing-model logging pass), hook charter, model-neutrality principle
   (skills = last-resort carrier only, after judging the content justifies
   per-model authoring cost), consumer-coverage rule (hermetic
   dispatched reviewers read only their packet), and the promotion/retirement
   lifecycle with the incubator ledger. Placement decisions in §2 must follow
   that framework.
3. **§P8 apply** — after selection, edit English canonical (`claude/`) → regen
   `codex/` mirror + `ko/` → run `scripts/gates/check-parity.sh` + prompting-target
   gate. Separate, explicitly-approved step. Nothing is applied yet.
4. **Design-doc disposition** — see below; demote to exploration record (already
   relocated) is recommended.
5. **BACKLOG: corpus domain packaging** — repackage the ENTIRE corpus (not
   just learnings) into installable work-domain packages (core / domain /
   env-personal tiers, bullet-level classification, installation-predicate
   criterion). Design captured in `design/corpus-domain-packaging.md`;
   user-deferred 2026-07-19.
6. **BACKLOG: TUI review area** — dedicated Review mode in the launcher:
   on-the-spot capability install (onto/ultracode via the capabilities
   registry), pluggable third-party review services (user-owned registry),
   per-service backend/model choice (codex-cli / claude-cli / api). Design
   captured in `design/tui-review-area.md`; user-requested 2026-07-20.

## The 12-round design review — what happened and the lesson (context)

Before v1, one Codex session (Day 1) produced a 140 KB "production-grade"
pipeline contract; an Opus session (Days 2–3) ran a 12-round dual-track
cross-family review that grew it to 193 KB. **This was over-engineering + a
fixed-point-chasing tail**: the architecture was sound by round 2, but each
hand-edit to a hyper-interconnected prose contract perturbed adjacent clauses
the next round caught (a prose contract has no compiler). Root diagnosis: the
effort optimized assurance over delivery for a single-user, own-data, own-machine
tool — kernel isolation, hypergeometric audits, egress proofs were disproportionate.
The 3-day cost is itself a textbook instance of the user's own criteria ①/② and
belongs in the bundle as a meta-lesson.

Design record (relocated from /tmp, durable, isolated per doc-hygiene rules):
- `design/session-distill/DESIGN-v13-exploration-record.md` (193 KB, hash
  `d545c20c…`; status was `DESIGN_REVIEWED_PENDING_USER_GATES`, closed via
  user-accepted residuals). Reusable ideas: provenance classifiers, episode/
  evidence-grade model, current-gap-as-sole-admission-authority, human-approved
  bundle, provider-affine privacy. **Do NOT resume the review tail.** v1
  supersedes it as the delivery path.
- `design/session-distill/REVIEW-round1-ledger.md` — round-1 over-engineering
  verdicts (8 clusters).
- `design/session-distill/REVIEW-closure-punchlist.md` — the 4 accepted residuals
  + full round arc.

User decisions already made during the design review (still valid if the design
is ever revived): privacy route C + subscription-OAuth-token (`claude setup-token`)
preferred over API key; (n,c)=(46,1) acceptance rule; indefinite archive/bundle
retention; recurring rolling-window; Method-B route-lost stays open/upgradeable;
32 orphan ultracode temp dirs verified + deleted 2026-07-18.

## Environment facts a fresh session needs

- Repo: `/Users/kangmin/Documents/agent-bios`, branch `main`, canonical = `claude/`
  (English), `codex/AGENTS.md` mirrors with one declared exception, `ko/` reference,
  `scripts/gates/check-parity.sh` is the parity gate. Global text has a strict token budget.
- Installed: ultracode-for-codex 0.6.0 (`/opt/homebrew/bin/`), Codex CLI 0.144.4,
  Claude CLI 2.1.211. Default shell zsh. macOS `sys/event.h` has only
  NOTE_EXIT/FORK/EXEC/REAP/SIGNAL/TRACK (no group/session notify).
- Provenance: Codex dispatched = `source=exec`/`originator=codex_exec`; Claude
  dispatched = sidechain / entrypoint=sdk-cli|review / agentId set.
- Screening is provider-affine (Codex sessions → ultracode; Claude → Workflow
  sonnet) — own data, own machine, digests are secret-redacted.

## Top 7 (strength-4) for promote-first, if scope is minimal
pipe exit-code masking (pipefail/PIPESTATUS) · grep binary-heuristic false
no-match (grep -a/ripgrep) · zsh-vs-bash idiom silent misbehavior · normalize
cost comparisons to a common basis · own+teardown full subprocess/handle
lifecycle · confirm the real dispatch chain before trusting "different-kind"
verifier diversity · diff-review silently omits uncommitted/untracked subject.
