#!/usr/bin/env python3
"""Migrate design/session-distill/ledger.json from schema 1 to schema 2, deterministically (design §12.2).

`status` stays the authoritative current state. A legacy field that describes a past event becomes
an element of `decisions[]` or a relation, never a current-state field, so history cannot contradict
the status. The mapping of every field is in `migrate_entry`; the prefix table for legacy decision
text is `PREFIXES`. Nothing is guessed: a decision text no prefix matches (`DECISION_UNMAPPED`), a
field the table does not name (`FIELD_UNMAPPED`) and a window chain that does not parse
(`WINDOW_UNPARSED`) stop the migration by name, and the values the schema removes (`verdict`,
`strength`, `criteria`, the window chain) are returned with the migration, to be written to the dated
migration record when the ledger moves (plan WP-22); `criteria` also becomes `consequence.kinds`, and
each of the two homes is held on its own. The committed ledger is not changed by this module.

The §12.2 field table lists `review_note`, `classified`, `selected` and `placement_proposed` with the
decision fields, each as one `decisions[]` element; the sentence after the table and the expected
records name only the decision fields. This module follows the table, so those four fields keep
their values as elements with disposition `unknown` and approval `unavailable`, and `EXPECTED_ROWS`
lists them beside the elements §12.2 names. `unknown` and `revival` exist only inside such legacy
elements; the entry itself takes design §7.2's vocabulary and starts at `none` (leave as is).
`at` is the first ISO date anywhere in the field's text, `null` when it holds none (design §12.2).
Each entry also gets one last element of kind `legacy_migration` that records its schema 1 status
(`legacy_text`) and the status it migrates to (`legacy_status`), dated by the newest window of the
schema 1 ledger: a revert of the first run decision on the entry restores that status (runlib/ledger.py
`replays`), where the decisions alone leave several statuses open. The element is not in design
§12.2's table; `EXPECTED_ROWS` lists it beside the elements §12.2 names.

  migrate-ledger.py --check [--ledger FILE]   a dry migration of the ledger against the expected
                                              records; a schema 2 ledger must be its own migration
  migrate-ledger.py --self-test
"""
import argparse
import ast
import copy
import datetime
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from runlib import ledger as ledger_lib  # noqa: E402

LEDGER = REPO / ledger_lib.LEDGER_REL
READERS = HERE / "tables" / "ledger_readers.json"

# The mapping itself (design §12.2's prefix table, the field table, `migrate_entry`, `migrate`) lives in
# runlib/ledger_migration.py, so S4's intake migrates a schema 1 pin with the same function (WP-09, D4).
from runlib.ledger_migration import (PREFIXES, DECISION_FIELDS, EVENT_FIELDS, REMOVED_FIELDS, KEPT_FIELDS, MOVED_FIELDS, LEGACY_ONLY, DATE, CHAIN,
                                     LEGACY_APPLIED, MigrationError, match_prefix, first_date, element, migrate_entry,
                                     windows_of, migrate)  # noqa: E402,F401


def lost_values(legacy, migrated, removed):
    """Design §12.2's own rule, "every legacy field value is found in the migrated record": the
    problems naming the entry and the field whose value is not where the table puts it."""
    problems = []
    if migrated["framework"] != legacy["framework"]:
        problems.append("FIELD_VALUE_LOST ledger framework: the framework path changed")
    if removed.get("_ledger", {}).get("window") != legacy.get("window"):
        problems.append("FIELD_VALUE_LOST ledger window: the chain string is not in the migration record")
    if [w["end"] for w in migrated["windows"]] != [m[1] for m in reversed(CHAIN.findall(legacy.get("window") or ""))]:
        problems.append("FIELD_VALUE_LOST ledger window: windows[] does not hold the chain's window ends")
    new = {e["id"]: e for e in migrated["entries"]}
    for entry in legacy["entries"]:
        eid, there = entry["id"], new.get(entry["id"])
        if there is None:
            problems.append(f"FIELD_VALUE_LOST {eid}: the entry is not in the migrated ledger")
            continue
        by_field = {e.get("field"): e for e in there["decisions"]}
        for field, value in entry.items():
            if value is None:
                continue  # a null carries no value to find
            if field == "status":
                ok = there["status"] == ("incubating" if value == "incubating-G" else value) and any(
                    e.get("kind") == "legacy_migration" and e["legacy_text"] == value and e["legacy_status"] == there["status"]
                    for e in there["decisions"])
            elif field == "window":
                ok = there["window"] == value
            elif field == "classification":
                ok = there["classification"] == ({**value, "type": "G"} if entry["status"] == "incubating-G" else value)
            elif field in KEPT_FIELDS and field not in ("absorbed_by", "retired", "retire_reason"):
                ok = there.get(field) == value
            elif field in DECISION_FIELDS or field in EVENT_FIELDS:
                ok = by_field.get(field, {}).get("legacy_text") == value
            elif field in REMOVED_FIELDS and field != "criteria":
                ok = removed.get(eid, {}).get(field) == value
            elif field == "criteria":
                ok = there["consequence"]["kinds"] == value and removed.get(eid, {}).get("criteria") == value
            elif field == "supporting_sessions":
                ok = [x["session"] for x in there["evidence"]] == value
            elif field == "absorbed_by":
                ok = there.get("absorbed_by") == value or there["relations"].get("instance_of") == value
            elif field in ("retired", "retire_reason"):
                ok = there.get(field) == value or by_field.get("retired", {}).get("at" if field == "retired" else "legacy_text") == value
            elif field == "placed":
                ok = any(e["applied"] is not None and value in (e["at"], e.get("legacy_placed")) for e in there["decisions"])
            else:  # implementation, placed_anchor, placed_package_id
                key = {"implementation": "implementation", "placed_anchor": "anchor", "placed_package_id": "package_id"}[field]
                ok = (there["destination"] or {}).get(key) == value
            if not ok:
                problems.append(f"FIELD_VALUE_LOST {eid} {field}: {str(value)[:60]!r} is not where design §12.2 puts it")
    return problems


def leftover_fields(migrated):
    """Legacy fields that stayed on an entry: a retirement kept where the status differs counts too."""
    problems = []
    for entry in migrated["entries"]:
        problems += [f"FIELD_NOT_MIGRATED {entry['id']} {field}: a legacy field left on a schema 2 entry"
                     for field in sorted(set(entry) & set(LEGACY_ONLY))]
        if entry["status"] != "retired":
            problems += [f"FIELD_NOT_MIGRATED {entry['id']} {field}: kept only on a retired entry"
                         for field in ("retired", "retire_reason") if field in entry]
        if entry["status"] != "absorbed" and "absorbed_by" in entry:
            problems.append(f"FIELD_NOT_MIGRATED {entry['id']} absorbed_by: kept only on an absorbed entry")
    return problems


# design §12.2, "Expected migrated records for the named rows", copied here once (WP-13 done-when 1)
# and held against the real ledger. Each element is (field, disposition, approval_id, at, kind); the
# elements run in the order the migration serializes them: the decision fields, then the four
# event fields (see the module docstring), the historical retirement, the legacy application.
# `entry` lists what §12.2 says the entry keeps or loses.
LEG = "legacy_application"
EXPECTED_ROWS = {
    "G-8": {"status": "placed", "relations": {}, "entry": {"retired": None, "retire_reason": None, "absorbed_by": None},
            "elements": [("decision", "incubate", "legacy", "2026-07-19", None), ("decision3", "revival", "legacy", "2026-08-25", None),
                         ("selected", "unknown", "unavailable", "2026-08-25", None),
                         ("retired", "drop", "unavailable", "2026-08-09", "legacy_retirement"),
                         ("placed", "unknown", "unavailable", "2026-08-25", LEG)], "status_note": False},
    "G-5": {"status": "placed", "relations": {}, "entry": {}, "elements": [("placed", "unknown", "unavailable", "2026-07-19", LEG)], "status_note": False},
    "S2-17": {"status": "absorbed", "relations": {}, "entry": {"absorbed_by": "G-5"},
              "elements": [("decision1", "unknown", "legacy", "2026-07-19", None), ("classified", "unknown", "unavailable", "2026-07-18", None)],
              "status_note": False},
    "S2-19": {"status": "retired", "relations": {}, "entry": {"retired": "2026-08-09"},
              "elements": [("decision1", "unknown", "legacy", "2026-08-25", None), ("decision2", "unknown", "unavailable", "2026-08-25", None),
                           ("classified", "unknown", "unavailable", "2026-07-18", None)], "status_note": False},
    "S3-06": {"status": "placed", "relations": {"instance_of": "G-2"}, "entry": {"absorbed_by": None},
              "elements": [("decision1", "unknown", "legacy", "2026-08-25", None), ("decision2", "unknown", "unavailable", "2026-08-25", None),
                           ("decision3", "none", "unavailable", "2026-07-19", None), ("classified", "unknown", "unavailable", "2026-07-18", None),
                           ("selected", "unknown", "unavailable", "2026-08-25", None), ("placed", "unknown", "unavailable", "2026-08-25", LEG)],
              "status_note": False},
    "S4-03": {"status": "placed", "relations": {"instance_of": "G-2"}, "entry": {"absorbed_by": None},
              "elements": [("decision1", "unknown", "legacy", "2026-07-19", None), ("decision3", "none", "unavailable", "2026-07-19", None),
                           ("classified", "unknown", "unavailable", "2026-07-18", None), ("placed", "unknown", "unavailable", "2026-07-19", LEG)],
              "status_note": False},
    "S4-07": {"status": "placed", "relations": {"instance_of": "G-3"}, "entry": {"absorbed_by": None},
              "elements": [("decision1", "unknown", "legacy", "2026-07-19", None), ("decision3", "none", "unavailable", "2026-07-19", None),
                           ("classified", "unknown", "unavailable", "2026-07-18", None), ("placed", "unknown", "unavailable", "2026-07-19", LEG)],
              "status_note": False},
    "S3-16": {"status": "placed", "relations": {"instance_of": "G-3"}, "entry": {"absorbed_by": None},
              "elements": [("decision1", "unknown", "legacy", "2026-07-19", None), ("decision3", "none", "unavailable", "2026-07-19", None),
                           ("classified", "unknown", "unavailable", "2026-07-18", None), ("placed", "unknown", "unavailable", "2026-07-19", LEG)],
              "status_note": False},
}
# design §12.2: "all 310 values in `decision` and `decision1`–`decision3`, measured 2026-10-20, fall
# under these 14 prefixes", with their counts; copied once.
DESIGN_PREFIX_COUNTS = {"below-bar-default": 81, "incubating": 26, "user-confirmed incubating": 2, "selected": 7, "user-promoted": 3,
                        "user-approved": 4, "user-adopted": 5, "curator-placed": 1, "absorbed": 6, "absorbed-as-instance": 4,
                        "user-revived": 1, "PROPOSED resolved": 26, "user-approved-default": 133, "recommendation-confirmed": 11}


def row_problems(migrated, migration_at, expected=EXPECTED_ROWS, retired_fields=("retired", "retire_reason", "absorbed_by")):
    """`EXPECTED_RECORD_MISMATCH <row>` for each named row whose migrated record differs from §12.2's.
    Every row ends with the element of kind `legacy_migration`, dated `migration_at` (see the module docstring)."""
    rows, problems = {e["id"]: e for e in migrated["entries"]}, []
    for rid, want in expected.items():
        have = rows.get(rid)
        if have is None:
            problems.append(f"EXPECTED_RECORD_MISMATCH {rid}: the row is not in the migrated ledger")
            continue
        got = [(e["field"], e["disposition"], e["approval_id"], e["at"], e.get("kind")) for e in have["decisions"]]
        notes = any("status_note" in e for e in have["decisions"])
        kept = {k: have.get(k) for k in retired_fields if k in want["entry"] or k in have}
        for label, ok in (("status", have["status"] == want["status"]), ("elements", got == [*want["elements"], ("status", "unknown", "unavailable", migration_at, "legacy_migration")]),
                          ("relations", have["relations"] == want["relations"]), ("status_note", notes == want["status_note"]),
                          ("entry fields", all(kept.get(k) == v for k, v in want["entry"].items()))):
            if not ok:
                problems.append(f"EXPECTED_RECORD_MISMATCH {rid}: {label} differ from design §12.2" + (f" (elements {got})" if label == "elements" else ""))
    return problems


def decision_values(legacy):
    return [(e["id"], f, e[f]) for e in legacy["entries"] for f in DECISION_FIELDS if e.get(f) is not None]


def prefix_counts(legacy):
    counts = {}
    for eid, field, text in decision_values(legacy):
        row = match_prefix(text)
        if row is not None:
            counts[row[0]] = counts.get(row[0], 0) + 1
    return counts


# ---------------------------------------------------------------- the reader inventory

CODE_SUFFIXES = (".py", ".js", ".mjs", ".cjs", ".sh", ".toml")
LEDGER_NAME = "ledger.json"
PATH_PIECES = {"session-distill", LEDGER_NAME}
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def scope_pieces(scope):
    """{path piece: first line} over the string constants of one scope, split at `/`, not counting a
    scope nested in it. A bare string statement is a docstring and builds nothing."""
    found, todo = {}, list(ast.iter_child_nodes(scope))
    while todo:
        node = todo.pop()
        if isinstance(node, SCOPES) or (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for piece in node.value.split("/"):
                found[piece] = min(found.get(piece, node.lineno), node.lineno)
        todo.extend(ast.iter_child_nodes(node))
    return found


def ast_lines(text):
    """Lines of the Python scopes (the module, each function and class) that hold `session-distill` and
    `ledger.json` as path components, in one string or several, in one statement or several."""
    try:
        tree = ast.parse(text)
    except SyntaxError:  # a file that cannot be read for statements is a reader until someone says it is not
        return [0]
    lines = []
    for scope in [tree, *[n for n in ast.walk(tree) if isinstance(n, SCOPES)]]:
        pieces = scope_pieces(scope)
        if PATH_PIECES <= set(pieces):
            lines.append(min(pieces[piece] for piece in PATH_PIECES))
    return sorted(set(lines))


def discover_readers(sources, patterns=()):
    """{path: {layer: [line, …]}} over the code files, by three layers that each see what the others miss.
    `text`: the file names `ledger.json` anywhere. `ast`: a Python scope assembles the ledger's path
    from its pieces. `argument`: a line of a file with a pattern's suffix matches the pattern's regex,
    the way a script that is handed the ledger's rows names them."""
    found = {}
    for path, text in sources.items():
        lines = text.splitlines()
        layers = {"text": [n for n, line in enumerate(lines, 1) if LEDGER_NAME in line],
                  "argument": [n for n, line in enumerate(lines, 1)
                               if any(path.endswith(tuple(p["suffixes"])) and re.search(p["regex"], line) for p in patterns)]}
        if path.endswith(".py") and LEDGER_NAME in text and "session-distill" in text:
            layers["ast"] = ast_lines(text)
        layers = {layer: where for layer, where in layers.items() if where}
        if layers:
            found[path] = layers
    return found


def tracked_sources(repo=REPO):
    listing = subprocess.run(["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard", "-z", "--", *[f"*{s}" for s in CODE_SUFFIXES]],
                             capture_output=True)
    if listing.returncode != 0:
        raise MigrationError(f"READERS_UNDISCOVERABLE: git ls-files failed: {listing.stderr.decode()[:100]}")
    return {p: (pathlib.Path(repo) / p).read_text(encoding="utf-8", errors="replace") for p in listing.stdout.decode().split("\0") if p
            and (pathlib.Path(repo) / p).is_file()}


def reader_problems(found, inventory, sources, repo=REPO):
    """The inventory against what discovery found. `READER_UNLISTED`: a file is found by some layer and
    the inventory lists it neither as a reader nor as a mention. `READER_STALE`: a listed reader the
    layer that should find it does not find (`literal`: the text layer; `components`: the AST layer;
    `argument`: its own witness pattern). `MENTION_STALE`: a listed mention that no longer names the file."""
    if not found:
        return ["READER_DISCOVERY_EMPTY: discovery found no reader at all, so a pass would judge nothing"]
    readers = {r["path"]: r for r in inventory["readers"]}
    mentions = {m["path"] for m in inventory["mentions_only"]}
    problems = [f"READER_UNLISTED {path}:{min(n for where in layers.values() for n in where)}: found by the {'+'.join(sorted(layers))} layer "
                f"and tables/ledger_readers.json lists it neither as a reader nor as a mention"
                for path, layers in sorted(found.items()) if path not in readers and path not in mentions]
    for path, reader in sorted(readers.items()):
        built = reader["path_built"]
        if built == "literal" and "text" not in found.get(path, {}) or built == "components" and "ast" not in found.get(path, {}):
            problems.append(f"READER_STALE {path}: listed as building the ledger's path ({built}), and the {'text' if built == 'literal' else 'AST'} layer finds no such statement")
        if built == "argument" and not re.search(reader["witness"], sources.get(path, "")):
            problems.append(f"READER_STALE {path}: listed as receiving the ledger's rows, and its witness {reader['witness']!r} is gone")
        if not (pathlib.Path(repo) / path).is_file():
            problems.append(f"READER_MISSING {path}: listed, and not a file of this tree")
    problems += [f"MENTION_STALE {path}: listed as a mention, and the file no longer names {LEDGER_NAME}" for path in sorted(mentions)
                 if "text" not in found.get(path, {})]
    return problems


# ---------------------------------------------------------------- the check and the self-test

def check_ledger(legacy):
    """Every problem of migrating `legacy`: the design's own self-test rules over its migration."""
    if legacy.get("schema") == 2:
        migrated, _ = migrate(legacy)
        return ([] if migrated == legacy else ["MIGRATION_NOT_IDEMPOTENT: a schema 2 ledger changed under the migration"]) + ledger_lib.validate_ledger(legacy)
    try:
        migrated, removed = migrate(legacy)
    except MigrationError as exc:
        return [str(exc)]
    return leftover_fields(migrated) + lost_values(legacy, migrated, removed) + row_problems(migrated, CHAIN.search(legacy["window"]).group(2))


def history(migrated, index=0):
    """The decisions of one migrated entry without the `legacy_migration` element every entry ends with."""
    return [e for e in migrated["entries"][index]["decisions"] if e.get("kind") != "legacy_migration"]


def tiny(**over):
    entry = {"id": "S3-1", "lesson": "l", "strength": 3, "verdict": "novel", "criteria": ["rollback"], "supporting_sessions": ["claude:1"],
             "classification": None, "status": "incubating", "window": "2026-08-25", "surfaced": "2026-08-25"}
    entry.update(over)
    return {"schema": 1, "framework": "f", "window": "census ending 2026-08-25 (previous: census 21d ending 2026-07-18)", "entries": [entry]}


def build_promotions():
    sys.path.insert(0, str(REPO / "compose"))
    spec = importlib.util.spec_from_file_location("build_promotions", REPO / "learn" / "build-promotions.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_promotions"] = module
    spec.loader.exec_module(module)
    return module


def instructions_state():
    sys.path.insert(0, str(REPO / "compose"))
    spec = importlib.util.spec_from_file_location("instructions_state", REPO / "compose" / "instructions-state.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["instructions_state"] = module
    spec.loader.exec_module(module)
    return module


def self_test():
    failures = []

    def refused(label, legacy, code, *needles):
        try:
            migrate(legacy)
            failures.append(f"{label}: migrated although {code} was due")
        except MigrationError as exc:
            for needle in (code, *needles):
                if needle not in str(exc):
                    failures.append(f"{label}: refusal lacks {needle!r}: {exc}")

    # positive control first: a legacy entry carrying every kind of field migrates to a valid, idempotent record
    full = tiny(status="placed", decision1="user-adopted 2026-08-25; placement decided at apply", placed="2026-08-25",
                placed_anchor="a.md", placed_package_id="@x/y", implementation=["claude/a.md §x"], review_note="note",
                placement_proposed="a.md", classified="2026-07-18", selected="2026-08-25", recurrence=[{"window": "2026-08-25"}],
                learning_id="lid-1", domain="core")
    migrated, removed = migrate(full)
    entry = migrated["entries"][0]
    if ledger_lib.validate_ledger(migrated) or migrate(migrated)[0] != migrated:
        failures.append(f"positive control: the full entry did not migrate to a valid idempotent record: {ledger_lib.validate_ledger(migrated)}")
    if leftover_fields(migrated) or lost_values(full, migrated, removed):
        failures.append(f"positive control: the full entry has problems: {leftover_fields(migrated) + lost_values(full, migrated, removed)}")
    if removed != {"S3-1": {"verdict": "novel", "strength": 3, "criteria": ["rollback"]}, "_ledger": {"window": full["window"]}}:
        failures.append(f"the removed values are {removed}")
    if entry["consequence"] != {"kinds": ["rollback"]} or entry["disposition"] != "none":
        failures.append(f"criteria became {entry['consequence']} and the entry's disposition {entry['disposition']!r}; expected kinds ['rollback'] and none")
    want = [("decision1", "place", "legacy", "2026-08-25"), ("review_note", "unknown", "unavailable", None),
            ("classified", "unknown", "unavailable", "2026-07-18"), ("selected", "unknown", "unavailable", "2026-08-25"),
            ("placement_proposed", "unknown", "unavailable", None)]
    if [(e["field"], e["disposition"], e["approval_id"], e["at"]) for e in history(migrated)] != want:
        failures.append(f"decision elements out of order or wrong: {[(e['field'], e['disposition'], e['approval_id'], e['at']) for e in entry['decisions']]}")
    placing = history(migrated)[0]
    if placing["applied"] != LEGACY_APPLIED or any(e.get("kind") == LEG for e in history(migrated)):
        failures.append("the placement did not land on the place decision whose date it shares")
    if entry["destination"] != {"implementation": ["claude/a.md §x"], "anchor": "a.md", "package_id": "@x/y"}:
        failures.append(f"destination is {entry['destination']}")
    # a placement dated unlike the place decision still lands on it, and keeps its own date beside it (F#8)
    other = tiny(status="placed", decision1="user-adopted 2026-08-25", placed="2026-09-01", implementation="x")
    placed_other = history(migrate(other)[0])
    if [(e["field"], e.get("kind"), e["at"], e.get("legacy_placed")) for e in placed_other] != [("decision1", None, "2026-08-25", "2026-09-01")] \
            or placed_other[0]["applied"] != LEGACY_APPLIED:
        failures.append(f"a placement dated unlike the place decision did not land on it with its own date: {placed_other}")
    if lost_values(other, migrate(other)[0], migrate(other)[1]):
        failures.append(f"positive control: the placement kept on the place decision lost a value: {lost_values(other, *migrate(other))}")
    stripped_date = copy.deepcopy(migrate(other)[0])
    stripped_date["entries"][0]["decisions"][0].pop("legacy_placed", None)
    if not any("FIELD_VALUE_LOST S3-1 placed" in line for line in lost_values(other, stripped_date, migrate(other)[1])):
        failures.append("an application date kept nowhere was not named")
    two = tiny(status="placed", decision1="user-adopted 2026-08-25", decision2="selected 2026-09-02", placed="2026-09-02", implementation="x")
    latest = history(migrate(two)[0])
    if [e["applied"] is not None for e in latest] != [False, True] or latest[1].get("legacy_placed") is not None:
        failures.append(f"the latest of two place decisions, by date, did not carry the application: {latest}")
    reordered = tiny(status="placed", decision1="selected 2026-09-02", decision2="user-adopted 2026-08-25", placed="2026-09-02", implementation="x")
    if [e["applied"] is not None for e in history(migrate(reordered)[0])] != [True, False]:
        failures.append("the latest place decision was taken by field order, not by its date")
    undated = tiny(status="placed", decision1="curator-placed", placed="2026-09-02", placed_anchor="a.md")
    undated_decisions = history(migrate(undated)[0])
    if (undated_decisions[0]["at"], undated_decisions[0]["applied"] is not None, undated_decisions[0].get("legacy_placed")) != (None, True, "2026-09-02"):
        failures.append(f"an undated place decision did not carry the application and its date: {undated_decisions}")
    bare = tiny(status="placed", decision1="incubating 2026-08-25", placed="2026-09-02", placed_anchor="a.md")
    if [(e.get("kind"), e["at"]) for e in history(migrate(bare)[0])] != [(None, "2026-08-25"), (LEG, "2026-09-02")]:
        failures.append("an entry with no place decision did not get its separate legacy application")
    refused("an unmapped decision", tiny(decision2="mystery 2026-01-01"), "DECISION_UNMAPPED", "S3-1 decision2")
    refused("a prefix only as a part of a word", tiny(decision="absorbedly 2026-01-01"), "DECISION_UNMAPPED")
    refused("a field no row names", tiny(surprise=1), "FIELD_UNMAPPED", "surprise")
    refused("a top-level field no row names", {**tiny(), "extra": 1}, "FIELD_UNMAPPED", "extra")
    refused("a window chain that does not parse", {**tiny(), "window": "phase 4 fixture"}, "WINDOW_UNPARSED")
    refused("an absorbed_by with no absorbed-as-instance decision", tiny(status="placed", absorbed_by="G-1"), "ABSORBED_BY_UNMAPPED")
    refused("an unsupported schema", {"schema": 5, "entries": []}, "LEDGER_SCHEMA_UNSUPPORTED")
    refused("a migration that does not validate", tiny(id="bad id"), "MIGRATION_INVALID")
    revived = history(migrate(tiny(status="placed", retired="2026-08-09", retire_reason="r", decision3="user-revived 2026-08-25: back"))[0])
    unrevived = history(migrate(tiny(status="placed", retired="2026-08-09", retire_reason="r"))[0])
    if any("status_note" in e for e in revived) or unrevived[-1].get("status_note") != "current status set without a recorded revival":
        failures.append("a retirement without a recorded revival did not carry the status note, or one with a revival did")
    if migrate(tiny(status="incubating-G", classification={"type": "C", "layer": "incubator"}))[0]["entries"][0]["classification"] != {"type": "G", "layer": "incubator"} or \
            migrate(tiny(status="incubating-G"))[0]["entries"][0]["status"] != "incubating":
        failures.append("incubating-G did not become incubating with type G")
    # every entry ends with the element that records the status it was migrated at, which a revert restores
    plain_decisions = migrate(tiny())[0]["entries"][0]["decisions"]
    marked = plain_decisions[-1] if plain_decisions else {}
    if (marked.get("kind"), marked.get("field"), marked.get("legacy_text"), marked.get("legacy_status"), marked.get("at"), marked.get("disposition"), marked.get("approval_id")) != (
            "legacy_migration", "status", "incubating", "incubating", "2026-08-25", "unknown", "unavailable"):
        failures.append(f"the migration element of a plain entry is {marked}")
    g_decisions = migrate(tiny(status="incubating-G"))[0]["entries"][0]["decisions"]
    marked_g = g_decisions[-1] if g_decisions else {}
    if (marked_g.get("legacy_text"), marked_g.get("legacy_status")) != ("incubating-G", "incubating"):
        failures.append(f"incubating-G was not recorded raw with the status it migrates to: {marked_g}")
    plain = tiny(status="placed")
    plain_migrated, plain_removed = migrate(plain)
    if lost_values(plain, plain_migrated, plain_removed):
        failures.append(f"positive control: the migration element made a faithful migration lose a value: {lost_values(plain, plain_migrated, plain_removed)}")
    for label, mutate in (("its legacy_text changed", lambda d: d[-1:] and d[-1].update(legacy_text="incubating")),
                          ("its legacy_status changed", lambda d: d[-1:] and d[-1].update(legacy_status="retired")),
                          ("the element removed", lambda d: d[-1:] and d.pop())):
        lossy = copy.deepcopy(plain_migrated)
        mutate(lossy["entries"][0]["decisions"])
        if not any("FIELD_VALUE_LOST S3-1 status" in line for line in lost_values(plain, lossy, plain_removed)):
            failures.append(f"a migration element with {label} was not named")
    # `at` is the first ISO date anywhere in the field's text (F#9), null when there is none
    dated = history(migrate(tiny(review_note="2026-09-22 placed; mirrored to codex/ (see 2026-09-10)", placement_proposed="guides/x.md §y",
                         classified="2026-07-18", decision="user-approved-default 2026-07-19; see 2026-07-01",
                         decision3="absorbed-as-instance of G-2, decided 2026-07-19"))[0])
    if [(e["field"], e["at"]) for e in dated] != [("decision", "2026-07-19"), ("decision3", "2026-07-19"), ("review_note", "2026-09-22"),
                                                    ("classified", "2026-07-18"), ("placement_proposed", None)]:
        failures.append(f"dates were not parsed out of every history field: {[(e['field'], e['at']) for e in dated]}")
    if history(migrate(tiny(review_note="the owner restored it in the review"))[0])[0]["at"] is not None:
        failures.append("a field with no date did not get a null at")
    # criteria has two homes, each held on its own (F#7)
    kept_kinds, kept_removed = migrate(tiny(criteria=["rollback", "tests"]))
    if kept_kinds["entries"][0]["consequence"]["kinds"] != ["rollback", "tests"] or kept_removed["S3-1"]["criteria"] != ["rollback", "tests"]:
        failures.append("criteria is not in both consequence.kinds and the migration record")
    one_home = tiny(criteria=["rollback"])
    for label, mutate, removed_after in (
            ("consequence.kinds emptied", lambda m: m["entries"][0]["consequence"].update(kinds=[]), migrate(one_home)[1]),
            ("the migration record without criteria", lambda m: None, {"S3-1": {"verdict": "novel", "strength": 3}, "_ledger": migrate(one_home)[1]["_ledger"]})):
        broken_home = copy.deepcopy(migrate(one_home)[0])
        mutate(broken_home)
        if not any("FIELD_VALUE_LOST S3-1 criteria" in line for line in lost_values(one_home, broken_home, removed_after)):
            failures.append(f"criteria with {label} was not named")
    if lost_values(one_home, *migrate(one_home)):
        failures.append(f"positive control: criteria kept in both homes lost a value: {lost_values(one_home, *migrate(one_home))}")
    if [w["end"] for w in windows_of("census ending 2026-09-22 (previous: census 21d ending 2026-07-18)")] != ["2026-07-18", "2026-09-22"] or \
            windows_of("census 21d ending 2026-07-18")[0]["start"] != "2026-06-27":
        failures.append("the window chain did not parse oldest first with the start of a day count")

    # the design's own self-test rules, each with a control: a value dropped, a field left behind, a row edited
    ok_migrated, ok_removed = migrate(full)
    dropped = copy.deepcopy(ok_migrated)
    dropped["entries"][0]["lesson"] = "changed"
    if not any(p.startswith("FIELD_VALUE_LOST S3-1 lesson") for p in lost_values(full, dropped, ok_removed)):
        failures.append("a value changed in the migrated record was not named by entry and field")
    unplaced = copy.deepcopy(ok_migrated)
    unplaced["entries"][0]["decisions"][0]["applied"] = None
    if not any("FIELD_VALUE_LOST S3-1 placed" in p for p in lost_values(full, unplaced, ok_removed)):
        failures.append("a placement date found nowhere was not named")
    if not any("FIELD_VALUE_LOST S3-1 strength" in p for p in lost_values(full, ok_migrated, {})):
        failures.append("a removed value missing from the migration record was not named")
    if lost_values(full, ok_migrated, ok_removed):
        failures.append(f"positive control: a faithful migration lost values: {lost_values(full, ok_migrated, ok_removed)}")
    kept = copy.deepcopy(ok_migrated)
    kept["entries"][0]["placed_anchor"] = "a.md"
    if not any(p.startswith("FIELD_NOT_MIGRATED S3-1 placed_anchor") for p in leftover_fields(kept)):
        failures.append("an entry-level placed_anchor after migration was not FIELD_NOT_MIGRATED")
    if leftover_fields(ok_migrated):
        failures.append(f"positive control: a faithful migration left fields: {leftover_fields(ok_migrated)}")
    for label, mutate, removed_set, needle in (
            ("the framework changed", lambda m: m.update(framework="elsewhere"), ok_removed, "FIELD_VALUE_LOST ledger framework"),
            ("the window chain missing from the migration record", lambda m: None, {}, "FIELD_VALUE_LOST ledger window"),
            ("windows[] holding other ends", lambda m: m["windows"].pop(), ok_removed, "windows[] does not hold the chain's window ends"),
            ("an entry missing from the migrated ledger", lambda m: m["entries"].clear(), ok_removed, "FIELD_VALUE_LOST S3-1: the entry is not in the migrated ledger")):
        broken = copy.deepcopy(ok_migrated)
        mutate(broken)
        if not any(needle in p for p in lost_values(full, broken, removed_set)):
            failures.append(f"{label}: lost_values did not name {needle!r}")
    absorbed = copy.deepcopy(ok_migrated)
    absorbed["entries"][0]["absorbed_by"] = "G-1"
    if not any("FIELD_NOT_MIGRATED S3-1 absorbed_by" in p for p in leftover_fields(absorbed)):
        failures.append("an absorbed_by kept on a placed entry was not named")
    odd = copy.deepcopy(ok_migrated)
    odd["entries"][0]["retired"] = "2026-08-09"
    if not any("FIELD_NOT_MIGRATED S3-1 retired" in p for p in leftover_fields(odd)):
        failures.append("a retirement kept on an entry that is not retired was not named")

    # the real ledger (schema 1): the migration against §12.2, then the consumers that must not notice
    legacy = json.loads(LEDGER.read_text(encoding="utf-8"))
    if legacy["schema"] == 2:
        if check_ledger(legacy):
            failures.append(f"the committed schema 2 ledger is not its own migration: {check_ledger(legacy)}")
        note = "the committed ledger is schema 2: idempotence only"
    else:
        note = "310 decision values, 8 named rows, consumers"
        values = decision_values(legacy)
        counts = prefix_counts(legacy)
        if len(values) != 310 or counts != DESIGN_PREFIX_COUNTS or sum(counts.values()) != 310:
            failures.append(f"the real ledger's decision values are {len(values)}, prefix counts {counts}; design §12.2 measured 310 and {DESIGN_PREFIX_COUNTS}")
        problems = check_ledger(legacy)
        if problems:
            failures.append(f"the real ledger does not migrate cleanly: {problems[:3]}")
        real, real_removed = migrate(legacy)
        real_at = CHAIN.search(legacy["window"]).group(2)
        plant = copy.deepcopy(legacy)
        plant["entries"][5]["decision1"] = "mystery 2026-01-01"
        try:
            migrate(plant)
            failures.append("an unmapped value planted in a copy of the real ledger migrated")
        except MigrationError as exc:
            if f"DECISION_UNMAPPED {plant['entries'][5]['id']} decision1" not in str(exc):
                failures.append(f"the planted value was not named by entry: {exc}")
        edited = copy.deepcopy(EXPECTED_ROWS)
        edited["S3-06"]["elements"][0] = ("decision1", "place", "legacy", "2026-08-25", None)
        if not any(p.startswith("EXPECTED_RECORD_MISMATCH S3-06") for p in row_problems(real, real_at, edited)):
            failures.append("an expected record edited was not named by row id")
        gone = copy.deepcopy(EXPECTED_ROWS)
        gone["X-1"] = gone["G-5"]
        if not any(p.startswith("EXPECTED_RECORD_MISMATCH X-1") for p in row_problems(real, real_at, gone)):
            failures.append("an expected row absent from the ledger was not named")
        for rid in ("G-8", "S2-19"):  # a row whose retirement is mishandled is caught by the same table
            broken = copy.deepcopy(real)
            row = next(e for e in broken["entries"] if e["id"] == rid)
            row["decisions"] = [d for d in row["decisions"] if d.get("kind") != "legacy_retirement"] if rid == "G-8" else row["decisions"]
            row["status"] = "placed" if rid == "S2-19" else row["status"]
            if not any(p.startswith(f"EXPECTED_RECORD_MISMATCH {rid}") for p in row_problems(broken, real_at)):
                failures.append(f"a mishandled {rid} was not named by row id")
        if ledger_lib.check_pair(legacy, real):
            failures.append(f"the schema 1 ledger and its migration are not accepted by the id-set check: {ledger_lib.check_pair(legacy, real)[:3]}")
        tampered = copy.deepcopy(real)
        tampered["entries"][0]["lesson"] = "tampered"
        if not any("MIGRATION_MISMATCH" in p for p in ledger_lib.check_pair(legacy, tampered)):
            failures.append("a schema 2 head that is not the migration of its schema 1 base was accepted")
        # a revert of the first run decision on a migrated entry restores the schema 1 status, and says it cannot without the element
        # (a decision that leaves the status as it was pins the earlier status by itself, so only the status-changing ones depend on the element)
        for status, disposition, extra, updates, depends in (("incubating", "place", {}, {}, True), ("retired", "place", {}, {}, True),
                                                             ("adopted-no-text", "keep", {"reason": "kept"}, {"keep": {"units": ["u"]}}, False)):
            target = next(e["id"] for e in real["entries"] if e["status"] == status)
            decided = ledger_lib.apply_decision(real, target, ledger_lib.sample_element("run-1", disposition, **extra), updates)
            try:
                back = ledger_lib.record_event(decided, target, "revert", element=ledger_lib.sample_element("run-2", "none", kind="revert"))
                restored = next(e for e in back["entries"] if e["id"] == target)["status"]
            except ledger_lib.LedgerError as exc:
                restored = f"nothing ({exc})"
            if restored != status:
                failures.append(f"a revert of the first {disposition} on migrated {target} restored {restored}, the schema 1 status was {status}")
            if not depends:
                continue
            without = copy.deepcopy(decided)
            row = next(e for e in without["entries"] if e["id"] == target)
            row["decisions"] = [d for d in row["decisions"] if d.get("kind") != "legacy_migration"]
            try:
                ledger_lib.record_event(without, target, "revert", element=ledger_lib.sample_element("run-2", "none", kind="revert"))
                failures.append(f"a revert on {target} with its migration element removed was not refused")
            except ledger_lib.LedgerError as exc:
                if f"REVERT_PRIOR_STATUS_AMBIGUOUS {target}" not in str(exc):
                    failures.append(f"a revert with the migration element removed was refused without the named ambiguity: {exc}")
        unmarked = copy.deepcopy(real)
        row = next(e for e in unmarked["entries"] if e["id"] == "G-5")
        row["decisions"] = [d for d in row["decisions"] if d.get("kind") != "legacy_migration"]
        if not any(p.startswith("EXPECTED_RECORD_MISMATCH G-5") for p in row_problems(unmarked, real_at)):
            failures.append("a named row without its migration element was not named")
        late = copy.deepcopy(real)
        next(e for e in late["entries"] if e["id"] == "G-5")["decisions"][-1]["at"] = "2026-01-01"
        if not any(p.startswith("EXPECTED_RECORD_MISMATCH G-5") for p in row_problems(late, real_at)):
            failures.append("a migration element dated other than the newest window was not named")
        # S-4: the promotion manifest is byte-identical from the unmigrated and the migrated ledger
        promotions = build_promotions()
        domains = json.loads((REPO / "compose" / "domains.json").read_text(encoding="utf-8"))
        committed = (REPO / "learn" / "promotions.json").read_text(encoding="utf-8")
        for label, ledger in (("unmigrated", legacy), ("migrated", real)):
            if promotions.render(promotions.build_manifest(ledger, domains)) != committed:
                failures.append(f"learn/promotions.json differs from the manifest built from the {label} ledger")
        # the F3 guard on a ledger of its own: a placed learning builds a promotion, and the same one without its destination does not
        own_domains = {"bullets": [{"anchor": "universal placed rule", "tier": "core", "domains": []}], "guides": {}, "hooks": {}, "agents": {}}
        own, _ = migrate({"schema": 1, "framework": "f", "window": "census ending 2026-08-25", "entries": [
            {"id": "S9-77", "lesson": "l", "status": "placed", "window": "2026-08-25", "learning_id": "lid-77", "decision1": "user-adopted 2026-08-25",
             "classification": None, "placed": "2026-08-25", "placed_anchor": "universal placed rule", "placed_package_id": "@x/y", "implementation": "claude/a.md §x"}]})
        made = promotions.build_manifest(own, own_domains)["promotions"]
        if [(m["learning_id"], m["anchor"], m["package_id"]) for m in made] != [("lid-77", "universal placed rule", "@x/y")]:
            failures.append(f"positive control: the placed learning of the fixture ledger did not build its promotion: {made}")
        homeless = copy.deepcopy(own)
        homeless["entries"][0]["destination"] = None
        try:
            promotions.build_manifest(homeless, own_domains)
            failures.append("a placed learning whose destination was removed still built a promotion")
        except promotions.ManifestError as exc:
            if "has no `placed_anchor`" not in str(exc) or "'S9-77'" not in str(exc):
                failures.append(f"the missing placement was not refused by the placement guard naming the entry: {exc}")
        # S-4: compose/instructions-state.py reads only fields §12.2 keeps
        status_vocabulary = set(ledger_lib.schema()["$defs"]["entry"]["properties"]["status"]["enum"])
        with tempfile.TemporaryDirectory() as td:
            (pathlib.Path(td) / "design" / "session-distill").mkdir(parents=True)
            (pathlib.Path(td) / ledger_lib.LEDGER_REL).write_text(ledger_lib.render(real), encoding="utf-8")
            summary = instructions_state().ledger_summary(pathlib.Path(td))
            if summary["entries"] != len(real["entries"]) or sum(summary["by_status"].values()) != len(real["entries"]) \
                    or not set(summary["by_status"]) <= status_vocabulary or sum(summary["placed_by_layer"].values()) != summary["by_status"].get("placed"):
                failures.append(f"ledger_summary on the migrated ledger is inconsistent: {summary}")
            # the documented old invocation keeps working on the data it finds until the cutover (N#14)
            scratch = pathlib.Path(td) / "legacy"
            (scratch / "out").mkdir(parents=True)
            old = scratch / "ledger.json"
            old.write_text(LEDGER.read_text(encoding="utf-8"), encoding="utf-8")
            target = next(e["id"] for e in legacy["entries"] if e["status"] == "placed")
            (scratch / "out" / "consolidated.json").write_text(json.dumps({"survivors": [
                {"supporting": ["claude:fixture1"], "strength": 3, "verdict": "novel", "lesson": "a recurring lesson", "principle": "p",
                 "criteria": ["rollback"], "baseline_ref": "b", "placement": "x", "rationale": "r"},
                {"supporting": ["claude:fixture2"], "strength": 3, "verdict": "novel", "lesson": "a new lesson", "principle": "p",
                 "criteria": ["rollback"], "baseline_ref": "b", "placement": "x", "rationale": "r"}],
                "matches": [{"survivor": 0, "ledger_id": target, "reason": "same"}]}), encoding="utf-8")
            command = [sys.executable, str(HERE / "merge-ledger.py"), "--window-end", "2026-10-01", "--apply", "--out", str(scratch / "out"), "--ledger", str(old)]
            done = subprocess.run(command, capture_output=True, text=True)
            merged = json.loads(old.read_text(encoding="utf-8"))
            top = max(int(e["id"].split("-")[1]) for e in legacy["entries"] if e["id"].startswith("S3-"))
            if done.returncode != 0 or len(merged["entries"]) != len(legacy["entries"]) + 1 or merged["entries"][-1]["id"] != f"S3-{top + 1}" \
                    or merged["entries"][-1]["window"] != "2026-10-01" or {"claude:fixture1"} - set(next(e for e in merged["entries"] if e["id"] == target)["supporting_sessions"]):
                failures.append(f"the documented merge-ledger.py --window-end invocation did not merge (exit {done.returncode}): {done.stderr[:200]}")
            again = subprocess.run(command, capture_output=True, text=True)
            if again.returncode != 2 or "already merged" not in again.stderr:
                failures.append(f"the documented invocation did not refuse a second apply for one window (exit {again.returncode})")
            if ledger_lib.check_pair(legacy, merged):
                failures.append(f"the schema 1 ledger after a legacy merge fails the id-set check: {ledger_lib.check_pair(legacy, merged)[:3]}")

    # the reader inventory: what the three layers find against what the inventory lists
    inventory = json.loads(READERS.read_text(encoding="utf-8"))
    patterns = inventory["argument_patterns"]
    sources = tracked_sources()
    found = discover_readers(sources, patterns)
    problems = reader_problems(found, inventory, sources)
    if problems:
        failures.append(f"the reader inventory disagrees with the tree: {problems[:3]}")
    for path, layer in (("learn/build-promotions.py", "ast"), ("learn/ingest-learnings-export.py", "ast"), ("compose/instructions-state.py", "text"),
                        ("session-distill/consolidate.js", "argument"), ("launch/agent-launch.toml", "text")):
        if layer not in found.get(path, {}):
            failures.append(f"{path} is found by the {layer} layer in the tree and discovery did not find it there")

    def plant(label, name, text, *needles, layers=None, absent=()):
        """A file planted in a copy of the tree: discovery finds it by the named layers, and the inventory, which does not list it, fails it by path."""
        planted = {**sources, name: text}
        there = discover_readers(planted, patterns).get(name, {})
        named = reader_problems(discover_readers(planted, patterns), inventory, planted)
        if not any(p.startswith(f"READER_UNLISTED {name}:") for p in named):
            failures.append(f"{label}: the planted file was not named unlisted: {named}")
        for layer in layers or ():
            if layer not in there:
                failures.append(f"{label}: the {layer} layer did not find it (found by {sorted(there)})")
        for layer in absent:
            if layer in there:
                failures.append(f"{label}: the {layer} layer found it, so this case no longer shows what the other layers add")

    plant("a path built from components in one statement", "learn/planted-reader.py",
          'import pathlib\nR = pathlib.Path(".") / "ledger.json" / "session-distill"\n', layers=("ast", "text"))
    plant("a path assembled across statements of one function", "learn/planted-split.py",
          'import pathlib\n\ndef where():\n    root = "session-distill"\n    name = "ledger.json"\n    return pathlib.Path(root) / name\n', layers=("ast", "text"))
    plant("a path assembled across statements of the module", "learn/planted-module.py",
          'import pathlib\nROOT = "design/session-distill"\nNAME = "ledger.json"\nPATH = pathlib.Path(ROOT) / NAME\n', layers=("ast", "text"))
    plant("pieces in two functions, which only the text layer joins", "learn/planted-apart.py",
          'def a():\n    return "session-distill"\n\ndef b():\n    return "ledger.json"\n', layers=("text",), absent=("ast",))
    plant("a script handed the ledger's rows", "session-distill/planted-argument.js", "const rows = args.ledger || []\n", layers=("argument",), absent=("text", "ast"))
    if "argument" in discover_readers({"decisions/planted.py": "rows = args.ledger\n"}, patterns).get("decisions/planted.py", {}):
        failures.append("a Python argument parser's args.ledger was taken for a workflow script handed the ledger's rows")
    plant("a shell script naming the file", "gates/planted-reader.sh", "cat design/session-distill/ledger.json\n", layers=("text",))
    plant("a file that cannot be parsed and mentions the ledger", "learn/broken.py", "X = ledger.json session-distill (", layers=("text", "ast"))
    plant("a docstring that names the ledger", "learn/doc.py", '"""reads design/session-distill/ledger.json"""\nX = 1\n', layers=("text",), absent=("ast",))
    cleared = {**inventory, "mentions_only": inventory["mentions_only"] + [{"path": "learn/doc.py", "reason": "a docstring"}]}
    doc_sources = {**sources, "learn/doc.py": '"""reads design/session-distill/ledger.json"""\nX = 1\n'}
    if reader_problems(discover_readers(doc_sources, patterns), cleared, doc_sources):
        failures.append(f"a mention listed with its reason was still named: {reader_problems(discover_readers(doc_sources, patterns), cleared, doc_sources)}")
    without = {**inventory, "readers": [r for r in inventory["readers"] if r["path"] != "session-distill/consolidate.js"]}
    named = reader_problems(found, without, sources)
    if not any(p.startswith("READER_UNLISTED session-distill/consolidate.js") and "argument" in p for p in named):
        failures.append(f"consolidate.js dropped from the inventory was not named: {named}")
    unwitnessed = {**sources, "session-distill/consolidate.js": sources["session-distill/consolidate.js"].replace("args.ledger", "args.rows")}
    named = reader_problems(discover_readers(unwitnessed, patterns), inventory, unwitnessed)
    if not any(p.startswith("READER_STALE session-distill/consolidate.js") for p in named):
        failures.append(f"an argument reader that stopped naming the rows was not named stale: {named}")
    stale = {"readers": inventory["readers"] + [{"path": "learn/gone.py", "reads": ["status"], "via": "direct", "path_built": "literal"}],
             "mentions_only": inventory["mentions_only"] + [{"path": "learn/also-gone.py", "reason": "x"}]}
    named = reader_problems(found, {**inventory, **stale}, sources)
    if not any(p.startswith("READER_STALE learn/gone.py") for p in named) or not any(p.startswith("READER_MISSING learn/gone.py") for p in named) \
            or not any(p.startswith("MENTION_STALE learn/also-gone.py") for p in named):
        failures.append(f"an inventory entry no layer backs was not named stale, missing and stale as a mention: {named}")
    if not any(p.startswith("READER_DISCOVERY_EMPTY") for p in reader_problems({}, inventory, sources)):
        failures.append("a discovery that found nothing passed")
    try:
        tracked_sources(pathlib.Path(tempfile.gettempdir()) / "no-such-repository")
        failures.append("reader discovery over a directory git cannot list did not refuse")
    except MigrationError as exc:
        if "READERS_UNDISCOVERABLE" not in str(exc):
            failures.append(f"reader discovery refused without its code: {exc}")

    for failure in failures:
        print(f"migrate-ledger --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"migrate-ledger --self-test: OK (fixtures for every mapping rule and refusal, {note}, the reader inventory against a text, AST and argument discovery)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--ledger", default=str(LEDGER))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.check:
        parser.print_usage()
        return 2
    legacy = json.loads(pathlib.Path(args.ledger).read_text(encoding="utf-8"))
    problems = check_ledger(legacy)
    inventory = json.loads(READERS.read_text(encoding="utf-8"))
    try:
        sources = tracked_sources()
        problems += reader_problems(discover_readers(sources, inventory["argument_patterns"]), inventory, sources)
    except MigrationError as exc:
        problems.append(str(exc))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"migrate-ledger --check: OK (schema {legacy['schema']}, {len(legacy['entries'])} entries, {len(DECISION_FIELDS)} decision fields, "
          f"{len(EXPECTED_ROWS)} named rows, reader inventory current)")
    print(f"reader discovery limits ({len(inventory['limits'])}, tables/ledger_readers.json):")
    print("\n".join(f"  - {line}" for line in inventory["limits"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
