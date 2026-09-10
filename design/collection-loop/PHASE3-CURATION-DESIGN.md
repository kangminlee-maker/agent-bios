# Collection loop — Phase 3 (curation reception, D3) — design

Status: **build target for Phase 3.** Decisions locked with the user 2026-07-21
(delivery mechanism, EXPORTED lifecycle, PII inclusion — see D3.1–D3.3; secret
redaction — see F3 in "Review folded"). **Two-lens pre-code adversarial review
DONE 2026-07-21** (authority/PII + correctness/idempotency); all findings folded
below. **BOTH halves BUILT + verified 2026-07-21** — agent-bios (intake) on
branch `collection-loop-phase-3`, dashboard (server) on branch
`feat/export-learnings`. Not yet committed/merged; prod deploy is a separate
user-driven step (like Phase 2b). SSOT for the loop stays
`design/collection-loop/DESIGN.md`; terms follow
`LEXICON.md`. Cross-repo: server half in `~/Documents/day1co-ai-usage-dashboard`
(its own repo/PR/deploy), intake half agent-bios-owned.

Phase 0–2 are DONE (server endpoint live in prod, client shipped in npm v0.5.0).
Phase 3 turns the accumulating `raw_learning_events` rows into curated corpus
entries. Phase 4 (round-trip: promote→migrate) follows.

---

## Goal (from DESIGN.md Phase 3)

A curator **exports** user learnings from the dashboard Postgres as
ledger-compatible JSON filtered by domain/date, and an agent-bios **intake
procedure** triages `unclassified`, reuses the domains gate +
bundle-classification, screens novelty against the FULL canon, and rides the
existing packaging pipeline. **Done-when: a real DB row → export → domains gate
validates → the entry rides `assemble.py`.**

## Two halves, clean ownership split

```
dashboard (server)                         agent-bios (intake)
──────────────────                         ───────────────────
raw_learning_events                        export.json
  └─ GET /api/exports/learnings  ──file──▶   └─ ingest-learnings-export.py (validate + map)
     admin-only, verbatim dump                  └─ curation worklist (ledger candidates)
     flips RECEIVED→EXPORTED                        └─ CURATION-INTAKE.md (triage/classify/novelty)
                                                        └─ ledger.json candidate → §P8 placement → assemble.py
```

**Ownership rule:** the server owns storage + auth + a filtered *verbatim* dump.
It does **not** know the ledger format — it never shapes rows into ledger
entries (honors D3 refinement C: store/emit verbatim, reinterpretable after
format evolution). The agent-bios side owns all curation semantics (ledger
shape, typology, novelty), because `PLACEMENT-FRAMEWORK.md` and `ledger.json`
live here.

---

## Locked decisions (user, 2026-07-21)

### D3.1 — Delivery: admin API route (mirror the CSV export)
`GET /api/exports/learnings`, mirroring the existing `GET /api/exports/csv`
(`src/app/api/exports/csv/route.ts` + `src/services/export.service.ts`): a
logged-in admin triggers a browser download; runs against the deployed service
(in-VPC, DB access); zero new infra; inherits the service's existing exposure
(NOT a new public surface — admin-gated like the sessions CSV export). Prod
deploy is a **separate, user-driven step** (as with Phase 2b); build + test +
merge are verifiable on a dev/local Postgres round-trip.

### D3.2 — EXPORTED lifecycle: flip at export, default excludes EXPORTED
The reserved `status` column (`RECEIVED | EXPORTED`, currently inert — nothing
writes `EXPORTED`) goes live here. Export selects matching `RECEIVED` rows,
returns them, and flips them to `EXPORTED` in the same DB transaction. Default
export excludes `EXPORTED` (= "new since last pull" — robust to late arrivals /
overlapping windows, unlike a date-only cursor). `?includeExported=true`
re-pulls everything for recovery/audit. This retires the inert field (corpus
rule: a produced field is inert until a consumer reads it). Residual: an
admin-only `GET` with a side effect — accepted for a low-frequency internal
export; the flip is transactional and guarded (`WHERE status='RECEIVED'`) so
concurrent exports never double-pull.

### D3.3 — PII: include `user_email` per export row
Rationale (user): visibility into which users produce more valuable content in
which domains (열람 목적; no systematic action yet). Each export row carries
`user_email` + `domain` + `received_at`, so a per-user × domain contribution
view is a later aggregation, not a new endpoint. Posture: admin-only route
(role check) exporting to a file an admin already can see (admins have
`resolveReadScope = ALL`); consistent with the existing sessions CSV export.
Guards: `user_email` is the **token-derived** email (never client-supplied —
the ingest identity blocklist already rejects `email`/`user_email` in the
payload); logs emit counts/filters only, never row contents.

---

## Server half — dashboard (branch off `main`; RawLearningEvent is on main)

**Reference model** (`prisma/schema.prisma`, `RawLearningEvent`): `id`,
`learningId`, `userEmail`, `schemaVersion`, `domain` (String?, verbatim from
`payload_json.domain`), `payloadJson` (Json, verbatim), `status` (String, dflt
`RECEIVED`), `receivedAt`. `@@unique([userEmail, learningId])`,
`@@index([status, receivedAt])`. No `(domain, receivedAt)` index — v1 does NOT
add one (low volume, admin/infrequent; adding an index would require the
in-VPC manual `prisma db execute` workflow — disproportionate now).

1. `src/services/learning-export.service.ts` — `generateLearningExport(filters)`:
   - `filters = { domain?, from?, to?, includeExported? }`; build a Prisma `where`
     AND-array: `domain` equals (if given), `receivedAt: { gte: from, lte: to }`
     (if given, parsed to `Date`), `status: 'RECEIVED'` unless `includeExported`.
   - In a **`$transaction`**: `findMany({ where, orderBy: { receivedAt: 'asc' },
     take: CAP })` → then `updateMany({ where: { id: { in: ids }, status:
     'RECEIVED' }, data: { status: 'EXPORTED' } })` (guard on RECEIVED so an
     `includeExported` re-pull of already-EXPORTED rows is a no-op update).
   - `CAP` = a bounded page (e.g. 5000) — log if the cap is hit (no silent
     truncation).
   - Map each row → export element (verbatim payload + provenance):
     `{ learning_id, user_email, schema_version, domain, received_at, status,
     payload: <payloadJson verbatim> }`.
   - Return `{ source: 'learnings-export', exported_at, filters, count, learnings }`.
2. `src/app/api/exports/learnings/route.ts` — GET, mirroring `exports/csv`:
   `authenticate(request)` → `auth.role !== 'ADMIN'` → 403 (match the CSV route's
   inline idiom exactly, the sibling export) → parse query → service → JSON
   download (`Content-Type: application/json`, `Content-Disposition: attachment;
   filename="learnings-<domain|all>-<YYYY-MM-DD>.json"`). 400 on unparseable
   date; 401/403 from auth; 500 on DB error. Log filters + count only.
3. Tests (`__tests__/services/learning-export.service.test.ts`,
   `__tests__/api/exports-learnings.test.ts`).

## Intake half — agent-bios (branch `collection-loop-phase-3`)

4. `scripts/ingest-learnings-export.py` — deterministic intake helper:
   - Input: an export JSON file. For each `learnings[].payload`, validate via
     `check-learning.py`'s `validate_record` (schema + domain membership — the
     single validation source, reused as `collect-learning.py` does). Never
     patch to pass.
   - Output a **curation worklist** JSON: `{ source, generated_from, count_valid,
     count_rejected, rejected: [{ index, learning_id, reason }], entries:
     [ledger-candidate…] }`. Each candidate = ledger entry shape with `status:
     'candidate'`, `id: null`, `strength: null`, `verdict: null`, mappable fields
     from the payload (`lesson`, `criteria`, `supporting_sessions`, `domain`,
     `classification` mapped from the slim `{type,layer,meets_bar}` →
     `{type, layer, meets_promotion_bar}` with curator-only fields null),
     `proposed_domain` if present, and `provenance: { learning_id, user_email,
     received_at, schema_version }`.
   - Deterministic ONLY: it does not classify (type A–G beyond what the record
     carries), assign domains, or judge novelty — those are the curator's
     semantic steps (capability boundary).
   - `--self-test`: run over a bundled fixture export (valid + broken rows) →
     assert valids mapped (cardinality > 0), broken row reject-reported, exit
     non-zero on any mismatch. Chained into `check-parity.sh`.
5. `design/collection-loop/CURATION-INTAKE.md` — the procedure a curator follows:
   export → run the helper → for each candidate: (a) **triage** `unclassified`
   (assign a `domain` from `config/domains.json`; use `proposed_domain` as a
   hint; domain creation stays curator authority) → (b) **classify** via the
   bundle-classification procedure (`PLACEMENT-FRAMEWORK.md` typology A–G + layer
   + mechanism/verification) → (c) **novelty vs FULL canon**: compare the lesson
   against the complete `claude/CLAUDE.md` + all `claude/guides/*` (NOT the
   domain-filtered installed subset; a hit on a not-installed domain is
   `exists-in-canon`, not novel) → (d) fill the ledger entry (`id`, `strength`,
   `verdict`, full `classification`) and merge into `ledger.json` as
   `status: candidate` → (e) the existing §P8 placement + `check-parity.sh` +
   `assemble.py` pipeline takes over. Cross-user dedup/merge stays v2-deferred:
   each learning is an individual candidate; the curator spots duplicates by hand.
6. `design/collection-loop/fixtures/export-sample.json` — a sample export built
   from the existing `valid-*`/`broken-*` learning fixtures wrapped in the export
   envelope; drives the helper self-test.
7. Wire `ingest-learnings-export.py --self-test` into `scripts/check-parity.sh`.

---

## Verification plan (falsifiable)

**Server (assert on real rows, cardinality > 0):** seed rows across 2 domains +
2 dates + one already-`EXPORTED`; `generateLearningExport({domain, from, to})`
→ returns only matching `RECEIVED` rows, payload verbatim (nested/unicode
preserved), and those rows are now `EXPORTED` in the DB (re-query proves the
flip); a second export with no filter returns 0 of the just-pulled rows (default
excludes EXPORTED) but `includeExported` returns them without re-flipping others;
route: admin → 200 + attachment, non-admin → 403, no token → 401. Real
Postgres round-trip (docker/dev) like the Phase 2a proof, not mocks-only.
**Intake:** run the helper over a real export (or the fixture) → valid rows
mapped to candidates (count > 0), a broken row reject-reported (negative
control), invalid never silently mapped; then hand-fill one candidate into
`ledger.json` and run `bash scripts/check-parity.sh` → the domains gate
validates the domain value and parity stays green = the entry "rides the
packaging pipeline". `--self-test` green in the umbrella gate.
**End-to-end (Phase 3 boundary):** a real learning row (dev insert or a prod
canary row) → export → intake → ledger candidate → domains gate green. Full
promote→migrate round-trip is Phase 4.

## Review folded (2026-07-21) — deltas from the two-lens pre-code review

Both lenses verified against real code; findings folded here.

**F3 — secret-redaction floor (user decision: add at capture).** The corpus
declares a secret-redaction floor (`design/corpus-domain-packaging.md`) that the
light `learn!` path never implemented — so a secret in free-text `lesson`/
`context` would egress verbatim (personal file → upload → this export). Fixed at
the **root cause (capture)**, single-sourced: new `scripts/redact.py`
(SECRET_RE + `redact()`) is the ONE floor, imported by both
`scripts/session-distill/digest.py` (heavy) and `scripts/collect-learning.py`
(light, redacting `lesson`/`context` in `build_record` before write/upload).
Shipped in the npm `files` (collect-learning imports it). Export stays verbatim
(D3-refinement-C) because capture already redacted. Residual: rows uploaded
BEFORE this ships are un-redacted (tiny pre-fix window; canary row deleted).
Reaching users needs a version bump + republish (separate step).

**Server (dashboard) — folded into the change-set above:**
- **Transaction (must-fix):** use the **interactive** `$transaction(async (tx)=>…)`
  with `tx.` for BOTH `findMany` and `updateMany` — the array form can't use the
  first result's ids, and a repeated-`where` `updateMany` (no `take`) would flip
  rows beyond the CAP page → silent loss. Assert `updated.count === (found rows
  with status RECEIVED)`, else throw → 409 (rolls back).
- **"never double-pull" corrected:** at READ COMMITTED two concurrent exports can
  both *return* the same rows; the guard prevents double-*flip* only. The
  count-check above turns a concurrent conflict into one success + one 409 (no
  duplicate candidates). Claim text amended accordingly.
- **CSRF (F2):** the flip is a GET side effect → reject `Sec-Fetch-Site:
  cross-site` (dashboard navigation is same-origin; typed/curl is none/absent).
- **Credential (F1):** reject `X-Hook-Token` on this route → session cookie only
  (matches D3.1's "logged-in admin"; a leaked admin hook token can't dump).
- **Date validation:** the CSV mirror has none; add `isNaN(d.getTime())` → 400
  BEFORE the transaction; treat `to` as end-of-day (or require datetime).
- **Filename (F7):** sanitize the query `domain` used in `Content-Disposition` to
  `[a-z0-9-]{1,64}` (else `filtered`), validated before any flip.
- **CAP truncation:** `capped: boolean` in the envelope (returned === CAP);
  CAP = 2000 (bounded memory on 1Gi Cloud Run at the 32KB body ceiling); log
  each batch's `learning_id`s (UUIDs, non-PII) so a post-flip transport failure
  is recoverable via `includeExported` + the same window.
- **Element `status`:** report the POST-flip value (`EXPORTED`), not the stale
  pre-read `RECEIVED`.

**Intake (agent-bios) — folded into the built helper:**
- **`context` + `created` mapping (must-fix):** `context` is the curator-facing
  evidence note (its only consumer is this step) — mapped verbatim; `created`
  kept in `_provenance` distinct from `received_at`.
- **PII → ledger (F/C):** the worklist keeps `user_email` under `_provenance`
  (worklist is local, `.gitignore`d); the ledger merge **keeps `learning_id`,
  drops `_provenance`** — `ledger.json` is git-tracked, never holds PII.
- **v2 dead-letter (F6):** `schema_version != 1` → **`deferred`** bucket (not
  `rejected`), re-exportable later.
- **NULL-domain (C):** documented in CURATION-INTAKE (periodic unfiltered sweep);
  no `IS NULL` filter in v1 (deployed v1 clients always set `domain`).
- **Dedup key (C):** helper flags a candidate whose `learning_id` already exists
  in `ledger.json` (`duplicate_in_ledger`) — deterministic string membership.
- **Contract binding (F8):** `fixtures/export-sample.json` is the pinned
  cross-repo contract artifact the intake self-test runs against; the server test
  must pin the exact envelope/element key set naming this consumer, and the
  round-trip should replace the fixture with a REAL captured export.

## Built artifacts (agent-bios, branch `collection-loop-phase-3`)

- `scripts/redact.py` — the secret-redaction floor (+ `--self-test`), in npm `files`.
- `scripts/session-distill/digest.py` — refactored to import the shared floor.
- `scripts/collect-learning.py` — redacts `lesson`/`context` at capture; self-test
  covers the wiring.
- `scripts/ingest-learnings-export.py` — deterministic intake (validate → bucket
  valid/rejected/deferred/duplicate → ledger candidates + `--self-test`).
- `design/collection-loop/CURATION-INTAKE.md` — the curator procedure.
- `design/collection-loop/fixtures/export-sample.json` — the contract fixture.
- `scripts/check-parity.sh` — chains the redact + intake self-tests.
- `.gitignore` — blocks `*worklist*.json` / `*learnings-export*.json` (PII guard).

All agent-bios self-tests + `check-parity.sh` green 2026-07-21.

## Built artifacts (dashboard, branch `feat/export-learnings`, off `main`)

- `src/services/learning-export.service.ts` — `generateLearningExport(filters)`:
  interactive `$transaction` findMany→updateMany with the count-check,
  `capped`, post-flip `status`, verbatim payload + provenance columns.
- `src/app/api/exports/learnings/route.ts` — GET, admin-gated; hook-token 401,
  cross-site 403, date→400, filename sanitize, conflict→409, log window+count.
- `__tests__/services/learning-export.service.test.ts` (7),
  `__tests__/api/exports-learnings.test.ts` (10). No schema/migration change
  (RawLearningEvent already on `main`; no new index in v1).

**Verification (2026-07-21):** full dashboard `tsc` clean; full suite
**1915 passed** (17 new; no regression). **Live throwaway-Postgres round-trip of
the REAL service (13/13)** — the migration SQL applies to match the model;
domain+date filter returns exactly the in-window RECEIVED rows; the core-domain
and already-EXPORTED rows are excluded (default); the pulled rows are flipped to
EXPORTED **in the DB** while non-pulled rows stay RECEIVED; a default re-pull
returns 0 (new-since-last-pull); `includeExported` returns all incl. prior
without error; payload is **value-verbatim** (nested + unicode preserved).
*Caveat recorded:* Postgres `jsonb` normalizes object key order + whitespace, so
the payload is value-verbatim, not byte-identical — harmless for the intake
consumer (jsonschema + name-based mapping, both order-insensitive).

## Deferred (v2 / later phases — do not build now)
- Cross-user dedup/merge + curation-throughput aids (wait for real volume).
- A `(domain, receivedAt)` index (add only if export volume proves it).
- Per-user × domain contribution analytics endpoint (the export row already
  carries the fields; aggregate later).
- Promote→migrate (clears the personal copy) = **Phase 4**.
