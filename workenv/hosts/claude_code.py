"""Claude Code: its command hooks, as its hooks and environment-variable references state them.

`SessionStart` runs with source `startup` for a new session and `compact` after the context was
compacted; `SubagentStart` runs when a child session begins; `UserPromptSubmit` runs in the
current session before each prompt. Each takes `hookSpecificOutput.additionalContext`. A hook
reads its session's id in `session_id`; a command the session runs reads it in
`CLAUDE_CODE_SESSION_ID`. Read 2026-09-27 against the references for version 2.1.278.
"""
from workenv.hosts import Adapter, Route

ADAPTER = Adapter(
    names=("claude-code",),
    routes={"new": Route("SessionStart", "startup"),
            "rehydrated": Route("SessionStart", "compact"),
            "child": Route("SubagentStart"),
            "current": Route("UserPromptSubmit")},
    session_env="CLAUDE_CODE_SESSION_ID",
)
