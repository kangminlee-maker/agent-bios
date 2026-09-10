# LEXICON — canonical terminology (operated)

Single source of truth for the repo's shared, lasting concept names. Every
concept below has **one** canonical term; each term is bound to the concrete
identifiers (paths, config keys, variable/function prefixes, triggers) that
must carry it. Deprecated aliases must not appear as live identifiers — the
`gates/check-lexicon.py` gate enforces this (it fails if a deprecated token
resurfaces outside the archive allowlist, and fails if any token it enforces
is missing from this file, so the two can never drift).

Why operate a lexicon: it keeps the concept graph compact and grep-navigable,
so a rename or a new feature reuses the established name instead of minting a
near-duplicate — fewer name-driven bugs, smoother maintenance.

한국어 요약: 저장소의 공유 개념명을 한 곳에서 관리한다. 개념마다 정규명은
하나, 그 정규명이 실제 식별자(경로·설정키·변수/함수 접두사·트리거)에 어떻게
묶이는지 명시한다. deprecated 별칭은 라이브 코드에 다시 나타나면 게이트가
막는다.

## Core concepts

| Concept | Canonical term | Trigger | Bound identifiers / paths |
| --- | --- | --- | --- |
| The per-session learning **artifact** (a captured lesson: prose + JSON record) | **learning** | — | `learn/learning.schema.json`, `learn/check-learning.py`, `~/.claude/personal/learnings.md`, `@personal/learnings.md`, `POST /api/ingest/learnings`, `pending-learnings.jsonl`, ledger `entries[].lesson` |
| The **light**, per-user, single-session in-conversation capture flow that produces a learning; available in every session mode | **session learning** | `learn!` | `claude/guides/learning-flow.md` (guide_id `learning-flow`), `learn/collect-learning.py`, the `## Session Learning` corpus rule, `~/.claude/personal/learnings.md` + `learnings.jsonl`, `@personal/learnings.md` import (Claude); the `agent-bios:personal-learnings` region of `~/.codex/AGENTS.md` (Codex, no import). Identifiers stay on the `learn`/`learning` root — the hyphen token `session-learning` is the deprecated heavy-subsystem alias (below), so it must NOT appear in light-flow identifiers |
| The **heavy** curator/power-user pipeline that mines many sessions and distills them into corpus-grade items; runs only in its dedicated preset | **session distill** | `distill!` | `design/session-distill/` (HANDOFF, PLACEMENT-FRAMEWORK, ledger.json, versions.json), `session-distill/`, `claude/guides/session-distill-workflow.md` (+ codex/ + ko/ mirrors, `guide_id: session-distill-workflow`), `compose/domains.json` guides key, `[presets.session-distill]` + `[session_distill]` in `launch/agent-launch.toml`, `mode = "distill"`, `session-distill-state.json`, launcher `DISTILL_MODE`/`DISTILL_PRESET`/`distill_hub`/`session_distill_nudge` |
| The chronological record of **decisions about developing this repo** — what was decided here and which alternative it closed. Author-side: it never ships, which is exactly what separates it from **session distill** (a feature of the deployed package, run by its users). `gates/check-package.sh` declares `decisions/` author-side and fails if it enters `files[]`. Merging it into distill later stays open | **decision record** | — | `decisions/record-decision.py`, `decisions/decisions.jsonl`, kinds `design`/`direction`/`stop`/`steering`, `AGENTS.md` |
| The **deployed instruction content** (installable packages, versions, rollback, applied status) — the output both flows ultimately feed | **corpus** | — | launcher `load_corpus_status`/`corpus_summary_lines`/`_corpus_packages`/`_corpus_versions`/`_corpus_rollback`/`corpus_lines`, `corpus-status.json`, `AGENT_BIOS_CORPUS_STATUS`, `compose/corpus-state.py`, "Corpus status" / "Corpus packages" UI |
| A guided dialogue about why a coherent corpus bundle exists, its context, mechanisms and limits. Distinct from session learning (capture) and session distill (mining): this consumes pinned effective corpus as learning data. A meaningful user-first discovery may save a requested-only personal note and unlock a persistent UI trophy; semantic originality remains a judgment, not a provenance-check claim | **corpus understanding** | `understand!` | `compose/corpus_understand.py`, `claude/skills/understand/SKILL.md`, `launch/agent-launch.py` Understand! menu and `--understand`, private user `understand/state.json` reset generation |
| **Deep review** — a deep check on an IMPLEMENTATION (functional, adversarial, logic, scenario, stress). **One concept, two host-bound mechanisms, both the host CLIs themselves**: `ultracode` runs on Claude (the Claude Code CLI's own dynamic workflow — many agents, each candidate finding adversarially verified — opened by the keyword in the prompt), `codex-exec` runs on Codex (the CLI's non-interactive exec mode: the whole packet handed to one frontier-effort pass). Personal or third-party reviewers are not shipped; they register in the user-owned methods file | **deep review** | — | `[capabilities.ultracode]` + `[review_methods.ultracode]` (Claude, the `claude` backend); `[capabilities.codex-exec]` + `[review_methods.codex-exec]` (Codex, the `codex` backend). The legacy `review_setup`/route token `"ultracode"` is a **different namespace** — a setup name, frozen — and is bound to its tool through `LEGACY_ULTRACODE_CAPABILITY` in `launch/agent-launch.py` rather than by sharing the string, which is what lets the tool be replaced without renaming the route |
| The declared, per-review definition of defect for a system type × work goal — observer, defect, evidence bar, non-defects, classification enum (ONE class stop-relevant), stop condition, misclassification cost, goldens — chosen and declared BEFORE the review starts. Nearest neighbors, distinguished on purpose: the **severity ladder** answers *how bad*, never *whether* — a loop can plateau entirely inside "material"; **deep review** names mechanisms, and a criterion is what any mechanism is handed; **consumption surface** names where knowledge reaches a model. Ordering: system type + goal → defect criterion → classification → defect? → severity → materiality → stop evaluation | **defect criterion** | — | `claude/guides/review-defect-criteria.md` (+ ko/ + generated codex mirrors, `guide_id: review-defect-criteria`), `compose/domains.json` guides key; routed from `claude/guides/review-request.md` ("Declare the criterion") and the Review Loop of `claude/guides/coding-staged-workflow.md` |
| A place knowledge or a tool reaches a model from — global bullet, guide, hook injection, agent description or body, launch contract, MCP tool list, personal learnings — together with the zero-context places that shape behavior without entering the window: enforcement defaults, gates, receipt adjudication, capability withholding. **Extends `capability surface`** rather than forking a second word: both name what the runtime makes available, one at call time and one at load time. The dated 2026-07-18 routing record calls its subset **layers** and orders them by cheapness; that word stays in that record and is not a live identifier | **consumption surface** | — | `SURFACES.md` — the catalog and each surface's admission bar. Realized by `compose/assemble.py` (tiering, audience filtering), the router bullets in `claude/CLAUDE.md`, `claude/hooks/`, `claude/agents/` + `codex/agents/`, `launch/agent-launch.py` (contract projection, MCP registration, receipt adjudication), `wrappers/`, `gates/` |
| A **procedure for one task**, packaged as a directory the host scans and loads by name — `SKILL.md` with `name`/`description` frontmatter plus free subdirectories, the format both hosts share. Its description is registered every session, its body loads on call. One consumption surface among the others (see `SURFACES.md`), classified in the domain manifest like a guide, deployed as one tree to both hosts and owned by manifest name because the scan directory is shared with other tools | **skill** | — | `claude/skills/<name>/SKILL.md`, the `skills` key of `compose/domains.json` (coverage in `compose/check-domains.py`), `compose/assemble.py --selected-skills`, `install.sh` `deploy_tree`/`shipped_skills`/`selected_skills`/`prune_stale_skills`/`rmdir_skill_dirs`, `$CLAUDE_DIR/skills/<name>`, `$CODEX_DIR/skills/<name>`, `SURFACES.md` "Skill" |
| A repository's **own layer** of agent instruction — its `AGENTS.md` body and `CLAUDE.md` shim — which agent-bios **teaches how to fill and never fills**: the produced file belongs to that repository, carries no marker or version, and is never a deploy or prune target. The repo-charter skill produces it by reading invariants and traps out of the code | **repo charter** | — | `claude/skills/repo-charter/`, `design/repo-charter/`, `SURFACES.md` "Skill" (the taught-not-filled distinction) |
| The declared, greppable marker — the literal `(private)` on a line — naming an author or environment binding an adopter swaps: the response-language preference in the global, a guide's Environment Binding author examples. One half of the content-hygiene bar: `gates/check-hygiene.py` scans the shipped distribution (npm payload + ko corpus trees) and refuses org identifiers everywhere and author identifiers outside marked lines or per-reason exemptions, so the already-clean distribution stays clean by construction | **private binding** | — | `gates/check-hygiene.py`, `README.md` (Adopting elsewhere), `claude/CLAUDE.md` (the marked language bullet) |
| The core-owned **endpoint contract** — the network operations agent-bios speaks (`publish-corpus` / `fetch-corpus` / `ingest-learning`; `ingest-session`'s home is an open design question, its name only reserved): the ingest-learning wire contract extracted from the operating code, the transport-config resolution — the slot `~/.config/agent-bios/{ingest-url,token}`, whose resolution and failure rules `ENDPOINTS.md` owns rather than restates here, and the zero-egress default (a default install configures no endpoint and registers no collection hook) | **endpoint contract** | — | `ENDPOINTS.md` (the contract, author-side), `gates/check-endpoints.py` (holds the doc's wire literals against the code and the default against the real resolver), `transport_config` in `learn/collect-learning.py`, `~/.config/agent-bios/{ingest-url,token}` |

Semantic model: users **LEARN** (capture a learning) → curators **DISTILL**
(reduce collected learnings) → the **corpus** is redistributed. `learning` is
the artifact and stays valid wherever it means the artifact (e.g. "the
learning ledger", "placed learning items"); only the compound proper noun of
the heavy subsystem changed.

## Concept homes (gated)

A concept whose files are scattered is findable only by memory. Each concept below
names one canonical **home**; any machinery file whose path carries that concept's
**slug** must live under it. `gates/check-lexicon.py` enforces this, which is what
keeps the layout guessable from a concept name instead of from a translation table.

Scope: machinery only. The corpus trees (`claude/`, `codex/`, `ko/`) are organized by
target because the harness loads fixed paths, `packages/` is organized by package
identity for the same reason — a package carries its own manifest and prose, so the
concept names repeat inside every package root — and `design/`, `benchmarks/` hold dated
records. A slug appearing in any of those is a mention, not a home, so they are exempt.

| Concept | Path slug | Home |
| --- | --- | --- |
| The launch profile, preflight, and shell interception | `agent-launch` | `launch/` |
| The **learning** artifact and the light capture flow | `learn` | `learn/` |
| The secret-redaction floor shared by both capture flows | `redact` | `learn/` |
| The **corpus** (deployed instruction content) and its state | `corpus` | `compose/` |
| Package identity for the domain-package ecosystem | `pkgid` | `compose/` |
| The domain manifest that classifies the corpus | `domains` | `compose/` |
| **session distill**, the heavy curator pipeline | `session-distill` | `session-distill/` |
| The repo's own dependency map — entities, obligation edges, code anchors | `ontology` | `ontology/` |
| The **decision record** for this repo's own work | `decision` | `decisions/` |
| The content-hygiene gate operating the private-binding marker | `hygiene` | `gates/check-hygiene.py` |

## Deprecated aliases (must not appear as live identifiers)

The gate forbids these exact tokens outside the archive allowlist. Bare
`learning` / `learnings` (the artifact noun) is NOT deprecated — only the
compound and identifier forms below are.

| Deprecated token | Replaced by | Reason |
| --- | --- | --- |
| `session-learning` | `session-distill` | heavy subsystem proper noun (paths, guide, domains key) |
| `session_learning` | `session_distill` | same, snake_case (config table, py identifiers) |
| `SESSION_LEARNING` | `SESSION_DISTILL` | same, env-var / constant form |
| `distillation` | `learning` | the light-flow artifact is a learning, not a distillation |
| `LEARNING_MODE` | `DISTILL_MODE` | launcher: the heavy hub mode |
| `LEARNING_PRESET` | `DISTILL_PRESET` | launcher: the heavy preset key holder |
| `learning_hub` | `distill_hub` | launcher: the heavy hub entry |
| `learning-status` | `corpus-status` | deployed-corpus status projection (`corpus-status.json`) |
| `learning-state.py` | `corpus-state.py` | deployed-corpus status/rollback tool |
| `AGENT_BIOS_LEARNING_STATUS` | `AGENT_BIOS_CORPUS_STATUS` | env override for corpus status path |
| `learning-rollback` | `corpus-rollback` | rollback backup directory under the state dir (`backups/corpus-rollback-<ts>`) |
| `distillation.schema` | `learning.schema` | the light-flow record schema is `learning.schema.json` |
| `check-distillation` | `check-learning` | the light-flow gate is `learn/check-learning.py` |
| `distillations.md` | `learnings.md` | the personal landing file is `~/.claude/personal/learnings.md` |
| `pending-distillations` | `pending-learnings` | the client retry queue is `pending-learnings.jsonl` |

Bare `distillation` is intentionally NOT gated: the heavy pipeline legitimately
uses "upward distillation" (deriving a principle). Only the specific
light-flow identifier tokens above are forbidden.

## Archive allowlist (deprecated tokens tolerated as dated history)

Historical design records are dated snapshots; their prose keeps the term as
written at the time. The gate ignores deprecated tokens under these paths:

- `design/session-distill/REVIEW-*.md`, `design/session-distill/DESIGN-v13-exploration-record.md`, `design/session-distill/BUNDLE-ko-review.md` — dated design-review ledgers and a superseded revision, written against the pipeline before it was renamed
- `design/collection-loop/DISCUSSION-*.md` — a discussion record, closed and dated on the day it finished
- `session-distill/out/` (regenerable pipeline snapshots; headings regenerate current from `bundle*.py`)
- `design/archive/` — dated records, never revised after the day they describe. Historical prose keeps the terms it was written with, so recording a rename must not turn the gate red; separately, no runtime file may name a record inside it, which `archive_referenced_by_runtime` enforces
- `LEXICON.md`, `gates/check-lexicon.py`, and `ontology/instances/graph.json` themselves (they hold the deprecated tokens to project / enforce / author them)

When you add a concept: find the nearest existing term here first; reuse,
extend, rename, or split explicitly, and update this file in the same change.
