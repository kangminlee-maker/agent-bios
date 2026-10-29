#!/usr/bin/env python3
"""The declared Python floor is judged by a real interpreter of that floor.

Shipped `launch/agent-launch.py` has used PEP 701 f-strings since 47ec804 (2026-09-11),
so v0.19.0-v0.19.3 needed Python 3.12 while every document in the tree said 3.11+.
Nothing gated the floor, and the obvious gate would not have caught it:
`ast.parse(feature_version=(3, 11))` accepts PEP 701 happily. Only a real interpreter of
the floor version decides whether this tree parses there, which is why this gate shells
out to one instead of reasoning about syntax.

One owner, two judgements:

  owner         `DEPENDENCIES.md` states the floor once, in its hand-written Runtime
                tools section, as `**Python floor: X.Y**`. This gate holds no version
                number of its own -- it reads that line, and fails without exactly one.
  declarations  every tracked live text file is scanned for a statement of the floor,
                and each one must name the owner's version.
  parse         every tracked shipped `.py` (`package.json` `files[]`) and every tracked
                author-side `.py` is compiled by a real floor interpreter. The two sets
                are reported separately and each must be non-empty, because a set that
                judged nothing satisfies any claim about it.

DEBT, not design. A restatement in Bash, in English or Korean prose, or in a translated
installer string cannot import a Python constant, so those sites are *gated* here rather
than *generated* from the owner. AGENTS.md ("Where authority lives") calls that a debt:
the day a declaration can be generated from the owner, generate it and delete its row
from this scan.

A MISSING FLOOR INTERPRETER BLOCKS. It does not disclose and pass. A run with no
interpreter of the floor version has judged nothing about parsing, and reporting that
run clean is exactly the "green about nothing" this repository's gates exist to refuse.
There is no environment bypass; `AGENT_BIOS_FLOOR_PYTHON` only says *where* to look, and
its version is verified against the owner before it is used. The cost is real and
deliberate: an author machine without the floor interpreter cannot commit until it
installs one (`uv python install X.Y`).

Tracked-file discovery deliberately differs by root. For the repository itself the gate
asks git, so under the commit hook it judges the staged index snapshot like every other
git-reading leg -- which also means an untracked new file is not scanned (`git add -N`
before trusting a result by hand). For any other root, including the self-test's throwaway
trees, it walks the filesystem and never invokes git: a `git ls-files` run inside a scratch
directory would inherit the hook's exported `GIT_DIR` and answer about the real repository.

  python3 gates/check-python-floor.py              # judge the tree
  python3 gates/check-python-floor.py --self-test   # positive control, then 10 negatives
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
OWNER_DOC = "DEPENDENCIES.md"
OWNER = re.compile(r"^\*\*Python floor: (\d+)\.(\d+)\*\*", re.MULTILINE)

# Two scopes, because the two judgements are about different things.
#
# SKIP is for DECLARATIONS. A dated record states the floor as it was on its day and is
# never edited (AGENTS.md §1, §2); a decision ledger row, a research note and a benchmark
# write-up are the same kind of claim about a past tree.
#
# DATED is for PARSING, and is much narrower on purpose. Whether a file parses on the
# floor is a fact about the file as it stands now, not about what its prose claims, so
# every live author-side Python is judged -- `benchmarks/` (36 files), `research/` (10)
# and `decisions/record-decision.py` are live tooling, and exempting them from the
# compile leg would leave 47 files unjudged for no reason. Only `design/` is excluded:
# its 19 Python files are snapshots of earlier gates, which AGENTS.md forbids editing, so
# a syntax failure there could not be fixed without violating the rule that keeps them.
SKIP = ("design/", "decisions/", "research/", "benchmarks/")
DATED = ("design/",)

# A statement of the floor is a version DECORATED AS A MINIMUM. The decoration is what
# keeps the scan honest: an undecorated `3.N` near the word "python" is usually another
# fact entirely -- a wheel's `requires_python`, a Windows CI pin, an observed local
# version report, or the 3.9 that stock macOS ships -- and a scan that flagged those
# would need some fifty exemptions, which is a list long enough to hide the one real
# stale declaration. Measured on the tree: these patterns find 60 sites and no false
# positives, where the proximity scan they replaced found 96 of which 50 were noise.
MINIMUM = r"(?:\+|\s*(?:or newer|or later|이상|以降))"
PATTERNS = (
    ("prose", re.compile(r"(?i)python\s*3\.(\d+)" + MINIMUM)),
    ("prose-argv", re.compile(r"(?i)python3 3\.(\d+)" + MINIMUM)),
    ("shell-compare", re.compile(r"(?i)python3\s*(?:&gt;|>)=\s*3\.(\d+)")),
    ("version_info", re.compile(r"version_info\s*[<>]=?\s*\(\s*3,\s*(\d+)\s*\)")),
    ("manifest", re.compile(r"python_requirement[^\n]{0,40}>=\s*3\.(\d+)")),
    ("builder", re.compile(r'"--python-version",\s*"3\.(\d+)"')),
    ("bare-minimum", re.compile(r"(?i)must be\s+3\.(\d+)" + MINIMUM)),
)

# Licensed asymmetry, as data naming each exact site: path, scan kind, the literal that
# must appear in the matched text, and the reason. A declaration that differs from the
# owner fails unless an entry here names it, and an entry that names nothing fails as a
# stale licence -- a licence naming no site would excuse every site (AGENTS.md, ontology
# rounds: "a declaration naming no site excuses every site").
ASYMMETRY = (
    ("compose/ui_runtime/manifest.json", "manifest", ">=3.11",
     "the shipped UI wheels are all py3-none-any pure Python and really do run on 3.11, "
     "so the bundle's own requirement is not this repository's floor. Raising it means "
     "gates/build-ui-runtime.py --build --refresh, which re-resolves every dependency "
     "over the network and would ride unrelated wheel bumps on a floor change"),
    ("compose/instructions_ui_runtime.py", "manifest", ">=3.11",
     "the loader compares the manifest's requirement literally, so this moves only when "
     "the manifest it validates moves"),
    ("gates/build-ui-runtime.py", "manifest", ">=3.11",
     "the builder writes that same manifest field; one value, one owner"),
    ("gates/build-ui-runtime.py", "builder", '"3.11"',
     "pip resolves the pure-Python wheels against the lowest supported version; a lower "
     "resolution target is a superset constraint and stays valid on the floor"),
)

# Compiled in ONE subprocess per set: the floor interpreter costs ~25ms to start, and
# paying that per file would put a second on the umbrella's budget for nothing.
COMPILER = r"""
import sys
judged = 0
for raw in sys.stdin.read().splitlines():
    path = raw.strip()
    if not path:
        continue
    judged += 1
    try:
        compile(open(path, "rb").read(), path, "exec")
    except SyntaxError as exc:
        print(f"{path}:{exc.lineno}: {exc.msg}")
    except (OSError, ValueError) as exc:
        print(f"{path}: cannot be read as source: {exc}")
print(f"judged {judged}")
"""


def tracked(root: Path) -> list[str]:
    """Paths git has for the repository root; a filesystem walk for any other root."""
    if root == ROOT:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True)
        return [rel for rel in out.stdout.splitlines() if (root / rel).is_file()]
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        parts = path.relative_to(root).parts
        if ".git" in parts or "__pycache__" in parts:
            continue
        found.append(str(path.relative_to(root)))
    return found


def floor(root: Path) -> tuple[tuple[int, int], list[str]]:
    doc = root / OWNER_DOC
    if not doc.is_file():
        return (0, 0), [f"{OWNER_DOC}: missing, so the floor has no owner to read"]
    found = OWNER.findall(doc.read_text(encoding="utf-8"))
    if len(found) != 1:
        return (0, 0), [f"{OWNER_DOC}: needs exactly one `**Python floor: X.Y**` line, found {len(found)}"]
    return (int(found[0][0]), int(found[0][1])), []


def declarations(root: Path, files: list[str]) -> list[tuple[str, int, str, int, str]]:
    rows = []
    for rel in files:
        if rel.startswith(SKIP):
            continue
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for kind, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                rows.append((rel, line, kind, int(match.group(1)), match.group(0)))
    return sorted(rows)


def check_declarations(rows, want: tuple[int, int], exemptions) -> list[str]:
    problems: list[str] = []
    if not rows:
        problems.append("the declaration scan judged nothing: no statement of the floor was found at all")
    used = set()
    for rel, line, kind, minor, text in rows:
        licence = next((e for e in exemptions if e[0] == rel and e[1] == kind and e[2] in text), None)
        if licence is not None:
            used.add(licence)
            continue
        if (3, minor) != want:
            problems.append(f"{rel}:{line}: declares Python 3.{minor} ({kind}: {text.strip()!r}) "
                            f"but {OWNER_DOC} owns {want[0]}.{want[1]}")
    for entry in exemptions:
        if entry not in used:
            problems.append(f"stale licensed asymmetry: {entry[0]} ({entry[1]}, {entry[2]!r}) "
                            f"matches no declaration; delete the entry or fix the site")
    return problems


def shipped_python(root: Path, files: set[str]) -> list[str]:
    try:
        entries = json.loads((root / "package.json").read_text(encoding="utf-8")).get("files", [])
    except (OSError, ValueError) as exc:
        raise ValueError(f"package.json: cannot read files[]: {exc}") from exc
    found = set()
    for entry in entries:
        entry = entry.rstrip("/")
        for rel in files:
            if rel == entry and rel.endswith(".py"):
                found.add(rel)
            elif rel.startswith(entry + "/") and rel.endswith(".py"):
                found.add(rel)
    return sorted(found)


def floor_interpreter(want: tuple[int, int]) -> tuple[str | None, list[str]]:
    """Name a real interpreter of the floor, or say what is missing. Never guesses."""
    tag = f"{want[0]}.{want[1]}"
    candidates: list[str] = []
    named = os.environ.get("AGENT_BIOS_FLOOR_PYTHON")
    if named:
        candidates.append(named)
    found = shutil.which(f"python{tag}")
    if found:
        candidates.append(found)
    if sys.version_info[:2] == want:
        candidates.append(sys.executable)
    uv = Path.home() / ".local/share/uv/python"
    candidates.extend(str(p) for p in sorted(uv.glob(f"cpython-{tag}*/bin/python{tag}")))
    for candidate in candidates:
        try:
            probe = subprocess.run([candidate, "-I", "-c", 'import sys; print("%d.%d" % sys.version_info[:2])'],
                                   capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0 and probe.stdout.strip() == tag:
            return candidate, []
    return None, [f"no Python {tag} interpreter found, so nothing judged whether this tree parses on the "
                  f"floor {OWNER_DOC} declares. Install one (`uv python install {tag}`) or name it in "
                  f"AGENT_BIOS_FLOOR_PYTHON. Checked: {candidates or ['nothing on PATH or under uv']}"]


def compile_set(interpreter: str, root: Path, label: str, members: list[str]) -> list[str]:
    if not members:
        return [f"the {label} Python set judged nothing: an empty set parses on every version"]
    run = subprocess.run([interpreter, "-I", "-c", COMPILER], cwd=root, input="\n".join(members),
                         capture_output=True, text=True)
    lines = [line for line in run.stdout.splitlines() if line.strip()]
    counted = [line for line in lines if line.startswith("judged ")]
    failures = [line for line in lines if not line.startswith("judged ")]
    problems = [f"{label}: {failure} (does not parse on the floor interpreter)" for failure in failures]
    if run.returncode != 0 or len(counted) != 1:
        problems.append(f"{label}: the floor interpreter did not report a judgement "
                        f"(exit {run.returncode}): {run.stderr.strip()[:400]}")
    elif int(counted[0].split()[1]) != len(members):
        problems.append(f"{label}: asked for {len(members)} files, the floor interpreter judged "
                        f"{counted[0].split()[1]}")
    return problems


def run(root: Path = ROOT, *, exemptions=ASYMMETRY, finder=floor_interpreter, report=False) -> list[str]:
    want, problems = floor(root)
    if problems:
        return problems
    files = tracked(root)
    if not files:
        return [f"{root}: no tracked files, so every check below would pass over nothing"]
    rows = declarations(root, files)
    problems += check_declarations(rows, want, exemptions)

    try:
        ships = shipped_python(root, set(files))
    except ValueError as exc:
        return problems + [str(exc)]
    shipped_set = set(ships)
    author = sorted(rel for rel in files
                    if rel.endswith(".py") and rel not in shipped_set and not rel.startswith(DATED))
    interpreter, missing = finder(want)
    if missing:
        problems += missing
    else:
        problems += compile_set(interpreter, root, "shipped", ships)
        problems += compile_set(interpreter, root, "author-side", author)
    if report:
        print(f"check-python-floor: floor {want[0]}.{want[1]} from {OWNER_DOC}; "
              f"{len(rows)} declaration(s) in {len({r[0] for r in rows})} file(s), "
              f"{len(exemptions)} licensed asymmetry; {len(ships)} shipped and {len(author)} author-side "
              f"Python compiled by {interpreter or 'NO FLOOR INTERPRETER'}")
    return problems


def self_test() -> int:
    """Synthetic trees, not a copy of the repository: each control needs its own shape."""
    newer = "def f[T = int]() -> T: ...\n"   # PEP 696 type-parameter default, 3.13+
    # NOT a usable control: a PEP 701 nested-quote f-string compiles on 3.12, so planting
    # one against a 3.12 floor is a control that can never fire.
    #
    # Every stale version below is ASSEMBLED rather than written, because this gate scans
    # its own source like any other tracked file: a version written out here, decorated as
    # a minimum, is a declaration, and the gate would fail on itself. This very comment
    # had to be reworded for that reason. It is not cosmetic -- the first run of this gate
    # passed only because the file was still untracked and therefore unscanned, which is
    # the "green about nothing" AGENTS.md warns about, found by running the gate against
    # a copy of the tree where nothing is untracked. The patterns need the digits
    # adjacent to their decoration, so a substituted `{stale}` matches nothing at rest
    # and the fixture still carries a real declaration once written to disk.
    stale = "3." + "11"
    base = {
        OWNER_DOC: "# Dependencies\n\n## Runtime tools\n\n**Python floor: 3.12** — the owner.\n\n"
                   "Python 3.12+ is required.\n",
        "package.json": json.dumps({"files": ["pkg/", "tool.py"]}),
        "pkg/shipped.py": "import sys\nif sys.version_info < (3, 12):\n    raise SystemExit(1)\n",
        "tool.py": 'print("Python 3.12 or newer")\n',
        "gate/author.py": "VALUE = 1\n",
        "README.md": "Needs Python 3.12+.\n",
        "design/old.md": f"Python {stale}+ was the floor then.\n",
    }
    licensed = (("pkg/shipped.py", "manifest", f">={stale}", "a synthetic licensed site"),)
    base["pkg/shipped.py"] += 'PIN = {"python_requirement": ">=' + stale + '"}\n'
    failures: list[str] = []

    def tree(changes: dict[str, str | None]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="python-floor-", dir="/private/tmp" if Path("/private/tmp").is_dir() else None))
        merged = dict(base)
        merged.update(changes)
        for name, body in merged.items():
            if body is None:
                continue
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(body, encoding="utf-8")
        return root

    clean = tree({})
    try:
        result = run(clean, exemptions=licensed)
        if result:
            failures.append(f"positive control did not pass: {result}")
        # Quiet controls: the two scopes must actually differ. A dated snapshot neither
        # declares the floor nor has to parse on it, and saying so is worth a control
        # because both exclusions are invisible when they work.
        quiet = [("dated declaration", "design/snapshot.md", f"Python {stale}+ was required then.\n"),
                 ("dated Python snapshot", "design/snapshot.py", newer)]
        for label, name, body in quiet:
            (clean / name).parent.mkdir(parents=True, exist_ok=True)
            (clean / name).write_text(body, encoding="utf-8")
            result = run(clean, exemptions=licensed)
            if result:
                failures.append(f"{label} under design/ was judged: {result}")
            (clean / name).unlink()
    finally:
        shutil.rmtree(clean)

    cases = [
        ("shipped file newer than the floor", {"pkg/newer.py": newer}, licensed, floor_interpreter,
         "shipped: pkg/newer.py"),
        ("author-side file newer than the floor", {"gate/newer.py": newer}, licensed, floor_interpreter,
         "author-side: gate/newer.py"),
        ("a declaration disagrees", {"README.md": f"Needs Python {stale}+.\n"}, licensed, floor_interpreter,
         f"README.md:1: declares Python {stale}"),
        ("a shipped declaration disagrees", {"tool.py": f'print("Python {stale} or newer")\n'}, licensed,
         floor_interpreter, f"tool.py:1: declares Python {stale}"),
        ("owner line removed", {OWNER_DOC: "# Dependencies\n\nNo floor here.\n"}, licensed, floor_interpreter,
         "needs exactly one"),
        ("owner stated twice", {OWNER_DOC: base[OWNER_DOC] + "\n**Python floor: 3.13** — again.\n"}, licensed,
         floor_interpreter, "found 2"),
        ("owner document missing", {OWNER_DOC: None}, licensed, floor_interpreter, f"{OWNER_DOC}: missing"),
        ("stale licensed asymmetry", {}, licensed + (("pkg/gone.py", "builder", f'"{stale}"', "names nothing"),),
         floor_interpreter, "stale licensed asymmetry: pkg/gone.py"),
        ("no declaration anywhere", {OWNER_DOC: "# Dependencies\n\n**Python floor: 3.12** — the owner.\n",
                                     "README.md": "Nothing stated.\n", "tool.py": "print(1)\n",
                                     "pkg/shipped.py": "VALUE = 2\n"}, (), floor_interpreter,
         "declaration scan judged nothing"),
        ("nothing shipped", {"package.json": json.dumps({"files": []})}, licensed, floor_interpreter,
         "shipped Python set judged nothing"),
        ("no author-side Python", {"gate/author.py": None}, licensed, floor_interpreter,
         "author-side Python set judged nothing"),
        ("floor interpreter absent", {}, licensed, lambda want: (None, ["no Python 3.12 interpreter found"]),
         "no Python 3.12 interpreter found"),
    ]
    for label, changes, exempt, finder, expected in cases:
        root = tree(changes)
        try:
            result = run(root, exemptions=exempt, finder=finder)
        except Exception as exc:                      # a control must fail by name, never crash
            failures.append(f"{label}: raised {type(exc).__name__}: {exc}")
            continue
        finally:
            shutil.rmtree(root)
        if not any(expected in problem for problem in result):
            failures.append(f"{label}: expected a failure naming {expected!r}, got {result}")
    if failures:
        for failure in failures:
            print(f"check-python-floor --self-test: FAIL {failure}")
        return 1
    print(f"check-python-floor --self-test: OK (positive control, {len(cases)} negative controls)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    started = time.monotonic()
    problems = run(args.root, report=True)
    for problem in problems:
        print(f"check-python-floor: FAIL {problem}")
    print(f"check-python-floor: {'FAIL' if problems else 'OK'} in {time.monotonic() - started:.1f}s")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
