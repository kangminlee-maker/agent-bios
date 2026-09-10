---
created_at: 2026-08-19T20:42:00+09:00
head: 788d0bf
kind: design
supersedes: the coupling-inventory portion of 2026-08-18T2302--bf61389--backlog.md
---

# The operating endpoint surface — inventory preceding step 2's contract extraction

Step 2's gate (roadmap `2026-08-19T1713`): the live-dashboard producer/consumer/schema
inventory precedes extraction, because the operating ingest breaks the no-backcompat
premise. This record is that inventory, and carries the retained-records facts that
pair with step 0's data-governance snapshot.

Method: two parallel read-only inventories — agent-bios's shipped set (79 files,
derived the way `gates/check-hygiene.py` derives it) at HEAD `788d0bf`, and
`day1co-ai-usage-dashboard` at `5ab04de` — with main-context spot-checks on the
load-bearing claims (INGEST_PATH, the venv pip path, the slot-file writer, the
schema-authority path). Citations are `file:line` at those two commits.

## 1. The four named operations, as they exist

| Operation | agent-bios side | dashboard side |
| --- | --- | --- |
| `ingest-learning` | SHIPPED — `agent-bios learn` → `learn/collect-learning.py` POSTs `{base}/api/ingest/learnings` (`:311,:406`) | LIVE — `src/app/api/ingest/learnings/route.ts` |
| `ingest-session` | NONE — zero references in the payload; the old settings-template registrations are gone | Wholly dashboard-owned: collectors `templates/hooks/{collect-session,codex-session-sync}.js.tpl` POST `/api/ingest/sessions`, self-update from unauthenticated serve routes |
| `publish-corpus` | NONE as a network op — npm publish + local assembly only | no counterpart |
| `fetch-corpus` | NONE as a network op — `agent-bios update` is `git pull` or a printed npm line (`install.sh:1534-1546`) | no counterpart (its serve routes serve telemetry collectors, not corpus) |

So extraction is a **compatibility exercise for one operation** (`ingest-learning`)
and **greenfield definition for two** (`publish-corpus`/`fetch-corpus`). A corpus is
not a serialized artifact today — it is the assembled deployment `compose/assemble.py`
produces from the `claude/` tree + `compose/domains.json`; the only distribution
channel is npm. `ingest-session`'s home stays a step-4 design question; nothing in
step 2 touches it.

## 2. The ingest-learning wire contract (both sides verified)

- **Transport**: POST `/api/ingest/learnings` (path hardcoded,
  `learn/collect-learning.py:311`), header `X-Hook-Token: <opaque DB UUID>`;
  identity is derived server-side from the token and is FORBIDDEN in the body
  (`raw-learning.service.ts:68-74`). Client parses no response body — HTTP status is
  the whole contract (2xx settle; 400/413 permanent; anything else transient, drain
  stops, `collect-learning.py:305-318,384-395`).
- **Payload**: authority `learn/learning.schema.json` (`$id
  urn:agent-bios:schema:learning:v1`, `additionalProperties: false`). Server-side
  envelope check is deliberately looser: `schema_version` int ≥1, `learning_id`
  canonical UUID; v1-only shape checks (`lesson` ≤2000, `domain` non-empty) apply
  only when `schema_version === 1` — **forward-tolerant by construction**
  (`raw-learning.service.ts:99-114`), stores the payload verbatim.
- **Limits**: 32 KiB body cap (413), 100 distinct learnings / rolling 24 h / user
  (429), server dedups by `(userEmail, learningId)`.
- **Config surface**: agent-bios owns NO endpoint slot. It reads three files in the
  dashboard-owned `<home>/hooks/`: `token`, then `ingest-url` → `dashboard-url`
  (`collect-learning.py:319-345`). The writer is the dashboard setup script, which
  writes `token` (chmod 600) and `dashboard-url` (`setup-script.ts:89-92`);
  `ingest-url` is a migration-era slot. Default install: none exist → upload prints
  a skip notice. No env var or config key in the shipped set matches
  `INGEST|ENDPOINT|_URL|TOKEN|API_KEY`.

Compatibility constraints extraction must hold: the path, the token header, the
identity-out-of-band rule, status-code-only responses, `schema_version` as the only
version marker, and the day1 hook-dir slots as one working provider of transport
config (the wrapper carries them once the core gets its own slot).

## 3. Zero-egress today — true for data, with one non-data exception

Full-text sweep of the shipped set found **one in-process network client** (the
learn drain, gated on the token file existing) and no egressing hook: the single
registered hook (`tooling-gotchas-hook.py`, owned by manifest name via
`compose/assemble.py:655`) has no network code. The dashboard's collectors are
installed and registered by the DASHBOARD's setup script into the same homes;
agent-bios's settings merge never touches entries it does not own
(`compose/assemble.py:318-345`) — verified coexistence, separate owners.

**The exception**: a non-dry-run `install` runs `launch/provision-venv.sh`
(`install.sh:829`) → `pip install textual==8.2.8` from PyPI (skipped when the venv
already imports textual; failure non-fatal). Dependency provisioning, not data
egress — but the roadmap's done-when control says "owns no network path" literally.
Step 2 scopes the control to **data egress** (no collection hook registered, no
endpoint configured, no code path transmitting locally derived data), keeping
install behavior unchanged; making venv provisioning lazy/opt-in is the alternative
if the user wants the literal reading.

Also on the shipped surface: `onboard` (not `install`) runs a live model probe
(`compose/canary.sh:37`); wrappers spawn the user's own host CLIs; the capability
`install` field (`install.sh:589` `sh -c`) is empty for both declared capabilities —
inert today, but it is an arbitrary-command slot the contract work should name.

## 4. Retained records (pairs with step 0's data-governance snapshot)

| Store | Identity | Content | Retention |
| --- | --- | --- | --- |
| `raw_learning_events` | `userEmail` COLUMN (body is identity-free; the row is not) | verbatim `payloadJson` | **none** — only RECEIVED→EXPORTED flip |
| `raw_ingest_events` | `userEmail` + `payloadJson` carries email, repo paths, free-text messages | verbatim collector body | no row TTL; GCS blobs 180 d |
| `sessions` + 5 child tables | `userEmail`, `claudeSessionId` | `SessionContext` holds first/latest user message, last assistant message, repo paths | none; child cascade on Session delete, `Session.user` blocks user deletion |
| `forge_collector_observations` | github login/id, git email — the linkage redacted elsewhere, kept here by design | — | 90 d TTL (the only real one) |
| `collector_health_snapshots` | none | error messages | none |

The learnings **export** re-attaches identity: envelope elements are
`{learning_id, user_email, schema_version, domain, received_at, status, payload}`
(`learning-export.service.ts:29-51`, cap 2000, admin-session + same-site only).
Frame-critique item 5 (provenance lineage before any public promotion) lands
exactly here: identity-free is a body property, not a pipeline property.

## 5. Version/auth mechanics worth copying or avoiding

- Sessions ingest runs three wire version markers with **warn-only floors**
  (below-min accepted and logged, `ingest/sessions/route.ts:48-53`) — the learnings
  side's single `schema_version` + forward-tolerance is the simpler model and is
  already what the corpus contract needs.
- No URL versioning, no content-type versioning anywhere; `openapi/external-api.yaml`
  (spec 0.1.0) covers 5 of 16 machine-facing routes and NOT learnings — the spec is
  decoration today, not authority. The contract extraction should not inherit that
  pattern: whatever step 2 writes must be the enforced authority or it is a third
  restatement.
- Dashboard auth choke point is `authenticate()` (`auth.service.ts:164`): hook token
  or session cookie; the admin export additionally rejects token auth outright.

## 6. Stale claims found and verified (fix queue, not step-2 scope)

- `claude/guides/learning-flow.md:106` (+ codex/ko mirrors): "Transport lands in
  Phase 2" — Phase 2 shipped; the guide installs in every install (tier `infra`).
- `SURFACES.md:183` + `IMPLEMENTATION_MAP.html:180`: claim `install.sh` calls
  `compose/register-hooks.py`; nothing calls it — live path is `assemble.py:655`.
  `register-hooks.py` ships callerless in `files[]` (`package.json:28`).
- `AGENTS.md` "learn/ five files ship" — `files[]` names six.
- Dashboard `ingest/learnings/route.ts:18-19` names `config/learning.schema.json`
  in agent-bios — no such path; authority is `learn/learning.schema.json`.
  `api/exports/learnings/route.ts:25-27` names `scripts/ingest-learnings-export.py`
  — actual path `learn/ingest-learnings-export.py` (author-side, unshipped).

## 7. What step 2 builds on this (the extraction, now unblocked)

1. A contract surface for the three corpus operations — `ingest-learning` written
   from the operating wire facts above; `publish-corpus`/`fetch-corpus` defined
   against the assembler's input set (`claude/` tree + `@scope/name` manifest),
   which today has npm as its only transport.
2. An agent-bios-OWNED transport-config slot, default unset (zero egress), with the
   day1 hook-dir as one compatible provider — the D-20260819-b515a0 default-install
   tier made real. The wrapper (step 3) carries the day1 provider.
3. The done-when gate: a control proving a default install registers no collection
   hook and configures no endpoint (data-egress scoping per §3), with its negative
   control.
