---
guide_id: coding-staged-workflow
language: en
status: active
use_when:
  - meaningful development work needing execution depth, review loops, and stop conditions
  - architecture changes, new features, cross-module or ontology changes, review-driven fixes
  - the user asks to design ("설계") before implementation
  - judging materiality of review findings and deciding when to stop or redesign
  - deciding where a stage's verification points and review gates belong in the work plan
---

# Coding Guidelines: Staged Workflow

This guide is a scoped extension of the global Coding Guidelines. Use it for meaningful development work to choose execution depth, review loops, and stop conditions.

It operates inside the existing global rules for requested scope, concept economy, LLM/tools/code boundary, verification discipline, and documentation hygiene.

For trivial edits, use the lightweight inspect-edit-verify path, defined here in full:
read the surface you are about to touch before changing it; if the request admits more
than one reading, state the reading you act on; make the surgical edit — every changed
line traceable to the request, adjacent code left alone; verify with the narrowest
reliable check that would fail if the edit were wrong; clean up only what your own
change introduced. The stages below are for work that outgrows that sentence.

When the user asks to "설계" or design, stay in design mode. Focus on high-level design and implementation-process design, then present the plan, tradeoffs, review gates, and implementation trigger. Move to implementation after the user asks to implement or approves the plan.

## When To Use

- Use this workflow for architecture changes, new features, cross-module behavior changes, ontology changes, review-driven fixes, or work that affects user-visible behavior, authority, lifecycle, validation, failure handling, or roadmap commitments.
- Use the lightweight path for small text edits, narrow config changes, or single-file adjustments whose completion criteria and verification are obvious.
- Increase workflow depth when new evidence shows broader risk than the initial request suggested.

## Stages

1. High-level design: define the goal, scope, architecture direction, affected concepts, tradeoffs, and completion criteria.
2. Implementation-process design: turn the design into an ordered work plan with dependencies, verification points, review gates, and redesign triggers.
3. Implementation: make the smallest viable functional changes that satisfy the approved design and process plan.

**Minimum** limits surface area, configuration, abstractions, optional scope, and implementation spread. It must not reduce required behavior, runtime authority, evidence quality, or verification depth — a change that ships less of those is not smaller, it is less finished, and "smallest viable" becomes the excuse rather than the discipline.

**Viable** means real behavior: the change runs against real inputs, real authority, and the intended runtime path. Mocks belong to tests, fixtures, and explicitly requested simulations — a mock-backed path supports verification but does not count as product completion, even when nothing labels it a mock; the full boundary lives in `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/mock-realization-boundary.md`.

Define the success criteria before multi-step work starts, then verify against those criteria rather than against what you ended up building. Criteria written afterwards describe the implementation, so they cannot fail it.

When simplifying a pipeline, moving processing downstream and dropping captured source fields are separate decisions: relocation is free simplification, but reducing captured information is riskier and needs explicit confirmation — "no current consumer" is not evidence of no future value.

## Making the change

Deciding what to build and building it are different disciplines. This one is about leaving a
change that reads as the change that was asked for.

**State the assumption before you act on it.** Most wasted implementation is not a wrong answer to
the question; it is a right answer to a question nobody asked. Where the request admits more than
one reading, say which one you took and keep going — surfacing it early costs a sentence, and
surfacing it after the work costs the work.

**Surgical means legible, not minimal.** Touch what the request requires, follow the file's
existing style rather than your preferred one, and leave adjacent code alone even when it is
worse than what you are adding. A diff carrying an unrequested refactor forces the reviewer to
separate the two by hand, and the improvement is the part that gets dropped when they run out of
patience.

**Clean up what this change introduced, and only that.** Dead code, unused imports, and debris
your own edit created belong in the same change. Debris you found belongs in a sentence: name it
so it is visible, and leave it where the person who owns it can decide.

**For a bug, reproduce before you fix, when that is practical.** A test written after the fix
proves the code does what it now does. A test written before proves you understood the failure —
and it is the only version that can tell you the fix was unnecessary, or that it addressed a
different bug than the one reported.

**Fix the cause at its authority, not the symptom where it shows.** Two signals say you are
patching downstream: compensating code keeps accumulating around bad inputs, and each fix reveals
another instance of the same defect. The first says go upstream to where the value is produced.
The second says the instances are a class — single-source the value and fix the class, because
patching them one at a time is a queue that refills.
**Supplying a missing shared dependency wakes every consumer, not just the one you are fixing.** When
a repair supplies a value many paths read and that was absent — a secret, a packaged file —
enumerate those consumers and say what each starts doing: metered calls, external writes,
user-visible output. Where that onset exceeds the feature under repair, hand the list to the owner
as a decision, not a line in the fix. Consumers that are all read-only and free need no gate.

**Measure a flip before you design its activation.** When a version bump, default change, or
severity re-mapping is coming, flip it, run the full suite, classify every failure (cascade,
pinned control, true detection, real regression), and restore — that count is the activation's
blast radius. Re-mapping a level obliges enumerating every reader of that field, since one level
commonly gates shipping, repair, retry, and display at once. A deferred defect is pinned as a
strict expected failure, never a silent pass.

## Review Loop

- At each stage, run review loops as appropriate: self review, subagent review when available, and structured multi-lens review when the repository or domain supports one (concrete tool: Environment Binding below).
- Iterate until material issues reach zero: review, identify material issues, fix them, and review again.
- "Material issues reach zero" is counted over the declared defect criterion's stop-relevant class; choosing and declaring that criterion is owned by `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/review-defect-criteria.md`.
- Use the severity contract for materiality — the canonical definition is the ladder below; external review tools map their levels onto it: blocker, high, and medium are material; low and info are non-material.
- Treat blocker as primary happy-path or core-contract failure.
- Treat high as supported user, environment, data, or execution path failure.
- Treat medium as meaningful weakening of trust, auditability, reproducibility, completeness, or decision quality.
- Treat low and info as non-blocking unless requested or promoted by new evidence.
- When a document declares sections co-authoritative for a rule (fixture blocks, conformance appendices), treat every occurrence as one replicated value: propagate edits to all declared locations in the same pass and check propagation completeness explicitly in review.

## Verification

Verification is a subject of its own — depth, per-domain menus, deriving the case space, and what
a green is worth. It lives in `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/verification-discipline.md`.
Run it at each stage's verification points, and use its Verification Menus to pick the mix.

## Stop Conditions

- If the issue boundary expands compared with the previous review, stop and ask the user to choose redesign/rework or continuing the current iteration.
- Consider the boundary expanded when review reveals a broader affected purpose, failure condition, impact area, concept boundary, architecture boundary, or severity class.
- When review rounds keep producing material findings, classify each before fixing: a regression the previous round's own fix introduced, or a fresh instance of one pre-existing root cause. Regressions say tighten the increment and continue; recurring instances with zero regressions say instance-patching is a refilling queue — trigger the redesign-versus-continue stop above.
- Before calling the work done, report the current stage, review results, remaining material issues, verification results, and any stop reason.

## Environment Binding (edit per environment)

The only section of this guide that names concrete tools. Dated; expires ~8 weeks after the date or when the bound tool changes.

Binding (2026-07):

| Slot | Binding | Notes |
|---|---|---|
| Structured multi-lens review | agent-launch review methods: isolated panel + Codex deep exec (`codex exec` at ultra effort) + Claude ultracode workflow | consumes/emits the severity contract defined in Review Loop; personal tools register in the user-owned `review-methods.local.toml` |
| Subagent review | host CLI's native review mechanism | e.g. Claude Code `/code-review` or Agent-tool reviewers |
