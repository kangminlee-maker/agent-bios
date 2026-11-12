#!/usr/bin/env python3
"""Where S11 and S12 are allowed to write, resolved before the first effect (WP-21 commit 1).

Design §10.5 with amendment N#4. Every writer S11 and S12 run resolves its destination from the
environment the run hands it; each destination must be INSIDE the root its class declares in
`run.json.destinations`; and `destinations.resolved.json` records the whole set before the first
`planned` journal record exists. A destination outside its root is `DESTINATION_OUTSIDE_ROOT` and a
required override that is unset is `OVERRIDE_MISSING` — both refusals, both before any effect.

Why an unset override is a refusal even when its fallback looks harmless: a fallback is a path the
run did not declare. `update-state.py` falls back through `pathlib.Path.home()`, which reads HOME
when it is set and the password database when it is not, so the same code that writes into a fixture
in one process writes into the real home of whoever runs it in another. This repository has paid for
that once already (a control exercising a `pw_dir` fallback wrote a run into the owner's home during
a commit hook). The confinement is therefore the declaration, never the fallback.

This module writes nothing except `destinations.resolved.json`, and performs no effect of any kind.
It is the first commit of WP-21 on purpose: the code that confines writes lands before the code that
writes.

    destinations.py --self-test
"""
import ast
import json
import os
import pathlib
import re
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import declare, records, targets, validate  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
REPO = HERE.parent
TABLE_PATH = HERE / "tables" / "destinations.json"
OUTPUT = "destinations.resolved.json"
# The declared classes come from the declaration's own schema, through declare.py, so this module
# cannot disagree with what a run is allowed to declare.
CLASSES = declare.DESTINATIONS
_TABLE = {}


# The states a row can carry that are NOT a certification, named so a reader of the manifest does
# not have to infer them. They sat beside the git isolation and left with it; they belong here,
# with the table they describe.
RELEASE_1_UNINVOKED = "not_invoked_in_release_1"
READ_NOT_WRITTEN = "read_not_written"
RELEASE_1_WHY = ("not invoked by release-1 S11: the apply writes the approved changes into files of "
                 "the declared checkout and executes no git, and names the commit and install "
                 "commands for the owner to run instead of running them (D-20261113-f22b7d, "
                 "narrowing D-20261112-2cf1c4)")


def table():
    """The writer inventory, read once."""
    if not _TABLE:
        _TABLE.update(json.loads(TABLE_PATH.read_text(encoding="utf-8")))
    return _TABLE


def writers():
    return tuple(table()["writers"])


def pairs():
    """Every (writer, override, class) the table declares, in table order."""
    held = []
    for row in writers():
        for entry in row.get("destinations") or ():
            held.append((row.get("writer"), entry.get("override"), entry.get("class")))
    return tuple(held)


def required_overrides():
    """Every environment name some writer's destination depends on, sorted."""
    return tuple(sorted({override for _writer, override, _cls in pairs()}))


def class_of_override():
    """Each override's class, and the overrides two writers place in different classes.

    An environment variable has one value, so a variable two writers read must resolve to one class
    for both; otherwise its single value would have to be inside two roots at once, which is
    satisfiable only by accident. The disagreement is a table defect, reported by name.
    """
    held, conflicts = {}, {}
    for writer, override, cls in pairs():
        if override in held and held[override] != cls:
            conflicts.setdefault(override, {held[override]}).add(cls)
        held.setdefault(override, cls)
    return held, conflicts


def table_problems(root=None):
    """What is wrong with the table itself, by name.

    A writer naming a class the declaration does not hold cannot be confined, and a declared class
    no writer uses is a stale declaration — the same bar the lexicon gate applies to a concept home
    that matches no file.
    """
    problems, rows = [], writers()
    if not rows:
        problems.append("WRITER_SET_EMPTY: a destination manifest over no writer confines nothing")
        return problems
    for row in rows:
        if not row.get("writer"):
            problems.append("WRITER_UNNAMED: a row with no writer")
            continue
        named = [entry.get("class") for entry in row.get("destinations") or ()]
        if row.get("writes_without_override"):
            named.append(row["writes_without_override"])
        if not named:
            problems.append(f"DESTINATION_UNDECLARED {row['writer']}: the row names no class, by "
                            f"override or otherwise")
        for cls in named:
            if cls not in CLASSES:
                problems.append(f"DESTINATION_UNDECLARED {row['writer']}: class {cls!r} is not one "
                                f"of {', '.join(CLASSES)}")
        # A writer may do BOTH, and the real tree settles it: `install.sh` resolves CLAUDE_CONFIG_DIR
        # and CODEX_HOME from the environment while assigning `STATE_DIR` from `$HOME`
        # unconditionally (install.sh:48). The first version of this gate forbade the combination,
        # which would have forced the inventory to misdescribe its largest writer. What must hold is
        # that a fixed root is itself classified and shown where it was derived from.
        if row.get("writes_without_override") and not row.get("writer_unwritten"):
            if row["writes_without_override"] not in CLASSES:
                problems.append(f"FIXED_ROOT_UNCLASSED {row['writer']}: "
                                f"{row['writes_without_override']!r} is not a destination class")
            derived_fixed_here = any(e["writer"] == row["writer"] and e["override"] is None
                                     for e in closure(root))
            if derived_fixed_here and not row.get("fixed_roots"):
                problems.append(f"FIXED_ROOT_UNSHOWN {row['writer']}: the closure derived a "
                                f"HOME-fixed root for this writer and the row shows none of the "
                                f"lines it came from")
        if not row.get("$comment"):
            problems.append(f"WRITER_UNREASONED {row['writer']}: every row carries its own reason")
    _held, conflicts = class_of_override()
    for override, names in sorted(conflicts.items()):
        problems.append(f"OVERRIDE_CLASS_SPLIT {override}: placed in {', '.join(sorted(names))} by "
                        f"different writers, but one variable has one value")
    used = set()
    for row in rows:
        used.update(entry.get("class") for entry in row.get("destinations") or ())
        if row.get("writes_without_override"):
            used.add(row["writes_without_override"])
    for name in CLASSES:
        if name not in used:
            problems.append(f"DESTINATION_CLASS_UNWRITTEN {name}: a declared class no writer writes "
                            f"under is a stale declaration")
    return problems


LAYOUT_DECLARATION = "provenance.json"
LAYOUT_AUTHOR_TREE = "gates"


def install_layout(root=None):
    """`"checkout"`, `"package"`, or None when nothing in the tree declares which.

    It matters because an author-scope writer's SOURCE is not shipped: `fidelity_problems` reads
    every `fallback_source`, so in a packaged install the manifest failed `WRITER_SOURCE_ABSENT`
    over `session-distill/update-state.py` — a refusal no packaged user can act on, and one no check
    run from a clone can see. Found by the WP-21 review.

    Decided by a DECLARED fact, not by an absence. `provenance.json` is written by
    `gates/check-publish.sh --stamp` at `npm prepack`, carries the commit the tarball holds, and is
    removed again after packing, so it exists in a published package and in nothing else. The
    author tree (`gates/`) is the checkout's own declaration. Inferring `package` from a missing
    directory made every incomplete copy of this tree a package — including a fixture that had
    simply not copied everything — and the excuses that ride on the layout (an author-scope writer
    may be absent; its source need not be read) were then granted to a tree nobody had published.
    Neither declaration present, or both, is not guessed at: it is None, and `layout_problems` says
    so by name.
    """
    base = pathlib.Path(root or REPO)
    declared = (base / LAYOUT_DECLARATION).is_file()
    author_side = (base / LAYOUT_AUTHOR_TREE).is_dir()
    if declared and not author_side:
        return "package"
    if author_side and not declared:
        return "checkout"
    return None


def layout_problems(root=None):
    """What stops the layout being established, by name — a refusal, not a default."""
    base = pathlib.Path(root or REPO)
    if install_layout(base) is not None:
        return []
    held = ((base / LAYOUT_DECLARATION).is_file(), (base / LAYOUT_AUTHOR_TREE).is_dir())
    if held == (True, True):
        return [f"LAYOUT_AMBIGUOUS {base}: it carries both a package's {LAYOUT_DECLARATION} and the "
                f"author-side {LAYOUT_AUTHOR_TREE}/, so which excuses apply to an author-scope "
                f"writer cannot be established"]
    return [f"LAYOUT_UNDECLARED {base}: neither a package's {LAYOUT_DECLARATION} nor the "
            f"author-side {LAYOUT_AUTHOR_TREE}/ is here, so this tree does not say which layout it "
            f"is, and the excuses that ride on the layout may not be granted by default"]


def author_rows_absent(root=None):
    """The author-scope rows whose writer is not present in this layout, by writer name.

    In a package these are recorded rather than refused, and their destination is NOT certified: a
    writer that is not installed cannot write, so there is nothing to confine. In a checkout the
    source is required, because that is where the fallback literal is audited.
    """
    base = pathlib.Path(root or REPO)
    return sorted(row["writer"] for row in writers()
                  if row.get("writer_scope") == "author" and not (base / row["writer"]).is_file())


def fidelity_problems(root=None):
    """Where the table's stated fallback is no longer the one its writer carries.

    The fallback is a restatement, tolerated because this makes its drift decidable: the literal must
    still be present in the writer's own source. A row whose source file is gone fails too — the
    inventory would otherwise go on describing a writer that no longer exists.
    """
    problems = []
    base = pathlib.Path(root or REPO)
    for row in writers():
        # An author-scope writer absent from a packaged install is not a fidelity failure: its
        # source is not shipped, and the row's destination is not certified either (see
        # `author_rows_absent`). In a checkout it is required, and absence still fails.
        if (row.get("writer_scope") == "author"
                and install_layout(base) == "package"
                and not (base / row["writer"]).is_file()):
            continue
        source = row.get("fallback_source")
        if source is None:
            if row.get("fallbacks"):
                problems.append(f"FALLBACK_UNSOURCED {row['writer']}: a fallback is stated with no "
                                f"source to hold it against")
            continue
        # Against the install this runs in, not against the author's checkout: a check that reads
        # one tree while judging another cannot see a packaged install at all.
        path = base / source
        if not path.is_file():
            problems.append(f"WRITER_SOURCE_ABSENT {row['writer']}: {source} does not exist")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        carried = {entry["override"] for entry in row.get("destinations") or ()}
        for held in row.get("fallbacks") or ():
            # A fallback for an override the row does not carry is the same error as a certified
            # class for an override the writer does not read: install.sh's fallbacks listed
            # AGENT_BIOS_STATE_DIR, whose literal IS in install.sh — as an unconditional assignment
            # with no override in it — so the literal check passed over it.
            if held["override"] not in carried:
                problems.append(f"FALLBACK_UNPAIRED {row['writer']} {held['override']}: a fallback "
                                f"is stated for an override this row carries no destination for")
                continue
            if held["literal"] not in text:
                problems.append(f"FALLBACK_MOVED {row['writer']} {held['override']}: {source} no "
                                f"longer carries {held['literal']!r}")
    return problems


# ---- the inventory derived from the writers' real closure ---------------------------------------
#
# The first version of this table was written from memory and was incomplete in both directions: it
# lacked nine override variables that shipped writers really read, and it certified
# `AGENT_BIOS_STATE_DIR` for `install.sh`, which assigns `STATE_DIR` from `$HOME` unconditionally and
# never reads that variable at all — a row certifying a value its writer cannot use. Memory is not a
# source. These functions derive the closure from the shipped files themselves, so a writer that
# gains a destination appears here without anyone remembering to add it.

# A destination override is one whose fallback is a PATH. `AGENT_LAUNCH_TUI:-1`,
# `AGENT_BIOS_UPDATE_CHECK:-1` and `AGENT_BIOS_LEGACY_INSTALL` are flags compared to a literal, and a
# flag is not a place anything is written.
_OVERRIDE_NAME = (r"(AGENT_BIOS_[A-Z_]+|AGENT_LAUNCH_[A-Z_]+|XDG_[A-Z_]+|CLAUDE_CONFIG_DIR"
                  r"|CODEX_HOME|ZDOTDIR|HOME)")
# Python: ANY mapping's `.get("OVERRIDE"`, over the whole text rather than line by line. Both
# corrections are findings from the first derivation: it matched only `environ.get(`, so
# `compose/instructions_install.py`'s `self.env.get("CLAUDE_CONFIG_DIR", ...)` — the same read
# through an injected environment — looked like an override the writer does not read; and it scanned
# single lines, so `session-distill/update-state.py`'s three-line `os.environ.get(` was invisible.
# Both false answers pointed the same way, at the table being wrong where it was right.
_PY_OVERRIDE = re.compile(r'\.get\(\s*["\']' + _OVERRIDE_NAME + r'["\']\s*(?:,\s*(?P<fb>(?:[^()]|\([^()]*\))*))?',
                          re.DOTALL)
_PY_SUBSCRIPT = re.compile(r'environ\[\s*["\']' + _OVERRIDE_NAME + r'["\']\s*\]')
_SH_OVERRIDE = re.compile(r'\$\{' + _OVERRIDE_NAME + r':-(?P<fb>[^}]*)\}')
_PATHISH = re.compile(r'(Path\.home\(\)|expanduser|os\.path\.join|\$HOME|\$\{HOME\}|/|\.local|\.config)')
_HOME_ROOT = re.compile(r'(Path\.home\(\)|expanduser\(\s*["\']~|\$HOME|\$\{HOME\})')
_ROOTISH = re.compile(r'(\.local/|\.config/|\.claude|\.codex|\.cache/|\.zsh|/share/|/bin\b)')


def shipped_writers(root=None):
    """Every shipped script the package carries, from `package.json` `files[]`.

    Derived rather than listed: a writer added to the package is scanned without this module being
    told about it, which is the whole point of deriving the inventory.

    `root` is the installation being INSPECTED, which is not always the tree this file sits in. A
    packaged install has no `gates/` and no author-side writers, and with the global `REPO` wired
    in here the derivation read the author's checkout instead — so a real package could not produce
    a manifest at all (round 2). The default stays `REPO`, which is what a checkout run means.
    """
    base = pathlib.Path(root or REPO)
    manifest = json.loads((base / "package.json").read_text(encoding="utf-8"))
    held = [base / rel for rel in sorted(_author_writers()) if (base / rel).is_file()]
    for entry in manifest.get("files") or ():
        path = base / entry
        if path.is_file() and path.suffix in (".py", ".sh", ".zsh"):
            held.append(path)
        elif path.is_dir():
            held += [p for p in sorted(path.rglob("*"))
                     if p.is_file() and p.suffix in (".py", ".sh", ".zsh")]
    return held


def _author_writers():
    """Writers the table declares as author-side, with the paths they live at.

    `session-distill/update-state.py` is one: it writes the nudge state the design's §10.6 names, and
    it is NOT in `package.json` `files[]` — the owner runs it from a checkout. Scanning only the
    shipped set therefore cannot see it, and the first derivation reported its real row as
    certifying an override nobody reads. A writer outside the package is admissible in this table,
    but it must say so, and `inventory_problems` holds the declaration against `files[]` in both
    directions so "author-side" cannot be used to excuse a shipped writer from the derivation.
    """
    return {row["writer"] for row in writers() if row.get("writer_scope") == "author"}


# A path-shaped environment read is not yet a destination: `AGENT_BIOS_PACKAGE_ROOT` names where the
# package is READ from, `AGENT_BIOS_PYTHON_EXECUTABLE` names an interpreter, and the fixture strings
# in `inventory.py`'s own self-test name paths nothing writes. A derivation that cannot tell a read
# from a write produces an inventory whose exemption list is the real table — which is the shape this
# repo refuses everywhere else. So the question asked of each read is whether its value REACHES A
# WRITE in the same file.
_WRITE_CALLS = frozenset((
    "write_text", "write_bytes", "mkdir", "makedirs", "touch", "replace", "rename", "symlink_to",
    "copy", "copy2", "copyfile", "copytree", "move", "unlink", "rmtree", "chmod", "write",
    "writelines", "writestr", "add", "extractall", "dump", "mkstemp", "NamedTemporaryFile",
))
_SH_WRITE = re.compile(
    r'(>>?\s*"?\$|\b(cp|mv|mkdir|install|tee|rm|rmdir|ln|chmod|touch|cat\s*>|tar|printf[^|]*>)\b)')


def _py_destination_reads(text):
    """(override, line) for every env read in this Python source whose value reaches a write.

    Reaching is answered over NAMES, not over a full dataflow: the read's assignment target (a name
    or an attribute like `self.state_root`) must appear somewhere inside a write call's arguments.
    That is deliberately generous — a name used in one write and read in ten still counts — because
    the failure this inventory exists to prevent is a destination nobody declared, and a row too many
    costs a reason while a row too few costs the owner's files.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    reads = []               # (override, line, target-name)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = set()
        for target in targets:
            for part in ast.walk(target):
                if isinstance(part, ast.Name):
                    names.add(part.id)
                elif isinstance(part, ast.Attribute):
                    names.add(part.attr)
        if node.value is None:
            continue
        held = ast.unparse(node.value)
        # A CALL, not a text match. `compose/assemble.py` holds
        # `CLAUDE_VAR = "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"` — a token it rewrites text with, and a
        # regex over the unparsed value read that string as an environment read. A string that
        # mentions an override is not a read of it.
        overrides, home_call = set(), False
        for part in ast.walk(node.value):
            if isinstance(part, ast.Subscript) and isinstance(part.slice, ast.Constant):
                base = part.value
                base_name = (base.attr if isinstance(base, ast.Attribute)
                             else getattr(base, "id", ""))
                if base_name == "environ" and re.fullmatch(_OVERRIDE_NAME, str(part.slice.value) or ""):
                    overrides.add(str(part.slice.value))
            if not isinstance(part, ast.Call):
                continue
            func = part.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name == "get" and part.args:
                # The key can be chosen at runtime: `compose/instructions_understand.py` reads
                # `.get("CODEX_HOME" if host == "codex" else "CLAUDE_CONFIG_DIR", ...)`, which
                # honours BOTH overrides. Reading only a constant key recorded that writer as
                # fixing its root from HOME — the same error as certifying an override nobody reads,
                # pointing the other way.
                asked_nodes = [part.args[0]]
                if isinstance(part.args[0], ast.IfExp):
                    asked_nodes = [part.args[0].body, part.args[0].orelse]
                for node_asked in asked_nodes:
                    if not isinstance(node_asked, ast.Constant):
                        continue
                    asked = str(node_asked.value)
                    if re.fullmatch(_OVERRIDE_NAME, asked) and _PATHISH.search(held):
                        overrides.add(asked)
            if name in ("home", "expanduser"):
                home_call = True
        for asked in overrides:
            for name in names:
                reads.append((asked, node.lineno, name))
        if not overrides and home_call and _ROOTISH.search(held):
            for name in names:
                reads.append((None, node.lineno, name))
    written = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        opens_for_write = (
            name == "open"
            and any(isinstance(a, ast.Constant) and isinstance(a.value, str)
                    and any(mode in a.value for mode in ("w", "a", "x", "+"))
                    for a in list(node.args[1:]) + [k.value for k in node.keywords]))
        if name not in _WRITE_CALLS and not opens_for_write:
            continue
        for part in ast.walk(node):
            if isinstance(part, ast.Name):
                written.add(part.id)
            elif isinstance(part, ast.Attribute):
                written.add(part.attr)
    # One name is not enough. `launch/shell_integration.py` reads ZDOTDIR into `self.zdotdir`, builds
    # `self.startup` from it, and writes THAT — so a rule that asks only whether the read's own
    # target appears in a write call calls a correct row a false certificate. The names form a graph
    # (an assignment is an edge from every name in its value to every target), and the question is
    # whether the read's target reaches a written name through it.
    edges = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        outs = set()
        for target in targets:
            for part in ast.walk(target):
                if isinstance(part, ast.Name):
                    outs.add(part.id)
                elif isinstance(part, ast.Attribute):
                    outs.add(part.attr)
        for part in ast.walk(node.value):
            source = (part.id if isinstance(part, ast.Name)
                      else part.attr if isinstance(part, ast.Attribute) else None)
            if source:
                edges.setdefault(source, set()).update(outs)

    # One hop across a call. `session-distill/update-state.py` reads its override into `STATE` and
    # passes it to a function that writes through `os.replace(temporary, path)` — the write names
    # the PARAMETER, not the module constant, so a graph that stops at function boundaries declares
    # a real destination unwritten. An argument therefore flows to the callee's parameter when the
    # callee is defined in this same module.
    params = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spec = node.args
            params[node.name] = [a.arg for a in
                                 list(spec.posonlyargs) + list(spec.args) + list(spec.kwonlyargs)]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if callee not in params:
            continue
        for index, argument in enumerate(node.args):
            if index >= len(params[callee]):
                break
            for part in ast.walk(argument):
                source = (part.id if isinstance(part, ast.Name)
                          else part.attr if isinstance(part, ast.Attribute) else None)
                if source:
                    edges.setdefault(source, set()).add(params[callee][index])
        for keyword in node.keywords:
            if keyword.arg in params[callee]:
                for part in ast.walk(keyword.value):
                    source = (part.id if isinstance(part, ast.Name)
                              else part.attr if isinstance(part, ast.Attribute) else None)
                    if source:
                        edges.setdefault(source, set()).add(keyword.arg)

    def reaches(name):
        seen, queue = {name}, [name]
        while queue:
            held_name = queue.pop()
            if held_name in written:
                return True
            for nxt in edges.get(held_name, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return False

    return [(override, line) for override, line, name in reads if reaches(name)]


def _sh_destination_reads(text):
    """The same question for a shell script: the variable the read is assigned to must appear in a
    redirection or a writing command's arguments."""
    held, lines = [], text.splitlines()
    assigns = {}             # variable -> (override|None, line)
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assign = re.match(r'(?:local\s+|export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)', stripped)
        if not assign:
            continue
        name, value = assign.group(1), assign.group(2)
        for match in _SH_OVERRIDE.finditer(value):
            if _PATHISH.search(match.group("fb")) or _PATHISH.search(value):
                assigns[name] = (match.group(1), number)
        if name not in assigns and _HOME_ROOT.search(value) and _ROOTISH.search(value):
            assigns[name] = (None, number)
    # Shell carries the same indirection: `install.sh` builds `MANIFEST="$STATE_DIR/manifest.txt"`
    # and writes the manifest. Propagate a root through assignments that mention it, to a fixpoint.
    for _ in range(4):
        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            assign = re.match(r'(?:local\s+|export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)', stripped)
            if not assign or stripped.startswith("#"):
                continue
            name, value = assign.group(1), assign.group(2)
            if name in assigns:
                continue
            for held_name, origin in list(assigns.items()):
                if re.search(r'\$\{?' + re.escape(held_name) + r'\b', value):
                    assigns[name] = origin
                    break
    for number, line in enumerate(lines, 1):
        if line.strip().startswith("#") or not _SH_WRITE.search(line):
            continue
        for name, (override, where) in assigns.items():
            if re.search(r'\$\{?' + re.escape(name) + r'\b', line):
                held.append((override, where))
    return held


_CLOSURE_CACHE = {}


def closure(root=None):
    """The (writer, override) pairs and HOME-fixed roots the shipped tree really carries.

    Each entry is `{writer, override|None, line, text}`. `override=None` means the writer defines a
    destination root from HOME with no variable to redirect it, which is a different obligation: the
    run cannot point that writer anywhere, so the table must say so rather than name an override.
    """
    # Scanning every shipped script costs real time, and `table_problems` asks this question once
    # per row: without a cache the self-test's table mutations re-scan the tree dozens of times.
    # The key is the declared author-side set, the only input a caller can vary in one process.
    base = pathlib.Path(root or REPO)
    key = (str(base), tuple(sorted(_author_writers())))
    if key in _CLOSURE_CACHE:
        return _CLOSURE_CACHE[key]
    held = []
    for path in shipped_writers(base):
        rel = str(path.relative_to(base))
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        reached = (_py_destination_reads(text) if path.suffix == ".py"
                   else _sh_destination_reads(text))
        for override, number in sorted(set(reached), key=lambda h: (h[0] or "", h[1])):
            line = lines[number - 1] if number - 1 < len(lines) else ""
            held.append({"writer": rel, "override": override, "line": number,
                         "text": line.strip()[:160]})
    _CLOSURE_CACHE[key] = held
    return held


def inventory_problems(root=None):
    """Where the table and the derived closure disagree, in both directions.

    `INVENTORY_INCOMPLETE` is a (writer, override) pair the tree carries and the table does not — the
    run would hand that writer an environment it never certified. `INVENTORY_UNWRITTEN` is the
    reverse and the one that actually shipped: a row certifying an override its writer does not read,
    so the certificate is about a value that cannot reach the writer. A pair may be excused only by
    name, in the table's `not_a_destination`, with its own reason.
    """
    base = pathlib.Path(root or REPO)
    table_data = table()
    excused = {(row["writer"], row.get("override")): row.get("reason")
               for row in table_data.get("not_a_destination") or ()}
    declared, fixed = set(), set()
    for row in writers():
        for held in row.get("destinations") or ():
            declared.add((row["writer"], held["override"]))
        if row.get("writes_without_override"):
            fixed.add(row["writer"])
    problems = []
    derived_pairs, derived_fixed = set(), set()
    for entry in closure(base):
        if entry["override"] is None:
            derived_fixed.add(entry["writer"])
            continue
        derived_pairs.add((entry["writer"], entry["override"]))
    for pair in sorted(derived_pairs - declared):
        if pair in excused:
            continue
        problems.append(f"INVENTORY_INCOMPLETE {pair[0]} {pair[1]}: the shipped writer reads this "
                        f"override as a destination and no table row carries the pair")
    forward = {row["writer"] for row in writers() if row.get("writer_unwritten")}
    for writer in sorted(forward):
        if (base / writer).exists():
            problems.append(f"INVENTORY_FORWARD_LANDED {writer}: the row is declared as a writer "
                            f"that does not exist yet, and the file now exists — the declaration "
                            f"must give way to the derived closure")
    # A writer the table declares author-side and this installation does not have writes nothing
    # here, so its pairs are neither certified nor missing: they are NOT INSTALLED, which is what
    # `author_rows_absent` and the resolved row already say. Without this, a real packaged install
    # could not produce a manifest at all — the table's author-scope rows came back as certifying
    # overrides no source reads, and the only source that reads them is the one npm leaves out.
    # Round 2's finding; the fidelity check already made this exclusion and the inventory did not.
    uninstalled = set(author_rows_absent(base))
    for pair in sorted(declared - derived_pairs):
        if pair in excused or pair[0] in forward or pair[0] in uninstalled:
            continue
        problems.append(f"INVENTORY_UNWRITTEN {pair[0]} {pair[1]}: the table certifies a destination "
                        f"class for an override this writer's source never reads, so the class is "
                        f"about a value that cannot reach it")
    # The REVERSE direction for fixed-root rows, which this check did not cover: a row claiming a
    # HOME-fixed root for a writer that is not in this tree at all passed, because every leg here
    # asked about (writer, override) PAIRS and a fixed root has none. A nonexistent writer with
    # `writes_without_override` was certified by `path = root, inside = bool(root)` (the round-2
    # review found both halves).
    for row in writers():
        if not row.get("writes_without_override"):
            continue
        if row.get("writer_unwritten") or row["writer"] in uninstalled or row["writer"] == "git":
            continue
        if not (base / row["writer"]).exists():
            problems.append(f"INVENTORY_FIXED_ROOT_ABSENT {row['writer']}: the row claims a fixed "
                            f"destination root and the writer is not in this tree, is not declared "
                            f"`writer_unwritten` and is not author-side, so the row certifies a "
                            f"class for a file nobody has")
        if row.get("root_from") not in ("home", "argument"):
            problems.append(f"INVENTORY_ROOT_FROM_UNSTATED {row['writer']}: a fixed-root row says "
                            f"whether the run passes the root (`argument`) or the writer derives it "
                            f"from HOME (`home`), because the two are certified differently")
        if row.get("root_from") == "home" and not (row.get("fixed_roots") or ()):
            problems.append(f"INVENTORY_FIXED_ROOT_UNSHOWN {row['writer']}: the row says the root "
                            f"is derived from HOME and shows no source line it is derived at, so "
                            f"there is nothing to compute the destination from")
    for writer in sorted(derived_fixed):
        if any(w == writer for w, _ in declared) or writer in fixed or writer in forward:
            continue
        if writer in uninstalled:
            continue
        if (writer, None) in excused:
            continue
        problems.append(f"INVENTORY_FIXED_ROOT {writer}: the writer derives a destination root from "
                        f"HOME with no override, and the table neither carries the writer nor "
                        f"excuses it — a run cannot point that writer anywhere")
    shipped_rel = {str(p.relative_to(base)) for p in shipped_writers(base)}
    packed = set(json.loads((base / "package.json").read_text(encoding="utf-8")).get("files") or ())
    for writer in sorted(_author_writers()):
        if writer in packed or any(writer.startswith(entry) for entry in packed if entry.endswith("/")):
            problems.append(f"INVENTORY_SCOPE_WRONG {writer}: declared author-side while "
                            f"package.json files[] ships it, so the declaration excuses a writer "
                            f"the derivation can see")
        elif not (base / writer).is_file() and install_layout(base) == "checkout":
            # In a CHECKOUT the file must be there: the declaration says the owner runs it from one.
            # In a package its absence is the layout, not a defect, and `author_rows_absent` is what
            # reports it.
            problems.append(f"INVENTORY_SCOPE_ABSENT {writer}: declared author-side and not present "
                            f"in this tree at all")
    if not shipped_rel:
        problems.append("INVENTORY_NO_WRITERS_SCANNED: package.json files[] yielded no script to "
                        "scan, so every table row would pass unexamined")
    if not derived_pairs:
        problems.append("INVENTORY_DERIVED_EMPTY: the closure found no (writer, override) pair at "
                        "all, so an empty table would satisfy this check")
    return problems


def inside(path, root):
    """Public name for the LEXICAL containment question, so one module answers it.

    Lexical is half the answer and the smaller half. `os.open` follows symlinks, so a path inside
    this root can still open a file outside it; what closes that is the WRITER opening with
    `O_NOFOLLOW` (`journal.Storage.append` does), not a comparison of strings. A caller that cannot
    open with O_NOFOLLOW must check `links_problem` as well.

    `journal.py` asks it of its own file: the journal is `runtime_state`, and a journal written
    outside its declared root is the hole this module exists to close.
    """
    return _inside(path, root)


def links_problem(path, root):
    """A symlink on the way from `root` to `path`, by name, or None.

    For a caller that cannot open with `O_NOFOLLOW`. It walks the parts between the root and the
    path and names the first link it finds, because a link anywhere on the way is enough to put the
    final write outside the root. It answers about the filesystem AS IT IS NOW, so a writer that
    can refuse the follow itself should do that instead: between this check and the open, a link can
    appear.
    """
    path, root = pathlib.Path(path), pathlib.Path(root)
    if not _inside(path, root):
        return f"DESTINATION_OUTSIDE_ROOT {path}: not inside {root}"
    held = root
    for part in path.relative_to(pathlib.PurePosixPath(os.path.normpath(str(root)))).parts:
        held = held / part
        if held.is_symlink():
            return (f"DESTINATION_SYMLINK {held}: a symlink on the way to {path} can put the write "
                    f"outside {root}, and a lexical check cannot see it")
    return None


def _inside(path, root):
    """Whether `path` is the root itself or beneath it, decided on normalized absolute paths.

    No `resolve()`: a symlink is followed by the writer, so the question is what the writer will
    open, and `/var` against `/private/var` has cost this repository a green pretrial and a red hook
    before. Normalizing without resolving keeps the answer the same in both places.
    """
    path = pathlib.PurePosixPath(os.path.normpath(str(path)))
    root = pathlib.PurePosixPath(os.path.normpath(str(root)))
    return path == root or root in path.parents


# ─── The environment a writer is GIVEN ───────────────────────────────────────────────────────────
# The inversion this unit's round-2 review asked for, and the reason it is the right way round:
# DERIVING every override that could redirect a write loses the moment a writer resolves one across
# a module boundary (`environment_value` reads the instructions and corpus aliases in
# `compose/instructions_install.py`, where this module's scanner does not follow), and what is not
# derived is not refused. An override that is ABSENT cannot redirect anything.
#
# So the run hands each writer an environment holding EXACTLY the names the table declares for it,
# with HOME set to what the run declares, and the derivation becomes a DISCLOSURE: what does this
# writer read that it was not given? A non-empty answer withholds certification instead of being
# weighed.
#
# Four channels the environment cannot close, each with its own rule below rather than a hope:
# the password database (a path from `getpwuid` ignores HOME entirely), an absolute literal in the
# source, a login shell that re-reads the user's profile and restores what was scrubbed, and a path
# the writer takes as an ARGUMENT — which is not a hole but the preferred channel, because an
# argument cannot be inherited by anything.
ENVIRONMENT_HOME = ("environment", "home")


def declared_home(declaration):
    """The HOME the run declares for its writers, or None.

    Its own block rather than a destination class: HOME is not a place anything is classified into,
    it is the input from which this writer's fixed roots are computed. Optional in the declaration's
    schema and REQUIRED here, so a lane whose fixtures predate it still declares a valid run while
    no manifest can be written without it.
    """
    held = (declaration or {}).get(ENVIRONMENT_HOME[0]) or {}
    return held.get(ENVIRONMENT_HOME[1])


def environment_for(row, declaration):
    """Exactly what the run hands this writer: the declared overrides, and HOME. Nothing else.

    `{name: value}`, where each name is one this writer's own table row declares and each value is
    the declared root of that name's class. A variable this writer reads and the table does not
    declare for it is ABSENT from the answer, which is the whole mechanism: it cannot redirect a
    write it is not there for.
    """
    roots = (declaration or {}).get("destinations") or {}
    held = {}
    for entry in row.get("destinations") or ():
        held[entry["override"]] = roots.get(entry.get("class"))
    home = declared_home(declaration)
    if home:
        held["HOME"] = home
    return held


def reads_not_given(writer, environment, root=None):
    """The override names this writer's own source reads that the run did not hand it.

    The derivation's job after the inversion: not to PROVE containment — the absence of a variable
    does that — but to DISCLOSE what a writer reaches for and is not given. A non-empty answer
    withholds certification, because a writer reading a name the run did not set resolves it through
    a fallback the run never declared, and where that fallback points is not this manifest's answer.
    """
    held = {entry["override"] for entry in closure(root)
            if entry["writer"] == writer and entry["override"]}
    # A pair the table has REASONED about is not an undisclosed read: `not_a_destination` names the
    # writer, the variable and why no §10.6 operation can reach that write. The row carries those
    # names with their reasons (`reads_excused`) so the manifest shows them instead of hiding them;
    # what withholds certification is a read nobody has reasoned about.
    return sorted(held - set(environment or {}) - set(excused_overrides(writer)))


def entry_invoked_in_release_1(row, entry):
    """Whether release-1 S11 may write THIS destination of this writer.

    The scope is per destination, not per writer, because S11 is itself one of the writers: the
    apply stage edits the declared checkout (invoked) and patches a personal layer (not invoked in
    release 1). An entry says so for itself and otherwise inherits its writer's answer, so a row
    cannot be narrowed by the writer's silence.
    """
    held = entry.get("release_1_invoked")
    return bool(row.get("release_1_invoked")) if held is None else bool(held)


def invoked_in_release_1(writer):
    """Whether release-1 S11 may invoke this writer at all.

    The scope is a FACT each row carries, not a sentence in a design record: release 1's apply writes
    the declared checkout and makes the git commit, and runs nothing else
    (`D-20261112-2cf1c4`). A row the release may not invoke has its certification WITHHELD by the
    name `not_invoked_in_release_1`, so a reader asking what this release may write reads the
    manifest rather than the record.
    """
    for row in writers():
        if row["writer"] == writer:
            return bool(row.get("release_1_invoked"))
    return False


def excused_overrides(writer):
    """`{override: reason}` the table declares not a destination for this writer."""
    return {row.get("override"): row.get("reason")
            for row in table().get("not_a_destination") or ()
            if row.get("writer") == writer and row.get("override")}


def environment_problems(declaration):
    """What stops an environment being produced at all, by name."""
    problems = []
    if not declared_home(declaration):
        problems.append(f"ENVIRONMENT_HOME_UNDECLARED: the run declares no "
                        f"{'.'.join(ENVIRONMENT_HOME)}, so every HOME-derived root is a guess and "
                        f"no writer can be handed an environment")
    return problems


# The ways a writer in this tree names the home it derives a root from: the library call, the shell
# variable, the tilde, and a LOCAL named `home` — `compose/instructions_install.py` assigns
# `home = Path(self.env.get("HOME", str(Path.home())))` and then builds every root from it, so a
# pattern that knew only `Path.home()` read that writer's roots as unestablishable.
_HOME_ROOTED = re.compile(
    r"""(?:pathlib\.Path\.home\(\)|Path\.home\(\)|os\.path\.expanduser\(|\$HOME|\$\{HOME\}"""
    r"""|\bhome\b|~)"""
    r"""\s*(?:/\s*)?["']?/?(?P<suffix>[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*)?""")


def source_line(writer, number, base=None):
    """The writer's own line `number`, or None when the file is not in this installation.

    The table stores a 160-character EXCERPT of that line as evidence for a reader; the computation
    reads the file, because the excerpt cut `str(home / ".config/agent-bios/corpus")` off the end of
    a long line and that root then read as unestablishable. The table says where to look; the source
    says what is there.
    """
    path = pathlib.Path(base or REPO) / writer
    if not path.is_file() or not number:
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not 0 < number <= len(lines):
        return None
    # The STATEMENT, not the line: `INSTRUCTIONS_STATUS_PATH = pathlib.Path(` opens a call whose
    # HOME-derived default is three lines further down, and one line of it establishes nothing. The
    # window ends where the parentheses balance, so it is the statement's own extent rather than a
    # guess, and it is bounded so an unbalanced file cannot read the rest of the module in.
    held = [lines[number - 1]]
    depth = held[0].count("(") - held[0].count(")")
    index = number
    while depth > 0 and index < len(lines) and len(held) < 6:
        held.append(lines[index])
        depth += lines[index].count("(") - lines[index].count(")")
        index += 1
    return " ".join(piece.strip() for piece in held)


def fixed_destination(entry, home, source_text=None):
    """`(path, why)` for one declared fixed root, computed from the GIVEN home.

    `path=None` with a reason is **certification withheld**: the row's own source line does not say,
    in a form this can read, where the writer will write. That is a state the manifest carries and
    S11 refuses on — not a warning. Before this, a fixed-root row was certified by
    `path = root, inside = bool(root)`, which asserts nothing about the writer at all: `install.sh`
    came back certified at the install_roots root while its source puts STATE_DIR under HOME (the
    round-2 review).
    """
    source = source_text if source_text is not None else ((entry or {}).get("root") or "")
    if not home:
        return None, "the run declares no home, so a HOME-derived root cannot be computed"
    held = _HOME_ROOTED.search(source)
    if not held:
        return None, (f"its source line names no HOME-derived root this can read: {source[:80]!r}")
    suffix = held.group("suffix") or ""
    if not suffix or "(" in suffix or "," in suffix:
        # The line derives its root from HOME and the SUFFIX is an expression this cannot read —
        # `Path(environment_value(..., str(home / ".config/agent-bios/corpus")))` on one line of a
        # multi-line call. What is established is the BOUND: the writer writes under the home it
        # was given. Whether that is a certification depends on the class root, which is the
        # caller's comparison, so the bound is returned and labelled rather than guessed at or
        # refused outright.
        return str(pathlib.Path(home)), ("a HOME-derived root whose suffix this cannot read "
                                         f"({source[:60]!r}); the home is its upper bound")
    return str(pathlib.Path(home) / suffix), "/".join(["<home>", suffix])


# ─── The four channels an environment cannot close ───────────────────────────────────────────────
# Scrubbing the environment is the mechanism and it is not sufficient: a writer can reach a path
# without reading a variable at all. Each channel has a RULE here rather than a hope, and each rule
# is derived from the writer's own source.
#
#  * the PASSWORD DATABASE. `getpwuid`/`getpwnam` answer with the account's home whatever HOME says,
#    so a path built from one cannot be redirected by the run at all. No writer may read it: this is
#    not excusable by a statement, because there is nothing the run could do about it. This is the
#    channel that wrote a run into the owner's real home during a commit hook, and it is proved BY
#    SOURCE — never by running a writer with a real HOME to see where it lands.
#  * a LOGIN SHELL. `bash -l`, `zsh -l`, `--login` re-read the user's profile and restore exactly
#    the variables the run scrubbed, so a child shell must not be a login shell.
#  * an ABSOLUTE LITERAL. A path spelled out in the source reads no variable, so the row must state
#    it with its reason.
#  * a PATH ARGUMENT. Not a hole but the PREFERRED channel: an argument cannot be inherited by
#    anything, so a writer that takes one is handed its root that way and the row records it.
CHANNEL_RULES = {
    "password_database": (
        re.compile(r"\b(?:getpwuid|getpwnam|pwd\.getpw\w+|os\.getlogin)\s*\("),
        "reads the password database, whose answer the run cannot redirect at all"),
    "login_shell": (
        re.compile(r"(?:--login\b|\b(?:ba|z)?sh\s+-[A-Za-z]*l\b)"),
        "starts a login shell, which re-reads the user's profile and restores what was scrubbed"),
}
# The path-argument channels THIS TREE declares, by writer. Written out so the control over the
# live table compares against a specification rather than against the table it is judging: a keyed
# comparison fails for a row that appears, disappears or changes its option (the round-4 review).
CHANNEL_STATED_ARGUMENTS = {
    "compose/assemble.py": ("--state-dir",),
    "compose/instructions-state.py": ("--state-dir",),
    "compose/instructions_app.py": ("--state-dir",),
    "compose/instructions_import.py": ("--state-dir",),
    "compose/instructions_understand.py": ("--state-dir",),
    "compose/prune-backups.py": ("--state-dir",),
    "compose/windows_deploy.py": ("--root",),
    "install.sh": ("--state-dir",),
    "wrappers/claude-run.sh": ("--home", "--root"),
    "wrappers/codex-helm.sh": ("--home",),
    "wrappers/codex-run.sh": ("--home",),
}
CHANNEL_STATED = {
    "absolute_literals": (
        # The token is the literal's first whitespace-free run: `"/Library/Application Support/x"`
        # identifies itself by `/Library/Application`, and a command string like `"/bin/sleep 30 &"`
        # by `/bin/sleep`, which is what a statement about it should name. The closing quote is NOT
        # required — a literal with a space in it is still an absolute path in the source.
        re.compile(r"""["'](/(?:usr|opt|etc|var|srv|Users|home|Library|private|tmp|bin|sbin)"""
                   r"""[^"'\s]*)"""),
        "names an absolute path in its source, which reads no variable"),
    "path_arguments": (
        re.compile(r"(--(?:state-dir|config-home|corpus-dir|instructions-dir|root|prefix"
                   r"|home))\b"),
        "takes a path as an argument, which is the channel the run prefers"),
}


def channel_lines(text, pattern):
    """The line numbers of a pattern's matches outside comments, for one writer's source."""
    held = []
    for number, line in enumerate((text or "").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("#", "//", "*")):
            continue
        if pattern.search(line):
            held.append(number)
    return held


def guarded_by(text, line, name):
    """Whether the statement at `line` runs only when `name` is ABSENT from the environment.

    The licence for the one channel that cannot otherwise be excused. `compose/instructions_session`
    reads the password database at one line, and only inside `if home is None:` where `home` came
    from `env.get('HOME')` — so with HOME GIVEN, the line is unreachable, and the environment closes
    the channel after all. Two hops, both from the source: the enclosing `if` names the guard, or it
    names a local the enclosing scope assigned from it. Proved by SOURCE, never by running a writer
    against a real home to see where it lands.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # A shell writer: the guard has to be visible immediately above the line, which is as much
        # as a reader of shell can establish without an interpreter.
        lines = (text or "").splitlines()
        held_name = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")
        return any(held_name.search(held) for held in lines[max(0, line - 6):line - 1])
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        inside = any(getattr(child, "lineno", None) == line
                     for part in list(node.body) + list(node.orelse)
                     for child in ast.walk(part))
        if not inside:
            continue
        held_name = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")
        test = ast.unparse(node.test)
        if held_name.search(test):
            return True
        asked = {held.id for held in ast.walk(node.test) if isinstance(held, ast.Name)}
        for assign in ast.walk(tree):
            if isinstance(assign, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id in asked
                    for target in assign.targets):
                if held_name.search(ast.unparse(assign.value)):
                    return True
    return False


def channel_tokens(text, pattern):
    """The matched tokens of a pattern outside comments: the literal path, the option name."""
    held = set()
    for line in (text or "").splitlines():
        if line.strip().startswith(("#", "//", "*")):
            continue
        for found in pattern.finditer(line):
            held.add(found.group(1) if found.groups() else found.group(0))
    return held


def channel_problems(root=None):
    """Every channel a writer's source shows that this module has not answered for, by name.

    Two kinds. A FORBIDDEN channel (the password database, a login shell) is a defect no statement
    excuses, because the run cannot do anything about it. A STATED channel (an absolute literal, a
    path argument) must be named in the writer's own row with its reason, and a statement whose
    channel the source no longer shows is stale — the same bar as every other allowlist here.
    """
    base = pathlib.Path(root or REPO)
    problems, subjects = [], 0
    for row in writers():
        path = base / row["writer"]
        if not path.is_file():
            continue
        subjects += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        stated = row.get("channels") or {}
        for name, (pattern, why) in CHANNEL_RULES.items():
            licences = {held.get("line"): held for held in stated.get(name) or ()
                        if isinstance(held, dict)}
            for number in channel_lines(text, pattern):
                licence = licences.get(number)
                guard = (licence or {}).get("guarded_by")
                if guard and guarded_by(text, number, guard) and (licence or {}).get("reason"):
                    # Licensed, and the licence is held against the source: the line runs only when
                    # the run does not set `guard`, and the run always sets it. A licence naming no
                    # line, or a guard the source does not show, licenses nothing.
                    continue
                problems.append(f"CHANNEL_{name.upper()} {row['writer']}:{number}: it {why}, so the "
                                f"environment the run hands it cannot decide where it writes"
                                + (f" — the row licenses line {number} by {guard!r}, which its "
                                   f"source does not show guarding it" if guard else ""))
            for number in sorted(licences):
                if number not in channel_lines(text, pattern):
                    problems.append(f"CHANNEL_STALE {row['writer']} {name}:{number}: the row "
                                    f"licenses a line the source no longer shows")
        for name, (pattern, why) in CHANNEL_STATED.items():
            # Keyed to the TOKEN — the literal path, the option name — and not to a line number,
            # which goes stale on any edit above it and teaches a reader to renumber rather than
            # re-examine. The licence above is line-keyed on purpose: there is one of it, and a
            # moved line there has to be looked at again.
            found = channel_tokens(text, pattern)
            held_stated = stated.get(name) or {}
            said = set(held_stated.get("tokens") or ())
            if found - said:
                problems.append(f"CHANNEL_UNSTATED {row['writer']} {name}: "
                                f"{', '.join(sorted(found - said)[:4])} — it {why}, and the row "
                                f"says nothing about {'that' if len(found - said) == 1 else 'those'}")
            if said - found:
                problems.append(f"CHANNEL_STALE {row['writer']} {name}: the row states "
                                f"{', '.join(sorted(said - found)[:4])} and the source no longer "
                                f"shows it")
            if found and not held_stated.get("reason"):
                problems.append(f"CHANNEL_UNREASONED {row['writer']} {name}: the row names the "
                                f"tokens and gives no reason why this channel is safe for a run "
                                f"that confines this writer")
    if not subjects:
        problems.append("CHANNEL_NO_WRITERS_READ: no writer's source was read, so every channel "
                        "would pass unexamined")
    return problems


# ─── git: not this release's to run ──────────────────────────────────────────────────────────────
#
# Release 1's S11 writes the approved changes into files of the declared checkout and executes NO
# git: it ends by naming the commit command and the install command for the owner to run, and the
# owner commits as usual, so the repository's hooks run in the owner's own environment
# (`D-20261113-f22b7d`, narrowing `D-20261112-2cf1c4`).
#
# The git environment, the configuration policy, the hooks certificate and the hook-refusal contract
# that stood here are REMOVED rather than kept behind a label. Round 4 found five blocking defects in
# them — the parser was not git's grammar, repository-layout redirections were not walked, hook files
# were not inspected, signing and trailer commands executed arbitrary programs, and the repository's
# own hook writes under /tmp and provisions under HOME — and a module still carrying a
# `git_certificate` would read as a working certification to the next reader. They live in history at
# `0ab9fca2` with that review and
# `design/session-distill/2026-11-13T0130--0ab9fca--release-1-s11-writes-files-and-the-owner-commits.md`
# beside them, which is where release 2 starts. Two facts measured for it are in that record: one
# variable closes both of git's global files, and WHICH git binary runs is decided by the active
# developer directory (`DEVELOPER_DIR`), outside any configuration policy.
#
# What the release needs from git is nothing. The before-state is the file hashes the approvals carry,
# checked through `runlib/targets`.


def claim_problems(declaration, environ, scope="release_1"):
    """Where the caller's CLAIM about the environment differs from what the run produces.

    This used to be asked per destination row, which tied it to a row resting on an override. Once
    `inventory.py`'s HOME became a read (the round-4 review), release 1 had no such row left and the
    check went silent — while the run still HANDS every invoked writer a HOME and git its isolation.
    The question belongs to the produced mapping, so it is asked there: for every writer the scope
    invokes, a name the caller says it will run with and the run produces differently is refused.
    """
    problems = []
    for row in writers():
        if scope == "release_1" and not row.get("release_1_invoked"):
            continue
        produced = environment_for(row, declaration)
        for name, value in sorted(produced.items()):
            claimed = (environ or {}).get(name)
            if claimed is not None and claimed != value:
                problems.append(
                    f"ENVIRONMENT_CLAIM_DIFFERS {row['writer']} {name}: the caller says it will run "
                    f"with {claimed!r} and the run produces {value!r}, so what this writer is handed "
                    f"is not established and no effect may proceed")
    return problems


def resolved_rows(declaration, environ, root=None, scope="release_1"):
    """One row per writer: `{class, writer, path, root, inside}` as N#4 names it.

    `path` is what the writer will actually write under, taken from the environment the run hands it
    — never from this process's own environment unless the caller passes it.

    `scope` is the RELEASE, as a parameter rather than a constant: `release_1` resolves only the
    writers release-1 S11 may invoke and names the rest `not_invoked_in_release_1`
    (`D-20261112-2cf1c4`), and `all` resolves every row. S11 and the manifest take the default; the
    wider scope is how the resolution machinery stays exercised for the writers a later release
    will invoke, so narrowing the release does not quietly retire the mechanism that confines them.
    """
    if scope not in ("release_1", "all"):
        raise Refused(f"RESOLUTION_SCOPE_UNKNOWN {scope!r}: the scopes are 'release_1' and 'all'; "
                      f"a typo that resolved everything would widen the release silently")
    roots = (declaration or {}).get("destinations") or {}
    home = declared_home(declaration)
    rows = []
    absent = set(author_rows_absent(root))
    for row in writers():
        if row["writer"] in absent:
            # Named, not certified: the writer is not in this install, so it writes nowhere. Saying
            # so in the manifest is the point — a silent omission would read as "no such writer".
            rows.append({"class": row.get("writes_without_override")
                         or (row.get("destinations") or [{}])[0].get("class"),
                         "writer": row["writer"], "path": None, "root": None, "inside": None,
                         "certification": "not_installed",
                         "not_installed": "author-side writer, not present in this install"})
            continue
        if scope == "release_1" and not row.get("release_1_invoked"):
            # The SCOPE, as a state of the row: release 1's S11 writes the declared checkout and
            # commits, and runs nothing else (D-20261112-2cf1c4). Certification is withheld by that
            # name rather than computed, because computing it would mean certifying what a writer
            # this release never invokes would do — which is exactly the unbounded surface three
            # review rounds kept finding new defects in.
            rows.append({"class": row.get("writes_without_override")
                         or (row.get("destinations") or [{}])[0].get("class"),
                         "writer": row["writer"], "path": None, "root": None, "inside": None,
                         "certification": RELEASE_1_UNINVOKED,
                         # One owner for the sentence: a row says something of its own only where
                         # its reason differs, instead of the same sentence written out 22 times.
                         "why": row.get("$comment_release_1") or RELEASE_1_WHY})
            continue
        # What this writer is GIVEN, and what it reads that is not in it. The environment is the
        # mechanism; the disclosure is what says the mechanism is not enough for this writer.
        given = environment_for(row, declaration)
        ungiven = reads_not_given(row["writer"], given, root)
        excused = excused_overrides(row["writer"])
        # One row per (writer, override), so a single escaping value cannot hide behind a sibling
        # of the same writer that is in root.
        for entry in row.get("destinations") or ():
            override, cls = entry.get("override"), entry.get("class")
            if entry.get("read_only"):
                # A READ, not a destination. The row exists because the derivation sees the read
                # reach a write, and a row that came back certified presented the owner's home as a
                # place this release may write (the round-4 review). The state is named and carries
                # no path, in every scope: what the writer does with the value does not change.
                rows.append({"class": cls, "writer": f"{row['writer']} [{override}]",
                             "path": None, "root": None, "inside": None,
                             "certification": READ_NOT_WRITTEN, "why": entry["read_only"]})
                continue
            if scope == "release_1" and not entry_invoked_in_release_1(row, entry):
                # The scope is per DESTINATION, because S11 is itself a writer here: the apply
                # stage edits the declared checkout (invoked) and patches a personal layer (not
                # invoked in release 1). Naming this row rather than certifying it is what keeps a
                # deferred finding about the personal layers out of reach.
                rows.append({"class": cls, "writer": f"{row['writer']} [{override}]",
                             "path": None, "root": None, "inside": None,
                             "certification": RELEASE_1_UNINVOKED,
                             "why": entry.get("$comment_release_1") or RELEASE_1_WHY})
                continue
            # `held_root`, not `root`: the parameter names the INSTALLATION being inspected, and
            # this loop used to rebind it to a class root — so anything later in the function that
            # needed the installation root got a destination instead.
            # The certificate is resolved from the environment the run PRODUCES for this writer,
            # never from the caller's separate dict. The two could disagree — `environment_for`
            # sets HOME from the declaration, and every override's value is its class's declared
            # root — so a row certified from `environ` certified a value the writer would not be
            # handed. `environ` is now read as the caller's CLAIM about what it will run with, and
            # a claim that differs from what the run produces is refused rather than preferred
            # (the round-3 review).
            held_root, value = roots.get(cls), given.get(override)
            claimed = (environ or {}).get(override)
            if not value:
                rows.append({"class": cls, "writer": f"{row['writer']} [{override}]", "path": None,
                             "root": held_root, "inside": False, "unset": [override],
                             "certification": "unset"})
                continue
            if claimed is not None and claimed != value:
                rows.append({"class": cls, "writer": f"{row['writer']} [{override}]",
                             "path": value, "root": held_root, "inside": None,
                             "certification": "withheld",
                             "why": f"the caller says it will run with {override}={claimed!r} and "
                                    f"the run produces {value!r} for it, so which path this "
                                    f"certificate speaks for cannot be established"})
                continue
            rows.append({"class": cls, "writer": f"{row['writer']} [{override}]", "path": value,
                         "root": held_root,
                         "inside": bool(held_root) and _inside(value, held_root),
                         "reads_not_given": ungiven, "reads_excused": excused,
                         "certification": "withheld" if ungiven else "given",
                         "why": (f"its source reads {', '.join(ungiven)}, which the run does not "
                                 f"hand it, so it would resolve those through a fallback nobody "
                                 f"declared" if ungiven else
                                 "the run hands it this value and nothing else can redirect it")})
        if row.get("writes_without_override"):
            cls = row["writes_without_override"]
            held_root = roots.get(cls)
            fixed = [entry for entry in row.get("fixed_roots") or ()
                     if not entry.get("not_a_destination")]
            if row.get("writer_unwritten"):
                # A forward declaration: the file does not exist yet, so there is nothing to
                # confine and nothing to withhold. `INVENTORY_FORWARD_LANDED` fails the day it
                # appears, which is when the derived closure takes over from this row.
                rows.append({"class": cls, "writer": row["writer"], "path": None,
                             "root": held_root, "inside": None, "certification": "forward",
                             "why": "declared as a writer that does not exist yet"})
                continue
            if row.get("root_from") == "argument":
                # The PREFERRED channel, and a certification in its own right: the run hands this
                # writer its root as an argument, so there is no variable to inherit and nothing to
                # derive from HOME. An argument cannot be redirected by an environment at all.
                rows.append({"class": cls, "writer": row["writer"], "path": held_root,
                             "root": held_root, "inside": bool(held_root),
                             "certification": "argument",
                             "why": "the run passes this writer its root; it reads no override for "
                                    "it and derives nothing from HOME"})
                continue
            if not fixed:
                # A row that claims a fixed root and shows none of the lines it came from cannot be
                # certified: there is nothing to compute from. `writer_unwritten` rows are the
                # exception the table declares for work in flight.
                rows.append({"class": cls, "writer": row["writer"], "path": None,
                             "root": held_root, "inside": None,
                             "certification": None if row.get("writer_unwritten") else "withheld",
                             "why": ("declared as a writer that does not exist yet"
                                     if row.get("writer_unwritten") else
                                     "the row claims a HOME-fixed root and shows no source line "
                                     "for it, so there is nothing to compute from")})
                continue
            for entry in fixed:
                held_line = source_line(row["writer"], entry.get("derived_at_line"), root)
                path, why = fixed_destination(entry, home, source_text=held_line)
                bounded = path is not None and "upper bound" in why
                # A bound is a certification only where the class root CONTAINS the home: then
                # every path the writer can compute under the home is inside the root, whatever the
                # suffix is. Where the root is narrower, the suffix is exactly what would decide,
                # and it is unread — so certification is withheld rather than guessed either way.
                if bounded and not (bool(held_root) and _inside(str(pathlib.Path(home)), held_root)):
                    rows.append({"class": cls,
                                 "writer": f"{row['writer']} [fixed:{entry.get('derived_at_line')}]",
                                 "path": None, "root": held_root, "inside": None,
                                 "certification": "withheld",
                                 "why": f"{why}, and the declared {cls} root is narrower than the "
                                        f"home, so whether this write lands inside it is exactly "
                                        f"what the unread suffix would decide"})
                    continue
                rows.append({"class": cls,
                             "writer": f"{row['writer']} [fixed:{entry.get('derived_at_line')}]",
                             "path": path, "root": held_root,
                             "inside": None if path is None else (bool(held_root)
                                                                  and _inside(path, held_root)),
                             "certification": ("withheld" if path is None
                                               else "bounded" if bounded else "computed"),
                             "why": why})
    return rows


def resolution_problems(rows):
    """The refusals the resolved set carries, by name, in the order a reader needs them.

    `OVERRIDE_MISSING` comes first: an unset override means the path in the row is not what the
    writer would use, so judging that path for escape would be judging a value nobody will write to.
    """
    problems = []
    for row in rows:
        for name in row.get("unset") or ():
            problems.append(f"OVERRIDE_MISSING {row['writer']} {name}: unset, so this writer would "
                            f"resolve through a fallback the run did not declare")
    for row in rows:
        if row.get("unset"):
            continue
        if row.get("not_installed"):
            # Nothing to confine: the writer is not in this install, so it has no path to judge.
            # Judging it would produce DESTINATION_ROOT_ABSENT for a writer that cannot write,
            # which is how the packaged manifest refused over a file npm does not ship.
            continue
        if row.get("certification") == READ_NOT_WRITTEN:
            # A read has nothing to confine and needs no root: requiring one would make the owner
            # declare a destination for a value the writer only reads (the round-4 review).
            continue
        if row.get("certification") == RELEASE_1_UNINVOKED:
            # Not an escape and not a certification: a writer this release does not invoke has
            # nothing to confine. It is named in the manifest and S11 refuses any operation that
            # would reach it, which is the apply stage's question rather than this one's.
            continue
        if row.get("certification") == "forward":
            # A forward declaration: no file, no path, nothing to confine. `INVENTORY_FORWARD_LANDED`
            # is what fails the day the writer appears.
            continue
        if row.get("certification") == "withheld":
            # A NAMED STATE, not a warning: the manifest says certification is withheld for this
            # destination, and S11 refuses on it. Before, a fixed root was certified by
            # `path = root, inside = bool(root)`, which asserts nothing about where the writer
            # writes — `install.sh` was certified at the install_roots root while its own source
            # puts STATE_DIR under HOME (the round-2 review).
            problems.append(f"DESTINATION_UNCERTIFIED {row['writer']}: {row.get('why')}, so where "
                            f"this writer writes cannot be established and no effect may proceed")
            continue
        if not row.get("root"):
            problems.append(f"DESTINATION_ROOT_ABSENT {row['writer']}: the run declares no root for "
                            f"class {row['class']}")
            continue
        if row.get("path") is None:
            problems.append(f"DESTINATION_UNRESOLVED {row['writer']}: no path was resolved for it, "
                            f"so there is nothing to judge for containment")
            continue
        if not row["inside"]:
            problems.append(f"DESTINATION_OUTSIDE_ROOT {row['writer']}: {row['path']} is not inside "
                            f"{row['root']}")
    return problems


def problems(declaration, environ, root=None):
    """Everything wrong, table and resolution together. Empty means apply may take its first effect."""
    held = (environment_problems(declaration)
            + claim_problems(declaration, environ)
            + layout_problems(root) + channel_problems(root)
            + table_problems(root) + fidelity_problems(root) + inventory_problems(root))
    if held:
        return held
    return resolution_problems(resolved_rows(declaration, environ, root))


def document(declaration, environ, root=None):
    """The manifest `apply` writes before any effect, or Refused naming what stops it."""
    rows = resolved_rows(declaration, environ, root)
    # The derived inventory is part of the manifest's own correctness, not a separate audit: a
    # destination the tree writes and the table does not carry is exactly the hole this manifest
    # exists to close, so `apply` refuses before any effect rather than recording a partial answer.
    held = (environment_problems(declaration)
            + claim_problems(declaration, environ)
            + layout_problems(root) + channel_problems(root)
            + table_problems(root) + fidelity_problems(root) + inventory_problems(root)
            + resolution_problems(rows))
    if held:
        raise Refused("; ".join(held))
    return {"stage": "S11", "resolved": rows,
            # No git key: release 1's S11 executes no git (`D-20261113-f22b7d`), so a certificate
            # here would speak for a command this release never runs.
            "release_scope": {"scope": "release_1",
                              "decision": "D-20261112-2cf1c4",
                              "uninvoked": sorted({r["writer"] for r in rows
                                                   if r.get("certification")
                                                   == RELEASE_1_UNINVOKED})},
            "overrides_required": list(required_overrides()),
            "classes": list(CLASSES),
            "writers_scanned": sorted({entry["writer"] for entry in closure(root)}),
            "layout": install_layout(root),
            "not_installed": author_rows_absent(root),
            "$comment": "design §10.5 / N#4: every writer's destination, resolved from the "
                        "environment the run hands it and asserted inside its declared root before "
                        "the first effect."}


def write(run_dir, declaration, environ):
    """Write the manifest into the run. Nothing is written when anything refuses.

    The path is absolute beneath the run and the file is registered with the stage, for the reason
    `stage_propose.run` states: `records.write_json` confines its path, so a bare name resolves
    against the working directory and is refused, and an unregistered output leaves the next stage's
    staleness check nothing to read.
    """
    run_dir = pathlib.Path(run_dir)
    doc = document(declaration, environ)       # refuses before the stage record is opened
    # No declared input: the run declaration is the run's own root, not a stage output, so naming it
    # as one is refused (`INPUT_INVALID S0: no record for the stage that produces run.json`). Every
    # stage that reads only the declaration opens its record the same way.
    with records.run_stage(run_dir, "S11") as stage:
        records.write_json(run_dir, run_dir / OUTPUT, doc)
        stage.output(OUTPUT)
        return stage, doc


# ---- self-test ---------------------------------------------------------------------------------


# ─── The effect audit ───────────────────────────────────────────────────────────────────────────
# One owner for one vocabulary. `drift.py` holds itself to this same function rather than carrying a
# second copy of the rules, because two copies drift and the first round's copies did: each module
# watched a different tuple of module names.
#
# What the round-2 review found the old rules passing, every item reachable: `__import__('os')
# .system(...)` and `importlib.import_module('os').system(...)`, because the call's first printed
# component is neither `os` nor `subprocess`; `pathlib.Path(x).write_text(...)` and `open(x, 'w')`,
# because a filesystem write names no watched module at all; anything inside `main`, because `main`
# was excluded by name although `python3 -m runlib.destinations` runs it; and the effects of a
# `self_test` that a runtime function calls, because `self_test` was excluded by name too.
#
# So the exclusions are now by REACHABILITY, not by name. `self_test` is skipped only while every
# path to it passes a branch guarded by a `--self-test` test; called from anywhere else, its effects
# are the module's effects.
EFFECT_MODULES = ("subprocess", "os", "shutil", "tempfile", "socket", "urllib", "http", "ftplib",
                  "smtplib", "multiprocessing", "ctypes", "signal", "pty", "fcntl", "webbrowser")
# Reading a path out of the environment and joining it is not an effect; this is the whole list.
EFFECT_ALLOWED = ("os.path.normpath", "os.path.join", "os.path.sep", "os.path.basename",
                  "os.path.dirname", "os.path.isabs", "os.path.splitdrive", "os.path.split",
                  "os.sep", "os.fspath", "os.environ", "os.environ.get", "os.name")
# Filesystem writes by METHOD NAME, on any object: `pathlib.Path(p).write_text(...)` names no
# watched module, and neither does a handle the function was handed by its caller.
EFFECT_METHODS = ("write_text", "write_bytes", "writelines", "mkdir", "makedirs", "touch", "unlink",
                  "rmdir", "rmtree", "rename", "symlink_to", "hardlink_to", "chmod", "chown",
                  "truncate", "copy", "copy2", "copytree", "move")
# Anything that can produce a call whose name this audit cannot read.
EFFECT_DYNAMIC = ("__import__", "exec", "eval", "compile", "importlib.import_module",
                  "importlib.__import__", "runpy.run_path", "runpy.run_module")
EFFECT_WRITE_MODES = set("wax+")


def _self_test_branch(node):
    """`"body"`, `"orelse"` or None: which half of an `if` the `--self-test` flag guards.

    The skip followed `orelse` for any test mentioning the flag, which is exactly inverted for
    `if "--self-test" not in sys.argv:` — there the BODY is the runtime path, and the audit skipped
    it (the round-3 review). Decided from the test's own shape: a `not in` comparison or a `not`
    puts the runtime code in the body, anything else in the orelse.
    """
    rendered = ast.unparse(node.test)
    if "--self-test" not in rendered:
        return None
    # Only the two predicates this audit can PROVE. `"--self-test" not in sys.argv and True` was
    # read as the negated form and its body — real runtime code — was skipped (the round-4 review).
    # Anything else mentioning the flag is unsupported, and an unsupported guard means both halves
    # are scanned rather than one being trusted: a wrong skip hides an effect, a wrong scan only
    # reports one.
    # And the LEFT side must be the flag itself, exactly. `'--self-test-other' in argv` mentions
    # the flag as a substring and guards nothing this audit knows about; its body was skipped (the
    # round-5 review).
    if isinstance(node.test, ast.Compare) and len(node.test.ops) == 1 \
            and isinstance(node.test.left, ast.Constant) and node.test.left.value == "--self-test":
        # The right side must be the ARGUMENT VECTOR, not any container that happens to hold the
        # flag: `'--self-test' in held.flags()` is a call this audit cannot evaluate, and reading it
        # as dispatch skipped a half on the strength of a method name.
        held = ast.unparse(node.test.comparators[0])
        if held in ("sys.argv", "argv", "sys.argv[1:]", "argv[1:]"):
            if isinstance(node.test.ops[0], ast.In):
                return "orelse"
            if isinstance(node.test.ops[0], ast.NotIn):
                return "body"
    return None


def _effect_reachable(tree):
    """The top-level function names a runtime entry point can reach.

    Roots are the module's top level and every top-level function except `self_test`; an edge
    through a branch whose test names `--self-test` is not followed, which is what keeps a suite's
    own fixture building out of the answer without excluding the suite by name.
    """
    functions = {node.name: node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    # A class's METHODS are code too. The scope was top-level functions only, so
    # `main()` calling `Writer().go()` reached nothing and an effect inside `go` was invisible (the
    # round-3 review). Methods are registered as `Class.method`, and reaching the CLASS reaches
    # them: whether a particular method is called needs an analysis this does not have, and for an
    # effect audit the over-approximation is the safe direction.
    methods = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for held in node.body:
                if isinstance(held, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[f"{node.name}.{held.name}"] = held
                    functions[f"{node.name}.{held.name}"] = held

    def called_in(node):
        held = set()

        def walk(parent):
            # The node itself first: a top-level `f()` is the root of its own statement, and a walk
            # that only looked at children never saw it.
            if isinstance(parent, ast.Call):
                rendered = ast.unparse(parent.func)
                held.add(rendered)
                held.add(rendered.split(".")[0].split("(")[0])
            for child in ast.iter_child_nodes(parent):
                held_half = isinstance(child, ast.If) and _self_test_branch(child)
                if held_half:
                    for part in (child.body if held_half == "body" else child.orelse):
                        walk(part)                # the unguarded half still counts
                    continue
                walk(child)

        walk(node)
        return held

    # A function the SUITE alone calls is the suite. Excluding `self_test` by name and making every
    # other function a root read `_self_test_body` — the half of the suite a dying-control wrapper
    # delegates to — as a runtime entry point, and the suite's own fixture building as module
    # effects. Decided by reachability like everything else here: a function is test-only when it
    # has callers and every one of them is test-only, and `self_test` qualifies when nothing
    # outside that set calls it. A `self_test` a RUNTIME function calls is therefore not test-only,
    # which is the case a control below plants.
    callers = {name: set() for name in functions}
    for held_name, held_node in functions.items():
        for reached in called_in(held_node) & set(functions):
            callers[reached].add(held_name)
    test_only = set()
    moved = True
    while moved:
        moved = False
        for name in functions:
            if name in test_only:
                continue
            held_callers = callers[name] - test_only
            if name == "self_test" and not held_callers:
                test_only.add(name)
                moved = True
            elif name != "self_test" and callers[name] and not held_callers:
                test_only.add(name)
                moved = True
    frontier = {name for name in functions if name not in test_only and name not in methods}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            held_reached = called_in(node)
            frontier |= held_reached & set(functions)
            frontier |= {name for name in methods if name.split(".")[0] in held_reached}
    held = set()
    while frontier:
        name = frontier.pop()
        if name in held or name not in functions:
            continue
        held.add(name)
        reached = called_in(functions[name])
        frontier |= reached & set(functions)
        for held_name in methods:
            if held_name.split(".")[0] in reached:
                frontier.add(held_name)
    return held


def effect_scope(source):
    """What `effect_audit` scanned: the module's top level and the functions it reached.

    An audit that scanned nothing reports nothing, so the suites assert this set rather than
    reading a clean answer as proof.
    """
    return sorted(_effect_reachable(ast.parse(source)) | {"<module>"})


def effect_audit(source):
    """Every effect a module's reachable runtime code performs, by canonical name.

    A function over source text rather than a block over one file, so each widened rule can be
    shown to fire on a planted call. The answer carries the function the call sits in, because
    `in main` is the difference between a reported effect and an excluded one.
    """
    tree = ast.parse(source)
    bindings = {}                                 # local name -> the module it is bound to
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.split(".")[0]] = alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bindings[alias.asname or alias.name] = node.module.split(".")[0]

    reachable = _effect_reachable(tree)
    scope = [("<module>", node) for node in tree.body
             if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    scope += [(node.name, node) for node in tree.body
              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
              and node.name in reachable]
    # And the METHODS the reachability found. Walking only top-level functions left them out of the
    # scan even once they were reached, which is the half of the finding that mattered: the effect
    # sits in the method body.
    # A class BODY runs at definition time, so a statement there is runtime code with no function
    # to be reached through: `open('/outside', 'w')` beside the methods was invisible (the round-4
    # review). Included under the class's own name, before its methods.
    scope += [(held.name, node) for held in tree.body if isinstance(held, ast.ClassDef)
              for node in held.body
              if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    # Everything ELSE that runs when a definition is executed, whoever calls the thing defined: a
    # class's bases and keywords, any decorator, a function's default arguments, and the whole of a
    # class nested in a class — body, methods' definitions and all. A default argument that calls
    # `open` runs at import, in a method nobody ever calls (the round-5 review). A nested class's
    # method BODIES are scanned too: reachability is computed over top-level names, so the safe
    # direction for a name it cannot see is to scan it.
    def definition_time(node, where, nested=False):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for held in [*node.decorator_list, *node.args.defaults,
                         *[d for d in node.args.kw_defaults if d is not None]]:
                yield f"{where} definition", held
            if nested:
                for held in node.body:
                    yield where, held
        elif isinstance(node, ast.ClassDef):
            for held in [*node.decorator_list, *node.bases, *[k.value for k in node.keywords]]:
                yield f"{where} definition", held
            for held in node.body:
                if isinstance(held, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield from definition_time(held, f"{where}.{held.name}", nested)
                elif isinstance(held, ast.ClassDef):
                    yield from definition_time(held, f"{where}.{held.name}", True)
                elif nested:
                    yield where, held

    for held in tree.body:
        if isinstance(held, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope += list(definition_time(held, held.name))
    scope += [(f"{held.name}.{node.name}", node) for held in tree.body
              if isinstance(held, ast.ClassDef) for node in held.body
              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
              and f"{held.name}.{node.name}" in reachable]

    held = set()

    def say(where, text):
        held.add(text if where == "<module>" else f"{text} (in {where})")

    def mode_of(node):
        """The mode an `open` call was given: the string, None for a default read, or '?'."""
        asked = None
        if len(node.args) > 1:
            asked = node.args[1]
        for keyword in node.keywords:
            if keyword.arg == "mode":
                asked = keyword.value
        if asked is None:
            return None
        if isinstance(asked, ast.Constant) and isinstance(asked.value, str):
            return asked.value
        return "?"

    for where, root_node in scope:
        def walk(parent):
            # Look at `parent`, then recurse. A walk that looked only at CHILDREN never saw a
            # top-level `import os as _o` or a top-level `os.system(...)`, because each is the root
            # of its own statement — which is how the alias control came back empty.
            look(parent)
            for child in ast.iter_child_nodes(parent):
                held_half = isinstance(child, ast.If) and _self_test_branch(child)
                if held_half:
                    for part in (child.body if held_half == "body" else child.orelse):
                        walk(part)
                    continue
                walk(child)

        def look(child):
                if isinstance(child, ast.Import):
                    for alias in child.names:
                        if alias.asname and alias.name.split(".")[0] in EFFECT_MODULES:
                            say(where, f"import {alias.name} as {alias.asname} (an alias on a "
                                       f"watched module hides its calls from this very check)")
                if isinstance(child, ast.Call):
                    rendered = ast.unparse(child.func)
                    root_name = rendered.split(".")[0].split("(")[0]
                    # A watched module, under its own name or an alias.
                    if bindings.get(root_name) in EFFECT_MODULES or root_name in EFFECT_MODULES:
                        canonical = rendered.replace(root_name,
                                                     bindings.get(root_name, root_name), 1)
                        if canonical not in EFFECT_ALLOWED:
                            say(where, canonical)
                    # A dynamic import or dispatch anywhere in the callee expression.
                    for mark in EFFECT_DYNAMIC:
                        if re.search(rf"(?<![\w.]){re.escape(mark)}(?![\w])", rendered):
                            say(where, f"{rendered} — {mark} reaches a module this audit "
                                       f"cannot name")
                    # A filesystem write by method name, on whatever object.
                    if rendered.split(".")[-1] in EFFECT_METHODS:
                        say(where, rendered)
                    # `open` for writing, builtin or method, including an undecidable mode.
                    if rendered.split(".")[-1] == "open":
                        mode = mode_of(child)
                        if mode == "?":
                            say(where, f"{rendered}(mode=<not a literal>) — a mode this audit "
                                       f"cannot read")
                        elif mode is not None and set(mode) & EFFECT_WRITE_MODES:
                            say(where, f"{rendered}(mode={mode!r})")
                    # `getattr(os, "system")(...)`: the callee is itself a getattr over a module.
                    if isinstance(child.func, ast.Call) \
                            and getattr(child.func.func, "id", "") == "getattr":
                        inner = child.func
                        if inner.args and ast.unparse(inner.args[0]).split(".")[0] in EFFECT_MODULES:
                            say(where, f"getattr({ast.unparse(inner.args[0])}, "
                                       f"{ast.unparse(inner.args[1]) if len(inner.args) > 1 else '?'})")

        walk(root_node)
    return sorted(held)


def self_test():
    """Positive control first, then one planted violation per rule, each refused BY NAME.

    The body is wrapped so a control that DIES still speaks. The A revert trial planted
    `for entry in fixed:` -> `for entry in ():`: the fixed-root rows vanished, the control reading
    the first of them raised StopIteration, and the suite ended with no [FAIL] line at all — a row
    that reads as CONTROL-SILENT, which is indistinguishable from a rule nobody enforces. A
    traceback is not a control firing, so the wrapper prints the control that was in flight.
    """
    failures, ran = [], []
    try:
        return _self_test_body(failures, ran)
    except BaseException as exc:  # noqa: BLE001 - the suite must speak before it dies
        held = ran[-1] if ran else "<no control ran>"
        print(f"destinations --self-test [FAIL] the suite died after {held!r}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        for name, detail in failures:
            print(f"destinations --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"destinations --self-test: INCOMPLETE ({len(ran)} controls ran, {len(failures)} "
              f"failed before the suite died)", file=sys.stderr)
        raise


def _self_test_body(failures, ran):
    # Imported here, before anything uses them: a later `import shutil` inside this function makes
    # the name a local for the WHOLE function, so an earlier use raises UnboundLocalError — the same
    # shadowing trap as a local named like a module function. They stay out of the module's own
    # imports because this half of the file is the suite, and the module itself touches no
    # filesystem of its own.
    import shutil
    import tempfile

    def control(name, got, want):
        ran.append(name)
        if want not in str(got):
            failures.append((name, f"expected {want!r} in {str(got)[:400]!r}"))

    def equals(name, got, want):
        """A control whose expectation is the WHOLE answer, not a fragment of it.

        `control` asks `want in str(got)`, which is right for a refusal's name inside a longer
        message and wrong for a value: `'true'` is inside `'["false", "true"]'` and `'4=1+3'` is
        inside `'14=1+3'` (the round-3 review found that class). Every json-dumped answer below is
        asked for equality.
        """
        ran.append(name)
        if str(got) != str(want):
            failures.append((name, f"expected exactly {want!r}, got {str(got)[:400]!r}"))

    def clean(name, held):
        ran.append(name)
        if held:
            failures.append((name, f"expected nothing, got {held}"))

    def guarded(call):
        """The call's answer, or the exception as text.

        Without this a revert that removes a guard raises out of the control and the trial reads a
        traceback where it needed a named failure: a control that dies is not a control.
        """
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return f"RAISED {type(exc).__name__}: {exc}"

    def refusal(call):
        try:
            call()
        except Refused as exc:
            return str(exc)
        return ""

    # The declaration's own fixture, so the roots this suite judges are the ones a real run declares
    # rather than a shape invented here.
    FIXTURE = declare.fixture()
    root = str(pathlib.PurePosixPath(FIXTURE["destinations"][CLASSES[0]]).parent.parent)

    # A checkout that is a real repository, because the manifest judges the declared checkout's own
    # git configuration before any effect. Built as FILES — a `.git/` holding a `config` — and never
    # by running `git init`, which under a commit hook's exported GIT_DIR rewrites the author's real
    # `.git/config` (AGENTS.md's first trap).
    fixture_checkout = pathlib.Path(tempfile.mkdtemp(prefix="dest-checkout-", dir="/tmp"))
    (fixture_checkout / ".git").mkdir(parents=True, exist_ok=True)
    (fixture_checkout / ".githooks").mkdir(parents=True, exist_ok=True)
    # The fixture carries a hooksPath, because this repository does and S11's commit is meant to run
    # it. A fixture without one would let the manifest control below pass on the "no hooks path"
    # branch and never assert the resolved directory at all.
    (fixture_checkout / ".git" / "config").write_text(
        "[core]\n\tbare = false\n\trepositoryformatversion = 0\n\thooksPath = .githooks\n",
        encoding="utf-8")

    def fx_declaration(**over):
        held = dict(FIXTURE["destinations"])
        held["checkout"] = str(fixture_checkout)
        held.update(over)
        return {**FIXTURE, "destinations": held}

    def fx_env(**over):
        """The environment the RUN produces, built from the declaration like a run's own.

        It used to be built from a hardcoded `/srv/destinations/<class>/<name>`, which meant the
        suite judged values no declaration had produced: a root the declaration names and a value
        the fixture invents cannot disagree, because they were never the same answer. Every value
        is now the declared root of that name's class, with HOME the declared home, which is what
        `environment_for` hands each writer.
        """
        roots = fx_declaration()["destinations"]
        held = {override: roots.get(cls) for override, cls in class_of_override()[0].items()}
        held["HOME"] = declared_home(FIXTURE)
        held.update(over)
        return held

    def with_source(writer, text, call):
        """Run `call` with one writer's source replaced in a throwaway copy of the tree."""
        held_root = pathlib.Path(tempfile.mkdtemp(prefix="dest-channel-", dir="/tmp"))
        try:
            for row in writers():
                source = REPO / row["writer"]
                if not source.is_file():
                    continue
                target = held_root / row["writer"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text if row["writer"] == writer
                                  else source.read_text(encoding="utf-8", errors="replace"),
                                  encoding="utf-8")
            (held_root / "gates").mkdir(exist_ok=True)
            # `author_rows_absent` reads `files[]` from the tree it is given, so a tree that is to
            # answer for a real installation carries that file too.
            (held_root / "package.json").write_bytes((REPO / "package.json").read_bytes())
            return call(str(held_root))
        finally:
            shutil.rmtree(held_root, ignore_errors=True)

    # ---- the table itself ------------------------------------------------------------------------
    clean("the writer inventory is well formed and every class it names is a declared one",
          table_problems())
    clean("and every stated fallback is still the literal its writer's source carries",
          fidelity_problems())
    def declared_classes():
        held = set()
        for row in writers():
            held.update(entry["class"] for entry in row.get("destinations") or ())
            if row.get("writes_without_override"):
                held.add(row["writes_without_override"])
        return held

    clean("every declared destination class is written by some writer, so no class is a stale "
          "declaration", [name for name in CLASSES if name not in declared_classes()])
    clean("and no override is placed in two classes, since one variable has one value",
          sorted(class_of_override()[1]))
    control("the overrides are read from the table rather than named here",
            next(line for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                 if line.strip().startswith("return tuple(sorted({override")), "pairs()")
    control("the classes come from the declaration's schema rather than a list here",
            next(line for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                 if line.startswith("CLASSES = ")), "declare.DESTINATIONS")
    clean("the required overrides are the union of the table's own pairs, with nothing invented",
          sorted(set(required_overrides()) - {override for _w, override, _c in pairs()}))
    control("and update-state.py's nudge override is among them, since its fallback reads the "
            "password database", ", ".join(required_overrides()),
            "AGENT_BIOS_SESSION_DISTILL_STATE")

    def _row(data, writer):
        """The row for this writer, by NAME.

        These controls used to index `writers[0]`, which is the trap AGENTS.md names: the row at
        index 0 moved when the inventory became derived, and the control then died with a KeyError
        over a row that simply has no fallbacks instead of failing by name.
        """
        for row in data["writers"]:
            if row["writer"] == writer:
                return row
        raise AssertionError(f"self-test needs a {writer} row and the table has none")

    def with_table(mutate, call):
        """Run `call` with the table mutated, restoring it however the call ends."""
        held = json.loads(json.dumps(table()))
        try:
            mutate(_TABLE)
            return call()
        finally:
            _TABLE.clear()
            _TABLE.update(held)

    control("a writer naming a class the declaration does not hold is refused by name",
            with_table(lambda t: _row(t, "install.sh")["destinations"][0].__setitem__("class", "elsewhere"),
                       lambda: "; ".join(table_problems())),
            "DESTINATION_UNDECLARED install.sh")
    control("a class no writer writes under is refused as a stale declaration",
            with_table(lambda t: t.__setitem__(
                "writers", [r for r in t["writers"]
                            if not any(e["class"] == "nudge" for e in r.get("destinations") or ())]),
                       lambda: "; ".join(table_problems())),
            "DESTINATION_CLASS_UNWRITTEN nudge")
    control("one variable placed in two classes by two writers is refused: its single value cannot "
            "be inside two roots",
            with_table(lambda t: next(e for e in _row(t, "launch/shell_integration.py")["destinations"]
                                      if e["override"] == "AGENT_BIOS_STATE_DIR"
                                      ).__setitem__("class", "recovery"),
                       lambda: "; ".join(table_problems())),
            "OVERRIDE_CLASS_SPLIT AGENT_BIOS_STATE_DIR")
    # A writer may both take overrides and fix a root from HOME — install.sh does — so what is
    # refused is a fixed root with no class and a fixed root with nothing to show for it.
    def with_writer(writer, mutate):
        def apply(data):
            for row in data["writers"]:
                if row["writer"] == writer:
                    mutate(row)
        return apply

    control("a fixed destination root whose class is not in the vocabulary is refused",
            with_table(with_writer("install.sh",
                                   lambda row: row.__setitem__("writes_without_override", "nowhere")),
                       lambda: "; ".join(table_problems())),
            "FIXED_ROOT_UNCLASSED install.sh")
    control("and a fixed root with no derived lines to show is refused, so the row cannot assert a "
            "root nobody can check",
            with_table(with_writer("install.sh", lambda row: row.pop("fixed_roots", None)),
                       lambda: "; ".join(table_problems())),
            "FIXED_ROOT_UNSHOWN install.sh")
    clean("a writer that does both is accepted, because install.sh really does both",
          [p for p in table_problems() if "install.sh" in p])
    control("a row that names no class at all is refused",
            with_table(lambda t: _row(t, "git").__setitem__("writes_without_override", None),
                       lambda: "; ".join(table_problems())),
            "DESTINATION_UNDECLARED git")
    control("an empty writer set is refused, because a manifest over no writer confines nothing",
            with_table(lambda t: t.__setitem__("writers", []),
                       lambda: "; ".join(table_problems())),
            "WRITER_SET_EMPTY")
    control("a writer row without its own reason is refused",
            with_table(lambda t: _row(t, "install.sh").pop("$comment"),
                       lambda: "; ".join(table_problems())),
            "WRITER_UNREASONED install.sh")
    control("a fallback whose literal has left its writer's source is named with the file",
            with_table(lambda t: _row(t, "install.sh")["fallbacks"][0].__setitem__(
                           "literal", "${CLAUDE_CONFIG_DIR:-$HOME/.claude-gone}"),
                       lambda: "; ".join(fidelity_problems())),
            "FALLBACK_MOVED install.sh CLAUDE_CONFIG_DIR")
    control("and a row whose source file is gone is named too, rather than raising",
            with_table(lambda t: _row(t, "install.sh").__setitem__("fallback_source", "install-gone.sh"),
                       lambda: guarded(lambda: "; ".join(fidelity_problems()))),
            "WRITER_SOURCE_ABSENT install.sh")

    # ---- the resolution --------------------------------------------------------------------------
    rows = resolved_rows(fx_declaration(), fx_env(), scope="all")
    clean("with every override set inside its class's root, nothing refuses", resolution_problems(rows))
    clean("every writer in the inventory is answered for", [row["writer"] for row in writers()
                                                            if not any(r["writer"].startswith(row["writer"])
                                                                       for r in rows)])
    control("and every (writer, override) pair has its own row, so the count is the pair count plus "
            "the writers that take none",
            f'{len(rows)}', f'{len(pairs()) + len([r for r in writers() if r.get("writes_without_override")])}')
    clean("and every row says which class, which root and whether it is inside",
          [r["writer"] for r in rows if set(r) < {"class", "writer", "path", "root", "inside"}])
    control("a writer with several overrides is answered once per override, so one escaping value "
            "cannot hide behind a sibling in root",
            str(len([r for r in rows if r["writer"].startswith("install.sh [")])),
            str(len([e for e in next(r for r in writers() if r["writer"] == "install.sh")
                     ["destinations"]])
                + len([e for e in next(r for r in writers() if r["writer"] == "install.sh")
                       .get("fixed_roots") or []])))

    # OVERRIDE_MISSING: the case that writes into a real home through a fallback. After the
    # inversion the run BUILDS the environment, so an override is unset when the declaration names
    # no root for that name's class — the caller can no longer forget one, which is the point.
    unset = resolution_problems(resolved_rows(
        {**fx_declaration(), "destinations": {k: v for k, v
                                              in fx_declaration()["destinations"].items()
                                              if k != "nudge"}}, fx_env(), scope="all"))
    control("an unset override is refused before anything else, naming the writer and the variable",
            "; ".join(unset), "OVERRIDE_MISSING session-distill/update-state.py "
                              "[AGENT_BIOS_SESSION_DISTILL_STATE] AGENT_BIOS_SESSION_DISTILL_STATE")
    control("and the refusal says why a fallback is not an answer", "; ".join(unset),
            "a fallback the run did not declare")
    clean("an unset override is not also reported as an escape, since the path in the row is not "
          "the one the writer would use",
          [p for p in unset if "DESTINATION_OUTSIDE_ROOT" in p
           and "update-state" in p])
    control("the unset override is reported before any other refusal in the same resolution, "
            "because a path nobody will write to is not worth judging",
            "|".join(p.split()[0] for p in resolution_problems(resolved_rows(
                {**fx_declaration(), "destinations": {k: v for k, v
                                                      in fx_declaration()["destinations"].items()
                                                      if k != "nudge"}},
                fx_env(CODEX_HOME=f"{root}-other/codex"), scope="all"))),
            "OVERRIDE_MISSING")

    # DESTINATION_OUTSIDE_ROOT: an actual escape, under a second fixture root.
    escaped = resolution_problems(resolved_rows(
        fx_declaration(), fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=f"{root}-other/nudge/state.json"), scope="all"))
    # The inversion changes WHERE an escape can come from, and these controls follow it. A
    # per-override certificate is now the declared root of that name's class, so an override row
    # cannot escape its own root by construction — testing that it can would be testing a state the
    # code no longer has. What CAN escape is a fixed root computed from the given home (controlled
    # above, with the declaration narrowed), and what can disagree is the caller's claim about the
    # environment it will run with.
    control("a caller that says it will run with another value is refused by name, naming both the "
            "value it claims and the value the run produces",
            "; ".join(escaped),
            "DESTINATION_UNCERTIFIED session-distill/update-state.py "
            "[AGENT_BIOS_SESSION_DISTILL_STATE]")
    control("and the refusal says which path the certificate would have spoken for",
            "; ".join(escaped), "and the run produces")
    nudge_root = fx_declaration()["destinations"]["nudge"]
    clean("a caller whose claim MATCHES what the run produces is no disagreement",
          resolution_problems(resolved_rows(
              fx_declaration(), fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=nudge_root), scope="all")))
    clean("every override row's path IS its class root, which is why it cannot escape: the row "
          "carries no value the run did not produce",
          [r["writer"] for r in resolved_rows(fx_declaration(), {}, scope="all")
           if "[" in r["writer"] and "[fixed:" not in r["writer"]
           and r.get("path") and r["path"] != r["root"]])
    # The lexical rule the FIXED roots are judged by, asked of `inside` directly — the question is
    # the rule's, and the rows that used to carry it could only reach it through a value the run no
    # longer takes from the caller.
    equals("a path that IS the root is inside it, not an escape",
            json.dumps(inside(nudge_root, nudge_root)), "true")
    equals("a sibling whose name merely starts with the root's is an escape, not a child",
            json.dumps(inside(f"{nudge_root}-other/s.json", nudge_root)), "false")
    equals("a traversal that climbs out of the root is an escape even though its text begins "
            "inside", json.dumps(inside(f"{nudge_root}/../../out.json", nudge_root)), "false")
    equals("and one that climbs and comes back is inside, because the question is what the writer "
            "opens", json.dumps(inside(f"{nudge_root}/d/../s.json", nudge_root)), "true")
    control("a run that declares no root for a class is refused rather than defaulting to one",
            "; ".join(resolution_problems(resolved_rows(
                {"destinations": {k: v for k, v in fx_declaration()["destinations"].items()
                                  if k != "checkout"}}, fx_env(), scope="all"))),
            "DESTINATION_ROOT_ABSENT")

    # ---- the derived inventory ---------------------------------------------------------------
    #
    # The table was written from memory once and was wrong in both directions. These controls hold
    # the derivation itself, because the derivation is now what the table rests on.
    held_closure = closure()
    clean("the derivation and the table agree in both directions", inventory_problems())
    control("the closure is not empty, so an empty table could not pass unexamined",
            "yes" if len(held_closure) > 20 else f"only {len(held_closure)}", "yes")
    control("a row certifying an override its writer never reads is refused by name — the defect "
            "that shipped: install.sh assigns STATE_DIR from $HOME and reads no such variable",
            with_table(lambda t: _row(t, "install.sh")["destinations"].append(
                           {"override": "AGENT_BIOS_STATE_DIR", "class": "install_roots"}),
                       lambda: "; ".join(inventory_problems())),
            "INVENTORY_UNWRITTEN install.sh AGENT_BIOS_STATE_DIR")
    control("and a pair the tree carries with no row is refused by name",
            with_table(lambda t: _row(t, "install.sh").__setitem__(
                           "destinations",
                           [e for e in _row(t, "install.sh")["destinations"]
                            if e["override"] != "CLAUDE_CONFIG_DIR"]),
                       lambda: "; ".join(inventory_problems())),
            "INVENTORY_INCOMPLETE install.sh CLAUDE_CONFIG_DIR")
    control("a HOME-fixed root the derivation found and the row does not show is refused",
            with_table(lambda t: _row(t, "install.sh").pop("fixed_roots"),
                       lambda: "; ".join(table_problems())),
            "FIXED_ROOT_UNSHOWN install.sh")
    control("a fallback stated for an override the row carries no destination for is refused: the "
            "literal check passed over install.sh's AGENT_BIOS_STATE_DIR fallback because the "
            "literal really is in the file, as an assignment with no override in it",
            with_table(lambda t: _row(t, "install.sh")["fallbacks"].append(
                           {"override": "AGENT_BIOS_STATE_DIR",
                            "literal": "STATE_DIR=\"$HOME/.local/share/agent-bios\""}),
                       lambda: "; ".join(fidelity_problems())),
            "FALLBACK_UNPAIRED install.sh AGENT_BIOS_STATE_DIR")
    control("an author-side writer declared while files[] ships it is refused, so the declaration "
            "cannot excuse a writer the derivation can see",
            with_table(lambda t: _row(t, "install.sh").__setitem__("writer_scope", "author"),
                       lambda: "; ".join(inventory_problems())),
            "INVENTORY_SCOPE_WRONG install.sh")
    control("a forward declaration for a file that now exists is refused, so the derived closure "
            "takes over rather than the row standing unchecked",
            with_table(lambda t: _row(t, "session-distill/runlib/journal.py").__setitem__(
                           "writer_unwritten", True),
                       lambda: "; ".join(inventory_problems())),
            "INVENTORY_FORWARD_LANDED session-distill/runlib/journal.py")

    # Each of these five shapes was a wrong answer the derivation gave before it was corrected.
    def derived_for(writer):
        return sorted({e["override"] or "(fixed)" for e in held_closure if e["writer"] == writer})

    control("a read assigned through an INJECTED environment counts: instructions_install.py reads "
            "self.env.get(...), which a scan for os.environ.get called a non-reader",
            ",".join(derived_for("compose/instructions_install.py")),
            "(fixed),AGENT_BIOS_STATE_DIR,CLAUDE_CONFIG_DIR,CODEX_HOME,HOME,ZDOTDIR")
    # The author-side writer is addressed through the table's own declaration rather than by its
    # path: a shipped module naming an author-side path raises on the first packaged user, and
    # `check-package.sh` caught this line on exactly that rule.
    control("a read spread over several lines counts: the author-side writer's os.environ.get "
            "spans three of them",
            ",".join(derived_for(sorted(_author_writers())[0]) if _author_writers() else ["none"]),
            "AGENT_BIOS_SESSION_DISTILL_STATE")
    control("a runtime-chosen override key counts both ways: instructions_understand.py reads "
            "'CODEX_HOME' if host == 'codex' else 'CLAUDE_CONFIG_DIR'",
            ",".join(derived_for("compose/instructions_understand.py")),
            "CLAUDE_CONFIG_DIR,CODEX_HOME,HOME")
    control("a STRING that merely mentions an override is not a read of it: assemble.py's "
            "CLAUDE_VAR literal is a token it rewrites text with",
            "yes" if not any(e["line"] == 39 for e in held_closure
                             if e["writer"] == "compose/assemble.py") else "counted the literal",
            "yes")
    control("and a root that reaches a write THROUGH other names counts: shell_integration.py "
            "reads ZDOTDIR into self.zdotdir, builds self.startup from it, and writes that",
            "ZDOTDIR" if "ZDOTDIR" in derived_for("launch/shell_integration.py")
            else "missed the indirection", "ZDOTDIR")

    # ---- the environment a writer is GIVEN ---------------------------------------------------
    #
    # The inversion. Deriving every override that could redirect a write loses across a module
    # boundary, and what is not derived is not refused; a variable that is ABSENT cannot redirect
    # anything. These controls are about the environment this module PRODUCES — it executes nothing,
    # so what is asserted is the mapping, not a process.
    held_install = next(r for r in writers() if r["writer"] == "install.sh")
    given_install = environment_for(held_install, fx_declaration())
    equals("a writer is handed exactly the names its own row declares, and HOME",
            json.dumps(sorted(given_install)),
            json.dumps(sorted({e["override"] for e in held_install["destinations"]} | {"HOME"})))
    equals("and each value is the declared root of that name's class, not a value invented here",
            json.dumps(given_install["CLAUDE_CONFIG_DIR"]),
            json.dumps(fx_declaration()["destinations"]["install_roots"]))
    equals("HOME is what the run declares it hands, which is what every fixed root is computed "
            "from", json.dumps(given_install["HOME"]),
            json.dumps(declared_home(fx_declaration())))
    clean("a variable this writer reads and its row does not declare is ABSENT from what it is "
          "given — the whole mechanism, since what is not there cannot redirect a write",
          [name for name in ("AGENT_BIOS_UNINSTALL_ARCHIVE", "XDG_CACHE_HOME", "GIT_DIR",
                             "AGENT_LAUNCH_CONFIG", "AGENT_BIOS_INSTRUCTIONS_DIR")
           if name in given_install])
    equals("and the environment is the same answer for every writer: the names its row declares "
            "plus the isolation its row names, with no extras anywhere",
            json.dumps(sorted({name for row in writers()
                               for name in environment_for(row, fx_declaration())
                               if name != "HOME"
                               and name not in {e["override"]
                                                for e in row.get("destinations") or ()}
                               })),
            "[]")
    control("a run that declares no home is refused before any writer is handed anything",
            "; ".join(environment_problems({**FIXTURE, "environment": {}})),
            "ENVIRONMENT_HOME_UNDECLARED")
    clean("while the fixture run declares one", environment_problems(FIXTURE))
    control("and the manifest refuses without it rather than guessing the owner's home",
            refusal(lambda: document({**fx_declaration(), "environment": {}}, fx_env())),
            "ENVIRONMENT_HOME_UNDECLARED")

    # ---- the derivation as DISCLOSURE ---------------------------------------------------------
    control("what a writer reads and is not given is disclosed per row, and withholds "
            "certification: a fallback nobody declared points nowhere this manifest can speak for",
            "; ".join(resolution_problems([
                {"class": "install_roots", "writer": "x [CLAUDE_CONFIG_DIR]", "path": "/a",
                 "root": "/a", "inside": True, "reads_not_given": ["AGENT_BIOS_STATE_DIR"],
                 "certification": "withheld",
                 "why": "its source reads AGENT_BIOS_STATE_DIR, which the run does not hand it"}])),
            "DESTINATION_UNCERTIFIED x [CLAUDE_CONFIG_DIR]")
    clean("the real writers read nothing they are not given, once the excused pairs carry their "
          "reasons",
          [f"{row['writer']}: {row['reads_not_given']}" for row in
           resolved_rows(fx_declaration(), fx_env(), scope="all") if row.get("reads_not_given")])
    equals("and an excused pair is SHOWN with its reason rather than hidden, since the run does "
            "not hand it and something has to say why that is safe",
            json.dumps(sorted(excused_overrides("install.sh"))),
            '["AGENT_BIOS_UNINSTALL_ARCHIVE"]')
    equals("the disclosure is derived from the writer's own closure, so a name it stops reading "
            "stops being disclosed",
            json.dumps(reads_not_given("install.sh", {}, None)),
            json.dumps(sorted({e["override"] for e in closure(None)
                               if e["writer"] == "install.sh" and e["override"]}
                              - set(excused_overrides("install.sh")))))
    control("a writer handed nothing at all reads everything it reads ungiven, which is the "
            "disclosure firing rather than an empty answer",
            "yes" if reads_not_given("install.sh", {}, None) else "the disclosure is empty", "yes")

    # ---- the fixed roots, computed from the given HOME ----------------------------------------
    fixed_rows = [r for r in resolved_rows(fx_declaration(), fx_env(), scope="all") if "[fixed:" in r["writer"]]
    equals("every fixed-root row carries a path computed from the declared home, not the class "
            "root restated",
            json.dumps(sorted({r["certification"] for r in fixed_rows})), '["computed"]')
    control("and the home-rooted statement whose suffix cannot be read is BOUNDED by the home "
            "instead of being guessed at",
            fixed_destination({}, "/h", source_text="root = Path(pick(home, other()))")[1],
            "the home is its upper bound")
    held_state = next(r for r in fixed_rows if r["writer"].startswith("install.sh"))
    control("install.sh's own STATE_DIR is computed under the home it is given",
            held_state["path"],
            str(pathlib.Path(declared_home(fx_declaration())) / ".local/share/agent-bios"))
    control("and the manifest says how it was computed, so a reader can check it by hand",
            held_state["why"], "<home>/.local/share/agent-bios")
    control("a declaration whose class root does not contain what the writer computes is refused "
            "by name rather than certified",
            "; ".join(resolution_problems(resolved_rows(
                fx_declaration(install_roots="/srv/elsewhere"), fx_env(), scope="all"))),
            "DESTINATION_OUTSIDE_ROOT install.sh [fixed:")
    # The bounded BRANCH of `resolved_rows`, exercised through `resolved_rows` itself. It used to be
    # asked of `fixed_destination` and `_inside` separately, so the branch that decides between
    # "bounded is a certification" and "withheld" never ran at all (the round-3 review). Every
    # statement in this tree has a readable suffix, so the subject is PLANTED: install.sh's own
    # source, replaced in a throwaway tree, with a HOME-derived statement whose suffix is an
    # expression at exactly the line its row declares.
    held_line = next(entry["derived_at_line"] for row in writers()
                     if row["writer"] == "install.sh" for entry in row["fixed_roots"])
    unreadable_source = ("#\n" * (held_line - 1)) + "STATE_DIR=$(pick \"$HOME\" \"$(other)\")\n"

    def bounded_rows(declaration):
        return with_source("install.sh", unreadable_source,
                           lambda held_root: [r for r in resolved_rows(declaration, fx_env(),
                                                                       held_root, scope="all")
                                              if r["writer"].startswith("install.sh [fixed")])

    held_home = declared_home(fx_declaration())
    equals("a fixed root whose suffix cannot be read is BOUNDED by the home, and the bound is a "
           "certification where the class root contains the home",
           json.dumps([(r["certification"], r["path"]) for r in
                       bounded_rows(fx_declaration(install_roots=held_home))]),
           json.dumps([["bounded", held_home]]))
    equals("and where the class root is narrower than the home, certification is WITHHELD, because "
           "the unread suffix is exactly what would decide",
           json.dumps([r["certification"] for r in bounded_rows(
               fx_declaration(install_roots=f"{held_home}/.local/share/agent-bios"))]),
           '["withheld"]')
    control("and the withheld row says so in those words, so a reader knows which half of the "
            "question is open",
            "; ".join(resolution_problems(bounded_rows(
                fx_declaration(install_roots=f"{held_home}/.local/share/agent-bios")))),
            "narrower than the home")
    control("and a row that claims a fixed root while the run declares no home is uncertified, "
            "never certified at the root",
            "; ".join(p for p in resolution_problems(resolved_rows(
                {**fx_declaration(), "environment": {}}, fx_env(), scope="all")) if "UNCERTIFIED" in p),
            "the run declares no home")
    equals("a writer the run PASSES its root is certified by that, which is the preferred channel "
            "because an argument cannot be inherited",
            json.dumps(sorted({r["certification"] for r in resolved_rows(fx_declaration(), fx_env(), scope="all")
                               if r["writer"] in ("git", "session-distill/runlib/journal.py")})),
            '["argument"]')
    control("and the row says so, naming what passes it",
            next(r["why"] for r in resolved_rows(fx_declaration(), fx_env(), scope="all") if r["writer"] == "git"),
            "the run passes this writer its root")
    control("a fixed-root row that says neither how its root is reached is a table defect",
            "; ".join(with_table(lambda held: [row.pop("root_from") for row in held["writers"]
                                               if row["writer"] == "install.sh"],
                                 inventory_problems)),
            "INVENTORY_ROOT_FROM_UNSTATED install.sh")
    control("and one that says HOME and shows no line to derive it at is another",
            "; ".join(with_table(lambda held: [row.pop("fixed_roots") for row in held["writers"]
                                               if row["writer"] == "install.sh"],
                                 inventory_problems)),
            "INVENTORY_FIXED_ROOT_UNSHOWN install.sh")
    control("a fixed-root row for a writer this tree does not have is reported, which the pair-only "
            "legs could not see",
            "; ".join(with_table(lambda held: held["writers"].append(
                {"writer": "compose/no-such-writer.py", "destinations": [],
                 "writes_without_override": "install_roots", "root_from": "home",
                 "fixed_roots": [{"derived_at_line": 1, "root": "X = Path.home() / 'x'"}],
                 "$comment": "planted"}), inventory_problems)),
            "INVENTORY_FIXED_ROOT_ABSENT compose/no-such-writer.py")
    control("the line the destination is computed from is read from the WRITER's source, not from "
            "the table's 160-character excerpt of it",
            "yes" if (source_line("compose/instructions_install.py", 327) or "").endswith(
                ".expanduser()") else "the excerpt is what was read", "yes")
    control("and a multi-line statement is read to where its parentheses balance, because one line "
            "of it establishes nothing",
            fixed_destination({}, "/h", source_text=source_line("launch/agent-launch.py", 8314))[1],
            "<home>/.local/share/agent-bios/corpus-status.json")

    # ---- the four channels an environment cannot close ---------------------------------------
    #
    # Scrubbing is the mechanism and it is not sufficient: a writer can reach a path without reading
    # a variable. Each channel is derived from the writer's own source, and each control plants its
    # subject rather than waiting for a real writer to acquire one.
    clean("no writer in this tree reaches a path through a channel the run cannot answer for",
          channel_problems())
    control("and the check says so about a non-empty set of writers, since an empty one would pass "
            "unexamined", "named" if "CHANNEL_NO_WRITERS_READ" in "; ".join(
                channel_problems(str(pathlib.Path(tempfile.mkdtemp(prefix="dest-nowriter-",
                                                                   dir="/tmp"))))) else "silent",
            "named")

    # The password database: the channel that put a run in the owner's real home during a commit
    # hook. Proved BY SOURCE in both directions — the defect and its licence — because the only
    # other way to prove it is to run a writer against a real home and look at what appeared.
    control("a writer that reads the password database is refused by name: the run cannot redirect "
            "what `getpwuid` answers",
            "; ".join(with_source("compose/prune-backups.py",
                                  "import pwd, os\nroot = pwd.getpwuid(os.getuid()).pw_dir\n",
                                  channel_problems)),
            "CHANNEL_PASSWORD_DATABASE compose/prune-backups.py:2")
    equals("and the licence for one is held against the source: the read must sit behind the "
            "absence of a name the run always gives",
            json.dumps([guarded_by("home = env.get('HOME')\nif home is None:\n    import pwd\n"
                                   "    home = pwd.getpwuid(os.getuid()).pw_dir\n", 4, "HOME"),
                        guarded_by("home = env.get('XDG_HOME')\nif home is None:\n    import pwd\n"
                                   "    home = pwd.getpwuid(os.getuid()).pw_dir\n", 4, "HOME"),
                        guarded_by("import pwd\nhome = pwd.getpwuid(os.getuid()).pw_dir\n", 2,
                                   "HOME")]),
            "[true, false, false]")
    control("so a row licensing a line its source does not guard is refused, naming the guard it "
            "claimed",
            "; ".join(with_table(
                lambda held: [row.__setitem__("channels", {"password_database": [
                    {"line": 2, "guarded_by": "HOME", "reason": "planted"}]})
                    for row in held["writers"] if row["writer"] == "compose/prune-backups.py"],
                lambda: with_source("compose/prune-backups.py",
                                    "import pwd, os\nroot = pwd.getpwuid(os.getuid()).pw_dir\n",
                                    channel_problems))),
            "which its source does not show guarding it")
    control("and a licence with no reason licenses nothing either",
            "; ".join(with_table(
                lambda held: [row.__setitem__("channels", {"password_database": [
                    {"line": 4, "guarded_by": "HOME"}]})
                    for row in held["writers"] if row["writer"] == "compose/prune-backups.py"],
                lambda: with_source("compose/prune-backups.py",
                                    "import os, pwd\nhome = os.environ.get('HOME')\n"
                                    "if home is None:\n    home = pwd.getpwuid(os.getuid()).pw_dir\n",
                                    channel_problems))),
            "CHANNEL_PASSWORD_DATABASE compose/prune-backups.py:4")
    clean("while the real licence in this tree holds: the read is behind `if home is None` where "
          "home came from the HOME the run hands it",
          [p for p in channel_problems() if "PASSWORD_DATABASE" in p])

    # A login shell restores exactly what was scrubbed.
    control("a child login shell is refused by name, because a profile re-read puts the user's own "
            "variables back",
            "; ".join(with_source("wrappers/codex-run.sh",
                                  "#!/bin/sh\nexec zsh -l -c \"$1\"\n", channel_problems)),
            "CHANNEL_LOGIN_SHELL wrappers/codex-run.sh:2")
    control("and `--login` spelled in full is the same channel",
            "; ".join(with_source("wrappers/codex-run.sh",
                                  "#!/bin/sh\nbash --login -c \"$1\"\n", channel_problems)),
            "CHANNEL_LOGIN_SHELL wrappers/codex-run.sh:2")

    # An absolute literal and a path argument are STATED, with their reasons, keyed to the token.
    control("an absolute literal a row does not name is reported with the literal itself",
            "; ".join(with_source("compose/instructions_setup.py",
                                  "DEST = '/Library/Application Support/x'\n", channel_problems)),
            "CHANNEL_UNSTATED compose/instructions_setup.py absolute_literals: "
            "/Library/Application")
    control("a statement whose token the source no longer shows is stale, not approval",
            "; ".join(with_table(
                lambda held: [row["channels"]["absolute_literals"]["tokens"].append("/srv/gone")
                              for row in held["writers"]
                              if row["writer"] == "wrappers/codex_frame_filter.py"],
                channel_problems)),
            "CHANNEL_STALE wrappers/codex_frame_filter.py absolute_literals: the row states "
            "/srv/gone")
    control("and a statement with tokens and no reason is refused: naming a channel is not "
            "answering for it",
            "; ".join(with_table(
                lambda held: [row["channels"]["absolute_literals"].pop("reason")
                              for row in held["writers"]
                              if row["writer"] == "wrappers/codex_frame_filter.py"],
                channel_problems)),
            "CHANNEL_UNREASONED wrappers/codex_frame_filter.py absolute_literals")
    control("a path option a row does not record is reported, because an argument is the channel "
            "the run PREFERS and it has to know the writer takes one",
            "; ".join(with_source("compose/instructions_setup.py",
                                  "parser.add_argument('--state-dir')\n", channel_problems)),
            "CHANNEL_UNSTATED compose/instructions_setup.py path_arguments: --state-dir")
    # KEYED, not positional, and non-empty before anything is indexed: sorting the live rows and
    # asserting element [0] ignored every other row and raised instead of failing by name when the
    # set was empty (the round-4 review).
    held_arguments = {row["writer"]: tuple(row["channels"]["path_arguments"]["tokens"])
                      for row in writers()
                      if (row.get("channels") or {}).get("path_arguments")}
    control("the tree really declares path-argument channels, so the assertions below are not over "
            "an empty set", "yes" if held_arguments else "the set is empty", "yes")
    equals("and every option in this tree is recorded, keyed by its writer, so a row this control "
            "does not name fails it rather than hiding behind a sorted first element",
            json.dumps({name: list(tokens) for name, tokens in sorted(held_arguments.items())}),
            json.dumps({name: list(tokens) for name, tokens
                        in sorted(CHANNEL_STATED_ARGUMENTS.items())}))
    clean("and each one carries the reason it is preferred, in its own row",
          [name for name, row in ((row["writer"], row) for row in writers())
           if (row.get("channels") or {}).get("path_arguments")
           and not str(row["channels"]["path_arguments"].get("reason") or "").strip()])

    # ---- the release's scope, as a fact the rows carry -----------------------------------------
    #
    # Release 1's S11 writes the declared checkout and makes the git commit, and runs nothing else
    # (D-20261112-2cf1c4). The six findings that were deferred with that decision are all about
    # writers it never invokes, so the scope has to be checkable rather than asserted in a record.
    release_rows = resolved_rows(fx_declaration(), fx_env())
    equals("the rows release 1 may invoke are exactly the stages that write files — git is not "
            "among them, because this release executes none",
            json.dumps(sorted({r["writer"].split(" [")[0] for r in release_rows
                               if r["certification"] != RELEASE_1_UNINVOKED})),
            json.dumps(sorted(["session-distill/runlib/inventory.py",
                               "session-distill/runlib/journal.py",
                               "session-distill/runlib/recovery.py",
                               "session-distill/runlib/stage_apply.py",
                               "session-distill/runlib/stage_close.py"])))
    clean("and NO row outside that set comes back certified — the installer, the launcher, "
          "update-state and the personal layers are named, never confined-and-allowed, so a "
          "deferred finding about one of them cannot become reachable without this failing",
          [r["writer"] for r in release_rows
           if r["certification"] != RELEASE_1_UNINVOKED
           and r["writer"].split(" [")[0] not in ("session-distill/runlib/inventory.py",
                                                  "session-distill/runlib/journal.py",
                                                  "session-distill/runlib/recovery.py",
                                                  "session-distill/runlib/stage_apply.py",
                                                  "session-distill/runlib/stage_close.py")])
    # The permitted ENTRIES, asked independently of the writer-name allowlist: the scope control
    # above strips the `[OVERRIDE]` suffix, so a row for a writer in the set was accepted whatever
    # destination it carried — which is how `inventory.py [HOME]` came back certified at the
    # personal-layers root (the round-4 review). This asks the (class, override) pairs themselves.
    equals("the destination ENTRIES release 1 may write are exactly the checkout-and-state set, "
            "asked by class and override rather than by the writer's name",
            json.dumps(sorted({(r["class"], r["writer"].split(" [")[1][:-1]
                               if " [" in r["writer"] else "")
                              for r in release_rows
                              if r["certification"] not in (RELEASE_1_UNINVOKED,
                                                            READ_NOT_WRITTEN)})),
            json.dumps(sorted([("checkout", ""), ("runtime_state", ""), ("recovery", "")])))
    clean("so no destination resting on an environment OVERRIDE is certified in this release at "
          "all: every writer it invokes is passed its root",
          [r["writer"] for r in release_rows
           if " [" in r["writer"] and "[fixed:" not in r["writer"]
           and r["certification"] not in (RELEASE_1_UNINVOKED, READ_NOT_WRITTEN)])
    equals("and the owner's home is a READ with no path, not a destination this release may write",
            json.dumps([(r["certification"], r["path"]) for r in release_rows
                        if r["class"] == "personal_layers"
                        and r["certification"] == READ_NOT_WRITTEN]),
            json.dumps([[READ_NOT_WRITTEN, None]]))
    control("and the row says so in its own words rather than leaving the reader to the table",
            next((r["why"] for r in release_rows if r["certification"] == READ_NOT_WRITTEN),
                 "<no read_not_written row in the release's scope>"),
            "nothing of this writer's is written under it")
    # The claim check survived the narrowing because it is asked of the produced MAPPING: with no
    # override-rooted row left in the release, a check keyed on such a row would have gone silent.
    control("a caller that says it will run with another HOME is refused by name even though no "
            "destination rests on HOME any more",
            "; ".join(claim_problems(fx_declaration(), {"HOME": "/srv/elsewhere"})),
            "ENVIRONMENT_CLAIM_DIFFERS")
    control("and the refusal names the writer whose environment it would have been",
            "; ".join(claim_problems(fx_declaration(), {"HOME": "/srv/elsewhere"})),
            "session-distill/runlib/stage_apply.py HOME")
    clean("while a name NO writer the release invokes is handed is not claimed over at all: the "
          "check speaks for the mapping the run produces, not for every name a caller mentions",
          claim_problems(fx_declaration(), {"GIT_CONFIG_GLOBAL": "/dev/zero"}))
    clean("while a claim that matches what the run produces is no disagreement",
          claim_problems(fx_declaration(), fx_env()))
    clean("every named row says WHY in its own words rather than leaving the reader to the decision "
          "record", [r["writer"] for r in release_rows
                     if r["certification"] == RELEASE_1_UNINVOKED
                     and "release-1" not in str(r.get("why"))])
    clean("and no named row carries a path, so nothing downstream can read one and write there",
          [r["writer"] for r in release_rows
           if r["certification"] == RELEASE_1_UNINVOKED and r.get("path") is not None])
    # The subject is TAKEN FROM THE TABLE rather than written out: a literal author-side path in a
    # shipped module is refused by the package gate, and a name copied here would go stale the day
    # the row is renamed.
    held_uninvoked = next(row["writer"] for row in writers()
                          if not row.get("release_1_invoked") and row.get("destinations")
                          and not row.get("writer_unwritten"))
    equals("the fact is the TABLE's, so flipping one row's declaration moves it into the release "
            "and back out",
            json.dumps(with_table(
                lambda held: _row(held, held_uninvoked).__setitem__("release_1_invoked", True),
                lambda: [r["certification"] for r
                         in resolved_rows(fx_declaration(), fx_env())
                         if r["writer"].startswith(held_uninvoked)
                         and r["certification"] == RELEASE_1_UNINVOKED])),
            json.dumps([]))
    equals("the scope is per DESTINATION and not per writer, because S11 is itself one of the "
            "writers: the apply stage's checkout row is answered and its personal-layer row is "
            "named, in the same release",
            json.dumps([(r["class"], r["certification"]) for r in release_rows
                        if r["writer"].startswith("session-distill/runlib/stage_apply.py")]),
            json.dumps([["personal_layers", RELEASE_1_UNINVOKED], ["checkout", "forward"]]))
    equals("an entry that says nothing inherits its writer's answer, so a row cannot be narrowed "
            "by the writer's silence",
            json.dumps([entry_invoked_in_release_1({"release_1_invoked": True}, {}),
                        entry_invoked_in_release_1({"release_1_invoked": False}, {}),
                        entry_invoked_in_release_1({"release_1_invoked": True},
                                                   {"release_1_invoked": False})]),
            "[true, false, false]")
    # What the narrowing BUYS the declaration: the classes only uninvoked writers write no longer
    # need a root. The lead asked what `environment.home` is still needed for, and this is the other
    # half of that answer — the home is required, the class roots for those writers are not.
    # A read needs no root, so it is not one of the classes the declaration must carry: this set is
    # what `required` in S0's schema is held against.
    held_classes = {entry.get("class") for row in writers()
                    for entry in list(row.get("destinations") or ())
                    + list(row.get("fixed_roots") or ())
                    if entry_invoked_in_release_1(row, entry) and not entry.get("read_only")}
    held_classes |= {row.get("writes_without_override") for row in writers()
                     if row.get("release_1_invoked")}
    narrowed = {k: v for k, v in fx_declaration()["destinations"].items()
                if k in held_classes}
    clean("a declaration carrying roots only for the classes release 1 writes resolves with no "
          "refusal, so the owner no longer has to name a root for a writer S11 will not run",
          resolution_problems(resolved_rows({**fx_declaration(), "destinations": narrowed},
                                            fx_env())))
    # Through the SCHEMA as well as the resolution: a clean resolution says the code accepts the
    # narrowed declaration and nothing about whether S0 would admit it, and the schema still
    # required all seven roots (the round-4 review).
    held_declaration = {**fx_declaration(), "destinations": narrowed}
    equals("the narrowed declaration passes S0's own schema, so the release can actually be "
            "declared and not only resolved",
            json.dumps(validate.violations(declare.VALIDATOR, held_declaration)), "[]")
    equals("and the schema's required classes ARE the table's release-1 classes, so the two cannot "
            "drift apart",
            json.dumps(sorted(declare.DESTINATIONS_REQUIRED)),
            json.dumps(sorted(name for name in held_classes if name)))
    clean("while the vocabulary stays the whole set, so a wider declaration is still typed and "
          "still judged rather than becoming undeclared",
          [name for name in ("install_roots", "personal_layers", "launcher_shell_integration",
                             "nudge") if name not in declare.DESTINATIONS])
    control("while a declaration missing a class release 1 DOES write is still refused by the "
            "schema, so the narrowing did not make the requirement empty",
            "; ".join(str(held) for held in validate.violations(
                declare.VALIDATOR,
                {**fx_declaration(),
                 "destinations": {k: v for k, v in narrowed.items() if k != "checkout"}})),
            "checkout")
    control("and the same declaration at the WIDER scope refuses by name, which is what says the "
            "narrowing is the release's and not the mechanism's",
            "; ".join(resolution_problems(resolved_rows(
                {**fx_declaration(), "destinations": narrowed}, fx_env(), scope="all"))),
            "DESTINATION_ROOT_ABSENT")
    clean("and the same row, unflipped, is named by that state — without this the control above "
          "would pass over a row that was never named at all",
          [r["certification"] for r in release_rows
           if r["writer"].startswith(held_uninvoked)
           and r["certification"] != RELEASE_1_UNINVOKED])
    control("an unknown scope is refused rather than read as one of the two, because a typo that "
            "resolved everything would widen the release silently",
            refusal(lambda: resolved_rows(fx_declaration(), fx_env(), scope="releaes_1")),
            "RESOLUTION_SCOPE_UNKNOWN")
    equals("`environment.home` is still required, and these are what needs it: the HOME handed to "
            "every writer the release DOES invoke",
            json.dumps(sorted({r["writer"].split(" [")[0] for r in release_rows
                               if r["certification"] != RELEASE_1_UNINVOKED
                               and "HOME" in environment_for(
                                   next(w for w in writers()
                                        if w["writer"] == r["writer"].split(" [")[0]),
                                   fx_declaration())})),
            json.dumps(sorted(["session-distill/runlib/inventory.py",
                               "session-distill/runlib/journal.py",
                               "session-distill/runlib/recovery.py",
                               "session-distill/runlib/stage_apply.py",
                               "session-distill/runlib/stage_close.py"])))
    control("and a declaration without it is refused, so the narrowing did not make the home "
            "optional", "; ".join(environment_problems({"destinations": {}})),
            "ENVIRONMENT_HOME_UNDECLARED")

    # ---- git is not this release's to run ------------------------------------------------------
    #
    # The configuration policy, the hooks certificate, the hook-refusal contract and the child
    # environment all stood here, with their controls. Release 1's S11 executes no git
    # (`D-20261113-f22b7d`), so what is left to assert is that nothing of git's is reachable from
    # the release's own scope — which the scope controls above do, by name — and that the manifest
    # the stage reads carries no certificate speaking for a command nobody runs.
    clean("the manifest carries no git certificate, since a certificate for a command this release "
          "never runs would be read as one that was checked",
          [name for name in ("git", "hook_refusal")
           if name in document(fx_declaration(), fx_env())])
    equals("and the git row is NAMED by the release's scope, like every other writer it does not "
            "invoke",
            json.dumps([(r["class"], r["certification"]) for r in release_rows
                        if r["writer"] == "git"]),
            json.dumps([["checkout", RELEASE_1_UNINVOKED]]))
    clean("so the produced environment for it carries no GIT name at all: there is no isolation to "
          "hand a command that is not run, and the declared HOME is handed to every row alike",
          [name for name in environment_for(
              next(row for row in writers() if row["writer"] == "git"), fx_declaration())
           if name.startswith("GIT")])

    # ---- the two install layouts ----------------------------------------------------------------
    #
    # A packaged install has no `gates/` and no author-scope writer source. The manifest used to
    # refuse WRITER_SOURCE_ABSENT there, over `session-distill/update-state.py`, which npm does not
    # ship: a refusal no packaged user can act on, invisible from every clone. Found by the WP-21
    # review. These controls build both layouts as file trees and ask the real functions.
    layout_root = pathlib.Path(tempfile.mkdtemp(prefix="dest-layout-", dir="/tmp"))
    try:
        author_writer = sorted(_author_writers())[0] if _author_writers() else None
        # The package layout: the shipped file set only. `files[]` decides it, so the fixture cannot
        # drift from what npm actually packs.
        packed = json.loads((REPO / "package.json").read_text(encoding="utf-8")).get("files") or []
        pack = layout_root / "package"
        (pack / "session-distill" / "tables").mkdir(parents=True)
        (pack / "package.json").write_bytes((REPO / "package.json").read_bytes())
        # EVERY script `files[]` ships, not only the writer sources the table happens to name.
        # The thin fixture is what let the "a packaged install produces a manifest" control pass
        # while the thing it claimed to test was broken: with the global `REPO` wired into the
        # derivation, `inventory_problems` scanned the AUTHOR'S CHECKOUT, agreed with the table
        # there, and never looked at the fixture at all. Scanning the fixture required the fixture
        # to be a real package — npm installs the whole of `files[]`, and the author-scope writer
        # is the only thing it leaves out.
        for entry in packed:
            source = REPO / entry
            held_sources = ([source] if source.is_file()
                            else sorted(p for p in source.rglob("*") if p.is_file()))
            for held_path in held_sources:
                if held_path.suffix not in (".py", ".sh", ".zsh"):
                    continue
                target = pack / held_path.relative_to(REPO)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(held_path.read_bytes())
        # What a package DECLARES, written here because npm's own pack writes it: `files[]` carries
        # `provenance.json`, `check-publish.sh --stamp` writes it at prepack with the commit the
        # tarball holds, and removes it afterwards — so it is in a published package and in no
        # checkout. A fixture that models a package carries it, like one that models a checkout
        # carries `gates/`.
        (pack / LAYOUT_DECLARATION).write_text(
            json.dumps({"commit": "0" * 40, "committedAt": "2026-11-12T00:00:00Z", "dirty": False}),
            encoding="utf-8")
        control("the package layout is recognised by what a publish DECLARES, not by a directory "
                "that happens to be missing", install_layout(pack), "package")
        control("and a checkout is recognised by the author tree it declares itself with",
                install_layout(REPO), "checkout")
        bare = layout_root / "bare"
        (bare / "session-distill").mkdir(parents=True)
        control("a tree that declares neither is not guessed at: an incomplete copy used to BE a "
                "package, and every excuse the layout carries was granted to it",
                str(install_layout(bare)), "None")
        control("and the manifest refuses over it by name rather than defaulting",
                "; ".join(layout_problems(bare)), f"LAYOUT_UNDECLARED {bare}")
        both = layout_root / "both"
        (both / "gates").mkdir(parents=True)
        (both / LAYOUT_DECLARATION).write_text("{}", encoding="utf-8")
        control("a tree carrying both declarations is refused too, since which excuses apply "
                "cannot be established", "; ".join(layout_problems(both)),
                f"LAYOUT_AMBIGUOUS {both}")
        clean("while the real checkout and the package fixture each declare exactly one",
              layout_problems(REPO) + layout_problems(pack))
        # Every row carries exactly one certification state, including the two that only a
        # refused resolution has: `not_installed` for a writer this install does not have, and
        # `unset` for an override the declaration names no root for. The document is produced only
        # when nothing refuses, so these are asked of `resolved_rows` where they exist.
        equals("a writer this install does not have carries `not_installed` rather than an absent "
               "field",
               json.dumps(sorted({str(r.get("certification"))
                                  for r in resolved_rows(fx_declaration(), fx_env(), str(pack), scope="all")
                                  if r.get("not_installed")})),
               '["not_installed"]')
        equals("and an override the declaration names no root for carries `unset`",
               json.dumps(sorted({str(r.get("certification")) for r in resolved_rows(
                   {**fx_declaration(), "destinations": {k: v for k, v
                                                         in fx_declaration()["destinations"].items()
                                                         if k != "nudge"}}, fx_env(), str(pack), scope="all")
                                  if r.get("unset")})),
               '["unset"]')
        control("the author-scope writer is named as not installed there",
                ", ".join(author_rows_absent(pack)), author_writer or "none")
        clean("and its absence is not a fidelity failure in that layout",
              [p for p in fidelity_problems(pack) if "WRITER_SOURCE_ABSENT" in p])
        held_rows = resolved_rows(fx_declaration(), fx_env(), root=pack, scope="all")
        control("its row is recorded rather than dropped, so the manifest does not read as though "
                "no such writer existed",
                "; ".join(r.get("not_installed", "") for r in held_rows
                          if r["writer"] == author_writer),
                "author-side writer, not present in this install")
        clean("and that row is not judged for escape, since a writer that is not there writes "
              "nowhere",
              [p for p in resolution_problems(held_rows) if author_writer and author_writer in p])
        held_doc = guarded(lambda: document(fx_declaration(), fx_env(), root=pack))
        control("so a packaged install produces a manifest at all",
                "dict" if isinstance(held_doc, dict) else str(held_doc)[:160], "dict")
        control("and the manifest says which layout it was written in",
                held_doc.get("layout") if isinstance(held_doc, dict) else "none", "package")
        # The derivation must read the root it was GIVEN. It read the module's own checkout through
        # a global instead, so every answer about a packaged install was an answer about the
        # author's tree — and the control above passed while what it named was broken.
        pack_writers = {entry["writer"] for entry in closure(pack)}
        repo_writers = {entry["writer"] for entry in closure(REPO)}
        control("the closure scanned the package tree rather than nothing",
                "scanned" if len(pack_writers) > 3 else f"only {sorted(pack_writers)}", "scanned")
        control("and the set is the PACKAGE's: the author-scope writer is in the checkout's "
                "closure and not in the package's, which is the difference npm makes",
                "differs" if author_writer and author_writer in repo_writers
                and author_writer not in pack_writers
                else f"the same answer for both roots ({author_writer})", "differs")
        clean("the inventory agrees with the table in the packaged layout too, because a writer "
              "this install does not have certifies nothing", inventory_problems(pack))
        # The checkout half: the same absence IS a failure where the source is audited.
        checkout = layout_root / "checkout"
        (checkout / "gates").mkdir(parents=True)
        (checkout / "session-distill").mkdir(parents=True)
        (checkout / "package.json").write_bytes((REPO / "package.json").read_bytes())
        control("while in a CHECKOUT the author-scope writer's absence is a defect, so the "
                "exclusion is the layout's and not a blanket excuse",
                "; ".join(inventory_problems(checkout)), "INVENTORY_SCOPE_ABSENT")
        control("in a checkout, an author-scope writer whose file is missing fails by name, "
                "because that is where the fallback literal is held against its source",
                "; ".join(fidelity_problems(checkout)), "WRITER_SOURCE_ABSENT")
    finally:
        shutil.rmtree(layout_root, ignore_errors=True)

    # Lexical containment is half the answer: `os.open` follows symlinks, so a path inside the root
    # can open a file outside it. `links_problem` is for a caller that cannot open with O_NOFOLLOW;
    # `journal.Storage.append` does open that way, which is the stronger half.
    # Plain names, no aliases: `dispatch.py`'s source-shape rule refuses `import os as _os` in a
    # shipped module because renaming an executing module is how an effect hides from a scan, and it
    # caught this block. The same blindness is a finding against this unit's own AST check.
    link_root = pathlib.Path(tempfile.mkdtemp(prefix="dest-link-", dir="/tmp"))
    try:
        (link_root / "declared" / "deep").mkdir(parents=True)
        (link_root / "outside").mkdir()
        os.symlink(link_root / "outside" / "f.json", link_root / "declared" / "f.json")
        os.symlink(link_root / "outside", link_root / "declared" / "away")
        declared = link_root / "declared"
        control("a path that IS a symlink is lexically inside and named by links_problem",
                f'{_inside(declared / "f.json", declared)}:'
                f'{(links_problem(declared / "f.json", declared) or "none")[:20]}',
                "True:DESTINATION_SYMLINK")
        control("a symlinked DIRECTORY on the way is named too, since a link anywhere puts the "
                "write outside the root",
                (links_problem(declared / "away" / "f.json", declared) or "none"),
                "DESTINATION_SYMLINK")
        clean("an ordinary path under the root carries no link problem",
              [links_problem(declared / "deep" / "f.json", declared)]
              if links_problem(declared / "deep" / "f.json", declared) else [])
        control("and a path outside the root is still reported as outside, not as a link, and not "
                "by raising",
                guarded(lambda: links_problem(link_root / "outside" / "f.json", declared) or "none"),
                "DESTINATION_OUTSIDE_ROOT")
        control("the docstring says why this is the weaker half, so a caller does not read it as "
                "the whole answer",
                inside.__doc__, "O_NOFOLLOW")
    finally:
        shutil.rmtree(link_root, ignore_errors=True)

    # ---- the document and the write --------------------------------------------------------------
    # `document` refuses on an inventory problem too, so a mutation to the DERIVATION makes this
    # call raise. Guarded, so the suite names the inventory failure instead of dying here: four
    # revert rows reported CONTROL-SILENT with an empty FAIL list because this one line stopped the
    # run before the controls that would have named the defect.
    doc_or_refusal = guarded(lambda: document(fx_declaration(), fx_env()))
    doc = doc_or_refusal if isinstance(doc_or_refusal, dict) else {
        "resolved": [], "overrides_required": [], "refused": doc_or_refusal}
    control("the document is produced at all, rather than refusing over its own inventory",
            "dict" if isinstance(doc_or_refusal, dict) else str(doc_or_refusal)[:200], "dict")
    # Equality, and of the rows' own keys rather than of a count: `'32' in '132'` passed the
    # substring helper (the round-5 review). The claim is that the document drops and adds no row of
    # the resolution it was built from, so the keys are what is compared.
    equals("the document carries exactly the resolved rows of the RELEASE's scope — the rows above "
           "are the wider scope, and the document is what S11 reads",
           json.dumps(sorted((r["writer"], r["class"]) for r in doc["resolved"])),
           json.dumps(sorted((r["writer"], r["class"])
                             for r in resolved_rows(fx_declaration(), fx_env()))))
    equals("and that set is not empty", json.dumps(bool(doc["resolved"])), "true")
    equals("and it carries the release's scope with the decision that set it, so a reader of the "
            "manifest alone can say which writers this release may not invoke",
            json.dumps([doc["release_scope"]["scope"], doc["release_scope"]["decision"],
                        len(doc["release_scope"]["uninvoked"])]),
            json.dumps(["release_1", "D-20261112-2cf1c4",
                        len([r for r in doc["resolved"]
                             if r.get("certification") == RELEASE_1_UNINVOKED])]))
    control("and the overrides the run must set", json.dumps(doc["overrides_required"]),
            "AGENT_BIOS_SESSION_DISTILL_STATE")
    # `inside` is None where there is nothing to confine — a writer this install does not have, and
    # a forward declaration whose file does not exist. Those rows carry their own state and are not
    # read as escapes; `False` is an escape and is what this asks about.
    clean("every row in the written manifest carries a named certification, so a later stage reads "
          "a state rather than inferring one from a missing field",
          [r["writer"] for r in doc["resolved"] if not r.get("certification")])
    equals("and the states are exactly the declared vocabulary, with none invented and none left "
           "to be inferred from an absent field — at the release's scope `computed` does not "
           "appear, because the only writer with a computed root is one release 1 never invokes",
           json.dumps(sorted({str(r.get("certification")) for r in doc["resolved"]})),
           '["argument", "forward", "not_invoked_in_release_1", "read_not_written"]')
    equals("and at the WIDER scope the same rows are certified rather than named, so the release "
           "narrows what S11 may invoke without retiring the confinement that judges the rest "
           "(this control and the one above were the same assertion written twice until round 3; "
           "they now ask the two scopes)",
           json.dumps(sorted({str(r.get("certification")) for r
                              in resolved_rows(fx_declaration(), fx_env(), scope="all")})),
           '["argument", "computed", "forward", "given", "read_not_written"]')
    clean("with every row that HAS a path inside its root",
          [r["writer"] for r in doc["resolved"] if r["inside"] is False])
    equals("and the rows with nothing to confine say which they are, by a named state, rather "
            "than reading as escapes or as certified",
            json.dumps(sorted({str(r.get("certification") or r.get("not_installed"))
                               for r in doc["resolved"] if r["inside"] is None})),
            '["forward", "not_invoked_in_release_1", "read_not_written"]')
    control("a document over an environment the caller claims and the run does not produce is "
            "refused instead of written — asked of the produced MAPPING, so the narrowing that made "
            "release 1's only override-rooted row a read did not take the check with it",
            refusal(lambda: document(fx_declaration(),
                                     fx_env(HOME=f"{root}-other/home"))),
            "ENVIRONMENT_CLAIM_DIFFERS")
    control("and so is one over a mutated table, so the manifest cannot be written from a broken "
            "inventory",
            with_table(lambda t: t.__setitem__("writers", []),
                       lambda: refusal(lambda: document(fx_declaration(), fx_env()))),
            "WRITER_SET_EMPTY")

    held_root = pathlib.Path(tempfile.mkdtemp(prefix="dest-", dir="/tmp"))
    try:
        run_dir = held_root / "r1"
        declare.create(run_dir, fx_declaration())
        declaration = records.read_json(run_dir / "run.json")
        try:
            _stage, written = write(run_dir, declaration, fx_env())
        except Refused as exc:
            written = {"problem": str(exc)}
        control("the manifest is written inside the run", str((run_dir / OUTPUT).is_file()), "True")
        clean("and holds what the document held",
              [] if (run_dir / OUTPUT).is_file()
              and records.read_json(run_dir / OUTPUT).get("resolved") == written.get("resolved")
              else [f"{written}"])
        # Guarded for the same reason as the document above: when the manifest refuses, there is no
        # stage record to read, and reading it kills the suite instead of letting the controls below
        # name the refusal.
        record = guarded(lambda: records.read_json(records.record_path(run_dir, "S11")))
        control("registered with the stage, so a later stage can read its staleness",
                json.dumps([o.get("artifact") for o in record.get("outputs") or []])
                if isinstance(record, dict) else str(record)[:200], OUTPUT)
        # Nothing is written when anything refuses: the escape case must leave no manifest at all.
        other = held_root / "r2"
        declare.create(other, fx_declaration())
        said = refusal(lambda: write(other, declaration, fx_env(HOME=f"{root}-other/home")))
        control("a refused resolution writes nothing", said, "ENVIRONMENT_CLAIM_DIFFERS")
        clean("not even an empty manifest, and no stage record either",
              [name for name in (OUTPUT, "records") if (other / name).exists() and name == OUTPUT]
              + ([f"an S11 record exists"] if records.record_path(other, "S11").exists() else []))
        clean("and the escape target itself was never touched: it is a fixture path and has no file",
              [] if not pathlib.Path(f"{root}-other/home").exists()
              else [f"{root}-other/home exists"])
    finally:
        shutil.rmtree(held_root, ignore_errors=True)

    # This module performs no effect, which is the whole reason it is the first commit. Asserted on
    # its own source — over the RUNTIME code only, since the self-test builds fixtures — and the
    # scope is now a real scope rather than an accident. Three corrections, each one a way the old
    # check could be walked past:
    #
    #  * it read the whole file, so the only thing keeping it green was that the fixture code used
    #    ALIASED imports (`import os as _os`): removing the aliases, which `dispatch.py`'s source
    #    rule demands, made the check fire on fixtures. A check whose silence depends on a rename is
    #    not a check, and the review of this unit names the same blindness.
    #  * an alias is now refused outright in the runtime code, by comparing the module's own import
    #    bindings against the watched names: `import os as _o` then `_o.system(...)` passed.
    #  * `getattr(os, "system")(...)` passed too, because the call's function is a `getattr` node
    #    whose unparse starts with neither `os` nor `subprocess`.
    import ast

    effects_in = effect_audit            # the module's own function, not a second copy here
    own_source = pathlib.Path(__file__).read_text(encoding="utf-8")
    spawners = effects_in(own_source)
    control("the no-effects check fires on a PLAIN call",
            "; ".join(effects_in("import os\ndef f():\n    os.system('x')\n")), "os.system")
    control("and on an ALIASED import, which is what kept the old check green",
            "; ".join(effects_in("import os as _o\ndef f():\n    _o.system('x')\n")),
            "os.system")
    control("and names the alias itself, since the rename is the hiding place",
            "; ".join(effects_in("import subprocess as sp\n")),
            "import subprocess as sp")
    control("and on a getattr form, which the review of this unit named",
            "; ".join(effects_in("import os\ndef f():\n    getattr(os, 'system')('x')\n")),
            "getattr(os, 'system')")
    # Round 2: five shapes the audit passed. Each is the real form, not a near miss.
    control("and on `__import__`, whose call names no watched module at its first component",
            "; ".join(effects_in("def f():\n    __import__('os').system('x')\n")),
            "__import__ reaches a module this audit cannot name")
    control("and on importlib, for the same reason",
            "; ".join(effects_in("import importlib\ndef f():\n"
                                 "    importlib.import_module('os').system('x')\n")),
            "importlib.import_module reaches a module this audit cannot name")
    control("and on a filesystem write that names no module at all",
            "; ".join(effects_in("import pathlib\ndef f():\n"
                                 "    pathlib.Path('a').write_text('x')\n")),
            "pathlib.Path('a').write_text")
    control("and on an open for writing, by its mode",
            "; ".join(effects_in("def f():\n    open('a', 'w').close()\n")),
            "open(mode='w')")
    control("and on an open whose mode this audit cannot read, rather than assuming a read",
            "; ".join(effects_in("def f(m):\n    open('a', m).close()\n")),
            "a mode this audit cannot read")
    control("an effect in `main` is reported, and `main` is a real entry point: "
            "`python3 runlib/destinations.py` runs it",
            "; ".join(effects_in("import os\ndef main(argv):\n    os.system('x')\n")),
            "os.system (in main)")
    control("and so is one in a `self_test` a runtime function calls outright",
            "; ".join(effects_in("import os\ndef self_test():\n    os.symlink('a', 'b')\n"
                                 "def run():\n    return self_test()\n")),
            "os.symlink (in self_test)")
    # Round 4: a class BODY runs at definition time, and a guard the audit cannot prove is not a
    # guard.
    control("a statement in a class BODY is runtime code — it runs at definition time and there is "
            "no function to reach it through",
            "; ".join(effects_in("class K:\n    open('/outside', 'w')\n"
                                 "    def m(self):\n        pass\n")),
            "open(mode='w') (in K)")
    control("and it is reported under the class's own name, so the reader knows where to look",
            "; ".join(effects_in("class Held:\n    import os\n    os.system('x')\n")),
            "(in Held)")
    control("a compound test mentioning the flag is NOT a self-test guard, so both halves are "
            "scanned: trusting it skipped real runtime code",
            "; ".join(effects_in("import sys\ndef main():\n"
                                 "    if '--self-test' not in sys.argv and True:\n"
                                 "        open('/x', 'w')\n")),
            "open(mode='w') (in main)")
    control("and so is a membership test on something other than argv, by the same rule",
            "; ".join(effects_in("def main(held):\n"
                                 "    if '--self-test' in held.flags():\n"
                                 "        open('/x', 'w')\n")),
            "open(mode='w') (in main)")
    equals("the two predicates the audit DOES prove are the plain membership tests, and they are "
            "read in opposite directions",
            json.dumps([_self_test_branch(ast.parse(
                "if '--self-test' in sys.argv:\n    pass\n").body[0]),
                        _self_test_branch(ast.parse(
                            "if '--self-test' not in sys.argv:\n    pass\n").body[0]),
                        _self_test_branch(ast.parse(
                            "if '--self-test' not in sys.argv and True:\n    pass\n").body[0])]),
            json.dumps(["orelse", "body", None]))
    clean("while a `self_test` reached only through the flag's own branch is fixtures, which is "
          "reachability deciding the exclusion rather than the name",
          effects_in("import os\ndef self_test():\n    os.symlink('a', 'b')\n"
                     "def main(argv):\n"
                     "    if '--self-test' in argv:\n        return self_test()\n    return 0\n"))
    clean("while the allowed path helpers are not effects",
          effects_in("import os\ndef f():\n    return os.path.normpath('a')\n"))
    clean("and a read is not a write",
          effects_in("def f():\n    return open('a').read()\n"))
    # An audit that scanned nothing reports nothing: the scope is asserted, not assumed.
    # A class's methods are code, and a branch whose test is NEGATED is the runtime half.
    control("an effect in a class METHOD the reachable code names is reported, with the method",
            "; ".join(effects_in("import os\nclass Writer:\n    def go(self):\n"
                                 "        os.symlink('a', 'b')\n"
                                 "def main():\n    return Writer().go()\n")),
            "os.symlink (in Writer.go)")
    clean("while a class nothing reachable names is out of scope, so the rule is reachability and "
          "not 'every method everywhere'",
          effects_in("import os\nclass Writer:\n    def go(self):\n"
                     "        os.symlink('a', 'b')\n"
                     "def main():\n    return 1\n"))
    equals("and the method is in the scanned scope rather than merely reachable, which is the half "
            "that mattered: the effect sits in the body",
            json.dumps(effect_scope("import os\nclass Writer:\n    def go(self):\n"
                                    "        os.symlink('a', 'b')\n"
                                    "def main():\n    return Writer().go()\n")),
            '["<module>", "Writer.go", "main"]')
    control("an effect behind `if \'--self-test\' NOT in argv` is reported: that branch is the "
            "runtime half, and the skip followed the wrong one",
            "; ".join(effects_in("import os, sys\ndef run():\n"
                                 "    if '--self-test' not in sys.argv:\n"
                                 "        os.symlink('a', 'b')\n")),
            "os.symlink (in run)")
    clean("while the flag's own branch is still fixtures, which is what the skip is for",
          effects_in("import os, sys\ndef run():\n    if '--self-test' in sys.argv:\n"
                     "        os.symlink('a', 'b')\n"))
    control("and the half NOT guarded by the flag is scanned either way round",
            "; ".join(effects_in("import os, sys\ndef run():\n"
                                 "    if '--self-test' in sys.argv:\n        pass\n"
                                 "    else:\n        os.symlink('a', 'b')\n")),
            "os.symlink (in run)")
    # Round 5: the flag must be the flag, and a definition executes more than its body.
    equals("a guard on a flag that merely CONTAINS `--self-test` guards nothing this audit knows",
           json.dumps(effects_in("def main(argv):\n    if '--self-test-other' in argv:\n"
                                 "        open('/outside', 'w')\n")),
           json.dumps(["open(mode='w') (in main)"]))
    equals("a class nested in a class runs its body at definition time",
           json.dumps(effects_in("class Outer:\n    class Inner:\n"
                                 "        open('/outside', 'w')\n")),
           json.dumps(["open(mode='w') (in Outer.Inner)"]))
    equals("a default argument runs when the method is DEFINED, called or not",
           json.dumps(effects_in("class Held:\n    def never_called(self, x=open('/outside', 'w')):\n"
                                 "        return x\n")),
           json.dumps(["open(mode='w') (in Held.never_called definition)"]))
    equals("so does a decorator on a top-level function nobody calls from the suite alone",
           json.dumps(effects_in("import os\n@os.system('x')\ndef self_test():\n    pass\n")),
           json.dumps(["os.system (in self_test definition)"]))
    equals("and a class's bases",
           json.dumps(effects_in("import os\nclass Held(os.system('x')):\n    pass\n")),
           json.dumps(["os.system (in Held definition)"]))
    # Membership, asserted as a membership rather than as a substring of a dumped list.
    equals("the audit scanned this module's own entry point",
            json.dumps("main" in effect_scope(own_source)), "true")
    equals("and its top level",
            json.dumps("<module>" in effect_scope(own_source)), "true")
    equals("and the resolution path a destination row is judged by",
            json.dumps("resolved_rows" in effect_scope(own_source)), "true")
    clean("this module runs nothing and spawns nothing: the code that confines writes cannot itself "
          "be a writer", spawners)
    # The dying-control wrapper, and the audit rule it needed. A suite split across two functions
    # is still the suite: `_self_test_body` is reached only from `self_test`, so it is test-only by
    # reachability and its fixture building is not a module effect.
    control("the suite's own body is out of the audit's scope, because the suite alone calls it",
            "out" if "_self_test_body" not in effect_scope(own_source) else "in", "out")
    equals("and the rule is reachability, not the name: a body a RUNTIME function calls is in",
            json.dumps(effect_scope("def self_test():\n    pass\n"
                                    "def _self_test_body(f, r):\n    pass\n"
                                    "def run():\n    return _self_test_body([], [])\n")),
            '["<module>", "_self_test_body", "run"]')
    control("the wrapper prints the control that was in flight, so a suite that dies is not read "
            "as a rule nobody enforces",
            next((line.strip() for line in own_source.splitlines()
                  if "the suite died after" in line), "<no such line>"),
            'print(f"destinations --self-test [FAIL] the suite died after {held!r}: "')
    control("and it says INCOMPLETE rather than OK, since the controls after the death never ran",
            "yes" if "destinations --self-test: INCOMPLETE" in own_source else "no", "yes")
    control("and the only file it writes is its own manifest",
            ", ".join(sorted({ast.unparse(node.func)
                              for node in ast.walk(ast.parse(own_source))
                              if isinstance(node, ast.Call)
                              and ast.unparse(node.func).startswith("records.write_")})),
            "records.write_json")

    shutil.rmtree(fixture_checkout, ignore_errors=True)
    print(f"destinations --self-test: {'FAILED' if failures else 'OK'} ({len(ran)} controls: the "
          f"writer inventory held against its writers' own sources, OVERRIDE_MISSING before any "
          f"escape judgement, an escape under a second fixture root, the root itself and a "
          f"name-prefix sibling, traversal in both directions, and a refused resolution writing "
          f"nothing)")
    for name, detail in failures:
        print(f"destinations --self-test [FAIL] {name}: {detail}")
    return 1 if failures else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    print(json.dumps({"classes": list(CLASSES), "overrides_required": list(required_overrides()),
                      "writers": [{"writer": r["writer"], "class": r["class"],
                                   "overrides": r.get("overrides") or []} for r in writers()]},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
