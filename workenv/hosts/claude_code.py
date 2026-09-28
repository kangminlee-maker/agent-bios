"""Claude Code: its command hooks, as its hooks and environment-variable references state them.

`SessionStart` runs with source `startup` for a new session and `compact` after the context was
compacted; `SubagentStart` runs when a child session begins; `UserPromptSubmit` runs in the
current session before each prompt. Each takes `hookSpecificOutput.additionalContext`. A hook
reads its session's id in `session_id`; a command the session runs reads it in
`CLAUDE_CODE_SESSION_ID`. Read 2026-09-27 against the references for version 2.1.278.

At launch, `--append-system-prompt-file` adds a file's text to the session's system prompt, after
the person's own instructions, and the session keeps it through compaction; it does not reach a
child. `--agents` defines subagents for the session alone, each with its prompt, model and
effort, and a definition given that way wins over an installed one of the same name. Measured on
2.1.283 on 2026-09-28: the appended text went in whole to 120,000 characters, where a hook's
output is cut at 10,000 (a fixed threshold in the binary, with no setting). A subagent Claude
Code would load on its own is the project's `.claude/agents/<name>.md`, else the person's in
their configuration directory, else, for a kind this installation ships, `claude/agents/`.

A probe runs `claude -p` with the adapter's hooks in a plugin of its own (`--plugin-dir`) and no
setting sources, so the only hooks configured are the adapter's and the person's settings are
neither read nor changed. A new, current or child session is one run that keeps no session; a
child is asked for through the session's subagent tool. A rehydrated session is one run given
three prompts in turn as a stream (`--input-format stream-json`): a first prompt, `/compact`,
and the question asked after it. It is one process because launch instructions are given to a
process: a second run given them again would be handed them anew, not keep them.
"""
from __future__ import annotations

import json
import os
import pathlib
import queue
import subprocess
import threading
import time
import uuid

from workenv.hosts import Adapter, Configured, Kind, Route

SHIPPED = pathlib.Path(__file__).resolve().parents[2] / "claude" / "agents"


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


def launch(directory: pathlib.Path, text: str | None, kinds: dict) -> list[str]:
    arguments = []
    if text is not None:
        path = directory / "instructions.md"
        path.write_text(text, encoding="utf-8")
        arguments += ["--append-system-prompt-file", str(path)]
    if kinds:
        path = directory / "agents.json"
        path.write_text(json.dumps(
            {name: {**kind.settings, "description": kind.description,
                    "prompt": kind.instructions} for name, kind in kinds.items()},
            ensure_ascii=False), encoding="utf-8")
        arguments += ["--agents", str(path)]
    return arguments


def hooked(command: str, directory: pathlib.Path) -> list[str]:
    """The adapter's hooks, in a plugin of their own."""
    plugin = directory / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps(
        {"name": "agent-bios", "version": "1.0.0",
         "description": "The hooks agent-bios gives a session it starts."}), encoding="utf-8")
    (plugin / "hooks").mkdir()
    (plugin / "hooks" / "hooks.json").write_text(json.dumps({"hooks": ADAPTER.groups(command)}),
                                                 encoding="utf-8")
    return ["--plugin-dir", str(plugin)]


def value(text: str):
    """One frontmatter value: a flow list as a list, a quoted string unquoted, else the text."""
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return [value(item) for item in text[1:-1].split(",") if item.strip()]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


def defined(path: pathlib.Path) -> Kind | None:
    """A subagent's definition file as a kind: its frontmatter's description, its body as the
    instructions, and every other field as it is. None where it has no frontmatter."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in (line.strip() for line in lines[1:]):
        return None
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    fields = {}
    for line in lines[1:end]:
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, rest = line.partition(":")
            fields[key.strip()] = value(rest)
    fields.pop("name", None)
    description = fields.pop("description", "")
    return Kind(description=description if isinstance(description, str) else "",
                instructions="\n".join(lines[end + 1:]).strip() + "\n", settings=fields)


def configured(executable: str, workdir: pathlib.Path, environ: dict) -> Configured:
    home = pathlib.Path(environ.get("CLAUDE_CONFIG_DIR") or
                        pathlib.Path(environ.get("HOME", os.path.expanduser("~"))) / ".claude")
    kinds: dict[str, Kind] = {}
    for where in (workdir / ".claude" / "agents", home / "agents", SHIPPED):
        for path in sorted(where.glob("*.md")) if where.is_dir() else ():
            kind = defined(path)
            if kind is not None:
                kinds.setdefault(path.stem, kind)
    return Configured(native=None, kinds=kinds)


def conversed(argv: list[str], workdir: pathlib.Path, environ: dict,
              prompts: list[str]) -> tuple[str | None, str]:
    """The reply to the last of `prompts`, given one at a time to one run that takes them as a
    stream, or None and what the host reported instead. A prompt is given only once the one
    before it was answered, so a run that fails early is never asked the rest."""
    from workenv.hosts import probes

    try:
        process = subprocess.Popen(argv, cwd=workdir, env=environ, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return None, "Claude Code could not be started."
    lines: queue.Queue = queue.Queue()

    def read() -> None:
        for line in process.stdout:
            lines.put(line)
        lines.put(None)
    threading.Thread(target=read, daemon=True).start()
    deadline = time.monotonic() + probes.TIMEOUT

    def result() -> dict | None:
        while (left := deadline - time.monotonic()) > 0:
            try:
                line = lines.get(timeout=left)
            except queue.Empty:
                return None
            if line is None:
                return None
            try:
                printed = json.loads(line)
            except ValueError:
                continue
            if isinstance(printed, dict) and printed.get("type") == "result":
                return printed
        return None
    try:
        for step, prompt in enumerate(prompts, 1):
            before = "" if step == len(prompts) else "Before the question: "
            try:
                process.stdin.write(json.dumps({"type": "user", "message": {
                    "role": "user", "content": prompt}}) + "\n")
                process.stdin.flush()
            except OSError:
                return None, f"{before}Claude Code stopped taking prompts."
            printed = result()
            if printed is None:
                return None, f"{before}Claude Code gave no result to {prompt!r}."
            if printed.get("is_error"):
                return None, f"{before}Claude Code reported an error on {prompt!r}."
        answered = printed.get("result")
        return (answered, "") if isinstance(answered, str) else (
            None, "Claude Code's last result carried no reply.")
    finally:
        process.kill()
        process.wait()


def drive(recipient: str, executable: str, command: str, given: list[str],
          workdir: pathlib.Path, environ: dict):
    from workenv.hosts import probes

    hooks = [probes.hook(event, command, True) for event in ADAPTER.groups(command)]
    base = [executable, "-p", *hooked(command, workdir), "--setting-sources", "", *given]
    if recipient == "rehydrated":
        answered, note = conversed(
            base + ["--input-format", "stream-json", "--output-format", "stream-json",
                    "--verbose", "--session-id", str(uuid.uuid4())],
            workdir, environ, ["Reply OK.", "/compact", probes.ASK])
        return probes.Run(answered, hooks, note)
    ask = probes.ASK_CHILD if recipient == "child" else probes.ASK
    answered, note = reply(probes.ran(base + ["--output-format", "json",
                                              "--no-session-persistence", ask], workdir, environ))
    return probes.Run(answered, hooks, note)


ADAPTER = Adapter(
    names=("claude-code",),
    routes={"new": Route("SessionStart", "startup", carrier="launch"),
            "rehydrated": Route("SessionStart", "compact", carrier="launch"),
            "child": Route("SubagentStart", carrier="definition"),
            "current": Route("UserPromptSubmit", carrier="hook")},
    session_env="CLAUDE_CODE_SESSION_ID",
    binary="claude",
    nested=("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT"),
    launch=launch,
    hooked=hooked,
    configured=configured,
    limit=(10_000, "characters"),
    drive=drive,
)
