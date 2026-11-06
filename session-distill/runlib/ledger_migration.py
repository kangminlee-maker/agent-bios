#!/usr/bin/env python3
"""The schema 1 to schema 2 migration of the ledger (design §12.2), as a function of the ledger's document alone.

Moved here from `session-distill/migrate-ledger.py` unchanged (WP-09 commit 4, lead decision D4): S4's lifecycle intake
migrates a schema 1 pinned ledger in memory with the same function the cutover uses (plan WP-22), and a runlib module
does not import a script. `migrate-ledger.py` imports every name below and keeps its checks, its reader inventory and its
self-test; the module docstring there describes the mapping. Nothing here reads or writes a file.
"""
import copy
import datetime
import pathlib
import re
import sys

if __package__ in (None, ""):  # imported by a script that put session-distill/ on the path, or run by path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import ledger as ledger_lib  # noqa: E402

# design §12.2, "Prefix table for legacy decision text": prefix, disposition, and whether the text
# records an owner decision (`user-…`, and the recommendations the owner confirmed). Matching takes
# the longest prefix that ends at a word boundary, so `user-approved` is not `user-approved-default`.
PREFIXES = (
    ("user-confirmed incubating", "incubate", True), ("user-approved-default", "unknown", True),
    ("recommendation-confirmed", "unknown", True), ("absorbed-as-instance", "none", False),
    ("below-bar-default", "incubate", False), ("PROPOSED resolved", "unknown", False),
    ("curator-placed", "place", False), ("user-promoted", "place", True), ("user-approved", "place", True),
    ("user-adopted", "place", True), ("user-revived", "revival", True), ("incubating", "incubate", False),
    ("selected", "place", False), ("absorbed", "reduce", False),
)
DECISION_FIELDS = ("decision", "decision1", "decision2", "decision3")
EVENT_FIELDS = ("review_note", "classified", "selected", "placement_proposed")  # see the module docstring
REMOVED_FIELDS = ("verdict", "strength", "criteria")
# Every legacy field, and where it goes. A field in none of these is `FIELD_UNMAPPED`.
KEPT_FIELDS = ("id", "lesson", "principle", "rationale", "status", "surfaced", "domain", "source", "note",
               "learning_id", "baseline_ref", "window", "classification", "recurrence", "absorbed_by", "retired", "retire_reason")
MOVED_FIELDS = ("supporting_sessions", "placed", "placed_anchor", "placed_package_id", "implementation")
LEGACY_ONLY = (*REMOVED_FIELDS, *MOVED_FIELDS, *DECISION_FIELDS, *EVENT_FIELDS)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
CHAIN = re.compile(r"census (?:(\d+)d )?ending (" + DATE.pattern + ")")
LEGACY_APPLIED = {"commit": None, "paths": [], "operations": [], "delivery": "unverified"}


class MigrationError(Exception):
    """A refusal; the message starts with the named code."""


def match_prefix(text):
    best = None
    for prefix, disposition, owner in PREFIXES:
        if text.startswith(prefix) and (len(text) == len(prefix) or text[len(prefix)] in " :;,(") \
                and (best is None or len(prefix) > len(best[0])):
            best = (prefix, disposition, owner)
    return best


def first_date(text):
    """The first ISO date anywhere in `text`, else None: design §12.2's "`at` from the date in the text"."""
    found = DATE.search(text)
    return found.group(0) if found else None


def element(run, field, disposition, approval, at, text, **extra):
    return {"run": run, "disposition": disposition, "approval_id": approval, "adjudication_id": None, "confirmation": None,
            "applied": None, "tests": None, "expected_observation": None, "at": at, "field": field, "legacy_text": text, **extra}


def migrate_entry(entry, migrated_at):
    """(the schema 2 entry, the values the schema removes) for one schema 1 entry; `migrated_at` is the
    date its `legacy_migration` element carries."""
    eid = entry["id"]
    unknown = sorted(set(entry) - set(KEPT_FIELDS) - set(LEGACY_ONLY))
    if unknown:
        raise MigrationError(f"FIELD_UNMAPPED {eid}: {unknown} are named by no row of design §12.2")
    run = f"legacy-{entry.get('window') or 'unknown'}"
    status = entry["status"]
    new = {k: copy.deepcopy(entry[k]) for k in KEPT_FIELDS if k in entry and k not in ("window", "absorbed_by", "retired", "retire_reason", "status")}
    new["status"] = "incubating" if status == "incubating-G" else status
    new["window"] = entry.get("window") or "unknown"
    classification = new.get("classification")
    if status == "incubating-G":
        new["classification"] = {**(classification or {}), "type": "G"}
    elements, relations = [], {}
    for field in (*DECISION_FIELDS, *EVENT_FIELDS):
        text = entry.get(field)
        if text is None:
            continue
        if field in DECISION_FIELDS:
            row = match_prefix(text)
            if row is None:
                raise MigrationError(f"DECISION_UNMAPPED {eid} {field}: {text!r} starts with none of the 14 prefixes of design §12.2")
            prefix, disposition, owner = row
            elements.append(element(run, field, disposition, "legacy" if owner else "unavailable", first_date(text), text))
            if prefix == "absorbed-as-instance" and status == "placed" and "absorbed_by" in entry:
                relations["instance_of"] = entry["absorbed_by"]
        else:
            elements.append(element(run, field, "unknown", "unavailable", first_date(text), text))
    if "absorbed_by" in entry:
        if status == "absorbed":
            new["absorbed_by"] = entry["absorbed_by"]
        elif "instance_of" not in relations:
            raise MigrationError(f"ABSORBED_BY_UNMAPPED {eid}: absorbed_by on a {status} entry without an absorbed-as-instance decision")
    if "retired" in entry or "retire_reason" in entry:
        if status == "retired":
            new.update({k: entry[k] for k in ("retired", "retire_reason") if k in entry})
        else:
            revived = any(e["disposition"] == "revival" and (e["at"] or "") >= (entry.get("retired") or "") for e in elements)
            elements.append(element(run, "retired", "drop", "unavailable", entry.get("retired"), entry.get("retire_reason", ""),
                                    kind="legacy_retirement",
                                    **({} if revived else {"status_note": "current status set without a recorded revival"})))
    moved = {k: entry[k] for k in ("placed", "placed_anchor", "placed_package_id", "implementation") if entry.get(k) is not None}
    new["destination"] = ({"implementation": entry.get("implementation"), "anchor": entry.get("placed_anchor"),
                           "package_id": entry.get("placed_package_id")} if moved else None)
    if moved:
        placing = [(e["at"] or "", n) for n, e in enumerate(elements) if e["disposition"] == "place"]
        if placing:  # the latest place decision by its date, field order breaking a tie, carries the application
            latest = elements[max(placing)[1]]
            latest["applied"] = copy.deepcopy(LEGACY_APPLIED)
            if entry.get("placed") is not None and latest["at"] != entry["placed"]:
                latest["legacy_placed"] = entry["placed"]  # the application's own date, which the decision's date is not
        else:
            first = next(k for k in ("placed", "placed_anchor", "placed_package_id", "implementation") if k in moved)
            elements.append(element(run, first, "unknown", "unavailable", entry.get("placed"), str(entry.get("placed") or ""),
                                    kind="legacy_application", applied=copy.deepcopy(LEGACY_APPLIED)))
    elements.append(element(run, "status", "unknown", "unavailable", migrated_at, status, kind="legacy_migration", legacy_status=new["status"]))
    new.update(kind="unclassified", diagnosis="unknown", disposition="none",
               evidence=[{"locator": "unavailable", "session": s} for s in entry.get("supporting_sessions", [])],
               independent_lineages="unavailable", consequence={"kinds": list(entry.get("criteria") or [])},
               coverage={"basis": "unavailable"}, keep=None, relations=relations, decisions=elements)
    return new, {k: entry[k] for k in REMOVED_FIELDS if k in entry}


def windows_of(chain):
    """`windows[]` from the legacy chain string, oldest first; the unknown fields are null."""
    found = CHAIN.findall(chain or "")
    if not found:
        raise MigrationError(f"WINDOW_UNPARSED: {chain!r} holds no 'census … ending <date>'")
    out = []
    for days, end in reversed(found):
        start = (datetime.date.fromisoformat(end) - datetime.timedelta(days=int(days))).isoformat() if days else None
        out.append({"start": start, "end": end, "run_id": f"legacy-{end}", "kind": "legacy", "commit": None,
                    "accounted": None, "fully_read": None})
    return out


def migrate(ledger):
    """(the schema 2 ledger, the removed values). A schema 2 ledger is its own migration."""
    if ledger.get("schema") == 2:
        return copy.deepcopy(ledger), {}
    if ledger.get("schema") != 1:
        raise MigrationError(f"LEDGER_SCHEMA_UNSUPPORTED schema {ledger.get('schema')!r}")
    unknown = sorted(set(ledger) - {"schema", "framework", "window", "entries"})
    if unknown:
        raise MigrationError(f"FIELD_UNMAPPED ledger: top-level {unknown}")
    entries, removed = [], {}
    windows = windows_of(ledger.get("window"))
    for entry in ledger["entries"]:
        new, gone = migrate_entry(entry, windows[-1]["end"])
        entries.append(new)
        if gone:
            removed[entry["id"]] = gone
    removed["_ledger"] = {"window": ledger.get("window")}
    migrated = {"schema": 2, "framework": ledger["framework"], "windows": windows, "entries": entries}
    problems = ledger_lib.validate_ledger(migrated)
    if problems:
        raise MigrationError("MIGRATION_INVALID: " + "; ".join(problems[:5]))
    return migrated, removed
