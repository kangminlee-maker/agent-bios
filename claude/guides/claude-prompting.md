---
guide_id: claude-prompting
language: en
status: active
use_when:
  - composing a prompt, packet, or tool description for a claude-family model
  - dispatching cross-family review to the claude side from a Codex main
  - prompting claude subagents, or prompting yourself when the main is Claude
  - porting a prompt written for an older claude model
  - deciding a reasoning-effort level for claude work
core_rules:
  - choose guidance by the actual target model — each bound tier has its own vendor document and they disagree on effort, initiative, and verification
  - effort level names do not carry across models; after a rebind, sweep levels again instead of keeping the previous model's setting
  - state the goal, the constraints, and the reason behind the request; let the model choose the route
  - compare inherited process scaffolding on the target model before keeping or removing it
  - put the full task specification in the first turn for long-horizon work rather than revealing it across turns
  - make tool descriptions prescriptive about when to call, not only what the tool does
  - require progress claims to be audited against a tool result from the same session
  - name the boundary explicitly — what to do without asking, and what to stop and ask about
derived_at: 2026-10-21
source_pins:
  - doc: prompting-claude-opus-5
    sha256: e73cd26863642596486a43f90ff9c04d13f8e4b6cd00ae83546d4d3cd93c5143
    pinned_at: 2026-10-21
  - doc: claude-prompting-best-practices
    sha256: e9bd30b6abd49cc42549387cfa7a4cd9946d79d0eb7ed2a1c12f4cf431ee04f4
    pinned_at: 2026-10-21
  - doc: prompting-claude-fable-5-1
    sha256: b921ea4d827411b3f4401fd5c92021eb7166c6c5642688321a3780297d8b5497
    pinned_at: 2026-10-21
  - doc: prompting-claude-opus-5-5
    sha256: 3432e66ac97f77b45e1ecba014c9d6d0001be7ab47b55ebe8c70f5aa55883a14
    pinned_at: 2026-10-21
  - doc: prompting-claude-sonnet-5-5
    sha256: 6886cdd2625b73be5bd74420e31c3a050c1c52b8073b9bebe15f4dcf33e44f91
    pinned_at: 2026-10-21
  - doc: prompting-claude-haiku-5-5
    sha256: e871a37701e88998c5bed2e15c586048c86d3d8ab5c333a67c60ad717e0131fd
    pinned_at: 2026-10-21
targets:
  - claude-fable-5-1
  - claude-opus-5-5
  - claude-sonnet-5-5
  - claude-haiku-5-5
  - claude-fable-5
  - claude-opus-5
  - claude-sonnet-5
  - claude-haiku-4-5
verification_focus:
  - prompt changes are A/B'd against the prior scaffolding rather than assumed
  - effort changes are swept across levels on a real eval set, not chosen by reputation
  - per-model constraints are confirmed against the live surface before use
  - model-specific advice stays within its named section, including after assembly
---

# Claude Prompting Guide

This guide is a scoped extension of the global Coding Guidelines. Use it when
composing a prompt for a claude-tier model — a review packet dispatched
cross-family, a subagent brief, or the main's own instructions when the main is
Claude.

Use the shared recipe and checklist together with the section for the model being
prompted, even when a subagent uses a different model from the main. Model-specific
tuning preserves the instructions' permission boundaries and required verification.

| Target | Apply |
| --- | --- |
| `claude-fable-5-1` | Shared recipe and Claude Fable 5.1 |
| `claude-opus-5-5` | Shared recipe and Claude Opus 5.5 |
| `claude-sonnet-5-5` | Shared recipe and Claude Sonnet 5.5 |
| `claude-haiku-5-5` | Shared recipe and Claude Haiku 5.5 |
| `claude-opus-5` | Shared recipe and Claude Opus 5 |
| `claude-fable-5`, `claude-sonnet-5`, `claude-haiku-4-5` | Shared recipe; consult the target's own guidance before borrowing another model's tuning |

## Default prompt recipe

- `Goal` and the **reason behind it** — provide the audience, purpose, and relevant
  context so the model does not have to infer the intent.
- `Success criteria` — what done means and how it is checked.
- `Constraints and boundaries` — state the permitted scope and approval conditions.
- `Tools` — each description states **when to call it**, not only what it does.
  Name prerequisite retrieval and validation when correctness depends on them.
- `Output` — the artifact shape and the register.

## Claude Fable 5.1

- Begin effort experiments at `high`; compare supported levels afresh. Identical
  effort names need not have identical costs across models.
- Request brief start, progress, and final updates; first verify the client renders
  updates and remove conflicting silence instructions.
- Batch independent tool calls. Let the lead do independent work while subagents run.
- Complete authorized requests, including promised next steps. State genuine approval
  boundaries and whether a person is available; avoid unnecessary pauses.
- Ask for literal prose and useful formatting. Demonstrate how retrieved quotations
  should be marked and attributed.
- Keep edits targeted and tests proportional to the requested behavior; report
  unrelated issues separately.
- At `low`, explicitly trigger retrieval for current facts instead of trusting name
  recognition. Compare higher effort when retrieval still fails.
- Preserve decisions, constraints, open work, and exact details in compaction summaries.
- Append API history unchanged; use supported compaction instead of replaying thinking
  against an edited prefix.
- At `xhigh`/`max`, budget tokens for thinking and the deliverable; compare `high` for
  long outputs.
- Give dense-image work crop and zoom tools.

- `medium` roughly matches Claude Fable 5 at lower cost, and `low` often beats the
  smaller models on cost per task — include it wherever you would otherwise run a
  smaller model at a higher level.

These are prompt and harness tuning choices, not changes to the configured seat's
effort or permissions. Advice in the other model sections does not transfer to this one.

## Claude Opus 5.5

- The default is `medium`, where Claude Opus 5 defaulted to `high`. At a GIVEN level
  this model thinks more per turn, so carrying an Opus 5 level forward buys longer
  turns and more output tokens rather than more depth. Reserve `xhigh` and `max` for
  work with a measured gain.
- Thinking is always on and `thinking: disabled` is rejected. Remove instructions that
  stood in for thinking, and remove any rule telling the model not to think.
- Progress notes between tool calls arrive as progress-update thinking blocks whose
  text is empty at the default display, so a client that renders only text looks silent
  through a long turn.
- In unattended loops a text-only end of turn is a report, not proof of completion.
  Keep the parts in a checklist, re-prompt the open items, and stop after two or three
  automatic continuations rather than looping.
- Safety classifiers decline with `stop_reason: "refusal"` and a named category; the
  biology safeguards are new if you are coming from Opus 5.
- It reads charts, diagrams and screenshots markedly better unaided — re-test visual
  scaffolding built for earlier models before keeping it.
- In multi-agent harnesses, an elapsed-time line against a budget makes teams finish
  sooner; the budget is advisory, so keep your own timeout.
- Mark text the user pasted in tagged blocks and say so in the system prompt.
- For frontend work, name the specific defaults to avoid; a general "avoid a generic
  look" swaps one default for another.

## Claude Sonnet 5.5

- Levels are recalibrated against Claude Sonnet 5, so sweep again rather than carrying
  a level over. Start at `medium` for well-specified agentic work and `high` for harder
  or longer tasks.
- At `low` it can report a change done without running a check, and at `low`/`medium`
  it checks in before finishing a long task. Raise effort first; otherwise state
  carry-through and the scope boundary in the system prompt.
- At `xhigh` and `max` it starts its own review rounds and may launch reviewer
  subagents. Telling it to stop once the requested work passes its checks cut session
  cost by about a third in vendor testing with no quality change.
- It adds tests, docs and supporting files that were not requested, at every level and
  more at higher effort. Say so explicitly if you want changes limited to the request.
- For a JSON answer to a multi-step reasoning task, add a line asking it to think the
  problem through first, or run `xhigh`. Treat `stop_reason: "max_tokens"` as failed
  even when the text parses.
- It occasionally calls a tool with the wrong letter case or a near-miss parameter
  name: accept an unambiguous match, or return an error naming the exact expected name.
- Never put user text inside a tool result; deliver mid-turn input as a user turn, and
  keep harness notices in a separate message.

## Claude Haiku 5.5

- The first Haiku with effort levels, replacing the thinking budget, so there is no
  previous setting to carry over. The default is `medium`.
- `low` is cheapest but likelier to skip a search, stop early, or skip a check. Use
  `high` where strict instruction following matters. Before paying for `xhigh` or
  `max`, compare Claude Sonnet 5.5 on quality, cost and speed.
- Give a search tool today's date. Add an explicit instruction to search what may have
  changed when the system prompt is long or effort is `low`; avoid blanket "always
  search" wording, which searches when nothing needs it without improving answers.
- In long agent prompts at `low` it stops early and hands the task back. Add a
  carry-through instruction, raise effort, or both.
- At `low` and `medium` it can report a code change done without a check that exercises
  it; require a real check and name what counts as one.
- Safety classifiers are new coming from Haiku 4.5, and this model has no server-side
  fallback — handle a refusal in your own client.

## Claude Opus 5

The following behavior claims and tuning recommendations apply to `claude-opus-5`,
which no tier binds today; they remain here because the model stays selectable.

### When to add blocks

- Long-horizon or autonomous work: give the full spec up front in one
  well-specified turn and run at a high effort. Do **not** add a self-check
  cadence or a dedicated verifier subagent: the helm binding verifies its own
  work unasked, so an instruction to verify buys over-verification instead.
  Deleting inherited verification scaffolding costs no capability — this inverts
  the usual self-check advice, so carve this tier out of a prompt library that
  applies that advice uniformly.
- Review: state the evidence bar and the verdict shape. This tier follows
  severity filters literally, so "only report high-severity" depresses measured
  recall even as bug-finding improves — ask for every finding with confidence
  and severity attached, and filter downstream.
- Delegation: say when *not* to delegate, and cap the spawn count. The helm
  binding reaches for subagents readily — the reverse of the binding it replaced
  — and every spawn rebuilds context, reports back, and is then re-read, so
  unbounded delegation multiplies cost and latency. Where the harness offers
  deterministic caps, prefer them to prose: under Claude Code and the Agent SDK
  these are `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`,
  `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, and the SDK's `max_budget_usd` — a
  limit the model cannot talk itself past. Confirm the harness version supports
  them before relying on it. File-based memory and custom
  tools are the opposite case: they still need an explicit when-to-use trigger.
- Autonomous runs with no human watching: say so. Otherwise it asks permission
  it does not need and blocks. Grant autonomy on minor choices (naming,
  defaults, equivalent approaches) while keeping the ask for scope changes and
  destructive actions.
- Progress reporting: require each claim to be traceable to a tool result from
  the session, and unverified work to be labeled as such.

### How to choose prompt shape

- One bounded question with a self-contained packet → a single run. Default for
  review.
- Independent workstreams → delegate, and prefer asynchronous subagents over
  spawn-and-block: long-lived agents keep their context instead of rebuilding it
  per subtask, and the orchestrator is not pinned to the slowest one.
- Start effort experiments at `high`; compare lower settings on representative
  tasks and step up to `xhigh` for demanding coding or agentic work when quality
  improves. Re-test inherited defaults. The configured seat's effort remains an
  explicit workload choice. Effort does not control response length — see Working
  rules.
- Per-model constraints differ across the `targets` bindings — thinking
  configuration, sampling parameters, and effort support are not uniform, and
  the sweep binding is the most restricted. On the helm binding, for instance,
  thinking is on by default and turning it off is accepted only at `high` effort
  or below. Confirm the constraint against the
  live surface before relying on it in a dispatch; do not assume the frontier
  binding's rules apply to the sweep one.

### Working rules

- Expect long turns. A single request on a hard task at high effort can run for
  minutes; plan timeouts, streaming, and progress UX around that rather than
  treating a quiet call as a hang.
- Do not add "summarize every N tool calls" scaffolding — this tier narrates on
  its own. If it narrates too much for a coding agent, set a silence default
  instead: text only on a finding, a direction change, or a blocker. Describe the
  cadence you want by example; a positive description of the style outperforms a
  list of what not to do.
- Length is a prompting lever, not an effort lever. This tier writes longer
  answers and longer files than its predecessors, and lowering `effort` does not
  reliably shorten visible output — only an explicit instruction does. Calibrate
  the deliverable's length separately from the conversation's.
- Scope self-correction. Left alone this tier narrates its own earlier mistakes
  at length, which reads as thrash. Ask it to correct only what would change the
  reader's decisions, say it plainly, and carry on.
- Give it somewhere to write learnings, tell it to consult that place later, and
  give the file a format. It performs notably better with a memory surface.
- Keep the deliverable readable: the final message is the reader's first look at
  work they did not watch. Lead with the outcome; drop the working shorthand.
- Do not show a remaining-context countdown. This tier can start conserving and
  suggest a fresh session instead of finishing.
- Re-validate prompt-side vision workarounds carried from older bindings; this
  tier is strong on charts, documents, diagrams, and UI replication, and the
  workaround may now be the thing costing quality. Tools that let it crop and
  visually verify beat thinking alone here.
- Instruction following stays consistent across the full context window, so a
  rule does not need restating near the end to survive a long session.

### Running with thinking disabled

Disabling thinking is accepted only at `high` effort or below, and it is usually
the wrong lever: thinking on at `low` effort generally beats thinking off at
comparable cost. Reach for lower effort before reaching for the switch.

Two artifacts appear when it is off, and both are prompt-fixable:

- A tool call written as **user-facing text** instead of a structured call. The
  turn completes, the call never runs, and in an agentic loop the leaked text
  stays in history and contaminates later turns. Most common on tool-heavy work.
- Internal XML tags leaking into the visible response.

One instruction mitigates both — permission to speak before a call, an out when
no tool fits, and a general ban on internal tags:

> When you use a tool, you may say a brief sentence first. If no tool can express
> what the user asked for, say so instead of guessing. Do not include internal or
> system XML tags in your response.

Two traps. Naming the tags specifically is **less** effective than the general
form. And if a prompt anywhere tells this tier not to think or not to reason,
delete it: that instruction increases tag leakage rather than suppressing it.

## Prompt assembly checklist

1. Write the goal, the reason behind it, and the success criteria.
2. Name the boundaries — what to do freely, what to stop and ask about.
3. Give each tool a when-to-call description.
4. Say how progress claims must be grounded, and how the deliverable should read.
5. Apply the target model's section and check for contradictions. Compare changes
   on the same tasks; remove inherited scaffolding only when the target benefits,
   keeping required repository checks and permission boundaries intact.

## Sources

The shared recipe is derived from `claude-prompting-best-practices`; each model
section from that model's own document — `prompting-claude-fable-5-1`,
`prompting-claude-opus-5-5`, `prompting-claude-sonnet-5-5`,
`prompting-claude-haiku-5-5`, `prompting-claude-opus-5`. `source_pins` records the
exact bytes used for this derivation. A model name in `targets` never extends one
model's behavior claims to another; the sections are deliberately separate because
the vendor's own pages disagree on effort defaults and on how much initiative to
expect.

When a `targets` model changes, re-derive its advice from its own current document
and check the shared recipe for conflicts.
`launch/check-prompting-targets.sh` fails when the launch config binds a model
this guide does not list; that check is about **naming**, and a model added to
`targets:` satisfies it forever. Whether the guidance was actually re-derived is
not decidable and is gated nowhere.
