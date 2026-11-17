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

A record ends at a terminator, "\n" or "\r\n", and the two are the same terminator:
lines compare equal whichever ended them. A "\r" anywhere else in a line stays — JSON
allows it as whitespace between tokens. A reader takes the file's bytes and decodes them
itself (`read`), because text-mode reading turns that bare "\r" into a line break before
any splitter sees it. A writer that rewrites a file keeps each line's own terminator
(`split_terminated`) and writes bytes, so no newline translation touches it.

This module has no side effects on import and is safe to load by path.
"""


def split_terminated(text):
    """[(line, terminator)] of `text` (str or bytes): cut at each "\n" only, the
    terminator "\n" or "\r\n" taken off the line, "" for a last line with none.
    Joining every line with its terminator gives `text` back. Blank lines are kept,
    so a reader's line numbers are the file's."""
    nl, cr = (b"\n", b"\r") if isinstance(text, bytes) else ("\n", "\r")
    parts = text.split(nl)
    out = []
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if last and not part:
            break
        if not last and part.endswith(cr):
            out.append((part[:-1], cr + nl))
        else:
            out.append((part, text[:0] if last else nl))
    return out


def split(text):
    """The lines of `text`, each without its terminator ("\n" or "\r\n")."""
    return [line for line, _terminator in split_terminated(text)]


def read(path, errors="strict"):
    """The lines of the JSONL file at `path`: its bytes decoded as UTF-8 (`errors` as
    bytes.decode takes it), then `split`."""
    with open(path, "rb") as handle:
        return split(handle.read().decode("utf-8", errors))


def read_terminated(path, errors="strict"):
    """`read`, each line with its own terminator, for a writer that keeps it."""
    with open(path, "rb") as handle:
        return split_terminated(handle.read().decode("utf-8", errors))
