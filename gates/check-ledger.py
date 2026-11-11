#!/usr/bin/env python3
"""The ledger's checkout-only legs: the committed ledger, and the schema 1 migration.

`session-distill/runlib/ledger.py` ships. Two things it used to reach for do not:

* `design/session-distill/ledger.json` — the OWNER'S ledger, in this checkout. An installed driver's
  ledger lives under its state root (`<state>/distill/ledger.json`), so a default pointing at
  `design/` was a path that cannot exist on the machine the code runs on.
* `session-distill/migrate-ledger.py` — the one-time schema 1 to schema 2 migration, author-side
  work that the payload excludes. Shipped code loading it by path is the direction AGENTS.md
  forbids.

So this script holds both, and passes them in: `--check` compares the ledger in the index with the
ledger at a base revision through `ledger.check_command`, and `--self-test` runs the module's own
suite with the migrator and the committed ledger supplied, which turns its two SKIPPED legs on.

Run from a checkout. `gates/check-parity.sh` calls both; nothing here is installed.
"""
import argparse
import ast
import importlib.util
import json
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
LEDGER_REL = "design/session-distill/ledger.json"       # the owner's ledger, in this checkout
MIGRATOR_REL = "session-distill/migrate-ledger.py"      # author-side, excluded from the payload
sys.path.insert(0, str(REPO / "session-distill"))
from runlib import ledger as ledger_lib                 # noqa: E402  (after the path insert)


def migrator():
    """The author-side migration module, loaded by its literal path in THIS script.

    It is loaded rather than imported because its name carries a hyphen, and read for two callables
    only: `migrate` (a schema 1 ledger to its schema 2 form) and `tiny` (a schema 1 sample).
    """
    path = REPO / MIGRATOR_REL
    spec = importlib.util.spec_from_file_location("migrate_ledger", path)
    if spec is None or not path.is_file():
        sys.exit(f"check-ledger: FAILED — {MIGRATOR_REL} is unreadable, so a schema 1 base cannot be "
                 f"compared with a schema 2 head")
    module = importlib.util.module_from_spec(spec)
    sys.modules["migrate_ledger"] = module
    spec.loader.exec_module(module)
    return module


# The constant the shipped module used to carry, and the only name whose RETURN would be a
# regression: while it existed as an alias, `runlib/stage_read.py` read `design/session-distill/…`
# under a name that had quietly become the state-root path, so a real checkout's pinned ledger was
# looked for in a directory no checkout has. The alias is gone; this keeps it gone.
RETIRED_CONSTANT = "LEDGER_REL"


def shipped_driver_files():
    """The driver files a user receives, from `files[]` rather than from a habit here."""
    manifest = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    entries = [e for e in manifest.get("files", []) if e.startswith("session-distill/")]
    found = []
    for entry in entries:
        path = REPO / entry.rstrip("/")
        if path.is_file() and path.suffix == ".py":
            found.append(path)
        elif path.is_dir():
            found.extend(sorted(q for q in path.rglob("*.py") if "__pycache__" not in q.parts))
    return found


def retired_constant_problems(paths=None):
    """Every shipped driver file that names the retired constant AS CODE.

    By AST, not by grep: the name appears inside a planted fixture STRING in `runlib/inventory.py`'s
    own suite, which is a mention of someone else's source text and not a reference. A grep would
    have to exempt it, and an exemption is how the next real reference gets excused."""
    problems = []
    subjects = shipped_driver_files() if paths is None else list(paths)
    if not subjects:
        return [f"check-ledger: no shipped driver .py found, so '{RETIRED_CONSTANT} is gone' would "
                f"be a claim over nothing"]
    for path in subjects:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"{path}: cannot be parsed, so it cannot be judged: {exc}")
            continue
        for node in ast.walk(tree):
            # An IMPORT names it too, and `as` then hides it from every later reference:
            # `from runlib.ledger import LEDGER_REL as old` left this leg with nothing to see,
            # because an imported name is an `ast.alias` and not a `Name` or an `Attribute`
            # (review Y #7).
            imported = isinstance(node, ast.ImportFrom) and any(
                alias.name == RETIRED_CONSTANT for alias in node.names)
            named = imported or (
                isinstance(node, ast.Attribute) and node.attr == RETIRED_CONSTANT) or (
                isinstance(node, ast.Name) and node.id == RETIRED_CONSTANT)
            if named:
                rel = path.relative_to(REPO) if path.is_relative_to(REPO) else path.name
                problems.append(f"{rel}:{node.lineno} names {RETIRED_CONSTANT}, retired in WP-24: a "
                                f"shipped module may not name a path inside the author's checkout, "
                                f"and the caller passes the reference in")
    return problems


def self_test_retired_constant():
    """The negative control: a file that names the constant fails, by its path and line."""
    with tempfile.TemporaryDirectory() as tmp:
        clean = pathlib.Path(tmp) / "clean.py"
        clean.write_text("from runlib import ledger\nX = ledger.STATE_LEDGER_REL\n", encoding="utf-8")
        if retired_constant_problems([clean]):
            return ["the retired-constant leg fails a file that does not name it"]
        planted = pathlib.Path(tmp) / "planted.py"
        planted.write_text("from runlib import ledger\nY = ledger.LEDGER_REL\n", encoding="utf-8")
        got = retired_constant_problems([planted])
        if not any("planted.py:2 names LEDGER_REL" in line for line in got):
            return [f"a planted reference to {RETIRED_CONSTANT} was not reported by name: {got}"]
        bare = pathlib.Path(tmp) / "bare.py"
        bare.write_text("LEDGER_REL = 'x'\nZ = LEDGER_REL\n", encoding="utf-8")
        if not retired_constant_problems([bare]):
            return ["a bare use of the retired name was not reported"]
        aliased = pathlib.Path(tmp) / "aliased.py"
        aliased.write_text("from runlib.ledger import LEDGER_REL as old\nvalue = old\n",
                           encoding="utf-8")
        got = retired_constant_problems([aliased])
        if not any("aliased.py:1 names LEDGER_REL" in line for line in got):
            return [f"an aliased from-import of {RETIRED_CONSTANT} was not reported: {got}"]
        plain_import = pathlib.Path(tmp) / "plain_import.py"
        plain_import.write_text("from runlib.ledger import STATE_LEDGER_REL as keep\nv = keep\n",
                                encoding="utf-8")
        if retired_constant_problems([plain_import]):
            return ["an import of the CURRENT constant was reported as the retired one"]
        mention = pathlib.Path(tmp) / "mention.py"
        mention.write_text('SOURCE = "LEDGER_REL = design/x"\n', encoding="utf-8")
        if retired_constant_problems([mention]):
            return ["the name inside a string was read as a reference"]
        if not retired_constant_problems([]):
            return ["an empty subject set was reported as clean"]
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="the committed ledger against a base revision")
    parser.add_argument("--self-test", action="store_true",
                        help="the module's suite with the checkout's ledger and the migrator supplied")
    parser.add_argument("--ledger", default=LEDGER_REL, help="repo-relative path of the ledger to judge")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--worktree", action="store_true", help="read the file on disk instead of the index")
    parser.add_argument("--allocated", help="comma-separated ids the run allocated; pass it empty for a "
                                            "transaction that allocated none, omit it only when there is no run")
    args = parser.parse_args(argv)
    if args.self_test:
        module = migrator()
        control = self_test_retired_constant()
        if control:
            for line in control:
                print(f"check-ledger --self-test: FAIL: {line}", file=sys.stderr)
            return 1
        print("check-ledger --self-test: the retired-constant leg caught its planted reference, a "
              "bare use and an aliased from-import, and left a string mention, an import of the "
              "current constant and a clean file alone")
        return ledger_lib.self_test(migrate=module.migrate, checkout_ledger=REPO / args.ledger,
                                    tiny=module.tiny)
    if args.check:
        retired = retired_constant_problems()
        if retired:
            for line in retired:
                print(f"check-ledger: FAIL: {line}", file=sys.stderr)
            return 1
        code, lines = ledger_lib.check_command(REPO, args.ledger, args.base, args.worktree,
                                               ledger_lib.allocation(args.allocated),
                                               migrate=migrator().migrate)
        print("\n".join(lines), file=sys.stdout if code == 0 else sys.stderr)
        return code
    parser.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
