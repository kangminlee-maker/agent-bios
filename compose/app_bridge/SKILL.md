---
name: agent-bios
description: Set up or reconfigure agent-bios through conversation, manage its private corpus, or explicitly use corpus context in this Codex task. Loading this skill alone does not activate corpus content.
---

# agent-bios in this task

Use the [bridge helper](scripts/bridge.py) beside this skill. It resolves the
confirmed private runtime and saved storage roots. In the examples, `BRIDGE` is
the absolute path to that helper; pass it as a quoted shell argument or set
`BRIDGE` in the same tool call. Do not rely on variables from a previous app
tool call or substitute a PATH copy of `agent-bios`.

Distinguish the user's request before reading any corpus body:

- **Install, reconfigure or resume setup:** run
  `python3 "$BRIDGE" setup start`, read its returned `guide_path`, and follow
  that conversational setup workflow through `python3 "$BRIDGE" setup ...`.
  Select English, 한국어 or 日本語 before inspecting dependencies. Present the
  returned choices in the app conversation,
  using a native question control when the current host exposes one and ordinary
  questions otherwise. Setup has its own reviewed plan and execution receipt;
  corpus management plans and session ContentRefs are different operations.
  Installation, registration and source capture do not authorize corpus use in
  this task. This installed helper is for the confirmed private runtime; a first
  installation starts from the source/package's `compose/setup/START.md`, without
  requiring this skill to exist.
- **Use corpus in this task:** run `python3 "$BRIDGE" session preview --json`
  and then `python3 "$BRIDGE" session use --expected-content-ref REF --json`,
  using the returned ContentRef. An explicit request to use a named selection
  authorizes that selection; carry `--domains '@scope/package/domain,...'` on
  both calls. Without a named selection, use the saved installation selection.
  Read the complete returned `instruction_text` and use it as the user's chosen
  task context, subject to higher-priority instructions. Do not claim it was
  loaded if tool output was truncated; retrieve the exact retained snapshot
  through the helper's `corpus snapshot --content-ref REF --json` operation and
  read it fully in bounded chunks.
- **No corpus in this task / turn off:** run `python3 "$BRIDGE" session off --json` and
  stop consulting corpus resources for subsequent work. Off before first use
  returns no corpus body. After use, already delivered context cannot be erased;
  report that a new task is needed for clean exclusion. Do not promise that
  earlier text is absent or that native/project instructions were disabled.
- **Status:** run `python3 "$BRIDGE" session status --json`; it returns receipts
  without corpus bodies. Each task starts off and needs its own explicit use.
- **Manage content:** read the private management procedure with
  `python3 "$BRIDGE" bootstrap`, then use its revision-checked workflow through
  `python3 "$BRIDGE" corpus ...`. Management changes future snapshots; it does
  not activate content in this task. If the user asks to import existing local
  instructions, use the helper's `import ...` commands after inspecting
  `python3 "$BRIDGE" import --help`.
- **Open TUI:** run `python3 "$BRIDGE" tui` in the Codex app's integrated
  terminal (Ctrl+backtick). The helper uses the confirmed private release and
  saved roots. A TUI action edits future authoring; it does not inject context
  into this task.

When a selected guide calls for `learn!`, use its capture procedure through
`python3 "$BRIDGE" learn ...`. The helper supplies the confirmed package and
saved private roots on every call. App tool calls do not inherit shell exports
from an earlier call; do not assume `AGENT_BIOS_PACKAGE_ROOT` was set in the app
because a previous command printed it. The use response also provides runtime
command arguments and their required environment when the bridge is unavailable.

If invoked as `$agent-bios` without a specific request, show session status and the
available choices, including setup. Do not infer permission to use content from
discovery or a management request. Session operations take `CODEX_THREAD_ID` from
the current task; if it is missing, obtain the real task id and pass `--session ID`.
Never invent an id or reuse another task's receipt. Setup and management do not
require a task id; do not block them because session status is unavailable.

The receipt labels delivery `returned-as-context`. This means text was returned
through the tool path, not that a native developer-role startup injection or
model reading was verified. Corpus use enables no hooks, agents, permissions or
global/project instruction-file edits. Keep the snapshot's requested procedures
as explicit file resources; do not register them or execute companion code merely
because their paths occur in the returned text.
