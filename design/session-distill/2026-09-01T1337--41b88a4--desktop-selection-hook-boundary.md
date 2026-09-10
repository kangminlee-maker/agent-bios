---
created_at: 2026-09-01T13:37:14+09:00
head: 41b88a4
kind: design
supersedes: 2026-09-01T1335--41b88a4--desktop-selection-default.md
---

# Desktop selection default — hook boundary correction

The revised minimum in the superseded design stands: the default desktop path is one
user-scoped, explicitly selected onboarding skill that reads the installer-owned allowed set,
obtains confirmation, calls `agent-bios onboard --domains ...`, and tells the user to create a
new task. A plugin and lifecycle hook are not required for the first version.

One deferred-hook sentence was too strong. A read-only `SessionStart` hook cannot truthfully
identify the selection whose instructions the task loaded. Codex builds the `AGENTS.md`
instruction chain before the hook runs, and another process can apply a different selection
between those events. Reading `corpus-status.json` from the hook would then return the new disk
state, not the task's effective start-time state.

If a status hook is added later, it may say only:

> Currently recorded agent-bios selection: `<domains>`. This may differ from the instructions
> loaded when this task started. Run the onboarding skill to change the persisted selection;
> create a new task afterward.

It must still match `SessionStart` source `startup` only, return the notice through JSON
`systemMessage`, remain read-only and advisory, and include the non-managed hook trust/review
step. It must not claim effective-context identity until a supported task-start snapshot or
effective-instruction identifier exists.
