#!/usr/bin/env python3
"""The delivery evidence of design §6.3 (WP-10): for one unit, one session and the instant of the decision an event
concerns, the delivery state - `delivered`, `exposed_not_read`, `selected_unavailable`, `not_delivered` or `unknown` -
with the evidence level reached and every reason, read from `tables/delivery_evidence.json`.

Selection is not delivery. A unit is `delivered` only at the level its surface needs, before the decision:

- a rule on the always surface when the pin's selection holds its item, the compiled instruction text holds its
  lines, its route is not unavailable, and the injection was recorded at or before the decision;
- a guide when its **unit read** holds: every requirement of the unit's operative context (the inventory's
  `operative_context`: the unit, its frontmatter, the enclosing conditions, every operative unit it names, in any
  guide) is covered by bytes a read actually returned before the decision - line-number prefixes removed, a
  requested offset never enough - and each covering read is of the requirement's own version. A fragment that two
  versions of its source share binds to the version the pin or release names (`bound_versions`), and is `unknown`
  otherwise;
- a native layer when the session's most recent recorded injection at or before the decision loaded it.

`exposed_not_read` is a guide whose pointer was exposed (the router path, or a requested item's own path, in an
injection recorded before the decision) or which the session partly read, while its unit read does not hold. A
tool call before the decision that names the guide but whose returned bytes could not be read as a read makes the
state `unknown` (`read_unparsed`), never `exposed_not_read`: a failure is not claimed from evidence this code did
not read. `selected_unavailable` is a selected item whose route the compiled output lists as unavailable.
`not_delivered` - the release holds the item and the selection lacks it - is an absence, held to the absence policy
of `tables/unit_outcome.json` (`derive.absence`, D-20261111-eaa2a8): at an incomplete release it is `unknown`, and
the reason names the layers whose completeness is unknown.

A session with no pin answers from the evidence that exists: a unit read delivers, a partial read exposes, and
nothing else is claimed; its selection stays `unknown`. A row the selection history answers (D-20261110-9c60bc) is
the licensed level `library_selected`: the owner's library held it, delivery `unknown`. A Codex pin that names no
rollout stays `unknown` with the inventory's reason (F-22), and a joined Codex pin is a pin like any other. A surface
whose evidence no producer reads yet (`producer: absent`) answers `unknown` naming that, and an executable that
produces consumed artifacts - the installer - is read from its installation binding (`installer_exposure`), golden
until WP-15's receipt is installed and read live.

  delivery_evidence.py --self-test
  delivery_evidence.py --generate-fixtures [PATH]
"""
import copy
import json
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import derive  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
TABLE_PATH = HERE / "tables" / "delivery_evidence.json"
FIXTURES_PATH = HERE / "tables" / "delivery_evidence_fixtures.json"
SECTIONS = ("surfaces", "licensed_levels")
PREFIX = re.compile(r"^\s*\d+(?:\t|→)")
ROUTER = "router/relevant.md"

_TABLES = {}


def table():
    """The §6.3 table, read once per process; a control may hold a scratch copy in `_TABLES["t"]`."""
    if "t" not in _TABLES:
        _TABLES["t"] = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    return _TABLES["t"]


def row_ids(held=None):
    held = held or table()
    return [f"{section}/{row['id']}" for section in SECTIONS for row in held[section]]


# ---- returned bytes and versions ----------------------------------------------------------------

def returned_lines(text):
    """A read's returned text as its non-blank lines, with the line-number prefix a reading tool adds removed - but only
    when every non-blank line carries one, so a digit that begins a line of the file is never taken for a prefix."""
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if lines and all(PREFIX.match(line) for line in lines):
        lines = [PREFIX.sub("", line, count=1) for line in lines]
    return [line.rstrip() for line in lines if line.strip()]


def text_lines(text):
    return [line.rstrip() for line in (text or "").splitlines() if line.strip()]


def contains(haystack, needle):
    """Whether `needle`'s lines occur as one contiguous run of `haystack`'s."""
    if not needle:
        return False
    first = needle[0]
    return any(haystack[i:i + len(needle)] == needle for i, line in enumerate(haystack) if line == first)


def versions_of(units):
    """`{path: {version_sha256: lines}}`: each carrier version's text as its units' lines in order."""
    out = {}
    for unit in sorted(units, key=lambda u: (u["path"], u["version_sha256"], u.get("start", 0), u.get("n", 0))):
        out.setdefault(unit["path"], {}).setdefault(unit["version_sha256"], []).extend(text_lines(unit["text"]))
    return out


def delivered_suffix(path):
    """The part of a catalog path a deployed copy keeps: `claude/guides/x.md` is read as `.../guides/x.md`."""
    head, _, rest = path.partition("/")
    return rest if head in ("claude", "codex") and rest else path


def of_carrier(read, unit, session):
    """Whether a read is of the unit's carrier: the path the compiled output emitted for its item, or a path ending in
    the part of the carrier's path a deployed copy keeps. The returned bytes then decide the version."""
    emitted = (session.get("emitted") or {}).get(read["path"])
    if emitted is not None:
        return emitted == unit.get("item_ref") and read["path"].endswith("/" + delivered_suffix(unit["path"]))
    return read["path"] == unit["path"] or read["path"].endswith("/" + delivered_suffix(unit["path"]))


def requirement(req_id, units, reads, session, versions):
    """`(status, reason)` of one requirement of a unit's operative context: `met`, `unmet` or `unknown`."""
    if req_id.startswith("k-"):
        return "unknown", "context_unresolved"
    req = units.get(req_id)
    if req is None:
        return "unknown", "requirement_absent"
    want = text_lines(req["text"])
    held = versions.get(req["path"], {})
    known = {line for lines in held.values() for line in lines}
    seen = []
    for read in reads:
        if not of_carrier(read, req, session):
            continue
        got = returned_lines(read["returned"])
        if not contains(got, want):
            continue
        while got and got[0] not in known:      # what the tool added around the file's bytes is not the file
            got = got[1:]
        while got and got[-1] not in known:
            got = got[:-1]
        matching = sorted(version for version, lines in held.items() if contains(lines, got))
        if matching == [req["version_sha256"]]:
            return "met", None
        if req["version_sha256"] in matching:
            bound = (session.get("bound_versions") or {}).get(req["path"])
            if bound == req["version_sha256"]:
                return "met", "bound_by_pin_or_release"
            seen.append("version_unbound" if bound is None else "version_mismatch")
        else:
            seen.append("version_mismatch")
    if not seen:
        return "unmet", "not_returned"
    return ("unknown", "version_unbound") if "version_unbound" in seen else ("unmet", "version_mismatch")


def unit_read(unit, units, reads, session, versions):
    """`(status, rows)`: `met` when every requirement is met, `unknown` when none is unmet but one is unknown."""
    context = unit.get("operative_context") or [unit["unit_id"]]
    rows = [{"unit_id": req, "status": status, "reason": reason}
            for req in context for status, reason in [requirement(req, units, reads, session, versions)]]
    if all(row["status"] == "met" for row in rows):
        return "met", rows
    if any(row["status"] == "unmet" for row in rows):
        return "unmet", rows
    return "unknown", rows


# ---- the surfaces -------------------------------------------------------------------------------

def surface_row(unit):
    for row in table()["surfaces"]:
        if unit.get("layer") in row.get("layers", []) or unit.get("surface") in row["item_surfaces"]:
            return row
    return None


def _selection(unit, session):
    """What selection evidence the session has for the unit's item: `(basis, selected, surface)`."""
    basis = session.get("basis")
    if basis == "pin":
        selected = session.get("selected") or {}
        return "pin", unit.get("item_ref") in selected, selected.get(unit.get("item_ref"))
    if basis == "selection_history":
        held = session.get("history_selected") or {}
        return "selection_history", unit.get("item_ref") in held, held.get(unit.get("item_ref"))
    return None, None, None


def _before(rows, decision_at):
    return [row for row in rows or [] if isinstance(row.get("at"), int) and row["at"] < decision_at]


def _injected(session, decision_at):
    at = session.get("injection_at")
    return isinstance(at, int) and at <= decision_at


def _result(unit, session, row, state, level, reasons, selection, requirements=None):
    return {"unit_id": unit["unit_id"], "session": session.get("session_ref"), "surface": row["id"] if row else None,
            "state": state, "level": level, "reasons": reasons, "selection": selection or "unknown",
            "requirements": requirements or []}


def _absence(unit, session, row, selection):
    """The selection lacks the item: `not_delivered` only where the release holds it at a complete reference point."""
    release = session.get("release") or {}
    if unit.get("item_ref") not in (release.get("items") or []):
        return _result(unit, session, row, "unknown", None, ["not_in_release"], selection)
    complete, read = derive.absence(release)
    if not complete:
        return _result(unit, session, row, "unknown", None,
                       ["absence_withheld: completeness unknown for " + (", ".join(read["unknown_layers"]) or "the release")],
                       selection)
    return _result(unit, session, row, "not_delivered", None, ["selection_lacks_item"], selection)


def _always(unit, units, session, decision_at, versions, row):
    basis, selected, surface = _selection(unit, session)
    if basis == "selection_history":
        return _history(unit, session, row, selected)
    if basis != "pin":
        return _result(unit, session, row, "unknown", None, [session.get("pin_reason") or "unpinned"], None)
    if not selected:
        return _absence(unit, session, row, "pin")
    if _unavailable(unit, session, surface):
        return _result(unit, session, row, "selected_unavailable", "selected", ["route_unavailable"], "pin")
    if not _injected(session, decision_at):
        return _result(unit, session, row, "unknown", "selected", ["injection_unrecorded_before_decision"], "pin")
    held, why = in_compiled_text(unit, session)
    if held is None:
        return _result(unit, session, row, "unknown", "selected", [why], "pin")
    if not held:
        return _result(unit, session, row, "unknown", "selected", ["absent_from_compiled_text"], "pin")
    if _rank(row, "exposed") >= _rank(row, row["delivered_at"]):
        return _result(unit, session, row, "delivered", "exposed", [], "pin")
    return _result(unit, session, row, "unknown", "exposed", ["below_the_level_the_table_delivers_at"], "pin")


def in_compiled_text(unit, session):
    """`(verdict, reason)` for "the unit's lines are in the compiled instruction text".

    Two sources, one answer. The compiled text itself is the fixture path and stays supported. The
    production path is FACTS: S2 reads the session's snapshot where the snapshot is readable and
    publishes, per unit, how many of its operative-context lines appear in that text under the same
    prefix-stripping rule, with the text's sha256 — so the run never carries the owner's compiled
    instructions and a later stage never reaches outside the run for them (lead decision, WP-11b).

    Neither source is `unknown` by name, never a miss: a unit absent from a text nobody could read
    is not an absence, and reading it as one would turn an input failure into `not_delivered`."""
    facts = (session.get("instruction_coverage") or {}).get(unit["unit_id"])
    if facts is not None:
        total, covered = facts.get("total"), facts.get("covered")
        if not isinstance(total, int) or not isinstance(covered, int) or total < 0 or covered < 0:
            return None, "instruction_coverage_malformed"
        if total == 0:
            return None, "instruction_coverage_counts_no_line"
        return covered >= total, None
    if session.get("instruction_text") is not None:
        return contains(text_lines(session.get("instruction_text")), text_lines(unit["text"])), None
    return None, "compiled_text_unavailable"


def _rank(row, level):
    """A level's place on its surface's ladder, -1 for none."""
    return row["levels"].index(level) if level in row["levels"] else -1


def _unavailable(unit, session, surface):
    return any(r.get("ref") == unit.get("item_ref") and (surface is None or r.get("surface") == surface)
               for r in session.get("unavailable") or [])


def _history(unit, session, row, selected):
    if selected:
        return _result(unit, session, row, "unknown", "library_selected", ["selection_history"], "selection_history")
    return _result(unit, session, row, "unknown", None, ["not_in_selection_history"], "selection_history")


def _guide(unit, units, session, decision_at, versions, row):
    basis, selected, surface = _selection(unit, session)
    reads = _before(session.get("reads"), decision_at)
    status, requirements = unit_read(unit, units, reads, session, versions)
    selection = basis if basis in ("pin", "selection_history") and selected else None
    level = None
    if basis == "pin" and selected:
        level = "selected"
        if _unavailable(unit, session, surface):
            return _result(unit, session, row, "selected_unavailable", level, ["route_unavailable"], "pin", requirements)
        if _injected(session, decision_at) and _pointer(unit, session, surface):
            level = "pointer exposed"
            if _router_read(unit, session, reads):
                level = "router read"
    if status == "met":
        level = "unit read"
    if level is not None and _rank(row, level) >= _rank(row, row["delivered_at"]):
        return _result(unit, session, row, "delivered", level, [] if selection else ["selection_unknown"],
                       selection, requirements)
    unparsed = [m for m in _before(session.get("unparsed"), decision_at) if of_carrier(m, unit, session)]
    partly = any(of_carrier(read, unit, session) for read in reads)
    exposed = row.get("exposed_at") is not None and (_rank(row, level) >= _rank(row, row["exposed_at"]) or partly)
    if exposed:
        if unparsed:
            return _result(unit, session, row, "unknown", level, ["read_unparsed"], selection, requirements)
        if status == "unknown":
            return _result(unit, session, row, "unknown", level,
                           sorted({r["reason"] for r in requirements if r["status"] == "unknown"}), selection, requirements)
        return _result(unit, session, row, "exposed_not_read", level,
                       sorted({r["reason"] for r in requirements if r["status"] != "met"}
                              | ({"partly_read"} if partly and _rank(row, level) < _rank(row, row["exposed_at"]) else set())),
                       selection, requirements)
    if basis == "selection_history":
        return _history(unit, session, row, selected)
    if basis == "pin" and not selected:
        return _absence(unit, session, row, "pin")
    if basis == "pin":
        return _result(unit, session, row, "unknown", level, ["not_exposed_before_decision"], "pin", requirements)
    return _result(unit, session, row, "unknown", None, [session.get("pin_reason") or "unpinned"], None, requirements)


def _pointer(unit, session, surface):
    """The guide's pointer in the compiled text: the router path for a relevant item, its own emitted path for a
    requested one.

    Answered from the FACT when the session carries one (`item_pointer_in_compiled_text`, published by S2 where
    the snapshot is readable), because the compiled text is the owner's and does not enter a run; the text path
    below stays for the frozen fixtures and for a caller that holds the text. A fact of None is "this surface has
    no pointer to find", which is not the same as a pointer that is missing, so it is returned as given."""
    stated = session.get("item_pointer_in_compiled_text") or {}
    if unit.get("item_ref") in stated:
        return stated[unit["item_ref"]]
    text = session.get("instruction_text") or ""
    if surface == "relevant":
        return bool(session.get("router_path")) and f"Relevant procedures: {session['router_path']}" in text
    emitted = [path for path, ref in (session.get("emitted") or {}).items() if ref == unit.get("item_ref")]
    return any(path in text for path in emitted)


def _router_read(unit, session, reads):
    """A read of the router whose returned content holds the guide's own line (the line ends with its item ref)."""
    marker = f"({unit.get('item_ref')})"
    return any(read["path"].endswith("/" + ROUTER) and any(line.endswith(marker) for line in returned_lines(read["returned"]))
               for read in reads)


def _native(unit, units, session, decision_at, versions, row):
    events = [e for e in session.get("native_events") or [] if isinstance(e.get("at"), int) and e["at"] <= decision_at]
    if not events:
        return _result(unit, session, row, "unknown", None, ["no_recorded_injection_before_decision"], None)
    latest = max(events, key=lambda e: e["at"])
    if unit["unit_id"] in (latest.get("unit_ids") or []):
        return _result(unit, session, row, "delivered", "loaded", [], "native")
    release = session.get("release") or {}
    complete, read = derive.absence(release)
    if not complete:
        return _result(unit, session, row, "unknown", "identity",
                       ["absence_withheld: completeness unknown for " + (", ".join(read["unknown_layers"]) or "the release")],
                       "native")
    return _result(unit, session, row, "not_delivered", "identity", ["not_in_recorded_injection"], "native")


HANDLERS = {"always_rule": _always, "guide": _guide, "native_layer": _native}
# the installer's row is answered by `installer_exposure`, which reads a binding rather than a unit
OTHER_ENTRIES = {"executable_consumed": "installer_exposure"}


def delivery(unit, units, session, decision_at, versions=None, instruction_coverage=None):
    """§6.3's answer for one unit in one session before `decision_at` (a record ordinal of that session).

    `instruction_coverage` is the per-unit coverage of the compiled instruction text as FACTS
    (`{unit_id: {covered, total, text_sha256}}`), which S2 publishes because the text itself is the
    owner's and does not enter the run. Passed here or carried on the session; absent, the fixture's
    `instruction_text` answers; absent too, the state is `unknown` naming that."""
    if not isinstance(decision_at, int):
        raise Refused(f"DELIVERY_INPUT_INVALID decision_at {decision_at!r}: a record ordinal of the session")
    if instruction_coverage is not None:
        session = {**session, "instruction_coverage": instruction_coverage}
    versions = versions if versions is not None else versions_of(units.values())
    row = surface_row(unit)
    if row is None:
        return _result(unit, session, None, "unknown", None, ["surface_unclassified"], None)
    if row["producer"] == "absent":
        return _result(unit, session, row, "unknown", None, [f"producer_absent:{row['id']}"], None)
    handler = HANDLERS.get(row["id"])
    if handler is None:
        raise Refused(f"SURFACE_UNHANDLED {row['id']}: the table says implemented and no handler answers it")
    return handler(unit, units, session, decision_at, versions, row)


def installer_exposure(binding, receipt, snapshot_artifacts):
    """The installer row (§6.3): `consumed` when the store's `installation_binding()` is bound, its receipt is a
    success receipt, and the receipt's release artifacts hold every artifact the snapshot records; `unknown` with the
    reason otherwise. Exposure is judged against the executing installer and, for a recovered transaction, the one
    that began it."""
    row = next(r for r in table()["surfaces"] if r["id"] == "executable_consumed")
    out = {"surface": row["id"], "realization": "golden", "waiting": "receipt_live_waiting_wp15"}
    if not (binding or {}).get("bound"):
        return {**out, "state": "unknown", "level": None, "reasons": ["unbound"]}
    if (receipt or {}).get("schema") != "InstallationReceipt/v1" or receipt.get("transaction_id") != binding.get("transaction_id"):
        return {**out, "state": "unknown", "level": None, "reasons": ["receipt_not_the_binding's"]}
    if receipt.get("result") != "success":
        return {**out, "state": "unknown", "level": "identity of the producing version", "reasons": ["receipt_not_success"]}
    released = {(a.get("path"), a.get("sha256")) for a in receipt.get("artifacts") or [] if a.get("role") == "release"}
    missing = [a for a in snapshot_artifacts or [] if (a.get("path"), a.get("sha256")) not in released]
    if missing or not snapshot_artifacts:
        return {**out, "state": "unknown", "level": "identity of the producing version",
                "reasons": ["artifacts_unmatched" if missing else "snapshot_records_no_artifact"]}
    digests = [binding.get("installer_digest")] + ([binding["begun_by_installer_digest"]]
                                                   if binding.get("begun_by_installer_digest") else [])
    return {**out, "state": "delivered", "level": "consumed", "reasons": [], "installer_digests": digests}


# ---- the table's checks and the frozen fixtures -------------------------------------------------

def table_problems(held=None):
    """An implemented surface no handler answers, a handler for no implemented surface, an absent surface with no
    reason, a level the row's ladder does not hold, a licensed level whose state is not one of the five."""
    held = held or table()
    problems = []
    implemented = {r["id"] for r in held["surfaces"] if r["producer"] == "implemented"}
    answered = set(HANDLERS) | set(OTHER_ENTRIES)
    problems += [f"SURFACE_UNHANDLED {i}: implemented, and no handler answers it" for i in sorted(implemented - answered)]
    problems += [f"HANDLER_ORPHAN {i}: a handler for no implemented surface" for i in sorted(answered - implemented)]
    for r in held["surfaces"]:
        if r["producer"] == "absent" and not r.get("reason_absent"):
            problems.append(f"TABLE_INVALID surfaces/{r['id']}: absent with no reason")
        for key in ("delivered_at", "exposed_at"):
            if r.get(key) is not None and r[key] not in r["levels"]:
                problems.append(f"TABLE_INVALID surfaces/{r['id']}: {key} {r[key]!r} is not one of its levels")
    for r in held["licensed_levels"]:
        if r["state"] not in held["states"] or not r.get("decision"):
            problems.append(f"TABLE_INVALID licensed_levels/{r['id']}: a state of the five and a decision are required")
    return problems


def expected_state(row, level):
    """The state the table's own fields give a unit that reached `level` on `row`'s surface and no further."""
    if level == row["delivered_at"]:
        return "delivered"
    if row.get("exposed_at") is not None and row["levels"].index(level) >= row["levels"].index(row["exposed_at"]):
        return "exposed_not_read"
    return "unknown"


def _unit(uid, path, text, version="a" * 64, layer="catalog", surface="relevant", ref="claude:guides/g", context=None, n=1):
    return {"unit_id": uid, "path": path, "text": text, "version_sha256": version, "layer": layer, "surface": surface,
            "item_ref": ref, "operative_context": context or [uid], "n": n, "start": n * 100}


def _builder(row, level):
    """One case that reaches exactly `level` on `row`'s surface: `(unit, units, session, decision_at)`."""
    if row["id"] == "always_rule":
        unit = _unit("u-a", "claude/CLAUDE.md", "- Verify before you claim.", surface="always", ref="claude:core")
        session = {"session_ref": "claude:s", "basis": "pin", "selected": {"claude:core": "always"},
                   "instruction_text": "# Activated private instructions\n- Verify before you claim.\n"}
        if level == "exposed":
            session["injection_at"] = 1
        return unit, {unit["unit_id"]: unit}, session, 5
    if row["id"] == "guide":
        unit = _unit("u-g", "claude/guides/g.md", "- Read the log before you retry.")
        session = {"session_ref": "claude:s", "basis": "pin", "selected": {"claude:guides/g": "relevant"},
                   "router_path": "/state/runtime/x/router/relevant.md",
                   "instruction_text": "Relevant procedures: /state/runtime/x/router/relevant.md\n", "reads": []}
        at = row["levels"].index(level)
        if at >= 1:
            session["injection_at"] = 1
        if at >= 2:
            session["reads"].append({"at": 2, "path": "/state/runtime/x/router/relevant.md",
                                     "returned": "- [g](/state/runtime/x/items/item-g/guides/g.md) — retries (claude:guides/g)\n"})
        if at >= 3:
            session["reads"].append({"at": 3, "path": "/state/runtime/x/items/item-g/guides/g.md",
                                     "returned": "     1\t- Read the log before you retry.\n"})
        return unit, {unit["unit_id"]: unit}, session, 5
    if row["id"] == "native_layer":
        unit = _unit("u-n", "native_global", "- Answer in Korean.", layer="native_global", surface=None, ref=None)
        session = {"session_ref": "claude:s", "native_events": [{"at": 1, "unit_ids": ["u-n"] if level == "loaded" else []}],
                   "release": {"complete": False, "layers": {"native_settings": "unknown"}, "items": []}}
        return unit, {unit["unit_id"]: unit}, session, 5
    unit = _unit(f"u-{row['id']}", "claude/x", "- x", surface=(row["item_surfaces"] or [None])[0])
    return unit, {unit["unit_id"]: unit}, {"session_ref": "claude:s", "basis": "pin"}, 5


def _cases(section, row, held):
    if section == "licensed_levels":
        unit = _unit("u-h", "claude/guides/h.md", "- h", ref="claude:guides/h")
        session = {"session_ref": "claude:s", "basis": row["basis"], "history_selected": {"claude:guides/h": "relevant"}}
        return [{"kind": "delivery", "unit": unit, "units": {unit["unit_id"]: unit}, "session": session, "decision_at": 5,
                 "expected": {"state": row["state"], "level": row["level"]}}]
    if row["id"] == "executable_consumed":
        binding = {"bound": True, "receipt_id": "r" * 64, "transaction_id": "t1", "installer_digest": "d1",
                   "release_digest": "rd", "begun_by_installer_digest": None}
        receipt = {"schema": "InstallationReceipt/v1", "transaction_id": "t1", "result": "success",
                   "artifacts": [{"path": "runtime/baselines/b/inventory.json", "sha256": "s1", "role": "release"},
                                 {"path": "launch/bin/x", "sha256": "s2", "role": "owned"}]}
        artifacts = [{"path": "runtime/baselines/b/inventory.json", "sha256": "s1"}]
        return [{"kind": "installer", "binding": binding, "receipt": receipt, "artifacts": artifacts,
                 "expected": {"state": "delivered", "level": row["delivered_at"]}},
                {"kind": "installer", "binding": {"bound": False}, "receipt": None, "artifacts": artifacts,
                 "expected": {"state": "unknown", "level": None}}]
    if row["producer"] == "absent":
        unit, units, session, at = _builder(row, row["levels"][0])
        return [{"kind": "delivery", "unit": unit, "units": units, "session": session, "decision_at": at,
                 "expected": {"state": "unknown", "level": None, "reason": f"producer_absent:{row['id']}"}}]
    cases = []
    for level in row["levels"]:
        unit, units, session, at = _builder(row, level)
        cases.append({"kind": "delivery", "unit": unit, "units": units, "session": session, "decision_at": at,
                      "expected": {"state": expected_state(row, level), "level": level}})
    return cases


def generate_fixtures(path=FIXTURES_PATH):
    """Write one fixture per row of the table, once; a second call refuses."""
    path = pathlib.Path(path)
    if path.exists():
        raise Refused(f"FIXTURES_FROZEN {path}: generated once and committed; delete it by hand to regenerate")
    held = table()
    fixtures = [{"id": f"{section}/{row['id']}", "cases": _cases(section, row, held)}
                for section in SECTIONS for row in held[section]]
    doc = {"$comment": "design §6.3: one frozen fixture per row of tables/delivery_evidence.json, written once by "
                       "`runlib/delivery_evidence.py --generate-fixtures`; the self-test never regenerates them.",
           "fixtures": fixtures}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(fixtures)


def run_fixture(fixture):
    problems = []
    for n, case in enumerate(fixture["cases"]):
        try:
            if case["kind"] == "installer":
                result = installer_exposure(case["binding"], case["receipt"], case["artifacts"])
            else:
                result = delivery(case["unit"], case["units"], case["session"], case["decision_at"])
            got = {"state": result["state"], "level": result["level"]}
            if "reason" in case["expected"]:
                got["reason"] = (result["reasons"] or [None])[0]
        except Refused as exc:
            got = f"refused {str(exc).split()[0]}"
        if got != case["expected"]:
            problems.append(f"FIXTURE_FAILED {fixture['id']} case {n}: expected {case['expected']}, got {got}")
    return problems


# ---- the self-test ------------------------------------------------------------------------------

# The design's §6.3, copied here once (WP-10 done-when 5): each surface with its levels in order, and the five states.
DESIGN_6_3_SURFACES = (
    ("Rule on the always surface", ("selected", "exposed")),
    ("Guide", ("selected", "pointer exposed", "router read", "unit read")),
    ("Executable invoked directly (hook script, skill script, tool, wrapper)", ("identity", "invoked", "completed")),
    ("Executable producing consumed artifacts (catalog compiler, installer)", ("identity of the producing version", "consumed")),
    ("Skill", ("selected", "listed", "invoked")),
    ("Hook", ("selected", "registered for the route", "fired")),
    ("Native layer", ("identity", "loaded")),
    ("Child session (subagent reach)", ("the child's own record",)),
)
DESIGN_6_3_STATES = ("delivered", "exposed_not_read", "selected_unavailable", "not_delivered", "unknown")


def fidelity_problems(held=None):
    held = held or table()
    problems = []
    surfaces = tuple((r["design"], tuple(r["levels"])) for r in held["surfaces"])
    for n, (have, want) in enumerate(zip(surfaces, DESIGN_6_3_SURFACES)):
        if have != want:
            problems.append(f"CONTRACT_DRIFT surface {n + 1}: the table says {have}, §6.3 says {want}")
    if len(surfaces) != len(DESIGN_6_3_SURFACES):
        problems.append(f"CONTRACT_DRIFT surfaces: {len(surfaces)} rows, §6.3 has {len(DESIGN_6_3_SURFACES)}")
    if tuple(held["states"]) != DESIGN_6_3_STATES:
        problems.append(f"CONTRACT_DRIFT states: {held['states']}")
    return problems


def self_test():
    failures, ran = [], []

    def expect(label, got, want):
        ran.append(label)
        if got != want:
            failures.append(f"{label}: expected {want!r}, got {got!r}")

    def named(label, lines, needle):
        ran.append(label)
        if not any(needle in line for line in lines):
            failures.append(f"{label}: expected {needle!r} in {lines}")

    def refused(label, action, code):
        ran.append(label)
        try:
            action()
        except Refused as exc:
            if not str(exc).startswith(code):
                failures.append(f"{label}: refused {str(exc)[:160]!r}, expected {code}")
            return
        except Exception as exc:  # noqa: BLE001 - anything else fails this control by name, never the suite
            failures.append(f"{label}: raised {type(exc).__name__}: {exc}, expected {code}")
            return
        failures.append(f"{label}: not refused, expected {code}")

    held = table()
    expect("the table's surfaces each have their handler, and its rows are well formed", table_problems(), [])
    expect("the table holds §6.3's surfaces, levels and states", fidelity_problems(), [])
    moved = copy.deepcopy(held)
    moved["surfaces"][1]["levels"] = ["selected", "router read", "pointer exposed", "unit read"]
    named("control: a guide ladder reordered", fidelity_problems(moved), "CONTRACT_DRIFT surface 2")
    claimed = copy.deepcopy(held)
    claimed["surfaces"][4]["producer"] = "implemented"
    named("control: a surface marked implemented with no handler", table_problems(claimed), "SURFACE_UNHANDLED skill")
    silent = copy.deepcopy(held)
    silent["surfaces"][5].pop("reason_absent")
    named("control: an absent surface that does not say why", table_problems(silent), "absent with no reason")

    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["fixtures"]
    executed = set()
    for fixture in fixtures:
        failures.extend(run_fixture(fixture))
        executed.add(fixture["id"])  # recorded after its cases ran through the production functions
    frozen = {f["id"] for f in fixtures}
    expect("table rows, frozen fixtures and executed cases are one set", derive.coverage_problems(row_ids(), frozen, executed), [])
    added = copy.deepcopy(held)
    added["surfaces"].append({**added["surfaces"][0], "id": "plugin"})
    named("control: a surface added to a scratch copy, the frozen fixtures unchanged",
          derive.coverage_problems(row_ids(added), frozen, executed), "ROW_UNFIXTURED surfaces/plugin")
    named("control: an executed case removed from the run's record",
          derive.coverage_problems(row_ids(), frozen, executed - {"surfaces/guide"}), "CASE_NOT_EXECUTED surfaces/guide")
    by_id = {f["id"]: f for f in fixtures}
    _TABLES["t"] = {**held, "surfaces": [{**r, "exposed_at": None} if r["id"] == "guide" else r for r in held["surfaces"]]}
    try:
        named("control: a frozen guide fixture against a table that no longer exposes at the pointer",
              run_fixture(by_id["surfaces/guide"]), "FIXTURE_FAILED surfaces/guide")
    finally:
        _TABLES["t"] = held
    with tempfile.TemporaryDirectory() as td:
        target = pathlib.Path(td) / "fixtures.json"
        expect("the generator writes one fixture per row", generate_fixtures(target), len(row_ids()))
        expect("the generator's fixtures are the frozen ones", json.loads(target.read_text(encoding="utf-8"))["fixtures"],
               fixtures)
        refused("a second generation", lambda: generate_fixtures(target), "FIXTURES_FROZEN")

    # returned bytes
    expect("a reading tool's line-number prefixes are removed", returned_lines("     1\t- a\n     2→- b\n"), ["- a", "- b"])
    expect("control: a line that begins with a digit is kept when not every line has a prefix",
           returned_lines("12 rules\n- a\n"), ["12 rules", "- a"])

    # ---- done-when 2: the O3 verdicts that rest on delivery evidence, each with its flipped control
    v1, v2 = "1" * 64, "2" * 64
    path, path2 = "claude/guides/review.md", "claude/guides/second.md"
    deployed = "/state/runtime/s/items/item-claude_guides_review/guides/review.md"
    deployed2 = "/state/runtime/s/items/item-claude_guides_second/guides/second.md"
    heading = _unit("u-h1", path, "## Review", v1, n=1, ref="claude:guides/review")
    rule = _unit("u-r1", path, "- Read the diff twice.", v1, n=2, ref="claude:guides/review",
                 context=["u-r1", "u-h1", "u-x1", "u-s1"])
    exception = _unit("u-x1", path, "### Exceptions\n- except a one-line typo fix.", v1, n=3, ref="claude:guides/review")
    second = _unit("u-s1", path2, "- Name the reviewer.", v1, n=1, ref="claude:guides/second")
    units = {u["unit_id"]: u for u in (heading, rule, exception, second)}
    other_second = [_unit("u-s2", path2, "- Name the reviewer.", v2, n=1, ref="claude:guides/second"),
                    _unit("u-s3", path2, "- And name who reviews them.", v2, n=2, ref="claude:guides/second")]
    versions = versions_of(list(units.values()))                  # one version of each guide
    both_versions = versions_of(list(units.values()) + other_second)  # the second guide at two versions
    full = "\n".join(f"{n:>6}\t{line}" for n, line in enumerate(["## Review", "- Read the diff twice.", "### Exceptions",
                                                                  "- except a one-line typo fix."], 1))
    second_read = {"at": 4, "path": deployed2, "returned": "     1\t- Name the reviewer.\n"}
    pinned = {"session_ref": "claude:p", "host": "claude", "basis": "pin",
              "selected": {"claude:guides/review": "relevant", "claude:guides/second": "relevant"},
              "router_path": "/state/runtime/s/router/relevant.md",
              "instruction_text": "Relevant procedures: /state/runtime/s/router/relevant.md\n", "injection_at": 1,
              "reads": [{"at": 3, "path": deployed, "returned": full}, second_read]}

    def state(session, unit=rule, at=10, held_units=units, held_versions=None):
        return delivery(unit, held_units, session, at, held_versions or versions)

    expect("O3: an operative context across two guides read completely is delivered", state(pinned)["state"], "delivered")
    expect("O3: the second guide unread is exposed_not_read",
           state({**pinned, "reads": pinned["reads"][:1]})["state"], "exposed_not_read")
    other_version = {**pinned, "reads": pinned["reads"][:1] + [
        {**second_read, "returned": "     1\t- Name the reviewer.\n     2\t- And name who reviews them.\n"}]}
    expect("O3: the second guide read at a different version than the requirement names is exposed_not_read",
           (state(other_version, held_versions=both_versions)["state"],
            state(other_version, held_versions=both_versions)["requirements"][-1]),
           ("exposed_not_read", {"unit_id": "u-s1", "status": "unmet", "reason": "version_mismatch"}))
    expect("control: the second guide's line read where two versions share it, the pin naming none, is unknown",
           state(pinned, held_versions=both_versions)["requirements"][-1]["reason"], "version_unbound")
    expect("control: ... and delivered when the pin names its version",
           state({**pinned, "bound_versions": {path2: v1}}, held_versions=both_versions)["state"], "delivered")
    no_exception = "\n".join(full.splitlines()[:2])
    expect("O3: a read returning the unit and its heading but not the enclosing exception is exposed_not_read",
           state({**pinned, "reads": [{"at": 3, "path": deployed, "returned": no_exception}, second_read]})["state"],
           "exposed_not_read")
    truncated = "\n".join(full.splitlines()[:1])
    expect("O3: a guide read spanning the unit but truncated before it is exposed_not_read",
           state({**pinned, "reads": [{"at": 3, "path": deployed, "returned": truncated}, second_read]})["state"],
           "exposed_not_read")
    expect("control: the same reads after the decision expose only the pointer, never deliver",
           (state(pinned, at=3)["state"], state(pinned, at=3)["level"]), ("exposed_not_read", "pointer exposed"))
    pointer_only = {**pinned, "reads": []}
    expect("O3: a guide pointer exposed and never read is exposed_not_read, at the pointer",
           (state(pointer_only)["state"], state(pointer_only)["level"]), ("exposed_not_read", "pointer exposed"))
    expect("control: the pointer in an injection recorded after the decision is not exposure",
           state({**pointer_only, "injection_at": 20})["state"], "unknown")
    routed = {**pointer_only, "reads": [{"at": 2, "path": "/state/runtime/s/router/relevant.md",
                                         "returned": f"- [Review]({deployed}) — reviews (claude:guides/review)\n"}]}
    expect("the router read is a level of its own and still not a unit read", (state(routed)["state"], state(routed)["level"]),
           ("exposed_not_read", "router read"))
    unparsed = {**pointer_only, "unparsed": [{"at": 2, "path": deployed}]}
    expect("a tool call naming the guide whose bytes could not be read leaves the state unknown, never a claimed miss",
           (state(unparsed)["state"], state(unparsed)["reasons"]), ("unknown", ["read_unparsed"]))
    unavailable = {**pinned, "reads": [], "unavailable": [{"ref": "claude:guides/review", "surface": "relevant",
                                                           "reason": "native consumption is disabled"}]}
    expect("O3: a selected item whose route is unavailable is selected_unavailable", state(unavailable)["state"],
           "selected_unavailable")
    expect("control: the same item with no unavailable row is exposed_not_read", state({**unavailable, "unavailable": []})["state"],
           "exposed_not_read")
    unpinned = {"session_ref": "claude:u", "host": "claude", "basis": None, "pin_reason": "unpinned"}
    expect("O3: an unpinned session with no read is unknown, naming why",
           (state(unpinned)["state"], state(unpinned)["reasons"]), ("unknown", ["unpinned"]))
    read_unpinned = {**unpinned, "reads": pinned["reads"]}
    expect("O3: an unpinned session that read the unit before the decision is delivered, its selection unknown",
           (state(read_unpinned)["state"], state(read_unpinned)["selection"], state(read_unpinned)["reasons"]),
           ("delivered", "unknown", ["selection_unknown"]))
    expect("control: the same reads after the decision deliver nothing", state(read_unpinned, at=3)["state"], "unknown")
    # identical fragment in two versions with different contexts: the pin or the release binds it
    rule_v2 = _unit("u-r2", path, "- Read the diff twice.", v2, n=2, ref="claude:guides/review", context=["u-r2", "u-x2"])
    exception_v2 = _unit("u-x2", path, "### Exceptions\n- except a docs-only change.", v2, n=3, ref="claude:guides/review")
    twin = {**units, "u-r2": rule_v2, "u-x2": exception_v2}
    twin_versions = versions_of(list(twin.values()))
    just_rule = {"at": 3, "path": deployed, "returned": "     2\t- Read the diff twice.\n"}
    v1_exception = {"at": 4, "path": deployed, "returned": "     3\t### Exceptions\n     4\t- except a one-line typo fix.\n"}
    lone = _unit("u-r1", path, "- Read the diff twice.", v1, n=2, ref="claude:guides/review", context=["u-r1", "u-x1"])
    twins = {**twin, "u-r1": lone}

    def twin_state(bound):
        session = {**pinned, "reads": [just_rule, v1_exception], "bound_versions": bound}
        return delivery(lone, twins, session, 10, twin_versions)
    expect("O3: an identical fragment in two versions binds to the version the pin names: delivered",
           twin_state({path: v1})["state"], "delivered")
    expect("O3: ... and is unknown when nothing binds it", (twin_state({})["state"], twin_state({})["reasons"]),
           ("unknown", ["version_unbound"]))
    expect("control: bound to the other version, the requirement is unmet", twin_state({path: v2})["state"], "exposed_not_read")
    # the always surface
    core = _unit("u-c1", "claude/CLAUDE.md", "- Verify before you claim.", surface="always", ref="claude:core")
    core_units = {"u-c1": core}
    always = {"session_ref": "claude:p", "basis": "pin", "selected": {"claude:core": "always"}, "injection_at": 1,
              "instruction_text": "# Activated private instructions\n\n## Always in this environment\n\n- Verify before you claim.\n"}
    expect("O3: a rule on the always surface exposed in a recorded injection is delivered",
           delivery(core, core_units, always, 5)["state"], "delivered")
    expect("control: the same rule absent from the compiled text is unknown",
           delivery(core, core_units, {**always, "instruction_text": "# Activated\n"}, 5)["state"], "unknown")
    # the full O3 verdicts through the derivation
    met = {n: "met" for n in derive.table()["requirements"]}

    def verdict(state_row, following="not_followed", contribution="harmed"):
        judged = {"situation": "yes", "action": "yes", "following": following, "contribution": contribution}
        point = {"complete": True, "layers": {}, "units": {"u": {"A": judged, "B": judged}}}
        return derive.unit_outcome({"candidate": {"candidate_id": "k1", "type": "A", "lifecycle": None},
                                    "judges": {"A": {"requirements": met}, "B": {"requirements": met}},
                                    "points": {"release": point, "current": point}, "checks_pass": True, "lineages": 2},
                                   {"u": [{"session": state_row["session"], "state": state_row["state"]}]},
                                   "untested: s8_deferred")["kind"]["kind"]
    expect("O3 end to end: a pinned session violating a delivered rule is a misfire",
           verdict(delivery(core, core_units, always, 5)), "misfire")
    expect("O3 end to end: a pointer exposed and never read is a misfire (trigger)",
           derive.unit_outcome({"candidate": {"candidate_id": "k1", "type": "A", "lifecycle": None},
                                "judges": {"A": {"requirements": met}, "B": {"requirements": met}},
                                "points": {p: {"complete": True, "layers": {}, "units": {"u-r1": {
                                    who: {"situation": "yes", "action": "yes", "following": "not_followed",
                                          "contribution": "harmed"} for who in ("A", "B")}}} for p in ("release", "current")},
                                "checks_pass": True, "lineages": 2},
                               {"u-r1": [{"session": "claude:p", "state": state(pointer_only)["state"]}]},
                               "untested: s8_deferred")["unit_outcomes"][0]["outcome"], "misfire (trigger)")
    expect("O3 end to end: selected_unavailable is not delivered", verdict(state(unavailable)), "not delivered")
    expect("O3 end to end: an unpinned session is unclassified", verdict(state(unpinned)), "unclassified")
    expect("O3 end to end: an unpinned session that read the unit before violating is a misfire",
           verdict(state(read_unpinned)), "misfire")
    # the selection history, Codex pins, and an absence under the literal policy
    history = {"session_ref": "claude:h", "basis": "selection_history", "history_selected": {"claude:core": "always"}}
    expect("a row the selection history answers is library_selected, delivery unknown",
           (delivery(core, core_units, history, 5)["state"], delivery(core, core_units, history, 5)["level"]),
           ("unknown", "library_selected"))
    expect("control: the same item under a pin and a recorded injection is delivered",
           delivery(core, core_units, always, 5)["state"], "delivered")
    codex = {"session_ref": "codex:t", "host": "codex", "basis": None, "pin_reason": "pin_predates_rollout_binding"}
    expect("a Codex pin naming no rollout is unknown with the F-22 reason",
           delivery(core, core_units, codex, 5)["reasons"], ["pin_predates_rollout_binding"])
    expect("golden: a joined Codex pin answers as a pin does",
           delivery(core, core_units, {**always, "session_ref": "codex:j", "host": "codex"}, 5)["state"], "delivered")
    absent_item = {**always, "selected": {}, "release": {"complete": False, "layers": {"catalog": "complete",
                                                                                         "native_settings": "unknown"},
                                                         "items": ["claude:core"]}}
    expect("an item the release holds and the selection lacks is withheld under the literal policy, naming the layer",
           (delivery(core, core_units, absent_item, 5)["state"], delivery(core, core_units, absent_item, 5)["reasons"]),
           ("unknown", ["absence_withheld: completeness unknown for native_settings"]))
    expect("control: at a complete release it is not_delivered",
           delivery(core, core_units, {**absent_item, "release": {**absent_item["release"], "complete": True}}, 5)["state"],
           "not_delivered")
    # native layers and absent producers
    native = _unit("u-n1", "native_global", "- Answer in Korean.", layer="native_global", surface=None, ref=None)
    loaded = {"session_ref": "claude:p", "native_events": [{"at": 1, "unit_ids": ["u-n1"]}, {"at": 8, "unit_ids": []}]}
    expect("a native layer loaded by the most recent injection at or before the decision is delivered",
           delivery(native, {"u-n1": native}, loaded, 5)["state"], "delivered")
    expect("control: a later injection without it, before the decision, does not deliver it",
           delivery(native, {"u-n1": native}, {**loaded, "release": {"complete": True, "layers": {}}}, 9)["state"],
           "not_delivered")
    hook = _unit("u-k1", "claude/hooks/h.py", "x", surface="event", ref="claude:hooks/h")
    expect("a surface no producer reads answers unknown naming it",
           delivery(hook, {"u-k1": hook}, always, 5)["reasons"], ["producer_absent:hook"])
    # the installer row (golden)
    binding = {"bound": True, "receipt_id": "r" * 64, "transaction_id": "t1", "installer_digest": "dY",
               "release_digest": "rd", "begun_by_installer_digest": "dX"}
    receipt = {"schema": "InstallationReceipt/v1", "transaction_id": "t1", "result": "success",
               "artifacts": [{"path": "a", "sha256": "1", "role": "release"}, {"path": "b", "sha256": "2", "role": "owned"}]}
    exposure = installer_exposure(binding, receipt, [{"path": "a", "sha256": "1"}])
    expect("golden: a bound success receipt holding the snapshot's artifacts is consumed, judged against both installers",
           (exposure["state"], exposure["installer_digests"], exposure["waiting"]), ("delivered", ["dY", "dX"], "receipt_live_waiting_wp15"))
    expect("control: an owned row never stands in for a release artifact",
           installer_exposure(binding, receipt, [{"path": "b", "sha256": "2"}])["reasons"], ["artifacts_unmatched"])
    expect("control: an unbound snapshot leaves installer exposure unknown",
           installer_exposure({"bound": False}, receipt, [{"path": "a", "sha256": "1"}])["reasons"], ["unbound"])
    expect("control: a failed transaction's receipt is not consumption",
           installer_exposure(binding, {**receipt, "result": "failed"}, [{"path": "a", "sha256": "1"}])["reasons"],
           ["receipt_not_success"])
    refused("a decision instant that is not an ordinal", lambda: delivery(core, core_units, always, None),
            "DELIVERY_INPUT_INVALID")

    # The compiled instruction text as FACTS (lead decision, WP-11b): S2 counts the lines where the
    # snapshot is readable and publishes the counts, so the owner's compiled instructions never enter
    # the run and no later stage reaches outside it. The two paths must answer alike.
    no_text = {k: v for k, v in always.items() if k != "instruction_text"}
    covered = {core["unit_id"]: {"covered": 1, "total": 1, "text_sha256": "f" * 64}}
    expect("the facts path delivers what the text path delivers",
           delivery(core, core_units, no_text, 5, instruction_coverage=covered)["state"],
           delivery(core, core_units, always, 5)["state"])
    partial = {core["unit_id"]: {"covered": 1, "total": 2, "text_sha256": "f" * 64}}
    expect("a unit the text covers in part is not in the compiled text",
           (delivery(core, core_units, no_text, 5, instruction_coverage=partial)["state"],
            delivery(core, core_units, no_text, 5, instruction_coverage=partial)["reasons"]),
           ("unknown", ["absent_from_compiled_text"]))
    expect("k of n lines is a count, not a judgement: k == n delivers",
           delivery(core, core_units, no_text, 5,
                    instruction_coverage={core["unit_id"]: {"covered": 2, "total": 2,
                                                            "text_sha256": "f" * 64}})["state"],
           "delivered")
    expect("neither facts nor text is unknown by name, never an absence",
           (delivery(core, core_units, no_text, 5)["state"],
            delivery(core, core_units, no_text, 5)["reasons"]),
           ("unknown", ["compiled_text_unavailable"]))
    expect("facts for another unit do not answer for this one",
           delivery(core, core_units, no_text, 5,
                    instruction_coverage={"u-somebody-else": {"covered": 1, "total": 1,
                                                              "text_sha256": "f" * 64}})["reasons"],
           ["compiled_text_unavailable"])
    expect("counts that are not counts are refused by name rather than read as coverage",
           delivery(core, core_units, no_text, 5,
                    instruction_coverage={core["unit_id"]: {"covered": None, "total": 1}})["reasons"],
           ["instruction_coverage_malformed"])
    expect("and a unit whose context counts no line at all is unknown, not covered",
           delivery(core, core_units, no_text, 5,
                    instruction_coverage={core["unit_id"]: {"covered": 0, "total": 0}})["reasons"],
           ["instruction_coverage_counts_no_line"])
    expect("the facts may ride on the session instead of the argument",
           delivery(core, core_units, {**no_text, "instruction_coverage": covered}, 5)["state"],
           "delivered")

    for failure in failures:
        print(f"delivery_evidence --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"delivery_evidence --self-test: OK ({len(ran)} controls, {len(fixtures)} frozen fixtures over the table's {len(row_ids())} "
          "rows: §6.3's surfaces and states as the design states them, every implemented surface handled and every absent "
          "one named, the unit read over returned bytes with prefixes removed and versions bound by pin or release, the O3 "
          "delivery verdicts each with its flipped control and five through the derivation, the selection history, Codex "
          "pins, the literal absence, native layers, the golden installer row)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--generate-fixtures"]:
        target = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else FIXTURES_PATH
        print(f"wrote {generate_fixtures(target)} fixtures to {target}")
        sys.exit(0)
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: delivery_evidence.py --self-test | --generate-fixtures [PATH]")
    sys.exit(self_test())
