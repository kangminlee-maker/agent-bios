#!/usr/bin/env python3
"""Revert proofs for the bounds reader. Each fix is undone, one at a time, in a temporary
copy of `benchmarks/` outside the checkout, and its S9 control must fail by name there; the
checkout is never written. The receipt is printed by the copied runner itself, re-executed
from the copy, so the runner hash in the header is the file that emitted it (review round
7). Bytecode is off in the copy (an equal-size edit inside one second keeps a stale .pyc
alive across a restore — seen 2026-09-05), and the copy's removal is verified before it is
attested.

A control that survives a faithful revert of the code it claims to test is testing
something else; this is the check the repo's rules ask for ("then revert the fix and watch
the control fail"). Run from anywhere:

    python3 benchmarks/tier/revert-proofs.py --expect 14:<full sha256 of the proof set>

`--expect COUNT:DIGEST` is the pin a record carries — the full 64-hex digest, compared for
equality, so neither an omission nor an empty digest can pass against a citation. Without
it the run is UNPINNED and says so. `--self-test` runs the runner's own negative controls
with S9 stubbed; anything it needs on disk is allocated through `workspace()` only, and the
allocator is spied on during every refusal: a traceback on either stream, an abnormal status, or a summary that
disagrees with its FAIL lines is NOT PROVED; a malformed or differing pin is refused; a
workspace inside the checkout — by filesystem identity, so a differently-cased spelling of
the same directory counts — is refused. A proof whose current text is no longer in the
file exactly once is STALE and fails the run. Each proof names the review round of the
Stage-2 record that added it.
"""
import argparse
import datetime
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent          # benchmarks/tier (of the checkout, or of the copy)
BENCH = HERE.parent
REPO = BENCH.parent
B, T = "bounds.py", "stage.py"
HASHED = (B, T, "selftest.py", "revert-proofs.py")

# (round, name, file, [(current text, reverted text)], control that must fail by name).
# Reader proofs only: the runner's controls (S8) build the experiment pin from the checkout's
# launch config and agent bodies, which no copy outside a checkout has — a runner proof is
# run by hand in a disposable git worktree and receipted in the record that needs it.
PROOFS = [
    ("r1", "stage.cells judges a contrast's pairing against that size's own R (the 2dc3404 fix)", T,
     [("            r_m = R_by_size[m]   # this size's own R: every count below is judged against it",
       "            r_m = min(R_by_size.values())")], "stage.cells R per size pairing"),
    ("r1", "a contrast short of R is qualified INCOMPLETE and counted apart", B,
     [('    short = [c for c in contrasts if not c.get("complete")]', '    short = []')], "bounds R completeness"),
    ("r1", "missing level evidence is never zero defects", B,
     [('"defects_a": xa["level_defects"], "m_a": xa["m"],', '"defects_a": xa["level_defects"] or 0, "m_a": xa["m"],'),
      ('"defects_b": xb["level_defects"], "m_b": xb["m"]})', '"defects_b": xb["level_defects"] or 0, "m_b": xb["m"]})')], "bounds missing level"),
    ("r1", "a no-seat-effect cell is not counted as a candidate", B,
     [('        counted = ("KEEP", "REBIND")', '        counted = ("KEEP", "REBIND", "no-seat-effect")')], "bounds no-seat-effect count"),
    ("c1", "surplus sound pairs read as the first R in block order, never all of them", B,
     [('    rows = rows[:r_m]\n', '    rows = rows\n')], "bounds surplus rule"),
    ("r2", "no-seat-effect predicate sees complete cells only", B,
     [('retention_cells = [m for m, c in cells.items() if c["retention"].get("complete")]',
       'retention_cells = [m for m, c in cells.items() if "inconclusive" not in c["retention"] and c["retention"].get("blocks")]')],
     "bounds no-seat-effect eligible set"),
    ("r2", "a zero-block contrast leaves the cell incomplete", B,
     [('out["complete"] = all(("inconclusive" in c) or (c.get("complete") and c.get("blocks")) for c in',
       'out["complete"] = all(c.get("complete") or "inconclusive" in c or not c.get("blocks") for c in')], "bounds zero-block cell"),
    ("r2", "records spanning two hosts are refused", B,
     [('    if len(hosts) > 1:\n', '    if False:\n')], "bounds mixed hosts"),
    ("r3", "REBIND needs one receipted seat", B,
     [('    if len(seats) != 1 or any(not (f.get("child_seats") or []) for f in runs):\n        return None\n    seat = seats.pop()',
       '    seat = seats.pop() if seats else "delegated-sweep@?"')], "bounds seat/dominance/family"),
    ("r3", "tolerance inclusive at three points", B,
     [('and c["saving_lower"] - KEEP_SAVING <= RECONCILIATION_TOLERANCE + 1e-12]',
       'and c["saving_lower"] - KEEP_SAVING < RECONCILIATION_TOLERANCE - 1e-12]')], "bounds tolerance annotation"),
    ("r3", "tolerance reads the bound the label crosses", B,
     [('    if side == "lower":\n', '    if True:\n')], "bounds tolerance annotation"),
    ("r3", "family rebinding count per endpoint contrast", B,
     [('"rebinding_complete": sum(int(bool(c["rebind_vs_same"].get("complete"))) + int(bool(c["rebind_vs_incumbent"].get("complete"))) for c in cells.values()),',
       '"rebinding_complete": sum(1 for c in cells.values() if c["rebind_vs_same"].get("complete") and c["rebind_vs_incumbent"].get("complete")),')],
     "bounds seat/dominance/family"),
    ("r3", "a block run twice is refused", B,
     [('                if twice:\n', '                if False:\n')], "bounds duplicate block"),
    ("r3", "census classifies by the access receipt", T,
     [('for f in figs if not f["sound"] and f["access_hits"]],',
       'for f in figs if not f["sound"] and any(p.startswith("held-out access") for p in f["problems"])],'),
      ('for f in figs if not f["sound"] and not f["access_hits"]},',
       'for f in figs if not f["sound"] and not any(p.startswith("held-out access") for p in f["problems"])},')], "census exclusion kinds"),
    ("c1", "confirmation refuses a block discovery ran", B,
     [('        if fid in seen or fid[1] in seen_tags:\n', '        if False:\n')], "bounds confirmation manifest"),
    ("c1", "confirmation without a candidate manifest is refused at the CLI", B,
     [('        if not a.candidates:\n            raise stage.StageError("confirmation needs --candidates <manifest discovery wrote>: k, the cells, and their R come from it")\n',
       '        if not a.candidates:\n            print(json.dumps(host_table(records, a.arms.split(","), sizes, a.draws, a.seed, "confirmation", 1, 4), default=str)); return 0\n')], "bounds confirmation manifest"),
    ("c1", "a caller's k is not an input to a confirmation read", B,
     [('    if a.k is not None:\n        raise stage.StageError("--k is not an input: confirmation derives k from the candidate manifest (--candidates)")\n', '')], "bounds confirmation manifest"),
]
def manifest_of(count: int) -> str:
    """The digest of the first `count` proofs: a citation pins a prefix, so a record's pin
    stays valid while the list is only appended to, and breaks when an entry it named is
    changed — which is a different proof."""
    return hashlib.sha256(repr(PROOFS[:count]).encode()).hexdigest()


MANIFEST = manifest_of(len(PROOFS))
SUMMARY = re.compile(r"^S9: (\d+) passed, (\d+) failed$")
PIN = re.compile(r"^(\d+):([0-9a-f]{64})$")


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    """Whether `path` is `root` or under it, by filesystem identity — a differently-cased
    spelling of the same directory is the same directory on a case-insensitive
    filesystem, and lexical comparison would not know (review round 7)."""
    try:
        rst = os.stat(root)
    except FileNotFoundError:
        return False
    for p in (path, *path.parents):
        try:
            if os.path.samestat(os.stat(p), rst):
                return True
        except FileNotFoundError:
            continue
    return False


def check_pin(expect: str | None) -> str | None:
    """None when the pin names this proof set; else why not. The digest is the full
    sha256, compared whole — a prefix or an empty string is refused (review round 7)."""
    if expect is None:
        return None
    m = PIN.fullmatch(expect)
    if not m:
        return f"malformed pin {expect!r}: want COUNT:<64 hex sha256>"
    n = int(m.group(1))
    if n < 1 or n > len(PROOFS) or m.group(2) != manifest_of(n):
        return f"proof set differs from the pinned one: here {len(PROOFS)} proofs, manifest {MANIFEST[:12]}…; pinned {n}, {m.group(2)[:12]}…"
    return None


def classify(rc: int, stdout: str, stderr: str) -> dict:
    """One S9 run's outcome: the failing controls as (name, detail), the summary counts, and
    whether the run was abnormal — a status other than 0 or 1, a traceback on either
    stream, no summary, or a summary that disagrees with the FAIL lines or the status."""
    fails, summary = [], None
    for l in stdout.splitlines():
        l = l.strip()
        if l.startswith("FAIL ") and ": " in l:
            name, detail = l[5:].split(": ", 1)
            fails.append((name, detail))
        m = SUMMARY.match(l)
        if m:
            summary = (int(m.group(1)), int(m.group(2)))
    abnormal = (rc not in (0, 1) or "Traceback" in stderr or "Traceback" in stdout or summary is None
                or summary[1] != len(fails) or (rc == 0) != (summary[1] == 0))
    return {"rc": rc, "fails": fails, "summary": summary, "abnormal": abnormal}


def s9(tier: pathlib.Path) -> dict:
    shutil.rmtree(tier / "__pycache__", ignore_errors=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-B", "selftest.py", "--s9"], capture_output=True, text=True, cwd=tier, env=env)
    return classify(r.returncode, r.stdout, r.stderr)


def in_git_checkout(path: pathlib.Path) -> bool:
    """Whether any ancestor of `path` (or `path`) carries a `.git` entry — the copy lives
    under a temporary directory and has none; a checkout, this one or another, has one."""
    return any((p / ".git").exists() for p in (path, *path.parents))


def workspace() -> pathlib.Path:
    """A temporary parent outside this checkout and outside any git checkout, or refuse
    before anything is created: `mkdtemp()` with no `dir` falls back to the working
    directory when no temp directory is usable, which here is the checkout (review round
    6), and a `TMPDIR` under another checkout would put the copy there (round 9)."""
    parent = pathlib.Path(os.environ.get("TMPDIR") or "/tmp").resolve()
    if inside(parent, REPO):
        raise SystemExit(f"refusing a workspace inside the checkout: {parent}")
    if in_git_checkout(parent):
        raise SystemExit(f"refusing a workspace inside a git checkout: {parent}")
    work = pathlib.Path(tempfile.mkdtemp(prefix="revert-proofs-", dir=parent)).resolve()
    if inside(work, REPO) or in_git_checkout(work):
        shutil.rmtree(work, ignore_errors=True)
        raise SystemExit(f"refusing a workspace inside a checkout: {work}")
    return work


def prove(expect: str | None, checkout: pathlib.Path | None, tier: pathlib.Path = HERE) -> int:
    """The proofs, run in `tier` — the copy — printing the receipt. A tier inside the
    checkout named by the outer runner, or inside any git checkout at all, is refused
    before anything is written (review round 8: the self-test had reached this with the
    checkout's own directory)."""
    why = check_pin(expect)
    if why:
        print(why)
        return 1
    if (checkout is not None and inside(tier, checkout)) or in_git_checkout(tier):
        print(f"refusing to prove inside a checkout: {tier}")
        return 1
    print(f"revert proofs — {datetime.datetime.now().astimezone().isoformat(timespec='seconds')} "
          + " ".join(f"{n} {sha(tier / n)[:12]}" for n in HASHED)
          + f" proofs={len(PROOFS)} manifest {MANIFEST[:12]} {'pinned ' + expect.split(':')[0] if expect else 'UNPINNED'} (hashes are this copy's — the runner hash is the file printing this; a pin names a prefix of the append-only list)")
    print(f"manifest (full): {MANIFEST}")
    orig = {name: (tier / name).read_bytes() for name in (B, T)}
    base = s9(tier)
    if base["rc"] != 0 or base["fails"] or base["abnormal"]:
        print(f"baseline S9 is not green in the copy: rc={base['rc']} summary={base['summary']} fails={[n for n, _ in base['fails']]} abnormal={base['abnormal']}")
        return 1
    print(f"baseline S9: {base['summary'][0]} passed, 0 failed, rc 0")
    ok = True
    for rnd, name, fname, edits, expected in PROOFS:
        s = orig[fname].decode()
        stale = [cur for cur, _ in edits if s.count(cur) != 1]
        if stale:
            print(f"STALE {rnd} {name}: current text not in {fname} exactly once — re-derive the proof")
            ok = False
            continue
        for cur, rev in edits:
            s = s.replace(cur, rev)
        (tier / fname).write_bytes(s.encode())
        run = s9(tier)
        (tier / fname).write_bytes(orig[fname])
        hit = (not run["abnormal"]) and any(n == expected for n, _ in run["fails"])
        ok = ok and hit
        how = "ABNORMAL run (crash, traceback, or a summary that disagrees — not a control failing by name)" if run["abnormal"] else f"{len(run['fails'])} fail(s)"
        print(f"{'PROVED' if hit else 'NOT PROVED'} {rnd} {name}: {how}: {[n + ': ' + d[:40] for n, d in run['fails']]}")
    print("ALL PROVED" if ok else "SOME UNPROVED OR STALE")
    return 0 if ok else 1


def outer(expect: str | None) -> int:
    """Copy `benchmarks/` outside the checkout and re-execute the copied runner there; relay
    its receipt; verify the copy's removal; report whether the checkout moved meanwhile."""
    if expect is not None and not PIN.fullmatch(expect):
        print(f"malformed pin {expect!r}: want COUNT:<64 hex sha256>")
        return 1
    before = {n: sha(HERE / n) for n in HASHED}
    work = workspace()
    rc = 1
    try:
        shutil.copytree(BENCH, work / "benchmarks", ignore=shutil.ignore_patterns("__pycache__"))
        inner = work / "benchmarks" / "tier" / "revert-proofs.py"
        cmd = [sys.executable, "-B", str(inner), "--in-workspace", "--checkout", str(REPO)] + (["--expect", expect] if expect else [])
        r = subprocess.run(cmd, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), text=True, capture_output=True)
        sys.stdout.write(r.stdout)
        if r.stderr.strip():
            sys.stdout.write("inner stderr: " + r.stderr.strip()[-600:] + "\n")
        rc = r.returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)
        removed = not work.exists()
    after = {n: sha(HERE / n) for n in HASHED}
    same = before == after
    print(f"hashed proof inputs in the checkout equal before and after the run ({', '.join(HASHED)}; an endpoint comparison, not a lock): {same}; workspace {work} removed: {removed}; inner rc {rc}")
    return 0 if rc == 0 and removed and same else 1


def self_test() -> int:
    """The runner's own negative controls, in seconds, with no S9 run."""
    results = []
    # classify: a traceback on stdout with the expected FAIL and a matching summary is abnormal
    c = classify(1, "Traceback (most recent call last):\n  FAIL bounds R completeness: x\nS9: 27 passed, 1 failed\n", "")
    results.append(("a traceback on stdout is abnormal even with a matching FAIL line and summary", c["abnormal"]))
    c = classify(1, "  FAIL bounds R completeness: x\nS9: 27 passed, 1 failed\n", "Traceback (most recent call last):\n")
    results.append(("a traceback on stderr is abnormal", c["abnormal"]))
    c = classify(137, "  FAIL bounds R completeness: x\n", "")
    results.append(("status 137 with no summary is abnormal", c["abnormal"]))
    c = classify(1, "  FAIL bounds R completeness: x\nS9: 26 passed, 2 failed\n", "")
    results.append(("a summary that disagrees with the FAIL lines is abnormal", c["abnormal"]))
    c = classify(1, "  FAIL bounds R completeness: x\nS9: 27 passed, 1 failed\n", "")
    results.append(("a normal one-failure run is not abnormal", not c["abnormal"] and c["fails"][0][0] == "bounds R completeness"))
    # pins
    results.append(("an empty digest is refused", check_pin(f"{len(PROOFS)}:") is not None))
    results.append(("a digest prefix is refused", check_pin(f"{len(PROOFS)}:{MANIFEST[:12]}") is not None))
    results.append(("a count that differs from its digest is refused", check_pin(f"{len(PROOFS) - 1}:{MANIFEST}") is not None))
    results.append(("a shorter prefix pinned with its own digest is accepted (append-only list)", check_pin(f"{len(PROOFS) - 1}:{manifest_of(len(PROOFS) - 1)}") is None))
    results.append(("a digest that differs is refused", check_pin(f"{len(PROOFS)}:{'0' * 64}") is not None))
    results.append(("the full pin of this proof set is accepted", check_pin(f"{len(PROOFS)}:{MANIFEST}") is None))
    results.append(("the full pin with a trailing newline is refused", check_pin(f"{len(PROOFS)}:{MANIFEST}\n") is not None))
    # workspace containment by identity — every refusal must happen before the allocator is
    # called at all, so `tempfile.mkdtemp` is spied on during each attempt (review round 10:
    # the other-checkout fixture had been allocated with a raw mkdtemp under the ambient
    # TMPDIR, and was removed before the "nothing created" assertion looked)
    real_env = dict(os.environ)
    real_mkdtemp = tempfile.mkdtemp
    calls = []
    def spy(*a, **k):
        calls.append((a, k)); return real_mkdtemp(*a, **k)
    def refusal(tmpdir: str, phrase: str) -> bool:
        os.environ["TMPDIR"] = tmpdir; calls.clear()
        tempfile.mkdtemp = spy
        try:
            workspace(); return False
        except SystemExit as e:
            return phrase in str(e) and not calls
        finally:
            tempfile.mkdtemp = real_mkdtemp
    safe = workspace()   # the guarded allocation, under the ambient TMPDIR only if that is safe
    try:
        results.append(("a workspace under the checkout (its own spelling) is refused with no allocator call", refusal(str(REPO), "inside the checkout")))
        other = safe / "other-checkout"; (other / ".git").mkdir(parents=True)
        results.append(("a workspace under another git checkout is refused with no allocator call", refusal(str(other), "inside a git checkout")))
        results.append(("the other-checkout fixture holds nothing but its .git afterwards", sorted(x.name for x in other.iterdir()) == [".git"]))
        alt = pathlib.Path(str(REPO).swapcase()) if str(REPO) != str(REPO).swapcase() else None
        if alt is not None and alt.exists() and os.path.samefile(alt, REPO):
            results.append(("a workspace under a differently-cased spelling of the checkout is refused with no allocator call", refusal(str(alt), "inside the checkout")))
        else:
            results.append(("(case-sensitive filesystem: the alternate-case control does not apply here)", True))
    finally:
        os.environ.clear(); os.environ.update(real_env)
        shutil.rmtree(safe, ignore_errors=True)
    results.append(("the self-test's fixture root is removed", not safe.exists()))
    # prove() refuses the checkout's own tier before writing anything, and refuses any tier
    # under a git checkout; the end-to-end abnormal-run control runs in a disposable copy
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = prove(None, REPO, HERE)
    results.append(("prove() on the checkout's own tier is refused before any write", rc == 1 and "refusing to prove inside a checkout" in buf.getvalue()))
    global s9
    real_s9 = s9
    work = workspace()
    try:
        shutil.copytree(BENCH, work / "benchmarks", ignore=shutil.ignore_patterns("__pycache__"))
        tier = work / "benchmarks" / "tier"
        expected = PROOFS[0][4]
        def stub(t, _n=[0]):
            _n[0] += 1
            return ({"rc": 0, "fails": [], "summary": (28, 0), "abnormal": False} if _n[0] == 1
                    else {"rc": 137, "fails": [(expected, "printed before the crash")], "summary": None, "abnormal": True})
        s9 = stub
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = prove(None, REPO, tier)
        out = buf.getvalue()
        results.append(("an abnormal S9 run is NOT PROVED even with the control's name in its output (in a disposable copy)", rc == 1 and "NOT PROVED" in out and "ABNORMAL" in out))
        (tier / ".git").mkdir()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = prove(None, REPO, tier)
        results.append(("a tier under any git checkout is refused", rc == 1 and "refusing to prove inside a checkout" in buf.getvalue()))
    finally:
        s9 = real_s9
        shutil.rmtree(work, ignore_errors=True)
    results.append(("the self-test's disposable copy is removed", not work.exists()))
    for name, ok in results:
        print(f"{'ok ' if ok else 'BAD'} self-test: {name}")
    return 0 if all(ok for _, ok in results) else 1


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", help="COUNT:<full sha256> — the proof set a record pins; the run fails when this set differs")
    ap.add_argument("--self-test", action="store_true", help="the runner's own negative controls (no S9 run)")
    ap.add_argument("--in-workspace", action="store_true", help="internal: run the proofs where this file lives (the copy)")
    ap.add_argument("--checkout", help="internal: the checkout the copy was made from")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.in_workspace:
        if not a.checkout or not pathlib.Path(a.checkout).is_dir():
            print("--in-workspace needs --checkout <the checkout the copy was made from>")
            return 1
        return prove(a.expect, pathlib.Path(a.checkout).resolve())
    return outer(a.expect)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
