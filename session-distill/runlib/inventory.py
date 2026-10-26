#!/usr/bin/env python3
"""S2's inventory (design §6.1): the effective library split into numbered units, per layer, per
reference point.

  distill.py inventory --run-id ID [--pin HOST:SESSION] [--native-live] [--to DIR]
  inventory.py --self-test

Every layer of design §6.1 has a **named producer** and a status in `layers[]`; a layer is never
silently empty. `complete` means every carrier of that layer split and reproduced byte for byte;
`unsupported` means a carrier's structure is one the splitter cannot divide; `incomplete` means the
producer ran and something it needed was missing, unreadable, or yielded nothing; `unknown` means
no record of that layer exists at this reference point (a historical overlay, a native home nobody
captured, a selection with no pin). Anything but `complete` makes the reference point incomplete,
with the reason named — which is what every later absence claim rests on, because "the release does
not hold it" is only sayable where the release is complete (§6.3's `not_delivered` against
`unknown`).

Reference points: *current* (every layer now), *release* (the installed or pinned baseline's
inventory), *selection* (a pin's snapshot items and the instruction text it compiled).

A unit is `{unit_id, layer, path, heading, n, text, sha, class}` as §6.1, plus `operative_context`
and `version_sha256` as the plan asks. `sha` is the fragment hash: the same fragment in the same
carrier at two reference points yields the same `unit_id` and the same `sha`, and only its
`operative_context` and `version_sha256` differ, which is what lets WP-10 bind a returned fragment
to a version. `renames[]` carries the units whose fragment moved carrier since *release*.

**The owner's state is read through frozen copies** (done-when 5). `InstructionsStore`'s public
methods take the transaction lock and recover pending transactions — they write — so the overlay and
snapshot producers copy the few files they read and resolve over the copies with the store's own
non-locking internals. Nothing under the owner's state root is created, locked or changed.

Ports `reconstruction/scripts/inventory.py` (the 1,938 units / 1,553 operative measurement of
2026-10-20). Design: §6.1, §6.3, §6.4 inputs, §8.6.
"""
import sys

# Before this module's own graph is imported: `runlib.projection` loads `learn/redact.py` by path
# at import time, and a cache write lands beside the file it caches (GB#7). The driver sets the
# same flag before it imports anything; this covers the module run on its own.
sys.dont_write_bytecode = True

import ast
import collections
import datetime
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

try:
    import tomllib  # the settings reader for a Codex config.toml (3.11+)
except ModuleNotFoundError:  # pragma: no cover - the pinned interpreter has it
    tomllib = None

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# The bootstrap, and the only thing in this file that runs before the boundary exists. It is
# stdlib only and its line carries NO path, because what failed is the very code that would have
# projected one: `from runlib import entry` stood outside every boundary this command has, so an
# `entry` that cannot import left a traceback on stderr with the importer's absolute paths in it
# (r3 #2). `BaseException`, because a module can exit during import; a `SystemExit` already carries
# the code its raiser chose, so it is re-raised rather than relabelled.
STARTUP_UNAVAILABLE = ("COMMAND_FAILED startup: session distill could not load the boundary that "
                       "describes its own failures, so it says nothing further about this one")
STARTUP_UNAVAILABLE_CODE = 3

# The boundary first, and the rest of the graph inside it. This module is an entry point of its
# own (`python3 runlib/inventory.py --self-test`), and `runlib.validate` exits during import when
# its schema pin is unreadable — so the import that can fail must sit inside the thing that
# describes the failure. `runlib.entry` imports nothing but the standard library and reaches the
# floor lazily, which is what makes it safe to import first (R2#3); the bootstrap above is what
# answers when that import fails regardless (r3 #2).
try:
    from runlib import entry
except SystemExit:
    raise
except BaseException:
    # Imported as a module, the caller owns the failure and gets the exception. Run as a command,
    # there is nothing left to describe it with, so the fixed line stands in for the whole floor.
    if __name__ != "__main__":
        raise
    sys.stderr.write(STARTUP_UNAVAILABLE + "\n")
    raise SystemExit(STARTUP_UNAVAILABLE_CODE)

try:
    from runlib import projection, records, sources, validate
    from runlib.records import Refused
except BaseException as _startup_exc:   # SystemExit included: `validate` exits at import time
    if __name__ == "__main__":
        sys.exit(entry.failed(_startup_exc, str(pathlib.Path.home()), label="STARTUP_FAILED", code=2))
    raise

# Every line this module's own entry point publishes — its self-test's report most of all, because
# a failure line is exactly where a planted credential or a fixture path would leave — goes through
# the one boundary. Bound here rather than inside the suite: `entry` is an ordinary local name in
# there (a census entry, a declaration entry), and the alias has to be the module (R2#3).
report = entry.say
# Same reason for the boundary and the child bound: `entry` is an ordinary local name inside the
# suite (a census entry, a declaration entry), so the module is aliased out here.
guarded_entry = entry.guarded
bounded_child = entry.bounded

HERE = pathlib.Path(__file__).resolve().parents[1]  # session-distill/
REPO = HERE.parent
# Provenance only: it is recorded in `produced_by` so a reader can find the design this was derived
# from. Nothing executable reads it — the contract lives in `SCHEMA_REL`, which is a file the code
# owns and does not expire (the 1548 amendment §10).
DESIGN = "design/session-distill/2026-10-20T1942--9684f05--mechanism-design.md"
LEDGER_REL = "design/session-distill/ledger.json"
REFERENCES = ("current", "release", "selection")
STATUSES = ("complete", "incomplete", "unsupported", "unknown")

# §6.1's unit record, with the two fields the plan adds and the one the emission adds. `class`
# carries §6.1's `operative|reference`; `contract_problems` holds this tuple against the schema.
UNIT_FIELDS = ("unit_id", "layer", "path", "heading", "n", "text", "sha", "class",
               "operative_context", "version_sha256", "redaction_version")
PLAN_FIELDS = ("operative_context", "version_sha256")
# The emitted strings that are SPANS of the carrier, and the ones that are metadata about it. The
# first kind goes through `_carrier_span` (the whole-carrier decision and the carrier's credential
# context); the second passes the floor on its own. `shed` is the only reader, and no control reads
# either tuple — the differential enumerates what the row actually carries (R2#0).
SPAN_FIELDS = ("text", "heading")
METADATA_TEXT_FIELDS = ("path", "item_ref", "package_id")
# What the emission adds to §6.1's record, and why: `text` is the projection of the fragment, not the
# fragment, so the version of the floor that made it has to travel with it (design §5.4).
EMISSION_FIELDS = ("redaction_version",)
# Where a carrier came from, when the layer's own answer needs it: the hosts an overlay resolved
# for, and the units a ledger keep record protects (GA#7, GA#9).
PROVENANCE_FIELDS = ("provenance",)

# What a heading marks as not itself a requirement (the port's list).
REFERENCE_HEADING = re.compile(
    r"(?i)\b(evidence|rationale|history|sources?|background|changelog|references?|derivation|why this|provenance)\b")
# A carrier named inside a unit's text, with the heading it names when it names one.
MENTION = re.compile(r"(?P<path>[\w./-]+\.(?:md|py|sh|toml|json|js))(?:\s*(?:§|#)\s*(?P<heading>[^\n,.;)]{1,80}))?")
NATIVE = {
    "claude": {"home": "~/.claude", "global": ("CLAUDE.md",), "settings": ("settings.json",),
               "memory": ("projects/*/memory/*.md",)},
    "codex": {"home": "~/.codex", "global": ("AGENTS.md",), "settings": ("config.toml",), "memory": ()},
}
PROJECT_FILES = ("CLAUDE.md", "AGENTS.md")
MEMBER_BASE = {"guide": "claude/guides", "hook": "claude/hooks", "agent": "claude/agents", "skill": "claude/skills"}


# The child this module's self-test runs to answer, behaviourally, whether the command's own module
# graph writes a `.pyc` (GB#7, GC#10). It is passed to `python -c`: a question only a real process
# answers, and a script file would be a program the dispatch trace cannot follow.
#
# It runs the driver the way production does — as `__main__`, through `runpy.run_path` — because
# that is the only shape a real invocation has. Importing it as a module was the control's own
# probe, and the one shape that caches the driver: the probe produced the single
# `session-distill/__pycache__/distill.*.pyc` ever seen here and then called it a finding (GC#10).
#
# `checkout` is the copy of the checkout this run is confined to looking at. Every attempted
# MUTATION under it is reported, and the bytecode ones separately: the claim is about THAT tree,
# which is also the tree the caller compares before and after.
#
# A write-mode `open` is one way to change a tree and not the only one. The first version returned
# immediately for every event that was not `open`, so a fixture `os.mkdir`, `os.remove` and
# `os.rename` under the copy were each observed as nothing while the claim read "no write at all
# anywhere under the checkout" (R1#4). The operations are a DATA list: a kind this does not name
# cannot be excused by prose, and the after-run comparison of the whole tree is the backstop for one
# that is missing — a directory created or a file renamed changes the tree whether or not an event
# for it was recognised.
#
# Audit hooks fire BEFORE the operation, so an attempt that then fails is still observed. That is
# what makes "attempted write" the right question: a run that tried and was refused by the operating
# system has still tried.
#
# Paths are resolved AT EVENT TIME. Resolving later answers about a tree that has moved on, and the
# process's working directory is the copy's neighbour, so a relative argument has to be resolved
# while it still means what it meant.
BYTECODE_PROBE = """
import json, os, runpy, sys

# event name -> (which positional arguments are paths, which argument holds the dir_fd for each).
# Every entry is one filesystem mutation the interpreter audits. `open` is handled separately,
# because only some modes and flags mutate. A `-1` means that path has no dir_fd argument.
#
# The layouts are CPython's audit-event arguments. An event this table does not know, or an argument
# missing from one it does, is UNVERIFIED rather than ignored: the claim this probe exists for is
# "no attempted write under the copy", and an event nobody could attribute is not evidence of that.
MUTATIONS = {
    'os.mkdir': ((0,), (2,)), 'os.rmdir': ((0,), (1,)), 'os.remove': ((0,), (1,)),
    'os.unlink': ((0,), (1,)),
    'os.rename': ((0, 1), (2, 3)), 'os.replace': ((0, 1), (2, 3)), 'os.link': ((0, 1), (2, 3)),
    'os.symlink': ((0, 1), (-1, 2)),
    'os.truncate': ((0,), (-1,)), 'os.chmod': ((0,), (2,)), 'os.chown': ((0,), (3,)),
    'os.utime': ((0,), (3,)),
    'os.makedirs': ((0,), (-1,)), 'os.removedirs': ((0,), (-1,)), 'os.mknod': ((0,), (2,)),
    'os.mkfifo': ((0,), (2,)),
    'os.setxattr': ((0,), (-1,)), 'os.removexattr': ((0,), (-1,)),
    'shutil.copyfile': ((0, 1), (-1, -1)), 'shutil.copymode': ((0, 1), (-1, -1)),
    'shutil.copystat': ((0, 1), (-1, -1)), 'shutil.copytree': ((0, 1), (-1, -1)),
    'shutil.move': ((0, 1), (-1, -1)), 'shutil.rmtree': ((0,), (1,)),
    'shutil.unpack_archive': ((0, 1), (-1, -1)), 'shutil.make_archive': ((0,), (-1,)),
    'pathlib.Path.mkdir': ((0,), (-1,)), 'pathlib.Path.rename': ((0, 1), (-1, -1)),
    'pathlib.Path.replace': ((0, 1), (-1, -1)),
    'pathlib.Path.unlink': ((0,), (-1,)), 'pathlib.Path.rmdir': ((0,), (-1,)),
    'pathlib.Path.touch': ((0,), (-1,)),
    'pathlib.Path.symlink_to': ((0, 1), (-1, -1)), 'pathlib.Path.hardlink_to': ((0, 1), (-1, -1)),
    'pathlib.Path.chmod': ((0,), (-1,)), 'tempfile.mkstemp': ((0,), (-1,)),
    'tempfile.mkdtemp': ((0,), (-1,)),
}
F_GETPATH = 50          # darwin; elsewhere /proc/self/fd answers
seen = []               # (event, resolved path)
unverified = []         # (event, why) — a mutation nobody could attribute to a tree


def fd_path(fd):
    '''The path a descriptor is open on: F_GETPATH where the platform has it, /proc/self/fd where it
    does not. `fcntl.fcntl` RETURNS the result buffer rather than filling the one it is given.'''
    try:
        import fcntl
        answer = fcntl.fcntl(fd, F_GETPATH, b'\\0' * 1024)
        return os.fsdecode(bytes(answer).split(b'\\0', 1)[0]) or None
    except Exception:
        try:
            return os.readlink('/proc/self/fd/%d' % fd)
        except OSError:
            return None


def resolve(value, dir_fd=None):
    \'\'\'(resolved path, why it could not be resolved). Fail closed: a descriptor-only operation and a
    descriptor-relative one are resolved through the descriptor, and anything left over is named.\'\'\'
    if isinstance(value, int):
        base = fd_path(value)
        return (os.path.realpath(base), None) if base else (None, 'descriptor-only')
    try:
        text = os.fsdecode(value)
    except (TypeError, ValueError):
        return None, 'not-a-path'
    if dir_fd is not None and not isinstance(dir_fd, int):
        dir_fd = None
    if dir_fd is not None and dir_fd >= 0 and not os.path.isabs(text):
        base = fd_path(dir_fd)
        if base is None:
            return None, 'descriptor-relative'
        return os.path.realpath(os.path.join(base, text)), None
    return os.path.realpath(text), None


def record(event, value, dir_fd=None):
    resolved, why = resolve(value, dir_fd)
    if resolved is None:
        unverified.append((event, why))
        return
    seen.append((event, resolved))


def hook(event, args):
    if event == 'open':
        if not args:
            unverified.append((event, 'no-arguments'))
            return
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        # A .pyc is written through os.open, whose audit args carry no mode string at all: a
        # mode-only test observed nothing and called it proof. O_TRUNC truncates a file that the
        # process may have opened read-write without O_CREAT, so it counts too.
        writes = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
        writing = (isinstance(mode, str) and any(f in mode for f in 'wax+')) or bool(flags & writes)
        if writing:
            record('open(write)', args[0])
        return
    layout = MUTATIONS.get(event)
    if layout is None:
        return
    positions, fds = layout
    for index, position in enumerate(positions):
        if position >= len(args):
            unverified.append((event, 'argument-%d-absent' % position))
            continue
        at = fds[index] if index < len(fds) else -1
        dir_fd = args[at] if 0 <= at < len(args) else None
        record(event, args[position], dir_fd)


checkout, destination, which, driver = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
root = os.path.realpath(checkout)
sys.addaudithook(hook)
code = 0
if which == 'unguarded':
    import importlib.util
    sys.dont_write_bytecode = False
    spec = importlib.util.spec_from_file_location('probe_floor', driver)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
elif which == 'mutations':
    # The positive controls for the kinds that are not an open. Each one is under the copy, and the
    # three that FAIL are given paths nothing else here touches, so the control can assert them by
    # (event, path) identity rather than by a count that successful events already satisfy.
    probe_dir = os.path.join(root, 'session-distill', 'probe-mutations')
    os.mkdir(probe_dir)
    made = os.path.join(probe_dir, 'made.txt')
    with open(made, 'w') as handle:
        handle.write('x')
    renamed = os.path.join(probe_dir, 'renamed.txt')
    os.rename(made, renamed)
    # A descriptor-relative creation and a descriptor-only truncation: the shapes the old observer
    # resolved against the working directory, or discarded as a non-path.
    folder = os.open(probe_dir, os.O_RDONLY)
    try:
        os.mkdir('relative-to-a-descriptor', dir_fd=folder)
        os.rmdir('relative-to-a-descriptor', dir_fd=folder)
    finally:
        os.close(folder)
    handle = os.open(renamed, os.O_RDWR)
    try:
        os.truncate(handle, 0)
    finally:
        os.close(handle)
    # An open whose ONLY write flag is O_TRUNC: it carries no mode string and no O_WRONLY, and it
    # destroys the file's contents. The file is put there by a rename so that this open is the only
    # event about it, and the row it produces is the one the O_TRUNC classification answers for.
    truncated = os.path.join(probe_dir, 'truncated.txt')
    os.rename(renamed, truncated)
    try:
        os.close(os.open(truncated, os.O_RDONLY | os.O_TRUNC))
    except OSError:
        pass
    os.remove(truncated)
    for attempt in ('mkdir', 'remove', 'rename'):
        try:
            if attempt == 'mkdir':
                os.mkdir(probe_dir)                                   # already there: fails
            elif attempt == 'remove':
                os.remove(os.path.join(root, 'a-file-that-is-not-here'))   # absent: fails
            else:
                os.rename(os.path.join(root, 'also-not-here'),
                          os.path.join(probe_dir, 'nowhere.txt'))     # source absent: fails
        except OSError:
            pass
    os.rmdir(probe_dir)
else:
    sys.argv = [driver, 'inventory', '--to', destination, '--no-state']
    try:
        runpy.run_path(driver, run_name='__main__')
    except SystemExit as exit:
        code = exit.code if isinstance(exit.code, int) else 1
under = sorted({'%s %s' % (event, path) for event, path in seen if path.startswith(root)})
kinds = sorted({event for event, path in seen if path.startswith(root)})
print(json.dumps({'code': code, 'under_checkout': under[:16], 'under_checkout_total': len(under),
                  'kinds': kinds,
                  'unverified': sorted({'%s %s' % row for row in unverified})[:8],
                  'unverified_total': len(unverified),
                  'bytecode': sorted({row for row in under
                                      if row.endswith('.pyc') or '__pycache__' in row})[:8]}))

"""


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def projected(text, home=None):
    """The characters of a fragment as every model-facing artifact carries them: the one floor of
    `runlib/projection.py` over `learn/redact.py`, versioned like the views' own projection.

    A unit's hashes are taken over the RAW fragment and its raw carrier, before this runs, so a
    returned fragment still binds to its source version (§6.3); the raw bytes themselves stay in the
    run's frozen copy, which is discarded, and never reach an artifact. A settings file is covered by
    the same floor rather than by a rule of its own: the floor reads a credential-named member of a
    structure wherever it stands, which is what keeps keys and structure and drops the value."""
    out = projection.project(text, projection.CURRENT, home)
    disclosed = projection.discloses(out, home)
    if disclosed is not None:
        raise Refused(f"DISCLOSED_IN_UNIT: the projection left {disclosed} in a unit's text; no artifact is written")
    return out


def disclosure_problems(document, home=None, at="$"):
    """What a written document still discloses, as this module's refusal names it.

    The question belongs to the floor and is asked through its one entry point
    (`projection.document_disclosures`): it owns the rules, takes the document in either decoded
    representation, and converts internally. Choosing a floor helper per value is what this used to
    do, and it got one wrong in each direction — `all_mask` reads an object as `Members` and calls a
    plain `dict` unmasked whatever it holds, while `holds_secret` reads plain objects and misses a
    credential-named member inside `Members`. The code here is the refusal, not the rule.

    `DOCUMENT_KEYS` is what this module contributes: the member names its own documents carry, so a
    refusal names a member of a schema this code owns and reports every other key — a key a document
    happens to hold — by its ordinal (GC#5)."""
    return [f"DISCLOSED_IN_ARTIFACT {row}" for row in
            projection.document_disclosures(document, home, at, schema=DOCUMENT_KEYS)]


def write_document(out_dir, path, document, home=None):
    """Write one artifact, after the whole document has been asked what it still discloses.

    The document is judged as the DECODED object it is, member by member and value by value, which
    is the representation the floor's structural predicates are written for (GC#5). The serialized
    form is not asked the same question: `discloses` reads one projected block, and a whole JSON
    document reads as a keyed fragment to it — a check that fires on `"sha": "..."` would be routed
    around within a day, and `holds_secret` already answers about the structure."""
    problems = disclosure_problems(document, home)
    if problems:
        raise Refused(f"{'; '.join(problems[:4])}"
                      + (f" (+{len(problems) - 4} more)" if len(problems) > 4 else "")
                      + "; no artifact is written")
    records.write_json(out_dir, path, document)


def stage_record_problems(run_dir, stage="S2", home=None):
    """What a stage record this run wrote still discloses.

    Its fields are machinery — digests, timestamps, the artifact names this module passes in — so
    this is a post-condition rather than a filter: nothing here is owner text today, and a field
    added later that is cannot pass unnoticed (GB#5)."""
    path = pathlib.Path(run_dir) / "stages" / stage / "record.json"
    if not path.is_file():
        return []
    return disclosure_problems(json.loads(path.read_text(encoding="utf-8")), home)


def projected_message(exc, home=None):
    """An exception as an artifact may carry it: its type, and its message through the floor. An
    OSError's message is a path, and a path is the owner's home more often than not."""
    return f"{type(exc).__name__}: {projection.project(str(exc), projection.CURRENT, home)}"


def masked(value, home=None):
    """A path as an artifact or a refusal carries it: the projection's own home mask, not a second
    spelling. The owner's home is the default, so a caller that passes none still masks."""
    return projection.project(str(value), projection.CURRENT, home or str(pathlib.Path.home()))


# ---------------------------------------------------------------- the splitter (ported)

def md_blocks(text):
    """`(kind, text)` blocks of a markdown carrier; the concatenation is the carrier."""
    lines = text.splitlines(keepends=True)
    i, n, blocks = 0, len(lines), []
    if lines and lines[0].rstrip("\r\n") == "---":
        j = 1
        while j < n and lines[j].rstrip("\r\n") != "---":
            j += 1
        j = min(j + 1, n)
        blocks.append(["frontmatter", "".join(lines[:j])])
        i = j
    while i < n:
        line = lines[i]
        s = line.rstrip("\r\n")
        if not s.strip():
            if blocks:
                blocks[-1][1] += line
            else:
                blocks.append(["blank", line])
            i += 1
            continue
        if s.startswith("```") or s.startswith("~~~"):
            fence = s[:3]
            j = i + 1
            while j < n and not lines[j].lstrip().startswith(fence):
                j += 1
            j = min(j + 1, n)
            blocks.append(["code", "".join(lines[i:j])])
            i = j
            continue
        if re.match(r"#{1,6} ", s):
            blocks.append(["heading", line])
            i += 1
            continue
        if s.lstrip().startswith("|"):
            j = i
            while j < n and lines[j].strip().startswith("|"):
                j += 1
            rows = lines[i:j]
            head = 2 if len(rows) >= 2 and re.match(r"^\s*\|[\s:|-]+\|\s*$", rows[1]) else 0
            if head:
                blocks.append(["table-head", "".join(rows[:2])])
            for row in rows[head:]:
                blocks.append(["table-row", row])
            i = j
            continue
        if re.match(r"(\s*)([-*+]|\d+[.)])\s", s):
            base = len(s) - len(s.lstrip())
            j = i + 1
            while j < n:
                t = lines[j].rstrip("\r\n")
                if not t.strip():
                    break
                indent = len(t) - len(t.lstrip())
                if indent <= base and re.match(r"\s*([-*+]|\d+[.)])\s", t):
                    break
                if indent <= base and (re.match(r"#{1,6} ", t) or t.lstrip().startswith(("|", "```"))):
                    break
                j += 1
            blocks.append(["list-item", "".join(lines[i:j])])
            i = j
            continue
        j = i + 1
        while j < n:
            t = lines[j].rstrip("\r\n")
            if not t.strip() or re.match(r"#{1,6} ", t) or t.startswith(("```", "~~~")) or t.lstrip().startswith("|") \
                    or re.match(r"\s*([-*+]|\d+[.)])\s", t):
                break
            j += 1
        blocks.append(["paragraph", "".join(lines[i:j])])
        i = j
    return blocks


def py_blocks(text):
    """Top-level statements; a leading comment belongs to the statement it introduces, and a list
    literal of more than three elements splits per element."""
    lines = text.splitlines(keepends=True)
    module = ast.parse(text)
    cuts = []
    for node in module.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List) and len(node.value.elts) > 3:
            cuts.append((node.lineno - 1, "assign-open"))
            for element in node.value.elts:
                cuts.append((element.lineno - 1, "list-element"))
            cuts.append((node.value.end_lineno - 1, "assign-close"))
        else:
            kind = "docstring" if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant) \
                and isinstance(node.value.value, str) else type(node).__name__
            cuts.append((node.lineno - 1, kind))
    adjusted, previous_end = [], 0
    for k, (start, kind) in enumerate(cuts):
        s = start
        while s - 1 >= previous_end and (lines[s - 1].strip().startswith("#") or not lines[s - 1].strip()) \
                and kind != "assign-close":
            s -= 1
        if k == 0:
            s = 0
        adjusted.append((max(s, previous_end), kind))
        previous_end = max(s, previous_end) + 1
    blocks = []
    for k, (start, kind) in enumerate(adjusted):
        end = adjusted[k + 1][0] if k + 1 < len(adjusted) else len(lines)
        blocks.append([kind, "".join(lines[start:end])])
    return [block for block in blocks if block[1]]


def plain_blocks(text):
    """Blank-line separated blocks of a carrier with no structure the splitter knows."""
    blocks, current = [], ""
    for line in text.splitlines(keepends=True):
        if not line.strip() and current:
            blocks.append(["code-block", current + line])
            current = ""
        elif current == "" and blocks and not line.strip():
            blocks[-1][1] += line
        else:
            current += line
    if current:
        blocks.append(["code-block", current])
    return blocks


class Unacquired(Exception):
    """An input this reference point needs and this run has no record of: the layer is `unknown`,
    which is neither "the producer looked and found nothing" nor "this structure is unsupported".
    A run's native layers are unacquired until the S0 capture package lands (2026-10-23)."""


class Unsupported(Exception):
    """A carrier whose structure this producer cannot divide at all: the layer is `unsupported`,
    and what is missing is a splitter, not a correct file."""


class Malformed(Exception):
    """A carrier of a structure the producer does support, which this one instance of is broken: the
    layer is `incomplete` and the reason names the carrier. The two are not the same answer — one
    says the inventory cannot read this kind of file, the other that this file is wrong."""


def structured(path, text, form):
    """A supported structured carrier, parsed to prove it is well formed. A settings file is the
    carrier kind whose breakage the splitter cannot see: `plain_blocks` divides any text at all, so
    a settings file with a missing brace split clean and the layer reported complete (GA#5)."""
    if form == "json":
        try:
            json.loads(text)
        except ValueError as exc:
            raise Malformed(f"{path}: not valid JSON: {exc}") from exc
    elif form == "toml":
        if tomllib is None:
            raise Unsupported(f"{path}: this interpreter has no TOML reader, so a settings file of this kind "
                              f"cannot be proved well formed")
        try:
            tomllib.loads(text)
        except Exception as exc:  # tomllib raises its own decode error type
            raise Malformed(f"{path}: not valid TOML: {exc}") from exc


def blocks_of(path, text, form=None):
    """The blocks of one carrier, by its declared form. The concatenation has to reproduce the
    carrier byte for byte, or the structure is one this producer does not support."""
    if not text:
        return []
    form = form or form_of(path)
    structured(path, text, form)
    try:
        if form == "markdown":
            blocks = md_blocks(text)
        elif form == "python":
            blocks = py_blocks(text)
        else:
            blocks = plain_blocks(text)
    except (SyntaxError, ValueError, RecursionError) as exc:
        # Python and markdown are forms this splitter supports, so a carrier of one that does not
        # parse is a malformed carrier of a supported form, never an unsupported structure (GB#12).
        raise Malformed(f"{path}: {type(exc).__name__}: {exc}") from exc
    if "".join(block[1] for block in blocks) != text:
        raise Unsupported(f"{path}: the split does not reproduce the carrier")
    return blocks


def classify(kind, heading_path):
    """Whether a unit is a requirement or the reference around one (§6.1's `operative|reference`)."""
    if kind in ("heading", "table-head", "blank", "docstring"):
        return "reference"
    if any(REFERENCE_HEADING.search(heading) for heading in heading_path):
        return "reference"
    return "operative"


# ---------------------------------------------------------------- carriers and units

def form_of(path):
    """The structure of a carrier, from its path: `markdown`, `python`, `json`, `toml` or `plain`."""
    for suffix, form in ((".md", "markdown"), (".py", "python"), (".json", "json"), (".toml", "toml")):
        if path.endswith(suffix):
            return form
    return "plain"


def carrier_identity(layer, path, item_ref, package_id):
    """The canonical identity of a carrier — its package, the item that supplied it and the path it
    is delivered at — as a stable OPAQUE id.

    The path alone is not an identity. `item_carriers` rewrites every package's member into the
    tree position it is delivered at, so two packages' `guides/review.md` both become
    `claude/guides/review.md`; keying a unit on the path alone made one package's fragment the
    other's, and made an occurrence number depend on which items the run happened to enumerate
    (GA#2).

    The id is a digest of that tuple rather than the tuple spelled out, because a delivered path is
    an ordinary absolute path on the owner's disk often enough: `shed` projects the path it emits and
    copied the identity unchanged, so one transcript member under a host home made the whole
    inventory refuse its own artifact (GC#12). A digest is what the later stages actually use it for
    — one fragment in one carrier keeps its id across reference points, and two carriers at one path
    stay two. What a reader needs to SEE is the layer, the package, the item and the projected path,
    and the record carries all four beside it."""
    return "c-" + sha256_text(f"{layer}\0{package_id or '-'}\0{item_ref or '-'}\0{path}")[:24]


def carrier(layer, path, text, item_ref=None, package_id=None, form=None, provenance=None):
    """One carrier. `form` is declared when the text is a member of the file the path names rather
    than the file itself — the session's compiled instruction text is markdown that lives inside an
    `output.json`, and reading its structure off the path's suffix made it a malformed settings
    file (GA#5)."""
    return {"layer": layer, "path": path, "item_ref": item_ref, "package_id": package_id,
            "text": text, "version_sha256": sha256_text(text), "form": form or form_of(path),
            "carrier_id": carrier_identity(layer, path, item_ref, package_id),
            "provenance": provenance or {}}


def units_of(carriers):
    """Every carrier's units, each with its enclosing headings. `unit_id` is the carrier and the
    fragment, so one fragment in one carrier keeps its id across reference points; a fragment
    repeated inside a carrier carries its occurrence."""
    units, seen = [], collections.Counter()
    for item in carriers:
        heading_path, heading_spans, enclosing, before = [], [], [], ""
        carrier_text = item["text"]
        for n, (kind, text) in enumerate(blocks_of(item["path"], item["text"], item.get("form")), 1):
            if kind == "heading":
                level = len(text) - len(text.lstrip("#"))
                heading_path = heading_path[:level - 1] + [text.strip().lstrip("#").strip()]
                # Where that heading block sits in the carrier. A heading is carrier text like any
                # other span, and projecting the detached string lost both the carrier's whole-carrier
                # decision and its credential context: for `api\_key: "alpha\n\n## shortpass\n"` the
                # floor withholds the carrier, while `heading` carried `shortpass` into two emitted
                # rows whose `text` was redacted (R2#0).
                heading_spans = heading_spans[:level - 1] + [(len(before), len(before) + len(text))]
                enclosing = enclosing[:level - 1]
            key = sha256_text(f"{item.get('carrier_id') or carrier_identity(item['layer'], item['path'], item.get('item_ref'), item.get('package_id'))}\0{text}")[:16]
            seen[key] += 1
            unit_id = f"u-{key}" if seen[key] == 1 else f"u-{key}-{seen[key]}"
            unit = {"unit_id": unit_id, "layer": item["layer"], "path": item["path"],
                    "heading": " > ".join(heading_path), "n": n, "text": text, "sha": sha256_text(text),
                    "class": classify(kind, heading_path), "operative_context": [],
                    "version_sha256": item["version_sha256"], "redaction_version": projection.CURRENT,
                    "block": kind, "item_ref": item["item_ref"], "package_id": item["package_id"],
                    "carrier_id": item.get("carrier_id") or carrier_identity(
                        item["layer"], item["path"], item.get("item_ref"), item.get("package_id")),
                    "provenance": item.get("provenance") or {},
                    "enclosing": list(enclosing),
                    # The carrier this block is a span OF, and where in it the span sits. The floor
                    # is asked about the span with the carrier intact (`projection.project_span`),
                    # because a credential's key and its value are one relationship and the splitter
                    # can put the two in different blocks. A fixed window of preceding lines does not
                    # preserve that: two nonblank lines left the key outside the window as soon as the
                    # value was a list with blank lines in it (GC#4). Neither field is emitted —
                    # `shed` carries §6.1's record and the carrier metadata, and nothing else.
                    "carrier_text": carrier_text, "span": (len(before), len(before) + len(text)),
                    "heading_spans": list(heading_spans)}
            if kind == "heading":
                enclosing = enclosing + [unit_id]
            before += text
            units.append(unit)
    return units


CONDITION_HEADING = re.compile(
    r"(?i)\b(exception|exceptions|unless|caveat|caveats|limitation|limitations|scope|applies|"
    r"applicability|trigger|triggers|when to|conditions?|prerequisites?)\b")
UNRESOLVED = "unknown:"  # a mention this reference point could not resolve, kept as a requirement


def _section_spans(units):
    """Per carrier identity, the units under each heading path — the span a heading opens."""
    spans = collections.defaultdict(list)
    for unit in units:
        spans[(unit["carrier_id"], tuple(h for h in unit["heading"].split(" > ") if h))].append(unit["unit_id"])
    return spans


def operative_context(units):
    """Fill every unit's `operative_context`: the requirement set §6.3 asks a read to cover.

    Four rules, and a closure over them:

    * a heading is not its own condition. A rule under `## Delivery` is bound by the `### Exceptions`
      under it, so the context carries the condition SPANS at or above the unit's own chain, not
      their titles. Recording only the enclosing heading units left a rule's context unchanged when
      an exception's body changed, which is the delivery state WP-10 has to tell apart (GA#1).
    * a mention that names a heading resolves to that heading's units; a heading that matches nothing
      is `unknown`, never silently the carrier's frontmatter.
    * a mention with no heading is a reference to the whole carrier: its frontmatter and its
      requirements, because that is what a reader following it would have to read (GB#9).
    * the carrier a mention names may be the unit's own, and the units it names there are part of the
      context like any other.

    The closure is transitive and cycle-safe: a requirement reached through another guide is read
    with that guide's own conditions, and the mentions inside what was just included are followed in
    turn, each unit visited once. What cannot be resolved stays in the set as `unknown:<what>` — a
    context that silently omits what it could not reach claims a completeness it does not have.

    Everything is keyed by CARRIER IDENTITY, not by path: two packages deliver `claude/guides/x.md`
    at one path, and grouping by path gave one package's rule the other package's trigger, with the
    answer depending on which package the run enumerated first (GB#10)."""
    by_carrier = collections.defaultdict(list)
    for unit in units:
        by_carrier[unit["carrier_id"]].append(unit)
    carriers_at_path = collections.defaultdict(list)
    for unit in units:
        if unit["carrier_id"] not in carriers_at_path[unit["path"]]:
            carriers_at_path[unit["path"]].append(unit["carrier_id"])
    basenames = collections.defaultdict(list)
    for path in carriers_at_path:
        basenames[path.rsplit("/", 1)[-1]].append(path)
    frontmatter = {carrier_id: next((u["unit_id"] for u in rows if u["block"] == "frontmatter"), None)
                   for carrier_id, rows in by_carrier.items()}
    spans = _section_spans(units)
    by_id = {unit["unit_id"]: unit for unit in units}

    def conditions(unit):
        chain = tuple(h for h in unit["heading"].split(" > ") if h)
        found = []
        for (carrier_id, heading_path), members in spans.items():
            if carrier_id != unit["carrier_id"] or not heading_path:
                continue
            above = heading_path[:-1]
            if above == chain[:len(above)] and CONDITION_HEADING.search(heading_path[-1]):
                found += members
        return found

    def whole_carrier(carrier_id):
        """What a reader following a bare reference to this carrier would have to read."""
        rows = [u["unit_id"] for u in by_carrier[carrier_id]
                if u["class"] == "operative" or u["block"] == "frontmatter"]
        return rows or [u["unit_id"] for u in by_carrier[carrier_id]]

    direct = {}
    for unit in units:
        context = [unit["unit_id"]]
        own = frontmatter.get(unit["carrier_id"])
        if own and own != unit["unit_id"]:
            context.append(own)
        context += unit["enclosing"]
        context += [member for member in conditions(unit) if member != unit["unit_id"]]
        direct[unit["unit_id"]] = list(dict.fromkeys(context))

    def mentioned(unit_id):
        """What this unit's text names: resolved unit ids, and `unknown:` for what it does not.

        An `unknown:` entry is kept as the string the closure walks, AND its position in the carrier
        is recorded in `origins`. The string is raw carrier text, so the emission builds the entry
        from those offsets through the floor instead of carrying it (r3 #0). Resolution reads the raw
        text as before: only what is emitted changes."""
        unit = by_id[unit_id]
        reached = []
        base = (unit.get("span") or (0, 0))[0] if unit.get("carrier_text") else None

        def origin(entry, kind, match):
            """Where in the carrier this entry was read, so the emission can project it."""
            if base is None:
                return
            named_at = (base + match.start("path"), base + match.end("path"))
            heading_at = None
            if match.group("heading") is not None and match.start("heading") >= 0:
                heading_at = (base + match.start("heading"), base + match.end("heading"))
            row = (unit["carrier_id"], unit["carrier_text"], named_at,
                   heading_at if kind == "heading" else None, kind)
            if row not in origins.setdefault(entry, []):
                origins[entry].append(row)

        for match in MENTION.finditer(unit["text"]):
            named, heading = match.group("path"), (match.group("heading") or "").strip()
            paths = [named] if named in carriers_at_path else basenames.get(named.rsplit("/", 1)[-1], [])
            targets = [carrier_id for path in paths for carrier_id in carriers_at_path[path]]
            if not targets:
                if named != unit["path"] and named != unit["path"].rsplit("/", 1)[-1]:
                    reached.append(f"{UNRESOLVED}{named}")
                    origin(f"{UNRESOLVED}{named}", "plain", match)
                continue
            if len(targets) > 1:
                # Several packages deliver this path. Every candidate's requirements are in the set
                # AND the ambiguity is stated: choosing the first match is how a context silently
                # became another package's (GB#10).
                reached.append(f"{UNRESOLVED}ambiguous:{named}")
                origin(f"{UNRESOLVED}ambiguous:{named}", "ambiguous", match)
            for carrier_id in targets:
                if heading:
                    rows = [u["unit_id"] for u in by_carrier[carrier_id]
                            if u["heading"] and heading.lower().startswith(u["heading"].rsplit(" > ", 1)[-1].lower())]
                    if rows:
                        reached += rows
                    else:
                        reached.append(f"{UNRESOLVED}{named}#{heading}")
                        origin(f"{UNRESOLVED}{named}#{heading}", "heading", match)
                else:
                    reached += whole_carrier(carrier_id)
        return [row for row in dict.fromkeys(reached) if row != unit_id]

    origins = {}
    reached = {unit["unit_id"]: mentioned(unit["unit_id"]) for unit in units}
    # One map for every unit: an entry a unit reached through the closure was READ in another
    # carrier, and it is that carrier's offsets and that carrier's floor decision the emission needs.
    for unit in units:
        unit["context_origins"] = origins

    for unit in units:
        context, seen = list(direct[unit["unit_id"]]), {unit["unit_id"]}
        # The starting unit's own requirements are expanded as well: seeding the queue with its
        # mentions alone left a condition span's own references out of the closure, so a rule whose
        # exception pointed at a second guide was read without that guide (GC#8).
        queue = collections.deque([row for row in direct[unit["unit_id"]] if row != unit["unit_id"]]
                                  + reached[unit["unit_id"]])
        while queue:  # cycle-safe: each unit id is expanded once
            row = queue.popleft()
            if row in seen:
                continue
            seen.add(row)
            context.append(row)
            if row.startswith(UNRESOLVED):
                continue
            for member in direct.get(row, []):
                if member not in seen:
                    queue.append(member)
            for onward in reached.get(row, []):
                if onward not in seen:
                    queue.append(onward)
        unit["operative_context"] = list(dict.fromkeys(context))
    return units


def _carrier_span(carrier_text, start, end, home=None, decision=None):
    """One span of a carrier, through the floor, judged with the carrier INTACT.

    The floor reads a credential-named key and the value that follows it as one relationship, and
    the splitter can put the two in different blocks — so projecting a block alone emitted the value
    with nothing to mark it (GC#4). `projection.project_span` takes the floor's decision about the
    WHOLE carrier: its masked extents, clipped to this span, and its refusal to return the carrier at
    all, which withholds every span of it. `decision` is that decision when the caller has already
    taken it for this carrier's other spans.

    Every carrier-derived field of an emitted unit goes through HERE. `text` did and `heading` did
    not, and the detached heading published `shortpass` from a carrier the floor withheld (R2#0)."""
    out = projection.project_span(carrier_text, start, end, home, decision)
    disclosed = projection.discloses(out, home)
    if disclosed is not None:
        raise Refused(f"DISCLOSED_IN_UNIT: the projection left {disclosed} in a unit's text; no artifact is written")
    return out


def _projected_span(unit, home=None, decision=None):
    """The unit's own block, through `_carrier_span`.

    A unit that carries no carrier of its own — a caller that built the record by hand — is
    projected as the block it is, which is the same answer as a carrier holding only that block."""
    carrier_text, span = unit.get("carrier_text"), unit.get("span")
    if not carrier_text or not span:
        return projected(unit["text"], home)
    return _carrier_span(carrier_text, span[0], span[1], home, decision)


def _projected_heading(unit, home=None, decision=None):
    """The unit's heading path, each component projected as the span of the carrier it IS.

    The components are joined after projection, never before: joining first would hand the floor a
    string that stands nowhere in the carrier, and the heading of a withheld carrier has to come back
    blank component by component."""
    carrier_text, spans = unit.get("carrier_text"), unit.get("heading_spans")
    if not unit["heading"]:
        return unit["heading"]
    if not carrier_text or spans is None:
        return projected(unit["heading"], home)
    parts = [_carrier_span(carrier_text, start, end, home, decision).strip().lstrip("#").strip()
             for start, end in spans]
    return " > ".join(part for part in parts if part)


# ---------------------------------------------------------------- emission: one declared rule per field
# A row used to be built as `{**{field: unit[field] for field in UNIT_FIELDS}, ...}` — a RAW COPY of
# every field, with the ones this module knew about overwritten afterwards. A field on no list stayed
# raw, and three rounds found three of them: the span (R1#0), the heading (R2#0), and
# `operative_context`, whose `unknown:` entries are built out of raw carrier text (r3 #0). The list
# was default-ALLOW, so the next unlisted field was only a matter of time.
#
# Every emitted row is now built from a DECLARED TABLE and nothing else: one rule per field, applied
# by one function, and a field on the source record or declared by the schema that no rule covers is
# refused by name. The rules are data, so a control reads them and a refusal says which one answered.
#
# Nine rules. Five are leaves — `as_scalar`, `as_constant`, `as_enum`, `as_metadata`, `as_opaque` —
# one is the carrier's own text (`as_span`), and three compose: `list_of`, `map_of`, `table_of`.
# `one_of` is the ninth: a per-item union, which `operative_context` needs because its items are of
# two kinds. Composition is defined ONCE here rather than spelled per field, so there is no
# `span-list` rule to forget to keep in step with `span`.
SCALAR, CONSTANT, ENUM, METADATA, OPAQUE, SPAN = "scalar", "constant", "enum", "metadata", "opaque", "span"
LIST, MAP, OBJECT, UNION = "list", "map", "object", "union"
CONTEXT, TREE = "context", "tree"
# The shapes an opaque id has. An opaque field may carry nothing but its own form: it is emitted
# without passing the floor, so a value that is not the form could carry text this row never
# projected (`carrier_id` was once the raw delivered path, GC#12).
OPAQUE_FORMS = {"unit_id": re.compile(r"^u-[0-9a-f]{16}(-[0-9]+)?$"),
                "carrier_id": re.compile(r"^c-[0-9a-f]{24}$"),
                "sha256": re.compile(r"^[0-9a-f]{64}$")}


def as_scalar(nullable=False):
    """A number or a boolean, by exact type. Not a string, not a float, and `None` only when the
    table says so: a count that arrives as text is a string nobody projected."""
    return {"rule": SCALAR, "nullable": nullable}


def as_constant(value):
    """Exactly one literal."""
    return {"rule": CONSTANT, "value": value}


def as_enum(values, nullable=False):
    """A member of a declared set, which is the field's whole vocabulary.

    `values` may be a callable, so the vocabulary can be read from its OWNER — the schema declares
    the layer names and the unit classes, and restating them here would be a second copy to drift."""
    return {"rule": ENUM, "values": values, "nullable": nullable}


def _enum_values(spec):
    """The set this enum admits. A callable is asked EVERY time, never cached: the vocabulary's owner
    is a table in force, and a control that stands a fixture table in its place must be judged
    against that one."""
    if callable(spec["values"]):
        return frozenset(spec["values"]())
    if not isinstance(spec["values"], frozenset):
        spec["values"] = frozenset(spec["values"])
    return spec["values"]


def schema_enum(name):
    """The vocabulary the SCHEMA declares for one of its shapes."""
    return frozenset(((inventory_schema().get("$defs") or {}).get(name) or {}).get("enum") or ())


def layer_names():
    """The whole vocabulary of `layer`, from its two code-owned sources: the names the SCHEMA
    declares for an artifact, and the names the producer table in force carries.

    Both, because both are real and neither is owner data. The schema is the artifact's contract, so
    a unit carrying a layer it does not name is a unit no reader can validate; the table in force is
    what a control stands a fixture producer in — a suite that declares a `no-units` layer to test
    the layer table is testing this module, not publishing a layer. What matters for the floor is
    that a layer name is never read out of a file, and under both sources it never is."""
    return frozenset(schema_enum("layer_name")) | {name for name, _ in LAYERS}


def as_context():
    """One entry of `operative_context` that this reference point could not resolve.

    The entry is BUILT from the carrier offsets of the mention it came from, through the same floor
    decision as any other span of that carrier — never from the stored string, which is raw carrier
    text and is what leaked (r3 #0). Internal resolution still reads the raw text; only what is
    emitted changes."""
    return {"rule": CONTEXT}


def as_metadata(nullable=False):
    """A string ABOUT the carrier rather than of it — a delivered path, a host's own value, a
    diagnostic this module composed — through the floor on its own."""
    return {"rule": METADATA, "nullable": nullable}


def as_opaque(form, nullable=False):
    """An id whose form is its guarantee, checked against `OPAQUE_FORMS`."""
    return {"rule": OPAQUE, "form": form, "nullable": nullable}


def as_span(offsets, join=None, marks=False):
    """The carrier's own text, through `_carrier_span` with that carrier's whole-carrier decision.

    `offsets` names the field of the SOURCE record holding the span (or spans) in carrier
    coordinates, never the stored string: the string is what the leaks were made of. `join` makes a
    breadcrumb of several spans, and `marks` strips a heading's `#` marks after projection."""
    return {"rule": SPAN, "offsets": offsets, "join": join, "marks": marks}


def list_of(item):
    """A list, with `item`'s rule applied to each element, in order."""
    return {"rule": LIST, "item": item}


def map_of(key, value):
    """An object used as a map: `key`'s rule over every key, `value`'s over every value."""
    return {"rule": MAP, "key": key, "value": value}


def table_of(fields, optional=(), schema=None):
    """A nested object with its own table. Its key set must equal the table's, minus `optional`.

    `schema` names the shape the schema declares for it, when it declares one, so a field the schema
    requires and this table has no rule for is refused rather than quietly dropped."""
    return {"rule": OBJECT, "fields": fields, "optional": frozenset(optional), "schema": schema}


def one_of(*choices):
    """A value of several declared kinds, tried in order. An item matching none is refused."""
    return {"rule": UNION, "choices": choices}


_SCHEMA_NAMES = {}


def schema_row_fields(kind):
    """The field names the schema declares for one row kind, or an empty set when it declares none.

    Read from the schema rather than restated here: a field the schema requires and the table has no
    rule for is the defect this emission is about, and a second copy of the schema's field list could
    drift out of step with it."""
    if kind not in _SCHEMA_NAMES:
        try:
            defs = inventory_schema().get("$defs") or {}
            _SCHEMA_NAMES[kind] = frozenset((defs.get(kind) or {}).get("properties") or {})
        except Exception:                      # an unreadable schema is its own refusal elsewhere
            _SCHEMA_NAMES[kind] = frozenset()
    return _SCHEMA_NAMES[kind]


def schema_field_names():
    """Every field name the schema declares anywhere: these are schema text and may be printed."""
    if "*" not in _SCHEMA_NAMES:
        names = set()
        try:
            for shape in (inventory_schema().get("$defs") or {}).values():
                names |= set((shape or {}).get("properties") or {})
            names |= set(inventory_schema().get("properties") or {})
        except Exception:
            names = set()
        _SCHEMA_NAMES["*"] = frozenset(names)
    return _SCHEMA_NAMES["*"]


def as_tree():
    """A producer's own note, of a shape this module does not fix: every string leaf and every key
    through the floor, numbers and booleans as they are, and nothing else admitted.

    This is NOT a way around the tables. It is used where the shape belongs to a producer rather
    than to the record — `produced_by.notes` holds whatever the layer producers recorded — and what
    it guarantees is the one thing that matters there: no string leaves unprojected. The KEY SET is
    still declared by the table above it, so a new note is declared before it can be published."""
    return {"rule": TREE}


def _emit_tree(value, place, where):
    """One producer note through the floor, recursively."""
    if value is None or type(value) in (int, bool):
        return value
    if isinstance(value, str):
        return projected(value, place["home"]) if value else value
    if isinstance(value, (list, tuple)):
        return [_emit_tree(item, place, f"{where}[{n}]") for n, item in enumerate(value)]
    if isinstance(value, dict):
        emitted = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise Refused(f"EMISSION_NOT_DECLARED_VALUE {where}: a {type(key).__name__} key, "
                              f"where a note's keys are strings")
            at = projected(key, place["home"]) if key else key
            if at in emitted:
                raise Refused(f"EMISSION_KEY_COLLISION {where}: two note keys project to one string; "
                              f"a note is refused rather than merged")
            emitted[at] = _emit_tree(item, place, f"{where}[{at}]")
        return emitted
    raise Refused(f"EMISSION_NOT_DECLARED_VALUE {where}: a {type(value).__name__}, which no rule of "
                  f"this emission admits")


def _named_field(where, key, spec):
    """How a refusal may name a key. A field name the SCHEMA or the table declares is schema text
    and may be printed; a key that arrived as DATA is named by its length and a short digest, so a
    refusal about an undeclared key cannot be the thing that publishes it."""
    if spec is not None or key in schema_field_names():
        return f"{where}.{key}"
    return f"{where}.<undeclared key: {len(str(key))} characters, {sha256_text(str(key))[:12]}>"


def _emit_span(spec, place, where):
    """One carrier-derived field, from its OFFSETS, through the floor's whole-carrier decision."""
    unit = place["unit"]
    carrier_text, offsets = unit.get("carrier_text"), unit.get(spec["offsets"])
    if spec["join"] is None:
        if not carrier_text or not offsets:
            # A record built by hand carries no carrier of its own: the block IS the carrier, which
            # is the same answer as a carrier holding only that block.
            return projected(unit.get("text") or "", place["home"])
        _span_agrees(unit, place, where)
        return _carrier_span(carrier_text, offsets[0], offsets[1], place["home"], place["decision"])
    if not carrier_text or not offsets:
        return projected(unit.get("heading") or "", place["home"])
    _span_agrees(unit, place, where)
    parts = [_carrier_span(carrier_text, start, end, place["home"], place["decision"])
             for start, end in offsets]
    if spec["marks"]:
        parts = [part.strip().lstrip("#").strip() for part in parts]
    return spec["join"].join(parts)


def _span_agrees(unit, place, where):
    """The record's own text must BE the carrier's bytes at the span it declares.

    Every offset this emission computes — a span, a heading, a mention's position — is in the
    carrier's coordinates, and that arithmetic is only sound while the record and the carrier agree.
    It is checked rather than assumed: a record whose `text` is not `carrier_text[start:end]` is a
    record whose offsets name something else."""
    carrier_text, span = unit.get("carrier_text"), unit.get("span")
    if not carrier_text or not span:
        return
    if unit.get("text") != carrier_text[span[0]:span[1]]:
        raise Refused(f"EMISSION_SPAN_MISMATCH {where}: the record's text is not the carrier's bytes "
                      f"at the span it declares, so no offset of this row can be trusted")


def _decision_for(place, carrier_id, carrier_text):
    """The floor's whole-carrier decision for one carrier, taken once per carrier."""
    decisions = place.setdefault("decisions", {})
    if carrier_id not in decisions:
        decisions[carrier_id] = projection.carrier_decision(carrier_text, place["home"])
    return decisions[carrier_id]


def _render_context(origin, place):
    """One unresolved context entry, assembled from projected spans of the carrier it was found in."""
    carrier_id, carrier_text, named, heading, kind = origin
    decision = _decision_for(place, carrier_id, carrier_text)
    out = UNRESOLVED + ("ambiguous:" if kind == "ambiguous" else "")
    out += _carrier_span(carrier_text, named[0], named[1], place["home"], decision)
    if heading is not None:
        out += "#" + _carrier_span(carrier_text, heading[0], heading[1], place["home"], decision).strip()
    return out


def _emit_context(value, place, where):
    """An unresolved entry, from its ORIGINS. An entry with none is refused: the stored string is
    raw carrier text and is never what is emitted.

    Several carriers can name the same thing, and their floor decisions can differ — one withholds
    its carrier whole and another does not. When the renderings disagree the WITHHELD one stands,
    because a context entry says what a reader would have to read and the safe answer is the one
    that carries nothing."""
    unit = place["unit"]
    origins = (unit.get("context_origins") or {}).get(value)
    if not origins:
        if not unit.get("carrier_text"):
            # A record built by hand carries no carrier of its own, so this entry takes exactly the
            # path that record's `text` takes.
            return projected(value, place["home"])
        raise Refused(f"EMISSION_UNDECLARED {where}: an unresolved context entry with no carrier "
                      f"offsets behind it; the stored string is never what is emitted")
    rendered = sorted({_render_context(origin, place) for origin in origins})
    withheld = [row for row in rendered if projection.blank_for("x") in row]
    return (withheld or rendered)[0]


def _emit_value(spec, value, place, where):
    """One value through its ONE declared rule."""
    kind = spec["rule"]
    if kind == SPAN:
        return _emit_span(spec, place, where)
    if value is None:
        if spec.get("nullable"):
            return None
        raise Refused(f"EMISSION_NOT_DECLARED_VALUE {where}: None, where the table declares {kind}")
    if kind == SCALAR:
        if type(value) not in (int, bool):
            raise Refused(f"EMISSION_NOT_DECLARED_VALUE {where}: a {type(value).__name__} where the "
                          f"table declares a number or a boolean")
        return value
    if kind == CONSTANT:
        if value != spec["value"]:
            raise Refused(f"EMISSION_NOT_DECLARED_VALUE {where}: not the one value this field carries")
        return value
    if kind == ENUM:
        if value not in _enum_values(spec):
            raise Refused(f"EMISSION_NOT_DECLARED_VALUE {where}: a value no declared set holds")
        return value
    if kind == METADATA:
        if not isinstance(value, str):
            raise Refused(f"EMISSION_NOT_DECLARED_VALUE {where}: a {type(value).__name__} where the "
                          f"table declares metadata text")
        return projected(value, place["home"]) if value else value
    if kind == OPAQUE:
        if not (isinstance(value, str) and OPAQUE_FORMS[spec["form"]].match(value)):
            raise Refused(f"EMISSION_NOT_OPAQUE {where}: not the {spec['form']} form, so it may carry "
                          f"text this row never projected")
        return value
    if kind == LIST:
        if not isinstance(value, list):
            raise Refused(f"EMISSION_NOT_DECLARED_VALUE {where}: a {type(value).__name__} where the "
                          f"table declares a list")
        return [_emit_value(spec["item"], item, place, f"{where}[{n}]")
                for n, item in enumerate(value)]
    if kind == MAP:
        if not isinstance(value, dict):
            raise Refused(f"EMISSION_NOT_DECLARED_VALUE {where}: a {type(value).__name__} where the "
                          f"table declares a map")
        emitted = {}
        for key, item in value.items():
            at = _emit_value(spec["key"], key, place, f"{where}<key>")
            if at in emitted:
                # Two keys that project to one string are TWO facts. Merging them would drop one
                # silently and the surviving value would answer for both.
                raise Refused(f"EMISSION_KEY_COLLISION {where}: two keys project to one string; a map "
                              f"is refused rather than merged")
            emitted[at] = _emit_value(spec["value"], item, place, f"{where}[{at}]")
        return emitted
    if kind == CONTEXT:
        return _emit_context(value, place, where)
    if kind == TREE:
        return _emit_tree(value, place, where)
    if kind == OBJECT:
        return emit_row(where, spec, value, place)
    if kind == UNION:
        for choice in spec["choices"]:
            try:
                return _emit_value(choice, value, place, where)
            except Refused:
                continue
        raise Refused(f"EMISSION_UNION_UNMATCHED {where}: no declared kind of this field admits it")
    raise Refused(f"EMISSION_UNDECLARED {where}: the table names a rule this emission does not have")


def emit_row(kind, table, source, place):
    """`source` as the artifact carries it: every field through its declared rule, and nothing else.

    A field of the source record, or declared by the schema for this row, that the table has no rule
    for is refused BY NAME. That is the whole point: the previous shape copied every field and
    overwrote the ones it knew, so an unlisted field left raw was invisible until a reviewer read the
    bytes."""
    fields, optional = table["fields"], table["optional"]
    for key in source:
        if key not in fields and key not in EMISSION_INTERNAL:
            raise Refused(f"EMISSION_UNDECLARED {_named_field(kind, key, fields.get(key))}: the record "
                          f"carries this field and no rule says how it is emitted")
    for key in schema_row_fields(table.get("schema") or ""):
        if key not in fields:
            raise Refused(f"EMISSION_UNDECLARED {kind}.{key}: the schema declares this field for this "
                          f"row and no rule says how it is emitted")
    emitted = {}
    for key, spec in fields.items():
        if key not in source and key in optional:
            continue
        if key not in source and spec["rule"] != SPAN:
            raise Refused(f"EMISSION_UNDECLARED {kind}.{key}: the table declares this field and the "
                          f"record does not carry it")
        emitted[key] = _emit_value(spec, source.get(key), place, f"{kind}.{key}")
    held = set(emitted) | {key for key in fields if key in optional and key not in source}
    if held != set(fields):
        raise Refused(f"EMISSION_UNDECLARED {kind}: the emitted row's fields are not the table's "
                      f"({sorted(set(fields) ^ held)})")
    return emitted


# The vocabulary of `block`, derived rather than enumerated: the splitter's own kinds, plus the
# names python gives its statements, which `py_blocks` uses for anything it does not name itself. A
# kind outside this set is refused, so a new splitter kind is declared here instead of travelling
# into an artifact unread.
BLOCK_KINDS = frozenset((
    # md_blocks
    "heading", "paragraph", "list-item", "table-head", "table-row", "blank", "code", "frontmatter",
    # py_blocks, for the shapes it names itself
    "docstring", "assign-open", "assign-close", "list-element", "value",
    # plain_blocks, for a carrier whose structure the splitter does not read
    "code-block")) | frozenset(
    name for name in dir(ast)
    if isinstance(getattr(ast, name), type) and issubclass(getattr(ast, name), ast.stmt))
# Fields a unit record carries that are NOT emitted, each because the emission has its own path to
# what they hold: the carrier and the offsets are what `as_span` reads, and `enclosing` is the
# closure's own bookkeeping. Declared here so a field left off the table is refused rather than
# silently dropped.
EMISSION_INTERNAL = frozenset(("carrier_text", "span", "heading_spans", "enclosing",
                               "context_origins"))
# The hosts a provenance row may name. This one IS a vocabulary of this code: the host of a session
# injection is named by the producer, never read out of a file.
PROVENANCE_HOSTS = frozenset(("claude", "codex"))

PROVENANCE_TABLE = table_of({
    "as_of": as_metadata(nullable=True), "session": as_metadata(nullable=True),
    "transcript": as_metadata(nullable=True), "where": as_metadata(nullable=True),
    "scope": as_metadata(nullable=True), "reference": as_metadata(nullable=True),
    "record": as_scalar(nullable=True), "identity": as_metadata(nullable=True),
    # `status` and `keep_units` come from the owner's LEDGER, not from this code: the status is
    # whatever that file says (`str(entry.get("status", ""))`) and the kept ids are the ledger's own.
    # Neither is a vocabulary this module owns, so both pass the floor as metadata rather than
    # pretending to be an enum or an id of a form nothing guarantees.
    "status": as_metadata(nullable=True),
    "keep_units": list_of(as_metadata()), "keep_reason": as_metadata(nullable=True),
    "hosts": list_of(as_enum(PROVENANCE_HOSTS)),
}, optional=("as_of", "session", "transcript", "where", "scope", "reference", "record", "identity",
             "status", "keep_units", "keep_reason", "hosts"), schema="provenance")

# §6.1's unit record as the artifact carries it. `operative_context` is ONE list with a per-item
# union: a resolved entry is an opaque unit id, and an unresolved one is built from the carrier
# offsets of the mention it came from — never from the stored string, which is what leaked (r3 #0).
UNIT_TABLE = table_of({
    "unit_id": as_opaque("unit_id"),
    "layer": as_enum(layer_names),
    "path": as_metadata(),
    "heading": as_span("heading_spans", join=" > ", marks=True),
    "n": as_scalar(),
    "text": as_span("span"),
    "sha": as_opaque("sha256"),
    "class": as_enum(lambda: schema_enum("unit_class") or ("operative", "reference")),
    "operative_context": list_of(one_of(as_opaque("unit_id"), as_context())),
    "version_sha256": as_opaque("sha256"),
    "redaction_version": as_constant(projection.CURRENT),
    "block": as_enum(BLOCK_KINDS),
    "item_ref": as_metadata(nullable=True),
    "package_id": as_metadata(nullable=True),
    "carrier_id": as_opaque("carrier_id"),
    "provenance": PROVENANCE_TABLE,
}, schema="unit")


# The note keys the layer producers write. The key set is declared so a new note is declared here
# before it can be published; what each note HOLDS is a producer's own shape (`as_tree`).
NOTE_KEYS = frozenset((
    "adopted_packages", "baselines", "frozen_missing", "hosts_in_scope", "installed_baseline_ref",
    "ledger_keep_held_back", "overlay_counts", "overlay_hosts", "pin", "release", "selection",
    "state", "transcripts"))

# R1: the reference point's own block. Which of `commit`, `ref` and `content_ref` it carries depends
# on the reference point, so each is optional and the kind decides.
REFERENCE_TABLE = table_of({
    "kind": as_enum(REFERENCES),
    "complete": as_scalar(),
    "incomplete_reasons": list_of(as_metadata()),
    "commit": as_metadata(nullable=True),
    "ref": as_metadata(nullable=True),
    "content_ref": as_metadata(nullable=True),
}, optional=("commit", "ref", "content_ref"))

# R2: who produced it. `notes` is the producers' own, through the floor leaf by leaf.
PRODUCED_BY_TABLE = table_of({
    "module": as_constant("session-distill/runlib/inventory.py"),
    "design": as_constant(DESIGN),
    "state_root": as_metadata(nullable=True),
    "notes": map_of(as_enum(NOTE_KEYS), as_tree()),
})

# R3: the layer/producer table. `reasons` are diagnostics this module composed, exception messages
# among them, and an exception message is a path often enough — so every one passes the floor. Two
# of the sites that build them did not (found during S1, `layer_rows`'s `units_of` handlers).
LAYER_ROW_TABLE = table_of({
    "layer": as_enum(layer_names),
    "producer": as_metadata(nullable=True),
    "status": as_enum(STATUSES),
    "units": as_scalar(),
    "empty": as_scalar(),
    "reasons": list_of(as_metadata()),
}, optional=("empty",), schema="layer_row")

# R5: a rename, in its two shapes. A row names carriers by their opaque ids and projects the two
# paths it reports, because a delivered path is the owner's disk often enough.
RENAME_AMBIGUOUS_TABLE = table_of({
    "unit_id": as_opaque("unit_id"),
    "ambiguous": as_scalar(),
    "from_carriers": list_of(as_opaque("carrier_id")),
    "to_carriers": list_of(as_opaque("carrier_id")),
    "reason": as_metadata(),
})
RENAME_TABLE = table_of({
    "unit_id": as_opaque("unit_id"),
    "from_unit_id": as_opaque("unit_id"),
    "from_carrier_id": as_opaque("carrier_id"),
    "to_carrier_id": as_opaque("carrier_id"),
    "from_path": as_metadata(),
    "to_path": as_metadata(),
    "from_layer": as_enum(layer_names),
    "to_layer": as_enum(layer_names),
    "moved": list_of(as_enum(("path", "layer", "package", "carrier"))),
})

def shed(units, home=None):
    """The unit records the artifact carries: every field through `UNIT_TABLE`, and nothing else.

    This is the boundary the raw text does not cross. `sha` and `version_sha256` are the raw
    fragment's and the raw carrier's, taken in `units_of` before any projection, so a returned
    fragment still binds to its source version.

    There is no raw copy here any more. The previous shape copied every field of the record and
    overwrote the ones it knew, which is how three rounds each found one more field left raw — the
    span, the heading, and `operative_context`. A field the record carries or the schema declares
    with no rule in the table is refused by name (`EMISSION_UNDECLARED`), so the next unlisted field
    stops the run instead of travelling into an artifact."""
    place = {"home": home, "decisions": {}}
    records_out = []
    for unit in units:
        carrier_text = unit.get("carrier_text")
        if carrier_text is not None:
            # Once per carrier, not once per span: the decision is a property of the carrier, and it
            # carries the floor's whole-carrier WITHHOLDING as well as its extents.
            _decision_for(place, unit["carrier_id"], carrier_text)
        place["unit"] = unit
        place["decision"] = place["decisions"].get(unit["carrier_id"])
        records_out.append(emit_row("unit", UNIT_TABLE, unit, place))
    return records_out


def renames_against(units, base_units, home=None):
    """Units whose fragment carried over from the base reference point in another carrier.

    A row names the carriers by the same opaque ids the unit records carry (GC#12), and the two
    paths it reports pass the floor, because a delivered path is the owner's disk often enough.

    A fragment is evidence of a rename only when it is a requirement and it belongs to ONE carrier
    on each side. Uniqueness is per carrier identity, not per path: two packages delivering one path
    are two carriers, and counting paths read that as an unambiguous rename (GB#10). An ambiguous
    fragment is reported as ambiguous rather than resolved to whichever carrier came first."""
    def unique_carrier(rows):
        carriers = collections.defaultdict(set)
        for unit in rows:
            if unit["class"] == "operative":
                carriers[unit["sha"]].add(unit["carrier_id"])
        return carriers

    place = {"home": home, "decisions": {}}
    was_all, now_all = unique_carrier(base_units), unique_carrier(units)
    was = {sha: next(iter(ids)) for sha, ids in was_all.items() if len(ids) == 1}
    now = {sha: next(iter(ids)) for sha, ids in now_all.items() if len(ids) == 1}
    first = {}
    for unit in base_units:
        first.setdefault(unit["carrier_id"], {}).setdefault(unit["sha"], unit)
    by_carrier = {unit["carrier_id"]: unit for unit in base_units}
    rows = []
    for unit in units:
        sha = unit["sha"]
        if sha not in was_all or sha not in now_all:  # both sides hold it, and only requirements are in either
            continue
        if sha not in was or sha not in now:
            rows.append(emit_row("rename_ambiguous", RENAME_AMBIGUOUS_TABLE, {
                "unit_id": unit["unit_id"], "ambiguous": True,
                "from_carriers": sorted(was_all[sha]), "to_carriers": sorted(now_all[sha]),
                "reason": "the fragment belongs to more than one carrier on one side, "
                          "so which carrier it moved from is not decided here"}, place))
            continue
        if was[sha] == now[sha]:
            continue
        # `was[sha]` is a carrier of `base_units` and `first` is built from the same units, so the
        # fragment's source is there by construction.
        source = first[was[sha]][sha]
        rows.append(emit_row("rename", RENAME_TABLE, {
            "unit_id": unit["unit_id"], "from_unit_id": source["unit_id"],
            "from_carrier_id": was[sha], "to_carrier_id": now[sha],
            # The two paths go in RAW: `as_metadata` is the one thing that projects them, so a field
            # added here cannot reach the artifact by a route the table never declared.
            "from_path": source["path"], "to_path": unit["path"],
            "from_layer": source["layer"], "to_layer": unit["layer"],
            "moved": [kind for kind, moved in (("path", source["path"] != unit["path"]),
                                               ("layer", source["layer"] != unit["layer"]),
                                               ("package", source["package_id"] != unit["package_id"]))
                      if moved] or ["carrier"]}, place))
    return rows


# ---------------------------------------------------------------- frozen copies of the owner's state

SYMLINK_POLICY = ("a symlink is never read and never hashed: it names a file outside the root whose "
                  "ownership this inventory cannot state, and the host adapters refuse one in an "
                  "instruction path for the same reason (compose/instructions_session.py)")


def linked_above(path, boundary=None):
    """The first symlink on `path`'s own chain, or None: the leaf, and every component between it and
    the declared root it was named under.

    This is the one question "may these bytes be read" is asked through, and it is asked BEFORE any
    byte is read. `walk_source` asked it of the walker's root and of what the walk found under it,
    which left every read that does not go through the walker — the runtime state, a pin, a
    snapshot, a baseline, a single-file copy input — reading first and judging afterwards, and left
    a root whose own ancestors inside the declared root were links (GC#7).

    `boundary` is the root the caller declared. Components ABOVE it are not judged: the owner named
    that root, and where they keep it is not this inventory's question (on macOS `/tmp` is itself a
    link). Components at and below it are, because a link there redirects bytes out of the root the
    input manifest says were read."""
    path = pathlib.Path(path).expanduser()
    chain = [path]
    if boundary is not None:
        boundary = pathlib.Path(boundary).expanduser()
        for parent in path.parents:
            chain.append(parent)
            if parent == boundary or not parent.is_relative_to(boundary):
                break
    return next((item for item in chain if item.is_symlink()), None)


def source_selection(path, boundary=None, home=None):
    """`path`, admitted for reading — or a refusal, before a byte of it is read.

    Every read of the owner's state passes through here: the runtime state, a pin, a snapshot, a
    baseline's own item list, and each input of a frozen copy."""
    linked = linked_above(path, boundary)
    if linked is not None:
        raise Refused(f"SOURCE_LINKED {masked(linked, home)}: {SYMLINK_POLICY}; "
                      f"{masked(path, home)} is not read")
    return pathlib.Path(path).expanduser()


def read_source(path, boundary=None, home=None):
    """The text of one file of the owner's state, after `source_selection` admitted it."""
    return source_selection(path, boundary, home).read_text(encoding="utf-8")


def walk_source(root, boundary=None):
    """`(readable, omitted)` under `root`: the files this inventory may read, and the ones it may
    not, each with the reason.

    One walker decides what is read, what is hashed and what is copied. Two decisions used to
    disagree: the hash reported a symlink as omitted while the copier followed it, so bytes from
    outside the declared root reached a frozen copy that the input manifest said had never been
    read (GB#8). A link is rejected before it is read, leaf and ancestor alike — the root's own
    chain through `linked_above`, and everything under it here."""
    root = pathlib.Path(root).expanduser()
    readable, omitted = [], []
    if linked_above(root, boundary) is not None:
        return readable, [{"path": ".", "reason": "symlink"}]
    if not root.is_dir():
        return readable, [{"path": masked(root), "reason": "the root is not a directory"}]
    linked = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if any(relative == name or relative.startswith(f"{name}/") for name in linked):
            continue  # its ancestor was a link: the whole subtree is outside the declared root
        if path.is_symlink():
            omitted.append({"path": relative, "reason": "symlink"})
            linked.append(relative)
            continue
        if path.is_file():
            readable.append((relative, path))
    return readable, omitted


def hash_tree(root):
    """`({relative path: sha256}, omissions)` over `walk_source`'s readable set, each file admitted
    through `source_selection` before its bytes are read.

    The omissions are part of the answer, not a silence: a symlink is skipped by policy, a path the
    selection does not admit is skipped by that decision, an unreadable file is skipped by failure,
    and a before/after comparison over a set that quietly dropped any of them would say "unchanged"
    about files it never looked at (GA#3)."""
    readable, omissions = walk_source(root)
    digests = {}
    for relative, path in readable:
        try:
            # Admitted through the one entry point, like every other read of the owner's state: the
            # walker decided WHICH files, and this decides whether these bytes may be read at all.
            # Reading them directly made `source_selection` a claim rather than a gate — denying it
            # outright still hashed eight files (R1#6).
            digests[relative] = hashlib.sha256(source_selection(path, root).read_bytes()).hexdigest()
        except Refused as exc:
            omissions.append({"path": relative, "reason": f"not admitted: {exc}"})
        except OSError as exc:
            omissions.append({"path": relative, "reason": f"unreadable: {projected_message(exc)}"})
    return digests, omissions


STATE_DIR_VAR, CORPUS_DIR_VAR = "AGENT_BIOS_STATE_DIR", "AGENT_BIOS_INSTRUCTIONS_DIR"
STATE_DIR_DEFAULT, CORPUS_DIR_DEFAULT = ".local/share/agent-bios", ".config/agent-bios/corpus"


def configured_roots(state_root=None, user_root=None, environ=None, home=None):
    """The owner's state and authoring roots AS CONFIGURED — whether or not this run reads them.

    Protection and reading are two questions, and they were one value. `--no-state` set both roots to
    None before the protected set was built, so the flag that says "read nothing" also said "write
    anywhere": `--state-root <s> --to <s>/out --no-state` exited 0 and wrote four artifacts under the
    owner's state root, while the same command without the flag refused by name. A root is protected
    because it is the owner's, not because this run happens to open it.

    Resolution is the driver's own order — the flag, the environment, then the installed default — so
    a caller that names neither still gets the owner's real roots. That is the safe direction:
    protection never depends on being told."""
    environ = os.environ if environ is None else environ
    # The home is the one THIS ENVIRONMENT names, which is the rule the shipped installer follows
    # (`compose/instructions_install.py`: `env.get("HOME", str(Path.home()))`). Reading the process's
    # own home instead meant the installed defaults did not move with `HOME`, so a fixture
    # environment resolved the real owner's state root — and a control that reverted the protection
    # being tested then wrote inventory artifacts into it (R2#6).
    home = pathlib.Path(environ.get("HOME") or pathlib.Path.home()) if home is None else pathlib.Path(home)
    state = state_root or environ.get(STATE_DIR_VAR) or str(home / STATE_DIR_DEFAULT)
    user = user_root or environ.get(CORPUS_DIR_VAR) or str(home / CORPUS_DIR_DEFAULT)
    return pathlib.Path(state).expanduser(), pathlib.Path(user).expanduser()


def install_module(repo=REPO):
    """The shipped `compose/instructions_install.py`, loaded by path — the same way this module
    already loads the store, so a checkout under test is the one that answers."""
    path = pathlib.Path(repo) / "compose" / "instructions_install.py"
    if not path.is_file():
        raise Refused(f"PRODUCER_UNAVAILABLE {masked(path)}: the host homes are the installer's rule")
    spec = importlib.util.spec_from_file_location("instructions_install_frozen", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(pathlib.Path(repo) / "compose"))
    with no_bytecode():
        spec.loader.exec_module(module)
    return module


def host_homes(environ=None, repo=REPO):
    """The host configuration homes AS CONFIGURED, by paths alone: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`,
    and the installed defaults when neither is set.

    `NATIVE`'s `home` fields are the DEFAULTS, and the protected sets read only those — so a host
    home moved by either variable was a writable destination and an admissible scratch parent for
    both hosts (R2#1). The rule is not restated here: `compose/instructions_install.py` owns it
    (`claude_root`, `codex_root`), it ships, and it is loaded by path like the store. Constructing the
    installer resolves paths and touches no disk.

    A checkout without that file refuses rather than returning a shorter list: protection that cannot
    be resolved must not quietly become protection of less."""
    module = install_module(repo)
    installer = module.InstructionsInstaller(repo, dict(os.environ if environ is None else environ))
    return [installer.claude_root, installer.codex_root]


def protected_roots(state_root, user_root, native_roots, host_homes=None, checkout=None,
                    environ=None, repo=REPO):
    """Every root this inventory must not write into: the owner's state, the authoring root, the
    host homes, the checkout and the project roots.

    `state_root` and `user_root` here are the CONFIGURED roots (`configured_roots`), not the ones
    this run reads: `--no-state` makes the second pair None and must not make the first pair None.

    The host homes are protected whether or not this run reads them. A run reads the native layers
    from its own capture, so the homes are not among its inputs — but `~/.claude` is still never a
    place for a run directory, and deriving the protected set from the inputs alone quietly stopped
    protecting them the moment the capture replaced them (GA#4).

    The checkout is protected unconditionally, here rather than by the caller. It used to arrive only
    as the default value of `--project`, so naming any project root at all replaced it and a
    destination inside this checkout became writable — the one root every run of this command has
    (GC#0 through `--project`). `--project` adds roots; it never takes this one away."""
    roots = [root for root in (state_root, user_root, checkout) if root]
    for group in (native_roots or {}).values():
        roots += list(group.values()) if isinstance(group, dict) else []
    # `host_homes=None` means "the homes as configured", resolved through the one helper. Every
    # production caller leaves it unset: passing a list was how three call sites each carried
    # `NATIVE`'s defaults and none of them saw `CODEX_HOME` or `CLAUDE_CONFIG_DIR` (R2#1).
    roots += list(globals()["host_homes"](environ, repo) if host_homes is None else host_homes)
    # Deduplicated: the checkout is also a project root of every default run, and one root named
    # twice reported the same overlap twice.
    return list(dict.fromkeys(pathlib.Path(root).expanduser() for root in roots))


def overlap_problems(destinations, roots, enclosing=True, home=None):
    """A destination inside — or, with `enclosing`, holding — a protected root, before a byte is
    written. A run directory under the owner's home is fine; one under the state root or a host home
    is not, and the old code found that out after three writes had landed (GA#3).

    `enclosing=False` is for the system temp directory, which the frozen copy is made under: a
    fixture state placed in the same temp directory is not a reason to refuse, while a temp
    directory that sits *inside* the owner's state root still is."""
    problems = []
    for destination in destinations:
        destination = pathlib.Path(destination).expanduser().resolve()
        for root in roots:
            root = root.resolve()
            inside = destination == root or destination.is_relative_to(root)
            holds = enclosing and root.is_relative_to(destination)
            if inside or holds:
                # "which this inventory reads" was the old wording, and it is not what protection
                # means: a root is protected because it is the owner's, read on this run or not.
                problems.append(f"PROTECTED_OVERLAP {masked(destination, home)}: it "
                                f"{'holds' if holds and not inside else 'is inside'} {masked(root, home)}, "
                                f"which this inventory must not write into; nothing is written")
    return problems


RUN_MARKERS = ("run.json", "amendments.jsonl")


def declared_run_at(path):
    """Whether `path` is the directory of a declared run: `run.json` and the log that authorizes it.

    Both files, not either: a directory holding only one of them is not a run this command may
    assume anything about, and `records.declaration_state` is the authority on what a declared run
    is — this asks only whether one is THERE, which is a destination question."""
    path = pathlib.Path(path)
    return all((path / name).is_file() for name in RUN_MARKERS)


def standalone_problems(out_dir, home=None):
    """Why a standalone `--to` destination may not be written, before anything is written.

    `--to` writes `inventory/<reference>.json` and enters no stage: no lock, no stage record, no
    declaration is read. Pointed at a declared run it replaced that run's artifacts through
    `os.replace` while the run's own S2 record went on describing the bytes it had just overwritten —
    census-backed native content replaced by unknowns, with nothing in the run saying so (GC#3 by
    another route). A run's inventory is written through the run-aware path, which records the stage,
    or not at all.

    A destination that already holds an inventory is refused for the same reason one level down: the
    documents there were produced by some other call whose record this one neither reads nor
    replaces."""
    out_dir = pathlib.Path(out_dir).expanduser().resolve()
    advice = "write a run's inventory with --run-id, which enters the stage and records it"
    problems = []
    if declared_run_at(out_dir):
        problems.append(f"RUN_DESTINATION {masked(out_dir, home)}: it is a declared run directory; {advice}")
    else:
        for parent in out_dir.parents:
            if declared_run_at(parent):
                problems.append(f"RUN_DESTINATION {masked(out_dir, home)}: it is inside the declared run "
                                f"directory {masked(parent, home)}; {advice}")
                break
    present = sorted((out_dir / "inventory").glob("*.json")) if (out_dir / "inventory").is_dir() else []
    if present:
        problems.append(f"INVENTORY_PRESENT {masked(out_dir, home)}: it already holds {len(present)} "
                        f"inventory document(s), which this call would replace without reading or "
                        f"recording what produced them; name a destination that holds none")
    return problems


@contextlib.contextmanager
def no_bytecode():
    """No `.pyc` for the modules loaded by path: a cache write lands beside the file it caches, and
    the catalog and the store are read out of the checkout and out of frozen copies (GA#3)."""
    kept = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = kept


# Bytecode caches, which a copy of a checkout must not carry. Git CAN track a `.pyc` — nothing stops
# anyone committing one — so this is not a claim about what is trackable; it is this repository's
# arrangement (every `.gitignore` here excludes them) plus the one property `checkout_copy` exists
# for: the copy is UNCACHED, and a copy that carries a `.pyc` is the one thing it was built not to be.
# Excluded in BOTH branches of `tracked_paths`, so the copy is uncached by construction either way
# rather than because `git ls-files` happens not to name one here.
BYTECODE_CACHE_PARTS = ("__pycache__",)
BYTECODE_CACHE_SUFFIXES = (".pyc", ".pyo")


def is_bytecode_cache(relative):
    """Whether a path relative to a tree root is a bytecode cache or sits in one."""
    parts = pathlib.PurePosixPath(relative).parts
    return bool(set(parts) & set(BYTECODE_CACHE_PARTS)) or relative.endswith(BYTECODE_CACHE_SUFFIXES)


def tracked_paths(source=REPO, git_env=None, git_timeout=entry.TIMEOUT):
    """The files of `source`, whether it is a checkout or a tree materialised from one — by the same
    rule the payload gate keeps (`gates/check-package.sh` `tracked_files`), plus one exclusion.

    A checkout lists what git tracks. A materialised tree has no `.git`, so it is walked. What decides
    is the presence of `.git`, not whether `git` can be run: the commit hook runs the gates in such a
    snapshot with `GIT_DIR` exported, so `git ls-files` there answers about the REAL index and would
    name files that are not in the tree under judgement.

    **A materialised tree holds nothing else only until something runs in it, and the hook runs
    every gate there.** Neither `.githooks/pre-commit` nor `gates/check-parity.sh` sets
    `PYTHONDONTWRITEBYTECODE`, and the legs before this one import Python in that same tree — so by
    the time this is asked, the snapshot carries `__pycache__/*.pyc` in several directories. The walk
    returned them, `checkout_copy` copied them, and the copy's own "it is uncached" control failed
    inside the hook and nowhere else.

    Bytecode caches are therefore excluded from BOTH branches (`is_bytecode_cache`). Not because git
    cannot track one — it can — but because the one property a copy of a checkout is taken for is
    that it is uncached, and that must not depend on which branch answered."""
    source = pathlib.Path(source)
    if (source / ".git").exists():
        # The one child this function starts, bounded like every other: a `git` that never returns
        # hung the walk with nothing to read, and `check=True` turns a failure into an exception but
        # says nothing about a child that simply does not finish (r3 #8). `spawn` is injectable so a
        # control hands it a PATH whose `git` sleeps. The executor is spelled as the direct
        # callee: passed as a value — `(spawn or subprocess.Popen)(...)` — it is a program the
        # closure judge never sees, which is a shape that judge is for (G5).
        listing = bounded_child(lambda: subprocess.Popen(
            ["git", "-C", str(source), "ls-files", "-z"], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=True,
            env=git_env if git_env is not None else dict(os.environ)),
            timeout=git_timeout, what="git ls-files over the tree being copied")
        if listing.returncode != 0:
            # The timeout is NAMED here rather than left to be read out of the child's stderr: the
            # window is the last 200 characters, and the cleanup lines after it can push the fact
            # out of view. A control that reads a window is a control about the window.
            why = ("CHILD_TIMEOUT: it never answered" if listing.returncode == entry.TIMED_OUT
                   else f"code={listing.returncode}")
            raise Refused(f"TREE_UNLISTABLE: git could not list {masked(source)} ({why}); no copy is "
                          f"made from a listing this run does not have: "
                          f"{projected(listing.stderr.strip()[-200:], None)}")
        return [name for name in listing.stdout.split("\0") if name and not is_bytecode_cache(name)]
    names = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source).as_posix()
        if ".git" in path.relative_to(source).parts or is_bytecode_cache(relative):
            continue
        names.append(relative)
    return names


def checkout_copy(destination, source=REPO):
    """An uncached COPY of a checkout under `destination`: the files it tracks, and nothing else.

    The bytecode question is about a tree nobody has imported from yet, and it has to be asked of a
    tree this test owns. Asking it of the review checkout meant deleting that checkout's caches to
    make the question meaningful — a write into the very tree the run is supposed not to write to,
    and one that only cleared two of the directories the command loads from (GC#10). A bytecode cache
    is never a tracked file and `tracked_paths` never returns one, so the copy is uncached by
    construction whatever state the source is in; the caller asserts that before it runs anything."""
    destination, source = pathlib.Path(destination), pathlib.Path(source)
    copied = []
    for name in tracked_paths(source):
        member = source / name
        if member.is_symlink() or not member.is_file():
            continue
        target = confined(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(member.read_bytes())
        copied.append(name)
    _COPIES.add(str(destination.resolve()))
    return copied


# The copy roots THIS PROCESS made with `checkout_copy`. `copied_member` admits no other root, so
# "a closure file inside a copy of this checkout" is a fact about what ran, not a claim about a
# path's shape (R2#5).
_COPIES = set()
# The members a control may run or load from such a copy, and nothing else: the driver, as
# production runs it; the redaction floor, which the bytecode control's positive leg loads by path
# with the no-bytecode guard off; and this module, whose own entry point the boundary-bootstrap
# control runs as a production command from a copy with `runlib/entry.py` broken (r3 #2).
COPIED_MEMBERS = ("session-distill/distill.py", "learn/redact.py",
                  "session-distill/runlib/inventory.py")


def copied_member(copy_root, member):
    """The path of one closure member inside a tree `checkout_copy` produced — or a refusal.

    This is the OWNER of "the program is a closure file in a copy of this checkout", and
    `runlib/dispatch.py` admits a copy-run only where the program expression IS a call of this
    function. The admission used to rest on guard text somewhere in the same file, so a run of
    `os.environ['OTHER_SCRIPT']` added to that file would have been admitted too (R2#5).

    Three refusals, each of which something had to be able to get wrong: a member this is not for, a
    root this process did not copy, and a member name that would leave the copy (`confined`)."""
    if member not in COPIED_MEMBERS:
        raise Refused(f"COPY_MEMBER_UNKNOWN {member!r}: a copy-run names one of {list(COPIED_MEMBERS)}")
    root = pathlib.Path(copy_root)
    if str(root.resolve()) not in _COPIES:
        raise Refused(f"COPY_UNVERIFIED {masked(root)}: this process did not make that copy")
    return confined(root, member)


def loads_outside_the_guard(source):
    """Every `exec_module` in this module's own source that is not lexically inside a
    `with no_bytecode():` block. A flag that is set in one place and the loads that must sit under
    it are two facts, and only the second one is what keeps a `.pyc` out of a frozen copy (GA#3)."""
    tree = ast.parse(source)
    guarded = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With) and any(
                isinstance(item.context_expr, ast.Call) and getattr(item.context_expr.func, "id", None) == "no_bytecode"
                for item in node.items):
            guarded.append((node.body[0].lineno, node.end_lineno))
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "exec_module":
            if not any(start <= node.lineno <= end for start, end in guarded):
                problems.append(f"LOAD_UNGUARDED line {node.lineno}: a module is loaded by path outside "
                                f"`with no_bytecode():`, so the load may write a .pyc beside its source")
    return problems


def freeze(sources, destination, boundary=None):
    """Copy each existing `(source, relative)` into `destination` and say what was left out.

    The copies are what the producers read: the store's public methods lock the state root and
    recover pending transactions, and a read of the owner's library may not write to it. Every
    input passes `linked_above` first and every directory is copied through `walk_source`, so the
    bytes that land here are exactly the bytes the input manifest says were read — a link is omitted
    by name rather than followed, at the input's own path and at every component of it below the
    declared root `boundary` (GB#8, GC#7)."""
    destination = pathlib.Path(destination)
    missing = []
    for source, relative in sources:
        source = pathlib.Path(source).expanduser()
        target = confined(destination, relative)
        if linked_above(source, boundary) is not None:
            missing.append(f"{relative}: symlink")
            continue
        if source.is_dir():
            readable, omitted = walk_source(source, boundary)
            for inner, path in readable:
                inner_target = confined(target, inner)
                try:
                    admitted = source_selection(path, boundary or source)
                except Refused as exc:
                    missing.append(f"{relative}/{inner}: not admitted: {exc}")
                    continue
                inner_target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    inner_target.write_bytes(admitted.read_bytes())
                except OSError as exc:
                    missing.append(f"{relative}/{inner}: {projected_message(exc)}")
            missing += [f"{relative}/{row['path']}: {row['reason']}" for row in omitted]
        elif source.is_file():
            try:
                admitted = source_selection(source, boundary)
            except Refused as exc:
                missing.append(f"{relative}: not admitted: {exc}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(admitted.read_bytes())
        else:
            missing.append(relative)
    return missing


def store_module(repo):
    """The shipped `compose/instructions_store.py`, loaded by path so a checkout under test is the
    one that answers."""
    path = pathlib.Path(repo) / "compose" / "instructions_store.py"
    if not path.is_file():
        raise Refused(f"PRODUCER_UNAVAILABLE {path}: this producer needs the shipped store")
    spec = importlib.util.spec_from_file_location("instructions_store_frozen", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(pathlib.Path(repo) / "compose"))
    with no_bytecode():
        spec.loader.exec_module(module)
    return module


def store_of(repo, state_root, user_root):
    """The store pointed at frozen copies. Only its non-locking internals are called."""
    module = store_module(repo)
    return module, module.InstructionsStore(pathlib.Path(repo), state_root=state_root, user_root=user_root)


# ---------------------------------------------------------------- the producers

def catalog_carriers(tree, layer="catalog", adopted=False):
    """Rules, guides, skills, hooks and agents of a checkout's catalog, through the shipped loader.
    `adopted=True` keeps the items an adopted package brought instead of the core ones."""
    tree = pathlib.Path(tree)
    path = tree / "compose" / "instructions_catalog.py"
    if not path.is_file():
        raise Refused(f"PRODUCER_UNAVAILABLE {masked(path)}: the catalog producer needs the shipped loader")
    spec = importlib.util.spec_from_file_location("instructions_catalog_frozen", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(tree / "compose"))
    with no_bytecode():
        spec.loader.exec_module(module)
        catalog = module.load_catalog(tree)
    core = core_package_id(tree, catalog)
    rows = []
    for item in catalog["items"]:
        if (item.get("package_id") != core) != adopted:
            continue
        rows += item_carriers(item, layer)
    return rows


def core_package_id(tree, catalog):
    """The package the checkout itself publishes; every other item of its catalog was adopted.
    `compose/domains.json` is that package's authority (AGENTS.md), and an external package root
    declares its own id in `manifest.json`."""
    for relative, key in (("compose/domains.json", "package_id"), ("manifest.json", "package_id")):
        path = pathlib.Path(tree) / relative
        if path.is_file():
            declared = json.loads(path.read_text(encoding="utf-8")).get(key)
            if isinstance(declared, str):
                return declared
    packages = catalog.get("packages") or []
    return packages[0].get("package_id") if len(packages) == 1 and isinstance(packages[0], dict) else None


def item_carriers(item, layer):
    """One carrier per member of a catalog, baseline or snapshot item. A rule is one bullet line,
    which is all the compiler takes from it; every other kind carries its member files."""
    if item["kind"] == "rule":
        return [carrier(layer, "claude/CLAUDE.md", item["body"], item["ref"], item.get("package_id"))]
    members = item.get("members") or {}
    # `primary_member` is the catalog's field; the store's normalized items carry their members
    # without it, so it orders the members when it is there and nothing when it is not.
    primary = item.get("primary_member")
    if not isinstance(members, dict) or not members:
        return [carrier(layer, item.get("origin", {}).get("source_path") or primary or f"{item['ref']}",
                        item.get("body") or "", item["ref"], item.get("package_id"))]
    rows = []
    for member, content in sorted(members.items(), key=lambda kv: (kv[0] != primary, kv[0])):
        base = MEMBER_BASE.get(item["kind"])
        relative = member.split("/", 1)[1] if base and "/" in member else member
        path = f"{base}/{relative}" if base else member
        rows.append(carrier(layer, path, content, item["ref"], item.get("package_id")))
    return rows


def overlay_carriers(repo, state_root, user_root, host=None):
    """The owner's overlays as the store resolves its effective items, over frozen copies and
    through the store's own non-locking internals (`_effective_items`), never a method that locks,
    recovers or writes. Only the items the owner's state adds or replaces are this layer; the
    baseline items under them are the release's."""
    module, store = store_of(repo, state_root, user_root)
    runtime, user = store._runtime_state(), store._user_state()
    hosts = list(host) if isinstance(host, (list, tuple)) else [host]
    overlaid = set(user.get("items", {})) | set(user.get("overrides", {}))
    by_carrier, baseline_ref = {}, None
    for one in hosts:
        items, _inventory, _defaults, baseline_ref = store._effective_items(runtime, user, host=one)
        for item in items:
            if item["ref"] in overlaid or str(item.get("package_id", "")).startswith("@local"):
                for row in item_carriers(item, "overlays"):
                    kept = by_carrier.setdefault(row["carrier_id"], row)
                    kept["provenance"].setdefault("hosts", [])
                    if one is not None and one not in kept["provenance"]["hosts"]:
                        kept["provenance"]["hosts"].append(one)
    rows = list(by_carrier.values())
    return rows, baseline_ref, {"personal_items": len(user.get("items", {})),
                                "overrides": len(user.get("overrides", {})),
                                "tombstones": len(user.get("tombstones", {})),
                                "hosts_resolved": [one for one in hosts if one is not None],
                                "learning_suppressions": {one: len(rowset) for one, rowset
                                                          in (user.get("learning_suppressions") or {}).items()}}


def memory_slug(project):
    """A host's directory name for a project root: the path with every other character a dash,
    which is the layout `~/.claude/projects/` uses."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(pathlib.Path(project).expanduser().resolve()))


NATIVE_LAYERS = ("native_global", "native_settings", "native_memory", "native_project")
# The host layers whose text a transcript records, and the attachment `type` each one comes from.
# `native_settings` is in neither map on purpose: no transcript carries a settings file, and no
# mode reads one, so that layer is `unknown` at every reference point (the 1548 amendment §4).
ATTACHMENT_LAYER = {"User": "native_global", "Project": "native_project", "AutoMem": "native_memory"}
TRANSCRIPT_LAYERS = tuple(dict.fromkeys(ATTACHMENT_LAYER.values()))


def native_read_problems(source=None):
    """Any place in this module that would read a host instruction, settings or memory file.

    `NATIVE` stays, because the host homes are protected WRITE targets whether or not anything reads
    them (GA#4). What must not exist is a read: a subscript of a host's layer names, or a glob over
    a home. The native layers come from what a transcript records (the 1548 amendment §5)."""
    source = pathlib.Path(__file__).read_text(encoding="utf-8") if source is None else source
    tree = ast.parse(source)
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                and node.slice.value in ("global", "settings", "memory"):
            inner = node.value
            while isinstance(inner, ast.Subscript):
                inner = inner.value
            if getattr(inner, "id", None) == "NATIVE":
                problems.append(f"NATIVE_FILE_READ line {node.lineno}: a host layer's file names are read "
                                f"from NATIVE, and no mode reads a native file")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) in ("glob", "rglob"):
            for inner in ast.walk(node):
                if getattr(inner, "id", None) == "NATIVE":
                    problems.append(f"NATIVE_FILE_READ line {node.lineno}: a host home is globbed")
    return problems


def project_identities(roots):
    """`{canonical path: {path, slug, present}}` for the project roots a run names.

    A project is its canonical path. Keying it by basename — which is what the driver did — made
    two checkouts called `source` one project, and the memory entries of one the other's (GA#4)."""
    identities = {}
    for root in roots:
        canonical = str(pathlib.Path(root).expanduser().resolve())
        identities[canonical] = {"path": canonical, "slug": memory_slug(canonical),
                                 "present": pathlib.Path(canonical).is_dir()}
    return identities


# ------------------------------------------- the transcript as a reference point (the 1548 amendment)

CENSUS = "census.json"
# §4's table: every `unknown` this module reports names one of these. A reason is data, not prose —
# a layer that goes unknown without one is the silence the whole record exists to refuse.
UNKNOWN_REASONS = {
    "census": "INPUT_UNACQUIRED: this run has no S1 census, so no transcript is bound to a record here",
    "no_record": "unknown: the transcript records no injection",
    "changed": "unknown: the transcript's bytes no longer match its census record",
    "unreadable": "unknown: the transcript could not be read",
    "settings": "unknown: a settings file is carried by no transcript, and none is read",
    "unpinned": "unknown: no pin, so nothing says what this session was selected to receive",
    "ledger_history": "unknown: the ledger records the present, with no per-session history",
    "codex_identity": "unknown: Codex records the loaded text, not the file it was loaded from",
}
SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$")


def safe_label(kind, value):
    """An identifier that may become part of a path, or a refusal naming the kind and not the value.

    A pin's host, session id and `content_ref` are read out of the owner's state, and a copy label
    built from one of them straight is a destination the caller chose (GC#0)."""
    text = str(value)
    if not SAFE_LABEL.match(text):
        raise Refused(f"INPUT_INVALID {kind}: not an identifier this run will build a path from")
    return text


def confined(base, relative):
    """`base / relative`, or a refusal: a copy label is relative, has no traversal, and lands inside
    the destination. The label comes from the owner's state, so it is input, not a constant."""
    base = pathlib.Path(os.path.normpath(str(base)))
    label = str(relative)
    parts = pathlib.PurePosixPath(label).parts
    if label.startswith("/") or ".." in parts or any(part.startswith("/") for part in parts):
        raise Refused(f"DESTINATION_ESCAPES {label!r}: a copy label is relative and holds no traversal")
    target = pathlib.Path(os.path.normpath(str(base / label)))
    # The second line is **unguarded-accepted** (ruled 2026-10-24): for any label the first line
    # admits, `normpath(base / label)` cannot leave `base`, so no fixture reaches it without
    # weakening the first. It stays as the second layer, for the case where that string test is ever
    # narrowed. `base` is normalised above for the same reason the comparison exists: `pathlib` does
    # not normalise, so a base carrying `..` would make this refuse a perfectly valid label. Every
    # caller passes an mkdtemp-derived base today, so that correction needs no control either.
    if target != base and not target.is_relative_to(base):
        raise Refused(f"DESTINATION_ESCAPES {label!r}: it resolves outside the frozen destination")
    return target


# The platform's fixed fallbacks, after the environment's three names. Data, so a control can say
# what it means (`temp_home(candidates=...)`).
TEMP_CANDIDATES = ("/tmp", "/var/tmp")


def temp_home(guarded, home=None, environ=None, candidates=TEMP_CANDIDATES):
    """The directory the frozen copies are made under, chosen and judged before anything writes.

    `tempfile.gettempdir()` PROBES its candidates by creating a file in one, so calling it to decide
    whether a destination is allowed is itself the write the decision exists to prevent (GC#1). This
    reads the environment and the platform's fixed candidates and judges them as paths.

    `environ` is the environment to read, so a control can state the one it means instead of mutating
    this process's own. `candidates` is the platform's fixed list for the same reason: a control can
    state one whose members are absent, which is the only way to reach the exhaustion refusal below
    — on this platform `/var/tmp` always exists, so that refusal had no control at all. Production
    callers pass neither."""
    environ = os.environ if environ is None else environ
    for candidate in [environ.get(name) for name in ("TMPDIR", "TEMP", "TMP")] + list(candidates):
        if not candidate:
            continue
        path = pathlib.Path(candidate).expanduser()
        if not path.is_dir() or path.is_symlink():
            continue
        problems = overlap_problems([path], guarded, enclosing=False, home=home)
        if problems:
            raise Refused("; ".join(problems))
        return path
    raise Refused("TEMP_UNAVAILABLE: no temporary directory outside the protected roots to freeze inputs under")


def scratch_parent(environ=None, home=None, state_root=None, user_root=None, checkout=None):
    """Where a SELF-TEST may create its fixtures, judged by the same path-only rule production uses.

    A self-test writes a great deal: fixture state roots, a copy of the checkout, run directories.
    Both self-tests asked `tempfile` for a parent, which resolves `TMPDIR` by PROBING it — and an
    ordinary `TMPDIR` inside the checkout's own `.tmp`, or inside the owner's state root, then put
    every one of those writes inside a protected root before production's preflight could refuse
    anything (R1#5). The judgement is `temp_home`'s, over the same protected set: the real checkout,
    the configured state and corpus roots, and the host homes.

    It is the SELECTION that is tested, not the suite: a control calls this with a fixture
    environment and reads the refusal, which costs one call rather than a recursive run."""
    state, user = configured_roots(state_root, user_root, environ, home)
    guarded = protected_roots(state, user, {}, checkout=REPO if checkout is None else checkout,
                              environ=environ)
    return temp_home(guarded, home or str(pathlib.Path.home()), environ)


# The suites' in-process depth, counted here rather than in the environment: an environment mark
# travels to children, and after S4 no child runs a suite at all — what can still nest is a control
# that calls `main(["--self-test"])` in this process. Depth 1 is the suite; depth 2 is that control's
# own inner run and must stay allowed; depth 3 means the inner suite reached this control again,
# which is the recursion that filled the disk, and it is refused by name.
SELF_TEST_DEPTH = [0]
SELF_TEST_DEPTH_LIMIT = 2
# The parent the current scratch was created under, for the control that asks where this suite's own
# fixtures went. Read rather than re-derived: a control above it takes `TMPDIR` out of the process's
# environment, so calling the rule again would answer about a different environment.
SELF_TEST_SCRATCH_PARENT = [None]


@contextlib.contextmanager
def self_test_scratch(prefix="wp07-self-test-", environ=None):
    """The ONE place either suite creates anything: its scratch directory, under the judged parent.

    Both suites asked `tempfile` for a parent of their own, and `tempfile` resolves `TMPDIR` by
    PROBING it, so an ordinary `TMPDIR` inside the checkout or the owner's state root put every
    fixture this suite writes inside a protected root (R1#5). Observing that from outside took a
    child process running the whole suite, which is what made recursion possible (S7). One function
    answers both questions in this process instead: it refuses when the judged parent refuses, and
    the directory it returns has that parent.

    Nothing else in either suite may call `tempfile` — `gates`-side the dispatch judge holds that as
    a two-site allow-list, so a second scratch cannot appear without being declared."""
    if SELF_TEST_DEPTH[0] >= SELF_TEST_DEPTH_LIMIT:
        raise Refused(f"SELF_TEST_TOO_DEEP: a suite is already running at depth {SELF_TEST_DEPTH[0]} "
                      f"inside this process and the limit is {SELF_TEST_DEPTH_LIMIT}; the suite that "
                      f"runs a suite is the recursion this bound exists for")
    parent = scratch_parent(environ)
    SELF_TEST_SCRATCH_PARENT[0] = parent
    SELF_TEST_DEPTH[0] += 1
    try:
        with tempfile.TemporaryDirectory(prefix=prefix, dir=str(parent)) as td:
            yield pathlib.Path(td)
    finally:
        SELF_TEST_DEPTH[0] -= 1


def census_entries(run_dir):
    """The transcripts this run's census read, one row per session, as the inventory reads them.

    WP-07 opens no host home. Every transcript byte reaches it through the S1 readers
    (`sources.read_lines`) and is bound to the census record that says what S1 read, so a reference
    point is derived from the same bytes the rest of the run was derived from (the 1548 amendment §5).
    Host instruction, settings and memory files are not read at all, in any mode."""
    path = (pathlib.Path(run_dir) / CENSUS) if run_dir else None
    if path is None or not path.is_file():
        raise Unacquired(UNKNOWN_REASONS["census"])
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for entry in document.get("transcripts") or []:
        version = (entry.get("versions") or [{}])[-1]
        rows.append({"host": entry.get("host"), "id": entry.get("id"), "path": entry.get("path"),
                     "kind": "subagent" if entry.get("status") == "child_of" else "main",
                     "parent": entry.get("parent"), "sha256": entry.get("sha256"),
                     "prefix_sha": version.get("prefix_sha"), "record_count": version.get("record_count"),
                     "pin": (entry.get("pin") or {}).get("content_ref")})
    return rows


def transcript_records(entry, zstd=None):
    """`(records, which bytes)` of one transcript, read through the S1 reader and bound to its census
    record.

    A file whose bytes no longer hash to that record is NOT re-read and not repaired: the session's
    reference points go `unknown` with that reason, because a silent re-read answers about a
    different file than every other stage of the run judged. A transcript the host has grown since —
    append-only, with the census's own complete-line prefix intact — is read up to the census's
    boundary and says so."""
    if not entry.get("path"):
        raise Unacquired(f"{UNKNOWN_REASONS['no_record']} ({entry.get('host')}:{entry.get('id')}): the census row has no path")
    whole, prefix, count, read, tail = hashlib.sha256(), None, 0, [], b""
    try:
        for raw in sources.read_lines(entry["path"], zstd):
            if not raw.endswith(b"\n"):
                tail = raw
                break
            whole.update(raw)
            count += 1
            if entry.get("record_count") == count:
                prefix = whole.hexdigest()
            try:
                record = json.loads(raw)
            except ValueError:
                record = None
            if isinstance(record, dict):
                read.append(record)
    except sources.Unreadable as exc:
        raise Unacquired(f"{UNKNOWN_REASONS['unreadable']}: {projected_message(exc)}") from exc
    whole.update(tail)
    sha = whole.hexdigest()
    if entry.get("sha256") and sha != entry["sha256"]:
        if not (prefix and entry.get("prefix_sha") and prefix == entry["prefix_sha"]):
            raise Unacquired(f"{UNKNOWN_REASONS['changed']} ({sha[:12]} now, {str(entry['sha256'])[:12]} on record)")
        return read[:entry["record_count"]], "the census record's complete lines, the host having appended since"
    return read, "the bytes the census read"


def _instant(text):
    """A record's timestamp as an orderable value; None when it has none."""
    if not isinstance(text, str):
        return None
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _timestamp(record):
    for key in ("timestamp", "ts", "time"):
        if isinstance(record.get(key), str):
            return record[key]
    payload = record.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("timestamp"), str):
        return payload["timestamp"]
    return None


def _located(record, delivered):
    """`(where, how)` the delivered body sits in this record, or None.

    Located by the pin's snapshot text and its hash: the host's field is a LARGER string that holds
    the body (measured 2026-10-23: 23 of 23 recorded sessions, none of them field-exact), so an
    equality test over the field would answer "absent" about a body that is there."""
    if not delivered:
        return None
    places = []
    attachment = record.get("attachment") if isinstance(record.get("attachment"), dict) else {}
    for n, text in enumerate(attachment.get("systemPrompt") or []):
        if isinstance(text, str):
            places.append(("attachment.systemPrompt[]", text))
    shape = record.get("shape") if isinstance(record.get("shape"), dict) else {}
    for block in shape.get("system") or []:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            places.append(("shape.system[].text", block["text"]))
    for where, text in places:
        if text == delivered:
            return where, "the field is the delivered body"
        if delivered in text:
            return where, "the delivered body inside the field"
        if _normalised(delivered) and _normalised(delivered) in _normalised(text):
            return where, "the delivered body inside the field, line endings normalised"
    return None


def _normalised(text):
    """Line endings and trailing whitespace only: the normalisation the match check measured."""
    return "\n".join(line.rstrip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()


def injection_events(records, entry, delivered=None):
    """The injection events one transcript records, in order (the 1548 amendment §1).

    An event is per INJECTION, not per session: the same session is injected again after a compaction
    and the second body is not always the first (measured 2026-10-23: 22 of 84 recorded file entries
    differed from the first). A layer the host does not distinguish stays one carrier — Codex records
    `base_instructions` as one merged block, so no global/project split is derived from it."""
    host, events = entry.get("host"), []
    for n, record in enumerate(records):
        at = _timestamp(record)
        if host == "claude":
            attachment = record.get("attachment") if isinstance(record.get("attachment"), dict) else {}
            if attachment.get("type") == "instructions":
                files = [{"layer": ATTACHMENT_LAYER.get(member.get("type")), "type": member.get("type"),
                          "path": member.get("path"), "text": member.get("content")}
                         for member in attachment.get("files") or []
                         if isinstance(member, dict) and isinstance(member.get("content"), str)]
                if files:
                    events.append({"kind": "native", "host": host, "at": at, "n": n, "files": files,
                                   "session": f"{host}:{entry.get('id')}", "transcript": entry.get("kind"),
                                   "scope": record.get("cwd") if isinstance(record.get("cwd"), str) else None,
                                   "where": "attachment.files[] by type"})
            found = _located(record, delivered)
            if found:
                events.append({"kind": "session_injection", "host": host, "at": at, "n": n,
                               "session": f"{host}:{entry.get('id')}", "transcript": entry.get("kind"),
                               "where": found[0], "how": found[1]})
        elif host == "codex":
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
            base = payload.get("base_instructions") if isinstance(payload.get("base_instructions"), dict) else None
            text = (base or {}).get("text") if base else payload.get("base_instructions")
            if isinstance(text, str) and text.strip():
                events.append({"kind": "native", "host": host, "at": at, "n": n,
                               "session": f"{host}:{entry.get('id')}", "transcript": entry.get("kind"),
                               "scope": (payload.get("cwd") if isinstance(payload.get("cwd"), str) else None),
                               "where": "session_meta.payload.base_instructions",
                               "git": payload.get("git") if isinstance(payload.get("git"), dict) else None,
                               # One undivided block: the global and project parts of it are unknown,
                               # and no estimated split is recorded (the 1548 amendment §1).
                               "files": [{"layer": "native_global", "type": "base_instructions",
                                          "path": "codex:base_instructions", "text": text,
                                          "undivided": True}]})
    return events


def event_in_force(events, when, kind="native"):
    """The event a turn is judged against: the most recent one at or before `when` (§6).

    A turn before every recorded event has an unknown reference point; a later event never answers
    for an earlier turn."""
    moment = _instant(when) if not isinstance(when, datetime.datetime) else when
    best = None
    for event in events:
        if event["kind"] != kind:
            continue
        at = _instant(event.get("at"))
        if moment is not None and at is not None and at > moment:
            continue
        if moment is not None and at is None:
            continue
        if best is None or (_instant(best.get("at")) or _instant("1970-01-01T00:00:00+00:00")) <= (at or _instant("1970-01-01T00:00:00+00:00")):
            best = event
    return best


def current_sets(events):
    """§8: per layer AND SCOPE, the whole file set of the newest recorded event, labelled `as_of`.

    Never per path. Taking the newest event for each path separately would keep a file alive forever
    after it was deleted, because no later event mentions a file that is gone; a whole-set answer
    lets a deletion show as a deletion.

    Only MAIN transcripts feed this. A subagent's injection can omit a layer by agent type — some
    built-in agent types load no `CLAUDE.md` — so a subagent event would make a present layer look
    absent. Subagent transcripts keep their own past reference points (§6)."""
    newest = {}
    for event in events:
        if event["kind"] != "native" or event.get("transcript") != "main":
            continue
        at = _instant(event.get("at"))
        for layer in {member["layer"] for member in event["files"] if member["layer"]}:
            key = (layer, event.get("scope") or event.get("host"))
            held = newest.get(key)
            if held is None or (at is not None and (_instant(held.get("at")) is None or at > _instant(held.get("at")))):
                newest[key] = event
    return newest


def event_carriers(layer, event, reference):
    """One event's files for one layer, as carriers, each carrying when and from whom it came."""
    rows = []
    for member in event["files"]:
        if member["layer"] != layer:
            continue
        provenance = {"as_of": event.get("at"), "session": event.get("session"),
                      "transcript": event.get("transcript"), "where": event.get("where"),
                      "scope": masked(event.get("scope")) if event.get("scope") else None,
                      "reference": reference, "record": event.get("n")}
        if member.get("undivided"):
            # Codex delivers one merged body, so the layer's identity is unknown and only the
            # loaded text is known (§2, design §6.3's Native layer row).
            provenance["identity"] = UNKNOWN_REASONS["codex_identity"]
        rows.append(carrier(layer, f"{event['host']}:{member.get('type')}:{member.get('path')}",
                            member["text"], provenance=provenance, form="md"))
    return rows


def transcript_events(run_dir, delivered=None, zstd=None):
    """Every injection event the run's census-bound transcripts record, with the rows that failed.

    A session whose bytes moved, or that records no injection, is a NAMED unknown here rather than a
    silence: the reasons are what every layer status below is built from."""
    entries = census_entries(run_dir)
    events, unknown = [], []
    for entry in entries:
        try:
            records_read, which = transcript_records(entry, zstd)
        except Unacquired as exc:
            unknown.append(f"{entry.get('host')}:{entry.get('id')}: {exc}")
            continue
        found = injection_events(records_read, entry, delivered)
        if not found:
            unknown.append(f"{entry.get('host')}:{entry.get('id')}: {UNKNOWN_REASONS['no_record']} ({which})")
        events += found
    return events, unknown


KEEP_ACTIVE = ("placed",)  # the ledger's own lifecycle states in which a keep record still stands


def ledger_carriers(ledger, layer, notes=None):
    """The ledger layer (§6.1): the incubating principles, and the `keep` records still standing.
    Schema 1 and schema 2 both carry a status and the text; a schema this does not read is the
    layer's own `incomplete` reason, never a silent empty.

    A keep record is not a keep. The ledger retires, absorbs and reverts entries while the `keep`
    field stays on the row as history, so admitting any truthy `keep` delivered retired rules as
    live ones. Eligibility is the entry's lifecycle state, and the units the keep protects travel
    with the carrier as provenance instead of being dropped on the floor (GA#9). Every entry held
    back is named in `notes`, because a layer that quietly shrinks is the failure this inventory
    exists to make visible."""
    version = ledger.get("schema")
    if version not in (1, 2):
        raise Refused(f"LEDGER_SCHEMA_UNSUPPORTED schema {version!r}: the inventory reads schema 1 and 2")
    rows, held_back = [], []
    for entry in ledger.get("entries", []):
        text = entry.get("principle") or entry.get("lesson") or ""
        status = str(entry.get("status", ""))
        if layer == "ledger_incubating" and status.startswith("incubating") and text:
            rows.append(carrier(layer, f"{LEDGER_REL}#{entry['id']}", text, entry["id"],
                                provenance={"status": status}))
        if layer == "ledger_keep" and entry.get("keep"):
            keep = entry["keep"] if isinstance(entry["keep"], dict) else {}
            reason = None
            if not text:
                reason = "the entry carries no principle or lesson text"
            elif entry.get("absorbed_by"):
                reason = f"absorbed by {entry['absorbed_by']}, whose own entry carries the keep now"
            elif status not in KEEP_ACTIVE:
                reason = f"status {status!r} is not one of {list(KEEP_ACTIVE)}"
            if reason:
                held_back.append({"id": entry.get("id"), "status": status, "reason": reason,
                                  "keep_units": keep.get("units", [])})
                continue
            rows.append(carrier(layer, f"{LEDGER_REL}#{entry['id']}", text, entry["id"],
                                provenance={"status": status, "keep_units": list(keep.get("units", [])),
                                            "keep_reason": entry.get("reason")}))
    if notes is not None and layer == "ledger_keep":
        notes["ledger_keep_held_back"] = held_back
    return rows


def baseline_items(state_root, ref):
    """A baseline's own item list — the release reference point's carriers, and the expected set
    done-when 1 judges the mapping against, read from the file rather than from the mapping."""
    path = pathlib.Path(state_root).expanduser() / "runtime" / "baselines" / ref / "inventory.json"
    if not path.is_file():
        raise Refused(f"BASELINE_ABSENT {masked(path)}: the release reference point has no baseline inventory")
    document = json.loads(read_source(path, state_root))
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise Refused(f"BASELINE_EMPTY {masked(path)}: a baseline inventory with no items judges nothing")
    return items


def read_pin(state_root, host, session_id):
    """A pin, read as a file: the content ref it names is what the snapshot is frozen by."""
    pin_path = pathlib.Path(state_root).expanduser() / "sessions" / "pins" / host / f"{session_id}.json"
    if not pin_path.is_file():
        raise Refused(f"PIN_ABSENT {masked(pin_path)}: the selection reference point needs the session's pin")
    pin = json.loads(read_source(pin_path, state_root))
    if not isinstance(pin.get("content_ref"), str):
        raise Refused(f"PIN_UNREADABLE {masked(pin_path)}: the pin names no content_ref")
    return pin


def snapshot_of(repo, frozen_state, content_ref):
    """A pin's snapshot over the frozen copy, through the store's own `verify_snapshot` — a
    module-level reader that takes no lock and writes nothing, unlike `snapshot_inventory`.

    The store reads the snapshot's files itself, so the selection is taken here, before it is
    handed the root: nothing the store reads is admitted by a decision made after the read."""
    root = source_selection(pathlib.Path(frozen_state) / "sessions" / "snapshots" / content_ref, frozen_state)
    return store_module(repo).verify_snapshot(root, content_ref)


# ---------------------------------------------------------------- the layer table

def layer_rows(reference, context):
    """The layer/producer table: one row per §6.1 layer for this reference point, with the producer
    named and its carriers, or the status and reason that make the reference point incomplete.

    This table decides what a complete reference point is, so every row is data and every row is
    answered: a layer with no producer here is `unknown` or `unsupported`, never absent and never
    silently empty."""
    rows = []
    context["reference"] = reference   # the producers answer per reference point, not per call site
    for layer, producers in LAYERS:
        producer = producers.get(reference)
        if producer is None:
            rows.append({"layer": layer, "producer": None, "status": "unknown", "carriers": [],
                         "reasons": [f"{layer} has no record at the {reference} reference point"]})
            continue
        if context.get("acquisition_error"):
            rows.append({"layer": layer, "producer": producer[0], "status": "unknown", "carriers": [],
                         "reasons": [f"{layer}: {context['acquisition_error']}"]})
            continue
        # A reason goes in RAW. `LAYER_ROW_TABLE`'s `list_of(as_metadata())` is the one thing that
        # projects it, so a reason added here cannot reach the artifact unprojected, and no site
        # holds a second copy of the projection rule (found during S1).
        name, call = producer
        try:
            carriers = call(context)
        except Unacquired as exc:
            rows.append({"layer": layer, "producer": name, "status": "unknown", "carriers": [],
                         "reasons": [f"{layer}: {exc}"]})
            continue
        except Unsupported as exc:
            rows.append({"layer": layer, "producer": name, "status": "unsupported", "carriers": [],
                         "reasons": [f"{layer}: {exc}"]})
            continue
        except Malformed as exc:
            rows.append({"layer": layer, "producer": name, "status": "incomplete", "carriers": [],
                         "reasons": [f"{layer}: {exc}"]})
            continue
        except Exception as exc:  # a producer that cannot read its input leaves a status, not a traceback
            rows.append({"layer": layer, "producer": name, "status": "incomplete", "carriers": [],
                         "reasons": [f"{layer}: {projected_message(exc, context.get('home'))}"]})
            continue
        if carriers is None:
            rows.append({"layer": layer, "producer": name, "status": "unknown", "carriers": [],
                         "reasons": [f"{layer}: {name} found no record of this layer"]})
            continue
        rows.append({"layer": layer, "producer": name, "status": "complete", "carriers": carriers, "reasons": []})
    return rows


def produce(rows):
    """Split every layer's carriers into units, and hold each layer against its own non-empty
    assertion: a producer that ran and yielded nothing is `incomplete`, never clean."""
    units = []
    for row in rows:
        row["empty"] = False
        if row["status"] != "complete":
            row["units"] = 0
            continue
        if not row["carriers"]:  # the producer looked and this layer has nothing: an answer, stated
            row.update(units=0, empty=True)
            continue
        try:
            produced = units_of(row["carriers"])
        except Unsupported as exc:
            row.update(status="unsupported", units=0, reasons=row["reasons"] + [f"{row['layer']}: {exc}"])
            continue
        except Malformed as exc:
            row.update(status="incomplete", units=0, reasons=row["reasons"] + [f"{row['layer']}: {exc}"])
            continue
        row["units"] = len(produced)
        if not produced:
            row.update(status="incomplete", reasons=row["reasons"] + [
                f"{row['layer']}: {row['producer']} read {len(row['carriers'])} carrier(s) and produced no unit, "
                f"and a layer is never silently empty"])
            continue
        units += produced
    for row in rows:
        row.pop("carriers", None)
    return units


# ---------------------------------------------------------------- the reference points

def context_of(repo, state_root, user_root, native_roots, pin, ledger):
    return {"repo": repo, "state_root": state_root, "user_root": user_root, "native_roots": native_roots,
            "frozen_native": {}, "pin": pin, "ledger": ledger, "notes": {},
            # The home every artifact is masked against, declared once rather than per call site.
            "home": str(pathlib.Path.home())}


def hosts_in_scope(ctx):
    """The hosts this run has transcript evidence for: the hosts of the events it bound. A host with
    no event is a declared omission, never an empty answer."""
    hosts = sorted({event["host"] for event in (ctx.get("events") or [])})
    ctx["notes"]["hosts_in_scope"] = {"hosts": hosts, "from": "the census-bound transcripts' events"}
    return hosts


def overlay_hosts(ctx):
    """The hosts the OVERLAY layer resolves for: every host the store keeps a journal for.

    This is a different scope from the native capture. A learned rule lives in the owner's corpus
    whether or not that host's home was handed to this run, and the store reads a journal only when
    it is told which host — so resolving for the captured homes alone would drop the other host's
    learned rules as silently as passing no host at all did (GA#7)."""
    hosts = list(NATIVE)
    ctx["notes"]["overlay_hosts"] = hosts
    return hosts


def _catalog_current(ctx):
    return catalog_carriers(ctx["repo"])


def adopted_items(items, core):
    """The items of a package the owner adopted: neither the core package's nor a personal one's."""
    return [item for item in items
            if item.get("package_id") and item["package_id"] != core
            and not str(item["package_id"]).startswith("@local")]


def _packages_current(ctx):
    """Adopted packages as the owner's own state records them.

    The checkout's catalog cannot answer this: `load_catalog` returns one root's catalog and every
    item in it carries that root's package id, so filtering it for "not the core package" read
    `complete, empty` without ever consulting an adoption (GA#6). What the owner adopted is in the
    installed state, which the store resolves over the frozen copy."""
    if ctx["state_root"] is None:
        raise Refused("PRODUCER_UNAVAILABLE adopted_packages: the adoption record is in the owner's state, "
                      "and this run was given no state root")
    module, store = store_of(ctx["repo"], ctx["state_root"], ctx["user_root"])
    runtime, user = store._runtime_state(), store._user_state()
    # Adoption is not a host's property: the item set the owner installed is the same for both, so
    # this resolves hostless and leaves the per-host journals to the overlay layer.
    items, _inventory, _defaults, _ref = store._effective_items(runtime, user, host=None)
    core = core_package_id(ctx["repo"], {"packages": []})
    rows = adopted_items(items, core)
    ctx["notes"]["adopted_packages"] = {"core": core, "adopted": sorted({item["package_id"] for item in rows})}
    return [row for item in rows for row in item_carriers(item, "adopted_packages")]


def _packages_release(ctx):
    """The packages the release itself carried, from the baseline's own item list."""
    if not ctx.get("release_ref"):
        return None  # no baseline names this reference point, so this layer has no record here
    core = core_package_id(ctx["repo"], {"packages": []})
    rows = adopted_items(ctx["expected_release_items"], core)
    return [row for item in rows for row in item_carriers(item, "adopted_packages")]


def _packages_selection(ctx):
    snapshot = _selection(ctx)
    if snapshot is None:
        return None
    core = core_package_id(ctx["repo"], {"packages": []})
    return [row for item in adopted_items(snapshot["items"] or [], core)
            for row in item_carriers(item, "adopted_packages")]


def _overlays_current(ctx):
    # Every host in scope, not the default resolution: the store reads a host's learning journal
    # only when it is told which host, so the hostless call silently dropped every learned rule
    # the owner's own sessions had added (GA#7).
    rows, baseline_ref, counts = overlay_carriers(ctx["repo"], ctx["state_root"], ctx["user_root"],
                                                  host=overlay_hosts(ctx))
    ctx["notes"]["installed_baseline_ref"] = baseline_ref
    ctx["notes"]["overlay_counts"] = counts
    return rows


def _native(layer):
    """A native layer at a reference point, from what a transcript records as delivered.

    `current` is §8's newest recorded event per scope; `selection` is the event in force at the
    pinned session's own activation, read from that session's transcript. No native file is read."""
    def produce_native(ctx):
        if layer == "native_settings":
            raise Unacquired(UNKNOWN_REASONS["settings"])
        if ctx.get("transcript_error"):
            raise Unacquired(ctx.get("transcript_error") or UNKNOWN_REASONS["census"])
        reference = ctx["reference"]
        if reference == "current":
            chosen = {key: event for key, event in (ctx.get("current_sets") or {}).items() if key[0] == layer}
            if not chosen:
                raise Unacquired(f"{UNKNOWN_REASONS['no_record']}: no main transcript records {layer}")
            rows = []
            for (_layer, scope), event in sorted(chosen.items(), key=lambda row: str(row[0][1])):
                rows += event_carriers(layer, event, reference)
            return rows
        if reference == "selection":
            if not ctx.get("pin"):
                raise Unacquired(UNKNOWN_REASONS["unpinned"])
            event = ctx.get("pin_event")
            if event is None:
                raise Unacquired(f"{UNKNOWN_REASONS['no_record']}: the pinned session's transcript records no injection")
            rows = event_carriers(layer, event, reference)
            if not rows:
                raise Unacquired(f"{UNKNOWN_REASONS['no_record']}: the event in force records no {layer}")
            return rows
        return None
    return produce_native


def _ledger_history(ctx):
    """A ledger layer at a past reference point. The ledger records the present, so a session's own
    ledger state is not recoverable — and that is a named unknown, not an empty layer."""
    raise Unacquired(UNKNOWN_REASONS["ledger_history"])


def _ledger(layer):
    def produce_ledger(ctx):
        if ctx["ledger"] is None:
            return None  # no ledger was handed in: this layer has no record here
        return ledger_carriers(ctx["ledger"], layer, ctx["notes"])
    return produce_ledger


def _release_catalog(ctx):
    if not ctx.get("release_ref"):
        return None  # no pin and no installed baseline: this reference point has no record
    return [row for item in baseline_items(ctx["state_root"], ctx["release_ref"]) for row in item_carriers(item, "catalog")]


def _selection(ctx):
    """The pin's snapshot, or None when no pin names one (§6.3: no pin, no selection evidence)."""
    return ctx.get("snapshot")


def _selection_catalog(ctx):
    snapshot = _selection(ctx)
    return None if snapshot is None else [row for item in snapshot["items"] for row in item_carriers(item, "catalog")]


def _selection_injection(ctx):
    snapshot = _selection(ctx)
    if snapshot is None:
        return None
    text = snapshot["output"].get("instruction_text") or ""
    return [carrier("session_injection", f"snapshot:{snapshot['content_ref']}/output.json#instruction_text",
                    text, form="markdown")] if text else []


def _selection_overlays(ctx):
    snapshot = _selection(ctx)
    if snapshot is None:
        return None
    local = [item for item in snapshot["items"] if str(item.get("package_id", "")).startswith("@local")]
    return [row for item in local for row in item_carriers(item, "overlays")]


# layer -> reference point -> (producer name, producer). A reference point a layer has no producer
# for is `unknown` by the table itself (§6.1: historical overlays and native layers are unknown
# unless recorded), which makes that reference point incomplete.
LAYERS = (
    ("catalog", {"current": ("checkout catalog (compose/instructions_catalog.load_catalog)", _catalog_current),
                 "release": ("baseline inventory (runtime/baselines/<ref>/inventory.json)", _release_catalog),
                 "selection": ("pinned snapshot items (sessions/snapshots/<content_ref>)", _selection_catalog)}),
    ("adopted_packages", {"current": ("the owner's installed state, items of an adopted package", _packages_current),
                          "release": ("baseline inventory, items of an adopted package", _packages_release),
                          "selection": ("pinned snapshot items of an adopted package", _packages_selection)}),
    ("overlays", {"current": ("instructions_store._effective_items over frozen copies", _overlays_current),
                  "selection": ("pinned snapshot items of @local packages", _selection_overlays)}),
    # The native layers are what a transcript records as delivered: §8's newest recorded event per
    # scope for `current`, and the pinned session's own event for `selection`. No file is read.
    ("native_global", {"current": ("the newest recorded instructions attachment, User entry", _native("native_global")),
                       "selection": ("the pinned session's recorded instructions attachment, User entry", _native("native_global"))}),
    ("native_project", {"current": ("the newest recorded instructions attachment, Project entry", _native("native_project")),
                        "selection": ("the pinned session's recorded instructions attachment, Project entry", _native("native_project"))}),
    ("native_settings", {"current": ("no producer: a settings file is carried by no transcript", _native("native_settings")),
                         "selection": ("no producer: a settings file is carried by no transcript", _native("native_settings"))}),
    ("native_memory", {"current": ("the newest recorded instructions attachment, AutoMem entry", _native("native_memory")),
                       "selection": ("the pinned session's recorded instructions attachment, AutoMem entry", _native("native_memory"))}),
    # Session-level injection exists per session, so "all layers now" can only mean the injection
    # the session being diagnosed received: with a pin, the snapshot's compiled text answers for
    # `current` too; without one there is nothing to read and the layer is `unknown`.
    ("session_injection", {"current": ("the pinned session's compiled instruction text", _selection_injection),
                           "selection": ("the snapshot's compiled instruction text", _selection_injection)}),
    ("ledger_incubating", {"current": ("the ledger's incubating entries (schema 1 or 2)", _ledger("ledger_incubating")),
                           "selection": ("no producer: the ledger records the present", _ledger_history)}),
    ("ledger_keep", {"current": ("the ledger's standing keep records (schema 1 or 2)", _ledger("ledger_keep")),
                     "selection": ("no producer: the ledger records the present", _ledger_history)}),
)

# The member names this module's own documents carry. A refusal may NAME a member only when it is one
# of these; every other key is reported by its ordinal, because a key is untrusted text and a
# document can carry a credential as one (`projection.document_location`). Syntax is not authority:
# naming any key that looked like a name repeated the arbitrary nested key of
# `{"api_key": {"shortpass": ...}}` in the refusal (GC#5).
#
# A name missing from here costs a readable location and nothing else, so the list failing behind the
# documents is safe rather than silent. What is NOT safe is a credential name reaching it, and
# `self_test` asks the floor about every entry.
DOCUMENT_MEMBERS = (
    # the reference-point document and its layer rows
    "reference", "complete", "incomplete_reasons", "layers", "units", "renames", "produced_by",
    "module", "design", "commit", "kind", "ref", "state", "layer", "producer", "status", "carriers",
    "reasons", "empty", "notes", "overlay_hosts", "sessions", "events", "unknown", "content_ref",
    "ledger_keep_held_back",
    # the manifest
    "references", "state_root_unchanged", "out_dir", "inputs", "operative", "layer_units",
    "layer_empty", "symlink_policy", "protected_roots", "roots", "roots_absent", "transcripts",
    "read_through", "native_files_read", "watched_roots", "watched_native_files", "files",
    "omissions", "baseline_unmapped", "baseline_items_expected", "state_root", "user_root",
    "frozen_missing", "baselines", "installed", "pinned", "differ", "release", "selection",
    "current", "catalog", "host", "pin", "pin_unknown", "unknown_total", "current_scopes",
    "native_events", "delivery_confirmed", "session", "scope", "at", "acquisition_error",
    # a rename row
    "from_unit_id", "from_carrier_id", "to_carrier_id", "from_path", "to_path", "from_layer",
    "to_layer", "moved", "ambiguous", "from_carriers", "to_carriers", "reason",
)
DOCUMENT_KEYS = frozenset(DOCUMENT_MEMBERS + UNIT_FIELDS + PLAN_FIELDS + EMISSION_FIELDS
                          + PROVENANCE_FIELDS + ("block", "item_ref", "package_id", "carrier_id")
                          + tuple(layer for layer, _producers in LAYERS)
                          + tuple(REFERENCES) + tuple(STATUSES))


def emitted_document(reference, rows, ctx):
    """The document one reference point publishes, from its layer rows.

    THE production path, called by `reference_of` and by the differential control alike. It was
    composed inline inside `reference_of`, so a control could only approximate it — and a control
    that approximates the path it judges is judging a different path (r3 #0)."""
    units = operative_context(produce(rows))
    place = {"home": ctx.get("home"), "decisions": {}}
    reasons = [reason for row in rows for reason in row["reasons"]]
    if ctx.get("acquisition_error"):
        reasons = [ctx["acquisition_error"]] + reasons
    kind = {"current": {"kind": "current", "commit": ctx.get("commit")},
            "release": {"kind": "release", "ref": ctx.get("release_ref")},
            "selection": {"kind": "selection", "content_ref": (ctx.get("snapshot") or {}).get("content_ref")}}[reference]
    document = {
        "reference": emit_row("reference", REFERENCE_TABLE,
                              {**kind, "complete": not reasons, "incomplete_reasons": reasons}, place),
        "produced_by": emit_row("produced_by", PRODUCED_BY_TABLE, {
            "module": "session-distill/runlib/inventory.py", "design": DESIGN,
            "state_root": str(ctx["state_root"]) if ctx["state_root"] else None,
            "notes": ctx["notes"]}, place),
        "layers": [emit_row("layer_row", LAYER_ROW_TABLE,
                            {key: row[key] for key in ("layer", "producer", "status", "units",
                                                       "empty", "reasons")}, place)
                   for row in rows],
        "units": shed(units, ctx.get("home")),
        "renames": [],
    }
    return document, units


def reference_of(reference, ctx):
    """One reference point: its layers, its units, its completeness and the reasons against it."""
    return emitted_document(reference, layer_rows(reference, ctx), ctx)


def mapping_problems(expected, units):
    """Done-when 1: every item of the expected set — read from the baseline file itself, not from
    what was produced — carries at least one unit."""
    produced = {unit["item_ref"] for unit in units if unit["item_ref"]}
    return [f"BASELINE_UNMAPPED {ref}: the release reference point produced no unit for this baseline item"
            for ref in sorted(expected) if ref not in produced]


def verify_unchanged(watched, before, native_before, failing=None, home=None):
    """Re-hash every watched root and native source and refuse by name on a difference.

    `failing` is the exception already on its way out, if any. A write into the owner's state is the
    graver fact, so it is reported — but the error that was in flight is carried in the message
    rather than swallowed, because a verifier that hides the failure it ran beside is a worse
    instrument than no verifier (GA#3)."""
    after, result = {}, {}
    for root in watched:
        after[str(root)], _ = hash_tree(root)
    native_after = {name: hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()
                    for name in native_before if pathlib.Path(name).is_file()}
    result["state_root_unchanged"] = before == after and native_before == native_after
    result["watched_roots"] = {masked(root, home): len(before[str(root)]) for root in watched}
    result["watched_native_files"] = len(native_before)
    beside = f" (raised while {type(failing).__name__}: {failing} was in flight)" if failing else ""
    if native_before != native_after:
        touched = (sorted(set(native_before) ^ set(native_after))
                   or [name for name in native_before if native_before[name] != native_after.get(name)])
        raise Refused(f"STATE_WRITTEN: reading the native layers changed "
                      f"{[masked(name, home) for name in touched]}{beside}")
    if before != after:
        changed = sorted({f"{root}/{name}" for root in before
                          for name in set(before[root]) ^ set(after.get(root, {}))}
                         | {f"{root}/{name}" for root in before for name in set(before[root]) & set(after.get(root, {}))
                            if before[root][name] != after[root][name]})
        raise Refused(f"STATE_WRITTEN: reading the library changed "
                      f"{[masked(name, home) for name in changed[:4]]} ({len(changed)} file(s)); "
                      f"the frozen-copy route is not being taken{beside}")
    return result


# R6: the manifest. Every count is a number by type, every root is a projected path, and every
# reason passes the floor like the reasons in the document.
MANIFEST_REFERENCE_TABLE = table_of({
    "complete": as_scalar(),
    "units": as_scalar(),
    "operative": as_scalar(),
    "layers": map_of(as_enum(layer_names), as_enum(STATUSES)),
    "layer_units": map_of(as_enum(layer_names), as_scalar()),
    "layer_empty": list_of(as_enum(layer_names)),
    "incomplete_reasons": list_of(as_metadata()),
    "renames": as_scalar(),
})
INPUTS_TABLE = table_of({
    "symlink_policy": as_constant(SYMLINK_POLICY),
    "protected_roots": list_of(as_metadata()),
    "roots": map_of(as_metadata(), table_of({"files": as_scalar(),
                                             "omissions": as_tree()})),
    "roots_absent": list_of(as_metadata()),
    "transcripts": as_tree(),
})
MANIFEST_TABLE = table_of({
    "references": map_of(as_enum(REFERENCES), MANIFEST_REFERENCE_TABLE),
    "state_root_unchanged": as_scalar(nullable=True),
    "out_dir": as_metadata(),
    "inputs": INPUTS_TABLE,
    "watched_roots": map_of(as_metadata(), as_scalar()),
    "watched_native_files": as_scalar(),
    "baseline_unmapped": list_of(as_metadata()),
    "baseline_items_expected": as_scalar(),
    "state_written": list_of(as_metadata()),
    "native_changed": list_of(as_metadata()),
}, optional=("baseline_unmapped", "baseline_items_expected", "state_written", "native_changed",
             "watched_roots", "watched_native_files", "state_root_unchanged"))


def run(repo, state_root, user_root, out_dir, pin=None, native_roots=None, ledger=None, commit=None,
        run_dir=None, zstd=None, declared_state=None, declared_user=None, environ=None):
    """Write `inventory/<reference>.json` for every reference point, and return the manifest.

    The owner's state is hashed before and after, and the two hashes are compared here rather than
    claimed in prose: this reads the library through frozen copies, and a difference refuses the
    whole inventory by name (done-when 5).

    The native layers are what a transcript records as delivered (the 1548 amendment): they are read
    through the S1 census readers, bound to each session's census record, and NO native file is ever
    read — not a host instruction file, not a settings file, not a memory entry, on any path.
    `native_roots` names the project roots, which are protected WRITE TARGETS and nothing else."""
    out_dir = pathlib.Path(out_dir)
    state_root = pathlib.Path(state_root).expanduser() if state_root else None
    user_path = pathlib.Path(user_root).expanduser() if user_root else None
    # Protection is resolved independently of READING: `--no-state` passes None for both roots, and
    # the owner's state is protected all the same. `declared_state`/`declared_user` are what the
    # caller was configured with; a caller that names neither still gets the owner's real roots,
    # because `configured_roots` falls back to the environment and the installed default (R1#1).
    protect_state, protect_user = configured_roots(state_root or declared_state,
                                                   user_root or declared_user, environ)
    guarded = protected_roots(protect_state, protect_user, native_roots, checkout=repo, repo=repo,
                              environ=environ)
    home = str(pathlib.Path.home())
    temp_root = temp_home(guarded, home, environ)   # chosen and judged before any write, GC#1
    overlaps = overlap_problems([out_dir], guarded, home=home)
    if overlaps:
        raise Refused("; ".join(overlaps))
    watched = [root for root in (state_root, user_path) if root is not None and root.is_dir()]
    before, omitted = {}, {}
    for root in watched:
        before[str(root)], omitted[str(root)] = hash_tree(root)
    inputs = {"symlink_policy": SYMLINK_POLICY, "protected_roots": [masked(root, home) for root in guarded],
              "roots": {masked(root, home): {"files": len(before[str(root)]), "omissions": omitted[str(root)]}
                        for root in watched},
              "roots_absent": [masked(root, home) for root in (state_root, user_path)
                               if root is not None and not root.is_dir()],
              "transcripts": {"read_through": "runlib/sources.read_lines, bound to the S1 census record",
                              "native_files_read": 0}}
    produced, manifest = {}, {"references": {}, "state_root_unchanged": None,
                              "out_dir": masked(out_dir, home), "inputs": inputs}
    try:
        with no_bytecode(), tempfile.TemporaryDirectory(prefix="distill-inventory-", dir=str(temp_root)) as frozen_dir:
            ctx = context_of(repo, state_root, user_root, dict(native_roots or {}), pin, ledger)
            ctx["commit"] = commit
            try:
                freeze_inputs(pathlib.Path(frozen_dir), repo, state_root, user_root, pin, ctx)
            except Exception as exc:  # acquisition is an input, and a missing input is a status
                ctx["acquisition_error"] = (f"INPUT_UNACQUIRED: freezing the inputs failed "
                                            f"({projected_message(exc, ctx.get('home'))}), so every layer "
                                            f"read from the owner's state has no record here")
                ctx.setdefault("release_ref", None)
                ctx.setdefault("expected_release_items", [])
            bind_transcripts(ctx, run_dir, zstd)
            inputs["transcripts"].update(ctx["notes"]["transcripts"])
            for reference in REFERENCES:
                produced[reference] = reference_of(reference, ctx)
            base = produced["release"][1]
            for reference in ("current", "selection"):
                produced[reference][0]["renames"] = renames_against(produced[reference][1], base, home)
            if ctx.get("release_ref"):
                problems = mapping_problems({item["ref"] for item in ctx["expected_release_items"]}, produced["release"][1])
                document = produced["release"][0]
                document["reference"]["incomplete_reasons"] += problems
                document["reference"]["complete"] = not document["reference"]["incomplete_reasons"]
                manifest["baseline_unmapped"] = problems
                manifest["baseline_items_expected"] = len(ctx["expected_release_items"])
        for reference, (document, units) in produced.items():
            write_document(out_dir, out_dir / "inventory" / f"{reference}.json", document, home)
            manifest["references"][reference] = {
                "complete": document["reference"]["complete"], "units": len(units),
                "operative": sum(1 for unit in units if unit["class"] == "operative"),
                "layers": {row["layer"]: row["status"] for row in document["layers"]},
                "layer_units": {row["layer"]: row["units"] for row in document["layers"]},
                "layer_empty": sorted(row["layer"] for row in document["layers"] if row["empty"]),
                "incomplete_reasons": document["reference"]["incomplete_reasons"],
                "renames": len(document["renames"]),
            }
    finally:
        # The read-only guarantee is verified on the error paths too: a producer that wrote into
        # the owner's state and then raised would otherwise leave the write unreported (GA#3).
        manifest.update(verify_unchanged(watched, before, {}, sys.exc_info()[1], home))
    # R6 out through its table, nested references and inputs with it: the manifest is published, so
    # it is emitted by the same default-deny rule as every document row (r3 S1).
    manifest = emit_row("manifest", MANIFEST_TABLE, manifest, {"home": home, "decisions": {}})
    write_document(out_dir, out_dir / "inventory" / "manifest.json", manifest, home)
    return manifest


def bind_transcripts(ctx, run_dir, zstd=None):
    """Read this run's census-bound transcripts into the context: the events, the pinned session's
    event in force, §8's current sets, and every named unknown.

    This is the only place a transcript is read, and it reads none of the owner's instruction files."""
    delivered = ((ctx.get("snapshot") or {}).get("output") or {}).get("instruction_text")
    notes = {"read_through": "runlib/sources.read_lines, bound to the S1 census record",
             "native_files_read": 0}
    try:
        events, unknown = transcript_events(run_dir, delivered, zstd)
    except Unacquired as exc:
        ctx["transcript_error"] = str(exc)
        notes.update({"sessions": 0, "events": 0, "unknown": [str(exc)]})
        ctx["notes"]["transcripts"] = notes
        ctx["current_sets"], ctx["pin_event"] = {}, None
        return
    ctx["events"] = events
    ctx["current_sets"] = current_sets(events)
    ctx["pin_event"] = None
    if ctx.get("pin") and ctx.get("pin_record"):
        session = f"{str(ctx['pin']).partition(':')[0]}:{str(ctx['pin']).partition(':')[2]}"
        own = [event for event in events if event["session"] == session and event["kind"] == "native"]
        ctx["pin_event"] = event_in_force(own, ctx["pin_record"].get("created")) or (own[0] if own else None)
        if not own:
            notes["pin_unknown"] = UNKNOWN_REASONS["no_record"] if any(
                event["session"] == session for event in events) else UNKNOWN_REASONS["codex_identity"] \
                if str(ctx["pin"]).startswith("codex:") else UNKNOWN_REASONS["no_record"]
    delivery = [event for event in events if event["kind"] == "session_injection"]
    notes.update({"events": len(events), "native_events": len([e for e in events if e["kind"] == "native"]),
                  "delivery_confirmed": len(delivery),
                  "current_scopes": sorted({f"{layer}@{scope and masked(scope) or 'host'}"
                                            for layer, scope in (ctx["current_sets"] or {})}),
                  "unknown": unknown[:20], "unknown_total": len(unknown)})
    ctx["notes"]["transcripts"] = notes


def freeze_inputs(frozen, repo, state_root, user_root, pin, ctx):
    """Copy what the producers read and point the context at the copies: after this, no producer
    holds a path under the owner's state or home."""
    state, user = frozen / "state", frozen / "user"
    ctx["state_root"], ctx["user_root"] = state, user
    # The project roots are protected write targets and nothing else: no native file is read, here
    # or anywhere (the 1548 amendment §5).
    ctx["projects"] = [str(root) for root in (ctx["native_roots"].get("projects") or {}).values()]
    if state_root is None:
        ctx["notes"]["state"] = "no state root: the overlay, release and selection producers have no record"
        ctx["release_ref"], ctx["expected_release_items"] = None, []
        return
    # Every read below goes through the one source selection, before any byte of it is read: the
    # runtime state here, the pin in `read_pin`, the snapshot in `snapshot_of`, the baseline's item
    # list in `baseline_items`, and each copy input in `freeze` (GC#7).
    runtime_path = state_root / "runtime" / "state.json"
    runtime = json.loads(read_source(runtime_path, state_root)) if runtime_path.is_file() else {}
    state_sources = [(runtime_path, "runtime/state.json")]
    release_ref = None
    if pin:
        host, _, session_id = pin.partition(":")
        host, session_id = safe_label("pin host", host), safe_label("pin session id", session_id)
        record = read_pin(state_root, host, session_id)
        safe_label("snapshot content_ref", record["content_ref"])
        state_sources += [(state_root / "sessions" / "pins" / host / f"{session_id}.json",
                           f"sessions/pins/{host}/{session_id}.json"),
                          (state_root / "sessions" / "snapshots" / record["content_ref"],
                           f"sessions/snapshots/{record['content_ref']}")]
        ctx["pin_record"] = record
    else:
        ctx["notes"]["selection"] = "no pin: the selection reference point has no record (§6.3)"
    # Both baselines, always, and each with its own provenance. The current reference point's
    # overlays resolve against whatever the installed state selects, while the pin names the
    # baseline the session was activated from; freezing only the pin's left the current resolver
    # without its baseline tuple as soon as an upgrade moved the installed one (GA#8).
    installed_ref = runtime.get("selected_baseline_ref")
    ctx["installed_ref"] = installed_ref
    if pin is None:
        release_ref = installed_ref
        if release_ref:
            ctx["notes"]["release"] = "from the installed state's selected_baseline_ref, there being no pin to name one"
    ctx["notes"]["baselines"] = {"installed": installed_ref, "pinned": None}
    for ref in sorted({release_ref, installed_ref} - {None}):
        safe_label("baseline ref", ref)
        state_sources.append((state_root / "runtime" / "baselines" / ref, f"runtime/baselines/{ref}"))
    user_sources = []
    if user_root:
        user_root = pathlib.Path(user_root).expanduser()
        user_sources = [(user_root / "state.json", "state.json"), (user_root / "learnings", "learnings")]
    ctx["notes"]["frozen_missing"] = (freeze(state_sources, state, state_root)
                                      + [f"user/{name}" for name in freeze(user_sources, user, user_root)])
    if pin:
        verified = snapshot_of(repo, state, ctx["pin_record"]["content_ref"])
        release_ref = (verified["inputs"] or {}).get("baseline_ref")
        ctx["snapshot"] = verified
        ctx["notes"]["pin"] = {"host": pin.partition(":")[0], "content_ref": verified["content_ref"],
                               "state": ctx["pin_record"].get("state")}
        if release_ref:
            safe_label("baseline ref", release_ref)
            freeze([(state_root / "runtime" / "baselines" / release_ref, f"runtime/baselines/{release_ref}")],
                   state, state_root)
            ctx["notes"]["release"] = "from the pin's snapshot inputs.baseline_ref"
            ctx["notes"]["baselines"] = {"installed": installed_ref, "pinned": release_ref,
                                         "differ": installed_ref != release_ref}
    ctx["release_ref"] = release_ref
    ctx["expected_release_items"] = baseline_items(state, release_ref) if release_ref else []


def safe_lines(lines, home=None):
    """The lines a command prints, after the same policy every written document passes.

    A diagnostic is read by a person and stored by whatever captured the terminal, so a line is an
    artifact too; printing one that the write boundary would refuse is the same leak by another
    route (GC#6)."""
    problems = disclosure_problems(list(lines), home)
    if problems:
        raise Refused("; ".join(problems[:4]) + "; nothing is printed")
    return list(lines)


def report_lines(manifest, home=None):
    lines = []
    for reference, row in manifest["references"].items():
        flag = "complete" if row["complete"] else "incomplete"
        lines.append(f"{reference}: {row['units']} units ({row['operative']} operative), {flag}"
                     + (f", {row['renames']} rename(s)" if row["renames"] else ""))
        lines.append("  layers: " + ", ".join(f"{layer}={status}" for layer, status in row["layers"].items()))
        for reason in row["incomplete_reasons"][:6]:
            lines.append(f"  - {reason}")
    lines.append(f"state root unchanged: {manifest['state_root_unchanged']}")
    inputs = manifest.get("inputs", {})
    for root, row in inputs.get("roots", {}).items():
        lines.append(f"read {row['files']} file(s) under {root}"
                     + (f", {len(row['omissions'])} omitted (symlink or unreadable)" if row["omissions"] else ""))
    for root in inputs.get("roots_absent", []):
        lines.append(f"declared input root absent: {root}")
    lines.append(f"redaction: every unit's text through {projection.CURRENT}; hashes over the raw carrier")
    return safe_lines(lines, home)


# ---------------------------------------------------------------- the contract

# The contract this module is held against is a schema the code owns, not a dated design record.
#
# `layer_problems` and `contract_problems` used to read
# `design/session-distill/2026-10-20T1942--9684f05--mechanism-design.md` by path and parse §6.1 out
# of its prose. That made a dated record part of executable acceptance: a record is a claim about a
# past tree, being superseded is its normal fate, and superseding one changed what this suite
# accepts (GC#12, the 1548 amendment §10). The schema below is the same statement with an owner that
# does not expire; the design section it was derived from is cited in the schema's `$comment` as
# provenance, and nothing executable reads that citation.
#
# It is still an INDEPENDENT statement, which is what GA#11 asked for: `LAYERS` and `UNIT_FIELDS` are
# the tables the code walks, the schema is a separate file, and a layer or a field deleted from
# either has to fail against something that is not itself. The schema is load-bearing beyond this
# comparison — `self_test` validates the real documents' units and layer rows against it.
SCHEMA_REL = "session-distill/schemas/inventory.schema.json"
SCHEMA_PATH = HERE / "schemas" / "inventory.schema.json"


def inventory_schema(path=SCHEMA_PATH):
    """The schema this module's documents are held against, read from the file the code owns."""
    path = pathlib.Path(path)
    if not path.is_file():
        raise Refused(f"SCHEMA_MISSING {SCHEMA_REL}: the inventory has no contract to hold")
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_or_problem(schema):
    """`(schema, problems)`: the schema to judge against, or why there is none."""
    if schema is not None:
        return schema, []
    try:
        return inventory_schema(), []
    except (Refused, ValueError) as exc:
        return None, [f"SCHEMA_UNREADABLE {SCHEMA_REL}: {type(exc).__name__}: {exc}"]


def layer_problems(schema=None):
    """The layer table against the schema's own enumeration of the layers."""
    schema, problems = _schema_or_problem(schema)
    if problems:
        return problems
    declared = (((schema.get("$defs") or {}).get("layer_name") or {}).get("enum"))
    if not declared:
        return [f"SCHEMA_UNREADABLE {SCHEMA_REL}: $defs/layer_name declares no layer enum"]
    walked = [layer for layer, _producers in LAYERS]
    for missing in sorted(set(declared) - set(walked)):
        problems.append(f"LAYER_MISSING {missing}: the schema names this layer and the table does not walk it")
    for extra in sorted(set(walked) - set(declared)):
        problems.append(f"LAYER_UNDECLARED {extra}: the table walks a layer the schema does not name")
    if list(declared) != walked and not problems:
        problems.append(f"LAYER_ORDER: the table walks {walked} and the schema declares {list(declared)}")
    return problems


def contract_problems(schema=None):
    """Done-when 6: the unit record carries exactly the fields the schema requires of one, in order.

    `UNIT_FIELDS` is §6.1's list plus the plan's two fields and the emission's one; the schema is
    where that set is declared, and this holds the tuple against it."""
    schema, problems = _schema_or_problem(schema)
    if problems:
        return problems
    required = (((schema.get("$defs") or {}).get("unit") or {}).get("required"))
    if not required:
        return [f"SCHEMA_UNREADABLE {SCHEMA_REL}: $defs/unit requires no fields, so it is no contract"]
    if tuple(UNIT_FIELDS) != tuple(required):
        return [f"CONTRACT_MISMATCH unit ({SCHEMA_REL}): the record carries {list(UNIT_FIELDS)}, "
                f"the schema requires {list(required)}"]
    missing = [field for field in PLAN_FIELDS + EMISSION_FIELDS if field not in required]
    if missing:
        return [f"CONTRACT_MISMATCH unit ({SCHEMA_REL}): the plan's and the emission's fields "
                f"{missing} are not required of a unit"]
    return []


def document_contract_problems(document, schema=None):
    """The units and layer rows of one produced document against the schema.

    This is what makes the schema a contract rather than a second list: the real artifact is
    validated against it, so a document that drifts from the declaration fails here and not only
    where a tuple is compared with one."""
    schema, problems = _schema_or_problem(schema)
    if problems:
        return problems
    subject = {"units": document.get("units") or [], "layers": document.get("layers") or []}
    try:
        validator = validate.compile_schema(schema)
    except Exception as exc:  # a schema this policy refuses is a named failure, not a traceback
        return [f"SCHEMA_INVALID {SCHEMA_REL}: {type(exc).__name__}: {exc}"]
    return [f"DOCUMENT_INVALID {row}" for row in validate.validate_instance(validator, subject)]


DATED_RECORD = re.compile(r"design/[^\s\"']*/\d{4}-\d{2}-\d{2}T\d{4}--")


def dated_record_problems(source=None):
    """Every place this module resolves a dated design record into a path it reads.

    A dated record may be NAMED — `DESIGN` is recorded in `produced_by` so a reader can find the
    design this was derived from — but it may not be READ, because then superseding it changes what
    this suite accepts, and being superseded is the normal fate of these files (GC#12, the 1548
    amendment §10). The contract belongs in `SCHEMA_REL`, which the code owns.

    What is decided here is the shape that was actually there: `path = REPO / rel`, where `rel` is a
    parameter whose default is the dated constant. So a parameter defaulting to one counts as the
    record itself, and a check that only looked at literals beside the `/` would have passed over
    the very code it exists to forbid."""
    source = pathlib.Path(__file__).read_text(encoding="utf-8") if source is None else source
    tree = ast.parse(source)

    def is_dated(node, names):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return bool(DATED_RECORD.search(node.value))
        return isinstance(node, ast.Name) and node.id in names

    dated = set()
    for node in ast.walk(tree):     # module constants holding one
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) and is_dated(node.value, set()):
            dated.add(node.targets[0].id)
    for node in ast.walk(tree):     # parameters defaulting to one
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional = node.args.posonlyargs + node.args.args
            for arg, default in zip(positional[len(positional) - len(node.args.defaults):], node.args.defaults):
                if is_dated(default, dated):
                    dated.add(arg.arg)
            for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
                if default is not None and is_dated(default, dated):
                    dated.add(arg.arg)
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and is_dated(node.right, dated):
            problems.append(f"DATED_RECORD_READ line {node.lineno}: a dated design record is resolved "
                            f"into a path this module reads; the contract belongs in {SCHEMA_REL}")
    return problems


def reason_problems(source=None):
    """Every `unknown` this module reports names a reason from `UNKNOWN_REASONS`, and every entry of
    that table is used.

    This is what replaced a control that asserted a dated design record existed by path (GC#12). A
    dated record is a claim about a past tree: a test bound to one tests provenance rather than
    behaviour, and it fails the day the record is superseded, which is the normal fate of those
    files. What the code owns is this table and the places that raise from it."""
    source = pathlib.Path(__file__).read_text(encoding="utf-8") if source is None else source
    tree = ast.parse(source)
    problems, used = [], set()

    def named(node):
        """The `UNKNOWN_REASONS[...]` keys inside one node."""
        keys = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Subscript) and getattr(inner.value, "id", None) == "UNKNOWN_REASONS" \
                    and isinstance(inner.slice, ast.Constant):
                keys.add(inner.slice.value)
        return keys

    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) \
                and getattr(node.exc.func, "id", None) == "Unacquired":
            keys = named(node)
            if not keys:
                problems.append(f"REASON_UNNAMED line {node.lineno}: an `unknown` is raised with a reason "
                                f"that is not in UNKNOWN_REASONS, so the status carries prose nobody owns")
            used |= keys
        elif isinstance(node, (ast.Assign, ast.Expr, ast.Return, ast.Dict, ast.Call)):
            used |= named(node)
    for key in UNKNOWN_REASONS:
        if key not in used:
            problems.append(f"REASON_UNUSED {key}: the table declares a reason no path reports")
    return problems


def self_test():
    """Done-when 1-6, each with the control that fails by name when the rule is taken out."""
    failures, ran = [], []

    def control(name, problems, *needles):
        ran.append(name)
        text = "; ".join(problems)
        if not problems:
            failures.append(f"{name}: expected a failure naming {needles or ('anything',)}, got none")
        else:
            missing = [needle for needle in needles if needle not in text]
            if missing:
                failures.append(f"{name}: expected {missing} among {problems}")

    def clean(name, problems):
        ran.append(name)
        if problems:
            failures.append(f"{name}: expected no violation, got {problems}")

    def check(name, ok, detail=""):
        ran.append(name)
        if not ok:
            failures.append(f"{name}: {detail}")

    # ---- the splitter reproduces its carriers, over the real guides (the measured property)
    guides = sorted((REPO / "claude" / "guides").glob("*.md"))[:6] + sorted((REPO / "claude" / "hooks").glob("*.py"))[:2]
    check("the splitter has carriers to reproduce", len(guides) >= 3, f"only {len(guides)} carrier(s) found")
    for path in guides:
        text = path.read_text(encoding="utf-8")
        blocks = blocks_of(path.name, text)
        check(f"the split reproduces {path.name}", "".join(block[1] for block in blocks) == text, "the concatenation differs")
        check(f"{path.name} yields units", len(blocks) > 1, f"{len(blocks)} block(s)")
    control("a carrier whose structure the splitter cannot divide",
            [str(exc) for exc in [_raised(lambda: blocks_of("broken.py", "def f(:\n  pass\n"))]], "broken.py", "SyntaxError")
    control("a supported language that does not parse",
            [str(_raised(lambda: blocks_of("broken.py", "def f(:\n  pass\n")))], "SyntaxError")
    check("a parse failure of a supported form is malformed, not unsupported",
          isinstance(_raised(lambda: blocks_of("broken.py", "def f(:\n  pass\n")), Malformed),
          f"{type(_raised(lambda: blocks_of('broken.py', 'def f(:\n  pass\n'))).__name__}")
    control("a carrier the split would lose bytes of", [str(exc) for exc in [_raised(lambda: blocks_of("blank.py", "\n\n"))]],
            "blank.py", "does not reproduce")

    # ---- done-when 6: the unit record is the schema's required set, and no dated record is read.
    # Every mutation below is an in-memory schema, so nothing here depends on a design document
    # existing, being at a path, or still carrying a sentence (GC#12, the 1548 amendment §10).
    own_schema = inventory_schema()
    clean("the unit record against the schema the code owns", contract_problems())
    control("a schema that requires another field of a unit", contract_problems(
        {**own_schema, "$defs": {**own_schema["$defs"],
                                 "unit": {**own_schema["$defs"]["unit"],
                                          "required": list(UNIT_FIELDS)[:-1] + ["something_else"]}}}),
        "CONTRACT_MISMATCH unit")
    control("a schema whose unit requires nothing at all", contract_problems(
        {**own_schema, "$defs": {**own_schema["$defs"], "unit": {"type": "object"}}}), "SCHEMA_UNREADABLE")
    control("a schema file that is not there at all",
            [str(_raised(lambda: inventory_schema(HERE / "schemas" / "no-such-schema.json")))],
            "SCHEMA_MISSING")
    # ---- GA#11: the layer set, judged against the schema's enumeration rather than against the
    # table that walks it
    clean("the layer table against the schema's own enumeration", layer_problems())
    saved_layers = globals()["LAYERS"]
    try:
        globals()["LAYERS"] = tuple(row for row in saved_layers if row[0] != "native_memory")
        control("a layer deleted from the table the inventory walks", layer_problems(), "LAYER_MISSING native_memory")
        globals()["LAYERS"] = saved_layers + (("a_layer_nobody_declared", {}),)
        control("a layer the table walks and the schema does not name", layer_problems(),
                "LAYER_UNDECLARED a_layer_nobody_declared")
    finally:
        globals()["LAYERS"] = saved_layers
    control("a schema that no longer names one of its layers", layer_problems(
        {**own_schema, "$defs": {**own_schema["$defs"],
                                 "layer_name": {"type": "string",
                                                "enum": [name for name in own_schema["$defs"]["layer_name"]["enum"]
                                                         if name != "session_injection"]}}}),
        "LAYER_UNDECLARED session_injection")
    control("a schema whose layer enum is empty", layer_problems(
        {**own_schema, "$defs": {**own_schema["$defs"], "layer_name": {"type": "string", "enum": []}}}),
        "SCHEMA_UNREADABLE")
    # A schema the project's own policy refuses is not a contract anything can be held against: it
    # must be valid JSON Schema and closed, like every other schema here (`runlib/validate.py`).
    control("the schema compiles under this project's schema policy",
            [f"compiled={_raised(lambda: validate.compile_schema(own_schema)) is None}"], "compiled=True")
    # ---- the 1548 amendment §10: no control here reads a dated design record
    clean("no dated design record is resolved into a path this module reads", dated_record_problems())
    control("the shape this module used to carry: a parameter defaulting to the dated record",
            dated_record_problems(
                'DESIGN = "design/session-distill/2026-10-20T1942--9684f05--mechanism-design.md"\n'
                "\n\ndef layer_problems(design_text=None, rel=DESIGN):\n"
                "    path = REPO / rel\n    return [path.read_text()]\n"),
            "DATED_RECORD_READ")
    control("and the plainer shape: the record named where it is read",
            dated_record_problems('def f():\n    return (REPO / "design/session-distill/'
                                  '2026-10-20T1942--9684f05--mechanism-design.md").read_text()\n'),
            "DATED_RECORD_READ")
    clean("a record NAMED as provenance and never read",
          dated_record_problems('DESIGN = "design/session-distill/2026-10-20T1942--9684f05--x.md"\n'
                                '\n\ndef produced_by():\n    return {"design": DESIGN}\n'))
    clean("and the ledger, which is read at runtime and carries no date in its name",
          dated_record_problems('LEDGER_REL = "design/session-distill/ledger.json"\n'
                                "\n\ndef f():\n    return (REPO / LEDGER_REL).read_text()\n"))

    # ---- GC#12: the reason table is the contract, and it is the code's own
    clean("every unknown this module reports names a reason the table owns", reason_problems())
    control("an unknown raised with a reason the table does not own",
            reason_problems("class Unacquired(Exception):\n    pass\n\n\n"
                            "def produce():\n    raise Unacquired('no record, trust me')\n"
                            + "".join(f"USED = UNKNOWN_REASONS[{key!r}]\n" for key in UNKNOWN_REASONS)),
            "REASON_UNNAMED")
    control("a declared reason no path reports",
            reason_problems("".join(f"USED = UNKNOWN_REASONS[{key!r}]\n" for key in list(UNKNOWN_REASONS)[1:])),
            "REASON_UNUSED", list(UNKNOWN_REASONS)[0])

    # ---- done-when 3: a context that spans two guides, and the mention that carries it
    def guide(name, body):
        return carrier("catalog", f"claude/guides/{name}", body)

    first = ("---\nuse_when:\n  - the fixture asks\n---\n\n## Rule\n\n"
             "- do the thing, as claude/guides/second.md § Exceptions says\n")
    second = "---\nuse_when:\n  - the second fixture asks\n---\n\n## Exceptions\n\n- except on a Tuesday\n"
    spanning = operative_context(units_of([guide("first.md", first), guide("second.md", second)]))
    mentioning = next(unit for unit in spanning if "do the thing" in unit["text"])
    carriers_named = {unit["path"] for unit in spanning if unit["unit_id"] in mentioning["operative_context"]}
    check("a unit's context spans both carriers", carriers_named == {"claude/guides/first.md", "claude/guides/second.md"},
          f"the context names {sorted(carriers_named)}")
    check("the context names the exception the mention points at",
          any(unit["unit_id"] in mentioning["operative_context"] and "Tuesday" in unit["text"] for unit in spanning),
          "the second guide's exception is not in the requirement set")
    without = operative_context(units_of([guide("first.md", first.replace(" claude/guides/second.md § Exceptions", "")),
                                          guide("second.md", second)]))
    shrunk = next(unit for unit in without if "do the thing" in unit["text"])
    check("the context shrinks when the cross-reference goes",
          len(shrunk["operative_context"]) < len(mentioning["operative_context"])
          and {unit["path"] for unit in without if unit["unit_id"] in shrunk["operative_context"]} == {"claude/guides/first.md"},
          f"{len(shrunk['operative_context'])} against {len(mentioning['operative_context'])} requirement(s)")

    # ---- done-when 4: one fragment, two versions, two contexts, one fragment hash
    fragment = "- the fragment both versions carry\n"
    older = units_of([guide("first.md", f"## Rule\n\n{fragment}")])
    newer = units_of([guide("first.md", f"## Rule, with an exception\n\n- except on a Tuesday\n\n{fragment}")])
    was = next(unit for unit in older if unit["text"] == fragment)
    now = next(unit for unit in newer if unit["text"] == fragment)
    check("the same fragment in the same carrier keeps its id", was["unit_id"] == now["unit_id"],
          f"{was['unit_id']} against {now['unit_id']}")
    check("the same fragment shares one fragment hash", was["sha"] == now["sha"], "the fragment hashes differ")
    check("the two versions are told apart", was["version_sha256"] != now["version_sha256"], "the carrier versions are equal")
    older, newer = operative_context(older), operative_context(newer)
    was = next(unit for unit in older if unit["text"] == fragment)
    now = next(unit for unit in newer if unit["text"] == fragment)
    check("the fragment's context differs between the versions",
          was["operative_context"] != now["operative_context"], "the two contexts are equal")
    moved = units_of([guide("second.md", f"## Rule\n\n{fragment}")])
    renames = renames_against(moved, older)
    check("a requirement that moved carrier is a rename",
          [row.get("from_path") for row in renames] == ["claude/guides/first.md"], f"{renames}")
    check("a heading every carrier shares is no rename",
          not [row for row in renames_against(units_of([guide("third.md", "## Rule\n\n")]), older)], "a reference unit was read as a rename")
    shared = units_of([guide("first.md", f"## Rule\n\n{fragment}"), guide("second.md", f"## Rule\n\n{fragment}")])
    try:  # guard the subject: a rename pass that raises fails this control, not the whole suite
        ambiguous = renames_against(units_of([guide("third.md", f"## Rule\n\n{fragment}")]), shared)
    except Exception as exc:
        ambiguous = [{"ambiguous": f"RAISED {type(exc).__name__}", "from_carriers": []}]
    control("a requirement two carriers already shared",
            [f"ambiguous={row.get('ambiguous')} from={len(row.get('from_carriers') or [])}" for row in ambiguous]
            or ["no row at all"],
            "ambiguous=True", "from=2")
    check("an ambiguous fragment is never resolved to one carrier",
          all(row.get("ambiguous") and "from_carrier_id" not in row for row in ambiguous),
          f"{ambiguous}")

    # ---- GA#1: the O3 delivery-state fixture — one heading, one changed exception body
    def delivery_state(exception_body):
        body = ("---\nuse_when:\n  - the fixture asks\n---\n\n"
                "## Delivery\n\n- hand the result to the reviewer\n\n"
                f"### Exceptions\n\n- {exception_body}\n")
        rows = operative_context(units_of([guide("delivery.md", body)]))
        rule = next(unit for unit in rows if "hand the result" in unit["text"])
        return rule, {by["unit_id"]: by["text"] for by in rows}

    tuesday, tuesday_rows = delivery_state("not on a Tuesday")
    wednesday, wednesday_rows = delivery_state("not on a Wednesday")
    check("the rule itself is unchanged when only its exception changed",
          tuesday["unit_id"] == wednesday["unit_id"] and tuesday["sha"] == wednesday["sha"],
          "the rule's identity moved with its exception")
    check("the rule's context carries the exception's body, not only its heading",
          any("Tuesday" in tuesday_rows[uid] for uid in tuesday["operative_context"]),
          f"{[tuesday_rows[uid] for uid in tuesday['operative_context']]}")
    control("a changed exception body under an unchanged heading",
            [f"context changed: {tuesday['operative_context'] != wednesday['operative_context']}"],
            "context changed: True")
    check("the exception the context names is the one this version carries",
          not any("Wednesday" in tuesday_rows[uid] for uid in tuesday["operative_context"])
          and any("Wednesday" in wednesday_rows[uid] for uid in wednesday["operative_context"]),
          "the two versions name the same exception")

    # ---- GA#1: a referenced requirement is read with its own context, and what cannot be reached says so
    referring = guide("referring.md", "## Rule\n\n- follow claude/guides/referred.md § Exceptions\n")
    referred = guide("referred.md", "---\nuse_when:\n  - the referred fixture asks\n---\n\n"
                                    "## Exceptions\n\n- except when the day is odd\n")
    reached = operative_context(units_of([referring, referred]))
    pointing = next(unit for unit in reached if "follow claude" in unit["text"])
    carried = {unit["unit_id"]: unit for unit in reached}
    check("a referenced requirement brings the trigger its own carrier states",
          any(carried[uid]["block"] == "frontmatter" and carried[uid]["path"].endswith("referred.md")
              for uid in pointing["operative_context"] if uid in carried),
          "the referenced guide's frontmatter is not in the requirement set")
    dangling = operative_context(units_of([guide("dangling.md", "## Rule\n\n- follow claude/guides/absent.md\n")]))
    unresolved = next(unit for unit in dangling if "follow claude" in unit["text"])
    control("a mention this reference point cannot resolve",
            [row for row in unresolved["operative_context"] if row.startswith(UNRESOLVED)],
            "unknown:claude/guides/absent.md")

    # ---- GB#9: a whole-guide reference, a same-carrier one, an unresolved heading, and a cycle
    whole = operative_context(units_of([
        guide("pointing.md", "## Rule\n\n- follow claude/guides/pointed.md\n"),
        guide("pointed.md", "## Pointed\n\n- the requirement the other guide points at\n"
                            "\n- a second requirement of the same guide\n")]))
    pointing = next(unit for unit in whole if "follow claude" in unit["text"])
    carried_whole = {unit["unit_id"]: unit for unit in whole}
    control("a bare reference that brought none of the guide's requirements",
            [f"requirements={sorted(carried_whole[uid]['text'].strip() for uid in pointing['operative_context'] if uid in carried_whole and carried_whole[uid]['path'].endswith('pointed.md') and carried_whole[uid]['class'] == 'operative')}"],
            "the requirement the other guide points at", "a second requirement of the same guide")
    # `## Appendix` is not a condition heading, so only the mention can bring it into the context:
    # an `## Exceptions` section would be in the set anyway and the control would prove nothing.
    same = operative_context(units_of([guide("same.md",
        "## Rule\n\n- follow claude/guides/same.md § Appendix\n\n## Appendix\n\n- the appendix requirement\n")]))
    same_rule = next(unit for unit in same if "follow claude" in unit["text"])
    same_rows = {unit["unit_id"]: unit for unit in same}
    control("a reference to the unit's own carrier",
            [f"appendix in context={any('appendix requirement' in same_rows[uid]['text'] for uid in same_rule['operative_context'] if uid in same_rows)}"],
            "appendix in context=True")
    missing_heading = operative_context(units_of([
        guide("asking.md", "## Rule\n\n- follow claude/guides/answering.md § Nowhere\n"),
        guide("answering.md", "---\nuse_when:\n  - asked\n---\n\n## Elsewhere\n\n- a requirement\n")]))
    asking = next(unit for unit in missing_heading if "follow claude" in unit["text"])
    control("a mention naming a heading the carrier does not have",
            [row for row in asking["operative_context"] if row.startswith(UNRESOLVED)],
            "unknown:claude/guides/answering.md#Nowhere")
    chained = operative_context(units_of([
        guide("chain-a.md", "## Rule\n\n- start at claude/guides/chain-b.md\n"),
        guide("chain-b.md", "## Rule\n\n- then read claude/guides/chain-c.md\n"),
        guide("chain-c.md", "## Rule\n\n- the requirement at the end of the chain\n")]))
    chain_start = next(unit for unit in chained if "start at" in unit["text"])
    chain_rows = {unit["unit_id"]: unit for unit in chained}
    control("a chain of references the closure followed only one step of",
            [f"reached={sorted(chain_rows[uid]['path'].rsplit('/', 1)[-1] for uid in chain_start['operative_context'] if uid in chain_rows)}"],
            "chain-c.md")
    cyclic = operative_context(units_of([
        guide("left.md", "## Rule\n\n- see claude/guides/right.md\n"),
        guide("right.md", "## Rule\n\n- see claude/guides/left.md\n")]))
    left = next(unit for unit in cyclic if unit["path"].endswith("left.md") and "see claude" in unit["text"])
    check("a cycle between two guides closes rather than running away",
          len(left["operative_context"]) == len(set(left["operative_context"])) and len(left["operative_context"]) < 20,
          f"{len(left['operative_context'])} entries")
    check("the cycle's far side is in the requirement set",
          any(unit["path"].endswith("right.md") for unit in cyclic if unit["unit_id"] in left["operative_context"]),
          "the closure stopped before the guide it pointed at")

    # ---- GB#9: the O3 returned span — what a session read back, against what it had to read
    def delivery_state(unit, context_rows, returned):
        """§6.3's vocabulary over one returned span: `delivered` when every requirement of the
        unit's context is in what came back, `exposed_not_read` when the unit is but a requirement
        of its context is not."""
        requirements = [row for row in context_rows if not row.startswith(UNRESOLVED)]
        present = [row for row in requirements if row in returned]
        if len(present) == len(requirements):
            return "delivered"
        return "exposed_not_read" if unit["unit_id"] in returned else "not_delivered"

    o3_units = operative_context(units_of([
        guide("o3-first.md", "## Rule\n\n- do the thing, as claude/guides/o3-second.md says\n"),
        guide("o3-second.md", "---\nuse_when:\n  - the second guide applies\n---\n\n"
                              "## Exceptions\n\n- except on a Tuesday\n")]))
    o3_rule = next(unit for unit in o3_units if "do the thing" in unit["text"])
    everything = {unit["unit_id"] for unit in o3_units}
    control("a returned span holding every requirement of the rule's context",
            [delivery_state(o3_rule, o3_rule["operative_context"], everything)], "delivered")
    without_second = {unit["unit_id"] for unit in o3_units if not unit["path"].endswith("o3-second.md")}
    control("the same span with the second guide's requirements omitted",
            [delivery_state(o3_rule, o3_rule["operative_context"], without_second)], "exposed_not_read")
    check("the second guide really is in the rule's requirement set, so the flip is about the omission",
          any(unit["path"].endswith("o3-second.md") for unit in o3_units
              if unit["unit_id"] in o3_rule["operative_context"]),
          "the rule's context never named the second guide")

    # ---- GA#2: two packages delivering the same path, and an occurrence that does not drift
    def package_item(package, text):
        return {"ref": f"{package}:review", "kind": "guide", "package_id": package,
                "primary_member": "guides/review.md", "members": {"guides/review.md": text},
                "origin": {"source_path": "claude/guides/review.md"}, "body": text}

    shared_path = units_of([row for item in (package_item("@one/pkg", "## Review\n\n- read it twice\n"),
                                             package_item("@two/pkg", "## Review\n\n- read it once\n"))
                            for row in item_carriers(item, "catalog")])
    delivered = {unit["path"] for unit in shared_path}
    check("the two packages really do deliver one path", delivered == {"claude/guides/review.md"},
          f"{sorted(delivered)}")
    per_package = {unit["package_id"]: unit["carrier_id"] for unit in shared_path}
    check("a package's fragment is never another package's unit",
          len({unit["unit_id"] for unit in shared_path}) == len(shared_path)
          and len(set(per_package.values())) == len(per_package) > 1,
          f"two packages' units aliased at one delivered path: {per_package}")
    # The id is what distinguishes them, and it is opaque: it answers about identity and carries
    # neither the delivered path nor the package it was built from (GC#12).
    check("a carrier id spells out nothing it was built from",
          all(unit["carrier_id"].startswith("c-") and unit["package_id"] not in unit["carrier_id"]
              and "claude/guides" not in unit["carrier_id"] for unit in shared_path),
          f"{sorted(per_package.values())}")
    by_package = collections.defaultdict(set)
    for unit in shared_path:
        by_package[unit["package_id"]].add(unit["text"])
    check("each package's units carry that package's own text",
          "- read it twice\n" in by_package["@one/pkg"] and "- read it once\n" in by_package["@two/pkg"],
          f"{dict(by_package)}")
    repeated = "## Review\n\n- say it twice\n\n- say it twice\n"
    alone = units_of(item_carriers(package_item("@two/pkg", repeated), "catalog"))
    crowded = units_of([row for item in (package_item("@one/pkg", repeated), package_item("@two/pkg", repeated))
                        for row in item_carriers(item, "catalog")])
    check("a repeated fragment's occurrence is counted inside its own carrier",
          [unit["unit_id"] for unit in alone]
          == [unit["unit_id"] for unit in crowded if unit["package_id"] == "@two/pkg"],
          "the occurrence numbers moved with the other carriers delivered at the same path")
    subset = units_of([row for row in item_carriers(package_item("@one/pkg", "## Review\n\n- read it twice\n"), "catalog")])
    check("a subset selection keeps the ids the fuller reference point gave",
          {unit["unit_id"] for unit in subset} <= {unit["unit_id"] for unit in shared_path},
          "the same item's units changed id when fewer items were enumerated")
    same_path_layer = [dict(unit, layer="overlays",
                            carrier_id=carrier_identity("overlays", unit["path"], unit["item_ref"], unit["package_id"]))
                       for unit in older]
    # ---- GB#10: context and renames do not depend on which package the run enumerated first
    def two_packages(order):
        rows = [row for item in order for row in item_carriers(item, "catalog")]
        return operative_context(units_of(rows))

    package_a = package_item("@one/pkg", "---\nuse_when:\n  - package A applies\n---\n\n"
                                         "## Review\n\n- read it twice, as claude/guides/review.md says\n")
    package_b = package_item("@two/pkg", "---\nuse_when:\n  - package B applies\n---\n\n"
                                         "## Review\n\n- read it once\n")
    forward, backward = two_packages([package_a, package_b]), two_packages([package_b, package_a])

    def context_of_text(rows, needle):
        unit = next(row for row in rows if needle in row["text"])
        carried = {row["unit_id"]: row for row in rows}
        return sorted(carried[uid]["text"].strip() for uid in unit["operative_context"]
                      if uid in carried and carried[uid]["block"] == "frontmatter"), unit

    forward_triggers, forward_unit = context_of_text(forward, "read it once")
    backward_triggers, backward_unit = context_of_text(backward, "read it once")
    control("the same unit's trigger under the other package order",
            [f"forward={forward_triggers} backward={backward_triggers}"], "package B applies")
    check("package B's rule is never read with package A's trigger",
          all("package A" not in trigger for trigger in forward_triggers + backward_triggers),
          f"{forward_triggers} / {backward_triggers}")
    check("the context is the same whichever order the packages were enumerated in",
          forward_triggers == backward_triggers and forward_unit["operative_context"] == backward_unit["operative_context"],
          "the requirement set moved with the enumeration order")
    ambiguous_mention = next(row for row in forward if "read it twice" in row["text"])
    control("a mention of a path two packages deliver",
            [row for row in ambiguous_mention["operative_context"] if row.startswith(UNRESOLVED)],
            "unknown:ambiguous:claude/guides/review.md")

    layer_renames = renames_against(same_path_layer, older)
    control("a requirement that stayed at its path and changed layer",
            [f"{row.get('from_layer')}->{row.get('to_layer')} moved={row.get('moved')}" for row in layer_renames],
            "catalog->overlays", "moved=['layer']")

    # The scratch parent is CHOSEN AND JUDGED, not probed: this suite writes fixture state roots, a
    # copy of the checkout and run directories, and `tempfile`'s own resolution of `TMPDIR` would put
    # all of it inside a protected root when that is where `TMPDIR` points (R1#5).
    with self_test_scratch() as scratch:
        # ---- done-when 1: the release mapping, against the baseline file's own item list
        baseline = {"schema_version": 1, "packages": [{"package_id": "@fixture/core"}], "items": [
            {"ref": f"@fixture/core:item-{n}", "item_id": f"item-{n}", "kind": "guide", "package_id": "@fixture/core",
             "title": f"Item {n}", "surface": "relevant", "tier": "env-team", "domains": ["personal"],
             "primary_member": f"guides/item-{n}.md", "members": {f"guides/item-{n}.md": f"## Item {n}\n\n- a rule\n"},
             "origin": {"source_path": f"claude/guides/item-{n}.md"}, "body": "- a rule\n"} for n in (1, 2, 3)]}
        state = scratch / "state"
        (state / "runtime" / "baselines" / "ref1").mkdir(parents=True)
        (state / "runtime" / "baselines" / "ref1" / "inventory.json").write_text(json.dumps(baseline), encoding="utf-8")
        (state / "runtime" / "baselines" / "ref1" / "defaults.json").write_text(
            json.dumps({"schema_version": 1, "selected": [item["ref"] for item in baseline["items"]]}), encoding="utf-8")
        (state / "runtime" / "state.json").write_text(json.dumps(
            {"schema_version": 1, "selected_baseline_ref": "ref1", "last_successful_install_ref": "ref1"}), encoding="utf-8")
        expected_before = {item["ref"] for item in baseline_items(state, "ref1")}
        produced = units_of([row for item in baseline_items(state, "ref1") for row in item_carriers(item, "catalog")])
        clean("every baseline item mapped to a unit", mapping_problems(expected_before, produced))
        check("the expected set is not empty", len(expected_before) == 3, f"{len(expected_before)} item(s)")
        dropped = [unit for unit in produced if unit["item_ref"] != "@fixture/core:item-2"]
        expected_after = {item["ref"] for item in baseline_items(state, "ref1")}
        check("the control did not shrink the expected set", expected_before == expected_after,
              "the baseline file changed with the mapping, so the control judges nothing")
        control("a baseline item with no unit", mapping_problems(expected_after, dropped),
                "BASELINE_UNMAPPED @fixture/core:item-2")
        control("a baseline with no items at all",
                [str(_raised(lambda: baseline_items(scratch / "empty", "ref1")))], "BASELINE_ABSENT")

        hollow = state / "runtime" / "baselines" / "empty-ref"
        hollow.mkdir(parents=True)
        (hollow / "inventory.json").write_text(json.dumps({"schema_version": 1, "items": []}), encoding="utf-8")
        control("a baseline inventory with no items", [str(_raised(lambda: baseline_items(state, "empty-ref")))],
                "BASELINE_EMPTY")
        control("a selection with no pin on the state", [str(_raised(lambda: read_pin(state, "claude", "nobody")))],
                "PIN_ABSENT")
        (state / "sessions" / "pins" / "claude").mkdir(parents=True)
        (state / "sessions" / "pins" / "claude" / "hollow.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        control("a pin that names no snapshot", [str(_raised(lambda: read_pin(state, "claude", "hollow")))],
                "PIN_UNREADABLE")
        control("a checkout with no catalog loader to read",
                [str(_raised(lambda: catalog_carriers(scratch / "not-a-checkout")))], "PRODUCER_UNAVAILABLE")
        control("a checkout with no store to resolve the overlays with",
                [str(_raised(lambda: store_module(scratch / "not-a-checkout")))], "PRODUCER_UNAVAILABLE")

        # ---- done-when 2: the native layers answer from the transcript, and no file is read
        def jsonl(path, records_in):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(json.dumps(record) + "\n" for record in records_in), encoding="utf-8")
            return path

        def attachment(at, files, cwd=None, prompt=None):
            record = {"type": "attachment", "timestamp": at,
                      "attachment": {"type": "instructions", "files": files}}
            if cwd:
                record["cwd"] = cwd
            if prompt is not None:
                record["attachment"]["systemPrompt"] = [prompt]
            return record

        def member(kind, path, text):
            return {"type": kind, "path": path, "content": text}

        project_scope = str(scratch / "project")
        (scratch / "project").mkdir(exist_ok=True)
        delivered_body = "# Delivered\n\n- the body agent-bios compiled\n"
        main_path = jsonl(scratch / "transcripts" / "claude" / "s-main.jsonl", [
            attachment("2026-10-01T09:00:00+00:00",
                       [member("User", "~/.claude/CLAUDE.md", "# Global\n\n- a native rule\n"),
                        member("Project", f"{project_scope}/CLAUDE.md", "# Project\n\n- a project rule\n"),
                        member("AutoMem", "~/.claude/projects/p/memory/one.md", "---\nname: one\n---\n\n- a fact\n")],
                       cwd=project_scope,
                       prompt=f"<system-reminder>\n{delivered_body}</system-reminder>\n"),
            {"type": "user", "timestamp": "2026-10-01T09:30:00+00:00", "message": "a turn between the events"},
            attachment("2026-10-01T10:00:00+00:00",
                       [member("User", "~/.claude/CLAUDE.md", "# Global\n\n- a native rule, revised\n"),
                        member("AutoMem", "~/.claude/projects/p/memory/one.md", "---\nname: one\n---\n\n- a fact\n")],
                       cwd=project_scope)])
        child_path = jsonl(scratch / "transcripts" / "claude" / "s-main" / "subagents" / "s-child.jsonl", [
            attachment("2026-10-02T08:00:00+00:00",
                       [member("User", "~/.claude/CLAUDE.md", "# Global\n\n- what a built-in agent type got\n")],
                       cwd=project_scope)])
        codex_path = jsonl(scratch / "transcripts" / "codex" / "rollout-2026-10-01T09-00-00-aaaa.jsonl", [
            {"type": "session_meta", "timestamp": "2026-10-01T09:00:00+00:00",
             "payload": {"cwd": project_scope, "git": {"commit_hash": "abc1234"},
                         "base_instructions": {"text": "# Merged\n\n- one undivided block\n",
                                               "provenance": "config + project"}}}])

        def census_row(host, ident, path, status="eligible", parent=None, sha=None, count=None, prefix=None):
            data = pathlib.Path(path).read_bytes()
            lines = data.count(b"\n")
            return {"host": host, "id": ident, "source": "claude_projects" if host == "claude" else "codex_sessions",
                    "path": str(path), "status": status, "parent": parent,
                    "sha256": sha or hashlib.sha256(data).hexdigest(),
                    "versions": [{"sha": sha or hashlib.sha256(data).hexdigest(),
                                  "record_count": count if count is not None else lines,
                                  "prefix_sha": prefix or hashlib.sha256(data).hexdigest()}]}

        run_fixture = scratch / "run"
        run_fixture.mkdir(parents=True, exist_ok=True)
        rows_in = [census_row("claude", "s-main", main_path),
                   census_row("claude", "s-child", child_path, status="child_of", parent="s-main"),
                   census_row("codex", "aaaa", codex_path)]
        (run_fixture / CENSUS).write_text(json.dumps({"transcripts": rows_in}), encoding="utf-8")

        control("a run with no census to bind a transcript to",
                [str(_raised(lambda: census_entries(scratch / "no-run")))], "INPUT_UNACQUIRED", "census")
        entries = {entry["id"]: entry for entry in census_entries(run_fixture)}
        check("the census rows reach the inventory, main and child apart",
              [entries["s-main"]["kind"], entries["s-child"]["kind"]] == ["main", "subagent"],
              f"{[entries['s-main']['kind'], entries['s-child']['kind']]}")
        moved = dict(entries["s-main"], sha256="0" * 64, prefix_sha="0" * 64)
        control("a transcript whose bytes no longer match its census record",
                [str(_raised(lambda: transcript_records(moved)))], "no longer match", "on record")
        grown = scratch / "transcripts" / "claude" / "grown.jsonl"
        grown.write_bytes(main_path.read_bytes() + json.dumps({"type": "user", "timestamp": "2026-10-03T08:00:00+00:00"}).encode() + b"\n")
        appended = dict(entries["s-main"], path=str(grown))
        read_back, which = transcript_records(appended)
        check("a transcript the host appended to is read to the census boundary, and says so",
              len(read_back) == appended["record_count"] and "appended" in which, f"{len(read_back)} record(s), {which}")

        main_events = injection_events(transcript_records(entries["s-main"])[0], entries["s-main"], delivered_body)
        native_events = [event for event in main_events if event["kind"] == "native"]
        # Every row below is built from the list rather than indexed into it: a revert that drops an
        # event must fail by name here, not crash the suite on an index.
        def globals_of(event):
            return sorted(member["text"] for member in (event or {}).get("files", [])
                          if member["layer"] == "native_global")

        bodies = [globals_of(event) for event in native_events]
        instants = [event.get("at") for event in native_events]
        control("one transcript records one event per injection, not one per session",
                [f"native_events={len(native_events)} instants={instants}"],
                "native_events=2", "2026-10-01T09:00:00+00:00", "2026-10-01T10:00:00+00:00")
        control("the two injections carry their own bytes, which is why a reference point is per event",
                [f"distinct_bodies={len({tuple(body) for body in bodies})} of {len(bodies)}"],
                "distinct_bodies=2 of 2")
        in_force_before = globals_of(event_in_force(native_events, "2026-10-01T09:30:00+00:00"))
        control("the body in force before the second injection is the first injection's",
                [f"in_force_count={len(in_force_before)} "
                 f"in_force_has_the_later_body={any('revised' in text for text in in_force_before)}"],
                "in_force_count=1", "in_force_has_the_later_body=False")
        check("the body only the second injection carries is not in force before it",
              all("revised" not in text for text in in_force_before),
              f"the later body answered for an earlier turn: {in_force_before}")
        check("the agent-bios body is located inside the host's larger field, by the snapshot's text",
              [event["where"] for event in main_events if event["kind"] == "session_injection"]
              == ["attachment.systemPrompt[]"],
              f"{[event['where'] for event in main_events if event['kind'] == 'session_injection']}")
        check("a turn between two events is judged against the earlier one",
              (event_in_force(native_events, "2026-10-01T09:30:00+00:00") or {}).get("n")
              == (native_events[0]["n"] if native_events else None),
              "a later event answered for an earlier turn")
        check("a turn before every recorded event has no event in force",
              event_in_force(native_events, "2026-10-01T08:00:00+00:00") is None,
              "an event answered for a turn that preceded it")

        all_events = []
        for entry in census_entries(run_fixture):
            all_events += injection_events(transcript_records(entry)[0], entry, delivered_body)
        sets = current_sets(all_events)
        check("the current reference point resolves per layer and scope",
              {key[0] for key in sets} == {"native_global", "native_project", "native_memory"},
              f"{sorted({key[0] for key in sets})}")
        check("a subagent's injection is not evidence about the current state",
              all(event["transcript"] == "main" for event in sets.values()),
              "a subagent event was taken for the current reference point")
        global_event = sets[("native_global", project_scope)]
        check("the newest recorded event answers for its scope",
              global_event["at"] == "2026-10-01T10:00:00+00:00", f"{global_event['at']}")
        check("a file the newest event does not carry is gone from the current set",
              not any(member_row["layer"] == "native_project" for member_row in global_event["files"]),
              "a deleted project file survived in the newest event's set")
        check("the whole set of one event answers, never the newest event per path",
              sets[("native_project", project_scope)]["at"] == "2026-10-01T09:00:00+00:00",
              "the project layer did not fall back to the event that last carried it")
        codex_events = [event for event in all_events if event["host"] == "codex"]
        check("Codex is one undivided block, with no global/project split derived from it",
              [member_row["layer"] for member_row in codex_events[0]["files"]] == ["native_global"]
              and codex_events[0]["files"][0]["undivided"],
              f"{[member_row['layer'] for member_row in codex_events[0]['files']]}")
        codex_carrier = event_carriers("native_global", codex_events[0], "current")[0]
        check("a Codex carrier says its identity is unknown",
              "loaded text" in str(codex_carrier["provenance"].get("identity")),
              f"{codex_carrier['provenance']}")
        carriers_out = event_carriers("native_global", global_event, "current")
        check("a native carrier carries when and from whom it came",
              carriers_out[0]["provenance"]["as_of"] == global_event["at"]
              and carriers_out[0]["provenance"]["session"] == "claude:s-main",
              f"{carriers_out[0]['provenance']}")

        # No native file is read, on any path: the host layer names of `NATIVE` are not read by this
        # module at all, and the check is on the module's own source rather than on a promise.
        clean("no path in this module reads a host instruction, settings or memory file",
              native_read_problems())
        control("a module that globs a host home for its instruction files",
                native_read_problems('home = pathlib.Path(NATIVE["claude"]["home"]).expanduser()\n'
                                     'for path in home.glob(NATIVE["claude"]["global"][0]):\n    path.read_text()\n'),
                "NATIVE_FILE_READ")
        ledger = {"schema": 1, "entries": [
            {"id": "S-1", "status": "incubating", "lesson": "- an incubating principle\n"},
            {"id": "S-2", "status": "placed", "lesson": "- a placed one\n", "keep": {"units": ["u"]}},
            {"id": "S-3", "status": "placed", "lesson": "- no keep\n"}]}
        check("the ledger's incubating layer", len(ledger_carriers(ledger, "ledger_incubating")) == 1, "not one carrier")
        check("the ledger's keep layer", len(ledger_carriers(ledger, "ledger_keep")) == 1, "not one carrier")
        control("a ledger schema the inventory does not read",
                [str(_raised(lambda: ledger_carriers({"schema": 9, "entries": []}, "ledger_keep")))],
                "LEDGER_SCHEMA_UNSUPPORTED")

        # ---- GA#9: a keep record stands only while the entry's lifecycle says it does
        lifecycles = {"schema": 2, "entries": [
            {"id": "K-placed", "status": "placed", "lesson": "- a placed keep\n", "keep": {"units": ["unit-1"]},
             "reason": "it is still delivered"},
            {"id": "K-retired", "status": "retired", "lesson": "- a retired keep\n", "keep": {"units": ["unit-2"]}},
            {"id": "K-absorbed", "status": "placed", "lesson": "- an absorbed keep\n", "keep": {"units": ["unit-3"]},
             "absorbed_by": "K-placed"},
            {"id": "K-revived", "status": "placed", "lesson": "- a revived keep\n", "keep": {"units": ["unit-4"]}},
            {"id": "K-reverted", "status": "incubating", "lesson": "- a reverted keep\n", "keep": {"units": ["unit-5"]}}]}
        keep_notes = {}
        keeps = ledger_carriers(lifecycles, "ledger_keep", keep_notes)
        check("every lifecycle state the fixture plants is judged",
              len(lifecycles["entries"]) == len(keeps) + len(keep_notes["ledger_keep_held_back"]),
              f"{len(keeps)} kept, {len(keep_notes['ledger_keep_held_back'])} held back")
        control("a retired entry whose keep field survived its retirement",
                [f"{row['id']}: {row['reason']}" for row in keep_notes["ledger_keep_held_back"]],
                "K-retired", "K-absorbed", "K-reverted")
        check("only the entries the ledger still places are the keep layer",
              {row["item_ref"] for row in keeps} == {"K-placed", "K-revived"},
              f"{sorted(row['item_ref'] for row in keeps)}")
        check("the units a keep record protects travel with its carrier",
              [row["provenance"].get("keep_units") for row in keeps if row["item_ref"] == "K-placed"] == [["unit-1"]],
              "the keep's protected units were dropped")
        check("an entry held back still names the units it protected",
              all("keep_units" in row for row in keep_notes["ledger_keep_held_back"]),
              "a held-back keep lost its protected units")
        planted = {
            "complete": lambda ctx: [guide("first.md", first)],
            "empty": lambda ctx: [],
            # A structure the splitter cannot divide without losing bytes — not a supported form
            # that failed to parse, which is `malformed` below (GB#12).
            "unsupported": lambda ctx: [carrier("catalog", "blank.py", "\n\n")],
            "malformed": lambda ctx: [carrier("catalog", "broken.py", "def f(:\n  pass\n")],
            "no-units": lambda ctx: [carrier("catalog", "hollow.md", "")],
            "raising": lambda ctx: (_ for _ in ()).throw(Refused("INPUT_UNREADABLE hollow: planted")),
            "unknown": lambda ctx: None,
        }
        want = {"complete": ("complete", False), "empty": ("complete", True), "unsupported": ("unsupported", False),
                "malformed": ("incomplete", False),
                "no-units": ("incomplete", False), "raising": ("incomplete", False), "unknown": ("unknown", False)}
        saved = globals()["LAYERS"]
        try:
            globals()["LAYERS"] = tuple((name, {"current": (f"{name} producer", call)}) for name, call in planted.items())
            document, units = reference_of("current", context_of(REPO, None, None, {}, None, None))
        finally:
            globals()["LAYERS"] = saved
        rows = {row["layer"]: row for row in document["layers"]}
        check("every planted layer is in the table", set(rows) == set(planted), f"{sorted(rows)}")
        for layer, (status, empty) in want.items():
            check(f"the {layer} layer reports {status}", rows[layer]["status"] == status and rows[layer]["empty"] == empty,
                  f"{layer} reported {rows[layer]['status']}, empty={rows[layer]['empty']}")
            if status != "complete":
                check(f"the {layer} layer says why", bool(rows[layer]["reasons"]), "no reason given")
        check("an unsupported or unknown layer makes the reference point incomplete",
              document["reference"]["complete"] is False, "the reference point reported complete")
        check("a layer that read nothing is never silently empty",
              "never silently empty" in "; ".join(rows["no-units"]["reasons"]), f"{rows['no-units']['reasons']}")

        # ---- GA#11: one cause at a time, so ignoring any single one of them cannot survive
        causes = {"unsupported": planted["unsupported"], "unknown": planted["unknown"],
                  "malformed": planted["malformed"],
                  "no-units": planted["no-units"], "raising": planted["raising"]}
        for cause, producer in causes.items():
            saved_one = globals()["LAYERS"]
            try:
                globals()["LAYERS"] = (("catalog", {"current": ("the complete layer", planted["complete"])}),
                                       ("overlays", {"current": (f"the {cause} layer", producer)}))
                document_one, _units_one = reference_of("current", context_of(REPO, None, None, {}, None, None))
            finally:
                globals()["LAYERS"] = saved_one
            rows_one = {row["layer"]: row for row in document_one["layers"]}
            control(f"a reference point whose only fault is a {cause} layer",
                    [f"complete={document_one['reference']['complete']} "
                     f"catalog={rows_one['catalog']['status']} overlays={rows_one['overlays']['status']}"],
                    "complete=False", "catalog=complete")
            check(f"the {cause} layer is the one the reasons name",
                  all("overlays" in reason for reason in document_one["reference"]["incomplete_reasons"]),
                  f"{document_one['reference']['incomplete_reasons']}")

        def captured(**extra):
            """The argument set every run in this self-test uses: the project root as a protected
            write target, and the fixture run whose census binds the transcripts."""
            return {"native_roots": {"projects": {"project": scratch / "project"}},
                    "run_dir": run_fixture, **extra}

        # ---- done-when 5: the owner's state is read through frozen copies
        pending = state / "runtime" / "transactions" / "tx-1"
        pending.mkdir(parents=True)
        (pending / "transaction.json").write_text(json.dumps({"state": "NEEDS_RECOVERY", "owner": "installer"}), encoding="utf-8")
        user = scratch / "user"
        user.mkdir()
        (user / "state.json").write_text(json.dumps({"schema_version": 1, "items": {}, "overrides": {}, "tombstones": {},
                                                     "selection": None,
                                                     "learning_suppressions": {"claude": [], "codex": []}}), encoding="utf-8")
        before, _ = hash_tree(state)
        manifest = run(REPO, state, user, scratch / "out", ledger=ledger, commit="fixture", **captured())
        check("the frozen route left the owner's state untouched", manifest["state_root_unchanged"] and hash_tree(state)[0] == before,
              "the state root changed while the inventory read it")
        # ---- GA#11: the records as the artifact serializes them, not the field tuple in this module
        serialized = json.loads((scratch / "out" / "inventory" / "current.json").read_text(encoding="utf-8"))["units"]
        check("the artifact carries units to judge", bool(serialized), "no unit reached the artifact")
        missing_fields = sorted({field for unit in serialized for field in UNIT_FIELDS if field not in unit})
        control("a serialized unit record missing a field §6.1 asks for",
                [f"missing={missing_fields}"], "missing=[]")
        check("every serialized record's hashes are present and are hex",
              all(isinstance(unit.get("sha"), str) and len(unit.get("sha", "")) == 64
                  and isinstance(unit.get("version_sha256"), str) and len(unit.get("version_sha256", "")) == 64
                  for unit in serialized),
              "a serialized record has no usable hash")
        check("every serialized record carries the floor that made its text",
              all(unit.get("redaction_version") == projection.CURRENT for unit in serialized),
              "a serialized record does not name its redaction version")
        check("the inventory wrote a file per reference point",
              all((scratch / "out" / "inventory" / f"{reference}.json").is_file() for reference in REFERENCES),
              "a reference point has no artifact")
        check("the fixture release mapped every item",
              manifest.get("baseline_unmapped") == [] and manifest.get("baseline_items_expected") == 3,
              f"{manifest.get('baseline_unmapped')}")
        planted_write = state / "runtime" / "planted-by-a-producer.json"
        saved = globals()["LAYERS"]

        def writing_producer(ctx):
            planted_write.write_text("{}", encoding="utf-8")
            return [guide("first.md", first)]

        try:
            globals()["LAYERS"] = (("catalog", {"current": ("a producer that writes", writing_producer)}),)
            control("a producer that writes into the owner's state", [str(_raised(
                lambda: run(REPO, state, user, scratch / "written", ledger=ledger)))], "STATE_WRITTEN")
        finally:
            globals()["LAYERS"] = saved
            planted_write.unlink(missing_ok=True)
        check("the planted write is gone again", not planted_write.is_file(), "the fixture state kept the planted file")
        module = store_module(REPO)
        store = module.InstructionsStore(REPO, state_root=state, user_root=user)
        try:
            store.status()
        except Exception:
            pass
        after, _ = hash_tree(state)
        control("the store's own entry point writes to the state the frozen route leaves alone",
                [f"STATE_WRITTEN fixture: {sorted(set(after) - set(before))}"] if after != before else [],
                "STATE_WRITTEN")
        check("the write the frozen route avoids is in the state root, not the copy",
              sorted(set(after) - set(before)) or [name for name in after if after[name] != before.get(name)],
              "the recovering entry point changed nothing, so the control shows nothing")

        # ---- GA#3: no write can reach a protected root, and the guarantee is checked on error paths
        guarded_before, _ = hash_tree(state)
        for name, destination in (("inside the owner's state root", state / "out"),
                                  ("holding the owner's state root", state.parent)):
            control(f"an output destination {name} is refused before any write",
                    [str(_raised(lambda destination=destination: run(
                        REPO, state, user, destination, ledger=ledger, **captured())))],
                    "PROTECTED_OVERLAP")
        control("an output destination inside the project root a run names",
                [str(_raised(lambda: run(REPO, state, user, scratch / "project" / "out",
                                         ledger=ledger, **captured())))],
                "PROTECTED_OVERLAP")
        # A host home at its installed default, under a FIXTURE home: no control of this suite names
        # a path under the real one, so no revert of the rule under test can put a write there
        # (R2#6). The variables are unset here, which is what makes this the default's case.
        default_home = scratch / "default-host-home"
        control("an output destination inside a host home at its installed default",
                overlap_problems([default_home / ".claude" / "out"],
                                 protected_roots(None, None, {}, environ={"HOME": str(default_home)})),
                "PROTECTED_OVERLAP")
        check("the refused destination was never written",
              hash_tree(state)[0] == guarded_before and not (state / "out").exists(),
              "a refused run still touched the protected root")

        # ---- R1#1: protection does not depend on READING. This is the shape `--no-state` produces
        # — no state root and no authoring root to read — and the roots the caller was CONFIGURED
        # with are protected all the same. The flag that says "read nothing" used to say "write
        # anywhere": the same destination returned 0 and wrote four artifacts under the state root.
        unread_out = state / "out-while-reading-nothing"
        control("a destination inside the owner's state root when the run reads no state at all",
                [str(_raised(lambda: run(REPO, None, None, unread_out, ledger=ledger,
                                         declared_state=state, declared_user=user, **captured())))],
                "PROTECTED_OVERLAP")
        check("and the attempted write under the unread state root did not happen",
              not unread_out.exists() and hash_tree(state)[0] == guarded_before,
              f"exists={unread_out.exists()} "
              f"changed={sorted(set(hash_tree(state)[0]) - set(guarded_before))}")
        # A run that names NO roots resolves them from the environment and the installed default —
        # asked under a fixture environment and a fixture home, so the destination this control
        # reaches is inside disposable scratch. It used to be `configured_roots()[0]`, the owner's
        # REAL state root: with the refusal reverted, the writer would have created inventory
        # artifacts there (R2#6).
        unconfigured_home = scratch / "unconfigured-owner"
        unconfigured_env = {"HOME": str(unconfigured_home)}
        resolved_state = configured_roots(environ=unconfigured_env)[0]
        check("the fixture's own installed default is where this control writes, if it writes at all",
              resolved_state.is_relative_to(scratch), f"{masked(resolved_state)}")
        control("a run that names no roots at all, judged against what the environment resolves to",
                [str(_raised(lambda: run(REPO, None, None, resolved_state / "out-unconfigured",
                                         ledger=ledger, environ=unconfigured_env, **captured())))],
                "PROTECTED_OVERLAP")
        check("and nothing was created under the fixture's resolved state root",
              not (resolved_state / "out-unconfigured").exists(),
              f"{masked(resolved_state / 'out-unconfigured')} exists after a refused run")

        # ---- R2#1: a host home is where its variable says, not where the default says. The
        # protected sets read `NATIVE`'s literal defaults, so a home moved by `CODEX_HOME` or
        # `CLAUDE_CONFIG_DIR` was a writable destination and an admissible scratch parent for both
        # hosts. The rule has one owner — the shipped installer — and one reader here (`host_homes`),
        # used by all three sets. Both questions are asked with a fixture environment, so nothing
        # here depends on, or changes, this process's own.
        moved = scratch / "moved-host-homes"
        moved_env = {"HOME": str(moved / "home"), "CLAUDE_CONFIG_DIR": str(moved / "elsewhere/claude"),
                     "CODEX_HOME": str(moved / "elsewhere/codex")}
        for host in ("claude", "codex"):
            (moved / "elsewhere" / host).mkdir(parents=True)
        check("the configured homes are the ones the variables name, not the defaults",
              [str(root) for root in host_homes(moved_env)]
              == [moved_env["CLAUDE_CONFIG_DIR"], moved_env["CODEX_HOME"]],
              f"{[str(root) for root in host_homes(moved_env)]}")
        # The rule has one owner. Nothing this module EXECUTES may name either variable — a string
        # literal is how a second copy of the rule would read. Prose that explains the rule is not a
        # copy of it, so docstrings are excluded by construction rather than by a text search, and
        # the fixture environment above names them because that is this control saying what it means.
        def named_variables(source):
            tree = ast.parse(source)
            docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                          if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                          and node.body and isinstance(node.body[0], ast.Expr)
                          and isinstance(node.body[0].value, ast.Constant)
                          and isinstance(node.body[0].value.value, str)}
            return sorted({node.value for node in ast.walk(tree)
                           if isinstance(node, ast.Constant) and isinstance(node.value, str)
                           and id(node) not in docstrings
                           and node.value in ("CLAUDE_CONFIG_DIR", "CODEX_HOME")})
        module_code = pathlib.Path(__file__).read_text(encoding="utf-8").split("\ndef self_test(", 1)[0]
        check("and the owner of that rule is the shipped installer, not a copy of it here",
              not named_variables(module_code + "\n"),
              f"{named_variables(module_code)} named by this module's own code")
        control("this module reading a host-home variable for itself",
                named_variables('x = environ.get("CODEX_HOME")\n'), "CODEX_HOME")
        for host, variable in (("claude", "CLAUDE_CONFIG_DIR"), ("codex", "CODEX_HOME")):
            destination = pathlib.Path(moved_env[variable]) / "out"
            control(f"a production destination inside the configured {host} home",
                    [str(_raised(lambda destination=destination: run(
                        REPO, None, None, destination, ledger=ledger, environ=moved_env, **captured())))],
                    "PROTECTED_OVERLAP")
            check(f"and the attempted write under the configured {host} home did not happen",
                  not destination.exists(), f"{destination} exists after a refused run")
            inner_tmp = pathlib.Path(moved_env[variable]) / "tmp"
            inner_tmp.mkdir()
            control(f"a scratch parent inside the configured {host} home",
                    [str(_raised(lambda inner_tmp=inner_tmp: scratch_parent(
                        {**moved_env, "TMPDIR": str(inner_tmp)}, moved_env["HOME"])))],
                    "PROTECTED_OVERLAP")
            check(f"and that location under the configured {host} home was never written to",
                  not any(inner_tmp.iterdir()), f"{sorted(path.name for path in inner_tmp.iterdir())}")
        check("the same destinations are admissible when no variable moves the home, so the "
              "controls above are about the variables and not about the paths",
              not overlap_problems([pathlib.Path(moved_env["CODEX_HOME"]) / "out"],
                                   protected_roots(None, None, {}, environ={"HOME": str(moved / "home")})),
              "the destination overlaps a protected root even with the variables unset")

        # ---- R1#6: one admission point, and denying it stops every category of state-byte read.
        # `hash_tree` and `freeze` read their selected paths directly, so `source_selection` was a
        # claim about where reads pass rather than the gate they pass: denied outright, a fixture
        # still hashed eight files and copied one.
        admit_root = scratch / "admission"
        (admit_root / "runtime").mkdir(parents=True)
        (admit_root / "runtime" / "state.json").write_text("{}", encoding="utf-8")
        (admit_root / "runtime" / "second.json").write_text("{}", encoding="utf-8")
        open_digests, open_omissions = hash_tree(admit_root)
        check("the fixture has bytes to read, so the denial judges something",
              len(open_digests) == 2 and not open_omissions, f"{open_digests} {open_omissions}")
        kept_selection = globals()["source_selection"]
        denied_copy = scratch / "admission-denied-copy"
        try:
            def deny(path, boundary=None, home=None):
                raise Refused("SOURCE_DENIED: the fixture admits nothing")

            globals()["source_selection"] = deny
            denied_digests, denied_omissions = hash_tree(admit_root)
            denied_missing = freeze([(admit_root / "runtime", "runtime"),
                                     (admit_root / "runtime" / "state.json", "one.json")], denied_copy)
        finally:
            globals()["source_selection"] = kept_selection
        control("a hash over a tree the selection admits nothing of",
                [f"hashed={sorted(denied_digests)} "] + [row["reason"] for row in denied_omissions],
                "hashed=[]", "not admitted", "SOURCE_DENIED")
        control("a frozen copy of inputs the selection admits nothing of",
                [f"copied={sorted(path.name for path in denied_copy.rglob('*')) if denied_copy.exists() else []} "]
                + denied_missing,
                "copied=[]", "not admitted", "SOURCE_DENIED")
        check("every file of the fixture is accounted for as an omission rather than dropped",
              len(denied_omissions) == len(open_digests)
              and len([row for row in denied_missing if "not admitted" in row]) == len(open_digests) + 1,
              f"{denied_omissions} / {denied_missing}")

        was = sys.dont_write_bytecode
        sys.dont_write_bytecode = False  # the state the guard is supposed to change
        try:
            with no_bytecode():
                inside = sys.dont_write_bytecode
            restored = sys.dont_write_bytecode
        finally:
            sys.dont_write_bytecode = was
        check("the guard that keeps a path import from caching bytecode is on inside it", inside,
              "dont_write_bytecode was not set inside no_bytecode()")
        check("the guard leaves the interpreter as it found it", restored is False,
              "dont_write_bytecode stayed on after the guard")
        check("the command itself turns bytecode writing off before its own imports",
              was is True, "the entry point did not set dont_write_bytecode before importing its graph")
        check("the interpreter would otherwise write bytecode, so the guard has a subject",
              not sys.flags.dont_write_bytecode, "this interpreter never writes bytecode, so the guard proves nothing")
        guarded_loads = loads_outside_the_guard(pathlib.Path(__file__).read_text(encoding="utf-8"))
        control("a module loaded by path outside the no-bytecode guard",
                loads_outside_the_guard(pathlib.Path(__file__).read_text(encoding="utf-8").replace(
                    "with no_bytecode():\n        spec.loader.exec_module(module)",
                    "if True:\n        spec.loader.exec_module(module)", 1)),
                "LOAD_UNGUARDED")
        clean("every module this reads by path is loaded under the guard", guarded_loads)

        saved = globals()["LAYERS"]

        # A producer's own failure is absorbed into its layer status by design, so the error path
        # here is the artifact write: the destination is an existing file, which fails after the
        # planted write has landed.
        failing_out = scratch / "failed"
        failing_out.write_text("not a directory", encoding="utf-8")

        try:
            globals()["LAYERS"] = (("catalog", {"current": ("a producer that writes", writing_producer)}),)
            control("a write is reported even when the inventory failed afterwards",
                    [str(_raised(lambda: run(REPO, state, user, failing_out, ledger=ledger)))],
                    "STATE_WRITTEN", "in flight")
        finally:
            globals()["LAYERS"] = saved
            planted_write.unlink(missing_ok=True)

        link = state / "runtime" / "a-link-out.json"
        link.symlink_to(scratch / "project" / "CLAUDE.md")
        try:
            manifest = run(REPO, state, user, scratch / "manifest-out", ledger=ledger)
        finally:
            link.unlink()
        inputs = manifest["inputs"]
        check("the input manifest declares the symlink policy and names the symlink it left out",
              SYMLINK_POLICY in inputs["symlink_policy"]
              and any(entry["reason"] == "symlink" and entry["path"] == "runtime/a-link-out.json"
                      for entry in inputs["roots"][str(state)]["omissions"]),
              f"{inputs['roots'][str(state)]['omissions']}")
        # ---- GB#8: a link inside a tree a run really copies is omitted, never followed
        outside = scratch / "outside-the-root"
        outside.write_text("bytes from outside the declared root\n", encoding="utf-8")
        planted_links = {"baseline": state / "runtime" / "baselines" / "ref1" / "linked.json",
                         "learnings": user / "learnings" / "linked.jsonl"}
        (user / "learnings").mkdir(parents=True, exist_ok=True)
        for link in planted_links.values():
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(outside)
        frozen_probe = scratch / "frozen-probe"
        left_out = freeze([(state / "runtime" / "baselines" / "ref1", "baseline"),
                           (user / "learnings", "learnings")], frozen_probe)
        control("a link inside a tree the run copies",
                left_out, "baseline/linked.json: symlink", "learnings/linked.jsonl: symlink")
        check("the bytes outside the declared root are not in the frozen copy",
              not any(path.is_file() and "outside the declared root" in path.read_text(encoding="utf-8", errors="replace")
                      for path in frozen_probe.rglob("*")),
              "a frozen copy carries bytes from outside the root it declared")
        check("the files beside the link were copied",
              (frozen_probe / "baseline" / "inventory.json").is_file(),
              "the walker dropped the files it should have copied")
        for link in planted_links.values():
            link.unlink()

        check("the input manifest names every root it read and every protected root",
              set(inputs["roots"]) == {str(state), str(user)} and str(state) in inputs["protected_roots"],
              f"{sorted(inputs['roots'])} / {inputs['protected_roots']}")

        # ---- GA#0: a credential or a home path planted in every personal carrier kind, and in the
        # session's compiled text, reaches no artifact — while the hashes still bind to the raw carrier
        secret = "sk-ant-api03-" + "Ab3" * 14
        private = str(pathlib.Path.home() / "Documents" / "a-directory-of-the-owner-s")
        tainted = f"\n- a rule naming {private}, with apiKeyHelper: {secret}\n"
        planted_in = {
            "native_global": "# Global\n\n- a native rule\n" + tainted,
            "native_project": "# Project\n\n- a project rule\n" + tainted,
            "native_memory": "---\nname: one\n---\n\n- a fact\n" + tainted,
        }
        store = store_module(REPO)
        injected = f"# Session\n\n- a compiled rule naming {private}, with apiKeyHelper: {secret}\n"
        snapshot_inputs = {"baseline_ref": "ref1", "host": "claude", "selection": ["@fixture/core:item-1"]}
        content_ref = store._digest(snapshot_inputs)
        snapshot_dir = state / "sessions" / "snapshots" / content_ref
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "CLAUDE.md").write_text(injected, encoding="utf-8")
        output = {"instruction_text": injected, "files": ["CLAUDE.md"], "assets": {},
                  "item_refs": ["@fixture/core:item-1"], "unavailable": []}
        (snapshot_dir / "output.json").write_text(json.dumps(output), encoding="utf-8")
        (snapshot_dir / "inventory.json").write_text(json.dumps({
            "inputs": snapshot_inputs, "items": [{"ref": "@fixture/core:item-1"}],
            "file_digests": {name: store._digest((snapshot_dir / name).read_bytes())
                             for name in ("CLAUDE.md", "output.json")}}), encoding="utf-8")
        (state / "sessions" / "pins" / "claude" / "session-1.json").write_text(
            json.dumps({"schema_version": 1, "content_ref": content_ref,
                        "created": "2026-10-04T12:00:00+00:00"}), encoding="utf-8")
        # The planted credentials travel the way the owner's text really reaches this inventory now:
        # inside what a transcript records as delivered.
        planted_path = jsonl(scratch / "transcripts" / "claude" / "session-1.jsonl", [
            attachment("2026-10-04T11:00:00+00:00",
                       [member("User", "~/.claude/CLAUDE.md", planted_in["native_global"]),
                        member("Project", f"{project_scope}/CLAUDE.md", planted_in["native_project"]),
                        member("AutoMem", "~/.claude/projects/p/memory/one.md", planted_in["native_memory"])],
                       cwd=project_scope, prompt=f"<system-reminder>\n{injected}</system-reminder>\n")])
        run_planted = scratch / "run-planted"
        run_planted.mkdir(parents=True, exist_ok=True)
        (run_planted / CENSUS).write_text(json.dumps({"transcripts": [
            census_row("claude", "session-1", planted_path)]}), encoding="utf-8")
        planted_out = scratch / "planted-out"
        manifest = run(REPO, state, user, planted_out, pin="claude:session-1",
                       native_roots={"projects": {"project": scratch / "project"}},
                       run_dir=run_planted, ledger=ledger, commit="fixture")
        artifacts = sorted(path for path in planted_out.rglob("*") if path.is_file())
        check("the planted run wrote artifacts to scan", len(artifacts) >= len(REFERENCES),
              f"{len(artifacts)} artifact(s)")
        leaking = sorted(path.name for path in artifacts
                         if secret in path.read_text(encoding="utf-8") or private in path.read_text(encoding="utf-8"))
        check("no artifact carries the planted credential or the owner's home path", not leaking,
              f"{leaking}")
        emitted = {}
        for reference in REFERENCES:
            for unit in json.loads((planted_out / "inventory" / f"{reference}.json").read_text(encoding="utf-8"))["units"]:
                emitted.setdefault(unit["path"], []).append(unit)
        for layer, raw_text in planted_in.items():
            carried = [unit for units_for in emitted.values() for unit in units_for
                       if unit["layer"] == layer and unit["version_sha256"] == sha256_text(raw_text)]
            check(f"the {layer} carrier's units still hash to the raw carrier", bool(carried),
                  f"no unit of {layer} carries the raw carrier's sha256")
            check(f"the {layer} carrier's text is masked in the artifact",
                  all(secret not in unit["text"] and private not in unit["text"] for unit in carried)
                  and any("<REDACTED>" in unit["text"] or "<HOME>" in unit["text"] for unit in carried),
                  f"{layer} produced no masked unit")
            check(f"the {layer} carrier still names the floor that masked it",
                  all(unit.get("redaction_version") == projection.CURRENT for unit in carried), "no redaction_version")
        session_units = [unit for units_for in emitted.values() for unit in units_for
                         if unit["layer"] == "session_injection"]
        check("the session's compiled text was read at all", bool(session_units),
              f"the pin produced no session_injection unit: "
              f"{[(r, m['layers'].get('session_injection')) for r, m in manifest['references'].items()]}")
        check("the session's compiled text is masked too",
              all(secret not in unit["text"] and private not in unit["text"] for unit in session_units)
              and any("<REDACTED>" in unit["text"] or "<HOME>" in unit["text"] for unit in session_units),
              "the session's units carry the planted credential or home path")
        kept_project = projection.project
        try:  # a floor that masks nothing: the guard beyond it is what the control reads
            projection.project = lambda text, version=None, home=None: text
            control("a unit the floor left a credential in is never emitted",
                    [str(_raised(lambda: projected(f"apiKeyHelper: {secret}\n", None)))], "DISCLOSED_IN_UNIT")
        finally:
            projection.project = kept_project
        check("the floor itself does mask that unit, so the guard is a second line, not the first",
              secret not in projected(f"apiKeyHelper: {secret}\n", None), "the floor passed the credential through")

        # ---- GA#0 (security review): the fields beside `text`, and the boundary that does not
        # depend on remembering them
        heading_secret = f"## A heading naming apiKeyHelper {secret} and {private}\n"
        headed = shed(units_of([guide("headed.md", heading_secret + "\n- a rule under it\n")]), home=str(pathlib.Path.home()))
        check("a secret in a heading line is masked in every unit that carries the heading",
              all(secret not in unit["heading"] and private not in unit["heading"] for unit in headed)
              and all(secret not in unit["text"] for unit in headed),
              "a heading carried the planted credential into the artifact")
        absolute = {"ref": "@vendor/pkg:abs", "item_id": "abs", "kind": "guide", "package_id": "@vendor/pkg",
                    "title": "Abs", "surface": "relevant", "tier": "env-team", "domains": ["personal"],
                    "primary_member": "guides/abs.md", "members": {},
                    "origin": {"source_path": f"{pathlib.Path.home()}/Documents/private-checkout/guides/abs.md"},
                    "body": "- a rule from a path on the owner's disk\n"}
        absolute_units = shed(units_of(item_carriers(absolute, "adopted_packages")), home=str(pathlib.Path.home()))
        check("an absolute source path is masked in the unit's own path field",
              all(str(pathlib.Path.home()) not in unit["path"] for unit in absolute_units)
              and any("<HOME>" in unit["path"] for unit in absolute_units),
              f"{[unit['path'] for unit in absolute_units]}")
        hiding = {"home": str(pathlib.Path.home())}
        check("an acquisition failure records the exception's type and a masked message",
              "OSError" in projected_message(OSError(f"cannot read {pathlib.Path.home()}/Documents/x"), hiding["home"])
              and str(pathlib.Path.home()) not in projected_message(
                  OSError(f"cannot read {pathlib.Path.home()}/Documents/x"), hiding["home"]),
              "the exception message carried the owner's home path")
        manifest_text = (planted_out / "inventory" / "manifest.json").read_text(encoding="utf-8")
        check("the manifest carries no owner home prefix", str(pathlib.Path.home()) not in manifest_text,
              "the manifest holds an absolute path under the owner's home")
        under_home = pathlib.Path.home() / "Documents" / "a-run-directory"
        check("a path the manifest records is masked with the projection's own mask",
              "<HOME>" in masked(under_home, str(pathlib.Path.home()))
              and str(pathlib.Path.home()) not in masked(under_home, str(pathlib.Path.home())),
              f"{masked(under_home, str(pathlib.Path.home()))}")
        control("a manifest that recorded its own paths unmasked",
                disclosure_problems({"out_dir": str(under_home)}, str(pathlib.Path.home())),
                "DISCLOSED_IN_ARTIFACT $.out_dir", "home path")
        clean("the same manifest with the paths masked",
              disclosure_problems({"out_dir": masked(under_home, str(pathlib.Path.home()))},
                                  str(pathlib.Path.home())))
        control("a document holding a string nothing projected",
                disclosure_problems({"layers": [{"reasons": [f"read {pathlib.Path.home()}/Documents/x"]}]},
                                    str(pathlib.Path.home())),
                "DISCLOSED_IN_ARTIFACT", "$.layers[0].reasons[0]", "home path")
        # ---- GB#6: a credential relationship, and a refusal that repeats nothing
        # `api_key` is not a member name this module's documents carry, so the location is its
        # ordinal rather than its spelling: a key is untrusted text wherever it stands (GC#5).
        control("a short value under a credential-named key",
                disclosure_problems({"api_key": "shortpass"}, str(pathlib.Path.home())),
                "DISCLOSED_IN_ARTIFACT $[key #0]", "credential-named member")
        clean("the same member carrying the mask instead",
              disclosure_problems({"api_key": "<REDACTED>"}, str(pathlib.Path.home())))
        # One control here, because the rules and every representation they must read are the
        # floor's own table (`projection.py --self-test`): a nested credential reaches the write
        # boundary and is refused by location, through that one entry point.
        control("a credential nested inside a plain structure reaching the write boundary",
                disclosure_problems({"layers": [{"notes": {"api_key": "shortpass"}}]},
                                    str(pathlib.Path.home())),
                "DISCLOSED_IN_ARTIFACT $.layers[0].notes[key #0]", "credential-named member")
        clean("the same structure masked through and through",
              disclosure_problems({"layers": [{"notes": {"api_key": "<REDACTED>"}}]},
                                  str(pathlib.Path.home())))
        # The location names a member of a schema this code owns, and nothing else. An ordinary short
        # secret as a nested key is an ordinary word to find there, and naming it repeated it.
        nested = disclosure_problems({"api_key": {"shortpass": {"token": "x"}}}, str(pathlib.Path.home()))
        control("an ordinary short secret as a nested key", [f"rows={len(nested)} "
                + " ".join(nested)], "[key #0]")
        check("and the refusal repeats none of it",
              bool(nested) and not any("shortpass" in row for row in nested), f"{nested}")
        # A schema that declared a credential name would license naming one, so the floor is asked
        # about every entry rather than trusted to have none.
        leaky = sorted(name for name in DOCUMENT_KEYS if projection.secret_key(name))
        check("no member name this module declares is a name the floor calls a credential",
              not leaky and len(DOCUMENT_KEYS) > 40, f"{leaky} of {len(DOCUMENT_KEYS)}")
        keyed = disclosure_problems({f"apiKeyHelper {secret}": str(pathlib.Path.home())},
                                    str(pathlib.Path.home()))
        control("a document carrying a credential as a key", keyed, "DISCLOSED_IN_ARTIFACT")
        check("the refusal repeats neither the credential nor the home path",
              all(secret not in problem and str(pathlib.Path.home()) not in problem for problem in keyed),
              "the refusal interpolated the untrusted key")
        check("the boundary names where the string sits and not what it said",
              all(str(pathlib.Path.home()) not in problem for problem in disclosure_problems(
                  {"reasons": [f"read {pathlib.Path.home()}/Documents/x"]}, str(pathlib.Path.home()))),
              "the refusal repeated the string it objected to")
        stage_dir = scratch / "stage-probe" / "stages" / "S2"
        stage_dir.mkdir(parents=True)
        (stage_dir / "record.json").write_text(json.dumps(
            {"stage": "S2", "parts": {"inventory": {"outputs": [{"artifact": f"{pathlib.Path.home()}/x.json"}]}}}),
            encoding="utf-8")
        control("a stage record naming a path under the owner's home",
                stage_record_problems(scratch / "stage-probe", "S2", str(pathlib.Path.home())),
                "DISCLOSED_IN_ARTIFACT", "home path")
        clean("a stage record of this run as the inventory writes one",
              stage_record_problems(scratch / "no-such-run", "S2", str(pathlib.Path.home())))
        control("a run whose document reaches the write boundary unprojected",
                [str(_raised(lambda: write_document(scratch / "boundary-out",
                                                    scratch / "boundary-out" / "inventory" / "current.json",
                                                    {"units": [{"text": f"see {pathlib.Path.home()}/Documents/x"}]},
                                                    str(pathlib.Path.home()))))],
                "DISCLOSED_IN_ARTIFACT")
        check("the refused document was never written",
              not (scratch / "boundary-out").exists(), "a refused document still reached the disk")

        # ---- the 1548 amendment: the native layers come from the transcript, settings never do,
        # and nothing reads a native file in any mode
        split_out = scratch / "split-out"
        split = run(REPO, state, user, split_out, ledger=ledger, **captured())
        split_doc = json.loads((split_out / "inventory" / "current.json").read_text(encoding="utf-8"))
        native_rows = {row["layer"]: row for row in split_doc["layers"] if row["layer"] in NATIVE_LAYERS}
        check("every native layer is in the table", set(native_rows) == set(NATIVE_LAYERS),
              f"{sorted(native_rows)}")
        check("the layers a transcript records answer at the current reference point",
              all(native_rows[layer]["status"] == "complete" for layer in TRANSCRIPT_LAYERS),
              f"{[(layer, native_rows[layer]['status'], native_rows[layer]['reasons']) for layer in TRANSCRIPT_LAYERS]}")
        control("the settings layer, which no transcript carries and no mode reads",
                [f"native_settings={native_rows['native_settings']['status']}: "
                 + "; ".join(native_rows["native_settings"]["reasons"])],
                "native_settings=unknown", "settings file is carried by no transcript")
        check("a reference point missing the settings layer is incomplete",
              split["references"]["current"]["complete"] is False,
              "a reference point with an unknown layer reported complete")
        check("the current native layers carry when and from whom they came",
              all(unit["provenance"].get("as_of") and unit["provenance"].get("session")
                  for unit in split_doc["units"] if unit["layer"] in TRANSCRIPT_LAYERS),
              "a current native unit carries no as_of or no session")
        check("the run's artifact names no mode that reads a host home",
              "mode" not in split_doc["produced_by"] and split["inputs"]["transcripts"]["native_files_read"] == 0,
              f"{sorted(split_doc['produced_by'])}")
        # A run with no census at all: every native layer unknown, with the census reason.
        blind_out = scratch / "blind-out"
        blind = run(REPO, state, user, blind_out, ledger=ledger,
                    native_roots={"projects": {"project": scratch / "project"}})
        blind_rows = {row["layer"]: row for row in json.loads(
            (blind_out / "inventory" / "current.json").read_text(encoding="utf-8"))["layers"]}
        control("a run with no census to read a transcript through",
                [f"{layer}={blind_rows[layer]['status']}: " + "; ".join(blind_rows[layer]["reasons"])
                 for layer in TRANSCRIPT_LAYERS],
                "native_global=unknown", "INPUT_UNACQUIRED")
        check("a run with no census is incomplete", blind["references"]["current"]["complete"] is False,
              "a run that bound no transcript reported complete")

        # ---- GA#5: a malformed supported carrier is incomplete, not unsupported, and says which
        control("a settings file with a missing brace",
                [str(_raised(lambda: units_of([carrier("native_settings", "settings.json", '{"hooks": {}\n')])))],
                "not valid JSON")
        control("a Codex settings file that is not TOML",
                [str(_raised(lambda: units_of([carrier("native_settings", "config.toml", "model = \n")])))],
                "not valid TOML" if tomllib is not None else "no TOML reader")
        kept_toml = globals()["tomllib"]
        try:  # an interpreter without a TOML reader cannot prove the carrier well formed, so it says so
            globals()["tomllib"] = None
            control("a TOML settings file on an interpreter with no TOML reader",
                    [str(_raised(lambda: units_of([carrier("native_settings", "config.toml", "model = 'x'\n")])))],
                    "no TOML reader")
        finally:
            globals()["tomllib"] = kept_toml
        check("this interpreter does have a TOML reader, so that branch is a fallback and not the rule",
              tomllib is not None, "no tomllib here: the malformed-TOML control above judges nothing")
        broken_rows = [{"layer": "native_settings", "producer": "a settings file with a missing brace",
                        "status": "complete", "reasons": [],
                        "carriers": [carrier("native_settings", "settings.json", '{"hooks": {}\n')]}]
        produce(broken_rows)
        control("the layer a malformed settings file belongs to",
                [f"{broken_rows[0]['status']}: {'; '.join(broken_rows[0]['reasons'])}"],
                "incomplete", "not valid JSON")
        check("a malformed supported carrier is not reported as unsupported",
              broken_rows[0]["status"] == "incomplete", f"{broken_rows[0]['status']}")
        markdown_in_json = units_of([carrier("session_injection", "snapshot:x/output.json#instruction_text",
                                             "# A heading\n\n- a rule\n", form="markdown")])
        check("a declared form reads a markdown member of a JSON file as markdown",
              [unit["block"] for unit in markdown_in_json][:1] == ["heading"],
              f"{[unit['block'] for unit in markdown_in_json][:2]}")

        # ---- GA#5: a failure acquiring the inputs still leaves a layer-status artifact naming it
        brittle = scratch / "brittle-state"
        (brittle / "runtime").mkdir(parents=True)
        (brittle / "runtime" / "state.json").write_text('{"schema_version": 1,\n', encoding="utf-8")
        brittle_out = scratch / "brittle-out"
        brittle_manifest, brittle_failure = {"references": {}}, None
        try:  # the subject is guarded: a run that raises makes this control fail, not the suite abort
            brittle_manifest = run(REPO, brittle, user, brittle_out, ledger=ledger)
        except Exception as exc:
            brittle_failure = exc
        control("a run whose input freezing failed",
                ([f"the run raised instead of reporting it: {type(brittle_failure).__name__}: {brittle_failure}"]
                 if brittle_failure is not None else
                 [reason for entry in brittle_manifest["references"].values() for reason in entry["incomplete_reasons"]]),
                "INPUT_UNACQUIRED")
        check("the failed acquisition still wrote a layer-status artifact per reference point",
              all((brittle_out / "inventory" / f"{reference}.json").is_file() for reference in REFERENCES),
              "a reference point lost its artifact to the acquisition failure")
        brittle_current = brittle_out / "inventory" / "current.json"
        brittle_layers = (json.loads(brittle_current.read_text(encoding="utf-8"))["layers"]
                          if brittle_current.is_file() else [])
        check("every layer of that artifact carries a status and the cause",
              len(brittle_layers) == len(LAYERS)
              and all(row["status"] == "unknown" and row["reasons"] for row in brittle_layers),
              f"{[row['status'] for row in brittle_layers]}")

        # ---- GA#6, GA#7, GA#8: adopted packages, overlays per host, and both baselines frozen
        adopted_item = {"ref": "@vendor/pkg:guide-1", "item_id": "guide-1", "kind": "guide",
                        "package_id": "@vendor/pkg", "title": "Vendor", "surface": "relevant",
                        "tier": "env-team", "domains": ["personal"], "primary_member": "guides/vendor.md",
                        "members": {"guides/vendor.md": "## Vendor\n\n- a rule the owner adopted\n"},
                        "origin": {"source_path": "claude/guides/vendor.md"}, "body": "- a rule the owner adopted\n"}
        upgraded = {"schema_version": 1, "packages": [{"package_id": "@fixture/core"}, {"package_id": "@vendor/pkg"}],
                    "items": baseline["items"] + [adopted_item]}
        (state / "runtime" / "baselines" / "ref2").mkdir(parents=True)
        (state / "runtime" / "baselines" / "ref2" / "inventory.json").write_text(json.dumps(upgraded), encoding="utf-8")
        (state / "runtime" / "baselines" / "ref2" / "defaults.json").write_text(
            json.dumps({"schema_version": 1, "selected": [item["ref"] for item in upgraded["items"]]}), encoding="utf-8")
        (state / "runtime" / "state.json").write_text(json.dumps(
            {"schema_version": 1, "selected_baseline_ref": "ref2", "last_successful_install_ref": "ref2"}),
            encoding="utf-8")
        learned = {"claude": "- a rule this host learned\n", "codex": "- a rule the other host learned\n"}
        for one, lesson in learned.items():
            (user / "learnings" / one).mkdir(parents=True, exist_ok=True)
            (user / "learnings" / one / "events.jsonl").write_text(json.dumps(
                {"learning_id": f"L-{one}", "lesson": lesson, "domain": "personal"}) + "\n", encoding="utf-8")
        suppressed_event = {"learning_id": "L-suppressed", "lesson": "- a rule the owner suppressed\n",
                            "domain": "personal"}
        with (user / "learnings" / "claude" / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(suppressed_event) + "\n")
        (user / "state.json").write_text(json.dumps(
            {"schema_version": 1, "items": {}, "overrides": {}, "tombstones": {"@fixture/core:item-3": {"reason": "dropped"}},
             "selection": None,
             "learning_suppressions": {"claude": [store._digest(suppressed_event)], "codex": []}}), encoding="utf-8")
        both_out = scratch / "both-out"
        both = run(REPO, state, user, both_out, pin="claude:session-1",
                   ledger=ledger, commit="fixture", **captured())
        current_doc = json.loads((both_out / "inventory" / "current.json").read_text(encoding="utf-8"))
        notes = current_doc["produced_by"]["notes"]
        control("a run whose pin names an older baseline than the installed one",
                [f"installed={notes['baselines']['installed']} pinned={notes['baselines']['pinned']} "
                 f"differ={notes['baselines']['differ']}"],
                "installed=ref2", "pinned=ref1", "differ=True")
        frozen_both = [row for row in notes.get("frozen_missing", []) if "baselines" in row]
        check("both baselines were frozen, so neither resolver is left without its tuple", not frozen_both,
              f"{frozen_both}")
        # The schema is a contract, not a second list: the real document's units and layer rows are
        # validated against it, so a record that drifts fails here too (the 1548 amendment §10).
        clean("a produced document's units and layer rows against the schema the code owns",
              document_contract_problems(current_doc))
        check("that document really has units to judge", len(current_doc["units"]) > 100,
              f"{len(current_doc['units'])} unit(s)")
        control("a unit whose carrier id is not the opaque identity the schema declares",
                document_contract_problems({**current_doc, "units": [
                    {**current_doc["units"][0], "carrier_id": f"catalog\0claude/guides/x.md"}]}),
                "DOCUMENT_INVALID")
        control("a layer row naming a layer the schema does not declare",
                document_contract_problems({**current_doc, "layers": [
                    {**current_doc["layers"][0], "layer": "a_layer_nobody_declared"}]}),
                "DOCUMENT_INVALID")
        overlay_row = next(row for row in current_doc["layers"] if row["layer"] == "overlays")
        check("the overlay layer resolved rather than failing on a missing baseline",
              overlay_row["status"] == "complete", f"{overlay_row['status']}: {overlay_row['reasons']}")
        overlay_units = [unit for unit in current_doc["units"] if unit["layer"] == "overlays"]
        learned_texts = {unit["text"] for unit in overlay_units}
        check("every host in scope contributed its learned rule",
              all(any(lesson.strip() in text for text in learned_texts) for lesson in learned.values()),
              f"{sorted(learned_texts)}")
        control("a learned rule the owner suppressed",
                [f"suppressed present: {any('suppressed' in text for text in learned_texts)}"],
                "suppressed present: False")
        hosts_named = {host for unit in overlay_units for host in unit["provenance"].get("hosts", [])}
        check("an overlay carries the hosts it resolved for", hosts_named == {"claude", "codex"},
              f"{sorted(hosts_named)}")
        check("an item both hosts share is one carrier, not two",
              len({unit["carrier_id"] for unit in overlay_units}) == len(overlay_units),
              "the same overlay carrier was emitted twice")
        check("a tombstoned item is not in the overlay layer",
              not any(unit["item_ref"] == "@fixture/core:item-3" for unit in overlay_units),
              "a tombstoned item came back as an overlay")
        adopted_rows = {reference: [unit for unit in json.loads(
            (both_out / "inventory" / f"{reference}.json").read_text(encoding="utf-8"))["units"]
            if unit["layer"] == "adopted_packages"] for reference in REFERENCES}
        control("a run with no state root to read the adoption record from",
                [str(_raised(lambda: _packages_current(context_of(REPO, None, None, {}, None, None))))],
                "PRODUCER_UNAVAILABLE adopted_packages")
        control("a reference point whose adopted packages were read from the checkout catalog",
                [f"from the checkout: {len(catalog_carriers(REPO, layer='adopted_packages', adopted=True))}; "
                 f"from the owner's state: {len(adopted_rows['current'])}"],
                "from the checkout: 0", "from the owner's state:")
        check("the adopted package's units are in the current reference point",
              any(unit["package_id"] == "@vendor/pkg" for unit in adopted_rows["current"]),
              f"{sorted({unit['package_id'] for unit in adopted_rows['current']})} / "
              f"{[row for row in current_doc['layers'] if row['layer'] == 'adopted_packages']}")
        check("the adopted package's units are in the release reference point it was installed from",
              any(unit["package_id"] == "@vendor/pkg" for unit in adopted_rows["release"])
              or notes["baselines"]["pinned"] == "ref1",
              "the release reference point lost the adopted package")

        # ---- GC#1: the temporary location is chosen and judged before anything is written
        guarded_tmp = scratch / "guarded-tmp"
        inner_tmp = guarded_tmp / "tmp"
        inner_tmp.mkdir(parents=True)
        # The environment under test is stated as an argument rather than installed in this process:
        # the old control updated `os.environ` and then POPPED `TMPDIR`, so every later `tempfile`
        # call in this suite resolved somewhere else than the parent the suite was given.
        control("a temporary location inside a protected root",
                [str(_raised(lambda: temp_home([guarded_tmp], str(pathlib.Path.home()),
                                               {"TMPDIR": str(inner_tmp)})))],
                "PROTECTED_OVERLAP")
        check("and the refused location was never written to",
              not any(inner_tmp.iterdir()), f"{sorted(path.name for path in inner_tmp.iterdir())}")
        chosen = temp_home([guarded_tmp], str(pathlib.Path.home()))
        check("the chosen temporary location is a directory outside every protected root",
              chosen.is_dir() and not chosen.is_relative_to(guarded_tmp), f"{masked(chosen)}")
        control("no temporary location outside the protected roots at all",
                [str(_raised(lambda: temp_home([pathlib.Path("/")], str(pathlib.Path.home()))))],
                "PROTECTED_OVERLAP")

        # ---- R1#5: the SELF-TEST's own scratch parent is chosen by the same path-only rule. Both
        # suites asked `tempfile` for one, and `tempfile` resolves `TMPDIR` by PROBING it — so an
        # ordinary `TMPDIR` inside a checkout's `.tmp`, or inside the owner's state root, put every
        # fixture, the checkout copy and the cleanup inside a protected root before production's
        # preflight could refuse anything. It is the SELECTION under test: one call with a fixture
        # environment, not a recursive run of the suite.
        fixture_checkout = scratch / "scratch-parent-checkout"
        (fixture_checkout / ".tmp").mkdir(parents=True)
        fixture_state = scratch / "scratch-parent-state"
        (fixture_state / "tmp").mkdir(parents=True)
        for where, parent, roots in (
                ("the checkout's own .tmp", fixture_checkout / ".tmp", {"checkout": fixture_checkout}),
                ("the owner's state root", fixture_state / "tmp", {"state_root": fixture_state,
                                                                   "checkout": fixture_checkout}),
                ("the owner's authoring root", fixture_state / "tmp", {"user_root": fixture_state,
                                                                       "checkout": fixture_checkout})):
            control(f"a self-test scratch parent inside {where}",
                    [str(_raised(lambda parent=parent, roots=roots: scratch_parent(
                        {"TMPDIR": str(parent)}, str(pathlib.Path.home()), **roots)))],
                    "PROTECTED_OVERLAP")
        check("and neither refused location was written to",
              not any((fixture_checkout / ".tmp").iterdir()) and not any((fixture_state / "tmp").iterdir()),
              f"{sorted(path.name for path in (fixture_checkout / '.tmp').iterdir())} "
              f"{sorted(path.name for path in (fixture_state / 'tmp').iterdir())}")
        outside = scratch / "scratch-parent-outside"
        outside.mkdir()
        check("a scratch parent outside every protected root is accepted as given",
              scratch_parent({"TMPDIR": str(outside)}, str(pathlib.Path.home()),
                             state_root=fixture_state, checkout=fixture_checkout) == outside,
              f"{masked(scratch_parent({'TMPDIR': str(outside)}, str(pathlib.Path.home())))}")
        # The reader of the rule is this suite itself: everything it has written lives under the
        # parent that call returned. (`scratch_parent()` is not called again here — a control above
        # has since taken `TMPDIR` out of this process's environment.)
        check("this suite's own fixtures really are under a parent this rule chose",
              scratch.parent == SELF_TEST_SCRATCH_PARENT[0]
              and scratch.is_relative_to(SELF_TEST_SCRATCH_PARENT[0]),
              f"{masked(scratch.parent)} vs {masked(SELF_TEST_SCRATCH_PARENT[0])}")

        # The rule lives in `run`, so this control runs one: the temporary location is where the
        # frozen copies of the owner's state are made, and gettempdir() picks one by writing to it.
        protected_tmp = state / "tmpdir"
        protected_tmp.mkdir(parents=True, exist_ok=True)
        held_tmpdir = os.environ.get("TMPDIR")
        os.environ["TMPDIR"] = str(protected_tmp)
        try:
            control("a run whose temporary location is inside a protected root is refused before it freezes anything",
                    [str(_raised(lambda: run(REPO, state, user, scratch / "tmp-out", ledger=ledger, **captured())))],
                    "PROTECTED_OVERLAP")
            check("and the refused run left that temporary location empty",
                  not any(protected_tmp.iterdir()),
                  f"{sorted(path.name for path in protected_tmp.iterdir())}")
            check("and wrote no artifact either", not (scratch / "tmp-out").exists(),
                  "a refused run still wrote its output directory")
        finally:
            if held_tmpdir is None:
                os.environ.pop("TMPDIR", None)
            else:
                os.environ["TMPDIR"] = held_tmpdir
            protected_tmp.rmdir()

        # ---- GC#0: every copy destination is confined, and every label is an identifier
        control("a copy label that climbs out of the frozen destination",
                [str(_raised(lambda: confined(scratch / "frozen", "../outside/x")))], "DESTINATION_ESCAPES")
        control("an absolute copy label", [str(_raised(lambda: confined(scratch / "frozen", "/etc/passwd")))],
                "DESTINATION_ESCAPES")
        check("a plain label lands inside the destination",
              confined(scratch / "frozen", "state/runtime/state.json").is_relative_to(scratch / "frozen"),
              "a confined label landed outside")
        for kind, value in (("pin host", "../../etc"), ("pin session id", "a/b"),
                            ("snapshot content_ref", "sha256:../x")):
            control(f"a {kind} that is not an identifier this run builds a path from",
                    [str(_raised(lambda value=value, kind=kind: safe_label(kind, value)))], "INPUT_INVALID")
        escaping = scratch / "frozen-escape"
        control("a freeze whose label would write outside the frozen copy",
                [str(_raised(lambda: freeze([(scratch / "project", "../escaped")], escaping)))],
                "DESTINATION_ESCAPES")
        check("and nothing was written beside the frozen copy",
              not (scratch / "escaped").exists(), "a confined freeze still wrote outside")

        # ---- GC#4: a credential whose key the splitter left in the previous block
        pair = carrier("catalog", "claude/guides/keys.md",
                       '## Keys\n\n- the helper reads api_key:\n\n  "Ab3Ab3Ab3Ab3Ab3Ab3"\n')
        pair_units = units_of([pair])
        value_unit = next(unit for unit in pair_units if "Ab3Ab3" in unit["text"])
        emitted_pair = shed([value_unit], str(pathlib.Path.home()))[0]
        control("a credential value emitted with its key in the block before it",
                [f"emitted={emitted_pair['text'].strip()}"], "REDACTED")
        check("the span projected without its carrier context is what kept the value",
              "Ab3Ab3" in projected(value_unit["text"], str(pathlib.Path.home())),
              "the floor masks the value on its own, so this control judges nothing")
        check("the emitted unit still hashes to the raw fragment",
              emitted_pair["sha"] == sha256_text(value_unit["text"]), "the context changed the hash")
        # The context is the carrier's own, not a window of it. Two preceding nonblank lines do not
        # preserve a credential's structural context: the key falls outside as soon as the value is a
        # list with blank lines in it, and the last element was emitted with nothing to mark it.
        far = carrier("catalog", "claude/guides/far.md",
                      '## Keys\n\napi_key: [\n  "alpha",\n\n  "bravo",\n\n  "shortpass"\n]\n')
        far_units = units_of([far])
        far_value = next(unit for unit in far_units if "shortpass" in unit["text"])
        far_emitted = shed(far_units, str(pathlib.Path.home()))
        control("a credential whose key sits more than two nonblank lines above the value",
                [f"emitted={next(row['text'] for row in far_emitted if row['unit_id'] == far_value['unit_id']).strip()}"],
                "REDACTED")
        check("that value really does survive the floor on its own, so the control judges something",
              "shortpass" in projected(far_value["text"], str(pathlib.Path.home())),
              "the floor masks the block on its own")
        check("and nothing the carrier holds reaches any emitted span",
              not any("shortpass" in row["text"] or "alpha" in row["text"] for row in far_emitted),
              f"{[row['text'] for row in far_emitted]}")
        # A credential whose VALUE spans lines, cut by the splitter in the middle of itself: the
        # fragment is part of one value, and a fragment of a credential is a credential.
        multi = carrier("catalog", "claude/guides/multi.md",
                        '## Keys\n\napi_key: "alpha\nbravo\n\nshortpass"\n')
        multi_emitted = shed(units_of([multi]), str(pathlib.Path.home()))
        control("a multi-line credential fragment the splitter cut in two",
                [f"emitted={[row['text'] for row in multi_emitted]}"], "REDACTED")
        check("no line of the multi-line value reaches an emitted span",
              not any("shortpass" in row["text"] or "bravo" in row["text"] for row in multi_emitted),
              f"{[row['text'] for row in multi_emitted]}")
        # The whole way out, for the fixture that reached publication: split, shed, and the REAL
        # writer, to a file this control then reads back. The floor WITHHOLDS this carrier — the
        # escape in it makes the carrier undecodable — and span projection published a later block
        # of it regardless; the write boundary accepted that document, so the end of the path is
        # where this is asked (R1#0).
        # The escaped key: the same value under `api\\_key`, which the floor cannot decode, so it
        # WITHHOLDS the whole carrier rather than masking parts of it. That decision is not an
        # extent, and the span path used to apply it only to the detached span — `project` returned
        # the mask for the carrier while a later block of it was published with `shortpass` in it.
        escaped = carrier("catalog", "claude/guides/escaped.md",
                          '## Keys\n\napi\\_key: "alpha\nbravo\n\nshortpass"\n')
        escaped_emitted = shed(units_of([escaped]), str(pathlib.Path.home()))
        check("the floor withholds this carrier whole, which is the decision extents cannot carry",
              projection.carrier_decision(escaped["text"], str(pathlib.Path.home()))[1],
              "the floor returns this carrier, so the fixture is not the escaped one")
        escaped_out = scratch / "escaped-key-out"
        write_document(escaped_out, escaped_out / "inventory" / "current.json",
                       {"units": escaped_emitted}, str(pathlib.Path.home()))
        escaped_text = (escaped_out / "inventory" / "current.json").read_text(encoding="utf-8")
        control("the escaped-key carrier through splitting, shedding and the real writer",
                [f"published={escaped_text}"], projection.blank_for(escaped["text"]))
        check("and the published file carries no byte of a carrier the floor withheld",
              all(part not in escaped_text for part in ("shortpass", "bravo", "alpha", "api")),
              f"{escaped_text}")
        check("every span of a withheld carrier is blanked, not only the one that cannot decode",
              {row["text"] for row in escaped_emitted} == {projection.blank_for(escaped["text"])},
              f"{[row['text'] for row in escaped_emitted]}")
        # The same carrier with the value in a HEADING — the reviewer's fixture. `text` was redacted
        # on every row while `heading` carried `shortpass` on two of them, and the real writer
        # accepted that document: a heading is a span of the carrier, and the detached projection it
        # went through knew neither the withholding nor the key three lines above (R2#0).
        heading_value = carrier("catalog", "claude/guides/heading-value.md",
                                'api\\_key: "alpha\n\n## shortpass\n"\n')
        heading_emitted = shed(units_of([heading_value]), str(pathlib.Path.home()))
        heading_out = scratch / "heading-value-out"
        write_document(heading_out, heading_out / "inventory" / "current.json",
                       {"units": heading_emitted}, str(pathlib.Path.home()))
        heading_published = (heading_out / "inventory" / "current.json").read_text(encoding="utf-8")
        control("a withheld carrier whose credential value is a heading, through the real writer",
                [f"published={heading_published}"], projection.blank_for(heading_value["text"]))
        check("the floor withholds that carrier whole, so the rows are answering about that",
              projection.carrier_decision(heading_value["text"], str(pathlib.Path.home()))[1],
              "the floor returns this carrier, so the fixture is not the reviewer's")
        check("and no field of any row — heading included — carries a byte of it",
              "shortpass" not in heading_published and "alpha" not in heading_published
              and all(row["heading"] in ("", projection.blank_for(heading_value["text"]))
                      for row in heading_emitted),
              f"{[(row['text'], row['heading']) for row in heading_emitted]}")

        # ---- R2#3: this module is an entry point, and everything it publishes passes the floor.
        # Its self-test printed its report with `print`, so a failure line carried a planted
        # credential and a fixture path out verbatim; and `main` ran the suite with no boundary at
        # all, so an ordinary file failure left a traceback. Both are asked of the real statements.
        captured_report = io.StringIO()
        with contextlib.redirect_stdout(captured_report):
            report(f"inventory --self-test [FAIL] a fixture read failed: {pathlib.Path.home()}/x "
                   f"with apiKeyHelper: {secret}", home=str(pathlib.Path.home()))
        published = captured_report.getvalue()
        control("a report line carrying a credential and the owner's home path",
                [f"published={published.strip()}"], "REDACTED", "<HOME>")
        check("and neither the credential nor the home path is in it",
              secret not in published and str(pathlib.Path.home()) not in published, f"{published}")
        # ---- N1: this suite runs ITSELF below, and at depth 1 only. The child used to be kept
        # from spawning its own child by the very `dir=` wiring these controls revert; with it gone
        # the recursion went 594 deep and filled the disk. The child is marked (`entry.nest`) and a
        # marked run skips this section, whatever any protection does. The controls here still run
        # in the parent, and still fail by their own names when the wiring is gone.
        # ---- r3 #8: the one child `tracked_paths` starts is bounded, and a `git` that does not
        # finish is a REFUSAL rather than an empty listing. An empty listing would make a copy of
        # nothing and every control over that copy would pass over nothing.
        slow_bin = scratch / "slow-git-bin"
        slow_bin.mkdir()
        slow_marker = scratch / "slow-git-ran"
        # `: > file` is a shell builtin and `/bin/sleep` is absolute, so this script needs nothing
        # from PATH — the first version used bare `sleep`, which PATH did not hold, so the fixture
        # git died at once with code 127 and the control passed on the wrong failure (r3 #8 rework).
        (slow_bin / "git").write_text(f"#!/bin/sh\n: > {slow_marker}\n/bin/sleep 3\n", encoding="utf-8")
        (slow_bin / "git").chmod(0o755)
        # The SOURCE is a fixture of this control's own, never this checkout: `tracked_paths` takes
        # the git branch only when `source/.git` exists, and the commit hook materialises the index
        # into a tree that has none — there the call fell to the rglob branch, git never ran, and
        # this control failed inside the hook and nowhere else (S4 rework).
        slow_tree = scratch / "slow-git-tree"
        (slow_tree / "inner").mkdir(parents=True)
        (slow_tree / ".git").write_text("gitdir: a fixture, not a repository\n", encoding="utf-8")
        (slow_tree / "inner" / "held.txt").write_text("held\n", encoding="utf-8")
        slow_git = ""
        try:
            tracked_paths(slow_tree, git_env={"PATH": f"{slow_bin}:/usr/bin:/bin"}, git_timeout=0.5)
            slow_git = "a listing came back from a git that never answered"
        except Exception as exc:
            slow_git = f"{type(exc).__name__}: {exc}"
        control("a git listing that does not finish is refused by name, never read as an empty tree",
                [slow_git[:300]], "TREE_UNLISTABLE", "CHILD_TIMEOUT")
        check("and the fixture git really was the program that did not answer",
              slow_marker.is_file(), f"{masked(slow_marker)} was never created")

        # ---- R2#3 and R2#7 for this entry point, in this process. Both used to be asked of a
        # child running this whole suite with `--self-test` in its argv, which is what made the
        # recursion of S7 possible; neither needs a child. This module's `main` has no handler of its
        # own — `__main__` hands it to `entry.guarded`, and that is the one boundary — so the failure
        # is raised where the suite creates its fixtures and the real entry is called through it.
        held_scratch = globals()["self_test_scratch"]
        guarded_stream, guarded_code = io.StringIO(), "RAISED nothing"
        fixture_scratch = f"{pathlib.Path.home()}/Documents/fixture-scratch"
        try:
            def _unwritable_scratch(*_args, **_kwargs):
                raise PermissionError(13, "Permission denied", fixture_scratch)
            globals()["self_test_scratch"] = _unwritable_scratch
            guarded_code = guarded_entry(main, ["--self-test"], str(pathlib.Path.home()),
                                         stream=guarded_stream)
        except BaseException as left_the_boundary:   # `escaped` is a carrier fixture in this suite
            guarded_code = f"RAISED {type(left_the_boundary).__name__}"
        finally:
            globals()["self_test_scratch"] = held_scratch
        guarded_text = guarded_stream.getvalue()
        control("this entry point's own uncaught file failure, through the one boundary",
                [f"code={guarded_code} output={guarded_text.strip()[-400:]}"],
                "COMMAND_FAILED", "<HOME>")
        check("and the interpreter printed no traceback and no raw fixture path",
              "Traceback" not in guarded_text and fixture_scratch not in guarded_text
              and guarded_code == 1,
              f"{guarded_code} {guarded_text[-400:]}")
        # And `__main__` is wired to that layer rather than calling `main` itself: the two are
        # indistinguishable from outside, so the wiring is read here.
        boundary_calls = [node for node in ast.walk(ast.parse(
                              pathlib.Path(__file__).read_text(encoding="utf-8")))
                          if isinstance(node, ast.If)
                          and ast.unparse(node.test) == "__name__ == '__main__'"
                          for node in ast.walk(node) if isinstance(node, ast.Call)
                          and ast.unparse(node.func) == "entry.guarded"]
        check("and this entry point is wired to that layer rather than calling main itself",
              len(boundary_calls) == 1 and "main" in ast.unparse(boundary_calls[0]),
              f"{[ast.unparse(call) for call in boundary_calls]}")
        # R2#7: the judged parent refuses a location inside a fixture host home and creates nothing.
        guarded_home = scratch / "boundary-fixture-home"
        guarded_tmp = guarded_home / ".claude" / "tmp"
        guarded_tmp.mkdir(parents=True)
        guarded_env = {"HOME": str(guarded_home), "CLAUDE_CONFIG_DIR": str(guarded_home / ".claude"),
                       "TMPDIR": str(guarded_tmp), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        refused_scratch = ""
        try:
            with self_test_scratch("wp07-refused-", environ=guarded_env):
                refused_scratch = "the judged parent accepted a location inside a host home"
        except Exception as exc:
            refused_scratch = f"{type(exc).__name__}: {exc}"
        control("this suite passes the judged parent to TemporaryDirectory",
                [refused_scratch[:300]], "PROTECTED_OVERLAP")
        check("and nothing was created in the location the judgement refused",
              not any(guarded_tmp.iterdir()),
              f"{sorted(path.name for path in guarded_tmp.iterdir())}")

        # ---- R1#0/R2#0, the differential: for EVERY carrier fixture in this suite, nothing the
        # floor removes from the INTACT carrier appears in ANY string the emitted row carries. The
        # controls above name particular fixtures and particular fields; this one names the property.
        #
        # Two things it does not do, each because the first version did and was wrong (R2#0): it does
        # not rebuild the fixtures as Markdown guides — every fixture keeps its own layer, path and
        # form, because a Python or JSON carrier splits differently and the differential would be
        # judging a shape the inventory never emits — and it does not read a list of fields. It walks
        # every string in the row and holds that walk against the STRING FIELDS THE SCHEMA DECLARES,
        # so a field added later is covered by this control on the day it is added.
        session_text = (snapshot_dir / "output.json").read_text(encoding="utf-8")
        fixtures = {"key in the previous block": pair, "key four lines above": far,
                    "multi-line value": multi, "escaped key, withheld whole": escaped,
                    "a credential inside a heading line": carrier(
                        "catalog", "claude/guides/headed.md", heading_secret + "\n- a rule under it\n"),
                    "a heading that IS the credential's value": heading_value,
                    "a hook carrier (python)": carrier(
                        "catalog", "claude/hooks/planted.py",
                        f'API = "{secret}"\n\n\ndef run():\n    return API\n'),
                    # An adopted package's carrier, so `item_ref` and `package_id` are strings on at
                    # least one fixture rather than null: a field that is null everywhere is a field
                    # the walk cannot visit, and the schema check below says so.
                    "an adopted package's carrier": carrier(
                        "adopted_packages", "guides/adopted.md",
                        f"## Keys\n\n- the helper reads apiKeyHelper: {secret}\n",
                        item_ref="@vendor/pkg:adopted", package_id="@vendor/pkg"),
                    "planted native_global": carrier(
                        "native_global", f"{pathlib.Path.home()}/.claude/CLAUDE.md", planted_in["native_global"]),
                    "planted native_project": carrier(
                        "native_project", f"{project_scope}/CLAUDE.md", planted_in["native_project"]),
                    "planted native_memory": carrier(
                        "native_memory", f"{pathlib.Path.home()}/.claude/projects/p/memory/one.md",
                        planted_in["native_memory"]),
                    "the session's compiled text": carrier(
                        "session_injection", str(snapshot_dir / "output.json"), injected, form="markdown")}

        def strings_in(value, at="$"):
            """Every string the emitted row carries, with where it sits. Not a list of fields: a
            field added to a unit record is in this walk the moment it exists."""
            if isinstance(value, str):
                return [(at, value)]
            if isinstance(value, dict):
                return [row for key, item in value.items() for row in strings_in(item, f"{at}.{key}")]
            if isinstance(value, (list, tuple)):
                return [row for n, item in enumerate(value) for row in strings_in(item, f"{at}[{n}]")]
            return []

        def emitted_strings(item):
            rows = shed(units_of([item]), str(pathlib.Path.home()))
            return [(f"{item['layer']}[{n}]{where}", text)
                    for n, row in enumerate(rows) for where, text in strings_in(row)]

        def withheld_lines(item, emit=None):
            """`(lines the intact carrier does not keep, where any of them reached the row anyway)`.

            The comparison is per nonblank line: the floor's answer for the WHOLE carrier is the
            reference, and any line of the raw text it does not return is a line no string of that
            carrier's rows may carry. A withheld carrier keeps nothing, so every line of it is in the
            first list — which is the case the span path, and then the heading path, got wrong."""
            intact = projection.project(item["text"], projection.CURRENT, str(pathlib.Path.home()))
            removed = []
            for line in item["text"].splitlines():
                bare = line.strip()
                if len(bare) >= 6 and bare not in intact:
                    # The line, AND the line with its heading marks taken off, because that strip is
                    # the one transformation the emission path applies to a span: `## shortpass`
                    # leaves the carrier as the heading `shortpass`, and a whole-line comparison
                    # looked straight past it.
                    removed.append(bare)
                    stripped = bare.lstrip("#").strip()
                    if stripped != bare and len(stripped) >= 6:
                        removed.append(stripped)
            carried = (emit or emitted_strings)(item)
            return removed, sorted({where for line in removed for where, text in carried if line in text})

        differential = {name: withheld_lines(item) for name, item in fixtures.items()}
        control("every carrier fixture, differentially: what the intact carrier withholds, withheld in every emitted string",
                [f"fixtures={len(differential)} "
                 f"withheld_lines={sum(len(rows[0]) for rows in differential.values())} "
                 f"leaks={ {name: rows[1] for name, rows in differential.items() if rows[1]} }"],
                "leaks={}")
        check("every fixture had withheld lines to look for, so the differential judges each one",
              all(rows[0] for rows in differential.values()),
              f"{[name for name, rows in differential.items() if not rows[0]]}")
        check("every fixture kept its own carrier kind, so the splitter the differential ran is the real one",
              {item["form"] for item in fixtures.values()} >= {"markdown", "python"}
              and all(item["form"] == form_of(item["path"]) or item["form"] == "markdown"
                      for item in fixtures.values()),
              f"{sorted({item['form'] for item in fixtures.values()})}")
        # The walk is held against the schema the code owns: every string field a unit declares must
        # be one the walk visited. A field the walk cannot see is a field this control is blind to.
        declared_strings = sorted(
            name for name, spec in (inventory_schema()["$defs"]["unit"]["properties"]).items()
            if spec.get("type") == "string" or (isinstance(spec.get("type"), list) and "string" in spec["type"]))
        walked = {where.split("$.", 1)[-1].split(".")[0].split("[")[0]
                  for _name, item in fixtures.items() for where, _text in emitted_strings(item)}
        control("a string field the schema declares that the differential never looks at",
                [f"declared={declared_strings} walked={sorted(walked)} "
                 f"unwalked={[name for name in declared_strings if name not in walked]}"],
                "unwalked=[]")
        check("the schema declared string fields to cover at all", len(declared_strings) >= 8,
              f"{declared_strings}")
        # And the differential can see a leak: projecting each field DETACHED from its carrier is
        # exactly what this fix replaced — for the block, and then for the heading — so both shapes
        # must be reported.
        # The seam is `_emit_span`, which is where every carrier-derived field now leaves: patching
        # it to project the STORED STRING instead of the carrier's offsets reproduces exactly the
        # shape this fix replaced.
        kept_emit = globals()["_emit_span"]

        def detached_span(spec, place, where):
            unit = place["unit"]
            if spec["join"] is None:
                return projected(unit.get("text") or "", place["home"])
            return projected(unit.get("heading") or "", place["home"]) if unit.get("heading") else unit.get("heading")

        def detached_heading(spec, place, where):
            if spec["join"] is None:
                return kept_emit(spec, place, where)
            return detached_span(spec, place, where)

        try:
            globals()["_emit_span"] = detached_span
            detached = {name: withheld_lines(item)[1] for name, item in fixtures.items()}
        finally:
            globals()["_emit_span"] = kept_emit
        control("the same fixtures with every field projected detached from its carrier",
                [f"leaking={sorted(name for name, leaks in detached.items() if leaks)}"],
                "escaped key, withheld whole", "multi-line value", "a heading that IS the credential's value")
        try:
            globals()["_emit_span"] = detached_heading
            heading_only = {name: withheld_lines(item)[1] for name, item in fixtures.items()}
        finally:
            globals()["_emit_span"] = kept_emit
        control("and with only the heading detached, which is the shape that published a withheld carrier",
                [f"leaking={sorted(name for name, leaks in heading_only.items() if leaks)}"],
                "a heading that IS the credential's value")

        # ---- r3 S1, the differential over the CONTEXT path: a mention is a string this module
        # built, and the entry it is stored under is RAW carrier text. `shed` alone never fills
        # `operative_context`, so the walk above cannot reach it; this leg produces the same
        # fixtures the way a reference point does, through `operative_context`, so the entry rule is
        # held to the same property as every span.
        def context_strings(item):
            units = operative_context(produce([{"layer": item["layer"], "producer": "a fixture producer",
                                                "status": "complete", "carriers": [item],
                                                "reasons": []}]))
            rows = shed(units, str(pathlib.Path.home()))
            return [(f"{item['layer']}[{n}]{where}", text)
                    for n, row in enumerate(rows) for where, text in strings_in(row)]

        # Withheld whole (the escape the floor cannot decode), and the mention names a guide no
        # fixture delivers, so the entry stays unresolved and the stored string is the raw text the
        # mention sat in.
        # Every carrier KIND the splitter handles, each withheld whole and each holding a
        # mention-shaped secret: a JSON or TOML carrier splits differently from a guide, and a
        # markdown-only differential would be judging a shape the inventory never emits.
        mention_token = "claude/guides/shortpass-in-a-mention.md"
        mention_fixtures = {
            "a withheld carrier whose mention is a credential": carrier(
                "catalog", "claude/guides/withheld-mention.md",
                '---\nuse_when:\n  - the fixture asks\n---\n\n## Keys\n\n'
                'api\\_key: "alpha\n\n'
                # The mention is the WHOLE line, so the line the intact carrier withholds is also a
                # substring of the entry a detached emitter would store: without that, the
                # per-line comparison cannot see this leak at all.
                'claude/guides/shortpass-in-a-mention.md\n'),
            "a withheld carrier whose mention names a heading": carrier(
                "catalog", "claude/guides/withheld-heading.md",
                '## Keys\n\napi\\_key: "alpha\n\n'
                '- see claude/guides/absent.md#shortpass before applying this\n'),
            # A TOML value the splitter cuts in two, which is the shape the floor withholds whole.
            "a withheld toml carrier whose value spans lines": carrier(
                "catalog", "claude/guides/withheld.toml",
                'api_key = """alpha\nbravo\n\nshortpass"""\nsee = "' + mention_token + '"\n'),
            "a withheld python carrier with a mention in a comment": carrier(
                "catalog", "claude/hooks/withheld.py",
                'API_KEY = "alpha\\_bravo"\n# ' + mention_token + '\n'),
            "a withheld carrier of a form the splitter does not read": carrier(
                "catalog", "claude/guides/withheld.txt",
                'api\\_key: "alpha"\n' + mention_token + '\n'),
        }
        # JSON is the one kind with no whole-withheld fixture: the floor withholds a carrier whose
        # escape it cannot decode or whose masking breaks the syntax, and neither is reachable while
        # the carrier stays valid JSON — an undecodable escape makes it `Malformed` before any unit
        # exists. So JSON is covered by the shape the review named instead: the SECRET is itself
        # mention-shaped, so a detached emitter would store the credential as the entry.
        masked_mentions = {
            "a json carrier whose credential is mention-shaped": carrier(
                "catalog", "claude/guides/masked.json",
                '{"api_key": "shortpass.md",\n "see": "claude/guides/absent-json.md"}\n'),
        }
        check("the mention fixtures cover every carrier kind the splitter handles",
              {form_of(item["path"])
               for item in list(mention_fixtures.values()) + list(masked_mentions.values())}
              == {"markdown", "json", "toml", "python", "plain"},
              f"{sorted({form_of(item['path']) for item in list(mention_fixtures.values()) + list(masked_mentions.values())})}")
        for name, item in masked_mentions.items():
            entries = [text for where, text in context_strings(item)
                       if "operative_context" in where and text.startswith(UNRESOLVED)]
            check(f"{name} publishes no part of the credential its mention was made of",
                  entries and not any("shortpass" in entry for entry in entries), f"{entries}")
            # The whole way out for that fixture: produce, shed, and the REAL writer into a sink in
            # scratch, read back as bytes. The entry rule is asked where the document ends up,
            # because that is where the leak this round found was visible.
            produced_units = operative_context(produce([{"layer": item["layer"],
                                                         "producer": "a fixture producer",
                                                         "status": "complete", "carriers": [item],
                                                         "reasons": []}]))
            json_out = scratch / "mention-shaped-out"
            write_document(json_out, json_out / "inventory" / "current.json",
                           {"units": shed(produced_units, str(pathlib.Path.home()))},
                           str(pathlib.Path.home()))
            published = (json_out / "inventory" / "current.json").read_text(encoding="utf-8")
            control(f"{name} through splitting, the context rule, shedding and the real writer",
                    [f"published={published}"], "REDACTED")
            check("and no string of that published document carries the credential",
                  "shortpass" not in published, "the published document carries the credential")
        for name, item in mention_fixtures.items():
            check(f"the floor withholds {name} whole, so every line of it is a withheld line",
                  projection.carrier_decision(item["text"], str(pathlib.Path.home()))[1],
                  "the floor returns this carrier, so the fixture is not a withheld one")
            check(f"{name} really does produce an unresolved context entry",
                  any(entry.startswith(UNRESOLVED)
                      for row in operative_context(produce([{"layer": item["layer"],
                                                             "producer": "a fixture producer",
                                                             "status": "complete", "carriers": [item],
                                                             "reasons": []}]))
                      for entry in row["operative_context"]),
                  "no entry went unresolved, so the entry rule is not exercised")
        # Per fixture, the entry itself: a whole-withheld carrier's unresolved entry carries the
        # floor's fixed withheld form and never the mention it was built from. The per-line
        # differential below cannot see this on its own, because an entry is not a whole line.
        for name, item in mention_fixtures.items():
            entries = [text for where, text in context_strings(item)
                       if "operative_context" in where and text.startswith(UNRESOLVED)]
            check(f"{name} emits its unresolved entry from the carrier, withheld",
                  entries and all(projection.blank_for(item["text"]) in entry for entry in entries),
                  f"{entries}")
            check(f"{name} publishes no part of the mention it was built from",
                  not any("shortpass" in entry for entry in entries), f"{entries}")
        context_differential = {name: withheld_lines(item, context_strings)
                                for name, item in {**fixtures, **mention_fixtures,
                                                   **masked_mentions}.items()}
        control("every fixture through the context path: what the intact carrier withholds, withheld in every emitted string",
                [f"fixtures={len(context_differential)} "
                 f"leaks={ {name: rows[1] for name, rows in context_differential.items() if rows[1]} }"],
                "leaks={}")
        check("and the context walk reached an unresolved entry, so it judged the entry rule",
              any(where.endswith("]") and "operative_context" in where
                  for name in mention_fixtures
                  for where, _text in context_strings(mention_fixtures[name])),
              "no emitted string sat in operative_context")
        # And it can see the leak: emitting the entry from its STORED STRING is the shape r3 #0
        # found, and for a carrier the floor withholds whole it publishes raw carrier text.
        kept_context = globals()["_emit_context"]
        try:
            globals()["_emit_context"] = lambda value, place, where: projected(value, place["home"])
            stored = {name: withheld_lines(item, context_strings)[1]
                      for name, item in mention_fixtures.items()}
        finally:
            globals()["_emit_context"] = kept_context
        control("the same mentions emitted from the stored string instead of their carrier offsets",
                [f"leaking={sorted(name for name, leaks in stored.items() if leaks)}"],
                "a withheld carrier whose mention is a credential")

        # ---- GC#8: the closure expands the starting unit's own requirements
        conditioned = ("---\nuse_when:\n  - the fixture asks\n---\n\n## Rule\n\n- do the thing\n\n"
                       "### Exceptions\n\n- unless claude/guides/third.md says otherwise\n")
        third_body = "---\nuse_when:\n  - the third asks\n---\n\n## Rule\n\n- the third guide's requirement\n"
        closed = operative_context(units_of([guide("conditioned.md", conditioned), guide("third.md", third_body)]))
        rule_unit = next(unit for unit in closed if "do the thing" in unit["text"])
        third_ids = {unit["unit_id"] for unit in closed if unit["path"].endswith("third.md")}
        control("a requirement reached only through the unit's own condition span",
                [f"reached={sorted(third_ids & set(rule_unit['operative_context']))}"
                 if third_ids & set(rule_unit["operative_context"]) else ""],
                "reached=[")

        # ---- GC#11: one delivered path, two packages, and the ambiguity is kept
        shared_path = "claude/guides/review.md"
        shared_body = "## Rule\n\n- a shared requirement\n"
        base_two = units_of([carrier("catalog", "claude/guides/old-review.md", shared_body,
                                     item_ref="@a/pkg:review", package_id="@a/pkg")])
        # Both packages deliver the fragment at the one path now, so which carrier it moved from is
        # undecided — and taking the first match is how one package's fragment became the other's.
        both_sides = [carrier("catalog", shared_path, shared_body,
                              item_ref="@a/pkg:review", package_id="@a/pkg"),
                      carrier("catalog", shared_path, shared_body,
                              item_ref="@b/pkg:review", package_id="@b/pkg")]
        for order, rows_in in (("as enumerated", both_sides), ("reversed", list(reversed(both_sides)))):
            ambiguous = [row for row in renames_against(units_of(rows_in), base_two) if row.get("ambiguous")]
            control(f"one path in two packages, {order}: the rename is ambiguous, not resolved",
                    [f"ambiguous={len(ambiguous)} to={len(ambiguous[0]['to_carriers']) if ambiguous else 0}"],
                    "ambiguous=2", "to=2")
        by_path = collections.defaultdict(set)
        for unit in units_of(both_sides):
            if unit["class"] == "operative":
                by_path[unit["sha"]].add(unit["path"])
        control("uniqueness by path cannot see the second package at all",
                [f"paths_per_fragment={sorted({len(paths) for paths in by_path.values()})}"],
                "paths_per_fragment=[1]")

        # ---- GC#12: an ordinary absolute native path does not make publication fail, and does not
        # appear unprojected. A transcript records what a host home delivered, so the carrier's
        # delivered path IS an absolute path under someone's home — the identity embedded it, `shed`
        # projected the path and copied the identity, and the whole inventory refused its own
        # artifact at `$.units[0].carrier_id`.
        native_home = str(pathlib.Path.home())
        native_path = f"{native_home}/.claude/CLAUDE.md"
        native_carrier = carrier("native_global", native_path, "## Rule\n\n- a rule as delivered\n",
                                 item_ref=f"{native_path}#1", package_id=native_path,
                                 provenance={"session": "claude:session-1", "scope": native_path})
        native_units = units_of([native_carrier])
        native_rows = shed(native_units, native_home)
        native_doc = {"units": native_rows, "renames": renames_against(native_units, [], native_home)}
        clean("an artifact whose carrier is delivered at an absolute native path",
              disclosure_problems(native_doc, native_home))
        check("and the home path is nowhere in it, in any field",
              native_home not in json.dumps(native_doc) and "<HOME>" in json.dumps(native_doc),
              f"{native_rows}")
        check("the carrier id is opaque and still distinguishes this carrier",
              native_rows[0]["carrier_id"].startswith("c-") and native_home not in native_rows[0]["carrier_id"]
              and native_rows[0]["carrier_id"] != shed(units_of([carrier(
                  "native_project", native_path, "## Rule\n\n- a rule as delivered\n")]), native_home)[0]["carrier_id"],
              f"{native_rows[0]['carrier_id']}")
        # A rename record names carriers by the same ids, so it carries nothing the unit records do
        # not — the same path through a rename row was the other half of this.
        moved_native = units_of([carrier("native_project", f"{native_home}/project/CLAUDE.md",
                                         "## Rule\n\n- a rule as delivered\n")])
        rename_rows = renames_against(moved_native, native_units, native_home)
        control("a rename between two carriers delivered at absolute native paths",
                [f"rows={len(rename_rows)} ids={[row.get('from_carrier_id') for row in rename_rows]} "
                 f"paths={[row.get('from_path') for row in rename_rows]}"], "c-", "<HOME>")
        clean("and the rename rows cross the write boundary",
              disclosure_problems({"renames": rename_rows}, native_home))

        # ---- GC#7: one source selection decides every read of the owner's state, before a byte of
        # it is read, and it rejects a link at the leaf and at any component below the declared root.
        link_target = scratch / "link-target"
        (link_target / "runtime" / "baselines" / "ref1").mkdir(parents=True, exist_ok=True)
        (link_target / "runtime" / "baselines" / "ref1" / "inventory.json").write_text(
            json.dumps({"items": [{"ref": "@elsewhere/pkg:item"}]}), encoding="utf-8")
        (link_target / "elsewhere.json").write_text(json.dumps({"content_ref": "from-outside"}), encoding="utf-8")
        # The target mirrors the state's own layout, so a link standing in for a COMPONENT leads to a
        # file that is really there: a target without it makes the read never happen and the control
        # passes on a missing file rather than on the rejection it is about.
        (link_target / "runtime" / "state.json").write_text(
            json.dumps({"schema_version": 1, "selected_baseline_ref": "from-outside"}), encoding="utf-8")
        (link_target / "claude").mkdir(parents=True, exist_ok=True)
        (link_target / "claude" / "session-1.json").write_text(
            json.dumps({"schema_version": 1, "content_ref": "from-outside"}), encoding="utf-8")

        @contextlib.contextmanager
        def instead_a_link(path, target):
            """`path` replaced by a link to `target` for the duration, and put back afterwards."""
            path = pathlib.Path(path)
            aside = path.with_name(path.name + ".kept")
            path.rename(aside)
            path.symlink_to(target)
            try:
                yield
            finally:
                path.unlink()
                aside.rename(path)

        frozen_seq = [0]

        def acquisition(pin="claude:session-1"):
            """`freeze_inputs` over the fixture state — the real site of the runtime, pin, snapshot
            and baseline reads, and of every copy input."""
            frozen_seq[0] += 1
            ctx = {"native_roots": {}, "notes": {}}
            try:
                freeze_inputs(scratch / f"frozen-link-{frozen_seq[0]}", REPO, state, user, pin, ctx)
            except Exception as exc:
                return [f"{type(exc).__name__}: {exc}"]
            return [f"accepted: frozen_missing={ctx['notes'].get('frozen_missing')}"]

        clean("the fixture state is acquired when nothing on its paths is a link", [
            row for row in acquisition() if "SOURCE_LINKED" in row])
        for label, path, target in (
                ("the runtime state itself", state / "runtime" / "state.json", link_target / "elsewhere.json"),
                ("a component above the runtime state", state / "runtime", link_target / "runtime"),
                ("the pin itself", state / "sessions" / "pins" / "claude" / "session-1.json",
                 link_target / "elsewhere.json"),
                ("a component above the pin", state / "sessions" / "pins", link_target)):
            with instead_a_link(path, target):
                control(f"a read of the owner's state through a link: {label}", acquisition(), "SOURCE_LINKED")
        for label, path, target in (
                ("the baseline's item list itself", state / "runtime" / "baselines" / "ref1" / "inventory.json",
                 link_target / "runtime" / "baselines" / "ref1" / "inventory.json"),
                ("a component above the baseline", state / "runtime" / "baselines" / "ref1",
                 link_target / "runtime" / "baselines" / "ref1")):
            with instead_a_link(path, target):
                control(f"a read of the owner's state through a link: {label}",
                        [str(_raised(lambda: baseline_items(state, "ref1")))], "SOURCE_LINKED")
                check(f"and the bytes behind the link are not what was returned: {label}",
                      "@elsewhere/pkg:item" not in str(_raised(lambda: baseline_items(state, "ref1"))),
                      "the link's target was read after all")
        frozen_fake = scratch / "frozen-fake"
        (frozen_fake / "sessions" / "snapshots").mkdir(parents=True)
        (frozen_fake / "sessions" / "snapshots" / "linked-ref").symlink_to(link_target)
        control("a read of the owner's state through a link: the snapshot itself",
                [str(_raised(lambda: snapshot_of(REPO, frozen_fake, "linked-ref")))], "SOURCE_LINKED")
        frozen_above = scratch / "frozen-above"
        (frozen_above / "sessions").mkdir(parents=True)
        (frozen_above / "sessions" / "snapshots").symlink_to(link_target)
        control("a read of the owner's state through a link: a component above the snapshot",
                [str(_raised(lambda: snapshot_of(REPO, frozen_above, "any-ref")))], "SOURCE_LINKED")
        with instead_a_link(state / "runtime" / "baselines", link_target / "runtime" / "baselines"):
            copy_probe = scratch / "frozen-copy-above"
            left = freeze([(state / "runtime" / "baselines" / "ref1", "baseline")], copy_probe, state)
            control("a copy input reached through a link above the declared root",
                    left, "baseline: symlink")
            check("and nothing from behind that link was copied",
                  not any(path.is_file() for path in copy_probe.rglob("*")),
                  f"{sorted(str(path) for path in copy_probe.rglob('*'))}")

        # ---- GC#0 through `--project`: the checkout is protected whatever the caller declares
        elsewhere_project = scratch / "another-project"
        elsewhere_project.mkdir()
        declared_only = protected_roots(None, None, {"projects": {str(elsewhere_project): elsewhere_project}},
                                        checkout=REPO)
        check("the checkout is a protected root even when another project is the declared one",
              REPO in declared_only and elsewhere_project in declared_only,
              f"{[str(root) for root in declared_only]}")
        control("a destination inside the checkout, with another project declared",
                overlap_problems([REPO / "session-distill" / "out" / "probe"], declared_only, home=native_home),
                "PROTECTED_OVERLAP")
        check("and the checkout is named once, not twice",
              len(declared_only) == len(set(declared_only)), f"{[str(root) for root in declared_only]}")

        # ---- GC#3 by another route: a standalone `--to` is not a way into a run's artifacts
        declared_elsewhere = scratch / "a-declared-run"
        declared_elsewhere.mkdir()
        for name in RUN_MARKERS:
            (declared_elsewhere / name).write_text("{}\n", encoding="utf-8")
        control("a standalone destination that is a declared run directory",
                standalone_problems(declared_elsewhere, native_home), "RUN_DESTINATION", "--run-id")
        inside_run = declared_elsewhere / "inventory"
        inside_run.mkdir()
        control("a standalone destination inside a declared run directory",
                standalone_problems(inside_run, native_home), "RUN_DESTINATION")
        held = scratch / "already-holds"
        (held / "inventory").mkdir(parents=True)
        (held / "inventory" / "current.json").write_text("{}\n", encoding="utf-8")
        control("a standalone destination that already holds an inventory",
                standalone_problems(held, native_home), "INVENTORY_PRESENT")
        clean("an empty standalone destination outside every run",
              standalone_problems(scratch / "a-fresh-destination", native_home))

        # ---- GC#10: the real invocation writes no bytecode, observed as attempted writes into an
        # uncached COPY of the checkout and then read off that same copy's disk.
        #
        # Three things this control used to get wrong, each of which made it answer about something
        # else: it imported the driver as a module (the one shape production never takes, and the
        # only shape that caches the driver), it cleared `__pycache__` inside the REVIEW checkout to
        # make its question meaningful (a write into the tree under test, and only two of the
        # directories the command loads from), and it then scanned a scratch directory rather than
        # the tree it had asked about. The copy fixes all three: it is a tree this test owns, it has
        # no caches to begin with, and it is both the observation's filter and the disk inspected.
        probe = scratch / "bytecode-probe"
        copied_checkout = probe / "checkout"
        probe.mkdir()
        copied = checkout_copy(copied_checkout)
        driver_copy = copied_checkout / "session-distill" / "distill.py"
        check("the checkout copy is a real checkout and holds the driver",
              len(copied) > 200 and driver_copy.is_file()
              and (copied_checkout / "learn" / "redact.py").is_file()
              and (copied_checkout / "compose" / "instructions_catalog.py").is_file(),
              f"{len(copied)} file(s) copied")
        # The file list has two readers: a checkout, and a tree materialised from one — which is
        # what the commit hook runs the gates in, with no `.git` and `GIT_DIR` pointing elsewhere.
        # Both paths are exercised here, because a control that only ever ran in a checkout would
        # answer about a different tree under the hook (`gates/check-package.sh` `tracked_files`).
        walked = checkout_copy(probe / "walked", copied_checkout)
        check("the copy's own file list comes from a tree walk, there being no .git in it",
              not (copied_checkout / ".git").exists() and bool(walked), "the copy carries a .git")
        check("and a checkout and a materialised tree yield the same files",
              sorted(walked) == sorted(copied),
              f"{len(walked)} walked vs {len(copied)} listed: "
              f"{sorted(set(walked) ^ set(copied))[:6]}")
        shutil.rmtree(probe / "walked", ignore_errors=True)
        # A materialised tree holds only what was materialised UNTIL SOMETHING RUNS IN IT, and the
        # commit hook runs every gate inside one: by the time this leg is reached the snapshot
        # carries `__pycache__/*.pyc` from the legs before it. The walk used to return those and the
        # copy then held them, which failed the "it is uncached" check inside the hook and nowhere
        # else. This control builds its own rows — a planted cache in a source with no `.git` — so it
        # does not depend on the state the suite happens to run in.
        cached_source = probe / "cached-source"
        (cached_source / "session-distill" / "runlib" / "__pycache__").mkdir(parents=True)
        (cached_source / "session-distill" / "runlib" / "__pycache__" / "records.cpython-314.pyc"
         ).write_bytes(b"a bytecode cache an earlier leg left here")
        (cached_source / "session-distill" / "runlib" / "records.py").write_text("x = 1\n", encoding="utf-8")
        (cached_source / "stray.pyc").write_bytes(b"and one beside no package at all")
        from_cached = checkout_copy(probe / "from-cached", cached_source)
        check("a copy of a materialised tree that something has already run in holds no cache",
              not any((probe / "from-cached").rglob("*.pyc"))
              and not any((probe / "from-cached").rglob("__pycache__"))
              and from_cached == ["session-distill/runlib/records.py"],
              f"copied {from_cached}")
        check("and the planted cache is still in the source, so nothing was deleted to achieve that",
              (cached_source / "session-distill" / "runlib" / "__pycache__"
               / "records.cpython-314.pyc").is_file() and (cached_source / "stray.pyc").is_file(),
              "the copier removed the source's cache instead of declining to copy it")
        shutil.rmtree(probe / "from-cached", ignore_errors=True)
        check("and it is uncached, so a run that writes nothing cannot be a run that found a cache",
              not any(copied_checkout.rglob("*.pyc")) and not any(copied_checkout.rglob("__pycache__")),
              f"{sorted(str(path.relative_to(copied_checkout)) for path in copied_checkout.rglob('*.pyc'))}")
        probe_env = dict(os.environ)
        probe_env.pop("PYTHONPYCACHEPREFIX", None)
        probe_env.pop("PYTHONDONTWRITEBYTECODE", None)

        # ---- R2#5: the owner of "a closure member inside a copy of this checkout". The closure
        # gate admits a copy-run only where the program expression is a call of this function, so
        # what this function refuses is what the gate's admission rests on.
        control("a member a copy-run may not name",
                [str(_raised(lambda: copied_member(copied_checkout, "gates/check-package.sh")))],
                "COPY_MEMBER_UNKNOWN")
        control("a root this process did not copy",
                [str(_raised(lambda: copied_member(scratch / "not-a-copy", "session-distill/distill.py")))],
                "COPY_UNVERIFIED")
        check("even when that root holds a tree of the same shape, because the question is what ran",
              ("COPY_UNVERIFIED" in str(_raised(lambda: copied_member(REPO, "session-distill/distill.py")))),
              "a root nobody copied was admitted")
        check("and the member of a copy this process made resolves inside it",
              copied_member(copied_checkout, "session-distill/distill.py") == driver_copy,
              f"{masked(copied_member(copied_checkout, 'session-distill/distill.py'))}")
        control("a member name that would climb out of the copy",
                [str(_raised(lambda: copied_member(copied_checkout, "../elsewhere.py")))],
                "COPY_MEMBER_UNKNOWN")
        check("every member a copy-run may name is a file of this checkout",
              all((REPO / member).is_file() for member in COPIED_MEMBERS), f"{COPIED_MEMBERS}")

        def bytecode_probe(which, member, destination):
            """The child, and what it reported: one real process per question.

            The program the child loads is produced HERE, by `copied_member`, and that call is what
            `runlib/dispatch.py` admits: the path is a closure member inside a tree this process
            copied, or this raises. Passing a path the caller had built left the admission resting on
            text elsewhere in the file (R2#5)."""
            ran = bounded_child(lambda: subprocess.Popen(
                [sys.executable, "-I", "-c", BYTECODE_PROBE, str(copied_checkout),
                 str(destination), which, str(copied_member(copied_checkout, member))],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=probe_env,
                cwd=str(probe), start_new_session=True), what="the bytecode observer's own child")
            try:
                return ran, json.loads(ran.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                return ran, {}

        # The positive control first, on this same copy: a by-path load with the guard off writes a
        # `.pyc` beside the file it caches, and BOTH instruments — the audit hook and the disk scan
        # of the copy — are shown to see it. Then the cache it made is removed from the copy (never
        # from the review checkout) and the copy is asserted uncached again.
        unguarded_run, unguarded_seen = bytecode_probe(
            "unguarded", "learn/redact.py", probe / "out-positive")
        on_disk = sorted(copied_checkout.rglob("*.pyc"))
        check("the same observation sees a by-path load write bytecode when the guard is off",
              bool(unguarded_seen.get("bytecode")) and bool(on_disk),
              f"the positive control observed none: {unguarded_run.stdout[-200:]} "
              f"{unguarded_run.stderr[-200:]} {[path.name for path in on_disk]}")
        # A write-mode open is one way to change a tree. The observer is shown to see the others —
        # a directory created, a file renamed, a file deleted, and two attempts that FAIL (an audit
        # hook fires before the operation, so a refused attempt has still been attempted). Without
        # this, "no write at all" rested on an observer that returned immediately for every event
        # that was not `open` (R1#4).
        mutation_run, mutation_seen = bytecode_probe(
            "mutations", "learn/redact.py", probe / "out-mutations")
        observed_kinds = set(mutation_seen.get("kinds") or [])
        for kind in ("os.mkdir", "os.rename", "os.remove", "os.rmdir"):
            control(f"the observation sees {kind} under the checkout",
                    [f"kinds={sorted(observed_kinds)}"], kind)
        observed_rows = set(mutation_seen.get("under_checkout") or [])
        # The probe reports resolved paths, so the rows this control expects are resolved too: on
        # this platform the scratch parent is reached through a symlink, and comparing the two forms
        # was comparing a path with another name for it.
        real_copy = pathlib.Path(os.path.realpath(copied_checkout))
        probe_dir = real_copy / "session-distill" / "probe-mutations"
        # Each deliberately FAILED attempt, by its own (event, path) identity. A count was not an
        # assertion about them at all: mkdir, the write-open, rename's two paths, remove and rmdir
        # already supply six rows, so the old threshold passed with no failed attempt observed (R2#4).
        for what, row in (("a mkdir of a directory that is already there", f"os.mkdir {probe_dir}"),
                          ("a remove of a file that is not there",
                           f"os.remove {real_copy / 'a-file-that-is-not-here'}"),
                          ("a rename whose source is not there",
                           f"os.rename {real_copy / 'also-not-here'}")):
            # The rows themselves are the problems list, so the needle is looked for in ALL of them:
            # rendering a truncated list and searching that text was a control reporting "not seen"
            # about a row it had.
            control(f"the observation sees {what}, which failed", sorted(observed_rows), row)
        # A descriptor-relative creation and a descriptor-only truncation: the shapes `record`
        # resolved against the working directory, or discarded because `os.fspath` cannot take an
        # integer. Either the descriptor resolves them under the copy, or they are UNVERIFIED — and
        # unverified is a failure of the claim, never a pass.
        for what, row in (("a mkdir made relative to a directory descriptor",
                           f"os.mkdir {probe_dir / 'relative-to-a-descriptor'}"),
                          ("a truncation given only a file descriptor",
                           f"os.truncate {probe_dir / 'renamed.txt'}"),
                          ("an open whose only write flag is O_TRUNC",
                           f"open(write) {probe_dir / 'truncated.txt'}")):
            control(f"the observation sees {what}",
                    sorted(observed_rows) + [f"unverified={mutation_seen.get('unverified')}"], row)
        check("the mutation probe attributed every event it saw, so none of it rests on 'unverified'",
              mutation_seen.get("unverified_total") == 0,
              f"{mutation_seen.get('unverified')} {mutation_run.stderr[-200:]}")
        check("the mutation probe left the copy as it found it",
              not (copied_checkout / "session-distill" / "probe-mutations").exists(),
              "the mutation probe's own directory is still there")
        for cache in list(copied_checkout.rglob("__pycache__")):
            shutil.rmtree(cache, ignore_errors=True)
        check("the copy is uncached again before the real invocation runs",
              not any(copied_checkout.rglob("*.pyc")),
              f"{sorted(str(path.relative_to(copied_checkout)) for path in copied_checkout.rglob('*.pyc'))}")

        def tree_state(root):
            """Every entry under `root`: its name, its contents, and its METADATA — mode, size and
            mtime in nanoseconds.

            A content-only comparison cannot see a chmod, a utime or a truncation that restored the
            same bytes, so it was no backstop for the event kinds the observer might miss (R2#4).
            It still cannot see an attempt that FAILED — nothing changes on disk — which is why the
            failed attempts are asserted from the events, by identity, and not from here."""
            root = pathlib.Path(root)
            state_of = {}
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root).as_posix()
                try:
                    stat = path.lstat()
                    metadata = f"mode={stat.st_mode:o} size={stat.st_size} mtime_ns={stat.st_mtime_ns}"
                except OSError as exc:
                    state_of[relative] = f"unstattable:{type(exc).__name__}"
                    continue
                if path.is_symlink():
                    state_of[relative] = f"link:{os.readlink(path)} {metadata}"
                elif path.is_dir():
                    state_of[relative] = f"dir {metadata}"
                else:
                    try:
                        state_of[relative] = f"{hashlib.sha256(path.read_bytes()).hexdigest()} {metadata}"
                    except OSError as exc:
                        state_of[relative] = f"unreadable:{type(exc).__name__} {metadata}"
            return state_of

        before_tree = tree_state(copied_checkout)
        guarded_run, guarded_seen = bytecode_probe("guarded", "session-distill/distill.py", probe / "out")
        after_tree = tree_state(copied_checkout)
        check("the real invocation ran the driver as __main__ and produced the inventory",
              guarded_seen.get("code") == 0 and (probe / "out" / "inventory" / "manifest.json").is_file(),
              f"{guarded_run.returncode} {guarded_run.stdout[-300:]} {guarded_run.stderr[-400:]}")
        # Every attempted mutation under the copy, not only the bytecode ones: the read-only claim is
        # the wider one, and the observation that answers it is the same observation.
        # Fail closed. "No attempted write" is `writes_under_checkout=0` AND `unverified=0`: an
        # event the observer could not attribute to a tree is not evidence that nothing was written,
        # and reading it as one is how a descriptor-relative removal would have passed (R2#4).
        control("the real invocation attempts no write at all anywhere under the checkout",
                [f"observed={guarded_seen.get('bytecode')} "
                 f"writes_under_checkout={guarded_seen.get('under_checkout_total')} "
                 f"unverified={guarded_seen.get('unverified_total')} "
                 f"first={guarded_seen.get('under_checkout')} {guarded_seen.get('unverified')}"],
                "observed=[]", "writes_under_checkout=0", "unverified=0")
        differences = sorted(set(before_tree) ^ set(after_tree)) + sorted(
            name for name in set(before_tree) & set(after_tree) if before_tree[name] != after_tree[name])
        control("and that same checkout's whole tree — contents, names and metadata — is what it was",
                [f"entries={len(before_tree)} differences={differences[:6]}"], "differences=[]")
        check("the comparison carried metadata as well as contents, so a chmod or a utime would show",
              all("mode=" in value and "mtime_ns=" in value for value in before_tree.values()),
              f"{sorted(before_tree.items())[:2]}")
        check("the comparison had a tree to compare", len(before_tree) > 200,
              f"{len(before_tree)} entries")

        # ---- the pinned session's own transcript answers the selection reference point
        selection_doc = json.loads((planted_out / "inventory" / "selection.json").read_text(encoding="utf-8"))
        selection_rows = {row["layer"]: row for row in selection_doc["layers"]}
        check("the pinned session's native layers come from its own transcript",
              all(selection_rows[layer]["status"] == "complete" for layer in TRANSCRIPT_LAYERS),
              f"{[(layer, selection_rows[layer]['status'], selection_rows[layer]['reasons']) for layer in TRANSCRIPT_LAYERS]}")
        check("and each one names the session it was recorded in",
              {unit["provenance"].get("session") for unit in selection_doc["units"]
               if unit["layer"] in TRANSCRIPT_LAYERS} == {"claude:session-1"},
              f"{sorted({unit['provenance'].get('session') for unit in selection_doc['units'] if unit['layer'] in TRANSCRIPT_LAYERS})}")
        unpinned_doc = json.loads((split_out / "inventory" / "selection.json").read_text(encoding="utf-8"))
        control("a selection reference point with no pin to name a session",
                [f"{row['layer']}={row['status']}: " + "; ".join(row["reasons"])
                 for row in unpinned_doc["layers"] if row["layer"] in TRANSCRIPT_LAYERS],
                "native_global=unknown", "no pin")
        control("a ledger layer at a past reference point",
                [f"{row['layer']}={row['status']}: " + "; ".join(row["reasons"])
                 for row in unpinned_doc["layers"] if row["layer"] == "ledger_keep"],
                "ledger_keep=unknown", "no per-session history")

        # ---- the refusals `gates/control-audit.py` found no control for (352d35f). Each one is
        # asked of the real function DIRECTLY, with rows this block builds: in the end-to-end path
        # an earlier check answers first, which is exactly why removing these left every suite
        # green. One of the fifteen it named is accepted unguarded, with its reason in `confined`.
        credential_line = f'apiKeyHelper: {"sk-ant-api03-" + "Ab3" * 14}\n'
        check("the floor does call that line a disclosure, so the control below judges something",
              projection.discloses(credential_line, str(pathlib.Path.home())) is not None,
              f"{credential_line!r} is not a disclosure to this floor")
        kept_project_span = projection.project_span
        try:
            # The guard in `_projected_span` sits behind `project_span`, which masks the credential
            # itself — so the only way to ask whether the guard is there is to hand it a span the
            # floor returned with a credential still in it.
            projection.project_span = lambda carrier, start, end, home=None, decision=None: credential_line
            control("a span the floor returned with a credential still in it",
                    [str(_raised(lambda: _projected_span(
                        {"text": "- a rule\n", "carrier_text": "## Rule\n\n- a rule\n", "span": (9, 18)},
                        str(pathlib.Path.home()))))],
                    "DISCLOSED_IN_UNIT")
        finally:
            projection.project_span = kept_project_span

        # The two native-read shapes, as source text rather than as this module's own body: the
        # scan's subject is a module, and its own body must have neither.
        control("a module that reads a host layer's file names from the native table",
                native_read_problems('names = NATIVE["claude"]["global"]\n'),
                "NATIVE_FILE_READ", "a host layer's file names are read")
        control("a module that globs a host home",
                native_read_problems('found = list(pathlib.Path(NATIVE["claude"]["home"]).rglob("*.md"))\n'),
                "NATIVE_FILE_READ", "a host home is globbed")
        clean("this module itself, by the same scan", native_read_problems())

        # A traversal that normalises back INSIDE the destination: refused by the label rule, and
        # invisible to the resolution check, which is what made the two shadow each other.
        control("a copy label whose traversal normalises back inside the destination",
                [str(_raised(lambda: confined(scratch / "frozen", "a/../b")))],
                "DESTINATION_ESCAPES", "holds no traversal")
        check("and that label really does resolve inside, so it is the label rule that refused it",
              pathlib.Path(os.path.normpath(str(scratch / "frozen" / "a/../b"))).is_relative_to(scratch / "frozen"),
              "the fixture resolves outside after all")

        # No temporary location at all: the environment names none and the platform's candidates are
        # not there. `/var/tmp` always exists here, so this refusal is unreachable without saying
        # which candidates are meant.
        control("no temporary location in the environment or among the platform's candidates",
                [str(_raised(lambda: temp_home([], str(pathlib.Path.home()), {},
                                               candidates=(str(scratch / "no-such-tmp"),))))],
                "TEMP_UNAVAILABLE")
        check("the candidate list this control replaces is the one production uses",
              TEMP_CANDIDATES == ("/tmp", "/var/tmp"), f"{TEMP_CANDIDATES}")

        # A native source whose bytes changed between the before-hash and the after-hash. The
        # library half of this is covered end to end; the native half had no control, and it is the
        # graver one, because it is reported ahead of the failure already in flight.
        native_witness = scratch / "a-native-source.md"
        native_witness.write_text("- a rule as delivered\n", encoding="utf-8")
        control("a native source whose bytes changed while the layers were read",
                [str(_raised(lambda: verify_unchanged([], {}, {str(native_witness): "0" * 64},
                                                      home=str(pathlib.Path.home()))))],
                "STATE_WRITTEN", "reading the native layers changed")

        # The schema contract's own failure paths. The schema is a file, so "there is no schema" is
        # one of its answers, and every reader of it must say so rather than compare against None.
        kept_schema_reader = globals()["inventory_schema"]
        try:
            def unreadable_schema(path=SCHEMA_PATH):
                raise Refused(f"JSONSCHEMA_PIN_UNREADABLE {masked(path)}: the fixture withholds it")

            globals()["inventory_schema"] = unreadable_schema
            control("a layer table judged against a schema that cannot be read",
                    layer_problems(), "SCHEMA_UNREADABLE", "JSONSCHEMA_PIN_UNREADABLE")
            control("a unit contract judged against a schema that cannot be read",
                    contract_problems(), "SCHEMA_UNREADABLE", "JSONSCHEMA_PIN_UNREADABLE")
            control("a produced document judged against a schema that cannot be read",
                    document_contract_problems({"units": [], "layers": []}),
                    "SCHEMA_UNREADABLE", "JSONSCHEMA_PIN_UNREADABLE")
        finally:
            globals()["inventory_schema"] = kept_schema_reader
        reordered = json.loads(json.dumps(inventory_schema()))
        reordered["$defs"]["layer_name"]["enum"] = list(reversed(reordered["$defs"]["layer_name"]["enum"]))
        control("a schema that names the same layers in another order",
                layer_problems(reordered), "LAYER_ORDER")
        kept_unit_fields = globals()["UNIT_FIELDS"]
        try:
            # The record and the schema agree with each other and both omit a field the PLAN
            # requires: the first comparison passes, and what the plan asked for is gone. Only this
            # branch sees that, which is why it needs its own rows.
            trimmed = tuple(field for field in kept_unit_fields if field != PLAN_FIELDS[0])
            globals()["UNIT_FIELDS"] = trimmed
            agreeing = json.loads(json.dumps(inventory_schema()))
            agreeing["$defs"]["unit"]["required"] = list(trimmed)
            control("a record and a schema that agree with each other and drop a field the plan requires",
                    contract_problems(agreeing), "CONTRACT_MISMATCH", PLAN_FIELDS[0])
        finally:
            globals()["UNIT_FIELDS"] = kept_unit_fields
        control("a schema this project's own schema policy refuses",
                document_contract_problems({"units": [], "layers": []},
                                           {"type": "object", "additionalProperties": False,
                                            "properties": {"units": {}}}),
                "SCHEMA_INVALID")

        # ---- r3 #2: the boundary module's OWN import is inside a boundary. Everything else this
        # file describes a failure with is `runlib.entry`, so an `entry` that cannot be imported
        # used to leave the interpreter's traceback — with the importer's absolute paths in it — on
        # stderr before a line of this command ran. Two real children, because an import runs before
        # anything this suite can patch, each from a COPY of the checkout so this one is untouched.
        boundary_copy = scratch / "boundary-checkout"
        checkout_copy(boundary_copy)
        boundary_entry = boundary_copy / "session-distill" / "runlib" / "entry.py"
        check("the copy holds the boundary module this control removes",
              boundary_entry.is_file(), f"{masked(boundary_entry)} is not in the copy")
        boundary_env = {**os.environ, "HOME": str(scratch)}

        def without_the_boundary(member, argv, what):
            """One production command (never `--self-test`) from the copy, with `entry.py` gone."""
            return bounded_child(lambda: subprocess.Popen(
                [sys.executable, str(copied_member(boundary_copy, member))] + argv,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=boundary_env,
                cwd=str(boundary_copy / "session-distill"), start_new_session=True), what=what)

        for how, break_it in (("missing", lambda: boundary_entry.unlink()),
                              ("unreadable", lambda: boundary_entry.chmod(0o000))):
            boundary_entry.write_text("x = 1\n", encoding="utf-8")
            boundary_entry.chmod(0o644)
            break_it()
            for label, member, argv in (
                    ("this module's entry point", "session-distill/runlib/inventory.py", []),
                    ("the driver", "session-distill/distill.py",
                     ["inventory", "--to", str(scratch / f"boundary-out-{how}"), "--no-state"])):
                # `ran` is this suite's own control register, so the child is NOT bound to it.
                child = without_the_boundary(member, argv, f"{label} with no boundary ({how})")
                control(f"{label}, with the boundary module {how}: the fixed line and nothing else",
                        [f"code={child.returncode} stderr={child.stderr.strip()} "
                         f"stdout={child.stdout.strip()}"],
                        STARTUP_UNAVAILABLE)
                check(f"{label} ({how}) exits with the fixed code and prints no traceback or path",
                      child.returncode == STARTUP_UNAVAILABLE_CODE
                      and child.stderr.strip() == STARTUP_UNAVAILABLE and not child.stdout.strip()
                      and "Traceback" not in child.stderr and str(boundary_copy) not in child.stderr
                      and str(scratch) not in child.stderr,
                      f"code={child.returncode} stderr={child.stderr[-300:]}")
        boundary_entry.chmod(0o644)

        # ---- r3 S1: every refusal the emission can state, asked of `emit_row` DIRECTLY with rows
        # this block builds. The tables in force are default-deny, so in the production path a
        # declared field never reaches most of these branches — a control that went through
        # `reference_of` would be testing the fixtures rather than the rules.
        secret_text = "sk-ant-api03-" + "Ab3" * 14
        home_here = str(pathlib.Path.home())
        emit_place = {"home": home_here, "decisions": {}}
        probe_table = table_of({"kind": as_enum(("a", "b")), "count": as_scalar(),
                                "label": as_metadata(), "pinned": as_constant("one"),
                                "unit_id": as_opaque("unit_id"), "note": as_tree(),
                                "either": one_of(as_scalar(), as_enum(("yes",)))})

        def emitted(**fields):
            row = {"kind": "a", "count": 1, "label": "a label", "pinned": "one",
                   "unit_id": "u-" + "0" * 16, "note": {"a note": "a value"}, "either": 2}
            row.update(fields)
            return [str(_raised(lambda: emit_row("probe", probe_table, row, dict(emit_place))))]

        clean("the probe row this block builds is emitted as the tables declare it",
              [problem for problem in emitted() if problem != "None"])
        control("a record field no rule of its table names",
                emitted(surprise="x"), "EMISSION_UNDECLARED")
        check("and the undeclared key is named by its length and digest, never printed",
              "surprise" not in emitted(surprise="x")[0],
              f"the refusal printed the key: {emitted(surprise='x')[0]}")
        control("a table naming a rule this emission does not have",
                [str(_raised(lambda: emit_row("probe", table_of({"kind": {"rule": "no-such-rule"}}),
                                              {"kind": "a"}, dict(emit_place))))],
                "EMISSION_UNDECLARED", "a rule this emission does not have")
        control("a value outside the declared set", emitted(kind="c"),
                "EMISSION_NOT_DECLARED_VALUE", "no declared set holds")
        control("text where the table declares a number", emitted(count="1"),
                "EMISSION_NOT_DECLARED_VALUE", "a number or a boolean")
        control("None where the table declares no null", emitted(label=None),
                "EMISSION_NOT_DECLARED_VALUE", "None, where the table declares")
        control("not the one value a constant field carries", emitted(pinned="two"),
                "EMISSION_NOT_DECLARED_VALUE", "not the one value")
        control("a number where the table declares metadata text", emitted(label=7),
                "EMISSION_NOT_DECLARED_VALUE", "declares metadata text")
        control("an owner's path in a field whose form is its guarantee",
                emitted(unit_id=f"{pathlib.Path.home()}/.claude/CLAUDE.md"),
                "EMISSION_NOT_OPAQUE", "unit_id form")
        check("and the refusal about that field does not carry the path it refused",
              home_here not in emitted(unit_id=f"{pathlib.Path.home()}/.claude/CLAUDE.md")[0],
              "the opaque refusal printed the path")
        control("a value no declared kind of a union field admits", emitted(either="no"),
                "EMISSION_UNION_UNMATCHED")
        control("a note whose key is not a string", emitted(note={1: "x"}),
                "EMISSION_NOT_DECLARED_VALUE", "key, where a note's keys are strings")
        control("a note holding a value no rule of this emission admits",
                emitted(note={"a note": {1, 2}}), "EMISSION_NOT_DECLARED_VALUE", "no rule of")
        # Two DIFFERENT credentials, which the floor masks to one string: the keys are two facts and
        # the emitted map would answer for both with whichever came last.
        other_secret = "sk-ant-api03-" + "Cd4" * 14
        check("the two collision fixtures really are two strings the floor masks to one",
              secret_text != other_secret
              and projected(f"apiKeyHelper: {secret_text}", home_here)
              == projected(f"apiKeyHelper: {other_secret}", home_here),
              "the fixtures do not collide after projection")
        control("two note keys that project to one string",
                emitted(note={f"apiKeyHelper: {secret_text}": 1, f"apiKeyHelper: {other_secret}": 2}),
                "EMISSION_KEY_COLLISION", "two note keys")
        collide_table = table_of({"paths": map_of(as_metadata(), as_scalar())})
        control("two map keys that project to one string",
                [str(_raised(lambda: emit_row("probe", collide_table,
                                              {"paths": {f"apiKeyHelper: {secret_text}": 1,
                                                         f"apiKeyHelper: {other_secret}": 2}},
                                              dict(emit_place))))],
                "EMISSION_KEY_COLLISION", "refused rather than merged")
        def span_place(record):
            """`shed`'s own place for one record: the carrier's decision, taken once, and the unit."""
            where = {"home": home_here, "decisions": {}}
            _decision_for(where, "c-" + "0" * 24, record.get("carrier_text"))
            where.update(unit=record, decision=where["decisions"]["c-" + "0" * 24])
            return where

        span_table = table_of({"text": as_span("span")})
        disagreeing = {"text": "- another rule\n", "carrier_text": "## Rule\n\n- a rule\n",
                       "span": (9, 18)}
        control("a record whose text is not the carrier's bytes at the span it declares",
                [str(_raised(lambda: emit_row("probe", span_table, disagreeing,
                                              span_place(disagreeing))))],
                "EMISSION_SPAN_MISMATCH", "no offset of this row can be trusted")
        agreeing_span = {"text": "- a rule\n", "carrier_text": "## Rule\n\n- a rule\n",
                         "span": (9, 18)}
        check("and the same table emits the record whose text IS those bytes",
              emit_row("probe", span_table, agreeing_span,
                       span_place(agreeing_span))["text"] == "- a rule\n",
              "the agreeing fixture did not come back as its carrier's bytes")
        context_table = table_of({"needs": list_of(as_context())})
        originless = {"needs": [secret_text], "carrier_text": "## Rule\n\n- a rule\n",
                      "span": (9, 18), "context_origins": {}}
        control("an unresolved context entry with no carrier offsets behind it",
                [str(_raised(lambda: emit_row("probe", context_table, originless,
                                              span_place(originless))))],
                "EMISSION_UNDECLARED", "the stored string is never what is emitted")
        check("and that refusal does not carry the stored string it refused",
              secret_text not in str(_raised(lambda: emit_row("probe", context_table, originless,
                                                              span_place(originless)))),
              "the refusal published the entry it would not emit")

        # The hole this round's S1 found: a `units_of` failure's message carries the carrier's path,
        # and the path can hold the owner's home or a credential. The reasons now go in RAW and
        # `LAYER_ROW_TABLE` projects them, so this asks the emitted row, not the raised message.
        leaky_name = f"{pathlib.Path.home()}/.claude/{secret_text}.toml"
        leaky = _raised(lambda: units_of([carrier("overlays", leaky_name, "key = \n", "leak")]))
        check("a malformed carrier's own message does carry its path, so the control below judges something",
              leaky is not None and secret_text in str(leaky), f"{leaky!r}")
        leaky_row = emit_row("layer_row", LAYER_ROW_TABLE,
                             {"layer": "overlays", "producer": "a fixture producer",
                              "status": "incomplete", "units": 0, "empty": False,
                              "reasons": [f"overlays: {leaky}"]}, dict(emit_place))
        check("and the emitted layer row carries neither the credential nor the owner's home",
              secret_text not in json.dumps(leaky_row) and home_here not in json.dumps(leaky_row),
              f"{leaky_row}")
        check("while the reason is still there to read",
              "overlays" in leaky_row["reasons"][0] and len(leaky_row["reasons"]) == 1,
              f"{leaky_row['reasons']}")

    report(f"inventory --self-test: {'OK' if not failures else 'FAILED'} ({len(ran)} controls: the splitter's "
          f"reproduction over the real guides, the unit record and the layer set against the schema the code owns "
          f"(no control reads a dated design record), a produced document validated against that schema, a span "
          f"projected with its carrier intact — a credential's key four nonblank lines above its value, a "
          f"multi-line credential the splitter cut in two, and an escaped key whose whole carrier the floor "
          f"withholds, published through the real writer — every carrier-derived field out through one path and "
          f"every carrier fixture differentially checked, over every string an emitted row carries and every "
          f"string field the schema declares, for what the intact carrier does not keep, every refusal the "
          f"emission tables can state asked of `emit_row` with rows the controls build, the unresolved context "
          f"entry held to the same property through every carrier kind the splitter handles, this entry point's own "
          f"report and uncaught failures through the one diagnostic boundary, the host homes as configured rather "
          f"than as defaulted, a copy-run bound to the owner that produces it, an opaque carrier identity that "
          f"lets an absolute native "
          f"path be published, one source selection before every read of the owner's state with a leaf and an "
          f"ancestor link refused for each read kind, and denying that selection stopping every category of read, "
          f"the owner's roots protected whether or not this run reads them, a self-test scratch parent chosen by "
          f"the same rule, the boundary module's own import inside a boundary — the fixed path-free "
          f"line from both entry points, with `runlib/entry.py` missing and unreadable, as real "
          f"children of a checkout copy — the checkout protected whatever `--project` declares, a "
          f"standalone destination that is a run or already holds an inventory refused, the real invocation run as "
          f"`__main__` against an uncached copy of the checkout with every attempted write observed, a context that "
          f"spans two guides "
          f"and shrinks without its cross-reference, one fragment across two versions with two contexts, the release "
          f"mapping against the baseline file's own item list, every layer status the table can report, the owner's "
          f"state unchanged by a whole inventory beside the write its own entry point makes, an output destination "
          f"overlapping a protected root refused before any write, a planted credential and home path in every "
          f"personal carrier kind masked in every artifact while the hashes still bind to the raw carrier, a "
          f"malformed settings file reported incomplete rather than unsupported, and a failed acquisition that "
          f"still leaves a layer-status artifact)", home=str(pathlib.Path.home()))
    for failure in failures:
        report(f"inventory --self-test [FAIL] {failure}", home=str(pathlib.Path.home()))
    return 1 if failures else 0


def _raised(call):
    """The exception `call` raises, as the controls read it."""
    try:
        call()
    except Exception as exc:  # the control names the code in the message
        return exc
    return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--self-test"]:
        return self_test()
    entry.say(__doc__.strip().split("\n\n")[0], home=str(pathlib.Path.home()))
    return 2


if __name__ == "__main__":
    # The same boundary the driver runs inside: an uncaught failure of this entry point — a fixture
    # read that is refused, a scratch directory that cannot be made — is described through the floor
    # instead of by the interpreter, and its report lines pass the floor too (R2#3).
    sys.exit(entry.guarded(main, sys.argv[1:], str(pathlib.Path.home())))
