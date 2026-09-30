#!/usr/bin/env python3
"""Claude Desktop MCP server for explicit agent-bios instructions delivery.

It is a transport at the same layer as `compose/app_bridge/scripts/bridge.py`: it
owns no selection, ContentRef, receipt or identifier. Each tool call resolves the
confirmed private release again and runs that release's
`compose/instructions_app.py session <op> --host claude-desktop` in a child
process, so a package update answers from the next call and this long-lived
process holds nothing across requests.

Protocol 2025-11-25 over stdio, the revision Desktop speaks; a call that arrives
without a handshake is still answered, because nothing here depends on one.
Standard library only; stdout carries protocol messages and nothing else.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
PROTOCOL = "2025-11-25"
KNOWN_PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
CALL_TIMEOUT = 120

_SESSION_ID = {"type": "string", "description": "The session_id an earlier preview or use returned in this conversation."}
_DOMAINS = {"type": "array", "items": {"type": "string"},
            "description": "Only when the user names a selection; omit to use their saved installation selection."}
# One owner: the bundle builder reads this list for the manifest.
TOOLS = [
    {"name": "status",
     "description": "Show whether agent-bios instructions were delivered to this conversation. After reading a "
                    "delivery to its last line, call this with end_marker_seen set to that line.",
     "inputSchema": {"type": "object", "properties": {
         "session_id": _SESSION_ID,
         "end_marker_seen": {"type": "string", "description": "The delivery's last line, exactly as read."}},
         "required": ["session_id"]}},
    {"name": "preview",
     "description": "Describe the agent-bios work environment use would return, without delivering it. "
                    "Call only when the user asks for their agent-bios instructions or environment.",
     "inputSchema": {"type": "object", "properties": {"session_id": _SESSION_ID, "domains": _DOMAINS}}},
    {"name": "use",
     "description": "Return the user's selected agent-bios work environment as context for this conversation. "
                    "Call only when the user asks for it.",
     "inputSchema": {"type": "object", "properties": {
         "session_id": _SESSION_ID, "domains": _DOMAINS,
         "expected_content_ref": {"type": "string", "description": "The content_ref preview returned, to refuse a changed snapshot."}}}},
    {"name": "off",
     "description": "Stop agent-bios delivery in this conversation. Text already returned stays in context.",
     "inputSchema": {"type": "object", "properties": {"session_id": _SESSION_ID}, "required": ["session_id"]}},
]


class ToolError(RuntimeError):
    pass


def _config() -> dict[str, Any]:
    config = json.loads((HERE / "desktop.json").read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ToolError("this agent-bios Desktop bundle has an unsupported configuration; generate it again with agent-bios app desktop")
    for key in ("home", "state_root", "user_root"):
        if not isinstance(config.get(key), str) or not Path(config[key]).is_absolute():
            raise ToolError("this agent-bios Desktop bundle needs absolute private roots")
    return config


def _string(arguments: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"{key} must be a nonempty string")
    return value.strip()


def _argv(operation: str, arguments: dict[str, Any]) -> list[str]:
    tail = ["--host", "claude-desktop"]
    session = _string(arguments, "session_id")
    if session is not None:
        tail += ["--session", session]
    if operation in {"preview", "use"} and arguments.get("domains") is not None:
        domains = arguments["domains"]
        if not isinstance(domains, list) or not domains or not all(isinstance(v, str) and v.strip() for v in domains):
            raise ToolError("domains must be a nonempty list of selection names")
        tail += ["--domains", ",".join(v.strip() for v in domains)]
    if operation == "use" and (ref := _string(arguments, "expected_content_ref")) is not None:
        tail += ["--expected-content-ref", ref]
    if operation == "status" and (marker := _string(arguments, "end_marker_seen")) is not None:
        tail += ["--end-marker-seen", marker]
    return tail


def run_session(operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
    config = _config()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(HERE))
    from host_platform import python_argv, runtime_environment
    from instructions_transaction import confirmed_release, guard_pending, reject_symlink_ancestors
    state = Path(config["state_root"])
    reject_symlink_ancestors(state)
    reject_symlink_ancestors(Path(config["user_root"]))
    guard_pending(state)
    release = confirmed_release(state)
    reject_symlink_ancestors(release)
    env = dict(os.environ)
    env.update({"HOME": config["home"], "AGENT_BIOS_STATE_DIR": config["state_root"],
                "AGENT_BIOS_INSTRUCTIONS_DIR": config["user_root"], "AGENT_BIOS_CORPUS_DIR": config["user_root"],
                "AGENT_BIOS_PACKAGE_ROOT": str(release), "AGENT_BIOS_PRIVATE_INSTRUCTIONS": "1",
                "AGENT_BIOS_PRIVATE_CORPUS": "1", "AGENT_BIOS_LEGACY_INSTALL": "0",
                "PYTHONDONTWRITEBYTECODE": "1"})
    if "python_binding" in config:
        if not isinstance(config["python_binding"], dict):
            raise ToolError("the bundle's Python binding must be an object")
        env.update(runtime_environment(config["python_binding"]))
    manager = release / "compose/instructions_app.py"
    argv = python_argv(manager, "--repo", str(release), "--state-dir", config["state_root"],
                       "--user-dir", config["user_root"], "--json", "session", operation,
                       *_argv(operation, arguments), environ=env)
    try:
        done = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", timeout=CALL_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"agent-bios did not answer within {CALL_TIMEOUT} seconds") from exc
    if done.returncode != 0:
        raise ToolError(done.stderr.strip() or f"agent-bios session {operation} failed")
    try:
        return json.loads(done.stdout)
    except ValueError as exc:
        raise ToolError("agent-bios returned an unreadable session result") from exc


def _scope(result: dict[str, Any]) -> str:
    return ("Project scope: none. Desktop names no project, so project-scoped imported "
            "instructions are not included.") if result.get("project_scope") == "none" else ""


def _size_note(result: dict[str, Any]) -> str:
    if not result.get("host_may_save_to_file"):
        return ""
    return (f"{result['instruction_bytes']} bytes is above the smallest limit Desktop has kept inline; "
            "Desktop may save this result to a file instead of showing it.")


def _unavailable(result: dict[str, Any]) -> str:
    items = result.get("unavailable") or []
    names = [f"{item.get('ref')} ({item.get('reason')})" if isinstance(item, dict) else str(item) for item in items]
    return "Not included: " + "; ".join(names) if names else ""


def render(operation: str, result: dict[str, Any]) -> str:
    session = result.get("session_id")
    if operation == "use" and isinstance(result.get("instruction_text"), str):
        lines = [f"agent-bios session_id: {session} — pass it to status, off and use in this conversation.",
                 f"content_ref: {result['content_ref']}", _scope(result), _size_note(result)]
        if result.get("repeat"):
            lines.append("Same snapshot as this conversation's latest delivery; returned again with its existing receipt.")
        lines.append(_unavailable(result))
        lines.append("The text below ends with a line beginning 'agent-bios end'. After reading to it, "
                     "call status with that whole line as end_marker_seen.")
        header = "\n".join(line for line in lines if line)
        return f"{header}\n\n{result['instruction_text'].rstrip()}\n\n{result['end_marker']}"
    if operation == "preview":
        if result.get("selection_mode") == "none":
            return f"agent-bios session_id: {session}\nNo instructions are selected; use would return nothing."
        lines = [f"agent-bios session_id: {session} — pass it to use, status and off in this conversation.",
                 f"content_ref: {result['content_ref']}",
                 f"Size: {result.get('instruction_characters')} characters, {result.get('instruction_bytes')} bytes.",
                 _scope(result), _size_note(result),
                 _unavailable(result),
                 "Nothing was delivered. Call use to return this text."]
        return "\n".join(line for line in lines if line)
    lines = [f"agent-bios session_id: {session}",
             f"Delivery: {'on' if result.get('enabled') else 'off'}; "
             f"deliveries recorded: {len(result.get('deliveries', []))}.",
             f"Latest delivery read to its end: {'yes' if result.get('latest_end_confirmed') else 'no'}."
             if result.get("ever_delivered") else "",
             result.get("message", "")]
    return "\n".join(line for line in lines if line)


def call_tool(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if name not in {tool["name"] for tool in TOOLS}:
        return {"content": [{"type": "text", "text": f"unknown tool: {name}"}], "isError": True}
    if not isinstance(arguments, dict):
        return {"content": [{"type": "text", "text": "arguments must be an object"}], "isError": True}
    try:
        text = render(name, run_session(name, arguments))
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except (ToolError, OSError, RuntimeError, ValueError, KeyError) as exc:
        return {"content": [{"type": "text", "text": f"agent-bios: {exc}"}], "isError": True}


def respond(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "expected one JSON-RPC request object"}}
    method, ident = message.get("method"), message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if method == "initialize":
        asked = params.get("protocolVersion")
        result: dict[str, Any] = {"protocolVersion": asked if asked in KNOWN_PROTOCOLS else PROTOCOL,
                                  "capabilities": {"tools": {}},
                                  "serverInfo": {"name": "agent-bios", "version": _version()}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        result = call_tool(params)
    elif ident is None:
        return None
    else:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"method not supported: {method}"}}
    return None if ident is None else {"jsonrpc": "2.0", "id": ident, "result": result}


def _version() -> str:
    try:
        return str(json.loads((HERE.parent / "manifest.json").read_text(encoding="utf-8"))["version"])
    except (OSError, ValueError, KeyError):
        return "unknown"


def main() -> int:
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply: dict[str, Any] | None = {"jsonrpc": "2.0", "id": None,
                                            "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = respond(message)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
