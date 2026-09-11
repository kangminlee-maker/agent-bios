# Your corpus

[← Overview](../README.md) · [Corpus](corpus.md) · [Sessions](session-model.md) · [Recovery](recovery.md) · [Launch](advanced-launch.md) · [Understand!](understand.md)

Inspect, edit, and select the instruction library without rewriting native global instructions. Commands use the installed CLI; from a checkout, use `bash install.sh <command>` at the repository root.

## Consumption surfaces

| Surface | Delivery |
| --- | --- |
| `always` | Included in every activated snapshot selecting the item. |
| `relevant` | Available through the relevant-procedure router. |
| `requested` | Available as an explicitly requested procedure. |
| `event` | A supported native hook, requiring separate opt-in and host approval. |
| `delegated` | A supported native agent, requiring separate opt-in. |

## Manage the library

Corpus Studio and the machine CLI are views over the same `CorpusStore`. The CLI
provides `list`, `search`, `show`, `history`, `status`, and `snapshot`; mutations are
semantic JSON passed to `plan`, followed by `apply PLAN --expected-revision REV`.
Implemented operations are create, update (including consumption surface), enablement, remove,
installed-item restore, personal-item recover, selection, reset, and rollback. Stable
`CorpusRef` identities survive those changes. The current `ContentRef` hashes the
baseline, resolved selection, authoring/item/learning/promotion digests, catalog and
store implementation digests, and management bootstrap. There is not yet a standalone undo command,
arbitrary package authoring/import, automatic semantic conflict resolution, or verified
native skill-menu registration; those design stages must not be inferred from the
library UI.

Studio marks rules containing explicit `guides/*.md` references with **→ GUIDE**
and the guide names in the library. Their **Guide pointer** section links to exact
guide members in the same package and shows each target's current consumption surface
and state. Missing or ambiguous targets are disclosed rather than guessed. These
are display-only references, not new dependencies or proof of loading: rule bodies,
IDs, ordering, selection, and delivery remain unchanged. Personal body edits are
reflected when the library refreshes; ordinary rules are not classified by meaning.

Moving the library cursor to an item immediately displays its document; Enter is
not required. Group rows show group guidance and disable item-specific actions.
Cursor events cannot retarget an open editor or a prepared change preview.

Arrow keys also navigate the reading controls: **Search ↓ buttons ↓ library →
document**, with **←/→** between neighboring buttons and **↑** back toward search.
At the end of search text, **→** focuses the view selector; within text, the caret
moves normally. **←** from a closed view selector returns to search. Open menus
keep their native arrow selection. The library keeps normal **↑/↓** item movement;
at its top, **↑** returns to controls. In the document, arrows scroll until an
edge: **←** returns to the library, **↑** reaches the controls/member selector,
and **↓** at the bottom reaches pending on/off buttons when present. Disabled or
hidden buttons are skipped. TextArea editing, modal boundaries, and Tab remain intact.

In the library, **Space** toggles an item's use in future activated sessions:
`[x]` is on, `[ ]` is off, `[-]` is removed, and `*` marks an unapplied change.
The Available group means retained authoring items, not that every item is on.
Stage several choices, then use **Preview on/off → Apply**, or **Discard on/off**.
Text inputs keep normal spaces; Space on a group still expands or collapses it.
Unapplied choices require discard confirmation on exit and cannot be mixed with
content edits. A stale authoring revision refuses the preview or apply.

Per-item choices override domain and explicit launch selections, including core
and infrastructure defaults. Turning an item off does not delete its body, edits,
or identity, and old snapshots and session pins remain intact. Choices survive
updates and content restoration; full reset returns to installed defaults.
Enabling a removed item requires Restore/Recover first. A guide switched off is
marked in its referring rule, without automatically changing that rule. Native
hook/agent opt-in, trust, host support, and promotion rules still apply: a checked
item is a projection choice, not proof of execution. This does not block host
global/project instructions or a tool from opening a file independently.

The same revision-checked manager accepts `{"operation":"enable","items":{"@agent-bios/core:rule-003":false}}`
through `corpus plan`; `true` forces inclusion, `false` excludes, and `null`
removes that override so the normal selection applies. `list` reports `enabled`,
`enabled_override`, and the captured authoring `revision`; pass that revision as
`expected_revision` when planning a batch from the displayed inventory.

New personal identities are allocated once in the creation plan and remain stable
on retry; reset and history rollback do not make retired identities reusable.
Member files are the content authority: `primary_member` identifies the main file,
and `body` is its view or edit alias. The manager applies a body edit to that file
for all clients. Divergent older body/member values stay visible until an explicit
content choice reconciles them; old immutable snapshots are not rewritten.

## Included guides

| Guide | Scope |
| --- | --- |
| `cli-multi-model-workflow` | multi-model CLI workflow: Default Frame, role slots/tiers, delegation mechanics, driving Codex CLI directly, cache economy, unattended-batch safety, halt/resume, handoff contract, Environment Binding |
| `coding-staged-workflow` | staged development: design → process → implement, lightweight path, review loop, severity contract, stop conditions |
| `verification-discipline` | verification depth and per-domain mix (owns the Verification Menus), case space, what a green result is worth |
| `concept-economy` | concept-surface economy: reuse / extend / rename / split, split triggers, migration compatibility |
| `documentation-hygiene` | where comments, history, and handoffs belong; how to phrase rules others follow |
| `llm-capability-boundary` (+ `-patterns`, `-examples`) | LLM/tool/code authority boundary: field authority, accepted output channels, structural enforcement, worked examples |
| `mock-realization-boundary` | mock/fixture realization vs product semantic path |
| `svg-visualization-guide` | SVG diagram / service-blueprint spec |
| `implementation-map` | IMPLEMENTATION_MAP.html current-state dashboard |

The table names the load-bearing guides; the full inventory and its per-domain
classification live in `compose/domains.json`, which the domains gate holds against the
tree.

## Slides and presentations

The `slide-writing` guide is selected through `office-work` and
`visualization-docs`. Its primary guide supplies the semantic criteria for every
slide or presentation task. Its companion runbook and scripts are used only for
an explicitly applicable static HTML/PDF job: preparation derives a job-local
criteria copy and `ORACLE.json`, then freezes them with the job inputs and runtime
version. Jobs stay outside immutable corpus snapshots; preparation and result
acceptance need Python, while rendering uses the optional dependencies listed in
`DEPENDENCIES.md`. Native presentation formats remain the user's choice; the
supplied renderer's mechanical checks apply only to its static HTML/PDF path.

See [recovery](recovery.md) for migration, reset, and ownership conflicts, and [native launch settings](advanced-launch.md#native-hooks-and-agents) before enabling executable corpus content.
