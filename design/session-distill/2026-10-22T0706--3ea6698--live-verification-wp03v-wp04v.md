---
created_at: 2026-10-22T07:06:00+09:00
head: 3ea6698
kind: review
---

# Live verification of WP-03 and WP-04 (WP-03v, WP-04v)

Run by the lead on 2026-10-22 between 01:10 and 02:45 KST against the integrated tree
(feat/distill-redesign at aa2d8c6, then the gate fixes up to 3ea6698). Cells lived under
`/Users/Shared/agent-bios-probe-cells` (outside HOME). Every Claude call declared
`--max-output-tokens`; the Claude token reached children only through `CLAUDE_RUN_TOKEN_FILE`.
After the runs, no file under the cell roots held an Anthropic token prefix, no Codex `auth.json`
copy remained under the cell roots, and no host process was left running.

## WP-04v — Codex 0.163.0, seat codex:gpt-6-luna/medium (4 live calls)

| Item | Result |
| --- | --- |
| (a) hermetic rendering, model-free | pass — no `# AGENTS.md instructions` and no canary under the hermetic overrides; instructions `[]`, skill roots `@CODEX_HOME/skills/.system`, the four built-in skills; the control without `project_doc_max_bytes=0` loads `@CWD/AGENTS.md` |
| (b) canary | pass — adapter: 6 frames, nothing unattested, reconciled, seat observed main and warm-up `gpt-6-luna`, effort `medium`, warm-up 11,750 input / 0 output, receipt with 13 evidence keys; through dispatch and the gate: ok, codes `[]`, effort host-reported, coverage complete |
| (c) trace channel closed | pass — the adapter warns about `RUST_LOG`; frames 0; the gate refuses `MODEL_UNATTESTED` |
| (d) stream aborted by SIGTERM | pass — the gate refuses `COMPLETION_INCOMPLETE` (exit 143, no `turn.completed`, aborted stream); the main request is unresolved; the ledger records the call failed with measured 11,750 and provisional 15,721 |
| (e) HTTP-transport coverage | pass at e6bcd5f — helper and gate agree: WebSocket clean complete; HTTP with a retry warning unknown; WebSocket beside a `codex.api_request` row unknown. At aa2d8c6 the gate still applied its own pre-WP-04 reduction and read the last two as complete |

The retained captures of (b)–(d) were re-judged with the fixed gate; their verdicts did not change.

## WP-03v — Claude Code 2.1.304 (15 live calls)

Standalone calls used `claude-haiku-5-5/low` (what loads and what a tool may reach depends on the
host and profile, not the model); calls through dispatch used `claude-sonnet-5-5/medium`, the
small Claude seat stage S6 pins.

| Item | Result |
| --- | --- |
| 3 live detection under a loading profile | pass — with plants in a cell, the capture names each: the ancestor `CLAUDE.md` (Project, also in `ancestor_exposure`), the configuration home's `CLAUDE.md` (User), auto memory `MEMORY.md` (AutoMem), the working directory's `CLAUDE.md` (Project), skill `plant-skill`, MCP server `plant-mcp`; the gate names them `CONTEXT_UNDECLARED`. The same in-cell plants under hermetic: context empty, the gate accepts |
| 3 hooks | pass on the second form — hooks that print and touch a marker file: both markers exist, two `hook_success` records, `context.hooks` = SessionStart, UserPromptSubmit, the gate names them. A hook that prints nothing leaves no transcript record (first form, `command: "true"`) |
| 4 tool boundary, standalone hermetic-producing | pass — init tools `Read`, `StructuredOutput`; permission mode `dontAsk`; Read inside the manifest and through an inside symlink allowed; an outside path, a `../` traversal and an outside symlink refused; Grep, Glob and Bash refused as tools not available; the canary is in no transcript or capture |
| 4 through dispatch | pass — ok, codes `[]`; inside read allowed, outside and traversal refused; the cell root afterwards holds only the planted outside file |
| 5 through dispatch and the gate | pass — judge accepted with the seat observed equal to the seat sent; inherit refused `PROFILE_INHERITED`; an output cap of 16 refused `COMPLETION_INCOMPLETE` naming the cap; every cell deleted after its usage was captured |

## Defects the live runs found, and their fixes

1. **The gate read Codex captures with its own copy of the reduction** (WP-04v (e)). Fixed at
   e6bcd5f: the gate calls the capture helper's `responses`, `completions`, `join` and `attempts`;
   seat policy stays in the gate. Decision D-20261022-7ddd72 described this before it was true.
2. **An output-cap overrun tripped the provider breaker** (WP-03v item 5). Claude Code 2.1.304 ends
   such a call as `is_error`, `terminal_reason 'api_error'`, text "API Error: Claude's response
   exceeded the 16 output token maximum…", not as `stop_reason 'max_tokens'`. The breaker read it as an
   unrecognised provider stop with no reset time and refused every later Claude call of the run.
   Fixed at 5999501 and tightened at 3ea6698: the exact sentence, with N equal to the call's declared
   cap and the structured fields present, fails only that call; any other api_error still stops the
   provider. Re-checked live: the capped call is refused by name and the next call in the same run is
   accepted.
3. **A sub-agent's warm-up and compaction were judged against the main seat** (review of the fix
   branch). Fixed at 3ea6698: the seat comes from the send's child identity, not the request kind.
4. **A SIGKILLed Codex wrapper left its temp home, with an `auth.json` copy, in `$TMPDIR`** (one
   from 2026-10-21 07:53 was found and removed). Fixed on wp/04-codex-tmp-sweep (0e33570): temp homes
   carry the owner PID, and each start removes this user's homes whose owner is gone and which are
   older than 24 hours.

## Measured value: Claude host allowance (hermetic)

Observed main-request input (input + cache read + cache creation) on four hermetic calls through
dispatch: 3,886 (judge), 3,876, 3,878, 3,877 (minimal payload). The planned subtraction "observed
tokens minus packet and schema bytes" came out negative (−638 to −828), because bytes overstate
tokens. The recorded allowance is the observed input itself, 3,886 tokens: it includes the packet,
so it overstates the host's share, which is the safe direction for admission.
`session-distill/seats.json` `hosts.claude.host_allowance.hermetic` carries it. The producing
profile has no allowance slot and stays unmeasured.

## Rulings made during the runs

- Hooks: the detector is not extended. A hook that prints nothing is invisible to the transcript, so
  hooks under a loading profile are a lower bound. Hermetic calls load no settings hooks, and a call
  under a loading profile is always refused `PROFILE_INHERITED`.
- The built-in context a clean inherit run reports on 2.1.304 is recorded here, not declared in
  `seats.json`: agents Explore, Plan, claude, general-purpose, statusline-setup; skills claude-api,
  code-review, dataviz, fewer-permission-prompts, init, keybindings-help, loop, plugin-authoring,
  run, schedule, security-review, simplify, update-config, workflow-authoring.
- Effort stays provenance only (plan S-6); a child answering at another effort is recorded as
  unverified, not refused.
