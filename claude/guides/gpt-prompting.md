---
guide_id: gpt-prompting
language: en
status: active
use_when:
  - composing a prompt, packet, or tool description for a gpt-family model
  - dispatching cross-family review to the gpt side from a Claude main
  - prompting gpt subagents, or prompting yourself when the main is Codex
  - porting a prompt written for an older gpt model
  - deciding a reasoning-effort level for gpt work
core_rules:
  - apply the shared recipe and only the section for the actual target model — GPT-5.6 and GPT-6 Astra have different prompting needs
  - describe the destination, not the route — state outcome, success bar, real constraints, and available evidence
  - keep only what changes behavior; cut repeated statements, style rules, and examples that do not
  - replace blanket ALWAYS/NEVER with decision rules naming the condition each choice applies under
  - fix the prompt before raising effort — weak output usually means a missing success criterion, dependency rule, tool-routing rule, or verification loop
  - prompting habits carried from older gpt models cost tokens and can cost accuracy
derived_at: 2026-09-07
source_pins:
  - doc: prompt-guidance-gpt-5p6
    sha256: 46181efec9fd1160ef537b0379282a14c1ba32380f2f8149a805128253c1115a
    pinned_at: 2026-09-07
  - doc: model-guidance-gpt-6-astra
    sha256: 2a59b26078e001a4e4e3da10693e80ad5ee1c02cbe472afa6b682308f27b8b22
    pinned_at: 2026-09-07
targets:
  - gpt-6-astra
  - gpt-5.6-sol
  - gpt-5.6-terra
  - gpt-5.6-luna
verification_focus:
  - prompt changes are validated by re-running the same evals, not by inspection
  - removals are tested one group at a time so the cause of a delta is known
  - effort changes use settings the target model supports and are compared against the baseline
  - model-specific advice is checked against its own pinned source, including autonomy, writing style, delegation, and verification
---

# GPT Prompting Guide

This guide is a scoped extension of the global Coding Guidelines. Use it when
composing a prompt for a gpt-tier model — a review packet dispatched
cross-family, a subagent brief, or the main's own instructions when the main is
Codex.

Use the shared recipe below together with the section for the actual target model.
The model being prompted decides the section, including when it is a subagent on a
different model from the main. These sections tune prompts within the existing
permission policy; they do not change tool permissions or approval requirements.

| Target | Apply | Pinned source |
| --- | --- | --- |
| `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | GPT-5.6 | `prompt-guidance-gpt-5p6` |
| `gpt-6-astra` | GPT-6 Astra | `model-guidance-gpt-6-astra` |

## GPT-5.6

- **Simplify first.** State the outcome, constraints, evidence, and completion bar,
  then leave the model room to choose its path. Start from a working prompt; remove
  one group of repeated instructions, examples, or irrelevant tools at a time and
  re-run the same evals. Keep a process instruction when it changes behavior.
- **Calibrate brevity.** GPT-5.6 tends to be more concise than GPT-5.5. Re-test broad
  brevity instructions before carrying them over; they can make answers too thin.
  Keep them when they produce the required result. Where the API exposes
  `text.verbosity`, use it for the default detail level and the prompt for the
  task's length, structure, and required content. Shorten repetition before evidence,
  decisions, caveats, or next actions.
- **Define collaboration separately from tone.** Briefly name when to ask, assume,
  take initiative, and explain uncertainty. Distinguish inspection or planning
  requests from requests to implement. Name safe local actions and approval
  boundaries once so ordinary in-scope work does not pause unnecessarily.
- **Tune effort after the prompt.** Preserve the current effective effort as the
  baseline, then compare it and one supported level lower on representative tasks.
  Use `low` when latency matters and quality holds; `medium` is a balanced starting
  point. Use `high`/`xhigh` when evals show a gain, and reserve `max` for the hardest
  quality-first work. Verify availability against the active model and host.

## GPT-6 Astra

- **Initiative and follow-through.** Astra is more likely to ask a question when
  input could materially change the result. For action requests, prompt it to infer
  routine details from context and complete authorized work, including validation,
  before answering. A plan or an offer to continue does not complete an action
  request. Ask when missing information changes the outcome; continue independent
  authorized work while waiting. If approval is required for a later step, prepare
  the concrete, reviewable result first. Keep existing permission boundaries and
  avoid adding approval steps based only on hypothetical risk.
- **Instruction and skill sensitivity.** Audit the loaded skills and instruction
  files for unclear or conflicting guidance. Make explicit user instructions take
  precedence over skill workflow preferences within higher-priority instructions
  and permission constraints. When a skill causes a pause, an approval request, or
  unfinished work, identify and link the exact skill file, quote the relevant rule,
  and explain whether it is explicit or an interpretation. Do not turn an optional
  guideline into a new requirement.
- **Writing style.** Astra tends toward detailed responses, lists, tables, and
  recurring phrases. Specify the desired length and structure for the audience.
  For plain prose, request concise paragraphs, familiar words, active verbs, and
  the main point first. Use lists when comparison or sequence benefits; retain
  technical detail needed to assess the result. Name unwanted stock phrases or
  formulaic contrasts when they recur rather than assuming GPT-5.6's brevity bias.
- **Subagent delegation.** Astra may delegate less often than a workflow needs.
  State when independent work should be delegated, the intended amount of
  parallelism, each subagent's scope, and when to keep work local. Use the existing
  spawn gates, available seats, and budget; a generic instruction to be proactive
  does not specify delegation. Require readable inter-agent messages with correct
  spacing.
- **Testing and verification.** Astra can over-test small coding changes. Name the
  relevant checks and completion bar. Avoid tests that only mirror a reversible,
  low-impact implementation. Complete required checks; broaden or repeat them only
  when a new edit, a failure, or an unresolved concern warrants it. This calibration
  preserves required repository gates and validation of the actual changed behavior.
- **Reasoning effort.** Astra does not support `none`. When migrating a prompt from
  `none` or `minimal`, begin with `low` and compare results; otherwise preserve the
  current effective effort. Check the active model and host for supported settings
  instead of reusing a family-wide effort ladder. Fix a missing success criterion,
  dependency rule, or verification loop before increasing effort.

## Shared prompt recipe

Compose in this order; omit any block that would not change the artifact.

- `Role` and `Personality` — who is acting and in what register. Omit
  personality when it does not change the output.
- `Goal` and `Success criteria` — the outcome, and the bar that decides done.
  This is the block most worth its tokens; write it first. If you cannot state
  the bar, the prompt is not ready.
- `Constraints` — safety, business, and scope limits that must hold. Real
  constraints only; preferences belong in output shape or nowhere.
- `Tools` — only task-relevant ones. Each description states what it does, when
  to use it, its important return fields, and its error behavior.
- `Output` — the artifact shape. `Stop rules` — when to stop looping and answer.

## When to add blocks

- Coding and debugging: name the validation to run after changes — targeted
  tests for the changed behavior, type/lint checks, build, a minimal smoke test.
  Require prerequisite lookups before edits.
- Review: carry the general rules and be explicit about the evidence bar and the verdict shape; a
  reviewer with no stated bar defaults to plausible-sounding findings.
- Research and grounded work: cite only retrieved sources, attach citations to
  the claims they support, and label inference separately from supported fact.
  Say to narrow the answer or report missing evidence rather than guess.
- Write-capable work: name the safe actions explicitly (read files, edit code,
  run tests) and require confirmation for external writes, destructive actions,
  or scope expansion.
- Implementation plans: requirements, named resources, state transitions,
  validation checks, failure behavior, privacy/security, open questions.

## How to choose prompt shape

- One bounded question with a self-contained packet → a single hermetic run.
  This is the default for review.
- Work that divides into independent workstreams → fan-out. Parallelize
  independent reads; keep dependent steps sequential.
- Choose reasoning effort using the target model's section above and the settings
  the active model and host actually support.
- Prefer a self-contained packet over resuming a long history: it is cheaper to
  reason about and cheaper to cache.

## Programmatic tool calling

A bounded stage where code processes several tool results and returns a much smaller
structured result. The qualifier is **reduction**, not parallelism: multiple, parallel,
or dependent calls alone do not justify it.

- Use it for filtering, joining, sorting, ranking, deduplication and aggregation;
  batching across many similar records; repeated deterministic validation; and large
  structured results reducible to a compact schema.
- Prefer direct calls when one call suffices, when intermediate outputs are already
  small, when each result may change the next decision, when an action needs approval,
  when the answer must preserve citations or native artifacts, or when semantic
  judgment sits between calls.
- A generic "use programmatic tool calling efficiently" does nothing. State the bounded
  stage, the eligible tools, the output schema, the retry limit, the stop condition, and
  the handoff back to direct judgment. If both routes are needed, define one handoff and
  say not to switch routes or repeat completed work.
- **Test both outputs.** The program's result and the final assistant message are
  separate; a program can return the right records while the message drops a required
  field, citation, or caveat.
- Compare the two routes on the same tasks, and count lower token/latency/cost as an
  improvement only when the response still passes the existing evals.

## Working rules

- One clear task per run, with an explicit output contract.
- **Read the assembled prompt for contradictions.** This tier follows a prompt contract
  closely, so two rules that disagree destabilize it more than a missing rule does —
  the opposite of the intuition that more instruction is safer.
- State each authority rule once. Repeating "ask first", "do not mutate", or "wait for
  approval" produces approval requests for safe, expected actions.
- Name the current layer of work — research, design, implementation, review, external
  coordination — on long-running tasks, so the model does not move between layers
  silently.
- Persisted reasoning is not a free optimization. It helps while the objective and
  priorities hold; once they move, stale reasoning adds tokens and anchors the model to
  a superseded approach. Compact at milestones, not every turn, and treat compacted
  items as opaque.
- Preserve explicit user values. Where the right value is implicit, give decision
  criteria and let the model reason from context or schema rather than installing
  universal defaults or keyword maps.
- Keep reusable prefixes stable and avoid churn in large system prompts. Add
  explicit cache breakpoints only where they measurably improve cache behavior —
  inspect the active model's cache usage and cost before adding one.
- After each tool result, ask whether the core request can now be answered with
  useful evidence. If yes, answer.
- Render any visual artifact before finalizing; inspect layout, clipping,
  spacing, and missing content.

## Prompt assembly checklist

1. Write the success criteria first.
2. Add role, goal, real constraints, and the output shape.
3. Add only the tools the task needs, each with when-to-use and error behavior.
4. Add stop rules and the verification the task must pass.
5. Apply the matching model section. Re-read for contradictions and rules inherited
   from a different model; validate targeted changes with the same representative cases.

## Evidence base

The vendor's GPT-5.6 coding-agent sample reported roughly +10–15% eval score,
41–66% fewer total tokens, and 33–67% lower cost with leaner system prompts
(`prompt-guidance-gpt-5p6`, pinned 2026-09-07). These are directional results for
that sample, not Astra measurements or promised gains on another workload.

## Sources

The GPT-5.6 section is derived from `prompt-guidance-gpt-5p6`; the GPT-6 Astra
section from `model-guidance-gpt-6-astra`. The shared recipe retains task, evidence,
tool, and validation practices from the GPT-5.6 guidance and the corpus; model
behavior claims belong only to their matching section. `source_pins` records the
exact bytes used for this derivation so later vendor edits can be detected.

When a `targets` model changes, re-derive its section from the matching current
document, check the shared rules for contradictions, and re-run representative
evals rather than extending another model's behavior claims to it.
`launch/check-prompting-targets.sh` fails when the launch config binds a model
this guide does not list; that check is about **naming**, and a model added to
`targets:` satisfies it forever. Whether the guidance was actually re-derived is
not decidable and is gated nowhere.
