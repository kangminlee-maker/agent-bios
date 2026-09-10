---
created_at: 2026-09-07T21:28:52+09:00
head: ed5b00f
kind: design
supersedes: 2026-09-07T1818--ed5b00f--proposed-design.md
---

# User-managed corpus, private at rest and activated per session

Status: **PROPOSED governing design after Astra cross-validation.** This is the
high-level and implementation-process design. It authorizes no implementation.

This record accepts the current worktree's direction as fixed:

- installation stores agent-bios content privately;
- a clean install does not modify native global instruction files, discovery
  directories, hooks, configuration, or shell command resolution;
- plain CLI and Software Engineer / Vanilla receive no automatic agent-bios
  corpus;
- an explicit `agent-launch` activation resolves and pins an immutable corpus
  for that session;
- resume keeps that pin.

It supersedes the earlier session-scoped proposal by adding the complete
Corpus Manager lifecycle. It absorbs the stable-id, immutable-baseline,
personal-overlay, wiki/editor, preview/apply, and recovery contracts from
`../corpus-management/2026-09-04T2321--17862b3--proposed-design.md`, while
superseding that document's global deployment and globally discovered management
skill. The independent Astra findings and their evidence are recorded in
`2026-09-07T2126--ed5b00f--astra-cross-validation.md`.

## Product outcome

Users get one private corpus library and one manager. Installation by itself
changes no model context. Corpus Studio can be used immediately to review,
create, edit, remove, restore, and reset content. When the user launches an
agent-bios session, the launcher resolves the selected installed baseline,
personal changes, and session selection into an immutable snapshot, delivers
that snapshot through the host's per-call surface, and records the actual host
session id → snapshot binding. Vanilla receives none of it.

```text
installed package baselines        personal packages / overrides / learnings
             \                                   /
              └──── Corpus Manager + validator ─┘
                              │
                    immutable content snapshot
                              │
                    launch plan + session pin
                         ┌────┴────┐
                    Codex adapter  Claude adapter
                         │             │
                   activated session only
```

## Completion criteria

The feature is complete only when a real npm-only installation proves all of
these outcomes:

1. Fresh install leaves pre-existing Claude/Codex global files, discovery
   directories, settings, and shell commands byte-identical and adds no new
   globally loaded/discovered agent-bios content.
2. Plain CLI and Vanilla show no agent-bios rule, skill description, hook,
   agent registration, or launch contract; an explicitly activated session
   receives exactly its selected immutable snapshot.
3. Corpus Studio works before any activated session, and TUI, non-TTY CLI, and
   the activated-session management bootstrap use one manager and validator.
4. Every registered corpus item is reviewable, editable, removable, and—when it
   has an installed baseline—individually restorable without changing its stable
   identity or an unrelated item.
5. Create, content edit, consumption-surface edit, remove, restore, update,
   rollback, reset, and undo affect future snapshots only; existing and resumable
   sessions retain their recorded snapshot.
6. Learning capture evidence is immutable, local edits survive promotion, and a
   session whose selected baseline lacks a promoted replacement still receives
   the personal learning once.
7. Every successful installation record binds its baseline, defaults, and
   packaged settings as one tuple. Reset replays that tuple without guessing.
8. A crash or concurrent writer yields either the prior committed state or a
   fail-loud recovery record; no operation reports success over a split source,
   snapshot, host activation, or session pin.
9. The legacy global installation is removed only through an explicit,
   previewed, recoverable migration, and no remaining writer can recreate it.

## 1. Concept and authority decisions

| Concept | Decision |
| --- | --- |
| corpus | Extend: registered instruction items plus their resolved immutable snapshot; neither the private source tree nor one host projection is a second corpus authority. |
| package | Reuse `@scope/name`; an installed package owns baseline items and a reserved local package owns new personal items. |
| domain | Reuse `(package_id, domain)` as audience classification. It does not mean global installation. |
| consumption surface | Reuse, but scope every prose label to an **activated session**. “Always” means every activated session carrying that item, never plain CLI/Vanilla. |
| preset | Extend with a reference to a corpus selection. It never copies or owns instruction bodies. |
| selection | Extend the existing package/domain selection so a saved default or preset can seed one launch; a temporary launch choice does not silently rewrite the saved default. |
| personal area | Extend with packages, overlays, tombstones, learning sources, history, and trash outside overwrite-managed state. |

Two durable runtime identities are required:

```text
CorpusRef  = (package_id, item_id)
ContentRef = digest(canonical SnapshotInputs record)
```

`item_id` is immutable and package-local. A content edit, label change,
consumption move, source-path change, remove, or restore does not change it.
Package authors assign and preserve installed ids; runtime assigns personal ids.
Removed ids are never reused.

`SnapshotInputs` contains every value that can change emitted bytes: baseline
tuple ref, resolved selection digest, personal revision, both applicable
host-learning source revisions/digests, promotion/suppression manifest digest,
compiler/adapter schema, and management-bootstrap digest. `ContentRef` is
runtime-owned and content-addressed over that canonical record. It identifies a
complete immutable snapshot, not an authored corpus concept. A session pin maps
the actual host session id to this ref; the launcher derives ids, paths, digests,
timestamps, and serialization. Adding any new output-shaping input requires
adding it to `SnapshotInputs` and a control proving the ref changes with it.

This increases the lasting concept surface only where lifecycle differs:
stable item identity is required by individual restore, and a session pin is
required by resume. No new “workspace” concept or general precedence engine is
introduced.

## 2. Corpus item boundary

A corpus item is a registered logical instruction bundle containing:

- `CorpusRef` and origin;
- a human label and one or more content members;
- one consumption specification;
- separate audience/domain applicability;
- dependencies/route edges;
- lifecycle state (`active`, `removed`, `conflict`);
- zero or more host realizations.

The manager inventories agent-bios-owned global rules, guides, prose-only skills,
hook-injected prose, agent descriptions/bodies, and personal learnings. All are
reviewable. Existing items are editable/removable; installed items are
restorable. Advanced hook/agent bindings become editable only after the selected
host adapter proves their real session-only consumer.

One logical item may generate several files. A guide consumed “when relevant”
owns its guide body and its route edge, not a substring of shared physical router
prose. Route identity is derived from `(guide CorpusRef, route slot)`. The
compiler groups active edges and deterministically regenerates any shared router;
remove/restore changes one edge and must leave sibling targets reachable. Common
router prose with independent meaning is its own item.

A skill item owns its complete declared tree. Text members are editable; binary
or executable assets are replace-only through bounded artifact handles. V1
personal creation admits prose-only skills and no executable assets.

System control mechanisms—manager executable, session pinning, launch adapter,
MCP/capability registration, gates, receipt adjudication, and the private
management bootstrap—may be shown in the wiki's System view but are not mutable
corpus items. Manual user text and files another tool owns are outside write
authority.

## 3. Identity sources

Installed items use their package id and manifest item id.

V1 auto-creates one reserved, local-only personal package:

```text
@local/personal
```

A create request that omits a package always targets this package. The model
cannot invent another destination. Named package creation/export is a separate
explicit action; exporting the reserved package requires choosing a publishable
identity and creates a copy rather than silently renaming live refs.

The package initially declares one package-local `personal` domain, selected by
default in activated sessions. V1 items that do not name another explicitly
created local domain use `(@local/personal, personal)`; they never borrow a bare
domain id from core. Package/domain selections remain fully qualified.

Personal learning sources remain host-distinct and are exposed as adapter-backed
local packages:

```text
@local/learnings-claude  + item_id = learning_id
@local/learnings-codex   + item_id = learning_id
```

They are displayed together under Personal Learnings, but every operation,
receipt, upload state, and history entry keeps its host-qualified `CorpusRef`.
The two source authorities are never merged merely to simplify the UI.

## 4. Private storage and ownership

Conceptual Unix layout; platform adapters resolve the actual config/data homes.

```text
~/.local/share/agent-bios/
  runtime/                              # deploy-managed; uninstall may remove
    baselines/<baseline-ref>/
      defaults.json                    # selection + packaged settings for THIS baseline
      inventory.json
      packages/...
    baseline-current.json
    candidates/<baseline-ref>/...
    transactions/<transaction-id>/
      journal.json
      undo/...
    activations/<activation-intent-id>/
      journal.json
      host-output.log
    status.json

  sessions/                             # user session state; retained while referenced
    snapshots/<content-ref>/
      inventory.json
      launch-content/...
      guides/...
      skills/...
      hooks/...
      agents/...
      bootstrap/SKILL.md
    pins/<host>/<session-id>.json

~/.config/agent-bios/corpus/            # user-owned; install never overwrites
  selections/default.json
  selections/named/<selection-id>.json
  active-personal.json
  packages/local/personal/
    manifest.json
    items/...
  overrides/<package>/<item-id>/...
  tombstones/<package>/<item-id>.json
  learnings/claude/events.jsonl
  learnings/claude/upload-state.json
  learnings/codex/events.jsonl
  learnings/codex/upload-state.json
  history/<transaction-id>/...
  trash/...
```

Ownership:

- validated installed package bytes own baseline content and default metadata;
- each baseline owns the exact defaults/settings tuple valid for it;
- the reserved personal package owns created items;
- an override owns only its declared field mask and preserves the old base bytes
  needed for later conflict display;
- capture JSONL owns immutable learning events; overlays own local presentation
  changes;
- snapshots, inventories, pins, paths, ids, and status are deterministic runtime
  artifacts;
- TUI/wiki/skill pages render from the same sources and inventory.

Ordinary install/update never writes the user-owned tree. Ordinary uninstall
preserves it. Session snapshots and pins are user session state: uninstall may
remove unreferenced snapshots, but it preserves those needed by active/resumable
sessions and reports the retained location. Permanent local purge is the separate
operation that may remove them after listing affected resumptions.

The personal store is inspectable Markdown/JSON rather than SQLite. A generated
search index is a cache and may be rebuilt from authoritative files.

## 5. Corpus Studio and the three management clients

One manager backend serves:

1. **Corpus Studio** — rich TUI, available immediately after installation;
2. **non-TTY CLI** — JSON/Markdown/pager/editor flows;
3. **activated-session bootstrap** — a private skill-shaped procedure calling
   the same plan/apply API.

`agent-bios corpus` opens Studio directly. The launcher's **Corpus** entry
deep-links to the same screen. Installing this inert executable changes no model
context, so it is compatible with the no-global-corpus rule.

### Wiki/library

- Tree/filter by installed, personal, modified, removed, conflict, package,
  domain, consumption surface, and host.
- Search label, content, `CorpusRef`, package, domain, and state.
- Render with `MarkdownViewer`; internal `corpus://` links navigate without
  opening external URLs automatically.
- Default page is Effective Authoring. Tabs show Installed, My Change, Diff,
  Dependencies, Host Realization, History, and Sessions Using This Version.
- A session bootstrap additionally exposes This Session, showing the pinned
  snapshot beside current authoring state.

### Editing

- `TextArea(language="markdown")` for text; runtime-owned temporary files under
  `$VISUAL`/`$EDITOR` in fallback mode.
- Save creates a plan; it never publishes.
- Preview shows source diff, effective snapshot diff, affected future presets,
  validation, context-cost impact, conflicts, and retained pinned sessions.
- Apply is bound to the plan's expected authoring revision.
- Non-TTY mutation requires a structured payload and exact plan/revision.

### Activated-session management bootstrap

The manager ships one immutable private `SKILL.md` plus supporting procedure
files under each snapshot. Every activated launch includes a compact invocation
description and concrete path independently of optional domain, package, skill,
or tombstone selection. The bootstrap is outside corpus CRUD and cannot remove
itself.

On a host with proven session-only native skill registration, the adapter may
register it natively. Until then, the launch contract maps the `corpus`/`$corpus`
request to the exact private skill path. This is reported as **private procedure
access**, not falsely as native skill-menu registration. The acceptance test is
behavioral: an activated core-only session can invoke the path and use the same
manager API. Vanilla receives no description, path, or registration.

The bootstrap can inspect its pinned snapshot and current authoring state.
Mutations always target current source through a revision-checked plan and say
that the running session will not change; a new activated launch is needed.

## 6. Consumption surfaces in a session-scoped world

| User-facing choice | Meaning | Private realization |
| --- | --- | --- |
| Always in this environment | every activated session whose selection includes the item | appended/developer instruction fragment in immutable snapshot |
| When relevant | load after the trigger is recognized | private guide + generated route edge |
| When requested | explicit procedure invocation | private prose-only skill path; native registration only when proven |
| On a matching event | event-scoped injection | session-only hook adapter, disabled until its merge/consumer is proven |
| When delegated | only the selected subagent | compiled private agent definition, disabled until inheritance/dispatch is proven |

Audience/domain selection is independent of consumption. `removed` is lifecycle
state, not a surface. Moving prose into a gate, MCP tool, capability grant, or
executable hook is a development operation, not an enum choice.

Codex and Claude projections preserve native user/project instructions and
unrelated settings. Neither redirects the whole configuration home, copies auth,
temporarily edits global files, or depends on restoring shared state after
launch.

## 7. Authoring transaction versus session activation

These are two different transactions.

### Authoring transaction

Create/edit/move/remove/restore/reset/update changes private source and the
default for future resolutions:

1. Read authoritative baseline, selection, personal revision, and applicable
   learning revisions.
2. Produce a plan with semantic and generated diffs.
3. On Apply, acquire the manager transaction lock and re-read all revisions.
4. Reject stale plans, unknown/runtime-owned fields, invalid refs, unowned paths,
   invalid surfaces, and an empty inventory.
5. Write a candidate personal revision and immutable snapshot in staging.
6. Validate dependency closure and both host projections.
7. Atomically publish source pointers/status and journal the prior state.

No native global file changes. Existing session pins remain unchanged.

### Activation transaction

1. Resolve preset/default/temporary selection without mutating saved defaults.
2. Resolve or build the immutable `ContentRef` snapshot.
3. Before starting the host, create a durable `PREPARED` activation journal
   binding a runtime-owned intent id to host, `ContentRef`, launch selection,
   argv/contract digests, adapter version, and the retained snapshot.
4. Compose the snapshot and dynamic launch contract at the outgoing host boundary.
5. Start the host through an adapter that writes raw startup evidence to the
   intent's log. On observing the actual session id, the adapter first fsyncs a
   `HOST_OBSERVED` journal record containing that id, then returns it to the
   launcher. Parent-process survival is not required for this write.
6. Atomically write the session pin bound to host, session id, `ContentRef`,
   launch selection, and adapter version; mark the intent `PINNED`.
7. Report activated only after the real loader/registration evidence reaches the
   strength the UI claims.

GC and uninstall treat every nonterminal activation intent as a live retention
root. On restart, recovery reconciles `PREPARED`/`HOST_OBSERVED` against the raw
startup log and host session inventory: complete the exact pin when the id is
proven, or retain the snapshot and require an explicit orphan resolution. A
launch that never reached `PINNED` is never reported resumable. Resume resolves
the recorded pin, never current defaults. A missing snapshot is a recovery error
with a fetch/reinstall/archive path, not permission to choose latest silently.

## 8. Learning authority and promotion

### Capture is immutable

Each `learn!` call appends one immutable event to its host-specific private
JSONL. It never edits global `CLAUDE.md`/`AGENTS.md` or native discovery state.
An event's `learning_id` remains the upload/idempotency identity of those exact
captured bytes.

Editing that learning in Corpus Studio creates an overlay revision. It changes
future local snapshots but not the captured event or any already-uploaded remote
record. The UI states this. Uploading revised content is an explicit new capture
with a new `learning_id` and provenance link, not reuse of a settled id.

### Promotion suppresses per snapshot; it does not delete source

Promotion metadata selects a captured revision by host-qualified ref and exact
source/content digest. It also carries either a stable target-member ref or a
runtime-verified assertion that the target item exclusively represents that
learning. A whole-file/whole-guide locator is non-exclusive by default: naming a
container does not prove ownership of all content in it. The resolver suppresses
the personal copy only in an immutable snapshot that demonstrably contains the
corresponding effective replacement and would lose no local or sibling content.

- No local overlay + replacement present → snapshot contains the promoted copy
  once.
- Local overlay + a verified exclusive-item mapping + compatible surface → the
  local effective revision replaces/suppresses that dedicated baseline item, so
  exactly one version is emitted.
- Local overlay + a stable member mapping → replace only that member through a
  deterministic structural operation and assert every sibling member remains
  byte-identical.
- Shared/enriched target, whole-container-only mapping, competing customization,
  or incompatible surface → fail snapshot resolution with
  `learning_rebase_conflict`. Never semantically reconstruct a merged guide,
  emit both versions, discard sibling content, or erase the overlay.
- Older baseline, unselected package/domain, or missing replacement → keep the
  personal copy in that snapshot.
- Uncertainty → keep.

Rollback/deselection merely builds a new snapshot and recomputes suppression.
The source event remains available for every selection and audit.

### Concurrency

The manager owns one authoring revision. Each host learning source has its own
lock; a combined operation acquires Claude then Codex in fixed order while the
manager transaction lock is held. Capture takes its host source lock, appends,
and advances the source revision. Any plan that read an older revision fails and
replans. No new path writes whole native reader files, eliminating the current
central/personal-region lost-update race after migration.

## 9. Baseline, selection, update, and conflicts

A `BaselineTuple` contains:

```text
baseline refs + package/domain defaults + packaged settings + compiler schema
```

Every successful install records one immutable tuple. The current default pointer
selects a tuple. Two runtime-owned pointers have distinct jobs:

- `last_successful_install_ref` advances only after a complete install/update
  commits; a staged or conflicted candidate never changes it.
- `selected_baseline_ref` seeds future launches and may change through rollback.

Rollback changes only `selected_baseline_ref`; it never rewrites the successful-
install record. Corpus/full reset deterministically sets
`selected_baseline_ref = last_successful_install_ref` and restores the defaults
carried by that tuple. Therefore `T1 → install T2 → rollback T1 → reset` selects
T2, while a staged/conflicted T3 is ignored. Each tuple is validated against its
own package manifests before it becomes selectable.

Presets may reference a saved selection. A one-off launch may alter selection for
that launch only. A Studio action explicitly saves a new default or preset ref.

On package update:

1. no personal change → adopt new base;
2. tombstone + same id → remain removed;
3. disjoint field/member changes → deterministic combine;
4. same field/member changed on both sides → conflict;
5. upstream removed overridden item → choose convert to personal item, accept
   removal, or keep previous default tuple;
6. new baseline invalidates a surface/selection → conflict.

A candidate may be staged while conflicted. It does not replace future-launch
defaults until the entire graph validates. Existing session pins never move.

## 10. Recovery vocabulary

| Operation | Exact result |
| --- | --- |
| Remove installed item | Add a tombstone; future snapshots omit it. Baseline and existing pins remain. |
| Remove personal item | Deactivate it in a new personal revision; source/history remain recoverable. |
| Restore installed item | Remove its overrides/tombstone and use the item from the currently selected baseline tuple in future snapshots. An unselected domain remains inactive. |
| Recover personal item | Reactivate a historical personal revision; distinct from installed restore. |
| Undo | Apply an inverse plan to current authoring state; never rewind across later changes or session pins. |
| Corpus reset | Archive/deactivate active personal packages, overlays, tombstones, and learning projections; set `selected_baseline_ref` to `last_successful_install_ref` and restore that tuple's saved selection for future sessions. Sources/history/pins remain. |
| `agent-bios reset` | Corpus reset plus removal of agent-bios-owned launcher local settings. Return connections to zero-egress after explicit preview; secret values are deleted and never copied into recovery archives. |
| Rollback | Select another validated BaselineTuple for future sessions; personal intent resolves normally and existing pins remain. |
| Uninstall | Remove manager/runtime and unreferenced private artifacts; preserve user sources/history and snapshots referenced by active/resumable pins, reporting them. |
| Permanent local purge | Delete exactly listed local user/history/pin artifacts after confirmation. It makes no remote deletion claim and reports uploaded records that may remain remotely. |

If the selected baseline no longer contains an item, Restore refuses and offers
Recover Personal Copy or Roll Back Baseline. Reset never edits manual native
instruction text or another tool's files.

## 11. Host adapters and evidence

### Codex

- Keep `CODEX_HOME`, auth, history, and native settings in place.
- Read the effective existing `developer_instructions` through the real
  cwd/profile-aware config reader and preserve it before adding snapshot text and
  the dynamic contract.
- Use private generation-qualified paths for guides/procedures/assets.
- The recorded `skills.config` probe is a negative result; do not claim native
  private-skill discovery through it.
- Compile normal delegated agents with the intended snapshot or prove another
  inheritance route. Hermetic reviewers retain their declared isolation.

### Claude

- Keep normal user/project/local settings sources enabled.
- Append selected instruction text and dynamic contract per call.
- Use the existing per-call agent-definition route.
- Treat `--plugin-dir` or per-call hook/settings registration as candidates only;
  enable them after real merge, collision, child, and resume probes.
- Never use safe/bare mode or whole-home redirection as the general corpus switch.

### Status vocabulary

Distinguish:

- stored baseline;
- current authoring/default selection;
- composed immutable snapshot;
- session pinned;
- registered/reachable;
- observed loaded/invoked.

File presence never becomes “active.” Where the host emits no proof, report the
strongest lower state plus `activation unverified`.

## 12. Legacy migration

New installs take the private path immediately. Existing installs retain global
content until an explicit migration is accepted.

Migration inventory is derived from live ownership evidence:

- Claude active central/personal imports, central tree, hook registrations,
  agent/skill discovery files;
- Codex central and personal-learning regions, config additions, agents/skills;
- shell interception and already-running shell functions;
- current rollback and learning writers capable of recreating global state.

The TUI shows exact before/after bytes and paths. It backs up exact user files,
removes only proven markers/registrations/files, preserves foreign content, and
read-checks native registration state afterwards. Mixed or unprovable content is
an owner choice, never a broad deletion.

Writer retirement is part of the same migration release: install, rollback,
learn capture, promotion migration, reset, and uninstall must all target private
state before the default changes. A migration that cleans files while one old
writer remains is incomplete.

A temporary default-off development switch may preserve current behavior while
the replacement is built. It is removed when private installation is promoted;
the product does not keep two permanent content authorities.

## 13. Implementation sequence

### Stage 0 — lock the contract and population

- Add stable ids and one normalized inventory over every current instruction
  carrier; assert the population is non-empty.
- Add the reserved personal and host-learning source identities.
- Record executable negative controls for unmapped content, duplicate/reused ids,
  unowned paths, shared-router sibling loss, and empty subject sets.
- No runtime behavior change.

### Stage 1 — standalone read-only manager

- Parameterize multi-package validation/composition.
- Add private baseline snapshots, list/search/show/diff, and read-only Studio.
- Make distribution, benchmark realization, migration inventory, and wiki read
  the same registry.
- Verify npm-only operation from an arbitrary directory.

### Stage 2 — personal authoring and dry-run plans

- Add `@local/personal`, overrides, tombstones, learning adapters, history,
  route-edge regeneration, import/export, and conflict calculation.
- Implement plan validation with live apply still disabled.
- Reject arbitrary paths, symlinks, unknown/runtime fields, unsupported refs,
  invalid surfaces, stale revisions, and incomplete dependency closure.

### Stage 3 — immutable snapshots and session pins

- Build canonical `SnapshotInputs`, `ContentRef` snapshots and BaselineTuple
  records; prove every learning/promotion/bootstrap input changes the ref.
- Extend presets/selections by reference, not copied content.
- Implement pre-launch activation journals, adapter-owned host-id persistence,
  launch and resume pins, retention, stale/missing/orphan recovery, and
  current-vs-pinned Studio views.
- Prove the recorded host session id is the one actually launched.

### Stage 4 — learning writer migration

- Move future capture to the two private immutable event stores.
- Replace destructive promotion deletion with per-snapshot suppression.
- Add overlay/revision semantics and exact digest matching.
- Run concurrent capture/edit/promotion/reset/rollback matrices before enabling.

### Stage 5 — host activation and management bootstrap

- Codex instruction adapter first, using the already-positive off/on/off loader
  seam; then Claude per-call instruction/agent adapter.
- Include the private management bootstrap in every activated launch.
- Add guide/skill procedure paths; enable native hooks, skills, and agents one
  carrier at a time only after positive and negative real-loader controls.
- Prove active and Vanilla sessions simultaneously with unchanged global files.

### Stage 6 — live authoring and recovery

- Enable create/edit/move/remove/restore/reset/update/rollback/undo through the
  common transaction engine.
- Crash-inject at each source pointer, snapshot, activation, and pin boundary.
- Verify current sessions remain pinned and future launches change.

### Stage 7 — explicit legacy migration and promotion

- Implement previewed global cleanup and readback.
- Retire every old global writer before making private installation the default.
- Update current docs, ontology, surfaces, endpoints, implementation map, payload,
  mirrors, and release E2E.
- Remove the temporary rollout switch in the promotion change.

## 14. Verification matrix

Derive cases from the item registry, package manifests, host adapters, baseline
tuples, and stored pins rather than a handwritten subset. Required real-path
families:

- fresh install and migrated install;
- plain/Vanilla/activated, active+Vanilla concurrency, child, and resume;
- global rule, shared-router guide, multi-file skill, hook prose, agent body, and
  both learning authorities;
- create/edit/move/remove/restore/recover/reset/rollback/undo/update;
- upstream-only, user-only, disjoint, same-field, upstream deletion, invalidated
  selection/surface;
- capture before/after upload, local edit, promotion, older baseline, domain
  deselection, and remote-retention disclosure;
- snapshot-key movement when either host learning source, promotion suppression,
  bootstrap, compiler, or adapter input changes;
- crash after host start/id observation but before pin publication, followed by
  recovery, resume, GC, and uninstall;
- promoted exact revision plus local overlay: exactly one version or a named
  rebase conflict, never both;
- learning L promoted into a guide that also contains Q, then locally edited:
  either a stable member operation preserves Q byte-for-byte or resolution
  returns `learning_rebase_conflict`; a dedicated one-learning item retains the
  automatic replacement path;
- `T1 → T2 → rollback T1 → reset` and reset with a staged/conflicted T3;
- crashes and concurrent operations at every durable transition;
- uninstall with zero and non-zero resumable pins.

Each “all items” assertion first proves the subject set non-empty. Every new gate
has a planted negative control and is re-run after reverting the guarded fix.
File/dry-run evidence proves structure only; loader, invocation, child, and resume
claims require real host behavior.

## 15. Non-goals and redesign triggers

Non-goals:

- remote package registry, marketplace, signing, or trust scoring;
- arbitrary third-party executable hooks/scripts/MCP servers;
- automatic semantic conflict resolution;
- whole-home redirection or temporary global-file mutation;
- retroactive changes to running or resumable sessions;
- global deletion of remotely uploaded learnings without a delete protocol.

Return to design if:

- a required activated-session procedure cannot be reached without global
  discovery or host-home replacement;
- stable ids cannot cover a current carrier without changing package identity;
- a content snapshot cannot retain every resource its resumable session needs;
- personal composition requires arbitrary N-layer precedence;
- the explicit migration cannot prove ownership of a current global artifact;
- two implementation rounds reveal a new source authority or writer not modeled
  here.

## Review disposition

The synthesis was re-reviewed against current source by the Astra FRONTIER and
an isolated implementation-reality reviewer. Their union exposed incomplete
snapshot inputs, a host-start/pin crash window, ambiguous reset pointers, and an
over-broad promotion replacement. After the corrections above, both final
targeted passes reported **0 open material design defects**. Runtime/loader
claims remain proposed until the verification matrix executes them.

`Astra disposition: session-scoped activation remains fixed; the historical
Corpus Manager's source/identity/overlay/UI contracts are absorbed; global
realization and always-discovered skill are superseded; immutable learning
events, per-snapshot promotion suppression, activated private bootstrap, and
baseline-bound reset defaults close the four material review findings.`
