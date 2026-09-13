---
guide_id: cli-multi-model-workflow
language: en
status: active
use_when:
  - work spans multiple models or CLI agents
  - a handoff crosses a context reset, or parallel worktree branches run
  - running unattended LLM batches or orchestrated subagent fleets
  - allocating tiers, spawning subagents, or planning model switches
  - resuming a halted staged pipeline or writing a handoff
---

# CLI Multi-Model Workflow

Scoped extension of the global Multi-Model Workflow rules. Rules use portable role slots; only **Driving Codex CLI Directly** and **Environment Binding** name concrete tools or models.

## When To Use

- Use for multiple models/agents, handoffs across clear/new sessions, unattended fleets, or parallel worktrees. Routine auto-compaction is not a handoff.
- Skip single-session, single-model work with no handoff.

## Role Slots And Tiers

- FRONTIER: hardest bounded design, authority-changing decisions, triage, final verdicts.
- HELM: standing main/judgment seat; orchestration and bounded escalation.
- WORKHORSE: implementation volume and per-item judgments. SWEEP: read-only work applying one explicit rule to each item, returning ambiguity as an exception.
- VERIFIER-A/B: different review kinds, preferably cross-family. INDEPENDENT-PR-REVIEWER: final review from a different family than the author.

- Bind concrete models in Environment Binding and allocate by **difficulty × blast radius**. The main defaults to HELM; first-of-kind/authority-changing mains use FRONTIER at a session boundary; trivial work stays direct.
- Apply the same allocation to subagents. Prefer spawning a bounded FRONTIER judgment over switching the loaded main; a context cannot switch its own model.
- Keep architecture, interfaces, scope, tradeoffs, and user-facing decisions in the main. Delegate volume work.
- A cheaper implementation tier requires stronger verification; never economize on both.

## When To Spawn

Main-context pollution is usually costlier than spawn overhead. Apply these gates in order; the first that fires decides:

1. **Independence:** verification and review go outside your own reasoning, not merely outside your conversation. A child carries the standing corpus on both hosts, except Claude's built-in `Explore` and `Plan`, which omit the CLAUDE.md hierarchy. Otherwise a Claude child starts fresh, while Codex `spawn_agent` forks by default — `fork_turns` defaults to `all`, so the child also holds the parent's turn input unless the call passes `none` or a turn count. What a spawn buys is graded by the seat — see Review Independence — never by the fact that it happened.
   Verify a spawn from the artifact: Claude writes the child to its own `agent-<id>.jsonl` beside the session transcript; Codex writes a rollout whose header carries `parent_thread_id`, `agent_nickname`, `agent_path`, `agent_role`. Codex's `--json` stream cannot see a spawn at all — its `collab_tool_call` object is identical whether or not one occurred.
2. **Parallelism:** independent items spawn in parallel with per-item tracking.
3. **Residual context:** spawn work whose working log is much larger than the conclusion the main needs, such as broad reads, searches, tests, or implementation bursts.
4. **Specifiability:** keep work local when it needs the main's live context or unresolved round-trips, especially deep debugging. Grind alone is not a FRONTIER reason.
5. **De-minimis:** do work directly when its dispatch packet would be larger than the work.

- **Escalation:** spawn FRONTIER first for a bounded judgment with material stakes (an irreversible or authority-changing action ahead, an architecture or public-interface commitment, or invalidation of two or more downstream units) and a named residual-risk signal (two failed attempts, two persisting alternatives, conflicting evidence, or an unverified assumption that can flip the decision). Pre-note the finding that would change what; send a blind packet — evidence, constraints, rubric, neutrally ordered alternatives, never the main's draft conclusion — and record the disposition afterward (what changed, or why nothing did; persistent no-change indicts the gate or the packet). Switch the main only when the judgment is not delegable.
- Every spawn gets a bounded report contract, artifact paths instead of pasted context, and an explicit model/effort pin. Never dump a worker transcript into the main.
- Explicit no-fan-out overrides standing authorization.
- Record one line per gate decision — `SpawnGate: <gate> <tier> spawn|inline — <why>` — plus the FRONTIER disposition. A launch contract's `Delegation=off` lifts the spawn obligation, not the records.

### Cost-Driven Down-Spawn (bounded implementation work)

For a unit already classified as bounded implementation work, this rule takes the place of gates 4 and 5 above; gates 1–3 and Escalation still come first, and an explicit no-fan-out instruction still wins. It is the measured text — apply it verbatim, do not paraphrase it:

> This rule applies at a work-unit boundary of bounded implementation work; an explicit instruction not to fan out always wins. Spawn a WORKHORSE for the unit when it has 5 or more items and is decision-complete, has a machine-checkable done-when, and is self-contained; otherwise do it inline. An unstated count is below 5.

Measured 2026-09-08 on the dependent L2 edit family with a claude-opus-5 (xhigh) parent and a claude-sonnet-5 WORKHORSE child: delegating a five-item unit saved about $0.05 per unit and a ten-item unit $0.14–0.18, net of the rule's own cost; a one-item unit cost $0.05 more delegated, and a three-item unit was unresolved at the registered sample. Untested sizes between and above the tested ones rest on the assumption that a saving present at 5 and 10 holds at 6–9 and beyond; the ordering with the gates above, the cost of reading this guide, and the rule's firing rate were not measured. Shipped by guide placement rather than into the global (decision D-20260908-2186cd).

## Delegation Mechanics And Teammate Persistence

Delegate execution, not decisions. A unit is delegable only when it is decision-complete, self-containedly specifiable, machine-checkable at done-when, and bounded in blast radius. Delegated output is staged until the main accepts it — workers take no external irreversible actions — and handling (brief, verify, correct, integrate) must be clearly subordinate to the work itself. A SWEEP-bound unit applies one explicit rule per item and returns ambiguity as an exception, never resolved.

- Re-cut units containing unresolved choice, discovery-before-spec, untestable completion, or unfrozen interfaces. A worker asking which direction to take is a sizing failure; the decision returns to the main.
- Bundle related sub-floor tasks up to the decision-complete ceiling. A scout is read-only and reports file:line evidence for named pending decisions, probing the highest kill-risk unknown first.
- Prompt constants, thresholds, signatures, and judgment criteria are decisions even when stored in code. Discard decision-tainted worker output when review would cost more than a clean re-dispatch.
- Worker cost grows with request count × transcript prefix. Batch independent reads, minimize edit rounds, and dispatch independent workers/messages together.
- **Pin the tier before dispatch.** Unpinned, the tier is chosen once the work is in view and tracks task size rather than task difficulty. Claim a cost advantage only from evidence on this task.
- Use a resident teammate only for dependent slices in one burst. Verify that the CLI preserves its model and context; resume-after-completion may silently change both. Retire after the burst or cache TTL, and persist durable knowledge in files.
- After a discard or direction change, respawn once a routine round costs about as much as a fresh slice. Recover unique in-flight state to files first.
- Redirects to busy workers may queue rather than preempt. Check artifacts before destructive redirects, phrase them conditionally, and stop an actively harmful worker by scoped PID/worktree authority.
- Idle/progress notifications are hypotheses; verify repo artifacts before re-dispatch. An idle signal is liveness decoupled from the report: a subagent can go idle without ever delivering its result, so idle-without-report is not done — request the report explicitly rather than waiting. Cross-reset state belongs in files, not task boards or transcripts. When polling concurrent async jobs, pin the exact id/handle received at dispatch — a "latest" convenience selector can silently point at a sibling job and return plausible-but-wrong results.
- Give reviewers/subagents a read-only diff, snapshot, or isolated worktree — not the live tree the main is editing — and forbid destructive git ops (checkout --, reset --hard, stash, clean) on any tree with uncommitted work; re-verify tree integrity before trusting results produced mid-edit.
- Codex `spawn_agent` decides how much of the parent crosses: `fork_turns` defaults to `all`, and takes `none` or a turn count. A `SubagentStart` hook there receives `agent_type` and may return `continue: false`, so a tier rule can be enforced rather than stated.
- No per-spawn corpus suppression exists on either host: the subagent definition carries model and effort, not scope. Excluding the standing instructions is a process-level act — `claude --setting-sources ''`, or `CODEX_HOME` pointed at a directory holding only `auth.json` — and it removes the tier definitions with them, so a corpus-free reader and a pinned tier cannot come from one process. An emptied `CODEX_HOME` without `auth.json` fails 401; skills still load.
- Review cost scales with the diff, so layered review preserves delegation savings. Lower reviewer tier before dropping a review kind.

## Driving Codex CLI Directly

Instruction/config reach is per invocation. A rule in AGENTS.md cannot bind a hermetic worker; put required hermetic rules in its prompt/schema.

| Profile | Reach | Use |
|---|---|---|
| inherit | real `CODEX_HOME`, project cwd | full global/project AGENTS.md and user config |
| hermetic | temporary home, auth only, user config ignored | independent lens with prompt-owned criteria |
| custom | caller-populated home | exact curated instructions/config |

- Control instruction home, working directory, config overrides, task prompt, and output schema independently. The repo wrapper owns setup and teardown.
- Inherit review is discipline-aware; hermetic review is an independent kind. Confirm reach with a contrast phrase from AGENTS.md before trusting independence.
- Concrete flags, versions, sandbox defaults, and dispatch bindings live in Environment Binding.

## Default Frame

| Stage | Owner | Artifact / exit |
|---|---|---|
| 0 Triage | current session | difficulty/blast-radius call; dials fixed |
| 1 Design | FRONTIER | dated design with measured background, done-when, concept map, allocation; owner approval |
| 2 Design verify | VERIFIER-A+B | findings union and revision; zero material issues |
| 3 Implement | WORKHORSE | smallest viable diff; deterministic gates green |
| 4 Implementation verify | SWEEP → WORKHORSE → FRONTIER | at least two reviewer kinds; strongest model on verdicts |
| 5 PR review | INDEPENDENT-PR-REVIEWER | clean cross-family review |
| 6 Merge verify | implementing session | freshly fetched merged state green |
| 7 Close | current session | docs/handoff synced; no silently parked items |

- A T1+ kickoff names the session model, orchestration authorization, this guide, and main-as-orchestrator delegation mode.
- T0 mechanical/low-risk uses stages 3→4 (→5 for shared merge); T1 normal work uses the full skeleton with a lightweight design; T2 authority-changing/first-of-kind/release work raises design and verdict review.
- Put stage transitions on context-reset boundaries so model changes are free and the design doubles as handoff. Keep a loaded session only when live state is load-bearing.
- Apply the **convergence heuristic by reviewer kind**: same-kind convergence raises confidence but shares blind spots; different-kind divergence is expected, so act on the union.
- If verification broadens the issue boundary, return to design and re-triage; the second identical loopback stops for owner choice. Halts resume from valid artifacts. Persist per-item outcomes.

## Model Switching And The Prompt Cache

- Prompt caches are per model; each mid-session switch reprocesses the loaded transcript once. Batch work by model and switch at reset boundaries.
- Prefer a spawned FRONTIER decision. Switch the main only when context fidelity outweighs handoff cost and the judgment cannot be delegated.
- Avoid unplanned alternation. Planned escalate/return and explicit A/B comparisons are valid when each cache miss is budgeted.
- Forking preserves conversation content on both hosts and the prompt cache on only one: a Claude `--fork-session` at the same model reuses nearly all of it and loses it across models, while a Codex `exec fork` re-sends at any model. So "fork without changing the model" is a Claude rule; on Codex a fork is priced like a fresh dispatch.

## Cross-Verification Economy

- Once cross-verification is warranted, keep kind diversity and tune effort first. Losing a kind loses an error class.
- Run deterministic gates before LLM review. Funnel SWEEP finders → WORKHORSE judgments → FRONTIER triage/verdicts.
- On family collapse, record the downgrade and label clean verdicts PROPOSED until diversity is restored.
- A silent/dead lens is incomplete, never clean. Confirm liveness from usage/error/report evidence; rerun, swap provider, or report PROPOSED.
- Kind labels do not guarantee distinct backends: wrappers and rate-limit fallbacks can silently route two "different-kind" verifiers to the same model/provider. Before trusting diversity on a high-stakes verdict, confirm each verifier's actual backing model from live process or usage evidence; on collapse, treat the pair as one kind and label PROPOSED. Runners recording what ran need the same read: identity taken from the target at execution time, never a runner-side literal, and asserted equal to what was requested — fallback seats pass existence checks.

### Review Independence

How much independence a review actually bought, as an ordinal grade per reviewer rather than a global cross/same flag. Given the main seat `M` and the reviewer seat `R`:

| Grade | When |
|---|---|
| `provider_difference` | `R.provider != M.provider` |
| `model_difference` | same provider, `R.model != M.model` |
| `higher_effort` | same provider and model, `R.effort` strictly above `M.effort` |
| `perspective_floor` | otherwise — still a real review |

- Only upward counts. A different-but-**lower** effort earns nothing and lands on the floor: cheaper is not another perspective.
- **Isolation is a gate, not a rung.** A reviewer that cannot be shown to run in a fresh context is excluded entirely (`NOT_REVIEW`), never graded low — an in-context "review" is the failure this ladder exists to make visible, so it must not appear as a weak pass. Isolation is realised per mechanism: a fresh read-only subprocess, a hermetic profile, a stdio tool call in a fresh session, a headless host workflow, or a stateless API call. If none of these can deliver the required seat, the review did not happen. An in-process subagent clears the conversation and keeps the standing instructions, so it satisfies isolation and still grades only by its seat — spawning is not itself a rung.
- The floor still requires **at least two distinct perspectives**; one pass on the main's own seat is self-review with extra steps.
- Multiple ready methods are **coverage, not diversity**. Distinct labels do not prove the perspectives differed.
- **Achieved is not available.** What can be projected before a review runs is `projected`; a clean verdict without a receipt evidencing a fresh dispatch, the declared packet, a non-empty result and the exact seat is `PROPOSED`, never ACHIEVED. A model echo is not a receipt.
- **Evidence access is its own axis.** When every reviewer saw only the blind packet, convergence — even across providers — is evidence about the packet's framing, omissions included. Before adopting a converged verdict resting on a code seat, a measured fact, or a constraint list, route one seat with live read access to falsify those facts: a lone dissent citing a real constraint outweighs a blind majority, and the missing fact returns to the packet. It sits beside the ladder, not on it.

## Dual-Provider Design Drafts

- Trigger: the task is design — high-level shape and implementation process, before any code — AND two or more providers are reachable at frontier tier. Reachability via an OAuth session is subscription-covered — no marginal spend, so no approval and no question: if a non-main-context OAuth frontier provider exists, proceed with the dual-provider design directly. The consent gate applies ONLY to a provider reachable solely via a metered API key: dispatching to it needs the user's explicit per-request approval of that spend (per-request, not standing — an old approval does not carry to the next design). If the only way to reach a second provider is un-approved metered API spend, stay single-provider rather than blocking the design.
- Mechanics: compose ONE blind packet (evidence, constraints, rubric, neutral alternatives — the escalation-gate packet shape) and dispatch it unchanged to one frontier-tier model per provider; drafts stay independent — neither sees the other's output. Then adjudicate: compare the two dual-provider frontier design drafts against the rubric, take the winner as the skeleton, graft the loser's superior parts, and record what differed and why the synthesis chose as it did (FRONTIER disposition line).
- Packet injection: a dispatched designer is hermetic — it reads only its packet and never loads this corpus. Inject the design principles the corpus would have supplied: concept economy (reuse/extend/rename/split, compact concept graph), the LLM/tools-code capability boundary, the staged design rules (smallest viable path, falsifiable done-when), and any domain-specific principles the design touches. A draft produced without the principles is not comparable to one produced with them.

## Unattended Batch Safety

- The parent owns per-item completion and a **code-level circuit breaker**. For dispatchers you do not control, verify equivalent protection or attend the run.
- Default breaker: halt after 3 consecutive cross-item provider limit/auth/transport failures after bounded backoff. Persist undone items and alert or swap provider.
- Item-specific failures are poison items: cap at 2–3 attempts, then dead-letter them as complete-with-failure. Resume only unfinished/invalid items; whole-batch reruns require cheap idempotence.
- An enumeration run is done only when its collected count is asserted against the source's own reported total for the same filter. Classify retriable failures by class — any server-side transient — rather than an enumerated code list, since an omitted code drops items silently; persist which batches failed and reconcile them before declaring completion; and treat a mismatch, or a total from a differently scoped population, as a defect rather than a footnote. A declared partial or sampled scope is outside this.
- Persist per-item outcome, token, and cost records for recalibration.
- Before releasing a metered batch past its first item, use that item to probe the batch machinery, not the item logic: run it end to end through the real runner to its side effect, then confirm every value the later analysis depends on — treatment knob, run identity, cost — reached the persisted record through the expected channel. On the first failures read raw run logs, not the runner's status classifier, which infers causes from missing outputs. A cheap idempotent batch needs no gate.

## Halt And Resume

- Resume-first from artifacts that parse, pass schema, and match their recorded source/config/HEAD fingerprint; unverifiable means invalid.
- A cache-hit or fingerprint predicate must cover every value that shapes the artifact's content — the upstream input's content identity, caps, templates, model ids, config — never existence, mtime, or size alone; when adding a new output-shaping value, inspect the key's pre-image in the same change and assert the key moves when the value moves. Before re-running because an upstream input changed, invalidate intermediates whose predicate omits that input's identity: a regenerate over existence-keyed caches re-derives from the old input.
- Resubmit one invalid unit unless failures are broadly correlated, which is structural and halts the run.
- Treat halt→continue as normal operation.
- Treat tool-managed temp/cache output locations as ephemeral — they are garbage-collected on the tool's own schedule. Copy any artifact a pending or handed-off decision depends on into a project-owned durable path before relying on it later.
- Bounded-size cross-session indexes (memory index files) truncate silently past their read limit. Compare size against the limit periodically; before compacting, migrate index-only detail into per-item files, then verify links and no orphans.

## Sessions, Branches, Worktrees

- Sessions bind to their starting directory. Use the CLI's native relocation/resume mechanism; never copy transcript files.
- For a new worktree, relocate natively or write a handoff and start fresh. Re-integrate branches serially and re-verify after each merge.
- A conflict-free merge with a green build is evidence about text, not placement. When the base side restructured the surrounding code — regrouped sections, split modules, new per-variant containers — locate each merged addition in the new structure and confirm its scope still matches its container's: a global setting must not sit inside a variant-specific container, and no duplicate or orphaned copy may remain. A merge onto an unchanged layout needs only the ordinary green-state check.
- Mark superseded worktrees/handoffs dead so later resume cannot select them.
- After resume/clear/relocation, verify pwd, branch, and HEAD against the pinned handoff before acting.
- Attribute a parallel session's action (commit, branch, resource) by execution evidence in that session's own transcript, never by token mentions — shared handoff/memory files inject the same tokens into every session's context.

## Context Budget And Reset

Context growth is a property of the work, not of the host: over 1,075 sessions of 50+
requests across both CLIs it runs ~2,400 tokens per request (IQR 1,850-2,950), the two
hosts within 7% of each other (2,280 Claude, 2,450 Codex); the longest sessions (400+
requests) run lower, ~1,800. One budget therefore serves both, and what differs per host
is the price of ignoring it. The figure is a prior; the live session is measured below.

- **Automatic compaction fires only when the window is nearly full** — Claude at 84-87%
  (windows cluster at 200K and 1M), Codex at ~95% of the window its transcript records as
  `model_context_window` (258,400 on the sessions measured; a later Codex/model pair
  records 353,400 — read the value, never assume it). Cache read is charged per
  request against the whole loaded context, so leaving the reset to the host pays the
  maximum on every request before it. Measured: input is 92-94% of session cost and
  output 6-8%, at a 95-97% cache hit rate — the context is the bill, and uncached input
  is 0.0% of it.
- Reset deliberately instead. Cost per request falls ~4x from an 867K auto-compact point
  to 200K. The cost-theoretic optimum is ~65K, but it buys a compaction every ~32
  requests at 2-3 minutes each, so 150-250K is the working range and the tail below it is
  not worth chasing.
- **What bounds the budget is what survives the reset, not the token count.** A compaction
  keeps a ~14K summary plus 3-4 recent messages and discards the rest — unguided when it
  fires on its own. Anything already written to a file survives every reset, so the
  earliest safe threshold is the one where durable state is already on disk. That is what
  decouples cost from loss: without it, resetting more often loses proportionally more.
- Choose the mechanism by what is known, not by how large the context grew:

| Situation | Mechanism |
|---|---|
| Stage finished, what to keep is known | clear + dated handoff file — cheapest, and the loss is not a loss |
| Mid-stage, what to keep is known | write the handoff first, then compact with explicit instructions |
| Mid-stage, the needed detail is not yet identifiable | compact with instructions; a summary spans what a file cannot yet name |
| Original detail likely wanted later | clear, and record the transcript path in the handoff — transcripts persist on disk |
| The next question is unknown | new session plus messaging; only this keeps a round trip available |
| Growth is tool output | offload to subagents instead — measured ~20x cheaper (tier ~5x, context isolation ~4x) |
| The judgement trail itself is load-bearing | keep the session and pay the 2-5x resume |

- Measure rather than estimate: `agent-bios cost --context <transcript>` (the installed
  entry to `session-cost.py`) reads either
  host's transcript and reports current context, growth rate, compactions, and requests
  remaining against a budget. Codex records `model_context_window` directly; Claude does
  not, so the tool reports its observed auto-compaction point instead of assuming a
  window.

## Handoff Contract

Write for the next agent and re-verification, not narrative. Required content:

1. One-line current state.
2. Pinned worktree, branch, HEAD, upstream/merge-base, author tier, and active fallback/family collapse.
3. CONFIRMED claims whose cited command or anchored file evidence independently re-establishes them. Anchor code citations by stable symbol names (grep-re-derivable), not bare line numbers, which drift silently under later edits.
4. Separate PROPOSED/OPEN items, including inherited claims not re-verified this session.
5. Ordered next actions and the literal first command: model, orchestration authorization, and guide load for T1+.
6. Credentials only by env-var/gitignored slot; scrub secrets from excerpts and commands.

- Never record the hash of the commit that will contain the record itself — it is unstable by construction. Land substantive changes first and reference the settled hash from a follow-up commit, or use a relative phrase ("resume from the commit containing this handoff").
- A broken evidence anchor demotes CONFIRMED to PROPOSED. If pinned state fails or no trustworthy handoff exists, rebuild from source artifacts and write a fresh handoff before acting.
- Store handoffs in the working repo's isolated dated docs path, never this instruction-SSOT repo. Re-verify load-bearing claims on resume.

## Environment Binding (edit per environment)

This is the human-readable projection of concrete models/tools; `launch/agent-launch.toml` is the machine launch authority and parity checks keep them aligned. Re-probe when the binding is older than ~8 weeks or a newer observable model/tool changes the surface. Edit shipped defaults in the source repository; keep personal launch bindings in user-owned launcher configuration. Private installation stores an immutable release and preserves personal state. A new configured session resolves its bindings; existing session pins retain theirs.

Binding (2026-09-08):

| Slot | Binding | Notes |
|---|---|---|
| FRONTIER | Claude Fable 5.1 · GPT-6 Astra (read-only; max default; launcher may explicitly select Ultra) | bounded hardest decisions and verdicts |
| HELM | Claude Opus 5 (xhigh) · GPT-5.6 Sol (xhigh main; main Ultra requires explicit selection; bounded FRONTIER Ultra allowed) | standing main; Codex defaults bypass, explicit sandbox narrows |
| WORKHORSE | Claude Sonnet 5 (xhigh) · GPT-5.6 Terra (xhigh) | implementation and per-item judgment |
| SWEEP | Claude Haiku 4.5 (effort omitted) · GPT-5.6 Luna (max) | read-only; one explicit rule per item; not a rebind candidate |
| VERIFIER-A | plain `codex exec` deep pass — GPT-5.6 Sol at ultra effort, packet on stdin (`-c service_tier="fast"` as explicit fast opt-in) | strongest single reader; cross-family from a Claude main |
| VERIFIER-B | Claude Code ultracode workflow (keyword-opened, many-agent) | code/execution kind; fan-out counterpart |
| INDEPENDENT-PR-REVIEWER | Codex CLI | adversarial `gh pr diff` review |
| Claude relocation | EnterWorktree, `/cd`, `--worktree`; resume is directory-scoped | verified 2.1.207 |
| Codex relocation | `codex resume` (cwd-filtered; `--all` lifts), fork | verified 0.144.1 |
| Claude teammate | named mailbox continuation; completed-agent message may cold-rerun on main model | keep resident; avoid completed resume |
| Rate-limit fallback | OpenAI limited → VERIFIER-B (Anthropic workflow); Claude limited → VERIFIER-A (Codex exec) | record family collapse |

Codex direct-drive (verified 0.144.1, 2026-07-12):

- `codex-helm` defaults the HELM main to `--dangerously-bypass-approvals-and-sandbox`; explicit `--sandbox` wins in any flag order. Non-Ultra defaults native multi-agent off; explicit main Ultra defaults it on.
- HELM is instructed to dispatch tiers through internal `codex-run`, which pins model/effort/sandbox. FRONTIER uses a separate `gpt-6-astra`, read-only root: max by default, Ultra for divisible work, lower effort when cost/latency dominates. Nested multi-agent is enabled only for Ultra. Native `codex exec` spawn cannot pin role/effort.
- This is an instruction-backed, live-E2E-verified default, not a security boundary: main bypass and arbitrary expert `-c` remain available by design. `frontier.toml` pins the direct native FRONTIER default to max; launcher projections overwrite it from the selected tier.
- `codex-run` owns reach, stdin, schema, profiles, expert `-c`, channel preservation, and exit status. Keep it internal.
- `claude-run` is its Claude-side twin and the command a composable review contract names for a panel dispatch on that host. Same shape: prompt on stdin, final message on stdout, exit status mirrored, `--model`/`--effort` pinning the seat, everything it does not recognise forwarded to `claude`. It denies the mutating tools by default, which is not the OS-level sandbox `codex-run` gets — do not read the two defaults as equivalent guarantees. Dispatch whatever command the contract names rather than the bare CLI: only the adapter can report what the dispatch actually did, and a review with no receipt stays PROPOSED.

Dispatch packets:

| Target | Required packet / default |
|---|---|
| GPT-6 Astra FRONTIER | outcome, evidence, decision boundary, stop/verification; max default; read-only |
| GPT-5.6 Terra WORKHORSE | outcome, frozen scope/inputs, authority, done-when, evidence/report, escalation; xhigh |
| GPT-5.6 Luna SWEEP | exact search space, one rule per item, ambiguity behavior, stop, output; max; read-only; no architecture/debugging |
| Claude Opus 5 HELM | xhigh for agentic work; high minimum for sensitive judgment; lower only when bounded/cost-led |
| Claude Sonnet 5 WORKHORSE | exact scope, apply-to-all rules, tools, verification, report; xhigh default |
| Claude Haiku 4.5 SWEEP | one explicit rule per item, read-only; effort parameter omitted; ambiguity returned as an exception |

Use only task-relevant tools; parallelize independent calls. Worker report: `status`, `files_or_items_touched`, `evidence`, `verification`, `risks_or_escalations`. Official basis: OpenAI [model](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6), [migration](https://developers.openai.com/api/docs/guides/upgrading-to-gpt-5p6-sol), [prompting](https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6), [Codex models](https://learn.chatgpt.com/docs/models); Anthropic [subagents](https://code.claude.com/docs/en/sub-agents), [model effort](https://code.claude.com/docs/en/model-config).

## Evidence Base

Single owner of numeric defaults. Dates and workload scopes belong to each observation; recalibration updates this table and dependent inline thresholds.

| Evidence | Result / rule supported |
|---|---|
| Claude M=40 confirmation (2026-09-06), adopted by owner correction (2026-09-08) | Sonnet 5/xhigh child under Opus 5/xhigh: KEEP confirmed on five fresh paired blocks; modelled cost-to-parity saving 45.5%, lower bound 40.4%. This is scoped cost evidence, not a general quality or billing guarantee. |
| Owner tier correction (2026-09-08), Codex discovery cells incomplete | Terra/xhigh is the measured experimental effort adopted by owner instruction, not a confirmed Codex KEEP verdict. The two HELM parent seats stay unchanged; SWEEP is not a rebind candidate and remains one-rule-per-item read-only work. |
| 15 sessions, 3,758 requests, 10 switches | switches consumed 13.9% of uncached input; avoid unplanned switching |
| 285-call limit incident | 208 post-limit dispatches and 34/35 lost items; breaker default 3 |
| 99 staged reviews | 15.2% halted after most compute; resume-first |
| three-task delegation probe | batched worker 5 requests/$0.23 vs loaded FRONTIER direct 6/$3.35; cache TTL 5 min; completed resume cost 2–5× |
| two live delegation sessions | tiering saved ~3.3×; discarded prefixes made fresh respawn cheaper; unpinned reviewers inherited FRONTIER |
| Codex reach contrast | inherit ~16.5K vs hermetic ~8.7K tokens; schema and stdout/stderr contract verified |
| Codex native-spawn probe + HELM E2E | requested max/Ultra native children recorded xhigh/role null; separate read-only roots recorded max and Ultra successfully |
| 1,075 sessions of 50+ requests, both hosts (2026-08-16; the earlier 62-session top-by-size sample gave ~1,800-2,000) | context grows ~2,400 tok/request (IQR 1,850-2,950), hosts within 7%, ~1,800 in 400+-request sessions; auto-compaction fires at 84-95% of window, never earlier |
| 2 sessions decomposed by cost component (2026-08) | input 92-94% of cost, output 6-8%, cache hit 95-97%, uncached input 0.0%; an 867K→200K budget cuts cost per request ~4x |
| 4 dispatches over 3 situations built to trigger the Independence gate, plus a positive control (2026-09-01) | 0 spawns in the 3, 1 in the control; de-minimis absorbed all three and each inline answer was correct — a spawn mandate stated as always-fire did not fire |
| 60/150-file mechanical scan, N=5 on load-bearing cells (2026-09-02) | inline $0.627→$0.919; tier-pinned delegation $0.665→$0.921; unpinned +57-73%; an N=2 first reading of the same cells reported 19% and 36% savings that N=5 erased |
| fork cache reuse, both hosts (2026-09-02) | Claude same-model 98.9%, cross-model 0-26%; Codex 14-18% at any model (N=1 per Codex cell) — fork guidance is host-qualified |
