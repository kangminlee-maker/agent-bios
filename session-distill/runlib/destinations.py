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
from runlib import declare, records  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
REPO = HERE.parent
TABLE_PATH = HERE / "tables" / "destinations.json"
OUTPUT = "destinations.resolved.json"
# The declared classes come from the declaration's own schema, through declare.py, so this module
# cannot disagree with what a run is allowed to declare.
CLASSES = declare.DESTINATIONS
_TABLE = {}


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


def install_layout(root=None):
    """`"checkout"` or `"package"`, decided by whether the author-side tree is present.

    The npm package carries `session-distill/` and `package.json` and NOT `gates/`, so the presence
    of the author-side tree is what separates the two layouts. It matters here because an
    author-scope writer's SOURCE is not shipped: `fidelity_problems` reads every `fallback_source`,
    so in a packaged install the manifest failed `WRITER_SOURCE_ABSENT` over
    `session-distill/update-state.py` — a refusal that no packaged user can act on, and one no
    check run from a clone can see. Found by the WP-21 review.
    """
    return "checkout" if (pathlib.Path(root or REPO) / "gates").is_dir() else "package"


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


def resolved_rows(declaration, environ, root=None):
    """One row per writer: `{class, writer, path, root, inside}` as N#4 names it.

    `path` is what the writer will actually write under, taken from the environment the run hands it
    — never from this process's own environment unless the caller passes it.
    """
    roots = (declaration or {}).get("destinations") or {}
    rows = []
    absent = set(author_rows_absent(root))
    for row in writers():
        if row["writer"] in absent:
            # Named, not certified: the writer is not in this install, so it writes nowhere. Saying
            # so in the manifest is the point — a silent omission would read as "no such writer".
            rows.append({"class": row.get("writes_without_override")
                         or (row.get("destinations") or [{}])[0].get("class"),
                         "writer": row["writer"], "path": None, "root": None, "inside": None,
                         "not_installed": "author-side writer, not present in this install"})
            continue
        # One row per (writer, override), so a single escaping value cannot hide behind a sibling
        # of the same writer that is in root.
        for entry in row.get("destinations") or ():
            override, cls = entry.get("override"), entry.get("class")
            root, value = roots.get(cls), environ.get(override)
            if not value:
                rows.append({"class": cls, "writer": f"{row['writer']} [{override}]", "path": None,
                             "root": root, "inside": False, "unset": [override]})
                continue
            rows.append({"class": cls, "writer": f"{row['writer']} [{override}]", "path": value,
                         "root": root, "inside": bool(root) and _inside(value, root)})
        if row.get("writes_without_override"):
            cls = row["writes_without_override"]
            root = roots.get(cls)
            rows.append({"class": cls, "writer": row["writer"], "path": root, "root": root,
                         "inside": bool(root)})
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
        if not row.get("root"):
            problems.append(f"DESTINATION_ROOT_ABSENT {row['writer']}: the run declares no root for "
                            f"class {row['class']}")
            continue
        if not row["inside"]:
            problems.append(f"DESTINATION_OUTSIDE_ROOT {row['writer']}: {row['path']} is not inside "
                            f"{row['root']}")
    return problems


def problems(declaration, environ, root=None):
    """Everything wrong, table and resolution together. Empty means apply may take its first effect."""
    held = table_problems(root) + fidelity_problems(root) + inventory_problems(root)
    if held:
        return held
    return resolution_problems(resolved_rows(declaration, environ, root))


def document(declaration, environ, root=None):
    """The manifest `apply` writes before any effect, or Refused naming what stops it."""
    rows = resolved_rows(declaration, environ, root)
    # The derived inventory is part of the manifest's own correctness, not a separate audit: a
    # destination the tree writes and the table does not carry is exactly the hole this manifest
    # exists to close, so `apply` refuses before any effect rather than recording a partial answer.
    held = (table_problems(root) + fidelity_problems(root) + inventory_problems(root)
            + resolution_problems(rows))
    if held:
        raise Refused("; ".join(held))
    return {"stage": "S11", "resolved": rows,
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


def _effect_reachable(tree):
    """The top-level function names a runtime entry point can reach.

    Roots are the module's top level and every top-level function except `self_test`; an edge
    through a branch whose test names `--self-test` is not followed, which is what keeps a suite's
    own fixture building out of the answer without excluding the suite by name.
    """
    functions = {node.name: node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

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
                if isinstance(child, ast.If) and "--self-test" in ast.unparse(child.test):
                    for part in child.orelse:   # the unguarded half still counts
                        walk(part)
                    continue
                walk(child)

        walk(node)
        return held

    frontier = {name for name in functions if name != "self_test"}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            frontier |= called_in(node) & set(functions)
    held = set()
    while frontier:
        name = frontier.pop()
        if name in held or name not in functions:
            continue
        held.add(name)
        frontier |= called_in(functions[name]) & set(functions)
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
                if isinstance(child, ast.If) and "--self-test" in ast.unparse(child.test):
                    for part in child.orelse:
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
    # Imported once, at the top: a later `import shutil` inside this function makes the name a
    # local for the WHOLE function, so an earlier use raises UnboundLocalError. That is the same
    # shadowing trap as a local named like a module function.
    import shutil
    import tempfile

    failures, ran = [], []

    def control(name, got, want):
        ran.append(name)
        if want not in str(got):
            failures.append((name, f"expected {want!r} in {str(got)[:400]!r}"))

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

    def fx_declaration(**over):
        held = dict(FIXTURE["destinations"])
        held.update(over)
        return {**FIXTURE, "destinations": held}

    def fx_env(**over):
        held = {override: f"{root}/destinations/{cls}/{override.lower()}"
                for override, cls in class_of_override()[0].items()}
        held.update(over)
        return held

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
    rows = resolved_rows(fx_declaration(), fx_env())
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
            str(len([r for r in rows if r["writer"].startswith("install.sh [")])), "3")

    # OVERRIDE_MISSING: the case that writes into a real home through a fallback.
    unset = resolution_problems(resolved_rows(fx_declaration(),
                                              {k: v for k, v in fx_env().items()
                                               if k != "AGENT_BIOS_SESSION_DISTILL_STATE"}))
    control("an unset override is refused before anything else, naming the writer and the variable",
            "; ".join(unset), "OVERRIDE_MISSING session-distill/update-state.py "
                              "[AGENT_BIOS_SESSION_DISTILL_STATE] AGENT_BIOS_SESSION_DISTILL_STATE")
    control("and the refusal says why a fallback is not an answer", "; ".join(unset),
            "a fallback the run did not declare")
    clean("an unset override is not also reported as an escape, since the path in the row is not "
          "the one the writer would use",
          [p for p in unset if "DESTINATION_OUTSIDE_ROOT" in p
           and "update-state" in p])
    control("the unset override is reported before any escape in the same resolution",
            "|".join(p.split()[0] for p in resolution_problems(resolved_rows(
                fx_declaration(),
                {**{k: v for k, v in fx_env().items() if k != "ZDOTDIR"},
                 "CODEX_HOME": f"{root}-other/codex"}))),
            "OVERRIDE_MISSING")

    # DESTINATION_OUTSIDE_ROOT: an actual escape, under a second fixture root.
    escaped = resolution_problems(resolved_rows(
        fx_declaration(), fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=f"{root}-other/nudge/state.json")))
    control("a destination under a second root is refused by name with both paths",
            "; ".join(escaped), f"DESTINATION_OUTSIDE_ROOT session-distill/update-state.py "
                                f"[AGENT_BIOS_SESSION_DISTILL_STATE]: {root}-other/nudge/state.json")
    control("and the refusal names the root it is not inside", "; ".join(escaped),
            f"not inside {root}/destinations/nudge")
    clean("a path that IS the root is inside it, not an escape",
          resolution_problems(resolved_rows(
              fx_declaration(), fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=f"{root}/destinations/nudge"))))
    control("a sibling directory whose name merely starts with the root's is an escape, not a child",
            "; ".join(resolution_problems(resolved_rows(
                fx_declaration(),
                fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=f"{root}/destinations/nudge-other/s.json")))),
            "DESTINATION_OUTSIDE_ROOT")
    control("a traversal that climbs out of the root is an escape even though its text begins inside",
            "; ".join(resolution_problems(resolved_rows(
                fx_declaration(),
                fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=f"{root}/destinations/nudge/../../out.json")))),
            "DESTINATION_OUTSIDE_ROOT")
    clean("and one that climbs and comes back is inside, because the question is what the writer opens",
          resolution_problems(resolved_rows(
              fx_declaration(),
              fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=f"{root}/destinations/nudge/d/../s.json"))))
    control("a run that declares no root for a class is refused rather than defaulting to one",
            "; ".join(resolution_problems(resolved_rows(
                {"destinations": {k: v for k, v in fx_declaration()["destinations"].items()
                                  if k != "checkout"}}, fx_env()))),
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
        control("the package layout is recognised without `gates/`", install_layout(pack), "package")
        control("and a checkout is recognised by its presence",
                install_layout(REPO), "checkout")
        control("the author-scope writer is named as not installed there",
                ", ".join(author_rows_absent(pack)), author_writer or "none")
        clean("and its absence is not a fidelity failure in that layout",
              [p for p in fidelity_problems(pack) if "WRITER_SOURCE_ABSENT" in p])
        held_rows = resolved_rows(fx_declaration(), fx_env(), root=pack)
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
    control("the document carries one resolved row per answered writer",
            str(len(doc["resolved"])), str(len(rows)))
    control("and the overrides the run must set", json.dumps(doc["overrides_required"]),
            "AGENT_BIOS_SESSION_DISTILL_STATE")
    clean("with every row inside its root", [r["writer"] for r in doc["resolved"] if not r["inside"]])
    control("a document over an escaping environment is refused instead of written",
            refusal(lambda: document(fx_declaration(),
                                     fx_env(CODEX_HOME=f"{root}-other/codex"))),
            "DESTINATION_OUTSIDE_ROOT")
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
        said = refusal(lambda: write(other, declaration, fx_env(CODEX_HOME=f"{root}-other/codex")))
        control("a refused resolution writes nothing", said, "DESTINATION_OUTSIDE_ROOT")
        clean("not even an empty manifest, and no stage record either",
              [name for name in (OUTPUT, "records") if (other / name).exists() and name == OUTPUT]
              + ([f"an S11 record exists"] if records.record_path(other, "S11").exists() else []))
        clean("and the escape target itself was never touched: it is a fixture path and has no file",
              [] if not pathlib.Path(f"{root}-other/codex").exists() else ["/elsewhere/codex exists"])
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
    control("the audit scanned this module's own entry point",
            json.dumps(effect_scope(own_source)), '"main"')
    control("and its top level", json.dumps(effect_scope(own_source)), '"<module>"')
    control("and the resolution path a destination row is judged by",
            json.dumps(effect_scope(own_source)), '"resolved_rows"')
    clean("this module runs nothing and spawns nothing: the code that confines writes cannot itself "
          "be a writer", spawners)
    control("and the only file it writes is its own manifest",
            ", ".join(sorted({ast.unparse(node.func)
                              for node in ast.walk(ast.parse(own_source))
                              if isinstance(node, ast.Call)
                              and ast.unparse(node.func).startswith("records.write_")})),
            "records.write_json")

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
