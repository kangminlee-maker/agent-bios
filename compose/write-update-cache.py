#!/usr/bin/env python3
"""Write the update-check cache atomically.

The launcher READS this file on every start and never writes it, so a half-written
cache is a crash in the TUI rather than a stale badge — hence os.replace over a
temp file in the same directory, not a plain open-and-write.

`latest` is omitted when the lookup failed; `checked_at` is written regardless, so
an offline machine records its attempt and waits out the interval instead of
retrying on every launch. Absence of `latest` therefore means "asked, no answer",
which the launcher must not render as "up to date".
"""
import json
import os
import sys
import tempfile


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print("usage: write-update-cache.py <out> <checked_at> <latest|''> <current>",
              file=sys.stderr)
        return 2
    out, checked_at, latest, current = argv[1], argv[2], argv[3], argv[4]
    try:
        checked = int(checked_at)
    except ValueError:
        print(f"checked_at is not an integer: {checked_at!r}", file=sys.stderr)
        return 2
    payload: dict[str, object] = {"checked_at": checked}
    if current:
        payload["current"] = current
    if latest:
        payload["latest"] = latest
    directory = os.path.dirname(out) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".update-check.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp, out)
    except BaseException:
        # A temp file left in the state dir would be swept by nothing.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
