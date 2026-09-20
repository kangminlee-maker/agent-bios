# Contributing to agent-bios

[← Overview](README.md) · [한국어](ko/CONTRIBUTING.md)

Requires an agent-bios checkout. [AGENTS.md](AGENTS.md) owns the working rules; instructions files are shipped payload, not instructions for developing this repository.

## Edit workflow

1. Edit the English canonical sources in `claude/`, and the Korean canonical in `ko/claude/` for user-facing changes.
2. Run `python3 gates/emit-mirrors.py`. Do not hand-edit generated `codex/` or `ko/codex/`.
3. Enable the commit hook once per clone with `git config core.hooksPath .githooks`. Run `bash gates/check-package.sh` and `bash gates/check-parity.sh`; allow several minutes.
4. Commit the validated changes. To deploy that checkout locally, run `bash install.sh install --non-interactive` from its root. The globally installed `agent-bios install` deploys its npm package instead.

The hook judges a snapshot of the index and refuses a commit if the index changes during validation. There is no CI; do not treat an unrun hook as evidence. Publication has a separate clean/reachable-commit guard and archive provenance. See [AGENTS.md](AGENTS.md) before publishing or changing a gate.

## Layout

| Path | Role |
| --- | --- |
| `claude/CLAUDE.md`, `codex/AGENTS.md` | canonical and generated always-surface sources (en); shipped privately and selected into activated snapshots, never installed into native global files by default |
| `claude/guides/*.md`, `codex/guides/*.md` | scoped-guide sources copied to immutable private snapshots when selected |
| `codex/agents/*.toml` | Codex role-template sources retained in the private release; agent-item activation remains separately evidenced |
| `ko/**` | Korean instructions projections and user/developer reference documents; never installed or model-loaded |
| `launch/` | launch profile and preflight TUI; `agent-launch.py` resolves a private snapshot for configured sessions, keeps Software Engineer / Vanilla bare, and routes resume through the recorded pin. Optional private zsh connection and retained legacy compatibility wiring are separate opt-in paths |
| `compose/` | instructions authority and clients: `instructions_catalog.py` inventory/compiler, `instructions_store.py` baseline/overlay/plan/snapshot store, `instructions.py` + `instructions_ui.py` management clients, private installation and its shared terminal/conversation setup controller, source-preserving instruction import, explicit app bridge, `instructions_session.py` host delivery and pins, and the immutable private management bootstrap |
| `learn/` | the collection loop — capture, record schema and its validator, curation intake, promotion manifest, redistribution, and the secret-redaction floor |
| `session-distill/` | the heavy curator pipeline that mines many sessions into instructions-grade items |
| `wrappers/` | internal host/review adapters carried by the private release; the default install does not populate native host bin directories |
| `workenv/` | Team work-environment runtime, at its contract freeze: `contracts/` owns the canonical byte form and digest of a contract record, the closed JSON Schema subset that reads contract schemas, and the contract error table (`errors.json` is generated from the modules by `python3 -m workenv.contracts.errors --emit`). No installed command reaches it and it is not in `package.json` `files[]`; `gates/workenv/check-workenv.py` runs its unit tests and pinned static analysis in the umbrella |
| `gates/` | author-side verification (mirror generation, parity, lexicon, payload, assembler scenarios) — reachable only from a repo checkout, and `check-package.sh` fails if any of it enters the npm payload |
| `ontology/` | what a change obliges elsewhere — entities, obligation edges, and the service's routes, held against real source by `check-ontology.py`. `instances/graph.json` is canonical; `LEXICON.md`, the RDF views, the HTML map, and the competency/extension docs are generated from it |
| `install.sh`, `session-cost.py` | the `agent-bios` command dispatcher/private installer entry and the cost meter |
| `decisions/` | the decision record for developing this repo — what was decided and which alternative it closed; author-side, never shipped |
| `packages/` | authored instructions packages, organized by package identity rather than by concept home |
| `.githooks/` | the pre-commit hook that runs the gates against the index, enabled per clone with `core.hooksPath` |
| `SURFACES.md` | where knowledge and tools reach a model, and what each place admits — every entry names the code that realizes it |
| `FINDINGS.md` | open implementation defects, live; closing one deletes its entry |
| `design/`, `benchmarks/` | design records and the instruction-behavior benchmark |
| `research/` | corpus research (the 12,749-file AGENTS.md/CLAUDE.md classification): reports, scripts, labeling record; bulk data stays local by `.gitignore` rule |
| `docs/` | user operations, session model, recovery, launch configuration, learning, and UI media |
| `DEPENDENCIES.md` | external tools / host CLIs / model providers + verified versions |

`config.toml`, `settings.json`, and `hooks.json` are machine-specific (trust lists, hook paths, secrets) and intentionally untracked.

## Instruction design

- **Rule bodies never name concrete models or tools** — only role slots and tiers. Bindings live in each guide's `Environment Binding` (dated; expire ~8 weeks or on a newer model). New model → update that row + date; leave rules alone. Declared exceptions: sections whose subject is a concrete tool surface (the cli guide's Codex direct-drive section) and optional-capability names inventoried in `DEPENDENCIES.md` (e.g. the `spreadsheet-processing` skill) — model-version-bound prompting guides also declare concrete `targets:`; see Adopting elsewhere below.
- **The Codex tree is generated, not mirrored by hand** — `gates/emit-mirrors.py` projects `claude/` → `codex/` and `ko/claude/` → `ko/codex/`, differing only in title and config-home variable (`$CLAUDE_CONFIG_DIR` ↔ `$CODEX_HOME`), plus one declared Codex-only standing-dispatch authorization required by Codex's trigger contract, inserted at a pinned position. It owns the projection rule; `gates/check-parity.sh` runs its `--check` and adds pointer resolvability, frontmatter, shared anchor phrases on the global↔guide restatement pairs that remain, and Codex role-binding / wrapper-default projections. Parity enforces content synchronization only; it does not guarantee both harnesses respond to the same wording with the same strength.
- **The always surface is a per-activated-session token budget** — selected rules reach that activated session; child reach requires its own projection evidence. The canonical always surface is frozen to reductions. Procedures, tables, numbers, and worked examples belong in guides.
- **Installation is storage, not activation** — `install` and `onboard` copy a validated immutable release into agent-bios-owned state and record a baseline plus selection. `verify` proves those stored bytes, the catalog, the baseline, and the owned launcher projection; it deliberately reports activation as unverified. A configured `agent-launch` resolves a snapshot and calls a host adapter; explicit app use returns selected snapshot text through the task's tool/context path.
- **The default installer leaves native host state alone** — it does not seed global `AGENTS.md`/`CLAUDE.md`, host skill/agent directories, hook settings, or shell interception. An explicit app connection registers only its owned discovery entry; it does not enable task instructions use. Existing installations keep their old global projection until `agent-bios migrate` previews and, with explicit apply confirmation, removes only proven legacy-owned material. `AGENT_BIOS_LEGACY_INSTALL=1` exists only for compatibility and migration regression coverage.
- **Source, snapshot, and session have separate lifetimes** — `InstructionsStore` revision-checks private authoring, compiles content-addressed snapshots, and preserves prior snapshots. `instructions_session.py` records a host-observed session id before a pin counts as resumable; reset and later edits affect future snapshots, not an existing pin.
- **Learning evidence stays immutable** — capture events are host-qualified private JSONL records. A local edit is an overlay for later snapshots; promotion suppresses only an exact source revision when its replacement is proven in that snapshot. Local reset, removal, or migration makes no claim that an uploaded record was deleted.
- **`Evidence Base` (per guide) is the single owner of numbers.** Measure with `session-cost.py` (`agent-bios cost` on an installed package).
- **English is canonical and shipped; Korean (`ko/`) is reference only.** The private catalog and snapshot compiler consume the fixed-name English sources.

## Adopting elsewhere

Review every `(private)` binding, the guide Environment Binding sections, and the environment-specific capabilities in [DEPENDENCIES.md](DEPENDENCIES.md). Re-measure each guide's Evidence Base before tuning. Personal adjustments can live in Instructions Studio; changes to the shipped defaults follow the canonical-source workflow above.

## Documentation and UI media

The root README introduces the user journey. `docs/` holds user operations and ships with the package; developer layout belongs here. The Korean README is reference-only. Keep the two entrypoints linked to their maintained references.

UI images must come from the real app with an isolated demo instructions, without private paths or account data. Label the app version and the runtime used for that capture. Current source entrypoints carry a verified UI bundle; a captured older release must keep its own version label. Do not imply that a headless UI capture proves a host session, review, or model call succeeded.
