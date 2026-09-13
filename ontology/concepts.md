---
version: 1
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
| **F4 Distribution mechanism** | private installation, session delivery, ownership, and removal | `install.sh`, `compose/`, `launch/shell_integration.py` |
| **F5 Assurance** | what proves the other four stayed consistent, and what produces the evidence they cite | `gates/`, `session-cost.py` |

**ME argument.** The families are mutually exclusive by governance role. F1 is
the payload; F2 decides *which* payload; F3 names things outside this repo; F4
moves payload onto a machine; F5 asserts relations among F1–F4 and never
carries payload of its own. A concept that appears to sit in two families is
attributed to its primary enforcement point (`domain_scope.md`).

**CE argument.** Every tracked path outside the exempt record trees resolves to
exactly one family: `claude/` + `codex/` + `ko/` + `learn/` + `session-distill/`
(machinery) → F1; `compose/` → F2 with distribution authorities in F4; `launch/` +
`wrappers/` → F3 with shell ownership in F4; `install.sh` + `package.json` → F4; `gates/` + `session-cost.py`
+ every `--self-test` and `--check` entry point → F5.

That claim is executed, not asserted: **a coverage claim that was never run over
a non-empty subject is a hypothesis wearing an argument's clothes.** The sweep is
`ontology/check-ontology.py`'s coverage check rather than this paragraph, so an
omission fails a gate instead of surviving in prose.

## Identity rule

An entity is named by its **concept**, never by a path. Paths are properties,
because a path is exactly the thing that changes during a rename while the
obligations survive. Where a concept already carries a stable machine
identifier, that identifier *is* the entity id:

- a guide → its `guide_id` frontmatter value (`tooling-gotchas`, not the filename)
- a corpus rule → its `anchor` substring, the mechanism `compose/domains.json`
  `bullets[]` already uses; private catalog items carry stable package-qualified refs
- a review method / capability → its TOML table key
- a tier binding → `(host, tier)`

Reusing the repo's existing identity mechanisms rather than minting ontology-only
ids is what keeps the graph joinable to real code without a translation table.

---

## F1 — Instruction content

**corpus rule** — one instruction bullet selected for an activated session.
*Identity:* the manifest's stable item id; `anchor` locates the canonical bullet.
*Manifestations:* `claude/CLAUDE.md` → Codex and Korean projections →
`compose/domains.json` classification → `compose/corpus_catalog.py` inventory →
`compose/corpus_store.py` immutable snapshot → `compose/corpus_session.py` delivery.
Native global instruction files are preserved by private installation. The canonical
always surface permits reductions only; placement additions use another surface.
*Missed when:* an unclassified rule is absent from the catalog, or a selected rule
points at a guide excluded from the same snapshot.

**guide** — a scoped instruction document reached through a selected private
router or explicit request. *Identity:* `guide_id` frontmatter and catalog ref.
*Manifestations:* `claude/guides/<id>.md` → Codex and Korean projections →
`domains.json` `guides{}` → private release → selected snapshot path → consumer.
Frontmatter supplies `use_when`, `core_rules`, and author-only withholding.
*Missed when:* a delivered pointer has no selected target or a source document has
no registered consumer. The domain and parity gates check declared relationships.

**agent template** — a subagent role definition. Launcher tier templates are
selected through `[hosts.<host>.agent_templates]` in `launch/agent-launch.toml`;
HELM is the main and is not a spawnable template. `reviewer.toml` is a Codex role
with no Claude source counterpart. Authored corpus agent items have separate
catalog refs and default-off native delivery. Claude's per-item plugins carry
those agents; their frontmatter translation to Codex is not implemented.
Registration or configuration is not evidence that a child executed the body.

**hook** — executable guidance for a supported host event. *Identity:* manifest
name and catalog ref. *Manifestations:* `claude/hooks/*.py` → `domains.json`
`hooks{}` and `source_guide` → common compiler in `compose/corpus_catalog.py` →
selected snapshot → `compose/corpus_session.py` adapter. `--corpus-native` is
required: Claude uses per-item plugins and Codex uses session configuration;
unsupported events remain non-executable. Existing native hooks and host trust
remain in force. Private installation does not register global hooks.
*Missed when:* a carrier is merely stored, registered without a supported event,
or credited with execution without an observed invocation.

**learning record** — the captured per-session artifact. *Identity:* the
`learning_id` the collector mints. *Manifestations:* `learn/learning.schema.json`
(shape) → `learn/collect-learning.py` (writer, PATH-reachable only via the
`learn` subcommand) → private `learnings/<host>/events.jsonl` through
`compose/corpus_store.py` → selected activated-session snapshots.
`learn/check-learning.py` validates the record; per-host `upload-state.json`
tracks delivery when transport is configured. `learn/promotions.json` supplies
promotion claims; the store suppresses a captured source in a snapshot only when
its exact digest has a safe selected replacement. Capture preserves user-global
instruction files and immutable source events.

**session distill pipeline** — the curator flow that learns from many directly
handled sessions and authors corpus improvements. *Identity:* `session-distill`.
*Manifestations:* the Python/JavaScript pipeline under `session-distill/`, the
`distill!` trigger, launch preset and hub, and the author-only
`session-distill-workflow` guide. It produces proposals and ledger evidence;
accepted placement follows current repo rules and delivery surfaces.
`session-distill/out/` is regenerable output. Dated design records are evidence,
not current runtime contracts. The live ledger and window registry remain their
own state authorities.

---

## F2 — Classification & packaging

**packaging tier** — `core | domain | env-personal | infra` (`domains.json`
`tiers`). Decides whether a unit is universal, opt-in, machine-local, or
plumbing. *Missed when:* a new unit lands untiered and the assembler's default
silently decides distribution.

**domain** — a package-local opt-in classification from `compose/domains.json`.
Core and infra inclusion and optional domain membership are interpreted by the
catalog/store. Derive the current domain names and memberships from the manifest;
individual item enablement can override selection.

**package identity** — `@agent-bios/core` (`domains.json` `package_id`,
`compose/pkgid.py`). Unversioned by design; the domain is package-local, so the
pair `(package_id, domain)` is the real key.

**selection** — qualified package/domain or item choices resolved by
`compose/corpus_store.py`. Installed defaults, personal selection, explicit
session requests, and per-item enablement determine future snapshots; they do not
rewrite existing pins. `selection.json` and `packaged_mode()` describe retained
compatibility installation, not the private store's selection authority.

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

**tier binding** — `(host, tier) → (model, effort)`, owned by
`[hosts.<host>.tiers.<tier>]` in `launch/agent-launch.toml`. Prompting guide
`targets:` coverage is checked by `launch/check-prompting-targets.sh`.
`gates/check_parity.py` derives guide display names through the profile's
`model_display` map; role-policy assertions remain separate from those names.
Launcher templates and wrapper role output have their own projection checks.
Model capability restrictions are a separate constraint from tier selection.

**capability** — an optional external tool (`[capabilities.*]`: `command`,
`install`, `offers = [{operation, adapter, hosts}]`). Data-only by contract: no
branch of the resolver reads a capability's identity, which is what lets an
unseen capability project with no code change.
*Missed when:* the name is advertised somewhere that copies the table instead of
deriving from it — the failure the `--with help matches the capability table` assertion was built to prevent after the
`--with` help text went stale on the first rename.

**review method** — a named review protocol in `[review_methods.*]`, with
capability, operation, instructions, output, perspectives, trials, order,
aggregation, and severity fields. User-owned local descriptors pass the same
reader and may not shadow shipped names. A configured route is a request;
receipts and their adjudication determine what actual dispatch can be credited.

**wrapper** — an internal dispatch adapter under `wrappers/`, carried by the
private release. Launcher review routes resolve the adapter they will execute.
The default install does not populate `$CODEX_HOME/bin/`; that native destination
belongs to compatibility installation. Each route must verify the resolved
adapter's arguments and result rather than infer execution from file presence.

**managed runtime** — the Python dependency environment supplied for a named runtime
role. `launch/provision-venv.sh` owns the Textual root pin; the author builder derives
the exact `compose/ui_runtime/manifest.json` and wheel set. The runtime loader verifies
and extracts those files temporarily before the package CLI imports UI modules.
Installation, package/current-checkout Corpus Studio and private/current-checkout
launcher rich paths need no prior Textual installation. Their corrupt-bundle outcome
is a named failure requiring repair. Normal exit and backend process replacement
release the temporary runtime. Standalone compatibility launcher copies and retained
in-process APIs separately support managed-environment/numbered behavior.
`gates/build-ui-runtime.py --check` and `--self-test` hold pin agreement, exact inventory,
metadata, hashes, licensing and offline loading against the source.

---

## F4 — Distribution mechanism

**CLI subcommand** — a user-invocable entry advertised and dispatched by
`install.sh`. The private dispatcher routes lifecycle commands to
`compose/corpus_install.py`, corpus management to `compose/corpus.py`, and
session understanding to `compose/corpus_understand.py`. The early `learn` branch
preserves stdin through fd 3. Compatibility dispatch has a separate explicit
`AGENT_BIOS_LEGACY_INSTALL=1` boundary. Extraction must cover all dispatch sites.
Private `install` and `onboard` open the UI unless `--non-interactive` is explicit;
selection flags initialize the shared `SetupController` plan. The Textual client in
`compose/corpus_setup_ui.py` renders choices while the controller owns preview/apply.

**deploy target** — a source-to-owned-destination write with a stated verification
and removal contract. `compose/corpus_install.py` inventories the private release
and its owned launcher projections. Release files are immutable and digest-checked.
Compatibility `deploy_file`/`deploy_glob`/`deploy_tree` calls retain separate
native-destination obligations; their verification does not establish private
session delivery.

**payload entry** — a path in `package.json` `files[]`. Gated derivationally by
`gates/check-package.sh`, which greps real `$REPO/...` references out of
`install.sh` and `compose/assemble.py` instead of holding a list. Breakage is
visible only on npm installs, which no repo-checkout test can see.

**deployment manifest** — ownership evidence for installed paths. The private
installer records exact release entries and owned projection digests in
`runtime/private-install.json`; verification and removal re-read that evidence.
The compatibility manifest and marked-region rules are inputs to explicit
migration. A stale path list alone does not authorize deleting user content.

**state artifact** — persisted authority or projection with named writers,
readers, identity, and validation. Private runtime and user `state.json`, baseline
inventories, transaction journals, immutable snapshot inventories, and host session
pins have distinct lifetimes. `compose/corpus-state.py` projects the launcher panel;
that projection is not the source authority for private reset or rollback.

**migration** — an explicit, recovery-backed transform of legacy native state
into private ownership, implemented by `compose/corpus_install.py` and
`compose/corpus_transaction.py`. Preview identifies exact owned inputs; apply
backs up originals, imports and verifies learnings, rechecks native inputs, and
retires only proven owned regions. Pending operations block conflicting writes.
Ambiguous ownership or changed inputs require recovery, not a guessed deletion.

**schema version** — the declared format contract of a persisted artifact
(`schema_version = 1` in `launch/agent-launch.toml`, `version: 1` in
`compose/domains.json`, the shape in `learn/learning.schema.json`).
*Why separate from migration:* it is migration's **trigger**. A format change
that bumps no version leaves already-deployed state unmigrated and silently
misread; a version bumped with no migration authored does the same. The pair is
the entity relation, and neither half is currently gated.

**user-owned file region** — a bounded managed span or discovery entry inside
otherwise user-owned native state. Default private installation preserves global
instructions, settings, and discovery directories. Explicit app registration owns
only its verified discovery link through `compose/corpus_app.py`; it carries no
selected corpus body and disables implicit invocation. Optional shell connection owns
only its marked `.zshrc` span and managed script through
`launch/shell_integration.py`. Explicit migration can retire proven legacy
agent-bios spans, imports, and registrations while preserving other content.
Every region writer needs a corresponding scoped removal and conflict check.

**shell interception** — an optional connection from bare interactive `claude`
or `codex` to the launch TUI. `launch/shell_integration.py` is the common CLI/TUI
owner, using `launch/agent-launch.zsh` plus a marked `.zshrc` block. New private
installs are disconnected until explicit restore; remove, reset, and uninstall
remove only owned connection material. Argument-bearing and non-TTY calls pass
through without added permission flags. An edited owned block or script is a
conflict; native instruction files are outside this operation's write set.

**environment variable** — a named runtime override with a precise authority.
`AGENT_BIOS_STATE_DIR` moves private runtime/session state;
`AGENT_BIOS_CORPUS_DIR` moves personal corpus sources;
`AGENT_BIOS_PACKAGE_ROOT` selects the session's package runtime.
`CLAUDE_CONFIG_DIR` and `CODEX_HOME` locate native host state,
`AGENT_LAUNCH_VENV` selects the optional interpreter, and `ZDOTDIR` locates shell
startup files. Each reader must preserve that scope; one override does not move
unrelated roots or the HOME-rooted learning transport slot.

**corpus assembler** — selection-aware composition owned by
`compose/corpus_catalog.py` and `compose/corpus_store.py` for the private path.
It combines the installed baseline, personal source, overlays, and host learnings
into a content-addressed snapshot. No-corpus mode emits no instruction text or
management bootstrap; imported host/project scope constrains selection.
`compose/corpus_session.py` delivers and pins native sessions separately, while
`compose/corpus_app.py` records explicit returned task context without claiming a
native pin or retracting earlier text. `compose/assemble.py` retains source parsing helpers
and the guarded compatibility assembly path; its native entry seeding and
settings merge are not default private behavior.

---

## F5 — Assurance

**gate** — an executable check owning a stated invariant, a subject set, and an
enforcement claim. Properties the ontology records for each: what it asserts,
its subject set, whether that set is *derived* or *hand-authored*, and whether it
carries negative controls. A gate whose subject set can be empty passes
vacuously and proves nothing.

**golden** — captured expected behavior with a named producer, such as
`gates/goldens/review-matrix.json` from `gates/capture-review-goldens.py`.
Its contents are payload; regeneration must preserve the intended contract.

**negative control** — a case asserting the gate *fails* when it should. The
densest population lives in `gates/check_parity.py`'s review-editor checks,
including a runtime-generated method id that proves an unseen reviewer projects
with no code change. A gate without one is unproven, not merely untested.
*Count deliberately unstated:* the per-check totals are a derived quantity, so
`ontology/check-ontology.py` computes them rather than this file asserting a number
that goes stale on the next added case.

**self-test** — the repo's `--self-test` convention (`check-domains.py`,
`check-learning.py`, `collect-learning.py`, `redact.py`,
`ingest-learnings-export.py`, `build-promotions.py`, `emit-mirrors.py`), each
run by `gates/check-parity.sh`.

**activation canary** — an observation that content reached a host, distinct from
stored-state verification. Private activation uses `compose/corpus_session.py`
with host-observed evidence and session pins; its evidence level does not imply
model compliance or corpus-agent execution. `compose/canary.sh` probes only the
retained compatibility global bundle. Neither a stored release nor a launcher
status projection is an activation result.

**measurement instrument** — the tool that produces the numbers the corpus
cites (`session-cost.py`; CONTRIBUTING.md binds it as the measurement authority
for each guide's `Evidence Base`, the single owner of numbers). *Why F5 rather than a
utility:* a guide's quantitative claim and the instrument that can reproduce it
are a pair, so changing the instrument's accounting changes what every cited
number means. Streaming snapshots sharing one message id are deduplicated by maximum.

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

한국어 요약: 엔티티는 파일이 아니라 개념이며, 지시 내용·분류와 패키징·역량
바인딩·배포 기구·보증으로 나눈다. 현재 배포는 private 설치와 선택된 세션 전달이며,
호스트 전역 쓰기는 명시적인 호환·이관 범위에만 속한다. 경로, 소비 지점, 검사와
의무는 실제 구현에서 다시 도출한다. 현재 개수는 생성된 그래프에서 확인한다.

## Related documents

- `domain_scope.md` — purpose, completion criterion, the two-axis model
- `structure_spec.md` — the manifestation axis and Golden Relationships
- `dependency_rules.md` — obligation edge types and enforcement status
- `instances/` — machine-readable nodes/edges with verified anchors
- `../LEXICON.md` — terminology projected from `instances/graph.json`
