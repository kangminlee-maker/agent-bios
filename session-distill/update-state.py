#!/usr/bin/env python3
"""Record the session-distill nudge baseline at mining-window close.

Writes the state file the launcher's session_distill_nudge() reads:
{window_end, history_lines_total, updated}. history_lines_total must be
counted the same way the launcher counts it (newlines in both providers'
history.jsonl), so the launcher's delta starts at ~0 after a window closes.

Usage: update-state.py [--window-end YYYY-MM-DD]  (default: today)
"""
import argparse
import datetime
import json
import os
import pathlib

STATE = pathlib.Path(
    os.environ.get(
        "AGENT_BIOS_SESSION_DISTILL_STATE",
        str(pathlib.Path.home() / ".local/share/agent-bios/session-distill-state.json"),
    )
)


def line_count(path: pathlib.Path) -> int:
    try:
        with path.open("rb") as fh:
            return sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(1 << 20), b""))
    except OSError:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-end", default=datetime.date.today().isoformat())
    args = parser.parse_args()
    total = line_count(pathlib.Path.home() / ".claude/history.jsonl") + line_count(
        pathlib.Path.home() / ".codex/history.jsonl"
    )
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(
            {
                "window_end": args.window_end,
                "history_lines_total": total,
                "updated": datetime.datetime.now().isoformat(timespec="seconds"),
            },
            indent=1,
        )
        + "\n"
    )
    print(f"state written: {STATE} (window_end={args.window_end}, lines={total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
