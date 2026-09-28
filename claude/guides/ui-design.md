---
guide_id: ui-design
language: en
status: active
description: For designing, reviewing, or changing task flows, information layout, visual hierarchy, or interaction in operational user interfaces; keep bounded corrections proportionate.
use_when:
  - designing or reviewing a work application, operations tool, or interactive work surface
  - changing information arrangement, visual hierarchy, design tokens, or interaction states
  - preserving scope, evidence, authority, and continuity through a user interface
---

# Operational interface design and delivery

Use for interfaces where people inspect evidence, compose work, make decisions
or act on records. Match the deliverable to the user's requested stage and scope.
A clear text correction needs that correction and a proportionate check.

1. **Establish what the sources mean now.** Separate implemented behavior,
   accepted requirements, proposed design choices and illustrative states.
   Reconcile amendments and decisions before reusing an older screen. A newer
   date alone does not establish authority. Keep material contradictions and
   unknowns visible instead of silently choosing a convenient interpretation.

2. **Preserve requested coverage; bound the work at the right level.** Identify
   the operator, outcome and evidence that would complete this deliverable.
   Distinguish people consuming work context from those authoring or managing
   it; do not invent their visit frequency or force a common starting screen.
   For a complete design request, cover the required operations even when their
   backend is not built; specify their subjects, inputs, effects, dependencies
   and recovery rather than claiming implementation. For a bounded change,
   complete the requested path before expanding neighboring features. Include
   adjacent repairs when that path depends on them or this change causes a
   regression, and state why. An unavailable implementation does not erase a
   requested design contract.

3. **Organize around a meaningful next decision.** Show the working scope,
   evidence to compare, current state, available action and resulting next step
   together. Internal modules or protocol phases are not automatically menus
   or buttons. Combine preparation steps behind one authorized intent when no
   user choice is needed, while keeping distinct outcomes understandable. Use
   the team's visual language to assign emphasis according to the task, and
   make typography, spacing, color and boundaries express meaningful
   relationships. Test whether actual task content is prominent at the target
   size; decorative summaries must earn their space. When layout uncertainty
   matters, compare arrangements at the lowest useful fidelity, explaining the
   task tradeoff and what evidence would change the choice.

   When a new visual direction or a material arrangement decision remains
   unresolved, use
   `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/ui-design/visual-direction.md`.
   An established direction or a bounded correction does not require new
   reference research or multiple designs.

4. **Keep qualifications with the thing they qualify.** Preserve applicable
   conditions, exceptions, units, source/version, time meaning and affected
   scope through summaries, edits, comparisons and exports. Keep independent
   dimensions separate. Missing evidence is not an empty result or a zero, and
   an index or relationship view is not proof of its underlying body or meaning.
   Expand technical detail when useful without hiding a consequential limit.

5. **Make each action's authority and effect precise.** Name the exact target,
   base and changed content when reviewing a change. Recheck a changed base or
   permission instead of carrying approval onto different input. Distinguish
   selection, saved draft, approval, execution and recipient use as applicable;
   one positive state does not prove the next. Preserve request identity when
   an outcome is uncertain and reconcile its actual result before retrying.
   UI controls reflect the existing authoritative policy; they do not create it.
   If policy is unsettled, label proposed choices and the responsible decision
   owner rather than implying permission or omitting the required design.

6. **Carry the same work across views and people.** Preserve the draft, target,
   review/request identity and return context when moving between surfaces.
   Equivalent outcomes need suitable representations, not identical layouts or
   duplicated business rules. Provide keyboard and structured alternatives for
   necessary spatial interactions. Verify evidence for the actual recipient;
   another worker's receipt does not establish their access or delivery.

7. **Verify this deliverable, then finish it.** Walk a design's concrete scenario
   and relevant exceptions against its sources; inspect its proposed composition.
   For working changes, exercise the changed runtime path, relevant failures,
   keyboard and recovery. When a visual change is material, inspect the affected
   composition with representative content and relevant states at the target
   size, distinguishing token changes from changes to information arrangement.
   Check that visual, reading and focus order remain coherent across layouts.
   Report visual preference separately from observed task performance. Keep
   simulation, observed runtime and user evidence distinct. Once the required
   checks are complete, leave the result, material decisions, source bindings
   and remaining work in ordinary team artifacts. Keep private facts within
   their permitted boundary. Choose dependencies only when a requirement
   demands a decision, using the supported environment first.
