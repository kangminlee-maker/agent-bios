#!/usr/bin/env python3
"""The write-ahead side-effect journal of §10.5 (WP-21 commit 2).

Design §10.5: "The side-effect journal is write-ahead: before each effect, a `planned` record
(durable operation id, target, expected before-hash, intended after-hash) is written and fsynced;
after the effect, a `done` record." §10.6 then reads it: "a recovery close reads the journal and
reconciles every `planned` record without `done`".

Two properties decide the shape, and both are about what a reader can still trust after a crash.

**No effect precedes a SUCCESSFUL fsync of its `planned` record.** `append` returns only after the
bytes are on the device, and a caller that takes its effect before calling it has the order wrong -
which `apply` is held to, not this module. The three named seams (`FAULTS`) let a suite inject a
fault before the write, between the write and the fsync, and after the fsync, with no process
killed: a crash is not how you test a lost write, because an unsynced write is usually still there
after one. Losing it needs a storage that drops it, which `LosingStorage` is.

**A torn record is detected, not believed.** Each line is `<bytes> <sha256> <json>`: the length and
the digest of its own payload. A line whose payload is short or whose digest does not match is TORN,
which is legitimate only at the tail - a crash mid-write - so `read` returns it separately instead of
raising, and a torn record in the MIDDLE is reported as its own problem, because that is corruption
rather than an interrupted append.

The journal is `runtime_state` in `tables/destinations.json`: it lives outside the run so a run
directory lost with its machine does not take the record of what was already applied with it. This
module performs no effect but its own append, which its suite asserts over its AST.

    journal.py --self-test
"""
import contextlib
import errno
import fcntl
import hashlib
import json
import os
import pathlib
import shutil
import stat
import sys
import time
import unicodedata

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import destinations, targets  # noqa: E402
from runlib.records import Refused  # noqa: E402

# §10.5's own four, and the three the plan adds. Held against the design sentence below by
# `fidelity_problems`, which is done-when 12's "the journal record's required set equals §10.5's".
# Resolved once at import, by attribute access rather than `getattr(os, ...)`: handing the module
# to `getattr` is what `dispatch.py` refuses, and the platform question is answered the same way.
try:
    _NOFOLLOW = os.O_NOFOLLOW
except AttributeError:          # a platform without it; the lexical check is then the only half
    _NOFOLLOW = 0

DESIGN_10_5 = (
    "The side-effect journal is write-ahead: before each effect, a `planned` record (durable "
    "operation id, target, expected before-hash, intended after-hash) is written and fsynced; after "
    "the effect, a `done` record.")
DESIGN_FIELDS = ("operation_id", "target", "before_sha256", "after_sha256")
PLAN_ADDS = ("item_id", "approval_id")
# `commit` is on `done` alone: a core item's effect is a commit, and §10.6 reconciles it by finding
# the operation id in the branch log. `null` where the effect was not a commit.
DONE_ADDS = ("commit",)
KINDS = ("planned", "done")
# The fault seams. A name not in this set is refused rather than ignored, so a misspelled seam in a
# control cannot quietly test nothing.
FAULTS = ("before_write", "after_write_before_fsync", "after_fsync")
_INJECTED = {}


class Injected(Exception):
    """A fault a suite asked for at a named seam. Never raised in production: nothing injects."""


def inject(name, times=1):
    """Arm the named seam. Returns a callable that disarms it, for a `finally`."""
    if name not in FAULTS:
        raise Refused(f"FAULT_UNKNOWN {name}: the seams are {', '.join(FAULTS)}")
    _INJECTED[name] = times

    def disarm():
        _INJECTED.pop(name, None)
    return disarm


def _seam(name):
    held = _INJECTED.get(name)
    if not held:
        return
    if held <= 1:
        _INJECTED.pop(name, None)
    else:
        _INJECTED[name] = held - 1
    raise Injected(name)


LOCK_NAME = "journal.lock"
# The wait a writer accepts before refusing by name, and how often it retries. The bound is the
# point: one stuck holder must not hang every later command (D-20261102-49b466).
LOCK_WAIT_S = 30.0
LOCK_RETRY_S = 0.05


def durable(fd):
    """Make what was written to `fd` durable, and return the name of the call that did it.

    What the platform gives, stated rather than assumed. Plain `fsync(2)` on darwin hands the bytes
    to the DRIVE and does not ask the drive to flush its own write cache, so a power loss can still
    take them; `F_FULLFSYNC` is the request that does. Durability is the whole claim of this record
    — the effect may not precede it — so this asks for `F_FULLFSYNC` where the platform has it, falls
    back to `fsync` where it does not or where the filesystem refuses it, and RETURNS which, so a
    control reads the answer instead of trusting a comment.
    """
    held = getattr(fcntl, "F_FULLFSYNC", None)
    if held is not None:
        try:
            fcntl.fcntl(fd, held)
            return "F_FULLFSYNC"
        except OSError:
            pass            # a filesystem that does not implement it: fsync is what there is
    os.fsync(fd)
    return "fsync"


class Confined:
    """The journal's declared root, opened ONCE, with every path under it reached through it.

    `destinations.inside` answers the LEXICAL question and cannot answer the other one: `os.open`
    follows symlinks, and `O_NOFOLLOW` on the leaf leaves every parent component unguarded. The root
    is therefore opened `O_DIRECTORY|O_NOFOLLOW` once and each component is walked with `dir_fd`, and
    the same handle serves the lock, the read, the append and the reconciliation — one confinement
    rather than four lexical checks, which is what the WP-21 round-2 review found missing (reconcile
    opened the path with a plain `open` after a lexical check).

    It FAILS CLOSED on what the platform will not give: a root that is not a real directory, or is
    itself a symlink, or whose directory fsync the filesystem refuses, is a root no journal is
    written into. A containment contract that carries on when its own primitive is unavailable is
    not a contract.
    """

    def __init__(self, root):
        if not root:
            raise Refused("JOURNAL_ROOT_UNDECLARED: the journal's root is run.json's "
                          "destinations.runtime_state, and nothing is written without it")
        self.root = pathlib.Path(root)
        try:
            self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW)
        except OSError as exc:
            raise Refused(f"JOURNAL_ROOT_UNOPENABLE {self.root}: {exc.strerror} — the declared root "
                          f"must be a real directory and not a symlink, or nothing under it can be "
                          f"confined") from exc

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False

    def parts(self, path):
        """The path's components relative to the root, or Refused.

        The lexical question first, through the module that owns it, so one answer serves both this
        and `destinations`; the components are what the walk then opens one at a time.
        """
        held = pathlib.Path(path)
        if not destinations.inside(held, self.root):
            raise Refused(f"JOURNAL_OUTSIDE_ROOT {held}: not inside the declared runtime_state root "
                          f"{str(self.root)!r}")
        relative = os.path.relpath(str(held), str(self.root))
        pieces = [piece for piece in relative.split(os.sep) if piece not in ("", ".")]
        if not pieces or ".." in pieces:
            raise Refused(f"JOURNAL_OUTSIDE_ROOT {held}: its path relative to the root is "
                          f"{relative!r}, which names no file under it")
        return pieces

    def walk(self, pieces, create=False, missing_ok=False):
        """`(fds, leaf)` — one fd per directory from the root down, and the leaf's name.

        Every component is opened `O_NOFOLLOW`, so a symlink ANYWHERE in the chain is refused rather
        than followed. The fds are returned because the directories themselves have to be fsynced:
        syncing by path would walk the chain again, lexically, which is the hole this closes. The
        caller closes every fd after the root's.
        """
        fds, created = [self.fd], []
        try:
            for piece in pieces[:-1]:
                try:
                    held = os.open(piece, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW, dir_fd=fds[-1])
                except OSError as exc:
                    if exc.errno == errno.ENOENT and missing_ok and not create:
                        # Nothing there yet. A READER asking about a journal whose directory has
                        # not been created is answered with "no journal", not refused: that is the
                        # state before the first append, and §10.6 reads it.
                        for held_fd in fds[1:]:
                            try:
                                os.close(held_fd)
                            except OSError:
                                pass
                        return None, None, []
                    if exc.errno == errno.ENOENT and create:
                        os.mkdir(piece, 0o700, dir_fd=fds[-1])
                        created.append(piece)
                        held = os.open(piece, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW,
                                       dir_fd=fds[-1])
                    else:
                        # WHAT the component is decides, not the errno: a symlink to a directory
                        # under `O_DIRECTORY|O_NOFOLLOW` raises ELOOP on Linux and ENOTDIR on
                        # darwin, so a rule written on one errno reads a symlink as an ordinary
                        # file on the other platform.
                        linked = False
                        try:
                            linked = stat.S_ISLNK(os.lstat(piece, dir_fd=fds[-1]).st_mode)
                        except OSError:
                            linked = False
                        if linked or exc.errno in (errno.ELOOP, errno.EMLINK):
                            raise Refused(
                                f"JOURNAL_SYMLINK_COMPONENT {'/'.join(pieces)}: {piece} is a "
                                f"symbolic link, so the journal would be written wherever it "
                                f"points — outside the declared root a lexical check approved"
                            ) from exc
                        raise Refused(
                            f"JOURNAL_PATH_UNWALKABLE {'/'.join(pieces)}: {piece} could not be "
                            f"opened ({exc.strerror}), so containment cannot be established"
                        ) from exc
                fds.append(held)
        except BaseException:
            for held in fds[1:]:
                try:
                    os.close(held)
                except OSError:
                    pass
            raise
        return fds, pieces[-1], created

    def labels(self, pieces):
        """The absolute path of each directory in the chain, for a storage fake and for a report."""
        held, out = self.root, [str(self.root)]
        for piece in pieces[:-1]:
            held = held / piece
            out.append(str(held))
        return out

    @contextlib.contextmanager
    def lock(self, wait_s=None):
        """The journal's one lock, held across read-validate-truncate and plan-effect-done.

        Its place is FIXED and declared: `journal.lock` at the top of the declared root, opened
        through this handle. A lock whose path a caller chooses is not a lock — two writers would
        take two different files and both proceed — so there is one name, it is inside the thing it
        protects, and it is reached the same confined way as the journal.

        `flock` is advisory and per open file description: it serializes every writer that takes
        THIS lock, in this process or another, and it cannot stop a program that writes the journal
        without asking. That is the platform's limit, stated rather than papered over.
        """
        try:
            held = os.open(LOCK_NAME, os.O_RDWR | os.O_CREAT | _NOFOLLOW, 0o600, dir_fd=self.fd)
        except OSError as exc:
            raise Refused(f"JOURNAL_LOCK_UNOPENABLE {self.root / LOCK_NAME}: {exc.strerror}") from exc
        try:
            # BOUNDED, and the bound is the repository's: a writer that waits on `flock` with no
            # deadline hangs every later command on one stuck holder, so an exclusive lock is asked
            # for with LOCK_NB and retried for at most LOCK_WAIT_S, then refused BY NAME
            # (D-20261102-49b466). `runlib/stagelock.py` takes its locks the same way; this module
            # does not import `compose/host_platform.py`'s helper because the payload's stage
            # library does not depend on the installer's.
            waited = LOCK_WAIT_S if wait_s is None else wait_s
            for _attempt in range(int(waited / LOCK_RETRY_S) + 1):
                try:
                    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(LOCK_RETRY_S)
            else:
                raise Refused(f"JOURNAL_LOCKED {self.root / LOCK_NAME}: another writer has held the "
                              f"journal's lock for {waited:g} s, so this one refuses rather than "
                              f"waiting without a deadline")
            yield held
        finally:
            try:
                fcntl.flock(held, fcntl.LOCK_UN)
            finally:
                os.close(held)


class Storage:
    """The real device: append the bytes, then make the file and its whole directory chain durable.

    The directory sync is what makes a newly created journal file's own NAME durable; without it the
    file's bytes can be on the device while the entry that reaches them is not. The WHOLE chain is
    synced on every append, not only the parts this append created: `mkdir(parents=True)` can leave
    `a/b` behind after a failed sync, and the retry then finds nothing new to create and syncs
    nothing — the record is durable inside directory entries that never reached the device. There is
    no way to ask the kernel whether an entry is already durable, so the answer is to sync the chain
    unconditionally, which costs a handful of fsyncs and closes the hole (the WP-21 round-2 review).
    """

    def _write_once(self, handle, data):
        """One write to the device, as its own named seam.

        A seam rather than a patch: a control that swaps `os.write` out hands an executor's module
        around, which `dispatch.py`'s source-shape rule refuses in a shipped module — rightly, since
        replacing a module is how an effect hides from a scan. Overriding one method needs nothing
        global swapped, and it matches this unit's decision that faults arrive through named seams.
        """
        return os.write(handle, data)

    def _single_name(self, handle, pieces):
        """Refuse a journal whose bytes have a second name.

        `O_NOFOLLOW` refuses a symlink and says nothing of a hard link: the open succeeds and the
        bytes it reaches may be a file outside the declared root, under its other name. Appending or
        truncating through this name then changes that file (the round-5 review). The descriptor is
        asked, after the open and before any byte moves.
        """
        held = os.fstat(handle)
        if not stat.S_ISREG(held.st_mode) or held.st_nlink != 1:
            raise Refused(f"JOURNAL_HARD_LINKED {'/'.join(pieces)}: the journal is not a regular "
                          f"file with exactly one name (links: {held.st_nlink}), so writing it "
                          f"here would change bytes this root does not confine")

    def append(self, confined, pieces, data):
        """Append `data` to the journal named by `pieces`, under the confined root."""
        fds, leaf, _created = confined.walk(pieces, create=True)
        labels = confined.labels(pieces)
        try:
            existed = True
            try:
                os.stat(leaf, dir_fd=fds[-1], follow_symlinks=False)
            except OSError:
                existed = False
            _seam("before_write")
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | _NOFOLLOW
            try:
                handle = os.open(leaf, flags, 0o600, dir_fd=fds[-1])
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.EMLINK):
                    raise Refused(f"JOURNAL_SYMLINK {'/'.join(pieces)}: the journal path is a "
                                  f"symlink, so the append would land wherever it points — outside "
                                  f"the declared root that a lexical check just approved") from exc
                raise
            try:
                self._single_name(handle, pieces)
                # A SHORT write is not a complete record. `os.write` may write fewer bytes than it
                # was given, and returning then would acknowledge a durable complete record for a
                # line the reader will see as torn. Loop until every byte is written, and fail by
                # name if the device stops accepting them.
                written = 0
                while written < len(data):
                    held = self._write_once(handle, data[written:])
                    if held <= 0:
                        raise Refused(f"JOURNAL_SHORT_WRITE {'/'.join(pieces)}: the device accepted "
                                      f"{written} of {len(data)} bytes and then none, so the record "
                                      f"is incomplete")
                    written += held
                _seam("after_write_before_fsync")
                self._durable_file(handle, labels[-1] + "/" + leaf, created=not existed)
            finally:
                os.close(handle)
            for index, held_fd in enumerate(fds):
                self._sync_directory(held_fd, labels[index])
            _seam("after_fsync")
        finally:
            for held_fd in fds[1:]:
                try:
                    os.close(held_fd)
                except OSError:
                    pass

    def read_bytes(self, confined, pieces):
        """The journal's bytes, through the same confined handle. Empty when it is not there yet."""
        fds, leaf, _created = confined.walk(pieces, missing_ok=True)
        if fds is None:
            return None
        try:
            try:
                handle = os.open(leaf, os.O_RDONLY | _NOFOLLOW, dir_fd=fds[-1])
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    return None
                if exc.errno in (errno.ELOOP, errno.EMLINK):
                    raise Refused(f"JOURNAL_SYMLINK {'/'.join(pieces)}: the journal path is a "
                                  f"symlink, so a read would come from wherever it points") from exc
                raise
            try:
                held = []
                while True:
                    chunk = os.read(handle, 1 << 20)
                    if not chunk:
                        break
                    held.append(chunk)
                return b"".join(held)
            finally:
                os.close(handle)
        finally:
            for held_fd in fds[1:]:
                try:
                    os.close(held_fd)
                except OSError:
                    pass

    def truncate(self, confined, pieces, cut):
        """Cut the journal to `cut` bytes, durably, through the same confined handle."""
        fds, leaf, _created = confined.walk(pieces)
        labels = confined.labels(pieces)
        try:
            handle = os.open(leaf, os.O_RDWR | _NOFOLLOW, dir_fd=fds[-1])
            try:
                self._single_name(handle, pieces)
                os.ftruncate(handle, cut)
                self._durable_file(handle, labels[-1] + "/" + leaf, created=False)
            finally:
                os.close(handle)
            for index, held_fd in enumerate(fds):
                self._sync_directory(held_fd, labels[index])
        finally:
            for held_fd in fds[1:]:
                try:
                    os.close(held_fd)
                except OSError:
                    pass

    def _durable_file(self, handle, label, created):
        """The file's CONTENTS made durable. `created` says whether its name is new.

        Three things are at risk and they are lost separately: the contents, the file's own entry in
        its directory, and the entries of the directories above it. A fake that models fewer than
        three cannot show the loss of the ones it skipped, which is how a journal whose own directory
        entry never landed stayed invisible to a suite that had a storage fake in it.
        """
        durable(handle)

    def _dir_sync_call(self, held_fd):
        """The platform call itself, as its own seam.

        A seam so the translation below can be shown to fire: a filesystem that refuses to fsync a
        directory is a real configuration, and the only way to exercise this module's answer to it
        without one is to override the call.
        """
        return durable(held_fd)

    def _sync_directory(self, held_fd, label):
        """One directory's entries made durable, by fd.

        By fd rather than by path: syncing by path walks the chain a second time, lexically, which
        is the hole the confined handle closes. A filesystem that refuses the request is a
        filesystem this module will not claim durability on.
        """
        try:
            self._dir_sync_call(held_fd)
        except OSError as exc:
            if exc.errno in (errno.EINVAL, errno.ENOTSUP):
                raise Refused(f"JOURNAL_DIRECTORY_SYNC_UNSUPPORTED {label}: the filesystem refuses "
                              f"to fsync a directory ({exc.strerror}), so a new journal's own name "
                              f"cannot be made durable here and no durability is claimed") from exc
            raise


class LosingStorage(Storage):
    """A storage that keeps unsynced writes in memory and loses them on demand.

    The only honest way to exercise §10.5's "no effect precedes a successful fsync": a killed process
    does NOT lose an unsynced write on a real filesystem, so a control built on a crash would be
    asserting something the platform does not do. `lose_unsynced()` is the storage failure.

    Three things are at risk and a real filesystem loses them SEPARATELY: the contents, the journal
    file's own entry in its directory, and the entries of the directories created above it. This fake
    modelled two, so a new journal under an EXISTING directory could not be shown to disappear at all
    (the WP-21 round-2 review). `lose_names=True` is that third model: the bytes are written and the
    file is fsynced, and the directory entries are not, which is exactly the state in which a file
    exists on the device and nothing can reach it.
    """

    def __init__(self, lose_names=False):
        self.unsynced = []
        self.unsynced_directories = []
        self.unsynced_files = []
        self.synced = []
        self.roots = set()
        self.lose_names = lose_names
        self._flushing = False

    def _durable_file(self, handle, label, created):
        """While flushing, the contents really are made durable; the NAME may still be at risk."""
        if not self._flushing:
            return
        Storage._durable_file(self, handle, label, created)
        if created and self.lose_names:
            self.unsynced_files.append(pathlib.Path(label))

    def _sync_directory(self, held_fd, label):
        """Recorded always; performed only while flushing, and not at all under `lose_names`.

        A directory that really was synced leaves the loss list. Without that the fake lost entries
        a real device would have kept, so every control built on it was watching the fake's own
        bookkeeping rather than the durability rule (the round-3 review).
        """
        self.synced.append(str(label))
        if self._flushing and not self.lose_names:
            Storage._sync_directory(self, held_fd, label)
            held_path = pathlib.Path(label)
            self.unsynced_directories = [p for p in self.unsynced_directories if p != held_path]

    def append(self, confined, pieces, data):
        self.roots.add(str(confined.root))
        fds, leaf, created = confined.walk(pieces, create=True)
        labels = confined.labels(pieces)
        try:
            for index, piece in enumerate(pieces[:-1]):
                if piece in created:
                    self._created_directory(pathlib.Path(labels[index + 1]))
            _seam("before_write")
            self.unsynced.append((confined, list(pieces), data))
            _seam("after_write_before_fsync")
            held_writes, self.unsynced = self.unsynced, []
            self._flushing = True
            try:
                for held_confined, held_pieces, held_data in held_writes:
                    Storage.append(self, held_confined, held_pieces, held_data)
            finally:
                self._flushing = False
            _seam("after_fsync")
        finally:
            for held_fd in fds[1:]:
                try:
                    os.close(held_fd)
                except OSError:
                    pass

    def _created_directory(self, made):
        """A directory ENTRY that has not reached the device yet.

        An entry that never landed takes everything under it with it, because nothing can reach what
        has no name.
        """
        self.unsynced_directories.append(pathlib.Path(made))

    def lose_unsynced(self):
        """Discard every write, file name and directory entry that was not made durable.

        Returns `{contents, files, directories}`: the three are lost separately on a real
        filesystem, and a caller that counted only contents could not see a journal whose own name
        never landed.
        """
        held = len(self.unsynced)
        files = [p for p in self.unsynced_files if p.exists()]
        directories = [p for p in self.unsynced_directories if p.exists()]
        self.unsynced = []
        self.unsynced_files = []
        self.unsynced_directories = []
        lost_files = 0
        for held_file in sorted({str(p) for p in files}):
            try:
                pathlib.Path(held_file).unlink()
                lost_files += 1
            except OSError:
                pass
        # The entries go from the DEEPEST created downwards, the order a device that never got them
        # would have left the tree in.
        lost_directories = 0
        for directory in sorted({str(p) for p in directories}, key=len, reverse=True):
            held_path = pathlib.Path(directory)
            if not held_path.is_dir() or held_path == held_path.parent:
                continue
            if str(held_path) in self.roots:
                raise Refused(f"STORAGE_FAKE_WOULD_REMOVE_ROOT {held_path}: a declared journal root "
                              f"reached the loss list, which no append can cause and no fake may do")
            shutil.rmtree(held_path, ignore_errors=True)
            lost_directories += 1
        return {"contents": held, "files": lost_files, "directories": lost_directories}


def frame(record):
    """One line: the payload's byte length, its sha256, and the payload."""
    payload = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    data = payload.encode("utf-8")
    return f"{len(data)} {hashlib.sha256(data).hexdigest()} {payload}\n".encode("utf-8")


def record_problems(record):
    """What is wrong with one record, by name. Empty means it may be appended."""
    problems = []
    kind = record.get("kind")
    if kind not in KINDS:
        problems.append(f"JOURNAL_KIND {kind!r}: a record is {' or '.join(KINDS)}")
        return problems
    required = DESIGN_FIELDS + PLAN_ADDS + (DONE_ADDS if kind == "done" else ())
    for field in required:
        if field not in record:
            problems.append(f"JOURNAL_FIELD_ABSENT {kind}.{field}: §10.5's record names it")
    extra = sorted(set(record) - set(required) - {"kind"})
    if extra:
        problems.append(f"JOURNAL_FIELD_UNDECLARED {kind}: {', '.join(extra)}")
    for field in ("operation_id", "target", "item_id", "approval_id"):
        value = record.get(field)
        if field not in record:
            continue
        if not isinstance(value, str) or not value:
            problems.append(f"JOURNAL_VALUE {kind}.{field}: a non-empty string, not {value!r}")
            continue
        # No character that a reader, a renderer or a path could read as structure. These values are
        # written into a line-delimited journal and the target is opened by an effect: a Unicode
        # line separator in a target was accepted, and `str.splitlines` — which other readers in
        # this repo still use — would have split the record at it. The framing itself now carries
        # any payload (that is `read`'s job); what a legal RECORD may hold is this rule's.
        held_bad = sorted({repr(ch) for ch in value
                           if unicodedata.category(ch) in targets.CONTROL_CATEGORIES})
        if held_bad:
            problems.append(f"JOURNAL_CONTROL_CHARACTER {kind}.{field}: {', '.join(held_bad)} is "
                            f"not admissible in a value this journal carries on one line")
    target = record.get("target")
    if isinstance(target, str) and target:
        # The target is a path an effect will open, and ONE contract says what it names:
        # `runlib/targets.py`. These rules were a second copy, and the copies disagreed — this one
        # accepted `./claude/CLAUDE.md` where `drift` refused the same spelling, so an approval was
        # valid or invalid according to which surface was asked (the round-2 review). The codes keep
        # the `JOURNAL_` namespace by prefix, so a record still says which surface judged it while
        # the rule has one owner.
        for held in targets.lexical_problems(target):
            code, _, detail = held.partition(" ")
            problems.append(f"JOURNAL_{code} {kind}: {detail}" if detail
                            else f"JOURNAL_{code} {kind}")
    return problems


def planned(operation_id, target, before_sha256, after_sha256, item_id, approval_id):
    """A `planned` record, refused if it is not one."""
    held = {"kind": "planned", "operation_id": operation_id, "target": target,
            "before_sha256": before_sha256, "after_sha256": after_sha256, "item_id": item_id,
            "approval_id": approval_id}
    problems = record_problems(held)
    if problems:
        raise Refused("; ".join(problems))
    return held


def done(operation_id, target, before_sha256, after_sha256, item_id, approval_id, commit=None):
    """A `done` record, refused if it is not one."""
    held = {"kind": "done", "operation_id": operation_id, "target": target,
            "before_sha256": before_sha256, "after_sha256": after_sha256, "item_id": item_id,
            "approval_id": approval_id, "commit": commit}
    problems = record_problems(held)
    if problems:
        raise Refused("; ".join(problems))
    return held


def plan_digest(record):
    """The identity of an operation: the sha256 of its WHOLE plan.

    Keyed on `operation_id` alone, two different plans were one operation: `journalled` compared the
    id and the kind, so an OLDER plan already in the journal satisfied the durability check for a new
    one, and the new plan's effect ran against a record that described something else. The digest is
    over every field of the plan but its kind, canonically, so "the same operation" means the same
    plan and nothing looser (the WP-21 round-2 review).
    """
    held = {key: value for key, value in (record or {}).items() if key != "kind"}
    return hashlib.sha256(json.dumps(held, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _read_bytes(confined, pieces, storage):
    blob = storage.read_bytes(confined, pieces)
    return b"" if blob is None else blob


def _parse(blob):
    """`read`'s answer over bytes already in hand, so a reader under the lock re-reads nothing."""
    return _records_of(blob)


def operation_problems(records, record):
    """Why this operation may not be planned now, by name — three different answers.

    A retry is not a re-execution. The three states a journal can already be in for one operation id
    are different situations with different answers, and `journalled` ran the effect again in all
    three: it only asked whether a record with that id and kind existed.

    * COMPLETED — a `done` record is there. The effect happened; running it again is the duplicate
      the journal exists to prevent.
    * CONFLICTING — a `planned` record is there with a DIFFERENT plan. The id has been reused for
      another operation, and neither plan may be taken as the other's durability.
    * UNRECONCILED — a `planned` record with the same plan and no `done`. This is a retry, and it
      belongs to recovery (§10.6): whether the effect happened is exactly what the journal cannot
      say, so the callback is not called again here.
    """
    held = plan_digest(record)
    problems = []
    # A plan whose `done` is in the journal is COMPLETED and nothing else. Asked row by row, the
    # planned row of a finished operation also answered UNRECONCILED - "no done record" - ahead of
    # the done row's answer, and sent a retry of finished work to recovery (the round-8 review).
    completed = any(row.get("operation_id") == record.get("operation_id") and row.get("kind") == "done"
                    for row in records)
    for row in records:
        if row.get("operation_id") != record.get("operation_id"):
            continue
        if row.get("kind") == "done":
            problems.append(f"JOURNAL_OPERATION_COMPLETED {record.get('operation_id')}: the journal "
                            f"already holds a done record for it, so the effect has been taken and "
                            f"taking it again is the duplicate this journal exists to prevent")
        elif row.get("kind") == "planned":
            if plan_digest(row) != held:
                problems.append(f"JOURNAL_OPERATION_CONFLICTING {record.get('operation_id')}: the "
                                f"journal holds another plan under this id ({plan_digest(row)[:12]}… "
                                f"against {held[:12]}…), so neither can serve as the other's "
                                f"durability")
            elif not completed:
                problems.append(f"JOURNAL_OPERATION_UNRECONCILED {record.get('operation_id')}: a "
                                f"plan for it is durable with no done record, which is what §10.6's "
                                f"recovery decides; a retry enters recovery and does not re-run the "
                                f"effect")
    return problems


def append(path, record, root, storage=None):
    """Append one record, durably, and return it. Refuses before writing anything.

    `root` is the journal's declared root (`run.json.destinations.runtime_state`): a journal written
    outside it is the hole `destinations.py` exists to close, and the question is asked through that
    module so one answer serves both. Every byte goes through ONE confined handle on that root, and
    read-validate-write happens under the journal's one lock.
    """
    storage = storage or Storage()
    with Confined(root) as confined:
        pieces = confined.parts(path)
        problems = record_problems(record)
        if problems:
            raise Refused("; ".join(problems))
        with confined.lock():
            _validate_before_append(confined, pieces, storage, path)
            storage.append(confined, pieces, frame(record))
    return record


def _validate_before_append(confined, pieces, storage, path):
    """What must be true of the journal before anything is added to it, read under the lock.

    An unterminated tail is reconciled first: appending blindly put the new frame on the same line
    as the torn one, and recovery then read ONE unframed line where two records had been written —
    the second durable and invisible. §10.6 expects a torn tail; it does not expect the next append
    to bury it.

    A complete line whose frame does not verify is CORRUPTION, not an interrupted write, and no
    append or effect proceeds over it: `read`'s problems were computed and ignored, so `journalled`
    appended a plan and ran an effect on a journal already reported as damaged in the middle. Tail
    repair and corruption recovery stay apart — the first is mechanical, the second is a decision.
    """
    held = _parse(_read_bytes(confined, pieces, storage))
    if held["problems"]:
        raise Refused(f"JOURNAL_CORRUPT {path}: {'; '.join(held['problems'])}. An append and any "
                      f"effect are refused over a journal with complete-line corruption; tail "
                      f"repair does not touch it and recovery decides what does")
    if held["torn"] and held.get("unterminated"):
        raise Refused(f"JOURNAL_TAIL_UNRECONCILED {path}: the last line carries no newline, so an "
                      f"append would put two records on one line. Reconcile the tail "
                      f"(`reconcile_tail`) before adding to this journal")
    return held


def journalled(path, record, root, effect, storage=None):
    """Append the plan, take the effect, append the done record. Returns both records.

    The API a future effect loop calls, and the reason it exists: §10.5's ordering is "no effect
    precedes a successful fsync", and nothing in this module could show that an effect WAITED,
    because the only ordering control appended a record and then looked at the journal. It invoked no
    effect, created no target and held no before-state, so it would have passed over a loop that took
    the effect first.

    `effect` is called with no arguments and its return value is carried into the done record's
    `result`. It is called EXACTLY ONCE, after the plan record is durable, and not at all when the
    append refuses, when the storage loses the write, or when the journal already knows this
    operation — completed, conflicting or unreconciled, three different refusals. Calling it twice
    with one id ran the effect twice; that is now a refusal by name.

    The whole sequence — read, validate, plan, effect, done — is under the journal's ONE lock, held
    across all of it. A lock taken per write would let another writer append between the plan and the
    done record, and the reconciliation that reads this journal cannot tell that interleaving from a
    crash.
    """
    storage = storage or Storage()
    problems = record_problems(record)
    if problems:
        raise Refused("; ".join(problems))
    with Confined(root) as confined:
        pieces = confined.parts(path)
        with confined.lock():
            held = _validate_before_append(confined, pieces, storage, path)
            refusals = operation_problems(held["records"], record)
            if refusals:
                raise Refused("; ".join(refusals))
            storage.append(confined, pieces, frame(record))
            # Durable only if the journal now actually holds it: a storage that lost the unsynced
            # write has told us nothing was written, and the effect must not run. The plan is
            # recognised by its DIGEST, not by its id — an older plan under the same id used to
            # satisfy this check for a new one.
            after = _parse(_read_bytes(confined, pieces, storage))
            # The WHOLE parse, before anything irreversible: the pre-append validation cannot see a
            # journal this very append damaged, and `after` was searched for one record while its
            # own problems went unread. A journal that does not parse is not a journal an effect may
            # stand on.
            if after["problems"]:
                raise Refused(f"JOURNAL_CORRUPT {path}: {'; '.join(after['problems'])} — the "
                              f"journal does not parse after the append, so the effect is not "
                              f"taken and tail repair does not touch it")
            if not any(row.get("kind") == "planned" and plan_digest(row) == plan_digest(record)
                       for row in after["records"]):
                raise Refused(f"JOURNAL_PLAN_NOT_DURABLE {path}: the plan for "
                              f"{record.get('operation_id')!r} is not in the journal after the "
                              f"append, so the effect is not taken")
            result = effect()
            finished = done(record["operation_id"], record["target"], record["before_sha256"],
                            record["after_sha256"], record["item_id"], record["approval_id"],
                            commit=result if isinstance(result, str) else None)
            storage.append(confined, pieces, frame(finished))
    return {"planned": record, "done": finished, "result": result}


def reconcile_tail(path, root, storage=None):
    """Truncate an unterminated tail so appending is safe again, and say what was dropped.

    The tail is returned rather than silently discarded: an interrupted append is a record somebody
    may want to look at, and recovery (§10.6) is the reader that decides. Only a tail with no newline
    is removed — a complete line whose frame does not verify is corruption, not an interrupted write,
    and this does not touch it.

    Read, validate and truncate happen under the SAME lock and through the SAME confined handle as an
    append. Before, this read the bytes, computed the cut, and then reopened the path with a plain
    `open` to truncate: another recovery could repair the tail and append a record in between, and
    the truncation then cut a record that had been made durable after the read (the WP-21 round-2
    review). Under the lock, the bytes are re-read and the tail re-identified immediately before the
    cut, so the length this truncates to is the length it just measured.
    """
    storage = storage or Storage()
    with Confined(root) as confined:
        pieces = confined.parts(path)
        with confined.lock():
            blob = storage.read_bytes(confined, pieces)
            if blob is None:
                return {"dropped": None}
            if not blob or blob.endswith(b"\n"):
                return {"dropped": None}
            cut = blob.rfind(b"\n") + 1
            dropped = blob[cut:]
            # Re-measured under the lock, immediately before the cut. Equal bytes are what licenses
            # the truncation; anything else means the journal moved and this answer is stale.
            again = storage.read_bytes(confined, pieces)
            if again != blob:
                raise Refused(f"JOURNAL_MOVED_UNDER_RECONCILE {path}: the journal changed between "
                              f"the read and the truncation ({len(blob)} bytes then "
                              f"{len(again or b'')}), so the cut this computed is not the cut this "
                              f"file needs")
            storage.truncate(confined, pieces, cut)
            return {"dropped": dropped.decode("utf-8", errors="replace")}


def read(path):
    """`{records, torn, problems}` — the journal as a reader may trust it.

    A torn line is returned rather than raised: at the tail it is an interrupted append, which §10.6
    expects. One anywhere else is corruption and is named as a problem, because an append cannot tear
    a line that already has a line after it.

    Reading takes no lock: recovery is allowed to look at a journal mid-append, and that is the
    reading §10.6 does. What may not happen without the lock is deciding or writing, which is why
    `append`, `journalled` and `reconcile_tail` re-read the bytes through the confined handle under
    it rather than calling this.
    """
    path = pathlib.Path(path)
    if not path.is_file():
        return {"records": [], "torn": [], "problems": [], "unterminated": False}
    return _records_of(path.read_bytes())


def _records_of(blob):
    """One parser for the journal's bytes, whoever is holding them.

    The locked path reads the bytes through the confined handle and this turns them into records, so
    a reader under the lock and a reader outside it cannot disagree about what the file says.
    """
    unterminated = bool(blob) and not blob.endswith(b"\n")
    pieces = blob.split(b"\n")
    if pieces and pieces[-1] == b"":
        pieces = pieces[:-1]
    records, torn, problems = [], [], []
    for number, raw in enumerate(pieces, start=1):
        last = number == len(pieces)
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError:
            line = None
        held = None if line is None else _unframe(line)
        if held is None or (last and unterminated):
            # An unterminated tail is torn even when the bytes before it frame correctly: the
            # delimiter is part of the record, and a reader that accepts the frame without it
            # cannot tell a finished append from one that stopped before its newline.
            torn.append({"line": number, "text": (line or repr(raw))[:120],
                         "why": "no trailing newline" if held is not None else "unframed"})
            # An append is interrupted BEFORE its newline, so the only line a tear can explain is a
            # last line with no newline. Any other unframed line is corruption, and the final one
            # was the hole: a complete last line that framed nowhere went into `torn` with no
            # problem at all, so `append` and `journalled` ran over it (the round-3 review).
            if not last:
                problems.append(f"JOURNAL_TORN_MIDDLE line {number}: a line with lines after it "
                                f"cannot have been torn by an append, so this is corruption")
            elif not unterminated:
                problems.append(f"JOURNAL_CORRUPT_LINE line {number}: the last line carries its "
                                f"newline and frames nowhere, so no interrupted append explains it "
                                f"— this is corruption, and tail repair does not touch it")
            continue
        records.append(held)
    return {"records": records, "torn": torn, "problems": problems,
            "unterminated": unterminated}


def _unframe(line):
    """The record a framed line carries, or None when the line is torn."""
    head, _, payload = line.partition(" ")
    digest, _, payload = payload.partition(" ")
    if not head.isdigit() or len(digest) != 64:
        return None
    data = payload.encode("utf-8")
    if len(data) != int(head) or hashlib.sha256(data).hexdigest() != digest:
        return None
    try:
        held = json.loads(payload)
    except ValueError:
        return None
    return held if isinstance(held, dict) else None


def pending(records):
    """Every `planned` operation with no `done`, in the order they were planned.

    What §10.6 reconciles. Keyed by operation id, because that is the durable identity: a target can
    carry several operations in one run and each is reconciled on its own.
    """
    finished = {row["operation_id"] for row in records if row.get("kind") == "done"}
    held, seen = [], set()
    for row in records:
        if row.get("kind") != "planned":
            continue
        operation = row.get("operation_id")
        if operation in finished or operation in seen:
            continue
        seen.add(operation)
        held.append(row)
    return held


# Each required field paired with the PHRASE §10.5 names it by. A parameter so the suite can hand
# this check a SHORTENED list and watch it say so: a coverage check whose own list is the thing that
# can shrink has no negative control otherwise.
DESIGN_PHRASES = (("operation_id", "durable operation id"), ("target", "target"),
                  ("before_sha256", "expected before-hash"), ("after_sha256", "intended after-hash"))


def fidelity_problems(phrases=DESIGN_PHRASES):
    """The required sets against §10.5's sentence (done-when 12), and the seams against their list."""
    problems = []
    # Each required field paired with the PHRASE §10.5 names it by, so the check reads the sentence
    # rather than a mangling of it: the first version stripped characters until "operation id"
    # became "operationid" and then failed on a sentence that says it.
    named = phrases
    if sorted(field for field, _phrase in named) != sorted(DESIGN_FIELDS):
        problems.append(f"DESIGN_FIELD_SET: this check covers "
                        f"{', '.join(sorted(field for field, _p in named))}, the required set is "
                        f"{', '.join(sorted(DESIGN_FIELDS))}")
    for field, phrase in named:
        if phrase not in DESIGN_10_5:
            problems.append(f"DESIGN_FIELD_UNNAMED {field}: §10.5's sentence here does not say "
                            f"{phrase!r}")
    for kind in KINDS:
        if f"`{kind}` record" not in DESIGN_10_5:
            problems.append(f"DESIGN_KIND_UNNAMED {kind}: §10.5's sentence here does not name it")
    if "fsynced" not in DESIGN_10_5:
        problems.append("DESIGN_FSYNC_UNNAMED: the sentence no longer says the record is fsynced, "
                        "which is the whole order this module exists to keep")
    return problems


def document():
    """What this module is, for a reader deciding whether to trust the journal."""
    return {"design": DESIGN_10_5, "kinds": list(KINDS),
            "planned_fields": list(DESIGN_FIELDS + PLAN_ADDS),
            "done_fields": list(DESIGN_FIELDS + PLAN_ADDS + DONE_ADDS),
            "seams": list(FAULTS),
            "framing": "<payload byte length> <sha256 of the payload> <payload json>"}


def _short_write_probe(path, record, root=None):
    """Append with the device accepting one byte and then zero: the short-write refusal's own case.

    A real short write cannot be arranged on demand, so it arrives through `Storage._write_once`, a
    named seam. It was `unittest.mock.patch.object(os, "write", ...)` until `dispatch.py`'s
    source-shape rule refused handing an executor's module to anybody from a shipped module — which
    is right, and the seam is the better shape anyway: nothing global is swapped.
    """
    calls = {"n": 0}

    def short(_handle, data):
        calls["n"] += 1
        # The cap is what makes this a control rather than a hang. With the `held <= 0` refusal
        # reverted, a device returning zero forever spins the loop forever: a revert trial over the
        # unbounded probe stopped reporting and timed out at fifteen minutes with nothing said. The
        # cap turns that into a named exception, so the trial reads "the guard is load-bearing"
        # instead of waiting.
        if calls["n"] > 64:
            raise AssertionError("JOURNAL_WRITE_LOOP_UNBOUNDED: the writer accepted a zero-byte "
                                 "write without refusing, so the loop does not terminate")
        return 1 if calls["n"] == 1 else 0

    class ShortDevice(Storage):
        """A device that accepts one byte and then none, through the named seam."""

        def _write_once(self, handle, data):
            return short(handle, data)

    return append(path, record, root=root or str(pathlib.Path(path).parent),
                  storage=ShortDevice())


# ---- self-test ---------------------------------------------------------------------------------


def self_test():
    failures, ran = [], []

    def control(name, got, want):
        ran.append(name)
        if want not in str(got):
            failures.append((name, f"expected {want!r} in {str(got)[:400]!r}"))

    def clean(name, held):
        ran.append(name)
        if held:
            failures.append((name, f"expected nothing, got {held}"))

    def refusal(call):
        try:
            call()
        except Refused as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - a control that dies is not a control
            return f"RAISED {type(exc).__name__}: {exc}"
        return ""

    import shutil
    import tempfile
    # The declared root is a SUBDIRECTORY of the fixture tree, and the escape target is a sibling
    # inside the same tree. The first form used `root.parent` - which is the shared temp directory -
    # so a revert trial that removed the containment check wrote `/tmp/elsewhere.jsonl` and every
    # later run then failed the "that path has no file" control for a file no run of its own made.
    # An escape target outside the fixture tree is not a fixture.
    held_tree = pathlib.Path(tempfile.mkdtemp(prefix="jrnl-", dir="/tmp"))
    root = held_tree / "declared"
    outside = held_tree / "other" / "elsewhere.jsonl"
    root.mkdir()
    try:
        def fx_plan(**over):
            held = {"operation_id": "op-1", "target": "claude/guides/g.md",
                    "before_sha256": "a" * 64, "after_sha256": "b" * 64,
                    "item_id": "i-1", "approval_id": "A-0123456789abcdef"}
            held.update(over)
            return planned(**held)

        def fx_done(**over):
            held = {"operation_id": "op-1", "target": "claude/guides/g.md",
                    "before_sha256": "a" * 64, "after_sha256": "b" * 64,
                    "item_id": "i-1", "approval_id": "A-0123456789abcdef", "commit": None}
            held.update(over)
            return done(**held)

        # ---- the record ------------------------------------------------------------------------
        clean("a planned record carrying §10.5's four fields and the plan's two is accepted",
              record_problems(fx_plan()))
        clean("and a done record, which also carries its commit or null", record_problems(fx_done()))
        control("a record of neither kind is refused by name",
                "; ".join(record_problems({"kind": "started"})), "JOURNAL_KIND")
        for field in DESIGN_FIELDS + PLAN_ADDS:
            control(f"a planned record without {field} is refused by name",
                    "; ".join(record_problems({k: v for k, v in fx_plan().items() if k != field})),
                    f"JOURNAL_FIELD_ABSENT planned.{field}")
        control("a done record without its commit field is refused, since §10.6 reconciles a commit "
                "by that field",
                "; ".join(record_problems({k: v for k, v in fx_done().items() if k != "commit"})),
                "JOURNAL_FIELD_ABSENT done.commit")
        control("a planned record carrying a commit is refused: a commit is the effect, and there is "
                "none yet", "; ".join(record_problems({**fx_plan(), "commit": "abc"})),
                "JOURNAL_FIELD_UNDECLARED planned: commit")
        control("a field no record declares is refused rather than carried",
                "; ".join(record_problems({**fx_plan(), "note": "x"})),
                "JOURNAL_FIELD_UNDECLARED planned: note")
        control("an empty operation id is refused, since it is the durable identity §10.6 reconciles by",
                refusal(lambda: fx_plan(operation_id="")), "JOURNAL_VALUE planned.operation_id")
        clean("§10.5's own sentence names every field this module requires of it", fidelity_problems())

        def with_sentence(sentence, call):
            """Run `call` with the design sentence replaced, restoring it however it ends."""
            global DESIGN_10_5
            kept = DESIGN_10_5
            DESIGN_10_5 = sentence
            try:
                return call()
            finally:
                DESIGN_10_5 = kept

        control("a sentence that no longer names the before-hash is reported, so the comparison is "
                "shown to fire rather than merely to exist",
                "; ".join(with_sentence(DESIGN_10_5.replace("expected before-hash", "a hash"),
                                        fidelity_problems)),
                "DESIGN_FIELD_UNNAMED before_sha256")
        control("and one that no longer says the record is fsynced",
                "; ".join(with_sentence(DESIGN_10_5.replace("and fsynced", ""), fidelity_problems)),
                "DESIGN_FSYNC_UNNAMED")
        control("a phrase list covering three of the four required fields is reported, so the "
                "coverage check cannot pass over what it left out",
                "; ".join(fidelity_problems(DESIGN_PHRASES[:3])), "DESIGN_FIELD_SET")
        clean("while the list this module ships covers the required set exactly",
              [p for p in fidelity_problems() if "DESIGN_FIELD_SET" in p])
        control("and one that stops naming the `done` record",
                "; ".join(with_sentence(DESIGN_10_5.replace("a `done` record", "a second record"),
                                        fidelity_problems)),
                "DESIGN_KIND_UNNAMED done")

        # ---- the framing -----------------------------------------------------------------------
        line = frame(fx_plan()).decode("utf-8")
        control("a framed line carries the payload's byte length first", line.split(" ")[0],
                str(len(json.dumps(fx_plan(), sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":")).encode("utf-8"))))
        control("and its sha256 second", line.split(" ")[1],
                hashlib.sha256(json.dumps(fx_plan(), sort_keys=True, ensure_ascii=False,
                                          separators=(",", ":")).encode("utf-8")).hexdigest())
        clean("a framed line reads back as the record it framed",
              [] if _unframe(line.rstrip("\n")) == fx_plan() else [f"{_unframe(line)}"])
        clean("a payload with Korean in it survives the frame, since the length is in BYTES",
              [] if _unframe(frame({**fx_plan(), "target": "한글/안내.md"}).decode().rstrip("\n"))
              == {**fx_plan(), "target": "한글/안내.md"} else ["the Korean payload did not survive"])
        clean("a truncated payload is torn, not believed",
              [] if _unframe(line.rstrip("\n")[:-5]) is None else ["a short payload was accepted"])
        clean("a payload whose digest does not match is torn",
              [] if _unframe(line.rstrip("\n").replace('"op-1"', '"op-2"')) is None
              else ["an altered payload was accepted"])
        clean("a line with no frame at all is torn", [] if _unframe("{\"kind\": \"planned\"}") is None
              else ["an unframed line was accepted"])

        # ---- the append ------------------------------------------------------------------------
        path = root / "state" / "journal.jsonl"
        append(path, fx_plan(), root=str(root))
        held = read(path)
        control("an appended record reads back", json.dumps(held["records"][0]), '"op-1"')
        clean("with nothing torn and no problem", held["torn"] + held["problems"])
        control("a journal outside its declared root is refused before anything is written",
                refusal(lambda: append(outside, fx_plan(), root=str(root))), "JOURNAL_OUTSIDE_ROOT")
        clean("and that path has no file", [] if not outside.exists()
              else ["a journal was written outside the root"])
        sibling = held_tree / f"{root.name}-other" / "journal.jsonl"
        control("a sibling whose NAME begins with the root's is outside it: the question is path "
                "parts, not text",
                refusal(lambda: append(sibling, fx_plan(), root=str(root))), "JOURNAL_OUTSIDE_ROOT")
        clean("and it has no file either",
              [] if not sibling.exists() else ["a journal was written into the name-prefix sibling"])
        # A symlink under the declared root: lexically inside, and the open is what refuses it.
        linked = root / "linked.jsonl"
        linked.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(held_tree / "other" / "escaped.jsonl", linked)
        control("a journal path that is a SYMLINK is refused by name: the open does not follow it, "
                "which is the half a lexical containment check cannot answer",
                refusal(lambda: append(linked, fx_plan(), root=str(root))), "JOURNAL_SYMLINK")
        clean("and the file it pointed at was never created",
              [] if not (held_tree / "other" / "escaped.jsonl").exists()
              else ["the append followed the symlink"])
        # A HARD link under the declared root: no symlink, the open succeeds, the bytes are outside.
        twin_source = held_tree / "other-twin" / "outside.jsonl"
        twin_source.parent.mkdir(parents=True, exist_ok=True)
        twin_source.write_bytes(b"")
        twin = root / "twin.jsonl"
        os.link(twin_source, twin)
        control("a journal with a second name is refused before a byte is appended",
                refusal(lambda: append(twin, fx_plan(), root=str(root))), "JOURNAL_HARD_LINKED")
        clean("and the file under its other name is unchanged",
              [] if twin_source.read_bytes() == b"" else ["the append wrote through the hard link"])
        twin_source.write_bytes(b"a tail with no newline")
        control("and reconciling its torn tail is refused the same way: a truncation through this "
                "name would cut the outside file",
                refusal(lambda: reconcile_tail(twin, root=str(root))), "JOURNAL_HARD_LINKED")
        clean("and the outside file kept its bytes",
              [] if twin_source.read_bytes() == b"a tail with no newline"
              else ["the truncation cut the hard-linked file"])
        control("the writer opens with O_NOFOLLOW rather than trusting the check",
                next(line.strip() for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                     if "flags = os.O_WRONLY" in line),
                "_NOFOLLOW")
        control("and the flag is resolved once at import, by attribute access rather than by "
                "handing the module to getattr",
                "resolved" if _NOFOLLOW else "zero on this platform", "resolved")
        control("and a short write is looped rather than acknowledged as a complete record",
                next(line.strip() for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                     if "while written < len(data)" in line),
                "while written < len(data)")
        control("a device that stops accepting bytes mid-record is refused by name",
                refusal(lambda: _short_write_probe(root / "short.jsonl", fx_plan())),
                "JOURNAL_SHORT_WRITE")

        # Its own symlinked root, under this control's own temp tree: a control that needs a
        # symlink builds one where it can see it, and never near the run's real roots.
        linked_root = held_tree / "linked-root"
        os.symlink(root, linked_root)
        control("a journal with no declared root at all is refused, not defaulted",
                refusal(lambda: append(path, fx_plan(), root=None)), "JOURNAL_ROOT_UNDECLARED")
        control("and a root that is a SYMLINK is refused before anything under it is reached, "
                "because a lexical check cannot see where it points",
                refusal(lambda: append(linked_root / "state" / "j.jsonl", fx_plan(),
                                       root=str(linked_root))),
                "JOURNAL_ROOT_UNOPENABLE")
        control("a malformed record is refused before the file is touched",
                refusal(lambda: append(root / "state" / "other.jsonl", {"kind": "planned"},
                                       root=str(root))),
                "JOURNAL_FIELD_ABSENT")
        clean("and that file was never created",
              [] if not (root / "state" / "other.jsonl").exists() else ["a refused record was written"])

        # ---- the torn tail ---------------------------------------------------------------------
        torn_path = root / "state" / "torn.jsonl"
        append(torn_path, fx_plan(), root=str(root))
        with open(torn_path, "ab") as handle:              # a tail cut mid-write
            handle.write(frame(fx_plan(operation_id="op-2"))[:-9])
        after = read(torn_path)
        control("a torn tail is reported as torn rather than raising",
                f'{len(after["records"])}:{len(after["torn"])}', "1:1")
        clean("and it is not a problem, because an interrupted append is what §10.6 expects",
              after["problems"])
        control("the torn line is named by its number", json.dumps(after["torn"]), '"line": 2')
        with open(torn_path, "ab") as handle:              # now something after the torn line
            handle.write(b"\n")
            handle.write(frame(fx_done(operation_id="op-3")))
        middle = read(torn_path)
        control("a torn line with lines after it is corruption, named as its own problem",
                "; ".join(middle["problems"]), "JOURNAL_TORN_MIDDLE")
        control("while the records around it still read", str(len(middle["records"])), "2")

        # ---- the seams and the lost write ------------------------------------------------------
        for seam in FAULTS:
            disarm = inject(seam)
            try:
                seam_path = root / "state" / f"seam-{seam}.jsonl"
                raised = ""
                try:
                    append(seam_path, fx_plan(), root=str(root))
                except Injected as exc:
                    raised = str(exc)
                control(f"the {seam} seam fires when armed", raised, seam)
            finally:
                disarm()
        # The real Storage's fsync cannot be observed from inside this process - a write is visible
        # to a reader whether or not it reached the device - so the ORDER is asserted on its source:
        # write, then the seam, then fsync, before the handle is closed. `LosingStorage` is what
        # shows the consequence of the order being wrong.
        import inspect
        storage_src = inspect.getsource(Storage.append)
        # The write is now a loop over `os.write(handle, data[written:])`, so the order is read
        # from the three operations rather than from three exact lines.
        steps = []
        for line in storage_src.splitlines():
            held_line = line.strip()
            for mark in ("self._write_once(handle,", "self._durable_file(handle,",
                         "self._sync_directory(held_fd,"):
                if held_line.startswith(mark) or held_line.startswith("held = " + mark):
                    steps.append(mark.rstrip("(,"))
        control("the real storage writes, then makes the file durable, then makes its whole "
                "directory chain durable, in that order", " -> ".join(steps),
                "self._write_once(handle -> self._durable_file(handle -> "
                "self._sync_directory(held_fd")
        control("and what `durable` asks the platform for is read from the platform, not assumed: "
                "on darwin plain fsync does not flush the drive's own cache, so F_FULLFSYNC is "
                "asked for where it exists",
                durable(os.open(str(root), os.O_RDONLY)),
                "F_FULLFSYNC" if hasattr(fcntl, "F_FULLFSYNC") else "fsync")
        control("a seam name the list does not hold is refused, so a misspelled seam cannot test "
                "nothing", refusal(lambda: inject("after_the_effect")), "FAULT_UNKNOWN")
        clean("and no seam stays armed after its control", sorted(_INJECTED))

        # No effect precedes a SUCCESSFUL fsync: with the fault between the write and the fsync, the
        # record's fate is whatever the storage decides, and the TARGET shows no effect either way.
        losing = LosingStorage()
        lost_path = root / "state" / "lost.jsonl"
        disarm = inject("after_write_before_fsync")
        try:
            try:
                append(lost_path, fx_plan(), root=str(root), storage=losing)
            except Injected:
                pass
        finally:
            disarm()
        control("a fault between the write and the fsync leaves the record unsynced",
                str(len(losing.unsynced)), "1")
        control("and losing the unsynced write leaves the journal with no such record",
                f'{losing.lose_unsynced()["contents"]}:{len(read(lost_path)["records"])}',
                "1:0")
        clean("which is the state §10.5 requires: the caller had not been told the record was "
              "durable, so it had not taken its effect",
              [] if not lost_path.exists() or not read(lost_path)["records"] else ["the record survived"])
        # ---- durability of the NAMES, not only the bytes --------------------------------------
        #
        # `mkdir(parents=True)` can create a whole chain while only the journal and its immediate
        # parent are fsynced: the record is then durable inside directory entries that never
        # reached the device. The WP-21 review found it, and found that the storage fake could not
        # show it either, because it modelled contents and not entries.
        class CountingStorage(Storage):
            """A real storage that records which directories it synced, and how."""

            def __init__(self):
                self.synced = []
                self.calls = []

            def _sync_directory(self, held_fd, label):
                self.synced.append(str(label))
                Storage._sync_directory(self, held_fd, label)

            def _durable_file(self, handle, label, created):
                self.calls.append(("file", str(label), created))
                Storage._durable_file(self, handle, label, created)

        counting = CountingStorage()
        deep_path = root / "state" / "a" / "b" / "c" / "deep.jsonl"
        append(deep_path, fx_plan(), root=str(root), storage=counting)
        # The WHOLE chain, every time — including the root and including directories this append
        # found already there. A retry after a failed sync creates nothing, so a rule that synced
        # only what it created synced nothing at all and left the record durable inside entries that
        # never reached the device.
        control("the whole directory chain is synced, root included, not only what this append "
                "created",
                json.dumps(sorted(set(counting.synced))),
                json.dumps(sorted({str(root), str(root / "state"), str(root / "state" / "a"),
                                   str(root / "state" / "a" / "b"),
                                   str(root / "state" / "a" / "b" / "c")})))
        again = CountingStorage()
        # A different journal in the SAME chain: the directories are all there already, so this is
        # the retry case — nothing to create, and a created-only rule would sync nothing.
        append(deep_path.parent / "deep-again.jsonl", fx_plan(operation_id="OP-again"),
               root=str(root), storage=again)
        control("and a SECOND append into the same chain syncs it again, which is the retry the "
                "created-only rule skipped", json.dumps(sorted(set(again.synced))),
                json.dumps(sorted(set(counting.synced))))
        control("and the record is readable afterwards",
                str(len(read(deep_path)["records"])), "1")
        # The entry a device never got. `lose_names=True` is the storage whose directory sync did
        # NOT happen, which is the only state in which an entry can be lost — a directory that was
        # synced is durable, and the fake used to lose it anyway, so this control was watching the
        # fake's bookkeeping instead of the rule (the round-3 review).
        losing_dirs = LosingStorage(lose_names=True)
        lost_deep = root / "state" / "x" / "y" / "lost-deep.jsonl"
        append(lost_deep, fx_plan(), root=str(root), storage=losing_dirs)
        held_lost = losing_dirs.lose_unsynced()
        control("and the storage fake models directory ENTRIES as their own loss, which is what "
                "kept this defect invisible (the contents loss has its own control above; this one "
                "is about the names)",
                json.dumps({"directories": held_lost["directories"] > 0}),
                '{"directories": true}')
        clean("losing the entry takes the journal under it, because nothing can reach what has no "
              "name", [] if not lost_deep.exists() else ["the journal survived its own directory"])
        # And the same chain with the sync PERFORMED keeps both: the entry is not in the loss list
        # at all, so the two cases differ by the sync and not by the control's wording.
        kept_dirs = LosingStorage()
        kept_deep = root / "state" / "kept" / "deep" / "kept.jsonl"
        append(kept_deep, fx_plan(operation_id="OP-kept"), root=str(root), storage=kept_dirs)
        held_kept = kept_dirs.lose_unsynced()
        control("a chain whose directories were synced loses no entry, and the journal is still "
                "there",
                json.dumps({"directories": held_kept["directories"], "exists": kept_deep.exists()}),
                '{"directories": 0, "exists": true}')

        # ---- the framing, on the protocol's own delimiter ------------------------------------------
        #
        # `frame` writes with ensure_ascii=False, so a payload can carry any Unicode; `read` used
        # `str.splitlines()`, which splits on U+2028, U+2029, U+0085 and more. A record whose text
        # held one of those came back as two torn lines and read as corruption. The WP-21 review
        # found it; these controls are the round trips it asked for.
        # Asked UNCONDITIONALLY. The first version of this block only ran its controls when writing
        # the record was refused, so a change that stopped refusing would have made the whole
        # framing question silently unasked — six controls that could not fire.
        for name, separator in (("line separator U+2028", "\u2028"),
                                ("paragraph separator U+2029", "\u2029"),
                                ("next line U+0085", "\u0085"),
                                ("vertical tab", "\v"),
                                ("form feed", "\f"),
                                ("carriage return", "\r")):
            sep_path = root / "state" / f"sep-{ord(separator)}.jsonl"
            sep_path.parent.mkdir(parents=True, exist_ok=True)
            sep_path.write_bytes(frame({"kind": "note", "text": f"before{separator}after"}))
            held_sep = read(sep_path)
            control(f"a payload containing a {name} is one record, not two torn lines",
                    f'{len(held_sep["records"])}:{len(held_sep["torn"])}', "1:0")
            control(f"and its text survives the round trip with the {name} intact",
                    json.dumps((held_sep["records"] or [{}])[0].get("text")),
                    json.dumps(f"before{separator}after"))
        for bad_target, want in (("claude/guides/g\u2028x.md", "JOURNAL_CONTROL_CHARACTER"),
                                 ("/etc/passwd", "JOURNAL_TARGET_ABSOLUTE"),
                                 ("~/.claude/CLAUDE.md", "JOURNAL_TARGET_ABSOLUTE"),
                                 ("claude/../../etc/x", "JOURNAL_TARGET_TRAVERSAL"),
                                 ("claude//guides/g.md", "JOURNAL_TARGET_SPELLING"),
                                 ("claude/guides/", "JOURNAL_TARGET_SPELLING"),
                                 # The spelling the two surfaces disagreed on: this suite took it
                                 # and `drift` refused it, so one approval was valid or invalid by
                                 # which surface was asked. One contract now answers both.
                                 ("./claude/CLAUDE.md", "JOURNAL_TARGET_SPELLING"),
                                 ("claude/./CLAUDE.md", "JOURNAL_TARGET_SPELLING")):
            control(f"a target spelled {bad_target!r} is refused by name",
                    "; ".join(record_problems({**fx_plan(), "target": bad_target})), want)
        control("and a control character in the approval id is refused too, since every value here "
                "is written on one line",
                "; ".join(record_problems({**fx_plan(), "approval_id": "A-1\u0085x"})),
                "JOURNAL_CONTROL_CHARACTER")
        clean("while an ordinary target passes", record_problems(fx_plan()))
        control("the rule is the identity contract's, not a second copy here: the two surfaces "
                "answer one question with one answer",
                "; ".join(f"{held}|{targets.lexical_problems('./claude/CLAUDE.md')[0].split(' ')[0]}"
                          for held in ["journal"]),
                "journal|TARGET_SPELLING")

        # A control character in a record's own fields is a different question, and the record
        # rules answer it: the framing must carry any payload, and the rules decide which payloads
        # are legal records.
        control("and the append refuses such a record before writing anything",
                refusal(lambda: append(root / "state" / "ctl.jsonl",
                                       {**fx_plan(), "target": "claude/guides/g\u2028x.md"},
                                       root=str(root))),
                "JOURNAL_CONTROL_CHARACTER")
        clean("with no file left behind",
              [] if not (root / "state" / "ctl.jsonl").exists() else ["a journal was created"])

        # A COMPLETE frame whose final newline never reached the device: torn, and appending to it
        # is refused rather than putting two records on one line.
        tail_path = root / "state" / "tail.jsonl"
        tail_path.parent.mkdir(parents=True, exist_ok=True)
        tail_path.write_bytes(frame(fx_plan()).rstrip(b"\n"))
        held_tail = read(tail_path)
        control("a frame with no trailing newline is torn, not a finished record",
                f'{len(held_tail["records"])}:{len(held_tail["torn"])}:{held_tail["unterminated"]}',
                "0:1:True")
        control("and the tear says why",
                json.dumps((held_tail["torn"] or [{}])[0].get("why")),
                '"no trailing newline"')
        control("appending to such a journal is refused by name, instead of burying the tail",
                refusal(lambda: append(tail_path, fx_plan(), root=str(root))),
                "JOURNAL_TAIL_UNRECONCILED")
        held_reconciled = reconcile_tail(tail_path, str(root))
        control("reconciling it returns what was dropped rather than discarding it silently",
                json.dumps(held_reconciled["dropped"] == frame(fx_plan()).rstrip(b"\n").decode()),
                "true")
        append(tail_path, fx_plan(), root=str(root))
        control("and then the append lands as one record on its own line",
                f'{len(read(tail_path)["records"])}:{len(read(tail_path)["torn"])}', "1:0")
        clean("reconciling a journal with a complete tail drops nothing",
              [] if reconcile_tail(tail_path, str(root))["dropped"] is None else ["it dropped a line"])
        control("and reconciling outside the declared root is refused like any other write",
                refusal(lambda: reconcile_tail(held_tree / "other" / "x.jsonl", str(root))),
                "JOURNAL_OUTSIDE_ROOT")

        # ---- the ordering, with an effect that is actually invoked --------------------------------
        #
        # The controls above show the RECORD's fate. They say nothing about whether an effect waited
        # for it, because none of them has an effect: that was the WP-21 review's finding, and
        # `journalled` is the seam it asked for. The target here is a file inside the fixture, and
        # the before-state is held so "the effect did not happen" is a fact rather than an absence.
        effects = []
        target_file = root / "state" / "target.txt"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text("before\n", encoding="utf-8")

        def take_effect():
            effects.append(target_file.read_text(encoding="utf-8"))
            target_file.write_text("after\n", encoding="utf-8")
            return "deadbeef" * 5

        order_path = root / "state" / "ordered.jsonl"
        held_order = journalled(order_path, fx_plan(), str(root), take_effect)
        control("the effect ran, and the journal holds the plan before it did",
                f'{len(effects)}:{effects[0].strip() if effects else "never ran"}', "1:before")
        control("and the done record follows it", json.dumps(held_order["done"]["kind"]), '"done"')
        control("with the effect's own result carried into it",
                json.dumps(held_order["done"]["commit"]), '"deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"')
        # compared as a LIST, here, and only the verdict handed to `control` (which looks for a substring):
        # joined with commas, `planned,done` was found inside `planned,done,planned,done` (the S11 review)
        control("so the journal reads plan then done, in that order, and nothing else",
                "exactly" if [row["kind"] for row in read(order_path)["records"]] == ["planned", "done"]
                else json.dumps([row["kind"] for row in read(order_path)["records"]]), "exactly")
        control("and the target was changed exactly once", target_file.read_text(encoding="utf-8"),
                "after")

        # The fault case: a storage that loses the unsynced plan must leave the effect UNTAKEN.
        untaken = []
        lost_target = root / "state" / "untaken.txt"
        lost_target.write_text("before\n", encoding="utf-8")

        class SilentStorage(Storage):
            """Returns from `append` having written nothing.

            Not a crash and not a refusal: the shape where a storage says it is done and the device
            holds nothing. `LosingStorage` cannot model it — it writes on the way through and
            `lose_unsynced` only forgets the list — so the check that the plan is really IN the
            journal needs its own fake.
            """

            def append(self, confined, pieces, data):
                fds, _leaf, _created = confined.walk(pieces, create=True)
                for held_fd in fds[1:]:
                    os.close(held_fd)

        said_order = refusal(lambda: journalled(
            root / "state" / "untaken.jsonl",
            fx_plan(), str(root),
            lambda: untaken.append("the effect ran") or "x",
            storage=SilentStorage()))
        control("an effect is NOT taken when the plan record did not survive the append",
                f'{said_order}|{len(untaken)}', "JOURNAL_PLAN_NOT_DURABLE")
        # And the fault BEFORE the fsync: the append raises, so `journalled` never reaches the
        # effect. The two together cover both ways the plan can fail to become durable.
        faulted = []
        disarm_order = inject("after_write_before_fsync")
        try:
            said_fault = refusal(lambda: journalled(
                root / "state" / "faulted.jsonl", fx_plan(), str(root),
                lambda: faulted.append("the effect ran") or "x", storage=LosingStorage()))
        finally:
            disarm_order()
        control("a fault between the write and the fsync stops the effect too",
                f'{said_fault}|{len(faulted)}', "Injected")
        clean("and that effect was never called either", faulted)
        clean("and the target is untouched", [] if lost_target.read_text(encoding="utf-8") == "before\n"
              else ["the effect ran anyway"])
        clean("the effect was never called at all", untaken)

        kept = LosingStorage()
        keep_path = root / "state" / "kept.jsonl"
        append(keep_path, fx_plan(), root=str(root), storage=kept)
        control("while a completed append is synced, so losing nothing loses nothing",
                f'{kept.lose_unsynced()["contents"]}:{len(read(keep_path)["records"])}',
                "0:1")

        # ---- what recovery reads ----------------------------------------------------------------
        many = [fx_plan(operation_id="op-a"), fx_plan(operation_id="op-b"),
                fx_done(operation_id="op-a"), fx_plan(operation_id="op-c")]
        control("every planned operation with no done is pending, in the order planned",
                ",".join(row["operation_id"] for row in pending(many)), "op-b,op-c")
        clean("a done operation is not pending", [row for row in pending(many)
                                                  if row["operation_id"] == "op-a"])
        repeated = ",".join(row["operation_id"] for row in
                            pending(many + [fx_plan(operation_id="op-b")]))
        clean("a planned record repeated is pending once, since the operation id is the identity",
              [] if repeated == "op-b,op-c" else [f"pending is {repeated!r}"])
        clean("an empty journal has nothing pending", pending([]))
        # ---- the one lock, and what it spans ----------------------------------------------------
        #
        # Its place is FIXED and declared: `journal.lock` at the top of the declared root, reached
        # through the same confined handle as the journal. The proof that it is HELD is deterministic
        # and single-process: the control opens that file itself and asks for the lock without
        # blocking, so the answer is an immediate refusal rather than a wait, and nothing is slept on
        # or killed.
        def lock_is_held(where):
            """Whether `journal.lock` under `where` is exclusively held right now."""
            held_fd = os.open(str(pathlib.Path(where) / LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(held_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(held_fd, fcntl.LOCK_UN)
                return False
            except OSError:
                return True
            finally:
                os.close(held_fd)

        control("the lock's name is fixed and declared, not a caller's choice", LOCK_NAME,
                "journal.lock")
        clean("and no lock is held when nothing is in flight",
              [] if not lock_is_held(root) else ["the lock was already held"])
        lock_path = root / LOCK_NAME
        locked_during = []
        held_lock_journal = root / "state" / "locked.jsonl"
        journalled(held_lock_journal, fx_plan(operation_id="OP-lock"), str(root),
                   lambda: locked_during.append(lock_is_held(root)) or "x")
        control("the lock is held WHILE the effect runs, so nothing can append between the plan "
                "and the done record", json.dumps(locked_during), "[true]")
        clean("and it is released afterwards",
              [] if not lock_is_held(root) else ["the lock stayed held"])
        # The BOUND, deterministically: the control holds the lock itself and asks for it with a
        # wait of hundredths of a second, so the refusal arrives at once instead of in 30 s. The
        # production bound is asserted separately, as a number, because a control cannot wait it out.
        own_lock = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(own_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def held_under_contention():
                with Confined(str(root)) as other:
                    with other.lock(wait_s=0.01):
                        return "took it anyway"

            control("a lock another writer holds is refused BY NAME after its bound, not waited on "
                    "without a deadline", refusal(held_under_contention), "JOURNAL_LOCKED")
            control("and the refusal names the lock file, so the reader knows what to look at",
                    refusal(held_under_contention), LOCK_NAME)
        finally:
            fcntl.flock(own_lock, fcntl.LOCK_UN)
            os.close(own_lock)
        control("the production bound is 30 s and the retry is not a busy loop",
                f"{LOCK_WAIT_S:g}/{LOCK_RETRY_S:g}", "30/0.05")
        clean("and the lock is free again after the contending control let it go",
              [] if not lock_is_held(root) else ["the control kept the lock"])
        control("the lock file lives inside the root it protects",
                "inside" if destinations.inside(lock_path, root) else str(lock_path), "inside")
        control("and it is opened through the confined handle, by name under the root's own fd",
                next(line.strip() for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                     if "os.open(LOCK_NAME" in line),
                "dir_fd=self.fd")
        for held_name, held_source in (("append", inspect.getsource(append)),
                                       ("journalled", inspect.getsource(journalled)),
                                       ("reconcile_tail", inspect.getsource(reconcile_tail))):
            control(f"{held_name} does its reading and its writing under that lock",
                    "yes" if "with confined.lock():" in held_source else held_source[:200], "yes")

        # ---- reconciliation revalidates under the lock -------------------------------------------
        #
        # It read the bytes, computed the cut, and then REOPENED the path with a plain `open` to
        # truncate. Another recovery could repair the tail and append a record in between, and the
        # truncation then cut a record made durable after the read. The cut is now measured again
        # under the lock, immediately before it is made, and unequal bytes refuse rather than cut.
        class MovingStorage(Storage):
            """A storage whose second read returns a journal that grew, as a racing writer would."""

            def __init__(self):
                self.reads = 0

            def read_bytes(self, confined, pieces):
                self.reads += 1
                held = Storage.read_bytes(self, confined, pieces)
                if self.reads >= 2 and held is not None:
                    return held + b"another record arrived\n"
                return held

        moving_path = root / "state" / "moving.jsonl"
        append(moving_path, fx_plan(operation_id="OP-moving"), root=str(root))
        with open(moving_path, "ab") as handle:
            handle.write(b"a torn tail with no newline")
        said_moved = refusal(lambda: reconcile_tail(moving_path, str(root), storage=MovingStorage()))
        control("a journal that moved between the read and the truncation refuses rather than "
                "cutting the length it measured earlier", said_moved,
                "JOURNAL_MOVED_UNDER_RECONCILE")
        control("and the refusal says both lengths, so the reader can see what moved", said_moved,
                "bytes then")
        clean("and the tail it would have cut is still there, because nothing was truncated",
              [] if moving_path.read_bytes().endswith(b"a torn tail with no newline")
              else ["the file was truncated anyway"])
        held_dropped = reconcile_tail(moving_path, str(root))["dropped"]
        control("while an unmoved journal reconciles, so the refusal is the race and not the "
                "mechanism", held_dropped, "a torn tail with no newline")

        # ---- one operation id, three different situations ----------------------------------------
        #
        # `journalled` asked only whether a record with this id and kind existed, so calling it twice
        # with one id ran the effect TWICE, and an older plan under the same id satisfied the
        # durability check for a new one. Completed, conflicting and unreconciled are three answers.
        twice = []
        once_path = root / "state" / "once.jsonl"
        plan_once = fx_plan(operation_id="OP-once")
        journalled(once_path, plan_once, str(root), lambda: twice.append("ran") or "x")
        said_completed = refusal(lambda: journalled(once_path, plan_once, str(root),
                                                    lambda: twice.append("ran again") or "x"))
        control("a COMPLETED operation is refused by its own name", said_completed,
                "JOURNAL_OPERATION_COMPLETED OP-once")
        control("and the effect did not run a second time", json.dumps(twice), '["ran"]')
        control("and it is completed ONLY: its planned row is not also read as unreconciled",
                json.dumps("JOURNAL_OPERATION_UNRECONCILED" in said_completed), "false")
        pending_path = root / "state" / "pending.jsonl"
        plan_pending = fx_plan(operation_id="OP-pending")
        append(pending_path, plan_pending, root=str(root))
        retried = []
        said_unreconciled = refusal(lambda: journalled(pending_path, plan_pending, str(root),
                                                       lambda: retried.append("ran") or "x"))
        control("an UNRECONCILED operation is a retry, and a retry belongs to recovery",
                said_unreconciled, "JOURNAL_OPERATION_UNRECONCILED OP-pending")
        control("and the callback is not called: whether the effect happened is what the journal "
                "cannot say", json.dumps(retried), "[]")
        conflicting = []
        said_conflicting = refusal(lambda: journalled(
            pending_path, fx_plan(operation_id="OP-pending", target="claude/guides/other.md"),
            str(root), lambda: conflicting.append("ran") or "x"))
        control("a CONFLICTING plan under the same id is its own refusal, naming both digests",
                said_conflicting, "JOURNAL_OPERATION_CONFLICTING OP-pending")
        clean("and that callback does not run either", conflicting)
        control("the identity is the whole plan, so the same id with another target is another "
                "operation",
                "differs" if plan_digest(fx_plan(operation_id="OP-x")) !=
                plan_digest(fx_plan(operation_id="OP-x", target="claude/guides/z.md"))
                else "the same digest for two plans", "differs")
        control("and the kind is not part of it, so a plan and its done record speak of one "
                "operation",
                "equal" if plan_digest({**fx_plan(operation_id="OP-y"), "kind": "done"}) ==
                plan_digest(fx_plan(operation_id="OP-y")) else "the kind changed the identity",
                "equal")

        # ---- corruption stops everything ---------------------------------------------------------
        #
        # `append` checked the torn TAIL and ignored `read`'s problems, so a journal already reported
        # as damaged in the middle took a new plan and ran an effect.
        corrupt_path = root / "state" / "corrupt.jsonl"
        append(corrupt_path, fx_plan(operation_id="OP-c1"), root=str(root))
        append(corrupt_path, fx_plan(operation_id="OP-c2"), root=str(root))
        held_lines = corrupt_path.read_bytes().split(b"\n")
        held_lines[0] = b"9999 " + b"0" * 64 + b" {\"kind\": \"planned\"}"
        corrupt_path.write_bytes(b"\n".join(held_lines))
        control("a complete line whose frame does not verify is corruption, and `read` says so",
                "; ".join(read(corrupt_path)["problems"]), "JOURNAL_TORN_MIDDLE")
        control("an append over it is refused by name rather than adding to it",
                refusal(lambda: append(corrupt_path, fx_plan(operation_id="OP-c3"),
                                       root=str(root))),
                "JOURNAL_CORRUPT")
        over_corruption = []
        control("and so is an effect",
                refusal(lambda: journalled(corrupt_path, fx_plan(operation_id="OP-c4"), str(root),
                                           lambda: over_corruption.append("ran") or "x")),
                "JOURNAL_CORRUPT")
        clean("which did not run", over_corruption)
        control("the refusal says that tail repair does not touch it, because the two recoveries "
                "are different decisions",
                refusal(lambda: append(corrupt_path, fx_plan(operation_id="OP-c5"),
                                       root=str(root))),
                "tail repair does not touch it")
        clean("and reconciliation leaves a corrupt middle alone: its tail is complete",
              [] if reconcile_tail(corrupt_path, str(root))["dropped"] is None
              else ["a complete line was cut"])

        # ---- a COMPLETE line that frames nowhere -------------------------------------------------
        #
        # An append is interrupted before its newline, so the only line a tear explains is a LAST
        # line with no newline. A complete last line that framed nowhere went into `torn` with no
        # problem at all, so append and journalled ran over it: the journal said "a tear, nothing to
        # report" about bytes no append could have produced (the round-3 review).
        final_path = root / "state" / "final.jsonl"
        append(final_path, fx_plan(operation_id="OP-final"), root=str(root))
        with open(final_path, "ab") as handle:
            handle.write(b"9999 " + b"0" * 64 + b' {"kind": "planned"}\n')
        held_final = read(final_path)
        control("a complete last line whose frame does not verify is corruption, and `read` names "
                "it", "; ".join(held_final["problems"]), "JOURNAL_CORRUPT_LINE line 2")
        control("and the refusal says no interrupted append explains it",
                "; ".join(held_final["problems"]), "no interrupted append explains it")
        control("an append over it is refused rather than added to",
                refusal(lambda: append(final_path, fx_plan(operation_id="OP-f2"), root=str(root))),
                "JOURNAL_CORRUPT")
        over_final = []
        control("and so is an effect",
                refusal(lambda: journalled(final_path, fx_plan(operation_id="OP-f3"), str(root),
                                           lambda: over_final.append("ran") or "x")),
                "JOURNAL_CORRUPT")
        clean("which did not run", over_final)
        clean("and tail repair leaves it alone, because its newline is there",
              [] if reconcile_tail(final_path, str(root))["dropped"] is None
              else ["a complete line was cut"])
        # While an UNTERMINATED last line is still a tear, which is the case the rule must keep:
        # the two differ by the newline and by nothing else.
        tear_path = root / "state" / "tear.jsonl"
        append(tear_path, fx_plan(operation_id="OP-tear"), root=str(root))
        with open(tear_path, "ab") as handle:
            handle.write(b"an interrupted append")
        clean("an unterminated last line is a tear and carries no corruption problem",
              read(tear_path)["problems"])
        control("and tail repair removes exactly it", reconcile_tail(tear_path, str(root))["dropped"],
                "an interrupted append")

        # The WHOLE post-append parse, before the effect. `journalled` searched the post-append
        # parse for its own plan and never read that parse's problems, so a journal this very
        # append left unparseable still carried an effect.
        class CorruptingStorage(Storage):
            """A storage whose append also writes a complete line that frames nowhere."""

            def append(self, confined, pieces, data):
                Storage.append(self, confined, pieces, data)
                Storage.append(self, confined, pieces,
                               b"9999 " + b"0" * 64 + b' {"kind": "planned"}\n')

        after_effect = []
        control("an append that leaves the journal unparseable is refused BEFORE the effect, not "
                "after it",
                refusal(lambda: journalled(root / "state" / "after.jsonl",
                                           fx_plan(operation_id="OP-after"), str(root),
                                           lambda: after_effect.append("ran") or "x",
                                           storage=CorruptingStorage())),
                "the journal does not parse after the append")
        clean("and the effect did not run", after_effect)

        # ---- a new journal's own NAME ------------------------------------------------------------
        #
        # The fake modelled contents and created directories, never the journal file's own entry, so
        # a new journal under an EXISTING directory could not be shown to disappear at all.
        (root / "state" / "existing").mkdir(parents=True, exist_ok=True)
        named_path = root / "state" / "existing" / "named.jsonl"
        losing_names = LosingStorage(lose_names=True)
        append(named_path, fx_plan(operation_id="OP-name"), root=str(root), storage=losing_names)
        control("the file is there after a file-only sync, with its record",
                str(len(read(named_path)["records"])), "1")
        held_names = losing_names.lose_unsynced()
        control("and losing the directory entry takes the file, name and all, although its contents "
                "were fsynced", json.dumps({"files": held_names["files"],
                                            "exists": named_path.exists()}),
                '{"files": 1, "exists": false}')
        survivor = root / "state" / "existing" / "survivor.jsonl"
        surviving = LosingStorage()
        append(survivor, fx_plan(operation_id="OP-survive"), root=str(root), storage=surviving)
        # The loss is ACTUALLY TAKEN here. The control used to read the journal without calling
        # `lose_unsynced`, so it asserted that a file written a moment ago is readable — true of any
        # write at all, and nothing about durability (the round-3 review).
        held_loss = surviving.lose_unsynced()
        control("while the same append with the directory synced survives the loss, which this "
                "control now actually takes",
                json.dumps({"records": len(read(survivor)["records"]),
                            "lost": sorted((k, v) for k, v in held_loss.items()
                                           if k != "contents")}),
                '{"records": 1, "lost": [["directories", 0], ["files", 0]]}')
        control("and the directory that was synced is not in what the fake would lose, so the fake "
                "models the device rather than its own bookkeeping",
                json.dumps([str(p) for p in surviving.unsynced_directories]), "[]")

        # ---- failing closed on what the platform will not give -----------------------------------
        class NoDirSync(Storage):
            """A filesystem that refuses to fsync a directory, which is a real configuration."""

            def _dir_sync_call(self, held_fd):
                raise OSError(errno.EINVAL, "Invalid argument")

        control("a filesystem that will not fsync a directory is refused by name, because a new "
                "journal's own name cannot be made durable there",
                refusal(lambda: append(root / "state" / "nodir.jsonl", fx_plan(),
                                       root=str(root), storage=NoDirSync())),
                "JOURNAL_DIRECTORY_SYNC_UNSUPPORTED")
        control("and the refusal says no durability is claimed there",
                refusal(lambda: append(root / "state" / "nodir2.jsonl", fx_plan(),
                                       root=str(root), storage=NoDirSync())),
                "no durability is claimed")
        # A symlink in the MIDDLE of the journal's own path, built under this control's temp tree.
        (root / "state" / "real").mkdir(parents=True, exist_ok=True)
        os.symlink(root / "state" / "real", root / "state" / "via-link")
        control("a symlinked component in the middle of the journal's path is refused, which "
                "O_NOFOLLOW on the leaf cannot catch",
                refusal(lambda: append(root / "state" / "via-link" / "j.jsonl", fx_plan(),
                                       root=str(root))),
                "JOURNAL_SYMLINK_COMPONENT")
        clean("and nothing was written through it",
              [] if not (root / "state" / "real" / "j.jsonl").exists()
              else ["the append followed the symlink"])

        control("the document says how a line is framed, so a reader can check one by hand",
                document()["framing"], "sha256 of the payload")
    finally:
        shutil.rmtree(held_tree, ignore_errors=True)

    # This module's only effect is its own append: asserted over its own AST, in both directions.
    import ast
    own = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    spawners = sorted({ast.unparse(node.func) for node in ast.walk(own) if isinstance(node, ast.Call)
                       and ast.unparse(node.func).split(".")[0] == "subprocess"})
    clean("the journal spawns nothing: it is the record of effects, not a taker of them", spawners)
    # An EXACT set, not a containment: `", ".join(writes)` containing "os.write" was satisfied by
    # any list that happened to include it, so every call this module gained was invisible to the
    # assertion. The set is what the rule is about — these are the only ways this module touches a
    # file, and each one is inside `Storage` or `Confined` where the confinement is.
    WRITE_CALLS = ("open", "os.fsync", "os.ftruncate", "os.lstat", "os.mkdir", "os.open", "os.read",
                   "os.replace", "os.stat", "os.unlink", "os.write", "shutil.rmtree")
    writes = sorted({ast.unparse(node.func) for node in ast.walk(own) if isinstance(node, ast.Call)
                     and ast.unparse(node.func) in WRITE_CALLS})
    control("the calls that touch a file are exactly the ones this module declares, so a new one "
            "cannot arrive unnoticed",
            json.dumps(writes),
            json.dumps(["open", "os.fsync", "os.ftruncate", "os.lstat", "os.mkdir", "os.open",
                        "os.read", "os.stat", "os.write", "shutil.rmtree"]))
    # `open` is the suite's own fixture building and `shutil.rmtree` is its teardown; the runtime
    # path uses the fd-based calls alone. Asserted, because "the suite's" is a claim about where a
    # call sits, not about its name.
    runtime_only = sorted({ast.unparse(node.func) for node in ast.walk(
        ast.Module(body=[node for node in own.body
                         if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                                 and node.name in ("self_test", "_self_test_body"))],
                   type_ignores=[]))
        if isinstance(node, ast.Call) and ast.unparse(node.func) in WRITE_CALLS})
    control("and outside the suite every one of them is reached with a `dir_fd` or an open fd — no "
            "path is opened by name there. `open` is the suite's own fixture building, and "
            "`shutil.rmtree` is `LosingStorage`'s modelled loss, which lives in this module because "
            "a fault seam belongs with the thing it tests",
            json.dumps(runtime_only),
            json.dumps(["os.fsync", "os.ftruncate", "os.lstat", "os.mkdir", "os.open", "os.read",
                        "os.stat", "os.write", "shutil.rmtree"]))
    control("and `open` by name is the suite's alone", json.dumps("open" in runtime_only), "false")

    print(f"journal --self-test: {'FAILED' if failures else 'OK'} ({len(ran)} controls: §10.5's "
          f"record fields in both kinds, the frame's length and digest against a truncated and an "
          f"altered payload, a torn tail reported and a torn middle named as corruption, the three "
          f"seams with no process killed, an unsynced write lost by a storage that drops it, and "
          f"what §10.6 reads as pending)")
    for name, detail in failures:
        print(f"journal --self-test [FAIL] {name}: {detail}")
    return 1 if failures else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    print(json.dumps(document(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
