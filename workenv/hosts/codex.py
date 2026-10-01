"""Codex: its command hooks, as its source and the schemas its binary carries state them.

`SessionStart` runs with source `startup`, `resume`, `clear`, `compact` or `fork`; after a
conversation is compacted it runs again, with source `compact`, before the next turn.
`UserPromptSubmit` runs before each prompt, and `SubagentStart` when a child agent begins. Each
takes `hookSpecificOutput.additionalContext`, which Codex adds as a developer message (the
`session-start`, `user-prompt-submit` and `subagent-start` command output schemas in the 0.157.1
binary). A hook reads its session's id in `session_id`; a command the session runs reads it in
`CODEX_THREAD_ID`. Read 2026-09-27.

At launch, `-c developer_instructions=` gives the session its developer instructions, replacing
any the person configured, and the session keeps them through compaction; a child started with no
role takes them too. `-c agents.<name>.description=` and `-c agents.<name>.config_file=` define a
role for the session alone, and a role's own `developer_instructions` replace the session's in its
child. Measured on 0.157.1 on 2026-09-28: the instructions went in whole to 120,000 characters,
where a hook's output is cut at about 2,500 tokens. A child started with no role is of the role
`default`, so defining `default` for the session decides what such a child starts from. A role
whose `developer_instructions` are absent, empty or only whitespace does not replace the session's:
its child starts from the session's instructions (measured the same day, one child each). What
Codex would give a session on its own, its effective developer instructions and the roles it
defines, is what its app server's `config/read` answers for the working directory; a role this
installation ships and the person did not define is read from `codex/agents/`.

A probe drives Codex through its app server (`codex app-server --stdio`), which runs the same
conversations a person does without a terminal: it lists every hook Codex would run, starts a
conversation that keeps no session (`ephemeral`) in a read-only sandbox, and asks it. A child is
asked for through Codex's subagent tool; a rehydrated session is one the probe compacts first
(`thread/compact/start`). `codex exec` is not used: it cannot compact, and on an ephemeral run it
cannot start a child. The hooks are per-run `-c hooks.<event>` values. Codex runs a hook given
that way only once the person has reviewed and trusted it in `/hooks`, by its place (event, group
and handler) and a hash of it; the probe never trusts one for them, and the configuration it
records says, for every hook Codex lists (the person's own included), whether Codex would run it.

A turn Codex gives up on ends with an `error` notification it will not retry and a
`turn/completed` whose turn `failed`, each carrying its message; where the provider refused, the
message is the provider's JSON error (measured on 0.158.0 on 2026-09-30, a configured model the
account is not offered). A probe whose turn said nothing keeps that reason in what it observed.

A probe counts a turn only where Codex ends it `completed` (the `TurnStatus` of the app-server
schema 0.159.2 generates: `completed`, `interrupted`, `failed`, `inProgress`); one it ends
otherwise gave no reply. The first turn of a rehydrated probe only gives the conversation
something to compact, so how it ended does not matter. It counts a compaction only where Codex
accepted the request, reported the compaction (a `contextCompaction` item, or the older
`thread/compacted`) and completed that turn: a compaction Codex accepts and then fails ends its
turn `failed`, and a session asked after it would answer from the uncompacted conversation, so
the probe asks nothing then (r9-1, design record
`2026-10-01T2134--3551ccb--v1-restructure-design.md`). Every notification it reads is about its
own conversation and turn: Codex names the thread each turn, item and error notification is
about, and the turn each item is in, and another conversation, such as a subagent's, may be
reported on the same server (r10-0). A turn ends where Codex completes the turn the probe started,
an agent message is the probe's where it is in that turn, and a compaction counts where the turn
Codex completes is the one it reported the compaction in.
"""
from __future__ import annotations

import json
import pathlib
import queue
import subprocess
import threading
import time
import tomllib

from workenv.hosts import Adapter, Configured, HostError, Kind, Route

SHIPPED = pathlib.Path(__file__).resolve().parents[2] / "codex" / "agents"
# The fields of a role file that a kind states apart from its settings.
OWN = ("name", "description", "developer_instructions")


def toml(value) -> str:
    """A configuration value as the inline TOML `-c` takes."""
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key} = {toml(item)}" for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(toml(item) for item in value) + "]"
    if isinstance(value, str):
        # A TOML basic string: every character as itself but the quote, the backslash and the
        # control characters, which TOML admits only escaped.
        return '"' + "".join(f"\\u{ord(c):04x}" if c in '"\\' or ord(c) < 0x20 or ord(c) == 0x7f
                             else c for c in value) + '"'
    return json.dumps(value)


def flags(command: str) -> list[str]:
    """The per-run configuration that gives Codex the adapter's hooks; a person reviews the same
    hooks by opening Codex with them and trusting them in `/hooks`."""
    return [part for event, groups in ADAPTER.groups(command).items()
            for part in ("-c", f"hooks.{event}={toml(groups)}")]


def launch(directory: pathlib.Path, text: str | None, kinds: dict) -> list[str]:
    arguments = [] if text is None else ["-c", f"developer_instructions={toml(text)}"]
    for name, kind in kinds.items():
        role = {**kind.settings, "name": name, "description": kind.description,
                "developer_instructions": kind.instructions}
        path = directory / f"{name}.toml"
        path.write_text("".join(f"{key} = {toml(value)}\n" for key, value in role.items()),
                        encoding="utf-8")
        arguments += ["-c", f"agents.{name}.description={toml(kind.description)}",
                      "-c", f"agents.{name}.config_file={toml(str(path))}"]
    return arguments


def hooked(command: str, directory: pathlib.Path) -> list[str]:
    return flags(command)


def role(path: pathlib.Path, description: str | None = None) -> Kind:
    """A role file as a kind: its instructions, and every other field as it is."""
    fields = tomllib.loads(path.read_text(encoding="utf-8"))
    return Kind(description=description or fields.get("description", ""),
                instructions=fields.get("developer_instructions", ""),
                settings={key: item for key, item in fields.items() if key not in OWN})


def reason(error) -> str:
    """Codex's words for an error, or the provider's own where Codex passes on its JSON."""
    said = error.get("message") if isinstance(error, dict) else None
    if not isinstance(said, str):
        return "no reason given"
    try:
        passed = json.loads(said)
    except ValueError:
        return said
    inner = passed.get("error") if isinstance(passed, dict) else None
    return inner["message"] if isinstance(inner, dict) and isinstance(inner.get("message"), str) \
        else said


def completed(ended: dict | None) -> bool:
    """Whether a `turn/completed` notification says Codex completed the turn."""
    return ended is not None and ended.get("params", {}).get("turn", {}).get("status") == \
        "completed"


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
        # What Codex last said failed a turn, in its own words, where it gave up on it.
        self.failed: str | None = None
        # The conversation the probe acts on, and the turn it waits for. Every turn, item and
        # error notification names its thread, and each item its turn (app-server schema v2), so
        # a notification about another conversation or another turn is not the probe's.
        self.thread: str | None = None
        self.turn_id: str | None = None
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
        """The first message `wanted` accepts, keeping the agent's messages seen on the way and
        the reason Codex gave for a turn it gave up on, or None where the server closed or the
        probe's time ran out."""
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
            params = message.get("params", {})
            if "method" in message and self.thread is not None and \
                    params.get("threadId") != self.thread:
                continue
            item = params.get("item", {})
            if message.get("method") == "item/completed" and item.get("type") == "agentMessage" \
                    and params.get("turnId") == self.turn_id:
                self.said.append(item.get("text", ""))
            if message.get("method") == "error" and not params.get("willRetry"):
                self.failed = reason(params.get("error"))
            if message.get("method") == "turn/completed" and \
                    params.get("turn", {}).get("status") == "failed":
                self.failed = reason(params["turn"].get("error"))
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

    def ended(self, thread: str, text: str) -> dict | None:
        """The `turn/completed` that ended the turn this starts in the conversation, however it
        ended, or None where it did not end."""
        self.said, self.thread, self.turn_id = [], thread, None
        started = self.call("turn/start", {"threadId": thread,
                                           "input": [{"type": "text", "text": text}]})
        if started is None:
            return None
        self.turn_id = started.get("turn", {}).get("id")
        return self.until(lambda message: message.get("method") == "turn/completed" and
                          message["params"].get("turn", {}).get("id") == self.turn_id)

    def turn(self, thread: str, text: str) -> list[str] | None:
        """What the agent said in one turn Codex completed, or None where the turn did not end
        or ended otherwise."""
        return list(self.said) if completed(self.ended(thread, text)) else None

    def compacted(self, thread: str) -> bool:
        """Whether Codex compacted the conversation: it accepted the request, reported the
        compaction in this conversation, and completed the turn it reported it in."""
        self.thread, self.turn_id = thread, None
        if self.call("thread/compact/start", {"threadId": thread}) is None:
            return False
        reported = set()

        def ends(message: dict) -> bool:
            params = message.get("params", {})
            if message.get("method") == "thread/compacted" or (
                    message.get("method") == "item/completed" and
                    params.get("item", {}).get("type") == "contextCompaction"):
                reported.add(params.get("turnId"))
            return message.get("method") == "turn/completed"
        ended = self.until(ends)
        return completed(ended) and ended["params"]["turn"].get("id") in reported

    def close(self) -> None:
        self.process.kill()
        self.process.wait()


def configured(executable: str, workdir: pathlib.Path, environ: dict) -> Configured:
    from workenv.hosts import probes

    try:
        server = Server(executable, [], workdir, environ, probes.TIMEOUT)
    except OSError as error:
        raise HostError("Codex could not be started.") from error
    try:
        started = server.call("initialize", {"clientInfo": {"name": "agent-bios", "version": "1"},
                                             "capabilities": {"experimentalApi": True}})
        server.send({"method": "initialized"})
        read = (server.call("config/read", {"cwd": str(workdir), "includeLayers": False})
                if started is not None else None)
    finally:
        server.close()
    config = read.get("config") if isinstance(read, dict) else None
    if not isinstance(config, dict):
        raise HostError("Codex did not answer what configuration a session starts with.")
    native = config.get("developer_instructions")
    if native is not None and not isinstance(native, str):
        raise HostError("Codex did not say what developer instructions a session starts with.")
    kinds = {name: role(pathlib.Path(entry["config_file"]), entry.get("description"))
             for name, entry in (config.get("agents") or {}).items()
             if isinstance(entry, dict) and isinstance(entry.get("config_file"), str)}
    for path in sorted(SHIPPED.glob("*.toml")) if SHIPPED.is_dir() else ():
        kinds.setdefault(path.stem, role(path))
    return Configured(native=native or "", kinds=kinds)


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


def drive(recipient: str, executable: str, command: str, given: list[str],
          workdir: pathlib.Path, environ: dict):
    from workenv.hosts import probes

    try:
        server = Server(executable, [*hooked(command, workdir), *given], workdir, environ,
                        probes.TIMEOUT)
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
        route = ADAPTER.routes[recipient]
        note = "" if route.carrier != "hook" or runs(rows, route, command) else (
            "Codex would not run the adapter's hook on this route: it is not trusted until the "
            "person reviews it in /hooks.")
        opened = server.call("thread/start", {"cwd": str(workdir), "ephemeral": True,
                                              "sandbox": "read-only", "approvalPolicy": "never"})
        if opened is None:
            return probes.Run(None, hooks, " ".join(filter(None, (
                "Codex did not start a conversation.", note))))
        thread = opened["thread"]["id"]

        def failed() -> str:
            return f"Codex ended the turn with an error: {server.failed}" if server.failed else ""
        # The first turn only gives the conversation something to compact; how it ended does
        # not matter, but the compaction must be one Codex confirmed.
        if recipient == "rehydrated" and (server.ended(thread, "Reply OK.") is None or
                                          not server.compacted(thread)):
            return probes.Run(None, hooks, " ".join(filter(None, (
                "Before the question: Codex did not compact the conversation.", failed(),
                note))))
        said = server.turn(thread, probes.ASK_CHILD if recipient == "child" else probes.ASK)
        return probes.Run("\n".join(said) if said else None, hooks,
                          " ".join(filter(None, ("" if said else failed(), note))))
    finally:
        server.close()


ADAPTER = Adapter(
    names=("codex",),
    routes={"new": Route("SessionStart", "startup", carrier="launch"),
            "rehydrated": Route("SessionStart", "compact", carrier="launch"),
            "current": Route("UserPromptSubmit", carrier="hook"),
            "child": Route("SubagentStart", carrier="definition")},
    session_env="CODEX_THREAD_ID",
    binary="codex",
    nested=("CODEX_THREAD_ID",),
    skip=("--dangerously-bypass-approvals-and-sandbox",),
    launch=launch,
    hooked=hooked,
    configured=configured,
    plain="default",
    limit=(2_500, "bytes"),
    drive=drive,
)
