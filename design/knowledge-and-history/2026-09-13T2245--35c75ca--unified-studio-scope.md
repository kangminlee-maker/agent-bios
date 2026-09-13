---
created_at: 2026-09-13T22:45:58+09:00
head: 35c75ca
kind: design
status: proposed-interaction-scope
amends: 2026-09-13T1857--35c75ca--environment-storage-design.md
consumption: 2026-09-13T2138--35c75ca--knowledge-memory-consumption.md
team_scope: 2026-09-13T2027--35c75ca--team-as-environment-unit.md
---

# Unified Studio: minimum product workflow

## Current coverage and decision

The current implementation is Instructions Studio, an InstructionsStore client for browsing, editing, selecting, and previewing instruction changes. It does not provide team environment composition, Domain knowledge management, or Decision memory views. See [the current app](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:210) and [the current library contract](/Users/kangmin/Documents/agent-bios-personal/docs/instructions.md).

The environment/storage design defined the data and authority boundaries while explicitly deferring whole-product UI redesign. The consumption design defined readers, but not the human-facing Studio workflow. The user's clarification now brings the minimum unified Studio interaction scope into the design. Detailed visual design and the final umbrella UI name remain deferred; this record uses Studio as the working label.

## Product boundary

Studio is the user-facing workspace for selecting, understanding, composing, and managing a team's work environment. It uses the existing providers and authority contracts. It does not become another storage authority or a universal editor over every record type.

The current Instructions Studio's library/editor/preview functionality becomes the Instructions area of that larger workspace. Its direct management route can remain available. This is intended functionality reuse, not a decision to embed one application instance inside another.

## Minimum information architecture

The shared context header identifies the selected Team, environment, and exact edition. It distinguishes an edited draft, the team's adopted edition, and the edition actually available or active for this worker.

| Area | Primary user question | Minimum functionality |
| --- | --- | --- |
| Work environment | Which setup will our team use, and can I work with it now? | Show the composition, exact source editions, permitted memory scopes, required/optional material, pending changes, adoption state, and local readiness. |
| Instructions | How should we perform the work? | Reuse current browsing, editing, item selection, consumption-surface inspection, revision-checked preview/apply, and recovery functionality. |
| Domain knowledge | What supports this judgment, and where does it apply? | Browse topic/question maps, inspect coherent support units and their source/period/conditions, expand evidence, and prepare a new revision or permitted derivative. |
| Decision memory | What is currently decided, why, and what remains unresolved? | Select authorized workstreams, show qualified current state, expand recorded reasons/evidence, and append decisions, outcomes, corrections, or withdrawals. |

These are four areas of one workspace, not four required databases or a mandated tab layout. Search and browsing make the active scope visible. Library availability is distinct from inclusion in the selected environment.

## Primary workflow

1. Select a Team and an environment edition, or prepare an explicitly owned draft/derivative.
2. Inspect its three content areas and declared requirements.
3. Add or replace references in the environment draft; source editing is a separate operation under the source owner's permission.
4. Preview the composition difference, affected knowledge/decision references, required gaps, and known conflicts.
5. Publish and/or adopt the exact edition through the appropriate existing authority and policy.
6. Check this worker's source access, host capabilities, context compatibility, and actual local delivery state before reporting readiness.

The UI must distinguish publication, team adoption, local readiness, and actual activation. An already-authorized policy remains applicable; this design does not require a new human confirmation for every read or reuse. Mutations use their existing revision checks and provider receipts.

## Editing is role-specific

Instructions and knowledge changes create new versions. A user who cannot edit a source may be able to create a separately owned derivative, but selecting the Team does not grant source rights.

Decision and event records are not edited as ordinary documents. Corrections target earlier assertions; withdrawals and replacements record actual changes of choice. Authorized deletion/retention is a distinct operation. A search filter, removal from a displayed view, or deselection of a source never silently withdraws a decision.

Use explicit action labels for the affected object: edit source, change environment composition, publish edition, adopt for Team, use in this task. A single generic active/latest badge or Apply action must not collapse those effects.

## Consumption preview

Studio offers a preview of what a selected task or question would receive. It calls the same knowledge and memory readers as other clients, under the same environment, authorized scope, exact editions/frontiers, and output budget.

Preview includes required gaps, source qualifications, and continuation information. It must not independently create a second summary or state reducer. Opening a document or completing a preview is not activation and does not prove model reading.

A context-inspection view can display the actual operation manifest and its relationship to the adopted edition. It should explain unmet requirements in terms a worker can act on, rather than expose internal hashes or recovery details without a reason.

## Minimum acceptance cases

- A new worker finds the team's adopted environment, discovers existing decisions, and sees what is still needed before use.
- A user edits a draft while the team and an active session remain on an earlier edition; the three states stay distinct.
- A user browses a shared source without including it in the environment; browsing causes no selection or activation.
- A source belongs to another owner; the UI offers only permitted editing or derivative actions.
- A memory correction appears in the state view even when it was recorded under another workstream, subject to authorized state disclosure.
- A preview produces the same qualified context as the consumer reader for the same request.
- Missing required data or incompatible native context prevents a false ready indication.
- A capability that is not implemented is shown as unsupported, not as an empty library or a configuration problem the user could solve.

## Implementation order and deferrals

First prove one complete path: select an owned environment, inspect its composition, read knowledge/current memory, preview the task context, and establish qualified readiness. Reuse the instruction-management services and controls where appropriate.

Add role-specific authoring and publication/adoption actions as the corresponding providers become available. Do not implement empty tabs that suggest unavailable backends exist.

Continue deferring the final Studio brand name, visual styling, a large administration console, advanced dashboards, and a universal editor. Revisit those only when needed by a demonstrated workflow. The minimal product interaction contract is no longer deferred with visual polish.

This record is design scope only. No Studio runtime or UI was changed by this addition.
