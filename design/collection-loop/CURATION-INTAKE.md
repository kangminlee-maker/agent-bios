# Curation intake — procedure (collection loop, Phase 3)

How a curator turns a dashboard **learnings export** into **ledger candidates**
and rides them onto the existing packaging pipeline. Terms follow `LEXICON.md`;
the framework is `design/session-distill/PLACEMENT-FRAMEWORK.md`; design rationale
is `PHASE3-CURATION-DESIGN.md`. The deterministic half is
`scripts/ingest-learnings-export.py`; the semantic half (triage, classify,
novelty) is the curator's — the script never does it.

## 0. Export (dashboard, admin)

While logged into the dashboard as an ADMIN, download an export:

```
GET /api/exports/learnings?domain=<key|tier|unclassified>&from=<ISO>&to=<ISO>
GET /api/exports/learnings                      # everything still RECEIVED
GET /api/exports/learnings?includeExported=true # re-pull (recovery/audit)
```

The export returns each matching **RECEIVED** row verbatim and **flips it to
EXPORTED** (default pulls skip EXPORTED = "new since last pull"). Save the file
**locally** — e.g. `~/learnings-export.json`. **It contains `user_email` and
free-text payloads: never commit it, never paste it into a shared channel.**

- **NULL-domain sweep**: a row uploaded by a future `schema_version >= 2` client
  without a top-level `domain` stores a NULL `domain` column; a `?domain=…`
  filter (equality) will never match it, and `?domain=unclassified` won't either
  (NULL ≠ the string "unclassified"). Periodically run an **unfiltered** export
  so those rows surface (they stay RECEIVED until pulled — never lost).
- If a download fails after the flip, recover with `includeExported=true` over
  the same `from`/`to` window; the server logs each batch's `learning_id`s.

## 1. Deterministic intake (script)

```
python3 scripts/ingest-learnings-export.py ~/learnings-export.json --out ~/worklist.json
```

The worklist is **local only** (it carries `_provenance.user_email`); the repo
`.gitignore` blocks `*worklist*.json` as a guard, but keep it outside the repo
anyway. Buckets in the output:

- `entries[]` — VALID rows mapped to ledger-candidate shape (`status: candidate`,
  `id: null`, curator-only fields null, `learning_id` kept, `_provenance` block).
- `rejected[]` — schema or domain-membership failures (verbatim payload didn't
  conform). Inspect the reasons; usually discard (a malformed upload), or fix the
  record's source if it's a real client bug.
- `deferred[]` — `schema_version != 1`: Phase 2 stores v2+ verbatim, but the v1
  intake can't map it yet. Re-export via `includeExported=true` once a v2-aware
  intake exists. (No v2 client exists today.)
- `warnings[]` — e.g. the export's `domain` column disagreeing with
  `payload.domain` (a server-side bug signal).
- a candidate with `duplicate_in_ledger: true` — its `learning_id` is already in
  `ledger.json`; likely a re-export — reconcile rather than add a second entry.

## 2. Semantic curation (per candidate — the curator's judgment)

For each `entries[]` candidate, in order:

1. **Triage the domain.** If `domain` is `unclassified`, assign one from
   `config/domains.json` (domain keys ∪ tier names). Use `proposed_domain` as a
   hint; if a genuinely new area is warranted, register the domain first (curator
   authority) — domain creation is never automatic.
2. **Classify** via the bundle-classification procedure
   (`PLACEMENT-FRAMEWORK.md`): confirm/assign `classification.type` (A–G),
   `layer` (enforcement > gate > hook > guide > global > memory > incubator),
   and fill `mechanism`, `verification`, `token_est`, `underlying_value`,
   `meets_promotion_bar`. The candidate carries the user's slim
   `{type, layer, meets_promotion_bar}` as a starting point — re-derive, don't
   trust blindly.
3. **Screen novelty vs the FULL canon.** Compare the lesson against the
   **complete** canon — `claude/CLAUDE.md` (all tiers/domains) + every
   `claude/guides/*` — **not** the domain-filtered installed subset. A lesson
   already covered by a not-installed domain is `exists-in-canon`, **not novel**
   (else opt-in users mint permanent personal duplicates no dedup path clears).
   Set `verdict` (`novel` | `partial` | `principle`) accordingly.
4. **Fill the ledger fields**: `id` (curator short id, e.g. `S4-02`/`G-6`),
   `strength` (recurrence 1–4, or null for a principle), `criteria`, `classified`
   (date), and the full `classification`.

Cross-user dedup/merge is **v2-deferred**: each learning is an individual
candidate. If two candidates say the same thing, merge them by hand (their
distinct `supporting_sessions` raise `strength`).

## 3. Merge into the ledger + ride the pipeline

- Merge the finished entry into `design/session-distill/ledger.json` as
  `status: candidate`. **Keep `learning_id`** (non-PII — the dedup key that lets
  a later re-export be reconciled). **DROP the `_provenance` block** — it carries
  `user_email`; `ledger.json` is git-tracked and must never hold PII.
- From here the existing **§P8 placement** flow takes over
  (`claude/guides/session-distill-workflow.md`): edit the canonical `claude/`
  text/guide/hook, update `compose/domains.json`, regenerate `codex/` + `ko/`
  mirrors, run `bash gates/check-parity.sh` green (the domains gate validates the
  domain value), and `agent-bios install`/`update` re-runs `compose/assemble.py` to
  deploy — the learning now rides the same packaging pipeline as any distilled
  entry. Flip the ledger entry to `status: placed` with its `implementation` path.
- **Phase 4 migrate contract (record where it landed — `placed_anchor`).** When
  you flip a promoted learning to `status: placed`, ALSO set **`placed_anchor`**
  on the ledger entry to the `config/domains.json` anchor/key where the bullet
  landed (the bullet's `anchor`, or a guide/hook/agent filename). This is the
  ENFORCED contract: `scripts/build-promotions.py` resolves the anchor against
  `domains.json` and derives the promotion's audience (tier + domains) from the
  REAL placement — the user-side migrate then removes the personal copy for
  exactly the users whose bundle carries it. A **missing or unresolvable**
  `placed_anchor` FAILS `build-promotions --check` (a `check-parity.sh` gate), so
  you cannot ship a promotion that hasn't actually landed, nor one whose audience
  is guessed. Never flip `placed` before the bullet is really registered in
  `domains.json`. (The ledger `domain` tag stays for curation/reporting but no
  longer drives removal.) See `PHASE4-ROUNDTRIP-DESIGN.md` "Review F3".

Phase 4 (promote→migrate: the push clears the user's personal copy by
`learning_id`) closes the round trip — tracked separately, not part of intake.
