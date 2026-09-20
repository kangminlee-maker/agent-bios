#!/usr/bin/env python3
"""Two umbrella legs over the work-environment runtime and its tests.

  unit-tests       every gates/workenv/test_*.py, one process per file. A file passes only
                   when at least one of its tests actually executed and none failed: an empty
                   file, or one whose every test is skipped, reports OK to unittest.
  static-analysis  ruff at the exact version RUFF_PIN over workenv/ and gates/workenv/. The
                   subject files are enumerated here and handed over by name, because ruff
                   given a directory with no Python in it exits 0.

Each leg fails by name on an empty subject set and on an absent or mismatched tool. Nothing
is installed or fetched: a missing ruff is a failure, not a skip. Counts are printed per
leg and per tree and never summed, because a sum is where a zero hides.

  python3 gates/workenv/check-workenv.py              # both legs on this checkout
  python3 gates/workenv/check-workenv.py --self-test  # every rule against an input built here
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True   # a gate leaves no bytecode in the checkout it judges

REPO = pathlib.Path(__file__).resolve().parents[2]

# The static-analysis tool and its exact version. DEPENDENCIES.md names this constant as the
# owner. Moving it means re-running the leg on the whole subject set under the new binary.
RUFF_PIN = "0.14.3"
# pycodestyle, pyflakes, bugbear and pylint's error class: findings that are wrong code, not
# taste. --isolated keeps a developer's own ruff configuration out of the verdict, so the rule
# set is these arguments and nothing else.
RUFF_ARGS = ["check", "--isolated", "--no-cache", "--select", "E,F,W,B,PLE",
             "--line-length", "100", "--target-version", "py311", "--output-format", "concise"]
STATIC_TREES = ("workenv", "gates/workenv")

# The floor DEPENDENCIES.md states for every Python entry point here (tomllib).
PYTHON_FLOOR = (3, 11)
TEST_DIR = "gates/workenv"
TEST_PATTERN = "test_*.py"

RUN_ONE = "--run-one"
PROBE_TIMEOUT = 30
LEG_TIMEOUT = 600


def python_files(root, tree):
    base = root / tree
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.py") if p.is_file())


def test_files(root):
    base = root / TEST_DIR
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob(TEST_PATTERN) if p.is_file())


def probe(argv):
    """(stdout, None) or (None, reason) — a tool that cannot answer is absent, not clean."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=PROBE_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, type(error).__name__
    if done.returncode != 0:
        return None, f"exit {done.returncode}"
    return done.stdout.strip(), None


def static_analysis(root, tool, timeout=LEG_TIMEOUT):
    """(failures, report) for the static-analysis leg. `tool` is a path, or None when no
    ruff was found."""
    failures, report = [], []
    subjects = []
    for tree in STATIC_TREES:
        files = python_files(root, tree)
        report.append(f"static-analysis: {tree}/ {len(files)} file(s)")
        if not files:
            failures.append(f"static-analysis: empty subject set: no Python file under {tree}/")
        subjects.extend(files)

    if tool is None or not pathlib.Path(tool).is_file():
        failures.append(f"static-analysis: tool absent: ruff {RUFF_PIN} is required and "
                        f"{tool or 'no ruff on PATH'} is not a file")
        return failures, report
    version, reason = probe([str(tool), "--version"])
    if version is None:
        failures.append(f"static-analysis: tool absent: {tool} --version did not answer ({reason})")
        return failures, report
    if version != f"ruff {RUFF_PIN}":
        failures.append(f"static-analysis: tool version: {tool} reports {version!r}, "
                        f"the pin is 'ruff {RUFF_PIN}'")
        return failures, report
    report.append(f"static-analysis: {version} at {tool}")
    if not subjects:
        return failures, report

    try:
        done = subprocess.run([str(tool), *RUFF_ARGS, *map(str, subjects)], cwd=root,
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        failures.append(f"static-analysis: tool did not complete: {type(error).__name__}")
        return failures, report
    if done.returncode == 1:
        failures.append("static-analysis: violations:\n" + done.stdout.rstrip())
    elif done.returncode != 0:
        # 2 is ruff's own usage or internal error: nothing was judged, which is not clean.
        failures.append(f"static-analysis: tool did not complete: exit {done.returncode}: "
                        + (done.stderr.strip() or done.stdout.strip())[:400])
    return failures, report


def interpreter_version(python):
    out, reason = probe([str(python), "-c",
                         "import sys; print('%d.%d' % sys.version_info[:2])"])
    if out is None:
        return None, reason
    try:
        major, minor = out.split(".")
        return (int(major), int(minor)), None
    except ValueError:
        return None, f"unreadable version {out!r}"


def unit_tests(root, python, timeout=LEG_TIMEOUT):
    """(failures, report) for the unit-test leg. Each file runs in its own process through
    this file's --run-one mode, so one file's imports and module state reach no other."""
    failures, report = [], []
    files = test_files(root)
    report.append(f"unit-tests: {TEST_DIR}/{TEST_PATTERN} {len(files)} file(s)")
    if not files:
        failures.append(f"unit-tests: empty subject set: no {TEST_DIR}/{TEST_PATTERN}")

    if not pathlib.Path(python).is_file():
        failures.append(f"unit-tests: tool absent: interpreter {python} is not a file")
        return failures, report
    version, reason = interpreter_version(python)
    if version is None:
        failures.append(f"unit-tests: tool absent: interpreter {python} did not answer ({reason})")
        return failures, report
    if version < PYTHON_FLOOR:
        failures.append(f"unit-tests: tool version: interpreter {python} is "
                        f"{version[0]}.{version[1]}, the floor is "
                        f"{PYTHON_FLOOR[0]}.{PYTHON_FLOOR[1]}")
        return failures, report

    for path in files:
        rel = path.relative_to(root).as_posix()
        with tempfile.TemporaryDirectory(prefix="workenv-unit-") as scratch:
            result = pathlib.Path(scratch) / "result.json"
            try:
                done = subprocess.run(
                    [str(python), "-B", str(pathlib.Path(__file__).resolve()), RUN_ONE,
                     str(path), str(result)],
                    cwd=root, capture_output=True, text=True, timeout=timeout)
            except (OSError, subprocess.TimeoutExpired) as error:
                failures.append(f"unit-tests: {rel}: did not complete: {type(error).__name__}")
                continue
            try:
                counts = json.loads(result.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                failures.append(f"unit-tests: {rel}: no result was written (exit "
                                f"{done.returncode}): {done.stderr.strip()[-400:]}")
                continue
        executed = counts["ran"] - counts["skipped"]
        report.append(f"unit-tests: {rel} ran {counts['ran']}, skipped {counts['skipped']}")
        if counts["ran"] == 0:
            failures.append(f"unit-tests: {rel}: ran 0 tests")
        elif executed <= 0:
            failures.append(f"unit-tests: {rel}: every test was skipped "
                            f"({counts['skipped']} of {counts['ran']})")
        if counts["failed"]:
            failures.append(f"unit-tests: {rel}: {counts['failed']} test(s) failed:\n"
                            + done.stderr.rstrip()[-2000:])
    return failures, report


def run_one(path, result):
    """Child mode: run one test file and write its counts. The counts are the verdict; the
    parent reads no exit status, so a test that calls sys.exit cannot report for the file."""
    import importlib.util
    import unittest

    path = pathlib.Path(path)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    outcome = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(suite)
    counts = {
        "ran": outcome.testsRun,
        "skipped": len(outcome.skipped),
        "failed": len(outcome.failures) + len(outcome.errors) + len(outcome.unexpectedSuccesses),
    }
    pathlib.Path(result).write_text(json.dumps(counts), encoding="utf-8")
    return 0


def find_ruff():
    return os.environ.get("AGENT_BIOS_RUFF") or shutil.which("ruff")


def check(root, ruff, python):
    failures, report = [], []
    for leg_failures, leg_report in (unit_tests(root, python), static_analysis(root, ruff)):
        failures.extend(leg_failures)
        report.extend(leg_report)
    return failures, report


PASSING_TEST = ("import unittest\n\n\nclass T(unittest.TestCase):\n"
                "    def test_it(self):\n        self.assertEqual(1 + 1, 2)\n")
SKIPPED_TEST = ("import unittest\n\n\nclass T(unittest.TestCase):\n"
                "    @unittest.skip('never')\n    def test_it(self):\n        pass\n")
FAILING_TEST = ("import unittest\n\n\nclass T(unittest.TestCase):\n"
                "    def test_it(self):\n        self.assertEqual(1 + 1, 3)\n")
NO_TESTS = "import unittest  # noqa: F401\n"
BROKEN_IMPORT = "import a_module_nobody_has\n"
EXITS_ZERO = "import sys\n\nsys.exit(0)\n"
NEVER_RETURNS = "import time\n\ntime.sleep(30)\n"
CLEAN_RUNTIME = '"""Runtime."""\n\n\ndef one():\n    return 1\n'
UNDEFINED_NAME = '"""Runtime."""\n\n\ndef one():\n    return not_defined_anywhere\n'


def self_test():
    """Every rule against an input built here, positive control first so a miss is
    attributable to the planted difference and not to the machine."""
    problems = []
    python = sys.executable
    ruff = find_ruff()

    def tree(base, runtime=CLEAN_RUNTIME, tests=None):
        tests = {"test_ok.py": PASSING_TEST} if tests is None else tests
        root = pathlib.Path(base)
        (root / "workenv").mkdir(parents=True)
        (root / TEST_DIR).mkdir(parents=True)
        if runtime is not None:
            (root / "workenv" / "runtime.py").write_text(runtime, encoding="utf-8")
        for name, body in tests.items():
            (root / TEST_DIR / name).write_text(body, encoding="utf-8")
        return root

    def fake_tool(base, name, body):
        path = pathlib.Path(base) / name
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(0o755)
        return path

    controls = []

    def expect(label, got, fragment):
        controls.append(label)
        hits = [f for f in got if fragment in f]
        if len(hits) != 1 or len(got) != 1:
            problems.append(f"{label}: wanted exactly one failure containing {fragment!r}, "
                            f"got {got!r}")

    with tempfile.TemporaryDirectory(prefix="workenv-selftest-") as scratch:
        scratch = pathlib.Path(scratch)

        def case(name):
            path = scratch / name
            path.mkdir()
            return path

        # positive controls
        got, _ = unit_tests(tree(case("u-ok")), python)
        if got:
            problems.append(f"unit-tests positive control failed: {got!r}")
        got, _ = static_analysis(tree(case("s-ok")), ruff)
        if got:
            problems.append(f"static-analysis positive control failed: {got!r}")

        # unit-tests
        got, _ = unit_tests(tree(case("u-empty"), tests={}), python)
        expect("unit empty set", got, "unit-tests: empty subject set")
        got, _ = unit_tests(tree(case("u-helper"), tests={"helper.py": PASSING_TEST}), python)
        expect("unit file outside the pattern", got, "unit-tests: empty subject set")
        got, _ = unit_tests(tree(case("u-none"), tests={"test_none.py": NO_TESTS}), python)
        expect("unit zero tests", got, "test_none.py: ran 0 tests")
        got, _ = unit_tests(tree(case("u-skip"), tests={"test_skip.py": SKIPPED_TEST}), python)
        expect("unit all skipped", got, "test_skip.py: every test was skipped")
        got, _ = unit_tests(tree(case("u-fail"), tests={"test_fail.py": FAILING_TEST}), python)
        expect("unit failing test", got, "test_fail.py: 1 test(s) failed")
        got, _ = unit_tests(tree(case("u-exit"), tests={"test_exit.py": EXITS_ZERO}), python)
        expect("unit file that exits 0 before any test", got, "test_exit.py: no result was written")
        got, _ = unit_tests(tree(case("u-import"), tests={"test_imp.py": BROKEN_IMPORT}), python)
        expect("unit import error", got, "test_imp.py: no result was written")
        both = tree(case("u-both"),
                    tests={"test_ok.py": PASSING_TEST, "test_skip.py": SKIPPED_TEST})
        got, _ = unit_tests(both, python)
        expect("unit one good file does not cover a skipped one", got,
               "test_skip.py: every test was skipped")
        got, _ = unit_tests(tree(case("u-absent")), scratch / "no-such-python")
        expect("unit absent interpreter", got, "unit-tests: tool absent")
        got, _ = unit_tests(tree(case("u-hang"), tests={"test_hang.py": NEVER_RETURNS}), python,
                            timeout=1)
        expect("unit file that never returns", got, "test_hang.py: did not complete")
        mute = fake_tool(scratch, "python-mute", "exit 3\n")
        got, _ = unit_tests(tree(case("u-mute")), mute)
        expect("unit interpreter that does not answer", got, "did not answer (exit 3)")
        old = fake_tool(scratch, "python-old", "echo 3.9\n")
        got, _ = unit_tests(tree(case("u-old")), old)
        expect("unit interpreter below the floor", got, "unit-tests: tool version")

        # static-analysis
        got, _ = static_analysis(tree(case("s-noruntime"), runtime=None), ruff)
        expect("static empty runtime tree", got, "empty subject set: no Python file under workenv/")
        got, _ = static_analysis(tree(case("s-notests"), tests={}), ruff)
        expect("static empty tests tree", got,
               "empty subject set: no Python file under gates/workenv/")
        got, _ = static_analysis(tree(case("s-absent")), scratch / "no-such-ruff")
        expect("static absent tool", got, "static-analysis: tool absent")
        got, _ = static_analysis(tree(case("s-none")), None)
        expect("static no tool on PATH", got, "static-analysis: tool absent")
        got, _ = static_analysis(tree(case("s-mute")), mute)
        expect("static tool that does not answer", got, "--version did not answer (exit 3)")
        other = fake_tool(scratch, "ruff-other", "echo 'ruff 0.0.1'\n")
        got, _ = static_analysis(tree(case("s-other"), runtime=UNDEFINED_NAME), other)
        expect("static other version", got, "static-analysis: tool version")
        longer = fake_tool(scratch, "ruff-longer", f"echo 'ruff {RUFF_PIN}0'\n")
        got, _ = static_analysis(tree(case("s-longer")), longer)
        expect("static version that only starts with the pin", got,
               "static-analysis: tool version")
        got, _ = static_analysis(tree(case("s-bad"), runtime=UNDEFINED_NAME), ruff)
        expect("static planted violation", got, "workenv/runtime.py")
        if got and "F821" not in got[0]:
            problems.append(f"static planted violation: F821 not named in {got!r}")
        got, _ = static_analysis(tree(case("s-badtest"),
                                      tests={"test_ok.py": PASSING_TEST + "import os\n"}), ruff)
        expect("static planted violation in a test file", got, "gates/workenv/test_ok.py")
        answers_version = f'[ "$1" = --version ] && {{ echo "ruff {RUFF_PIN}"; exit 0; }}\n'
        crash = fake_tool(scratch, "ruff-crash", answers_version + "exit 2\n")
        hang = fake_tool(scratch, "ruff-hang", answers_version + "exec sleep 30\n")
        got, _ = static_analysis(tree(case("s-hang")), hang, timeout=1)
        expect("static tool that never returns", got, "tool did not complete: TimeoutExpired")
        got, _ = static_analysis(tree(case("s-crash")), crash)
        expect("static tool that judges nothing", got, "static-analysis: tool did not complete")

    for line in problems:
        print(f"SELF-TEST FAIL: {line}")
    if not problems:
        unit = sum(1 for label in controls if label.startswith("unit "))
        print(f"workenv gate self-test OK: 2 positive controls, {unit} unit-test and "
              f"{len(controls) - unit} static-analysis negative controls")
    return 1 if problems else 0


def main():
    if len(sys.argv) == 4 and sys.argv[1] == RUN_ONE:
        return run_one(sys.argv[2], sys.argv[3])
    if "--self-test" in sys.argv:
        return self_test()
    if len(sys.argv) > 1:
        print(f"usage: {sys.argv[0]} [--self-test]")
        return 2
    failures, report = check(REPO, find_ruff(), sys.executable)
    for line in report:
        print(line)
    for line in failures:
        print(f"FAIL: {line}")
    if not failures:
        print("WORKENV OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
