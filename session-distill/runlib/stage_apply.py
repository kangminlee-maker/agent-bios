#!/usr/bin/env python3
"""S11 apply, release 1: the confirmed final set written into files of the declared checkout.

The owner decided the release-1 form on 2026-11-13 (D-20261113-f22b7d): S11 writes the approved
changes into files of the declared checkout and NOTHING else. It starts no process — no git, no
installer, no hook — and writes no personal layer and no state root. Its other writes are inside the
run directory: the plan, the write-ahead journal and its own record. It ends by naming the two
commands the owner runs, the commit and the install, and runs neither.

What an operation does to a file's text is `runlib/operations.py`'s contract; this module decides
when it is allowed to happen and makes it happen on disk. The stage has two parts, each its own
admission (`records.run_stage`), so the plan the effects are taken from is a RECORDED output and not
a file the effects part trusts because it is there:

**plan** — refusing before anything is written:
1. the confirmation binds: the manifest S10b recorded is on disk unchanged and the final set built
   again from the run's records is that manifest (`stage_confirm.binding_problems`);
2. every path any operation touches passes the target contract (`targets.set_problems`), no two
   paths spell one directory or file differently, and an operation that ADDS to the always-loaded
   file has S7b's faithful-merge judgment (`drift.global_op_problems`);
3. every operation is applied in the confirmed order to the files as they are NOW, in memory
   (`operations.plan_of`). Each operation's `before_state_sha256` — the state S7 read when the
   proposal was written — must be the file's state now, so a file that moved since is refused, not
   patched. `apply/plan.json` is written once, as this part's output.

**effects** — `apply/plan.json` is an input the shared record check holds to the plan part's
recorded hash, so an edited plan is refused before it is read; its bytes are then read once and
must be the bytes admission pinned. Then, before any write: the binding again; every effect of the
plan held to the confirmed set (its item, its approval, its operation, a path that operation names,
its operation id recomputed, its bytes at their own hash, and each file's effects chained); the
journal read whole and refused if it does not parse, holds a record the plan does not, or holds a
history other than planned-then-done in the plan's order; and the plan held WHOLE - before any
effect, the confirmed operations planned again over the files must give this plan byte for byte,
and after one, the plan must be the very one the journal's effects were taken from. Then one file
at a time through `journal.journalled`, the journal's lock held from the plan record to the done
record:

- the declaration's lock is held around each effect and the declaration read again under it: it
  must be the one this part was admitted under, and an amendment cannot land during a write. It
  is held once more before the stage says it is complete;
- the file is reached by a confined walk from the checkout's own descriptor (`journal.Confined`):
  no symlink in the chain, every component spelled as the directory holds it, the leaf a regular
  file with one name, opened without blocking;
- the new bytes are written to a temporary beside the target and synced FIRST; only then is the
  target's state read through its descriptor and held to the plan's before-state, the staged file
  read back through the descriptor that wrote it (regular, one name, the planned bytes, still what
  its name holds), and the rename made; then the name is checked to hold
  that same file, the directories are synced, and the after-state is read back before the done
  record.

What stays open, stated as it is: POSIX has no compare-and-rename, and no check is one instant.
The target's bytes, its name's identity, and the staged file's bytes, metadata and name are each
read by a separate call, and the rename is one more. A writer acting between two of those calls can
still have the target overwritten, or bytes installed that the plan did not hold; what the checks
bound is that such a writer must act inside that sequence of calls, after the target was read whole
and the staged file was read back standing still. An installed file that is not the plan's is
detected and reported (`APPLY_AFTER_MISMATCH`), never hidden. This stage is safe against accident
and against a second run of itself; it is not a defence against a concurrent adversary writing the
checkout, and nothing else should be writing the checkout while it runs.

What this stage trusts: the run directory against accident and against a second caller, not against
a writer who can rewrite the run's own records, approvals and confirmation together - that writer
is the owner. One S11 call runs at a time (`APPLY_LOCK`).

A re-run skips what the journal says is done. An operation the journal holds as planned with no
done record is not run again: the stage says whether the file is at its before-state, its
after-state or neither, and stops (`APPLY_UNRECONCILED`). The checkout is a git repository the owner
controls, so the way back is theirs: inspect, restore the file, and apply in a new run.

    stage_apply.py --self-test
"""
import base64
import errno
import hashlib
import json
import os
import pathlib
import stat
import sys
import unicodedata

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runlib import (drift, journal, operations, records, stage_approvals, stage_confirm,  # noqa: E402
                    stagelock, targets)
from runlib.operations import ABSENT, sha_of, split_target  # noqa: E402
from runlib.records import Refused  # noqa: E402

STAGE = "S11"
PLAN_PART, EFFECTS_PART = "plan", "effects"
OUTPUT = "apply.json"
PLAN = "apply/plan.json"
JOURNAL = "apply/journal.jsonl"
_NOFOLLOW = journal._NOFOLLOW   # one answer for the walk and the leaf: the journal's own
plan_of = operations.plan_of


def operation_id(confirmation_id, effect, ordinal):
    held = json.dumps([confirmation_id, effect["item_id"], effect["operation"], effect["path"], ordinal,
                       effect["before"], effect["after"]])
    return "A-" + hashlib.sha256(held.encode("utf-8")).hexdigest()[:24]


def spelling_problems(paths, folds):
    """Two planned paths that spell one directory or file in two CASES, by name, where that is one name.

    Each path alone can pass the target contract while its directory does not exist yet; written one
    after the other on a filesystem that folds case, the second lands in the first's directory under
    a name the plan never held. Whether two cases are one name is the filesystem's to say
    (`targets.folds_case`): True refuses, False allows - they are two directories - and None, a
    filesystem that did not say, refuses rather than guesses, as `targets.collision_problems` does.
    Canonically equivalent spellings are one name already (`targets.identity` is NFC), so only a case
    difference is asked about."""
    if folds is False:
        return []
    seen, pairs = {}, []
    for path in paths:
        pieces = [p for p in unicodedata.normalize("NFC", str(path)).split("/") if p]
        for depth in range(1, len(pieces) + 1):
            spelled = "/".join(pieces[:depth])
            other = seen.setdefault(spelled.casefold(), spelled)
            if other != spelled and (other, spelled) not in pairs:
                pairs.append((other, spelled))
    code = "APPLY_SPELLING_CONFLICT" if folds else "APPLY_SPELLING_UNDECIDED"
    why = ("this filesystem folds case, so both would be written under one name" if folds else
           "whether this filesystem folds case could not be established, so the set is refused rather than applied")
    return [f"{code} {a} and {b}: two planned paths spell one name in two cases; {why}" for a, b in pairs]


# ---- the files of the checkout -----------------------------------------------------------------------

class Checkout:
    """The declared checkout opened once; every file under it reached by a confined walk."""

    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.confined = journal.Confined(str(self.root))

    def close(self):
        self.confined.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False

    def _pieces(self, path):
        return self.confined.parts(self.root / path)

    @staticmethod
    def _close(fds):
        for held in fds[1:]:
            try:
                os.close(held)
            except OSError:
                pass

    @staticmethod
    def _open(parent, leaf, path):
        """The leaf's descriptor, or None when it is absent: never through a link, never blocking, and
        only a regular file with one name."""
        try:
            handle = os.open(leaf, os.O_RDONLY | _NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return None
            raise Refused(f"APPLY_TARGET_UNOPENABLE {path}: {exc.strerror} - a target is a regular file "
                          f"and never a link") from exc
        try:
            held = os.fstat(handle)
            if not stat.S_ISREG(held.st_mode):
                raise Refused(f"APPLY_TARGET_NOT_FILE {path}: a target is a regular file")
            if held.st_nlink != 1:
                raise Refused(f"APPLY_TARGET_HARD_LINKED {path}: it has {held.st_nlink} names, and a write "
                              f"through one would change a file the checkout does not name")
        except BaseException:
            os.close(handle)
            raise
        return handle

    @staticmethod
    def _bytes(handle):
        out = b""
        while True:
            chunk = os.read(handle, 1 << 20)
            if not chunk:
                return out
            out += chunk

    def _state(self, parent, leaf, path):
        """`(sha | "absent", mode | None, (device, inode) | None)` of the leaf, through its descriptor."""
        handle = self._open(parent, leaf, path)
        if handle is None:
            return ABSENT, None, None
        try:
            held = os.fstat(handle)
            return hashlib.sha256(self._bytes(handle)).hexdigest(), stat.S_IMODE(held.st_mode), (held.st_dev,
                                                                                               held.st_ino)
        finally:
            os.close(handle)

    @staticmethod
    def _spelled(fds, pieces, path):
        """Every component the walk reached is spelled as its directory holds it. `open` on a filesystem
        that folds case answers for `upper/` with `Upper/`, and the file then lands under a name the
        plan never held."""
        for parent, piece in zip(fds, pieces):
            # the target contract's own comparison, so the plan and the write agree on what one name is:
            # a canonically equivalent entry is the name, a case difference is another
            found = targets._spelling_on_disk([piece], parent, path)
            if found:
                raise Refused(f"APPLY_SPELLING_ON_DISK {path}: " + "; ".join(found))

    def read(self, path):
        """The file's bytes, or None when it is absent (the plan's reader)."""
        pieces = self._pieces(path)
        fds, leaf, _made = self.confined.walk(pieces, missing_ok=True)
        if fds is None:
            return None
        try:
            self._spelled(fds, pieces, path)
            handle = self._open(fds[-1], leaf, path)
            if handle is None:
                return None
            try:
                return self._bytes(handle)
            finally:
                os.close(handle)
        finally:
            self._close(fds)

    def state(self, path):
        fds, leaf, _made = self.confined.walk(self._pieces(path), missing_ok=True)
        if fds is None:
            return ABSENT
        try:
            return self._state(fds[-1], leaf, path)[0]
        finally:
            self._close(fds)

    @staticmethod
    def _named(parent, name):
        """`(device, inode)` of what `name` is in `parent` now, a regular file with one name, or None."""
        try:
            held = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return None
        return (held.st_dev, held.st_ino) if stat.S_ISREG(held.st_mode) and held.st_nlink == 1 else None

    def take(self, effect):
        """One effect on disk. The new bytes are staged and synced first; the target is then held to
        the plan's before-state and the staged name to the staged file, the rename is made, and what
        the name holds is read back. Raises Refused, with the done record unwritten, on any
        difference."""
        path, data = effect["path"], effect["data"]
        pieces = self._pieces(path)
        # directories are made only for a file that is not there yet: replacing one never needs a new directory,
        # and a refused replacement must not leave one behind (the S12 review, round 2)
        fds, leaf, _made = self.confined.walk(pieces, create=data is not None and effect["before"] == ABSENT)
        try:
            parent = fds[-1]
            self._spelled(fds, pieces, path)

            def held_to_before():
                now, mode, where = self._state(parent, leaf, path)
                if now != effect["before"]:
                    raise Refused(f"APPLY_BEFORE_MISMATCH {path}: it is {now[:12]} at the write, and the plan "
                                  f"holds {effect['before'][:12]}")
                # ... and the NAME still holds the file that was read: a file put under the name while the old
                # one was being read is not the one the plan's before-state describes
                if self._named(parent, leaf) != where:
                    raise Refused(f"APPLY_BEFORE_MISMATCH {path}: the name was given to another file while the "
                                  f"one the plan holds was being read")
                return mode

            if data is None:
                held_to_before()
                os.unlink(leaf, dir_fd=parent)
            else:
                mode = held_to_before()             # an early answer; the binding one follows the staging
                temp = f".{leaf}.s11-{os.urandom(8).hex()}.tmp"
                handle = os.open(temp, os.O_RDWR | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
                                 0o644 if mode is None else mode, dir_fd=parent)
                try:
                    try:
                        view = memoryview(data)
                        while view:
                            view = view[os.write(handle, view):]
                        os.fsync(handle)
                        held_to_before()            # the target, immediately before the rename
                        # ... and the staged file, through the descriptor that wrote it: still a regular file
                        # with one name, still holding the planned bytes, and still what its name holds. A
                        # writer that changed it in place, or gave its name to another file, installs nothing.
                        staged = os.fstat(handle)
                        there = hashlib.sha256()
                        offset = 0
                        while True:
                            chunk = os.pread(handle, 1 << 20, offset)
                            if not chunk:
                                break
                            there.update(chunk)
                            offset += len(chunk)
                        after_scan = os.fstat(handle)       # the scan itself must have read a file standing still
                        still = (staged.st_size, staged.st_mtime_ns, staged.st_ctime_ns) == (
                            after_scan.st_size, after_scan.st_mtime_ns, after_scan.st_ctime_ns)
                        if (not stat.S_ISREG(staged.st_mode) or staged.st_nlink != 1 or not still
                                or there.hexdigest() != effect["after"]
                                or self._named(parent, temp) != (staged.st_dev, staged.st_ino)):
                            raise Refused(f"APPLY_STAGING_MOVED {path}: the temporary no longer holds the planned "
                                          f"bytes under its own name, so nothing is installed")
                        staged = (staged.st_dev, staged.st_ino)
                        os.replace(temp, leaf, src_dir_fd=parent, dst_dir_fd=parent)
                    finally:
                        os.close(handle)
                except BaseException:
                    try:
                        os.unlink(temp, dir_fd=parent)
                    except OSError:
                        pass
                    raise
                if self._named(parent, leaf) != staged:
                    raise Refused(f"APPLY_AFTER_MISMATCH {path}: the name does not hold the file that was "
                                  f"staged for it")
            for held in reversed(fds):          # the entry, and any directory this walk made
                os.fsync(held)
            after = self._state(parent, leaf, path)[0]
            if after != effect["after"]:
                raise Refused(f"APPLY_AFTER_MISMATCH {path}: it is {after[:12]} after the write, and the "
                              f"plan holds {effect['after'][:12]}")
        finally:
            self._close(fds)


# ---- the stage ---------------------------------------------------------------------------------------

def inputs_of(run_dir, version):
    return stage_confirm.inputs_of(run_dir) + [
        {"artifact": stage_confirm.CONFIRMATION, "producer_stage": "S10b"},
        {"artifact": stage_confirm.manifest_rel(version), "producer_stage": "S10b"}]


def items_of(manifest, current, approvals):
    """The confirmed items in the confirmed order, each with its approval and its WHOLE operations
    (the manifest's F carries type, target and before-state only)."""
    rows = {r["item_id"]: r for r in current["rows"]}
    last = {}
    for row in approvals:
        last[row["item_id"]] = row
    in_f = [i["item_id"] for i in manifest["F"]]
    order = list(manifest["sequencing"].get("order") or [])
    if in_f and manifest["sequencing"].get("sequenced") is not True:
        raise Refused(f"APPLY_UNSEQUENCED S11: the confirmed set holds {len(in_f)} items and no order "
                      f"({manifest['sequencing'].get('reason')})")
    if sorted(order) != sorted(in_f):
        raise Refused("APPLY_ORDER_INCOMPLETE S11: the confirmed order does not hold exactly the items of F")
    items = []
    for item_id in order:
        approval = last.get(item_id) or {}
        if approval.get("approval_id") not in manifest["approval_ids"]:
            raise Refused(f"APPROVAL_UNBOUND {item_id}: its last approval is not one the confirmation binds")
        items.append({"item_id": item_id, "approval_id": approval["approval_id"],
                      "operations": list((rows[item_id].get("proposal") or {}).get("operations") or [])})
    return items


def paths_of(items):
    out = []
    for item in items:
        for operation in item["operations"]:
            for held in [operation.get("target")] + list(operation.get("units") or ()):
                path = split_target(held)[0]
                if path and path not in out:
                    out.append(path)
    return out


def commands_of(checkout, paths):
    """The two commands the owner runs. S11 runs neither."""
    quoted = " ".join("'" + p.replace("'", "'\\''") + "'" for p in paths)
    root = "'" + str(checkout).replace("'", "'\\''") + "'"
    return {"commit": f"git -C {root} add -- {quoted} && git -C {root} commit",
            "install": f"bash {root}/install.sh install --non-interactive"}


def _plan_doc(confirmation_id, effects):
    rows = []
    for ordinal, effect in enumerate(effects):
        rows.append({**{k: effect[k] for k in ("item_id", "approval_id", "operation", "type", "path", "before",
                                               "after")},
                     "operation_id": operation_id(confirmation_id, effect, ordinal),
                     "data_b64": None if effect["data"] is None else base64.b64encode(effect["data"]).decode("ascii")})
    return {"stage": STAGE, "confirmation_id": confirmation_id, "effects": rows}


def plan_problems(plan, confirmation_id, items):
    """Why a plan read back is not the confirmed set's, by name. The shared record check already holds
    the file to the hash the plan part recorded; this holds what it SAYS to what was confirmed, so
    the effects part acts on nothing the confirmation does not bind."""
    if plan.get("confirmation_id") != confirmation_id:
        return [f"PLAN_UNBOUND {PLAN}: it was planned for another confirmation"]
    by_item, problems, last = {i["item_id"]: i for i in items}, [], {}
    for ordinal, row in enumerate(plan.get("effects") or []):
        who = f"{PLAN} effects[{ordinal}]"
        item = by_item.get(row.get("item_id"))
        if item is None or row.get("approval_id") != item["approval_id"]:
            problems.append(f"PLAN_EFFECT_UNCONFIRMED {who}: {row.get('item_id')} under approval "
                            f"{row.get('approval_id')} is not an item of the confirmed set")
            continue
        index = row.get("operation")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(item["operations"]):
            problems.append(f"PLAN_EFFECT_UNCONFIRMED {who}: {row.get('item_id')} has no operation {index!r}")
            continue
        operation = item["operations"][index]
        named = {split_target(held)[0] for held in [operation.get("target")] + list(operation.get("units") or ())}
        if row.get("path") not in named or row.get("type") != operation.get("type"):
            problems.append(f"PLAN_EFFECT_UNCONFIRMED {who}: {row.get('type')} {row.get('path')} is not what "
                            f"operation {index} of {row.get('item_id')} names")
            continue
        try:
            data = None if row.get("data_b64") is None else base64.b64decode(row["data_b64"], validate=True)
        except (ValueError, TypeError):
            problems.append(f"PLAN_CHANGED {who}: its bytes do not decode")
            continue
        if sha_of(data) != row.get("after"):
            problems.append(f"PLAN_CHANGED {who}: the bytes it holds for {row.get('path')} are not the ones it "
                            f"planned")
        if row.get("operation_id") != operation_id(confirmation_id, row, ordinal):
            problems.append(f"PLAN_CHANGED {who}: its operation id is not the one its fields derive")
        if row["path"] in last and last[row["path"]] != row.get("before"):
            problems.append(f"PLAN_CHANGED {who}: {row['path']} is planned from {str(row.get('before'))[:12]}, and "
                            f"the effect before it leaves {str(last[row['path']])[:12]}")
        last[row["path"]] = row.get("after")
    return problems


def _effects_in(doc):
    return [{**{k: v for k, v in row.items() if k != "data_b64"},
             "data": None if row["data_b64"] is None else base64.b64decode(row["data_b64"])}
            for row in doc["effects"]]


def journal_problems(held, effects):
    """Why the journal on disk is not this plan's, by name: it does not parse, or it holds a record
    the plan does not."""
    problems = [f"APPLY_JOURNAL_CORRUPT {JOURNAL}: {p}" for p in held.get("problems") or []]
    if held.get("torn") or held.get("unterminated"):
        problems.append(f"APPLY_JOURNAL_CORRUPT {JOURNAL}: its last record is torn or unterminated")
    planned = {e["operation_id"]: e for e in effects}
    rows = list(held.get("records") or [])
    for row in rows:
        effect = planned.get(row.get("operation_id"))
        if effect is None or (row.get("target"), row.get("before_sha256"), row.get("after_sha256"),
                              row.get("item_id"), row.get("approval_id")) != (
                effect["path"], effect["before"], effect["after"], effect["item_id"], effect["approval_id"]):
            problems.append(f"APPLY_JOURNAL_FOREIGN {JOURNAL}: it holds a {row.get('kind')} record for "
                            f"{row.get('target')} that the plan does not")
    if problems:
        return problems
    # The stream itself, in ITS order, is the plan's: planned then done for each effect in the plan's order - a
    # completed prefix, and at most one planned record after it. Read against the expected order instead of in its
    # own, two completed pairs swapped and two effects interleaved both passed (the S12 review, round 2).
    expected = [(e["operation_id"], kind) for e in effects for kind in ("planned", "done")]
    got = [(row.get("operation_id"), row.get("kind")) for row in rows]
    if got != expected[:len(got)]:
        at = next(i for i, pair in enumerate(got) if i >= len(expected) or pair != expected[i])
        problems.append(f"APPLY_JOURNAL_CORRUPT {JOURNAL}: record {at + 1} is a {got[at][1]!r} record where the "
                        f"plan's history has {'nothing' if at >= len(expected) else repr(expected[at][1])}; an "
                        f"operation's history is planned then done, in the plan's order")
    return problems


def _bound(run_dir, declaration, confirmation, version):
    """`(stored manifest, gathered, checkout)` once the confirmation binds, or Refused."""
    checkout = ((declaration or {}).get("destinations") or {}).get("checkout")
    if not checkout or not pathlib.Path(checkout).is_dir():
        raise Refused("CHECKOUT_UNDECLARED S11: the files are written in run.json's destinations.checkout, "
                      "which must be a directory")
    manifest_path = run_dir / stage_confirm.manifest_rel(version)
    stored = records.read_json(manifest_path)
    gathered = stage_confirm.gathered(run_dir)
    again, found = stage_confirm.final_set(declaration, *gathered)
    found = list(found) + stage_confirm.binding_problems(stored, again, records.sha256_file(manifest_path),
                                                          confirmation["manifest_sha"])
    if sorted(confirmation["approval_ids"]) != sorted(stored["approval_ids"]):
        found.append("CONFIRMATION_UNBOUND approval_ids: the confirmation does not bind the manifest's approvals")
    if found:
        raise Refused("\n".join(found))
    return stored, gathered, checkout


COMMITMENT = "apply/plan-commitment.json"
APPLY_LOCK = "S11-apply"
DECLARATION_WAIT_S = 5      # how long a write waits for an amendment in progress before it is refused


def plan(run_dir):
    """S11's plan part: `apply/plan.json`, or Refused with nothing written. One S11 call at a time: the lock is
    what makes "no journal yet" still true when the part's record is replaced."""
    with stagelock.hold(run_dir, APPLY_LOCK):
        return _plan(pathlib.Path(run_dir))


def _plan(run_dir):
    confirmation = records.read_json(run_dir / stage_confirm.CONFIRMATION)
    version = confirmation["confirm_version"]
    if (run_dir / JOURNAL).exists():
        raise Refused(f"PLAN_AFTER_EFFECTS {JOURNAL}: effects were taken from a plan that is not there to read; "
                      f"nothing is planned over them")
    with records.run_stage(run_dir, STAGE, inputs_of(run_dir, version), part=PLAN_PART) as stage:
        stored, gathered, checkout = _bound(run_dir, stage.declaration, confirmation, version)
        current, approvals, s7b = gathered[0], gathered[1], gathered[2]
        items = items_of(stored, current, approvals)
        paths = paths_of(items)
        judgments = {r.get("item_id"): r.get("faithful_merge") for r in (s7b or {}).get("reviews") or []}
        problems = (list(targets.set_problems(paths, checkout))
                    + spelling_problems(paths, targets.folds_case(checkout))
                    + list(drift.global_op_problems(items, judgments)))
        if problems:
            raise Refused("\n".join(problems))
        with Checkout(checkout) as tree:
            planned, problems = operations.plan_of(items, tree.read)
        if problems:
            raise Refused("\n".join(problems))
        records.write_json(run_dir, run_dir / PLAN, _plan_doc(confirmation["confirmation_id"], planned))
        stage.output(PLAN)
        return {"effects": len(planned)}


def _part(run_dir, name):
    return (((records.stage_records(run_dir).get(STAGE) or {}).get("parts") or {}).get(name)) or {}


def run(run_dir):
    """S11 over the confirmed final set: `apply.json`, or Refused with no file of the checkout
    written by this call."""
    with stagelock.hold(run_dir, APPLY_LOCK):
        return _run(pathlib.Path(run_dir))


def _held_declaration(run_dir, admitted, who=STAGE):
    """Refused unless the declaration is the one this part was admitted under. Called with the declaration's lock
    held, so an amendment (`declare.amend` takes that lock) cannot land between this answer and what follows it."""
    now_run, now_digest, _amendments = records.declaration_state(run_dir, who=who)
    if (now_run["declaration_seq"], now_digest) != admitted:
        raise Refused(f"DECLARATION_MOVED {who}: the declaration is at sequence {now_run['declaration_seq']} and "
                      f"this stage was admitted at {admitted[0]}; no further file is written")


def _run(run_dir):
    if not (run_dir / stage_confirm.CONFIRMATION).is_file():
        raise Refused("CONFIRMATION_ABSENT S11: the final set is not confirmed; S10b's confirm comes first")
    confirmation = records.read_json(run_dir / stage_confirm.CONFIRMATION)
    version = confirmation["confirm_version"]
    if _part(run_dir, PLAN_PART).get("status") != "complete" or not (run_dir / PLAN).is_file():
        _plan(run_dir)
    # The plan the effects are taken from is committed ONCE, before the first effect, in a file no attempt
    # replaces. The effects record's own pinned input is replaced by every attempt - a refused one too - so
    # reading the commitment from it let a refused retry authorize the plan it had just refused (round 2).
    earlier_plan = (records.read_json(run_dir / COMMITMENT).get("plan_sha256")
                    if (run_dir / COMMITMENT).is_file() else None)
    specs = inputs_of(run_dir, version) + [{"artifact": PLAN, "producer_stage": STAGE}]
    with records.run_stage(run_dir, STAGE, specs, part=EFFECTS_PART) as stage:
        declaration = stage.declaration
        stored, gathered, checkout = _bound(run_dir, declaration, confirmation, version)
        items = items_of(stored, gathered[0], gathered[1])
        # The plan's bytes are read ONCE, and they are the bytes admission checked: the record's pinned input.
        plan_bytes = (run_dir / PLAN).read_bytes()
        plan_sha = hashlib.sha256(plan_bytes).hexdigest()
        admitted_sha = next((i["sha256"] for i in stage.record["inputs"] if i["artifact"] == PLAN), None)
        if plan_sha != admitted_sha:
            raise Refused(f"PLAN_CHANGED {PLAN}: its bytes are not the ones this part was admitted on")
        held_plan = json.loads(plan_bytes.decode("utf-8"))
        problems = plan_problems(held_plan, confirmation["confirmation_id"], items)
        if problems:
            raise Refused("\n".join(problems))
        effects = _effects_in(held_plan)
        held = journal.read(run_dir / JOURNAL)
        problems = journal_problems(held, effects)
        if problems:
            raise Refused("\n".join(problems))
        # ... and the plan is the WHOLE ordered result of the confirmed operations, not rows that each pass.
        # Before any effect that is asked directly: the confirmed set planned again over the files as they are
        # must be this plan, byte for byte. Once effects were taken the files have moved, so the plan must be
        # the very one those effects were taken from.
        if held["records"] or earlier_plan is not None:
            if earlier_plan != plan_sha:
                raise Refused(f"PLAN_CHANGED {PLAN}: the effects of this run are committed to another plan "
                              f"({str(earlier_plan)[:12]}), and this one is {plan_sha[:12]}")
        else:
            with Checkout(checkout) as tree:
                again, problems = operations.plan_of(items, tree.read)
            if problems:
                raise Refused("\n".join(problems))
            if _plan_doc(confirmation["confirmation_id"], again) != held_plan:
                raise Refused(f"PLAN_NOT_THE_CONFIRMED_SET {PLAN}: the confirmed operations, planned over the files "
                              f"as they are, give {len(again)} effects that are not this plan's "
                              f"{len(held_plan.get('effects') or [])} in order and bytes")
            records.write_json(run_dir, run_dir / COMMITMENT,
                               {"stage": STAGE, "confirmation_id": confirmation["confirmation_id"],
                                "plan_sha256": plan_sha})
        stage.output(COMMITMENT)
        done = {r["operation_id"] for r in held["records"] if r.get("kind") == "done"}
        pending = {r["operation_id"] for r in held["records"] if r.get("kind") == "planned"} - done
        admitted = (declaration["declaration_seq"], stage.record["run_json_sha256"])
        with Checkout(checkout) as tree:
            for effect in effects:
                if effect["operation_id"] in pending:
                    now = tree.state(effect["path"])
                    where = ("its before-state" if now == effect["before"] else
                             "its after-state" if now == effect["after"] else "neither state the plan holds")
                    raise Refused(f"APPLY_UNRECONCILED {effect['path']}: an earlier run planned this write and "
                                  f"recorded no end; the file is at {where}. Inspect it in the checkout, restore "
                                  f"it if needed, and apply in a new run")
            rows = []
            for effect in effects:
                row = {k: effect[k] for k in ("operation_id", "item_id", "approval_id", "operation", "type",
                                              "path", "before", "after")}
                if effect["operation_id"] in done:
                    rows.append({**row, "state": "done_before"})
                    continue
                # The declaration this part was admitted under, held for the whole of each write: admission
                # releases the declaration's lock, so the lock is taken again around the check AND the effect,
                # and an amendment waits for the write or the write is refused - never both at once.
                with stagelock.hold(run_dir, "declaration", wait_s=DECLARATION_WAIT_S):
                    _held_declaration(run_dir, admitted)
                    record = journal.planned(effect["operation_id"], effect["path"], effect["before"],
                                             effect["after"], effect["item_id"], effect["approval_id"])
                    journal.journalled(run_dir / JOURNAL, record, str(run_dir),
                                       lambda effect=effect: tree.take(effect))
                rows.append({**row, "state": "applied"})
            if (run_dir / JOURNAL).is_file():
                stage.output(JOURNAL)
        changed = []
        for row in rows:
            if row["path"] not in changed:
                changed.append(row["path"])
        doc = {"stage": STAGE, "confirmation_id": confirmation["confirmation_id"], "checkout": str(checkout),
               "effects": rows, "paths": changed,
               "ledger_only": len(stored.get("ledger_only") or []),
               "counts": {"items": len(items), "effects": len(rows),
                          "applied": sum(1 for r in rows if r["state"] == "applied"),
                          "done_before": sum(1 for r in rows if r["state"] == "done_before"),
                          "files": len(changed)},
               "owner_commands": commands_of(checkout, changed) if changed else None,
               "not_done_by_this_stage": ["git", "install", "personal layers", "state roots"]}
        with stagelock.hold(run_dir, "declaration", wait_s=DECLARATION_WAIT_S):
            _held_declaration(run_dir, admitted)     # and once more before the stage says it is complete
            records.write_json(run_dir, run_dir / OUTPUT, doc)
        stage.output(OUTPUT)
        return doc


def report_lines(doc):
    """What the driver prints: counts, the files, and the two commands the owner runs."""
    counts = doc["counts"]
    lines = [f"S11 apply: {counts['items']} items, {counts['effects']} file changes over {counts['files']} files "
             f"in {doc['checkout']} ({counts['applied']} written now, {counts['done_before']} by an earlier run); "
             f"{doc['ledger_only']} approved items change the ledger alone and are S12's"]
    lines += [f"  {path}" for path in doc["paths"]]
    if doc["owner_commands"]:
        lines += ["This stage ran no git and no installer. The two commands are yours to run:",
                  f"  {doc['owner_commands']['commit']}", f"  {doc['owner_commands']['install']}"]
    else:
        lines.append("No file of the checkout changed, so there is nothing to commit or install.")
    return lines


# ---- self-test ---------------------------------------------------------------------------------------

def self_test():
    failures, ran, reporting = [], [], []
    try:
        _self_test_body(failures, ran, reporting)
    except Exception as exc:  # noqa: BLE001 - a suite that dies says so by name
        if reporting:
            raise
        failures.append(("the suite ran to its end", f"{type(exc).__name__}: {exc}"[:600]))
        ran.append("the suite ran to its end")
    if failures:
        for name, detail in failures:
            print(f"stage_apply --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"stage_apply --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"stage_apply --self-test: OK ({len(ran)} controls: the write itself - staged before the last check, links, "
          f"FIFOs, second names, spellings and outside paths refused - and the stage in its two parts: the plan "
          f"recorded and held to the confirmed set, the effects through the journal, an edited plan, a corrupt "
          f"journal, an amendment mid-run, a re-run and an unreconciled write)")
    return 0


def _self_test_body(failures, ran, reporting):
    import shutil
    import tempfile

    def control(name, got, want):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        ran.append(name)
        if got != want:
            failures.append((name, f"expected {want!r}, got {got!r}"[:900]))

    def said(call):
        try:
            call()
        except Refused as exc:
            return str(exc).split(":")[0].split()[0]
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return f"RAISED {type(exc).__name__}: {exc}"
        return ""

    doc = "# Guide\n\nintro\n\n## One\n\nfirst body\n\n### Deep\n\ndeep body\n\n## Two\n\nsecond body\n"
    files = {"g/a.md": doc.encode(), "g/b.md": b"# B\n\nbody of b\n", "g/r.md": b"# Routes\n"}
    A, B_, R = (hashlib.sha256(files[k]).hexdigest() for k in ("g/a.md", "g/b.md", "g/r.md"))
    control("the text rules are `operations.py`'s, and this stage plans with that module's plan",
            [plan_of is operations.plan_of, split_target("g/a.md#One")], [True, ("g/a.md", "One")])
    control("two planned paths that spell one directory differently are refused before anything is written",
            [[p.split()[0] for p in spelling_problems(["Upper/a.md", "upper/b.md"], True)],
             spelling_problems(["Upper/a.md", "Upper/b.md", "lower/c.md"], True)], [["APPLY_SPELLING_CONFLICT"], []])
    control("whether two cases are one name is the filesystem's to say: where it does not fold case they are two "
            "directories, where it did not say the set is refused rather than guessed, and two canonical forms of "
            "one name are one name everywhere",
            [spelling_problems(["Upper/a.md", "upper/b.md"], False),
             [p.split()[0] for p in spelling_problems(["Upper/a.md", "upper/b.md"], None)],
             spelling_problems(["caf\u00e9/a.md", "cafe\u0301/b.md"], True)],
            [[], ["APPLY_SPELLING_UNDECIDED"], []])

    # ---- the files -------------------------------------------------------------------------------
    root = pathlib.Path(tempfile.mkdtemp(prefix="s11-"))
    try:
        checkout = root / "checkout"
        (checkout / "g").mkdir(parents=True)
        for name, data in files.items():
            (checkout / name).write_bytes(data)
        outside = root / "outside.md"
        outside.write_text("outside\n")

        def effect(path, data, before=None):
            return {"path": path, "data": data, "after": sha_of(data),
                    "before": before if before is not None else sha_of(files.get(path))}

        with Checkout(checkout) as tree:
            control("the plan's reader gives a file's bytes and None for an absent one",
                    [tree.read("g/b.md"), tree.read("g/none.md"), tree.read("none/none.md")],
                    [files["g/b.md"], None, None])
            tree.take(effect("g/b.md", b"changed\n"))
            control("a write replaces the file, keeps its mode and leaves no temp file beside it",
                    [(checkout / "g/b.md").read_bytes(), sorted(p.name for p in (checkout / "g").iterdir()),
                     stat.S_IMODE((checkout / "g/b.md").stat().st_mode) == stat.S_IMODE(
                         (checkout / "g/a.md").stat().st_mode)],
                    [b"changed\n", ["a.md", "b.md", "r.md"], True])
            tree.take(effect("new/deep/n.md", b"n\n"))
            control("a create makes the directories it needs", (checkout / "new/deep/n.md").read_bytes(), b"n\n")
            tree.take(effect("new/deep/n.md", None, before=sha_of(b"n\n")))
            control("a removal removes the file", (checkout / "new/deep/n.md").exists(), False)
            control("a file that is not at the plan's before-state at the write is refused and left as it is",
                    [said(lambda: tree.take(effect("g/a.md", b"x", before=B_))), (checkout / "g/a.md").read_bytes()],
                    ["APPLY_BEFORE_MISMATCH", files["g/a.md"]])
            control("bytes that are not the planned after-state are never installed: the staged file is held to "
                    "it before the rename",
                    [said(lambda: tree.take({**effect("g/a.md", b"y"), "after": B_})),
                     (checkout / "g/a.md").read_bytes()], ["APPLY_STAGING_MOVED", files["g/a.md"]])
            (checkout / "g/a.md").write_bytes(files["g/a.md"])
            os.symlink(outside, checkout / "g" / "link.md")
            control("a target that is a symbolic link is refused, and what it points at is untouched",
                    [said(lambda: tree.take(effect("g/link.md", b"x", before=sha_of(b"outside\n")))),
                     outside.read_text()], ["APPLY_TARGET_UNOPENABLE", "outside\n"])
            os.symlink(root, checkout / "away")
            control("a directory in the path that is a symbolic link is refused",
                    said(lambda: tree.take(effect("away/outside.md", b"x", before=sha_of(b"outside\n")))),
                    "JOURNAL_SYMLINK_COMPONENT")
            os.link(checkout / "g/r.md", root / "second-name.md")
            control("a file with two names is refused, and the other name keeps its bytes",
                    [said(lambda: tree.take(effect("g/r.md", b"x"))), (root / "second-name.md").read_bytes()],
                    ["APPLY_TARGET_HARD_LINKED", files["g/r.md"]])
            control("a path that leaves the checkout is refused",
                    said(lambda: tree.read("../outside.md")), "JOURNAL_OUTSIDE_ROOT")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    control("the two commands name the checkout and the changed files, quoted",
            commands_of("/c o", ["a.md", "it's.md"]),
            {"commit": "git -C '/c o' add -- 'a.md' 'it'\\''s.md' && git -C '/c o' commit",
             "install": "bash '/c o'/install.sh install --non-interactive"})
    # ---- the stage: S10's real parse, S10b's build and confirm, then the apply -----------------------
    from grammar import owner_lines
    from runlib import declare
    K = b"# K\n\nold\n"

    def fx(name, place="claude/guides/g.md"):
        """A run parsed over two approved items - a create (at `place`) and a delete - and its own checkout."""
        base = pathlib.Path(tempfile.mkdtemp(prefix=f"s11-{name}-"))
        made.append(base)
        checkout = base / "checkout"
        (checkout / "claude" / "guides").mkdir(parents=True)
        (checkout / "claude" / "guides" / "k.md").write_bytes(K)
        declaration = declare.fixture()
        declaration["destinations"]["checkout"] = str(checkout)

        def edit(rows_doc):
            for row in rows_doc["rows"]:
                for operation in (row.get("proposal") or {}).get("operations") or []:
                    if operation["target"] == "claude/guides/k.md":
                        operation["before_state_sha256"] = sha_of(K)
                    if operation["target"] == "claude/guides/g.md":
                        operation["target"] = place
        run_dir = stage_confirm.fx_run(base, declaration, edit)
        copy = run_dir / "decisions.ko.v1.md"
        held = copy.read_text(encoding="utf-8").split("\n")
        for ident, lines in {"k-place": ["결정: 승인"],
                             "k-reduce": ["결정: 승인", "keep 해제: R-1 사용자가 직접 줄인다"]}.items():
            start = next(i for i, x in enumerate(held) if x.startswith(f"<!-- owner-block review item={ident} "))
            end = next(i for i in range(start + 1, len(held)) if held[i] == owner_lines.CLOSE)
            held = held[:start + 1] + lines + held[end:]
        copy.write_text("\n".join(held), encoding="utf-8")
        stage_approvals.run(run_dir, 1)
        return base, run_dir, checkout

    def confirmed(name, **over):
        base, run_dir, checkout = fx(name, **over)
        stage_confirm.build(run_dir)
        page = run_dir / stage_confirm.copy_name(1)
        page.write_text(page.read_text(encoding="utf-8").replace("확인:\n", "확인: 확정\n", 1), encoding="utf-8")
        stage_confirm.confirm(run_dir)
        return base, run_dir, checkout

    def refusal(call):
        try:
            call()
        except Refused as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return f"RAISED {type(exc).__name__}: {exc}"
        return ""

    def tree_of(checkout):
        return sorted(str(p.relative_to(checkout)) for p in checkout.rglob("*") if p.is_file())

    made, kept = [], []
    def section(title, body):
        """One scenario: a break inside it fails under ITS name, and the scenarios after it still run."""
        try:
            body()
        except Exception as exc:  # noqa: BLE001 - reported by name, never swallowed
            control(title, f"{type(exc).__name__}: {exc}"[:600], "ran to its end")

    def code(call):
        return (refusal(call).split() or [""])[0]

    try:
        def scenario_0():
            base, run_dir, checkout = fx("unconfirmed")
            control("an unconfirmed final set is not applied", refusal(lambda: run(run_dir)).split(":")[0],
                    "CONFIRMATION_ABSENT S11")
        section('an unconfirmed final set (section)', scenario_0)

        def scenario_1():
            base, run_dir, checkout = confirmed("applied")
            out = run(run_dir)
            control("the confirmed set is written: the create is there, the delete is gone, and nothing else moved",
                    [tree_of(checkout), (checkout / "claude/guides/g.md").read_bytes()], [["claude/guides/g.md"], b"text"])
            control("apply.json counts what was written and names the files",
                    [out["counts"], sorted(out["paths"]), [r["state"] for r in out["effects"]]],
                    [{"items": 2, "effects": 2, "applied": 2, "done_before": 0, "files": 2},
                     ["claude/guides/g.md", "claude/guides/k.md"], ["applied", "applied"]])
            held = journal.read(run_dir / JOURNAL)["records"]
            control("every write has its plan record before it and its done record after, with both states",
                    [[r["kind"] for r in held], sorted({(r["target"], r["before_sha256"], r["after_sha256"]) for r in held})],
                    [["planned", "done", "planned", "done"],
                     sorted([("claude/guides/g.md", ABSENT, sha_of(b"text")), ("claude/guides/k.md", sha_of(K), ABSENT)])])
            control("the stage names the two commands and says what it did not do",
                    [out["owner_commands"]["commit"].startswith(f"git -C '{checkout}' add -- "),
                     out["owner_commands"]["install"], out["not_done_by_this_stage"]],
                    [True, f"bash '{checkout}'/install.sh install --non-interactive",
                     ["git", "install", "personal layers", "state roots"]])
            rec = records.stage_records(run_dir).get(STAGE) or {}
            control("the stage's record has two parts: the plan is the plan part's output, and the journal and "
                    "apply.json the effects part's, which took the plan as a recorded input",
                    [rec.get("status"),
                     {name: sorted(o["artifact"] for o in part.get("outputs") or [])
                      for name, part in (rec.get("parts") or {}).items()},
                     PLAN in [i["artifact"] for i in ((rec.get("parts") or {}).get(EFFECTS_PART) or {}).get("inputs") or []]],
                    ["complete", {PLAN_PART: [PLAN], EFFECTS_PART: sorted([JOURNAL, OUTPUT, COMMITMENT])}, True])
            again = refusal(lambda: kept.append(run(run_dir)))
            control("a second apply writes nothing: every write is the journal's already",
                    [again, (kept[-1]["counts"] if kept else None), tree_of(checkout)],
                    ["", {"items": 2, "effects": 2, "applied": 0, "done_before": 2, "files": 2}, ["claude/guides/g.md"]])
            with open(run_dir / JOURNAL, "ab") as handle:
                handle.write(b"not a journal line\n")
            control("a journal that does not parse is refused on a re-run, even when every write is already done",
                    code(lambda: run(run_dir)), "APPLY_JOURNAL_CORRUPT")
        section('the apply of a confirmed set (section)', scenario_1)

        def scenario_2():
            base, run_dir, checkout = confirmed("moved")
            (checkout / "claude/guides/k.md").write_bytes(b"# K\n\nchanged by the owner\n")
            control("a file that moved after the proposal is refused before ANY write: the create is not made either",
                    [code(lambda: run(run_dir)), tree_of(checkout), (run_dir / JOURNAL).exists()],
                    ["APPLY_BEFORE_MISMATCH", ["claude/guides/k.md"], False])
        section('a file that moved after the proposal (section)', scenario_2)

        def scenario_3():
            base, run_dir, checkout = confirmed("edited")
            manifest = run_dir / stage_confirm.manifest_rel(1)
            manifest.write_text(manifest.read_text(encoding="utf-8").replace("k-place", "k-other"), encoding="utf-8")
            control("a manifest edited after the confirmation is refused before anything is read from it",
                    [code(lambda: run(run_dir)), tree_of(checkout)],
                    ["INPUT_INVALID", ["claude/guides/k.md"]])
        section('a manifest edited after the confirmation (section)', scenario_3)

        def scenario_4():
            base, run_dir, checkout = confirmed("linked")
            (checkout / "claude/guides/k.md").unlink()
            (base / "elsewhere.md").write_bytes(K)
            os.symlink(base / "elsewhere.md", checkout / "claude/guides/k.md")
            control("a target that became a link is refused by the target contract, with nothing written",
                    [bool(refusal(lambda: run(run_dir))), (base / "elsewhere.md").read_bytes(),
                     (checkout / "claude/guides/g.md").exists()], [True, K, False])
        section('a target that became a link (section)', scenario_4)

        def scenario_5():
            base, run_dir, checkout = confirmed("global", place="claude/CLAUDE.md")
            control("an addition to the always-loaded file that S7b did not judge a faithful merge is refused, "
                    "with nothing written",
                    [code(lambda: run(run_dir)), tree_of(checkout)],
                    ["GLOBAL_OP_UNJUDGED", ["claude/guides/k.md"]])
        section('an unjudged addition to the always-loaded file (section)', scenario_5)

        def scenario_6():
            base, run_dir, checkout = confirmed("cut")
            real_take = Checkout.take

            def cut(self, effect):
                if effect["path"].endswith("k.md"):
                    raise Refused("FIXTURE_CUT the write did not end")
                return real_take(self, effect)
            Checkout.take = cut
            try:
                first = code(lambda: run(run_dir))
            finally:
                Checkout.take = real_take
            second = refusal(lambda: run(run_dir))
            control("a write that did not end is not run again: the re-run names the file and the state it is at",
                    [first, second.split(":")[0], "its before-state" in second, (checkout / "claude/guides/k.md").exists()],
                    ["FIXTURE_CUT", "APPLY_UNRECONCILED claude/guides/k.md", True, True])
        section('a write that did not end (section)', scenario_6)

        def scenario_6b():
            # a completed prefix, then the REMAINING effect changed with its record made to agree: refused, and
            # refused again - the refusal itself must not become the next attempt's authority
            base, run_dir, checkout = confirmed("prefix")
            real_take, calls = Checkout.take, []

            def stop_after_first(self, effect):
                calls.append(effect["path"])
                if len(calls) == 2:
                    raise Refused("FIXTURE_STOP before the second effect")
                return real_take(self, effect)
            Checkout.take = stop_after_first
            try:
                first = code(lambda: run(run_dir))
            finally:
                Checkout.take = real_take
            # the second effect was planned and not done, so the journal's last record is taken back as a real
            # stop before it would have left it: a completed prefix and nothing after
            lines = (run_dir / JOURNAL).read_bytes().split(b"\n")
            (run_dir / JOURNAL).write_bytes(b"\n".join(lines[:2]) + b"\n")
            held = records.read_json(run_dir / PLAN)
            original = (run_dir / PLAN).read_bytes()
            changed = dict(held["effects"][1])
            changed.update(type=held["effects"][1]["type"], data_b64=base64.b64encode(b"UNAPPROVED").decode("ascii"),
                           after=sha_of(b"UNAPPROVED"))
            changed["operation_id"] = operation_id(held["confirmation_id"], changed, 1)
            (run_dir / PLAN).write_text(json.dumps({**held, "effects": [held["effects"][0], changed]}),
                                        encoding="utf-8")
            record_file = records.record_path(run_dir, STAGE)
            doc = json.loads(record_file.read_bytes())
            for output in doc["parts"][PLAN_PART]["outputs"]:
                if output["artifact"] == PLAN:
                    output["sha256"] = records.sha256_file(run_dir / PLAN)
            record_file.write_text(json.dumps(doc), encoding="utf-8")
            before_tree = {str(p.relative_to(checkout)): p.read_bytes() for p in checkout.rglob("*") if p.is_file()}
            answers = [code(lambda: run(run_dir)), code(lambda: run(run_dir)), code(lambda: run(run_dir))]
            control("after a completed prefix, a changed remainder is refused on every retry: a refused attempt does "
                    "not become the next one's authority, and nothing more is written",
                    [first, [a in ("PLAN_CHANGED", "PLAN_EFFECT_UNCONFIRMED", "APPLY_JOURNAL_FOREIGN") for a in answers],
                     len(set(answers)),
                     {str(p.relative_to(checkout)): p.read_bytes() for p in checkout.rglob("*") if p.is_file()}
                     == before_tree, records.read_json(run_dir / COMMITMENT)["plan_sha256"]
                     == hashlib.sha256(original).hexdigest()],
                    ["FIXTURE_STOP", [True, True, True], 1, True, True])
        section('a changed remainder after a completed prefix (section)', scenario_6b)

        def scenario_7():
            base, run_dir, checkout = confirmed("planted")
            plan(run_dir)
            held = records.read_json(run_dir / PLAN)
            foreign = {"item_id": "k-place", "approval_id": held["effects"][0]["approval_id"], "operation": 0,
                       "type": "create", "path": "unapproved.md", "before": ABSENT, "after": sha_of(b"FOREIGN"),
                       "data_b64": base64.b64encode(b"FOREIGN").decode("ascii")}
            foreign["operation_id"] = operation_id(held["confirmation_id"], foreign, 0)
            original = (run_dir / PLAN).read_bytes()
            answers = []
            for effects in ([foreign], []):
                (run_dir / PLAN).write_text(json.dumps({**held, "effects": effects}), encoding="utf-8")
                answers.append(code(lambda: run(run_dir)))
            control("a plan changed after it was recorded - an unapproved file put in, the approved effects taken "
                    "out - is refused before any write: the effects part reads the plan the plan part recorded",
                    [answers, tree_of(checkout), (run_dir / JOURNAL).exists()],
                    [["INPUT_INVALID", "INPUT_INVALID"], ["claude/guides/k.md"], False])
            # ... and when the record is made to agree with the planted plan, what the plan SAYS is still held
            # to the confirmed set
            (run_dir / PLAN).write_text(json.dumps({**held, "effects": [foreign]}), encoding="utf-8")
            record_file = records.record_path(run_dir, STAGE)
            record_held = record_file.read_bytes()
            doc = json.loads(record_held)
            for output in doc["parts"][PLAN_PART]["outputs"]:
                output["sha256"] = records.sha256_file(run_dir / PLAN)
            record_file.write_text(json.dumps(doc), encoding="utf-8")
            control("a planted plan whose record was made to agree is refused by what it says: its effect is not "
                    "the confirmed set's",
                    [code(lambda: run(run_dir)), tree_of(checkout), (run_dir / JOURNAL).exists()],
                    ["PLAN_EFFECT_UNCONFIRMED", ["claude/guides/k.md"], False])
            answers = []
            for effects in ([], held["effects"][:1], list(reversed(held["effects"]))):
                (run_dir / PLAN).write_text(json.dumps({**held, "effects": effects}), encoding="utf-8")
                doc = json.loads(record_held)
                for output in doc["parts"][PLAN_PART]["outputs"]:
                    output["sha256"] = records.sha256_file(run_dir / PLAN)
                record_file.write_text(json.dumps(doc), encoding="utf-8")
                answers.append(code(lambda: run(run_dir)))
            control("a plan that is empty, a subset or a reordering of the confirmed set's - each row valid - is "
                    "refused: the confirmed operations planned again must give this plan whole",
                    [answers, tree_of(checkout), (run_dir / JOURNAL).exists()],
                    [["PLAN_NOT_THE_CONFIRMED_SET", "PLAN_NOT_THE_CONFIRMED_SET", "PLAN_CHANGED"],
                     ["claude/guides/k.md"], False])
            record_file.write_bytes(record_held)
            (run_dir / PLAN).write_bytes(original)
            real_bound = globals()["_bound"]

            def swapped_after_admission(*args):
                (run_dir / PLAN).write_text(json.dumps({**held, "effects": [foreign]}), encoding="utf-8")
                return real_bound(*args)
            globals()["_bound"] = swapped_after_admission
            try:
                after_admission = code(lambda: run(run_dir))
            finally:
                globals()["_bound"] = real_bound
            control("plan bytes replaced AFTER the part was admitted are not the bytes admission checked",
                    [after_admission, tree_of(checkout)], ["PLAN_CHANGED", ["claude/guides/k.md"]])
            (run_dir / PLAN).write_bytes(original)
            control("and the recorded plan, put back, applies", [refusal(lambda: run(run_dir)), tree_of(checkout)],
                    ["", ["claude/guides/g.md"]])
        section('a plan changed after it was recorded (section)', scenario_7)

        def scenario_7b():
            base, run_dir, checkout = confirmed("spelled", place="Claude/guides/g.md")
            said_all = refusal(lambda: run(run_dir))
            control("a confirmed set whose paths spell one directory two ways is refused before any write",
                    ["APPLY_SPELLING_CONFLICT claude and Claude" in said_all
                     or "APPLY_SPELLING_CONFLICT Claude and claude" in said_all, tree_of(checkout)],
                    [True, ["claude/guides/k.md"]])
        section('two spellings of one directory in a confirmed set (section)', scenario_7b)

        def scenario_8():
            items = [{"item_id": "i1", "approval_id": "P-1", "operations": [
                {"type": "create", "target": "a.md", "before_state_sha256": ABSENT, "content": "one\n"},
                {"type": "edit", "target": "a.md", "before_state_sha256": ABSENT, "content": "two\n"}]}]
            # the second operation is held to the state the proposal read, so plan each alone and join them
            effects = [{"item_id": "i1", "approval_id": "P-1", "operation": 0, "type": "create", "path": "a.md",
                        "before": ABSENT, "after": sha_of(b"one\n"), "data": b"one\n"},
                       {"item_id": "i1", "approval_id": "P-1", "operation": 1, "type": "edit", "path": "a.md",
                        "before": sha_of(b"one\n"), "after": sha_of(b"two\n"), "data": b"two\n"}]
            good = _plan_doc("C-1", effects)

            def changed(index, **over):
                rows = [dict(r) for r in good["effects"]]
                rows[index].update(over)
                return [p.split()[0] for p in plan_problems({**good, "effects": rows}, "C-1", items)]
            control("a plan read back is held to the confirmed set: the item and its approval, the operation, a path "
                    "that operation names, the bytes, the operation id, and each file's chain",
                    [plan_problems(good, "C-1", items),
                     [p.split()[0] for p in plan_problems(good, "C-2", items)],
                     changed(0, item_id="other"), changed(0, approval_id="P-9"), changed(0, operation=7),
                     changed(0, path="b.md"), changed(0, type="delete"),
                     changed(0, data_b64=base64.b64encode(b"FOREIGN").decode("ascii")),
                     changed(1, before=ABSENT), changed(0, data_b64="!")],
                    [[], ["PLAN_UNBOUND"], ["PLAN_EFFECT_UNCONFIRMED"], ["PLAN_EFFECT_UNCONFIRMED"],
                     ["PLAN_EFFECT_UNCONFIRMED"], ["PLAN_EFFECT_UNCONFIRMED"], ["PLAN_EFFECT_UNCONFIRMED"],
                     ["PLAN_CHANGED"], ["PLAN_CHANGED", "PLAN_CHANGED"], ["PLAN_CHANGED"]])
            planned_rows = _effects_in(good)
            row = journal.planned(planned_rows[0]["operation_id"], "a.md", ABSENT, sha_of(b"one\n"), "i1", "P-1")
            second_row = journal.planned(planned_rows[1]["operation_id"], "a.md", sha_of(b"one\n"), sha_of(b"two\n"),
                                         "i1", "P-1")
            control("a journal is this plan's only when every record it holds is one of the plan's effects",
                    [journal_problems({"records": [row]}, planned_rows),
                     [p.split()[0] for p in journal_problems({"records": [second_row, {**second_row, "kind": "done"},
                                                                          row, {**row, "kind": "done"}]},
                                                             planned_rows)],     # two completed pairs, swapped
                     [p.split()[0] for p in journal_problems({"records": [row, second_row, {**second_row, "kind": "done"},
                                                                          {**row, "kind": "done"}]},
                                                             planned_rows)],     # two effects interleaved
                     journal_problems({"records": [row, {**row, "kind": "done"}, second_row]}, planned_rows),
                     [p.split()[0] for p in journal_problems({"records": [{**row, "target": "b.md"}]}, planned_rows)],
                     [p.split()[0] for p in journal_problems({"records": [{**row, "operation_id": "A-x"}]}, planned_rows)],
                     [p.split()[0] for p in journal_problems({"records": [{**row, "kind": "done"}]}, planned_rows)],
                     [p.split()[0] for p in journal_problems({"records": [{**row, "kind": "garbage"}]}, planned_rows)],
                     [p.split()[0] for p in journal_problems({"records": [row, row]}, planned_rows)],
                     [p.split()[0] for p in journal_problems({"records": [
                         journal.planned(planned_rows[1]["operation_id"], "a.md", sha_of(b"one\n"), sha_of(b"two\n"),
                                         "i1", "P-1")]}, planned_rows)],
                     journal_problems({"records": [row, {**row, "kind": "done"}]}, planned_rows),
                     [p.split()[0] for p in journal_problems({"records": [], "torn": [1]}, planned_rows)],
                     [p.split()[0] for p in journal_problems({"records": [], "problems": ["line 3"]}, planned_rows)]],
                    [[], ["APPLY_JOURNAL_CORRUPT"], ["APPLY_JOURNAL_CORRUPT"], [],
                     ["APPLY_JOURNAL_FOREIGN"], ["APPLY_JOURNAL_FOREIGN"],
                     ["APPLY_JOURNAL_CORRUPT"],      # a done record with no plan before it
                     ["APPLY_JOURNAL_CORRUPT"],      # a kind this stage does not read
                     ["APPLY_JOURNAL_CORRUPT"],      # a plan record twice
                     ["APPLY_JOURNAL_CORRUPT"],      # the plan's second effect and not its first
                     [], ["APPLY_JOURNAL_CORRUPT"], ["APPLY_JOURNAL_CORRUPT"]])
        section('a plan and a journal held to the confirmed set (section)', scenario_8)

        def scenario_9():
            base, run_dir, checkout = confirmed("amended")
            real_take, calls, during = Checkout.take, [], []

            def amend_during(self, effect):
                calls.append(effect["path"])
                if len(calls) == 1:
                    try:
                        declare.amend(run_dir, [("budget.per_stage.S8", 10_000)], "an amendment while S11 writes",
                                      scope=["S8"])
                        during.append("the amendment landed")
                    except stagelock.Locked as exc:
                        during.append((str(exc).split() or [""])[0])
                return real_take(self, effect)
            Checkout.take = amend_during
            try:
                answer = refusal(lambda: run(run_dir))
            finally:
                Checkout.take = real_take
            control("an amendment cannot land DURING a write: the declaration's lock is held from the check through "
                    "the effect, so the amendment is refused and the apply ends on the declaration it began on",
                    [during, answer, len(calls), (run_dir / OUTPUT).exists()], [["STAGE_LOCKED"], "", 2, True])
            base, run_dir, checkout = confirmed("amended-between")
            real_read, done = journal.read, []

            def amend_after_admission(path):
                if not done:
                    done.append(declare.amend(run_dir, [("budget.per_stage.S8", 10_000)],
                                              "an amendment after S11 was admitted", scope=["S8"]))
                return real_read(path)
            journal.read = amend_after_admission
            try:
                answer = code(lambda: run(run_dir))
            finally:
                journal.read = real_read
            control("an amendment that landed after admission stops the effects: no file is written",
                    [answer, tree_of(checkout), (run_dir / OUTPUT).exists()],
                    ["DECLARATION_MOVED", ["claude/guides/k.md"], False])
            base, run_dir, checkout = confirmed("amended-last")
            real_journalled, seen = journal.journalled, []

            def amend_after_last(path, record, root, effect):
                out = real_journalled(path, record, root, effect)
                seen.append(record["operation_id"])
                return out
            real_held = globals()["_held_declaration"]

            def moved_before_the_end(directory, admitted):
                if len(seen) == 2:          # both effects are done; the check before the stage says complete
                    raise Refused("DECLARATION_MOVED S11: (fixture) the declaration moved before the end")
                return real_held(directory, admitted)
            journal.journalled = amend_after_last
            globals()["_held_declaration"] = moved_before_the_end
            try:
                answer = code(lambda: run(run_dir))
            finally:
                journal.journalled = real_journalled
                globals()["_held_declaration"] = real_held
            control("the declaration is held once more before the stage says it is complete",
                    [answer, len(seen), (run_dir / OUTPUT).exists()], ["DECLARATION_MOVED", 2, False])
        section('an amendment while the effects run (section)', scenario_9)

        def scenario_10():
            base = pathlib.Path(tempfile.mkdtemp(prefix="s11-staging-"))
            made.append(base)
            checkout = base / "checkout"
            checkout.mkdir()
            (checkout / "a.md").write_bytes(b"planned from\n")
            effect = {"path": "a.md", "data": b"planned\n", "before": sha_of(b"planned from\n"),
                      "after": sha_of(b"planned\n")}
            real_state, real_named, seen = Checkout._state, Checkout._named, []

            def owner_writes_during_staging(self, parent, leaf, path):
                seen.append(leaf)
                if len(seen) == 2:                      # the check that follows the staging
                    (checkout / "a.md").write_bytes(b"OWNER CHANGED\n")
                return real_state(self, parent, leaf, path)
            Checkout._state = owner_writes_during_staging
            try:
                with Checkout(checkout) as tree:
                    first = code(lambda: tree.take(effect))
            finally:
                Checkout._state = real_state
            control("a target changed while the new bytes were being staged is not overwritten, and no temporary is "
                    "left beside it",
                    [first, (checkout / "a.md").read_bytes(), sorted(p.name for p in checkout.iterdir())],
                    ["APPLY_BEFORE_MISMATCH", b"OWNER CHANGED\n", ["a.md"]])
            (checkout / "a.md").write_bytes(b"planned from\n")
            seen.clear()

            def staged_file_changed_in_place(self, parent, leaf, path):
                seen.append(leaf)
                if len(seen) == 2:
                    for held_temp in checkout.glob(".a.md.s11-*.tmp"):
                        with open(held_temp, "r+b") as handle:      # the same inode, other bytes
                            handle.write(b"NOT PLANNED")
                return real_state(self, parent, leaf, path)
            Checkout._state = staged_file_changed_in_place
            try:
                with Checkout(checkout) as tree:
                    in_place = code(lambda: tree.take(effect))
            finally:
                Checkout._state = real_state
            control("a staged file changed in place before the rename is not installed: its bytes are read back "
                    "through the descriptor that wrote them",
                    [in_place, (checkout / "a.md").read_bytes(), sorted(p.name for p in checkout.iterdir())],
                    ["APPLY_STAGING_MOVED", b"planned from\n", ["a.md"]])

            (checkout / "a.md").write_bytes(b"planned from\n")
            seen.clear()

            def name_given_to_a_rival(self, parent, leaf, path):
                seen.append(leaf)
                held_state = real_state(self, parent, leaf, path)      # the OLD file's bytes, read to the end
                if len(seen) == 2:
                    (checkout / "rival.md").write_bytes(b"RIVAL\n")
                    os.replace(checkout / "rival.md", checkout / "a.md")
                return held_state
            Checkout._state = name_given_to_a_rival
            try:
                with Checkout(checkout) as tree:
                    rival = code(lambda: tree.take(effect))
            finally:
                Checkout._state = real_state
            control("a rival file put under the target's name while the old one was being read is not overwritten",
                    [rival, (checkout / "a.md").read_bytes(), sorted(p.name for p in checkout.iterdir())],
                    ["APPLY_BEFORE_MISMATCH", b"RIVAL\n", ["a.md"]])
            (checkout / "a.md").write_bytes(b"planned from\n")
            real_pread, reads = os.pread, []

            def changed_during_the_scan(fd, length, offset):
                out = real_pread(fd, length, offset)
                if not reads:
                    reads.append(True)
                    for held_temp in checkout.glob(".a.md.s11-*.tmp"):
                        with open(held_temp, "r+b") as handle:
                            handle.write(b"XXXXXXX\n")
                return out
            os.pread = changed_during_the_scan
            try:
                with Checkout(checkout) as tree:
                    during = code(lambda: tree.take(effect))
            finally:
                os.pread = real_pread
            control("a staged file changed WHILE it was being read back is not installed: the scan must have read "
                    "a file standing still",
                    [during, (checkout / "a.md").read_bytes(), sorted(p.name for p in checkout.iterdir())],
                    ["APPLY_STAGING_MOVED", b"planned from\n", ["a.md"]])
            with Checkout(checkout) as tree:
                absent_parent = code(lambda: tree.take({"path": "nodir/x.md", "data": b"x\n",
                                                        "before": sha_of(b"was there\n"), "after": sha_of(b"x\n")}))
            control("a refused replacement leaves no directory behind: directories are made only for a file that "
                    "is not there yet",
                    [bool(absent_parent), sorted(p.name for p in checkout.iterdir())], [True, ["a.md"]])

            def swapped(parent, name):
                if name.endswith(".tmp"):
                    os.unlink(name, dir_fd=parent)
                    handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644, dir_fd=parent)
                    os.write(handle, b"NOT PLANNED\n")
                    os.close(handle)
                return real_named(parent, name)
            Checkout._named = staticmethod(swapped)
            try:
                with Checkout(checkout) as tree:
                    second = code(lambda: tree.take(effect))
            finally:
                Checkout._named = staticmethod(real_named)
            control("a temporary whose name was given to another file is not installed",
                    [second, (checkout / "a.md").read_bytes(), sorted(p.name for p in checkout.iterdir())],
                    ["APPLY_STAGING_MOVED", b"planned from\n", ["a.md"]])
            # a FIFO where the file is named: asked on another thread and held to a deadline, so a blocking
            # open fails this control by name instead of hanging the suite
            import threading
            os.mkfifo(checkout / "pipe.md")
            answered = []

            def ask():
                with Checkout(checkout) as tree:
                    answered.append(code(lambda: tree.read("pipe.md")))
            asking = threading.Thread(target=ask, daemon=True)
            asking.start()
            asking.join(10)
            waited = asking.is_alive()      # an answer that came only after the release is not "at once"
            if waited:
                released = os.open(checkout / "pipe.md", os.O_WRONLY | os.O_NONBLOCK)
                asking.join(10)
                os.close(released)
            control("a FIFO named as a target is refused at once: its open does not wait for a writer",
                    [waited, answered[:1]], [False, ["APPLY_TARGET_NOT_FILE"]])
            (checkout / "Upper").mkdir()
            folds = (checkout / "UPPER").exists()
            with Checkout(checkout) as tree:
                alias = code(lambda: tree.take({"path": "upper/b.md", "data": b"b\n", "before": ABSENT,
                                                "after": sha_of(b"b\n")}))
            control("where the filesystem folds case, a write through another spelling of a directory is refused "
                    "(where it does not, the directory is simply another one)",
                    [alias, (checkout / "Upper" / "b.md").exists()],
                    ["APPLY_SPELLING_ON_DISK" if folds else "", False])
        section('the write itself: staging, a FIFO, a spelling (section)', scenario_10)

    finally:
        for base in made:
            shutil.rmtree(base, ignore_errors=True)

    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    body = source.split("# ---- self-test ----")[0]
    control("the stage starts no process: its source names no subprocess, os.system, exec or spawn",
            [word for word in ("subprocess", "os.system", "os.exec", "os.spawn", "os.popen", "pty.")
             if word in body.split('"""', 2)[2]], [])
    reporting.append(True)


def main(argv):
    if argv[1:] == ["--self-test"]:
        return self_test()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
