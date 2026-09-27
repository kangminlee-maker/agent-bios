"""A stand-in for an installed host, for the probe tests: run as `claude` or `codex` from a
directory put first on PATH, it takes the arguments a probe gives the real host and runs the
hooks it was given on the events the real host would fire, so the probe, the adapter's drive and
`hook.py` are the real code and only the host is not.

`FAKE_HOST_MODE` says how it behaves: `obey` (runs the hooks and repeats every probe marker it
was handed), `ignore` (runs no hook), `silent` (fails with nothing printed), `error` (reports an
error), `stale` (runs no hook and repeats a marker it made up), `nocompact` (Claude Code fails to
compact), `nolist` (Codex's app server answers nothing). `FAKE_HOST_VERSION` is the version it
reports and `FAKE_HOST_TRUST` (`trusted` or not) whether Codex would run a session hook. Every
run appends to `FAKE_HOST_LOG` its host, its arguments, the hooks it was configured with, and
whether nested-session variables and the hook's job reached it.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tomllib

MARKER = "agent-bios probe marker: "
MODE = os.environ.get("FAKE_HOST_MODE", "obey")
NESTED = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "CODEX_THREAD_ID")


def log(argv: list[str], groups: dict | None) -> None:
    with open(os.environ["FAKE_HOST_LOG"], "a", encoding="utf-8") as out:
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
        return MARKER + "0000000000000000"
    found = [line for text in context for line in text.splitlines() if line.startswith(MARKER)]
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
    kept = pathlib.Path(os.environ["FAKE_HOST_LOG"]).with_name("sessions")
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


def codex(argv: list[str]) -> int:
    groups = flags(argv)
    log(argv, groups or None)
    if argv == ["--version"]:
        print(f"codex-cli {os.environ['FAKE_HOST_VERSION']}")
        return 0
    trusted = os.environ.get("FAKE_HOST_TRUST") == "trusted"
    if "app-server" in argv:
        if MODE == "nolist":
            return 0
        own = {"eventName": "stop", "command": "the person's own hook", "enabled": True,
               "trustStatus": "trusted", "isManaged": False}
        rows = [own, dict(own),
                {"eventName": "stop", "command": "a managed hook", "enabled": True,
                 "trustStatus": "untrusted", "isManaged": True}]
        rows += [{"eventName": event[0].lower() + event[1:], "command": handler["command"],
                  "enabled": True, "trustStatus": "trusted" if trusted else "untrusted",
                  "isManaged": False}
                 for event, listed in groups.items() for group in listed
                 for handler in group["hooks"]]
        for line in sys.stdin:
            message = json.loads(line)
            if message.get("id") == 1:
                print(json.dumps({"id": 1, "result": {}}), flush=True)
            elif message.get("id") == 2:
                print(json.dumps({"id": 2, "result": {"data": [{"hooks": rows}]}}), flush=True)
        return 0
    if MODE in ("silent", "error"):
        return 1
    run = MODE == "obey" and trusted
    context = (fire(groups, "SessionStart", "startup", os.getcwd())
               + fire(groups, "UserPromptSubmit", None, os.getcwd())) if run else []
    pathlib.Path(argv[argv.index("-o") + 1]).write_text(answer(context))
    return 0


if __name__ == "__main__":
    sys.exit({"claude": claude, "codex": codex}[pathlib.Path(sys.argv[0]).name](sys.argv[1:]))
