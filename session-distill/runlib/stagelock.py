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


def _directory(piece, parent, destination):
    """One directory of the run, opened beneath `parent` without following a link, made when absent."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        try:
            return os.open(piece, flags, dir_fd=parent)
        except FileNotFoundError:
            try:
                os.mkdir(piece, dir_fd=parent)
            except FileExistsError:
                pass
            return os.open(piece, flags, dir_fd=parent)
    except OSError as exc:
        raise Escaped(f"RUN_PATH_ESCAPE {destination}: {piece!r} is not a directory of the run to open "
                      f"({exc.strerror}); a link put there after the path was confined is not followed") from exc


# The run directories a stage is running in, by the path the stage was GIVEN: `{absolute path: [(device, inode),
# holders]}`. `beneath` resolves its run directory anew on every write, so a run directory replaced by a link
# after a stage was admitted resolved into whatever the link named, and the stage's later records - its failure
# record among them - were written there (the S12 review, round 2). While a stage holds the pin, the directory a
# write is anchored in must be the one the stage was admitted in.
PINNED = {}


@contextlib.contextmanager
def pinned(run_dir):
    """Hold `run_dir`'s identity for as long as the caller runs; `beneath` refuses a root that is another one."""
    key = os.path.abspath(run_dir)
    root = pathlib.Path(run_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    held = os.stat(root)
    entry = PINNED.setdefault(key, [(held.st_dev, held.st_ino), 0])
    entry[1] += 1
    try:
        yield
    finally:
        entry[1] -= 1
        if entry[1] <= 0:
            PINNED.pop(key, None)


@contextlib.contextmanager
def beneath(run_dir, destination):
    """`(parent descriptor, leaf name)` of `destination`, reached from the run directory's own descriptor.

    `confine` answers where a path resolves NOW; a write that then opened that path by name would follow whatever a
    directory on the way had been swapped for in between, and create or replace a file outside the run (the S11
    review, 2026-11-13). So the directories between the run directory and the leaf are opened one component at a time,
    each beneath the last and none through a link, and the caller creates, renames and unlinks the leaf relative to
    the descriptor this yields. Missing directories are made."""
    target = confine(run_dir, destination)
    root = pathlib.Path(run_dir).resolve()
    pieces = target.relative_to(root).parts
    root.mkdir(parents=True, exist_ok=True)     # the run directory itself is the anchor, made as it always was
    # ... and opened WITHOUT following a link: `root` is resolved, so a link there now was put there since, and
    # following it would anchor every write below in whatever it names (the S11 review, round 2).
    try:
        fds = [os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)]
    except OSError as exc:
        raise Escaped(f"RUN_PATH_ESCAPE {destination}: the run directory {root} is not a directory to open "
                      f"({exc.strerror}); a link put there after it was resolved is not followed") from exc
    try:
        admitted = PINNED.get(os.path.abspath(run_dir))
        anchor = os.fstat(fds[0])
        if admitted is not None and (anchor.st_dev, anchor.st_ino) != admitted[0]:
            raise Escaped(f"RUN_PATH_ESCAPE {destination}: the run directory is not the one this stage was admitted "
                          f"in; it was replaced while the stage ran, and nothing is written in its place")
        for piece in pieces[:-1]:
            fds.append(_directory(piece, fds[-1], destination))
        yield fds[-1], pieces[-1]
    finally:
        for held in fds:
            try:
                os.close(held)
            except OSError:
                pass


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
    with beneath(run_dir, path) as (parent, leaf):
        try:
            fd = os.open(leaf, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        except OSError as exc:
            raise Escaped(f"RUN_PATH_ESCAPE {path}: the lock file could not be opened beneath the run "
                          f"({exc.strerror})") from exc
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
        # the walk beneath the run's own descriptor: `confine` is made to answer as it would have BEFORE a directory
        # on the way was swapped for a link, and the write must still not leave the run
        import shutil
        outside = pathlib.Path(tempfile.mkdtemp())
        try:
            run = pathlib.Path(td) / "swap"
            run.mkdir()
            os.symlink(outside, run / "locks")
            real = confine

            def before_the_swap(run_dir, destination):
                root, held = pathlib.Path(run_dir).resolve(), pathlib.Path(destination)
                return root / (held.relative_to(root) if root in held.parents else held.relative_to(run_dir))
            globals()["confine"] = before_the_swap
            try:
                try:
                    with hold(run, "swapped"):
                        failures.append("a lock was taken through a directory swapped for a link")
                except Escaped as exc:
                    if "RUN_PATH_ESCAPE" not in str(exc):
                        failures.append(f"the swapped directory was refused under another name: {exc}")
            finally:
                globals()["confine"] = real
            if list(outside.iterdir()):
                failures.append(f"a lock file was made outside the run: {sorted(p.name for p in outside.iterdir())}")
            # the run directory replaced by a link WHILE a stage holds it: resolved anew, the link's target would
            # be the new root, so the root is held to the one the stage was admitted in
            moved = pathlib.Path(td).resolve() / "moved-run"
            moved.mkdir()
            elsewhere = pathlib.Path(tempfile.mkdtemp())
            try:
                with pinned(moved):
                    os.rename(moved, str(moved) + ".was")
                    os.symlink(elsewhere, moved)
                    try:
                        with beneath(moved, moved / "stages" / "record.json") as (_parent, _leaf):
                            failures.append("a run directory replaced while its stage ran was written in")
                    except Escaped as exc:
                        if "not the one this stage was admitted in" not in str(exc):
                            failures.append(f"the replaced run directory was refused for another reason: {exc}")
                if list(elsewhere.iterdir()):
                    failures.append(f"a record was made where the link pointed: {sorted(p.name for p in elsewhere.iterdir())}")
                if PINNED:
                    failures.append(f"a pin outlived its holder: {sorted(PINNED)}")
            finally:
                shutil.rmtree(elsewhere, ignore_errors=True)
            # the run directory ITSELF swapped for a link after it was resolved
            anchor = pathlib.Path(td).resolve() / "anchor"
            os.symlink(outside, anchor)
            real_resolve = pathlib.Path.resolve
            pathlib.Path.resolve = lambda self, *a, **k: self      # as it resolved before the swap
            try:
                try:
                    with beneath(anchor, anchor / "x.json") as (_parent, _leaf):
                        failures.append("a run directory swapped for a link was opened")
                except Escaped as exc:
                    if "RUN_PATH_ESCAPE" not in str(exc):
                        failures.append(f"the swapped run directory was refused under another name: {exc}")
            finally:
                pathlib.Path.resolve = real_resolve
        finally:
            shutil.rmtree(outside, ignore_errors=True)
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
