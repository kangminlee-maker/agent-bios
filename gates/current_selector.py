#!/usr/bin/env python3
"""Read a dated-bundle pointer the way CommonMark reads it, once, for both readers.

`gates/check-development-plan.py` and the checker inventory inside
`gates/check-parity.sh` both decide which dated file is current by reading one
markdown entry point, so the reading lives here instead of in two copies that
had already drifted: one destination pattern admitted an empty link target and
the other did not, and one of them matched a target carrying a newline.

Block structure is resolved first and line by line -- fenced code, then HTML
comment blocks, then indented code -- and inline structure only afterwards,
scoped to a single paragraph. That scoping is the whole point. A code span
cannot cross a blank line and an unmatched backtick run is ordinary text, so
two stray backticks can no longer hide a live selector between them and one
stray backtick can no longer delete the rest of the document and report the
loss as a missing pointer.
"""
from __future__ import annotations

import re

# One destination pattern behind every selector. It refuses a newline inside the
# parentheses and admits an empty target, so an empty destination reaches the
# caller's own name rule and is reported as a bad name rather than as no pointer.
DESTINATION = r"([^)\n]*)"
PLAN_SELECTOR = r"\*\*Implementation task graph:\*\*[ \t]*\[[^\]\n]+\]\(" + DESTINATION + r"\)"
SSOT_SELECTOR = r"\*\*Design SSOT:\*\*[ \t]*\[[^\]\n]+\]\(" + DESTINATION + r"\)"
CHECKER_SELECTOR = r"\[Static plan checker\]\(" + DESTINATION + r"\)"
CATALOG_SELECTOR = r"\[Test families and phase scopes\]\(" + DESTINATION + r"\)"
REGRESSION_SELECTOR = r"\[bound acceptance regressions\]\(" + DESTINATION + r"\)"

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_INDENTED = re.compile(r"^(?: {4}|\t)")
_LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")
_COMMENT_OPEN = re.compile(r"^ {0,3}<!--")
_COMMENT_SPAN = re.compile(r"<!--.*?-->", re.DOTALL)
_BACKTICKS = re.compile(r"`+")


def current_selector_prose(text: str) -> str:
    """Return the prose a reader sees: code and comments cannot select anything."""
    return _inline("\n".join(_blocks(text.splitlines())))


def _blocks(lines: list[str]) -> list[str]:
    """Drop fenced code, HTML comment blocks and indented code, in that order.

    Comments are read after fences because a literal `<!--` inside a fence is
    code, and reading it as a comment opener used to swallow every following
    line up to the next `-->` or to end of file.
    """
    kept: list[str] = []
    fence: str | None = None
    comment = code = listed = False
    after_blank = True
    for line in lines:
        if fence is not None:
            closer = _FENCE.match(line)
            if closer and closer[1][0] == fence[0] and len(closer[1]) >= len(fence) \
                    and not closer[2].strip():
                fence = None
            continue
        if comment:
            comment = "-->" not in line
            continue
        if code:
            if not line.strip() or _INDENTED.match(line):
                continue
            code = False
        if not line.strip():
            kept.append(line)
            after_blank = True
            continue
        opener = _FENCE.match(line)
        if opener:
            fence = opener[1]
            after_blank = False
            continue
        if _COMMENT_OPEN.match(line):
            # A CommonMark HTML block runs to the line carrying its closer, and
            # that whole line belongs to the block rather than to the prose.
            comment = "-->" not in line
            after_blank = False
            continue
        if _LIST_ITEM.match(line):
            listed = True
        elif not line[:1].isspace():
            listed = False
        if _INDENTED.match(line) and after_blank and not listed:
            # Indented code cannot interrupt a paragraph, and the same
            # indentation under a bullet is a nested list item, not code.
            code = True
            after_blank = False
            continue
        kept.append(line)
        after_blank = False
    return kept


def _inline(text: str) -> str:
    """Resolve inline structure one paragraph at a time; a blank line ends a span."""
    out: list[str] = []
    paragraph: list[str] = []
    for line in text.split("\n"):
        if line.strip():
            paragraph.append(line)
            continue
        if paragraph:
            out.append(_spans("\n".join(paragraph)))
            paragraph = []
        out.append("")
    if paragraph:
        out.append(_spans("\n".join(paragraph)))
    return "\n".join(out)


def _spans(paragraph: str) -> str:
    """Remove code spans, then the comments left in the prose around them.

    CommonMark closes a backtick run with the next run of the same width and
    leaves an unpaired run as text, so the runs are walked rather than handed
    to one regex that pairs the first backtick in the file with the last.
    """
    runs = list(_BACKTICKS.finditer(paragraph))
    kept: list[str] = []
    cut = index = 0
    while index < len(runs):
        opener = runs[index]
        width = opener.end() - opener.start()
        closer = next((position for position in range(index + 1, len(runs))
                       if runs[position].end() - runs[position].start() == width), None)
        if closer is None:
            index += 1
            continue
        kept.append(paragraph[cut:opener.start()])
        cut = runs[closer].end()
        index = closer + 1
    kept.append(paragraph[cut:])
    return _COMMENT_SPAN.sub("", "".join(kept))
