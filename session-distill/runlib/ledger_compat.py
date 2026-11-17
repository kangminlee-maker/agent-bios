#!/usr/bin/env python3
"""The read path the old ledger consumers keep (plan S-4): a derived projection, never stored.

Schema 2 moves `placed`, `placed_anchor` and `implementation` out of the entry (design §12.2). A
consumer written for schema 1 reads them as entry fields; `placed_entries` hands it those fields,
derived from either schema version. Schema 1 passes through untouched, so a consumer switched to
this module reads the unmigrated ledger exactly as it did, and the migrated one the same way.
Nothing here is written back: a second copy of a field would be a second authority.

The projection's six fields come from the entry alone — `destination.anchor` and
`destination.package_id`, and the `status`, `learning_id` and `classification` design §12.2 keeps.
It reads no `decisions[]` element, because an `applied` record carries none of the six; that the
schema 1 values land in `destination` and on the latest place decision is the migration's
guarantee, held by `migrate-ledger.py`'s own self-test
(design/session-distill/2026-10-21T1009--a04f78a--plan-addendum-wp13-correction-2.md §1).

The consumers are listed as data in `tables/ledger_readers.json`: `learn/build-promotions.py` reads
this projection; `compose/instructions-state.py` and `learn/ingest-learnings-export.py` read only
fields §12.2 keeps and need no projection.

  ledger_compat.py --self-test
"""
import copy
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


class CompatError(Exception):
    """A ledger this projection cannot read; the message starts with LEDGER_SCHEMA_UNSUPPORTED."""


def placed_entries(ledger):
    """`{id, status, learning_id, placed_anchor, placed_package_id, classification}` for every entry
    whose status is `placed`, in ledger order. An absent field is None."""
    version = ledger.get("schema")
    if version not in (1, 2):
        raise CompatError(f"LEDGER_SCHEMA_UNSUPPORTED schema {version!r}: the projection reads schema 1 and 2")
    out = []
    for entry in ledger.get("entries", []):
        if not isinstance(entry, dict) or entry.get("status") != "placed":
            continue
        home = (entry.get("destination") or {}) if version == 2 else {}
        out.append({
            "id": entry.get("id"), "status": "placed", "learning_id": entry.get("learning_id"),
            "placed_anchor": home.get("anchor") if version == 2 else entry.get("placed_anchor"),
            "placed_package_id": home.get("package_id") if version == 2 else entry.get("placed_package_id"),
            "classification": entry.get("classification"),
        })
    return out


def self_test():
    failures = []
    legacy = {"schema": 1, "entries": [
        {"id": "S9-01", "status": "placed", "learning_id": "lid-1", "placed_anchor": "a.md", "placed_package_id": "@x/y", "classification": {"type": "A"}},
        {"id": "S9-02", "status": "incubating", "learning_id": "lid-2", "placed_anchor": "b.md"},
        {"id": "S4-01", "status": "placed"},
        "not an entry"]}
    current = {"schema": 2, "entries": [
        {"id": "S9-01", "status": "placed", "learning_id": "lid-1", "classification": {"type": "A"},
         "destination": {"implementation": "a.md §x", "anchor": "a.md", "package_id": "@x/y"}},
        {"id": "S9-02", "status": "incubating", "learning_id": "lid-2", "destination": None},
        {"id": "S4-01", "status": "placed", "destination": None}]}
    want = [
        {"id": "S9-01", "status": "placed", "learning_id": "lid-1", "placed_anchor": "a.md", "placed_package_id": "@x/y", "classification": {"type": "A"}},
        {"id": "S4-01", "status": "placed", "learning_id": None, "placed_anchor": None, "placed_package_id": None, "classification": None}]
    for label, ledger in (("schema 1", legacy), ("schema 2", current)):
        if placed_entries(ledger) != want:
            failures.append(f"{label}: the projection is {placed_entries(ledger)}, expected {want}")
    before = copy.deepcopy(current)
    placed_entries(current)
    if current != before:
        failures.append("the projection changed the ledger it read")
    if [e["id"] for e in placed_entries(legacy)] != ["S9-01", "S4-01"]:
        failures.append("an incubating entry or a non-entry was projected")
    for label, ledger in (("no schema", {"entries": []}), ("a future schema", {"schema": 3, "entries": []})):
        try:
            placed_entries(ledger)
            failures.append(f"{label}: the projection read a ledger it does not know")
        except CompatError as exc:
            if "LEDGER_SCHEMA_UNSUPPORTED" not in str(exc):
                failures.append(f"{label}: refused without the code: {exc}")
    moved = copy.deepcopy(current)
    moved["entries"][0]["destination"] = None
    if placed_entries(moved)[0]["placed_anchor"] is not None:
        failures.append("a destination removed from a schema 2 entry still projected an anchor")
    for failure in failures:
        print(f"ledger_compat --self-test [FAIL] {failure}")
    if failures:
        return 1
    print("ledger_compat --self-test: OK (schema 1 passthrough and schema 2 projection agree, an unknown schema is refused by name)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: ledger_compat.py --self-test")
    sys.exit(self_test())
