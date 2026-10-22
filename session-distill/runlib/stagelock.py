#!/usr/bin/env python3
"""Locks and confinement for the driver's writers.

One run directory has one declaration (`run.json`, `amendments.jsonl`) and one record per
stage. A second process writing the same thing would interleave a read-modify-write, so
every writer holds the lock named for what it writes: `declaration`, or `stage-<id>`.

The lock is an `flock` on a file under `<run-dir>/locks/`. It belongs to the open file, so
the operating system drops it when the holder exits, however it exits; no lock file is ever
stale, and none is deleted.

Every write the driver makes inside a run directory — the lock files, `run.json`,
`amendments.jsonl`, the stage records — first passes `confine`: the destination is resolved
with every symlink in it followed (a dangling final link and symlinked parent directories
included) and must lie beneath the resolved run directory, or the write is refused by name
(RUN_PATH_ESCAPE) before anything is created or opened. `confine` judges the path the caller
is about to open, spelled as the caller spells it — absolute, or relative to the working
directory exactly as `run_dir` is — so a relative run directory and its absolute spelling
are one place.

  stagelock.py --self-test
"""
import contextlib
import fcntl
import os
import pathlib
import sys
import time


RETRY_S = 0.005  # between attempts of a waiting writer


class Locked(Exception):
    """The lock is held by another writer; the message starts with STAGE_LOCKED."""


class Escaped(Exception):
    """A destination resolves outside the run directory; the message starts with RUN_PATH_ESCAPE."""


def contained(run_dir, name):
    """`name`, an artifact or run id spelled relative to `run_dir` (or absolute), resolved with
    every symlink followed, when it lies strictly beneath the resolved `run_dir`; else None."""
    root = pathlib.Path(run_dir).resolve()
    resolved = (root / name).resolve()
    return resolved if root in resolved.parents else None


def confine(run_dir, destination):
    """`destination` — the path the caller is about to open, absolute or relative to the working
    directory like `run_dir` — resolved with every symlink followed; `Escaped` by name unless it
    lies strictly beneath the resolved `run_dir`. Every metadata and lock write goes through
    here, and opens the path this returns."""
    root = pathlib.Path(run_dir).resolve()
    resolved = pathlib.Path(destination).resolve()
    if root not in resolved.parents:
        raise Escaped(f"RUN_PATH_ESCAPE {destination}: resolves to {resolved}, outside the run directory {root}")
    return resolved


# Set to a callable by a test only, and called with the lock's name the first time an acquisition finds
# that lock held - the real contention, inside the real attempt. A control that needs to act at that
# instant (dispatch's stop against an amendment holding the declaration) has no other way to know the
# attempt has happened rather than being about to: a signal from the caller leaves a schedule in which
# the holder finishes first. None in production, where nothing reads it.
CONTENDED = None


@contextlib.contextmanager
def hold(run_dir, name, wait_s=0):
    """Hold the lock `name`; a held lock is refused at once, or after `wait_s` seconds of
    retrying (the dispatch supervisor's reservations and breaker wait their turn)."""
    path = confine(run_dir, pathlib.Path(run_dir) / "locks" / f"{name}.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    contended = False
    try:
        for _attempt in range(int(wait_s / RETRY_S) + 1):
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not contended:
                    contended = True
                    if CONTENDED is not None:
                        CONTENDED(name)
                if wait_s:
                    time.sleep(RETRY_S)
        else:
            raise Locked(f"STAGE_LOCKED {name}: another writer holds {path}")
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock


def self_test():
    import tempfile
    failures = []
    with tempfile.TemporaryDirectory() as td:
        # positive control first: a free lock is taken, and is free again after release
        with hold(td, "declaration"):
            pass
        with hold(td, "declaration"):
            pass
        # the contention hook fires inside the real attempt, with the lock's name, and only when the lock
        # was actually held by someone else (a test's only way to act at that instant)
        seen = []
        globals()["CONTENDED"] = seen.append
        try:
            with hold(td, "declaration"):
                try:
                    with hold(td, "declaration"):
                        failures.append("a held lock was taken twice")
                except Locked:
                    pass
                if seen != ["declaration"]:
                    failures.append(f"the contention hook did not fire once with the lock's name: {seen}")
                with hold(td, "other-name"):          # a free lock is no contention
                    pass
                if seen != ["declaration"]:
                    failures.append(f"the contention hook fired for a free lock: {seen}")
        finally:
            globals()["CONTENDED"] = None
        if CONTENDED is not None:
            failures.append("the contention hook is left set, so production would call it")

        # a held lock refuses a second writer by name, and only that name
        with hold(td, "declaration"):
            try:
                with hold(td, "declaration"):
                    failures.append("a second writer took a held lock")
            except Locked as exc:
                if "STAGE_LOCKED declaration" not in str(exc):
                    failures.append(f"refusal does not carry its name: {exc}")
            with hold(td, "stage-S1"):
                pass
        # an exception inside the block releases the lock
        try:
            with hold(td, "stage-S1"):
                raise RuntimeError("stage failed")
        except RuntimeError:
            pass
        with hold(td, "stage-S1"):
            pass
        if not (pathlib.Path(td) / "locks" / "declaration.lock").is_file():
            failures.append("lock file is not kept under <run-dir>/locks/")
        # a waiting writer takes the lock once the holder releases it, and gives up by name at its deadline
        import threading
        held, release = threading.Event(), threading.Event()

        def holder():
            with hold(td, "supervisor"):
                held.set()
                release.wait(5)
        thread = threading.Thread(target=holder)
        thread.start()
        held.wait(5)
        try:
            with hold(td, "supervisor", wait_s=0.05):
                failures.append("a waiting writer took a held lock before its holder released it")
        except Locked as exc:
            if "STAGE_LOCKED supervisor" not in str(exc):
                failures.append(f"a timed-out wait was refused unnamed: {exc}")
        threading.Timer(0.1, release.set).start()
        try:
            with hold(td, "supervisor", wait_s=5):
                pass
        except Locked:
            failures.append("a waiting writer did not take the lock its holder released")
        thread.join(5)

    # confinement: a clean destination first, then each way a symlink can lead out of the run directory
    with tempfile.TemporaryDirectory() as td:
        run_dir, outside = pathlib.Path(td) / "run", pathlib.Path(td) / "outside"
        (run_dir / "sub").mkdir(parents=True)
        outside.mkdir()
        (outside / "file").write_text("outside\n", encoding="utf-8")
        (run_dir / "sub" / "inner").mkdir()
        (run_dir / "link-inside").symlink_to(run_dir / "sub" / "inner")
        (run_dir / "link-dangling").symlink_to(outside / "not-yet")
        (run_dir / "link-file").symlink_to(outside / "file")
        (run_dir / "link-dir").symlink_to(outside)
        cases = [("a clean destination", "sub/new.json", True), ("a destination that does not exist yet", "a/b/c.json", True),
                 ("a symlink that stays inside", "link-inside/new.json", True),
                 ("a dangling symlink to a place outside", "link-dangling", False),
                 ("a symlink to an existing file outside", "link-file", False),
                 ("a symlinked parent directory", "link-dir/new.json", False),
                 ("parent traversal", "../outside/new.json", False),
                 ("an absolute path outside", str(outside / "new.json"), False),
                 ("the run directory itself", ".", False)]
        for label, destination, allowed in cases:
            destination = run_dir / destination  # an absolute destination stays itself
            try:
                got = confine(run_dir, destination)
                if not allowed:
                    failures.append(f"{label}: {destination} was confined to {got}")
            except Escaped as exc:
                if allowed or "RUN_PATH_ESCAPE" not in str(exc) or str(destination) not in str(exc):
                    failures.append(f"{label}: refused wrongly or unnamed: {exc}")
        if sorted(p.name for p in outside.iterdir()) != ["file"] or (outside / "file").read_text() != "outside\n":
            failures.append("confine created or changed something outside the run directory")
        (run_dir / "locks").symlink_to(outside)
        try:
            with hold(run_dir, "declaration"):
                failures.append("a lock was taken through a symlinked locks directory")
        except Escaped as exc:
            if "RUN_PATH_ESCAPE" not in str(exc):
                failures.append(f"symlinked locks directory refused unnamed: {exc}")
        if sorted(p.name for p in outside.iterdir()) != ["file"]:
            failures.append("a lock file was created through a symlinked locks directory")

    # a relative run directory: the destination is judged where it is opened, never joined under the run
    # directory a second time, and the relative and absolute spellings of one run directory are one place
    with tempfile.TemporaryDirectory() as td:
        here = os.getcwd()
        os.chdir(td)
        try:
            root = pathlib.Path(os.getcwd()).resolve()  # the resolved spelling of the scratch directory
            pathlib.Path("run/sub").mkdir(parents=True)
            pathlib.Path("elsewhere").mkdir()
            got = confine("run", "run/sub/new.json")
            if got != root / "run" / "sub" / "new.json":
                failures.append(f"a relative destination under a relative run directory resolved to {got}")
            for label, destination in (("a relative destination beside the run directory", "elsewhere/new.json"),
                                       ("a relative destination reaching out of the run directory", "run/../elsewhere/new.json"),
                                       ("the relative run directory itself", "run")):
                try:
                    confine("run", destination)
                    failures.append(f"{label}: {destination} was confined")
                except Escaped as exc:
                    if "RUN_PATH_ESCAPE" not in str(exc):
                        failures.append(f"{label}: refused unnamed: {exc}")
            with hold("run", "declaration"):
                pass
            if not (root / "run" / "locks" / "declaration.lock").is_file() or (root / "run" / "run").exists():
                failures.append("a relative run directory did not keep its lock file at run/locks/declaration.lock")
            absolute = os.path.join(td, "run")  # td may be a symlinked spelling of the same place
            for first, second in (("run", absolute), (absolute, "run")):
                with hold(first, "declaration"):
                    try:
                        with hold(second, "declaration"):
                            failures.append(f"{first!r} and {second!r} spell one run directory but did not contend for its lock")
                    except Locked as exc:
                        if "STAGE_LOCKED declaration" not in str(exc):
                            failures.append(f"contention between {first!r} and {second!r} was refused unnamed: {exc}")
            if sorted(str(path.relative_to(root)) for path in root.rglob("*")) != [
                    "elsewhere", "run", "run/locks", "run/locks/declaration.lock", "run/sub"]:
                failures.append("relative spellings created something besides run/locks/declaration.lock")
        finally:
            os.chdir(here)
    for failure in failures:
        print(f"stagelock --self-test [FAIL] {failure}")
    if failures:
        return 1
    print("stagelock --self-test: OK (free lock taken, held lock refused by name, other names "
          "independent, released after an exception, a waiting writer served after release and refused at its "
          "deadline; confinement: clean and inside-symlink destinations "
          "allowed, dangling link, linked file, linked parent, traversal and absolute escapes refused by name; "
          "a relative run directory is one place with its absolute spelling)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: stagelock.py --self-test")
    sys.exit(self_test())
