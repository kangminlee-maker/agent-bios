#!/usr/bin/env python3
"""Every dependency the SHIPPED session-distill driver reaches for is declared in DEPENDENCIES.md.

An unshipped runtime path is invisible from a clone and fatal on npm (`check-package.sh`'s
reason for existing). An UNDECLARED dependency is the same failure one layer out: the code
works on the author's machine, where `jsonschema` and `zstd` happen to be installed, and
raises on the first user who has neither — with nothing in the inventory to have told them.

Two derivations, both from the code:

* **imports** — every module imported by `session-distill/distill.py` or `session-distill/runlib/*.py`
  that is neither in the standard library nor local to the driver. Decidable and complete.
* **programs** — every command name given as a STRING LITERAL to `subprocess.run`, `.Popen`,
  `.check_output`, `.check_call`, `.call` or `shutil.which`. Decidable, and deliberately NOT
  complete: the host CLIs the dispatcher runs arrive as resolved paths from configuration, so no
  scan can see them. Their declarations are held by review, not here. A gate that claimed
  completeness over them would be claiming more than it checks.

Declared means: the name appears in a DEPENDENCIES.md table cell, as the tool it is. Two names
reach the file under their product names rather than their binaries, which `ALIASES` carries.

    python3 gates/check-driver-dependencies.py            # --check is the default
    python3 gates/check-driver-dependencies.py --self-test
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
DRIVER = "session-distill/distill.py"
RUNLIB = "session-distill/runlib"
GRAMMAR = "session-distill/grammar"
INVENTORY = "DEPENDENCIES.md"

# Local to the driver: imported by module name because the driver puts its own directory on the
# path. None is a dependency anyone installs. `grammar` holds the owner-line grammar the stages
# import (WP-20), so its modules are subjects too: a local package nobody scans is a hole.
LOCAL = {"runlib", "distill", "grammar"}

# The runner calls whose first literal argument is a command name, as (module, names) PAIRS rather
# than two independent sets. Qualified on purpose: a bare `run("S6", ...)` of some object's own
# method is not a program, and an unqualified scan read one as `S6`. Pairs rather than the product
# of two sets, because the product admits calls nobody makes (`os.run`, `subprocess.system`) and
# because each module's runners take their command differently, which the scan has to know.
RUNNER_PAIRS = {
    "subprocess": {"run", "Popen", "check_output", "check_call", "call"},
    "shutil": {"which"},
    # `os.system` and `os.popen` hand one STRING to a shell. They were outside the scan entirely:
    # the driver could have run anything through either and this gate reported a clean tree,
    # because it looked only for an argv vector.
    "os": {"system", "popen"},
}
# The modules whose runners take a string command rather than an argv vector: the program is its
# first word.
STRING_COMMAND_MODULES = {"os"}
RUNNER_QUALIFIERS = set(RUNNER_PAIRS)
RUNNERS = {name for names in RUNNER_PAIRS.values() for name in names}

# A binary whose inventory row names the product. The row is the declaration; this maps the name
# the code uses to the words the row uses, and nothing else.
ALIASES = {"claude": "Claude Code", "codex": "Codex CLI"}

# Names that are never a dependency: the interpreter already running, and a path, not a command.
NOT_A_DEPENDENCY = {"sys.executable", "python3", ""}


def subjects(root: pathlib.Path) -> list[pathlib.Path]:
    """The shipped driver files, sorted. Empty is a failure, never a clean run."""
    found = [root / DRIVER, *sorted((root / RUNLIB).glob("*.py")), *sorted((root / GRAMMAR).glob("*.py"))]
    return [path for path in found if path.is_file()]


def _runner_bindings(tree):
    """(bound name -> the module it IS, bound name -> the (module, runner) it is) in this file.

    Spelled out because ordinary Python hides a program three ways and the scan saw none of them
    (review Y #3): `import subprocess as sp` binds the module under another name, `from subprocess
    import run` binds the function with no qualifier at all, and either can be renamed with `as`.
    A scan matching only the literal text `subprocess.run` reports a clean tree while the driver
    runs whatever it likes.

    Each binding keeps the module it came from, rather than being collected into one anonymous set:
    with runners declared per module, `sp.system(...)` and `os.run(...)` must read as nothing, and a
    set of names cannot tell them from the pairs that do exist."""
    modules, functions = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in RUNNER_QUALIFIERS:
                    modules[alias.asname or root] = root
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            root = node.module.split(".")[0]
            if root not in RUNNER_QUALIFIERS:
                continue
            for alias in node.names:
                if alias.name in RUNNER_PAIRS[root]:
                    functions[alias.asname or alias.name] = (root, alias.name)
                else:
                    modules[alias.asname or alias.name] = root
    return modules, functions


def _argv_of(call):
    """The command vector a runner call was given, positionally or as `args=`.

    `subprocess.run(args=[...])` is the documented spelling of the same call, and reading only
    `call.args` let it through."""
    if call.args:
        return call.args[0]
    for keyword in call.keywords:
        if keyword.arg in ("args", "cmd"):
            return keyword.value
    return None


def _runner_of(call, modules, functions):
    """The MODULE whose runner this call is, or None: `subprocess`, `shutil`, `os`.

    The module, not a yes/no, because it decides how the command is written — an argv vector for
    `subprocess`, one shell string for `os`."""
    func = call.func
    if isinstance(func, ast.Attribute):
        base = func.value
        qualifier = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
        module = modules.get(qualifier)
        if module is not None and func.attr in RUNNER_PAIRS[module]:
            return module
        return None
    if isinstance(func, ast.Name):
        found = functions.get(func.id)
        return found[0] if found is not None else None
    return None


def derive(paths: list[pathlib.Path], root: pathlib.Path) -> tuple[dict, dict, dict]:
    """(third-party imports, literal program names, unresolved shell commands).

    The first two map each name to the files that reach for it. The third maps a site to the call
    it could not read: a shell runner whose command is not a literal string names a program this
    scan cannot derive, and silence there would be the same hole the string runners were in."""
    imports: dict[str, set[str]] = {}
    programs: dict[str, set[str]] = {}
    unresolved: dict[str, str] = {}
    standard = set(sys.stdlib_module_names)
    for path in paths:
        rel = str(path.relative_to(root))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules, functions = _runner_bindings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                names = []
            for name in names:
                if name not in standard and name not in LOCAL:
                    imports.setdefault(name, set()).add(rel)
            if not isinstance(node, ast.Call):
                continue
            module = _runner_of(node, modules, functions)
            if module is None:
                continue
            if module in STRING_COMMAND_MODULES:
                # One shell string: the program is its first word. A command this scan cannot read
                # is REPORTED rather than passed over — an f-string or a variable here is exactly
                # how a program would stay undeclared once the spelling is in scope at all.
                written = node.args[0] if node.args else None
                if isinstance(written, ast.Constant) and isinstance(written.value, str):
                    words = written.value.split()
                    command = words[0].split("/")[-1] if words else ""
                    if command and command not in NOT_A_DEPENDENCY:
                        programs.setdefault(command, set()).add(rel)
                else:
                    unresolved[f"{rel}:{node.lineno}"] = ast.unparse(node)[:80]
                continue
            first = _argv_of(node)
            if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
                first = first.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                command = first.value.split("/")[-1]
                if command and command not in NOT_A_DEPENDENCY:
                    programs.setdefault(command, set()).add(rel)
    return imports, programs, unresolved


def declared(inventory_text: str, name: str) -> bool:
    """Whether DEPENDENCIES.md declares this name, in a table row."""
    rows = [line for line in inventory_text.splitlines() if line.startswith("|")]
    needles = [f"`{name}`", ALIASES.get(name, "")]
    return any(needle and needle in row for row in rows for needle in needles)


def check(root: pathlib.Path = REPO) -> list[str]:
    problems = []
    paths = subjects(root)
    if not paths:
        return [f"no shipped driver file found under {DRIVER} / {RUNLIB}: an empty subject set "
                f"satisfies every rule below"]
    inventory = (root / INVENTORY)
    if not inventory.is_file():
        return [f"{INVENTORY} is missing, so nothing can be held against it"]
    text = inventory.read_text(encoding="utf-8")
    imports, programs, unresolved = derive(paths, root)
    for site, written in sorted(unresolved.items()):
        problems.append(f"{site} hands a shell a command this scan cannot read ({written}): the "
                        f"program it runs cannot be checked against {INVENTORY}, so write the "
                        f"command as a literal or run it through an argv vector")
    if not imports and not programs:
        problems.append("the derivation found neither a third-party import nor a program name in "
                        f"{len(paths)} driver files, which no version of this driver has been "
                        "true of — the deriver is broken, not the code")
    for name, sites in sorted(imports.items()):
        if not declared(text, name):
            problems.append(f"{name} is imported by {', '.join(sorted(sites))} and is not declared "
                            f"in {INVENTORY}: a user without it meets a traceback, not a message")
    for name, sites in sorted(programs.items()):
        if not declared(text, name):
            problems.append(f"the driver runs {name!r} ({', '.join(sorted(sites))}) and it is not "
                            f"declared in {INVENTORY} with the version it was verified at")
    return problems


def self_test() -> int:
    """Positive control first, then one planted violation per rule, each failing BY NAME."""
    failures = []

    ran = []

    def control(label, got, want):
        ran.append(label)
        if want not in got:
            failures.append(f"{label}: expected {want!r} in {got!r}")
        print(f"  control {label}", flush=True)

    live = check(REPO)
    if live:
        print("check-driver-dependencies --self-test: FAIL: the unmutated tree does not pass, so a "
              f"planted violation would prove nothing: {live}", file=sys.stderr)
        return 1
    print("  control the unmutated tree passes (positive control)", flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "tree"
        (root / RUNLIB).mkdir(parents=True)
        (root / INVENTORY).write_text("| Tool | Required by |\n| --- | --- |\n| `git` | x |\n",
                                      encoding="utf-8")
        (root / DRIVER).write_text("import json\nimport runlib\n", encoding="utf-8")
        planted = root / RUNLIB / "plant.py"

        planted.write_text("import json\nimport nowhere_declared\n", encoding="utf-8")
        control("an undeclared third-party import fails by name",
                " ".join(check(root)), "nowhere_declared is imported by")

        planted.write_text("import json\nfrom grammar import owner_lines\n", encoding="utf-8")
        (root / GRAMMAR).mkdir(parents=True)
        (root / GRAMMAR / "rules.py").write_text("import json\nimport nowhere_in_grammar\n", encoding="utf-8")
        control("the local grammar package is no dependency, and an undeclared import inside it fails by name",
                " ".join(check(root)), "nowhere_in_grammar is imported by session-distill/grammar/rules.py")
        found = " ".join(check(root))
        control("and the grammar import itself is not reported",
                found if re.search(r"(?<![\w])grammar is imported by", found) else "absent", "absent")
        (root / GRAMMAR / "rules.py").unlink()

        planted.write_text("import subprocess\nsubprocess.run(['nosuchtool', '-x'])\n",
                           encoding="utf-8")
        control("an undeclared program fails by name", " ".join(check(root)),
                "the driver runs 'nosuchtool'")

        def clean(label, got):
            """A control for the ABSENCE of problems. `control(..., want="")` could not fail: the
            empty string is in every string, so both positive controls passed whatever `check`
            returned (review Y #6)."""
            ran.append(label)
            if got:
                failures.append(f"{label}: expected no problem, got {got}")
            print(f"  control {label}", flush=True)

        planted.write_text("import subprocess\nsubprocess.run(['/opt/homebrew/bin/git', 'show'])\n",
                           encoding="utf-8")
        clean("a declared program under an absolute path is recognised by its basename", check(root))

        # The alias half: the row names the product, the code names the binary.
        planted.write_text("import subprocess\nsubprocess.run(['claude', '--version'])\n",
                           encoding="utf-8")
        control("a host CLI not declared even under its product name fails",
                " ".join(check(root)), "the driver runs 'claude'")
        (root / INVENTORY).write_text(
            "| CLI | Required by |\n| --- | --- |\n| Claude Code | the driver |\n", encoding="utf-8")
        clean("and passes once the row declares it under that name", check(root))

        # review Y #3: the three spellings that hid a program from the scan entirely.
        planted.write_text("import subprocess as sp\nsp.run(['nosuchtool', '-x'])\n", encoding="utf-8")
        control("an aliased module import does not hide the program it runs",
                " ".join(check(root)), "the driver runs 'nosuchtool'")
        planted.write_text("from subprocess import run\nrun(['nosuchtool', '-x'])\n", encoding="utf-8")
        control("an imported runner function does not hide it either",
                " ".join(check(root)), "the driver runs 'nosuchtool'")
        planted.write_text("from subprocess import run as go\ngo(['nosuchtool'])\n", encoding="utf-8")
        control("nor an imported runner renamed again", " ".join(check(root)),
                "the driver runs 'nosuchtool'")
        planted.write_text("import subprocess\nsubprocess.run(args=['nosuchtool', '-x'])\n",
                           encoding="utf-8")
        control("the command vector is read from `args=` as well as from the first positional",
                " ".join(check(root)), "the driver runs 'nosuchtool'")
        planted.write_text("import shutil\nshutil.which('nosuchtool')\n", encoding="utf-8")
        control("and a `which` probe counts as reaching for a program",
                " ".join(check(root)), "the driver runs 'nosuchtool'")

        # The shell runners, which the scan did not look at at all until now. Their command is one
        # string, so the program is its first word — and the three spellings above apply here too.
        planted.write_text("import os\nos.system('nosuchtool --x')\n", encoding="utf-8")
        control("a shell command run through os.system names a program like any other",
                " ".join(check(root)), "the driver runs 'nosuchtool'")
        planted.write_text("import os\nos.popen('/opt/homebrew/bin/nosuchtool -q').read()\n",
                           encoding="utf-8")
        control("os.popen counts too, and its program is read by basename",
                " ".join(check(root)), "the driver runs 'nosuchtool'")
        planted.write_text("from os import system as sh\nsh('nosuchtool --x')\n", encoding="utf-8")
        control("an imported shell runner, renamed, does not hide it either",
                " ".join(check(root)), "the driver runs 'nosuchtool'")
        # A command the scan cannot read is REPORTED. Passing over it silently is the hole the
        # string runners were already in: the spelling is in scope, so the unreadable case has to
        # be named rather than treated as "no program here".
        planted.write_text("import os\ntool = 'nosuchtool'\nos.system(f'{tool} --x')\n",
                           encoding="utf-8")
        control("a shell command that is not a literal is reported, not passed over",
                " ".join(check(root)), "hands a shell a command this scan cannot read")
        planted.write_text("import os\nos.system()\n", encoding="utf-8")
        control("and so is a shell runner called with no command at all",
                " ".join(check(root)), "hands a shell a command this scan cannot read")

        # Pair discipline, both directions: a runner belongs to a module, and the names are not
        # interchangeable. Each of these trees also runs a DECLARED program, so a clean verdict
        # here is the pair being unrecognised rather than the deriver finding nothing.
        (root / INVENTORY).write_text("| Tool | Required by |\n| --- | --- |\n| `git` | x |\n",
                                      encoding="utf-8")
        planted.write_text("import os\nimport subprocess\nsubprocess.run(['git', 'show'])\n"
                           "os.run(['nosuchtool'])\n", encoding="utf-8")
        clean("a runner name that module does not have is not a program (os.run)", check(root))
        planted.write_text("import os\nimport subprocess\nsubprocess.run(['git', 'show'])\n"
                           "subprocess.system(['nosuchtool', '--x'])\n", encoding="utf-8")
        clean("nor the other way round (subprocess.system)", check(root))
        # ... and that the absence can fail: declare the pair the code wrote, on the module whose
        # runners take an argv vector, and the same tree reports the program it runs.
        RUNNER_PAIRS["subprocess"].add("system")
        try:
            control("the pair control is real: declare subprocess.system and the same tree fails",
                    " ".join(check(root)), "the driver runs 'nosuchtool'")
        finally:
            RUNNER_PAIRS["subprocess"].discard("system")
        # The os.run absence, proven the same way. What it reports is the unreadable-command
        # message rather than a program name — `os` reads a string, and the planted call hands it a
        # list — which is the honest observable and still a failure on a tree that passes today.
        planted.write_text("import os\nimport subprocess\nsubprocess.run(['git', 'show'])\n"
                           "os.run(['nosuchtool'])\n", encoding="utf-8")
        RUNNER_PAIRS["os"].add("run")
        try:
            control("and the os.run absence is real: declare it and the same tree fails",
                    " ".join(check(root)), "hands a shell a command this scan cannot read")
        finally:
            RUNNER_PAIRS["os"].discard("run")
        # ... and the two proofs that the clean controls above can fail: break the recognition each
        # one rests on, and watch it report a problem.
        planted.write_text("import subprocess\nsubprocess.run(['/opt/homebrew/bin/git', 'show'])\n",
                           encoding="utf-8")
        kept_basename = globals()["derive"]
        try:
            def whole_path(paths, where):
                imports, programs, unresolved = kept_basename(paths, where)
                return imports, {f"/opt/homebrew/bin/{name}" if name == "git" else name: sites
                                 for name, sites in programs.items()}, unresolved
            globals()["derive"] = whole_path
            control("the basename control is real: without basename recognition the same tree fails",
                    " ".join(check(root)), "/opt/homebrew/bin/git")
        finally:
            globals()["derive"] = kept_basename
        planted.write_text("import subprocess\nsubprocess.run(['claude', '--version'])\n",
                           encoding="utf-8")
        kept_aliases = dict(ALIASES)
        try:
            ALIASES.clear()
            control("the alias control is real: without the product alias the same row fails",
                    " ".join(check(root)), "the driver runs 'claude'")
        finally:
            ALIASES.update(kept_aliases)

        # An empty subject set must fail rather than report clean.
        empty = pathlib.Path(tmp) / "empty"
        empty.mkdir()
        control("an empty subject set is a failure, not a clean run",
                " ".join(check(empty)), "an empty subject set")

        # A subject set that parses but reaches for nothing: the deriver would be broken.
        bare = pathlib.Path(tmp) / "bare"
        (bare / RUNLIB).mkdir(parents=True)
        (bare / INVENTORY).write_text("| Tool |\n| --- |\n| `git` |\n", encoding="utf-8")
        (bare / DRIVER).write_text("import json\n", encoding="utf-8")
        control("a derivation that finds nothing at all is reported as a broken deriver",
                " ".join(check(bare)), "the deriver is broken")

    if failures:
        for line in failures:
            print(f"check-driver-dependencies --self-test: FAIL: {line}", file=sys.stderr)
        return 1
    print(f"check-driver-dependencies --self-test: OK (positive control + {len(ran)} controls: "
          f"every planted violation failing by name, every absence asserted as an empty problem "
          f"list, and each absence control shown to fail when the recognition it rests on is "
          f"changed)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="the default")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    problems = check(REPO)
    if problems:
        for line in problems:
            print(f"check-driver-dependencies: FAIL: {line}", file=sys.stderr)
        return 1
    paths = subjects(REPO)
    imports, programs, _unresolved = derive(paths, REPO)
    print(f"check-driver-dependencies: OK — {len(paths)} shipped driver files, "
          f"{len(imports)} third-party import(s) ({', '.join(sorted(imports))}), "
          f"{len(programs)} literal program name(s) ({', '.join(sorted(programs))}), "
          f"each declared in {INVENTORY}. Host CLIs resolved from configuration are declared by "
          f"review, not derivable here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
