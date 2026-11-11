#!/usr/bin/env python3
"""Every session-distill file that offers `--self-test` has a leg in the commit hook's umbrella.

A suite the umbrella does not run is green about nothing at commit time. WP-10's runlib/derive.py and
runlib/delivery.py passed their self-tests in a hand run before each hook while the hook itself never ran them
(012ca20), and plain-asks.py had no leg either. This gate makes the coverage decidable.

The subjects are the Python files under session-distill/ whose argv handling accepts `--self-test`, read from the
syntax tree: an argparse registration (`add_argument("--self-test", ...)`), or a comparison that holds the flag
(`sys.argv[1:] == ["--self-test"]`, `"--self-test" not in sys.argv[1:]`, `sys.argv[1] == "--self-test"`). A file that
only names the flag in prose or a comment (runlib/entry.py) offers no such route and is no subject. A leg is a
`python3 [flags] <path> --self-test` line of gates/check-parity.sh. Excluded paths carry their reasons (EXCLUDED).

  check-self-test-legs.py              the tree it runs in: SELF_TEST_UNLEGGED <path> for each file with no leg,
                                       SELF_TEST_UNPARSED for a file the tree cannot be read from, SUBJECTS_EMPTY when
                                       no file is a subject; exit 1 on any
  check-self-test-legs.py --self-test  planted trees, the positive control first
"""
import ast
import pathlib
import re
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SUBJECT_ROOT = "session-distill"
UMBRELLA = "gates/check-parity.sh"
FLAG = "--self-test"
EXCLUDED = {
    "session-distill/out/": "regenerable pipeline snapshots (AGENTS.md, What goes where): run output, not code the umbrella runs",
}
LEG = re.compile(r"python3\s+(?:-\S+\s+)*(\S+\.py)\s+--self-test\b")


def holds_flag(node):
    """The flag itself, or a list, tuple or set display holding it."""
    if isinstance(node, ast.Constant):
        return node.value == FLAG
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(isinstance(e, ast.Constant) and e.value == FLAG for e in node.elts)
    return False


def accepts(source):
    """Whether a module's code offers the `--self-test` route (raises SyntaxError when it cannot be parsed)."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare) and any(holds_flag(x) for x in [node.left, *node.comparators]):
            return True
        if isinstance(node, ast.Call) and node.args and holds_flag(node.args[0]):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
            if name == "add_argument":
                return True
    return False


def subjects(root, excluded=None):
    """`(subjects, unparsed)`: the files under SUBJECT_ROOT offering the route, and those that cannot be parsed."""
    excluded = EXCLUDED if excluded is None else excluded
    root = pathlib.Path(root)
    found, unparsed = [], []
    for path in sorted((root / SUBJECT_ROOT).rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or any(rel.startswith(prefix) for prefix in excluded):
            continue
        try:
            if accepts(path.read_text(encoding="utf-8")):
                found.append(rel)
        except (SyntaxError, UnicodeDecodeError) as exc:
            unparsed.append((rel, exc.__class__.__name__))
    return found, unparsed


def legs(root):
    return set(LEG.findall((pathlib.Path(root) / UMBRELLA).read_text(encoding="utf-8")))


def problems(root, excluded=None):
    """`(problems, subjects)` of a tree."""
    found, unparsed = subjects(root, excluded)
    have = legs(root)
    out = [f"SELF_TEST_UNPARSED {rel}: {why}; whether it offers {FLAG} cannot be decided" for rel, why in unparsed]
    if not found and not unparsed:
        out.append(f"SUBJECTS_EMPTY: no file under {SUBJECT_ROOT}/ offers {FLAG}, so this gate judged nothing")
    out += [f"SELF_TEST_UNLEGGED {rel}: it accepts {FLAG}, and {UMBRELLA} declares no `python3 {rel} {FLAG}` leg"
            for rel in found if rel not in have]
    return out, found


def self_test():
    failures, ran = [], []

    def control(name, condition, detail=""):
        ran.append(name)
        if not condition:
            failures.append(f"{name}: {detail}")

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="self-test-legs-"))
    try:
        def tree(name, files, umbrella):
            root = scratch / name
            for rel, text in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            (root / UMBRELLA).parent.mkdir(parents=True, exist_ok=True)
            (root / UMBRELLA).write_text(umbrella, encoding="utf-8")
            return root

        files = {
            "session-distill/runlib/exact.py": 'import sys\nif __name__ == "__main__":\n    if sys.argv[1:] == ["--self-test"]:\n        pass\n',
            "session-distill/runlib/member.py": 'import sys\nif "--self-test" not in sys.argv[1:]:\n    sys.exit(2)\n',
            "session-distill/runlib/index.py": 'import sys\nif sys.argv[1] == "--self-test":\n    pass\n',
            "session-distill/tool.py": 'import argparse\nap = argparse.ArgumentParser()\nap.add_argument("--self-test", action="store_true")\n',
            "session-distill/runlib/prose.py": '"""Run it with --self-test, says the prose."""\n# a comment: --self-test\nTEXT = "--self-test"\n',
            "session-distill/out/run-1/snapshot.py": 'import sys\nif sys.argv[1:] == ["--self-test"]:\n    pass\n',
        }
        umbrella = "".join(f"  leg -q \"FAIL: {rel}\" \\\n    python3 {'-I ' if 'index' in rel else ''}{rel} --self-test\n"
                           for rel in ("session-distill/runlib/exact.py", "session-distill/runlib/member.py",
                                       "session-distill/runlib/index.py", "session-distill/tool.py"))
        good = tree("good", files, umbrella)
        got, found = problems(good)
        control("positive: four files offering --self-test in four shapes, each with a leg (one under -I), pass",
                got == [] and found == ["session-distill/runlib/exact.py", "session-distill/runlib/index.py",
                                        "session-distill/runlib/member.py", "session-distill/tool.py"], f"{got} {found}")
        control("a file that names the flag only in prose, a comment or a constant offers no route and is no subject",
                "session-distill/runlib/prose.py" not in found, f"{found}")
        control("an excluded snapshot is no subject, and the exclusion is what keeps it out",
                "session-distill/out/run-1/snapshot.py" not in found
                and "SELF_TEST_UNLEGGED session-distill/out/run-1/snapshot.py: it accepts --self-test, and "
                    "gates/check-parity.sh declares no `python3 session-distill/out/run-1/snapshot.py --self-test` leg"
                in problems(good, excluded={})[0], f"{problems(good, excluded={})[0]}")
        planted = tree("planted", {**files, "session-distill/runlib/new.py": files["session-distill/runlib/exact.py"]}, umbrella)
        control("negative: a self-testing module planted without a leg fails by name, and only it",
                problems(planted)[0] == ["SELF_TEST_UNLEGGED session-distill/runlib/new.py: it accepts --self-test, and "
                                         "gates/check-parity.sh declares no `python3 session-distill/runlib/new.py "
                                         "--self-test` leg"], f"{problems(planted)[0]}")
        unlegged_argparse = tree("argparse", files, umbrella.replace("session-distill/tool.py", "session-distill/other.py"))
        control("negative: an argparse --self-test with its leg gone fails by name",
                any(p.startswith("SELF_TEST_UNLEGGED session-distill/tool.py") for p in problems(unlegged_argparse)[0]),
                f"{problems(unlegged_argparse)[0]}")
        empty = tree("empty", {"session-distill/runlib/prose.py": files["session-distill/runlib/prose.py"]}, "")
        control("an empty subject set is SUBJECTS_EMPTY, never a pass", problems(empty)[0][:1] and
                problems(empty)[0][0].startswith("SUBJECTS_EMPTY"), f"{problems(empty)[0]}")
        broken = tree("broken", {**files, "session-distill/runlib/broken.py": "def (:\n"}, umbrella)
        control("a file whose syntax tree cannot be read is SELF_TEST_UNPARSED by name",
                any(p.startswith("SELF_TEST_UNPARSED session-distill/runlib/broken.py") for p in problems(broken)[0]),
                f"{problems(broken)[0]}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    for failure in failures:
        print(f"check-self-test-legs --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"check-self-test-legs --self-test: OK ({len(ran)} controls)")
    return 0


def main():
    got, found = problems(REPO)
    for line in got:
        print(f"FAIL: {line}")
    if got:
        return 1
    print(f"check-self-test-legs: OK ({len(found)} files under {SUBJECT_ROOT}/ offer {FLAG}, each with a leg in {UMBRELLA})")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    if sys.argv[1:]:
        print("usage: check-self-test-legs.py [--self-test]", file=sys.stderr)
        sys.exit(2)
    sys.exit(main())
