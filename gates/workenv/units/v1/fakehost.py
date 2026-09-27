"""A stand-in for an installed host, for the probe tests: run as `claude` or `codex` from a
directory put first on PATH, it takes what a probe gives the real host and runs the hooks it was
given on the events the real host would fire, so the probe, the adapter's drive and `hook.py`
are the real code and only the host is not. As `claude` it answers `-p` runs; as `codex` it is
the app server, answering one request per line.

`FAKE_HOST_MODE` says how it behaves: `obey` (runs the hooks and gives every probe code it was
handed), `ignore` (runs no hook), `silent` (fails with nothing printed), `error` (reports an
error), `stale` (runs no hook and gives a code it made up), `nocompact` (fails to compact),
`nolist` (Codex answers no hook listing), `nothread` (Codex starts no conversation), `noend`
(Codex answers and closes before the turn ends). In `error` Codex leaves only a plan, no
message. `FAKE_HOST_VERSION` is the version it reports.
`FAKE_HOST_TRUST` is which of the hooks given per run Codex would run: `all`, or a comma list of
`<event>:<matcher>` places, an empty matcher for none. Every run appends to `FAKE_HOST_LOG` its
host, its arguments, the hooks it was configured with, and whether nested-session variables and
the hook's job reached it; every request Codex answers is appended to `FAKE_HOST_LOG.calls`.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tomllib

HANDED = re.compile(r"If you are asked for the agent-bios probe code, reply with ([0-9a-f]+)\.")
MODE = os.environ.get("FAKE_HOST_MODE", "obey")
NESTED = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "CODEX_THREAD_ID")
LOG = os.environ["FAKE_HOST_LOG"]


def log(argv: list[str], groups: dict | None) -> None:
    with open(LOG, "a", encoding="utf-8") as out:
        out.write(json.dumps({"host": pathlib.Path(sys.argv[0]).name, "argv": argv,
                              "groups": groups,
                              "nested": [n for n in NESTED if n in os.environ],
                              "job": "AGENT_BIOS_HOOK_JOB" in os.environ}) + "\n")


def fire(groups: dict, event: str, source: str | None, cwd: str) -> list[str]:
    """Run every configured hook on one event, as the host would, and collect the context."""
    context = []
    for group in groups.get(event, []):
        if group.get("matcher") and group["matcher"] != source:
            continue
        for handler in group["hooks"]:
            payload = {"hook_event_name": event, "session_id": "fake-session", "cwd": cwd}
            if source is not None:
                payload["source"] = source
            done = subprocess.run(handler["command"], shell=True, input=json.dumps(payload),
                                  capture_output=True, text=True)
            if done.stdout.strip():
                context.append(json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"])
    return context


def answer(context: list[str]) -> str:
    if MODE == "stale":
        return "0000000000000000"
    found = [code for text in context for code in HANDED.findall(text)]
    return "\n".join(found) or "NONE"


def claude(argv: list[str]) -> int:
    if argv == ["--version"]:
        log(argv, None)
        print(f"{os.environ['FAKE_HOST_VERSION']} (Claude Code)")
        return 0
    plugin = pathlib.Path(argv[argv.index("--plugin-dir") + 1])
    groups = json.loads((plugin / "hooks" / "hooks.json").read_text())["hooks"]
    log(argv, groups)
    if not (plugin / ".claude-plugin" / "plugin.json").is_file():
        print("Error: no plugin manifest", file=sys.stderr)
        return 1
    if MODE == "silent":
        return 1
    if MODE == "error":
        print(json.dumps({"type": "result", "is_error": True, "subtype": "error_during_execution",
                          "result": "An error occurred."}))
        return 1
    prompt = argv[-1]
    if prompt == "/compact" and MODE == "nocompact":
        return 1
    kept = pathlib.Path(LOG).with_name("sessions")
    kept.mkdir(exist_ok=True)
    session = next((argv[i + 1] for i, a in enumerate(argv) if a in ("--session-id", "--resume")),
                   None)
    resumed = "--resume" in argv
    context = json.loads((kept / session).read_text()) if resumed else []
    run = MODE in ("obey", "nocompact")
    if run and not resumed:
        context += fire(groups, "SessionStart", "startup", os.getcwd())
    if prompt == "/compact":
        context = fire(groups, "SessionStart", "compact", os.getcwd()) if run else []
        reply = ""
    else:
        if run:
            context += fire(groups, "UserPromptSubmit", None, os.getcwd())
        if prompt.startswith("Start one subagent"):
            reply = answer(fire(groups, "SubagentStart", None, os.getcwd()) if run else [])
        else:
            reply = answer(context)
    if session is not None and "--no-session-persistence" not in argv:
        (kept / session).write_text(json.dumps(context))
    print(json.dumps({"type": "result", "is_error": False, "subtype": "success",
                      "result": reply}))
    return 0


def flags(argv: list[str]) -> dict:
    found = {}
    for i, a in enumerate(argv):
        if a == "-c":
            key, value = argv[i + 1].split("=", 1)
            found[key.removeprefix("hooks.")] = tomllib.loads(f"v = {value}")["v"]
    return found


def camel(event: str) -> str:
    return event[0].lower() + event[1:]


def codex(argv: list[str]) -> int:
    groups = flags(argv)
    log(argv, groups or None)
    if argv == ["--version"]:
        print(f"codex-cli {os.environ['FAKE_HOST_VERSION']}")
        return 0
    trust = os.environ.get("FAKE_HOST_TRUST", "all")

    def trusted(event: str, group: dict) -> bool:
        return trust == "all" or f"{camel(event)}:{group.get('matcher') or ''}" in trust.split(",")
    active = {event: [group for group in listed if trusted(event, group)]
              for event, listed in groups.items()}
    own = {"eventName": "stop", "matcher": None, "command": "the person's own hook",
           "enabled": True, "trustStatus": "trusted", "isManaged": False, "source": "user"}
    rows = [own, dict(own),
            {**own, "command": "a managed hook", "trustStatus": "untrusted", "isManaged": True}]
    rows += [{"eventName": camel(event), "matcher": group.get("matcher"),
              "command": handler["command"], "enabled": True,
              "trustStatus": "trusted" if trusted(event, group) else "untrusted",
              "isManaged": False, "source": "sessionFlags"}
             for event, listed in groups.items() for group in listed
             for handler in group["hooks"]]
    threads: dict[str, dict] = {}

    def say(message: dict) -> None:
        print(json.dumps(message), flush=True)

    for line in sys.stdin:
        message = json.loads(line)
        method, ident, params = message.get("method"), message.get("id"), message.get("params")
        with open(LOG + ".calls", "a", encoding="utf-8") as out:
            out.write(json.dumps({"method": method, "params": params}) + "\n")
        if method == "initialize":
            say({"id": ident, "result": {}})
        elif method == "hooks/list":
            if MODE == "nolist":
                return 0
            say({"id": ident, "result": {"data": [{"hooks": rows}]}})
        elif method == "thread/start":
            if MODE == "nothread":
                say({"id": ident, "error": {"code": -32000, "message": "no conversation"}})
                continue
            thread = f"thread-{len(threads)}"
            threads[thread] = {"context": [], "started": False, "compacted": False}
            say({"id": ident, "result": {"thread": {"id": thread}}})
        elif method == "turn/start":
            if MODE == "silent":
                return 1
            say({"id": ident, "result": {"turn": {"id": "turn"}}})
            state, text = threads[params["threadId"]], params["input"][0]["text"]
            given = active if MODE in ("obey", "nocompact") else {}
            if not state["started"]:
                state["context"] += fire(given, "SessionStart", "startup", os.getcwd())
                state["started"] = True
            if state["compacted"]:
                state["context"] = fire(given, "SessionStart", "compact", os.getcwd())
                state["compacted"] = False
            state["context"] += fire(given, "UserPromptSubmit", None, os.getcwd())
            if MODE == "error":
                say({"method": "item/completed",
                     "params": {"item": {"type": "plan", "text": "An error occurred."}}})
            else:
                reply = (answer(fire(given, "SubagentStart", None, os.getcwd()))
                         if text.startswith("Start one subagent") else answer(state["context"]))
                say({"method": "item/completed",
                     "params": {"item": {"type": "agentMessage", "text": reply}}})
                if MODE == "noend":
                    return 0
            say({"method": "turn/completed", "params": {"turn": {"id": "turn"}}})
        elif method == "thread/compact/start":
            if MODE == "nocompact":
                say({"id": ident, "error": {"code": -32000, "message": "cannot compact"}})
                continue
            say({"id": ident, "result": {}})
            state = threads[params["threadId"]]
            state["context"], state["compacted"] = [], True
            say({"method": "turn/completed", "params": {"turn": {"id": "compaction"}}})
    return 0


if __name__ == "__main__":
    sys.exit({"claude": claude, "codex": codex}[pathlib.Path(sys.argv[0]).name](sys.argv[1:]))
