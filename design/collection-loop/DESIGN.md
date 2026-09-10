# Collection loop — DESIGN (SSOT)

Status: **Phase 0 + Phase 1 BUILT and verified 2026-07-20 (all gates green,
end-to-end proven on a scratch CLAUDE_CONFIG_DIR); next: Phase 2 (transport) —
gated on the mandatory adversarial endpoint review BEFORE code.** All five
design forks were user-resolved on 2026-07-20; the discussion record (forks,
downsides, corrections) is archived in `DISCUSSION-2026-07-20.md`. Terminology
follows `LEXICON.md`. This file is the single source of truth for current
design and the implementation plan.

**Corrections applied during the Phase 1 build (2026-07-20):**
- The Phase-0-frozen record id field `distill_id` was renamed to
  **`learning_id`** (schema + all fixtures + `check-learning.py`). Rationale:
  the artifact is a *learning* (`LEXICON.md`) and `distill` now names the heavy
  pipeline, so `distill_id` was a cross-concept collision; the ledger uses `id`
  (never `distill_id`), so nothing was lost; Phase 1 step 4 already specified
  `learning_id`; no records existed yet, so the rename is data-safe.
- The flow guide is **`learning-flow.md`** (guide_id `learning-flow`). The
  hyphenated heavy-subsystem alias is LEXICON-deprecated (`check-lexicon.py`
  blocks it), so the light-flow identifier family stays on the `learn`/`learning`
  root: `learning-flow.md`, `collect-learning.py`, `learnings.md`,
  `learnings.jsonl`, `learning.schema.json`.
- The submit tool `scripts/collect-learning.py` is **repo-relative** (reuses
  `check-learning.py` as the single validation source). Universal PATH
  deployment + config bundling is deferred to Phase 2 (transport), so Phase 1
  runs where the agent-bios clone is present — matching the heavy flow and the
  "installs from clone until npm publish" state.

## Goal

Close the loop the shipped distribution half (see
`design/corpus-domain-packaging.md`) deliberately deferred: a user's
session **learning** (the per-session artifact) — captured by the light
**session learning** flow (`learn!`), distinct from the heavy **session
distill** curation pipeline (`distill!`; see `LEXICON.md`) — must (a) apply
to their own account from the next session, and (b) reach the organization
for curation and redistribution.

## v1 done-when

A learning made in a user session lands in that user's
`~/.claude/personal/learnings.md` and loads in their next session (via
the guaranteed `@personal/learnings.md` import); the same artifact
reaches the dashboard Postgres through `POST /api/ingest/learnings`; a
curator exports it as ledger-compatible JSON and promotes it through the
existing curation procedure; the next push includes it and the user-side
migrate rule clears the personal copy — the full round-trip demonstrated
end-to-end on one real machine.

## Architecture (round trip)

```
user session ──learn!──▶ slim session learning flow (user-approved, single-session)
  ├─▶ prose → ~/.claude/personal/learnings.md   (loads next session via @import)
  └─▶ JSON record ──POST /api/ingest/learnings──▶ dashboard Postgres (raw, verbatim)
        └─ on failure → ~/.claude/hooks/pending-learnings.jsonl (bounded retry)
curator ──export (ledger-compatible JSON, by domain/date)──▶ existing curation
  ──promote──▶ existing packaging pipeline ──push──▶ all users
  └─ promotion manifest ──▶ user-side migrate rule clears the personal copy
```

## Resolved design (user-approved 2026-07-20)

- **D1 — Personal write path** (was F1): the `learn!` trigger runs a slim
  in-session session learning flow; ALL learning types land as prose user-side
  (mechanization deferred to curation). Prose accumulates in the
  automation-owned `~/.claude/personal/learnings.md`; the entry
  CLAUDE.md carries a guaranteed `@personal/learnings.md` import (added
  to the assembler seed; existing installs get the line ensured once on
  first learn!). Ownership separation is the point: promote→migrate cleans
  the automation's own file and never edits the user's hand-written
  Personal section. **Fact (verified vs `scripts/assemble.py`)**: files
  under `personal/` do NOT auto-load — only the entry file plus explicit
  `@`-imports; the import line is therefore load-bearing, not cosmetic.
- **D2 — Transport** (was F2): reuse the org's existing ingest server
  (`ai-litmus.day1co.kr`; repo `~/Documents/day1co-ai-usage-dashboard`;
  Next.js + Prisma/Postgres on Cloud Run). Per-user `X-Hook-Token` auth is
  already provisioned on all ~500 machines and the server derives identity
  from the token (client-supplied email is not trusted). New sibling
  endpoint `POST /api/ingest/learnings` (the sessions endpoint's rigid
  Zod schema is NOT reusable); external exposure requires a
  `PUBLIC_API_PATHS` allowlist entry + LB url-map regen (exact-match only).
  Client keeps a SEPARATE pending queue `pending-learnings.jsonl` (the
  session queue is capped at 500 lines; never compete with it).
- **D3 — Central reception + curation** (was F3): upload payload and
  curator export format = ledger-compatible JSON; `domain` (D6 vocabulary)
  is the curation join key; review/redistribution reuse the existing
  bundle-classification procedure, domains gate, and packaging pipeline.
  Three refinements are part of the design: **(A)** a `schema_version`
  field in every payload; **(B)** an `unclassified` domain escape value
  (curator assigns later — users are never blocked at capture time);
  **(C)** the server preserves the raw uploaded JSON verbatim
  (reinterpretable after format evolution).
  **Correction 2026-07-20 (Phase 0 review):** the earlier "domain = D6 ∪
  `unclassified`" wording was too narrow for the ledger-compatible goal — 4
  real ledger entries (`S3-07`, `S2-17`, `G-5` = `core`; `S3-39` = `infra`)
  already use *tier* names as `domain` values for cross-cutting lessons. The
  frozen rule is therefore **domain ∈ D6 domain keys ∪ tier names ∪
  `unclassified`** (all three drawn from `config/domains.json`; no new
  vocabulary introduced). `core` (a genuinely cross-cutting lesson) stays
  semantically distinct from `unclassified` (not yet triaged), so refinement
  B is unchanged.
- **D4 — Lightweight per-user flow** (was F4): regular users get a bounded
  single-session session learning flow (no Workflow fleets), gated on the
  existing user-approval convention; the heavy mining pipeline remains a
  curator/power-user tool.
- **D5 — Type-G scope** (was F5): general-principle manufacture is
  curator-only in v1. Users record principle-ish observations as prose
  (harvested like everything else); hand-writing personal principles in the
  user-owned zone stays free; only automated principle-grade promotion is
  central.

## Inherited constraints (resolved elsewhere — design within these)

- Two-zone topology, FULL automatic harvest of `personal/*`,
  secret-redaction floor, human curation gate: `design/corpus-domain-packaging.md`.
- Derived rules: promote→migrate is USER-side off a promotion manifest in
  the push; retire→reconcile correction feed; **novelty judged against the
  FULL canon, not the installed subset** (wire this into Phase 3 — curator
  screening still compares against the deployed baseline today).
- Typology A–G, routing tree, admission tests, lifecycle:
  `design/session-distill/PLACEMENT-FRAMEWORK.md`. The typology gains a
  two-column org overlay (user-side landing / curator-side routing) in
  Phase 1.

## Key reference points (verified 2026-07-20)

agent-bios (this repo):
- `scripts/assemble.py` — `ENTRY_SEED` (entry CLAUDE.md seed; gains the
  `@personal/learnings.md` line), assembler + `scripts/test-assemble.sh`.
- `design/session-distill/ledger.json` — the ledger format to stay
  compatible with: top-level `{schema, framework, window, entries[]}`;
  entries carry `id`, `lesson`, `strength`, `verdict`, `criteria`,
  `supporting_sessions`, `domain` (D6), `classification{type, layer, …}`.
- `config/domains.json` — D6 domain vocabulary + tiers;
  `scripts/check-domains.py` is the gate.

day1co-ai-usage-dashboard (server side):
- `src/app/api/ingest/sessions/route.ts` — the sibling-route pattern to
  follow; `src/services/auth.service.ts` — `authenticate()` (token→email).
- `src/services/raw-ingest.service.ts` + `RawIngestEvent`
  (prisma/schema.prisma) — verbatim JSON envelope (refinement C).
- `src/lib/public-surface.ts` — `PUBLIC_API_PATHS` allowlist;
  `scripts/infra/ingest/generate-url-map-rules.sh` + `setup-lb.sh` — LB
  exposure.
- `templates/hooks/collect-session.js.tpl` — hook transport/queue pattern
  (token file `~/.claude/hooks/token`, ingest-url file, pending-queue
  drain). **Ownership boundary**: the hook is dashboard-owned — do NOT
  patch it for learning uploads; the learning client is agent-bios-owned with
  its own queue and POST.

## Implementation plan (Phases 0–4)

- **Phase 0 — schema freeze** [agent-bios] ✅ 2026-07-20: learning record
  spec as a JSON Schema (ledger-compatible fields + `schema_version` +
  `domain` = D6 ∪ `unclassified` + provenance). SSOT lives in agent-bios; the
  dashboard mirrors only minimal validation. Verify: fixture records validate;
  a deliberately broken fixture fails (negative control).
  **Artifacts**: `config/learning.schema.json` (v1; domain *membership*
  deliberately enforced by the gate against `config/domains.json`, not frozen
  in the schema, so vocabulary evolution needs no `schema_version` bump);
  `scripts/check-learning.py` (fixture gate + single-record validator —
  Phase 1's client validation entry point — + `--self-test` mutations; chained
  from `check-parity.sh`); fixtures in `design/collection-loop/fixtures/`
  (reused as Phase 2 server-test payloads; `broken-extra-field.json` encodes
  the identity-never-in-payload rule).
- **Phase 1 — user-side write path (D1+D4)** [agent-bios] ✅ 2026-07-20: the
  `learn!` session learning flow (single-session, user-approval gated, no
  Type-G manufacture) writes prose + JSON record; import wiring (seed +
  ensure-once); typology org overlay in PLACEMENT-FRAMEWORK.md.
  **Artifacts**: schema extensions in `config/learning.schema.json` (optional
  `classification {type, layer, meets_bar}` + `proposed_domain`, with an
  `if/then` guard tying `proposed_domain` to `domain: unclassified`) + fixtures
  + `check-learning.py` coverage; the corpus rule as a core bullet in a new
  `## Session Learning` section of `claude/CLAUDE.md` (mirrored to codex/ + ko/,
  registered in `config/domains.json`, defers to the `distill!` preset mission);
  the flow guide `claude/guides/learning-flow.md` (infra tier, ×4 mirror); the
  **host-aware** deterministic submit tool `scripts/collect-learning.py`
  (`--host claude`: prose → `personal/learnings.md` + the `@personal/learnings.md`
  import; `--host codex`: prose → a preserved `agent-bios:personal-learnings`
  region of `AGENTS.md`, since Codex has no import and AGENTS.md is always
  loaded — the region sits outside the central markers so `assemble.py`'s
  codex merge preserves it); import wiring in `assemble.py` (`ENTRY_SEED` gains
  `@personal/learnings.md` + seeds `personal/learnings.md`) and in
  `collect-learning.py` (ensure-once for existing installs). Verified end-to-end on a scratch CLAUDE_CONFIG_DIR: learn!
  → prose in `personal/learnings.md`, JSON record in `personal/learnings.jsonl`,
  entry import ensured once; a fresh assemble seeds both imports; parity/lexicon/
  domains/learning/assemble gates all green.
- **Phase 2 — transport (D2)** [dashboard, then agent-bios]: the endpoint
  (reuse `authenticate()`; version-tolerant Zod; store verbatim;
  allowlist + url-map regen), then the client POST with `X-Hook-Token` and
  the separate `pending-learnings.jsonl` fallback (bounded retries, no
  retry storm). **Gate: adversarial review of the endpoint design BEFORE
  implementation** (new public LB surface = authority-changing). Verify:
  local server round-trip with a fixture token, then N=1 canary on a real
  machine.
- **Phase 3 — curation reception (D3)** [dashboard, then agent-bios]:
  curator export (admin-only) emitting ledger-compatible JSON filtered by
  domain/date; curation intake procedure (unclassified triage; reuse
  bundle-classification + domains gate; **novelty screening vs the FULL
  canon** per the inherited rule). Verify: export from a real DB row →
  domains gate validates → entry rides the existing packaging pipeline.
- **Phase 4 — round-trip proof**: implement the user-side migrate rule
  (consume the promotion manifest slot reserved in the packaging design;
  clear the personal copy), then demonstrate the full done-when
  end-to-end on one real machine.

## Phase 1 design (trigger/UX + schema extensions, resolved 2026-07-20)

The build target for Phase 1. Terms follow `LEXICON.md` (learning = artifact;
**session learning** / `learn!` = this light flow; **session distill** /
`distill!` = the heavy pipeline).

1. **Trigger reaches every session.** `learn!` runs the light flow in ANY
   session mode. Today `learn!` is only known inside a launcher preset
   mission; Phase 1 must add a **corpus-level rule** (loaded by every session
   via the always-on corpus) that defines `learn!` → run the flow.
   **Already done (committed):** the heavy pipeline was retriggered `learn!`
   → `distill!`, so `learn!` is free. The corpus rule must **defer to the
   preset mission** when a session-distill preset session is active (so
   `learn!` there is not ambiguous).
2. **Flow = heavy-grade rigor, light mechanism** (in-conversation,
   single-session, no Workflow fleets). For each candidate learning, establish
   three things before asking the user, reusing existing framework concepts:
   ① **admission bar** (PLACEMENT-FRAMEWORK: independent-session recurrence ≥2
   or single-event high materiality) → ② **type** (typology A–G) →
   ③ **consumption/application method** (consumption layer: enforcement > gate
   > hook > guide > global > memory). Only items still sufficiently valid
   after the three gates are surfaced for **user approval** (D4).
   **Multiple learnings per invocation are allowed.** Mechanization stays
   deferred to curation (D1): record type + intended layer + bar-pass as
   **metadata only** — do NOT build the hook/enforcement user-side.
3. **Domain tagging** (D6 join key): model **suggests** from existing domains
   → user **confirms**; `unclassified` when unsure (refinement B — never
   blocks). If no existing domain fits, the model **proposes a new domain
   name**, recorded as `domain: "unclassified"` + `proposed_domain: "<name>"`
   (domain creation stays curator authority).
4. **Output via a deterministic submit script** (capability boundary): the
   script owns `learning_id` / `created` / serialization, and writes BOTH the
   prose → `~/.claude/personal/learnings.md` AND the JSON record (+ queues the
   upload in Phase 2). The LLM provides only the semantic payload (lesson
   prose, domain, criteria, classification, proposed_domain). Never hand-author
   the deterministic fields.
5. **Schema extensions — do FIRST** (optional, backward-compatible additions
   to `config/learning.schema.json`; existing fixtures stay valid): ① a
   `classification { type, layer, meets_bar }` block (ledger-compatible with
   `entries[].classification`); ② `proposed_domain`. Add fields + fixtures +
   `check-learning.py` coverage, verify green, then build the flow.

## Deferred to v2 (deliberate — do not build in v1)

- Cross-user dedup/merge tooling and curation throughput aids (wait for
  real canary volume).
- Per-user Type-G principle manufacture (needs a principle-verification
  procedure first).
- Phase 2 presets / plain-register rewrite, opencode/Cursor targets, npm
  publish — tracked in `design/corpus-domain-packaging.md`, not here.

## Kickoff checklist (fresh session starts here — Phase 2 is next)

1. Re-verify location: `pwd` = agent-bios repo. **Phase 0 + Phase 1 (incl.
   Codex) are BUILT, verified, and COMMITTED on branch `collection-loop-phase-1`**
   — the ~30-file change set is that branch's HEAD commit (`git log --oneline -1`
   shows it; `git status` is clean). `main` does NOT yet carry Phase 1, so check
   out `collection-loop-phase-1` before building on it (or merge it first). This
   dev machine still runs the ORIGINAL single-zone config — round-trip proof
   needs a packaged-install machine or a scratch `CLAUDE_CONFIG_DIR`.
2. Read this file top to bottom + `LEXICON.md` (terminology SSOT); skim
   `DISCUSSION-2026-07-20.md` only if a decision's rationale is needed.
3. **Phase 0 + Phase 1 are ✅** (see the plan + the "Corrections applied" block
   above). Do NOT re-derive these wrong: the record id field is `learning_id`
   (not `distill_id`); the flow guide is `learning-flow.md` (the hyphenated
   heavy-subsystem alias is LEXICON-deprecated); `collect-learning.py` is
   host-aware (`--host claude` → `personal/learnings.md` + `@personal/learnings.md`
   import; `--host codex` → the `agent-bios:personal-learnings` region of
   `AGENTS.md`) and repo-relative (single validation source). Re-run the gates to
   confirm green before building on top: `bash scripts/check-parity.sh` (umbrella)
   + `python3 scripts/check-learning.py --self-test`.
4. **Start Phase 2 — transport (D2).** MANDATORY first step: the adversarial
   review gate on the endpoint design BEFORE writing any endpoint code (new
   public LB surface = authority-changing). Dashboard-side work happens in
   `~/Documents/day1co-ai-usage-dashboard` (separate repo — separate commits, its
   own conventions); follow "Phase 2 — transport (D2)" in the plan above and the
   D2 reference points. Client side (agent-bios): the POST + the separate
   `pending-learnings.jsonl` bounded-retry queue drain from
   `personal/learnings.jsonl` (the local record log `collect-learning.py` writes).
