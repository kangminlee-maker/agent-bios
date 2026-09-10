---
version: 1
last_updated: "2026-07-29"
source: manual
status: draft
---

# agent-bios Ontology — Core Entities

## Classification axis

**Axis: what the concept governs in the service.** Declared explicitly, single
axis at this level, per `~/.onto/domains/ontology/structure_spec.md`
("Classification Criteria Design"). Position in the derivation chain is a
*separate* axis and is not mixed in here — see `structure_spec.md`.

Five families:

| Family | Governs | Primary home |
| --- | --- | --- |
| **F1 Instruction content** | what the agent is told, and what authors it | `claude/`, `learn/`, `session-distill/` |
| **F2 Classification & packaging** | which content a given machine gets | `compose/` |
| **F3 Capability binding** | what external things exist and how they are reached | `launch/`, `wrappers/` |
| **F4 Distribution mechanism** | how content reaches a machine, what it may own there, and how it is undone | `install.sh` |
| **F5 Assurance** | what proves the other four stayed consistent, and what produces the evidence they cite | `gates/`, `session-cost.py` |

**ME argument.** The families are mutually exclusive by governance role. F1 is
the payload; F2 decides *which* payload; F3 names things outside this repo; F4
moves payload onto a machine; F5 asserts relations among F1–F4 and never
carries payload of its own. A concept that appears to sit in two families is
attributed to its primary enforcement point (`domain_scope.md`).

**CE argument.** Every tracked path outside the exempt record trees resolves to
exactly one family: `claude/` + `codex/` + `ko/` + `learn/` + `session-distill/`
(machinery) → F1; `compose/` → F2 with the assembler in F4; `launch/` +
`wrappers/` → F3; `install.sh` + `package.json` → F4; `gates/` + `session-cost.py`
+ every `--self-test` and `--check` entry point → F5.

That claim is executed, not asserted: **a coverage claim that was never run over
a non-empty subject is a hypothesis wearing an argument's clothes.** The sweep is
`gates/check-ontology.py`'s coverage check rather than this paragraph, so an
omission fails a gate instead of surviving in prose.

## Identity rule

An entity is named by its **concept**, never by a path. Paths are properties,
because a path is exactly the thing that changes during a rename while the
obligations survive. Where a concept already carries a stable machine
identifier, that identifier *is* the entity id:

- a guide → its `guide_id` frontmatter value (`tooling-gotchas`, not the filename)
- a corpus rule → its `anchor` substring, the mechanism `compose/domains.json`
  `bullets[]` already uses (114 entries, `{anchor, tier, domains}`)
- a review method / capability → its TOML table key
- a tier binding → `(host, tier)`

Reusing the repo's existing identity mechanisms rather than minting ontology-only
ids is what keeps the graph joinable to real code without a translation table.

---

## F1 — Instruction content

**corpus rule** — one always-on instruction bullet in the global file.
*Identity:* `anchor` substring. *Manifestations:* `claude/CLAUDE.md` (canonical,
154 lines) → `codex/AGENTS.md` + `ko/claude/CLAUDE.md` + `ko/codex/AGENTS.md`
(derived by `gates/emit-mirrors.py`) → `compose/domains.json` `bullets[]`
(classified) → assembled bundle → `~/.claude/central/bundle.md` (deployed) →
the session load that makes it act (consumed).
*Missed when:* a rule is added to the canonical file but not classified, so it
ships to nobody; or it names a guide, tool, or subcommand whose entity does not
exist, so it instructs agents toward something absent.

**guide** — a scoped instruction document loaded when a corpus rule's pointer
fires. *Identity:* `guide_id` frontmatter. *Manifestations:* `claude/guides/<id>.md`
→ three mirrors → `domains.json` `guides{}` → deployed →
the pointing corpus rule → `gates/check-parity.sh` pointer-resolvability and
shared-anchor-phrase checks. Frontmatter carries `use_when` and `core_rules`,
which are consumed rather than decorative.
*Missed when:* a guide is added with no rule pointing at it (unreachable), or a
rule points at a `guide_id` that no file declares (dead pointer).

**agent template** — a subagent role definition. *Identity:* tier name.
*Manifestations:* `claude/agents/{frontier,sweep,workhorse}.md` and
`codex/agents/{frontier,workhorse,sweep,reviewer}.toml`, referenced from
`[hosts.<host>.agent_templates]` in `launch/agent-launch.toml`, required by name
at the hardcoded `required = {"frontier.toml", …}` set in `cmd_verify`.
*Asymmetry to record, not smooth over:* `reviewer.toml` exists on Codex with no
Claude counterpart. The ontology states the asymmetry; a graph that assumed
symmetry would be wrong in a way parity never catches.

**hook** — executable instruction that fires on a tool event. *Identity:*
filename. *Manifestations:* `claude/hooks/*.py` → `domains.json` `hooks{}`, whose
`source_guide` field binds the hook to the guide it enforces → registered by
`compose/register-hooks.py` (both install paths) → deployed under
`~/.claude/central/hooks/`, never the shared `~/.claude/hooks/`.
*Missed when:* deployed but unregistered — the file lands and never fires; or
registered under a path marker rather than a manifest name, which is how one
machine ended up firing the same hook twice.

**learning record** — the captured per-session artifact. *Identity:* the
`learning_id` the collector mints. *Manifestations:* `learn/learning.schema.json`
(shape) → `learn/collect-learning.py` (writer, PATH-reachable only via the
`learn` subcommand) → `~/.claude/personal/learnings.md` + `learnings.jsonl` →
`learn/check-learning.py` (validator) → ledger → `learn/promotions.json`
(derived) → `learn/migrate-learnings.py` (the prune path that *deletes* user
learnings absorbed into the corpus).

**session distill pipeline** — the heavy curator flow that mines many sessions
into corpus-grade items, and therefore *authors* F1 content rather than merely
handling it. *Identity:* the concept slug `session-distill`, whose home LEXICON
already declares. *Manifestations:* `session-distill/{census,digest,batch,
screen-codex,collect,merge-ledger,bundle,bundle_final,update-state}.py` +
`{screen-claude,consolidate}.js`
(machinery) → trigger `distill!` → `[presets.session-distill]` and
`[session_distill]` in `launch/agent-launch.toml` → `mode = "distill"` and the
launcher's `DISTILL_MODE`/`distill_hub` surfaces → the
`session-distill-workflow` guide → `compose/domains.json` guides key.
*Scope boundary:* the machinery is in; `session-distill/out/` and
`design/session-distill/` are dated records and stay exempt (`domain_scope.md`).
*Missed when:* renamed on one surface only — LEXICON's deprecated-alias table exists
because that has already happened to this concept across its path, config-table,
env-var and launcher-identifier forms, and `gates/check-lexicon.py` is what now
catches it. The aliases are deliberately **not** spelled out here: that gate forbids
those tokens outside its archive allowlist and cannot tell a live identifier from
prose quoting one, so it flagged this very paragraph on the first run. Naming the
table instead of its rows is the fix, and the incident is the entity's own
`Missed when` demonstrating itself.

---

## F2 — Classification & packaging

**packaging tier** — `core | domain | env-personal | infra` (`domains.json`
`tiers`). Decides whether a unit is universal, opt-in, machine-local, or
plumbing. *Missed when:* a new unit lands untiered and the assembler's default
silently decides distribution.

**domain** — an opt-in bundle of instruction content (5 today: `builder-base`,
`llm-pipeline-dev`, `multi-agent-orchestration`, `visualization-docs`,
`office-work`). Every F1 entity carries a `domains[]` membership.

**package identity** — `@agent-bios/core` (`domains.json` `package_id`,
`compose/pkgid.py`). Unversioned by design; the domain is package-local, so the
pair `(package_id, domain)` is the real key.

**selection** — the machine's chosen domain set (`$STATE_DIR/selection.json`).
Its mere existence flips `packaged_mode()` (`packaged_mode()`), which changes
what `install` deploys *and* what `verify` is allowed to assert. A state file
that reroutes verification is an entity, not a detail.

**preset / mode** — `software-engineer | builder | distill`
(`PRESET_MODES`, `[presets.*]` in `launch/agent-launch.toml`),
plus the user-owned `presets.local.toml` merged at launch and never deployed.

---

## F3 — Capability binding

**backend** — the CLI actually executed (`[backends.codex|claude]`: `command`,
`bare_launch_args` — appended on a bare launch only; a configured launch projects the
preset's policy instead).

**host** — a model family seat (`[hosts.*]`: `provider`, `models`,
`agent_templates`). The provider→host reverse map must be unique
or a review binding resolves to no validatable seat.

**tier binding** — `(host, tier) → (model, effort)`. **The exemplar of why this
ontology exists.** Canonical at `[hosts.<host>.tiers.<tier>]` in
`launch/agent-launch.toml`; restated in the owning prompting guide's `targets:`
frontmatter and in that guide's dated `Environment Binding` table; asserted by
`launch/check-prompting-targets.sh` and the Environment Binding row assertions in `gates/check_parity.py`; and
shadowed by a hardcoded model-capability exclusion at
the `gpt-5.6-luna`/`ultra` exclusion in `launch/agent-launch.py` and `:3242`.
*Missed when:* the model is swapped in the TOML alone — but the sharper finding
is that `check_parity.py` **hardcodes the model names it is checking**, so it
proves the guide agrees with the gate, not with the launcher config. The gate is
itself a lockstep surface. `structure_spec.md` GR-7 carries the surface-by-surface
result; note that `launch/agent-launch.py` holds no tier→model binding of its own,
which an earlier draft of this file wrongly claimed before the file was read.

**capability** — an optional external tool (`[capabilities.*]`: `command`,
`install`, `offers = [{operation, adapter, hosts}]`). Data-only by contract: no
branch of the resolver reads a capability's identity, which is what lets an
unseen capability project with no code change.
*Missed when:* the name is advertised somewhere that copies the table instead of
deriving from it — the failure the `--with help matches the capability table` assertion was built to prevent after the
`--with` help text went stale on the first rename.

**review method** — a named way to obtain a review (`[review_methods.*]`:
`capability`, `operation`, `instructions`, `output`, `perspectives`, `trials`,
`order`, `aggregation`, `severity_emits`, `severity_map`). The legacy setup-name
namespace is deliberately separate and bridged by `LEGACY_ULTRACODE_CAPABILITY`
(`LEGACY_ULTRACODE_CAPABILITY`) rather than by sharing a string — the separation
is what allowed the two `ultracode` concepts to be renamed independently.

**wrapper** — an internal dispatch script (`wrappers/codex-run.sh`,
`wrappers/codex-helm.sh`) deployed to `$CODEX_HOME/bin/`.
*Missed when:* deployed at `the `deploy_file "$REPO/wrappers/codex-run.sh"` call-495` but absent from `cmd_verify`'s
subject set — `codex-run` is never compared, and the `codex-helm` check at
the `[ -x "$CODEX_DIR/bin/codex-helm" ]`-guarded dry run sits behind `[ -x ... ]`, so a missing wrapper **skips** the
check instead of failing it. A live `unguarded` edge, and the seed's motivating
example.

**managed runtime** — an interpreter environment this repo provisions rather
than assumes. *Identity:* the runtime's role name. *Manifestations:*
`launch/provision-venv.sh` (provisioner) → the venv at
`${AGENT_LAUNCH_VENV:-$HOME/.local/share/agent-launch/venv}` → the `import
textual` probe in `cmd_verify` → `DEPENDENCIES.md`.
*Carries a declared degradation:* provisioning failure does not fail the install;
it logs a warning and the launcher falls back to numbered prompts. **A declared
fallback is behaviour, not an error path** — it is reachable for real inputs, so
it belongs to the reproduction bar as much as the happy path does.

---

## F4 — Distribution mechanism

**CLI subcommand** — a user-invocable entry. *Three dispatch/advertisement sites,
not one:* the early branch at install.sh's early `learn` branch (`learn`, which must bypass the
flag parser to forward stdin, hence `exec ... <&3`), the `case "$CMD"` block at
`:859`, and the `usage()` advertisement at `:799`. Recorded because a
single-site extractor produces a confidently wrong graph.

**deploy target** — a `(source, destination, mode)` triple realised by
`deploy_file` (`deploy_file()`) / `deploy_glob` (`:100`). Every deploy target
owes a verify assertion and a manifest line; the manifest is what `uninstall`
replays, so removal is derived and safe, while verification is hand-authored and
therefore the drift-prone half.

**payload entry** — a path in `package.json` `files[]`. Gated derivationally by
`gates/check-package.sh`, which greps real `$REPO/...` references out of
`install.sh` and `compose/assemble.py` instead of holding a list. Breakage is
visible only on npm installs, which no repo-checkout test can see.

**deployment manifest** — the record of what this install wrote, and the sole
authority for `uninstall`.

**state artifact** — `selection.json`, `version.json`, `corpus-status.json`
(overridable via `AGENT_BIOS_CORPUS_STATUS`, projected by
`compose/corpus-state.py`). Each has a writer, readers, and a migration.

**migration** — a one-way transform of previously deployed state
(`migrate_state` `migrate_state()`, `migrate_user_presets` `:386`,
`migrate_learnings` `:453`). Order-bearing: `migrate_user_presets` must precede
the `profiles.toml` deploy that overwrites it.

**schema version** — the declared format contract of a persisted artifact
(`schema_version = 1` in `launch/agent-launch.toml`, `version: 1` in
`compose/domains.json`, the shape in `learn/learning.schema.json`).
*Why separate from migration:* it is migration's **trigger**. A format change
that bumps no version leaves already-deployed state unmigrated and silently
misread; a version bumped with no migration authored does the same. The pair is
the entity relation, and neither half is currently gated.

**user-owned file region** — a marked span this repo writes **into a file it
does not own**. *Identity:* `(target file, marker)`. *Manifestations:* the
`~/.codex/config.toml` additions merged from `codex/config-additions.toml`
(`codex_config_additions()`, operations `merge | check | remove`); the `.zshrc` line
guarded by `$HOOK_MARK` (`add_zsh_hook` `add_zsh_hook()`, `remove_zsh_hook`
`:439`, `ZSHRC` `:55`); the `agent-bios:central:*` region of `~/.codex/AGENTS.md`;
the seeded-then-user-owned entry `~/.claude/CLAUDE.md`; the merged
`claude/settings.template.json`.
*The ownership rule this entity exists to hold:* these are **not manifested**
(the comment above `assemble_packaged` stating the entry files are NOT manifested), so `uninstall` never deletes them — removal must be
surgical and marker-scoped. *Missed when:* a new region is added and only its
write path is implemented, leaving no `check` (verify goes blind) or no `remove`
(uninstall orphans it inside a user's file).

**shell interception** — the zero-argument launcher entry. *Identity:* the hook
marker. *Manifestations:* `launch/agent-launch.zsh` → deployed
`$LAUNCH_DIR/shell.zsh` (byte-compared in `cmd_verify`) **paired with** the
`.zshrc` line that sources it. *Why one entity and not two deploy targets:* the
pair must be installed and removed together — remove one side and the user's
shell sources a file that is not there, on every new shell.

**environment variable** — a runtime override that moves where this repo reads
or writes (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `AGENT_BIOS_CORPUS_STATUS`,
`AGENT_LAUNCH_VENV`, `ZDOTDIR`). *Why an entity:* an ontology that records the
default path as a constant is wrong for every machine that sets the override,
and the mirror-projection rule itself is defined in terms of
`$CLAUDE_CONFIG_DIR` ↔ `$CODEX_HOME`. Paths are properties of these, not of the
filesystem.

**corpus assembler** — the packaged-mode path that owns the corpus surfaces
outright (`compose/assemble.py`, entered via `assemble_packaged`
`assemble_packaged()`). It performs entry seeding, the codex marker region, and the
settings merge, which is why `cmd_verify` cannot byte-compare in packaged mode
and asserts selection-derived properties instead. *Split out of `deploy target`
deliberately:* a deploy target copies a file, whereas the assembler *composes*
one from a selection, so their obligations differ — the assembler owes
`gates/test-assemble.sh` scenarios, not a `verify_match`.

---

## F5 — Assurance

**gate** — an executable check owning a stated invariant, a subject set, and an
enforcement claim. Properties the ontology records for each: what it asserts,
its subject set, whether that set is *derived* or *hand-authored*, and whether it
carries negative controls. A gate whose subject set can be empty passes
vacuously and proves nothing.

**golden** — captured expected behaviour (`gates/goldens/review-matrix.json`,
7,476 lines, produced by `gates/capture-review-goldens.py`). Payload, with a
regeneration rule.

**negative control** — a case asserting the gate *fails* when it should. The
densest population lives in `gates/check_parity.py`'s review-editor checks,
including a runtime-generated method id that proves an unseen reviewer projects
with no code change. A gate without one is unproven, not merely untested.
*Count deliberately unstated:* the per-check totals are a derived quantity, so
`gates/check-ontology.py` computes them rather than this file asserting a number
that goes stale on the next added case.

**self-test** — the repo's `--self-test` convention (`check-domains.py`,
`check-learning.py`, `collect-learning.py`, `redact.py`,
`ingest-learnings-export.py`, `build-promotions.py`, `emit-mirrors.py`), each
run by `gates/check-parity.sh`.

**activation canary** — a post-install probe that the deployed corpus actually
*loads*, as distinct from having been written (`compose/canary.sh`, run by
`cmd_onboard` `cmd_onboard()`). It is the entity that separates "the bytes are
on disk" from "the agent is reading them" — the repo's own rule that a value is
inert until a consumer reads it, realised as a check.

**measurement instrument** — the tool that produces the numbers the corpus
cites (`session-cost.py`; README binds it as the measurement authority for each
guide's `Evidence Base`, the single owner of numbers). *Why F5 rather than a
utility:* a guide's quantitative claim and the instrument that can reproduce it
are a pair, so changing the instrument's accounting changes what every cited
number means. Its own defect history is on record — output tokens were
under-counted ~20× until streaming snapshots sharing one message id were
deduped by maximum.

---

## Deliberate non-entities

Functions, local variables, and control flow that nothing outside their file
depends on; the semantic wording of rules and guides (payload); and everything
under `design/`, `benchmarks/`, `research/`, `session-distill/out/` — mentions,
not homes, per `LEXICON.md` scope. Recording them would buy staleness and no
safety, and would breach the entity-relation ratio threshold (>3:1 classes to
relations) that flags an ontology listing things instead of connecting them.

**The `session-distill/` boundary is drawn deliberately**, because the tree
straddles the line: its scripts are live machinery and are in scope, while
`session-distill/out/` and `design/session-distill/` are dated records and are
not. Machinery in, records out — which is also what keeps the `LEXICON.md`
projection closable, since LEXICON declares `session-distill` a canonical
concept with a home and a projection cannot omit a concept its source declares.

한국어 요약: 엔티티는 파일이 아니라 **개념**이고, 분류 축은 "그 개념이 서비스에서
무엇을 지배하는가" 하나다 — 지시 내용(F1), 분류·패키징(F2), 역량 바인딩(F3),
배포 기구(F4), 보증(F5). 개념의 id는 레포가 이미 쓰는 식별자(`guide_id`, 규칙의
`anchor`, TOML 테이블 키, `(host, tier)`)를 그대로 쓴다 — 경로는 rename 때 바뀌고
의무는 살아남기 때문에 경로를 id로 쓰면 안 된다. 각 엔티티에는 *어느 나타남을
놓치면 무엇이 깨지는가*를 붙였다. 실물 두 건: 티어 바인딩은 다섯 표면에 걸쳐
있는데 그중 둘만 게이트돼 있고, `codex-run`은 배포되지만 verify가 한 번도
비교하지 않는다.

초안은 26개였고, 면제 트리를 뺀 55개 경로를 실제로 훑자 어느 계열에도 안 붙는
개념 7종이 드러나 **35개**가 됐다 — 사용자 소유 파일 영역, 셸 인터셉션, 관리
런타임, 스키마 버전, 환경변수 오버라이드, session distill 파이프라인, 그리고
카나리/비용계. 실행해 보지 않은 커버리지 주장은 논증의 옷을 입은 가설이라는
교훈은 지우지 않고 CE 논증에 남겨 뒀고, 그 스윕은
`gates/check-ontology.py`의 커버리지 검사가 된다.

## Related documents

- `domain_scope.md` — purpose, completion criterion, the two-axis model
- `structure_spec.md` — the manifestation axis and Golden Relationships
- `dependency_rules.md` — obligation edge types and enforcement status
- `instances/` — machine-readable nodes/edges with verified anchors
- `../LEXICON.md` — projected terminology view of this file's entity layer
