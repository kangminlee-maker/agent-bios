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
  - apply the shared recipe plus the section for the target model's family — GPT-5.6, GPT-6 and GPT-6.2 have different prompting needs; the GPT-6 advice is observed on GPT-6 Astra, the GPT-6.2 advice on GPT-6.2 Astra and Sol, and each is a starting point for the rest of its family
  - describe the destination, not the route — state outcome, success bar, real constraints, and available evidence
  - keep only what changes behavior; cut repeated statements, style rules, and examples that do not
  - replace blanket ALWAYS/NEVER with decision rules naming the condition each choice applies under
  - fix the prompt before raising effort — first check for a missing success criterion, dependency rule, tool-routing rule, or verification loop
  - prompting habits carried from older gpt models cost tokens and can cost accuracy
derived_at: 2026-11-24
source_pins:
  - doc: model-guidance-gpt-6p2
    sha256: d51a271ccee79b94428bc1d1a1591f9f98c424f2d9d084a37ccc4358dada40c0
    pinned_at: 2026-11-24
  - doc: prompt-guidance-gpt-5p6
    sha256: fbf38652350fee866f46d888e6a0e83537cf5a5a148818271332260cd3e439f7
    pinned_at: 2026-11-24
  - doc: model-guidance-gpt-5p6
    sha256: bcbc002991e3ff6491ba5c4d38d8f5c497fa785c0b11ea27d92c9d34676ab460
    pinned_at: 2026-11-24
  - doc: upgrading-to-gpt-5p6-sol
    sha256: 59484b7370078d3482d972dfeb7f79fe862e410571881f9983e1bca7dea89ebe
    pinned_at: 2026-11-24
  - doc: model-gpt-6p2-astra
    sha256: b12e61471fed60c843626fdee3dea09c86babae84ea779a5f5eb9193cb62720f
    pinned_at: 2026-11-24
  - doc: model-gpt-6p2-sol
    sha256: 551d09dbb7e6f64a1af314446b8d5a72ab9bf66daa4407060007d11ce54acf43
    pinned_at: 2026-11-24
  - doc: model-guidance-gpt-6-astra
    sha256: b12f5dde985df0ac1e03ea5eaa40dfcdb0e4620a1bf1ae4d78cdd81f8c7f4c3a
    pinned_at: 2026-11-24
  - doc: model-gpt-6-astra
    sha256: 31d55873985379d2b4e129fd41f974e8511b9de1a5105dc4e0692b53b504a8cb
    pinned_at: 2026-11-24
  - doc: model-gpt-6p1-sol
    sha256: 02dff9ef937bbc97fb24ba7c936269a549563cfb8a49b91a6ba1c1575d2b77c0
    pinned_at: 2026-11-24
  - doc: model-gpt-6-sol
    sha256: 8e3cd3378f0686313dd489ed37347d481d24d4b791e7bd28b1538c4df7762fc4
    pinned_at: 2026-11-24
  - doc: model-gpt-6-luna
    sha256: dacc9870e67c0d68e4272f8394d4296ffe7cf70f18d3f4675ee6bd4c666966b7
    pinned_at: 2026-11-24
  - doc: reasoning
    sha256: f0c480788b035a289f34aef88a58cb48abead8abd82194ae8f68b110d5971bfa
    pinned_at: 2026-11-24
  - doc: codex-models
    sha256: 2ca411d02af5e803e25d60eedcac752c7a6153c2c6dffafdbd854aff61f4277c
    pinned_at: 2026-11-24
  - doc: prompt-caching
    sha256: 41fd5ad72dc74045ffb0fbe33e8213a879cc018a473b1e022b7be8fa04057625
    pinned_at: 2026-11-24
  - doc: responses-multi-agent
    sha256: 1bb6554687059202a4c92486d39fb2ea42730fb20a85880c33258186872012f8
    pinned_at: 2026-11-24
  - doc: structured-outputs
    sha256: fbabb4598029cba47f3b19e173371da9950e6c9050b5380460b0256b8a08d9fe
    pinned_at: 2026-11-24
  - doc: tools-programmatic-tool-calling
    sha256: cd5027c76f0d5c9473c0333b69dc89af27bf45c356760e2b1628172ef54923a9
    pinned_at: 2026-11-24
targets:
  - gpt-6.2-astra
  - gpt-6.2-sol
  - gpt-6-astra
  - gpt-6.1-sol
  - gpt-6-sol
  - gpt-6-luna
  - gpt-5.6-sol
  - gpt-5.6-terra
  - gpt-5.6-luna
verification_focus:
  - prompt changes are validated by re-running the same evals, not by inspection
  - removals are tested one group at a time so the cause of a delta is known
  - effort changes use values the target model accepts and are compared against the baseline
  - family-level advice is checked against the family document, per-model facts against each model page, and Codex-only values against the Codex documents
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
| `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | GPT-5.6 | `prompt-guidance-gpt-5p6`, `model-guidance-gpt-5p6` |
| `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna` | GPT-6 family | `model-guidance-gpt-6-astra` plus the model's own page |
| `gpt-6.2-astra`, `gpt-6.2-sol` | GPT-6.2 | `model-guidance-gpt-6p2` plus the model's own page |

## Per-model facts

Accepted `reasoning.effort` values and tool-calling routes, from each model's page or
family guide. An omitted effort takes the documented default.

| Model | `reasoning.effort` | Tool calling | Vendor positioning |
| --- | --- | --- | --- |
| `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `none`, `low`, `medium` (default), `high`, `xhigh`, `max` | Responses API for reasoning with tools; Chat Completions function tools only with effective `none` — an omitted effort is `medium` and breaks that combination | Sol flagship capability; Terra intelligence/cost balance; Luna efficient, high-volume work |
| `gpt-6.2-astra`, `gpt-6.2-sol` | the API rejects `none` and documents no list or default; the vendor starts a new integration at `medium` and moves `none` or `minimal` to `low`; the Codex catalogue offers `low` through `max` and `ultra` | Responses API; Chat Completions only without tools; no Flex processing | Astra the most demanding tasks; Sol complex work at lower cost, Codex's everyday model |
| `gpt-6-astra` | `low`, `medium`, `high`, `xhigh`, `max`; no `none`; no documented default | Responses API; Chat Completions only without tools | the most demanding reasoning, coding, computer use, and professional work |
| `gpt-6.1-sol` | `low`, `medium` (default), `high`, `xhigh`, `max`; no `none` or `minimal` | Responses API; Chat Completions only without tools | near-Astra performance at lower cost |
| `gpt-6-sol` | `none`, `low`, `medium` (default), `high`, `xhigh`, `max` | Responses API for reasoning with tools; Chat Completions function calling only with `none` | complex coding and agentic workflows; its page points to 6.1 Sol as the newer Sol |
| `gpt-6-luna` | `none`, `low`, `medium` (default), `high`, `xhigh`, `max` | as `gpt-6-sol` | focused, high-volume tasks |

## GPT-5.6

- **Simplify first.** State the outcome, constraints, evidence, and completion bar,
  then leave the model room to choose its path. Start from a working prompt; remove
  one group of repeated instructions, examples, or irrelevant tools at a time and
  re-run the same evals. Keep a process instruction when it changes behavior.
- **Calibrate brevity.** GPT-5.6 tends to be more concise than GPT-5.5. Re-test broad
  brevity instructions before carrying them over; they can make answers too thin, and
  stay only when they produce the required result. Where the API exposes
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
  point; use `high`/`xhigh` when evals show a gain and reserve `max` for the hardest
  quality-first work. The table above lists the accepted values; verify the host.

## GPT-6 family

OpenAI's GPT-6 prompting document ("Using GPT-6") predates GPT-6.2, which has its own
(the next section). Its best practices address behavior observed with GPT-6 Astra and
are offered as a starting point across the family, to be evaluated with the chosen
model and workload. The five behavior bullets
below are therefore Astra observations; for `gpt-6.1-sol`, `gpt-6-sol`, and
`gpt-6-luna` the vendor states no model-specific prompting behavior, and what differs
per model is the API facts in the table above, taken from each model page. Re-derive
this section when a GPT-6 model other than Astra gets a prompting document of its own.

- **Initiative and follow-through.** Astra is more likely to ask when input could
  materially change the result, and asks non-blocking questions while working. For
  action requests, prompt it to infer routine details from context and complete
  authorized work, including validation, before answering; a plan or an offer to
  continue does not complete an action request. Ask when missing information changes
  the outcome and continue independent authorized work while waiting. If a later step
  needs approval, prepare the concrete, reviewable result first. Keep existing
  permission boundaries; add no approval steps on hypothetical risk alone. Astra stays
  coherent over long tasks better than GPT-5.6 Sol and earlier models.
- **Instruction and skill sensitivity.** Astra follows longer instructions better and
  is more sensitive to context: unclear or conflicting guidance in a skill file can
  make it pause and block work early. Audit the loaded skills and instruction files,
  and make explicit user instructions outrank skill workflow preferences within
  higher-priority instructions and permission constraints. When a skill causes a
  pause, an approval request, or unfinished work, require it to name and link the
  exact skill file, quote the rule, and say whether that rule is explicit or inferred;
  an inferred reading of an optional guideline is not a requirement.
- **Writing style.** Astra tends toward detailed responses, lists, tables, and
  recurring phrases across sessions. Specify length and structure for the audience.
  For plain prose, request concise paragraphs, familiar words, active verbs, and the
  main point first, with lists only for parallel, sequential, or comparable content.
  Retain the technical detail needed to assess the result; name unwanted stock
  phrases and contrastive framing when they recur.
- **Subagent delegation.** Astra may delegate less often than a workflow needs and
  responds well to prompting for how and when to delegate. State when independent
  work is delegated, the intended parallelism, each subagent's scope, and when to keep
  work local, within the existing spawn gates, seats, and budget; "be proactive" does
  not specify delegation. Require legible inter-agent messages with proper spacing.
- **Testing and verification.** Astra can over-test small coding changes. Name the
  relevant checks and the completion bar; avoid tests that only mirror a reversible,
  low-impact implementation. Complete required checks, and broaden or repeat them only
  when a new edit, a failure, or an unresolved concern warrants it. Required
  repository gates and validation of the changed behavior stay in force.

### Reasoning effort

- Preserve the current effective effort where the model accepts it: a prompt that ran
  at `none` moves to `low` on Astra or 6.1 Sol, and one that ran at `minimal` starts at
  `low` and is compared on representative tasks. When effort is not `none`, drop
  `temperature`, `top_p`, and the log-probability options (`top_logprobs`; `logprobs`
  in Chat Completions; `message.output_text.logprobs` in a Responses `include`). To
  change effort between responses, add a `configuration_update` item (GPT-6 and later;
  standard single-agent requests; it updates the effort and the response format,
  `json_schema` or `text`) and leave the request-level effort unchanged so the cached
  prefix survives; the response keeps reporting the request-level effort. Such a
  history can use automatic compaction through `context_management`, but automatic
  truncation and `/responses/compact` reject it; to compact it explicitly, add a
  `compaction_trigger` item in a `/responses` request, then a fresh
  `configuration_update` restating every changed setting, format included, before the
  next user message. Fix a missing success criterion, dependency rule, or verification
  loop before raising effort (the GPT-5.6 guidance): effort is a tuning knob, not the
  primary way to recover quality.
- **Under Codex.** `ultra` is a Codex effort, not an API value — the API's effort list
  ends at `max`. It is a different mode, not the next rung: the client catalog
  describes it as maximum reasoning with automatic task delegation, it runs the task
  with subagents, and it suits work that divides into meaningful parts. The catalog
  offers it for every listed Astra, Sol and Terra model, GPT-6.2 included; Luna goes up
  to Max and refuses Ultra, and most tasks need neither. Take the supported levels for
  a seat from the host's catalog, not from the API ladder: the two disagree, and for
  GPT-6.2 only the catalog lists them. A run that omits effort inherits the client's
  default, which can differ from the API default (the client catalog sets
  `gpt-6.2-astra`, `gpt-6.2-sol`, `gpt-6-astra` and `gpt-6.1-sol` to `low`; the API
  default for 6.1 Sol is `medium`) — pin it in the launch config. The client's model
  catalog also places per-model instructions under your prompt: GPT-6.2 Astra and Sol
  carry the vendor's GPT-6.2 coding sample, which skips new tests unless they are
  requested, required by the repository, or needed for a regression the existing tests
  would miss, so a 6.2 run that must add tests needs that requirement named; GPT-6
  Astra, 6.1 Sol and 6 Sol carry the GPT-6 testing calibration above; and GPT-6 Luna is
  told not to add or run tests unless asked, so a Luna run that must verify needs its
  checks named in the prompt (Codex client catalog, codex-cli 0.171.0, read 2026-11-24;
  not a published document).

## GPT-6.2

OpenAI's GPT-6.2 document ("Using GPT-6.2") offers its prompts as a starting point
across the GPT-6.2 family; its examples address behavior seen with GPT-6.2 Astra and
Sol. It says nothing about delegation or skill sensitivity: for those, the GPT-6
bullets above are an Astra 6 starting point to evaluate, not a 6.2 observation.

- **Writing style.** More concise and direct by default than earlier models: revisit
  "be concise" carried from older prompts instead of adding more brevity pressure.
  Ask for the terminology the user and the sources use, the key points first, and
  enough context to follow the reasoning; for material sent to an outside audience,
  ask it to supply the background that audience lacks, and when editing, to keep the
  author's content and wording.
- **Self-contained final answers.** Over long tasks the model can carry shorthand from
  its reasoning, tool calls or subagent briefs into the final answer. Ask for a final
  answer that a reader who skipped the progress updates can follow, written anew for
  that reader.
- **Task completion.** When intent is unclear the model may propose a next step and
  wait. For work that can proceed unsupervised, state the outcome to complete and which
  decisions need the user; let it make reasonable, reversible assumptions within scope,
  state them, and keep working, stopping only for a significant scope change, a concrete
  block, a decision the user must make, or an irreversible or destructive action. Ask
  it to check that every part of the request is done before it finishes; higher effort
  can help it persist through those final checks. These tune behavior within the
  existing approval rules, which stay as they are.
- **Coding style.** It writes more efficient code by default. Describe the codebase's
  conventions and the behavior callers rely on: when to reuse existing logic, how
  narrowly to scope a change, and when a test is wanted. The vendor's coding sample
  asks for readable code over the shortest code and warns against indirection that adds
  no value; its test rule is above, under Codex. Required repository gates stay in force.
- **Visual work.** For a particular look, name the imagery and typography; give it a
  reference to render against and refine.

What changes in the API from GPT-6.2 on:

- **An edited prefix drops reasoning.** The Responses API drops reasoning items after an
  edit to earlier history (rewriting an earlier developer message or tool result), some
  model changes (downgrades among them), or a different end user or organization
  (`safety_identifier`); answers can degrade and the model repeats work. Deleting whole
  items or appending new ones is not such an edit. Change settings between responses
  with `configuration_update` rather than by rewriting the prefix, and read
  `input_transformations` in the response to see a removal.
- **Top-level `instructions` move after `input`.** They sit past every cache breakpoint,
  bill at the uncached rate even on a cache hit, and do not carry over with
  `previous_response_id`. Put reusable instructions in the first `developer` message of
  `input`; keep top-level `instructions` for guidance meant for the current request only.
- **Caching parameters.** `prompt_cache_options.ttl` replaces `prompt_cache_retention`:
  `"30m"` by default, `"12h"` in the Responses API. Cache writes bill at 1.25× the
  uncached input rate for 30 minutes and 2.5× for 12 hours, and reads on 6.2 Astra and
  Sol at 0.05×.
- **Processing.** No Flex processing; background mode offers discounted two- and
  eight-hour completion windows for long requests.
- **Multi-agent beta.** Available on 6.2 Astra and Sol (and 6.1 Sol and GPT-5.6). With it
  on, `/responses/compact` is unavailable, automatic compaction is on, `reasoning.summary`
  and `max_tool_calls` are not supported, and three subagents run at once by default.
- **Under Codex.** The client's default context is 272,000 tokens for 6.2 Astra and
  500,000 for 6.2 Sol (client catalog); the Codex documents list both models for the
  Codex app and CLI and not for the IDE extension.

## Shared prompt recipe

Arrange the finished prompt in this order; draft the success criteria first (the
checklist below); omit any block that would not change the artifact.

- `Role` and `Personality` — who is acting and in what register. Omit
  personality when it does not change the output.
- `Goal` and `Success criteria` — the outcome, and the bar that decides done.
  Draft them before the rest; if you cannot state the bar, the prompt is not ready.
- `Constraints` — safety, business, and scope limits that must hold. Real
  constraints only; preferences belong in output shape or nowhere.
- `Tools` — only task-relevant ones. Each description states what it does, when
  to use it, its important return fields, and its error behavior.
- `Output` — the artifact shape. Under a forced schema the model writes fields in the
  schema's key order and every field is required; this repository therefore puts
  evidence fields before the verdict they justify (a design choice to confirm on your
  evals) and gives an explicit way to report an incompatible input instead of forcing
  a value. `Stop rules` — when to stop looping and answer.

## When to add blocks

- Coding and debugging: name the validation to run after changes — targeted
  tests for the changed behavior, type/lint checks, build, a minimal smoke test, a
  render of any visual artifact. Require prerequisite lookups before edits. If
  validation cannot run, require the reason and the next best check.
- Review: carry the general rules and state the evidence bar and the verdict shape
  explicitly.
- Research and grounded work: cite only retrieved sources, attach citations to
  the claims they support, and label inference separately from supported fact.
  Say to narrow the answer or report missing evidence rather than guess; absence
  of evidence is not a factual no.
- Write-capable work: name the safe actions explicitly (read files, edit code, run
  tests). Require confirmation only for external writes, destructive actions, or scope
  expansion the session has not already authorized, and ask for it as the final step,
  after the work is prepared; earlier or strongly implied authorization stays in force.
- Implementation plans: requirements, named resources, state transitions,
  validation checks, failure behavior, privacy/security, open questions.

## How to choose prompt shape

- A bounded review packet runs as one self-contained run with no inherited
  instructions — the hermetic profile — by default (repository practice).
- One run when each step depends on the previous one, the task finishes in one short
  run, or agents would contend over the same mutable state. Fan out when the work
  splits into independent bounded tasks, separate context improves focus, or parallel
  exploration cuts wall-clock time; subagents add token usage, so the split has to earn
  it. Within a run, parallelize independent reads and keep dependent steps sequential.
- Choose reasoning effort from the table and the target model's section. In an API
  dispatch, reasoning and visible output share the output limit and reasoning can
  exhaust it before any visible output appears: budget output capacity for reasoning
  plus the deliverable, and count such exhausted runs when comparing effort levels.
- Put stable instructions and shared reference material first, changing per-request
  content last, and keep that prefix free of churn. Ordering alone caches nothing: the
  prefix must reach the minimum cacheable length and end at a breakpoint, and implicit
  caching writes through a changing suffix, so on GPT-5.6 and later mark the stable
  boundary with an explicit breakpoint where the implicit one misses it; check the
  reported `cached_tokens` and the cost before and after, and keep the breakpoint only
  where it improves them. On GPT-6.2 the stable instructions belong in the first
  `developer` message, not top-level `instructions` (the GPT-6.2 section). Continuing a
  multi-turn task, keep earlier messages and tool results unedited so later turns
  reuse the full prefix. Starting a new bounded task, send a
  self-contained packet rather than resuming a long history that holds context the task
  does not need.

## Programmatic tool calling

A bounded stage where code processes several tool results and returns a much smaller
structured result. The qualifier is **reduction**, not parallelism: multiple or parallel
calls alone do not justify it, and dependent calls qualify only when code can derive the
later arguments and the limits and failure behavior are explicit.

- Use it for filtering, joining, sorting, ranking, deduplication and aggregation,
  batching across many similar records, repeated deterministic validation, and large
  structured results reducible to a compact schema. Prefer direct calls when one call
  suffices, intermediate outputs are already small, each result may change the next
  decision, an action needs approval, the answer must preserve citations or native
  artifacts, or semantic judgment sits between calls.
- A generic "use programmatic tool calling efficiently" does nothing. State the bounded
  stage, the eligible tools, the output schema, the retry limit, the stop condition, and
  the handoff back to direct judgment; if both routes are needed, define one handoff
  and say not to switch routes or repeat completed work. A running program cannot
  invoke tool search, so require any deferred tool the stage needs to be discovered
  and loaded before the program starts.
- **Test both outputs.** The program's result and the final assistant message are
  separate; a program can return the right records while the message drops a required
  field, citation, or caveat. Compare the two routes on the same tasks, and count lower
  token/latency/cost as an improvement only when the response still passes the evals.

## Working rules

- One clear task per run, with an explicit output contract.
- **Read the assembled prompt for contradictions, and state each authority rule
  once.** The GPT-5.6 guidance reports that GPT-5-class models follow prompt contracts
  closely, so conflicting rules create more instability than missing detail, and that
  repeating "ask first", "do not mutate", or "wait for approval" causes approval
  requests for safe, expected actions. This guide applies both checks to every target
  as repository practice.
- Name the current layer of work — research, design, implementation, review, external
  coordination — on long-running tasks, so the model does not move between layers
  silently.
- Persisted reasoning is not a free optimization. It helps while the objective and
  priorities hold; once they move, stale reasoning adds tokens and anchors the model to
  a superseded approach. Where the model supports `reasoning.context` (the GPT-5.6
  family, which defaults to `all_turns`, and GPT-6.1 Sol; not documented for GPT-6.2),
  set `current_turn` when
  earlier reasoning is no longer relevant. Compact at milestones, not every turn, and
  treat compacted items as opaque.
- Preserve explicit user values. Where the right value is implicit, give decision
  criteria and let the model reason from context or schema rather than installing
  universal defaults or keyword maps.
- Render any visual artifact before finalizing, inspect its layout, clipping, spacing,
  missing content, and visual consistency, and revise until the render meets the
  requirements.
- After each tool result, ask whether the success criteria — required actions and
  validation included — are now met with useful evidence; if yes, answer. Loop
  minimization never outranks correctness, required evidence, calculations, or
  required citations.

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
(`prompt-guidance-gpt-5p6`). These are directional results for that sample, not
GPT-6 measurements or promised gains on another workload.

## Sources

The GPT-5.6 section is derived from `prompt-guidance-gpt-5p6`, its facts row from
`model-guidance-gpt-5p6` and `upgrading-to-gpt-5p6-sol`. The GPT-6 family section is
derived from `model-guidance-gpt-6-astra` — the GPT-6 prompting document, "Using
GPT-6", which the Astra URL serves — with per-model facts from `model-gpt-6-astra`,
`model-gpt-6p1-sol`, `model-gpt-6-sol`, and `model-gpt-6-luna` — the document calls its
prompts a starting point across the GPT-6 family, so the section is not limited to
Astra — effort semantics, `configuration_update` limits and the reasoning-item removal
rules from `reasoning`, and Codex-only effort values from `codex-models`. The GPT-6.2
section is derived from `model-guidance-gpt-6p2` ("Using GPT-6.2") with facts from
`model-gpt-6p2-astra` and `model-gpt-6p2-sol`, the caching changes from
`prompt-caching`, and the multi-agent limits from `responses-multi-agent`. The
per-model instruction notes, the default efforts and the 6.2 context sizes come from
the Codex client's local model catalog, which no URL serves and no pin tracks. The shared recipe keeps the GPT-5.6
guidance's task, evidence, tool, and validation practices and applies them to the
GPT-6 and GPT-6.2 targets as this repository's choice, with prompt placement from `prompt-caching`,
run shape from `responses-multi-agent`, schema-forced output from `structured-outputs`,
and the programmatic-stage prerequisite from `tools-programmatic-tool-calling`. Model
behavior claims belong only to their own section; `source_pins` records the exact
bytes used so later vendor edits can be detected.

When a `targets` model changes, re-derive its section from the matching current
document, check the shared rules for contradictions, and re-run representative evals
rather than extending another model's behavior claims to it.
`launch/check-prompting-targets.sh` only checks that every bound model is **named** in
`targets:`; whether the guidance was re-derived is not decidable and is gated nowhere.
