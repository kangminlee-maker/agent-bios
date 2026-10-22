#!/usr/bin/env python3
"""The lines of a JSONL text — the ONE splitter every JSONL reader in the repo uses.

A JSONL record ends at "\\n" and nowhere else. `str.splitlines()` also breaks at
U+2028, U+2029, \\x0b, \\x0c, \\x1c-\\x1e and \\x85, and JSON allows U+2028 and
U+2029 raw inside a string: Claude Code writes them raw, and so does every
`json.dumps(..., ensure_ascii=False)` writer here. Split that way, one record
becomes two halves that do not parse — read as unreadable, or dropped, or, in a
reader that keeps what it cannot parse, rejoined with "\\n" in place of the
character it lost.

It lives in wrappers/ because a reader of it is copied out of the package on its own:
the compatibility install puts wrappers/claude_hermetic_evidence.py in the host's bin,
and that helper finds this file beside itself and nowhere else, so the install puts
this file beside it there too. Every other consumer loads it by path inside its own
package root: compose/host_platform.py and learn/migrate-learnings.py as
../wrappers/jsonl_lines.py, author-side session-distill/runlib through runlib/records.py.
Shipped code may not import author-side code, so the owner is shipped.

A reader takes the file's bytes and decodes them itself (`read`): text-mode reading
turns a bare "\r", which JSON allows as whitespace between tokens, into a line break
before any splitter sees it.

This module has no side effects on import and is safe to load by path.
"""


def split(text):
    """`text` (str or bytes) cut at each "\\n" only, the newline dropped, as
    str.splitlines() would cut a text whose only line break is "\\n": no empty
    last line after a final newline, and blank lines kept, so a reader's line
    numbers are the file's. A "\\r" before a "\\n" stays, which json.loads reads
    as whitespace."""
    parts = text.split(b"\n" if isinstance(text, bytes) else "\n")
    if parts and not parts[-1]:
        parts.pop()
    return parts


def read(path, errors="strict"):
    """The lines of the JSONL file at `path`: its bytes decoded as UTF-8 (`errors` as
    bytes.decode takes it), then `split`."""
    with open(path, "rb") as handle:
        return split(handle.read().decode("utf-8", errors))
