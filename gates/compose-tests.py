#!/usr/bin/env python3
"""The compose `test_instructions*` unittests, in named groups the parity umbrella runs as concurrent legs.

Each test module belongs to exactly one group. A named group lists the file patterns it takes, and
`rest`, last, takes every module the others leave, so a module added later runs in `rest` without
anyone placing it. A pattern that matches no module, or a module two groups both claim, is refused
by name: the declaration has gone stale or ambiguous. --self-test holds the split to the suite it
replaced: the union of the groups' test ids is the plain `discover -s compose -p
'test_instructions*.py'` set, by name and by count.

  "$VENV/bin/python" gates/compose-tests.py --groups      the group names, one per line
  "$VENV/bin/python" gates/compose-tests.py GROUP         run one group, as `python -m unittest` does
  "$VENV/bin/python" gates/compose-tests.py --self-test
"""
import fnmatch
import os
import pathlib
import sys
import unittest

COMPOSE = pathlib.Path(__file__).resolve().parent.parent / "compose"
PATTERN = "test_instructions*.py"
REST = "rest"
# The cut follows each module's own time, measured 2026-11-02 one process each and unloaded (ui about
# 71 s, setup 65, store 56, rest 53); like any measurement it goes stale. The Textual and pty modules
# are split in two only because the review screen's keys now wait for its Apply button and focus to be
# drawn (test_instructions_setup.await_drawn): before that, load made the keys land on the old screen.
GROUPS = (
    ("ui", ("test_instructions_ui*.py", "test_instructions_understand_ui.py", "test_instructions_shell.py")),
    ("setup", ("test_instructions_setup.py", "test_instructions_setup_cli.py", "test_instructions_setup_ui.py")),
    ("store", ("test_instructions_app.py", "test_instructions_migration.py", "test_instructions_integrity.py",
               "test_instructions_store.py", "test_instructions_native.py")),
    (REST, ()),
)


def modules(directory=COMPOSE):
    return sorted(path.name for path in pathlib.Path(directory).glob(PATTERN))


def assign(names, groups=GROUPS):
    """({group: [module file names]}, problems)."""
    placed, problems = {name: [] for name, _ in groups}, []
    if [name for name, _ in groups][-1:] != [REST] or dict(groups).get(REST):
        problems.append(f"COMPOSE_GROUP_NO_REST: the last group must be {REST!r} with no patterns")
    for group, patterns in groups:
        for pattern in patterns:
            if not any(fnmatch.fnmatchcase(name, pattern) for name in names):
                problems.append(f"COMPOSE_GROUP_STALE {group}: {pattern!r} matches no test module")
    for name in names:
        claims = [group for group, patterns in groups if any(fnmatch.fnmatchcase(name, p) for p in patterns)]
        if len(claims) > 1:
            problems.append(f"COMPOSE_GROUP_AMBIGUOUS {name}: claimed by {claims}")
        placed.setdefault(claims[0] if claims else REST, []).append(name)
    return placed, problems


def ids(suite):
    out = []
    for test in suite:
        out.extend(ids(test) if isinstance(test, unittest.TestSuite) else [test.id()])
    return out


def group_suite(files):
    loader = unittest.TestLoader()
    return unittest.TestSuite(loader.discover(str(COMPOSE), pattern=name, top_level_dir=str(COMPOSE))
                              for name in files)


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    placed, problems = assign(modules())
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 2
    if argv == ["--groups"]:
        print("\n".join(placed))
        return 0
    if len(argv) != 1 or argv[0] not in placed:
        print(f"usage: compose-tests.py --groups | --self-test | GROUP, GROUP one of {list(placed)}", file=sys.stderr)
        return 2
    if not placed[argv[0]]:
        print(f"FAIL: compose test group {argv[0]!r} holds no module, so a pass would judge nothing")
        return 2
    # What `python -m unittest discover -s compose` does, over this group's modules only: the
    # working directory first on the import path, as `-m` puts it, and the runner `unittest.main`
    # builds, warnings included.
    # The node-based CLIs the tests run (claude, codex, npm) would otherwise leave a compile cache
    # directory in the caller's TMPDIR, which outlives the run.
    os.environ["NODE_DISABLE_COMPILE_CACHE"] = "1"
    runner = unittest.TextTestRunner(warnings=None if sys.warnoptions else "default")
    return 0 if runner.run(group_suite(placed[argv[0]])).wasSuccessful() else 1


def self_test():
    failures, ran = [], []

    def control(name, ok, detail=""):
        ran.append(name)
        if not ok:
            failures.append(f"{name}: {detail}")

    names = modules()
    placed, problems = assign(names)
    control("the-declared-groups-hold-the-real-modules", not problems and len(names) > 0
            and sorted(n for files in placed.values() for n in files) == names
            and all(placed.values()), f"{problems} {placed}")
    planted = names + ["test_instructions_planted_newcomer.py"]
    got, problems = assign(planted)
    control("a-new-module-lands-in-rest", not problems and "test_instructions_planted_newcomer.py" in got[REST],
            f"{problems} {got[REST]}")
    _, problems = assign(names, GROUPS[:-1] + (("planted", ("test_instructions_no_such_module.py",)), (REST, ())))
    control("a-pattern-matching-nothing-is-refused", any("COMPOSE_GROUP_STALE planted" in p for p in problems),
            f"{problems}")
    _, problems = assign(names, (("planted", ("test_instructions_app.py",)),) + GROUPS)
    control("a-module-two-groups-claim-is-refused",
            any("COMPOSE_GROUP_AMBIGUOUS test_instructions_app.py" in p for p in problems), f"{problems}")
    _, problems = assign(names, GROUPS[:-1])
    control("a-declaration-without-rest-is-refused", any("COMPOSE_GROUP_NO_REST" in p for p in problems),
            f"{problems}")
    # The split holds the suite it replaced: every test id the plain discovery loads, once, and no other.
    plain = ids(unittest.TestLoader().discover(str(COMPOSE), pattern=PATTERN, top_level_dir=str(COMPOSE)))
    split = [test_id for files in placed.values() for test_id in ids(group_suite(files))]
    control("the-groups-load-the-plain-discovery-ids", len(plain) > 0 and sorted(plain) == sorted(split)
            and len(split) == len(set(split)),
            f"plain {len(plain)} split {len(split)}; only plain {sorted(set(plain) - set(split))[:5]}, "
            f"only split {sorted(set(split) - set(plain))[:5]}")
    for failure in failures:
        print(f"compose-tests --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"compose-tests --self-test: OK ({len(ran)} controls, {len(plain)} tests in {len(placed)} groups)")
    return 0


if __name__ == "__main__":
    # `python -m unittest` runs with the working directory, not this file's, first on the path.
    sys.path[0] = os.getcwd()
    sys.exit(main(sys.argv[1:]))
