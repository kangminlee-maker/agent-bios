#!/usr/bin/env python3
"""The grammar of the lines the owner writes into a review's decision copy and into a confirmation file (plan WP-20
K1; design §10.1, §10.3; settled S-11; lead decision E1).

A render (`review.ko.v<n>.md`, `confirm.ko.v<n>.md`) is immutable. Beside it the renderer writes a copy (`copy_of`):
the render's bytes under one header line that names the render and its sha256. The owner edits the copy, and only
inside its owner blocks. A block opens with `<!-- owner-block review item=<item id> sha=<item sha> -->` (one per
review row, `review_block`) or `<!-- owner-block confirm set=<set sha> -->` (one per confirmation file,
`confirm_block`) and closes with `<!-- /owner-block -->`. Every byte outside the blocks, the markers included, must
equal the render's: an edit there is refused by its line number (EDIT_OUTSIDE_EDITABLE), and the same text inside a
block's note is accepted. What is editable is decided by position, never by what a line looks like, so a payload
line that happens to begin with `결정:` is as fixed as any other.

Inside a review block each non-blank line is one of

    결정: <verb>                   승인 | 수정 | 보류 | 기각 | 판정, or empty for undecided; 수정 may name
                                   S7b's alternative as `수정 대안 <id>`
    메모: <text>                   the note; repeatable, joined by newlines
    판정 <label>: A | B | <value>  one disputed judgment: judge A's side, judge B's, or the owner's own value
    keep 해제: <record id> <grounds>  releases a keep record the proposal reduces or merges over

and inside a confirmation block

    확인: 확정 | 반려               confirm the final set or return it, or empty for undecided
    메모: <text>

A line that is none of these, a second `결정:` or `확인:` line, a verb with words after it, a filled `판정` line under
another verb, a release under anything but 승인: each is refused by its line number, never read as the nearest thing
it resembles (the LLM/capability rule). The colon may be ASCII or full-width, and an editable line is read after
Unicode NFC, so an editor's normalization of Hangul does not change what it says.

With a `spec` - the current rows, from the stage that renders and parses them - each block is also held to its row:
an anchor whose sha is no longer the item's makes the item `stale` (DECISION_STALE: decided again in a new review
version, never applied from this one), and a judgment label or value the row does not carry, an alternative S7b did
not offer, a keep record the proposal does not override, a disputed row approved without adjudication, and an approval
over a keep record nobody released are each refused by line.

Named owner_lines rather than the plan's `decisions.py`: the lexicon's concept slug `decision` homes this repo's own
decision record under `decisions/` (`gates/check-lexicon.py` judges every path that carries it).

    owner_lines.py --self-test
"""
import hashlib
import pathlib
import re
import sys
import unicodedata

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib.records import Refused  # noqa: E402

# §10.1's sentence, copied once and held to VERBS by the self-test, so neither changes alone.
DESIGN_10_1 = ("Per row the owner writes `결정:` followed by one of `승인`, `수정`, `보류`, `기각`, `판정`, with a "
               "note.")
VERBS = {"승인": "approve", "수정": "revise", "보류": "defer", "기각": "reject", "판정": "adjudicate"}
CONFIRM_VERBS = {"확정": "confirm", "반려": "return"}   # lead decision E1: one 확인 line per confirmation file
ALTERNATIVE_WORD = "대안"
JUDGES = ("A", "B")
FIELDS = {"review": ("item", "sha"), "confirm": ("set",)}
CLOSE = "<!-- /owner-block -->"
_VALUE = r"[^\s=<>]+"
OPEN = re.compile(rf"^<!-- owner-block (review|confirm)((?: [a-z]+={_VALUE})+) -->$")
LOOKS_LIKE_MARKER = re.compile(r"^\s*<!--\s*/?\s*owner-(?:block|copy)\b")
HEADER = re.compile(r"^<!-- owner-copy of=(\S+) sha256=([0-9a-f]{64}) -->$")
TOKEN = re.compile(rf"^{_VALUE}$")
_LABEL = r"[0-9A-Za-z_.\-]+"
LABEL = re.compile(rf"^{_LABEL}$")
_COLON = "[:：]"
DECISION_LINE = re.compile(rf"^결정\s*{_COLON}(.*)$")
NOTE_LINE = re.compile(rf"^메모\s*{_COLON}(.*)$")
JUDGMENT_LINE = re.compile(rf"^판정\s+({_LABEL})\s*{_COLON}(.*)$")
KEEP_LINE = re.compile(rf"^(?i:keep)\s*해제\s*{_COLON}(.*)$")
CONFIRM_LINE = re.compile(rf"^확인\s*{_COLON}(.*)$")
GROUNDS_LEAD = "—–-:： "   # a dash or colon the owner may put between a record id and its grounds


def owner_shaped(line):
    """Whether `line` reads, as the parser reads an editable line (NFC, stripped), as an owner line or a block marker.
    The parser reads by position, so such a line outside a block decides nothing; a renderer uses this to keep text it
    did not write from standing where the owner would read a decision (`stage_render.page_problems`)."""
    text = unicodedata.normalize("NFC", str(line)).strip()
    return bool(LOOKS_LIKE_MARKER.match(text) or any(p.match(text) for p in (DECISION_LINE, NOTE_LINE, JUDGMENT_LINE,
                                                                             KEEP_LINE, CONFIRM_LINE)))


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _token(name, value):
    if not isinstance(value, str) or not TOKEN.match(value):
        raise Refused(f"BLOCK_ARGUMENT_INVALID {name}: {value!r} is not one token without whitespace, '=', '<' or '>'")
    return value


def _shown(word):
    return repr(word[:24])


def review_block(item_id, item_sha, labels=()):
    """One review row's owner block as a render writes it: its markers, an empty `결정:` and `메모:`, and one empty
    `판정 <label>:` per disputed judgment the row carries, in the order given."""
    labels = list(labels)
    for label in labels:
        if not isinstance(label, str) or not LABEL.match(label):
            raise Refused(f"BLOCK_ARGUMENT_INVALID label: {label!r} is not letters, digits, '_', '.' or '-'")
    if len(set(labels)) != len(labels):
        raise Refused(f"BLOCK_ARGUMENT_INVALID labels: {labels} repeat a label")
    return [f"<!-- owner-block review item={_token('item', item_id)} sha={_token('sha', item_sha)} -->",
            "결정:", "메모:", *[f"판정 {label}:" for label in labels], CLOSE]


def confirm_block(set_sha):
    """A confirmation file's one owner block as a render writes it."""
    return [f"<!-- owner-block confirm set={_token('set', set_sha)} -->", "확인:", "메모:", CLOSE]


def segments(lines, first=1):
    """`(fixed, blocks, problems)` over a text's lines numbered from `first`: `fixed` holds `(line, text)` of every line
    outside a block and of every marker; `blocks` each block's `{kind, fields, line, lines}`; `problems` the breaks of
    the block structure, by line."""
    fixed, blocks, problems, held = [], [], [], None
    for n, text in enumerate(lines, first):
        opened = OPEN.match(text)
        if held is None:
            fixed.append((n, text))
            if opened:
                pairs = opened.group(2).split()
                fields = dict(pair.split("=", 1) for pair in pairs)
                held = {"kind": opened.group(1), "fields": fields, "line": n, "lines": []}
                if sorted(fields) != sorted(FIELDS[held["kind"]]) or len(pairs) != len(fields):
                    problems.append(f"BLOCK_MALFORMED line {n}: a {held['kind']} block names {sorted(fields)}, not "
                                    f"{list(FIELDS[held['kind']])}")
            elif text == CLOSE:
                problems.append(f"BLOCK_UNOPENED line {n}: a block end with no block open")
            elif LOOKS_LIKE_MARKER.match(text):
                problems.append(f"BLOCK_MALFORMED line {n}: shaped like an owner-block marker but not one as the "
                                "render writes it")
        elif text == CLOSE:
            fixed.append((n, text))
            blocks.append(held)
            held = None
        elif opened or LOOKS_LIKE_MARKER.match(text):
            fixed.append((n, text))
            problems.append(f"BLOCK_NESTED line {n}: a block marker inside the block opened at line {held['line']}")
        else:
            held["lines"].append((n, text))
    if held is not None:
        problems.append(f"BLOCK_UNTERMINATED line {held['line']}: the block opened here has no end marker")
    return fixed, blocks, problems


def render_problems(text):
    """What makes `text` no render a copy can be made of, by name: bytes other than LF-terminated UTF-8, a copy's
    header, a broken block structure, review and confirmation blocks in one file, an item with two blocks, a second
    confirmation block, and a block other than `review_block` or `confirm_block` writes."""
    if not isinstance(text, str):
        return [f"RENDER_NOT_TEXT: a render is text, not {type(text).__name__}"]
    problems = []
    if text.startswith("﻿") or "\r" in text:
        problems.append("RENDER_BYTES_INVALID: a render is LF-terminated UTF-8 with no byte-order mark and no carriage "
                        "return")
    if text.split("\n", 1)[0].startswith("<!-- owner-copy"):
        problems.append("RENDER_IS_COPY line 1: the text carries a copy's header, so it is a copy, not a render")
    _fixed, blocks, found = segments(text.split("\n"))
    problems += found
    if len({b["kind"] for b in blocks}) > 1:
        problems.append("FILE_KINDS_MIXED: a render holds review blocks or one confirmation block, never both")
    seen = {}
    for b in blocks:
        if b["kind"] == "review" and "item" in b["fields"]:
            item = b["fields"]["item"]
            if item in seen:
                problems.append(f"ITEM_TWICE line {b['line']}: item {item} has its block at line {seen[item]} already")
            seen.setdefault(item, b["line"])
        interior = [t for _n, t in b["lines"]]
        labels = [m.group(1) for m in (JUDGMENT_LINE.match(t) for t in interior[2:]) if m]
        want = (["결정:", "메모:", *[f"판정 {label}:" for label in labels]] if b["kind"] == "review"
                else ["확인:", "메모:"])
        if interior != want or len(set(labels)) != len(labels):
            problems.append(f"RENDER_BLOCK_INVALID line {b['line']}: the block is not as "
                            f"{'review_block' if b['kind'] == 'review' else 'confirm_block'} writes it (empty lines only)")
    confirms = [b for b in blocks if b["kind"] == "confirm"]
    if len(confirms) > 1:
        problems.append(f"CONFIRM_BLOCK_TWICE line {confirms[1]['line']}: a confirmation file has one block")
    return problems


def copy_of(render_text, render_name):
    """The owner's copy of a render: one header line naming `render_name` and the render's sha256, then the render's
    bytes unchanged. A render with any `render_problems` is refused."""
    found = render_problems(render_text)
    if found:
        raise Refused("RENDER_INVALID " + "\n".join(found))
    return f"<!-- owner-copy of={_token('render name', render_name)} sha256={sha256_text(render_text)} -->\n" + render_text


def first_difference(render_fixed, copy_fixed):
    """The first fixed line where the copy departs from the render, by the copy's line number, or None."""
    for (rn, rt), (cn, ct) in zip(render_fixed, copy_fixed):
        if rt == ct:
            continue
        if unicodedata.normalize("NFC", rt) == unicodedata.normalize("NFC", ct):
            return (f"NORMALIZATION_CHANGED line {cn}: the line's Hangul is in another Unicode normalization than the "
                    f"render's line {rn}; save the copy without re-normalizing it")
        how = "only its trailing whitespace" if rt.rstrip() == ct.rstrip() else "its text"
        return (f"EDIT_OUTSIDE_EDITABLE line {cn}: {how} differs from the render's line {rn}, and only lines inside "
                "an owner block may change")
    if len(copy_fixed) > len(render_fixed):
        return (f"EDIT_OUTSIDE_EDITABLE line {copy_fixed[len(render_fixed)][0]}: a line the render does not have, "
                "outside every owner block")
    if len(copy_fixed) < len(render_fixed):
        rn, rt = render_fixed[len(copy_fixed)]
        last = copy_fixed[-1][0] if copy_fixed else 1
        if rt == "" and len(render_fixed) == len(copy_fixed) + 1:
            return f"EDIT_OUTSIDE_EDITABLE line {last}: the copy lacks the render's final newline"
        return f"EDIT_OUTSIDE_EDITABLE line {last + 1}: the copy ends where the render's line {rn} continues"
    return None


def _said(verb):
    return f"says {verb}" if verb else "is empty"


def review_rules(held, problems):
    """The rules a review block's lines obey among themselves, whatever the row."""
    verb, at = held["verb"], held["decision_line"]
    filled = [j for j in held["judgments"] if j["choice"] is not None]
    if verb != "판정" and filled:
        problems.append(f"ADJUDICATION_WITHOUT_VERB line {filled[0]['line']}: a 판정 value is filled and the 결정 line "
                        f"{_said(verb)}; write 결정: 판정, or empty the value")
    if verb == "판정":
        if not held["judgments"]:
            problems.append(f"ADJUDICATION_INCOMPLETE line {at}: 결정: 판정 resolves no 판정 line")
        for j in held["judgments"]:
            if j["choice"] is None:
                problems.append(f"ADJUDICATION_INCOMPLETE line {j['line']}: 판정 {j['label']} has no value (A, B or "
                                "the owner's own)")
        if not held["note"]:
            problems.append(f"NOTE_REQUIRED line {at}: 판정 records its rationale in a 메모 line")
    if verb == "수정" and held["alternative"] is None and not held["note"]:
        problems.append(f"NOTE_REQUIRED line {at}: 수정 returns the item to S7 with a 메모 line, or names S7b's "
                        f"alternative as 수정 {ALTERNATIVE_WORD} <id>")
    if verb != "승인":
        for k in held["keep_releases"]:
            problems.append(f"KEEP_RELEASE_UNUSED line {k['line']}: keep 해제 releases a keep record for an approval, "
                            f"and the 결정 line {_said(verb)}")


def read_review(block, problems):
    """One review block's lines, read: `{item_id, item_sha, line, state, decision, verb, alternative, note, judgments,
    keep_releases, decision_line}`; every line it refuses goes to `problems` by its number."""
    held = {"item_id": block["fields"].get("item"), "item_sha": block["fields"].get("sha"), "line": block["line"],
            "state": "undecided", "decision": None, "verb": None, "alternative": None, "note": "",
            "judgments": [], "keep_releases": [], "decision_line": None}
    notes = []
    for n, raw in block["lines"]:
        text = unicodedata.normalize("NFC", raw).strip()
        if not text:
            continue
        hit = DECISION_LINE.match(text)
        if hit:
            if held["decision_line"] is not None:
                problems.append(f"DECISION_TWICE line {n}: the block has its 결정 line at line {held['decision_line']}")
                continue
            held["decision_line"] = n
            words = hit.group(1).split()
            if not words:
                continue
            verb, rest = words[0], words[1:]
            if verb not in VERBS:
                problems.append(f"DECISION_VERB_UNKNOWN line {n}: {_shown(verb)} is not one of {', '.join(VERBS)}")
                continue
            if verb == "수정" and rest[:1] == [ALTERNATIVE_WORD]:
                if len(rest) != 2:
                    problems.append(f"DECISION_ARGUMENT_INVALID line {n}: 수정 {ALTERNATIVE_WORD} takes one "
                                    "alternative id and nothing after it")
                    continue
                held["alternative"] = rest[1]
            elif rest:
                problems.append(f"DECISION_ARGUMENT_INVALID line {n}: {verb} takes no words after it"
                                + (f" but {ALTERNATIVE_WORD} <id>" if verb == "수정" else ""))
                continue
            held.update(verb=verb, decision=VERBS[verb], state="decided")
            continue
        hit = NOTE_LINE.match(text)
        if hit:
            notes.append(hit.group(1).strip())
            continue
        hit = JUDGMENT_LINE.match(text)
        if hit:
            label, value = hit.group(1), hit.group(2).strip()
            earlier = next((j for j in held["judgments"] if j["label"] == label), None)
            if earlier is not None:
                problems.append(f"JUDGMENT_TWICE line {n}: 판정 {label} is at line {earlier['line']} already")
                continue
            choice = None if not value else value if value in JUDGES else "own"
            held["judgments"].append({"label": label, "choice": choice, "value": value if choice == "own" else None,
                                      "line": n})
            continue
        hit = KEEP_LINE.match(text)
        if hit:
            words = hit.group(1).strip().split(None, 1)
            if not words:
                continue
            record = words[0]
            grounds = words[1].lstrip(GROUNDS_LEAD).strip() if len(words) > 1 else ""
            earlier = next((k for k in held["keep_releases"] if k["record_id"] == record), None)
            if earlier is not None:
                problems.append(f"KEEP_RELEASE_TWICE line {n}: keep 해제 {record} is at line {earlier['line']} already")
                continue
            if not grounds:
                problems.append(f"KEEP_RELEASE_GROUNDLESS line {n}: keep 해제 {record} needs its grounds after the "
                                "record id")
                continue
            held["keep_releases"].append({"record_id": record, "grounds": grounds, "line": n})
            continue
        if CONFIRM_LINE.match(text):
            problems.append(f"LINE_NOT_EDITABLE line {n}: a 확인 line belongs to a confirmation file, not a review row")
            continue
        problems.append(f"LINE_NOT_EDITABLE line {n}: inside a review block a line is 결정, 메모, 판정 <label> or "
                        "keep 해제; write a note as a 메모: line")
    held["note"] = "\n".join(x for x in notes if x)
    review_rules(held, problems)
    return held


def read_confirm(block, problems, confirm_set=None):
    """A confirmation block's lines, read: `{set_sha, line, state, decision, verb, note, confirm_line}`. With
    `confirm_set`, a block confirming another set is `stale` (CONFIRM_STALE)."""
    held = {"set_sha": block["fields"].get("set"), "line": block["line"], "state": "undecided", "decision": None,
            "verb": None, "note": "", "confirm_line": None}
    notes = []
    for n, raw in block["lines"]:
        text = unicodedata.normalize("NFC", raw).strip()
        if not text:
            continue
        hit = CONFIRM_LINE.match(text)
        if hit:
            if held["confirm_line"] is not None:
                problems.append(f"CONFIRM_TWICE line {n}: the block has its 확인 line at line {held['confirm_line']}")
                continue
            held["confirm_line"] = n
            words = hit.group(1).split()
            if not words:
                continue
            if len(words) != 1 or words[0] not in CONFIRM_VERBS:
                problems.append(f"CONFIRM_VERB_UNKNOWN line {n}: 확인 takes one of {', '.join(CONFIRM_VERBS)} and "
                                "nothing after it")
                continue
            held.update(verb=words[0], decision=CONFIRM_VERBS[words[0]], state="decided")
            continue
        hit = NOTE_LINE.match(text)
        if hit:
            notes.append(hit.group(1).strip())
            continue
        problems.append(f"LINE_NOT_EDITABLE line {n}: inside a confirmation block a line is 확인 or 메모")
    held["note"] = "\n".join(x for x in notes if x)
    if held["verb"] == "반려" and not held["note"]:
        problems.append(f"NOTE_REQUIRED line {held['confirm_line']}: 반려 says why in a 메모 line")
    if confirm_set is not None and held["set_sha"] != confirm_set:
        held["state"] = "stale"
        held["code"] = (f"CONFIRM_STALE line {held['line']}: the block confirms set {held['set_sha'][:12]}, and the "
                        f"final set is {confirm_set[:12]} now; it is confirmed again in a new confirmation file")
    return held


def spec_problems(spec):
    """What makes `spec` no set of current rows: it is the calling stage's, so a bad one is refused, not reported."""
    if not isinstance(spec, dict):
        return [f"SPEC_INVALID: the rows are a mapping of item id to row, not {type(spec).__name__}"]
    out = []
    for ident, row in spec.items():
        if not (isinstance(row, dict) and isinstance(row.get("item_sha"), str)
                and isinstance(row.get("judgments", {}), dict)
                and all(isinstance(v, list) for v in row.get("judgments", {}).values())
                and isinstance(row.get("alternatives", []), list) and isinstance(row.get("guarded_keeps", []), list)):
            out.append(f"SPEC_INVALID {ident}: a row is {{item_sha, judgments: {{label: [values]}}, alternatives, "
                       "guarded_keeps}")
    return out


def hold_to_spec(items, spec, problems):
    """Each read review block held to its current row. A changed row makes its item `stale` with DECISION_STALE and
    nothing else is judged of it, since its lines answered the row as it was rendered."""
    for item in items:
        row = spec.get(item["item_id"])
        if row is None:
            problems.append(f"ITEM_UNKNOWN line {item['line']}: item {item['item_id']} is not among the current rows")
            continue
        if item["item_sha"] != row["item_sha"]:
            item["state"] = "stale"
            item["code"] = (f"DECISION_STALE line {item['line']}: item {item['item_id']} changed after this render "
                            f"({item['item_sha'][:12]} rendered, {row['item_sha'][:12]} now); it is decided again in "
                            "a new review version and never applied from this one")
            continue
        labels = row.get("judgments") or {}
        verb, at = item["verb"], item["decision_line"]
        for j in item["judgments"]:
            if j["label"] not in labels:
                problems.append(f"JUDGMENT_UNKNOWN line {j['line']}: the row has no disputed judgment {j['label']}")
            elif j["choice"] == "own" and j["value"] not in labels[j["label"]]:
                problems.append(f"JUDGMENT_VALUE_INVALID line {j['line']}: 판정 {j['label']} takes A, B or one of "
                                f"{', '.join(labels[j['label']])}")
        if verb == "판정":
            if not labels:
                problems.append(f"DECISION_NOT_ALLOWED line {at}: the row has no disputed judgment to 판정")
            for label in sorted(set(labels) - {j["label"] for j in item["judgments"]}):
                problems.append(f"ADJUDICATION_INCOMPLETE line {at}: disputed judgment {label} has no 판정 line")
        if verb == "승인" and labels:
            problems.append(f"DISPUTE_UNRESOLVED line {at}: the row is disputed; 판정 each disputed judgment, or "
                            "보류 or 기각 it")
        if item["alternative"] is not None and item["alternative"] not in (row.get("alternatives") or []):
            problems.append(f"ALTERNATIVE_UNKNOWN line {at}: S7b offered no alternative {_shown(item['alternative'])}")
        guarded = row.get("guarded_keeps") or []
        for k in item["keep_releases"]:
            if k["record_id"] not in guarded:
                problems.append(f"KEEP_UNKNOWN line {k['line']}: the proposal overrides no keep record "
                                f"{_shown(k['record_id'])}")
        if verb == "승인":
            released = {k["record_id"] for k in item["keep_releases"]}
            for record in guarded:
                if record not in released:
                    problems.append(f"KEEP_GUARDED line {at}: the proposal reduces or merges over keep record {record}, "
                                    f"and approving it needs `keep 해제: {record} <grounds>`")
    listed = {i["item_id"] for i in items}
    for ident in sorted(set(spec) - listed):
        problems.append(f"ITEM_NOT_RENDERED {ident}: a current row with no block in this render")


def parse(render_text, copy_text, spec=None, render_name=None, confirm_set=None):
    """`(result, problems)` of the owner's copy of a render. `result` is None when the copy is not the render with only
    its blocks edited (the header, the bytes, the fixed lines); else `{render, render_sha256, items, confirm}`, the
    items in the render's order. `problems` empty means every line was read; any problem refuses the file."""
    found = render_problems(render_text)
    if found:
        return None, [f"RENDER_INVALID {p}" for p in found]
    if not isinstance(copy_text, str):
        return None, [f"COPY_NOT_TEXT: a copy is text, not {type(copy_text).__name__}"]
    if spec is not None and spec_problems(spec):
        raise Refused("\n".join(spec_problems(spec)))
    if copy_text.startswith("﻿"):
        return None, ["ENCODING_CHANGED line 1: the copy starts with a byte-order mark the render does not have; save "
                      "it as UTF-8 without one"]
    lines = copy_text.split("\n")
    for n, text in enumerate(lines, 1):
        if text.endswith("\r"):
            return None, [f"LINE_ENDINGS_CHANGED line {n}: the copy's lines end in CRLF where the render's end in LF; "
                          "save it with LF line endings"]
    head = HEADER.match(lines[0])
    if not head:
        return None, ["COPY_HEADER_MISSING line 1: the first line is not the header naming the render this copies"]
    sha = sha256_text(render_text)
    if head.group(2) != sha or (render_name is not None and head.group(1) != render_name):
        return None, [f"COPY_UNBOUND line 1: the copy names {head.group(1)} at {head.group(2)[:12]}, not "
                      f"{render_name or 'this render'} at {sha[:12]}"]
    render_fixed, _blocks, _found = segments(render_text.split("\n"))
    copy_fixed, blocks, found = segments(lines[1:], first=2)
    if found:
        return None, found
    differs = first_difference(render_fixed, copy_fixed)
    if differs:
        return None, [differs]
    problems = []
    result = {"render": head.group(1), "render_sha256": sha, "items": [], "confirm": None}
    for block in blocks:
        if block["kind"] == "review":
            result["items"].append(read_review(block, problems))
        else:
            result["confirm"] = read_confirm(block, problems, confirm_set)
    if spec is not None:
        hold_to_spec(result["items"], spec, problems)
    return result, problems


def require(render_text, copy_text, **kwargs):
    """`parse`'s result, or Refused naming every problem, the first line first."""
    result, problems = parse(render_text, copy_text, **kwargs)
    if problems:
        raise Refused("\n".join(problems))
    return result


def self_test():
    """Positive controls first; then each verb and line kind read; then one planted violation per rule, each named by
    its code and, where the rule is a line's, by the exact line. Every control builds its own copy from the fixture."""
    failures, ran, reporting = [], [], []

    def record(name):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}")
        ran.append(name)

    def control(name, got, want):
        record(name)
        if not isinstance(got, str):
            raise TypeError(f"CONTROL_GOT_NOT_STR {name}: {type(got).__name__}")
        if want not in got:
            failures.append((name, f"expected {want!r} in {got[:400]!r}"))

    def equal(name, got, want):
        record(name)
        if got != want:
            failures.append((name, f"expected {want!r}, got {got!r}"))

    def clean(name, problems):
        record(name)
        if not isinstance(problems, list):
            raise TypeError(f"CLEAN_PROBLEMS_NOT_LIST {name}: {type(problems).__name__}")
        if problems:
            failures.append((name, f"expected nothing, got {problems}"))

    def refusal(call):
        try:
            call()
        except Refused as exc:
            return str(exc)
        return ""

    name = "review.ko.v1.md"
    head = ["# 검토 v1 (fixture)", "", "이 파일은 고정 자료입니다.", ""]
    rows = [("k-aaa", "s1", [], ["## 1. k-aaa", "무엇이 있었나: 브랜치를 묻지 않고 지웠다.", "제안: 지우기 전에 묻는다.",
                                 "결정: 이 줄은 인용이고 블록 밖에 있다."]),
            ("k-bbb", "s2", ["1", "2"], ["## 2. k-bbb (판정 필요)", "판정 1 - bounded: A 충족, B 미충족",
                                         "판정 2 - recognizable: A 미충족, B 충족"]),
            ("k-ccc", "s3", [], ["## 3. k-ccc", "제안: keep 기록 R-1을 줄인다."])]

    def render_of(held_rows):
        lines = list(head)
        for item, sha, labels, text in held_rows:
            lines += text + review_block(item, sha, labels) + [""]
        return "\n".join(lines) + "\n"

    render = render_of(rows)
    blank = copy_of(render, name)

    def spec_of(**over):
        held = {"k-aaa": {"item_sha": "s1", "judgments": {}, "alternatives": ["alt-1"], "guarded_keeps": []},
                "k-bbb": {"item_sha": "s2", "judgments": {"1": ["met", "unmet"], "2": ["met", "unmet"]},
                          "alternatives": [], "guarded_keeps": []},
                "k-ccc": {"item_sha": "s3", "judgments": {}, "alternatives": [], "guarded_keeps": ["R-1"]}}
        for ident, row in over.items():
            if row is None:
                held.pop(ident)
            else:
                held[ident] = {**held.get(ident, {"judgments": {}, "alternatives": [], "guarded_keeps": []}), **row}
        return held

    def fill(item, *lines_, base=None):
        text = (base or blank).split("\n")
        start = next(i for i, t in enumerate(text) if t.startswith(f"<!-- owner-block review item={item} "))
        end = next(i for i in range(start + 1, len(text)) if text[i] == CLOSE)
        return "\n".join(text[:start + 1] + list(lines_) + text[end:])

    def run(copy, spec="default", **kwargs):
        return parse(render, copy, spec=spec_of() if spec == "default" else spec, render_name=name, **kwargs)

    def said(copy, spec="default", **kwargs):
        return "\n".join(run(copy, spec, **kwargs)[1]) or "(none)"

    def item_of(copy, ident, spec="default"):
        result, problems = run(copy, spec)
        if result is None:
            return {"problems": problems}
        return next((i for i in result["items"] if i["item_id"] == ident), {"absent": ident})

    def number(copy, text):
        return copy.split("\n").index(text) + 1

    # ---- positive controls ---------------------------------------------------------------------------------------
    clean("the fixture render is a render", render_problems(render))
    clean("the unedited copy parses with nothing refused", run(blank)[1])
    result, _p = run(blank)
    equal("the unedited copy holds the render's three rows, in its order (the controls below judge real blocks)",
          [i["item_id"] for i in (result or {"items": []})["items"]], ["k-aaa", "k-bbb", "k-ccc"])
    equal("and every row of an unedited copy is undecided, with no decision",
          [(i["state"], i["decision"]) for i in (result or {"items": []})["items"]], [("undecided", None)] * 3)
    control("the copy's first line names the render and its sha256", blank.split("\n", 1)[0],
            f"of={name} sha256={sha256_text(render)}")
    equal("and every other byte of the copy is the render's", blank.split("\n", 1)[1], render)
    equal("§10.1's five verbs are VERBS, in the design's order",
          re.findall(r"`([^`]+)`", DESIGN_10_1)[1:], list(VERBS))

    # ---- each verb and line kind ---------------------------------------------------------------------------------
    got = item_of(fill("k-aaa", "결정: 승인", "메모:"), "k-aaa")
    equal("결정: 승인 is an approval", (got.get("state"), got.get("decision"), got.get("verb")),
          ("decided", "approve", "승인"))
    got = item_of(fill("k-aaa", "결정: 수정", "메모: 묻는 대상을 원격 브랜치로 좁힌다."), "k-aaa")
    equal("결정: 수정 with a note returns the note", (got.get("decision"), got.get("note"), got.get("alternative")),
          ("revise", "묻는 대상을 원격 브랜치로 좁힌다.", None))
    got = item_of(fill("k-aaa", "결정: 수정 대안 alt-1", "메모:"), "k-aaa")
    equal("결정: 수정 대안 <id> adopts S7b's alternative and needs no note", (got.get("decision"), got.get("alternative")),
          ("revise", "alt-1"))
    got = item_of(fill("k-aaa", "결정: 보류", "메모:"), "k-aaa")
    equal("결정: 보류 defers", got.get("decision"), "defer")
    got = item_of(fill("k-aaa", "결정: 기각", "메모:"), "k-aaa")
    equal("결정: 기각 rejects", got.get("decision"), "reject")
    got = item_of(fill("k-bbb", "결정: 판정", "메모: 상황이 미리 알아볼 수 있다.", "판정 1: A", "판정 2: unmet"), "k-bbb")
    equal("결정: 판정 reads each judgment: judge A's side, and the owner's own value",
          (got.get("decision"), [(j["label"], j["choice"], j["value"]) for j in got.get("judgments", [])]),
          ("adjudicate", [("1", "A", None), ("2", "own", "unmet")]))
    got = item_of(fill("k-bbb", "결정: 판정", "메모: 근거", "판정 1: B", "판정 2: B"), "k-bbb")
    equal("and judge B's side", [j["choice"] for j in got.get("judgments", [])], ["B", "B"])
    got = item_of(fill("k-ccc", "결정: 승인", "메모:", "keep 해제: R-1 — 사용자가 직접 줄이기로 했다."), "k-ccc")
    equal("keep 해제: <record> <grounds> releases the record with its grounds, the dash dropped",
          (got.get("decision"), [(k["record_id"], k["grounds"]) for k in got.get("keep_releases", [])]),
          ("approve", [("R-1", "사용자가 직접 줄이기로 했다.")]))
    copy = fill("k-ccc", "결정: 승인", "메모:", "keep 해제: R-1 근거")
    equal("and the release's line is the copy's own line number",
          item_of(copy, "k-ccc").get("keep_releases", [{}])[0].get("line"), number(copy, "keep 해제: R-1 근거"))
    got = item_of(fill("k-aaa", "결정： 승인"), "k-aaa")
    equal("a full-width colon reads as the colon", got.get("decision"), "approve")
    got = item_of(fill("k-aaa", unicodedata.normalize("NFD", "결정: 승인")), "k-aaa")
    equal("a decision line in NFD Hangul reads as its NFC", got.get("decision"), "approve")
    got = item_of(fill("k-aaa", "   결정:   승인   ", "", "  메모: 하나", "메모: 둘"), "k-aaa")
    equal("indentation, blank lines and repeated notes inside a block: the notes joined in order",
          (got.get("decision"), got.get("note")), ("approve", "하나\n둘"))
    got = item_of(fill("k-aaa"), "k-aaa")
    equal("a block emptied of every line is undecided, not refused", (got.get("state"), got.get("problems")),
          ("undecided", None))
    clean("and nothing is refused of it", run(fill("k-aaa"))[1])

    # ---- edits outside the editable parts ------------------------------------------------------------------------
    copy = blank.replace("제안: 지우기 전에 묻는다.", "제안: 지우기 전에 꼭 묻는다.")
    control("a changed payload word is refused by its line number", said(copy),
            f"EDIT_OUTSIDE_EDITABLE line {number(copy, '제안: 지우기 전에 꼭 묻는다.')}: its text differs")
    clean("the same words inside a note are accepted",
          run(fill("k-aaa", "결정: 승인", "메모: 제안: 지우기 전에 꼭 묻는다."))[1])
    copy = blank.replace("결정: 이 줄은 인용이고 블록 밖에 있다.", "결정: 승인")
    control("a payload line shaped like a 결정 line is fixed by its position: editing it is refused", said(copy),
            f"EDIT_OUTSIDE_EDITABLE line {number(copy, '결정: 승인')}:")
    copy = blank.replace("## 2. k-bbb (판정 필요)", "결정: 승인\n## 2. k-bbb (판정 필요)")
    control("a 결정 line written outside every block is refused at its line", said(copy),
            f"EDIT_OUTSIDE_EDITABLE line {number(copy, '결정: 승인')}:")
    copy = blank.replace("무엇이 있었나: 브랜치를 묻지 않고 지웠다.\n", "")
    control("a deleted payload line is refused where the copy departs", said(copy),
            f"EDIT_OUTSIDE_EDITABLE line {number(copy, '제안: 지우기 전에 묻는다.')}:")
    control("a removed final newline is named", said(blank[:-1]), "lacks the render's final newline")
    copy = blank + "\n"
    control("a line past the render's end is refused at its line", said(copy),
            f"EDIT_OUTSIDE_EDITABLE line {len(copy.split(chr(10)))}: a line the render does not have")
    copy = blank.replace("제안: 지우기 전에 묻는다.", "제안: 지우기 전에 묻는다.  ")
    control("trailing whitespace on a fixed line is refused and named", said(copy), "only its trailing whitespace")
    control("CRLF line endings are refused by name", said(blank.replace("\n", "\r\n")), "LINE_ENDINGS_CHANGED line 1")
    copy = blank.replace("무엇이 있었나: 브랜치를 묻지 않고 지웠다.",
                         unicodedata.normalize("NFD", "무엇이 있었나: 브랜치를 묻지 않고 지웠다."))
    control("a fixed line re-normalized to NFD is refused by name", said(copy), "NORMALIZATION_CHANGED line")
    control("a byte-order mark is refused by name", said("﻿" + blank), "ENCODING_CHANGED line 1")
    control("a copy without its header is refused", said(blank.split("\n", 1)[1]), "COPY_HEADER_MISSING line 1")
    other = render_of(rows[:2])
    control("a copy of another render is refused: the sha names another render", said(copy_of(other, name)),
            "COPY_UNBOUND line 1")
    control("and a copy naming another render's file is refused", said(copy_of(render, "review.ko.v2.md")),
            "COPY_UNBOUND line 1")
    control("a marker's sha edited is an edit outside the editable parts",
            said(blank.replace("item=k-aaa sha=s1", "item=k-aaa sha=s9")), "EDIT_OUTSIDE_EDITABLE line")
    copy = blank.replace("메모:\n" + CLOSE + "\n\n## 2.", "메모:\n\n## 2.", 1)
    control("a deleted block end lets the next block open inside it: refused by line", said(copy),
            f"BLOCK_NESTED line {number(copy, '<!-- owner-block review item=k-bbb sha=s2 -->')}")
    last = blank.rsplit(CLOSE, 1)
    control("the last block's end deleted is refused as unterminated", said(last[0] + last[1]), "BLOCK_UNTERMINATED line")

    # ---- ambiguous lines, refused by line ------------------------------------------------------------------------
    copy = fill("k-aaa", "결정: 승인 기각")
    control("two verbs on one line are refused, not read as the first", said(copy),
            f"DECISION_ARGUMENT_INVALID line {number(copy, '결정: 승인 기각')}")
    copy = fill("k-aaa", "결정: 승인함")
    control("a word that is not a verb is refused, not read as the verb it resembles", said(copy),
            f"DECISION_VERB_UNKNOWN line {number(copy, '결정: 승인함')}")
    copy = fill("k-aaa", "결정: 승인", "좋습니다")
    control("a free line inside a block is refused: a note is a 메모: line", said(copy),
            f"LINE_NOT_EDITABLE line {number(copy, '좋습니다')}")
    copy = fill("k-aaa", "결정: 승인", "메모:", "결정: 기각")
    control("a second 결정 line is refused at its line", said(copy),
            f"DECISION_TWICE line {number(copy, '결정: 기각')}")
    copy = fill("k-bbb", "결정: 판정", "메모: 근거", "판정: A")
    control("a 판정 line without its label is refused", said(copy), f"LINE_NOT_EDITABLE line {number(copy, '판정: A')}")
    copy = fill("k-aaa", "결정: 승인", "확인: 확정")
    control("a 확인 line in a review row is refused", said(copy), f"LINE_NOT_EDITABLE line {number(copy, '확인: 확정')}")
    copy = fill("k-aaa", "결정: 수정 대안")
    control("수정 대안 without its id is refused", said(copy),
            f"DECISION_ARGUMENT_INVALID line {number(copy, '결정: 수정 대안')}")

    # ---- the rules among a block's lines (no rows needed) --------------------------------------------------------
    copy = fill("k-bbb", "결정: 보류", "판정 1: A")
    control("a filled 판정 value under another verb is refused at the value's line", said(copy, spec=None),
            f"ADJUDICATION_WITHOUT_VERB line {number(copy, '판정 1: A')}")
    copy = fill("k-bbb", "결정: 판정", "메모: 근거", "판정 1: A", "판정 2:")
    control("결정: 판정 with an empty judgment is refused at the empty line", said(copy, spec=None),
            f"ADJUDICATION_INCOMPLETE line {number(copy, '판정 2:')}")
    copy = fill("k-bbb", "결정: 판정", "메모: 근거")
    control("결정: 판정 with no judgment line at all is refused", said(copy, spec=None),
            f"ADJUDICATION_INCOMPLETE line {number(copy, '결정: 판정')}")
    copy = fill("k-bbb", "결정: 판정", "판정 1: A", "판정 2: B")
    control("판정 without its rationale is refused", said(copy, spec=None),
            f"NOTE_REQUIRED line {number(copy, '결정: 판정')}")
    copy = fill("k-aaa", "결정: 수정", "메모:")
    control("수정 with neither a note nor an alternative is refused", said(copy, spec=None),
            f"NOTE_REQUIRED line {number(copy, '결정: 수정')}")
    copy = fill("k-ccc", "결정: 승인", "keep 해제: R-1")
    control("keep 해제 without grounds is refused", said(copy, spec=None),
            f"KEEP_RELEASE_GROUNDLESS line {number(copy, 'keep 해제: R-1')}")
    copy = fill("k-ccc", "결정: 보류", "keep 해제: R-1 근거")
    control("keep 해제 under anything but 승인 is refused", said(copy, spec=None),
            f"KEEP_RELEASE_UNUSED line {number(copy, 'keep 해제: R-1 근거')}")
    copy = fill("k-bbb", "결정: 판정", "메모: 근거", "판정 1: A", "판정 1: B", "판정 2: A")
    control("one judgment answered twice is refused at the second", said(copy, spec=None),
            f"JUDGMENT_TWICE line {number(copy, '판정 1: B')}")
    copy = fill("k-ccc", "결정: 승인", "keep 해제: R-1 하나", "keep 해제: R-1 둘")
    control("one record released twice is refused at the second", said(copy, spec=None),
            f"KEEP_RELEASE_TWICE line {number(copy, 'keep 해제: R-1 둘')}")
    got = item_of(fill("k-bbb", "결정: 판정", "메모: 근거", "판정 1: a", "판정 2: B"), "k-bbb", spec=None)
    equal("a lower-case a is the owner's own value, never read as judge A",
          [(j["choice"], j["value"]) for j in got.get("judgments", [])], [("own", "a"), ("B", None)])

    # ---- each line held to its current row -----------------------------------------------------------------------
    copy = fill("k-aaa", "결정: 승인")
    got = item_of(copy, "k-aaa", spec=spec_of(**{"k-aaa": {"item_sha": "s1-changed"}}))
    equal("an item whose sha changed after rendering is stale, and its approval is not a decision",
          (got.get("state"), (got.get("code") or "").split(" ", 1)[0]), ("stale", "DECISION_STALE"))
    clean("and a stale item refuses nothing else of the file", run(copy, spec=spec_of(**{"k-aaa": {"item_sha": "x"}}))[1])
    got = item_of(fill("k-bbb", "결정: 승인"), "k-bbb", spec=spec_of(**{"k-bbb": {"item_sha": "s2-changed"}}))
    equal("and a stale disputed row is not judged by its old lines", got.get("state"), "stale")
    clean("so its approval raises no DISPUTE_UNRESOLVED",
          run(fill("k-bbb", "결정: 승인"), spec=spec_of(**{"k-bbb": {"item_sha": "s2-changed"}}))[1])
    copy = fill("k-bbb", "결정: 판정", "메모: 근거", "판정 1: A", "판정 2: B", "판정 3: A")
    control("a judgment label the row does not carry is refused", said(copy),
            f"JUDGMENT_UNKNOWN line {number(copy, '판정 3: A')}")
    copy = fill("k-bbb", "결정: 판정", "메모: 근거", "판정 1: maybe", "판정 2: B")
    control("an own value outside the judgment's values is refused", said(copy),
            f"JUDGMENT_VALUE_INVALID line {number(copy, '판정 1: maybe')}")
    copy = fill("k-aaa", "결정: 판정", "메모: 근거", "판정 1: A")
    control("판정 on a row with no disputed judgment is refused", said(copy),
            f"DECISION_NOT_ALLOWED line {number(copy, '결정: 판정')}")
    copy = fill("k-bbb", "결정: 판정", "메모: 근거", "판정 1: A")
    control("판정 that leaves one of the row's disputed judgments without a line is refused", said(copy),
            f"ADJUDICATION_INCOMPLETE line {number(copy, '결정: 판정')}: disputed judgment 2")
    copy = fill("k-bbb", "결정: 승인")
    control("a disputed row approved without adjudication is refused", said(copy),
            f"DISPUTE_UNRESOLVED line {number(copy, '결정: 승인')}")
    copy = fill("k-aaa", "결정: 수정 대안 alt-9")
    control("an alternative S7b did not offer is refused", said(copy),
            f"ALTERNATIVE_UNKNOWN line {number(copy, '결정: 수정 대안 alt-9')}")
    copy = fill("k-ccc", "결정: 승인", "keep 해제: R-1 근거", "keep 해제: R-9 근거")
    control("a release of a record the proposal does not override is refused", said(copy),
            f"KEEP_UNKNOWN line {number(copy, 'keep 해제: R-9 근거')}")
    copy = fill("k-ccc", "결정: 승인")
    control("an approval over a keep record nobody released is refused (KEEP_GUARDED)", said(copy),
            f"KEEP_GUARDED line {number(copy, '결정: 승인')}: the proposal reduces or merges over keep record R-1")
    clean("and the same approval with the release is accepted", run(fill("k-ccc", "결정: 승인", "keep 해제: R-1 근거"))[1])
    control("a rendered item the current rows do not hold is refused", said(blank, spec=spec_of(**{"k-ccc": None})),
            "ITEM_UNKNOWN line")
    control("a current row the render does not hold is named", said(blank, spec=spec_of(**{"k-ddd": {"item_sha": "s4"}})),
            "ITEM_NOT_RENDERED k-ddd")
    control("rows that are not rows are refused as the caller's error, not reported as the owner's",
            refusal(lambda: run(blank, spec={"k-aaa": {"judgments": {}}})), "SPEC_INVALID k-aaa")

    # ---- the confirmation file (lead decision E1) ----------------------------------------------------------------
    confirm = "\n".join(["# 최종 확인 v1 (fixture)", "", "항목 k-aaa, k-ccc", "", *confirm_block("f1"), ""]) + "\n"
    cname = "confirm.ko.v1.md"
    cblank = copy_of(confirm, cname)

    def cfill(*lines_):
        text = cblank.split("\n")
        start = next(i for i, t in enumerate(text) if t.startswith("<!-- owner-block confirm "))
        end = next(i for i in range(start + 1, len(text)) if text[i] == CLOSE)
        return "\n".join(text[:start + 1] + list(lines_) + text[end:])

    def crun(copy, **kwargs):
        return parse(confirm, copy, render_name=cname, **kwargs)

    def cheld(copy, **kwargs):
        result, problems = crun(copy, **kwargs)
        return (result or {}).get("confirm") or {"problems": problems}

    clean("the confirmation fixture is a render", render_problems(confirm))
    equal("an unedited confirmation copy is undecided", (cheld(cblank).get("state"), cheld(cblank).get("decision")),
          ("undecided", None))
    equal("확인: 확정 confirms the set", (cheld(cfill("확인: 확정")).get("decision")), "confirm")
    equal("확인: 반려 with a note returns it", (cheld(cfill("확인: 반려", "메모: k-ccc를 빼고 다시")).get("decision")),
          "return")
    copy = cfill("확인: 반려")
    control("반려 without a note is refused", "\n".join(crun(copy)[1]),
            f"NOTE_REQUIRED line {number(copy, '확인: 반려')}")
    copy = cfill("확인: 예")
    control("a 확인 word that is not 확정 or 반려 is refused", "\n".join(crun(copy)[1]),
            f"CONFIRM_VERB_UNKNOWN line {number(copy, '확인: 예')}")
    copy = cfill("확인: 확정", "확인: 반려")
    control("a second 확인 line is refused", "\n".join(crun(copy)[1]),
            f"CONFIRM_TWICE line {number(copy, '확인: 반려')}")
    copy = cfill("확인: 확정", "결정: 승인")
    control("a 결정 line in a confirmation block is refused", "\n".join(crun(copy)[1]),
            f"LINE_NOT_EDITABLE line {number(copy, '결정: 승인')}")
    got = cheld(cfill("확인: 확정"), confirm_set="f2")
    equal("a confirmation of a set that is no longer the final set is stale",
          (got.get("state"), (got.get("code") or "").split(" ", 1)[0]), ("stale", "CONFIRM_STALE"))

    # ---- what a render is ----------------------------------------------------------------------------------------
    control("a payload line shaped like a marker is refused in a render",
            "\n".join(render_problems(render.replace("이 파일은 고정 자료입니다.", "<!-- owner-block 안내 -->"))),
            "BLOCK_MALFORMED line 3")
    control("a block end with no block open is refused in a render",
            "\n".join(render_problems(render.replace("이 파일은 고정 자료입니다.", CLOSE))), "BLOCK_UNOPENED line 3")
    control("a prefilled render is refused", "\n".join(render_problems(render.replace("결정:\n메모:", "결정: 승인\n메모:", 1))),
            "RENDER_BLOCK_INVALID line")
    control("two blocks for one item are refused", "\n".join(render_problems(render_of(rows + rows[:1]))), "ITEM_TWICE line")
    control("a copy is not a render", "\n".join(render_problems(blank)), "RENDER_IS_COPY line 1")
    control("review and confirmation blocks in one file are refused",
            "\n".join(render_problems(render + "\n".join(confirm_block("f1")) + "\n")), "FILE_KINDS_MIXED")
    control("a confirmation file with two blocks is refused",
            "\n".join(render_problems(confirm + "\n".join(confirm_block("f2")) + "\n")), "CONFIRM_BLOCK_TWICE line")
    control("a render with a carriage return is refused", "\n".join(render_problems(render.replace("\n", "\r\n", 1))),
            "RENDER_BYTES_INVALID")
    control("a review block missing its sha is refused",
            "\n".join(render_problems(render.replace(" sha=s1 -->", " -->"))), "BLOCK_MALFORMED line")
    control("copy_of refuses an invalid render", refusal(lambda: copy_of(blank, name)), "RENDER_INVALID")
    control("parse refuses a copy of an invalid render as the render's fault", "\n".join(parse(blank, blank)[1]),
            "RENDER_INVALID RENDER_IS_COPY")
    control("a label with a space is refused when the block is made", refusal(lambda: review_block("k", "s", ["a b"])),
            "BLOCK_ARGUMENT_INVALID label")
    control("an item id with '=' is refused when the block is made", refusal(lambda: review_block("k=1", "s")),
            "BLOCK_ARGUMENT_INVALID item")
    control("a repeated label is refused when the block is made", refusal(lambda: review_block("k", "s", ["1", "1"])),
            "BLOCK_ARGUMENT_INVALID labels")
    control("require names every problem, the first first",
            refusal(lambda: require(render, fill("k-aaa", "결정: 승인함", "좋습니다"), render_name=name)),
            "DECISION_VERB_UNKNOWN line")
    try:
        approved = require(render, fill("k-aaa", "결정: 승인"), render_name=name)["items"][0]["decision"]
    except Refused as exc:   # a refusal here is this control failing by name, not the suite dying
        approved = f"refused: {str(exc)[:160]}"
    equal("and returns the result when nothing is refused", approved, "approve")

    reporting.append(True)
    if failures:
        for label, detail in failures:
            print(f"owner_lines --self-test [FAIL] {label}: {detail}", file=sys.stderr)
        print(f"owner_lines --self-test: FAILED ({len(failures)} of {len(ran)} controls)", file=sys.stderr)
        return 1
    print(f"owner_lines --self-test: OK ({len(ran)} controls: the copy is the render under its header; each of the "
          f"five verbs, 수정 대안, 판정 A/B/own, keep 해제 and 확인 read; edits outside a block refused by line and the "
          f"same words in a note accepted; every ambiguous line refused by line; DECISION_STALE, KEEP_GUARDED and the "
          f"row rules held to the current rows)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit("usage: owner_lines.py --self-test")
