# Collection-loop — human curation finale · KICKOFF (historical record)

> **Status: DONE 2026-07-23. This is the kickoff as written before the run, kept
> as the decision trail — it is no longer a starting point.** Verified against
> real artifacts 2026-07-25: `config/promotions.json` carries the single
> promotion (`a6feee41…`, tier `domain`, `builder-base`) and
> `design/session-distill/ledger.json` has `L-01` at `status: placed` with
> `placed_anchor: tooling-gotchas.md`. The round-trip below completed end to end.

> Turn-key start point for the ONE remaining collection-loop task: the live
> human-in-the-loop round-trip (export → curate → promote → migrate). Everything
> automatable is already built, merged, deployed, and proven (see
> `[[collection-loop]]` memory). This is the human curation pass + running the
> promote/migrate scripts. Prepared 2026-07-23 (real-code verified).

## State (verified 2026-07-23 — re-verify the volatile bits before acting)
- **Mechanism COMPLETE + DEPLOYED.** Ingest endpoint + export route both LIVE in
  prod and auth-gated: `POST /api/ingest/learnings` → 401, `GET /api/exports/learnings`
  → 401 (both confirmed 2026-07-23). npm **v0.8.0 = latest, globally installed**.
- **Nothing curated yet.** `config/promotions.json` = `{"version":1,"promotions":[]}`;
  0 promotions ever; `build-promotions.py --check` = "current with the ledger". This
  is a clean first run.
- Scripts present + gate green: `scripts/ingest-learnings-export.py`,
  `scripts/build-promotions.py` (`--check` is a check-parity gate),
  `scripts/migrate-learnings.py`. Ledger = `design/session-distill/ledger.json`
  (82 entries; ~29 incubating). Domains = `config/domains.json`.
- Repo = agent-bios `/Users/kangmin/Documents/agent-bios`. Cross-repo (dashboard,
  for the export API) = `/Users/kangmin/Documents/day1co-ai-usage-dashboard`.

## Prerequisites (the export step is the only gated one)
- **Admin BROWSER session on the dashboard.** The export route rejects hook tokens
  by design → it needs an OAuth login. Dashboard UI = `ai-litmus.day1co.kr` (Google
  OAuth). **사내 VPN (kpvpn) required** (off-VPN strips the OAuth param). The
  logged-in account must be **ADMIN**.
- Everything after export is local CLI in the agent-bios repo — no VPN.

## Procedure (ordered — detail in `CURATION-INTAKE.md` + `PHASE4-ROUNDTRIP-DESIGN.md`)

**0. Export (admin browser).** Logged into the dashboard as admin (VPN on), pull:
   `GET /api/exports/learnings` (everything still RECEIVED) — or scope with
   `?domain=…&from=…&to=…`. Periodically also run an **unfiltered** pull to surface
   NULL-domain rows. Save locally, e.g. `~/learnings-export.json`. The export flips
   RECEIVED→EXPORTED (re-pull with `?includeExported=true`).
   **PII: the file carries `user_email` + free text — never commit, never paste to a
   shared channel.** (First pull also answers: is there real learning data yet? If
   users haven't run `learn!`, it may be empty — then seed one test learning to prove
   the round-trip, or wait for real volume.)

**1. Deterministic intake.**
   `python3 scripts/ingest-learnings-export.py ~/learnings-export.json --out ~/worklist.json`
   → buckets: `entries` (valid → ledger-candidate shape), `rejected`, `deferred`
   (schema_version≠1), `warnings`, duplicates. Worklist is **local-only** (carries
   `_provenance.user_email`; `.gitignore` blocks `*worklist*` but keep it out of the repo).

**2. Curate (human judgment, per candidate).** Triage domain → classify
   (type A–G, layer, mechanism/verification/token_est/bar) → **novelty vs the FULL
   canon** (`claude/CLAUDE.md` + all `claude/guides/*`, NOT the installed subset) →
   fill ledger fields (`id`, `strength`, `criteria`, `classified`). See
   `CURATION-INTAKE.md` §2 + `PLACEMENT-FRAMEWORK.md`.

**3. Merge into the ledger + place (§P8).** Merge the finished entry into
   `design/session-distill/ledger.json` as `status: candidate` — **keep `learning_id`,
   DROP `_provenance` (PII)**. Then place it: edit the canonical `claude/` text/guide/
   hook, update `config/domains.json`, regenerate `codex/`+`ko/` mirrors, `bash
   scripts/check-parity.sh` green. Flip to `status: placed` **AND set `placed_anchor`**
   to the real `domains.json` anchor/key where it landed (this is the enforced Phase-4
   contract — a missing/unresolvable anchor FAILS `build-promotions --check`).

**4. Promote.** `python3 scripts/build-promotions.py` → derives
   `config/promotions.json` (audience {tier, domains} from the real placement).
   `python3 scripts/build-promotions.py --check` must be green (check-parity gate).

**5. Republish.** Bump version (`npm version minor -m "Release v%s"` — vX.Y.0
   convention), push commit+tag, `npm publish` (user has creds).

**6. Update + migrate.** On a packaged-install host: `agent-bios update` re-runs the
   assembler to deploy the new corpus; `install.sh migrate_learnings()` (best-effort,
   per host) / `scripts/migrate-learnings.py` prunes the user's personal copy of the
   promoted learning **iff** it's in that user's bundle AND the corpus is loaded.
   NOTE: this dev machine runs the ORIGINAL single-zone config — round-trip proof
   needs a packaged-install host or a scratch `CLAUDE_CONFIG_DIR`.

## Done-when
A learning travels end-to-end on the LIVE path: a real user's `learn!` upload →
admin export → curated + placed in the corpus → promoted → republished → on
`agent-bios update`, that user's personal `learnings.md` copy is pruned by
`learning_id`. One real promotion round-trip proven = finale complete.

## References
- `design/collection-loop/CURATION-INTAKE.md` — the full intake+curation procedure.
- `design/collection-loop/PHASE3-CURATION-DESIGN.md` / `PHASE4-ROUNDTRIP-DESIGN.md`.
- `design/session-distill/PLACEMENT-FRAMEWORK.md` (classification) + `HANDOFF.md` (§P8).
- Memory `[[collection-loop]]`, `[[lexicon]]`, `[[no-web-artifacts]]` (review docs = local files).
