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
import ast
import collections
import contextlib
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

try:
    import tomllib  # the settings reader for a Codex config.toml (3.11+)
except ModuleNotFoundError:  # pragma: no cover - the pinned interpreter has it
    tomllib = None

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from runlib import projection, records
from runlib.records import Refused

HERE = pathlib.Path(__file__).resolve().parents[1]  # session-distill/
REPO = HERE.parent
DESIGN = "design/session-distill/2026-10-20T1942--9684f05--mechanism-design.md"
RECORD = "design/session-distill/2026-10-22T1949--2c1235a--inventory-layers-and-producers.md"
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
# fragment, so the version of the floor that made it has to travel with it (RECORD, design §5.4).
EMISSION_FIELDS = ("redaction_version",)

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
        raise Unsupported(f"{path}: {type(exc).__name__}: {exc}") from exc
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


def carrier(layer, path, text, item_ref=None, package_id=None, form=None):
    """One carrier. `form` is declared when the text is a member of the file the path names rather
    than the file itself — the session's compiled instruction text is markdown that lives inside an
    `output.json`, and reading its structure off the path's suffix made it a malformed settings
    file (GA#5)."""
    return {"layer": layer, "path": path, "item_ref": item_ref, "package_id": package_id,
            "text": text, "version_sha256": sha256_text(text), "form": form or form_of(path)}


def units_of(carriers):
    """Every carrier's units, each with its enclosing headings. `unit_id` is the carrier and the
    fragment, so one fragment in one carrier keeps its id across reference points; a fragment
    repeated inside a carrier carries its occurrence."""
    units, seen = [], collections.Counter()
    for item in carriers:
        heading_path, enclosing = [], []
        for n, (kind, text) in enumerate(blocks_of(item["path"], item["text"], item.get("form")), 1):
            if kind == "heading":
                level = len(text) - len(text.lstrip("#"))
                heading_path = heading_path[:level - 1] + [text.strip().lstrip("#").strip()]
                enclosing = enclosing[:level - 1]
            key = sha256_text(f"{item['layer']}\0{item['path']}\0{text}")[:16]
            seen[key] += 1
            unit_id = f"u-{key}" if seen[key] == 1 else f"u-{key}-{seen[key]}"
            unit = {"unit_id": unit_id, "layer": item["layer"], "path": item["path"],
                    "heading": " > ".join(heading_path), "n": n, "text": text, "sha": sha256_text(text),
                    "class": classify(kind, heading_path), "operative_context": [],
                    "version_sha256": item["version_sha256"], "redaction_version": projection.CURRENT,
                    "block": kind, "item_ref": item["item_ref"], "package_id": item["package_id"],
                    "enclosing": list(enclosing)}
            if kind == "heading":
                enclosing = enclosing + [unit_id]
            units.append(unit)
    return units


def operative_context(units):
    """Fill every unit's `operative_context`: the requirement set §6.3 asks a read to cover — the
    unit itself, the trigger and exceptions enclosing it (its carrier's frontmatter and the headings
    above it), and the carriers its text names, which is how a context spans two guides. A named
    heading narrows the mention to that heading's units; without one, the mentioned carrier's
    trigger stands for it."""
    by_carrier = collections.defaultdict(list)
    for unit in units:
        by_carrier[unit["path"]].append(unit)
    frontmatter = {path: next((u["unit_id"] for u in rows if u["block"] == "frontmatter"), None)
                   for path, rows in by_carrier.items()}
    basenames = collections.defaultdict(list)
    for path in by_carrier:
        basenames[path.rsplit("/", 1)[-1]].append(path)
    for unit in units:
        context = [unit["unit_id"]]
        own = frontmatter.get(unit["path"])
        if own and own != unit["unit_id"]:
            context.append(own)
        context += unit["enclosing"]
        for match in MENTION.finditer(unit["text"]):
            named, heading = match.group("path"), (match.group("heading") or "").strip()
            targets = [named] if named in by_carrier else basenames.get(named.rsplit("/", 1)[-1], [])
            for target in targets:
                if target == unit["path"]:
                    continue
                if heading:
                    # the capture runs to the end of the phrase ("§ Exceptions says"), so a heading
                    # the mention opens with is the heading it names
                    rows = [u["unit_id"] for u in by_carrier[target]
                            if u["heading"] and heading.lower().startswith(u["heading"].rsplit(" > ", 1)[-1].lower())]
                    context += rows or [u for u in [frontmatter.get(target)] if u]
                elif frontmatter.get(target):
                    context.append(frontmatter[target])
        unit["operative_context"] = list(dict.fromkeys(context))
    return units


def shed(units, home=None):
    """The unit records the artifact carries: §6.1's fields, the plan's two, the floor's version, and
    the carrier metadata the later stages read back (`block`, `item_ref`, `package_id`).

    This is the boundary the raw text does not cross. `sha` and `version_sha256` are the raw
    fragment's and the raw carrier's, taken in `units_of`; `text` is what `projected` returns."""
    records_out = []
    for unit in units:
        emitted = {**{field: unit[field] for field in UNIT_FIELDS},
                   "block": unit["block"], "item_ref": unit["item_ref"], "package_id": unit["package_id"]}
        emitted["text"] = projected(unit["text"], home)
        emitted["redaction_version"] = projection.CURRENT
        records_out.append(emitted)
    return records_out


def renames_against(units, base_units):
    """Units whose fragment carried over from the base reference point in another carrier.

    A fragment is evidence of a rename only when it is a requirement and it names one carrier on
    each side: the boilerplate heading every guide shares matches everywhere and says nothing about
    where a requirement went."""
    def unique_operative(rows):
        carriers = collections.defaultdict(set)
        for unit in rows:
            if unit["class"] == "operative":
                carriers[unit["sha"]].add(unit["path"])
        return {sha: paths.pop() for sha, paths in carriers.items() if len(paths) == 1}

    was, now = unique_operative(base_units), unique_operative(units)
    first = {}
    for unit in base_units:
        first.setdefault(unit["sha"], unit)
    rows = []
    for unit in units:
        if unit["sha"] not in was or unit["sha"] not in now:  # both sides hold it, and only requirements are in either
            continue
        if was[unit["sha"]] != unit["path"]:
            rows.append({"unit_id": unit["unit_id"], "from_unit_id": first[unit["sha"]]["unit_id"],
                         "from_path": was[unit["sha"]], "to_path": unit["path"]})
    return rows


# ---------------------------------------------------------------- frozen copies of the owner's state

SYMLINK_POLICY = ("a symlink is never read and never hashed: it names a file outside the root whose "
                  "ownership this inventory cannot state, and the host adapters refuse one in an "
                  "instruction path for the same reason (compose/instructions_session.py)")


def hash_tree(root):
    """`({relative path: sha256}, omissions)` for every file under `root`.

    The omissions are part of the answer, not a silence: a symlink is skipped by policy and an
    unreadable file is skipped by failure, and a before/after comparison over a set that quietly
    dropped either would say "unchanged" about files it never looked at (GA#3)."""
    root = pathlib.Path(root).expanduser()
    digests, omissions = {}, []
    if not root.is_dir():
        return digests, [{"path": str(root), "reason": "the root is not a directory"}]
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            omissions.append({"path": relative, "reason": "symlink"})
            continue
        if not path.is_file():
            continue
        try:
            digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            omissions.append({"path": relative, "reason": f"unreadable: {exc}"})
    return digests, omissions


def protected_roots(state_root, user_root, native_roots):
    """Every root this inventory reads and must not write into: the owner's state, the authoring
    root, the configured host homes and the project roots."""
    roots = [root for root in (state_root, user_root) if root]
    for group in (native_roots or {}).values():
        roots += list(group.values()) if isinstance(group, dict) else []
    return [pathlib.Path(root).expanduser() for root in roots]


def overlap_problems(destinations, roots, enclosing=True):
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
                problems.append(f"PROTECTED_OVERLAP {destination}: it {'holds' if holds and not inside else 'is inside'} "
                                f"{root}, which this inventory reads; nothing is written")
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
    """Copy each existing `(source, relative)` into `destination` and say what was missing. The
    copies are what the producers read: the store's public methods lock the state root and recover
    pending transactions, and a read of the owner's library may not write to it."""
    destination = pathlib.Path(destination)
    missing = []
    for source, relative in sources:
        source = pathlib.Path(source).expanduser()
        target = destination / relative
        if source.is_dir():
            if not source.exists():
                missing.append(relative)
                continue
            shutil.copytree(source, target, symlinks=False, dirs_exist_ok=True)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
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
        raise Refused(f"PRODUCER_UNAVAILABLE {path}: the catalog producer needs the shipped loader")
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
    if not isinstance(members, dict) or not members:
        return [carrier(layer, item.get("origin", {}).get("source_path") or item["primary_member"],
                        item.get("body") or "", item["ref"], item.get("package_id"))]
    rows = []
    for member, content in sorted(members.items(), key=lambda kv: (kv[0] != item["primary_member"], kv[0])):
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
    items, _inventory, _defaults, baseline_ref = store._effective_items(runtime, user, host=host)
    overlaid = set(user.get("items", {})) | set(user.get("overrides", {}))
    rows = []
    for item in items:
        if item["ref"] in overlaid or str(item.get("package_id", "")).startswith("@local"):
            rows += item_carriers(item, "overlays")
    return rows, baseline_ref, {"personal_items": len(user.get("items", {})),
                                "overrides": len(user.get("overrides", {})),
                                "tombstones": len(user.get("tombstones", {}))}


def memory_slug(project):
    """A host's directory name for a project root: the path with every other character a dash,
    which is the layout `~/.claude/projects/` uses."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(pathlib.Path(project).expanduser().resolve()))


def native_patterns(layer, host, projects):
    """What a native layer reads inside a host home. Memory entries belong to a project, so only
    the projects this run names are read — a host home holds every project the owner ever opened,
    and an inventory that swept them all would be neither reproducible nor this run's library."""
    if layer == "native_project":
        return PROJECT_FILES
    if layer == "native_memory":
        return tuple(f"projects/{memory_slug(project)}/memory/*.md"
                     for project in projects) if NATIVE.get(host, {}).get("memory") else ()
    return NATIVE.get(host, {}).get(layer.split("_", 1)[1], ())


def native_files(layer, roots, projects=()):
    """The files a native layer would read under each root. A home's other contents — a host's
    transcripts above all — are never walked, let alone copied."""
    found = []
    for host, home in sorted(roots.items()):
        home = pathlib.Path(home).expanduser()
        for pattern in native_patterns(layer, host, projects):
            matches = sorted(home.glob(pattern)) if "*" in pattern else [home / pattern]
            for path in matches:
                if path.is_file() and not path.is_symlink():
                    found.append((host, path, path.relative_to(home).as_posix()))
    return found


def freeze_native(frozen, roots, projects=()):
    """Copy only the native files the layers name, and hand back the frozen homes. The owner's
    instruction files and memory entries are read from the copies, like the store's state."""
    copies, sources = {}, []
    for layer in ("native_global", "native_settings", "native_memory", "native_project"):
        for host, path, relative in native_files(layer, roots, projects):
            target = frozen / host / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            copies[host] = frozen / host
            sources.append(path)
    return copies, sources


def native_carriers(layer, roots, projects=()):
    """A native layer from the host homes: the global instruction file, the project instruction
    files, the settings, the memory entries. `roots` are frozen copies, one per host."""
    return [carrier(layer, f"{host}:{relative}", (pathlib.Path(root) / relative).read_text(encoding="utf-8", errors="replace"))
            for host, root in sorted(roots.items())
            for _host, _source, relative in native_files(layer, {host: root}, projects)]


def ledger_carriers(ledger, layer):
    """The ledger layer (§6.1): the incubating principles, and the `keep` records still standing.
    Schema 1 and schema 2 both carry a status and the text; a schema this does not read is the
    layer's own `incomplete` reason, never a silent empty."""
    version = ledger.get("schema")
    if version not in (1, 2):
        raise Refused(f"LEDGER_SCHEMA_UNSUPPORTED schema {version!r}: the inventory reads schema 1 and 2")
    rows = []
    for entry in ledger.get("entries", []):
        text = entry.get("principle") or entry.get("lesson") or ""
        if layer == "ledger_incubating" and str(entry.get("status", "")).startswith("incubating") and text:
            rows.append(carrier(layer, f"{LEDGER_REL}#{entry['id']}", text, entry["id"]))
        if layer == "ledger_keep" and entry.get("keep") and text:
            rows.append(carrier(layer, f"{LEDGER_REL}#{entry['id']}", text, entry["id"]))
    return rows


def baseline_items(state_root, ref):
    """A baseline's own item list — the release reference point's carriers, and the expected set
    done-when 1 judges the mapping against, read from the file rather than from the mapping."""
    path = pathlib.Path(state_root).expanduser() / "runtime" / "baselines" / ref / "inventory.json"
    if not path.is_file():
        raise Refused(f"BASELINE_ABSENT {path}: the release reference point has no baseline inventory")
    document = json.loads(path.read_text(encoding="utf-8"))
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise Refused(f"BASELINE_EMPTY {path}: a baseline inventory with no items judges nothing")
    return items


def read_pin(state_root, host, session_id):
    """A pin, read as a file: the content ref it names is what the snapshot is frozen by."""
    pin_path = pathlib.Path(state_root).expanduser() / "sessions" / "pins" / host / f"{session_id}.json"
    if not pin_path.is_file():
        raise Refused(f"PIN_ABSENT {pin_path}: the selection reference point needs the session's pin")
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    if not isinstance(pin.get("content_ref"), str):
        raise Refused(f"PIN_UNREADABLE {pin_path}: the pin names no content_ref")
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
                         "reasons": [f"{layer}: {type(exc).__name__}: {exc}"]})
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
            "frozen_native": {}, "pin": pin, "ledger": ledger, "notes": {}}


def _catalog_current(ctx):
    return catalog_carriers(ctx["repo"])


def _packages_current(ctx):
    return catalog_carriers(ctx["repo"], layer="adopted_packages", adopted=True)  # read; empty is an answer


def _overlays_current(ctx):
    rows, baseline_ref, counts = overlay_carriers(ctx["repo"], ctx["state_root"], ctx["user_root"])
    ctx["notes"]["installed_baseline_ref"] = baseline_ref
    ctx["notes"]["overlay_counts"] = counts
    return rows


def _native(layer):
    def produce_native(ctx):
        roots = ctx["frozen_native"].get("hosts")
        if not roots:
            return None  # no capture and no live home given: this layer has no record
        return native_carriers(layer, roots, ctx.get("projects", ()))
    return produce_native


def _project_current(ctx):
    roots = ctx["frozen_native"].get("projects")
    if not roots:
        return None  # no project root was named
    return native_carriers("native_project", roots)


def _ledger(layer):
    def produce_ledger(ctx):
        if ctx["ledger"] is None:
            return None  # no ledger was handed in: this layer has no record here
        return ledger_carriers(ctx["ledger"], layer)
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
    ("adopted_packages", {"current": ("checkout catalog, items of an adopted package", _packages_current)}),
    ("overlays", {"current": ("instructions_store._effective_items over frozen copies", _overlays_current),
                  "selection": ("pinned snapshot items of @local packages", _selection_overlays)}),
    ("native_global", {"current": ("host homes: the native global instruction file", _native("native_global"))}),
    ("native_project", {"current": ("project roots: CLAUDE.md and AGENTS.md", _project_current)}),
    ("native_settings", {"current": ("host homes: the native settings file", _native("native_settings"))}),
    ("native_memory", {"current": ("host homes: the memory entries", _native("native_memory"))}),
    # Session-level injection exists per session, so "all layers now" can only mean the injection
    # the session being diagnosed received: with a pin, the snapshot's compiled text answers for
    # `current` too; without one there is nothing to read and the layer is `unknown`.
    ("session_injection", {"current": ("the pinned session's compiled instruction text", _selection_injection),
                           "selection": ("the snapshot's compiled instruction text", _selection_injection)}),
    ("ledger_incubating", {"current": ("the ledger's incubating entries (schema 1 or 2)", _ledger("ledger_incubating"))}),
    ("ledger_keep", {"current": ("the ledger's standing keep records (schema 1 or 2)", _ledger("ledger_keep"))}),
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
        "produced_by": {"module": "session-distill/runlib/inventory.py", "design": DESIGN, "record": RECORD,
                        "state_root": str(ctx["state_root"]) if ctx["state_root"] else None,
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


def verify_unchanged(watched, before, native_before, failing=None):
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
    result["watched_roots"] = {str(root): len(before[str(root)]) for root in watched}
    result["watched_native_files"] = len(native_before)
    beside = f" (raised while {type(failing).__name__}: {failing} was in flight)" if failing else ""
    if native_before != native_after:
        touched = (sorted(set(native_before) ^ set(native_after))
                   or [name for name in native_before if native_before[name] != native_after.get(name)])
        raise Refused(f"STATE_WRITTEN: reading the native layers changed {touched}{beside}")
    if before != after:
        changed = sorted({f"{root}/{name}" for root in before
                          for name in set(before[root]) ^ set(after.get(root, {}))}
                         | {f"{root}/{name}" for root in before for name in set(before[root]) & set(after.get(root, {}))
                            if before[root][name] != after[root][name]})
        raise Refused(f"STATE_WRITTEN: reading the library changed {changed[:4]} ({len(changed)} file(s)); "
                      f"the frozen-copy route is not being taken{beside}")
    return result


def run(repo, state_root, user_root, out_dir, pin=None, native_roots=None, ledger=None, commit=None):
    """Write `inventory/<reference>.json` for every reference point, and return the manifest.

    The owner's state is hashed before and after, and the two hashes are compared here rather than
    claimed in prose: this reads the library through frozen copies, and a difference refuses the
    whole inventory by name (done-when 5)."""
    out_dir = pathlib.Path(out_dir)
    state_root = pathlib.Path(state_root).expanduser() if state_root else None
    user_path = pathlib.Path(user_root).expanduser() if user_root else None
    guarded = protected_roots(state_root, user_path, native_roots)
    overlaps = (overlap_problems([out_dir], guarded)
                + overlap_problems([tempfile.gettempdir()], guarded, enclosing=False))
    if overlaps:
        raise Refused("; ".join(overlaps))
    watched = [root for root in (state_root, user_path) if root is not None and root.is_dir()]
    before, omitted = {}, {}
    for root in watched:
        before[str(root)], omitted[str(root)] = hash_tree(root)
    inputs = {"symlink_policy": SYMLINK_POLICY, "protected_roots": [str(root) for root in guarded],
              "roots": {str(root): {"files": len(before[str(root)]), "omissions": omitted[str(root)]}
                        for root in watched},
              "roots_absent": [str(root) for root in (state_root, user_path)
                               if root is not None and not root.is_dir()]}
    produced, manifest = {}, {"references": {}, "state_root_unchanged": None, "out_dir": str(out_dir),
                              "inputs": inputs}
    native_before = {}
    try:
        with no_bytecode(), tempfile.TemporaryDirectory(prefix="distill-inventory-") as frozen_dir:
            ctx = context_of(repo, state_root, user_root, native_roots or {}, pin, ledger)
            ctx["commit"] = commit
            try:
                freeze_inputs(pathlib.Path(frozen_dir), repo, state_root, user_root, pin, ctx)
            except Exception as exc:  # acquisition is an input, and a missing input is a status
                ctx["acquisition_error"] = (f"INPUT_UNACQUIRED: freezing the inputs failed "
                                            f"({type(exc).__name__}: {exc}), so every layer read from the "
                                            f"owner's state has no record here")
                ctx.setdefault("release_ref", None)
                ctx.setdefault("expected_release_items", [])
            native_before.update({str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in ctx.get("native_sources", []) if path.is_file()})
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
            records.write_json(out_dir, out_dir / "inventory" / f"{reference}.json", document)
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
        manifest.update(verify_unchanged(watched, before, native_before, sys.exc_info()[1]))
    records.write_json(out_dir, out_dir / "inventory" / "manifest.json", manifest)
    return manifest


def freeze_inputs(frozen, repo, state_root, user_root, pin, ctx):
    """Copy what the producers read and point the context at the copies: after this, no producer
    holds a path under the owner's state or home."""
    state, user = frozen / "state", frozen / "user"
    ctx["state_root"], ctx["user_root"] = state, user
    native = {}
    projects = [str(root) for root in (ctx["native_roots"].get("projects") or {}).values()]
    ctx["projects"] = projects
    for key in ("hosts", "projects"):
        roots = ctx["native_roots"].get(key)
        if roots:
            copies, sources = freeze_native(frozen / "native" / key, roots, projects)
            native[key] = copies
            ctx.setdefault("native_sources", []).extend(sources)
    ctx["frozen_native"] = native
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
        record = read_pin(state_root, host, session_id)
        state_sources += [(state_root / "sessions" / "pins" / host / f"{session_id}.json",
                           f"sessions/pins/{host}/{session_id}.json"),
                          (state_root / "sessions" / "snapshots" / record["content_ref"],
                           f"sessions/snapshots/{record['content_ref']}")]
        ctx["pin_record"] = record
    else:
        ctx["notes"]["selection"] = "no pin: the selection reference point has no record (§6.3)"
    if pin is None:
        release_ref = runtime.get("selected_baseline_ref")
        if release_ref:
            ctx["notes"]["release"] = "from the installed state's selected_baseline_ref, there being no pin to name one"
    for ref in sorted({release_ref} - {None}):
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
            freeze([(state_root / "runtime" / "baselines" / release_ref, f"runtime/baselines/{release_ref}")], state)
            ctx["notes"]["release"] = "from the pin's snapshot inputs.baseline_ref"
    ctx["release_ref"] = release_ref
    ctx["expected_release_items"] = baseline_items(state, release_ref) if release_ref else []


def report_lines(manifest):
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
    return lines


# ---------------------------------------------------------------- the contract

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


def record_problems(text=None, rel=RECORD):
    """The dated record of what this package decided: it exists and it names each decision's rule."""
    if text is None:
        path = REPO / rel
        if not path.is_file():
            return [f"RECORD_MISSING {rel}: the decisions of this work package have no record"]
        text = path.read_text(encoding="utf-8")
    return [f"RECORD_SILENT {rel}: it carries no {token}" for token in
            ("operative_context", "unsupported", "--native-live", "frozen", "BASELINE_UNMAPPED", "STATE_WRITTEN")
            if token not in text]


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
    control("a carrier the split would lose bytes of", [str(exc) for exc in [_raised(lambda: blocks_of("blank.py", "\n\n"))]],
            "blank.py", "does not reproduce")

    # ---- done-when 6: the unit record is §6.1's list plus the plan's two fields
    clean("the unit record against design §6.1 and the plan", contract_problems())
    control("a design that names another field", contract_problems(
        "numbered units `{unit_id, layer, path, heading, n, text, operative|reference}`:"), "CONTRACT_MISMATCH unit")
    control("a design whose §6.1 sentence is gone", contract_problems("units are not written here"), "DESIGN_UNREADABLE")
    control("a design document that is not there at all",
            contract_problems(rel="design/session-distill/no-such-design.md"), "DESIGN_MISSING")
    clean("the record of this package's decisions", record_problems())
    control("no record of this package at all", record_problems(rel="design/session-distill/no-such-record.md"),
            "RECORD_MISSING")
    text = (REPO / RECORD).read_text(encoding="utf-8") if (REPO / RECORD).is_file() else ""
    for token in ("operative_context", "unsupported", "BASELINE_UNMAPPED"):
        control(f"the record silent about {token}", record_problems(text.replace(token, "it")), "RECORD_SILENT", token)

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
          [row["from_path"] for row in renames] == ["claude/guides/first.md"], f"{renames}")
    check("a heading every carrier shares is no rename",
          not [row for row in renames_against(units_of([guide("third.md", "## Rule\n\n")]), older)], "a reference unit was read as a rename")
    shared = units_of([guide("first.md", f"## Rule\n\n{fragment}"), guide("second.md", f"## Rule\n\n{fragment}")])
    check("a requirement two carriers already shared is no rename",
          not renames_against(units_of([guide("third.md", f"## Rule\n\n{fragment}")]), shared),
          "a fragment that named two carriers on the base side was read as a rename")

    with tempfile.TemporaryDirectory(prefix="wp07-self-test-") as td:
        scratch = pathlib.Path(td)

        # ---- done-when 1: the release mapping, against the baseline file's own item list
        baseline = {"schema_version": 1, "packages": [{"package_id": "@fixture/core"}], "items": [
            {"ref": f"@fixture/core:item-{n}", "item_id": f"item-{n}", "kind": "guide", "package_id": "@fixture/core",
             "primary_member": f"guides/item-{n}.md", "members": {f"guides/item-{n}.md": f"## Item {n}\n\n- a rule\n"},
             "origin": {"source_path": f"claude/guides/item-{n}.md"}, "body": "- a rule\n"} for n in (1, 2, 3)]}
        state = scratch / "state"
        (state / "runtime" / "baselines" / "ref1").mkdir(parents=True)
        (state / "runtime" / "baselines" / "ref1" / "inventory.json").write_text(json.dumps(baseline), encoding="utf-8")
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

        # ---- done-when 2: every layer answers, and the answers are the ones the fixture plants
        fixture_home = scratch / "home" / "claude"
        (fixture_home / "projects" / memory_slug(scratch / "project") / "memory").mkdir(parents=True)
        (fixture_home / "CLAUDE.md").write_text("# Global\n\n- a native rule\n", encoding="utf-8")
        (fixture_home / "settings.json").write_text('{\n "hooks": {}\n}\n', encoding="utf-8")
        (fixture_home / "projects" / memory_slug(scratch / "project") / "memory" / "one.md").write_text(
            "---\nname: one\n---\n\n- a remembered fact\n", encoding="utf-8")
        (scratch / "project").mkdir(exist_ok=True)
        (scratch / "project" / "CLAUDE.md").write_text("# Project\n\n- a project rule\n", encoding="utf-8")
        native = {"claude": fixture_home}
        for layer, expected in (("native_global", 1), ("native_settings", 1), ("native_memory", 1)):
            rows = native_carriers(layer, native, [str(scratch / "project")])
            check(f"{layer} reads its carrier", len(rows) == expected, f"{len(rows)} carrier(s)")
        check("native_memory reads only the projects this run names",
              not native_carriers("native_memory", native, []), "a memory entry was read with no project named")
        ledger = {"schema": 1, "entries": [
            {"id": "S-1", "status": "incubating", "lesson": "- an incubating principle\n"},
            {"id": "S-2", "status": "placed", "lesson": "- a placed one\n", "keep": {"units": ["u"]}},
            {"id": "S-3", "status": "placed", "lesson": "- no keep\n"}]}
        check("the ledger's incubating layer", len(ledger_carriers(ledger, "ledger_incubating")) == 1, "not one carrier")
        check("the ledger's keep layer", len(ledger_carriers(ledger, "ledger_keep")) == 1, "not one carrier")
        control("a ledger schema the inventory does not read",
                [str(_raised(lambda: ledger_carriers({"schema": 9, "entries": []}, "ledger_keep")))],
                "LEDGER_SCHEMA_UNSUPPORTED")
        planted = {
            "complete": lambda ctx: [guide("first.md", first)],
            "empty": lambda ctx: [],
            "unsupported": lambda ctx: [carrier("catalog", "broken.py", "def f(:\n  pass\n")],
            "no-units": lambda ctx: [carrier("catalog", "hollow.md", "")],
            "raising": lambda ctx: (_ for _ in ()).throw(Refused("INPUT_UNREADABLE hollow: planted")),
            "unknown": lambda ctx: None,
        }
        want = {"complete": ("complete", False), "empty": ("complete", True), "unsupported": ("unsupported", False),
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
        manifest = run(REPO, state, user, scratch / "out", native_roots={"hosts": native, "projects": {"project": scratch / "project"}},
                       ledger=ledger, commit="fixture")
        check("the frozen route left the owner's state untouched", manifest["state_root_unchanged"] and hash_tree(state)[0] == before,
              "the state root changed while the inventory read it")
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
        kept = (fixture_home / "CLAUDE.md").read_text(encoding="utf-8")

        def rewriting_producer(ctx):
            (fixture_home / "CLAUDE.md").write_text(kept + "- a rule a producer added\n", encoding="utf-8")
            return [guide("first.md", first)]

        try:
            globals()["LAYERS"] = (("catalog", {"current": ("a producer that rewrites a native file", rewriting_producer)}),)
            control("a producer that rewrites the owner's native instruction file", [str(_raised(
                lambda: run(REPO, state, user, scratch / "native-written",
                            native_roots={"hosts": native, "projects": {"project": scratch / "project"}}, ledger=ledger)))],
                "STATE_WRITTEN")
        finally:
            globals()["LAYERS"] = saved
            (fixture_home / "CLAUDE.md").write_text(kept, encoding="utf-8")
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
                                  ("holding the owner's state root", state.parent),
                                  ("inside a configured host home", fixture_home / "out")):
            control(f"an output destination {name} is refused before any write",
                    [str(_raised(lambda destination=destination: run(
                        REPO, state, user, destination,
                        native_roots={"hosts": native, "projects": {"project": scratch / "project"}},
                        ledger=ledger)))],
                    "PROTECTED_OVERLAP")
        check("the refused destination was never written",
              hash_tree(state)[0] == guarded_before and not (state / "out").exists(),
              "a refused run still touched the protected root")

        with no_bytecode():
            inside = sys.dont_write_bytecode
        check("the guard that keeps a path import from caching bytecode is on inside it", inside,
              "dont_write_bytecode was not set inside no_bytecode()")
        check("the guard leaves the interpreter as it found it",
              sys.dont_write_bytecode is False, "dont_write_bytecode stayed on after the guard")
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
        check("the input manifest names every root it read and every protected root",
              set(inputs["roots"]) == {str(state), str(user)} and str(state) in inputs["protected_roots"],
              f"{sorted(inputs['roots'])} / {inputs['protected_roots']}")

        # ---- GA#0: a credential or a home path planted in every personal carrier kind, and in the
        # session's compiled text, reaches no artifact — while the hashes still bind to the raw carrier
        secret = "sk-ant-api03-" + "Ab3" * 14
        private = str(pathlib.Path.home() / "Documents" / "a-directory-of-the-owner-s")
        memory_entry = fixture_home / "projects" / memory_slug(scratch / "project") / "memory" / "one.md"
        planted_in = {
            "native_global": fixture_home / "CLAUDE.md",
            "native_memory": memory_entry,
            "native_project": scratch / "project" / "CLAUDE.md",
        }
        for path in planted_in.values():
            path.write_text(path.read_text(encoding="utf-8")
                            + f"\n- a rule naming {private}, with apiKeyHelper: {secret}\n", encoding="utf-8")
        settings = fixture_home / "settings.json"
        settings.write_text(json.dumps({"hooks": {}, "apiKeyHelper": secret, "projectDir": private}, indent=1) + "\n",
                            encoding="utf-8")
        planted_in["native_settings"] = settings
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
            json.dumps({"schema_version": 1, "content_ref": content_ref}), encoding="utf-8")
        planted_out = scratch / "planted-out"
        manifest = run(REPO, state, user, planted_out, pin="claude:session-1",
                       native_roots={"hosts": native, "projects": {"project": scratch / "project"}},
                       ledger=ledger, commit="fixture")
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
        for layer, path in planted_in.items():
            carried = [unit for units_for in emitted.values() for unit in units_for
                       if unit["layer"] == layer and unit["version_sha256"] == sha256_text(path.read_text(encoding="utf-8"))]
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
