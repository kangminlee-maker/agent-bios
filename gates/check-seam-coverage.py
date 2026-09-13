#!/usr/bin/env python3
"""Every statement of the declared seam functions must be EXECUTED by the union
of the harnesses that claim to cover them.

This is the coverage axis, and it is deliberately not the same question as
gates/control-audit.py. That tool asks whether a check is load-bearing —
sensitivity: remove it, does anything notice. This one asks whether a branch is
reached at all — coverage: is this case in any harness's response set. A
statement no harness executes is outside every control's reach by construction,
so the two are independent and neither implies the other.

It exists because measuring found what imagining had not. The transport seam has
leaked six times on one question — "something is there and we cannot read it" —
and the branch written FOR that question had never been executed by its own
self-test. Nor had the not-a-directory branch, nor the unparseable-base branch;
and a `return None` below another `return None` turned out to be unreachable,
which is a comment wearing code's clothes.

Two limits, stated rather than discovered later:

  * Statements reached only through a SUBPROCESS are invisible here. `trace`
    follows this interpreter, and the wire leg's shipped-CLI dispatch runs the
    collector as a child. A statement only that path reaches will be reported as
    uncovered, correctly — it is uncovered IN-PROCESS — and the honest fix is an
    in-process harness for it, not an exemption.
  * Executed is not asserted. A line can run without any check reading its
    result; that is control-audit's question, and the two gates are meant to be
    read together.

  python3 gates/check-seam-coverage.py
  python3 gates/check-seam-coverage.py --self-test
"""
import ast
import importlib.util
import io
import contextlib
import pathlib
import shutil
import subprocess
import sys
import tempfile
import trace

REPO = pathlib.Path(__file__).resolve().parent.parent

# The seam, its functions, and the harnesses that between them must reach every
# statement. Named as data so the subject set is inspectable and non-empty by
# assertion rather than by assumption.
SUBJECT = "learn/collect-learning.py"
# The banner that opens the subject's transport section. Every top-level
# function below it is a CANDIDATE for the seam, and the candidate set is read
# from the source rather than restated here.
SECTION_BANNER = "# \u2500\u2500 Phase 2 transport:"
FUNCTIONS = (
    "transport_config",     # the one transport contract
    "invalid_base",         # what may carry a POST
    "classify_status",      # settle / retry / drop
    "http_post",            # the request itself
    "drain_uploads",        # the watermark drain
)
# Candidates deliberately outside the seam, each with the reason it is out.
#
# This pairing is what keeps FUNCTIONS from shrinking in silence. The seam is a
# JUDGEMENT — which functions carry a transport decision is not derivable, and a
# gate on a judgement is one people route around. What IS decidable is that every
# candidate has been classified: delete a name from FUNCTIONS and it becomes a
# candidate that is neither declared nor excused, and this gate fails naming it.
# Before this pairing existed, removing "transport_config" dropped 37 of 110
# statements from the denominator and the gate still reported OK — a wrong
# denominator, which is the failure this gate was built to prevent.
NOT_SEAM = {
    "read_jsonl_records": "record I/O; decides no endpoint, carries no status",
    "load_state": "watermark persistence; cannot send or leak on its own",
    "save_state": "watermark persistence; cannot send or leak on its own",
    "print_upload_summary": "operator output; no transport decision",
    "_self_test": "a harness, not a subject — it is what executes the seam",
    "main": "CLI entry; its branches are argument parsing, not the transport path",
}
HARNESSES = ("collect-learning --self-test", "check-endpoints wire leg")


def candidate_functions(root):
    """Top-level functions below the transport banner — the set the declaration
    must account for. Derived, so the denominator cannot shrink by an edit to a
    tuple alone."""
    text = (root / SUBJECT).read_text(encoding="utf-8")
    banner_line = None
    for i, line in enumerate(text.splitlines(), start=1):
        if line.startswith(SECTION_BANNER):
            banner_line = i
            break
    if banner_line is None:
        return None
    tree = ast.parse(text)
    return {n.name for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.lineno > banner_line}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_traced(fn):
    """Executed line numbers per file, for one harness run. The harness runs
    INSIDE the tracer — calling it outside was the first version's defect, and
    it reported every line of every function as never executed, which is the
    kind of answer that should be disbelieved on sight."""
    tracer = trace.Trace(count=1, trace=0, ignoredirs=[sys.prefix, sys.exec_prefix])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        tracer.runfunc(fn)
    return tracer.results().counts


def harness_lines(root):
    """{harness: {line numbers executed in the subject}} — per harness, so a
    harness that silently stopped contributing is visible instead of being
    covered for by the other one."""
    # ONE spelling of the path on both sides. `trace` keys by the filename the
    # module was compiled with, so resolving only the expectation makes every
    # count vanish wherever the tree sits behind a symlink — /var vs /private/var
    # on macOS, which is exactly where the self-test's scratch clone lives. The
    # real repo has no such link, so this passed in place and failed in the
    # positive control, which is the one place it was still cheap to find.
    root = pathlib.Path(root).resolve()
    subject = str(root / SUBJECT)
    out = {}

    def measure(name, make):
        # A harness that RAISES is a result, not a crash of this gate: "the
        # harness died" and "the harness covered nothing" are different facts
        # and a traceback out of here would report neither.
        try:
            counts = _run_traced(make())
        except Exception as e:                                   # noqa: BLE001
            out[name] = e
            return
        out[name] = {ln for (f, ln) in counts if f == subject}

    measure(HARNESSES[0],
            lambda: _load(root / SUBJECT, "seam_collector_under_test")._self_test)
    measure(HARNESSES[1],
            lambda: (lambda mod=_load(root / "gates" / "check-endpoints.py",
                                      "seam_endpoints_under_test"):
                     (lambda: mod.leg_wire(root)))())
    return out


def statement_lines(root):
    """{function: {statement line numbers}} for the declared functions."""
    tree = ast.parse((root / SUBJECT).read_text(encoding="utf-8"))
    found = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    out = {}
    for name in FUNCTIONS:
        node = found.get(name)
        if node is None:
            out[name] = None            # reported as a missing subject below
            continue
        stmts = [n for n in ast.walk(node)
                 if isinstance(n, ast.stmt)
                 and node.lineno < n.lineno <= node.end_lineno
                 and not _is_string_statement(n)]
        # `trace` reports LINES, so two statements sharing one physical line are
        # one unit to this gate: `return "x"; raise RuntimeError("never")` marks
        # the line executed on the return and reports the unreachable raise as
        # covered. The granularity cannot be recovered from line data, so the
        # input is refused rather than judged — a coverage claim over a unit
        # coarser than the statements it names is a wrong denominator.
        seen = {}
        for n in stmts:
            seen.setdefault(n.lineno, []).append(type(n).__name__)
        shared = {ln: kinds for ln, kinds in seen.items() if len(kinds) > 1}
        if shared:
            out[name] = shared          # reported as unjudgeable below
            continue
        out[name] = set(seen)
    return out


def _is_string_statement(node):
    """A bare string expression — a docstring, or prose parked mid-function.
    Its line is bound at definition time and never recorded as executed by a
    call, so counting it would make every documented function permanently
    uncovered. Excluded as a KIND, not by line number, because an exemption
    list of line numbers is wrong within a day."""
    return (isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str))


def run(root):
    problems = []
    source = (root / SUBJECT).read_text(encoding="utf-8").splitlines()

    candidates = candidate_functions(root)
    if candidates is None:
        problems.append(f"seam-coverage: {SUBJECT} has no {SECTION_BANNER!r} banner "
                        "— the candidate set cannot be derived, so the declaration "
                        "below is accountable to nothing")
    elif not candidates:
        problems.append("seam-coverage: the transport banner is present but no "
                        "function follows it — an empty candidate set would excuse "
                        "any declaration")
    else:
        unclassified = sorted(candidates - set(FUNCTIONS) - set(NOT_SEAM))
        if unclassified:
            problems.append(
                f"seam-coverage: {unclassified} live in the transport section and "
                "are neither declared in FUNCTIONS nor excused in NOT_SEAM — "
                "classify each one; an unclassified candidate is how the "
                "denominator shrinks without anybody choosing it")
        stale = sorted(set(NOT_SEAM) - candidates)
        if stale:
            problems.append(f"seam-coverage: NOT_SEAM excuses {stale}, which the "
                            "transport section no longer defines — a stale excuse "
                            "silently widens what may go unclassified")
        outside = sorted(set(FUNCTIONS) - candidates)
        if outside:
            problems.append(f"seam-coverage: FUNCTIONS declares {outside}, which is "
                            "not a transport-section candidate — the declaration and "
                            "the section disagree about where the seam is")

    statements = statement_lines(root)
    for name, lines in statements.items():
        if isinstance(lines, dict):
            detail = ", ".join(f"{ln}: {'+'.join(k)}" for ln, k in sorted(lines.items()))
            problems.append(
                f"seam-coverage: {name}() puts more than one statement on a "
                f"physical line ({detail}) — `trace` records lines, so this gate "
                "cannot tell which of them ran; split them onto their own lines")
    unjudgeable = {n for n, l in statements.items() if isinstance(l, dict)}
    statements = {n: (None if isinstance(l, dict) else l) for n, l in statements.items()}
    # `unjudgeable` is already reported above with its own reason; folding it into
    # "defines no such function" would misattribute the cause.
    missing_fns = [n for n, lines in statements.items()
                   if lines is None and n not in unjudgeable]
    if missing_fns:
        problems.append(f"seam-coverage: {SUBJECT} defines no {missing_fns} — the "
                        "declared subject set names functions that are not there, "
                        "so this gate would pass over nothing")
    subjects = {n: l for n, l in statements.items() if l}
    if not subjects:
        problems.append("seam-coverage: no declared function resolved to any "
                        "statement — an empty subject set satisfies everything")
        return problems, 0, 0

    per_harness = harness_lines(root)
    usable = {}
    for harness, result in per_harness.items():
        if isinstance(result, Exception):
            problems.append(f"seam-coverage: harness {harness!r} raised "
                            f"{type(result).__name__}: {result} — it measured "
                            "nothing, which is not the same as covering nothing")
            continue
        if not result:
            problems.append(f"seam-coverage: harness {harness!r} executed no line "
                            f"of {SUBJECT} — it contributes nothing, and the other "
                            "harness would have covered for it silently")
        usable[harness] = result
    executed = set().union(*usable.values()) if usable else set()

    total = 0
    for name in FUNCTIONS:
        lines = subjects.get(name)
        if not lines:
            continue
        total += len(lines)
        for line in sorted(lines - executed):
            text = source[line - 1].strip() if line <= len(source) else ""
            problems.append(f"seam-coverage: {SUBJECT}:{line} in {name}() is never "
                            f"executed by any harness — {text[:90]!r}")
    return problems, len(subjects), total


def main(root=REPO):
    problems, n_fns, n_stmts = run(root)
    if problems:
        for p in problems:
            print(f"check-seam-coverage: FAIL: {p}", file=sys.stderr)
        return 1
    print(f"check-seam-coverage: OK — every statement of {n_fns} seam function(s) "
          f"({n_stmts} statements) is executed by {len(HARNESSES)} harness(es)")
    return 0


# ---------------------------------------------------------------- self-test

# What a scratch copy must contain for both harnesses to run. Declared, because
# the alternatives are worse in different ways: cloning assumes the subject tree
# IS a git repository, and the pre-commit hook runs gates against a materialised
# index with no `.git` at all (and with GIT_DIR exported, which is how a gate
# once rewrote the real repository's config). Copying everything is 416 MB, most
# of it a research instructions no harness reads. Sufficiency is not asserted here —
# the positive control proves it, and fails loudly if this list is short.
COPY_SET = ("learn", "gates/check-endpoints.py", "install.sh", "package.json",
            "ENDPOINTS.md", "learn/learning.schema.json")


def _copy(dst):
    dst.mkdir(parents=True, exist_ok=True)
    for rel in COPY_SET:
        src = REPO / rel
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__"))
        elif src.is_file():
            shutil.copy(src, target)
        else:
            raise SystemExit(f"check-seam-coverage --self-test: {rel} is neither "
                             "a file nor a directory — the scratch copy would be "
                             "missing a subject the harnesses need")
    return dst


def self_test():
    base = pathlib.Path(tempfile.mkdtemp(prefix="seam-coverage-selftest-"))
    ok = True
    try:
        # Positive control first, or a failure below is not attributable.
        clean = _copy(base / "clean")
        problems, _, _ = run(clean)
        if problems:
            print("check-seam-coverage --self-test: FAIL: the unmutated copy does "
                  f"not pass; mutations below would prove nothing: {problems[:2]}",
                  file=sys.stderr)
            return 1

        # 1) an unreachable statement must be named.
        root = _copy(base / "m1")
        p = root / SUBJECT
        p.write_text(p.read_text(encoding="utf-8").replace(
            "def classify_status(status):",
            "def classify_status(status):\n"
            "    if False:\n"
            "        return 'never'", 1), encoding="utf-8")
        problems, _, _ = run(root)
        if not any("is never executed" in x for x in problems):
            print("check-seam-coverage --self-test: FAIL: an unreachable statement "
                  f"was not reported: {problems[:2]}", file=sys.stderr)
            ok = False

        # 2) a declared function that no longer exists must be loud, not skipped
        #    — the subject set going quiet is how a coverage gate reports OK
        #    about nothing.
        root = _copy(base / "m2")
        p = root / SUBJECT
        p.write_text(p.read_text(encoding="utf-8").replace(
            "def invalid_base(base):", "def invalid_base_renamed(base):", 1),
            encoding="utf-8")
        problems, _, _ = run(root)
        if not any("names functions that are not there" in x for x in problems):
            print("check-seam-coverage --self-test: FAIL: a vanished declared "
                  f"function was not reported: {problems[:2]}", file=sys.stderr)
            ok = False

        # 3) a harness that stops contributing must be named, rather than being
        #    covered for by the other one.
        root = _copy(base / "m3")
        p = root / "gates" / "check-endpoints.py"
        p.write_text(p.read_text(encoding="utf-8").replace(
            "def leg_wire(root):", "def leg_wire(root):\n    return [], 0", 1),
            encoding="utf-8")
        problems, _, _ = run(root)
        if not any("contributes nothing" in x for x in problems):
            print("check-seam-coverage --self-test: FAIL: a silent harness was not "
                  f"reported: {problems[:2]}", file=sys.stderr)
            ok = False

        # 4) shrinking the declaration must be loud. This is the control the
        #    gate shipped without: removing one name dropped 37 of 110 statements
        #    from the denominator and it still reported OK — the wrong-denominator
        #    failure this gate exists to prevent, inside this gate.
        global FUNCTIONS
        root = _copy(base / "m4")
        original_functions = FUNCTIONS
        try:
            FUNCTIONS = tuple(f for f in FUNCTIONS if f != "transport_config")
            problems, _, _ = run(root)
        finally:
            FUNCTIONS = original_functions
        if not any("neither declared in FUNCTIONS nor excused" in x for x in problems):
            print("check-seam-coverage --self-test: FAIL: a shrunken declaration "
                  f"was not reported: {problems[:2]}", file=sys.stderr)
            ok = False

        # 5) a physical line carrying two statements must be refused, not judged.
        #    `trace` records lines, so the second statement is reported covered
        #    by the first one's execution.
        root = _copy(base / "m5")
        p = root / SUBJECT
        p.write_text(p.read_text(encoding="utf-8").replace(
            "def classify_status(status):",
            "def classify_status(status):\n    _a = 1; _b = 2", 1),
            encoding="utf-8")
        problems, _, _ = run(root)
        if not any("more than one statement on a" in x for x in problems):
            print("check-seam-coverage --self-test: FAIL: two statements on one "
                  f"line were judged rather than refused: {problems[:2]}",
                  file=sys.stderr)
            ok = False
    finally:
        shutil.rmtree(base, ignore_errors=True)
    if not ok:
        return 1
    print("check-seam-coverage --self-test: OK (positive control + 5 planted "
          "violations failed by name)")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
