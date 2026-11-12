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
import hashlib
import json
import os
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import destinations  # noqa: E402
from runlib.records import Refused  # noqa: E402

# §10.5's own four, and the three the plan adds. Held against the design sentence below by
# `fidelity_problems`, which is done-when 12's "the journal record's required set equals §10.5's".
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

    def append(self, path, data):
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _seam("before_write")
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(handle, data)
            _seam("after_write_before_fsync")
            os.fsync(handle)
        finally:
            os.close(handle)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        _seam("after_fsync")


class LosingStorage(Storage):
    """A storage that keeps unsynced writes in memory and loses them on demand.

    The only honest way to exercise §10.5's "no effect precedes a successful fsync": a killed process
    does NOT lose an unsynced write on a real filesystem, so a control built on a crash would be
    asserting something the platform does not do. `lose_unsynced()` is the storage failure.
    """

    def __init__(self):
        self.unsynced = []

    def append(self, path, data):
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _seam("before_write")
        self.unsynced.append((path, data))
        _seam("after_write_before_fsync")
        for held_path, held_data in self.unsynced:
            with open(held_path, "ab") as handle:
                handle.write(held_data)
                handle.flush()
                os.fsync(handle.fileno())
        self.unsynced = []
        _seam("after_fsync")

    def lose_unsynced(self):
        """Discard every write that has not been fsynced. Returns how many were lost."""
        held = len(self.unsynced)
        self.unsynced = []
        return held


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
    for field in ("operation_id", "target", "item_id"):
        value = record.get(field)
        if field in record and (not isinstance(value, str) or not value):
            problems.append(f"JOURNAL_VALUE {kind}.{field}: a non-empty string, not {value!r}")
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
    (storage or Storage()).append(path, frame(record))
    return record


def read(path):
    """`{records, torn, problems}` — the journal as a reader may trust it.

    A torn line is returned rather than raised: at the tail it is an interrupted append, which §10.6
    expects. One anywhere else is corruption and is named as a problem, because an append cannot tear
    a line that already has a line after it.
    """
    path = pathlib.Path(path)
    if not path.is_file():
        return {"records": [], "torn": [], "problems": []}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    records, torn, problems = [], [], []
    for number, line in enumerate(lines, start=1):
        held = _unframe(line)
        if held is None:
            torn.append({"line": number, "text": line[:120]})
            if number != len(lines):
                problems.append(f"JOURNAL_TORN_MIDDLE line {number}: a line with lines after it "
                                f"cannot have been torn by an append, so this is corruption")
            continue
        records.append(held)
    return {"records": records, "torn": torn, "problems": problems}


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
        steps = [line.strip() for line in storage_src.splitlines()
                 if line.strip() in ("os.write(handle, data)", "os.fsync(handle)",
                                     "os.fsync(directory)")]
        control("the real storage writes, then fsyncs the file, then fsyncs its directory, in that "
                "order", " -> ".join(steps),
                "os.write(handle, data) -> os.fsync(handle) -> os.fsync(directory)")
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
                f'{losing.lose_unsynced()}:{len(read(lost_path)["records"])}', "1:0")
        clean("which is the state §10.5 requires: the caller had not been told the record was "
              "durable, so it had not taken its effect",
              [] if not lost_path.exists() or not read(lost_path)["records"] else ["the record survived"])
        kept = LosingStorage()
        keep_path = root / "state" / "kept.jsonl"
        append(keep_path, fx_plan(), root=str(root), storage=kept)
        control("while a completed append is synced, so losing nothing loses nothing",
                f'{kept.lose_unsynced()}:{len(read(keep_path)["records"])}', "0:1")

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
