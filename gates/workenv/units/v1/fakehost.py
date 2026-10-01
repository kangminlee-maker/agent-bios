"""A stand-in for an installed host, for the probe tests: run as `claude` or `codex` from a
directory put first on PATH, it takes what a probe gives the real host and answers from it as the
real host does, so the probe, the adapter's drive and `hook.py` are the real code and only the
host is not. As `claude` it answers `-p` runs, one prompt in its arguments or a stream of them on
standard input; as `codex` it is the app server, answering one request per line.

What it answers from, as the hosts were measured to on 2026-09-28:

  - a session: its launch instructions (Claude Code's `--append-system-prompt-file`, Codex's
    `-c developer_instructions`), which compaction keeps, and the output of the hooks it ran,
    which compaction drops but for the hook run on compaction itself;
  - a child: the definition of the kind it was started as (Claude Code's `--agents`, Codex's
    `-c agents.<name>.config_file`) and the output of its `SubagentStart` hooks. A Codex child of
    no defined kind takes the session's launch instructions instead, and a Claude Code child
    never takes them.

`FAKE_HOST_MODE` says how it behaves: `obey` (takes everything it is handed), `ignore` (takes
nothing: runs no hook and reads neither launch instructions nor definitions), `nolaunch` (runs
its hooks but reads neither), `forget` (drops its launch instructions on compaction), `silent`
(fails with nothing printed), `error` (reports an error), `stale` (gives a code it made up),
`nocompact` (refuses to compact at once), `compactfails` (accepts the compaction, then fails
it: Codex an `error` and a `failed` compaction turn, Claude Code an error result),
`compactquiet` (accepts the compaction and does not compact: Codex completes the turn reporting
no compaction, Claude Code gives a result with no `compact_boundary`), `compactitemfails` (Codex
reports a compaction item, does not compact, and fails the turn), `crosscompact` (Codex reports
another conversation's compaction and completed turn, then fails this one's), `stalecompact`
(Codex reports a compaction under an earlier turn, does not compact, and completes the turn),
`saidinterrupted`
(Codex says its reply, then ends the turn `interrupted`), `crossturn` and `staleturn` (asked the
probe's question, Codex reports the reply in another conversation's completed turn, or in an
earlier turn of this one, then completes this turn replying `NONE`), `nolist` (Codex answers
no hook listing), `nothread` (Codex
starts no conversation), `noend` (Codex answers and closes before the turn ends), `refuse`
(Codex gives the turn up as it did on 2026-09-30 for a model the account is not offered: an
`error` it will not retry, then a `failed` turn carrying the same provider error), `refusenoend`
(that `error`, then it closes), `refusequiet` (the `failed` turn alone), `refusefirst` (gives up
a conversation's first turn as `refuse` does, then answers as `obey` does) and `retrysilent` (an
`error` it retries, then a turn that completes saying nothing). In `error` Codex leaves only a
plan, no message. `FAKE_HOST_VERSION` is the version it reports, and
`FAKE_HOST_NATIVE` the developer instructions Codex is configured with, which its `config/read`
answers and a session given none at launch starts with, and `FAKE_HOST_ROLES` the roles the person
defined (JSON: name to description and config_file), which a run's own `-c agents.*` override. As
Codex does, a role whose developer instructions are absent or blank leaves its child the
session's.
`FAKE_HOST_TRUST` is which of the hooks given per run Codex would run: `all`, or a comma list of
`<event>:<matcher>` places, an empty matcher for none. Every run appends to `FAKE_HOST_LOG` its
host, its arguments, the hooks it was configured with, and whether nested-session variables and
the hook's job reached it; every prompt Claude Code is given and every request Codex answers is
appended to `FAKE_HOST_LOG.calls`.
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
KIND = re.compile(r'Start one subagent of type "([^"]+)"')
MODE = os.environ.get("FAKE_HOST_MODE", "obey")
NESTED = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "CODEX_THREAD_ID")
LOG = os.environ["FAKE_HOST_LOG"]
# Whether the host runs its hooks, and whether it reads what it was given at launch.
HOOKS = MODE in ("obey", "nocompact", "compactfails", "compactquiet", "compactitemfails",
                 "crosscompact", "stalecompact", "saidinterrupted", "crossturn", "staleturn",
                 "nolaunch", "forget", "refusefirst")
LAUNCH = MODE in ("obey", "nocompact", "compactfails", "compactquiet", "compactitemfails",
                  "crosscompact", "stalecompact", "saidinterrupted", "crossturn", "staleturn",
                  "forget", "refusefirst")
# What the provider said on 2026-09-30, as Codex passed it on in its error message.
REFUSAL = json.dumps({"type": "error", "status": 400, "error": {
    "type": "invalid_request_error",
    "message": "The 'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT "
               "account."}}, separators=(",", ":"))


def log(argv: list[str], groups: dict | None) -> None:
    with open(LOG, "a", encoding="utf-8") as out:
        out.write(json.dumps({"host": pathlib.Path(sys.argv[0]).name, "argv": argv,
                              "groups": groups,
                              "nested": [n for n in NESTED if n in os.environ],
                              "job": "AGENT_BIOS_HOOK_JOB" in os.environ}) + "\n")


def called(method: str, params) -> None:
    with open(LOG + ".calls", "a", encoding="utf-8") as out:
        out.write(json.dumps({"method": method, "params": params}) + "\n")


def fire(groups: dict, event: str, source: str | None, cwd: str, **more) -> list[str]:
    """Run every configured hook on one event, as the host would, and collect the context."""
    context = []
    for group in groups.get(event, []) if HOOKS else []:
        if group.get("matcher") and group["matcher"] != source:
            continue
        for handler in group["hooks"]:
            payload = {"hook_event_name": event, "session_id": "fake-session", "cwd": cwd,
                       **more}
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


class Session:
    """One session: its launch instructions, the hooks' output it holds, and the kinds of child
    defined for it, with what a child of no defined kind takes."""

    def __init__(self, groups: dict, launched: list[str], kinds: dict[str, str],
                 inherits: bool):
        self.groups, self.kinds, self.inherits = groups, kinds if LAUNCH else {}, inherits
        self.launched = launched if LAUNCH else []
        self.hooked = fire(groups, "SessionStart", "startup", os.getcwd())

    def compact(self) -> None:
        self.hooked = fire(self.groups, "SessionStart", "compact", os.getcwd())
        if MODE == "forget":
            self.launched = []

    def turn(self, prompt: str) -> str:
        self.hooked += fire(self.groups, "UserPromptSubmit", None, os.getcwd())
        asked = KIND.match(prompt)
        if asked is None:
            return answer(self.launched + self.hooked)
        kind = self.kinds.get(asked.group(1))
        start = [kind] if kind is not None else self.launched if self.inherits else []
        return answer(start + fire(self.groups, "SubagentStart", None, os.getcwd(),
                                   agent_type=asked.group(1)))


def argument(argv: list[str], name: str) -> str | None:
    return argv[argv.index(name) + 1] if name in argv else None


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
    appended = argument(argv, "--append-system-prompt-file")
    agents = argument(argv, "--agents")
    session = Session(groups, [pathlib.Path(appended).read_text()] if appended else [],
                      {name: kind["prompt"] for name, kind in
                       json.loads(pathlib.Path(agents).read_text()).items()} if agents else {},
                      inherits=False)
    streamed = argument(argv, "--input-format") == "stream-json"
    prompts = (json.loads(line)["message"]["content"] for line in sys.stdin) if streamed \
        else iter([argv[-1]])
    for prompt in prompts:
        called("prompt", {"text": prompt})
        if prompt == "/compact":
            if MODE == "nocompact":
                return 1
            if MODE == "compactfails":
                print(json.dumps({"type": "result", "is_error": True,
                                  "subtype": "error_during_execution",
                                  "result": "Error during compaction"}), flush=True)
                continue
            if MODE != "compactquiet":
                session.compact()
                print(json.dumps({"type": "system", "subtype": "compact_boundary",
                                  "compact_metadata": {"trigger": "manual", "pre_tokens": 1}}),
                      flush=True)
            reply = ""
        else:
            reply = session.turn(prompt)
        print(json.dumps({"type": "result", "is_error": False, "subtype": "success",
                          "result": reply}), flush=True)
    return 0


def configured(argv: list[str]) -> tuple[dict, list[str], dict[str, dict]]:
    """What Codex was given per run: its hooks, its launch instructions (else the ones it is
    configured with), and each role defined for the run."""
    given = {}
    for i, a in enumerate(argv):
        if a == "-c":
            key, value = argv[i + 1].split("=", 1)
            given[key] = tomllib.loads(f"v = {value}")["v"]
    hooks = {key.removeprefix("hooks."): value for key, value in given.items()
             if key.startswith("hooks.")}
    native = os.environ.get("FAKE_HOST_NATIVE")
    launched = [given.get("developer_instructions", native)]
    roles: dict[str, dict] = {}
    for key, value in given.items():
        parts = key.split(".")
        if parts[0] == "agents" and len(parts) > 2:
            roles.setdefault(".".join(parts[1:-1]), {})[parts[-1]] = value
    return hooks, [text for text in launched if text], roles


def camel(event: str) -> str:
    return event[0].lower() + event[1:]


def codex(argv: list[str]) -> int:
    groups, launched, given = configured(argv)
    roles = {**json.loads(os.environ.get("FAKE_HOST_ROLES", "{}")), **given}
    kinds = {name: tomllib.loads(pathlib.Path(role["config_file"]).read_text())
             .get("developer_instructions", "") for name, role in roles.items()
             if "config_file" in role}
    kinds = {name: text for name, text in kinds.items() if text.strip()}
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
        called(method, params)
        if method == "initialize":
            say({"id": ident, "result": {}})
        elif method == "config/read":
            say({"id": ident, "result": {"config": {
                "developer_instructions": os.environ.get("FAKE_HOST_NATIVE"),
                "agents": {"max_depth": None, **roles}}, "origins": {}}})
        elif method == "hooks/list":
            if MODE == "nolist":
                return 0
            say({"id": ident, "result": {"data": [{"hooks": rows}]}})
        elif method == "thread/start":
            if MODE == "nothread":
                say({"id": ident, "error": {"code": -32000, "message": "no conversation"}})
                continue
            thread = f"thread-{len(threads)}"
            threads[thread] = {"session": None, "compacted": False, "turns": 0}
            say({"id": ident, "result": {"thread": {"id": thread}}})
        elif method == "turn/start":
            if MODE == "silent":
                return 1
            thread = params["threadId"]
            state, text = threads[thread], params["input"][0]["text"]
            state["turns"] += 1
            turn = f"{thread}-turn-{state['turns']}"
            say({"id": ident, "result": {"turn": {"id": turn, "items": [],
                                                  "status": "inProgress"}}})
            if state["session"] is None:
                state["session"] = Session(active, launched, kinds, inherits=True)
            if state["compacted"]:
                state["session"].compact()
                state["compacted"] = False
            failure = {"message": REFUSAL, "codexErrorInfo": "other", "additionalDetails": None}
            refused = MODE in ("refuse", "refusenoend", "refusequiet") or (
                MODE == "refusefirst" and state["turns"] == 1)
            reply = None
            # Every turn but a rehydrated probe's first, which only gives it something to compact.
            if MODE in ("crossturn", "staleturn") and text != "Reply OK.":
                # Another conversation's turn, or an earlier turn of this one, ends first saying
                # what this one would; then this turn completes knowing nothing.
                other, earlier = ("thread-other", "thread-other-turn-1") \
                    if MODE == "crossturn" else (thread, f"{thread}-turn-0")
                say({"method": "item/completed", "params": {
                    "threadId": other, "turnId": earlier, "completedAtMs": 0,
                    "item": {"type": "agentMessage", "text": state["session"].turn(text)}}})
                say({"method": "turn/completed", "params": {
                    "threadId": other, "turn": {"id": earlier, "status": "completed"}}})
                reply = "NONE"
            if (refused and MODE != "refusequiet") or MODE == "retrysilent":
                say({"method": "error", "params": {"error": failure,
                                                   "willRetry": MODE == "retrysilent",
                                                   "threadId": thread, "turnId": turn}})
            if MODE == "refusenoend":
                return 0
            if refused or MODE == "retrysilent":
                say({"method": "turn/completed", "params": {"threadId": thread, "turn": {
                    "id": turn, "status": "failed" if refused else "completed",
                    "error": failure if refused else None}}})
                continue
            if MODE == "error":
                say({"method": "item/completed", "params": {
                    "threadId": thread, "turnId": turn, "completedAtMs": 0,
                    "item": {"type": "plan", "text": "An error occurred."}}})
            else:
                say({"method": "item/completed", "params": {
                    "threadId": thread, "turnId": turn, "completedAtMs": 0,
                    "item": {"type": "agentMessage",
                             "text": reply or state["session"].turn(text)}}})
                if MODE == "noend":
                    return 0
            say({"method": "turn/completed", "params": {"threadId": thread, "turn": {
                "id": turn, "status": "interrupted" if MODE == "saidinterrupted"
                else "completed"}}})
        elif method == "thread/compact/start":
            if MODE == "nocompact":
                say({"id": ident, "error": {"code": -32000, "message": "cannot compact"}})
                continue
            thread = params["threadId"]
            state = threads[thread]
            state["turns"] += 1
            turn = f"{thread}-turn-{state['turns']}"
            say({"id": ident, "result": {}})
            if MODE == "crosscompact":
                # Another conversation compacts and completes its turn first.
                other = "thread-other"
                say({"method": "item/completed", "params": {
                    "threadId": other, "turnId": f"{other}-turn-1", "completedAtMs": 0,
                    "item": {"type": "contextCompaction", "id": "other-compaction"}}})
                say({"method": "turn/completed", "params": {
                    "threadId": other, "turn": {"id": f"{other}-turn-1", "status": "completed"}}})
            if MODE in ("compactfails", "crosscompact"):
                failure = {"message": "compaction failed", "codexErrorInfo": "other",
                           "additionalDetails": None}
                say({"method": "error", "params": {"error": failure, "willRetry": False,
                                                   "threadId": thread, "turnId": turn}})
                say({"method": "turn/completed", "params": {"threadId": thread, "turn": {
                    "id": turn, "status": "failed", "error": failure}}})
                continue
            if MODE != "compactquiet":
                state["compacted"] = MODE not in ("compactitemfails", "stalecompact")
                say({"method": "item/completed", "params": {
                    "threadId": thread, "completedAtMs": 0,
                    "turnId": f"{thread}-turn-0" if MODE == "stalecompact" else turn,
                    "item": {"type": "contextCompaction", "id": "compaction-item"}}})
            say({"method": "turn/completed", "params": {"threadId": thread, "turn": {
                "id": turn, "status": "failed" if MODE == "compactitemfails"
                else "completed"}}})
    return 0


if __name__ == "__main__":
    sys.exit({"claude": claude, "codex": codex}[pathlib.Path(sys.argv[0]).name](sys.argv[1:]))
