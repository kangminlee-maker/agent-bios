"""Codex: its command hooks, as its source and the schemas its binary carries state them.

`SessionStart` runs with source `startup`, `resume`, `clear`, `compact` or `fork`; after a
conversation is compacted it runs again, with source `compact`, before the next turn.
`UserPromptSubmit` runs before each prompt, and `SubagentStart` when a child agent begins. Each
takes `hookSpecificOutput.additionalContext`, which Codex adds as a developer message (the
`session-start`, `user-prompt-submit` and `subagent-start` command output schemas in the 0.157.1
binary). A hook reads its session's id in `session_id`; a command the session runs reads it in
`CODEX_THREAD_ID`. Read 2026-09-27.

A probe drives Codex through its app server (`codex app-server --stdio`), which runs the same
conversations a person does without a terminal: it lists every hook Codex would run, starts a
conversation that keeps no session (`ephemeral`) in a read-only sandbox, and asks it. A child is
asked for through Codex's subagent tool; a rehydrated session is one the probe compacts first
(`thread/compact/start`). `codex exec` is not used: it cannot compact, and on an ephemeral run it
cannot start a child. The hooks are per-run `-c hooks.<event>` values. Codex runs a hook given
that way only once the person has reviewed and trusted it in `/hooks`, by its place (event, group
and handler) and a hash of it; the probe never trusts one for them, and the configuration it
records says, for every hook Codex lists (the person's own included), whether Codex would run it.
"""
from __future__ import annotations

import json
import pathlib
import queue
import subprocess
import threading
import time

from workenv.hosts import Adapter, Route


def toml(value) -> str:
    """A configuration value as the inline TOML `-c` takes."""
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key} = {toml(item)}" for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(toml(item) for item in value) + "]"
    return json.dumps(value)


def flags(command: str) -> list[str]:
    """The per-run configuration that gives Codex the adapter's hooks; a person reviews the same
    hooks by opening Codex with them and trusting them in `/hooks`."""
    return [part for event, groups in ADAPTER.groups(command).items()
            for part in ("-c", f"hooks.{event}={toml(groups)}")]


class Server:
    """Codex's app server over standard input and output, for the length of one probe."""

    def __init__(self, executable: str, given: list[str], workdir: pathlib.Path, environ: dict,
                 timeout: float):
        self.process = subprocess.Popen([executable, *given, "app-server", "--stdio"],
                                        cwd=workdir, env=environ, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True)
        self.messages: queue.Queue = queue.Queue()
        self.deadline = time.monotonic() + timeout
        self.asked, self.said = 0, []
        threading.Thread(target=self.read, daemon=True).start()

    def read(self) -> None:
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except ValueError:
                continue
        self.messages.put(None)

    def send(self, message: dict) -> bool:
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
        except OSError:
            return False
        return True

    def until(self, wanted) -> dict | None:
        """The first message `wanted` accepts, keeping the agent's messages seen on the way, or
        None where the server closed or the probe's time ran out."""
        while (left := self.deadline - time.monotonic()) > 0:
            try:
                message = self.messages.get(timeout=left)
            except queue.Empty:
                return None
            if message is None:
                return None
            if "id" in message and "method" in message:
                # A request of the server's, such as an approval: a probe grants nothing.
                self.send({"id": message["id"], "error": {"code": -32601,
                                                          "message": "not granted"}})
                continue
            item = message.get("params", {}).get("item", {})
            if message.get("method") == "item/completed" and item.get("type") == "agentMessage":
                self.said.append(item.get("text", ""))
            if wanted(message):
                return message
        return None

    def call(self, method: str, params: dict) -> dict | None:
        """The result of one request, or None where it failed or went unanswered."""
        self.asked += 1
        asked = self.asked
        if not self.send({"id": asked, "method": method, "params": params}):
            return None
        answer = self.until(lambda message: message.get("id") == asked and
                            "method" not in message)
        return None if answer is None or "error" in answer else answer.get("result")

    def turn(self, thread: str, text: str) -> list[str] | None:
        """What the agent said in one turn, or None where the turn did not end."""
        self.said = []
        if self.call("turn/start", {"threadId": thread,
                                    "input": [{"type": "text", "text": text}]}) is None:
            return None
        ended = self.until(lambda message: message.get("method") == "turn/completed")
        return None if ended is None else list(self.said)

    def close(self) -> None:
        self.process.kill()
        self.process.wait()


def recorded(rows: list[dict]) -> list[dict]:
    """Every hook Codex lists, as a host configuration records it: whether Codex would run it is
    whether it is enabled and either trusted or managed."""
    from workenv.hosts import probes

    hooks = []
    for row in rows:
        hook = probes.hook(row["eventName"], row["command"] or "",
                           bool(row["enabled"]) and (row["trustStatus"] == "trusted"
                                                     or bool(row["isManaged"])))
        if hook not in hooks:
            hooks.append(hook)
    return hooks


def runs(rows: list[dict], route: Route, command: str) -> bool:
    """Whether Codex would run the adapter's hook on this route, found by its own place."""
    event = route.event[0].lower() + route.event[1:]
    return any(row["source"] == "sessionFlags" and row["eventName"] == event and
               row["matcher"] == route.source and row["command"] == command and
               row["enabled"] and row["trustStatus"] == "trusted" for row in rows)


def drive(recipient: str, executable: str, command: str, workdir: pathlib.Path,
          environ: dict):
    from workenv.hosts import probes

    try:
        server = Server(executable, flags(command), workdir, environ, probes.TIMEOUT)
    except OSError:
        return probes.Run(None, [], "Codex could not be started.")
    try:
        started = server.call("initialize", {"clientInfo": {"name": "agent-bios", "version": "1"},
                                             "capabilities": {"experimentalApi": True}})
        server.send({"method": "initialized"})
        listed = (server.call("hooks/list", {"cwds": [str(workdir)]}) if started is not None
                  else None)
        try:
            rows = listed["data"][0]["hooks"]
        except (KeyError, IndexError, TypeError):
            return probes.Run(None, [], "Codex did not list the hooks it would run.")
        hooks = recorded(rows)
        note = "" if runs(rows, ADAPTER.routes[recipient], command) else (
            "Codex would not run the adapter's hook on this route: it is not trusted until the "
            "person reviews it in /hooks.")
        opened = server.call("thread/start", {"cwd": str(workdir), "ephemeral": True,
                                              "sandbox": "read-only", "approvalPolicy": "never"})
        if opened is None:
            return probes.Run(None, hooks, " ".join(filter(None, (
                "Codex did not start a conversation.", note))))
        thread = opened["thread"]["id"]
        if recipient == "rehydrated" and (
                server.turn(thread, "Reply OK.") is None or
                server.call("thread/compact/start", {"threadId": thread}) is None or
                server.until(lambda message: message.get("method") == "turn/completed") is None):
            return probes.Run(None, hooks, " ".join(filter(None, (
                "Before the question: Codex did not compact the conversation.", note))))
        said = server.turn(thread, probes.ASK_CHILD if recipient == "child" else probes.ASK)
        return probes.Run("\n".join(said) if said else None, hooks, note)
    finally:
        server.close()


ADAPTER = Adapter(
    names=("codex",),
    routes={"new": Route("SessionStart", "startup"),
            "rehydrated": Route("SessionStart", "compact"),
            "current": Route("UserPromptSubmit"),
            "child": Route("SubagentStart")},
    session_env="CODEX_THREAD_ID",
    binary="codex",
    nested=("CODEX_THREAD_ID",),
    drive=drive,
)
