#!/usr/bin/env python3
"""The checker, both directions, and the level measure (controls 3, 7, 10).

Two questions about a workdir, kept apart because they answer different things:

  done-when  — did the arm make the visible test and the regression check pass? This is
               what the repair protocol drives; a seat reaches it by fitting to the tests
               it can see, so it is NOT the level.
  level      — how many HELD-OUT checks, which no arm ever saw, does the result fail,
               plus regression breaks and static errors, per item. This is what parity is
               measured on (design, "Parity is enforced").

The held-out tests live in the oracle, never in the workdir. `leak_problems` refuses a
workdir that carries any held-out identifier or the oracle's held-out files — control 10,
blocking, because the level measure is worthless the moment a seat can see what it is
scored on.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


class CheckerError(RuntimeError):
    """A checker that could not run its subject — never scored as a pass."""


def _pytest(workdir: pathlib.Path, targets: list[str]) -> dict:
    """Run pytest and return per-test outcomes. A collection error, a missing path, or
    a nonzero exit with no reported tests is a checker failure, not a set of misses."""
    present = [t for t in targets if (workdir / t).exists()]
    if not present:
        raise CheckerError(f"none of {targets} exist under {workdir}")
    report = workdir / ".report.json"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         *present, "--tb=no",
         f"--junitxml={workdir / '.junit.xml'}"],
        cwd=workdir, capture_output=True, text=True)
    # Parse JUnit XML — a structured per-test outcome, not stdout scraping.
    xml = workdir / ".junit.xml"
    if not xml.is_file():
        raise CheckerError(f"pytest produced no report ({proc.returncode}): "
                           f"{proc.stdout[-400:]}{proc.stderr[-400:]}")
    import xml.etree.ElementTree as ET
    root = ET.parse(xml).getroot()
    suite = root.find("testsuite") if root.tag != "testsuite" else root
    total = int(suite.get("tests", 0))
    errors = int(suite.get("errors", 0))
    failures = int(suite.get("failures", 0))
    if total == 0 or errors:
        raise CheckerError(f"pytest collected {total} tests with {errors} errors — the "
                           f"checker did not run its subject")
    outcomes = {}
    for case in suite.iter("testcase"):
        name = f"{case.get('classname')}::{case.get('name')}"
        bad = case.find("failure") is not None or case.find("error") is not None
        outcomes[name] = "fail" if bad else "pass"
    xml.unlink(missing_ok=True)
    report.unlink(missing_ok=True)
    return {"total": total, "failures": failures, "outcomes": outcomes}


def _static_errors(pkg: pathlib.Path) -> int:
    """Syntax / import-time errors in the delivered package — a level defect a passing
    visible test cannot mask (an item that imports fine but breaks a sibling)."""
    n = 0
    for f in sorted(pkg.rglob("*.py")):
        try:
            ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            n += 1
    return n


def done_when(workdir: pathlib.Path) -> dict:
    """The visible contract: every visible test and the regression check pass."""
    res = _pytest(workdir, ["tests_visible", "tests_regression"])
    return {"reached": res["failures"] == 0, "failures": res["failures"],
            "total": res["total"], "outcomes": res["outcomes"]}


def level_measure(workdir: pathlib.Path, oracle: pathlib.Path) -> dict:
    """Defects on checks no arm saw: held-out failures + regression breaks + static
    errors, per item and in total. The held-out tests are run against the arm's
    delivered package in a throwaway tree BESIDE THE ORACLE — never under TMPDIR: the
    copy holds the key and a solved package, the access scan discloses a scratch tree
    rather than voiding a read there, and a stage on the other host runs concurrently
    (review round 5; the f7f74cc instrument put it under TMPDIR as `tier-level-*`, which
    the scan names as key material for that reason). Running them here cannot leak them
    into the workdir the arm keeps."""
    run = pathlib.Path(tempfile.mkdtemp(prefix="level-", dir=oracle.parent))
    try:
        shutil.copytree(workdir / "pkg", run / "pkg")
        shutil.copytree(oracle / "heldout", run / "heldout")
        held = _pytest(run, ["heldout"])
    finally:
        shutil.rmtree(run, ignore_errors=True)
    reg = _pytest(workdir, ["tests_regression"])
    static = _static_errors(workdir / "pkg")
    heldout_fail = held["failures"]
    return {
        "heldout_failures": heldout_fail,
        "regression_failures": reg["failures"],
        "static_errors": static,
        "defects": heldout_fail + reg["failures"] + static,
        "heldout_total": held["total"],
        "heldout_outcomes": held["outcomes"],
    }


def leak_problems(workdir: pathlib.Path, manifest: dict) -> list[str]:
    """Control 10, blocking: no held-out identifier, and no held-out file, may appear
    anywhere under the workdir the arm can read. A single hit is a leak."""
    problems = []
    tokens = set(manifest.get("heldout_tokens", [])) | set(manifest.get("heldout_test_ids", []))
    for f in sorted(workdir.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(workdir)
        if "_hidden" in f.name or "heldout" in str(rel).lower():
            problems.append(f"held-out artifact present in the workdir: {rel}")
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for tok in tokens:
            if tok in text:
                problems.append(f"held-out token {tok!r} leaked into {rel}")
                break
    return problems


# Control 10, second half. The host sandbox does not stop a read outside the cwd, so a
# content scan of the workdir cannot see a seat that READ the answer key without copying
# it: Stage 1 (2026-09-04) found 28 of 45 runs reading the oracle, the generator, or the
# manifest, or searching above the workdir — a Stage-0 fixture left in /private/tmp was
# found by one of them — with the content scan clean on all of them. Every tool call in
# every participant's artifact is scanned for what it names, and every tool OUTPUT for the
# names only key material carries. What the seats also do, on every run, is read the
# deployed corpus guides under the host's config home, run `git status`, and make a
# scratch directory under /tmp: the instruction surface, repository metadata, and a tree
# the key never enters now that it is regenerated only for scoring (`D-20260904-4ccdf9`)
# — allowed / disclosed rather than voided. Only a tool-call unit is a call: a turn's
# context names the sandbox's paths and is not one (round 4: a turn_context alone gave a
# receipt of 18 calls).
RULE = 13  # stamped on every receipt; the aggregator re-scans a record whose receipt carries another
# Key names. `oracle` is matched as a PATH name — after a `/`, or before `/` or the
# scoring/rescore suffix — because a seat writes the word in its own self-check scripts
# (`oracle = {...}`; two re-run inlines were voided for it, rule 9); the others are tokens
# only our fixtures carry.
# Case-insensitive: the filesystem is, so `ORACLE/pkg/mod.py` opens the key (round 8).
ACCESS_FRAGMENTS = (("oracle", re.compile(r"(?<=/)oracle(?![\w])|oracle(?=/|-scoring|-rescore)", re.I)),
                    ("heldout", re.compile("heldout", re.I)), ("_hidden", re.compile("_hidden", re.I)),
                    ("fixture_gen", re.compile("fixture_gen", re.I)), ("benchmarks/tier", re.compile("benchmarks/tier", re.I)),
                    ("tier-level", re.compile("tier-level", re.I)))
OUTPUT_FRAGMENTS = ("oracle/", "heldout", "_hidden", "tier-level")   # names only key material carries
ACCESS_KEYS = {"command", "cmd", "file_path", "path", "pattern", "glob", "arguments",
               "input", "notebook_path", "workdir", "cwd", "working_directory"}   # a cwd outside the workdir is where the relative reads go (rule 11)
OUTPUT_KEYS = {"output", "stdout", "stderr", "aggregated_output"}
# The units the scan reads: a Codex call and its output (`response_item`), a Codex
# completed item (the command as run, with its output), a Claude tool_use / tool_result.
CODEX_CALLS = ("function_call", "custom_tool_call", "local_shell_call")
CODEX_OUTPUTS = ("function_call_output", "custom_tool_call_output")
CODEX_ITEMS = ("CommandExecution", "FileChange")
_DOTDOT = re.compile(r"(?<![.\w])\.\.(?![.\w])")
# `~/x`, `$HOME/x`, and the bare `~` / `$HOME` (a `find "$HOME" …` is a search of everything
# above the workdir — round 6 showed it walking past a rule that wanted a slash)
_HOME_REL = re.compile(r"(?<![\w])~(?:/[^\s\"'`)\]\;|&<>]*)?(?![\w])|\$\{?HOME\}?(?:/[^\s\"'`)\]\;|&<>]*)?(?![\w])")
_QUOTES = re.compile(r"[\"'`\\]")
# another run's directory under a stage's `runs/`, however the root before it is spelt
# (a variable, a bare `/` search, a relative walk): `M40-b1-delegated-sweep`
_RUN_DIR = re.compile(r"(?<![\w-])(M\d+-b\d+-(?:inline|delegated-same|delegated-workhorse|delegated-sweep|fork-same))(?![\w-])")
# an absolute path token in shell or tool text: after start, whitespace, a quote, `=`,
# `(`, `:` or `,`; a glob such as `!**/.git/**` is preceded by `*` and does not match;
# `{` ends a token (an awk program `/x/{n++}` is not a two-segment path)
_ABS = re.compile(r"(?:(?<=[\s\"'`=(:,\[])|^)(/[A-Za-z0-9._-][^\s\"'`)\]\;|&<>,{}]*)")
_GIT_ANY = re.compile(r"(?<![\w-])git\s+(?!-C\s)\w")
_GIT_C = re.compile(r"(?<![\w-])git\s+-C\s+\S+\s*")   # the -C path is the repo root, not a read
_JS_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|`((?:[^`\\]|\\.)*)`')
# ${VAR:-default}, ${VAR-default}, ${VAR:+alt}, ${VAR-}: the text the shell would use — the
# re-run's first sweep run printed "${CODEX_HOME-}" and rule 5 read `<home>-}` as a path
_SHELL_DEFAULT = re.compile(r"\$\{([A-Za-z_][A-Za-z_0-9]*)(:?[-+=?])([^}]*)\}")
_HOST_VARS = ("CODEX_HOME", "CLAUDE_CONFIG_DIR")


def _default(m: re.Match) -> str:
    """`${VAR:-default}`: the stage sets each host home variable, so a default on one of
    those is dead text and the variable stands (`${CODEX_HOME:-$HOME/.codex}/sessions/x`
    is the stage home's store, which exists, not the machine's, which may not — rule 10
    read the default and excused the read as absent); any other variable's default is
    the text the seat wrote; `${VAR:+alt}` is the alternative, since the variable is set
    (rule 13: `${CODEX_HOME:+/tmp/note}` reads the scratch note, not the home)."""
    name, op, text = m.group(1), m.group(2), m.group(3)
    if op.endswith("+"):
        return text
    return "${" + name + "}" if name in _HOST_VARS else text
_HOST_HOME_VAR = re.compile(r"\$\{?(?:CODEX_HOME|CLAUDE_CONFIG_DIR)\}?")
# Roots that hold tools, never a fixture: a read there is not a read of anything ours.
TOOL_ROOTS = ("/usr", "/bin", "/sbin", "/opt", "/etc", "/dev", "/proc", "/sys", "/Library",
              "/System", "/Applications", "/nix", "/lib", "/lib64", "/run", "/snap")
# Inside a host config home, only the instruction surface is allowed; everything else
# (session stores, sqlite state, logs, caches, shell snapshots) can hold other runs' text.
HOME_SURFACE = ("guides", "AGENTS.md", "CLAUDE.md", "skills", "agents", "rules", "central",
                "personal", "commands", "prompts", "config.toml", "settings.json", "plugins",
                "automations", "hooks", "hooks.json", "bin", "mcp.json")


def _host_homes() -> tuple[str, ...]:
    h = pathlib.Path.home()
    return (str(h / ".codex"), str(h / ".claude"))


def _under(path: str, prefix: str) -> bool:
    prefix = prefix.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def _surface_ok(path: str, home: str) -> bool:
    """The home's root itself (printed, listed) or a path under its instruction surface."""
    rel = path[len(home.rstrip("/")):].lstrip("/")
    head = rel.split("/", 1)[0]
    return not rel or head in HOME_SURFACE


# Single-segment roots that are still a path when named alone (`rg pattern /tmp`); any
# other single-segment token (`/exec_command/` in a JS regex, `/unreachable/` in awk) is
# not a path.
ROOT_TOKENS = ("/tmp", "/private", "/var", "/Volumes", "/Users", "/home", "/root", "/mnt", "/media")
# Scratch trees. A seat that makes a temp dir there, moves its caches out, or searches it
# reads nothing of ours: the key is never written there (the run tree is `~/.agent-bios`,
# the oracle exists only under a run's own dir while scoring), so the access is disclosed,
# not voided — round 4 found M160-b1-delegated-same voided for `mktemp -d /private/tmp/…`
# and `mv .pytest_cache` into it. A key name (ACCESS_FRAGMENTS) under them still voids.
SCRATCH_TREES = ("/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp", "/var/folders", "/private/var/folders")


def _scratch(path: str) -> str | None:
    return next((t for t in SCRATCH_TREES if _under(path, t)), None)


def _stage(workdir) -> tuple[str | None, str | None, str | None]:
    """(own run dir, stage root, own run name) for a stage run's workdir
    (`<out>/runs/<run>/fixture/workdir`), else Nones."""
    own = run_name(workdir)
    if not own:
        return None, None, None
    p = pathlib.Path(workdir)
    return str(p.parents[1]), str(p.parents[3]), own


def _roots(allow: tuple[str, ...], workdir) -> tuple[str, ...]:
    _, stage_root, _ = _stage(workdir)
    out = tuple(a.rstrip("/") for a in allow)
    if stage_root:
        out += (stage_root, stage_root + "/runs")
    return out


def excuse(path: str, workdirs: tuple[str, ...], allow: tuple[str, ...],
           workdir: str | None = None, s: str | None = None) -> str | None:
    """Why a path is not a read outside the workdir: "own" (the run's workdir, fixture
    dir, or run dir), "token" (a single segment that is no root), "tool", "scratch",
    "surface" (an allowed home's root or instruction surface), "stage" (the stage tree
    outside `runs/` — block stubs, logs, the declaration; no key there), or "absent" (a
    path that does not exist — a seat's own typo reads nothing; the re-run's sweep seats
    named `<out>/fixture/workdir`). None = a read outside the workdir. Key names and
    sibling runs are judged BEFORE any excuse, so a removed scoring tree or a sealed
    sibling is never excused as absent."""
    import os
    path = path.rstrip("/")
    own_dirs = tuple(workdirs) + tuple(str(pathlib.Path(w).parent) for w in workdirs)
    rundir, stage_root, _ = _stage(workdir)
    if rundir:
        own_dirs += tuple(str(pathlib.Path(w).parents[1]) for w in workdirs)
    if any(_under(path, d) for d in own_dirs):
        return "own"
    if "/" not in path.strip("/") and path not in ROOT_TOKENS:
        return "token"
    if any(_under(path, r) for r in TOOL_ROOTS):
        return "tool"
    if _scratch(path):
        return "scratch"
    # a ROOT named alone is a name, not a read, only after a verb that prints, tests, or
    # lists it; as a search root, a cwd, or an unknown command it reaches everything under
    if path in _roots(allow, workdir):
        return "root" if s is not None and root_verb_ok(s, path, allow, workdirs, workdir) else None
    for a in allow:
        if _under(path, a):
            if _surface_ok(path, a):
                return "surface"
            return "absent" if not os.path.lexists(path) and not _GLOB.search(path) else None
    if stage_root and _under(path, stage_root) and not _under(path, stage_root + "/runs"):
        # block stubs and the stage's own files; the root itself was judged above, and a
        # path that does not exist there falls through to `absent`
        if _under(path, stage_root + "/blocks") or (str(pathlib.Path(path).parent) == stage_root and os.path.isfile(path)):
            return "stage"
    if not os.path.lexists(path) and not _GLOB.search(path):   # a glob names what it expands to
        # absent excuses a typo inside a tree whose layout is known (the stage tree, an
        # allowed home) and a token whose first segment is no directory on this machine
        # (`/pkg/mod.py` to be concatenated); an absent path elsewhere may have been read
        # and removed since (round 8)
        first = "/" + path.strip("/").split("/", 1)[0]
        return "absent" if not os.path.isdir(first) or (stage_root and _under(path, stage_root)) else None
    return None


def classify_path(path: str, workdirs: tuple[str, ...], allow: tuple[str, ...],
                  workdir: str | None = None, s: str | None = None) -> str | None:
    """None when `excuse` names a reason; otherwise why the path is a read outside the
    workdir — a root as a search root, another run's tree, a store inside an allowed
    home, or any other path."""
    path = path.rstrip("/")
    if excuse(path, workdirs, allow, workdir, s):
        return None
    if path in _roots(allow, workdir):
        return f"names a root as a search root, cwd, or unknown command: {path[:80]}"
    _, stage_root, _ = _stage(workdir)
    if stage_root and _under(path, stage_root + "/runs"):
        return f"names another run's tree: {path[:80]}"
    if any(_under(path, a) for a in allow):
        return f"names a host-home store outside the instruction surface: {path[:80]}"
    return f"names a path outside the workdir: {path[:80]}"


_ASSIGN = re.compile(r'(?:^|(?<=[\s;&|]))([A-Za-z_][A-Za-z_0-9]*)=("[^"]*"|\'[^\']*\'|[^\s;&|]+)')


def _expand_assignments(s: str) -> str:
    """A shell variable set in the string is substituted where the string uses it after:
    `R="${CODEX_HOME:-$HOME/.codex}"; sed -n 1,9p "$R/sessions/x"` names the store (the
    seats set such a variable in 30 re-run calls; rule 10 saw only the assignment).
    A use is substituted with the value the variable had at that point, so a reassignment
    after a read does not rewrite the read (rule 13)."""
    def subst(text: str, env: dict[str, str]) -> str:
        for k, v in env.items():
            text = re.sub(r"\$\{?" + re.escape(k) + r"\}?(?![\w])", lambda _: v, text)
        return text
    env: dict[str, str] = {}
    out: list[str] = []
    last = 0
    for m in _ASSIGN.finditer(s):
        out.append(subst(s[last:m.start()], env))
        out.append(s[m.start():m.end()])
        env[m.group(1)] = subst(m.group(2).strip("\"'"), env)
        last = m.end()
    out.append(subst(s[last:], env))
    return "".join(out)


# Verbs after which naming a ROOT (an allowed home's root, the stage's root, its `runs/`)
# reads nothing under it: they print, test, or list the name. Any other verb — `rg`,
# `find`, `cat`, `cd`, an exec's working directory — reaches inside (round 8).
ROOT_VERBS = ("printf", "echo", "test", "[", "[[", "ls", "stat", "dirname", "basename", "realpath", "readlink", "file", "du", "pwd")
# A searcher at a root reads everything beneath — unless it only lists names: `rg --files`
# and a `find` without an action are `ls -R` (the names it prints are judged as output)
SEARCH_VERBS = ("rg", "grep", "egrep", "fgrep", "find", "fd", "ag", "ack", "tree")
_FIND_ACTS = ("-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fls")
_SEGMENT = re.compile(r"\s*(?:&&|\|\||\||;|\n)\s*")
# a JS exec call's command literal (`tools.exec_command({cmd:"…", workdir:"…"})`, quoted
# keys too), read from the raw string so its escaped quotes still nest
_CMD_LIT = re.compile(r'\b(?:cmd|command)["\']?\s*:\s*(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\')')
CWD_KEYS = ("workdir", "cwd", "working_directory")
_JS_KEY = re.compile(r'\b(cmd|command|workdir|cwd|working_directory)["\']?\s*:\s*$')
_GLOB = re.compile(r"[*?\[]")
# a run can climb above its workdir without writing `..`: a modifier on PWD, dirname of
# the working directory, or a bare `cd` (to the home) — rule 13
_PARENT = re.compile(r"\$\{?OLDPWD|(?<![\w./-])cd(?=\s*(?:;|&&|\|\||\||\)|$))")


def _expand_pwd(s: str, workdir: str | None) -> str:
    """`$PWD` and what the shell derives from it, spelled out against the run's known
    working directory so the result is judged like any path: `${PWD:h:h:h}` (zsh
    dirname modifiers), `${PWD%pattern}` / `${PWD%%pattern}` (a suffix stripped —
    `${PWD%/fixture/workdir}` is the run's own directory, `${PWD%/runs/*}` the stage
    root), `$(dirname "$(pwd)")`, `$(pwd)`. Unknown working directory: left as written."""
    if not workdir:
        return s
    import fnmatch
    wd = str(workdir).rstrip("/")
    def heads(m):
        q = wd
        for _ in range(m.group(1).count(":h")):
            q = str(pathlib.PurePosixPath(q).parent)
        return q
    s = re.sub(r"\$\{PWD((?::h)+)\}", heads, s)
    def strip(m):
        op, pat = m.group(1), m.group(2)
        order = range(len(wd), -1, -1) if op == "%" else range(0, len(wd) + 1)
        for i in order:
            if fnmatch.fnmatchcase(wd[i:], pat):
                return wd[:i]
        return wd
    s = re.sub(r"\$\{PWD(%%?)([^}]*)\}", strip, s)
    s = re.sub(r"\$\{?PWD\}?(?![\w])", lambda m: wd, s)
    s = re.sub(r"\$\(\s*pwd\s*\)", lambda m: wd, s)
    for _ in range(8):   # `$(dirname "$(dirname "<wd>")")`, innermost first
        t = re.sub(r"\$\(\s*dirname\s+\"?(/[^\"\s)]*)\"?\s*\)", lambda m: str(pathlib.PurePosixPath(m.group(1)).parent), s)
        if t == s:
            break
        s = t
    return s


def _words(seg: str) -> list[str]:
    """A simple command's words, quotes kept (`'def f0'` is one word)."""
    import shlex
    try:
        return shlex.split(seg, posix=False)
    except ValueError:
        return seg.split()
# a pipe from a name listing into one of these consumes the names only; anything else
# (`xargs cat`, `while read`, a shell, an interpreter) can open them
NAME_FILTERS = ("head", "tail", "wc", "sort", "uniq", "grep", "cut", "tr", "sed", "tee", "less", "more", "cat", "awk", "column", "nl", "rev", "paste", "fold")
_SEP = re.compile(r"\s*(&&|\|\||\||;|\n)\s*")
_TOKEN = re.compile(r"[^\s\"'`(),;:=]+")
_EXT_ANY = re.compile(r"\.(?:md|py|json|jsonl|sqlite|txt|toml|yaml|yml|log|db|cfg|ini)(?![\w])", re.I)


def _split(text: str) -> list[tuple[str, str]]:
    """The simple commands of a shell string with the separator before each."""
    out: list[tuple[str, str]] = []
    last, sep = 0, ""
    for m in _SEP.finditer(text):
        out.append((sep, text[last:m.start()]))
        sep, last = m.group(1), m.end()
    out.append((sep, text[last:]))
    return out


def _verb(words: list[str]) -> str:
    return words[0].rsplit("/", 1)[-1]   # `/bin/ls` is ls


def _feeds_reader(segs: list[tuple[str, str]], i: int) -> bool:
    """True when segment `i`'s output is piped, directly or through name filters, into
    a command that can open the names it receives (`find … | xargs cat`)."""
    for sep, seg in segs[i + 1:]:
        if sep != "|":
            return False
        words = seg.strip().split()
        if not words:
            return False
        v = _verb(words)
        if v == "awk" and ("getline" in seg or "system(" in seg):
            return True
        if v not in NAME_FILTERS:
            return True
    return False

_EXT = re.compile(r"\.(?:md|py|json|jsonl|sqlite|txt|toml|yaml|yml|log|db|cfg|ini)$", re.I)


def _listing(words: list[str]) -> bool:
    """`rg --files …` or a `find` with no action prints names, as `ls -R` does."""
    if words[0] == "rg":
        return "--files" in words
    if words[0] == "find":
        return not any(w in _FIND_ACTS for w in words)
    return False


def _operands(word: str) -> list[str]:
    """The names a word could open relative to the working directory: a bare operand
    (`cat rollout`), an input redirection (`<sessions/x`), and the path-shaped tokens
    inside a quoted program (`'open("thread_history_1.sqlite")'`); never a flag, a
    variable, an absolute path, a number, an assignment, or an output redirection."""
    w = word[1:] if word.startswith("<") else word
    if not w or w.startswith(("/", "$", "~", "-", "%", "{", "[", "(", ">", "&", "|", "2>", "1>", "2&")):
        return []
    if w[0] in "\"'`":
        inner = w.strip("\"'`")
        return [t for t in _TOKEN.findall(inner)
                if not t.startswith(("/", "$", "~", "-")) and ("/" in t or _EXT_ANY.search(t))]
    if _ASSIGN.match(w) or re.fullmatch(r"[\d.,:]+[a-z]?", w) or "=" in w:
        return []
    return [w]


def cwd_ok(cmd: str, cwd: str, allow: tuple[str, ...] = (), workdirs: tuple[str, ...] = (),
           workdir: str | None = None) -> bool:
    """A command run with a root as its working directory is judged on what it names
    there: every relative operand is resolved against the root and classified like an
    absolute path (`cat guides/x.md` at the home is a surface read, `cat sessions/x` a
    store read, `cat TODO` a name that does not exist); a searcher with no operand reads
    all of the root; a name listing is a name unless its names are piped to a reader."""
    import os
    text = _normalise(cmd, allow, workdir)
    segs = _split(text)
    for i, (_, seg) in enumerate(segs):
        words = _words(seg.strip())
        while words and _ASSIGN.match(words[0]):
            words = words[1:]
        if not words:
            continue
        verb = _verb(words)
        if verb in ROOT_VERBS or _listing([verb] + words[1:]):   # names, not reads
            if _feeds_reader(segs, i):
                return False
            continue
        rels = [r for w in words[1:] for r in _operands(w)]
        for r in rels:
            if _DOTDOT.search(r):
                return False
            if classify_path(os.path.normpath(os.path.join(cwd, r)), workdirs, allow, workdir, None):
                return False
        if verb in SEARCH_VERBS and not rels and not any(w.strip("\"'`").startswith("/") for w in words[1:]):
            return False
    return True


def root_verb_ok(s: str, path: str, allow: tuple[str, ...] = (), workdirs: tuple[str, ...] = (),
                 workdir: str | None = None) -> bool:
    """True when every simple command in `s` that names `path` — read the way `_paths`
    reads it — starts with a ROOT_VERB or is a name listing whose names reach no reader."""
    p = path.rstrip("/")
    bare = re.compile(re.escape(p) + r"(?![\w/.-])")   # the root itself, not a longer path under it
    text = _normalise(s, allow, workdir)
    cmds = [m.group(1) or m.group(2) or "" for m in _CMD_LIT.finditer(s)]
    # a JS call whose working directory is the root is judged on its commands (rule 12)
    cwd_excused = False
    if cmds and all(cwd_ok(c, p, allow, workdirs, workdir) for c in cmds):
        text, n = re.subn(r'\b(?:workdir|cwd|working_directory)["\']?\s*:\s*(["\'])' + re.escape(p) + r'/?\1', 'workdir:"."', text)
        cwd_excused = n > 0
    # a command inside a JS literal is judged on its own text, not on the call around it
    lits = [t for t in (_normalise(c, allow, workdir) for c in cmds) if bare.search(t)]
    for t in lits or [text]:
        segs = _split(t)
        hits = [i for i, (_, seg) in enumerate(segs) if bare.search(seg)]
        if not hits:
            if cwd_excused:
                continue
            return False
        for i in hits:
            words = _words(segs[i][1].strip())
            while words and _ASSIGN.match(words[0]):   # leading VAR=value
                words = words[1:]
            if not words:            # an assignment alone: its uses are judged where they occur
                continue
            verb = _verb(words)
            if verb in ROOT_VERBS:
                continue
            if _listing([verb] + words[1:]) and not _feeds_reader(segs, i):
                continue
            return False
    return True


def _normalise(s: str, allow: tuple[str, ...] = (), workdir: str | None = None) -> str:
    """A tool-call string with every path spelled absolutely: an escaped newline or tab
    (a JS literal carries `\\n` between shell commands) becomes a token break, a shell
    variable set in the string is substituted where it is used, `${VAR:-default}` becomes
    its default, a host home variable becomes the allowed home, `git -C <repo>` loses its
    argument (the repo root is git's, not a read), and `~` / `$HOME` expand. `_paths`
    and `root_verb_ok` read the same text, so a verb is judged on the path it names."""
    home = str(pathlib.Path.home())
    # a JS literal escapes its quotes: `\"$HOME/.codex/guides\"` is the quoted path, not
    # a path ending in a backslash (rule 9 voided four re-run runs for `.codex\`)
    # a JS literal may spell a character as `\u002f` or `\x2f`; JavaScript decodes it
    # before the shell sees the command (rule 13)
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)
    s = s.replace('\\"', '"').replace("\\'", "'").replace("file://", "")
    s = s.replace("\\n", " ").replace("\\t", " ").replace("\n", " ").replace("\t", " ")
    s = _expand_pwd(s, workdir)
    s = _expand_assignments(s)
    s = _SHELL_DEFAULT.sub(_default, s)
    s = _HOST_HOME_VAR.sub(allow[0] if allow else home + "/.codex", s)
    s = re.sub(r'"(/[^"\s]*)"(?=/)', r"\1", s)   # `"$X"/more` is one path
    s = _GIT_C.sub("git ", s)
    return _HOME_REL.sub(lambda m: home + m.group(0)[1:] if m.group(0).startswith("~")
                         else re.sub(r"^\$\{?HOME\}?", home, m.group(0)), s)


def _paths(s: str, allow: tuple[str, ...] = (), workdir: str | None = None):
    """Every absolute path a tool-call string names, normalised by `_normalise`."""
    for m in _ABS.finditer(_normalise(s, allow, workdir)):
        yield m.group(1)


def generator_sha256() -> str:
    """The digest of `fixture_gen.py` as it is on disk now — the bytes that draw a
    fixture's workdir, reference, and held-out tests. The generator stays free of this
    receipt so a run's pin can still be compared to it byte for byte (round 7)."""
    import hashlib
    return hashlib.sha256((pathlib.Path(__file__).resolve().parent / "fixture_gen.py").read_bytes()).hexdigest()


def run_name(workdir) -> str | None:
    """The run's own directory name when the workdir is a stage run's
    (`<out>/runs/<run>/fixture/workdir`), else None."""
    if not workdir:
        return None
    p = pathlib.Path(workdir)
    try:
        return p.parents[1].name if p.parents[2].name == "runs" else None
    except IndexError:
        return None


def other_run(s: str, own: str | None) -> str | None:
    """A sibling run's name in the string — a solved workdir of the same block, or any
    other run's artifacts — whatever spelling of the root precedes it (round 7)."""
    for m in _RUN_DIR.finditer(_QUOTES.sub("", s)):
        if m.group(1) != own:
            return m.group(1)
    return None


def access_reason(s: str, workdir: str | None, allow: tuple[str, ...] = (),
                  workdirs: tuple[str, ...] = ()) -> str | None:
    """Why a tool-call string is a read outside the workdir, or None. `workdir` (and
    `workdirs`, its other spellings — unresolved, /private-prefixed) is the run's absolute
    working directory; `allow` lists the host config homes whose instruction surface a
    seat may read. Any other absolute or home-relative path is a hit — the oracle, the
    generator, every other run's tree, a session store — except the tool roots and the
    scratch trees."""
    # a key name is matched with quotes and backslashes removed: the shell joins
    # `'ora'cle` back into the word (round 6)
    bare = _QUOTES.sub("", s)
    for name, rx in ACCESS_FRAGMENTS:
        if rx.search(bare):
            return f"names {name!r}"
    if _DOTDOT.search(s):
        return "names '..'"
    if _PARENT.search(s):
        return "climbs above the workdir (a PWD modifier, dirname of it, or a bare cd)"
    own = run_name(workdir)
    if own:
        sib = other_run(s, own)
        if sib:
            return f"names another run's tree ({sib})"
    wds = tuple(w for w in ((workdir,) + tuple(workdirs)) if w)
    for path in _paths(s, allow, workdir):
        why = classify_path(path, wds, allow, workdir, s)
        if why:
            return why
    return None


def output_reason(s: str, own: str | None = None) -> str | None:
    """A tool OUTPUT that shows key material, or another run's tree — the seat's search
    reached it, whatever the command text named."""
    bare = _QUOTES.sub("", s).lower()
    for frag in OUTPUT_FRAGMENTS:
        if frag in bare:
            return f"output shows {frag!r}"
    if own:
        sib = other_run(s, own)
        if sib:
            return f"output shows another run's tree ({sib})"
    return None


def access_note(s: str, allow: tuple[str, ...] = (), workdir: str | None = None) -> str | None:
    """A disclosed (not voided) access: any git invocation — the seat addressed the
    enclosing repository (status, diff of its own file, log, rev-parse) — a path under a
    scratch tree, the stage tree outside `runs/`, or a path that does not exist."""
    if _GIT_ANY.search(s) or _GIT_C.search(s):
        return "git invocation"
    wds = _workdir_forms(workdir) if workdir else ()
    for path in _paths(s, allow, workdir):
        why = excuse(path, wds, allow, workdir, s)
        if why == "scratch":
            return f"scratch access under {_scratch(path.rstrip('/'))}"
        if why == "stage":
            return f"names the stage tree outside runs/: {path[:80]}"
        if why == "absent":
            return f"names a path that does not exist: {path[:80]}"
    return None


def _units(obj):
    """The tool-call and tool-output units of one artifact record: a Codex call or its
    output, a Codex completed item (the command as run, with its output), a Claude
    tool_use or tool_result block. Any other record — session metadata, a turn's context
    with its sandbox paths, reasoning, an agent message, a host attachment (a hook's
    command, measured 2026-09-04 voiding a run) — is not a call and is not counted."""
    if not isinstance(obj, dict):
        return
    t, p = obj.get("type"), obj.get("payload")
    if t == "response_item" and isinstance(p, dict):
        if p.get("type") in CODEX_CALLS:
            yield "call", p
        elif p.get("type") in CODEX_OUTPUTS:
            yield "output", p
    elif t == "event_msg" and isinstance(p, dict) and p.get("type") == "item_completed":
        item = p.get("item")
        if isinstance(item, dict) and item.get("type") in CODEX_ITEMS:
            yield "call", item
    elif t in ("assistant", "user"):
        msg = obj.get("message")
        blocks = msg.get("content") if isinstance(msg, dict) else None
        for b in blocks if isinstance(blocks, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                yield "call", b.get("input")
            elif isinstance(b, dict) and b.get("type") == "tool_result":
                yield "output", b


def _walk_strings(obj, key=None, kind=None):
    """Yield (kind, key, string) for every string under a tool-call-shaped key ('call')
    and every tool output ('output') inside one unit. Codex stores a tool call's
    arguments as a JSON string: walk the parsed object, never the raw text — escaped
    quotes there turn the run's own workdir path into "/…/workdir\\" and read as a path
    outside it. Everything under an output key is output, however it is nested (a Codex
    custom tool's output is a list of text blocks); a Claude tool_result block's content
    is an output."""
    if isinstance(obj, dict):
        if obj.get("type") == "tool_result":
            c = obj.get("content")
            texts = [c] if isinstance(c, str) else [x.get("text", "") for x in c if isinstance(x, dict)] if isinstance(c, list) else []
            for t in texts:
                if isinstance(t, str):
                    yield "output", "tool_result", t
            return
        for k, v in obj.items():
            yield from _walk_strings(v, k, "output" if k in OUTPUT_KEYS else kind)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v, key, kind)
    elif isinstance(obj, str):
        if kind == "output":
            yield "output", key, obj
            return
        if key == "arguments" and obj[:1] in "{[":
            try:
                yield from _walk_strings(json.loads(obj), key, kind)
                return
            except ValueError:
                pass
        if key == "input" and ("tools." in obj or "await " in obj or "const " in obj):
            # a Codex `exec` tool call is JavaScript; its shell commands and paths live in
            # its string literals, and a bare regex literal (`/exec_command/`) is not a path
            for m in _JS_LITERAL.finditer(obj):
                # the literal keeps the key it is the value of (`workdir:"…"`), so a
                # working directory is judged beside the call's command (rule 12)
                km = _JS_KEY.search(obj[max(0, m.start() - 32):m.start()])
                yield "call", km.group(1) if km else "input", next(g for g in m.groups() if g is not None)
            return
        if key in ACCESS_KEYS:
            yield "call", key, obj
        elif key in OUTPUT_KEYS:
            yield "output", key, obj


def _workdir_forms(workdir) -> tuple[str, ...]:
    if not workdir:
        return ()
    p = pathlib.Path(workdir)
    forms = {str(p.resolve()), str(p.absolute())}
    for f in list(forms):
        if f.startswith("/private/"):
            forms.add(f[len("/private"):])
        elif f.startswith("/tmp/") or f.startswith("/var/"):
            forms.add("/private" + f)
    return tuple(sorted(forms))


def _judge(unit, wd, wds, allow):
    """One unit's verdict: (problem, note, call strings judged, outputs scanned). The
    first problem in a unit is the unit's problem; a note is kept only for a unit with no
    problem."""
    strings = outputs = 0
    note = None
    own = run_name(wd)
    walked = list(_walk_strings(unit))
    cmd_at = [i for i, (kind, key, _) in enumerate(walked) if kind != "output" and key in ("command", "cmd")]
    def paired(i):   # the command nearest this working directory, the one before it on a tie (rule 13)
        return walked[min(cmd_at, key=lambda j: (abs(j - i), j > i))][2] if cmd_at else None
    for i, (kind, key, s) in enumerate(walked):
        excerpt = s.replace("\n", " ")[:110]
        if kind == "output":
            outputs += 1
            why = output_reason(s, own)
            if why:
                return f"{key} {why}: {excerpt}", None, strings, outputs
            continue
        strings += 1
        # a working directory at a root reaches only what its own command names there;
        # that command is judged on the names, resolved against the root (rules 12–13)
        if key in CWD_KEYS:
            ps = list(_paths(s, allow, wd))
            c = paired(i)
            if ps and c is not None and all(p in _roots(allow, wd) for p in ps) and cwd_ok(c, ps[0], allow, wds, wd):
                continue
        why = access_reason(s, wd, allow, wds)
        if why:
            return f"{key} {why}: {excerpt}", None, strings, outputs
        if note is None:
            n = access_note(s, allow, wd)
            if n:
                note = f"{key} {n}: {excerpt}"
    return None, note, strings, outputs


def _scan(artifact_dir: pathlib.Path, workdir, allow: tuple[str, ...]):
    """Returns (receipt, problems, notes). The receipt counts what was actually scanned
    under RULE: `units` = every tool-call and tool-output unit met, `calls` = the call
    units that named something a read could name (a collaboration call — wait_agent,
    spawn_agent — names nothing and is not one; round 5: a cut artifact keeping only such
    a call read as one scanned call), `outputs` = output strings, `malformed` = lines
    that did not parse. An unparseable line, or a run in which no call was scanned at
    all, is a problem — a receipt over nothing is what a cut artifact looks like."""
    files = sorted(pathlib.Path(artifact_dir).glob("*.jsonl")) if pathlib.Path(artifact_dir).is_dir() else []
    if not files:
        return {"files": 0, "units": 0, "calls": 0, "outputs": 0, "malformed": 0, "rule": RULE}, \
            [f"held-out access scan found no artifact under {artifact_dir}"], []
    wds = _workdir_forms(workdir)
    wd = wds[0] if wds else None
    allow = tuple(dict.fromkeys(tuple(str(pathlib.Path(a).resolve()) for a in allow if a)
                                + tuple(str(a) for a in allow if a) + _host_homes()))
    problems, notes = [], []
    units = calls = outputs = malformed = 0
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                malformed += 1
                problems.append(f"artifact {f.name}:{n} is not JSON — cut or corrupt; the scan cannot vouch for it")
                continue
            for ukind, unit in _units(obj):
                units += 1
                problem, note, strings, outs = _judge(unit, wd, wds, allow)
                calls += ukind == "call" and strings > 0
                outputs += outs
                if problem:
                    problems.append(f"held-out access: {f.name}:{n} {problem}")
                    break
                if note:
                    notes.append(f"{f.name}:{n} {note}")
    if calls == 0:
        problems.append(f"held-out access scan found no tool call in {len(files)} artifact(s) — nothing to vouch for")
    return {"files": len(files), "units": units, "calls": calls, "outputs": outputs, "malformed": malformed, "rule": RULE}, problems, notes


def access_scan(artifact_dir: pathlib.Path, workdir=None, allow: tuple[str, ...] = ()) -> dict:
    """Control 10, blocking: the receipt, the problems (each a read outside the workdir,
    an output showing key material, or an artifact the scan cannot vouch for), and the
    disclosed notes. This is the detector; the isolation (`D-20260904-4ccdf9`) is what
    keeps a read that names none of these from finding anything."""
    receipt, problems, notes = _scan(artifact_dir, workdir, allow)
    return {"checked": receipt["files"], "units": receipt["units"], "calls": receipt["calls"], "outputs": receipt["outputs"],
            "malformed": receipt["malformed"], "rule": RULE, "hits": len(problems), "problems": problems,
            "notes": len(notes), "note_lines": notes[:5]}


def access_problems(artifact_dir: pathlib.Path, workdir=None, allow: tuple[str, ...] = ()) -> list[str]:
    return _scan(artifact_dir, workdir, allow)[1]


def access_notes(artifact_dir: pathlib.Path, workdir=None, allow: tuple[str, ...] = ()) -> list[str]:
    return _scan(artifact_dir, workdir, allow)[2]


def score(workdir: pathlib.Path, oracle: pathlib.Path, manifest: dict) -> dict:
    """The full picture for one run's workdir: done-when, level, and any leak. A leak is
    a control failure that voids the level measure — reported, not scored around."""
    leaks = leak_problems(workdir, manifest)
    out = {"leaks": leaks}
    if leaks:
        out["scored"] = False
        out["why"] = "held-out leak voids the level measure"
        return out
    dw = done_when(workdir)
    lv = level_measure(workdir, oracle)
    out.update({"scored": True, "done_when_reached": dw["reached"],
                "done_when_failures": dw["failures"], "level_defects": lv["defects"],
                "level": lv})
    return out


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="score a fixture workdir")
    ap.add_argument("fixture", help="the dest dir generate() wrote (has workdir/, oracle/)")
    a = ap.parse_args(argv)
    root = pathlib.Path(a.fixture)
    manifest = json.loads((root / "manifest.json").read_text())
    print(json.dumps(score(root / "workdir", root / "oracle", manifest), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
