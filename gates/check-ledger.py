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
import importlib.util
import pathlib
import sys

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
        return ledger_lib.self_test(migrate=module.migrate, checkout_ledger=REPO / args.ledger,
                                    tiny=module.tiny)
    if args.check:
        code, lines = ledger_lib.check_command(REPO, args.ledger, args.base, args.worktree,
                                               ledger_lib.allocation(args.allocated),
                                               migrate=migrator().migrate)
        print("\n".join(lines), file=sys.stdout if code == 0 else sys.stderr)
        return code
    parser.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
