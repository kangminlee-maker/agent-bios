#!/usr/bin/env python3
"""The ledger of the session distill: schema 2, transitions, events, the id-set check, the atomic write.

`design/session-distill/ledger.json` moves to schema 2 at the cutover (design §12.1-§12.4); until
then it is schema 1 and every function here reads both. The pieces:

  validate_ledger      schema 1: the structure the legacy merge keeps (entries with unique ids and
                       a status). Schema 2: `schemas/ledger.schema.json` through `validate.py`, then
                       the rules a schema cannot say: unique ids and decision runs, an approval row
                       on every run decision, the §7.2 vocabulary and none of §12.2's metadata on
                       every decision a run made, the structural rules of §7.3 (an incubate with its observation,
                       a keep or a drop with its reason), resolutions on the decision they resolve,
                       relations that resolve, exactly one evidence form per evidence item, and a
                       history that replays through the table to the status the entry holds.
  check_pair           the id-set check of design §12.4 over a frozen base and a head ledger: no id
                       lost, new ids exactly those allocated (a schema 2 run that writes at all needs
                       the allocation it froze; only a schema 1 ledger may continue its numbering),
                       every changed row bound to an applied decision whose disposition licenses that
                       field, every new row bound to the
                       decision that created it, decisions append-only. Schema 1 to schema 2 is
                       judged by equality with the migration.
  transition, events   design §12.3, read from `tables/transitions.json`. `render_cell` writes the
                       design's cell wording back from the data, and the self-test holds that wording
                       and the event rows against the design's tables. `apply_decision` and
                       `create_entry` append one decisions[] element, move the status by the table and
                       check the effects the cell requires; `record_event` carries the five events. A
                       revert restores the status derived from the entry's own history (`replays`); a
                       migrated entry's history starts at the status its `legacy_migration` element records.
  write_atomic         lock, expected base hash, temporary file, fsync, rename, all confined beneath
                       the ledger's directory.

  ledger.py --check [--ledger FILE] [--base REV] [--worktree] [--allocated ID,ID]
  ledger.py --generate-transition-fixtures
  ledger.py --self-test

`--check` compares the ledger in the index (`--worktree`: on disk) with its content at REV (HEAD by
default). Exit 0 holds; 1 a violation; 2 a side git could not read, because a gate that judged
nothing has not passed (design/session-distill/2026-10-21T0455--9410a1d--plan-addendum-wp14.md).
Failures are named by their first word.
"""
import argparse
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import stagelock, validate

HERE = pathlib.Path(__file__).resolve().parents[1]  # session-distill/
REPO = HERE.parent
LEDGER_REL = "design/session-distill/ledger.json"
SCHEMA_PATH = HERE / "schemas" / "ledger.schema.json"
EO_SCHEMA_PATH = HERE / "schemas" / "expected_observation.schema.json"
TRANSITIONS_PATH = HERE / "tables" / "transitions.json"
FIXTURES_PATH = HERE / "tables" / "transition_fixtures.json"
LOCK_ROOT = HERE / "out" / "ledger-lock"  # untracked: `session-distill/out/*/` is ignored
MIGRATOR = HERE / "migrate-ledger.py"
GATE_READERS = REPO / "gates" / "check-global-file.py"  # the git readers of design §13.1's gate, reused

SUPPORTED = (1, 2)
ID_SERIES = re.compile(r"^([A-Z]+[0-9]*)-([0-9]+)$")
# Fields whose growth needs no decision: design §12.3's recurrence event ("evidence and lineages
# appended"). A list among them only ever grows at its end.
EVENT_FIELDS = ("recurrence", "evidence", "independent_lineages", "coverage")
APPEND_ONLY = ("recurrence", "evidence")
TEXT_FIELDS = ("lesson", "principle", "rationale")  # what "text revised" revises
# What each disposition of design §7.2 licenses on its entry, besides the status the table moves and
# the disposition the entry takes from it (ADDENDUM §3). A disposition that changes nothing installed
# — `none`, and design §12.3's incubated or dropped intervention — licenses neither the entry's text
# nor its destination. The identity and the provenance of an entry (id, learning_id, source,
# surfaced, window, baseline_ref) are licensed by no disposition at all.
CLASSIFYING_FIELDS = ("kind", "diagnosis", "classification", "note", "domain")
DISPOSITION_FIELDS = {
    "place": TEXT_FIELDS + ("destination", "relations") + CLASSIFYING_FIELDS,
    "correct": TEXT_FIELDS + ("destination",) + CLASSIFYING_FIELDS,
    "re-deliver": ("destination",) + CLASSIFYING_FIELDS,
    "keep": ("keep",) + CLASSIFYING_FIELDS,
    "reduce": ("absorbed_by", "relations", "retired", "retire_reason") + CLASSIFYING_FIELDS,
    "incubate": CLASSIFYING_FIELDS,
    "drop": ("retired", "retire_reason") + CLASSIFYING_FIELDS,
    "none": (),
}
# What a cell's effect needs the entry to gain or lose, over what its disposition licenses.
EFFECT_FIELDS = {"keep_record": ("keep",), "absorbed_by": ("absorbed_by",), "allocate_destination_entry": ("absorbed_by",),
                 "text_revised": TEXT_FIELDS, "never_placed": ("destination",),
                 "revival": ("retired", "retire_reason", "absorbed_by")}
# A revert restores what the application it undoes recorded: design §12.1's `applied` carries `before`,
# the values the row held for every field that application changed (the owner's decision of 2026-10-21,
# in RECORD below). Six review rounds of inferring those values from the history each found a case the
# inference got wrong, so nothing is inferred here: an application that changes a row records what it
# replaced, and a revert with no such record to read is refused by name.
REVERTIBLE = tuple(sorted({f for fields in DISPOSITION_FIELDS.values() for f in fields}))
NULLABLE = ("destination", "keep", "classification")  # design §12.1 keeps these on every entry, null when it has none
EMPTY_BEFORE = {"fields": {}, "absent": []}
LEGACY_KINDS = ("legacy_application", "legacy_retirement", "legacy_migration")
# Design §12.2's metadata: what an element the migration produced carries and a decision of a run
# never does (ADDENDUM §1-§2). `contract_problems` holds this list against the schema's own marks.
LEGACY_PROPERTIES = ("at", "field", "legacy_text", "legacy_placed", "legacy_status", "status_note")
LEGACY_MARK = "design §12.2, a migrated element only"  # what marks one of them in the schema
LEGACY_REQUIRED = ("at", "field", "legacy_text")  # design §12.2: what every migrated element carries
UNAPPROVED = ("legacy", "unavailable")  # approval_id values that record no approval row
EMPTY_SHA = hashlib.sha256(b"").hexdigest()
# What schema 2 carries beyond design §12.1, with each property's reader and its reason: the record
# the plan's one-authority rule asks for. `addendum_problems` holds it against this module.
ADDENDUM = "design/session-distill/2026-10-21T0820--9b42df2--plan-addendum-wp13.md"
# The owner's decision on how a revert knows what to put back, with the rules that hold a recorded
# value complete — no missing record read as an empty one, no field recorded as both held and
# absent, no migrated element carrying one — and how the two rows of a merge are paired: by the
# entry, the run and the operation, and by replaying what each appended revert actually undoes. It
# also owns where that contract is held: the writer, against the bytes it would replace.
RECORD = "design/session-distill/2026-10-21T1545--b324de5--writer-holds-the-transaction.md"
# A property schema 2 gained after ADDENDUM, each contracted by a dated record of its own: a dated record is
# written once, so a later property is not added to ADDENDUM's text. `field_record_problems` holds each
# against this module the way `addendum_problems` holds ADDENDUM.
FIELD_RECORDS = {"resolves": "design/session-distill/2026-11-06T0558--01eaddf--a-decision-names-the-incubate-it-resolves.md"}
SUPERSEDED = "design/session-distill/2026-10-21T1420--428724d--merge-pair-identity.md"


class LedgerError(Exception):
    """A refusal; the message starts with the named code."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def render(ledger):
    """The bytes a ledger file holds: the legacy layout (indent 1, insertion order, UTF-8)."""
    return json.dumps(ledger, ensure_ascii=False, indent=1) + "\n"


def parse(raw, where="ledger"):
    try:
        ledger = json.loads(raw)
    except ValueError as exc:
        raise LedgerError(f"LEDGER_UNREADABLE {where}: {exc}") from exc
    if not isinstance(ledger, dict):
        raise LedgerError(f"LEDGER_UNREADABLE {where}: the top level is not an object")
    return ledger


def version(ledger):
    found = ledger.get("schema")
    if found not in SUPPORTED:
        raise LedgerError(f"LEDGER_SCHEMA_UNSUPPORTED schema {found!r}; supported {list(SUPPORTED)}")
    return found


def schema():
    """The schema-2 document, `schemas/ledger.schema.json`."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


_VALIDATOR = {}


def validator():
    if "v" not in _VALIDATOR:
        _VALIDATOR["v"] = validate.compile_schema(schema())
    return _VALIDATOR["v"]


def vocabulary(name):
    """An enumeration of the schema: `disposition`, `legacy_disposition`, or an entry property."""
    defs = schema()["$defs"]
    return list(defs[name]["enum"]) if name in defs else list(defs["entry"]["properties"][name]["enum"])


# ---------------------------------------------------------------- validation

def is_legacy(element):
    """A legacy element: one design §12.2 migrates from a schema 1 field, not a run's decision."""
    return element["run"].startswith("legacy-") or element.get("kind") in LEGACY_KINDS


def entry_row(entry):
    """The table row of an entry no decision has made yet: a gap is a new learning, every other kind
    (and an unclassified legacy one) comes from a unit of the library or from the intake."""
    return "no_entry_new_learning" if entry["kind"] in ("gap", "unclassified") else "no_entry_existing_unit"


def element_problems(eid, n, element):
    """The rules of one decisions[] element that the schema cannot say."""
    tag, problems = f"{eid} decisions[{n}]", []
    if is_legacy(element):
        problems += [f"LEGACY_ELEMENT_INCOMPLETE {tag}: a legacy element carries {k} (design §12.2)" for k in LEGACY_REQUIRED if k not in element]
        if element.get("kind") == "legacy_migration" and "legacy_status" not in element:
            problems.append(f"LEGACY_ELEMENT_INCOMPLETE {tag}: a legacy_migration element carries legacy_status, the status the entry had when it was migrated")
        if "legacy_status" in element and element.get("kind") != "legacy_migration":
            problems.append(f"LEGACY_STATUS_MISPLACED {tag}: legacy_status belongs to an element of kind legacy_migration")
        if element.get("kind") == "revert":
            problems.append(f"LEGACY_KIND_ON_REVERT {tag}: a revert is a decision a run made, not an element the migration produced")
        if "legacy_placed" in element and (element["applied"] is None or element.get("kind") in ("legacy_retirement", "legacy_migration")):
            problems.append(f"LEGACY_PLACED_MISPLACED {tag}: legacy_placed is the date of the application the element itself carries "
                            f"(design §12.2), and this element carries none")
        if before_of(element) is not None:
            problems.append(f"LEGACY_BEFORE {tag}: applied.before is what a run's application records about the row it changed; the "
                            f"migration replaced nothing (RECORD)")
        if "resolves" in element:
            problems.append(f"RESOLVES_ON_LEGACY {tag}: resolves is what a run's decision names; the migration resolved nothing "
                            f"(design §7.1, {FIELD_RECORDS['resolves']})")
        return problems
    run, disposition = element["run"], element["disposition"]
    if element["approval_id"] in UNAPPROVED:
        problems.append(f"DECISION_UNAPPROVED {tag}: run {run!r} carries approval_id {element['approval_id']!r}, which is no approval row")
    if disposition not in vocabulary("disposition"):
        problems.append(f"DISPOSITION_NOT_CURRENT {tag}: {disposition!r} is outside design §7.2's vocabulary, which only a legacy element may leave")
    problems += [f"LEGACY_FIELD_ON_MODERN {tag}: {k} belongs to a legacy element" for k in LEGACY_PROPERTIES if k in element]
    if disposition == "incubate" and element["expected_observation"] is None:
        problems.append(f"INCUBATE_WITHOUT_OBSERVATION {tag}: an incubate carries its observation and expiry (design §7.3)")
    if disposition in ("keep", "drop") and not element.get("reason"):
        problems.append(f"REASON_REQUIRED {tag}: a {disposition} carries its reason (design §7.3)")
    if element.get("kind") == "revert" and (disposition != "none" or element["applied"] is None):
        problems.append(f"REVERT_MALFORMED {tag}: a revert is an applied decision with disposition none")
    problems += before_overlap(tag, before_of(element))
    return problems


def resolves_problems(entry):
    """Design §7.1's `resolves` over one entry: a run's decision names an incubate decision an earlier run made on the
    same entry, as `<entry id>@<run>`, and no incubate is resolved twice. Each break by name."""
    problems, eid, resolved = [], entry["id"], {}
    runs = {d["run"]: n for n, d in enumerate(entry["decisions"]) if not is_legacy(d)}
    for n, element in enumerate(entry["decisions"]):
        target = element.get("resolves")
        if target is None or is_legacy(element):
            continue
        tag = f"{eid} decisions[{n}]"
        owner, _, run = target.partition("@")
        if owner != eid:
            problems.append(f"RESOLVES_OTHER_ENTRY {tag}: it resolves {target!r}, a decision of another entry; a decision resolves "
                            "the incubate of its own entry")
            continue
        at = runs.get(run)
        if at is None:
            problems.append(f"RESOLVES_DANGLING {tag}: no decision of run {run!r} on {eid} is there to resolve")
            continue
        if at >= n:
            problems.append(f"RESOLVES_NOT_EARLIER {tag}: it resolves {target!r} at decisions[{at}], which is not an earlier decision")
            continue
        if entry["decisions"][at]["disposition"] != "incubate":
            problems.append(f"RESOLVES_NOT_INCUBATE {tag}: {target!r} is a {entry['decisions'][at]['disposition']}, and only an "
                            "incubate is pending")
            continue
        if target in resolved:
            problems.append(f"RESOLVES_TWICE {tag}: {target!r} was resolved at decisions[{resolved[target]}] already")
            continue
        resolved[target] = n
    return problems


def unresolved_incubates(ledger):
    """Design §7.1's pending incubate decisions: every incubate a run decided (an incubating entry, or a pending
    intervention on a placed one, §12.3) that no later decision of its entry resolves, by id `<entry>@<run>`, with its
    expiry and its entry's status, in id order. Asked of a ledger `validate_ledger` passed."""
    out = []
    for entry in ledger["entries"]:
        resolved = {d["resolves"] for d in entry["decisions"] if not is_legacy(d) and d.get("resolves")}
        for element in entry["decisions"]:
            if is_legacy(element) or element["disposition"] != "incubate":
                continue
            ident = f"{entry['id']}@{element['run']}"
            if ident not in resolved:
                out.append({"decision_id": ident, "entry": entry["id"], "run": element["run"], "status": entry["status"],
                            "expiry": element["expected_observation"]["expiry"]})
    return sorted(out, key=lambda d: d["decision_id"])


def semantic_v2(ledger):
    """What `schemas/ledger.schema.json` cannot say about a schema 2 ledger."""
    problems, seen_ids, seen_runs = [], set(), set()
    ids = {e["id"] for e in ledger["entries"]}
    for window in ledger["windows"]:
        if window["run_id"] in seen_runs:
            problems.append(f"WINDOW_DUPLICATE {window['run_id']}")
        seen_runs.add(window["run_id"])
    for entry in ledger["entries"]:
        eid = entry["id"]
        if eid in seen_ids:
            problems.append(f"ID_DUPLICATE {eid}")
        seen_ids.add(eid)
        runs = set()
        for n, element in enumerate(entry["decisions"]):
            problems += element_problems(eid, n, element)
            if not is_legacy(element):
                if element["run"] in runs:
                    problems.append(f"DECISION_RUN_DUPLICATE {eid} decisions[{n}]: run {element['run']!r} decided this entry twice")
                runs.add(element["run"])
            for resolution in (element["expected_observation"] or {}).get("resolutions", []):
                if resolution["run"] != element["run"]:
                    problems.append(f"RESOLUTION_MISPLACED {eid} decisions[{n}]: a resolution of run "
                                    f"{resolution['run']!r} sits under run {element['run']!r}")
        problems += resolves_problems(entry)
        for field, target in (("absorbed_by", entry.get("absorbed_by")), ("instance_of", entry["relations"].get("instance_of"))):
            if target is not None and target not in ids:
                problems.append(f"RELATION_DANGLING {eid} {field}: {target!r} is no entry of this ledger")
        migrations = [n for n, d in enumerate(entry["decisions"]) if d.get("kind") == "legacy_migration"]
        if len(migrations) > 1:
            problems.append(f"LEGACY_MIGRATION_DUPLICATE {eid}: {len(migrations)} legacy_migration elements; an entry is migrated once")
        modern_at = [n for n, d in enumerate(entry["decisions"]) if not is_legacy(d)]
        if migrations and modern_at and migrations[0] > modern_at[0]:
            problems.append(f"LEGACY_MIGRATION_LATE {eid} decisions[{migrations[0]}]: the migration element follows the run decision at decisions[{modern_at[0]}]")
        for n, item in enumerate(entry["evidence"]):
            if ("claim_id" in item) == ("locator" in item):
                problems.append(f"EVIDENCE_FORM {eid} evidence[{n}]: exactly one of a claim id with its evidence id, or the unavailable form")
        if not replays(entry, entry["status"]):
            problems.append(f"HISTORY_INCONSISTENT {eid}: the entry's decisions do not replay through design §12.3 to its status {entry['status']!r}")
    return problems


def validate_ledger(ledger):
    """Every violation of `ledger` as a list of strings, each starting with its code."""
    try:
        found = version(ledger)
    except LedgerError as exc:
        return [str(exc)]
    if found == 1:
        entries = ledger.get("entries")
        if not isinstance(entries, list):
            return ["LEDGER_INVALID entries: schema 1 holds a list of entries"]
        problems, seen = [], set()
        for n, entry in enumerate(entries):
            if not (isinstance(entry, dict) and isinstance(entry.get("id"), str) and isinstance(entry.get("status"), str)):
                problems.append(f"LEDGER_INVALID entries[{n}]: an entry needs a string id and status")
            elif entry["id"] in seen:
                problems.append(f"ID_DUPLICATE {entry['id']}")
            else:
                seen.add(entry["id"])
        return problems
    problems = [f"LEDGER_INVALID {line}" for line in validate.validate_instance(validator(), ledger)]
    return problems or semantic_v2(ledger)


def entry_ids(ledger):
    return [e["id"] for e in ledger["entries"]]


# ---------------------------------------------------------------- the id-set check

def id_set_violations(base_ids, head_ids, allocated=None, numbered=False, transaction=False):
    """Design §12.4: no id lost, and the new ids exactly the allocated ones.

    `allocated` is the id list the run froze before it began. A schema 2 run that writes the ledger
    at all (`transaction`) needs it, whether or not the ids it added turn out to be none: an
    allocation that produced no row is a violation the check can see (`ID_ALLOCATED_MISSING`), and
    an absent allocation says nothing at all. An explicit empty list is an allocation; `None` is the
    absence of one (`ALLOCATION_REQUIRED`). Validating a ledger against nothing — a head with no
    base — is not a transaction and asks for none. Only a schema 1 ledger (`numbered`) may add ids
    without an allocation: the legacy merge has no record, so a series (`S3`, `G`, `L`) continues at
    the base's highest number, none skipped. A duplicate id is the validator's finding."""
    problems = [f"ID_LOST {i}: present in the base, absent from the ledger" for i in sorted(set(base_ids) - set(head_ids))]
    new = sorted(set(head_ids) - set(base_ids))
    if allocated is not None:
        problems += [f"ID_UNALLOCATED {i}: not among the allocated ids" for i in new if i not in allocated]
        problems += [f"ID_ALLOCATED_EXISTING {i}: allocated as new, and the base already holds it" for i in sorted(set(allocated) & set(base_ids))]
        problems += [f"ID_ALLOCATED_MISSING {i}: allocated, absent from the ledger" for i in sorted(set(allocated) - set(base_ids) - set(new))]
        return problems
    if not numbered:
        return problems + ([f"ALLOCATION_REQUIRED {new or '[]'}: a schema 2 run writes the ledger only against the allocation it froze"]
                           if new or transaction else [])
    top = {}
    for i in base_ids:
        found = ID_SERIES.match(i)
        if found:
            top[found.group(1)] = max(top.get(found.group(1), 0), int(found.group(2)))
    by_series = {}
    for i in new:
        found = ID_SERIES.match(i)
        by_series.setdefault(found.group(1) if found else None, []).append((int(found.group(2)) if found else 0, i))
    for series, members in by_series.items():
        if series is None:
            problems += [f"ID_UNALLOCATED {i}: not an id of the form <series>-<number>" for _, i in members]
            continue
        want = set(range(top.get(series, 0) + 1, top.get(series, 0) + 1 + len(members)))
        problems += [f"ID_UNALLOCATED {i}: series {series} continues at {top.get(series, 0) + 1} with no number skipped"
                     for number, i in members if number not in want]
    return problems


# ---------------------------------------------------------------- transitions

_TABLES = {}


def transitions():
    if "t" not in _TABLES:
        _TABLES["t"] = json.loads(TRANSITIONS_PATH.read_text(encoding="utf-8"))
    return _TABLES["t"]


EFFECT_WORDING = {
    "never_placed": " (never placed)", "text_revised": " (text revised)", "expiry_renewed": " (expiry renewed)",
    "revival": " (revival)", "keep_record": ", keep record", "pending_intervention": ", pending intervention",
    "dropped_intervention": ", dropped intervention",
    "allocate_destination_entry": "; destination entry allocated (placed) if it has none",
    "absorbed_by": " (`absorbed_by`)", "receiver_merge_decision": "; the receiving entry gets a merge decision",
}


def render_cell(cell):
    """The wording design §12.3 gives a table cell, written from the cell's record."""
    if cell is None:
        return "—"
    if cell["status"] is None:
        return "no entry"
    unknown = [e for e in cell["effects"] if e not in EFFECT_WORDING]
    if unknown:
        raise LedgerError(f"TRANSITION_EFFECT_UNKNOWN {unknown}: no wording for it in the design's table")
    return ("new entry, " if cell["new_entry"] else "") + cell["status"] + "".join(EFFECT_WORDING[e] for e in cell["effects"])


def disposition_key(element):
    """The table column of a decision: `reduce` is a merge when an operation of it merges."""
    if element["disposition"] != "reduce":
        return element["disposition"]
    merged = any(op["type"] == "merge" for op in (element["applied"] or {"operations": []})["operations"])
    return "reduce_merge" if merged else "reduce_delete"


def transition(row, key):
    """The cell for `row` and column `key`; `TRANSITION_DISALLOWED` for a pair the design marks —."""
    table = transitions()
    if key not in table["dispositions"] or row not in table["cells"]:
        raise LedgerError(f"TRANSITION_DISALLOWED {row} + {key}: the table has no such row or column")
    cell = table["cells"][row][key]
    if cell is None:
        raise LedgerError(f"TRANSITION_DISALLOWED {row} + {key}: design §12.3 allows no such pair")
    return cell


def row_of(status):
    return transitions()["state_rows"][status]


def status_after(status, cell):
    return status if cell["status"] in (None, "unchanged") else cell["status"]


def takes_effect(element):
    """An applied decision: its operations completed, so it moves the status and licenses its row's
    changes, whatever its delivery check then found. Design §10.6 records an application whose
    delivery failed or did not run as applied, "not lost", and leaves the owner to keep, revert or
    revise it; design §12.3's delivery row leaves that application unchanged —
    `decisions[].applied.delivery` records the outcome and moves nothing further (ADDENDUM §3)."""
    return element["applied"] is not None


def revive(entry):
    """A revived entry (placed or incubating again) no longer holds the retirement or the absorption."""
    for field in ("retired", "retire_reason", "absorbed_by"):
        entry.pop(field, None)


def effect_problems(cell, element, before, after, rows):
    """What a cell's effects require of the result of `element`. `before` is the entry as it was (None
    for an entry the decision creates), `after` as it is now, `rows` every entry of the ledger by id."""
    eid, problems = after["id"], []
    receiver = rows.get(after.get("absorbed_by"))
    observation = element["expected_observation"]
    for token in cell["effects"]:
        if token == "keep_record":
            missing = after["keep"] is None or not element.get("reason")
            what = "the entry's keep record and the decision's reason"
        elif token == "absorbed_by":
            missing, what = receiver is None, "the receiving entry's id, an entry of the ledger"
        elif token == "receiver_merge_decision":
            missing = receiver is None or receiver["status"] != "placed" or not any(
                d["run"] == element["run"] and any(op["type"] == "merge" for op in (d["applied"] or {"operations": []})["operations"])
                for d in receiver["decisions"])
            what = "a decision of this run on a placed receiving entry that carries the merge"
        elif token == "allocate_destination_entry":
            missing, what = receiver is None or receiver["status"] != "placed", "a placed receiving entry"
        elif token == "pending_intervention":
            missing, what = element["disposition"] != "incubate" or observation is None, "an incubate with its observation and expiry"
        elif token == "dropped_intervention":
            missing, what = element["disposition"] != "drop" or not element.get("reason"), "a drop with its reason"
        elif token == "never_placed":
            missing, what = after["destination"] is not None, "an entry with no destination"
        elif token == "text_revised":
            missing, what = before is None or all(before.get(k) == after.get(k) for k in TEXT_FIELDS), "a revised lesson, principle or rationale"
        elif token == "expiry_renewed":
            earlier = [d["expected_observation"]["expiry"] for d in (before or after)["decisions"] if d["expected_observation"] and d is not element]
            missing = observation is None or (bool(earlier) and observation["expiry"] <= max(earlier))
            what = "an observation whose expiry is later than every earlier one"
        elif token == "revival":
            missing, what = any(k in after for k in ("retired", "retire_reason", "absorbed_by")), "an entry that is no longer retired or absorbed"
        else:
            raise LedgerError(f"TRANSITION_EFFECT_UNKNOWN [{token!r}]: no check for it")
        if missing:
            problems.append(f"EFFECT_MISSING {eid}: {token} needs {what}")
    return problems


def licensed_fields(element, cell):
    """The entry fields `element` licenses besides its status and its disposition: what design §7.2's
    disposition changes, widened by exactly what the cell's own effects need (ADDENDUM §3)."""
    fields = set(DISPOSITION_FIELDS.get(element["disposition"], ()))
    for token in cell["effects"]:
        fields |= set(EFFECT_FIELDS.get(token, ()))
    return fields


def reverted(entry, status):
    """The decision a revert of `entry` undoes and the status it restores: the latest decision that took
    effect and is not already reverted, and the status the entry held before it, both derived from the
    entry's own decisions[] through design §12.3's table (`replays`). `entry` holds the decisions before
    the revert and `status` the status it has now. A history that leaves the status open is refused
    rather than guessed, and one that does not replay to `status` at all is refused too."""
    fits = replays(entry, status)
    if not fits:
        raise LedgerError(f"REPLAY_INCONSISTENT {entry['id']}: the decisions do not replay to {status!r}")
    # Which decision is the one to revert does not depend on where the history started: every fit
    # pushes the same applied decisions and pops on the same reverts, so the stacks are equal. What
    # the start does decide is the status before that decision, which is why only that is open below.
    if not fits[0]["stack"]:
        raise LedgerError(f"REVERT_NOTHING {entry['id']}: no applied decision is left to revert")
    stack = fits[0]["stack"]
    index = stack[-1]
    priors = sorted({str(fit["before"][index]) for fit in fits})
    if len(priors) > 1:
        raise LedgerError(f"REVERT_PRIOR_STATUS_AMBIGUOUS {entry['id']}: the history leaves {priors} open for the status before that decision")
    if priors == ["None"]:
        raise LedgerError(f"REVERT_PRIOR_STATUS_NONE {entry['id']}: the decision created the entry; there is no status before it to restore")
    return entry["decisions"][index], priors[0]


def before_record(was, now):
    """The values `was` held for every field `now` changed: design §12.1's `applied.before` (RECORD).
    `fields` carries what was there and `absent` names the fields the row had none of, which is not the
    same answer — a row that held no destination and one whose destination this application replaced
    are undone differently."""
    fields, absent = {}, []
    for field in REVERTIBLE:
        if was.get(field) == now.get(field):
            continue
        (absent.append(field) if was.get(field) is None else fields.update({field: copy.deepcopy(was[field])}))
    return {"fields": fields, "absent": sorted(absent)}


def before_of(element):
    """The `before` record of an applied decision, or None when it carries none."""
    return (element["applied"] or {}).get("before")


def restore(entry, before):
    """Put `before` back on `entry`: its values where the row had them, and nothing where it had none."""
    entry.update(copy.deepcopy(before["fields"]))
    for field in before["absent"]:
        if field in NULLABLE:
            entry[field] = None
        else:
            entry.pop(field, None)


def revert_restored(was, now, recorded):
    """What a revert left undone: a field the application recorded as replaced that the row does not
    hold again, and one the row had none of that it still holds."""
    problems = [f"REVERT_NOT_RESTORED {now['id']} {field}: the application recorded {value!r} as what it replaced, the row holds {now.get(field)!r}"
                for field, value in recorded["fields"].items() if now.get(field) != value]
    return problems + [f"REVERT_NOT_RESTORED {now['id']} {field}: the row held none before the application and holds {now.get(field)!r}"
                       for field in recorded["absent"] if now.get(field) is not None]


def before_overlap(tag, recorded):
    """A field in both parts of a before record: the row held a value there or it did not, never both,
    and `restore` would put the value back and clear it in one pass (RECORD)."""
    both = sorted(set((recorded or EMPTY_BEFORE)["fields"]) & set((recorded or EMPTY_BEFORE)["absent"]))
    return [f"BEFORE_FIELD_OVERLAP {tag} {both}: its applied.before records a value there and records that the row held none"] if both else []


def before_required(tag, element):
    """Every application records what it replaced, an empty record when that was nothing (RECORD).
    A missing record is the one case a revert cannot read, so it is refused where it is appended
    rather than where it is read."""
    return [] if before_of(element) is not None else [
        f"BEFORE_MISSING {tag}: an applied decision records what it replaced in applied.before, an empty record when it replaced nothing"]


def before_problems(tag, recorded, want):
    """`recorded` against the row change it claims to describe (RECORD): a field the application changed
    and the record does not name, one it names and the application did not change, and one whose value
    is not what the row held."""
    recorded = recorded or EMPTY_BEFORE
    held, wanted = dict(recorded["fields"]), dict(want["fields"])
    missing = (set(wanted) | set(want["absent"])) - (set(held) | set(recorded["absent"]))
    extra = (set(held) | set(recorded["absent"])) - (set(wanted) | set(want["absent"]))
    problems = [f"BEFORE_FIELD_MISSING {tag} {f}: the application changed it and its applied.before does not say what it replaced"
                for f in sorted(missing)]
    problems += [f"BEFORE_FIELD_EXTRA {tag} {f}: its applied.before says what it replaced there and the application did not change it"
                 for f in sorted(extra)]
    problems += [f"BEFORE_FIELD_WRONG {tag} {f}: its applied.before says {held.get(f, 'absent')!r}, the row held {wanted.get(f, 'absent')!r}"
                 for f in sorted((set(held) | set(recorded["absent"])) & (set(wanted) | set(want["absent"])))
                 if held.get(f, "\0absent") != wanted.get(f, "\0absent")]
    return problems


def reverted_before(entry, status):
    """The decision a revert of `entry` undoes, the status it restores, and the row values it puts back.

    The values are the ones that application recorded (`applied.before`); nothing is inferred from the
    history (RECORD). A decision that recorded none — an element design §12.2 migrated carries no
    `before`, and so does a row written by hand — can have its status reverted and its fields not, so
    unless it changed nothing the revert is refused by name."""
    undone, prior = reverted(entry, status)
    recorded = before_of(undone)
    if recorded is None:
        raise LedgerError(f"REVERT_INVERSE_UNPROVABLE {entry['id']} applied.before: the application of run {undone['run']!r} did not "
                          f"record the values it replaced, so what its fields were before it is not in the ledger")
    # No decision still standing can have changed the same field after this one: a revert undoes the
    # latest standing decision and each earlier one is still covered by the value this record holds,
    # so the order is last in, first out. Two rows are the one place where that does not hold by
    # itself, and `merge_receiver` is where it is checked (RECORD).
    return undone, prior, recorded


def merge_receiver_element(element, absorbed_id, before=None):
    """The decision the receiving entry of a merge gets: its unit is revised by the merge, so the
    decision carries the merge's own operations and what it replaced on this row (RECORD)."""
    receiver = copy.deepcopy(element)
    receiver.update(disposition="correct", reason=f"receives the merge of {absorbed_id}", expected_observation=None)
    receiver["applied"] = {**receiver["applied"], "before": copy.deepcopy(before or EMPTY_BEFORE)}
    return receiver


def merge_receiver_revert(element, absorbed_id, before=None):
    """The decision the receiving entry gets when the merge it received is reverted: the merge revised
    its unit, so reverting the merge reverts that application too (design §12.3's revert row)."""
    receiver = copy.deepcopy(element)
    receiver.update(reason=f"releases the merge of {absorbed_id}", expected_observation=None)
    receiver["applied"] = {**receiver["applied"], "before": copy.deepcopy(before or EMPTY_BEFORE)}
    return receiver


def is_merge(element):
    """This application merged its entry into another: design §12.3's reduce (merge) column."""
    return disposition_key(element) == "reduce_merge"


def merge_operations(element):
    """The merge operations of an application, by their own operation ids (design §7.3)."""
    return {op["operation_id"] for op in (element["applied"] or {"operations": []})["operations"] if op["type"] == "merge"}


def receiving_side(element):
    """This application received a merge rather than making one: it carries the merge's own operation
    and is not design §12.3's reduce (merge) that performed it."""
    return bool(merge_operations(element)) and not is_merge(element)


def standing_decision(entry):
    """The application still standing over `entry`, through the same replay a revert of that row uses
    (`reverted`): a reverted application is not standing, and a revert is never itself standing."""
    fits = replays(entry, entry["status"])
    if not fits:
        raise LedgerError(f"REPLAY_INCONSISTENT {entry['id']}: the decisions do not replay to {entry['status']!r}")
    if not fits[0]["stack"]:
        return None
    return entry["decisions"][fits[0]["stack"][-1]]


def merge_receiver(ledger, entry, undone):
    """The entry the reverted merge wrote its decision on, and that decision — the one carrying the
    merge's own operation, not merely one of the same run. It has to be the application still standing
    over the receiver: a row whose own history moved on after the merge cannot be put back by this
    revert alone, and what came after it is reverted first (Q#3, RECORD)."""
    # The id is there: a dangling absorbed_by never validated in the first place (RELATION_DANGLING)
    # and an id of the base is never lost (ID_LOST), so this reads the row the merge named.
    receiver, ops = _rows(ledger)[entry["absorbed_by"]], merge_operations(undone)
    carried = [d for d in receiver["decisions"] if d["run"] == undone["run"] and receiving_side(d) and merge_operations(d) & ops]
    if not carried:
        raise LedgerError(f"REVERT_INVERSE_UNPROVABLE {receiver['id']} decisions: no decision of this entry carries the merge operation "
                          f"{sorted(ops)} of run {undone['run']!r}, so there is none of it to put back")
    standing = standing_decision(receiver)
    if standing is None or standing is not carried[-1]:
        raise LedgerError(f"REVERT_INVERSE_UNPROVABLE {receiver['id']} decisions: the application standing over this entry is "
                          f"{'none' if standing is None else repr(standing['run'])}, not the one that received the merge "
                          f"{sorted(ops)} of run {undone['run']!r}, so that one is reverted first")
    return receiver, carried[-1]


def receiver_revert(ledger, entry, undone, element):
    """Revert the merge on the receiving entry too: its own decision recorded what the merge replaced
    there, so the same record puts that row back (`merge_receiver` says what stops it)."""
    receiver, given = merge_receiver(ledger, entry, undone)
    recorded = before_of(given)
    if recorded is None:
        raise LedgerError(f"REVERT_INVERSE_UNPROVABLE {receiver['id']} applied.before: the merge's decision on this entry did not record "
                          f"the values it replaced here")
    was = copy.deepcopy(receiver)
    restore(receiver, recorded)
    receiver["decisions"].append(merge_receiver_revert(element, entry["id"], before_record(was, receiver)))
    receiver["disposition"] = element["disposition"]


def _rows(ledger):
    return {e["id"]: e for e in ledger["entries"]}


def apply_decision(ledger, entry_id, element, updates=None):
    """A copy of `ledger` with `element` appended to the entry and the status moved by design §12.3.

    A decision that was not applied changes nothing but its own record, so it brings no `updates`
    (`UPDATES_WITHOUT_DECISION`). `updates` are the entry fields its disposition and its cell license
    (`licensed_fields`, `UPDATES_UNLICENSED`), and the appended decision records what they replaced
    (`applied.before`, RECORD). A revert carries no value of its own: it puts back exactly what the
    application it undoes recorded, and is refused by name where that record is missing. The effects
    the cell requires are checked on the result, which is then validated."""
    result = copy.deepcopy(ledger)
    entry = _rows(result).get(entry_id)
    if entry is None:
        raise LedgerError(f"ENTRY_UNKNOWN {entry_id}")
    updates = copy.deepcopy(updates or {})
    was = copy.deepcopy(entry)
    cell, reverting, plan = None, element.get("kind") == "revert", None
    if takes_effect(element):
        cell = {"effects": []} if reverting else transition(row_of(was["status"]), disposition_key(element))
        if reverting:
            if updates:
                raise LedgerError(f"REVERT_VALUE_SUPPLIED {entry_id}: {sorted(updates)} were handed to a revert, which carries no value: "
                                  f"it puts back what the application it undoes recorded")
            plan = reverted_before(was, was["status"])
            if receiving_side(plan[0]):
                makers = merge_makers(result["entries"], entry_id, plan[0])
                raise LedgerError(f"REVERT_MERGE_SIDE {entry_id}: this decision received the merge "
                                  f"{sorted(merge_operations(plan[0]))} of run {plan[0]['run']!r}; a merge is put back on both rows at "
                                  f"once, and the owner reverts it on "
                                  f"{'the entry it absorbed, which no row of this ledger is' if not makers else ', '.join(row['id'] for row in makers)}")
        else:
            unlicensed = sorted(set(updates) - licensed_fields(element, cell))
            if unlicensed:
                raise LedgerError(f"UPDATES_UNLICENSED {entry_id}: {unlicensed} are not fields a {element['disposition']} decision licenses")
    elif updates:
        raise LedgerError(f"UPDATES_WITHOUT_DECISION {entry_id}: {sorted(updates)} change an entry only through an applied decision")
    entry["decisions"].append(copy.deepcopy(element))
    if cell is not None:
        if reverting:
            undone, prior, recorded = plan
            entry["status"] = prior
            restore(entry, recorded)
        else:
            entry["status"] = status_after(was["status"], cell)
            entry.update(updates)
        entry["disposition"] = element["disposition"]
        if "revival" in cell["effects"]:
            revive(entry)
        rows = _rows(result)
        receiver = rows.get((was if reverting else entry).get("absorbed_by"))
        if "receiver_merge_decision" in cell["effects"] and receiver is not None:
            receiver["decisions"].append(merge_receiver_element(element, entry_id, before_record(receiver, receiver)))
            receiver["disposition"] = "correct"
        problems = effect_problems(cell, element, was, entry, rows)
        if reverting:
            problems += revert_restored(was, entry, recorded)
            # The merge wrote a decision on the receiving entry too, and that decision recorded what
            # it replaced there, so the revert reaches that row by the same record.
            if is_merge(undone):
                receiver_revert(result, was, undone, element)
        if problems:
            raise LedgerError("; ".join(problems))
        # What this application replaced, recorded on the decision itself: the row as it was against
        # the row as it is now, so a later revert reads values rather than inferring them (RECORD).
        entry["decisions"][-1]["applied"]["before"] = before_record(was, entry)
    problems = validate_ledger(result)
    if problems:
        raise LedgerError("LEDGER_INVALID after the decision: " + "; ".join(problems))
    return result


def create_entry(ledger, entry, element):
    """A copy of `ledger` with `entry` created by `element`, its first decision (design §12.3's rows
    for an entry no one has made yet). A cell that says "no entry" creates none. A decision whose
    delivery failed or went unverified still created the entry: its operations completed, and the
    delivery outcome is what `applied.delivery` records (design §10.6, ADDENDUM §3)."""
    result = copy.deepcopy(ledger)
    new = copy.deepcopy(entry)
    if not takes_effect(element):
        raise LedgerError(f"NEW_ROW_UNAPPLIED {new['id']}: an entry is created by an applied decision")
    cell = transition(entry_row(new), disposition_key(element))
    if cell["status"] is None:
        return result
    new["decisions"] = [copy.deepcopy(element)]
    # A row that did not exist replaced nothing, and recording that is not the same as recording
    # nothing: the empty record is what says this application had no earlier value to put back (RECORD).
    new["decisions"][0]["applied"] = {**new["decisions"][0]["applied"], "before": copy.deepcopy(EMPTY_BEFORE)}
    new.update(status=cell["status"], disposition=element["disposition"])
    result["entries"].append(new)
    problems = effect_problems(cell, element, None, new, _rows(result))
    if problems:
        raise LedgerError("; ".join(problems))
    problems = validate_ledger(result)
    if problems:
        raise LedgerError("LEDGER_INVALID after the new entry: " + "; ".join(problems))
    return result


def append_resolution(ledger, entry_id, run, resolution):
    """A copy of `ledger` with `resolution` appended to the observation of the entry's decision of
    `run`. The status never moves: a resolution records what a window observed."""
    result = copy.deepcopy(ledger)
    entry = _rows(result).get(entry_id)
    element = next((d for d in (entry or {"decisions": []})["decisions"] if d["run"] == run), None)
    if element is None or element["expected_observation"] is None:
        raise LedgerError(f"RESOLUTION_TARGET_MISSING {entry_id} run {run!r}: no decision of that run holds an expected observation")
    element["expected_observation"]["resolutions"].append(copy.deepcopy(resolution))
    problems = validate_ledger(result)
    if problems:
        raise LedgerError("LEDGER_INVALID after the resolution: " + "; ".join(problems))
    return result


# ---------------------------------------------------------------- history: replays and reverts

def replays(entry, final_status):
    """Every way the entry's decisions replay through design §12.3 to `final_status`.

    An entry the migration produced records its status at migration in its `legacy_migration` element
    (design §12.2), and that is its one start. Any other entry did not record where it started, so each
    start that fits is tried: no entry at all when the first decision is a run's (it may have created the
    entry), or any status. A fit is
    `{start, before, stack}`: the status before every applied decision (by index), and the decisions that
    took effect and are not yet reverted. A revert pops the latest of them and restores the status it
    had before it. Legacy elements move nothing here: design §12.2 migrates the status itself."""
    modern = [(i, d) for i, d in enumerate(entry["decisions"]) if not is_legacy(d) and d["applied"] is not None]
    first = entry["decisions"][0] if entry["decisions"] else None
    migration = next((d for d in entry["decisions"] if d.get("kind") == "legacy_migration" and "legacy_status" in d), None)
    if migration is not None:
        starts = [migration["legacy_status"]]
    else:
        starts = ([None] if first is not None and not is_legacy(first) else []) + vocabulary("status")
    fits = []
    for start in starts:
        status, before, stack, fits_here = start, {}, [], True
        for i, d in modern:
            before[i] = status
            if not takes_effect(d):
                continue
            if d.get("kind") == "revert":
                if not stack:  # nothing left to revert
                    fits_here = False
                    break
                status = before[stack.pop()]
                continue
            try:
                cell = transition(entry_row(entry) if status is None else row_of(status), disposition_key(d))
            except LedgerError:  # a pair the table rejects
                fits_here = False
                break
            if status is None and cell["status"] is None:  # a decision recorded on an entry that does not exist
                fits_here = False
                break
            status = cell["status"] if status is None else status_after(status, cell)
            stack.append(i)
        if fits_here and status == final_status:
            fits.append({"start": start, "before": before, "stack": stack})
    return fits


def revert_target(entry, status):
    """The status a revert of the entry's latest applied decision restores (design §12.3's revert row):
    what the latest earlier decision that set one left, or the status the history started from."""
    return reverted(entry, status)[1]


# ---------------------------------------------------------------- events (design §12.3)

def _entry_copy(ledger, entry_id):
    result = copy.deepcopy(ledger)
    entry = _rows(result).get(entry_id)
    if entry is None:
        raise LedgerError(f"ENTRY_UNKNOWN {entry_id}")
    return result, entry


def _malformed(entry_id, event, why):
    return LedgerError(f"EVENT_MALFORMED {entry_id} {event}: {why}")


def _awaiting_r(ledger, entry_id, element):
    """An admitted item waits for R: an incubating entry keeps its status; an unapplied decision records why."""
    result, entry = _entry_copy(ledger, entry_id)
    if entry["status"] != "incubating":
        raise LedgerError(f"EVENT_NOT_APPLICABLE {entry_id} awaiting_R: the entry is {entry['status']}; awaiting R is an incubating entry's")
    if element["applied"] is not None or not element.get("reason"):
        raise _malformed(entry_id, "awaiting_R", "an unapplied decision that records its reason")
    entry["decisions"].append(copy.deepcopy(element))
    return result


def _recurrence(ledger, entry_id, evidence=(), lineages=None, record=None):
    """New evidence for the same learning: evidence and lineages are appended, the status stays."""
    result, entry = _entry_copy(ledger, entry_id)
    if not evidence:
        raise _malformed(entry_id, "recurrence", "a recurrence appends evidence")
    held = [json.dumps(item, sort_keys=True) for item in entry["evidence"]]
    if any(json.dumps(item, sort_keys=True) in held for item in evidence):
        raise _malformed(entry_id, "recurrence", "evidence the entry already holds is not new")
    entry["evidence"] += copy.deepcopy(list(evidence))
    if lineages is not None:
        entry["independent_lineages"] = lineages
    if record is not None:
        entry.setdefault("recurrence", []).append(copy.deepcopy(record))
    return result


def _contradiction(ledger, entry_id, element):
    """Admitted evidence against an entry: nothing changes until the candidate's disposition is applied."""
    result, entry = _entry_copy(ledger, entry_id)
    if element["applied"] is not None or element["disposition"] not in ("correct", "reduce", "drop"):
        raise _malformed(entry_id, "contradiction", "an unapplied correct, reduce or drop")
    entry["decisions"].append(copy.deepcopy(element))
    return result


def _delivery(ledger, entry_id, run, outcome):
    """What the delivery check of an already applied decision found (design §12.3's delivery row).

    The application itself was recorded when its operations completed and took effect then; this
    writes the outcome into that decision's `applied.delivery` and moves nothing else — no transition
    is replayed and no second decision is appended for the same run (ADDENDUM §3, the correction)."""
    result, entry = _entry_copy(ledger, entry_id)
    if outcome not in ("failed", "unverified"):
        raise _malformed(entry_id, "delivery", f"an outcome of failed or unverified, not {outcome!r}; design §12.3's row has no other")
    element = next((d for d in entry["decisions"] if d["run"] == run), None)
    if element is None:
        raise _malformed(entry_id, "delivery", f"no decision of run {run!r} is on this entry")
    if is_legacy(element):
        raise _malformed(entry_id, "delivery", f"run {run!r} is an element of the migration, whose delivery design §12.2 already recorded")
    if element["applied"] is None:
        raise _malformed(entry_id, "delivery", f"the decision of run {run!r} records no application for a delivery check to have found")
    element["applied"]["delivery"] = outcome
    return result


def _revert(ledger, entry_id, element):
    """The owner reverts an application: a revert decision is appended, the status goes back, and the
    row takes the values that application recorded as replaced. It carries no value of its own, and
    where the application recorded none the revert is refused (`reverted_before`, RECORD)."""
    if element.get("kind") != "revert":
        raise _malformed(entry_id, "revert", "a decision of kind revert")
    return apply_decision(ledger, entry_id, element)


EVENTS = {"awaiting_R": _awaiting_r, "recurrence": _recurrence, "contradiction": _contradiction, "delivery": _delivery, "revert": _revert}


def record_event(ledger, entry_id, event, **kwargs):
    """A copy of `ledger` with the event recorded as design §12.3 gives it; the result is validated."""
    if event not in EVENTS:
        raise LedgerError(f"EVENT_UNKNOWN {event!r}: design §12.3 has {sorted(EVENTS)}")
    result = EVENTS[event](ledger, entry_id, **kwargs)
    problems = validate_ledger(result)
    if problems:
        raise LedgerError(f"LEDGER_INVALID after {event}: " + "; ".join(problems))
    return result


# ---------------------------------------------------------------- changed rows

def _written_once(element):
    """The element without the two things a later window still writes into it: the resolutions of its
    expected observation (design §11) and the outcome its delivery check found (design §12.3's
    delivery row). Everything else of a decision is written once and never overwritten (design §12.1)."""
    element = copy.deepcopy(element)
    if element["expected_observation"] is not None:
        element["expected_observation"]["resolutions"] = []
    if element["applied"] is not None:
        element["applied"]["delivery"] = None
    return element


def _grew(old, new):
    return isinstance(old, list) and isinstance(new, list) and new[:len(old)] == old


def delivery_problems(eid, n, before, after):
    """A delivery outcome written into a recorded decision by a transaction, by the same rules the
    delivery event applies (`_delivery`, K#4): design §12.3's row has only failed and unverified, and a
    legacy element's delivery is the one design §12.2 recorded when it migrated the entry."""
    was, now = (before["applied"] or {}).get("delivery"), (after["applied"] or {}).get("delivery")
    if was == now:
        return []
    tag = f"{eid} decisions[{n}] ({after['run']})"
    if is_legacy(after):
        return [f"DELIVERY_ON_MIGRATED {tag}: the delivery of an element design §12.2 migrated is the one the migration recorded"]
    if now not in ("failed", "unverified"):
        return [f"DELIVERY_OUTCOME_INVALID {tag}: a delivery check records failed or unverified, not {now!r}; design §12.3's row has no other"]
    return []


def legacy_appended(eid, elements, offset=0):
    """An element of the migration a transaction introduced. It is not a decision a run made: it
    carries no approval row and design §12.2 is its only author, so it enters a ledger through the
    migration of the schema 1 file (MIGRATION_MISMATCH holds that) and never through a transaction
    between two schema 2 ledgers — on a row that was already there or on one the run allocated."""
    return [f"LEGACY_ELEMENT_APPENDED {eid} decisions[{offset + n}]: an element of the migration is written by the "
            f"migration of the schema 1 ledger, not appended by a run" for n, e in enumerate(elements) if is_legacy(e)]


def new_row_problems(entry, rows):
    """A new row is bound to the applied decision that created it (design §12.3's rows for no entry)."""
    eid, decisions = entry["id"], entry["decisions"]
    if not decisions or is_legacy(decisions[0]):
        return [f"NEW_ROW_WITHOUT_DECISION {eid}: a new entry is created by a decision of a run"]
    first = decisions[0]
    if not takes_effect(first):
        return [f"NEW_ROW_UNAPPLIED {eid}: the decision that creates an entry is applied"]
    try:
        cell = transition(entry_row(entry), disposition_key(first))
    except LedgerError as exc:
        return [str(exc).replace("TRANSITION_DISALLOWED", f"TRANSITION_DISALLOWED {eid}:", 1)]
    if cell["status"] is None:
        return [f"NEW_ENTRY_FOR_NO_ENTRY {eid}: design §12.3 creates no entry for this decision"]
    # One decision per row a transaction allocates. A second one would have to be judged from the
    # state the first left, which is the work `row_violations` does between two recorded rows and
    # which this side has no base for: the row did not exist at the base (K#3, correction 3). A run
    # that decides such an entry again does it in the next close, against the row it can now read.
    problems = legacy_appended(eid, decisions)
    if len(decisions) > 1:
        return problems + [f"NEW_ROW_MULTIPLE_DECISIONS {eid}: {len(decisions)} decisions on a row this transaction allocated; the decision "
                           f"that creates an entry is the only one it carries, and a later one is judged against the row the close recorded"]
    problems += effect_problems(cell, first, None, entry, rows)
    problems += before_required(f"{eid} decisions[0] ({first['run']})", first)
    problems += before_problems(f"{eid} decisions[0] ({first['run']})", before_of(first), EMPTY_BEFORE)
    if entry["status"] != cell["status"]:
        problems.append(f"STATUS_UNEXPLAINED {eid}: created as {entry['status']}, but its first decision leads to {cell['status']}")
    if entry["disposition"] != first["disposition"]:
        problems.append(f"DISPOSITION_UNBOUND {eid}: the entry says {entry['disposition']!r}, its first decision {first['disposition']!r}")
    return problems


def merge_makers(rows, eid, undone):
    """Every entry whose merge this decision received: a row absorbed into `eid` carrying a reduce
    (merge) of the same run and the same operation. All of it is identity — the row the merge named,
    the run that decided it, the operation it recorded (RECORD) — and the row is the half that was
    missing: two rows can carry a merge of one run and one operation id, and only one of them merged
    into this entry (T#0). More than one leaves which row this revert puts back undecidable, and the
    caller refuses rather than taking the first."""
    ops = merge_operations(undone)
    return [row for row in rows if row["id"] != eid and row.get("absorbed_by") == eid and any(
        is_merge(d) and d["run"] == undone["run"] and merge_operations(d) & ops for d in row["decisions"])]


def at(decisions, element):
    """Where `element` sits in `decisions`, by identity: its position is what identifies a decision
    across the base and the head of one transaction, because decisions are only ever appended
    (`DECISION_REWRITTEN`). Comparing the elements themselves would read a delivery outcome or a
    resolution written into the recorded decision as a different decision (T#1)."""
    return next((n for n, d in enumerate(decisions) if d is element), None)


def undoes(partner_base, partner_head, revert_at, target_at):
    """The replay says the revert this transaction appended at `revert_at` undoes the decision at
    `target_at`.

    Asking what a revert undoes is the only way to know: a revert carries no reference to its own
    target, so a same-run revert sitting on the right row can be undoing something else entirely
    (RECORD). The row holds at most one appended application (`TRANSACTION_MULTIPLE_APPLICATIONS`),
    so the status before this revert is the base's."""
    was = {**partner_base, "decisions": partner_head["decisions"][:revert_at]}
    try:
        undone, _prior = reverted(was, partner_base["status"])
    except LedgerError:
        return False
    return at(was["decisions"], undone) == target_at


def merge_pair_problems(side, partner_base, partner_head, target_at, run, ops, role):
    """A merge is put back on both rows or on neither (RECORD): the partner row carries a revert this
    transaction appended, and the replay says that revert undoes the merge's application there."""
    first = len(partner_base["decisions"])
    revert_at = next((n for n, d in enumerate(partner_head["decisions"][first:], first)
                      if d.get("kind") == "revert" and d["run"] == run), None)
    if revert_at is None:
        return [f"REVERT_MERGE_SIDE {side}: the merge {sorted(ops)} is put back here and {partner_base['id']}, the entry that "
                f"{role} it, is left holding it; this transaction appends no revert of run {run!r} there"]
    if not undoes(partner_base, partner_head, revert_at, target_at):
        return [f"REVERT_MERGE_UNPAIRED {side}: the revert of run {run!r} appended to {partner_base['id']} undoes another decision of "
                f"that row, not the application that {role} the merge {sorted(ops)}"]
    return []


def row_violations(base, head, rows, base_rows=None):
    """Design §12.4, "every changed row matching a validated decision", between two schema 2 rows.

    A change is licensed by what was appended. Without an applied decision only the recurrence event's
    fields may change; with one, its status (by the table, or by the history for a revert), its
    disposition (the decision's own) and the fields that decision's own disposition and cell license
    (`licensed_fields`), and the effects its cell requires are checked on the result."""
    if base == head:
        return []
    eid, problems = head["id"], []
    old, new = base["decisions"], head["decisions"]
    if len(new) < len(old):
        problems.append(f"DECISION_REWRITTEN {eid}: {len(old) - len(new)} decision(s) removed; a decision is never overwritten")
    for n, (before, after) in enumerate(zip(old, new)):
        if before != after and (_written_once(before) != _written_once(after) or not _grew(
                (before["expected_observation"] or {}).get("resolutions") or [], (after["expected_observation"] or {}).get("resolutions") or [])):
            problems.append(f"DECISION_REWRITTEN {eid} decisions[{n}] ({before['run']}): only a resolution and the delivery outcome are written later")
        problems += delivery_problems(eid, n, before, after)
    appended = new[len(old):]
    problems += legacy_appended(eid, appended, len(old))
    appended = [e for e in appended if not is_legacy(e)]
    applied = [e for e in appended if takes_effect(e)]
    changed = sorted(k for k in set(base) | set(head) if k != "decisions" and base.get(k) != head.get(k))
    for field in (f for f in APPEND_ONLY if f in changed):
        if not _grew(base.get(field, []), head.get(field, [])):
            problems.append(f"EVENT_REWRITTEN {eid} {field}: a recurrence only appends")
    # One applied decision per row per transaction. A second would have to be judged from the row the
    # first left, and this side holds the row as the base recorded it and as the close wrote it, never
    # the state in between: a transaction that applied a decision and reverted it in one close would
    # be judged against neither (RECORD). A run decides an entry once (DECISION_RUN_DUPLICATE), so
    # the case this refuses is a close carrying two runs' applications for one row.
    if len(applied) > 1:
        problems.append(f"TRANSACTION_MULTIPLE_APPLICATIONS {eid}: {len(applied)} applied decisions appended in one transaction "
                        f"({', '.join(e['run'] for e in applied)}); the row in between them is not recorded anywhere")
        return problems
    reached, so_far, licensed = base["status"], list(old), set()
    for element in appended:
        so_far.append(element)
        if not takes_effect(element):
            continue
        restored, undone = None, None
        try:
            if element.get("kind") == "revert":
                was = {**base, "decisions": so_far[:-1]}
                undone, reached, restored = reverted_before(was, reached)
                cell, licensed = {"effects": []}, licensed | set(restored["fields"]) | set(restored["absent"])
            else:
                cell = transition(row_of(reached), disposition_key(element))
                reached = status_after(reached, cell)
        except LedgerError as exc:
            problems.append(str(exc).replace("TRANSITION_DISALLOWED", f"TRANSITION_DISALLOWED {eid}:", 1))
            continue
        licensed |= licensed_fields(element, cell)
        problems += effect_problems(cell, element, base, head, rows)
        # What the application says it replaced, against what the row says it replaced.
        tag = f"{eid} decisions[{len(old) + appended.index(element)}] ({element['run']})"
        problems += before_required(tag, element)
        problems += before_problems(tag, before_of(element), before_record(base, head))
        if restored is not None:  # a revert puts the row back, and the result is held against the record
            problems += revert_restored(base, head, restored)
            if receiving_side(undone):  # the receiving side of a merge: the row it absorbed is put back with it
                makers = merge_makers((base_rows or rows).values(), eid, undone)
                if not makers:
                    problems.append(f"REVERT_MERGE_SIDE {eid}: this decision received the merge {sorted(merge_operations(undone))} of run "
                                    f"{undone['run']!r} and no entry of the base merged into this one with it, so there is no row to "
                                    f"put back with it")
                elif len(makers) > 1:
                    problems.append(f"REVERT_MERGE_SIDE {eid}: {[row['id'] for row in makers]} each recorded the merge "
                                    f"{sorted(merge_operations(undone))} of run {undone['run']!r} into this entry, so which row this "
                                    f"revert puts back is not decidable")
                else:
                    source = makers[0]
                    made = next(d for d in source["decisions"] if is_merge(d) and d["run"] == undone["run"])
                    problems += merge_pair_problems(eid, source, rows[source["id"]], at(source["decisions"], made),
                                                    element["run"], merge_operations(undone), "made")
            if is_merge(undone):  # and the receiving entry of a merge is part of that row's inverse
                try:
                    # the receiver as the base recorded it: its own revert is what this transaction
                    # appends, so the row to read the merge's standing from is the one before that
                    receiver, given = merge_receiver({"entries": list((base_rows or rows).values())}, base, undone)
                    now = rows[receiver["id"]]
                    appended_there = now["decisions"][len(receiver["decisions"]):]
                    if not any(d.get("kind") == "revert" and d["run"] == element["run"] for d in appended_there):
                        problems.append(f"RECEIVER_REVERT_MISSING {receiver['id']}: the merge of run {undone['run']!r} is reverted on {eid} "
                                        f"and this transaction appends no revert of it on this entry, where its decision still stands")
                    else:
                        problems += merge_pair_problems(eid, receiver, now, at(receiver["decisions"], given),
                                                        element["run"], merge_operations(undone), "received")
                        problems += revert_restored(receiver, now, before_of(given) or EMPTY_BEFORE)
                except LedgerError as exc:
                    problems.append(str(exc))
    allowed = set(EVENT_FIELDS) | ({"status", "disposition"} | licensed if applied else set())
    problems += [f"ROW_FIELD_UNLICENSED {eid} {k}: changed with {'no applied decision' if not applied else 'a decision whose disposition does not license it'}"
                 for k in changed if k not in allowed]
    if applied and head["disposition"] != applied[-1]["disposition"]:
        problems.append(f"DISPOSITION_UNBOUND {eid}: the entry says {head['disposition']!r}, the latest decision that took effect {applied[-1]['disposition']!r}")
    if reached != head["status"]:
        problems.append(f"STATUS_UNEXPLAINED {eid}: {base['status']} → {head['status']}, but the decisions that took effect lead to {reached}")
    return problems


def _migrator():
    spec = importlib.util.spec_from_file_location("migrate_ledger", MIGRATOR)
    if spec is None or not MIGRATOR.is_file():
        raise LedgerError(f"MIGRATOR_UNREADABLE {MIGRATOR}: a schema 1 base cannot be compared with a schema 2 head")
    module = importlib.util.module_from_spec(spec)
    sys.modules["migrate_ledger"] = module
    spec.loader.exec_module(module)
    return module


def check_pair(base, head, allocated=None):
    """Every violation of design §12.4 between a frozen `base` ledger and a `head` ledger."""
    problems = validate_ledger(head)
    if problems:
        return problems
    before, after = version(base), version(head)
    problems = id_set_violations(entry_ids(base), entry_ids(head), allocated, numbered=before == 1 and after == 1,
                                 transaction=before == 2 and after == 2 and base != head)
    held = base.get("windows", [])
    if after == 2 and held != head["windows"][:len(held)]:
        problems.append("WINDOWS_REWRITTEN: a window record of the base was changed or removed")
    if before == 1 and after == 2:
        migrated, _removed = _migrator().migrate(base)
        if migrated != head:
            problems.append("MIGRATION_MISMATCH: the schema 2 head is not the migration of the schema 1 base")
    elif before == 2 and after == 1:
        problems.append("LEDGER_SCHEMA_REGRESSED: the head is schema 1 and the base schema 2")
    elif before == 2:
        base_rows, rows = _rows(base), _rows(head)
        for entry in head["entries"]:
            if entry["id"] in base_rows:
                problems += row_violations(base_rows[entry["id"]], entry, rows, base_rows)
            else:
                problems += new_row_problems(entry, rows)
    return problems


# ---------------------------------------------------------------- atomic writes

def read_current(path):
    try:
        return pathlib.Path(path).read_bytes()
    except FileNotFoundError:
        return b""


def write_atomic(path, ledger, base_sha, lock_root=LOCK_ROOT, before_rename=None, allocated=()):
    """Replace the ledger at `path` with `ledger` if it still hashes to `base_sha`.

    The ledger is validated first, the lock taken (`STAGE_LOCKED` when another writer holds it), the
    file's hash compared with the one the caller read (`BASE_STALE`), and the file it would replace
    held against the ledger that replaces it (`check_pair`, with the allocation the caller froze):
    the bytes on disk are the base of a transaction, and a writer that erases or reorders a decision
    is refused here rather than caught later by a gate (U#0). Only then are the new bytes written to
    a temporary file beside it, fsynced, and renamed over it. Every path is confined beneath the
    ledger's directory (`RUN_PATH_ESCAPE`). `before_rename` is the seam a crash is injected through:
    a reader sees the old file or the complete new one, never a part."""
    problems = validate_ledger(ledger)
    if problems:
        raise LedgerError("LEDGER_INVALID, nothing written: " + "; ".join(problems))
    path = pathlib.Path(path)
    root = path.parent
    target = stagelock.confine(root, path)
    with stagelock.hold(lock_root, "ledger"):
        bytes_there = read_current(target)
        current = sha256_bytes(bytes_there)
        if current != base_sha:
            raise LedgerError(f"BASE_STALE {path}: the file hashes to {current[:12]}, the writer read {base_sha[:12]}")
        if bytes_there:  # a first write replaces no transaction; every later one does
            # the base is read as a ledger before it is read as a transaction's base: `check_pair`
            # validates the head it is given and takes the base as one, so a base that is not a
            # ledger reaches the comparison as whatever it is — a list, a null, a row set with two
            # rows of one id — and is read through as if it said something (X#0).
            try:
                was = json.loads(bytes_there.decode("utf-8"))
                unsound = validate_ledger(was) if isinstance(was, dict) else [f"it holds {type(was).__name__}, not an object"]
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError, KeyError) as exc:
                unsound = [f"reading it raised {type(exc).__name__}: {exc}"]
            if unsound:
                raise LedgerError(f"BASE_UNREADABLE {path}, nothing written: the file this writer would replace is not a ledger: "
                                  + "; ".join(unsound))
            problems = check_pair(was, ledger, allocated)
            if problems:
                raise LedgerError("TRANSACTION_INVALID, nothing written: " + "; ".join(problems))
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(render(ledger))
                handle.flush()
                os.fsync(handle.fileno())
            if before_rename is not None:
                before_rename()
            os.replace(temporary, target)
        except BaseException:
            pathlib.Path(temporary).unlink(missing_ok=True)
            raise
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


# ---------------------------------------------------------------- the check command

def _gate():
    """gates/check-global-file.py's git readers: an absent path measures as empty, an unreadable
    side as None. One implementation of "read a side of a commit", not two. It is this checkout's
    helper, found beside this module, never a file of the repository being judged."""
    spec = importlib.util.spec_from_file_location("check_global_file", GATE_READERS)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_global_file"] = module
    spec.loader.exec_module(module)
    return module


def allocation(argument):
    """`--allocated` as an allocation: an omitted flag is no allocation at all (`None`), and the flag
    passed empty is the allocation of a run that froze no new id (`[]`) — a correction or a resolution
    writes the ledger without adding a row, and the two cases are not the same answer (`ALLOCATION_REQUIRED`)."""
    return None if argument is None else [i for i in (part.strip() for part in argument.split(",")) if i]


def check_command(repo, rel, base, worktree, allocated):
    """(exit code, lines). 0 holds, 1 a violation, 2 a side that could not be read."""
    git = _gate()
    old, old_absent = git.base_blob(repo, base, rel)
    new, new_absent = git.current_blob(repo, rel, worktree)
    where = "worktree" if worktree else "index"
    if old is None:
        return 2, [f"CANNOT JUDGE LEDGER_BASE_UNREADABLE {base}:{rel}"]
    if new is None:
        return 2, [f"CANNOT JUDGE LEDGER_FILE_UNREADABLE {rel} ({where})"]
    if new_absent:
        return 1, [f"LEDGER_ABSENT {rel}: the {where} holds no ledger"]
    try:
        head = parse(new, f"{where}:{rel}")
        if old_absent:
            problems = validate_ledger(head)
            note = f"no ledger at {base}: validated alone"
        else:
            problems = check_pair(parse(old, f"{base}:{rel}"), head, allocated)
            note = f"against {base}"
    except LedgerError as exc:
        return 1, [str(exc)]
    if problems:
        return 1, problems
    return 0, [f"ledger --check: OK (schema {version(head)}, {len(head['entries'])} entries, {note}, {where})"]


# ---------------------------------------------------------------- samples and transition fixtures

def sample_entry(eid, status="placed", **fields):
    entry = {"id": eid, "lesson": f"lesson of {eid}", "status": status, "classification": None, "window": "unknown",
             "kind": "unclassified", "diagnosis": "unknown", "disposition": "none", "destination": None, "evidence": [],
             "independent_lineages": "unavailable", "consequence": {"kinds": []}, "coverage": {"basis": "unavailable"},
             "keep": None, "relations": {}, "decisions": []}
    entry.update(fields)
    return entry


def sample_ledger(*entries, windows=()):
    return {"schema": 2, "framework": "design/session-distill/PLACEMENT-FRAMEWORK.md", "windows": list(windows), "entries": list(entries)}


def sample_element(run, disposition, applied=True, observation=None, approval="ap-1", operations=(), delivery="not_applicable", **extra):
    """A decision of a run: design §12.1's eight keys, and nothing design §12.2 gives a migrated one."""
    return {"run": run, "disposition": disposition, "approval_id": approval, "adjudication_id": None, "confirmation": None,
            "applied": ({"commit": None, "paths": [], "operations": list(operations), "delivery": delivery,
                         "before": copy.deepcopy(EMPTY_BEFORE)} if applied else None),
            "tests": None, "expected_observation": observation, **extra}


def sample_observation(expiry="2026-12-31"):
    return {"occasion_criteria": "the owner asks again", "exposure_rule": "the unit was delivered first",
            "expected_behavior": "no second ask", "retrieval_terms": ["ask again"], "expiry": expiry, "resolutions": []}


def sample_resolution(run, window="2026-11-20", resolution="observed"):
    return {"run": run, "window": window, "resolution": resolution, "basis": "source",
            "counts": {"eligible": 2, "observed": 2, "not_observed": 0, "exposure_unknown": 0}, "occasions": ["occ-1", "occ-2"]}


MERGE = {"operation_id": "op-1", "type": "merge", "target": "claude/CLAUDE.md#x"}
ROW_STATUS = {"incubating": "incubating", "placed": "placed", "absorbed_retired": "retired"}


def cell_ids():
    """`<row>/<disposition>` of every cell the table allows."""
    return sorted(f"{row}/{key}" for row, cells in transitions()["cells"].items() for key, cell in cells.items() if cell is not None)


# What an entry has to gain for a cell's effect: the footprints the fixtures pass as `updates`. The other
# footprints belong to the decision (a reason, an observation) or to the receiving entry, and are built
# by `scenario`.
UPDATES = {"keep_record": {"keep": {"units": ["unit-1"]}}, "absorbed_by": {"absorbed_by": "G-0"},
           "allocate_destination_entry": {"absorbed_by": "G-0"}, "text_revised": {"lesson": "a revised lesson"}}


def updates_for(cell):
    return {k: v for e in cell["effects"] for k, v in UPDATES.get(e, {}).items()}


def scenario(row, key, updates):
    """What one cell's fixture runs through the production code: the entry (a candidate when the row is
    no entry yet), the entries around it, the decision, and the updates."""
    status = ROW_STATUS.get(row)
    if status is None:  # no entry yet: a new learning is a gap, anything else comes from a unit of the library
        entry = sample_entry("S9-01", "placed", kind="gap" if row == "no_entry_new_learning" else "misfire")
    else:
        entry = sample_entry("S9-01", status, kind="gap")
        if row == "incubating":  # an incubating entry was incubated by an earlier run, whose expiry a renewal has to pass
            entry["decisions"].append(sample_element("run-0", "incubate", observation=sample_observation("2026-12-31")))
    disposition = "reduce" if key.startswith("reduce") else key
    extra = {"reason": "the reason"} if disposition in ("keep", "drop") else {}
    observation = sample_observation("2027-06-30") if disposition == "incubate" else None
    element = sample_element("run-1", disposition, observation=observation, operations=[MERGE] if key == "reduce_merge" else (), **extra)
    return {"entry": entry, "others": [sample_entry("G-0")], "element": element, "updates": updates}


def fixture_for(row, key):
    return scenario(row, key, updates_for(transition(row, key)))


def generate_fixtures(path=FIXTURES_PATH):
    """Write one fixture per allowed cell, once. The fixtures are committed, and a second call refuses:
    a fixture regenerated from the table it is meant to hold would hold nothing."""
    path = pathlib.Path(path)
    if path.exists():
        raise LedgerError(f"FIXTURES_FROZEN {path}: generated once and committed; delete it by hand to regenerate")
    fixtures = []
    for cid in cell_ids():
        row, key = cid.split("/")
        cell = transitions()["cells"][row][key]
        fixtures.append({"id": cid, "row": row, "disposition": key, "before": ROW_STATUS.get(row),
                         "updates": updates_for(cell), "after": cell})
    doc = {"$comment": "design §12.3: one frozen fixture per allowed cell of tables/transitions.json, written once by "
                       "`runlib/ledger.py --generate-transition-fixtures`; the self-test never regenerates them.",
           "fixtures": fixtures}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(fixtures)


def fixture_problems(fixture):
    """Run one frozen fixture through the real code path and compare it with what it froze: an entry
    that exists moves by `apply_decision`, a row with no entry yet creates it (or none) by `create_entry`."""
    fid, row, key, before, after = fixture["id"], fixture["row"], fixture["disposition"], fixture["before"], fixture["after"]
    cell = transition(row, key)  # the table as it stands now
    if cell != after:
        return [f"{fid}: the table now says {cell}, frozen {after}"]
    run = scenario(row, key, fixture["updates"])
    ledger = sample_ledger(*run["others"])
    try:
        if before is None:
            made = [e for e in create_entry(ledger, {**run["entry"], **run["updates"]}, run["element"])["entries"] if e["id"] == "S9-01"]
            if len(made) != (1 if after["status"] is not None else 0):
                return [f"{fid}: {len(made)} entries created, frozen {after['status']}"]
            return [] if not made or made[0]["status"] == after["status"] else [f"{fid}: created {made[0]['status']}, frozen {after['status']}"]
        ledger["entries"].append(run["entry"])
        moved = apply_decision(ledger, "S9-01", run["element"], run["updates"])["entries"][-1]["status"]
    except LedgerError as exc:
        return [f"{fid}: {exc}"]
    want = after["status"] if after["status"] not in (None, "unchanged") else before
    return [] if moved == want else [f"{fid}: the status moved {before} → {moved}, frozen {want}"]


def coverage_problems(cells, frozen, executed):
    """The three-set comparison of the table's cells, the frozen fixtures' ids and the case ids a run
    executed (the `check_bijection` pattern of benchmarks/manifest.py): any difference, by id."""
    return ([f"CELL_UNFIXTURED {i}: a cell of the table with no frozen fixture" for i in sorted(set(cells) - set(frozen))]
            + [f"FIXTURE_ORPHAN {i}: a frozen fixture for no cell of the table" for i in sorted(set(frozen) - set(cells))]
            + [f"CASE_NOT_EXECUTED {i}: a frozen fixture the run never executed" for i in sorted(set(frozen) - set(executed))]
            + [f"CASE_UNFROZEN {i}: a case the run executed with no frozen fixture" for i in sorted(set(executed) - set(frozen))])


# ---------------------------------------------------------------- the self-test

# The design's table of §12.3, copied here once (WP-13 done-when 4). The cross-provider review of
# this module compares it with the design text. Each row is the cell wording in the column order of
# `transitions()["dispositions"]`; "—" is a pair code rejects.
DESIGN_12_3 = {
    "no_entry_new_learning": ["new entry, placed", "—", "—", "—", "—", "—", "new entry, incubating",
                              "new entry, retired (never placed)", "no entry"],
    "no_entry_existing_unit": ["—", "new entry, placed", "new entry, placed", "new entry, placed, keep record",
                               "new entry, retired", "new entry, absorbed; destination entry allocated (placed) if it has none",
                               "new entry, placed, pending intervention", "new entry, placed, dropped intervention", "no entry"],
    "incubating": ["placed", "incubating (text revised)", "—", "—", "—", "—", "incubating (expiry renewed)", "retired", "unchanged"],
    "placed": ["—", "unchanged", "unchanged", "unchanged, keep record", "retired",
               "absorbed (`absorbed_by`); the receiving entry gets a merge decision", "unchanged, pending intervention",
               "unchanged, dropped intervention", "unchanged"],
    "absorbed_retired": ["placed (revival)", "—", "—", "—", "—", "—", "incubating (revival)", "unchanged", "unchanged"],
}
# design §12.3, "Events other than dispositions": (from, event, to), copied once. Its branch set is the
# five events; `EVENTS` holds one handler for each.
DESIGN_12_3_EVENTS = (
    ("incubating", "awaiting R (§10.2)", "incubating, reason recorded"),
    ("any", "recurrence (new evidence for the same learning)", "unchanged; evidence and lineages appended"),
    ("any", "contradiction (admitted evidence against it)", "unchanged until its candidate's disposition (correct, reduce, or drop) is applied"),
    ("any applied decision", "delivery failed or unverified", "unchanged; `decisions[].applied.delivery` records it"),
    ("any applied decision", "application reverted by the owner", "the status before that decision; a revert decision appended"),
)
# design §7.2's closed vocabularies, copied once. A current entry and every decision of a run use them;
# design §12.2 adds `unknown` and `revival` to the elements it migrates, and nowhere else.
DESIGN_7_2 = {
    "kind": ["misfire", "gap", "not delivered", "confirmed", "obsolete", "already resolved", "unclassified"],
    "diagnosis": ["covered", "wrong or insufficient", "trigger problem", "gap", "redundant", "unknown"],
    "disposition": ["place", "correct", "re-deliver", "keep", "reduce", "incubate", "drop", "none"],
    "legacy_only": ["unknown", "revival"],
}
# The field lists of design §12.1 and §12.2, copied once. `entry_required` are the fields §12.1 adds and
# the kept fields every entry carries, `element_required` the eight keys of a decisions[] element in §12.1
# and nothing else. Every property beyond those lists is optional, and each is contracted — with the code
# that reads it and the reason it exists — by ADDENDUM, which `addendum_problems` holds against this
# module: §12.2's metadata of a migrated element (`element_legacy_only`, which a decision of a run may
# not carry), the legacy and revert kinds, and the `reason` §7.3 and §12.3 ask of a keep, a drop and an
# awaiting-R record.
DESIGN_12_1 = {
    "entry_required": {"id", "lesson", "status", "classification", "window"} | {
        "kind", "diagnosis", "disposition", "destination", "evidence", "independent_lineages", "consequence",
        "coverage", "keep", "relations", "decisions"},
    "entry_optional": {"principle", "rationale", "surfaced", "domain", "source", "note", "learning_id", "baseline_ref",
                       "recurrence", "absorbed_by", "retired", "retire_reason"},
    "element_required": {"run", "disposition", "approval_id", "adjudication_id", "confirmation", "applied", "tests",
                         "expected_observation"},
    "element_optional": {"at", "field", "legacy_text", "legacy_placed", "legacy_status", "kind", "status_note", "reason",
                         "resolves"},
    "element_legacy_only": set(LEGACY_PROPERTIES),
    "applied": {"commit", "paths", "operations", "delivery"},
    "applied_optional": {"before"},  # the owner's decision of 2026-10-21, contracted in RECORD
    "tests": {"results_sha", "summary", "attribution"},
    "window": {"start", "end", "run_id", "kind", "commit", "accounted", "fully_read"},
    "evidence": {"claim_id", "evidence_id", "locator", "session"},
}


def contract_problems(doc):
    """Where the schema departs from the field lists of design §12.1, §12.2, §12.4 and the vocabularies of §7.2."""
    problems = []
    if not str(doc.get("$comment", "")).startswith("design §12.1"):
        problems.append("CONTRACT_MISMATCH ledger: $comment does not cite design §12.1")
    defs = doc["$defs"]
    shapes = {"entry": (defs["entry"], DESIGN_12_1["entry_required"], DESIGN_12_1["entry_optional"]),
              "decision": (defs["decision"], DESIGN_12_1["element_required"], DESIGN_12_1["element_optional"]),
              "applied": (defs["applied"], DESIGN_12_1["applied"], DESIGN_12_1["applied_optional"]),
              "tests": (defs["tests"], DESIGN_12_1["tests"], set()),
              "window": (defs["window"], DESIGN_12_1["window"], set()),
              "evidence_item": (defs["evidence_item"], set(), DESIGN_12_1["evidence"])}
    for name, (shape, required, optional) in shapes.items():
        for verb, fields in (("lacks", required - set(shape["required"] if "required" in shape else ())), ("adds", set(shape.get("required", ())) - required)):
            if fields:
                problems.append(f"CONTRACT_MISMATCH {name} (design §12.1): required {verb} {sorted(fields)}")
        for verb, fields in (("lacks", (required | optional) - set(shape["properties"])), ("adds", set(shape["properties"]) - required - optional)):
            if fields:
                problems.append(f"CONTRACT_MISMATCH {name} (design §12.1): properties {verb} {sorted(fields)}")
    entry = defs["entry"]["properties"]
    legacy_only = set(defs["legacy_disposition"]["enum"]) - set(defs["disposition"]["enum"])
    for name, have, want in (("entry kind", defs["entry_kind"]["enum"], DESIGN_7_2["kind"]),
                             ("entry diagnosis", defs["entry_diagnosis"]["enum"], DESIGN_7_2["diagnosis"]),
                             ("disposition", defs["disposition"]["enum"], DESIGN_7_2["disposition"]),
                             ("legacy-only dispositions", sorted(legacy_only), sorted(DESIGN_7_2["legacy_only"]))):
        if have != want:
            problems.append(f"CONTRACT_MISMATCH {name} (design §7.2): {have} differs from {want}")
    before = defs["before_row"]
    named = set(before["properties"]["fields"]["properties"]) | set(before["properties"]["absent"]["items"]["enum"])
    if named != set(REVERTIBLE) or set(before["properties"]["fields"]["properties"]) != set(before["properties"]["absent"]["items"]["enum"]):
        problems.append(f"CONTRACT_MISMATCH before_row (RECORD): it names {sorted(named)}, the fields a decision may change are {sorted(REVERTIBLE)}")
    if not str(before.get("$comment", "")).startswith("the owner's decision of 2026-10-21"):
        problems.append("CONTRACT_MISMATCH before_row (RECORD): its comment does not cite the decision that added it")
    if defs["decision"]["properties"].get("legacy_status", {}).get("enum") != entry["status"]["enum"]:
        problems.append("CONTRACT_MISMATCH legacy_status (design §12.2): its values differ from the entry status vocabulary")
    if entry["disposition"] != {"$ref": "#/$defs/disposition"}:
        problems.append("CONTRACT_MISMATCH entry disposition (design §7.2): an entry takes the current vocabulary only")
    if defs["decision"]["properties"]["disposition"] != {"$ref": "#/$defs/legacy_disposition"}:
        problems.append("CONTRACT_MISMATCH decision disposition (design §12.2): a decision takes the vocabulary with the two legacy values")
    # The two shapes of a decisions[] element (ADDENDUM §1): the schema marks each property design §12.2
    # gives a migrated element, and this module rejects exactly those on a decision a run made.
    marked = {k for k, v in defs["decision"]["properties"].items() if str(v.get("$comment", "")).startswith(LEGACY_MARK)}
    if marked != DESIGN_12_1["element_legacy_only"]:
        problems.append(f"CONTRACT_MISMATCH decision (ADDENDUM §1): the schema marks {sorted(marked)} as a migrated element's, "
                        f"the record names {sorted(DESIGN_12_1['element_legacy_only'])}")
    return problems


def addendum_problems(text=None, rel=ADDENDUM):
    """ADDENDUM against this module: it exists, and it names a contract for every property schema 2
    carries beyond design §12.1's lists. A property added to the schema without one is then a named
    failure here, not a comment in the file that added it."""
    if text is None:
        path = REPO / rel
        if not path.is_file():
            return [f"ADDENDUM_MISSING {rel}: what schema 2 carries beyond design §12.1 has no contract"]
        text = path.read_text(encoding="utf-8")
    named = {f"`{p}`" for p in DESIGN_12_1["element_optional"] - {"kind"} - set(FIELD_RECORDS)} | {
        f"`kind: {k}`" for k in (*LEGACY_KINDS, "revert")}
    return [f"ADDENDUM_SILENT {rel}: it contracts no {token}" for token in sorted(named) if token not in text]


def field_record_problems(texts=None, field_records=None):
    """Each property FIELD_RECORDS names against its record: the property is one schema 2 carries beyond design §12.1,
    and the record exists and names it. `texts` maps a property to the text to read instead of its file;
    `field_records` replaces FIELD_RECORDS (the self-test's way to name a record that is not there)."""
    problems = []
    for prop, rel in sorted((FIELD_RECORDS if field_records is None else field_records).items()):
        if prop not in DESIGN_12_1["element_optional"]:
            problems.append(f"FIELD_RECORD_STALE {rel}: {prop} is no optional property of a decision")
        if texts is not None and prop in texts:
            text = texts[prop]
        elif (REPO / rel).is_file():
            text = (REPO / rel).read_text(encoding="utf-8")
        else:
            problems.append(f"FIELD_RECORD_MISSING {rel}: schema 2's `{prop}` has no contract")
            continue
        if f"`{prop}`" not in text:
            problems.append(f"FIELD_RECORD_SILENT {rel}: it contracts no `{prop}`")
    return problems


def record_problems(text=None, rel=RECORD):
    """The owner's decision on what a revert puts back: the record exists, it says which reading it
    supersedes, and it names the rules the code now holds. A rule decided in the code and not here
    would leave an earlier dated record standing as the contract, which is how the first one went wrong."""
    if text is None:
        path = REPO / rel
        if not path.is_file():
            return [f"RECORD_MISSING {rel}: the decision this module implements has no record"]
        text = path.read_text(encoding="utf-8")
    older = SUPERSEDED.rsplit("/", 1)[1]
    problems = [] if f"supersedes: {older}" in text else [f"RECORD_UNANCHORED {rel}: its frontmatter does not supersede {older}"]
    return problems + [f"RECORD_SILENT {rel}: it carries no {code}" for code in
                       ("applied.before", "REVERT_INVERSE_UNPROVABLE", "BEFORE_FIELD_WRONG", "TRANSACTION_MULTIPLE_APPLICATIONS",
                        "BEFORE_MISSING", "BEFORE_FIELD_OVERLAP", "REVERT_MERGE_SIDE", "standing_decision",
                        "REVERT_MERGE_UNPAIRED", "TRANSACTION_INVALID", "BASE_UNREADABLE")
                       if code not in text]


def eo_mismatch(doc):
    """The ledger's expected_observation against schemas/expected_observation.schema.json (design §7.3)."""
    mine = doc["$defs"]["expected_observation"]
    other = json.loads(EO_SCHEMA_PATH.read_text(encoding="utf-8"))
    problems = []
    if set(mine["properties"]) - {"resolutions"} != set(other["properties"]):
        problems.append("CONTRACT_MISMATCH expected_observation (design §7.3): properties differ from schemas/expected_observation.schema.json")
    if set(mine["required"]) - {"resolutions"} != set(other["required"]):
        problems.append("CONTRACT_MISMATCH expected_observation (design §7.3): required differs from schemas/expected_observation.schema.json")
    return problems


def event_problems(table):
    """The event rows of the table against the design's, and the handlers against the rows."""
    rows = table.get("events", [])
    problems = [f"CONTRACT_MISMATCH events (design §12.3): row {n} is {(r['from'], r['event'], r['to'])}, the design says {want}"
                for n, (r, want) in enumerate(zip(rows, DESIGN_12_3_EVENTS)) if (r["from"], r["event"], r["to"]) != want]
    if len(rows) != len(DESIGN_12_3_EVENTS):
        problems.append(f"CONTRACT_MISMATCH events (design §12.3): {len(rows)} rows, the design has {len(DESIGN_12_3_EVENTS)}")
    if [r["id"] for r in rows] != list(EVENTS):
        problems.append(f"CONTRACT_MISMATCH events (design §12.3): the handlers {list(EVENTS)} differ from the rows' ids {[r['id'] for r in rows]}")
    return problems


@contextlib.contextmanager
def scratch_git():
    """A scratch repository with every GIT_* variable scrubbed: the pre-commit hook exports them, and
    a repository initialised under them would rewrite the real one (AGENTS.md traps)."""
    saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("GIT_")}
    try:
        with tempfile.TemporaryDirectory() as td:
            def git(*args, check=True):
                done = subprocess.run(["git", "-C", td, "-c", "user.email=t@t", "-c", "user.name=t", *args],
                                      capture_output=True, text=True)
                assert not check or done.returncode == 0, f"git {args}: {done.stderr}"
                return done
            git("init", "-q")
            yield pathlib.Path(td), git
    finally:
        os.environ.update(saved)


def legacy_element(field="decision", disposition="unknown", **extra):
    """A decisions[] element design §12.2 migrates from a schema 1 field."""
    element = sample_element("legacy-2026-08-25", disposition, applied=False, approval="legacy",
                             **{"at": "2026-08-25", "field": field, "legacy_text": "user-approved-default 2026-08-25", **extra})
    if element["applied"] is not None:  # a legacy application carries one, and it records nothing
        element["applied"].pop("before", None)
    return element


def migration_element(status, **extra):
    """The element a migrated entry ends its legacy decisions with: its status when it was migrated."""
    return legacy_element("status", "unknown", kind="legacy_migration", legacy_status=status, legacy_text=status, **extra)


# The hard-kill fixture this module's self-test runs: a real process that proposes a successor and
# dies before the rename, so bytes that are still the base afterwards say the rename had not
# happened (X#1). An inline `python -c` program is admitted by DECLARATION
# (`runlib/dispatch.py` `INLINE_PROGRAMS`, which pins its sha256), so its text is FIXED and the four
# values it used to interpolate arrive as its own argv (r3 S3). A test fixture; nothing in this
# module's behaviour reads it.
HARD_KILL = (
    "import json, os, sys, pathlib\n"
    "here, target, current, lock_root = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]\n"
    "sys.path.insert(0, here)\n"
    "from runlib import ledger\n"
    "doc = json.loads(pathlib.Path(target).read_text())\n"
    "proposed = ledger.apply_decision(doc, 'S3-2', ledger.sample_element('r2', 'correct'))\n"
    "ledger.write_atomic(target, proposed, current, lock_root, before_rename=lambda: os._exit(9))\n")


def self_test():
    failures = []
    ran = {"events": {}, "effects": set()}

    def expect(label, problems, *needles):
        """`problems` must name every needle; an empty list for a case that must fail is a failure."""
        text = "\n".join(problems)
        for needle in needles:
            if needle not in text:
                failures.append(f"{label}: expected {needle!r} among {problems or 'no violation'}")

    def clean(label, problems):
        if problems:
            failures.append(f"{label}: expected no violation, got {problems}")

    def refuses(label, call, *needles):
        try:
            call()
        except LedgerError as exc:
            expect(label, [str(exc)], *needles)
        except Exception as exc:  # a refusal carries its code; a bare exception is reported, not raised
            failures.append(f"{label}: raised {type(exc).__name__} ({exc}) instead of a refusal naming {needles}")
        else:
            failures.append(f"{label}: accepted although {needles} was due")

    def accepts(label, call):
        try:
            return call()
        except LedgerError as exc:
            failures.append(f"{label}: refused: {exc}")

    def event_case(event, outcome):
        ran["events"].setdefault(event, set()).add(outcome)

    placed = sample_entry("S3-1")
    base = sample_ledger(placed, sample_entry("S3-2", "incubating"), sample_entry("S3-3", "incubating"))

    # contract fidelity: the schema holds the design's field lists and vocabularies, and the checker can tell
    doc = schema()
    clean("schema against design §12.1/§12.2/§12.4/§7.2", contract_problems(doc))
    clean("expected_observation against §7.3", eo_mismatch(doc))
    clean("the record contracting what schema 2 carries beyond design §12.1", addendum_problems())
    clean("the record of the owner's decision on what a revert puts back", record_problems())
    record_text = (REPO / RECORD).read_text(encoding="utf-8") if (REPO / RECORD).is_file() else ""
    for token in ("applied.before", "REVERT_INVERSE_UNPROVABLE", "TRANSACTION_MULTIPLE_APPLICATIONS",
                  "BEFORE_MISSING", "BEFORE_FIELD_OVERLAP", "REVERT_MERGE_SIDE", "standing_decision",
                  "REVERT_MERGE_UNPAIRED", "TRANSACTION_INVALID", "BASE_UNREADABLE"):
        expect(f"the record silent about {token}", record_problems(record_text.replace(token, "it")), f"RECORD_SILENT {RECORD}", token)
    expect("a record that supersedes nothing", record_problems(record_text.replace("supersedes: 2026", "supersedes: null  # 2026")),
           f"RECORD_UNANCHORED {RECORD}")
    expect("no record at all of that decision", record_problems(rel="design/session-distill/no-such-record.md"), "RECORD_MISSING")
    addendum_text = (REPO / ADDENDUM).read_text(encoding="utf-8") if (REPO / ADDENDUM).is_file() else ""
    for token in ("`legacy_placed`", "`kind: legacy_migration`", "`reason`"):
        expect(f"the record silent about {token}", addendum_problems(addendum_text.replace(token, "it")), f"ADDENDUM_SILENT {ADDENDUM}", token)
    expect("no record at all", addendum_problems(rel="design/session-distill/no-such-addendum.md"), "ADDENDUM_MISSING")
    # a property contracted by a record of its own (WP-09 commit 3): ADDENDUM is not asked for it, its record is
    clean("each property a record of its own contracts", field_record_problems())
    expect("the record of resolves silent about it", field_record_problems({"resolves": "a decision names what it settles"}),
           f"FIELD_RECORD_SILENT {FIELD_RECORDS['resolves']}")
    expect("no record of resolves at all", field_record_problems(field_records={"resolves": "design/session-distill/no-such-record.md"}),
           "FIELD_RECORD_MISSING design/session-distill/no-such-record.md")
    expect("a record contracting a property a decision does not carry", field_record_problems(
        texts={"surfaced": "`surfaced`"}, field_records={"surfaced": FIELD_RECORDS["resolves"]}), "FIELD_RECORD_STALE")
    clean("ADDENDUM is not asked for a property a record of its own contracts", addendum_problems(addendum_text.replace("`resolves`", "")))
    # design §7.1's resolves (WP-09 commit 3): a run's decision names the earlier incubate of its own entry it resolves.
    # A subject that raises is reported under its control's name, never as a traceback ending the suite.
    def run_rules(call):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - reported by the control that reads it
            return [f"RAISED {exc!r}"]
    incubate = sample_element("r1", "incubate", observation=sample_observation("2026-11-30"))
    later = sample_element("r2", "drop", reason="expired and not seen", resolves="S3-1@r1")
    clean("a drop resolving the incubate an earlier run made on the entry", run_rules(lambda: validate_ledger(sample_ledger(
        sample_entry("S3-1", "retired", decisions=[incubate, later])))))
    intervention = sample_element("r1", "incubate", observation=sample_observation("2026-11-30"))
    pending_placed = sample_ledger(sample_entry("P-1", "placed", decisions=[sample_element("r0", "place"), intervention]))
    clean("a pending intervention on a placed entry", validate_ledger(pending_placed))
    clean("unresolved_incubates lists the pending intervention on a placed entry by <entry>@<run>",
          [] if [(d["decision_id"], d["status"], d["expiry"]) for d in unresolved_incubates(pending_placed)]
          == [("P-1@r1", "placed", "2026-11-30")] else [f"listed {unresolved_incubates(pending_placed)}"])
    resolved_ledger = sample_ledger(sample_entry("S3-1", "retired", decisions=[incubate, later]))
    clean("unresolved_incubates leaves out an incubate a later decision resolves",
          [] if unresolved_incubates(resolved_ledger) == [] else [f"listed {unresolved_incubates(resolved_ledger)}"])
    open_ledger = sample_ledger(sample_entry("S3-1", "incubating", decisions=[incubate]))
    clean("unresolved_incubates lists an incubate nothing resolves",
          [] if [d["decision_id"] for d in unresolved_incubates(open_ledger)] == ["S3-1@r1"] else [f"{unresolved_incubates(open_ledger)}"])
    for label, decisions, needle in (
            ("a decision resolving another entry's incubate", [incubate, {**later, "resolves": "S3-9@r1"}], "RESOLVES_OTHER_ENTRY S3-1 decisions[1]"),
            ("a decision resolving a run that decided nothing here", [incubate, {**later, "resolves": "S3-1@r7"}], "RESOLVES_DANGLING S3-1 decisions[1]"),
            ("a decision resolving itself", [incubate, {**later, "resolves": "S3-1@r2"}], "RESOLVES_NOT_EARLIER S3-1 decisions[1]"),
            ("a decision resolving one that is not an incubate",
             [sample_element("r1", "place"), {**later, "resolves": "S3-1@r1"}], "RESOLVES_NOT_INCUBATE S3-1 decisions[1]"),
            ("two decisions resolving one incubate",
             [incubate, sample_element("r2", "incubate", observation=sample_observation(), resolves="S3-1@r1"),
              {**later, "run": "r3", "resolves": "S3-1@r1"}], "RESOLVES_TWICE S3-1 decisions[2]")):
        expect(label, run_rules(lambda decisions=decisions: resolves_problems(sample_entry("S3-1", "incubating", decisions=decisions))), needle)
    expect("validate_ledger holds the resolves rules", run_rules(lambda: validate_ledger(sample_ledger(sample_entry("S3-1", "retired", decisions=[
        incubate, {**later, "resolves": "S3-1@r7"}])))), "RESOLVES_DANGLING S3-1 decisions[1]")
    expect("a migrated element naming what it resolves", run_rules(lambda: validate_ledger(sample_ledger(sample_entry("M-1", "incubating", decisions=[
        {**legacy_element(), "resolves": "M-1@r1"}, migration_element("incubating")])))), "RESOLVES_ON_LEGACY M-1 decisions[0]")
    expect("a resolves that is no <entry>@<run>", run_rules(lambda: validate_ledger(sample_ledger(sample_entry("S3-1", "retired", decisions=[
        incubate, {**later, "resolves": "r1"}])))), "does not match '^[A-Z]+[0-9]*-[0-9]+@.+$'")
    for label, mutate, needle in (
            ("a field dropped from the entry's required set", lambda d: d["$defs"]["entry"]["required"].remove("keep"), "required lacks ['keep']"),
            ("a ninth key in the element's required set", lambda d: d["$defs"]["decision"]["required"].append("at"), "required adds ['at']"),
            ("a key dropped from the element's required set", lambda d: d["$defs"]["decision"]["required"].remove("tests"), "required lacks ['tests']"),
            ("a property dropped from applied", lambda d: d["$defs"]["applied"]["properties"].pop("delivery"), "properties lacks ['delivery']"),
            ("legacy_status dropped from the element", lambda d: d["$defs"]["decision"]["properties"].pop("legacy_status"), "properties lacks ['legacy_status']"),
            ("legacy_status values differing from the entry's", lambda d: d["$defs"]["decision"]["properties"]["legacy_status"]["enum"].append("done"),
             "CONTRACT_MISMATCH legacy_status"),
            ("a property dropped from the evidence item", lambda d: d["$defs"]["evidence_item"]["properties"].pop("evidence_id"), "properties lacks ['evidence_id']"),
            ("a legacy value leaking into the current vocabulary", lambda d: d["$defs"]["disposition"]["enum"].append("unknown"), "CONTRACT_MISMATCH disposition (design §7.2)"),
            ("a current value dropped from the vocabulary", lambda d: d["$defs"]["disposition"]["enum"].remove("drop"), "CONTRACT_MISMATCH disposition (design §7.2)"),
            ("an entry taking the legacy vocabulary", lambda d: d["$defs"]["entry"]["properties"].update(disposition={"$ref": "#/$defs/legacy_disposition"}),
             "an entry takes the current vocabulary only"),
            ("a decision taking the current vocabulary", lambda d: d["$defs"]["decision"]["properties"].update(disposition={"$ref": "#/$defs/disposition"}),
             "a decision takes the vocabulary with the two legacy values"),
            ("a legacy-only property the schema does not mark", lambda d: d["$defs"]["decision"]["properties"]["at"].pop("$comment"),
             "CONTRACT_MISMATCH decision (ADDENDUM §1)"),
            ("a property of both shapes marked as a migrated element's",
             lambda d: d["$defs"]["decision"]["properties"]["reason"].update({"$comment": LEGACY_MARK}), "CONTRACT_MISMATCH decision (ADDENDUM §1)"),
            ("the comment citing another section", lambda d: d.update({"$comment": "design §9"}), "does not cite design §12.1"),
            ("a field a disposition licenses that the before record cannot name",
             lambda d: d["$defs"]["before_row"]["properties"]["fields"]["properties"].pop("keep"), "CONTRACT_MISMATCH before_row (RECORD)"),
            ("a before record naming a field no disposition licenses",
             lambda d: (d["$defs"]["before_row"]["properties"]["fields"]["properties"].update(surfaced={"type": "string"}),
                        d["$defs"]["before_row"]["properties"]["absent"]["items"]["enum"].append("surfaced")), "CONTRACT_MISMATCH before_row (RECORD)"),
            ("a before record whose two parts name different fields",
             lambda d: d["$defs"]["before_row"]["properties"]["absent"]["items"]["enum"].remove("keep"), "CONTRACT_MISMATCH before_row (RECORD)"),
            ("the before record not citing the decision that added it",
             lambda d: d["$defs"]["before_row"].update({"$comment": "what a revert puts back"}), "its comment does not cite the decision")):
        broken = copy.deepcopy(doc)
        mutate(broken)
        expect(label, contract_problems(broken), needle)
    mutated = copy.deepcopy(doc)
    mutated["$defs"]["expected_observation"]["properties"].pop("expiry")
    expect("expected_observation losing a §7.3 field", eo_mismatch(mutated), "properties differ")
    mutated = copy.deepcopy(doc)
    mutated["$defs"]["expected_observation"]["required"].remove("expiry")
    expect("expected_observation losing a §7.3 requirement", eo_mismatch(mutated), "required differs")

    # validation: a conforming ledger first, then one rejection per rule
    clean("a conforming schema 2 ledger", validate_ledger(base))
    clean("a conforming schema 1 ledger", validate_ledger({"schema": 1, "entries": [{"id": "S3-1", "status": "placed"}]}))
    eight = sample_element("r1", "none")
    clean("an element with exactly design §12.1's eight keys", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[eight]))))
    expect("an element lacking one of the eight keys", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        {k: v for k, v in eight.items() if k != "tests"}]))), "'tests' is a required property")
    dropped = copy.deepcopy(base)
    del dropped["entries"][0]["keep"]
    expect("an entry missing a required field", validate_ledger(dropped), "LEDGER_INVALID", "'keep' is a required property")
    extra = copy.deepcopy(base)
    extra["entries"][0]["strength"] = 3
    expect("a legacy field left on an entry", validate_ledger(extra), "Additional properties", "strength")
    expect("an unsupported schema", validate_ledger({"schema": 3, "entries": []}), "LEDGER_SCHEMA_UNSUPPORTED")
    expect("schema 1 entries not a list", validate_ledger({"schema": 1, "entries": {}}), "LEDGER_INVALID entries")
    expect("a schema 1 entry without a status", validate_ledger({"schema": 1, "entries": [{"id": "S3-1"}]}), "LEDGER_INVALID entries[0]")
    expect("a duplicate id in schema 1", validate_ledger({"schema": 1, "entries": [{"id": "S3-1", "status": "p"}, {"id": "S3-1", "status": "p"}]}), "ID_DUPLICATE S3-1")
    expect("a duplicate id in schema 2", validate_ledger(sample_ledger(sample_entry("S3-1"), sample_entry("S3-1"))), "ID_DUPLICATE S3-1")
    expect("one run deciding an entry twice", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        sample_element("r1", "none"), sample_element("r1", "none")]))), "DECISION_RUN_DUPLICATE S3-1 decisions[1]")
    clean("legacy runs repeating", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        legacy_element("decision"), legacy_element("decision1", approval_id="unavailable")]))))
    expect("a run decision without an approval row", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        sample_element("r1", "none", approval="legacy")]))), "DECISION_UNAPPROVED S3-1 decisions[0]")
    expect("a relation to no entry", validate_ledger(sample_ledger(sample_entry("S3-1", relations={"instance_of": "G-9"}))), "RELATION_DANGLING S3-1 instance_of")
    expect("an absorption by no entry", validate_ledger(sample_ledger(sample_entry("S3-1", absorbed_by="G-9"))), "RELATION_DANGLING S3-1 absorbed_by")
    expect("a window run id twice", validate_ledger(sample_ledger(windows=[
        {"start": None, "end": "2026-09-01", "run_id": "w", "kind": "periodic", "commit": None, "accounted": None, "fully_read": None}] * 2)), "WINDOW_DUPLICATE w")
    misplaced = sample_ledger(sample_entry("S3-1", decisions=[sample_element("r1", "incubate", observation={
        **sample_observation(), "resolutions": [sample_resolution("r2")]})]))
    expect("a resolution under another run's decision", validate_ledger(misplaced), "RESOLUTION_MISPLACED S3-1 decisions[0]")

    # the two vocabularies (F#2): design §7.2's for everything current, the legacy values only in legacy elements
    clean("a legacy element with disposition unknown and a null date", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        legacy_element(disposition="unknown", at=None), legacy_element("decision3", disposition="revival")]))))
    for value in ("unknown", "revival"):
        expect(f"a run's decision with the legacy value {value}", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
            sample_element("r1", value)]))), "DISPOSITION_NOT_CURRENT S3-1 decisions[0]")
        expect(f"an entry with the legacy value {value}", validate_ledger(sample_ledger(sample_entry("S3-1", disposition=value))), "LEDGER_INVALID", "is not one of")
    expect("a value outside both vocabularies", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        legacy_element(disposition="adopt")]))), "LEDGER_INVALID", "'adopt' is not one of")
    expect("a legacy element without the date design §12.2 gives it", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        {k: v for k, v in legacy_element().items() if k != "at"}]))), "LEGACY_ELEMENT_INCOMPLETE S3-1 decisions[0]", "at")
    expect("a legacy element without its field name", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        {k: v for k, v in legacy_element().items() if k != "field"}]))), "LEGACY_ELEMENT_INCOMPLETE S3-1 decisions[0]", "field")
    # the two shapes (ADDENDUM §1): design §12.2's metadata belongs to a migrated element, the kind
    # revert to a decision a run made, and neither crosses
    legacy_values = {"at": "2026-08-25", "field": "decision", "legacy_text": "user-approved-default 2026-08-25",
                     "legacy_placed": "2026-07-19", "legacy_status": "incubating", "status_note": "set without a recorded revival"}
    for legacy_property in LEGACY_PROPERTIES:  # a value the schema itself accepts, so the refusal is this rule's
        expect(f"a run's decision carrying {legacy_property}", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
            sample_element("r1", "none", **{legacy_property: legacy_values[legacy_property]})]))),
            "LEGACY_FIELD_ON_MODERN S3-1 decisions[0]", legacy_property)
    expect("a migrated element marked a revert", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        legacy_element(kind="revert")]))), "LEGACY_KIND_ON_REVERT S3-1 decisions[0]")
    # legacy_placed is the date of the application its own element carries (F#4): design §12.2 attaches
    # `placed` to the latest place decision, or to a legacy_application when the entry has no place decision
    applied_record = {"commit": None, "paths": [], "operations": [], "delivery": "unverified"}
    for label, element in (("a migrated place decision", {**legacy_element("decision1"), "applied": applied_record, "legacy_placed": "2026-09-01"}),
                           ("a legacy application", {**legacy_element("placed", kind="legacy_application"), "applied": applied_record, "legacy_placed": "2026-09-01"})):
        clean(f"{label} carrying the date its application happened", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[element]))))
    for label, element in (
            ("a migrated element that records no application", legacy_element("decision1", legacy_placed="2026-09-01")),
            ("a historical retirement", {**legacy_element("retired", kind="legacy_retirement"), "applied": applied_record, "legacy_placed": "2026-09-01"}),
            ("the migration element", {**migration_element("placed"), "applied": applied_record, "legacy_placed": "2026-09-01"})):
        expect(f"legacy_placed on {label}", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[element]))),
               "LEGACY_PLACED_MISPLACED S3-1 decisions[0]")
    expect("an incubate without its observation", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        sample_element("r1", "incubate")]))), "INCUBATE_WITHOUT_OBSERVATION S3-1 decisions[0]")
    for disposition in ("keep", "drop"):
        expect(f"a {disposition} without its reason", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
            sample_element("r1", disposition)]))), f"REASON_REQUIRED S3-1 decisions[0]")
    expect("a revert that is not an applied none", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        sample_element("r1", "place", kind="revert")]))), "REVERT_MALFORMED S3-1 decisions[0]")
    expect("a status its decisions do not reach", validate_ledger(sample_ledger(sample_entry("S3-1", "retired", decisions=[
        sample_element("r1", "place")]))), "HISTORY_INCONSISTENT S3-1")
    expect("a revert with nothing before it to revert", validate_ledger(sample_ledger(sample_entry("S3-1", decisions=[
        sample_element("r1", "none", kind="revert")]))), "HISTORY_INCONSISTENT S3-1")
    refuses("a revert over a history that does not replay", lambda: revert_target(
        sample_entry("S3-1", "retired", decisions=[sample_element("r1", "place")]), "retired"), "REPLAY_INCONSISTENT S3-1")
    # the status an entry was migrated at: exactly one element, before any run decision, in the status vocabulary
    clean("a migrated entry with its migration element", validate_ledger(sample_ledger(sample_entry("M-1", "incubating", decisions=[
        legacy_element(), migration_element("incubating")]))))
    expect("a migration element without its status", validate_ledger(sample_ledger(sample_entry("M-1", "incubating", decisions=[
        {k: v for k, v in migration_element("incubating").items() if k != "legacy_status"}]))), "LEGACY_ELEMENT_INCOMPLETE M-1 decisions[0]", "legacy_status")
    expect("legacy_status on another legacy kind", validate_ledger(sample_ledger(sample_entry("M-1", decisions=[
        legacy_element(kind="legacy_application", legacy_status="placed")]))), "LEGACY_STATUS_MISPLACED M-1 decisions[0]")
    expect("legacy_status on a run decision", validate_ledger(sample_ledger(sample_entry("M-1", decisions=[
        sample_element("r1", "none", legacy_status="placed")]))), "LEGACY_FIELD_ON_MODERN M-1 decisions[0]")
    expect("a migration status outside the vocabulary", validate_ledger(sample_ledger(sample_entry("M-1", decisions=[
        migration_element("done")]))), "LEDGER_INVALID", "'done' is not one of")
    expect("two migration elements", validate_ledger(sample_ledger(sample_entry("M-1", "incubating", decisions=[
        migration_element("incubating"), migration_element("incubating")]))), "LEGACY_MIGRATION_DUPLICATE M-1")
    expect("a migration element after a run decision", validate_ledger(sample_ledger(sample_entry("M-1", decisions=[
        sample_element("r1", "correct"), migration_element("placed")]))), "LEGACY_MIGRATION_LATE M-1 decisions[1]")
    expect("an entry whose status is not the one it was migrated at and no decision moved it", validate_ledger(sample_ledger(sample_entry(
        "M-1", "placed", decisions=[migration_element("incubating")]))), "HISTORY_INCONSISTENT M-1")

    # evidence references (F#3): claim and evidence ids together, or the explicit unavailable form, never a part
    for label, item in (("a claim id with its evidence id", {"claim_id": "c-1", "evidence_id": "e-1"}),
                        ("the unavailable form of a legacy supporting session", {"locator": "unavailable", "session": "claude:1"})):
        clean(label, validate_ledger(sample_ledger(sample_entry("S3-1", evidence=[item]))))
    for label, item, needles in (
            ("a claim id with no evidence id", {"claim_id": "c-1"}, ("LEDGER_INVALID", "evidence_id")),
            ("an evidence id with no claim id", {"evidence_id": "e-1"}, ("LEDGER_INVALID", "claim_id")),
            ("an unavailable locator with no session", {"locator": "unavailable"}, ("LEDGER_INVALID", "session")),
            ("both forms in one item", {"claim_id": "c-1", "evidence_id": "e-1", "locator": "unavailable", "session": "claude:1"}, ("EVIDENCE_FORM S3-1 evidence[0]",)),
            ("an empty item", {}, ("LEDGER_INVALID",)),
            ("a locator other than unavailable", {"locator": "somewhere", "session": "claude:1"}, ("LEDGER_INVALID",)),
            ("an unknown key", {"claim_id": "c-1", "evidence_id": "e-1", "note": "x"}, ("LEDGER_INVALID", "Additional properties"))):
        expect(label, validate_ledger(sample_ledger(sample_entry("S3-1", evidence=[item]))), *needles)

    for label, raw in (("a list at the top", "[1]"), ("text that is not JSON", "{ nope")):
        refuses(label, lambda raw=raw: parse(raw), "LEDGER_UNREADABLE")

    # a schema 1 base against a schema 2 head is judged by equality with the migration
    migrator = _migrator()
    legacy_one = migrator.tiny()
    migrated_one, _ = migrator.migrate(legacy_one)
    clean("a schema 2 head that is the migration of its schema 1 base", check_pair(legacy_one, migrated_one))
    tampered_one = copy.deepcopy(migrated_one)
    tampered_one["entries"][0]["lesson"] = "tampered"
    expect("a schema 2 head that is not the migration of its base", check_pair(legacy_one, tampered_one), "MIGRATION_MISMATCH")
    global MIGRATOR
    kept_migrator, MIGRATOR = MIGRATOR, HERE / "no-such-migrator.py"
    try:
        refuses("a missing migrator", lambda: check_pair(legacy_one, migrated_one), "MIGRATOR_UNREADABLE")
    finally:
        MIGRATOR = kept_migrator

    # the id-set check (design §12.4, O10): schema 1 continues a series; schema 2 needs the frozen allocation
    ids = ["S3-1", "S3-2", "S3-3"]
    clean("identical id sets", id_set_violations(ids, ids))
    clean("a schema 1 series continuing at the next number", id_set_violations(ids, ids + ["S3-4", "G-1"], numbered=True))
    expect("a schema 1 equal-count deletion plus insertion", id_set_violations(ids, ["S3-1", "S3-2", "S3-4"], numbered=True), "ID_LOST S3-3")
    expect("a schema 1 id past the next number", id_set_violations(ids, ids + ["S3-9"], numbered=True), "ID_UNALLOCATED S3-9")
    expect("a schema 1 id reusing a gap", id_set_violations(["S3-1", "S3-3"], ["S3-1", "S3-2", "S3-3"], numbered=True), "ID_UNALLOCATED S3-2")
    expect("a schema 1 id outside every series", id_set_violations(ids, ids + ["new"], numbered=True), "ID_UNALLOCATED new")
    expect("a schema 2 id continuing a series with no allocation", id_set_violations(ids, ids + ["S3-4"]), "ALLOCATION_REQUIRED")
    clean("a schema 2 ledger validated against no base needs no allocation", id_set_violations(ids, ids))
    expect("a schema 2 transaction that added no id and froze no allocation", id_set_violations(ids, ids, transaction=True), "ALLOCATION_REQUIRED")
    clean("a schema 2 transaction whose frozen allocation is explicitly empty", id_set_violations(ids, ids, allocated=[], transaction=True))
    expect("a frozen allocation that produced no row", id_set_violations(ids, ids, allocated=["S3-7"], transaction=True), "ID_ALLOCATED_MISSING S3-7")
    clean("exactly the allocated ids", id_set_violations(ids, ids + ["S3-7"], allocated=["S3-7"]))
    clean("an allocation that skips numbers", id_set_violations(ids, ids + ["S3-7", "N-1"], allocated=["N-1", "S3-7"]))
    expect("an id outside the allocation", id_set_violations(ids, ids + ["S3-4"], allocated=["S3-7"]), "ID_UNALLOCATED S3-4", "ID_ALLOCATED_MISSING S3-7")
    expect("an allocated id the ledger never gained", id_set_violations(ids, ids, allocated=["S3-7"]), "ID_ALLOCATED_MISSING S3-7")
    expect("an allocated id the base already holds", id_set_violations(ids, ids + ["S3-4"], allocated=["S3-4", "S3-2"]), "ID_ALLOCATED_EXISTING S3-2")
    expect("an equal-count deletion plus insertion under an allocation", id_set_violations(ids, ["S3-1", "S3-2", "S3-4"], allocated=["S3-4"]), "ID_LOST S3-3")
    expect("a duplicate id", check_pair(base, sample_ledger(*base["entries"], sample_entry("S3-2"))), "ID_DUPLICATE S3-2")

    # changed rows between schema 2 ledgers (F#1): what was appended licenses a change, and only that change
    def changed(label, mutate, *needles, expect_clean=False, over=None, allocated=()):
        """A transaction over `over`: the run froze an allocation, empty unless the case says otherwise."""
        start = over or base
        head = copy.deepcopy(start)
        mutate(head)
        found = check_pair(start, head, None if allocated is None else list(allocated))
        (clean if expect_clean else lambda lab, p: expect(lab, p, *needles))(label, found)

    def bound(h, i, element, **fields):
        """Append `element` to entry i the way apply_decision does: the entry says what the decision
        says, and the decision records what its own change replaced (`applied.before`)."""
        was = copy.deepcopy(h["entries"][i])
        h["entries"][i].update(fields)
        element = copy.deepcopy(element)
        if element["applied"] is not None and not is_legacy(element):
            element["applied"]["before"] = before_record(was, h["entries"][i])
        h["entries"][i]["decisions"].append(element)

    changed("an unchanged ledger", lambda h: None, expect_clean=True)
    changed("a field edited with no decision", lambda h: h["entries"][0].update(lesson="edited"), "ROW_FIELD_UNLICENSED S3-1 lesson")
    changed("a status moved with no decision", lambda h: h["entries"][1].update(status="placed"),
            "ROW_FIELD_UNLICENSED S3-2 status", "STATUS_UNEXPLAINED S3-2")
    changed("an applied correct that moves nothing", lambda h: bound(h, 0, sample_element("r1", "correct"), disposition="correct"), expect_clean=True)
    # the frozen allocation (C#4): a schema 2 run that writes at all carries one, empty or not
    changed("that same transaction with no allocation frozen", lambda h: bound(
        h, 0, sample_element("r1", "correct"), disposition="correct"), "ALLOCATION_REQUIRED", allocated=None)
    changed("that same transaction under an allocation that produced no row", lambda h: bound(
        h, 0, sample_element("r1", "correct"), disposition="correct"), "ID_ALLOCATED_MISSING S3-7", allocated=["S3-7"])
    changed("an applied decision the entry does not say it holds", lambda h: bound(h, 0, sample_element("r1", "correct")), "DISPOSITION_UNBOUND S3-1")
    changed("an unapplied decision alone", lambda h: bound(h, 0, sample_element("r1", "place", applied=False)), expect_clean=True)
    changed("an unapplied decision licensing an unrelated edit", lambda h: bound(
        h, 0, sample_element("r1", "place", applied=False), lesson="edited"), "ROW_FIELD_UNLICENSED S3-1 lesson")
    changed("an unapplied decision licensing a status change", lambda h: bound(
        h, 1, sample_element("r1", "place", applied=False), status="placed"), "ROW_FIELD_UNLICENSED S3-2 status", "STATUS_UNEXPLAINED S3-2")
    # an application stands whatever its delivery check found (design §10.6, ADDENDUM §3): it moves the
    # status and licenses what its disposition licenses, exactly as a verified one does
    changed("a correct whose delivery failed revising the text it corrected", lambda h: bound(
        h, 0, sample_element("r1", "correct", delivery="failed"), disposition="correct", lesson="edited"), expect_clean=True)
    changed("a place whose delivery went unverified moving the status", lambda h: bound(
        h, 1, sample_element("r1", "place", delivery="unverified"), status="placed", disposition="place"), expect_clean=True)
    changed("a decision whose delivery failed licensing a field its disposition does not", lambda h: bound(
        h, 0, sample_element("r1", "correct", delivery="failed"), disposition="correct", window="2026-09-01"), "ROW_FIELD_UNLICENSED S3-1 window")
    changed("an applied decision licensing an unrelated field", lambda h: bound(
        h, 1, sample_element("r1", "place"), status="placed", disposition="place", window="2026-09-01"), "ROW_FIELD_UNLICENSED S3-2 window")
    changed("an applied decision licensing its own status and fields", lambda h: bound(
        h, 1, sample_element("r1", "place"), status="placed", disposition="place"), expect_clean=True)
    # the licence is the decision's own disposition (C#3, ADDENDUM §3): positive first, then the edit it
    # does not carry. An applied `none` changes nothing; an incubated or dropped intervention on a placed
    # entry leaves what is installed alone.
    changed("an applied none on a placed entry", lambda h: bound(h, 0, sample_element("r1", "none"), disposition="none"), expect_clean=True)
    changed("an applied none rewriting the installed text", lambda h: bound(
        h, 0, sample_element("r1", "none"), disposition="none", lesson="edited"), "ROW_FIELD_UNLICENSED S3-1 lesson")
    changed("an applied none rewriting the destination", lambda h: bound(
        h, 0, sample_element("r1", "none"), disposition="none", destination={"implementation": "x", "anchor": None, "package_id": None}),
        "ROW_FIELD_UNLICENSED S3-1 destination")
    pending = sample_element("r1", "incubate", observation=sample_observation())
    changed("a pending intervention on a placed entry", lambda h: bound(h, 0, pending, disposition="incubate"), expect_clean=True)
    changed("a pending intervention rewriting the destination", lambda h: bound(
        h, 0, pending, disposition="incubate", destination={"implementation": "x", "anchor": None, "package_id": None}),
        "ROW_FIELD_UNLICENSED S3-1 destination")
    changed("a pending intervention rewriting the installed text", lambda h: bound(
        h, 0, pending, disposition="incubate", lesson="edited"), "ROW_FIELD_UNLICENSED S3-1 lesson")
    dropped_intervention = sample_element("r1", "drop", reason="the miss is acceptable: the unit is still right")
    changed("a dropped intervention on a placed entry", lambda h: bound(h, 0, dropped_intervention, disposition="drop"), expect_clean=True)
    changed("a dropped intervention rewriting the destination", lambda h: bound(
        h, 0, dropped_intervention, disposition="drop", destination={"implementation": "x", "anchor": None, "package_id": None}),
        "ROW_FIELD_UNLICENSED S3-1 destination")
    changed("a correct revising the text it corrected", lambda h: bound(
        h, 0, sample_element("r1", "correct"), disposition="correct", lesson="edited"), expect_clean=True)
    refuses("an applied none carrying an edit of the installed text", lambda: apply_decision(
        base, "S3-1", sample_element("r1", "none"), {"lesson": "edited"}), "UPDATES_UNLICENSED S3-1", "none")
    refuses("a pending intervention carrying a new destination", lambda: apply_decision(
        base, "S3-1", pending, {"destination": {"implementation": "x", "anchor": None, "package_id": None}}),
        "UPDATES_UNLICENSED S3-1", "incubate")
    refuses("a dropped intervention carrying a new destination", lambda: apply_decision(
        base, "S3-1", dropped_intervention, {"destination": {"implementation": "x", "anchor": None, "package_id": None}}),
        "UPDATES_UNLICENSED S3-1", "drop")
    accepts("a correct carrying the text it revised", lambda: apply_decision(base, "S3-1", sample_element("r1", "correct"), {"lesson": "edited"}))
    # an element of the migration licenses nothing in a transaction (F#0): it carries no approval row,
    # and design §12.2 writes it only when the schema 1 ledger is migrated
    # the fabrication wears a disposition the table accepts, so without the rule above its edit is
    # licensed and the ledger holds a correction no approval row stands behind
    fabricated = {**legacy_element("decision1", "correct"), "applied": {"commit": None, "paths": [], "operations": [], "delivery": "unverified"}}
    changed("a run's decision licensing the same edit", lambda h: bound(
        h, 0, sample_element("r1", "correct"), disposition="correct", lesson="edited"), expect_clean=True)
    changed("a fabricated legacy element licensing a lesson edit", lambda h: bound(
        h, 0, fabricated, disposition="correct", lesson="edited"), "LEGACY_ELEMENT_APPENDED S3-1 decisions[0]", "ROW_FIELD_UNLICENSED S3-1 lesson")
    changed("a fabricated legacy element appended alone", lambda h: bound(h, 0, fabricated), "LEGACY_ELEMENT_APPENDED S3-1 decisions[0]")
    # A revert puts back what the application it undoes recorded (RECORD): one round trip per
    # disposition that changes a row, over entries whose migrated status gives the history one start,
    # each application run through production code so the record it writes is the one a revert reads.
    HOME = {"implementation": "claude/CLAUDE.md §x", "anchor": "claude/CLAUDE.md#x", "package_id": None}
    ROUTE = {"implementation": "claude/guides/x.md §y", "anchor": "claude/guides/x.md#y", "package_id": "@d1/x"}
    revert_of = sample_element("r3", "none", kind="revert")

    def migrated(eid, status, **fields):
        return sample_entry(eid, status, decisions=[migration_element(status)], **fields)

    def undo(ledger, eid="M-1", run="r3"):
        return apply_decision(ledger, eid, sample_element(run, "none", kind="revert"))

    for label, start_entry, element, updates, want in (
            ("a place", migrated("M-1", "incubating", kind="gap"), sample_element("r2", "place"),
             {"destination": HOME}, {"status": "incubating", "destination": None}),
            ("a place that also sets a relation", migrated("M-1", "incubating", kind="gap"), sample_element("r2", "place"),
             {"destination": HOME, "relations": {"instance_of": "G-0"}},
             {"status": "incubating", "destination": None, "relations": {}}),
            ("a correction design §12.3 requires to revise the text",
             migrated("M-1", "incubating", kind="gap", lesson="the first lesson"), sample_element("r2", "correct"),
             {"lesson": "the corrected lesson"}, {"status": "incubating", "lesson": "the first lesson"}),
            ("a correction with no operations recorded",
             migrated("M-1", "placed", kind="misfire", destination=HOME, lesson="the first lesson"), sample_element("r2", "correct"),
             {"lesson": "the corrected lesson"}, {"status": "placed", "lesson": "the first lesson"}),
            ("a re-delivery", migrated("M-1", "placed", kind="not delivered", destination=HOME), sample_element("r2", "re-deliver"),
             {"destination": ROUTE}, {"status": "placed", "destination": HOME}),
            ("a keep", migrated("M-1", "placed", kind="confirmed"), sample_element("r2", "keep", reason="the unit still works"),
             {"keep": {"units": ["u"]}}, {"status": "placed", "keep": None}),
            ("a deletion", migrated("M-1", "placed", kind="obsolete", destination=HOME), sample_element("r2", "reduce"),
             {"retired": "2026-11-01", "retire_reason": "obsolete"}, {"status": "placed", "retired": None, "retire_reason": None}),
            ("a deletion over a retirement design §12.2 migrated",
             sample_entry("M-1", "placed", kind="obsolete", destination=HOME, retired="2026-08-09", retire_reason="superseded",
                          decisions=[legacy_element("retired", kind="legacy_retirement"), migration_element("placed")]),
             sample_element("r2", "reduce"), {"retired": "2026-11-01", "retire_reason": "obsolete"},
             {"status": "placed", "retired": "2026-08-09", "retire_reason": "superseded"}),
            ("a merge", migrated("M-1", "placed", kind="misfire", destination=HOME), sample_element("r2", "reduce", operations=[MERGE]),
             {"absorbed_by": "G-0"}, {"status": "placed", "absorbed_by": None})):
        ledger = sample_ledger(start_entry, sample_entry("G-0"))
        done = accepts(f"{label} applied to a migrated entry", lambda ledger=ledger, element=element, updates=updates:
                       apply_decision(ledger, "M-1", element, updates))
        if done is None:
            continue
        recorded = before_of(_rows(done)["M-1"]["decisions"][-1])
        if recorded != before_record(_rows(ledger)["M-1"], _rows(done)["M-1"]):
            failures.append(f"{label}: the decision recorded {recorded}, not what the row held before it")
        undone = accepts(f"a revert of {label}", lambda done=done: undo(done))
        if undone is None:
            continue
        row = _rows(undone)["M-1"]
        left = {field: row.get(field) for field in want}
        if left != want:
            failures.append(f"revert of {label}: the row is {left}, the record says {want}")
        if label == "a merge":  # the merge wrote a decision on the receiver, so the revert reaches it too
            receiver = _rows(undone)["G-0"]
            if len(receiver["decisions"]) != 2 or receiver["decisions"][-1].get("kind") != "revert" or receiver["disposition"] != "none":
                failures.append(f"revert of a merge: the receiving entry still holds the merge it was given: {receiver['decisions']}")
        clean(f"a revert of {label}, as a transaction", check_pair(done, undone, []))
        refuses(f"a revert of {label} handed the value to put back", lambda done=done, updates=updates: apply_decision(
            done, "M-1", revert_of, updates), "REVERT_VALUE_SUPPLIED M-1", "it puts back what the application it undoes recorded")
        cheated = copy.deepcopy(done)
        cheated["entries"][0]["decisions"].append(revert_of)
        cheated["entries"][0]["disposition"] = "none"
        cheated["entries"][0]["status"] = want["status"]
        expect(f"a revert of {label} recorded without putting the row back", check_pair(done, cheated, []), "REVERT_NOT_RESTORED M-1")
    # a keep reaffirmed with the same record, and one that changes it: the earlier record comes back,
    # which is what clearing it to null used to destroy (K#0, L#4)
    for label, second in (("the same record", {"keep": {"units": ["u"]}}), ("a wider record", {"keep": {"units": ["u", "v"]}})):
        twice = accepts(f"a keep reaffirmed with {label}", lambda second=second: apply_decision(apply_decision(
            sample_ledger(migrated("M-1", "placed", kind="confirmed"), sample_entry("G-0")), "M-1",
            sample_element("r2", "keep", reason="the unit works"), {"keep": {"units": ["u"]}}),
            "M-1", sample_element("r3", "keep", reason="it still works"), second))
        if twice is None:
            continue
        back = accepts(f"a revert of the keep reaffirmed with {label}", lambda twice=twice: undo(twice, run="r4"))
        if back is not None:
            if _rows(back)["M-1"]["keep"] != {"units": ["u"]}:
                failures.append(f"revert of a keep reaffirmed with {label}: the earlier keep record is {_rows(back)['M-1']['keep']}, "
                                f"not the {{'units': ['u']}} the second keep replaced")
            clean(f"a revert of the keep reaffirmed with {label}, as a transaction", check_pair(twice, back, []))
    # an application that recorded nothing: its status can be reverted and its fields cannot (RECORD)
    silent = accepts("an application recorded by hand with no before", lambda: apply_decision(
        sample_ledger(migrated("M-1", "incubating", kind="gap"), sample_entry("G-0")), "M-1", sample_element("r2", "incubate", observation=sample_observation())))
    if silent is not None:
        stripped = copy.deepcopy(silent)
        _rows(stripped)["M-1"]["decisions"][-1]["applied"].pop("before")
        refuses("a revert of an application that recorded nothing", lambda: undo(stripped),
                "REVERT_INVERSE_UNPROVABLE M-1 applied.before", "r2")
    # the record against the row change it claims to describe
    for label, mutate, needle in (
            ("a field the application changed and its record does not name", lambda b: b["fields"].pop("lesson"), "BEFORE_FIELD_MISSING"),
            ("a field its record names and the application did not change", lambda b: b["fields"].update(domain="elsewhere"), "BEFORE_FIELD_EXTRA"),
            ("a value its record gets wrong", lambda b: b["fields"].update(lesson="never there"), "BEFORE_FIELD_WRONG"),
            ("a field recorded as absent that held a value", lambda b: (b["fields"].pop("lesson"), b["absent"].append("lesson")), "BEFORE_FIELD_WRONG")):
        changed(f"a transaction whose applied.before names {label}", lambda h, mutate=mutate: mutate(
            bound(h, 0, sample_element("r1", "correct"), disposition="correct", lesson="edited") or h["entries"][0]["decisions"][-1]["applied"]["before"]),
            needle, over=sample_ledger(sample_entry("S3-1", lesson="the first lesson")))
    # an application and its revert batched into one close: the row between them is recorded nowhere
    changed("a transaction appending one applied decision", lambda h: bound(
        h, 0, sample_element("r1", "keep", reason="kept"), disposition="keep", keep={"units": ["u"]}), expect_clean=True)
    changed("a transaction appending an applied keep and its revert", lambda h: (
        bound(h, 0, sample_element("r1", "keep", reason="kept"), disposition="keep", keep={"units": ["u"]}),
        bound(h, 0, sample_element("r2", "none", kind="revert"), disposition="none")), "TRANSACTION_MULTIPLE_APPLICATIONS S3-1")
    # the receiving entry of a merge (K#2, L#3): bound to the merge's own operation, and its row put
    # back by the record that decision carries
    pre_merge = sample_ledger(migrated("M-1", "placed", kind="misfire", destination=HOME), sample_entry("G-0"))
    merged = accepts("a merge into a receiving entry", lambda: apply_decision(
        pre_merge, "M-1", sample_element("r2", "reduce", operations=[MERGE]), {"absorbed_by": "G-0"}))
    if merged is not None:
        alone = copy.deepcopy(merged)
        alone["entries"][0]["decisions"].append(revert_of)
        alone["entries"][0]["disposition"] = "none"
        alone["entries"][0].update(status="placed")
        alone["entries"][0].pop("absorbed_by", None)
        expect("the absorbed row put back and its receiver left holding the merge", check_pair(merged, alone, []),
               "RECEIVER_REVERT_MISSING G-0")
        moved_on = accepts("a correction of the receiving entry after the merge", lambda: apply_decision(
            merged, "G-0", sample_element("r3", "correct")))
        if moved_on is not None:
            refuses("a revert of the merge once the receiver has moved on", lambda: undo(moved_on, run="r4"),
                    "REVERT_INVERSE_UNPROVABLE G-0 decisions", "r3")
            reverted_anyway = copy.deepcopy(moved_on)
            late = sample_element("r4", "none", kind="revert")
            absorbed_row, receiving_row = _rows(reverted_anyway)["M-1"], _rows(reverted_anyway)["G-0"]
            absorbed_row["decisions"].append(late)
            absorbed_row.update(status="placed", disposition="none")
            absorbed_row.pop("absorbed_by", None)
            receiving_row["decisions"].append(merge_receiver_revert(late, "M-1"))
            receiving_row["disposition"] = "none"
            expect("a transaction reverting a merge the receiver has moved on from", check_pair(moved_on, reverted_anyway, []),
                   "REVERT_INVERSE_UNPROVABLE G-0 decisions")
        unrecorded = copy.deepcopy(merged)
        _rows(unrecorded)["G-0"]["decisions"][-1]["applied"].pop("before")
        refuses("a revert of a merge whose decision on the receiver recorded nothing", lambda: undo(unrecorded),
                "REVERT_INVERSE_UNPROVABLE G-0 applied.before", "replaced here")
        mismatched = copy.deepcopy(merged)
        _rows(mismatched)["G-0"]["decisions"][-1]["applied"]["operations"] = [{**MERGE, "operation_id": "op-9"}]
        refuses("a revert of a merge the receiver recorded under another operation", lambda: undo(mismatched),
                "REVERT_INVERSE_UNPROVABLE G-0 decisions", "op-1")
        orphaned = copy.deepcopy(merged)
        _rows(orphaned)["G-0"].update(decisions=[], disposition="none")
        refuses("a revert of a merge the receiving entry never recorded", lambda: undo(orphaned),
                "REVERT_INVERSE_UNPROVABLE G-0 decisions", "none of it to put back")
        # the receiver's own history moves on and comes back: the merge is reverted once its own
        # revert leaves the merge's decision standing again, which is the stack and not the list (Q#3)
        if moved_on is not None:
            settled = accepts("the correction of the receiver reverted", lambda: apply_decision(
                moved_on, "G-0", sample_element("r4", "none", kind="revert")))
            if settled is not None:
                back = accepts("a revert of the merge once the receiver's own revert put it back", lambda: undo(settled, run="r5"))
                if back is not None and _rows(back)["M-1"].get("absorbed_by") is not None:
                    failures.append("the merge was not released although the receiver's standing decision was the merge's again")
        # the merge is put back on both rows or neither, from either side (Q#2)
        refuses("a revert of the merge from the entry that received it", lambda: record_event(
            merged, "G-0", "revert", element=sample_element("r3", "none", kind="revert")), "REVERT_MERGE_SIDE G-0",
            "reverts it on M-1")  # the refusal names the entry the merge absorbed (S#3)
        one_side = copy.deepcopy(merged)
        receiving_row = _rows(one_side)["G-0"]
        receiving_row["decisions"].append(merge_receiver_revert(sample_element("r3", "none", kind="revert"), "M-1"))
        receiving_row["disposition"] = "none"
        expect("a transaction putting the receiver back and leaving the row it absorbed", check_pair(merged, one_side, []),
               "REVERT_MERGE_SIDE G-0", "M-1, the entry that made it")
        # and the merge is no longer the receiver's standing application once that revert is in its
        # history, so the source cannot put it back on its own either (Q#3)
        refuses("a revert of a merge the receiver has already released", lambda: undo(one_side),
                "REVERT_INVERSE_UNPROVABLE G-0 decisions", "is none")
        adrift = copy.deepcopy(merged)
        _rows(adrift)["G-0"]["status"] = "retired"
        refuses("a revert of a merge whose receiving entry's own decisions do not replay to its status",
                lambda: undo(adrift), "REPLAY_INCONSISTENT G-0")
        # a receiver put back where no row of the base made the merge it says it received: there is no
        # second row to revert with it, so the pair cannot be closed either way (Q#2)
        received = {**merge_receiver_element(sample_element("r2", "reduce", operations=[MERGE]), "M-1"), "disposition": "correct"}
        stranded = sample_ledger(sample_entry("G-0", "placed", disposition="correct",
                                              decisions=[migration_element("placed"), received]))
        clean("a receiving decision whose merge no row of this ledger made", validate_ledger(stranded))
        on_its_own = copy.deepcopy(stranded)
        _rows(on_its_own)["G-0"]["decisions"].append(merge_receiver_revert(sample_element("r3", "none", kind="revert"), "M-1"))
        _rows(on_its_own)["G-0"]["disposition"] = "none"
        expect("a transaction putting that receiver back with no row to put back beside it",
               check_pair(stranded, on_its_own, []), "REVERT_MERGE_SIDE G-0", "no entry of the base merged into this one")

        # a pair is two reverts that each undo the merge, and a same-run revert on the right row is
        # not that by itself: the replay says what a revert undoes, because a revert names no target
        # (S#0). The source's own later decision is the counterexample — its revert undoes that one.
        after_drop = accepts("a field-neutral drop on the absorbed row", lambda: apply_decision(
            merged, "M-1", sample_element("r3", "drop", reason="the unit is gone")))
        if after_drop is not None:
            drop_back = accepts("that drop reverted on the absorbed row alone", lambda: undo(after_drop, run="r4"))
            if drop_back is not None:
                clean("a revert of a decision that is not the merge, as a transaction", check_pair(after_drop, drop_back, []))
                unpaired = copy.deepcopy(drop_back)
                late = sample_element("r4", "none", kind="revert")
                receiving_row = _rows(unpaired)["G-0"]
                receiving_row["decisions"].append(merge_receiver_revert(late, "M-1"))
                receiving_row["disposition"] = "none"
                expect("a transaction releasing the receiver beside a revert that undoes the source's later drop",
                       check_pair(after_drop, unpaired, []), "REVERT_MERGE_UNPAIRED G-0", "undoes another decision of that row")
        # and the receiver's revert is the one this transaction appends: an older revert of the same
        # run, sitting in the receiver's history for another reason, closes no pair (S#0)
        settled_first = accepts("a correction of the receiving entry reverted before any merge", lambda: apply_decision(
            apply_decision(pre_merge, "G-0", sample_element("r0", "correct")), "G-0", sample_element("r1", "none", kind="revert")))
        if settled_first is not None:
            merged_after = accepts("a merge into a receiving entry whose history already holds a revert", lambda: apply_decision(
                settled_first, "M-1", sample_element("r2", "reduce", operations=[MERGE]), {"absorbed_by": "G-0"}))
            if merged_after is not None:
                source_only = copy.deepcopy(merged_after)
                absorbed_row = _rows(source_only)["M-1"]
                reopened = sample_element("r1", "none", kind="revert")
                reopened["applied"]["before"] = {"fields": {"absorbed_by": "G-0"}, "absent": []}
                absorbed_row["decisions"].append(reopened)
                absorbed_row.update(status="placed", disposition="none")
                absorbed_row.pop("absorbed_by", None)
                expect("a transaction reverting the merge on the source and reading the receiver's older revert of that run",
                       check_pair(merged_after, source_only, []), "RECEIVER_REVERT_MISSING G-0", "appends no revert of it on this entry")
        # a close may write a delivery outcome and append a resolution to a decision already recorded
        # (ADDENDUM §3), and a pair is judged by which decision the replay says each revert undoes,
        # not by comparing the decisions themselves — which would read either of those as a different
        # decision and refuse a sound pair (T#1)
        paired = accepts("a merge reverted on both rows", lambda: undo(merged))
        if paired is not None:
            clean("that pair, as a transaction", check_pair(merged, paired, []))
            with_delivery = copy.deepcopy(paired)
            _rows(with_delivery)["M-1"]["decisions"][1]["applied"]["delivery"] = "failed"
            clean("a pair in a close that also records the merge's delivery as failed", check_pair(merged, with_delivery, []))
        observed = accepts("a merge whose decision carries an observation", lambda: apply_decision(
            pre_merge, "M-1", sample_element("r2", "reduce", operations=[MERGE], observation=sample_observation()),
            {"absorbed_by": "G-0"}))
        if observed is not None:
            watched = accepts("that merge reverted on both rows", lambda: undo(observed))
            if watched is not None:
                with_resolution = copy.deepcopy(watched)
                _rows(with_resolution)["M-1"]["decisions"][1]["expected_observation"]["resolutions"].append(sample_resolution("r2"))
                clean("a pair in a close that also appends a resolution to the merge's observation",
                      check_pair(observed, with_resolution, []))
        # the row the merge named is part of its identity: two rows can carry a merge of one run and
        # one operation id, and the one that merged into this entry is the one this revert pairs with
        # (T#0). Each of these holds a receiver whose own decision says no more than the merge does.
        def absorbed_into(eid, receiver_id, run="r2"):
            made = sample_element(run, "reduce", operations=[MERGE])
            made["applied"]["before"] = {"fields": {}, "absent": ["absorbed_by"]}  # the row held none before the merge
            return sample_entry(eid, "absorbed", kind="misfire", disposition="reduce", absorbed_by=receiver_id, decisions=[
                migration_element("placed"), made])

        def released(ledger, source_id, receiver_ids, run="r9"):
            """The transaction that puts the merge back: a revert appended to the source and to each
            entry named, the way the owner's revert of the source writes them."""
            head, late = copy.deepcopy(ledger), sample_element(run, "none", kind="revert")
            for receiver_id in receiver_ids:
                row = _rows(head)[receiver_id]
                row["decisions"].append(merge_receiver_revert(late, source_id))
                row["disposition"] = "none"
            row = _rows(head)[source_id]
            reopened = copy.deepcopy(late)
            reopened["applied"]["before"] = {"fields": {"absorbed_by": row["absorbed_by"]}, "absent": []}
            row["decisions"].append(reopened)
            row.update(status="placed", disposition="none")
            row.pop("absorbed_by", None)
            return head

        received_merge = merge_receiver_element(sample_element("r2", "reduce", operations=[MERGE]), "M-1")
        one_maker = sample_ledger(absorbed_into("M-1", "G-0"), sample_entry(
            "G-0", "placed", disposition="correct", decisions=[migration_element("placed"), received_merge]))
        clean("a merge of one run and one operation recorded on both of its rows", validate_ledger(one_maker))
        clean("that merge put back on both of its rows", check_pair(one_maker, released(one_maker, "M-1", ["G-0"]), []))
        two_makers = sample_ledger(absorbed_into("M-1", "G-0"), absorbed_into("M-2", "G-0"), sample_entry(
            "G-0", "placed", disposition="correct", decisions=[migration_element("placed"), copy.deepcopy(received_merge)]))
        clean("two entries absorbed into one by a merge of the same run and operation", validate_ledger(two_makers))
        expect("a receiver put back where two entries recorded that merge into it",
               check_pair(two_makers, released(two_makers, "M-1", ["G-0"]), []), "REVERT_MERGE_SIDE G-0", "not decidable")
        elsewhere = sample_ledger(absorbed_into("M-1", "G-1"), sample_entry(
            "G-1", "placed", disposition="correct", decisions=[migration_element("placed"), copy.deepcopy(received_merge)]), sample_entry(
            "G-0", "placed", disposition="correct", decisions=[migration_element("placed"), copy.deepcopy(received_merge)]))
        clean("a merge into one entry beside another holding a decision of the same run and operation", validate_ledger(elsewhere))
        beside = check_pair(elsewhere, released(elsewhere, "M-1", ["G-0", "G-1"]), [])
        expect("a receiver put back beside the pair of a merge that was never into it", beside,
               "REVERT_MERGE_SIDE G-0", "no entry of the base merged into this one")
        if [problem for problem in beside if "G-1" in problem]:
            failures.append(f"the merge into G-1 was put back on both its rows and still drew {[p for p in beside if 'G-1' in p]}")
        # a revert of the receiver's own, carrying the merge's run and operation: it looks like the
        # application that received the merge and is not one, because a revert never stands (S#2)
        masked_receiver = sample_entry("G-0", "placed", disposition="none", decisions=[
            migration_element("placed"), sample_element("r0", "correct"),
            sample_element("r2", "none", kind="revert", operations=[MERGE])])
        masked = sample_ledger(sample_entry("M-1", "absorbed", kind="misfire", disposition="reduce", absorbed_by="G-0", decisions=[
            migration_element("placed"), sample_element("r2", "reduce", operations=[MERGE])]), masked_receiver)
        clean("a receiver whose own revert carries the merge's run and operation", validate_ledger(masked))
        refuses("a revert of a merge whose receiver recorded a revert carrying that run and operation",
                lambda: undo(masked), "REVERT_INVERSE_UNPROVABLE G-0 decisions", "is none")
        # a merge whose receiver's own row the merge changed: the record on the receiver's decision is
        # what puts that row back, through the transaction side and through the event API (Q#4)
        routed = copy.deepcopy(merged)
        receiving_row = _rows(routed)["G-0"]
        receiving_row["decisions"][-1]["applied"]["before"] = {"fields": {"lesson": receiving_row["lesson"]}, "absent": ["destination"]}
        receiving_row["decisions"][-1]["applied"]["operations"] = [MERGE, {"operation_id": "op-2", "type": "route",
                                                                          "target": "claude/guides/x.md"}]
        receiving_row.update(lesson="the merged lesson", destination=ROUTE)
        clean("a merge that revised the receiving entry's own text and route", check_pair(pre_merge, routed, []))
        released = accepts("the owner's revert of a merge that revised the receiver", lambda: undo(routed))
        if released is not None:
            receiver = _rows(released)["G-0"]
            if receiver["lesson"] != _rows(merged)["G-0"]["lesson"] or receiver["destination"] is not None:
                failures.append(f"the revert of a merge that revised the receiver left {receiver['lesson']!r} and "
                                f"{receiver['destination']!r}, not the values its decision recorded")
            clean("that revert, as a transaction", check_pair(routed, released, []))
            for label, mutate, needle in (
                    ("the receiver's text", lambda r: r.update(lesson="never there"), "REVERT_NOT_RESTORED G-0 lesson"),
                    ("the receiver's route", lambda r: r.update(destination=ROUTE), "REVERT_NOT_RESTORED G-0 destination")):
                planted = copy.deepcopy(released)
                mutate(_rows(planted)["G-0"])
                expect(f"a revert of that merge leaving {label} as the merge wrote it", check_pair(routed, planted, []), needle)
        overlap = copy.deepcopy(routed)
        _rows(overlap)["G-0"]["decisions"][-1]["applied"]["before"]["absent"].append("lesson")
        expect("a merge whose receiver's record says the row both held a value and held none",
               check_pair(pre_merge, overlap, []), "BEFORE_FIELD_OVERLAP G-0")
    # every application records what it replaced, and a row that did not exist replaced nothing (Q#0)
    # the creating decision carries design §12.1's four keys and no record of its own, so what the
    # created row holds is what create_entry wrote there, not what the caller handed in (S#1)
    bare = sample_element("r1", "place")
    bare["applied"].pop("before")
    anchored = sample_ledger(sample_entry("G-0"))
    created = accepts("an entry created by a place that records nothing of its own", lambda: create_entry(
        anchored, sample_entry("N-1", kind="gap"), bare))
    if created is not None:
        if before_of(_rows(created)["N-1"]["decisions"][0]) != EMPTY_BEFORE:
            failures.append(f"the decision that created an entry recorded {before_of(_rows(created)['N-1']['decisions'][0])}, "
                            f"and create_entry is what writes the empty record there")
        clean("that created row, as a transaction", check_pair(anchored, created, ["N-1"]))
        for label, mutate, needle in (
                ("no record at all", lambda d: d["applied"].pop("before", None), "BEFORE_MISSING N-1 decisions[0]"),
                ("a value it claims to have replaced", lambda d: d["applied"]["before"]["fields"].update(lesson="never there"),
                 "BEFORE_FIELD_EXTRA N-1 decisions[0]"),
                ("a field it claims the row held none of", lambda d: d["applied"]["before"]["absent"].append("destination"),
                 "BEFORE_FIELD_EXTRA N-1 decisions[0]"),
                ("both parts naming one field", lambda d: (d["applied"]["before"]["fields"].update(keep={"units": ["u"]}),
                                                           d["applied"]["before"]["absent"].append("keep")), "BEFORE_FIELD_OVERLAP N-1")):
            planted = copy.deepcopy(created)
            # each plant is written against a record it seeds itself, so that the control above is
            # the only one reading what create_entry generated
            decision = _rows(planted)["N-1"]["decisions"][0]
            decision["applied"].setdefault("before", copy.deepcopy(EMPTY_BEFORE))
            mutate(decision)
            expect(f"a row this transaction allocated whose creating decision records {label}",
                   check_pair(anchored, planted, ["N-1"]), needle)
    changed("a transaction appending an application that records nothing at all", lambda h: (
        bound(h, 0, sample_element("r1", "none"), disposition="none"),
        h["entries"][0]["decisions"][-1]["applied"].pop("before")), "BEFORE_MISSING S3-1 decisions[0]")
    changed("a transaction whose applied.before says the row both held a value and held none", lambda h: (
        bound(h, 0, sample_element("r1", "correct"), disposition="correct", lesson="edited"),
        h["entries"][0]["decisions"][-1]["applied"]["before"]["absent"].append("lesson")), "BEFORE_FIELD_OVERLAP S3-1",
        over=sample_ledger(sample_entry("S3-1", lesson="the first lesson")))
    changed("a migrated element carrying a record of what it replaced", lambda h: h["entries"][0]["decisions"][0]["applied"].update(
        before=copy.deepcopy(EMPTY_BEFORE)), "LEGACY_BEFORE S3-1 decisions[0]", over=sample_ledger(sample_entry(
            "S3-1", "placed", decisions=[{**legacy_element("placed", kind="legacy_application"), "applied": {
                "commit": None, "paths": [], "operations": [], "delivery": "unverified"}}])))
    # the entry design §12.2 migrated with its retirement on the row and no element of its own: a
    # decision that changes nothing records nothing, so its revert restores the status and leaves the
    # retirement where the migration put it (Q#4, over the real migrated ledger)
    real_migrated, _removed = _migrator().migrate(json.loads((REPO / LEDGER_REL).read_text(encoding="utf-8")))
    drop_done = accepts("an approved drop over a migrated retirement", lambda: apply_decision(
        real_migrated, "S2-19", sample_element("r1", "drop", reason="the unit is covered elsewhere")))
    if drop_done is not None:
        if before_of(_rows(drop_done)["S2-19"]["decisions"][-1]) != EMPTY_BEFORE:
            failures.append(f"the drop over S2-19 recorded {before_of(_rows(drop_done)['S2-19']['decisions'][-1])}, "
                            f"and it changed no field of the row")
        drop_back = accepts("the owner's revert of that drop", lambda: record_event(
            drop_done, "S2-19", "revert", element=sample_element("r2", "none", kind="revert")))
        if drop_back is not None:
            row, was = _rows(drop_back)["S2-19"], _rows(real_migrated)["S2-19"]
            if row["retired"] != was["retired"] or row["retire_reason"] != was["retire_reason"] or row["status"] != was["status"]:
                failures.append(f"the revert of a drop over S2-19 left retired={row.get('retired')!r} and status={row['status']!r}, "
                                f"not the {was['retired']!r} and {was['status']!r} the migration put on the row")
            clean("that revert of a drop, as a transaction", check_pair(drop_done, drop_back, []))
            drop_cleared = copy.deepcopy(drop_back)
            _rows(drop_cleared)["S2-19"].pop("retired"), _rows(drop_cleared)["S2-19"].pop("retire_reason")
            expect("a revert of that drop clearing the retirement the migration kept on the row",
                   check_pair(drop_done, drop_cleared, []), "ROW_FIELD_UNLICENSED S2-19")
    changed("a status moved to a state the table does not reach", lambda h: bound(
        h, 1, sample_element("r1", "place"), status="retired", disposition="place"), "HISTORY_INCONSISTENT S3-2")
    changed("a pair the table rejects", lambda h: bound(h, 0, sample_element("r1", "place"), disposition="place"),
            "TRANSITION_DISALLOWED S3-1: placed + place: design §12.3 allows no such pair")
    changed("an applied keep without its record", lambda h: bound(h, 0, sample_element("r1", "keep", reason="kept"), disposition="keep"), "EFFECT_MISSING S3-1")
    changed("an applied keep with its record", lambda h: bound(
        h, 0, sample_element("r1", "keep", reason="kept"), disposition="keep", keep={"units": ["u"]}), expect_clean=True)
    changed("a recurrence appended", lambda h: h["entries"][0].update(recurrence=[{"window": "2026-09-01"}]), expect_clean=True)
    changed("evidence appended", lambda h: h["entries"][0].update(evidence=[{"locator": "unavailable", "session": "claude:1"}]), expect_clean=True)
    withrecurrence = sample_ledger(sample_entry("S3-1", recurrence=[{"window": "2026-09-01"}], evidence=[{"claim_id": "c-1", "evidence_id": "e-1"}]))
    changed("a recurrence rewritten", lambda h: h["entries"][0].update(recurrence=[{"window": "2026-09-02"}]), "EVENT_REWRITTEN S3-1 recurrence", over=withrecurrence)
    changed("evidence rewritten", lambda h: h["entries"][0].update(evidence=[{"claim_id": "c-2", "evidence_id": "e-2"}]), "EVENT_REWRITTEN S3-1 evidence", over=withrecurrence)
    withdecision = sample_ledger(sample_entry("S3-1", decisions=[sample_element("r1", "none")]))
    changed("a decision overwritten", lambda h: h["entries"][0]["decisions"][0].update(disposition="correct"),
            "DECISION_REWRITTEN S3-1 decisions[0] (r1)", over=withdecision)
    changed("a decision removed", lambda h: h["entries"][0].update(decisions=[]), "DECISION_REWRITTEN S3-1", "removed", over=withdecision)
    windowed = sample_ledger(windows=[{"start": None, "end": "2026-09-01", "run_id": "w1", "kind": "periodic", "commit": None, "accounted": True, "fully_read": True}])
    changed("a window record rewritten", lambda h: h["windows"][0].update(accounted=False), "WINDOWS_REWRITTEN", over=windowed)
    expect("a head that does not validate", check_pair(base, dropped), "LEDGER_INVALID")
    expect("schema 2 returning to schema 1", check_pair(base, {"schema": 1, "entries": []}), "LEDGER_SCHEMA_REGRESSED")
    legacy_base = {"schema": 1, "entries": [{"id": "S3-1", "status": "placed", "strength": 3}]}
    legacy_head = {"schema": 1, "entries": [{"id": "S3-1", "status": "placed", "strength": 4}, {"id": "S3-2", "status": "candidate"}]}
    clean("a schema 1 merge changing a row and adding the next id", check_pair(legacy_base, legacy_head))
    expect("a schema 1 equal-count deletion plus insertion", check_pair(legacy_base, {"schema": 1, "entries": [{"id": "S3-2", "status": "p"}]}), "ID_LOST S3-1")

    # new rows (F#1): each is bound to the applied decision that created it, and a ledger without one is refused
    anchor = sample_ledger(sample_entry("G-0"))
    created = accepts("an entry created by its first decision", lambda: create_entry(
        anchor, sample_entry("N-1", kind="misfire"), sample_element("r1", "correct")))
    if created is not None:
        clean("a new row bound to the decision that created it", check_pair(anchor, created, ["N-1"]))
        expect("a new row with no allocation", check_pair(anchor, created), "ALLOCATION_REQUIRED")

    def new_row(label, entry, *needles):
        head = sample_ledger(*anchor["entries"], entry)
        expect(label, check_pair(anchor, head, ["N-1"]), *needles)

    new_row("a new row with no decision", sample_entry("N-1"), "NEW_ROW_WITHOUT_DECISION N-1")
    new_row("a new row created by a legacy element", sample_entry("N-1", decisions=[legacy_element()]), "NEW_ROW_WITHOUT_DECISION N-1")
    new_row("a new row whose first decision is not applied", sample_entry("N-1", decisions=[sample_element("r1", "place", applied=False)]), "NEW_ROW_UNAPPLIED N-1")
    # an application whose delivery failed still created its entry (design §10.6, ADDENDUM §3)
    created_failed = accepts("an entry created by a place whose delivery failed", lambda: create_entry(
        anchor, sample_entry("N-1", kind="gap"), sample_element("r1", "place", delivery="failed")))
    if created_failed is not None:
        if [e["id"] for e in created_failed["entries"]] != ["G-0", "N-1"] or created_failed["entries"][1]["status"] != "placed":
            failures.append(f"delivery: a place whose delivery failed did not create the placed entry: {created_failed['entries'][1:]}")
        clean("that entry bound to the decision that created it", check_pair(anchor, created_failed, ["N-1"]))
    new_row("a new row from a pair the table rejects", sample_entry("N-1", kind="gap", disposition="keep", decisions=[
        sample_element("r1", "keep", reason="kept")]), "TRANSITION_DISALLOWED N-1")
    new_row("a new row for a decision the table gives no entry", sample_entry("N-1", kind="misfire", decisions=[sample_element("r1", "none")]),
            "NEW_ENTRY_FOR_NO_ENTRY N-1")
    new_row("a new row created in a state its decision does not lead to", sample_entry(
        "N-1", "incubating", kind="misfire", disposition="incubate", decisions=[sample_element("r1", "incubate", observation=sample_observation())]),
        "STATUS_UNEXPLAINED N-1")
    new_row("a new row saying another disposition than its decision", sample_entry(
        "N-1", "placed", kind="gap", disposition="none", decisions=[sample_element("r1", "place")]), "DISPOSITION_UNBOUND N-1")
    new_row("a new row that gained its decision without its keep record", sample_entry(
        "N-1", "placed", kind="misfire", disposition="keep", decisions=[sample_element("r1", "keep", reason="kept")]), "EFFECT_MISSING N-1")
    # a row the run allocated is no way in for an element of the migration either (H#1): the clean
    # transaction first, then the same row with a complete legacy application behind its first decision
    allocated = sample_entry("N-1", "placed", kind="gap", disposition="place", decisions=[sample_element("r1", "place")])
    clean("a new row bound to its first decision", check_pair(anchor, sample_ledger(*anchor["entries"], allocated), ["N-1"]))
    new_row("a new row carrying a legacy application behind its first decision", {
        **allocated, "decisions": [*allocated["decisions"], legacy_element("placed", kind="legacy_application", legacy_text="placed 2026-07-19")]},
        "LEGACY_ELEMENT_APPENDED N-1 decisions[1]")
    # A row the transaction allocated carries the one decision that created it (K#3). A second
    # decision would have to be judged from the state the first left, and this side has no base for
    # that row at all, so the whole class is refused by name rather than half-checked: the tail that
    # looks valid, the one missing the keep record its cell requires, and the one whose entry ends on
    # another disposition than its latest decision are all the same refusal.
    for label, tail, fields in (
            ("a keep with the record its cell requires", sample_element("r2", "keep", reason="still works"), {"keep": {"units": ["u"]}, "disposition": "keep"}),
            ("a keep without that record", sample_element("r2", "keep", reason="still works"), {"disposition": "keep"}),
            ("a keep the entry does not say it holds", sample_element("r2", "keep", reason="still works"), {"keep": {"units": ["u"]}})):
        new_row(f"a new row whose second decision is {label}", {
            **allocated, **fields, "decisions": [*allocated["decisions"], tail]}, "NEW_ROW_MULTIPLE_DECISIONS N-1")

    # events (F#6): design §12.3's five rows, each with the entry it accepts and the ones it refuses
    table = transitions()
    clean("the event rows against the design's", event_problems(table))
    for label, mutate, needle in (
            ("an event row reworded", lambda t: t["events"][4].update(to="unchanged"), "row 4 is"),
            ("an event row dropped", lambda t: t["events"].pop(), "4 rows, the design has 5"),
            ("an event row renamed", lambda t: t["events"][0].update(id="waiting"), "the handlers")):
        changed_events = copy.deepcopy(table)
        mutate(changed_events)
        expect(label, event_problems(changed_events), needle)
    inc = sample_ledger(sample_entry("S3-2", "incubating"), sample_entry("S3-1"))
    waiting = sample_element("r1", "none", applied=False, reason="awaiting R: the core item needs a second window")
    held = accepts("awaiting R on an incubating entry", lambda: record_event(inc, "S3-2", "awaiting_R", element=waiting))
    if held is not None:
        event_case("awaiting_R", "accept")
        if held["entries"][0]["status"] != "incubating" or held["entries"][0]["decisions"] != [waiting]:
            failures.append("awaiting R: the status moved or the reason was not recorded")
        clean("awaiting R recorded", check_pair(inc, held, []))
    for label, call, needles in (
            ("awaiting R on a placed entry", lambda: record_event(inc, "S3-1", "awaiting_R", element=waiting), ("EVENT_NOT_APPLICABLE S3-1",)),
            ("awaiting R recorded as an applied decision", lambda: record_event(inc, "S3-2", "awaiting_R", element=sample_element("r1", "none", reason="x")), ("EVENT_MALFORMED S3-2 awaiting_R",)),
            ("awaiting R with no reason", lambda: record_event(inc, "S3-2", "awaiting_R", element=sample_element("r1", "none", applied=False)), ("EVENT_MALFORMED S3-2 awaiting_R",))):
        refuses(label, call, *needles)
        event_case("awaiting_R", "refuse")
    changed("awaiting R moving the status", lambda h: bound(h, 0, waiting, status="placed"), "STATUS_UNEXPLAINED S3-2", over=inc)

    reference = {"claim_id": "c-1", "evidence_id": "e-1"}
    recurred = accepts("recurrence on an incubating entry", lambda: record_event(
        inc, "S3-2", "recurrence", evidence=[reference], lineages=2, record={"window": "2026-11-01"}))
    if recurred is not None:
        event_case("recurrence", "accept")
        entry = recurred["entries"][0]
        if (entry["status"], entry["evidence"], entry["independent_lineages"], entry["decisions"]) != ("incubating", [reference], 2, []):
            failures.append(f"recurrence: expected the evidence and lineages appended, status and decisions unchanged, got {entry}")
        clean("a recurrence licensed with no decision", check_pair(inc, recurred, []))
        refuses("evidence the entry already holds", lambda: record_event(recurred, "S3-2", "recurrence", evidence=[reference]), "EVENT_MALFORMED S3-2 recurrence")
    for label, call, needles in (
            ("a recurrence with no evidence", lambda: record_event(inc, "S3-2", "recurrence", evidence=[]), ("EVENT_MALFORMED S3-2 recurrence",)),
            ("a recurrence with an incomplete reference", lambda: record_event(inc, "S3-2", "recurrence", evidence=[{"claim_id": "c-1"}]), ("LEDGER_INVALID after recurrence",)),
            ("an event nobody defined", lambda: record_event(inc, "S3-2", "resurrection", evidence=[reference]), ("EVENT_UNKNOWN",)),
            ("an event for no entry", lambda: record_event(inc, "S9-9", "recurrence", evidence=[reference]), ("ENTRY_UNKNOWN S9-9",))):
        refuses(label, call, *needles)
        event_case("recurrence", "refuse")

    candidate = sample_element("r2", "drop", applied=False, reason="the contradicting session shows the rule is wrong")
    contradicted = accepts("a contradiction of an incubating entry", lambda: record_event(inc, "S3-2", "contradiction", element=candidate))
    if contradicted is not None:
        event_case("contradiction", "accept")
        if contradicted["entries"][0]["status"] != "incubating":
            failures.append("contradiction: the status moved before the candidate's disposition was applied")
        clean("a contradiction recorded", check_pair(inc, contradicted, []))
        later = accepts("the candidate applied by a later run", lambda: apply_decision(
            contradicted, "S3-2", sample_element("r3", "drop", reason="the contradicting session shows the rule is wrong")))
        if later is not None and later["entries"][0]["status"] != "retired":
            failures.append("contradiction: the candidate's disposition, applied, did not retire the entry")
    for label, call, needles in (
            ("a contradiction recorded as an applied decision", lambda: record_event(inc, "S3-2", "contradiction", element=sample_element("r2", "drop", reason="x")), ("EVENT_MALFORMED S3-2 contradiction",)),
            ("a contradiction whose candidate is a place", lambda: record_event(inc, "S3-2", "contradiction", element=sample_element("r2", "place", applied=False)), ("EVENT_MALFORMED S3-2 contradiction",))):
        refuses(label, call, *needles)
        event_case("contradiction", "refuse")
    changed("a contradiction moving the status", lambda h: bound(h, 0, candidate, status="retired"), "STATUS_UNEXPLAINED S3-2", over=inc)

    # design §10.6: an application whose delivery check failed or did not run is applied, not lost. Its
    # effects stand, `applied.delivery` records the outcome, and the owner may revert it (ADDENDUM §3).
    verified = accepts("a place with its delivery verified", lambda: apply_decision(inc, "S3-2", sample_element("r1", "place", delivery="verified")))
    if verified is not None and verified["entries"][0]["status"] != "placed":
        failures.append("delivery: a verified place did not place the entry, so the unverified cases prove nothing")
    # the event records what the check found on the decision already applied: no transition is
    # replayed, no second decision of that run is appended, and the entry stands as the application
    # left it (F#1). Each case starts from a real application made by production code.
    # Each entry records the status it was migrated at, so the revert of its one application has an answer.
    marked = sample_ledger(sample_entry("S3-2", "incubating", decisions=[migration_element("incubating")]),
                           sample_entry("S3-1", "placed", decisions=[migration_element("placed")]), sample_entry("G-0"))
    for applied_label, entry_id, element, updates, want_status, want_before in (
            ("a place", "S3-2", sample_element("r1", "place"), None, "placed", "incubating"),
            ("a correct", "S3-2", sample_element("r1", "correct"), {"lesson": "a revised lesson"}, "incubating", "incubating"),
            ("a reduction", "S3-1", sample_element("r1", "reduce", operations=[MERGE]), {"absorbed_by": "G-0"}, "absorbed", "placed")):
        done = accepts(f"{applied_label} applied, its delivery not yet checked", lambda entry_id=entry_id,
                       element=element, updates=updates: apply_decision(marked, entry_id, element, updates))
        if done is None:
            continue
        for state in ("failed", "unverified"):
            late = accepts(f"the delivery of {applied_label} recorded {state}", lambda done=done, entry_id=entry_id, state=state:
                           record_event(done, entry_id, "delivery", run="r1", outcome=state))
            if late is None:
                continue
            event_case("delivery", "accept")
            was, now = _rows(done)[entry_id], _rows(late)[entry_id]
            if now["status"] != want_status or now["status"] != was["status"]:
                failures.append(f"delivery {state}: recording the outcome of {applied_label} moved the status to {now['status']!r}")
            if len(now["decisions"]) != len(was["decisions"]) or now["decisions"][-1]["applied"]["delivery"] != state:
                failures.append(f"delivery {state}: the outcome of {applied_label} was not written into the decision already there: {now['decisions']}")
            if {k: v for k, v in now.items() if k != "decisions"} != {k: v for k, v in was.items() if k != "decisions"}:
                failures.append(f"delivery {state}: recording the outcome of {applied_label} changed the entry besides its decisions")
            if _written_once(now["decisions"][-1]) != _written_once(was["decisions"][-1]):
                failures.append(f"delivery {state}: recording the outcome of {applied_label} rewrote the decision")
            clean(f"the delivery of {applied_label} recorded {state}, as a transaction", check_pair(done, late, []))
            # a revert reads the application and the values it recorded, not the outcome of its
            # delivery check: an application stands whatever its delivery did, so the row it put back
            # is the same one a verified delivery would have put back (ADDENDUM §3, RECORD)
            back = accepts(f"the owner's revert of {applied_label} whose delivery {state}", lambda late=late, entry_id=entry_id: record_event(
                late, entry_id, "revert", element=sample_element("r2", "none", kind="revert")))
            if back is not None:
                row = _rows(back)[entry_id]
                if row["status"] != want_before:
                    failures.append(f"delivery {state}: the owner's revert of {applied_label} left {row['status']!r}, "
                                    f"not the {want_before!r} before it")
                for field, value in (before_of(_rows(late)[entry_id]["decisions"][-1]) or EMPTY_BEFORE)["fields"].items():
                    if row.get(field) != value:
                        failures.append(f"delivery {state}: the owner's revert of {applied_label} left {field} at {row.get(field)!r}, "
                                        f"not the {value!r} the application recorded")
    for label, call, needles in (
            ("a delivery outcome for a run that decided nothing", lambda: record_event(inc, "S3-2", "delivery", run="r9", outcome="failed"),
             ("EVENT_MALFORMED S3-2 delivery", "no decision of run 'r9'")),
            ("a delivery outcome for a decision that was not applied", lambda: record_event(sample_ledger(sample_entry(
                "S3-2", "incubating", decisions=[sample_element("r1", "place", applied=False)])), "S3-2", "delivery", run="r1", outcome="failed"),
             ("EVENT_MALFORMED S3-2 delivery", "records no application"))):
        refuses(label, call, *needles)
        event_case("delivery", "refuse")
    # each guard against the ledger the other guards accept (H#2), so what refuses is the guard named.
    # The outcome: a real applied decision of run r1, recorded failed first and then with a verdict
    # design §12.3's row does not have. The legacy exclusion: a legacy element that carries an
    # application of its own, which only the exclusion stands between and the write.
    outcome_ready = apply_decision(inc, "S3-2", sample_element("r1", "place"))
    accepts("a delivery outcome of failed on that applied decision", lambda: record_event(outcome_ready, "S3-2", "delivery", run="r1", outcome="failed"))
    refuses("a delivery outcome of verified on the same decision", lambda: record_event(outcome_ready, "S3-2", "delivery", run="r1", outcome="verified"),
            "EVENT_MALFORMED S3-2 delivery", "not 'verified'", "design §12.3's row has no other")
    event_case("delivery", "refuse")
    legacy_applied = sample_ledger(sample_entry("S3-2", "placed", decisions=[
        {**legacy_element("placed", kind="legacy_application"), "applied": {"commit": None, "paths": [], "operations": [], "delivery": "unverified"}}]))
    clean("a ledger whose migrated application records its own delivery", validate_ledger(legacy_applied))
    refuses("a delivery outcome for the run of that migrated application", lambda: record_event(
        legacy_applied, "S3-2", "delivery", run="legacy-2026-08-25", outcome="failed"),
        "EVENT_MALFORMED S3-2 delivery", "is an element of the migration")
    event_case("delivery", "refuse")
    changed("a decision rewritten past its delivery outcome", lambda h: h["entries"][0]["decisions"][0].update(approval_id="ap-9"),
            "DECISION_REWRITTEN S3-1 decisions[0]", over=sample_ledger(sample_entry("S3-1", decisions=[sample_element("r1", "none")])))
    # a transaction writes a delivery outcome by the same rules as the event (K#4): the positive case
    # first, then the two the event refuses, each written straight into a recorded decision
    recorded = sample_ledger(sample_entry("S3-1", decisions=[sample_element("r1", "none")]),
                             sample_entry("S3-2", decisions=[{**legacy_element("placed", kind="legacy_application"),
                                                              "applied": {"commit": None, "paths": [], "operations": [], "delivery": "unverified"}}]))
    for state in ("failed", "unverified"):
        changed(f"a transaction recording a delivery of {state}", lambda h, state=state: h["entries"][0]["decisions"][0]["applied"].update(delivery=state),
                expect_clean=True, over=recorded)
    changed("a transaction recording a delivery of verified", lambda h: h["entries"][0]["decisions"][0]["applied"].update(delivery="verified"),
            "DELIVERY_OUTCOME_INVALID S3-1 decisions[0] (r1)", over=recorded)
    changed("a transaction recording a delivery on an element the migration wrote",
            lambda h: h["entries"][1]["decisions"][0]["applied"].update(delivery="failed"),
            "DELIVERY_ON_MIGRATED S3-2 decisions[0]", over=recorded)

    two_back = accepts("a placed entry corrected and then reduced", lambda: apply_decision(apply_decision(
        accepts("an entry created by place", lambda: create_entry(sample_ledger(sample_entry("G-0")), sample_entry("N-1", kind="gap"), sample_element("r1", "place"))),
        "N-1", sample_element("r2", "correct")), "N-1", sample_element("r3", "reduce")))
    revert = sample_element("r4", "none", kind="revert")
    if two_back is not None:
        if two_back["entries"][1]["status"] != "retired":
            failures.append("revert: the setup did not retire the entry")
        undone = accepts("a revert of the latest decision", lambda: record_event(two_back, "N-1", "revert", element=revert))
        if undone is not None:
            event_case("revert", "accept")
            # r3 retired it, r2 changed nothing, r1 placed it: the status before r3 comes from r1, two decisions back
            appended = {k: v for k, v in undone["entries"][1]["decisions"][-1].items() if k != "applied"}
            if undone["entries"][1]["status"] != "placed" or appended != {k: v for k, v in revert.items() if k != "applied"}:
                failures.append(f"revert: expected placed (set by the decision two steps back) with the revert appended, got {undone['entries'][1]['status']}")
            clean("a revert recorded", check_pair(two_back, undone, []))
            again = accepts("a second revert", lambda: record_event(undone, "N-1", "revert", element=sample_element("r5", "none", kind="revert")))
            if again is not None and again["entries"][1]["status"] != "placed":
                failures.append("revert: reverting the correct, which changed nothing, did not leave the status placed")
            refuses("a third revert, of the decision that created the entry", lambda: record_event(again, "N-1", "revert", element=sample_element("r6", "none", kind="revert")),
                    "REVERT_PRIOR_STATUS_AMBIGUOUS N-1")
        changed("a revert that restores a status the history does not give", lambda h: bound(
            h, 1, revert, status="incubating", disposition="none"), "HISTORY_INCONSISTENT N-1", over=two_back)
        changed("a status restored with no revert decision", lambda h: h["entries"][1].update(status="placed"), "HISTORY_INCONSISTENT N-1", over=two_back)
    step = accepts("an entry created by incubate and then placed", lambda: apply_decision(
        accepts("an entry created by incubate", lambda: create_entry(
            sample_ledger(sample_entry("G-0")), sample_entry("N-1", kind="gap"), sample_element("r1", "incubate", observation=sample_observation()))),
        "N-1", sample_element("r2", "place")))
    if step is not None:
        back = accepts("a revert of the place", lambda: record_event(step, "N-1", "revert", element=revert))
        if back is not None and back["entries"][1]["status"] != "incubating":
            failures.append(f"revert: the status before the place was incubating, got {back['entries'][1]['status']}")
    merged = accepts("an entry created by place and then merged", lambda: apply_decision(
        accepts("a placed entry", lambda: create_entry(sample_ledger(sample_entry("G-0")), sample_entry("N-1", kind="gap"), sample_element("r1", "place"))),
        "N-1", sample_element("r2", "reduce", operations=[MERGE]), {"absorbed_by": "G-0"}))
    if merged is not None:
        released = accepts("a revert of a merge", lambda: record_event(merged, "N-1", "revert", element=sample_element("r3", "none", kind="revert")))
        if released is not None and (released["entries"][1]["status"], "absorbed_by" in released["entries"][1]) != ("placed", False):
            failures.append(f"revert of a merge: expected placed with the absorption gone, got {released['entries'][1]['status']}")
    migrated_like = accepts("a migrated entry placed by a run", lambda: apply_decision(
        sample_ledger(sample_entry("M-1", "incubating", decisions=[legacy_element()])), "M-1", sample_element("r1", "place")))
    if migrated_like is not None:
        refuses("a revert where the history leaves the earlier status open", lambda: record_event(
            migrated_like, "M-1", "revert", element=revert), "REVERT_PRIOR_STATUS_AMBIGUOUS M-1", "incubating")
        event_case("revert", "refuse")
    for start in ("incubating", "retired"):  # the element is the one start the history has, so the revert has its answer
        marked = accepts(f"a migrated {start} entry placed by a run", lambda start=start: apply_decision(sample_ledger(sample_entry(
            "M-1", start, decisions=[legacy_element(), migration_element(start)])), "M-1", sample_element("r1", "place")))
        if marked is not None:
            returned = accepts(f"a revert of the first run decision on a migrated {start} entry", lambda marked=marked: record_event(marked, "M-1", "revert", element=revert))
            if returned is not None:
                event_case("revert", "accept")
                if returned["entries"][0]["status"] != start:
                    failures.append(f"revert: the entry was migrated {start} and the revert of its first run decision restored {returned['entries'][0]['status']}")
                clean(f"a revert to the status {start} recorded", check_pair(marked, returned, []))
    for label, call, needles in (
            ("a revert with no application to revert", lambda: record_event(sample_ledger(sample_entry("S3-1")), "S3-1", "revert", element=revert), ("REVERT_NOTHING S3-1",)),
            ("a revert that is not a revert decision", lambda: record_event(inc, "S3-2", "revert", element=sample_element("r4", "none")), ("EVENT_MALFORMED S3-2 revert",))):
        refuses(label, call, *needles)
        event_case("revert", "refuse")
    only_created = accepts("an entry created by place", lambda: create_entry(
        sample_ledger(sample_entry("G-0")), sample_entry("N-1", kind="gap"), sample_element("r1", "place")))
    if only_created is not None:  # no status can start the history, so only creation does: the guard has to speak
        saved_vocabulary, globals()["vocabulary"] = vocabulary, lambda name: [] if name == "status" else saved_vocabulary(name)
        try:
            refuses("a revert of the decision that created the entry, with no status left to restore",
                    lambda: revert_target(only_created["entries"][1], "placed"), "REVERT_PRIOR_STATUS_NONE")
        finally:
            globals()["vocabulary"] = saved_vocabulary
    for event in DESIGN_12_3_EVENTS:
        name = next((r["id"] for r in table["events"] if (r["from"], r["event"], r["to"]) == event), None)
        if name is None or ran["events"].get(name) != {"accept", "refuse"}:
            failures.append(f"events: design §12.3's {event[1]!r} has no accepting and refusing control (ran {ran['events'].get(name)})")

    # decisions applied to entries (F#5): the effects each cell requires, checked on the resulting entry
    def fx(row, key):
        f = fixture_for(row, key)
        entries = [copy.deepcopy(f["entry"])] if ROW_STATUS.get(row) else []
        return f, sample_ledger(*f["others"], *entries)

    def effect_case(token, row, key, *, element=None, updates=None, entry=None, others=None, rows=None):
        """Run the fixture of `row`/`key` with one footprint taken away; the production path must name the effect."""
        f, ledger = fx(row, key)
        if others is not None:
            ledger = sample_ledger(*others, *ledger["entries"][len(f["others"]):])
        element = element if element is not None else f["element"]
        updates = f["updates"] if updates is None else updates
        if ROW_STATUS.get(row) is None:
            refuses(f"{token} missing on {row}/{key}", lambda: create_entry(ledger, {**(entry or f["entry"]), **updates}, element), f"EFFECT_MISSING", token)
        else:
            refuses(f"{token} missing on {row}/{key}", lambda: apply_decision(ledger, f["entry"]["id"], element, updates), "EFFECT_MISSING", token)
        ran["effects"].add(token)

    f, _ = fx("placed", "keep")
    effect_case("keep_record", "placed", "keep", updates={})
    effect_case("keep_record", "placed", "keep", element={k: v for k, v in f["element"].items() if k != "reason"})
    effect_case("keep_record", "no_entry_existing_unit", "keep", updates={})
    effect_case("absorbed_by", "placed", "reduce_merge", updates={})
    effect_case("absorbed_by", "placed", "reduce_merge", updates={"absorbed_by": "G-404"})
    effect_case("allocate_destination_entry", "no_entry_existing_unit", "reduce_merge", others=[sample_entry("G-0", "incubating")])
    f, _ = fx("placed", "incubate")
    effect_case("pending_intervention", "placed", "incubate", element={**f["element"], "expected_observation": None})
    f, _ = fx("placed", "drop")
    effect_case("dropped_intervention", "placed", "drop", element={k: v for k, v in f["element"].items() if k != "reason"})
    effect_case("never_placed", "no_entry_new_learning", "drop", entry={**fx("no_entry_new_learning", "drop")[0]["entry"], "destination": {
        "implementation": "x", "anchor": None, "package_id": None}})
    effect_case("text_revised", "incubating", "correct", updates={})
    f, _ = fx("incubating", "incubate")
    effect_case("expiry_renewed", "incubating", "incubate", element={**f["element"], "expected_observation": sample_observation("2026-06-30")})
    # the effects that a second row carries are held at the row check: the merge decision on the receiver, the revival of the entry
    f, ledger = fx("placed", "reduce_merge")
    absorbed = apply_decision(ledger, "S9-01", f["element"], f["updates"])
    clean("a merge with its receiving decision", check_pair(ledger, absorbed, []))
    stripped = copy.deepcopy(absorbed)
    stripped["entries"][0]["decisions"] = []
    stripped["entries"][0]["disposition"] = "none"
    expect("a merge whose receiver has no merge decision", check_pair(ledger, stripped, []), "EFFECT_MISSING S9-01", "receiver_merge_decision")
    ran["effects"].add("receiver_merge_decision")
    f, ledger = fx("absorbed_retired", "place")
    revived = apply_decision(ledger, "S9-01", f["element"], f["updates"])
    clean("a revival that drops the retirement", check_pair(ledger, revived, []))
    holding = copy.deepcopy(revived)
    holding["entries"][-1]["retired"] = "2026-08-09"
    expect("a revival that keeps the retirement", check_pair(ledger, holding, []), "EFFECT_MISSING S9-01", "revival")
    ran["effects"].add("revival")
    all_effects = {e for cells in table["cells"].values() for cell in cells.values() if cell for e in cell["effects"]}
    if all_effects != ran["effects"]:
        failures.append(f"effects: the table's {sorted(all_effects - ran['effects'])} have no refusing control, and the controls name {sorted(ran['effects'] - all_effects)} the table lacks")
    f, ledger = fx("no_entry_existing_unit", "none")
    if create_entry(ledger, f["entry"], f["element"]) != ledger:
        failures.append("a decision the table gives no entry created one")
    refuses("an entry created by an unapplied decision", lambda: create_entry(ledger, f["entry"], sample_element("r1", "correct", applied=False)), "NEW_ROW_UNAPPLIED")
    f, ledger = fx("no_entry_existing_unit", "correct")
    made = accepts("an entry created by a correct whose delivery failed", lambda: create_entry(
        ledger, f["entry"], sample_element("r1", "correct", delivery="failed")))
    if made is not None and [e["id"] for e in made["entries"]] != [e["id"] for e in ledger["entries"]] + ["S9-01"]:
        failures.append("a decision whose delivery failed did not create the entry its completed operations made")
    refuses("updates to an entry through an unapplied decision", lambda: apply_decision(
        base, "S3-1", sample_element("r1", "correct", applied=False), {"lesson": "edited"}), "UPDATES_WITHOUT_DECISION S3-1")
    refuses("updates outside the fields a decision changes", lambda: apply_decision(
        base, "S3-1", sample_element("r1", "correct"), {"id": "S3-9"}), "UPDATES_UNLICENSED S3-1")

    # history: two decisions, each resolved on its own, and the status stays
    ledger = sample_ledger(sample_entry("S3-1", decisions=[]))
    ledger = apply_decision(ledger, "S3-1", sample_element("r1", "correct", observation=sample_observation("2026-12-31")))
    ledger = apply_decision(ledger, "S3-1", sample_element("r2", "incubate", observation=sample_observation("2027-02-28")))
    ledger = append_resolution(ledger, "S3-1", "r1", sample_resolution("r1", resolution="observed"))
    ledger = append_resolution(ledger, "S3-1", "r2", sample_resolution("r2", window="2027-03-01", resolution="pending"))
    decisions = ledger["entries"][0]["decisions"]
    if [len(d["expected_observation"]["resolutions"]) for d in decisions] != [1, 1] or ledger["entries"][0]["status"] != "placed":
        failures.append(f"history: two decisions with one resolution each, status unchanged, expected; got {decisions}")
    if [d["expected_observation"]["resolutions"][0]["resolution"] for d in decisions] != ["observed", "pending"]:
        failures.append("history: each decision keeps its own resolution")
    clean("the history ledger", validate_ledger(ledger))
    wrong = copy.deepcopy(ledger)
    wrong["entries"][0]["decisions"][1]["expected_observation"]["resolutions"].append(sample_resolution("r1", window="2027-04-01"))
    expect("a resolution appended to the wrong decision", validate_ledger(wrong), "RESOLUTION_MISPLACED S3-1 decisions[1]")
    refuses("a resolution for a run that decided nothing", lambda: append_resolution(ledger, "S3-1", "r9", sample_resolution("r9")), "RESOLUTION_TARGET_MISSING")
    refuses("a resolution outside the vocabulary", lambda: append_resolution(ledger, "S3-1", "r1", {**sample_resolution("r1"), "resolution": "later"}), "LEDGER_INVALID")
    pre = sample_ledger(sample_entry("S3-1", decisions=[sample_element("r1", "correct", observation=sample_observation())]))
    clean("a resolution appended to an existing decision", check_pair(pre, append_resolution(pre, "S3-1", "r1", sample_resolution("r1")), []))
    refuses("a decision for no entry", lambda: apply_decision(pre, "S9-9", sample_element("r2", "none")), "ENTRY_UNKNOWN S9-9")
    refuses("a rejected pair applied", lambda: apply_decision(pre, "S3-1", sample_element("r2", "place")), "TRANSITION_DISALLOWED")
    refuses("a keep applied without its record", lambda: apply_decision(pre, "S3-1", sample_element("r2", "keep", reason="kept")), "EFFECT_MISSING")
    kept = apply_decision(pre, "S3-1", sample_element("r2", "keep", reason="kept"), {"keep": {"units": ["u"]}})
    if kept["entries"][0]["keep"] != {"units": ["u"]} or kept["entries"][0]["status"] != "placed" or kept["entries"][0]["disposition"] != "keep":
        failures.append("a keep with its record did not keep the entry placed and say so")
    unapplied = apply_decision(sample_ledger(sample_entry("S3-1", "incubating")), "S3-1", sample_element("r2", "place", applied=False))
    if unapplied["entries"][0]["status"] != "incubating" or unapplied["entries"][0]["disposition"] != "none":
        failures.append("an unapplied place moved the status or the disposition")

    # transitions: the data renders to the design's wording, every allowed cell has a frozen fixture that runs
    if list(table["cells"]) != list(DESIGN_12_3):
        failures.append(f"transitions: rows {list(table['cells'])} differ from the design's {list(DESIGN_12_3)}")
    for row, wording in DESIGN_12_3.items():
        for key, text in zip(table["dispositions"], wording):
            rendered = render_cell(table["cells"][row][key])
            if not rendered.startswith("—") if text.startswith("—") else rendered != text:
                failures.append(f"transitions: {row}/{key} renders {rendered!r}, the design says {text!r}")
    if len(table["dispositions"]) != len(next(iter(DESIGN_12_3.values()))):
        failures.append("transitions: the table's columns are not the design's nine")
    mutated = copy.deepcopy(table)
    mutated["cells"]["placed"]["keep"]["effects"] = []
    _TABLES["t"] = mutated
    try:
        if render_cell(mutated["cells"]["placed"]["keep"]) == DESIGN_12_3["placed"][3]:
            failures.append("transitions: a cell losing its effect still rendered the design's wording")
    finally:
        _TABLES["t"] = table
    refuses("an effect with no wording", lambda: render_cell({"new_entry": False, "status": "placed", "effects": ["invented"]}), "TRANSITION_EFFECT_UNKNOWN")
    refuses("an effect no check exists for", lambda: effect_problems(
        {"effects": ["invented"]}, sample_element("r1", "none"), None, sample_entry("S3-1"), {}), "TRANSITION_EFFECT_UNKNOWN")
    if len(cell_ids()) != 29:
        failures.append(f"transitions: {len(cell_ids())} allowed cells, the design's table has 29")
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["fixtures"]
    executed = set()
    for fixture in fixtures:
        failures += [f"transitions: {line}" for line in fixture_problems(fixture)]
        executed.add(fixture["id"])  # recorded after the case ran through the real code path
    frozen = {f["id"] for f in fixtures}
    clean("table cells, frozen fixtures and executed cases", coverage_problems(cell_ids(), frozen, executed))
    scratch_cells = copy.deepcopy(table)
    scratch_cells["cells"]["incubating"]["re-deliver"] = scratch_cells["cells"]["incubating"]["correct"]
    _TABLES["t"] = scratch_cells
    try:
        expect("a cell added to the table, the fixtures unchanged", coverage_problems(cell_ids(), frozen, executed), "CELL_UNFIXTURED incubating/re-deliver")
    finally:
        _TABLES["t"] = table
    expect("a frozen fixture deleted", coverage_problems(cell_ids(), frozen - {"placed/keep"}, executed), "CELL_UNFIXTURED placed/keep")
    expect("a cell removed with its fixture left", coverage_problems(set(cell_ids()) - {"placed/keep"}, frozen, executed), "FIXTURE_ORPHAN placed/keep")
    expect("an executed case removed from the run's record", coverage_problems(cell_ids(), frozen, executed - {"placed/keep"}), "CASE_NOT_EXECUTED placed/keep")
    expect("a case executed with no fixture", coverage_problems(cell_ids(), frozen, executed | {"placed/place"}), "CASE_UNFROZEN placed/place")
    by_id = {f["id"]: f for f in fixtures}
    for cid, mutate, needle in (("no_entry_new_learning/place", lambda t: t["cells"]["no_entry_new_learning"]["place"].update(status="incubating"), "the table now says"),
                                ("placed/keep", lambda t: t["cells"]["placed"]["keep"].update(effects=[]), "effects"),
                                ("incubating/place", lambda t: t["cells"]["incubating"]["place"].update(status="retired"), "the table now says")):
        changed_table = copy.deepcopy(table)
        mutate(changed_table)
        _TABLES["t"] = changed_table
        try:
            expect(f"fixture {cid} against a changed table", fixture_problems(by_id[cid]), needle)
        finally:
            _TABLES["t"] = table
    saved_status_after, globals()["status_after"] = status_after, lambda status, cell: "retired"
    try:  # the fixtures run the production code: when it moves the status somewhere else than the table does, they say so
        expect("a production status_after that disagrees with the table", fixture_problems(by_id["incubating/place"]), "the status moved")
    finally:
        globals()["status_after"] = saved_status_after
    saved_takes_effect, globals()["takes_effect"] = takes_effect, lambda element: False
    try:
        expect("a production creation that refuses the decision", fixture_problems(by_id["no_entry_new_learning/place"]),
               "no_entry_new_learning/place:", "NEW_ROW_UNAPPLIED")
    finally:
        globals()["takes_effect"] = saved_takes_effect
    saved_create, globals()["create_entry"] = create_entry, lambda ledger, entry, element: copy.deepcopy(ledger)
    try:
        expect("a production creation that creates nothing", fixture_problems(by_id["no_entry_new_learning/place"]), "0 entries created")
    finally:
        globals()["create_entry"] = saved_create
    saved_entry_row, globals()["entry_row"] = entry_row, lambda entry: "no_entry_existing_unit"
    try:
        expect("a production creation that reads the wrong row", fixture_problems(by_id["no_entry_new_learning/place"]), "no_entry_new_learning/place:", "TRANSITION_DISALLOWED")
    finally:
        globals()["entry_row"] = saved_entry_row
    for row, key in (("no_entry_new_learning", "keep"), ("placed", "place"), ("absorbed_retired", "reduce_merge")):
        refuses(f"{row}/{key}", lambda row=row, key=key: transition(row, key), "TRANSITION_DISALLOWED")
    refuses("an unknown row", lambda: transition("nowhere", "place"), "TRANSITION_DISALLOWED nowhere + place")
    with tempfile.TemporaryDirectory() as td:
        target = pathlib.Path(td) / "fixtures.json"
        if generate_fixtures(target) != 29:
            failures.append("transitions: the generator did not write 29 fixtures")
        if json.loads(target.read_text(encoding="utf-8"))["fixtures"] != fixtures:
            failures.append("transitions: the generator's fixtures differ from the frozen ones")
        refuses("a second generation", lambda: generate_fixtures(target), "FIXTURES_FROZEN")

    # atomic writes: a stale base, a held lock, a crash before the rename, an escape, an invalid ledger
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        target, lock_root = root / "ledger" / "ledger.json", root / "lock"
        target.parent.mkdir()
        write_atomic(target, base, EMPTY_SHA, lock_root)
        if json.loads(target.read_text(encoding="utf-8")) != base or target.read_text(encoding="utf-8") != render(base):
            failures.append("write: a first write did not leave the ledger's bytes")
        first = sha256_bytes(target.read_bytes())
        newer = apply_decision(base, "S3-2", sample_element("r1", "place"))
        write_atomic(target, newer, first, lock_root)
        refuses("a stale base", lambda: write_atomic(target, base, first, lock_root), "BASE_STALE")
        if json.loads(target.read_text(encoding="utf-8")) != newer:
            failures.append("write: a refused stale writer changed the file")
        current = sha256_bytes(target.read_bytes())
        # the bytes on disk are the base of a transaction, so what this writer would replace them
        # with is held against them, and a writer that erases or reorders a decision is refused
        # before anything is written (U#0). Every write below is a transaction over the one before it.
        # The plants run against a file of their own, so a write that slipped through would be read
        # here rather than disturbing the chain the crash controls depend on.
        later = apply_decision(newer, "S3-2", sample_element("r2", "correct"))
        probe = root / "ledger" / "probe.json"
        write_atomic(probe, newer, EMPTY_SHA, lock_root)
        reordered = {**later, "entries": [{**row, "decisions": list(reversed(row["decisions"]))} if row["id"] == "S3-2" else row
                                          for row in later["entries"]]}
        for label, proposed, successor, needle in (
                ("a decision removed", base, later, "DECISION_REWRITTEN S3-2: 1 decision(s) removed"),
                ("the decisions reordered", reordered, None, "DECISION_REWRITTEN S3-2 decisions[0]")):
            held = sha256_bytes(probe.read_bytes())
            refuses(f"a writer with {label}", lambda proposed=proposed, held=held: write_atomic(probe, proposed, held, lock_root),
                    "TRANSACTION_INVALID, nothing written", needle)
            if sha256_bytes(probe.read_bytes()) != held:
                failures.append(f"write: a writer with {label} was refused and the file changed anyway")
            if successor is not None:  # the next plant needs a row with two decisions to reorder
                write_atomic(probe, successor, sha256_bytes(probe.read_bytes()), lock_root)
        with stagelock.hold(lock_root, "ledger"):
            try:
                write_atomic(target, later, current, lock_root)
                failures.append("write: a second writer took a held lock")
            except stagelock.Locked as exc:
                expect("a held lock", [str(exc)], "STAGE_LOCKED ledger")
        before = target.read_bytes()

        class Crash(Exception):
            pass

        def crash():
            raise Crash("injected between the temporary write and the rename")
        try:
            write_atomic(target, later, current, lock_root, before_rename=crash)
            failures.append("write: the injected crash did not surface")
        except Crash:
            pass
        if target.read_bytes() != before or sorted(p.name for p in target.parent.iterdir()) != ["ledger.json", "probe.json"]:
            failures.append("write: a crash before the rename changed the file or left a temporary behind")
        hard = subprocess.run([sys.executable, "-c", HARD_KILL, str(HERE), str(target), current,
                               str(lock_root)], capture_output=True, text=True)
        if hard.returncode != 9 or target.read_bytes() != before:
            failures.append(f"write: a process killed before the rename left the file changed (exit {hard.returncode})")
        # the same successor the killed child proposed, written now: it lands, so what the child
        # proposed was a transaction this writer accepts and the unchanged bytes above say the
        # rename had not happened rather than that nothing was proposed (X#1)
        write_atomic(target, later, current, lock_root)
        if target.read_text(encoding="utf-8") != render(later):
            failures.append("write: a write after a killed writer did not land")
        landed = sha256_bytes(target.read_bytes())
        # a base is read as a ledger before it is read as a transaction's base (X#0): a file of its
        # own takes an append first, then each shape that is not a ledger is refused over it and the
        # bytes stay. A valid empty-looking ledger is the one worth planting — nothing in a row or
        # window comparison would have reported it.
        scratch = root / "ledger" / "scratch.json"
        write_atomic(scratch, newer, EMPTY_SHA, lock_root)
        write_atomic(scratch, later, sha256_bytes(scratch.read_bytes()), lock_root)
        if scratch.read_text(encoding="utf-8") != render(later):
            failures.append("write: an append over a sound base of its own did not land")
        for label, text in (  # the shapes a reader reports on come first, the one it raises on last
                ("bytes that are not a ledger", "not a ledger at all"),
                ("a ledger without the framework design §12.1 requires", json.dumps({"schema": 2, "windows": [], "entries": []})),
                ("a base holding two rows of one id", render({**base, "entries": [base["entries"][0], copy.deepcopy(base["entries"][0])]})),
                ("JSON that is not an object", "[]")):
            scratch.write_text(text, encoding="utf-8")
            refuses(f"a writer over {label}", lambda text=text: write_atomic(
                scratch, later, sha256_bytes(text.encode("utf-8")), lock_root), "BASE_UNREADABLE", "nothing written")
            if scratch.read_text(encoding="utf-8") != text:
                failures.append(f"write: a writer over {label} was refused and the file changed anyway")
        elsewhere = root / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "ledger.json").write_text("{}", encoding="utf-8")
        (root / "linked").mkdir()
        (root / "linked" / "ledger.json").symlink_to(elsewhere / "ledger.json")
        try:
            write_atomic(root / "linked" / "ledger.json", base, sha256_bytes(b"{}"), lock_root)
            failures.append("write: a ledger linked to a file outside its directory was replaced")
        except stagelock.Escaped as exc:
            expect("a linked ledger", [str(exc)], "RUN_PATH_ESCAPE")
        if (elsewhere / "ledger.json").read_text(encoding="utf-8") != "{}":
            failures.append("write: a linked ledger's target was changed")
        refuses("an invalid ledger", lambda: write_atomic(target, dropped, landed, lock_root), "LEDGER_INVALID, nothing written")

    # the check command, end to end over scratch repositories: index against HEAD, then exit codes
    with scratch_git() as (repo, git):
        path = repo / LEDGER_REL
        path.parent.mkdir(parents=True)
        path.write_text(render(base), encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "base")
        code, lines = check_command(repo, LEDGER_REL, "HEAD", False, None)
        if code != 0 or "OK" not in lines[0]:
            failures.append(f"check: an unchanged ledger was not accepted: {code} {lines}")
        swapped = copy.deepcopy(base)
        swapped["entries"][2] = sample_entry("S3-4", "incubating")
        path.write_text(render(swapped), encoding="utf-8")
        git("add", LEDGER_REL)
        code, lines = check_command(repo, LEDGER_REL, "HEAD", False, None)
        if code != 1 or "ID_LOST S3-3" not in "\n".join(lines) or "ALLOCATION_REQUIRED" not in "\n".join(lines):
            failures.append(f"check: a staged equal-count deletion plus insertion was not refused naming the lost id and the missing allocation: {code} {lines}")
        code, lines = check_command(repo, LEDGER_REL, "HEAD", False, ["S3-4"])
        if code != 1 or "ID_LOST S3-3" not in "\n".join(lines) or "NEW_ROW_WITHOUT_DECISION S3-4" not in "\n".join(lines):
            failures.append(f"check: under its allocation, the swap was not refused naming the lost id and the row with no decision: {code} {lines}")
        path.write_text(render(base), encoding="utf-8")  # restored on disk; the index keeps the swap
        code, lines = check_command(repo, LEDGER_REL, "HEAD", False, None)
        if code != 1:
            failures.append(f"check: the index was not judged when the disk was restored: {code} {lines}")
        code, lines = check_command(repo, LEDGER_REL, "HEAD", True, None)
        if code != 0:
            failures.append(f"check: --worktree did not read the disk: {code} {lines}")
        code, lines = check_command(repo, LEDGER_REL, "no-such-revision", False, None)
        if code != 2 or "CANNOT JUDGE" not in lines[0]:
            failures.append(f"check: an unresolvable base did not exit 2 naming it: {code} {lines}")
        git("rm", "-q", "-f", "--cached", LEDGER_REL)
        code, lines = check_command(repo, LEDGER_REL, "HEAD", False, None)
        if code != 1 or "LEDGER_ABSENT" not in lines[0]:
            failures.append(f"check: a ledger removed from the index was not refused: {code} {lines}")
        git("add", LEDGER_REL)
        path.unlink()
        path.mkdir()  # a directory where the file should be: the disk cannot answer
        code, lines = check_command(repo, LEDGER_REL, "HEAD", True, None)
        if code != 2 or "LEDGER_FILE_UNREADABLE" not in lines[0]:
            failures.append(f"check: a side the disk could not read did not exit 2 naming it: {code} {lines}")
        path.rmdir()
        path.write_text("{ not json", encoding="utf-8")
        code, lines = check_command(repo, LEDGER_REL, "HEAD", True, None)
        if code != 1 or "LEDGER_UNREADABLE" not in lines[0]:
            failures.append(f"check: an unparsable ledger was not refused: {code} {lines}")
    with scratch_git() as (repo, git):
        (repo / "README").write_text("x", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "no ledger")
        (repo / LEDGER_REL).parent.mkdir(parents=True)
        (repo / LEDGER_REL).write_text(render(base), encoding="utf-8")
        git("add", "-A")
        code, lines = check_command(repo, LEDGER_REL, "HEAD", False, None)
        if code != 0 or "validated alone" not in lines[0]:
            failures.append(f"check: a ledger new in the index was not validated alone: {code} {lines}")

    # the command line, end to end (F#3): a run that allocated no id says so, and that is not the
    # same argument as no run at all. A correction writes the ledger and adds no row.
    for label, argument, want in (("an omitted flag", None, None), ("the flag passed empty", "", []),
                                  ("one id", "N-1", ["N-1"]), ("two ids and a space", "N-1, N-2", ["N-1", "N-2"])):
        if allocation(argument) != want:
            failures.append(f"allocation: {label} read as {allocation(argument)!r}, expected {want!r}")
    with scratch_git() as (repo, git):
        path = repo / LEDGER_REL
        path.parent.mkdir(parents=True)
        path.write_text(render(base), encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "base")
        path.write_text(render(apply_decision(base, "S3-1", sample_element("r1", "correct"), {"lesson": "a corrected lesson"})), encoding="utf-8")
        git("add", LEDGER_REL)
        kept_repo, globals()["REPO"] = REPO, repo
        try:
            for label, argv, want_code, needle in (
                    ("a correction under the empty allocation it froze", ["--check", "--allocated", ""], 0, "OK"),
                    ("the same correction with no allocation at all", ["--check"], 1, "ALLOCATION_REQUIRED"),
                    ("an allocated id no row of the result carries", ["--check", "--allocated", "N-9"], 1, "ID_ALLOCATED_MISSING N-9")):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = main(argv)
                said = (out.getvalue() + err.getvalue()).strip()
                if code != want_code or needle not in said:
                    failures.append(f"check CLI, {label}: expected exit {want_code} naming {needle}, got {code}: {said[:160]}")
        finally:
            globals()["REPO"] = kept_repo

    for failure in failures:
        print(f"ledger --self-test [FAIL] {failure}")
    if failures:
        return 1
    print("ledger --self-test: OK (contract fidelity against design §12.1/§12.2/§12.4/§7.2/§7.3 and the record contracting what "
          "schema 2 carries beyond them, validation with the two disposition vocabularies, the two element shapes and the evidence "
          "forms, the id-set check against the frozen allocation a schema 2 transaction carries whether or not it adds a row, changed "
          "rows and new rows bound to the decision whose disposition licenses them, an application standing with its delivery failed or "
          "unverified and its delivery outcome written into the decision already there, the five events with accepting and refusing controls, "
          "a migrated element refused when a run appends it on an existing or a new row, one decision per row a transaction allocates, a "
          "revert that restores the status design §12.3 derives and the values the application it undoes recorded — one round trip per "
          "disposition that changes a row, a keep reaffirmed, a merge with its receiver, and a named refusal where an application recorded "
          "nothing, where its record disagrees with the row change, where the receiver has moved on, and where an application and its "
          "revert are batched into one close — the revert to the migrated status, "
          "every effect of the table refused "
          "when missing, 29 transitions rendered to the design's wording and run from frozen fixtures, atomic writes with an "
          "injected crash, --check over scratch repositories)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--ledger", default=LEDGER_REL, help="repo-relative path of the ledger")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--worktree", action="store_true", help="read the file on disk instead of the index")
    parser.add_argument("--allocated", help="comma-separated ids the run allocated; pass it empty for a "
                                            "transaction that allocated none, omit it only when there is no run")
    parser.add_argument("--generate-transition-fixtures", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.generate_transition_fixtures:
        try:
            print(f"wrote {generate_fixtures()} fixtures to {FIXTURES_PATH}")
        except LedgerError as exc:
            sys.exit(str(exc))
        return 0
    if args.check:
        code, lines = check_command(REPO, args.ledger, args.base, args.worktree, allocation(args.allocated))
        print("\n".join(lines), file=sys.stdout if code == 0 else sys.stderr)
        return code
    parser.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
