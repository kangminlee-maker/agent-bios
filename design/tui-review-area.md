# TUI review area — BACKLOG design note

Status: **ABSORBED 2026-07-26 — superseded by
`design/reviewer-registry/DESIGN.md`, which is the SSOT for this item.**
This note is the dated record of how the surface was first framed
(user-requested 2026-07-20); its live requirements now live under that file's
`## Surface`. Do not pick work up from here — the framing below predates the
ecosystem's two master levers (2026-07-26), which answered two of its open
decisions and narrowed the rest.

Original status: backlog. Captured so the work can start cold.

## Requirements (user's words, restated)

1. A dedicated Review area in the launcher TUI (precedent: the Session
   Learning mode — separated entry, inverted header, own hub).
2. onto-mcp and ultracode-for-codex are separately-installed services; when a
   user wants one, the TUI must install it on the spot.
3. Other (third-party/user-defined) review services must be pluggable.
4. Per-service execution choice: which backend (Codex CLI / Claude Code CLI /
   direct API) and which model.

## Existing assets to reuse (do not rebuild)

- `[capabilities.*]` in config/agent-launch.toml — already the
  install-gating registry ({command, install}); `install.sh
  handle_capabilities` + `install --with` already run install lines. The TUI
  install action shells out to the same single source.
- `REVIEW_SETUPS` / `effective_review` / `route_availability` — route
  composition and graceful degradation; the review area's status panel is a
  projection of these plus capability presence.
- `[hosts.*].onto_review` seats and Environment Binding — per-family model
  binding precedent for review seats.
- `presets.local.toml` pattern — user-owned config that installs never
  overwrite; a user-defined service registry should live in a sibling
  user-owned file (e.g. `review-services.local.toml`).
- codex-run adapter contract (self-contained packet on stdin, bounded
  report, pinned model/effort, read-only) — the invocation shape a
  third-party review service must declare.
- Severity contract (coding-staged guide Review Loop ladder) — every
  external service's output must map onto it; a service without a mapping
  cannot participate in material-issue gating.

## Proposed shape (sketch, to be designed properly at pickup)

- Root screen gains a Review area entry alongside Session Distill (same
  visual grammar: separator, marker, distinct hue).
- Hub: status panel (per-service: installed/missing, backend, model, live
  route availability; active review_setup and family) + actions:
  1. Install a missing capability — confirm, then run its registered install
     line; re-probe availability after.
  2. Add/edit a review service — registry entry in the user-owned file:
     {name, kind (logic/code/etc. for diversity accounting), backend:
     codex-cli | claude-cli | api, model, effort, command template,
     severity-map}. Model choice enumerates from [hosts.*].models (CLI
     backends) or a provider model list (api backend).
  3. Bind services into review setups — which setup uses which services,
     per-family seats.
- S4-04 rule applies structurally: the status panel shows each service's
  ACTUAL backing model/provider (from the dispatch audit log where
  available), not just its label.

## Open decisions for pickup

- API backend credentials: env-slot only (gitignored), never transcript;
  which env var convention per provider.
- Third-party invocation contract: exact stdin/stdout/exit + report schema a
  service must satisfy (align with codex-run channel contract).
- Whether review-service registry entries feed `effective_review` directly
  or through a projection step (launcher stays read+dispatch only).
- Verification: dry-run probes per service (liveness + severity-map
  conformance fixture) before a service becomes selectable in setups.
