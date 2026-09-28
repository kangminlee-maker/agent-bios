---
created_at: 2026-09-28T09:30:59+09:00
head: d107ec0
kind: design
plan: 2026-09-26T1404--f065835--development-plan.json
---

# What each host takes, through which channel: the delivery limits compared

The [hook-delivery design](2026-09-28T0708--6c4f2c1--v1-slice4-hook-delivery-design.md) found
that Claude Code 2.1.283 spills a hook's large output to a file. The owner asked for an option
that takes more than 10,000 characters directly, or a way to cover more with less. Splitting one
delivery across several hooks was set aside as awkward.

Then the owner set a further bar: channels that differ by host raise the cost of keeping them. So
this record compares every channel on both hosts before one is chosen.

All runs are on this machine, 2026-09-28, in this repository: Claude Code 2.1.283 (main
`claude-opus-5-5`) and Codex 0.157.1 (`gpt-6-astra`). Tools and raw outputs are in the
workbench's `team-env-20260920/v1-slice4-use/`:

- `context-size/`: `e1.sh`–`e5.sh`, `m12.sh`, `idx_claude.sh`, `claude-hook-spill-finding.md`;
- `manual/`: `codex_limits.py`, `codex_devinst.py`, `idx_codex.py`, `review_child_isolation.py`.

Each result below is measured unless marked **code** (read from the binary or a schema) or
**not measured**.

## The channels

| Channel | Claude Code 2.1.283 | Codex 0.157.1 |
| --- | --- | --- |
| **Hook output**: `additionalContext` at `SessionStart`, `UserPromptSubmit` or `SubagentStart` | Whole up to 10,000 characters. **code**: `CLo = 1e4`, and no call on these paths passes another threshold or reads a setting. Measured above it: 30,177 characters at `SessionStart` became a 2 KB preview and a path; 11,983 characters at `UserPromptSubmit` and at `SubagentStart` became about 2,300 characters of preview and a path. | Whole up to about 2,500 **tokens** by default. Measured: 5,980 characters whole. 11,983 characters (3,007 tokens) and 30,177 characters (7,573 tokens) each became about 10,070 characters: head and tail, with "…N tokens truncated…" in the middle and a path at the end. `additionalContextLimit = 0` turns this off for one hook (**code**, schema); **not measured**, because it changes the hook's hash and needs the person's review. |
| **Launch-time system prompt** | `--append-system-prompt-file`: 30,177 characters whole (+9,557 tokens); 119,984 characters whole (+42,040 tokens). | `-c developer_instructions=…`: 30,177 characters whole (+6,317 tokens); 119,984 characters whole (+26,633 tokens). |
| **Session-scoped child definitions** | `--agents`: a tier redefined as its shipped prompt plus 30,177 characters. Its child answered the last-line marker. The tier's model and effort were honored. It took precedence over `~/.claude/agents/`. | Agent roles in configuration: **not measured**. |
| **Native repository files** (not a V1 delivery channel: native files are preserved) | `CLAUDE.md`'s import loads this repository's `AGENTS.md` whole: 42,636 characters, 14.8k tokens. | `AGENTS.md` is cut at the default 32 KiB (`project_doc_max_bytes`): 32,320 of 42,864 bytes. |
| **An index through a hook, the bodies in files** | A 785-character index at `SessionStart` said to read two files (29,897 characters) in full before the first reply. On a first prompt of "Reply OK.", the model read both files whole before replying, **3 of 3**. | The same index through the trusted hook, under the default threshold: both files read whole (`cat`) before replying, **3 of 3**. The next prompt grew by about 6k tokens, the files' size. |

The same 30,177 characters are about 9.6k tokens to Claude Code and about 6.3k to Codex. **A
character budget and a token budget are not the same limit**, and Korean text moves the ratio
further.

## Where each channel reaches

| Channel | Claude Code | Codex |
| --- | --- | --- |
| Hook output | the session that ran the hook | the session that ran the hook. A child spawned with `fork_turns: all`, Codex's default, gets it in the copied turns; one spawned with `none` does not |
| Launch-time system prompt | **the main session only**: a `general-purpose` child's transcript had no trace of it | **every child**, forked or not |
| Child definitions | only the redefined tier's children | not measured |
| After compaction | Hook output is part of the messages compaction summarizes, so it is gone. A system prompt is not part of those messages and should stay; **not measured** in an interactive session. | Hook output: the same as Claude Code. `developer_instructions` is configuration and should stay; **not measured** |

## What follows for one uniform method

- **No channel is both uniform and whole.** On both hosts, the only channel with the same reach
  (the session that ran it, plus a fixed child route) is the hook. On Claude Code its output is
  capped at 10,000 characters with no switch.
- **Whole content needs different channels per host.** On Claude Code it takes the launch-time
  system prompt and `--agents`. On Codex it takes a hook with `additionalContextLimit = 0`. The
  launch channels do not reach alike: Codex's `developer_instructions` reaches every child, so it
  would break the owner's review rule (`D-20260928-4a1cc3`).
- **An index through a hook is the same on both hosts, and was read whole.** The index was under a
  thousand characters. Both hosts read the files whole before the first reply, 6 of 6.
  - It keeps one mechanism: the same events, the same hook, the same files. Rehydration hands the
    index again at `compact`; a tier child gets it at `SubagentStart`; a review child gets
    nothing.
  - It fits Codex's default threshold, so `D-20260928-cc0692` (turn the threshold off) and the
    person's re-review it needs would no longer be needed.
  - The cost is that the bodies reach the model only by its reading them. Six runs with a
    one-line first prompt do not show what happens under a task-first prompt or a long session.
  - What the owner records changes. The adapter hands an index and the paths of stored bodies,
    and the host's own transcript then shows each file read. `received` would state the index;
    the read is observed separately, which is where C07 already keeps use.

## Decided 2026-09-28: a channel per host (`D-20260928-fad6ef`)

The owner chose the channels that carry the environment whole. This closes the uniform index
method, because whole content must not depend on the model choosing to read.

Each adapter declares its channel per recipient, as data. The owner stays host-neutral: it
composes, records and observes the same way whatever the channel.

| Recipient | Claude Code | Codex |
| --- | --- | --- |
| `new` | the start composes before launch and passes `--append-system-prompt-file`, with `--session-id` chosen by the start so the link is opened before launch | `SessionStart` startup hook, `additionalContextLimit = 0` (`D-20260928-cc0692`) |
| `rehydrated` | nothing, if an interactive session keeps the appended system prompt through compaction. Measured before the route relies on it; otherwise the hook at `compact`, capped at 10,000 characters | `SessionStart` compact hook, uncapped |
| `child`, a tier seat | `--agents`: each tier's shipped definition (prompt, model, effort) plus the environment | `SubagentStart` hook for the tier's `agent_type`, uncapped |
| `child`, review or other | nothing; the appended system prompt does not reach it (E5) | nothing from the hook. The review dispatch passes `fork_turns: none` (`D-20260928-7d8bbb`) |
| `current`, mid-session | `UserPromptSubmit` hook, up to 10,000 characters | `UserPromptSubmit` hook, uncapped |

Open before building:

- **Claude Code's compaction.** Whether one Claude Code process keeps its appended system prompt
  through compaction. `-p` starts a process per call, so it cannot show this. A single process
  driven with `--input-format stream-json` can.
- **A large mid-session delivery on Claude Code.** A `current` delivery above 10,000 characters has
  no whole channel there: the hook is the only channel that opens mid-session. What it does then is
  not decided.
- **What Codex's `SubagentStart` input carries.** Whether it carries the child's kind
  (`agent_type`) and how the child was forked is observed before the child route relies on it. A
  tier child forked with `all` already holds the parent's hook output in its copied turns, so
  delivering again would duplicate it.
- **Probes.** The probes qualify a route under the channel a session uses:
  - Claude Code's `new` and `child` routes are probed again through the launch channels;
  - Codex's four routes are probed again with `additionalContextLimit = 0`, after the person
    reviews the changed hooks in `/hooks`.
