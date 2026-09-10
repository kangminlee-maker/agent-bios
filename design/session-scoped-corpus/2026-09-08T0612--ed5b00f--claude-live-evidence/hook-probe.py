#!/opt/homebrew/bin/python3
"""Fixture-only evidence wrapper for the unmodified agent-bios Claude hook."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path("/private/tmp/agent-bios-claude-live.Tsipsi")
SOURCE = Path("/Users/kangmin/Documents/agent-bios/claude/hooks/tooling-gotchas-hook.py")
EVENTS = ROOT / "hook-events.jsonl"


def main() -> int:
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    result = subprocess.run(
        [sys.executable, str(SOURCE)], input=raw, capture_output=True, check=False
    )
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.flush()

    tool_input = payload.get("tool_input") if isinstance(payload, dict) else {}
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    evidence = {
        "fixture": True,
        "hook_event_name": payload.get("hook_event_name") if isinstance(payload, dict) else None,
        "session_id": payload.get("session_id") if isinstance(payload, dict) else None,
        "tool_name": payload.get("tool_name") if isinstance(payload, dict) else None,
        "synthetic_command": command if isinstance(command, str) else None,
        "actual_hook_output": result.stdout.decode("utf-8", errors="replace"),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    }
    with EVENTS.open("a", encoding="utf-8") as output:
        output.write(json.dumps(evidence, ensure_ascii=False, separators=(",", ":")) + "\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
