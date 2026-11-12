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
import errno
import hashlib
import json
import os
import pathlib
import shutil
import sys
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


class Storage:
    """The real device: append the bytes, then fsync the file and its directory.

    The directory fsync is what makes a newly created journal file itself durable; without it the
    file's bytes can be on the device while the name is not.
    """

    def _write_once(self, handle, data):
        """One write to the device, as its own named seam.

        A seam rather than a patch: a control that swaps `os.write` out hands an executor's module
        around, which `dispatch.py`'s source-shape rule refuses in a shipped module — rightly, since
        replacing a module is how an effect hides from a scan. Overriding one method needs nothing
        global swapped, and it matches this unit's decision that faults arrive through named seams.
        """
        return os.write(handle, data)

    def append(self, path, data):
        path = pathlib.Path(path)
        # Which ancestors this append CREATES, noted before creating them. `mkdir(parents=True)` can
        # make root/state/nested while only the journal and its immediate parent are fsynced, so a
        # power loss could take the whole chain and the record with it — durable inside a directory
        # entry that never reached the device. Found by the WP-21 review.
        created = []
        held_parent = path.parent
        while not held_parent.exists():
            created.append(held_parent)
            if held_parent.parent == held_parent:
                break
            held_parent = held_parent.parent
        path.parent.mkdir(parents=True, exist_ok=True)
        for made in reversed(created):
            self._created_directory(made)
        _seam("before_write")
        # O_NOFOLLOW: `os.open` follows a symlink, so a journal path that is a link under the
        # declared root appends OUTSIDE it and the containment check cannot see it. The check is
        # lexical and this is the half it cannot answer.
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | _NOFOLLOW
        try:
            handle = os.open(path, flags, 0o600)
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.EMLINK):
                raise Refused(f"JOURNAL_SYMLINK {path}: the journal path is a symlink, so the "
                              f"append would land wherever it points — outside the declared root "
                              f"that a lexical check just approved") from exc
            raise
        try:
            # A SHORT write is not a complete record. `os.write` may write fewer bytes than it was
            # given, and returning then would acknowledge a durable complete record for a line the
            # reader will see as torn. Loop until every byte is written, and fail by name if the
            # device stops accepting them.
            written = 0
            while written < len(data):
                held = self._write_once(handle, data[written:])
                if held <= 0:
                    raise Refused(f"JOURNAL_SHORT_WRITE {path}: the device accepted {written} of "
                                  f"{len(data)} bytes and then none, so the record is incomplete")
                written += held
            _seam("after_write_before_fsync")
            os.fsync(handle)
        finally:
            os.close(handle)
        self._sync_directory(path.parent)
        _seam("after_fsync")

    def _created_directory(self, made):
        """A directory this append CREATED: its entry lives in its parent, so the parent is synced.

        A hook rather than a direct call because what is at risk is the ENTRY, and a storage fake
        has to be able to model the entry's loss instead of the sync's absence. `LosingStorage`
        overrides this one and `_sync_directory` both.
        """
        self._sync_directory(made.parent)

    def _sync_directory(self, directory_path):
        """fsync one directory, so the names it holds reach the device.

        Its own method because the creation chain needs the same operation: a storage fake that
        models file contents but not directory ENTRIES cannot show the loss this closes, which is
        why `LosingStorage` overrides it too.
        """
        directory = os.open(directory_path, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


class LosingStorage(Storage):
    """A storage that keeps unsynced writes in memory and loses them on demand.

    The only honest way to exercise §10.5's "no effect precedes a successful fsync": a killed process
    does NOT lose an unsynced write on a real filesystem, so a control built on a crash would be
    asserting something the platform does not do. `lose_unsynced()` is the storage failure.
    """

    def __init__(self):
        self.unsynced = []
        self.unsynced_directories = []

    def _created_directory(self, made):
        """A directory ENTRY that has not reached the device yet.

        Contents and entries are lost separately on a real filesystem, and a fake that models only
        contents cannot show the second loss at all — which is why the ancestor defect survived a
        suite that had a storage fake in it. An entry that never landed takes everything under it
        with it, because nothing can reach what has no name.
        """
        self.unsynced_directories.append(pathlib.Path(made))

    def _sync_directory(self, directory_path):
        """Nothing: this storage syncs nothing until `lose_unsynced` decides."""

    def append(self, path, data):
        path = pathlib.Path(path)
        created = []
        held_parent = path.parent
        while not held_parent.exists():
            created.append(held_parent)
            if held_parent.parent == held_parent:
                break
            held_parent = held_parent.parent
        path.parent.mkdir(parents=True, exist_ok=True)
        for made in reversed(created):
            self._created_directory(made)
        _seam("before_write")
        self.unsynced.append((path, data))
        _seam("after_write_before_fsync")
        for held_path, held_data in self.unsynced:
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | _NOFOLLOW
            handle = os.open(held_path, flags, 0o600)
            try:
                written = 0
                while written < len(held_data):
                    held = os.write(handle, held_data[written:])
                    if held <= 0:
                        raise Refused(f"JOURNAL_SHORT_WRITE {held_path}: the device accepted "
                                      f"{written} of {len(held_data)} bytes and then none")
                    written += held
                os.fsync(handle)
            finally:
                os.close(handle)
        self.unsynced = []
        _seam("after_fsync")

    def lose_unsynced(self):
        """Discard every write and every directory entry that has not been fsynced.

        Returns `{contents, directories}`: a real filesystem loses the two separately, and the
        caller that only ever counted contents could not see a journal whose own directory entry
        never landed.
        """
        held = len(self.unsynced)
        directories = [p for p in self.unsynced_directories if p.exists()]
        self.unsynced = []
        self.unsynced_directories = []
        # The entries are removed from the LAST created downwards, so the tree is taken apart in
        # the order a device that never got them would have left it.
        lost_directories = 0
        for directory in sorted({str(p) for p in directories}, key=len, reverse=True):
            held_path = pathlib.Path(directory)
            if not held_path.is_dir():
                continue
            shutil.rmtree(held_path, ignore_errors=True)
            lost_directories += 1
        return {"contents": held, "directories": lost_directories}


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
                           if unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp")})
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


def append(path, record, root, storage=None):
    """Append one record, durably, and return it. Refuses before writing anything.

    `root` is the journal's declared root (`run.json.destinations.runtime_state`): a journal written
    outside it is the hole `destinations.py` exists to close, and the question is asked through that
    module so one answer serves both.
    """
    path = pathlib.Path(path)
    if not root or not destinations.inside(path, root):
        raise Refused(f"JOURNAL_OUTSIDE_ROOT {path}: not inside the declared runtime_state root "
                      f"{root!r}")
    problems = record_problems(record)
    if problems:
        raise Refused("; ".join(problems))
    # An unterminated tail is reconciled before anything is added to it. Appending blindly put the
    # new frame on the same line as the torn one, and recovery then read ONE unframed line where two
    # records had been written — the second was durable and invisible. §10.6 expects a torn tail; it
    # does not expect the next append to bury it.
    held = read(path)
    if held["torn"] and held.get("unterminated"):
        raise Refused(f"JOURNAL_TAIL_UNRECONCILED {path}: the last line carries no newline, so an "
                      f"append would put two records on one line. Reconcile the tail "
                      f"(`reconcile_tail`) before adding to this journal")
    (storage or Storage()).append(path, frame(record))
    return record


def journalled(path, record, root, effect, storage=None):
    """Append the plan, then take the effect, then append the done record. Returns both records.

    The API a future effect loop calls, and the reason it exists: §10.5's ordering is "no effect
    precedes a successful fsync", and nothing in this module could show that an effect WAITED,
    because the only ordering control appended a record and then looked at the journal. It invoked
    no effect, created no target and held no before-state, so it would have passed over a loop that
    took the effect first. The WP-21 review named it.

    `effect` is called with no arguments and its return value is carried into the done record's
    `result`. It is called exactly once, after the plan record is durable, and not at all when the
    append refuses or the storage loses the write.
    """
    storage = storage or Storage()
    plan = append(path, record, root, storage=storage)
    # Durable only if the journal now actually holds it: a storage that lost the unsynced write has
    # told us nothing was written, and the effect must not run.
    held = read(path)
    if not any(row.get("operation_id") == record.get("operation_id")
               and row.get("kind") == "planned" for row in held["records"]):
        raise Refused(f"JOURNAL_PLAN_NOT_DURABLE {path}: the plan record for "
                      f"{record.get('operation_id')!r} is not in the journal after the append, so "
                      f"the effect is not taken")
    result = effect()
    finished = done(record["operation_id"], record["target"], record["before_sha256"],
                    record["after_sha256"], record["item_id"], record["approval_id"],
                    commit=result if isinstance(result, str) else None)
    append(path, finished, root, storage=storage)
    return {"planned": plan, "done": finished, "result": result}


def reconcile_tail(path, root):
    """Truncate an unterminated tail so appending is safe again, and say what was dropped.

    The tail is returned rather than silently discarded: an interrupted append is a record somebody
    may want to look at, and recovery (§10.6) is the reader that decides. Only a tail with no
    newline is removed — a complete line whose frame does not verify is corruption, not an
    interrupted write, and this does not touch it.
    """
    path = pathlib.Path(path)
    if not root or not destinations.inside(path, root):
        raise Refused(f"JOURNAL_OUTSIDE_ROOT {path}: not inside the declared runtime_state root "
                      f"{root!r}")
    if not path.is_file():
        return {"dropped": None}
    blob = path.read_bytes()
    if not blob or blob.endswith(b"\n"):
        return {"dropped": None}
    cut = blob.rfind(b"\n") + 1
    dropped = blob[cut:]
    with open(path, "r+b") as handle:
        handle.truncate(cut)
        handle.flush()
        os.fsync(handle.fileno())
    Storage()._sync_directory(path.parent)
    return {"dropped": dropped.decode("utf-8", errors="replace")}


def read(path):
    """`{records, torn, problems}` — the journal as a reader may trust it.

    A torn line is returned rather than raised: at the tail it is an interrupted append, which §10.6
    expects. One anywhere else is corruption and is named as a problem, because an append cannot tear
    a line that already has a line after it.
    """
    path = pathlib.Path(path)
    if not path.is_file():
        return {"records": [], "torn": [], "problems": [], "unterminated": False}
    # Split on the protocol's LITERAL LF, over BYTES, and keep whether the last line carried its
    # delimiter. `str.splitlines()` did both jobs wrongly: it splits on U+2028, U+2029, U+0085 and
    # more, so a payload containing any of them — `frame` writes with ensure_ascii=False, so it can
    # — came back as two torn lines and the record read as corruption; and it discards delimiter
    # information, so a COMPLETE frame whose final LF never reached the device read as a finished
    # record, and the next append then put two records on one line and lost one of them from
    # recovery. Both were found by the WP-21 review.
    blob = path.read_bytes()
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
            if not last:
                problems.append(f"JOURNAL_TORN_MIDDLE line {number}: a line with lines after it "
                                f"cannot have been torn by an append, so this is corruption")
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

        control("a journal with no declared root at all is refused, not defaulted",
                refusal(lambda: append(path, fx_plan(), root=None)), "JOURNAL_OUTSIDE_ROOT")
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
            for mark in ("self._write_once(handle,", "os.fsync(handle)",
                         "self._sync_directory(path.parent)"):
                if held_line.startswith(mark) or held_line.startswith("held = " + mark):
                    steps.append(mark.rstrip("(,"))
        control("the real storage writes, then fsyncs the file, then fsyncs its directory, in that "
                "order", " -> ".join(steps), "self._write_once(handle -> os.fsync(handle) -> "
                "self._sync_directory(path.parent)")
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
            """A real storage that records which directories it synced."""

            def __init__(self):
                self.synced = []

            def _sync_directory(self, directory_path):
                self.synced.append(str(directory_path))
                Storage._sync_directory(self, directory_path)

        counting = CountingStorage()
        deep_path = root / "state" / "a" / "b" / "c" / "deep.jsonl"
        append(deep_path, fx_plan(), root=str(root), storage=counting)
        control("every directory the append created is synced, not only the journal's own parent",
                json.dumps(sorted(set(counting.synced))),
                json.dumps(sorted({str(root / "state"), str(root / "state" / "a"),
                                   str(root / "state" / "a" / "b"),
                                   str(root / "state" / "a" / "b" / "c")})))
        control("and the record is readable afterwards",
                str(len(read(deep_path)["records"])), "1")
        losing_dirs = LosingStorage()
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
        control("so the journal reads plan then done, in that order",
                ",".join(row["kind"] for row in read(order_path)["records"]), "planned,done")
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

            def append(self, path, data):
                pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)

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
    writes = sorted({ast.unparse(node.func) for node in ast.walk(own) if isinstance(node, ast.Call)
                     and ast.unparse(node.func) in ("os.write", "os.open", "open", "os.fsync",
                                                    "os.replace", "shutil.rmtree")})
    control("and every write it makes goes through the storage it was handed",
            ", ".join(writes), "os.write")

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
