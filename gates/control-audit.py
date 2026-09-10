#!/usr/bin/env python3
"""Which checks have a negative control, decided by removing them one at a time.

AGENTS.md states the revert test in prose: a control must be MISSED when its check is
reverted, because a control written against a bug it does not test survives a faithful
revert. Prose ran it by hand, and by hand it was skipped — three controls in one session
were fake, two of them only found because someone remembered to try.

The mechanization is mutation testing scoped to failure emissions. For each statement that
makes a gate fail, neuter that statement alone and run the gate's own `--self-test`:

  self-test FAILS  -> KILLED   — some control depends on this check
  self-test PASSES -> SURVIVED — nothing in the self-test notices this check is gone

A survivor is not automatically a defect. Non-vacuity guards fire only on a broken subject
set, and no ordinary control reaches them. That is why this DISCLOSES and exits 0 rather
than blocking: which survivors deserve a control is a judgement, and a gate on a judgement
call is one people learn to route around. The number is the point — it moves, and someone
has to say why.

Statements inside `self_test` itself are excluded. Neutering a control's own assertion
weakens the oracle rather than the check, and would report itself as a survivor.

  python3 gates/control-audit.py              # audit every gate
  python3 gates/control-audit.py --only compose/check-domains.py
  python3 gates/control-audit.py --self-test  # prove the harness can tell the two apart
"""
import ast
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent

# Gates that ship a --self-test AND emit failures from Python. check-package.sh and
# check-parity.sh are shell: their failure paths are `echo ... >&2` plus exit status, which
# this cannot neuter statement-wise. Named here rather than silently absent, because an
# audit that quietly covers two thirds of the gates reads like one that covers all of them.
SUBJECTS = [
    # Added once its --self-test stopped costing 134s. It was absent for exactly
    # that reason — 47 failure statements x a 134s self-test is 105 minutes, so
    # the audit was never run here, so an assertion that could not fire survived
    # into a merged branch. The self-test now runs one leg per mutation (~42s),
    # which is what made this line affordable rather than aspirational.
    "gates/check-endpoints.py",
    "gates/check-lexicon.py",
    "gates/check-surfaces.py",
    "gates/check-receipt-chain.py",
    "compose/check-domains.py",
    "learn/check-learning.py",
    "ontology/check-ontology.py",
    "claude/hooks/tooling-gotchas-hook.py",
]
# The not-audited disclosure is DERIVED, not typed. The first version typed two shell
# gates here while the tracked tree held five shell checkers — the audit tool carrying
# the exact enumeration-narrower-than-claim defect it exists to measure, found by review
# on the round that was meant to close the branch.
CHECKER_NAME = re.compile(r"(?:^|/)(?:check[-_.]|test-)[^/]*\.(?:py|sh)$")
# Whether a file DECLARES `--self-test`, which is not whether the three characters appear in
# it. `gates/check_parity.py` passes "--self-test" to other scripts and declares none of its
# own; a substring test calls that a self-test and the disclosure below then reports the
# opposite of the truth. Only the three shapes that make the flag reachable count: argparse
# registration, a membership test against argv, and an exact-argv comparison.
SELF_TEST_DECL = re.compile(
    r"""add_argument\(\s*["']--self-test["']"""
    r"""|["']--self-test["']\s+in\s+(?:sys\.)?argv"""
    r"""|(?:sys\.)?argv\[1:\]\s*==\s*\[\s*["']--self-test["']"""
)


def declares_self_test(rel, root=REPO):
    """True when `<rel> --self-test` is a route this file actually offers."""
    try:
        return bool(SELF_TEST_DECL.search((root / rel).read_text(encoding="utf-8")))
    except OSError:
        return False


def checker_inventory():
    """Every tracked checker-shaped file, unioned with the audited set (the hook is a
    subject but not checker-named)."""
    ls = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    if ls.returncode != 0:
        raise SystemExit("control-audit: git ls-files failed, so the not-audited "
                         "disclosure would be a guess: " + ls.stderr.strip()[:120])
    tracked = [f for f in ls.stdout.splitlines() if CHECKER_NAME.search(f)]
    return sorted(set(tracked) | set(SUBJECTS))

# Sink NAMES matter only for appends of plain string constants (the vacuity guards:
# `failures.append("DENY list is empty (vacuous gate)")`). An f-string append is a failure
# emission WHATEVER the list is called — keying that on the name is how 87 `fails.append`
# statements in the ontology gate were invisible and the coverage figure flattered itself.
# The reverse guard: a plain constant to a non-sink name is data, not a message —
# `cmd.append("--self-test")` builds an argv.
FAIL_SINKS = {"errors", "problems", "failures", "fails", "muts"}
# Lists that legitimately collect f-strings WITHOUT being failure sinks, each with the
# reason it is data. Counting every f-string append classified check-surfaces' deploy-path
# builder as an uncovered check; counting only listed names made 87 fails.append invisible.
# The escape from that fork: names are classified HERE, and an f-string append to a name in
# neither set is reported loudly per run — the next uncatalogued sink becomes a printed
# line instead of a silent hole in the denominator.
DATA_SINKS = {
    "gates/check-surfaces.py": {"out": "deploy-path builder; returned as data, never printed"},
    "gates/check-receipt-chain.py": {"planless": "disclosure list; reaches the summary, "
                                                 "not the failure report"},
}


def failure_statements(tree, data_names=frozenset()):
    """(statements, unclassified) — statements whose removal makes the gate stop reporting
    something, plus f-string appends to sinks classified neither FAIL nor DATA.

    Four shapes of saying no: appending to a failure sink, returning a list of messages,
    exiting non-zero, and raising SystemExit."""
    unclassified = []
    excluded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "self_test":
            excluded.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        # The `if __name__ == "__main__": sys.exit(main())` dispatcher is an entry point, not
        # a check. Neutering it makes the process exit 0 whatever it found, so it would survive
        # in every gate and report a check that does not exist.
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) \
                and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__":
            excluded.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Expr, ast.Raise, ast.Return)) or node.lineno in excluded:
            continue
        kind = None
        if isinstance(node, ast.Return):
            # A gate can emit by RETURNING its failures — self_consistency() and
            # findings_queue_open_only() do — and review caught that these were neither
            # mutated nor disclosed, so the totals overstated coverage. Only lists whose
            # elements are message strings count: a comprehension returning data (
            # corpus_bullets returns the monolith's lines) is plumbing, and mutating it
            # would inflate the denominator with non-checks. Neutering is `return []`,
            # not `pass` — a None return crashes the caller and scores a false KILLED.
            v = node.value

            def is_msg_list(x):
                el = (x.elts if isinstance(x, ast.List)
                      else [x.elt] if isinstance(x, ast.ListComp) else None)
                return bool(el) and all(
                    isinstance(e, ast.JoinedStr)
                    or (isinstance(e, ast.Constant) and isinstance(e.value, str))
                    for e in el)

            if is_msg_list(v):
                kind = "return [failures]"
            elif isinstance(v, ast.Tuple) and any(is_msg_list(e) for e in v.elts):
                # `return ["message"], {}` — the receipt-chain gate's vacuity guards wrap
                # the failure list in a result tuple, and the bare-list rule saw nothing.
                # The neuter must keep the tuple's arity: a plain `return []` would crash
                # every caller that unpacks two values and score a false KILLED.
                kind = "return [failures]"
                # A scalar f-string in a tuple stays data on purpose: `return False, f"..."`
                # is the (ok, reason) idiom, and its message is detail the CALLER appends —
                # the emission is the caller's, already counted where it appends.
        elif isinstance(node, ast.Raise):
            exc = node.exc
            name = getattr(exc, "func", exc)
            if isinstance(name, ast.Name):
                args = getattr(exc, "args", [])
                msg = bool(args) and (isinstance(args[0], ast.JoinedStr) or (
                    isinstance(args[0], ast.Constant) and isinstance(args[0].value, str)))
                # SystemExit is an emission whatever it carries — exit semantics. Any other
                # exception counts only with a message-string argument: the ontology gate's
                # vacuity check raises RuntimeError(f"..."), which the SystemExit-only rule
                # neither mutated nor disclosed. A raise carrying a variable stays out,
                # uniformly with appends and returns — a message assembled elsewhere is
                # counted where it was assembled.
                if name.id == "SystemExit" or msg:
                    kind = f"raise {name.id}"
        elif isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Attribute) and fn.attr == "append" \
                    and isinstance(fn.value, ast.Name) and node.value.args:
                arg = node.value.args[0]

                def _is_msg(a):
                    # A message is an f-string, a string constant, or a concatenation
                    # whose leaves include one — check-surfaces builds one failure with
                    # `"..." + repr(...)`, and the two-shape rule neither counted nor
                    # disclosed it.
                    if isinstance(a, ast.JoinedStr):
                        return True
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        return True
                    if isinstance(a, ast.BinOp):
                        return _is_msg(a.left) or _is_msg(a.right)
                    return False

                if isinstance(arg, (ast.JoinedStr, ast.BinOp)) and _is_msg(arg):
                    if fn.value.id in FAIL_SINKS:
                        kind = f"{fn.value.id}.append"
                    elif fn.value.id not in data_names:
                        unclassified.append((node.lineno, fn.value.id))
                elif isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and fn.value.id in FAIL_SINKS:
                    kind = f"{fn.value.id}.append"
            elif isinstance(fn, ast.Attribute) and fn.attr == "exit":
                # Not every exit is a failure. `sys.exit(0)` is success, and
                # `sys.exit(self_test())` hands over someone else's verdict — both are
                # dispatch. Removing them changes the exit code without removing a check, so
                # they survive everywhere and inflate the uncovered count with plumbing.
                arg = node.value.args[0] if node.value.args else None
                zero = isinstance(arg, ast.Constant) and arg.value in (0, None)
                handover = isinstance(arg, ast.Call)
                kind = None if (arg is None or zero or handover) else "sys.exit"
        if kind:
            if kind == "return [failures]":
                v = node.value
                if isinstance(v, ast.Tuple):
                    kept = [ast.List(elts=[], ctx=ast.Load()) if is_msg_list(e) else e
                            for e in v.elts]
                    fix = "return " + ast.unparse(ast.Tuple(elts=kept, ctx=ast.Load()))
                else:
                    fix = "return []"
            else:
                fix = "pass"
            out.append((node.lineno, node.end_lineno or node.lineno, kind, fix))
    return out, unclassified


def neutered(source, start, end, repl="pass"):
    """The same file with one statement replaced, indentation preserved."""
    lines = source.splitlines(keepends=True)
    indent = len(lines[start - 1]) - len(lines[start - 1].lstrip())
    return "".join(lines[: start - 1] + [" " * indent + repl + "\n"] + lines[end:])


def audit(rel, work, report=print):
    src_path = work / rel
    source = src_path.read_text(encoding="utf-8")
    data_names = frozenset(DATA_SINKS.get(rel, {}))
    stmts, unclassified = failure_statements(ast.parse(source), data_names)
    for line, sink in unclassified:
        report(f"  {rel}:{line}: f-string append to UNCLASSIFIED sink {sink!r} — not in "
               f"FAIL_SINKS or DATA_SINKS, so it is in nobody's denominator; classify it")
    if not stmts:
        report(f"  {rel}: NO failure statements found — the audit judged nothing here")
        return None

    base = subprocess.run([sys.executable, str(src_path), "--self-test"],
                          cwd=work, capture_output=True, text=True)
    if base.returncode != 0:
        report(f"  {rel}: baseline --self-test already fails, so no verdict is attributable")
        return None

    survivors, invalid = [], []
    try:
        for start, end, kind, repl in stmts:
            mutant = neutered(source, start, end, repl)
            # A mutant that does not compile fails the self-test for the wrong reason and would
            # be scored as KILLED, inflating coverage. Checking a multi-line statement by hand
            # produced exactly that false KILLED, which is why this guard exists.
            try:
                ast.parse(mutant)
            except SyntaxError:
                invalid.append((start, kind))
                continue
            src_path.write_text(mutant, encoding="utf-8")
            r = subprocess.run([sys.executable, str(src_path), "--self-test"],
                               cwd=work, capture_output=True, text=True)
            if r.returncode == 0:
                survivors.append((start, kind))
    finally:
        src_path.write_text(source, encoding="utf-8")

    graded_n = len(stmts) - len(invalid)
    killed = graded_n - len(survivors)
    report(f"  {rel}: {killed}/{graded_n} checks have a control, {len(survivors)} survive")
    for line, kind in sorted(survivors):
        report(f"      line {line}: {kind} — no control notices its removal")
    for line, kind in sorted(invalid):
        report(f"      line {line}: {kind} — mutation did not compile, not scored")
    return killed, survivors


def main(argv):
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]
        if only not in SUBJECTS:
            sys.exit(f"control-audit: {only} is not an audited gate; subjects are {SUBJECTS}")
    subjects = [only] if only else SUBJECTS

    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td) / "repo"
        # A real clone: several gates read `git ls-files`, and a copy without .git would make
        # them judge an empty subject set and pass over nothing.
        subprocess.run(["git", "clone", "--quiet", "--local", "--no-hardlinks",
                        str(REPO), str(work)], check=True, capture_output=True)
        # The WHOLE working snapshot, not only the subjects. Copying just the subject
        # over a HEAD clone audits a chimera: review reproduced a run where the new
        # check-domains.py landed on its parent while the simultaneously edited
        # domains.json stayed at HEAD, so the baseline self-test failed and the gate
        # got no verdict at all. Tracked modifications only — the gates read the
        # clone's index, which an untracked copy would never enter.
        st = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain",
                             "--untracked-files=no"], capture_output=True, text=True)
        if st.returncode != 0:
            raise SystemExit("control-audit: git status failed, so the working snapshot "
                             "cannot be materialized: " + st.stderr.strip()[:120])
        overlaid = 0
        for line in st.stdout.splitlines():
            rel = line[3:]
            if " -> " in rel:
                # A rename's SOURCE must leave the clone too: HEAD still has the old path,
                # and keeping it while staging everything reproduces a two-file state that
                # exists nowhere — gates enumerating git ls-files audit a phantom subject.
                src_rel, rel = (x.strip().strip('"') for x in rel.split(" -> ", 1))
                ghost = work / src_rel
                if ghost.exists():
                    ghost.unlink()
                    overlaid += 1
            else:
                rel = rel.strip().strip('"')
            src, dst = REPO / rel, work / rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                overlaid += 1
            elif dst.exists():
                dst.unlink()
                overlaid += 1
        if overlaid:
            print(f"control-audit: overlaid {overlaid} working-tree change(s) onto the clone")
        for rel in subjects:
            shutil.copy2(REPO / rel, work / rel)
        # Bytes are not membership. The gates read the clone's INDEX (`git ls-files`), and a
        # staged addition copied onto the clone's disk is still invisible to them — reproduced:
        # a staged new file landed in the clone with ls-files empty for it. Stage everything,
        # so the clone's index IS the working snapshot the audit claims to judge.
        staged = subprocess.run(["git", "-C", str(work), "add", "--all"],
                                capture_output=True, text=True)
        if staged.returncode != 0:
            raise SystemExit("control-audit: could not stage the overlay in the clone, so "
                             "gates would audit HEAD's subject set: "
                             + staged.stderr.strip()[:120])

        print(f"control-audit: {len(subjects)} gate(s), removing one check at a time")
        results = [(rel, audit(rel, work)) for rel in subjects]

    ungraded = [rel for rel, r in results if not r]
    graded = [(rel, r) for rel, r in results if r]
    if not graded:
        print("control-audit: FAIL — no gate produced a verdict, so this audited nothing")
        return 1
    total_k = sum(k for _, (k, _) in graded)
    total_s = sum(len(s) for _, (_, s) in graded)
    print(f"\ncontrol-audit: {total_k} check(s) covered by a control, {total_s} uncovered "
          f"across {len(graded)} gate(s)")
    if ungraded:
        print(f"  no verdict: {', '.join(ungraded)}")
    inventory = checker_inventory()
    shell = [f for f in inventory if f.endswith(".sh")]
    unaudited_py = [f for f in inventory if f.endswith(".py") and f not in SUBJECTS]
    # Split, because the two halves mean opposite things and the single line used to claim
    # the wrong one of them for every file: this tool audits a gate BY running its own
    # --self-test, so a file that declares one is auditable and simply is not audited — a gap
    # someone can close by adding a SUBJECTS line — while a file that declares none cannot be
    # audited by this tool at all. check-hygiene.py and check-seam-coverage.py were being
    # printed as having no self-test while both have working ones.
    auditable = [f for f in unaudited_py if declares_self_test(f)]
    no_route = [f for f in unaudited_py if f not in auditable]
    print(f"  not audited (shell failure paths): {', '.join(shell)}")
    if auditable:
        print(f"  not audited (python that DOES declare --self-test — add to SUBJECTS to "
              f"audit): {', '.join(auditable)}")
    if no_route:
        print(f"  not audited (python with no --self-test to consult): "
              f"{', '.join(no_route)}")
    print("  Disclosure only — whether an uncovered check deserves a control is a judgement.")
    return 0


def self_test():
    """The harness must tell a controlled check from an uncontrolled one.

    Two gates built here: one whose self-test asserts the check fires, one whose self-test
    asserts nothing about it. Removing the check must be KILLED in the first and SURVIVED in
    the second. Without the second case, a harness that reported everything as covered would
    pass this."""
    CONTROLLED = '''
import sys
def run(x):
    errors = []
    if x:
        errors.append("bad")
    return errors
def self_test():
    return 0 if run(True) else 1
if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else 0)
'''
    UNCONTROLLED = CONTROLLED.replace("return 0 if run(True) else 1", "run(True); return 0")

    problems = []
    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td)
        RETURNING = CONTROLLED.replace(
            '''def run(x):
    errors = []
    if x:
        errors.append("bad")
    return errors''',
            '''def run(x):
    if x:
        return [f"bad {x}"]
    return []''')
        for name, src, want_survivors in (("controlled.py", CONTROLLED, 0),
                                          ("uncontrolled.py", UNCONTROLLED, 1),
                                          ("returning.py", RETURNING, 0)):
            (work / name).write_text(src, encoding="utf-8")
            got = audit(name, work, report=lambda _m: None)
            if got is None:
                problems.append(f"{name}: the audit returned no verdict at all")
                continue
            killed, survivors = got
            if len(survivors) != want_survivors:
                problems.append(
                    f"{name}: expected {want_survivors} survivor(s), got {len(survivors)} "
                    f"(killed {killed}) — the harness cannot tell a real control from none")

    # The inventory's name rule must admit both separators and both suffixes, and the
    # partition printed as "not audited" must be total: every inventory file is a subject,
    # a shell checker, or an unaudited python checker — nothing falls silently between.
    inv = checker_inventory()
    for name, want in (("gates/check_parity.py", True), ("gates/test-assemble.sh", True),
                       ("claude/guides/checklist.md", False)):
        if bool(CHECKER_NAME.search(name)) is not want:
            problems.append(f"inventory name rule: {name} should{'' if want else ' not'} "
                            f"be a checker")
    # The self-test classifier, in both directions. Without the second row a plain substring
    # match passes this — and that is exactly the defect the split above repairs.
    with tempfile.TemporaryDirectory() as td:
        cls = pathlib.Path(td)
        (cls / "declares_argparse.py").write_text(
            'ap.add_argument("--self-test", action="store_true")\n', encoding="utf-8")
        (cls / "declares_argv.py").write_text(
            'sys.exit(self_test() if "--self-test" in sys.argv else 0)\n', encoding="utf-8")
        (cls / "declares_exact.py").write_text(
            'if sys.argv[1:] == ["--self-test"]:\n    pass\n', encoding="utf-8")
        (cls / "only_passes_it_on.py").write_text(
            'subprocess.run([sys.executable, str(script), "--self-test"])\n', encoding="utf-8")
        (cls / "mentions_in_prose.py").write_text(
            '# this gate ships no --self-test; see AGENTS.md\n', encoding="utf-8")
        for name, want in (("declares_argparse.py", True), ("declares_argv.py", True),
                           ("declares_exact.py", True), ("only_passes_it_on.py", False),
                           ("mentions_in_prose.py", False), ("absent.py", False)):
            if declares_self_test(name, root=cls) is not want:
                problems.append(
                    f"self-test classifier: {name} read as "
                    f"{'declaring' if not want else 'not declaring'} --self-test")

    leftover = [f for f in inv if f not in SUBJECTS and not f.endswith(".sh")
                and not f.endswith(".py")]
    if not inv:
        problems.append("checker inventory is empty — the disclosure would be vacuous")
    if leftover:
        problems.append(f"inventory files reported in no bucket: {leftover}")

    # The statement finder must see the shapes it claims to, or every gate reads as covered
    # because nothing was ever removed. The contrast rows matter as much: a data return —
    # a comprehension of NAMES — must not be counted, or plumbing inflates the denominator.
    probe = (
        "errors.append('empty subject (vacuous)')\n"      # constant message, sink name
        "fails.append(f'bad {tok}')\n"                    # f-string, name outside the list
        "errors.append('no deploy source: ' + repr(x))\n"  # concatenated message, sink name
        "cmd.append('--self-test')\n"                     # constant to a non-sink: argv, not a message
        "out.append(name)\n"                              # data append
        "zz.append(f'boom {x}')\n"                       # f-string to a name in NEITHER set
        "pl.append(f'left out {x}')\n"                    # f-string to a DATA-classified name
        "sys.exit(1)\nraise SystemExit('x')\nprint('not a failure')\n"
        "def f(tok):\n    return [f\"DENY token {tok!r} is undocumented\"]\n"
        "def g(text):\n    return [ln for ln in text.splitlines() if ln.startswith('- ')]\n"
        "def h(x):\n    return [f'no method in {x}'], {}\n"     # tuple-wrapped failure list
        "def k(ok):\n    return False, f'adapter exited {ok}'\n"  # (ok, reason) idiom: data
        "def m(doc):\n    raise RuntimeError(f'no edge kinds parsed from {doc}')\n"
        "def n(name):\n    raise KeyError(name)\n"                # data raise: no message literal
    )
    stmts_p, unclassified_p = failure_statements(ast.parse(probe), frozenset({"pl"}))
    found = {k for _s, _e, k, _r in stmts_p}
    want = {"errors.append", "fails.append", "sys.exit", "raise SystemExit",
            "raise RuntimeError", "return [failures]"}
    if found != want:
        problems.append(f"statement finder saw {sorted(found)}, expected {sorted(want)} — "
                        f"argv/data appends stay out, catalogued sinks enter")
    # The unclassified channel is the guard against the fails-class recurring silently:
    # an f-string append to a name in neither set must surface, and a DATA-classified one
    # must not.
    if [s for _l, s in unclassified_p] != ["zz"]:
        problems.append(f"unclassified-sink disclosure reported {unclassified_p!r}, "
                        f"expected exactly one hit for 'zz' and none for the DATA name")

    for p in problems:
        print(f"control-audit --self-test [FAIL] {p}")
    if problems:
        return 1
    print("control-audit --self-test: OK (a controlled check is killed, an uncontrolled one "
          "survives, a return-emitting check is killable, and all four failure shapes are "
          "found with data returns excluded)")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv[1:] else main(sys.argv[1:]))
