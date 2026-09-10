# Collection loop — Phase 2 (transport) endpoint design — v2 (post-review)

Status: **adversarial review COMPLETE (5 lenses, 2026-07-20) → unanimous
needs-changes-before-code; core design holds.** This v2 folds in every confirmed
fix plus the user's sequencing and rate-limit decisions and the infra corrections
found this session. It is the **post-review build target for D2**. SSOT for the
collection loop stays `design/collection-loop/DESIGN.md`; terms follow
`LEXICON.md`. Cross-repo: server half in `~/Documents/day1co-ai-usage-dashboard`
(its own repo/PR), client half agent-bios-owned.

---

## Review outcome (2026-07-20)

Five independent adversarial lenses reviewed the v1 draft before any code:
public-boundary/authority, concept-economy/storage, correctness/idempotency,
client-transport/ownership, ops/release-gate. **Verdict: all five =
needs-changes-before-code.**

- **Conceded sound (attacked, held):** the `RawLearningEvent` storage split;
  token-derived identity (unauth write blocked, cross-user squatting blocked);
  `(userEmail, learning_id)` exactly-once dedup.
- **Independently re-verified (load-bearing ops findings, confirmed vs real
  code):** `src/proxy.ts` is **inert** — no `middleware.ts`, only tests import it,
  so the "2-layer LB+proxy" safety claim is false today; `setup-lb.sh` is
  **create-once + prod-unsupported** (line 56 prod exits 2; line 169 re-run =
  "ALREADY EXISTS" no-op) — it cannot incrementally add a path.

All findings are folded into the decisions below. The v1 rationale errors
(the "six services pollution" overstatement and the "fingerprint-collapse"
strawman) are corrected in D2.1.

## Decisions locked this session (user + infra findings)

- **Sequencing: 2a → 2b.** 2a = build + verify the endpoint and client
  end-to-end on **dev**; 2b = **prod exposure is a separate Ops-coordinated
  gate**. Nothing touches the prod public surface until 2b. *(user)*
- **Rate limit: app-level per-user write quota (429) ships with the endpoint;
  edge Cloud Armor deferred to 2b.** Permissions are confirmed (`roles/owner` on
  both `d1-ai-dashboard`/639026199042 and `day1-ai-dashboard-dev`/430377224121;
  all 10 Cloud-Armor + backend-service permissions held). But Cloud Armor
  attaches only to an **external-LB backend-service**, and the ingest path does
  not currently require one, so the app-level quota is the shippable floor now;
  Cloud Armor is added at 2b **only if** the prod path fronts the service with an
  external LB, as a **separate** policy on the ingest backend — never touching
  the existing `mcp-workspace-corp-ip-only` policy. *(user direction + infra)*

## Infra reality (corrected this session — verified vs live GCP + real code)

- **Ingest is reached by hooks/pollers with `X-Hook-Token`, NOT via a public
  custom domain.** `ai-litmus.day1company.io` currently resolves **NXDOMAIN**;
  `ai-litmus.day1co.kr` is the **internal dashboard UI** host (browser Google
  OAuth login; `AUTH_URL` pinned there per `src/auth.ts`). The learnings upload
  never uses OAuth — that is a separate concern (prod login client
  `639026199042-791gs7uq…`, dev `430377224121-4c3r7hk6…`).
- **Prod ingest** = Cloud Run `run-day1-production-ai-dashboard` (project
  `d1-ai-dashboard`, `asia-northeast3`), ingress
  `internal-and-cloud-load-balancing`, `allUsers` invoker. **Dev ingest** =
  Cloud Run `run-day1-development-ai-dashboard` (project `day1-ai-dashboard-dev`).
- **The learnings endpoint is a SIBLING route to `/api/ingest/sessions` on the
  same Cloud Run service.** It inherits whatever exposure/reachability the
  sessions endpoint already uses — there is **no bespoke exposure to invent**.
  The `docs/public-ingest-endpoint-design.md` external-LB machinery
  (`PUBLIC_API_PATHS` + url-map) applies only where the sessions endpoint uses it;
  per the ops review that machinery is dev-targeted, cannot incrementally add a
  path, and its proxy layer is inert — so exposure is **resolved at 2b by
  matching the sessions endpoint**, not re-designed here.

## Grounded reference facts (verified 2026-07-20)

- **Auth (reuse as-is):** `authenticate(request)` (`src/services/auth.service.ts:164`)
  → `X-Hook-Token` → DB lookup by `hookToken` → `AuthResult{ email, … }`; requires
  `user.active`; identity from token, client email never trusted.
- **Existing envelope is session-shaped (do NOT reuse):** `RawIngestEvent`
  (`prisma/schema.prisma`) `@@unique([source, sourceSessionId, eventFingerprint])`;
  key columns `source`/`sourceSessionId`/`eventFingerprint`/`provider` are
  **NON-NULL**; `buildEventFingerprint` (`raw-ingest.service.ts:44`) hashes
  session-only fields; P2021 guard at `raw-ingest.service.ts:153`.
- **Client contract:** `HOOK_DIR = ~/.claude/hooks` (or `~/.codex/hooks`);
  files `token`, and the URL comes from `ingest-url` **|| `dashboard-url`** (the
  installer writes `dashboard-url` — it is the primary, not a rare legacy); the
  dashboard hook is dashboard-owned (read-only for us).
- **Payload schema (SSOT):** `config/learning.schema.json` v1 — required
  `schema_version`(=1), `learning_id`(client UUID, lowercase, the idempotency
  key), `lesson`(8–2000), `domain`, `created`, `supporting_sessions`; identity
  never in payload; server tolerant on version, stores verbatim.

---

## Decisions D2.1–D2.5 (v2)

### D2.1 — Storage: new `RawLearningEvent` (split) — CONFIRMED; rationale corrected
**Decision:** persist learning uploads verbatim in a new model `RawLearningEvent`.
**Decisive rationale (corrected):** `RawIngestEvent`'s key columns are NON-NULL
and session-fingerprint-shaped, so reuse/extend would (a) fabricate fake
`sourceSessionId`/`eventFingerprint`/`provider`, (b) carry ~13 permanently-null
session/blob columns, (c) still be unable to express the real `(userEmail,
learningId)` dedup key, and (d) require a hot-table `ALTER` (nullable relaxation
+ new unique) on the ~500-machine ingest table. The split is a pure additive
`CREATE TABLE` + indexes, zero lock. *(Drop the v1 "six services pollution" claim
— only `pii-canary` scans unfiltered — and the "fingerprint-collapse" strawman;
they are not the reason.)*
**Q-D resolved:** `status` uses a **learning-specific 2-value token set
`RECEIVED | EXPORTED`**, NOT the session `IngestEventStatusEnum` (whose
NORMALIZED/IGNORED_DUPLICATE/FAILED are dead for learnings). `status` is a plain
`String` column → no DB enum to migrate; the collision is TS/semantic only.
**Shape:** `id`(uuid), `learningId`, `userEmail`(token), `schemaVersion`(int),
`domain`(string?, **derived at write from `payloadJson.domain` only — never
independently mutated**), `payloadJson`(verbatim), `receivedAt`(default now),
`status`(default `RECEIVED`). `@@unique([userEmail, learningId])`,
`@@index([status, receivedAt])`; add `@@index([domain, receivedAt])` **only if**
the curator export provably filters by domain, else omit.

### D2.2 — Idempotency: `(userEmail, learningId)` exactly-once — CONFIRMED
**Decision:** re-POST of the same `learning_id` by the same user → 200
`{ duplicate: true }`. **P2002 is ALWAYS a plain duplicate** → `{ duplicate:true }`
— do NOT port the sessions FAILED-row branch (dead for learnings) and never
return `{ id: null }` on the commit race. **Server canonicalizes `learning_id`
to lowercase before the dedup comparison** (robust to an uppercase-UUID client
variant). Documented residual: same-user re-POST of one `learning_id` with a
different body = first-write-wins (new body dropped) — acceptable for a verbatim
audit store.

### D2.3 — Validation: minimal hard envelope + pre-parse cap + verbatim — hardened
**Enforce the size cap BEFORE parse:** reject `Content-Length > cap` AND cap the
stream read with a hard byte ceiling that aborts over-limit → 413 (do NOT inherit
the sessions route's parse-then-check → Cloud Run OOM). **Cap = 32 KB** (Q-A:
`lesson` 2000 + `context` 4000 + envelope; 32 KB is a comfortable ceiling).
**Permanent cross-version invariants (hard):** valid JSON object; `learning_id`
present + canonical UUID; whole body ≤ cap; **no ` ` in any string** → reject
400 (a jsonb insert on ` ` throws; rejecting keeps it a permanent 400 the
client drops rather than a 500 it retries forever; `src/lib/strip-null-chars.ts`
exists if stripping is preferred).
**v1-shape checks:** under `schema_version==1`, `lesson` present non-empty ≤2000
and `domain` present non-empty; under `schema_version>=2`, treat lesson/domain as
**store-if-present** (a v2 client hitting a v1 server during rollout is not 400'd
on shape). `schema_version` must be an int ≥ 1.
**Identity:** derived from token only; **reject a named identity blocklist in the
payload** (`email`, `user_email`, `userEmail`) → 400 (consistent with the client's
`additionalProperties:false`; forward-compat concerns only UNKNOWN fields, which
are stored verbatim). `domain` membership is NOT enforced server-side (Q-B:
accept unregistered → curator triages `unclassified`).
**Log hygiene:** log ONLY validated fields (`userEmail`, UUID `learning_id`, row
`id`) — never interpolate raw payload strings (log injection via `domain`).
**Table-not-ready:** P2021 → **500** (client retains/queues), NOT the sessions'
silent-null-200 (which would be silent upload loss).

### D2.4 — Exposure: inherit the sessions endpoint — deferred to 2b
The learnings route reaches the fleet by **exactly whatever `/api/ingest/sessions`
already uses** — nothing bespoke.
- **2a (dev):** verify end-to-end against the **dev** Cloud Run service (dev
  ingress / dev path). No prod surface touched.
- **2b (prod, separate Ops gate):** mirror the sessions endpoint's prod exposure.
  IF that is the `PUBLIC_API_PATHS` external-LB path, the documented 4-step add
  applies, but these confirmed blockers are resolved FIRST: (1) `setup-lb.sh`
  needs an **idempotent path-rule update** mode (or a `url-maps` patch that
  merges, not `import` which replaces); (2) either **mount the proxy**
  (`src/middleware.ts`) before claiming 2-layer defense, or explicitly accept
  single-layer LB enforcement; (3) **pin deploy order migrate → code → open
  exposure** (P2021→500 makes an early-open window fail-safe: client retains);
  (4) attach edge Cloud Armor as a **separate** policy on the ingest backend.
  Fail-mode row (if the LB path is used): fail-open-if-listed, else fail-close
  (404), matching the sessions row.

### D2.5 — Client transport: watermark over the durable log — rewritten (2 reviewers converged)
**Replace the separate `pending-learnings.jsonl` queue** with: drain the durable
append-only `personal/learnings.jsonl` (already written *before* upload) against a
**persisted watermark** (last-uploaded offset / uploaded-`learning_id` set). This
collapses dead-queue, cap-drop-oldest, and enqueue-race at once and removes a
concept; server-side `learning_id` idempotency keeps re-sends safe.
- **Status taxonomy (fresh + backfill share ONE rule):** SUCCESS = any 2xx (incl.
  `duplicate:true`) → advance watermark. RETAIN/retry (leave behind watermark) =
  401, 403, 404, 429, 503, 5xx, network/timeout (all transient across
  provisioning / deploy window / rollback). PERMANENT drop (advance past + mark
  dead) = 400, 413.
- **Wall-clock bound:** one total budget (~5 s) across the whole upload+drain
  phase (daemon thread the main abandons after the deadline); **always print the
  `learn!` result regardless of upload outcome** (prose already landed). Bound
  records/invocation (e.g. 20) so a backlog can't stall.
- **Host:** derive the hooks dir from `resolve_home(host)` (`~/.claude/hooks` or
  `~/.codex/hooks`), never hardcode `~/.claude`.
- **URL/token:** `url = read ingest-url || dashboard-url`; `token = read token`.
  If token OR resolved url is missing → skip upload, emit a one-line **"not
  uploaded (dashboard hook not installed)"** notice (Q-E: notice, not silent), and
  leave the watermark unadvanced so a later enrolled `learn!` backfills from the
  durable log.
- **Ownership:** read-only on token/url; never touch `collect-session.js` or
  `pending-sessions.jsonl`; reach any hooks-dir write (the watermark file, our
  own) only after the token+url check passes. A malformed durable-log line is
  skipped, never wedges.

## Open questions — resolved
- **Q-A** cap: 32 KB, enforced pre-parse. **Q-B** unregistered domain: accept +
  store (curator triages). **Q-C** rate limit: app-level quota now, Cloud Armor at
  2b. **Q-D** status enum: learning-specific `RECEIVED|EXPORTED`. **Q-E** no-token
  UX: one-line notice + durable-log backfill.

## Change-set

**2a — server (dashboard repo, feature branch, verified on dev):**
1. `prisma/schema.prisma` + additive migration: `RawLearningEvent` (D2.1).
2. `src/services/raw-learning.service.ts`: `createRawLearningEvent` — pre-parse
   cap, minimal envelope + identity-blocklist + null-byte reject (D2.3),
   canonical-lowercase `learningId`, verbatim store, P2002→duplicate,
   P2021→500.
3. `src/app/api/ingest/learnings/route.ts`: `authenticate()` → validate → store;
   200 `{ id, learningId, duplicate }`, 400/401/403/413/500; log hygiene.
4. App-level per-user write quota → 429 (Q-C floor).

**2a — client (agent-bios, this branch):**
5. `scripts/collect-learning.py`: the D2.5 watermark upload/backfill over
   `personal/learnings.jsonl`, host-aware dir, url/token resolution + no-token
   notice, wall-clock bound, shared status taxonomy.

**2b — prod exposure (separate Ops gate):** mirror the sessions endpoint (D2.4);
resolve the four ops blockers; add edge Cloud Armor; deploy order pinned.

## Verification plan (falsifiable, from the review)

**2a server (assert on a real written/absent row, cardinality > 0):** valid
fixtures → 200 + row verbatim; each `broken-*` → 400; body > 32 KB → 413 with
bounded handler memory (cap fired pre-parse); missing token → 401; duplicate
`learning_id` → 200 `{duplicate:true}`; payload with `"email":…` → row's
`payloadJson` has no `email`; `"lesson":"a b"` → 400; P2021 (drop table) →
500 (not 200).
**2a client:** server down / 5s-drip sink with 20 backlog records → `learn!`
total wall-time ≤ ~6 s AND the result still prints; `--host codex` on a box with
only `~/.codex/hooks/token` → reads codex token and uploads; durable log with one
413-sized + one corrupt line → both dropped (not re-tried forever), valid lines
send; `ingest-url` absent → still uploads via `dashboard-url`; no token → notice
printed, watermark unadvanced, later enrolled `learn!` backfills.
**2b:** N=1 canary on one real machine (real token) AFTER prod exposure matches
the sessions endpoint and Cloud Armor is attached.
