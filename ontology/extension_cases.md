---
version: 1
last_updated: "2026-07-30"
source: manual
status: draft
---

# agent-bios Ontology — Extension Cases

GENERATED from `instances/graph.json` by `ontology/emit-questions.py`. Do not edit.

Named change scenarios, each with the surfaces it touches. The impact tables are
**computed** by walking the obligation graph in each edge kind's declared direction —
the same traversal `ontology/impact.py` runs — so a table here cannot disagree with the
edges. An authored table would have been wrong the first time an edge moved.

6 cases over 21 obligations. Run
`python3 ontology/impact.py <entity>` for the live version of any of them.

---

## EC-1: Add a guide

**Situation.** A new scoped guide is authored under claude/guides/.

**Entity.** `Guide` (F1, guard gated, reaches
P1/P2/P3/P4/P5/P6) — anchored at `claude/guides/*.md guide_id frontmatter`.

### Impact — computed from the obligation graph

| Counterpart | Kind / direction | Enforcement | Why |
| --- | --- | --- | --- |
| InstructionsRule | requires ← | gated | The private compiler emits router links for selected relevant guides; legacy global pointers remain only on the retained deployment route |
| Hook | requires ← | gated | domains.json hooks[].source_guide binds a hook to the guide it enforces |
| Domain | owes_entry → | gated | Every instruction unit carries a domains[] membership |
| TierBinding | lockstep_with ← | partial | The prompting guide's targets: is gated; its Environment Binding table is not |
| MeasurementInstrument | asserts ← | **unguarded** | Each guide's Evidence Base is the single owner of numbers this tool produces |
| Guide | projects_to → | derived | emit-mirrors.py owns the claude to codex and ko projection rule |

### Verification checklist

- [ ] InstructionsRule — requires
- [ ] Hook — requires
- [ ] Domain — owes_entry
- [ ] TierBinding — lockstep_with
- [ ] MeasurementInstrument — asserts  ← nothing will tell you; check by hand
- [ ] Guide — projects_to

**1 of 6 obligation(s) here are enforced by nothing.**
---

## EC-2: Swap a tier binding's model

**Situation.** A tier is rebound to a different model or effort in launch/agent-launch.toml.

**Entity.** `TierBinding` (F3, guard partial, reaches
P1/P4/P5/P6) — anchored at `launch/agent-launch.toml [hosts.*.tiers.*]`.

### Impact — computed from the obligation graph

| Counterpart | Kind / direction | Enforcement | Why |
| --- | --- | --- | --- |
| Host | lockstep_with ← | partial | Launch profile bindings and agent templates are compared as site sets; the parity gate derives displayed binding rows from the profile model_display map |
| Guide | lockstep_with → | partial | The prompting guide's targets: is gated; its Environment Binding table is not |
| PresetMode | requires ← | gated | a preset carries host-scoped tier overrides, so it resolves against the binding |

### Verification checklist

- [ ] Host — lockstep_with
- [ ] Guide — lockstep_with
- [ ] PresetMode — requires

**0 of 3 obligation(s) here are enforced by nothing.**
---

## EC-3: Add a deploy target

**Situation.** install.sh gains a new deploy_file/deploy_glob call.

**Entity.** `DeployTarget` (F4, guard partial, reaches
P1/P4/P6) — anchored at `install.sh deploy_file, compose/instructions_install.py InstructionsInstaller.install, compose/instructions_app.py, compose/app_bridge/agents/openai.yaml`.

### Impact — computed from the obligation graph

| Counterpart | Kind / direction | Enforcement | Why |
| --- | --- | --- | --- |
| DeploymentManifest | owes_removal → | **unguarded** | Each writer preserves verifiable ownership for removal: private install metadata, shell receipt, app bridge generation or compatibility manifest |
| Gate | asserts ← | **unguarded** | Runtime private verification and instructions tests check private writes; ontology/extract.py separately discloses legacy deploy targets without complete verify assertions |
| PayloadEntry | owes_entry → | derived | check-package.sh greps real $REPO references rather than holding a list |
| StateArtifact | projects_to → | partial | Private installation writes its ownership record, baseline reference and status; compatibility install writes its version marker |
| ShellInterception | lockstep_with ← | partial | Optional shell restore owns the shell.zsh script and receipt; its bounded .zshrc block remains a user-owned region |

### Verification checklist

- [ ] DeploymentManifest — owes_removal  ← nothing will tell you; check by hand
- [ ] Gate — asserts  ← nothing will tell you; check by hand
- [ ] PayloadEntry — owes_entry
- [ ] StateArtifact — projects_to
- [ ] ShellInterception — lockstep_with

**2 of 5 obligation(s) here are enforced by nothing.**
---

## EC-4: Add a CLI subcommand

**Situation.** A new agent-bios subcommand is introduced.

**Entity.** `CliSubcommand` (F4, guard unguarded, reaches
P1/P3/P4/P5) — anchored at `install.sh, compose/instructions.py, compose/instructions_install.py, compose/instructions_understand.py, compose/instructions_import.py, compose/instructions_app.py, compose/instructions_setup.py, compose/app_bridge/scripts/bridge.py, compose/instructions_setup_ui.py, compose/instructions_setup_i18n.py, compose/instructions_setup_cli.py, compose/setup/START.md, INSTALL.md, docs/setup.md`.

### Impact — computed from the obligation graph

| Counterpart | Kind / direction | Enforcement | Why |
| --- | --- | --- | --- |
| DeployTarget | controls → | partial | Private install stores a pinned release and owns launcher projections; the explicit legacy install route writes native instructions destinations |
| CliSubcommand | precedes → | **unguarded** | usage() advertises the operations dispatched by case blocks and early command branches |
| Migration | precedes → | **unguarded** | Explicit migrate coordinates legacy cleanup and private installation; compatibility install runs its own migrations before deploy writes |
| ManagedRuntime | controls → | partial | Interactive package CLI entrypoints activate the verified UI bundle without persistent installation; explicit optional recipes separately provision the learning validator or compatibility environment |
| LearningRecord | controls → | **unguarded** | the learn branch execs the collector with the caller's stdin on fd 3; it is the only PATH-reachable route to capture |

### Verification checklist

- [ ] DeployTarget — controls
- [ ] CliSubcommand — precedes  ← nothing will tell you; check by hand
- [ ] Migration — precedes  ← nothing will tell you; check by hand
- [ ] ManagedRuntime — controls
- [ ] LearningRecord — controls  ← nothing will tell you; check by hand

**3 of 5 obligation(s) here are enforced by nothing.**
---

## EC-5: Change a persisted format

**Situation.** A persisted artifact's shape changes and its schema version is bumped.

**Entity.** `SchemaVersion` (F4, guard unguarded, reaches
P1/P5) — anchored at `compose/instructions_install.py SCHEMA_VERSION, compose/instructions_store.py, compose/instructions_session.py, launch/agent-launch.toml schema_version, compose/domains.json version, compose/instructions_setup_cli.py`.

### Impact — computed from the obligation graph

| Counterpart | Kind / direction | Enforcement | Why |
| --- | --- | --- | --- |
| Migration | migrates → | **unguarded** | A persisted-format change must preserve supported readers or provide the corresponding explicit migration |

### Verification checklist

- [ ] Migration — migrates  ← nothing will tell you; check by hand

**1 of 1 obligation(s) here are enforced by nothing.**
---

## EC-6: Add a user-owned file region

**Situation.** The installer starts writing a marked region into another file it does not own.

**Entity.** `UserOwnedFileRegion` (F4, guard partial, reaches
P1/P4/P5/P6) — anchored at `launch/shell_integration.py, compose/instructions_install.py, compose/assemble.py, codex/config-additions.toml, compose/instructions_app.py, compose/app_bridge/agents/openai.yaml`.

### Impact — computed from the obligation graph

| Counterpart | Kind / direction | Enforcement | Why |
| --- | --- | --- | --- |
| DeploymentManifest | owes_removal → | partial | User-owned files require bounded span cleanup; the private shell receipt and explicit legacy migration preserve surrounding bytes |

### Verification checklist

- [ ] DeploymentManifest — owes_removal

**0 of 1 obligation(s) here are enforced by nothing.**

---

## What these cases do not cover

Every case above is a change to something the ontology already names. A change that
*introduces* a condition — a new install branch, a new degradation path, a new external
dependency — has no case here, because the dynamic surface it would belong to is the
seed's declared gap (`competency_qs.md`, CQ-D-01, CQ-D-02, CQ-E-01).

한국어 요약: 변경 시나리오마다 영향 표를 **그래프에서 계산**한다 — kind별 의무 방향을
따라 순회하므로 표가 엣지와 어긋날 수 없다. 각 사례 끝의 "아무것도 강제하지 않는 의무"
개수가 손으로 확인해야 할 몫이다.
