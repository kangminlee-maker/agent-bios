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
INVENTORY = "DEPENDENCIES.md"

# Local to the driver: imported by module name because the driver puts its own directory on the
# path. Neither is a dependency anyone installs.
LOCAL = {"runlib", "distill"}

# The runner calls whose first literal argument is a command name. Qualified on purpose: a bare
# `run("S6", ...)` of some object's own method is not a program, and an unqualified scan read one
# as `S6`.
RUNNER_QUALIFIERS = {"subprocess", "shutil"}
RUNNERS = {"run", "Popen", "check_output", "check_call", "call", "which"}

# A binary whose inventory row names the product. The row is the declaration; this maps the name
# the code uses to the words the row uses, and nothing else.
ALIASES = {"claude": "Claude Code", "codex": "Codex CLI"}

# Names that are never a dependency: the interpreter already running, and a path, not a command.
NOT_A_DEPENDENCY = {"sys.executable", "python3", ""}


def subjects(root: pathlib.Path) -> list[pathlib.Path]:
    """The shipped driver files, sorted. Empty is a failure, never a clean run."""
    found = [root / DRIVER, *sorted((root / RUNLIB).glob("*.py"))]
    return [path for path in found if path.is_file()]


def _runner_bindings(tree):
    """(names bound to a watched module, names bound to a runner function) in this file.

    Spelled out because ordinary Python hides a program three ways and the scan saw none of them
    (review Y #3): `import subprocess as sp` binds the module under another name, `from subprocess
    import run` binds the function with no qualifier at all, and either can be renamed with `as`.
    A scan matching only the literal text `subprocess.run` reports a clean tree while the driver
    runs whatever it likes."""
    modules, functions = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in RUNNER_QUALIFIERS:
                    modules.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] not in RUNNER_QUALIFIERS:
                continue
            for alias in node.names:
                if alias.name in RUNNERS:
                    functions.add(alias.asname or alias.name)
                else:
                    modules.add(alias.asname or alias.name)
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


def _is_runner(call, modules, functions):
    """Whether this call starts a program, under any spelling this file's imports allow."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in RUNNERS:
        base = func.value
        qualifier = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
        return qualifier in modules
    if isinstance(func, ast.Name):
        return func.id in functions
    return False


def derive(paths: list[pathlib.Path], root: pathlib.Path) -> tuple[dict, dict]:
    """(third-party imports, literal program names), each name -> the files that reach for it."""
    imports: dict[str, set[str]] = {}
    programs: dict[str, set[str]] = {}
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
            if isinstance(node, ast.Call) and _is_runner(node, modules, functions):
                first = _argv_of(node)
                if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
                    first = first.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    command = first.value.split("/")[-1]
                    if command and command not in NOT_A_DEPENDENCY:
                        programs.setdefault(command, set()).add(rel)
    return imports, programs


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
    imports, programs = derive(paths, root)
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
        # ... and the two proofs that the clean controls above can fail: break the recognition each
        # one rests on, and watch it report a problem.
        planted.write_text("import subprocess\nsubprocess.run(['/opt/homebrew/bin/git', 'show'])\n",
                           encoding="utf-8")
        kept_basename = globals()["derive"]
        try:
            def whole_path(paths, where):
                imports, programs = kept_basename(paths, where)
                return imports, {f"/opt/homebrew/bin/{name}" if name == "git" else name: sites
                                 for name, sites in programs.items()}
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
          f"list, and the two absence controls each shown to fail when their recognition is broken)")
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
    imports, programs = derive(paths, REPO)
    print(f"check-driver-dependencies: OK — {len(paths)} shipped driver files, "
          f"{len(imports)} third-party import(s) ({', '.join(sorted(imports))}), "
          f"{len(programs)} literal program name(s) ({', '.join(sorted(programs))}), "
          f"each declared in {INVENTORY}. Host CLIs resolved from configuration are declared by "
          f"review, not derivable here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
