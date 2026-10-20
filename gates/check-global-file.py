#!/usr/bin/env python3
"""Gate: the always-loaded global file only shrinks (AGENTS.md section 8, design 13.1).

Compares `claude/CLAUDE.md` in the INDEX with a base revision (HEAD by default) and BLOCKS
when its line count or its byte count grows (exit 1). Growth is the only block. Whether a
line is a faithful merge of removed ones is a judgement, so every line the index holds whose
text the base does not is DISCLOSED, never blocked: a deletion plus a shorter unrelated line
passes the count check and still appears there. `ko/claude/CLAUDE.md` is disclosed by size
alone and never changes the exit code.

Measurement comes before the verdict. A side on which the file is ABSENT — a staged deletion,
a base revision that lacks it, a commit with it on neither side — measures as empty and is
judged by the growth predicate, disclosed as absent. A side git cannot READ — an unresolvable
base revision, a failing or unmerged index — leaves no measurement: the gate names that side
(`CANNOT JUDGE`) and exits 2, because a gate that judged nothing has not passed. That is not a
third verdict (design/session-distill/2026-10-21T0455--9410a1d--plan-addendum-wp14.md).

The index is read through git, not from disk, because git commits the index — a gate that
read the checkout would judge something else. Under the pre-commit hook the inherited
GIT_DIR / GIT_INDEX_FILE point at the hook's snapshot, which is what git reads here.
`--worktree` reads the file on disk instead, for an explicit look at unstaged work.

  --self-test   scratch repos built with every GIT_* variable scrubbed: the hook exports
                them, and a fixture built under them re-initialises the REAL repository.
                The positive case runs first; each blocking code, each disclosure and the
                index-versus-disk distinction has a case that fails by name without it, the
                branch set the code can emit is held against design 13.1, and the real
                pre-commit hook is driven in a scratch clone with only its callees stubbed.
"""
import argparse
import ast
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parent.parent
GLOBAL = "claude/CLAUDE.md"
KO = "ko/claude/CLAUDE.md"


def git_blob(repo, spec):
    """The bytes of `REV:path` (or `:path`, the index), or None when git cannot read it."""
    done = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", spec],
                          capture_output=True)
    return done.stdout if done.returncode == 0 else None


def base_blob(repo, base, rel):
    """(bytes, absent) for `rel` at `base`. A revision that lacks the path is absent and
    measures as empty. Bytes are None only when git cannot resolve the revision or read the
    tree, which is no measurement at all."""
    resolved = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
                               f"{base}^{{commit}}"], capture_output=True)
    if resolved.returncode != 0:
        return None, False
    listing = subprocess.run(["git", "-C", str(repo), "ls-tree", "--full-tree", "-z",
                              resolved.stdout.strip().decode(), "--", rel], capture_output=True)
    if listing.returncode != 0:
        return None, False
    entries = [e for e in listing.stdout.split(b"\0") if e]
    if not entries:
        return b"", True
    mode, kind, oid = entries[0].split(b"\t", 1)[0].split(b" ")
    return (git_blob(repo, oid.decode()) if kind == b"blob" else None), False


def current_blob(repo, rel, worktree):
    """(bytes, absent). A path the index (or disk) lacks is absent and measures as empty — a
    deletion is a reduction. Bytes are None only when git or the disk cannot answer, which
    is no measurement at all."""
    if worktree:
        try:
            return (pathlib.Path(repo) / rel).read_bytes(), False
        except FileNotFoundError:
            return b"", True
        except OSError:
            return None, False
    listing = subprocess.run(["git", "-C", str(repo), "ls-files", "--stage", "-z", "--", rel],
                             capture_output=True)
    if listing.returncode != 0:
        return None, False
    entries = [e for e in listing.stdout.split(b"\0") if e]
    if not entries:
        return b"", True
    if any(e.split(b"\t", 1)[0].split(b" ")[2] != b"0" for e in entries):
        return None, False  # unmerged: the index holds no single version to measure
    return git_blob(repo, f":{rel}"), False


def lines_of(raw):
    text = raw.decode("utf-8", "replace").split("\n")
    return text[:-1] if text[-1] == "" else text


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
    """Contract: design 13.1 — blocks when the line count or the byte count grows; discloses
    every line the base lacks. Returns (failures, errors, new lines, KO note, absent sides).
    `failures` are growth verdicts. `errors` are not verdicts — git could not read a side, so
    nothing was compared and the new-lines value is None; an ABSENT side is no error, it
    measures as empty (design/session-distill/2026-10-21T0455--9410a1d--plan-addendum-wp14.md)."""
    failures, errors, found, sides = [], [], None, []
    old, old_absent = base_blob(repo, base, GLOBAL)
    new, new_absent = current_blob(repo, GLOBAL, worktree)
    if old is None:
        errors.append(f"GLOBAL_BASE_UNREADABLE {base}:{GLOBAL}")
    elif new is None:
        errors.append(f"GLOBAL_FILE_UNREADABLE {GLOBAL} ({'worktree' if worktree else 'index'})")
    else:
        (a_lines, a_bytes), (b_lines, b_bytes) = counts(old), counts(new)
        if b_lines > a_lines:
            failures.append(f"GLOBAL_LINES_GREW {a_lines}→{b_lines}")
        if b_bytes > a_bytes:
            failures.append(f"GLOBAL_BYTES_GREW {a_bytes}→{b_bytes}")
        found = new_lines(lines_of(old), lines_of(new))
        sides = ([base] if old_absent else []) + (
            [("the worktree" if worktree else "the index")] if new_absent else [])
    # No base, no comparison: against an unreadable base a size note would only be noise.
    ko = None if old is None else ko_note(repo, worktree, base)
    return failures, errors, found, ko, sides


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


def grown_in_index_only(repo):
    change(GLOBAL, lambda t: t + "- Rule four.\n")(repo)
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
    ko_grown = KO_BASE + f"- R{HAN * 3}.\n"
    both = {"GLOBAL_LINES_GREW", "GLOBAL_BYTES_GREW"}

    def case(label, prep, code=0, codes=(), new=(), ko=None, flags=(), notes=()):
        return dict(label=label, prep=prep, code=code, codes=set(codes),
                    new=None if new is None else list(new), ko=ko, flags=list(flags),
                    notes=list(notes))

    four = change(GLOBAL, lambda t: t + "- Rule four.\n")
    four_disk = change(GLOBAL, lambda t: t + "- Rule four.\n", stage=False)

    def drop_global_from_head(repo):
        git(repo, "rm", "-q", GLOBAL)
        git(repo, "commit", "-qm", "drop")

    def base_lacks_file_index_has_it(repo):
        drop_global_from_head(repo)
        (repo / GLOBAL).parent.mkdir(parents=True, exist_ok=True)  # git rm removed the empty dir
        (repo / GLOBAL).write_text(BASE, encoding="utf-8")
        git(repo, "add", GLOBAL)

    def corrupt_index(repo):
        (repo / ".git" / "index").write_bytes(b"not an index")

    cases = [
        case("unchanged (positive control)", lambda repo: None),
        case("added line", four, 1, both, ["- Rule four."]),
        case("added line, bytes shrunk elsewhere",
             change(GLOBAL, lambda t: t.replace(two, "- Rule two.\n- R.\n")), 1,
             {"GLOBAL_LINES_GREW"}, ["- Rule two.", "- R."]),
        case("added word", change(GLOBAL, lambda t: t.replace("Rule one.", "Rule one now.")), 1,
             {"GLOBAL_BYTES_GREW"}, ["- Rule one now."]),
        case("same character count, more bytes",
             change(GLOBAL, lambda t: t.replace("Rule one.", f"Rule on{HAN}.")), 1,
             {"GLOBAL_BYTES_GREW"}, [f"- Rule on{HAN}."]),
        case("deleted line", change(GLOBAL, lambda t: t.replace(two, ""))),
        case("deletion plus a shorter unrelated line",
             change(GLOBAL, lambda t: t.replace(two, "") + "- Short.\n"), new=["- Short."]),
        case("reduction whose new line is whitespace-only",
             change(GLOBAL, lambda t: t.replace(two, " \n")), new=[" "]),
        case("Korean file grew, English unchanged", change(KO, lambda t: ko_grown),
             ko=f"lines 3→4, bytes {len(KO_BASE.encode())}→{len(ko_grown.encode())}"),
        case("grown in the index, restored on disk (default reads the index)",
             grown_in_index_only, 1, both, ["- Rule four."]),
        case("grown in the index, restored on disk (--worktree reads the disk)",
             grown_in_index_only, flags=["--worktree"]),
        case("grown on disk only (default reads the index)", four_disk),
        case("grown on disk only (--worktree reads the disk)", four_disk, 1, both,
             ["- Rule four."], flags=["--worktree"]),
        case("global file deleted in the index (measured as empty)",
             lambda repo: git(repo, "rm", "-q", "--cached", GLOBAL),
             notes=[f"ABSENT: {GLOBAL} is not in the index"]),
        case("global file deleted on disk (--worktree measures it as empty)",
             lambda repo: (repo / GLOBAL).unlink(), flags=["--worktree"],
             notes=[f"ABSENT: {GLOBAL} is not in the worktree"]),
        case("base revision unreadable", lambda repo: None, 2, {"GLOBAL_BASE_UNREADABLE"}, None,
             flags=["--base", "no-such-rev"]),
        case("file on neither side (the base lacks it and the index lacks it)",
             drop_global_from_head,
             notes=[f"ABSENT: {GLOBAL} is not in HEAD", f"ABSENT: {GLOBAL} is not in the index"]),
        case("base revision lacks the file, the index holds it (empty to non-empty is growth)",
             base_lacks_file_index_has_it, 1, both, BASE.splitlines(),
             notes=[f"ABSENT: {GLOBAL} is not in HEAD"]),
        case("index unreadable", corrupt_index, 2, {"GLOBAL_FILE_UNREADABLE"}, None),
    ]
    # Two contract assertions, each against a set copied once, here, and neither absorbing the
    # other. design 13.1: the gate "blocks when the line count or byte count grows" — that is
    # the whole growth predicate. The cannot-read codes are not a third verdict but the rule
    # that a gate which measured nothing must not report clean, and are cited to
    # design/session-distill/2026-10-21T0455--9410a1d--plan-addendum-wp14.md.
    growth_13_1 = {"GLOBAL_LINES_GREW", "GLOBAL_BYTES_GREW"}
    cannot_read_addendum = {"GLOBAL_BASE_UNREADABLE", "GLOBAL_FILE_UNREADABLE"}
    by_sink = {}
    for sink, code in emitted_branches():
        by_sink.setdefault(sink, set()).add(code)
    if by_sink.get("failures") != growth_13_1:
        problems.append(f"growth branches {sorted(by_sink.get('failures', ()))} differ from "
                        f"design 13.1's {sorted(growth_13_1)}")
    if by_sink.get("errors") != cannot_read_addendum:
        problems.append(f"cannot-read branches {sorted(by_sink.get('errors', ()))} differ from the "
                        f"addendum's {sorted(cannot_read_addendum)}")
    if set(by_sink) != {"failures", "errors"} or growth_13_1 & cannot_read_addendum:
        problems.append(f"the two sets must stay apart and be the only sinks: {sorted(by_sink)}")
    emitted_re = re.compile(r"^check-global-file: (?:FAIL|CANNOT JUDGE) (GLOBAL_[A-Z_]+)", re.M)

    def hook_control(root):
        """design 13.1's commit gate through the REAL hook, without recursion: the scratch clone
        carries .githooks/pre-commit byte for byte and only what it calls (the two umbrella
        scripts) is replaced by stubs that run this gate alone, so the hook's own snapshot export
        of GIT_INDEX_FILE and GIT_DIR is what the gate reads."""
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
        # staged growth is refused
        change(GLOBAL, lambda t: t + "- Rule four.\n")(repo)
        attempt("staged growth", False, "GLOBAL_LINES_GREW")
        # the disk file goes back to HEAD while the index keeps the growth: still refused
        head_text = git(repo, "show", f"HEAD:{GLOBAL}").stdout
        (repo / GLOBAL).write_text(head_text, encoding="utf-8")
        if git(repo, "diff", "--quiet", "HEAD", "--", GLOBAL, check=False).returncode != 0 \
                or git(repo, "diff", "--cached", "--quiet", "--", GLOBAL, check=False).returncode != 1:
            problems.append("hook: fixture error — the disk file must equal HEAD while the index differs")
        attempt("staged growth, disk restored to HEAD", False, "GLOBAL_LINES_GREW")

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

        passing_with_new = []
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
            if done.returncode != c["code"]:
                problems.append(f"{label}: exit {done.returncode}, wanted {c['code']}: {out}{done.stderr}")
            if set(emitted_re.findall(out)) != c["codes"]:
                problems.append(f"{label}: emitted codes differ from {sorted(c['codes'])}: {out}")
            if c["new"] is not None and got_new != c["new"]:
                problems.append(f"{label}: NEW LINES {got_new}, wanted {c['new']}")
            if (c["new"] is None) != ("NEW LINES:" not in out):
                problems.append(f"{label}: the NEW LINES block must be absent exactly when "
                                f"nothing was compared: {out}")
            if got_ko != c["ko"]:
                problems.append(f"{label}: KO SIZE {got_ko!r}, wanted {c['ko']!r}")
            if out.count("ABSENT:") != len(c["notes"]) or any(n not in out for n in c["notes"]):
                problems.append(f"{label}: the ABSENT notes differ from {c['notes']!r}: {out}")
            if c["code"] == 0 and got_new:
                passing_with_new.append(label)
        # Control of the control: among the cases that pass, the disclosure is non-empty
        # exactly where a line absent from the base survives the count check.
        wanted = ["deletion plus a shorter unrelated line",
                  "reduction whose new line is whitespace-only"]
        if passing_with_new != wanted:
            problems.append(f"disclosure non-empty in {passing_with_new}, wanted {wanted}")
        hook_control(root)
    for problem in problems:
        print(f"check-global-file --self-test: FAIL {problem}")
    if not problems:
        print(f"check-global-file --self-test: OK (positive first, {len(cases) - 1} planted, "
              f"branch set, scrub, real hook)")
    return 1 if problems else 0


def main(argv):
    ap = argparse.ArgumentParser(description="claude/CLAUDE.md may not grow against its base.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--index", action="store_true", help="read the staged file (default)")
    mode.add_argument("--worktree", action="store_true", help="read the file on disk instead")
    ap.add_argument("--base", default="HEAD", help="revision to compare against (default HEAD)")
    ap.add_argument("--repo", type=pathlib.Path, default=REPO)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    failures, errors, found, ko, sides = judge(args.repo, args.worktree, args.base)
    if found is not None:
        print(f"NEW LINES: {len(found)}")
        for number, text in found:
            print(f"  {number}: {text}")
    for side in sides:
        print(f"ABSENT: {GLOBAL} is not in {side}; measured as empty")
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
    print(f"check-global-file: OK ({GLOBAL} did not grow against {args.base})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
