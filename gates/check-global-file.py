#!/usr/bin/env python3
"""Gate: the always-loaded global file stays under its ceiling (AGENTS.md section 8).

BLOCKS (exit 1) when `claude/CLAUDE.md` in the INDEX is larger than CEILING_BYTES, counted
as UTF-8 bytes. That is the only verdict; the decision and its evidence are in
design/session-distill/2026-10-21T0634--9b42df2--global-file-ceiling.md. Below the ceiling any
edit passes, so room freed by deleting or merging a rule can be reused, and the line count is
not limited. Whether a new line earns its place is a judgement, so every line the index holds
whose text the base (HEAD by default) does not is DISCLOSED, never blocked, and so is the
before/after size of `ko/claude/CLAUDE.md`. The base is read for those disclosures only: if it
cannot be read, the gate says so and the verdict stands.

Measurement comes before the verdict. A staged file that is ABSENT measures as empty and
passes, disclosed as absent. A staged file git cannot READ — a failing or unmerged index —
leaves no measurement: the gate names it (`CANNOT JUDGE`) and exits 2, because a gate that
judged nothing has not passed (design/session-distill/2026-10-21T0455--9410a1d--plan-addendum-wp14.md).

The index is read through git, not from disk, because git commits the index — a gate that
read the checkout would judge something else. Under the pre-commit hook the inherited
GIT_DIR / GIT_INDEX_FILE point at the hook's snapshot, which is what git reads here.
`--worktree` reads the file on disk instead, for an explicit look at unstaged work.

  --self-test   scratch repos built with every GIT_* variable scrubbed: the hook exports
                them, and a fixture built under them re-initialises the REAL repository.
                The positive case runs first; the boundary on both sides of the ceiling, each
                disclosure and the index-versus-disk distinction have a case that fails by
                name without it, the branch sets the code can emit are held against the
                records, and the real pre-commit hook is driven in a scratch clone with only
                its callees stubbed.
"""
import argparse
import ast
import importlib.util
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parent.parent
# The git readers live in the driver (`session-distill/runlib/gitread.py`), which ships, and this
# author-side gate imports them from there. The direction is AGENTS.md's: author-side imports
# shipped, never the reverse. Loaded by path because `session-distill` is not an importable package
# name, and this gate runs only from a checkout, where the file is present.
GITREAD_REL = "session-distill/runlib/gitread.py"
_gitread = importlib.util.spec_from_file_location("runlib_gitread", REPO / GITREAD_REL)
gitread = importlib.util.module_from_spec(_gitread)
_gitread.loader.exec_module(gitread)
git_blob, base_blob, current_blob, lines_of = (
    gitread.git_blob, gitread.base_blob, gitread.current_blob, gitread.lines_of)
# The ceiling (20 KiB) of design/session-distill/2026-10-21T0634--9b42df2--global-file-ceiling.md.
CEILING_BYTES = 20480
GLOBAL = "claude/CLAUDE.md"
KO = "ko/claude/CLAUDE.md"


def new_lines(base, current):
    """(number, text) of each line of `current` whose text the base never held — blank and
    whitespace-only lines included."""
    known = set(base)
    return [(n, line) for n, line in enumerate(current, 1) if line not in known]


def counts(raw):
    return ("-", "-") if raw is None else (len(lines_of(raw)), len(raw))


def ko_note(repo, worktree, base):
    """`lines a→b, bytes a→b` for the Korean reference when it differs from the base."""
    old, old_absent = base_blob(repo, base, KO)
    new, new_absent = current_blob(repo, KO, worktree)
    if old is None or new is None:  # a failed read leaves no measurement to disclose
        return None
    old, new = (None if old_absent else old), (None if new_absent else new)
    if old == new:
        return None
    (a_lines, a_bytes), (b_lines, b_bytes) = counts(old), counts(new)
    return f"lines {a_lines}→{b_lines}, bytes {a_bytes}→{b_bytes}"


def judge(repo, worktree, base):
    """Contract: the ceiling record — the one verdict is the staged file above CEILING_BYTES;
    every line the base lacks is disclosed. Returns (failures, errors, new lines, KO note,
    notes, staged size). `failures` is the verdict. `errors` are not verdicts — git could not
    read the staged file, so nothing was measured. An ABSENT side is no error, it measures as
    empty, and an unreadable base only silences the disclosures (`notes` says so); the staged
    side's rules are the WP-14 addendum's (design/session-distill/2026-10-21T0455--9410a1d--plan-addendum-wp14.md)."""
    failures, errors, found, notes = [], [], None, []
    old, old_absent = base_blob(repo, base, GLOBAL)
    new, new_absent = current_blob(repo, GLOBAL, worktree)
    where = "the worktree" if worktree else "the index"
    if new is None:
        errors.append(f"GLOBAL_FILE_UNREADABLE {GLOBAL} ({'worktree' if worktree else 'index'})")
    elif len(new) > CEILING_BYTES:
        failures.append(f"GLOBAL_BYTES_OVER_CEILING {len(new)}>{CEILING_BYTES}")
    if new is not None and new_absent:
        notes += [f"ABSENT: {GLOBAL} is not in {where}; measured as empty"]
    if old is None:
        notes += [f"BASE UNREADABLE: {base}:{GLOBAL} could not be read, so NEW LINES and KO SIZE "
                  f"are not disclosed; the verdict stands"]
    elif new is not None:
        if old_absent:
            notes += [f"ABSENT: {GLOBAL} is not in {base}; measured as empty"]
        found = new_lines(lines_of(old), lines_of(new))
    ko = None if old is None else ko_note(repo, worktree, base)
    return failures, errors, found, ko, notes, (None if new is None else len(new))


def scratch_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                           "-c", "commit.gpgsign=false", *args],
                          check=check, capture_output=True, text=True, env=scratch_env())


HAN = "\N{HANGUL SYLLABLE HAN}"  # multi-byte, so a byte count and a character count differ
BASE = "# Global\n- Rule one.\n- Rule two is longer than the others.\n- Rule three.\n"
KO_BASE = f"# Global (ko)\n- R{HAN}.\n- R{HAN * 2}.\n"


def fixture(root):
    repo = pathlib.Path(tempfile.mkdtemp(prefix="case-", dir=root))
    git(repo, "init", "-q")
    for rel, text in ((GLOBAL, BASE), (KO, KO_BASE)):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    return repo


def change(rel, fn, stage=True):
    def prep(repo):
        path = repo / rel
        path.write_text(fn(path.read_text(encoding="utf-8")), encoding="utf-8")
        if stage:
            git(repo, "add", rel)
    return prep


def sized(n):
    """ASCII text of exactly n bytes in distinct lines: 1000-byte lines, then one shorter one."""
    full, rest = divmod(n, 1000)
    return "".join(f"{i:03d}" + "x" * 996 + "\n" for i in range(full)) \
        + (("y" * (rest - 1) + "\n") if rest else "")


def fresh(text, base):
    """The lines of `text` whose text `base` does not hold — what NEW LINES must list."""
    known = set(base.split("\n"))
    return [line for line in text.split("\n")[:-1] if line not in known]


def put(text, stage=True, commit=False):
    def prep(repo):
        (repo / GLOBAL).parent.mkdir(parents=True, exist_ok=True)
        (repo / GLOBAL).write_text(text, encoding="utf-8")
        if stage:
            git(repo, "add", GLOBAL)
        if commit:
            git(repo, "commit", "-qm", "new base")
    return prep


def over_in_index_only(repo):
    put(sized(CEILING_BYTES + 1))(repo)
    (repo / GLOBAL).write_text(BASE, encoding="utf-8")


def emitted_branches():
    """(sink, code) of every `<sink>.append("GLOBAL_…")` in judge(), read from this file's
    source: what the code CAN say, not what the cases happened to provoke."""
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "judge")
    found = set()
    for call in ast.walk(fn):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) \
                and call.func.attr == "append" and isinstance(call.func.value, ast.Name):
            arg = call.args[0]
            head = arg.values[0] if isinstance(arg, ast.JoinedStr) else arg
            if isinstance(head, ast.Constant) and str(head.value).startswith("GLOBAL_"):
                found.add((call.func.value.id, head.value.split()[0]))
    return found


def self_test():
    problems = []
    two = "- Rule two is longer than the others.\n"
    near, at, over = sized(20000), sized(CEILING_BYTES), sized(CEILING_BYTES + 1)
    ko_grown = KO_BASE + f"- R{HAN * 3}.\n"
    ko_big = sized(25000)
    wide = sized(20400) + f"- {HAN * 50}\n"  # fewer characters than the ceiling, more bytes
    base_lines = BASE.split("\n")[:-1]
    block = {"GLOBAL_BYTES_OVER_CEILING"}

    def case(label, prep, code=0, codes=(), new=(), ko=None, flags=(), notes=()):
        return dict(label=label, prep=prep, code=code, codes=set(codes),
                    new=None if new is None else list(new), ko=ko, flags=list(flags),
                    notes=list(notes))

    def drop_global_from_head(repo):
        git(repo, "rm", "-q", GLOBAL)
        git(repo, "commit", "-qm", "drop")

    def base_lacks_file_index_has_it(repo):
        drop_global_from_head(repo)
        put(BASE)(repo)

    def corrupt_index(repo):
        (repo / ".git" / "index").write_bytes(b"not an index")

    def at_head_then(staged_text, base_text):
        def prep(repo):
            put(base_text, commit=True)(repo)
            put(staged_text)(repo)
        return prep

    at_plus_one = at.replace("x", "xx", 1)
    cases = [
        case("unchanged (positive control)", lambda repo: None),
        case("exactly at the ceiling passes", put(at), new=fresh(at, BASE)),
        case("one byte over the ceiling blocks", put(over), 1, block, fresh(over, BASE)),
        case("growth below the ceiling passes and is disclosed (freed room reused)",
             at_head_then(near + "- Rule four.\n", near), new=["- Rule four."]),
        case("a shrinking commit passes", at_head_then("".join(near.splitlines(True)[:-1]), near)),
        case("HEAD at the ceiling, one byte added, blocks",
             at_head_then(at_plus_one, at), 1, block, fresh(at_plus_one, at)),
        case("still over the ceiling after shrinking blocks (the size is the verdict)",
             at_head_then(sized(24000), sized(25000)), 1, block, []),
        case("bytes are counted, not characters", put(wide), 1, block, fresh(wide, BASE)),
        case("deletion plus a shorter unrelated line discloses the new line",
             change(GLOBAL, lambda t: t.replace(two, "") + "- Short.\n"), new=["- Short."]),
        case("reduction whose new line is whitespace-only",
             change(GLOBAL, lambda t: t.replace(two, " \n")), new=[" "]),
        case("Korean file grew, English unchanged", change(KO, lambda t: ko_grown),
             ko=f"lines 3→4, bytes {len(KO_BASE.encode())}→{len(ko_grown.encode())}"),
        case("Korean file above the ceiling does not block",
             change(KO, lambda t: ko_big),
             ko=f"lines 3→{len(lines_of(ko_big.encode()))}, bytes {len(KO_BASE.encode())}→{len(ko_big)}"),
        case("over the ceiling in the index, restored on disk (default reads the index)",
             over_in_index_only, 1, block, fresh(over, BASE)),
        case("over the ceiling in the index, restored on disk (--worktree reads the disk)",
             over_in_index_only, flags=["--worktree"]),
        case("over the ceiling on disk only (default reads the index)", put(over, stage=False)),
        case("over the ceiling on disk only (--worktree reads the disk)",
             put(over, stage=False), 1, block, fresh(over, BASE), flags=["--worktree"]),
        case("global file deleted in the index (measured as empty)",
             lambda repo: git(repo, "rm", "-q", "--cached", GLOBAL),
             notes=[f"ABSENT: {GLOBAL} is not in the index"]),
        case("global file deleted on disk (--worktree measures it as empty)",
             lambda repo: (repo / GLOBAL).unlink(), flags=["--worktree"],
             notes=[f"ABSENT: {GLOBAL} is not in the worktree"]),
        case("base revision unreadable: disclosed, the verdict stands", lambda repo: None,
             new=None, flags=["--base", "no-such-rev"],
             notes=[f"BASE UNREADABLE: no-such-rev:{GLOBAL} could not be read"]),
        case("base revision unreadable and the staged file over the ceiling blocks", put(over),
             1, block, None, flags=["--base", "no-such-rev"],
             notes=[f"BASE UNREADABLE: no-such-rev:{GLOBAL} could not be read"]),
        case("file on neither side (the base lacks it and the index lacks it)",
             drop_global_from_head,
             notes=[f"ABSENT: {GLOBAL} is not in HEAD", f"ABSENT: {GLOBAL} is not in the index"]),
        case("base revision lacks the file, the index holds it",
             base_lacks_file_index_has_it, new=base_lines,
             notes=[f"ABSENT: {GLOBAL} is not in HEAD"]),
        case("index unreadable", corrupt_index, 2, {"GLOBAL_FILE_UNREADABLE"}, None),
    ]
    # Contract assertions, each against a value or set copied once, here, and none absorbing
    # another. The ceiling record (design/session-distill/2026-10-21T0634--9b42df2--global-file-ceiling.md):
    # "may not exceed 20,480 bytes" and "blocks only a staged file above the ceiling" — one
    # verdict branch. The cannot-read code is not a verdict but the rule that a gate which
    # measured nothing must not report clean, kept for the staged side by the record and cited
    # to design/session-distill/2026-10-21T0455--9410a1d--plan-addendum-wp14.md.
    ceiling_record = 20480
    verdict_record = {"GLOBAL_BYTES_OVER_CEILING"}
    cannot_read_addendum = {"GLOBAL_FILE_UNREADABLE"}
    if CEILING_BYTES != ceiling_record:
        problems.append(f"CEILING_BYTES {CEILING_BYTES} differs from the record's {ceiling_record}")
    by_sink = {}
    for sink, code in emitted_branches():
        by_sink.setdefault(sink, set()).add(code)
    if by_sink.get("failures") != verdict_record:
        problems.append(f"verdict branches {sorted(by_sink.get('failures', ()))} differ from "
                        f"the record's {sorted(verdict_record)}")
    if by_sink.get("errors") != cannot_read_addendum:
        problems.append(f"cannot-read branches {sorted(by_sink.get('errors', ()))} differ from the "
                        f"addendum's {sorted(cannot_read_addendum)}")
    if set(by_sink) != {"failures", "errors"} or verdict_record & cannot_read_addendum:
        problems.append(f"the two sets must stay apart and be the only sinks: {sorted(by_sink)}")
    emitted_re = re.compile(r"^check-global-file: (?:FAIL|CANNOT JUDGE) (GLOBAL_[A-Z_]+)", re.M)

    def hook_control(root):
        """The commit gate through the REAL hook, without recursion: the scratch clone carries
        .githooks/pre-commit byte for byte and only what it calls (the two umbrella scripts)
        is replaced by stubs that run this gate alone, so the hook's own snapshot export of
        GIT_INDEX_FILE and GIT_DIR is what the gate reads."""
        real = REPO / ".githooks" / "pre-commit"
        if not real.is_file():
            problems.append("hook: .githooks/pre-commit is missing, so the commit path is untested")
            return
        repo = pathlib.Path(tempfile.mkdtemp(prefix="hook-", dir=root))
        git(repo, "init", "-q")
        stub = f'#!/usr/bin/env bash\nexec "{sys.executable}" gates/check-global-file.py\n'
        files = {GLOBAL: (BASE, 0o644), KO: (KO_BASE, 0o644),
                 ".githooks/pre-commit": (real.read_text(encoding="utf-8"), 0o755),
                 "gates/check-global-file.py": (pathlib.Path(__file__).read_text(encoding="utf-8"), 0o755),
                 # the git readers this gate imports from the driver, which is where they ship
                 GITREAD_REL: ((REPO / GITREAD_REL).read_text(encoding="utf-8"), 0o644),
                 "gates/check-parity.sh": (stub, 0o755), "gates/check-package.sh": (stub, 0o755)}
        for rel, (text, mode) in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(text, encoding="utf-8")
            (repo / rel).chmod(mode)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")  # before core.hooksPath is set, so no hook runs yet
        git(repo, "config", "core.hooksPath", ".githooks")

        def attempt(label, want_ok, want_text):
            head = git(repo, "rev-parse", "HEAD").stdout
            done = git(repo, "commit", "-qm", label, check=False)
            out = done.stdout + done.stderr
            moved = git(repo, "rev-parse", "HEAD").stdout != head
            if (done.returncode == 0) != want_ok or moved != want_ok:
                problems.append(f"hook: {label}: exit {done.returncode}, commit created {moved}, "
                                f"wanted {'a commit' if want_ok else 'a refusal'}: {out}")
            if want_text not in out:
                problems.append(f"hook: {label}: the hook output lacks {want_text!r}: {out}")

        # positive first: a reduction commits, and the gate demonstrably ran inside the hook
        change(GLOBAL, lambda t: t.replace("- Rule two is longer than the others.\n", ""))(repo)
        attempt("a reduction", True, "check-global-file: OK")
        # growth below the ceiling commits: the hook no longer ratchets
        change(GLOBAL, lambda t: t + "- Rule four.\n")(repo)
        attempt("growth below the ceiling", True, "check-global-file: OK")
        # a staged file over the ceiling is refused
        put(over)(repo)
        attempt("staged over the ceiling", False, "GLOBAL_BYTES_OVER_CEILING")
        # the disk file goes back to HEAD while the index keeps the excess: still refused
        head_text = git(repo, "show", f"HEAD:{GLOBAL}").stdout
        (repo / GLOBAL).write_text(head_text, encoding="utf-8")
        if git(repo, "diff", "--quiet", "HEAD", "--", GLOBAL, check=False).returncode != 0 \
                or git(repo, "diff", "--cached", "--quiet", "--", GLOBAL, check=False).returncode != 1:
            problems.append("hook: fixture error — the disk file must equal HEAD while the index differs")
        attempt("staged over the ceiling, disk restored to HEAD", False, "GLOBAL_BYTES_OVER_CEILING")

    with tempfile.TemporaryDirectory(prefix="check-global-file-") as root:
        # Control for the scrub, run first and under the hook's environment whether or not
        # the hook is present: building a fixture must leave the "outer" repository alone.
        outer = fixture(root)
        listing = ["git", "-C", str(outer), "config", "--local", "--list"]
        before = subprocess.run(listing, capture_output=True, text=True, env=scratch_env()).stdout
        inner = None
        with mock.patch.dict(os.environ, {"GIT_DIR": str(outer / ".git"),
                                          "GIT_WORK_TREE": str(outer)}):
            try:
                inner = fixture(root)
            except subprocess.CalledProcessError:
                pass
        after = subprocess.run(listing, capture_output=True, text=True, env=scratch_env()).stdout
        if before != after or inner is None or not (inner / ".git" / "HEAD").is_file():
            problems.append("scrub: a fixture built under GIT_DIR touched the outer repository")

        for c in cases:
            repo = fixture(root)
            c["prep"](repo)
            done = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()),
                                   "--repo", str(repo), *c["flags"]],
                                  capture_output=True, text=True, env=scratch_env())
            out, label = done.stdout, c["label"]
            got_new = [line.split(": ", 1)[1] for line in out.splitlines()
                       if line.startswith("  ") and line[2:3].isdigit()]
            got_ko = next((line[len("KO SIZE: "):] for line in out.splitlines()
                           if line.startswith("KO SIZE: ")), None)
            shown = [line for line in out.splitlines() if line.startswith(("ABSENT:", "BASE UNREADABLE:"))]
            if done.returncode != c["code"]:
                problems.append(f"{label}: exit {done.returncode}, wanted {c['code']}: {out[:600]}{done.stderr}")
            if set(emitted_re.findall(out)) != c["codes"]:
                problems.append(f"{label}: emitted codes differ from {sorted(c['codes'])}: {out[:600]}")
            if c["new"] is not None and got_new != c["new"]:
                problems.append(f"{label}: NEW LINES {len(got_new)} lines, wanted {len(c['new'])}: "
                                f"{[t[:20] for t in got_new][:4]} vs {[t[:20] for t in c['new']][:4]}")
            if (c["new"] is None) != ("NEW LINES:" not in out):
                problems.append(f"{label}: the NEW LINES block must be absent exactly when "
                                f"nothing was compared: {out[:600]}")
            if got_ko != c["ko"]:
                problems.append(f"{label}: KO SIZE {got_ko!r}, wanted {c['ko']!r}")
            if len(shown) != len(c["notes"]) or any(not any(line.startswith(n) for line in shown)
                                                    for n in c["notes"]):
                problems.append(f"{label}: the notes {shown} differ from {c['notes']!r}")
        hook_control(root)
    for problem in problems:
        print(f"check-global-file --self-test: FAIL {problem}")
    if not problems:
        print(f"check-global-file --self-test: OK (positive first, {len(cases) - 1} planted, "
              f"branch sets, scrub, real hook)")
    return 1 if problems else 0


def main(argv):
    ap = argparse.ArgumentParser(description="claude/CLAUDE.md may not exceed its byte ceiling.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--index", action="store_true", help="read the staged file (default)")
    mode.add_argument("--worktree", action="store_true", help="read the file on disk instead")
    ap.add_argument("--base", default="HEAD",
                    help="revision the NEW LINES and KO SIZE disclosures compare against (default HEAD)")
    ap.add_argument("--repo", type=pathlib.Path, default=REPO)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    failures, errors, found, ko, notes, size = judge(args.repo, args.worktree, args.base)
    if found is not None:
        print(f"NEW LINES: {len(found)}")
        for number, text in found:
            print(f"  {number}: {text}")
    for note in notes:
        print(note)
    if ko:
        print(f"KO SIZE: {ko}")
    for failure in failures:
        print(f"check-global-file: FAIL {failure}")
    for error in errors:
        print(f"check-global-file: CANNOT JUDGE {error}")
    if errors:
        return 2
    if failures:
        return 1
    print(f"check-global-file: OK ({GLOBAL} is {size} of {CEILING_BYTES} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
