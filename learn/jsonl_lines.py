#!/usr/bin/env python3
"""The lines of a JSONL text — the ONE splitter every JSONL reader in the repo uses.

A JSONL record ends at "\\n" and nowhere else. `str.splitlines()` also breaks at
U+2028, U+2029, \\x0b, \\x0c, \\x1c-\\x1e and \\x85, and JSON allows U+2028 and
U+2029 raw inside a string: Claude Code writes them raw, and so does every
`json.dumps(..., ensure_ascii=False)` writer here. Split that way, one record
becomes two halves that do not parse — read as unreadable, or dropped, or, in a
reader that keeps what it cannot parse, rejoined with "\\n" in place of the
character it lost.

It lives in learn/ because shipped code reads JSONL too (learn/migrate-learnings.py)
and shipped code may not import author-side code; session-distill/runlib reaches it
through runlib/records.py, which loads it by path.

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
