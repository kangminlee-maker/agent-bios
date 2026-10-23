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

from runlib import projection, records, sources
from runlib.records import Refused

HERE = pathlib.Path(__file__).resolve().parents[1]  # session-distill/
REPO = HERE.parent
DESIGN = "design/session-distill/2026-10-20T1942--9684f05--mechanism-design.md"
LEDGER_REL = "design/session-distill/ledger.json"
REFERENCES = ("current", "release", "selection")
STATUSES = ("complete", "incomplete", "unsupported", "unknown")

# §6.1's unit record, with the two fields the plan adds. `class` carries §6.1's `operative|reference`;
# `contract_problems` holds this tuple against the design's own sentence.
DESIGN_CLASS_FIELD = "operative|reference"
UNIT_FIELDS = ("unit_id", "layer", "path", "heading", "n", "text", "sha", "class",
               "operative_context", "version_sha256", "redaction_version")
PLAN_FIELDS = ("operative_context", "version_sha256")
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
BYTECODE_PROBE = """
import json, os, sys, pathlib
writes = []


def hook(event, args):
    if event != 'open' or len(args) < 2:
        return
    mode = args[1]
    flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
    # A .pyc is written through os.open, whose audit args carry no mode string at all: a mode-only
    # test observed nothing and called it proof.
    writing = (isinstance(mode, str) and any(f in mode for f in 'wax+')) or (
        mode is None and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND)))
    if writing:
        writes.append(str(args[0]))


sys.addaudithook(hook)
if len(sys.argv) > 4 and sys.argv[3] == 'unguarded':
    import importlib.util
    sys.dont_write_bytecode = False
    spec = importlib.util.spec_from_file_location('probe_floor', sys.argv[4])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    code = 0
else:
    sys.path.insert(0, sys.argv[1])
    import distill
    code = distill.main(['inventory', '--to', sys.argv[2], '--no-state'])
print(json.dumps({'code': code,
                  'bytecode': sorted({w for w in writes if w.endswith('.pyc') or '__pycache__' in w})[:4]}))
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
    credential-named member inside `Members`. The code here is the refusal, not the rule."""
    return [f"DISCLOSED_IN_ARTIFACT {row}" for row in
            projection.document_disclosures(document, home, at)]


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
    """The canonical identity of a carrier: its package, the item that supplied it, and the path it
    is delivered at.

    The path alone is not an identity. `item_carriers` rewrites every package's member into the
    tree position it is delivered at, so two packages' `guides/review.md` both become
    `claude/guides/review.md`; keying a unit on the path alone made one package's fragment the
    other's, and made an occurrence number depend on which items the run happened to enumerate
    (GA#2)."""
    return f"{layer}\0{package_id or '-'}\0{item_ref or '-'}\0{path}"


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
        heading_path, enclosing, before = [], [], ""
        for n, (kind, text) in enumerate(blocks_of(item["path"], item["text"], item.get("form")), 1):
            if kind == "heading":
                level = len(text) - len(text.lstrip("#"))
                heading_path = heading_path[:level - 1] + [text.strip().lstrip("#").strip()]
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
                    # The last lines of the carrier BEFORE this block, so the projection sees a
                    # credential's key even when the splitter put the key and its value in two
                    # blocks: projecting a span on its own lost that relationship (GC#4).
                    "context_prefix": "\n".join([line for line in before.split("\n") if line.strip()][-2:])}
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
        """What this unit's text names: resolved unit ids, and `unknown:` for what it does not."""
        unit = by_id[unit_id]
        reached = []
        for match in MENTION.finditer(unit["text"]):
            named, heading = match.group("path"), (match.group("heading") or "").strip()
            paths = [named] if named in carriers_at_path else basenames.get(named.rsplit("/", 1)[-1], [])
            targets = [carrier_id for path in paths for carrier_id in carriers_at_path[path]]
            if not targets:
                if named != unit["path"] and named != unit["path"].rsplit("/", 1)[-1]:
                    reached.append(f"{UNRESOLVED}{named}")
                continue
            if len(targets) > 1:
                # Several packages deliver this path. Every candidate's requirements are in the set
                # AND the ambiguity is stated: choosing the first match is how a context silently
                # became another package's (GB#10).
                reached.append(f"{UNRESOLVED}ambiguous:{named}")
            for carrier_id in targets:
                if heading:
                    rows = [u["unit_id"] for u in by_carrier[carrier_id]
                            if u["heading"] and heading.lower().startswith(u["heading"].rsplit(" > ", 1)[-1].lower())]
                    if rows:
                        reached += rows
                    else:
                        reached.append(f"{UNRESOLVED}{named}#{heading}")
                else:
                    reached += whole_carrier(carrier_id)
        return [row for row in dict.fromkeys(reached) if row != unit_id]

    reached = {unit["unit_id"]: mentioned(unit["unit_id"]) for unit in units}

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


def _projected_span(prefix, text, home=None):
    """A unit's text through the floor, projected together with the carrier lines that precede it.

    The floor reads a credential-named key and the value that follows it as one relationship, and
    the splitter can put the two in different blocks — so projecting a block alone emitted the value
    with nothing to mark it (GC#4). The prefix is projected with the text and then removed again;
    a mask never introduces a line, so when the line count does not come back as expected the
    plain projection stands rather than a guess."""
    if not prefix:
        return projected(text, home)
    drop = prefix.count("\n") + 1
    out = projected(f"{prefix}\n{text}", home)
    lines = out.split("\n")
    if len(lines) >= drop + text.count("\n") + 1:
        return "\n".join(lines[drop:])
    # The context made the floor mask ACROSS the block boundary, and one mask standing for the key
    # and its value cannot be cut back into two. The span is emitted as that mask: cutting the
    # context off and projecting the span alone is exactly what let the value through (GC#4).
    return out


def shed(units, home=None):
    """The unit records the artifact carries: §6.1's fields, the plan's two, the floor's version, and
    the carrier metadata the later stages read back (`block`, `item_ref`, `package_id`).

    This is the boundary the raw text does not cross. `sha` and `version_sha256` are the raw
    fragment's and the raw carrier's, taken in `units_of`; `text` is what `projected` returns."""
    records_out = []
    for unit in units:
        emitted = {**{field: unit[field] for field in UNIT_FIELDS},
                   "block": unit["block"], "item_ref": unit["item_ref"], "package_id": unit["package_id"],
                   "carrier_id": unit["carrier_id"], "provenance": unit["provenance"]}
        emitted["text"] = _projected_span(unit.get("context_prefix") or "", unit["text"], home)
        # `heading` and `path` are carrier text too — a heading line holds whatever its author wrote
        # there, and a package's `origin.source_path` can be an absolute path on the owner's disk.
        emitted["heading"] = projected(unit["heading"], home) if unit["heading"] else unit["heading"]
        emitted["path"] = projected(unit["path"], home)
        emitted["provenance"] = {key: projected(item, home) if isinstance(item, str) else item
                                 for key, item in (unit["provenance"] or {}).items()}
        emitted["redaction_version"] = projection.CURRENT
        records_out.append(emitted)
    return records_out


def renames_against(units, base_units):
    """Units whose fragment carried over from the base reference point in another carrier.

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
            rows.append({"unit_id": unit["unit_id"], "ambiguous": True,
                         "from_carriers": sorted(was_all[sha]), "to_carriers": sorted(now_all[sha]),
                         "reason": "the fragment belongs to more than one carrier on one side, "
                                   "so which carrier it moved from is not decided here"})
            continue
        if was[sha] == now[sha]:
            continue
        # `was[sha]` is a carrier of `base_units` and `first` is built from the same units, so the
        # fragment's source is there by construction.
        source = first[was[sha]][sha]
        rows.append({"unit_id": unit["unit_id"], "from_unit_id": source["unit_id"],
                     "from_carrier_id": was[sha], "to_carrier_id": now[sha],
                     "from_path": source["path"], "to_path": unit["path"],
                     "from_layer": source["layer"], "to_layer": unit["layer"],
                     "moved": [kind for kind, moved in (("path", source["path"] != unit["path"]),
                                                        ("layer", source["layer"] != unit["layer"]),
                                                        ("package", source["package_id"] != unit["package_id"]))
                               if moved] or ["carrier"]})
    return rows


# ---------------------------------------------------------------- frozen copies of the owner's state

SYMLINK_POLICY = ("a symlink is never read and never hashed: it names a file outside the root whose "
                  "ownership this inventory cannot state, and the host adapters refuse one in an "
                  "instruction path for the same reason (compose/instructions_session.py)")


def walk_source(root):
    """`(readable, omitted)` under `root`: the files this inventory may read, and the ones it may
    not, each with the reason.

    One walker decides what is read, what is hashed and what is copied. Two decisions used to
    disagree: the hash reported a symlink as omitted while the copier followed it, so bytes from
    outside the declared root reached a frozen copy that the input manifest said had never been
    read (GB#8). A link is rejected before it is read, leaf and ancestor alike."""
    root = pathlib.Path(root).expanduser()
    readable, omitted = [], []
    if root.is_symlink():
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
    """`({relative path: sha256}, omissions)` over `walk_source`'s readable set.

    The omissions are part of the answer, not a silence: a symlink is skipped by policy and an
    unreadable file is skipped by failure, and a before/after comparison over a set that quietly
    dropped either would say "unchanged" about files it never looked at (GA#3)."""
    readable, omissions = walk_source(root)
    digests = {}
    for relative, path in readable:
        try:
            digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            omissions.append({"path": relative, "reason": f"unreadable: {projected_message(exc)}"})
    return digests, omissions


def protected_roots(state_root, user_root, native_roots, host_homes=()):
    """Every root this inventory must not write into: the owner's state, the authoring root, the
    host homes and the project roots.

    The host homes are protected whether or not this run reads them. A run reads the native layers
    from its own capture, so the homes are not among its inputs — but `~/.claude` is still never a
    place for a run directory, and deriving the protected set from the inputs alone quietly stopped
    protecting them the moment the capture replaced them (GA#4)."""
    roots = [root for root in (state_root, user_root) if root]
    for group in (native_roots or {}).values():
        roots += list(group.values()) if isinstance(group, dict) else []
    roots += list(host_homes)
    return [pathlib.Path(root).expanduser() for root in roots]


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
                problems.append(f"PROTECTED_OVERLAP {masked(destination, home)}: it "
                                f"{'holds' if holds and not inside else 'is inside'} {masked(root, home)}, "
                                f"which this inventory reads; nothing is written")
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


def freeze(sources, destination):
    """Copy each existing `(source, relative)` into `destination` and say what was left out.

    The copies are what the producers read: the store's public methods lock the state root and
    recover pending transactions, and a read of the owner's library may not write to it. Every
    directory is copied through `walk_source`, so the bytes that land here are exactly the bytes
    the input manifest says were read — a link is omitted by name rather than followed (GB#8)."""
    destination = pathlib.Path(destination)
    missing = []
    for source, relative in sources:
        source = pathlib.Path(source).expanduser()
        target = confined(destination, relative)
        if source.is_symlink():
            missing.append(f"{relative}: symlink")
            continue
        if source.is_dir():
            readable, omitted = walk_source(source)
            for inner, path in readable:
                inner_target = confined(target, inner)
                inner_target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    inner_target.write_bytes(path.read_bytes())
                except OSError as exc:
                    missing.append(f"{relative}/{inner}: {projected_message(exc)}")
            missing += [f"{relative}/{row['path']}: {row['reason']}" for row in omitted]
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
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
    base = pathlib.Path(base)
    label = str(relative)
    parts = pathlib.PurePosixPath(label).parts
    if label.startswith("/") or ".." in parts or any(part.startswith("/") for part in parts):
        raise Refused(f"DESTINATION_ESCAPES {label!r}: a copy label is relative and holds no traversal")
    target = pathlib.Path(os.path.normpath(str(base / label)))
    if target != base and not target.is_relative_to(base):
        raise Refused(f"DESTINATION_ESCAPES {label!r}: it resolves outside the frozen destination")
    return target


def temp_home(guarded, home=None):
    """The directory the frozen copies are made under, chosen and judged before anything writes.

    `tempfile.gettempdir()` PROBES its candidates by creating a file in one, so calling it to decide
    whether a destination is allowed is itself the write the decision exists to prevent (GC#1). This
    reads the environment and the platform's fixed candidates and judges them as paths."""
    for candidate in [os.environ.get(name) for name in ("TMPDIR", "TEMP", "TMP")] + ["/tmp", "/var/tmp"]:
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
    document = json.loads(path.read_text(encoding="utf-8"))
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise Refused(f"BASELINE_EMPTY {masked(path)}: a baseline inventory with no items judges nothing")
    return items


def read_pin(state_root, host, session_id):
    """A pin, read as a file: the content ref it names is what the snapshot is frozen by."""
    pin_path = pathlib.Path(state_root).expanduser() / "sessions" / "pins" / host / f"{session_id}.json"
    if not pin_path.is_file():
        raise Refused(f"PIN_ABSENT {masked(pin_path)}: the selection reference point needs the session's pin")
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    if not isinstance(pin.get("content_ref"), str):
        raise Refused(f"PIN_UNREADABLE {masked(pin_path)}: the pin names no content_ref")
    return pin


def snapshot_of(repo, frozen_state, content_ref):
    """A pin's snapshot over the frozen copy, through the store's own `verify_snapshot` — a
    module-level reader that takes no lock and writes nothing, unlike `snapshot_inventory`."""
    root = pathlib.Path(frozen_state) / "sessions" / "snapshots" / content_ref
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
        name, call = producer
        try:
            carriers = call(context)
        except Unacquired as exc:
            rows.append({"layer": layer, "producer": name, "status": "unknown", "carriers": [],
                         "reasons": [f"{layer}: {projection.project(str(exc), projection.CURRENT, context.get('home'))}"]})
            continue
        except Unsupported as exc:
            rows.append({"layer": layer, "producer": name, "status": "unsupported", "carriers": [],
                         "reasons": [f"{layer}: {projection.project(str(exc), projection.CURRENT, context.get('home'))}"]})
            continue
        except Malformed as exc:
            rows.append({"layer": layer, "producer": name, "status": "incomplete", "carriers": [],
                         "reasons": [f"{layer}: {projection.project(str(exc), projection.CURRENT, context.get('home'))}"]})
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


def reference_of(reference, ctx):
    """One reference point: its layers, its units, its completeness and the reasons against it."""
    rows = layer_rows(reference, ctx)
    units = operative_context(produce(rows))
    reasons = [reason for row in rows for reason in row["reasons"]]
    if ctx.get("acquisition_error"):
        reasons = [ctx["acquisition_error"]] + reasons
    kind = {"current": {"kind": "current", "commit": ctx.get("commit")},
            "release": {"kind": "release", "ref": ctx.get("release_ref")},
            "selection": {"kind": "selection", "content_ref": (ctx.get("snapshot") or {}).get("content_ref")}}[reference]
    document = {
        "reference": {**kind, "complete": not reasons, "incomplete_reasons": reasons},
        "produced_by": {"module": "session-distill/runlib/inventory.py", "design": DESIGN,
                        "state_root": masked(ctx["state_root"], ctx.get("home")) if ctx["state_root"] else None,
                        "notes": ctx["notes"]},
        "layers": [{"layer": row["layer"], "producer": row["producer"], "status": row["status"],
                    "units": row["units"], "empty": row["empty"], "reasons": row["reasons"]} for row in rows],
        "units": shed(units, ctx.get("home")),
        "renames": [],
    }
    return document, units


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


def run(repo, state_root, user_root, out_dir, pin=None, native_roots=None, ledger=None, commit=None,
        run_dir=None, zstd=None):
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
    guarded = protected_roots(state_root, user_path, native_roots,
                              host_homes=[spec["home"] for spec in NATIVE.values()])
    home = str(pathlib.Path.home())
    temp_root = temp_home(guarded, home)   # chosen and judged before any write, GC#1
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
                produced[reference][0]["renames"] = renames_against(produced[reference][1], base)
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
    runtime_path = state_root / "runtime" / "state.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8")) if runtime_path.is_file() else {}
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
    ctx["notes"]["frozen_missing"] = freeze(state_sources, state) + [f"user/{name}" for name in freeze(user_sources, user)]
    if pin:
        verified = snapshot_of(repo, state, ctx["pin_record"]["content_ref"])
        release_ref = (verified["inputs"] or {}).get("baseline_ref")
        ctx["snapshot"] = verified
        ctx["notes"]["pin"] = {"host": pin.partition(":")[0], "content_ref": verified["content_ref"],
                               "state": ctx["pin_record"].get("state")}
        if release_ref:
            safe_label("baseline ref", release_ref)
            freeze([(state_root / "runtime" / "baselines" / release_ref, f"runtime/baselines/{release_ref}")], state)
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

# §6.1's own enumeration of the layers, each with the words the design names it by. This is the
# INDEPENDENT statement of the layer set: `LAYERS` is the table the code walks, and a layer deleted
# from it has to fail against something that is not itself (GA#11).
DESIGN_LAYERS = (
    ("catalog", "catalog content"), ("adopted_packages", "adopted"),
    ("overlays", "overlays"), ("native_global", "native global instruction files"),
    ("native_project", "project instruction files"), ("native_settings", "settings"),
    ("native_memory", "memory"), ("session_injection", "session-level injection"),
    ("ledger_incubating", "incubating ledger principles"), ("ledger_keep", "active `keep` records"))


def layer_problems(design_text=None, rel=DESIGN):
    """The layer table against §6.1: the same layers, and each one named in the design's own text."""
    if design_text is None:
        path = REPO / rel
        if not path.is_file():
            return [f"DESIGN_MISSING {rel}: the layer set has no contract to hold"]
        design_text = path.read_text(encoding="utf-8")
    section = design_text.split("### 6.1 Inventory")[-1].split("### 6.2")[0] if "### 6.1 Inventory" in design_text else ""
    if not section.strip():
        return [f"DESIGN_UNREADABLE {rel}: §6.1 is not in this design"]
    problems = []
    declared = [slug for slug, _phrase in DESIGN_LAYERS]
    walked = [layer for layer, _producers in LAYERS]
    for missing in sorted(set(declared) - set(walked)):
        problems.append(f"LAYER_MISSING {missing}: §6.1 names this layer and the table does not walk it")
    for extra in sorted(set(walked) - set(declared)):
        problems.append(f"LAYER_UNDECLARED {extra}: the table walks a layer §6.1 does not name")
    for slug, phrase in DESIGN_LAYERS:
        if phrase.lower() not in section.lower():
            problems.append(f"LAYER_UNNAMED {slug}: §6.1 no longer carries the words {phrase!r}")
    return problems


def contract_problems(design_text=None, rel=DESIGN):
    """Done-when 6: the unit record's required set is §6.1's own list plus the plan's two fields.
    The design's sentence is the authority, parsed from it rather than copied here."""
    if design_text is None:
        path = REPO / rel
        if not path.is_file():
            return [f"DESIGN_MISSING {rel}: the unit record has no contract to hold"]
        design_text = path.read_text(encoding="utf-8")
    match = re.search(r"numbered units\s+`\{(.*?)\}`", design_text, re.S)
    if not match:
        return [f"DESIGN_UNREADABLE {rel}: §6.1's unit record is not in the form `{{...}}`"]
    declared = [field.strip() for field in match.group(1).replace("\n", " ").split(",") if field.strip()]
    expected = tuple(("class" if field == DESIGN_CLASS_FIELD else field) for field in declared) + PLAN_FIELDS + EMISSION_FIELDS
    if tuple(UNIT_FIELDS) != expected:
        return [f"CONTRACT_MISMATCH unit (§6.1 + the plan): the record carries {list(UNIT_FIELDS)}, "
                f"the design and the plan ask for {list(expected)}"]
    return []


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

    # ---- done-when 6: the unit record is §6.1's list plus the plan's two fields
    clean("the unit record against design §6.1 and the plan", contract_problems())
    control("a design that names another field", contract_problems(
        "numbered units `{unit_id, layer, path, heading, n, text, operative|reference}`:"), "CONTRACT_MISMATCH unit")
    control("a design whose §6.1 sentence is gone", contract_problems("units are not written here"), "DESIGN_UNREADABLE")
    control("a design document that is not there at all",
            contract_problems(rel="design/session-distill/no-such-design.md"), "DESIGN_MISSING")
    # ---- GA#11: the layer set, judged against §6.1 rather than against the table that walks it
    clean("the layer table against §6.1's own enumeration", layer_problems())
    saved_layers = globals()["LAYERS"]
    try:
        globals()["LAYERS"] = tuple(row for row in saved_layers if row[0] != "native_memory")
        control("a layer deleted from the table the inventory walks", layer_problems(), "LAYER_MISSING native_memory")
        globals()["LAYERS"] = saved_layers + (("a_layer_nobody_declared", {}),)
        control("a layer the table walks and §6.1 does not name", layer_problems(),
                "LAYER_UNDECLARED a_layer_nobody_declared")
    finally:
        globals()["LAYERS"] = saved_layers
    control("a §6.1 that no longer names one of its layers",
            layer_problems((REPO / DESIGN).read_text(encoding="utf-8").replace("session-level injection", "it")
                           if (REPO / DESIGN).is_file() else ""),
            "LAYER_UNNAMED session_injection")

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
    check("a package's fragment is never another package's unit",
          len({unit["unit_id"] for unit in shared_path}) == len(shared_path)
          and all(unit["package_id"] in unit["carrier_id"] for unit in shared_path),
          "two packages' units aliased at one delivered path")
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

    with tempfile.TemporaryDirectory(prefix="wp07-self-test-") as td:
        scratch = pathlib.Path(td)

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
        control("an output destination inside a host home the native table declares",
                overlap_problems([pathlib.Path(NATIVE["claude"]["home"]).expanduser() / "out"],
                                 protected_roots(None, None, {},
                                                 host_homes=[spec["home"] for spec in NATIVE.values()])),
                "PROTECTED_OVERLAP")
        check("the refused destination was never written",
              hash_tree(state)[0] == guarded_before and not (state / "out").exists(),
              "a refused run still touched the protected root")

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
        control("a short value under a credential-named key",
                disclosure_problems({"api_key": "shortpass"}, str(pathlib.Path.home())),
                "DISCLOSED_IN_ARTIFACT $.api_key", "credential-named member")
        clean("the same member carrying the mask instead",
              disclosure_problems({"api_key": "<REDACTED>"}, str(pathlib.Path.home())))
        # One control here, because the rules and every representation they must read are the
        # floor's own table (`projection.py --self-test`): a nested credential reaches the write
        # boundary and is refused by location, through that one entry point.
        control("a credential nested inside a plain structure reaching the write boundary",
                disclosure_problems({"layers": [{"notes": {"api_key": "shortpass"}}]},
                                    str(pathlib.Path.home())),
                "DISCLOSED_IN_ARTIFACT $.layers[0].notes.api_key", "credential-named member")
        clean("the same structure masked through and through",
              disclosure_problems({"layers": [{"notes": {"api_key": "<REDACTED>"}}]},
                                  str(pathlib.Path.home())))
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
        control("a temporary location inside a protected root",
                [str(_raised(lambda: temp_home([guarded_tmp], str(pathlib.Path.home()))
                             if os.environ.update({"TMPDIR": str(inner_tmp)}) is None else None))],
                "PROTECTED_OVERLAP")
        check("and the refused location was never written to",
              not any(inner_tmp.iterdir()), f"{sorted(path.name for path in inner_tmp.iterdir())}")
        os.environ.pop("TMPDIR", None)
        chosen = temp_home([guarded_tmp], str(pathlib.Path.home()))
        check("the chosen temporary location is a directory outside every protected root",
              chosen.is_dir() and not chosen.is_relative_to(guarded_tmp), f"{masked(chosen)}")
        control("no temporary location outside the protected roots at all",
                [str(_raised(lambda: temp_home([pathlib.Path("/")], str(pathlib.Path.home()))))],
                "PROTECTED_OVERLAP")

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

        # ---- GC#10: the command itself writes no bytecode, observed as attempted writes
        probe = scratch / "bytecode-probe"
        probe.mkdir()
        # The caches this question is about are cleared first: a run that found a valid `.pyc`
        # already there writes none, and a control that passes for that reason judges nothing.
        for cache in list((REPO / "learn").rglob("__pycache__")) + list((REPO / "compose").rglob("__pycache__")):
            shutil.rmtree(cache, ignore_errors=True)
        probe_env = dict(os.environ)
        probe_env.pop("PYTHONPYCACHEPREFIX", None)
        probe_env.pop("PYTHONDONTWRITEBYTECODE", None)
        guarded_run = subprocess.run([sys.executable, "-I", "-c", BYTECODE_PROBE, str(HERE), str(probe / "out")],
                                     capture_output=True, text=True, env=probe_env, cwd=str(probe))
        guarded_seen = json.loads(guarded_run.stdout.strip().splitlines()[-1]) if guarded_run.stdout.strip() else {}
        check("the bytecode probe reached the inventory command",
              guarded_seen.get("code") == 0 and (probe / "out" / "inventory" / "manifest.json").is_file(),
              f"{guarded_run.returncode} {guarded_run.stdout[-200:]} {guarded_run.stderr[-300:]}")
        # The modules this module loads BY PATH are the guard's subject: `learn/redact.py` under the
        # floor, and `compose/` under the catalog and the store. A module the import machinery loads
        # normally is compiled and cached BEFORE any line of the command runs, which is the
        # interpreter's own doing and is what `-B` is for, not something this guard can reach.
        by_path = [name for name in (guarded_seen.get("bytecode") or [])
                   if "/learn/" in name or "/compose/" in name]
        control("the modules the command loads by path write no bytecode beside their source",
                [f"by_path_bytecode={by_path}"], "by_path_bytecode=[]")
        # The positive control loads the same module the floor loads by path, with the guard off and
        # on a COPY — a .pyc lands beside the file it caches, and the repo is not a fixture.
        floor_copy = probe / "floor" / "redact.py"
        floor_copy.parent.mkdir(parents=True, exist_ok=True)
        floor_copy.write_bytes((REPO / "learn" / "redact.py").read_bytes())
        unguarded_run = subprocess.run([sys.executable, "-I", "-c", BYTECODE_PROBE, str(HERE), str(probe / "out2"),
                                        "unguarded", str(floor_copy)],
                                       capture_output=True, text=True, env=probe_env, cwd=str(probe))
        unguarded_seen = json.loads(unguarded_run.stdout.strip().splitlines()[-1]) if unguarded_run.stdout.strip() else {}
        check("the same observation sees a by-path load write bytecode when the guard is off",
              bool(unguarded_seen.get("bytecode")) and any(floor_copy.parent.rglob("*.pyc")),
              f"the positive control observed none: {unguarded_run.stdout[-200:]} "
              f"{sorted(path.name for path in floor_copy.parent.rglob('*'))}")
        check("no bytecode landed anywhere the guarded run could reach",
              not any(probe.rglob("*.pyc")) or all("floor" in str(path) for path in probe.rglob("*.pyc")),
              f"{sorted(masked(path) for path in probe.rglob('*.pyc'))}")

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

    print(f"inventory --self-test: {'OK' if not failures else 'FAILED'} ({len(ran)} controls: the splitter's "
          f"reproduction over the real guides, the unit record against design §6.1, a context that spans two guides "
          f"and shrinks without its cross-reference, one fragment across two versions with two contexts, the release "
          f"mapping against the baseline file's own item list, every layer status the table can report, the owner's "
          f"state unchanged by a whole inventory beside the write its own entry point makes, an output destination "
          f"overlapping a protected root refused before any write, a planted credential and home path in every "
          f"personal carrier kind masked in every artifact while the hashes still bind to the raw carrier, a "
          f"malformed settings file reported incomplete rather than unsupported, and a failed acquisition that "
          f"still leaves a layer-status artifact)")
    for failure in failures:
        print(f"inventory --self-test [FAIL] {failure}")
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
    print(__doc__.strip().split("\n\n")[0])
    return 2


if __name__ == "__main__":
    sys.exit(main())
