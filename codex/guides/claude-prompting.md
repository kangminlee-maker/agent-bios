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
  - choose guidance by the actual target model — effort defaults, thinking controls, and initiative tuning differ per model, and a technique measured on one model is re-checked before it is applied to another
  - state the goal, the reason behind it, and what done means; let the model choose the route
  - make tool descriptions prescriptive about when to call, not only what the tool does — the prompt is the lever where forced tool choice is rejected
  - compare inherited process scaffolding on the target model before keeping or removing it
  - name the boundary explicitly — what to do without asking, and what to stop and ask about
  - keep the conversation history append-only, and never ask for the reasoning written out in the response
derived_at: 2026-10-20
source_pins:
  - doc: claude-prompting-best-practices
    sha256: e9bd30b6abd49cc42549387cfa7a4cd9946d79d0eb7ed2a1c12f4cf431ee04f4
    pinned_at: 2026-10-20
  - doc: prompting-claude-fable-5-1
    sha256: b921ea4d827411b3f4401fd5c92021eb7166c6c5642688321a3780297d8b5497
    pinned_at: 2026-10-20
  - doc: prompting-claude-opus-5-5
    sha256: 3432e66ac97f77b45e1ecba014c9d6d0001be7ab47b55ebe8c70f5aa55883a14
    pinned_at: 2026-10-20
  - doc: prompting-claude-sonnet-5-5
    sha256: 6886cdd2625b73be5bd74420e31c3a050c1c52b8073b9bebe15f4dcf33e44f91
    pinned_at: 2026-10-20
  - doc: prompting-claude-haiku-5-5
    sha256: e871a37701e88998c5bed2e15c586048c86d3d8ab5c333a67c60ad717e0131fd
    pinned_at: 2026-10-20
  - doc: prompting-claude-opus-5
    sha256: e73cd26863642596486a43f90ff9c04d13f8e4b6cd00ae83546d4d3cd93c5143
    pinned_at: 2026-10-20
  - doc: thinking
    sha256: 8bbc8ed20cffa039e5c2c371c64610c7e4019d2dabf1a01392a87dc0018d9375
    pinned_at: 2026-10-20
  - doc: effort
    sha256: 38cf202f17d28efe5a42f1df1de7f7af5924f76ce05abb7b5989db919ae892e5
    pinned_at: 2026-10-20
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

This guide is a scoped extension of the global Coding Guidelines. Use it when composing
a prompt for a claude-tier model — a review packet dispatched cross-family, a subagent
brief, or the main's own instructions when the main is Claude.

Use the shared recipe and checklist together with the section for the model being
prompted, even when a subagent uses a different model from the main. Each sectioned model
has its own official prompting document; a technique measured on one model is re-checked
on the target before it is borrowed. Model-specific tuning preserves the instructions'
permission boundaries and required verification.

| Target | Apply |
| --- | --- |
| `claude-fable-5-1` | Shared recipe and Claude Fable 5.1 |
| `claude-opus-5-5` | Shared recipe and Claude Opus 5.5 |
| `claude-sonnet-5-5` | Shared recipe and Claude Sonnet 5.5 |
| `claude-haiku-5-5` | Shared recipe and Claude Haiku 5.5 |
| `claude-opus-5` | Shared recipe and Claude Opus 5 |
| `claude-fable-5`, `claude-sonnet-5` | Shared recipe, plus the model's own prompting document (`prompting-claude-fable-5`, `prompting-claude-sonnet-5`) read for every dispatch to it — this guide carries none of its tuning |
| `claude-haiku-4-5` | Shared recipe only. No model-specific document exists. Thinking is off unless manual extended thinking (`enabled` with `budget_tokens`) is requested, adaptive returns a 400, it has no effort levels, and while thinking is on it rejects forced tool choice, a prefilled assistant turn, and `temperature` or `top_k`, allowing `top_p` only between 0.95 and 1 |

## Default prompt recipe

- `Goal` and the **reason behind it** — provide the audience, purpose, and relevant
  context so the model does not have to infer the intent.
- `Success criteria` — what done means and how it is checked.
- `Constraints and boundaries` — state the permitted scope and approval conditions.
- `Tools` — each description states **when to call it**, not only what it does. Name
  prerequisite retrieval and validation when correctness depends on them.
- `Output` — the artifact shape and the register, phrased as what to do rather than what
  to avoid; where words describe a format poorly, give an example in `<example>` tags.
- `Long inputs` — documents and other long material at the top, the request at the end,
  and a request to quote the relevant parts before acting on them.

## Constraints by model

Confirm a constraint against the live surface before a dispatch relies on it.

| Model | Default effort | Thinking off | `tool_choice` `any` / `tool` |
| --- | --- | --- | --- |
| Fable 5.1 | `high` | rejected — always on | rejected |
| Opus 5.5 | `medium` | rejected — always on | rejected |
| Sonnet 5.5 | `high` | rejected; `between_tools` turns off up-front thinking at `high` or below | rejected |
| Haiku 5.5 | `medium` | accepted at `high` or below | accepted |
| Opus 5 | `high` | accepted at `high` or below | accepted |

- Where forced tool choice is rejected, keep `tool_choice` on `auto`, say in the prompt
  when the tool applies, and get schema-valid JSON from strict tool use or structured
  outputs where available (not on every platform; otherwise ask for the format in the
  prompt). Where accepted, a forced call skips thinking; prefer `auto` plus an instruction.
- Manual thinking (`enabled` with `budget_tokens`) returns a 400 on all five, and a
  prefilled final assistant turn on every target but Haiku 4.5; effort, instructions, and
  structured outputs replace them.
- Omit `temperature`, `top_p`, and `top_k` on all five and on Fable 5 and Sonnet 5:
  non-default values return a 400, as does `temperature` with `top_p` even at defaults.
- Thinking counts toward `max_tokens`; leave room, and stream above 21,333 (SDK rule).
- Keep the history append-only: pass each assistant turn back exactly as returned,
  thinking blocks included. On Fable 5.1 and the 5.5 models, editing earlier messages,
  rebuilding `system` or `tools`, or summarizing older turns in place invalidates every
  later thinking block; send per-turn reminders as turn-scoped system messages and let
  server-side compaction trim. A model switch can drop earlier reasoning, since a thinking
  block is readable only by the model that produced it and certain others.
- Do not ask for the reasoning written out in the response, verbatim or in a fixed format:
  on Fable 5.1, Opus 5.5, Sonnet 5.5, and Opus 5 such a prompt, skill, or tool description
  may be declined with `reasoning_extraction`. Ask for a short explanation or a summary of
  the actions taken, or read `display: "summarized"` thinking blocks.
- A decline returns `stop_reason: "refusal"` with the category in `stop_details` and is
  not an answer; each model's document says what a server-side fallback retries, and
  Haiku 5.5 has no fallback and usually refuses again on retry.
- A top-level `effort` change between requests restarts the prompt cache; on Fable 5.1,
  Opus 5.5, Opus 5, Sonnet 5.5, and Haiku 5.5, change effort mid-conversation with the
  per-message form (beta), which takes effect from the next user turn with new input. It
  needs adaptive thinking: thinking off on Haiku 5.5 or `between_tools` on Sonnet 5.5 → 400.

## Claude Fable 5.1

The document also covers Claude Mythos 5.1. Fable 5 prompts carry over unchanged.

- Effort: start at the default `high` and test the others on your own evals; level names
  do not mean the same amount of thinking across models. `medium` roughly matches Fable 5
  at lower cost, and `low` is often competitive with Opus and Sonnet models per task.
- Progress text: it writes fewer user-facing updates in long tool-calling turns, more so
  at higher effort. First check that the client renders progress-update `thinking` blocks
  (`display: "updates"`, beta), then remove lines that suppress narration, then ask for a
  one-line start, brief updates, and a recap that stands alone. Say when the UI hides tool
  output, or it runs commands to "show" output nobody sees.
- Batching: in coding and computer-use loops it may issue one implied call per turn. Nudge
  it to list what it needs next and request every independent item at once — a turn-scoped
  system message after each round of tool results (beta), or a text block after the
  `tool_result` blocks — appending a fresh copy each turn and never deleting old ones.
- Finishing: on long asynchronous work it may announce the next step instead of doing it,
  or ask permission for work already requested. The autonomy block (the user is not
  watching; proceed on reversible actions; stop only for destructive actions or genuine
  scope changes; do what your last paragraph promises) carries most of the effect, and a
  second block makes the request itself the scope. Keep its two exceptions — a problem
  described, a question asked, or thinking aloud without a request for a change gets an
  assessment, not a fix; a state-changing command needs evidence for that exact action —
  and check whether it asks less about ambiguous requests.
- Extras: it may fix nearby code or commit more tests than the change warrants; a
  leave-it-out instruction drops both with no measurable change in task success. It
  rewrites whole files more readily than Fable 5; ask for surgical edits.
- Prose: denser than Fable 5's, and it formats less — replace anti-formatting rules with
  when formatting helps; "Please remove all mannered prose." works. Summaries may reproduce
  source passages unmarked; add one complete example of a correct response and why.
- Search at `low`: it answers from memory more readily. Raise effort for those turns, or
  say that recognizing a name is not knowing its current state and to search it as written.
- Long deliverables at `xhigh`/`max`: it may draft them in thinking and write them again.
  Run them at `high`, or size `max_tokens` for thinking plus reply and say the two share
  one limit.
- Subagents: let the lead keep working — the start tool returns at once, results arrive in
  a later user message, a separate tool waits. It still often waits by choice.
- Dense images: a crop-and-enlarge tool alone delivers most of the uplift. False refusals
  rise on compile-check phrasing (ask "are there bugs"), lesser-known languages (give
  context), and base64 in tool output (remove it).

## Claude Opus 5.5

Opus 5 prompts carry over, and the Opus 5 section remains a reasonable starting point.

- Effort: the default is `medium` (Opus 5: `high`). Set it explicitly and sweep rather
  than carrying the Opus 5 value over: `medium` matches or exceeds Opus 5 at `high` on
  coding and knowledge-work evals, and `low` comes close on several coding evals. At a
  given level it thinks more per turn than Opus 5, most at `xhigh`/`max`, so leave room in
  `max_tokens` (128,000 has worked for long agentic coding turns), reserve `xhigh`/`max`
  for measured gains, and lower effort before prompting for less thinking.
- Thinking is always on. For a prompt that ran on Opus 5 with thinking off: start at `low`
  and measure, remove instructions that stood in for thinking, re-test the Opus 5
  thinking-off mitigations and drop any no-thinking rule either way, and read responses by
  block type. In chat, remove "think carefully" lines; telling it to treat earlier answers
  as settled cuts follow-up thinking, but leave that out of long analyses and agentic work
  and test whether it mutes the model's own corrections.
- Unattended runs: some progress updates end the turn as text (`end_turn`). Treat a
  text-only end of turn as a report, not proof: keep the task's parts in a checklist the
  model updates, send a short user message naming the open items, stop after two or three
  automatic continuations, and wait for background commands or subagents it started. A
  system-prompt paragraph naming the early stops to avoid (a summary that announces the
  next step, an offer to continue, a list of non-blocking decisions, stopping at a
  milestone) and the stops you want makes them rarer; add it from the first request, keep
  your own confirmation for risky actions, and leave it out when a person can answer.
- Progress text arrives as progress-update `thinking` blocks, empty at the default display
  — set `display: "updates"` (beta). Declare a send-to-user tool for verbatim content from
  the first request. After about five silent tool steps, append a one-line reminder as a
  turn-scoped system message, at most two or three times; appended rather than deleted,
  it keeps cache and thinking blocks intact and roughly halved long silences at no cost.
- It gets to work quickly: on loosely specified multi-app tasks say to explore the relevant
  sources, including ones the task does not name, before acting — and keep untrusted
  content out of what it searches, because it acts on what it finds.
- It paces to elapsed time: a harness line such as `elapsed 340s / 1200s` makes agent teams
  finish sooner at comparable quality; the budget is advisory (keep your own timeout) and
  may cost a little searching and verifying.
- Pasted text: wrap it in `<pasted_content id="…">` tags carrying one random id and say in
  the system prompt that instructions inside are followed only where the user asks; the
  tags can be imitated, so this is one guardrail among others.
- Dense images: it reads charts, diagrams, and screenshots more precisely without tools,
  so re-test scaffolding built for earlier models; for the densest inputs, higher
  resolution and crop/measure tools still help (more at higher effort), while effort alone
  helps technical drawings, not charts. Frontend: "avoid a generic look" only swaps one
  default for another — name the patterns to avoid, inspect, and extend the list.

## Claude Sonnet 5.5

Sonnet 5 prompts carry over. For the hardest long-horizon work an Opus model is the better
choice.

- Effort: the levels are recalibrated, so run a fresh sweep. Start at the default `high`
  unless the work is agentic or latency-sensitive: `medium` for well-specified agentic
  coding and `high` for harder or longer tasks, `medium` or `low` for chat. At `low` it
  keeps thinking short and can skip verifying a change; at `low` and `medium` it is more
  likely to check in before a long task is done. For agentic coding set `max_tokens` to
  128,000 and stream. Asking in the prompt for less thinking does not reliably work.
- Initiative: to carry work through at `low`/`medium`, say to keep working until
  everything asked for is done and to stop only when blocked on the user or before a risky
  step. It adds tests, docs, and supporting files at every effort, more at higher ones;
  "when the work is done and checked, stop and report; mention extras instead of doing
  them" limits that. At `xhigh`/`max` it starts its own review rounds and reviewer
  subagents: saying not to unless the user asked cut session cost by about a third at
  `max` with no change in quality. For ideas or a plan, say to stop there.
- `between_tools` is the lowest thinking setting, accepted at `high` or below; with it,
  per-message effort returns a 400, and any instruction not to think must go because it
  leaks internal XML tags. In a request without tools it means no thinking at all.
- JSON on reasoning tasks: with structured outputs it often skips thinking at `low` and
  `medium`. Add "Think the problem through before you answer." (at `high` this nears
  `xhigh` accuracy) or run `xhigh`, with adaptive thinking rather than `between_tools`.
  Treat `stop_reason: "max_tokens"` as a failure even when the text holds valid JSON.
  Without structured outputs it often writes working-out before the final JSON, so a
  whole-response parser fails: follow the document's extraction recipe (non-overlapping
  parse of the last value, or of the last run of values for multi-record answers, a field
  check, one retry) rather than slicing from the first brace to the last.
- Progress text longer than a sentence or two arrives as progress-update `thinking` blocks
  — with adaptive thinking set `display: "updates"` (beta); under `between_tools` the
  summary text comes back anyway and `display` is rejected. Remove "hold all findings"
  lines; after about five silent steps append a one-line reminder as a turn-scoped system
  message, at most two or three times.
- Mid-turn input: it may read harness text after a tool result as an injection. Never put
  user text inside a `tool_result`: append it as a text block after the last `tool_result`,
  keep harness notices in a separate system message, and add no token countdown after
  tool results in interactive sessions.
- Verification: at `low` it may report a change done without a check that exercises it. A
  paragraph requiring a real test, type-check, or build makes that rare at slightly higher
  cost: a syntax-only check or a command that failed to start does not count, missing
  declared dependencies are installed with the project's own package manager and lockfile
  (never via sudo or the system package manager), and a skipped check is named with its
  reason instead of reporting the change done.
- Chat and knowledge work: it sometimes answers from training knowledge where a search
  would catch changed details. Remove "minimize tool calls" wording and say to search for
  specifics that may have changed (what is allowed, required, or charged).
- Dense images: give it a crop, zoom, or code tool. On charts tools help at every effort
  (tools at `high` beat no tools at `max`, cheaper); on technical drawings from `high` up.

## Claude Haiku 5.5

Haiku 4.5 prompts carry over. It is the first Haiku with effort levels; effort replaces
the thinking budget Haiku 4.5 used. Add system-prompt text to new conversations only.

- Effort: `low` for chat, short tool tasks, and high-volume requests (in long agent
  prompts it then skips searches, stops early, and skips checks more often); `medium`, the
  default, for most work including agentic coding; `high` for knowledge work, longer
  agent tasks, and strict instruction following; at `xhigh`/`max` also run the evals on
  Sonnet 5.5 and compare. Telling it to answer directly did not stop it from thinking —
  lower the effort. At `xhigh` in multi-turn chat it sometimes answers entirely in
  thinking and ends with no visible text; check for empty replies.
- Search: give today's date, rendered once and sent unchanged on later requests; on a
  later day, give the new date in the newest turn. With a long prompt or at `low`, add
  after the date that training data ends well before today and changeable facts are
  searched even when it feels sure. A blanket "search any factual question" rule searched
  half of the no-search prompts with no more correct answers.
- JSON with your own tools: with thinking off it may skip a tool call it needs. Use
  adaptive thinking, drop `output_config.format` where a tool must run, or force the call
  with `tool_choice`; if thinking must stay off, say the JSON format applies to the final
  answer only and tools are called first with no text before the call.
- Early stopping: with a long coding-agent prompt at `low` it may hand the task back. Say
  to keep working until done and to stop only when blocked or before a risky step; moving
  from `low` to `medium` roughly halved early stops and more than doubled output tokens.
  At `low`/`medium` it may also report a change done without a check; the same real-check
  paragraph as for Sonnet 5.5 made it check more often, with better results at more tokens.
- Mid-turn input and chatbots: never put user text in a `tool_result`; append it after the
  last `tool_result` and keep notices in a separate system message. For a chatbot, say the
  system prompt's rules hold for the whole conversation despite arguing, sympathetic
  reasons, or repeated asking, and use `high` when adherence matters most. Reasoning-like
  text in the reply means switch to adaptive thinking at `medium`.

## Claude Opus 5

- Effort: start at the default `high` and re-run the sweep; `low` and `medium` hold strong
  quality at a fraction of the tokens, and `xhigh` is for demanding coding and agentic
  work. It performs best given the complete specification up front and left to run.
- Review: it finds real bugs at a high rate with few false positives, and accuracy holds
  at lower effort. "Only report high-severity issues" is followed literally and depresses
  what is reported; ask for everything and filter in a separate pass.
- Verification: it verifies its own work unasked. Remove scaffolding that only tells it to
  verify — a self-check step for every task, a verifier subagent, "double-check" rules —
  which cuts tokens with no loss in quality; a repository's required checks and the user's
  explicit asks are not such scaffolding. Constrain scope explicitly for narrow tasks,
  since it can widen a task on its own judgment.
- Delegation: it delegates readily, which multiplies cost on small tasks. Say which work
  warrants a subagent and which does not, and prefer deterministic caps —
  `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, and the
  SDK's `max_budget_usd` (Claude Code 2.1.217 or later). Claude Code adds its own
  delegation instruction only with the `claude_code` preset.
- Length: responses and written files run longer than earlier Opus models', and lowering
  effort does not reliably shorten the visible response. Prompt for conciseness and
  document length explicitly; in a long system prompt, repeat it briefly near the end.
- Narration: it announces what it is about to do. Describe the cadence you want (one line
  before the first call, updates on a finding or direction change, outcome first at the
  end); positive examples beat lists of what not to do. Limit correction narration to
  errors that would change the reader's code or decisions.
- Dense images: re-validate workarounds tuned for prior models; tools to crop and visually
  verify are a more cost-effective lever than thinking alone.
- Thinking off is accepted at `high` or below and is usually the wrong lever: thinking on
  at `low` beats it at similar cost. Off, it can write a tool call as text or leak
  internal XML tags; one instruction mitigates both (you may say a brief sentence before a
  tool call; say so when no tool fits; no internal XML tags), the general form beats
  naming the tags, and any "do not think" rule must go.

## Prompt assembly checklist

1. Write the goal, the reason behind it, and the success criteria.
2. Name the boundaries — what to do freely, what to stop and ask about.
3. Give each tool a when-to-call description, and check that the target accepts the tool
   and output settings the dispatch relies on.
4. Say what the final message must contain and how completion is checked, and decide how
   the harness treats a turn that ends in text with work still open.
5. Apply the target model's section and check for contradictions. Compare changes on the
   same tasks; remove inherited scaffolding only when the target benefits, keeping
   required repository checks and permission boundaries intact.

## Sources

The shared recipe and the append-only and reasoning rules come from
`claude-prompting-best-practices`; the constraints from `thinking`, `effort`, and the
model documents; each model section from its own document (`prompting-claude-fable-5-1`,
`prompting-claude-opus-5-5`, `prompting-claude-sonnet-5-5`, `prompting-claude-haiku-5-5`,
`prompting-claude-opus-5`). `source_pins` records the exact bytes used, and a model name in
`targets` does not extend another model's claims to it.

When a `targets` model changes, re-derive its advice from its own current document and
check the shared recipe for conflicts. `launch/check-prompting-targets.sh` fails when the
launch config binds a model this guide does not list; that check is about **naming**, and a
model added to `targets:` satisfies it forever. Whether the guidance was actually
re-derived is not decidable and is gated nowhere.
