#!/usr/bin/env python3
"""The versioned redaction projection: the one text a window, a search hit or a quote is built from (design §5.4, §5.5).

`project(value, version)` takes a **content block** - a string, or any JSON value, since a tool call's
arguments are an object - and gives the characters the block projects to. A locator (`line`,
`json_pointer`, `char_span`) names those characters, so every reader resolves a quote the same way.

**A key is recognised in the structure, never in the serialisation.** The floor's own patterns read
`key=value` and `key: value`; a serialised object puts a closing quote between the key and the colon, so
`{"password": "x"}` handed to the floor as text keeps its secret, and `json.dumps` doubles a path's
backslashes past the Windows pattern. The rules below follow from that, and their order is the order they
run in:

1. **The structure is walked before anything is serialised** (`walk`). Every string and every key is
   projected, and the value of any key the floor treats as the name of a secret is replaced whole.
   `secret_key` asks the floor - does it redact `<key>=<a value>` - rather than copying its key list, so
   a name the floor learns about later is covered here with no edit and no second authority.
2. **A string that is itself a serialised structure is parsed and walked** (`embedded`), at up to
   `MAX_EMBEDDED` removes, because a tool result prints a JSON body whose own members then arrive as text
   with escaped quotes. The walked form replaces the text only when a secret was actually masked, so a
   JSON document a person reads keeps its own formatting unless it held a credential.
3. **The floor runs over every string** (`learn/redact.py::redact`, the repository's single secret floor,
   loaded by path and never changed here), followed by the keyed values the floor cannot see, anchored on
   the floor's own **name** (`_KEYED`): nothing before the name is required, so a fragment that begins
   mid-string is read like any other text, and the name must be followed by an optional closing quote and
   then the separator, which IS the floor's rule - `openai_api_key=` is a secret and `input_tokens=` is
   not. The value's extent is then **scanned, never described**: a string in any of its three spellings
   however long and whatever it holds, or a bare token; or, when the value opens a
   structure, found by decoding it from that point (exact, and it reaches a fragment
   of a document where parsing the whole string cannot; a structure that never closes is one a view
   clipped, so the rest of the text goes, while one that closes without decoding is another notation and
   stays).
4. **Text that is one level of JSON string escaping** is projected through its own unescaped form and
   escaped back (`unescaped`). That encoding is a bijection, so this is exact, and it is the only way the
   rules above reach a member whose value opens a structure in escaped text, where decoding cannot run and
   counting brackets cannot tell a string's delimiter from an escaped quote. Like rule 2 it replaces the
   text only when a secret was masked, so prose keeps its own escaping byte for byte.
5. **Local paths are masked.** An absolute path that begins at a person's home (`/Users/<name>`,
   `/home/<name>`, `C:\\Users\\<name>`) becomes `<HOME>` plus the rest, so a view shows where a file was
   without saying whose account it was; this process's own home is masked wherever it stands.
   `/Users/Shared` is a shared directory, not a home, and stays.

Everything past rule 1 exists because the live run of 2026-10-21 was swept for members whose key the floor
itself calls a secret and whose value was not masked. Each sweep found the next shape: 11,045 when the name
was read as a key's prefix, 3,117 at one or two removes of serialisation, 277 whose value opened a
structure, 27 whose structure the view's own clipping had cut off. A pattern per spelling is what that
progression is; the structure is where the question has one answer, and each rule here either walks a
structure or recovers one.

Then the sweep itself moved (`sweep`, `--sweep <run-dir>`). It had been a byte scan over the files, and so
it judged a different text from the one the projection judges: where it reported 24 members, the decoded
strings - the text a model actually receives - held 63. Thirteen of those were **scalars**, which no story
about a structure's extent explains: the pattern had required the key's own opening quote, capped the key's
prefix at 64 characters and the value's at 4,096, and allowed no quote or backslash inside a value. Each of
those four assumptions hid members of a kind the floor would have masked in prose. Rule 3 anchors on the
name and scans for the end because of them, and the sweep now reads what the projection wrote rather than
the bytes that hold it, so the two cannot drift apart again.

What remains for the design to decide, not this module: a secret-named key whose value opens a structure
inside escaped text that is not a complete JSON string body - a fragment beginning mid-string, where one
level of unescaping has no exact inverse and no rule here can read the structure's extent. Masking to the
end of such a fragment would swallow what followed it, which rule 3's own look-alike control forbids.

The projection is a pure function of the value and the version: the same block projects to the same
characters on every run, which is what lets a quote be checked against it later (`evidence.verify`).

Every projection carries its `redaction_version`. A change to either half is a new version: `r2`
supersedes `r1`, which was the text-only projection of commit 5ea5c3a. A superseded version is **not**
left registered - a projection known to under-redact that anything can still call is a hazard, and
design §5.5 needs only that an old quote fail by name (`REDACTION_VERSION_MISMATCH`) and be made again
from the source, which an unregistered version does.

  projection.py --self-test
  projection.py --sweep <run-dir>
"""
import importlib.util
import collections
import unicodedata
import random
import contextlib
import io
import json
import os
import pathlib
import re
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import records

REPO = pathlib.Path(__file__).resolve().parents[2]
# The version is the masking's identity, so it advances whenever the masking changes - not when the module
# does. `r22` is ONE monotone pass in the original text's own coordinates, VERIFIED on the way out: every source of masking - the
# floor, a secret-named key's whole value, the owner's home paths, and whatever only decoding reveals,
# mapped back at literal or structure granularity - answers in the same coordinates, and the union of their
# extents is masked once. There is no decoded candidate and no fallback, because the gap between those two
# paths is what leaked in four consecutive rounds, each new rule closing one side and opening the other
# (`design/session-distill/2026-10-21T1740--5efadbf--projection-single-pass.md`). Behind the pass stands an
# independent verifier, which does no mapping at all and blanks a block whose output still discloses
# anything or which it could not fully read
# (`design/session-distill/2026-10-21T1937--b8c83d2--projection-verified-invariants.md`).
# A window built under one
# version cannot be read under another, and no superseded version is registered: a projection known to mask
# less that anything can still call is a hazard, and §5.5 asks only that an old artifact fail by name and be
# made again from the source.
CURRENT = "r22"
HOME_MASK = "<HOME>"
MAX_DEPTH = 64   # deeper than any real tool argument; past it the value is projected as its text
MAX_EMBEDDED = 8  # how many times a string may itself be a serialised structure before the text stands as it is


class FloorUnreadable(Exception):
    """The floor is not the shape this projection reads its secret key names out of."""


def _load_floor():
    """`learn/redact.py`, loaded by path: it is the owner of the secret patterns, shipped, and imported here (never copied)."""
    spec = importlib.util.spec_from_file_location("agent_bios_secret_floor", REPO / "learn" / "redact.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FLOOR_PATH = REPO / "learn" / "redact.py"
FLOOR = _load_floor()
# the segment after the home marker runs to the first character that cannot be part of a user name
_SEGMENT = r"""[^/\\\s"'`<>()\[\]{},;:|*?]+"""
# What may stand before another person's home for it to be a path of its own, rather than the tail of a
# relative one (`src/Users/alice.py` is not a home path). A transcript carries tool arguments as JSON, so a
# line break often reaches the text as the two characters `\` and `n`, and that is a boundary, not a segment:
# before this was allowed for, a live run left 8,536 owner paths in the projection with `n` in front of them.
_BOUNDARY = r"(?:(?<=\\n)|(?<=\\t)|(?<=\\r)|(?<![\w.~-]))"
_PATTERNS = (
    re.compile(rf"{_BOUNDARY}/(?:Users|home)/(?!Shared(?![\w.-]))({_SEGMENT})"),
    # one or more backslashes per separator: `json.dumps` doubles them, and a Windows home path that
    # reached the floor through a serialised tool argument used to pass with `C:\\Users\\carol`
    # ... and case-insensitively: `c:\users\Carol` is the same directory as `C:\Users\carol` on the system
    # it came from, so a projection that reads one spelling and not the other masks by luck.
    re.compile(rf"{_BOUNDARY}[A-Za-z]:\\+Users\\+({_SEGMENT})", re.IGNORECASE),
)
_WINDOWS_HOME = re.compile(r"^[A-Za-z]:[\\/]")   # which spelling a declared home is, so its own pattern matches alike
_PROBE = "Zq7probevalue0123456789"   # matched by no pattern of the floor on its own; the self-test proves that


def floor_key_alternation():
    """The alternation of secret key names, read out of the floor's own first pattern so this module keeps no
    second list of them. A floor whose first pattern no longer leads with that group is a named failure, never
    a silently empty list - an empty alternation would match every key or none."""
    first = FLOOR.SECRET_RE[0].pattern
    match = re.match(r"\(\?i\)\(([^()]+)\)\\s\*\[:=\]", first)
    if not match or not match.group(1).strip():
        raise FloorUnreadable(f"REDACTION_FLOOR_UNREADABLE learn/redact.py SECRET_RE[0]: its leading key-name group is "
                              f"not where this projection reads it from ({first[:60]!r}); re-derive the JSON-keyed pattern")
    return match.group(1)


# The JSON-keyed form of a secret, which the floor's `key=value` and `key: value` patterns cannot see because a
# serialised object puts a closing quote between the key and the colon. The value - a JSON string, number,
# boolean or null - is replaced; the key is kept, so a reader still sees that a credential stood there.
#
# The key may carry any prefix, and the name must END it, because that is exactly the floor's own rule: its
# pattern needs the separator straight after the name, so `openai_api_key=` is a secret and `input_tokens=` is
# not. Reading the name as a prefix instead left 11,045 members unmasked in the live run of 2026-10-21 -
# `user_authorization`, `x-api-key`, `page_token`, `google_client_secret` - every one of them a key the floor
# itself calls a secret. `secret_key` asks the floor the same question for the structural half, so the two
# halves answer alike.
_Q = r'\\?"'   # a quote, or one a serialisation escaped: a fragment of a document carries both spellings
# The anchor is the NAME, not a whole key, and nothing before it is required. A pattern that demanded the
# key's opening quote could not see a member in a fragment that begins mid-string (`password": "..."`), and
# one that capped the key's prefix or the value's length could not see a long key or a long value at all:
# thirteen members of the live run of 2026-10-21 were scalars of exactly those shapes, unmasked.
#
# The name must be followed by an optional closing quote and then the separator, which IS the floor's own
# rule - its separator comes straight after the name - so `openai_api_key=` is a secret and `input_tokens=`
# is not, with no prefix to measure.
_KEYED = re.compile(rf'(?i)(?:{floor_key_alternation()})(?:\\?["\'])?[ \t]*[:=][ \t]*')
# The value's extent is scanned rather than described: a string in any of its three spellings, however long
# and whatever it contains, or a bare token. A structure is not scanned - `keyed_spans` decodes it, because
# its extent is a decoding question, not a delimiter one.
_VALUE = re.compile(r'\\"(?:(?!\\").)*\\"'      # a string whose quotes a serialisation escaped
                    r'|"(?:[^"\\]|\\.)*"'        # a plain JSON string
                    r"|'(?:[^'\\]|\\.)*'"        # a repr's string
                    # an unquoted value, which may be several words: a header's credential is `Bearer <token>`
                    # and the floor masks both words, so a scan that stopped at the first space would hand the
                    # floor a text it no longer recognises and the token would stand. It stops at a separator
                    # or the end of the line, never crossing into the next member.
                    r'|[^\s,}\]]+(?:[ \t]+[^\s,}\]]+)*',
                    re.DOTALL)
_COMMENT = re.compile(r'(?:\s|/\*.*?\*/)*', re.DOTALL)


def secret_key(name):
    """Whether the floor treats `name` as the name of a secret: it does, exactly when the floor **changes**
    `name=<a value>`. Asked of the floor rather than copied from it, so a key name the floor learns about
    later is covered here with no edit and no second authority.

    The question is whether the floor changed the string, not whether the placeholder is in the answer: a
    key whose own name already carries the placeholder - an address the floor masked a moment earlier -
    contains it before the floor is asked, and asking the wrong question called every one of those a
    secret (175 of the 205 the live sweep of 2026-10-21 still reported)."""
    if not isinstance(name, str) or not name.strip():
        return False
    probe = f"{name}={_PROBE}"
    return FLOOR.redact(probe) != probe


def home_patterns(home=None):
    """The masking patterns: the two general forms, each needing a boundary before it, and this process's own
    home, which is masked wherever it stands. The owner's path is the one a view must never carry, and prose,
    an escape sequence or a relative prefix may abut it with no separator at all; a longer directory name that
    merely begins with the home is still not the home (the trailing lookahead)."""
    home = os.path.expanduser("~") if home is None else home
    patterns = list(_PATTERNS)
    if home not in ("", "/", "~"):
        # a Windows home is matched case-insensitively, a POSIX one exactly: each follows its own filesystem
        flags = re.IGNORECASE if _WINDOWS_HOME.match(home) else 0
        patterns.append(re.compile(rf"{re.escape(home.rstrip('/'))}(?![\w.-])", flags))
    return patterns


def unterminated(text, start):
    """Whether the structure opening at `start` never closes in `text`, counting brackets outside strings. The
    question is only yes or no, which is why counting is enough here: an extent would have to survive every
    escaping, a decision does not."""
    depth, in_string, i = 0, False, start
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return False
        i += 1
    return True


# ---- the spans every rule would mask, and the one masking over their union ------------------------
#
# The rules do not run in sequence any more, and that is the point. Composing maskers by substitution
# trades one bypass for another: the floor's replacement is destructive, so reading a key after it loses
# the key (`Authorization: "Bearer <v>"` -> `<REDACTED> <v>"`), and reading the key first hands the floor a
# text whose own match it no longer recognises (`Authorization: Bearer\nopaque...` -> the scheme masked and
# the credential left, because the floor's scheme pattern crosses the newline and a scan for a bare value
# does not). r2 fixed the first and opened the second.
#
# So every rule now answers the same question about the SAME input text - which spans would you mask? - and
# the union is masked once. A span any rule claims is masked to its full extent, so no rule can shrink
# another's, and a rule reading the original text cannot be shown a text another rule has rewritten.
SECRET_SPAN, HOME_SPAN = 1, 0   # on an overlap the stronger replacement wins: a secret hides a path's tail


def floor_patterns():
    """The floor's own compiled patterns, read from `learn/redact.py` and never copied.

    `redact` substitutes, which tells us what it masked but not where. The patterns tell us where, and they
    are the floor's property: a pattern it gains covers the projection with no edit here. A floor that does
    not expose them usably fails by name rather than silently masking less."""
    patterns = getattr(FLOOR, "SECRET_RE", None)
    if not isinstance(patterns, (list, tuple)) or not patterns:
        raise FloorUnreadable(f"REDACTION_FLOOR_UNREADABLE {FLOOR_PATH}: SECRET_RE is not a non-empty list of "
                              "compiled patterns, so the spans the floor would mask cannot be read")
    for pattern in patterns:
        if not hasattr(pattern, "finditer") or not hasattr(pattern, "pattern"):
            raise FloorUnreadable(f"REDACTION_FLOOR_UNREADABLE {FLOOR_PATH}: {pattern!r} is not a compiled "
                                  "pattern, so the spans the floor would mask cannot be read")
    return patterns


def floor_spans(text):
    """Every span the floor's patterns match, each masked whole as `redact` masks it.

    The floor applies its patterns in sequence, so a later pattern sees an earlier one's output; these spans
    are all read from the original text, which can only cover more, never less."""
    return [(match.start(), match.end(), FLOOR.PLACEHOLDER, SECRET_SPAN)
            for pattern in floor_patterns() for match in pattern.finditer(text)]


def keyed_spans(text):
    """Every span a secret-named key's value occupies: a scalar by scan, a structure by decoding.

    The value's own quotes stay outside the span, so the quoting comes back exactly as it was without
    re-emitting it - and a structure, which has no quotes of its own, carries them in its replacement."""
    spans, decoder = [], json.JSONDecoder()
    for match in _KEYED.finditer(text):
        at = _COMMENT.match(text, match.end()).end()
        if at < len(text) and text[at] in "{[":
            try:
                _value, end = decoder.raw_decode(text, at)
            except ValueError:
                if not unterminated(text, at):
                    continue      # it closes without decoding: a repr or another notation, left to the other rules
                end = len(text)   # a structure a view clipped: its extent is absent, so the rest of the text goes
            # A structure holding nothing but this module's own masks needs no masking: masking it again
            # replaces the structure with one placeholder, so a second projection of the same text would
            # differ from the first and the projection would not be idempotent. The test is over the
            # CHARACTERS, not over a decode, because the same structure can arrive escaped - where no decode
            # succeeds and the old check silently did not apply.
            if not mask_free(text[at:end]).replace("\x00", "").strip(" \t\r\n\"'[]{},:\\"):
                continue
            spans.append((at, end, f'"{FLOOR.PLACEHOLDER}"', SECRET_SPAN))
            continue
        found = _VALUE.match(text, at)
        if found is None:
            continue
        value, inner = found.group(0), None
        for quote in ('\\"', '"', "'"):
            if value.startswith(quote) and value.endswith(quote) and len(value) >= 2 * len(quote):
                inner = (found.start() + len(quote), found.end() - len(quote))
                break
        if inner is None:
            # An unquoted value stops at a separator, and a value standing at the end of a literal has the
            # closing quote next: the scan took it, and masking it broke the syntax and made a second
            # projection read the orphaned opening quote as a bare value of its own.
            begin, finish = found.start(), found.end()
            while finish > begin and text[finish - 1] in '"\'}],':
                finish -= 1
            # A number, a boolean or a null carries no quotes of its own, so replacing it with a bare mask
            # left a document that no longer parsed. The replacement supplies the quotes the value never had.
            bare, readable = None, True
            try:
                bare = json.loads(text[begin:finish])
            except (ValueError, RecursionError):
                readable = False
            # a sentinel rather than `is not None`: `null` parses TO None, and reading that as "did not
            # parse" left the bare mask standing where a document needed a quoted one
            if readable and not isinstance(bare, str):
                spans.append((begin, finish, f'"{FLOOR.PLACEHOLDER}"', SECRET_SPAN))
                continue
            inner = (begin, finish)
        spans.append((*inner, FLOOR.PLACEHOLDER, SECRET_SPAN))
    return spans


def literal_ranges(text):
    """The inner range of every string literal in `text`, in both spellings: a plain `"..."` and a
    serialisation's `\"...\"`. The ranges are what a replacement may touch without taking a delimiter
    with it."""
    ranges, decoder, index = [], json.JSONDecoder(), 0
    while index < len(text):
        if text[index] == '"':
            try:
                value, end = decoder.raw_decode(text, index)
            except ValueError:
                index += 1
                continue
            if isinstance(value, str):
                ranges.append((index + 1, end - 1))
                index = end
                continue
            index += 1
            continue
        if text.startswith('\\"', index):
            close = text.find('\\"', index + 2)
            if close == -1:
                break
            ranges.append((index + 2, close))
            index = close + 2
            continue
        index += 1
    return ranges


def within_literals(text, start, end):
    """One floor extent, normalised to the boundaries of whatever holds it, as `(start, end, replacement)`.

    The floor's patterns are greedy over characters, not over syntax: `token=def"}` is one match, and
    replacing it took the closing quote and brace with it. The document then no longer parsed, and a second
    projection read the orphaned opening quote as a bare value and masked differently - so the projection was
    not idempotent either.

    One literal holding the extent gives that literal's INNER range, so its quotes survive at whatever
    escaping level they were written. An extent reaching across two or more literals is a claim no single
    value holds, and the unit is then the smallest structure that encloses it - masked whole, quotes and
    all - because the delimiters in between are the ones that would otherwise be eaten. Failing both, the
    extent is the floor's own and stands as it is."""
    touched = [(inner_start, inner_end) for inner_start, inner_end in literal_ranges(text)
               if inner_start < end and inner_end > start]
    if len(touched) == 1:
        return [(touched[0][0], touched[0][1], FLOOR.PLACEHOLDER)]
    if len(touched) > 1:
        enclosing = [(begin, finish) for begin, finish, _value in structures_in(text)
                     if begin <= touched[0][0] and finish >= touched[-1][1]]
        if enclosing:
            begin, finish = min(enclosing, key=lambda pair: pair[1] - pair[0])
            return [(begin, finish, f'"{FLOOR.PLACEHOLDER}"')]
        return [(touched[0][0], touched[-1][1], FLOOR.PLACEHOLDER)]
    return [(start, end, FLOOR.PLACEHOLDER)]


def floor_spans_normalised(text):
    """`floor_spans`, with every extent normalised to the delimiters that enclose it."""
    return [(a, b, replacement, rank)
            for start, end, _replacement, rank in floor_spans(text)
            for a, b, replacement in within_literals(text, start, end)]


def visible_secret_keys(text):
    """The secret-named keys the RAW rules can see here - the ones whose value `keyed_spans` locates by its
    own extent. A key the raw rules cannot see has no locatable value, whatever else the text happens to
    contain."""
    names = set()
    for match in _KEYED.finditer(text):
        name = re.sub(r'[\s:="\'\\]+$', "", match.group(0)).strip().strip('"\'').lower()
        if name:
            names.add(name.lstrip('\\"\''))
    return names


def path_spans(text, home=None):
    """Every span a local home path occupies - the home itself, never the rest of the path, so a view still
    shows where a file was without saying whose account it was."""
    return [(match.start(), match.end(), HOME_MASK, HOME_SPAN)
            for pattern in home_patterns(home) for match in pattern.finditer(text)]


PARTIAL_SURVIVAL = 8    # characters of a credential that may not stand together in the output


def secret_part(match):
    """The credential inside one floor match - not the key that named it.

    The floor's header pattern matches `Authorization: Bearer <v>` whole, so asking whether the MATCH
    survives asks about the word `Authorization` too, and the keyed rule keeps that word on purpose. What may
    not survive is the credential: the match's tail after the key and its separator, and after any scheme
    word, which is the last whitespace-separated run of that tail. For every other pattern the match IS the
    credential. Nothing here enumerates the floor's scheme words - the shape "optional words, then the
    credential" is what is read."""
    whole = match.group(0)
    if match.re.groups and match.group(1) is not None:
        tail = whole[match.end(1) - match.start(0):].lstrip(" \t\r\n:=")
        parts = tail.split()
        return parts[-1] if parts else ""
    return whole


def mask_free(text):
    """`text` with this module's own mask tokens replaced by a character no transcript holds.

    A credential and the output can SHARE the mask: an input that already carried `<REDACTED>` next to a
    secret puts those characters inside the obligation, and the projection's own masking puts them in the
    output, so a comparison of runs reports a survival that is the mask agreeing with itself. The separator
    keeps the fragments apart, so removing a mask cannot join two pieces into a run that was never there."""
    return text.replace(FLOOR.PLACEHOLDER, "\x00").replace(HOME_MASK, "\x00")


def survives(secret, out):
    """Whether `secret` survives in `out` - WHOLLY OR IN PART.

    Asking only whether the whole string is still there passes the very shape this module was fixed for: an
    output that drops `Authorization: Bearer` and keeps the credential after it no longer contains the whole
    match, and the credential is what mattered. Any run of PARTIAL_SURVIVAL characters of a credential is
    enough to be one, so that is the unit; a credential shorter than that is asked about whole - but only
    when it is the whole credential, never when it is a fragment left by removing a mask."""
    if not secret:
        return False
    swept = mask_free(out)
    pieces = [piece for piece in mask_free(secret).split("\x00") if piece]
    if not pieces:
        return False          # the value was nothing but this module's own mask
    entire = len(pieces) == 1 and pieces[0] == secret
    for piece in pieces:
        if entire and len(piece) <= PARTIAL_SURVIVAL:
            return piece in swept
        if len(piece) >= PARTIAL_SURVIVAL and any(piece[i:i + PARTIAL_SURVIVAL] in swept
                                                  for i in range(len(piece) - PARTIAL_SURVIVAL + 1)):
            return True
    return False


def floor_survivors(raw, out):
    """Every credential the unchanged floor claims in `raw` that still stands in `out`, wholly or in part.

    This is the oracle the projection is judged by, and the one it consults before trusting its own decoded
    result. It is independent of how the masking is done: it reads the floor's own patterns over the RAW
    text and asks a question about the OUTPUT."""
    return [secret for pattern in floor_patterns() for match in pattern.finditer(raw)
            for secret in [secret_part(match)] if survives(secret, out)]


def relaxed_decode(text):
    r"""`text` read as the body of a JSON string, or None: what a `\u` escape, an escaped slash and an
    escaped backslash spell when decoded.

    `escaped_form` asks for an escaped QUOTE before it tries, because its job is to re-emit the text in the
    same escaping. This one asks nothing: a value can be spelled in escapes without ever quoting anything,
    and that spelling is the one a reader of the decoded layer sees."""
    if not text or "\\" not in text:
        return None
    try:
        decoded = json.loads(f'"{text}"')
    except ValueError:
        return None
    return decoded if isinstance(decoded, str) and decoded != text else None


def spellings(value):
    """Every form `value` can take through the decodings this projection applies: itself, the serialisation
    and the string leaves of any structure it holds, one level of JSON string escaping, and the plain text
    its escapes spell - repeated to the depth the projection decodes.

    This closes a class rather than a case. A check written in one spelling and a value surviving in another
    is the same defect four times over: the obligation `[ "\u0061bcd..." ]` disappears from the output not
    because it was masked but because the output spells it decoded, and a comparison of raw strings reads
    that as masked. An obligation is a VALUE, not a string, so every form of it is asked about."""
    out, seen, pending = [], set(), [(value, 0)]
    while pending:
        text, depth = pending.pop()
        if not isinstance(text, str) or not text or text in seen or depth > MAX_EMBEDDED:
            continue
        seen.add(text)
        out.append(text)
        for _start, _end, decoded in structures_in(text):
            # the structure's SERIALISATION, not its leaves: every run of eight characters of a leaf is a
            # run of the serialisation too, while a short leaf inside a larger obligation is not itself an
            # obligation - asking about it asks about a character or two, which any output answers by chance
            pending.append((serialise(decoded), depth + 1))
        for inner in (escaped_form(text, depth), relaxed_decode(text)):
            if inner is not None:
                pending.append((inner, depth + 1))
    return out


def is_mask(value):
    """Whether this value is ENTIRELY this projection's own mask.

    A projected text is a valid input: `{"password":"<REDACTED>"}` has a secret-named key, so the keyed rule
    names its value, and that value is the placeholder. Counting it as a surviving credential discarded the
    decoded result of every text that had already been masked and flattened the structure - the projection
    stopped being idempotent, which is a contract, not a nicety.

    The test is exact equality, and that is the point: a mask standing NEXT to, inside, or around a
    credential exempts nothing. `{"token":"<REDACTED>","v":"abcdefghij"}` is not a mask, and reading it as
    one is how a literal placeholder in the input bought acceptance for the value beside it."""
    return value in (FLOOR.PLACEHOLDER, HOME_MASK)


def obligations(text):
    """Every value the original text obliges this module to mask, each with all of its spellings - the
    AUDIT's question, not the pass's.

    The pass does not consult this: it masks extents, and an extent cannot be half-masked. What this answers
    is whether a finished projection still READS a value the original obliged - which is the question a
    control asks, and the one a reviewer asks. A value standing in the projection in any spelling it has is
    the failure; the mask itself is not a value."""
    spans = []
    for pattern in floor_patterns():
        for match in pattern.finditer(text):
            secret = secret_part(match)
            if secret:
                spans.append((match.end() - len(secret), match.end()))
    spans += [(start, end) for start, end, _replacement, _rank in keyed_spans(text)]
    outer = [(a, b) for a, b in spans
             if not any(c <= a and b <= d and (c, d) != (a, b) for c, d in spans)]
    out = []
    for a, b in sorted(set(outer)):
        value = text[a:b]
        if not value:
            continue
        forms = spellings(value)
        if any(is_mask(form) for form in forms):
            continue
        out.append(forms)
    return out


def readable_survivors(raw, out):
    """Every original-text obligation of `raw` whose value still READS in `out` - in any spelling it has,
    wholly or in any run of PARTIAL_SURVIVAL characters. This is the audit question: what is still there."""
    return [forms[0] for forms in obligations(raw) if any(survives(form, out) for form in forms)]


def floor_leftovers(text, home=None):
    """What the unchanged floor claims in `text` and the projection does NOT mask: the differential this
    module is judged by.

    The projection may mask more than the floor and never less. That direction is not a matter of taste -
    the floor is the repository's single secret floor and every other caller relies on it - so it is asked
    as a question about the output, through the oracle above."""
    return floor_survivors(text, project_text(text, home))


def spans_of(text, home=None):
    """Every span any rule would mask in `text`."""
    return floor_spans(text) + keyed_spans(text) + path_spans(text, home)


def mask_one(text, home=None):
    """`text` with ONE rule's spans applied - the home paths. The self-test uses it to state what that rule
    alone does; the projection always masks the union, never one rule's spans."""
    return mask_spans(text, path_spans(text, home))


def mask_spans(text, spans):
    """`text` with every span masked, overlapping spans merged and each merged span masked to its FULL
    extent. The strongest replacement wins an overlap: a secret's placeholder hides a path's tail, which
    masks more than either rule alone asked for and never less."""
    if not spans:
        return text
    merged = []
    for span in sorted(spans, key=lambda s: (s[0], -s[1])):
        start, end, replacement, rank = span
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            prev = merged[-1]
            merged[-1] = (prev[0], max(prev[1], end),
                          replacement if rank > prev[3] else prev[2], max(rank, prev[3]))
        else:
            merged.append((start, end, replacement, rank))
    out, pos = [], 0
    for start, end, replacement, _rank in merged:
        out.append(text[pos:start])
        out.append(replacement)
        pos = end
    out.append(text[pos:])
    return "".join(out)


STATS = collections.Counter()   # counts only: how often the decoded result was discarded, and why


def structures_in(text):
    """Every serialised structure the text holds, as `(start, end, value)`, outermost and non-overlapping.

    A block's text is not always a structure whole: a line of prose can carry one, and the credential may be
    inside it. Asking only whether the stripped text begins with a brace missed every such block, which is
    how a value behind a floor match that crosses the structure's syntax reached a window."""
    decoder, out, pos = json.JSONDecoder(), [], 0
    while pos < len(text):
        nxt = min((i for i in (text.find("{", pos), text.find("[", pos)) if i >= 0), default=-1)
        if nxt < 0:
            break
        try:
            value, end = decoder.raw_decode(text, nxt)
        except ValueError:
            pos = nxt + 1
            continue
        if isinstance(value, (dict, list)):
            out.append((nxt, end, value))
            pos = end
        else:
            pos = nxt + 1
    return out


def escaped_form(text, depth):
    """`text` read as one level of JSON string escaping, or None. Exact, because JSON string encoding is a
    bijection - and the only way the rules reach a member whose value opens a structure in escaped text."""
    if depth > MAX_EMBEDDED or '\\"' not in text:
        return None
    try:
        return json.loads(f'"{text}"')
    except ValueError:
        return None   # a raw quote or control character: not one level of escaping


def undecodable_claim(text, depth):
    """Whether this text names a secret key in some spelling and NOTHING here can decode it.

    Read with every escape collapsed, the text says a credential stands in it; read as it is, no decoding
    succeeds, so no rule can find that value's extent and no result can be shown to have masked it. That is
    the same fail-closed position as an unprovable obligation, and it is a closing rule rather than another
    spelling: nothing here enumerates how the escaping was written, only that it cannot be undone."""
    flat = text.replace("\\", "")
    if flat == text:
        return False
    # a claim whose value is already this module's mask hides nothing; a text where every claim is masked is
    # a text this projection has already produced, and firing on it would make the projection non-idempotent
    pending = [match for match in _KEYED.finditer(flat)
               if not flat[match.end():].lstrip(" \t\r\n\"'").startswith((FLOOR.PLACEHOLDER, HOME_MASK))]
    if not pending:
        return False
    return not (structures_in(text) or escaped_form(text, depth) is not None
                or relaxed_decode(text) is not None)


def escape_map(text):
    """For each character of `text` read as one level of JSON string escaping, the RAW span of `text` that
    produced it - or None when `text` is not one level of such escaping, or when a decoded character has no
    single span of its own.

    This is what lets a finding in a decoded text be masked in the original's coordinates without
    re-serialising anything: a span of the decoded text maps to the span of the raw text between the first
    escape's start and the last escape's end, so a mask never lands inside an escape sequence."""
    spans, index = [], 0
    while index < len(text):
        char = text[index]
        if char != "\\":
            spans.append((index, index + 1))
            index += 1
            continue
        if index + 1 >= len(text):
            return None
        kind = text[index + 1]
        if kind == "u":
            if index + 6 > len(text):
                return None
            spans.append((index, index + 6))
            index += 6
            continue
        if kind in '"\\/bfnrt':
            spans.append((index, index + 2))
            index += 2
            continue
        return None
    decoded = relaxed_decode(text)
    if decoded is None or len(decoded) != len(spans):
        return None   # a surrogate pair, or something this scanner does not model: not mappable
    return spans


def holds_secret(value, home=None, depth=0):
    """Whether a DECODED value is, or holds, a secret: a credential the floor claims, a secret-named key
    whose value is not already the mask, or the owner's home path - at any depth this module decodes.

    This is the question asked of what decoding reveals. It answers about the value; where that value came
    from in the original text is a separate question, and `decoded_extents` answers that one."""
    if depth > MAX_EMBEDDED:
        return True          # no further look is possible, so the honest answer is the closed one
    if isinstance(value, str):
        if is_mask(value):
            return False
        if any(pattern.search(value) for pattern in floor_patterns()):
            return True
        if any(pattern.search(value) for pattern in home_patterns(home)):
            return True
        if any(not is_mask(value[start:end]) for start, end, _replacement, _rank in keyed_spans(value)):
            return True
        for _start, _end, inner in structures_in(value):
            if holds_secret(inner, home, depth + 1):
                return True
        for deeper in (escaped_form(value, depth), relaxed_decode(value)):
            if deeper is not None and deeper != value and holds_secret(deeper, home, depth + 1):
                return True
        return False
    if isinstance(value, dict):
        for key, item in value.items():
            if secret_key(key) and not (isinstance(item, str) and is_mask(item)) and item not in (None, "", {}, []):
                return True
            if holds_secret(key, home, depth + 1) or holds_secret(item, home, depth + 1):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(holds_secret(item, home, depth + 1) for item in value)
    return False


def encoded_secret_keys(value, home=None, depth=0):
    """Every secret-named key inside a decoded value whose own member is not already masked."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and secret_key(key) \
                    and not (isinstance(item, str) and is_mask(item)) and item not in (None, "", {}, []):
                found.append(key)
            if depth < MAX_EMBEDDED:
                found += encoded_secret_keys(item, home, depth + 1)
    elif isinstance(value, (list, tuple)) and depth < MAX_EMBEDDED:
        for item in value:
            found += encoded_secret_keys(item, home, depth + 1)
    elif isinstance(value, str) and depth < MAX_EMBEDDED:
        for _start, _end, inner in structures_in(value):
            found += encoded_secret_keys(inner, home, depth + 1)
    return found


def decoded_extents(text, home=None, depth=0):
    """The extents of `text` that only DECODING shows to hold a secret, in `text`'s own coordinates.

    Granularity is the literal: a finding at any decode depth marks the whole outermost raw string literal
    it came from, because a mask inside an encoded literal is a mask in a text nobody reads, and because a
    partial mask of an encoded value is how the last four rounds each leaked. A literal whose decoded content
    equals its raw content is left to the rules above - they read it exactly as it stands, and masking it
    whole would take a sentence for the sake of a path inside it.

    An escaped text is handled in the same coordinates through `escape_map`; when that mapping cannot be
    built and the decoded text holds a secret, the extent is the whole block."""
    found, decoder, index = [], json.JSONDecoder(), 0
    while index < len(text):
        if text[index] != '"':
            index += 1
            continue
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            index += 1
            continue
        if isinstance(value, str) and value != text[index + 1:end - 1] \
                and holds_secret(value, home, depth + 1):
            found.append((index + 1, end - 1, FLOOR.PLACEHOLDER, SECRET_SPAN))
        index = max(end, index + 1)
    # A structure whose secret-named KEY is written encoded. The keyed rule reads a key it can see and masks
    # that key's value exactly; a key spelled `\u0070assword` it cannot see, and the value it names has no
    # locatable extent of its own - so the structure that holds it is the unit, which is the granularity rule
    # 1 names for a finding no literal explains.
    for begin, finish, value in structures_in(text):
        # Whether the raw rules can SEE the key, not whether its name appears somewhere in the structure.
        # `{"note":"password","\u0070assword":"..."}` has the word in an unrelated value, and reading that
        # as coverage left the encoded member's credential standing.
        visible = visible_secret_keys(text[begin:finish])
        hidden = [key for key in encoded_secret_keys(value, home) if key.lower() not in visible]
        if hidden:
            STATS["encoded_secret_key"] += 1
            found.append((begin, finish, f'"{FLOOR.PLACEHOLDER}"', SECRET_SPAN))

    # The ESCAPED spelling, over the region that carries it rather than over the whole block. Requiring the
    # whole text to be one level of escaping let a decodable part elsewhere excuse an undecodable claim: a
    # plain structure followed by an escaped `"password": "..."` was read by nothing at all.
    for begin, finish in escaped_regions(text):
        region = text[begin:finish]
        decoded = relaxed_decode(region)
        if decoded is None or not holds_secret(decoded, home, depth + 1):
            continue
        mapping = escape_map(region)
        if not mapping:
            STATS["unmappable_escape"] += 1
            found.append((begin, finish, FLOOR.PLACEHOLDER, SECRET_SPAN))
            continue
        # EVERY extent the decoded level yields, not the deepest set alone: `decoded_extents(...) or
        # mask_extents(...)` dropped the decoded level's own floor, keyed and path spans whenever a deeper
        # extent existed, so a plain home path beside an encoded token was left for a second projection.
        inner = list(mask_extents(decoded, home, depth + 1))
        for start, end, replacement, rank in inner:
            if end <= len(mapping) and start < end:
                found.append((begin + mapping[start][0], begin + mapping[end - 1][1], replacement, rank))
    return found


def escaped_regions(text):
    """The regions of `text` to read as one level of JSON string escaping, as `(start, end)`.

    The whole text is a region whenever it decodes as one - which does NOT require an escaped quote in it.
    Keying this on `\\"` meant `sk\\u002dabcdefghijklmnopqrst` and an encoded home path were examined by
    nothing at all: no raw rule matches the escaped spelling, no literal scanner finds a quote, and the
    closing rule finds no keyed claim. Where escaped quotes are present they also give their own region, from
    the first to the last, so a block that is plain in one part and escaped in another is read in both and
    neither part excuses the other."""
    regions = []
    if relaxed_decode(text) is not None:
        regions.append((0, len(text)))
    if '\\"' in text:
        first, last = text.index('\\"'), text.rindex('\\"') + 2
        region = (first, max(last, first + 2))
        if region not in regions:
            regions.append(region if relaxed_decode(text[region[0]:region[1]]) is not None else (0, len(text)))
    return regions


def mask_extents(text, home=None, depth=0):
    """Every extent of `text` that must be masked, in `text`'s own coordinates: what the floor claims, the
    whole value of every secret-named key, the owner's home paths, and whatever only decoding reveals."""
    return (floor_spans_normalised(text) + keyed_spans(text) + path_spans(text, home)
            + decoded_extents(text, home, depth))


VERIFY_DEPTH = 16        # decode layers the verifier descends - comfortably past MAX_EMBEDDED
VERIFY_BUDGET = 4096     # strings it will examine for one block, so a pathological input cannot hang a run


class Reach:
    """What one verification traversal was able to look at.

    It carries the budget because the honest answer to "is this output clean" depends on whether the whole
    output was read. A traversal that stopped early has not verified anything, and `exhausted` is how it
    says so instead of returning a clean-looking list."""

    def __init__(self):
        self.budget, self.exhausted, self.seen = VERIFY_BUDGET, False, set()
        self.reason = None     # the strict closure's own words for WHY it stopped


HIGH_SURROGATE = range(0xD800, 0xDC00)
LOW_SURROGATE = range(0xDC00, 0xE000)
_HEX4 = re.compile(r"[0-9a-fA-F]{4}")


def vf_pair(text, index):
    """`(scalar, consumed)` for the `\\uXXXX` escape at `index` - or `(None, 0)` when it cannot be read.

    A surrogate PAIR is one character. Reading the halves separately produced two lone surrogates, which no
    normalisation maps: a compatibility name written in mathematical-alphanumeric letters arrived as
    unmappable halves and the floor was never asked about the name it spells. A lone surrogate is therefore
    not a character this reader can produce - it says so instead, and on the strict side that refuses the
    quote."""
    if _HEX4.fullmatch(text[index + 2:index + 6]) is None:
        return None, 0
    code = int(text[index + 2:index + 6], 16)
    if code in HIGH_SURROGATE:
        if text[index + 6:index + 8] == "\\u" and _HEX4.fullmatch(text[index + 8:index + 12]):
            low = int(text[index + 8:index + 12], 16)
            if low in LOW_SURROGATE:
                return chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)), 12
        return None, 0       # a lone high surrogate
    if code in LOW_SURROGATE:
        return None, 0       # a lone low surrogate
    return chr(code), 6


def vf_unescape(text):
    """One layer of JSON string escaping, undone by the VERIFIER's own reader.

    Written here rather than borrowed so the backstop does not share a decoder with the thing it checks: a
    mistake in the projection's reading of an escape is exactly what this is here to catch. Returns None
    when `text` is not one layer of such escaping - which includes a lone surrogate, since this reader
    produces characters and a lone surrogate is not one."""
    out, index = [], 0
    while index < len(text):
        char = text[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        if index + 1 >= len(text):
            return None
        kind = text[index + 1]
        if kind == "u":
            if index + 6 > len(text):
                return None
            scalar, consumed = vf_pair(text, index)
            if scalar is None:
                return None
            out.append(scalar)
            index += consumed
            continue
        simple = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f",
                  "n": "\n", "r": "\r", "t": "\t"}
        if kind not in simple:
            return None
        out.append(simple[kind])
        index += 2
    return "".join(out)


def vf_relax(text):
    """`text` with every `\\uXXXX` escape resolved where this reader can resolve it, surrogate pairs
    included, for text that is not one clean layer of escaping throughout."""
    out, index = [], 0
    while index < len(text):
        if text.startswith("\\u", index):
            scalar, consumed = vf_pair(text, index)
            if scalar is not None:
                out.append(scalar)
                index += consumed
                continue
        if text.startswith("\\/", index):
            out.append("/")
            index += 2
            continue
        out.append(text[index])
        index += 1
    return "".join(out)


class Members(list):
    """A decoded JSON object as its members IN ORDER, duplicates kept.

    `json.loads` keeps the last value for a repeated key, and a repeated secret-named key standing behind a
    masked one is exactly the shape that got through: the verifier would have seen one `password` member,
    already masked, and never the second."""


def vf_load(text):
    """`text` read as a JSON document by the VERIFIER, with every member preserved - or None."""
    try:
        return json.loads(text, object_pairs_hook=Members)
    except (ValueError, RecursionError):
        return None


def vf_structures(text):
    """Every JSON document embedded in `text`, decoded by the verifier's own scan, members preserved."""
    found, decoder, index = [], json.JSONDecoder(object_pairs_hook=Members), 0
    while index < len(text):
        if text[index] not in "{[":
            index += 1
            continue
        try:
            value, end = decoder.raw_decode(text, index)
        except (ValueError, RecursionError):
            index += 1
            continue
        found.append(value)
        index = max(end, index + 1)
    return found


# The verifier's own reading of a keyed fragment in TEXT. Written here, with its own patterns, because the
# question is what a READER sees - a name, a separator a few characters later, a value - and not where a
# value's extent begins and ends. The mapping's scanner answers the second question and is the thing being
# checked; a fragment in decoded mixed text (`"\u0070assword":"canary"` after a plain structure) is read by
# neither the floor nor the member rule, and that is the gap this closes.
# A name token, matched WHOLE. The cap of 41 characters split a long key into two tokens, neither of which
# the floor claims - `xxxxxxxx...password` became `...pas` and `sword`, and the fragment went through. The
# boundary is the one a key name has: a run of name characters, however long.
VF_NAME = re.compile(r"[^\W\d][\w.-]*", re.UNICODE)


# Whitespace, quotes and escape characters that may stand between a key and its separator - newlines
# included. A quoted key followed by a newline and then the colon is one association a reader sees and the
# per-line scan could not: the key's line had no separator on it at all.
VF_GAP = re.compile(r"[\s\"'\\]*")


def vf_region(text, after):
    """The value region beginning at `after`: everything to the end of that line, or the next non-empty line
    when the line ends at the separator.

    The unit is the logical line because every bounded unit tried before it - a token, a span of so many
    characters - had a next bound for the following round to find. A line has no number in it.

    One exception, and it is not a bound: a value that OPENS a structure is read from the whole text rather
    than from the line, because a structure's extent is a decoding question and a line cut through it left
    `[` alone - which then read as a structure this verifier cannot parse, and so as the owner-pending
    class. A structure that spans lines has a complete readable extent, and this is how it keeps it."""
    opening = text[after:].lstrip()
    if opening[:1] in ("{", "[", '"', "'"):
        # A quoted scalar and a structure both have an extent a scanner decides, not a line: the scalar's
        # own content is read to its closing quote wherever that stands, and what follows it has to be read
        # too, since a member's separator may sit on the next line. A line cut through either of them left
        # `[` alone - read as unparseable, and so as the owner-pending class - or cut the continuation that
        # tells packaging from content.
        return text[after:]
    end = text.find("\n", after)
    region = text[after:] if end < 0 else text[after:end]
    if region.strip():
        return region
    for later in text[end + 1:].split("\n") if end >= 0 else []:
        if later.strip():
            return later
    return region


def vf_keyed(text):
    """Every `(name, value region)` fragment of `text` whose name the floor treats as a secret's.

    Two readings, and a fragment either matches gives a region. The first is the line rule: a secret-named
    token, then a `:` or `=` anywhere later ON THE SAME LINE, any distance. The second crosses whitespace,
    quotes and escape characters from the token to the separator even over a newline, because
    `"password"\\n: "canary"` is an association a reader makes and the line rule reads as two lines, one
    with no separator on it."""
    found = []
    for match in VF_NAME.finditer(text):
        if not secret_key(match.group(0)):
            continue
        line_end = text.find("\n", match.end())
        line_rest = text[match.end():] if line_end < 0 else text[match.end():line_end]
        positions = [at for at in (line_rest.find(":"), line_rest.find("=")) if at >= 0]
        if positions:
            found.append((match.group(0), vf_region(text, match.end() + min(positions) + 1)))
            continue
        gap = VF_GAP.match(text, match.end())
        at = gap.end() if gap else match.end()
        if at < len(text) and text[at] in ":=":
            found.append((match.group(0), vf_region(text, at + 1)))
    return found


def vf_scalar(region):
    """`(content, end)` for the quoted scalar `region` begins with - or `(None, 0)`.

    A scanner, not a pattern: it tracks the opening quote and the escapes, so a comma, a brace or a newline
    INSIDE the scalar belongs to the scalar. It also returns where the scalar ENDED, because what follows a
    scalar is not the scalar's: replacing the region with the content alone discarded a suffix, and
    `"<REDACTED>"suffix_canary` passed as masked. None means this scanner could not read the scalar to its
    close, which is itself a finding rather than a pass."""
    text = region.lstrip()
    offset = len(region) - len(text)
    if not text or text[0] not in "\"'":
        return None, 0
    quote, index, out = text[0], 1, []
    while index < len(text):
        character = text[index]
        if character == "\\":
            if index + 1 >= len(text):
                return None, 0          # an escape with nothing behind it
            out.append(text[index + 1])
            index += 2
            continue
        if character == quote:
            return "".join(out), offset + index + 1
        out.append(character)
        index += 1
    return None, 0                      # a scalar that never closes


def vf_packaging(remainder):
    """Whether what follows a value is the value's PACKAGING, or the start of a further member of the
    structure the value sat in.

    Packaging is whitespace, a comma or semicolon, and the brackets that close the structure. Content is
    anything else - and content directly after a masked scalar is what `"<REDACTED>"suffix_canary` hid
    behind, which is why the remainder is validated at all.

    A remainder that BEGINS a further member is neither: `, "other": "x"}` is the rest of the object, and
    the member rule reads those members as members. Treating it as content made every one-line JSON object
    with a masked member a finding, and the member rule is the better reader of exactly that shape - it
    sees each member's key with its own value, which is what this text rule exists to approximate when
    nothing can be parsed at all."""
    text = remainder.strip()
    if all(character in " \t\r\n,;}])" for character in text):
        return True
    # the brackets that close the structures the value sat in, and then the rest of an enclosing one
    while text and text[0] in " \t\r\n}])":
        text = text[1:].lstrip()
    if not text:
        return True
    if text[0] not in ",;":
        return False
    # ... and what follows the comma must BE a further member - something with a separator of its own. Any
    # comma-prefixed text used to pass, so `"<REDACTED>",v15suffix` was read as packaging and the suffix
    # belonged to nobody: the member rule owns members, and that was not one.
    rest = text[1:]
    # the whole remainder, not its first line: a member's separator may stand on the next one, which is
    # exactly the shape `"password"\n: "..."` has
    return not rest.strip() or ":" in rest or "=" in rest


def vf_leaves(value):
    """Every leaf VALUE of a decoded value, so each one can be held against the mask.

    A key is not one. A key names a value; it is read by the member rule and by the detectors over the text,
    and counting it as a leaf made `{"password":{"a":"<REDACTED>"}}` a finding because `a` is not the
    mask."""
    if isinstance(value, Members):
        found = []
        for _key, item in value:
            found += vf_leaves(item)
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for item in value:
            found += vf_leaves(item)
        return found
    return [value]


def vf_exempt(region):
    """Whether a value region holds the mask and nothing else.

    Three shapes, and each is read as what it is rather than stripped into submission:

    * a quoted scalar - read with the scanner, its CONTENT compared exactly with the mask, and whatever
      follows the closing quote validated separately as packaging;
    * a structure whose extent this verifier can read - every leaf of it compared with the mask, so the key
      association survives. The owner-pending exemption is for a structure whose extent genuinely cannot be
      read, not for anything that merely begins with a bracket: a complete readable array held an ordinary
      string and was exempted on its opening character alone;
    * anything else - packaging removed from the OUTSIDE only, and what remains compared exactly.
    """
    text = region.strip()
    if not text:
        return True
    if text[0] in ('"', "'"):
        content, end = vf_scalar(text)
        if content is None:
            return False
        return content in ("", FLOOR.PLACEHOLDER, HOME_MASK) and vf_packaging(text[end:])
    decoder = json.JSONDecoder(object_pairs_hook=Members)
    if text[0] in "{[":
        try:
            value, end = decoder.raw_decode(text)
        except (ValueError, RecursionError):
            return True      # an extent this verifier cannot read: the owner-pending class, unchanged
        if not vf_packaging(text[end:]):
            return False
        return all(leaf is None or isinstance(leaf, str) and leaf in ("", FLOOR.PLACEHOLDER, HOME_MASK)
                   for leaf in vf_leaves(value))
    # a bare JSON scalar - a number, a boolean, a null - read as ONE value, so the members after it on the
    # same line are not swept into this one's region
    try:
        value, end = decoder.raw_decode(text)
    except (ValueError, RecursionError):
        value, end = None, -1
    if end >= 0 and not isinstance(value, (dict, list, Members)):
        return value is None and vf_packaging(text[end:])
    previous = None
    while text != previous:
        previous = text
        text = text.strip().rstrip(",;").rstrip()
        while text and text[-1] in "}])":
            text = text[:-1].rstrip(",;").rstrip()
    return text in ("", FLOOR.PLACEHOLDER, HOME_MASK)


def vf_unfinished(text):
    r"""Whether an escape run in `text` STARTS and no reading of this verifier consumes it.

    Asked per run, and of this string alone: an unrelated plain structure elsewhere in the block used to
    answer for a run nothing had read. A run is consumed when it is a valid JSON escape, or when the lenient
    reading can drop its backslash - which it cannot do before an actual newline, since that reading does
    not cross one. So three runs are unfinished: a backslash at the very end, a backslash before a real
    newline or carriage return, and a `\u` with fewer than four hex digits behind it. A Windows path is none
    of them."""
    index = 0
    while index < len(text):
        if text[index] != "\\":
            index += 1
            continue
        if index + 1 >= len(text):
            return True
        following = text[index + 1]
        if following == "\\":
            index += 2
            continue
        if following in "\r\n":
            return True
        if following == "u":
            scalar, consumed = vf_pair(text, index)
            if scalar is None:
                return True      # too few hex digits, or a lone surrogate: a run nothing here can read
            index += consumed
            continue
        index += 2
    return False


JSON_ESCAPE_TABLE = set('"\\/bfnrtu')


def vf_outside_table(text):
    r"""The first backslash sequence in `text` that the JSON escape table does not define - or None.

    The STRICT side's own reading, and the whole table: `\" \\ \/ \b \f \n \r \t` and `\uXXXX` with a
    surrogate pair joined. Anything else - `\x41`, `\q`, `\U0001D5C9`, a short `\u12`, a trailing lone
    backslash - is a sequence this reader does not define, so it cannot say what the text spells.

    Deliberately NOT the lenient reading. That reading drops a backslash before anything at all, which is
    useful for finding what a careless reader recovers and useless for deciding what a text IS: it made
    `\x41` read as `x41`, nothing reported a layer left undone, and an unsupported escape passed strict
    admission. A Windows path is refused here for the same reason, which is the conservative direction on
    the side that stores text for sharing."""
    index = 0
    while index < len(text):
        if text[index] != "\\":
            index += 1
            continue
        if index + 1 >= len(text):
            return "\\"                              # a trailing lone backslash
        following = text[index + 1]
        if following not in JSON_ESCAPE_TABLE:
            return text[index:index + 2]
        if following == "u":
            scalar, consumed = vf_pair(text, index)
            if scalar is None:
                return text[index:index + 6]         # short, or a lone surrogate
            index += consumed
            continue
        index += 2
    return None


def vf_undecodable(value, depth=0, seen=None):
    """The first sequence outside the JSON escape table that the STRICT traversal reaches - or None.

    At any decode depth: a quote may carry an unsupported escape behind a layer of escaping, or inside a
    JSON structure it spells. The traversal decodes with the table alone (`vf_unescape`, `vf_relax`,
    `vf_load`, `vf_structures`) and tracks the answer itself, so the lenient reading is never asked."""
    seen = set() if seen is None else seen
    if isinstance(value, Members):
        for key, item in value:
            for part in (key, item):
                found = vf_undecodable(part, depth + 1, seen)
                if found is not None:
                    return found
        return None
    if isinstance(value, dict):
        return vf_undecodable(Members(value.items()), depth, seen)
    if isinstance(value, (list, tuple)):
        for item in value:
            found = vf_undecodable(item, depth + 1, seen)
            if found is not None:
                return found
        return None
    if not isinstance(value, str) or value in seen or depth > VERIFY_DEPTH:
        return None
    seen.add(value)
    outside = vf_outside_table(value)
    if outside is not None:
        return outside
    deeper = [form for form in (vf_unescape(value), vf_relax(value), vf_load(value))
              if form is not None and form != value] + list(vf_structures(value))
    for form in deeper:
        found = vf_undecodable(form, depth + 1, seen)
        if found is not None:
            return found
    return None


def all_mask(value):
    """Whether a value is the mask and nothing else - for a structure, every leaf of it.

    This is the verifier's own test of a secret-named member. It asks nothing about what the projection did
    or did not locate; it asks what the value IS. An absent value - null, empty text, an empty structure -
    discloses nothing and is not a secret."""
    if value is None or value == "" or value == [] or isinstance(value, Members) and not value:
        return True
    if isinstance(value, str):
        return is_mask(value)
    if isinstance(value, Members):
        return all(all_mask(item) for _key, item in value)
    if isinstance(value, (list, tuple)):
        return all(all_mask(item) for item in value)
    return False     # a number, a boolean: not the mask, so a secret-named key still holds its value


def vf_members(value):
    """The `(key, value)` members of one decoded object, duplicates and order preserved.

    One object, not its nested ones: `every_spelling` hands every object it reaches to `discloses` as a form
    of its own, so recursing here would only ask the same question twice - and a second reader of the same
    rule is a place for the two to disagree."""
    return [(key, item) for key, item in value] if isinstance(value, Members) else []


def every_spelling(value, depth=0, reach=None):
    """Every string and every decoded value the VERIFIER can reach from `value`, by its own decoder.

    Returns `(forms, reach)`. A form is a string to run the detectors over, or a `Members` object whose
    members are checked as key/value pairs - the association is what matters, and flattening keys and values
    into one list of strings is what lost it. `reach.exhausted` is set when the traversal stopped with
    something still to decode: its depth limit, its budget, or a layer that starts and cannot be read."""
    reach = Reach() if reach is None else reach
    out = []
    if isinstance(value, Members):
        out.append(value)
        for key, item in value:
            out += every_spelling(key, depth, reach)[0] + every_spelling(item, depth, reach)[0]
        return out, reach
    if isinstance(value, dict):
        for key, item in value.items():
            out += every_spelling(key, depth, reach)[0] + every_spelling(item, depth, reach)[0]
        return out, reach
    if isinstance(value, (list, tuple)):
        for item in value:
            out += every_spelling(item, depth, reach)[0]
        return out, reach
    if not isinstance(value, str):
        return out, reach
    if value in reach.seen:
        return out, reach
    if reach.budget <= 0:
        reach.exhausted = True
        return out, reach
    reach.budget -= 1
    reach.seen.add(value)
    out.append(value)

    deeper = []
    parsed = vf_load(value)
    if parsed is not None and not isinstance(parsed, (str, int, float, bool)):
        deeper.append(parsed)
    plain = vf_unescape(value)
    if plain is not None and plain != value:
        deeper.append(plain)
    # a hand-relaxed unescaping, for text that is not one clean layer throughout: an encoded run inside
    # ordinary prose is the shape that defeated a whole-body decode
    relaxed = vf_relax(value)
    if relaxed != value:
        deeper.append(relaxed)
    # ... and a fully lenient reading, where a backslash before anything at all is dropped. Six layers of
    # `\u005c` decode down to `sk\-abcdefghijklmnopqrst`: no further layer is valid JSON escaping, the floor
    # does not match the backslash, and the credential stood there in a form any careless reader recovers.
    lenient = re.sub(r"\\(.)", r"\1", value)
    if lenient != value and lenient != relaxed:
        deeper.append(lenient)
    deeper += vf_structures(value)

    # An escape run that starts and cannot be read is a layer this traversal did not finish - asked per
    # run, and of this string alone. Testing it as "and nothing else decoded" let an unrelated plain
    # structure elsewhere in the block answer for the run.
    if vf_unfinished(value):
        reach.exhausted = True

    if deeper and depth >= VERIFY_DEPTH:
        reach.exhausted = True
        return out, reach
    for item in deeper:
        out += every_spelling(item, depth + 1, reach)[0]
    return out, reach


def discloses(text, home=None):
    """What a projected block still discloses, named by the detector that found it - or None.

    Three rules, each LOCAL and TOTAL - they ask what the output contains, never what the projection did
    with it:

    * a floor match in any spelling the verifier can reach;
    * the owner's home path in any spelling;
    * a secret-named key whose value is not exactly the mask, for EVERY member of every decoded object,
      duplicates included and whatever whitespace stands around the colon.

    The third used to be asked through the projection's own textual scanner, which reads a key only where it
    can locate its value, and whose mapping had already declared the key "covered" by NAME - so a duplicate
    member, or one with a newline before its colon, was skipped by both. A backstop that consults the
    mapping cannot catch the mapping. `self_test` holds that structurally: these functions call nothing of
    the mapping."""
    forms, reach = every_spelling(text)
    # The member rule first, over every decoded object: when a block is a document, that is the reading that
    # names what was found, and the text rule below would otherwise answer for it with a coarser name.
    for form in forms:
        if isinstance(form, Members):
            for key, item in vf_members(form):
                if isinstance(key, str) and secret_key(key) and not all_mask(item):
                    return "secret-named key"
    for form in forms:
        if isinstance(form, Members):
            continue
        if any(pattern.search(form) for pattern in floor_patterns()):
            return "floor"
        if any(pattern.search(form) for pattern in home_patterns(home)):
            return "home path"
        if any(not vf_exempt(value) for _name, value in vf_keyed(form)):
            return "keyed fragment"
    return "verifier-limit" if reach.exhausted else None


def spellings_of(value):
    """Just the forms `every_spelling` reaches - for a caller sweeping artifacts, where the traversal's own
    reach is reported by the projection that produced them rather than asked again here."""
    return [form for form in every_spelling(value)[0] if isinstance(form, str)]


# A name token, Unicode-aware. `\w` is Unicode in Python 3, so a name written in any script is one token;
# the ASCII class this used to carry split `paſſword` into `pa` and `word` and the floor's own matching never
# saw the name at all.
VF_TOKEN = re.compile(r"[\w.-]+", re.UNICODE)


# AB#0: the categories whose characters render nothing of their own - the three mark categories, the
# format characters, and the unassigned points, which have no glyph at all and are where a tag block's
# holes live.
VF_INVISIBLE_CATEGORIES = ("Mn", "Mc", "Me", "Cf", "Cn")

# ... and the characters NO category names. The variation selectors, their supplement, the Mongolian
# U+180B..U+180F run and the tag block are all covered above, so listing them would be lines no revert
# can make fail; the control asserts this list holds nothing a category covers, which is what keeps that
# true as Unicode assigns new characters.
VF_IGNORABLE = frozenset([0x115F, 0x1160, 0x3164, 0xFFA0])   # Hangul and halfwidth fillers: ordinary
                                                             # letters (Lo) that render nothing


def vf_invisible(character):
    """Whether `character` renders nothing of its own, or only modifies the character beside it.

    A skeleton that drops only `Mn` closed accents and left every other invisible character standing, so
    `pass<ZWSP>word` tokenised as two names and the floor was asked about neither. The test is the property
    rather than a list of attacks: all three mark categories (`Mn`, `Mc`, `Me`), the format characters
    (`Cf` - zero-width space, joiner and non-joiner, soft hyphen, the bidi controls, the word joiner, the
    tag characters), the unassigned points (`Cn`), which have no glyph at all, and the fillers listed
    above, which are ordinary letters to Unicode and render nothing to a reader.

    This is the strict side, where over-refusal costs a quote and under-refusal ships a credential. It is
    NOT a confusable mapping: a Cyrillic or Greek lookalike renders a character of its own, and the owner
    placed those outside the strict rule's scope on 2026-10-22. The rule covers spelling variants - the
    escape table, Unicode normalisation, and characters that render nothing - and stops there."""
    return (unicodedata.category(character) in VF_INVISIBLE_CATEGORIES
            or ord(character) in VF_IGNORABLE)


def vf_skeletons(text):
    """The spellings of `text` the strict rule asks the floor about.

    A union rather than one canonical form, because no single normalisation preserves every name the floor
    recognises. Casefolding `APİ_KEY` (U+0130) inserts a combining dot and the floor's `api[_-]?key` no
    longer matches it; NFKC alone leaves a fullwidth `ｓｅｃｒｅｔ` unmatched; and a combining acute over an
    `o` hides `password` from both. So the floor is asked about all of them:

    * the text as it stands, which is what the floor itself would see;
    * NFKC, which folds compatibility spellings;
    * casefold, which folds case across scripts;
    * NFKC of the casefold of NFKC, which folds the two in the order that settles U+0130;
    * a skeleton - NFKD, every character that renders nothing of its own dropped, casefolded, NFKC -
      which folds accents away and closes `pass<ZWSP>word` with them.

    Over-refusal is acceptable here: a refused quote is simply not stored, and the caller quotes a span
    that names nothing. Under-refusal is a credential in a shared record."""
    bare = "".join(character for character in unicodedata.normalize("NFKD", text)
                   if not vf_invisible(character))
    return list(dict.fromkeys([
        text,
        unicodedata.normalize("NFKC", text),
        text.casefold(),
        unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", text).casefold()),
        unicodedata.normalize("NFKC", bare.casefold()),
    ]))


def vf_name_in(text):
    """The first complete name token in THIS ONE string that the floor treats as a secret's - or None.

    `vf_secret_name` is this asked about each of `vf_skeletons`. The split exists so strict admission can
    hand all three of its detectors the same string: when the name detector expanded the spellings itself
    and the other two did not, only names were judged in normalised form (AC#0)."""
    for match in VF_TOKEN.finditer(text):
        if secret_key(match.group(0)):
            return match.group(0)
    return None


# AD#0 / AD#1: the strict side's spelling set is a CLOSURE, not a pipeline. Two orders were missing when
# the set was "each decode layer, expanded by the skeleton": invisible characters were stripped only in
# the casefolded skeleton, so a case-sensitive owner path never saw a stripped, case-preserved spelling;
# and an escape that normalisation REVEALS (a fullwidth backslash NFKC turns into `\`) was never decoded,
# because decoding ran before normalising and never again.
VF_CLOSURE_LIMIT = 256       # strings; a quote whose closure is larger is refused, never truncated
VF_CLOSURE_ROUNDS = 12       # ... and so is one that is still growing after this many rounds


def vf_transforms(text):
    """Every SINGLE-STEP transform the closure applies to one string.

    One layer undone by the JSON escape table (strict and relaxed), NFKC, casefold, the invisible
    characters stripped, and NFKD. Each is one step and the closure composes them, so no order is
    privileged: `casefold then decode` is in the set exactly as `decode then casefold` is, and the
    skeleton of r20 is now one path through these rather than a form of its own."""
    out = []
    plain = vf_unescape(text)
    if plain is not None:
        out.append(plain)
    out.append(vf_relax(text))
    out.append(unicodedata.normalize("NFKC", text))
    out.append(unicodedata.normalize("NFKD", text))
    out.append(text.casefold())
    out.append("".join(character for character in text if not vf_invisible(character)))
    return [form for form in out if form and form != text]


def vf_all_spellings(quote):
    """`(spellings, members, reach)` - the closure of `quote` under `vf_transforms`.

    One function so the three triggers cannot diverge, and a closure so no composition of steps can be
    missing. Every string in the set has had every transform applied to it, and the result was already in
    the set, which the self-test asserts directly.

    Bounded, and the bound REFUSES rather than truncates: `reach.exhausted` is set when the set would pass
    `VF_CLOSURE_LIMIT` strings, when it is still growing after `VF_CLOSURE_ROUNDS` rounds, or when any
    string in it holds a sequence the JSON escape table does not define. A truncated set would be a clean
    answer about a quote nobody finished reading."""
    spellings, members, reach = [], [], Reach()
    seen, pending, rounds = set(), [quote], 0
    while pending:
        rounds += 1
        if rounds > VF_CLOSURE_ROUNDS:
            reach.exhausted, reach.reason = True, f"its spellings were still growing after {rounds - 1} rounds"
            return [], [], reach
        following = []
        for text in pending:
            if not isinstance(text, str) or text in seen:
                continue
            if len(seen) >= VF_CLOSURE_LIMIT:
                reach.exhausted, reach.reason = True, f"it spells more than {VF_CLOSURE_LIMIT} strings"
                return [], [], reach
            seen.add(text)
            spellings.append(text)
            outside = vf_outside_table(text)
            if outside is not None:
                reach.exhausted = True
                reach.reason = f"one of its spellings holds {outside!r}, which the JSON escape table does " \
                               f"not define"
                return [], [], reach
            following += vf_transforms(text)
            for structure in [vf_load(text)] + list(vf_structures(text)):
                following += vf_structure_strings(structure, members)
        pending = following
    return spellings, members, reach


def vf_structure_strings(value, members):
    """The strings inside a decoded structure, collecting its member objects into `members` on the way."""
    strings, stack = [], [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Members):
            members.append(item)
            for key, member in item:
                stack += [key, member]
        elif isinstance(item, dict):
            members.append(Members(item.items()))
            stack += list(item.keys()) + list(item.values())
        elif isinstance(item, (list, tuple)):
            stack += list(item)
        elif isinstance(item, str):
            strings.append(item)
    return strings


# Self-test only: when this is a dict, admission records which strings each detector was asked about, so
# a control can assert the three sets are identical rather than trusting that they are.
SPELLING_PROBE = None


def vf_probe(detector, spelling):
    if SPELLING_PROBE is not None:
        SPELLING_PROBE.setdefault(detector, []).append(spelling)


def vf_secret_name(text):
    """The first complete name token in `text` that THE FLOOR treats as a secret's - or None.

    Two properties, and the previous form of this gave up one for the other. The floor is asked directly,
    with its own pattern, its own end-of-name context and its own flags, so the strict rule cannot be
    narrower than the floor; and it is asked about whole TOKENS, so `input_tokens` and `tokenizer` are
    ordinary names rather than names that happen to contain one. An alternation scraped out of the floor's
    pattern had neither property: unanchored, it claimed every name containing `token`, and recompiled, it
    lost the recognition the floor's own flags give it."""
    for spelling in vf_skeletons(text):
        found = vf_name_in(spelling)
        if found is not None:
            return found
    return None


def evidence_quote_admissible(quote, home=None):
    """Whether a quote may stand as evidence: it names no secret at all, in any spelling.

    This is STRICTER than the projection's rule and deliberately so. The projection decides what a window
    may show, where a secret-named key with a masked value is a correct and useful thing to show. A quote is
    a different object: it is lifted out of its block and carried into a report, so the context that made
    `"password": "<REDACTED>"` safe to read does not travel with it. This refuses a quote that, in any
    spelling the verifier can reach, holds a secret-named token, a floor match, or the owner's home path -
    the key's NAME included, masked value or not.

    Owner decision of 2026-10-21: the rule is strict and blocking for everything persisted for sharing.
    `evidence.make` and `evidence.append` both ask it."""
    # AA#0: the strict traversal decides undecodability itself, with the JSON escape table and nothing
    # else. Inheriting the lenient reading's treatment of an unsupported escape let `\x41` pass as `x41`.
    outside = vf_undecodable(quote)
    if outside is not None:
        return False, f"undecodable: the quote holds {outside!r}, which the JSON escape table does not define"
    spellings, members, reach = vf_all_spellings(quote)
    if reach.exhausted:
        # The strict side's principle, and it is a principle rather than a case: a valid surrogate pair
        # decodes to its scalar, and a lone surrogate, an invalid escape or any decoding this traversal
        # cannot complete refuses the quote. An encoding nobody here can finish reading is an encoding
        # whose content nobody here can rule out.
        return False, ("undecodable: " + (reach.reason or
                       "the quote holds an encoding this verifier cannot finish reading"))
    for member in members:
        for key, _item in vf_members(member):
            if isinstance(key, str):
                named = vf_secret_name(key)
                if named:
                    return False, f"the quote names the secret-named key {named!r}"
    # AC#0: one set, three detectors, one loop. The name detector used to expand the normalised spellings
    # inside itself while the floor's value patterns and the owner-path detector saw the decoded string
    # alone, so a fullwidth or zero-width-spaced owner path was judged by a narrower set than a name was.
    floors, homes = floor_patterns(), home_patterns(home)
    detectors = (
        ("floor", lambda text: "the quote holds a credential the floor claims"
         if any(pattern.search(text) for pattern in floors) else None),
        ("home", lambda text: "the quote holds the owner's home path"
         if any(pattern.search(text) for pattern in homes) else None),
        ("name", lambda text: (lambda named: f"the quote names the secret-named token {named!r}"
                               if named is not None else None)(vf_name_in(text))),
    )
    for spelling in spellings:
        for detector, ask in detectors:
            vf_probe(detector, spelling)
            why = ask(spelling)
            if why is not None:
                return False, why
    return True, None


BLANKED = collections.Counter()    # run-scoped: how many BLANKING OPERATIONS the backstop ran, by detector
BLOCKS = collections.Counter()     # ... and how many CONTENT BLOCKS it blanked, counted once per block
_OPEN_BLOCK = []                   # the detectors seen while the current content block was projected


def parses_as_json(text):
    """Whether this block is a JSON document."""
    try:
        json.loads(text)
    except (ValueError, RecursionError):
        return False
    return True


def blank_for(original):
    """What a blanked block becomes: the mask, as a valid JSON string when the block itself was valid JSON.

    Blanking a JSON document to a bare `<REDACTED>` left a block that no longer parsed, and a window a
    reader opens is read as JSON by everything downstream."""
    if not parses_as_json(original):
        return FLOOR.PLACEHOLDER
    return json.dumps(FLOOR.PLACEHOLDER, ensure_ascii=False)


def emit(original, projected, home=None, masked=None):
    """THE EXIT. Every projected block this module returns leaves through here, and here it is verified.

    One choke point rather than a call at each site: the structured path used to serialise its walk and
    return it unverified, so two leaves that were each clean on their own emitted a floor match across the
    member boundary between them - and a second projection then masked it, which is also how idempotence
    broke. What a reader, an index and an evidence quote all see is the FINAL emitted text, so that is the
    text the backstop reads. `self_test` holds this structurally: every `return` in the block-producing
    functions is a call to this one."""
    STATS["emitted"] += 1
    reason = discloses(projected, home)
    if not reason and parses_as_json(original) and not parses_as_json(projected):
        # valid JSON in, valid JSON out: a window a reader opens is read as JSON by everything downstream,
        # and a masking that breaks the syntax is a block nothing can quote from
        reason = "broken syntax"
    if reason:
        STATS[f"blanked:{reason}"] += 1
        BLANKED[reason] += 1          # one blanking operation; a block's leaves may each contribute one
        if _OPEN_BLOCK:
            _OPEN_BLOCK[-1].append(reason)
        projected = blank_for(original)
    return note_change(original, projected, "a masked span", masked)


def project_text(text, home=None, depth=0, masked=None):
    """One string's projection: ONE monotone pass in the original text's own coordinates.

    There is no decoded candidate and no fallback, because the gap between those two paths is what leaked in
    four consecutive rounds - each new rule closing one side and opening the other. Instead every source of
    masking answers in the SAME coordinates, the union of their extents is masked once, and nothing is
    re-serialised: a document a person reads keeps its formatting, with the masked extents replaced.

    Masks only grow, so the pass is monotone, and a mask extent is never a secret - `is_mask` is exact - so
    projecting a projection changes nothing."""
    if undecodable_claim(text, depth):
        STATS["undecodable_claim"] += 1
        return emit(text, blank_for(text), home, masked)
    return emit(text, mask_spans(text, mask_extents(text, home, depth)), home, masked)


def note_change(before, after, what, masked):
    """`after`, recording that `what` changed the text when it did."""
    if masked is not None and after != before:
        masked.append(what)
    return after


def walk(value, home=None, depth=0, masked=None):
    """`value` with every string projected, every key projected, and the value of every secret-named key
    replaced whole. The structure is walked before anything is serialised, which is what lets a key be
    recognised at all: once `json.dumps` has run, the floor sees `"password":"x"` and reads no key there.
    `masked` collects the key names whose values were replaced, so a caller can tell a walk that changed
    something from one that only re-projected what was already projected."""
    if depth > MAX_DEPTH:
        return project_text(serialise(value), home, depth, masked)
    if isinstance(value, str):
        return project_text(value, home, depth, masked)
    if isinstance(value, dict):
        out = {}
        for key, inner in value.items():
            # A KEY's own masking counts as a change too. It was projected with `masked` withheld - "a key's
            # own masking is not the member's" - so a decoded structure whose only secret stood in a key
            # looked unchanged to `embedded`, which handed the original encoded text back out. The member it
            # belongs to is still decided by `secret_key(key)` below; what is recorded here is only that the
            # projection changed something, which is the question the caller is asking.
            name = project_text(key, home, depth, masked) if isinstance(key, str) else key
            if secret_key(key):
                if masked is not None:
                    masked.append(key)
                out[name] = FLOOR.PLACEHOLDER
            else:
                out[name] = walk(inner, home, depth + 1, masked)
        return out
    if isinstance(value, (list, tuple)):
        return [walk(item, home, depth + 1, masked) for item in value]
    return value


def serialise(value):
    """The characters of a value: the string itself, or its compact JSON."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def project_r22(value, home=None):
    """The projection of one content block. A lone surrogate (JSON can carry one; UTF-8 cannot) becomes `?`,
    so the characters can be written and read back.

    The walk projects each leaf, and then the SERIALISED result is verified: a claim can cross the boundary
    between two members that were each clean on their own, and the text a reader sees is this one."""
    text = serialise(walk(value, home)).encode("utf-8", "replace").decode("utf-8")
    return emit(text, text, home)


# version -> projection. A new version is added here and CURRENT moves. A superseded version is removed
# rather than kept: an old quote is made again from the source (§5.5), and a projection that under-redacts
# must not stay callable by anything that happens to name it.
VERSIONS = {"r22": project_r22}


def project(value, version=CURRENT, home=None):
    """The characters one content block projects to. `home` names the home to mask instead of this process's,
    so a test can state the owner it means rather than depending on the account the run happens to use.

    This is the content-block BOUNDARY, which is where a blanked block is counted. A structured block's
    leaves each pass through `emit`, so counting there counts operations rather than blocks - and a block
    with four masked leaves then read as four blanked blocks. Both figures are kept: `BLANKED` counts the
    operations, `BLOCKS` counts the blocks."""
    if version not in VERSIONS:
        raise KeyError(f"REDACTION_VERSION_MISMATCH {version!r}: no projection is registered under that version")
    _OPEN_BLOCK.append([])
    try:
        out = VERSIONS[version](value, home)
    finally:
        reasons = _OPEN_BLOCK.pop()
    if reasons and not _OPEN_BLOCK:    # a nested call belongs to the block that opened, not to a new one
        BLOCKS[reasons[0]] += 1
    elif reasons:
        _OPEN_BLOCK[-1].extend(reasons)
    return out



# ---- the sweep ------------------------------------------------------------------------------------

# A run directory's own verification, and it reads the layer the projection wrote rather than the bytes of
# the files holding it. The first sweep of this was a byte scan with one backslash of tolerance, and it
# judged a different text from the one the projection judged: over the live run of 2026-10-21 it reported
# 24 members where the decoded strings held 63, the thirteen worst of them scalars no structure story
# explains. A verification that reads a different text than the thing it verifies cannot be its evidence.
#
# `index/` is not scanned, and that is safe rather than convenient: a BM25 index's keys are the vocabulary
# of already-projected text and its values are document numbers, so a posting named `token` means the word
# occurred. Scanning it reported 2,794 members that were words. The sweep asserts that shape instead.
SWEPT = ("redacted", "views", "evidence")


_KEY_TAIL = re.compile(r'[\w.-]+\Z')


def key_at(text, name_start, name):
    """The whole key a floor name ends, for the report: the name plus the run of key characters before it.
    `_KEYED` anchors on the name alone, so the name is all a match carries - and `token` tells a reader far
    less than `page_token` about where to look."""
    before = _KEY_TAIL.search(text[:name_start])
    return (before.group(0) if before else "") + name


def already_masked(text, start):
    """Whether the value at `start` is already the placeholder. One recognition, used by the masker and by
    the sweep: when the two kept their own, the keyed rule wrote a repr's `\'<REDACTED>\'` and the sweep,
    which stripped only double quotes, reported the projection's own output as residual."""
    return text[start:].lstrip('\\"\'').startswith(FLOOR.PLACEHOLDER)


def residual_in(text):
    """The key name of every member of `text` whose key the floor calls a secret and whose value the
    projection did not replace. The same `_KEYED` the projection masks with, so the two cannot drift: a hit
    is a key the projection should have masked and did not."""
    out = []
    for match in _KEYED.finditer(text):
        start = _COMMENT.match(text, match.end()).end()
        if already_masked(text, start):
            continue
        name = match.group(0).rstrip(" \t:=").rstrip('"\'').rstrip("\\")
        out.append(key_at(text, match.start(), name))
    return out


def strings_of(value, depth=0):
    """Every string inside a parsed structure - the decoded layer, which is what a model receives."""
    if depth > MAX_DEPTH:
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings_of(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            yield from strings_of(item, depth + 1)


class Unswept(Exception):
    """A subject the sweep could not judge. It is raised rather than skipped, because a sweep that skips what
    it cannot read reports zero for the files it never looked at - and a window file is pretty-printed, so
    reading every file line by line skipped every window in the run while printing a clean result."""


def documents_in(path):
    """Every JSON document in one file: a `.json` file holds one, a `.jsonl` file one per line."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".jsonl":
        for number, raw in enumerate(records.jsonl_lines(text), 1):
            if not raw.strip():
                continue
            try:
                yield json.loads(raw)
            except ValueError as exc:
                raise Unswept(f"UNSWEPT_RECORD {path}:{number}: {exc}") from exc
        return
    try:
        yield json.loads(text)
    except ValueError as exc:
        raise Unswept(f"UNSWEPT_DOCUMENT {path}: {exc}") from exc


def sweep(run_dir):
    """`(residual, masked, by_key, bad_index, index_files)` over one run directory.

    Raises `Unswept` when a subject cannot be judged or when there is no subject at all: an empty set
    satisfies every "no secret survives" claim, and this is the artifact that claim rests on."""
    run_dir = pathlib.Path(run_dir)
    residual, masked, by_key, subjects = 0, 0, collections.Counter(), 0
    for directory in SWEPT:
        base = run_dir / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            subjects += 1
            for document in documents_in(path):
                for text in strings_of(document):
                    for name in residual_in(text):
                        residual += 1
                        by_key[name] += 1
                    masked += text.count(FLOOR.PLACEHOLDER)
    if not subjects:
        raise Unswept(f"UNSWEPT_EMPTY {run_dir}: no file under {', '.join(SWEPT)} to judge")
    bad_index, index_files = 0, 0
    for path in sorted((run_dir / "index").rglob("*.json")) if (run_dir / "index").is_dir() else []:
        index_files += 1
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            bad_index += 1
            continue
        postings = document.get("postings") if isinstance(document, dict) else None
        if not isinstance(postings, dict) or any(
                not isinstance(v, list) or any(not isinstance(n, int) for n in v) for v in postings.values()):
            bad_index += 1
    return residual, masked, by_key, bad_index, index_files


def report_sweep(run_dir):
    """Print the sweep's counts and key names - never a value - and return 1 if anything is residual, or if
    there was nothing to judge or something that could not be judged."""
    try:
        residual, masked, by_key, bad_index, index_files = sweep(run_dir)
    except Unswept as exc:
        print(f"projection --sweep {run_dir}: refused - {exc}")
        return 1
    print(f"projection --sweep {run_dir}: {residual} residual member(s) over the decoded strings")
    print(f"  placeholders already standing in those strings (must not be zero): {masked}")
    print(f"  index files whose postings hold anything but lists of document numbers: {bad_index} of {index_files}")
    if by_key:
        print("  residual by key name (names only, never a value):")
        for name, count in by_key.most_common():
            print(f"    {count:5}  {name}")
    return 1 if residual or bad_index else 0


def self_test():
    failures = []
    # a .jsonl record ends at "\n" only; JSON allows U+2028 and U+2029 raw inside a string
    with tempfile.TemporaryDirectory() as td:
        held = {"text": "before\u2028between\u2029after"}
        swept = pathlib.Path(td) / "r.jsonl"
        swept.write_text(json.dumps(held, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            got = list(documents_in(swept))
        except Unswept as exc:
            got = str(exc)
        if got != [held]:
            failures.append(f"jsonl-line-separators-inside-a-string-read-whole (documents_in): {got!r}")
    # the home every control states, rather than the account this process happens to run under: the owner's own
    # home is masked wherever it stands, so a fixture that named a real one would answer differently per machine
    owner = "/Users/fixture-owner"
    token = "sk-ant-oat01-" + "Ab1_" * 12
    secrets = [("a subscription token", f"use {token} now", "sk-ant-oat"),
               ("an api key assignment", "api_key=live_0123456789abcdef", "live_0123456789abcdef"),
               ("a bearer header", "Authorization: Bearer abcdef0123456789xyz", "abcdef0123456789xyz"),
               ("an email", "ask alice.dev@example.com", "alice.dev@example.com"),
               ("a github token", "ghp_" + "a" * 24, "ghp_a")]
    paths = [("a macOS home path", "see /Users/alice/Documents/repo/file.py:12", "/Users/alice"),
             # M#2: a Windows home is the same directory in any capitalisation, and M#1: an encoded one is
             # masked while decoded, so the decoded form must be the one that is kept
             ("a mixed-case Windows home path", r"open c:\users\FixtureOwner\notes", "FixtureOwner"),
             ("a mixed-case Windows home path of another person", r"open D:\USERS\Carol\x", "Carol"),
             ("an encoded home path under an ordinary key",
              '{"path":"\\u002fUsers\\u002ffixtureowner\\u002fnotes"}', "fixtureowner"),
             ("a Linux home path", "cd /home/bob/work && ls", "/home/bob"),
             ("a Windows home path", r"open C:\Users\carol\proj\a.txt", r"C:\Users\carol"),
             ("a path in quotes", "path='/Users/alice/x y'", "/Users/alice"),
             ("the end of a sentence", "it lives in /Users/alice.", "/Users/alice")]
    kept = [("a shared directory", "/Users/Shared/agent-bios-cells/run1"), ("a system path", "/usr/local/bin/python3"),
            ("prose", "the secret sauce is verifying the real dispatch path"), ("a relative path", "src/Users/alice.py"),
            ("a home-relative path", "~/Documents/notes.md"), ("a word that starts like a home", "/Usersfoo/bar")]
    for label, text, needle in secrets + paths:  # positive controls: each is masked, and the surrounding prose is not
        out = project(text, home=owner)
        if needle in out or not (FLOOR.PLACEHOLDER in out or HOME_MASK in out):
            failures.append(f"{label} was not masked: {out!r}")
        if project(out, home=owner) != out:
            failures.append(f"{label}: the projection is not idempotent: {out!r} -> {project(out, home=owner)!r}")
    for label, text in kept:
        if project(text, home=owner) != text:
            failures.append(f"{label} was changed: {text!r} -> {project(text, home=owner)!r}")
    if project("see /Users/alice/Documents/repo/file.py:12", home=owner) != f"see {HOME_MASK}/Documents/repo/file.py:12":
        failures.append("a home path did not keep the rest of the path after the mask")
    # The defect a review of 5ea5c3a found, in both halves. A structured value handed to the floor as text
    # kept its secrets, because a serialised object puts a closing quote between the key and the colon; and a
    # Windows home path lost its masking to the backslashes `json.dumps` doubles. Every shape below is a
    # fabricated value, and the structure is what the floor is given now - never its serialisation.
    structured = [
        ("a password key", {"password": "hunter2xyz0123"}, "hunter2xyz0123"),
        ("an api_key key", {"api_key": "abc123def4567890"}, "abc123def4567890"),
        ("a token key", {"token": "t0kenvalue1234567"}, "t0kenvalue1234567"),
        ("an Authorization header value", {"Authorization": "Bearer wire9876543210value"}, "wire9876543210value"),
        ("a secret nested two deep", {"outer": {"inner": {"secret": "nested12345678"}}}, "nested12345678"),
        ("a secret inside a list", {"calls": [{"n": 1}, {"token": "listed123456789"}]}, "listed123456789"),
        ("a non-string secret value", {"token": 12345678901234}, "12345678901234"),
        # only the walk can mask these: once serialised, a `"key":` followed by `{` or `[` is a shape no text
        # pattern reads as a value, so the structure is where the key has to be recognised
        ("a secret whose value is an object", {"token": {"value": "objected123456", "kind": "oauth"}}, "objected123456"),
        ("a secret whose value is a list", {"api_key": ["k1abcdef123456", "k2abcdef123456"]}, "k1abcdef123456"),
        ("a secret key under a projected key", {f"{owner}/cfg": {"password": "keyed12345678"}}, "keyed12345678"),
        ("a Windows home path a tool argument carries", {"cmd": r"type C:\Users\carol\notes.txt"}, r"C:\Users\carol"),
        ("a string that quotes serialised JSON", '{"password": "quoted12345678"}', "quoted12345678"),
        # the names the floor calls secrets end a key rather than begin it; reading them as prefixes left
        # 11,045 of these unmasked in the live run of 2026-10-21, every one a key the floor itself names
        ("a prefixed key in text", '{"openai_api_key": "sk-planted0123456789"}', "planted0123456789"),
        ("a prefixed header key in text", '{"user_authorization": "Bearer plantedwire12345"}', "plantedwire12345"),
        ("a hyphenated key in text", '{"x-api-key": "plantedkeyvalue123"}', "plantedkeyvalue123"),
        ("a prefixed token key in text", '{"page_token": "plantedpagetoken123"}', "plantedpagetoken123"),
        ("a prefixed key in a structure", {"google_client_secret": "plantedclientsecret"}, "plantedclientsecret"),
        # a string that is itself a serialised structure, at one and at two removes: the shape no key pattern
        # of ours reads, because its quotes arrive escaped. 3,117 members of the live run of 2026-10-21 were
        # of this shape after the pattern had been fixed twice, which is why it is closed by parsing instead
        ("a secret one serialisation deep", {"body": '{"password": "deep1planted12"}'}, "deep1planted12"),
        ("a secret two serialisations deep",
         {"body": json.dumps({"inner": json.dumps({"api_key": "deep2planted12"})})}, "deep2planted12"),
        ("a serialised structure as the whole block", '{"body": "{\\"token\\": \\"deep3planted12\\"}"}',
         "deep3planted12"),
        # a secret-named key whose value OPENS a structure, in a fragment of a document rather than a whole
        # one: both key patterns read a scalar, so these kept everything inside them (277 live members)
        ("an object-valued key in a document fragment",
         '      },\n      "authorization": {\n        "scheme": "bearer",\n        "value": "frag1planted"\n      },\n      "next": 1',
         "frag1planted"),
        ("an array-valued key in a fragment", 'prefix "hadSecret": ["frag2planted"], "other": 2', "frag2planted"),
        ("a structured value mid-sentence", 'a fragment "page_token": {"a": "frag3planted"} and more', "frag3planted"),
        # the same member with its quotes escaped, in a fragment no parse can take whole
        ("an escaped scalar member in a fragment", 'tail\\", \\"client_secret\\": \\"frag4planted\\", \\"next\\": 1',
         "frag4planted"),
        # the last shape any sweep of the live run found: an escaped member whose value opens a structure,
        # which only the pass through one level of unescaping reaches
        ("an escaped structured value",
         'tail\\", \\"root_password\\": {\\n  \\"value\\": \\"frag5planted\\"\\n}, \\"next\\": 1', "frag5planted"),
        ("an escaped object under a prefixed key", '}, \\"nextPageToken\\": {\\"a\\": \\"frag6planted\\"}',
         "frag6planted"),
        # a structure a view clipped: its extent is absent rather than unknown, so the rest of the text goes
        ("a clipped structured value", 'a clipped fragment "password": {"value": "frag7planted', "frag7planted"),
        # the thirteen scalars of the live run of 2026-10-21, by the shape that hid each of them: the key's
        # own quote missing because the fragment began mid-string, a value the old length cap or character
        # class could not span, a key longer than the old prefix cap, and a notation that is not JSON
        ("a keyed scalar with no opening quote", 'password": "sc1planted", "next": 1', "sc1planted"),
        ("a value holding a quote", 'a line "password": "pre\\"sc2planted" and more', "sc2planted"),
        ("a value holding a backslash", 'a line "password": "C:\\\\xsc3planted" and more', "sc3planted"),
        ("a value longer than four thousand characters",
         'a line "password": "' + "p" * 4200 + 'sc4planted" and more', "sc4planted"),
        ("a value holding an escape sequence", 'a line "password": "\\u0041sc5planted" and more', "sc5planted"),
        ("a repr's single-quoted value", 'a line "password": \'sc6planted\' and more', "sc6planted"),
        ("a value behind a comment", 'a line "password": /*x*/ "sc7planted"', "sc7planted"),
        ("a key longer than the old prefix cap", 'a "' + "z" * 70 + 'password": "sc8planted"', "sc8planted"),
        # M#0: the floor's own substitution is destructive, so a pass that needs the key must run before it
        ("a quoted bearer header the floor truncates", 'Authorization: "Bearer m0aplanted"', "m0aplanted"),
        # P#0: the floor's scheme pattern crosses whitespace of any kind, including a newline. A scan for a
        # bare value stops at the first space, so composing the two by substitution lost the credential
        # whichever order they ran in; the union of their spans loses neither.
        ("a multiline bearer header", "Authorization: Bearer\np0aplanted0123456789", "p0aplanted0123456789"),
        ("a header split by a tab run", "Authorization:\tBearer \t p0bplanted0123456789", "p0bplanted0123456789"),
        # P#1: a decoded structure whose only secret stands in a KEY
        ("an encoded home path as a dictionary key", '{"\\u002fUsers\\u002ffixture-owner\\u002fnotes":1}',
         "fixture-owner"),
        ("a repr's single-quoted key and value", "{'password': 'm0bplanted'}", "m0bplanted"),
        # M#1: the floor and the path masking change text no keyed pass touches, and a walk that recorded
        # only keyed maskings threw their work away with the decoded form
        ("an encoded token under an ordinary key",
         '{"note":"sk\\u002dant\\u002doat01\\u002dAb1_Ab1_Ab1_Ab1_Ab1_Ab1_"}', "Ab1_Ab1_"),
        ("a Windows home path already escaped in text", r"see C:\\Users\\carol\\x", r"Users\\carol"),
    ]
    for label, value, needle in structured:
        out = project(value, home=owner)
        if needle in out or FLOOR.PLACEHOLDER not in out and HOME_MASK not in out:
            failures.append(f"{label} survived the projection: {out!r}")
        if project(out, home=owner) != out:
            failures.append(f"{label}: the projection is not idempotent: {out!r} -> {project(out, home=owner)!r}")
    # the walk is not a blanket: a key the floor does not treat as a secret keeps its value, and so does prose
    structured_kept = [("an ordinary key", {"command": "ls -la"}, '{"command":"ls -la"}'),
                       # the floor needs its separator straight after the name, so a key the name only STARTS
                       # is not a secret: a usage counter must survive, or every transcript loses its numbers
                       ("a usage counter in text", '{"input_tokens": 1234}', '{"input_tokens": 1234}'),
                       ("a nested usage counter in text", '{"total_token_usage": {"input": 7}}',
                        '{"total_token_usage": {"input": 7}}'),
                       ("a plural of a secret name", {"tokens": 42}, '{"tokens":42}'),
                       # a JSON document with no secret in it keeps its own formatting: the walked form
                       # replaces the text only when something was actually masked
                       ("a pretty-printed document with no secret", '{\n  "pretty": 1,\n  "input_tokens": 2\n}',
                        '{\n  "pretty": 1,\n  "input_tokens": 2\n}'),
                       ("a serialised structure with nothing to mask", '{"keep": "no secret here at all"}',
                        '{"keep": "no secret here at all"}'),
                       # a structure under a key the floor does not name, and a value that does not decode,
                       # are both left alone: the extent is found by decoding, never guessed at
                       # the key is not one the floor claims, and neither is any other word on the line:
                       # the word `secret` in the old wording of this fixture IS such a word, and under the
                       # keyed rule's line unit it named the structure that followed it
                       ("a structured value under an ordinary key", 'not a canary "input_tokens": {"a": 1}',
                        'not a canary "input_tokens": {"a": 1}'),
                       # a value that does not decode but DOES close is another notation, not a clipped
                       # structure: a repr's own extent is its own, and the prose after it is not the secret's
                       ("a repr that closes, with prose after it",
                        'a line "token": {\'a\': 1} and prose after it',
                        'a line "token": {\'a\': 1} and prose after it'),
                       # escaped text is re-spelled only when a secret was masked in it: prose and a member
                       # under an ordinary key keep their own escaping, byte for byte
                       ("escaped text with nothing to mask", 'a\\", \\"input_tokens\\": {\\"a\\": 1}',
                        'a\\", \\"input_tokens\\": {\\"a\\": 1}'),
                       ("escaped prose", 'he said \\"hello\\" and left', 'he said \\"hello\\" and left'),
                       ("a quoted key with no value after it", 'the "token" column is an integer',
                        'the "token" column is an integer'),
                       ("a lesson about tokens", "trust the X-Hook-Token header; the server derives identity from it",
                        "trust the X-Hook-Token header; the server derives identity from it")]
    for label, value, want in structured_kept:
        if project(value, home=owner) != want:
            failures.append(f"{label} was changed: {project(value, home=owner)!r}, expected {want!r}")
    # the key names are the floor's own, and the probe that asks it is not matched by the floor on its own
    if FLOOR.redact(_PROBE) != _PROBE:
        failures.append("instrument control: the floor redacts the probe value itself, so secret_key answers yes to every key")
    if not all(secret_key(k) for k in ("password", "api_key", "API-KEY", "secret", "token", "authorization", "bearer")):
        failures.append("a key name the floor's own pattern lists was not read as the name of a secret")
    if not all(secret_key(k) for k in ("openai_api_key", "user_authorization", "x-api-key", "page_token")):
        failures.append("a key the name only ends was not read as the name of a secret, though the floor redacts it")
    if any(secret_key(k) for k in ("command", "path", "file", "prompt", "input_tokens", "total_token_usage", "", None)):
        failures.append("a key name the floor does not list was read as the name of a secret")
    # a key whose own name the floor already masked holds the placeholder before the floor is asked: the
    # question is whether the floor CHANGES `name=<value>`, not whether the answer carries the placeholder
    if any(secret_key(k) for k in (FLOOR.PLACEHOLDER, f"serviceAccount:{FLOOR.PLACEHOLDER}", f"user:{FLOOR.PLACEHOLDER}")):
        failures.append("a key whose name already carries the placeholder was read as the name of a secret")
    # the floor's shape is read, never assumed: a floor whose key-name group moved is a named failure
    kept_first = FLOOR.SECRET_RE[0]
    FLOOR.SECRET_RE[0] = re.compile(r"nothing-like-the-floor")
    try:
        floor_key_alternation()
        failures.append("a floor whose first pattern does not lead with its key-name group was read anyway")
    except FloorUnreadable as exc:
        if "REDACTION_FLOOR_UNREADABLE" not in str(exc):
            failures.append(f"an unreadable floor was refused unnamed: {exc}")
    finally:
        FLOOR.SECRET_RE[0] = kept_first
    # a transcript carries tool arguments as JSON, so a line break reaches the text as `\` and `n`: it is a
    # boundary, not a path segment (the live run of 2026-10-21, 8,536 owner paths left in the projection)
    for label, text in (("an escaped newline", r"cat out\n/Users/alice/x"), ("an escaped tab", r"a\t/Users/alice/x"),
                        ("an escaped return", r"a\r/Users/alice/x")):
        if HOME_MASK not in project(text, home=owner):
            failures.append(f"{label} before a home path was read as a path segment: {project(text, home=owner)!r}")
    # the owner's own home is masked wherever it stands - prose, a relative prefix or an escape may abut it
    for label, text in (("prose with no separator", "표시된/Users/fixture-owner/notes.md"),
                        ("a relative prefix", "../../../Users/fixture-owner/notes.md"),
                        ("a diff prefix", "a/Users/fixture-owner/notes.md")):
        if owner in project(text, home=owner):
            failures.append(f"the owner's home survived {label}: {project(text, home=owner)!r}")
    if project("src/Users/alice.py", home=owner) != "src/Users/alice.py":
        failures.append("another person's relative path was masked because the owner's rule is unconditional")
    if project(token) == token or "oat" in project(token):
        failures.append("the subscription token prefix survived the projection")
    # this process's own home, when it is not under /Users or /home
    if mask_one("log at /srv/people/zed/work/a.log", home="/srv/people/zed") != f"log at {HOME_MASK}/work/a.log":
        failures.append("a home outside /Users and /home was not masked")
    if mask_one("/srv/people/zedder/a", home="/srv/people/zed") != "/srv/people/zedder/a":
        failures.append("a longer directory name that merely begins with the home was masked")
    # block text: a string is itself, any other value its compact JSON
    if project("x", home=owner) != "x" or project({"a": [1, "é"]}, home=owner) != '{"a":[1,"é"]}':
        failures.append("a block did not project to the string itself or to its compact JSON")
    if project(json.loads('"a\\ud83dz"'), home=owner) != "a?z":
        failures.append("a lone surrogate was not replaced, so the block could not be written as UTF-8")
    # a registered second version is a different projection, and an unknown one is named
    VERSIONS["rt"] = lambda value, home=None: project_r22(value, home).upper()
    try:
        if project("path /Users/alice/x", "rt", owner) == project("path /Users/alice/x", home=owner):
            failures.append("a second registered version did not project differently")
    finally:
        del VERSIONS["rt"]
    for gone in ("r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15", "r16", "r17", "r18", "r19", "r20", "r21"):   # each superseded projection masks less: removed, not left callable
        try:
            project("x", gone)
            failures.append(f"version {gone} was projected although it is not registered")
        except KeyError as exc:
            if "REDACTION_VERSION_MISMATCH" not in str(exc):
                failures.append(f"version {gone} was refused unnamed: {exc}")
    try:
        project("x", "r99")
        failures.append("an unregistered version was projected")
    except KeyError as exc:
        if "REDACTION_VERSION_MISMATCH" not in str(exc):
            failures.append(f"an unregistered version was refused unnamed: {exc}")
    # ---- R#0: a floor match that crosses the structure's syntax, and the credential behind it -----
    #
    # The shape the finding names: the floor's greedy run eats the closing quote and the comma, so masking it
    # first leaves text that no longer parses and the member after it is never decoded. Decoding first reaches
    # both; the oracle then checks the raw claim, so neither can be traded for the other.
    mixed = [("a floor match across the syntax, with an encoded key after it",
              '{"note":"api_key=abc", "\\u0070assword":"r0planted-value"}', ["r0planted-value", "api_key=abc"]),
             ("... and with an encoded home path as the key after it",
              '{"note":"api_key=abc", "\\u002fUsers\\u002ffixture-owner\\u002fn":1}',
              ["fixture-owner", "api_key=abc"]),
             ("a multiline header inside a structure",
              '{"header":"Authorization: Bearer\\nr0opaque0123456789"}', ["r0opaque0123456789"]),
             ("an escaped structure holding both",
              '\\"api_key\\": \\"r0escaped-value\\", \\"path\\": \\"/Users/fixture-owner/x\\"',
              ["r0escaped-value", "fixture-owner"])]
    for label, text, planted in mixed:
        out = project_text(text, owner)
        standing = [needle for needle in planted if needle in out]
        if standing:
            failures.append(f"{label}: {standing} survived the projection: {out!r}")
        if floor_leftovers(text, owner):
            failures.append(f"{label}: the floor claims a credential the projection left: {out!r}")
        if project_text(out, owner) != out:
            failures.append(f"{label}: the projection is not idempotent: {out!r} -> {project_text(out, owner)!r}")

    # ---- the shapes that used to need two paths, now in one ---------------------------------------
    #
    # There is no candidate and no fallback any more: one pass, one set of extents, in the original text's
    # own coordinates. These are the cases each of the four previous rounds was about, kept because each one
    # is a shape a reader can check, and because a rule nobody can see fail is not a rule.
    single_pass = [
        ("a floor claim spread across two members", '{"a":"sk-' + "A1b2" * 6
         + ' api_key=","b":"r0leftover-credential"}', ["r0leftover"]),
        ("an encoded scalar credential behind that claim", '{"a":"sk-' + "A1b2" * 6
         + ' api_key=","b":"v0left", "\\u0070assword":"v0encoded-secret-123"}',
         ["v0encoded-secret-123"]),
        ("an encoded home path behind that claim", '{"a":"sk-' + "A1b2" * 6
         + ' api_key=","b":"v0left", "\\u002fUsers\\u002ffixtureowner\\u002fx":1}', ["fixtureowner"]),
        # A#0: the keyed value is a quoted scalar that happens to contain a structure. Masking what was
        # found INSIDE it left the rest of the scalar standing, and a second projection then removed the
        # rest - two runs, two answers.
        ("a quoted keyed value holding a structure", 'prefix "password": "x{}a0abcd-credential"',
         ["a0abcd-credential"]),
        # A#1: a plain structure followed by an escaped member. The escaped region is read in its own
        # coordinates, so neither part excuses the other.
        ("a cross-member claim followed by an escaped member", '{"a":"sk-' + "A1b2" * 6
         + ' api_key=","b":"a1left"} \\"\\u0070assword\\": \\"a1gap-secret-123\\"',
         ["a1gap-secret-123"]),
        ("... and with an encoded home path in that escaped member", '{"a":"sk-' + "A1b2" * 6
         + ' api_key=","b":"a1left"} \\"path\\": \\"\\u002fUsers\\u002ffixtureowner\\u002fx\\"',
         ["fixtureowner"]),
        # E#0: the key's name stands in an unrelated value, which is not coverage of the encoded member
        ("an encoded key whose name appears in a sibling value",
         '{"note":"password","\\u0070assword":"e0opaqueCredential123"}', ["e0opaqueCredential123"]),
        ("... and with an ordinary value under an ordinary key beside it",
         '{"note":"password","keep":"ordinary","\\u0070assword":"e0sibling-credential"}',
         ["e0sibling-credential"]),
        ("... and with the key spelled plainly twice over",
         '{"password":"e0first-credential","\\u0070assword":"e0second-credential"}',
         ["e0first-credential", "e0second-credential"]),
        # E#1: two findings in one decoded region, at different depths
        ("a token needing one more decoding beside an already plain path",
         '\\"note\\":\\"sk\\\\u002de1abcdefghijklmnopq\\", '
         '\\"path\\":\\"\\u002fUsers\\u002ffixtureowner/x\\"',
         ["e1abcdefghijklmnopq", "fixtureowner"]),
        # E#2: a decodable body with no escaped quote in it at all
        ("an encoded credential in a body with no escaped quotes", 'sk\\u002de2abcdefghijklmnopq',
         ["e2abcdefghijklmnopq"]),
        ("an encoded home path in such a body", '\\u002fUsers\\u002ffixtureowner\\u002fnotes',
         ["fixtureowner"]),
        ("an encoded credential in the tail after a plain structure",
         '{"note":"plain"} sk\\u002de2tail-abcdefghij', ["e2tail-abcdefghij"]),
        ("an escaped structure inside a tool argument",
         '{\\"command\\": \\"curl -H \\\\\\"authorization: Bearer a2abcdef0123456789\\\\\\"\\"}',
         ["a2abcdef0123456789"]),
    ]
    # E#3: the delimiters survive, the document still parses, and a second projection is the first
    syntax_cases = [
        ("a floor match inside a secret-named value", '{"password":"abc token=e3def-credential"}'),
        ("a floor match across two members",
         '{"a":"sk-' + "A1b2" * 6 + ' api_key=","b":"e3cross-credential"}'),
        ("a floor match in a nested structure",
         '{"outer":{"a":"sk-' + "A1b2" * 6 + ' api_key=","b":"e3nested"},"keep":"plain"}'),
        ("a floor match at the very end of a value", '{"token":"e3end token=e3tail-credential"}'),
        # R#5: the serialised scalar shapes, and a block the backstop really takes
        ("a numeric value under a secret-named key", '{"password":1234567890}'),
        ("a boolean value under a secret-named key", '{"password":true}'),
        ("a null value under a secret-named key", '{"password":null,"keep":"plain words"}'),
        ("duplicate secret-named members", '{"password":"r5first-value","password":"r5second-value"}'),
        # a VALID JSON document the backstop takes: the credential is six escape layers down, which the
        # mapping does not locate and the verifier's lenient reading does
    ]
    # S#4: the one fixture that must ACTIVATE the backstop, kept apart from the syntax cases because what is
    # asserted of it is different: the named detector, a counter that moved by one, and an output equal to
    # the JSON string `"<REDACTED>"` written out here rather than asked of `blank_for`.
    must_blank = json.dumps({"note": "sk" + "\\\\u005c" * 6 + "u002ds4blankedabcdefghijklmn"},
                            ensure_ascii=False)
    floor_before = BLANKED["floor"]
    blanked_out = project_text(must_blank, owner)
    if BLANKED["floor"] - floor_before != 1:
        failures.append("the fixture that must activate the backstop did not blank by the floor detector "
                        f"exactly once: {blanked_out[:60]!r}")
    if blanked_out != '"<REDACTED>"':
        failures.append(f"a blanked JSON block is not the JSON string \"<REDACTED>\": {blanked_out!r}")
    if json.loads(blanked_out) != FLOOR.PLACEHOLDER:
        failures.append(f"the blanked block does not read back as the mask: {blanked_out!r}")
    if project_text(blanked_out, owner) != blanked_out:
        failures.append(f"a blanked block is not a fixed point: {blanked_out!r}")
    # R#5: every one of these is parsed by `json.loads` here, and the blanked form is written out as the
    # literal `"<REDACTED>"` rather than asked of `blank_for` - a control that calls the producer's own
    # helper agrees with it by construction, including when both are wrong.
    for label, text in syntax_cases:
        out = project_text(text, owner)
        try:
            json.loads(out)
        except ValueError as exc:
            failures.append(f"{label}: the projection no longer parses as JSON: {out!r} ({exc})")
        again = project_text(out, owner)
        if again != out:
            failures.append(f"{label}: the second projection differs from the first: {out!r} -> {again!r}")
        if discloses(out, owner):
            failures.append(f"{label}: the verifier still finds {discloses(out, owner)} in {out!r}")
        if out.strip().startswith('"') and out != f'"{FLOOR.PLACEHOLDER}"' and json.loads(out) != text:
            failures.append(f"{label}: a blanked JSON block is not the JSON mask: {out!r}")

    # Each mapping fix gets a control of its own, because the verifier would otherwise hide all of them:
    # with the backstop in place a mapping mistake blanks the block, the credential is gone either way, and
    # every absence control stays green. What tells the two apart is PRECISION - these shapes must be masked
    # in place, with the block surviving - so reverting a mapping fix fails here by name instead of silently
    # falling through to the blanket.
    precise = [
        ("E#0: an encoded key whose name stands in a sibling value",
         '{"note":"password","\\u0070assword":"e0precise-credential"}'),
        ("E#1: a twice-encoded token beside an already plain path in one region",
         '\\"note\\":\\"sk\\\\u002de1precise-abcdefghij\\", '
         '\\"path\\":\\"\\u002fUsers\\u002ffixtureowner/x\\"'),
        # surrounded by ordinary words, so masking in place is distinguishable from blanking the block
        ("E#2: a decodable body carrying no escaped quote",
         'see sk\\u002de2precise-abcdefghij here'),
        ("E#2: an encoded home path in such a body",
         'see \\u002fUsers\\u002ffixtureowner\\u002fnotes here'),
        ("E#3: a floor match inside a secret-named value",
         '{"password":"abc token=e3precise-credential"}'),
    ]
    for label, text in precise:
        blanked_before = sum(count for key, count in STATS.items() if key.startswith("blanked:"))
        out = project_text(text, owner)
        blanked = sum(count for key, count in STATS.items() if key.startswith("blanked:")) - blanked_before
        if blanked:
            failures.append(f"{label}: the mapping missed it and the verifier blanked the whole block, so "
                            f"the masking this case is about is not happening: {out!r}")
        if out == FLOOR.PLACEHOLDER:
            failures.append(f"{label}: the whole block was replaced, so nothing proves the extent was found")
    # ---- M#6 and M#0: the backstop fires, by exactly the detector and exactly once ---------------
    #
    # The previous control required three things at once and so passed whenever none of them held - it was
    # green with the verifier removed. These require the counter to MOVE, by the named detector, by one.
    # The clean counterpart comes first: an input the mapping covers must NOT blank, or the figures below
    # would be satisfied by a projection that blanks everything.
    def blanked_by(text, home=owner):
        """`(reason, out)` - which detector blanked this block, and what it became."""
        before = collections.Counter({key: value for key, value in BLANKED.items()})
        out = project_text(text, home)
        moved = [key for key in BLANKED if BLANKED[key] - before[key] == 1]
        extra = [key for key in BLANKED if BLANKED[key] - before[key] > 1]
        if extra:
            failures.append(f"one block raised {extra} by more than one, so the counts are not per block")
        return (moved[0] if moved else None), out

    def nested_layers(count, secret="sk-m0deepAbCdEfGhIjKlMn"):
        """A credential wrapped in `count` JSON documents, each inside the previous one's string."""
        value = secret
        for _level in range(count):
            value = json.dumps({"carrier": value}, ensure_ascii=False)
        return value

    reason, out = blanked_by('{"note":"ordinary text","password":"m6clean-value"}')
    if reason is not None:
        failures.append(f"a block the mapping covers was blanked by {reason!r}: {out!r}")

    # The depth limit is asked of the verifier directly, not through a projected block. Nothing the
    # projection emits can reach it: `holds_secret` fails closed past MAX_EMBEDDED, so a deeply wrapped
    # credential is already masked by the mapping and the output the verifier sees is clean. The limit is
    # still the rule that decides what an unfinished traversal means, so it is held where it lives - and the
    # shallower counterpart must NOT read as a limit, or the detector would be answering by depth alone.
    # At the limit with something still to decode, the traversal reports a limit rather than a clean list.
    # Asked of the traversal at its own boundary, because no constructed block reaches it from outside: the
    # lenient reading collapses any number of escape layers in one step, and JSON nesting escapes its own
    # quotes, so that reading shortcuts the nesting too. Both halves are asserted - at the boundary it
    # reports the limit, and one step below it reports the detector - or a rule that always says "limit"
    # would pass.
    at_limit = every_spelling(nested_layers(3), VERIFY_DEPTH)[1]
    if not at_limit.exhausted:
        failures.append("the traversal stopped at its depth limit with layers left to decode and did not "
                        "report it, so an output it never finished reading would read as clean")
    inside_limit = every_spelling(nested_layers(3), VERIFY_DEPTH - 3)[1]
    if inside_limit.exhausted:
        failures.append("the traversal reported a limit although it had the depth to finish")
    thrifty = Reach()
    thrifty.budget = 2
    if not every_spelling(nested_layers(4), 0, thrifty)[1].exhausted:
        failures.append("the traversal spent its budget and did not report it")
    if discloses(nested_layers(2), owner) != "floor":
        failures.append("a credential two layers down was reported as "
                        f"{discloses(nested_layers(2), owner)!r} rather than by the detector that finds it")
    if discloses(FLOOR.PLACEHOLDER, owner) is not None:
        failures.append("the verifier reports a finding in the mask itself, so every block would blank")

    # ---- R#0 and R#1: the verifier's own rules, on the shapes the mapping cannot see ------------
    #
    # Clean counterpart first in each pair: a block the mapping covers must NOT blank, or a verifier that
    # blanks everything would satisfy the rest.
    member_cases = [
        ("a duplicate secret-named member behind a masked one",
         '{"password":"' + FLOOR.PLACEHOLDER + '","password":"r0dup-credential-456"}', True),
        ("a secret-named key with a newline before its colon",
         '{"safe":{"password":"' + FLOOR.PLACEHOLDER + '"},"password"\n:"r0newline-credential"}', True),
        ("a secret-named key with spaces around its colon",
         '{ "password"  :  "r0spaced-credential" }', True),
        ("a secret-named member nested under an ordinary one",
         '{"outer":{"inner":{"password":"r0nested-credential"}}}', True),
        ("a secret-named member whose value is a structure of leaves",
         '{"password":{"a":"r0leaf-one","b":["r0leaf-two"]}}', True),
        # ... and the absent value, which discloses nothing: the mapping may still mask it, but the block
        # must stay readable rather than being blanked whole
        ("a secret-named key with no value at all", '{"password":null,"other":"plain words"}', None),
        ("a secret-named key with an empty value", '{"password":"","other":"plain words"}', None),
    ]
    for label, text, must_mask in member_cases:
        out = project_text(text, owner)
        if must_mask and out == text:
            failures.append(f"{label}: the projection left the block untouched: {out!r}")
        if must_mask is None:
            if "plain words" not in out:
                failures.append(f"{label}: a block with nothing to disclose was blanked whole: {out!r}")
            if not parses_as_json(out):
                failures.append(f"{label}: a JSON block stopped parsing: {out!r}")
        if discloses(out, owner):
            failures.append(f"{label}: the verifier still finds {discloses(out, owner)!r} in {out!r}")
        if project_text(out, owner) != out:
            failures.append(f"{label}: not idempotent: {out!r} -> {project_text(out, owner)!r}")
    # the verifier reads the SHAPES directly too, so the rule is held where it lives
    for label, text, expected in (
            ("a duplicate secret-named member whose MASKED copy comes last - the one a reader that keeps "
             "only the last value cannot see",
             '{"password":"r0direct-credential","password":"' + FLOOR.PLACEHOLDER + '"}', "secret-named key"),
            ("a duplicate secret-named member whose masked copy comes first",
             '{"password":"' + FLOOR.PLACEHOLDER + '","password":"r0direct-second"}', "secret-named key"),
            ("a secret-named member nested two objects down",
             '{"outer":{"inner":{"password":"r0direct-nested"}}}', "secret-named key"),
            ("a secret-named member whose value is a structure with an unmasked leaf",
             '{"password":{"a":"' + FLOOR.PLACEHOLDER + '","b":["r0direct-leaf"]}}', "secret-named key"),
            ("a secret-named member whose value is a structure of masks only",
             '{"password":{"a":"' + FLOOR.PLACEHOLDER + '","b":["' + FLOOR.PLACEHOLDER + '"]}}', None),
            ("a newline before the colon",
             '{"password"\n:"r0direct-newline"}', "secret-named key"),
            ("a masked member and nothing else",
             '{"password":"' + FLOOR.PLACEHOLDER + '"}', None),
            ("an escape layer that starts and cannot be read", "ordinary text ending in a backslash\\",
             "verifier-limit"),
            ("a Windows path, whose characters the lenient reading does reach", "see C:\\temp\\notes.txt",
             None),
            # S#0: a readable keyed fragment in mixed text - no JSON object to read it as a member, no floor
            # match, no home path. The old verifier saw the decoded key as a bare word and nothing else.
            ("a keyed fragment in mixed text",
             '{"note":"plain"} "\\u0070assword":"s0canarycredential"', "keyed fragment"),
            ("the same fragment already masked",
             '{"note":"plain"} "password":"' + FLOOR.PLACEHOLDER + '"', None),
            ("a keyed fragment with the separator a few characters away",
             'the setting token \\" = \\" s0spacedcredential', "keyed fragment"),
            ("a keyed fragment whose name the floor does not claim", 'colour = s0ordinaryvalue', None),
            # V#0: a readable structured value in a fragment keeps its key association, and every leaf of
            # it is held against the mask. Exempting it on the opening bracket alone let a complete array
            # carry an ordinary string.
            ("a readable array under an encoded key",
             '{"note":"plain"} "\\u0070assword":["v0structure_canary"]', "keyed fragment"),
            ("a readable object under an encoded key",
             '{"note":"plain"} "\\u0070assword":{"inner":"v0object_canary"}', "keyed fragment"),
            ("... while an array of masks only is exempt",
             '{"note":"plain"} "\\u0070assword":["<REDACTED>","<REDACTED>"]', None),
            ("... and a structure whose extent cannot be read is the owner-pending class, untouched",
             '{"note":"plain"} "\\u0070assword":{truncated', None),
            # V#1: what follows a scalar is not the scalar's, and nothing is stripped from inside one
            ("a suffix after a masked scalar",
             '{"note":"plain"} "\\u0070assword":"<REDACTED>"v1suffix_canary', "keyed fragment"),
            ("a quoted scalar holding only punctuation",
             '{"note":"plain"} "\\u0070assword":";"', "keyed fragment"),
            ("... while a masked scalar followed by packaging is exempt",
             '{"note":"plain"} "\\u0070assword":"<REDACTED>" ,', None),
            # V#2: a quoted key whose separator stands on the next line
            ("a quoted key with a newline before its separator",
             '{"note":"plain"} "password"\n: "v2line_canary"', "keyed fragment"),
            ("an encoded key with a newline before its separator",
             '{"note":"plain"} "\\u0070assword"\n= "v2encoded_canary"', "keyed fragment"),
            ("... while the same association already masked is exempt",
             '{"note":"plain"} "password"\n: "<REDACTED>"', None),
            # T#0: a long name token, which a cap split into two words the floor claims neither of
            ("a secret-named key behind 38 characters of name",
             '{"note":"plain"} "' + "x" * 38 + '\\u0070assword":"t0canarycredential"', "keyed fragment"),
            # T#1: a value that merely STARTS with the mask still holds what follows it
            ("a keyed value that starts with the mask and goes on",
             '{"note":"plain"} "\\u0070assword":"' + FLOOR.PLACEHOLDER + ' t1survivingcanary"',
             "keyed fragment"),
            ("... while the value that IS the mask is exempt",
             '{"note":"plain"} "password":"' + FLOOR.PLACEHOLDER + '"', None),
            ("a keyed value that ends with the mask",
             '{"note":"plain"} "\\u0070assword":"t1leading ' + FLOOR.PLACEHOLDER + '"', "keyed fragment"),
            # T#2: a backslash before a real newline - a run the lenient reading cannot cross
            ("a backslash before an actual newline, beside a structure that decodes",
             '{"note":"plain"} \\\nordinary', "verifier-limit"),
            ("a backslash before a carriage return", '{"note":"plain"} \\\rordinary', "verifier-limit"),
            ("an escaped newline, which IS a valid escape", '{"note":"plain"} \\n ordinary', None),
            # S#1: the unfinished run is reported although the block also holds a structure that decodes
            ("an unfinished escape run beside a structure that decodes", '{"note":"plain"} \\',
             "verifier-limit"),
            ("a truncated \\u sequence beside a structure that decodes", '{"note":"plain"} \\u00',
             "verifier-limit")):
        if discloses(text, owner) != expected:
            failures.append(f"the verifier reads {label} as {discloses(text, owner)!r}, not {expected!r}")

    backstop_cases = [
        # ... and seven layers, which is inside the limit but outside the projection's own mapping
        ("seven decode layers in a mixed-prose tail",
         '{"note":"plain"} sk' + "\\\\u005c" * 6 + "u002dm0sevenabcdefghij", ("floor", "verifier-limit")),
        # more distinct strings than the traversal's budget allows: the same reasoning as the depth limit
        ("beyond the verifier's budget",
         json.dumps({f"k{index}": f"v{index}" for index in range(VERIFY_BUDGET + 50)}, ensure_ascii=False),
         ("verifier-limit",)),
    ]
    for label, text, allowed in backstop_cases:
        reason, out = blanked_by(text)
        if reason is None:
            failures.append(f"{label}: no block was blanked, so the backstop did not fire on the one input "
                            f"this case is about: {out[:60]!r}")
        elif reason not in allowed:
            failures.append(f"{label}: the backstop blanked for {reason!r}, not one of {allowed}")
        if reason is not None and out != blank_for(text):
            failures.append(f"{label}: a blanked block is not the mask: {out[:60]!r}")
        if project_text(out, owner) != out:
            failures.append(f"{label}: a blanked block is not idempotent: {out[:60]!r}")

    for label, text, planted in single_pass:
        out = project_text(text, "/Users/fixtureowner")
        standing = [needle for needle in planted if needle in out]
        if standing:
            failures.append(f"{label}: {standing} survived the projection: {out!r}")
        if readable_survivors(text, out):
            failures.append(f"{label}: an obligation of the original still reads in the projection: {out!r}")
        if project_text(out, "/Users/fixtureowner") != out:
            failures.append(f"{label}: the projection is not idempotent: {out!r} -> "
                            f"{project_text(out, '/Users/fixtureowner')!r}")
    # ... and a block whose secrets are all reachable keeps its own text everywhere else: masking extents
    # means a document a person reads is not re-serialised for the sake of one member
    in_place = project_text('{"note": "ordinary text",  "password": "r0kept-value"}', owner)
    if in_place != '{"note": "ordinary text",  "password": "<REDACTED>"}':
        failures.append(f"a block was re-serialised rather than masked in place: {in_place!r}")

    # ---- R#4: the oracle itself, before it is used to judge anything -----------------------------
    #
    # A differential is only as good as its question. The previous one asked whether an entire floor MATCH
    # still stood in the output, which the original defect passes: drop `Authorization: Bearer` and keep the
    # credential, and the whole match is gone. So the oracle is proven first - on a deliberately partial
    # mask - and then used.
    partial_cases = [
        ("a credential with its middle removed", "Authorization: Bearer abcdefgh01234567ijklmnop",
         "Authorization: Bearer abcdefgh<REDACTED>ijklmnop"),
        ("the P#0 shape: the header masked and the credential left",
         "Authorization: Bearer\nopaque0123456789abcdef", "<REDACTED>\nopaque0123456789abcdef"),
        ("a token with one character changed", "sk-" + "b" * 20, "sk-" + "b" * 19 + "c"),
        ("an email with its domain masked", "write to alice.developer@example.com",
         "write to alice.developer@<REDACTED>"),
    ]
    for label, raw, planted in partial_cases:
        if not floor_survivors(raw, planted):
            failures.append(f"the oracle accepted a deliberately partial mask ({label}): {planted!r}")
    for label, raw, _planted in partial_cases:
        if floor_survivors(raw, FLOOR.PLACEHOLDER):
            failures.append(f"the oracle reports a survivor in a wholly masked output ({label})")
    unit = [("a credential shorter than the unit is asked about whole", survives("short", "a short word"), True),
            ("... and is not found when it is absent", survives("short", "a long word"), False),
            ("eight characters of a credential standing together is a survival",
             survives("abcdefghij", "x abcdefgh y"), True),
            ("seven are not", survives("abcdefghij", "x abcdefg y"), False)]
    for label, got, want in unit:
        if got is not want:
            failures.append(f"the oracle's unit of survival is wrong: {label} gave {got}")

    # the oracle asks about the CREDENTIAL, not about the key that named it: the keyed rule keeps that key on
    # purpose, so asking about the whole match would report a survivor wherever the key is kept, and a
    # control reading that report would call a correct projection a leak. No corpus string tells the two
    # apart today - wherever the floor matches, its own span masks the key too - so the contract is asserted
    # directly.
    keyed_cases = [("a header with a scheme", "Authorization: Bearer abcdefgh01234567", "abcdefgh01234567"),
                   ("a header split by a newline", "Authorization: Bearer\nopaque0123456789", "opaque0123456789"),
                   ("an assignment with no scheme", "api_key=live_0123456789abcdef", "live_0123456789abcdef")]
    for label, text, credential in keyed_cases:
        found = [secret_part(m) for pattern in floor_patterns() for m in pattern.finditer(text)
                 if pattern.groups and m.group(1) is not None]
        if found[:1] != [credential]:
            failures.append(f"the oracle reads the wrong part of {label} as the credential: {found}")
    plain = [secret_part(m) for m in floor_patterns()[1].finditer("use sk-" + "A1b2" * 6 + " now")]
    if plain != ["sk-" + "A1b2" * 6]:
        failures.append(f"the oracle reads a pattern with no key as something other than its whole match: {plain}")

    # ... and every pattern the floor carries has a positive case in this corpus. A pattern with no case is
    # a pattern this self-test says nothing about, so it fails by name rather than passing quietly.
    pattern_cases = {
        "the keyed header or assignment": "Authorization: Bearer abcdefgh01234567ijklmnop",
        "an sk- token": "use sk-" + "A1b2" * 6 + " now",
        "a GitHub token": "ghp_" + "C3d4" * 6,
        "a JWT": "eyJ" + "E5f6" * 6 + ".rest",
        "an AWS key id": "AKIA" + "G7H8I9J0K1L2",
        "an email": "write to alice.developer@example.com",
    }
    uncovered = [pattern.pattern[:40] for pattern in floor_patterns()
                 if not any(pattern.search(text) for text in pattern_cases.values())]
    if uncovered:
        failures.append(f"{len(uncovered)} floor pattern(s) have no positive case in this self-test: {uncovered}")
    for label, text in pattern_cases.items():
        if floor_leftovers(text, owner):
            failures.append(f"{label} survives the projection: {text!r} -> {project_text(text, owner)!r}")
        if project_text(text, owner) == text:
            failures.append(f"{label} was not masked at all: {text!r}")

    # The two ways the floor can stop being readable. Neither can be reached by any input, so each is reached
    # by replacing what the module reads - and both must fail BY NAME, because a floor whose patterns cannot
    # be read is a projection that would otherwise mask less than the floor and say nothing.
    kept_patterns = FLOOR.SECRET_RE
    try:
        for label, planted in (("SECRET_RE is not a list", "sk-"), ("SECRET_RE is empty", []),
                               ("a member is not a compiled pattern", [kept_patterns[0], r"sk-\d+"])):
            FLOOR.SECRET_RE = planted
            try:
                project_text("Authorization: Bearer abc0123456789xyz", owner)
                failures.append(f"a floor whose {label} was read as if it were usable")
            except FloorUnreadable as exc:
                if "REDACTION_FLOOR_UNREADABLE" not in str(exc):
                    failures.append(f"a floor whose {label} failed unnamed: {exc}")
    finally:
        FLOOR.SECRET_RE = kept_patterns
    if floor_patterns() is not kept_patterns:
        failures.append("the floor's patterns were not restored after the planted failures")

    # ---- M#1: the choke point, held structurally rather than remembered --------------------------
    #
    # Every block this module returns must leave through `emit`, because `emit` is where the backstop runs.
    # A call added at each site is a rule someone forgets at the next site - which is exactly what happened:
    # the structured path serialised its walk and returned it unverified. So the question is asked of the
    # SOURCE: in each block-producing function, every `return` is a call to `emit`.
    import ast as _ast
    module = _ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))

    # ---- R#0 / U#4: the verifier is independent of the mapping, as one callable ------------------
    #
    # The backstop exists to catch the mapping's mistakes. Any reading of the mapping's own state makes it
    # blind exactly where the mapping is blind, which is what let a duplicate member through. The check is
    # ONE function returning named violations, so the same code can be run on this module and on an AST with
    # a dependency planted below an entry point - the second run is what proves the first one looks.
    verifier_entry = {"vf_unescape", "vf_load", "vf_structures", "vf_members", "vf_keyed", "vf_exempt",
                      "vf_scalar", "vf_region", "vf_unfinished", "all_mask", "every_spelling", "discloses",
                      "spellings_of"}
    detectors = {"floor_patterns", "home_patterns", "secret_key", "is_mask", "floor_key_alternation",
                 "secret_part", "note_change", "blank_for", "parses_as_json"}
    mapping = {"mask_extents", "decoded_extents", "floor_spans", "floor_spans_normalised", "keyed_spans",
               "path_spans", "literal_ranges", "within_literals", "visible_secret_keys",
               "encoded_secret_keys", "escaped_regions", "escape_map", "structures_in", "relaxed_decode",
               "spans_of", "mask_spans", "mask_one", "holds_secret", "undecodable_claim", "project_text",
               "obligations", "floor_leftovers", "spellings", "unterminated", "mask_free", "survives"}

    def independence_violations(tree, entry_points):
        """Every place the verifier's reachable closure in `tree` touches the mapping, by name.

        The closure is computed from the call graph rather than read from a list, because a helper three
        calls down is as much the verifier as its entry point is."""
        bodies = {node.name: node for node in _ast.walk(tree) if isinstance(node, _ast.FunctionDef)}

        def calls_of(name):
            node = bodies.get(name)
            return set() if node is None else {call.func.id for call in _ast.walk(node)
                                               if isinstance(call, _ast.Call)
                                               and isinstance(call.func, _ast.Name)}

        reached, pending = set(), list(entry_points)
        while pending:
            name = pending.pop()
            if name in reached or name not in bodies:
                continue
            reached.add(name)
            pending += [called for called in calls_of(name)
                        if called in bodies and called not in detectors]
        return sorted(f"{name} -> {called}" for name in reached for called in calls_of(name) & mapping), reached

    violations, reached = independence_violations(module, verifier_entry)
    failures += [f"the verifier is not independent of the mapping: {violation}" for violation in violations]
    if reached & verifier_entry != verifier_entry:
        failures.append(f"the independence check reached {sorted(reached & verifier_entry)} rather than "
                        f"{sorted(verifier_entry)}, so it is asking about functions that no longer exist")
    defined = {node.name for node in _ast.walk(module) if isinstance(node, _ast.FunctionDef)}
    if mapping - defined:
        failures.append(f"the independence check forbids {sorted(mapping - defined)}, which this module "
                        "does not define, so those entries forbid nothing")
    # ... and the SAME callable on an AST whose dependency sits one call below an entry point
    planted_tree = _ast.parse("def vf_unescape(text):\n    return vf_planted_helper()\n"
                              "def vf_planted_helper():\n    return keyed_spans('')\n")
    planted_violations, _planted_reached = independence_violations(planted_tree, {"vf_unescape"})
    if planted_violations != ["vf_planted_helper -> keyed_spans"]:
        failures.append("the independence check does not report a dependency planted one call below an "
                        f"entry point: {planted_violations}")

    # ---- M#1: the choke point, held structurally rather than remembered --------------------------
    #
    # Every block this module returns must leave through `emit`, because `emit` is where the backstop runs.
    # A call added at each site is a rule someone forgets at the next site - which is exactly what happened:
    # the structured path serialised its walk and returned it unverified. So the question is asked of the
    # SOURCE: in each block-producing function, every `return` is a call to `emit`.
    import ast as _ast
    module = _ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))

    # ---- R#0: the verifier is independent of the mapping, and that is a source-level fact ---------
    #
    # The backstop exists to catch the mapping's mistakes. Any reading of the mapping's own state - which
    # keys it located, which extents it covered, its scanner for a keyed value - makes it blind in exactly
    # the places the mapping is blind, which is what let a duplicate member through: the mapping declared
    # the key covered by name, and the verifier asked the mapping. So the verifier's functions may use the
    # FLOOR and the detectors, and nothing of the mapping.
    # The guard follows the verifier's whole REACHABLE closure, not a list of its entry points: a helper
    # three calls down is as much the verifier as `discloses` is, and a dependency added there would have
    # been invisible to a check that only read the names it was given. The closure is computed from the call
    # graph, and a planted dependency below must be rejected by it.
    bodies = {node.name: node for node in _ast.walk(module) if isinstance(node, _ast.FunctionDef)}
    detectors = {"floor_patterns", "home_patterns", "secret_key", "is_mask", "floor_key_alternation",
                 "secret_part", "note_change", "blank_for", "parses_as_json"}
    mapping = {"mask_extents", "decoded_extents", "floor_spans", "floor_spans_normalised", "keyed_spans",
               "path_spans", "literal_ranges", "within_literals", "visible_secret_keys",
               "encoded_secret_keys", "escaped_regions", "escape_map", "structures_in", "relaxed_decode",
               "spans_of", "mask_spans", "mask_one", "holds_secret", "undecodable_claim", "project_text",
               "obligations", "floor_leftovers", "spellings", "unterminated", "mask_free", "survives"}

    def calls_of(name):
        node = bodies.get(name)
        if node is None:
            return set()
        return {call.func.id for call in _ast.walk(node)
                if isinstance(call, _ast.Call) and isinstance(call.func, _ast.Name)}

    entry_points = {"vf_unescape", "vf_load", "vf_structures", "vf_members", "vf_keyed", "vf_exempt",
                    "vf_unfinished", "all_mask", "every_spelling", "discloses", "spellings_of"}
    verifier, pending = set(), list(entry_points)
    while pending:
        name = pending.pop()
        if name in verifier or name not in bodies:
            continue
        verifier.add(name)
        pending += [called for called in calls_of(name)
                    if called in bodies and called not in detectors]
    for name in sorted(verifier):
        for called in sorted(calls_of(name) & mapping):
            failures.append(f"the verifier's {name} calls the mapping's {called}, so the backstop shares "
                            "the blindness it exists to catch")
    seen_verifier = verifier & entry_points
    verifier = entry_points
    # ... and the guard really follows the closure: a dependency planted one call BELOW an entry point must
    # be rejected, or the traversal is only reading the names it was handed
    planted = _ast.parse("def vf_planted_helper():\n    return keyed_spans('')\n"
                         "def vf_planted_entry():\n    return vf_planted_helper()\n")
    planted_bodies = {node.name: node for node in planted.body}
    bodies.update(planted_bodies)
    reached, pending = set(), ["vf_planted_entry"]
    while pending:
        name = pending.pop()
        if name in reached or name not in bodies:
            continue
        reached.add(name)
        pending += [called for called in calls_of(name) if called in bodies and called not in detectors]
    if not any(calls_of(name) & mapping for name in reached):
        failures.append("the independence guard does not follow a dependency planted one call below an "
                        "entry point, so it only checks the functions it was handed")
    if seen_verifier != verifier:
        failures.append(f"the independence check found {sorted(seen_verifier)} rather than "
                        f"{sorted(verifier)}, so it is asking about functions that no longer exist")
    # ... and the mapping names it checks for are real functions of this module, or the check forbids nothing
    defined = {node.name for node in _ast.walk(module) if isinstance(node, _ast.FunctionDef)}
    if mapping - defined:
        failures.append(f"the independence check forbids {sorted(mapping - defined)}, which this module "
                        "does not define, so those entries forbid nothing")

    producers = {"project_text", "project_r22"}
    checked = set()
    for node in _ast.walk(module):
        if not isinstance(node, _ast.FunctionDef) or node.name not in producers:
            continue
        checked.add(node.name)
        for statement in _ast.walk(node):
            if not isinstance(statement, _ast.Return) or statement.value is None:
                continue
            call = statement.value
            if not (isinstance(call, _ast.Call) and isinstance(call.func, _ast.Name)
                    and call.func.id == "emit"):
                failures.append(f"{node.name} returns a block at line {statement.lineno} without passing "
                                "through emit(), so that block is never verified")
    if checked != producers:
        failures.append(f"the choke-point check found {sorted(checked)} rather than {sorted(producers)}, so "
                        "it is asking about functions that no longer exist")
    # ... and the exit really runs for both shapes of input, or the check above is about dead code
    before_emitted = STATS["emitted"]
    project_text("plain text", owner)
    project({"note": "plain"}, home=owner)
    if STATS["emitted"] - before_emitted < 2:
        failures.append("a string block and a structured block did not both leave through emit()")

    # ---- A#2: a seeded property control whose transformations are REAL ---------------------------
    #
    # The previous generator advertised four spellings and delivered two: no generated credential held a
    # slash, so slash-escaping was a no-op, and double-encoding a credential with no special characters
    # changed nothing. Worse, the leak check looked for the PLAIN credential, so a case whose credential was
    # emitted escaped could pass while the escaped spelling stood in the output.
    #
    # Each case now records the spelling it actually emitted, each class asserts that its transformation
    # changed the text, and the output is decoded independently - every form the output takes through this
    # module's decodings - before the credential is looked for in any of them.
    rnd = random.Random(20261021)

    def still_reads(secret, out, emitted=None):
        """The ONE predicate every generated case and every planted control is judged by: does any spelling
        the VERIFIER can reach from `out` still carry this credential, whole or in a run long enough to
        matter? Built on `every_spelling`, so the oracle does not share the projection's coordinates - and
        used for the deliberately unredacted and deliberately partial outputs below, so what it rejects is
        proven rather than assumed."""
        forms = spellings_of(out)
        wanted = [secret] + ([emitted] if emitted and emitted != secret else [])
        for form in forms:
            for value in wanted:
                if value in form:
                    return True
                if len(value) >= PARTIAL_SURVIVAL and any(
                        value[at:at + PARTIAL_SURVIVAL] in form
                        for at in range(len(value) - PARTIAL_SURVIVAL + 1)):
                    return True
        return False

    # ---- AD#0 / AD#1: the spelling set is CLOSED under the transforms ----------------------------
    #
    # Two orders were missing when the set was "each decode layer, expanded by the skeleton": the
    # invisible characters were stripped only inside the casefolded skeleton, so a case-sensitive owner
    # path or credential pattern never saw a stripped, case-preserved spelling; and an escape that
    # normalisation REVEALS was never decoded, because decoding ran before normalising and never again.
    # The closure makes every composition reachable, and this control asserts the closure IS closed.
    closure_subjects = [
        '{"note":"plain"} caf' + chr(0xE9),
        "/Us" + chr(0x200B) + "ers/kangmin/notes.md",
        "a " + chr(0xFF3C) + "u0070assword field",
        chr(0xC554) + chr(0xD638) + " " + chr(0xD544) + chr(0xB4DC),
    ]
    for subject in closure_subjects:
        members_set, _members, closure_reach = vf_all_spellings(subject)
        if closure_reach.exhausted:
            failures.append(f"the closure of {subject[:28]!r} did not finish: {closure_reach.reason!r}")
            continue
        if not members_set:
            failures.append(f"the closure of {subject[:28]!r} is empty, so closure proves nothing")
            continue
        held = set(members_set)
        for spelling in members_set:
            for step in vf_transforms(spelling):
                if step not in held:
                    failures.append(f"the spelling set is not closed: a transform of {spelling[:24]!r} "
                                    f"gives {step[:24]!r}, which is not in the set")
                    break
    # ... one shape per ORDER, each refused. The last is refused as undecodable rather than by name,
    # because `\U` is outside the escape table and AA#0's refusal fires before any casefolding - still a
    # refusal, which is what the boundary owes.
    orders = [
        ("an invisible character inside a case-sensitive owner path",
         "/Us" + chr(0x200B) + "ers/kangmin/notes.md", "the owner's home path"),
        ("an invisible character inside a case-sensitive credential",
         "sk-abcdefghij" + chr(0x200B) + "klmnopqrst", "the floor claims"),
        ("an escape revealed by NFKC", "a " + chr(0xFF3C) + "u0070assword field", "password"),
        ("an escape revealed by casefolding", "A " + chr(92) + "U0070ASSWORD FIELD", "undecodable"),
    ]
    for label, text, expected in orders:
        allowed, why = evidence_quote_admissible(text, "/Users/kangmin")
        if allowed:
            failures.append(f"the strict rule admits {label}")
        elif expected not in (why or ""):
            failures.append(f"{label}: refused for the wrong reason: {why!r}")
    # ... and the admitted side, so the closure is not refusing everything it reaches
    for label, text in (("ordinary Korean text", chr(0xC554) + chr(0xD638) + " " + chr(0xD544) + chr(0xB4DC)),
                        ("an ordinary escaped e-acute", "caf" + chr(92) + "u00e9 on the menu"),
                        ("an emoji with a ZWJ sequence",
                         "a family " + chr(0x1F468) + chr(0x200D) + chr(0x1F469) + chr(0x200D)
                         + chr(0x1F467) + " here")):
        allowed, why = evidence_quote_admissible(text, "/Users/kangmin")
        if not allowed:
            failures.append(f"the strict rule refuses {label}, which names nothing: {why!r}")
    # ... and the bound itself REFUSES by name rather than truncating. Asserted by lowering the bound
    # around a quote the closure handles comfortably, so the control reads the bound and not one
    # hand-built pathological string.
    held_limit, held_rounds = VF_CLOSURE_LIMIT, VF_CLOSURE_ROUNDS
    try:
        globals()["VF_CLOSURE_LIMIT"] = 2
        allowed, why = evidence_quote_admissible('{"note":"plain"} caf' + chr(0xE9), "/Users/kangmin")
        if allowed or "spells more than 2 strings" not in (why or ""):
            failures.append(f"the closure's size bound does not refuse by name: {why!r}")
        globals()["VF_CLOSURE_LIMIT"] = held_limit
        globals()["VF_CLOSURE_ROUNDS"] = 1
        allowed, why = evidence_quote_admissible('{"note":"plain"} caf' + chr(0xE9), "/Users/kangmin")
        if allowed or "still growing after 1 round" not in (why or ""):
            failures.append(f"the closure's round bound does not refuse by name: {why!r}")
    finally:
        globals()["VF_CLOSURE_LIMIT"], globals()["VF_CLOSURE_ROUNDS"] = held_limit, held_rounds
    # ... and the bounds are back, so nothing after this runs under a lowered one
    if (VF_CLOSURE_LIMIT, VF_CLOSURE_ROUNDS) != (held_limit, held_rounds):
        failures.append("the closure bounds were left lowered by the control that tested them")

    # ---- AC#0: the three triggers see ONE spelling set ------------------------------------------
    #
    # The name detector expanded the normalised spellings inside itself; the floor's value patterns and
    # the owner-path detector saw the decoded string alone. So a fullwidth or zero-width-spaced owner
    # path, and a fullwidth floor match, were judged by a narrower set than a name was.
    fullwidth = {character: chr(ord(character) - 0x61 + 0xFF41) for character in "abcdefghijklmnopqrstuvwxyz"}
    def wide(text):
        return "".join(fullwidth.get(character, character) for character in text)
    zwsp, acute = chr(0x200B), chr(0x0301)
    variants = [
        ("an owner path with a fullwidth letter", "/U" + wide("sers") + "/kangmin/notes.md",
         "the owner's home path"),
        ("an owner path with a zero-width space", "/Users/kang" + zwsp + "min/notes.md",
         "the owner's home path"),
        ("an owner path with a combining mark", "/Users/kangmi" + acute + "n/notes.md",
         "the owner's home path"),
        ("a floor value in fullwidth", "sk-" + wide("abcdefghijklmnopqrst"), "the floor claims"),
        ("a floor value with a zero-width space", "sk-abcdefghij" + zwsp + "klmnopqrst", "the floor claims"),
    ]
    for label, text, expected in variants:
        allowed, why = evidence_quote_admissible(text, "/Users/kangmin")
        if allowed:
            failures.append(f"the strict rule admits {label}")
        elif expected not in (why or ""):
            failures.append(f"{label}: refused by the wrong detector: {why!r}")
    # ... and the admitted side, so the uniform loop is not simply refusing everything
    for label, text in (("an ordinary non-owner path with Unicode letters", "/opt/caf" + chr(0xE9) + "/bin/tool"),
                        ("ordinary Korean text", chr(0xC554) + chr(0xD638) + " " + chr(0xD544) + chr(0xB4DC)),
                        ("a plain sentence", "three files changed")):
        allowed, why = evidence_quote_admissible(text, "/Users/kangmin")
        if not allowed:
            failures.append(f"the strict rule refuses {label}: {why!r}")
    # ... and the structural claim itself: each detector was asked about the SAME strings. Asked of an
    # ADMITTED quote, because a refusal returns early and would leave the three lists different lengths
    # for a reason that is not divergence.
    global SPELLING_PROBE
    SPELLING_PROBE = {}
    try:
        # an admitted quote with a structure to decode, and NO backslash: a `\\u0070` body would be
        # refused as undecodable before the loop runs, and the probe would record nothing
        evidence_quote_admissible('{"note":"plain","n":2} caf' + chr(0xE9), "/Users/kangmin")
        seen = {detector: tuple(items) for detector, items in SPELLING_PROBE.items()}
    finally:
        SPELLING_PROBE = None
    if sorted(seen) != ["floor", "home", "name"]:
        failures.append(f"strict admission did not run all three detectors: {sorted(seen)}")
    elif len(set(seen.values())) != 1:
        widths = {detector: len(items) for detector, items in seen.items()}
        narrowest = min(widths, key=widths.get)
        failures.append(f"the three strict detectors were handed different spelling sets - {narrowest!r} "
                        f"saw the narrowest, {widths}")
    elif not seen["name"]:
        failures.append("the spelling probe recorded nothing, so the identity of the three sets is vacuous")
    # ... and the set really is every decode depth times every normalisation
    shared_set, _members, _reach = vf_all_spellings('{"note":"' + chr(92) + 'u0070lain"}')
    if not any("plain" in form for form in shared_set):
        failures.append("the shared spelling set does not reach a name behind a layer of escaping")
    if wide("secret") not in vf_all_spellings(wide("secret"))[0]:
        failures.append("the shared spelling set drops the text as it stands")
    if "secret" not in vf_all_spellings(wide("secret"))[0]:
        failures.append("the shared spelling set does not normalise a fullwidth spelling")

    # ---- AB#0: the skeleton drops every character that renders nothing of its own ----------------
    #
    # Dropping only `Mn` closed accents and left the rest standing: `pass<ZWSP>word` reads as the name to
    # a person, tokenised as two ordinary names, and the floor was asked about neither.
    invisibles = [("an Mn mark", 0x0301), ("an Mc mark", 0x093E), ("an Me mark", 0x0488),
                  ("a zero-width space", 0x200B), ("a zero-width joiner", 0x200D),
                  ("a zero-width non-joiner", 0x200C), ("a soft hyphen", 0x00AD),
                  ("a word joiner", 0x2060), ("a bidi override", 0x202E),
                  ("a variation selector", 0xFE0F), ("a supplementary variation selector", 0xE0100),
                  ("a tag character", 0xE0041), ("an unassigned tag code point", 0xE0002),
                  ("a Mongolian free variation selector", 0x180B), ("a Mongolian separator", 0x180E),
                  ("a Hangul choseong filler", 0x115F), ("a halfwidth Hangul filler", 0xFFA0)]
    for label, code in invisibles:
        if not vf_invisible(chr(code)):
            failures.append(f"{label} (U+{code:04X}) is not read as invisible")
        spelled = "the pass" + chr(code) + "word field"
        if vf_secret_name(spelled) != "password":
            failures.append(f"{label} inside the name hides it from the floor: "
                            f"{vf_secret_name(spelled)!r}")
        allowed, why = evidence_quote_admissible(spelled, owner)
        if allowed:
            failures.append(f"the strict rule admits a quote with {label} inside a secret name")
        elif "password" not in (why or ""):
            failures.append(f"{label}: the refusal does not name the token: {why!r}")
    # ... every entry in the list is load-bearing: one a category already covers is a line no revert can
    # make fail, and this is the assertion that keeps the list honest as Unicode assigns new characters
    covered = sorted(code for code in VF_IGNORABLE
                     if unicodedata.category(chr(code)) in VF_INVISIBLE_CATEGORIES)
    if covered:
        failures.append(f"VF_IGNORABLE lists {len(covered)} code point(s) a category already covers, "
                        f"starting at U+{covered[0]:04X}")
    if not vf_invisible(chr(0xE0002)):
        failures.append("an unassigned tag code point (U+E0002) is not read as invisible")
    # ... and a character that renders something of its own is NOT dropped, so this is not a confusable
    # mapping: a Cyrillic lookalike stays a different name, which is the scope the owner set on
    # 2026-10-22 and a tracked residual rather than a gap
    for label, code in (("a Cyrillic a", 0x0430), ("an ordinary letter", ord("a")),
                        ("a Hangul syllable", 0xC554), ("an emoji", 0x1F600)):
        if vf_invisible(chr(code)):
            failures.append(f"{label} (U+{code:04X}) is read as invisible, which it is not")
    # ... and the invisible characters where they name nothing are admitted
    admitted = [("ordinary Korean text", chr(0xC554) + chr(0xD638) + " " + chr(0xD544) + chr(0xB4DC)),
                ("an emoji with a ZWJ sequence",
                 chr(0x1F468) + chr(0x200D) + chr(0x1F469) + chr(0x200D) + chr(0x1F467)),
                ("a variation selector in a non-secret word", "caf" + chr(0xE9) + chr(0xFE0F) + " menu")]
    for label, text in admitted:
        if vf_secret_name(text) is not None:
            failures.append(f"{label} is read as naming a secret: {vf_secret_name(text)!r}")
        allowed, why = evidence_quote_admissible("a " + text + " stands here", owner)
        if not allowed:
            failures.append(f"the strict rule refuses {label}, which names nothing: {why!r}")

    # ---- AA#0: the strict traversal decodes the JSON escape table and nothing else ---------------
    #
    # The lenient reading drops a backslash before anything at all, so it read `\x41` as `x41`, reported no
    # layer left undone, and an unsupported escape passed strict admission. The strict side tracks this
    # itself: every sequence the table does not define is undecodable, at any decode depth.
    slash = chr(0x5C)
    for label, run in (("an \\x escape", slash + "x41"), ("a \\q escape", slash + "q"),
                       ("a short \\u escape", slash + "u12"), ("a \\U escape", slash + "U0001D5C9"),
                       ("an \\8 escape", slash + "8")):
        if vf_outside_table("a " + run + " field") is None:
            failures.append(f"{label} was read as a sequence the table defines")
        if vf_undecodable("a " + run + " field") is None:
            failures.append(f"{label} was not reached by the strict traversal")
        allowed, why = evidence_quote_admissible("a " + run + " field", owner)
        if allowed or "undecodable" not in (why or ""):
            failures.append(f"the strict rule does not refuse {label} as undecodable: {why!r}")
    if vf_outside_table("a field ends here " + slash) != slash:
        failures.append("a trailing lone backslash was read as a sequence the table defines")
    if evidence_quote_admissible("a field ends here " + slash, owner)[0]:
        failures.append("the strict rule admits a quote ending in a lone backslash")
    # ... at any depth: behind one layer of escaping, and inside a JSON structure the text spells
    behind = slash + slash + "x41 stands behind one layer"
    if vf_outside_table(behind) is not None:
        failures.append(f"the top layer of {behind!r} is not itself outside the table, so the depth case "
                        f"proves nothing")
    if vf_undecodable(behind) is None:
        failures.append("an unsupported escape behind one layer of escaping was not reached")
    if evidence_quote_admissible(behind, owner)[0]:
        failures.append("the strict rule admits an unsupported escape behind one layer of escaping")
    inside = '{"note":"' + slash + slash + 'x41"}'
    if vf_undecodable(inside) is None:
        failures.append("an unsupported escape inside a spelled JSON structure was not reached")
    if evidence_quote_admissible(inside, owner)[0]:
        failures.append("the strict rule admits an unsupported escape inside a spelled structure")
    # ... and the table's own escapes, with characters that need none, are read and admitted
    table_only = "a " + slash + "n b " + slash + '" c ' + slash + "/ d " + chr(0xE9) + " " + chr(0x1F600)
    if vf_outside_table(table_only) is not None:
        failures.append(f"a table escape was read as outside it: {vf_outside_table(table_only)!r}")
    if vf_undecodable(table_only) is not None:
        failures.append(f"the strict traversal refuses the table's own escapes: "
                        f"{vf_undecodable(table_only)!r}")
    if not evidence_quote_admissible(table_only, owner)[0]:
        failures.append("the strict rule refuses a quote holding only table escapes")

    # ---- Y#0: a surrogate pair is one character, and a lone surrogate is none -------------------
    #
    # Reading the halves separately produced two lone surrogates, which no normalisation maps: a
    # compatibility name written in mathematical letters arrived as unmappable halves and the floor was
    # never asked about the name they spell. On the strict side an encoding this traversal cannot finish
    # refuses the quote, which is why a lone surrogate must say so rather than pass as a character.
    maths = "".join(chr(0x1D5BA + (ord(character) - ord("a"))) for character in "password")
    paired = "".join(f"\\u{((ord(c) - 0x10000) >> 10) + 0xD800:04x}"
                     f"\\u{((ord(c) - 0x10000) & 0x3FF) + 0xDC00:04x}" for c in maths)
    if vf_unescape(paired) != maths:
        failures.append(f"a surrogate pair did not decode to its character: {vf_unescape(paired)!r}")
    if vf_relax("prefix " + paired + " suffix") != "prefix " + maths + " suffix":
        failures.append("the relaxed reading did not join a surrogate pair inside ordinary text")
    if vf_secret_name(maths) != "password":
        failures.append(f"the floor was not asked about the name those letters spell: "
                        f"{vf_secret_name(maths)!r}")
    for label, text in (("a lone high surrogate", "a field \\ud83d here"),
                        ("a lone low surrogate", "a field \\ude00 here"),
                        ("a high surrogate followed by an ordinary escape", "x \\ud83d\\u0041 y"),
                        ("a pair with too few digits in its second half", "x \\ud83d\\ude0 y")):
        if vf_unescape(text) is not None:
            failures.append(f"{label} decoded to something: {vf_unescape(text)!r}")
        if not vf_unfinished(text):
            failures.append(f"{label} was not reported as an unfinished run")
        allowed, why = evidence_quote_admissible(text, owner)
        if allowed or "undecodable" not in (why or ""):
            failures.append(f"the strict rule does not refuse {label} as undecodable: {why!r}")
    # ... and an ordinary non-ASCII word, escaped, is read and admitted
    for label, text in (("an escaped Korean word", "\\uc554\\ud638 \\ud544\\ub4dc"),
                        ("an escaped emoji, written as a pair", "see \\ud83d\\ude00 here")):
        if vf_unescape(text) is None:
            failures.append(f"{label} was not readable: {text!r}")
        if vf_unfinished(text):
            failures.append(f"{label} was reported as an unfinished run")
        allowed, _why = evidence_quote_admissible(text, owner)
        if not allowed:
            failures.append(f"the strict rule refuses {label}, which names nothing")

    # T#1: the exemption is EXACT equality, asked of the rule itself. A value that starts with the mask, or
    # ends with it, or carries a comma after it, is a value with something else still in it - and the
    # generous traversal catches most such shapes by another route, so the rule is held where it lives
    # rather than only through a block.
    for value, exempt in ((FLOOR.PLACEHOLDER, True), (HOME_MASK, True), ("", True),
                          ('"' + FLOOR.PLACEHOLDER + '"', True),
                          (FLOOR.PLACEHOLDER + ",", True),          # packaging, not content
                          (FLOOR.PLACEHOLDER + " ", True), (" " + FLOOR.PLACEHOLDER, True),
                          (FLOOR.PLACEHOLDER + "};", True),
                          (FLOOR.PLACEHOLDER + " u0after", False),
                          ("u0before " + FLOOR.PLACEHOLDER, False),
                          (FLOOR.PLACEHOLDER * 2, False),
                          # the scanner reads a quoted scalar WHOLE, so a comma inside it is content
                          ('"' + FLOOR.PLACEHOLDER + ',u0comma_canary"', False),
                          ('"' + FLOOR.PLACEHOLDER + ' u0space_canary"', False),
                          # ... and a scalar it cannot read to its close is a finding, not a pass
                          ('"' + FLOOR.PLACEHOLDER + " u0unterminated", False),
                          ('"' + FLOOR.PLACEHOLDER + " u0trailing\\", False)):
        if vf_exempt(value) != exempt:
            failures.append(f"the keyed-fragment exemption reads {value!r} as "
                            f"{'exempt' if vf_exempt(value) else 'a finding'}, which is wrong")

    # ---- the stricter quote rule, measured rather than enforced --------------------------------
    #
    # `evidence_quote_admissible` is not wired into anything yet. It is here so the cost of making it the
    # rule can be read off a measurement instead of guessed at, and these controls say what it would mean.
    quote_cases = [
        ("an ordinary sentence", "the tool reported three files changed", True),
        ("a masked keyed fragment, which the projection allows and this does not",
         '"password": "' + FLOOR.PLACEHOLDER + '"', False),
        ("a secret-named token on its own", "rotate the refresh_token next week", False),
        ("a credential the floor claims", "sk-" + "Ab1_" * 6, False),
        ("the owner's home path", owner + "/Documents/notes.md", False),
        ("a secret-named key inside a decoded document",
         json.dumps({"password": FLOOR.PLACEHOLDER}, ensure_ascii=False), False),
        ("a secret-named key one encoding down",
         '{"' + "".join(f"\\u{ord(ch):04x}" for ch in "password") + '":"' + FLOOR.PLACEHOLDER + '"}', False),
        ("an encoding this verifier cannot finish", "a quote ending in a backslash\\", False),
        ("the mask by itself", FLOOR.PLACEHOLDER, True),
    ]
    for label, quote, admissible in quote_cases:
        allowed, why = evidence_quote_admissible(quote, owner)
        if allowed != admissible:
            failures.append(f"the stricter quote rule reads {label} as "
                            f"{'admissible' if allowed else 'refused'}: {why!r}")
        if not allowed and not why:
            failures.append(f"the stricter quote rule refused {label} without naming a reason")

    # S#2: the extent rule itself, on a pair that differs only in whether a raw detector covers the plant
    covered = '{"password":"s2plainCredentialValue"}'
    uncovered = '{"' + "".join(f"\\u{ord(ch):04x}" for ch in "password") + '":"s2plainCredentialValue"}'
    spots = [(start, end) for start, end, _replacement, _rank in keyed_spans(covered)]
    if not any(start <= covered.find("s2plainCredentialValue") < end for start, end in spots):
        failures.append("the keyed locator does not cover a plainly keyed credential, so the extent rule "
                        "below is not measuring coverage")
    if any(start <= uncovered.find("s2plainCredentialValue") < end
           for start, end, _replacement, _rank in keyed_spans(uncovered)):
        failures.append("the keyed locator covers a credential under an ENCODED key, so a case of a "
                        "decoding class cannot be distinguished from a raw one")

    # the oracle rejects an output that was not redacted at all, and one that was redacted by half
    oracle_secret = "sk-" + "Zz9Q" * 5
    oracle_controls = [
        ("an encoded credential left entirely unredacted",
         '{"note":"' + "".join(f"\\u{ord(ch):04x}" for ch in oracle_secret) + '"}'),
        ("a credential whose first half alone was masked",
         '{"note":"' + FLOOR.PLACEHOLDER + oracle_secret[10:] + '"}'),
        ("a credential inside a doubly encoded document",
         json.dumps({"payload": json.dumps({"v": oracle_secret}, ensure_ascii=False)}, ensure_ascii=False)),
        # S#2: fully and partially surviving ENCODED outputs, through this same predicate
        ("an encoded credential surviving whole",
         '{"v":"' + "".join(f"\\u{ord(ch):04x}" for ch in oracle_secret) + '"}'),
        ("an encoded credential surviving by half",
         '{"v":"' + FLOOR.PLACEHOLDER
         + "".join(f"\\u{ord(ch):04x}" for ch in oracle_secret[10:]) + '"}'),
        ("a credential surviving inside an escaped document",
         '\\"v\\": \\"' + oracle_secret + '\\"'),
    ]
    for label, planted_output in oracle_controls:
        if not still_reads(oracle_secret, planted_output):
            failures.append(f"the oracle accepts {label}, so every judgement it makes below is vacuous")
    if still_reads(oracle_secret, FLOOR.PLACEHOLDER):
        failures.append("the oracle reads a credential in the mask itself, so it can never report clean")

    def body(length, alphabet="abcdefghijkmnpqrstuvwxyz23456789"):
        """A distinctive credential body: repeated filler would let two generated secrets share a run of
        eight characters, and the oracle would then read one as the other."""
        return "".join(rnd.choice(alphabet) for _ in range(length))

    def floor_shape(which):
        """A credential the FLOOR itself claims, in the shape `which` names."""
        return {"sk": "sk-" + body(20), "ghp": "ghp_" + body(22),
                "jwt": "eyJ" + body(22) + ".rest", "akia": "AKIA" + body(14, "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"),
                "email": body(10) + ".dev@example.com"}[which]

    def u_escape(text, portion=0.4):
        return "".join(f"\\u{ord(ch):04x}" if ch.isalnum() and rnd.random() < portion else ch for ch in text)

    def emitted_in(text, spelling):
        """The spelling as `text` really carries it - the planted extent, not a guess.

        Each nesting doubles the backslashes of the layer inside it, so the spelling a generator wrote and
        the one the finished text holds are different strings. The extent checks below are about the
        characters that are actually there, so the doubling is followed until it matches."""
        form = spelling
        for _doubling in range(5):
            if form and form in text:
                return form
            form = form.replace("\\", "\\\\")
        return None

    cases = []        # (class, text, the credential, the spelling that was emitted)
    for which in ("sk", "ghp", "jwt", "akia", "email"):
        for _round in range(4):
            # 1. a credential inside an ESCAPED literal: only the escaped reading finds it
            secret = floor_shape(which)
            cases.append(("escaped literal", '{\\"note\\": \\"' + secret + '\\"}', secret, secret))
            # 2. a \u escape: the credential's own characters are written as escapes
            secret = floor_shape(which)
            spelled = u_escape(secret, 0.6)
            cases.append(("u-escaped value", '{"note":"' + spelled + '"}', secret, spelled))
            # 3. a \/ escape, over a value that HAS slashes - an owner path, which is what carries them
            path = f"{owner}/Documents/{body(6)}/notes.md"
            cases.append(("slash-escaped path", '{"at":"' + path.replace("/", "\\/") + '"}',
                          owner, path.replace("/", "\\/")))
            # 4. double encoded: a literal whose content is itself a JSON document
            secret = floor_shape(which)
            # the KEY is encoded as well, or the raw keyed locator covers the planted extent without any
            # decoding and the case stops being about a decoding at all
            spelled = u_escape(secret, 1.0)
            inner = json.dumps({u_escape("password", 1.0): spelled}, ensure_ascii=False)
            text = json.dumps({"payload": inner}, ensure_ascii=False)
            cases.append(("double encoded", text, secret, emitted_in(text, spelled)))
            # 5. JSON in a string at depth two or more
            secret = floor_shape(which)
            spelled = u_escape(secret, 1.0)
            deep = json.dumps({"outer": json.dumps({"mid": json.dumps(
                {u_escape("api_key", 1.0): spelled}, ensure_ascii=False)}, ensure_ascii=False)},
                ensure_ascii=False)
            cases.append(("json in string at depth 2+", deep, secret, emitted_in(deep, spelled)))
            # 6. a quoted scalar that holds a structure - A#0's trace
            secret = floor_shape(which)
            cases.append(("quoted scalar holding a structure",
                          'prefix "password": "x{}' + secret + '"', secret, secret))
            # 7. a literal mask as a neighbour, in each position
            secret = floor_shape(which)
            cases.append(("literal mask before", f'{{"seen":"{FLOOR.PLACEHOLDER}"}} "token":"{secret}"',
                          secret, secret))
            secret = floor_shape(which)
            cases.append(("literal mask inside the value",
                          '"password": ' + json.dumps({"seen": FLOOR.PLACEHOLDER, "v": secret},
                                                      ensure_ascii=False), secret, secret))
            # 8. a floor claim spread across two members - no leaf holds it
            secret = floor_shape(which)
            cases.append(("cross-member claim",
                          '{"a":"' + floor_shape("sk") + ' api_key=","b":"' + secret + '"}', secret, secret))
            # 9. a secret in the prose before and after a structure
            secret = floor_shape(which)
            cases.append(("secret in the gap", f'token={secret} ' + '{"note":"plain"}', secret, secret))
            secret = floor_shape(which)
            cases.append(("secret in the tail", '{"note":"plain"} ' + f'token={secret}', secret, secret))
            # 10. an OPAQUE keyed value: nothing in the value's own characters says it is a credential, so
            # only the key that names it can mask it - and that key is written in escapes
            opaque = body(18, "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz")
            cases.append(("opaque value under an encoded key",
                          '{"note":"ordinary", "' + u_escape("password", 1.0) + '":"' + opaque + '"}',
                          opaque, opaque))
            # 11. a floor credential that only exists after a decoding - the floor cannot see the raw form
            secret = floor_shape(which)
            cases.append(("encoded floor credential", '{"note":"' + u_escape(secret, 1.0) + '"}',
                          secret, u_escape(secret, 1.0)))
            # 12. an encoded secret-named KEY, whose member has no locatable extent. The value is a floor
            # shape written in escapes, so neither the key nor the value is readable without decoding.
            secret = floor_shape(which)
            cases.append(("encoded secret-named key",
                          '{"note":"plain", "' + u_escape("password", 1.0) + '":"'
                          + u_escape(secret, 1.0) + '"}', secret, u_escape(secret, 1.0)))

    # Every class must have delivered the transformation it advertises - and what has to have changed is
    # not the same thing in each: the credential's own spelling in some, the container's in others, and in
    # one the KEY's. A blanket test called two classes inert that were doing exactly their job.
    def transformed(kind, text, secret, emitted):
        if kind == "escaped literal":
            return '\\"' in text          # the container is written in escapes
        if kind in ("u-escaped value", "slash-escaped path"):
            return emitted != secret and emitted in text
        if kind == "double encoded":
            return '\\"' in text and text.count('"') > 4   # a literal whose content is itself a document
        if kind in ("encoded secret-named key", "opaque value under an encoded key"):
            return '"password"' not in text and "password" not in text
        if kind == "encoded floor credential":
            return emitted != secret and not any(p.search(text) for p in floor_patterns())
        if kind == "json in string at depth 2+":
            return text.count("\\\\") > 0 or text.count('\\"') > 1
        return True
    needs_decoding = {"escaped literal", "u-escaped value", "slash-escaped path", "double encoded",
                      "json in string at depth 2+", "encoded secret-named key",
                      "opaque value under an encoded key", "encoded floor credential"}
    # The escaped-literal class plants a PLAIN credential inside an escaped container: its subject is the
    # container, and the floor can see the credential by design. Every other decoding class must hide its
    # credential from the raw detectors, or the case proves nothing about a decoding.
    hidden_from_raw = needs_decoding - {"escaped literal"}
    # the depth each class is about, declared rather than implied
    declared_depth = {"u-escaped value": 1, "slash-escaped path": 1, "encoded floor credential": 1,
                      "encoded secret-named key": 1, "opaque value under an encoded key": 1,
                      "double encoded": 2, "json in string at depth 2+": 2}
    per_class, reached = collections.Counter(), collections.Counter()
    inert, leaked, not_idempotent, raw_visible, unreachable = [], [], [], [], []

    def secret_key_visible(text, secret):
        """Whether a raw keyed rule already locates this credential - which means no decoding is needed."""
        return any(text[start:end] == secret for start, end, _replacement, _rank in keyed_spans(text))

    def depth_validation(text, subject, declared):
        """`(depth, complaint)` - the decoding depth at which the verifier first sights `subject`, and what
        is wrong with it against the depth this case DECLARES.

        One function for the generated cases and for the planted ones, so a case cannot be judged by a
        looser rule than the one the suite advertises. "At least one decoding" let a class claiming two
        layers pass on one."""
        depth = depth_of_first_sighting(text, subject)
        if depth is None:
            return None, f"no decoding reaches {subject[:12]!r}"
        if depth < declared:
            return depth, f"INSUFFICIENT_DEPTH actual={depth} declared={declared} subject={subject[:12]!r}"
        return depth, None

    def depth_of_first_sighting(text, secret):
        """The least decode depth at which the VERIFIER's own traversal sees the credential, or None.

        Depth 0 is the text as it stands. A class that advertises a decoding and is sighted at 0 is a case
        that proves nothing: the credential was readable without decoding anything."""
        for layers in range(VERIFY_DEPTH + 1):
            # the traversal starts at `VERIFY_DEPTH - layers`, so it has exactly `layers` left to spend
            forms = [form for form in every_spelling(text, VERIFY_DEPTH - layers)[0]
                     if isinstance(form, str)]
            if any(secret in form for form in forms):
                return layers
        return None
    for kind, text, secret, emitted in cases:
        per_class[kind] += 1
        if not transformed(kind, text, secret, emitted):
            inert.append((kind, text[:40]))
        # M#5: for a class that advertises a decoding, the RAW detectors must be blind to the planted
        # credential and the intended depth must expose it. Without both halves a case can pass by being
        # trivially visible, which is the opposite of what it claims to test.
        if kind in hidden_from_raw:
            # S#2: no raw detector may COVER THE PLANTED EXTENT - the characters the credential was actually
            # emitted as. Asking "does any detector match anywhere in the text" is a different question: a
            # case can carry an unrelated raw match and still be claiming a decoding it does not need, and a
            # case whose own extent IS covered raw proves nothing whatever else the text holds.
            at = text.find(emitted) if emitted else -1
            if at < 0:
                inert.append((kind, "the emitted spelling is not in the text: " + emitted[:20]))
            else:
                extent = (at, at + len(emitted))
                covering = [pattern.pattern[:18] for pattern in list(floor_patterns())
                            + list(home_patterns(owner))
                            for match in pattern.finditer(text)
                            if match.start() < extent[1] and match.end() > extent[0]]
                if covering:
                    raw_visible.append((kind, f"a raw detector covers the planted extent: {covering[:2]}"))
                if any(start < extent[1] and end > extent[0]
                       for start, end, _replacement, _rank in keyed_spans(text)):
                    raw_visible.append((kind, "the keyed locator covers the planted extent"))
            # What has to require a decoding is not the same thing in every class. Where the credential
            # itself is encoded, the credential must be sighted only below the surface. Where the value is
            # opaque and the KEY carries the secrecy, it is the key that must be.
            subject = "password" if kind == "opaque value under an encoded key" else secret
            depth, complaint = depth_validation(text, subject, declared_depth[kind])
            if complaint:
                unreachable.append((kind, complaint))

        out = project_text(text, owner)
        # judged by the shared predicate above, which the planted controls proved rejects both an
        # unredacted and a half-masked output
        if still_reads(secret, out, emitted):
            leaked.append((kind, secret[:14], out[:60]))
        if discloses(out, owner):
            leaked.append((kind, discloses(out, owner), out[:60]))
        reached[kind] += 1 if any(form != text for form in spellings_of(text)[1:]) else 0
        if project_text(out, owner) != out:
            not_idempotent.append((kind, out[:60]))
    for kind in ("escaped literal", "u-escaped value", "slash-escaped path", "double encoded",
                 "json in string at depth 2+", "quoted scalar holding a structure", "literal mask before",
                 "literal mask inside the value", "cross-member claim", "secret in the gap",
                 "secret in the tail", "encoded secret-named key", "opaque value under an encoded key",
                 "encoded floor credential"):
        if per_class[kind] < 4:
            failures.append(f"the class {kind!r} has {per_class[kind]} generated case(s), so it stands for "
                            "nothing")
        # ... and for the classes whose whole point is a decoding, the verifier's own decoder must really
        # have had something to decode: a class that advertises an encoding and hands the verifier a plain
        # string proves nothing about either of them.
        if kind in needs_decoding and reached[kind] < 1:
            failures.append(f"no case of the class {kind!r} reached the verifier's decoder with anything to "
                            "decode, so the class exercises nothing it advertises")
    if inert:
        failures.append(f"{len(inert)} case(s) advertise a transformation that changed nothing: {inert[:3]}")
    if raw_visible:
        failures.append(f"{len(raw_visible)} case(s) of a decoding class are already visible to the raw "
                        f"detectors, so they do not test a decoding: {raw_visible[:3]}")
    # ... and the assertion is proven on a deliberately SHALLOWER fixture: a case that declares two layers
    # and delivers one must be rejected, or the declaration is decoration
    # U#3: a case that needs ONE decoding while claiming two must be rejected by that same function
    shallow_secret = floor_shape("sk")
    shallow = json.dumps({"payload": json.dumps({"v": shallow_secret}, ensure_ascii=False)},
                         ensure_ascii=False)
    # this shape escapes only its container's quotes, so its credential stands in the raw text: depth 0.
    # Declaring one layer, or two, must be rejected; declaring none must not.
    # V#4: the violation is NAMED, and the name carries the actual depth and the declared one - a control
    # that only asks "was there a complaint" passes on a complaint about something else
    for declared in (1, 2):
        _depth, named = depth_validation(shallow, shallow_secret, declared)
        if named != f"INSUFFICIENT_DEPTH actual=0 declared={declared} subject={shallow_secret[:12]!r}":
            failures.append(f"the depth validation did not name its refusal of a case readable without any "
                            f"decoding while declaring {declared}: {named!r}")
    if depth_validation(shallow, shallow_secret, 0)[1]:
        failures.append("the depth validation rejects the same case against the depth it really has")
    # ... and a case that really is one layer down is accepted at one and rejected at two
    one_layer = '{"v":"' + "".join(f"\\u{ord(ch):04x}" for ch in shallow_secret) + '"}'
    # X#5: the WHOLE returned tuple in both directions - the depth as well as the verdict, so a function
    # that reported the right complaint about the wrong depth would fail here
    accepted = depth_validation(one_layer, shallow_secret, 1)
    if accepted != (1, None):
        failures.append(f"the depth validation did not accept a one-decoding case declaring one as "
                        f"(1, None): {accepted!r}")
    refused = depth_validation(one_layer, shallow_secret, 2)
    if refused != (1, f"INSUFFICIENT_DEPTH actual=1 declared=2 subject={shallow_secret[:12]!r}"):
        failures.append(f"a one-decoding case declaring two was not refused by name: {refused!r}")
    if unreachable:
        failures.append(f"{len(unreachable)} case(s) of a decoding class hide their credential from the "
                        f"verifier's own traversal, so nothing proves the depth is reached: {unreachable[:3]}")
    if leaked:
        failures.append(f"{len(leaked)} generated case(s) leave a credential readable in some decoding of the "
                        f"output, first: {leaked[:2]}")
    if not_idempotent:
        failures.append(f"{len(not_idempotent)} generated case(s) are not idempotent, first: {not_idempotent[:2]}")
    # ... and the oracle itself rejects a deliberately partial mask, or every count above means nothing
    partial_secret = floor_shape("sk")
    half_masked = f'{{"note":"{FLOOR.PLACEHOLDER}{partial_secret[10:]}"}}'
    if not any(partial_secret[10:] in form for form in spellings(half_masked)):
        failures.append("the leak oracle does not see a credential whose first half alone was masked")
    generated = len(cases)
    class_counts = dict(sorted(per_class.items()))

    # The differential the lead's direction names: over every fixture string of this self-test, whatever the
    # unchanged floor would mask, the projection masks at least as much. Positive control first - the corpus
    # is non-empty and its own secret cases are asserted above - and the subject set is counted, because an
    # empty corpus satisfies this and every other "never less" claim.
    corpus = ([text if isinstance(text, str) else serialise(text) for _label, text, _planted in secrets + structured]
              + [text for _label, text, _planted in paths]
              + [text for _label, text in kept]
              + [value if isinstance(value, str) else serialise(value)
                 for _label, value, _want in structured_kept]
              + ["Authorization: Bearer\nopaque0123456789abcdef", "ask alice.dev@example.com",
                 "api_key=live_0123456789abcdef and sk-" + "a" * 20, "nothing to see here"])
    if len(corpus) < 40:
        failures.append(f"the differential corpus is {len(corpus)} strings, too few to be the subject of this claim")
    leftover = {text: floor_leftovers(text, owner) for text in corpus if floor_leftovers(text, owner)}
    if leftover:
        failures.append(f"the floor masks something the projection does not, which is the one direction this "
                        f"module may not take: {sorted(leftover)[:3]}")
    # ... and the projection masks MORE than the floor somewhere in the corpus, or it is not a projection
    if not any(project_text(text, owner) != FLOOR.redact(text) for text in corpus):
        failures.append("the projection masks exactly what the floor masks everywhere, so the corpus cannot "
                        "show the difference this module exists to make")

    # The sweep, over a fixture run directory: it must find a member the projection would have masked, must
    # not count one already masked, and must read the index only for its shape. Positive control first, so a
    # green sweep cannot be a sweep that scanned nothing.
    with tempfile.TemporaryDirectory() as tmp:
        run = pathlib.Path(tmp)
        (run / "redacted").mkdir()
        (run / "index" / "bm25").mkdir(parents=True)
        planted = 'tail\\", \\"client_secret\\": \\"sweepplanted\\", \\"next\\": 1'
        line = {"line": 1, "ts": "2026-10-15T00:00:00Z",
                "items": [{"pointer": "/a", "kind": "tool_result", "tool": "Bash", "error": False, "text": planted}]}
        (run / "redacted" / "x.r2.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
        (run / "index" / "bm25" / "t.json").write_text(json.dumps(
            {"version_sha": "x", "redaction_version": CURRENT, "docs": [], "postings": {"token": [1, 2]}}), encoding="utf-8")
        residual, masked, by_key, bad_index, index_files = sweep(run)
        if residual != 1 or by_key != collections.Counter({"client_secret": 1}):   # the whole key, not just `secret`
            failures.append(f"the sweep did not find the planted residual member: {residual}, {dict(by_key)}")
        if bad_index or index_files != 1:
            failures.append(f"the sweep misread a well-formed index: {bad_index} bad of {index_files}")
        # the same line as the projection writes it: nothing residual, and the placeholder is counted
        line["items"][0]["text"] = project(planted, home=owner)
        (run / "redacted" / "x.r2.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
        residual, masked, _by_key, _bad, _files = sweep(run)
        if residual:
            failures.append(f"the sweep called the projection's own output residual: {residual}")
        if not masked:
            failures.append("the sweep counted no placeholder in projected text, so it scanned nothing")
        # M#4: a window file is a pretty-printed document, not one record per line, and reading it line by
        # line skipped every window in the run while printing a clean result
        (run / "views" / "s1").mkdir(parents=True)
        window = {"records": [{"text": 'tail\\", \\"client_secret\\": \\"windowplanted\\"'}]}
        (run / "views" / "s1" / "1.json").write_text(json.dumps(window, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            residual, _masked, by_key, _bad, _files = sweep(run)
            if residual != 1 or by_key != collections.Counter({"client_secret": 1}):
                failures.append(f"the sweep did not read a pretty-printed window: {residual}, {dict(by_key)}")
        except Unswept as exc:
            failures.append(f"the sweep could not read a pretty-printed window at all: {exc}")
        # ... and every quoting the masker can write is recognised as masked, including a repr's
        for spelling in ('"password": "{}"', "'password': '{}'", 'password": \\"{}\\"', "password = {}"):
            projected = project(spelling.format("quoteplanted"), home=owner)
            if residual_in(projected):
                failures.append(f"the sweep called its own masker's output residual: {spelling}")
        # an index whose postings are not document numbers is the one index shape the sweep does judge
        (run / "views" / "s1" / "1.json").unlink()
        (run / "index" / "bm25" / "t.json").write_text(json.dumps(
            {"version_sha": "x", "redaction_version": CURRENT, "docs": [], "postings": {"token": "a secret"}}),
            encoding="utf-8")
        if sweep(run)[3] != 1:
            failures.append("the sweep accepted an index posting that is not a list of document numbers")
        # M#4: a subject it cannot read, and no subject at all, are refusals - not a clean sweep
        (run / "redacted" / "broken.jsonl").write_text("{not json\n", encoding="utf-8")
        try:
            sweep(run)
            failures.append("the sweep skipped a record it could not read instead of refusing")
        except Unswept as exc:
            if "UNSWEPT_RECORD" not in str(exc):
                failures.append(f"an unreadable record was refused unnamed: {exc}")
        (run / "redacted" / "broken.jsonl").unlink()
        (run / "views" / "s1" / "sequence.json").write_text("{not json", encoding="utf-8")
        try:
            sweep(run)
            failures.append("the sweep skipped a document it could not read instead of refusing")
        except Unswept as exc:
            if "UNSWEPT_DOCUMENT" not in str(exc):
                failures.append(f"an unreadable document was refused unnamed: {exc}")
    with tempfile.TemporaryDirectory() as empty:
        try:
            sweep(empty)
            failures.append("the sweep judged a run directory with no subject and called it clean")
        except Unswept as exc:
            if "UNSWEPT_EMPTY" not in str(exc):
                failures.append(f"an empty subject set was refused unnamed: {exc}")
        with contextlib.redirect_stdout(io.StringIO()):   # its refusal is the subject here, not its printing
            refused = report_sweep(empty)
        if refused == 0:
            failures.append("the sweep reported success over no subject at all")
    for failure in failures:
        print(f"projection --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"projection --self-test: OK ({len(secrets)} secret shapes and {len(paths)} home-path shapes masked and "
          f"idempotent, {len(structured)} structured and JSON-keyed shapes masked (keyed secrets, nested, in a list, "
          f"a non-string value, a Windows path through a tool argument and through escaped text), "
          f"{len(kept) + len(structured_kept)} look-alikes untouched, three escape sequences read as boundaries, the "
          f"owner's own home masked through prose, a relative prefix and a diff prefix, its longer-name look-alike "
          f"kept, the floor's key names read from the floor and an unreadable floor named, a block's characters, "
          f"versions, ONE monotone masking pass in the original text's own coordinates ({generated} seeded "
          f"cases over fourteen classes, each asserted to have made the transformation it advertises and judged "
          f"by decoding the output independently at every depth: {class_counts}), the oracle "
          f"proven on deliberately partial masks and carrying a positive case for every floor pattern, the "
          f"differential over the whole fixture corpus (whatever the unchanged floor masks, the "
          f"projection masks at least as much, and somewhere it masks more), and the sweep over a fixture run directory - a planted member found in a record and in a "
          f"pretty-printed window, every quoting its masker writes recognised, an index judged only for its "
          f"shape, and an unreadable record, an unreadable document and an empty subject set each refused)")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    if len(sys.argv) == 3 and sys.argv[1] == "--sweep":
        sys.exit(report_sweep(sys.argv[2]))
    sys.exit("usage: projection.py --self-test | --sweep <run-dir>")
