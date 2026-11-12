#!/usr/bin/env python3
"""S11 apply, release 1: the confirmed final set written into files of the declared checkout.

The owner decided the release-1 form on 2026-11-13 (D-20261113-f22b7d): S11 writes the approved
changes into files of the declared checkout and NOTHING else. It starts no process — no git, no
installer, no hook — and writes no personal layer and no state root. Its other writes are inside the
run directory: the plan, the write-ahead journal and its own record. It ends by naming the two
commands the owner runs, the commit and the install, and runs neither.

What an operation DOES is defined here, because nothing else defined it (the packet names the five
types and their fields; §7.3 gives their shape). The definitions are deterministic and take no
patch: a model writes text, and code places it.

    target      `path` or `path#heading`. The path is a file of the checkout; the heading is one
                ATX heading of that file (its title, with or without its `#`s), which must occur
                exactly once outside fenced code. A heading's SECTION runs from its line to the next
                heading of the same or a higher level.
    create      the file is absent; it becomes `content`.
    edit        the file is present. With `anchor`: that exact text occurs once in the section (or
                the file) and is replaced by `content`. With a heading and no anchor: the section is
                replaced by `content`. With neither: the file becomes `content`. A `diff` is not
                applied: an edit that carries no `content` is refused by name.
    delete      with `anchor`: that text is removed. With a heading: the section is removed. With
                neither: the file is removed.
    merge       each unit is removed (its section, or its file when it names none), except the unit
                that IS the target; then the target takes `content` as an edit does, or is created.
    route       `entry` is appended to the section (or the file) as one line; an entry already there
                is refused rather than written twice.

Order of the stage, each step refusing before the next and before any effect:

1. the confirmation binds: the manifest S10b recorded is on disk unchanged, and the final set built
   again from the run's records is that manifest (`stage_confirm.binding_problems`). The declaration
   is the one `records.run_stage` admits, so a stale declaration or a moved input stops here;
2. every path any operation touches passes the target contract (`targets.set_problems`), and an
   operation that ADDS to the always-loaded file has S7b's faithful-merge judgment
   (`drift.global_op_problems`);
3. the plan: every operation applied in the confirmed order to the files as they are NOW, in memory.
   Each operation's `before_state_sha256` — the state S7 read when the proposal was written — must be
   the file's state now, so a file that moved since is refused, not patched. The plan is written to
   the run directory once and a re-run reads it back rather than planning again;
4. the effects, one file at a time through `journal.journalled` holding the journal's lock from the
   plan record to the done record. Every file is reached by a confined walk from the checkout's own
   descriptor (`journal.Confined`): no symlink in the chain, a regular file with one name, its
   state checked through the descriptor immediately before the write and the written state read back
   before the done record. A write is a temp file made beside the target, synced, renamed over it,
   and the directory synced.

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
import re
import stat
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runlib import (drift, journal, records, stage_approvals, stage_confirm,  # noqa: E402
                    stage_review_proposals, targets)
from runlib.records import Refused  # noqa: E402

STAGE = "S11"
OUTPUT = "apply.json"
PLAN = "apply/plan.json"
JOURNAL = "apply/journal.jsonl"
ABSENT = "absent"
TYPES = ("create", "edit", "delete", "merge", "route")
_NOFOLLOW = journal._NOFOLLOW   # one answer for the walk and the leaf: the journal's own
HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
FENCE = re.compile(r"^[ \t]{0,3}(```|~~~)")


def sha_of(data):
    return ABSENT if data is None else hashlib.sha256(data).hexdigest()


# ---- what an operation does to a text ---------------------------------------------------------------

def split_target(target):
    """`(path identity, heading | None)` of a target or a unit: `path` or `path#heading`."""
    path, _, heading = str(target or "").partition("#")
    return targets.identity(path), (heading.strip() or None)


def headings(text):
    """`[(line index, level, title)]` of the ATX headings of `text` outside fenced code."""
    out, fence = [], None
    for index, line in enumerate(text.split("\n")):
        opened = FENCE.match(line)
        if opened:
            fence = None if fence == opened.group(1) else (fence or opened.group(1))
            continue
        if fence:
            continue
        held = HEADING.match(line)
        if held:
            out.append((index, len(held.group(1)), held.group(2)))
    return out


def section_span(text, heading, who):
    """`(start, end)` character offsets of the one section `heading` names, or Refused by name."""
    marks = re.match(r"^(#{1,6})[ \t]+", heading)
    title = heading[marks.end():].strip() if marks else heading.strip()
    held = headings(text)
    found = [(i, level) for i, level, name in held
             if name == title and (not marks or level == len(marks.group(1)))]
    if not found:
        raise Refused(f"HEADING_ABSENT {who}: the file holds no heading {heading!r} outside fenced code")
    if len(found) > 1:
        raise Refused(f"HEADING_AMBIGUOUS {who}: the file holds {len(found)} headings {heading!r}, and a "
                      f"section is named by one")
    index, level = found[0]
    after = next((i for i, lvl, _name in held if i > index and lvl <= level), None)
    lines = text.split("\n")
    start = sum(len(line) + 1 for line in lines[:index])
    end = len(text) if after is None else sum(len(line) + 1 for line in lines[:after])
    return start, min(end, len(text))


def _scope(text, heading, who):
    return section_span(text, heading, who) if heading else (0, len(text))


def _anchor_at(text, span, anchor, who):
    start, end = span
    count = text.count(anchor, start, end) if anchor else 0
    if count == 0:
        raise Refused(f"ANCHOR_ABSENT {who}: the anchor does not occur in "
                      f"{'the section' if (start, end) != (0, len(text)) else 'the file'}")
    if count > 1:
        raise Refused(f"ANCHOR_AMBIGUOUS {who}: the anchor occurs {count} times, and a place is named by one")
    return text.index(anchor, start, end)


def _block(content, text, end):
    """`content` as a block that ends its line when more of the file follows it."""
    return content if end >= len(text) or content.endswith("\n") or not content else content + "\n"


def _content(operation, who):
    held = operation.get("content")
    if not isinstance(held, str):
        if operation.get("diff") is not None:
            raise Refused(f"OPERATION_NOT_APPLICABLE {who}: it carries a diff and no content, and release 1 "
                          f"places text and applies no patch")
        raise Refused(f"CONTENT_ABSENT {who}: a {operation.get('type')} names the text it writes in `content`")
    return held


def placed(text, heading, anchor, content, who):
    """`text` with `content` placed: over the anchor, over the section, or as the whole."""
    if anchor:
        at = _anchor_at(text, _scope(text, heading, who), anchor, who)
        return text[:at] + content + text[at + len(anchor):]
    if heading:
        start, end = section_span(text, heading, who)
        return text[:start] + _block(content, text, end) + text[end:]
    return content


def removed(text, heading, anchor, who):
    """`text` without the anchor or the section; None when neither is named (the file goes)."""
    if anchor:
        at = _anchor_at(text, _scope(text, heading, who), anchor, who)
        return text[:at] + text[at + len(anchor):]
    if heading:
        start, end = section_span(text, heading, who)
        return text[:start] + text[end:]
    return None


def routed(text, heading, entry, who):
    """`text` with `entry` appended as one line to the section or the file."""
    if not isinstance(entry, str) or not entry.strip() or "\n" in entry.strip("\n"):
        raise Refused(f"ROUTE_ENTRY_INVALID {who}: a route's `entry` is one non-empty line")
    line = entry.strip("\n")
    start, end = _scope(text, heading, who)
    if line in text[start:end].split("\n"):
        raise Refused(f"ROUTE_ENTRY_PRESENT {who}: that entry is already there")
    body = text[start:end]
    joint = "" if not body or body.endswith("\n") else "\n"
    return text[:end] + joint + line + "\n" + text[end:]


class Tree:
    """The checkout's files as the plan sees them: read once from `read(path)` (bytes, or None when
    absent), then changed in memory only."""

    def __init__(self, read):
        self.read, self.first, self.now = read, {}, {}

    def initial(self, path):
        if path not in self.first:
            self.first[path] = self.read(path)
            self.now[path] = self.first[path]
        return self.first[path]

    def get(self, path):
        self.initial(path)
        return self.now[path]

    def text(self, path, who):
        held = self.get(path)
        if held is None:
            return None
        try:
            return held.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Refused(f"APPLY_NOT_TEXT {who}: {path} is not UTF-8 text, and an operation places text") from exc

    def put(self, path, text):
        self.initial(path)
        self.now[path] = None if text is None else text.encode("utf-8")


def operation_effects(operation, tree, who):
    """`[(path, bytes | None)]`: the files one operation leaves changed, in the order it changes
    them, each with its new state. Refused by name where the operation does not apply."""
    kind = operation.get("type")
    if kind not in TYPES:
        raise Refused(f"OPERATION_UNKNOWN {who}: {kind!r} is not one of {', '.join(TYPES)}")
    path, heading = split_target(operation.get("target"))
    if not path:
        raise Refused(f"TARGET_ABSENT {who}: the operation names no file")
    carried = operation.get("before_state_sha256")
    if sha_of(tree.initial(path)) != carried:
        raise Refused(f"APPLY_BEFORE_MISMATCH {who}: {path} is {sha_of(tree.initial(path))[:12]} now, and the "
                      f"proposal was written against {str(carried)[:12]}")
    text = tree.text(path, who)
    anchor = operation.get("anchor") or None
    touched = []

    def put(where, new):
        tree.put(where, new)
        touched.append((where, tree.get(where)))

    if kind == "create":
        if text is not None:
            raise Refused(f"CREATE_TARGET_PRESENT {who}: {path} is there, and a create makes a file")
        if heading or anchor:
            raise Refused(f"CREATE_WITH_PLACE {who}: a create writes a whole file and names no heading or anchor")
        put(path, _content(operation, who))
    elif kind == "edit":
        if text is None:
            raise Refused(f"EDIT_TARGET_ABSENT {who}: {path} is not there")
        put(path, placed(text, heading, anchor, _content(operation, who), who))
    elif kind == "delete":
        if text is None:
            raise Refused(f"DELETE_TARGET_ABSENT {who}: {path} is not there")
        put(path, removed(text, heading, anchor, who))
    elif kind == "route":
        if text is None:
            raise Refused(f"ROUTE_TARGET_ABSENT {who}: {path} is not there")
        put(path, routed(text, heading, operation.get("entry"), who))
    else:   # merge: the units first, the target after (`sequencing.apply_to`'s order)
        content = _content(operation, who)
        states = {row.get("unit"): row.get("state") for row in operation.get("unit_states") or ()
                  if isinstance(row, dict)}
        for unit in operation.get("units") or ():
            unit_path, unit_heading = split_target(unit)
            if (unit_path, unit_heading) == (path, heading):
                continue                      # the unit that IS the target is replaced, not removed
            if unit_path != path:
                if unit not in states:
                    raise Refused(f"MERGE_UNIT_STATE_ABSENT {who}: {unit} is in another file than the target, "
                                  f"and the operation carries no state for it")
                if sha_of(tree.initial(unit_path)) != states[unit]:
                    raise Refused(f"APPLY_BEFORE_MISMATCH {who}: {unit_path} is "
                                  f"{sha_of(tree.initial(unit_path))[:12]} now, and the proposal was written "
                                  f"against {str(states[unit])[:12]}")
            held = tree.text(unit_path, who)
            if held is None:
                raise Refused(f"MERGE_UNIT_ABSENT {who}: {unit_path} is not there")
            put(unit_path, removed(held, unit_heading, None, who))
        text = tree.text(path, who)
        put(path, content if text is None or not heading else placed(text, heading, None, content, who))
    return touched


def plan_of(items, read):
    """`(effects, problems)` for the confirmed items in their order: every operation applied in
    memory to the files `read` gives. An effect is one file's change by one operation — `item_id`,
    `approval_id`, `operation` (its index), `type`, `path`, `before`, `after` and the bytes it
    leaves (`data`, None for a removal). Any problem and nothing is to be written."""
    tree, effects, problems = Tree(read), [], []
    for item in items:
        for index, operation in enumerate(item.get("operations") or []):
            who = f"{item['item_id']} operations[{index}]"
            before = {}
            try:
                # the state before, of every file the operation may touch, taken before it runs
                paths = [split_target(operation.get("target"))[0]]
                paths += [split_target(u)[0] for u in operation.get("units") or ()]
                for path in paths:
                    if path:
                        before.setdefault(path, sha_of(tree.get(path)))
                touched = operation_effects(operation, tree, who)
            except Refused as exc:
                problems.append(str(exc))
                continue
            for path, data in touched:
                effects.append({"item_id": item["item_id"], "approval_id": item["approval_id"],
                                "operation": index, "type": operation.get("type"), "path": path,
                                "before": before[path], "after": sha_of(data), "data": data})
                before[path] = sha_of(data)
    return [e for e in effects if e["before"] != e["after"]], problems


def operation_id(confirmation_id, effect, ordinal):
    held = json.dumps([confirmation_id, effect["item_id"], effect["operation"], effect["path"], ordinal,
                       effect["before"], effect["after"]])
    return "A-" + hashlib.sha256(held.encode("utf-8")).hexdigest()[:24]


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
    def _state(parent, leaf, path):
        """`(sha | "absent", mode | None)` of the leaf, read through its own descriptor."""
        try:
            handle = os.open(leaf, os.O_RDONLY | _NOFOLLOW, dir_fd=parent)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return ABSENT, None
            raise Refused(f"APPLY_TARGET_UNOPENABLE {path}: {exc.strerror} - a target is a regular file "
                          f"and never a link") from exc
        try:
            held = os.fstat(handle)
            if not stat.S_ISREG(held.st_mode):
                raise Refused(f"APPLY_TARGET_NOT_FILE {path}: a target is a regular file")
            if held.st_nlink != 1:
                raise Refused(f"APPLY_TARGET_HARD_LINKED {path}: it has {held.st_nlink} names, and a write "
                              f"through one would change a file the checkout does not name")
            digest = hashlib.sha256()
            while True:
                chunk = os.read(handle, 1 << 20)
                if not chunk:
                    break
                digest.update(chunk)
            return digest.hexdigest(), stat.S_IMODE(held.st_mode)
        finally:
            os.close(handle)

    def read(self, path):
        """The file's bytes, or None when it is absent (the plan's reader)."""
        fds, leaf, _made = self.confined.walk(self._pieces(path), missing_ok=True)
        if fds is None:
            return None
        try:
            try:
                handle = os.open(leaf, os.O_RDONLY | _NOFOLLOW, dir_fd=fds[-1])
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    return None
                raise Refused(f"APPLY_TARGET_UNOPENABLE {path}: {exc.strerror}") from exc
            try:
                if not stat.S_ISREG(os.fstat(handle).st_mode):
                    raise Refused(f"APPLY_TARGET_NOT_FILE {path}: a target is a regular file")
                out = b""
                while True:
                    chunk = os.read(handle, 1 << 20)
                    if not chunk:
                        return out
                    out += chunk
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

    def take(self, effect):
        """One effect on disk: the before-state checked through the descriptor, the change made
        durably, the after-state read back. Raises Refused and leaves the done record unwritten on
        any difference."""
        path, data = effect["path"], effect["data"]
        fds, leaf, _made = self.confined.walk(self._pieces(path), create=data is not None)
        try:
            parent = fds[-1]
            now, mode = self._state(parent, leaf, path)
            if now != effect["before"]:
                raise Refused(f"APPLY_BEFORE_MISMATCH {path}: it is {now[:12]} at the write, and the plan "
                              f"holds {effect['before'][:12]}")
            if data is None:
                os.unlink(leaf, dir_fd=parent)
            else:
                temp = f".{leaf}.s11-{os.getpid()}.tmp"
                handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
                                 0o644 if mode is None else mode, dir_fd=parent)
                try:
                    try:
                        view = memoryview(data)
                        while view:
                            view = view[os.write(handle, view):]
                        os.fsync(handle)
                    finally:
                        os.close(handle)
                    os.replace(temp, leaf, src_dir_fd=parent, dst_dir_fd=parent)
                except BaseException:
                    try:
                        os.unlink(temp, dir_fd=parent)
                    except OSError:
                        pass
                    raise
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


def _effects_in(doc):
    out = []
    for row in doc["effects"]:
        data = None if row["data_b64"] is None else base64.b64decode(row["data_b64"])
        if sha_of(data) != row["after"]:
            raise Refused(f"PLAN_CHANGED {PLAN}: the bytes it holds for {row['path']} are not the ones it planned")
        out.append({**{k: v for k, v in row.items() if k != "data_b64"}, "data": data})
    return out


def run(run_dir):
    """S11 over the confirmed final set: `apply.json`, or Refused with no file of the checkout
    written by this call."""
    run_dir = pathlib.Path(run_dir)
    if not (run_dir / stage_confirm.CONFIRMATION).is_file():
        raise Refused("CONFIRMATION_ABSENT S11: the final set is not confirmed; S10b's confirm comes first")
    confirmation = records.read_json(run_dir / stage_confirm.CONFIRMATION)
    version = confirmation["confirm_version"]
    with records.run_stage(run_dir, STAGE, inputs_of(run_dir, version)) as stage:
        declaration = stage.declaration
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
        current, approvals, s7b = gathered[0], gathered[1], gathered[2]
        items = items_of(stored, current, approvals)
        paths = paths_of(items)
        judgments = {r.get("item_id"): r.get("faithful_merge") for r in (s7b or {}).get("reviews") or []}
        problems = list(targets.set_problems(paths, checkout)) + list(drift.global_op_problems(items, judgments))
        if problems:
            raise Refused("\n".join(problems))
        with Checkout(checkout) as tree:
            if (run_dir / PLAN).is_file():
                plan = records.read_json(run_dir / PLAN)
                if plan.get("confirmation_id") != confirmation["confirmation_id"]:
                    raise Refused(f"PLAN_UNBOUND {PLAN}: it was planned for another confirmation")
                effects = _effects_in(plan)
            else:
                planned, problems = plan_of(items, tree.read)
                if problems:
                    raise Refused("\n".join(problems))
                plan = _plan_doc(confirmation["confirmation_id"], planned)
                records.write_json(run_dir, run_dir / PLAN, plan)
                effects = _effects_in(plan)
            stage.output(PLAN)
            held = journal.read(run_dir / JOURNAL) if (run_dir / JOURNAL).is_file() else {"records": []}
            done = {r["operation_id"] for r in held["records"] if r.get("kind") == "done"}
            pending = {r["operation_id"] for r in held["records"] if r.get("kind") == "planned"} - done
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
                record = journal.planned(effect["operation_id"], effect["path"], effect["before"], effect["after"],
                                         effect["item_id"], effect["approval_id"])
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
    print(f"stage_apply --self-test: OK ({len(ran)} controls: each operation type placed and refused by name, the "
          f"plan held to the files' states, the effects through the journal with the before- and after-state "
          f"checked, links and outside paths refused, a re-run and an unreconciled write)")
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

    # ---- the text rules --------------------------------------------------------------------------
    control("a section runs from its heading to the next heading of the same or a higher level",
            doc[slice(*section_span(doc, "One", "t"))], "## One\n\nfirst body\n\n### Deep\n\ndeep body\n\n")
    control("the last section runs to the end of the file", doc[slice(*section_span(doc, "## Two", "t"))],
            "## Two\n\nsecond body\n")
    control("a heading is named with its marks or without, and the marks are held to its level",
            [said(lambda: section_span(doc, "### One", "t")), said(lambda: section_span(doc, "Three", "t"))],
            ["HEADING_ABSENT", "HEADING_ABSENT"])
    control("two headings of one title are ambiguous, by name",
            said(lambda: section_span(doc + "\n## One\n\nagain\n", "One", "t")), "HEADING_AMBIGUOUS")
    control("a heading inside fenced code is not a heading",
            [h[2] for h in headings("# A\n\n```\n# not\n```\n\n~~~\n## nor\n~~~\n## B\n")], ["A", "B"])
    control("an edit with a heading replaces the section and keeps what follows on its own line",
            placed(doc, "Two", None, "## Two\n\nnew", "t"), doc.replace("## Two\n\nsecond body\n", "## Two\n\nnew"))
    control("a section in the middle replaced by text without a final newline still ends its line",
            placed(doc, "### Deep", None, "### Deep\n\nX", "t"),
            doc.replace("### Deep\n\ndeep body\n\n", "### Deep\n\nX\n"))
    control("an edit with an anchor replaces that text once, inside the section it names",
            placed(doc, "One", "first body", "FIRST", "t"), doc.replace("first body", "FIRST"))
    control("an anchor outside the named section is absent, and one occurring twice is ambiguous",
            [said(lambda: placed(doc, "One", "second body", "x", "t")),
             said(lambda: placed(doc, None, "body", "x", "t"))], ["ANCHOR_ABSENT", "ANCHOR_AMBIGUOUS"])
    control("an edit with neither is the whole file", placed(doc, None, None, "whole\n", "t"), "whole\n")
    control("a delete removes the anchor, the section, or - with neither - the file",
            [removed(doc, None, "intro\n\n", "t"), removed(doc, "Two", None, "t"), removed(doc, None, None, "t")],
            [doc.replace("intro\n\n", ""), doc.replace("## Two\n\nsecond body\n", ""), None])
    control("a route appends one line to the section, and to the file when no heading is named",
            [routed(doc, "One", "- [x](x.md)", "t"), routed("a\nb", None, "c", "t")],
            [doc.replace("deep body\n\n", "deep body\n\n- [x](x.md)\n"), "a\nb\nc\n"])
    control("a route already there, an empty one and a two-line one are refused by name",
            [said(lambda: routed("a\nb\n", None, "b", "t")), said(lambda: routed(doc, None, " ", "t")),
             said(lambda: routed(doc, None, "a\nb", "t"))],
            ["ROUTE_ENTRY_PRESENT", "ROUTE_ENTRY_INVALID", "ROUTE_ENTRY_INVALID"])

    # ---- the plan --------------------------------------------------------------------------------
    files = {"g/a.md": doc.encode(), "g/b.md": b"# B\n\nbody of b\n", "g/r.md": b"# Routes\n"}
    A, B_, R = (hashlib.sha256(files[k]).hexdigest() for k in ("g/a.md", "g/b.md", "g/r.md"))

    def item(*operations, item_id="i1", approval="P-1"):
        return {"item_id": item_id, "approval_id": approval, "operations": list(operations)}

    def planned(*items, held=None):
        return plan_of(list(items), (held or files).get)

    def codes(problems):
        return [p.split()[0] for p in problems]

    effects, problems = planned(item({"type": "create", "target": "g/new.md", "before_state_sha256": ABSENT,
                                      "content": "# New\n"},
                                     {"type": "route", "target": "g/r.md", "before_state_sha256": R,
                                      "entry": "- g/new.md"}))
    control("a create and a route are two effects, each with the state before and the state after",
            [problems, [(e["path"], e["before"], e["after"], e["data"]) for e in effects]],
            [[], [("g/new.md", ABSENT, hashlib.sha256(b"# New\n").hexdigest(), b"# New\n"),
                  ("g/r.md", R, hashlib.sha256(b"# Routes\n- g/new.md\n").hexdigest(), b"# Routes\n- g/new.md\n")]])
    effects, problems = planned(item({"type": "edit", "target": "g/a.md#One", "before_state_sha256": A,
                                      "anchor": "first body", "content": "1"},
                                     {"type": "edit", "target": "g/a.md#Two", "before_state_sha256": A,
                                      "anchor": "second body", "content": "2"}))
    control("two operations on one file chain: each is held to the state the proposal read, and the second "
            "starts where the first ended",
            [problems, len(effects), effects[0]["after"] == effects[1]["before"],
             effects[1]["data"] == doc.replace("first body", "1").replace("second body", "2").encode()],
            [[], 2, True, True])
    control("a file that moved since the proposal was written is refused, not patched",
            codes(planned(item({"type": "edit", "target": "g/a.md", "before_state_sha256": B_, "content": "x"}))[1]),
            ["APPLY_BEFORE_MISMATCH"])
    control("each type's own refusal, by name",
            [codes(planned(item(op))[1]) for op in (
                {"type": "create", "target": "g/a.md", "before_state_sha256": A, "content": "x"},
                {"type": "create", "target": "g/n.md#H", "before_state_sha256": ABSENT, "content": "x"},
                {"type": "edit", "target": "g/n.md", "before_state_sha256": ABSENT, "content": "x"},
                {"type": "edit", "target": "g/a.md", "before_state_sha256": A, "diff": "@@"},
                {"type": "edit", "target": "g/a.md", "before_state_sha256": A},
                {"type": "delete", "target": "g/n.md", "before_state_sha256": ABSENT},
                {"type": "route", "target": "g/n.md", "before_state_sha256": ABSENT, "entry": "x"},
                {"type": "patch", "target": "g/a.md", "before_state_sha256": A},
                {"type": "edit", "target": "", "before_state_sha256": A, "content": "x"})],
            [["CREATE_TARGET_PRESENT"], ["CREATE_WITH_PLACE"], ["EDIT_TARGET_ABSENT"], ["OPERATION_NOT_APPLICABLE"],
             ["CONTENT_ABSENT"], ["DELETE_TARGET_ABSENT"], ["ROUTE_TARGET_ABSENT"], ["OPERATION_UNKNOWN"],
             ["TARGET_ABSENT"]])
    merge = {"type": "merge", "target": "g/a.md#One", "before_state_sha256": A, "content": "## One\n\nmerged\n\n",
             "units": ["g/a.md#One", "g/a.md#Two", "g/b.md"], "unit_states": [{"unit": "g/b.md", "state": B_}]}
    effects, problems = planned(item(merge))
    control("a merge removes its units - a section, a whole file - and leaves the target with the text; the unit "
            "that is the target is replaced, not removed",
            [problems, [(e["path"], e["data"]) for e in effects][-1:],
             [(e["path"], e["after"]) for e in effects if e["path"] == "g/b.md"]],
            [[], [("g/a.md", b"# Guide\n\nintro\n\n## One\n\nmerged\n\n")], [("g/b.md", ABSENT)]])
    control("a merge unit in another file needs its own state, and that state is held to the file",
            [codes(planned(item({**merge, "unit_states": []}))[1]),
             codes(planned(item({**merge, "unit_states": [{"unit": "g/b.md", "state": A}]}))[1])],
            [["MERGE_UNIT_STATE_ABSENT"], ["APPLY_BEFORE_MISMATCH"]])
    control("a file that is not text is refused by name",
            codes(planned(item({"type": "edit", "target": "g/x.bin", "anchor": "a", "content": "b",
                                "before_state_sha256": hashlib.sha256(b"\xff\xfe").hexdigest()}),
                          held={**files, "g/x.bin": b"\xff\xfe"})[1]), ["APPLY_NOT_TEXT"])
    control("an operation that changes nothing is no effect",
            planned(item({"type": "edit", "target": "g/a.md", "before_state_sha256": A, "content": doc}))[0], [])

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
            control("a write whose result is not the planned after-state is refused before any done record",
                    said(lambda: tree.take({**effect("g/a.md", b"y"), "after": B_})), "APPLY_AFTER_MISMATCH")
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
            control("the stage's record holds the plan, the journal and apply.json",
                    [rec.get("status"), sorted(o["artifact"] for o in rec.get("outputs") or [])],
                    ["complete", sorted([PLAN, JOURNAL, OUTPUT])])
            again = refusal(lambda: kept.append(run(run_dir)))
            control("a second apply writes nothing: every write is the journal's already",
                    [again, (kept[-1]["counts"] if kept else None), tree_of(checkout)],
                    ["", {"items": 2, "effects": 2, "applied": 0, "done_before": 2, "files": 2}, ["claude/guides/g.md"]])
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
