# Collection loop — Phase 4 (round-trip proof: promote → migrate) — design

Status: **BUILT + verified 2026-07-21** on branch `collection-loop-phase-4`
(mechanism + scratch round-trip; the LIVE one-machine proof is the handoff — see
Boundary). Closes the loop: after a learning is promoted into the shared corpus,
the user-side **migrate** rule clears the now-absorbed **personal** copy — so a
promoted learning stops double-loading (once from the corpus, once from
`personal/learnings.md`). SSOT for the loop stays
`design/collection-loop/DESIGN.md`; terms follow `LEXICON.md`. Phases 0–3 are
DONE (Phase 3 merged; export route awaits a prod deploy).

## Goal (DESIGN.md Phase 4 + inherited rules)

Implement the user-side migrate rule off a **promotion manifest** shipped in the
push, then demonstrate the full done-when end-to-end. **The load-bearing safety
rule** (`design/corpus-domain-packaging.md:161-168`): migrate removes a personal
copy **only after verifying the promoted item is actually in THAT user's own
assembled bundle** — per-domain opt-in means a promotion into a package the user
did NOT install must NOT trigger removal (that would silently lose the learning).
Central never edits personal files; a ledger-global `placed` flip is not a
removal trigger. Bias: when unsure, **keep** (a kept duplicate is redundant; a
wrong removal loses data).

## Mechanism (three pieces + wiring)

```
curator places a learning (ledger status→placed, keeps learning_id)
  └─ build-promotions.py (release step): ledger.json → config/promotions.json
       (learning_id + placement domain/tier)                    [shipped in push]
push/install ──assemble.py deploys the selected bundle──▶
  └─ migrate-learnings.py (user-side, per host): for each promoted learning_id
       present in THIS user's bundle → remove its personal bullet + jsonl record;
       else keep. Never touches the user's hand-written '## Personal' section.
```

### D4.1 — Promotion manifest: `config/promotions.json` (derived, shipped)
`{ "version": 1, "promotions": [ { "learning_id": "<uuid>", "tier":
"core|infra|domain", "domains": ["<key>", …] } ] }` (`domains` empty for the
universal tiers).
- **Derived from the ledger** by `scripts/build-promotions.py`: every ledger
  entry with `status == "placed"` AND a `learning_id` (a promoted user learning,
  not a session-distill entry) → one promotion. The **audience** (tier + domains)
  is resolved from the entry's **`placed_anchor`** against `config/domains.json`
  — where the bullet ACTUALLY landed — NOT the ledger's free `domain` tag (F3).
  A missing/unresolvable `placed_anchor` FAILS the build/`--check`. Deterministic;
  re-runnable; regenerated before a push. Reuses `learning_id` — no new vocabulary.
- Shipped in npm `files` + present in the clone, so the user-side migrate reads
  it repo-relative. No PII (learning_id + audience only).

### D4.2 — User-side migrate: `scripts/migrate-learnings.py` (shipped, host-aware)
For a given host+home (mirrors `collect-learning.py`: `--host claude|codex`,
`resolve_home`), for each promotion:
- **In-bundle check (the safety gate), reusing `assemble.py` `kept()` semantics
  against the user's selection:** removable iff — the install is **non-packaged**
  (full corpus → everything installed); OR the promotion's **tier** is a
  **universal tier** (`core`/`infra`); OR (packaged, `tier == "domain"`) any of
  the promotion's **`domains`** is in `<state>/selection.json`. Otherwise **keep**
  (not in this user's bundle). Unknown tier → keep. The audience comes from the
  manifest (derived from the real placement anchor, D4.1), not a guessed domain.
- **Remove** (only when removable AND the learning_id is in the local personal
  zone): the `personal/learnings.jsonl` record line for that learning_id, and
  the prose bullet — claude: the `- […] … <!-- learning_id: <id> … -->` line in
  `personal/learnings.md`; codex: the same bullet inside the
  `agent-bios:personal-learnings` region of `AGENTS.md`. Back up before writing
  (like collect-learning). The upload-state file self-prunes next `learn!`
  (its ids are intersected with the present jsonl), so migrate leaves it.
- **Never** touches the entry `CLAUDE.md` `## Personal` (user-owned) or the
  `@personal/learnings.md` import (harmless if the file becomes empty; the header
  stays). Idempotent: re-running removes nothing already gone.
- `--dry-run` + `--self-test`; reuses `collect-learning.py` constants
  (`HOSTS`, `resolve_home`, `PERSONAL_START/END`) by path-import (single source).

### D4.3 — Install wiring (`scripts/install.sh`)
After the corpus is deployed (`assemble_packaged` / plain deploy) and before
verify, call migrate best-effort for each host (`|| true` — a prune failure
never fails an install). Runs on `install` and `update` (update = pull +
reinstall). Manifest absent / empty → no-op.

## Verification (falsifiable)

- **`build-promotions.py --self-test`**: a ledger fixture with a `placed`+
  `learning_id` entry, a `placed` entry WITHOUT learning_id (session-distill —
  excluded), and an `incubating`+learning_id entry (excluded) → manifest lists
  exactly the one promoted learning; deterministic.
- **`migrate-learnings.py --self-test`** (temp home, no network): seed a
  personal bullet+jsonl for L1 (domain `core`, universal) and L2 (domain
  `builder-base`) and L3 (domain `office-work`); manifest promotes all three.
  Non-packaged home → all removed. Packaged home with selection `{builder-base}`
  → L1 (core, universal) and L2 (selected) removed, **L3 kept** (office-work not
  selected — the silent-loss guard); jsonl + bullet both gone for removed, both
  present for kept; re-run is a no-op (idempotent); user `## Personal` untouched.
- **Scratch round-trip** on a throwaway `CLAUDE_CONFIG_DIR`: `collect-learning`
  writes a personal learning → `build-promotions` from a ledger that promotes it
  → `migrate-learnings` clears it → assert the personal copy is gone and the
  corpus (would) carry it. Proves the mechanism end-to-end without the live
  publish/deploy.
- **`check-parity.sh`** chains both new self-tests.

## Boundary (what needs the user — not buildable here)

The **live one-machine round-trip** (a real `learn!` → upload → the deployed
export → real curation → promote → `npm publish` → `agent-bios update` →
migrate) needs the export route deployed to prod, an `npm publish`, and a real
curation pass — all user-driven. Phase 4 delivers the mechanism + a scratch-dir
proof; the live proof is the handoff.

## Built artifacts (branch `collection-loop-phase-4`)

- `scripts/build-promotions.py` — ledger → `config/promotions.json` (release/dev
  tool; `--check` gate + `--self-test`). NOT shipped (manifest is generated in
  the clone at release time).
- `config/promotions.json` — the manifest (generated; currently empty — no
  learning promoted yet). Shipped.
- `scripts/migrate-learnings.py` — the user-side prune (host-aware; `--full` /
  `--selection-file` / `--domains`; `--manifest`; `--dry-run`; `--self-test`).
  Shipped; reuses `collect-learning.py` constants.
- `scripts/install.sh` — `migrate_learnings()` runs best-effort per host after
  the corpus deploy (install + update).
- `design/collection-loop/fixtures/ledger-promote-sample.json` — build-promotions
  fixture. `check-parity.sh` chains build-promotions `--self-test`+`--check` and
  migrate `--self-test`. `package.json` ships migrate-learnings.py + promotions.json.

**Verified 2026-07-21:** `check-parity.sh` green; `build-promotions --self-test`
(6), `migrate-learnings --self-test` (9, incl. the not-in-bundle KEEP guard,
both-host prune, idempotency, dry-run, user `## Personal` untouched);
`install.sh` `bash -n` clean; `npm pack` ships migrate-learnings.py +
promotions.json, not build-promotions.py. **CLI scratch round-trip** on a
throwaway home: real `collect-learning` writes a personal learning (secret
`<REDACTED>` at capture — the Phase 3 floor proven end-to-end via the CLI) →
a push manifest promotes it → real `migrate-learnings` removes the core
(universal) copy from prose+jsonl while KEEPING a builder-base copy under a
`{office-work}` selection (the silent-loss guard), idempotent on re-run.

## Review folded (2026-07-21) — one adversarial lens on the data-deleting path

- **F1 (ship-blocker, fixed):** `migrate_learnings` expanded an empty bash array
  as `"${dry[@]}"`; under `set -u` on **bash 3.2 (macOS default)** that is an
  unbound-variable error that aborted the install (empirically reproduced). Now
  `${dry[@]+"${dry[@]}"}`. Proven on `/bin/bash` 3.2.57.
- **F2 (silent loss of behavior, fixed):** migrate would prune while the corpus
  wasn't actually loaded (packaged user whose custom entry lacks
  `@central/bundle.md` — `assemble.py` exit 2, which install.sh logs and
  continues past). Added `claude_corpus_loaded()`: claude+packaged prunes ONLY
  if the entry imports `@central/bundle.md`; `--full` (inline monolith) and codex
  (always-loaded AGENTS.md region) are always loaded. corpus-not-loaded → keep all.
- **F4 (partial-failure desync, fixed):** prune PROSE first, jsonl second, so a
  prose-write failure leaves the id in the jsonl and a re-run self-heals; guarded
  the codex marker split against `END`-before-`START` (no-op, no corruption).
- **F5 (wrong-item deletion, fixed):** the bullet-id regex is anchored to the
  trailing `-->\s*$` comment, so a `learning_id` quoted in the lesson body can't
  shadow the bullet's own id.
- **F6 (bullet contract, fixed at capture):** `collect-learning.build_record`
  now collapses newlines in `lesson` so the personal bullet stays one line
  (a multi-line lesson would strand fragments past the by-id prune).
- **F7 (non-atomic writes, fixed):** all destructive prunes go through
  `atomic_write` (backup + tmp + `os.replace`), so a crash can't truncate the
  durable personal log.

- **F3 — HARDENED (2026-07-21, user-approved).** The former residual silent-loss
  path (the manifest `domain` was unverified curator metadata) is closed: a
  promoted+placed ledger entry now carries **`placed_anchor`**, and
  `build-promotions` **derives the audience (tier + domains) from that anchor's
  real `config/domains.json` registration** rather than the ledger `domain` tag.
  A missing/unresolvable `placed_anchor` FAILS `build-promotions --check` (a
  `check-parity.sh` gate), so a promotion can neither ship with a guessed
  audience nor ship without actually landing. The manifest shape is now
  `{learning_id, tier, domains}` (D4.1); the deployed v0.7.0 migrate (old
  `{…,domain}` reader) reads the new shape as `domain=None` → keep, so the shape
  change is data-loss-safe across the version skew.

### Known gaps (flagged, not silently closed)

- **F8 — pre-existing (Phase 1 deploy, not introduced here):** a **non-packaged**
  install overwrites the entry `CLAUDE.md` with the repo monolith (which lacks
  the `@personal/learnings.md` import) and overwrites `AGENTS.md` wholesale
  (destroying the codex personal-learnings region, backup only) — unwiring
  personal until the next `learn!`. Packaged installs (the ~500-user target)
  use `assemble.py`'s seed+merge and are unaffected. Tracked separately as a
  Phase 1 deploy fix.

## Deferred (not Phase 4)
- **Retire → reconcile** (symmetric correction feed for central retirements —
  `corpus-domain-packaging.md:169`): flag-not-delete; a separate later rule.
- Manifest pruning/versioning as it grows (fine as an append-only list in v1).
