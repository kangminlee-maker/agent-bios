---
created_at: 2026-09-04T23:10:16+09:00
head: 17862b3
kind: design
supersedes: null
---

# Blind design packet: end-user corpus management

## Role and stage

You are producing an independent frontier design draft. This is pre-implementation
architecture work. Missing implementation is not a defect. Do not edit files or perform
external side effects. Design from this packet only; do not assume facts not stated here.

## Goal

Design what agent-bios should look like when end users can build their own working
environment by managing the corpus. The required outcomes are:

1. Every corpus item can be reviewed, modified, and removed.
2. Corpus review is available as wiki-like documentation in the terminal UI and from a
   skill during an agent session.
3. Users can create corpus content. A corpus-creation skill is acceptable, but a better
   interaction may replace it.
4. Modification includes both content changes and changes to how the item is consumed.
   The TUI should offer a document-editor experience for content and a closed choice for
   consumption behavior; the session skill must support both too.
5. Every corpus item provided by the installed product can be restored individually at
   any time.
6. A command resets all settings to the installed state.
7. This turn is design only: propose high-level architecture and an implementation
   process, not code.

## Confirmed current state

- Canonical authoring is split: `claude/CLAUDE.md` owns global prose;
  `claude/guides|hooks|agents|skills` own their files; `compose/domains.json` owns
  classification. Codex globals and guides are generated projections and must not be
  edited directly.
- The core manifest identifies `@agent-bios/core`; a domain is package-local and the
  canonical domain key is `(package_id, domain)`.
- Current item identity is not uniform: bullets use mutable anchor substrings; guides,
  hooks, and agents use basenames; skills use directory names.
- Current consumption behavior is implicit in several axes, not one enum: manifest kind
  (`bullets|guides|hooks|agents|skills`), audience/tier
  (`core|domain|env-personal|infra`), host realization, and separate launcher/MCP config.
- The active consumption-surface catalog includes: global bundle, personal learnings,
  guide, skill, hook injection, agent description/body, launch contract, MCP tool
  surface, enforcement defaults, verification gates, receipt adjudication, capability
  withholding, and an incubator ledger. Prose surfaces and control surfaces are not
  interchangeable.
- The installer/assembler is the current write authority. The launcher sends corpus
  selection changes to `agent-bios onboard`; it does not write corpus destinations.
- Claude uses a user-owned entry file importing a managed central bundle. Codex uses a
  marker-bounded managed region in a user-owned AGENTS.md. User-owned and
  overwrite-managed bytes must remain separate.
- The current Textual TUI supports corpus status, a domain checklist, and whole content
  version rollback. It has no wiki browser, multiline editor, item CRUD, or reset.
- The installed Textual 8.2.8 runtime has `MarkdownViewer`, `Markdown`, `TextArea`, and
  `Tree`; a native wiki browser/editor is technically feasible. The numbered-prompt
  fallback still has to degrade usefully when Textual is absent.
- Existing corpus rollback is checkout-only, Git-history based, and moves only part of
  the realized corpus. npm users must reinstall an older whole package. Installer
  backups are explicitly a manual escape hatch and have no restore reader.
- `~/.local/share/agent-bios` is deploy-managed state and is purged by uninstall. It is
  not a safe canonical home for user-authored corpus.
- User-owned configuration already exists separately (`presets.local.toml`,
  `review-methods.local.toml`, `launcher.local.toml`), survives install, and is not reset
  today. Personal learnings and entry-file personal text are user data, not presently
  installer-owned settings.
- A multi-package architecture is already specified: authored packages are local,
  package ids are unversioned `@scope/name`, package manifests are prose-only, and the
  composer was deliberately deferred until the first real second package. A dormant
  `packages/agent-bios/visualization-docs` source tree exists but is not composed.
- The current corpus scope is inconsistent across the system: distribution describes
  the whole source tree, rollback covers only some carriers, and benchmark realization
  follows the installer manifest including skills. This design must establish one
  inventory/footprint.
- Deployment is not loading. File presence alone does not prove the host consumed an
  item. The current canary proves one global bundle revision, not independently loaded
  skills, hooks, agents, or future packages.

## Existing invariants to preserve

1. One value has one owner; views and host projections are generated.
2. User-owned content never shares an overwrite-managed canonical file.
3. Only paths/regions the product can prove it owns may be replaced or removed.
4. Destructive changes are previewable, recoverable, atomic, and serialized under one
   deployment lock from input validation through status publication.
5. A failed validation or apply leaves the previous effective corpus authoritative.
6. Claude/Codex projections preserve their different ownership boundaries.
7. A corpus that is deployed but not loaded must not be reported as active.
8. The rich TUI, CLI/non-TTY fallback, and in-session skill share one backend and one
   validation contract.
9. The model may draft semantic content and choose among valid options. Runtime owns ids,
   paths, metadata, serialization, validation, atomic persistence, deployment, and audit.
10. Canonical machine artifacts are accepted only through a bounded submit/apply route;
    free-form model prose never becomes artifact truth directly.
11. Current install behavior remains the default until the new manager is explicitly
    used; rollout must be reversible.

## Alternatives that must be compared neutrally

### Storage and customization

- Directly edit deployed files.
- Fork/copy the installed corpus into a user package.
- Keep an immutable installed baseline plus a copy-on-write personal layer containing
  overrides and removal markers.

### Identity

- Keep derived `(package_id, kind, anchor-or-filename)` locators.
- Introduce an immutable package-local item id independent of content and consumption
  surface, with a migration for existing items.

### Consumption choice

- Expose every internal consumption surface as one enum.
- Expose only prose-safe outcomes initially (for example always, when relevant, on
  request), while advanced mechanism surfaces use separate structured editors.
- Treat a surface move as delete-plus-create rather than preserving item identity.

### TUI and session integration

- Put all CRUD directly in the existing 10k+ line launcher.
- Build a standalone corpus manager/backend and deep-link to it from the launcher.
- Rely on an external editor and pager instead of native Textual widgets.
- Ship one lifecycle-wide corpus skill or separate review/create/edit skills.

### Reset and recovery

- Reset every app-specific file including user-authored corpus, learnings, and
  credentials.
- Reset settings/effective corpus while preserving user data.
- Archive user data and disable it, with permanent purge as a separate explicit action.
- Define restore against the current installed baseline or the bytes from the very first
  installation.

## Required design output

Produce one recommended default and explain why it wins. Include:

1. scope: the exact unit called a corpus item and which current surfaces are reviewable,
   editable, removable, or creatable in the first release;
2. concept map and identity model, explicitly choosing reuse, extension, rename, or split
   for existing `corpus`, `package`, `domain`, `consumption surface`, and `preset`;
3. canonical storage layout and ownership for installed baseline, personal sources,
   effective projection, status, change history, and recovery artifacts;
4. merge/update behavior when an installed item changes while a user override exists;
5. TUI information architecture for wiki review, search/navigation, editing, consumption
   choice, preview/apply, delete, restore, and reset;
6. session skill and deterministic CLI/tool contract, including accepted structured
   payloads and which fields runtime owns;
7. exact semantics for item delete, item restore, corpus reset, global settings reset,
   uninstall, and older-version rollback so the terms cannot conflict;
8. activation evidence for globals, guides, skills, hooks, and agents where applicable;
9. atomic transaction, locking, failure, and conflict behavior;
10. staged implementation plan with dependencies, verification points, migration,
    review gates, and redesign triggers;
11. a compact example showing an installed item modified, moved to another consumption
    behavior, removed, restored, and reset;
12. explicit non-goals and open owner decisions.

## Design principles to apply

- Concept economy: find the nearest existing concept first, prefer reuse/extension, add a
  lasting concept only when behavior, ownership, lifecycle, validation, failure mode, or
  user control genuinely differs. State the concept-surface cost.
- Capability boundary: instructions describe intent and semantic criteria; the runtime
  makes invalid paths unavailable, owns deterministic fields and side effects, validates
  allowed references, and creates canonical artifacts atomically.
- Staged workflow: choose the smallest viable path without reducing required behavior,
  runtime authority, or evidence. Define falsifiable done-when before implementation.
- Verification: enumerate cases from the registry, prove a non-empty subject set, use
  negative controls, and verify real dispatch/load paths rather than only serialized
  files.
- Portability: user-owned corpus should be inspectable, exportable, and usable after an
  npm install without requiring a Git checkout.

## Evaluation rubric

Rank the design by: goal fit; survival across install/update/uninstall; individual restore
clarity; no user-data loss; one source of truth; cross-host correctness; honest
consumption semantics; TUI/skill consistency; portability; implementation cost; future
package compatibility; and how little unnecessary concept or machinery it introduces.

