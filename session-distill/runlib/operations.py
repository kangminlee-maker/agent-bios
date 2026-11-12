#!/usr/bin/env python3
"""What an operation does to a file's text: the one contract S7's check and S11's plan both read.

§7.3 names five operation types and the packet lists their fields; this module says what each does
to BYTES (lead decision D-20261113-1e6983). It is pure: text in, text out, no file opened. S11
(`stage_apply.py`) plans with it and S7's live check asks it whether a proposal's operations apply
to the checkout as it is, so a model learns in its one retry what S11 would have refused after the
owner approved.

    target      `path` or `path#heading`. The heading names one ATX heading of the file, by its
                title with or without its `#` marks; it must occur exactly once outside fenced code.
                Its SECTION runs from the heading's line to the next heading of the same or a higher
                level, or to the end of the file.
    create      the file is absent; it becomes `content`.
    edit        with `anchor`: that exact text occurs once in the section (or the file), counting
                overlapping occurrences, and is replaced by `content`. With a heading and no anchor:
                the section is replaced by `content`, which must end its own last line when more of
                the file follows (nothing is added to it). With neither: the file becomes `content`.
                A `diff` is not applied.
    delete      with `anchor`: that text is removed. With a heading: the section. With neither: the
                file.
    merge       each unit is removed (its section, or its file), except a unit that IS the target;
                then the target takes `content` exactly as an edit does, or is created.
    route       `entry` is appended as one line to the section or the file, with the file's own line
                ending; an entry already there is refused.

Headings and fences are read as CommonMark reads them, so a section is what a reader sees: an ATX
heading may be indented up to three spaces and may close with `#`s after a space; a fence opens with
three or more backticks or tildes and closes only with a line of the same character, at least as
long, and nothing after it; a line ending `\\r\\n` is a line.

Every refusal has its own code, and the text is never changed except where the operation names.

    operations.py --self-test
"""
import hashlib
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runlib import targets  # noqa: E402
from runlib.records import Refused  # noqa: E402

ABSENT = "absent"
TYPES = ("create", "edit", "delete", "merge", "route")
ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
CLOSING = re.compile(r"^(.*?)(?:^|[ \t]+)#+$")
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def sha_of(data):
    return ABSENT if data is None else hashlib.sha256(data).hexdigest()


def split_target(target):
    """`(path identity, heading | None)` of a target or a unit: `path` or `path#heading`."""
    heading = str(target or "").partition("#")[2]
    return targets.identity(targets.file_of(target or "")), (heading.strip() or None)


def _line(raw):
    return raw[:-1] if raw.endswith("\r") else raw


def _title(text):
    held = CLOSING.match(text or "")
    return (held.group(1) if held else (text or "")).strip()


def headings(text):
    """`[(line index, level, title)]` of the ATX headings of `text` outside fenced code."""
    out, fence = [], None
    for index, raw in enumerate(text.split("\n")):
        line = _line(raw)
        if fence:
            closing = re.match(r"^ {0,3}(" + re.escape(fence[0]) + "{" + str(len(fence)) + r",})[ \t]*$", line)
            if closing:
                fence = None
            continue
        opened = FENCE_OPEN.match(line)
        if opened and not (opened.group(1)[0] == "`" and "`" in opened.group(2)):
            fence = opened.group(1)
            continue
        held = ATX.match(line)
        if held:
            out.append((index, len(held.group(1)), _title(held.group(2))))
    return out


def heading_key(heading):
    """`(level | None, title)` of a heading as a target names it: with its marks, or its title alone."""
    held = re.match(r"^(#{1,6})[ \t]+(.*)$", heading.strip())
    return (len(held.group(1)), _title(held.group(2))) if held else (None, _title(heading))


def section_span(text, heading, who):
    """`(start, end)` character offsets of the one section `heading` names, or Refused by name."""
    level, title = heading_key(heading)
    held = headings(text)
    found = [(i, lvl) for i, lvl, name in held if name == title and level in (None, lvl)]
    if not found:
        raise Refused(f"HEADING_ABSENT {who}: the file holds no heading {heading!r} outside fenced code")
    if len(found) > 1:
        raise Refused(f"HEADING_AMBIGUOUS {who}: the file holds {len(found)} headings {heading!r}, and a "
                      f"section is named by one")
    index, lvl = found[0]
    after = next((i for i, other, _name in held if i > index and other <= lvl), None)
    lines = text.split("\n")
    start = sum(len(line) + 1 for line in lines[:index])
    end = len(text) if after is None else sum(len(line) + 1 for line in lines[:after])
    return start, min(end, len(text))


def _scope(text, heading, who):
    return section_span(text, heading, who) if heading else (0, len(text))


def _anchor_at(text, span, anchor, who):
    start, end = span
    first = text.find(anchor, start, end)
    where = "the section" if (start, end) != (0, len(text)) else "the file"
    if first < 0:
        raise Refused(f"ANCHOR_ABSENT {who}: the anchor does not occur in {where}")
    if text.find(anchor, first + 1, end) >= 0:          # an overlapping second occurrence is a second one
        raise Refused(f"ANCHOR_AMBIGUOUS {who}: the anchor occurs more than once in {where}, and a place is "
                      f"named by one")
    return first


def _content(operation, who):
    held = operation.get("content")
    if not isinstance(held, str):
        if operation.get("diff") is not None:
            raise Refused(f"OPERATION_NOT_APPLICABLE {who}: it carries a diff and no content, and release 1 "
                          f"places text and applies no patch")
        raise Refused(f"CONTENT_ABSENT {who}: a {operation.get('type')} names the text it writes in `content`")
    return held


def placed(text, heading, anchor, content, who):
    """`text` with `content` placed: over the anchor, over the section, or as the whole. Nothing is
    added to `content`: a section's replacement that would run into the text after it is refused."""
    if anchor:
        at = _anchor_at(text, _scope(text, heading, who), anchor, who)
        return text[:at] + content + text[at + len(anchor):]
    if heading:
        start, end = section_span(text, heading, who)
        if content and end < len(text) and not content.endswith("\n"):
            raise Refused(f"SECTION_CONTENT_UNTERMINATED {who}: more of the file follows the section, and the "
                          f"content replacing it does not end its last line; end it with a newline")
        return text[:start] + content + text[end:]
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
    """`text` with `entry` appended as one line to the section or the file, in the file's line ending."""
    if not isinstance(entry, str) or not entry.strip() or "\n" in entry.strip("\r\n") or "\r" in entry.strip("\r\n"):
        raise Refused(f"ROUTE_ENTRY_INVALID {who}: a route's `entry` is one non-empty line")
    line = entry.strip("\r\n")
    start, end = _scope(text, heading, who)
    if line in [_line(held) for held in text[start:end].split("\n")]:
        raise Refused(f"ROUTE_ENTRY_PRESENT {who}: that entry is already there")
    ending = "\r\n" if "\r\n" in text else "\n"
    body = text[start:end]
    joint = "" if not body or body.endswith("\n") else ending
    return text[:end] + joint + line + ending + text[end:]


class Tree:
    """Files as a plan sees them: read once from `read(path)` (bytes, or None when absent), then
    changed in memory only."""

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


def _same_place(text, path, heading, unit_path, unit_heading, who):
    """Whether a merge's unit names the very place its target does, however each is spelled."""
    if unit_path != path:
        return False
    if not heading or not unit_heading:
        return heading == unit_heading
    if text is None:
        return heading_key(heading)[1] == heading_key(unit_heading)[1]
    return section_span(text, heading, who) == section_span(text, unit_heading, who)


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
            if _same_place(tree.text(path, who), path, heading, unit_path, unit_heading, who):
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
        if text is None:
            if anchor:
                raise Refused(f"ANCHOR_ABSENT {who}: {path} is not there for the anchor to occur in")
            put(path, content)
        else:
            put(path, placed(text, heading, anchor, content, who))
    return touched


def plan_of(items, read):
    """`(effects, problems)` for items in their order: every operation applied in memory to the
    files `read` gives. An effect is one file's change by one operation — `item_id`, `approval_id`,
    `operation` (its index), `type`, `path`, `before`, `after` and the bytes it leaves (`data`, None
    for a removal). Any problem and nothing is to be written."""
    tree, effects, problems = Tree(read), [], []
    for item in items:
        for index, operation in enumerate(item.get("operations") or []):
            who = f"{item['item_id']} operations[{index}]"
            before = {}
            try:
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
                effects.append({"item_id": item["item_id"], "approval_id": item.get("approval_id"),
                                "operation": index, "type": operation.get("type"), "path": path,
                                "before": before[path], "after": sha_of(data), "data": data})
                before[path] = sha_of(data)
    return [e for e in effects if e["before"] != e["after"]], problems


def applicability_problems(operations, read, who="the proposal"):
    """What S11 would refuse of one proposal's operations against the files as `read` gives them
    now: the question S7's check asks, so the refusal reaches the model and not the owner."""
    return plan_of([{"item_id": who, "approval_id": None, "operations": list(operations or [])}], read)[1]


# ---- self-test ---------------------------------------------------------------------------------------

def self_test():
    failures, ran = [], []

    def control(name, got, want):
        ran.append(name)
        if got != want:
            failures.append((name, f"expected {want!r}, got {got!r}"[:900]))

    def said(call):
        try:
            call()
        except Refused as exc:
            return (str(exc).split() or [""])[0]
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return f"RAISED {type(exc).__name__}: {exc}"
        return ""

    doc = "# Guide\n\nintro\n\n## One\n\nfirst body\n\n### Deep\n\ndeep body\n\n## Two\n\nsecond body\n"

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
    # the round-1 review's boundary cases
    control("an ATX heading indented up to three spaces is a heading, so a section ends at it",
            [headings("# A\nx\n  # B\ny\n"), removed("# A\nx\n  # B\ny\n", "A", None, "t")],
            [[(0, 1, "A"), (2, 1, "B")], "  # B\ny\n"])
    control("four spaces of indent is code, not a heading",
            [h[2] for h in headings("# A\n    # code\n")], ["A"])
    control("a fence closes only with its own character, at least as long, and nothing after it",
            [[h[2] for h in headings("````\n```\n# fake\n````\n# real\n")],
             [h[2] for h in headings("```\n``` not a close\n# still code\n```\n# real\n")],
             [h[2] for h in headings("~~~\n```\n# still code\n~~~\n# real\n")]],
            [["real"], ["real"], ["real"]])
    control("a backtick fence whose info string holds a backtick is not a fence",
            [h[2] for h in headings("``` a`b\n# heading\n")], ["heading"])
    control("a CRLF file's headings are headings, and its section offsets are the file's own",
            [headings("# A\r\nx\r\n# B\r\n"), "# A\r\nx\r\n# B\r\n"[slice(*section_span("# A\r\nx\r\n# B\r\n", "A", "t"))]],
            [[(0, 1, "A"), (2, 1, "B")], "# A\r\nx\r\n"])
    control("closing marks belong to the heading only after a space: `# C#` is titled C#, `# C #` is titled C",
            [headings("# C#\n")[0][2], headings("# C #\n")[0][2], headings("# C ##  \n")[0][2], headings("#\n")[0][2]],
            ["C#", "C", "C", ""])
    control("an edit with a heading replaces the section with the content exactly",
            placed(doc, "Two", None, "## Two\n\nnew", "t"), doc.replace("## Two\n\nsecond body\n", "## Two\n\nnew"))
    control("content replacing a section in the middle must end its own last line: nothing is added to it",
            [said(lambda: placed(doc, "### Deep", None, "### Deep\n\nX", "t")),
             placed(doc, "### Deep", None, "### Deep\n\nX\n", "t"), placed(doc, "### Deep", None, "", "t")],
            ["SECTION_CONTENT_UNTERMINATED", doc.replace("### Deep\n\ndeep body\n\n", "### Deep\n\nX\n"),
             doc.replace("### Deep\n\ndeep body\n\n", "")])
    control("an edit with an anchor replaces that text once, inside the section it names",
            placed(doc, "One", "first body", "FIRST", "t"), doc.replace("first body", "FIRST"))
    control("an anchor outside the named section is absent, and one occurring twice is ambiguous",
            [said(lambda: placed(doc, "One", "second body", "x", "t")),
             said(lambda: placed(doc, None, "body", "x", "t"))], ["ANCHOR_ABSENT", "ANCHOR_AMBIGUOUS"])
    control("an anchor whose occurrences overlap occurs twice",
            [said(lambda: placed("aaa", None, "aa", "X", "t")), said(lambda: removed("aaa", None, "aa", "t")),
             placed("aab", None, "aa", "X", "t")], ["ANCHOR_AMBIGUOUS", "ANCHOR_AMBIGUOUS", "Xb"])
    control("an edit with neither is the whole file", placed(doc, None, None, "whole\n", "t"), "whole\n")
    control("a delete removes the anchor, the section, or - with neither - the file",
            [removed(doc, None, "intro\n\n", "t"), removed(doc, "Two", None, "t"), removed(doc, None, None, "t")],
            [doc.replace("intro\n\n", ""), doc.replace("## Two\n\nsecond body\n", ""), None])
    control("a route appends one line to the section, to the file when no heading is named, and in a CRLF file "
            "with its ending",
            [routed(doc, "One", "- [x](x.md)", "t"), routed("a\nb", None, "c", "t"), routed("a\r\nb\r\n", None, "c", "t")],
            [doc.replace("deep body\n\n", "deep body\n\n- [x](x.md)\n"), "a\nb\nc\n", "a\r\nb\r\nc\r\n"])
    control("a route already there, an empty one and a two-line one are refused by name",
            [said(lambda: routed("a\nb\n", None, "b", "t")), said(lambda: routed("a\r\nb\r\n", None, "b", "t")),
             said(lambda: routed(doc, None, " ", "t")), said(lambda: routed(doc, None, "a\nb", "t"))],
            ["ROUTE_ENTRY_PRESENT", "ROUTE_ENTRY_PRESENT", "ROUTE_ENTRY_INVALID", "ROUTE_ENTRY_INVALID"])
    control("a target is its path and its heading, and the path is the file's one identity",
            [split_target("g//a.md#One"), split_target("./g/a.md"), split_target("")],
            [("g/a.md", "One"), ("g/a.md", None), (None, None)])

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
            [problems, len(effects), [e["after"] for e in effects][:1] == [e["before"] for e in effects][1:],
             [e["data"] for e in effects][-1:] == [doc.replace("first body", "1").replace("second body", "2").encode()]],
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
    spelled = planned(item({**merge, "units": ["g/a.md### One", "g/a.md#Two", "g/b.md"]}))
    control("the unit that is the target is recognised however its heading is spelled",
            [spelled[1], [(e["path"], e["data"]) for e in spelled[0]][-1:]],
            [[], [("g/a.md", b"# Guide\n\nintro\n\n## One\n\nmerged\n\n")]])
    anchored = planned(item({"type": "merge", "target": "g/b.md", "before_state_sha256": B_, "anchor": "body of b",
                             "content": "NEW", "units": ["g/a.md#Two"],
                             "unit_states": [{"unit": "g/a.md#Two", "state": A}]}))
    control("a merge places its content as an edit does: over the anchor, and not as the whole file",
            [anchored[1], [(e["path"], e["data"]) for e in anchored[0]][-1:]], [[], [("g/b.md", b"# B\n\nNEW\n")]])
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
    control("the applicability question S7 asks is the plan's own answer",
            [codes(applicability_problems([{"type": "edit", "target": "g/a.md#Nine", "before_state_sha256": A,
                                            "content": "x\n"}], files.get)),
             applicability_problems([{"type": "edit", "target": "g/a.md#Two", "before_state_sha256": A,
                                      "content": "## Two\n\nx\n"}], files.get)],
            [["HEADING_ABSENT"], []])

    if failures:
        for name, detail in failures:
            print(f"operations --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"operations --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"operations --self-test: OK ({len(ran)} controls: sections and fences as CommonMark reads them, each "
          f"operation type placed and refused by name, nothing added to the content, the plan held to the files' "
          f"states, and the merge's units and target)")
    return 0


def main(argv):
    if argv[1:] == ["--self-test"]:
        return self_test()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
