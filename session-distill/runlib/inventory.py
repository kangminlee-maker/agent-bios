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
import bisect
import collections
import datetime
import contextlib
import builtins
import hashlib
import importlib.util
import io
import json
import math
import os
import pathlib
import re
import shutil
import stat
import subprocess
import tempfile
import time

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
SESSIONS = "sessions"  # `inventory/sessions.json`: the per-session records and their events
STORE = "shared_store"  # `inventory/shared/store.json`: every carrier version the run names, once (S-22)
# `inventory/shared/<selection|release>-<i>.json`: one per verified snapshot and per baseline a session's own
# pin names, each the layer rows of its kind, by reference into the store (S-22)
SHARED = "shared_inventory"
SHARED_KINDS = ("selection", "release")
# the layers a release inventory answers: its overlays and session injection are per session (S-17)
SHARED_RELEASE_LAYERS = ("catalog", "adopted_packages")
STORE_REL = "shared/store.json"
STATUSES = ("complete", "incomplete", "unsupported", "unknown")

# §6.1's unit record, with the two fields the plan adds, the one the emission adds, and the unit's
# reference into the shared store (step 0 S-11). `class` carries §6.1's `operative|reference`;
# `contract_problems` holds this tuple against the schema.
UNIT_FIELDS = ("unit_id", "unit_ref", "layer", "path", "heading", "n", "text", "sha", "class",
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


# The child this module's self-test runs to answer, behaviourally, whether a real invocation writes
# anything into the tree it ran from (GB#7, GC#10). It is passed to `python -c`: a question only a
# real process answers, and a script file would be a program the dispatch trace cannot follow.
#
# It runs the driver the way production does — as `__main__`, through `runpy.run_path` — because
# that is the only shape a real invocation has. Importing it as a module was the control's own
# probe, and the one shape that caches the driver: the probe produced the single
# `session-distill/__pycache__/distill.*.pyc` ever seen here and then called it a finding (GC#10).
#
# It OBSERVES NOTHING. It used to carry an audit hook, a table of 37 mutating events and an
# accounting of the ones it could not attribute, and the claim rested on that instrument — which was
# wrong twice (R1#4: every event that was not an `open` returned immediately; R2#4: a
# descriptor-relative path was resolved against the working directory), and both times the instrument
# reported a clean run. What answers now is the tree itself, compared before and after by the caller,
# and a positive control with the cause removed shows that comparison can fail. The claim is
# narrower for it: this says nothing about a write that was ATTEMPTED and refused, because nothing
# on disk records one (owner's narrowing, 2026-10-25).
BYTECODE_PROBE = """
import json, runpy, sys

destination, driver = sys.argv[1], sys.argv[2]
sys.argv = [driver, 'inventory', '--to', destination, '--no-state']
code = 0
try:
    runpy.run_path(driver, run_name='__main__')
except SystemExit as leaving:
    code = leaving.code if isinstance(leaving.code, int) else 1
print(json.dumps({'code': code}))

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


class ScopedAnswer(Exception):
    """A layer answered scope by scope whose row is not complete (S-10): its status, its reasons, and
    the carriers of the scopes that did answer, which are published beside their scope's own row."""

    def __init__(self, status, reasons, carriers):
        super().__init__("; ".join(reasons))
        self.status, self.reasons, self.carriers = status, reasons, carriers


class Unsupported(Exception):
    """A carrier whose structure this producer cannot divide at all: the layer is `unsupported`,
    and what is missing is a splitter, not a correct file."""


class Malformed(Exception):
    """A carrier of a structure the producer does support, which this one instance of is broken: the
    layer is `incomplete` and the reason names the carrier. The two are not the same answer — one
    says the inventory cannot read this kind of file, the other that this file is wrong."""


def where_in(exc):
    """` at line N column M` from a parser's own numeric attributes, or nothing.

    A parser's MESSAGE is carrier text: tomllib names the duplicated table, json names the token,
    and `SyntaxError` names the identifier it tripped on. Those messages reached a layer row's
    reasons, which the floor projects as a diagnostic on its own — without the carrier's context —
    so a carrier the floor withholds WHOLE leaked through its own parse error (r5 F0). Only the
    position is taken, and only from the attributes, never parsed out of the message: the declared
    floor is Python 3.11, where `TOMLDecodeError` carries no such attributes at all, so this is
    absent as often as it is present."""
    line, column = getattr(exc, "lineno", None), getattr(exc, "colno", None)
    if line is None:
        return ""
    return f" at line {line}" + (f" column {column}" if column is not None else "")


def structured(path, text, form):
    """A supported structured carrier, parsed to prove it is well formed. A settings file is the
    carrier kind whose breakage the splitter cannot see: `plain_blocks` divides any text at all, so
    a settings file with a missing brace split clean and the layer reported complete (GA#5).

    The reason carries the path, a fixed category and a numeric position — never the parser's
    message, which is made of the carrier's own bytes (r5 F0)."""
    if form == "json":
        try:
            json.loads(text)
        except ValueError as exc:
            raise Malformed(f"{path}: MALFORMED_CARRIER: not valid JSON{where_in(exc)}") from exc
    elif form == "toml":
        if tomllib is None:
            raise Unsupported(f"{path}: this interpreter has no TOML reader, so a settings file of this kind "
                              f"cannot be proved well formed")
        try:
            tomllib.loads(text)
        except Exception as exc:  # tomllib raises its own decode error type
            raise Malformed(f"{path}: MALFORMED_CARRIER: not valid TOML{where_in(exc)}") from exc


def blocks_of(path, text, form=None):
    """The blocks of one carrier, by its declared form. The concatenation has to reproduce the
    carrier byte for byte, or the structure is one this producer does not support.

    The form is judged BEFORE the empty carrier returns: a form outside the closed set is a caller's
    error whatever the text, and `md` reached the plain splitter for every transcript carrier (#13)."""
    form = declared_form(form or form_of(path))
    if not text:
        return []
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
        # A fixed category and the position only: a `SyntaxError`'s message names the identifier it
        # tripped on, which is the carrier's text (r5 F0), and the type's name is not something a
        # reader of the row acts on (lead, after a36c728). A subclass is its base's category.
        category = next(text for kind, text in CARRIER_PARSE_FAILURES.items() if isinstance(exc, kind))
        raise Malformed(f"{path}: MALFORMED_CARRIER: {category}{where_in(exc)}") from exc
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


# The whole vocabulary of a carrier's form: the forms `blocks_of` splits and `structured` proves.
FORMS = ("markdown", "python", "json", "toml", "plain")


def declared_form(form):
    """`form` when it is one of `FORMS`, or a refusal by name. A form outside the set is a code
    defect, not a carrier property, so the refusal names the rule and nothing the caller passed."""
    if not (isinstance(form, str) and form in FORMS):
        raise Refused(f"CARRIER_FORM_UNDECLARED: a carrier's form is one of {list(FORMS)}")
    return form


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


def carrier(layer, path, text, item_ref=None, package_id=None, form=None, provenance=None, carrier_id=None):
    """One carrier. `form` is declared when the text is a member of the file the path names rather
    than the file itself — the session's compiled instruction text is markdown that lives inside an
    `output.json`, and reading its structure off the path's suffix made it a malformed settings
    file (GA#5). `carrier_id` is given for a transcript carrier and a session injection, whose
    identity is built from the raw values they were recorded under (step 0 S-11); every other
    carrier keeps `carrier_identity`."""
    return {"layer": layer, "path": path, "item_ref": item_ref, "package_id": package_id,
            "text": text, "version_sha256": sha256_text(text), "form": declared_form(form or form_of(path)),
            "carrier_id": carrier_id or carrier_identity(layer, path, item_ref, package_id),
            "provenance": provenance or {}}


def unit_ref(carrier_id, version_sha256, n):
    """The unit reference `r-` (step 0 S-11): the block's 1-based position `n` in ONE carrier version.
    `unit_id` is not one: its occurrence counter runs across a whole `units_of` call, so two versions
    of one carrier split together give one fragment two ids, and it is never a join key."""
    return opaque_id("r", "unit", carrier_id, version_sha256, n)


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
            carrier_id = item.get("carrier_id") or carrier_identity(
                item["layer"], item["path"], item.get("item_ref"), item.get("package_id"))
            unit = {"unit_id": unit_id, "unit_ref": unit_ref(carrier_id, item["version_sha256"], n),
                    "layer": item["layer"], "path": item["path"],
                    "heading": " > ".join(heading_path), "n": n, "text": text, "sha": sha256_text(text),
                    "class": classify(kind, heading_path), "operative_context": [],
                    "version_sha256": item["version_sha256"], "redaction_version": projection.CURRENT,
                    "block": kind, "item_ref": item["item_ref"], "package_id": item["package_id"],
                    "carrier_id": carrier_id,
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


def _carrier_key(unit):
    """A carrier's identity AND its version — what the context structures group by.

    `carrier_identity` holds no content, and one reference point can carry two VERSIONS of one
    identity (`event_carriers` makes a carrier per `(layer, scope)`). Grouped by the identity alone,
    the two versions' units became one carrier: a mention of that path reached both versions' units
    at once, and `carriers_at_path` deduplicated them to a single carrier, so the one thing the
    design says to do about two carriers at one path — state the ambiguity instead of resolving it —
    did not happen. The floor decision keyed the same way is r4 R0; this is the same defect in the
    structures beside it."""
    return unit["carrier_id"], unit.get("version_sha256")


def _section_spans(units):
    """Per carrier version, the units under each heading path — the span a heading opens."""
    spans = collections.defaultdict(list)
    for unit in units:
        spans[(_carrier_key(unit), tuple(h for h in unit["heading"].split(" > ") if h))].append(unit["unit_id"])
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
        by_carrier[_carrier_key(unit)].append(unit)
    carriers_at_path = collections.defaultdict(list)
    for unit in units:
        if _carrier_key(unit) not in carriers_at_path[unit["path"]]:
            carriers_at_path[unit["path"]].append(_carrier_key(unit))
    basenames = collections.defaultdict(list)
    for path in carriers_at_path:
        basenames[path.rsplit("/", 1)[-1]].append(path)
    frontmatter = {key: next((u["unit_id"] for u in rows if u["block"] == "frontmatter"), None)
                   for key, rows in by_carrier.items()}
    spans = _section_spans(units)
    by_id = {unit["unit_id"]: unit for unit in units}

    def conditions(unit):
        chain = tuple(h for h in unit["heading"].split(" > ") if h)
        found = []
        for (key, heading_path), members in spans.items():
            if key != _carrier_key(unit) or not heading_path:
                continue
            above = heading_path[:-1]
            if above == chain[:len(above)] and CONDITION_HEADING.search(heading_path[-1]):
                found += members
        return found

    def whole_carrier(key):
        """What a reader following a bare reference to this carrier version would have to read."""
        rows = [u["unit_id"] for u in by_carrier[key]
                if u["class"] == "operative" or u["block"] == "frontmatter"]
        return rows or [u["unit_id"] for u in by_carrier[key]]

    direct = {}
    for unit in units:
        context = [unit["unit_id"]]
        own = frontmatter.get(_carrier_key(unit))
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
            targets = [key for path in paths for key in carriers_at_path[path]]
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
            for key in targets:
                if heading:
                    rows = [u["unit_id"] for u in by_carrier[key]
                            if u["heading"] and heading.lower().startswith(u["heading"].rsplit(" > ", 1)[-1].lower())]
                    if rows:
                        reached += rows
                    else:
                        reached.append(f"{UNRESOLVED}{named}#{heading}")
                        origin(f"{UNRESOLVED}{named}#{heading}", "heading", match)
                else:
                    reached += whole_carrier(key)
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
                "sha256": re.compile(r"^[0-9a-f]{64}$"),
                # the step-0 ids, each `<prefix>-` and 24 hex (`opaque_id`)
                "event_id": re.compile(r"^e-[0-9a-f]{24}$"),
                "owner_ref": re.compile(r"^o-[0-9a-f]{24}$"),
                "session_ref": re.compile(r"^p-[0-9a-f]{24}$"),
                "scope_id": re.compile(r"^s-[0-9a-f]{24}$"),
                "unit_ref": re.compile(r"^r-[0-9a-f]{24}$"),
                "occurrence_id": re.compile(r"^q-[0-9a-f]{24}$"),
                "inventory_id": re.compile(r"^i-[0-9a-f]{24}$"),
                "segment_id": re.compile(r"^g-[0-9a-f]{24}$"),
                "commit_hash": re.compile(r"^[0-9a-f]{7,64}$")}


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


def _decision_key(carrier_id, carrier_text):
    """The key a floor decision is cached under: the carrier's identity AND its VERSION.

    `carrier_identity` is the package, the item and the delivered path, with no content in it, and
    one reference point can hold two versions of one identity — `event_carriers` makes a carrier per
    `(layer, scope)`, so a user-level instruction file loaded in two scopes at two versions is two
    carriers with one id. Keyed on the id alone, whichever version was decided first answered for
    both, and the version whose carrier the floor withholds WHOLE was emitted through the other
    version's extents: the lead reproduced a withheld secret reaching `shed` that way (r4 R0).

    The digest is taken from the carrier text itself rather than read from a record's
    `version_sha256`, because a cache key that can disagree with the bytes it answers for is the
    same defect one level further in."""
    return carrier_id, hashlib.sha256((carrier_text or "").encode("utf-8")).hexdigest()


def _decision_for(place, carrier_id, carrier_text):
    """The floor's whole-carrier decision for one carrier version, taken once per version."""
    decisions = place.setdefault("decisions", {})
    key = _decision_key(carrier_id, carrier_text)
    if key not in decisions:
        decisions[key] = projection.carrier_decision(carrier_text, place["home"])
    return decisions[key]


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
    # A post-condition over the loop above stood here — "the emitted row's fields are not the
    # table's" — and could not fire: `emitted` takes its keys from `fields` alone, and every key of
    # `fields` leaves the loop emitted, refused, or skipped as optional-and-absent, so the two sets
    # are equal by construction. A check that cannot fire is not a check (lead ruling, S8h).
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

GIT_TABLE = table_of({
    "commit_hash": as_opaque("commit_hash", nullable=True),
    "branch": as_metadata(nullable=True),
    "repository_url": as_metadata(nullable=True),
}, schema="git")

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
    # a scope's answer (S-10): the scope row and the event a unit of `current` came from
    "scope_id": as_opaque("scope_id"), "event_id": as_opaque("event_id"),
    # what a Codex `session_meta` records of its repository (step 0 S-19), userinfo removed
    "git": GIT_TABLE,
}, optional=("as_of", "session", "transcript", "where", "scope", "reference", "record", "identity",
             "status", "keep_units", "keep_reason", "hosts", "scope_id", "event_id", "git"), schema="provenance")

# §6.1's unit record as the artifact carries it. `operative_context` is ONE list with a per-item
# union: a resolved entry is an opaque unit id, and an unresolved one is built from the carrier
# offsets of the mention it came from — never from the stored string, which is what leaked (r3 #0).
UNIT_TABLE = table_of({
    "unit_id": as_opaque("unit_id"),
    # the unit's reference into `shared/store.json` (step 0 S-11, S-22)
    "unit_ref": as_opaque("unit_ref"),
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

# ---- `sessions.json` (step 0 S-14, S-5, S-11): the per-session records and their events. Every
# location is a number, every category a fixed word, every join an opaque reference; the ids a host
# wrote (session, agent, census id) pass the floor as metadata and are never a join key.
SESSION_KINDS = ("main", "subagent")
EVENT_KINDS = ("native", "session_injection")
BINDINGS = ("whole", "prefix", "none")
READ_OUTCOMES = ("bound", "appended", "changed", "unbound", "binding_invalid", "no_path", "unreadable")
UNDECODABLE_CATEGORIES = ("not_json", "not_object")
MEMBER_CATEGORIES = ("member_not_object", "member_type_unmapped", "member_path_invalid", "member_content_invalid")
DAMAGE_CATEGORIES = ("container_unusable", "locator_unusable", "locator_element_rejected")
INHERITED_CATEGORIES = ("another_session_id", "no_session_id")
# A session's own pin and its delivery (step 0 S-14, S-15, S-25; lead rulings on the P2.4 plan and their
# 12:25 amendment): one status and ONE reason each. A delivery's reason is the first broken link in the
# order the chain is read — the pin, its snapshot, the transcript read, a damaged injection event of the
# session's own owner, a recorded occurrence whose offsets could not be recovered — and only when none
# is broken, `no_record`: no recorded occurrence never reads as "not delivered".
PIN_STATUSES = ("read", "unpinned", "unknown")
PIN_REASONS = ("unpinned", "id_space", "pin_absent", "pin_mismatch", "pin_content_ref_mismatch", "input_failed",
               "input_unread")
SNAPSHOT_REASONS = ("snapshot_absent", "input_failed")
# a transcript that was not read: `changed` among them, since bytes that no longer match the census are
# never opened (`transcript_records`)
READ_FAILURES = ("unbound", "binding_invalid", "no_path", "changed", "unreadable")
DELIVERY_STATUSES = ("confirmed", "unknown")
SELECTION_REASONS = tuple(dict.fromkeys(PIN_REASONS + SNAPSHOT_REASONS))
DELIVERY_REASONS = tuple(dict.fromkeys(PIN_REASONS + SNAPSHOT_REASONS + READ_FAILURES
                                       + ("container_unusable", "locator_element_rejected", "recorded_unmapped",
                                          "no_record")))

UNKNOWN_ENTRY_TABLE = table_of({"reason": as_enum(lambda: UNKNOWN_REASONS), "line": as_scalar()},
                               optional=("line",), schema="unknown_entry")
LIMITATION_TABLE = one_of(
    table_of({"kind": as_constant("alt_paths"), "count": as_scalar()}),
    table_of({"kind": as_constant("undecodable"), "category": as_enum(UNDECODABLE_CATEGORIES),
              "line": as_scalar()}),
    table_of({"kind": as_constant("member_rejected"), "category": as_enum(MEMBER_CATEGORIES),
              "line": as_scalar(), "ordinal": as_scalar()}),
    table_of({"kind": as_constant("damaged"), "category": as_enum(DAMAGE_CATEGORIES), "line": as_scalar(),
              "ordinal": as_scalar()}, optional=("ordinal",)),
    table_of({"kind": as_constant("agent_id_unusable"), "count": as_scalar(), "line": as_scalar()}),
    table_of({"kind": as_constant("member_duplicate"), "line": as_scalar(), "ordinal": as_scalar()}),
)
OWNERSHIP_TABLE = table_of({
    "intervals": list_of(table_of({"owner_ref": as_opaque("owner_ref"), "from": as_scalar(), "to": as_scalar()})),
    "unknown": list_of(table_of({"from": as_scalar(), "to": as_scalar()})),
}, schema="ownership")
SESSION_TABLE = table_of({
    "session_ref": as_opaque("session_ref"),
    "session": as_metadata(),
    "host": as_enum(PROVENANCE_HOSTS),
    "kind": as_enum(SESSION_KINDS),
    "transcript": table_of({"host": as_enum(PROVENANCE_HOSTS), "id": as_metadata(),
                            "source": as_metadata(nullable=True)}),
    "parent_ref": as_opaque("session_ref", nullable=True),
    "binding": as_enum(BINDINGS),
    "read": as_enum(READ_OUTCOMES),
    "lines_read": as_scalar(nullable=True),
    "owners": list_of(table_of({"owner_ref": as_opaque("owner_ref"), "display": as_metadata()})),
    "ownership": OWNERSHIP_TABLE,
    "inherited_session_meta": table_of({key: as_scalar() for key in INHERITED_CATEGORIES}),
    "own_meta_unidentified": as_scalar(nullable=True),
    "limitations": list_of(LIMITATION_TABLE),
    "event_refs": list_of(as_opaque("event_id")),
    "segment_refs": list_of(as_opaque("segment_id")),
    "unknown": list_of(UNKNOWN_ENTRY_TABLE),
    "pin": table_of({
        "status": as_enum(PIN_STATUSES),
        "reason": as_enum(PIN_REASONS, nullable=True),
        "content_ref": as_opaque("sha256", nullable=True),
        "baseline_ref": as_metadata(nullable=True),
        "include_global_instructions": as_scalar(nullable=True),
    }, schema="pin"),
    "delivery": table_of({
        "status": as_enum(DELIVERY_STATUSES),
        "reason": as_enum(DELIVERY_REASONS, nullable=True),
        "event_refs": list_of(as_opaque("event_id")),
    }, schema="delivery"),
    "selection": table_of({
        "status": as_enum(PIN_STATUSES),
        "reason": as_enum(SELECTION_REASONS, nullable=True),
        "inventory_ref": as_opaque("inventory_id", nullable=True),
    }, schema="session_selection"),
}, schema="session")
EVENT_TABLE = table_of({
    "event_id": as_opaque("event_id"),
    "kind": as_enum(EVENT_KINDS),
    "host": as_enum(PROVENANCE_HOSTS),
    "session_ref": as_opaque("session_ref"),
    "owner_ref": as_opaque("owner_ref", nullable=True),
    "owner": as_metadata(),
    "line": as_scalar(),
    "at": as_metadata(nullable=True),
    "at_reason": as_enum(("undated", "undated_naive"), nullable=True),
    "damaged": as_enum(("container_unusable", "locator_element_rejected"), nullable=True),
    "interval_from": as_scalar(nullable=True),
    "interval_to": as_scalar(nullable=True),
    "certain_to": as_scalar(nullable=True),
    "uncertain_reason": as_enum(("undecodable_after", "ownership_unknown"), nullable=True),
    "where": as_metadata(nullable=True),
    "rejected": list_of(table_of({"ordinal": as_scalar(), "category": as_enum(MEMBER_CATEGORIES)})),
    # every member the event recorded, a collapsed duplicate's copy included, at its own ordinal: what an
    # occurrence of this event is held against (an injection event's carrier is its session's own)
    "members": list_of(table_of({"ordinal": as_scalar(), "carrier_id": as_opaque("carrier_id"),
                                 "version_sha256": as_opaque("sha256")})),
}, schema="event")
# One owner's segment (step 0 S-17): a line interval `[from, to)` of its transcript in which the event in
# force of each kind is fixed. Per kind: the event in force, or none yet, or the one in force past its
# certainty cut (the line named), or a kind nobody could look for, by the reason (`unsought`).
SEGMENT_STATES = ("in_force", "no_event_yet", "uncertain", "unsought")
IN_FORCE_TABLE = table_of({
    "state": as_enum(SEGMENT_STATES),
    "event_ref": as_opaque("event_id", nullable=True),
    "reason": as_enum(lambda: UNKNOWN_REASONS, nullable=True),
    "line": as_scalar(nullable=True),
}, schema="in_force")
SEGMENT_TABLE = table_of({
    "segment_id": as_opaque("segment_id"),
    "session_ref": as_opaque("session_ref"),
    "owner_ref": as_opaque("owner_ref"),
    "from": as_scalar(),
    "to": as_scalar(),
    "in_force": table_of({kind: IN_FORCE_TABLE for kind in EVENT_KINDS}),
}, schema="segment")
# One recorded occurrence (step 0 S-12, S-13): where in which event a carrier version's bytes sit. Its
# span counts code points of the decoded FIELD text the pointer names — not the carrier version's raw
# text, which is the store's coordinate. `unmapped` is a normalised match whose offsets could not be
# recovered: kept as evidence, with no version, span or digest (#14).
OCCURRENCE_METHODS = ("field", "exact", "normalised", "unmapped")
OCCURRENCE_TABLE = table_of({
    "occurrence_id": as_opaque("occurrence_id"),
    "event_id": as_opaque("event_id"),
    "ordinal": as_scalar(),
    "pointer": as_metadata(),
    "carrier_id": as_opaque("carrier_id"),
    "version_sha256": as_opaque("sha256", nullable=True),
    "start": as_scalar(nullable=True),
    "end": as_scalar(nullable=True),
    "sha256": as_opaque("sha256", nullable=True),
    "method": as_enum(OCCURRENCE_METHODS),
    "reason": as_enum(("recorded_unmapped",), nullable=True),
    "git": GIT_TABLE,
}, optional=("git",), schema="occurrence")
SESSIONS_PRODUCED_BY_TABLE = table_of({
    "module": as_constant("session-distill/runlib/inventory.py"),
    "design": as_constant(DESIGN),
    "commit": as_metadata(nullable=True),
})


# §8's freshness sentence, carried by every scope answer as data (the 1548 amendment §8).
FRESHNESS = ("the newest delivery on record, not the file on disk: an edit made after this event is unknown "
             "until a later transcript records it")
# The per-host counts of the scope universe (S-10): outcomes that answer no scope, each by its reason,
# and the events that are not eligible to answer at all.
UNIVERSE_COUNTS = ("no_scope", "cwd_unreadable", "memory_path_relative", "global_excluded_by_launch", "ineligible")
SCOPE_REASON_TABLE = table_of({"reason": as_enum(lambda: UNKNOWN_REASONS), "event_id": as_opaque("event_id"),
                               "session_ref": as_opaque("session_ref"), "line": as_scalar()},
                              optional=("event_id", "session_ref", "line"), schema="scope_reason")
SCOPE_TABLE = table_of({
    "scope_id": as_opaque("scope_id"),
    "layer": as_enum(lambda: SCOPED_LAYERS),
    "host": as_enum(PROVENANCE_HOSTS),
    "scope": as_metadata(nullable=True),
    "status": as_enum(lambda: SCOPE_STATUSES),
    "as_of": as_metadata(nullable=True),
    "session": as_metadata(nullable=True),
    "session_ref": as_opaque("session_ref", nullable=True),
    "line": as_scalar(nullable=True),
    "event_ids": list_of(as_opaque("event_id")),
    "reasons": list_of(SCOPE_REASON_TABLE),
    "evidence": list_of(table_of({"event_id": as_opaque("event_id"), "as_of": as_metadata(nullable=True)})),
    "limitations": list_of(as_enum(lambda: UNKNOWN_REASONS)),
    "freshness": as_constant(FRESHNESS),
}, schema="scope_answer")
UNIVERSE_TABLE = table_of({"host": as_enum(PROVENANCE_HOSTS), **{key: as_scalar() for key in UNIVERSE_COUNTS}},
                          schema="scope_universe")

# ---- `shared/store.json` (step 0 S-22): every carrier version the run names, once, with its
# context-free units. A unit of a reference document resolves here by its `unit_ref`, a version by
# `carrier_id` and `version_sha256`. Nothing here says when or from whom a version came: that is each
# occurrence's own record, and a version delivered three times is still one row.
SPLIT_OUTCOMES = ("split", "malformed", "unsupported")
SPAN_UNIT = "code_point"  # every [start, end) the store publishes counts Unicode code points of the raw text
CARRIER_VERSION_TABLE = table_of({
    "layer": as_enum(layer_names),
    "path": as_metadata(),
    "item_ref": as_metadata(nullable=True),
    "package_id": as_metadata(nullable=True),
    "form": as_enum(FORMS),
    "length": as_scalar(),
    "split": as_enum(SPLIT_OUTCOMES),
    "unit_refs": list_of(as_opaque("unit_ref")),
}, schema="carrier_version")
# A unit as the store carries it: no context and no provenance, its span in the RAW version's code
# points, and `sha` the raw fragment's digest, so a projected `text` still binds to the bytes it came
# from. `unit_id` is not here: it is the fragment's id within one reference document's split (see
# `unit_ref`), and the run-wide store would give one reference two of them.
CARRIER_UNIT_TABLE = table_of({
    "carrier_id": as_opaque("carrier_id"),
    "version_sha256": as_opaque("sha256"),
    "n": as_scalar(),
    "start": as_scalar(),
    "end": as_scalar(),
    "sha": as_opaque("sha256"),
    "heading": as_span("heading_spans", join=" > ", marks=True),
    "text": as_span("span"),
    "class": as_enum(lambda: schema_enum("unit_class") or ("operative", "reference")),
    "block": as_enum(BLOCK_KINDS),
    "redaction_version": as_constant(projection.CURRENT),
}, schema="carrier_unit")


def event_row(event):
    """One event as `sessions.json` carries it: the fields `EVENT_TABLE` declares, from the event."""
    instant = _instant(event.get("at"))
    interval = event.get("interval")
    return {"event_id": event["id"], "kind": event["kind"], "host": event["host"],
            "session_ref": event["session_ref"], "owner_ref": event.get("owner_ref"),
            "owner": event["session"], "line": event["n"],
            "at": instant.isoformat() if instant is not None else None, "at_reason": event.get("at_reason"),
            "damaged": event.get("damaged"),
            "interval_from": interval[0] if interval else None, "interval_to": interval[1] if interval else None,
            "certain_to": event.get("certain_to"), "uncertain_reason": event.get("uncertain_reason"),
            "where": event.get("where"),
            "rejected": [{"ordinal": row["ordinal"], "category": row["category"]}
                         for row in event.get("rejected") or []],
            "members": event_members(event)}


def event_members(event):
    """`(ordinal, carrier_id, version_sha256)` of every member a native event recorded, by ordinal, a
    collapsed duplicate's copy included; an injection event records none of its own."""
    if event["kind"] != "native":
        return []
    rows = [{"ordinal": member.get("ordinal", 0), "carrier_id": member["carrier_id"],
             "version_sha256": sha256_text(member["text"])} for member in event.get("files") or []]
    rows += [{"ordinal": row["ordinal"], "carrier_id": row["carrier_id"], "version_sha256": row["version_sha256"]}
             for row in event.get("duplicates") or []]
    return sorted(rows, key=lambda row: row["ordinal"])


def sessions_document(ctx):
    """`sessions.json`: every census row's per-session record and every event, none truncated."""
    place = {"home": ctx.get("home"), "decisions": {}}
    return {
        "document": "sessions",
        "produced_by": emit_row("produced_by", SESSIONS_PRODUCED_BY_TABLE, {
            "module": "session-distill/runlib/inventory.py", "design": DESIGN,
            "commit": ctx.get("commit")}, place),
        "span_unit": SPAN_UNIT,
        "sessions": [emit_row("session", SESSION_TABLE, record, place) for record in ctx.get("sessions") or []],
        "events": [emit_row("event", EVENT_TABLE, event_row(event), place) for event in ctx.get("events") or []],
        "segments": [emit_row("segment", SEGMENT_TABLE, row, place) for row in ctx.get("segments") or []],
        "occurrences": [emit_row("occurrence", OCCURRENCE_TABLE,
                                 {key: row[key] for key in OCCURRENCE_TABLE["fields"] if key in row}, place)
                        for row in ctx.get("occurrences") or []],
    }


def sessions_cross_problems(document):
    """What `sessions.json` gets wrong ACROSS its records (step 0 S-21's cross-record validation), each
    as a fixed code with counts: every event is listed by exactly one session record and points back at
    it, every listed event exists exactly once, and one owner's intervals of one kind are ordered and
    disjoint. The schema judges each record alone; none of this is visible to it."""
    problems = []
    events, sessions = document.get("events") or [], document.get("sessions") or []
    by_id = {}
    for event in events:
        by_id.setdefault(event.get("event_id"), []).append(event)
    twice = sum(1 for rows in by_id.values() if len(rows) > 1)
    if twice:
        problems.append(f"CROSS_EVENT_DUPLICATE: {twice} event id(s) name more than one event")
    session_of = {}
    for record in sessions:
        session_of.setdefault(record.get("session_ref"), []).append(record)
    if any(len(rows) > 1 for rows in session_of.values()):
        problems.append("CROSS_SESSION_DUPLICATE: a session reference names more than one record")
    listed = {}
    for record in sessions:
        for ref in record.get("event_refs") or []:
            listed.setdefault(ref, []).append(record.get("session_ref"))
    dangling = sum(1 for ref in listed if ref not in by_id)
    if dangling:
        problems.append(f"CROSS_EVENT_UNRESOLVED: {dangling} listed event reference(s) name no event")
    unlisted = sum(1 for ref in by_id if len(listed.get(ref) or []) != 1)
    if unlisted:
        problems.append(f"CROSS_EVENT_UNLISTED: {unlisted} event(s) listed by no session record, or by several")
    astray = sum(1 for ref, rows in by_id.items() for event in rows
                 if listed.get(ref) and listed[ref][0] != event.get("session_ref"))
    if astray:
        problems.append(f"CROSS_EVENT_ASTRAY: {astray} event(s) listed by another session than their own")
    lanes = {}
    for event in events:
        if event.get("owner_ref") is not None and event.get("interval_from") is not None:
            lanes.setdefault((event["owner_ref"], event.get("kind")), []).append(
                (event["interval_from"], event.get("interval_to")))
    overlapping = 0
    for rows in lanes.values():
        rows.sort()
        overlapping += sum(1 for (start, end), (after, _) in zip(rows, rows[1:])
                           if end is None or start >= end or end > after)
        overlapping += sum(1 for start, end in rows[-1:] if end is None or start >= end)
    if overlapping:
        problems.append(f"CROSS_INTERVAL_OVERLAP: {overlapping} interval(s) of one owner and kind are empty, "
                        f"open or overlap the next")
    return problems + segment_cross_problems(document, by_id)


def segment_cross_problems(document, by_id):
    """What the segments get wrong across `sessions.json` (step 0 S-17, S-21): each is listed by exactly
    its own session; one owner's segments of one transcript are ordered, disjoint and cover
    `[1, lines_read + 1)` with no gap; and per kind the event a segment names has the segment's owner and
    that kind, its interval covers the segment (its own line may precede it), and the segment's state
    agrees with the event's certainty cut. Each problem is a fixed code with a count."""
    problems = []
    rows, sessions = document.get("segments") or [], document.get("sessions") or []
    ids = {}
    for row in rows:
        ids.setdefault(row.get("segment_id"), []).append(row)
    if any(len(found) > 1 for found in ids.values()):
        problems.append("CROSS_SEGMENT_DUPLICATE: a segment id names more than one segment")
    listed = {}
    for record in sessions:
        for ref in record.get("segment_refs") or []:
            listed.setdefault(ref, []).append(record.get("session_ref"))
    dangling = sum(1 for ref in listed if ref not in ids)
    unlisted = sum(1 for ref, found in ids.items()
                   if listed.get(ref) is None or listed[ref] != [found[0].get("session_ref")])
    if dangling:
        problems.append(f"CROSS_SEGMENT_UNRESOLVED: {dangling} listed segment reference(s) name no segment")
    if unlisted:
        problems.append(f"CROSS_SEGMENT_UNLISTED: {unlisted} segment(s) listed by no session, by several, "
                        f"or by another session than their own")
    end_of = {record.get("session_ref"): (record.get("lines_read") or 0) + 1 for record in sessions}
    lanes = {}
    for row in rows:
        lanes.setdefault((row.get("session_ref"), row.get("owner_ref")), []).append((row.get("from"), row.get("to")))
    broken = 0
    for (session, _owner), spans in lanes.items():
        spans.sort(key=lambda span: (span[0] is None, span))
        edges = [1] + [end for _start, end in spans]
        broken += sum(1 for (start, end), expected in zip(spans, edges)
                      if start != expected or not isinstance(end, int) or end <= start)
        broken += 0 if spans and spans[-1][1] == end_of.get(session) else 1
    if broken:
        problems.append(f"CROSS_SEGMENT_PARTITION: {broken} segment(s) or owner(s) whose segments do not "
                        f"partition the transcript from line 1 to its end")
    astray = 0
    for row in rows:
        for kind, state in (row.get("in_force") or {}).items():
            event = (by_id.get(state.get("event_ref")) or [None])[0]
            if state.get("state") in ("no_event_yet", "unsought"):
                astray += 0 if state.get("event_ref") is None else 1
                continue
            cut = (event or {}).get("certain_to")
            astray += 1 if event is None or event.get("owner_ref") != row.get("owner_ref") \
                or event.get("kind") != kind or event.get("session_ref") != row.get("session_ref") \
                or not (event.get("interval_from") or 0) <= row.get("from", 0) \
                or not row.get("to", 0) <= (event.get("interval_to") or 0) \
                or (state.get("state") == "in_force" and cut is not None and row.get("to", 0) > cut) \
                or (state.get("state") == "uncertain" and (cut is None or row.get("from", 0) < cut
                                                           or state.get("line") != cut)) else 0
    if astray:
        problems.append(f"CROSS_SEGMENT_EVENT: {astray} segment state(s) naming an event of another owner, "
                        f"session or kind, one whose interval does not cover the segment, or one its cut "
                        f"contradicts")
    return problems


def occurrence_cross_problems(sessions, store):
    """What the occurrences get wrong against the events and the store (step 0 S-21): each id is the one
    its event, ordinal and pointer derive and names one occurrence, its event is published, a mapped
    occurrence's version is in the store with exactly its span's length and the digest of its recorded
    bytes, and an unmapped one carries no version, span or digest and says why.

    Its carrier is the one its event recorded at its ordinal, or for an injection event the session's own
    injection carrier, and the kind of place its pointer names is the layer of the version it names
    (lead, carried from P2.3b): an occurrence that names another carrier than the one at its place is a
    claim about bytes its event never held."""
    problems = []
    rows = sessions.get("occurrences") or []
    events = {event.get("event_id"): event for event in sessions.get("events") or []}
    records = {record.get("session_ref"): record for record in sessions.get("sessions") or []}
    versions = store.get("versions") or {}
    twice = sum(1 for n in collections.Counter(row.get("occurrence_id") for row in rows).values() if n > 1)
    if twice:
        problems.append(f"OCCURRENCE_DUPLICATE: {twice} occurrence id(s) name more than one occurrence")
    for n, row in enumerate(rows):
        where = f"occurrences[{n}]"
        if row.get("event_id") not in events:
            problems.append(f"OCCURRENCE_EVENT_UNRESOLVED {where}: its event is not published")
        if row.get("occurrence_id") != opaque_id("q", "occurrence", row.get("event_id"), row.get("ordinal"),
                                                 row.get("pointer")):
            problems.append(f"OCCURRENCE_ID_MISMATCH {where}: not the id its event, ordinal and pointer derive")
        event = events.get(row.get("event_id"))
        if event is not None and not occurrence_carrier_holds(event, row, records):
            problems.append(f"OCCURRENCE_CARRIER_MISMATCH {where}: not the carrier its event recorded at its "
                            f"place, nor its session's own injection carrier")
        if row.get("method") == "unmapped":
            if row.get("reason") != "recorded_unmapped" or any(
                    row.get(key) is not None for key in ("version_sha256", "start", "end", "sha256")):
                problems.append(f"OCCURRENCE_UNMAPPED_INCONSISTENT {where}: an unmapped occurrence carries a "
                                f"version, a span or a digest, or no reason")
            continue
        if row.get("reason") is not None or row.get("version_sha256") is None:
            problems.append(f"OCCURRENCE_UNMAPPED_INCONSISTENT {where}: a mapped occurrence names no version, "
                            f"or a reason")
            continue
        version = (versions.get(row.get("carrier_id")) or {}).get(row.get("version_sha256"))
        if version is None:
            problems.append(f"OCCURRENCE_VERSION_UNRESOLVED {where}: its carrier version is not in the store")
            continue
        if version.get("layer") not in pointer_layers(row.get("pointer")):
            problems.append(f"OCCURRENCE_LAYER_MISMATCH {where}: the place its pointer names does not hold "
                            f"the layer of the version it names")
        start, end = row.get("start"), row.get("end")
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start <= end
                and end - start == version.get("length")):
            problems.append(f"OCCURRENCE_SPAN_MISMATCH {where}: its span is not its version's length")
        if row.get("sha256") != row.get("version_sha256"):
            problems.append(f"OCCURRENCE_DIGEST_MISMATCH {where}: its recorded bytes are not its version")
    return problems


# The kind of place a pointer names, and the layers a version found there can be (step 0 S-13): an
# instructions member, a Codex block, or the selected body in a system prompt or a request shape.
POINTER_KINDS = (("/attachment/files/", ("native_global", "native_project", "native_memory")),
                 ("/payload/base_instructions", ("native_undivided",)),
                 ("/attachment/systemPrompt/", ("session_injection",)),
                 ("/shape/system/", ("session_injection",)))


def pointer_layers(pointer):
    """The layers a version at `pointer` can be, or `()` for a place no recorded event points at."""
    text = pointer if isinstance(pointer, str) else ""
    return next((layers for prefix, layers in POINTER_KINDS if text.startswith(prefix)), ())


def occurrence_carrier_holds(event, row, records):
    """Whether an occurrence names the carrier its event recorded at its ordinal (with that member's
    version when it is mapped), or, in an injection event, its session's own injection carrier — the
    session's pin read and its snapshot's `c-`."""
    if event.get("kind") == "native":
        member = next((member for member in event.get("members") or [] if member.get("ordinal") == row.get("ordinal")),
                      None)
        return member is not None and member.get("carrier_id") == row.get("carrier_id") \
            and (row.get("method") == "unmapped" or member.get("version_sha256") == row.get("version_sha256"))
    pin = (records.get(event.get("session_ref")) or {}).get("pin") or {}
    return pin.get("status") == "read" and pin.get("content_ref") is not None \
        and row.get("carrier_id") == injection_carrier_id(event.get("host"), pin.get("content_ref"))


def store_carriers(ctx):
    """Every carrier the run names: what each reference point's layer rows carried, and every member
    of every recorded event, the ones no scope chose included. Damaged events carry none."""
    named = list(ctx.get("carriers_named") or [])
    for event in ctx.get("events") or []:
        named += [member_carrier(event, member) for member in event.get("files") or []]
    # what a transcript recorded of a session's selected body, at each place it was found (M1, #14):
    # an exact match is the selected version itself, a normalised one a version of its own
    named += [carrier("session_injection", f"{row['host']}:session_injection:{row['pointer']}", row["recorded"],
                      form="markdown", carrier_id=row["carrier_id"])
              for row in ctx.get("occurrences") or [] if row.get("recorded") is not None
              and row.get("kind") == "session_injection"]
    return named


def store_document(ctx):
    """`shared/store.json`: each carrier VERSION once, by (`carrier_id`, `version_sha256`), split on
    its own so its units do not depend on what else a call held, every unit through the floor with
    that version's whole-carrier decision. A version the splitter refuses is listed with no units and
    the refusal's kind, never dropped."""
    place = {"home": ctx.get("home"), "decisions": {}}
    by_version = {}
    for item in store_carriers(ctx):
        by_version.setdefault((item["carrier_id"], item["version_sha256"]), item)
    versions, units = {}, {}
    for (carrier_id, version), item in sorted(by_version.items()):
        try:
            split, produced = "split", units_of([item])
        except Malformed:
            split, produced = "malformed", []
        except Unsupported:
            split, produced = "unsupported", []
        where = f"versions[{carrier_id}][{version}]"
        _emit_value(as_opaque("carrier_id"), carrier_id, place, f"{where}<key>")
        versions.setdefault(carrier_id, {})[version] = emit_row(where, CARRIER_VERSION_TABLE, {
            "layer": item["layer"], "path": item["path"], "item_ref": item.get("item_ref"),
            "package_id": item.get("package_id"), "form": item["form"], "length": len(item["text"]),
            "split": split, "unit_refs": [unit["unit_ref"] for unit in produced]}, place)
        place["decision"] = _decision_for(place, carrier_id, item["text"])
        for unit in produced:
            place["unit"] = unit
            units[unit["unit_ref"]] = emit_row(f"units[{unit['unit_ref']}]", CARRIER_UNIT_TABLE, {
                "carrier_id": carrier_id, "version_sha256": version, "n": unit["n"],
                "start": unit["span"][0], "end": unit["span"][1], "sha": unit["sha"],
                "class": unit["class"], "block": unit["block"], "redaction_version": unit["redaction_version"],
                "carrier_text": unit["carrier_text"], "span": unit["span"],
                "heading_spans": unit["heading_spans"]}, place)
    return {"document": STORE, "span_unit": SPAN_UNIT,
            "produced_by": emit_row("produced_by", SESSIONS_PRODUCED_BY_TABLE, {
                "module": "session-distill/runlib/inventory.py", "design": DESIGN,
                "commit": ctx.get("commit")}, place),
            "versions": versions, "units": units}


def store_cross_problems(store, documents):
    """What the store and the documents that point into it get wrong ACROSS records (step 0 S-21):
    every reference resolves exactly once, a unit's version is one of its carrier's versions and
    lists it, a unit's reference is the one its version and position derive, its span lies inside the
    version, and every unit a reference document publishes is that block of the store."""
    problems, listed = [], collections.Counter()
    versions, units = store.get("versions") or {}, store.get("units") or {}
    for carrier_id, rows in versions.items():
        for version, row in rows.items():
            for ref in row.get("unit_refs") or []:
                listed[ref] += 1
                found = units.get(ref)
                if found is None:
                    problems.append(f"STORE_UNRESOLVED {ref}: a version lists a unit the store does not hold")
                elif (found.get("carrier_id"), found.get("version_sha256")) != (carrier_id, version):
                    problems.append(f"STORE_VERSION_MISMATCH {ref}: listed by a version it is not a unit of")
    for ref, found in units.items():
        if listed[ref] != 1:
            problems.append(f"STORE_UNIT_UNLISTED {ref}: its version lists it {listed[ref]} time(s), not once")
        if ref != unit_ref(found.get("carrier_id"), found.get("version_sha256"), found.get("n")):
            problems.append(f"STORE_REF_MISMATCH {ref}: not the reference its version and position derive")
        version = (versions.get(found.get("carrier_id")) or {}).get(found.get("version_sha256"))
        if version is None:
            problems.append(f"STORE_VERSION_ABSENT {ref}: its carrier version is not in the store")
        elif not (isinstance(found.get("start"), int) and isinstance(found.get("end"), int)
                  and 0 <= found["start"] <= found["end"] <= version.get("length", -1)):
            problems.append(f"STORE_SPAN_OUTSIDE {ref}: its span is not inside its version's text")
    for name, document in sorted(documents.items()):
        for n, unit in enumerate(document.get("units") or []):
            found = units.get(unit.get("unit_ref"))
            if found is None:
                problems.append(f"STORE_UNRESOLVED {name}.units[{n}]: its unit_ref is not in the store")
            elif (found.get("carrier_id"), found.get("version_sha256"), found.get("n"), found.get("sha")) \
                    != (unit.get("carrier_id"), unit.get("version_sha256"), unit.get("n"), unit.get("sha")):
                problems.append(f"STORE_MISMATCH {name}.units[{n}]: the store's unit at its reference is another block")
    return problems


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
        decision = None
        if carrier_text is not None:
            # Once per carrier VERSION, not once per span: the decision is a property of the carrier's
            # bytes, and it carries the floor's whole-carrier WITHHOLDING as well as its extents. The
            # decision this row is emitted with is the one `_decision_for` just answered for THESE
            # bytes; a second lookup by the id alone is what crossed two versions (r4 R0).
            decision = _decision_for(place, unit["carrier_id"], carrier_text)
        place["unit"] = unit
        place["decision"] = decision
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
            omissions.append({"path": relative, "reason": f"unreadable: {acquisition_reason(exc)}"})
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
# production runs it, and this module, whose own entry point the boundary-bootstrap control runs as
# a production command from a copy with `runlib/entry.py` broken (r3 #2). `learn/redact.py` was here
# while the bytecode control loaded the floor by path to make its own observer fire; the observer is
# gone and so is the member.
COPIED_MEMBERS = ("session-distill/distill.py", "session-distill/runlib/inventory.py")


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


# The entry files whose own source carries the cause: each sets `sys.dont_write_bytecode` before it
# imports anything that is not the standard library. Declared, so the judge below cannot be green
# about an empty set.
ENTRY_FILES = ("session-distill/distill.py", "session-distill/runlib/inventory.py")


def _stdlib_only(node):
    """Whether this import names nothing but standard-library modules.

    The test is `sys.stdlib_module_names`, a frozenset the interpreter publishes, so the contract
    behind "this import cannot be one of ours" is Python's own. Naming this repository's own
    directories instead would be an enumeration of prefixes — the shape that keeps being the hole."""
    if isinstance(node, ast.ImportFrom):
        return node.level == 0 and bool(node.module) and \
            node.module.split(".")[0] in sys.stdlib_module_names
    return all(alias.name.split(".")[0] in sys.stdlib_module_names for alias in node.names)


def guard_before_imports(source):
    """Violations, in one entry file's own source, of the rule that bytecode writing is turned off
    BEFORE anything of this repository is imported.

    `runlib.projection` loads `learn/redact.py` by path at import time, and a cache write lands
    beside the file it caches — in the checkout, or in a frozen copy a run is about to hash (GB#7).
    Setting the flag is therefore not enough: it has to come first, and "first" is a fact about the
    order of statements, which only the source can answer. A control that reads the flag at runtime
    sees it set and learns nothing about the order.

    Default-deny. Before the guard, a module-level statement may be the module docstring, a
    `__future__` import, or an import of the standard library — nothing else. A repository import, a
    dynamic `importlib.import_module(...)`, an assignment and a bare call are each refused, because
    any of them can be what loads and caches a module.

    The guard must be the literal module-level `sys.dont_write_bytecode = True`. Nested inside `if`,
    `try` or `with` it is not a statement this judge can order at all, so it does not count as the
    guard: a guard under a condition is a guard that may not run."""
    body = list(ast.parse(source).body)
    at = next((n for n, node in enumerate(body) if _is_the_guard(node)), None)
    if at is None:
        nested = [node.lineno for node in ast.walk(ast.parse(source)) if _is_the_guard(node)]
        return [f"BYTECODE_GUARD_ABSENT: no module-level `sys.dont_write_bytecode = True`"
                + (f"; one is nested at line {nested[0]}, where it may not run" if nested else "")]
    problems = []
    for node in body[:at]:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            continue                                              # the module's own docstring
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)) and _stdlib_only(node):
            continue
        problems.append(f"BYTECODE_GUARD_LATE line {node.lineno}: a "
                        f"{type(node).__name__} stands before the guard, so a module may be loaded "
                        f"and cached before bytecode writing is turned off")
    return problems


def _is_the_guard(node):
    """Whether this statement IS `sys.dont_write_bytecode = True`."""
    return (isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Attribute)
            and node.targets[0].attr == "dont_write_bytecode"
            and isinstance(node.targets[0].value, ast.Name) and node.targets[0].value.id == "sys"
            and isinstance(node.value, ast.Constant) and node.value.value is True)


def guard_problems(root=REPO, entries=ENTRY_FILES):
    """`guard_before_imports` over every declared entry file, each named with its own violations."""
    problems = []
    for relative in entries:
        path = pathlib.Path(root) / relative
        if not path.is_file():
            problems.append(f"BYTECODE_GUARD_ABSENT {relative}: no such file")
            continue
        problems += [f"{row.split(':', 1)[0]} {relative}:{row.split(':', 1)[1]}"
                     for row in guard_before_imports(path.read_text(encoding="utf-8"))]
    if not entries:
        problems.append("BYTECODE_GUARD_ABSENT: no entry file was judged, so this says nothing")
    return problems


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
    declared root `boundary` (GB#8, GC#7).

    Each omission is a ROW, `{path, outcome, reason, code, message}`, because two different facts
    used to share one string: an input that is not there (`absent`) and one that is there and was not
    read (`failed`: a link, a source the selection does not admit, a read that failed). Downstream they
    mean different things — an optional journal that is absent is an empty answer, one that failed is
    no answer — and the caller decides which by the input's class (#16). `omission_line` renders a
    row the way this function used to report it."""
    destination = pathlib.Path(destination)
    missing = []

    def omitted_row(path, outcome, reason, exc=None):
        missing.append({"path": path, "outcome": outcome, "reason": reason,
                        "code": refusal_code(exc) if exc is not None else None,
                        "message": None if exc is None else (str(exc) if isinstance(exc, Refused)
                                                            else projected_message(exc))})

    for source, relative in sources:
        source = pathlib.Path(source).expanduser()
        target = confined(destination, relative)
        if linked_above(source, boundary) is not None:
            omitted_row(relative, "failed", "symlink")
            continue
        if source.is_dir():
            readable, omitted = walk_source(source, boundary)
            for inner, path in readable:
                inner_target = confined(target, inner)
                try:
                    admitted = source_selection(path, boundary or source)
                except Refused as exc:
                    omitted_row(f"{relative}/{inner}", "failed", "not_admitted", exc)
                    continue
                inner_target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    inner_target.write_bytes(admitted.read_bytes())
                except OSError as exc:
                    omitted_row(f"{relative}/{inner}", "failed", "unreadable", exc)
            for row in omitted:
                omitted_row(f"{relative}/{row['path']}", "failed", row["reason"])
        elif source.is_file():
            try:
                admitted = source_selection(source, boundary)
            except Refused as exc:
                omitted_row(relative, "failed", "not_admitted", exc)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.write_bytes(admitted.read_bytes())
            except OSError as exc:
                omitted_row(relative, "failed", "unreadable", exc)
        else:
            omitted_row(relative, "absent", "absent")
    return missing


# `blocks_of`'s parse failures of a supported form, by the category a reason names them under.
CARRIER_PARSE_FAILURES = {SyntaxError: "the carrier does not parse in its form",
                          ValueError: "the carrier does not parse in its form",
                          RecursionError: "the carrier nests deeper than the splitter reads"}


def refusal_code(exc):
    """The first word of this module's own refusal — `SOURCE_LINKED`, `PIN_ABSENT` — or the
    exception's type name. A fixed vocabulary either way: never the message, which names paths."""
    if isinstance(exc, Refused):
        word = str(exc).split(" ", 1)[0].rstrip(":")
        return word if re.fullmatch(r"[A-Z][A-Z0-9_]*", word) else "REFUSED"
    return type(exc).__name__


def omission_line(row):
    """One `freeze` omission as the line it was reported as before it became a row."""
    if row["outcome"] == "absent":
        return row["path"]
    if row["reason"] == "not_admitted":
        return f"{row['path']}: not admitted: {row['message']}"
    if row["reason"] == "unreadable":
        return f"{row['path']}: {row['message']}"
    return f"{row['path']}: {row['reason']}"


def omission_lines(rows):
    return [omission_line(row) for row in rows]


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

def catalog_module(tree):
    """The checkout's shipped catalog loader, as a module."""
    tree = pathlib.Path(tree)
    path = tree / "compose" / "instructions_catalog.py"
    if not path.is_file():
        raise Refused(f"PRODUCER_UNAVAILABLE {masked(path)}: the catalog producer needs the shipped loader")
    spec = importlib.util.spec_from_file_location("instructions_catalog_frozen", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(tree / "compose"))
    with no_bytecode():
        spec.loader.exec_module(module)
    return module


def catalog_carriers(tree, layer="catalog", adopted=False):
    """Rules, guides, skills, hooks and agents of a checkout's catalog, through the shipped loader.
    `adopted=True` keeps the items an adopted package brought instead of the core ones."""
    tree = pathlib.Path(tree)
    module = catalog_module(tree)
    with no_bytecode():
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
    which is all the compiler takes from it; every other kind carries its member files.

    An item that names no kind or no ref is a malformed item, said so in a declared reason: indexed
    straight, it reached a layer row as the exception's type and text (lead, after a36c728)."""
    if not (isinstance(item, dict) and isinstance(item.get("kind"), str) and isinstance(item.get("ref"), str)):
        raise Malformed(f"MALFORMED_ITEM: a {layer} item that names no kind or no ref")
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
    "unbound": "unknown: the census holds no binding for this transcript, so it is not opened",
    "binding_invalid": ("unknown: the census binding for this transcript is not a hash with a line count, "
                        "so it is not opened"),
    "input_absent": "unknown: a required input is absent from the owner's state",
    "input_failed": "unknown: an input of the owner's state could not be acquired",
    "input_unread": "unknown: this run was given no root to read the input from",
    "no_path": "unknown: the census row names no file to read",
    "ownership_unknown": "unknown: a sidechain record that names no agent, so no owner it belongs to",
    "undated": "unknown: the record carries no instant this inventory reads",
    "undated_naive": "unknown: the record's instant carries no zone, and none is guessed",
    "own_meta_unidentified": ("unknown: the rollout's first session_meta names no session, and no later "
                              "one names this rollout"),
    "container_unusable": "unknown: an injection record whose container cannot be read",
    "undecodable_after": "uncertain: a line that does not decode lies inside this event's interval",
    "no_scope": "not an outcome: the record names no cwd, so it answers no project scope",
    "cwd_unreadable": "unknown: the record's cwd is not a string naming an absolute path",
    "memory_path_relative": "not an outcome: the AutoMem path is not absolute, and nothing resolves it",
    "tie": "unknown: two transcripts record different sets for this scope at one instant",
    "memory_unconfirmed": ("unknown: a later injection of the same project names no member of this memory "
                           "directory"),
    "member_unmapped": "unknown: an injection carries a member whose type no native layer admits",
    "member_rejected": "incomplete: an injection carries a member of this layer whose content is unusable",
    "codex_undivided": ("unknown: Codex delivers its instructions as one block, so no global, project or "
                        "memory part of it is known"),
    "exclusion_unobservable": ("limitation: the session has no pin, so a launch that excluded the global "
                               "instructions cannot be seen"),
    "exclusion_unreadable": ("unknown: the session's pin was not read, so whether its launch excluded the global "
                             "instructions is not known"),
    "global_excluded_by_launch": ("not an outcome: the session was launched without the global instructions, so "
                                  "its global set is not a deletion"),
    "undecodable_elsewhere": ("uncertain: another transcript of this host holds a line that does not decode, "
                              "after its last dated event and not bracketed below this answer"),
    "locator_element_rejected": ("unknown: an element of the field the body is located in was rejected, and "
                                 "the body is not among the rest"),
    # a session's own pin chain (step 0 S-15, S-16, S-25), and its delivery when no link of it is broken
    "id_space": ("unknown: Codex session ids and pins are different id spaces, so no pin is associated with "
                 "a rollout, an equal id included"),
    "pin_absent": "unknown: the census names a pin for this session that the owner's state does not hold",
    "pin_mismatch": "unknown: the pin at this session's path names another host or session",
    "pin_content_ref_mismatch": "unknown: the session's pin names another snapshot than its census row",
    "snapshot_absent": "unknown: the session's pin is there and the snapshot it names is not",
    "no_census_session": "unknown: the pinned session has no census row, so no transcript of it is read",
    "recorded_unmapped": ("unknown: a normalised match of the selected body whose offsets could not be recovered "
                          "is the only recorded occurrence"),
    # a selection's native layers, an unpinned release, and a baseline a release names (S-15, S-24, S-25)
    "per_event": ("unknown: a native layer is what each event recorded, so a selection does not hold one; the "
                  "session's events in sessions.json do"),
    "release_history_deferred": ("unknown: which baseline an unpinned session ran under needs the baseline-selection "
                                 "history, which a follow-up package builds; the installed-now inventory is not it"),
    "baseline_absent": "unknown: the release names a baseline the owner's state does not hold",
    # a segment before an owner's first event of a kind (S-17), and an injection nobody can look for
    # because the body that finds it is empty (R15's `unsought`)
    "no_event_yet": "unknown: no event of this kind is recorded yet at this line of the transcript",
    "injection_body_empty": ("unknown: the session's own snapshot holds an empty session-injection body, so no "
                             "injection of it can be looked for"),
}


def reason(key):
    """A reason as a published record names it: its KEY, which must be in `UNKNOWN_REASONS`.
    `reason_problems` reads every `reason("...")` call, so a key named here and nowhere declared
    fails there, and a declared key counts as reported."""
    if key not in UNKNOWN_REASONS:
        raise KeyError(key)
    return key


def reason_key(message):
    """The `UNKNOWN_REASONS` key a message states, by the text it starts with, or None: the record
    of a session whose transcript raised names its reason by key, never by the message."""
    text = str(message)
    hits = [key for key, value in UNKNOWN_REASONS.items() if text.startswith(value)]
    return max(hits, key=lambda key: len(UNKNOWN_REASONS[key])) if hits else None


def opaque_id(prefix, *parts):
    """`<prefix>-` and 24 hex of the sha256 of `parts` as one canonical JSON array: UTF-8, no
    whitespace, raw values (step 0 S-11). The id says nothing of what it was built from, so it can
    join two documents without either one publishing the raw value."""
    canonical = json.dumps(list(parts), separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"


SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

# The inputs a producer reads from the owner's state, and what an ABSENCE of each one means (#16).
# `optional`: the absence is an answer — a learning journal that is not there is complete and empty,
# and so is a personal state the owner never wrote (the store reads both that way). `required`: the
# producer cannot answer without it, so the absence is a named unknown; a pin, its snapshot and a
# baseline are of this kind, and so is the runtime state, because without it nothing names the
# installed baseline the current overlays resolve against. A FAILED acquisition — a link, an
# unreadable file, a source the selection does not admit — is unknown whatever the class: the input
# is there and was not read. Every producer declares the kinds it reads on its `LAYERS` entry.
INPUT_CLASSES = {
    "runtime_state": "required",
    "user_state": "optional",
    "learning_journals": "optional",
    "pin": "required",
    "snapshot": "required",
    "installed_baseline": "required",
    "release_baseline": "required",
}


# A producer that raised: the layer row's declared reason, with `acquisition_reason`'s fixed category.
PRODUCER_FAILED = "the producer could not read its input, so this layer has no record here"


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


# The census reasons and entrypoints that say a row's own thread is a child (census.py 221-245,
# 333, and `index_only`'s `excluded`/`subagent`).
SUBAGENT_REASONS = frozenset(("child_without_parent", "orphan_child", "subagent"))
SUBAGENT_ENTRYPOINTS = frozenset(("sidechain", "subagent"))


def transcript_kind(entry):
    """`subagent` or `main` for a census row, from its LINEAGE and never from its processing status.

    A child whose parent the census cleared (`orphan_child`) or never found (`child_without_parent`)
    is still a subagent: the row stops being `child_of` (census.py ~333) without its thread becoming
    a main session. A Codex child can keep `entrypoint='cli'` (lineage.py 164-166, census.py
    240-241), so the entrypoint alone never makes a row main; what makes it a child is the status or
    the reason the census gave it."""
    reason, entrypoint = entry.get("reason"), entry.get("entrypoint")
    if entry.get("status") == "child_of" \
            or (isinstance(reason, str) and reason in SUBAGENT_REASONS) \
            or (isinstance(entrypoint, str) and entrypoint in SUBAGENT_ENTRYPOINTS):
        return "subagent"
    return "main"


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
        versions = entry.get("versions")
        version = versions[-1] if isinstance(versions, list) and versions and isinstance(versions[-1], dict) else {}
        pin = entry.get("pin") if isinstance(entry.get("pin"), dict) else {}
        rows.append({"host": entry.get("host"), "id": entry.get("id"), "path": entry.get("path"),
                     "kind": transcript_kind(entry), "status": entry.get("status"),
                     "reason": entry.get("reason"), "entrypoint": entry.get("entrypoint"),
                     "parent": entry.get("parent"), "sha256": entry.get("sha256"),
                     "prefix_sha": version.get("prefix_sha"), "record_count": version.get("record_count"),
                     "pin": pin.get("content_ref"), "source": entry.get("source"),
                     # census keeps the first file of an identity found twice and lists the others
                     # (census.py 324-326): they are COUNTED, as a limitation, and never read (M9)
                     "alt_paths": len(entry["alt_paths"]) if isinstance(entry.get("alt_paths"), list) else 0})
    return rows


def binding_of(entry):
    """`(whole, prefix)`: the census row's whole-file hash, and its `(prefix_sha, record_count)` —
    each None when the row does not carry it, and each validated ON ITS OWN.

    A transcript is opened only under a binding (#9). The census acquires hashes only for the rows
    it first classified `eligible` (census.py 349-360), so a child, an excluded row and an
    `unknown_provenance` one arrive with `sha256: None` and no version; comparing only `if sha256`
    read such a row anyway and bound it to nothing. A row with neither binding is `unbound` and its
    file is never opened. A binding that is there but malformed refuses as THAT binding — it never
    falls through to no comparison at all. A zero-line prefix is a prefix like any other."""
    label = f"{entry.get('host')}:{entry.get('id')}"
    whole = entry.get("sha256")
    prefix, count = entry.get("prefix_sha"), entry.get("record_count")
    if whole is None and prefix is None and count is None:
        raise Unacquired(f"{UNKNOWN_REASONS['unbound']} ({label})")
    if whole is not None and not (isinstance(whole, str) and SHA256_HEX.match(whole)):
        raise Unacquired(f"{UNKNOWN_REASONS['binding_invalid']} ({label}: the whole-file hash)")
    if (prefix, count) != (None, None) and not (isinstance(prefix, str) and SHA256_HEX.match(prefix)
                                                  and type(count) is int and count >= 0):
        raise Unacquired(f"{UNKNOWN_REASONS['binding_invalid']} ({label}: the complete-line prefix)")
    return whole, (None if prefix is None else (prefix, count))


def transcript_records(entry, zstd=None):
    """One transcript, read through the S1 reader and bound to its census record:
    `{records: [(line, record)], undecodable: [(line, category)], lines, which}`.

    `line` is the record's 1-based number among the file's COMPLETE lines — the coordinate the views
    stage uses for a record's `line`, so a turn and an event of one transcript compare directly. It is
    never the index among decoded objects: a malformed or non-object line in front of an event
    shifted that index, and cutting a prefix by it let appended records back in (#10). A line that
    does not decode is kept as a fixed category at its position (M5), because a dropped line is a
    record nobody can say anything about — not even that it was there.

    A file whose bytes no longer hash to that record is NOT re-read and not repaired: the session's
    reference points go `unknown` with that reason, because a silent re-read answers about a
    different file than every other stage of the run judged. A transcript the host has grown since —
    append-only, with the census's own complete-line prefix intact — is read up to the census's
    boundary and says so."""
    whole_sha, prefix = binding_of(entry)
    label = f"{entry.get('host')}:{entry.get('id')}"
    if not entry.get("path"):
        raise Unacquired(f"{UNKNOWN_REASONS['no_path']} ({label})")
    count = prefix[1] if prefix else None
    digest = hashlib.sha256()
    prefix_seen = digest.hexdigest() if count == 0 else None
    line, read, undecodable, tail = 0, [], [], b""
    try:
        for raw in sources.read_lines(entry["path"], zstd):
            if not raw.endswith(b"\n"):
                tail = raw
                break
            digest.update(raw)
            line += 1
            if count is not None and line == count:
                prefix_seen = digest.hexdigest()
            try:
                record = json.loads(raw)
            except (ValueError, RecursionError):
                undecodable.append((line, "not_json"))
                continue
            if isinstance(record, dict):
                read.append((line, record))
            else:
                undecodable.append((line, "not_object"))
    except sources.Unreadable as exc:
        raise Unacquired(f"{UNKNOWN_REASONS['unreadable']} ({acquisition_reason(exc)})") from exc
    digest.update(tail)
    sha = digest.hexdigest()
    if whole_sha is not None and sha == whole_sha:
        return {"records": read, "undecodable": undecodable, "lines": line, "which": "the bytes the census read",
                "read": "bound", "binding": ["whole", whole_sha]}
    if prefix is not None and prefix_seen == prefix[0]:
        return {"records": [(n, record) for n, record in read if n <= count],
                "undecodable": [(n, category) for n, category in undecodable if n <= count],
                "lines": count,
                "which": "the census record's complete lines" + (", the host having appended since"
                                                                 if whole_sha is not None else ""),
                "read": "appended" if whole_sha is not None else "bound",
                "binding": ["prefix", prefix[0], count]}
    on_record = whole_sha if whole_sha is not None else prefix[0]
    raise Unacquired(f"{UNKNOWN_REASONS['changed']} ({sha[:12]} now, {on_record[:12]} on record)")


EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


def _instant(value):
    """A record's or a pin's time as an AWARE instant in UTC, or None (#5).

    Two shapes are real: an ISO string carrying `Z` or an offset, which both hosts write, and an
    epoch number in seconds, which a pin's `created` is (`compose/instructions_session.py` writes
    `time.time()`). A string with no zone is UNSUPPORTED rather than read as UTC the way
    `census.parse` reads it: its zone is not recorded, inside one transcript the record's line already
    decides the order, and the one thing a guessed zone would buy is the order of two transcripts —
    which is exactly where a wrong guess hands one session's answer to another. Anything else is
    None too, and no shape raises: a naive instant beside an aware one used to raise `TypeError` in
    the comparisons and take the whole run with it."""
    if isinstance(value, datetime.datetime):
        return value.astimezone(datetime.timezone.utc) if value.tzinfo else None
    if type(value) in (int, float):
        if not math.isfinite(value):
            return None
        try:
            return datetime.datetime.fromtimestamp(value, tz=datetime.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    try:
        when = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when.astimezone(datetime.timezone.utc) if when.tzinfo else None


def _timestamp(record):
    """The time a record carries, in the shape it carries it — a string or a number, never a bool."""
    for key in ("timestamp", "ts", "time"):
        value = record.get(key)
        if isinstance(value, str) or type(value) in (int, float):
            return value
    payload = record.get("payload")
    if isinstance(payload, dict):
        value = payload.get("timestamp")
        if isinstance(value, str) or type(value) in (int, float):
            return value
    return None


LOCATED_HOW = {"field": "the field is the delivered body",
               "exact": "the delivered body inside the field",
               "normalised": "the delivered body inside the field, line endings normalised",
               "unmapped": "the delivered body inside the field, line endings normalised, its offsets unrecovered"}


def _located(record, delivered, damage=None, line=None):
    """`(where, how, matches)` the delivered body sits in this record, or None.

    Located by the pin's snapshot text and its hash: the host's field is a LARGER string that holds
    the body (measured 2026-10-23: 23 of 23 recorded sessions, none of them field-exact), so an
    equality test over the field would answer "absent" about a body that is there.

    Two sources are admitted, each by its own discriminator (M3): an ATTACHMENT record's
    `attachment.systemPrompt[]` — the same test views.py uses for an attachment — and a request-shape
    record's `shape.system[].text`. A `systemPrompt` on any other record type is a lookalike, not a
    delivery. A field of either source that is not the shape it should be is counted in `damage` by a
    fixed category and the record's line, never by its content, and never raises (M2).

    Every place the body sits is a MATCH (step 0 S-13, M1): the field's JSON pointer, the half-open span
    in the field's decoded text in code points, and the exact bytes there — the RECORDED version, which
    a normalised match does not share with the selected one (`_field_matches`). `where` and `how` are
    the first match's."""
    if not delivered:
        return None
    places = []

    def harmed(category, ordinal=None):
        if damage is not None:
            damage.append({"line": line, "category": category, **({} if ordinal is None else {"ordinal": ordinal})})

    if record.get("type") == "attachment" and isinstance(record.get("attachment"), dict) \
            and "systemPrompt" in record["attachment"]:
        prompts = record["attachment"]["systemPrompt"]
        if not isinstance(prompts, list):
            harmed("locator_unusable")
        else:
            for ordinal, text in enumerate(prompts):
                if isinstance(text, str):
                    places.append(("attachment.systemPrompt[]", f"/attachment/systemPrompt/{ordinal}", text))
                else:
                    harmed("locator_element_rejected", ordinal)
    if isinstance(record.get("shape"), dict) and "system" in record["shape"]:
        blocks = record["shape"]["system"]
        if not isinstance(blocks, list):
            harmed("locator_unusable")
        else:
            for ordinal, block in enumerate(blocks):
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    places.append(("shape.system[].text", f"/shape/system/{ordinal}/text", block["text"]))
                else:
                    harmed("locator_element_rejected", ordinal)
    matches = [{"where": where, **match} for where, pointer, text in places
               for match in _field_matches(text, delivered, pointer)]
    if not matches:
        return None
    return matches[0]["where"], LOCATED_HOW[matches[0]["method"]], matches


def _field_matches(text, delivered, pointer):
    """Every place `delivered` sits in one field, each `{pointer, ordinal, method, start, end, recorded}`.

    The field itself, else every exact occurrence, else every normalised one (#14): found in the
    normalised field, mapped back through `_normalised_index` to the field's own offsets, and kept only
    when the bytes there normalise to the body again. One that does not is `unmapped`, with no span and
    no recorded bytes: a span that might be wrong is never published as the recorded version."""
    if text == delivered:
        return [{"pointer": pointer, "ordinal": 0, "method": "field", "start": 0, "end": len(text), "recorded": text}]
    found, at = [], text.find(delivered)
    while at >= 0:
        found.append({"pointer": pointer, "ordinal": len(found), "method": "exact", "start": at,
                      "end": at + len(delivered), "recorded": delivered})
        at = text.find(delivered, at + len(delivered))
    body = _normalised(delivered)
    if found or not body:
        return found
    normal, offsets = _normalised_index(text)
    at = normal.find(body)
    while at >= 0:
        start, end = offsets[at], offsets[at + len(body) - 1] + 1
        recorded = text[start:end]
        if _normalised(recorded) == body:
            found.append({"pointer": pointer, "ordinal": len(found), "method": "normalised", "start": start,
                          "end": end, "recorded": recorded})
        else:
            found.append({"pointer": pointer, "ordinal": len(found), "method": "unmapped", "start": None,
                          "end": None, "recorded": None})
        at = normal.find(body, at + len(body))
    return found


def _normalised(text):
    """Line endings and trailing whitespace only: the normalisation the match check measured."""
    return "\n".join(line.rstrip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()


def _normalised_index(text):
    """`(normalised, offsets)`: `_normalised(text)` built character by character, each kept character
    with its offset in `text`, so a match in the normalised text maps back to the field (#14). A line
    break stands at the offset of the `\r` or `\n` that made it."""
    kept, offsets, line = [], [], []

    def close(newline_at):
        while line and line[-1][0].isspace():
            line.pop()
        for char, at in line:
            kept.append(char)
            offsets.append(at)
        line.clear()
        if newline_at is not None:
            kept.append("\n")
            offsets.append(newline_at)

    at = 0
    while at < len(text):
        char = text[at]
        if char == "\r":
            close(at)
            at += 2 if text[at + 1:at + 2] == "\n" else 1
        elif char == "\n":
            close(at)
            at += 1
        else:
            line.append((char, at))
            at += 1
    close(None)
    start, end = 0, len(kept)
    while start < end and kept[start].isspace():
        start += 1
    while end > start and kept[end - 1].isspace():
        end -= 1
    return "".join(kept[start:end]), offsets[start:end]


# The member `type`s an `instructions` attachment admits, each the native layer the host itself
# distinguishes. A member of any other type is REJECTED and counted, never given layer None: a None
# layer dropped it from every layer at once, and the event read complete (M2, Fable M-b).
ADMITTED_MEMBER_TYPES = frozenset(ATTACHMENT_LAYER)


def member_problem(member):
    """The fixed category one `files[]` member is rejected under, or None when it is usable. The
    member's own values are never part of the answer: a type string is host text (r5 F0)."""
    if not isinstance(member, dict):
        return "member_not_object"
    kind = member.get("type")
    if not (isinstance(kind, str) and kind in ADMITTED_MEMBER_TYPES):
        return "member_type_unmapped"
    if not isinstance(member.get("path"), str):
        return "member_path_invalid"
    if not isinstance(member.get("content"), str):
        return "member_content_invalid"
    return None


def owner_ref(host, session_id, agent=None):
    """The opaque owner reference every cross-document join uses (step 0 S-4): the RAW host, session
    and agent. A display name is projected metadata, and two raw owners can project to one string."""
    return opaque_id("o", "owner", host, session_id, agent)


def session_ref(host, session_id):
    """The opaque session reference (step 0 S-14), from the raw host and session id."""
    return opaque_id("p", "session", host, session_id)


def record_owner(entry, record):
    """Who one Claude record belongs to: `{session, transcript, owner_ref, agent_id_unusable}`.

    lineage.py 102-105: inline sidechain records occur INSIDE ordinary main files, and such a file is
    not thereby a child. By the census's own test (lineage.py 76-77), a record of a main row is a
    sidechain's when `isSidechain is True` or its `agentId` is a NON-EMPTY string; it then never
    answers for the main session and never feeds `current` (Fable M-a). An `agentId` that is there but
    empty, null or not a string, beside no `isSidechain`, leaves the record the main session's and is
    counted (`agent_id_unusable`): a main injection that left `current` over a null field would be the
    silent wrong answer. A sidechain record with no usable agent has NO owner (`owner_ref` None,
    `ownership_unknown`): joining such records under one invented name merged children that may be
    different ones. In a subagent row every record is the row's own."""
    host, ident = entry.get("host"), entry.get("id")
    session = f"{host}:{ident}"
    if entry.get("kind") != "main":
        return {"session": session, "transcript": entry.get("kind"), "owner_ref": owner_ref(host, ident),
                "agent_id_unusable": False}
    agent = record.get("agentId")
    usable = isinstance(agent, str) and agent != ""
    if usable:
        # the display is projected metadata when it is published; `owner_ref` is the join
        return {"session": f"{session}#sidechain:{agent}", "transcript": "subagent",
                "owner_ref": owner_ref(host, ident, agent), "agent_id_unusable": False}
    if record.get("isSidechain") is True:
        return {"session": f"{session}#sidechain:unidentified", "transcript": "subagent", "owner_ref": None,
                "agent_id_unusable": False}
    return {"session": session, "transcript": "main", "owner_ref": owner_ref(host, ident),
            "agent_id_unusable": "agentId" in record}


def injection_events(records, entry, delivered=None, seen=None):
    """`(events, damage, inherited)`: the injection events one transcript records, in line order (the
    1548 amendment §1), the injection records it could not use, and the records that carry another
    session's start (M10).

    An event is per INJECTION, not per session: the same session is injected again after a compaction
    and the second body is not always the first (measured 2026-10-23: 22 of 84 recorded file entries
    differed from the first). A layer the host does not distinguish stays one carrier — Codex records
    `base_instructions` as one merged block, so no global/project split is derived from it.

    Each source is admitted by its own discriminator (M3): a Claude `instructions` attachment only on a
    record of type `attachment` whose `attachment` is an object, as views.py reads one; the Codex
    block only on a `session_meta` record whose payload is an object, as lineage.py does. Damage is
    told apart by level (M2): a rejected MEMBER is counted on its event, which keeps the members it
    could use; an unusable CONTAINER is a `damage` row at its line, with no event. Every category is a
    fixed word and every location a number — host text, the type string included, is never echoed.

    A Codex rollout's own block is the `session_meta` whose `payload.id` is the rollout's own id, the
    census row's (M10). A subagent or fork rollout also carries its parent's `session_meta`, with the
    parent's id and the same block text (measured 2026-10-28: 333 of 1,334 rollouts): that record is
    not an injection into this session. It is an `inherited` row — `another_session_id`, or
    `no_session_id` when the payload names none — and never an event.

    An unusable container is ALSO an event, `damaged` with its category and no members (step 0 S-5):
    it is a later injection whose content nobody can read, so it ends the previous event's interval
    instead of vanishing. `seen`, when given, collects what the per-session record counts: the lines
    of the rollout's own `session_meta` records and of each unusable `agentId`."""
    host, events, damage, inherited = entry.get("host"), [], [], []
    seen = {} if seen is None else seen
    seen.setdefault("own_meta", [])
    seen.setdefault("agent_id_unusable", [])
    for line, record in records:
        at = _timestamp(record)
        if host == "claude":
            owner = record_owner(entry, record)
            session, transcript = owner["session"], owner["transcript"]
            if owner["agent_id_unusable"]:
                seen["agent_id_unusable"].append(line)
            mine = {"session": session, "transcript": transcript, "owner_ref": owner["owner_ref"]}
            attachment = record.get("attachment")
            if record.get("type") == "attachment" and isinstance(attachment, dict) \
                    and attachment.get("type") == "instructions":
                files = attachment.get("files")
                case, cwd = cwd_case(record)
                if not isinstance(files, list):
                    damage.append({"line": line, "category": "container_unusable"})
                    events.append({"kind": "native", "host": host, "at": at, "n": line, "files": [],
                                   "rejected": [], "unmapped": False,
                                   "damaged": reason("container_unusable"), **mine,
                                   "scope": cwd, "cwd_case": case, "where": "attachment.files[] by type"})
                else:
                    members, rejected = [], []
                    for ordinal, member in enumerate(files):
                        problem = member_problem(member)
                        if problem:
                            row = {"ordinal": ordinal, "category": problem}
                            if problem in ("member_path_invalid", "member_content_invalid"):
                                # A known type: the layer is identifiable, so it is incomplete rather
                                # than unknown (S-6), and an AutoMem member with a path keeps its
                                # directory, which is the scope it leaves incomplete.
                                row["layer"] = ATTACHMENT_LAYER[member["type"]]
                                if problem == "member_content_invalid":
                                    row["path"] = member["path"]
                            rejected.append(row)
                            continue
                        members.append({"layer": ATTACHMENT_LAYER[member["type"]], "type": member["type"],
                                        "path": member["path"], "text": member["content"], "ordinal": ordinal,
                                        "pointer": f"/attachment/files/{ordinal}/content"})
                    members, duplicates = distinct_members(host, case, cwd, members)
                    # A valid `files: []` is kept: it is an empty answer, a deletion that shows (#6, S-8).
                    events.append({"kind": "native", "host": host, "at": at, "n": line, "files": members,
                                   "duplicates": duplicates, "rejected": rejected,
                                   "unmapped": any(row["category"] in UNMAPPED_CATEGORIES for row in rejected),
                                   "damaged": None, **mine,
                                   "scope": cwd, "cwd_case": case, "where": "attachment.files[] by type"})
            before = len(damage)
            found = _located(record, delivered, damage, line)
            harmed = [row["category"] for row in damage[before:]]
            if found:
                events.append({"kind": "session_injection", "host": host, "at": at, "n": line, **mine,
                               "where": found[0], "how": found[1], "matches": found[2], "damaged": None})
            elif harmed:
                # The locator could not be read, or an element it holds was rejected and the body is not
                # among the rest: the injection at this line is unknown, not absent (step 0 S-6).
                events.append({"kind": "session_injection", "host": host, "at": at, "n": line, **mine,
                               "where": None, "how": None,
                               "damaged": reason("container_unusable") if "locator_unusable" in harmed
                               else reason("locator_element_rejected")})
        elif host == "codex":
            payload = record.get("payload")
            if record.get("type") != "session_meta" or not isinstance(payload, dict):
                continue
            if not isinstance(payload.get("id"), str) or payload["id"] != entry.get("id"):
                inherited.append({"line": line, "category": "another_session_id" if isinstance(payload.get("id"), str)
                                  else "no_session_id"})
                continue
            seen["own_meta"].append(line)
            if payload.get("base_instructions") is None:
                continue
            mine = {"session": f"{host}:{entry.get('id')}", "transcript": entry.get("kind"),
                    "owner_ref": owner_ref(host, entry.get("id"))}
            base = payload["base_instructions"]
            text = base if isinstance(base, str) else base.get("text") if isinstance(base, dict) else None
            case, cwd = cwd_case(payload)
            if not isinstance(text, str):
                damage.append({"line": line, "category": "container_unusable"})
                events.append({"kind": "native", "host": host, "at": at, "n": line, "rejected": [],
                               "unmapped": False, "damaged": reason("container_unusable"),
                               **mine, "files": [], "scope": cwd, "cwd_case": case,
                               "where": "session_meta.payload.base_instructions",
                               "git": git_of(payload)})
                continue
            events.append({"kind": "native", "host": host, "at": at, "n": line, "rejected": [],
                           "unmapped": False, "damaged": None, **mine, "scope": cwd, "cwd_case": case,
                           "where": "session_meta.payload.base_instructions",
                           "git": git_of(payload),
                           # One undivided block at its own layer value (#14, S-19): the global and
                           # project parts of it are unknown, and no estimated split is recorded (the
                           # 1548 amendment §1). An empty block is kept: an empty answer (#6).
                           "files": [{"layer": "native_undivided", "type": "base_instructions",
                                      "path": "codex:base_instructions", "text": text, "undivided": True,
                                      "ordinal": 0, "pointer": "/payload/base_instructions"
                                      + ("" if isinstance(base, str) else "/text"),
                                      "carrier_id": native_carrier_id(host, case, cwd, {"undivided": True})}]
                           if text.strip() else []})
    return events, damage, inherited


def event_at_instant(events, when, owner_ref, kind="native"):
    """The event in force for an INSTANT alone (step 0 S-5): auxiliary, because a turn from views always
    has a line, and its line finds its segment (S-17).

    Over one owner's events of one kind in line order, only the longest prefix whose instants are all
    supported and non-decreasing can bracket an instant. The answer is the last event of that prefix at
    or before `when`. Where an event past the prefix could still be the one in force — `when` at or after
    the prefix's last instant, or before its first, while events remain beyond it — the answer is
    `uncertain`, naming the line that broke the prefix, never the prefix's last event (the lower bound).
    An unsupported `when` has no event (`none`); one before every event of a fully ordered list is
    `no_event_yet`. A chosen event past its own certainty cut is `uncertain` by that cut's reason and line
    (lead ruling R13): an instant cannot be held against a line. The answer is `{state, event_ref, reason,
    line}`; it is not published."""
    moment = _instant(when)
    if moment is None:
        return {"state": "none", "event_ref": None, "reason": None, "line": None}
    own = sorted((event for event in events if event.get("owner_ref") == owner_ref and event["kind"] == kind),
                 key=lambda event: event["n"])
    prefix = []
    for event in own:
        at = _instant(event.get("at"))
        if at is None or (prefix and at < _instant(prefix[-1].get("at"))):
            break
        prefix.append(event)
    breaker = own[len(prefix)] if len(prefix) < len(own) else None
    unbracketed = {"state": "uncertain", "event_ref": None, "line": breaker["n"] if breaker else None,
                   "reason": breaker.get("at_reason") if breaker else None}
    chosen = None
    for event in prefix:
        if _instant(event.get("at")) > moment:
            break
        chosen = event
    if chosen is None:
        return unbracketed if breaker else {"state": "no_event_yet", "event_ref": None,
                                            "reason": reason("no_event_yet"), "line": None}
    if breaker is not None and chosen is prefix[-1]:
        return unbracketed
    interval = chosen.get("interval") or [chosen["n"], None]
    cut = chosen.get("certain_to")
    if cut is not None and interval[0] < cut and (interval[1] is None or cut < interval[1]):
        return {"state": "uncertain", "event_ref": chosen["id"], "reason": chosen.get("uncertain_reason"), "line": cut}
    return {"state": "in_force", "event_ref": chosen["id"], "reason": None, "line": None}


# ---- §8's current reference point, scope by scope (step 0 S-7 .. S-10, S-19)
# A scope is a (layer, host, key) the host itself distinguishes: the global layer per host, a project
# per recorded cwd, a memory directory per AutoMem path, and the Codex block per (codex, cwd). Each is
# answered by its own newest eligible outcome, never per path, and each answer is a published row.
SCOPED_LAYERS = ("native_global", "native_project", "native_memory", "native_undivided")
SCOPE_STATUSES = ("answered", "empty", "incomplete", "uncertain", "unknown")
SCOPE_RANK = {"unknown": 1, "uncertain": 2, "incomplete": 3, "answered": 4, "empty": 4}
# What each reason does to a scope (S-10's table): the rank-1 reasons make it unknown, the rank-2 ones
# uncertain, a known-layer rejected member incomplete. One condition, one status, wherever it appears.
REASON_STATUS = {
    **{key: "unknown" for key in ("container_unusable", "member_unmapped", "cwd_unreadable", "undated",
                                  "undated_naive", "tie", "memory_unconfirmed", "locator_element_rejected",
                                  "exclusion_unreadable", "codex_undivided")},
    **{key: "uncertain" for key in ("undecodable_after", "undecodable_elsewhere")},
    "member_rejected": "incomplete",
}
# The layers each count leaves incomplete at its host (S-10: complete only without them). The global
# layer is not among them: an event with no cwd still answers it (S-7), and an unreadable cwd reaches
# it through its scope status. Memory is: S-9 asks whether a later event is at a directory's project,
# and an event without a readable cwd cannot answer that (lead ruling, 2026-10-29).
COUNTED_LAYERS = {"no_scope": ("native_project", "native_undivided", "native_memory"),
                  "cwd_unreadable": ("native_project", "native_undivided", "native_memory"),
                  "memory_path_relative": ("native_memory",)}
UNMAPPED_CATEGORIES = ("member_type_unmapped", "member_not_object")
ABSOLUTE = re.compile(r"^(/|[A-Za-z]:[\\/]|\\\\)")
PROJECT_SEGMENT = re.compile(r"[\\/]projects[\\/]([^\\/]+)(?:[\\/]|$)")


def cwd_case(holder):
    r"""`(case, cwd)` of one record's cwd, read as DATA and never resolved on disk (S-7): `absent` when
    the key is not there, `unreadable` when it is not a string naming an absolute path by its spelling
    (POSIX `/`, a drive `X:\` or `X:/`, a UNC `\\`), `scoped` with the string otherwise."""
    if not isinstance(holder, dict) or "cwd" not in holder:
        return "absent", None
    value = holder["cwd"]
    if isinstance(value, str) and ABSOLUTE.match(value):
        return "scoped", value
    return "unreadable", None


def lexical_slug(text):
    """`memory_slug`'s character rule on the recorded string itself: nothing expanded or resolved (S-9)."""
    return re.sub(r"[^A-Za-z0-9]", "-", text)


def member_dir(path):
    """The directory of a recorded AutoMem path, by its spelling, or None when the path is not absolute."""
    if not (isinstance(path, str) and ABSOLUTE.match(path)):
        return None
    cut = max(path.rfind("/"), path.rfind("\\"))
    return path[:cut] or path[:1]


def brackets(read):
    """For one read transcript, `bracket(line)` = `(after, ok)`: the first supported instant of a
    record LATER than that line, and whether the transcript's supported instants do not step back
    across it (S-5's bracketing). The upper bound of an undated outcome, or of a line that does not
    decode, is only ever that later record of its own transcript."""
    supported = [(n, at) for n, record in read["records"] for at in [_instant(_timestamp(record))] if at is not None]
    lines = [n for n, _at in supported]

    def bracket(line):
        later = bisect.bisect_right(lines, line)
        earlier = bisect.bisect_left(lines, line) - 1
        after = supported[later][1] if later < len(supported) else None
        before = supported[earlier][1] if earlier >= 0 else None
        return after, after is None or before is None or before <= after
    return bracket


def could_follow(other, chosen):
    """Whether `other` may come after `chosen` by S-8's order: by line inside one transcript, by
    instant across two, and an undated one by its upper bound only (an equal instant may follow)."""
    if other["session_ref"] == chosen["session_ref"]:
        return other["n"] > chosen["n"]
    chosen_at, other_at = _instant(chosen.get("at")), _instant(other.get("at"))
    if chosen_at is None:
        return True
    if other_at is not None:
        return other_at >= chosen_at
    upper = other.get("after_at") if other.get("bracket_ok") else None
    return upper is None or upper > chosen_at


def scope_id(layer, host, key):
    """The opaque scope id (S-7, S-11), from the RAW layer, host and key: two raw scopes that project
    to one display string stay two scopes."""
    return opaque_id("s", "scope", layer, host, key)


COMMIT_HASH = re.compile(r"^[0-9a-f]{7,64}$")


def without_userinfo(url):
    """A repository URL with whatever stands before `@` in its authority removed — a user, a token, a
    password — for `scheme://` URLs and scp-like `user@host:path` alike, before the floor sees it."""
    scheme, sep, rest = url.partition("://")
    if sep:
        authority, slash, path = rest.partition("/")
        return f"{scheme}://{authority.rpartition('@')[2]}{slash}{path}"
    head, colon, tail = url.partition(":")
    return head.rpartition("@")[2] + colon + tail if colon and "@" in head else url


def git_of(payload):
    """`payload.git` as provenance (step 0 S-19), or None: the commit hash only when it is one, the
    branch, and the repository URL without its userinfo. What the floor still finds in them is its."""
    git = payload.get("git")
    if not isinstance(git, dict):
        return None
    commit, branch, url = git.get("commit_hash"), git.get("branch"), git.get("repository_url")
    return {"commit_hash": commit if isinstance(commit, str) and COMMIT_HASH.match(commit) else None,
            "branch": branch if isinstance(branch, str) and branch else None,
            "repository_url": without_userinfo(url) if isinstance(url, str) and url else None}


def injection_carrier_id(host, content_ref):
    """A session injection's `c-` (step 0 S-11): its host and the snapshot it was compiled into."""
    return opaque_id("c", "session_injection", host, content_ref)


def event_occurrences(event, injection_id=None):
    """Every recorded occurrence one event holds (step 0 S-12, S-13): one per member at its pointer —
    a duplicate's copy included, since its bytes were at that pointer too — and one per place the
    selected body was found, under the session's own injection carrier `injection_id`, whose version
    is the RECORDED bytes there. `recorded`, `kind` and `host`
    stay internal: the store reads them, the occurrence row does not carry them."""
    rows = []

    def add(ordinal, pointer, carrier_id, version, start, end, method, **internal):
        rows.append({"occurrence_id": opaque_id("q", "occurrence", event["id"], ordinal, pointer),
                     "event_id": event["id"], "ordinal": ordinal, "pointer": pointer, "carrier_id": carrier_id,
                     "version_sha256": version, "start": start, "end": end, "sha256": version, "method": method,
                     "reason": "recorded_unmapped" if method == "unmapped" else None,
                     "kind": event["kind"], "host": event["host"], **internal})

    if event["kind"] == "native":
        for member in event.get("files") or []:
            add(member.get("ordinal", 0), member["pointer"], member["carrier_id"], sha256_text(member["text"]),
                0, len(member["text"]), "field", **({"git": event["git"]} if event.get("git") else {}))
        for row in event.get("duplicates") or []:
            add(row["ordinal"], row["pointer"], row["carrier_id"], row["version_sha256"], 0, row["length"], "field")
        return rows
    for match in event.get("matches") or []:
        recorded = match.get("recorded")
        add(match["ordinal"], match["pointer"], injection_id,
            sha256_text(recorded) if recorded is not None else None, match.get("start"), match.get("end"),
            match["method"], recorded=recorded)
    return rows


def native_carrier_id(host, case, cwd, member):
    """A transcript carrier's `c-` (step 0 S-11), from the raw values it was recorded under.

    A Claude member is `["native", layer, host, type, recorded path]`, and a path that is not absolute
    takes the event's project scope as well, so two projects' `./CLAUDE.md` stay two carriers; with no
    usable cwd that component is `null`. The Codex block is `["native_undivided", "codex", its scope]`,
    the scope `null` when the record has no usable cwd: the event keeps its carrier, and is simply no
    `current` outcome."""
    if member.get("undivided"):
        return opaque_id("c", "native_undivided", "codex",
                         scope_id("native_undivided", "codex", cwd) if case == "scoped" else None)
    parts = ["native", member["layer"], host, member["type"], member["path"]]
    if not ABSOLUTE.match(member["path"]):
        parts.append(scope_id("native_project", host, cwd) if case == "scoped" else None)
    return opaque_id("c", *parts)


def distinct_members(host, case, cwd, members):
    """`(members, duplicates)`: one member per carrier VERSION (step 0 S-12, final). A recorded path
    named twice with equal bytes is one version, as `r-` has one copy per version; each dropped copy
    is a duplicate by its ordinal. Two byte strings at one path stay two versions."""
    kept, duplicates, seen = [], [], set()
    for member in members:
        member["carrier_id"] = native_carrier_id(host, case, cwd, member)
        key = (member["carrier_id"], sha256_text(member["text"]))
        if key in seen:
            duplicates.append({"ordinal": member["ordinal"], "pointer": member.get("pointer"),
                               "carrier_id": key[0], "version_sha256": key[1], "length": len(member["text"])})
            continue
        seen.add(key)
        kept.append(member)
    return kept, duplicates


def pin_state(pinned):
    """What a session's own pin says about the global instructions (S-8 b, S-25): `unpinned` when no
    pin is recorded, `included` or `excluded` by the flag the pin records, and `unreadable` when the
    census names a pin this run could not read as the session's own — absent, failed, another
    session's or another snapshot's — or one whose flag is not a boolean. Every pinned session's pin is
    read (`session_pin`); its snapshot is not consulted, because the flag is the pin's."""
    if pinned["status"] == "unpinned":
        return "unpinned"
    if pinned["status"] != "read" or pinned["include"] is None:
        return "unreadable"
    return "included" if pinned["include"] else "excluded"


def outcomes_of(event, pin):
    """`(outcomes, counts)`: every scope one ELIGIBLE event answers, each with the members it carries
    there and the state that may keep it from answering, and the per-host counts of what it cannot
    answer at all (S-7, S-8 b, S-9, S-19)."""
    host, case, cwd = event["host"], event.get("cwd_case"), event.get("scope")
    outcomes, counts = [], []
    if case == "unreadable" and host == "codex":
        return outcomes, [reason("cwd_unreadable")]
    state = event.get("damaged") or (reason("member_unmapped") if event.get("unmapped") else None)

    def answer(layer, key, members, own_state=None, incomplete=False, limitations=()):
        outcomes.append({"layer": layer, "host": host, "key": key, "members": members,
                         "state": own_state or state, "incomplete": incomplete,
                         "limitations": list(limitations), "event": event})

    rejected = event.get("rejected") or []
    if host == "codex":
        answer("native_global", None, [], reason("codex_undivided"))
        if case == "absent":
            return outcomes, [reason("no_scope")]
        for layer in ("native_project", "native_memory"):
            answer(layer, cwd, [], reason("codex_undivided"))
        answer("native_undivided", cwd, [member for member in event["files"] if member["layer"] == "native_undivided"])
        return outcomes, counts
    if case == "unreadable":
        # No global and no project answer (S-7); its memory directories come from their own recorded
        # paths, never from the cwd, so it still answers them (S-9, lead ruling 2026-10-29).
        counts.append(reason("cwd_unreadable"))
    elif pin == "excluded":
        counts.append(reason("global_excluded_by_launch"))
    else:
        answer("native_global", None, [member for member in event["files"] if member["layer"] == "native_global"],
               reason("exclusion_unreadable") if pin == "unreadable" else None,
               any(row.get("layer") == "native_global" for row in rejected),
               [reason("exclusion_unobservable")] if pin == "unpinned" else ())
    if case == "absent":
        counts.append(reason("no_scope"))
    elif case == "scoped":
        answer("native_project", cwd, [member for member in event["files"] if member["layer"] == "native_project"],
               incomplete=any(row.get("layer") == "native_project" for row in rejected))
    if state is None:
        directories = {}
        for member in event["files"]:
            if member["layer"] != "native_memory":
                continue
            directory = member_dir(member["path"])
            if directory is None:
                counts.append(reason("memory_path_relative"))
                continue
            directories.setdefault(directory, []).append(member)
        # A member whose content is unusable still names its directory: that scope is answered,
        # incomplete, even when no usable member of it is left (S-6).
        broken = {member_dir(row.get("path")) for row in rejected
                  if row.get("layer") == "native_memory" and row.get("path") is not None} - {None}
        for directory in sorted(broken - set(directories)):
            directories[directory] = []
        for directory, members in directories.items():
            answer("native_memory", directory, members, incomplete=directory in broken)
    return outcomes, counts


def memory_membership(event):
    """What a LATER event says about memory directories (S-9): None when its AutoMem membership is
    known, else the reason it is not — an unmapped member, an unusable container, or an AutoMem member
    with no usable path, which leaves the directory incomplete rather than unknown."""
    if event.get("damaged"):
        return reason("container_unusable")
    if event.get("unmapped"):
        return reason("member_unmapped")
    if any(row.get("layer") == "native_memory" and row["category"] == "member_path_invalid"
           for row in event.get("rejected") or []):
        return reason("member_rejected")
    return None


def same_project(directory, chosen, other):
    """S-9's test, the host's own: the recorded cwd, under `memory_slug`'s rule without resolving it,
    equals the `projects/<slug>/` segment of the directory's recorded path. Plain cwd equality only
    where the path has no such segment; two missing cwds are never one project."""
    if other.get("cwd_case") != "scoped":
        return False
    segment = PROJECT_SEGMENT.search(directory)
    if segment:
        return lexical_slug(other["scope"]) == segment.group(1)
    return chosen.get("cwd_case") == "scoped" and chosen["scope"] == other["scope"]


def signature(outcome):
    """The multiset a tie is judged on (S-8 c): each member's type, recorded path and raw sha256."""
    return sorted((member.get("type"), member.get("path"), sha256_text(member.get("text") or ""))
                  for member in outcome["members"])


def choose(candidates):
    """S-8 over one scope: `(chosen, reasons, evidence)`.

    Step 1 takes each transcript's greatest-line outcome; step 2 the latest instant across them. An
    undated head is the scope's unknown unless a competitor provably follows its upper bound; a tie
    at one instant gives one answer only when every candidate carries the same usable bytes, and a
    damaged one is never promoted by them."""
    heads = {}
    for outcome in candidates:
        held = heads.get(outcome["event"]["session_ref"])
        if held is None or outcome["event"]["n"] > held["event"]["n"]:
            heads[outcome["event"]["session_ref"]] = outcome
    dated = [outcome for outcome in heads.values() if _instant(outcome["event"].get("at")) is not None]
    latest = max((_instant(outcome["event"]["at"]) for outcome in dated), default=None)
    evidence = [{"event_id": outcome["event"]["id"], "as_of": outcome["event"].get("at")} for outcome in heads.values()]
    open_heads = [outcome for outcome in heads.values() if _instant(outcome["event"].get("at")) is None
                  and not (latest is not None and outcome["event"].get("bracket_ok")
                           and outcome["event"].get("after_at") is not None and latest > outcome["event"]["after_at"])]
    if open_heads:
        return open_heads, [{"reason": outcome["event"].get("at_reason") or reason("undated"),
                             "event_id": outcome["event"]["id"]} for outcome in open_heads], evidence
    top = [outcome for outcome in dated if _instant(outcome["event"]["at"]) == latest]
    if len({json.dumps(signature(outcome)) for outcome in top}) > 1:
        return top, [{"reason": reason("tie"), "event_id": outcome["event"]["id"]} for outcome in top], evidence
    return top, [], evidence


def scope_answer(layer, host, key, candidates, context):
    """`(row, outcome)`: one scope's published row (S-10) — its status by the strongest condition that
    applies at the chosen outcome or after it, every reason with the event or line it names, the
    evidence, and the limitations, §8's freshness sentence among them — and the outcome its carriers
    are built from, None when the scope is unknown and its sets are evidence only."""
    chosen, reasons, evidence = choose(candidates)
    first = chosen[0]["event"]
    if not reasons:
        for outcome in chosen:
            if outcome["state"]:
                reasons.append({"reason": outcome["state"], "event_id": outcome["event"]["id"]})
            if outcome["incomplete"]:
                reasons.append({"reason": reason("member_rejected"), "event_id": outcome["event"]["id"]})
        # Any line after the chosen outcome in its own transcript that does not decode may hold a
        # re-injection of this scope (S-5, S-10 rank 2); its interval alone would miss one after the
        # next event of another scope.
        for row in (context["timelines"].get(first["session_ref"]) or {}).get("undecodable", []):
            if row["line"] > first["n"]:
                reasons.append({"reason": reason("undecodable_after"), "event_id": first["id"], "line": row["line"]})
        for marker in context["unreadable_cwd"].get(host, []):
            if marker["id"] == first["id"] or not could_follow(marker, first):
                continue
            # At a memory directory only a record that names nothing under it: one that names a member
            # there is the directory's own later outcome, and answers it (lead ruling, 2026-10-29).
            if layer != "native_memory" or not any(member["layer"] == "native_memory" and member_dir(member["path"]) == key
                                                   for member in marker["files"]):
                reasons.append({"reason": reason("cwd_unreadable"), "event_id": marker["id"]})
        chosen_at = _instant(first.get("at"))
        for ref, timeline in context["timelines"].items():
            if ref == first["session_ref"] or timeline["host"] != host or timeline["kind"] != "main":
                continue
            for row in timeline["undecodable"]:
                upper = row["after_at"] if row["ok"] else None
                if (timeline["last_dated"] is None or row["line"] > timeline["last_dated"]) \
                        and (upper is None or upper > chosen_at):
                    reasons.append({"reason": reason("undecodable_elsewhere"), "session_ref": ref, "line": row["line"]})
        if layer == "native_memory" and host == "claude":
            for later in context["eligible"]:
                if later["host"] != host or later["id"] == first["id"] or not could_follow(later, first) \
                        or not same_project(key, first, later):
                    continue
                unknown = memory_membership(later)
                if unknown:
                    reasons.append({"reason": unknown, "event_id": later["id"]})
                elif not any(member["layer"] == "native_memory" and member_dir(member["path"]) == key
                             for member in later["files"]):
                    reasons.append({"reason": reason("memory_unconfirmed"), "event_id": later["id"]})
    # `cwd_unreadable` later at the host: the global scope is unknown, an earlier project answer only
    # uncertain (S-7), so the one key carries two statuses by the layer it lands on.
    statuses = ["uncertain" if row["reason"] == "cwd_unreadable" and layer != "native_global"
                else REASON_STATUS[row["reason"]] for row in reasons]
    status = min(statuses, key=SCOPE_RANK.get) if statuses \
        else ("answered" if chosen[0]["members"] else "empty")
    answered = status != "unknown"
    instant = _instant(first.get("at"))
    row = {
        "scope_id": scope_id(layer, host, key), "layer": layer, "host": host,
        "scope": key, "status": status,
        "as_of": instant.isoformat() if answered and instant else None,
        "session": first["session"] if answered else None,
        "session_ref": first["session_ref"] if answered else None,
        "line": first["n"] if answered else None,
        "event_ids": [outcome["event"]["id"] for outcome in chosen] if answered else [],
        "reasons": reasons,
        "evidence": [] if answered else [
            {"event_id": item["event_id"], "as_of": (_instant(item["as_of"]).isoformat()
                                                     if _instant(item["as_of"]) else None)} for item in evidence],
        "limitations": sorted({limit for outcome in chosen for limit in outcome["limitations"]}),
        "freshness": FRESHNESS,
    }
    return row, (chosen[0] if answered else None)


def current_scopes(events, timelines=None, pins=None):
    """§8's current reference point, scope by scope: `{scopes, universe}`.

    Only an ELIGIBLE outcome answers — an event or a damaged event of the main owner of a main row,
    with a known session (S-8); anything else is counted with its reason and never selected. Every
    scope an eligible outcome names is in the universe, and so are the per-host counts of outcomes
    that answer none (S-10)."""
    pins = pins or {}
    universe = {host: dict.fromkeys(UNIVERSE_COUNTS, 0) for host in sorted({event["host"] for event in events})}
    grouped, eligible, unreadable_cwd = {}, [], {}
    for event in events:
        if event["kind"] != "native":
            continue
        if event.get("transcript") != "main" or not event.get("session_ref"):
            universe[event["host"]]["ineligible"] += 1
            continue
        eligible.append(event)
        outcomes, counts = outcomes_of(event, pins.get(event["session_ref"], "unpinned"))
        for count in counts:
            universe[event["host"]][count] += 1
        if "cwd_unreadable" in counts:
            unreadable_cwd.setdefault(event["host"], []).append(event)
        for outcome in outcomes:
            grouped.setdefault((outcome["layer"], outcome["host"], outcome["key"]), []).append(outcome)
    context = {"timelines": timelines or {}, "unreadable_cwd": unreadable_cwd, "eligible": eligible}
    scopes, answers = [], {}
    for (layer, host, key), candidates in sorted(grouped.items(), key=lambda row: json.dumps(row[0])):
        row, outcome = scope_answer(layer, host, key, candidates, context)
        scopes.append(row)
        if outcome is not None:
            answers[row["scope_id"]] = outcome
    return {"scopes": scopes, "answers": answers,
            "universe": [{"host": host, **counts} for host, counts in universe.items()]}


def event_carriers(layer, event, reference, members=None, scope=None):
    """One event's files for one layer, as carriers, each carrying when and from whom it came, and,
    for a scope's answer, the scope and the event it is (S-10).

    A Claude member's form is what its recorded path says it is, and the Codex block is markdown: the
    form `md` this used to pass is in no splitter's vocabulary, so every transcript carrier was split
    as plain text, with no heading and no operative context under one (#13)."""
    rows = []
    for member in (event["files"] if members is None else members):
        if member["layer"] != layer:
            continue
        provenance = {"as_of": event.get("at"), "session": event.get("session"),
                      "transcript": event.get("transcript"), "where": event.get("where"),
                      "scope": masked(event.get("scope")) if event.get("scope") else None,
                      "reference": reference, "record": event.get("n")}
        if scope is not None:
            provenance.update(scope_id=scope, event_id=event.get("id"))
        if member.get("undivided"):
            # Codex delivers one merged body, so the layer's identity is unknown and only the
            # loaded text is known (§2, design §6.3's Native layer row).
            provenance["identity"] = UNKNOWN_REASONS["codex_identity"]
            if event.get("git"):
                provenance["git"] = event["git"]
        rows.append(member_carrier(event, member, provenance))
    return rows


def member_carrier(event, member, provenance=None):
    """One recorded member as a carrier, under the identity its event recorded (S-11)."""
    return carrier(member["layer"], f"{event['host']}:{member.get('type')}:{member.get('path')}",
                   member["text"], provenance=provenance,
                   form="markdown" if member.get("undivided") else form_of(member["path"]),
                   carrier_id=member.get("carrier_id") or native_carrier_id(
                       event["host"], event.get("cwd_case"), event.get("scope"), member))


def instant_reason(value):
    """Why a record's instant is not read, as a reason key, or None when it is (step 0 S-3):
    `undated_naive` for an ISO string with no zone, `undated` for anything else unread."""
    if _instant(value) is not None:
        return None
    if isinstance(value, str):
        try:
            when = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return reason("undated")
        if when.tzinfo is None:
            return reason("undated_naive")
    return reason("undated")


def ownership_map(entry, read):
    """Per transcript, the half-open line intervals each owner holds, and those whose owner is unknown
    (step 0 S-4), and each owner's display. Built from EVERY decoded record's own markers, because a
    turn is joined to its owner by its line: views publishes a turn's `line` and no `agentId`
    (views.py ~960)."""
    owner_at, displays = {}, {}
    for line, record in read["records"]:
        if entry.get("host") == "claude":
            owner = record_owner(entry, record)
            owner_at[line] = owner["owner_ref"]
            if owner["owner_ref"] is not None:
                displays.setdefault(owner["owner_ref"], owner["session"])
        else:
            owner_at[line] = owner_ref(entry.get("host"), entry.get("id"))
            displays.setdefault(owner_at[line], f"{entry.get('host')}:{entry.get('id')}")
    intervals, unknown, last = [], [], None
    for line in range(1, (read["lines"] or 0) + 1):
        owner = owner_at.get(line)          # an undecodable line is in no owner's hands
        rows = unknown if owner is None else intervals
        if last is not None and last[0] == owner and last[1]["to"] == line:
            last[1]["to"] = line + 1
            continue
        row = {"from": line, "to": line + 1} if owner is None else {"owner_ref": owner, "from": line, "to": line + 1}
        rows.append(row)
        last = (owner, row)
    return {"intervals": intervals, "unknown": unknown}, displays


def applicability(found, read):
    """Each event's interval (step 0 S-5): `[line, next)` per owner and kind, the last ending at
    `lines_read + 1`, and where its certainty ends.

    Only an undecodable line cuts certainty, for every owner, because nobody can say whose line it
    was or whether it held a re-injection. A sidechain injection with no owner has no interval of its
    own; it cuts the identified sidechains' intervals of its kind, and never the main owner's: it is a
    sidechain record, so it cannot be the main session's re-injection."""
    end_of_file = (read["lines"] or 0) + 1
    broken = sorted(line for line, _category in read["undecodable"])
    groups = {}
    for event in found:
        event.update(interval=None, certain_to=None, uncertain_reason=None)
        if event.get("owner_ref") is not None:
            groups.setdefault((event["owner_ref"], event["kind"]), []).append(event)
    for (_owner, _kind), rows in groups.items():
        rows.sort(key=lambda row: row["n"])
        for here, after in zip(rows, rows[1:] + [None]):
            here["interval"] = [here["n"], after["n"] if after else end_of_file]
            cut = next((line for line in broken if here["n"] < line < here["interval"][1]), None)
            if cut is not None:
                here.update(certain_to=cut, uncertain_reason=reason("undecodable_after"))
    for stray in (event for event in found if event.get("owner_ref") is None):
        for event in found:
            if event.get("interval") is None or event["kind"] != stray["kind"] or event["transcript"] != "subagent" \
                    or not (event["n"] < stray["n"] < event["interval"][1]):
                continue
            if event["certain_to"] is None or stray["n"] < event["certain_to"]:
                event.update(certain_to=stray["n"], uncertain_reason=reason("ownership_unknown"))
    return found


def segments(found, read, ownership, sought):
    """Each owner's segments (step 0 S-17): line intervals partitioning `[1, lines_read + 1)` of the
    transcript, cut at the owner's event lines and at its events' certainty cuts (S-5), so that the event
    in force of each kind is fixed within one.

    Per kind a segment names the event in force, or says none is recorded yet (`no_event_yet`), or that
    the one in force is past its certainty cut, by the cut's own reason and line. `sought` maps a kind
    nobody could look for to its reason (`unsought`): an injection event is found by the session's own
    snapshot body, which an unpinned session does not have (lead ruling R15), so its absence is no
    evidence. Records of an unknown owner get no segment; the ownership map holds them as unknown."""
    end_of_file = (read["lines"] or 0) + 1
    out = []
    for owner in sorted({row["owner_ref"] for row in ownership["intervals"]}):
        own = sorted((event for event in found if event.get("owner_ref") == owner), key=lambda event: event["n"])
        bounds = sorted({1, end_of_file} | {event["n"] for event in own}
                        | {event["certain_to"] for event in own if event.get("certain_to") is not None})
        for start, stop in zip(bounds, bounds[1:]):
            row = {"segment_id": opaque_id("g", "segment", owner, start), "owner_ref": owner,
                   "from": start, "to": stop, "in_force": {}}
            for kind in EVENT_KINDS:
                event = next((event for event in reversed(own) if event["kind"] == kind and event["n"] <= start), None)
                if sought.get(kind) is not None:
                    state = {"state": "unsought", "event_ref": None, "reason": sought[kind], "line": None}
                elif event is None:
                    state = {"state": "no_event_yet", "event_ref": None, "reason": reason("no_event_yet"), "line": None}
                elif event.get("certain_to") is not None and start >= event["certain_to"]:
                    state = {"state": "uncertain", "event_ref": event["id"], "reason": event["uncertain_reason"],
                             "line": event["certain_to"]}
                else:
                    state = {"state": "in_force", "event_ref": event["id"], "reason": None, "line": None}
                row["in_force"][kind] = state
            out.append(row)
    return out


def session_record(entry, read=None, found=(), damage=(), inherited=(), seen=None, failure=None, pinned=None,
                   segment_refs=()):
    """The per-session record of step 0 S-14 for one census row, as far as the transcript says it.

    Every location is a number and every reason a key: nothing a host wrote is in it except the ids,
    which pass the floor as metadata when it is published. `pinned` is the session's own pin as
    `session_pin` read it; a row given none is a pin this run did not read."""
    host, ident = entry.get("host"), entry.get("id")
    seen = seen or {}
    pinned = pinned or session_pin(None, host, ident, entry.get("pin"))
    # the binding the transcript was READ under; for one that was not read, the binding the row carries
    binding = read["binding"][0] if read is not None else "whole" if entry.get("sha256") is not None \
        else "prefix" if (entry.get("prefix_sha"), entry.get("record_count")) != (None, None) else "none"
    named = entry.get("pin") if host == "claude" and isinstance(entry.get("pin"), str) \
        and SHA256_HEX.match(entry["pin"]) else None
    record = {"session_ref": session_ref(host, ident), "session": f"{host}:{ident}", "host": host,
              "kind": entry.get("kind"),
              "transcript": {"host": host, "id": ident, "source": entry.get("source")},
              "parent_ref": session_ref(host, entry["parent"]) if entry.get("parent") else None,
              "binding": binding, "read": None, "lines_read": None,
              "owners": [], "ownership": {"intervals": [], "unknown": []},
              "inherited_session_meta": {"another_session_id": 0, "no_session_id": 0},
              "own_meta_unidentified": None, "limitations": [], "event_refs": [], "segment_refs": [],
              "unknown": [],
              # the snapshot the pin names when the pin was read (agreeing or not), else the one the
              # census row names; a Codex row's is read for nothing (S-16)
              "selection": selection_of(pinned),
              "pin": {"status": pinned["status"], "reason": pinned["reason"],
                      "content_ref": pinned["content_ref"] if isinstance(pinned["content_ref"], str)
                      and SHA256_HEX.match(pinned["content_ref"]) else named,
                      "baseline_ref": pinned.get("baseline_ref"),
                      "include_global_instructions": pinned["include"]}}
    if entry.get("alt_paths"):
        record["limitations"].append({"kind": "alt_paths", "count": entry["alt_paths"]})
    if failure is not None:
        key = reason_key(failure)
        key = key if key in READ_OUTCOMES else reason("unreadable")
        record["read"] = key
        record["unknown"].append({"reason": key})
        record["delivery"] = delivery_of(pinned, key, (), None)
        return record
    ownership, displays = ownership_map(entry, read)
    record.update(read=read["read"], lines_read=read["lines"], ownership=ownership,
                  owners=[{"owner_ref": ref, "display": name} for ref, name in sorted(displays.items())])
    for row in inherited:
        record["inherited_session_meta"][row["category"]] += 1
    metas = sorted([row["line"] for row in inherited] + list(seen.get("own_meta") or []))
    if host == "codex" and not seen.get("own_meta") and metas \
            and any(row["line"] == metas[0] and row["category"] == "no_session_id" for row in inherited):
        record["own_meta_unidentified"] = metas[0]
    record["limitations"] += [{"kind": "undecodable", "category": category, "line": line}
                              for line, category in read["undecodable"]]
    record["limitations"] += [{"kind": "member_rejected", "category": row["category"], "line": event["n"],
                               "ordinal": row["ordinal"]} for event in found for row in event.get("rejected") or []]
    record["limitations"] += [{"kind": "member_duplicate", "line": event["n"], "ordinal": row["ordinal"]}
                              for event in found for row in event.get("duplicates") or []]
    record["limitations"] += [{"kind": "damaged", "category": row["category"], "line": row["line"],
                               **({"ordinal": row["ordinal"]} if "ordinal" in row else {})} for row in damage]
    unusable = list(seen.get("agent_id_unusable") or [])
    if unusable:
        record["limitations"].append({"kind": "agent_id_unusable", "count": len(unusable), "line": unusable[0]})
    record["event_refs"] = [event["id"] for event in found]
    record["segment_refs"] = list(segment_refs)
    for event in found:
        if event.get("damaged"):
            record["unknown"].append({"reason": event["damaged"], "line": event["n"]})
        if event.get("owner_ref") is None:
            record["unknown"].append({"reason": reason("ownership_unknown"), "line": event["n"]})
    if record["own_meta_unidentified"] is not None:
        record["unknown"].append({"reason": reason("own_meta_unidentified"),
                                  "line": record["own_meta_unidentified"]})
    elif not any(not event.get("damaged") for event in found):
        record["unknown"].append({"reason": reason("no_record")})
    record["delivery"] = delivery_of(pinned, record["read"], found, owner_ref(host, ident))
    return record


def inventory_id(kind, ref):
    """A shared inventory's `i-` (step 0 S-11): `["inventory", "release"|"selection", ref]`."""
    return opaque_id("i", "inventory", kind, ref)


def selection_of(pinned):
    """A session's selection (step 0 S-14, S-15): the shared selection inventory its own verified
    snapshot is, or the one reason of the first broken link of its pin and snapshot."""
    if pinned["status"] != "read":
        return {"status": pinned["status"], "reason": pinned["reason"], "inventory_ref": None}
    if pinned.get("snapshot") is None:
        return {"status": "unknown", "reason": pinned.get("snapshot_reason") or reason("input_failed"),
                "inventory_ref": None}
    return {"status": "read", "reason": None, "inventory_ref": inventory_id("selection", pinned["content_ref"])}


def delivery_of(pinned, read, found, own):
    """A session's delivery (step 0 S-13, S-14; lead rulings on the P2.4 plan, amended 12:25):
    `confirmed` by a usable RECORDED occurrence of its own selected body that its own owner `own` holds,
    else `unknown` with ONE reason — the first broken link of the pin, its snapshot, the transcript read,
    a damaged injection event of its own owner, an occurrence of it whose offsets could not be recovered —
    and `no_record` only when no link is broken."""
    def unknown(key, refs=()):
        return {"status": "unknown", "reason": key, "event_refs": list(refs)}

    if pinned["status"] != "read":
        return unknown(pinned["reason"])
    if pinned.get("snapshot") is None:
        return unknown(pinned.get("snapshot_reason") or reason("input_failed"))
    if read in READ_FAILURES:
        return unknown(read)
    mine = [event for event in found if event["kind"] == "session_injection" and event.get("owner_ref") == own]
    confirming = [event["id"] for event in mine if not event.get("damaged")
                  and any(match["method"] != "unmapped" for match in event.get("matches") or [])]
    if confirming:
        return {"status": "confirmed", "reason": None, "event_refs": confirming}
    damaged = [event for event in mine if event.get("damaged")]
    if damaged:
        return unknown(damaged[0]["damaged"], [event["id"] for event in damaged])
    unmapped = [event["id"] for event in mine if event.get("matches")]
    if unmapped:
        return unknown(reason("recorded_unmapped"), unmapped)
    return unknown(reason("no_record"))


def transcript_events(run_dir, pins=None, zstd=None):
    """`(events, unknown, findings)`: every injection event the run's census-bound transcripts
    record, the sessions that are a named unknown, and what reading them found unusable.

    A session whose bytes moved, that has no binding, or that records no injection, is a NAMED
    unknown here rather than a silence: the reasons are what every layer status below is built from.
    Reading and decoding run inside one handler, so a transcript that cannot be processed is that
    session's unknown and every other session still processes (M2). `findings` holds each
    undecodable line, each unusable injection container, each rejected member and each inherited
    `session_meta` (M10), as a session, a line, a fixed category and an ordinal — nothing a host wrote,
    and `findings["sessions"]` the per-session records (step 0 S-14), none truncated.

    Every event gets its opaque id (step 0 S-11): its kind, the session, the census binding the
    transcript was read under, and its line. The kind is in it because one Claude record can hold both
    an instructions attachment and the selected body.

    `pins` holds each session's own pin by session reference, as `freeze_inputs` read it with its
    snapshot. The body looked for in a transcript is THAT session's own selected body, under that
    session's own injection carrier (S-1, #4); a session with no read snapshot has none to look for. A
    row `pins` does not hold is a pin this run did not read."""
    entries = census_entries(run_dir)
    events, unknown = [], []
    findings = {"undecodable": [], "damaged": [], "rejected": [], "inherited": [], "sessions": [], "timelines": {},
                "occurrences": [], "segments": []}
    for entry in entries:
        label = f"{entry.get('host')}:{entry.get('id')}"
        seen = {}
        pinned = (pins or {}).get(session_ref(entry.get("host"), entry.get("id"))) \
            or session_pin(None, entry.get("host"), entry.get("id"), entry.get("pin"))
        snapshot = pinned.get("snapshot") if pinned["status"] == "read" else None
        delivered = ((snapshot or {}).get("output") or {}).get("instruction_text") or None
        injection_id = injection_carrier_id(entry.get("host"), pinned["content_ref"]) if delivered else None
        try:
            read = transcript_records(entry, zstd)
            found, damage, inherited = injection_events(read["records"], entry, delivered, seen)
        except Unacquired as exc:
            unknown.append(f"{label}: {exc}")
            findings["sessions"].append(session_record(entry, failure=exc, pinned=pinned))
            continue
        bracket = brackets(read)
        for event in found:
            event["id"] = opaque_id("e", "event", event["kind"], entry.get("host"), entry.get("id"),
                                    read["binding"], event["n"])
            event["session_ref"] = session_ref(entry.get("host"), entry.get("id"))
            event["at_reason"] = instant_reason(event.get("at"))
            event["after_at"], event["bracket_ok"] = bracket(event["n"])
            findings["occurrences"] += event_occurrences(event, injection_id)
        applicability(found, read)
        # an injection is looked for by the session's own snapshot body; without one, by nobody (R15)
        sought = {"native": None,
                  "session_injection": None if delivered
                  else selection_of(pinned)["reason"] or reason("injection_body_empty")}
        segmented = segments(found, read, ownership_map(entry, read)[0], sought)
        for row in segmented:
            row["session_ref"] = session_ref(entry.get("host"), entry.get("id"))
        findings["segments"] += segmented
        dated = [event["n"] for event in found if _instant(event.get("at")) is not None]
        findings["timelines"][session_ref(entry.get("host"), entry.get("id"))] = {
            "host": entry.get("host"), "kind": entry.get("kind"), "last_dated": max(dated) if dated else None,
            "undecodable": [{"line": line, "after_at": after, "ok": ok}
                            for line, _category in read["undecodable"] for after, ok in [bracket(line)]]}
        findings["undecodable"] += [{"session": label, "line": line, "category": category}
                                    for line, category in read["undecodable"]]
        findings["damaged"] += [{"session": label, **row} for row in damage]
        findings["inherited"] += [{"session": label, **row} for row in inherited]
        findings["rejected"] += [{"session": event["session"], "line": event["n"], "ordinal": row["ordinal"],
                                  "category": row["category"]}
                                 for event in found for row in event.get("rejected") or []]
        findings["sessions"].append(session_record(entry, read, found, damage, inherited, seen, pinned=pinned,
                                                    segment_refs=[row["segment_id"] for row in segmented]))
        if not found:
            unknown.append(f"{label}: {UNKNOWN_REASONS['no_record']} ({read['which']})")
        events += found
    return events, unknown, findings


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
    """A pin, read as a file: the content ref it names is what the snapshot is frozen by.

    The file's OWN identity is checked against the one asked for, as `sources.read_pins` and the
    store's `read_pin` do (M6): a pin at `pins/claude/<id>.json` whose record names another host or
    session is another session's pin, and its snapshot is not this session's selection. A mismatch is
    refused by name and nothing else is substituted for it."""
    pin_path = pathlib.Path(state_root).expanduser() / "sessions" / "pins" / host / f"{session_id}.json"
    if not pin_path.is_file():
        raise Refused(f"PIN_ABSENT {masked(pin_path)}: the selection reference point needs the session's pin")
    pin = json.loads(read_source(pin_path, state_root))
    if not isinstance(pin, dict) or pin.get("host") != host or pin.get("session_id") != session_id:
        raise Refused(f"PIN_IDENTITY_MISMATCH {masked(pin_path)}: the pin names another host or session "
                      f"than the one asked for")
    if not isinstance(pin.get("content_ref"), str):
        raise Refused(f"PIN_UNREADABLE {masked(pin_path)}: the pin names no content_ref")
    return pin


def session_pin(state_root, host, session_id, census_ref, evidence=False):
    """One session's own pin, the first links of its chain (step 0 S-15, S-16, M6; lead rulings on the
    P2.4 plan): `{status, reason, content_ref, record, include, outcome, detail, code}`.

    A Codex row is `id_space` before anything is read, its census `content_ref` included: no pin is
    associated with a rollout by any means (S-16). A Claude row whose census names no pin is
    `unpinned`. Otherwise the pin is read under the session's own host and id, its record must name
    them (M6), and its `content_ref` must be the one the census row names. `evidence` is a `--pin`
    the census names no pin for: evidence about that pin only, with nothing to hold it against.
    `outcome`, `detail` and `code` are what an omission row says of a pin that was not read; a flag
    that is not a boolean leaves the pin read and its exclusion unknown (`include` None)."""
    entry = {"status": "unknown", "reason": None, "content_ref": None, "record": None, "include": None,
             "outcome": None, "detail": None, "code": None}
    if host != "claude" and not evidence:
        return {**entry, "reason": reason("id_space")}
    if census_ref is None and not evidence:
        return {**entry, "status": "unpinned", "reason": reason("unpinned")}
    if state_root is None:
        return {**entry, "reason": reason("input_unread"), "outcome": "unread", "detail": "no_root"}
    try:
        if census_ref is not None and not (isinstance(census_ref, str) and SHA256_HEX.match(census_ref)):
            raise Refused("INPUT_INVALID census content_ref: not a snapshot digest")
        record = read_pin(state_root, safe_label("pin host", host), safe_label("pin session id", session_id))
        content_ref = safe_label("snapshot content_ref", record["content_ref"])
    except (Refused, ValueError, OSError) as exc:
        code = refusal_code(exc)
        if code == "PIN_ABSENT":
            return {**entry, "reason": reason("pin_absent"), "outcome": "absent", "detail": "absent", "code": code}
        key = reason("pin_mismatch") if code == "PIN_IDENTITY_MISMATCH" else reason("input_failed")
        return {**entry, "reason": key, "outcome": "failed", "detail": acquisition_reason(exc), "code": code}
    if census_ref is not None and content_ref != census_ref:
        return disagreeing(entry, content_ref)
    flag = record.get("include_global_instructions", True)
    return {**entry, "status": "read", "content_ref": content_ref, "record": record,
            "include": flag if type(flag) is bool else None}


def disagreeing(entry, content_ref):
    """A session's own pin that its census row does not agree with (M6): read, and still not this
    session's selection. It names the snapshot the PIN names, so the disagreement is visible, and no
    baseline: what that snapshot names is not this session's release."""
    return {**entry, "status": "unknown", "reason": reason("pin_content_ref_mismatch"), "content_ref": content_ref,
            "record": None, "include": None, "snapshot": None, "baseline_ref": None, "outcome": "failed",
            "detail": "pin_content_ref_mismatch", "code": "PIN_CONTENT_REF_MISMATCH"}


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
    silently empty.

    Each producer DECLARES the inputs it reads (`INPUT_CLASSES`), and an omission answers only for
    the producers that declare its input (#16). An exception out of the acquisition used to turn every
    layer unknown, the checkout's catalog and the transcript layers among them; it now reaches only a
    producer that reads the owner's state. A producer that declares nothing is refused by name: an
    omission cannot be applied to a producer that never said what it reads."""
    rows = []
    context["reference"] = reference   # the producers answer per reference point, not per call site
    for layer, producers in LAYERS:
        producer = producers.get(reference)
        if producer is None:
            rows.append({"layer": layer, "producer": None, "status": "unknown", "carriers": [],
                         "reasons": [f"{layer} has no record at the {reference} reference point"]})
            continue
        if not (isinstance(producer, tuple) and len(producer) == 3 and isinstance(producer[2], tuple)
                and all(kind in INPUT_CLASSES for kind in producer[2])):
            raise Refused(f"PRODUCER_UNDECLARED {layer} at {reference}: a producer declares the inputs "
                          f"it reads, each one of {sorted(INPUT_CLASSES)}")
        # A reason goes in RAW. `LAYER_ROW_TABLE`'s `list_of(as_metadata())` is the one thing that
        # projects it, so a reason added here cannot reach the artifact unprojected, and no site
        # holds a second copy of the projection rule (found during S1).
        name, call, inputs = producer
        # An unpinned release, and a Codex one, reads none of the inputs its producers declare (S-24 option
        # 1, S-16): it is `release_history_deferred` whatever any of them did, no journal is read for it,
        # and the installed-now baseline is never taken for it. A Codex --pin's `id_space` is not its reason.
        if reference == "release" and layer in SHARED_RELEASE_LAYERS and context.get("release_deferred"):
            rows.append({"layer": layer, "producer": name, "status": "unknown", "carriers": [],
                         "reasons": [f"{layer}: {UNKNOWN_REASONS['release_history_deferred']}"]})
            continue
        blocked = input_reasons(inputs, context)
        if blocked:
            rows.append({"layer": layer, "producer": name, "status": "unknown", "carriers": [],
                         "reasons": [f"{layer}: {reason}" for reason in blocked]})
            continue
        if context.get("acquisition_error") and inputs:
            rows.append({"layer": layer, "producer": name, "status": "unknown", "carriers": [],
                         "reasons": [f"{layer}: {context['acquisition_error']}"]})
            continue
        try:
            carriers = call(context)
        except ScopedAnswer as exc:
            rows.append({"layer": layer, "producer": name, "status": exc.status, "carriers": exc.carriers,
                         "reasons": [f"{layer}: {text}" for text in exc.reasons]})
            continue
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
            # ...and a declared reason with a fixed category, never the exception's type and text (lead,
            # after a36c728): an exception name is not something a reader of the row can act on.
            rows.append({"layer": layer, "producer": name, "status": "incomplete", "carriers": [],
                         "reasons": [f"{layer}: {PRODUCER_FAILED} ({acquisition_reason(exc)})"]})
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
        if row["status"] != "complete" and not row["carriers"]:
            row["units"] = 0
            continue
        if not row["carriers"]:  # the producer looked and this layer has nothing: an answer, stated
            row.update(units=0, empty=True)
            continue
        # A row that is not complete and still carries carriers is a scoped layer (S-10): the scopes
        # that answered keep their units, each pointing at its scope row, and the row keeps its status.
        whole = row["status"] == "complete"
        try:
            produced = units_of(row["carriers"])
        except Unsupported as exc:
            row.update(status="unsupported" if whole else row["status"], units=0,
                       reasons=row["reasons"] + [f"{row['layer']}: {exc}"])
            continue
        except Malformed as exc:
            row.update(status="incomplete" if whole else row["status"], units=0,
                       reasons=row["reasons"] + [f"{row['layer']}: {exc}"])
            continue
        row["units"] = len(produced)
        if not produced and not whole:
            continue
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

    `current` is §8's newest recorded event per scope; a `selection` holds none, since a native layer
    is what each event recorded (`per_event`, S-15). No native file is read."""
    def produce_native(ctx):
        if layer == "native_settings":
            raise Unacquired(UNKNOWN_REASONS["settings"])
        if ctx.get("transcript_error"):
            raise Unacquired(ctx.get("transcript_error") or UNKNOWN_REASONS["census"])
        reference = ctx["reference"]
        if reference == "current":
            return scoped_layer(layer, ctx.get("current_scopes") or {"scopes": [], "answers": {}, "universe": []},
                                reference)
        if reference == "selection":
            # A selection holds what a pin selected; what a native layer delivered is per event, and
            # `sessions.json` publishes every event (S-15; lead ruling 5 on the P2.4 plan). Picking the
            # event in force at the pin's activation picked one event, which a selection never does.
            raise Unacquired(UNKNOWN_REASONS["per_event"])
        return None
    return produce_native


def scoped_layer(layer, scoped, reference):
    """A native layer at the current reference point, from its scope answers (S-10): its carriers are
    the answering scopes' members, each pointing at its scope, and the row is complete only when every
    scope answered or is empty and no count of a host leaves an outcome of this layer unscoped."""
    rows = [row for row in scoped["scopes"] if row["layer"] == layer]
    counts = [(entry["host"], key, entry[key]) for entry in scoped["universe"]
              for key, layers in COUNTED_LAYERS.items() if layer in layers and entry[key]]
    if not rows and not counts:
        if layer == "native_undivided" and any(row["host"] == "claude" for row in scoped["scopes"]):
            return []  # a Claude event carries no Codex block: complete and empty (S-19)
        raise Unacquired(f"{UNKNOWN_REASONS['no_record']}: no main transcript records {layer}")
    carriers = []
    for row in rows:
        outcome = scoped["answers"].get(row["scope_id"])
        if outcome is not None:
            carriers += event_carriers(layer, outcome["event"], reference, outcome["members"], row["scope_id"])
    worst = min((row["status"] for row in rows), key=SCOPE_RANK.get, default="answered")
    if SCOPE_RANK[worst] == SCOPE_RANK["answered"] and not counts:
        return carriers
    tally = collections.Counter(entry["reason"] for row in rows if row["status"] not in ("answered", "empty")
                                for entry in row["reasons"])
    reasons = [f"{UNKNOWN_REASONS[key]} ({n} over this layer's scope rows)" for key, n in sorted(tally.items())]
    # Each count by its name and number, so a reader sees which outcomes left the layer unscoped.
    reasons += [f"{key} {n} at {host}: {UNKNOWN_REASONS[key]}" for host, key, n in counts]
    # `uncertain` is not a layer-row status: it is `unknown` with the reason saying `uncertain:` (S-21).
    # Otherwise the row is `incomplete` — a count alone included, since the layer is identifiable and
    # its universe is not whole — and `unknown` only when no scope of it answered at all, because then
    # it has no usable carrier (S-20; lead ruling, 2026-10-29).
    answered = any(row["status"] != "unknown" for row in rows)
    status = "unknown" if not answered or SCOPE_RANK[worst] < SCOPE_RANK["incomplete"] else "incomplete"
    raise ScopedAnswer(status, reasons, carriers)


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
        return None  # a pinned snapshot that names no baseline: this reference point has no record
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
    # the host the snapshot was compiled for: the `--pin`'s, or a shared selection inventory's
    host = ctx.get("selection_host") or str(ctx.get("pin") or "").partition(":")[0] or None
    return [carrier("session_injection", f"snapshot:{snapshot['content_ref']}/output.json#instruction_text",
                    text, form="markdown",
                    carrier_id=injection_carrier_id(host, snapshot["content_ref"]))] if text else []


def _selection_overlays(ctx):
    snapshot = _selection(ctx)
    if snapshot is None:
        return None
    local = [item for item in snapshot["items"] if str(item.get("package_id", "")).startswith("@local")]
    return [row for item in local for row in item_carriers(item, "overlays")]


# layer -> reference point -> (producer name, producer, the inputs it reads). A reference point a layer
# has no producer for is `unknown` by the table itself (§6.1: historical overlays and native layers are
# unknown unless recorded), which makes that reference point incomplete. The third member is what an
# omission is applied through (#16): an input that failed, or a required one that is absent, makes
# exactly the producers that declare it unknown, and no other.
STATE_NOW = ("runtime_state", "user_state", "installed_baseline")
PINNED = ("pin", "snapshot")
# A pinned session's release is the baseline its snapshot names, so the pin and the snapshot are read
# for it too; with no pin asked for, neither is acquired, and nothing about them blocks the release.
RELEASE = PINNED + ("release_baseline",)
LAYERS = (
    ("catalog", {"current": ("checkout catalog (compose/instructions_catalog.load_catalog)", _catalog_current, ()),
                 "release": ("baseline inventory (runtime/baselines/<ref>/inventory.json)", _release_catalog,
                             RELEASE),
                 "selection": ("pinned snapshot items (sessions/snapshots/<content_ref>)", _selection_catalog, PINNED)}),
    ("adopted_packages", {"current": ("the owner's installed state, items of an adopted package", _packages_current,
                                      STATE_NOW),
                          "release": ("baseline inventory, items of an adopted package", _packages_release,
                                      RELEASE),
                          "selection": ("pinned snapshot items of an adopted package", _packages_selection, PINNED)}),
    ("overlays", {"current": ("instructions_store._effective_items over frozen copies", _overlays_current,
                              STATE_NOW + ("learning_journals",)),
                  "selection": ("pinned snapshot items of @local packages", _selection_overlays, PINNED)}),
    # The native layers are what a transcript records as delivered: §8's newest recorded event per
    # scope for `current`; a selection holds none (per event, S-15). No file is read.
    ("native_global", {"current": ("the newest recorded instructions attachment, User entry", _native("native_global"), ()),
                       "selection": ("no producer: a native layer is per event, in sessions.json",
                                     _native("native_global"), ())}),
    ("native_project", {"current": ("the newest recorded instructions attachment, Project entry", _native("native_project"), ()),
                        "selection": ("no producer: a native layer is per event, in sessions.json",
                                      _native("native_project"), ())}),
    ("native_settings", {"current": ("no producer: a settings file is carried by no transcript", _native("native_settings"), ()),
                         "selection": ("no producer: a settings file is carried by no transcript",
                                       _native("native_settings"), ())}),
    ("native_memory", {"current": ("the newest recorded instructions attachment, AutoMem entry", _native("native_memory"), ()),
                       "selection": ("no producer: a native layer is per event, in sessions.json",
                                     _native("native_memory"), ())}),
    # The Codex block, one carrier at its own layer value per (codex, cwd): Codex does not divide it,
    # so its global, project and memory parts are unknown and never estimated (#14, S-19).
    ("native_undivided", {"current": ("the newest recorded Codex base_instructions block, per cwd",
                                      _native("native_undivided"), ()),
                          "selection": ("no producer: a native layer is per event, in sessions.json",
                                        _native("native_undivided"), ())}),
    # Session-level injection exists per session, so "all layers now" can only mean the injection
    # the session being diagnosed received: with a pin, the snapshot's compiled text answers for
    # `current` too; without one there is nothing to read and the layer is `unknown`.
    ("session_injection", {"current": ("the pinned session's compiled instruction text", _selection_injection, PINNED),
                           "selection": ("the snapshot's compiled instruction text", _selection_injection, PINNED)}),
    ("ledger_incubating", {"current": ("the ledger's incubating entries (schema 1 or 2)", _ledger("ledger_incubating"), ()),
                           "selection": ("no producer: the ledger records the present", _ledger_history, ())}),
    ("ledger_keep", {"current": ("the ledger's standing keep records (schema 1 or 2)", _ledger("ledger_keep"), ()),
                     "selection": ("no producer: the ledger records the present", _ledger_history, ())}),
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
    # what reading the transcripts found unusable, and an acquisition omission row (#16, M2, M5)
    "undecodable", "damaged", "rejected", "line", "category", "ordinal", "input", "outcome", "code",
    # a parent's session_meta inside a child or fork rollout, counted and never an event (M10)
    "inherited",
    # `sessions.json` (step 0 S-14, S-5, S-11)
    "document", "session_ref", "parent_ref", "binding", "read", "lines_read", "owners", "ownership",
    "intervals", "owner_ref", "display", "from", "to", "inherited_session_meta", "another_session_id",
    "no_session_id", "own_meta_unidentified", "limitations", "count", "event_refs", "event_id", "owner",
    "at_reason", "interval_from", "interval_to", "certain_to", "uncertain_reason", "where",
    "id", "source", "transcript",
    # an owner's segments in `sessions.json` (step 0 S-17)
    "segments", "segment_refs", "segment_id", "in_force", "event_ref", "native", "session_injection",
    # `current.json`'s scope rows (step 0 S-10)
    "scopes", "scope_universe", "scope_id", "event_ids", "evidence", "freshness", "no_scope",
    "cwd_unreadable", "memory_path_relative", "global_excluded_by_launch", "ineligible",
    # `shared/store.json` (step 0 S-22) and a unit's reference into it
    "versions", "unit_refs", "unit_ref", "length", "split", "start", "end", "form", "span_unit",
    # an occurrence in `sessions.json` and a Codex block's git (step 0 S-12, S-13, S-19)
    "occurrences", "occurrence_id", "pointer", "method", "sha256", "git", "commit_hash", "branch",
    "repository_url",
    # a session's own pin and delivery, and an event's recorded members (step 0 S-14, S-15)
    "delivery", "members", "include_global_instructions", "baseline_ref", "pin_delivery",
    # a shared inventory, a session's selection of one, and the manifest's artifact list (step 0 S-22)
    "inventory_id", "unavailable", "surface", "inventory_ref", "artifacts",
    # a rename row
    "from_unit_id", "from_carrier_id", "to_carrier_id", "from_path", "to_path", "from_layer",
    "to_layer", "moved", "ambiguous", "from_carriers", "to_carriers", "reason",
)
DOCUMENT_KEYS = frozenset(DOCUMENT_MEMBERS + UNIT_FIELDS + PLAN_FIELDS + EMISSION_FIELDS
                          + PROVENANCE_FIELDS + ("block", "item_ref", "package_id", "carrier_id")
                          + tuple(layer for layer, _producers in LAYERS)
                          + tuple(REFERENCES) + tuple(STATUSES))


def emitted_document(reference, rows, ctx, more_reasons=None):
    """The document one reference point publishes, from its layer rows.

    THE production path, called by `reference_of` and by the differential control alike. It was
    composed inline inside `reference_of`, so a control could only approximate it — and a control
    that approximates the path it judges is judging a different path (r3 #0)."""
    ctx.setdefault("carriers_named", []).extend(item for row in rows for item in row.get("carriers") or [])
    units = operative_context(produce(rows))
    place = {"home": ctx.get("home"), "decisions": {}}
    reasons = [reason for row in rows for reason in row["reasons"]]
    if ctx.get("acquisition_error"):
        reasons = [ctx["acquisition_error"]] + reasons
    if ctx.get("pin_disagreement"):
        reasons = [ctx["pin_disagreement"]] + reasons
    if more_reasons is not None:
        # A reason that can only be computed from the UNITS — the baseline mapping — belongs here,
        # before the row is emitted. Appended to `document["reference"]["incomplete_reasons"]` after
        # `reference_of` returned, those strings never passed `REFERENCE_TABLE`'s rule, and a
        # mapping problem names a baseline item ref, which is a path often enough (r4 R4).
        reasons = reasons + list(more_reasons(units))
    kind = {"current": {"kind": "current", "commit": ctx.get("commit")},
            "release": {"kind": "release", "ref": ctx.get("release_ref")},
            "selection": {"kind": "selection", "content_ref": (ctx.get("snapshot") or {}).get("content_ref")}}[reference]
    document = {
        "document": reference,
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
    if reference == "current":
        scoped = ctx.get("current_scopes") or {"scopes": [], "universe": []}
        document["scopes"] = [emit_row("scope_answer", SCOPE_TABLE, row, place) for row in scoped["scopes"]]
        document["scope_universe"] = [emit_row("scope_universe", UNIVERSE_TABLE, row, place)
                                      for row in scoped["universe"]]
    return document, units


def reference_of(reference, ctx, more_reasons=None):
    """One reference point: its layers, its units, its completeness and the reasons against it.

    `more_reasons(units)` is a reason this reference point can only state once its units exist; it
    reaches the row through the table like every other reason."""
    return emitted_document(reference, layer_rows(reference, ctx), ctx, more_reasons)


def mapping_problems(expected, units):
    """Done-when 1: every item of the expected set — read from the baseline file itself, not from
    what was produced — carries at least one unit."""
    produced = {unit["item_ref"] for unit in units if unit["item_ref"]}
    return [f"BASELINE_UNMAPPED {ref}: the release reference point produced no unit for this baseline item"
            for ref in sorted(expected) if ref not in produced]


# The inputs an omission row is keyed to one pin, snapshot or baseline for: a shared inventory takes only
# its own of these, and every other omission of the run.
KEYED_INPUTS = ("pin", "snapshot", "release_baseline")


def shared_inventories(ctx):
    """`[(relative path, document)]` of every shared inventory (step 0 S-22, S-25): a selection
    inventory per verified snapshot a Claude session's OWN pin names, through the very producers
    `selection.json` is made by, and a release inventory per baseline those snapshots name, its catalog
    and adopted packages only (its overlays and session injection are per session, S-17).

    Each runs over a context of its own: its own snapshot or baseline, the omission of THAT input and no
    other (S-25), and notes of its own, so nothing one inventory reads reaches another's rows. The run's
    UNKEYED omissions (runtime state, user state, the installed baseline, learning journals) are the
    same inputs for every reference point, so they reach a shared inventory exactly as they reach
    `selection.json`: through the inputs each producer declares. Starting from none hid a producer that
    declared one (pretrial-p24b-2, W21). Only the rows keyed to a pin, a snapshot or a baseline are its own."""
    out, snapshots = [], {}
    unkeyed = [row for row in ctx.get("omissions") or [] if row["input"] not in KEYED_INPUTS]
    for pinned in (ctx.get("session_pins") or {}).values():
        if pinned["status"] == "read" and pinned.get("snapshot") is not None:
            snapshots.setdefault(pinned["content_ref"], pinned["snapshot"])
    for content_ref, snapshot in sorted(snapshots.items()):
        sub = {**ctx, "notes": {}, "omissions": list(unkeyed), "pin": None, "pin_record": {"content_ref": content_ref},
               "snapshot": snapshot, "selection_host": "claude"}
        out.append(shared_document("selection", content_ref, layer_rows("selection", sub), ctx,
                                   unavailable=unavailable_rows(ctx, snapshot)))
    for ref, (items, failures) in sorted((ctx.get("session_baselines") or {}).items()):
        omissions = list(unkeyed) + [{"input": "release_baseline", "ref": ref, **row} for row in failures]
        sub = {**ctx, "notes": {}, "omissions": omissions, "pin": None, "pin_record": None, "release_ref": ref,
               "expected_release_items": items or [], "release_deferred": False}
        rows = [row for row in layer_rows("release", sub) if row["layer"] in SHARED_RELEASE_LAYERS]
        out.append(shared_document("release", ref, rows, ctx,
                                   expected={item["ref"] for item in items} if items is not None else None))
    return out


def unavailable_rows(ctx, snapshot):
    """A selection's `output.unavailable` (S-22): each `ref` must be one of the snapshot's own items
    (the catalog builds the list from its normalized items only) and each `surface` one of the
    catalog's `SURFACES`; emitted with those as the fields' whole vocabulary, so any other is refused
    by name. `reason` is metadata through the floor."""
    rows = (snapshot.get("output") or {}).get("unavailable") or []
    if not rows:
        return [], ()
    refs = tuple(sorted({item["ref"] for item in snapshot.get("items") or []
                         if isinstance(item, dict) and isinstance(item.get("ref"), str)}))
    surfaces = tuple(sorted(catalog_module(ctx["repo"]).SURFACES))
    return rows, (refs, surfaces)


def shared_document(kind, ref, rows, ctx, unavailable=None, expected=None):
    """One shared inventory as `shared/<kind>-<i>.json` publishes it: its layer rows, the carrier
    versions it holds and its units, by reference into the store, and — a release — its baseline items
    the units do not map (done-when 1, per inventory: lead ruling 6 on the P2.4 plan)."""
    place = {"home": ctx.get("home"), "decisions": {}}
    carriers = [item for row in rows for item in row.get("carriers") or []]
    ctx.setdefault("carriers_named", []).extend(carriers)
    units = produce(rows)
    reasons = [text for row in rows for text in row["reasons"]]
    unmapped = mapping_problems(expected, units) if expected is not None else []
    identity = inventory_id(kind, ref)
    document = {
        "document": SHARED, "inventory_id": identity, "kind": kind, "ref": ref,
        "complete": not (reasons or unmapped), "incomplete_reasons": reasons + unmapped,
        "produced_by": {"module": "session-distill/runlib/inventory.py", "design": DESIGN, "commit": ctx.get("commit")},
        "layers": [{key: row[key] for key in ("layer", "producer", "status", "units", "empty", "reasons")} for row in rows],
        "carriers": [{"carrier_id": carrier_id, "version_sha256": version}
                     for carrier_id, version in sorted({(item["carrier_id"], item["version_sha256"]) for item in carriers})],
        "unit_refs": sorted({unit["unit_ref"] for unit in units}),
    }
    table = SHARED_INVENTORY_TABLE
    if kind == "selection":
        rows_out, vocabulary = unavailable or ([], ())
        document["unavailable"] = rows_out
        if vocabulary:
            table = table_of({**SHARED_INVENTORY_TABLE["fields"], "unavailable": list_of(table_of({
                "ref": as_enum(vocabulary[0]), "surface": as_enum(vocabulary[1]), "reason": as_metadata()}))},
                optional=SHARED_INVENTORY_TABLE["optional"], schema=SHARED_INVENTORY_TABLE["schema"])
    else:
        document["baseline_unmapped"] = unmapped
        document["baseline_items_expected"] = len(expected) if expected is not None else None
    return f"shared/{kind}-{identity}.json", emit_row("shared_inventory", table, document, place)


def artifact_problems(artifacts):
    """The manifest's artifact rows against their rule (S-22; lead ruling 5, 14:55): a shared inventory
    is listed with its `i-` id, at the path that id names, and a single document with no id. The
    manifest has no JSON schema of its own, so the tie is this check, refused by name."""
    problems = []
    for row in artifacts:
        identity, path = row.get("id"), str(row.get("path"))
        if row.get("document") == SHARED:
            if not (isinstance(identity, str) and path.endswith(f"-{identity}.json")):
                problems.append(f"ARTIFACT_ID_MISMATCH {path}: a shared inventory is listed at the path its id names")
        elif identity is not None:
            problems.append(f"ARTIFACT_ID_UNEXPECTED {path}: a single document is listed with no id")
    return problems


def shared_cross_problems(shared, store, sessions):
    """What the shared inventories get wrong against the store and the session records (step 0 S-21):
    each id is the one its kind and ref derive, every carrier version and unit it names is in the store,
    and every session's `selection.inventory_ref` names a published selection inventory."""
    problems = []
    versions, units = store.get("versions") or {}, store.get("units") or {}
    published = {document.get("inventory_id"): document for _path, document in shared}
    for _path, document in shared:
        identity = document.get("inventory_id")
        if identity != inventory_id(document.get("kind"), document.get("ref")):
            problems.append(f"SHARED_ID_MISMATCH {identity}: not the id its kind and ref derive")
        if any((versions.get(row.get("carrier_id")) or {}).get(row.get("version_sha256")) is None
               for row in document.get("carriers") or []):
            problems.append(f"SHARED_VERSION_UNRESOLVED {identity}: a carrier version it names is not in the store")
        if any(ref not in units for ref in document.get("unit_refs") or []):
            problems.append(f"SHARED_UNIT_UNRESOLVED {identity}: a unit it names is not in the store")
    for record in sessions.get("sessions") or []:
        ref = (record.get("selection") or {}).get("inventory_ref")
        if ref is not None and (published.get(ref) or {}).get("kind") != "selection":
            problems.append(f"SHARED_SELECTION_UNRESOLVED: a session's selection names no published selection inventory")
    return problems


# The members of a published document whose strings are REASONS, and the exception types none of them may
# name (lead, after a36c728): a Python exception's type is not something a reader of a row can act on.
REASON_MEMBERS = ("reasons", "incomplete_reasons", "reason", "unknown", "acquisition_error", "baseline_unmapped")
def exception_names():
    """Every exception type name a reason may not carry, derived when asked and never listed by hand
    (lead ruling 4, 14:55): the `__name__` of each BaseException subclass in builtins, in this module,
    and in every module this module holds (json's JSONDecodeError, tomllib's TOMLDecodeError, sources'
    Unreadable). A name that does not begin with a capital is left out: it is how `type(exc).__name__`
    prints none of the classes a reason here could meet, and the word `error` is ordinary prose."""
    spaces = [vars(builtins), globals()] + [vars(value) for value in list(globals().values())
                                            if isinstance(value, type(builtins))]
    return {value.__name__ for space in spaces for value in list(space.values())
            if isinstance(value, type) and issubclass(value, BaseException) and value.__name__[:1].isupper()}


def exception_named_problems(document, where="$"):
    """`(problems, reasons judged)`: every reason string of one published document that names a Python
    exception type, by its location, and how many reason strings there were to judge."""
    problems, judged = [], [0]
    named = re.compile(r"\b(" + "|".join(sorted(map(re.escape, exception_names()), key=len, reverse=True)) + r")\b")

    def walk(value, at, inside):
        if isinstance(value, dict):
            for key, inner in value.items():
                walk(inner, f"{at}.{key}", inside or key in REASON_MEMBERS)
        elif isinstance(value, list):
            for n, inner in enumerate(value):
                walk(inner, f"{at}[{n}]", inside)
        elif isinstance(value, str) and inside:
            judged[0] += 1
            if named.search(value):
                problems.append(f"REASON_NAMES_EXCEPTION {at}: a reason names a Python exception type")

    walk(document, where, False)
    return problems, judged[0]


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
    result["watched_roots"] = {str(root): len(before[str(root)]) for root in watched}  # projected when emitted
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
    "sessions": table_of({"sessions": as_scalar(), "events": as_scalar(), "unknown": as_scalar()}),
    "store": table_of({"versions": as_scalar(), "units": as_scalar()}),
    "artifacts": list_of(table_of({"path": as_metadata(), "document": as_enum(tuple(REFERENCES) + (SESSIONS, STORE, SHARED)),
                                   "id": as_opaque("inventory_id", nullable=True), "sha256": as_opaque("sha256")})),
}, optional=("sessions", "store", "artifacts", "baseline_unmapped", "baseline_items_expected", "state_written", "native_changed",
             "watched_roots", "watched_native_files", "state_root_unchanged"))


# One shared inventory (step 0 S-22). Its `unavailable` rows' `ref` and `surface` are enums of the snapshot's
# own item refs and the catalog's SURFACES, set per inventory by `shared_document`; empty here.
SHARED_INVENTORY_TABLE = table_of({
    "document": as_constant(SHARED),
    "inventory_id": as_opaque("inventory_id"),
    "kind": as_enum(SHARED_KINDS),
    "ref": as_metadata(),
    "complete": as_scalar(),
    "incomplete_reasons": list_of(as_metadata()),
    "produced_by": SESSIONS_PRODUCED_BY_TABLE,
    "layers": list_of(LAYER_ROW_TABLE),
    "carriers": list_of(table_of({"carrier_id": as_opaque("carrier_id"), "version_sha256": as_opaque("sha256")})),
    "unit_refs": list_of(as_opaque("unit_ref")),
    "unavailable": list_of(table_of({"ref": as_enum(()), "surface": as_enum(()), "reason": as_metadata()})),
    "baseline_unmapped": list_of(as_metadata()),
    "baseline_items_expected": as_scalar(nullable=True),
}, optional=("unavailable", "baseline_unmapped", "baseline_items_expected"), schema="shared_inventory_document")


def run(repo, state_root, user_root, out_dir, pin=None, native_roots=None, ledger=None, commit=None,
        run_dir=None, zstd=None, declared_state=None, declared_user=None, environ=None, home=None):
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
    # The home every path in the manifest and every refusal message is projected against. A
    # production caller passes none and gets this process's own home, exactly as before; the home is
    # a SPELLING, not a decision — `temp_home` and `overlap_problems` judge paths and use it only to
    # write them down. A caller whose roots live under a home of its own passes that home, so the
    # projection is taken against the home the roots actually belong to (this suite's fixture does).
    home = str(pathlib.Path.home()) if home is None else str(home)
    temp_root = temp_home(guarded, home, environ)   # chosen and judged before any write, GC#1
    overlaps = overlap_problems([out_dir], guarded, home=home)
    if overlaps:
        raise Refused("; ".join(overlaps))
    watched = [root for root in (state_root, user_path) if root is not None and root.is_dir()]
    before, omitted = {}, {}
    for root in watched:
        before[str(root)], omitted[str(root)] = hash_tree(root)
    # Raw paths: MANIFEST_TABLE's METADATA rule projects every one against this run's home when the manifest
    # is emitted, the floor's one path for every document (lead, after b0abfef: masking here as well was a
    # second restatement of that projection, and a revert of either one was invisible).
    inputs = {"symlink_policy": SYMLINK_POLICY, "protected_roots": [str(root) for root in guarded],
              "roots": {str(root): {"files": len(before[str(root)]), "omissions": omitted[str(root)]}
                        for root in watched},
              "roots_absent": [str(root) for root in (state_root, user_path)
                               if root is not None and not root.is_dir()],
              "transcripts": {"read_through": "runlib/sources.read_lines, bound to the S1 census record",
                              "native_files_read": 0}}
    produced, manifest = {}, {"references": {}, "state_root_unchanged": None,
                              "out_dir": str(out_dir), "inputs": inputs}
    try:
        with no_bytecode(), tempfile.TemporaryDirectory(prefix="distill-inventory-", dir=str(temp_root)) as frozen_dir:
            ctx = context_of(repo, state_root, user_root, dict(native_roots or {}), pin, ledger)
            ctx["commit"] = commit
            # One home, the one every artifact below is judged against by `write_document`: emitted against
            # another (the process's), a leaf under the caller's home was not spelled `<HOME>` and the write
            # refused it (lead, P2.4b). A production caller passes none, and both are the process's home.
            ctx["home"] = home
            try:
                entries = census_entries(run_dir)
            except Unacquired:
                entries = ()  # no census: `bind_transcripts` names it, and no session's pin is read
            try:
                freeze_inputs(pathlib.Path(frozen_dir), repo, state_root, user_root, pin, ctx, entries)
            except Exception as exc:  # acquisition is an input, and a missing input is a status
                ctx["acquisition_error"] = (f"INPUT_UNACQUIRED: freezing the inputs failed "
                                            f"({acquisition_reason(exc)}), so every layer "
                                            f"read from the owner's state has no record here")
                ctx.setdefault("release_ref", None)
                ctx.setdefault("expected_release_items", [])
                # A pin the failure left unread was there to read: failed, not a root this run lacked.
                table = ctx.setdefault("session_pins", {})
                for entry in entries:
                    pinned = session_pin(None, entry.get("host"), entry.get("id"), entry.get("pin"))
                    if state_root is not None and pinned["reason"] == "input_unread":
                        pinned = {**pinned, "reason": reason("input_failed"), "outcome": "failed", "detail": "not_admitted"}
                    table.setdefault(session_ref(entry.get("host"), entry.get("id")), pinned)
            bind_transcripts(ctx, run_dir, zstd)
            inputs["transcripts"].update(ctx["notes"]["transcripts"])
            sessions_doc = sessions_document(ctx)
            crossed = sessions_cross_problems(sessions_doc)
            if crossed:
                raise Refused(f"{'; '.join(crossed)}; no artifact is written")
            expected_refs = {item["ref"] for item in ctx["expected_release_items"]} \
                if ctx.get("release_ref") else None
            for reference in REFERENCES:
                produced[reference] = reference_of(
                    reference, ctx,
                    more_reasons=(lambda units: mapping_problems(expected_refs, units))
                    if expected_refs is not None and reference == "release" else None)
            base = produced["release"][1]
            for reference in ("current", "selection"):
                produced[reference][0]["renames"] = renames_against(produced[reference][1], base, home)
            shared = shared_inventories(ctx)
            store_doc = store_document(ctx)
            crossed = store_cross_problems(store_doc, {reference: produced[reference][0] for reference in REFERENCES}) \
                + occurrence_cross_problems(sessions_doc, store_doc) + shared_cross_problems(shared, store_doc, sessions_doc)
            if crossed:
                raise Refused(f"{'; '.join(crossed[:4])}; no artifact is written")
            if ctx.get("release_ref"):
                # The reference row already carries these, emitted through the table with every
                # other reason. The manifest keeps its own copy, which its own table projects.
                problems = mapping_problems(expected_refs, produced["release"][1])
                manifest["baseline_unmapped"] = problems
                manifest["baseline_items_expected"] = len(ctx["expected_release_items"])
        artifacts = manifest["artifacts"] = []

        def written(relative, document, identity=None):
            """Write one artifact and list it in the manifest (S-22): its kind, its opaque id when it has
            one, and the sha256 of the bytes written. The manifest is not in its own list. The row is
            judged before the artifact is written."""
            row = {"path": f"inventory/{relative}", "document": document["document"], "id": identity}
            listed = artifact_problems([row])
            if listed:
                raise Refused(f"{'; '.join(listed)}; no artifact is written")
            path = out_dir / "inventory" / relative
            write_document(out_dir, path, document, home)
            artifacts.append({**row, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

        written(f"{SESSIONS}.json", sessions_doc)
        manifest["sessions"] = {"sessions": len(sessions_doc["sessions"]), "events": len(sessions_doc["events"]),
                                "unknown": sum(len(row["unknown"]) for row in sessions_doc["sessions"])}
        written(STORE_REL, store_doc)
        for relative, document in shared:
            written(relative, document, document["inventory_id"])
        manifest["store"] = {"versions": sum(len(rows) for rows in store_doc["versions"].values()),
                             "units": len(store_doc["units"])}
        for reference, (document, units) in produced.items():
            written(f"{reference}.json", document)
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
    """Read this run's census-bound transcripts into the context: the events, §8's current sets, and
    every named unknown.

    This is the only place a transcript is read, and it reads none of the owner's instruction files.
    Each session's own pin is what `freeze_inputs` read into `ctx["session_pins"]`; a session it holds
    none for is a pin this run did not read, never an assumed one."""
    table = ctx.get("session_pins") or {}
    notes = {"read_through": "runlib/sources.read_lines, bound to the S1 census record",
             "native_files_read": 0}
    ctx["occurrences"] = []
    try:
        events, unknown, findings = transcript_events(run_dir, table, zstd)
    except Unacquired as exc:
        ctx["transcript_error"] = str(exc)
        notes.update({"sessions": 0, "events": 0, "unknown": [str(exc)]})
        ctx["notes"]["transcripts"] = notes
        ctx["current_scopes"] = None
        ctx["sessions"], ctx["events"], ctx["segments"] = [], [], []
        return
    ctx["events"] = events
    ctx["sessions"] = findings["sessions"]
    ctx["segments"] = findings["segments"]
    ctx["occurrences"] = findings["occurrences"]
    entries = census_entries(run_dir)
    pins = {}
    for entry in entries:
        ref = session_ref(entry.get("host"), entry.get("id"))
        pins[ref] = pin_state(table.get(ref) or session_pin(None, entry.get("host"), entry.get("id"), entry.get("pin")))
    if ctx.get("pin") and not any(f"{entry.get('host')}:{entry.get('id')}" == ctx["pin"] for entry in entries):
        # the `--pin` session's selection is evidence about its pin only: no transcript of it is read (S-15)
        notes["pin_delivery"] = reason("no_census_session")
    ctx["current_scopes"] = current_scopes(events, findings["timelines"], pins)
    # A delivery is confirmed only by a usable RECORDED occurrence the session's main owner holds in its own
    # transcript (step 0 S-13): a sidechain's copy, and a match whose bytes could not be recovered, are not.
    delivery = [event for event in events if event["kind"] == "session_injection" and not event.get("damaged")
                and event.get("transcript") == "main"
                and any(match["method"] != "unmapped" for match in event.get("matches") or [])]
    notes.update({"events": len(events), "native_events": len([e for e in events if e["kind"] == "native"]),
                  "delivery_confirmed": len(delivery),
                  # the answers themselves are `current.json`'s `scopes`; here, how many of each
                  "current_scopes": [f"{layer} {status} {n}" for (layer, status), n in sorted(collections.Counter(
                      (row["layer"], row["status"]) for row in ctx["current_scopes"]["scopes"]).items())],
                  # every one, never a prefix: the authoritative per-session answers are in
                  # `sessions.json`, and a truncated list here would be the one a reader trusts
                  "unknown": unknown, "unknown_total": len(unknown), "sessions": len(findings["sessions"]),
                  # What the reading found unusable, each at its line under a fixed category (M2, M5).
                  # Recorded here and nowhere else yet: what an earlier event's applicability becomes
                  # across one of these is the reference model's to decide.
                  "undecodable": findings["undecodable"], "damaged": findings["damaged"],
                  "rejected": findings["rejected"],
                  # a parent's session_meta carried into a child or fork rollout: counted, never an event (M10)
                  "inherited": findings["inherited"]})
    ctx["notes"]["transcripts"] = notes


def freeze_inputs(frozen, repo, state_root, user_root, pin, ctx, entries=()):
    """Copy what the producers read and point the context at the copies: after this, no producer
    holds a path under the owner's state or home.

    Every input is acquired ON ITS OWN, and what happened to it is a row in `ctx["omissions"]` —
    `{input, ref, path, outcome, reason, code}` — rather than an exception (#16). An input that is
    not there is `absent`; one that is there and was not read is `failed`; one this run was given no
    root for is `unread`. Which layers that touches is decided in `layer_rows`, from the inputs each
    producer DECLARES: a pin that does not resolve leaves the catalog of the checkout and the
    transcript layers exactly as they were, which an exception out of here used not to (every layer
    went unknown at once). Every `freeze` result is collected, the pinned baseline's included.

    Every census row in `entries` has its OWN pin read into `ctx["session_pins"]` (step 0 S-15, S-16,
    S-25), with its snapshot frozen and verified once per `content_ref` however many sessions name it.
    A session's failure is that session's, stated in its own record and in no omission row, so it
    reaches no reference point it is not. The `--pin` reference point takes the same entry when the
    census names its pin; a `--pin` the census names no pin for is evidence about that pin only."""
    state, user = frozen / "state", frozen / "user"
    ctx["state_root"], ctx["user_root"] = state, user
    # The project roots are protected write targets and nothing else: no native file is read, here
    # or anywhere (the 1548 amendment §5).
    ctx["projects"] = [str(root) for root in (ctx["native_roots"].get("projects") or {}).values()]
    omissions = ctx.setdefault("omissions", [])
    ctx.setdefault("pin_record", None)
    ctx["installed_ref"], ctx["release_ref"], ctx["expected_release_items"] = None, None, []
    # S-24 option 1 and S-16: an unpinned release, and a Codex one, is `release_history_deferred`. The
    # installed baseline is frozen for the current overlays only, and no journal is read for a release.
    ctx["release_deferred"] = pin is None or str(pin).partition(":")[0] != "claude"
    ctx["session_baselines"] = {}

    def omitted(kind, ref, path, outcome, reason, code=None):
        row = {"input": kind, "ref": ref, "path": path, "outcome": outcome, "reason": reason, "code": code}
        if row not in omissions:
            omissions.append(row)

    def froze(kinds, ref, sources, destination, root):
        """`freeze` over one input's sources, every row it reports tagged with the input it is."""
        for row in freeze(sources, destination, root):
            for kind in kinds:
                omitted(kind, ref, row["path"], row["outcome"], row["reason"], row["code"])

    if user_root is None:
        for kind in ("user_state", "learning_journals"):
            omitted(kind, None, None, "unread", "no_root")
    else:
        user_root = pathlib.Path(user_root).expanduser()
        froze(("user_state",), None, [(user_root / "state.json", "state.json")], user, user_root)
        froze(("learning_journals",), None, [(user_root / "learnings", "learnings")], user, user_root)
    census = {(entry.get("host"), entry.get("id")): entry for entry in entries or ()}
    snapshots, table = {}, {}
    ctx["session_pins"] = table

    def snapshot_once(content_ref):
        """`(verified, outcome, detail, code)` of one snapshot, frozen and verified once."""
        if content_ref not in snapshots:
            rows = freeze([(state_root / "sessions" / "snapshots" / content_ref, f"sessions/snapshots/{content_ref}")],
                          state, state_root)
            if rows:
                snapshots[content_ref] = (None, rows[0]["outcome"], rows[0]["reason"], rows[0]["code"])
            else:
                try:
                    snapshots[content_ref] = (snapshot_of(repo, state, content_ref), None, None, None)
                except Exception as exc:  # the store's verifier raises its own error types
                    snapshots[content_ref] = (None, "failed", acquisition_reason(exc), refusal_code(exc))
        return snapshots[content_ref]

    def with_snapshot(pinned, host, ident):
        """A read pin, frozen, with its snapshot and the baseline that snapshot names (S-25's chain)."""
        rows = freeze([(state_root / "sessions" / "pins" / host / f"{ident}.json", f"sessions/pins/{host}/{ident}.json")],
                      state, state_root)
        if rows:
            return {**pinned, "status": "unknown", "reason": reason("input_failed"), "record": None,
                    "content_ref": None, "include": None, "outcome": "failed", "detail": rows[0]["reason"],
                    "code": rows[0]["code"]}
        verified, outcome, detail, code = snapshot_once(pinned["content_ref"])
        inputs = (verified or {}).get("inputs")
        named = inputs.get("baseline_ref") if isinstance(inputs, dict) else None
        return {**pinned, "snapshot": verified,
                "baseline_ref": named if isinstance(named, str) and SAFE_LABEL.match(named) else None,
                "snapshot_reason": None if verified is not None
                else reason("snapshot_absent") if outcome == "absent" else reason("input_failed"),
                "snapshot_omission": (outcome, detail, code)}

    for (host, ident), entry in census.items():
        pinned = session_pin(state_root, host, ident, entry.get("pin"))
        table[session_ref(host, ident)] = with_snapshot(pinned, host, ident) if pinned["status"] == "read" else pinned
    if state_root is None:
        ctx["notes"]["state"] = "no state root: the overlay, release and selection producers have no record"
        for kind in ("runtime_state", "installed_baseline") + (() if ctx["release_deferred"] else ("release_baseline",)) \
                + (("pin", "snapshot") if pin else ()):
            omitted(kind, pin if kind == "pin" else None, None, "unread", "no_root")
        return
    # Every read below goes through the one source selection, before any byte of it is read: the
    # runtime state here, the pin in `read_pin`, the snapshot in `snapshot_of`, the baseline's item
    # list in `baseline_items`, and each copy input in `freeze` (GC#7).
    runtime_path = state_root / "runtime" / "state.json"
    runtime = {}
    if runtime_path.is_file() or runtime_path.is_symlink():
        try:
            loaded = json.loads(read_source(runtime_path, state_root))
            if not isinstance(loaded, dict):
                raise ValueError("the runtime state is not an object")
            runtime = loaded
        except (Refused, ValueError, OSError) as exc:
            omitted("runtime_state", None, "runtime/state.json", "failed", acquisition_reason(exc), refusal_code(exc))
    froze(("runtime_state",), None, [(runtime_path, "runtime/state.json")], state, state_root)
    verified = None
    if pin:
        ctx["pin_record"] = None
        host, _, session_id = pin.partition(":")
        named = census.get((host, session_id))
        if host == "claude" and named is not None and named.get("pin") is not None:
            pinned = table[session_ref(host, session_id)]
        else:
            # no census row, or one that names no pin: evidence about this pin only (S-15, S-16)
            pinned = session_pin(state_root, host, session_id, None, evidence=True)
            pinned = with_snapshot(pinned, host, session_id) if pinned["status"] == "read" else pinned
            if host == "claude" and named is not None and pinned["status"] == "read":
                # The census row names no pin and the frozen state holds one: under M6 they disagree (the
                # state moved, or the census could not read it). The session's own record says so, and so
                # does every document this evidence reaches, so none says unpinned while another shows the
                # selection (lead ruling on the P2.4 readings).
                table[session_ref(host, session_id)] = disagreeing(pinned, pinned["content_ref"])
                ctx["pin_disagreement"] = (f"{reason('pin_content_ref_mismatch')}: "
                                           f"{UNKNOWN_REASONS['pin_content_ref_mismatch']}; the --pin is evidence "
                                           f"about its pin only")
        if pinned["status"] != "read":
            omitted("pin", pin, None, pinned["outcome"], pinned["detail"], pinned["code"])
        else:
            ctx["pin_record"] = pinned["record"]
            verified = pinned["snapshot"]
            if verified is None:
                omitted("snapshot", pinned["content_ref"], f"sessions/snapshots/{pinned['content_ref']}",
                        *pinned["snapshot_omission"])
    else:
        ctx["notes"]["selection"] = "no pin: the selection reference point has no record (§6.3)"
    # Both baselines, always, and each with its own provenance. The current reference point's
    # overlays resolve against whatever the installed state selects, while the pin names the
    # baseline the session was activated from; freezing only the pin's left the current resolver
    # without its baseline tuple as soon as an upgrade moved the installed one (GA#8).
    installed_ref = runtime.get("selected_baseline_ref")
    if installed_ref is not None:
        try:
            installed_ref = safe_label("baseline ref", installed_ref)
        except Refused as exc:
            omitted("installed_baseline", None, "runtime/state.json", "failed", "not_an_identifier", refusal_code(exc))
            installed_ref = None
    ctx["installed_ref"] = installed_ref
    release_ref = None
    if ctx["release_deferred"]:
        ctx["notes"]["release"] = "release_history_deferred: no pin, or a Codex one, names this release (S-24, S-16)"
    ctx["notes"]["baselines"] = {"installed": installed_ref, "pinned": None}
    baselines = {}

    def baseline_once(ref):
        """`(items, failures)` of one baseline, frozen and its item list read once: `items` is None
        when any of it could not be acquired, and `failures` holds one `freeze`-shaped row per path."""
        if ref not in baselines:
            failures = [{key: row[key] for key in ("path", "outcome", "reason", "code")}
                        for row in freeze([(state_root / "runtime" / "baselines" / ref, f"runtime/baselines/{ref}")],
                                          state, state_root)]
            items, listed = None, f"runtime/baselines/{ref}/inventory.json"
            if not failures:
                try:
                    items = baseline_items(state, ref)
                except Refused as exc:
                    absent = refusal_code(exc) == "BASELINE_ABSENT"
                    failures = [{"path": listed, "outcome": "absent" if absent else "failed",
                                 "reason": "absent" if absent else acquisition_reason(exc), "code": refusal_code(exc)}]
                except (ValueError, OSError) as exc:
                    failures = [{"path": listed, "outcome": "failed", "reason": acquisition_reason(exc),
                                 "code": refusal_code(exc)}]
            baselines[ref] = (items, failures)
        return baselines[ref]

    if installed_ref:
        froze(("installed_baseline",), installed_ref,
              [(state_root / "runtime" / "baselines" / installed_ref, f"runtime/baselines/{installed_ref}")],
              state, state_root)
    if verified is not None:
        content_ref = verified["content_ref"]
        ctx["snapshot"] = verified
        ctx["notes"]["pin"] = {"host": pin.partition(":")[0], "content_ref": verified["content_ref"],
                               "state": ctx["pin_record"].get("state")}
        release_ref = None if ctx["release_deferred"] else (verified["inputs"] or {}).get("baseline_ref")
        if release_ref is not None:
            try:
                release_ref = safe_label("baseline ref", release_ref)
            except Refused as exc:
                omitted("release_baseline", None, f"sessions/snapshots/{content_ref}", "failed",
                        "not_an_identifier", refusal_code(exc))
                release_ref = None
        if release_ref:
            items, failures = baseline_once(release_ref)
            for row in failures:
                omitted("release_baseline", release_ref, row["path"], row["outcome"], row["reason"], row["code"])
            if items is not None:
                ctx["expected_release_items"] = items
            ctx["notes"]["release"] = "from the pin's snapshot inputs.baseline_ref"
            ctx["notes"]["baselines"] = {"installed": installed_ref, "pinned": release_ref,
                                         "differ": installed_ref != release_ref}
    ctx["release_ref"] = release_ref
    # Every baseline a session's own verified snapshot names, each frozen once under its own key, for
    # the shared release inventories (S-22, S-25's `baseline@<ref>`): a failure reaches the inventory of
    # THAT baseline and the sessions naming it, and nothing else.
    for pinned in table.values():
        ref = pinned.get("baseline_ref") if pinned["status"] == "read" and pinned.get("snapshot") else None
        if ref and ref not in ctx["session_baselines"]:
            ctx["session_baselines"][ref] = baseline_once(ref)
    ctx["notes"]["frozen_missing"] = [{**row, "class": INPUT_CLASSES[row["input"]]} for row in omissions]


def acquisition_reason(exc):
    """The fixed category an acquisition failure is reported under."""
    code = refusal_code(exc)
    return {"SOURCE_LINKED": "symlink", "PIN_IDENTITY_MISMATCH": "pin_mismatch",
            "PIN_UNREADABLE": "unreadable", "INPUT_INVALID": "not_an_identifier",
            "BASELINE_EMPTY": "empty", "JSONDecodeError": "not_json", "ValueError": "malformed",
            "UnicodeDecodeError": "not_json", "Unreadable": "unreadable"}.get(code, "unreadable" if isinstance(exc, OSError) else "not_admitted")


def input_reasons(inputs, context):
    """The reasons a producer's declared inputs give against running it, or `[]`.

    A row about one of the inputs this producer reads blocks it when the input FAILED, was not read
    at all, or is absent and REQUIRED; an absent optional input is the empty answer the store gives,
    and blocks nothing. A row names the ref it is about, so when several pins, snapshots or
    baselines are acquired, one's failure answers only for the producer reading that one."""
    refs = {"pin": context.get("pin"),
            "snapshot": (context.get("pin_record") or {}).get("content_ref"),
            "installed_baseline": context.get("installed_ref"),
            "release_baseline": context.get("release_ref")}
    reasons = []
    for row in context.get("omissions") or []:
        kind = row["input"]
        if kind not in inputs or (row["ref"] is not None and refs.get(kind) not in (None, row["ref"])):
            continue
        if row["outcome"] == "failed":
            reason = f"{UNKNOWN_REASONS['input_failed']} ({kind}: {row['reason']})"
        elif row["outcome"] == "unread":
            reason = f"{UNKNOWN_REASONS['input_unread']} ({kind})"
        elif kind in ("installed_baseline", "release_baseline"):
            # a baseline a release names that is not there (S-25's `baseline@<ref>`)
            reason = f"{UNKNOWN_REASONS['baseline_absent']} ({kind})"
        elif INPUT_CLASSES[kind] == "required":
            reason = f"{UNKNOWN_REASONS['input_absent']} ({kind})"
        else:
            continue
        if reason not in reasons:
            reasons.append(reason)
    return reasons


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
# The schema's `$defs` root for every document this module publishes, by the kind its `document`
# member names (step 0 S-21). Held against the consts the schema declares by `document_roots_problems`.
DOCUMENT_ROOTS = {**{reference: f"{reference}_document" for reference in REFERENCES}, SESSIONS: "sessions_document",
                  STORE: "shared_store_document", SHARED: "shared_inventory_document"}
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
    try:
        validate.compile_schema(schema)
    except Exception as exc:  # a schema this policy refuses is a named failure, not a traceback
        return [f"SCHEMA_INVALID {SCHEMA_REL}: {type(exc).__name__}: {exc}"]
    # One root per document: the `$defs` entry its `document` names (step 0 S-21, `DOCUMENT_ROOTS`).
    # The schema policy has no `oneOf`, so the pick is made here, and a kind no root is declared for
    # is refused by name: judged as another document, a misspelled one passed on the members the two
    # happened to share.
    kind = document.get("document") if isinstance(document, dict) else None
    if not (isinstance(kind, str) and kind in DOCUMENT_ROOTS):
        return [f"DOCUMENT_KIND_UNDECLARED: the document names "
                f"{'no kind' if kind is None else 'a kind no root is declared for'}"]
    # A reference point is judged on the members its root declares (its units, its layer rows and,
    # for `current`, its scope rows); every other document whole.
    declared = ((schema.get("$defs") or {}).get(DOCUMENT_ROOTS[kind]) or {}).get("properties") or {}
    subject = ({key: value for key, value in document.items() if key in declared}
               if kind in REFERENCES else document)
    picked = {**({"$schema": schema["$schema"]} if "$schema" in schema else {}),
              "$defs": schema.get("$defs") or {}, "$ref": f"#/$defs/{DOCUMENT_ROOTS[kind]}"}
    try:
        validator = validate.compile_schema(picked)
    except Exception as exc:
        return [f"SCHEMA_INVALID {SCHEMA_REL}: {type(exc).__name__}: {exc}"]
    return [f"DOCUMENT_INVALID {row}" for row in validate.validate_instance(validator, subject)]


def document_roots_problems(schema=None):
    """`DOCUMENT_ROOTS` against the schema, read from the schema and never restated: a root is a
    `$defs` entry whose `document` is a const, it must require that member, each kind has one root,
    the code picks every root by the kind the schema gives it, the file root's kind list is that set,
    and every document this module publishes has a root."""
    schema, problems = _schema_or_problem(schema)
    if problems:
        return problems
    defs, roots = schema.get("$defs") or {}, {}
    for name, shape in defs.items():
        member = ((shape or {}).get("properties") or {}).get("document") or {}
        if "const" not in member:
            continue
        roots.setdefault(member["const"], []).append(name)
        if "document" not in ((shape or {}).get("required") or []):
            problems.append(f"DOCUMENT_ROOT_UNREQUIRED {name}: a root names its kind and does not require it")
    for kind, names in sorted(roots.items(), key=lambda row: str(row[0])):
        if len(names) > 1:
            problems.append(f"DOCUMENT_ROOT_AMBIGUOUS {kind}: {len(names)} roots name this kind")
    declared = {kind: names[0] for kind, names in roots.items()}
    if declared != DOCUMENT_ROOTS:
        problems.append(f"DOCUMENT_ROOTS_MISMATCH: the schema's roots are {sorted(map(str, declared.items()))}, "
                        f"the code picks {sorted(map(str, DOCUMENT_ROOTS.items()))}")
    listed = ((defs.get(str(schema.get("$ref") or "").rpartition("/")[2]) or {}).get("properties") or {}) \
        .get("document") or {}
    if set(listed.get("enum") or ()) != set(DOCUMENT_ROOTS):
        problems.append("DOCUMENT_KIND_ENUM_MISMATCH: the file root's kind list is not the set of roots")
    published = set(REFERENCES) | {SESSIONS, STORE, SHARED}
    if set(DOCUMENT_ROOTS) != published:
        problems.append(f"DOCUMENT_ROOTS_UNCOVERED: the module publishes {sorted(published)}, "
                        f"the roots are picked for {sorted(map(str, DOCUMENT_ROOTS))}")
    return problems


def limitation_schema_problems(schema=None):
    """`LIMITATION_TABLE` against the schema's `limitation` row, both READ: the schema declares one
    closed object (it has no `oneOf`), so the kinds, the categories and the field names the table
    holds each kind to must be the ones the schema admits, and none of them may be empty."""
    schema, problems = _schema_or_problem(schema)
    if problems:
        return problems
    declared = (((schema.get("$defs") or {}).get("limitation") or {}).get("properties") or {})
    choices = LIMITATION_TABLE["choices"]
    held = {"kinds": {choice["fields"]["kind"]["value"] for choice in choices},
            "categories": set().union(*(_enum_values(choice["fields"]["category"]) for choice in choices
                                        if "category" in choice["fields"])),
            "fields": set().union(*(set(choice["fields"]) for choice in choices))}
    admitted = {"kinds": set((declared.get("kind") or {}).get("enum") or ()),
                "categories": set((declared.get("category") or {}).get("enum") or ()),
                "fields": set(declared)}
    for name in ("kinds", "categories", "fields"):
        if not held[name] or held[name] != admitted[name]:
            problems.append(f"LIMITATION_{name.upper()}_MISMATCH: the table holds {sorted(held[name])}, "
                            f"the schema admits {sorted(admitted[name])}")
    return problems


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
        """The `UNKNOWN_REASONS[...]` keys and the `reason("...")` keys inside one node."""
        keys = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Subscript) and getattr(inner.value, "id", None) == "UNKNOWN_REASONS" \
                    and isinstance(inner.slice, ast.Constant):
                keys.add(inner.slice.value)
            elif isinstance(inner, ast.Call) and getattr(inner.func, "id", None) == "reason" and inner.args \
                    and isinstance(inner.args[0], ast.Constant):
                keys.add(inner.args[0].value)
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
    for key in sorted(used - set(UNKNOWN_REASONS), key=str):
        problems.append(f"REASON_UNDECLARED {key}: a path reports a reason the table does not declare")
    return problems


def self_test():
    """Done-when 1-6, each with the control that fails by name when the rule is taken out."""
    # Set where this suite begins publishing its report. Past that point a control is not in the
    # number the summary published, and the summary has already said OK — which is a conclusion
    # printed before the judging. The helpers below refuse past it rather than trusting placement.
    reporting = []
    failures, ran = [], []
    # Registered while this suite runs: an abort publishes what is here instead of taking it away.
    # Removed where this suite reports, below. The boundary is reached as `boundary` because `entry`
    # is a LOCAL name in this suite — a census row, and an omission row — which shadows the module.
    from runlib import entry as boundary
    boundary.SELF_TEST_COLLECTED.append(("inventory --self-test", failures))

    def control(name, problems, *needles):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}: this suite has begun publishing its "
                               f"report, so `control` is not in the count it published")
        # The mirror of the boolean guard below: this helper judges a LIST of problem strings, and a
        # bare string or a bool here would be read character by character or silently admitted.
        if not isinstance(problems, list):
            raise TypeError(f"CONTROL_PROBLEMS_NOT_LIST {name}: this file's `control` judges a list "
                            f"of problems and was given {type(problems).__name__}")
        ran.append(name)
        text = "; ".join(problems)
        if not problems:
            failures.append((name, f"expected a failure naming {needles or ('anything',)}, got none"))
        else:
            missing = [needle for needle in needles if needle not in text]
            if missing:
                failures.append((name, f"expected {missing} among {problems}"))

    def clean(name, problems):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}: this suite has begun publishing its "
                               f"report, so `clean` is not in the count it published")
        ran.append(name)
        if problems:
            failures.append((name, f"expected no violation, got {problems}"))

    class Absent(dict):
        """What a refused full run left behind (lead, after b0abfef: a refusal fails by name and never
        aborts the suite): an EMPTY dict whose every key reads as Absent again, so reading it never
        raises. Equality and membership keep a dict's own meaning (it lies on neither); it orders
        against nothing and adds to nothing, which only spares a comparison from raising. A negative
        control downstream of a judged run carries a presence term, because an empty subject would
        otherwise satisfy it."""
        def __getitem__(self, key):
            return Absent()

        def get(self, key, default=None):
            return Absent() if default is None else default

        __lt__ = __le__ = __gt__ = __ge__ = lambda self, other: False
        __add__ = __radd__ = __sub__ = __rsub__ = lambda self, other: Absent()
        __hash__ = None

    def check(name, ok, detail=""):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}: this suite has begun publishing its "
                               f"report, so `check` is not in the count it published")
        # A condition that reads a refused run's `Absent` (an `and` chain hands it back as it is) is a
        # failed condition, said so, and never a TypeError that ends the suite.
        if isinstance(ok, Absent):
            ok, detail = False, f"{detail} (its subject is a run that wrote nothing)"
        # A boolean-style helper given a problem LIST passed on whatever its needle said, because a
        # non-empty list is truthy: three controls in this package read correctly and asked nothing
        # until S8a found them. The signature is enforced here rather than remembered.
        if not isinstance(ok, bool):
            raise TypeError(f"CONTROL_CONDITION_NOT_BOOL {name}: this file's `check` judges a "
                            f"boolean condition and was given {type(ok).__name__}")
        ran.append(name)
        if not ok:
            failures.append((name, detail))

    def misuse_refusal(call):
        """The message a self-test helper raises when it is MISUSED — the wrong kind of argument, or
        a control asked after the report has begun. The controls below catch it here, so asking a
        guard does not fail the suite."""
        try:
            call()
        except Exception as exc:
            return str(exc)
        return ""

    check("a boolean-style check given a problem list is refused by name",
          "CONTROL_CONDITION_NOT_BOOL" in misuse_refusal(lambda: check("a planted non-boolean", ["a problem"])),
          "the guard admitted a non-boolean condition, so a control in the other style would pass on a truthy list")
    check("a problem-list control given something that is not a list is refused by name",
          "CONTROL_PROBLEMS_NOT_LIST" in misuse_refusal(lambda: control("a planted non-list", "a problem")),
          "the guard admitted a non-list, so a bare string would be read character by character")
    # The flag is planted rather than waited for: the report really beginning is the end of this
    # suite, and a control cannot be asked from there. What is asked is the rule itself.
    reporting.append("a planted report")
    after_summary = misuse_refusal(lambda: check("a planted control after the summary", True))
    reporting.clear()
    check("a control asked after the report has begun is refused by name",
          "CONTROL_AFTER_SUMMARY" in after_summary and not reporting,
          f"{after_summary!r}")

    # ---- the splitter reproduces its carriers, over the real guides (the measured property)
    guides = sorted((REPO / "claude" / "guides").glob("*.md"))[:6] + sorted((REPO / "claude" / "hooks").glob("*.py"))[:2]
    check("the splitter has carriers to reproduce", len(guides) >= 3, f"only {len(guides)} carrier(s) found")
    for path in guides:
        text = path.read_text(encoding="utf-8")
        blocks = blocks_of(path.name, text)
        check(f"the split reproduces {path.name}", "".join(block[1] for block in blocks) == text, "the concatenation differs")
        check(f"{path.name} yields units", len(blocks) > 1, f"{len(blocks)} block(s)")
    # The unparsable carrier these three ask about, bound to a name: spelled inside the f-string
    # below it carried a backslash in the expression part, which only Python 3.12 admits (PEP 701),
    # and this repository's declared floor is 3.11. The controls are unchanged.
    broken_source = "def f(:\n  pass\n"
    control("a carrier whose structure the splitter cannot divide",
            [str(exc) for exc in [_raised(lambda: blocks_of("broken.py", broken_source))]], "broken.py", "MALFORMED_CARRIER")
    control("a supported language that does not parse",
            [str(_raised(lambda: blocks_of("broken.py", broken_source)))], "does not parse in its form")
    check("a parse failure of a supported form is malformed, not unsupported",
          isinstance(_raised(lambda: blocks_of("broken.py", broken_source)), Malformed),
          f"{type(_raised(lambda: blocks_of('broken.py', broken_source))).__name__}")
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
    control("a published reason key the table does not declare",
            reason_problems("".join(f"USED = UNKNOWN_REASONS[{key!r}]\n" for key in UNKNOWN_REASONS)
                            + "NAMED = reason('a_reason_nobody_declared')\n"),
            "REASON_UNDECLARED", "a_reason_nobody_declared")

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

    @contextlib.contextmanager
    def section(name, record=None):
        """One block of this suite's controls (lead ruling "The self-test never aborts: section
        guards"): an exception out of it is a NAMED failed check, "<name> did not run to its end:
        <type>", and the suite goes on with the next block, so a refusal never ends the suite. It
        catches Exception only, never BaseException, and a block that runs to its end adds no control."""
        try:
            yield
        except Exception as exc:  # named below; the next block still runs
            (record or check)(f"{name} did not run to its end: {type(exc).__name__}", False, str(exc)[:300])

    # The guard's own controls: each plants its block under a recorder of its own, so the planted failure
    # never reaches this suite's verdict, and whatever the guard lets out is caught here and said by name.
    class PlantedExit(BaseException):
        """Not an Exception: the guard must let it through."""

    def guard_trial(block, raised):
        """What `section` recorded for a block that raises `raised` (None: it runs to its end), and the
        exception that left the block, if one did."""
        planted_records = []
        try:
            with section(block, record=lambda name, ok, detail="": planted_records.append((name, ok, detail))):
                if raised is not None:
                    raise raised
        except (Exception, PlantedExit) as exc:  # let out by the guard: said by the controls below
            return planted_records, exc
        return planted_records, None

    planted_records, let_out = guard_trial("a planted block", ValueError("planted inside the block"))
    check("a block that raises is one failed control named by its block and the exception's type, and the "
          "exception does not leave the block",
          let_out is None and planted_records == [("a planted block did not run to its end: ValueError", False,
                                                   "planted inside the block")], f"{planted_records} / {let_out!r}")
    planted_records, let_out = guard_trial("a planted long message", ValueError("x" * 400))
    check("a block's failed control carries the exception's first 300 characters as its detail",
          let_out is None and [len(detail) for _name, _ok, detail in planted_records] == [300], f"{let_out!r}")
    planted_records, let_out = guard_trial("a block that runs to its end", None)
    check("a block that runs to its end records nothing", let_out is None and planted_records == [],
          f"{planted_records} / {let_out!r}")
    planted_records, let_out = guard_trial("a planted exit", PlantedExit())
    check("the guard lets an exception that is not an Exception through and records nothing for it",
          isinstance(let_out, PlantedExit) and planted_records == [], f"{planted_records} / {let_out!r}")

    # The default path, no recorder given. `section` reads this suite's `check` through its closure when
    # it is called, so `check` is rebound to a capture for the trial and restored after; the closure's own
    # cell shows the guard saw the capture, and sees the original again.
    def sink_of_section():
        cells = dict(zip(section.__wrapped__.__code__.co_freevars, section.__wrapped__.__closure__ or ()))
        return cells["check"].cell_contents if "check" in cells else None

    held_check, default_records, let_out, sink_during = check, [], None, None
    capture = lambda name, ok, detail="": default_records.append((name, ok, detail))
    try:
        check = capture
        sink_during = sink_of_section()
        try:
            with section("a planted default block"):
                raise ValueError("planted with no recorder")
        except Exception as exc:  # let out by the guard: said by the control below
            let_out = exc
    finally:
        check = held_check
    check("a block given no recorder is one failed control in the suite's own check, and the exception does "
          "not leave the block",
          let_out is None and default_records == [("a planted default block did not run to its end: ValueError",
                                                   False, "planted with no recorder")],
          f"{default_records} / {let_out!r}")
    check("the default-path trial reached the guard's own sink and left it as it was",
          sink_during is capture and sink_of_section() is held_check and check is held_check,
          f"during={sink_during!r} after={sink_of_section()!r}")

    # The scratch parent is CHOSEN AND JUDGED, not probed: this suite writes fixture state roots, a
    # copy of the checkout and run directories, and `tempfile`'s own resolution of `TMPDIR` would put
    # all of it inside a protected root when that is where `TMPDIR` points (R1#5).
    with self_test_scratch() as scratch:
        with section('the fixtures and the first controls'):
            catalog_code = catalog_module(REPO)

            def catalog_item(item_id, kind="guide", text=None, package_id="@fixture/core"):
                """An item in the shape the store writes it, built by the catalog's own builder and validator
                (compose/instructions_catalog.py `_manifest_item`, `_validate_item`), which run offline. A
                baseline's items and a snapshot's `items` (the normalized items the store selected from that
                baseline) are this shape (lead ruling 3, 14:55: a hand-made shape published a broken selection
                catalog from phase 1 on, and no control noticed)."""
                text = text if text is not None else (f"- {item_id}" if kind == "rule" else f"## {item_id}\n\n- a rule\n")
                if kind == "rule":
                    members, primary, source = {"rule.md": text + "\n"}, "rule.md", "claude/CLAUDE.md"
                else:
                    primary = {"guide": f"guides/{item_id}.md", "skill": "SKILL.md", "hook": f"{item_id}.py",
                               "agent": f"agents/{item_id}.md"}[kind]
                    members = {primary: text}
                    source = {"skill": f"claude/skills/{item_id}/SKILL.md", "hook": f"claude/hooks/{item_id}.py"}.get(
                        kind, f"claude/{primary}")
                return catalog_code._validate_item(catalog_code._manifest_item(
                    package_id=package_id, item_id=item_id, title=item_id, body=text, surface=catalog_code._surface_for(kind),
                    tier="env-personal", domains=["personal"], kind=kind, members=members, primary_member=primary,
                    source_path=source), package_id, set())

        with section("done-when 1: the release mapping, against the baseline file's own item list"):
            # ---- done-when 1: the release mapping, against the baseline file's own item list
            baseline = {"schema_version": 1, "packages": [{"package_id": "@fixture/core"}],
                        "items": [catalog_item(f"item-{n}", text=f"## Item {n}\n\n- a rule\n") for n in (1, 2, 3)]}
            check("the fixture's catalog items are the shape the catalog writes: no content conflict, a primary member "
                  "whose text is the body",
                  all("content_conflict" not in item and item["members"].get(item.get("primary_member")) == item["body"]
                      for item in baseline["items"]),
                  f"{[sorted(item) for item in baseline['items']]}")
            # The fixture's roots live under a FIXTURE HOME, and every `run` below is told that home.
            # The manifest projects each root through `masked(root, home)`, so a root under the home the
            # run was given appears as `<HOME>/…` — which is the product property. Two controls used to
            # read the manifest back with RAW paths, so they only worked while the roots happened to sit
            # outside the home `run` read from the process: with `TMPDIR` under the owner's real home,
            # scratch was under it too, the keys were masked, and the suite died with a `KeyError` on
            # the root's raw path before any control ran. Giving the fixture its own home answers that
            # at its cause, and leaves the suite indifferent to where `TMPDIR` points.
            fixture_home = scratch / "home"
            state = fixture_home / "state"
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
            # r4 R4: and such a reason reaches the WRITTEN document through the reference table's rule.
            # It used to be appended to the emitted row afterwards, so it passed no rule at all — and an
            # item ref is a path often enough. The reason this control plants carries a home path, so
            # the published string either shows the projection or shows that it did not happen.
            home_ref = f"@fixture/core:{pathlib.Path.home()}/.claude/an-item-under-the-owners-home"
            late_document, _late_units = emitted_document(
                "release", [{"layer": "catalog", "producer": "a fixture producer", "status": "complete",
                             "reasons": [], "carriers": [guide("mapped.md", "## Rule\n\n- a rule\n")]}],
                {"home": str(pathlib.Path.home()), "state_root": None, "notes": {}, "release_ref": "ref1"},
                more_reasons=lambda units: mapping_problems({home_ref}, units))
            late_out = scratch / "late-reason-out"
            write_document(late_out, late_out / "inventory" / "release.json", late_document,
                           str(pathlib.Path.home()))
            late_published = (late_out / "inventory" / "release.json").read_text(encoding="utf-8")
            control("a mapping reason carrying a home path is projected in the written document",
                    [f"published={late_published}"], "BASELINE_UNMAPPED", "<HOME>")
            check("and that reason named the planted ref while the home path itself is not published",
                  "an-item-under-the-owners-home" in late_published
                  and str(pathlib.Path.home()) not in late_published,
                  f"{late_published[:400]}")
            check("and the reference point says it is incomplete because of it",
                  late_document["reference"]["complete"] is False, f"{late_document['reference']}")
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
            (state / "sessions" / "pins" / "claude" / "hollow.json").write_text(json.dumps(
                {"schema_version": 1, "host": "claude", "session_id": "hollow"}), encoding="utf-8")
            control("a pin that names no snapshot", [str(_raised(lambda: read_pin(state, "claude", "hollow")))],
                    "PIN_UNREADABLE")
        with section("M6: a pin is the session's own only when its record says so. The file sits at the"):
            # ---- M6: a pin is the session's own only when its record says so. The file sits at the
            # session's path; what it NAMES is what decides, as the store's and the census's readers judge.
            pin_dir = state / "sessions" / "pins" / "claude"
            for name, record in (("matched", {"host": "claude", "session_id": "matched"}),
                                 ("other-session", {"host": "claude", "session_id": "someone-else"}),
                                 ("other-host", {"host": "codex", "session_id": "other-host"}),
                                 ("no-identity", {})):
                (pin_dir / f"{name}.json").write_text(json.dumps(
                    {"schema_version": 1, "content_ref": "ref-of-a-snapshot", **record}), encoding="utf-8")
            check("a pin whose record names the session asked for is accepted",
                  (_raised(lambda: read_pin(state, "claude", "matched")) is None
                   and read_pin(state, "claude", "matched")["content_ref"] == "ref-of-a-snapshot"),
                  f"{_raised(lambda: read_pin(state, 'claude', 'matched'))!r}")
            for name in ("other-session", "other-host", "no-identity"):
                control(f"a pin file whose record names another identity: {name}",
                        [str(_raised(lambda name=name: read_pin(state, "claude", name)))], "PIN_IDENTITY_MISMATCH")
            control("a checkout with no catalog loader to read",
                    [str(_raised(lambda: catalog_carriers(scratch / "not-a-checkout")))], "PRODUCER_UNAVAILABLE")
            control("a checkout with no store to resolve the overlays with",
                    [str(_raised(lambda: store_module(scratch / "not-a-checkout")))], "PRODUCER_UNAVAILABLE")

        with section('done-when 2: the native layers answer from the transcript, and no file is read'):
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
            # absolute, and under no directory the floor reads as a home (`/home/<name>/` is one)
            memory_one = f"{scratch}/owner/.claude/projects/{lexical_slug(project_scope)}/memory/one.md"
            main_path = jsonl(scratch / "transcripts" / "claude" / "s-main.jsonl", [
                attachment("2026-10-01T09:00:00+00:00",
                           [member("User", "~/.claude/CLAUDE.md", "# Global\n\n- a native rule\n"),
                            member("Project", f"{project_scope}/CLAUDE.md", "# Project\n\n- a project rule\n"),
                            member("AutoMem", memory_one, "---\nname: one\n---\n\n- a fact\n")],
                           cwd=project_scope,
                           prompt=f"<system-reminder>\n{delivered_body}</system-reminder>\n"),
                {"type": "user", "timestamp": "2026-10-01T09:30:00+00:00", "message": "a turn between the events"},
                attachment("2026-10-01T10:00:00+00:00",
                           [member("User", "~/.claude/CLAUDE.md", "# Global\n\n- a native rule, revised\n"),
                            member("AutoMem", memory_one, "---\nname: one\n---\n\n- a fact\n")],
                           cwd=project_scope)])
            child_path = jsonl(scratch / "transcripts" / "claude" / "s-main" / "subagents" / "s-child.jsonl", [
                attachment("2026-10-02T08:00:00+00:00",
                           [member("User", "~/.claude/CLAUDE.md", "# Global\n\n- what a built-in agent type got\n")],
                           cwd=project_scope)])
            codex_path = jsonl(scratch / "transcripts" / "codex" / "rollout-2026-10-01T09-00-00-aaaa.jsonl", [
                {"type": "session_meta", "timestamp": "2026-10-01T09:00:00+00:00",
                 "payload": {"id": "aaaa", "cwd": project_scope, "git": {"commit_hash": "abc1234"},
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

            def delivered_to(text, *sessions, content_ref="0" * 64):
                """A pins table in which each `host:id` session's own pin was read with a snapshot whose
                compiled text is `text` — what `freeze_inputs` hands `transcript_events`, for a control
                about the transcript and not about the pin."""
                snapshot = {"content_ref": content_ref, "inputs": {}, "items": [], "output": {"instruction_text": text}}
                return {session_ref(*name.split(":", 1)): {
                    "status": "read", "reason": None, "content_ref": content_ref, "record": {"content_ref": content_ref},
                    "include": True, "outcome": None, "detail": None, "code": None, "snapshot": snapshot,
                    "baseline_ref": None, "snapshot_reason": None} for name in sessions}

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
            grown_read = transcript_records(appended)
            read_back, which = grown_read["records"], grown_read["which"]
            check("a transcript the host appended to is read to the census boundary, and says so",
                  len(read_back) == appended["record_count"] and "appended" in which, f"{len(read_back)} record(s), {which}")

            main_events = injection_events(transcript_records(entries["s-main"])["records"], entries["s-main"],
                                           delivered_body)[0]
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
            def in_force_at(when):
                """The event `event_at_instant` names as in force for the main owner at `when`, or None. These
                events come from `injection_events` itself, before `transcript_events` gives them ids, so each
                is named here by its line."""
                numbered = [{**event, "id": str(event["n"])} for event in native_events]
                answer = event_at_instant(numbered, when, (native_events[0] if native_events else {}).get("owner_ref"))
                return next((event for event in native_events if str(event["n"]) == answer["event_ref"]), None) \
                    if answer["state"] == "in_force" else None

            in_force_before = globals_of(in_force_at("2026-10-01T09:30:00+00:00"))
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
                  (in_force_at("2026-10-01T09:30:00+00:00") or {}).get("n")
                  == (native_events[0]["n"] if native_events else None),
                  "a later event answered for an earlier turn")
            check("a turn before every recorded event has no event in force",
                  event_at_instant([{**event, "id": str(event["n"])} for event in native_events],
                                   "2026-10-01T08:00:00+00:00",
                                   (native_events[0] if native_events else {}).get("owner_ref"))["state"]
                  == "no_event_yet",
                  "an event answered for a turn that preceded it")

            all_events, _all_unknown, all_findings = transcript_events(
                run_fixture, delivered_to(delivered_body, "claude:s-main", "claude:s-child"))
            scoped_all = current_scopes(all_events, all_findings["timelines"])
            by_scope = {(row["layer"], row["host"], row["scope"]): row for row in scoped_all["scopes"]}
            check("the current reference point resolves per layer, host and scope",
                  {key[0] for key in by_scope} == set(SCOPED_LAYERS), f"{sorted({key[0] for key in by_scope})}")
            check("a subagent's injection is not evidence about the current state",
                  {row["session"] for row in scoped_all["scopes"]} <= {None, "claude:s-main", "codex:aaaa"}
                  and {row["host"]: row["ineligible"] for row in scoped_all["universe"]}.get("claude") == 1,
                  "a subagent event was taken for the current reference point")
            global_row = by_scope.get(("native_global", "claude", None)) or {}
            check("the newest recorded event answers for its scope",
                  global_row.get("status") == "answered" and global_row.get("as_of") == "2026-10-01T10:00:00+00:00",
                  f"{global_row.get('status')} {global_row.get('as_of')}")
            # Replaces the control that REQUIRED the fall-back to the event that last carried the project
            # file (#6): the newest event's whole set answers, so the deletion shows as an empty scope.
            project_row = by_scope.get(("native_project", "claude", project_scope)) or {}
            check("the whole set of one event answers, never the newest event per path: the project scope is "
                  "empty as of the event that no longer carries its file",
                  project_row.get("status") == "empty" and project_row.get("as_of") == "2026-10-01T10:00:00+00:00",
                  f"{project_row.get('status')} {project_row.get('as_of')}")
            codex_events = [event for event in all_events if event["host"] == "codex"]
            check("Codex is one undivided block at its own layer value, with no global/project split derived from it",
                  [member_row["layer"] for member_row in codex_events[0]["files"]] == ["native_undivided"]
                  and codex_events[0]["files"][0]["undivided"]
                  and by_scope.get(("native_global", "codex", None), {}).get("reasons", [{}])[0].get("reason")
                  == "codex_undivided"
                  and by_scope.get(("native_undivided", "codex", project_scope), {}).get("status") == "answered",
                  f"{[member_row['layer'] for member_row in codex_events[0]['files']]}")
            def carriers_of(layer, event):
                """`event_carriers`, or [] when it refuses: a control over a carrier fails by its own
                name instead of ending the suite (a planted undeclared form refuses every one)."""
                try:
                    return event_carriers(layer, event, "current")
                except Exception:
                    return []

            codex_carrier = (carriers_of("native_undivided", codex_events[0]) or [{"provenance": {}}])[0]
            check("a Codex carrier says its identity is unknown",
                  "loaded text" in str(codex_carrier["provenance"].get("identity")),
                  f"{codex_carrier['provenance']}")
            global_event = (scoped_all["answers"].get(global_row.get("scope_id")) or {}).get("event") or {}
            carriers_out = carriers_of("native_global", global_event) if global_event else []
            check("a native carrier carries when and from whom it came",
                  bool(carriers_out) and carriers_out[0]["provenance"]["as_of"] == global_event["at"]
                  and carriers_out[0]["provenance"]["session"] == "claude:s-main",
                  f"{carriers_out[0]['provenance'] if carriers_out else 'no carrier'}")

            # ======== WP-07 package B, phase 1: acquisition and decoding of the transcripts ========
            def bound_row(host, ident, path, **fields):
                """A census row bound to `path` as it is now, by both binding kinds, with `fields` over it."""
                return {**census_row(host, ident, path), **fields}

            def raw_lines(path, rows):
                """A transcript whose lines are written as given: a dict becomes its JSON, bytes stay bytes."""
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"".join((row if isinstance(row, bytes) else json.dumps(row).encode()) + b"\n"
                                          for row in rows))
                return path

            def opened_while(call):
                """`(result or the exception, the paths sources.read_lines was asked for)` during `call`."""
                asked, kept_reader = [], sources.read_lines
                try:
                    sources.read_lines = lambda path, zstd=None: (asked.append(str(path)), kept_reader(path, zstd))[1]
                    try:
                        outcome = call()
                    except Exception as exc:
                        outcome = exc
                finally:
                    sources.read_lines = kept_reader
                return outcome, asked

            def dated(at, text="# Global\n\n- a rule\n", **extra):
                return {**attachment(at, [member("User", "~/.claude/CLAUDE.md", text)], cwd=project_scope), **extra}

        with section('#9: a transcript is opened only under a binding, and an unbound row says so unopened'):
            # ---- #9: a transcript is opened only under a binding, and an unbound row says so unopened
            unbound_path = raw_lines(scratch / "p1" / "unbound.jsonl", [dated("2026-10-05T09:00:00+00:00")])
            unbound_row = {"host": "claude", "id": "s-unbound", "path": str(unbound_path), "status": "child_of",
                           "parent": "s-main", "sha256": None, "versions": []}
            outcome, asked = opened_while(lambda: transcript_records(
                {**census_row("claude", "s-unbound", unbound_path), "sha256": None, "prefix_sha": None, "record_count": None}))
            check("an unbound census row is never opened, and carries its reason",
                  isinstance(outcome, Unacquired) and UNKNOWN_REASONS["unbound"] in str(outcome) and not asked,
                  f"unacquired={isinstance(outcome, Unacquired)} opened={len(asked)}")
            unbound_run = scratch / "p1" / "run-unbound"
            unbound_run.mkdir(parents=True)
            (unbound_run / CENSUS).write_text(json.dumps({"transcripts": [unbound_row]}), encoding="utf-8")
            outcome, asked = opened_while(lambda: transcript_events(unbound_run))
            check("and through the run's own path: the row is a named unknown and its file was not opened",
                  not isinstance(outcome, Exception) and not asked
                  and any(UNKNOWN_REASONS["unbound"] in row for row in outcome[1]),
                  f"raised={isinstance(outcome, Exception)} opened={len(asked)}")
            grown_whole = raw_lines(scratch / "p1" / "whole.jsonl", [dated("2026-10-05T09:00:00+00:00")])
            whole_only = {"host": "claude", "id": "s-whole", "path": str(grown_whole),
                          "sha256": hashlib.sha256(grown_whole.read_bytes()).hexdigest()}
            check("a whole-file binding alone binds the file it hashed",
                  len(transcript_records(whole_only)["records"]) == 1, "the whole-file binding did not read its file")
            with grown_whole.open("ab") as handle:
                handle.write(json.dumps(dated("2026-10-05T10:00:00+00:00")).encode() + b"\n")
            check("and a whole-file binding alone refuses a file that no longer matches it",
                  UNKNOWN_REASONS["changed"] in str(_raised(lambda: transcript_records(whole_only))),
                  f"{type(_raised(lambda: transcript_records(whole_only))).__name__}")
            prefix_path = raw_lines(scratch / "p1" / "prefix.jsonl", [dated("2026-10-05T09:00:00+00:00"),
                                                                     dated("2026-10-05T10:00:00+00:00")])
            first_line = prefix_path.read_bytes().split(b"\n", 1)[0] + b"\n"
            prefix_only = {"host": "claude", "id": "s-prefix", "path": str(prefix_path), "sha256": None,
                           "prefix_sha": hashlib.sha256(first_line).hexdigest(), "record_count": 1}
            prefix_read = transcript_records(prefix_only)
            check("a complete-line prefix alone binds the lines it counts and no more",
                  [line for line, _record in prefix_read["records"]] == [1], f"{[line for line, _ in prefix_read['records']]}")
            check("and a prefix alone refuses a file whose prefix no longer matches it",
                  UNKNOWN_REASONS["changed"] in str(_raised(lambda: transcript_records(
                      {**prefix_only, "prefix_sha": hashlib.sha256(b"other bytes\n").hexdigest()}))),
                  "a mismatched prefix was read")
            for label, broken in (("a whole-file hash that is not a hash", {"sha256": "not-a-hash"}),
                                  ("a prefix with no line count", {"prefix_sha": "0" * 64, "record_count": None}),
                                  ("a line count with no prefix", {"prefix_sha": None, "record_count": 3}),
                                  ("a line count that is a boolean", {"prefix_sha": "0" * 64, "record_count": True})):
                outcome, asked = opened_while(lambda broken=broken: transcript_records({**prefix_only, "sha256": None, **broken}))
                check(f"a binding that is there but malformed is refused as that binding: {label}",
                      isinstance(outcome, Unacquired) and UNKNOWN_REASONS["binding_invalid"] in str(outcome) and not asked,
                      f"unacquired={isinstance(outcome, Unacquired)} opened={len(asked)}")
            # Kind per ROW, from lineage. Every child below is BOUND and DATED, so each would qualify for
            # `current` as a main row: the `unbound` guard cannot be what keeps them out.
            kinds_run = scratch / "p1" / "run-kinds"
            kinds_run.mkdir(parents=True)
            child_rows = {
                "orphan": bound_row("claude", "s-orphan", raw_lines(scratch / "p1" / "orphan.jsonl",
                                                                    [dated("2026-10-06T09:00:00+00:00")]),
                                    status="unknown_provenance", reason="orphan_child", entrypoint="sidechain"),
                "without-parent": bound_row("claude", "s-without", raw_lines(scratch / "p1" / "without.jsonl",
                                                                              [dated("2026-10-06T10:00:00+00:00")]),
                                            status="unknown_provenance", reason="child_without_parent"),
                "codex-cli": bound_row("codex", "c-child", raw_lines(scratch / "p1" / "codex-child.jsonl", [
                    {"type": "session_meta", "timestamp": "2026-10-06T11:00:00+00:00",
                     "payload": {"id": "c-child", "cwd": project_scope, "source": "cli",
                                 "base_instructions": {"text": "# Child\n\n- a child's block\n"}}}]),
                                       status="unknown_provenance", reason="child_without_parent", entrypoint="cli"),
            }
            (kinds_run / CENSUS).write_text(json.dumps({"transcripts": list(child_rows.values())}), encoding="utf-8")
            kind_of = {row["id"]: row["kind"] for row in census_entries(kinds_run)}
            kind_events, kind_unknown, _kind_findings = transcript_events(kinds_run)
            check("the bound, dated children really record an event each, so the kind is what is judged",
                  len([event for event in kind_events if event["kind"] == "native"]) == 3 and not kind_unknown,
                  f"events={len(kind_events)} unknown={len(kind_unknown)}")
            for label, row in child_rows.items():
                check(f"a child row is a subagent by its lineage: {label}", kind_of.get(row["id"]) == "subagent",
                      f"{kind_of.get(row['id'])}")
            check("and none of those children's events answers for the current reference point",
                  current_scopes(kind_events)["scopes"] == [],
                  f"{len(current_scopes(kind_events)['scopes'])} scope(s)")
            # Kind per RECORD: an inline sidechain inside a bound main file (lineage.py 102-105).
            plain_main = raw_lines(scratch / "p1" / "plain-main.jsonl", [
                {"type": "user", "timestamp": "2026-10-06T08:00:00+00:00", "isSidechain": False},
                dated("2026-10-06T09:00:00+00:00", "# Global\n\n- the main session's rule\n")])
            side_main = raw_lines(scratch / "p1" / "side-main.jsonl", [
                {"type": "user", "timestamp": "2026-10-06T08:00:00+00:00", "isSidechain": False},
                dated("2026-10-06T09:00:00+00:00", "# Global\n\n- the main session's rule\n"),
                dated("2026-10-06T12:00:00+00:00", "# Global\n\n- what the sidechain's agent type got\n",
                      isSidechain=True, agentId="a1"),
                dated("2026-10-06T12:30:00+00:00", "# Global\n\n- an agent that names itself only\n", agentId="a2")])

            def own_and_current(path, ident):
                run_at = scratch / "p1" / f"run-own-{path.stem}"
                run_at.mkdir(parents=True, exist_ok=True)
                (run_at / CENSUS).write_text(json.dumps({"transcripts": [bound_row("claude", ident, path)]}),
                                             encoding="utf-8")
                found = transcript_events(run_at)[0]
                own = [(event["n"], globals_of(event)) for event in found if event["session"] == f"claude:{ident}"]
                scoped = current_scopes(found)
                return own, {(row["layer"], row["scope"]): (row["status"], row["as_of"], row["line"], sorted(
                    member["text"] for member in (scoped["answers"].get(row["scope_id"]) or {}).get("members", [])))
                    for row in scoped["scopes"]}, found

            plain_own, plain_current, _plain = own_and_current(plain_main, "s-side")
            side_own, side_current, side_found = own_and_current(side_main, "s-side")
            check("a bound main file's inline sidechain attachment leaves current unchanged",
                  side_current == plain_current and bool(plain_current), f"same={side_current == plain_current}")
            check("and leaves the main session's own events unchanged",
                  side_own == plain_own and len(side_own) == 1, f"own={len(side_own)} same={side_own == plain_own}")
            check("and the sidechain's events are its own, never the main session's",
                  sorted(event["session"] for event in side_found if event["session"] != "claude:s-side")
                  == ["claude:s-side#sidechain:a1", "claude:s-side#sidechain:a2"]
                  and all(event["transcript"] == "subagent" for event in side_found if "#sidechain:" in event["session"]),
                  f"{sorted(event['session'].rpartition('#')[2] for event in side_found)}")

        with section("#10: the census boundary is a count of LINES, and the line is the event's position"):
            # ---- #10: the census boundary is a count of LINES, and the line is the event's position
            undecodable_rows = [dated("2026-10-07T09:00:00+00:00"), b"{a complete line that is not JSON",
                                b"[\"a JSON line\", \"that is not an object\"]", dated("2026-10-07T10:00:00+00:00")]
            cut_path = raw_lines(scratch / "p1" / "cut.jsonl", undecodable_rows)
            census_prefix = hashlib.sha256(cut_path.read_bytes()).hexdigest()
            with cut_path.open("ab") as handle:
                handle.write(json.dumps(dated("2026-10-07T11:00:00+00:00", "# Global\n\n- appended after the census\n")).encode()
                             + b"\n")
            cut_row = {"host": "claude", "id": "s-cut", "path": str(cut_path), "kind": "main", "sha256": "1" * 64,
                       "prefix_sha": census_prefix, "record_count": 4}
            cut_read = transcript_records(cut_row)
            cut_events = injection_events(cut_read["records"], cut_row)[0]
            check("appended records are excluded after a prefix holding a malformed and a non-object line",
                  [event["n"] for event in cut_events] == [1, 4]
                  and not any("appended after" in text for event in cut_events for text in globals_of(event)),
                  f"lines={[event['n'] for event in cut_events]}")
            still_path = raw_lines(scratch / "p1" / "still.jsonl", [b"{not json", b"7", dated("2026-10-07T09:00:00+00:00")])
            still_row = {**bound_row("claude", "s-still", still_path), "kind": "main"}
            still_events = injection_events(transcript_records(still_row)["records"], still_row)[0]
            check("on an unchanged file, an event after such lines carries its raw-line position",
                  [event["n"] for event in still_events] == [3], f"{[event['n'] for event in still_events]}")
            zero_read = _raised(lambda: transcript_records({**cut_row, "prefix_sha": hashlib.sha256(b"").hexdigest(),
                                                            "record_count": 0}))
            check("a zero-line census prefix binds a transcript the host has written to since",
                  zero_read is None and transcript_records({**cut_row, "prefix_sha": hashlib.sha256(b"").hexdigest(),
                                                            "record_count": 0})["records"] == [],
                  f"{type(zero_read).__name__}")

        with section('#13: a transcript carrier is split by its own form, and the form set is closed'):
            # ---- #13: a transcript carrier is split by its own form, and the form set is closed
            control("carrier() refuses a form outside the closed set",
                    [str(_raised(lambda: carrier("native_global", "claude:User:x.md", "# H\n\n- r\n", form="md")))],
                    "CARRIER_FORM_UNDECLARED")
            control("blocks_of refuses a form outside the closed set over non-empty text",
                    [str(_raised(lambda: blocks_of("x.md", "# H\n\n- r\n", "md")))], "CARRIER_FORM_UNDECLARED")
            control("blocks_of refuses a form outside the closed set over empty text",
                    [str(_raised(lambda: blocks_of("x.md", "", "md")))], "CARRIER_FORM_UNDECLARED")
            headed_event = {"kind": "native", "host": "claude", "at": "2026-10-07T09:00:00+00:00", "n": 1,
                            "session": "claude:s-headed", "transcript": "main", "scope": project_scope,
                            "where": "attachment.files[] by type",
                            "files": [{"layer": "native_project", "type": "Project", "path": f"{project_scope}/CLAUDE.md",
                                       "text": "# Working here\n\n- a rule under the heading\n"}]}
            try:  # a refusal here fails this control by name rather than the suite
                headed_units = operative_context(units_of(event_carriers("native_project", headed_event, "current")))
            except Exception:
                headed_units = []
            heading_ids = [unit["unit_id"] for unit in headed_units if unit["block"] == "heading"]
            rule_units = [unit for unit in headed_units if "a rule under" in unit["text"]]
            check("a transcript CLAUDE.md carrier's rule holds its heading unit in its operative context, by identity",
                  len(heading_ids) == 1 and len(rule_units) == 1 and heading_ids[0] in rule_units[0]["operative_context"],
                  f"headings={len(heading_ids)} rules={len(rule_units)}")

        with section('#5: the shapes real records and pins carry, and none that raises'):
            # ---- #5: the shapes real records and pins carry, and none that raises
            moment = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=datetime.timezone.utc)
            check("a numeric instant and an offset-equivalent ISO instant parse to the same moment",
                  _instant(moment.timestamp()) == _instant("2026-10-01T18:00:00+09:00") == _instant("2026-10-01T09:00:00Z")
                  == moment, f"numeric={_instant(moment.timestamp()) == moment}")
            check("a record's numeric timestamp is read, a boolean one is not",
                  _timestamp({"timestamp": int(moment.timestamp())}) == int(moment.timestamp())
                  and _timestamp({"timestamp": True}) is None, "a numeric record timestamp was ignored")
            mixed_events = [{"kind": "native", "transcript": "main", "host": "claude", "at": at, "n": 1,
                             "session": f"claude:{ident}", "session_ref": session_ref("claude", ident),
                             "id": opaque_id("e", "event", "native", "claude", ident, None, 1),
                             "scope": project_scope, "cwd_case": "scoped", "rejected": [], "unmapped": False,
                             "damaged": None, "at_reason": instant_reason(at), "after_at": None, "bracket_ok": True,
                             "files": [{"layer": "native_global", "type": "User", "path": "/g", "text": "- r\n"}]}
                            for ident, at in (("s-naive", "2026-10-01T09:00:00"), ("s-aware", "2026-10-01T10:00:00+00:00"))]
            check("a tz-less instant beside an aware one raises nothing, and is unsupported",
                  _raised(lambda: current_scopes(mixed_events)) is None
                  and _raised(lambda: event_at_instant(mixed_events, moment.timestamp(), None)) is None
                  and _instant("2026-10-01T09:00:00") is None, "a naive instant raised or was guessed")
            shapes = [None, True, False, "", "yesterday", "2026-10-01", float("nan"), float("inf"), -float("inf"),
                      10 ** 30, -10 ** 30, [], {}, b"2026"]
            check("no instant shape raises", all(_raised(lambda shape=shape: _instant(shape)) is None
                                                and _instant(shape) is None for shape in shapes),
                  f"{[type(shape).__name__ for shape in shapes if _raised(lambda shape=shape: _instant(shape)) is not None]}")

        with section('M2: damage by level, usable evidence kept, every rejection a category and a number'):
            # ---- M2: damage by level, usable evidence kept, every rejection a category and a number
            raised_marker = object()

            def decoded(records_in, entry_in, delivered_in=None):
                """`injection_events`, or the marker when it raised: a control whose input makes it raise
                fails by its own name instead of ending the suite."""
                try:
                    return injection_events(records_in, entry_in, delivered_in)
                except Exception:
                    return raised_marker

            canary = "a-type-a-host-wrote-" + "Ab3" * 4
            damaged_entry = {"host": "claude", "id": "s-damaged", "kind": "main"}
            mixed = decoded([(5, {"type": "attachment", "timestamp": "2026-10-08T09:00:00Z",
                                  "attachment": {"type": "instructions", "files": [
                member("User", "~/.claude/CLAUDE.md", "# G\n\n- kept\n"), member(canary, "elsewhere.md", "- unmapped\n"),
                {"type": "Project", "path": "p.md", "content": 3}, "a member that is not an object"]}})], damaged_entry)
            mixed_found, mixed_damage, _mixed_inherited = ([], [], []) if mixed is raised_marker else mixed
            mixed_native = [event for event in mixed_found if event["kind"] == "native"]
            check("a member of an unmapped type is rejected and counted, and the usable members stay",
                  mixed is not raised_marker and len(mixed_native) == 1 and [row["path"] for row in mixed_native[0]["files"]] == ["~/.claude/CLAUDE.md"]
                  and [(row["ordinal"], row["category"]) for row in mixed_native[0]["rejected"]]
                  == [(1, "member_type_unmapped"), (2, "member_content_invalid"), (3, "member_not_object")]
                  and mixed_native[0]["unmapped"] is True and not mixed_damage,
                  f"raised={mixed is raised_marker} "
                  f"{[(row['ordinal'], row['category']) for event in mixed_native for row in event.get('rejected', [])]}")
            check("a rejection names a fixed category and a number, never what the host wrote",
                  mixed is not raised_marker
                  and canary not in json.dumps([event.get("rejected") for event in mixed_found] + mixed_damage),
                  f"raised={mixed is raised_marker} or the rejected member's type string reached the rejection")
            raising_shapes = {
                "files is a number": {"type": "attachment", "attachment": {"type": "instructions", "files": 5}},
                "files is a boolean": {"type": "attachment", "attachment": {"type": "instructions", "files": True}},
                "files is a string": {"type": "attachment", "attachment": {"type": "instructions", "files": "x"}},
                "files is an object": {"type": "attachment", "attachment": {"type": "instructions", "files": {"a": 1}}},
                "a member's type is a list": {"type": "attachment", "attachment": {"type": "instructions", "files": [
                    {"type": ["User"], "path": "a", "content": "b"}]}},
                "systemPrompt is a number": {"type": "attachment", "attachment": {"type": "x", "systemPrompt": 7}},
                "shape.system is a number": {"type": "request", "shape": {"system": 3}},
                "a Codex block of another shape": {"type": "session_meta", "payload": {"id": "s-shape",
                                                                                        "base_instructions": ["x"]}},
            }
            expected_damage = {"files is a number": ["container_unusable"], "files is a boolean": ["container_unusable"],
                               "files is a string": ["container_unusable"], "files is an object": ["container_unusable"],
                               "a member's type is a list": [], "systemPrompt is a number": ["locator_unusable"],
                               "shape.system is a number": ["locator_unusable"],
                               "a Codex block of another shape": ["container_unusable"]}
            for label, record in raising_shapes.items():
                entry_for = {"host": "codex" if "Codex" in label else "claude", "id": "s-shape", "kind": "main"}
                shaped = decoded([(2, record)], entry_for, "a body")
                found_for, damage_for, _inherited_for = ([], [], []) if shaped is raised_marker else shaped
                check(f"a shape that used to raise is a counted rejection: {label}",
                      shaped is not raised_marker and [row["category"] for row in damage_for] == expected_damage[label]
                      and all(row["line"] == 2 for row in damage_for),
                      f"raised={shaped is raised_marker} damage={[row['category'] for row in damage_for]}")
            listed = decoded([(2, raising_shapes["a member's type is a list"])], damaged_entry)
            check("and the list-valued type is a member rejection on its event, not a lost event",
                  listed is not raised_marker
                  and [row["category"] for event in listed[0] for row in event.get("rejected", [])] == ["member_type_unmapped"],
                  f"raised={listed is raised_marker} or the member with a list-valued type was not counted")
            handled_run = scratch / "p1" / "run-handled"
            handled_run.mkdir(parents=True)
            good_path = raw_lines(scratch / "p1" / "good.jsonl", [dated("2026-10-08T09:00:00+00:00")])
            (handled_run / CENSUS).write_text(json.dumps({"transcripts": [
                census_row("claude", "s-fails", good_path), census_row("claude", "s-good", good_path)]}), encoding="utf-8")
            kept_events_reader = globals()["injection_events"]

            def failing_for_one(records_in, entry_in, delivered_in=None, *rest):
                if entry_in.get("id") == "s-fails":
                    raise Unacquired(f"{UNKNOWN_REASONS['unreadable']}: a planted failure processing one transcript")
                return kept_events_reader(records_in, entry_in, delivered_in, *rest)

            try:
                globals()["injection_events"] = failing_for_one
                handled = _raised(lambda: transcript_events(handled_run))
                handled_out = None if handled else transcript_events(handled_run)
            finally:
                globals()["injection_events"] = kept_events_reader
            check("a transcript that cannot be processed is that session's unknown, and the others still process",
                  handled is None and handled_out is not None
                  and [row.split(":", 2)[1] for row in handled_out[1]] == ["s-fails"]
                  and {event["session"] for event in handled_out[0]} == {"claude:s-good"},
                  f"raised={type(handled).__name__ if handled else None}")

        with section('M3: each source by its own discriminator, and lookalikes are not deliveries'):
            # ---- M3: each source by its own discriminator, and lookalikes are not deliveries
            body_text = "- the compiled body\n"
            for label, record in (
                    ("a user record carrying an instructions attachment",
                     {"type": "user", "attachment": {"type": "instructions",
                                                     "files": [member("User", "~/.claude/CLAUDE.md", "- x\n")]}}),
                    ("an attachment record whose attachment is not an object",
                     {"type": "attachment", "attachment": [{"type": "instructions"}]})):
                looked = decoded([(1, record)], damaged_entry)
                check(f"a lookalike is no native event: {label}",
                      looked is not raised_marker and looked[0] == [],
                      f"raised={looked is raised_marker} or a lookalike made an event")
            codex_entry = {"host": "codex", "id": "c-look", "kind": "main"}
            # each lookalike names the rollout's own id, so the source discriminator is what refuses it, not M10
            for label, record in (("an event record carrying base_instructions",
                                   {"type": "event_msg", "payload": {"id": "c-look", "base_instructions": {"text": "- x\n"}}}),
                                  ("a session_meta whose payload is not an object",
                                   {"type": "session_meta", "payload": [{"id": "c-look", "base_instructions": "- x\n"}]})):
                looked = decoded([(1, record)], codex_entry)
                check(f"a lookalike is no Codex block: {label}",
                      looked is not raised_marker and looked[0] == [],
                      f"raised={looked is raised_marker} or a lookalike made a Codex event")
            admitted = decoded([(1, {"type": "session_meta", "payload": {"id": "c-look", "base_instructions": "- x\n"}})],
                               codex_entry)
            check("a Codex session_meta with its block is the event the lookalikes are not",
                  admitted is not raised_marker and len(admitted[0]) == 1,
                  f"raised={admitted is raised_marker} or the admitted Codex source made no event")
            check("a systemPrompt locates the body only on an attachment record",
                  _located({"type": "user", "attachment": {"systemPrompt": [f"<r>{body_text}</r>"]}}, body_text) is None
                  and (_located({"type": "attachment", "attachment": {"systemPrompt": [f"<r>{body_text}</r>"]}},
                                body_text) or ("",))[0] == "attachment.systemPrompt[]",
                  "a non-attachment record located the body, or an attachment did not")
            check("the request-shape body stays its own admitted case",
                  (_located({"type": "request", "shape": {"system": [{"text": f"<r>{body_text}</r>"}]}}, body_text)
                   or ("",))[0] == "shape.system[].text", "the request shape no longer located the body")

        with section("M10: a child or fork rollout carries its parent's session_meta, which is not its injection"):
            # ---- M10: a child or fork rollout carries its parent's session_meta, which is not its injection
            shared_block = {"text": "# Codex\n\n- the block parent and fork both carry\n"}

            def codex_meta(ident, at, **payload):
                return {"type": "session_meta", "timestamp": at,
                        "payload": {**({"id": ident} if ident is not None else {}), "cwd": project_scope,
                                    "base_instructions": shared_block, **payload}}

            m10_cases = {
                # (records, the events' lines, the inherited rows)
                "a fork-shaped rollout": (
                    [codex_meta("c-fork", "2026-10-09T10:00:00+00:00", forked_from_id="c-parent"),
                     codex_meta("c-parent", "2026-10-09T08:00:00+00:00")],
                    [1], [{"session": "codex:c-fork", "line": 2, "category": "another_session_id"}]),
                "a parent's record before the rollout's own": (
                    [codex_meta("c-parent", "2026-10-09T08:00:00+00:00"),
                     codex_meta("c-fork", "2026-10-09T10:00:00+00:00", source={"subagent": "review"})],
                    [2], [{"session": "codex:c-fork", "line": 1, "category": "another_session_id"}]),
                "a session_meta naming no session": (
                    [codex_meta("c-fork", "2026-10-09T10:00:00+00:00"), codex_meta(None, "2026-10-09T08:00:00+00:00")],
                    [1], [{"session": "codex:c-fork", "line": 2, "category": "no_session_id"}]),
                "a rollout with one session_meta": (
                    [codex_meta("c-fork", "2026-10-09T10:00:00+00:00")], [1], []),
                # census takes the file name's id when the head names none (census.py ~225), and a later
                # session_meta can carry exactly that id: every record is tested, not only the first
                "an id-less head followed by the rollout's own": (
                    [codex_meta(None, "2026-10-09T08:00:00+00:00"), codex_meta("c-fork", "2026-10-09T10:00:00+00:00")],
                    [2], [{"session": "codex:c-fork", "line": 1, "category": "no_session_id"}]),
            }
            for label, (rows_for, event_lines, inherited_rows) in m10_cases.items():
                slug = "-".join(label.split()[:4]).replace("'", "")
                m10_path = raw_lines(scratch / "p1" / f"m10-{slug}.jsonl", rows_for)
                m10_run = scratch / "p1" / f"run-m10-{slug}"
                m10_run.mkdir(parents=True)
                (m10_run / CENSUS).write_text(json.dumps({"transcripts": [census_row("codex", "c-fork", m10_path)]}),
                                              encoding="utf-8")
                outcome = _raised(lambda m10_run=m10_run: transcript_events(m10_run))
                m10_events, _m10_unknown, m10_findings = ([], [], {}) if outcome else transcript_events(m10_run)
                check(f"only the rollout's own session_meta is its event: {label}",
                      outcome is None and [event["n"] for event in m10_events] == event_lines
                      and {event["session"] for event in m10_events} == {"codex:c-fork"},
                      f"raised={outcome is not None} lines={[event['n'] for event in m10_events]}")
                check(f"and every other session_meta is counted as inherited: {label}",
                      outcome is None and m10_findings.get("inherited") == inherited_rows,
                      f"raised={outcome is not None} inherited={len(m10_findings.get('inherited') or [])}")
                m10_ctx = {"notes": {}}
                bound_outcome = _raised(lambda m10_ctx=m10_ctx, m10_run=m10_run: bind_transcripts(m10_ctx, m10_run))
                check(f"and the run's notes carry the inherited count: {label}",
                      bound_outcome is None
                      and m10_ctx["notes"].get("transcripts", {}).get("inherited") == inherited_rows,
                      f"raised={bound_outcome is not None}")

        with section('P2.1: events as published records (step 0 S-1, S-3, S-4, S-5, S-11, S-14, S-23, M9)'):
            # ---- P2.1: events as published records (step 0 S-1, S-3, S-4, S-5, S-11, S-14, S-23, M9)
            def p2_run(name, rows_by_id, delivered_in=None):
                """A run directory whose census holds the given rows, and its transcript events."""
                run_at = scratch / "p2" / f"run-{name}"
                run_at.mkdir(parents=True)
                (run_at / CENSUS).write_text(json.dumps({"transcripts": list(rows_by_id)}), encoding="utf-8")
                try:
                    events_out, _unknown_out, findings_out = transcript_events(run_at, delivered_to(
                        delivered_in, *[f"{row['host']}:{row['id']}" for row in rows_by_id]) if delivered_in else None)
                except Exception as exc:  # the control fails by its own name instead of ending the suite
                    return run_at, exc, [], {"sessions": []}
                return run_at, None, events_out, findings_out

            def session_of(findings_out, ident):
                return next((row for row in findings_out["sessions"] if row["transcript"]["id"] == ident), None)

            # S-4: the census's own sidechain test
            null_agent = raw_lines(scratch / "p2" / "null-agent.jsonl", [
                dated("2026-10-11T09:00:00+00:00", agentId=""), dated("2026-10-11T10:00:00+00:00", agentId=None),
                dated("2026-10-11T11:00:00+00:00", agentId=7)])
            _r, failed, events_na, findings_na = p2_run("null-agent", [census_row("claude", "s-na", null_agent)])
            record_na = session_of(findings_na, "s-na") or {}
            check("an empty, null or non-string agentId beside no isSidechain leaves the record the main session's, "
                  "counted",
                  failed is None and [event["transcript"] for event in events_na] == ["main", "main", "main"]
                  and {event["owner_ref"] for event in events_na} == {owner_ref("claude", "s-na")}
                  and [row for row in record_na.get("limitations", []) if row["kind"] == "agent_id_unusable"]
                  == [{"kind": "agent_id_unusable", "count": 3, "line": 1}],
                  f"raised={failed is not None} kinds={[event['transcript'] for event in events_na]}")
            unnamed = raw_lines(scratch / "p2" / "unnamed.jsonl", [
                dated("2026-10-11T09:00:00+00:00"),
                dated("2026-10-11T10:00:00+00:00", "# Global\n\n- one child\n", isSidechain=True),
                dated("2026-10-11T11:00:00+00:00", "# Global\n\n- another child\n", isSidechain=True)])
            _r, failed, events_un, findings_un = p2_run("unnamed", [census_row("claude", "s-un", unnamed)])
            strays = [event for event in events_un if event["transcript"] == "subagent"]
            record_un = session_of(findings_un, "s-un") or {}
            check("a sidechain record that names no agent has no owner, and two of them are never one timeline",
                  failed is None and len(strays) == 2 and all(event["owner_ref"] is None for event in strays)
                  and all(event["interval"] is None for event in strays)
                  and [row for row in record_un.get("unknown", []) if row["reason"] == "ownership_unknown"]
                  == [{"reason": "ownership_unknown", "line": 2}, {"reason": "ownership_unknown", "line": 3}]
                  and record_un.get("ownership", {}).get("unknown") == [{"from": 2, "to": 4}],
                  f"raised={failed is not None} strays={len(strays)}")
            twins = raw_lines(scratch / "p2" / "twins.jsonl", [
                dated("2026-10-11T09:00:00+00:00", agentId="token=" + "A" * 24 + "1"),
                dated("2026-10-11T10:00:00+00:00", agentId="token=" + "B" * 24 + "2")])
            twins_run, failed, events_tw, findings_tw = p2_run("twins", [census_row("claude", "s-tw", twins)])
            twins_doc = sessions_document({"home": None, "commit": None, "sessions": findings_tw["sessions"],
                                           "events": events_tw})
            published_owners = [row["owner_ref"] for row in twins_doc["events"]]
            check("two owners whose display values project to one string keep distinct owner_refs after publication",
                  failed is None and len(published_owners) == 2 and len(set(published_owners)) == 2
                  and len({row["owner"] for row in twins_doc["events"]}) == 1,
                  f"raised={failed is not None} refs={len(set(published_owners))} "
                  f"displays={len({row['owner'] for row in twins_doc['events']})}")
            check("and the agent ids a host wrote pass the floor in the published document",
                  ("A" * 24) not in json.dumps(twins_doc) and ("B" * 24) not in json.dumps(twins_doc),
                  "a raw agent id reached sessions.json")

            # S-1 / S-5: an unusable container is a damaged event that opens its own interval
            damaged_path = raw_lines(scratch / "p2" / "damaged.jsonl", [
                dated("2026-10-12T09:00:00+00:00"),
                {"type": "attachment", "timestamp": "2026-10-12T10:00:00+00:00", "cwd": project_scope,
                 "attachment": {"type": "instructions", "files": 5}},
                dated("2026-10-12T11:00:00+00:00")])
            _r, failed, events_dm, findings_dm = p2_run("damaged", [census_row("claude", "s-dm", damaged_path)])
            record_dm = session_of(findings_dm, "s-dm") or {}
            check("an unusable instructions container is a damaged event at its line, opening its own interval",
                  failed is None and [(event["n"], event["damaged"], event["interval"]) for event in events_dm]
                  == [(1, None, [1, 2]), (2, "container_unusable", [2, 3]), (3, None, [3, 4])]
                  and {"kind": "damaged", "category": "container_unusable", "line": 2} in record_dm.get("limitations", [])
                  and {"reason": "container_unusable", "line": 2} in record_dm.get("unknown", []),
                  f"raised={failed is not None} {[(event['n'], event['damaged'], event['interval']) for event in events_dm]}")
            own_damaged = raw_lines(scratch / "p2" / "own-damaged.jsonl", [
                {"type": "session_meta", "timestamp": "2026-10-12T09:00:00+00:00",
                 "payload": {"id": "c-own", "cwd": project_scope, "base_instructions": ["not a block"]}}])
            _r, failed, events_od, findings_od = p2_run("own-damaged", [census_row("codex", "c-own", own_damaged)])
            check("an own Codex session_meta whose block has another shape is a damaged native event, never inherited",
                  failed is None and [(event["kind"], event["damaged"]) for event in events_od]
                  == [("native", "container_unusable")]
                  and (session_of(findings_od, "c-own") or {}).get("inherited_session_meta")
                  == {"another_session_id": 0, "no_session_id": 0},
                  f"raised={failed is not None} {[(event['kind'], event['damaged']) for event in events_od]}")
            body = "- the compiled body\n"
            locator_rows = [
                (1, {"type": "attachment", "timestamp": "2026-10-12T09:00:00+00:00",
                     "attachment": {"type": "other", "systemPrompt": 5}}),
                (2, {"type": "attachment", "timestamp": "2026-10-12T10:00:00+00:00",
                     "attachment": {"type": "other", "systemPrompt": [3, "<r>another field</r>"]}}),
                (3, {"type": "attachment", "timestamp": "2026-10-12T11:00:00+00:00",
                     "attachment": {"type": "other", "systemPrompt": [3, f"<r>{body}</r>"]}})]
            located = decoded(locator_rows, {"host": "claude", "id": "s-loc", "kind": "main"}, body)
            located_events = [] if located is raised_marker else located[0]
            check("an unreadable locator, and a rejected element with the body not among the rest, are damaged "
                  "session injections; a body found beside a rejected element is the injection",
                  [(event["n"], event["kind"], event["damaged"]) for event in located_events]
                  == [(1, "session_injection", "container_unusable"),
                      (2, "session_injection", "locator_element_rejected"), (3, "session_injection", None)],
                  f"raised={located is raised_marker} {[(event['n'], event['damaged']) for event in located_events]}")

            # S-5: certainty, cut by an undecodable line for every owner, and by an ownerless sidechain injection
            cut_owners = raw_lines(scratch / "p2" / "cut-owners.jsonl", [
                dated("2026-10-13T09:00:00+00:00"),
                dated("2026-10-13T09:30:00+00:00", "# Global\n\n- a1's\n", agentId="a1"),
                b"{a line that does not decode",
                dated("2026-10-13T10:00:00+00:00")])
            _r, failed, events_co, findings_co = p2_run("cut-owners", [census_row("claude", "s-co", cut_owners)])
            main_co, a1_co = owner_ref("claude", "s-co"), owner_ref("claude", "s-co", "a1")
            check("the ownership map gives each line its owner, and a line that does not decode to nobody",
                  failed is None and (session_of(findings_co, "s-co") or {}).get("ownership") == {
                      "intervals": [{"owner_ref": main_co, "from": 1, "to": 2}, {"owner_ref": a1_co, "from": 2, "to": 3},
                                    {"owner_ref": main_co, "from": 4, "to": 5}],
                      "unknown": [{"from": 3, "to": 4}]},
                  f"raised={failed is not None}")
            check("an undecodable line cuts the certainty of the events before it, for every owner",
                  failed is None and [(event["n"], event["interval"], event["certain_to"], event["uncertain_reason"])
                                      for event in events_co]
                  == [(1, [1, 4], 3, "undecodable_after"), (2, [2, 5], 3, "undecodable_after"), (4, [4, 5], None, None)],
                  f"raised={failed is not None} "
                  f"{[(event['n'], event['interval'], event['certain_to']) for event in events_co]}")
            cut_stray = raw_lines(scratch / "p2" / "cut-stray.jsonl", [
                dated("2026-10-13T09:00:00+00:00"),
                dated("2026-10-13T09:30:00+00:00", "# Global\n\n- a1's\n", agentId="a1"),
                dated("2026-10-13T10:00:00+00:00", "# Global\n\n- nobody's\n", isSidechain=True),
                {"type": "user", "timestamp": "2026-10-13T10:30:00+00:00"}])
            _r, failed, events_cs, _f = p2_run("cut-stray", [census_row("claude", "s-cs", cut_stray)])
            check("a sidechain injection with no owner cuts the identified sidechains' certainty, never the main session's",
                  failed is None and [(event["n"], event["certain_to"], event["uncertain_reason"]) for event in events_cs]
                  == [(1, None, None), (2, 3, "ownership_unknown"), (3, None, None)],
                  f"raised={failed is not None} {[(event['n'], event['certain_to']) for event in events_cs]}")

            # S-11: an event's id is its canonical tuple, with its kind and its binding in it
            both_path = raw_lines(scratch / "p2" / "both.jsonl", [
                {**dated("2026-10-14T09:00:00+00:00"), "attachment": {
                    "type": "instructions", "files": [member("User", "~/.claude/CLAUDE.md", "# G\n\n- r\n")],
                    "systemPrompt": [f"<r>{body}</r>"]}}])
            both_row = census_row("claude", "s-both", both_path)
            both_entry = {**both_row, "kind": "main", "prefix_sha": both_row["versions"][0]["prefix_sha"],
                          "record_count": both_row["versions"][0]["record_count"]}
            both_read = transcript_records(both_entry)
            both_events = decoded(both_read["records"], both_entry, body)
            both_events = [] if both_events is raised_marker else both_events[0]
            independent = "e-" + hashlib.sha256(json.dumps(
                ["event", "native", "claude", "s-both", ["whole", both_row["sha256"]], 1],
                separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
            _r, failed, events_both, _f = p2_run("both", [both_row], body)
            check("one record holding the instructions list and the selected body is two events, of two kinds",
                  sorted(event["kind"] for event in both_events) == ["native", "session_injection"],
                  f"{sorted(event['kind'] for event in both_events)}")
            check("an event's id is the canonical tuple of its kind, session, binding and line",
                  failed is None and [event["id"] for event in events_both if event["kind"] == "native"] == [independent],
                  f"raised={failed is not None} matched={[event['id'] for event in events_both] == [independent]}")
            check("and the two events of one record have two ids",
                  failed is None and len(events_both) == 2 and len({event["id"] for event in events_both}) == 2,
                  f"events={len(events_both)} ids={len({event['id'] for event in events_both})}")
            # The same record of the same session at the same line, read under its prefix binding instead
            # of its whole-file one: the binding is the ONLY component that differs, so the two production
            # ids are compared with each other. Compared with `independent` alone, an id with no binding
            # in it still differed from one built with the whole-file binding, and the control passed.
            whole_native = [event["id"] for event in events_both if event["kind"] == "native"]
            prefix_only_row = {**both_row, "sha256": None}
            _r, failed, events_po, _f = p2_run("both-prefix", [prefix_only_row])
            independent_prefix = "e-" + hashlib.sha256(json.dumps(
                ["event", "native", "claude", "s-both",
                 ["prefix", both_row["versions"][0]["prefix_sha"], both_row["versions"][0]["record_count"]], 1],
                separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
            check("the binding a transcript was read under is part of its events' ids",
                  failed is None and len(events_po) == 1 and len(whole_native) == 1
                  and events_po[0]["id"] == independent_prefix and events_po[0]["id"] != whole_native[0],
                  f"raised={failed is not None} events={len(events_po)} "
                  f"canonical={bool(events_po) and events_po[0]['id'] == independent_prefix} "
                  f"same_as_whole={bool(events_po) and bool(whole_native) and events_po[0]['id'] == whole_native[0]}")

            # A selection holds no native layer (S-15; lead ruling 5 on the P2.4 plan): the damaged event that
            # used to be "the event in force" at the pin is published with its damage in sessions.json, and the
            # selection's native row is `per_event` whatever that event is.
            in_force = _raised(lambda: _native("native_global")({"reference": "selection", "pin": "claude:s-dm"}))
            check("a selection's native layer is per_event, a damaged event at the pin included, which stays published "
                  "with its damage",
                  isinstance(in_force, Unacquired) and str(in_force) == UNKNOWN_REASONS["per_event"]
                  and any(event["damaged"] == "container_unusable" for event in events_dm),
                  f"unacquired={isinstance(in_force, Unacquired)}")
            delivery_path = raw_lines(scratch / "p2" / "delivery.jsonl", [record for _line, record in locator_rows])
            delivery_run = scratch / "p2" / "run-delivery"
            delivery_run.mkdir(parents=True)
            (delivery_run / CENSUS).write_text(json.dumps({"transcripts": [
                census_row("claude", "s-loc", delivery_path)]}), encoding="utf-8")
            delivery_ctx = {"notes": {}, "session_pins": delivered_to(body, "claude:s-loc")}
            delivery_failed = _raised(lambda: bind_transcripts(delivery_ctx, delivery_run))
            check("a damaged session injection is never counted as a confirmed delivery",
                  delivery_failed is None
                  and delivery_ctx["notes"].get("transcripts", {}).get("delivery_confirmed") == 1
                  and len([event for event in delivery_ctx.get("events") or [] if event["kind"] == "session_injection"]) == 3,
                  f"raised={delivery_failed is not None} "
                  f"confirmed={delivery_ctx['notes'].get('transcripts', {}).get('delivery_confirmed')}")

            # S-3: an unread instant says why
            when_path = raw_lines(scratch / "p2" / "when.jsonl", [
                {k: v for k, v in dated("x").items() if k != "timestamp"},
                dated("2026-10-15T09:00:00"), dated("2026-10-15T18:00:00+09:00")])
            _r, failed, events_wh, _f = p2_run("when", [census_row("claude", "s-wh", when_path)])
            rows_wh = [event_row(event) for event in events_wh]
            check("an event's instant is published in UTC, and an unread one says why: absent apart from zone-less",
                  failed is None and [(row["at"], row["at_reason"]) for row in rows_wh]
                  == [(None, "undated"), (None, "undated_naive"), ("2026-10-15T09:00:00+00:00", None)],
                  f"raised={failed is not None} {[row['at_reason'] for row in rows_wh]}")

            # S-23: an id-less head with no later own record
            headless = raw_lines(scratch / "p2" / "headless.jsonl", [
                codex_meta(None, "2026-10-09T08:00:00+00:00"), codex_meta("c-parent", "2026-10-09T09:00:00+00:00")])
            _r, failed, events_hl, findings_hl = p2_run("headless", [census_row("codex", "c-hl", headless)])
            record_hl = session_of(findings_hl, "c-hl") or {}
            check("a first session_meta naming no session, with no later own record, is own_meta_unidentified at its line",
                  failed is None and not events_hl and record_hl.get("own_meta_unidentified") == 1
                  and {"reason": "own_meta_unidentified", "line": 1} in record_hl.get("unknown", [])
                  and record_hl.get("inherited_session_meta") == {"another_session_id": 1, "no_session_id": 1},
                  f"raised={failed is not None} unidentified={record_hl.get('own_meta_unidentified')}")
            headed = raw_lines(scratch / "p2" / "headed.jsonl", [
                codex_meta(None, "2026-10-09T08:00:00+00:00"), codex_meta("c-hd", "2026-10-09T09:00:00+00:00")])
            _r, failed, _events_hd, findings_hd = p2_run("headed", [census_row("codex", "c-hd", headed)])
            check("and a later own record answers it",
                  failed is None and (session_of(findings_hd, "c-hd") or {}).get("own_meta_unidentified", 1) is None,
                  f"raised={failed is not None}")

            # M9: the alternates are counted and never read
            alt_main = raw_lines(scratch / "p2" / "alt-main.jsonl", [dated("2026-10-16T09:00:00+00:00")])
            alt_other = [raw_lines(scratch / "p2" / f"alt-{n}.jsonl", [dated("2026-10-16T10:00:00+00:00")]) for n in (1, 2)]
            alt_run = scratch / "p2" / "run-alt"
            alt_run.mkdir(parents=True)
            (alt_run / CENSUS).write_text(json.dumps({"transcripts": [
                {**census_row("claude", "s-alt", alt_main), "alt_paths": [str(path) for path in alt_other]}]}),
                encoding="utf-8")
            alt_outcome, alt_asked = opened_while(lambda: transcript_events(alt_run))
            alt_record = (session_of(alt_outcome[2], "s-alt") or {}) if isinstance(alt_outcome, tuple) else {}
            check("a census row's two alternate files are counted on its session record, and no read reaches them",
                  isinstance(alt_outcome, tuple)
                  and {"kind": "alt_paths", "count": 2} in alt_record.get("limitations", [])
                  and alt_asked == [str(alt_main)],
                  f"tuple={isinstance(alt_outcome, tuple)} reads={len(alt_asked)}")

            # S-14: every census row has its record, with its read outcome; the survivor `no path` is its own
            bound_ok = raw_lines(scratch / "p2" / "rec-bound.jsonl", [dated("2026-10-17T09:00:00+00:00")])
            moved = raw_lines(scratch / "p2" / "rec-moved.jsonl", [dated("2026-10-17T09:00:00+00:00")])
            outcome_rows = [
                census_row("claude", "r-bound", bound_ok),
                {**census_row("claude", "r-unbound", bound_ok), "sha256": None, "versions": [],
                 "status": "child_of", "parent": "r-bound"},
                {**census_row("claude", "r-nopath", bound_ok), "path": None},
                {**census_row("claude", "r-invalid", bound_ok), "sha256": "not-a-hash"},
                census_row("claude", "r-moved", moved, sha="1" * 64, prefix="2" * 64)]
            _r, failed, _events_rec, findings_rec = p2_run("records", outcome_rows)
            reads = {row["transcript"]["id"]: (row["read"], [entry["reason"] for entry in row["unknown"]])
                     for row in findings_rec["sessions"]}
            check("every census row has its session record, each with its own read outcome and reason",
                  failed is None and reads == {
                      "r-bound": ("bound", []), "r-unbound": ("unbound", ["unbound"]),
                      "r-nopath": ("no_path", ["no_path"]), "r-invalid": ("binding_invalid", ["binding_invalid"]),
                      "r-moved": ("changed", ["changed"])},
                  f"raised={failed is not None} {sorted((key, value[0]) for key, value in reads.items())}")
            check("a bound row with no path is `no_path`, never the shared `no_record` (a survivor replaced)",
                  reads.get("r-nopath") == ("no_path", ["no_path"]), f"{reads.get('r-nopath')}")
            check("a child's session record points at its parent by reference",
                  (session_of(findings_rec, "r-unbound") or {}).get("parent_ref") == session_ref("claude", "r-bound"),
                  "the parent reference is not the parent's session reference")
            many = [{**census_row("claude", f"r-many-{n}", bound_ok), "sha256": None, "versions": []} for n in range(25)]
            many_run = scratch / "p2" / "run-many"
            many_run.mkdir(parents=True)
            (many_run / CENSUS).write_text(json.dumps({"transcripts": many}), encoding="utf-8")
            many_ctx = {"notes": {}}
            many_failed = _raised(lambda: bind_transcripts(many_ctx, many_run))
            check("no list of named unknowns is truncated: 25 unbound rows are 25 records and 25 notes",
                  many_failed is None and len(many_ctx.get("sessions") or []) == 25
                  and len(many_ctx["notes"].get("transcripts", {}).get("unknown") or []) == 25,
                  f"raised={many_failed is not None} sessions={len(many_ctx.get('sessions') or [])}")

            # the published document, through its production path and its own root in the schema
            sessions_doc = sessions_document({"home": None, "commit": "fixture", "sessions": findings_rec["sessions"],
                                              "events": _events_rec, "segments": findings_rec.get("segments") or []})
            clean("sessions.json validates against its own root in the schema", document_contract_problems(sessions_doc))
            clean("and its records agree with one another", sessions_cross_problems(sessions_doc))
            control("a document whose kind is misspelled is refused by name, never judged as another document",
                    document_contract_problems({**sessions_doc, "document": "sesions"}), "DOCUMENT_KIND_UNDECLARED")
            control("and so is a document that names no kind at all",
                    document_contract_problems({key: value for key, value in sessions_doc.items() if key != "document"}),
                    "DOCUMENT_KIND_UNDECLARED")
            clean("every document this module publishes has the schema root its kind names", document_roots_problems())
            own_roots = inventory_schema()
            renamed = json.loads(json.dumps(own_roots))
            renamed["$defs"]["sessions_document"]["properties"]["document"]["const"] = "sesions"
            control("a schema root whose kind is not the one the code picks it by",
                    document_roots_problems(renamed), "DOCUMENT_ROOTS_MISMATCH")
            unrequired = json.loads(json.dumps(own_roots))
            unrequired["$defs"]["sessions_document"]["required"].remove("document")
            control("a schema root that names its kind and does not require it",
                    document_roots_problems(unrequired), "DOCUMENT_ROOT_UNREQUIRED", "sessions_document")
            unlisted = json.loads(json.dumps(own_roots))
            unlisted["$defs"]["document_kind"]["properties"]["document"]["enum"].remove("sessions")
            control("a file root whose kind list leaves a root out",
                    document_roots_problems(unlisted), "DOCUMENT_KIND_ENUM_MISMATCH")
            kept_roots = globals()["DOCUMENT_ROOTS"]
            try:
                globals()["DOCUMENT_ROOTS"] = {**kept_roots, "extra": "sessions_document"}
                extra_roots = document_roots_problems()
            finally:
                globals()["DOCUMENT_ROOTS"] = kept_roots
            control("a root the code picks that the schema does not declare, for a document nobody publishes",
                    extra_roots, "DOCUMENT_ROOTS_MISMATCH", "DOCUMENT_ROOTS_UNCOVERED")
            clean("the limitation kinds, categories and fields the code holds are the ones the schema admits",
                  limitation_schema_problems())
            for name, field, value in (("kinds", "kind", "agent_id_unusable"), ("categories", "category", "locator_unusable")):
                narrowed = json.loads(json.dumps(own_roots))
                narrowed["$defs"]["limitation"]["properties"][field]["enum"].remove(value)
                control(f"a schema whose limitation {field} leaves out one the table holds",
                        limitation_schema_problems(narrowed), f"LIMITATION_{name.upper()}_MISMATCH")
            widened = json.loads(json.dumps(own_roots))
            widened["$defs"]["limitation"]["properties"]["note"] = {"type": "string"}
            control("a schema whose limitation admits a field no kind of the table carries",
                    limitation_schema_problems(widened), "LIMITATION_FIELDS_MISMATCH")
            doc_event = sessions_doc["events"][0]
            doc_record = next(row for row in sessions_doc["sessions"] if doc_event["event_id"] in row["event_refs"])
            control("an event listed twice", sessions_cross_problems(
                {**sessions_doc, "events": sessions_doc["events"] + [doc_event]}), "CROSS_EVENT_DUPLICATE")
            control("a session record listing an event nobody published", sessions_cross_problems(
                {**sessions_doc, "sessions": [{**row, "event_refs": row["event_refs"] + ["e-" + "0" * 24]}
                                              if row is doc_record else row for row in sessions_doc["sessions"]]}),
                "CROSS_EVENT_UNRESOLVED")
            control("an event no session record lists", sessions_cross_problems(
                {**sessions_doc, "sessions": [{**row, "event_refs": []} if row is doc_record else row
                                              for row in sessions_doc["sessions"]]}), "CROSS_EVENT_UNLISTED")
            control("an event listed by another session than its own", sessions_cross_problems(
                {**sessions_doc, "events": [{**event, "session_ref": "p-" + "0" * 24} if event is doc_event else event
                                            for event in sessions_doc["events"]]}), "CROSS_EVENT_ASTRAY")
            control("two intervals of one owner and kind that overlap", sessions_cross_problems(
                {**sessions_doc, "events": sessions_doc["events"] + [
                    {**doc_event, "event_id": "e-" + "1" * 24, "interval_from": doc_event["interval_from"],
                     "interval_to": doc_event["interval_to"]}]}), "CROSS_INTERVAL_OVERLAP")
            control("and the schema refuses a session record missing its reference",
                    document_contract_problems({**sessions_doc, "sessions": [
                        {key: value for key, value in sessions_doc["sessions"][0].items() if key != "session_ref"}]}),
                    "DOCUMENT_INVALID", "session_ref")

        with section('P2.2: the current reference point, scope by scope, on the PUBLISHED answers (#6, step 0'):
            # ---- P2.2: the current reference point, scope by scope, on the PUBLISHED answers (#6, step 0
            # S-7 .. S-10, S-19). Each run goes through the path `run` takes — `bind_transcripts`,
            # `layer_rows`, `emitted_document`, `write_document` — over the scoped native layers alone: the
            # catalog's producers cost seconds a run and say nothing about a scope.
            native_only = tuple((layer, producers) for layer, producers in LAYERS if layer in SCOPED_LAYERS)
            missing = object()

            def inj(at, files, cwd=missing, **extra):
                record = {"type": "attachment", "attachment": {"type": "instructions", "files": files}}
                if at is not None:
                    record["timestamp"] = at
                if cwd is not missing:
                    record["cwd"] = cwd
                return {**record, **extra}

            def block_meta(ident, at, text, cwd):
                return {"type": "session_meta", "timestamp": at,
                        "payload": {"id": ident, "cwd": cwd, "base_instructions": {"text": text}}}

            def published_run(name, transcripts, pin=None, snapshot=None, state=None):
                """`current.json`, `sessions.json` and `shared/store.json` as published for a census of
                `(host, id, records, extra row fields)`, crossed as `run` crosses them, or
                `{"refused": <code>}` when the path refuses it: a control fails by its own name.

                `state` is a fixture state root, acquired through `freeze_inputs` as `run` acquires it, so
                every census row's own pin is read there. `snapshot` is a control about the transcript and
                not the pin: every Claude session's own pin reads with it."""
                run_at = scratch / "p22" / f"run-{name}"
                rows_here = []
                for host, ident, records_in, fields in transcripts:
                    path_here = raw_lines(scratch / "p22" / name / f"{ident}.jsonl", records_in)
                    rows_here.append({**census_row(host, ident, path_here), **fields})
                run_at.mkdir(parents=True, exist_ok=True)
                (run_at / CENSUS).write_text(json.dumps({"transcripts": rows_here}), encoding="utf-8")
                ctx_here = context_of(REPO, None, None, {}, pin, None)
                ctx_here.update(home=str(fixture_home), commit="fixture")
                if snapshot is not None:
                    ctx_here.update(snapshot=snapshot, pin_record={"content_ref": snapshot["content_ref"]},
                                    session_pins=delivered_to(snapshot["output"]["instruction_text"], *[
                                        f"{host}:{ident}" for host, ident, _records, _fields in transcripts if host == "claude"],
                                        content_ref=snapshot["content_ref"]))
                kept_layers = globals()["LAYERS"]
                out_here = scratch / "p22" / f"out-{name}" / "inventory"
                written = {"current": out_here / "current.json", "sessions": out_here / f"{SESSIONS}.json",
                           "store": out_here / STORE_REL}
                try:
                    globals()["LAYERS"] = native_only
                    if state is not None:
                        freeze_inputs(scratch / "p22" / f"frozen-{name}", REPO, state, None, pin, ctx_here,
                                      census_entries(run_at))
                    bind_transcripts(ctx_here, run_at)
                    document_here, _units = emitted_document("current", layer_rows("current", ctx_here), ctx_here)
                    shared_here = []
                    if state is not None:
                        # A run over a fixture state publishes the shared inventories too, through the full
                        # producer table `run` uses (lead ruling 3, 14:55: its selection catalog is judged).
                        globals()["LAYERS"] = kept_layers
                        shared_here = shared_inventories(ctx_here)
                        globals()["LAYERS"] = native_only
                    sessions_here, store_here = sessions_document(ctx_here), store_document(ctx_here)
                    crossed_here = sessions_cross_problems(sessions_here) + store_cross_problems(
                        store_here, {"current": document_here}) + occurrence_cross_problems(sessions_here, store_here) \
                        + (shared_cross_problems(shared_here, store_here, sessions_here) if state is not None else [])
                    if crossed_here:
                        return {"refused": "crossed", "problems": crossed_here}
                    for key, document_out in (("current", document_here), ("sessions", sessions_here),
                                              ("store", store_here)):
                        write_document(out_here.parent, written[key], document_out, str(fixture_home))
                    for relative, document_out in shared_here:
                        write_document(out_here.parent, out_here / relative, document_out, str(fixture_home))
                except Exception as exc:  # the control names what refused, never the suite
                    return {"refused": type(exc).__name__}
                finally:
                    globals()["LAYERS"] = kept_layers
                published_here = {key: json.loads(path.read_text(encoding="utf-8")) for key, path in written.items()}
                if state is not None:
                    published_here["shared"] = {path.stem: json.loads(path.read_text(encoding="utf-8"))
                                                for path in sorted((out_here / "shared").glob("*-i-*.json"))}
                return published_here

            def published_current(name, transcripts, pin=None, state=None):
                published = published_run(name, transcripts, pin, state=state)
                return published.get("current") or {"refused": published["refused"], "scopes": [], "layers": [],
                                                      "units": [], "scope_universe": []}

            def scope_rows(document_here, layer, host):
                return [row for row in document_here["scopes"] if row["layer"] == layer and row["host"] == host]

            def one_scope(document_here, layer, host, scope=missing):
                found_here = [row for row in scope_rows(document_here, layer, host) if scope is missing or row["scope"] == scope]
                return found_here[0] if len(found_here) == 1 else {}

            def reason_keys(row):
                return [entry["reason"] for entry in row.get("reasons", [])]

            p1, p2, p3, q = "/w/p1", "/w/p2", "/w/p3", "/w/q"
            d1 = f"/w/owner/.claude/projects/{lexical_slug(p1)}/memory"
            d2 = f"/w/owner/.claude/projects/{lexical_slug(q)}/memory"
            d3 = f"/w/owner/.claude/projects/{lexical_slug(p3)}/memory"
            secret_a, secret_b = "token=" + "A" * 24 + "1", "token=" + "B" * 24 + "2"
            scopes_doc = published_current("scopes", [
                ("claude", "s-del", [
                    inj("2026-10-20T09:00:00+00:00", [member("User", "/w/g.md", "# G\n\n- one\n"),
                                                       member("Project", f"{p1}/CLAUDE.md", "# P\n\n- p1 rule\n"),
                                                       member("AutoMem", f"{d1}/a.md", "- a\n"),
                                                       member("AutoMem", f"{d1}/b.md", "- b\n"),
                                                       member("AutoMem", f"{d2}/c.md", "- c\n")], cwd=p1),
                    inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "# G\n\n- two\n"),
                                                       member("AutoMem", f"{d1}/a.md", "- a\n")], cwd=p1)], {}),
                ("claude", "s-two", [inj("2026-10-20T11:00:00+00:00", [member("User", "/w/g.md", "# G\n\n- three\n"),
                                                                        member("Project", f"{p2}/CLAUDE.md", "- p2\n")],
                                         cwd=p2)], {}),
                ("claude", "s-mem", [inj("2026-10-20T09:00:00+00:00", [member("AutoMem", f"{d3}/m.md", "- m\n")], cwd=p3)], {}),
                ("claude", "s-mem2", [inj("2026-10-20T10:30:00+00:00", [member("Project", f"{p3}/CLAUDE.md", "- p3\n")],
                                          cwd=p3)], {}),
                ("claude", "s-sec1", [inj("2026-10-20T08:00:00+00:00", [member("Project", f"/w/{secret_a}/CLAUDE.md", "- s\n")],
                                          cwd=f"/w/{secret_a}")], {}),
                ("claude", "s-sec2", [inj("2026-10-20T08:00:00+00:00", [member("Project", f"/w/{secret_b}/CLAUDE.md", "- s\n")],
                                          cwd=f"/w/{secret_b}")], {}),
                ("codex", "c-1", [block_meta("c-1", "2026-10-20T09:30:00+00:00", "# Block\n\n- the first\n", p1)], {}),
                ("codex", "c-2", [block_meta("c-2", "2026-10-20T12:00:00+00:00", "", p1)], {}),
                ("codex", "c-3", [block_meta("c-3", "2026-10-20T09:45:00+00:00", "# Block\n\n- the block at p2\n", p2)], {})])
            check("the published scope run was not refused", "refused" not in scopes_doc, f"{scopes_doc.get('refused')}")
            clean("and its current.json validates, scope rows included", document_contract_problems(
                {**scopes_doc, "document": "current"}) if "refused" not in scopes_doc else ["refused"])
            deleted = one_scope(scopes_doc, "native_project", "claude", p1)
            check("a deletion shows: the project scope is empty as of the event that no longer carries its file",
                  deleted.get("status") == "empty" and deleted.get("as_of") == "2026-10-20T10:00:00+00:00"
                  and deleted.get("session") == "claude:s-del" and deleted.get("line") == 2,
                  f"{deleted.get('status')} {deleted.get('as_of')} {deleted.get('line')}")
            codex_project = one_scope(scopes_doc, "native_project", "codex", p1)
            codex_block = one_scope(scopes_doc, "native_undivided", "codex", p1)
            check("Claude and Codex at one cwd keep separate answers",
                  bool(deleted) and bool(codex_project) and codex_project.get("scope_id") != deleted.get("scope_id")
                  and reason_keys(codex_project) == ["codex_undivided"] and codex_project.get("status") == "unknown"
                  and bool(codex_block) and codex_block.get("scope_id") not in (deleted.get("scope_id"), codex_project.get("scope_id")),
                  f"claude={deleted.get('status')} codex={codex_project.get('status')} block={codex_block.get('status')}")
            claude_globals = scope_rows(scopes_doc, "native_global", "claude")
            check("the global layer from two cwds is one answer per host",
                  len(claude_globals) == 1 and claude_globals[0]["status"] == "answered"
                  and claude_globals[0]["session"] == "claude:s-two"
                  and [row["status"] for row in scope_rows(scopes_doc, "native_global", "codex")] == ["unknown"],
                  f"claude={[(row['status'], row['session']) for row in claude_globals]}")
            memory_one, memory_two = one_scope(scopes_doc, "native_memory", "claude", d1), one_scope(scopes_doc, "native_memory", "claude", d2)
            check("one event with two memory directories answers for both",
                  memory_two.get("status") == "answered" and memory_two.get("line") == 1
                  and memory_two.get("session") == "claude:s-del" and memory_one.get("status") == "answered",
                  f"d1={memory_one.get('status')} d2={memory_two.get('status')} {memory_two.get('line')}")
            check("independent directories at one cwd: a later event of that cwd leaves another project's directory "
                  "answered", memory_two.get("status") == "answered" and memory_two.get("as_of") == "2026-10-20T09:00:00+00:00",
                  f"{memory_two.get('status')} {memory_two.get('as_of')}")
            d1_paths = sorted(unit["path"] for unit in scopes_doc["units"]
                              if unit["layer"] == "native_memory" and unit["provenance"].get("scope_id") == memory_one.get("scope_id"))
            check("removing one AutoMem member while another names the same directory: the directory's set is the "
                  "newest event's whole set", memory_one.get("line") == 2 and bool(d1_paths)
                  and all(path.endswith("/a.md") for path in d1_paths),
                  f"line={memory_one.get('line')} paths={[path.rsplit('/', 1)[-1] for path in d1_paths]}")
            check("a later empty Codex block empties the current block",
                  codex_block.get("status") == "empty" and codex_block.get("session") == "codex:c-2",
                  f"{codex_block.get('status')} {codex_block.get('session')}")
            block_row = one_scope(scopes_doc, "native_undivided", "codex", p2)
            block_units = [unit for unit in scopes_doc["units"] if "the block at p2" in unit["text"]]
            check("a Codex block is published only at its own layer value: its text is a unit of native_undivided at "
                  "its (codex, cwd) scope row, no global unit carries it, and Claude's global row is Claude's alone",
                  block_row.get("status") == "answered" and block_row.get("session") == "codex:c-3"
                  and bool(block_units) and all(unit["layer"] == "native_undivided"
                                                 and unit["provenance"].get("scope_id") == block_row.get("scope_id")
                                                 for unit in block_units)
                  and claude_globals and str(claude_globals[0].get("session") or "").startswith("claude:"),
                  f"{block_row.get('status')} units={[(unit['layer']) for unit in block_units]}")
            unconfirmed = one_scope(scopes_doc, "native_memory", "claude", d3)
            check("a later event of the same project that names no member of a memory directory makes it "
                  "memory_unconfirmed, naming that event, the earlier set evidence only",
                  unconfirmed.get("status") == "unknown" and reason_keys(unconfirmed) == ["memory_unconfirmed"]
                  and len(unconfirmed.get("evidence", [])) == 1 and not unconfirmed.get("event_ids")
                  and not any(unit["provenance"].get("scope_id") == unconfirmed.get("scope_id") for unit in scopes_doc["units"]),
                  f"{unconfirmed.get('status')} {reason_keys(unconfirmed)}")
            twin_scopes = [row for row in scope_rows(scopes_doc, "native_project", "claude") if row["session"] in
                           ("claude:s-sec1", "claude:s-sec2")]
            check("two raw scopes that project to one display string stay two scopes",
                  len(twin_scopes) == 2 and len({row["scope_id"] for row in twin_scopes}) == 2
                  and len({row["scope"] for row in twin_scopes}) == 1 and "A" * 24 not in json.dumps(scopes_doc),
                  f"rows={len(twin_scopes)} ids={len({row['scope_id'] for row in twin_scopes})} "
                  f"displays={len({row['scope'] for row in twin_scopes})}")
            check("every scope answer, empty ones included, carries its as_of, its session and the freshness sentence",
                  bool(scopes_doc["scopes"]) and all(row["freshness"] == FRESHNESS for row in scopes_doc["scopes"])
                  and all(row["as_of"] and row["session"] for row in scopes_doc["scopes"] if row["status"] in ("answered", "empty")),
                  f"{len(scopes_doc['scopes'])} row(s)")
            check("an unpinned session's global answer carries the limitation that its launch exclusion is unobservable",
                  bool(claude_globals) and claude_globals[0]["limitations"] == ["exclusion_unobservable"],
                  f"{claude_globals[0]['limitations'] if claude_globals else None}")

            empty_doc = published_current("empty-files", [
                ("claude", "s-e", [inj("2026-10-20T10:00:00+00:00", [], cwd="/w/e")], {})])
            check("a valid files: [] event is an empty answer at every scope it names, never a missing one",
                  one_scope(empty_doc, "native_global", "claude").get("status") == "empty"
                  and one_scope(empty_doc, "native_project", "claude", "/w/e").get("status") == "empty",
                  f"{[(row['layer'], row['status']) for row in empty_doc['scopes']]}")

            # The published counterparts of two behaviours the function-level controls above judge (lead,
            # 2026-10-29): a subagent row's and an inline sidechain's injections answer no current scope,
            # and a zone-less instant is an unknown head, never an error.
            eligibility_doc = published_current("eligibility", [
                ("claude", "s-main", [inj("2026-10-20T09:00:00+00:00", [member("User", "/w/g.md", "- main\n")], cwd=p1),
                                      inj("2026-10-20T11:00:00+00:00", [member("User", "/w/g.md", "- side\n")], cwd=p1,
                                          isSidechain=True, agentId="a1")], {}),
                ("claude", "s-kid", [inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "- kid\n")], cwd=p1)],
                 {"status": "child_of", "parent": "s-main"})])
            eligible_global = one_scope(eligibility_doc, "native_global", "claude")
            check("a subagent row's and an inline sidechain's injections answer no current scope, and are counted "
                  "ineligible",
                  eligible_global.get("status") == "answered" and eligible_global.get("session") == "claude:s-main"
                  and eligible_global.get("line") == 1
                  and {row["host"]: row["ineligible"] for row in eligibility_doc["scope_universe"]}.get("claude") == 2,
                  f"{eligible_global.get('session')} {eligible_global.get('line')} "
                  f"{[row['ineligible'] for row in eligibility_doc['scope_universe']]}")
            naive_doc = published_current("naive", [
                ("claude", "s-nv", [inj("2026-10-20T12:00:00", [member("User", "/w/g.md", "- naive\n")], cwd=p1)], {}),
                ("claude", "s-aw", [inj("2026-10-20T09:00:00+00:00", [member("User", "/w/g.md", "- aware\n")], cwd=p2)], {})])
            naive_global = one_scope(naive_doc, "native_global", "claude")
            check("a zone-less instant beside an aware one is published as the scope's unknown by undated_naive, and "
                  "nothing raises",
                  "refused" not in naive_doc and naive_global.get("status") == "unknown"
                  and reason_keys(naive_global) == ["undated_naive"],
                  f"{naive_doc.get('refused')} {naive_global.get('status')} {reason_keys(naive_global)}")

            # S-8 (a): an undated head, unbounded and then bounded by a later record of its own transcript
            undated_head = [("claude", "s-a", [inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "- a1\n")], cwd=p1),
                                               inj(None, [member("User", "/w/g.md", "- a2\n")], cwd=p1)], {}),
                            ("claude", "s-b", [inj("2026-10-20T11:00:00+00:00", [member("User", "/w/g.md", "- b\n")], cwd=p2)], {})]
            unbounded = one_scope(published_current("undated", undated_head), "native_global", "claude")
            check("an undated head is the scope's unknown, and a later transcript does not win over it",
                  unbounded.get("status") == "unknown" and reason_keys(unbounded) == ["undated"]
                  and unbounded.get("session") is None, f"{unbounded.get('status')} {reason_keys(unbounded)}")
            bounded_head = [undated_head[0][:2] + ([*undated_head[0][2], {"type": "user", "timestamp": "2026-10-20T10:30:00+00:00"}], {}),
                            undated_head[1]]
            bounded = one_scope(published_current("bounded", bounded_head), "native_global", "claude")
            check("and the competitor wins once a later dated record of the same transcript bounds the undated head",
                  bounded.get("status") == "answered" and bounded.get("session") == "claude:s-b",
                  f"{bounded.get('status')} {bounded.get('session')}")

            # S-8 (c): ties
            tie_doc = published_current("tie", [
                ("claude", "s-x", [inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "- x\n")], cwd=p1)], {}),
                ("claude", "s-y", [inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "- y\n")], cwd=p2)], {})])
            tied = one_scope(tie_doc, "native_global", "claude")
            check("two events at one instant that disagree give the scope's unknown",
                  tied.get("status") == "unknown" and reason_keys(tied) == ["tie", "tie"], f"{tied.get('status')} {reason_keys(tied)}")
            ties_doc = published_current("ties", [
                ("claude", "s-e1", [inj("2026-10-20T10:00:00+00:00", [], cwd="/w/t1")], {}),
                ("claude", "s-e2", [inj("2026-10-20T10:00:00+00:00", 5, cwd="/w/t1")], {}),
                ("claude", "s-f1", [inj("2026-10-20T10:00:00+00:00", [member("Project", "/w/t2/CLAUDE.md", "- t2\n")], cwd="/w/t2")], {}),
                ("claude", "s-f2", [inj("2026-10-20T10:00:00+00:00", [member("Project", "/w/t2/CLAUDE.md", "- t2\n"),
                                                                       {"type": "Project", "path": "/w/t2/x.md", "content": 5}],
                                        cwd="/w/t2")], {}),
                ("claude", "s-late", [inj("2026-10-20T12:00:00+00:00", [member("User", "/w/g.md", "- late\n")], cwd="/w/z")], {})])
            damaged_tie = one_scope(ties_doc, "native_project", "claude", "/w/t1")
            check("a valid empty event tied with a damaged one is never promoted to empty",
                  damaged_tie.get("status") == "unknown" and "container_unusable" in reason_keys(damaged_tie),
                  f"{damaged_tie.get('status')} {reason_keys(damaged_tie)}")
            rejected_tie = one_scope(ties_doc, "native_project", "claude", "/w/t2")
            check("a complete event tied with an equal-bytes event carrying an extra rejected member is incomplete",
                  rejected_tie.get("status") == "incomplete" and reason_keys(rejected_tie) == ["member_rejected"]
                  and len(rejected_tie.get("event_ids", [])) == 2, f"{rejected_tie.get('status')} {reason_keys(rejected_tie)}")

            # S-7: the cwd cases, and a memory path that is not absolute
            cwd_doc = published_current("cwd", [
                ("claude", "s-ok", [inj("2026-10-20T09:00:00+00:00", [member("Project", "/w/c/CLAUDE.md", "- c\n"),
                                                                       member("AutoMem", "~/.claude/projects/x/memory/m.md", "- m\n")],
                                        cwd="/w/c")], {}),
                ("claude", "s-nocwd", [inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "- g\n")])], {}),
                ("claude", "s-bad", [inj("2026-10-20T11:00:00+00:00", [member("User", "/w/g.md", "- bad\n")], cwd=5)], {}),
                ("claude", "s-rel", [inj("2026-10-20T08:00:00+00:00", [member("User", "/w/g.md", "- rel\n")], cwd="rel/dir")], {})])
            universe_cwd = {row["host"]: row for row in cwd_doc["scope_universe"]}.get("claude", {})
            check("the scope universe counts an absent cwd, an unreadable one and a relative memory path per host",
                  (universe_cwd.get("no_scope"), universe_cwd.get("cwd_unreadable"), universe_cwd.get("memory_path_relative"))
                  == (1, 2, 1), f"{universe_cwd}")
            global_cwd = one_scope(cwd_doc, "native_global", "claude")
            check("an unreadable cwd later at the host makes the global scope unknown, naming its event",
                  global_cwd.get("status") == "unknown" and "cwd_unreadable" in reason_keys(global_cwd)
                  and all(entry.get("event_id") for entry in global_cwd.get("reasons", []) if entry["reason"] == "cwd_unreadable"),
                  f"{global_cwd.get('status')} {reason_keys(global_cwd)}")
            project_cwd = one_scope(cwd_doc, "native_project", "claude", "/w/c")
            check("and an earlier project answer only uncertain, with its content still published",
                  project_cwd.get("status") == "uncertain" and set(reason_keys(project_cwd)) == {"cwd_unreadable"}
                  and any(unit["provenance"].get("scope_id") == project_cwd.get("scope_id") for unit in cwd_doc["units"]),
                  f"{project_cwd.get('status')} {reason_keys(project_cwd)}")
            layers_cwd = {row["layer"]: row for row in cwd_doc["layers"]}
            check("a count of outcomes that answer no scope keeps its layers from complete",
                  layers_cwd.get("native_project", {}).get("status") == "unknown"
                  and any("names no cwd" in text for text in layers_cwd.get("native_project", {}).get("reasons", []))
                  # no memory directory answered here at all (the one AutoMem path is relative): unknown (S-20)
                  and layers_cwd.get("native_memory", {}).get("status") == "unknown"
                  and any("memory_path_relative 1 at claude" in text
                          for text in layers_cwd.get("native_memory", {}).get("reasons", [])),
                  f"{layers_cwd.get('native_project', {}).get('status')} {layers_cwd.get('native_memory', {}).get('status')}")

            # Lead ruling 2026-10-29 on S-10's counts: an event without a readable cwd may be the later
            # same-project event of a memory directory, so the memory row is blocked by those counts too,
            # and an unreadable cwd later than a directory's last naming event makes it uncertain.
            dm = f"/w/owner/.claude/projects/{lexical_slug('/w/m')}/memory"
            nocwd_rows = published_current("memory-nocwd", [
                ("claude", "s-m", [inj("2026-10-20T09:00:00+00:00", [member("User", "/w/g.md", "- g\n"),
                                                                      member("AutoMem", f"{dm}/a.md", "- a\n")], cwd="/w/m")], {}),
                ("claude", "s-n", [inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "- g2\n")])], {})])
            nocwd_layers = {row["layer"]: row for row in nocwd_rows["layers"]}
            check("a later no_scope event at the host leaves the memory row incomplete and the global row complete",
                  nocwd_layers.get("native_memory", {}).get("status") == "incomplete"
                  and nocwd_layers.get("native_global", {}).get("status") == "complete"
                  and one_scope(nocwd_rows, "native_global", "claude").get("session") == "claude:s-n",
                  f"memory={nocwd_layers.get('native_memory', {}).get('status')} "
                  f"global={nocwd_layers.get('native_global', {}).get('status')}")
            later_bad = published_current("memory-badcwd", [
                ("claude", "s-m", [inj("2026-10-20T09:00:00+00:00", [member("AutoMem", f"{dm}/a.md", "- a\n")], cwd="/w/m")], {}),
                ("claude", "s-x", [inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "- x\n")], cwd=5)], {})])
            earlier_dir = one_scope(later_bad, "native_memory", "claude", dm)
            check("a later cwd_unreadable record makes an earlier memory directory uncertain: cwd_unreadable",
                  earlier_dir.get("status") == "uncertain" and reason_keys(earlier_dir) == ["cwd_unreadable"]
                  and earlier_dir.get("session") == "claude:s-m",
                  f"{earlier_dir.get('status')} {reason_keys(earlier_dir)}")
            naming_bad = published_current("memory-badcwd-names", [
                ("claude", "s-m", [inj("2026-10-20T09:00:00+00:00", [member("AutoMem", f"{dm}/a.md", "- a\n")], cwd="/w/m")], {}),
                ("claude", "s-x", [inj("2026-10-20T10:00:00+00:00", [member("AutoMem", f"{dm}/b.md", "- b\n")], cwd=5)], {})])
            check("and a count alone leaves a layer that has an answering scope incomplete, naming the count",
                  any(text.startswith("native_memory: no_scope 1 at claude")
                      for text in nocwd_layers.get("native_memory", {}).get("reasons", [])),
                  f"{nocwd_layers.get('native_memory', {}).get('reasons')}")
            unscoped_only = published_current("all-nocwd", [
                ("claude", "s-n", [inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "- g\n"),
                                                                      member("Project", "/w/x/CLAUDE.md", "- x\n")])], {})])
            unscoped_layers = {row["layer"]: row for row in unscoped_only["layers"]}
            check("a layer blocked by a count with no answering scope at all is unknown, the global layer complete",
                  unscoped_layers.get("native_project", {}).get("status") == "unknown"
                  and any("no_scope 1 at claude" in text for text in unscoped_layers.get("native_project", {}).get("reasons", []))
                  and unscoped_layers.get("native_global", {}).get("status") == "complete",
                  f"project={unscoped_layers.get('native_project', {}).get('status')} "
                  f"global={unscoped_layers.get('native_global', {}).get('status')}")
            named_dir = one_scope(naming_bad, "native_memory", "claude", dm)
            check("the same record naming a member under the directory leaves it answered by that record",
                  named_dir.get("status") == "answered" and named_dir.get("session") == "claude:s-x"
                  and not reason_keys(named_dir), f"{named_dir.get('status')} {named_dir.get('session')} {reason_keys(named_dir)}")

            # S-9: the slug test, plain cwd equality only without a projects/<slug>/ segment, unknown memberships
            memory_doc = published_current("memory", [
                ("claude", "s-m1", [inj("2026-10-20T09:00:00+00:00", [member("AutoMem", "/mem/plain/a.md", "- a\n"),
                                                                       member("AutoMem", "/mem/broken/b.md", "- b\n"),
                                                                       member("AutoMem", "/mem/gap/c.md", "- c\n")],
                                        cwd="/w/s")], {}),
                ("claude", "s-m2", [inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "- g\n")], cwd="/w/s")], {}),
                ("claude", "s-n1", [inj("2026-10-20T09:00:00+00:00", [member("AutoMem", "/mem/nocwd/d.md", "- d\n")])], {}),
                ("claude", "s-n2", [inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "- g\n")])], {}),
                ("claude", "s-k1", [inj("2026-10-20T09:00:00+00:00", [member("AutoMem", f"{d1}/k.md", "- k\n")], cwd=p1)], {}),
                ("claude", "s-k2", [inj("2026-10-20T10:00:00+00:00", 7, cwd=p1)], {}),
                ("claude", "s-j1", [inj("2026-10-20T09:00:00+00:00", [member("AutoMem", f"{d2}/j.md", "- j\n")], cwd=q)], {}),
                ("claude", "s-j2", [inj("2026-10-20T10:00:00+00:00", [{"type": "AutoMem", "path": 9, "content": "- j\n"}],
                                        cwd=q)], {})])
            plain_dir = one_scope(memory_doc, "native_memory", "claude", "/mem/plain")
            check("without a projects/<slug>/ segment, plain cwd equality decides the same project",
                  plain_dir.get("status") == "unknown" and reason_keys(plain_dir) == ["memory_unconfirmed"],
                  f"{plain_dir.get('status')} {reason_keys(plain_dir)}")
            nocwd_dir = one_scope(memory_doc, "native_memory", "claude", "/mem/nocwd")
            check("two missing cwds are never one project", nocwd_dir.get("status") == "answered",
                  f"{nocwd_dir.get('status')} {reason_keys(nocwd_dir)}")
            damaged_dir = one_scope(memory_doc, "native_memory", "claude", d1)
            check("a later unusable container of the same project makes the directory unknown by that reason",
                  damaged_dir.get("status") == "unknown" and reason_keys(damaged_dir) == ["container_unusable"],
                  f"{damaged_dir.get('status')} {reason_keys(damaged_dir)}")
            pathless_dir = one_scope(memory_doc, "native_memory", "claude", d2)
            check("a later AutoMem member of the same project with no usable path leaves the directory incomplete",
                  pathless_dir.get("status") == "incomplete" and reason_keys(pathless_dir) == ["member_rejected"],
                  f"{pathless_dir.get('status')} {reason_keys(pathless_dir)}")

            # S-8 (b), S-25: EVERY pinned session's own pin is read from a fixture state, through the
            # acquisition `run` uses, so its launch exclusion is known; none of these sessions is the `--pin`
            store_for_pins = store_module(REPO)

            def plant_snapshot(state_dir, text, baseline_ref="ref1", items=None, unavailable=()):
                """A verified-shape snapshot whose compiled text is `text`, with `items` (by default one item in
                the shape the store writes, `catalog_item`) and `unavailable` rows in its output; its content_ref."""
                items = [catalog_item("item-1", text="## Item 1\n\n- a rule\n")] if items is None else items
                inputs_here = {"baseline_ref": baseline_ref, "host": "claude", "selection": [item["ref"] for item in items],
                               "text": sha256_text(text)}
                ref = store_for_pins._digest(inputs_here)
                snap = state_dir / "sessions" / "snapshots" / ref
                snap.mkdir(parents=True, exist_ok=True)
                (snap / "CLAUDE.md").write_text(text, encoding="utf-8")
                (snap / "output.json").write_text(json.dumps({
                    "instruction_text": text, "files": ["CLAUDE.md"], "assets": {},
                    "item_refs": [item["ref"] for item in items], "unavailable": list(unavailable)}), encoding="utf-8")
                (snap / "inventory.json").write_text(json.dumps({
                    "inputs": inputs_here, "items": items,
                    "file_digests": {part: store_for_pins._digest((snap / part).read_bytes())
                                     for part in ("CLAUDE.md", "output.json")}}), encoding="utf-8")
                return ref

            def plant_pin(state_dir, ident, content_ref, include=True, names=None):
                """A Claude pin at `ident`'s path, naming `names` (another session) when given."""
                pins_dir = state_dir / "sessions" / "pins" / "claude"
                pins_dir.mkdir(parents=True, exist_ok=True)
                (pins_dir / f"{ident}.json").write_text(json.dumps({
                    "schema_version": 1, "content_ref": content_ref, "host": "claude", "session_id": names or ident,
                    "created": "2026-10-20T00:00:00+00:00", "include_global_instructions": include}), encoding="utf-8")

            pins_state = scratch / "p24" / "pins-state"
            included_ref = plant_snapshot(pins_state, "# Session\n\n- included\n")
            excluded_ref = plant_snapshot(pins_state, "# Session\n\n- excluded\n")
            plant_pin(pins_state, "s-pin", excluded_ref, include=False)
            plant_pin(pins_state, "s-inc", included_ref)
            plant_pin(pins_state, "s-mis", excluded_ref)
            old_row = ("claude", "s-old", [inj("2026-10-20T09:00:00+00:00", [member("User", "/w/g.md", "- old\n")], cwd=p1)], {})

            def newer(ident, census_ref, files=()):
                return ("claude", ident, [inj("2026-10-20T10:00:00+00:00", list(files), cwd=p1)],
                        {"pin": {"content_ref": census_ref}})

            excluded = one_scope(published_current("excluded", [old_row, newer("s-pin", excluded_ref)], state=pins_state),
                                 "native_global", "claude")
            check("a pinned, excluded session leaves the older global answer in force, and is counted",
                  excluded.get("status") == "answered" and excluded.get("session") == "claude:s-old",
                  f"{excluded.get('status')} {excluded.get('session')}")
            included = one_scope(published_current("included", [old_row, newer(
                "s-inc", included_ref, [member("User", "/w/g.md", "- new\n")])], state=pins_state), "native_global", "claude")
            check("TRANSITIONAL removed: a pinned session that is not the --pin, whose pin reads with "
                  "include_global_instructions true, answers the global scope",
                  included.get("status") == "answered" and included.get("session") == "claude:s-inc",
                  f"{included.get('status')} {included.get('session')} {reason_keys(included)}")
            mismatched = one_scope(published_current("mismatched", [old_row, newer(
                "s-mis", included_ref, [member("User", "/w/g.md", "- mis\n")])], state=pins_state), "native_global", "claude")
            check("a session's own pin that names another snapshot than its census row leaves its launch exclusion "
                  "unknown: the global scope it is chosen for is exclusion_unreadable",
                  mismatched.get("status") == "unknown" and reason_keys(mismatched) == ["exclusion_unreadable"],
                  f"{mismatched.get('status')} {reason_keys(mismatched)}")
            unread = one_scope(published_current("unread-pin", [old_row, newer("s-pin", excluded_ref)]),
                               "native_global", "claude")
            check("a pinned session whose pin this run was given no root to read gives the global scope "
                  "exclusion_unreadable",
                  unread.get("status") == "unknown" and reason_keys(unread) == ["exclusion_unreadable"],
                  f"{unread.get('status')} {reason_keys(unread)}")

            # S-5 / S-8: lines that do not decode, after the chosen outcome and in another transcript
            undecodable_doc = published_current("undecodable", [
                ("claude", "s-u1", [inj("2026-10-20T10:00:00+00:00", [member("User", "/w/g.md", "- u1\n")], cwd=p1),
                                    b"{not json"], {}),
                ("claude", "s-u2", [inj("2026-10-20T08:00:00+00:00", [member("Project", "/w/u2/CLAUDE.md", "- u2\n")],
                                        cwd="/w/u2"), b"{not json either"], {}),
                ("claude", "s-u3", [inj("2026-10-20T07:00:00+00:00", [member("Project", "/w/u3/CLAUDE.md", "- u3\n")],
                                        cwd="/w/u3"), b"{bracketed", {"type": "user", "timestamp": "2026-10-20T09:00:00+00:00"}], {})])
            undecodable_global = one_scope(undecodable_doc, "native_global", "claude")
            elsewhere = [entry for entry in undecodable_global.get("reasons", []) if entry["reason"] == "undecodable_elsewhere"]
            check("a line that does not decode after the chosen outcome makes the scope uncertain, naming the line",
                  undecodable_global.get("status") == "uncertain"
                  and {"reason": "undecodable_after", "line": 2} in [{k: v for k, v in entry.items() if k != "event_id"}
                                                                      for entry in undecodable_global.get("reasons", [])],
                  f"{undecodable_global.get('status')} {reason_keys(undecodable_global)}")
            check("and one in another transcript after its last dated event, not bracketed below the answer, names "
                  "that transcript and line; a bracketed one does not",
                  [(entry.get("session_ref"), entry.get("line")) for entry in elsewhere]
                  == [(session_ref("claude", "s-u2"), 2)], f"{[(entry.get('line')) for entry in elsewhere]}")

        with section('P2.3a: identities from raw values, duplicate members, the unit store and its spans, on the'):
            # ---- P2.3a: identities from raw values, duplicate members, the unit store and its spans, on the
            # PUBLISHED documents (step 0 S-11, S-12 final, S-13 v3, S-22). An expected id is built here by
            # hand from its canonical tuple, never by the function that publishes it.
            def canonical(prefix, *parts):
                text = json.dumps(list(parts), separators=(",", ":"), ensure_ascii=False)
                return f"{prefix}-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:24]}"

            rel_a, rel_b, dup_at, cx = "/w/ra", "/w/rb", "/w/pd", "/w/cx"
            secret_c = "token=" + "C" * 24 + "3"
            spanned = f"# R\n\n- same\n\n- same\n\n- {secret_c} here\n"
            ids_run = published_run("ids", [
                ("claude", "s-ra", [inj("2026-10-20T08:00:00+00:00", [member("User", "/w/g.md", "- older\n")], cwd=rel_a),
                                    inj("2026-10-20T09:00:00+00:00", [member("Project", "./CLAUDE.md", "- rel a\n"),
                                                                      member("User", "/w/g.md", "- g\n")], cwd=rel_a)], {}),
                ("claude", "s-rb", [inj("2026-10-20T09:30:00+00:00", [member("Project", "./CLAUDE.md", "- rel b\n"),
                                                                      member("User", "/w/g.md", "- g\n")], cwd=rel_b)], {}),
                ("claude", "s-dup", [inj("2026-10-20T07:00:00+00:00", [member("Project", f"{dup_at}/CLAUDE.md", "- dup\n"),
                                                                       member("Project", f"{dup_at}/CLAUDE.md", "- dup\n"),
                                                                       member("Project", f"{dup_at}/CLAUDE.md", "- other bytes\n"),
                                                                       member("User", "/w/span.md", spanned)], cwd=dup_at)], {}),
                ("codex", "c-x", [block_meta("c-x", "2026-10-20T09:00:00+00:00", "# Block\n\n- at cx\n", cx)], {}),
                ("codex", "c-y", [{"type": "session_meta", "timestamp": "2026-10-20T09:10:00+00:00",
                                   "payload": {"id": "c-y", "base_instructions": {"text": "# Block\n\n- no cwd\n"}}}], {})])
            check("the identities run was published, its documents crossing clean", "refused" not in ids_run,
                  f"{ids_run.get('refused')} {(ids_run.get('problems') or [])[:2]}")
            ids_store = ids_run.get("store") or {"document": STORE, "versions": {}, "units": {}}
            ids_current = ids_run.get("current") or {"units": []}
            ids_sessions = ids_run.get("sessions") or {"sessions": []}
            clean("the published store validates against its own root in the schema",
                  document_contract_problems(ids_store) if "refused" not in ids_run else ["refused"])

            def crossing(store_in, documents_in):
                """`store_cross_problems`, or the KIND of exception it raised as its one problem: a control
                that plants a store fails by its own name whatever the check does with it."""
                try:
                    return store_cross_problems(store_in, documents_in)
                except Exception as exc:
                    return [f"RAISED {type(exc).__name__}"]

            def versions_at(layer, tail):
                return {(carrier_id, version) for carrier_id, rows in ids_store["versions"].items()
                        for version, row in rows.items() if row["layer"] == layer and row["path"].endswith(tail)}

            relative_ids = {canonical("c", "native", "native_project", "claude", "Project", "./CLAUDE.md",
                                      canonical("s", "scope", "native_project", "claude", where)) for where in (rel_a, rel_b)}
            global_id = canonical("c", "native", "native_global", "claude", "User", "/w/g.md")
            check("a transcript member's carrier id is its raw tuple: two projects' relative CLAUDE.md are two "
                  "carriers, and one absolute path recorded at two cwds is one",
                  {carrier_id for carrier_id, _version in versions_at("native_project", ":./CLAUDE.md")} == relative_ids
                  and {carrier_id for carrier_id, _version in versions_at("native_global", ":/w/g.md")} == {global_id},
                  f"relative={len(versions_at('native_project', ':./CLAUDE.md'))} "
                  f"global={len({carrier_id for carrier_id, _ in versions_at('native_global', ':/w/g.md')})}")
            block_ids = {canonical("c", "native_undivided", "codex", canonical("s", "scope", "native_undivided", "codex", cx)),
                         canonical("c", "native_undivided", "codex", None)}
            check("the Codex block's carrier id carries its scope, and a block with no usable cwd carries null",
                  {carrier_id for carrier_id, rows in ids_store["versions"].items()
                   for row in rows.values() if row["layer"] == "native_undivided"} == block_ids,
                  f"{sorted(carrier_id for carrier_id, rows in ids_store['versions'].items() for row in rows.values() if row['layer'] == 'native_undivided')}")
            block_units = [unit for unit in ids_current["units"] if unit["layer"] == "native_undivided"]
            check("a published Codex block unit says its identity is unknown, beside the carrier id its scope gives it",
                  bool(block_units) and all("loaded text" in str(unit["provenance"].get("identity"))
                                            and unit["carrier_id"] in block_ids for unit in block_units),
                  f"units={len(block_units)} {[unit['provenance'].get('identity') for unit in block_units][:1]}")
            check("the published store states the unit its spans count, as data",
                  ids_store.get("span_unit") == "code_point", f"{ids_store.get('span_unit')}")
            check("every published unit's reference is r- over its carrier version and position, and resolves in the "
                  "store as that block",
                  bool(ids_current["units"])
                  and all(unit.get("unit_ref") == canonical("r", "unit", unit["carrier_id"], unit["version_sha256"], unit["n"])
                          for unit in ids_current["units"])
                  and not crossing(ids_store, {"current": ids_current}),
                  f"units={len(ids_current['units'])} {crossing(ids_store, {'current': ids_current})[:2]}")
            check("a version no scope chose is in the store: the older global file beside the one in force",
                  versions_at("native_global", ":/w/g.md") == {(global_id, sha256_text("- older\n")), (global_id, sha256_text("- g\n"))},
                  f"{len(versions_at('native_global', ':/w/g.md'))} version(s)")
            dup_id = canonical("c", "native", "native_project", "claude", "Project", f"{dup_at}/CLAUDE.md")
            dup_limits = [row for record in ids_sessions["sessions"] if record["session"] == "claude:s-dup"
                          for row in record["limitations"] if row["kind"] == "member_duplicate"]
            dup_units = sorted(unit["sha"] for unit in ids_current["units"] if unit["carrier_id"] == dup_id)
            check("one recorded path twice with equal bytes is one version, one set of units and one member_duplicate "
                  "limitation at its line and ordinal; another byte string at that path is a second version",
                  versions_at("native_project", f":{dup_at}/CLAUDE.md") == {(dup_id, sha256_text("- dup\n")),
                                                                            (dup_id, sha256_text("- other bytes\n"))}
                  and dup_limits == [{"kind": "member_duplicate", "line": 1, "ordinal": 1}]
                  and dup_units == sorted([sha256_text("- dup\n"), sha256_text("- other bytes\n")]),
                  f"versions={len(versions_at('native_project', f':{dup_at}/CLAUDE.md'))} limits={dup_limits} units={len(dup_units)}")
            span_row = (ids_store["versions"].get(canonical("c", "native", "native_global", "claude", "User", "/w/span.md"))
                        or {}).get(sha256_text(spanned)) or {}
            span_units = [ids_store["units"].get(ref) or {} for ref in span_row.get("unit_refs") or []]
            same = [unit for unit in span_units if unit.get("sha") == sha256_text("- same\n\n")]  # a block keeps its blank line
            token = [unit for unit in span_units if secret_c in spanned[unit.get("start", 0):unit.get("end", 0)]]
            check("a store unit's span is its block's place in the RAW version: a repeated fragment is two spans and "
                  "two references, and every span's raw bytes are its digest",
                  span_row.get("length") == len(spanned) and bool(span_units)
                  and all(sha256_text(spanned[unit["start"]:unit["end"]]) == unit["sha"] for unit in span_units)
                  and len(same) == 2 and len({unit["start"] for unit in same}) == 2
                  and len(set(span_row["unit_refs"])) == len(span_units),
                  f"length={span_row.get('length')} units={len(span_units)} same={len(same)}")
            span_expected = [canonical("r", "unit", canonical("c", "native", "native_global", "claude", "User", "/w/span.md"),
                                       sha256_text(spanned), n) for n in (1, 2, 3, 4)]
            check("a version's unit references are r- over hand-made (carrier, version, position) tuples, and one block "
                  "text at two positions is two references",
                  len(set(span_expected)) == 4 and span_row.get("unit_refs") == span_expected
                  and sorted(ref for ref in span_row["unit_refs"]
                             if (ids_store["units"].get(ref) or {}).get("sha") == sha256_text("- same\n\n")) == sorted(span_expected[1:3]),
                  f"listed={len(span_row.get('unit_refs') or [])} distinct={len(set(span_row.get('unit_refs') or []))}")
            check("a redaction that changes the text's length leaves the span raw and the digest the raw fragment's",
                  len(token) == 1 and token[0]["text"] != spanned[token[0]["start"]:token[0]["end"]]
                  and len(token[0]["text"]) != token[0]["end"] - token[0]["start"]
                  and token[0]["sha"] == sha256_text(spanned[token[0]["start"]:token[0]["end"]])
                  and "C" * 24 not in json.dumps(ids_store),
                  f"token units={len(token)}")
            # The store is also what the reference points' OWN carriers resolve into — a catalog guide no
            # transcript records — asked on the production builders before any full run, so a store that
            # lost them fails here by name rather than as the first full run's refusal.
            named_ctx = {"home": str(fixture_home), "state_root": None, "notes": {}, "commit": None,
                         "release_ref": None, "snapshot": {}, "events": []}
            named_guide = carrier("catalog", "claude/guides/named-for-the-store.md",
                                  "# Named\n\n- a catalog rule the store must hold\n")
            try:
                emitted_document("current", [{"layer": "catalog", "producer": "this suite's fixture producer",
                                              "status": "complete", "reasons": [], "carriers": [named_guide]}], named_ctx)
                named_store, named_raised = store_document(named_ctx), None
            except Exception as exc:  # the control names the kind, never the suite
                named_store, named_raised = {"versions": {}}, type(exc).__name__
            check("the store holds every carrier a reference point's layer rows carried, a catalog guide among them",
                  named_raised is None
                  and named_guide["version_sha256"] in (named_store["versions"].get(named_guide["carrier_id"]) or {}),
                  f"raised={named_raised} versions={len(named_store['versions'])}")

            # The store carries what transcripts record, AutoMem included, so its floor is judged on
            # TRANSCRIPT bodies: a credential and a home path in a User, a Project and an AutoMem member and
            # in a Codex block, published by the production path and read back from the written files.
            body_secret = "sk-ant-api03-" + "Tq7" * 14
            body_home = f"{fixture_home}/Documents/a-directory-of-the-owner-s"
            tainted_body = f"\n- a rule naming {body_home}, with apiKeyHelper: {body_secret}\n"
            bodies = {"User": "# Global\n\n- one\n" + tainted_body, "Project": "# Project\n\n- two\n" + tainted_body,
                      "AutoMem": "---\nname: m\n---\n\n- three\n" + tainted_body,
                      "codex": "# Block\n\n- four\n" + tainted_body}
            masked_run = published_run("masked", [
                ("claude", "s-tainted", [inj("2026-10-20T09:00:00+00:00", [
                    member("User", "/w/tainted.md", bodies["User"]),
                    member("Project", f"{p1}/CLAUDE.md", bodies["Project"]),
                    member("AutoMem", f"{d1}/tainted.md", bodies["AutoMem"])], cwd=p1)], {}),
                ("codex", "c-tainted", [block_meta("c-tainted", "2026-10-20T09:00:00+00:00", bodies["codex"], p2)], {})])
            masked_files = {key: (scratch / "p22" / "out-masked" / "inventory" / rel)
                            for key, rel in (("store", STORE_REL), ("sessions", f"{SESSIONS}.json"))}
            masked_bytes = {key: path.read_text(encoding="utf-8") if path.is_file() else "" for key, path in masked_files.items()}
            masked_store = masked_run.get("store") or {"versions": {}, "units": {}}
            masked_units = {version: [masked_store["units"].get(ref) or {} for ref in row["unit_refs"]]
                            for rows in masked_store["versions"].values() for version, row in rows.items()}
            carried_bodies = [kind for kind, text in bodies.items() if masked_units.get(sha256_text(text))]
            check("transcript bodies holding a credential and a home path — a User, a Project and an AutoMem member and "
                  "a Codex block — are in the written store under their raw versions, masked, and neither string is in "
                  "the written store, its map keys included, or in sessions.json",
                  "refused" not in masked_run and all(masked_bytes.values()) and sorted(carried_bodies) == sorted(bodies)
                  and all(any("<REDACTED>" in unit.get("text", "") or "<HOME>" in unit.get("text", "")
                              for unit in masked_units[sha256_text(text)]) for text in bodies.values())
                  and not any(body_secret in text or body_home in text for text in masked_bytes.values()),
                  f"refused={masked_run.get('refused')} files={[key for key, text in masked_bytes.items() if text]} "
                  f"carried={sorted(carried_bodies)} "
                  f"raw={[key for key, text in masked_bytes.items() if body_secret in text or body_home in text]}")

            # The store's cross-record checks, each planted on a copy of the published store.
            planted_store = json.loads(json.dumps(ids_store))
            refs_sorted = sorted(planted_store["units"])
            first_ref = refs_sorted[0] if refs_sorted else "r-" + "0" * 24
            control("a store missing a unit its own version lists is refused by name, with no document beside it",
                    crossing({**planted_store, "units": {ref: row for ref, row in planted_store["units"].items()
                                                         if ref != first_ref}}, {}),
                    f"STORE_UNRESOLVED {first_ref}")
            spilled = json.loads(json.dumps(planted_store))
            if first_ref in spilled["units"]:
                spilled["units"][first_ref]["end"] = 10 ** 6
            control("a unit whose span leaves its version is refused by name", crossing(spilled, {}),
                    "STORE_SPAN_OUTSIDE")
            renumbered = json.loads(json.dumps(planted_store))
            if first_ref in renumbered["units"]:
                renumbered["units"][first_ref]["n"] += 1
            control("a unit whose reference is not the one its version and position derive is refused by name",
                    crossing(renumbered, {}), "STORE_REF_MISMATCH")
            orphaned = json.loads(json.dumps(planted_store))
            if first_ref in orphaned["units"]:
                owner_id = orphaned["units"][first_ref]["carrier_id"]
                orphaned["versions"].pop(owner_id, None)
            control("a unit whose carrier version is not in the store is refused by name, and so is its listing",
                    crossing(orphaned, {}), "STORE_VERSION_ABSENT", "STORE_UNIT_UNLISTED")
            crossed_rows = json.loads(json.dumps(planted_store))
            version_rows = [row for rows in crossed_rows["versions"].values() for row in rows.values()
                            if first_ref not in row["unit_refs"]]
            if version_rows:
                version_rows[0]["unit_refs"].append(first_ref)
            control("a version listing another version's unit is refused by name, and the unit is listed twice",
                    crossing(crossed_rows, {}), "STORE_VERSION_MISMATCH", "STORE_UNIT_UNLISTED")
            aliased = json.loads(json.dumps(ids_current))
            if len(aliased["units"]) > 1:
                aliased["units"][0]["unit_ref"] = next((unit["unit_ref"] for unit in aliased["units"][1:]
                                                        if unit["unit_ref"] != aliased["units"][0]["unit_ref"]),
                                                       aliased["units"][0]["unit_ref"])
            control("a document unit whose reference names another block of the store is refused by name",
                    crossing(planted_store, {"current": aliased}), "STORE_MISMATCH")
            dangling = json.loads(json.dumps(ids_current))
            if dangling["units"]:
                dangling["units"][0]["unit_ref"] = "r-" + "f" * 24
            control("a document unit whose reference the store does not hold is refused by name, at that unit",
                    crossing(planted_store, {"current": dangling}), "STORE_UNRESOLVED current.units[0]")

        with section('P2.3b: occurrences, every located span (M1), a normalised match mapped back or unknown (#1'):
            # ---- P2.3b: occurrences, every located span (M1), a normalised match mapped back or unknown (#14),
            # recorded versions in the store, deliveries, and a Codex block's git (step 0 S-12, S-13, S-19),
            # on the PUBLISHED documents. Expected ids, offsets and digests are computed here by hand.
            def occurring(sessions_in, store_in):
                """`occurrence_cross_problems`, or the KIND of exception it raised as its one problem."""
                try:
                    return occurrence_cross_problems(sessions_in, store_in)
                except Exception as exc:
                    return [f"RAISED {type(exc).__name__}"]

            def occurrences_of(sessions_in, event_id):
                return [row for row in sessions_in.get("occurrences") or [] if row["event_id"] == event_id]

            def event_of(sessions_in, owner, kind):
                found_here = [row for row in sessions_in.get("events") or [] if row["owner"] == owner and row["kind"] == kind]
                return found_here[0] if len(found_here) == 1 else {}

            def prompt_record(at, prompts, **extra):
                return {"type": "attachment", "timestamp": at, "attachment": {"type": "system_prompt", "systemPrompt": prompts},
                        **extra}

            dup_event = event_of(ids_sessions, "claude:s-dup", "native")
            dup_rows = sorted(occurrences_of(ids_sessions, dup_event.get("event_id")), key=lambda row: row["ordinal"])
            dup_texts = ["- dup\n", "- dup\n", "- other bytes\n", spanned]
            dup_ids = [canonical("c", "native", "native_project", "claude", "Project", f"{dup_at}/CLAUDE.md")] * 3 + [
                canonical("c", "native", "native_global", "claude", "User", "/w/span.md")]
            check("every recorded member is an occurrence at its own pointer, its whole field, the version the store "
                  "holds — a duplicate's copy included, pointing at the one version",
                  [(row["ordinal"], row["pointer"], row["carrier_id"], row["version_sha256"], row["start"], row["end"],
                    row["method"], row["occurrence_id"]) for row in dup_rows]
                  == [(n, f"/attachment/files/{n}/content", dup_ids[n], sha256_text(text), 0, len(text), "field",
                       canonical("q", "occurrence", dup_event.get("event_id"), n, f"/attachment/files/{n}/content"))
                      for n, text in enumerate(dup_texts)]
                  and not occurring(ids_sessions, ids_store),
                  f"rows={len(dup_rows)} {occurring(ids_sessions, ids_store)[:2]}")
            delivered_body = "# Session\n\n- rule one\n- rule two\n"
            crlf_field = "<r>\r\n# Session  \r\n\r\n- rule one \r\n- rule two\r\n</r>"
            twice_field = f"<system-reminder>\n{delivered_body}</system-reminder>\n{delivered_body}"
            snapshot_here = {"content_ref": "1" * 64, "output": {"instruction_text": delivered_body}}
            injection_here = canonical("c", "session_injection", "claude", "1" * 64)
            delivered_run = published_run("delivered", [
                ("claude", "s-twice", [prompt_record("2026-10-20T09:00:00+00:00", [twice_field]),
                                       prompt_record("2026-10-20T09:05:00+00:00", [delivered_body],
                                                     isSidechain=True, agentId="a9")], {}),
                ("claude", "s-crlf", [prompt_record("2026-10-20T09:00:00+00:00", ["unrelated", crlf_field])], {}),
                ("claude", "s-shape", [{"type": "request", "timestamp": "2026-10-20T09:00:00+00:00",
                                        "shape": {"system": [{"text": "x"}, {"text": delivered_body}]}}], {}),
                ("codex", "c-str", [{"type": "session_meta", "timestamp": "2026-10-20T09:00:00+00:00",
                                     "payload": {"id": "c-str", "cwd": cx, "base_instructions": "# Block\n\n- a string\n"}}],
                 {})], pin="claude:s-crlf", snapshot=snapshot_here)
            check("the delivered run was published, its occurrences crossing clean", "refused" not in delivered_run,
                  f"{delivered_run.get('refused')} {(delivered_run.get('problems') or [])[:2]}")
            delivered_sessions = delivered_run.get("sessions") or {"events": [], "occurrences": []}
            delivered_store = delivered_run.get("store") or {"versions": {}, "units": {}}
            twice_rows = sorted(occurrences_of(delivered_sessions, event_of(delivered_sessions, "claude:s-twice",
                                                                            "session_injection").get("event_id")),
                                key=lambda row: row["ordinal"])
            twice_starts = [twice_field.find(delivered_body), twice_field.rfind(delivered_body)]
            check("a body found twice in one field is two occurrences, each with its own ordinal and span, and both are "
                  "the selected version",
                  [(row["ordinal"], row["pointer"], row["start"], row["end"], row["method"], row["version_sha256"],
                    row["carrier_id"]) for row in twice_rows]
                  == [(n, "/attachment/systemPrompt/0", start, start + len(delivered_body), "exact",
                       sha256_text(delivered_body), injection_here) for n, start in enumerate(twice_starts)]
                  and twice_starts[0] != twice_starts[1],
                  f"rows={[(row['ordinal'], row['method'], row['start']) for row in twice_rows]}")
            crlf_rows = occurrences_of(delivered_sessions, event_of(delivered_sessions, "claude:s-crlf",
                                                                    "session_injection").get("event_id"))
            crlf_start = crlf_field.index("# Session")
            crlf_end = crlf_field.index("- rule two") + len("- rule two")
            crlf_recorded = crlf_field[crlf_start:crlf_end]
            crlf_version = (delivered_store["versions"].get(injection_here) or {}).get(sha256_text(crlf_recorded)) or {}
            check("M1: a CRLF and trailing-space body against the LF snapshot reaches the locator and the publication, "
                  "mapped back to its own bytes: a real occurrence, and its raw digest beside the selected one",
                  [(row["pointer"], row["start"], row["end"], row["method"], row["sha256"], row["version_sha256"])
                   for row in crlf_rows]
                  == [("/attachment/systemPrompt/1", crlf_start, crlf_end, "normalised", sha256_text(crlf_recorded),
                       sha256_text(crlf_recorded))]
                  and sha256_text(crlf_recorded) != sha256_text(delivered_body)
                  and crlf_version.get("length") == len(crlf_recorded) and bool(crlf_version.get("unit_refs")),
                  f"rows={[(row['method'], row['start'], row['end']) for row in crlf_rows]} in_store={bool(crlf_version)}")
            shape_rows = occurrences_of(delivered_sessions, event_of(delivered_sessions, "claude:s-shape",
                                                                     "session_injection").get("event_id"))
            check("a request shape's body is an occurrence at its own indexed pointer",
                  [(row["pointer"], row["method"], row["start"], row["end"]) for row in shape_rows]
                  == [("/shape/system/1/text", "field", 0, len(delivered_body))],
                  f"{[(row['pointer'], row['method']) for row in shape_rows]}")
            string_rows = occurrences_of(delivered_sessions, event_of(delivered_sessions, "codex:c-str", "native").get("event_id"))
            check("a Codex block recorded as a plain string is an occurrence at /payload/base_instructions",
                  [(row["pointer"], row["method"]) for row in string_rows] == [("/payload/base_instructions", "field")],
                  f"{[(row['pointer'], row['method']) for row in string_rows]}")
            delivered_notes = ((delivered_run.get("current") or {}).get("produced_by") or {}).get("notes") or {}
            check("a delivery is confirmed only by a usable recorded occurrence of a session's main owner: a sidechain's "
                  "copy is not counted",
                  (delivered_notes.get("transcripts") or {}).get("delivery_confirmed") == 3
                  and len(occurrences_of(delivered_sessions, event_of(delivered_sessions, "claude:s-twice#sidechain:a9",
                                                                      "session_injection").get("event_id"))) == 1,
                  f"{(delivered_notes.get('transcripts') or {}).get('delivery_confirmed')}")
            sessions_written = scratch / "p22" / "out-delivered" / "inventory" / f"{SESSIONS}.json"
            check("sessions.json states the unit its occurrences' spans count, as data, read from the written file",
                  sessions_written.is_file()
                  and json.loads(sessions_written.read_text(encoding="utf-8")).get("span_unit") == "code_point",
                  f"written={sessions_written.is_file()}")
            # #14: a normalised match whose bytes cannot be recovered is an unknown, kept as evidence. Reached
            # through its own seam: an offset map that is off by one gives bytes that no longer normalise.
            kept_index = globals()["_normalised_index"]
            try:
                globals()["_normalised_index"] = lambda text: (kept_index(text)[0], [at + 1 for at in kept_index(text)[1]])
                unmapped_run = published_run("unmapped", [
                    ("claude", "s-crlf", [prompt_record("2026-10-20T09:00:00+00:00", [crlf_field])], {})],
                    pin="claude:s-crlf", snapshot=snapshot_here)
            finally:
                globals()["_normalised_index"] = kept_index
            unmapped_sessions = unmapped_run.get("sessions") or {"events": [], "occurrences": []}
            unmapped_rows = unmapped_sessions.get("occurrences") or []
            unmapped_notes = ((unmapped_run.get("current") or {}).get("produced_by") or {}).get("notes") or {}
            check("#14: a normalised match whose offsets cannot be recovered is recorded_unmapped, kept as evidence with "
                  "no version, span or digest, adds no recorded version, and confirms no delivery",
                  "refused" not in unmapped_run
                  and [(row["method"], row["reason"], row["version_sha256"], row["start"], row["end"], row["sha256"])
                       for row in unmapped_rows] == [("unmapped", "recorded_unmapped", None, None, None, None)]
                  and injection_here not in (unmapped_run.get("store") or {}).get("versions", {})
                  and (unmapped_notes.get("transcripts") or {}).get("delivery_confirmed") == 0,
                  f"refused={unmapped_run.get('refused')} rows={[(row['method'], row['reason']) for row in unmapped_rows]}")
            unmapped_record = next((row for row in unmapped_sessions.get("sessions") or []
                                    if row["transcript"]["id"] == "s-crlf"), {})
            check("a delivery's one reason is its first broken link — an occurrence of its own body whose offsets could "
                  "not be recovered, naming its event",
                  unmapped_record.get("delivery") == {
                      "status": "unknown", "reason": "recorded_unmapped",
                      "event_refs": [event_of(unmapped_sessions, "claude:s-crlf", "session_injection").get("event_id")]},
                  f"{unmapped_record.get('delivery')}")
            # The RECORDED bytes come from a transcript, so they are judged like every transcript body: a
            # credential and a home path in a normalised match, on the written store and sessions files.
            recorded_secret = "sk-ant-api03-" + "Rc9" * 14
            recorded_home = f"{fixture_home}/Documents/a-directory-of-the-owner-s"
            recorded_body = f"# Session\n\n- a rule naming {recorded_home}, with apiKeyHelper: {recorded_secret}\n"
            recorded_field = "<r>\r\n" + recorded_body.replace("\n", "  \r\n") + "</r>"
            recorded_run = published_run("recorded", [
                ("claude", "s-rec", [prompt_record("2026-10-20T09:00:00+00:00", [recorded_field])], {})],
                pin="claude:s-rec", snapshot={"content_ref": "2" * 64, "output": {"instruction_text": recorded_body}})
            recorded_out = scratch / "p22" / "out-recorded" / "inventory"
            recorded_bytes = {name: (recorded_out / rel).read_text(encoding="utf-8") if (recorded_out / rel).is_file() else ""
                              for name, rel in (("store", STORE_REL), ("sessions", f"{SESSIONS}.json"))}
            recorded_rows = (recorded_run.get("sessions") or {}).get("occurrences") or []
            recorded_versions = (recorded_run.get("store") or {}).get("versions", {}).get(
                canonical("c", "session_injection", "claude", "2" * 64)) or {}
            recorded_units = [(recorded_run.get("store") or {}).get("units", {}).get(ref) or {}
                              for row in recorded_versions.values() for ref in row["unit_refs"]]
            check("a RECORDED session injection holding a credential and a home path is in the written store under its "
                  "own version, masked, and neither string is in the written store or sessions.json",
                  "refused" not in recorded_run and all(recorded_bytes.values())
                  and [row["method"] for row in recorded_rows] == ["normalised"]
                  and len(recorded_versions) == 1 and bool(recorded_units)
                  and any("<REDACTED>" in unit.get("text", "") or "<HOME>" in unit.get("text", "") for unit in recorded_units)
                  and not any(recorded_secret in text or recorded_home in text for text in recorded_bytes.values()),
                  f"refused={recorded_run.get('refused')} methods={[row['method'] for row in recorded_rows]} "
                  f"versions={len(recorded_versions)} raw={[name for name, text in recorded_bytes.items() if recorded_secret in text or recorded_home in text]}")
            # S-19: a Codex block's git, the commit hash kept and every userinfo removed, a credential-shaped one included.
            github_token = "ghp_" + "A1b2" * 9
            git_run = published_run("git", [
                ("codex", "c-g1", [{"type": "session_meta", "timestamp": "2026-10-20T09:00:00+00:00",
                                    "payload": {"id": "c-g1", "cwd": "/w/g1", "base_instructions": {"text": "# B\n\n- one\n"},
                                                "git": {"commit_hash": "abc1234def", "branch": "feature/x",
                                                        "repository_url": "https://user:shortpass@example.com/org/repo.git"}}}], {}),
                ("codex", "c-g2", [{"type": "session_meta", "timestamp": "2026-10-20T09:00:00+00:00",
                                    "payload": {"id": "c-g2", "cwd": "/w/g2", "base_instructions": {"text": "# B\n\n- two\n"},
                                                "git": {"commit_hash": "0123456789abcdef0123456789abcdef01234567",
                                                        "branch": "main",
                                                        "repository_url": f"https://x-access-token:{github_token}@github.com/org/repo.git"}}}],
                 {})])
            git_units = sorted({((unit["provenance"].get("git") or {}).get("repository_url"),
                                 (unit["provenance"].get("git") or {}).get("commit_hash"),
                                 (unit["provenance"].get("git") or {}).get("branch"))
                                for unit in (git_run.get("current") or {}).get("units", []) if unit["layer"] == "native_undivided"})
            git_rows = sorted(((row.get("git") or {}).get("repository_url"), (row.get("git") or {}).get("commit_hash"))
                              for row in (git_run.get("sessions") or {}).get("occurrences", []))
            git_out = scratch / "p22" / "out-git" / "inventory"
            git_bytes = "".join((git_out / rel).read_text(encoding="utf-8") for rel in ("current.json", f"{SESSIONS}.json")
                                if (git_out / rel).is_file())
            check("S-19: a Codex block's git is published — the commit hash kept, the branch, and the repository URL "
                  "without its userinfo, a token-shaped one included — on its units and its occurrences",
                  "refused" not in git_run and bool(git_bytes)
                  and git_units == [("https://example.com/org/repo.git", "abc1234def", "feature/x"),
                                    ("https://github.com/org/repo.git", "0123456789abcdef0123456789abcdef01234567", "main")]
                  and git_rows == [("https://example.com/org/repo.git", "abc1234def"),
                                   ("https://github.com/org/repo.git", "0123456789abcdef0123456789abcdef01234567")]
                  and not any(text in git_bytes for text in ("shortpass", github_token, "x-access-token", "user:")),
                  f"refused={git_run.get('refused')} units={len(git_units)} rows={len(git_rows)}")
            check("a scp-like repository address loses its user too, and a commit hash that is not one is null",
                  without_userinfo("git@github.com:org/repo.git") == "github.com:org/repo.git"
                  and git_of({"git": {"commit_hash": "not a hash", "branch": "", "repository_url": None}})
                  == {"commit_hash": None, "branch": None, "repository_url": None},
                  f"{without_userinfo('git@github.com:org/repo.git')}")
            # The occurrences' cross-record checks, each planted on a copy of the published sessions.json.
            planted_sessions = json.loads(json.dumps(delivered_sessions))
            first_row = (planted_sessions.get("occurrences") or [{}])[0]

            def with_first(**changes):
                copy = json.loads(json.dumps(planted_sessions))
                if copy.get("occurrences"):
                    copy["occurrences"][0].update(changes)
                return copy

            control("an occurrence whose event is not published is refused by name",
                    occurring(with_first(event_id="e-" + "f" * 24), delivered_store), "OCCURRENCE_EVENT_UNRESOLVED")
            control("an occurrence whose id is not the one its event, ordinal and pointer derive is refused by name",
                    occurring(with_first(ordinal=(first_row.get("ordinal") or 0) + 7), delivered_store),
                    "OCCURRENCE_ID_MISMATCH")
            control("a mapped occurrence whose version the store does not hold is refused by name",
                    occurring(with_first(version_sha256="0" * 64, sha256="0" * 64), delivered_store),
                    "OCCURRENCE_VERSION_UNRESOLVED")
            control("a mapped occurrence whose span is not its version's length is refused by name",
                    occurring(with_first(end=(first_row.get("end") or 0) + 1), delivered_store), "OCCURRENCE_SPAN_MISMATCH")
            control("a mapped occurrence whose digest is not its version is refused by name",
                    occurring(with_first(sha256="1" * 64), delivered_store), "OCCURRENCE_DIGEST_MISMATCH")
            control("an unmapped occurrence that carries a version is refused by name",
                    occurring(with_first(method="unmapped", reason="recorded_unmapped"), delivered_store),
                    "OCCURRENCE_UNMAPPED_INCONSISTENT")
            control("a mapped occurrence that names a reason is refused by name",
                    occurring(with_first(reason="recorded_unmapped"), delivered_store), "OCCURRENCE_UNMAPPED_INCONSISTENT")
            doubled = json.loads(json.dumps(planted_sessions))
            doubled["occurrences"] = doubled.get("occurrences", [])[:1] * 2 + doubled.get("occurrences", [])[1:]
            control("two occurrences under one id are refused by name", occurring(doubled, delivered_store),
                    "OCCURRENCE_DUPLICATE")

        with section("P2.4a: every session's OWN pin and snapshot (step 0 S-14, S-15, S-16, S-25; lead rulings o"):
            # ---- P2.4a: every session's OWN pin and snapshot (step 0 S-14, S-15, S-16, S-25; lead rulings on
            # the P2.4 plan). Pins and snapshots are fixtures under this suite's own state roots; none of the
            # sessions below is the `--pin`, and each answer is read from the PUBLISHED sessions.json.
            deliver_state = scratch / "p24" / "deliver-state"
            deliver_body = "# Session\n\n- a delivered rule\n"
            deliver_ref = plant_snapshot(deliver_state, deliver_body)
            broken_ref = plant_snapshot(deliver_state, "# Session\n\n- a snapshot whose file was changed\n")
            (deliver_state / "sessions" / "snapshots" / broken_ref / "CLAUDE.md").write_text("changed\n", encoding="utf-8")
            gone_ref = "3" * 64  # a pin names it; no snapshot of it exists
            for ident in ("s-ok", "s-unbound", "s-nopath", "s-damaged", "s-unrecorded", "s-sidechain"):
                plant_pin(deliver_state, ident, deliver_ref)
            plant_pin(deliver_state, "s-named", deliver_ref, names="s-other")
            plant_pin(deliver_state, "s-cref", broken_ref)
            plant_pin(deliver_state, "s-gone", gone_ref)
            plant_pin(deliver_state, "s-broken", broken_ref)
            (deliver_state / "sessions" / "pins" / "claude" / "s-failed.json").write_text("{not json", encoding="utf-8")
            d_at, d_late = "2026-10-21T09:00:00+00:00", "2026-10-21T09:00:30+00:00"
            d_native = inj(d_at, [member("User", "/w/g.md", "- g\n")], cwd=p1)
            d_body = prompt_record(d_late, [f"<r>{deliver_body}</r>"])

            def pinned_row(ident, records_in, census_ref=deliver_ref, **fields):
                return ("claude", ident, records_in, {"pin": {"content_ref": census_ref}, **fields})

            deliveries = published_run("deliveries", [
                pinned_row("s-ok", [d_native, d_body]),
                ("claude", "s-none", [d_native, d_body], {}),
                ("codex", "c-id", [block_meta("c-id", d_at, "# Block\n\n- a block\n", p1)], {"pin": {"content_ref": deliver_ref}}),
                pinned_row("s-absent", [d_native, d_body]),
                pinned_row("s-named", [d_native, d_body]),
                pinned_row("s-cref", [d_native, d_body]),
                pinned_row("s-failed", [d_native, d_body]),
                pinned_row("s-gone", [d_native, d_body], gone_ref),
                pinned_row("s-broken", [d_native, d_body], broken_ref),
                pinned_row("s-unbound", [d_native, d_body], sha256=None, versions=[]),
                pinned_row("s-nopath", [d_native, d_body], path=None),
                pinned_row("s-damaged", [d_native, prompt_record(d_late, [3, "<r>another field</r>"])]),
                pinned_row("s-unrecorded", [d_native]),
                pinned_row("s-sidechain", [d_native, prompt_record(d_late, [deliver_body], isSidechain=True, agentId="a7")])],
                state=deliver_state)
            check("the deliveries run was published, its occurrences crossing clean", "refused" not in deliveries,
                  f"{deliveries.get('refused')} {(deliveries.get('problems') or [])[:2]}")
            delivered_records = {row["transcript"]["id"]: row for row in (deliveries.get("sessions") or {}).get("sessions") or []}
            clean("and its sessions.json validates, pins and deliveries included",
                  document_contract_problems(deliveries["sessions"]) if "sessions" in deliveries else ["refused"])

            def delivery_is(ident):
                row = (delivered_records.get(ident) or {}).get("delivery") or {}
                return row.get("status"), row.get("reason")

            def pin_is(ident):
                row = (delivered_records.get(ident) or {}).get("pin") or {}
                return row.get("status"), row.get("reason")

            ok_injection = [event["event_id"] for event in (deliveries.get("sessions") or {}).get("events") or []
                            if event["owner"] == "claude:s-ok" and event["kind"] == "session_injection"]
            check("a session whose own body its own owner holds is a confirmed delivery, naming that event, and its pin "
                  "is read with the snapshot's baseline and its flag",
                  (delivered_records.get("s-ok") or {}).get("delivery") == {"status": "confirmed", "reason": None,
                                                                            "event_refs": ok_injection}
                  and len(ok_injection) == 1
                  and (delivered_records.get("s-ok") or {}).get("pin") == {
                      "status": "read", "reason": None, "content_ref": deliver_ref, "baseline_ref": "ref1",
                      "include_global_instructions": True},
                  f"{(delivered_records.get('s-ok') or {}).get('delivery')} {(delivered_records.get('s-ok') or {}).get('pin')}")
            for ident, step, expected_pin, expected in (
                    ("s-none", "the pin chain: no pin recorded", ("unpinned", "unpinned"), ("unknown", "unpinned")),
                    ("c-id", "the pin chain: a Codex rollout", ("unknown", "id_space"), ("unknown", "id_space")),
                    ("s-absent", "the pin chain: a pin the census names and the state does not hold",
                     ("unknown", "pin_absent"), ("unknown", "pin_absent")),
                    ("s-named", "the pin chain: the pin at this path names another session",
                     ("unknown", "pin_mismatch"), ("unknown", "pin_mismatch")),
                    ("s-cref", "the pin chain: the pin names another snapshot than the census",
                     ("unknown", "pin_content_ref_mismatch"), ("unknown", "pin_content_ref_mismatch")),
                    ("s-failed", "the pin chain: a pin that does not read", ("unknown", "input_failed"),
                     ("unknown", "input_failed")),
                    ("s-gone", "the snapshot: a read pin whose snapshot is not there", ("read", None),
                     ("unknown", "snapshot_absent")),
                    ("s-broken", "the snapshot: a read pin whose snapshot does not verify", ("read", None),
                     ("unknown", "input_failed")),
                    ("s-unbound", "the transcript read: no binding", ("read", None), ("unknown", "unbound")),
                    ("s-nopath", "the transcript read: no path", ("read", None), ("unknown", "no_path")),
                    ("s-unrecorded", "no link broken and no recorded occurrence: not a non-delivery", ("read", None),
                     ("unknown", "no_record")),
                    ("s-sidechain", "a sidechain's copy is not its session's own delivery", ("read", None),
                     ("unknown", "no_record"))):
                check(f"a delivery's one reason is its first broken link — {step}",
                      pin_is(ident) == expected_pin and delivery_is(ident) == expected,
                      f"pin={pin_is(ident)} delivery={delivery_is(ident)}")
            # A session's selection is the shared inventory its own verified snapshot is, or the one reason of the
            # first broken link of its pin and snapshot: the transcript's links are the delivery's, never its own.
            selection_expected = {"s-none": ("unpinned", "unpinned", None), "c-id": ("unknown", "id_space", None),
                                  "s-absent": ("unknown", "pin_absent", None), "s-named": ("unknown", "pin_mismatch", None),
                                  "s-cref": ("unknown", "pin_content_ref_mismatch", None),
                                  "s-failed": ("unknown", "input_failed", None), "s-gone": ("unknown", "snapshot_absent", None),
                                  "s-broken": ("unknown", "input_failed", None),
                                  **{ident: ("read", None, inventory_id("selection", deliver_ref))
                                     for ident in ("s-ok", "s-unbound", "s-nopath", "s-unrecorded", "s-sidechain", "s-damaged")}}
            selection_got = {ident: tuple(((delivered_records.get(ident) or {}).get("selection") or {}).get(key)
                                          for key in ("status", "reason", "inventory_ref")) for ident in selection_expected}
            deliver_selection = ((deliveries.get("shared") or {}).get(f"selection-{inventory_id('selection', deliver_ref)}")
                                 or {})
            deliver_catalog = next((row for row in deliver_selection.get("layers") or [] if row["layer"] == "catalog"), {})
            check("POSITIVE: the deliveries run's selection catalog, its snapshot's shared selection inventory, is complete "
                  "(lead ruling 3, 14:55)",
                  deliver_catalog.get("status") == "complete" and deliver_catalog.get("reasons") == []
                  and deliver_catalog.get("units", 0) > 0,
                  f"{deliver_catalog} inventories={sorted(deliveries.get('shared') or {})}")
            check("a session's selection: its own snapshot's shared inventory, or the first broken link of its pin and "
                  "snapshot, and never a transcript's link",
                  selection_got == selection_expected,
                  f"{ {ident: got for ident, got in selection_got.items() if got != selection_expected[ident]} }")
            damaged_injection = [event["event_id"] for event in (deliveries.get("sessions") or {}).get("events") or []
                                 if event["owner"] == "claude:s-damaged" and event["kind"] == "session_injection"]
            check("a delivery's one reason is its first broken link — a damaged injection event of its own owner, "
                  "named, with no usable occurrence",
                  (delivered_records.get("s-damaged") or {}).get("delivery") == {
                      "status": "unknown", "reason": "locator_element_rejected", "event_refs": damaged_injection}
                  and len(damaged_injection) == 1,
                  f"{(delivered_records.get('s-damaged') or {}).get('delivery')}")
            check("a Codex row's census content_ref is read for nothing, and a pin whose snapshot is not read names "
                  "no baseline",
                  ((delivered_records.get("c-id") or {}).get("pin") or {}).get("content_ref") is None
                  and ((delivered_records.get("s-gone") or {}).get("pin") or {}).get("baseline_ref") is None
                  and ((delivered_records.get("s-gone") or {}).get("pin") or {}).get("content_ref") == gone_ref,
                  f"{(delivered_records.get('c-id') or {}).get('pin')} {(delivered_records.get('s-gone') or {}).get('pin')}")

            # S-25, two sessions through the production acquisition: a failed pin@(claude, X) reaches X's own
            # record and the aggregate scope X's event is chosen for; a failed snapshot@(claude, X) reaches X's
            # own record and nothing else. X's native events stay published either way.
            two_state = scratch / "p24" / "two-state"
            x_body, y_body = "# Session\n\n- x\n", "# Session\n\n- y\n"
            x_ref, y_ref = plant_snapshot(two_state, x_body), plant_snapshot(two_state, y_body)
            plant_pin(two_state, "s-x", x_ref)
            plant_pin(two_state, "s-y", y_ref)
            two_rows = [
                pinned_row("s-y", [inj("2026-10-21T09:00:00+00:00", [member("User", "/w/g.md", "- y\n"),
                                                                     member("Project", f"{p2}/CLAUDE.md", "- y at p2\n")],
                                       cwd=p2), prompt_record("2026-10-21T09:00:30+00:00", [y_body])], y_ref),
                pinned_row("s-x", [inj("2026-10-21T10:00:00+00:00", [member("User", "/w/g.md", "- x\n"),
                                                                     member("Project", f"{p1}/CLAUDE.md", "- x at p1\n")],
                                       cwd=p1), prompt_record("2026-10-21T10:00:30+00:00", [x_body])], x_ref)]

            def two_with(label, damage=None):
                case = scratch / "p24" / f"two-{label}"
                shutil.copytree(two_state, case)
                if damage is not None:
                    damage(case)
                return published_run(f"two-{label}", two_rows, state=case)

            two_clean = two_with("clean")
            two_pin = two_with("pin", lambda case: (case / "sessions" / "pins" / "claude" / "s-x.json").write_text(
                "{not json", encoding="utf-8"))
            two_snapshot = two_with("snapshot", lambda case: (case / "sessions" / "snapshots" / x_ref / "CLAUDE.md").write_text(
                "changed\n", encoding="utf-8"))

            def two_parts(published):
                """`(records by id, native events, injection events by owner, scope rows by (layer, scope))`."""
                sessions_here = published.get("sessions") or {}
                events_here = sessions_here.get("events") or []
                return ({row["transcript"]["id"]: row for row in sessions_here.get("sessions") or []},
                        sorted(json.dumps(event, sort_keys=True) for event in events_here if event["kind"] == "native"),
                        {owner: sorted(json.dumps(event, sort_keys=True) for event in events_here
                                       if event["kind"] == "session_injection" and event["owner"] == owner)
                         for owner in ("claude:s-x", "claude:s-y")},
                        {(row["layer"], row["host"], row["scope"]): row
                         for row in (published.get("current") or {}).get("scopes") or []})

            clean_parts, pin_parts, snap_parts = two_parts(two_clean), two_parts(two_pin), two_parts(two_snapshot)
            check("the two-session runs were published", not any("refused" in run_here for run_here in
                                                                  (two_clean, two_pin, two_snapshot)),
                  f"{[run_here.get('refused') for run_here in (two_clean, two_pin, two_snapshot)]}")
            x_occurrences = [row["carrier_id"] for row in (two_clean.get("sessions") or {}).get("occurrences") or []
                             if row["pointer"].startswith("/attachment/systemPrompt/")]
            check("each session's own body is looked for in its own transcript, under its own injection carrier",
                  sorted(x_occurrences) == sorted([canonical("c", "session_injection", "claude", x_ref),
                                                   canonical("c", "session_injection", "claude", y_ref)])
                  and clean_parts[0].get("s-x", {}).get("delivery", {}).get("status") == "confirmed"
                  and clean_parts[0].get("s-y", {}).get("delivery", {}).get("status") == "confirmed",
                  f"{len(x_occurrences)} occurrence(s)")
            global_key = ("native_global", "claude", None)
            check("S-25: a failed pin@(claude, X) changes X's own pin and delivery, makes the global scope X's event is "
                  "chosen for exclusion_unreadable, and leaves the other session, every other scope and X's native "
                  "events as they were",
                  pin_parts[0].get("s-y") == clean_parts[0].get("s-y")
                  and {key: value for key, value in pin_parts[0].get("s-x", {}).items()
                       if key not in ("pin", "delivery", "selection", "event_refs", "segment_refs")}
                  == {key: value for key, value in clean_parts[0].get("s-x", {}).items()
                      if key not in ("pin", "delivery", "selection", "event_refs", "segment_refs")}
                  and (pin_parts[0].get("s-x", {}).get("pin") or {}).get("reason") == "input_failed"
                  and (pin_parts[0].get("s-x", {}).get("selection") or {}).get("reason") == "input_failed"
                  and (pin_parts[0].get("s-x", {}).get("delivery") or {}).get("reason") == "input_failed"
                  and pin_parts[1] == clean_parts[1] and pin_parts[2]["claude:s-y"] == clean_parts[2]["claude:s-y"]
                  and (clean_parts[3].get(global_key) or {}).get("status") == "answered"
                  and (pin_parts[3].get(global_key) or {}).get("status") == "unknown"
                  and reason_keys(pin_parts[3].get(global_key) or {}) == ["exclusion_unreadable"]
                  and {key: row for key, row in pin_parts[3].items() if key != global_key}
                  == {key: row for key, row in clean_parts[3].items() if key != global_key},
                  f"global={(pin_parts[3].get(global_key) or {}).get('status')} "
                  f"x_pin={(pin_parts[0].get('s-x', {}).get('pin') or {}).get('reason')}")

            def x_segments(published):
                """X's segments in `published`: `(native event refs they name, injection states)`."""
                record = (two_parts(published)[0]).get("s-x") or {}
                rows = [row for row in (published.get("sessions") or {}).get("segments") or []
                        if row["session_ref"] == record.get("session_ref")]
                return ({row["in_force"]["native"]["event_ref"] for row in rows},
                        {(row["in_force"]["session_injection"]["state"], row["in_force"]["session_injection"]["reason"])
                         for row in rows})

            check("S-25: and X's segments name the same native events while its injection is unsought by "
                  "input_failed in every one: a failed pin leaves no injection anyone could look for",
                  bool(x_segments(two_clean)[0]) and x_segments(two_pin)[0] == x_segments(two_clean)[0]
                  and x_segments(two_pin)[1] == {("unsought", "input_failed")},
                  f"{x_segments(two_pin)} / {x_segments(two_clean)}")
            check("S-25: a failed snapshot@(claude, X) leaves X's pin read and its exclusion known, every scope and the "
                  "other session as they were, and X's native events published; X's delivery says why",
                  snap_parts[0].get("s-y") == clean_parts[0].get("s-y")
                  and (snap_parts[0].get("s-x", {}).get("pin") or {}).get("status") == "read"
                  and (snap_parts[0].get("s-x", {}).get("pin") or {}).get("baseline_ref") is None
                  and (snap_parts[0].get("s-x", {}).get("delivery") or {}).get("reason") == "input_failed"
                  and snap_parts[1] == clean_parts[1] and snap_parts[2]["claude:s-y"] == clean_parts[2]["claude:s-y"]
                  and snap_parts[3] == clean_parts[3],
                  f"x={(snap_parts[0].get('s-x', {}).get('delivery') or {}).get('reason')} "
                  f"scopes_same={snap_parts[3] == clean_parts[3]}")

            # An occurrence's carrier is the one its event recorded at its ordinal, or its session's own injection
            # carrier, and the place its pointer names holds the layer of the version it names (carried from P2.3b)
            carrier_sessions = deliveries.get("sessions") or {"events": [], "occurrences": [], "sessions": []}
            carrier_store = deliveries.get("store") or {"versions": {}, "units": {}}
            ok_native = next((event for event in carrier_sessions["events"]
                              if event["owner"] == "claude:s-ok" and event["kind"] == "native"), {})
            check("a native event publishes every member it recorded, at its ordinal, by carrier and version",
                  ok_native.get("members") == [{"ordinal": 0, "version_sha256": sha256_text("- g\n"), "carrier_id": canonical(
                      "c", "native", "native_global", "claude", "User", "/w/g.md")}],
                  f"{ok_native.get('members')}")
            clean("the deliveries run's occurrences hold their events' members and their sessions' own carriers",
                  occurring(carrier_sessions, carrier_store))
            foreign = canonical("c", "session_injection", "claude", "4" * 64)
            for label, pick, change, codes in (
                    ("a native occurrence naming another carrier than its event recorded at its ordinal",
                     lambda row: row["pointer"].startswith("/attachment/files/"),
                     lambda row: row.update(carrier_id=canonical("c", "session_injection", "claude", deliver_ref)),
                     ("OCCURRENCE_CARRIER_MISMATCH",)),
                    ("an injection occurrence naming another snapshot's injection carrier than its session's own",
                     lambda row: row["pointer"].startswith("/attachment/systemPrompt/"),
                     lambda row: row.update(carrier_id=foreign), ("OCCURRENCE_CARRIER_MISMATCH",)),
                    ("a member occurrence whose pointer names a system prompt, its version a native layer's",
                     lambda row: row["pointer"].startswith("/attachment/files/"),
                     lambda row: row.update(pointer="/attachment/systemPrompt/0", occurrence_id=canonical(
                         "q", "occurrence", row["event_id"], row["ordinal"], "/attachment/systemPrompt/0")),
                     ("OCCURRENCE_LAYER_MISMATCH",))):
                planted_rows = json.loads(json.dumps(carrier_sessions))
                target = next((row for row in planted_rows["occurrences"] if pick(row)), None)
                if target is not None:
                    change(target)
                control(label, occurring(planted_rows, carrier_store), *codes)
            kept_event_occurrences = globals()["event_occurrences"]

            def astray_occurrences(event, injection_id=None):
                return kept_event_occurrences(event, foreign if injection_id else injection_id)

            globals()["event_occurrences"] = astray_occurrences
            try:
                astray = published_run("astray", [pinned_row("s-ok", [d_native, d_body])], state=deliver_state)
            finally:
                globals()["event_occurrences"] = kept_event_occurrences
            control("a published run whose injection occurrence names another snapshot's carrier is refused by name",
                    astray.get("problems") or [str(astray.get("refused"))], "OCCURRENCE_CARRIER_MISMATCH")

            # The `--pin` takes its session's own entry when the census names its pin, and is evidence about its
            # pin only when the census names none (S-15)
            pin_mis_ctx, pin_evidence_ctx = {"native_roots": {}, "notes": {}}, {"native_roots": {}, "notes": {}}
            pin_mis_raised = _raised(lambda: freeze_inputs(scratch / "p24" / "frozen-pin-mis", REPO, pins_state, None,
                                                           "claude:s-mis", pin_mis_ctx,
                                                           [{"host": "claude", "id": "s-mis", "pin": included_ref}]))
            pin_evidence_raised = _raised(lambda: freeze_inputs(scratch / "p24" / "frozen-pin-evidence", REPO, pins_state,
                                                                None, "claude:s-mis", pin_evidence_ctx, []))
            check("the --pin of a session whose census names a pin takes that session's own entry: a pin naming another "
                  "snapshot than the census is no selection, and says why",
                  pin_mis_raised is None and pin_mis_ctx.get("pin_record") is None
                  and [(row["outcome"], row["reason"]) for row in pin_mis_ctx.get("omissions") or [] if row["input"] == "pin"]
                  == [("failed", "pin_content_ref_mismatch")],
                  f"raised={pin_mis_raised is not None} {[row for row in pin_mis_ctx.get('omissions') or [] if row['input'] == 'pin']}")
            check("a --pin with no census row is evidence about its pin only: read, with its snapshot",
                  pin_evidence_raised is None and (pin_evidence_ctx.get("pin_record") or {}).get("content_ref") == excluded_ref
                  and (pin_evidence_ctx.get("snapshot") or {}).get("content_ref") == excluded_ref,
                  f"raised={pin_evidence_raised is not None}")
            elsewhere_run = published_run("pin-elsewhere", [old_row], pin="claude:s-elsewhere", state=pins_state)
            check("a --pin with no census row says its delivery is unknown: no transcript of it is read",
                  (((elsewhere_run.get("current") or {}).get("produced_by") or {}).get("notes") or {}).get(
                      "transcripts", {}).get("pin_delivery") == "no_census_session",
                  f"{(((elsewhere_run.get('current') or {}).get('produced_by') or {}).get('notes') or {}).get('transcripts', {}).get('pin_delivery')}")

        with section('P2.4b: shared inventories (step 0 S-22, S-25; lead rulings 5-7 on the P2.4 plan), through '):
            # ---- P2.4b: shared inventories (step 0 S-22, S-25; lead rulings 5-7 on the P2.4 plan), through the
            # production acquisition and `shared_inventories`, which is what `run` calls. Fixtures only.
            def published_shared(name, transcripts, state_here, pin=None):
                """The shared inventories, sessions.json and the store as `run` makes, crosses and WRITES them
                over a fixture state, read back from the written files; `{"refused", "message"}` when refused."""
                run_at = scratch / "p24b" / f"run-{name}"
                rows_here = []
                for host, ident, records_in, fields in transcripts:
                    path_here = raw_lines(scratch / "p24b" / name / f"{ident}.jsonl", records_in)
                    rows_here.append({**census_row(host, ident, path_here), **fields})
                run_at.mkdir(parents=True, exist_ok=True)
                (run_at / CENSUS).write_text(json.dumps({"transcripts": rows_here}), encoding="utf-8")
                ctx_here = context_of(REPO, None, None, {}, pin, None)
                ctx_here.update(home=str(fixture_home), commit="fixture")
                out_here = scratch / "p24b" / f"out-{name}"
                try:
                    freeze_inputs(scratch / "p24b" / f"frozen-{name}", REPO, state_here, None, pin, ctx_here,
                                  census_entries(run_at))
                    bind_transcripts(ctx_here, run_at)
                    sessions_here = sessions_document(ctx_here)
                    shared_here = shared_inventories(ctx_here)
                    store_here = store_document(ctx_here)
                    crossed_here = shared_cross_problems(shared_here, store_here, sessions_here) \
                        + occurrence_cross_problems(sessions_here, store_here)
                    if crossed_here:
                        return {"refused": "crossed", "message": "; ".join(crossed_here)}
                    for relative, document_here in shared_here:
                        write_document(out_here, out_here / "inventory" / relative, document_here, str(fixture_home))
                    write_document(out_here, out_here / "inventory" / f"{SESSIONS}.json", sessions_here, str(fixture_home))
                    write_document(out_here, out_here / "inventory" / STORE_REL, store_here, str(fixture_home))
                except Exception as exc:  # the control names what refused, never the suite
                    return {"refused": type(exc).__name__, "message": str(exc)}
                return {"shared": {path.stem: json.loads(path.read_text(encoding="utf-8"))
                                   for path in sorted((out_here / "inventory" / "shared").glob("*-i-*.json"))},
                        "sessions": json.loads((out_here / "inventory" / f"{SESSIONS}.json").read_text(encoding="utf-8")),
                        "out": out_here, "omissions": list(ctx_here.get("omissions") or [])}

            def plant_baseline(state_dir, ref, items):
                base_dir = state_dir / "runtime" / "baselines" / ref
                base_dir.mkdir(parents=True, exist_ok=True)
                (base_dir / "inventory.json").write_text(json.dumps({"items": items}), encoding="utf-8")


            shared_state = scratch / "p24b" / "shared-state"
            secret_u = "sk-ant-api03-" + "Un4" * 14
            home_u = f"{fixture_home}/Documents/an-unavailable-reason-s-own"
            unavailable_in = [{"ref": "@fixture/core:hook-1", "surface": "event",
                               "reason": f"native event consumption is disabled under {home_u}, key {secret_u}"}]
            a_items = [catalog_item("rule-a", "rule", "- rule a"), catalog_item("hook-1", "hook", "print('a hook')\n")]
            a_ref = plant_snapshot(shared_state, "# Session\n\n- a\n", baseline_ref="ref-a", items=a_items,
                                   unavailable=unavailable_in)
            b_ref = plant_snapshot(shared_state, "# Session\n\n- b\n", baseline_ref="ref-b",
                                   items=[catalog_item("rule-b", "rule", "- rule b")])
            plant_baseline(shared_state, "ref-a", [catalog_item("rule-a", "rule", "- rule a")])
            plant_baseline(shared_state, "ref-b", [catalog_item("rule-b", "rule", "- rule b")])
            plant_pin(shared_state, "s-a", a_ref)
            plant_pin(shared_state, "s-b", b_ref)
            plant_pin(shared_state, "s-a2", a_ref)
            s_at = "2026-10-22T09:00:00+00:00"
            shared_rows = [pinned_row("s-a", [inj(s_at, [member("User", "/w/g.md", "- g a\n")], cwd=p1)], a_ref),
                           pinned_row("s-a2", [inj(s_at, [member("Project", f"{p2}/CLAUDE.md", "- a2\n")], cwd=p2)], a_ref),
                           pinned_row("s-b", [inj(s_at, [member("Project", f"{p3}/CLAUDE.md", "- b\n")], cwd=p3)], b_ref),
                           ("claude", "s-free", [inj(s_at, [], cwd=p1)], {})]
            shared_clean = published_shared("clean", shared_rows, shared_state)
            check("the shared inventories were published and crossed clean", "refused" not in shared_clean,
                  f"{shared_clean.get('refused')} {str(shared_clean.get('message'))[:200]}")
            shared_docs = shared_clean.get("shared") or {}
            a_selection = shared_docs.get(f"selection-{inventory_id('selection', a_ref)}") or {}
            b_selection = shared_docs.get(f"selection-{inventory_id('selection', b_ref)}") or {}
            a_release = shared_docs.get(f"release-{inventory_id('release', 'ref-a')}") or {}
            b_release = shared_docs.get(f"release-{inventory_id('release', 'ref-b')}") or {}
            clean("and every one of them validates against its own root",
                  [problem for document_here in shared_docs.values() for problem in document_contract_problems(document_here)]
                  or ([] if len(shared_docs) == 4 else [f"documents={sorted(shared_docs)}"]))
            check("one selection inventory per distinct snapshot a session's own pin names, and one release inventory per "
                  "baseline those snapshots name, each under the id its kind and ref derive",
                  sorted(shared_docs) == sorted([f"selection-{inventory_id('selection', a_ref)}",
                                                 f"selection-{inventory_id('selection', b_ref)}",
                                                 f"release-{inventory_id('release', 'ref-a')}",
                                                 f"release-{inventory_id('release', 'ref-b')}"])
                  and a_selection.get("inventory_id") == canonical("i", "inventory", "selection", a_ref)
                  and a_release.get("ref") == "ref-a" and a_release.get("kind") == "release",
                  f"{sorted(shared_docs)}")
            shared_records = {row["transcript"]["id"]: row for row in (shared_clean.get("sessions") or {}).get("sessions") or []}
            check("a session's selection names the shared inventory its own snapshot is, two sessions of one snapshot "
                  "naming one, and an unpinned session none",
                  (shared_records.get("s-a") or {}).get("selection") == {
                      "status": "read", "reason": None, "inventory_ref": inventory_id("selection", a_ref)}
                  and (shared_records.get("s-a2") or {}).get("selection") == (shared_records.get("s-a") or {}).get("selection")
                  and (shared_records.get("s-free") or {}).get("selection") == {
                      "status": "unpinned", "reason": "unpinned", "inventory_ref": None},
                  f"{(shared_records.get('s-a') or {}).get('selection')} {(shared_records.get('s-free') or {}).get('selection')}")
            a_rows = {row["layer"]: row for row in a_selection.get("layers") or []}
            check("a selection inventory's layers are the selection's: catalog and session injection from its snapshot, "
                  "every native layer unknown per_event, the ledgers by their own reason",
                  (a_rows.get("catalog") or {}).get("status") == "complete"
                  and (a_rows.get("session_injection") or {}).get("status") == "complete"
                  and all((a_rows.get(layer) or {}).get("reasons") == [f"{layer}: {UNKNOWN_REASONS['per_event']}"]
                          for layer in TRANSCRIPT_LAYERS + ("native_undivided",))
                  and (a_rows.get("ledger_keep") or {}).get("reasons") == [f"ledger_keep: {UNKNOWN_REASONS['ledger_history']}"]
                  and bool(a_selection.get("unit_refs")) and bool(a_selection.get("carriers")),
                  f"{[(layer, row['status']) for layer, row in a_rows.items()]}")
            check("a release inventory answers its catalog and adopted packages only, maps every baseline item, and names "
                  "its carrier versions and units by reference",
                  [row["layer"] for row in a_release.get("layers") or []] == list(SHARED_RELEASE_LAYERS)
                  and a_release.get("baseline_unmapped") == [] and a_release.get("baseline_items_expected") == 1
                  and a_release.get("complete") is True and bool(a_release.get("unit_refs")),
                  f"{[(row['layer'], row['status']) for row in a_release.get('layers') or []]} "
                  f"{a_release.get('baseline_unmapped')}")
            check("ruling 7: a selection inventory carries its snapshot's unavailable list, its ref among the snapshot's "
                  "own items and its surface among the catalog's",
                  [(row["ref"], row["surface"]) for row in a_selection.get("unavailable") or []]
                  == [("@fixture/core:hook-1", "event")] and b_selection.get("unavailable") == [],
                  f"{a_selection.get('unavailable')}")
            shared_written = "".join(path.read_text(encoding="utf-8")
                                     for path in sorted((pathlib.Path(shared_clean.get("out") or scratch) / "inventory").rglob("*.json")))
            check("an unavailable reason holding a credential and a home path reaches the written shared inventory masked",
                  bool(shared_written) and secret_u not in shared_written and home_u not in shared_written
                  and any("<REDACTED>" in row["reason"] or "<HOME>" in row["reason"] for row in a_selection.get("unavailable") or []),
                  f"written={bool(shared_written)} rows={len(a_selection.get('unavailable') or [])}")
            foreign_state = scratch / "p24b" / "foreign-state"
            foreign_ref = plant_snapshot(foreign_state, "# Session\n\n- foreign\n", baseline_ref="ref-a", items=a_items[:1],
                                         unavailable=[{"ref": "@elsewhere:not-an-item", "surface": "event", "reason": "x"}])
            plant_baseline(foreign_state, "ref-a", [catalog_item("rule-a", "rule", "- rule a")])
            plant_pin(foreign_state, "s-f", foreign_ref)
            foreign = published_shared("foreign", [pinned_row("s-f", [inj(s_at, [], cwd=p1)], foreign_ref)], foreign_state)
            control("ruling 7: an unavailable ref that is not among the snapshot's own items is refused by name",
                    [f"{foreign.get('refused')}: {foreign.get('message')}"], "EMISSION_NOT_DECLARED_VALUE", ".unavailable[0].ref")

            # S-25 `baseline@<ref>`, two sessions: a missing baseline reaches the release inventory of THAT baseline,
            # by `baseline_absent`, and leaves the other inventory and every session record as they were
            absent_state = scratch / "p24b" / "absent-state"
            shutil.copytree(shared_state, absent_state)
            shutil.rmtree(absent_state / "runtime" / "baselines" / "ref-a")
            shared_absent = published_shared("absent", shared_rows, absent_state)
            absent_docs = shared_absent.get("shared") or {}
            absent_a = absent_docs.get(f"release-{inventory_id('release', 'ref-a')}") or {}
            absent_records = {row["transcript"]["id"]: row for row in (shared_absent.get("sessions") or {}).get("sessions") or []}
            check("S-25: a missing baseline@R makes R's release inventory unknown by baseline_absent, and leaves the other "
                  "release inventory, every selection inventory and every session record as they were",
                  "refused" not in shared_absent and bool(absent_a.get("layers"))
                  and all(row["status"] == "unknown" and row["reasons"]
                          == [f"{row['layer']}: {UNKNOWN_REASONS['baseline_absent']} (release_baseline)"]
                          for row in absent_a.get("layers") or [])
                  and absent_docs.get(f"release-{inventory_id('release', 'ref-b')}") == b_release
                  and {key: value for key, value in absent_docs.items() if key.startswith("selection-")}
                  == {key: value for key, value in shared_docs.items() if key.startswith("selection-")}
                  and absent_records == shared_records,
                  f"{shared_absent.get('refused')} {[(row['layer'], row['status'], row['reasons']) for row in absent_a.get('layers') or []]}")

            # S-25 runtime state, two sessions: absent (the clean fixture holds none), present, or failed (a link), it
            # reaches no shared inventory and no session record: those are a pinned session's, and runtime state is
            # the installed-now inventory's input only (the matrix judges current.json for it)
            runtime_cases = {}
            for label, plant in (("present", lambda path: path.write_text(json.dumps(
                    {"schema_version": 1, "selected_baseline_ref": "ref-b"}), encoding="utf-8")),
                                 ("failed", lambda path: path.symlink_to(path.parent / "elsewhere.json"))):
                runtime_state_here = scratch / "p24b" / f"runtime-{label}-state"
                shutil.copytree(shared_state, runtime_state_here)
                (runtime_state_here / "runtime").mkdir(parents=True, exist_ok=True)
                plant(runtime_state_here / "runtime" / "state.json")
                runtime_cases[label] = published_shared(f"runtime-{label}", shared_rows, runtime_state_here)
            def selection_catalogs(case):
                """The catalog row of every shared selection inventory one arm wrote: the subject the
                comparison is about, so an arm that writes none cannot pass it."""
                return [row for key, document_here in (case.get("shared") or {}).items() if key.startswith("selection-")
                        for row in document_here.get("layers") or [] if row["layer"] == "catalog"]

            check("S-25: every arm of the runtime-state control writes shared selection inventories whose catalog is complete",
                  all(len(selection_catalogs(case)) == 2 and all(row["status"] == "complete" for row in selection_catalogs(case))
                      for case in (shared_clean, *runtime_cases.values())),
                  f"{[(label, [(row['status'], row['reasons']) for row in selection_catalogs(case)]) for label, case in (('absent', shared_clean), *runtime_cases.items())]}")
            # The rule itself (lead, after pretrial-p24b-2): under a planted UNKEYED omission (the runtime state a
            # link, so failed; and no user root), every row of the WRITTEN selection.json equals the same row of its
            # own shared selection inventory, status and reasons — one producer, and one context but for the rows
            # keyed to another pin, snapshot or baseline. Two arms, a --pin of s-a and of s-b, over one census of s-a,
            # s-a2 and s-b; each a full run, wrapped.
            equal_run = scratch / "p24b" / "run-equal"
            equal_run.mkdir(parents=True, exist_ok=True)
            equal_census = []
            for host_e, ident_e, records_e, fields_e in shared_rows:
                if ident_e in ("s-a", "s-a2", "s-b"):
                    path_e = raw_lines(scratch / "p24b" / "equal" / f"{ident_e}.jsonl", records_e)
                    equal_census.append({**census_row(host_e, ident_e, path_e), **fields_e})
            (equal_run / CENSUS).write_text(json.dumps({"transcripts": equal_census}), encoding="utf-8")
            equal_arms = {}
            for ident_e, ref_e in (("s-a", a_ref), ("s-b", b_ref)):
                equal_out = scratch / "p24b" / f"out-equal-{ident_e}"
                raised_e = _raised(lambda: run(REPO, scratch / "p24b" / "runtime-failed-state", None, equal_out,
                                               pin=f"claude:{ident_e}", run_dir=equal_run, commit="fixture",
                                               home=fixture_home, native_roots={"projects": {"project": scratch / "project"}}))
                files_e = {key: json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
                           for key, path in (("selection", equal_out / "inventory" / "selection.json"),
                                             ("shared", equal_out / "inventory" / "shared"
                                              / f"selection-{inventory_id('selection', ref_e)}.json"))}
                equal_arms[ident_e] = (raised_e, files_e)

            def arm_rows(document_here):
                return [(row["layer"], row["status"], row["reasons"]) for row in document_here.get("layers") or []]

            def arm_missing(files_e):
                return ((files_e["selection"].get("produced_by") or {}).get("notes") or {}).get("frozen_missing") or []

            check("under an unkeyed omission, every row of the written selection.json equals the same row of its own "
                  "shared selection inventory, status and reasons",
                  len(equal_arms) == 2 and all(
                      raised_e is None and bool(arm_rows(files_e["selection"]))
                      and arm_rows(files_e["selection"]) == arm_rows(files_e["shared"])
                      and any(row.get("input") == "runtime_state" and row.get("outcome") == "failed"
                              for row in arm_missing(files_e))
                      for raised_e, files_e in equal_arms.values()),
                  f"{[(ident_e, type(raised_e).__name__ if raised_e else None, str(raised_e or '')[:200], [pair for pair in zip(arm_rows(files_e['selection']), arm_rows(files_e['shared'])) if pair[0] != pair[1]][:2], [(row.get('input'), row.get('outcome')) for row in arm_missing(files_e)]) for ident_e, (raised_e, files_e) in equal_arms.items()]}")
            # One home for emission and judgement (lead, P2.4b): run(home=X) whose published leaf holds a path under X
            # writes it as `<HOME>` and is not refused — s-a's unavailable reason names this suite's fixture home
            a_raised, a_files = equal_arms.get("s-a", (None, {"shared": {}}))
            a_reasons = [row.get("reason") or "" for row in a_files["shared"].get("unavailable") or []]
            check("run(home=X): a published leaf holding a path under X is written as <HOME>, and the run is not refused",
                  a_raised is None and len(a_reasons) == 1 and "<HOME>" in a_reasons[0]
                  and str(fixture_home) not in a_reasons[0] and secret_u not in a_reasons[0],
                  f"raised={type(a_raised).__name__ if a_raised else None}: {str(a_raised or '')[:200]} reasons={a_reasons}")
            # ...and an omission KEYED to the --pin is that pin's alone: a --pin whose pin does not read reaches no
            # session's shared inventory (KEYED_INPUTS)
            pin_failed_case = published_shared("pin-failed", shared_rows, shared_state, pin="claude:s-missing")
            check("S-25: a --pin whose pin does not read reaches no shared inventory and no session record, its "
                  "omission being keyed to it",
                  "refused" not in pin_failed_case and pin_failed_case.get("shared") == shared_docs and bool(shared_docs)
                  and {row["transcript"]["id"]: row for row in pin_failed_case["sessions"]["sessions"]} == shared_records
                  and any(row["input"] == "pin" and row["ref"] == "claude:s-missing"
                          for row in pin_failed_case.get("omissions") or []),
                  f"{pin_failed_case.get('refused')} {[(row['input'], row['ref'], row['outcome']) for row in pin_failed_case.get('omissions') or []]}")
            check("S-25: runtime state absent, present or failed changes no shared inventory and no session record",
                  all("refused" not in case and case.get("shared") == shared_docs
                      and {row["transcript"]["id"]: row for row in case["sessions"]["sessions"]} == shared_records
                      for case in runtime_cases.values()) and bool(shared_docs),
                  f"{[(label, case.get('refused'), sorted(case.get('shared') or {}) == sorted(shared_docs)) for label, case in runtime_cases.items()]}")
            # each of the shared cross checks refuses by name, over rows built here
            crossed_store = {"versions": {}, "units": {}}
            crossed_doc = {"inventory_id": inventory_id("selection", "other-ref"), "kind": "selection", "ref": "a-ref",
                           "carriers": [{"carrier_id": "c-" + "0" * 24, "version_sha256": "0" * 64}],
                           "unit_refs": ["r-" + "0" * 24]}
            crossed_sessions = {"sessions": [{"selection": {"inventory_ref": inventory_id("selection", "unpublished")}}]}
            control("ruling 5: a shared inventory listed under another id than its path names, and a single document "
                    "listed with an id, each refused by name",
                    artifact_problems([{"path": f"inventory/shared/selection-{inventory_id('selection', 'a')}.json",
                                        "document": SHARED, "id": inventory_id("selection", "b")},
                                       {"path": "inventory/current.json", "document": "current",
                                        "id": inventory_id("selection", "a")}]),
                    "ARTIFACT_ID_MISMATCH inventory/shared/selection-", "ARTIFACT_ID_UNEXPECTED inventory/current.json")
            control("a shared inventory's id that its kind and ref do not derive, a carrier version and a unit outside the "
                    "store, and a session naming no published selection inventory, each refused by name",
                    shared_cross_problems([("x", crossed_doc)], crossed_store, crossed_sessions),
                    "SHARED_ID_MISMATCH", "SHARED_VERSION_UNRESOLVED", "SHARED_UNIT_UNRESOLVED", "SHARED_SELECTION_UNRESOLVED")

            # The selection rows a malformed snapshot item reaches are a declared reason, never an exception's name
            # (found by the lead after a36c728): the default fixture item names only its ref.
            declared_texts = tuple(UNKNOWN_REASONS.values()) + ("MALFORMED_ITEM:", PRODUCER_FAILED)

            def undeclared_rows(rows):
                """The layer rows that are neither evidence (`complete`) nor unknown or incomplete by reasons
                this module declares, as `layer=status: reasons`; `[]` when every row is one or the other."""
                return [f"{row['layer']}={row['status']}: {row['reasons']}" for row in rows
                        if not (row["status"] == "complete" and not row["reasons"])
                        and not (row["status"] in ("unknown", "incomplete") and row["reasons"] and all(
                            text.split(": ", 1)[-1].startswith(declared_texts) for text in row["reasons"]))]

            malformed_state = scratch / "p24b" / "malformed-state"
            # the ONE fixture whose item names only its ref: built for MALFORMED_ITEM, and no other is
            malformed_ref = plant_snapshot(malformed_state, "# Session\n\n- m\n", baseline_ref="ref-a",
                                           items=[{"ref": "@fixture/core:item-1"}])
            plant_baseline(malformed_state, "ref-a", [catalog_item("rule-a", "rule", "- rule a")])
            plant_pin(malformed_state, "s-m", malformed_ref)
            malformed = published_shared("malformed", [pinned_row("s-m", [inj(s_at, [], cwd=p1)], malformed_ref)], malformed_state)
            malformed_doc = (malformed.get("shared") or {}).get(f"selection-{inventory_id('selection', malformed_ref)}") or {}
            check("every row of a selection is the pin's evidence or carries a declared reason: a snapshot item naming no "
                  "kind is MALFORMED_ITEM, never an exception's name",
                  bool(malformed_doc.get("layers")) and not undeclared_rows(malformed_doc["layers"])
                  and (({row["layer"]: row for row in malformed_doc.get("layers") or []}.get("catalog") or {}).get("reasons")
                       == ["catalog: MALFORMED_ITEM: a catalog item that names no kind or no ref"]),
                  f"{[(row['layer'], row['status'], row['reasons']) for row in malformed_doc.get('layers') or []]}")
            def raising_producer(_ctx):
                raise KeyError("kind")

            kept_layers_here = globals()["LAYERS"]
            try:
                globals()["LAYERS"] = (("catalog", {"current": ("a fixture producer that raises", raising_producer, ())}),)
                raised_rows = layer_rows("current", {"notes": {}, "omissions": []})
            finally:
                globals()["LAYERS"] = kept_layers_here
            # a missing row is a failed condition below, never an IndexError that ends the suite
            raised_first = raised_rows[0] if raised_rows else {"layer": "catalog", "producer": None, "status": "unknown",
                                                               "reasons": ["layer_rows returned no row"]}
            raised_row = emit_row("layer_row", LAYER_ROW_TABLE,
                                  {**{key: raised_first[key] for key in ("layer", "producer", "status", "reasons")},
                                   "units": 0, "empty": False},
                                  {"home": str(fixture_home), "decisions": {}})
            check("a producer that raises an undeclared exception leaves the declared reason with its fixed category, "
                  "never the exception's type or text",
                  raised_row["status"] == "incomplete"
                  and raised_row["reasons"] == [f"catalog: {PRODUCER_FAILED} (not_admitted)"]
                  and not exception_named_problems(raised_row)[0],
                  f"{raised_row['reasons']}")
            # W4: a transcript the reader cannot read (no permission) is `unreadable` by category
            locked_path = raw_lines(scratch / "p24b" / "locked" / "s-locked.jsonl", [inj(s_at, [], cwd=p1)])
            locked_entry = census_row("claude", "s-locked", locked_path)
            locked_path.chmod(0)
            try:
                locked = _raised(lambda: transcript_records(locked_entry))
            finally:
                locked_path.chmod(0o600)
            check("an unreadable transcript's reason is its fixed category, never the reader's exception type or its path",
                  isinstance(locked, Unacquired) and str(locked) == f"{UNKNOWN_REASONS['unreadable']} (unreadable)"
                  and not exception_named_problems({"reason": str(locked)})[0],
                  f"{type(locked).__name__}: {locked}")
            # W5: a file the tree hash cannot read is omitted with its fixed category
            locked_tree = scratch / "p24b" / "locked-tree"
            locked_tree.mkdir(parents=True)
            (locked_tree / "readable.txt").write_text("x\n", encoding="utf-8")
            (locked_tree / "locked.txt").write_text("y\n", encoding="utf-8")
            (locked_tree / "locked.txt").chmod(0)
            try:
                locked_digests, locked_omissions = hash_tree(locked_tree)
            finally:
                (locked_tree / "locked.txt").chmod(0o600)
            check("a path the tree hash cannot read is omitted by its fixed category, never the exception's type",
                  locked_omissions == [{"path": "locked.txt", "reason": "unreadable: unreadable"}]
                  and "readable.txt" in locked_digests and not exception_named_problems({"omissions": locked_omissions})[0],
                  f"{locked_omissions}")
            # ruling 4: the names are derived, not listed: a class defined after the fact is among them
            globals()["PlantedProbeFailure"] = type("PlantedProbeFailure", (Exception,), {})
            try:
                derived_names = exception_names()
            finally:
                del globals()["PlantedProbeFailure"]
            check("the exception names are derived: builtins, this module's own and its modules' (a class planted in this "
                  "module after import is among them)",
                  {"KeyError", "SyntaxError", "JSONDecodeError", "Refused", "Malformed", "Unacquired", "Unreadable",
                   "PlantedProbeFailure"} <= derived_names and "PlantedProbeFailure" not in exception_names(),
                  f"{sorted(name for name in ('KeyError', 'JSONDecodeError', 'Refused', 'Unreadable', 'PlantedProbeFailure') if name not in derived_names)}")
            named_here, judged_here = exception_named_problems({"layers": [{"reasons": ["catalog: KeyError: 'kind'"]}]})
            control("a reason naming a Python exception type is found by name, where it is",
                    named_here + [f"judged={judged_here}"], "REASON_NAMES_EXCEPTION $.layers[0].reasons[0]", "judged=1")

        with section('M5 (recording): an undecodable line is kept at its position, before and after an event'):
            # ---- M5 (recording): an undecodable line is kept at its position, before and after an event
            for label, rows_for, expected_line, event_line in (
                    ("malformed before a valid injection", [b"{\"type\": \"attachment\", \"attachm", dated("2026-10-09T09:00:00+00:00")], 1, 2),
                    ("malformed after a valid injection", [dated("2026-10-09T09:00:00+00:00"), b"{\"type\": \"attachment\", \"attachm"], 2, 1)):
                m5_path = raw_lines(scratch / "p1" / f"m5-{expected_line}.jsonl", rows_for)
                m5_run = scratch / "p1" / f"run-m5-{expected_line}"
                m5_run.mkdir(parents=True)
                (m5_run / CENSUS).write_text(json.dumps({"transcripts": [census_row("claude", "s-m5", m5_path)]}),
                                             encoding="utf-8")
                m5_events, _m5_unknown, m5_findings = transcript_events(m5_run)
                check(f"a decoding failure is kept at its raw line: {label}",
                      m5_findings["undecodable"] == [{"session": "claude:s-m5", "line": expected_line, "category": "not_json"}]
                      and [event["n"] for event in m5_events] == [event_line],
                      f"{m5_findings['undecodable']} {[event['n'] for event in m5_events]}")
                m5_ctx = {"notes": {}}
                bind_transcripts(m5_ctx, m5_run)
                check(f"and the run's notes carry it: {label}",
                      m5_ctx["notes"]["transcripts"].get("undecodable") == m5_findings["undecodable"],
                      "the decoding failure did not reach the notes")

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

        with section("GA#9: a keep record stands only while the entry's lifecycle says it does"):
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
                globals()["LAYERS"] = tuple((name, {"current": (f"{name} producer", call, ())}) for name, call in planted.items())
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

        with section('#16: an omission is applied through the inputs a producer declares, so one that declares'):
            # ---- #16: an omission is applied through the inputs a producer declares, so one that declares
            # nothing has nothing to be applied through, and is refused rather than run
            saved_undeclared = globals()["LAYERS"]
            try:
                globals()["LAYERS"] = (("catalog", {"current": ("a producer that says nothing of its inputs",
                                                                planted["complete"])}),)
                undeclared = str(_raised(lambda: layer_rows("current", context_of(REPO, None, None, {}, None, None))))
                globals()["LAYERS"] = (("catalog", {"current": ("a producer naming an input kind nobody has",
                                                                planted["complete"], ("a_kind_nobody_declared",))}),)
                unknown_kind = str(_raised(lambda: layer_rows("current", context_of(REPO, None, None, {}, None, None))))
            finally:
                globals()["LAYERS"] = saved_undeclared
            control("a producer that declares no inputs is refused by name", [undeclared], "PRODUCER_UNDECLARED catalog")
            control("and one that declares an input kind outside the classes", [unknown_kind], "PRODUCER_UNDECLARED catalog")

        with section('GA#11: one cause at a time, so ignoring any single one of them cannot survive'):
            # ---- GA#11: one cause at a time, so ignoring any single one of them cannot survive
            causes = {"unsupported": planted["unsupported"], "unknown": planted["unknown"],
                      "malformed": planted["malformed"],
                      "no-units": planted["no-units"], "raising": planted["raising"]}
            for cause, producer in causes.items():
                saved_one = globals()["LAYERS"]
                try:
                    globals()["LAYERS"] = (("catalog", {"current": ("the complete layer", planted["complete"], ())}),
                                           ("overlays", {"current": (f"the {cause} layer", producer, ())}))
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
                        "run_dir": run_fixture, "home": fixture_home, **extra}

            def judged_run(name, *args, **kwargs):
                """A full `run` judged where it is called: a refusal is a failure by name, and what the run would
                have returned reads as `Absent`, so the controls after it fail by name too."""
                returned = []
                raised = _raised(lambda: returned.append(run(*args, **kwargs)))
                check(f"{name} run completes", raised is None,
                      f"{type(raised).__name__}: {str(raised)[:300]}" if raised else "")
                return returned[0] if returned else Absent()

            def written_json(path):
                """A document a run wrote, or `Absent` when that run wrote none."""
                path = pathlib.Path(path)
                return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else Absent()

        with section("done-when 5: the owner's state is read through frozen copies"):
            # ---- done-when 5: the owner's state is read through frozen copies
            pending = state / "runtime" / "transactions" / "tx-1"
            pending.mkdir(parents=True)
            (pending / "transaction.json").write_text(json.dumps({"state": "NEEDS_RECOVERY", "owner": "installer"}), encoding="utf-8")
            user = fixture_home / "user"
            user.mkdir()
            (user / "state.json").write_text(json.dumps({"schema_version": 1, "items": {}, "overrides": {}, "tombstones": {},
                                                         "selection": None,
                                                         "learning_suppressions": {"claude": [], "codex": []}}), encoding="utf-8")
            before, _ = hash_tree(state)
            manifest = judged_run("the unpinned", REPO, state, user, scratch / "out", ledger=ledger, commit="fixture",
                                  **captured())
            check("the frozen route left the owner's state untouched", manifest["state_root_unchanged"] and hash_tree(state)[0] == before,
                  "the state root changed while the inventory read it")
        with section('GA#11: the records as the artifact serializes them, not the field tuple in this module'):
            # ---- GA#11: the records as the artifact serializes them, not the field tuple in this module
            serialized = written_json(scratch / "out" / "inventory" / "current.json")["units"]
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
            # S-24 option 1: with no pin, release.json names no baseline and its catalog and adopted packages are
            # `release_history_deferred`; the installed baseline (ref1 here) is never taken for it. Done-when 1's
            # mapping is judged per shared release inventory, on the planted run below, whose session is pinned.
            deferred_doc = written_json(scratch / "out" / "inventory" / "release.json")
            # a layer missing from the document reads as no status, so the check fails by name rather than raising
            deferred_rows = collections.defaultdict(lambda: {"status": None, "reasons": None},
                                                    {row["layer"]: row for row in deferred_doc.get("layers") or []})
            check("an unpinned release names no baseline: its catalog and adopted packages are release_history_deferred, "
                  "and the installed baseline is not taken for it",
                  all(deferred_rows[layer]["status"] == "unknown"
                      and deferred_rows[layer]["reasons"] == [f"{layer}: {UNKNOWN_REASONS['release_history_deferred']}"]
                      for layer in SHARED_RELEASE_LAYERS)
                  and deferred_doc["reference"].get("ref") is None and "baseline_unmapped" not in manifest
                  and not any(unit["layer"] in SHARED_RELEASE_LAYERS for unit in deferred_doc["units"]),
                  f"{[(layer, deferred_rows[layer]['status'], deferred_rows[layer]['reasons']) for layer in SHARED_RELEASE_LAYERS]}")
            # M4 (S-24 option 1, S-16) through a recording seam over `freeze`, the one route by which this module
            # reads the owner's state (done-when 5): an unpinned run, a Codex --pin run and an unpinned run whose
            # runtime state is absent read no transaction or installer journal, and their release rows are
            # deferred, never the installed baseline and never a runtime-state reason. The fixture holds a
            # transaction (tx-1), so the absence is about a path that is there.
            kept_freeze, frozen_sources, seam_runs = globals()["freeze"], [], {}

            def recording_freeze(sources, *args, **kwargs):
                sources = list(sources)
                frozen_sources.extend(str(source) for source, _relative in sources)
                return kept_freeze(sources, *args, **kwargs)

            stateless = scratch / "m4-stateless-state"
            shutil.copytree(state, stateless, symlinks=True)
            (stateless / "runtime" / "state.json").unlink()
            globals()["freeze"] = recording_freeze
            try:
                for label, state_here, pin_here in (("unpinned", state, None), ("codex", state, "codex:c-seam"),
                                                    ("no-runtime-state", stateless, None)):
                    seam_out = scratch / f"m4-{label}"
                    raised_here = _raised(lambda: run(REPO, state_here, user, seam_out, pin=pin_here, ledger=ledger,
                                                      commit="fixture", **captured()))
                    release_here = seam_out / "inventory" / "release.json"
                    seam_runs[label] = (raised_here, json.loads(release_here.read_text(encoding="utf-8"))
                                        if release_here.is_file() else {})
            finally:
                globals()["freeze"] = kept_freeze
            journal_reads = [source for source in frozen_sources if "transactions" in source or "journal" in source.lower()]
            check("M4: an unpinned run, a Codex --pin run and an unpinned run with no runtime state read no transaction "
                  "or installer journal",
                  not journal_reads and any(source.endswith("runtime/state.json") for source in frozen_sources)
                  and (state / "runtime" / "transactions" / "tx-1" / "transaction.json").is_file(),
                  f"journal_reads={journal_reads} sources={len(frozen_sources)}")
            check("and each one's release catalog and adopted packages are release_history_deferred, the Codex --pin's "
                  "included and the absent runtime state's reason nowhere among them",
                  len(seam_runs) == 3 and all(
                      raised is None and [(row["layer"], row["status"], row["reasons"]) for row in doc.get("layers") or []
                                          if row["layer"] in SHARED_RELEASE_LAYERS]
                      == [(layer, "unknown", [f"{layer}: {UNKNOWN_REASONS['release_history_deferred']}"])
                          for layer in SHARED_RELEASE_LAYERS]
                      for raised, doc in seam_runs.values()),
                  f"{[(label, type(raised).__name__ if raised else None, [(row['layer'], row['reasons']) for row in doc.get('layers') or [] if row['layer'] in SHARED_RELEASE_LAYERS]) for label, (raised, doc) in seam_runs.items()]}")
            planted_write = state / "runtime" / "planted-by-a-producer.json"
            saved = globals()["LAYERS"]

            def writing_producer(ctx):
                planted_write.write_text("{}", encoding="utf-8")
                return [guide("first.md", first)]

            try:
                globals()["LAYERS"] = (("catalog", {"current": ("a producer that writes", writing_producer, ())}),)
                control("a producer that writes into the owner's state", [str(_raised(
                    lambda: run(REPO, state, user, scratch / "written", ledger=ledger,
                                       home=fixture_home)))], "STATE_WRITTEN")
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
                  bool(sorted(set(after) - set(before))
                       or [name for name in after if after[name] != before.get(name)]),
                  "the recovering entry point changed nothing, so the control shows nothing")

        with section('GA#3: no write can reach a protected root, and the guarantee is checked on error paths'):
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

        with section('R1#1: protection does not depend on READING. This is the shape `--no-state` produces'):
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

        with section('R2#1: a host home is where its variable says, not where the default says. The'):
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

        with section('R1#6: one admission point, and denying it stops every category of state-byte read'):
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
                denied_missing = omission_lines(freeze([(admit_root / "runtime", "runtime"),
                                                        (admit_root / "runtime" / "state.json", "one.json")],
                                                       denied_copy))
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
            check("the command itself has bytecode writing off by the time its graph is imported",
                  was is True, "the entry point did not set dont_write_bytecode before importing its graph")
            # And the ORDER, which the runtime reading above cannot see: by the time anything can read
            # that flag, every import has already happened. The order is a fact about the entry files'
            # own source, so it is judged there, over the real files and not a double.
            clean("both entry files turn bytecode writing off before any import of their own",
                  guard_problems())
            control("no entry file to judge at all", guard_problems(entries=()),
                    "BYTECODE_GUARD_ABSENT", "says nothing")
            control("an entry file that names a file that is not there",
                    guard_problems(entries=("session-distill/not-an-entry.py",)),
                    "BYTECODE_GUARD_ABSENT", "no such file")
            # Four source-only plants, each built from the REAL entry file's text so the subject is the
            # file that ships. The repo import the first two move the guard behind is the bootstrap's
            # own `from runlib import entry`, which is the earliest one either file has.
            for name, relative, mutate, needle in (
                    ("the guard taken out",
                     "session-distill/runlib/inventory.py",
                     lambda text: text.replace("sys.dont_write_bytecode = True\n", "", 1),
                     "BYTECODE_GUARD_ABSENT"),
                    ("the guard moved below the first repository import",
                     "session-distill/runlib/inventory.py",
                     lambda text: text.replace("sys.dont_write_bytecode = True\n", "", 1).replace(
                         "try:\n    from runlib import entry\n",
                         "try:\n    from runlib import entry\n    sys.dont_write_bytecode = True\n", 1),
                     "BYTECODE_GUARD_ABSENT"),
                    ("a dynamic import before the guard",
                     "session-distill/distill.py",
                     lambda text: text.replace(
                         "sys.dont_write_bytecode = True\n",
                         "import importlib\nimportlib.import_module('runlib.entry')\n"
                         "sys.dont_write_bytecode = True\n", 1),
                     "BYTECODE_GUARD_LATE"),
                    ("the guard nested under a condition",
                     "session-distill/distill.py",
                     lambda text: text.replace("sys.dont_write_bytecode = True\n",
                                               "if True:\n    sys.dont_write_bytecode = True\n", 1),
                     "BYTECODE_GUARD_ABSENT"),
                    # r7 G1: `_stdlib_only` is what separates an admitted import from a refused one, and
                    # none of the plants above reach it — the two GUARD_ABSENT ones take the guard away
                    # and the dynamic one is a call, refused whatever that helper answers. A plain
                    # repository import before the guard is the one shape only this helper decides.
                    ("a repository import before the guard",
                     "session-distill/distill.py",
                     lambda text: text.replace("sys.dont_write_bytecode = True\n",
                                               "from runlib import entry\n"
                                               "sys.dont_write_bytecode = True\n", 1),
                     "BYTECODE_GUARD_LATE"),
            ):
                live = (REPO / relative).read_text(encoding="utf-8")
                planted_text = mutate(live)
                check(f"the plant for {name} really changed the source", planted_text != live,
                      "the mutation did not apply, so the control below judges the real file")
                control(f"an entry file with {name}", guard_before_imports(planted_text), needle)
            check("a standard-library import before the guard is admitted, so the rule is not 'no imports'",
                  not guard_before_imports("import os\nimport sys\nsys.dont_write_bytecode = True\n"),
                  "a stdlib import before the guard was refused")
            check("and the admission comes from the interpreter's own list, not from a prefix of ours",
                  "os" in sys.stdlib_module_names and "runlib" not in sys.stdlib_module_names,
                  "sys.stdlib_module_names does not answer this question here")

        with section('audit 1109: the refusal behind the host homes. `install_module` loads the SHIPPED'):
            # ---- audit 1109: the refusal behind the host homes. `install_module` loads the SHIPPED
            # installer by path, because the rule for where each host's home is belongs to it and is not
            # restated here. A checkout without that file must refuse BY NAME: removing the refusal
            # leaves the load failing anyway, through the outer boundary as an ordinary file error, so
            # every suite stayed green while nothing watched the refusal itself.
            empty_repo = scratch / "a-checkout-without-the-installer"
            (empty_repo / "compose").mkdir(parents=True)
            control("a checkout that does not ship the installer the host homes come from",
                    [str(_raised(lambda: install_module(empty_repo)))],
                    "PRODUCER_UNAVAILABLE", "the installer's rule")
            check("and the refusal names no absolute path of the owner's",
                  str(pathlib.Path.home()) not in str(_raised(lambda: install_module(empty_repo))),
                  "the refusal carried the owner's home")
            control("and the protected set refuses rather than protecting less",
                    [str(_raised(lambda: host_homes({}, empty_repo)))],
                    "PRODUCER_UNAVAILABLE")
            check("the fixture checkout really is one the loader would otherwise accept, bar that file",
                  (empty_repo / "compose").is_dir()
                  and not (empty_repo / "compose" / "instructions_install.py").exists(),
                  f"{masked(empty_repo)} is not the fixture this control describes")
            check("and the real checkout does ship it, so the control above is about an absence",
                  (REPO / "compose" / "instructions_install.py").is_file(),
                  "this checkout has no installer either, so nothing distinguishes the fixture")
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
                globals()["LAYERS"] = (("catalog", {"current": ("a producer that writes", writing_producer, ())}),)
                control("a write is reported even when the inventory failed afterwards",
                        [str(_raised(lambda: run(REPO, state, user, failing_out, ledger=ledger,
                                                          home=fixture_home)))],
                        "STATE_WRITTEN", "in flight")
            finally:
                globals()["LAYERS"] = saved
                planted_write.unlink(missing_ok=True)

            link = state / "runtime" / "a-link-out.json"
            link.symlink_to(scratch / "project" / "CLAUDE.md")
            try:
                manifest = judged_run("the linked-input", REPO, state, user, scratch / "manifest-out", ledger=ledger,
                                      home=fixture_home)
            finally:
                link.unlink()
            inputs = manifest["inputs"]
            # Asked BEFORE the lookups below, because they index the manifest by the projected key: with
            # the projection gone they raise rather than report, and a reader of this suite needs the
            # spelling stated where it can fail as a control instead of as an abort.
            check("the manifest spells the roots it read as the projection does, never as raw paths",
                  bool(inputs["roots"]) and all(key.startswith("<HOME>/") for key in inputs["roots"])
                  and str(state) not in inputs["roots"],
                  f"{sorted(inputs['roots'])}")
            # Read by the PROJECTED key, and read so that a key that is not there REPORTS rather than
            # raises: an indexing lookup aborted this suite with a `KeyError` before any control ran,
            # which is a control asking nothing (S8a's lesson, in the other direction).
            state_row = inputs["roots"].get(masked(state, str(fixture_home))) or {}
            check("the input manifest declares the symlink policy and names the symlink it left out",
                  SYMLINK_POLICY in inputs["symlink_policy"]
                  and any(entry["reason"] == "symlink" and entry["path"] == "runtime/a-link-out.json"
                          for entry in state_row.get("omissions") or []),
                  f"{state_row.get('omissions')} of {sorted(inputs['roots'])}")
        with section('GB#8: a link inside a tree a run really copies is omitted, never followed'):
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
            left_out = omission_lines(freeze([(state / "runtime" / "baselines" / "ref1", "baseline"),
                                              (user / "learnings", "learnings")], frozen_probe))
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
                  set(inputs["roots"]) == {masked(state, str(fixture_home)), masked(user, str(fixture_home))}
                  and masked(state, str(fixture_home)) in inputs["protected_roots"],
                  f"{sorted(inputs['roots'])} / {inputs['protected_roots']}")
            # The `home` argument must not change what a production caller gets. A run given nothing and
            # a run given this process's own home produce the same manifest for the same inputs — which
            # is what "the default is the process's own home" means, stated where a change would fail.
            default_out, named_out = scratch / "home-default-out", scratch / "home-named-out"
            by_default = judged_run("the default-home", REPO, state, user, default_out, ledger=ledger)
            by_process_home = judged_run("the process-home", REPO, state, user, named_out, ledger=ledger,
                                         home=str(pathlib.Path.home()))
            check("a run given no home projects exactly as a run given this process's own home",
                  by_default["inputs"] == by_process_home["inputs"]
                  and by_default["out_dir"] == masked(default_out, str(pathlib.Path.home()))
                  and by_process_home["out_dir"] == masked(named_out, str(pathlib.Path.home())),
                  f"{by_default['inputs']} / {by_process_home['inputs']}")

        with section('GA#0: a credential or a home path planted in every personal carrier kind, and in the'):
            # ---- GA#0: a credential or a home path planted in every personal carrier kind, and in the
            # session's compiled text, reaches no artifact — while the hashes still bind to the raw carrier
            secret = "sk-ant-api03-" + "Ab3" * 14
            # under the home the planted run is GIVEN (home=fixture_home), so the masking judged is that home's
            private = str(fixture_home / "Documents" / "a-directory-of-the-owner-s")
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
                "inputs": snapshot_inputs, "items": [catalog_item("item-1", text="## Item 1\n\n- a rule\n")],
                "file_digests": {name: store._digest((snapshot_dir / name).read_bytes())
                                 for name in ("CLAUDE.md", "output.json")}}), encoding="utf-8")
            (state / "sessions" / "pins" / "claude" / "session-1.json").write_text(
                json.dumps({"schema_version": 1, "content_ref": content_ref, "host": "claude", "session_id": "session-1",
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
                # the census names the pin it read for the session, as `census.py` does from the same state
                {**census_row("claude", "session-1", planted_path), "pin": {"content_ref": content_ref}}]}),
                encoding="utf-8")
            planted_out = scratch / "planted-out"
            manifest = judged_run("the planted", REPO, state, user, planted_out, pin="claude:session-1",
                                  native_roots={"projects": {"project": scratch / "project"}},
                                  run_dir=run_planted, ledger=ledger, commit="fixture", home=fixture_home)
            artifacts = sorted(path for path in planted_out.rglob("*") if path.is_file())
            check("the planted run wrote artifacts to scan", len(artifacts) >= len(REFERENCES),
                  f"{len(artifacts)} artifact(s)")
            leaking = sorted(path.name for path in artifacts
                             if secret in path.read_text(encoding="utf-8") or private in path.read_text(encoding="utf-8"))
            # ...judged over artifacts that exist: a run that wrote nothing carries nothing, and says nothing
            check("no artifact carries the planted credential or the owner's home path",
                  not leaking and len(artifacts) >= len(REFERENCES), f"{leaking} artifacts={len(artifacts)}")
            emitted = {}
            for reference in REFERENCES:
                for unit in written_json(planted_out / "inventory" / f"{reference}.json")["units"]:
                    emitted.setdefault(unit["path"], []).append(unit)
            # ...and the store, where every recorded member is published once: a selection holds no native layer
            # any more (lead ruling 5 on the P2.4 plan), and the AutoMem member here answers no current scope
            # (its path is `~/`, so `memory_path_relative`), so the store is where its units are.
            planted_store_written = written_json(planted_out / "inventory" / STORE_REL)
            for carrier_id_here, rows_here in planted_store_written["versions"].items():
                for version_here, row_here in rows_here.items():
                    for ref_here in row_here["unit_refs"]:
                        unit = planted_store_written["units"][ref_here]
                        emitted.setdefault(row_here["path"], []).append({**unit, "layer": row_here["layer"]})
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
            planted_store_path = planted_out / "inventory" / STORE_REL
            planted_bytes = planted_store_path.read_text(encoding="utf-8") if planted_store_path.is_file() else ""
            planted_store_doc = json.loads(planted_bytes) if planted_bytes else {"versions": {}, "units": {}}
            planted_by_version = {version: [planted_store_doc["units"].get(ref) or {} for ref in row["unit_refs"]]
                                  for rows in planted_store_doc["versions"].values() for version, row in rows.items()}
            planted_raw = [sha256_text(text) for text in planted_in.values()] + [sha256_text(injected)]
            check("the planted run's store, read back from its written file, holds every planted carrier under its raw "
                  "version, masked, and its bytes carry neither the credential nor the home path",
                  bool(planted_bytes) and secret not in planted_bytes and private not in planted_bytes
                  and all(planted_by_version.get(version) for version in planted_raw)
                  and all(any("<REDACTED>" in unit.get("text", "") or "<HOME>" in unit.get("text", "")
                              for unit in planted_by_version[version]) for version in planted_raw
                          if planted_by_version.get(version)),
                  f"file={bool(planted_bytes)} carried={sum(1 for version in planted_raw if planted_by_version.get(version))}"
                  f"/{len(planted_raw)}")
            planted_docs = {reference: written_json(planted_out / "inventory" / f"{reference}.json")
                            for reference in REFERENCES}
            unequal = [(reference, n) for reference, document in planted_docs.items()
                       for n, unit in enumerate(document["units"])
                       if (planted_store_doc["units"].get(unit["unit_ref"]) or {}).get("text") != unit["text"]
                       or (planted_store_doc["units"].get(unit["unit_ref"]) or {}).get("heading") != unit["heading"]]
            check("a unit's text and heading in the store are its document's own: one floor and one decision answer for both",
                  bool(planted_docs["current"]["units"]) and not unequal, f"{len(unequal)} unit(s) differ: {unequal[:3]}")
            kept_project = projection.project
            try:  # a floor that masks nothing: the guard beyond it is what the control reads
                projection.project = lambda text, version=None, home=None: text
                control("a unit the floor left a credential in is never emitted",
                        [str(_raised(lambda: projected(f"apiKeyHelper: {secret}\n", None)))], "DISCLOSED_IN_UNIT")
            finally:
                projection.project = kept_project
            check("the floor itself does mask that unit, so the guard is a second line, not the first",
                  secret not in projected(f"apiKeyHelper: {secret}\n", None), "the floor passed the credential through")

        with section('GA#0 (security review): the fields beside `text`, and the boundary that does not'):
            # ---- GA#0 (security review): the fields beside `text`, and the boundary that does not
            # depend on remembering them
            heading_secret = f"## A heading naming apiKeyHelper {secret} and {private}\n"
            headed = shed(units_of([guide("headed.md", heading_secret + "\n- a rule under it\n")]), home=str(fixture_home))
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
            manifest_path = planted_out / "inventory" / "manifest.json"
            manifest_text = manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else ""
            # POSITIVE (lead, after b0abfef): the roots ARE under the home this run is given, so the manifest
            # spells them `<HOME>/…`; a manifest that holds none of them has nothing for the check below to judge
            check("the planted manifest spells its protected roots and its read roots under the run's home as <HOME>/…",
                  any(str(root).startswith("<HOME>/") for root in manifest.get("inputs", {}).get("protected_roots", []))
                  and any(str(root).startswith("<HOME>/") for root in manifest.get("inputs", {}).get("roots", {})),
                  f"{manifest.get('inputs', {}).get('protected_roots', [])}")
            # The manifest's paths are masked ONCE, by MANIFEST_TABLE's METADATA rule (lead, after b0abfef). That
            # `masked()` before it added nothing rested on two facts, judged here rather than assumed: over paths
            # under the home a run is given, the projection is idempotent, and `masked()` is that same projection.
            fixture_home_text = str(fixture_home)
            idem_cases = [f"{fixture_home_text}/state", fixture_home_text, f"{fixture_home_text}/user/",
                          f"{fixture_home_text}/Documents/a b/x", "/elsewhere/state", f"{fixture_home_text}x/state",
                          f"{fixture_home_text}/.claude/projects/p/memory", f"{fixture_home_text}/state/api_key=abc"]
            idem_rows = [(case, projection.project(case, projection.CURRENT, fixture_home_text)) for case in idem_cases]
            check("over eight paths at, under, beside and outside a run's home, projecting twice is projecting once, and "
                  "masked() is that projection",
                  all(projection.project(once, projection.CURRENT, fixture_home_text) == once
                      and masked(case, fixture_home_text) == once for case, once in idem_rows)
                  and sum("<HOME>" in once for _case, once in idem_rows) == 6,
                  f"{[(case[len(fixture_home_text):] if case.startswith(fixture_home_text) else case, once) for case, once in idem_rows]}")
            check("the manifest carries no owner home prefix",
                  bool(manifest_text) and str(pathlib.Path.home()) not in manifest_text and str(fixture_home) not in manifest_text,
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
        with section('GB#6: a credential relationship, and a refusal that repeats nothing'):
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

        with section('the 1548 amendment: the native layers come from the transcript, settings never do'):
            # ---- the 1548 amendment: the native layers come from the transcript, settings never do,
            # and nothing reads a native file in any mode
            split_out = scratch / "split-out"
            split = judged_run("the split", REPO, state, user, split_out, ledger=ledger, **captured())
            split_doc = written_json(split_out / "inventory" / "current.json")
            native_rows = {row["layer"]: row for row in split_doc["layers"] if row["layer"] in NATIVE_LAYERS}
            check("every native layer is in the table", set(native_rows) == set(NATIVE_LAYERS),
                  f"{sorted(native_rows)}")
            # The fixture holds a Codex rollout, so the divided layers are unknown at its scopes (S-19)
            # while every Claude scope answers, and the block answers at its own layer value.
            split_scopes = {(row["layer"], row["host"]): row["status"] for row in split_doc["scopes"]}
            check("the layers a transcript records answer at the current reference point, scope by scope",
                  all(split_scopes.get((layer, "claude")) in ("answered", "empty") for layer in TRANSCRIPT_LAYERS)
                  and all(split_scopes.get((layer, "codex")) == "unknown" for layer in TRANSCRIPT_LAYERS)
                  and all(native_rows[layer]["status"] == "unknown"
                          and any("one block" in text for text in native_rows[layer]["reasons"]) for layer in TRANSCRIPT_LAYERS)
                  and {row["layer"]: row["status"] for row in split_doc["layers"]}.get("native_undivided") == "complete",
                  f"{sorted(split_scopes.items())}")
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
                  bool(split_doc["produced_by"]) and "mode" not in split_doc["produced_by"]
                  and split["inputs"]["transcripts"]["native_files_read"] == 0,
                  f"{sorted(split_doc['produced_by'])}")
            # A run with no census at all: every native layer unknown, with the census reason.
            blind_out = scratch / "blind-out"
            blind = judged_run("the blind", REPO, state, user, blind_out, ledger=ledger, home=fixture_home,
                               native_roots={"projects": {"project": scratch / "project"}})
            blind_rows = {row["layer"]: row for row in written_json(blind_out / "inventory" / "current.json")["layers"]}
            control("a run with no census to read a transcript through",
                    [f"{layer}={blind_rows[layer]['status']}: " + "; ".join(blind_rows[layer]["reasons"])
                     for layer in TRANSCRIPT_LAYERS],
                    "native_global=unknown", "INPUT_UNACQUIRED")
            check("a run with no census is incomplete", blind["references"]["current"]["complete"] is False,
                  "a run that bound no transcript reported complete")

        with section('GA#5: a malformed supported carrier is incomplete, not unsupported, and says which'):
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

        with section('GA#5: a failure acquiring the inputs still leaves a layer-status artifact naming it'):
            # ---- GA#5: a failure acquiring the inputs still leaves a layer-status artifact naming it
            brittle = fixture_home / "brittle-state"
            (brittle / "runtime").mkdir(parents=True)
            (brittle / "runtime" / "state.json").write_text('{"schema_version": 1,\n', encoding="utf-8")
            brittle_out = scratch / "brittle-out"
            brittle_manifest, brittle_failure = {"references": {}}, None
            try:  # the subject is guarded: a run that raises makes this control fail, not the suite abort
                brittle_manifest = run(REPO, brittle, user, brittle_out, ledger=ledger,
                                       home=fixture_home)
            except Exception as exc:
                brittle_failure = exc
            control("a run whose input freezing failed",
                    ([f"the run raised instead of reporting it: {type(brittle_failure).__name__}"]
                     if brittle_failure is not None else
                     [reason for entry in brittle_manifest["references"].values() for reason in entry["incomplete_reasons"]]),
                    UNKNOWN_REASONS["input_failed"], "runtime_state: not_json")
            check("the failed acquisition still wrote a layer-status artifact per reference point",
                  all((brittle_out / "inventory" / f"{reference}.json").is_file() for reference in REFERENCES),
                  "a reference point lost its artifact to the acquisition failure")
            brittle_current = brittle_out / "inventory" / "current.json"
            brittle_layers = {row["layer"]: row for row in (json.loads(brittle_current.read_text(encoding="utf-8"))["layers"]
                                                            if brittle_current.is_file() else [])}
            # #16: the failure answers for the producers that READ the runtime state, and for nothing
            # else. It used to turn every layer unknown — the checkout's catalog and the ledger included.
            check("every layer of that artifact carries a status, and the ones reading the runtime state say why",
                  len(brittle_layers) == len(LAYERS)
                  and all(brittle_layers.get(layer, {}).get("status") == "unknown"
                          and "runtime_state" in "; ".join(brittle_layers.get(layer, {}).get("reasons") or [])
                          for layer in ("adopted_packages", "overlays")),
                  f"{[(layer, row['status']) for layer, row in brittle_layers.items()]}")
            check("and a layer that reads none of the owner's state keeps its own answer",
                  brittle_layers.get("catalog", {}).get("status") == "complete"
                  and brittle_layers.get("ledger_keep", {}).get("status") == "complete",
                  f"{[(layer, row['status']) for layer, row in brittle_layers.items()]}")

        with section('GA#6, GA#7, GA#8: adopted packages, overlays per host, and both baselines frozen'):
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
            both = judged_run("the both-baselines", REPO, state, user, both_out, pin="claude:session-1",
                              ledger=ledger, commit="fixture", **captured())
            current_doc = written_json(both_out / "inventory" / "current.json")
            notes = current_doc["produced_by"]["notes"]
            control("a run whose pin names an older baseline than the installed one",
                    [f"installed={notes['baselines']['installed']} pinned={notes['baselines']['pinned']} "
                     f"differ={notes['baselines']['differ']}"],
                    "installed=ref2", "pinned=ref1", "differ=True")
            frozen_both = [row for row in notes.get("frozen_missing", []) if "baselines" in str(row.get("path"))]
            check("both baselines were frozen, so neither resolver is left without its tuple",
                  bool(notes) and not frozen_both, f"{frozen_both} notes={bool(notes)}")
            # The schema is a contract, not a second list: the real document's units and layer rows are
            # validated against it, so a record that drifts fails here too (the 1548 amendment §10).
            clean("a produced document's units and layer rows against the schema the code owns",
                  document_contract_problems(current_doc) if current_doc else ["the run wrote no current.json"])
            check("that document really has units to judge", len(current_doc["units"]) > 100,
                  f"{len(current_doc['units'])} unit(s)")
            both_sessions_path = both_out / "inventory" / f"{SESSIONS}.json"
            both_sessions = (json.loads(both_sessions_path.read_text(encoding="utf-8")) if both_sessions_path.is_file()
                             else {"document": "sessions", "sessions": [], "events": []})
            check("the run published sessions.json", both_sessions_path.is_file(), "no inventory/sessions.json")
            clean("the run's published sessions.json against its own root in the schema",
                  document_contract_problems(both_sessions) if both_sessions_path.is_file()
                  else ["the run wrote no sessions.json"])
            check("and it holds a record for every census row, with the manifest's count beside it",
                  len(both_sessions["sessions"]) >= 1
                  and (both.get("sessions") or {}).get("sessions") == len(both_sessions["sessions"])
                  and len(both_sessions["events"]) == (both.get("sessions") or {}).get("events") >= 1,
                  f"sessions={len(both_sessions['sessions'])} events={len(both_sessions['events'])}")
            both_store_path = both_out / "inventory" / STORE_REL
            both_store = (json.loads(both_store_path.read_text(encoding="utf-8")) if both_store_path.is_file()
                          else {"document": STORE, "versions": {}, "units": {}})
            check("the run published shared/store.json, and the manifest counts its versions and units",
                  both_store_path.is_file() and len(both_store["units"]) > 100
                  and (both.get("store") or {}) == {"versions": sum(len(rows) for rows in both_store["versions"].values()),
                                                    "units": len(both_store["units"])},
                  f"store={both.get('store')} units={len(both_store['units'])}")
            clean("the run's published store against its own root in the schema",
                  document_contract_problems(both_store) if both_store_path.is_file() else ["the run wrote no store"])
            both_documents = {reference: written_json(both_out / "inventory" / f"{reference}.json")
                              for reference in REFERENCES}
            clean("every unit of the run's three documents resolves in its store as that block, each version once",
                  crossing(both_store, both_documents) if both_store_path.is_file() and all(both_documents.values())
                  else ["the run wrote no store or no reference document"])
            injection_id = canonical("c", "session_injection", "claude", content_ref)
            injection_units = [unit for unit in both_documents["current"]["units"] if unit["layer"] == "session_injection"]
            check("a session injection's carrier is its host and the snapshot it was compiled into, in the document "
                  "and in the store",
                  bool(injection_units) and {unit["carrier_id"] for unit in injection_units} == {injection_id}
                  and injection_id in both_store["versions"],
                  f"units={len(injection_units)} in_store={injection_id in both_store['versions']}")
            both_sessions_doc = written_json(both_out / "inventory" / f"{SESSIONS}.json")
            clean("every occurrence of the run's sessions.json resolves against its store",
                  occurring(both_sessions_doc, both_store) if both_sessions_doc and both_store_path.is_file()
                  else ["the run wrote no sessions.json or no store"])
            check("and the run recorded occurrences to judge", len(both_sessions_doc.get("occurrences") or []) >= 1,
                  f"{len(both_sessions_doc.get('occurrences') or [])}")
            kept_occurrences = globals()["event_occurrences"]

            def misnumbered(event_in, injection_in=None):
                return [{**row, "ordinal": row["ordinal"] + 1} for row in kept_occurrences(event_in, injection_in)]

            misnumbered_out = scratch / "misnumbered-out"
            try:
                globals()["event_occurrences"] = misnumbered
                misnumbered_raised = _raised(lambda: run(REPO, state, user, misnumbered_out, pin="claude:session-1",
                                                         ledger=ledger, commit="fixture", **captured()))
            finally:
                globals()["event_occurrences"] = kept_occurrences
            check("an occurrence whose id its own fields do not derive refuses the whole run by name, and nothing is written",
                  isinstance(misnumbered_raised, Refused) and "OCCURRENCE_ID_MISMATCH" in str(misnumbered_raised)
                  and not (misnumbered_out / "inventory" / f"{SESSIONS}.json").exists(),
                  f"{type(misnumbered_raised).__name__}")
            kept_store = globals()["store_document"]

            def holed_store(ctx_in):
                document = kept_store(ctx_in)
                first = sorted(document["units"])[0]
                document["units"] = {ref: row for ref, row in document["units"].items() if ref != first}
                return document

            holed_out = scratch / "holed-out"
            try:
                globals()["store_document"] = holed_store
                holed = _raised(lambda: run(REPO, state, user, holed_out, pin="claude:session-1", ledger=ledger,
                                            commit="fixture", **captured()))
            finally:
                globals()["store_document"] = kept_store
            check("a store a published unit cannot resolve against refuses the whole run by name, and nothing is written",
                  isinstance(holed, Refused) and "STORE_UNRESOLVED" in str(holed)
                  and not (holed_out / "inventory" / "current.json").exists()
                  and not (holed_out / "inventory" / STORE_REL).exists(),
                  f"{type(holed).__name__}")
            kept_record = globals()["session_record"]

            def mixed_record(*args, **kwargs):
                record = kept_record(*args, **kwargs)
                record["limitations"] = record["limitations"] + [
                    {"kind": "alt_paths", "count": 1, "line": 3, "category": "not_json"}]
                return record

            mixed_out = scratch / "mixed-out"
            try:
                globals()["session_record"] = mixed_record
                mixed = _raised(lambda: run(REPO, state, user, mixed_out, pin="claude:session-1",
                                            ledger=ledger, commit="fixture", **captured()))
            finally:
                globals()["session_record"] = kept_record
            check("a limitation carrying another kind's fields is refused by name on the publication path, "
                  "and nothing is written",
                  isinstance(mixed, Refused) and "EMISSION_UNION_UNMATCHED session.limitations[" in str(mixed)
                  and not any(mixed_out.rglob("*.json")),
                  f"refused={isinstance(mixed, Refused)} named={'EMISSION_UNION_UNMATCHED' in str(mixed)} "
                  f"written={len(list(mixed_out.rglob('*.json')))}")
            kept_cross = globals()["sessions_cross_problems"]
            crossed_out = scratch / "crossed-out"
            try:
                globals()["sessions_cross_problems"] = lambda document: ["CROSS_EVENT_DUPLICATE: planted"]
                crossed = _raised(lambda: run(REPO, state, user, crossed_out, pin="claude:session-1",
                                              ledger=ledger, commit="fixture", **captured()))
            finally:
                globals()["sessions_cross_problems"] = kept_cross
            check("a run whose sessions.json records disagree with one another is refused, and writes no document",
                  isinstance(crossed, Refused) and "CROSS_EVENT_DUPLICATE" in str(crossed)
                  and not any(crossed_out.rglob("*.json")),
                  f"refused={isinstance(crossed, Refused)} written={len(list(crossed_out.rglob('*.json')))}")
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
                  bool(overlay_units) and not any(unit["item_ref"] == "@fixture/core:item-3" for unit in overlay_units),
                  "a tombstoned item came back as an overlay")
            adopted_rows = {reference: [unit for unit in written_json(both_out / "inventory" / f"{reference}.json")["units"]
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

        with section('#16: an omission answers for the producers that READ that input, and for no other'):
            # ---- #16: an omission answers for the producers that READ that input, and for no other.
            # Each input kind is planted failed (a link where the input is) and, where its class has one,
            # absent, in a copy of the fixture state; the statuses of every layer at every reference point
            # are compared with the clean copy's. The expected sets are written here, not derived from the
            # declarations they judge, so a declaration that moves fails against something it is not.
            matrix_seq = [0]

            def statuses_over(state_root, user_root, pin="claude:session-1"):
                matrix_seq[0] += 1
                frozen_for = scratch / f"matrix-frozen-{matrix_seq[0]}"
                ctx = context_of(REPO, state_root, user_root, {}, pin, ledger)
                freeze_inputs(frozen_for, REPO, state_root, user_root, pin, ctx)
                bind_transcripts(ctx, run_planted)
                return {f"{reference}/{row['layer']}": (row["status"], "; ".join(row["reasons"]))
                        for reference in REFERENCES for row in layer_rows(reference, ctx)}

            def copied_fixture(label):
                case = scratch / f"matrix-{label}"
                shutil.copytree(state, case / "state", symlinks=True)
                shutil.copytree(user, case / "user", symlinks=True)
                return case / "state", case / "user"

            def linked_instead(path):
                """`path` replaced by a link to a copy of itself outside the fixture: a failed acquisition."""
                aside = scratch / "matrix-outside" / f"{len(list((scratch / 'matrix-outside').glob('*'))) if (scratch / 'matrix-outside').is_dir() else 0}-{path.name}"
                aside.parent.mkdir(parents=True, exist_ok=True)
                if path.is_dir():
                    shutil.copytree(path, aside)
                    shutil.rmtree(path)
                else:
                    shutil.copyfile(path, aside)
                    path.unlink()
                path.symlink_to(aside)

            def removed(path):
                shutil.rmtree(path) if path.is_dir() else path.unlink()

            matrix_pin = json.loads((state / "sessions" / "pins" / "claude" / "session-1.json").read_text(encoding="utf-8"))
            matrix_installed = json.loads((state / "runtime" / "state.json").read_text(encoding="utf-8"))["selected_baseline_ref"]
            clean_statuses = statuses_over(state, user)
            reads_state_now = {"current/adopted_packages", "current/overlays"}
            # A selection's native rows read no pin any more: they are `per_event` (lead ruling 5 on the P2.4 plan).
            reads_the_pin = {"release/catalog", "release/adopted_packages", "selection/catalog",
                             "selection/adopted_packages", "selection/overlays", "current/session_injection",
                             "selection/session_injection"}
            reads_the_snapshot = set(reads_the_pin)
            matrix_cases = [
                ("runtime_state", "failed", lambda s, u: linked_instead(s / "runtime" / "state.json"), reads_state_now),
                ("runtime_state", "absent", lambda s, u: removed(s / "runtime" / "state.json"), reads_state_now),
                ("user_state", "failed", lambda s, u: linked_instead(u / "state.json"), reads_state_now),
                ("user_state", "absent", lambda s, u: removed(u / "state.json"), set()),
                ("learning_journals", "failed", lambda s, u: linked_instead(u / "learnings" / "claude" / "events.jsonl"),
                 {"current/overlays"}),
                ("learning_journals", "absent", lambda s, u: removed(u / "learnings"), set()),
                ("pin", "failed", lambda s, u: linked_instead(s / "sessions" / "pins" / "claude" / "session-1.json"),
                 reads_the_pin),
                ("pin", "absent", lambda s, u: removed(s / "sessions" / "pins" / "claude" / "session-1.json"),
                 reads_the_pin),
                ("snapshot", "failed", lambda s, u: linked_instead(s / "sessions" / "snapshots" / matrix_pin["content_ref"]),
                 reads_the_snapshot),
                ("snapshot", "absent", lambda s, u: removed(s / "sessions" / "snapshots" / matrix_pin["content_ref"]),
                 reads_the_snapshot),
                ("installed_baseline", "failed", lambda s, u: linked_instead(s / "runtime" / "baselines" / matrix_installed),
                 reads_state_now),
                ("installed_baseline", "absent", lambda s, u: removed(s / "runtime" / "baselines" / matrix_installed),
                 reads_state_now),
                # A link INSIDE the pinned baseline, beside an item list that copies fine: only the freeze
                # result says the copy is short, so a discarded result reads the baseline as whole.
                ("release_baseline", "failed",
                 lambda s, u: linked_instead(s / "runtime" / "baselines" / "ref1" / "defaults.json"),
                 {"release/catalog", "release/adopted_packages"}),
                ("release_baseline", "absent", lambda s, u: removed(s / "runtime" / "baselines" / "ref1"),
                 {"release/catalog", "release/adopted_packages"}),
            ]
            check("the matrix's fixture pins one baseline and installs another, so the two are told apart",
                  matrix_installed != "ref1" and matrix_pin.get("content_ref") is not None,
                  f"installed_is_pinned={matrix_installed == 'ref1'}")
            every_subject = set().union(*(expected for *_rest, expected in matrix_cases))
            check("every layer the matrix expects to change answers in the clean copy",
                  all(clean_statuses.get(cell, ("unknown",))[0] != "unknown" for cell in every_subject),
                  f"{sorted(cell for cell in every_subject if clean_statuses.get(cell, ('unknown',))[0] == 'unknown')}")
            for kind, outcome, plant, expected in matrix_cases:
                case_state, case_user = copied_fixture(f"{kind}-{outcome}")
                plant(case_state, case_user)
                try:
                    case_statuses, failure = statuses_over(case_state, case_user), None
                except Exception as exc:  # a case that raises fails its own control by name
                    case_statuses, failure = {}, exc
                changed = {cell for cell in clean_statuses if case_statuses.get(cell, (None,))[0] != clean_statuses[cell][0]}
                check(f"#16 {kind} {outcome}: exactly the layers that read it change",
                      failure is None and changed == expected,
                      f"raised={type(failure).__name__ if failure else None} "
                      f"unexpected={sorted(changed - expected)} unchanged={sorted(expected - changed)}")
                check(f"#16 {kind} {outcome}: and each of them is unknown, naming the input",
                      failure is None and all(case_statuses[cell][0] == "unknown" and kind in case_statuses[cell][1]
                                              for cell in expected),
                      f"{sorted(cell for cell in expected if kind not in case_statuses.get(cell, ('', ''))[1])}")
            # The acquisition's own unexpected failure: what it cannot attribute to one input reaches every
            # producer that reads the owner's state, and still none that reads only the checkout, the
            # transcripts or the ledger.
            # Planted INSIDE the acquisition, where a real one would arise: `freeze_inputs` points the
            # context at the frozen copies before it copies anything, so what it leaves behind is that.
            kept_freeze = globals()["freeze"]
            try:
                def unexpected(*_args, **_kwargs):
                    raise RuntimeError("a planted failure no input owns")

                globals()["freeze"] = unexpected
                stray_out = scratch / "matrix-unexpected-out"
                stray = _raised(lambda: run(REPO, state, user, stray_out, pin="claude:session-1", ledger=ledger,
                                            run_dir=run_planted, home=fixture_home,
                                            native_roots={"projects": {"project": scratch / "project"}}))
            finally:
                globals()["freeze"] = kept_freeze
            stray_layers = {row["layer"]: row for row in (json.loads(
                (stray_out / "inventory" / "current.json").read_text(encoding="utf-8"))["layers"]
                if (stray_out / "inventory" / "current.json").is_file() else [])}
            stray_rows = {layer: row["status"] for layer, row in stray_layers.items()}
            stray_record = next((row for row in (json.loads((stray_out / "inventory" / f"{SESSIONS}.json").read_text(
                encoding="utf-8"))["sessions"] if (stray_out / "inventory" / f"{SESSIONS}.json").is_file() else [])
                if row["transcript"]["id"] == "session-1"), {})
            stray_reference = (json.loads((stray_out / "inventory" / "current.json").read_text(encoding="utf-8"))["reference"]
                               if (stray_out / "inventory" / "current.json").is_file() else {})
            check("an unattributed acquisition failure's reason is its fixed category, never the exception's type or text",
                  any(text.startswith("INPUT_UNACQUIRED: freezing the inputs failed (not_admitted)")
                      for text in stray_reference.get("incomplete_reasons") or [])
                  and not exception_named_problems(stray_reference)[0]
                  and not any("a planted failure no input owns" in text for text in stray_reference.get("incomplete_reasons") or []),
                  f"{stray_reference.get('incomplete_reasons')}")
            check("an unattributed acquisition failure leaves the checkout, transcript and ledger layers their answers",
                  stray is None and stray_rows.get("catalog") == "complete" and stray_rows.get("native_project") == "complete"
                  and stray_rows.get("ledger_keep") == "complete"
                  and stray_rows.get("overlays") == "unknown" and stray_rows.get("session_injection") == "unknown",
                  f"raised={type(stray).__name__ if stray else None} {sorted(stray_rows.items())}")
            # The census names session-1's pin, and the failure left it unread: the global scope its event is
            # chosen for depends on that pin (S-8 b, S-25), so it is the one transcript layer that becomes
            # unknown, by that reason, and the session's own record says its pin failed.
            check("and the global scope a session whose pin the failure left unread is chosen for is "
                  "exclusion_unreadable, while that session's record says its pin failed",
                  stray_rows.get("native_global") == "unknown"
                  and any(text.startswith(f"native_global: {UNKNOWN_REASONS['exclusion_unreadable']}")
                          for text in stray_layers.get("native_global", {}).get("reasons") or [])
                  and (stray_record.get("pin") or {}).get("reason") == "input_failed"
                  and (stray_record.get("delivery") or {}).get("reason") == "input_failed",
                  f"{stray_rows.get('native_global')} {stray_layers.get('native_global', {}).get('reasons')} "
                  f"{stray_record.get('pin')} {stray_record.get('delivery')}")

            # A --pin whose census row names no pin while the frozen state holds one: under M6 the two disagree
            # (lead ruling on the P2.4 readings, 2026-10-29). Both written files name pin_content_ref_mismatch,
            # and neither says unpinned while the other shows the selection. A session the --pin does not name,
            # with no pin in its census row, stays `unpinned` and its pin file is not read: here it is a link,
            # which a read would refuse.
            nopin_state = scratch / "nopin-state"
            shutil.copytree(state, nopin_state, symlinks=True)
            (nopin_state / "sessions" / "pins" / "claude" / "s-other.json").symlink_to(
                nopin_state / "sessions" / "pins" / "claude" / "session-1.json")
            other_path = jsonl(scratch / "transcripts" / "claude" / "s-other.jsonl", [
                attachment("2026-10-04T10:00:00+00:00", [member("Project", f"{project_scope}/CLAUDE.md", "# Other\n\n- other\n")],
                           cwd=project_scope)])
            run_nopin = scratch / "run-nopin"
            run_nopin.mkdir(parents=True, exist_ok=True)
            (run_nopin / CENSUS).write_text(json.dumps({"transcripts": [
                census_row("claude", "session-1", planted_path), census_row("claude", "s-other", other_path)]}),
                encoding="utf-8")
            nopin_out = scratch / "nopin-out"
            nopin = _raised(lambda: run(REPO, nopin_state, user, nopin_out, pin="claude:session-1", run_dir=run_nopin,
                                        ledger=ledger, commit="fixture", home=fixture_home,
                                        native_roots={"projects": {"project": scratch / "project"}}))
            nopin_files = {name: json.loads((nopin_out / "inventory" / rel).read_text(encoding="utf-8"))
                           if (nopin_out / "inventory" / rel).is_file() else {}
                           for name, rel in (("sessions", f"{SESSIONS}.json"), ("selection", "selection.json"),
                                             ("current", "current.json"))}
            nopin_records = {row["transcript"]["id"]: row for row in nopin_files["sessions"].get("sessions") or []}
            nopin_reference = nopin_files["selection"].get("reference") or {}
            nopin_injection = next((row for row in nopin_files["selection"].get("layers") or []
                                    if row["layer"] == "session_injection"), {})
            check("a --pin whose census row names no pin while the state holds one: sessions.json names "
                  "pin_content_ref_mismatch for its pin and its delivery, with the snapshot the pin names",
                  nopin is None and (nopin_records.get("session-1") or {}).get("pin") == {
                      "status": "unknown", "reason": "pin_content_ref_mismatch", "content_ref": matrix_pin["content_ref"],
                      "baseline_ref": None, "include_global_instructions": None}
                  and ((nopin_records.get("session-1") or {}).get("delivery") or {}).get("reason") == "pin_content_ref_mismatch",
                  f"raised={type(nopin).__name__ if nopin else None} {(nopin_records.get('session-1') or {}).get('pin')}")
            check("and selection.json, still that pin's evidence, names the same reason: neither file says unpinned while "
                  "the other shows the selection",
                  nopin_injection.get("status") == "complete" and nopin_reference.get("complete") is False
                  and any(text.startswith("pin_content_ref_mismatch: ") for text in nopin_reference.get("incomplete_reasons") or [])
                  and ((nopin_records.get("session-1") or {}).get("pin") or {}).get("status") != "unpinned",
                  f"{nopin_injection.get('status')} {nopin_reference.get('incomplete_reasons')}")
            nopin_global = next((row for row in nopin_files["current"].get("layers") or [] if row["layer"] == "native_global"), {})
            check("and its session record's selection carries the same reason and names no shared inventory, while every "
                  "row of its selection.json is evidence or a declared reason",
                  (nopin_records.get("session-1") or {}).get("selection") == {
                      "status": "unknown", "reason": "pin_content_ref_mismatch", "inventory_ref": None}
                  and bool(nopin_files["selection"].get("layers")) and not undeclared_rows(nopin_files["selection"]["layers"]),
                  f"{(nopin_records.get('session-1') or {}).get('selection')} {undeclared_rows(nopin_files['selection'].get('layers') or [])}")
            check("and the written current.json's global scope, which that session's event is chosen for, is "
                  "exclusion_unreadable (lead reading, 12:40)",
                  nopin_global.get("status") == "unknown"
                  and any(text.startswith(f"native_global: {UNKNOWN_REASONS['exclusion_unreadable']}")
                          for text in nopin_global.get("reasons") or []),
                  f"{nopin_global.get('status')} {nopin_global.get('reasons')}")
            check("a session the --pin does not name, whose census row names no pin, stays unpinned and its pin file is "
                  "not read",
                  (nopin_records.get("s-other") or {}).get("pin") == {
                      "status": "unpinned", "reason": "unpinned", "content_ref": None, "baseline_ref": None,
                      "include_global_instructions": None}
                  and ((nopin_records.get("s-other") or {}).get("delivery") or {}).get("reason") == "unpinned",
                  f"{(nopin_records.get('s-other') or {}).get('pin')}")

        with section('GC#1: the temporary location is chosen and judged before anything is written'):
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

        with section("R1#5: the SELF-TEST's own scratch parent is chosen by the same path-only rule. Both"):
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

        with section('GC#0: every copy destination is confined, and every label is an identifier'):
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

        with section('GC#4: a credential whose key the splitter left in the previous block'):
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

        with section('R2#3: this module is an entry point, and everything it publishes passes the floor'):
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
        with section('r4 R8: a failing control keeps its NAME. A name and its detail can read as a'):
            # ---- r4 R8: a failing control keeps its NAME. A name and its detail can read as a
            # credential key and its value TOGETHER while each passes the floor alone, and the floor then
            # withheld the whole line — tag, suite label and name with it — so a harness looking for
            # `[FAIL] <name>` read a named failure as an unnamed one. That is what r4's R0 revert did,
            # and the pair below is the one it did it with.
            #
            # Every detail HERE is booleans only. A control for this defect must report through a line
            # the defect itself cannot eat: with the fix reverted, a detail quoting the planted text or
            # the published line makes this control's own failure line the withheld one, and the row
            # proving the fix reads as unnamed (r4 R8, second round).
            home_here_str = str(pathlib.Path.home())
            eaten_name = "the withheld version's secret in no published string"
            eaten_detail = "carrying=['document$.units[4].text']"
            eaten_line = f"inventory --self-test [FAIL] {eaten_name}: {eaten_detail}"
            check("the planted name and the planted detail each pass the floor alone",
                  projection.diagnostic(eaten_name, home_here_str) == eaten_name
                  and projection.diagnostic(eaten_detail, home_here_str) == eaten_detail,
                  f"name_unchanged={projection.diagnostic(eaten_name, home_here_str) == eaten_name} "
                  f"detail_unchanged={projection.diagnostic(eaten_detail, home_here_str) == eaten_detail}")
            check("and the two of them together are withheld as one line",
                  projection.diagnostic(eaten_line, home_here_str).strip() == projection.blank_for("x"),
                  f"withheld={projection.diagnostic(eaten_line, home_here_str).strip() == projection.blank_for('x')}")
            kept = boundary.failure_text("inventory --self-test", eaten_name, eaten_detail, home_here_str)
            control("a failure whose name and detail trip the floor together still publishes its name",
                    [f"has_tag={'[FAIL]' in kept} has_name={eaten_name in kept} "
                     f"has_label={'inventory --self-test' in kept}"],
                    "has_tag=True", "has_name=True", "has_label=True")
            # The correction: the fallback may not publish the DETAIL in any form. The floor withheld the
            # line because of the pair, and a detail re-judged alone loses exactly the context it was
            # refused for — so projecting it again publishes what the whole-line judgement had refused.
            marked_name = "the planted secret"
            marked_detail = '"alpha-bravo-charlie"'
            marked_line = f"inventory --self-test [FAIL] {marked_name}: {marked_detail}"
            check("the planted value passes the floor on its own, so only the pair is the problem",
                  projection.diagnostic(marked_detail, home_here_str) == marked_detail
                  and projection.diagnostic(marked_line, home_here_str).strip() == projection.blank_for("x"),
                  f"detail_unchanged={projection.diagnostic(marked_detail, home_here_str) == marked_detail} "
                  f"pair_withheld={projection.diagnostic(marked_line, home_here_str).strip() == projection.blank_for('x')}")
            marked = boundary.failure_text("inventory --self-test", marked_name, marked_detail, home_here_str)
            control("a detail the floor admits alone is still not published when the pair is withheld",
                    [f"has_tag={'[FAIL]' in marked} has_name={marked_name in marked} "
                     f"carries_value={'alpha-bravo-charlie' in marked}"],
                    "has_tag=True", "has_name=True", "carries_value=False")
            # And the printer that does not project is closed by TYPE rather than by convention: its
            # docstring named its callers, which nothing held, so any string could have left through it
            # unprojected. Details are booleans here for the same reason as above.
            plain_refusal = ""
            try:
                boundary.emit("a plain string nobody projected", io.StringIO())
            except TypeError as exc:
                plain_refusal = str(exc)
            control("the unprojecting printer refuses a line that did not come from the floor",
                    [f"refused={'EMIT_UNPROJECTED' in plain_refusal} "
                     f"names_the_type={'FailureLine' in plain_refusal}"],
                    "refused=True", "names_the_type=True")
            emitted_sink = io.StringIO()
            boundary.emit(boundary.failure_text("inventory --self-test", "a planted control", "a planted detail",
                                                home_here_str), emitted_sink)
            check("and the real report path still prints through it",
                  "[FAIL] a planted control: a planted detail" in emitted_sink.getvalue(),
                  f"printed={bool(emitted_sink.getvalue().strip())}")
            # r5 F5: the type is a MARKER — anyone can wrap any string in it — so the one thing a check
            # can hold is that nothing outside the boundary module constructs one. Read as a tree, since
            # a mention in a docstring is not a call, and over SOURCES the caller may supply, so the
            # check itself can be shown to fire.
            def forged_failure_lines(sources=None):
                """Every `FailureLine(...)` construction outside `runlib/entry.py`, as `rel:line`."""
                found = []
                held = dict(sources or {})
                paths = sorted(str(path.relative_to(REPO)) for path in (REPO / "session-distill").rglob("*.py")
                               if "__pycache__" not in str(path))
                for rel in sorted(set(paths) | set(held)):
                    if rel.endswith("runlib/entry.py"):
                        continue
                    source = held.get(rel)
                    if source is None:
                        source = (REPO / rel).read_text(encoding="utf-8")
                    for node in ast.walk(ast.parse(source)):
                        if isinstance(node, ast.Call) and getattr(node.func, "attr",
                                                                  getattr(node.func, "id", "")) == "FailureLine":
                            found.append(f"{rel}:{node.lineno}")
                return found

            check("nothing outside the boundary module builds a FailureLine of its own",
                  not forged_failure_lines()
                  and len(list((REPO / "session-distill").rglob("*.py"))) > 10,
                  f"sites={len(forged_failure_lines())}")
            planted_forge = forged_failure_lines(
                {"session-distill/runlib/planted.py":
                 "from runlib.entry import FailureLine, emit\n\n\ndef _planted():\n"
                 "    return emit(FailureLine('a line nothing projected'))\n"})
            control("and that check sees a construction planted outside it",
                    [f"found={len(planted_forge)} "
                     f"named={any(row.startswith('session-distill/runlib/planted.py:') for row in planted_forge)}"],
                    "found=1", "named=True")
            # Every name this suite has registered so far, held against the floor: a name the floor
            # changes is a name that can be the thing withheld, whatever line it sits in.
            unprojected_names = [name for name in ran if projection.diagnostic(name, home_here_str) != name]
            check("every control name this suite registered passes the floor unchanged",
                  not unprojected_names and len(ran) > 100,
                  f"unchanged={len(ran) - len(unprojected_names)} of {len(ran)}")
        with section('N1: this suite runs ITSELF below, and at depth 1 only. The child used to be kept'):
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
            # `printf` is a shell builtin and `/bin/sleep` is absolute, so this script needs nothing
            # from PATH — the first version used bare `sleep`, which PATH did not hold, so the fixture
            # git died at once with code 127 and the control passed on the wrong failure (r3 #8 rework).
            #
            # The budget below used to be 0.5s against a 3s sleep, which made the marker check a question
            # about a child's START-UP time: in 8 of 61 inventory runs across r7 and r8 the timeout fired
            # before the shell had written it, and the refusal control passed while this one failed. The
            # margin is now wide in both directions — 3s to be seen, 30s before the child would end on
            # its own — so what is read is the refusal and not the scheduler. The marker carries the two
            # pids, because a 30s sleep that outlived the bound would outlive this suite.
            def slow_git_script(marker):
                """`(the fixture git's text, the environment it reads its marker path from)`.

                The path reaches the script through the ENVIRONMENT and the expansion is QUOTED.
                Interpolated bare after `>`, a scratch parent holding a space made the shell redirect to
                the path's first word — a file outside scratch, truncated by a fixture (r4 R3). A suite's
                own shell text is shell, and a path is not a word. One function, so the control below
                runs the same text this fixture does."""
                return ("#!/bin/sh\n/bin/sleep 30 &\n"
                        "printf '%s\\n%s\\n' \"$!\" \"$$\" > \"$SLOW_GIT_MARKER\"\nwait\n",
                        {"SLOW_GIT_MARKER": str(marker)})

            slow_script, slow_script_env = slow_git_script(slow_marker)
            (slow_bin / "git").write_text(slow_script, encoding="utf-8")
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
                tracked_paths(slow_tree, git_env={"PATH": f"{slow_bin}:/usr/bin:/bin", **slow_script_env},
                              git_timeout=3)
                slow_git = "a listing came back from a git that never answered"
            except Exception as exc:
                slow_git = f"{type(exc).__name__}: {exc}"
            control("a git listing that does not finish is refused by name, never read as an empty tree",
                    [slow_git[:300]], "TREE_UNLISTABLE", "CHILD_TIMEOUT")
            slow_pids = ([int(line) for line in slow_marker.read_text(encoding="utf-8").split()]
                         if slow_marker.is_file() else [])
            check("and the fixture git really was the program that did not answer",
                  slow_marker.is_file() and len(slow_pids) == 2,
                  f"{masked(slow_marker)}: {slow_pids}")

            def alive(pid):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    return False
                except OSError:                      # it exists and is not ours to signal
                    return True
                return True

            # `tracked_paths` starts its child with a session of its own, so the bound ends the GROUP:
            # the shell and the sleep it backgrounded both go. Asked rather than assumed, with a margin
            # of its own because a just-killed grandchild is reaped by init and not by this process.
            standing = list(slow_pids)
            for _ in range(40):
                standing = [pid for pid in standing if alive(pid)]
                if not standing:
                    break
                time.sleep(0.05)
            check("and neither the fixture git nor the sleep it started outlived the bound",
                  not standing, f"{standing} still standing two seconds after the refusal")

        with section('r4 R3: the same fixture under a parent whose NAME is shell. Unquoted after `>`, the'):
            # ---- r4 R3: the same fixture under a parent whose NAME is shell. Unquoted after `>`, the
            # redirect took the path's first word, so the fixture truncated a file outside scratch. Both
            # the parent and the file the unquoted redirect would have hit are this control's own, inside
            # the suite's disposable scratch: a control for this defect may not name a real path.
            hostile_parent = scratch / "a dir with a space, a ' and a $dollar"
            hostile_parent.mkdir()
            sentinel = scratch / "a"          # the first word of that path, where an unquoted `>` lands
            sentinel.write_text("a sentinel this fixture must leave alone\n", encoding="utf-8")
            hostile_marker = hostile_parent / "slow-git-ran"
            hostile_script, hostile_env = slow_git_script(hostile_marker)
            hostile_bin = scratch / "hostile-git-bin"
            hostile_bin.mkdir()
            (hostile_bin / "git").write_text(hostile_script, encoding="utf-8")
            (hostile_bin / "git").chmod(0o755)
            hostile_tree = scratch / "hostile-git-tree"
            hostile_tree.mkdir()
            (hostile_tree / ".git").write_text("gitdir: a fixture, not a repository\n", encoding="utf-8")
            # Through `tracked_paths`, the same caller the fixture git has above: it bounds the child and
            # ends its group, so the backgrounded sleep is not left standing — and this control adds no
            # dispatch site of its own, which a direct `/bin/sh <scratch path>` would (the trace cannot
            # resolve a scratch path, and an unresolvable program is a refusal by design).
            try:
                tracked_paths(hostile_tree, git_env={"PATH": f"{hostile_bin}:/usr/bin:/bin", **hostile_env},
                              git_timeout=3)
            except Exception:
                pass          # the refusal is the one the control above already names
            check("the fixture git writes its marker inside scratch when its parent's name is shell",
                  hostile_marker.is_file() and len(hostile_marker.read_text(encoding="utf-8").split()) == 2,
                  f"{masked(hostile_marker)}: exists={hostile_marker.is_file()} "
                  f"{sorted(path.name for path in hostile_parent.iterdir())}")
            check("and the file an unquoted redirect would have truncated is untouched",
                  sentinel.read_text(encoding="utf-8") == "a sentinel this fixture must leave alone\n",
                  f"{masked(sentinel)}: {sentinel.read_text(encoding='utf-8')!r}")

        with section('R2#3 and R2#7 for this entry point, in this process. Both used to be asked of a'):
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

        with section('R1#0/R2#0, the differential: for EVERY carrier fixture in this suite, nothing the'):
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
                        # With the provenance `event_carriers` builds, because `transcript` is an
                        # absolute path under the owner's home and `provenance` was a string field the
                        # schema declares that no fixture carried — so the walk could not visit it and
                        # the control was blind to it (r4 R4).
                        "planted native_global": carrier(
                            "native_global", f"{pathlib.Path.home()}/.claude/CLAUDE.md", planted_in["native_global"],
                            provenance={"as_of": "2026-10-28T00:00:00+09:00", "session": "s-a-planted-session",
                                        "transcript": f"{pathlib.Path.home()}/.claude/projects/p/planted.jsonl",
                                        "where": "User", "scope": "user", "reference": "current",
                                        "record": 7, "identity": UNKNOWN_REASONS["codex_identity"],
                                        # a scope answer's unit (S-10): its scope row and its event
                                        "scope_id": scope_id("native_global", "claude", None),
                                        "event_id": opaque_id("e", "event", "native", "claude", "s-a", None, 7),
                                        # a Codex block's git (S-19): every leaf the schema declares is filled
                                        "git": {"commit_hash": "abc1234", "branch": "a-planted-branch",
                                                "repository_url": "https://example.invalid/org/planted.git"}}),
                        # The ledger's own provenance shape (`_ledger`), and the `hosts` list the
                        # deduplication appends: every leaf the schema declares under `provenance` is
                        # filled by some fixture, because the walk is judged LEAF BY LEAF and a
                        # sub-field no fixture carries would pass it unseen (r4 R4 addendum).
                        "a ledger carrier with its own provenance": carrier(
                            "ledger_incubating", f"{LEDGER_REL}#planted-entry",
                            f"## Keys\n\n- the entry reads apiKeyHelper: {secret}\n",
                            item_ref="planted-entry",
                            provenance={"status": "incubating", "keep_units": ["u-0000000000000000"],
                                        "keep_reason": "a planted hold-back reason",
                                        "hosts": ["claude", "codex"]}),
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

            document_count = [0]

            def document_strings(items, reference="current"):
                """Every string in the document THE PRODUCTION PATH publishes for these carriers.

                `emitted_document` is what `reference_of` publishes, and its docstring claimed the
                differential drove it while nothing but `reference_of` did (r4 R4): a control that
                reaches `units_of` + `shed` itself skips `operative_context`, the reference, layer and
                produced-by rows, and the disclosure judgement `write_document` makes before an artifact
                exists. This drives all of it, and then WRITES the document into this suite's scratch
                the way `write_document` would publish it, so the strings judged are the published ones.

                A refusal from `write_document` is returned as a string rather than raised: its message
                is itself a published string, and a differential must be able to see a line that reached
                an artifact's refusal as well as one that reached the artifact."""
                layers, rows = dict.fromkeys(item["layer"] for item in items), []
                for layer in layers:
                    rows.append({"layer": layer, "producer": "this suite's fixture producer",
                                 "status": "complete", "reasons": [],
                                 "carriers": [item for item in items if item["layer"] == layer]})
                ctx = {"home": str(pathlib.Path.home()), "state_root": None, "notes": {},
                       "commit": None, "release_ref": None, "snapshot": {}}
                document, _units = emitted_document(reference, rows, ctx)
                out = scratch / "r4-published-documents"
                out.mkdir(exist_ok=True)
                document_count[0] += 1
                name = out / "inventory" / f"document-{document_count[0]}.json"
                try:
                    write_document(out, name, document, ctx["home"])
                    published = json.loads(name.read_text(encoding="utf-8"))
                except Refused as exc:
                    published = {"write_document_refused": str(exc)}
                return ([(f"document{where}", text) for where, text in strings_in(document)]
                        + [(f"published{where}", text) for where, text in strings_in(published)])

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
            # r4 R4(a): the same property over the PUBLISHED document, one fixture at a time and then
            # all of them in one document, because a document holding several carriers is what a
            # reference point actually publishes and the one-at-a-time shape never exercises the
            # context, reference and layer rows beside each other.
            published_differential = {name: withheld_lines(item, lambda it: document_strings([it]))
                                      for name, item in fixtures.items()}
            control("every carrier fixture, differentially, through the document the production path publishes",
                    [f"fixtures={len(published_differential)} "
                     f"withheld_lines={sum(len(rows[0]) for rows in published_differential.values())} "
                     f"leaks={ {name: rows[1] for name, rows in published_differential.items() if rows[1]} }"],
                    "leaks={}")
            together = document_strings(list(fixtures.values()))
            # One document holds every fixture, so a line is only evidence of a leak while it belongs to
            # ONE of them: a carrier the floor withholds WHOLE withholds its `## Rules` heading too, and
            # another fixture publishes that heading by right. The lines compared here are the ones no
            # other fixture's intact carrier keeps, which is what the per-fixture pass above judges.
            intacts = {name: projection.project(item["text"], projection.CURRENT, str(pathlib.Path.home()))
                       for name, item in fixtures.items()}
            exclusive = sorted({line for name, rows in published_differential.items() for line in rows[0]
                                if not any(line in text for other, text in intacts.items() if other != name)})
            control("and the same for one document carrying every fixture at once",
                    [f"carriers={len(fixtures)} strings={len(together)} exclusive_lines={len(exclusive)} "
                     f"leaks={sorted({where for line in exclusive for where, text in together if line in text})}"],
                    "leaks=[]")
            check("that one document really carried every fixture's strings", len(together) > len(fixtures),
                  f"strings={len(together)} carriers={len(fixtures)}")
            check("and the lines it looked for include every fixture's own planted credential",
                  all(any(secret in line for line in exclusive) for secret in (secret, heading_secret.strip())),
                  f"exclusive={len(exclusive)}")

        with section('r5 F0 (blocking): a reason derived from a carrier carries NO text of the carrier'):
            # ---- r5 F0 (blocking): a reason derived from a carrier carries NO text of the carrier.
            # The parsers' own messages do: tomllib names the duplicated table, and a `SyntaxError` names
            # the identifier it tripped on. Those messages became a layer row's reason and a reference
            # row's reason, which the floor projects as a diagnostic on its own — without the carrier's
            # context — so a carrier the floor withholds WHOLE leaked through its own parse error. The
            # differential could not see it: it compares withheld LINES, and a message echoes a fragment.
            # Each fixture carries its own canary and is searched for as a SUBSTRING of every published
            # string. `leaked_before` records whether the parser's message really would have carried the
            # canary — measured, not assumed, and false for the two parsers that echo nothing.
            malformed_fixtures = {
                "a toml carrier with a duplicated table": (
                    carrier("catalog", "claude/config.toml",
                            'example = \'api\\_key: "alpha\'\n[shortpass-r5-toml-dup]\nx = 1\n'
                            '[shortpass-r5-toml-dup]\ny = 2\n'),
                    "shortpass-r5-toml-dup", "toml", True),
                "a python carrier whose SyntaxError names an identifier": (
                    # The escaped key sits in a COMMENT: in a string literal the carrier's own quote
                    # ends the literal and the parser reports THAT instead of the future import.
                    carrier("catalog", "claude/hooks/broken.py",
                            '# api\\_key: "alpha\nfrom __future__ import shortpass_r5_py\n'),
                    "shortpass_r5_py", "python", True),
                "a toml carrier with a syntax error": (
                    carrier("catalog", "claude/other.toml",
                            'example = \'api\\_key: "alpha\'\nshortpass-r5-toml-bad = = 1\n'),
                    "shortpass-r5-toml-bad", "toml", False),
                "a json carrier with a syntax error": (
                    carrier("catalog", "claude/guides/broken.json",
                            '{"example": "api\\\\_key: \\"alpha", "shortpass-r5-json": }\n'),
                    "shortpass-r5-json", "json", False),
            }

            def parser_message(item, kind):
                """What the parser itself says about this carrier — the string that used to become the
                reason. Called for the premise only; nothing of it is published."""
                try:
                    if kind == "toml":
                        tomllib.loads(item["text"])
                    elif kind == "json":
                        json.loads(item["text"])
                    else:
                        ast.parse(item["text"])
                except Exception as exc:
                    return f"{type(exc).__name__}: {exc}"
                return ""

            for name, (item, canary, kind, leaked_before) in malformed_fixtures.items():
                check(f"{name} is withheld whole by the floor",
                      projection.carrier_decision(item["text"], str(pathlib.Path.home())) == ([], True),
                      f"whole_withheld={projection.carrier_decision(item['text'], str(pathlib.Path.home())) == ([], True)}")
                check(f"{name} really is malformed, so a reason is what the document carries for it",
                      bool(parser_message(item, kind)),
                      f"parser_refused={bool(parser_message(item, kind))}")
                if leaked_before:
                    check(f"{name}: the parser's own message would have carried its canary",
                          canary in parser_message(item, kind),
                          f"old_message_carried_it={canary in parser_message(item, kind)}")
                published_here = document_strings([item])
                control(f"{name}: its canary in no published string",
                        [f"strings={len(published_here)} "
                         f"carrying={len([1 for _where, text in published_here if canary in text])}"],
                        "carrying=0")
                # ...and the reason it carries is the category every parse failure of a supported form is
                # published under, never the parser's exception type (lead, after a36c728): a reason naming
                # one is itself the defect the exception-name scan forbids.
                reason_strings = [text for where, text in published_here if "reason" in where.lower()]
                check(f"{name}: and the document carries its reason as MALFORMED_CARRIER, naming no exception type",
                      any("MALFORMED_CARRIER" in text for text in reason_strings)
                      and not any(exception_named_problems({"reasons": [text]})[0] for text in reason_strings),
                      f"reasons={reason_strings[:4]}")

        with section('r4 R0 (blocking): two VERSIONS of one carrier identity in one reference point. The'):
            # ---- r4 R0 (blocking): two VERSIONS of one carrier identity in one reference point. The
            # identity is `(layer, package_id, item_ref, path)` with no content in it, and
            # `event_carriers` makes one carrier per `(layer, scope)`, so one instruction file recorded
            # in two scopes at two versions is two carriers under one id. The floor's whole-carrier
            # decision was cached by that id alone, so whichever version was decided first answered for
            # both and the withheld version's text was emitted through the other version's extents.
            # BOTH orders, because the defect only showed in one of them.
            r0_secret = "shortpass-r4-r0-control"
            r0_path = f"{pathlib.Path.home()}/.claude/CLAUDE.md"
            r0_harmless = carrier("native_global", r0_path, "## Rules\n\nkeep the tests green\n")
            r0_withheld = carrier("native_global", r0_path,
                                  f'## Rules\n\napi\\_key: "alpha\n\n{r0_secret}\n')
            check("the two versions really are one carrier identity",
                  r0_harmless["carrier_id"] == r0_withheld["carrier_id"],
                  f"{r0_harmless['carrier_id']} {r0_withheld['carrier_id']}")
            check("and the withheld version alone is withheld whole",
                  r0_secret not in str(document_strings([r0_withheld])),
                  "the withheld version's secret reached the document on its own")
            for order, pair_of_versions in (("harmless first", [r0_harmless, r0_withheld]),
                                            ("withheld first", [r0_withheld, r0_harmless])):
                r0_strings = document_strings(pair_of_versions)
                control(f"two versions of one carrier identity, {order}: the withheld version's secret in no published string",
                        [f"carrying={[where for where, text in r0_strings if r0_secret in text]}"],
                        "carrying=[]")
                control(f"and the harmless version's own text is still published, {order}",
                        [f"kept={any('keep the tests green' in text for where, text in r0_strings)}"],
                        "kept=True")
            # r4 R0, the audit beside the decision: every other structure keyed by the carrier id alone.
            # `by_carrier`, `carriers_at_path`, `frontmatter`, the section spans and `whole_carrier` made
            # two versions ONE carrier, so a mention of that path reached both versions' units at once
            # and the ambiguity the design states for two carriers at one path was deduplicated away.
            # The emitted string this changes is the context list itself.
            r0_v1 = carrier("catalog", "claude/guides/two-versions.md", "## Rules\n\n- a rule only v1 carries\n")
            r0_v2 = carrier("catalog", "claude/guides/two-versions.md", "## Rules\n\n- a rule only v2 carries\n")
            r0_ref = carrier("catalog", "claude/guides/mentions-it.md",
                             "## Ref\n\n- read claude/guides/two-versions.md before answering\n")

            def mentioning_context(items):
                found = [unit["operative_context"] for unit in operative_context(units_of(items))
                         if unit["path"].endswith("mentions-it.md") and len(unit["operative_context"]) > 1]
                return found[0] if found else []

            one_version = mentioning_context([r0_v1, r0_ref])
            two_versions = mentioning_context([r0_v1, r0_v2, r0_ref])
            control("two versions of one identity are two carriers at one path, so the context states the ambiguity",
                    [f"one_version_ambiguous={any('ambiguous' in row for row in one_version)} "
                     f"two_versions_ambiguous={any('ambiguous' in row for row in two_versions)}"],
                    "one_version_ambiguous=False two_versions_ambiguous=True")
            check("and both contexts were really resolved, so neither is empty",
                  len(one_version) >= 2 and len(two_versions) > len(one_version),
                  f"one={len(one_version)} two={len(two_versions)}")
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
            #
            # Resolved RECURSIVELY (r4 R4): the first version took only properties whose own `type` is
            # string, so `operative_context` — an array of strings, and the one field a context leak
            # would travel in — was not in the set, and neither was a string leaf under a `$ref` or a
            # nested object. Each leaf is named by the top-level field it sits under, which is what the
            # walk's own locations report.
            schema_here = inventory_schema()

            def string_leaves(spec, seen=()):
                """Every string LEAF under this schema node, each as its path from the node.

                Judged per leaf rather than per top-level field (r4 R4 addendum): "has a string
                somewhere under it" counts `provenance` as covered the moment any one of its five
                strings is walked, so a sub-field no fixture fills — or one added later — passes unseen.
                An array index is normalized to `[]`, which is how the walk's own locations are read
                below, and a `$ref` carries its parent's path."""
                if not isinstance(spec, dict):
                    return []
                ref = spec.get("$ref")
                if ref:
                    name = ref.rsplit("/", 1)[-1]
                    if name in seen:                 # a recursive definition is not a second answer
                        return []
                    return string_leaves(schema_here["$defs"].get(name, {}), seen + (name,))
                declared = spec.get("type")
                if declared == "string" or (isinstance(declared, list) and "string" in declared):
                    return [""]
                found = []
                for key in ("items", "contains"):
                    found += [f"[]{leaf}" for leaf in string_leaves(spec.get(key), seen)]
                for key in ("additionalProperties", "propertyNames"):
                    found += [f".{{}}{leaf}" for leaf in string_leaves(spec.get(key), seen)]
                for branch in ("anyOf", "oneOf", "allOf"):
                    for member in spec.get(branch) or ():
                        found += string_leaves(member, seen)
                for key, member in (spec.get("properties") or {}).items():
                    found += [f".{key}{leaf}" for leaf in string_leaves(member, seen)]
                return found

            declared_strings = sorted({f"{name}{leaf}"
                                       for name, spec in schema_here["$defs"]["unit"]["properties"].items()
                                       for leaf in string_leaves(spec)})
            check("the recursive resolution finds the string leaves a flat one missed",
                  {"operative_context[]", "provenance.transcript", "provenance.session", "layer", "sha"}
                  <= set(declared_strings), f"{declared_strings}")

            def leaf_of(where):
                """The leaf name a walked location reports, from the unit down, with every array index
                normalized to `[]` — the same spelling `string_leaves` returns."""
                after = where.split(".units[", 1)[-1]
                after = after.split("].", 1)[1] if "]." in after else where.split("$.", 1)[-1]
                return re.sub(r"\[\d+\]", "[]", after)

            walked = {leaf_of(where)
                      for _name, item in fixtures.items() for where, _text in emitted_strings(item)}
            # `units_of` + `shed` fills no `operative_context` and no `provenance`: those exist on the
            # PRODUCTION path, which is the second reason the differential had to drive the document
            # builder (r4 R4). The document's own locations name the unit field after `units[n]`.
            for _name, item in fixtures.items():
                for where, _text in document_strings([item]):
                    if ".units[" in where:
                        walked.add(leaf_of(where))
            control("a string field the schema declares that the differential never looks at",
                    [f"declared={declared_strings} walked={sorted(walked)} "
                     f"unwalked={[name for name in declared_strings if name not in walked]}"],
                    "unwalked=[]")
            check("the schema declared string fields to cover at all", len(declared_strings) >= 8,
                  f"{declared_strings}")

            # The same property over `shared/store.json` (step 0 S-21: the differential covers every new
            # document, leaf by leaf). Each fixture is published as the store publishes it — split on its
            # own, emitted through its version's decision, written by `write_document` — and judged on
            # every string of the WRITTEN store, the map keys included.
            store_count = [0]

            def store_strings(items):
                ctx_store = {"home": str(pathlib.Path.home()), "commit": None, "carriers_named": list(items), "events": []}
                out = scratch / "p23-published-stores"
                store_count[0] += 1
                name = out / "inventory" / "shared" / f"store-{store_count[0]}.json"
                try:
                    store_out = store_document(ctx_store)
                    write_document(out, name, store_out, ctx_store["home"])
                    published = json.loads(name.read_text(encoding="utf-8"))
                except Refused as exc:
                    published = {"write_document_refused": str(exc)}
                keys = [(f"published.{section}<key>", key) for section in ("versions", "units")
                        for key in published.get(section) or {}]
                return [(f"published{where}", text) for where, text in strings_in(published)] + keys

            store_differential = {name: withheld_lines(item, lambda it: store_strings([it]))
                                  for name, item in fixtures.items()}
            control("every carrier fixture, differentially, through the store the production path publishes",
                    [f"fixtures={len(store_differential)} "
                     f"withheld_lines={sum(len(rows[0]) for rows in store_differential.values())} "
                     f"leaks={ {name: rows[1] for name, rows in store_differential.items() if rows[1]} }"],
                    "leaks={}")
            store_together = store_strings(list(fixtures.values()))
            control("and the same for one store carrying every fixture at once",
                    [f"carriers={len(fixtures)} strings={len(store_together)} "
                     f"leaks={sorted({where for line in exclusive for where, text in store_together if line in text})}"],
                    "leaks=[]")

            def store_leaf(where):
                """A walked store location as the schema names it: `versions.<id>.<sha>.<field>` is a
                `carrier_version` field and `units.<ref>.<field>` a `carrier_unit` one."""
                parts = re.sub(r"\[\d+\]", "[]", where).split(".")
                if len(parts) >= 5 and parts[1] == "versions":
                    return "carrier_version." + ".".join(parts[4:])
                if len(parts) >= 4 and parts[1] == "units":
                    return "carrier_unit." + ".".join(parts[3:])
                return None

            store_declared = sorted({f"{name}.{field}{leaf}" for name in ("carrier_version", "carrier_unit")
                                     for field, spec in schema_here["$defs"][name]["properties"].items()
                                     for leaf in string_leaves(spec)})
            store_walked = {store_leaf(where) for where, _text in store_together} - {None}
            control("a string field the store's rows declare that the differential never looks at",
                    [f"declared={store_declared} walked={sorted(store_walked)} "
                     f"unwalked={[name for name in store_declared if name not in store_walked]}"],
                    "unwalked=[]")
            check("the store's rows declared string fields to cover at all",
                  {"carrier_unit.text", "carrier_unit.heading", "carrier_version.path", "carrier_version.item_ref"}
                  <= set(store_declared), f"{store_declared}")
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

        with section('r3 S1, the differential over the CONTEXT path: a mention is a string this module'):
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
                # The escape is written as a RAW string in the fixture's own source, so parsing this
                # carrier as Python emits no SyntaxWarning while the text still carries the escape the
                # floor cannot decode — four such warnings came out of this one fixture, on this tree and
                # on every tree since it was written (r4 R8's aside).
                "a withheld python carrier with a mention in a comment": carrier(
                    "catalog", "claude/hooks/withheld.py",
                    'API_KEY = r"alpha\\_bravo"\n# ' + mention_token + '\n'),
                "a withheld carrier of a form the splitter does not read": carrier(
                    "catalog", "claude/guides/withheld.txt",
                    'api\\_key: "alpha"\n' + mention_token + '\n'),
                # A VALID JSON carrier the floor withholds whole. The comment here used to say no valid
                # JSON carrier can be: `projection.carrier_decision` returns the whole-carrier
                # withholding for this text — the same `([], True)` the escaped markdown fixture gets —
                # and `units_of` splits it into a unit, so the claim was false and the one carrier kind
                # with no whole-withheld fixture was JSON (r4 R4).
                "a withheld json carrier whose escaped key spans lines": carrier(
                    "catalog", "claude/guides/withheld-whole.json",
                    '{"keys": "api\\\\_key: \\"alpha\\n\\n' + mention_token + '"}\n'),
            }
            # The mention-shaped SECRET, which is a different shape from the fixtures above: a detached
            # emitter would store the credential itself as the entry.
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
                # The floor's fixed withheld form is the PLACEHOLDER, which is what an entry carries: it
                # is a span of the carrier, not the carrier. `blank_for(the whole text)` quotes the mask
                # when the carrier is valid JSON, and an entry of the JSON fixture this round added is
                # `unknown:<REDACTED>` rather than `unknown:"<REDACTED>"` (r4 R4). Identical to the
                # previous spelling for every other fixture here.
                check(f"{name} emits its unresolved entry from the carrier, withheld",
                      entries and all(projection.blank_for("x") in entry for entry in entries),
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

        with section("GC#8: the closure expands the starting unit's own requirements"):
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

        with section('GC#11: one delivered path, two packages, and the ambiguity is kept'):
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

        with section('GC#12: an ordinary absolute native path does not make publication fail, and does not'):
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

        with section("GC#7: one source selection decides every read of the owner's state, before a byte of"):
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
                left = omission_lines(freeze([(state / "runtime" / "baselines" / "ref1", "baseline")], copy_probe, state))
                control("a copy input reached through a link above the declared root",
                        left, "baseline: symlink")
                check("and nothing from behind that link was copied",
                      not any(path.is_file() for path in copy_probe.rglob("*")),
                      f"{sorted(str(path) for path in copy_probe.rglob('*'))}")

        with section('GC#0 through `--project`: the checkout is protected whatever the caller declares'):
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

        with section("GC#3 by another route: a standalone `--to` is not a way into a run's artifacts"):
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

        with section('GC#10: a real invocation leaves the tree it ran from unchanged — asked of an uncached'):
            # ---- GC#10: a real invocation leaves the tree it ran from unchanged — asked of an uncached
            # COPY of the checkout, by comparing that copy before and after, with the cause asserted
            # separately and a positive control that removes the cause.
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

        with section('R2#5: the owner of "a closure member inside a copy of this checkout". The closure'):
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

            def probe_report(ran):
                """The child, and what it reported."""
                try:
                    return ran, json.loads(ran.stdout.strip().splitlines()[-1])
                except (ValueError, IndexError):
                    return ran, {}

            # The program the child loads is produced HERE, by `copied_member`, and that call is what
            # `runlib/dispatch.py` admits: a closure member inside a tree this process copied, by a name
            # this site declares as a literal (R2#5, r3 #4). One starter, because the floor is no longer
            # loaded by path by anything: the observer that did that is gone.
            def run_the_driver(from_copy, destination, what):
                return probe_report(bounded_child(lambda: subprocess.Popen(
                    [sys.executable, "-I", "-c", BYTECODE_PROBE, str(destination),
                     str(copied_member(from_copy, "session-distill/distill.py"))],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=probe_env,
                    cwd=str(probe), start_new_session=True), what=what))

            def tree_state(root):
                """Every entry under `root`: its name, its contents, and its METADATA — mode, size and
                mtime in nanoseconds.

                A content-only comparison cannot see a chmod, a utime or a truncation that restored the
                same bytes. Directories are entries of their own, so a `__pycache__/` that holds nothing
                still shows, and `lstat` is what is read, so a link is reported as a link rather than
                followed to whatever it points at.

                It cannot see an attempt that FAILED — nothing changes on disk. That is the claim this
                control gave up when the audit-hook observer was removed, stated here rather than left
                for a reader to notice (owner's narrowing, 2026-10-25)."""
                root = pathlib.Path(root)
                state_of = {}
                for path in sorted(root.rglob("*")):
                    relative = path.relative_to(root).as_posix()
                    try:
                        info = path.lstat()
                        metadata = f"mode={info.st_mode:o} size={info.st_size} mtime_ns={info.st_mtime_ns}"
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

            # r7 G4: the link leg below ran over NOTHING. The repository tracks no symlink and
            # `checkout_copy` skips any it meets, so `all(... if is_symlink())` was an empty `all()` —
            # true about no subject, and a revert of the `lstat`/`readlink` branch could not move it.
            # The control makes its own link, before the state is taken, so the subject exists.
            planted_link = copied_checkout / "a-link-only-this-control-makes"
            planted_link.symlink_to("session-distill/distill.py")

            before_tree = tree_state(copied_checkout)

            def differences_between(was, now):
                """Entries created or removed, and entries whose bytes or metadata changed."""
                return sorted(set(was) ^ set(now)) + sorted(
                    name for name in set(was) & set(now) if was[name] != now[name])

            # THE POSITIVE CONTROL COMES FIRST, on a copy of its own: the same run, from a copy whose
            # driver has the one line `sys.dont_write_bytecode = True` taken out, must leave a cache
            # behind — and the comparison below must be what reports it. Without this leg, "the tree is
            # unchanged" is a sentence about an instrument nobody has seen fail. The copy is thrown away
            # afterwards, and the review checkout is never touched.
            unguarded_copy = probe / "unguarded-checkout"
            checkout_copy(unguarded_copy)
            unguarded_driver = unguarded_copy / "session-distill" / "distill.py"
            held_driver = unguarded_driver.read_text(encoding="utf-8")
            unguarded_driver.write_text(held_driver.replace("sys.dont_write_bytecode = True\n", "", 1),
                                        encoding="utf-8")
            check("the positive control really removed the cause, and only it",
                  "sys.dont_write_bytecode = True" not in unguarded_driver.read_text(encoding="utf-8")
                  and len(held_driver) - len(unguarded_driver.read_text(encoding="utf-8")) == len(
                      "sys.dont_write_bytecode = True\n"),
                  "the copy's driver still sets the flag, or more than that line changed")
            before_unguarded = tree_state(unguarded_copy)
            unguarded_run, unguarded_seen = run_the_driver(
                unguarded_copy, probe / "out-positive", "the driver with the no-bytecode line removed")
            unguarded_differences = differences_between(before_unguarded, tree_state(unguarded_copy))
            control("the same run with the cause removed leaves a bytecode cache the comparison reports",
                    [f"code={unguarded_seen.get('code')} differences={unguarded_differences[:8]} "
                     f"stderr={unguarded_run.stderr[-200:]}"], "__pycache__")
            check("and the comparison reports the cache DIRECTORY as an entry of its own, not only the file",
                  "__pycache__" in [name.rsplit("/", 1)[-1] for name in unguarded_differences],
                  f"{unguarded_differences[:8]}")
            check("every difference the positive control saw is inside that copy",
                  all(not name.startswith("/") for name in unguarded_differences)
                  and bool(unguarded_differences), f"{unguarded_differences[:8]}")
            shutil.rmtree(unguarded_copy, ignore_errors=True)

            guarded_run, guarded_seen = run_the_driver(copied_checkout, probe / "out",
                                                       "the real invocation from an uncached copy")
            after_tree = tree_state(copied_checkout)
            check("the real invocation ran the driver as __main__ and produced the inventory",
                  guarded_seen.get("code") == 0 and (probe / "out" / "inventory" / "manifest.json").is_file(),
                  f"{guarded_run.returncode} {guarded_run.stdout[-300:]} {guarded_run.stderr[-400:]}")
            # What is claimed here, and nothing beyond it: the tree this invocation ran from is what it
            # was. A write that was ATTEMPTED and refused leaves nothing on disk, so this does not speak
            # about one — the audit-hook observer that did was wrong twice in the same direction, and
            # both times it reported a clean run (owner's narrowing, 2026-10-25).
            differences = differences_between(before_tree, after_tree)
            control("the real invocation leaves the checkout it ran from exactly as it was",
                    [f"entries={len(before_tree)} differences={differences[:6]}"], "differences=[]")
            check("the comparison carried metadata as well as contents, so a chmod or a utime would show",
                  all("mode=" in value and "mtime_ns=" in value for value in before_tree.values()),
                  f"{sorted(before_tree.items())[:2]}")
            check("and it carries directories as entries of their own, so an empty one would show",
                  any(value.startswith("dir ") for value in before_tree.values()),
                  "no directory is an entry of this comparison")
            linked = {name: value for name, value in before_tree.items()
                      if stat.S_ISLNK((copied_checkout / name).lstat().st_mode)}
            check("there is a link in the copy for that leg to judge", len(linked) == 1
                  and "a-link-only-this-control-makes" in linked,
                  f"{sorted(linked)} — the planted link is the subject, and it is the only one")
            def mode_of(value):
                """The mode `tree_state` recorded in this entry, as an integer."""
                found = re.search(r"\bmode=(\d+)\b", value)
                return int(found.group(1), 8) if found else 0

            # The PREFIX is not this rule's answer: `link:<target> ` comes from `is_symlink()` and
            # `os.readlink`, so it survives `lstat` being reverted to `stat` and the control passed over
            # a link it had followed (r8 G4, shown in a copy: `mode=100644`, a regular file). What the
            # reverted line decides is the METADATA, so the metadata is what is read.
            check("and it reads links without following them",
                  all(value.startswith("link:session-distill/distill.py ") for value in linked.values())
                  and all(stat.S_ISLNK(mode_of(value)) for value in linked.values())
                  and len(before_tree) > 200,
                  f"{sorted(linked.items())} — a link was followed (a mode that is not a link), or the "
                  f"tree was too small to judge")
            check("the comparison had a tree to compare", len(before_tree) > 200,
                  f"{len(before_tree)} entries")

        with section('a selection holds no native layer: each native row of the PUBLISHED selection.json is unkn'):
            # ---- a selection holds no native layer: each native row of the PUBLISHED selection.json is unknown
            # `per_event`, and the pinned session's native events stay published in sessions.json (S-15; lead
            # ruling 5 on the P2.4 plan). The row is made by the one producer the shared selection inventory of
            # the same snapshot is made by, so the two files carry the same rows.
            selection_doc = written_json(planted_out / "inventory" / "selection.json")
            # a layer missing from the document reads as no status, so a check fails by name rather than raising
            selection_rows = collections.defaultdict(lambda: {"status": None, "reasons": None},
                                                     {row["layer"]: row for row in selection_doc.get("layers") or []})
            planted_sessions_doc = written_json(planted_out / "inventory" / f"{SESSIONS}.json")
            check("selection.json's native rows are unknown per_event, and the pinned session's native events stay "
                  "published in sessions.json",
                  all(selection_rows[layer]["status"] == "unknown"
                      and selection_rows[layer]["reasons"] == [f"{layer}: {UNKNOWN_REASONS['per_event']}"]
                      for layer in TRANSCRIPT_LAYERS + ("native_undivided",))
                  and not any(unit["layer"] in TRANSCRIPT_LAYERS for unit in selection_doc["units"])
                  and any(event["owner"] == "claude:session-1" and event["kind"] == "native"
                          for event in planted_sessions_doc["events"]),
                  f"{[(layer, selection_rows[layer]['status'], selection_rows[layer]['reasons']) for layer in TRANSCRIPT_LAYERS]}")
            check("the planted run's selection.json: every row is the pin's evidence or carries a declared reason "
                  "(it published `catalog: KeyError` at a36c728, found by the lead)",
                  bool(selection_doc["layers"]) and not undeclared_rows(selection_doc["layers"]),
                  f"{undeclared_rows(selection_doc['layers'])}")
            # POSITIVE (lead ruling 3, 14:55): with snapshot items in the shape the store writes, the selection catalog
            # path is exercised end to end, so a broken path cannot pass as a declared reason
            check("the planted run's selection.json catalog is complete, with units of its snapshot's item",
                  selection_rows["catalog"]["status"] == "complete" and selection_rows["catalog"]["reasons"] == []
                  and any(unit["layer"] == "catalog" and unit["item_ref"] == "@fixture/core:item-1"
                          for unit in selection_doc["units"]),
                  f"catalog={selection_rows['catalog']['status']} {selection_rows['catalog']['reasons']}")
            planted_shared = {path.name: json.loads(path.read_text(encoding="utf-8"))
                              for path in sorted((planted_out / "inventory" / "shared").glob("selection-*.json"))}
            planted_ref = selection_doc["reference"].get("content_ref")
            own_inventory = planted_shared.get(f"selection-{inventory_id('selection', planted_ref)}.json") or {}
            planted_release_path = planted_out / "inventory" / "shared" / f"release-{inventory_id('release', 'ref1')}.json"
            planted_release = json.loads(planted_release_path.read_text(encoding="utf-8")) if planted_release_path.is_file() else {}
            check("done-when 1, per shared release inventory: the baseline the pinned session's snapshot names maps "
                  "every item to a unit (lead ruling 6 on the P2.4 plan)",
                  planted_release.get("baseline_unmapped") == [] and planted_release.get("baseline_items_expected") == 3
                  and [(row["layer"], row["status"]) for row in planted_release.get("layers") or []]
                  == [(layer, "complete") for layer in SHARED_RELEASE_LAYERS],
                  f"{planted_release.get('baseline_unmapped')} {planted_release.get('baseline_items_expected')} "
                  f"{[(row['layer'], row['status']) for row in planted_release.get('layers') or []]}")
            planted_written = {path.relative_to(planted_out).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in (planted_out / "inventory").rglob("*.json") if path.name != "manifest.json"}
            planted_listed = {row["path"]: row for row in manifest.get("artifacts") or []}
            check("the manifest lists every artifact the run wrote, the shared inventories among them, by its bytes, its "
                  "kind and its id, and not itself (S-22)",
                  {path: row["sha256"] for path, row in planted_listed.items()} == planted_written
                  and any(path.startswith("inventory/shared/selection-i-") for path in planted_written)
                  and any(path.startswith("inventory/shared/release-i-") for path in planted_written)
                  and all((row["id"] is None) == ("-i-" not in path)
                          and (row["id"] is None or path.endswith(f"-{row['id']}.json"))
                          for path, row in planted_listed.items())
                  and "inventory/manifest.json" not in planted_listed,
                  f"written={sorted(planted_written)} listed={sorted(planted_listed)}")
            check("and the shared selection inventory of the same snapshot, from the same producer, carries the same rows",
                  bool(own_inventory) and own_inventory.get("layers") == selection_doc["layers"]
                  and own_inventory.get("ref") == planted_ref
                  and {(row["carrier_id"], row["version_sha256"]) for row in own_inventory.get("carriers") or []}
                  >= {(unit["carrier_id"], unit["version_sha256"]) for unit in selection_doc["units"]}
                  and bool(selection_doc["units"]),
                  f"inventories={sorted(planted_shared)} same={own_inventory.get('layers') == selection_doc['layers']} "
                  f"carriers={len(own_inventory.get('carriers') or [])} units={len(selection_doc['units'])}")
            unpinned_doc = written_json(split_out / "inventory" / "selection.json")
            control("a selection reference point with no pin to name a session",
                    [f"{row['layer']}={row['status']}: " + "; ".join(row["reasons"])
                     for row in unpinned_doc["layers"] if row["layer"] in TRANSCRIPT_LAYERS],
                    "native_global=unknown", "what each event recorded")
            control("a ledger layer at a past reference point",
                    [f"{row['layer']}={row['status']}: " + "; ".join(row["reasons"])
                     for row in unpinned_doc["layers"] if row["layer"] == "ledger_keep"],
                    "ledger_keep=unknown", "no per-session history")

        with section('the refusals `gates/control-audit.py` found no control for (352d35f). Each one is'):
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

        with section("r3 #2: the boundary module's OWN import is inside a boundary. Everything else this"):
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

            # One starter per entry point, each naming its member as a LITERAL and passing a list
            # literal as the child's argv: the member a caller hands in is text the judge cannot read
            # back to a declaration (r3 #4).
            def this_module_with_no_boundary(what):
                """This module's own entry point, which prints its first paragraph and exits 2."""
                return bounded_child(lambda: subprocess.Popen(
                    [sys.executable,
                     str(copied_member(boundary_copy, "session-distill/runlib/inventory.py"))],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=boundary_env,
                    cwd=str(boundary_copy / "session-distill"), start_new_session=True), what=what)

            def driver_with_no_boundary(destination, what):
                """The driver, running the one production command this control uses."""
                return bounded_child(lambda: subprocess.Popen(
                    [sys.executable, str(copied_member(boundary_copy, "session-distill/distill.py")),
                     "inventory", "--to", str(destination), "--no-state"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=boundary_env,
                    cwd=str(boundary_copy / "session-distill"), start_new_session=True), what=what)

            for how, break_it in (("missing", lambda: boundary_entry.unlink()),
                                  ("unreadable", lambda: boundary_entry.chmod(0o000))):
                boundary_entry.write_text("x = 1\n", encoding="utf-8")
                boundary_entry.chmod(0o644)
                break_it()
                for label, start in (
                        ("this module's entry point",
                         lambda how=how: this_module_with_no_boundary(f"the inventory with no boundary ({how})")),
                        ("the driver",
                         lambda how=how: driver_with_no_boundary(scratch / f"boundary-out-{how}",
                                                                 f"the driver with no boundary ({how})"))):
                    # `ran` is this suite's own control register, so the child is NOT bound to it.
                    child = start()
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

        with section('r3 S1: every refusal the emission can state, asked of `emit_row` DIRECTLY with rows'):
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
        with section('the four refusals of `_emit_value` and `emit_row` the S1 block did not ask for'):
            # ---- the four refusals of `_emit_value` and `emit_row` the S1 block did not ask for
            # (lead's control-audit of 8b3b2c4). Each builds its own table and row, and each names a
            # phrase only that refusal carries, so removing the check makes the control fail rather than
            # some neighbour of it. What removal does TODAY is in each comment: these are the silent
            # answers the refusals exist to prevent, not crashes.
            #
            # A str where a list is declared is ITERATED: with the check gone the item rule runs over
            # each character, and a metadata item accepts every one of them, so "ab" would be emitted as
            # ["a", "b"] and no one would see it.
            str_list_table = table_of({"needs": list_of(as_metadata())})
            control("a string where the table declares a list",
                    [str(_raised(lambda: emit_row("probe", str_list_table, {"needs": "ab"},
                                                  dict(emit_place))))],
                    "EMISSION_NOT_DECLARED_VALUE", "where the table declares a list")
            check("and that string really would be emitted item by item with the check gone",
                  [_emit_value(as_metadata(), character, dict(emit_place), "probe.needs[]")
                   for character in "ab"] == ["a", "b"],
                  "the item rule refuses a single character, so the silent case is not what it looks like")
            # A list where a map is declared reaches `.items()`: with the check gone that is an
            # AttributeError, which is a crash in the middle of an emission rather than a named refusal.
            list_map_table = table_of({"paths": map_of(as_metadata(), as_scalar())})
            control("a list where the table declares a map",
                    [str(_raised(lambda: emit_row("probe", list_map_table, {"paths": [["a", 1]]},
                                                  dict(emit_place))))],
                    "EMISSION_NOT_DECLARED_VALUE", "where the table declares a map")
            # A field the SCHEMA declares for this row that the table has no rule for. The subject is
            # read from the schema rather than named here, so a schema that stops declaring it fails the
            # first check instead of leaving the second one vacuous.
            unit_fields = sorted(schema_row_fields("unit"))
            check("the schema declares fields for a row this control can build on", len(unit_fields) > 1,
                  f"{unit_fields}")
            partial_table = table_of({unit_fields[0]: as_metadata()}, schema="unit")
            control("a field the schema declares for this row that no rule of its table names",
                    [str(_raised(lambda: emit_row("unit", partial_table,
                                                  {unit_fields[0]: "a value"}, dict(emit_place))))],
                    "EMISSION_UNDECLARED", "the schema declares this field for this row")
            # A field the table declares, not optional, that the record does not carry. With the check
            # gone a NULLABLE field emits null silently — the row comes back looking complete and the
            # fact that nothing was ever carried is gone.
            missing_table = table_of({"label": as_metadata(nullable=True)})
            control("a field the table declares that the record does not carry",
                    [str(_raised(lambda: emit_row("probe", missing_table, {}, dict(emit_place))))],
                    "EMISSION_UNDECLARED", "the record does not carry it")
            check("and that field really would be emitted as null with the check gone",
                  _emit_value(as_metadata(nullable=True), None, dict(emit_place), "probe.label") is None,
                  "a nullable metadata field refuses None, so the silent case is not what it looks like")

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
                decided = _decision_for(where, "c-" + "0" * 24, record.get("carrier_text"))
                where.update(unit=record, decision=decided)
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

        with section('P2.5: segments per owner, and the instant-only placement (step 0 S-17, S-5)'):
            # ---- P2.5: segments per owner, and the instant-only placement (step 0 S-17, S-5)
            # One main transcript holds a main owner and an inline sidechain `a1`, each with native and
            # injection events, a re-injected native file, an owner-less sidechain injection (line 7), an
            # undecodable line (8), and a sidechain `a2` that records no event (line 10, R2). The expected segments are written out by hand below, never derived from
            # `segments` (rulings-2 S-12: a recompute-equals-runtime control cannot see a bug both share).
            seg_body = "# Segments\n\n- the selected body\n"
            seg_records = [
                {"type": "user", "timestamp": "2026-10-21T08:59:00+00:00"},
                inj("2026-10-21T09:00:00+00:00", [member("User", "/w/g.md", "- g one\n")], cwd="/w/seg"),
                prompt_record("2026-10-21T09:01:00+00:00", [seg_body]),
                inj("2026-10-21T09:02:00+00:00", [member("User", "/w/g.md", "- side\n")], cwd="/w/seg",
                    isSidechain=True, agentId="a1"),
                prompt_record("2026-10-21T09:03:00+00:00", [seg_body], isSidechain=True, agentId="a1"),
                inj("2026-10-21T09:10:00+00:00", [member("User", "/w/g.md", "- g two\n")], cwd="/w/seg"),
                prompt_record("2026-10-21T09:11:00+00:00", [seg_body], isSidechain=True),
                b"not a json line",
                {"type": "user", "timestamp": "2026-10-21T09:20:00+00:00"},
                {"type": "user", "timestamp": "2026-10-21T09:21:00+00:00", "isSidechain": True, "agentId": "a2"}]
            seg_run = published_run("segments", [
                ("claude", "s-seg", seg_records, {}),
                ("codex", "c-seg", [block_meta("c-seg", "2026-10-21T09:00:00+00:00", "# Block\n\n- at seg\n", "/w/seg")],
                 {})], pin="claude:s-seg", snapshot={"content_ref": "5" * 64, "output": {"instruction_text": seg_body}})
            check("the segments run was published, its documents crossing clean", "refused" not in seg_run,
                  f"{seg_run.get('refused')} {(seg_run.get('problems') or [])[:2]}")
            seg_sessions = seg_run.get("sessions") or {"sessions": [], "events": [], "segments": []}

            def lanes_of(sessions_in, session):
                """Per owner display, its segments as `(from, to, native, injection)`, each kind as
                `(state, the line of the event it names, reason, cut line)`: what S-17 publishes, read back."""
                line_of = {row["event_id"]: row["line"] for row in sessions_in.get("events") or []}
                record = next((row for row in sessions_in.get("sessions") or [] if row["session"] == session), {})
                names = {row["owner_ref"]: row["display"] for row in record.get("owners") or []}
                out = {}
                for row in sessions_in.get("segments") or []:
                    if row["session_ref"] == record.get("session_ref"):
                        kinds = tuple((state["state"], line_of.get(state["event_ref"]), state["reason"], state["line"])
                                      for state in (row["in_force"]["native"], row["in_force"]["session_injection"]))
                        out.setdefault(names.get(row["owner_ref"], "?"), []).append((row["from"], row["to"]) + kinds)
                return {name: sorted(rows) for name, rows in out.items()}

            not_yet = ("no_event_yet", None, "no_event_yet", None)

            def held(line):
                return ("in_force", line, None, None)

            def past_cut(line, why, cut):
                return ("uncertain", line, why, cut)

            seg_lanes = lanes_of(seg_sessions, "claude:s-seg")
            main_lane, side_lane = seg_lanes.get("claude:s-seg") or [], seg_lanes.get("claude:s-seg#sidechain:a1") or []
            check("S-17: each owner's segments partition its transcript at its own event lines and certainty cuts, "
                  "each kind's state as written out by hand",
                  seg_lanes == {
                      "claude:s-seg": [(1, 2, not_yet, not_yet), (2, 3, held(2), not_yet), (3, 6, held(2), held(3)),
                                       (6, 8, held(6), held(3)),
                                       (8, 11, past_cut(6, "undecodable_after", 8), past_cut(3, "undecodable_after", 8))],
                      "claude:s-seg#sidechain:a1": [
                          (1, 4, not_yet, not_yet), (4, 5, held(4), not_yet), (5, 7, held(4), held(5)),
                          (7, 8, held(4), past_cut(5, "ownership_unknown", 7)),
                          (8, 11, past_cut(4, "undecodable_after", 8), past_cut(5, "ownership_unknown", 7))],
                      "claude:s-seg#sidechain:a2": [(1, 11, not_yet, not_yet)]},
                  f"{seg_lanes}")
            check("R2: an owner that records no event still has its segment, every kind no_event_yet over the whole "
                  "transcript",
                  seg_lanes.get("claude:s-seg#sidechain:a2") == [(1, 11, not_yet, not_yet)],
                  f"{seg_lanes.get('claude:s-seg#sidechain:a2')}")
            check("S-17: before an owner's first event of a kind, that kind is no_event_yet",
                  bool(main_lane) and bool(side_lane) and main_lane[0][2:] == (not_yet, not_yet)
                  and side_lane[0][2:] == (not_yet, not_yet) and main_lane[1][3] == not_yet,
                  f"{main_lane[:2]} / {side_lane[:1]}")
            check("S-5: past an undecodable line every owner's kinds in force are uncertain by undecodable_after, "
                  "the line named",
                  bool(main_lane) and main_lane[-1][2][2:] == ("undecodable_after", 8) == main_lane[-1][3][2:]
                  and bool(side_lane) and side_lane[-1][2][2:] == ("undecodable_after", 8),
                  f"{main_lane[-1:]} / {side_lane[-1:]}")
            check("S-5: an owner-less sidechain injection cuts the identified sidechain's injection, never the main "
                  "owner's",
                  any(row[:2] == (7, 8) and row[3] == past_cut(5, "ownership_unknown", 7) for row in side_lane)
                  and bool(main_lane) and all(row[0] != 7 for row in main_lane),
                  f"{side_lane} / {main_lane}")
            reinjected = [row for row in seg_sessions["events"] if row["owner"] == "claude:s-seg" and row["kind"] == "native"]
            check("a re-injected native file gives two events and two segment boundaries, each event its own bytes",
                  [row["line"] for row in reinjected] == [2, 6]
                  and len({tuple((member["carrier_id"], member["version_sha256"]) for member in row["members"])
                           for row in reinjected}) == 2
                  and {2, 6} <= {row[0] for row in main_lane}, f"{[row['line'] for row in reinjected]}")
            codex_lane = lanes_of(seg_sessions, "codex:c-seg").get("codex:c-seg") or []
            seg_plain = published_run("segments-unpinned", [("claude", "s-seg", seg_records, {})])
            plain_lanes = lanes_of(seg_plain.get("sessions") or {}, "claude:s-seg")
            check("an injection nobody could look for is unsought by the session's own reason, never no_event_yet: "
                  "unpinned, and a Codex rollout's id space",
                  "refused" not in seg_plain and bool(plain_lanes) and bool(codex_lane)
                  and all(row[3] == ("unsought", None, "unpinned", None) for rows in plain_lanes.values() for row in rows)
                  and all(row[3] == ("unsought", None, "id_space", None) for row in codex_lane)
                  and codex_lane[0][:3] == (1, 2, held(1)),
                  f"{plain_lanes} / {codex_lane}")
            seg_empty = published_run("segments-empty", [("claude", "s-seg", seg_records, {})], pin="claude:s-seg",
                                      snapshot={"content_ref": "6" * 64, "output": {"instruction_text": ""}})
            empty_lanes = lanes_of(seg_empty.get("sessions") or {}, "claude:s-seg")
            check("a pinned session whose own snapshot body is empty has its injection unsought by "
                  "injection_body_empty, in every segment",
                  "refused" not in seg_empty and bool(empty_lanes)
                  and all(row[3] == ("unsought", None, "injection_body_empty", None)
                          for rows in empty_lanes.values() for row in rows),
                  f"{seg_empty.get('refused')} {empty_lanes}")
            covered = []
            for event in seg_sessions["events"]:
                naming = sorted((row["from"], row["to"]) for row in seg_sessions["segments"]
                                if row["in_force"][event["kind"]]["event_ref"] == event["event_id"])
                if event["owner_ref"] is not None:
                    covered.append(bool(naming) and naming[0][0] == event["interval_from"]
                                   and naming[-1][1] == event["interval_to"]
                                   and all(left[1] == right[0] for left, right in zip(naming, naming[1:])))
            check("every per-event reference point is recoverable: the segments naming an event cover exactly its "
                  "interval, with no gap",
                  len(covered) >= 6 and all(covered), f"{len(covered)} {covered}")
            clean("the published segments cross clean, and the sessions document validates against its own root",
                  segment_cross_problems(seg_sessions, {row["event_id"]: [row] for row in seg_sessions["events"]})
                  + document_contract_problems(seg_sessions))

            def planted_segments(change):
                """`segment_cross_problems` of a deep copy of the published segments after `change`."""
                copy_here = json.loads(json.dumps(seg_sessions))
                change(copy_here)
                return segment_cross_problems(copy_here, {row["event_id"]: [row] for row in copy_here["events"]})

            main_rows = [row for row in seg_sessions["segments"] if row["owner_ref"] == owner_ref("claude", "s-seg")]
            side_ref = owner_ref("claude", "s-seg", "a1")
            side_native = next((row["event_id"] for row in seg_sessions["events"]
                                if row["owner_ref"] == side_ref and row["kind"] == "native"), None)
            first_native = next((row["event_id"] for row in reinjected), None)

            def drop_segment(doc):
                gone = next(row for row in doc["segments"] if row["segment_id"] == main_rows[2]["segment_id"])
                doc["segments"].remove(gone)
                for record in doc["sessions"]:
                    record["segment_refs"] = [ref for ref in record["segment_refs"] if ref != gone["segment_id"]]

            def widen(doc):
                next(row for row in doc["segments"] if row["segment_id"] == main_rows[2]["segment_id"])["from"] -= 1

            def name_state(field, value, at=3):
                def change(doc):
                    next(row for row in doc["segments"]
                         if row["segment_id"] == main_rows[at]["segment_id"])["in_force"]["native"][field] = value
                return change

            def dangle(doc):
                doc["sessions"][0]["segment_refs"].append(opaque_id("g", "segment", "nobody", 1))

            def unlist(doc):
                doc["sessions"][0]["segment_refs"] = doc["sessions"][0]["segment_refs"][1:]

            planted_cases = (("a gap", drop_segment, "CROSS_SEGMENT_PARTITION"),
                             ("an overlap", widen, "CROSS_SEGMENT_PARTITION"),
                             ("a segment naming another owner's event", name_state("event_ref", side_native),
                              "CROSS_SEGMENT_EVENT"),
                             ("a segment naming an event whose interval does not cover it",
                              name_state("event_ref", first_native), "CROSS_SEGMENT_EVENT"),
                             ("a dangling segment reference", dangle, "CROSS_SEGMENT_UNRESOLVED"),
                             ("a segment its session does not list", unlist, "CROSS_SEGMENT_UNLISTED"))
            for what, change, code in planted_cases:
                found_here = planted_segments(change) if len(main_rows) == 5 and side_native and first_native else []
                check(f"S-21: {what} is refused by {code}", any(row.startswith(code) for row in found_here),
                      f"{found_here}")
            bad_id = json.loads(json.dumps(seg_sessions))
            if bad_id["segments"]:
                bad_id["segments"][0]["segment_id"] = "x-" + "0" * 24
            check("a segment id of another form is refused by the schema",
                  bool(seg_sessions["segments"]) and any("DOCUMENT_INVALID" in row
                                                         for row in document_contract_problems(bad_id)),
                  "the schema admitted a segment id that is not g-")

            # S-5's instant-only placement, on events built here: one owner, line order authoritative.
            def placed(lines_at, **cut):
                rows = []
                for n, at in lines_at:
                    rows.append({"kind": "native", "owner_ref": "o-x", "n": n, "at": at, "id": f"e-{n}",
                                 "at_reason": instant_reason(at), "interval": None, "certain_to": None,
                                 "uncertain_reason": None})
                for here, after in zip(rows, rows[1:] + [None]):
                    here["interval"] = [here["n"], after["n"] if after else 99]
                for n, (to, why) in cut.items():
                    next(row for row in rows if row["n"] == int(n[1:])).update(certain_to=to, uncertain_reason=why)
                return rows

            ordered = placed([(1, "2026-10-21T09:00:00+00:00"), (5, "2026-10-21T10:00:00+00:00")])
            half_past = "2026-10-21T09:30:00+00:00"
            check("S-5: an instant between two events selects the earlier one, by identity, given as an offset ISO "
                  "string and as a number (POSITIVE)",
                  [event_at_instant(ordered, when, "o-x")["event_ref"]
                   for when in ("2026-10-21T18:30:00+09:00", _instant(half_past).timestamp())] == ["e-1", "e-1"]
                  and event_at_instant(ordered, "2026-10-21T10:30:00+00:00", "o-x")["event_ref"] == "e-5",
                  f"{[event_at_instant(ordered, when, 'o-x') for when in (half_past, '2026-10-21T10:30:00+00:00')]}")
            check("S-5: an instant before every event of a fully ordered list is no_event_yet, and an unsupported one "
                  "has no event",
                  event_at_instant(ordered, "2026-10-21T08:00:00+00:00", "o-x")["state"] == "no_event_yet"
                  and [event_at_instant(ordered, when, "o-x")["state"] for when in (None, "yesterday", True)]
                  == ["none", "none", "none"], "an instant outside the events was answered")
            backwards = placed([(1, "2026-10-21T09:00:00+00:00"), (2, "2026-10-21T10:00:00+00:00"),
                                (3, "2026-10-21T08:00:00+00:00")])
            unsupported = placed([(1, "2026-10-21T09:00:00+00:00"), (2, "2026-10-21T10:00:00+00:00"), (3, "soon")])
            check("S-5: past a backwards step or an unsupported instant the answer is uncertain, naming the line that "
                  "broke the order, never the prefix's last event",
                  [(answer["state"], answer["event_ref"], answer["line"], answer["reason"]) for answer in (
                      event_at_instant(backwards, "2026-10-21T10:30:00+00:00", "o-x"),
                      event_at_instant(backwards, "2026-10-21T07:00:00+00:00", "o-x"),
                      event_at_instant(unsupported, "2026-10-21T10:30:00+00:00", "o-x"))]
                  == [("uncertain", None, 3, None), ("uncertain", None, 3, None), ("uncertain", None, 3, "undated")]
                  and event_at_instant(backwards, half_past, "o-x")["event_ref"] == "e-1",
                  f"{event_at_instant(backwards, '2026-10-21T10:30:00+00:00', 'o-x')}")
            tied = placed([(1, "2026-10-21T09:00:00+00:00"), (2, "2026-10-21T09:00:00+00:00"),
                           (3, "2026-10-21T10:00:00+00:00")])
            check("S-5: of equal instants, the later line is in force", event_at_instant(tied, half_past, "o-x")["event_ref"]
                  == "e-2", f"{event_at_instant(tied, half_past, 'o-x')}")
            ordered_at = [(1, "2026-10-21T09:00:00+00:00"), (5, "2026-10-21T10:00:00+00:00")]
            cut_inside = placed(ordered_at, n1=(3, "undecodable_after"))
            cut_at_end = placed(ordered_at, n1=(5, "undecodable_after"))
            check("S-5: a chosen event past a certainty cut inside its own interval is uncertain by the cut's reason "
                  "and line, and a cut at its interval's end is none",
                  event_at_instant(cut_inside, half_past, "o-x")
                  == {"state": "uncertain", "event_ref": "e-1", "reason": "undecodable_after", "line": 3}
                  and event_at_instant(cut_at_end, half_past, "o-x")["state"] == "in_force",
                  f"{event_at_instant(cut_inside, half_past, 'o-x')} / {event_at_instant(cut_at_end, half_past, 'o-x')}")

        with section("the general control (lead, after a36c728): no reason in ANY document this suite's runs"):
            # ---- the general control (lead, after a36c728): no reason in ANY document this suite's runs
            # published names a Python exception type. Asked last, of every file written under an `inventory/`
            # directory of this suite's scratch, so every run above is its subject; the subject set is counted
            # per document kind, and each kind the module publishes must have been judged.
            published_here = [path for path in sorted(scratch.rglob("*.json"))
                              if "inventory" in path.relative_to(scratch).parts[:-1]]
            named_all, judged_all, kinds_judged = [], 0, collections.Counter()
            for path in published_here:
                try:
                    document_here = json.loads(path.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                if not isinstance(document_here, dict):
                    continue
                problems_here, judged_here = exception_named_problems(document_here, str(path.relative_to(scratch)))
                named_all += problems_here
                judged_all += judged_here
                kinds_judged[str(document_here.get("document") or "manifest")] += 1
            check("no reason in any document this suite's runs published names a Python exception type",
                  not named_all, f"named={len(named_all)} {named_all[:6]}")
            check("and that judged every kind of document the module publishes, with reasons to read",
                  bool(published_here) and set(REFERENCES) | {SESSIONS, STORE, SHARED, "manifest"} <= set(kinds_judged)
                  and judged_all > 100,
                  f"judged={judged_all} kinds={dict(kinds_judged)}")

    # ---- S8b item 6b: a suite collects its failures and prints them at the end, so an exception
    # leaving it took every line with it — which is how r7 recorded D3 and R12 as SILENT when the
    # cause was an abort rather than a silent rule. `entry.publish_collected` is what every abort
    # path now calls; asked here with a planted list, and with this suite's own registration left
    # standing, because that registration is what makes an abort of THIS suite publishable.
    planted = ("a planted suite --self-test", ["a failure an abort must not swallow"])
    boundary.SELF_TEST_COLLECTED.append(planted)
    published = []
    try:
        returned = boundary.publish_collected(published.append)
    finally:
        boundary.SELF_TEST_COLLECTED.remove(planted)
    check("an abort publishes the failures a suite had already collected",
          "a planted suite --self-test [FAIL] a failure an abort must not swallow" in published
          and published == returned,
          f"{published}")
    check("and this suite's own failures are registered while it runs, so its own abort publishes them",
          ("inventory --self-test", failures) in boundary.SELF_TEST_COLLECTED,
          f"{[label for label, _ in boundary.SELF_TEST_COLLECTED]}")
    # The stop-at-a-cap machinery is loaded by production with the standard library alone, which is
    # why its suite imports `entry` lazily rather than at module scope (6b). The property is watched
    # here instead of only kept: a module-level import of anything else fails this.
    stop_body = ast.parse((REPO / "session-distill" / "runlib" / "stop.py").read_text(encoding="utf-8")).body
    stop_imports = sorted({(alias.name if isinstance(node, ast.Import) else (node.module or "")).split(".")[0]
                           for node in stop_body if isinstance(node, (ast.Import, ast.ImportFrom))
                           for alias in node.names})
    check("the stop machinery's module-level imports are the standard library alone",
          bool(stop_imports) and all(name in sys.stdlib_module_names for name in stop_imports),
          f"{[name for name in stop_imports if name not in sys.stdlib_module_names]} of {stop_imports}")
    # r4 R1: this claim used to be read out of the SOURCE — any `except` handler anywhere in a file
    # reaching `publish_collected` satisfied it — so the two handlers that did NOT publish were
    # invisible to it: `distill.main`'s handled-refusal handler, and `guarded`'s `SystemExit`
    # branches, which is the route inventory's own suite aborts through. A control over handlers in
    # the aggregate cannot say which handler ran. Each runner's real handler is now DRIVEN instead:
    # inventory's own route (`main` -> `entry.guarded` -> `entry.failed`) here, and `distill.main`,
    # `dispatch.main_boundary` and `stop.main_boundary` in their own suites.
    def published_on_abort(raiser):
        """`(exit code, what the boundary published)` for one abort through the real `guarded`."""
        planted_row = ("a planted suite --self-test", ["a failure an abort must not swallow"])
        boundary.SELF_TEST_COLLECTED.append(planted_row)
        buffer = io.StringIO()
        try:
            code = boundary.guarded(raiser, stream=buffer)
        finally:
            boundary.SELF_TEST_COLLECTED.remove(planted_row)
        return code, buffer.getvalue()

    def _throw(exc):
        raise exc

    for kind, raiser in (("SystemExit carrying an int", lambda: sys.exit(3)),
                         ("SystemExit carrying a message", lambda: sys.exit("a usage line")),
                         ("SystemExit carrying None", lambda: sys.exit(None)),
                         ("a refusal", lambda: _throw(Refused("a planted refusal"))),
                         ("an unexpected failure", lambda: _throw(RuntimeError("a planted failure")))):
        aborted_code, aborted_out = published_on_abort(raiser)
        control(f"the guarded boundary publishes the collected failures on {kind}",
                [f"published={'a failure an abort must not swallow' in aborted_out} code={aborted_code}"],
                "published=True")
    check("and a normal return through the same boundary publishes nothing",
          published_on_abort(lambda: 0)[1] == "", f"{published_on_abort(lambda: 0)[1][:200]!r}")
    boundary.SELF_TEST_COLLECTED.remove(("inventory --self-test", failures))
    reporting.append("the report begins here")
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
          f"`__main__` against an uncached copy of the checkout leaving that copy unchanged, the cause "
          f"judged in the entry files' own source with a positive control that removes it, a context that "
          f"spans two guides "
          f"and shrinks without its cross-reference, one fragment across two versions with two contexts, the release "
          f"mapping against the baseline file's own item list, every layer status the table can report, the owner's "
          f"state unchanged by a whole inventory beside the write its own entry point makes, an output destination "
          f"overlapping a protected root refused before any write, a planted credential and home path in every "
          f"personal carrier kind masked in every artifact while the hashes still bind to the raw carrier, a "
          f"malformed settings file reported incomplete rather than unsupported, and a failed acquisition that "
          f"still leaves a layer-status artifact)", home=str(pathlib.Path.home()))
    for name, detail in failures:
        # The NAME and the DETAIL are projected separately when the joined line would be withheld
        # whole, so a failing control cannot lose its own name (r4 R8).
        boundary.emit(boundary.failure_text("inventory --self-test", name, detail,
                                            str(pathlib.Path.home())), sys.stdout)
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
