"""Codex: its command hooks, as its source states them (`codex-rs/hooks/src/schema.rs` and the
generated schemas beside it).

`SessionStart` runs with source `startup`, `resume`, `clear`, `compact` or `fork`, and
`UserPromptSubmit` before each prompt; each takes `hookSpecificOutput.additionalContext`, which
Codex adds as a developer message. A hook reads its session's id in `session_id`; a command the
session runs reads it in `CODEX_THREAD_ID`. Codex also has `SubagentStart`, but what its output
takes is not yet shown on the installed version, so no `child` route is declared and a child
delivery here reaches nothing until one is. Read 2026-09-27.
"""
from workenv.hosts import Adapter, Route

ADAPTER = Adapter(
    names=("codex",),
    routes={"new": Route("SessionStart", "startup"),
            "rehydrated": Route("SessionStart", "compact"),
            "current": Route("UserPromptSubmit")},
    session_env="CODEX_THREAD_ID",
)
