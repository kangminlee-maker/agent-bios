"""Codex: its command hooks, as its source states them (`codex-rs/hooks/src/schema.rs` and the
generated schemas beside it).

`SessionStart` runs with source `startup`, `resume`, `clear`, `compact` or `fork`, and
`UserPromptSubmit` before each prompt; each takes `hookSpecificOutput.additionalContext`, which
Codex adds as a developer message. A hook reads its session's id in `session_id`; a command the
session runs reads it in `CODEX_THREAD_ID`. Codex also has `SubagentStart`, but what its output
takes is not yet shown on the installed version, so no `child` route is declared and a child
delivery here reaches nothing until one is. Read 2026-09-27.

A probe gives `codex exec` the hook as a per-run `-c hooks.<event>` value and keeps no session
(`--ephemeral`). Codex runs a hook given that way only once the person has reviewed and trusted
it in `/hooks`; the probe never trusts one for them, and the configuration it records says, for
every hook Codex lists (the person's own included), whether Codex would run it. A rehydrated
session cannot be reached by a run: `codex exec` does not compact a conversation, so only a
person can bring one about.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import threading

from workenv.hosts import Adapter, Route

LISTED = 60


def listed(executable: str, flags: list[str], workdir: pathlib.Path, environ: dict):
    """Every hook Codex lists for the working directory under these flags, as the probe records
    them, or None where it lists none: through its app server, which runs no model."""
    from workenv.hosts import probes

    messages = [{"id": 1, "method": "initialize",
                 "params": {"clientInfo": {"name": "agent-bios", "version": "1"},
                            "capabilities": {"experimentalApi": True}}},
                {"method": "initialized"},
                {"id": 2, "method": "hooks/list", "params": {"cwds": [str(workdir)]}}]
    try:
        server = subprocess.Popen([executable, *flags, "app-server", "--stdio"], cwd=workdir,
                                  env=environ, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return None
    timer = threading.Timer(LISTED, server.kill)
    timer.start()
    answer = None
    try:
        server.stdin.write("".join(json.dumps(message) + "\n" for message in messages))
        server.stdin.flush()
        for line in server.stdout:
            message = json.loads(line)
            if message.get("id") == 2:
                answer = message
                break
    except (OSError, ValueError):
        pass
    finally:
        timer.cancel()
        server.kill()
        server.wait()
    try:
        rows = answer["result"]["data"][0]["hooks"]
    except (KeyError, IndexError, TypeError):
        return None
    hooks = []
    for row in rows:
        hook = probes.hook(row["eventName"], row["command"] or "",
                           bool(row["enabled"]) and (row["trustStatus"] == "trusted"
                                                     or bool(row["isManaged"])))
        if hook not in hooks:
            hooks.append(hook)
    return hooks


def flags(recipient: str, command: str) -> list[str]:
    """The per-run configuration that gives Codex the hook on the route to one recipient; a
    person reviews the same hook by opening Codex with it and trusting it in `/hooks`."""
    route = ADAPTER.routes[recipient]
    matcher = "" if route.source is None else f"matcher = {json.dumps(route.source)}, "
    return ["-c", f"hooks.{route.event}=[{{{matcher}hooks = [{{type = \"command\", "
                  f"command = {json.dumps(command)}}}]}}]"]


def drive(recipient: str, executable: str, command: str, workdir: pathlib.Path,
          environ: dict):
    from workenv.hosts import probes

    if recipient == "rehydrated":
        return probes.Run(None, [], "codex exec does not compact a conversation, so a "
                          "rehydrated session is reached only when a person compacts one.",
                          outcome="unsupported")
    route, given = ADAPTER.routes[recipient], flags(recipient, command)
    hooks = listed(executable, given, workdir, environ)
    if hooks is None:
        return probes.Run(None, [], "Codex did not list the hooks it would run.",
                          outcome="no_response")
    ours = probes.hook(route.event[0].lower() + route.event[1:], command, True)
    note = ("" if ours in hooks else "Codex would not run the probe's hook: it is not trusted "
            "until the person reviews it in /hooks.")
    last = workdir / "reply.txt"
    done = probes.ran([executable, "exec", "--ephemeral", "--skip-git-repo-check",
                       "-s", "read-only", *given, "-o", str(last), probes.ASK], workdir, environ)
    if done is None or not last.is_file():
        return probes.Run(None, hooks, " ".join(filter(None, ("codex exec left no reply.",
                                                               note))))
    return probes.Run(last.read_text(encoding="utf-8"), hooks, note)


ADAPTER = Adapter(
    names=("codex",),
    routes={"new": Route("SessionStart", "startup"),
            "rehydrated": Route("SessionStart", "compact"),
            "current": Route("UserPromptSubmit")},
    session_env="CODEX_THREAD_ID",
    binary="codex",
    nested=("CODEX_THREAD_ID",),
    drive=drive,
)
