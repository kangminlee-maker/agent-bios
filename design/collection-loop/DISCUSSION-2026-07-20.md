# Collection loop — design discussion record (ARCHIVED)

Status: **archived 2026-07-20** — the discussion completed and every fork
below was resolved; the current design and implementation plan live in
`DESIGN.md` (the SSOT). Keep this file for rationale only.

Originally staged for design discussion (prepared 2026-07-20, right before a
session clear). The distribution half of corpus-domain-packaging is SHIPPED
(v1, 2026-07-20); this doc stages the deliberately deferred collection half:
a user's session distillation must (a) apply to their own account and (b)
reach the organization for curation and redistribution.

## Fixed constraints (resolved elsewhere — design WITHIN these)

From design/corpus-domain-packaging.md (all user-approved):
- Two-zone topology: personal-owned `~/.claude/CLAUDE.md` + `~/.claude/personal/*`
  vs the central-managed `~/.claude/central/` tree. Personal zone is never
  overwritten; it already LOADS in the user's own sessions (half (a) of the
  goal is structurally solved — only the write path into it is missing).
  > **Correction (2026-07-20, verified against `scripts/assemble.py`):** the
  > loading claim is half-right. The seeded entry CLAUDE.md loads (with its
  > `@central/bundle.md` import), but files under `~/.claude/personal/` do
  > NOT auto-load — Claude Code loads only the entry file plus explicit
  > `@`-imports, and the seed contains no `@personal/...` line. F1 therefore
  > must design the loading wiring as well, not just the write path. Central
  > harvest is unaffected (it reads files on disk, not session context).
- Collection posture: FULL automatic harvest of `personal/*` (no consent
  split; per-user decision 2026-07-20); secret-redaction stays the technical
  floor; central curation keeps a human approval gate.
- Derived rules: promote→migrate is USER-side off a promotion manifest in the
  push; retire→reconcile correction feed; novelty judged against the FULL
  canon (not the installed subset); ledger `domain` field (D6 vocabulary) is
  the curation join key.
- Vocabulary (user-confirmed 2026-07-20): **session learning** = the
  process/system name; **distillation** = the per-session artifact. Keep both.
  **SUPERSEDED 2026-07-20 by `LEXICON.md`**: the artifact is now **learning**;
  **session learning** (`learn!`) = the light per-user flow; **session
  distill** (`distill!`) = the heavy pipeline. (Dated history; see LEXICON.md.)

From design/session-distill/PLACEMENT-FRAMEWORK.md (defined AND operational
for the single-user model — 49 placed, 78 ledger entries):
- Mining pipeline: digest (secret-redacted, 6 heuristic value signals that
  rank but never decide) → LLM screen vs live baseline → consolidate (dedup,
  strength = recurrence × materiality) → user-approved bundle → placement.
- Typology A–G (own-tooling defect / tool gotcha / recognition principle /
  domain procedure / environment fact / unproven / principle-direction) with
  leftward-reformulation and consumer-escalation meta-rules.
- Routing tree (enforcement > gates > hooks > guides > global > memory >
  incubator), per-layer admission tests, lifecycle (promotion ≥2 recurrence
  or single high-materiality; retirement with dated corrections).

## The five org-model gaps (identified 2026-07-20)

1. **Role-split overlay on the typology**: the routing tree's targets
   (enforcement/gates/hooks/global) are central-owned under the org model. A
   regular user's type-A/B (mechanizable) learnings have no personal home
   beyond prose; mechanization must become a curator-side decision after
   harvest. The typology needs an org overlay: user-side landing rules vs
   curator-side routing.
2. **Weight**: the current pipeline is a power-user batch mining system
   (Workflow fleets, provider-affine screening). 500 mixed-role users need a
   lightweight in-session distill flow.
3. **Domain tagging at distillation time** (D6 vocabulary) — absent from the
   workflow; required as the curation join key.
4. **Novelty-vs-full-canon** — rule resolved, but screening still compares
   against the deployed baseline (opt-in users would mint duplicates).
5. **Type-G (principle distillation) at org scale** — deliberate-reflection
   type; per-user or curator-only is undecided.

## Discussion forks (recommendations to react to, not derive)

- **F1 — Personal write path** (self-contained; no org input needed).
  Recommendation: keep the `learn!` trigger; a slim in-session flow writes
  prose bullets + domain tag + ledger-format provenance into
  `~/.claude/personal/`; ALL types land as prose user-side (mechanization
  deferred to curation); the typology gains a two-column org overlay
  (user-side landing / curator-side routing). Collect hooks
  (collect-session.js, infra tier) already gather the raw substrate.
- **F2 — Upload transport** (BLOCKED on org infra facts — ask the user
  first): internal git remote? shared storage? internal API endpoint? auth
  story? Today's distribution is pull-based npm/git with no reverse channel.
  No recommendation until answered; design the channel with the same
  circuit-breaker discipline as other unattended batches.
- **F3 — Central reception + curation queue**. Recommendation: queue format =
  ledger-compatible JSON keyed by the D6 domain vocabulary; curation reuses
  the existing bundle-classification procedure + domains gate; redistribution
  rides the already-shipped packaging pipeline (promotion manifest +
  correction feed slots are reserved in the design).
- **F4 — Lightweight per-user distill flow** (the gap-2 fix; pairs with F1).
  Recommendation: the heavy pipeline remains the curator/power-user tool;
  regular users get a bounded single-session distill (no fleets), gated on
  the existing user-approval convention.
- **F5 — Type-G at scale**. Recommendation: curator-side only for v1.

Suggested discussion order: F1 → F4 (self-contained pair) → F2 (needs the
user's org-infra answers) → F3 → F5.

## Decisions and new facts (2026-07-20 discussion)

- **F1 RESOLVED (user-approved)**: staged recommendation accepted. Loading
  wiring (required per the correction above): distillations accumulate in an
  automation-owned `~/.claude/personal/distillations.md`; the entry CLAUDE.md
  gets a guaranteed `@personal/distillations.md` import line (added to the
  seed; existing installs get it ensured once on first distill run).
  Ownership separation is the point: promote→migrate cleans the automation's
  own file and never edits the user's hand-written Personal section.
- **F4 RESOLVED (user-approved)**: as staged — regular users get a bounded
  single-session distill (no fleets), existing user-approval convention;
  heavy pipeline stays a curator/power-user tool.
- **F2 org facts (user-provided)**: internal git remote, shared storage, AND
  internal API are all available. **New fact**: the org already operates an
  ingest server at `ai-litmus.day1co.kr` (repo
  `~/Documents/day1co-ai-usage-dashboard`; Next.js + Prisma/Postgres on
  Cloud Run) collecting per-session usage from the same ~500 users via the
  collect-session.js hook, with per-user `X-Hook-Token` auth and a local
  pending-queue/drain transport already deployed on every machine.
  Survey findings (2026-07-20): `/api/ingest/sessions` is NOT reusable as-is
  (rigid session Zod schema); a generic `RawIngestEvent` JSON envelope table
  already exists; adding a sibling `/api/ingest/distillations` is additive
  (route + Zod schema + `PUBLIC_API_PATHS` allowlist entry + LB url-map
  regen — exact-match only, no wildcards); no by-type curator export exists
  yet; client should use a SEPARATE pending queue file (the shared
  pending-sessions.jsonl is capped at 500 lines).
  **F2 RESOLVED (user-confirmed)**: reuse the ingest server — build cost is
  sunk and per-user auth is already provisioned, which beats distributing
  git push permissions to 500 users. Implementation spans two repos
  (agent-bios client side, dashboard server side). New sibling endpoint
  `/api/ingest/distillations` + allowlist entry + separate client pending
  queue (`pending-distillations.jsonl`).
- **F3 RESOLVED (user-approved, with refinements)**: ledger-compatible JSON
  payload, D6 domain tag as the curation join key, existing curation
  procedure + packaging pipeline for review/redistribution. Under ingest
  transport the queue physically lives in the dashboard Postgres
  (`raw_ingest_events` with a distinct source, or a small dedicated table);
  "ledger-compatible JSON" binds the upload payload and the curator export
  format. Discussed downsides (single-user-era format lacks cross-user
  recurrence; 500-client schema coupling; curation throughput ceiling; D6
  vocabulary rigidity; two-repo schema sync) resolved with three
  refinements: **(A)** a schema-version field in the payload; **(B)** an
  "unclassified" domain escape value (curator assigns later — users are
  never blocked at distill time); **(C)** the server preserves the raw
  uploaded JSON verbatim (reinterpretable after format evolution).
  Cross-user dedup/merge tooling and throughput aids are deliberately
  deferred to v2, pending real canary volume.
- **F5 RESOLVED (user-approved)**: Type-G (general-principle) manufacture is
  curator-only in v1. Users still record principle-ish observations as
  prose (harvested like everything else), and hand-writing personal
  principles in the user-owned zone remains free; only automated
  principle-grade promotion is central.

## Done-when for v1 (updated 2026-07-20 to the resolved transport)

A distillation made in a user session lands in that user's
`personal/distillations.md` and loads in their next session (via the
guaranteed `@personal/distillations.md` import); the same artifact reaches
the dashboard Postgres through `/api/ingest/distillations`; a curator
exports it as ledger-compatible JSON and promotes it through the existing
curation procedure; the next push includes it and the user-side migrate
rule clears the personal copy — the full round-trip demonstrated
end-to-end on one real machine.

## Implementation-process plan (stage-2 design, drafted 2026-07-20 — awaiting approval)

Ordered phases; each has its own verification. Cross-repo work: [AB] =
agent-bios, [DB] = day1co-ai-usage-dashboard.

- **Phase 0 — schema freeze** [AB]: the distillation record spec as a JSON
  Schema (ledger-compatible fields + `schema_version` + `domain` with the
  D6 vocabulary plus `unclassified` + provenance). SSOT lives in
  agent-bios; the dashboard mirrors only minimal validation. Verify:
  fixture records validate; a deliberately broken fixture fails (negative
  control).
- **Phase 1 — user-side write path (F1+F4)** [AB]: the slim `learn!`
  distill flow (single-session, user-approval gated, no Type-G
  manufacture) writes prose to `~/.claude/personal/distillations.md` plus
  the JSON record; import wiring (seed gains `@personal/distillations.md`;
  existing installs get the line ensured once on first distill); typology
  org overlay documented in PLACEMENT-FRAMEWORK.md. Verify: distill on a
  fixture session → file lands → a fresh session loads it; assemble/parity
  checks stay green.
- **Phase 2 — transport (F2)** [DB then AB]: `POST
  /api/ingest/distillations` (reuse `authenticate()`; version-tolerant Zod;
  raw stored verbatim per refinement C; `PUBLIC_API_PATHS` + url-map
  regen), then the client POST with `X-Hook-Token` and the separate
  `pending-distillations.jsonl` fallback queue (bounded retries, no retry
  storm). Gate: adversarial review of the endpoint design BEFORE
  implementation (new public LB surface = authority-changing). Verify:
  local server round-trip with a fixture token, then N=1 canary on a real
  machine.
- **Phase 3 — curation reception (F3)** [DB then AB]: curator export
  (admin-only) emitting ledger-compatible JSON filtered by domain/date;
  curation intake procedure (unclassified triage step; reuse
  bundle-classification + domains gate). Verify: export from a real DB row
  → domains gate validates → entry rides the existing packaging pipeline.
- **Phase 4 — round-trip proof**: implement the user-side migrate rule
  (consume the promotion manifest slot reserved in the packaging design;
  clear the personal copy), then demonstrate the full done-when end-to-end
  on one real machine.
