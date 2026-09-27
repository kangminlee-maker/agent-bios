"""Claude Code: its command hooks, as its hooks and environment-variable references state them.

`SessionStart` runs with source `startup` for a new session and `compact` after the context was
compacted; `SubagentStart` runs when a child session begins; `UserPromptSubmit` runs in the
current session before each prompt. Each takes `hookSpecificOutput.additionalContext`. A hook
reads its session's id in `session_id`; a command the session runs reads it in
`CLAUDE_CODE_SESSION_ID`. Read 2026-09-27 against the references for version 2.1.278.

A probe runs `claude -p` with the adapter's hooks in a plugin of its own (`--plugin-dir`) and no
setting sources, so the only hooks configured are the adapter's and the person's settings are
neither read nor changed. A new, current or child session is one run that keeps no session; a
child is asked for through the session's subagent tool. A rehydrated session is three runs of one
kept session: a first prompt, `/compact`, and the question asked after it.
"""
from __future__ import annotations

import json
import pathlib
import uuid

from workenv.hosts import Adapter, Route


def reply(done) -> tuple[str | None, str]:
    """The reply of one `-p` run printed as JSON, or None and what the host reported instead."""
    if done is None:
        return None, "Claude Code could not be started or ran out of time."
    try:
        printed = json.loads(done.stdout)
    except ValueError:
        return None, f"Claude Code exited {done.returncode} without a result."
    if not isinstance(printed, dict) or printed.get("is_error") or \
            not isinstance(printed.get("result"), str):
        return None, f"Claude Code exited {done.returncode} with an error: {done.stdout[:400]}"
    return printed["result"], ""


def drive(recipient: str, executable: str, command: str, workdir: pathlib.Path,
          environ: dict):
    from workenv.hosts import probes

    groups = ADAPTER.groups(command)
    plugin = workdir / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps(
        {"name": "agent-bios-probe", "version": "1.0.0",
         "description": "The hooks of one agent-bios probe."}), encoding="utf-8")
    (plugin / "hooks").mkdir()
    (plugin / "hooks" / "hooks.json").write_text(json.dumps({"hooks": groups}), encoding="utf-8")
    hooks = [probes.hook(event, command, True) for event in groups]
    base = [executable, "-p", "--plugin-dir", str(plugin), "--setting-sources", "",
            "--output-format", "json"]
    if recipient == "rehydrated":
        session = str(uuid.uuid4())
        for step in (["--session-id", session, "Reply OK."], ["--resume", session, "/compact"]):
            answered, note = reply(probes.ran(base + step, workdir, environ))
            if answered is None:
                return probes.Run(None, hooks, f"Before the question: {note}")
        answered, note = reply(probes.ran(base + ["--resume", session, probes.ASK], workdir,
                                          environ))
        return probes.Run(answered, hooks, note)
    ask = probes.ASK_CHILD if recipient == "child" else probes.ASK
    answered, note = reply(probes.ran(base + ["--no-session-persistence", ask], workdir, environ))
    return probes.Run(answered, hooks, note)


ADAPTER = Adapter(
    names=("claude-code",),
    routes={"new": Route("SessionStart", "startup"),
            "rehydrated": Route("SessionStart", "compact"),
            "child": Route("SubagentStart"),
            "current": Route("UserPromptSubmit")},
    session_env="CLAUDE_CODE_SESSION_ID",
    binary="claude",
    nested=("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT"),
    drive=drive,
)
